"""Tests for Economics page probability normalization and #12126/#12128 guards.

`_brackets_from_outcomes` normalizes only mutually-exclusive, complete fields
holding at least 90% (`SPECIALTY_FIELD_MASS_MIN`) of raw probability within the
160% ceiling (scale-down only). `_cumulative_to_discrete` converts cumulative
threshold ladders into discrete intervals without rescaling sums over 105%.
"""

import re
from types import SimpleNamespace

from app.routes.economics import (
    _brackets_from_outcomes,
    _cumulative_to_discrete,
    _modal_bracket,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_outcome(name: str, prob: float, rank: int = 0):
    return SimpleNamespace(
        id=1, name=name, current_probability=prob, rank=rank,
    )


def _make_market(
    name: str,
    outcomes: list,
    source: str = "kalshi",
    external_id: str = "kxcpi",
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


# ---------------------------------------------------------------------------
# _brackets_from_outcomes — multi-outcome market normalization (#11995 / #12093)
# ---------------------------------------------------------------------------


class TestBracketsFromOutcomes:
    """_brackets_from_outcomes normalizes via #11995 6-A guards."""

    def test_normal_distribution_unchanged(self):
        outcomes = [
            _make_outcome("2.5% - 3.0%", 0.35, rank=1),
            _make_outcome("3.0% - 3.5%", 0.30, rank=2),
            _make_outcome("2.0% - 2.5%", 0.20, rank=3),
            _make_outcome("3.5% - 4.0%", 0.15, rank=4),
        ]
        market = _make_market("CPI Year-over-Year", outcomes)
        brackets = _brackets_from_outcomes(market)
        total = sum(b[0] for b in brackets)
        assert 99.0 <= total <= 101.0, f"Sum should be ~100%, got {total}%"
        assert brackets[0][0] == 35.0

    def test_inflated_distribution_normalized(self):
        """Mutually-exclusive market whose probs sum up to 160% gets normalized."""
        outcomes = [
            _make_outcome("2.5% - 3.0%", 0.55, rank=1),
            _make_outcome("3.0% - 3.5%", 0.45, rank=2),
            _make_outcome("2.0% - 2.5%", 0.35, rank=3),
            _make_outcome("3.5% - 4.0%", 0.25, rank=4),
        ]
        market = _make_market("CPI Year-over-Year", outcomes)
        brackets = _brackets_from_outcomes(market)
        total = sum(b[0] for b in brackets)
        # Raw sum is 160%; should be normalized down to ~100%
        assert total <= 101.0, f"Sum should be <=101%, got {total}%"
        assert brackets[0][0] < 55.0

    def test_underround_not_scaled_up(self):
        """#11995 6-A scale-down only: sum < 100% is left untouched."""
        outcomes = [
            _make_outcome("Low", 0.45, rank=1),
            _make_outcome("High", 0.40, rank=2),
        ]
        market = _make_market("Rate Level", outcomes)
        brackets = _brackets_from_outcomes(market)
        assert brackets[0][0] == 45.0
        assert brackets[1][0] == 40.0

    def test_normalize_false_skips(self):
        outcomes = [
            _make_outcome("A", 0.80, rank=1),
            _make_outcome("B", 0.60, rank=2),
        ]
        market = _make_market("Test", outcomes)
        brackets = _brackets_from_outcomes(market, normalize=False)
        assert brackets[0][0] == 80.0
        assert brackets[1][0] == 60.0

    def test_preserves_labels(self):
        outcomes = [
            _make_outcome("2.0% - 2.5%", 0.60, rank=1),
            _make_outcome("2.5% - 3.0%", 0.50, rank=2),
            _make_outcome("3.0% - 3.5%", 0.30, rank=3),
        ]
        market = _make_market("CPI", outcomes)
        brackets = _brackets_from_outcomes(market)
        labels = [b[1] for b in brackets]
        assert labels == ["2.0% - 2.5%", "2.5% - 3.0%", "3.0% - 3.5%"]

    def test_empty_outcomes(self):
        market = _make_market("Empty", [])
        assert _brackets_from_outcomes(market) == []

    def test_over_160_ceiling_refused(self):
        """#11995 6-A: raw sum > 160% refuses normalization (independent binaries)."""
        outcomes = [_make_outcome(f"Bracket {i}", 0.40, rank=i) for i in range(6)]
        market = _make_market("Inflated", outcomes)
        brackets = _brackets_from_outcomes(market)
        assert [b[0] for b in brackets] == [40.0] * 6

    def test_one_cent_floor_excluded_from_divisor(self):
        """#11995 6-A / #8595: 1c floor outcomes are excluded from the divisor."""
        outcomes = [
            _make_outcome("2.0% - 2.5%", 0.55, rank=1),
            _make_outcome("2.5% - 3.0%", 0.55, rank=2),
            *[
                _make_outcome(f"Tail {i}", 0.01, rank=i + 3)
                for i in range(10)
            ],
        ]
        market = _make_market("CPI", outcomes)
        brackets = _brackets_from_outcomes(market)
        # Non-floor mass is 1.10 -> each 0.55 leg normalizes to 50.0%, not 0.55/1.20 = 45.8%
        assert brackets[0][0] == 50.0
        assert brackets[1][0] == 50.0
        assert brackets[2][0] == 0.9

    def test_mutually_exclusive_none_or_false_not_rescaled(self):
        """#12010 / #12093: mutually_exclusive must be True to normalize."""
        outcomes = [
            _make_outcome("2.0% - 2.5%", 0.60, rank=1),
            _make_outcome("2.5% - 3.0%", 0.55, rank=2),
        ]
        for me in (None, False):
            market = _make_market("CPI", outcomes, mutually_exclusive=me)
            brackets = _brackets_from_outcomes(market)
            assert [b[0] for b in brackets] == [60.0, 55.0]

    def test_blank_outcome_label_refused_and_withholds_normalization(self):
        """#12126 / #12128 / #11949: blank outcome labels are stripped and mark field incomplete."""
        outcomes = [
            _make_outcome("2.0% - 2.5%", 0.60, rank=1),
            _make_outcome("   ", 0.50, rank=2),
            _make_outcome("2.5% - 3.0%", 0.50, rank=3),
        ]
        market = _make_market("CPI", outcomes, mutually_exclusive=True)
        brackets = _brackets_from_outcomes(market)
        assert [b[1] for b in brackets] == ["2.0% - 2.5%", "2.5% - 3.0%"]
        assert [b[0] for b in brackets] == [60.0, 50.0]

    def test_missing_source_stays_none_and_blank_outcome_filtered_in_rows(self):
        """#12126 / #12128 / #11949: missing source stays None, never 'kalshi' or ''."""
        from app.routes.economics import _cross_source_row_fn, _distribution_row, _market_row

        m_bin = _make_market(
            "Will tariffs rise?",
            [
                _make_outcome("", 0.90, rank=1),
                _make_outcome("Yes", 0.42, rank=2),
                _make_outcome("No", 0.58, rank=3),
            ],
            source="",
            external_id="",
        )
        row = _market_row(m_bin)
        assert row is not None
        assert row["src"] is None
        assert row["prob"] == 42.0

        m_dist = _make_market(
            "CPI Brackets",
            [
                _make_outcome("2.0% - 2.5%", 0.45, rank=1),
                _make_outcome("   ", 0.25, rank=2),
                _make_outcome("2.5% - 3.0%", 0.30, rank=3),
            ],
            source="",
            external_id="",
        )
        dist = _distribution_row(m_dist, min_outcomes=2)
        assert dist is not None
        assert dist["src"] is None
        assert [r[1] for r in dist["rows"]] == ["2.0% - 2.5%", "2.5% - 3.0%"]

        cs = _cross_source_row_fn(m_dist)
        assert cs is not None
        assert cs["src"] is None
        assert [t["name"] for t in cs["top_outcomes"]] == ["2.0% - 2.5%", "2.5% - 3.0%"]

    def test_specialty_field_mass_min_threshold(self):
        """#12126 / #12128: SPECIALTY_FIELD_MASS_MIN = 0.9 guard on _brackets_from_outcomes.

        Sub-90% raw mass stays unscaled; boundary 0.90 and overround 1.10 pass
        the >= 0.90 gate (0.90 is left unscaled by scale-down-only, 1.10 scales
        down to 100%).
        """
        # Sub-90% raw mass (0.45 + 0.25 + 0.15 = 0.85 < 0.90) -> raw
        sub_90 = _make_market(
            "CPI",
            [
                _make_outcome("2.0% - 2.5%", 0.45, rank=1),
                _make_outcome("2.5% - 3.0%", 0.25, rank=2),
                _make_outcome("3.0% - 3.5%", 0.15, rank=3),
            ],
            mutually_exclusive=True,
        )
        assert [b[0] for b in _brackets_from_outcomes(sub_90)] == [45.0, 25.0, 15.0]

        # Boundary 90% raw mass (0.50 + 0.25 + 0.15 = 0.90) -> passes >= 0.90
        # mass check; divisor <= 1.0 so scale-down-only keeps raw values
        at_90 = _make_market(
            "CPI",
            [
                _make_outcome("2.0% - 2.5%", 0.50, rank=1),
                _make_outcome("2.5% - 3.0%", 0.25, rank=2),
                _make_outcome("3.0% - 3.5%", 0.15, rank=3),
            ],
            mutually_exclusive=True,
        )
        assert [b[0] for b in _brackets_from_outcomes(at_90)] == [50.0, 25.0, 15.0]

        # Overround 110% raw mass (0.55 + 0.35 + 0.20 = 1.10 >= 0.90) -> scaled down to 100%
        over_100 = _make_market(
            "CPI",
            [
                _make_outcome("2.0% - 2.5%", 0.55, rank=1),
                _make_outcome("2.5% - 3.0%", 0.35, rank=2),
                _make_outcome("3.0% - 3.5%", 0.20, rank=3),
            ],
            mutually_exclusive=True,
        )
        scaled = _brackets_from_outcomes(over_100)
        assert [b[0] for b in scaled] == [50.0, 31.8, 18.2]
        assert round(sum(b[0] for b in scaled), 1) == 100.0


# ---------------------------------------------------------------------------
# _cumulative_to_discrete — cumulative "Above X" discrete conversion
# ---------------------------------------------------------------------------


class TestCumulativeToDiscrete:
    """_cumulative_to_discrete converts cumulative rungs into discrete intervals without rescaling."""

    def test_well_behaved_cumulative(self):
        outcomes = [
            _make_outcome("Above 2.0%", 0.95),
            _make_outcome("Above 2.5%", 0.80),
            _make_outcome("Above 3.0%", 0.50),
            _make_outcome("Above 3.5%", 0.20),
            _make_outcome("Above 4.0%", 0.05),
        ]
        brackets = _cumulative_to_discrete(outcomes)
        total = sum(b[0] for b in brackets)
        assert total <= 105.0, f"Sum should be <=105%, got {total}%"
        assert len(brackets) > 0

    def test_above_labels_stripped(self):
        outcomes = [
            _make_outcome("Above 2.0%", 0.80),
            _make_outcome("Above 3.0%", 0.50),
            _make_outcome("Above 4.0%", 0.20),
        ]
        brackets = _cumulative_to_discrete(outcomes)
        labels = [b[1] for b in brackets]
        assert all("Above" not in lbl for lbl in labels)

    def test_empty_outcomes(self):
        assert _cumulative_to_discrete([]) == []

    def test_max_buckets_respected(self):
        outcomes = [_make_outcome(f"Above {i}", 0.95 - i * 0.08) for i in range(10)]
        brackets = _cumulative_to_discrete(outcomes, max_buckets=4)
        assert len(brackets) <= 4

    def test_normalization_guard_fires(self):
        """Well-formed monotonic cumulative data yields discrete intervals summing <= first rung."""
        outcomes = [
            _make_outcome("Above 100", 0.90),
            _make_outcome("Above 200", 0.70),
            _make_outcome("Above 300", 0.40),
            _make_outcome("Above 400", 0.10),
        ]
        brackets = _cumulative_to_discrete(outcomes)
        total = sum(b[0] for b in brackets)
        # 20 + 30 + 30 + 10 = 90 — well under threshold
        assert total <= 105.0

    def test_discrete_sum_over_105_not_rescaled(self):
        """#12126 / #12128: discrete diffs summing over 105% are NOT rescaled via 100 / total."""
        outcomes = [
            _make_outcome("Above 100", 1.20),
            _make_outcome("Above 200", 0.80),
            _make_outcome("Above 300", 0.30),
        ]
        brackets = _cumulative_to_discrete(outcomes)
        probs = [b[0] for b in brackets]
        assert sum(probs) == 120.0
        assert probs == [40.0, 50.0, 30.0]


class TestCumulativeSignedThresholds:
    """#7081 — the threshold sort key must read the minus sign.

    An unsigned `[\\d.]+` key reads "Above -0.4%" as 0.4. Nothing about the
    output *shape* gives that away: the ladder still comes back as brackets
    that sum sensibly, so these assert the label a probability is PAIRED WITH,
    never merely the ordering.
    """

    # The September CPI print, verbatim from market_id 364212 — the specimen
    # that was live on /economics.
    _CPI_SEPTEMBER = [
        ("Above -0.4%", 0.950), ("Above -0.3%", 0.945), ("Above -0.2%", 0.925),
        ("Above -0.1%", 0.925), ("Above 0.0%", 0.915), ("Above 0.1%", 0.905),
        ("Above 0.2%", 0.900), ("Above 0.3%", 0.675), ("Above 0.4%", 0.480),
        ("Above 0.5%", 0.440), ("Above 0.6%", 0.360),
    ]

    def test_mixed_sign_ladder_pairs_mass_with_the_right_label(self):
        """The two biggest non-modal brackets belong to +0.3% and +0.4%.

        Before #7081 they were served as -0.3% and -0.4% — 42 points of
        probability shown against deflation. #7081 moved them to "+0.2%" and
        "+0.3%", which was still one rung low (#9558): "above 0.2%, not above
        0.3%" is a print of exactly 0.3%, because BLS prints to one decimal.
        """
        outcomes = [_make_outcome(n, p) for n, p in self._CPI_SEPTEMBER]
        brackets = _cumulative_to_discrete(outcomes, max_buckets=6)
        by_label = {lbl: prob for prob, lbl in brackets}

        assert by_label.get("0.3%") == 22.5
        assert by_label.get("0.4%") == 19.5
        # The mass must not appear on the deflation legs at all.
        assert by_label.get("-0.3%") != 22.5
        assert by_label.get("-0.4%") != 19.5
        # The modal bar is P(above 0.6%): a print of 0.7% or more.
        assert by_label.get("0.7%+") == 36.0

    def test_mixed_sign_ladder_is_ascending_by_threshold(self):
        outcomes = [_make_outcome(n, p) for n, p in self._CPI_SEPTEMBER]
        labels = [lbl for _, lbl in _cumulative_to_discrete(outcomes, max_buckets=6)]
        # Labels now carry "≤" and "+" ("≤-0.4%", "0.7%+"), and a run across a
        # missing rung reads "0.4–0.6%": order by the first number in each.
        vals = [float(re.search(r"-?\d+(?:\.\d+)?", lbl).group()) for lbl in labels]
        assert vals == sorted(vals), f"ladder not ascending: {labels}"

    def test_all_negative_ladder_does_not_collapse_to_one_bar(self):
        """Germany's 2026 budget balance — 7 legs, every threshold negative.

        The unsigned key reversed the ladder, which made the cumulatives
        ascending, which made the monotonicity clamp flatten every leg to the
        first one's value; every difference then rounded to zero and was
        dropped. The card became a single bar.
        """
        legs = [
            ("Above -5.0% of GDP", 0.955), ("Above -4.5% of GDP", 0.895),
            ("Above -4.0% of GDP", 0.580), ("Above -3.5% of GDP", 0.155),
            ("Above -3.0% of GDP", 0.070), ("Above -2.5% of GDP", 0.040),
            ("Above -2.0% of GDP", 0.035),
        ]
        brackets = _cumulative_to_discrete(
            [_make_outcome(n, p) for n, p in legs], max_buckets=6
        )
        assert len(brackets) > 1, f"collapsed to {brackets}"
        by_label = {lbl: prob for prob, lbl in brackets}
        # The distribution is centred on -4.0%, not on the outermost leg.
        assert by_label.get("-4.0% of GDP") == 42.5
        assert by_label.get("-4.5% of GDP") == 31.5
        modal_idx, _, modal_label = _modal_bracket(brackets)
        assert modal_label == "-4.0% of GDP"

    def test_all_negative_ladder_survives_the_max_buckets_resort(self):
        """The post-truncation re-sort must key on threshold, not on label.

        8 legs into max_buckets=6 forces the `len(discrete) > max_buckets`
        path. Sorting the survivors by label string yields "-3%" before "-4%".
        """
        legs = [
            ("Above -10%", 0.920), ("Above -9%", 0.905), ("Above -8%", 0.860),
            ("Above -7%", 0.730), ("Above -6%", 0.570), ("Above -5%", 0.410),
            ("Above -4%", 0.220), ("Above -3%", 0.095),
        ]
        brackets = _cumulative_to_discrete(
            [_make_outcome(n, p) for n, p in legs], max_buckets=6
        )
        assert len(brackets) == 6
        vals = [float(lbl.rstrip("%")) for _, lbl in brackets]
        assert vals == sorted(vals), f"ladder not ascending: {vals}"

    def test_hyphen_inside_a_word_is_not_read_as_a_sign(self):
        """`(?<!\\w)` guard: only a leading hyphen is a minus."""
        legs = [("Above COVID-19 cases 5%", 0.80), ("Above COVID-19 cases 7%", 0.30)]
        brackets = _cumulative_to_discrete([_make_outcome(n, p) for n, p in legs])
        # Parsed as 19 for both (unchanged by the fix); the point is that
        # neither becomes -19, which would silently reorder the pair.
        assert len(brackets) == 2

    def test_malformed_numeric_token_does_not_raise(self):
        """`float('1.2.3')` would 500 the whole /economics route."""
        legs = [("Above 1.2.3", 0.80), ("Above 2.0", 0.30)]
        brackets = _cumulative_to_discrete([_make_outcome(n, p) for n, p in legs])
        assert brackets  # returned rather than raised

    def test_returned_rows_are_pairs(self):
        """The threshold is carried internally but must not reach the payload."""
        outcomes = [_make_outcome(n, p) for n, p in self._CPI_SEPTEMBER]
        for row in _cumulative_to_discrete(outcomes, max_buckets=6):
            assert len(row) == 2, f"row leaked its sort key: {row}"


# ---------------------------------------------------------------------------
# _modal_bracket
# ---------------------------------------------------------------------------


class TestModalBracket:
    def test_finds_highest(self):
        brackets = [[25.0, "Low"], [45.0, "Mid"], [30.0, "High"]]
        idx, prob, label = _modal_bracket(brackets)
        assert idx == 1
        assert prob == 45.0
        assert label == "Mid"

    def test_empty(self):
        idx, prob, label = _modal_bracket([])
        assert idx == 0
        assert prob == 0.0
        assert label == ""


# ---------------------------------------------------------------------------
# FOMC `resolved` guard (#12126 / #12128 / #11949)
# ---------------------------------------------------------------------------


class TestFomcResolvedGuard:
    """FOMC meeting `resolved` reads only venue settlement via `market_reads_settled`, never `status == 'closed'`."""

    def test_closed_status_or_high_price_without_venue_result_is_not_resolved(self):
        from datetime import datetime, timezone
        from pathlib import Path
        from app.utils.futures_liveness import market_reads_settled

        now = datetime(2026, 11, 6, 12, 0, tzinfo=timezone.utc)
        closed_ungraded = SimpleNamespace(
            id=501,
            name="What will the upper bound of the federal funds rate be after Dec 2026?",
            status="closed",
            market_metadata={},
            outcomes=[
                SimpleNamespace(
                    id=1,
                    name="Above 4.25%",
                    current_probability=0.99,
                    is_winner=None,
                    resolution_source=None,
                ),
                SimpleNamespace(
                    id=2,
                    name="Above 4.50%",
                    current_probability=0.01,
                    is_winner=False,
                    resolution_source=None,
                ),
            ],
        )
        assert market_reads_settled(closed_ungraded, now=now) is False

        venue_settled = SimpleNamespace(
            id=502,
            name="What will the upper bound of the federal funds rate be after Sep 2026?",
            status="open",
            market_metadata={"shape": {"expected_winners": 1}},
            outcomes=[
                SimpleNamespace(
                    id=1,
                    name="4.25% - 4.50%",
                    current_probability=0.99,
                    is_winner=True,
                    resolution_source="api_settlement",
                ),
                SimpleNamespace(
                    id=2,
                    name="4.00% - 4.25%",
                    current_probability=0.01,
                    is_winner=False,
                    resolution_source="api_settlement",
                ),
            ],
        )
        assert market_reads_settled(venue_settled, now=now) is True

        route_src = (
            Path(__file__).resolve().parent.parent / "app" / "routes" / "economics.py"
        ).read_text()
        assert '"resolved": market_reads_settled(m, now=now)' in route_src
        assert '"resolved": m.status == "closed"' not in route_src
