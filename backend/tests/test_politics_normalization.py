"""Tests for Politics page probability normalization (BR36 fix).

Independent binary markets ("Will X be the nominee?") produce probabilities
that can sum well over 100%.  The politics route must normalize these before
returning them to the frontend.
"""

from datetime import datetime, timezone
from types import SimpleNamespace

from app.routes.politics import (
    _build_presidential,
    _market_row,
    _normalize_outcome_probs,
)

#: A fixed anchor, because #3758 made the row a function of the clock as well as
#: the market. These tests are about NORMALIZATION and their candidate names
#: carry no dates, so the anchor only has to exist — the deadline ordering has
#: its own suite (`test_a_politics_ladder_stops_headlining_a_passed_deadline_3758`)
#: which sweeps the clock rather than pinning one instant (gotcha #44).
_NOW = datetime(2026, 9, 7, 12, 0, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# _normalize_outcome_probs — core helper
# ---------------------------------------------------------------------------


class TestNormalizeOutcomeProbs:
    """Unit tests for the shared normalization helper."""

    def test_no_normalization_when_under_threshold(self):
        outcomes = [{"prob": 40.0}, {"prob": 30.0}, {"prob": 25.0}]
        _normalize_outcome_probs(outcomes)
        assert outcomes == [{"prob": 40.0}, {"prob": 30.0}, {"prob": 25.0}]

    def test_no_normalization_at_exactly_105(self):
        outcomes = [{"prob": 55.0}, {"prob": 50.0}]
        _normalize_outcome_probs(outcomes)
        assert outcomes == [{"prob": 55.0}, {"prob": 50.0}]

    def test_normalization_when_over_threshold(self):
        outcomes = [{"prob": 80.0}, {"prob": 60.0}, {"prob": 40.0}, {"prob": 30.0}]
        _normalize_outcome_probs(outcomes)
        total = sum(o["prob"] for o in outcomes)
        assert 99.0 <= total <= 101.0, f"Sum should be ~100%, got {total}%"

    def test_preserves_relative_ordering(self):
        outcomes = [{"prob": 98.8}, {"prob": 24.5}, {"prob": 9.2}, {"prob": 8.2}]
        _normalize_outcome_probs(outcomes)
        probs = [o["prob"] for o in outcomes]
        assert probs == sorted(probs, reverse=True), "Order should be preserved"

    def test_custom_key(self):
        outcomes = [{"merged": 80.0}, {"merged": 60.0}, {"merged": 40.0}]
        _normalize_outcome_probs(outcomes, key="merged")
        total = sum(o["merged"] for o in outcomes)
        assert 99.0 <= total <= 101.0

    def test_handles_none_values(self):
        outcomes = [{"prob": 80.0}, {"prob": None}, {"prob": 60.0}]
        _normalize_outcome_probs(outcomes)
        # prob_sum = 140 > 105, so normalization happens
        assert outcomes[1]["prob"] is None  # None stays None

    def test_empty_list(self):
        outcomes = []
        _normalize_outcome_probs(outcomes)  # should not raise
        assert outcomes == []

    def test_bug_report_case(self):
        """Exact scenario from BR36: Democratic nominee probabilities >> 100%."""
        outcomes = [
            {"prob": 98.8},   # Keiko Fujimori (erroneous)
            {"prob": 24.5},   # Gavin Newsom
            {"prob": 9.2},    # Kamala Harris
            {"prob": 8.2},    # AOC
            {"prob": 5.0},    # Others
        ]
        _normalize_outcome_probs(outcomes)
        total = sum(o["prob"] for o in outcomes)
        assert total <= 101.0, f"Sum should be ≤101%, got {total}%"
        # Top candidate should be well below 100% after normalization
        assert outcomes[0]["prob"] < 100.0


# ---------------------------------------------------------------------------
# _market_row — per-market outcome normalization
# ---------------------------------------------------------------------------


def _make_outcome(name: str, prob: float):
    return SimpleNamespace(
        id=1, name=name, current_probability=prob, probability_change_24h=None, rank=None,
    )


def _make_market(
    name: str,
    outcomes: list,
    source: str | None = "kalshi",
    external_id: str = "kxtest",
    mutually_exclusive: bool | None = True,
):
    return SimpleNamespace(
        id=1,
        name=name,
        source=source,
        external_id=external_id,
        outcomes=outcomes,
        mutually_exclusive=mutually_exclusive,
    )


class TestMarketRowNormalization:
    """_market_row should normalize outcome probabilities when they sum > 105%."""

    def test_normal_market_unchanged(self):
        outcomes = [_make_outcome("Yes", 0.60), _make_outcome("No", 0.40)]
        market = _make_market("Will X happen?", outcomes)
        row = _market_row(market, now=_NOW)
        assert row["top_outcomes"][0]["prob"] == 60.0
        assert row["top_outcomes"][1]["prob"] == 40.0

    def test_independent_binary_market_normalized(self):
        """Multi-candidate independent binary markets get normalized."""
        outcomes = [
            _make_outcome("Trump", 0.55),
            _make_outcome("DeSantis", 0.40),
            _make_outcome("Haley", 0.30),
            _make_outcome("Ramaswamy", 0.20),
        ]
        market = _make_market("Who will win?", outcomes)
        row = _market_row(market, now=_NOW)
        total = sum(o["prob"] for o in row["top_outcomes"])
        # top 3 shown; their raw sum is 125% which exceeds 105%
        assert total <= 101.0, f"Top outcomes should sum ≤101%, got {total}%"

    def test_prob_field_matches_top_outcome(self):
        """The 'prob' field should equal the first outcome after normalization."""
        outcomes = [
            _make_outcome("Trump", 0.80),
            _make_outcome("DeSantis", 0.60),
            _make_outcome("Haley", 0.40),
        ]
        market = _make_market("Who wins?", outcomes)
        row = _market_row(market, now=_NOW)
        assert row["prob"] == row["top_outcomes"][0]["prob"]

    def test_market_row_requires_mutually_exclusive_true_and_90pct_mass_11949(self):
        """#11949 (#12126/#12128 guard): normalize only when mutually_exclusive is True and mass >= 0.9."""
        outcomes_over = [
            _make_outcome("Trump", 0.50),
            _make_outcome("DeSantis", 0.35),
            _make_outcome("Haley", 0.25),
        ]
        row_none = _market_row(
            _make_market("Who wins?", outcomes_over, mutually_exclusive=None),
            now=_NOW,
        )
        assert [o["prob"] for o in row_none["top_outcomes"]] == [50.0, 35.0, 25.0]

        outcomes_partial = [
            _make_outcome("Trump", 0.40),
            _make_outcome("DeSantis", 0.25),
            _make_outcome("Haley", 0.15),
        ]
        row_partial = _market_row(
            _make_market("Who wins?", outcomes_partial, mutually_exclusive=True),
            now=_NOW,
        )
        assert [o["prob"] for o in row_partial["top_outcomes"]] == [40.0, 25.0, 15.0]

    def test_market_row_refuses_blank_outcome_label_and_missing_source_stays_none_11949(self):
        """#11949 (#12126/#12128 guard): blank outcome labels are refused and missing source stays None."""
        outcomes = [
            _make_outcome("   ", 0.55),
            _make_outcome("Trump", 0.52),
            _make_outcome("DeSantis", 0.48),
        ]
        market = _make_market("Who wins?", outcomes, source=None, mutually_exclusive=True)
        row = _market_row(market, now=_NOW)
        assert [o["name"] for o in row["top_outcomes"]] == ["Trump", "DeSantis"]
        assert row["src"] is None

        all_blank = [_make_outcome("", 0.60), _make_outcome("  ", 0.40)]
        assert _market_row(_make_market("Who wins?", all_blank), now=_NOW) is None


# ---------------------------------------------------------------------------
# _build_presidential — candidate-level normalization
# ---------------------------------------------------------------------------


def _make_full_outcome(name: str, prob: float, oid: int = 1):
    return SimpleNamespace(
        id=oid, name=name, current_probability=prob, probability_change_24h=None, rank=None,
    )


def _make_full_market(
    name: str, outcomes: list, source: str = "kalshi", external_id: str = "kxpres2028",
    market_id: int = 1, mutually_exclusive: bool | None = True,
):
    return SimpleNamespace(
        id=market_id, name=name, source=source, external_id=external_id, outcomes=outcomes,
        mutually_exclusive=mutually_exclusive,
    )


class TestBuildPresidentialNormalization:
    """_build_presidential should normalize when candidate probs sum > 105%."""

    def test_candidates_normalized_single_source(self):
        """Kalshi headline with inflated probabilities."""
        outcomes = [
            _make_full_outcome("Trump", 0.45, oid=1),
            _make_full_outcome("DeSantis", 0.30, oid=2),
            _make_full_outcome("Haley", 0.25, oid=3),
            _make_full_outcome("Ramaswamy", 0.15, oid=4),
        ]
        market = _make_full_market(
            "Who will win the 2028 presidential election?",
            outcomes, source="kalshi", market_id=100,
        )
        response, _ = _build_presidential([market], now=_NOW)
        merged_sum = sum(c["merged"] for c in response["candidates"])
        assert merged_sum <= 101.0, f"Merged sum should be ≤101%, got {merged_sum}%"

    def test_candidates_normalized_dual_source(self):
        """Both Kalshi and Polymarket have inflated probabilities."""
        kalshi_outcomes = [
            _make_full_outcome("Trump", 0.50, oid=1),
            _make_full_outcome("DeSantis", 0.35, oid=2),
            _make_full_outcome("Haley", 0.25, oid=3),
        ]
        poly_outcomes = [
            _make_full_outcome("Trump", 0.55, oid=4),
            _make_full_outcome("DeSantis", 0.35, oid=5),
            _make_full_outcome("Haley", 0.25, oid=6),
        ]
        kalshi_market = _make_full_market(
            "Who will win the 2028 presidential election?",
            kalshi_outcomes, source="kalshi", market_id=100,
        )
        poly_market = _make_full_market(
            "Who will win the 2028 presidential election?",
            poly_outcomes, source="polymarket", external_id="polymarket_123", market_id=200,
        )
        response, _ = _build_presidential([kalshi_market, poly_market], now=_NOW)
        merged_sum = sum(c["merged"] for c in response["candidates"])
        assert merged_sum <= 101.0, f"Merged sum should be ≤101%, got {merged_sum}%"

    def test_no_normalization_when_under_threshold(self):
        """Reasonable probabilities left alone."""
        outcomes = [
            _make_full_outcome("Trump", 0.45, oid=1),
            _make_full_outcome("DeSantis", 0.25, oid=2),
            _make_full_outcome("Haley", 0.15, oid=3),
        ]
        market = _make_full_market(
            "Who will win the 2028 presidential election?",
            outcomes, source="kalshi", market_id=100,
        )
        response, _ = _build_presidential([market], now=_NOW)
        # Raw sum is 85%, under threshold — should be unchanged
        assert response["candidates"][0]["merged"] == 45.0
        assert response["candidates"][1]["merged"] == 25.0
        assert response["candidates"][2]["merged"] == 15.0

    def test_one_cent_floor_legs_excluded_from_presidential_divisor_12093(self):
        """#12093 (Defects 1 & 5a): Kalshi 1c floor bounds must not dilute the field."""
        outcomes = [
            _make_full_outcome("Jon Ossoff", 0.50, oid=1),
            _make_full_outcome("Alexandria Ocasio-Cortez", 0.30, oid=2),
            _make_full_outcome("Gavin Newsom", 0.20, oid=3),
            *[
                _make_full_outcome(f"Longshot {i}", 0.01, oid=10 + i)
                for i in range(12)
            ],
        ]
        market = _make_full_market(
            "2028 Democratic presidential nominee",
            outcomes,
            source="kalshi",
            market_id=108445,
        )
        response, _ = _build_presidential([market], now=_NOW)
        by_name = {c["name"]: c for c in response["candidates"]}
        assert by_name["Jon Ossoff"]["kalshi"] == 50.0
        assert by_name["Jon Ossoff"]["merged"] == 50.0

    def test_presidential_uses_blend_probabilities_not_plain_mean_12093(self):
        """#12093 (Defect 1): _build_presidential blends via blend_probabilities."""
        kalshi_outcomes = [
            _make_full_outcome("Jon Ossoff", 0.60, oid=1),
            _make_full_outcome("Gavin Newsom", 0.25, oid=2),
            _make_full_outcome("Josh Shapiro", 0.15, oid=3),
        ]
        poly_outcomes = [
            # 45pt spread on Jon Ossoff trips blend_probabilities's 40pt divergence gate
            _make_full_outcome("Jon Ossoff", 0.15, oid=4),
            _make_full_outcome("Gavin Newsom", 0.25, oid=5),
            _make_full_outcome("Josh Shapiro", 0.15, oid=6),
        ]
        kalshi_market = _make_full_market(
            "2028 Democratic presidential nominee",
            kalshi_outcomes,
            source="kalshi",
            market_id=108445,
        )
        poly_market = _make_full_market(
            "Democratic Presidential Nominee 2028",
            poly_outcomes,
            source="polymarket",
            external_id="poly_dem",
            market_id=112895,
        )
        response, _ = _build_presidential([kalshi_market, poly_market], now=_NOW)
        by_name = {c["name"]: c for c in response["candidates"]}
        # Plain mean of (60, 15) would be 37.5; blend_probabilities gates at >=40pt spread to 60.0
        assert by_name["Jon Ossoff"]["merged"] == 60.0

    def test_presidential_mutually_exclusive_none_not_rescaled_12093(self):
        """#12093: a venue market with mutually_exclusive=None is not rescaled."""
        outcomes = [
            _make_full_outcome("Trump", 0.50, oid=1),
            _make_full_outcome("DeSantis", 0.35, oid=2),
            _make_full_outcome("Haley", 0.30, oid=3),
        ]
        market = _make_full_market(
            "Who will win the 2028 presidential election?",
            outcomes,
            source="kalshi",
            market_id=100,
            mutually_exclusive=None,
        )
        response, _ = _build_presidential([market], now=_NOW)
        by_name = {c["name"]: c for c in response["candidates"]}
        assert by_name["Trump"]["kalshi"] == 50.0
        assert by_name["DeSantis"]["kalshi"] == 35.0
        assert by_name["Haley"]["kalshi"] == 30.0
        assert by_name["Trump"]["merged"] == 50.0

    def test_presidential_fallback_when_blend_returns_none_12093(self, monkeypatch):
        """#12093: if blend_probabilities returns None, _build_presidential falls back
        to the arithmetic mean rather than emitting 0.0."""
        import app.utils.futures_source_merge as fsm

        monkeypatch.setattr(fsm, "blend_probabilities", lambda _inputs: None)
        kalshi_outcomes = [
            _make_full_outcome("Jon Ossoff", 0.60, oid=1),
            _make_full_outcome("Gavin Newsom", 0.25, oid=2),
            _make_full_outcome("Josh Shapiro", 0.15, oid=3),
        ]
        poly_outcomes = [
            _make_full_outcome("Jon Ossoff", 0.15, oid=4),
            _make_full_outcome("Gavin Newsom", 0.25, oid=5),
            _make_full_outcome("Josh Shapiro", 0.15, oid=6),
        ]
        kalshi_market = _make_full_market(
            "2028 Democratic presidential nominee",
            kalshi_outcomes,
            source="kalshi",
            market_id=108445,
        )
        poly_market = _make_full_market(
            "Democratic Presidential Nominee 2028",
            poly_outcomes,
            source="polymarket",
            external_id="poly_dem",
            market_id=112895,
        )
        response, _ = _build_presidential([kalshi_market, poly_market], now=_NOW)
        by_name = {c["name"]: c for c in response["candidates"]}
        assert by_name["Jon Ossoff"]["merged"] == 37.5
        assert by_name["Jon Ossoff"]["merged"] != 0.0

