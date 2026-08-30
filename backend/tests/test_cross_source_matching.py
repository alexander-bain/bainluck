"""Unit tests for the shared cross-source matching utility.

Tests the extracted helpers in app.utils.cross_source_matching that are used
by politics.py, entertainment.py, and economics.py.
"""

from types import SimpleNamespace

import pytest

from app.utils.cross_source_matching import (
    GARBAGE_OUTCOME_RE,
    align_on_shared_outcome,
    clean_outcomes,
    find_cross_source_markets,
    group_markets_by_group_id,
    is_resolved,
    normalize_question,
    source,
)

# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------


def _outcome(
    name: str, probability: float, external_id: str | None = None
) -> SimpleNamespace:
    # `external_id` is NOT optional on the real FuturesOutcome, and UX-P188's leg
    # drop reads it, so the stub carries one. Defaulting it off the NAME keeps every
    # pre-existing caller distinct-by-construction (two outcomes in one market never
    # share a name), which is what the drop's sibling lookup needs.
    return SimpleNamespace(
        name=name,
        current_probability=probability,
        external_id=external_id if external_id is not None else f"xid-{name}",
    )


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
    """Minimal market_row_fn for testing.

    Mirrors the three real producers (`politics`, `economics` and
    `entertainment` `_market_row`): a ranked ``top_outcomes`` of the three
    best-priced outcomes, with ``prob`` being the leader's. ``top_outcomes``
    is part of the contract — ``find_cross_source_markets`` aligns the two
    sources on a shared outcome name and reports nothing for a row that
    cannot say what its number is about.
    """
    if not market.outcomes:
        return None
    ranked = sorted(
        market.outcomes,
        key=lambda o: float(o.current_probability or 0),
        reverse=True,
    )
    return {
        "q": market.name,
        "prob": round(float(ranked[0].current_probability or 0) * 100, 1),
        "src": source(market),
        "market_id": market.id,
        "top_outcomes": [
            {
                "name": o.name,
                "prob": round(float(o.current_probability or 0) * 100, 1),
            }
            for o in ranked[:3]
        ],
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


# ---------------------------------------------------------------------------
# group_markets_by_group_id
# ---------------------------------------------------------------------------


def _grouped_market(
    *,
    market_id: int = 1,
    name: str = "Will it happen?",
    group_id: str | None = None,
    outcomes: list | None = None,
    volume_24h: float | None = None,
) -> SimpleNamespace:
    """Create a market-like object with group_id support."""
    return SimpleNamespace(
        id=market_id,
        name=name,
        group_id=group_id,
        source="polymarket",
        outcomes=outcomes or [_outcome("Yes", 0.6), _outcome("No", 0.4)],
        volume_24h=volume_24h,
    )


class TestGroupMarketsByGroupId:
    def test_null_group_id_passes_through(self):
        """Markets with no group_id should pass through unchanged."""
        markets = [
            _grouped_market(market_id=1, group_id=None),
            _grouped_market(market_id=2, group_id=None),
        ]
        result = group_markets_by_group_id(markets)
        assert len(result) == 2

    def test_single_member_group_passes_through(self):
        """A group with only one member should pass through unchanged."""
        markets = [
            _grouped_market(market_id=1, group_id="g1"),
        ]
        result = group_markets_by_group_id(markets)
        assert len(result) == 1

    def test_group_collapses_to_one_representative(self):
        """Multiple markets with the same group_id should collapse to one."""
        markets = [
            _grouped_market(
                market_id=1,
                name="Will A win Best Picture?",
                group_id="polymarket:123",
                outcomes=[_outcome("Yes", 0.3), _outcome("No", 0.7)],
            ),
            _grouped_market(
                market_id=2,
                name="Will B win Best Picture?",
                group_id="polymarket:123",
                outcomes=[_outcome("Yes", 0.5), _outcome("No", 0.5)],
            ),
            _grouped_market(
                market_id=3,
                name="Will C win Best Picture?",
                group_id="polymarket:123",
                outcomes=[_outcome("Yes", 0.2), _outcome("No", 0.8)],
            ),
        ]
        result = group_markets_by_group_id(markets)
        assert len(result) == 1

    def test_group_merges_unique_outcomes(self):
        """The representative should have merged unique outcomes from all siblings."""
        markets = [
            _grouped_market(
                market_id=1,
                name="Who wins Best Picture?",
                group_id="polymarket:123",
                outcomes=[_outcome("Movie A", 0.3)],
            ),
            _grouped_market(
                market_id=2,
                name="Who wins Best Picture?",
                group_id="polymarket:123",
                outcomes=[_outcome("Movie B", 0.5)],
            ),
            _grouped_market(
                market_id=3,
                name="Who wins Best Picture?",
                group_id="polymarket:123",
                outcomes=[_outcome("Movie C", 0.2)],
            ),
        ]
        result = group_markets_by_group_id(markets)
        assert len(result) == 1
        outcome_names = {o.name for o in result[0].outcomes}
        assert outcome_names == {"Movie A", "Movie B", "Movie C"}

    def test_duplicate_outcome_names_not_merged(self):
        """Outcomes with the same name (case-insensitive) should not be duplicated."""
        markets = [
            _grouped_market(
                market_id=1,
                name="Q1",
                group_id="g1",
                outcomes=[_outcome("Yes", 0.6), _outcome("No", 0.4)],
            ),
            _grouped_market(
                market_id=2,
                name="Q2",
                group_id="g1",
                outcomes=[_outcome("Yes", 0.5), _outcome("No", 0.5)],
            ),
        ]
        result = group_markets_by_group_id(markets)
        assert len(result) == 1
        # Both markets have "Yes" and "No" — should not duplicate
        outcome_names = [o.name for o in result[0].outcomes]
        assert outcome_names.count("Yes") == 1
        assert outcome_names.count("No") == 1

    def test_representative_has_most_outcomes(self):
        """The market with the most outcomes should be the representative."""
        markets = [
            _grouped_market(
                market_id=1,
                name="Small market",
                group_id="g1",
                outcomes=[_outcome("A", 0.5)],
            ),
            _grouped_market(
                market_id=2,
                name="Big market",
                group_id="g1",
                outcomes=[_outcome("X", 0.3), _outcome("Y", 0.4), _outcome("Z", 0.3)],
            ),
        ]
        result = group_markets_by_group_id(markets)
        assert len(result) == 1
        assert result[0].id == 2  # market with most outcomes is representative

    def test_volume_tiebreaker(self):
        """When outcome counts are equal, higher volume_24h wins."""
        markets = [
            _grouped_market(
                market_id=1,
                name="Low volume",
                group_id="g1",
                outcomes=[_outcome("Yes", 0.5)],
                volume_24h=100,
            ),
            _grouped_market(
                market_id=2,
                name="High volume",
                group_id="g1",
                outcomes=[_outcome("Yes", 0.6)],
                volume_24h=5000,
            ),
        ]
        result = group_markets_by_group_id(markets)
        assert len(result) == 1
        assert result[0].id == 2

    def test_mixed_grouped_and_ungrouped(self):
        """Ungrouped and grouped markets should both appear in output."""
        markets = [
            _grouped_market(market_id=1, group_id=None),
            _grouped_market(market_id=2, group_id="g1"),
            _grouped_market(market_id=3, group_id="g1"),
            _grouped_market(market_id=4, group_id=None),
        ]
        result = group_markets_by_group_id(markets)
        # 2 ungrouped + 1 collapsed group = 3
        assert len(result) == 3
        result_ids = {m.id for m in result}
        assert 1 in result_ids
        assert 4 in result_ids

    def test_multiple_distinct_groups(self):
        """Different group_ids should create separate groups."""
        markets = [
            _grouped_market(market_id=1, group_id="g1"),
            _grouped_market(market_id=2, group_id="g1"),
            _grouped_market(market_id=3, group_id="g2"),
            _grouped_market(market_id=4, group_id="g2"),
        ]
        result = group_markets_by_group_id(markets)
        assert len(result) == 2

    def test_empty_input(self):
        """Empty input should return empty output."""
        result = group_markets_by_group_id([])
        assert result == []

    def test_does_not_mutate_input_list(self):
        """The original list should not be modified."""
        markets = [
            _grouped_market(market_id=1, group_id="g1"),
            _grouped_market(market_id=2, group_id="g1"),
        ]
        original_len = len(markets)
        group_markets_by_group_id(markets)
        assert len(markets) == original_len

    def test_objects_without_group_id_attribute(self):
        """Objects without a group_id attribute should be treated as ungrouped."""
        markets = [
            SimpleNamespace(id=1, name="No group_id attr", outcomes=[], source="x"),
            SimpleNamespace(id=2, name="Also no group_id", outcomes=[], source="y"),
        ]
        result = group_markets_by_group_id(markets)
        assert len(result) == 2


# ---------------------------------------------------------------------------
# UX-P187 — a spread is only a spread when both numbers price the same outcome
# ---------------------------------------------------------------------------


def _row(
    *,
    market_id: int,
    q: str,
    src: str,
    outcomes: list[tuple[str, float]],
    theme: str = "",
) -> dict:
    """A market_row_fn output, shaped like the three real producers."""
    ranked = sorted(outcomes, key=lambda o: -o[1])
    return {
        "q": q,
        "prob": ranked[0][1],
        "src": src,
        "market_id": market_id,
        "top_outcomes": [{"name": n, "prob": p} for n, p in ranked[:3]],
        "outcome_count": len(ranked),
        "theme": theme,
    }


def _pair_row_fn(rows: dict[int, dict]):
    """Serve pre-built rows by market id, so a test states its rows directly."""
    return lambda m: rows.get(m.id)


def _stub(market_id: int, name: str, src: str) -> SimpleNamespace:
    return SimpleNamespace(
        id=market_id,
        name=name,
        source=src,
        outcomes=[_outcome("placeholder", 0.5)],
    )


class TestAlignOnSharedOutcome:
    """The unit that decides whether two numbers may be subtracted."""

    def test_leaders_agree_so_that_outcome_is_the_comparison(self):
        k = _row(
            market_id=1,
            q="Next President of Estonia?",
            src="kalshi",
            outcomes=[("Ülle Madise", 97.5), ("Alar Karis", 1.5)],
        )
        p = _row(
            market_id=2,
            q="Next President of Estonia?",
            src="polymarket",
            outcomes=[("Ülle Madise", 34.6), ("Alar Karis", 30.0)],
        )
        assert align_on_shared_outcome(k, p) == ("Ülle Madise", 97.5, 34.6)

    def test_no_shared_outcome_is_not_comparable(self):
        """The Louisiana shape: Kalshi prices 'exactly 1 seat', Polymarket '9'.

        Both markets answer "how many House seats", neither prices anything the
        other prices, and there is no honest single number to show.
        """
        k = _row(
            market_id=1,
            q="How many House seats will Democrats win in Louisiana?",
            src="kalshi",
            outcomes=[
                ("Will Democrats win exactly 1 seats ...?", 92.5),
                ("Will Democrats win exactly 2 seats ...?", 6.0),
            ],
        )
        p = _row(
            market_id=2,
            q="How many House seats will Democrats win in Louisiana?",
            src="polymarket",
            outcomes=[("9", 36.0), ("8", 30.0)],
        )
        assert align_on_shared_outcome(k, p) is None

    def test_a_cumulative_ladder_against_discrete_brackets_is_dropped(self):
        """gotcha #17: 'Above 2.2%' and '2.4%' are not the same quantity, and
        no amount of arithmetic makes them one."""
        k = _row(
            market_id=1,
            q="Core inflation in August 2026?",
            src="kalshi",
            outcomes=[("Above 2.2%", 98.0), ("Above 2.4%", 71.0)],
        )
        p = _row(
            market_id=2,
            q="Core inflation in August 2026?",
            src="polymarket",
            outcomes=[("2.4%", 31.5), ("2.5%", 24.0)],
        )
        assert align_on_shared_outcome(k, p) is None

    def test_leaders_differ_but_a_shared_outcome_rescues_the_pair(self):
        """The Anthropic-IPO shape. Kalshi leads Goldman, Polymarket leads
        Morgan Stanley; both price both, so there is a real comparison and it
        is a more interesting one than either leader alone."""
        k = _row(
            market_id=1,
            q="Which bank will lead Anthropic's IPO?",
            src="kalshi",
            outcomes=[("Goldman Sachs", 65.5), ("Morgan Stanley", 20.0)],
        )
        p = _row(
            market_id=2,
            q="Which bank will lead Anthropic's IPO?",
            src="polymarket",
            outcomes=[("Morgan Stanley", 50.0), ("Goldman Sachs", 12.0)],
        )
        # Goldman is the highest-priced shared outcome on either side, so it is
        # the one compared — 65.5 vs 12.0, not 65.5 vs 50.0.
        assert align_on_shared_outcome(k, p) == ("Goldman Sachs", 65.5, 12.0)

    def test_case_and_spacing_do_not_hide_a_shared_outcome(self):
        k = _row(
            market_id=1, q="Q?", src="kalshi", outcomes=[("Ed  MARKEY", 66.5)]
        )
        p = _row(
            market_id=2, q="Q?", src="polymarket", outcomes=[("ed markey", 18.5)]
        )
        aligned = align_on_shared_outcome(k, p)
        assert aligned is not None
        # Kalshi's spelling is the one shown, deterministically.
        assert aligned[0] == "Ed  MARKEY"
        assert aligned[1:] == (66.5, 18.5)

    def test_distinct_bracket_labels_are_not_folded_together(self):
        """The key is deliberately conservative. A normalizer that stripped
        punctuation would make '2.4%' and '24%' — or '$800-900B' and
        '800 900B' — the same outcome and invent a comparison."""
        k = _row(market_id=1, q="Q?", src="kalshi", outcomes=[("2.4%", 40.0)])
        p = _row(market_id=2, q="Q?", src="polymarket", outcomes=[("24%", 9.0)])
        assert align_on_shared_outcome(k, p) is None

    def test_a_row_without_top_outcomes_can_never_be_aligned(self):
        k = {"q": "Q?", "prob": 60.0, "src": "kalshi", "market_id": 1}
        p = _row(market_id=2, q="Q?", src="polymarket", outcomes=[("Yes", 40.0)])
        assert align_on_shared_outcome(k, p) is None
        assert align_on_shared_outcome(p, k) is None

    def test_blank_outcome_names_are_not_a_shared_outcome(self):
        """Two nameless outcomes normalize to the same empty key, so without
        the filter they read as "both sources price the same thing" and the
        card gets a spread with nothing above it. Asserted on BOTH sides
        independently: one filter alone masks the other's removal, so a
        one-sided check cannot see half the defect."""
        blank_k = _row(market_id=1, q="Q?", src="kalshi", outcomes=[("", 60.0)])
        blank_p = _row(market_id=2, q="Q?", src="polymarket", outcomes=[(" ", 40.0)])
        named_k = _row(market_id=3, q="Q?", src="kalshi", outcomes=[("Yes", 60.0)])
        named_p = _row(market_id=4, q="Q?", src="polymarket", outcomes=[("Yes", 40.0)])
        assert align_on_shared_outcome(blank_k, blank_p) is None
        assert align_on_shared_outcome(blank_k, named_p) is None
        assert align_on_shared_outcome(named_k, blank_p) is None
        # ...and the control: the same shapes, named, do align.
        assert align_on_shared_outcome(named_k, named_p) == ("Yes", 60.0, 40.0)


class TestSpotlightOnlyComparesLikeWithLike:
    """The same rule, driven through the real `find_cross_source_markets`."""

    def test_an_incomparable_pair_produces_no_row(self):
        markets = [
            _stub(1, "How many House seats will Democrats win in Louisiana?", "kalshi"),
            _stub(2, "How many House seats will Democrats win in Louisiana?", "polymarket"),
        ]
        rows = {
            1: _row(
                market_id=1,
                q="How many House seats will Democrats win in Louisiana?",
                src="kalshi",
                outcomes=[("exactly 1 seats", 92.5)],
            ),
            2: _row(
                market_id=2,
                q="How many House seats will Democrats win in Louisiana?",
                src="polymarket",
                outcomes=[("9", 36.0)],
            ),
        }
        assert find_cross_source_markets(markets, market_row_fn=_pair_row_fn(rows)) == []

    def test_a_comparable_pair_names_the_outcome_it_prices(self):
        markets = [
            _stub(1, "Next President of Estonia?", "kalshi"),
            _stub(2, "Next President of Estonia?", "polymarket"),
        ]
        rows = {
            1: _row(
                market_id=1,
                q="Next President of Estonia?",
                src="kalshi",
                outcomes=[("Ülle Madise", 97.5), ("Alar Karis", 1.5)],
            ),
            2: _row(
                market_id=2,
                q="Next President of Estonia?",
                src="polymarket",
                outcomes=[("Ülle Madise", 34.6), ("Alar Karis", 30.0)],
            ),
        }
        (match,) = find_cross_source_markets(markets, market_row_fn=_pair_row_fn(rows))
        assert match["outcome"] == "Ülle Madise"
        assert match["kalshi"] == 97.5
        assert match["poly"] == 34.6
        assert match["delta"] == 62.9

    def test_the_reported_numbers_are_the_named_outcomes_own(self):
        """Two scans that can disagree will eventually bolt a number to the
        wrong name, which is strictly worse than printing no name. There is
        only one scan, and this holds it to that."""
        markets = [
            _stub(1, "Which bank will lead the IPO?", "kalshi"),
            _stub(2, "Which bank will lead the IPO?", "polymarket"),
        ]
        rows = {
            1: _row(
                market_id=1,
                q="Which bank will lead the IPO?",
                src="kalshi",
                outcomes=[("Goldman Sachs", 65.5), ("Morgan Stanley", 20.0)],
            ),
            2: _row(
                market_id=2,
                q="Which bank will lead the IPO?",
                src="polymarket",
                outcomes=[("Morgan Stanley", 50.0), ("Goldman Sachs", 12.0)],
            ),
        }
        (match,) = find_cross_source_markets(markets, market_row_fn=_pair_row_fn(rows))
        assert match["outcome"] == "Goldman Sachs"
        for side, row_id in (("kalshi", 1), ("poly", 2)):
            named = [
                o["prob"]
                for o in rows[row_id]["top_outcomes"]
                if o["name"] == match["outcome"]
            ]
            assert named == [match[side]]
        # ...and NOT the two leaders, which is what the old code subtracted.
        assert match["delta"] != round(abs(65.5 - 50.0), 1)
        assert match["delta"] == 53.5

    def test_the_numbers_come_from_top_outcomes_not_the_raw_market(self):
        """`top_outcomes` is already through the row builder's normalization
        (`_normalize_outcome_probs` fires on 102 of the 244 markets in the
        production pair set). Reading `market.outcomes` here instead would put
        a second basis on the page: the spotlight card and the market's own
        section would print different numbers for the same market."""
        markets = [
            SimpleNamespace(
                id=1,
                name="Q?",
                source="kalshi",
                outcomes=[_outcome("Yes", 0.90)],  # raw, un-normalized
            ),
            SimpleNamespace(
                id=2,
                name="Q?",
                source="polymarket",
                outcomes=[_outcome("Yes", 0.80)],
            ),
        ]
        rows = {
            1: _row(market_id=1, q="Q?", src="kalshi", outcomes=[("Yes", 60.0)]),
            2: _row(market_id=2, q="Q?", src="polymarket", outcomes=[("Yes", 40.0)]),
        }
        (match,) = find_cross_source_markets(markets, market_row_fn=_pair_row_fn(rows))
        assert (match["kalshi"], match["poly"]) == (60.0, 40.0)

    def test_every_returned_row_names_an_outcome(self):
        markets, rows = [], {}
        for i in range(6):
            k, p = i * 2 + 1, i * 2 + 2
            markets += [_stub(k, f"Question {i}?", "kalshi"), _stub(p, f"Question {i}?", "polymarket")]
            rows[k] = _row(market_id=k, q=f"Question {i}?", src="kalshi", outcomes=[("Yes", 50.0 + i)])
            rows[p] = _row(market_id=p, q=f"Question {i}?", src="polymarket", outcomes=[("Yes", 10.0)])
        result = find_cross_source_markets(markets, market_row_fn=_pair_row_fn(rows))
        assert result
        for match in result:
            assert match["outcome"].strip()

    def test_incomparable_pairs_are_dropped_BEFORE_the_cut(self):
        """The ordering half, and the reason three of four rendered cards were
        wrong: a mis-aligned pair yields a LARGER delta than a real
        disagreement, so ranking before dropping promoted the artifacts and
        pushed the honest rows below `max_results`."""
        markets, rows = [], {}
        # Eight incomparable pairs, each with a huge fake spread.
        for i in range(8):
            k, p = 100 + i * 2, 101 + i * 2
            markets += [_stub(k, f"Bracket question {i}?", "kalshi"), _stub(p, f"Bracket question {i}?", "polymarket")]
            rows[k] = _row(market_id=k, q=f"Bracket question {i}?", src="kalshi", outcomes=[(f"Above {i}", 95.0)])
            rows[p] = _row(market_id=p, q=f"Bracket question {i}?", src="polymarket", outcomes=[(f"{i}.5", 4.0)])
        # One comparable pair with a modest real spread.
        markets += [_stub(1, "Real question?", "kalshi"), _stub(2, "Real question?", "polymarket")]
        rows[1] = _row(market_id=1, q="Real question?", src="kalshi", outcomes=[("Yes", 40.0)])
        rows[2] = _row(market_id=2, q="Real question?", src="polymarket", outcomes=[("Yes", 33.0)])

        result = find_cross_source_markets(markets, market_row_fn=_pair_row_fn(rows))
        assert [m["q"] for m in result] == ["Real question?"]
        assert result[0]["delta"] == 7.0

    def test_a_dropped_exact_pair_does_not_fall_through_to_near_match(self):
        """An exact normalized-question match is the strongest evidence two
        markets are the same question. That it cannot be reduced to one number
        is a reason to show nothing — never a reason to release the Kalshi
        market to go find a WEAKER partner it happens to share an outcome with.

        The decoy is a PARAPHRASE, not a different year: the conservative
        near-match pass rejects a year mismatch on its own (see
        `test_slightly_different_names_not_matched`), so a decoy it would have
        refused anyway cannot tell us whether the exact pair was released.
        `test_paraphrased_names_matched` proves this decoy does get matched.
        """
        exact = "Will Donald Trump win the 2028 US presidential election?"
        decoy = "Donald Trump to win the 2028 US presidency?"
        markets = [
            _stub(1, exact, "kalshi"),
            _stub(2, exact, "polymarket"),
            _stub(3, decoy, "polymarket"),
        ]
        rows = {
            1: _row(
                market_id=1,
                q=exact,
                src="kalshi",
                outcomes=[("Before Jan 1, 2029", 16.0)],
            ),
            2: _row(market_id=2, q=exact, src="polymarket", outcomes=[("No", 86.0)]),
            3: _row(
                market_id=3,
                q=decoy,
                src="polymarket",
                outcomes=[("Before Jan 1, 2029", 5.0)],
            ),
        }
        assert find_cross_source_markets(markets, market_row_fn=_pair_row_fn(rows)) == []

        # The instrument: with the exact partner gone, the decoy IS reachable,
        # so the assertion above is about release, not about an unmatchable row.
        del rows[2]
        (match,) = find_cross_source_markets(
            [markets[0], markets[2]], market_row_fn=_pair_row_fn(rows)
        )
        assert match["poly_market_id"] == 3
        assert match["outcome"] == "Before Jan 1, 2029"

    def test_the_near_match_pass_is_held_to_the_same_rule(self):
        """The conservative near-match second pass builds its rows through the
        same alignment. It is the pass most likely to put two only-similar
        questions together, so it is the one that can least afford to subtract
        one market's leader from another's."""
        paraphrase_k = "Will Donald Trump win the 2028 US presidential election?"
        paraphrase_p = "Donald Trump to win the 2028 US presidency?"

        shared = [
            _stub(1, paraphrase_k, "kalshi"),
            _stub(2, paraphrase_p, "polymarket"),
        ]
        rows = {
            1: _row(market_id=1, q=paraphrase_k, src="kalshi", outcomes=[("Yes", 70.0)]),
            2: _row(market_id=2, q=paraphrase_p, src="polymarket", outcomes=[("Yes", 60.0)]),
        }
        (match,) = find_cross_source_markets(shared, market_row_fn=_pair_row_fn(rows))
        assert match["outcome"] == "Yes"
        assert match["delta"] == 10.0

        # Same pairing, nothing in common to price: no row.
        rows[2] = _row(
            market_id=2, q=paraphrase_p, src="polymarket", outcomes=[("No", 40.0)]
        )
        assert find_cross_source_markets(shared, market_row_fn=_pair_row_fn(rows)) == []
