"""
Auto-seeds sensible default security policies on first startup.
Only runs when the policies table is completely empty.
"""
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from .models import Policy

logger = logging.getLogger(__name__)

DEFAULT_POLICIES = [
    Policy(
        name="Block DB Drop",
        description="Prevent agents from dropping database tables.",
        tool="database", action="drop", effect="block", priority=1,
    ),
    Policy(
        name="Block DB Truncate",
        description="Prevent agents from truncating tables.",
        tool="database", action="truncate", effect="block", priority=2,
    ),
    Policy(
        name="Block DB Delete",
        description="Agents cannot delete rows. Use soft-delete instead.",
        tool="database", action="delete", effect="block", priority=3,
    ),
    Policy(
        name="Block Shell Execution",
        description="Agents must not run arbitrary shell commands.",
        tool="*", action="shell", effect="block", priority=4,
    ),
    Policy(
        name="Block Bash Execution",
        description="Agents must not run bash/cmd/powershell.",
        tool="*", action="bash", effect="block", priority=5,
    ),
    Policy(
        name="Alert on Email Send",
        description="Notify team whenever an agent sends email.",
        tool="*", action="send_email", effect="alert", priority=20,
    ),
    Policy(
        name="Alert on External HTTP POST",
        description="Flag outbound POST requests to external services.",
        tool="http", action="post", effect="alert", priority=21,
    ),
    Policy(
        name="Alert on File Write Outside /app",
        description="Flag file writes that may reach system paths.",
        tool="files", action="write", effect="alert", priority=22,
    ),
]


async def seed_default_policies(db: AsyncSession) -> None:
    count = (await db.execute(select(func.count(Policy.id)))).scalar()
    if count and count > 0:
        return  # Already seeded — don't overwrite user-defined policies

    logger.info("First startup detected — seeding %d default security policies", len(DEFAULT_POLICIES))
    for policy in DEFAULT_POLICIES:
        db.add(policy)
    await db.commit()
    logger.info("Default policies installed.")
