"""
Prometheus-compatible /metrics endpoint.

Exposes:
  agentshield_requests_total{agent_id, tool, decision}   — counter
  agentshield_blocked_total{agent_id, tool}              — counter
  agentshield_risk_score_bucket / _sum / _count          — histogram
  agentshield_request_duration_ms_bucket / _sum / _count — histogram
  agentshield_active_sse_subscribers                     — gauge

No external dependencies — uses prometheus_client (already in Python std ecosystem).
Add to requirements: prometheus-client==0.21.0
"""
import logging
from fastapi import APIRouter
from fastapi.responses import PlainTextResponse

logger = logging.getLogger(__name__)
router = APIRouter(tags=["metrics"])

try:
    from prometheus_client import (
        Counter, Histogram, Gauge,
        generate_latest, CONTENT_TYPE_LATEST,
        CollectorRegistry,
    )
    _PROMETHEUS_AVAILABLE = True
except ImportError:
    _PROMETHEUS_AVAILABLE = False
    logger.warning("prometheus-client not installed — /metrics will return stub response")

# ── Metric definitions ────────────────────────────────────────────────────────

if _PROMETHEUS_AVAILABLE:
    _registry = CollectorRegistry(auto_describe=True)

    requests_total = Counter(
        "agentshield_requests_total",
        "Total intercepted agent actions",
        ["agent_id", "tool", "decision"],
        registry=_registry,
    )

    blocked_total = Counter(
        "agentshield_blocked_total",
        "Total blocked agent actions",
        ["agent_id", "tool"],
        registry=_registry,
    )

    risk_score_histogram = Histogram(
        "agentshield_risk_score",
        "Distribution of risk scores (0–100)",
        buckets=[0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100],
        registry=_registry,
    )

    request_duration_histogram = Histogram(
        "agentshield_request_duration_ms",
        "Interceptor processing time in milliseconds",
        buckets=[1, 5, 10, 25, 50, 100, 250, 500, 1000],
        registry=_registry,
    )

    active_sse_subscribers = Gauge(
        "agentshield_active_sse_subscribers",
        "Number of active SSE dashboard connections",
        registry=_registry,
    )
else:
    # Stub objects so the rest of the codebase can call .labels().inc() safely
    class _Stub:
        def labels(self, **_): return self
        def inc(self, *_): pass
        def observe(self, *_): pass
        def set(self, *_): pass

    requests_total = blocked_total = risk_score_histogram = \
        request_duration_histogram = active_sse_subscribers = _Stub()


def record_intercept(
    agent_id: str,
    tool: str,
    decision: str,
    blocked: bool,
    risk_score: float,
    duration_ms: float,
) -> None:
    """Called by the interceptor after every action."""
    requests_total.labels(agent_id=agent_id, tool=tool, decision=decision).inc()
    if blocked:
        blocked_total.labels(agent_id=agent_id, tool=tool).inc()
    risk_score_histogram.observe(risk_score)
    request_duration_histogram.observe(duration_ms)


# ── Endpoint ──────────────────────────────────────────────────────────────────

@router.get("/metrics", include_in_schema=False)
async def prometheus_metrics():
    if not _PROMETHEUS_AVAILABLE:
        return PlainTextResponse(
            "# prometheus-client not installed\n"
            "# pip install prometheus-client\n",
            media_type="text/plain",
        )
    output = generate_latest(_registry)
    return PlainTextResponse(output.decode(), media_type=CONTENT_TYPE_LATEST)
