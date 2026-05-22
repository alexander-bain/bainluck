import importlib.util
import sys
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_PATH = (
    Path(__file__).resolve().parents[2] / "scripts" / "audit_search_fts_readiness.py"
)
SPEC = importlib.util.spec_from_file_location("audit_search_fts_readiness", SCRIPT_PATH)
audit = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = audit
SPEC.loader.exec_module(audit)


def test_trace_from_row_accepts_common_export_fields():
    trace = audit.trace_from_row(
        {
            "search_query": "Celtics Lakers",
            "response_time_ms": "123.4",
            "total_results": "8",
            "result_click": "true",
            "timestamp": "2026-05-20T12:00:00Z",
        }
    )

    assert trace.query == "Celtics Lakers"
    assert trace.latency_ms == 123.4
    assert trace.results_count == 8
    assert trace.clicked is True
    assert trace.timestamp == datetime(2026, 5, 20, 12, 0, tzinfo=timezone.utc)


def test_decision_keeps_issue_open_for_small_trace_sample():
    traces = [
        audit.SearchTrace(query=f"query {idx}", latency_ms=50.0) for idx in range(10)
    ]
    decision = audit.decide(audit.summarize_traces(traces), plan_summary=None)

    assert decision.status == "keep_open_pending_traces"


def test_decision_requires_db_plans_when_endpoint_latency_is_high():
    traces = [
        audit.SearchTrace(query=f"query {idx % 60}", latency_ms=900.0)
        for idx in range(600)
    ]
    decision = audit.decide(audit.summarize_traces(traces), plan_summary=None)

    assert decision.status == "collect_db_plans_before_migration"


def test_decision_recommends_spike_only_with_slow_traces_and_plans():
    traces = [
        audit.SearchTrace(query=f"query {idx % 60}", latency_ms=900.0)
        for idx in range(600)
    ]
    plan_summary = {
        "events": {
            "execution_ms": {"p95": 200.0, "max": 300.0},
        }
    }

    decision = audit.decide(audit.summarize_traces(traces), plan_summary)

    assert decision.status == "candidate_for_stored_tsvector_spike"


def test_decision_does_not_add_vectors_when_latency_is_low():
    traces = [
        audit.SearchTrace(query=f"query {idx % 60}", latency_ms=80.0)
        for idx in range(600)
    ]

    decision = audit.decide(audit.summarize_traces(traces), plan_summary=None)

    assert decision.status == "do_not_add_stored_vectors_yet"
