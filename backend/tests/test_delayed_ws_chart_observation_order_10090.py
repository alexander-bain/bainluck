"""Delayed WS points preserve observation clocks and newer poll history."""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock
import pytest
from app.models.models import WinProbSnapshot
from app.tasks.snapshots import _create_or_update_win_prob_snapshot

AT = datetime(2026, 10, 11, 0, 52, 30, tzinfo=timezone.utc)


def point(at, home, away=None, draw=None):
    return WinProbSnapshot(
        event_id=1,
        source="kalshi",
        captured_at=at,
        home_win_probability=home,
        away_win_probability=(1 - home) if away is None else away,
        draw_probability=draw,
        reading_count=1,
        valid_until=at + timedelta(seconds=5),
        game_state={"poll_type": "live_fast"},
    )


def session(previous, following):
    results = []
    for row in (previous, following):
        result = MagicMock()
        result.scalar_one_or_none.return_value = row
        results.append(result)
    return AsyncMock(execute=AsyncMock(side_effect=results))


@pytest.mark.asyncio
@pytest.mark.parametrize("same_predecessor", [False, True])
async def test_old_point_is_inserted_before_newer_poll_without_rewriting_it(
    same_predecessor,
):
    previous = point(AT - timedelta(seconds=25), 0.40 if same_predecessor else 0.30)
    following = point(AT + timedelta(seconds=10), 0.80)
    previous.valid_until = following.captured_at
    newer_before = (
        following.home_win_probability,
        following.away_win_probability,
        following.captured_at,
        following.valid_until,
        following.reading_count,
    )
    s = session(previous, following)
    snapshot, new = await _create_or_update_win_prob_snapshot(
        s,
        1,
        "kalshi",
        0.40,
        0.60,
        game_state={"poll_type": "ws_fast_lane"},
        observed_at=AT.isoformat(),
    )
    assert (
        following.home_win_probability,
        following.away_win_probability,
        following.captured_at,
        following.valid_until,
        following.reading_count,
    ) == newer_before
    assert new is not same_predecessor
    if new:
        assert (
            snapshot.captured_at == AT and snapshot.valid_until == following.captured_at
        )
        assert previous.valid_until == AT
    else:
        assert snapshot is previous and previous.valid_until == following.captured_at
    statements = [call.args[0] for call in s.execute.await_args_list]
    assert all(stmt._for_update_arg is not None for stmt in statements)
    assert "captured_at <= " in str(statements[0])
    assert "captured_at > " in str(statements[1])


@pytest.mark.asyncio
async def test_delayed_same_value_does_not_move_a_later_poll_observation_backwards():
    previous = point(AT - timedelta(seconds=25), 0.40)
    previous.valid_until = AT + timedelta(seconds=5)
    snapshot, new = await _create_or_update_win_prob_snapshot(
        session(previous, None),
        1,
        "kalshi",
        0.40,
        0.60,
        observed_at=AT,
    )
    assert not new and snapshot is previous
    assert previous.valid_until == AT + timedelta(seconds=5)
    assert previous.captured_at == AT - timedelta(seconds=25)


@pytest.mark.asyncio
async def test_delayed_heartbeat_and_three_way_values_keep_original_time():
    previous = point(AT - timedelta(seconds=60), 0.40, away=0.40, draw=0.20)
    snapshot, new = await _create_or_update_win_prob_snapshot(
        session(previous, None),
        1,
        "kalshi",
        0.40,
        0.40,
        draw_probability=0.20,
        observed_at=AT,
        max_gap_seconds=60,
    )
    assert new and snapshot.captured_at == AT and previous.valid_until == AT
    assert snapshot.away_win_probability == 0.40 and snapshot.draw_probability == 0.20


@pytest.mark.asyncio
@pytest.mark.parametrize("second_slot_only", [False, True])
async def test_delayed_change_splits_newer_dedup_evidence_into_actual_tail(
    second_slot_only,
):
    previous = point(AT - timedelta(seconds=10), 0.40, away=0.40, draw=0.20)
    polled_at = AT + timedelta(seconds=10)
    previous.valid_until = polled_at
    previous.reading_count = 2
    s = session(previous, None)
    s.add = MagicMock()
    home, away, draw = (0.40, 0.50, 0.10) if second_slot_only else (0.60, 0.30, 0.10)
    delayed, new = await _create_or_update_win_prob_snapshot(
        s,
        1,
        "kalshi",
        home,
        away,
        draw_probability=draw,
        observed_at=AT,
    )
    assert new and delayed.captured_at == AT
    assert delayed.home_win_probability == home
    assert delayed.away_win_probability == away and delayed.draw_probability == draw
    assert delayed.valid_until == polled_at
    tail = s.add.call_args.args[0]
    assert tail.captured_at == tail.valid_until == polled_at
    assert tail.home_win_probability == 0.40
    assert tail.away_win_probability == 0.40 and tail.draw_probability == 0.20
    assert tail.game_state == previous.game_state
    assert previous.valid_until == AT
    assert previous.reading_count + delayed.reading_count + tail.reading_count == 3
