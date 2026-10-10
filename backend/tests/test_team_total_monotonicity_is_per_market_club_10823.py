"""#10823 — every team-scoring line on a game page was served the same price.

## What a reader saw

`GET /api/events/14782161/game-markets` (Raiders at Patriots, 2026-10-10 04:08Z):
64 `team_totals` rows carried only 13 distinct `over_probability` values. Patriots
first-half over 6.5, Patriots full-game over 10.5 and Kalshi's
"LV Raiders over 7.5 points" were ALL served 0.825 — and the Raiders row was
tagged `team_name: "New England Patriots"`, `team_side: "home"`.

## Why

Two defects that compound:

* Team attribution read only the MARKET name, home club first. Kalshi lists both
  clubs' ladders in one market ("LV Raiders vs NE Patriots: Team Total"), so every
  Raiders outcome in it was tagged as the home Patriots.
* Step 7c grouped team totals by `team_side` alone, so one "ladder" held a club's
  first-half and full-game markets from both venues plus the other club's
  mis-tagged rungs, and `_enforce_monotonicity` capped them all to the first
  rung's price.

## The rule these tests pin

A row is attributed to the club its OUTCOME names before the club its market
names, and a text naming both clubs attributes neither. A cap never crosses a
market, never crosses clubs inside a two-club market, and only applies to rows
that are rungs of one ladder (`_is_threshold_ladder`, the 7d rule from #5374).
A real single-market, single-club ladder is still capped.
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

EVENT_ID = 14782161
HOME = "New England Patriots"
AWAY = "Las Vegas Raiders"

PM_NE_1H = 64470760  # polymarket "Patriots 1H Team Total: O/U 6.5"
PM_NE_FG = 64470758  # polymarket "Patriots Team Total: O/U 10.5"
K_TWO_CLUB = 64375972  # kalshi, both clubs' ladders in one market

MARKET_NAMES = {
    PM_NE_1H: ("Patriots 1H Team Total: O/U 6.5", "polymarket"),
    PM_NE_FG: ("Patriots Team Total: O/U 10.5", "polymarket"),
    K_TWO_CLUB: ("LV Raiders vs NE Patriots: Team Total", "kalshi"),
}

# (market_id, outcome_name, stored price). Three DISTINCT prices across the
# 1H line, the full-game line and the other club's outcome — ordered so that the
# old one-ladder-per-side cascade (sorted by threshold: 6.5, 7.5, 10.5) flattens
# all three to the cheapest, 0.62.
SPECIMEN = [
    (PM_NE_1H, "Over", 0.62),
    (PM_NE_1H, "Under", 0.38),
    (K_TWO_CLUB, "LV Raiders over 7.5 points", 0.74),
    (PM_NE_FG, "Over", 0.83),
    (PM_NE_FG, "Under", 0.17),
]


def _raiders_at_patriots(rows):
    event = _make_event(
        id=EVENT_ID,
        home_team=HOME,
        away_team=AWAY,
        status="scheduled",
        sport_key="americanfootball_nfl",
        home_score=None,
        away_score=None,
    )
    event.llm_league = "NFL"
    event.commence_time = datetime.now(timezone.utc) + timedelta(hours=3)
    event.completed_at = None
    event.box_score_data = {"players": {}}

    futures = []
    for mid in sorted({mid for mid, _n, _p in rows}):
        name, source = MARKET_NAMES[mid]
        market = _make_futures_market(id=mid, name=name, source=source)
        market.status = "open"
        market.event_id = EVENT_ID
        futures.append(market)

    outcomes = []
    for i, (mid, name, prob) in enumerate(rows):
        outcome = _make_outcome(
            id=91000 + i, market_id=mid, name=name, probability=prob or 0.0
        )
        outcome.current_probability = prob
        outcomes.append(outcome)
    return event, futures, outcomes


async def _team_totals(rows=SPECIMEN) -> list[dict]:
    from app.main import app
    from app.routes.events import _game_markets_cache

    _game_markets_cache.clear()
    event, futures, outcomes = _raiders_at_patriots(rows)
    session = _make_event_detail_session(event=event, futures=futures, outcomes=outcomes)

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
                resp = await ac.get(f"/api/events/{EVENT_ID}/game-markets")
    finally:
        _game_markets_cache.clear()
        app.dependency_overrides.clear()
    assert resp.status_code == 200, resp.text
    return resp.json().get("team_totals") or []


def _by_key(rows) -> dict:
    return {(r["_market_id"], r["outcome_name"]): r for r in rows}


def test_the_specimen_really_is_one_the_side_cascade_flattens():
    """In threshold order the prices RISE, so a one-ladder-per-side cap would move
    them — without that, the tests below could not fail on the old code."""
    order = [0.62, 0.74, 0.83]  # 1H 6.5, Raiders 7.5, full-game 10.5
    assert len(set(order)) == 3
    assert all(b > a for a, b in zip(order, order[1:]))


@pytest.mark.asyncio
async def test_first_half_full_game_and_opponent_rows_keep_their_own_prices():
    """The whole defect: three questions, three prices — never one shared 0.62."""
    served = _by_key(await _team_totals())

    assert served[(PM_NE_1H, "Over")]["over_probability"] == pytest.approx(0.62, abs=0.005)
    assert served[(PM_NE_FG, "Over")]["over_probability"] == pytest.approx(0.83, abs=0.005)
    assert served[(K_TWO_CLUB, "LV Raiders over 7.5 points")]["over_probability"] == (
        pytest.approx(0.74, abs=0.005)
    )


@pytest.mark.asyncio
async def test_a_two_club_kalshi_outcome_is_tagged_with_the_club_it_names():
    served = _by_key(await _team_totals())

    raiders = served[(K_TWO_CLUB, "LV Raiders over 7.5 points")]
    assert raiders["team_side"] == "away"
    assert raiders["team_name"] == AWAY
    # A single-club market still attributes off its own name.
    assert served[(PM_NE_FG, "Over")]["team_side"] == "home"
    assert served[(PM_NE_FG, "Over")]["team_name"] == HOME


# ── What must NOT change ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_one_clubs_ladder_inside_one_market_is_still_capped():
    """Negative control: the smoother still smooths where its premise holds. A
    harder Patriots rung priced above an easier one in the SAME market is pulled
    down — and the Raiders rung sharing that market is not touched by it."""
    rows = [
        (K_TWO_CLUB, "NE Patriots over 14.5 points", 0.55),
        (K_TWO_CLUB, "NE Patriots over 21.5 points", 0.65),  # harder, yet dearer
        (K_TWO_CLUB, "LV Raiders over 17.5 points", 0.40),
        (K_TWO_CLUB, "LV Raiders over 24.5 points", 0.30),
    ]
    served = _by_key(await _team_totals(rows))

    assert served[(K_TWO_CLUB, "NE Patriots over 21.5 points")]["over_probability"] == (
        pytest.approx(0.55)
    )
    assert served[(K_TWO_CLUB, "LV Raiders over 17.5 points")]["over_probability"] == (
        pytest.approx(0.40)
    )
    assert served[(K_TWO_CLUB, "LV Raiders over 24.5 points")]["over_probability"] == (
        pytest.approx(0.30)
    )


@pytest.mark.asyncio
async def test_rows_of_a_two_club_market_naming_neither_club_are_not_capped_or_guessed():
    """Refusal control: with no club on the outcome and both on the market, a row
    is attributed to nobody, and the repeated rung is not treated as a ladder."""
    rows = [
        (K_TWO_CLUB, "Over 10.5 points", 0.45),
        (K_TWO_CLUB, "Over 17.5 points", 0.70),
        (K_TWO_CLUB, "Over 10.5 points ", 0.80),
    ]
    served = await _team_totals(rows)

    assert served, "the untagged rows must still be served"
    assert all(r.get("team_side") is None for r in served)
    assert sorted(round(r["over_probability"], 3) for r in served) == [0.45, 0.70, 0.80]


@pytest.mark.asyncio
async def test_a_priceless_team_total_row_is_still_dropped():
    """The `> 0` filter lived inside `_enforce_monotonicity`; rows no longer capped
    still pass through it one at a time."""
    rows = [
        (PM_NE_FG, "Over", 0.83),
        (PM_NE_FG, "Under", None),
    ]
    served = _by_key(await _team_totals(rows))

    assert (PM_NE_FG, "Under") not in served, "a priceless row reached the payload"
    assert served[(PM_NE_FG, "Over")]["over_probability"] == pytest.approx(0.83, abs=0.005)
