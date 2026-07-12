"""운행정보·요금 어댑터 (FR-5) — TAGO / ODsay.

대회 버전: 운행정보·요금은 **실제 외부 API**를 쓴다 (§4). 지금은 mock이 골든패스이며,
TAGO 키가 준비되면 fetch_live()만 채우면 된다 — 반환 형식(정규화 leg)은 동일하다.

개별 수단 API 장애는 예외로 올리고, 호출 측(오케스트레이터)이
"일부 교통편은 확인하지 못했어요"로 흡수한다 (FR-5 예외).
"""
import random
import time
from typing import Any, Dict, List

from ..config import settings

SOURCES = ["KTX", "ITX-새마을", "SRT", "고속버스", "시외버스"]

# 서울 기준 대략 소요(분) — 정규화 키(canonicalId) 기준
_BASE_MIN = {
    "BUSAN": 155, "DAEJEON": 62, "DONGDAEGU": 105, "GWANGJU_SONGJEONG": 110,
    "MOKPO": 145, "OSONG": 48, "CHEONAN_ASAN": 38, "IKSAN": 82, "JEONJU": 100,
    "GANGNEUNG": 118, "POHANG": 140, "ULSAN": 128, "YEOSU": 180,
    "SEOUL": 0, "YONGSAN": 0, "SUSEO": 0, "SEOUL_EXPRESS": 0,
    "DAEJEON_TERMINAL": 62, "BUSAN_TERMINAL": 165,
}

_FACTOR = {"KTX": 1.0, "ITX-새마을": 1.55, "SRT": 0.96, "고속버스": 1.85, "시외버스": 2.05}
_FARE = {"KTX": 38000, "ITX-새마을": 25000, "SRT": 36000, "고속버스": 21000, "시외버스": 18000}


def duration(origin_id: str, dest_id: str, mode: str) -> int:
    a, b = _BASE_MIN.get(origin_id, 60), _BASE_MIN.get(dest_id, 120)
    base = abs(b - a) or 60
    return round(base * _FACTOR[mode] / 5) * 5


class ScheduleError(RuntimeError):
    """수단별 운행정보 조회 실패 — 해당 수단만 제외한다 (FR-5 예외)."""


def fetch_live(mode: str, origin_id: str, dest_id: str, date_iso: str) -> List[Dict[str, Any]]:
    """[실연동 교체 지점] TAGO(열차/고속/시외) · ODsay(복합) 호출.

    반환: 정규화된 leg 목록 — mode, no, from, to, dep, arr, fare
    (좌석 상태는 여기서 채우지 않는다. tools/seats.py 담당.)
    """
    raise ScheduleError(f"{mode} 실연동 미구성 (TAGO 키 필요)")


def fetch_mock(mode: str, origin_id: str, dest_id: str, arrive_by: int) -> List[Dict[str, Any]]:
    """시연용 운행정보 — 실제 시간표처럼 배차 간격을 두고 생성한다.

    운행 편성은 도착 마감 시각과 무관하게 존재하므로, 출발 시각을 기준으로
    편을 만들고 도착은 소요시간으로 계산한다 (마감 초과 편도 포함 — onTime이 걸러낸다).
    """
    dur = duration(origin_id, dest_id, mode)
    # 실제 배차 간격에 가깝게 (경부선 KTX 10~30분 등). 간격이 지나치게 넓으면
    # 환승 연결(대기 ≥20분)이 성립하지 않아 재조합이 사실상 불가능해진다.
    headway = {"KTX": 20, "SRT": 30, "ITX-새마을": 60, "고속버스": 30, "시외버스": 50}[mode]
    rnd = random.Random(f"{mode}{origin_id}{dest_id}")
    first_dep = 5 * 60 + rnd.randint(0, 5) * 10   # 첫차 05:00~05:50

    from ..core import places

    o = places.get(origin_id) or {}
    d = places.get(dest_id) or {}

    legs = []
    dep = first_dep
    while dep + dur <= arrive_by + 60 and len(legs) < 8:   # 마감 1시간 초과분까지만 생성
        no = f"{mode} {rnd.randint(11, 89)}회" if mode.endswith("버스") else f"{mode} {rnd.randint(101, 899)}"
        legs.append({
            "mode": mode,
            "no": no,
            "from": origin_id,
            "to": dest_id,
            "fromName": o.get("name", origin_id),
            "toName": d.get("name", dest_id),
            "dep": dep,
            "arr": dep + dur,
            "fare": _FARE[mode] + rnd.randint(0, 9) * 100,
        })
        dep += headway
    return legs


def fetch(mode: str, origin_id: str, dest_id: str, date_iso: str, arrive_by: int) -> Dict[str, Any]:
    """운행정보 조회. 반환: {legs, mode(DataMode), checkedAt}

    TOOL_MODE=live면 실 API를 시도하고, 실패 시 예외를 올린다 (수단 제외 → FR-5 예외).
    TOOL_MODE=mock이면 목업을 쓰고 DataMode.SIMULATED로 표시한다 (§5-1: 상태명 혼용 금지).
    """
    checked_at = time.strftime("%Y-%m-%dT%H:%M:%S")
    if settings.tool_mode == "live":
        legs = fetch_live(mode, origin_id, dest_id, date_iso)  # 실패 시 ScheduleError
        return {"legs": legs, "mode": "LIVE", "checkedAt": checked_at}
    return {"legs": fetch_mock(mode, origin_id, dest_id, arrive_by), "mode": "SIMULATED", "checkedAt": checked_at}
