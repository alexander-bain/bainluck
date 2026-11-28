"""#12108 Step 1: live write guards against pre-start contamination."""

from __future__ import annotations

import inspect
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models.models import Event, WinProbSnapshot
from app.routes import events as events_route
from app.tasks import odds_polling
from app.tasks.snapshots import _create_or_update_win_prob_snapshot
from app.utils import espn_helpers
from app.utils.game_pairing import live_write_is_premature


def _session_returning(existing):
    sess = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none = MagicMock(return_value=existing)
    sess.execute = AsyncMock(return_value=result)
    return sess


def _begin_nested_session():
    sess = AsyncMock()

    @asynccontextmanager
    async def _nested():
        yield

    sess.begin_nested = _nested
    sess.add = MagicMock()
    return sess


def _live_event(*, commence_time: datetime) -> SimpleNamespace:
    return SimpleNamespace(
        id=9001,
        espn_id="401999999",
        status="live",
        home_team_name="Boston Celtics",
        away_team_name="New York Knicks",
        commence_time=commence_time,
        opening_home_spread=-3.5,
        opening_home_probability=0.58,
        win_probability_sources={},
        period="1st",
        game_clock="9:15",
    )


def _espn_entry(*, status: str = "in", clock: str = "9:15") -> SimpleNamespace:
    return SimpleNamespace(
        espn_id="401999999",
        home_team=SimpleNamespace(display_name="Boston Celtics", name="Boston Celtics"),
        away_team=SimpleNamespace(display_name="New York Knicks", name="New York Knicks"),
        status=status,
        status_detail="1st Quarter",
        period=1,
        clock=clock,
        home_score=12,
        away_score=8,
        home_win_probability=0.66,
        position_outran_wall=False,
    )


class TestFinishedWritePreservesPreStartSnapshot:
    @pytest.mark.asyncio
    async def test_completed_write_does_not_overwrite_pre_start_row(self):
        now = datetime.now(timezone.utc)
        commence = now - timedelta(hours=2)
        pre_start_at = commence - timedelta(minutes=30)
        existing = WinProbSnapshot(
            event_id=101,
            source="stat_model",
            home_win_probability=0.62,
            away_win_probability=0.38,
            game_state={"stage": "pregame"},
            captured_at=pre_start_at,
            reading_count=2,
        )
        sess = _session_returning(existing)

        snap, is_new = await _create_or_update_win_prob_snapshot(
            sess,
            event_id=101,
            source="stat_model",
            home_win_probability=0.001,
            away_win_probability=0.999,
            game_state={"period": "Final"},
            is_completed=True,
            commence_time=commence,
        )

        assert is_new is True
        assert snap is not existing
        # Pre-start row must remain completely intact in value and timestamp.
        assert float(existing.home_win_probability) == 0.62
        assert float(existing.away_win_probability) == 0.38
        assert existing.game_state == {"stage": "pregame"}
        assert existing.captured_at == pre_start_at
        assert existing.valid_until >= commence
        # Terminal reading lands at or after commence_time on its own row.
        assert snap.captured_at >= commence
        assert float(snap.home_win_probability) == 0.001
        assert float(snap.away_win_probability) == 0.999

    @pytest.mark.asyncio
    async def test_completed_write_preserves_at_start_boundary_row_and_keeps_922_after(self):
        now = datetime.now(timezone.utc)
        commence = now - timedelta(hours=2)
        pre_start_at = commence
        existing = WinProbSnapshot(
            event_id=102,
            source="stat_model",
            home_win_probability=0.55,
            away_win_probability=0.45,
            game_state={"period": "Pregame"},
            captured_at=pre_start_at,
            reading_count=1,
        )
        sess = _session_returning(existing)

        first_terminal, is_new_1 = await _create_or_update_win_prob_snapshot(
            sess,
            event_id=102,
            source="stat_model",
            home_win_probability=0.999,
            away_win_probability=0.001,
            game_state={"period": "Final"},
            is_completed=True,
            commence_time=commence,
        )
        assert is_new_1 is True
        assert float(existing.home_win_probability) == 0.55
        assert existing.captured_at == pre_start_at
        assert first_terminal.captured_at >= commence

        # Subsequent post-final completion write must refresh the new post-start
        # terminal row in place (#922 stale-tail guard).
        sess2 = _session_returning(first_terminal)
        second_terminal, is_new_2 = await _create_or_update_win_prob_snapshot(
            sess2,
            event_id=102,
            source="stat_model",
            home_win_probability=1.0,
            away_win_probability=0.0,
            game_state={"period": "Final"},
            is_completed=True,
            commence_time=commence,
        )
        assert is_new_2 is False
        assert second_terminal is first_terminal
        assert float(second_terminal.home_win_probability) == 1.0
        assert second_terminal.reading_count == 2

    @pytest.mark.asyncio
    async def test_completed_write_with_future_venue_start_preserves_once_then_refreshes(self):
        now = datetime.now(timezone.utc)
        commence = now + timedelta(hours=1)
        existing = WinProbSnapshot(
            event_id=103,
            source="kalshi",
            home_win_probability=0.51,
            away_win_probability=0.49,
            game_state={"market_name": "Winner"},
            captured_at=now - timedelta(minutes=30),
            reading_count=1,
        )
        sess = _session_returning(existing)

        term1, is_new_1 = await _create_or_update_win_prob_snapshot(
            sess,
            event_id=103,
            source="kalshi",
            home_win_probability=0.99,
            away_win_probability=0.01,
            game_state={"market_name": "Winner"},
            is_completed=True,
            commence_time=commence,
        )
        assert is_new_1 is True
        assert float(existing.home_win_probability) == 0.51
        assert term1.game_state["_completed_terminal"] is True

        sess2 = _session_returning(term1)
        term2, is_new_2 = await _create_or_update_win_prob_snapshot(
            sess2,
            event_id=103,
            source="kalshi",
            home_win_probability=1.0,
            away_win_probability=0.0,
            game_state={"market_name": "Winner"},
            is_completed=True,
            commence_time=commence,
        )
        assert is_new_2 is False
        assert term2 is term1
        assert term2.game_state["_completed_terminal"] is True
        assert float(term2.home_win_probability) == 1.0

        # Served chart projection removes internal markers before sending to clients.
        wp_hist = {"kalshi": [{"game_state": term2.game_state}]}
        events_route._project_served_game_state(wp_hist)
        assert "_completed_terminal" not in (wp_hist["kalshi"][0]["game_state"] or {})

    @pytest.mark.asyncio
    async def test_completed_write_resolves_commence_from_sqlalchemy_identity_map(self):
        now = datetime.now(timezone.utc)
        commence = now - timedelta(hours=1)
        pre_start_at = commence - timedelta(minutes=15)
        existing = WinProbSnapshot(
            event_id=104,
            source="stat_model",
            home_win_probability=0.60,
            away_win_probability=0.40,
            captured_at=pre_start_at,
            reading_count=1,
        )
        engine = create_engine("sqlite:///:memory:")
        from sqlalchemy.orm.attributes import instance_state

        with Session(engine) as sync_sess:
            ev = Event(
                id=104,
                sport_id=1,
                external_id="ev-104",
                home_team_name="Home",
                away_team_name="Away",
                commence_time=commence,
            )
            state = instance_state(ev)
            state.key = (Event, (104,), None)
            sync_sess.identity_map._dict[(Event, (104,), None)] = state

            fake_async = _session_returning(existing)
            fake_async.identity_map = sync_sess.identity_map

            snap, is_new = await _create_or_update_win_prob_snapshot(
                fake_async,
                event_id=104,
                source="stat_model",
                home_win_probability=0.001,
                away_win_probability=0.999,
                is_completed=True,
            )
            assert is_new is True
            assert float(existing.home_win_probability) == 0.60
            assert float(snap.home_win_probability) == 0.001
        engine.dispose()


class TestStatModelPrematureLiveWriteGuard:
    @pytest.mark.asyncio
    async def test_stat_model_refuses_live_write_two_hours_before_start(self):
        event = _live_event(
            commence_time=datetime.now(timezone.utc) + timedelta(hours=2)
        )
        ee = _espn_entry()
        sess = _begin_nested_session()
        stats: dict = {}

        with patch(
            "app.utils.nonvenue_live_push.write_nonvenue_probability",
            new=AsyncMock(),
        ) as mock_push, patch(
            "app.tasks.snapshots._create_or_update_win_prob_snapshot",
            new=AsyncMock(),
        ) as mock_snap:
            wrote = await espn_helpers.compute_and_write_stat_model(
                sess, event, ee, "basketball_nba", stats
            )

        assert wrote is False
        assert stats.get("stat_model_premature_skipped") == 1
        mock_push.assert_not_awaited()
        mock_snap.assert_not_awaited()
        sess.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_stat_model_refuses_live_write_inside_espn_grace_before_start(self):
        event = _live_event(
            commence_time=datetime.now(timezone.utc) + timedelta(minutes=5)
        )
        ee = _espn_entry()
        sess = _begin_nested_session()
        stats: dict = {}

        with patch(
            "app.utils.nonvenue_live_push.write_nonvenue_probability",
            new=AsyncMock(),
        ) as mock_push, patch(
            "app.tasks.snapshots._create_or_update_win_prob_snapshot",
            new=AsyncMock(),
        ) as mock_snap:
            wrote = await espn_helpers.compute_and_write_stat_model(
                sess, event, ee, "basketball_nba", stats
            )

        assert wrote is False
        assert stats.get("stat_model_premature_skipped") == 1
        mock_push.assert_not_awaited()
        mock_snap.assert_not_awaited()
        sess.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_stat_model_writes_normally_after_stored_start(self):
        event = _live_event(
            commence_time=datetime.now(timezone.utc) - timedelta(minutes=5)
        )
        ee = _espn_entry()
        sess = _begin_nested_session()
        stats: dict = {}
        fake_snap = WinProbSnapshot(
            event_id=event.id,
            source="stat_model",
            home_win_probability=0.65,
            away_win_probability=0.35,
            captured_at=datetime.now(timezone.utc),
            reading_count=1,
        )

        with patch(
            "app.utils.nonvenue_live_push.write_nonvenue_probability",
            new=AsyncMock(),
        ) as mock_push, patch(
            "app.tasks.snapshots._create_or_update_win_prob_snapshot",
            new=AsyncMock(return_value=(fake_snap, True)),
        ) as mock_snap:
            wrote = await espn_helpers.compute_and_write_stat_model(
                sess, event, ee, "basketball_nba", stats
            )

        assert wrote is True
        assert stats.get("stat_model_computed") == 1
        mock_push.assert_awaited_once()
        mock_snap.assert_awaited_once()
        assert mock_snap.call_args.kwargs["commence_time"] == event.commence_time
        sess.add.assert_called_once_with(fake_snap)

    def test_odds_poll_stat_model_guard_wiring_and_timezone_normalization(self):
        src = inspect.getsource(odds_polling)
        assert "live_write_is_premature" in src
        assert "grace=timedelta(0)" in src
        assert 'commence_time=getattr(event_obj, "commence_time", None)' in src

        now_aware = datetime(2026, 11, 26, 18, 0, tzinfo=timezone.utc)
        now_naive = datetime(2026, 11, 26, 18, 0)
        start_future_naive = datetime(2026, 11, 26, 18, 5)
        start_past_naive = datetime(2026, 11, 26, 17, 55)

        assert (
            live_write_is_premature(start_future_naive, now_aware, grace=timedelta(0))
            is True
        )
        assert (
            live_write_is_premature(
                start_future_naive.replace(tzinfo=timezone.utc),
                now_naive,
                grace=timedelta(0),
            )
            is True
        )
        assert (
            live_write_is_premature(start_past_naive, now_aware, grace=timedelta(0))
            is False
        )
        assert (
            live_write_is_premature(now_aware, now_aware, grace=timedelta(0)) is False
        )
