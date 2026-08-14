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
        """Why the median alone was never enough — and why the floor exists.

        With a single book left, median == mean == that book, so the median
        cannot be the whole answer. That gap WAS the open policy call; Alex
        ruled it on 2026-08-14 (ruling 051): below three books `betting` is
        dropped entirely rather than reported. The arithmetic below is now the
        JUSTIFICATION for the floor rather than an admitted limitation.
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

    def test_a_thin_consensus_is_dropped_not_merely_logged(self):
        """SUPERSEDED BY RULING 051 (was: test_a_thin_consensus_is_logged).

        The old test asserted the writer LOGGED a thin consensus while still
        storing it. Under ruling 051 a below-floor consensus is not stored at
        all, so a test demanding the warning survive would lock in the very
        behaviour the ruling removed (ruling 130). The log line it checked is
        replaced by the DROP log, which reports a stronger fact.
        """
        src = self.src
        assert "BETTING_BOOK_FLOOR" in src
        assert "betting DROPPED below floor" in src

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


class TestRuling051BelowTheFloorBettingIsAbsent:
    """Alex's ruled policy (2026-08-14): floor 3, drop and re-weight, never freeze.

    Both halves of his acceptance are required:
      1. the 87-13 specimen replayed under the policy yields the fresh-source hero;
      2. a below-floor game shows the blend WITHOUT `betting`, not a ghost of it.
    """

    @property
    def src(self):
        return inspect.getsource(_ingest_event_odds)

    def test_the_floor_is_three(self):
        from app.tasks.odds_polling import BETTING_BOOK_FLOOR

        assert BETTING_BOOK_FLOOR == 3

    def test_below_floor_removes_the_key_rather_than_skipping_the_write(self):
        """The load-bearing distinction.

        `betting` is very likely ALREADY in the JSONB from an earlier poll taken
        when books were plentiful. Merely skipping the write leaves the frozen
        0.1347 in place — the exact bug. Only an explicit removal is honest.
        """
        src = self.src
        assert '_current.pop("betting", None)' in src

    def test_the_book_count_is_still_written_when_betting_is_dropped(self):
        """The absence must be observable AS an absence, not as silence.

        gotcha #53: an empty read and a healthy read must not render
        identically. `betting` missing with `betting_book_count: 1` says "we
        looked and there was not enough"; `betting` missing with no count at all
        would be indistinguishable from never having polled.
        """
        src = self.src
        # the count assignment must sit OUTSIDE the floor branch
        assert '_current["betting_book_count"] = _book_count' in src

    def test_specimen_15192596_yields_the_fresh_source_hero(self):
        """Alex's acceptance half 1, as arithmetic on the measured specimen.

        At 1 surviving book (rebet @ 0.1347) the policy drops `betting`, so the
        blend re-weights over whatever remains fresh — here ESPN's 0.02. The
        hero must be ESPN's number, NOT 0.1347 (the frozen ghost that rendered
        87-13) and NOT a re-weighted average that still contains rebet.
        """
        from app.utils.aggregation import compute_aggregate_probability

        class _E:
            # `betting` ABSENT — dropped below the floor. Count retained.
            win_probability_sources = {
                "betting_book_count": 1,
                "espn": 0.02,
            }
            espn_win_prob_home = None
            opening_home_probability = None
            status = "live"

        blended = compute_aggregate_probability(_E())
        assert blended == pytest.approx(0.02, abs=0.001)
        # The specific failure being closed: nowhere near rebet's last quote.
        assert abs(blended - 0.1347) > 0.10
        # And nothing between them — no averaging in the ghost.
        assert blended < 0.05

    def test_above_the_floor_is_unchanged(self):
        """The other direction (gotcha #43): normal games must not move.

        A healthy slate of books still writes `betting` and still blends it. If
        this goes red the floor has over-reached into ordinary play, which is
        the direction that breaks the product.
        """
        from app.utils.aggregation import compute_aggregate_probability

        class _E:
            win_probability_sources = {
                "betting": 0.60,
                "betting_book_count": 9,
            }
            espn_win_prob_home = None
            opening_home_probability = None
            status = "live"

        assert compute_aggregate_probability(_E()) == pytest.approx(0.60)
