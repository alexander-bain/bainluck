"""N-way de-vig helper + the movers delta that consumes it (#1844).

The defect this locks down: the grid's "Biggest Movers" row subtracted ONE
arbitrary bookmaker's raw, vig-inclusive price from a de-vigged consensus. The
bias is negative by construction and proportional to each outcome's probability,
so 29 of 30 MLB teams rendered as falling every single day, deterministically,
with a confident red arrow. LAD's headline "-7.6 in 24h" was 0.3153 x 0.245 —
the betrivers overround — not a market move.

Alex's standing rule, encoded here: **raw vig-inclusive book prices NEVER enter
probability arithmetic, anywhere.** The invariant that proves it is that the
implied distribution sums to ~1.0 on BOTH sides of the subtraction.
"""

import pytest

from app.utils.odds_math import (
    devig_consensus,
    remove_vig,
    remove_vig_nway,
)


class TestRemoveVigNway:
    """The helper itself. Invariant: the output is a distribution."""

    def test_sums_to_one_two_way(self):
        out = remove_vig_nway([0.55, 0.50])
        assert out is not None
        assert sum(out) == pytest.approx(1.0)

    def test_sums_to_one_thirty_way_with_real_overround(self):
        # betrivers' measured MLB World Series column: 32.5% overround.
        raw = [0.3922, 0.1538] + [0.0280] * 28  # sums to 1.3300
        out = remove_vig_nway(raw)
        assert out is not None
        assert sum(raw) > 1.3  # the input really is vig-inclusive
        assert sum(out) == pytest.approx(1.0)

    def test_preserves_relative_ordering_and_ratios(self):
        out = remove_vig_nway([0.40, 0.20, 0.10])
        assert out is not None
        # Proportional de-vig: ratios survive exactly.
        assert out[0] / out[1] == pytest.approx(2.0)
        assert out[1] / out[2] == pytest.approx(2.0)

    def test_already_normalized_input_is_unchanged(self):
        out = remove_vig_nway([0.6, 0.3, 0.1])
        assert out == pytest.approx([0.6, 0.3, 0.1])

    @pytest.mark.parametrize(
        "bad",
        [
            [],
            [None, 0.5],
            [-0.1, 0.9],
            [0.0, 0.0],
            [float("inf"), 0.5],
            [float("nan"), 0.5],
        ],
    )
    def test_unnormalizable_returns_none_not_a_fake_distribution(self, bad):
        """gotcha #53: an absence and a fact must not share a return value.

        Returning the input unchanged here would hand the caller a "distribution"
        that is not one, which is precisely how #1844 stayed invisible.
        """
        assert remove_vig_nway(bad) is None

    def test_two_way_wrapper_delegates_to_the_same_implementation(self):
        """ONE normalization implementation — the wrapper cannot drift."""
        home, away = remove_vig(0.55, 0.50)
        expected = remove_vig_nway([0.55, 0.50])
        assert [home, away] == pytest.approx(expected)
        assert home + away == pytest.approx(1.0)

    def test_two_way_wrapper_passes_through_when_unnormalizable(self):
        # Previously raised ZeroDivisionError.
        assert remove_vig(0.0, 0.0) == (0.0, 0.0)


class TestDevigConsensus:
    """Per-book de-vig, then average. The shared merge implementation."""

    def test_consensus_column_sums_to_one(self):
        # Two books, same outcome set, wildly different overrounds.
        book_columns = {
            "fanduel": {"a": 0.58, "b": 0.58},          # 16% overround
            "betrivers": {"a": 0.66, "b": 0.66},        # 32% overround
        }
        out = devig_consensus(book_columns)
        assert sum(out.values()) == pytest.approx(1.0)
        assert out["a"] == pytest.approx(0.5)

    def test_wide_vig_book_cannot_outweigh_a_tight_one(self):
        """The whole point of de-vigging BEFORE averaging.

        Both books agree the true split is 75/25. betrivers just charges more
        for it. Averaging RAW would drag the answer up toward betrivers; the
        de-vigged consensus lands exactly on the agreed split.
        """
        book_columns = {
            "fanduel": {"a": 0.75 * 1.05, "b": 0.25 * 1.05},
            "betrivers": {"a": 0.75 * 1.33, "b": 0.25 * 1.33},
        }
        out = devig_consensus(book_columns)
        assert out["a"] == pytest.approx(0.75)
        assert out["b"] == pytest.approx(0.25)
        assert sum(out.values()) == pytest.approx(1.0)

    def test_a_single_unnormalizable_book_is_skipped_not_the_market(self):
        book_columns = {
            "good": {"a": 0.6, "b": 0.6},
            "broken": {"a": 0.0, "b": 0.0},
        }
        out = devig_consensus(book_columns)
        assert sum(out.values()) == pytest.approx(1.0)

    def test_empty_input_returns_empty(self):
        assert devig_consensus({}) == {}
        assert devig_consensus({"x": {}}) == {}

    def test_median_method_is_supported(self):
        book_columns = {
            "a": {"x": 0.9, "y": 0.3},
            "b": {"x": 0.6, "y": 0.6},
            "c": {"x": 0.3, "y": 0.9},
        }
        out = devig_consensus(book_columns, method="median")
        assert out["x"] == pytest.approx(0.5)
        assert out["y"] == pytest.approx(0.5)


class TestMoversDeltaBothDirections:
    """gotcha #43: a guard must assert BOTH directions.

    The flood stays capped (a vig-only column produces ZERO movers) AND the
    adjacent surface stays populated (a real move is still reported at its true
    size). Asserting only the first would pass on a function that always
    returns zero.
    """

    @staticmethod
    def _consensus(book_columns):
        return devig_consensus(book_columns)

    def test_nothing_moved_produces_zero_movers_despite_heavy_vig(self):
        """The #1844 specimen, inverted into a regression test.

        Same true prices at t-24h and now; only the overround differs between
        the stored per-book rows and the published consensus. The delta must be
        zero, not -24.5% of each probability.
        """
        true_prices = {"LAD": 0.3153, "NYY": 0.1015, "MIL": 0.0700}
        # Normalize the specimen so it is a real distribution over 3 outcomes.
        total = sum(true_prices.values())
        true_prices = {k: v / total for k, v in true_prices.items()}

        # t-24h: five books, each with its own measured overround.
        overrounds = {
            "fanduel": 1.1662,
            "betmgm": 1.1904,
            "betonlineag": 1.2137,
            "draftkings": 1.2393,
            "betrivers": 1.3245,
        }
        then_columns = {
            book: {k: v * orr for k, v in true_prices.items()}
            for book, orr in overrounds.items()
        }
        consensus_then = self._consensus(then_columns)

        # Now: the published, de-vigged consensus. Nothing moved.
        merged_now = dict(true_prices)

        for team in true_prices:
            trend = merged_now[team] - consensus_then[team]
            assert trend == pytest.approx(0.0, abs=1e-9), (
                f"{team} shows movement with a static market — this is #1844"
            )

        # Acceptance 5: sign sanity on a normalized column.
        total_trend = sum(
            merged_now[t] - consensus_then[t] for t in true_prices
        )
        assert total_trend == pytest.approx(0.0, abs=1e-9)

    def test_the_lad_specimen_no_longer_fabricates_minus_seven_six(self):
        """The exact published number, reproduced then killed.

        The OLD code compared merged (0.3153) against ONE book's raw price. On
        betrivers' 32.45% overround that raw price is 0.3153 * 1.3245 = 0.4176,
        so trend = 0.3153 - 0.4176 = -0.1023 for a market that did not move.
        (Production rendered -0.0768 because the live column carried a slightly
        different mix; the SIGN and the mechanism are the finding.)
        """
        merged_now = 0.3153
        betrivers_raw = merged_now * 1.3245

        old_way = merged_now - betrivers_raw
        assert old_way < -0.05, "sanity: the old way really did fabricate a drop"

        # New way: de-vig the whole book column first.
        others = (1.0 - merged_now) / 29
        then_column = {
            "LAD": merged_now * 1.3245,
            **{f"t{i}": others * 1.3245 for i in range(29)},
        }
        consensus_then = self._consensus({"betrivers": then_column})
        new_way = merged_now - consensus_then["LAD"]

        assert new_way == pytest.approx(0.0, abs=1e-9)

    def test_a_real_single_outcome_move_is_still_reported_at_full_size(self):
        """The other direction: the fix must not flatten genuine movement."""
        then_true = {"a": 0.50, "b": 0.30, "c": 0.20}
        then_columns = {
            "book1": {k: v * 1.20 for k, v in then_true.items()},
            "book2": {k: v * 1.30 for k, v in then_true.items()},
        }
        consensus_then = self._consensus(then_columns)

        # 'a' genuinely rallies 10 points, taken out of 'b'.
        merged_now = {"a": 0.60, "b": 0.20, "c": 0.20}

        assert merged_now["a"] - consensus_then["a"] == pytest.approx(0.10)
        assert merged_now["b"] - consensus_then["b"] == pytest.approx(-0.10)
        assert merged_now["c"] - consensus_then["c"] == pytest.approx(0.0)

    def test_reconstructed_prior_column_sums_to_one(self):
        """Alex's acceptance 1, stated directly.

        The t-24h side is a normalized field, like the now side — not a 1.3178
        book column.
        """
        raw_column = {f"t{i}": 0.0439 for i in range(30)}  # sums to 1.317
        assert sum(raw_column.values()) == pytest.approx(1.317, abs=0.01)

        consensus_then = self._consensus({"betrivers": raw_column})
        assert sum(consensus_then.values()) == pytest.approx(1.0)


class TestOneImplementationNotTwo:
    """#1844's design constraint: the live and historical paths share code."""

    def test_futures_aggregation_routes_through_devig_consensus(self):
        """`_aggregate_futures_outcomes` must not re-implement the normalize.

        A second copy written to serve one side re-creates exactly the
        divergence this closes, so the sharing is asserted structurally.
        """
        import inspect

        from app.tasks.futures import _aggregate_futures_outcomes

        src = inspect.getsource(_aggregate_futures_outcomes)
        assert "devig_consensus" in src
        assert "/ total_prob" not in src, "open-coded normalization is back"

    def test_compute_movers_routes_through_devig_consensus(self):
        import inspect

        from app.routes.playoffs import _compute_movers

        src = inspect.getsource(_compute_movers)
        assert "devig_consensus" in src
        # The deterministic tie-break (acceptance 3) must survive edits: books
        # written in the same poll share a captured_at to the microsecond.
        assert "DISTINCT ON" in src
        assert "fos.id ASC" in src

    def test_aggregate_futures_outcomes_still_produces_a_distribution(self):
        """End-to-end on the live path, with the real call shape."""
        from types import SimpleNamespace

        from app.tasks.futures import _aggregate_futures_outcomes

        def mk(book, pairs):
            return SimpleNamespace(
                bookmaker=book,
                outcomes=[
                    SimpleNamespace(name=n, probability=p, american_odds=None)
                    for n, p in pairs
                ],
            )

        markets = [
            mk("fanduel", [("A", 0.60), ("B", 0.35), ("C", 0.22)]),
            mk("betrivers", [("A", 0.66), ("B", 0.39), ("C", 0.25)]),
        ]
        out = _aggregate_futures_outcomes(markets)

        assert set(out) == {"A", "B", "C"}
        assert sum(v["probability"] for v in out.values()) == pytest.approx(1.0)
        # Raw per-book values are preserved for display, un-normalized.
        assert out["A"]["bookmakers"]["betrivers"]["probability"] == 0.66
