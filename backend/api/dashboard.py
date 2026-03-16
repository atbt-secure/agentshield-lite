from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc
from datetime import datetime, timedelta, timezone
from ..database import get_db
from ..models import AgentLog, Alert

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/stats")
async def get_stats(db: AsyncSession = Depends(get_db)):
    now = datetime.now(timezone.utc)
    last_24h = now - timedelta(hours=24)

    total = (await db.execute(select(func.count(AgentLog.id)))).scalar()
    blocked = (await db.execute(
        select(func.count(AgentLog.id)).where(AgentLog.blocked == True)
    )).scalar()
    high_risk = (await db.execute(
        select(func.count(AgentLog.id)).where(AgentLog.risk_score >= 61)
    )).scalar()
    last_24h_count = (await db.execute(
        select(func.count(AgentLog.id)).where(AgentLog.created_at >= last_24h)
    )).scalar()
    avg_risk = (await db.execute(select(func.avg(AgentLog.risk_score)))).scalar() or 0
    unique_agents = (await db.execute(
        select(func.count(func.distinct(AgentLog.agent_id)))
    )).scalar()
    unack_alerts = (await db.execute(
        select(func.count(Alert.id)).where(Alert.acknowledged == False)
    )).scalar()

    return {
        "total_actions": total,
        "blocked_actions": blocked,
        "high_risk_actions": high_risk,
        "actions_last_24h": last_24h_count,
        "avg_risk_score": round(float(avg_risk), 1),
        "unique_agents": unique_agents,
        "unacknowledged_alerts": unack_alerts,
        "block_rate": round(blocked / total * 100, 1) if total else 0,
    }


@router.get("/timeline")
async def get_timeline(hours: int = 24, db: AsyncSession = Depends(get_db)):
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    result = await db.execute(
        select(AgentLog)
        .where(AgentLog.created_at >= since)
        .order_by(AgentLog.created_at)
        .limit(500)
    )
    logs = result.scalars().all()
    return [
        {
            "id": l.id,
            "agent_id": l.agent_id,
            "tool": l.tool,
            "action": l.action,
            "risk_score": l.risk_score,
            "blocked": l.blocked,
            "policy_decision": l.policy_decision,
            "created_at": l.created_at.isoformat() if l.created_at else None,
        }
        for l in logs
    ]


@router.get("/alerts")
async def get_alerts(
    acknowledged: bool = False,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Alert)
        .where(Alert.acknowledged == acknowledged)
        .order_by(desc(Alert.created_at))
        .limit(limit)
    )
    alerts = result.scalars().all()
    return [
        {
            "id": a.id,
            "log_id": a.log_id,
            "agent_id": a.agent_id,
            "alert_type": a.alert_type,
            "message": a.message,
            "severity": a.severity,
            "acknowledged": a.acknowledged,
            "created_at": a.created_at.isoformat() if a.created_at else None,
        }
        for a in alerts
    ]


@router.post("/alerts/{alert_id}/acknowledge")
async def acknowledge_alert(alert_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Alert).where(Alert.id == alert_id))
    alert = result.scalar_one_or_none()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    alert.acknowledged = True
    await db.commit()
    return {"acknowledged": True}


@router.get("/top-agents")
async def top_agents(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(
            AgentLog.agent_id,
            func.count(AgentLog.id).label("count"),
            func.avg(AgentLog.risk_score).label("avg_risk"),
        )
        .group_by(AgentLog.agent_id)
        .order_by(desc("count"))
        .limit(10)
    )
    rows = result.all()
    return [
        {
            "agent_id": r[0],
            "action_count": r[1],
            "avg_risk_score": round(float(r[2] or 0), 1),
        }
        for r in rows
    ]
