"""A baseball game never ends in a tie — and the staleness closer may not say it did.

Alex read "Final · TIED 1-1" on an Orioles page (event 15291461). The real game
finished 1-2. The 1-1 came from ``detect_and_close_stale_events``, which marks an
event terminal on an ODDS signal and never touches scores, so the row's frozen
mid-game score silently became its final.

Two things are guarded here:

1. ``is_impossible_final`` — the rules claim itself, in BOTH directions. The
   false arm matters as much as the true one: NFL ties, spring-training ties and
   NCAA-baseball ties are real results, and a guard that fires on them gets muted.

2. The closer's BEHAVIOUR. These drive the real ``detect_and_close_stale_events``
   against a fake session and read the UPDATE it emits. They deliberately do not
   use ``inspect.getsource``: a source-containment assertion passes as happily on
   a call site that is dead as on one that runs, and this defect is precisely a
   value reaching the database.

No test here anchors on the clock (gotcha #44): every timestamp is derived by
offset from a single fixed ``_NOW``.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.tasks.odds_polling import (
    _impossible_final_scrub,
    detect_and_close_stale_events,
)
from app.utils.impossible_final import is_impossible_final, sport_allows_draw

# Fixed anchor. Offset FIRST, never truncate-then-branch.
_NOW = datetime(2026, 3, 15, 12, 0, 0, tzinfo=timezone.utc)


# ── 1. The rules claim ──────────────────────────────────────────────────────


class TestSportAllowsDraw:
    @pytest.mark.parametrize(
        "sport_key",
        [
            "baseball_mlb",
            "basketball_nba",
            "basketball_wnba",
            "basketball_ncaab",
            "basketball_other",
            "icehockey_nhl",
            "tennis_atp_cincinnati_open",
            "tennis_wta_canadian_open",
            "BASEBALL_MLB",  # case is not a rules distinction
        ],
    )
    def test_rules_guarantee_a_winner(self, sport_key):
        assert sport_allows_draw(sport_key) is False

    @pytest.mark.parametrize(
        "sport_key",
        [
            # Spring training stops at an agreed inning. Sits UNDER the
            # `baseball_mlb` prefix and must escape it.
            "baseball_mlb_preseason",
        ],
    )
    def test_named_exceptions_permit_a_draw(self, sport_key):
        assert sport_allows_draw(sport_key) is True

    @pytest.mark.parametrize(
        "sport_key",
        [
            "americanfootball_nfl",  # ties are real, regular season and pre
            "americanfootball_nfl_preseason",
            "americanfootball_cfl",
            "baseball_ncaa",  # curfew / suspension ties are real
            "icehockey_sweden_allsvenskan",  # this league kept the tie
            "soccer_epl",
            "mma_mixed_martial_arts",  # a draw is a scorecard outcome
            "golf_pga",
            "",
            None,
        ],
    )
    def test_no_rules_claim_is_made(self, sport_key):
        """``None`` is not ``True``. It means we have not made a claim."""
        assert sport_allows_draw(sport_key) is None


class TestIsImpossibleFinal:
    def test_the_specimen(self):
        """Event 15291461 as it actually sat in production."""
        assert is_impossible_final("baseball_mlb", "closed", 1, 1) is True

    @pytest.mark.parametrize("status", ["completed", "closed"])
    def test_both_terminal_statuses_read_as_final_to_a_user(self, status):
        assert is_impossible_final("baseball_mlb", status, 3, 3) is True

    @pytest.mark.parametrize("status", ["scheduled", "live", None, ""])
    def test_a_game_still_in_progress_may_be_level(self, status):
        assert is_impossible_final("baseball_mlb", status, 3, 3) is False

    def test_a_real_result_is_not_impossible(self):
        assert is_impossible_final("baseball_mlb", "closed", 1, 2) is False

    @pytest.mark.parametrize(
        "sport_key,home,away",
        [
            ("americanfootball_nfl_preseason", 9, 9),  # the real 15291341
            ("baseball_mlb_preseason", 4, 4),
            ("baseball_ncaa", 0, 0),
            ("icehockey_sweden_allsvenskan", 2, 2),
        ],
    )
    def test_sports_that_really_tie_are_never_asserted_against(
        self, sport_key, home, away
    ):
        assert is_impossible_final(sport_key, "closed", home, away) is False

    @pytest.mark.parametrize("home,away", [(None, None), (1, None), (None, 1)])
    def test_a_missing_score_is_not_a_lie(self, home, away):
        """NULL means "we don't know" — the honest state this fix WRITES."""
        assert is_impossible_final("baseball_mlb", "closed", home, away) is False


# ── 2. The closer's behaviour ───────────────────────────────────────────────


def _event(**over):
    base = dict(
        id=15291461,
        home_team_name="Colorado Rockies",
        away_team_name="Baltimore Orioles",
        home_score=1,
        away_score=1,
        status="live",
        commence_time=_NOW - timedelta(hours=6),
        completed_at=None,
        statpal_end_time=None,
        win_probability_sources=None,
        sport=SimpleNamespace(key="baseball_mlb"),
    )
    base.update(over)
    return SimpleNamespace(**base)


class TestScrub:
    def test_an_impossible_final_loses_its_scores(self):
        assert _impossible_final_scrub(_event()) == {
            "home_score": None,
            "away_score": None,
        }

    def test_a_real_result_is_left_alone(self):
        assert _impossible_final_scrub(_event(home_score=1, away_score=2)) == {}

    def test_a_sport_that_can_tie_is_left_alone(self):
        ev = _event(
            sport=SimpleNamespace(key="americanfootball_nfl"),
            home_score=9,
            away_score=9,
        )
        assert _impossible_final_scrub(ev) == {}

    def test_an_event_with_no_sport_loaded_is_left_alone(self):
        assert _impossible_final_scrub(_event(sport=None)) == {}


class _FakeResult:
    def __init__(self, value, scalar_list=None):
        self._value = value
        self._scalar_list = scalar_list

    def scalars(self):
        return SimpleNamespace(all=lambda: self._scalar_list)

    def scalar(self):
        return self._value

    def first(self):
        return None


class _FakeSession:
    """Returns the live-event list first, then 0 for every snapshot count.

    0 recent snapshots + 0 total snapshots is the ``no_odds_data`` branch —
    exactly the branch a duplicate row always takes, because odds are keyed on
    an ``external_id`` it does not have.
    """

    def __init__(self, events):
        self._events = events
        self.updates = []
        self._first = True

    async def execute(self, stmt, params=None):
        if self._first:
            self._first = False
            return _FakeResult(None, scalar_list=self._events)
        if stmt.__class__.__name__ == "Update":
            self.updates.append(dict(stmt.compile().params))
            return _FakeResult(None)
        return _FakeResult(0)


async def _run(events):
    session = _FakeSession(events)
    await detect_and_close_stale_events(session)
    # The closer wraps each event in try/except (gotcha #42), so an exception
    # inside it is swallowed and would present as "no UPDATE" — which several
    # assertions below could not distinguish from a deliberate refusal to close.
    # Fail loudly instead.
    assert (
        session.updates
    ), "the closer emitted no UPDATE at all — check for a swallowed error"
    return session.updates


@pytest.mark.asyncio
class TestCloserWritesNoImpossibleFinal:
    async def test_no_odds_data_close_nulls_an_impossible_score(self):
        """THE REGRESSION. Before the fix this UPDATE carried status alone and
        the 1-1 stood as the final."""
        updates = await _run([_event()])

        assert len(updates) == 1, "the event should still be closed"
        params = updates[0]
        assert params["status"] == "closed"
        assert params["home_score"] is None
        assert params["away_score"] is None

    async def test_statpal_end_close_nulls_an_impossible_score(self):
        """The other close path in the same function. A fix on one branch only
        is not a fix — the specimen row carried a statpal fixture id."""
        updates = await _run([_event(statpal_end_time=_NOW - timedelta(hours=1))])

        assert len(updates) == 1
        params = updates[0]
        assert params["status"] == "closed"
        assert params["home_score"] is None
        assert params["away_score"] is None

    async def test_a_real_result_closes_with_its_score_intact(self):
        """The must-not-regress control. The overwhelming majority of closes are
        legitimate and must be untouched."""
        updates = await _run([_event(home_score=1, away_score=2)])

        assert len(updates) == 1
        params = updates[0]
        assert params["status"] == "closed"
        assert "home_score" not in params
        assert "away_score" not in params

    async def test_an_nfl_tie_closes_with_its_score_intact(self):
        updates = await _run(
            [
                _event(
                    sport=SimpleNamespace(key="americanfootball_nfl"),
                    home_score=9,
                    away_score=9,
                )
            ]
        )

        assert len(updates) == 1
        assert "home_score" not in updates[0]
