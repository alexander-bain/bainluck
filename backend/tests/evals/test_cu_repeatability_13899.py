"""Unit tests for #13899 repeatability comparison and budget enforcement."""

from __future__ import annotations

from pathlib import Path
import pytest

import scripts.run_cu_repeatability_13899 as repeatability
from app.services.llm_request import JobBudget
from scripts.run_cu_repeatability_13899 import (
    apply_writer_postprocess,
    build_prompt_for_market,
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


def test_job_budget_and_hard_cap_validation(monkeypatch):
    budget = JobBudget(limit_usd=1.0)
    assert budget.spent_usd == 0.0
    assert not hasattr(repeatability, "_load_dotenv")
    with pytest.raises(ValueError, match="max_budget_usd"):
        execute_repeatability_runs(Path("unused.json"), max_budget_usd=1.5)

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        execute_repeatability_runs(Path("unused.json"), max_budget_usd=0.5)


def test_postprocess_and_prompt_parity_uses_league_keys_rank_order_and_other_category():
    item = {
        "market_id": 88001,
        "title": "Fenerbahçe vs Stuttgart winner?",
        "source": "polymarket",
        "category": None,
        "llm_sport_category": None,
        "linked_game_id": 55501,
        "linked_start": "2026-06-15T20:00:00+00:00",
        "start_source": "odds_api",
        "linked_league": "soccer_uefa_europa_league",
        "home_team_league": "soccer_turkey_super_league",
        "away_team_league": "soccer_germany_bundesliga",
        "outcomes": [
            {"id": 10 + i, "name": f"Tail {i}", "prob": 0.01, "rank": 20 + i}
            for i in range(9)
        ] + [
            {"id": 999, "name": "Stuttgart", "prob": 0.35, "rank": 2},
            {"id": 998, "name": "Fenerbahçe", "prob": 0.45, "rank": 1},
        ],
    }

    prompt = build_prompt_for_market(item)
    assert "Category hint: other" in prompt
    idx_fener = prompt.find("Fenerbahçe")
    idx_stutt = prompt.find("Stuttgart")
    assert idx_fener != -1 and idx_stutt != -1 and idx_fener < idx_stutt
    assert "Tail 8" not in prompt
    assert "Omit these fields. Bain Luck supplies them: event_date, geography." in prompt

    raw = {
        "topic": "sports",
        "subtopic": "soccer",
        "entities": [{"name": "Fenerbahçe", "type": "team"}],
        "geography": "us",
        "story_key": "story:europa",
        "temporal": "event_tied",
        "event_date": None,
        "recurrence": "one_off",
        "stakes": 3,
        "breadth": 3,
        "oddity": 1,
        "arc": "matchup",
        "hook_facts": [],
        "junk_flags": [],
        "confidence": 0.9,
    }
    prof = apply_writer_postprocess(item, raw, model_name="gpt-4o-mini")
    # Distinct team country leagues yield global geography + Europe/Zurich schedule day.
    assert prof["geography"] == "global"
    assert prof["event_date"] == "2026-06-15"
