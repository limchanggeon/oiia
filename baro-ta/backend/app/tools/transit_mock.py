"""전 수단(KTX·SRT·고속버스·시외버스) mock 어댑터 — 시뮬레이션 모드의 골든패스.

어댑터 계약 (좌석/예약 어댑터 담당 팀원 통합 지점):
  search(source, origin, dest, window_start) -> List[leg dict]   # 시간표+잔여석 (FR-6/7)
  reserve(journey, passengers)               -> {reserveNo, fare, deadlineTs}  # 선점 (FR-10)

live 전환 시 korail2/SRTrain/KOBUS/티머니 결과를 이 형식으로 정규화해 반환하면 된다.
- 열차(KTX·SRT)만 reservable=True — 버스는 예약 시스템이 없어 잔여석 확인만 (명세 5장).
"""
import random
import time
import uuid
from typing import Any, Dict, List

from .trains_mock import DIST_MIN

SOURCES = ["KTX", "SRT", "고속버스", "시외버스"]

_FACTORS = {"KTX": 1.0, "SRT": 0.96, "고속버스": 1.85, "시외버스": 2.05}
_FARES = {"KTX": 380, "SRT": 360, "고속버스": 210, "시외버스": 180}  # ×100원
_RESERVABLE = {"KTX": True, "SRT": True, "고속버스": False, "시외버스": False}

HOLD_DEADLINE_MIN = 20  # mock 결제 기한 — 실연동 시 API가 반환한 값 사용 (FR-10)


def leg_duration(origin: str, dest: str, mode: str) -> int:
    if origin == "서울":
        base = DIST_MIN.get(dest, 120)
    elif dest == "서울":
        base = DIST_MIN.get(origin, 120)
    else:
        base = max(40, abs(DIST_MIN.get(dest, 120) - DIST_MIN.get(origin, 60)))
    return round(base * _FACTORS[mode] / 5) * 5


def search(source: str, origin: str, dest: str, window_start: int) -> List[Dict[str, Any]]:
    """시간대 창(window_start~) 내 출발 편 2~3개. soldOut 판정 포함 (FR-6+7)."""
    legs = []
    for i, offset in enumerate((20, 80, 150)):
        dep = window_start + offset
        dur = leg_duration(origin, dest, source)
        no = (
            f"{source} {random.randint(11, 89)}회"
            if source.endswith("버스")
            else f"{source} {random.randint(101, 899)}"
        )
        legs.append(
            {
                "mode": source,
                "no": no,
                "from": origin,
                "to": dest,
                "dep": dep,
                "arr": dep + dur,
                "fare": _FARES[source] * 100 + random.randint(0, 9) * 100,
                "reservable": _RESERVABLE[source],
                "soldOut": False,
            }
        )
    return legs


class HoldConflict(RuntimeError):
    """선점 경합 매진 (FR-10 예외) — '방금 자리가 나갔어요'."""


def reserve(journey: Dict[str, Any], passengers: int, conflict: bool = False) -> Dict[str, Any]:
    """열차 구간 선점 mock — 예약번호·운임·결제 기한 반환.

    [실연동 교체 지점] korail2/SRTrain reserve 호출로 교체.
    버스 구간은 예약 시스템이 없으므로 선점 대상에서 제외된다 (호출 측에서 안내).
    """
    if conflict:
        raise HoldConflict("방금 자리가 나갔어요")
    reservable_legs = [l for l in journey["legs"] if l["reservable"]]
    if not reservable_legs:
        return {"reserveNo": None, "fare": journey["totalFare"] * passengers, "deadlineTs": None}
    return {
        "reserveNo": f"R{uuid.uuid4().hex[:8].upper()}",
        "fare": journey["totalFare"] * passengers,
        "deadlineTs": time.time() + HOLD_DEADLINE_MIN * 60,
    }
