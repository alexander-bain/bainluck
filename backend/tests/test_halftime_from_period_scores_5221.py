"""#5221 — halftime is the first HALF of the linescore, not the first entry in it.

#5052 wired the 2H reconstructor into the refusing loop and it graded 1,013 legs
on its first production run. Every one of them was wrong in the same way: the
helper it reuses, `_get_halftime_score`, fell through to
``box_score_data.home_period_scores[0]`` behind a ``len(...) >= 2`` guard whose
comment read *"a finished 2-half game has >=2 entries"*. That is true of a
two-half sport and false of every quarter-scored one, where ``[0]`` is Q1. So
"second half" was computed as **final − Q1** — three quarters of scoring.

Measured on production 2026-09-11, hours after the release:

    graded 2H legs by linescore length
        4 (quarters)  950      5 (4+OT)  60      6 (4+2OT)  3
        2 (halves)      0   ← not one

    of the 135 whose arithmetic is fully checkable, 121 served the WRONG
    verdict, and 121 of 121 were exactly explained by the substitution

WHY THE BUG SURVIVED A WELL-TESTED SHIP, WHICH IS THE POINT OF THIS FILE.
Every test in `test_second_half_reconstruction_5052.py` monkeypatches
`_get_halftime_score` and asserts on `_period_scores` — so the subtraction is
covered exhaustively and *the thing being subtracted was never once computed*.
These tests drive the real helper against a real linescore instead.

The fixtures are chosen so the full-game answer, the true-2H answer and the
old final-minus-Q1 answer are all DIFFERENT. A fixture where any two agree
cannot fail, which is #4923's lesson and #5052's own stated rule.
"""

import pytest

import app.tasks.backfill_winners as bw


class _Result:
    def __init__(self, row):
        self._row = row

    def first(self):
        return self._row


class _Session:
    """Answers the two reads `_get_halftime_score` makes, in order.

    First the `scoring_plays` probe, then the `box_score_data` + sport lookup.
    A test that wants the plays path supplies `plays`; otherwise it is absent
    and the fallback under test is what runs.
    """

    def __init__(self, *, plays=None, box=None, sport_key=None):
        self._plays = plays
        self._box = box
        self._sport_key = sport_key
        self.calls = 0

    async def execute(self, *_args, **_kwargs):
        self.calls += 1
        if self.calls == 1:
            return _Result(self._plays)
        return _Result((self._box, self._sport_key))


def _box(home, away):
    return {"home_period_scores": home, "away_period_scores": away}


class TestFirstHalfPeriodCount:
    """The sport table, which is the whole fix — a length test cannot do this."""

    @pytest.mark.parametrize(
        "key,expected",
        [
            ("basketball_nba", 2),
            ("basketball_wnba", 2),
            ("americanfootball_nfl", 2),
            ("americanfootball_ncaaf", 2),
            ("soccer_epl", 1),
            ("soccer_usa_mls", 1),
            # Two halves, so a double-overtime game has FOUR entries and is not
            # a quarter game. This is the row that proves the decision cannot be
            # made from `len(period_scores)`.
            ("basketball_ncaab", 1),
        ],
    )
    def test_the_sports_we_can_answer_for(self, key, expected):
        assert bw._first_half_period_count(key) == expected

    def test_ncaab_is_not_swallowed_by_the_basketball_prefix(self):
        """Ordering, asserted rather than left to the reader of the `if`s.

        `basketball_ncaab` starts with `basketball_`. If the quarter branch is
        ever moved above the two-half branch this returns 2 and NCAA halves
        start grading against final − (H1 + H2), i.e. nothing.
        """
        assert bw._first_half_period_count("basketball_ncaab") == 1
        assert bw._first_half_period_count("basketball_nba") == 2

    @pytest.mark.parametrize(
        "key",
        ["icehockey_nhl", "baseball_mlb", "tennis_atp", "mma_mixed_martial_arts", "", None],
    )
    def test_a_sport_with_no_half_refuses(self, key):
        """Three periods and nine innings have no halftime to invent."""
        assert bw._first_half_period_count(key) is None

    def test_the_answer_is_case_insensitive(self):
        assert bw._first_half_period_count("Basketball_NBA") == 2


class TestHalftimeFromTheLinescore:
    async def test_the_production_specimen_that_was_served_wrong(self):
        """San Antonio 102 – Minnesota 104, event 14627377, graded 2026-09-11.

        quarters [23, 22, 27, 30] / [24, 21, 24, 35]

            true halftime      45 – 45   ⇒ 2H total 206 − 90 = 116
            what shipped       23 – 24   ⇒ 2H total 206 − 47 = 159

        "Over 125.5 2H points scored" was served WON. 116 < 125.5: it LOST.
        The three numbers differ, so this fixture can fail in both directions.
        """
        session = _Session(
            box=_box([23, 22, 27, 30], [24, 21, 24, 35]),
            sport_key="basketball_nba",
        )
        half = await bw._get_halftime_score(session, 14627377)

        assert half == (45, 45)
        assert half != (23, 24), "regressed to the first QUARTER (#5221)"

        # And the verdict the reader actually sees, spelled out.
        second_half_total = (102 + 104) - sum(half)
        assert second_half_total == 116
        assert not second_half_total > 125.5

    async def test_overtime_does_not_move_the_half(self):
        """4 + OT is still two quarters to the break."""
        session = _Session(
            box=_box([25, 20, 30, 22, 11], [24, 21, 28, 24, 9]),
            sport_key="basketball_nba",
        )
        assert await bw._get_halftime_score(session, 1) == (45, 45)

    async def test_a_two_half_sport_takes_one_entry(self):
        session = _Session(box=_box([1, 0], [0, 1]), sport_key="soccer_epl")
        assert await bw._get_halftime_score(session, 1) == (1, 0)

    async def test_ncaab_double_overtime_is_four_entries_and_still_one_half(self):
        """The case that makes `len` useless, driven end to end.

        Four entries, and the right answer is `[0]`, not `[0] + [1]`.
        """
        session = _Session(
            box=_box([34, 31, 9, 8], [30, 35, 9, 12]),
            sport_key="basketball_ncaab",
        )
        assert await bw._get_halftime_score(session, 1) == (34, 30)

    async def test_a_sport_with_no_half_refuses_rather_than_guessing(self):
        session = _Session(box=_box([1, 2, 0], [0, 1, 1]), sport_key="icehockey_nhl")
        assert await bw._get_halftime_score(session, 1) is None

    async def test_an_unknown_sport_refuses(self):
        session = _Session(box=_box([10, 10, 10, 10], [9, 9, 9, 9]), sport_key=None)
        assert await bw._get_halftime_score(session, 1) is None

    async def test_an_incomplete_half_refuses(self):
        """#816's guard, said correctly for a quarter game.

        One quarter on the board is not a finished half. The old `>= 2` test
        would have accepted this the moment a second quarter appeared; the
        point here is that a QUARTER sport needs two entries before the answer
        exists at all.
        """
        session = _Session(box=_box([23], [24]), sport_key="basketball_nba")
        assert await bw._get_halftime_score(session, 1) is None

    async def test_a_malformed_linescore_refuses_instead_of_raising(self):
        """A null inside the array must not take down a grading loop."""
        session = _Session(box=_box([23, None, 27, 30], [24, 21, 24, 35]), sport_key="basketball_nba")
        assert await bw._get_halftime_score(session, 1) is None

    async def test_no_box_score_refuses(self):
        session = _Session(box=None, sport_key="basketball_nba")
        assert await bw._get_halftime_score(session, 1) is None

    async def test_the_scoring_plays_path_still_wins_when_it_has_an_answer(self):
        """The authoritative source is unchanged and is still consulted first."""

        class _Row:
            home_score = 51
            away_score = 49

        session = _Session(
            plays=_Row(),
            box=_box([23, 22, 27, 30], [24, 21, 24, 35]),
            sport_key="basketball_nba",
        )
        assert await bw._get_halftime_score(session, 1) == (51, 49)
        assert session.calls == 1, "the fallback ran even though plays answered"
