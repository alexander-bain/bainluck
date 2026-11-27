"""Unit tests for #13899 repeatability comparison and budget enforcement."""

from __future__ import annotations

from pathlib import Path
import pytest

from app.services.llm_request import JobBudget
from scripts.run_cu_repeatability_13899 import (
    apply_writer_postprocess,
    compare_cu_runs,
    execute_repeatability_runs,
)


def test_compare_cu_runs_counts_changed_fields_and_orders_highest_churn_first():
    markets = [
        {"market_id": 1, "title": "Market A", "draw_bucket": "reader_weighted", "source": "kalshi"},
        {"market_id": 2, "title": "Market B", "draw_bucket": "pilot_50", "source": "polymarket"},
        {"market_id": 3, "title": "Market C", "draw_bucket": "roster_spread", "source": "kalshi"},
    ]
    run1 = {
        1: {"topic": "politics", "breadth": 2, "stakes": 2, "entities": [{"name": "senate", "type": "org"}]},
        2: {"topic": "sports", "breadth": 3, "stakes": 1, "entities": [{"name": "lakers", "type": "team"}]},
        3: {"topic": "weather", "breadth": 2, "stakes": 1, "entities": []},
    }
    run2 = {
        1: {"topic": "politics", "breadth": 3, "stakes": 3, "entities": [{"name": "senate", "type": "org"}]},
        2: {"topic": "esports", "breadth": 4, "stakes": 2, "entities": [{"name": "t1", "type": "team"}]},
        3: {"topic": "weather", "breadth": 2, "stakes": 1, "entities": []},
    }
    diff = compare_cu_runs(markets, run1, run2, fields=("topic", "breadth", "stakes", "entities"))
    assert diff["market_count"] == 3
    assert diff["any_field_changed_markets"] == 2
    assert [m["market_id"] for m in diff["changed_markets"]] == [2, 1]
    assert [f["field"] for f in diff["fields_over_10_pct"]] == ["breadth", "stakes", "entities", "topic"]


def test_apply_writer_postprocess_enforces_code_rules_without_db_write():
    item = {
        "market_id": 70136122,
        "title": "Vermont House Orleans-3 winner? (2028)",
        "source": "kalshi",
        "category": "politics",
        "llm_sport_category": "politics",
        "status": "open",
        "resolution_date": "2029-05-07T14:00:00+00:00",
        "outcomes": [{"name": "Democratic", "prob": 0.7}, {"name": "Republican", "prob": 0.25}],
    }
    raw = {
        "topic": "politics",
        "subtopic": "elections",
        "entities": [{"name": "vermont house orleans-3", "type": "place"}],
        "geography": "us",
        "story_key": "story:vt-house",
        "series_key": None,
        "temporal": "event_tied",
        "event_date": "2029-05-07",
        "recurrence": "one_off",
        "stakes": 3,
        "breadth": 3,
        "oddity": 1,
        "arc": "race",
        "hook_facts": [],
        "junk_flags": [],
        "confidence": 0.9,
    }
    prof = apply_writer_postprocess(item, raw, model_name="gpt-4o-mini")
    assert prof["geography"] == "local"
    assert prof["stakes"] == 1
    assert prof["breadth"] == 1
    assert prof["event_date"] == "2028-11-07"
    assert prof["liveness"] == "active"


def test_job_budget_and_hard_cap_validation():
    budget = JobBudget(limit_usd=1.0)
    assert budget.spent_usd == 0.0
    with pytest.raises(ValueError, match="max_budget_usd"):
        execute_repeatability_runs(Path("unused.json"), max_budget_usd=1.5)
