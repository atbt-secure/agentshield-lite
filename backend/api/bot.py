"""ARIA bot API — chat, status, and manual scan endpoints."""
from fastapi import APIRouter
from pydantic import BaseModel

from ..agent.security_agent import aria

router = APIRouter(prefix="/api/bot", tags=["bot"])


class ChatRequest(BaseModel):
    message: str
    history: list = []  # serialized conversation history (passed by client)


@router.get("/status")
async def bot_status():
    """ARIA availability and recent autonomous actions."""
    return aria.status


@router.post("/chat")
async def bot_chat(req: ChatRequest):
    """
    Send a message to ARIA. The client passes the full conversation history
    and receives updated_history back — keeping the backend stateless.
    """
    return await aria.chat(req.message, req.history)


@router.post("/scan")
async def bot_scan():
    """Trigger an immediate autonomous security scan."""
    return await aria.scan()
