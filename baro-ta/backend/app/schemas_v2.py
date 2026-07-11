"""기능 명세서 v2 계약 (FR-2~FR-15) — /api/v2/* 전용 Pydantic 모델.

기존 데모 계약(schemas.py)은 그대로 두고, 명세서 기반 계약을 여기에 둔다.
프론트(Next.js 시니어 UI) 팀원은 이 파일 + /docs 만 보면 된다.
"""
from typing import List, Literal, Optional

from pydantic import BaseModel, Field

from .schemas import AgentLine, TripDate

TimeOfDay = Literal["아침", "낮", "저녁", "밤"]
SlotName = Literal["departure", "arrival", "date", "time_of_day", "passengers"]


# ── FR-2: 슬롯 ────────────────────────────────────
class Slots(BaseModel):
    departure: Optional[str] = None   # 출발지 (필수)
    arrival: Optional[str] = None     # 도착지 (필수)
    date: Optional[TripDate] = None   # 날짜 (필수)
    timeOfDay: Optional[TimeOfDay] = None  # 시간대 — 기본값 '아침' (FR-2)
    passengers: Optional[int] = None       # 인원 — 기본값 1 (어른 1명)


# ── FR-3: 선택형 되묻기 ───────────────────────────
class AskOption(BaseModel):
    label: str        # 버튼 라벨 — 명사형/명령형 (예: "아침 출발")
    slot_value: str   # 선택 시 다음 turn의 text로 그대로 전송


class AskNext(BaseModel):
    type: Literal["ask"] = "ask"
    question: str
    options: List[AskOption]  # 2~3개
    target_slot: SlotName


class ConfirmNext(BaseModel):
    type: Literal["confirm"] = "confirm"
    summary: str  # FR-4: "7월 15일 화요일 아침 / 대전 → 부산 / 어른 1명"


class DialogTurnRequest(BaseModel):
    sessionId: str
    text: str
    location: Optional[str] = None  # 위치 정보 → 출발지 기본값 (FR-2)


class DialogTurnResponse(BaseModel):
    slots: Slots
    missing: List[SlotName]
    next: dict  # AskNext | ConfirmNext (discriminated by "type")
    askCount: int  # FR-3 토의사항(3회 초과 예외 처리)을 위한 카운트 — 프론트가 판단
    agent: List[AgentLine]


# ── FR-6/7/8: 통합 검색·여정 ───────────────────────
class Leg(BaseModel):
    mode: str                 # KTX | SRT | 고속버스 | 시외버스
    no: str
    from_: str = Field(alias="from")
    to: str
    dep: int                  # 자정 기준 분
    arr: int
    fare: int
    reservable: bool          # 열차만 온라인 선점 가능 (FR-10)

    model_config = {"populate_by_name": True}


class Journey(BaseModel):
    id: str
    legs: List[Leg]
    dep: int
    arr: int
    durationMin: int
    totalFare: int
    transfers: int            # 갈아타기 수 (≤1 — FR-8 제약)
    transferWaitMin: Optional[int] = None  # 환승 대기 (≥20 — FR-8 제약)
    reservable: bool          # 모든 구간 온라인 선점 가능 여부
    explain: Optional[str] = None  # 경로 설명문 (LLM 또는 결정적 생성)


class SimOptions(BaseModel):
    """시뮬레이션 모드 (시스템 구성 '데모용 매진·선점·결제 목업')."""
    soldOutAll: bool = False          # 직결 전 후보 매진 → FR-8 재조합 시연
    failSources: List[str] = []       # 특정 수단 API 장애 시연 (FR-6 예외)
    holdConflict: bool = False        # 선점 경합 매진 시연 (FR-10 예외)


class JourneySearchRequest(BaseModel):
    sessionId: Optional[str] = None
    slots: Optional[Slots] = None     # 생략 시 세션에 저장된 슬롯 사용
    sim: SimOptions = SimOptions()


class JourneySearchResponse(BaseModel):
    journeys: List[Journey]           # 예약 가능한 경로만, 최대 3개 (FR-9)
    excludedSources: List[str]        # 장애로 제외된 수단 → "일부 교통편은 확인하지 못했어요"
    recombined: bool                  # FR-8 재조합 여정 포함 여부
    agent: List[AgentLine]


# ── FR-10/15: 좌석 선점·내 예매 ────────────────────
class HoldCreateRequest(BaseModel):
    sessionId: Optional[str] = None
    journey: Journey
    passengers: int = 1
    dateIso: Optional[str] = None  # 여정 날짜 — FR-13 탑승 안내 계산에 사용
    sim: SimOptions = SimOptions()


class UnreservableLeg(BaseModel):
    mode: str
    notice: str


class Reminder(BaseModel):
    """FR-13 탑승 안내 — 알림 시각·문구 (발송 채널은 토의사항, 데모는 화면 안내)."""
    atIso: str
    label: str
    message: str


class HoldInfo(BaseModel):
    holdId: str
    status: Literal["held", "paid", "cancelled", "expired"]
    reserveNo: Optional[str] = None
    fare: int
    deadlineIso: Optional[str] = None
    remainingSec: int
    journey: Journey
    passengers: int
    notices: List[str]                 # FR-10 선점 성공 문구 (서버가 제공해 문구 일관성 유지)
    unreservableLegs: List[UnreservableLeg] = []
    dateIso: Optional[str] = None
    reminders: List[Reminder] = []     # FR-13 — paid 상태일 때 채워짐


class HoldListResponse(BaseModel):
    holds: List[HoldInfo]
    agent: List[AgentLine]
