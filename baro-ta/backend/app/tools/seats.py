"""좌석 상태 조회 어댑터 (FR-6) — 열차는 실시간 조회, 버스는 시뮬레이션.

VER3 §2 시연 안전 규칙을 코드로 강제한다:
- korail2·SRTrain의 **예약 함수는 호출하지 않는다** — 이 모듈은 조회만 노출한다.
  reserve()는 항상 ReservationDisabled를 던지는 차단 스텁이며, subprocess로 실행하는
  py/seat_lookup.py 에도 예약 계열 호출이 없다.
- 동일 구간 조회는 짧은 시간 캐시하고 중복 호출을 합친다 (구간 단위 조회 + in-flight 병합).
- 동시 호출 수와 재시도 횟수를 제한한다. 무한 재시도 금지.
- 조회 실패는 UNKNOWN으로 반환한다 — **매진으로 변환하지 않는다** (§5-4).
"""
import asyncio
import json
import os
import random
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from ..config import settings

SEAT_CACHE_TTL = 60          # 초 — 동일 구간 재조회 억제 (§2). 명세 "60초 hold"
MAX_CONCURRENCY = 3          # 동시 좌석 조회(외부 호출) 수 제한
MAX_RETRIES = 1              # 재시도 1회까지 (무한 재시도 금지)
LOOKUP_TIMEOUT = 20.0        # 초 — subprocess 전체

TRAIN_MODES = {"KTX", "ITX-새마을", "무궁화호", "SRT"}
BUS_MODES = {"고속버스", "시외버스"}

KORAIL_MODES = {"KTX", "ITX-새마을", "무궁화호"}   # 코레일 조회 대상
SRT_MODES = {"SRT"}

_SCRIPT = Path(__file__).resolve().parent.parent.parent / "py" / "seat_lookup.py"

_sem = asyncio.Semaphore(MAX_CONCURRENCY)
_cache: Dict[str, Tuple[float, Dict[str, bool]]] = {}     # 구간키 → (만료, {편명키: soldOut})
_inflight: Dict[str, asyncio.Future] = {}


class ReservationDisabled(RuntimeError):
    """예약·선점 함수 호출 차단 (§2, §5-6). 대회 버전에 실제 예약은 존재하지 않는다."""


def reserve(*_args, **_kwargs):
    """실제 예약 진입점 — 항상 차단된다. 예약은 core/simulation.py(목업)만 수행한다."""
    raise ReservationDisabled(
        "실제 예약·좌석 선점은 비활성화되어 있습니다 (대회 시연 안전 규칙). "
        "예약 시뮬레이션은 core/simulation.py를 사용하세요."
    )


def train_key(mode: str, no: str) -> str:
    """편명 매칭 키 — 열차번호 자릿수 표기가 소스마다 달라(075 vs 75) 숫자만 뽑아 비교한다."""
    digits = re.sub(r"\D", "", no or "")
    return f"{mode}:{int(digits)}" if digits else f"{mode}:{no}"


def _run_lookup(provider: str, dep_name: str, arr_name: str, ymd: str, hhmmss: str) -> list:
    env = {**os.environ, "SRT_ID": settings.srt_id, "SRT_PW": settings.srt_pw}
    proc = subprocess.run(
        [sys.executable, str(_SCRIPT), provider, dep_name, arr_name, ymd, hhmmss],
        capture_output=True, text=True, timeout=LOOKUP_TIMEOUT, env=env,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"{provider} 좌석 조회 실패: {proc.stderr.strip()[:120]}")
    return json.loads(proc.stdout)


async def fetch_route_rows(provider: str, dep_name: str, arr_name: str, date_iso: str) -> list:
    """구간의 열차 목록(시간표+요금+좌석)을 한 번 조회해 캐시한다.

    schedule.py(시간표)와 seats.py(좌석)가 **같은 캐시를 공유**하므로
    한 구간당 외부 호출은 1회로 합쳐진다 (§2 중복 호출 억제).
    """
    key = f"rail:{provider}:{dep_name}:{arr_name}:{date_iso}"

    hit = _cache.get(key)
    if hit and hit[0] > time.time():
        return hit[1]
    if key in _inflight:
        return await _inflight[key]              # 중복 호출 합치기 (§2)

    loop = asyncio.get_running_loop()
    fut: asyncio.Future = loop.create_future()
    _inflight[key] = fut
    try:
        ymd = date_iso.replace("-", "")
        async with _sem:                          # 동시 호출 제한 (§2)
            for attempt in range(MAX_RETRIES + 1):
                try:
                    rows = await asyncio.to_thread(_run_lookup, provider, dep_name, arr_name, ymd, "000000")
                    break
                except Exception:                 # noqa: BLE001
                    if attempt >= MAX_RETRIES:
                        raise                     # 재시도 상한 (무한 재시도 금지)
                    await asyncio.sleep(0.5)

        _cache[key] = (time.time() + SEAT_CACHE_TTL, rows)
        if not fut.done():
            fut.set_result(rows)
        return rows
    except BaseException as e:
        # 최초 조회가 실패하면 대기자도 함께 풀어준다 (무한 대기 방지)
        if not fut.done():
            fut.set_exception(e)
        raise
    finally:
        _inflight.pop(key, None)


async def _lookup_route(provider: str, dep_name: str, arr_name: str, date_iso: str) -> Dict[str, bool]:
    """구간의 {편명키: soldOut} 맵 (fetch_route_rows 캐시 재사용)."""
    rows = await fetch_route_rows(provider, dep_name, arr_name, date_iso)
    return {train_key(r["mode"], r["no"]): bool(r["soldOut"]) for r in rows}


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
    leg: Dict[str, Any],
    date_iso: str,
    *,
    force_sold_out: bool = False,
    force_fail: bool = False,
) -> Dict[str, Any]:
    """구간(leg)의 좌석 상태. 반환: {status: SeatStatus, mode: DataMode, checkedAt}

    - 열차: korail2/SRTrain 실시간 조회 → 실패 시 UNKNOWN (매진 아님, §5-4)
    - 버스: 시뮬레이션 (명세상 좌석 실조회 불가)
    """
    checked_at = time.strftime("%Y-%m-%dT%H:%M:%S")
    mode, no = leg["mode"], leg["no"]

    if force_fail:
        return {"status": "UNKNOWN", "mode": "UNAVAILABLE", "checkedAt": checked_at}

    # 시뮬레이션 강제(매진 시연)는 캐시·실조회를 우회한다
    if force_sold_out:
        return {**_simulate_seat(mode, no, date_iso, True), "checkedAt": checked_at}

    # 버스: 시뮬레이션 전용 (FR-6, 명세 §1)
    if mode in BUS_MODES:
        return {**_simulate_seat(mode, no, date_iso, False), "checkedAt": checked_at}

    # 시뮬레이션 시간표에는 실제 좌석을 붙이지 않는다 —
    # 실제값과 목업을 섞으면 출처가 무의미해진다 (§5-1)
    if settings.tool_mode != "live":
        return {**_simulate_seat(mode, no, date_iso, False), "checkedAt": checked_at}

    provider = "KORAIL" if mode in KORAIL_MODES else "SRT" if mode in SRT_MODES else None
    if provider is None:
        return {"status": "UNKNOWN", "mode": "UNAVAILABLE", "checkedAt": checked_at}

    dep_name = leg.get("fromName") or leg["from"]
    arr_name = leg.get("toName") or leg["to"]
    try:
        seat_map = await _lookup_route(provider, dep_name, arr_name, date_iso)
    except Exception:
        return {"status": "UNKNOWN", "mode": "UNAVAILABLE", "checkedAt": checked_at}

    sold = seat_map.get(train_key(mode, no))
    if sold is None:
        # 시간표에는 있는데 좌석 응답에 없는 편 — 판단 불가. 매진으로 단정하지 않는다.
        return {"status": "UNKNOWN", "mode": "UNAVAILABLE", "checkedAt": checked_at}
    return {
        "status": "LIVE_SOLD_OUT" if sold else "LIVE_AVAILABLE",
        "mode": "LIVE",
        "checkedAt": checked_at,
    }
