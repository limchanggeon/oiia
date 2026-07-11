"""규칙 기반 파서 — 기본값이자 LLM 실패 시 폴백 (골든패스).

server/src/services/nlu.js 와 동일 로직의 파이썬 포팅.
"""
import datetime as dt
import re
from typing import Any, Dict, Optional

from .base import STATIONS, build_date


def _parse_time(text: str) -> Optional[int]:
    m = re.search(r"(오전|오후|아침|저녁|밤)?\s*(\d{1,2})시\s*(반|\d{1,2}분)?", text)
    if m:
        h = int(m.group(2))
        mi = 0
        g3 = m.group(3)
        if g3 == "반":
            mi = 30
        elif g3:
            mi = int(g3.replace("분", ""))
        mer = m.group(1) or ""
        if mer in ("오후", "저녁", "밤") and h < 12:
            h += 12
        if not mer and h <= 8:
            h += 12  # 모호하면 낮 시간대로 해석
        return h * 60 + mi
    m = re.search(r"(\d{1,2}):(\d{2})", text)
    if m:
        return int(m.group(1)) * 60 + int(m.group(2))
    return None


def parse_rule(text: str, today: dt.date) -> Dict[str, Any]:
    got: Dict[str, Any] = {}

    for s in STATIONS:
        if re.search(rf"{s}(역)?\s*(에서|출발)", text):
            got["origin"] = s
        # "에(?!서)": "서울에서"의 '에'가 도착지 조사로 오인되지 않도록
        if re.search(rf"{s}(역)?\s*(까지|으로|로|에(?!서)|가|행|도착)", text):
            got["dest"] = s

    mentioned = [s for s in STATIONS if s in text]
    if got.get("dest") and got["dest"] == got.get("origin"):
        got["dest"] = next((s for s in mentioned if s != got.get("origin")), None)
    if not got.get("dest") and mentioned:
        got["dest"] = next((s for s in mentioned if s != got.get("origin")), None)
    if got.get("dest") is None:
        got.pop("dest", None)
    if re.search(r"지금|현재\s*위치|여기서", text):
        got["origin"] = "서울"

    if "오늘" in text:
        got["date"] = build_date(today, offset=0)
    elif "내일" in text:
        got["date"] = build_date(today, offset=1)
    elif "모레" in text:
        got["date"] = build_date(today, offset=2)
    else:
        m = re.search(r"(\d{1,2})월\s*(\d{1,2})일", text)
        if m:
            d = dt.date(today.year, int(m.group(1)), int(m.group(2)))
            got["date"] = build_date(today, iso=d.isoformat())

    t = _parse_time(text)
    if t is not None:
        got["time"] = {"min": t, "label": f"{t // 60:02d}:{t % 60:02d}"}

    return got
