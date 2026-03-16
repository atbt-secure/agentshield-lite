from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, func
from typing import Optional
from ..database import get_db
from ..models import AgentLog

router = APIRouter(prefix="/api/logs", tags=["logs"])


@router.get("")
async def list_logs(
    agent_id: Optional[str] = None,
    tool: Optional[str] = None,
    blocked: Optional[bool] = None,
    min_risk: Optional[float] = None,
    limit: int = Query(50, le=500),
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    query = select(AgentLog).order_by(desc(AgentLog.created_at))
    if agent_id:
        query = query.where(AgentLog.agent_id == agent_id)
    if tool:
        query = query.where(AgentLog.tool.ilike(f"%{tool}%"))
    if blocked is not None:
        query = query.where(AgentLog.blocked == blocked)
    if min_risk is not None:
        query = query.where(AgentLog.risk_score >= min_risk)

    count_query = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_query)).scalar()

    result = await db.execute(query.limit(limit).offset(offset))
    logs = result.scalars().all()

    return {
        "total": total,
        "offset": offset,
        "limit": limit,
        "items": [
            {
                "id": l.id,
                "agent_id": l.agent_id,
                "session_id": l.session_id,
                "tool": l.tool,
                "action": l.action,
                "risk_score": l.risk_score,
                "risk_flags": l.risk_flags,
                "policy_decision": l.policy_decision,
                "policy_matched": l.policy_matched,
                "blocked": l.blocked,
                "duration_ms": l.duration_ms,
                "created_at": l.created_at.isoformat() if l.created_at else None,
            }
            for l in logs
        ],
    }


@router.get("/{log_id}")
async def get_log(log_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(AgentLog).where(AgentLog.id == log_id))
    log = result.scalar_one_or_none()
    if not log:
        raise HTTPException(status_code=404, detail="Log not found")
    return {
        "id": log.id,
        "agent_id": log.agent_id,
        "session_id": log.session_id,
        "tool": log.tool,
        "action": log.action,
        "prompt": log.prompt,
        "tool_input": log.tool_input,
        "tool_output": log.tool_output,
        "risk_score": log.risk_score,
        "risk_flags": log.risk_flags,
        "policy_decision": log.policy_decision,
        "policy_matched": log.policy_matched,
        "blocked": log.blocked,
        "duration_ms": log.duration_ms,
        "metadata": log.metadata_,
        "created_at": log.created_at.isoformat() if log.created_at else None,
    }
