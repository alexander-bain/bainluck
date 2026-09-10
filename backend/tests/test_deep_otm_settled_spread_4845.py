"""#4845 — the deep-OTM floor was dropping one half of a settled question.

## What a reader sees on the finished specimen

`/events/15308050` (Braves 2 – Rays 7) grades "Tampa Bay -1.5 first 5 innings"
and "Tampa Bay -2.5 first 5 innings" — and says nothing at all about the two
legs on the other side of the same market, "Atlanta -1.5" and "Atlanta -2.5".
Both are gradable off the same line score (the first five finished 1–6, so both
are a miss), and neither exists anywhere in the payload.

## Why, and why it is not CERT-2502 again

`_SPREAD_DEEP_OTM_FLOOR` (0.02, #921) drops a deep-OTM alternate rung at
BUCKET-BUILD time so the spreads section shows meaningful lines rather than the
whole ladder. The Atlanta legs are priced 0.010.

CERT-2502 fixed the same *class* in step 9 — the 0.05–0.95 "boring" band was
eating settled player props — but that filter runs ~300 lines later and MOVES
its rows aside into `_window_closed_items`. This one `continue`s: the row
reaches no bucket, so the #1588 suppression filter never sees it, `#1735`'s
grader is never offered it, and the page cannot tell the difference between "a
rung nobody cared about" and "half of a question we have already answered".

## The rule these tests pin

A dropped rung whose window is PROVABLY over joins the same collection every
other settled window row joins, and takes the same route out: a verdict, no
price. A dropped rung whose window is not provably over is dropped exactly as
before — which is every rung on every live game, and every full-game spread on
a finished one.

Measured on production before building: 247 outcome rows across 90 finished MLB
events of the trailing week are dropped by this floor.
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

# The production line score for the specimen, verbatim.
HOME_PERIODS = [0, 0, 0, 1, 0, 1, 0, 0, 0]  # Atlanta Braves
AWAY_PERIODS = [0, 3, 0, 3, 0, 0, 1, 0, 0]  # Tampa Bay Rays
# First five innings: home 1, away 6 — Tampa Bay by five.

# Copied from production (`futures_outcomes` of market 60617963), prices and all.
FAVOURED_1 = "Tampa Bay -1.5 first 5 innings"   # 0.99 — above the floor today
FAVOURED_2 = "Tampa Bay -2.5 first 5 innings"   # 0.99
DROPPED_1 = "Atlanta -1.5 first 5 innings"      # 0.01 — below the floor
DROPPED_2 = "Atlanta -2.5 first 5 innings"      # 0.01
# A FULL-GAME rung at the same price. Its window is the whole game, so no filter
# can prove it is over ahead of the final whistle and `prop_window_closed`
# refuses it — the control that separates "settled window" from "cheap rung".
FULL_GAME_DROPPED = "Atlanta -8.5"


def _rays_at_braves(status: str):
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
    event.period = None if status == "completed" else "6th Inning"
    event.commence_time = datetime.now(timezone.utc) - timedelta(hours=10)
    event.completed_at = (
        datetime.now(timezone.utc) - timedelta(hours=7) if status == "completed" else None
    )
    event.box_score_data = {
        "players": {},
        "home_period_scores": HOME_PERIODS,
        "away_period_scores": AWAY_PERIODS,
    }

    window_spread = _make_futures_market(
        id=902, name="Tampa Bay vs Atlanta: First 5 Spread", source="kalshi"
    )
    window_spread.status = "open"
    window_spread.event_id = EVENT_ID

    full_game = _make_futures_market(
        id=903, name="Tampa Bay vs Atlanta: Spread", source="kalshi"
    )
    full_game.status = "open"
    full_game.event_id = EVENT_ID

    outcomes = [
        _make_outcome(id=9201, market_id=902, name=FAVOURED_1, probability=0.99),
        _make_outcome(id=9202, market_id=902, name=FAVOURED_2, probability=0.99),
        _make_outcome(id=9203, market_id=902, name=DROPPED_1, probability=0.01),
        _make_outcome(id=9204, market_id=902, name=DROPPED_2, probability=0.01),
        _make_outcome(id=9301, market_id=903, name=FULL_GAME_DROPPED, probability=0.01),
        # Above the floor, so the full-game market still renders a line and this
        # fixture is not silently testing an empty bucket.
        _make_outcome(id=9302, market_id=903, name="Tampa Bay -1.5", probability=0.62),
    ]
    return event, [window_spread, full_game], outcomes


async def _client(status: str):
    from app.main import app
    from app.routes.events import _game_markets_cache

    _game_markets_cache.clear()
    event, futures, outcomes = _rays_at_braves(status)
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
    app, cache = await _client("completed")
    with patch("app.main.init_db", new_callable=AsyncMock):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            yield ac
    cache.clear()


@pytest.fixture
async def live_client():
    app, cache = await _client("live")
    with patch("app.main.init_db", new_callable=AsyncMock):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            yield ac
    cache.clear()


def _script(payload) -> dict:
    return {row["label"]: row for row in payload.get("props_script") or []}


def _all_served_outcome_names(payload) -> set:
    names = set()
    for bucket in ("totals", "player_props", "team_totals", "spreads",
                   "period_markets", "matchups", "other"):
        for row in payload.get(bucket) or []:
            if row.get("outcome_name"):
                names.add(row["outcome_name"])
    return names


@pytest.mark.asyncio
async def test_the_dropped_half_of_the_question_comes_back_as_a_verdict(finished_client):
    """The ship: both sides of one settled market, or neither.

    Before this change the page graded the 0.99 legs and was silent about the
    0.01 legs of the same market — the reader could not tell that the question
    had a second side, let alone that it had been answered.
    """
    payload = (await finished_client.get(f"/api/events/{EVENT_ID}/game-markets")).json()
    script = _script(payload)

    for label in (DROPPED_1, DROPPED_2):
        assert label in script, (
            f"{label!r} is still absent from WHAT HIT; served labels: {sorted(script)}"
        )
        # Tampa Bay led the first five 1–6 from Atlanta's side, so both Atlanta
        # rungs are a miss — and the score is stated from the NAMED side first.
        assert script[label]["graded_label"] == "1–6 — miss", script[label]
        assert script[label]["graded_result"] == "miss"

    # The sibling legs that were already working still work — this is additive.
    assert script[FAVOURED_1]["graded_label"] == "6–1 — hit"
    assert script[FAVOURED_2]["graded_label"] == "6–1 — hit"


@pytest.mark.asyncio
async def test_the_recovered_rung_brings_no_price_with_it(finished_client):
    """#1735's standing constraint: these rows are a result, never a number.

    A recovered 0.01 rung republished as a price would be the #1588 bug wearing
    a rosette — and the floor exists precisely because that price is noise.
    """
    payload = (await finished_client.get(f"/api/events/{EVENT_ID}/game-markets")).json()
    script = _script(payload)

    for label in (DROPPED_1, DROPPED_2):
        assert script[label]["pregame_mark"] is None, script[label]
        assert script[label]["current"] is None, script[label]

    served = _all_served_outcome_names(payload)
    assert DROPPED_1 not in served, "the deep-OTM rung re-entered a price bucket"
    assert DROPPED_2 not in served, "the deep-OTM rung re-entered a price bucket"


@pytest.mark.asyncio
async def test_a_full_game_rung_at_the_same_price_stays_dropped(finished_client):
    """The control: "settled window", not "cheap rung", is what recovers a row.

    `Atlanta -8.5` is the same 0.01 on the same finished event. Its window is
    the whole game, so #921's floor is still the right answer for it. If this
    ever appears, the carve-out has become "publish everything the floor drops".

    HONEST ABOUT WHAT THIS PINS. It pins the READER's outcome, which is what the
    issue is about — and it does NOT pin the `_window_is_closed` call, because
    two barriers stand between this row and the page: the carve-out's test, and
    `prop_window_span` refusing a name that carries no window at all. Deleting
    the call leaves this test green (mutation run, survived, stated in the cert).
    The call stays because `_window_closed_items` is documented as holding rows
    whose window has been PROVED over, and feeding it unproven rows would make
    that invariant false for the next reader of the collection rather than for
    this one.
    """
    payload = (await finished_client.get(f"/api/events/{EVENT_ID}/game-markets")).json()

    assert FULL_GAME_DROPPED not in _script(payload)
    assert FULL_GAME_DROPPED not in _all_served_outcome_names(payload)
    # And the market it belongs to still renders its near-the-money line, so the
    # assertion above is about the rung and not about an empty bucket.
    assert "Tampa Bay -1.5" in _all_served_outcome_names(payload)


@pytest.mark.asyncio
async def test_a_live_game_keeps_the_floor_exactly_as_it_was(live_client):
    """#921 is unchanged in every state but settled.

    Mid-game the sixth inning is in progress, so the first five ARE over and the
    two Atlanta rungs are gradable — but nothing else about the ladder is, and
    the point of this test is the negative: no deep-OTM rung acquires a PRICE
    row on a live page, which is the only thing the floor was ever protecting.
    """
    payload = (await live_client.get(f"/api/events/{EVENT_ID}/game-markets")).json()
    served = _all_served_outcome_names(payload)

    assert DROPPED_1 not in served
    assert DROPPED_2 not in served
    assert FULL_GAME_DROPPED not in served
    # The above-floor rungs are the population the section is for, and they are
    # untouched.
    assert FAVOURED_1 in served or FAVOURED_1 in _script(payload)
