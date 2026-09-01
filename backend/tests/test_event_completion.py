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

        # A pregame line says nothing about when play ended, so both halves of
        # the union must be anchored to the event's own commence_time.
        assert LAST_POST_COMMENCE_SNAPSHOT_SQL.count(
            "captured_at >= e.commence_time"
        ) == 2

    def test_both_snapshot_sources_are_consulted(self):
        from app.utils.event_completion import LAST_POST_COMMENCE_SNAPSHOT_SQL

        assert "win_prob_snapshots" in LAST_POST_COMMENCE_SNAPSHOT_SQL
        assert "odds_snapshots" in LAST_POST_COMMENCE_SNAPSHOT_SQL

    def test_it_returns_both_the_last_change_and_the_last_confirmation(self):
        # #2444. Two questions, two columns: last_snap dates a close, last_seen
        # decides whether to take it. One query so the producers and the repair
        # can never disagree about either.
        from app.utils.event_completion import LAST_POST_COMMENCE_SNAPSHOT_SQL

        assert "AS last_snap" in LAST_POST_COMMENCE_SNAPSHOT_SQL
        assert "AS last_seen" in LAST_POST_COMMENCE_SNAPSHOT_SQL

    def test_the_confirmation_column_reads_valid_until(self):
        # Both snapshot tables bump valid_until (not captured_at) when a poll
        # re-sees the same value. A last_seen that ignores valid_until is just
        # last_snap under another name, and the defect is back.
        from app.utils.event_completion import LAST_POST_COMMENCE_SNAPSHOT_SQL

        sql = LAST_POST_COMMENCE_SNAPSHOT_SQL
        assert sql.count("valid_until") >= 3, (
            "valid_until must be selected from BOTH snapshot tables and used in "
            "the last_seen aggregate"
        )
        assert "GREATEST" in sql, (
            "last_seen must never go backwards from last_snap — a row whose "
            "valid_until is NULL or stale still confirms at its captured_at"
        )
        assert "COALESCE" in sql, "a NULL valid_until must fall back, not poison MAX"

    def test_both_snapshot_arms_carry_the_confirmation_column(self):
        # A one-armed fix would silently keep the defect for whichever source
        # the arm it missed happens to be the freshest on.
        from app.utils.event_completion import LAST_POST_COMMENCE_SNAPSHOT_SQL

        arms = LAST_POST_COMMENCE_SNAPSHOT_SQL.split("UNION ALL")
        assert len(arms) == 2
        for arm in arms:
            if "FROM win_prob_snapshots" in arm or "FROM odds_snapshots" in arm:
                assert "valid_until" in arm

    def test_it_is_batched(self):
        from sqlalchemy import text

        from app.utils.event_completion import LAST_POST_COMMENCE_SNAPSHOT_SQL

        # Per-event querying inside a loop over every live event is what made
        # the CAL-P002 repair time out. One bind, one pass.
        assert sorted(text(LAST_POST_COMMENCE_SNAPSHOT_SQL)._bindparams) == ["event_ids"]


class TestBothProducersAreWired:
    """The decision logic above is pure and directly tested; these pin the glue.

    Neither staleness net has an existing test harness (both run inside Celery
    tasks over live ORM sessions), so wiring is asserted at source level — the
    same way this repo pins other cross-module contracts.
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

    def test_odds_polling_also_holds_a_game_that_may_still_be_running(self):
        # #2444: this class is called TestBothProducersAreWired, but only
        # espn_sync was ever asserted to consult the still-running guard. A net
        # that can close an event must be able to see that something is still
        # reporting on it.
        import inspect

        from app.tasks.odds_polling import detect_and_close_stale_events

        src = inspect.getsource(detect_and_close_stale_events)
        assert "game_may_still_be_running" in src

    def test_neither_net_asks_the_hold_question_with_the_last_price_change(self):
        # The whole #2444 defect in one assertion. Both snapshot tables dedup at
        # write time, so `captured_at`/`last_snap` is the last time the price
        # MOVED — passing it to the hold guard reads a market we are polling
        # successfully as a dead one. The guard must be asked with `last_seen`.
        import inspect

        from app.tasks.espn_sync import _transition_event_statuses_impl
        from app.tasks.odds_polling import detect_and_close_stale_events

        for fn in (_transition_event_statuses_impl, detect_and_close_stale_events):
            src = inspect.getsource(fn)
            for line in src.splitlines():
                if "game_may_still_be_running(" not in line:
                    continue
                arg = line.split("game_may_still_be_running(", 1)[1]
                assert "last_snap" not in arg, (
                    f"{fn.__name__} asks the hold question with the last price "
                    f"CHANGE, not the last confirmation: {line.strip()}"
                )
                assert "last_seen" in arg, (
                    f"{fn.__name__} must pass last_seen: {line.strip()}"
                )

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
    """Fake session for the net.

    ``snapshots`` maps event id → either a single datetime (the price changed
    then and was last confirmed then — the two coincide) or an explicit
    ``(last_snap, last_seen)`` pair, which is how a frozen-but-still-quoted
    market looks: an old change, a recent confirmation.
    """

    def __init__(self, live, snapshots):
        self._selects = [[], live, [], []]  # scheduled, live, bogus, future-settled
        self._snapshots = snapshots
        self.blend_updates = []

    async def execute(self, stmt, params=None):
        sql = str(stmt)
        if "MAX(x.captured_at)" in sql:
            from types import SimpleNamespace
            return type("R", (), {"all": lambda _s: [
                SimpleNamespace(
                    event_id=i,
                    last_snap=(t[0] if isinstance(t, tuple) else t),
                    last_seen=(t[1] if isinstance(t, tuple) else t),
                )
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
    async def test_a_frozen_price_that_is_still_being_quoted_is_not_silence(self):
        # #2444, the US Open producer. A pre-match tennis line sits at the same
        # number for hours: every poll re-confirms it, so valid_until climbs and
        # captured_at does not. Asking the hold question with the last CHANGE
        # reads an actively-quoted market as a dead one and fabricates a
        # completion — which then clips the real in-play movement out of the
        # chart, and the match page shows a win-probability line that never
        # moves. Measured on the 2026-08-30 draw: 73 of 75 closes were this.
        ev = _Ev(7, "tennis_atp_us_open", NOW - timedelta(hours=7))
        session, stats = await _run_net(
            # price last MOVED 6h ago; a book CONFIRMED it 2 minutes ago
            [ev], {7: (NOW - timedelta(hours=6), NOW - timedelta(minutes=2))}, NOW
        )
        assert ev.status == "live", (
            "a market a bookmaker is still quoting was declared over"
        )
        assert ev.completed_at is None
        assert stats["held_still_running"] == 1
        assert stats["live_to_closed"] == 0
        assert session.blend_updates == []

    @pytest.mark.asyncio
    async def test_a_frozen_price_nobody_is_quoting_any_more_still_closes(self):
        # The other direction, or the fix would just disable the net: when the
        # books stop confirming too, the event is genuinely over and the last
        # real change is still what dates it.
        moved = NOW - timedelta(hours=6)
        ev = _Ev(8, "tennis_atp_us_open", NOW - timedelta(hours=7))
        _, stats = await _run_net(
            [ev], {8: (moved, NOW - timedelta(hours=5))}, NOW
        )
        assert ev.status == "closed"
        assert ev.completed_at == moved, (
            "the close must still be dated by the last price CHANGE, not by the "
            "last confirmation — last_seen decides whether, last_snap decides when"
        )
        assert stats["live_to_closed"] == 1

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
