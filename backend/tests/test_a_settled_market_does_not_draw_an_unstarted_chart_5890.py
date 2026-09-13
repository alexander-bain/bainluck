"""#5890 answer 2 — a market we have already settled does not draw the chart of a
game that has not kicked off.

## The specimen, shot on production 2026-09-13 18:06Z

`bainluck.com/events/15298125` (Sevilla v Valencia, kick-off 19:00Z) at 390px,
**58 minutes before kick-off**
(`artifacts/BEFORE-5890q2-sevilla-15298125-390-1806Z.png`, read):

* hero `59% – 41%`, captioned "2 sportsbooks" — honest, and already fixed (#5820)
* **Win Probability chart**: the Kalshi line runs flat near 50%, **cliffs
  vertically to a labelled `99%`** and holds it to the right edge, over a control
  reading "Lead changes (7)". The x-axis prints `11:06 AM … 3:56 PM` with no
  date, so the reader takes 2026-09-11's prices for this afternoon's.

Every point on that line is market **60482102** (`KXLALIGAGAME-26SEP13SEVVCF`),
whose own row reads `status='resolved', settled_at 2026-09-11 22:49:23Z`. The two
rows refute each other; no ground truth is needed to say the chart is wrong.

## Why this file exists beside two fixes that are already live

One market, one predicate, three rails. #5820 refused it as the **blend's**
speaker; #5771 refused it as a **market card** on `/game-markets`; `/history` was
still drawing it as a **chart series**, which is why the same screenshot holds an
honest hero above a dishonest line.

## The measurement that chose the shape of the fix

Over the 21 production events in scope (2026-09-13 18:0xZ), the points at or
after the settlement stamp number **0, 1 or 2** — Sevilla has one of 942. So
"truncate `/history`'s tail at the withdrawal", the fix #5890 proposed by name,
would have moved a single point and left the cliff on the page. The series goes,
not the tail.

## What must not move, and the population that says so

    market references on unstarted events   665  across 476 events
    -> withheld                              22  markets on  21 events
    -> untouched                            643  markets on 455 events

A started event and a finished event are both unreachable: the route asks
`_event_has_not_kicked_off` first. The finished direction is the load-bearing one
(gotcha #43) — "settled means settled", a completed event keeps its whole journey
— and it is pinned twice below, at the predicate and through the route.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.dependencies.auth import get_optional_user
from app.routes.events import _event_has_not_kicked_off, _event_is_really_finished
from app.services.database import get_db, get_db_rw
from app.utils.settled_chart import (
    drop_series_from_markets,
    market_ids_in_series,
    settled_market_ids,
)
from tests.integration.test_route_events_seeded import _make_event

NOW = datetime(2026, 9, 13, 18, 6, tzinfo=timezone.utc)

SETTLED_MARKET_ID = 60482102
LIVE_MARKET_ID = 60482103


def _event(*, commence, status="scheduled", completed_at=None):
    event = MagicMock()
    event.commence_time = commence
    event.status = status
    event.completed_at = completed_at
    return event


def _market(id=SETTLED_MARKET_ID, status="resolved", graded=False):
    market = MagicMock()
    market.id = id
    market.status = status
    outcome = MagicMock()
    outcome.is_winner = graded
    market.outcomes = [outcome]
    return market


def _point(market_id, prob=0.99, minutes_ago=0):
    return {
        "timestamp": (NOW - timedelta(minutes=minutes_ago)).isoformat(),
        "home_probability": prob,
        "away_probability": round(1 - prob, 4),
        "draw_probability": None,
        "game_state": {"market_id": market_id, "yes_probability": prob},
    }


# ── The scope test: has this contest started? ────────────────────────────────


def test_the_sevilla_specimen_has_not_kicked_off():
    assert _event_has_not_kicked_off(_event(commence=NOW + timedelta(minutes=54)), NOW)


def test_a_game_in_play_has_kicked_off():
    """The 2,080-event bucket #5771 measured: a live game's settled first set is
    real information and stays on its chart."""
    assert not _event_has_not_kicked_off(
        _event(commence=NOW - timedelta(minutes=40), status="live"), NOW
    )


def test_a_completed_event_has_kicked_off_and_keeps_its_journey():
    """Settled means settled (gotcha #43). This is the direction that, if it ever
    flips, silently deletes the chart of every finished event on the site."""
    assert not _event_has_not_kicked_off(
        _event(
            commence=NOW - timedelta(hours=3),
            status="completed",
            completed_at=NOW - timedelta(hours=1),
        ),
        NOW,
    )


def test_an_event_with_no_commence_time_gets_no_opinion():
    """NULL is *unknown*, not *future*."""
    assert not _event_has_not_kicked_off(_event(commence=None), NOW)


def test_a_naive_commence_time_is_read_as_utc_and_never_raises():
    """Asked of ordinary scheduled rows, so it meets the naive datetimes older
    fixtures build. Both directions, so the coercion cannot become an abstention.
    (#5771's sibling gate took a CI red for exactly this.)"""
    assert not _event_has_not_kicked_off(
        _event(commence=NOW.replace(tzinfo=None) - timedelta(hours=3)), NOW
    )
    assert _event_has_not_kicked_off(
        _event(commence=NOW.replace(tzinfo=None) + timedelta(hours=3)), NOW
    )


def test_the_corrupt_completed_with_future_kickoff_shape_counts_as_unstarted():
    """A row claiming `completed` while its kickoff is in the FUTURE (#46 /
    gotcha #32). `_event_is_really_finished` already refuses to read it as
    settled, so this gate sees an unstarted event and withholds — the same safe
    direction the `/game-markets` sibling takes on the same input."""
    corrupt = _event(
        commence=NOW + timedelta(hours=5),
        status="completed",
        completed_at=NOW - timedelta(hours=1),
    )
    assert not _event_is_really_finished(corrupt, NOW)
    assert _event_has_not_kicked_off(corrupt, NOW)


# ── Which markets is the chart drawn from ────────────────────────────────────


def test_the_market_ids_behind_every_series_are_collected():
    history = {
        "kalshi": [_point(SETTLED_MARKET_ID), _point(SETTLED_MARKET_ID)],
        "polymarket": [_point(LIVE_MARKET_ID)],
    }
    assert market_ids_in_series(history) == {SETTLED_MARKET_ID, LIVE_MARKET_ID}


def test_a_point_from_no_market_is_never_collected_and_never_withheld():
    """ESPN and the stat model write no `market_id`. A gate about markets must
    not be able to reach them at all."""
    history = {
        "espn": [
            {"timestamp": NOW.isoformat(), "home_probability": 0.6, "game_state": {}},
            {"timestamp": NOW.isoformat(), "home_probability": 0.6, "game_state": None},
            {"timestamp": NOW.isoformat(), "home_probability": 0.6},
        ]
    }
    assert market_ids_in_series(history) == set()
    assert drop_series_from_markets(history, {}, {SETTLED_MARKET_ID}) == 0
    assert len(history["espn"]) == 3


def test_a_malformed_market_id_is_ignored_instead_of_raising():
    """`game_state` is JSONB. A page build must never throw on a lookup."""
    history = {
        "kalshi": [
            {"game_state": {"market_id": "60482102"}},
            {"game_state": {"market_id": None}},
            {"game_state": {"market_id": True}},
            {"game_state": {"market_id": "not-a-number"}},
            {"game_state": ["not", "a", "dict"]},
            "not a point at all",
        ]
    }
    assert market_ids_in_series(history) == {SETTLED_MARKET_ID}


# ── The drop ─────────────────────────────────────────────────────────────────


def test_only_the_settled_markets_points_go():
    history = {
        "kalshi": [
            _point(LIVE_MARKET_ID, 0.55, minutes_ago=30),
            _point(SETTLED_MARKET_ID, 0.99, minutes_ago=10),
        ]
    }
    meta = {"kalshi": {"snapshot_count": 2}}
    assert drop_series_from_markets(history, meta, {SETTLED_MARKET_ID}) == 1
    assert [p["home_probability"] for p in history["kalshi"]] == [0.55]
    assert meta["kalshi"]["snapshot_count"] == 1, (
        "the advertised snapshot count is rendered — a legend that counts "
        "withheld points is a caption naming a source the chart does not carry"
    )


def test_a_source_left_with_nothing_leaves_the_legend_too():
    """14 of the 21 production events draw their whole rail from the settled
    market. Keeping the key at `snapshot_count: 0` would advertise a Kalshi line
    that plots nothing — #5890's third question, same answer: no points, no
    caption."""
    history = {"kalshi": [_point(SETTLED_MARKET_ID)], "polymarket": [_point(LIVE_MARKET_ID)]}
    meta = {"kalshi": {"snapshot_count": 1}, "polymarket": {"snapshot_count": 1}}
    assert drop_series_from_markets(history, meta, {SETTLED_MARKET_ID}) == 1
    assert list(history) == ["polymarket"]
    assert list(meta) == ["polymarket"]


def test_nothing_to_withhold_changes_nothing():
    history = {"kalshi": [_point(LIVE_MARKET_ID)]}
    meta = {"kalshi": {"snapshot_count": 1}}
    assert drop_series_from_markets(history, meta, set()) == 0
    assert len(history["kalshi"]) == 1 and meta["kalshi"]["snapshot_count"] == 1


# ── Which markets count as settled ───────────────────────────────────────────


def _db_returning(markets):
    db = AsyncMock()
    result = MagicMock()
    result.scalars.return_value.unique.return_value.all.return_value = markets
    db.execute = AsyncMock(return_value=result)
    return db


@pytest.mark.asyncio
async def test_a_resolved_market_is_settled():
    assert await settled_market_ids(
        _db_returning([_market(status="resolved")]), {SETTLED_MARKET_ID}
    ) == {SETTLED_MARKET_ID}


@pytest.mark.asyncio
async def test_a_graded_but_still_open_kalshi_market_is_settled_too():
    """Gotcha #33: Kalshi leaves settled markets `status='open'`. The grade arm is
    the whole reason this delegates to `market_assigned_settled` (#1951) instead
    of testing `status` itself — and the reason the outcomes are eager-loaded."""
    assert await settled_market_ids(
        _db_returning([_market(status="open", graded=True)]), {SETTLED_MARKET_ID}
    ) == {SETTLED_MARKET_ID}


@pytest.mark.asyncio
async def test_an_open_ungraded_market_is_not_settled():
    """643 of the 665 market references on unstarted events live here."""
    assert (
        await settled_market_ids(
            _db_returning([_market(status="open", graded=False)]), {SETTLED_MARKET_ID}
        )
        == set()
    )


@pytest.mark.asyncio
async def test_no_market_ids_asks_the_database_nothing():
    db = _db_returning([])
    assert await settled_market_ids(db, set()) == set()
    db.execute.assert_not_awaited()


# ── The route asks it (a correct helper nobody calls changes no chart) ───────


def _history_session(*, event, snapshots, market):
    """A session for `GET /api/events/{id}/history` over one seeded specimen.

    Ordering matters: `odds_snapshots` is tested before `events` because the
    odds query's recursive bookmaker walk names both tables (LAT-P107/#1605),
    and `win_prob_snapshots` before `events` for the same reason its own query
    does not name `events` but the fold lookup does.
    """
    session = AsyncMock()

    def result_for(rows, scalar_one=None):
        result = MagicMock()
        result.scalars.return_value.all.return_value = rows
        result.scalars.return_value.unique.return_value.all.return_value = rows
        result.scalars.return_value.first.return_value = rows[0] if rows else None
        result.scalar_one_or_none.return_value = scalar_one
        result.scalar.return_value = None
        result.fetchall.return_value = []
        result.all.return_value = []
        result.first.return_value = None
        return result

    async def execute(stmt, *args, **kwargs):
        sql = str(stmt).lower()
        if "win_prob_snapshots" in sql:
            return result_for(snapshots)
        if "odds_snapshots" in sql:
            return result_for([])
        if "futures_markets" in sql:
            return result_for([market])
        if "events" in sql:
            return result_for([event], scalar_one=event)
        return result_for([])

    session.execute = AsyncMock(side_effect=execute)
    return session


def _snapshot(market_id, prob, minutes_ago):
    snap = MagicMock()
    snap.source = "kalshi"
    snap.event_id = 15298125
    snap.captured_at = datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)
    snap.home_win_probability = prob
    snap.away_win_probability = round(1 - prob, 4)
    snap.draw_probability = None
    snap.game_state = {"market_id": market_id, "yes_probability": prob}
    return snap


async def _served_history(*, market_status, graded):
    """The Sevilla shape: kick-off two hours out, one Kalshi series, one market.

    The control differs from the specimen in exactly the thing under test — the
    market's settledness — so an empty series proves the gate fired and not that
    the fixture never produced a chart.
    """
    from app.main import app

    event = _make_event(
        id=15298125,
        home_team="Sevilla",
        away_team="Valencia",
        status="scheduled",
        sport_key="soccer_spain_la_liga",
        home_score=None,
        away_score=None,
    )
    # Offset from the clock, never a literal date (gotcha #44).
    event.commence_time = datetime.now(timezone.utc) + timedelta(hours=2)
    event.completed_at = None

    market = _market(status=market_status, graded=graded)
    market.event_id = event.id

    snapshots = [
        _snapshot(SETTLED_MARKET_ID, 0.32, minutes_ago=90),
        _snapshot(SETTLED_MARKET_ID, 0.99, minutes_ago=60),
    ]
    session = _history_session(event=event, snapshots=snapshots, market=market)

    async def _mock_get_db():
        yield session

    async def _mock_get_optional_user():
        return None

    app.dependency_overrides[get_db] = _mock_get_db
    app.dependency_overrides[get_db_rw] = _mock_get_db
    app.dependency_overrides[get_optional_user] = _mock_get_optional_user
    try:
        with patch("app.main.init_db", new_callable=AsyncMock):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as ac:
                resp = await ac.get("/api/events/15298125/history?hours=48")
        assert resp.status_code == 200, resp.text
        return resp.json()
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_the_route_withholds_the_settled_markets_series_before_kickoff():
    payload = await _served_history(market_status="resolved", graded=True)
    assert payload.get("win_prob_history", {}).get("kalshi") in (None, []), (
        "the chart is still drawn from a market our own row says is settled, on "
        "a fixture that has not kicked off — the 99% cliff is back: "
        f"{payload.get('win_prob_history')}"
    )
    assert "kalshi" not in (payload.get("win_prob_sources") or {}), (
        "the legend still names Kalshi over a line it no longer plots"
    )


@pytest.mark.asyncio
async def test_the_route_still_draws_an_open_markets_series_before_kickoff():
    payload = await _served_history(market_status="open", graded=False)
    series = (payload.get("win_prob_history") or {}).get("kalshi") or []
    assert len(series) == 2, (
        "the gate reached an ordinary open pre-kickoff market — 643 of the 665 "
        f"market references on unstarted events look like this one: {series}"
    )
    assert (payload.get("win_prob_sources") or {}).get("kalshi", {}).get(
        "snapshot_count"
    ) == 2
