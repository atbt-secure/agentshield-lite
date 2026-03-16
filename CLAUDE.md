# AgentShield Lite — AI Agent Security Platform

## Project Overview
Runtime security gateway for AI agents. Acts as a proxy layer between AI agents and their tools, providing logging, policy enforcement, prompt injection detection, and alerting.

## Architecture
```
User/System → AI Agent → AgentShield Proxy → Policy Engine + Risk Scorer + Logger → Tool (DB/API/Files/Cloud)
                                                         ↓
                                              Observability DB → Dashboard UI
```

## Core Components
- **Proxy (backend/proxy/)**: HTTP proxy intercepting all agent tool calls
- **Policy Engine (backend/policy/)**: Rule-based authorization (allow/block/alert)
- **Risk Scorer (backend/risk/)**: Prompt injection detection + risk scoring
- **Alerts (backend/alerts/)**: Slack webhook integration
- **SDK (sdk/python/)**: Python SDK for easy agent integration
- **Dashboard (dashboard/)**: Vanilla JS SPA for monitoring

## Development Commands
```bash
# Start backend dev server
make dev

# Start with Docker
make docker-up

# Run tests
make test

# Install SDK locally
cd sdk/python && pip install -e .
```

## Environment Variables
See .env.example for all required configuration.

## API Endpoints
- POST /proxy/intercept — Main proxy endpoint (used by SDK)
- GET  /api/logs — Agent action logs
- GET  /api/logs/{id} — Single log entry
- GET  /api/dashboard/stats — Dashboard statistics
- GET  /api/dashboard/timeline — Activity timeline
- GET  /api/policies — List policies
- POST /api/policies — Create policy
- PUT  /api/policies/{id} — Update policy
- DELETE /api/policies/{id} — Delete policy

## Policy Rule Format
```json
{
  "name": "No DB Delete",
  "tool": "database",
  "action": "delete",
  "condition": {},
  "effect": "block",
  "priority": 1
}
```

## Risk Score Levels
- 0-30: LOW (green)
- 31-60: MEDIUM (yellow)
- 61-80: HIGH (orange)
- 81-100: CRITICAL (red)
