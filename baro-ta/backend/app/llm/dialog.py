"""FR-2/3 LLM 대화 관리자 — 슬롯 추출 + 선택형 되묻기 생성을 구조화 출력 1회로 처리.

- provider=anthropic: Claude structured outputs (guided JSON)
- provider=ollama:    로컬 LLM format 스키마 + temp=0
호출 실패 시 상위(api_v2.py)에서 규칙 기반(rule_dialog)으로 폴백한다.
"""
import datetime as dt
import json
from typing import Any, Dict, Optional

import httpx

from ..config import settings
from .base import STATIONS, build_date
from .holidays import upcoming

_NULLABLE_STR = {"anyOf": [{"type": "string"}, {"type": "null"}]}

DIALOG_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "departure": {**_NULLABLE_STR, "description": "출발 도시 (목록에 있는 이름만)"},
        "arrival": {**_NULLABLE_STR, "description": "도착 도시 (목록에 있는 이름만)"},
        "date_iso": {**_NULLABLE_STR, "description": "출발 날짜 YYYY-MM-DD (자연어 날짜를 오늘 기준으로 해석)"},
        "time_of_day": {
            "anyOf": [{"type": "string", "enum": ["아침", "낮", "저녁", "밤"]}, {"type": "null"}],
            "description": "출발 시간대",
        },
        "passengers": {
            "anyOf": [{"type": "integer"}, {"type": "null"}],
            "description": "인원 수 (어른 기준)",
        },
        "question": {**_NULLABLE_STR, "description": "빈 필수 슬롯이 있을 때만 생성하는 되묻기 질문 1개"},
        "options": {
            "anyOf": [
                {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {"label": {"type": "string"}, "slot_value": {"type": "string"}},
                        "required": ["label", "slot_value"],
                        "additionalProperties": False,
                    },
                },
                {"type": "null"},
            ],
            "description": "선택지 2~3개",
        },
        "target_slot": {
            "anyOf": [
                {"type": "string", "enum": ["departure", "arrival", "date", "time_of_day", "passengers"]},
                {"type": "null"},
            ]
        },
    },
    "required": ["departure", "arrival", "date_iso", "time_of_day", "passengers", "question", "options", "target_slot"],
    "additionalProperties": False,
}

DIALOG_SYSTEM_PROMPT = (
    "당신은 노령세대(50–70대)를 위한 기차·버스 이동 비서의 대화 관리자입니다. "
    "사용자 발화에서 여정 슬롯을 추출하고, 빈 필수 슬롯이 있으면 선택형 되묻기 질문을 만듭니다.\n"
    f"- 도시 목록: {', '.join(STATIONS)} — 목록에 없는 지명은 null.\n"
    "- 필수 슬롯: departure(출발지), arrival(도착지), date(날짜). "
    "time_of_day와 passengers는 필수가 아니므로 절대 되묻지 않습니다.\n"
    "- 날짜는 자연어를 오늘 날짜 기준으로 해석합니다 (예: '다음 주 화요일', '설 전날'=설날 하루 전).\n"
    "- 명절 날짜는 반드시 아래 '다가오는 명절' 표에 적힌 날짜만 사용합니다. 표에 없으면 추측하지 말고 null.\n"
    "- 발화에 없는 슬롯은 null. 추측하지 않습니다.\n"
    "[되묻기 규칙 — 빈 필수 슬롯이 있을 때만]\n"
    "1. 한 번에 하나만 묻습니다 (question 1개, target_slot 1개).\n"
    "2. 열린 질문 금지 — 반드시 선택지 2~3개(options)를 함께 만듭니다.\n"
    "3. 버튼 라벨(label)은 명사형/명령형 — 예: '아침 출발' ○ / '아침에 출발하시겠어요?' ×.\n"
    "4. slot_value는 사용자가 그대로 말해도 이해되는 짧은 한국어 (예: '내일', '부산').\n"
    "5. 이미 채워진 슬롯은 다시 묻지 않습니다.\n"
    "6. 필수 슬롯이 모두 채워졌으면 question/options/target_slot 모두 null."
)


def _user_content(text: str, slots: Dict[str, Any], today: dt.date) -> str:
    weekday = "월화수목금토일"[today.weekday()]
    return (
        f"오늘 날짜: {today.isoformat()} ({weekday}요일)\n"
        f"다가오는 명절: {', '.join(upcoming(today))}\n"
        f"현재 슬롯 상태: {json.dumps(slots, ensure_ascii=False)}\n"
        f"사용자 발화: {text}"
    )


def normalize_dialog(raw: Dict[str, Any], today: dt.date) -> Dict[str, Any]:
    """LLM 출력 → 검증된 슬롯 + ask. 도시는 목록 검증, 옵션은 2~3개로 자른다."""
    slots: Dict[str, Any] = {}
    if raw.get("departure") in STATIONS:
        slots["departure"] = raw["departure"]
    if raw.get("arrival") in STATIONS and raw.get("arrival") != slots.get("departure"):
        slots["arrival"] = raw["arrival"]
    if raw.get("date_iso"):
        d = build_date(today, iso=raw["date_iso"])
        if d:
            slots["date"] = d
    if raw.get("time_of_day") in ("아침", "낮", "저녁", "밤"):
        slots["timeOfDay"] = raw["time_of_day"]
    if isinstance(raw.get("passengers"), int) and 1 <= raw["passengers"] <= 9:
        slots["passengers"] = raw["passengers"]

    ask: Optional[Dict[str, Any]] = None
    if raw.get("question") and raw.get("options") and raw.get("target_slot"):
        options = [o for o in raw["options"] if o.get("label") and o.get("slot_value")][:3]
        if len(options) >= 2:
            ask = {"question": raw["question"], "options": options, "target_slot": raw["target_slot"]}
    return {"slots": slots, "ask": ask}


async def dialog_anthropic(text: str, slots: Dict[str, Any], today: dt.date) -> Dict[str, Any]:
    from .anthropic_parser import _get_client

    response = await _get_client().messages.create(
        model=settings.llm_model,
        max_tokens=1024,
        system=DIALOG_SYSTEM_PROMPT,
        output_config={
            "format": {"type": "json_schema", "schema": DIALOG_SCHEMA},
            "effort": "low",
        },
        messages=[{"role": "user", "content": _user_content(text, slots, today)}],
    )
    raw_text = next(b.text for b in response.content if b.type == "text")
    return normalize_dialog(json.loads(raw_text), today)


async def dialog_ollama(text: str, slots: Dict[str, Any], today: dt.date) -> Dict[str, Any]:
    async with httpx.AsyncClient(timeout=60.0) as hc:
        r = await hc.post(
            f"{settings.ollama_base_url}/api/chat",
            json={
                "model": settings.llm_model,
                "messages": [
                    {"role": "system", "content": DIALOG_SYSTEM_PROMPT},
                    {"role": "user", "content": _user_content(text, slots, today)},
                ],
                "format": DIALOG_SCHEMA,
                "options": {"temperature": 0},
                "stream": False,
            },
        )
        r.raise_for_status()
        content = r.json()["message"]["content"]
    return normalize_dialog(json.loads(content), today)
