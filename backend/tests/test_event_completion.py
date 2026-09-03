"""CAL-P004 — the PRODUCER of the CAL-P002 frozen-final-score class.

CAL-P002 measured the damage (241 / 5,826 settled events storing a wrong final,
71 with the winner flipped) and CAL-P002B made the repair reachable. This suite
pins the two rules that stop new ones being minted.

The producer is a wall-clock staleness net. ``espn_sync`` closes any event that
has been live longer than its sport's max duration, keeps whatever score the last
poll wrote, and grades ``win_probability_sources.final_result`` to 1.0/0.0 off it.
A game that runs long — extra innings, overtime, a rain delay — is still being
PLAYED when that fires, so a mid-game score becomes a permanent final. The NBA
anchor held 45-56, a literal halftime score, for a game that finished 87-109;
the derived winner was inverted, and that is what calibration grades against.

Its docstring has always claimed the guard: "live → closed: commence_time +
max_duration has passed AND no score updates in the last 30 min". No such check
was ever written. These tests are that claim, made executable.
"""
from datetime import datetime, timedelta, timezone

import pytest

from app.utils.event_completion import (
    STILL_ACTIVE_MINUTES,
    derive_completed_at,
    game_may_still_be_running,
)

UTC = timezone.utc
NOW = datetime(2026, 8, 7, 4, 0, tzinfo=UTC)
START = datetime(2026, 8, 7, 0, 0, tzinfo=UTC)


class TestStillRunningGuard:
    """The check that keeps a long game from being settled mid-play."""

    def test_a_source_reporting_right_now_holds_the_close(self):
        assert game_may_still_be_running(NOW - timedelta(minutes=1), NOW) is True

    def test_activity_inside_the_window_holds_the_close(self):
        assert game_may_still_be_running(
            NOW - timedelta(minutes=STILL_ACTIVE_MINUTES - 1), NOW
        ) is True

    def test_silence_past_the_window_allows_the_close(self):
        # The net must keep working: a genuinely finished game whose sources went
        # quiet still has to close, or events pile up stuck on "live".
        assert game_may_still_be_running(
            NOW - timedelta(minutes=STILL_ACTIVE_MINUTES + 1), NOW
        ) is False

    def test_the_boundary_is_not_still_running(self):
        assert game_may_still_be_running(
            NOW - timedelta(minutes=STILL_ACTIVE_MINUTES), NOW
        ) is False

    def test_no_snapshot_at_all_is_not_evidence_of_activity(self):
        # The ordinary case for an event nothing reports on. Treating absence as
        # activity would disable the staleness net entirely.
        assert game_may_still_be_running(None, NOW) is False

    def test_the_window_is_the_thirty_minutes_the_docstring_promised(self):
        assert STILL_ACTIVE_MINUTES == 30


class TestCompletedAtDerivation:
    """gotcha #22 — completed_at is a GAME-END time, never now()."""

    def test_the_last_post_commence_snapshot_wins(self):
        ended = START + timedelta(hours=2, minutes=40)
        assert derive_completed_at(ended, START) == ended

    def test_no_snapshot_leaves_it_null_rather_than_guessing(self):
        # A visible gap the repair can fill beats a plausible-looking wrong value
        # that nothing will ever question. This is the whole gotcha #22 lesson:
        # now() is when the BACKEND noticed, not when the game ended, and chart
        # domains and "settled" language stand on it.
        assert derive_completed_at(None, START) is None

    def test_a_completion_before_the_start_is_refused(self):
        # gotcha #46: completed_at < commence_time means an earlier game's data
        # merged onto this event (the 439-row incident). Stamping it would
        # manufacture the exact invariant violation the audit hunts for.
        assert derive_completed_at(START - timedelta(hours=1), START) is None

    def test_a_completion_exactly_at_the_start_is_allowed(self):
        assert derive_completed_at(START, START) == START

    def test_a_missing_commence_time_yields_nothing(self):
        assert derive_completed_at(START, None) is None

    def test_it_never_invents_now(self):
        # The precise regression: the old code wrote now() unconditionally.
        assert derive_completed_at(None, START, now=NOW) is None


class TestSnapshotEvidenceQuery:
    def test_only_post_commence_snapshots_count(self):
        from app.utils.event_completion import LAST_POST_COMMENCE_SNAPSHOT_SQL

        # A pregame line says nothing about when play ended, so every arm of the
        # query must be anchored to the event's own commence_time. live/042 left
        # one arm, so there is one anchor to find rather than two.
        assert LAST_POST_COMMENCE_SNAPSHOT_SQL.count(
            "captured_at >= e.commence_time"
        ) == 1

    def test_only_play_reporting_snapshots_are_consulted(self):
        """live/042: the evidence is what REPORTS on the game, not what prices it.

        Was ``assert "odds_snapshots" in ...``. That arm is gone on purpose:
        every row in that table is a bookmaker line, and a book quoting a match
        it will still take action on is not a witness that the match is being
        played.
        """
        from app.utils.event_completion import LAST_POST_COMMENCE_SNAPSHOT_SQL

        assert "win_prob_snapshots" in LAST_POST_COMMENCE_SNAPSHOT_SQL
        assert "odds_snapshots" not in LAST_POST_COMMENCE_SNAPSHOT_SQL

    def test_it_is_batched(self):
        from sqlalchemy import text

        from app.utils.event_completion import LAST_POST_COMMENCE_SNAPSHOT_SQL

        # Per-event querying inside a loop over every live event is what made
        # the CAL-P002 repair time out. One bind, one pass.
        assert sorted(text(LAST_POST_COMMENCE_SNAPSHOT_SQL)._bindparams) == ["event_ids"]


class TestBothProducersAreWired:
    """The decision logic above is pure and directly tested; these pin the glue.

    Source-level assertions, kept as a cheap tripwire. They are NOT the wiring
    proof: both nets now have behavioural harnesses further down this file
    (``TestStalenessNetEndToEnd`` for espn_sync, ``TestOddsNetSportDuration``
    for odds_polling), and queue 067 is why. A ``getsource`` assertion cannot
    tell "the function calls this" from "the function's docstring mentions it",
    and it certainly cannot tell whether the value the call returns is used to
    decide anything.
    """

    def test_espn_sync_holds_a_game_that_may_still_be_running(self):
        import inspect

        from app.tasks.espn_sync import _transition_event_statuses_impl

        src = inspect.getsource(_transition_event_statuses_impl)
        assert "game_may_still_be_running" in src
        assert "held_still_running" in src

    def test_espn_sync_no_longer_stamps_now_as_the_end_time(self):
        import inspect

        from app.tasks.espn_sync import _transition_event_statuses_impl

        src = inspect.getsource(_transition_event_statuses_impl)
        assert "derive_completed_at" in src
        assert "event.completed_at = now" not in src

    def test_odds_polling_no_longer_stamps_now_as_the_end_time(self):
        import inspect

        from app.tasks.odds_polling import detect_and_close_stale_events

        src = inspect.getsource(detect_and_close_stale_events)
        assert "derive_completed_at" in src
        assert 'close_values["completed_at"] = now' not in src

    def test_the_statpal_end_time_is_still_preferred_when_we_have_one(self):
        import inspect

        from app.tasks.odds_polling import detect_and_close_stale_events

        # A real end time from a real source outranks any derivation. This
        # branch must survive the change.
        src = inspect.getsource(detect_and_close_stale_events)
        assert 'close_vals["completed_at"] = statpal_end' in src

    def test_the_repair_and_the_producers_share_one_rule(self):
        # If these ever diverge, the repair starts "fixing" completed_at to a
        # value the producer would not have written, and the two fight forever.
        import scripts.repair_event_final_scores as repair
        from app.utils.event_completion import LAST_POST_COMMENCE_SNAPSHOT_SQL

        assert repair._LAST_SNAPSHOT_SQL is LAST_POST_COMMENCE_SNAPSHOT_SQL


@pytest.mark.parametrize(
    "minutes_since_last_snapshot,expect_hold",
    [(0, True), (5, True), (29, True), (30, False), (31, False), (600, False)],
)
def test_hold_or_close_table(minutes_since_last_snapshot, expect_hold):
    assert game_may_still_be_running(
        NOW - timedelta(minutes=minutes_since_last_snapshot), NOW
    ) is expect_hold


# ---------------------------------------------------------------------------
# CAL-P005 — end-to-end harness for the espn_sync staleness net.
#
# WHY THIS EXISTS. CAL-P002 shipped 38 tests, every one of them on a pure
# predicate, and the thing that actually broke in production was the glue around
# them. The lesson generalises: rules tested in isolation prove the rules, not
# the caller. `_transition_event_statuses_impl` has never had a harness because
# it runs inside a Celery task over a live ORM session — so this builds one, by
# dispatching a fake session on statement shape and select order (which is
# deterministic in this function).
#
# The three cases below are the whole producer contract: hold a game that may
# still be running, close one that is genuinely over and stamp its END time, and
# still close one nothing ever reported on.
# ---------------------------------------------------------------------------


class _Ev:
    """Mutable stand-in for an Event row — the net assigns to it directly."""

    def __init__(self, id, sport_key, commence_time, home_score=None, away_score=None,
                 win_probability_sources=None):
        self.id = id
        self.status = "live"
        self.commence_time = commence_time
        self.completed_at = None
        self.home_score = home_score
        self.away_score = away_score
        self.win_probability_sources = win_probability_sources or {}
        self.home_team_name = "Home"
        self.away_team_name = "Away"
        self.sport = type("S", (), {"key": sport_key})()


class _NetSession:
    def __init__(self, live, snapshots):
        self._selects = [[], live, [], []]  # scheduled, live, bogus, future-settled
        self._snapshots = snapshots
        self.blend_updates = []

    async def execute(self, stmt, params=None):
        sql = str(stmt)
        if "MAX(x.captured_at)" in sql:
            from types import SimpleNamespace
            return type("R", (), {"all": lambda _s: [
                SimpleNamespace(event_id=i, last_snap=t)
                for i, t in self._snapshots.items() if i in params["event_ids"]
            ]})()
        if sql.startswith("UPDATE"):
            self.blend_updates.append(sql)
            return None
        rows = self._selects.pop(0)
        return type("R", (), {
            "scalars": lambda _s: type("S", (), {"all": lambda _x: rows})()
        })()

    async def commit(self):
        pass


async def _run_net(live, snapshots, now):
    import contextlib
    from unittest.mock import patch

    session = _NetSession(live, snapshots)

    @contextlib.asynccontextmanager
    async def _fake_session():
        yield session

    import app.tasks.espn_sync as mod

    class _FrozenNow(datetime):
        @classmethod
        def now(cls, tz=None):
            return now

    with patch("app.tasks.base.get_task_session", _fake_session), \
            patch.object(mod, "datetime", _FrozenNow):
        stats = await mod._transition_event_statuses_impl()
    return session, stats


# An NBA game: max duration 3.5h, so 6h since start trips the wall-clock net.
_LATE = NOW - timedelta(hours=6)


class TestStalenessNetEndToEnd:
    @pytest.mark.asyncio
    async def test_a_game_still_being_reported_on_is_held_live(self):
        # THE producer bug. Overtime/extra innings/rain delay: the wall-clock
        # net fires while the game is still being played, and the mid-game score
        # becomes a permanent final with the derived winner possibly inverted.
        ev = _Ev(1, "basketball_nba", _LATE, home_score=45, away_score=56,
                 win_probability_sources={"kalshi": {"home_win_probability": 0.4}})
        session, stats = await _run_net(
            [ev], {1: NOW - timedelta(minutes=5)}, NOW
        )
        assert ev.status == "live"
        assert ev.completed_at is None
        assert stats["held_still_running"] == 1
        assert stats["live_to_closed"] == 0
        # And critically: the blend was NOT graded off the halftime score.
        assert session.blend_updates == []

    @pytest.mark.asyncio
    async def test_a_genuinely_finished_game_still_closes(self):
        # The net must keep working — this is what it is for.
        ended = NOW - timedelta(hours=3)
        ev = _Ev(2, "basketball_nba", _LATE, home_score=109, away_score=87,
                 win_probability_sources={"kalshi": {"home_win_probability": 0.8}})
        session, stats = await _run_net([ev], {2: ended}, NOW)
        assert ev.status == "closed"
        assert stats["live_to_closed"] == 1
        assert stats["held_still_running"] == 0
        assert session.blend_updates, "a real final must still resolve the blend"

    @pytest.mark.asyncio
    async def test_the_close_stamps_the_game_end_not_the_processing_time(self):
        # gotcha #22. The old code wrote now(), which is wrong by however long
        # the net took to notice — and it is what chart domains stand on.
        ended = NOW - timedelta(hours=3)
        ev = _Ev(3, "basketball_nba", _LATE, home_score=4, away_score=2)
        await _run_net([ev], {3: ended}, NOW)
        assert ev.completed_at == ended
        assert ev.completed_at != NOW

    @pytest.mark.asyncio
    async def test_an_event_nothing_ever_reported_on_closes_with_a_null_end(self):
        # Silence is not evidence of activity, so it must still close; but we
        # have no honest end time, so the gap stays visible for the repair.
        ev = _Ev(4, "basketball_nba", _LATE, home_score=3, away_score=1)
        _, stats = await _run_net([ev], {}, NOW)
        assert ev.status == "closed"
        assert ev.completed_at is None
        assert stats["live_to_closed"] == 1

    @pytest.mark.asyncio
    async def test_held_and_closed_events_are_handled_independently(self):
        # One bad/held item must never suppress its healthy siblings (gotcha #42).
        held = _Ev(5, "basketball_nba", _LATE, home_score=45, away_score=56)
        done = _Ev(6, "basketball_nba", _LATE, home_score=109, away_score=87)
        _, stats = await _run_net(
            [held, done],
            {5: NOW - timedelta(minutes=2), 6: NOW - timedelta(hours=2)},
            NOW,
        )
        assert (held.status, done.status) == ("live", "closed")
        assert (stats["held_still_running"], stats["live_to_closed"]) == (1, 1)


# ---------------------------------------------------------------------------
# QUEUE 067 — end-to-end harness for the ODDS staleness net.
#
# WHY THIS EXISTS, and it is CAL-P005's lesson landing a second time. That
# harness was built for `espn_sync`'s net and the comment above it says the
# quiet part out loud: "rules tested in isolation prove the rules, not the
# caller." `odds_polling.detect_and_close_stale_events` was left on source-level
# assertions, and the defect that survived is precisely the one a source-level
# assertion cannot see.
#
# `get_max_duration_for_sport` has FOURTEEN tests in
# `test_odds_polling_helpers.py`. Every one of them passed, every day, while the
# closer it was written for never called it — so every sport was eligible to be
# auto-closed at MIN_HOURS_BEFORE_STALENESS_CHECK, 90 minutes. Seven of the
# nineteen priced impossible ties found on production had closed 88-91 minutes
# after first pitch. A 90-minute-old MLB game is in the fifth inning.
#
# So these tests do not ask what the lookup returns. They put a baseball event
# in front of the closer with stale odds and ask whether it survives.
# ---------------------------------------------------------------------------


class _OddsEv:
    """Stand-in for an Event row as the odds net reads it.

    The net writes through `Event.__table__.update()` rather than ORM attribute
    assignment, so `_OddsNetSession` applies the captured values back onto this
    object — the assertions read the row the way the database would.
    """

    def __init__(self, id, sport_key, commence_time, statpal_end_time=None):
        self.id = id
        self.status = "live"
        self.commence_time = commence_time
        self.completed_at = None
        self.statpal_end_time = statpal_end_time
        self.win_probability_sources = {}
        self.home_team_name = "Home"
        self.away_team_name = "Away"
        self.sport = type("S", (), {"key": sport_key})()


class _OddsNetSession:
    """Fake session dispatching on statement shape.

    `evidence` maps event id -> {"recent": int, "total": int, "last_snap": dt}.
      recent    snapshots updated inside ODDS_STALE_MINUTES
      total     snapshots this event has EVER had (0 == never priced)
      last_snap most recent post-commence capture from any source, or None
    """

    def __init__(self, live, evidence):
        self._live = live
        self._evidence = evidence
        self.updates = []  # (event_id, values dict) in write order

    async def execute(self, stmt, params=None):
        sql = str(stmt)

        if "MAX(x.captured_at)" in sql:
            snap = self._evidence.get(params["event_ids"][0], {}).get("last_snap")
            row = None if snap is None else type("Row", (), {"last_snap": snap})()
            return type("R", (), {"first": lambda _s: row})()

        if sql.startswith("UPDATE"):
            compiled = stmt.compile()
            values = {
                k: v for k, v in compiled.params.items()
                if k in ("status", "completed_at", "home_score", "away_score")
            }
            ev_id = compiled.params.get("id_1")
            self.updates.append((ev_id, values))
            for ev in self._live:
                if ev.id == ev_id:
                    for k, v in values.items():
                        setattr(ev, k, v)
            return None

        if "count(" in sql.lower() and "odds_snapshots" in sql:
            ev_id = stmt.compile().params.get("event_id_1")
            ev_evidence = self._evidence.get(ev_id, {})
            # The recent-window query is the one carrying the valid_until
            # predicate; the "did we EVER have odds" query is event_id alone.
            key = "recent" if "valid_until" in sql else "total"
            n = ev_evidence.get(key, 0)
            return type("R", (), {"scalar": lambda _s: n})()

        # The live-event selection.
        rows = self._live
        return type("R", (), {
            "scalars": lambda _s: type("S", (), {"all": lambda _x: rows})()
        })()


async def _run_odds_net(live, evidence, now=NOW):
    from unittest.mock import patch

    import app.tasks.odds_polling as mod

    class _FrozenNow(datetime):
        @classmethod
        def now(cls, tz=None):
            return now

    session = _OddsNetSession(live, evidence)
    with patch.object(mod, "datetime", _FrozenNow):
        closed = await mod.detect_and_close_stale_events(session)
    return session, closed


def _stale(total=12, last_snap_hours_ago=3):
    """Odds evidence for a game the books have stopped pricing.

    `recent` is 0 (nothing inside ODDS_STALE_MINUTES) and the last capture is
    hours old, so the still-running guard does not hold it. The ONLY thing left
    that can decide this event's fate is elapsed time against its sport's
    maximum — which is exactly what these tests are about.
    """
    return {"recent": 0, "total": total,
            "last_snap": NOW - timedelta(hours=last_snap_hours_ago)}


class TestOddsNetSportDuration:
    """The gate the config declared and the closer ignored."""

    @pytest.mark.asyncio
    async def test_a_baseball_game_is_not_over_after_two_hours(self):
        # THE BUG. Stale odds, two hours in — a real MLB game in the fifth or
        # sixth inning. The old closer stamped this FINAL; event 14877917
        # (BOS@NYY, 463 outcomes) was closed 0-0 ninety minutes in.
        ev = _OddsEv(1, "baseball_mlb", NOW - timedelta(hours=2))
        session, closed = await _run_odds_net([ev], {1: _stale()})
        assert ev.status == "live"
        assert ev.completed_at is None
        assert (closed, session.updates) == (0, [])

    @pytest.mark.asyncio
    async def test_a_baseball_game_closes_after_five_and_a_half_hours(self):
        # And the net must keep working. SPORT_MAX_DURATIONS["baseball"] is 5.0
        # ("extra innings possible"); past that, silent books are evidence.
        ev = _OddsEv(2, "baseball_mlb", NOW - timedelta(hours=5.5))
        session, closed = await _run_odds_net([ev], {2: _stale()})
        assert ev.status == "closed"
        assert closed == 1
        assert session.updates[0][1]["status"] == "closed"

    @pytest.mark.asyncio
    async def test_the_boundary_is_the_sports_own_maximum(self):
        # Exactly 5.0h has not EXCEEDED the maximum; a minute past it has.
        at = _OddsEv(3, "baseball_mlb", NOW - timedelta(hours=5))
        past = _OddsEv(4, "baseball_mlb", NOW - timedelta(hours=5, minutes=1))
        await _run_odds_net([at], {3: _stale()})
        await _run_odds_net([past], {4: _stale()})
        assert (at.status, past.status) == ("live", "closed")

    @pytest.mark.asyncio
    async def test_the_gate_is_per_sport_and_not_one_new_constant(self):
        # Four hours in: past basketball's 3.5 and hockey's 3.5, inside
        # baseball's 5.0 and tennis's 6.0. A single replacement constant —
        # however much better than 1.5 — cannot produce this split, so this is
        # the test that fails if someone "fixes" the bug with another literal.
        nba = _OddsEv(5, "basketball_nba", NOW - timedelta(hours=4))
        nhl = _OddsEv(6, "icehockey_nhl", NOW - timedelta(hours=4))
        mlb = _OddsEv(7, "baseball_mlb", NOW - timedelta(hours=4))
        atp = _OddsEv(8, "tennis_atp", NOW - timedelta(hours=4))
        live = [nba, nhl, mlb, atp]
        await _run_odds_net(live, {e.id: _stale() for e in live})
        assert [e.status for e in live] == ["closed", "closed", "live", "live"]

    @pytest.mark.asyncio
    async def test_no_sport_is_closeable_at_ninety_minutes(self):
        # The literal defect signature: seven of the nineteen priced impossible
        # ties sat at 88-91 minutes. The shortest maximum in the table is 3.0h,
        # so nothing in it can be closed on a wall clock this early.
        from app.tasks.config import SPORT_MAX_DURATIONS

        live = [
            _OddsEv(100 + i, f"{prefix}_x", NOW - timedelta(minutes=90))
            for i, prefix in enumerate(SPORT_MAX_DURATIONS)
        ]
        _, closed = await _run_odds_net(live, {e.id: _stale() for e in live})
        assert closed == 0
        assert {e.status for e in live} == {"live"}

    @pytest.mark.asyncio
    async def test_an_unknown_sport_gets_the_default_maximum(self):
        # 4.0h default: still live at 3h, closed at 5h. Not 1.5h either way.
        early = _OddsEv(9, "kabaddi_pkl", NOW - timedelta(hours=3))
        late = _OddsEv(10, "kabaddi_pkl", NOW - timedelta(hours=5))
        await _run_odds_net([early], {9: _stale()})
        await _run_odds_net([late], {10: _stale()})
        assert (early.status, late.status) == ("live", "closed")


class TestOddsNetEvidenceRules:
    """What the net is allowed to treat as evidence a game has ended."""

    @pytest.mark.asyncio
    async def test_an_event_we_never_priced_is_never_closed_here(self):
        # `no_odds_data`. Zero snapshots gives an ODDS net no odds signal at
        # all, and it used to be the strongest close signal in the file —
        # closing unconditionally, which is why every orphan closed on its first
        # eligible pass. Gotcha #53: an empty read is not a fact.
        ev = _OddsEv(11, "baseball_mlb", NOW - timedelta(hours=8))
        session, closed = await _run_odds_net(
            [ev], {11: {"recent": 0, "total": 0, "last_snap": None}}
        )
        assert ev.status == "live"
        assert (closed, session.updates) == (0, [])

    @pytest.mark.asyncio
    async def test_the_sibling_net_still_owns_that_population(self):
        # Declining above is only safe because something better-informed closes
        # these. If this beat entry is ever removed or slowed, the events the
        # odds net now declines stop being closed by anything.
        from app.tasks import celery_app

        entry = celery_app.conf.beat_schedule["transition-event-statuses"]
        assert entry["task"] == "app.tasks.transition_event_statuses"
        assert entry["schedule"] <= 300

    @pytest.mark.asyncio
    async def test_a_game_a_source_is_still_reporting_on_is_held(self):
        # Past the maximum with silent books, but something captured this event
        # two minutes ago. Books go quiet on a long game too; closing here is
        # the CAL-P002 producer, freezing a mid-game score as the final.
        ev = _OddsEv(12, "baseball_mlb", NOW - timedelta(hours=6))
        session, closed = await _run_odds_net(
            [ev], {12: {"recent": 0, "total": 40,
                        "last_snap": NOW - timedelta(minutes=2)}}
        )
        assert ev.status == "live"
        assert (closed, session.updates) == (0, [])

    @pytest.mark.asyncio
    async def test_the_close_stamps_the_game_end_not_the_processing_time(self):
        # gotcha #22, on the path that now actually reaches a write.
        ended = NOW - timedelta(hours=1, minutes=30)
        ev = _OddsEv(13, "baseball_mlb", NOW - timedelta(hours=6))
        await _run_odds_net(
            [ev], {13: {"recent": 0, "total": 40, "last_snap": ended}}
        )
        assert ev.status == "closed"
        assert ev.completed_at == ended
        assert ev.completed_at != NOW

    @pytest.mark.asyncio
    async def test_fresh_odds_never_close_however_long_the_game_runs(self):
        # The maximum duration is a necessary condition, never a sufficient one.
        ev = _OddsEv(14, "baseball_mlb", NOW - timedelta(hours=9))
        _, closed = await _run_odds_net(
            [ev], {14: {"recent": 6, "total": 60,
                        "last_snap": NOW - timedelta(minutes=1)}}
        )
        assert (ev.status, closed) == ("live", 0)

    @pytest.mark.asyncio
    async def test_a_statpal_end_time_still_closes_inside_the_maximum(self):
        # A real end time from a real source is not a wall-clock guess, so the
        # per-sport gate must not be allowed to suppress it. This arm keeps its
        # MIN_HOURS_BEFORE_STALENESS_CHECK reach.
        ended = NOW - timedelta(minutes=10)
        ev = _OddsEv(15, "baseball_mlb", NOW - timedelta(hours=2),
                     statpal_end_time=ended)
        _, closed = await _run_odds_net([ev], {15: _stale()})
        assert (ev.status, ev.completed_at, closed) == ("closed", ended, 1)

    @pytest.mark.asyncio
    async def test_a_held_event_never_suppresses_a_closeable_sibling(self):
        # gotcha #42 — one item's fate must not decide another's.
        held = _OddsEv(16, "baseball_mlb", NOW - timedelta(hours=2))
        done = _OddsEv(17, "basketball_nba", NOW - timedelta(hours=6))
        _, closed = await _run_odds_net(
            [held, done], {16: _stale(), 17: _stale()}
        )
        assert (held.status, done.status) == ("live", "closed")
        assert closed == 1
