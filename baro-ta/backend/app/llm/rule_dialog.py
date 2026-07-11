"""FR-2/3 규칙 기반 폴백 — 슬롯 추출 v2 + 템플릿 되묻기.

LLM 없이도 골든패스가 항상 동작하도록 유지한다.
날짜는 오늘/내일/모레/N월 N일/이번·다음 주 X요일까지 처리 (명절 등은 LLM만).
"""
import datetime as dt
import re
from typing import Any, Dict, Optional

from .base import STATIONS, build_date
from .holidays import HOLIDAYS
from .rule_parser import _parse_time

_WEEKDAYS = {"월": 0, "화": 1, "수": 2, "목": 3, "금": 4, "토": 5, "일": 6}
_KOR_NUM = {"한": 1, "두": 2, "세": 3, "네": 4, "다섯": 5}


def _holiday_date(text: str, today: dt.date) -> Optional[Dict[str, str]]:
    """'설 전날', '추석 당일' 등 — 명절 표 기준 (LLM 폴백 시에도 날짜가 흔들리지 않도록)."""
    m = re.search(r"(설날|설|추석|한가위)\s*(전날|다음\s*날|당일|날)?", text)
    if not m:
        return None
    name = "설날" if m.group(1) in ("설", "설날") else "추석"
    shift = {"전날": -1, "다음날": 1, "다음 날": 1}.get((m.group(2) or "").strip(), 0)
    for iso, hname in sorted(HOLIDAYS.items()):
        d = dt.date.fromisoformat(iso)
        if hname == name and d >= today:
            return build_date(today, iso=(d + dt.timedelta(days=shift)).isoformat())
    return None


def _parse_date(text: str, today: dt.date) -> Optional[Dict[str, str]]:
    h = _holiday_date(text, today)
    if h:
        return h
    if "오늘" in text:
        return build_date(today, offset=0)
    if "내일" in text:
        return build_date(today, offset=1)
    if "모레" in text:
        return build_date(today, offset=2)
    m = re.search(r"(\d{1,2})월\s*(\d{1,2})일", text)
    if m:
        d = dt.date(today.year, int(m.group(1)), int(m.group(2)))
        return build_date(today, iso=d.isoformat())
    m = re.search(r"(이번\s*주|다음\s*주|다다음\s*주)?\s*([월화수목금토일])요일", text)
    if m:
        wd = _WEEKDAYS[m.group(2)]
        prefix = (m.group(1) or "").replace(" ", "")
        if prefix == "다음주":
            days = (7 - today.weekday()) + wd          # 다음 주 월요일 기준
        elif prefix == "다다음주":
            days = (7 - today.weekday()) + 7 + wd
        elif prefix == "이번주":
            days = wd - today.weekday()
            if days < 0:
                days += 7  # 이미 지난 요일이면 다음 occurrence
        else:
            days = (wd - today.weekday()) % 7 or 7      # 맨몸 "화요일" = 다음 화요일
        return build_date(today, offset=days)
    return None


def _parse_time_of_day(text: str) -> Optional[str]:
    t = _parse_time(text)
    if t is not None:
        h = t // 60
        if h < 10:
            return "아침"
        if h < 15:
            return "낮"
        if h < 20:
            return "저녁"
        return "밤"
    if re.search(r"아침|오전|이른", text):
        return "아침"
    if re.search(r"점심|정오|낮|오후", text):
        return "낮"
    if "저녁" in text:
        return "저녁"
    if re.search(r"밤|심야", text):
        return "밤"
    return None


def _parse_passengers(text: str) -> Optional[int]:
    m = re.search(r"(?:어른|성인)?\s*(\d|한|두|세|네|다섯)\s*명", text)
    if m:
        g = m.group(1)
        return int(g) if g.isdigit() else _KOR_NUM[g]
    if re.search(r"혼자", text):
        return 1
    if re.search(r"둘이", text):
        return 2
    return None


def extract_slots_rule(text: str, today: dt.date, target_slot: Optional[str] = None) -> Dict[str, Any]:
    """발화 → 부분 슬롯. target_slot은 직전 되묻기 대상 (단일 도시 답변 배정용)."""
    got: Dict[str, Any] = {}

    cities = [s for s in STATIONS if s in text]
    origin = dest = None
    for s in cities:
        if re.search(rf"{s}(역)?\s*(에서|출발)", text):
            origin = s
        if re.search(rf"{s}(역)?\s*(까지|으로|로|에(?!서)|가|행|도착)", text):
            dest = s
    # 되묻기 답변: 조사 없는 단일 도시는 직전에 물어본 슬롯으로 배정
    if len(cities) == 1 and origin is None and dest is None and target_slot in ("departure", "arrival"):
        got[target_slot] = cities[0]
    else:
        if dest is None and cities:
            dest = next((s for s in cities if s != origin), None)
        if origin:
            got["departure"] = origin
        if dest and dest != origin:
            got["arrival"] = dest
    if re.search(r"지금|현재\s*위치|여기서", text):
        got["departure"] = got.get("departure", "서울")

    d = _parse_date(text, today)
    if d:
        got["date"] = d
    tod = _parse_time_of_day(text)
    if tod:
        got["timeOfDay"] = tod
    p = _parse_passengers(text)
    if p:
        got["passengers"] = p
    return got


# ── 템플릿 되묻기 (FR-3 규칙 준수: 1개 질문, 선택지 2~3, 명사형 라벨) ──
def template_ask(missing_slot: str, slots: Dict[str, Any]) -> Dict[str, Any]:
    exclude = {slots.get("departure"), slots.get("arrival")}
    if missing_slot == "arrival":
        opts = [c for c in ("부산", "대전", "강릉", "광주송정") if c not in exclude][:3]
        return {
            "question": "어디로 가세요?",
            "options": [{"label": f"{c} 도착", "slot_value": c} for c in opts],
            "target_slot": "arrival",
        }
    if missing_slot == "departure":
        opts = [c for c in ("서울", "대전", "동대구") if c not in exclude][:3]
        return {
            "question": "어디서 출발하세요?",
            "options": [{"label": f"{c} 출발", "slot_value": c} for c in opts],
            "target_slot": "departure",
        }
    # date
    return {
        "question": "언제 출발하세요?",
        "options": [
            {"label": "오늘 출발", "slot_value": "오늘"},
            {"label": "내일 출발", "slot_value": "내일"},
            {"label": "모레 출발", "slot_value": "모레"},
        ],
        "target_slot": "date",
    }
