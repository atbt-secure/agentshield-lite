"""
In-process event bus for real-time SSE streaming.

When the interceptor processes a request, it publishes an event here.
The SSE endpoint subscribes and forwards events to connected clients.
"""
import asyncio
import json
import logging
from dataclasses import dataclass, asdict
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class LogEvent:
    id: int
    agent_id: str
    tool: str
    action: str
    risk_score: float
    risk_level: str
    risk_flags: list[str]
    policy_decision: str
    blocked: bool
    created_at: str

    def to_sse(self) -> str:
        return f"data: {json.dumps(asdict(self))}\n\n"


class EventBus:
    """Simple pub/sub bus using asyncio Queues, one per subscriber."""

    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue] = set()

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=100)
        self._subscribers.add(q)
        logger.debug("SSE subscriber added (total: %d)", len(self._subscribers))
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        self._subscribers.discard(q)
        logger.debug("SSE subscriber removed (total: %d)", len(self._subscribers))

    def publish(self, event: Any) -> None:
        dead = set()
        for q in self._subscribers:
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                # Slow consumer — drop oldest event, add new one
                try:
                    q.get_nowait()
                    q.put_nowait(event)
                except Exception:
                    dead.add(q)
        for q in dead:
            self._subscribers.discard(q)


# Global singleton
event_bus = EventBus()
