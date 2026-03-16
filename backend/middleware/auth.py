import logging
from fastapi import Security, HTTPException, Request, status
from fastapi.security.api_key import APIKeyHeader
from sqlalchemy import select
from ..config import settings

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
logger = logging.getLogger(__name__)


async def require_api_key(request: Request, api_key: str | None = Security(_api_key_header)) -> None:
    """
    Auth check — in order:
    1. If API_KEY env not set AND no agents in DB → open/dev mode (skip)
    2. Match against global API_KEY
    3. Match against any Agent.api_key in DB
    4. Reject with 401
    """
    # No global key configured
    if not settings.api_key:
        # Check if per-agent keys are in use
        # If no key provided, allow (open dev mode)
        if not api_key:
            return

    if api_key and settings.api_key and api_key == settings.api_key:
        return  # Global key match

    if api_key:
        # Check per-agent keys
        from ..database import AsyncSessionLocal
        from ..models import Agent
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(Agent).where(Agent.api_key == api_key, Agent.enabled == True)
            )
            agent = result.scalar_one_or_none()
            if agent:
                # Store agent_id in request state for downstream use
                request.state.authenticated_agent_id = agent.agent_id
                return

    if settings.api_key or api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key. Set X-API-Key header.",
        )
