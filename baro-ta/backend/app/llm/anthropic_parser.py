"""상용 LLM API (Claude) 파서 — structured outputs로 guided JSON을 보장.

- 모델: LLM_MODEL (기본 claude-opus-4-8)
- 인증: ANTHROPIC_API_KEY 환경변수 (anthropic SDK가 자동으로 읽음)
- Opus 4.7+ 모델은 temperature 파라미터를 받지 않는다(400) —
  결정성은 output_config.format(JSON 스키마 강제)으로 확보한다.
호출 실패 시 상위(api.py)에서 규칙 기반 파서로 폴백한다.
"""
import datetime as dt
import json
from typing import Any, Dict

from anthropic import AsyncAnthropic

from ..config import settings
from .base import INTENT_SCHEMA, SYSTEM_PROMPT, build_output_config, date_context, normalize

_client = None


def _get_client() -> AsyncAnthropic:
    global _client
    if _client is None:
        _client = AsyncAnthropic()
    return _client


async def parse_anthropic(text: str, today: dt.date) -> Dict[str, Any]:
    weekday = "월화수목금토일"[today.weekday()]
    response = await _get_client().messages.create(
        model=settings.llm_model,
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        output_config=build_output_config(INTENT_SCHEMA),
        messages=[
            {
                "role": "user",
                "content": f"오늘 날짜: {today.isoformat()} ({weekday}요일)\n{date_context(today)}\n사용자 문장: {text}",
            }
        ],
    )
    raw_text = next(b.text for b in response.content if b.type == "text")
    return normalize(json.loads(raw_text), today)
