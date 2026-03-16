import asyncio
import time
import logging
from typing import Any, Optional
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import AgentLog, Alert
from ..policy.engine import policy_engine
from ..risk.scorer import risk_scorer
from ..alerts.dispatcher import dispatcher
from ..api.metrics import record_intercept
from ..events import event_bus, LogEvent
from ..config import settings

logger = logging.getLogger(__name__)


class InterceptRequest(BaseModel):
    agent_id: str
    session_id: Optional[str] = None
    tool: str
    action: str
    prompt: Optional[str] = None
    tool_input: Optional[Any] = None
    metadata: Optional[dict] = {}


class InterceptResponse(BaseModel):
    allowed: bool
    log_id: int
    risk_score: float
    risk_level: str
    risk_flags: list[str]
    policy_decision: str
    policy_matched: Optional[str]
    message: str


class AgentInterceptor:
    async def intercept(self, req: InterceptRequest, db: AsyncSession) -> InterceptResponse:
        start_time = time.time()

        # 1. Score risk
        risk_result = risk_scorer.score(req.prompt, req.tool, req.action, req.tool_input)

        # 2. Evaluate policy
        decision = await policy_engine.evaluate(db, req.agent_id, req.tool, req.action, req.tool_input)

        # 3. Escalate to alert if critical risk and no explicit block
        if risk_result.score >= 81 and decision.effect == "allow":
            decision.effect = "alert"

        duration_ms = (time.time() - start_time) * 1000

        # 4. Log to DB
        log = AgentLog(
            agent_id=req.agent_id,
            session_id=req.session_id,
            tool=req.tool,
            action=req.action,
            prompt=req.prompt,
            tool_input=req.tool_input,
            risk_score=risk_result.score,
            risk_flags=risk_result.flags,
            policy_decision=decision.effect,
            policy_matched=decision.matched_policy,
            blocked=decision.blocked,
            duration_ms=duration_ms,
            metadata_=req.metadata or {},
        )
        db.add(log)
        await db.flush()

        # 5. Create alert record if needed
        should_alert = risk_result.score >= settings.risk_alert_threshold or decision.blocked
        if should_alert:
            severity = (
                "critical" if risk_result.score >= 81
                else "high" if risk_result.score >= 61
                else "medium"
            )
            alert = Alert(
                log_id=log.id,
                agent_id=req.agent_id,
                alert_type="policy_block" if decision.blocked else "risk_threshold",
                message=f"Agent {req.agent_id} called {req.tool}.{req.action} — score {risk_result.score:.0f}",
                severity=severity,
            )
            db.add(alert)

        await db.commit()

        # 6. Publish to SSE bus (non-blocking)
        event_bus.publish(LogEvent(
            id=log.id,
            agent_id=req.agent_id,
            tool=req.tool,
            action=req.action,
            risk_score=risk_result.score,
            risk_level=risk_result.level,
            risk_flags=risk_result.flags,
            policy_decision=decision.effect,
            blocked=decision.blocked,
            created_at=log.created_at.isoformat() if log.created_at else "",
        ))

        # 7. Record Prometheus metrics
        record_intercept(
            agent_id=req.agent_id,
            tool=req.tool,
            decision=decision.effect,
            blocked=decision.blocked,
            risk_score=risk_result.score,
            duration_ms=duration_ms,
        )

        # 8. Fire-and-forget multi-channel alerts
        if should_alert:
            asyncio.create_task(dispatcher.dispatch(
                agent_id=req.agent_id,
                tool=req.tool,
                action=req.action,
                risk_score=risk_result.score,
                risk_flags=risk_result.flags,
                policy_decision=decision.effect,
                log_id=log.id,
            ))

        allowed = not decision.blocked
        message = (
            f"Action blocked by policy: {decision.matched_policy}" if decision.blocked
            else f"Action allowed (risk: {risk_result.level})"
        )

        logger.info(
            "[%d] %s → %s.%s score=%.0f decision=%s",
            log.id, req.agent_id, req.tool, req.action,
            risk_result.score, decision.effect,
        )

        return InterceptResponse(
            allowed=allowed,
            log_id=log.id,
            risk_score=risk_result.score,
            risk_level=risk_result.level,
            risk_flags=risk_result.flags,
            policy_decision=decision.effect,
            policy_matched=decision.matched_policy,
            message=message,
        )


interceptor = AgentInterceptor()
