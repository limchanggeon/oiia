"""장소 카탈로그 — 역·터미널 정규화 + 자동완성 (FR-1 ①②, FR-2).

canonicalId로 정규화해 수단별 어댑터(TAGO/코레일/버스)가 같은 키를 쓰게 한다.
동명 시설이 있으면 region·type을 함께 표시한다 (FR-1 ①).

[실연동 교체 지점] TAGO 터미널/역 코드 목록으로 교체. 지금은 시연 도시 위주.
"""
from typing import Any, Dict, List, Optional

# canonicalId → 시설 목록 (한 도시에 역·터미널이 함께 있을 수 있다)
PLACES: List[Dict[str, Any]] = [
    {"canonicalId": "SEOUL", "name": "서울", "type": "station", "region": "서울특별시", "aliases": ["서울역"]},
    {"canonicalId": "SEOUL_EXPRESS", "name": "서울고속버스터미널", "type": "terminal", "region": "서울특별시", "aliases": ["센트럴시티", "강남터미널"]},
    {"canonicalId": "YONGSAN", "name": "용산", "type": "station", "region": "서울특별시", "aliases": ["용산역"]},
    {"canonicalId": "SUSEO", "name": "수서", "type": "station", "region": "서울특별시", "aliases": ["수서역"]},
    {"canonicalId": "DAEJEON", "name": "대전", "type": "station", "region": "대전광역시", "aliases": ["대전역"]},
    {"canonicalId": "DAEJEON_TERMINAL", "name": "대전복합터미널", "type": "terminal", "region": "대전광역시", "aliases": ["대전터미널"]},
    {"canonicalId": "DONGDAEGU", "name": "동대구", "type": "station", "region": "대구광역시", "aliases": ["동대구역"]},
    {"canonicalId": "BUSAN", "name": "부산", "type": "station", "region": "부산광역시", "aliases": ["부산역"]},
    {"canonicalId": "BUSAN_TERMINAL", "name": "부산종합버스터미널", "type": "terminal", "region": "부산광역시", "aliases": ["노포동터미널"]},
    {"canonicalId": "GWANGJU_SONGJEONG", "name": "광주송정", "type": "station", "region": "광주광역시", "aliases": ["광주송정역"]},
    {"canonicalId": "MOKPO", "name": "목포", "type": "station", "region": "전라남도", "aliases": ["목포역"]},
    {"canonicalId": "OSONG", "name": "오송", "type": "station", "region": "충청북도", "aliases": ["오송역"]},
    {"canonicalId": "CHEONAN_ASAN", "name": "천안아산", "type": "station", "region": "충청남도", "aliases": ["천안아산역"]},
    {"canonicalId": "IKSAN", "name": "익산", "type": "station", "region": "전라북도", "aliases": ["익산역"]},
    {"canonicalId": "JEONJU", "name": "전주", "type": "station", "region": "전라북도", "aliases": ["전주역"]},
    {"canonicalId": "GANGNEUNG", "name": "강릉", "type": "station", "region": "강원도", "aliases": ["강릉역"]},
    {"canonicalId": "POHANG", "name": "포항", "type": "station", "region": "경상북도", "aliases": ["포항역"]},
    {"canonicalId": "ULSAN", "name": "울산", "type": "station", "region": "울산광역시", "aliases": ["울산역"]},
    {"canonicalId": "YEOSU", "name": "여수", "type": "station", "region": "전라남도", "aliases": ["여수엑스포역", "여수"]},
]

_TYPE_LABEL = {"station": "역", "terminal": "터미널"}


def _to_place(row: Dict[str, Any]) -> Dict[str, Any]:
    # 동명 시설 구분: 이름이 겹치면 지역·유형을 함께 노출 (FR-1 ①)
    same_name = [p for p in PLACES if p["name"] == row["name"]]
    suffix = f" · {row['region']}" if len(same_name) > 1 else ""
    label = row["name"] if row["type"] == "terminal" else f"{row['name']}역"
    return {
        "name": row["name"],
        "type": row["type"],
        "canonicalId": row["canonicalId"],
        "region": row["region"],
        "display": f"{label}{suffix}",
    }


def search(query: str, limit: int = 6) -> List[Dict[str, Any]]:
    """자동완성 — 이름/별칭 부분 일치."""
    q = (query or "").strip()
    if not q:
        return []
    hits = [
        row for row in PLACES
        if q in row["name"] or any(q in a for a in row["aliases"]) or q in row["region"]
    ]
    # 정확 일치 우선
    hits.sort(key=lambda r: (0 if r["name"] == q else 1, len(r["name"])))
    return [_to_place(r) for r in hits[:limit]]


def get(canonical_id: str) -> Optional[Dict[str, Any]]:
    row = next((r for r in PLACES if r["canonicalId"] == canonical_id), None)
    return _to_place(row) if row else None


def nearest(lat: Optional[float] = None, lng: Optional[float] = None) -> Dict[str, Any]:
    """현재 위치 기반 추천 (FR-1 ①).

    [실연동 교체 지점] 좌표 → 최근접 역/터미널. 지금은 데모 기본값(서울).
    자동 확정하지 않고 '추천값'으로만 내려보낸다 — 사용자가 눌러야 확정.
    """
    return _to_place(next(r for r in PLACES if r["canonicalId"] == "SEOUL"))
