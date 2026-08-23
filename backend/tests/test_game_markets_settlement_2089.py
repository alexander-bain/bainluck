"""#2089 — the settled grade exists, is authoritative, and the endpoint drops it.

## What this file pins

`/api/events/{id}/game-markets` emits `other` / `spreads` / `totals` / `matchups`
rows as `{market_name, outcome_name, probability, source}` and nothing else, so a
settled game page cannot say who won even though every market on it is graded in
the database. The specimen, verified against production 2026-08-21 (event
`15177664`, Wawrinka vs Burruchaga — Burruchaga won 2-1): 13 outcomes, every one
`status='resolved'` with `resolution_source='api_settlement'` and a real
`is_winner`. The page could say so; the serializer throws it away.

## 🔴 THE GATE IS `resolved` **AND** `resolution_source`, AND THE ISSUE'S OWN SNIPPET WAS WRONG

#2089 suggests `fo.is_winner if fm.status == "resolved" else None`, reasoning from
a measurement that split by market status only:

    markets status='resolved' -> 5,869 outcomes, 1,383 true / 4,486 false / 0 null

Splitting the SAME population by `resolution_source` as well (LAT-P080A, production
2026-08-21, newest 400 event-linked `status='resolved'` markets) shows that number
is two populations wearing one label:

    resolution_source IS NULL  ->  6,032 outcomes, 0 true / 6,032 false
    resolution_source present  ->  1,403 outcomes, 468 true /   935 false

**Zero winners in 6,032 outcomes is not a grade — it is the ungraded default.**
`is_winner` is a non-nullable Boolean defaulting to False (gotcha #33), so market
status alone cannot distinguish "this side lost" from "nobody graded this". Gating
on status only would have emitted 6,032 false verdicts — reproducing, one layer up,
the exact defect #2089 was filed to remove.

This is not a new rule. `_grade_settled_prop`'s consumer at `events.py:6589` already
gates on `resolution_source` for player props, and the comment there records the
production incident that taught it: WNBA props with `resolution_source=None` all
rendered a confident "miss".

The costs are asymmetric and that is what decides it. Over-gating shows no verdict
where one might exist — today's behaviour exactly, so no regression. Under-gating
tells a user their side lost when nobody ever graded it. A refusal is recoverable;
a false statement is not.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.dependencies.auth import get_optional_user
from app.routes.events import _settled_grade_fields
from app.services.database import get_db, get_db_rw
from tests.integration.test_route_events_seeded import (
    _make_event,
    _make_event_detail_session,
    _make_futures_market,
    _make_outcome,
)


def _mkt(status):
    market = MagicMock()
    market.status = status
    return market


def _out(is_winner, resolution_source):
    outcome = MagicMock()
    outcome.is_winner = is_winner
    outcome.resolution_source = resolution_source
    return outcome


# ── The rule, off its defaults ──────────────────────────────────────────────


def test_a_resolved_and_sourced_winner_is_served_as_a_verdict():
    fields = _settled_grade_fields(_mkt("resolved"), _out(True, "api_settlement"))
    assert fields["is_winner"] is True
    assert fields["resolution_source"] == "api_settlement"


def test_a_resolved_and_sourced_loser_is_served_as_a_verdict():
    """The false side of a GRADED market is a real verdict and must survive.

    The gate exists to suppress the ungraded default, not every false — a market
    with a winner necessarily has losers, and hiding them would leave the page
    unable to say anybody lost.
    """
    fields = _settled_grade_fields(_mkt("resolved"), _out(False, "api_settlement"))
    assert fields["is_winner"] is False
    assert fields["resolution_source"] == "api_settlement"


def test_the_ungraded_default_on_a_resolved_market_is_NOT_a_verdict():
    """6,032 of these in the newest 400 resolved markets, all false, zero true."""
    fields = _settled_grade_fields(_mkt("resolved"), _out(False, None))
    assert fields["is_winner"] is None, (
        "is_winner=False with no resolution_source is the non-nullable column's "
        "default (gotcha #33), not a grade — serving it renders 'lost'"
    )
    assert fields["resolution_source"] is None


def test_an_open_market_carries_no_verdict_even_when_is_winner_is_false():
    """#2089's acceptance criterion, and gotcha #33's own shape.

    1,761 outcomes sit on `status='open'` markets that Kalshi has already settled,
    every one `is_winner=false`, because polling stops seeing a market once it
    settles so the DB status never advances.
    """
    fields = _settled_grade_fields(_mkt("open"), _out(False, None))
    assert fields["is_winner"] is None
    assert fields["resolution_source"] is None


def test_an_open_market_carries_no_verdict_even_when_sourced_and_true():
    """Both halves of the gate are load-bearing, asserted independently.

    Without this, a single-condition implementation keyed on resolution_source
    alone passes every other test in this file.
    """
    fields = _settled_grade_fields(_mkt("open"), _out(True, "api_settlement"))
    assert fields["is_winner"] is None


def test_a_missing_status_is_not_read_as_resolved():
    fields = _settled_grade_fields(_mkt(None), _out(True, "api_settlement"))
    assert fields["is_winner"] is None


def test_the_keys_are_always_present_so_the_shape_never_varies():
    """Additive and STABLE — a sometimes-missing key is a second shape to handle.

    `None` and absent mean the same thing to a client only if the client
    remembers; a key that is always there makes 'no verdict' explicit.
    """
    for market, outcome in (
        (_mkt("resolved"), _out(True, "api_settlement")),
        (_mkt("open"), _out(False, None)),
        (_mkt(None), _out(None, None)),
    ):
        assert set(_settled_grade_fields(market, outcome)) == {
            "is_winner",
            "resolution_source",
        }


# ── The route actually serves it (a correct helper nobody calls changes nothing) ──


@pytest.fixture
async def burruchaga_client():
    """The production specimen: event 15177664, all markets api_settlement-graded.

    Three buckets in one fixture on purpose — `other`, `spreads` and `matchups`
    are separate serializers and #2089's acceptance names all four of the
    specimen's markets, which land across them.
    """
    from app.main import app
    from app.routes.events import _game_markets_cache

    _game_markets_cache.clear()

    event = _make_event(
        id=15177664,
        home_team="Stan Wawrinka",
        away_team="Roman Andres Burruchaga",
        status="completed",
    )

    exact = _make_futures_market(
        id=901,
        name="Stan Wawrinka vs Roman Andres Burruchaga: Exact Match Score",
        source="kalshi",
    )
    exact.status = "resolved"
    exact.event_id = event.id

    spread = _make_futures_market(
        id=902,
        name="Stan Wawrinka vs Roman Andres Burruchaga: Game Spread",
        source="kalshi",
    )
    spread.status = "resolved"
    spread.event_id = event.id

    # Deliberately the SAME serializer bucket as the graded rows above ("other"),
    # so the graded and ungraded cases differ only in the thing under test. An
    # earlier draft used a "Total Games" market, which the totals classifier
    # dropped entirely — the row was then absent rather than unverdicted, which
    # proves nothing about the gate.
    ungraded = _make_futures_market(
        id=903,
        name="Stan Wawrinka vs Roman Andres Burruchaga: Exact Match Score (alt)",
        source="kalshi",
    )
    ungraded.status = "open"  # gotcha #33 — settled upstream, still 'open' here
    ungraded.event_id = event.id

    outcomes = [
        _make_outcome(
            id=9101,
            market_id=901,
            name="Roman Andres Burruchaga wins 2-1",
            probability=0.99,
            is_winner=True,
            resolution_source="api_settlement",
        ),
        _make_outcome(
            id=9102,
            market_id=901,
            name="Stan Wawrinka wins 2-0",
            probability=0.01,
            is_winner=False,
            resolution_source="api_settlement",
        ),
        _make_outcome(
            id=9201,
            market_id=902,
            name="Stan Wawrinka -1.5 games",
            probability=0.05,
            is_winner=False,
            resolution_source="api_settlement",
        ),
        _make_outcome(
            id=9301,
            market_id=903,
            name="Roman Andres Burruchaga wins 3-0",
            probability=0.5,
            is_winner=False,  # the ungraded default
            resolution_source=None,
        ),
    ]

    mock_session = _make_event_detail_session(
        event=event, futures=[exact, spread, ungraded], outcomes=outcomes
    )

    async def _mock_get_db():
        yield mock_session

    async def _mock_get_optional_user():
        return None

    app.dependency_overrides[get_db] = _mock_get_db
    app.dependency_overrides[get_db_rw] = _mock_get_db
    app.dependency_overrides[get_optional_user] = _mock_get_optional_user

    with patch("app.main.init_db", new_callable=AsyncMock):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as ac:
            yield ac

    _game_markets_cache.clear()
    app.dependency_overrides.clear()


def _all_rows(payload):
    """Every graded-shaped row the payload serves, across every bucket."""
    rows = []
    for key in ("other", "spreads", "totals", "player_props"):
        rows.extend(payload.get(key) or [])
    for matchup in payload.get("matchups") or []:
        rows.extend(matchup.get("outcomes") or [])
    return rows


@pytest.mark.asyncio
async def test_the_settled_winner_reaches_the_payload(burruchaga_client):
    payload = (await burruchaga_client.get("/api/events/15177664/game-markets")).json()
    rows = _all_rows(payload)
    winners = [
        r
        for r in rows
        if r.get("is_winner") is True
        and "Burruchaga wins 2-1" in (r.get("outcome_name") or r.get("name") or "")
    ]
    assert winners, (
        "Burruchaga won 2-1, it is api_settlement-graded in the store, and the "
        f"payload does not say so. Served rows: {rows}"
    )
    assert winners[0].get("resolution_source") == "api_settlement"


@pytest.mark.asyncio
async def test_the_graded_loser_reaches_the_payload_as_false_not_none(
    burruchaga_client,
):
    payload = (await burruchaga_client.get("/api/events/15177664/game-markets")).json()
    rows = _all_rows(payload)
    losers = [
        r
        for r in rows
        if "Wawrinka -1.5 games" in (r.get("outcome_name") or r.get("name") or "")
    ]
    assert losers, f"the graded spread row is missing entirely: {rows}"
    assert losers[0].get("is_winner") is False
    assert losers[0].get("resolution_source") == "api_settlement"


@pytest.mark.asyncio
async def test_the_ungraded_open_market_row_serves_no_verdict(burruchaga_client):
    """The other direction, asserted as hard as the first (gotcha #43)."""
    payload = (await burruchaga_client.get("/api/events/15177664/game-markets")).json()
    rows = _all_rows(payload)
    ungraded = [
        r
        for r in rows
        if "Burruchaga wins 3-0" in (r.get("outcome_name") or r.get("name") or "")
    ]
    assert ungraded, f"the ungraded row is missing entirely: {rows}"
    assert ungraded[0].get("is_winner") is None, (
        "a 'status=open' market's default-false is_winner must never reach the "
        "wire as a verdict — that renders 1,761 production outcomes as 'lost'"
    )


@pytest.mark.asyncio
async def test_no_row_ever_serves_bare_false_without_a_source(burruchaga_client):
    """The cross-lane contract, stated as an invariant the client can rely on.

    A client keying on `is_winner === false` alone is the failure mode #2089
    warns about; this asserts the server never hands it that ambiguity.
    """
    payload = (await burruchaga_client.get("/api/events/15177664/game-markets")).json()
    for row in _all_rows(payload):
        if row.get("is_winner") is not None:
            assert row.get("resolution_source"), (
                f"row states a verdict with no resolution_source backing it: {row}"
            )
