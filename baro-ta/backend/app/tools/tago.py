"""TAGO 실연동 어댑터 (VER3 §1/§4 — 운행정보·요금은 실제 외부 API).

국토교통부 TAGO (공공데이터포털 data.go.kr) 3종:
- 열차정보    TrainInfoService      : 시간표 + 성인요금
- 고속버스    ExpBusInfoService     : 시간표 + 요금
- 시외버스    SuburbsBusInfoService : 시간표 + 요금

키 발급: data.go.kr에서 위 3개 오픈API 각각 '활용신청' → 일반 인증키(Decoding) 사용.
        .env의 TAGO_API_KEY 에 넣는다.

역·터미널 코드는 **추측하지 않는다**. TAGO의 코드 목록 API로 조회해 도시/이름으로 매칭하고
SQLite(tool_cache)에 캐시한다 — 잘못된 코드를 하드코딩하면 조용히 빈 결과가 나온다.
"""
import datetime as dt
from typing import Any, Dict, List, Optional

import httpx

from .. import db
from ..config import settings

BASE = "http://apis.data.go.kr/1613000"

TRAIN = f"{BASE}/TrainInfoService"
EXPBUS = f"{BASE}/ExpBusInfoService"
SUBBUS = f"{BASE}/SuburbsBusInfoService"

CODE_CACHE_TTL = 60 * 60 * 24 * 7   # 역·터미널 코드는 자주 안 바뀐다
TIMEOUT = 8.0

# 열차 등급명(TAGO traingradename) → 내부 mode
_TRAIN_GRADE = {
    "KTX": "KTX", "KTX-산천": "KTX", "KTX-이음": "KTX", "KTX-청룡": "KTX",
    "SRT": "SRT",
    "ITX-새마을": "ITX-새마을", "새마을": "ITX-새마을", "ITX-마음": "ITX-새마을",
    "무궁화호": "무궁화호", "누리로": "무궁화호", "ITX-청춘": "무궁화호",
}

# canonicalId → (TAGO 검색용 이름, 도시명)
_PLACE_HINT = {
    "SEOUL": ("서울", "서울"),
    "YONGSAN": ("용산", "서울"),
    "SUSEO": ("수서", "서울"),
    "SEOUL_EXPRESS": ("서울경부", "서울"),
    "DAEJEON": ("대전", "대전"),
    "DAEJEON_TERMINAL": ("대전복합", "대전"),
    "DONGDAEGU": ("동대구", "대구"),
    "BUSAN": ("부산", "부산"),
    "BUSAN_TERMINAL": ("부산", "부산"),
    "GWANGJU_SONGJEONG": ("광주송정", "광주"),
    "MOKPO": ("목포", "목포"),
    "OSONG": ("오송", "청주"),
    "CHEONAN_ASAN": ("천안아산", "천안"),
    "IKSAN": ("익산", "익산"),
    "JEONJU": ("전주", "전주"),
    "GANGNEUNG": ("강릉", "강릉"),
    "POHANG": ("포항", "포항"),
    "ULSAN": ("울산", "울산"),
    "YEOSU": ("여수", "여수"),
}


class TagoError(RuntimeError):
    pass


def enabled() -> bool:
    return bool(settings.tago_api_key)


def _items(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    """TAGO 응답에서 item 목록 추출 (0건이면 items가 빈 문자열로 온다)."""
    try:
        body = payload["response"]["body"]
    except (KeyError, TypeError):
        raise TagoError(f"예상치 못한 응답 형식: {str(payload)[:120]}")
    items = body.get("items")
    if not items:
        return []
    item = items.get("item") if isinstance(items, dict) else None
    if item is None:
        return []
    return item if isinstance(item, list) else [item]


async def _get(client: httpx.AsyncClient, url: str, params: Dict[str, Any]) -> Dict[str, Any]:
    p = {
        "serviceKey": settings.tago_api_key,
        "_type": "json",
        "numOfRows": 200,
        "pageNo": 1,
        **params,
    }
    r = await client.get(url, params=p, timeout=TIMEOUT)
    r.raise_for_status()
    # 키 오류 등은 XML(에러 문서)로 오기도 한다
    ct = r.headers.get("content-type", "")
    if "json" not in ct.lower():
        raise TagoError(f"JSON이 아닌 응답 (키 오류 가능): {r.text[:120]}")
    return r.json()


# ── 코드 조회 (역·터미널) ────────────────────────────
async def _city_codes(client: httpx.AsyncClient) -> List[Dict[str, Any]]:
    cached = db.cache_get("tago:citycodes")
    if cached:
        return cached
    data = await _get(client, f"{TRAIN}/getCtyCodeList", {})
    rows = _items(data)
    db.cache_set("tago:citycodes", rows, CODE_CACHE_TTL)
    return rows


async def station_id(client: httpx.AsyncClient, canonical_id: str) -> str:
    """canonicalId → TAGO 기차역 코드 (NAT...). 도시코드로 역 목록을 받아 이름으로 매칭."""
    key = f"tago:station:{canonical_id}"
    hit = db.cache_get(key)
    if hit:
        return hit

    name, city = _PLACE_HINT.get(canonical_id, (canonical_id, ""))
    cities = await _city_codes(client)
    matches = [c for c in cities if city and city in str(c.get("cityname", ""))]
    if not matches:
        raise TagoError(f"도시코드를 찾지 못했어요: {city} ({canonical_id})")

    for c in matches:
        data = await _get(client, f"{TRAIN}/getCtyAcctoTrainSttnList", {"cityCode": c["citycode"]})
        for st in _items(data):
            st_name = str(st.get("nodename", ""))
            if st_name == name or st_name == f"{name}역" or st_name.startswith(name):
                code = str(st["nodeid"])
                db.cache_set(key, code, CODE_CACHE_TTL)
                return code
    raise TagoError(f"기차역 코드를 찾지 못했어요: {name} ({canonical_id})")


async def terminal_id(client: httpx.AsyncClient, canonical_id: str, express: bool) -> str:
    """canonicalId → TAGO 터미널 코드. express=True면 고속버스, False면 시외버스."""
    kind = "exp" if express else "sub"
    key = f"tago:terminal:{kind}:{canonical_id}"
    hit = db.cache_get(key)
    if hit:
        return hit

    name, city = _PLACE_HINT.get(canonical_id, (canonical_id, ""))
    url = f"{EXPBUS}/getExpBusTrminlList" if express else f"{SUBBUS}/getSuberbsBusTrminlList"
    data = await _get(client, url, {})
    rows = _items(data)

    def score(t: Dict[str, Any]) -> int:
        tn = str(t.get("terminalNm", t.get("terminalnm", "")))
        s = 0
        if city and city in tn:
            s += 2
        if name and name in tn:
            s += 3
        return s

    best = max(rows, key=score, default=None)
    if best is None or score(best) == 0:
        raise TagoError(f"터미널 코드를 찾지 못했어요: {name} ({canonical_id}, {kind})")
    code = str(best.get("terminalId", best.get("terminalid", "")))
    db.cache_set(key, code, CODE_CACHE_TTL)
    return code


# ── 운행정보 조회 ───────────────────────────────────
def _hhmm(ts: Any) -> int:
    """TAGO 시각(YYYYMMDDHHMM(SS)) → 자정 기준 분."""
    s = str(ts)
    if len(s) < 12:
        raise TagoError(f"시각 형식 오류: {s}")
    return int(s[8:10]) * 60 + int(s[10:12])


async def fetch_train(canonical_from: str, canonical_to: str, date_iso: str) -> List[Dict[str, Any]]:
    """열차 시간표·요금 (KTX·SRT·일반열차). 반환: 정규화된 leg 목록."""
    ymd = date_iso.replace("-", "")
    async with httpx.AsyncClient() as client:
        dep_id = await station_id(client, canonical_from)
        arr_id = await station_id(client, canonical_to)
        data = await _get(client, f"{TRAIN}/getStrtpntAlocFndTrainInfo", {
            "depPlaceId": dep_id, "arrPlaceId": arr_id, "depPlandTime": ymd,
        })

    legs = []
    for it in _items(data):
        grade = str(it.get("traingradename", "")).strip()
        mode = _TRAIN_GRADE.get(grade)
        if mode is None:
            continue                      # 알 수 없는 등급은 버린다 (임의 매핑 금지)
        try:
            dep, arr = _hhmm(it["depplandtime"]), _hhmm(it["arrplandtime"])
        except (KeyError, TagoError):
            continue
        if arr <= dep:                    # 자정 넘김 편성은 시연 범위에서 제외
            continue
        legs.append({
            "mode": mode,
            "no": f"{mode} {it.get('trainno', '')}".strip(),
            "from": canonical_from,
            "to": canonical_to,
            "dep": dep,
            "arr": arr,
            "fare": int(it.get("adultcharge") or 0),
        })
    return legs


async def fetch_bus(canonical_from: str, canonical_to: str, date_iso: str, express: bool) -> List[Dict[str, Any]]:
    """고속/시외버스 시간표·요금."""
    ymd = date_iso.replace("-", "")
    mode = "고속버스" if express else "시외버스"
    url = (f"{EXPBUS}/getStrtpntAlocFndExpbusInfo" if express
           else f"{SUBBUS}/getStrtpntAlocFndSuberbsBusInfo")

    async with httpx.AsyncClient() as client:
        dep_id = await terminal_id(client, canonical_from, express)
        arr_id = await terminal_id(client, canonical_to, express)
        data = await _get(client, url, {
            "depTerminalId": dep_id, "arrTerminalId": arr_id, "depPlandTime": ymd,
        })

    legs = []
    for it in _items(data):
        try:
            dep, arr = _hhmm(it["depPlandTime"]), _hhmm(it["arrPlandTime"])
        except (KeyError, TagoError):
            continue
        if arr <= dep:
            continue
        grade = str(it.get("gradeNm", "")).strip()
        legs.append({
            "mode": mode,
            "no": f"{mode} {grade}".strip() if grade else mode,
            "from": canonical_from,
            "to": canonical_to,
            "dep": dep,
            "arr": arr,
            "fare": int(it.get("charge") or 0),
        })
    return legs
