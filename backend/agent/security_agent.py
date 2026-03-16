"""
ARIA — Autonomous Risk Intelligence Agent
==========================================
Uses Claude with tool use to monitor security, detect gaps, and apply safe fixes.
"""
import asyncio
import json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import anthropic
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..database import AsyncSessionLocal
from ..models import Agent, AgentLog, Alert, Policy

logger = logging.getLogger(__name__)


# ── System prompt ──────────────────────────────────────────────────────────────

ARIA_SYSTEM = """You are ARIA (Autonomous Risk Intelligence Agent), AgentShield's built-in security analyst.

Your role: Monitor AI agent behavior, detect threats, close policy gaps, apply safe fixes, and communicate findings clearly.

Personality: Direct, concise, security-focused. Lead with the most critical finding.
Use emojis for quick scanning: 🔴 critical · 🟠 high · 🟡 medium · 🟢 safe · ✅ ok · ⚠️ warning · 🔧 fix applied · 📊 data

When analyzing: Look for patterns, not just isolated events. Think like a security analyst.
When fixing: Be transparent — explain what you did and why. Never silently disable agents.
When reporting: Be concise. Focus on what needs action. If everything looks good, say so clearly.

Important limits:
- You CAN automatically: acknowledge low-severity old alerts, create blocking policies for clear threats
- You CANNOT automatically: disable agents (always propose and explain), delete data
- When unsure: ask the user before acting"""


# ── Tool definitions ───────────────────────────────────────────────────────────

TOOLS = [
    {
        "name": "get_security_summary",
        "description": "Get current security status: total actions, blocked count, risk distribution, unacknowledged alerts, and top risky agents over a time window.",
        "input_schema": {
            "type": "object",
            "properties": {
                "hours": {
                    "type": "integer",
                    "description": "Lookback window in hours (default 24)",
                    "default": 24,
                }
            },
        },
    },
    {
        "name": "get_policy_gaps",
        "description": "Find tool+action pairs with high average risk scores but no blocking policy — coverage gaps that should be closed.",
        "input_schema": {
            "type": "object",
            "properties": {
                "min_risk_score": {
                    "type": "integer",
                    "description": "Minimum average risk score to flag (default 60)",
                    "default": 60,
                },
                "min_occurrences": {
                    "type": "integer",
                    "description": "Minimum occurrences before flagging (default 2)",
                    "default": 2,
                },
            },
        },
    },
    {
        "name": "get_recent_alerts",
        "description": "Get unacknowledged security alerts, optionally filtered by severity.",
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Max alerts to return (default 10)", "default": 10},
                "severity": {
                    "type": "string",
                    "description": "Filter by severity: critical, high, medium, low — omit for all",
                },
            },
        },
    },
    {
        "name": "create_policy",
        "description": "Create a blocking or alerting policy to close a security gap.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Human-readable policy name"},
                "tool": {"type": "string", "description": "Tool to match (* for any)"},
                "action": {"type": "string", "description": "Action to match (* for any)"},
                "effect": {"type": "string", "enum": ["block", "alert"], "description": "Effect to apply"},
                "priority": {
                    "type": "integer",
                    "description": "Enforcement priority — lower = higher (default 50)",
                    "default": 50,
                },
                "description": {
                    "type": "string",
                    "description": "Why this policy was created (audit trail)",
                },
            },
            "required": ["name", "tool", "action", "effect"],
        },
    },
    {
        "name": "acknowledge_alerts",
        "description": "Batch-acknowledge low-severity alerts older than N hours to reduce noise.",
        "input_schema": {
            "type": "object",
            "properties": {
                "hours_old": {
                    "type": "integer",
                    "description": "Only acknowledge alerts older than this many hours (default 4)",
                    "default": 4,
                },
                "severity": {
                    "type": "string",
                    "enum": ["low"],
                    "description": "Only acknowledge this severity level (default low)",
                    "default": "low",
                },
            },
        },
    },
    {
        "name": "get_agent_profiles",
        "description": "Get risk profiles for all agents (or a specific one) — total actions, avg/max risk, block rate.",
        "input_schema": {
            "type": "object",
            "properties": {
                "agent_id": {
                    "type": "string",
                    "description": "Specific agent ID — omit for all agents",
                },
            },
        },
    },
]


# ── Tool implementations ───────────────────────────────────────────────────────

async def _tool_security_summary(inp: dict, db: AsyncSession) -> str:
    hours = inp.get("hours", 24)
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

    total = await db.scalar(select(func.count(AgentLog.id)).where(AgentLog.created_at >= cutoff)) or 0
    blocked = await db.scalar(
        select(func.count(AgentLog.id)).where(AgentLog.created_at >= cutoff, AgentLog.blocked == True)
    ) or 0
    high_risk = await db.scalar(
        select(func.count(AgentLog.id)).where(AgentLog.created_at >= cutoff, AgentLog.risk_score >= 61)
    ) or 0
    critical = await db.scalar(
        select(func.count(AgentLog.id)).where(AgentLog.created_at >= cutoff, AgentLog.risk_score >= 81)
    ) or 0
    avg_risk = round(
        float(await db.scalar(select(func.avg(AgentLog.risk_score)).where(AgentLog.created_at >= cutoff)) or 0), 1
    )
    unack = await db.scalar(select(func.count(Alert.id)).where(Alert.acknowledged == False)) or 0

    top_result = await db.execute(
        select(
            AgentLog.agent_id,
            func.avg(AgentLog.risk_score).label("avg_risk"),
            func.count(AgentLog.id).label("count"),
        )
        .where(AgentLog.created_at >= cutoff)
        .group_by(AgentLog.agent_id)
        .order_by(func.avg(AgentLog.risk_score).desc())
        .limit(5)
    )
    top_agents = [
        {"agent_id": r.agent_id, "avg_risk": round(float(r.avg_risk), 1), "count": r.count}
        for r in top_result
    ]

    return json.dumps({
        "period_hours": hours,
        "total_actions": total,
        "blocked_actions": blocked,
        "block_rate_pct": round(blocked / total * 100, 1) if total else 0,
        "high_risk_actions": high_risk,
        "critical_actions": critical,
        "avg_risk_score": avg_risk,
        "unacknowledged_alerts": unack,
        "top_risky_agents": top_agents,
    })


async def _tool_policy_gaps(inp: dict, db: AsyncSession) -> str:
    min_risk = inp.get("min_risk_score", 60)
    min_occ = inp.get("min_occurrences", 2)

    policies_result = await db.execute(
        select(Policy.tool, Policy.action).where(Policy.effect == "block", Policy.enabled == True)
    )
    blocked_patterns = {(r.tool, r.action) for r in policies_result}

    gaps_result = await db.execute(
        select(
            AgentLog.tool,
            AgentLog.action,
            func.avg(AgentLog.risk_score).label("avg_risk"),
            func.count(AgentLog.id).label("occurrences"),
            func.max(AgentLog.risk_score).label("max_risk"),
        )
        .group_by(AgentLog.tool, AgentLog.action)
        .having(
            func.avg(AgentLog.risk_score) >= min_risk,
            func.count(AgentLog.id) >= min_occ,
        )
        .order_by(func.avg(AgentLog.risk_score).desc())
        .limit(10)
    )

    gaps = []
    for r in gaps_result:
        is_covered = (
            (r.tool, r.action) in blocked_patterns
            or (r.tool, "*") in blocked_patterns
            or ("*", r.action) in blocked_patterns
            or ("*", "*") in blocked_patterns
        )
        if not is_covered:
            gaps.append({
                "tool": r.tool,
                "action": r.action,
                "avg_risk_score": round(float(r.avg_risk), 1),
                "max_risk_score": round(float(r.max_risk), 1),
                "occurrences": r.occurrences,
            })

    return json.dumps({"gaps": gaps, "total_gaps": len(gaps)})


async def _tool_recent_alerts(inp: dict, db: AsyncSession) -> str:
    limit = inp.get("limit", 10)
    severity = inp.get("severity")
    q = (
        select(Alert)
        .where(Alert.acknowledged == False)
        .order_by(Alert.created_at.desc())
        .limit(limit)
    )
    if severity:
        q = q.where(Alert.severity == severity)
    result = await db.execute(q)
    alerts = result.scalars().all()
    return json.dumps([
        {
            "id": a.id,
            "agent_id": a.agent_id,
            "message": a.message,
            "severity": a.severity,
            "alert_type": a.alert_type,
            "created_at": a.created_at.isoformat() if a.created_at else None,
        }
        for a in alerts
    ])


async def _tool_create_policy(inp: dict, db: AsyncSession, recent_actions: list) -> str:
    policy = Policy(
        name=inp["name"],
        description=inp.get(
            "description",
            f"Auto-created by ARIA at {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')} UTC",
        ),
        tool=inp.get("tool", "*"),
        action=inp.get("action", "*"),
        effect=inp["effect"],
        priority=inp.get("priority", 50),
        enabled=True,
    )
    db.add(policy)
    await db.commit()
    await db.refresh(policy)

    recent_actions.append({
        "type": "policy_created",
        "policy_id": policy.id,
        "name": policy.name,
        "tool": policy.tool,
        "action": policy.action,
        "effect": policy.effect,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    if len(recent_actions) > 20:
        recent_actions.pop(0)

    return json.dumps({"success": True, "policy_id": policy.id, "message": f"Policy '{policy.name}' created"})


async def _tool_acknowledge_alerts(inp: dict, db: AsyncSession, recent_actions: list) -> str:
    hours_old = inp.get("hours_old", 4)
    severity = inp.get("severity", "low")
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours_old)

    result = await db.execute(
        update(Alert)
        .where(
            Alert.acknowledged == False,
            Alert.severity == severity,
            Alert.created_at <= cutoff,
        )
        .values(acknowledged=True)
        .returning(Alert.id)
    )
    ack_ids = [r[0] for r in result.fetchall()]
    await db.commit()

    if ack_ids:
        recent_actions.append({
            "type": "alerts_acknowledged",
            "count": len(ack_ids),
            "severity": severity,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        if len(recent_actions) > 20:
            recent_actions.pop(0)

    return json.dumps({"acknowledged_count": len(ack_ids), "alert_ids": ack_ids})


async def _tool_agent_profiles(inp: dict, db: AsyncSession) -> str:
    agent_id = inp.get("agent_id")
    q = (
        select(
            AgentLog.agent_id,
            func.count(AgentLog.id).label("total_actions"),
            func.avg(AgentLog.risk_score).label("avg_risk"),
            func.max(AgentLog.risk_score).label("max_risk"),
            func.sum(AgentLog.blocked.cast(int)).label("blocked_count"),
        )
        .group_by(AgentLog.agent_id)
        .order_by(func.avg(AgentLog.risk_score).desc())
    )
    if agent_id:
        q = q.where(AgentLog.agent_id == agent_id)
    result = await db.execute(q)
    profiles = [
        {
            "agent_id": r.agent_id,
            "total_actions": r.total_actions,
            "avg_risk_score": round(float(r.avg_risk), 1),
            "max_risk_score": round(float(r.max_risk), 1),
            "blocked_count": int(r.blocked_count or 0),
            "block_rate_pct": round(int(r.blocked_count or 0) / r.total_actions * 100, 1),
        }
        for r in result
    ]
    return json.dumps({"agents": profiles})


# ── ARIA Agent class ───────────────────────────────────────────────────────────

class ARIAAgent:
    """Autonomous Risk Intelligence Agent — Claude-powered security analyst."""

    def __init__(self):
        self._client: Optional[anthropic.AsyncAnthropic] = None
        self._background_task: Optional[asyncio.Task] = None
        self._last_scan_at: Optional[datetime] = None
        self._recent_actions: list[dict] = []
        self._available = False  # becomes True once ANTHROPIC_API_KEY confirmed

    def _get_client(self) -> Optional[anthropic.AsyncAnthropic]:
        api_key = settings.anthropic_api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            return None
        if not self._client:
            self._client = anthropic.AsyncAnthropic(api_key=api_key)
            self._available = True
        return self._client

    async def _execute_tool(self, tool_name: str, tool_input: dict, db: AsyncSession) -> str:
        try:
            if tool_name == "get_security_summary":
                return await _tool_security_summary(tool_input, db)
            elif tool_name == "get_policy_gaps":
                return await _tool_policy_gaps(tool_input, db)
            elif tool_name == "get_recent_alerts":
                return await _tool_recent_alerts(tool_input, db)
            elif tool_name == "create_policy":
                return await _tool_create_policy(tool_input, db, self._recent_actions)
            elif tool_name == "acknowledge_alerts":
                return await _tool_acknowledge_alerts(tool_input, db, self._recent_actions)
            elif tool_name == "get_agent_profiles":
                return await _tool_agent_profiles(tool_input, db)
            else:
                return json.dumps({"error": f"Unknown tool: {tool_name}"})
        except Exception as e:
            logger.error("ARIA tool %s error: %s", tool_name, e, exc_info=True)
            return json.dumps({"error": str(e)})

    # ── Public API ─────────────────────────────────────────────────────────────

    async def chat(self, user_message: str, history: list[dict]) -> dict:
        """
        Process a user message with conversation history.
        Returns: {reply, actions_taken, updated_history, available}
        """
        client = self._get_client()
        if not client:
            return {
                "reply": "⚠️ ARIA requires an `ANTHROPIC_API_KEY` to be configured. Add it to your `.env` file to enable autonomous monitoring.",
                "actions_taken": [],
                "updated_history": history,
                "available": False,
            }

        messages = list(history) + [{"role": "user", "content": user_message}]
        actions_taken = []

        async with AsyncSessionLocal() as db:
            while True:
                response = await client.messages.create(
                    model="claude-opus-4-6",
                    max_tokens=1024,
                    thinking={"type": "adaptive"},
                    system=ARIA_SYSTEM,
                    tools=TOOLS,
                    messages=messages,
                )

                if response.stop_reason == "end_turn":
                    # Extract text (skip thinking blocks)
                    text = next(
                        (b.text for b in response.content if hasattr(b, "text") and b.type == "text"),
                        "I'm processing your request.",
                    )
                    # Serialize content for history (strip thinking blocks — they shouldn't be re-sent)
                    serializable = [
                        {"type": "text", "text": b.text}
                        for b in response.content
                        if hasattr(b, "text") and b.type == "text"
                    ]
                    return {
                        "reply": text,
                        "actions_taken": actions_taken,
                        "updated_history": messages + [{"role": "assistant", "content": serializable}],
                        "available": True,
                    }

                if response.stop_reason == "tool_use":
                    # Serialize assistant message (strip thinking blocks for history)
                    assistant_content = []
                    for b in response.content:
                        if b.type == "tool_use":
                            assistant_content.append({
                                "type": "tool_use",
                                "id": b.id,
                                "name": b.name,
                                "input": b.input,
                            })
                        elif b.type == "text" and b.text:
                            assistant_content.append({"type": "text", "text": b.text})

                    messages.append({"role": "assistant", "content": assistant_content})

                    tool_results = []
                    for b in response.content:
                        if b.type == "tool_use":
                            result = await self._execute_tool(b.name, b.input, db)
                            tool_results.append({
                                "type": "tool_result",
                                "tool_use_id": b.id,
                                "content": result,
                            })
                            if b.name in ("create_policy", "acknowledge_alerts"):
                                actions_taken.append({"tool": b.name, "input": b.input})

                    messages.append({"role": "user", "content": tool_results})
                else:
                    break

        return {
            "reply": "I encountered an unexpected issue. Please try again.",
            "actions_taken": [],
            "updated_history": history,
            "available": True,
        }

    async def scan(self) -> dict:
        """Run an autonomous security scan."""
        result = await self.chat(
            "Run a quick security scan. Check for: (1) policy gaps, (2) high-risk activity patterns, "
            "(3) unacknowledged alerts. If you find low-severity alerts older than 4 hours, acknowledge "
            "them automatically. Report findings concisely. If all looks good, say so.",
            [],
        )
        self._last_scan_at = datetime.now(timezone.utc)
        return result

    async def _background_loop(self):
        await asyncio.sleep(45)  # Let the server finish starting
        while True:
            try:
                logger.info("ARIA: starting background scan")
                result = await self.scan()
                logger.info("ARIA scan complete — actions taken: %d", len(result.get("actions_taken", [])))
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("ARIA background scan error: %s", e)
            await asyncio.sleep(300)  # Every 5 minutes

    def start(self):
        """Start background monitoring (only if API key is configured)."""
        api_key = settings.anthropic_api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            logger.info("ARIA: ANTHROPIC_API_KEY not set — autonomous monitoring disabled")
            return
        logger.info("ARIA: starting background monitoring")
        self._background_task = asyncio.create_task(self._background_loop())

    def stop(self):
        if self._background_task:
            self._background_task.cancel()

    @property
    def status(self) -> dict:
        api_key = settings.anthropic_api_key or os.environ.get("ANTHROPIC_API_KEY")
        return {
            "available": bool(api_key),
            "last_scan_at": self._last_scan_at.isoformat() if self._last_scan_at else None,
            "recent_actions": self._recent_actions[-10:],
        }


aria = ARIAAgent()
