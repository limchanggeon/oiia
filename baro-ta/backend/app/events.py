"""세션별 SSE 이벤트 브로커 (in-mem).

프론트(Next.js/React)는 GET /api/stream/{session_id} 로 구독한다.
세션 ID를 쓰지 않는 클라이언트는 "public" 채널을 구독하면 된다.
이벤트 형식: {"type": "agent", "tag": "...", "msg": "..."} 등 JSON 한 줄.
"""
import asyncio
from collections import defaultdict
from typing import Dict, Set


class EventBroker:
    def __init__(self) -> None:
        self._queues: Dict[str, Set["asyncio.Queue"]] = defaultdict(set)

    def subscribe(self, session_id: str) -> "asyncio.Queue":
        q: "asyncio.Queue" = asyncio.Queue(maxsize=256)
        self._queues[session_id].add(q)
        return q

    def unsubscribe(self, session_id: str, q: "asyncio.Queue") -> None:
        self._queues[session_id].discard(q)
        if not self._queues[session_id]:
            self._queues.pop(session_id, None)

    def publish(self, session_id: str, event: dict) -> None:
        for q in list(self._queues.get(session_id, ())):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                pass  # 느린 구독자는 이벤트를 잃는다 (데모 허용)


broker = EventBroker()
