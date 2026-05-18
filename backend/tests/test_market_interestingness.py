from datetime import datetime, timedelta, timezone

from app.utils.market_interestingness import (
    MarketInterestingnessInputs,
    category_novelty_signal,
    decisiveness_signal,
    movement_signal,
    score_market_interestingness,
)
from scripts.calibrate_interestingness import evaluate_labeled_rows, score_rows


NOW = datetime(2026, 5, 18, 12, 0, tzinfo=timezone.utc)


def test_decisiveness_prefers_visible_leader_without_settlement():
    assert decisiveness_signal(0.72) > decisiveness_signal(0.51)
    assert decisiveness_signal(0.72) > decisiveness_signal(0.99)
    assert decisiveness_signal(72) == decisiveness_signal(0.72)


def test_movement_accepts_percentage_points_and_fractional_values():
    assert movement_signal(12) == movement_signal(0.12)
    assert movement_signal(-0.12) == movement_signal(0.12)
    assert movement_signal(0.20) > movement_signal(0.02)


def test_category_novelty_uses_stricter_of_count_and_share():
    assert category_novelty_signal(recent_count=0) == 1.0
    assert category_novelty_signal(recent_count=12) == 0.1
    assert category_novelty_signal(recent_count=0, feed_share=0.60) == 0.0
    assert category_novelty_signal() == 0.5


def test_score_market_interestingness_returns_components_and_reasons():
    result = score_market_interestingness(
        MarketInterestingnessInputs(
            probability=0.72,
            source_count=3,
            updated_at=NOW - timedelta(minutes=20),
            movement_24h=0.14,
            resolution_date=NOW + timedelta(days=3),
            category_recent_count=1,
            volume_24h=25_000,
            llm_quality=0.9,
        ),
        now=NOW,
    )

    assert result.score > 80
    assert set(result.components) == {
        "decisiveness",
        "multi_source",
        "recency",
        "movement",
        "resolution_proximity",
        "category_novelty",
        "volume",
        "llm_quality",
    }
    assert "multi_source" in result.reasons
    assert "fresh" in result.reasons
    assert "moving" in result.reasons


def test_stale_low_signal_market_scores_lower_than_fresh_active_market():
    active = score_market_interestingness(
        {
            "leader_probability": "68",
            "source_count": "2",
            "last_updated": (NOW - timedelta(hours=1)).isoformat(),
            "probability_change_24h": "9",
            "resolution_date": (NOW + timedelta(days=5)).isoformat(),
            "category_impressions": "1",
            "volume_24h": "50000",
            "hook_quality": "8",
        },
        now=NOW,
    )
    stale = score_market_interestingness(
        {
            "leader_probability": "99",
            "source_count": "1",
            "last_updated": (NOW - timedelta(days=10)).isoformat(),
            "probability_change_24h": "0",
            "resolution_date": (NOW + timedelta(days=180)).isoformat(),
            "category_impressions": "15",
            "volume_24h": "0",
            "hook_quality": "2",
        },
        now=NOW,
    )

    assert active.score > stale.score + 50


def test_calibration_scaffold_scores_and_evaluates_labeled_rows():
    rows = [
        {
            "id": "interesting",
            "name": "Will rates be cut next week?",
            "probability": 0.66,
            "source_count": 2,
            "movement_24h": 0.12,
            "volume_24h": 100_000,
            "llm_quality": 9,
            "label": "yes",
        },
        {
            "id": "boring",
            "name": "Will a stale market resolve next year?",
            "probability": 0.99,
            "source_count": 1,
            "movement_24h": 0,
            "volume_24h": 0,
            "llm_quality": 1,
            "label": "no",
        },
    ]

    scored = score_rows(rows)
    metrics = evaluate_labeled_rows(scored, top_n=1)

    assert scored[0]["id"] == "interesting"
    assert metrics["labeled_rows"] == 2
    assert metrics["positive_rows"] == 1
    assert metrics["precision_at_1"] == 1
    assert metrics["recall_at_1"] == 1
