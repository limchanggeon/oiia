"""VER3 엔드포인트 (/api/v3/*) — 단계형 입력 · 통합검색 · 시뮬레이션 예약 · 이메일 알림."""
import datetime as dt
import time
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Header, HTTPException, Query

from . import db
from .config import settings
from .core import fares, gate, notify, places, simulation
from .core.search import search as run_search
from .events import broker
from .schemas import AgentLine
from .schemas_v3 import (
    NotifyDemoResponse,
    PlaceSearchResponse,
    SearchRequest,
    SearchResponse,
    SimHoldRequest,
    SimReservation,
    SimReservationList,
    SummaryResponse,
    TripInput,
    ValidateStepRequest,
    ValidateStepResponse,
)

router = APIRouter()

STEPS = ["departure", "arrival", "date", "arrivalTime", "passengers"]


def _emit(session_id: Optional[str], lines: List[AgentLine]) -> None:
    for line in lines:
        broker.publish(session_id or "public", {"type": "agent", **line.model_dump()})


def _fmt_ampm(minutes: int) -> str:
    m = minutes % 1440
    h, mi = m // 60, m % 60
    ampm = "오전" if h < 12 else "오후"
    h12 = h if 1 <= h <= 12 else (12 if h % 12 == 0 else h % 12)
    return f"{ampm} {h12}시" + (f" {mi}분" if mi else "")


def _weekday(date_iso: str) -> str:
    return "월화수목금토일"[dt.date.fromisoformat(date_iso).weekday()]


# ── FR-1 ①②: 장소 자동완성·추천 ────────────────────
@router.get("/places/search", response_model=PlaceSearchResponse)
async def places_search(q: str = Query(..., min_length=1)) -> PlaceSearchResponse:
    return PlaceSearchResponse(places=places.search(q))


@router.get("/places/nearest", response_model=PlaceSearchResponse)
async def places_nearest(lat: Optional[float] = None, lng: Optional[float] = None) -> PlaceSearchResponse:
    """현재 위치 기반 추천 — 자동 확정하지 않는다 (FR-1 ①). 위치 거부 시에도 200."""
    return PlaceSearchResponse(places=[places.nearest(lat, lng)])


# ── FR-2/3: 단계 검증·저장 ─────────────────────────
def _validate(step: str, data: Dict[str, Any]) -> tuple[bool, str]:
    dep, arr = data.get("departure"), data.get("arrival")
    if step == "departure":
        if not dep:
            return False, "출발지를 선택하면 다음으로 갈 수 있어요"
        return True, ""
    if step == "arrival":
        if not arr:
            return False, "도착지를 선택하면 다음으로 갈 수 있어요"
        if dep and arr and dep["canonicalId"] == arr["canonicalId"]:
            return False, "출발지와 도착지가 같아요. 다른 곳을 골라 주세요"
        return True, ""
    if step == "date":
        if not data.get("date"):
            return False, "날짜를 고르면 다음으로 갈 수 있어요"
        try:
            picked = dt.date.fromisoformat(data["date"])
        except ValueError:
            # 잘못된 형식("2026-13-99")이 500을 내지 않도록 방어
            return False, "날짜 형식이 올바르지 않아요. 달력에서 다시 골라 주세요"
        if picked < dt.date.today():
            return False, "지난 날짜는 고를 수 없어요"
        return True, ""
    if step == "arrivalTime":
        t = data.get("arrivalTime")
        if t is None:
            return False, "몇 시까지 도착할지 고르면 다음으로 갈 수 있어요"
        if not (0 <= t <= 1435) or t % 5 != 0:
            return False, "시간은 5분 단위로 골라 주세요"
        # 당일이면 이미 지난 시각 금지 (FR-2)
        if data.get("date") == dt.date.today().isoformat():
            now = dt.datetime.now()
            if t <= now.hour * 60 + now.minute:
                return False, "이미 지난 시각이에요. 더 늦은 시각을 골라 주세요"
        return True, ""
    if step == "passengers":
        p = data.get("passengers") or {}
        total = p.get("senior", 0) + p.get("adult", 0) + p.get("student", 0)
        if total < 1:
            return False, "한 명 이상 선택해 주세요"
        return True, ""
    return False, "알 수 없는 단계예요"


@router.post("/input/validate", response_model=ValidateStepResponse)
async def validate_step(body: ValidateStepRequest) -> ValidateStepResponse:
    # exclude_unset: 클라이언트가 **보낸 필드만** 갱신한다.
    # (exclude_none만 쓰면 passengers 기본값 0명이 항상 실려 와 이전 입력을 덮어쓴다.)
    data = body.input.model_dump(exclude_none=True, exclude_unset=True)
    saved = db.input_get(body.sessionId)
    saved.update(data)                      # [이전]으로 돌아가도 값 유지 (FR-3)
    db.input_save(body.sessionId, saved)
    ok, msg = _validate(body.step, saved)
    return ValidateStepResponse(ok=ok, message=msg, input=TripInput(**saved))


@router.get("/input/{session_id}", response_model=SummaryResponse)
async def get_input(session_id: str) -> SummaryResponse:
    """FR-3 중단 복귀 + FR-4 확인 요약 (문구는 서버가 생성)."""
    data = db.input_get(session_id)
    ready = all(_validate(s, data)[0] for s in STEPS)
    lines: List[str] = []
    if data.get("departure") and data.get("arrival"):
        lines.append(f"{data['departure']['name']} → {data['arrival']['name']}")
    if data.get("date"):
        d = dt.date.fromisoformat(data["date"])
        lines.append(f"{d.month}월 {d.day}일 {_weekday(data['date'])}요일")
    if data.get("arrivalTime") is not None:
        lines.append(f"{_fmt_ampm(data['arrivalTime'])}까지 도착")
    p = data.get("passengers") or {}
    if p:
        lines.append(f"노약자(만 65세 이상) {p.get('senior', 0)}명 · 성인 {p.get('adult', 0)}명 · 학생 {p.get('student', 0)}명")
        lines.append(f"총 {p.get('senior', 0) + p.get('adult', 0) + p.get('student', 0)}명")
    return SummaryResponse(lines=lines, input=TripInput(**data), ready=ready)


@router.post("/demo/{session_id}/reset")
async def demo_reset(session_id: str) -> dict:
    """[데모 초기화] — 입력값·시뮬레이션 예약·서버 알림 예약 일괄 삭제 (§5-7)."""
    db.demo_reset(session_id)
    return {"ok": True}


# ── FR-5/6/7/8: 통합 검색 ──────────────────────────
@router.post("/search", response_model=SearchResponse)
async def search(body: SearchRequest) -> SearchResponse:
    data = body.input.model_dump(exclude_none=True) if body.input else db.input_get(body.sessionId or "")
    missing = [s for s in STEPS if not _validate(s, data)[0]]
    if missing:
        raise HTTPException(status_code=400, detail=f"입력이 완료되지 않았어요: {missing}")

    result = await run_search(
        origin_id=data["departure"]["canonicalId"],
        dest_id=data["arrival"]["canonicalId"],
        date_iso=data["date"],
        arrive_by=data["arrivalTime"],
        passengers=data["passengers"],
        sold_out_all=body.sim.soldOutAll,
        fail_sources=body.sim.failSources,
        seat_lookup_fail=body.sim.seatLookupFail,
        use_simulated_for_unknown=body.useSimulatedForUnknown,
        only_confirmed=body.onlyConfirmed,
    )

    # FR-8: LLM 비교 설명문 — 확정된 데이터만 전달. 실패하거나 숫자를 지어내면
    # 정형 문구("가장 빠름"/"환승 없음"/"가장 저렴함")로 대체한다.
    engine = "rule"
    cards = result["journeys"]
    formulaic = [" · ".join(j["reasons"]) for j in cards]
    for j, f in zip(cards, formulaic):
        j["explain"] = f
    if settings.llm_provider == "anthropic" and cards:
        try:
            from .llm.explain import explain_anthropic

            brief = [{
                "durationMin": j["durationMin"], "totalFare": j["fare"]["total"],
                "transfers": j["transfers"], "dep": j["dep"], "arr": j["arr"],
                "legs": [{"mode": l["mode"]} for l in j["legs"]],
            } for j in cards]
            texts = await explain_anthropic(
                brief, fallbacks=formulaic, reasons=[j["reasons"] for j in cards]
            )
            for j, t in zip(cards, texts):
                j["explain"] = t
            engine = "anthropic"
        except Exception:
            pass  # 정형 문구 유지 (FR-8)

    agent = [AgentLine(tag=t, msg=m) for t, m in result["log"]]
    agent.append(AgentLine(tag="EXPLAIN", msg=f"경로 설명문 ({engine})"))
    _emit(body.sessionId, agent)

    return SearchResponse(
        journeys=cards,
        unknownJourneys=result["unknown"],
        excludedSoldOut=result["excluded_sold_out"],
        excludedSources=result["excluded_sources"],
        recombined=result["recombined"],
        hasUnknown=bool(result["unknown"]),
        agent=agent,
    )


# ── FR-9: 좌석 선점·결제 시뮬레이션 ──────────────────
def _to_reservation(r: Dict[str, Any]) -> SimReservation:
    left = max(0, int(r["deadline"] - time.time())) if r["deadline"] else 0
    notices = simulation.notices_for(r["deadline"]) if r["status"] == "SIM_HELD" and r["deadline"] else []
    p = r["passengers"]
    total = p.get("senior", 0) + p.get("adult", 0) + p.get("student", 0)
    reminders = db.notify_list(r["demoId"]) if r["status"] == "DEMO_COMPLETED" else []
    return SimReservation(
        demoId=r["demoId"],
        status=r["status"],
        journey=r["journey"],
        seats=r["seats"],
        passengers={**p, "total": total},
        fare=r["fare"],
        deadlineIso=dt.datetime.fromtimestamp(r["deadline"]).isoformat() if r["deadline"] else None,
        remainingSec=left if r["status"] in ("SIM_HELD", "MOCK_PAYMENT_OPENED") else 0,
        notices=notices,
        reminders=reminders,
    )


@router.post("/sim/hold", response_model=SimReservation)
async def sim_hold(body: SimHoldRequest) -> SimReservation:
    journey = body.journey.model_dump(by_alias=True)
    passengers = (db.input_get(body.sessionId or "") or {}).get("passengers") or {"adult": 1}

    try:
        held = simulation.hold(journey, passengers, body.seatPreference, conflict=body.sim.holdConflict)
    except simulation.SimConflict as e:
        # FR-9 예외 — 프론트는 [다른 길 찾기]로 FR-7 재조합 실행
        _emit(body.sessionId, [AgentLine(tag="SIM", msg="선점 경합 실패 시연 → 재조합 제안")])
        raise HTTPException(status_code=409, detail=str(e))

    fare = journey.get("fare") or fares.compute(journey["legs"], passengers)
    date_iso = (db.input_get(body.sessionId or "") or {}).get("date")
    db.sim_create(held["demoId"], body.sessionId, journey, held["seats"], passengers,
                  fare, date_iso, held["status"], held["deadline"])

    _emit(body.sessionId, [AgentLine(
        tag="SIM", msg=f"좌석 선점 시뮬레이션 완료 · {held['demoId']} · 실제 예약 없음")])
    r = db.sim_get(held["demoId"])
    assert r is not None
    return _to_reservation(r)


@router.post("/sim/{demo_id}/open-payment", response_model=SimReservation)
async def open_payment(demo_id: str) -> SimReservation:
    r = db.sim_get(demo_id)
    if r is None:
        raise HTTPException(status_code=404, detail="시뮬레이션 예약을 찾을 수 없어요")
    if r["status"] != "SIM_HELD":
        raise HTTPException(status_code=409, detail=f"결제 화면을 열 수 없는 상태예요: {r['status']}")
    db.sim_set_status(demo_id, "MOCK_PAYMENT_OPENED")
    return _to_reservation(db.sim_get(demo_id))


@router.post("/sim/{demo_id}/complete", response_model=SimReservation)
async def complete_demo(demo_id: str) -> SimReservation:
    """목업 결제 완료 → DEMO_COMPLETED. 실제 PAID 상태를 만들지 않는다 (FR-9)."""
    r = db.sim_get(demo_id)
    if r is None:
        raise HTTPException(status_code=404, detail="시뮬레이션 예약을 찾을 수 없어요")
    if r["status"] not in ("SIM_HELD", "MOCK_PAYMENT_OPENED"):
        raise HTTPException(status_code=409, detail=f"완료할 수 없는 상태예요: {r['status']}")

    db.sim_set_status(demo_id, "DEMO_COMPLETED")
    # FR-10: 알림 큐 등록 (최소 여정 + 데모 세션 식별자)
    if r["dateIso"] and not db.notify_list(demo_id):
        reminders = notify.build_reminders(r["journey"], r["dateIso"])
        db.notify_add(demo_id, r["sessionId"], reminders)
    _emit(r["sessionId"], [AgentLine(tag="DEMO", msg=f"데모 완료 · {demo_id} · 알림 큐 등록 (실제 결제 아님)")])
    return _to_reservation(db.sim_get(demo_id))


@router.post("/sim/{demo_id}/cancel", response_model=SimReservation)
async def cancel_sim(demo_id: str) -> SimReservation:
    r = db.sim_get(demo_id)
    if r is None:
        raise HTTPException(status_code=404, detail="시뮬레이션 예약을 찾을 수 없어요")
    if r["status"] in simulation.TERMINAL:
        raise HTTPException(status_code=409, detail=f"취소할 수 없는 상태예요: {r['status']}")
    db.sim_set_status(demo_id, "SIM_CANCELLED")
    return _to_reservation(db.sim_get(demo_id))


# ── FR-11: 시뮬레이션 예약 확인 ─────────────────────
@router.get("/sim", response_model=SimReservationList)
async def list_sim(sessionId: Optional[str] = None) -> SimReservationList:
    rows = db.sim_list(sessionId)
    reservations = [_to_reservation(r) for r in rows]
    active = [r for r in reservations if r.status in ("SIM_HELD", "MOCK_PAYMENT_OPENED")]
    agent = [AgentLine(tag="MYSIM", msg=f"진행 중 시뮬레이션 예약 {len(active)}건")] if active else []
    return SimReservationList(reservations=reservations, agent=agent)


@router.get("/sim/{demo_id}", response_model=SimReservation)
async def get_sim(demo_id: str) -> SimReservation:
    r = db.sim_get(demo_id)
    if r is None:
        raise HTTPException(status_code=404, detail="시뮬레이션 예약을 찾을 수 없어요")
    return _to_reservation(r)


# ── FR-10: 이메일 알림 ─────────────────────────────
@router.post("/notify/{demo_id}/demo", response_model=NotifyDemoResponse)
async def notify_demo(
    demo_id: str,
    x_approved_by: Optional[str] = Header(default=None),
) -> NotifyDemoResponse:
    """[알림 시연] — 실제 알림 시각을 기다리지 않고 즉시 1건 전송 (FR-10 시연 지원).

    이메일 발송은 시뮬레이션이 아닌 **실제 외부 부작용**이므로 승인 게이트를 거친다.
    """
    r = db.sim_get(demo_id)
    if r is None:
        raise HTTPException(status_code=404, detail="시뮬레이션 예약을 찾을 수 없어요")
    try:
        gate.check("notify.demo", gate.SIDE_EFFECT, r["sessionId"], approved_by=x_approved_by)
    except gate.ApprovalRequired as e:
        raise HTTPException(status_code=403, detail=str(e))

    pending = db.notify_list(demo_id)
    if not pending:
        raise HTTPException(status_code=409, detail="등록된 알림이 없어요 (데모 완료 후 사용하세요)")

    n = next((x for x in pending if not x["sent"]), pending[0])
    result = notify.send(n["subject"], n["body"])
    cleaned = False
    if result["sent"]:
        db.notify_mark_sent(n["id"])
        cleaned = db.notify_cleanup(demo_id)   # 마지막 알림 전송 후 데이터 삭제 (FR-10)

    agent = [AgentLine(tag="MAIL", msg=f"알림 시연 전송 → {result['to']} · "
                                       f"{'성공' if result['sent'] else '실패: ' + (result['error'] or '')}"
                                       f"{' · 알림 데이터 삭제(전송 완료)' if cleaned else ''}")]
    _emit(r["sessionId"], agent)
    return NotifyDemoResponse(
        sent=result["sent"], to=result["to"], subject=n["subject"],
        preview=n["body"], error=result["error"], agent=agent,
    )
