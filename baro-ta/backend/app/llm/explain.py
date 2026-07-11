"""LLM 경로 설명문 — 노령 사용자용 쉬운 한 문장 (structured outputs, 1회 호출로 일괄 생성).

실패하면 호출 측이 결정적 설명문(core/explain.py)을 유지한다.
"""
import json
from typing import Any, Dict, List

from ..config import settings

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
    "- 입력 배열과 같은 순서·같은 개수로 출력합니다."
)


def _fmt(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


async def explain_anthropic(journeys: List[Dict[str, Any]]) -> List[str]:
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
        output_config={
            "format": {"type": "json_schema", "schema": EXPLAIN_SCHEMA},
            "effort": "low",
        },
        messages=[{"role": "user", "content": json.dumps(brief, ensure_ascii=False)}],
    )
    raw_text = next(b.text for b in response.content if b.type == "text")
    explanations = json.loads(raw_text)["explanations"]
    if len(explanations) != len(journeys):
        raise ValueError("설명문 개수 불일치")
    return [str(e).strip() for e in explanations]
