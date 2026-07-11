"""로컬 LLM (Ollama) 파서 — guided JSON(format 스키마) + temp=0.

플로우차트의 "로컬 LLM · Qwen3-4B/8B · guided JSON · temp = 0" 담당.
- 모델: LLM_MODEL (예: qwen3:4b)
- 주소: OLLAMA_BASE_URL (기본 http://localhost:11434)
호출 실패 시 상위(api.py)에서 규칙 기반 파서로 폴백한다.
"""
import datetime as dt
import json
from typing import Any, Dict

import httpx

from ..config import settings
from .base import INTENT_SCHEMA, SYSTEM_PROMPT, normalize


async def parse_ollama(text: str, today: dt.date) -> Dict[str, Any]:
    weekday = "월화수목금토일"[today.weekday()]
    async with httpx.AsyncClient(timeout=60.0) as hc:
        r = await hc.post(
            f"{settings.ollama_base_url}/api/chat",
            json={
                "model": settings.llm_model,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": f"오늘 날짜: {today.isoformat()} ({weekday}요일)\n사용자 문장: {text}",
                    },
                ],
                "format": INTENT_SCHEMA,  # guided JSON
                "options": {"temperature": 0},
                "stream": False,
            },
        )
        r.raise_for_status()
        content = r.json()["message"]["content"]
    return normalize(json.loads(content), today)
