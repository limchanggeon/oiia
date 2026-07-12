"""예약·결제 시뮬레이션 엔진 (FR-9) — 실제 사업자 API를 호출하지 않는다.

VER3 §5-6: 실제 예약·결제 함수는 UI에서만 숨기지 않고 백엔드에서도 비활성화한다.
→ 실제 예약 진입점(tools/seats.reserve)은 항상 예외를 던지며, 예약은 이 모듈의
  목업 처리만 존재한다. demoId는 사업자 예약번호가 아니다 (FR-11).

상태: SIM_HOLDING → SIM_HELD → MOCK_PAYMENT_OPENED → DEMO_COMPLETED
                              ↘ SIM_CANCELLED / SIM_EXPIRED / SIM_FAILED
"""
import random
import time
import uuid
from typing import Any, Dict, List

HOLD_MINUTES = 15  # 시뮬레이션 결제 기한

NOTICES = [
    "좌석 선점 시뮬레이션이 완료됐어요.",
    "실제 예약이나 결제는 이루어지지 않았어요.",
]

TERMINAL = {"DEMO_COMPLETED", "SIM_EXPIRED", "SIM_CANCELLED", "SIM_FAILED"}


class SimConflict(RuntimeError):
    """시뮬레이션 경합 실패 (FR-9 예외) — '방금 자리가 나간 상황을 시연하고 있어요'."""


def new_demo_id() -> str:
    return "DEMO-" + uuid.uuid4().hex[:6].upper()


def assign_seats(journey: Dict[str, Any], total_passengers: int, preference: str) -> List[Dict[str, Any]]:
    """시뮬레이션 좌석 자동 배정 (FR-9).

    실제 열차 좌석 번호가 아님을 라벨에 명시한다. 여러 명이면 인접 좌석 우선.
    """
    rnd = random.Random(journey["id"])
    car = rnd.randint(3, 9)
    start = rnd.randint(1, 12)
    col_by_pref = {"window": "A", "aisle": "C", "any": rnd.choice(["A", "B", "C"])}
    col = col_by_pref.get(preference, "A")
    seats = []
    for i in range(max(1, total_passengers)):
        seats.append({
            "label": f"{car}호차 {start + i}{col} (시뮬레이션 좌석)",
            "preference": preference,
            "adjacent": total_passengers > 1,
        })
    return seats


def hold(journey: Dict[str, Any], passengers: Dict[str, int], preference: str,
         conflict: bool = False) -> Dict[str, Any]:
    """좌석 선점 시뮬레이션. conflict=True면 경합 실패를 시연한다."""
    if conflict:
        raise SimConflict("방금 자리가 나간 상황을 시연하고 있어요")

    total = passengers.get("senior", 0) + passengers.get("adult", 0) + passengers.get("student", 0)
    deadline = time.time() + HOLD_MINUTES * 60
    return {
        "demoId": new_demo_id(),
        "status": "SIM_HELD",
        "seats": assign_seats(journey, total, preference),
        "deadline": deadline,
    }


def notices_for(deadline_ts: float) -> List[str]:
    """선점 성공 문구 — 절대 시각 + 남은 시간 (FR-9)."""
    left = max(0, int(deadline_ts - time.time()))
    t = time.localtime(deadline_ts)
    h, mi = t.tm_hour, t.tm_min
    ampm = "오전" if h < 12 else "오후"
    h12 = h if 1 <= h <= 12 else (12 if h % 12 == 0 else h % 12)
    return NOTICES + [f"{ampm} {h12}시 {mi:02d}분까지 · {left // 60}분 남음"]
