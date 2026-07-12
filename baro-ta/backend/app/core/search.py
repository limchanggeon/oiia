"""검색 오케스트레이터 (FR-5/6/7/8) — 통합 조회 → 좌석 판정 → 재조합 → 카드 구성.

VER3 불변식 (코드로 강제):
- 운행정보·좌석·예약의 데이터 모드를 **각각** 추적해 Provenance로 노출한다 (§5-2).
- UNKNOWN은 매진으로 변환하지 않는다 (§5-4) — 별도 목록으로 분리한다.
- 실제 조회값과 시뮬레이션 값에 같은 상태명을 쓰지 않는다 (§5-1) — SeatStatus가 구분한다.
"""
import asyncio
import datetime as dt
import hashlib
from typing import Any, Dict, List, Optional, Tuple

from ..schemas_v3 import AVAILABLE_STATUSES, SOLD_OUT_STATUSES, DataMode, SeatStatus
from ..tools import schedule, seats
from . import fares

MAX_TRANSFERS = 1
MIN_TRANSFER_WAIT = 20
MAX_DURATION_FACTOR = 1.5
MAX_CARDS = 3
_HUBS = ["DAEJEON", "OSONG", "DONGDAEGU"]

_MODE_LABEL = {"LIVE": "실제 API 조회", "SIMULATED": "시뮬레이션", "UNAVAILABLE": "확인 불가"}


def _fmt_ampm(minutes: int) -> str:
    m = minutes % 1440
    h, mi = m // 60, m % 60
    ampm = "오전" if h < 12 else "오후"
    h12 = h if 1 <= h <= 12 else (12 if h % 12 == 0 else h % 12)
    return f"{ampm} {h12}시" + (f" {mi}분" if mi else "")


def _checked_label(iso: Optional[str]) -> str:
    if not iso:
        return ""
    try:
        t = dt.datetime.fromisoformat(iso)
    except ValueError:
        return ""
    return f"{_fmt_ampm(t.hour * 60 + t.minute)} 확인"


def build_provenance(schedule_mode: str, seat_mode: str, checked_at: Optional[str]) -> Dict[str, Any]:
    """카드 표시 문구까지 서버가 만든다 — 표현 일관성 유지 (§5-2, §5-3)."""
    seat_text = {
        "LIVE": "좌석 실시간",
        "SIMULATED": "좌석 시뮬레이션",
        "UNAVAILABLE": "좌석 확인 불가",
    }[seat_mode]
    parts = [f"운행정보 {_MODE_LABEL[schedule_mode]}", seat_text, "예약 시뮬레이션"]
    checked = _checked_label(checked_at)
    label = " · ".join(parts) + (f" · {checked}" if checked else "")
    return {
        "schedule": schedule_mode,
        "seat": seat_mode,
        "booking": DataMode.SIMULATED.value,
        "checkedAt": checked_at,
        "label": label,
    }


def _worst_seat_status(legs: List[Dict[str, Any]]) -> str:
    """여정 전체 좌석 상태 — 한 구간이라도 매진이면 매진, 하나라도 UNKNOWN이면 UNKNOWN."""
    statuses = [l["seatStatus"] for l in legs]
    if any(s in {SeatStatus.LIVE_SOLD_OUT.value, SeatStatus.SIMULATED_SOLD_OUT.value} for s in statuses):
        return next(s for s in statuses if s in {SeatStatus.LIVE_SOLD_OUT.value, SeatStatus.SIMULATED_SOLD_OUT.value})
    if any(s == SeatStatus.UNKNOWN.value for s in statuses):
        return SeatStatus.UNKNOWN.value
    if all(s == SeatStatus.LIVE_AVAILABLE.value for s in statuses):
        return SeatStatus.LIVE_AVAILABLE.value
    return SeatStatus.SIMULATED_AVAILABLE.value


def _worst_mode(modes: List[str]) -> str:
    if "UNAVAILABLE" in modes:
        return "UNAVAILABLE"
    if "SIMULATED" in modes:
        return "SIMULATED"
    return "LIVE"


def _jid(legs: List[Dict[str, Any]]) -> str:
    key = "|".join(f"{l['no']}:{l['dep']}" for l in legs)
    return "jn_" + hashlib.md5(key.encode()).hexdigest()[:10]


def _make_journey(
    legs: List[Dict[str, Any]],
    passengers: Dict[str, int],
    schedule_mode: str,
    checked_at: Optional[str],
    arrive_by: int,
) -> Dict[str, Any]:
    dep, arr = legs[0]["dep"], legs[-1]["arr"]
    wait = legs[1]["dep"] - legs[0]["arr"] if len(legs) > 1 else None
    seat_mode = _worst_mode([l["seatMode"] for l in legs])
    return {
        "id": _jid(legs),
        "legs": legs,
        "dep": dep,
        "arr": arr,
        "durationMin": arr - dep,
        "transfers": len(legs) - 1,
        "transferWaitMin": wait,
        "transferAt": legs[0].get("toName") or legs[0]["to"] if len(legs) > 1 else None,
        "fare": fares.compute(legs, passengers),
        "seatStatus": _worst_seat_status(legs),
        "provenance": build_provenance(schedule_mode, seat_mode, checked_at),
        "reasons": [],
        "explain": None,
        "onTime": arr <= arrive_by,
    }


async def _attach_seats(
    legs: List[Dict[str, Any]], date_iso: str, sold_out_all: bool, seat_fail: bool
) -> None:
    """구간별 좌석 상태를 병렬 조회해 붙인다 (동시성 제한은 seats 모듈이 관리)."""
    results = await asyncio.gather(*[
        seats.lookup(l["mode"], l["no"], date_iso, l["dep"],
                     force_sold_out=sold_out_all, force_fail=seat_fail)
        for l in legs
    ])
    for leg, r in zip(legs, results):
        leg["seatStatus"] = r["status"]
        leg["seatMode"] = r["mode"]


async def search(
    origin_id: str,
    dest_id: str,
    date_iso: str,
    arrive_by: int,
    passengers: Dict[str, int],
    *,
    sold_out_all: bool = False,
    fail_sources: Optional[List[str]] = None,
    seat_lookup_fail: bool = False,
    use_simulated_for_unknown: bool = False,
    only_confirmed: bool = False,
) -> Dict[str, Any]:
    fail_sources = fail_sources or []
    log: List[Tuple[str, str]] = []

    # ── FR-5: 수단별 운행정보 조회 (개별 장애는 해당 수단만 제외) ──
    candidates: List[Dict[str, Any]] = []
    excluded_sources: List[str] = []
    fell_back: List[str] = []
    for mode in schedule.SOURCES:
        try:
            if mode in fail_sources:
                raise schedule.ScheduleError(f"{mode} 조회 실패 (시뮬레이션)")
            res = await schedule.fetch(mode, origin_id, dest_id, date_iso, arrive_by)
            if res.get("fellBack"):
                fell_back.append(mode)
            for leg in res["legs"]:
                candidates.append({"leg": leg, "mode": res["mode"], "checkedAt": res["checkedAt"]})
        except Exception:
            excluded_sources.append(mode)
    if excluded_sources:
        log.append(("SEARCH", f"운행정보 조회 실패 → 제외: {', '.join(excluded_sources)}"))
    if fell_back:
        log.append(("SEARCH", f"운행정보 실조회 실패 → 시뮬레이션 전환(카드에 표시): {', '.join(fell_back)}"))

    if not candidates:
        return {"journeys": [], "unknown": [], "excluded_sold_out": 0,
                "excluded_sources": excluded_sources, "recombined": False, "log": log}

    # ── FR-6: 좌석 상태 (열차=실시간 시도, 버스=시뮬레이션) ──
    legs = [c["leg"] for c in candidates]
    await _attach_seats(legs, date_iso, sold_out_all, seat_lookup_fail)

    journeys = [
        _make_journey([c["leg"]], passengers, c["mode"], c["checkedAt"], arrive_by)
        for c in candidates
    ]

    # UNKNOWN → 사용자가 [시뮬레이션으로 보기]를 선택한 경우에만 대체 (§5-5)
    if use_simulated_for_unknown:
        for j in journeys:
            if j["seatStatus"] == SeatStatus.UNKNOWN.value:
                for leg in j["legs"]:
                    if leg["seatStatus"] == SeatStatus.UNKNOWN.value:
                        r = seats._simulate_seat(leg["mode"], leg["no"], date_iso, False)
                        leg["seatStatus"], leg["seatMode"] = r["status"], r["mode"]
                j["seatStatus"] = _worst_seat_status(j["legs"])
                j["provenance"] = build_provenance(
                    j["provenance"]["schedule"], "SIMULATED", j["provenance"]["checkedAt"]
                )
                j["provenance"]["label"] += " · 좌석 확인 실패로 시뮬레이션 전환"
        log.append(("SEAT", "UNKNOWN → 시뮬레이션 좌석으로 대체 (사용자 선택, 카드에 전환 고지)"))

    sold_out = [j for j in journeys if j["seatStatus"] in {s.value for s in SOLD_OUT_STATUSES}]
    unknown = [j for j in journeys if j["seatStatus"] == SeatStatus.UNKNOWN.value]
    available = [j for j in journeys
                 if j["seatStatus"] in {s.value for s in AVAILABLE_STATUSES} and j["onTime"]]

    log.append(("SEAT", f"좌석 판정 — 가능 {len(available)} · 매진 {len(sold_out)} · 확인불가 {len(unknown)}"))

    # ── FR-7: 전 후보 매진이면 재조합 ──
    recombined = False
    if not available and sold_out:
        fastest = min(j["durationMin"] for j in journeys)
        alt = await _recombine(origin_id, dest_id, date_iso, arrive_by, passengers,
                               fastest, sold_out_all, seat_lookup_fail)
        if alt:
            available = alt
            recombined = True
            log.append(("RECOMBINE", f"직결 전 후보 매진 → 환승 대체 여정 {len(alt)}건 "
                                     "(환승 ≤1, 대기 ≥20분, 소요 ≤직결최속 1.5배)"))

    cards = _pick_cards(available)
    _add_reasons(cards)

    if only_confirmed:
        unknown = []

    return {
        "journeys": cards,
        "unknown": unknown,
        "excluded_sold_out": len(sold_out),
        "excluded_sources": excluded_sources,
        "recombined": recombined,
        "log": log,
    }


async def _recombine(
    origin_id: str, dest_id: str, date_iso: str, arrive_by: int,
    passengers: Dict[str, int], fastest_direct: int,
    sold_out_all: bool, seat_fail: bool,
) -> List[Dict[str, Any]]:
    """FR-7 — 허브 경유 환승 조합 탐색.

    각 구간의 **모든 편성**을 후보로 놓고 좌석 있는 조합을 찾는다.
    (첫 편성만 보면 그 차가 매진일 때 나머지 편성을 시도조차 못 하고 포기한다.)

    제약: 갈아타기 ≤1회 · 환승 대기 ≥20분 · 총 소요 ≤ 직결 최속 × 1.5 · 도착 마감 이내.
    """
    limit = fastest_direct * MAX_DURATION_FACTOR
    out: List[Dict[str, Any]] = []

    for hub in _HUBS:
        if hub in (origin_id, dest_id):
            continue
        # 우회 자체가 제약을 넘으면 편성을 볼 필요도 없다
        min_total = (schedule.duration(origin_id, hub, "KTX")
                     + MIN_TRANSFER_WAIT
                     + schedule.duration(hub, dest_id, "KTX"))
        if min_total > limit:
            continue

        try:
            r1 = await schedule.fetch("KTX", origin_id, hub, date_iso, arrive_by)
            r2 = await schedule.fetch("KTX", hub, dest_id, date_iso, arrive_by)
        except Exception:
            continue

        legs1, legs2 = list(r1["legs"]), list(r2["legs"])
        await _attach_seats(legs1, date_iso, False, seat_fail)  # 재조합 경로엔 매진 시뮬 미적용
        await _attach_seats(legs2, date_iso, False, seat_fail)

        avail = {s.value for s in AVAILABLE_STATUSES}
        ok1 = [l for l in legs1 if l["seatStatus"] in avail]
        ok2 = [l for l in legs2 if l["seatStatus"] in avail]

        best: Optional[Dict[str, Any]] = None
        for l1 in ok1:
            for l2 in ok2:
                wait = l2["dep"] - l1["arr"]
                if wait < MIN_TRANSFER_WAIT:
                    continue
                j = _make_journey([dict(l1), dict(l2)], passengers, r1["mode"], r1["checkedAt"], arrive_by)
                if not j["onTime"] or j["durationMin"] > limit:
                    continue
                if best is None or (j["arr"], j["durationMin"]) < (best["arr"], best["durationMin"]):
                    best = j
        if best:
            out.append(best)
        if len(out) >= 2:
            break
    return out


def _pick_cards(available: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """대표성 기반 선별 (FR-8) — '가장 빨라요 / 가장 저렴해요 / 갈아타지 않아요'가
    모두 후보에 있으면 각각 한 장씩 뽑는다.

    단순 정렬(도착순·요금순)로 자르면 도착 시각이 비슷할 때 가장 빠른 열차가
    요금에 밀려 누락된다 — 어르신이 기대하는 선택지가 사라지므로 대표편을 먼저 확보한다.
    """
    if not available:
        return []
    picks: List[Dict[str, Any]] = []

    def add(j: Optional[Dict[str, Any]]) -> None:
        if j is not None and not any(p["id"] == j["id"] for p in picks):
            picks.append(j)

    add(min(available, key=lambda j: (j["durationMin"], j["fare"]["total"])))          # 가장 빠름
    add(min(available, key=lambda j: (j["fare"]["total"], j["durationMin"])))          # 가장 저렴
    direct = [j for j in available if j["transfers"] == 0]
    if direct:
        add(min(direct, key=lambda j: (j["arr"], j["fare"]["total"])))                 # 직통 중 이른 도착

    # 남는 자리는 이른 도착 순으로 채운다
    for j in sorted(available, key=lambda j: (j["transfers"], j["arr"], j["fare"]["total"])):
        if len(picks) >= MAX_CARDS:
            break
        add(j)

    picks.sort(key=lambda j: (j["transfers"], j["arr"], j["durationMin"]))
    return picks[:MAX_CARDS]


def _add_reasons(cards: List[Dict[str, Any]]) -> None:
    """추천 근거 키 (FR-7 출력, FR-8 카드) — 결정적 코드가 판단한다."""
    if not cards:
        return
    fastest = min(cards, key=lambda j: j["durationMin"])
    cheapest = min(cards, key=lambda j: j["fare"]["total"])
    for j in cards:
        r = []
        if j is fastest:
            r.append("가장 빨라요")
        if j is cheapest and len(cards) > 1:
            r.append("가장 저렴해요")
        if j["transfers"] == 0:
            r.append("갈아타지 않아요")
        j["reasons"] = r or ["조건에 맞아요"]
