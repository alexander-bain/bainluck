"""#1588 — a window-bounded prop must not quote a live price AFTER the final.

## The sighting

Fable reported a **"2nd Quarter 99%"** answer card rendering live-looking after
the game had finished. The suppression shipped for #1588 (`0d569053`) could not
catch it: `prop_window_closed` ran only while `event.status == "live"`, on the
reasoning that *"a settled game's props should show a graded result, and
suppressing them would hide the WHAT HIT surface"*.

## The premise of that carve-out was false for part of the population

Measured on production 2026-09-10, over window-bounded props attached to
finished games:

    fm.status = 'resolved'  ->  19,498    (WHAT HIT — genuinely graded)
    fm.status = 'open'      ->     367    (still quoting, never graded)

`GET /api/events/15308050/game-markets` — Rays at Braves, full time 01:49Z, read
at 08:5xZ, **seven hours after the final** — served:

    'Tampa Bay vs Atlanta: First 5 Spread'
        outcome  'Tampa Bay -1.5 first 5 innings'
        probability 0.99   is_winner None   resolution_source None

A first-five-innings market quoting 99% on a game that is over, with no grade
behind it. The carve-out was not protecting a graded card; it was protecting an
ungraded one.

## Two defects, and this file pins both

1. **The status gate.** Nothing was suppressed once the game finished. The fix
   passes the caller's hardened `_event_is_really_finished` verdict, which also
   refuses a row whose `commence_time` is still in the future (gotcha #32 / #46)
   — so a corrupt future-dated "completed" row is not settled by this path.
2. **`spreads` was never filtered at all.** The original wiring listed
   `game_totals`, `player_props`, `team_total_items`, `period_markets` and
   `other_markets`. `spreads` was not among them, and "First 5 Spread" lands
   there — so that bucket leaked in *every* game state, live included.

WHAT HIT is preserved by the test the payload already trusts: a row carrying an
authoritative `resolution_source` survives regardless of the window verdict.
`is_winner` alone cannot be used for that — it is a Boolean defaulting to False,
so ungraded rows read as "lost" (`_settled_grade_fields` measured 6,032 such
rows), and keying on it would hand the price straight back to the rows this rule
exists to suppress.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.dependencies.auth import get_optional_user
from app.services.database import get_db, get_db_rw
from tests.integration.test_route_events_seeded import (
    _make_event,
    _make_event_detail_session,
    _make_futures_market,
    _make_outcome,
)

EVENT_ID = 15308050

# The ungraded window market that produced the 0.99 — the thing to suppress.
LEAKED = "Tampa Bay -1.5 first 5 innings"
# A window market that IS graded — the WHAT HIT surface, which must survive.
GRADED = "Over 4.5 runs in the first 5 innings"
# A full-game market, ungraded — not window-bounded, must always survive.
FULL_GAME = "Tampa Bay wins by over 1.5 runs"


def _rays_at_braves(status: str, period: str | None):
    """The production specimen, in the requested game state."""
    event = _make_event(
        id=EVENT_ID,
        home_team="Atlanta Braves",
        away_team="Tampa Bay Rays",
        status=status,
        sport_key="baseball_mlb",
        home_score=2,
        away_score=7,
    )
    event.llm_league = "MLB"
    event.period = period
    event.commence_time = datetime.now(timezone.utc) - timedelta(hours=10)
    event.completed_at = (
        datetime.now(timezone.utc) - timedelta(hours=7) if status == "completed" else None
    )

    leaked = _make_futures_market(
        id=901, name="Tampa Bay vs Atlanta: First 5 Spread", source="kalshi"
    )
    leaked.status = "open"  # gotcha #33 — settled at Kalshi, still 'open' here
    leaked.event_id = EVENT_ID

    graded = _make_futures_market(
        id=902, name="Tampa Bay vs Atlanta: First 5 Innings Total", source="kalshi"
    )
    graded.status = "resolved"
    graded.event_id = EVENT_ID

    full_game = _make_futures_market(
        id=903, name="Tampa Bay vs Atlanta: Spread", source="kalshi"
    )
    full_game.status = "open"
    full_game.event_id = EVENT_ID

    outcomes = [
        _make_outcome(id=9101, market_id=901, name=LEAKED, probability=0.99),
        _make_outcome(
            id=9201,
            market_id=902,
            name=GRADED,
            probability=0.97,
            is_winner=True,
            resolution_source="api_settlement",
        ),
        _make_outcome(id=9301, market_id=903, name=FULL_GAME, probability=0.99),
    ]
    return event, [leaked, graded, full_game], outcomes


async def _client_for(status: str, period: str | None):
    from app.main import app
    from app.routes.events import _game_markets_cache

    _game_markets_cache.clear()
    event, futures, outcomes = _rays_at_braves(status, period)
    mock_session = _make_event_detail_session(
        event=event, futures=futures, outcomes=outcomes
    )

    async def _mock_get_db():
        yield mock_session

    async def _mock_get_optional_user():
        return None

    app.dependency_overrides[get_db] = _mock_get_db
    app.dependency_overrides[get_db_rw] = _mock_get_db
    app.dependency_overrides[get_optional_user] = _mock_get_optional_user
    return app, _game_markets_cache


@pytest.fixture
async def finished_client():
    """Full time. `period` is None because production stores NULL there."""
    app, cache = await _client_for("completed", None)
    with patch("app.main.init_db", new_callable=AsyncMock):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            yield ac
    cache.clear()
    app.dependency_overrides.clear()


@pytest.fixture
async def live_third_inning_client():
    """The same game in the 3rd — the first five innings are NOT over yet."""
    app, cache = await _client_for("live", "Top 3")
    with patch("app.main.init_db", new_callable=AsyncMock):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            yield ac
    cache.clear()
    app.dependency_overrides.clear()


def _names(payload) -> list[str]:
    """Every outcome name the payload serves, across every bucket."""
    names = []
    for key in ("other", "spreads", "totals", "team_totals", "player_props", "period_markets"):
        for row in payload.get(key) or []:
            names.append(row.get("outcome_name") or row.get("name") or "")
    for matchup in payload.get("matchups") or []:
        for row in matchup.get("outcomes") or []:
            names.append(row.get("name") or "")
    return names


@pytest.mark.asyncio
async def test_the_ungraded_window_market_is_gone_after_the_final(finished_client):
    """The sighting. Seven hours after full time this was served at 0.99."""
    payload = (await finished_client.get(f"/api/events/{EVENT_ID}/game-markets")).json()
    names = _names(payload)
    assert LEAKED not in names, (
        "a first-five-innings market is still quoting on a game that has "
        f"FINISHED — this is the 0.99 Fable saw. Served: {names}"
    )


@pytest.mark.asyncio
async def test_the_spreads_bucket_is_reached_at_all(finished_client):
    """#2 of the two defects, pinned separately from the status gate.

    `spreads` was missing from the filter list, so a fix to the predicate alone
    would leave this bucket leaking. The leaked row IS a spread, so if a later
    edit drops `spreads` from the wiring this test fails on its own.
    """
    payload = (await finished_client.get(f"/api/events/{EVENT_ID}/game-markets")).json()
    spread_names = [r.get("outcome_name") or "" for r in (payload.get("spreads") or [])]
    assert LEAKED not in spread_names, (
        f"the spreads bucket is unfiltered — served: {spread_names}"
    )


@pytest.mark.asyncio
async def test_the_graded_window_market_survives_the_final(finished_client):
    """WHAT HIT. The carve-out this rule must not break (gotcha #43).

    A graded row shows a RESULT, not a live probability, and it is the whole
    reason the original carve-out existed. It has to still be there.
    """
    payload = (await finished_client.get(f"/api/events/{EVENT_ID}/game-markets")).json()
    names = _names(payload)
    assert GRADED in names, (
        "the graded first-5 market was suppressed along with the ungraded one — "
        f"that hides the WHAT HIT surface. Served: {names}"
    )


@pytest.mark.asyncio
async def test_a_full_game_market_survives_the_final(finished_client):
    """Finishing a game closes WINDOWS; it does not empty the board."""
    payload = (await finished_client.get(f"/api/events/{EVENT_ID}/game-markets")).json()
    names = _names(payload)
    assert FULL_GAME in names, f"a full-game market was suppressed. Served: {names}"


@pytest.mark.asyncio
async def test_the_same_market_still_quotes_in_the_third_inning(
    live_third_inning_client,
):
    """The other direction, asserted as hard as the first (gotcha #43).

    Without this, 'suppress everything named First 5' passes every test above
    while destroying the live market — the new-regression direction the module
    promises never to take.
    """
    payload = (await live_third_inning_client.get(f"/api/events/{EVENT_ID}/game-markets")).json()
    names = _names(payload)
    assert LEAKED in names, (
        "the first five innings are still being played and the market must "
        f"quote. Served: {names}"
    )
