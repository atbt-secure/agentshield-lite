import functools
import inspect
from typing import Optional, Callable
from .client import AgentShieldClient

_default_client: Optional[AgentShieldClient] = None


def configure(client: AgentShieldClient):
    """Set the global AgentShield client used by the @shield decorator."""
    global _default_client
    _default_client = client


def shield(
    tool: str,
    action: Optional[str] = None,
    client: Optional[AgentShieldClient] = None,
):
    """
    Decorator to automatically intercept function calls through AgentShield.

    Usage:
        @shield(tool="database", action="query")
        async def query_database(prompt: str, query: str):
            ...

    The decorator reads `prompt` from kwargs or the first positional argument.
    All kwargs are forwarded as tool_input to the interceptor.
    """
    def decorator(func: Callable) -> Callable:
        effective_action = action or func.__name__

        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            c = client or _default_client
            if c:
                prompt = kwargs.get("prompt") or (args[0] if args else None)
                await c.intercept(
                    tool=tool,
                    action=effective_action,
                    prompt=str(prompt) if prompt else None,
                    tool_input=kwargs,
                )
            return await func(*args, **kwargs)

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            c = client or _default_client
            if c:
                prompt = kwargs.get("prompt") or (args[0] if args else None)
                c.intercept_sync(
                    tool=tool,
                    action=effective_action,
                    prompt=str(prompt) if prompt else None,
                    tool_input=kwargs,
                )
            return func(*args, **kwargs)

        if inspect.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator
