"""경로 설명문 (명세 'LLM 용도: 설명문') — 결정적 생성 + FR-13 탑승 안내 데이터.

결정적 설명문은 항상 생성되는 골든패스이며, LLM(anthropic)이 켜져 있으면
llm/explain.py 가 더 자연스러운 문장으로 덮어쓴다 (실패 시 이 결과 유지).
"""
import datetime as dt
from typing import Any, Dict, List


def add_explanations(journeys: List[Dict[str, Any]]) -> None:
    """비교 기반 한 줄 설명 — '가장 빨리 도착해요 · 갈아타지 않아요'."""
    if not journeys:
        return
    fastest = min(journeys, key=lambda j: j["durationMin"])
    cheapest = min(journeys, key=lambda j: j["totalFare"])
    for j in journeys:
        parts = []
        if j is fastest:
            parts.append("가장 빨리 도착해요")
        if j is cheapest and len(journeys) > 1:
            parts.append("요금이 제일 저렴해요")
        if j["transfers"] == 0:
            parts.append("갈아타지 않아요")
        else:
            parts.append(f"{j['legs'][0]['to']}에서 한 번 갈아타요")
        j["explain"] = " · ".join(parts[:2])


def build_reminders(date_iso: str, dep_min: int, origin: str) -> List[Dict[str, str]]:
    """FR-13: 전날 저녁(20시)·당일 출발 2시간 전 알림 시각과 문구.

    발송 채널(푸시/SMS 등)은 명세 토의사항 — 여기서는 시각·문구 데이터만 제공하고
    데모에서는 화면 내 안내로 보여준다.
    """
    d = dt.date.fromisoformat(date_iso)
    dep_h, dep_m = dep_min // 60, dep_min % 60
    dep_label = f"{dep_h}시" + (f" {dep_m}분" if dep_m else "")
    evening = dt.datetime.combine(d - dt.timedelta(days=1), dt.time(20, 0))
    two_hours_before = dt.datetime.combine(d, dt.time(dep_h % 24, dep_m)) - dt.timedelta(hours=2)
    return [
        {
            "atIso": evening.isoformat(),
            "label": "전날 저녁",
            "message": f"내일 {dep_label}에 {origin}에서 출발해요. 표와 준비물을 미리 챙겨두세요.",
        },
        {
            "atIso": two_hours_before.isoformat(),
            "label": "당일 아침 (출발 2시간 전)",
            "message": f"오늘 {dep_label} {origin} 출발이에요. 슬슬 나설 준비를 해요.",
        },
    ]
