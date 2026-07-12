"""좌석 상태 조회 어댑터 (FR-6) — 열차는 실시간 조회, 버스는 시뮬레이션.

VER3 §2 시연 안전 규칙을 코드로 강제한다:
- korail2·SRTrain의 **예약 함수는 호출하지 않는다** — 이 모듈은 조회 함수만 노출한다.
  reserve/cancel에 해당하는 진입점 자체가 없으며, 시도 시 ReservationDisabled를 던진다.
- 동일 조건 좌석 조회는 짧은 시간 캐시하고 중복 호출을 합친다 (in-flight 병합).
- 동시 호출 수와 재시도 횟수를 제한한다. 무한 재시도 금지.
- 조회 실패는 UNKNOWN으로 반환한다 — **매진으로 변환하지 않는다** (§5-4).
"""
import asyncio
import random
import time
from typing import Any, Dict, Optional, Tuple

from ..config import settings

SEAT_CACHE_TTL = 30          # 초 — 동일 조건 재조회 억제 (§2 안전 규칙)
MAX_CONCURRENCY = 4          # 동시 좌석 조회 수 제한
MAX_RETRIES = 1              # 재시도 1회까지만 (무한 재시도 금지)
LOOKUP_TIMEOUT = 6.0         # 초

TRAIN_MODES = {"KTX", "ITX-새마을", "SRT"}
BUS_MODES = {"고속버스", "시외버스"}

_sem = asyncio.Semaphore(MAX_CONCURRENCY)
_cache: Dict[str, Tuple[float, Dict[str, Any]]] = {}
_inflight: Dict[str, asyncio.Future] = {}


class ReservationDisabled(RuntimeError):
    """예약·선점 함수 호출 차단 (§2, §5-6). 대회 버전에서 실제 예약은 존재하지 않는다."""


def reserve(*_args, **_kwargs):
    """실제 예약 진입점 — 항상 차단된다. 예약은 core/simulation.py(목업)만 수행한다."""
    raise ReservationDisabled(
        "실제 예약·좌석 선점은 비활성화되어 있습니다 (대회 시연 안전 규칙). "
        "예약 시뮬레이션은 core/simulation.py를 사용하세요."
    )


def _key(mode: str, no: str, date_iso: str) -> str:
    return f"seat:{mode}:{no}:{date_iso}"


def _lookup_live_train(mode: str, no: str, date_iso: str, dep: int) -> bool:
    """[실연동 교체 지점] korail2 / SRTrain **조회 전용** 호출.

    korail2: Korail(id, pw).search_train(...) → 좌석 유무만 읽는다.
    SRTrain: SRT(id, pw).search_train(...) → 동일.
    ※ reserve()는 절대 호출하지 않는다 (§2).

    반환: 좌석 있음 여부. 실패 시 예외 → 호출 측에서 UNKNOWN 처리.
    """
    if not (settings.korail_id and settings.korail_pw):
        raise RuntimeError("코레일 계정 미설정 — 좌석 실시간 조회 불가")
    raise RuntimeError("korail2/SRTrain 실연동 미구성")


def _simulate_seat(mode: str, no: str, date_iso: str, sold_out: bool) -> Dict[str, Any]:
    if sold_out:
        return {"status": "SIMULATED_SOLD_OUT", "mode": "SIMULATED"}
    # 편명 해시 기반 결정적 시뮬레이션 — 같은 편은 같은 결과 (재조회 시 흔들리지 않음)
    rnd = random.Random(f"{mode}{no}{date_iso}")
    available = rnd.random() > 0.25
    return {
        "status": "SIMULATED_AVAILABLE" if available else "SIMULATED_SOLD_OUT",
        "mode": "SIMULATED",
    }


async def lookup(
    mode: str,
    no: str,
    date_iso: str,
    dep: int,
    *,
    force_sold_out: bool = False,
    force_fail: bool = False,
) -> Dict[str, Any]:
    """좌석 상태 조회. 반환: {status: SeatStatus, mode: DataMode, checkedAt}

    - 열차: 실시간 조회 시도 → 실패 시 UNKNOWN (매진 아님)
    - 버스: 시뮬레이션 (명세상 좌석 실조회 불가)
    """
    checked_at = time.strftime("%Y-%m-%dT%H:%M:%S")

    if force_fail:
        return {"status": "UNKNOWN", "mode": "UNAVAILABLE", "checkedAt": checked_at}

    # 버스: 시뮬레이션 전용 (FR-6)
    if mode in BUS_MODES:
        r = _simulate_seat(mode, no, date_iso, force_sold_out)
        return {**r, "checkedAt": checked_at}

    # 시뮬레이션 강제(매진 시연 등)는 캐시를 우회한다 —
    # 캐시된 실조회/이전 시뮬 결과가 시연 옵션을 덮어써 재조합이 안 걸리는 버그가 있었다.
    if force_sold_out:
        return {**_simulate_seat(mode, no, date_iso, True), "checkedAt": checked_at}

    # 열차: 캐시 → in-flight 병합 → 실조회
    key = _key(mode, no, date_iso)
    hit = _cache.get(key)
    if hit and hit[0] > time.time():
        return {**hit[1], "checkedAt": hit[1].get("checkedAt", checked_at)}

    if key in _inflight:
        return await _inflight[key]          # 중복 호출 합치기 (§2)

    loop = asyncio.get_running_loop()
    fut: asyncio.Future = loop.create_future()
    _inflight[key] = fut
    try:
        result = await _lookup_train_with_policy(mode, no, date_iso, dep, force_sold_out, checked_at)
        _cache[key] = (time.time() + SEAT_CACHE_TTL, result)
        if not fut.done():
            fut.set_result(result)
        return result
    finally:
        _inflight.pop(key, None)


async def _lookup_train_with_policy(
    mode: str, no: str, date_iso: str, dep: int, force_sold_out: bool, checked_at: str
) -> Dict[str, Any]:
    if settings.tool_mode != "live":
        # 시뮬레이션 모드 — 실조회를 시도하지 않는다 (§5-1: 출처를 명확히 구분)
        return {**_simulate_seat(mode, no, date_iso, force_sold_out), "checkedAt": checked_at}

    async with _sem:                                  # 동시 호출 제한 (§2)
        for attempt in range(MAX_RETRIES + 1):        # 재시도 상한 (무한 재시도 금지)
            try:
                available = await asyncio.wait_for(
                    asyncio.to_thread(_lookup_live_train, mode, no, date_iso, dep),
                    timeout=LOOKUP_TIMEOUT,
                )
                return {
                    "status": "LIVE_AVAILABLE" if available else "LIVE_SOLD_OUT",
                    "mode": "LIVE",
                    "checkedAt": checked_at,
                }
            except Exception:
                if attempt >= MAX_RETRIES:
                    # 실패 → UNKNOWN. 매진으로 변환하지 않는다 (§5-4)
                    return {"status": "UNKNOWN", "mode": "UNAVAILABLE", "checkedAt": checked_at}
                await asyncio.sleep(0.4)
    return {"status": "UNKNOWN", "mode": "UNAVAILABLE", "checkedAt": checked_at}
