"""The live winner field uses the shared allocation and its own full baseline."""

from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from app.routes.golf import _allocate_live_win_field

NAMES = ["Alice Smith", "Bob Jones", "Casey Reed"]


def setup_field(values=(0.4, 0.4, 0.4)):
    players = [SimpleNamespace(player_name=n, win=v) for n, v in zip(NAMES, values)]
    rows = [
        {
            "name": p.player_name,
            "win_prob": (p.win or 0) * 100,
            "win_prob_change": 3,
            "top_5_prob": 60,
            "position_change": 2,
        }
        for p in players
    ]
    return rows, players


def baseline(values):
    return {n.lower(): {"win_prob": v} for n, v in zip(NAMES, values)}


def test_live_allocation_uses_the_full_field_and_leaves_placement_prices_alone():
    rows, players = setup_field()
    original = deepcopy(players)
    _allocate_live_win_field(rows, players, {}, baseline_is_atomic=False)
    assert sum(r["rendered_percent"] for r in rows) == 100
    assert sorted(r["rendered_percent"] for r in rows) == [33, 33, 34]
    assert [r["top_5_prob"] for r in rows] == [60, 60, 60]
    assert [r["position_change"] for r in rows] == [2, 2, 2]
    assert all(r["win_prob_change"] is None for r in rows)
    assert players == original


def test_current_and_prior_fields_have_their_own_divisors():
    rows, players = setup_field((0.6, 0.3, 0.3))
    previous = baseline((60, 60, 30))
    before = deepcopy(previous)
    _allocate_live_win_field(rows, players, previous, baseline_is_atomic=True)
    assert [r["win_prob"] for r in rows] == pytest.approx([50, 25, 25])
    assert [r["win_prob_change"] for r in rows] == [10, -15, 5]
    assert previous == before


@pytest.mark.parametrize(
    "atomic,previous",
    [
        (False, baseline((40, 40, 40))),
        (True, baseline((40, 40))),
        (True, baseline((float("nan"), 40, 40))),
        (True, baseline(("40", 40, 40))),
    ],
)
def test_an_incomplete_staggered_or_refused_baseline_withholds_only_the_move(
    atomic, previous
):
    rows, players = setup_field()
    _allocate_live_win_field(rows, players, previous, baseline_is_atomic=atomic)
    assert sum(r["rendered_percent"] for r in rows) == 100
    assert all(r["win_prob_change"] is None for r in rows)


def test_a_zero_in_the_baseline_is_an_observation():
    rows, players = setup_field()
    _allocate_live_win_field(
        rows, players, baseline((0, 60, 60)), baseline_is_atomic=True
    )
    assert [r["win_prob_change"] for r in rows] == [33.3, -16.7, -16.7]


@pytest.mark.parametrize("values", [(None, 0.6, 0.6), (0.7, 0.7, 0.7)])
def test_refused_current_fields_remain_on_their_existing_basis(values):
    rows, players = setup_field(values)
    before = deepcopy(rows)
    _allocate_live_win_field(
        rows, players, baseline((40, 40, 40)), baseline_is_atomic=True
    )
    assert rows == before
    assert len(rows) == 3


@pytest.mark.anyio
@pytest.mark.parametrize(
    "values,status", [((1, 0, 0), "completed"), ((0.4, 0.4, 0.4), "live")]
)
async def test_actual_route_keeps_its_status_and_completed_rows(
    monkeypatch, values, status
):
    import app.routes.golf as golf
    import app.services.database as database
    import app.services.datagolf_api as dg

    players = [
        dg.DataGolfPlayer(dg_id=i, player_name=n, win=v, position=str(i + 1))
        for i, (n, v) in enumerate(zip(NAMES, values))
    ]
    service = SimpleNamespace(
        get_in_play_with_info=AsyncMock(return_value=(players, {"current_round": 2})),
        close=AsyncMock(),
    )
    monkeypatch.setattr(dg, "DataGolfAPIService", lambda: service)
    monkeypatch.setattr(golf, "_leaderboard_cache", {})

    def no_database():
        raise RuntimeError("offline baseline fixture")

    monkeypatch.setattr(database, "async_session_maker", no_database)
    result = await golf.get_golf_leaderboard("pga")
    assert result["status"] == status
    assert len(result["players"]) == 3
    if status == "completed":
        assert [r["win_prob"] for r in result["players"]] == [100, 0, 0]
        assert all("rendered_percent" not in r for r in result["players"])
    else:
        assert sum(r["rendered_percent"] for r in result["players"]) == 100
    service.close.assert_awaited_once()


def test_partial_live_field_stays_raw_instead_of_scaling_up():
    rows, players = setup_field((0.2, 0.2, 0.2))
    _allocate_live_win_field(
        rows, players, baseline((10, 10, 10)), baseline_is_atomic=True
    )
    assert [r["win_prob"] for r in rows] == [20, 20, 20]
    assert all("rendered_percent" not in row for row in rows)
    assert [r["win_prob_change"] for r in rows] == [3, 3, 3]


def test_midpoint_cleanup_cannot_shift_an_allocation_to_a_different_player():
    players = [
        SimpleNamespace(player_name=f"Player {i}", win=p)
        for i, p in enumerate([0.5] * 10 + [0.3, 0.3])
    ]
    rows = [
        {"name": p.player_name, "win_prob": p.win * 100, "win_prob_change": None}
        for p in players
    ]
    before = deepcopy(rows)
    _allocate_live_win_field(rows, players, {}, baseline_is_atomic=False)
    assert rows == before
    assert len(rows) == 12


@pytest.mark.anyio
@pytest.mark.parametrize("mode", ["complete", "staggered", "missing"])
async def test_round_one_route_requires_one_complete_recorded_instant(
    monkeypatch, mode
):
    from datetime import datetime, timedelta, timezone
    from unittest.mock import MagicMock
    import app.routes.golf as golf
    import app.services.database as database
    import app.services.datagolf_api as dg

    players = [
        dg.DataGolfPlayer(dg_id=i, player_name=n, win=0.4, position=str(i + 1))
        for i, n in enumerate(NAMES)
    ]
    service = SimpleNamespace(
        get_in_play_with_info=AsyncMock(return_value=(players, {"current_round": 1})),
        close=AsyncMock(),
    )
    monkeypatch.setattr(dg, "DataGolfAPIService", lambda: service)
    monkeypatch.setattr(golf, "_leaderboard_cache", {})
    first, second, third = MagicMock(), MagicMock(), MagicMock()
    first.scalar_one_or_none.return_value = SimpleNamespace(id=10)
    second.all.return_value = [
        SimpleNamespace(id=i, name=n) for i, n in enumerate(NAMES)
    ]
    at = datetime(2026, 11, 3, tzinfo=timezone.utc)
    snapshots = [
        SimpleNamespace(
            outcome_id=i,
            probability=value,
            captured_at=at
            + (timedelta(minutes=i) if mode == "staggered" else timedelta()),
        )
        for i, value in enumerate((0.3, 0.3, 0.6))
    ]
    third.scalars.return_value.all.return_value = (
        snapshots[:-1] if mode == "missing" else snapshots
    )
    session = AsyncMock()
    session.execute.side_effect = [first, second, third]
    manager = MagicMock()
    manager.__aenter__ = AsyncMock(return_value=session)
    manager.__aexit__ = AsyncMock(return_value=False)
    monkeypatch.setattr(database, "async_session_maker", lambda: manager)
    result = await golf.get_golf_leaderboard("pga")
    assert sum(p["rendered_percent"] for p in result["players"]) == 100
    moves = [p["win_prob_change"] for p in result["players"]]
    assert moves == ([8.3, 8.3, -16.7] if mode == "complete" else [None, None, None])
    assert session.execute.await_count == 3
