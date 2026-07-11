"""REST + SSE 엔드포인트 — Express(server/) 계약과 동일 + 오케스트레이터 확장.

기존 React 클라이언트는 VITE_API_URL만 이 서버(:8000)로 바꾸면 그대로 동작한다.
Next.js 클라이언트는 동일 REST + GET /api/stream/{session_id} (SSE)를 사용한다.
"""
import asyncio
import datetime as dt
import json
import random
import uuid
from typing import AsyncGenerator, List, Optional

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import StreamingResponse

from . import db
from .config import settings
from .core import gate, scoring
from .events import broker
from .llm.anthropic_parser import parse_anthropic
from .llm.ollama_parser import parse_ollama
from .llm.rule_parser import parse_rule
from .schemas import (
    AgentLine,
    BookingRequest,
    BookingStep,
    CreateBookingResponse,
    ParseRequest,
    ParseResponse,
    PayResponse,
    RouteOption,
    SearchRequest,
    SearchResponse,
    StandbyCheckResponse,
    Ticket,
    TravelSuggestResponse,
    TripParams,
)
from .tools.base import run_tool
from .tools.kskill import run_skill
from .tools.trains_mock import generate_routes

router = APIRouter()

BOOK_STEPS = [
    BookingStep(title="예매 페이지 접속", detail="WebView로 예매 사이트 로드", ms=1300),
    BookingStep(title="열차·좌석 선택", detail="07호차 11A (창측) — Vision으로 화면 요소 인식", ms=1700),
    BookingStep(title="승객 정보 입력", detail="저장된 프로필 자동 입력 (성인 1명)", ms=1400),
    BookingStep(title="결제 페이지 진입", detail="여기까지 완료 후 자동화를 멈춥니다", ms=1200),
]

SEAT = "07호차 11A (창측)"


def fmt_time(minutes: int) -> str:
    m = minutes % 1440
    return f"{m // 60:02d}:{m % 60:02d}"


def emit(session_id: Optional[str], lines: List[AgentLine], event_type: str = "agent") -> None:
    """에이전트 로그를 SSE 구독자에게 push (응답 JSON과 이중 채널)."""
    for line in lines:
        broker.publish(session_id or "public", {"type": event_type, **line.model_dump()})


# ── NLU: 자연어 → 필수 파라미터 ────────────────────
@router.post("/nlu/parse", response_model=ParseResponse)
async def nlu_parse(body: ParseRequest) -> ParseResponse:
    text = body.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="text가 필요합니다.")
    today = dt.date.today()
    agent: List[AgentLine] = []
    engine = settings.llm_provider

    try:
        if engine == "anthropic":
            got = await parse_anthropic(text, today)
        elif engine == "ollama":
            got = await parse_ollama(text, today)
        else:
            engine = "rule"
            got = parse_rule(text, today)
    except Exception as e:  # LLM 실패 → 규칙 기반 폴백 (조용히 죽지 않고 로그에 드러낸다)
        agent.append(AgentLine(tag="NLU", msg=f"{engine} 파서 실패 → 규칙 기반 폴백 ({type(e).__name__})"))
        engine = f"{engine}→rule"
        got = parse_rule(text, today)

    found = []
    if got.get("origin"):
        found.append(f"출발지={got['origin']}")
    if got.get("dest"):
        found.append(f"도착지={got['dest']}")
    if got.get("date"):
        found.append(f"날짜={got['date']['md']}")
    if got.get("time"):
        found.append(f"도착시각={got['time']['label']}")
    if found:
        agent.append(AgentLine(tag="NLU", msg=f"({engine}) 파라미터 추출 → {', '.join(found)}"))

    emit(body.sessionId, agent)
    return ParseResponse(got=TripParams(**got), agent=agent)


# ── 경로 검색: 도구 어댑터 → scoring.py 재랭킹 ──────
@router.post("/routes/search", response_model=SearchResponse)
async def routes_search(body: SearchRequest) -> SearchResponse:
    gate.check("routes.search", gate.READ, body.sessionId)

    result = await run_tool(
        "routes.search",
        mock_fn=lambda: generate_routes(body.origin, body.dest, body.arriveBy),
        # [k-skill 통합 지점] live 모드에서 도구 팀원의 스킬을 호출한다.
        live_fn=lambda: run_skill(
            "route-search",
            {"origin": body.origin, "dest": body.dest, "arriveBy": body.arriveBy, "dateIso": body.dateIso},
        ),
        cache_key=f"routes:{body.origin}:{body.dest}:{body.arriveBy}:{body.dateIso}",
    )

    routes = scoring.rerank(result.data, body.arriveBy)

    # 시연 시나리오: 최적 경로 매진 → 취소표 자동화 흐름 (mock일 때만)
    if result.source == "mock" and routes:
        routes[0]["soldOut"] = True
        if len(routes) > 3:
            routes[3]["soldOut"] = True
        routes[0]["reason"] = (
            f"희망 도착시각 대비 여유 {body.arriveBy - routes[0]['arr']}분, 최단 소요라 1위예요. "
            "매진이지만 취소표 확보 확률이 높아요."
        )

    agent = [
        AgentLine(tag="TOOL", msg=f"routes.search 실행 (source={result.source}, mode={settings.tool_mode})"),
        AgentLine(tag="ROUTE", msg=f"경로 후보 {len(routes)}건 산출 ({body.origin} → {body.dest})"),
    ]
    for r in routes:
        agent.append(AgentLine(tag="SCORE", msg=f"{r['no']} 적합도 {r['score']}점{' · 매진' if r['soldOut'] else ''}"))
    if routes and routes[0]["soldOut"]:
        agent.append(AgentLine(tag="AI", msg="1위 경로 매진 감지 → 취소표 자동 조회 제안"))

    emit(body.sessionId, agent)
    return SearchResponse(routes=[RouteOption(**r) for r in routes], agent=agent)


# ── 취소표 좌석 조회 (SQLite 세션·TTL) ─────────────
@router.get("/standby/{search_id}/check", response_model=StandbyCheckResponse)
async def standby_check(search_id: str, session_id: Optional[str] = None) -> StandbyCheckResponse:
    attempt, available = db.standby_check(search_id)
    if available:
        emit(session_id, [AgentLine(tag="POLL", msg=f"시도 #{attempt} → 잔여석 1석 발견 ✓")], event_type="standby")
    return StandbyCheckResponse(attempt=attempt, available=available, remaining=1 if available else 0)


# ── 자동 예매 (side_effect — 승인 게이트 통과 필요) ──
@router.post("/bookings", response_model=CreateBookingResponse)
async def create_booking(
    body: BookingRequest,
    x_approved_by: Optional[str] = Header(default=None),
) -> CreateBookingResponse:
    try:
        gate.check("booking.create", gate.SIDE_EFFECT, body.sessionId, approved_by=x_approved_by)
    except gate.ApprovalRequired as e:
        raise HTTPException(status_code=403, detail=str(e))

    if not (body.params.origin and body.params.dest and body.params.date and body.params.time):
        raise HTTPException(status_code=400, detail="params(origin, dest, date, time)가 필요합니다.")

    booking_id = f"bk_{uuid.uuid4().hex[:8]}"
    db.booking_create(booking_id, body.route.model_dump(), body.params.model_dump())

    agent = [AgentLine(tag="AUTO", msg=f"자동 예매 시작: {body.route.no} ({fmt_time(body.route.dep)} 출발)")]
    emit(body.sessionId, agent)
    return CreateBookingResponse(bookingId=booking_id, steps=BOOK_STEPS, seat=SEAT, agent=agent)


# ── 결제 확정 (side_effect — 사용자 제어 단계) ───────
@router.post("/bookings/{booking_id}/pay", response_model=PayResponse)
async def pay_booking(
    booking_id: str,
    x_approved_by: Optional[str] = Header(default=None),
    session_id: Optional[str] = None,
) -> PayResponse:
    try:
        gate.check("booking.pay", gate.SIDE_EFFECT, session_id, approved_by=x_approved_by)
    except gate.ApprovalRequired as e:
        raise HTTPException(status_code=403, detail=str(e))

    b = db.booking_get(booking_id)
    if b is None:
        raise HTTPException(status_code=404, detail="예매를 찾을 수 없습니다.")
    db.booking_mark_paid(booking_id)

    route, params = b["route"], b["params"]
    ticket = Ticket(
        mode=route["mode"],
        no=route["no"],
        origin=params["origin"],
        dest=params["dest"],
        depLabel=fmt_time(route["dep"]),
        arrLabel=fmt_time(route["arr"]),
        dateMd=params["date"]["md"],
        seat="07호차 11A",
        price=route["price"],
    )
    agent = [
        AgentLine(tag="USER", msg="사용자 결제 승인 → 예매 확정"),
        AgentLine(tag="DONE", msg=f"예매 완료 · {route['no']} · {route['price']:,}원"),
    ]
    emit(session_id, agent)
    return PayResponse(ticket=ticket, agent=agent)


# ── 도착지 숙소·투어 추천 (계약 유지용 — Express myrealtrip.js가 원본) ──
@router.get("/travel/suggest", response_model=TravelSuggestResponse)
async def travel_suggest(dest: str, checkIn: str) -> TravelSuggestResponse:
    # FastAPI 쪽은 형태만 유지한다 (빈 결과 → 프론트는 섹션을 조용히 생략).
    # 실연동은 Express server/src/services/myrealtrip.js 참고 — 필요 시 여기로 포팅.
    agent = [AgentLine(tag="MRT", msg=f"여행 추천 mock — {dest} (FastAPI에는 미연동, Express 참고)")]
    return TravelSuggestResponse(stays=[], tnas=[], agent=agent)


# ── SSE: 에이전트 이벤트 스트림 ─────────────────────
@router.get("/stream/{session_id}")
async def stream(session_id: str) -> StreamingResponse:
    async def gen() -> AsyncGenerator[str, None]:
        q = broker.subscribe(session_id)
        try:
            yield "retry: 3000\n\n"
            while True:
                try:
                    ev = await asyncio.wait_for(q.get(), timeout=15.0)
                    yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
                except asyncio.TimeoutError:
                    yield ": ping\n\n"  # keep-alive
        finally:
            broker.unsubscribe(session_id, q)

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
