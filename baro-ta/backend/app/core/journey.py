"""FR-6/7/8 — 전 수단 통합 검색 오케스트레이션 · 매진 제외 · 여정 재조합 엔진.

FR-8 알고리즘 (명세의 "?"에 대한 제안 — 결정적 코드):
  1. 직결 후보가 모두 매진이면 허브(대전·오송·동대구) 경유 2-leg 조합을 생성한다.
  2. 제약: 갈아타기 ≤ 1회, 환승 대기 ≥ 20분, 총 소요 ≤ 직결 최속편의 1.5배.
  3. 제약을 만족하는 조합만 반환하고, 없으면 빈 목록(정직하게 실패).
"""
import hashlib
from typing import Any, Dict, List, Optional, Tuple

from ..tools import transit_mock

# 시간대 → 출발 창 시작(분). FR-2 기본값 '아침'
TIME_WINDOWS = {"아침": 6 * 60, "낮": 10 * 60, "저녁": 15 * 60, "밤": 20 * 60}

MAX_TRANSFERS = 1
MIN_TRANSFER_WAIT = 20        # 분
MAX_DURATION_FACTOR = 1.5     # 직결 최속편 대비
MAX_RESULTS = 3               # 시니어 UI — 2~3개만 제시 (FR-9)

_HUBS = ["대전", "오송", "동대구"]


def _jid(legs: List[Dict[str, Any]]) -> str:
    key = "|".join(f"{l['no']}:{l['dep']}" for l in legs)
    return "jn_" + hashlib.md5(key.encode()).hexdigest()[:10]


def _make_journey(legs: List[Dict[str, Any]]) -> Dict[str, Any]:
    dep, arr = legs[0]["dep"], legs[-1]["arr"]
    wait = legs[1]["dep"] - legs[0]["arr"] if len(legs) > 1 else None
    return {
        "id": _jid(legs),
        "legs": legs,
        "dep": dep,
        "arr": arr,
        "durationMin": arr - dep,
        "totalFare": sum(l["fare"] for l in legs),
        "transfers": len(legs) - 1,
        "transferWaitMin": wait,
        "reservable": all(l["reservable"] for l in legs),
    }


def search_all_sources(
    origin: str, dest: str, window_start: int, fail_sources: List[str]
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """FR-6: 수단별 조회, 개별 장애는 해당 수단 제외로 흡수한다."""
    candidates: List[Dict[str, Any]] = []
    excluded: List[str] = []
    for source in transit_mock.SOURCES:
        try:
            if source in fail_sources:
                raise RuntimeError(f"{source} API 장애 (시뮬레이션)")
            # [실연동 교체 지점] TAGO·ODsay·korail2·SRTrain·KOBUS·티머니 결과를 정규화해 사용
            legs = transit_mock.search(source, origin, dest, window_start)
            candidates.extend(_make_journey([leg]) for leg in legs)
        except Exception:
            excluded.append(source)
    return candidates, excluded


def mark_sold_out(journeys: List[Dict[str, Any]], sold_out_all: bool) -> None:
    """FR-7: 매진 판정 (mock — 최속 직결편 매진, sim 시 전 직결편 매진)."""
    if not journeys:
        return
    if sold_out_all:
        for j in journeys:
            for l in j["legs"]:
                l["soldOut"] = True
        return
    fastest = min(journeys, key=lambda j: j["durationMin"])
    for l in fastest["legs"]:
        l["soldOut"] = True


def _is_available(j: Dict[str, Any]) -> bool:
    return not any(l.get("soldOut") for l in j["legs"])


def recombine(
    origin: str, dest: str, window_start: int, fastest_direct_dur: int
) -> List[Dict[str, Any]]:
    """FR-8: 허브 경유 대체 여정 생성 (제약 기반)."""
    out = []
    for hub in _HUBS:
        if hub in (origin, dest):
            continue
        leg2_dur = transit_mock.leg_duration(hub, dest, "KTX")
        leg1 = transit_mock.search("KTX", origin, hub, window_start)[0]
        wait = max(MIN_TRANSFER_WAIT, 25)
        leg2_dep = leg1["arr"] + wait
        leg2 = dict(transit_mock.search("KTX", hub, dest, leg2_dep - 20)[0])
        leg2["dep"], leg2["arr"] = leg2_dep, leg2_dep + leg2_dur
        journey = _make_journey([leg1, leg2])
        if (
            journey["transfers"] <= MAX_TRANSFERS
            and (journey["transferWaitMin"] or 0) >= MIN_TRANSFER_WAIT
            and journey["durationMin"] <= fastest_direct_dur * MAX_DURATION_FACTOR
        ):
            out.append(journey)
        if len(out) >= 2:
            break
    return out


def search_journeys(
    origin: str,
    dest: str,
    time_of_day: str,
    sold_out_all: bool = False,
    fail_sources: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """FR-6 → FR-7 → (필요 시) FR-8 파이프라인. 예약 가능 경로 최대 3개."""
    window_start = TIME_WINDOWS.get(time_of_day, TIME_WINDOWS["아침"])
    candidates, excluded = search_all_sources(origin, dest, window_start, fail_sources or [])
    mark_sold_out(candidates, sold_out_all)

    available = [j for j in candidates if _is_available(j)]
    recombined = False
    if not available and candidates:
        fastest_dur = min(j["durationMin"] for j in candidates)
        available = recombine(origin, dest, window_start, fastest_dur)
        recombined = True

    # 정렬: 갈아타기 적은 순 → 출발 이른 순 → 소요 짧은 순
    available.sort(key=lambda j: (j["transfers"], j["dep"], j["durationMin"]))
    return {
        "journeys": available[:MAX_RESULTS],
        "excluded_sources": excluded,
        "recombined": recombined,
        "total_candidates": len(candidates),
    }


def summarize_slots(slots: Dict[str, Any]) -> str:
    """FR-4 확인 요약 — '7월 15일 화요일 아침 / 대전 → 부산 / 어른 1명'."""
    import datetime as dt

    d = dt.date.fromisoformat(slots["date"]["iso"])
    weekday = "월화수목금토일"[d.weekday()]
    tod = slots.get("timeOfDay", "아침")
    n = slots.get("passengers", 1)
    return f"{d.month}월 {d.day}일 {weekday}요일 {tod} / {slots['departure']} → {slots['arrival']} / 어른 {n}명"
