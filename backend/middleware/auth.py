from fastapi import Security, HTTPException, status
from fastapi.security.api_key import APIKeyHeader
from ..config import settings

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def require_api_key(api_key: str | None = Security(_api_key_header)) -> None:
    """
    FastAPI dependency for API key authentication.
    Skipped entirely when API_KEY env var is not set (open/dev mode).
    """
    if not settings.api_key:
        return  # Auth disabled — open mode
    if api_key != settings.api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key. Set X-API-Key header.",
        )
