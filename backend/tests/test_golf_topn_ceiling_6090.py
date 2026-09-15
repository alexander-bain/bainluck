"""#6090/#6092 — a golf Top-N field is published only if its prices could be real.

WHAT A READER SAW. `/calibration` showed the two Kalshi golf Top-N finisher series
at a 20-28pp gap between predicted and actual, which reads as miscalibration. It is
not. The winner counts are correct and the grading is sound; the PRICES are
collectively impossible — a 147-leg "top 10" field whose published prices sum to
67.9 against a ceiling of 10.

Every specimen below is a production row measured 2026-09-14 and named by its
series ticker, so a later reader can re-read the market rather than trust the
fixture. The rule is asserted through BEHAVIOUR, and the negative cases are the
load-bearing half: this rule must not reach the cells Alex has already ruled on.
"""

import pytest

from app.tasks.precompute_calibration import (
    GOLF_TOPN_CEILING_TOLERANCE,
    GOLF_TOPN_DECLARED_N_PATTERN,
    GOLF_TOPN_DECLARED_N_SQL,
    GOLF_TOPN_SERIES_PREFIXES,
    MEX_NORMALIZE_THRESHOLD,
    golf_topn_declared_ceiling,
    market_is_golf_topn_incoherent,
)

#: (ticker, outcomes, winners, published sum, declared ceiling) — the filing
#: specimens, production 2026-09-14, all 41 markets of the two series folded.
MEASURED_SPECIMENS = [
    ("KXPGAR2TOP10-3MO26", 147, 12, 67.9, 10),
    ("KXPGAR3TOP10-CHSC26", 128, 11, 51.1, 10),
    ("KXPGAR2TOP10-CHSC26", 134, 10, 50.9, 10),
    ("KXPGAR2TOP10-WYC26", 153, 13, 49.2, 10),
    ("KXPGAR2TOP10-USO26", 117, 10, 45.0, 10),
    ("KXPGAR3TOP5-MAST26", 91, 6, 30.4, 5),
    ("KXPGAR2TOP5-THOC26", 156, 7, 22.1, 5),
]


class TestTheDefectIsRefused:
    """The fields a reader met, and what the accuracy page must stop grading."""

    @pytest.mark.parametrize(
        "ticker,_n_out,_n_win,cp_sum,_ceiling", MEASURED_SPECIMENS
    )
    def test_every_measured_specimen_is_refused(
        self, ticker, _n_out, _n_win, cp_sum, _ceiling
    ):
        assert market_is_golf_topn_incoherent(ticker, cp_sum) is True

    @pytest.mark.parametrize("ticker,_o,_w,_s,ceiling", MEASURED_SPECIMENS)
    def test_the_ceiling_is_read_from_the_ticker(self, ticker, _o, _w, _s, ceiling):
        """`...TOP10-...` declares 10. This is the only source of the ceiling."""
        assert golf_topn_declared_ceiling(ticker) == ceiling

    def test_the_worst_specimen_is_nearly_seven_times_its_ceiling(self):
        """67.9 against 10 is not a pricing story — it is the filing specimen."""
        assert market_is_golf_topn_incoherent("KXPGAR2TOP10-3MO26", 67.9)
        assert 67.9 / 10 > 6


class TestAnHonestTopNFieldStaysPublished:
    """The rule is arithmetic about the field, never a suspicion about golf."""

    def test_a_field_summing_to_its_ceiling_is_kept(self):
        assert market_is_golf_topn_incoherent("KXPGAR2TOP10-3MO26", 10.0) is False

    def test_a_field_at_the_overround_bar_is_kept(self):
        """Exactly N * tolerance is KEPT — the test is strictly greater-than."""
        assert market_is_golf_topn_incoherent("KXPGAR2TOP10-3MO26", 11.5) is False

    def test_one_hundredth_past_the_bar_is_refused(self):
        """The boundary is real and sits where the constant says, not near it."""
        assert market_is_golf_topn_incoherent("KXPGAR2TOP10-3MO26", 11.6) is True

    def test_a_top5_field_is_held_to_five_not_to_ten(self):
        """A sum of 8 is honest for a Top-10 field and impossible for a Top-5."""
        assert market_is_golf_topn_incoherent("KXPGAR2TOP10-USO26", 8.0) is False
        assert market_is_golf_topn_incoherent("KXPGAR2TOP5-THOC26", 8.0) is True

    def test_a_market_with_no_eligible_priced_outcome_fails_closed(self):
        """No sum means it cannot be SHOWN incoherent, so it stays published.

        Mirrors the SQL, where `NULL > x` is NULL and the row does not match.
        """
        assert market_is_golf_topn_incoherent("KXPGAR2TOP10-3MO26", None) is False


class TestItCannotReachTheCellsAlexAlreadyRuledOn:
    """The negative half, and the reason the ceiling may never come from winners.

    Making RULE E's sum arm ceiling-aware as `cp_sum > n_winners * 1.15` is the
    tempting generalisation and it would REVERSE a ruling: `kalshi/economics` was
    excluded by Alex on 2026-08-28, and its specimens are cumulative intraday
    ladders whose realized winner count is not a ceiling at all.
    """

    def test_the_kxdji_economics_specimen_is_untouched(self):
        """76 outcomes, 76 winners, sum 72.48 — ruled out 2026-08-28, stays out.

        A winners-derived bar would put it under 76 * 1.15 = 87.4 and silently
        return 63,537 rows to the curve. This rule never sees it: its ticker
        declares no Top-N ceiling.
        """
        assert golf_topn_declared_ceiling("KXDJI-26JUL2814") is None
        assert market_is_golf_topn_incoherent("KXDJI-26JUL2814", 72.48) is False

    @pytest.mark.parametrize(
        "ticker",
        [
            "KXNASDAQ100U-26SEP05",
            "KXINXU-26AUG12",
            "KXBBCHARTPOSITIONSONG-26SEP05BOS",
            "KXNHLGOAL-26MAR03-ABC",
        ],
    )
    def test_no_other_ruled_or_measured_family_is_reachable(self, ticker):
        """Each of these belongs to a cell with its own separate ruling."""
        assert market_is_golf_topn_incoherent(ticker, 999.0) is False

    @pytest.mark.parametrize("ticker", ["KXPGAR1TOP10-X26", "KXPGAR4TOP5-X26"])
    def test_an_unfolded_sibling_series_is_not_reachable(self, ticker):
        """`KXPGAR[0-9]TOP` is WIDER than what was measured, and that gap is the
        category-widening the `nonexclusive_bundle_census` warns against. Only
        the two folded prefixes may be reached.
        """
        assert market_is_golf_topn_incoherent(ticker, 999.0) is False

    def test_the_golf_cell_as_a_whole_is_not_excluded(self):
        """An ordinary golf winner market has no declared ceiling and is kept.

        The served census measures the golf cell's >=2-winner cohort at ECE 3.81
        against a remainder of 8.60, so a cell-wide exclusion would remove golf's
        BETTER half. This rule is series-scoped precisely so it cannot do that.
        """
        assert market_is_golf_topn_incoherent("KXPGATOURNAMENT-MAST26", 40.0) is False


class TestTheRuleAndItsSqlCannotDriftApart:
    """One pattern, two renderings. A retyped regex is how a mirror stops mirroring."""

    def test_the_sql_is_built_from_the_same_pattern_as_the_python(self):
        assert GOLF_TOPN_DECLARED_N_PATTERN in GOLF_TOPN_DECLARED_N_SQL

    def test_the_pattern_is_built_from_the_prefix_tuple(self):
        """Adding a folded series to the tuple must widen BOTH renderings at once."""
        for prefix in GOLF_TOPN_SERIES_PREFIXES:
            assert prefix in GOLF_TOPN_DECLARED_N_PATTERN

    def test_the_sql_reads_the_market_ticker_column(self):
        assert "fm.external_id" in GOLF_TOPN_DECLARED_N_SQL

    def test_the_tolerance_is_the_normalizers_constant_not_a_fitted_one(self):
        """At N = 1 this rule must reduce to the shipped sum arm, byte for byte."""
        assert GOLF_TOPN_CEILING_TOLERANCE == MEX_NORMALIZE_THRESHOLD
        assert market_is_golf_topn_incoherent("KXPGAR2TOP1-X26", 1.16) is True
        assert market_is_golf_topn_incoherent("KXPGAR2TOP1-X26", 1.15) is False


class TestDegenerateTickers:
    """A ticker that declares nothing usable declares nothing."""

    @pytest.mark.parametrize(
        "ticker", [None, "", "KXPGAR2TOP-NODIGITS26", "KXPGAR2TOP10", "kxpgar2top10-x"]
    )
    def test_no_ceiling_is_read(self, ticker):
        assert golf_topn_declared_ceiling(ticker) is None
        assert market_is_golf_topn_incoherent(ticker, 999.0) is False

    def test_a_declared_ceiling_of_zero_is_refused_as_a_ceiling(self):
        """`TOP0` would make every field incoherent against a bar of 0."""
        assert golf_topn_declared_ceiling("KXPGAR2TOP0-X26") is None
        assert market_is_golf_topn_incoherent("KXPGAR2TOP0-X26", 0.5) is False
