"""LLM 판단 엔진 공통 계약.

모든 파서는 `async parse(text) -> dict(부분 TripParams)`를 구현한다.
반환 형식(계약)만 지키면 rule ↔ ollama ↔ anthropic 을 환경변수로 교체할 수 있고,
프론트는 수정이 필요 없다.

LLM 파서(anthropic/ollama)는 중간 형식
  {"origin": str|None, "dest": str|None, "date_iso": "YYYY-MM-DD"|None, "arrive_time": "HH:MM"|None}
을 출력하고, normalize()가 계약 형식으로 변환한다.
"""
import datetime as dt
from typing import Any, Dict, Optional

from ..config import settings


def build_output_config(schema: Dict[str, Any]) -> Dict[str, Any]:
    """structured outputs 설정 — effort는 지원 모델에서만 붙인다.

    Haiku 4.5는 effort 파라미터를 받지 않는다(400). Opus/Sonnet 계열은
    단순 추출 작업이므로 low로 지연·비용을 줄인다.
    """
    cfg: Dict[str, Any] = {"format": {"type": "json_schema", "schema": schema}}
    if not settings.llm_model.startswith("claude-haiku"):
        cfg["effort"] = "low"
    return cfg


def date_context(today: dt.date) -> str:
    """상대 날짜 근거 주입 — LLM이 '다음 주'를 한 주 뒤로 미는 오류 방지 (주=월요일 시작)."""
    monday = today - dt.timedelta(days=today.weekday())
    def rng(offset: int) -> str:
        s = monday + dt.timedelta(days=7 * offset)
        return f"{s.isoformat()}~{(s + dt.timedelta(days=6)).isoformat()}"
    return f"주 기준(월요일 시작): 이번 주 {rng(0)}, 다음 주 {rng(1)}, 다다음 주 {rng(2)}"


STATIONS = [
    "서울", "용산", "수서", "대전", "동대구", "부산", "광주송정", "목포",
    "오송", "천안아산", "익산", "전주", "강릉", "포항", "울산", "여수",
]

# LLM guided JSON 스키마 (Anthropic structured outputs / Ollama format 공용)
INTENT_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "origin": {
            "anyOf": [{"type": "string"}, {"type": "null"}],
            "description": "출발역 이름 (역 목록에 있는 이름만, 없으면 null)",
        },
        "dest": {
            "anyOf": [{"type": "string"}, {"type": "null"}],
            "description": "도착역 이름 (역 목록에 있는 이름만, 없으면 null)",
        },
        "date_iso": {
            "anyOf": [{"type": "string"}, {"type": "null"}],
            "description": "도착 희망 날짜 YYYY-MM-DD (상대 날짜는 오늘 기준으로 변환, 없으면 null)",
        },
        "arrive_time": {
            "anyOf": [{"type": "string"}, {"type": "null"}],
            "description": "도착 희망 시각 HH:MM 24시간제 (없으면 null)",
        },
    },
    "required": ["origin", "dest", "date_iso", "arrive_time"],
    "additionalProperties": False,
}

SYSTEM_PROMPT = (
    "당신은 한국 기차·버스 예매 서비스의 파라미터 추출기입니다. "
    "사용자 문장에서 출발역(origin), 도착역(dest), 도착 희망 날짜(date_iso), 도착 희망 시각(arrive_time)만 추출합니다.\n"
    f"- 역 목록: {', '.join(STATIONS)} — 목록에 없는 지명은 null로 둡니다.\n"
    "- '~에서'가 붙은 역은 출발지, '~까지/~로/~가/도착'으로 언급된 역은 도착지입니다.\n"
    "- '지금/현재 위치/여기서'는 출발지 서울을 의미합니다.\n"
    "- 오늘/내일/모레 같은 상대 날짜는 제공된 오늘 날짜 기준으로 YYYY-MM-DD로 변환합니다.\n"
    "- 시각이 모호하면(예: '3시') 낮 시간대(15:00)로 해석합니다.\n"
    "- 문장에 없는 값은 반드시 null로 둡니다. 추측하지 않습니다."
)


def build_date(today: dt.date, iso: Optional[str] = None, offset: Optional[int] = None) -> Optional[Dict[str, str]]:
    if iso:
        try:
            d = dt.date.fromisoformat(iso)
        except ValueError:
            return None
    elif offset is not None:
        d = today + dt.timedelta(days=offset)
    else:
        return None
    delta = (d - today).days
    label = {0: "오늘", 1: "내일", 2: "모레"}.get(delta, f"{d.month}월 {d.day}일")
    return {"label": label, "md": f"{d.month}월 {d.day}일", "iso": d.isoformat()}


def build_time(hhmm: str) -> Optional[Dict[str, Any]]:
    try:
        h, mi = (int(x) for x in hhmm.strip().split(":"))
    except (ValueError, AttributeError):
        return None
    if not (0 <= h < 24 and 0 <= mi < 60):
        return None
    return {"min": h * 60 + mi, "label": f"{h:02d}:{mi:02d}"}


def normalize(raw: Dict[str, Any], today: dt.date) -> Dict[str, Any]:
    """LLM 중간 형식 → 계약 형식(TripParams 부분). 역 이름은 목록 검증한다."""
    got: Dict[str, Any] = {}
    origin = raw.get("origin")
    dest = raw.get("dest")
    if origin in STATIONS:
        got["origin"] = origin
    if dest in STATIONS and dest != got.get("origin"):
        got["dest"] = dest
    if raw.get("date_iso"):
        d = build_date(today, iso=raw["date_iso"])
        if d:
            got["date"] = d
    if raw.get("arrive_time"):
        t = build_time(raw["arrive_time"])
        if t:
            got["time"] = t
    return got
