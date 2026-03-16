import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models import Agent, AgentLog

router = APIRouter(prefix="/api/agents", tags=["agents"])


# ── Pydantic schemas ──────────────────────────────────────────

class AgentCreate(BaseModel):
    name: str
    description: Optional[str] = None
    tags: Optional[List[str]] = []


class AgentUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    tags: Optional[List[str]] = None
    enabled: Optional[bool] = None


# ── Helpers ───────────────────────────────────────────────────

def _slugify(text: str) -> str:
    """Convert a name to a URL-safe slug."""
    slug = text.lower().strip()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = slug.strip("-")
    return slug or "agent"


def _make_agent_id(name: str) -> str:
    suffix = secrets.token_hex(3)  # 6 hex chars
    return f"{_slugify(name)}-{suffix}"


# ── Routes ────────────────────────────────────────────────────

@router.get("")
async def list_agents(db: AsyncSession = Depends(get_db)):
    """List all registered agents enriched with activity stats."""
    result = await db.execute(select(Agent).order_by(Agent.created_at.desc()))
    agents = result.scalars().all()

    # Bulk-fetch stats from agent_logs
    stats_result = await db.execute(
        select(
            AgentLog.agent_id,
            func.count(AgentLog.id).label("action_count"),
            func.sum(AgentLog.blocked.cast(int)).label("blocked_count"),
            func.avg(AgentLog.risk_score).label("avg_risk_score"),
        ).group_by(AgentLog.agent_id)
    )
    stats_map = {
        row.agent_id: {
            "action_count": row.action_count or 0,
            "blocked_count": int(row.blocked_count or 0),
            "avg_risk_score": round(float(row.avg_risk_score or 0), 1),
        }
        for row in stats_result
    }

    return [
        {
            "id": a.id,
            "agent_id": a.agent_id,
            "name": a.name,
            "description": a.description,
            "enabled": a.enabled,
            "tags": a.tags or [],
            "created_at": a.created_at.isoformat() if a.created_at else None,
            "last_seen_at": a.last_seen_at.isoformat() if a.last_seen_at else None,
            **stats_map.get(a.agent_id, {"action_count": 0, "blocked_count": 0, "avg_risk_score": 0.0}),
        }
        for a in agents
    ]


@router.post("", status_code=201)
async def register_agent(data: AgentCreate, db: AsyncSession = Depends(get_db)):
    """Register a new agent, auto-generating agent_id and api_key."""
    agent_id = _make_agent_id(data.name)
    api_key = secrets.token_hex(32)

    agent = Agent(
        agent_id=agent_id,
        name=data.name,
        description=data.description,
        api_key=api_key,
        tags=data.tags or [],
        enabled=True,
    )
    db.add(agent)
    await db.commit()
    await db.refresh(agent)

    return {
        "id": agent.id,
        "agent_id": agent.agent_id,
        "name": agent.name,
        "description": agent.description,
        "api_key": api_key,  # returned only on creation
        "enabled": agent.enabled,
        "tags": agent.tags or [],
        "created_at": agent.created_at.isoformat() if agent.created_at else None,
    }


@router.get("/{agent_id}")
async def get_agent(agent_id: str, db: AsyncSession = Depends(get_db)):
    """Get a single agent with detailed stats (last 7 days activity, top tools)."""
    result = await db.execute(select(Agent).where(Agent.agent_id == agent_id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    # Overall stats
    stats_result = await db.execute(
        select(
            func.count(AgentLog.id).label("action_count"),
            func.sum(AgentLog.blocked.cast(int)).label("blocked_count"),
            func.avg(AgentLog.risk_score).label("avg_risk_score"),
        ).where(AgentLog.agent_id == agent_id)
    )
    stats_row = stats_result.one()

    # Last 7 days activity
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    activity_result = await db.execute(
        select(
            func.count(AgentLog.id).label("action_count"),
            func.sum(AgentLog.blocked.cast(int)).label("blocked_count"),
        ).where(
            AgentLog.agent_id == agent_id,
            AgentLog.created_at >= cutoff,
        )
    )
    activity_row = activity_result.one()

    # Top tools used
    tools_result = await db.execute(
        select(AgentLog.tool, func.count(AgentLog.id).label("count"))
        .where(AgentLog.agent_id == agent_id)
        .group_by(AgentLog.tool)
        .order_by(func.count(AgentLog.id).desc())
        .limit(5)
    )
    top_tools = [{"tool": row.tool, "count": row.count} for row in tools_result]

    return {
        "id": agent.id,
        "agent_id": agent.agent_id,
        "name": agent.name,
        "description": agent.description,
        "enabled": agent.enabled,
        "tags": agent.tags or [],
        "created_at": agent.created_at.isoformat() if agent.created_at else None,
        "last_seen_at": agent.last_seen_at.isoformat() if agent.last_seen_at else None,
        "stats": {
            "action_count": stats_row.action_count or 0,
            "blocked_count": int(stats_row.blocked_count or 0),
            "avg_risk_score": round(float(stats_row.avg_risk_score or 0), 1),
        },
        "last_7_days": {
            "action_count": activity_row.action_count or 0,
            "blocked_count": int(activity_row.blocked_count or 0),
        },
        "top_tools": top_tools,
    }


@router.patch("/{agent_id}")
async def update_agent(agent_id: str, data: AgentUpdate, db: AsyncSession = Depends(get_db)):
    """Update agent name, description, tags, or enabled status."""
    result = await db.execute(select(Agent).where(Agent.agent_id == agent_id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(agent, key, value)

    await db.commit()
    await db.refresh(agent)

    return {
        "id": agent.id,
        "agent_id": agent.agent_id,
        "name": agent.name,
        "description": agent.description,
        "enabled": agent.enabled,
        "tags": agent.tags or [],
    }


@router.delete("/{agent_id}", status_code=204)
async def delete_agent(agent_id: str, db: AsyncSession = Depends(get_db)):
    """Hard-delete an agent record."""
    result = await db.execute(select(Agent).where(Agent.agent_id == agent_id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    await db.delete(agent)
    await db.commit()


@router.post("/{agent_id}/rotate-key")
async def rotate_api_key(agent_id: str, db: AsyncSession = Depends(get_db)):
    """Generate a new api_key for the agent and return it."""
    result = await db.execute(select(Agent).where(Agent.agent_id == agent_id))
    agent = result.scalar_one_or_none()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    new_key = secrets.token_hex(32)
    agent.api_key = new_key
    await db.commit()

    return {"agent_id": agent.agent_id, "api_key": new_key}
