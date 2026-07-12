"""LLM 경로 설명문 — 노령 사용자용 쉬운 한 문장 (structured outputs, 1회 호출로 일괄 생성).

실패하면 호출 측이 결정적 설명문(core/explain.py)을 유지한다.
"""
import json
import re
from typing import Any, Dict, List, Optional

from ..config import settings
from .base import build_output_config

EXPLAIN_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "explanations": {
            "type": "array",
            "items": {"type": "string"},
            "description": "경로별 설명문 — 입력 순서·개수 동일",
        }
    },
    "required": ["explanations"],
    "additionalProperties": False,
}

EXPLAIN_SYSTEM_PROMPT = (
    "당신은 노령세대(50–70대)를 위한 이동 비서입니다. 각 경로마다 어르신이 바로 이해할 수 있는 "
    "설명문을 한 문장씩 만듭니다.\n"
    "- 30자 이내, 쉬운 말, 과장 금지. 예: '갈아타지 않는 제일 빠른 차예요.'\n"
    "- 다른 경로와 비교되는 장점(빠름/저렴/직통/환승)을 하나만 골라 말합니다.\n"
    "- 입력 배열과 같은 순서·같은 개수로 출력합니다.\n"
    "\n[절대 금지 — 위반 시 문장이 폐기됩니다]\n"
    "1. 숫자를 쓰지 마세요. 시각·소요시간·요금·분·원·호차는 이미 카드에 표시되므로 "
    "문장에 넣지 않습니다. ('10분 빠르고' ×, '3만원대' ×, '더 빨라요' ○)\n"
    "2. 주어진 시간·요금·좌석 상태를 바꾸거나 새로 계산하지 않습니다.\n"
    "3. 좌석 유무·매진 여부를 판단하거나 언급하지 않습니다.\n"
    "당신은 확정된 데이터를 '비교해서 말로 옮기는' 역할만 합니다."
)

# 숫자·단위가 섞이면 LLM이 값을 지어낸 것으로 보고 폐기한다 (FR-8, §4)
_FORBIDDEN = re.compile(r"[0-9]|분\s|원|시간|호차|퍼센트|%")

# 최상급 주장은 코드가 판단한 근거(reasons)와 일치할 때만 허용한다.
# LLM이 실제로는 더 비싼 편에 "가장 저렴한 기차예요"를 붙인 사례가 있었다 (FR-8 위반).
_CLAIMS = [
    (re.compile(r"싸|저렴|경제적"), "가장 저렴해요"),
    (re.compile(r"빠르|빨리|신속"), "가장 빨라요"),
]


def _fmt(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def sanitize(text: str, fallback: str, reasons: Optional[List[str]] = None) -> str:
    """LLM이 값을 지어냈으면 폐기하고 정형 문구로 대체한다 (FR-8, §4).

    LLM은 시간·요금·좌석을 '판단하거나 새로 만들' 수 없다. 두 가지를 검사한다:
    1. 숫자·단위 — '10분 빠르고'처럼 실제 차이(5분)와 다른 수치를 만든 사례가 있었다.
    2. 최상급 주장 — 실제로는 더 비싼 편에 '가장 저렴한 기차예요'를 붙인 사례가 있었다.
       코드가 판단한 근거(reasons)에 없는 우위 주장은 폐기한다.
    """
    t = (text or "").strip()
    if not t or _FORBIDDEN.search(t):
        return fallback
    for pattern, required in _CLAIMS:
        if pattern.search(t) and required not in (reasons or []):
            return fallback
    return t


async def explain_anthropic(
    journeys: List[Dict[str, Any]],
    fallbacks: Optional[List[str]] = None,
    reasons: Optional[List[List[str]]] = None,
) -> List[str]:
    from .anthropic_parser import _get_client

    brief = [
        {
            "수단": " + ".join(l["mode"] for l in j["legs"]),
            "출발": _fmt(j["dep"]),
            "도착": _fmt(j["arr"]),
            "소요분": j["durationMin"],
            "요금": j["totalFare"],
            "환승": j["transfers"],
        }
        for j in journeys
    ]
    response = await _get_client().messages.create(
        model=settings.llm_model,
        max_tokens=1024,
        system=EXPLAIN_SYSTEM_PROMPT,
        output_config=build_output_config(EXPLAIN_SCHEMA),
        messages=[{"role": "user", "content": json.dumps(brief, ensure_ascii=False)}],
    )
    raw_text = next(b.text for b in response.content if b.type == "text")
    explanations = json.loads(raw_text)["explanations"]
    if len(explanations) != len(journeys):
        raise ValueError("설명문 개수 불일치")

    fbs = fallbacks or [""] * len(journeys)
    rs = reasons or [[] for _ in journeys]
    return [sanitize(str(e), fb, r) for e, fb, r in zip(explanations, fbs, rs)]
