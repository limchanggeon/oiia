"""기차·버스 mock 데이터 생성기 — 골든패스 (KTX/SRT/항공 = mock).

server/src/services/routes.js 의 모의 경로 생성과 동일 로직.
live 모드에서는 kskill.run_skill("route-search", {...}) 결과가 이 형식으로
정규화되어 들어와야 한다 (RouteOption[] — schemas.py 참고).
"""
import random
import time
from typing import Any, Dict, List

DIST_MIN = {
    "부산": 155, "대전": 62, "동대구": 105, "광주송정": 110, "목포": 145,
    "오송": 48, "천안아산": 38, "익산": 82, "전주": 100, "강릉": 118,
    "포항": 140, "울산": 128, "여수": 180, "서울": 60, "용산": 60, "수서": 60,
}

MODES = [
    {"mode": "KTX", "factor": 1.0, "base_price": 380, "cls": ""},
    {"mode": "SRT", "factor": 0.96, "base_price": 360, "cls": ""},
    {"mode": "KTX", "factor": 1.0, "base_price": 380, "cls": ""},
    {"mode": "ITX-새마을", "factor": 1.55, "base_price": 250, "cls": ""},
    {"mode": "고속버스", "factor": 1.85, "base_price": 210, "cls": "bus"},
]

OFFSETS = [8, 22, 47, 15, 5]  # 희망 도착시각 대비 여유(분)


def generate_routes(origin: str, dest: str, arrive_by: int) -> List[Dict[str, Any]]:
    base = DIST_MIN.get(dest, 120)
    stamp = format(int(time.time() * 1000), "x")
    routes = []
    for i, m in enumerate(MODES):
        dur = round(base * m["factor"] / 5) * 5
        arr = arrive_by - OFFSETS[i]
        no = (
            f"우등 {random.randint(11, 89)}회"
            if m["mode"] == "고속버스"
            else f"{m['mode']} {random.randint(101, 899)}"
        )
        routes.append(
            {
                "id": f"rt_{stamp}_{i}",
                "mode": m["mode"],
                "cls": m["cls"],
                "no": no,
                "dep": arr - dur,
                "arr": arr,
                "dur": dur,
                "price": m["base_price"] * 100 + random.randint(0, 9) * 100,
                "soldOut": False,
                "score": 0,
            }
        )
    return routes
