from typing import Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from ..models import Policy


class PolicyDecision:
    def __init__(self, effect: str, matched_policy: str | None = None):
        self.effect = effect  # allow / block / alert
        self.matched_policy = matched_policy
        self.blocked = effect == "block"


class PolicyEngine:
    async def evaluate(
        self,
        db: AsyncSession,
        agent_id: str,
        tool: str,
        action: str,
        tool_input: Any,
    ) -> PolicyDecision:
        # Load enabled policies ordered by priority (lower number = higher priority)
        result = await db.execute(
            select(Policy)
            .where(Policy.enabled == True)
            .order_by(Policy.priority.asc())
        )
        policies = result.scalars().all()

        for policy in policies:
            if self._matches(policy, tool, action, tool_input):
                return PolicyDecision(effect=policy.effect, matched_policy=policy.name)

        # Default allow
        return PolicyDecision(effect="allow")

    def _matches(self, policy: Policy, tool: str, action: str, tool_input: Any) -> bool:
        # Match tool
        if policy.tool and policy.tool != "*":
            if policy.tool.lower() not in tool.lower():
                return False

        # Match action
        if policy.action and policy.action != "*":
            if policy.action.lower() not in action.lower():
                return False

        # Match conditions (simple key/value on tool_input)
        if policy.condition:
            for key, value in policy.condition.items():
                if isinstance(tool_input, dict):
                    if tool_input.get(key) != value:
                        return False

        return True


policy_engine = PolicyEngine()
