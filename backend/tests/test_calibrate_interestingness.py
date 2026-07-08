"""Tests for the interestingness calibration harness gold-set wiring (#142)."""

from scripts.calibrate_interestingness import (
    _parse_label,
    evaluate_labeled_rows,
    run_grid_search,
    score_rows,
)


def test_parse_label_understands_gold_set_vocabulary():
    assert _parse_label("love") is True
    assert _parse_label("bad") is False
    assert _parse_label("kill") is False
    assert _parse_label("fine") is None  # neutral, excluded
    # binary form still works
    assert _parse_label("interesting") is True
    assert _parse_label("boring") is False
    assert _parse_label("") is None


def _gold_rows():
    return [
        {"market_id": 1, "name": "hot", "label": "love", "leader_probability": 0.66,
         "movement_24h": 0.2, "volume_24h": 900000, "category": "economics",
         "source_count": 3, "llm_quality": 0.9,
         "resolution_date": "2026-07-20T00:00:00+00:00"},
        {"market_id": 2, "name": "hot2", "label": "love", "leader_probability": 0.71,
         "movement_24h": 0.22, "volume_24h": 120000, "category": "geopolitics",
         "source_count": 2, "llm_quality": 0.8,
         "resolution_date": "2026-07-15T00:00:00+00:00"},
        {"market_id": 3, "name": "dud", "label": "kill", "leader_probability": 0.55,
         "movement_24h": 0.01, "volume_24h": 500, "category": "crypto",
         "source_count": 1, "llm_quality": 0.2,
         "resolution_date": "2026-12-31T00:00:00+00:00"},
        {"market_id": 4, "name": "meh", "label": "fine", "leader_probability": 0.6,
         "movement_24h": 0.05, "volume_24h": 15000, "category": "culture",
         "source_count": 2, "llm_quality": 0.6,
         "resolution_date": "2026-08-01T00:00:00+00:00"},
    ]


def test_scorer_separates_love_from_kill():
    scored = score_rows(_gold_rows())
    metrics = evaluate_labeled_rows(scored, top_n=2)
    # "fine" is neutral so only 3 rows are labeled positive/negative.
    assert metrics["labeled_rows"] == 3
    assert metrics["positive_rows"] == 2
    assert metrics["negative_rows"] == 1
    assert metrics["positive_average_score"] > metrics["negative_average_score"]


def test_grid_search_ranks_by_separation():
    grid = run_grid_search(_gold_rows(), top_n=2)
    assert len(grid) == 5
    separations = [entry["separation"] for entry in grid]
    assert separations == sorted(separations, reverse=True)
    assert all("config" in entry for entry in grid)
