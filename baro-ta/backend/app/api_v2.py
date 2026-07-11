"""기능 명세서 v2 엔드포인트 (/api/v2/*) — FR-2/3/4/6/7/8/10/15.

기존 데모 계약(/api/*)은 유지하고, 명세서 기반 플로우를 별도 네임스페이스로 제공한다.
대화 상태(슬롯·되묻기 카운트)는 서버(SQLite)가 들고 있어 프론트는 텍스트만 보내면 된다.
"""
import datetime as dt
import time
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Header, HTTPException

from . import db
from .config import settings
from .core import gate
from .core.explain import add_explanations, build_reminders
from .core.journey import search_journeys, summarize_slots
from .events import broker
from .llm.dialog import dialog_anthropic, dialog_ollama
from .llm.rule_dialog import extract_slots_rule, template_ask
from .schemas import AgentLine
from .schemas_v2 import (
    DialogTurnRequest,
    DialogTurnResponse,
    HoldCreateRequest,
    HoldInfo,
    HoldListResponse,
    Journey,
    JourneySearchRequest,
    JourneySearchResponse,
    Slots,
    UnreservableLeg,
)
from .tools import transit_mock
from .tools.transit_mock import HoldConflict

router = APIRouter()

REQUIRED_SLOTS = ["departure", "arrival", "date"]  # FR-2 필수 슬롯
HOLD_NOTICE_TEMPLATE = [
    "자리를 잡아뒀어요.",
    "아직 돈은 나가지 않았어요.",
    "{m}분 안에 결제하지 않으면 자동으로 취소되고, 돈은 한 푼도 나가지 않아요.",
]
BUS_NOTICE = "버스는 온라인 좌석 선점이 없어요 — 결제 단계에서 바로 표를 사요."


def _emit(session_id: Optional[str], lines: List[AgentLine]) -> None:
    for line in lines:
        broker.publish(session_id or "public", {"type": "agent", **line.model_dump()})


def _missing(slots: Dict[str, Any]) -> List[str]:
    return [s for s in REQUIRED_SLOTS if not slots.get(s)]


# ── FR-2/3/4: 대화 관리자 ──────────────────────────
@router.post("/dialog/turn", response_model=DialogTurnResponse)
async def dialog_turn(body: DialogTurnRequest) -> DialogTurnResponse:
    gate.check("dialog.turn", gate.READ, body.sessionId)
    today = dt.date.today()
    agent: List[AgentLine] = []

    slots, ask_count, last_target = db.dialog_get(body.sessionId)
    engine = settings.llm_provider
    llm_ask: Optional[Dict[str, Any]] = None

    try:
        if engine == "anthropic":
            result = await dialog_anthropic(body.text, slots, today)
        elif engine == "ollama":
            result = await dialog_ollama(body.text, slots, today)
        else:
            engine = "rule"
            result = {"slots": extract_slots_rule(body.text, today, last_target), "ask": None}
        extracted, llm_ask = result["slots"], result.get("ask")
    except Exception as e:
        agent.append(AgentLine(tag="NLU", msg=f"{engine} 대화 관리자 실패 → 규칙 기반 폴백 ({type(e).__name__})"))
        engine = f"{engine}→rule"
        extracted, llm_ask = extract_slots_rule(body.text, today, last_target), None

    # 병합 (새로 추출된 값이 우선 — 사용자가 정정할 수 있어야 함, FR-4 [고칠게요])
    slots.update(extracted)

    # 기본값 (FR-2): 시간대 '아침', 인원 1명, 출발지는 위치 정보
    slots.setdefault("timeOfDay", "아침")
    slots.setdefault("passengers", 1)
    if not slots.get("departure") and body.location:
        from .llm.base import STATIONS

        if body.location in STATIONS:
            slots["departure"] = body.location
            agent.append(AgentLine(tag="GPS", msg=f"위치 정보 기반 출발지 기본값: {body.location}"))

    if extracted:
        pretty = ", ".join(f"{k}={v if not isinstance(v, dict) else v.get('md', v)}" for k, v in extracted.items())
        agent.append(AgentLine(tag="NLU", msg=f"({engine}) 슬롯 추출 → {pretty}"))

    missing = _missing(slots)
    if missing:
        # FR-3: 한 번에 하나만 — LLM 질문이 유효하면 사용, 아니면 템플릿
        if llm_ask and llm_ask["target_slot"] in missing:
            ask = llm_ask
        else:
            ask = template_ask(missing[0], slots)
        ask_count += 1
        db.dialog_save(body.sessionId, slots, ask_count, ask["target_slot"])
        agent.append(AgentLine(tag="ASK", msg=f"되묻기 #{ask_count} → {ask['target_slot']} ({ask['question']})"))
        _emit(body.sessionId, agent)
        return DialogTurnResponse(
            slots=Slots(**slots), missing=missing, next={"type": "ask", **ask}, askCount=ask_count, agent=agent
        )

    # FR-4: 필수 슬롯 완성 → 확인 요약
    summary = summarize_slots(slots)
    db.dialog_save(body.sessionId, slots, ask_count, None)
    agent.append(AgentLine(tag="CONFIRM", msg=f"확인 요약 생성 → {summary}"))
    _emit(body.sessionId, agent)
    return DialogTurnResponse(
        slots=Slots(**slots), missing=[], next={"type": "confirm", "summary": summary}, askCount=ask_count, agent=agent
    )


@router.post("/dialog/{session_id}/reset")
async def dialog_reset(session_id: str) -> dict:
    db.dialog_reset(session_id)
    return {"ok": True}


# ── FR-6/7/8: 전 수단 통합 검색 ─────────────────────
@router.post("/journeys/search", response_model=JourneySearchResponse)
async def journeys_search(body: JourneySearchRequest) -> JourneySearchResponse:
    gate.check("journeys.search", gate.READ, body.sessionId)

    if body.slots is not None:
        slots = {k: v for k, v in body.slots.model_dump().items() if v is not None}
    elif body.sessionId:
        slots, _, _ = db.dialog_get(body.sessionId)
    else:
        raise HTTPException(status_code=400, detail="slots 또는 sessionId가 필요합니다.")
    if _missing(slots):
        raise HTTPException(status_code=400, detail=f"필수 슬롯 미충족: {_missing(slots)}")

    result = search_journeys(
        origin=slots["departure"],
        dest=slots["arrival"],
        time_of_day=slots.get("timeOfDay", "아침"),
        sold_out_all=body.sim.soldOutAll,
        fail_sources=body.sim.failSources,
    )

    # 경로 설명문: 결정적 생성 → LLM(anthropic)이 켜져 있으면 자연어로 덮어쓰기
    add_explanations(result["journeys"])
    explain_engine = "rule"
    if settings.llm_provider == "anthropic" and result["journeys"]:
        try:
            from .llm.explain import explain_anthropic

            texts = await explain_anthropic(result["journeys"])
            for j, text in zip(result["journeys"], texts):
                j["explain"] = text
            explain_engine = "anthropic"
        except Exception:
            pass  # 결정적 설명문 유지

    agent = [
        AgentLine(tag="SEARCH", msg=f"통합 검색: 후보 {result['total_candidates']}건 "
                                    f"({slots['departure']} → {slots['arrival']}, {slots.get('timeOfDay', '아침')})"),
        AgentLine(tag="EXPLAIN", msg=f"경로 설명문 생성 ({explain_engine})"),
    ]
    if result["excluded_sources"]:
        agent.append(AgentLine(tag="SEARCH", msg=f"일부 교통편 확인 실패 → 제외: {', '.join(result['excluded_sources'])}"))
    if result["recombined"]:
        agent.append(AgentLine(tag="RECOMBINE", msg="직결 전 후보 매진 → 환승 대체 여정 생성 (환승 ≤1, 대기 ≥20분, 소요 ≤1.5배)"))
    agent.append(AgentLine(tag="RESULT", msg=f"예약 가능 경로 {len(result['journeys'])}개 제시"))

    _emit(body.sessionId, agent)
    return JourneySearchResponse(
        journeys=[Journey(**j) for j in result["journeys"]],
        excludedSources=result["excluded_sources"],
        recombined=result["recombined"],
        agent=agent,
    )


# ── FR-10: 좌석 선점 (side_effect) ─────────────────
def _hold_to_info(h: Dict[str, Any]) -> HoldInfo:
    remaining = max(0, int(h["deadline"] - time.time())) if h["deadline"] else 0
    minutes = max(1, remaining // 60)
    notices = (
        [HOLD_NOTICE_TEMPLATE[0], HOLD_NOTICE_TEMPLATE[1], HOLD_NOTICE_TEMPLATE[2].format(m=minutes)]
        if h["status"] == "held"
        else []
    )
    unreservable = [
        UnreservableLeg(mode=l["mode"], notice=BUS_NOTICE)
        for l in h["journey"]["legs"]
        if not l["reservable"]
    ]
    # FR-13: 결제 완료된 표는 탑승 안내 알림 계획 제공
    reminders = []
    if h["status"] == "paid" and h.get("date_iso"):
        reminders = build_reminders(h["date_iso"], h["journey"]["dep"], h["journey"]["legs"][0]["from"])
    return HoldInfo(
        dateIso=h.get("date_iso"),
        reminders=reminders,
        holdId=h["id"],
        status=h["status"],
        reserveNo=h["reserve_no"],
        fare=h["fare"],
        deadlineIso=dt.datetime.fromtimestamp(h["deadline"]).isoformat() if h["deadline"] else None,
        remainingSec=remaining if h["status"] == "held" else 0,
        journey=Journey(**h["journey"]),
        passengers=h["passengers"],
        notices=notices,
        unreservableLegs=unreservable,
    )


@router.post("/holds", response_model=HoldInfo)
async def create_hold(
    body: HoldCreateRequest,
    x_approved_by: Optional[str] = Header(default=None),
) -> HoldInfo:
    try:
        gate.check("hold.create", gate.SIDE_EFFECT, body.sessionId, approved_by=x_approved_by)
    except gate.ApprovalRequired as e:
        raise HTTPException(status_code=403, detail=str(e))

    journey = body.journey.model_dump(by_alias=True)
    try:
        # [실연동 교체 지점] korail2/SRTrain reserve — 결제 자동화는 금지 (FR-10)
        r = transit_mock.reserve(journey, body.passengers, conflict=body.sim.holdConflict)
    except HoldConflict:
        # FR-10 예외: 경합 매진 → 프론트가 "다른 길을 찾아볼까요?" 후 재조합 검색
        _emit(body.sessionId, [AgentLine(tag="HOLD", msg="선점 실패(경합 매진) → 재조합 제안")])
        raise HTTPException(status_code=409, detail="방금 자리가 나갔어요")

    hold_id = f"hd_{uuid.uuid4().hex[:8]}"
    db.hold_create(
        hold_id, body.sessionId, journey, body.passengers,
        r["reserveNo"], r["fare"], r["deadlineTs"], date_iso=body.dateIso,
    )
    h = db.hold_get(hold_id)
    assert h is not None

    agent = [AgentLine(tag="HOLD", msg=f"좌석 선점 완료 · 예약번호 {r['reserveNo'] or '없음(버스)'} · "
                                       f"기한 {transit_mock.HOLD_DEADLINE_MIN}분 · 결제는 사용자 직접")]
    _emit(body.sessionId, agent)
    return _hold_to_info(h)


# ── FR-15: 내 예매 확인 ────────────────────────────
@router.get("/holds", response_model=HoldListResponse)
async def list_holds(sessionId: Optional[str] = None) -> HoldListResponse:
    holds = [_hold_to_info(h) for h in db.hold_list(sessionId)]
    active = [h for h in holds if h.status == "held"]
    agent = []
    if active:
        agent.append(AgentLine(tag="MYBOOK", msg=f"결제 대기 중인 표 {len(active)}건 — 최상단 노출 대상"))
    return HoldListResponse(holds=holds, agent=agent)


@router.get("/holds/{hold_id}", response_model=HoldInfo)
async def get_hold(hold_id: str) -> HoldInfo:
    h = db.hold_get(hold_id)
    if h is None:
        raise HTTPException(status_code=404, detail="예약을 찾을 수 없습니다.")
    return _hold_to_info(h)


@router.post("/holds/{hold_id}/pay-confirmed", response_model=HoldInfo)
async def pay_confirmed(
    hold_id: str,
    x_approved_by: Optional[str] = Header(default=None),
    session_id: Optional[str] = None,
) -> HoldInfo:
    """결제 완료 '확인' 처리 — 결제 자체는 외부에서 사용자가 직접 (결제 자동화 금지)."""
    try:
        gate.check("hold.pay_confirmed", gate.SIDE_EFFECT, session_id, approved_by=x_approved_by)
    except gate.ApprovalRequired as e:
        raise HTTPException(status_code=403, detail=str(e))
    h = db.hold_get(hold_id)
    if h is None:
        raise HTTPException(status_code=404, detail="예약을 찾을 수 없습니다.")
    if h["status"] != "held":
        raise HTTPException(status_code=409, detail=f"결제 확인 불가 상태: {h['status']}")
    db.hold_set_status(hold_id, "paid")
    h = db.hold_get(hold_id)
    assert h is not None
    _emit(session_id, [AgentLine(tag="PAID", msg=f"결제 확인 · {hold_id} → 탑승 안내(FR-13) 대상")])
    return _hold_to_info(h)


@router.post("/holds/{hold_id}/cancel", response_model=HoldInfo)
async def cancel_hold(
    hold_id: str,
    x_approved_by: Optional[str] = Header(default=None),
    session_id: Optional[str] = None,
) -> HoldInfo:
    try:
        gate.check("hold.cancel", gate.SIDE_EFFECT, session_id, approved_by=x_approved_by)
    except gate.ApprovalRequired as e:
        raise HTTPException(status_code=403, detail=str(e))
    h = db.hold_get(hold_id)
    if h is None:
        raise HTTPException(status_code=404, detail="예약을 찾을 수 없습니다.")
    # [실연동 교체 지점] korail2/SRTrain 예약 취소 호출
    db.hold_set_status(hold_id, "cancelled")
    h = db.hold_get(hold_id)
    assert h is not None
    return _hold_to_info(h)
