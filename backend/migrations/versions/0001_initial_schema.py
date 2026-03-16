"""Initial schema — agent_logs, policies, alerts

Revision ID: 0001
Revises:
Create Date: 2026-03-16

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "agent_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("agent_id", sa.String(100), nullable=False),
        sa.Column("session_id", sa.String(100), nullable=True),
        sa.Column("tool", sa.String(100), nullable=False),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=True),
        sa.Column("tool_input", sa.JSON(), nullable=True),
        sa.Column("tool_output", sa.JSON(), nullable=True),
        sa.Column("risk_score", sa.Float(), nullable=True, server_default="0.0"),
        sa.Column("risk_flags", sa.JSON(), nullable=True),
        sa.Column("policy_decision", sa.String(20), nullable=True, server_default="allow"),
        sa.Column("policy_matched", sa.String(200), nullable=True),
        sa.Column("blocked", sa.Boolean(), nullable=True, server_default="0"),
        sa.Column("duration_ms", sa.Float(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_agent_logs_agent_id", "agent_logs", ["agent_id"])
    op.create_index("ix_agent_logs_session_id", "agent_logs", ["session_id"])

    op.create_table(
        "policies",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("tool", sa.String(100), nullable=True),
        sa.Column("action", sa.String(100), nullable=True),
        sa.Column("condition", sa.JSON(), nullable=True),
        sa.Column("effect", sa.String(20), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=True, server_default="100"),
        sa.Column("enabled", sa.Boolean(), nullable=True, server_default="1"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "alerts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("log_id", sa.Integer(), nullable=True),
        sa.Column("agent_id", sa.String(100), nullable=True),
        sa.Column("alert_type", sa.String(50), nullable=True),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("severity", sa.String(20), nullable=True),
        sa.Column("acknowledged", sa.Boolean(), nullable=True, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_alerts_agent_id", "alerts", ["agent_id"])
    op.create_index("ix_alerts_log_id", "alerts", ["log_id"])


def downgrade() -> None:
    op.drop_table("alerts")
    op.drop_table("policies")
    op.drop_table("agent_logs")
