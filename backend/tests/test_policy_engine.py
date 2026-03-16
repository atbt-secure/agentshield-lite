"""Unit tests for the policy engine."""
import pytest
import pytest_asyncio
from backend.policy.engine import PolicyEngine
from backend.models import Policy


@pytest_asyncio.fixture
async def engine():
    return PolicyEngine()


@pytest.mark.asyncio
async def test_default_allow_when_no_policies(db_session, engine):
    decision = await engine.evaluate(db_session, "agent-1", "database", "query", {})
    assert decision.effect == "allow"
    assert not decision.blocked


@pytest.mark.asyncio
async def test_block_policy_matches_exact_tool_and_action(db_session, engine):
    policy = Policy(name="No DB Delete", tool="database", action="delete", effect="block", priority=1, enabled=True)
    db_session.add(policy)
    await db_session.commit()

    decision = await engine.evaluate(db_session, "agent-1", "database", "delete", {})
    assert decision.effect == "block"
    assert decision.blocked
    assert decision.matched_policy == "No DB Delete"


@pytest.mark.asyncio
async def test_block_policy_does_not_match_different_action(db_session, engine):
    policy = Policy(name="No DB Delete", tool="database", action="delete", effect="block", priority=1, enabled=True)
    db_session.add(policy)
    await db_session.commit()

    decision = await engine.evaluate(db_session, "agent-1", "database", "query", {})
    assert decision.effect == "allow"


@pytest.mark.asyncio
async def test_wildcard_tool_matches_any(db_session, engine):
    policy = Policy(name="Block All Shell", tool="*", action="shell", effect="block", priority=1, enabled=True)
    db_session.add(policy)
    await db_session.commit()

    decision = await engine.evaluate(db_session, "agent-1", "system", "shell", {})
    assert decision.blocked


@pytest.mark.asyncio
async def test_disabled_policy_is_ignored(db_session, engine):
    policy = Policy(name="Disabled Block", tool="database", action="delete", effect="block", priority=1, enabled=False)
    db_session.add(policy)
    await db_session.commit()

    decision = await engine.evaluate(db_session, "agent-1", "database", "delete", {})
    assert decision.effect == "allow"


@pytest.mark.asyncio
async def test_priority_ordering_lower_wins(db_session, engine):
    """Lower priority number = evaluated first = wins."""
    alert_policy = Policy(name="Alert Delete", tool="database", action="delete", effect="alert", priority=10, enabled=True)
    block_policy = Policy(name="Block Delete", tool="database", action="delete", effect="block", priority=1, enabled=True)
    db_session.add_all([alert_policy, block_policy])
    await db_session.commit()

    decision = await engine.evaluate(db_session, "agent-1", "database", "delete", {})
    assert decision.effect == "block"
    assert decision.matched_policy == "Block Delete"


@pytest.mark.asyncio
async def test_alert_policy_is_not_blocking(db_session, engine):
    policy = Policy(name="Alert Email", tool="*", action="send_email", effect="alert", priority=10, enabled=True)
    db_session.add(policy)
    await db_session.commit()

    decision = await engine.evaluate(db_session, "agent-1", "email", "send_email", {})
    assert decision.effect == "alert"
    assert not decision.blocked


@pytest.mark.asyncio
async def test_condition_matching(db_session, engine):
    """Policy with condition only matches when tool_input contains the key/value."""
    policy = Policy(
        name="Block Prod Delete",
        tool="database",
        action="delete",
        condition={"env": "production"},
        effect="block",
        priority=1,
        enabled=True,
    )
    db_session.add(policy)
    await db_session.commit()

    blocked = await engine.evaluate(db_session, "agent-1", "database", "delete", {"env": "production"})
    allowed = await engine.evaluate(db_session, "agent-1", "database", "delete", {"env": "staging"})

    assert blocked.blocked
    assert not allowed.blocked
