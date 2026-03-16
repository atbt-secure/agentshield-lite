"""
Alert dispatcher — fan-out to all configured channels simultaneously.

Channels (each enabled only when its env var is set):
  - Slack        (SLACK_WEBHOOK_URL)
  - Microsoft Teams (TEAMS_WEBHOOK_URL)
  - Email        (SMTP_HOST + ALERT_EMAIL_TO)
  - Webhook      (WEBHOOK_URLS — comma-separated list)
"""
import asyncio
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class AlertDispatcher:
    async def dispatch(
        self,
        agent_id: str,
        tool: str,
        action: str,
        risk_score: float,
        risk_flags: list[str],
        policy_decision: str,
        log_id: int,
        message: Optional[str] = None,
    ) -> None:
        from .slack import slack_alerter
        from .teams import teams_alerter
        from .email import email_alerter
        from .webhook import webhook_alerter

        kwargs = dict(
            agent_id=agent_id,
            tool=tool,
            action=action,
            risk_score=risk_score,
            risk_flags=risk_flags,
            policy_decision=policy_decision,
            log_id=log_id,
            message=message,
        )

        results = await asyncio.gather(
            slack_alerter.send_alert(**kwargs),
            teams_alerter.send_alert(**kwargs),
            email_alerter.send_alert(**kwargs),
            webhook_alerter.send_alert(**kwargs),
            return_exceptions=True,
        )

        channels = ["slack", "teams", "email", "webhook"]
        for channel, result in zip(channels, results):
            if isinstance(result, Exception):
                logger.error("Alert channel %s raised: %s", channel, result)
            elif result:
                logger.debug("Alert sent via %s", channel)


dispatcher = AlertDispatcher()
