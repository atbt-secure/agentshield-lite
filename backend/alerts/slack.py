import httpx
import logging
from typing import Optional
from ..config import settings

logger = logging.getLogger(__name__)


class SlackAlerter:
    def __init__(self):
        self.webhook_url = settings.slack_webhook_url

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
        if not self.webhook_url:
            logger.debug("Slack webhook not configured, skipping alert")
            return False

        level_emoji = "🔴" if risk_score >= 81 else "🟠" if risk_score >= 61 else "🟡"

        text = message or (
            f"{level_emoji} *AgentShield Alert* — Risk Score: {risk_score:.0f}/100\n"
            f"*Agent:* `{agent_id}`\n"
            f"*Tool:* `{tool}` | *Action:* `{action}`\n"
            f"*Decision:* `{policy_decision.upper()}`\n"
            f"*Flags:* {', '.join(risk_flags) if risk_flags else 'none'}\n"
            f"*Log ID:* #{log_id}"
        )

        payload = {
            "text": text,
            "username": "AgentShield",
            "icon_emoji": ":shield:",
        }

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(self.webhook_url, json=payload, timeout=5.0)
                resp.raise_for_status()
                return True
        except Exception as e:
            logger.error(f"Failed to send Slack alert: {e}")
            return False


slack_alerter = SlackAlerter()
