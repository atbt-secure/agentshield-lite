"""Async SMTP email alerts using aiosmtplib."""
import logging
from typing import Optional
from ..config import settings

logger = logging.getLogger(__name__)


class EmailAlerter:
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
        if not settings.smtp_host or not settings.alert_email_to:
            return False

        try:
            import aiosmtplib
            from email.mime.text import MIMEText
            from email.mime.multipart import MIMEMultipart
        except ImportError:
            logger.warning("aiosmtplib not installed — email alerts disabled. pip install aiosmtplib")
            return False

        level = (
            "CRITICAL" if risk_score >= 81
            else "HIGH" if risk_score >= 61
            else "MEDIUM"
        )

        subject = f"[AgentShield {level}] {agent_id} → {tool}.{action} (score {risk_score:.0f})"
        body = f"""AgentShield Security Alert
{'=' * 50}

Agent ID   : {agent_id}
Tool       : {tool}.{action}
Risk Score : {risk_score:.0f}/100  ({level})
Decision   : {policy_decision.upper()}
Flags      : {', '.join(risk_flags) or 'none'}
Log ID     : #{log_id}

{message or ''}

View full details at your AgentShield dashboard.
"""

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = settings.smtp_from or settings.smtp_user or "agentshield@localhost"
        msg["To"] = settings.alert_email_to
        msg.attach(MIMEText(body, "plain"))

        try:
            await aiosmtplib.send(
                msg,
                hostname=settings.smtp_host,
                port=settings.smtp_port,
                username=settings.smtp_user or None,
                password=settings.smtp_password or None,
                use_tls=settings.smtp_tls,
                timeout=10,
            )
            logger.info("Email alert sent to %s", settings.alert_email_to)
            return True
        except Exception as e:
            logger.error("Email alert failed: %s", e)
            return False


email_alerter = EmailAlerter()
