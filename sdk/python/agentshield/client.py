import httpx
import logging
from typing import Any, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class ShieldResult:
    allowed: bool
    log_id: int
    risk_score: float
    risk_level: str
    risk_flags: list[str]
    policy_decision: str
    policy_matched: Optional[str]
    message: str


class AgentShieldClient:
    """
    Client for AgentShield proxy server.

    Usage:
        shield = AgentShieldClient(
            base_url="http://localhost:8000",
            agent_id="my-agent-v1",
        )

        result = await shield.intercept(
            tool="database",
            action="query",
            prompt="user request...",
            tool_input={"query": "SELECT * FROM users"},
        )

        if not result.allowed:
            raise PermissionError(result.message)
    """

    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        agent_id: str = "default-agent",
        session_id: Optional[str] = None,
        api_key: Optional[str] = None,
        raise_on_block: bool = True,
    ):
        self.base_url = base_url.rstrip("/")
        self.agent_id = agent_id
        self.session_id = session_id
        self.raise_on_block = raise_on_block
        self._headers = {"Content-Type": "application/json"}
        if api_key:
            self._headers["X-API-Key"] = api_key

    async def intercept(
        self,
        tool: str,
        action: str,
        prompt: Optional[str] = None,
        tool_input: Optional[Any] = None,
        metadata: Optional[dict] = None,
    ) -> ShieldResult:
        payload = {
            "agent_id": self.agent_id,
            "session_id": self.session_id,
            "tool": tool,
            "action": action,
            "prompt": prompt,
            "tool_input": tool_input,
            "metadata": metadata or {},
        }

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.base_url}/proxy/intercept",
                json=payload,
                headers=self._headers,
                timeout=5.0,
            )
            resp.raise_for_status()
            data = resp.json()

        result = ShieldResult(**data)

        if not result.allowed and self.raise_on_block:
            raise PermissionError(f"AgentShield blocked action: {result.message}")

        return result

    def intercept_sync(
        self,
        tool: str,
        action: str,
        prompt: Optional[str] = None,
        tool_input: Optional[Any] = None,
        metadata: Optional[dict] = None,
    ) -> ShieldResult:
        """Synchronous version for non-async code."""
        import asyncio
        loop = asyncio.get_event_loop()
        return loop.run_until_complete(
            self.intercept(tool, action, prompt, tool_input, metadata)
        )
