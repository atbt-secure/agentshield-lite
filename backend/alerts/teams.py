"""Microsoft Teams webhook alert via Adaptive Cards."""
import httpx
import logging
from typing import Optional
from ..config import settings

logger = logging.getLogger(__name__)


class TeamsAlerter:
    def __init__(self):
        self.webhook_url = settings.teams_webhook_url

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
            return False

        color = (
            "attention" if risk_score >= 81
            else "warning" if risk_score >= 61
            else "good"
        )

        card = {
            "type": "message",
            "attachments": [{
                "contentType": "application/vnd.microsoft.card.adaptive",
                "content": {
                    "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                    "type": "AdaptiveCard",
                    "version": "1.4",
                    "body": [
                        {
                            "type": "TextBlock",
                            "text": "🛡️ AgentShield Alert",
                            "weight": "bolder",
                            "size": "medium",
                            "color": color,
                        },
                        {
                            "type": "FactSet",
                            "facts": [
                                {"title": "Agent", "value": agent_id},
                                {"title": "Tool", "value": f"{tool}.{action}"},
                                {"title": "Risk Score", "value": f"{risk_score:.0f}/100"},
                                {"title": "Decision", "value": policy_decision.upper()},
                                {"title": "Flags", "value": ", ".join(risk_flags) or "none"},
                                {"title": "Log ID", "value": f"#{log_id}"},
                            ],
                        },
                    ],
                },
            }],
        }

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(self.webhook_url, json=card, timeout=5.0)
                resp.raise_for_status()
                return True
        except Exception as e:
            logger.error("Teams alert failed: %s", e)
            return False


teams_alerter = TeamsAlerter()
