"""
Simple in-memory rate limiter using a sliding window counter.
No external dependencies — avoids slowapi/redis complexity for v1.

Default limits (overridable via env):
  - /proxy/intercept  : 120 requests / 60 seconds per IP
  - /api/*            : 300 requests / 60 seconds per IP
"""
import time
import logging
from collections import defaultdict, deque
from fastapi import Request, HTTPException, status

logger = logging.getLogger(__name__)


class SlidingWindowRateLimiter:
    def __init__(self, max_requests: int, window_seconds: int):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._buckets: dict[str, deque] = defaultdict(deque)

    def is_allowed(self, key: str) -> bool:
        now = time.monotonic()
        window_start = now - self.window_seconds
        bucket = self._buckets[key]

        # Drop timestamps outside the window
        while bucket and bucket[0] < window_start:
            bucket.popleft()

        if len(bucket) >= self.max_requests:
            return False

        bucket.append(now)
        return True

    def remaining(self, key: str) -> int:
        now = time.monotonic()
        window_start = now - self.window_seconds
        bucket = self._buckets[key]
        while bucket and bucket[0] < window_start:
            bucket.popleft()
        return max(0, self.max_requests - len(bucket))


# Two separate limiters — proxy gets tighter limit than read-only API
proxy_limiter = SlidingWindowRateLimiter(max_requests=120, window_seconds=60)
api_limiter = SlidingWindowRateLimiter(max_requests=300, window_seconds=60)


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


async def proxy_rate_limit(request: Request) -> None:
    ip = _client_ip(request)
    if not proxy_limiter.is_allowed(ip):
        remaining = proxy_limiter.remaining(ip)
        logger.warning("Rate limit exceeded for %s on proxy endpoint", ip)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded. Max {proxy_limiter.max_requests} requests per {proxy_limiter.window_seconds}s.",
            headers={"Retry-After": str(proxy_limiter.window_seconds), "X-RateLimit-Remaining": str(remaining)},
        )


async def api_rate_limit(request: Request) -> None:
    ip = _client_ip(request)
    if not api_limiter.is_allowed(ip):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded. Max {api_limiter.max_requests} requests per {api_limiter.window_seconds}s.",
            headers={"Retry-After": str(api_limiter.window_seconds)},
        )
