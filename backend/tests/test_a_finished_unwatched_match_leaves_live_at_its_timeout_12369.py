"""#12369: a match nothing reports on leaves the live board at its 2.5h timeout.

THE READER'S PAGE (Sun Nov 8, 10:21 AM PT): ``/sports/soccer_other`` opened on
"Live Now 31", and its first four cards were matches that were already over.
Each was marked LIVE and printed a grey "0%" beside the home team, with no
score: the venue priced them as draws at 99.95%. All six such rows had kicked
off 2.2 to 2.9 hours earlier.

WATCHED AGAIN, Mon Nov 9 (``GET /api/events?sport=soccer_other&days=14&past_days=1``).
FC Botosani v ASC Otelul Galati (15336797) and Mushuc Runa SC v Delfin SC
(15342625) kicked off at 18:00 UTC. The venue had both decided by 20:05 UTC
(home 0.05% and 99.95%). Both were still ``live`` at 20:40 UTC, 2.67h after
kickoff, and ``suspended`` by 21:10 UTC, 3.17h after. Neither row has a score,
period, ESPN id or play snapshot; each carries a soccer StatPal id, which is a
shadow anchor (#4075). So both are "never observed".

THE CAUSE. ``wall_clock_bound_hours`` answers "how many hours past
``commence_time`` may this row keep claiming to be live?" with 2.5 for such a
row: #3946's "nothing has spoken" timeout. ``_transition_event_statuses_impl``
then suspended only past ``bound + 0.5``. That half hour (BR76, May) was a
buffer on a sport's MAXIMUM duration, from before the timeout existed, and
the timeout inherited it. So an unwatched match stayed LIVE until 3.0h, about
an hour after its final whistle. The sibling net
(``odds_polling.detect_and_close_stale_events``) already releases at the bound
itself, with no buffer.

THE FIX. For soccer, whose timeout already spans a whole match (measured p99
of real duration 2.15h against 2.5h), the buffer no longer applies where the
never-observed timeout narrowed the bound. Tennis and the default keep it,
because a best-of-three can outrun 3.0h: #9418's Challenger was suspended
mid-set at 3.0h + 0.5h. Observed rows and the exempt sports (golf, American
football, MLB) keep it exactly as before.

Nothing here ends a match on a price (doctrine §R rung 4): ``suspended`` is
not Final, asserts no winner, and the scores feed can still put a resumed
match straight back to live.
"""

import contextlib
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

import app.utils.event_completion as event_completion
from app.tasks.config import SPORT_MAX_DURATIONS

UTC = timezone.utc
KICKOFF = datetime(2026, 11, 9, 18, 0, tzinfo=UTC)
SOCCER = "soccer_other"
SOCCER_MAX = SPORT_MAX_DURATIONS["default"]  # soccer has no entry of its own
TIMEOUT = event_completion.UNOBSERVED_MAX_HOURS["soccer"]


class _Ev:
    """Mutable stand-in for an Event row, as the task assigns to it."""

    def __init__(self, id, sport_key, commence_time, *, home_score=None,
                 away_score=None, statpal_fixture_id=None):
        self.id = id
        self.status = "live"
        self.commence_time = commence_time
        self.commence_time_source = "polymarket_venue"
        self.completed_at = None
        self.statpal_end_time = None
        self.home_score = home_score
        self.away_score = away_score
        self.period = None
        self.game_clock = None
        self.espn_id = None
        self.statpal_fixture_id = statpal_fixture_id
        self.win_probability_sources = {}
        self.home_team_name = "FC Botosani"
        self.away_team_name = "ASC Otelul Galati"
        self.sport = type("S", (), {"key": sport_key})()


class _EspnSession:
    """The selects `_transition_event_statuses_impl` issues, in order.

    Positional, as in `test_the_shadow_anchor_repair_survives_both_lifecycle_
    tasks_4075.py`, so a new arm lands here as an IndexError, not as silence.
    """

    def __init__(self, live):
        self._selects = [[], live, [], [], [], [], []]

    async def execute(self, stmt, params=None):
        sql = str(stmt)
        if "AS winner_source" in sql:
            return type("R", (), {"all": lambda _s: []})()
        if "GROUP BY x.event_id" in sql:
            # No play source has ever captured these rows post-commence.
            return type("R", (), {"all": lambda _s: []})()
        if sql.startswith("UPDATE"):
            return None
        rows = self._selects.pop(0)
        return type(
            "R", (), {"scalars": lambda _s: type("S", (), {"all": lambda _x: rows})()}
        )()

    def expunge_all(self):
        return None

    async def commit(self):
        pass


async def _run(rows, now):
    session = _EspnSession(rows)

    @contextlib.asynccontextmanager
    async def _fake_session():
        yield session

    import app.tasks.espn_sync as mod

    class _FrozenNow(datetime):
        @classmethod
        def now(cls, tz=None):
            return now

    with patch("app.tasks.base.get_task_session", _fake_session), patch.object(
        mod, "datetime", _FrozenNow
    ):
        return await mod._transition_event_statuses_impl()


def _botosani():
    """The specimen, as production holds it: silent but for its shadow id."""
    return _Ev(15336797, SOCCER, KICKOFF, statpal_fixture_id="9686197")


def _at(hours):
    return KICKOFF + timedelta(hours=hours)


class TestThePremise:
    def test_the_specimen_is_never_observed(self):
        row = _botosani()
        assert event_completion.event_has_never_been_observed(
            row.home_score, row.away_score, row.period, row.espn_id,
            row.statpal_fixture_id, None, SOCCER,
        ) is True

    def test_its_timeout_is_two_and_a_half_hours(self):
        assert TIMEOUT == 2.5
        assert event_completion.wall_clock_bound_hours(SOCCER, SOCCER_MAX, True) == 2.5


class TestTheUnwatchedMatchLeavesAtItsTimeout:
    @pytest.mark.asyncio
    async def test_suspended_at_the_reading_production_still_served_live(self):
        # 20:40 UTC Mon Nov 9: 2.67h after kickoff, venue decided, still LIVE.
        row = _botosani()
        stats = await _run([row], now=_at(2.67))
        assert row.status == event_completion.EVENT_SUSPENDED
        assert stats["suspended_unobserved"] == 1

    @pytest.mark.asyncio
    async def test_just_past_the_timeout_it_is_suspended(self):
        row = _botosani()
        await _run([row], now=_at(TIMEOUT + 0.05))
        assert row.status == event_completion.EVENT_SUSPENDED

    @pytest.mark.asyncio
    async def test_inside_the_timeout_it_stays_live(self):
        row = _botosani()
        await _run([row], now=_at(TIMEOUT - 0.05))
        assert row.status == "live"

    @pytest.mark.asyncio
    async def test_nothing_is_written_but_the_status(self):
        # Suspended, not closed: no completion time, no score, no result.
        row = _botosani()
        await _run([row], now=_at(2.67))
        assert row.completed_at is None
        assert (row.home_score, row.away_score) == (None, None)


class TestEveryOtherRowKeepsItsBuffer:
    @pytest.mark.asyncio
    async def test_an_observed_soccer_row_keeps_its_maximum_and_buffer(self):
        # A score means something reported on play: 4.0h maximum + 0.5h.
        row = _Ev(1, SOCCER, KICKOFF, home_score=1, away_score=0)
        await _run([row], now=_at(SOCCER_MAX + 0.4))
        assert row.status == "live"
        await _run([row], now=_at(SOCCER_MAX + 0.6))
        assert row.status == event_completion.EVENT_SUSPENDED

    @pytest.mark.parametrize("sport_key", ["americanfootball_ncaaf", "golf_pga_championship"])
    @pytest.mark.asyncio
    async def test_an_exempt_sport_keeps_its_maximum_and_buffer(self, sport_key):
        # Exempt from the timeout (`UNOBSERVED_DEFAULT_EXEMPT_PREFIXES`), so
        # its bound IS its maximum, and the buffer still applies.
        top = event_completion.wall_clock_bound_hours(
            sport_key, SPORT_MAX_DURATIONS[sport_key.split("_")[0]], True
        )
        row = _Ev(2, sport_key, KICKOFF)
        await _run([row], now=_at(top + 0.4))
        assert row.status == "live"
        await _run([row], now=_at(top + 0.6))
        assert row.status == event_completion.EVENT_SUSPENDED


def _max_hours(sport_key):
    """The sport maximum the task reads, by the task's own prefix rule."""
    return next(
        (v for k, v in SPORT_MAX_DURATIONS.items()
         if k != "default" and sport_key.startswith(k)),
        SPORT_MAX_DURATIONS["default"],
    )


class TestTheTwoNetsAgreeOnSoccer:
    @pytest.mark.parametrize("sport_key", [SOCCER, "soccer_netherlands_eredivisie"])
    @pytest.mark.asyncio
    async def test_an_unwatched_match_leaves_where_the_odds_net_releases_it(
        self, sport_key
    ):
        # `detect_and_close_stale_events` releases at `bound` itself, with no
        # buffer. For soccer this net now suspends just past the same number.
        bound = event_completion.wall_clock_bound_hours(
            sport_key, _max_hours(sport_key), True
        )
        assert bound < _max_hours(sport_key)  # the timeout narrowed it
        row = _Ev(3, sport_key, KICKOFF)
        await _run([row], now=_at(bound - 0.05))
        assert row.status == "live"
        await _run([row], now=_at(bound + 0.05))
        assert row.status == event_completion.EVENT_SUSPENDED


class TestTennisAndTheDefaultKeepTheirBuffer:
    @pytest.mark.parametrize("sport_key", ["tennis_atp", "cricket_test_match"])
    @pytest.mark.asyncio
    async def test_an_unwatched_row_still_runs_to_timeout_plus_buffer(self, sport_key):
        # A best-of-three can outrun 3.0h, and #9418's Challenger was cut off
        # mid-set even with the buffer. Unchanged here.
        bound = event_completion.wall_clock_bound_hours(
            sport_key, _max_hours(sport_key), True
        )
        assert bound < _max_hours(sport_key)
        row = _Ev(4, sport_key, KICKOFF)
        await _run([row], now=_at(bound + 0.4))
        assert row.status == "live"
        await _run([row], now=_at(bound + 0.6))
        assert row.status == event_completion.EVENT_SUSPENDED
