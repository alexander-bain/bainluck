"""#6751 — a settled player prop with no recognisable window left the payload in silence.

## What a reader sees

`KXNFLFFPTS` — NFL fantasy points — is the specimen. Measured on production
2026-09-17: all 16 of those markets are tier-5, `resolved`, NFL, and 14 of them
are correctly linked to their real ESPN-anchored game. **Zero of the 14 reach
either serve path.** The string "Fantasy" appears nowhere in
`/api/events/{id}/related-futures` or `/api/events/{id}/game-markets` for any of
them, while sibling prop families on the SAME events — Passing Yards, Rushing
Yards, Receiving Yards, Touchdowns — render as settled Won/Lost cards.

The link is not the cause: `/related-futures?debug=true` on 14780144 reports
`game_prop_count: 61`, so the market IS in the pass-2 set. It is dropped
downstream, and the two unattached markets #5621 relinks carry 27 graded
outcomes between them — each with `opening_probability`, a current price,
`is_winner` and `resolution_source = api_settlement`.

## The mechanism

Step 9 of `_build_game_markets` splits `player_props` two ways and has no
`else`:

    if 0.05 <= p["over_probability"] <= 0.95:   -> interesting, kept
    elif _window_is_closed(p):                  -> settled window, graded later

Every leg of a settled market has priced out to 0.0 or 1.0, so none survives the
interest band. `prop_window_closed` returns False because "Fantasy Points" names
no contest segment — a whole-game prop has no window to close. Neither branch
takes them and there is no third, so the rows simply cease to exist: no count,
no log, no empty state.

The sibling families differ in one respect only — `_classify_game_market` files
them as `team_total`, so they never pass through this filter at all.

## The rule these tests pin

A player prop that is no longer a live question, carries no window we can prove
closed, and **already has its answer in hand** is served. An ungraded extreme
price is still dropped, on a finished game exactly as on a live one — that is
the #921 behaviour this filter exists for and the one thing that must not widen.
A graded row whose window IS provably over is untouched: it keeps taking the
`elif`, and #1588's rule that its price is not republished beside its verdict
still holds.
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

EVENT_ID = 14780138  # Patriots @ Seahawks — one of #5621's two relink targets.

# The specimen: whole-game fantasy points. No contest segment in the name, so
# `prop_window` returns None and no filter can ever prove its window closed.
FFPTS_TICKER = "KXNFLFFPTS-26SEP09NESEA"
FFPTS_NAME = "New England vs Seattle: Fantasy Points"
GRADED_WINNER = "Drake Maye: Over 12.5 fantasy points"
GRADED_LOSER = "Rhamondre Stevenson: Over 14.5 fantasy points"

# CONTROL A — identical in every respect except that it is NOT graded. This is
# the #921 cohort: a dead quote on a question nobody answered for us.
UNGRADED_EXTREME = "Hunter Henry: Over 9.5 fantasy points"

# CONTROL B — a player prop that IS window-bounded ("1st half"), graded, and
# priced out. It must keep taking the existing `elif` branch, never the new one.
HALF_TICKER = "KXNFLH1FFPTS-26SEP09NESEA"
HALF_NAME = "New England vs Seattle: 1st Half Fantasy Points"
GRADED_HALF = "Drake Maye: Over 6.5 fantasy points in the 1st half"

# CONTROL C — an ordinary live-priced prop, so no test here is reading an empty
# bucket and calling it a pass.
INTERESTING = "Stefon Diggs: Over 4.5 fantasy points"


def _patriots_at_seahawks(status: str):
    event = _make_event(
        id=EVENT_ID,
        home_team="Seattle Seahawks",
        away_team="New England Patriots",
        status=status,
        sport_key="americanfootball_nfl",
        home_score=24,
        away_score=20,
    )
    event.llm_league = "NFL"
    event.period = None if status == "completed" else "Q3"
    event.commence_time = datetime.now(timezone.utc) - timedelta(hours=6)
    event.completed_at = (
        datetime.now(timezone.utc) - timedelta(hours=3) if status == "completed" else None
    )
    event.box_score_data = {
        "players": {},
        "home_period_scores": [7, 3, 7, 7],
        "away_period_scores": [0, 10, 3, 7],
    }

    ffpts = _make_futures_market(id=902, name=FFPTS_NAME, source="kalshi",
                                 sport_category="football")
    ffpts.external_id = FFPTS_TICKER
    ffpts.event_id = EVENT_ID
    ffpts.market_tier = 5
    ffpts.category = "game_prop"
    # `_settled_grade_fields` demands this before it will publish any verdict.
    ffpts.status = "resolved" if status == "completed" else "open"

    half = _make_futures_market(id=903, name=HALF_NAME, source="kalshi",
                                sport_category="football")
    half.external_id = HALF_TICKER
    half.event_id = EVENT_ID
    half.market_tier = 5
    half.category = "game_prop"
    half.status = "resolved" if status == "completed" else "open"

    graded = {"resolution_source": "api_settlement"}
    outcomes = [
        # Priced out to the two ends, exactly as a settled Kalshi leg is.
        _make_outcome(id=9201, market_id=902, name=GRADED_WINNER,
                      probability=1.0, is_winner=True, **graded),
        _make_outcome(id=9202, market_id=902, name=GRADED_LOSER,
                      probability=0.0, is_winner=False, **graded),
        _make_outcome(id=9203, market_id=902, name=UNGRADED_EXTREME,
                      probability=0.99, is_winner=None, resolution_source=None),
        _make_outcome(id=9204, market_id=902, name=INTERESTING, probability=0.55),
        _make_outcome(id=9301, market_id=903, name=GRADED_HALF,
                      probability=1.0, is_winner=True, **graded),
    ]
    return event, [ffpts, half], outcomes


async def _client(status: str):
    from app.main import app
    from app.routes.events import _game_markets_cache

    _game_markets_cache.clear()
    event, futures, outcomes = _patriots_at_seahawks(status)
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


def _served_prop_names(payload) -> set:
    return {
        row.get("outcome_name")
        for row in (payload.get("player_props") or [])
        if row.get("outcome_name")
    }


def _row(payload, outcome_name):
    for row in payload.get("player_props") or []:
        if row.get("outcome_name") == outcome_name:
            return row
    return None


@pytest.mark.asyncio
async def test_the_settled_fantasy_points_legs_reach_the_page(finished_client):
    """THE SHIP: 27 graded outcomes stop being deleted between grader and reader."""
    payload = (await finished_client.get(f"/api/events/{EVENT_ID}/game-markets")).json()
    served = _served_prop_names(payload)

    for label in (GRADED_WINNER, GRADED_LOSER):
        assert label in served, (
            f"{label!r} is graded and still absent from the payload; "
            f"served player props: {sorted(served)}"
        )


@pytest.mark.asyncio
async def test_both_sides_of_the_settled_question_survive_with_their_verdict(
    finished_client,
):
    """A winner AND a loser — the loser is the half that vanishes most quietly.

    Asserting only the winner would pass against a payload that prints a page of
    green ticks and silently drops every "did not hit", which is #6169's failure
    mode one bucket over.
    """
    payload = (await finished_client.get(f"/api/events/{EVENT_ID}/game-markets")).json()

    winner = _row(payload, GRADED_WINNER)
    loser = _row(payload, GRADED_LOSER)
    assert winner is not None and loser is not None

    assert winner.get("is_winner") is True, winner
    assert loser.get("is_winner") is False, loser
    assert winner.get("resolution_source") == "api_settlement", winner
    assert loser.get("resolution_source") == "api_settlement", loser


@pytest.mark.asyncio
async def test_an_ungraded_extreme_price_is_still_dropped(finished_client):
    """THE CONTROL THAT BOUNDS THE FIX (#921).

    This row differs from the two above in exactly one respect — nobody has
    graded it — and it must still go. If this ever starts passing, the third
    branch has stopped being "a result survives" and become "a finished game
    shows everything", which is the widening the filter exists to prevent.
    """
    payload = (await finished_client.get(f"/api/events/{EVENT_ID}/game-markets")).json()
    assert UNGRADED_EXTREME not in _served_prop_names(payload)


@pytest.mark.asyncio
async def test_a_graded_window_bounded_leg_still_takes_the_closed_window_path(
    finished_client,
):
    """#1588 / #1735 are untouched: a provably-closed window keeps its route.

    The new branch is last, so a row the `elif` already claims never reaches it.
    That matters for more than ordering: rows on the closed-window path are
    stripped of their price on the way out, and republishing "0.99" beside a
    green tick is the original bug wearing a rosette.
    """
    payload = (await finished_client.get(f"/api/events/{EVENT_ID}/game-markets")).json()

    row = _row(payload, GRADED_HALF)
    if row is not None:
        # If it is ever served as a live prop row, it must not carry the
        # leftover price that #1588 removed on purpose.
        assert row.get("over_probability") in (None, 0), row


@pytest.mark.asyncio
async def test_a_live_game_is_completely_unchanged(live_client):
    """Nothing here may reach a game still being played.

    On a live game every one of these legs is still a question, and the
    interest-band filter is still the whole rule.
    """
    payload = (await live_client.get(f"/api/events/{EVENT_ID}/game-markets")).json()
    served = _served_prop_names(payload)

    assert UNGRADED_EXTREME not in served
    assert INTERESTING in served, (
        "the live control is reading an empty bucket, so it proves nothing; "
        f"served: {sorted(served)}"
    )


@pytest.mark.asyncio
async def test_the_ordinary_interesting_prop_still_serves_on_a_finished_game(
    finished_client,
):
    """The fixture is not silently empty: the interest band still works."""
    payload = (await finished_client.get(f"/api/events/{EVENT_ID}/game-markets")).json()
    assert INTERESTING in _served_prop_names(payload)


def test_the_grade_test_is_asked_once_and_reads_both_kinds_of_grade():
    """`_grade_is_in_hand` is the one grade test, and CERT-2486 is why.

    Two call sites drifted on which fields identify a window and two provider
    shapes walked through the gap; this is the same shape one predicate over.
    The test is a source read because both readers are closures inside
    `_build_game_markets` and cannot be imported.

    It also pins the deliberate omission: `is_winner` is a Boolean defaulting to
    False, so reading it here would mark 6,032 ungraded rows "lost" and hand a
    live-looking price back to exactly the rows suppression must remove.
    """
    import inspect

    from app.routes import events as events_module

    src = inspect.getsource(events_module._build_game_markets)

    assert src.count("def _grade_is_in_hand") == 1
    # Both readers go through the helper rather than re-testing the fields.
    assert src.count("_grade_is_in_hand(") >= 3  # 1 def + 2 call sites
    body = src.split("def _grade_is_in_hand")[1].split("return")[1].split("\n")[0]
    assert "resolution_source" in body and "hit" in body, body
    assert "is_winner" not in body, body
