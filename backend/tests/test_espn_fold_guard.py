"""Unit tests for the ESPN cross-merged-events fold guards (#189/#190; gotcha #32).

These pure predicates enforce the invariant `completed_at >= commence_time` at the
ESPN write sites so an earlier same-matchup game's terminal state can never again
be folded onto a later sibling (the 439-event inverted-completed_at class). The
forensic anchor is the Sox-Mets row: event 14970335, commence 2026-07-12 17:40,
completed_at 2026-07-11 00:46 — a game recorded as finishing ~41h before it began.
"""

from datetime import datetime, timedelta, timezone

from app.utils.espn_helpers import (
    commence_correction_inverts_completion,
    completion_stamp_inverts_commence,
    espn_live_write_is_premature,
    espn_replay_unsettles,
    espn_terminal_write_is_fold,
)


def _dt(y, mo, d, h=0, mi=0):
    return datetime(y, mo, d, h, mi, tzinfo=timezone.utc)


class TestCompletionStampInvertsCommence:
    def test_completed_before_commence_is_inversion(self):
        # The Sox-Mets fold: stamping a Jul-11 completion onto the Jul-12 event.
        assert completion_stamp_inverts_commence(
            _dt(2026, 7, 12, 17, 40), _dt(2026, 7, 11, 0, 46)
        ) is True

    def test_completed_after_commence_is_fine(self):
        assert completion_stamp_inverts_commence(
            _dt(2026, 7, 12, 17, 40), _dt(2026, 7, 12, 20, 30)
        ) is False

    def test_equal_is_not_inversion(self):
        t = _dt(2026, 7, 12, 17, 40)
        assert completion_stamp_inverts_commence(t, t) is False

    def test_missing_side_is_not_inversion(self):
        assert completion_stamp_inverts_commence(None, _dt(2026, 7, 11)) is False
        assert completion_stamp_inverts_commence(_dt(2026, 7, 12), None) is False


class TestCommenceCorrectionInvertsCompletion:
    def test_moving_commence_past_completion_is_inversion(self):
        # An already-completed event (finished Jul 11) whose commence would be
        # "corrected" to Jul 12 — the same inversion, from the commence side.
        assert commence_correction_inverts_completion(
            _dt(2026, 7, 12, 17, 40), _dt(2026, 7, 11, 0, 46)
        ) is True

    def test_moving_commence_before_completion_is_fine(self):
        assert commence_correction_inverts_completion(
            _dt(2026, 7, 12, 10, 0), _dt(2026, 7, 12, 13, 0)
        ) is False

    def test_no_completion_recorded_never_inverts(self):
        assert commence_correction_inverts_completion(_dt(2026, 7, 12), None) is False


class TestEspnTerminalWriteIsFold:
    def _now(self):
        return _dt(2026, 7, 11, 1, 0)  # the moment the Jul-10/11 game finished

    def test_future_commence_event_is_a_fold(self):
        # ESPN's just-finished game resolved onto the not-yet-played Jul-12 sibling.
        assert espn_terminal_write_is_fold(_dt(2026, 7, 12, 17, 40), self._now()) is True

    def test_started_event_is_not_a_fold(self):
        # A genuinely in-progress event (commence in the past) is fine.
        assert espn_terminal_write_is_fold(_dt(2026, 7, 11, 0, 5), self._now()) is False

    def test_within_slack_is_not_a_fold(self):
        # Commence 1h ahead of now (< 2h slack) tolerates clock/commence jitter.
        assert espn_terminal_write_is_fold(self._now() + timedelta(hours=1), self._now()) is False

    def test_just_beyond_slack_is_a_fold(self):
        assert espn_terminal_write_is_fold(self._now() + timedelta(hours=3), self._now()) is True

    def test_missing_commence_is_not_a_fold(self):
        assert espn_terminal_write_is_fold(None, self._now()) is False


class TestEspnReplayUnsettles:
    """#1201 un-settle-on-replay: a settled event that ESPN reports IN PROGRESS
    (a postponed→replayed game, or a wrong-sibling fold that never really
    finished) must revert from completed/closed to live."""

    def test_completed_event_reported_in_progress_unsettles(self):
        assert espn_replay_unsettles("completed", "in") is True

    def test_closed_event_reported_in_progress_unsettles(self):
        assert espn_replay_unsettles("closed", "in") is True

    def test_scheduled_event_is_not_an_unsettle(self):
        # scheduled → live is handled by a separate branch, not the un-settle path.
        assert espn_replay_unsettles("scheduled", "in") is False

    def test_live_event_is_not_an_unsettle(self):
        assert espn_replay_unsettles("live", "in") is False

    def test_settled_event_reported_final_does_not_unsettle(self):
        # ESPN post/final on a settled row is the steady state, not a replay.
        assert espn_replay_unsettles("completed", "post") is False
        assert espn_replay_unsettles("completed", "final") is False

    def test_settled_event_reported_scheduled_does_not_unsettle(self):
        assert espn_replay_unsettles("closed", "pre") is False


class TestEspnLiveWriteIsPremature:
    """#1207 premature-live guard: an event must not flip live (nor store an ESPN
    win-prob) while its own commence_time is still meaningfully in the future —
    the observed defect was event 15165209 going live + ESPN win-prob ~4h early."""

    def _now(self):
        return _dt(2026, 7, 22, 15, 0)  # 3pm UTC; a game commencing 7pm hasn't started

    def test_commence_hours_ahead_is_premature(self):
        # The 4h-early case: ESPN says "in" but first pitch is 4h out.
        assert espn_live_write_is_premature(self._now() + timedelta(hours=4), self._now()) is True

    def test_started_event_is_not_premature(self):
        # A genuinely live game (commence in the past) writes normally.
        assert espn_live_write_is_premature(self._now() - timedelta(minutes=30), self._now()) is False

    def test_within_grace_is_not_premature(self):
        # Commence 10 min ahead (< 15 min grace) tolerates near-start jitter.
        assert espn_live_write_is_premature(self._now() + timedelta(minutes=10), self._now()) is False

    def test_just_beyond_grace_is_premature(self):
        assert espn_live_write_is_premature(self._now() + timedelta(minutes=30), self._now()) is True

    def test_missing_commence_is_not_premature(self):
        assert espn_live_write_is_premature(None, self._now()) is False

    def test_grace_is_tighter_than_fold_slack(self):
        # A 1h-future commence is NOT a terminal-fold (2h slack) but IS premature
        # for a live/win-prob write (15 min grace) — the two guards are distinct.
        one_hour_out = self._now() + timedelta(hours=1)
        assert espn_terminal_write_is_fold(one_hour_out, self._now()) is False
        assert espn_live_write_is_premature(one_hour_out, self._now()) is True
