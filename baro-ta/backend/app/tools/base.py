"""도구 어댑터 3-mode 러너 — live / cache / mock + 3단 폴백.

플로우차트의 "어댑터 3-mode: live / cache / mock", "3단 폴백 live → cache → mock",
"골든패스 mock 100%" 담당.

사용법:
    result = await run_tool("routes.search", live_fn=..., mock_fn=..., cache_key="...")
    result.data    # 조회 결과
    result.source  # "live" | "cache" | "mock"  ← 에이전트 로그에 표시해 폴백을 드러낸다

live_fn은 동기 함수(예: k-skill subprocess)여도 된다 — 스레드로 넘겨 실행한다.
"""
import asyncio
from dataclasses import dataclass
from typing import Any, Callable, Optional

from .. import db
from ..config import settings


@dataclass
class ToolResult:
    data: Any
    source: str  # "live" | "cache" | "mock"


async def run_tool(
    name: str,
    mock_fn: Callable[[], Any],
    live_fn: Optional[Callable[[], Any]] = None,
    cache_key: Optional[str] = None,
    cache_ttl: int = db.CACHE_TTL_DEFAULT,
    mode: Optional[str] = None,
) -> ToolResult:
    mode = mode or settings.tool_mode
    key = cache_key or name

    if mode == "mock" or live_fn is None:
        return ToolResult(mock_fn(), "mock")

    if mode == "cache":
        cached = db.cache_get(key)
        if cached is not None:
            return ToolResult(cached, "cache")
        return ToolResult(mock_fn(), "mock")

    # live → cache → mock (3단 폴백)
    try:
        data = await asyncio.to_thread(live_fn)
        db.cache_set(key, data, cache_ttl)
        return ToolResult(data, "live")
    except Exception:
        cached = db.cache_get(key)
        if cached is not None:
            return ToolResult(cached, "cache")
        return ToolResult(mock_fn(), "mock")
