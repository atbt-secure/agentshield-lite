"""Generic HTTP webhook alert — POST JSON payload to any URL."""
import httpx
import logging
from typing import Optional
from ..config import settings

logger = logging.getLogger(__name__)


class WebhookAlerter:
    async def send_alert(
        self,
        agent_id: str,
        tool: str,
        action: str,
        risk_score: float,
        risk_flags: list[str],
        policy_decision: str,
        log_id: int,
        message: Optional[str] = None,
    ) -> bool:
        urls = settings.webhook_urls
        if not urls:
            return False

        payload = {
            "source": "agentshield",
            "log_id": log_id,
            "agent_id": agent_id,
            "tool": tool,
            "action": action,
            "risk_score": risk_score,
            "risk_level": (
                "critical" if risk_score >= 81
                else "high" if risk_score >= 61
                else "medium"
            ),
            "risk_flags": risk_flags,
            "policy_decision": policy_decision,
            "message": message or f"Agent {agent_id} called {tool}.{action} — score {risk_score:.0f}",
        }

        sent = 0
        async with httpx.AsyncClient() as client:
            for url in urls:
                try:
                    resp = await client.post(url.strip(), json=payload, timeout=5.0)
                    resp.raise_for_status()
                    sent += 1
                except Exception as e:
                    logger.error("Webhook alert to %s failed: %s", url, e)

        return sent > 0


webhook_alerter = WebhookAlerter()
