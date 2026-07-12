"""기능 명세서 VER3 계약 (/api/v3/*).

VER3 핵심 원칙:
1. 실제 조회값과 시뮬레이션 값을 같은 상태명으로 저장하지 않는다 (§5-1).
2. 모든 경로에 운행정보·좌석·예약 각각의 데이터 모드를 표시한다 (§5-2).
3. UNKNOWN(좌석 확인 불가)은 매진으로 변환하지 않는다 (§5-4).
4. 실제 예약·결제 함수는 백엔드에서도 비활성화한다 (§5-6).
"""
from enum import Enum
from typing import List, Literal, Optional

from pydantic import BaseModel, Field

from .schemas import AgentLine


# ── 데이터 모드 (§0 데이터 표시 기준) ────────────────
class DataMode(str, Enum):
    LIVE = "LIVE"                  # 실제 외부 API 조회
    SIMULATED = "SIMULATED"        # 목업 데이터/처리
    UNAVAILABLE = "UNAVAILABLE"    # 조회 실패 — 확인 불가


# ── 좌석 상태 (FR-6) ──────────────────────────────
class SeatStatus(str, Enum):
    LIVE_AVAILABLE = "LIVE_AVAILABLE"            # 실시간 좌석 있음
    LIVE_SOLD_OUT = "LIVE_SOLD_OUT"              # 실시간 매진
    UNKNOWN = "UNKNOWN"                          # 조회 실패 — 매진으로 처리 금지
    SIMULATED_AVAILABLE = "SIMULATED_AVAILABLE"  # 시뮬레이션상 좌석 있음
    SIMULATED_SOLD_OUT = "SIMULATED_SOLD_OUT"    # 시뮬레이션상 매진


SOLD_OUT_STATUSES = {SeatStatus.LIVE_SOLD_OUT, SeatStatus.SIMULATED_SOLD_OUT}
AVAILABLE_STATUSES = {SeatStatus.LIVE_AVAILABLE, SeatStatus.SIMULATED_AVAILABLE}


# ── 시뮬레이션 예약 상태 (FR-9) ────────────────────
class SimStatus(str, Enum):
    SIM_HOLDING = "SIM_HOLDING"                    # 선점 시도 중
    SIM_HELD = "SIM_HELD"                          # 선점 완료 (시뮬레이션)
    MOCK_PAYMENT_OPENED = "MOCK_PAYMENT_OPENED"    # 목업 결제 화면 진입
    DEMO_COMPLETED = "DEMO_COMPLETED"              # 데모 완료 — 실제 PAID 아님
    SIM_EXPIRED = "SIM_EXPIRED"
    SIM_CANCELLED = "SIM_CANCELLED"
    SIM_FAILED = "SIM_FAILED"                      # 경합 실패 등


class Provenance(BaseModel):
    """경로별 데이터 출처 (FR-5/8, §5-2) — 카드에 그대로 표시한다."""
    schedule: DataMode          # 운행정보·요금
    seat: DataMode              # 좌석 상태
    booking: DataMode = DataMode.SIMULATED  # 예약 — 대회 버전은 항상 시뮬레이션
    checkedAt: Optional[str] = None  # 조회 시각 ISO (예: "오후 2시 10분 확인")
    label: str = ""             # 화면 표시 문구 (서버가 생성해 문구 일관성 유지)


# ── 장소 (FR-2) ───────────────────────────────────
PlaceType = Literal["station", "terminal"]


class Place(BaseModel):
    name: str                   # "대전"
    type: PlaceType             # station | terminal
    canonicalId: str            # "SEOUL", "BUSAN" — 내부 정규화 키
    region: Optional[str] = None  # 동명 시설 구분용 ("대전광역시")
    display: str = ""           # 자동완성 표시용 ("대전역 · 대전광역시")


# ── 승객 구성 (FR-1 ⑤, FR-2) ───────────────────────
class PassengerCounts(BaseModel):
    # 음수 인원이 합계 검증을 통과하는 것을 스키마 수준에서 차단 (senior=-1, adult=2 → total=1)
    senior: int = Field(0, ge=0, le=9)    # 노약자 = 만 65세 이상
    adult: int = Field(0, ge=0, le=9)
    student: int = Field(0, ge=0, le=9)


class PassengerCountsOut(PassengerCounts):
    total: int = 0     # 세 유형의 합 (서버가 계산해 내려준다)


class FareBreakdown(BaseModel):
    """승객 유형별 요금 (FR-5)."""
    seniorEach: int = 0
    adultEach: int = 0
    studentEach: int = 0
    seniorTotal: int = 0
    adultTotal: int = 0
    studentTotal: int = 0
    total: int = 0
    studentDiscountApplied: bool = False   # false면 "학생 할인 미적용" 표시 (§0)
    notes: List[str] = []


class TripInput(BaseModel):
    """FR-2 확정 입력값."""
    departure: Optional[Place] = None
    arrival: Optional[Place] = None
    date: Optional[str] = None          # YYYY-MM-DD
    arrivalTime: Optional[int] = Field(None, ge=0, le=1435)  # 도착 마감 시각 (자정 기준 분, 5분 단위)
    passengers: PassengerCounts = PassengerCounts()


# ── 여정 ──────────────────────────────────────────
class Leg(BaseModel):
    mode: str                   # KTX | ITX-새마을 | SRT | 고속버스 | 시외버스
    no: str
    from_: str = Field(alias="from")   # canonicalId (내부 키)
    to: str                            # canonicalId
    fromName: str = ""          # 표시용 한글 이름 — 화면·이메일은 이 값을 쓴다
    toName: str = ""
    dep: int
    arr: int
    fare: int                   # 성인 1인 기준 정가
    seatStatus: SeatStatus
    seatMode: DataMode          # 이 구간 좌석 상태의 출처

    model_config = {"populate_by_name": True}


class Journey(BaseModel):
    id: str
    legs: List[Leg]
    dep: int
    arr: int
    durationMin: int
    transfers: int
    transferWaitMin: Optional[int] = None
    transferAt: Optional[str] = None     # 환승 장소 (FR-8 카드)
    fare: FareBreakdown
    seatStatus: SeatStatus               # 여정 전체 (가장 나쁜 구간 기준)
    provenance: Provenance
    reasons: List[str] = []              # 추천 근거 키 ("가장 빨라요", "갈아타지 않아요", "가장 저렴해요")
    explain: Optional[str] = None        # LLM 비교 설명문 (FR-8)
    onTime: bool = True                  # 도착 마감 시각 이내 여부


# ── FR-1/2: 단계형 입력 지원 ───────────────────────
class PlaceSearchResponse(BaseModel):
    places: List[Place]


class ValidateStepRequest(BaseModel):
    sessionId: str
    step: Literal["departure", "arrival", "date", "arrivalTime", "passengers"]
    input: TripInput


class ValidateStepResponse(BaseModel):
    ok: bool
    message: str = ""           # 비활성 안내 문구 ("출발지를 선택하면 다음으로 갈 수 있어요")
    input: TripInput            # 서버가 보관 중인 최신 입력값


class SummaryResponse(BaseModel):
    """FR-4 확인 요약 — 문구는 서버가 생성해 표현 일관성을 유지한다."""
    lines: List[str]            # ["대전 → 부산", "7월 15일 수요일", "낮 12시까지 도착", ...]
    input: TripInput
    ready: bool


# ── FR-5/6/7/8: 검색 ──────────────────────────────
class SimOptions(BaseModel):
    """시연 제어 (§4 시뮬레이션 목록)."""
    soldOutAll: bool = False        # 직결 전 후보 매진 → FR-7 재조합 시연
    failSources: List[str] = []     # 운행정보 API 장애 시연 (FR-5 예외)
    seatLookupFail: bool = False    # 좌석 조회 실패 → UNKNOWN 시연 (FR-6)
    holdConflict: bool = False      # 선점 경합 실패 시연 (FR-9)


class SearchRequest(BaseModel):
    sessionId: Optional[str] = None
    input: Optional[TripInput] = None       # 생략 시 세션 입력값 사용
    useSimulatedForUnknown: bool = False    # [시뮬레이션으로 보기] (FR-6)
    onlyConfirmed: bool = False             # [확인된 결과만 보기] (FR-6)
    sim: SimOptions = SimOptions()


class SearchResponse(BaseModel):
    journeys: List[Journey]                 # 추천 카드 (최대 3)
    unknownJourneys: List[Journey] = []     # "좌석을 확인하지 못한 교통편" 영역 (FR-6)
    excludedSoldOut: int = 0                # 매진 제외 건수
    excludedSources: List[str] = []         # 운행정보 조회 실패 수단 (FR-5 예외)
    recombined: bool = False                # FR-7 재조합 여부
    hasUnknown: bool = False                # UNKNOWN 안내 배너 표시 여부
    agent: List[AgentLine] = []


# ── FR-9: 좌석 선택·선점·결제 시뮬레이션 ─────────────
SeatPreference = Literal["any", "window", "aisle"]


class SimHoldRequest(BaseModel):
    sessionId: Optional[str] = None
    journey: Journey
    seatPreference: SeatPreference = "any"
    sim: SimOptions = SimOptions()


class SimSeat(BaseModel):
    label: str                  # "7호차 11A (시뮬레이션 좌석)"
    preference: SeatPreference
    adjacent: bool = True       # 여러 명이면 인접 배정 여부


class SimReservation(BaseModel):
    """실제 예약이 아님 — demoId는 사업자 예약번호가 아니다 (FR-11)."""
    demoId: str                 # "DEMO-3F9C1A" — 데모 식별번호
    status: SimStatus
    journey: Journey
    seats: List[SimSeat]
    passengers: PassengerCountsOut
    fare: FareBreakdown
    deadlineIso: Optional[str] = None
    remainingSec: int = 0
    notices: List[str] = []              # 선점 성공 문구 (FR-9)
    simulationBadge: str = "시뮬레이션"   # §5-3 — 글자 배지 필수
    reminders: List["Reminder"] = []     # DEMO_COMPLETED일 때 (FR-10)


class SimReservationList(BaseModel):
    reservations: List[SimReservation]
    agent: List[AgentLine] = []


# ── FR-10: 탑승 안내·이메일 ────────────────────────
class Reminder(BaseModel):
    atIso: str
    label: str                  # "출발 전날 오후 6시", "출발 2시간 전", "즉시 (출발 임박)"
    subject: str                # 메일 제목 (경진대회 시연용 명시)
    body: str
    sent: bool = False


class NotifyDemoResponse(BaseModel):
    """[알림 시연] — 심사 시 즉시 전송 확인용."""
    sent: bool
    to: str                     # 마스킹된 데모 이메일
    subject: str
    preview: str                # 본문 미리보기 (전송 실패 시에도 내용 확인 가능)
    error: Optional[str] = None
    agent: List[AgentLine] = []


SimReservation.model_rebuild()
