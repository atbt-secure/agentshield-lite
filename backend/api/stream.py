"""
Server-Sent Events (SSE) endpoint for real-time dashboard updates.

Clients connect to GET /api/stream/events and receive a live feed of
every agent action as it is intercepted — no polling needed.

Event format:
  data: {"id": 42, "agent_id": "...", "tool": "database", "action": "query",
         "risk_score": 15.0, "risk_level": "low", "risk_flags": [],
         "policy_decision": "allow", "blocked": false, "created_at": "..."}

Usage (JavaScript):
  const es = new EventSource('/api/stream/events');
  es.onmessage = (e) => console.log(JSON.parse(e.data));
"""
import asyncio
import logging
from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from ..events import event_bus

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/stream", tags=["stream"])


async def _event_generator(queue: asyncio.Queue):
    """Yield SSE-formatted events from the subscriber queue."""
    # Send a heartbeat comment every 15s to keep the connection alive
    HEARTBEAT_INTERVAL = 15.0
    try:
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), timeout=HEARTBEAT_INTERVAL)
                yield event.to_sse()
            except asyncio.TimeoutError:
                yield ": heartbeat\n\n"  # SSE comment — keeps proxy connections alive
    except asyncio.CancelledError:
        pass
    finally:
        event_bus.unsubscribe(queue)
        logger.debug("SSE client disconnected")


@router.get("/events")
async def stream_events():
    """
    Live SSE feed of agent actions.
    Connect with EventSource in the browser or curl:
      curl -N http://localhost:8000/api/stream/events
    """
    queue = event_bus.subscribe()
    return StreamingResponse(
        _event_generator(queue),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # disable nginx buffering
            "Connection": "keep-alive",
        },
    )
