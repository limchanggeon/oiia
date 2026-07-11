"""재랭킹 = scoring.py — 경로 후보 적합도 산출 (순수 함수).

플로우차트의 "재랭킹 = scoring.py (코드)" 담당.
LLM이 아닌 결정적 코드로 점수를 매겨 재현 가능성을 보장한다.
"""
from typing import Any, Dict, List


def rerank(routes: List[Dict[str, Any]], arrive_by: int) -> List[Dict[str, Any]]:
    """적합도 = 97 - 도착여유*0.45 - (소요-최단소요)*0.28, [42, 99] 클램프."""
    if not routes:
        return routes
    min_dur = min(r["dur"] for r in routes)
    for r in routes:
        gap = arrive_by - r["arr"]
        score = 97 - gap * 0.45 - (r["dur"] - min_dur) * 0.28
        r["score"] = round(max(42, min(99, score)))
    routes.sort(key=lambda r: r["score"], reverse=True)
    return routes
