"""Unit tests for the Discover candidate-pool snapshot feature builder (#142)."""

from datetime import datetime, timezone
from types import SimpleNamespace

from app.utils.discover_candidate_snapshot import build_candidate_features
from app.utils.market_interestingness import (
    MarketInterestingnessInputs,
    score_market_interestingness,
)


def _outcome(prob=None, move=None):
    return SimpleNamespace(current_probability=prob, probability_change_24h=move)


def _market(**kwargs):
    defaults = dict(
        outcomes=[],
        updated_at=datetime(2026, 7, 8, 12, 0, tzinfo=timezone.utc),
        resolution_date=datetime(2026, 7, 20, 12, 0, tzinfo=timezone.utc),
        llm_sport_category="politics",
        volume_24h=12345,
        market_metadata={},
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def test_leader_probability_and_movement_are_extremes():
    market = _market(
        outcomes=[
            _outcome(prob=0.4, move=0.02),
            _outcome(prob=0.62, move=-0.11),
            _outcome(prob=None, move=None),
        ]
    )
    features = build_candidate_features(market, source_count=3)
    assert features["leader_probability"] == 0.62
    # movement uses the largest absolute 24h change
    assert features["movement_24h"] == 0.11
    assert features["source_count"] == 3
    assert features["category"] == "politics"
    assert features["volume_24h"] == 12345.0


def test_zero_movement_stored_as_none():
    market = _market(outcomes=[_outcome(prob=0.5, move=0.0)])
    features = build_candidate_features(market, source_count=1)
    assert features["movement_24h"] is None


def test_llm_quality_pulled_from_discover_llm_metadata():
    market = _market(market_metadata={"discover_llm": {"quality_score": 0.8}})
    features = build_candidate_features(market, source_count=1)
    assert features["llm_quality"] == 0.8


def test_features_are_consumable_by_interestingness_scorer():
    # The whole point of the snapshot: the replay runner rebuilds inputs from
    # these features and recomputes interestingness under a new weight config.
    market = _market(
        outcomes=[_outcome(prob=0.7, move=0.15)],
        market_metadata={"discover_llm": {"quality_score": 0.9}},
    )
    features = build_candidate_features(market, source_count=2)
    inputs = MarketInterestingnessInputs.from_mapping(features)
    result = score_market_interestingness(inputs)
    assert 0.0 <= result.score <= 100.0
    # leader_probability alias maps to the scorer's probability signal
    assert inputs.probability == 0.7
