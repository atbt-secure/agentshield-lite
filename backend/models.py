from sqlalchemy import Column, Integer, String, DateTime, Float, Boolean, Text, JSON
from sqlalchemy.sql import func
from .database import Base


class AgentLog(Base):
    __tablename__ = "agent_logs"

    id = Column(Integer, primary_key=True, index=True)
    agent_id = Column(String(100), index=True, nullable=False)
    session_id = Column(String(100), index=True)
    tool = Column(String(100), nullable=False)
    action = Column(String(100), nullable=False)
    prompt = Column(Text)
    tool_input = Column(JSON)
    tool_output = Column(JSON)
    risk_score = Column(Float, default=0.0)
    risk_flags = Column(JSON, default=list)
    policy_decision = Column(String(20), default="allow")  # allow/block/alert
    policy_matched = Column(String(200))
    blocked = Column(Boolean, default=False)
    duration_ms = Column(Float)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    metadata_ = Column("metadata", JSON, default=dict)


class Policy(Base):
    __tablename__ = "policies"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False)
    description = Column(Text)
    tool = Column(String(100))     # "*" = any tool
    action = Column(String(100))   # "*" = any action
    condition = Column(JSON, default=dict)  # extra matching conditions
    effect = Column(String(20), nullable=False)  # allow / block / alert
    priority = Column(Integer, default=100)
    enabled = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class Alert(Base):
    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True, index=True)
    log_id = Column(Integer, index=True)
    agent_id = Column(String(100), index=True)
    alert_type = Column(String(50))  # risk_threshold / policy_block / injection
    message = Column(Text)
    severity = Column(String(20))  # low / medium / high / critical
    acknowledged = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
