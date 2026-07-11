"""API 계약(Pydantic 모델) — client/src/types.ts 와 1:1 대응.

필드명은 프론트(TypeScript) 쪽 camelCase를 그대로 따른다.
이 파일이 곧 팀 간 인터페이스 명세이며, /docs(OpenAPI)에 자동 노출된다.
"""
from typing import List, Optional

from pydantic import BaseModel


class TripDate(BaseModel):
    label: str  # 오늘/내일/모레 또는 "7월 8일"
    md: str     # "7월 8일"
    iso: str    # "2026-07-08"


class TripTime(BaseModel):
    min: int    # 자정 기준 분
    label: str  # "14:00"


class TripParams(BaseModel):
    origin: Optional[str] = None
    dest: Optional[str] = None
    date: Optional[TripDate] = None
    time: Optional[TripTime] = None


class AgentLine(BaseModel):
    tag: str
    msg: str


class RouteOption(BaseModel):
    id: str
    mode: str
    cls: str = ""
    no: str
    dep: int
    arr: int
    dur: int
    price: int
    soldOut: bool = False
    score: int = 0
    reason: Optional[str] = None


class BookingStep(BaseModel):
    title: str
    detail: str
    ms: int


class Ticket(BaseModel):
    mode: str
    no: str
    origin: str
    dest: str
    depLabel: str
    arrLabel: str
    dateMd: str
    seat: str
    price: int


# ── 요청 ──────────────────────────────────────────
class ParseRequest(BaseModel):
    text: str
    sessionId: Optional[str] = None


class SearchRequest(BaseModel):
    origin: str
    dest: str
    arriveBy: int
    dateIso: Optional[str] = None
    sessionId: Optional[str] = None


class BookingRequest(BaseModel):
    route: RouteOption
    params: TripParams
    sessionId: Optional[str] = None


# ── 응답 ──────────────────────────────────────────
class ParseResponse(BaseModel):
    got: TripParams
    agent: List[AgentLine]


class SearchResponse(BaseModel):
    routes: List[RouteOption]
    agent: List[AgentLine]


class StandbyCheckResponse(BaseModel):
    attempt: int
    available: bool
    remaining: int


class CreateBookingResponse(BaseModel):
    bookingId: str
    steps: List[BookingStep]
    seat: str
    agent: List[AgentLine]


class PayResponse(BaseModel):
    ticket: Ticket
    agent: List[AgentLine]


class TravelSuggestResponse(BaseModel):
    stays: List[dict]
    tnas: List[dict]
    agent: List[AgentLine]
