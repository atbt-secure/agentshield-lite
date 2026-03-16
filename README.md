# AgentShield Lite — AI Agent Security Platform

A runtime security gateway for AI agents. Acts as a transparent proxy between your AI agents and their tools, providing:

- **Prompt Injection Detection** — Pattern-based analysis of agent prompts
- **Policy Enforcement** — Rule-based allow/block/alert on tool calls
- **Risk Scoring** — Continuous risk assessment (0–100 scale)
- **Audit Logging** — Complete record of every agent action
- **Slack Alerts** — Real-time notifications for high-risk events
- **Dashboard UI** — Live monitoring of agent activity

---

## Quick Start

### 1. Clone and configure
```bash
git clone <repo>
cd AI_Agent_Security_Platform
cp .env.example .env
```

### 2. Start with Docker
```bash
make docker-up
```

Backend runs on `http://localhost:8000`
Dashboard runs on `http://localhost:8080`

### 3. Start in dev mode
```bash
make install
make dev
```

---

## SDK Usage

### Install
```bash
cd sdk/python
pip install -e .
```

### Basic usage
```python
from agentshield import AgentShieldClient

shield = AgentShieldClient(
    base_url="http://localhost:8000",
    agent_id="my-agent-v1",
)

result = await shield.intercept(
    tool="database",
    action="query",
    prompt=user_prompt,
    tool_input={"query": "SELECT * FROM users"},
)

if not result.allowed:
    raise PermissionError(result.message)
```

### Decorator usage
```python
from agentshield import shield, configure, AgentShieldClient

configure(AgentShieldClient(base_url="http://localhost:8000", agent_id="my-agent"))

@shield(tool="database", action="query")
async def query_db(prompt: str, query: str):
    # automatically intercepted
    ...
```

---

## API Reference

### POST /proxy/intercept
Main interception endpoint used by the SDK.

```json
{
  "agent_id": "my-agent",
  "session_id": "session-abc",
  "tool": "database",
  "action": "query",
  "prompt": "Get all users",
  "tool_input": {"query": "SELECT * FROM users"},
  "metadata": {}
}
```

Response:
```json
{
  "allowed": true,
  "log_id": 42,
  "risk_score": 15.0,
  "risk_level": "low",
  "risk_flags": [],
  "policy_decision": "allow",
  "policy_matched": null,
  "message": "Action allowed (risk: low)"
}
```

### GET /api/logs
Query agent action logs with filters: `agent_id`, `tool`, `blocked`, `min_risk`, `limit`, `offset`

### GET /api/dashboard/stats
Dashboard statistics: total actions, block rate, avg risk score, etc.

### GET /api/policies / POST /api/policies
Manage security policies.

---

## Policy Examples

Block all database deletes:
```json
{
  "name": "No DB Delete",
  "tool": "database",
  "action": "delete",
  "effect": "block",
  "priority": 1
}
```

Alert on any email sending:
```json
{
  "name": "Email Alert",
  "tool": "*",
  "action": "send_email",
  "effect": "alert",
  "priority": 10
}
```

---

## Risk Score Levels

| Score | Level    | Color  |
|-------|----------|--------|
| 0–30  | LOW      | Green  |
| 31–60 | MEDIUM   | Yellow |
| 61–80 | HIGH     | Orange |
| 81–100| CRITICAL | Red    |

---

## Architecture

```
User/System
    ↓
AI Agent (LLM)
    ↓
AgentShield SDK (intercept call)
    ↓
AgentShield Backend (/proxy/intercept)
    ├── Risk Scorer (injection detection, dangerous action scoring)
    ├── Policy Engine (rule evaluation)
    ├── Logger (SQLite/PostgreSQL)
    └── Alerter (Slack webhook)
    ↓
Tool (Database / API / Files / Cloud)
```

---

## Environment Variables

See `.env.example` for all configuration options.

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | sqlite+aiosqlite:///./agentshield.db | Database connection string |
| `SLACK_WEBHOOK_URL` | (empty) | Slack incoming webhook for alerts |
| `RISK_ALERT_THRESHOLD` | 70 | Minimum risk score to trigger alert |
| `API_KEY` | (empty) | Optional API key for authentication |
| `DEBUG` | false | Enable debug logging |
