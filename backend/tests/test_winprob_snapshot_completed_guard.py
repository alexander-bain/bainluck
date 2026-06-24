"""#922: completed/closed events must not grow a win-prob "stale tail".

On post-final re-process cycles (espn_sync's 6h recently-completed window) ESPN
can keep echoing a value / report MLB as "in" for 20-40 min, and the stat model
drifts — appending those as new WinProbSnapshot points extended the chart 20-40
min past the real final. `_create_or_update_win_prob_snapshot(is_completed=True)`
captures the terminal point ONCE and then refreshes in place instead of
appending. Live games are unaffected.
"""

import inspect
from unittest.mock import AsyncMock, MagicMock

from app.models.models import WinProbSnapshot
from app.tasks.snapshots import _create_or_update_win_prob_snapshot


def _session_returning(existing):
    sess = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none = MagicMock(return_value=existing)
    sess.execute = AsyncMock(return_value=result)
    return sess


async def test_completed_event_value_drift_updates_in_place_no_new_point():
    # last live point (e.g. 0.92) + a post-final drift to terminal 1.0
    existing = WinProbSnapshot(
        event_id=1, source="stat_model",
        home_win_probability=0.92, away_win_probability=0.08,
        game_state={"period": "Bottom 9th"}, reading_count=3,
    )
    sess = _session_returning(existing)

    snap, is_new = await _create_or_update_win_prob_snapshot(
        sess, event_id=1, source="stat_model",
        home_win_probability=1.0, away_win_probability=0.0,
        game_state={"period": "Final"}, is_completed=True,
    )

    assert is_new is False           # NO new time-series point appended (no tail)
    assert snap is existing          # refreshed in place
    assert float(snap.home_win_probability) == 1.0  # terminal value captured
    assert snap.reading_count == 4
    sess.add.assert_not_called() if hasattr(sess, "add") else None


async def test_live_event_value_drift_still_appends_new_point():
    existing = WinProbSnapshot(
        event_id=1, source="stat_model",
        home_win_probability=0.60, away_win_probability=0.40,
        game_state={"period": "3rd"}, reading_count=1,
    )
    sess = _session_returning(existing)

    snap, is_new = await _create_or_update_win_prob_snapshot(
        sess, event_id=1, source="stat_model",
        home_win_probability=0.75, away_win_probability=0.25,
        game_state={"period": "3rd"}, is_completed=False,
    )

    assert is_new is True            # live games keep the full time series
    assert snap is not existing
    assert float(snap.home_win_probability) == 0.75


async def test_completed_event_no_prior_creates_single_terminal_point():
    sess = _session_returning(None)

    snap, is_new = await _create_or_update_win_prob_snapshot(
        sess, event_id=2, source="espn",
        home_win_probability=1.0, away_win_probability=0.0,
        is_completed=True,
    )

    assert is_new is True            # capture the terminal point once if none exists
    assert float(snap.home_win_probability) == 1.0


async def test_completed_event_same_value_dedups_as_before():
    existing = WinProbSnapshot(
        event_id=3, source="espn",
        home_win_probability=1.0, away_win_probability=0.0,
        game_state={"period": "Final"}, reading_count=2,
    )
    sess = _session_returning(existing)

    snap, is_new = await _create_or_update_win_prob_snapshot(
        sess, event_id=3, source="espn",
        home_win_probability=1.0, away_win_probability=0.0,
        game_state={"period": "Final"}, is_completed=True,
    )
    assert is_new is False
    assert snap is existing
    assert snap.reading_count == 3


def test_writers_pass_is_completed_from_event_status():
    """Wiring guard: both ESPN writers derive is_completed from OUR event.status
    and the ESPNSnapshot append is gated for completed events."""
    from app.utils import espn_helpers

    wp_src = inspect.getsource(espn_helpers.write_espn_win_probability)
    assert 'getattr(event, "status", None) in ("completed", "closed")' in wp_src
    assert "is_completed=is_completed" in wp_src
    assert "if not is_completed:" in wp_src  # ESPNSnapshot append guarded

    sm_src = inspect.getsource(espn_helpers.compute_and_write_stat_model)
    assert 'getattr(event, "status", None) in ("completed", "closed")' in sm_src
    assert "is_completed=is_completed" in sm_src
