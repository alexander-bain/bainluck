"""The betting consensus does not degrade to one book in silence (#1841).

Books PULL the moneyline when a game goes out of reach, and they drop out one at
a time. Under an unweighted mean the stored "sportsbook consensus" silently
narrows as books leave — until it is one minor book's last quote.

Measured on event 15192596 (Red Sox @ Blue Jays, 2026-08-13):

    20:55 UTC   12 books                                        ~0.12
    21:05:41     3 books (fanduel .0140, betmgm .0288, rebet .1347)  0.0592
    ~21:08:36    1 book  (rebet)                                     0.1347

`win_probability_sources['betting']` was left at **0.1347** — one minor book,
stored as consensus, while the two sharper books still pricing it at 1-3% had
already dropped out. That number rendered **87-13 for a team trailing 5-0 in the
9th**.

Same integrity question as #1844, one step upstream: that one is about how a
consensus is COMPARED; this is about what the consensus IS when sources drop out.
"""

import inspect
from statistics import mean, median

import pytest

from app.tasks.odds_polling import _ingest_event_odds


class TestMedianCannotBeCarriedByOneBook:
    """The measured specimen, as arithmetic."""

    THREE_BOOKS = [0.0140, 0.0288, 0.1347]  # fanduel, betmgm, rebet @ 21:05:41

    def test_mean_is_dragged_by_the_outlier_book(self):
        # The old behaviour, preserved as the thing being fixed.
        assert mean(self.THREE_BOOKS) == pytest.approx(0.0592, abs=0.0001)

    def test_median_lands_on_the_sharp_books(self):
        # rebet can no longer carry it: the median is betmgm's quote.
        assert median(self.THREE_BOOKS) == pytest.approx(0.0288)

    def test_median_is_closer_to_the_true_state_of_a_5_0_ninth_inning(self):
        """A team trailing 5-0 in the 9th is not a 6% shot, but it is nearer 3%
        than 13%."""
        assert median(self.THREE_BOOKS) < mean(self.THREE_BOOKS)

    def test_one_surviving_book_is_still_that_book(self):
        """Honest about what this does NOT fix.

        With a single book left, median == mean == that book. Closing the rest
        needs a minimum-book-count refusal, which is a policy call #1841 marks
        "not ruled" and this change deliberately does not take.
        """
        assert median([0.1347]) == 0.1347

    def test_twelve_healthy_books_are_essentially_unchanged(self):
        """The other direction (gotcha #43): the fix must not move normal games."""
        books = [0.62, 0.61, 0.63, 0.62, 0.60, 0.64, 0.62, 0.61, 0.63, 0.62]
        assert abs(median(books) - mean(books)) < 0.005


class TestWiring:
    """Structural — these properties must survive future edits to the writer."""

    @property
    def src(self):
        return inspect.getsource(_ingest_event_odds)

    def test_consensus_uses_median_not_a_bare_mean(self):
        src = self.src
        assert "median" in src
        # The exact mean expressions this replaced must not come back.
        assert "sum(all_home_probs) / len(all_home_probs)" not in src
        assert "sum(all_away_probs) / len(all_away_probs)" not in src

    def test_book_count_is_recorded_alongside_the_value(self):
        assert "betting_book_count" in self.src

    def test_book_count_is_inert_for_the_blend(self):
        """It must be ignored by the aggregator, not silently weighted as a source."""
        from app.utils.aggregation import SOURCE_WEIGHTS

        assert "betting_book_count" not in SOURCE_WEIGHTS

    def test_a_thin_consensus_is_logged(self):
        assert "only %d book(s)" in self.src

    def test_market_closed_is_distinguished_from_not_polled(self):
        """gotcha #53 in the odds pipeline.

        "No book quotes a moneyline" (a FACT — the market closed) and "we did
        not poll" (an absence) are the same silence today: both skip the write
        and leave a stale `betting` in place. Naming the first is the
        prerequisite for ever treating them differently.
        """
        src = self.src
        assert "elif snapshots_processed:" in src
        assert "market closed, not a polling gap" in src


class TestAggregationStillReadsBetting:
    """The added key must not disturb the source the blend actually reads."""

    def test_betting_is_still_weighted_and_book_count_is_not(self):
        from app.utils.aggregation import (
            SOURCE_WEIGHTS,
            compute_aggregate_probability,
        )

        assert "betting" in SOURCE_WEIGHTS

        class _E:
            win_probability_sources = {
                "betting": 0.60,
                "betting_book_count": 7,
            }
            espn_win_prob_home = None
            opening_home_probability = None
            status = "live"

        # 7 must not be read as a probability.
        assert compute_aggregate_probability(_E()) == pytest.approx(0.60)
