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
