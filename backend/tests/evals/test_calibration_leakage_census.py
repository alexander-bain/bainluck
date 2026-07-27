from unittest.mock import AsyncMock, MagicMock

import pytest

from scripts.evals.calibration_leakage_census import (
    build_report,
    classify_resolution_source,
    load_from_session,
)


def row(i, question, probability, actual, resolution_source, **extra):
    return {
        "outcome_id": i,
        "market_id": i,
        "question_id": question,
        "source": extra.pop("source", "kalshi"),
        "llm_sport_category": extra.pop("category", "politics"),
        "market_type": extra.pop("market_type", "claim"),
        "probability": probability,
        "is_winner": actual,
        "resolution_source": resolution_source,
        "calibration_probability": extra.pop("calibration_probability", probability),
        "current_probability": extra.pop("current_probability", probability),
        **extra,
    }


def test_resolution_classes_are_explicit_and_unknown_fails():
    assert classify_resolution_source("api_settlement") == "independent_authoritative"
    assert classify_resolution_source("game_score") == "independent_deterministic"
    assert classify_resolution_source("clean_resolution") == "price_derived"
    assert classify_resolution_source("settlement_sync") == "price_derived"
    assert classify_resolution_source("all_losers") == "excluded_family"
    assert classify_resolution_source(None) == "missing"
    assert classify_resolution_source("new_unclassified_writer") == "unknown"
    with pytest.raises(ValueError, match="new_unclassified_writer"):
        build_report({"rows": [row(1, "q1", 0.5, True, "new_unclassified_writer")]})


def test_counterfactual_can_improve_error():
    rows = [row(i, f"good-{i}", 0.8, True, "api_settlement") for i in range(30)]
    rows += [row(100 + i, f"bad-{i}", 0.9, False, "clean_resolution") for i in range(30)]
    report = build_report({"rows": rows})
    assert report["counterfactual"]["ece"] < report["current"]["ece"]


def test_counterfactual_can_worsen_error():
    rows = [row(i, f"bad-{i}", 0.9, False, "api_settlement") for i in range(30)]
    rows += [row(100 + i, f"good-{i}", 0.8, True, "clean_resolution") for i in range(30)]
    report = build_report({"rows": rows})
    assert report["counterfactual"]["ece"] > report["current"]["ece"]


def test_counterfactual_can_leave_error_unchanged():
    rows = [row(i, f"a-{i}", 0.8, True, "api_settlement") for i in range(30)]
    rows += [row(100 + i, f"b-{i}", 0.8, True, "clean_resolution") for i in range(30)]
    report = build_report({"rows": rows})
    assert report["counterfactual"]["ece"] == report["current"]["ece"]


def test_removes_whole_question_not_one_correlated_outcome():
    rows = [
        row(1, "field", 0.6, True, "api_settlement", is_mex_normalized=True),
        row(2, "field", 0.3, False, "clean_resolution", is_mex_normalized=True),
        row(3, "field", 0.1, False, "api_settlement", is_mex_normalized=True),
        row(4, "other", 0.7, True, "api_settlement"),
    ]
    report = build_report({"rows": rows})
    assert report["removed"] == {
        "questions": 1,
        "outcomes": 3,
        "normalized_field_questions": 1,
    }
    assert report["counterfactual"]["outcomes"] == 1


def test_one_large_field_is_one_question_and_upper_bound_is_honest():
    rows = [
        row(i, "one-field", 0.99 if i == 0 else 0.01, i == 0, "clean_resolution")
        for i in range(100)
    ]
    report = build_report({"rows": rows})
    assert report["current"]["outcomes"] == 100
    assert report["current"]["questions"] == 1
    assert report["terminal_price_upper_bound"]["outcomes"] == 100
    assert "not proof" in report["terminal_price_upper_bound"]["meaning"]


def test_resolution_census_reports_outcomes_and_questions_by_full_cohort_key():
    rows = [
        row(1, "field", 0.7, True, "api_settlement", market_type="field"),
        row(2, "field", 0.3, False, "api_settlement", market_type="field"),
    ]
    cell = build_report({"rows": rows})["resolution_census"][0]
    assert cell["resolution_source"] == "api_settlement"
    assert cell["outcomes"] == 2
    assert cell["questions"] == 1


@pytest.mark.asyncio
async def test_session_loader_composes_canonical_rows_and_sports_audit():
    canonical_result = MagicMock()
    canonical_result.all.return_value = []
    sports_result = MagicMock()
    sports_result.all.return_value = []
    session = MagicMock()
    session.execute = AsyncMock(side_effect=[canonical_result, sports_result])
    payload = await load_from_session(session)
    assert payload == {"rows": [], "sports_closing_mismatches": []}
    first_sql = str(session.execute.await_args_list[0].args[0])
    second_sql = str(session.execute.await_args_list[1].args[0])
    assert "FROM deduped d" in first_sql
    assert "JOIN futures_outcomes fo ON fo.id = d.outcome_id" in first_sql
    assert second_sql.count("os.captured_at < e.commence_time") == 3
