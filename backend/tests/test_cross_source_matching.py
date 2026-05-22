"""Unit tests for the shared cross-source matching utility.

Tests the extracted helpers in app.utils.cross_source_matching that are used
by politics.py, entertainment.py, and economics.py.
"""

from types import SimpleNamespace

import pytest

from app.utils.cross_source_matching import (
    GARBAGE_OUTCOME_RE,
    clean_outcomes,
    find_cross_source_markets,
    is_resolved,
    normalize_question,
    source,
)

# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------


def _outcome(name: str, probability: float) -> SimpleNamespace:
    return SimpleNamespace(name=name, current_probability=probability)


def _market(
    *,
    market_id: int = 1,
    name: str = "Will it happen?",
    src: str = "kalshi",
    outcomes: list | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=market_id,
        name=name,
        source=src,
        outcomes=outcomes or [_outcome("Yes", 0.6), _outcome("No", 0.4)],
    )


def _simple_row_fn(market):
    """Minimal market_row_fn for testing."""
    if not market.outcomes:
        return None
    top = max(market.outcomes, key=lambda o: float(o.current_probability or 0))
    return {
        "q": market.name,
        "prob": round(float(top.current_probability or 0) * 100, 1),
        "src": source(market),
        "market_id": market.id,
    }


# ---------------------------------------------------------------------------
# normalize_question
# ---------------------------------------------------------------------------


class TestNormalizeQuestion:
    def test_lowercase_and_strip_punctuation(self):
        assert normalize_question("Will it rain?!") == "will it rain"

    def test_preserves_alphanumeric(self):
        assert normalize_question("GDP growth 2026") == "gdp growth 2026"

    def test_strips_leading_trailing_whitespace(self):
        assert normalize_question("  hello  ") == "hello"

    def test_empty_string(self):
        assert normalize_question("") == ""

    def test_all_punctuation(self):
        assert normalize_question("???!!!") == ""


# ---------------------------------------------------------------------------
# source
# ---------------------------------------------------------------------------


class TestSource:
    def test_returns_lowercase(self):
        m = _market(src="Kalshi")
        assert source(m) == "kalshi"

    def test_none_source(self):
        m = SimpleNamespace(source=None)
        assert source(m) == ""


# ---------------------------------------------------------------------------
# is_resolved
# ---------------------------------------------------------------------------


class TestIsResolved:
    def test_not_resolved_when_below_99(self):
        m = _market(outcomes=[_outcome("Yes", 0.98), _outcome("No", 0.02)])
        assert is_resolved(m) is False

    def test_resolved_when_at_99(self):
        m = _market(outcomes=[_outcome("Yes", 0.99), _outcome("No", 0.01)])
        assert is_resolved(m) is True

    def test_resolved_when_above_99(self):
        m = _market(outcomes=[_outcome("Yes", 1.0), _outcome("No", 0.0)])
        assert is_resolved(m) is True

    def test_no_outcomes(self):
        m = _market(outcomes=[])
        assert is_resolved(m) is False


# ---------------------------------------------------------------------------
# clean_outcomes
# ---------------------------------------------------------------------------


class TestCleanOutcomes:
    def test_filters_garbage_outcomes(self):
        outcomes = [
            _outcome("Player A", 0.5),
            _outcome("Real Candidate", 0.5),
        ]
        result = clean_outcomes(outcomes)
        assert len(result) == 1
        assert result[0].name == "Real Candidate"

    def test_keeps_all_real_outcomes(self):
        outcomes = [_outcome("Trump", 0.6), _outcome("Harris", 0.4)]
        result = clean_outcomes(outcomes)
        assert len(result) == 2

    def test_filters_various_garbage_patterns(self):
        garbage = [
            _outcome("Candidate B", 0.5),
            _outcome("Option AB", 0.3),
            _outcome("Person C", 0.2),
        ]
        result = clean_outcomes(garbage)
        assert len(result) == 0

    def test_empty_list(self):
        assert clean_outcomes([]) == []


# ---------------------------------------------------------------------------
# find_cross_source_markets
# ---------------------------------------------------------------------------


class TestFindCrossSourceMarkets:
    def test_matching_identical_names_different_sources(self):
        """Two markets with identical normalized names but different sources should match."""
        markets = [
            _market(
                market_id=1,
                name="Will GDP grow?",
                src="kalshi",
                outcomes=[_outcome("Yes", 0.7), _outcome("No", 0.3)],
            ),
            _market(
                market_id=2,
                name="Will GDP grow?",
                src="polymarket",
                outcomes=[_outcome("Yes", 0.6), _outcome("No", 0.4)],
            ),
        ]
        result = find_cross_source_markets(markets, market_row_fn=_simple_row_fn)
        assert len(result) == 1
        assert result[0]["q"] == "Will GDP grow?"
        assert result[0]["kalshi"] == 70.0
        assert result[0]["poly"] == 60.0
        assert result[0]["delta"] == 10.0
        assert result[0]["kalshi_market_id"] == 1
        assert result[0]["poly_market_id"] == 2

    def test_slightly_different_names_not_matched(self):
        """Two markets with slightly different names should NOT be matched."""
        markets = [
            _market(
                market_id=1,
                name="Will GDP grow in 2026?",
                src="kalshi",
                outcomes=[_outcome("Yes", 0.7), _outcome("No", 0.3)],
            ),
            _market(
                market_id=2,
                name="Will GDP grow in 2027?",
                src="polymarket",
                outcomes=[_outcome("Yes", 0.6), _outcome("No", 0.4)],
            ),
        ]
        result = find_cross_source_markets(markets, market_row_fn=_simple_row_fn)
        assert len(result) == 0

    def test_paraphrased_names_matched(self):
        """Obvious wording differences should match when entity/year align."""
        markets = [
            _market(
                market_id=1,
                name="Will Donald Trump win the 2028 US presidential election?",
                src="kalshi",
                outcomes=[_outcome("Yes", 0.7), _outcome("No", 0.3)],
            ),
            _market(
                market_id=2,
                name="Donald Trump to win the 2028 US presidency?",
                src="polymarket",
                outcomes=[_outcome("Yes", 0.6), _outcome("No", 0.4)],
            ),
        ]
        result = find_cross_source_markets(markets, market_row_fn=_simple_row_fn)
        assert len(result) == 1
        assert result[0]["kalshi_market_id"] == 1
        assert result[0]["poly_market_id"] == 2

    def test_near_miss_entity_mismatch_not_matched(self):
        """Similar structure should not match when the main entity differs."""
        markets = [
            _market(
                market_id=1,
                name="Will Donald Trump win the 2028 US presidential election?",
                src="kalshi",
                outcomes=[_outcome("Yes", 0.7), _outcome("No", 0.3)],
            ),
            _market(
                market_id=2,
                name="Ron DeSantis to win the 2028 US presidency?",
                src="polymarket",
                outcomes=[_outcome("Yes", 0.6), _outcome("No", 0.4)],
            ),
        ]
        result = find_cross_source_markets(markets, market_row_fn=_simple_row_fn)
        assert len(result) == 0

    def test_resolved_market_excluded(self):
        """A resolved market (outcome >= 99%) should be excluded."""
        markets = [
            _market(
                market_id=1,
                name="Will it happen?",
                src="kalshi",
                outcomes=[_outcome("Yes", 0.99), _outcome("No", 0.01)],
            ),
            _market(
                market_id=2,
                name="Will it happen?",
                src="polymarket",
                outcomes=[_outcome("Yes", 0.6), _outcome("No", 0.4)],
            ),
        ]
        result = find_cross_source_markets(markets, market_row_fn=_simple_row_fn)
        assert len(result) == 0

    def test_same_source_twice_only_first_kept(self):
        """When two markets from the same source have the same normalized name,
        only the first encountered should be kept."""
        markets = [
            _market(
                market_id=1,
                name="Will it rain?",
                src="kalshi",
                outcomes=[_outcome("Yes", 0.8), _outcome("No", 0.2)],
            ),
            _market(
                market_id=2,
                name="Will it rain?",
                src="kalshi",
                outcomes=[_outcome("Yes", 0.5), _outcome("No", 0.5)],
            ),
            _market(
                market_id=3,
                name="Will it rain?",
                src="polymarket",
                outcomes=[_outcome("Yes", 0.6), _outcome("No", 0.4)],
            ),
        ]
        result = find_cross_source_markets(markets, market_row_fn=_simple_row_fn)
        assert len(result) == 1
        # First Kalshi market (id=1, prob=80%) should be used
        assert result[0]["kalshi"] == 80.0
        assert result[0]["kalshi_market_id"] == 1

    def test_delta_computed_correctly(self):
        """Delta should be abs(kalshi_prob - poly_prob), rounded to 1 decimal."""
        markets = [
            _market(
                market_id=1,
                name="Test question?",
                src="kalshi",
                outcomes=[_outcome("Yes", 0.75), _outcome("No", 0.25)],
            ),
            _market(
                market_id=2,
                name="Test question?",
                src="polymarket",
                outcomes=[_outcome("Yes", 0.55), _outcome("No", 0.45)],
            ),
        ]
        result = find_cross_source_markets(markets, market_row_fn=_simple_row_fn)
        assert len(result) == 1
        # _simple_row_fn takes the max outcome: kalshi=75.0, poly=55.0
        assert result[0]["delta"] == 20.0

    def test_max_results_honored(self):
        """Should return at most max_results matches."""
        markets = []
        for i in range(20):
            markets.append(
                _market(
                    market_id=i * 2,
                    name=f"Question {i}?",
                    src="kalshi",
                    outcomes=[
                        _outcome("Yes", 0.5 + i * 0.01),
                        _outcome("No", 0.5 - i * 0.01),
                    ],
                )
            )
            markets.append(
                _market(
                    market_id=i * 2 + 1,
                    name=f"Question {i}?",
                    src="polymarket",
                    outcomes=[_outcome("Yes", 0.4), _outcome("No", 0.6)],
                )
            )
        result = find_cross_source_markets(
            markets, market_row_fn=_simple_row_fn, max_results=3
        )
        assert len(result) == 3

    def test_sorted_by_delta_descending(self):
        """Results should be sorted by delta in descending order."""
        markets = [
            _market(
                market_id=1,
                name="Small delta?",
                src="kalshi",
                outcomes=[_outcome("Yes", 0.51), _outcome("No", 0.49)],
            ),
            _market(
                market_id=2,
                name="Small delta?",
                src="polymarket",
                outcomes=[_outcome("Yes", 0.50), _outcome("No", 0.50)],
            ),
            _market(
                market_id=3,
                name="Big delta?",
                src="kalshi",
                outcomes=[_outcome("Yes", 0.90), _outcome("No", 0.10)],
            ),
            _market(
                market_id=4,
                name="Big delta?",
                src="polymarket",
                outcomes=[_outcome("Yes", 0.40), _outcome("No", 0.60)],
            ),
        ]
        result = find_cross_source_markets(markets, market_row_fn=_simple_row_fn)
        assert len(result) == 2
        assert result[0]["delta"] > result[1]["delta"]
        assert result[0]["q"] == "Big delta?"

    def test_non_kalshi_polymarket_sources_excluded(self):
        """Markets from sources other than kalshi/polymarket should be ignored."""
        markets = [
            _market(
                market_id=1,
                name="Will it happen?",
                src="oddapi",
                outcomes=[_outcome("Yes", 0.7), _outcome("No", 0.3)],
            ),
            _market(
                market_id=2,
                name="Will it happen?",
                src="espn",
                outcomes=[_outcome("Yes", 0.6), _outcome("No", 0.4)],
            ),
        ]
        result = find_cross_source_markets(markets, market_row_fn=_simple_row_fn)
        assert len(result) == 0

    def test_row_fn_returning_none_skips_market(self):
        """If market_row_fn returns None, the market should be skipped."""
        markets = [
            _market(
                market_id=1,
                name="Will it happen?",
                src="kalshi",
                outcomes=[_outcome("Yes", 0.7), _outcome("No", 0.3)],
            ),
            _market(
                market_id=2,
                name="Will it happen?",
                src="polymarket",
                outcomes=[_outcome("Yes", 0.6), _outcome("No", 0.4)],
            ),
        ]

        def skip_all(m):
            return None

        result = find_cross_source_markets(markets, market_row_fn=skip_all)
        assert len(result) == 0

    def test_empty_markets_list(self):
        """Empty input should return empty output."""
        result = find_cross_source_markets([], market_row_fn=_simple_row_fn)
        assert result == []

    def test_extra_fields_from_row_fn_propagated(self):
        """Extra fields like 'theme' from the row function should appear in category."""
        markets = [
            _market(
                market_id=1,
                name="Will it rain?",
                src="kalshi",
                outcomes=[_outcome("Yes", 0.7), _outcome("No", 0.3)],
            ),
            _market(
                market_id=2,
                name="Will it rain?",
                src="polymarket",
                outcomes=[_outcome("Yes", 0.5), _outcome("No", 0.5)],
            ),
        ]

        def row_fn_with_theme(m):
            row = _simple_row_fn(m)
            if row:
                row["theme"] = "weather"
            return row

        result = find_cross_source_markets(markets, market_row_fn=row_fn_with_theme)
        assert len(result) == 1
        assert result[0]["category"] == "weather"
