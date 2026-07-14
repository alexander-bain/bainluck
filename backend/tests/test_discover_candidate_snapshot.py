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


# --- #195: Decimal → float sanitizer for the JSONB columns ---
# Regression guard for the consec-6 failure: features/anatomy are built from
# Numeric outcome fields (Decimal), and asyncpg's JSONB encoder raised
# "Object of type Decimal is not JSON serializable" on insert.

def test_json_safe_converts_decimal_scalars():
    import json
    from decimal import Decimal
    from app.utils.discover_candidate_snapshot import _json_safe

    assert _json_safe(Decimal("0.62")) == 0.62
    assert isinstance(_json_safe(Decimal("0.62")), float)


def test_json_safe_converts_decimals_in_nested_structures():
    import json
    from decimal import Decimal
    from app.utils.discover_candidate_snapshot import _json_safe

    payload = {
        "prob": Decimal("0.5"),
        "nested": {"move": Decimal("0.1"), "flag": True, "name": "x"},
        "list": [Decimal("1.5"), 2, "y"],
    }
    safe = _json_safe(payload)
    # The whole point: it must now be JSON-serializable (the insert failure mode).
    json.dumps(safe)
    assert safe["prob"] == 0.5
    assert safe["nested"]["move"] == 0.1
    assert safe["nested"]["flag"] is True
    assert safe["list"][0] == 1.5


def test_json_safe_passes_through_plain_values():
    from app.utils.discover_candidate_snapshot import _json_safe

    assert _json_safe(None) is None
    assert _json_safe("hello") == "hello"
    assert _json_safe(7) == 7
    assert _json_safe(3.14) == 3.14


def test_build_candidate_features_output_is_json_serializable_after_sanitize():
    # End-to-end: real Decimal probabilities flow through build → sanitize → JSON.
    import json
    from decimal import Decimal
    from app.utils.discover_candidate_snapshot import _json_safe

    market = _market(outcomes=[_outcome(prob=Decimal("0.73"), move=Decimal("0.12"))])
    features = _json_safe(build_candidate_features(market, source_count=1))
    json.dumps(features)  # must not raise
