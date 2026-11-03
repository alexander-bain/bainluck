"""Election night: a Kalshi grade on any Midterms market is on the NEXT read.

The collection page re-reads ``GET /api/containers/midterms-2026`` every 30 s
while any card is unsettled (``collectionRefreshInterval``). For "the card shows
the official result within one refresh" to hold, the read that follows a grade
must already carry it. This drives the real chain, with only the database
replaced by transient ORM rows:

  FuturesOutcome.is_winner / resolution_source='api_settlement' (as the 2 h REST
  poll or the per-leg socket grader writes it)
  -> ``load_midterms_cards`` (real, with the real ``_format_futures_for_search``)
  -> ``present_midterms_sections`` / ``blend_card`` / ``_official_result``
  -> the route over HTTP: two consecutive reads, the grade landing between them.

Each of the 14 Kalshi markets is graded on its LOWEST-priced leg (an upset), so a
passing card cannot be inferring the result from a price, and its Polymarket twin
(where one exists) is still open and trading.

The second read is served by the same process right after the first: if the
Midterms read were ever routed through a revision-keyed body cache (a grade does
not move the membership revision), the second read would replay the first and
this fails. An HTTP Cache-Control that lets a client or CDN hold the body longer
than one 30 s refresh fails it too.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.models import FuturesMarket, FuturesOutcome
from app.utils.midterms_collection import MANIFEST, MIDTERMS_TWIN_REGISTER

REFRESH_SECONDS = 30

KALSHI_OUTCOMES = {
    108620: [("Democratic Party", 0.36), ("Republican Party", 0.64)],
    108621: [("Democratic Party", 0.81), ("Republican Party", 0.19)],
    108619: [
        ("Democrats sweep", 0.74),
        ("D-House, R-Senate", 0.22),
        ("Republicans sweep", 0.03),
        ("R-House, D-Senate", 0.01),
    ],
    109085: [("Adam Hamilton", 0.14), ("Roger Marshall", 0.86)],
    109088: [("Josh Turek", 0.37), ("Ashley Hinson", 0.63)],
    109082: [("Troy Jackson", 0.44), ("Susan Collins", 0.56)],
    109095: [("Democratic party", 0.48), ("Republican party", 0.52)],
    109065: [("James Talarico", 0.36), ("Ken Paxton", 0.64)],
    109072: [("Sherrod Brown", 0.52), ("Jon Husted", 0.48)],
    109068: [("Darline Graham", 0.84), ("Annie Andrews", 0.16)],
    109081: [("Abdul El-Sayed", 0.60), ("Mike Rogers", 0.40)],
    108645: [("Keisha Lance Bottoms", 0.44), ("Rick Jackson", 0.56)],
    109918: [("Yes", 0.24), ("No", 0.76)],
    108629: [("Georgia", 0.28), ("Nevada", 0.14)],
}
POLYMARKET_OUTCOMES = {
    112902: [("Democratic Party", 0.40), ("Republican Party", 0.60), ("Other", None)],
    112903: [("Democratic Party", 0.85), ("Republican Party", 0.15), ("Other", None)],
    112905: [
        ("Democrats Sweep", 0.72),
        ("R Senate, D House", 0.20),
        ("Republicans Sweep", 0.05),
        ("D Senate, R House", 0.01),
        ("Other", 0.0005),
    ],
    113093: [("Adam Hamilton (D)", 0.18), ("Roger Marshall (R)", 0.82)],
    113092: [("Josh Turek (D)", 0.41), ("Ashley Hinson (R)", 0.59)],
    113095: [("Troy Jackson (D)", 0.48), ("Susan Collins (R)", 0.52)],
    113109: [("James Talarico (D)", 0.40), ("Ken Paxton (R)", 0.60)],
    113116: [("Sherrod Brown (D)", 0.56), ("Jon Husted (R)", 0.44)],
    113106: [("Darline Graham Nordone (R)", 0.88), ("Annie Andrews (D)", 0.12)],
    113097: [("Abdul El-Sayed (D)", 0.64), ("Mike Rogers (R)", 0.36)],
    113056: [("Keisha Lance Bottoms", 0.48), ("Rick Jackson", 0.52), ("Other", None)],
}
KALSHI_IDS = [e.kalshi_market_id for e in MIDTERMS_TWIN_REGISTER]
TWIN_OF = {e.kalshi_market_id: e.polymarket_market_id for e in MIDTERMS_TWIN_REGISTER}

#: How a grade lands, as the two Kalshi writers leave the rows:
#: * ``socket_leg`` — ``ws_open_contracts.grade_open_contract_leg``: ONE leg is
#:   graded (with its settled price); siblings untouched; the market is not yet
#:   ``resolved`` and has no ``settled_at``.
#: * ``socket_leg_price_refused`` — the same, with the graded leg's price in the
#:   #6993 refusal set, so the graded leg reaches the card with no price at all
#:   (the official result must not depend on a surviving price).
#: * ``rest_poll`` — ``tasks/kalshi.py`` ``_poll_kalshi_markets``: every leg
#:   graded through ``graded_columns``; market ``resolved`` with ``settled_at``.
SHAPES = ("socket_leg", "socket_leg_price_refused", "rest_poll")


def _market(mid, name, source, outcomes, *, winner=None, shape=None):
    market = FuturesMarket(
        id=mid, name=name, source=source, status="open", market_tier=2,
        category="politics", settled_at=None,
    )
    rows = []
    for index, (outcome_name, probability) in enumerate(outcomes):
        row = FuturesOutcome(
            id=mid * 100 + index, market_id=mid, name=outcome_name,
            external_id=f"{source}-{mid}-{index}", current_probability=probability,
            last_updated=datetime(2026, 11, 4, 2, 0, tzinfo=timezone.utc),
        )
        if winner is not None:
            if outcome_name == winner:
                row.is_winner, row.resolution_source = True, "api_settlement"
                row.current_probability = 1.0
            elif shape == "rest_poll":
                row.is_winner, row.resolution_source = False, "api_settlement"
                row.current_probability = 0.0
        rows.append(row)
    market.outcomes = rows
    if winner is not None and shape == "rest_poll":
        market.status = "resolved"
        market.settled_at = datetime(2026, 11, 4, 3, 12, tzinfo=timezone.utc)
    return market


def _upset(mid):
    return min(KALSHI_OUTCOMES[mid], key=lambda o: o[1])[0]


def _database(graded_mid=None, shape=None):
    names = {e.kalshi_market_id: e.kalshi_name for e in MIDTERMS_TWIN_REGISTER}
    primary = [
        _market(
            mid, names[mid], "kalshi", KALSHI_OUTCOMES[mid],
            winner=_upset(mid) if mid == graded_mid else None, shape=shape,
        )
        for mid in KALSHI_IDS
    ]
    primary.append(
        _market(112905, "Balance of Power: 2026 Midterms", "polymarket",
                POLYMARKET_OUTCOMES[112905])
    )
    twins = [
        _market(e.polymarket_market_id, e.polymarket_name, "polymarket",
                POLYMARKET_OUTCOMES[e.polymarket_market_id])
        for e in MIDTERMS_TWIN_REGISTER
        if e.polymarket_market_id is not None and e.polymarket_market_id != 112905
    ]

    class Result:
        def __init__(self, rows):
            self.rows = rows

        def scalars(self):
            return self

        def all(self):
            return self.rows

    class Database:
        """The loader's two reads, in its order: the members, then their twins."""

        def __init__(self):
            self.reads = iter((primary, twins))

        async def execute(self, statement):
            return Result(next(self.reads))

    refused = {}
    if shape == "socket_leg_price_refused":
        market = next(m for m in primary if m.id == graded_mid)
        refused = {graded_mid: {o.id for o in market.outcomes if o.is_winner}}
    return Database(), refused


def _cache_window_seconds(header: str | None) -> float:
    """How long a client/CDN may reuse the body; 0 when it may not."""
    if not header:
        return 0  # no freshness lifetime is given; fetch() runs with no-store
    value = header.lower()
    if "no-store" in value or "no-cache" in value:
        return 0
    ages = [int(n) for n in re.findall(r"(?:s-)?max-age=(\d+)", value)]
    stale = [int(n) for n in re.findall(r"stale-while-revalidate=(\d+)", value)]
    return max(ages, default=float("inf")) + max(stale, default=0)


@pytest.fixture
def served(monkeypatch):
    from app.routes import containers, futures
    from app.services import get_db
    from app.utils.container_corrections import PublishedRead

    monkeypatch.setenv("CONTAINERS_READ_ENABLED", "true")
    monkeypatch.setenv("COLLECTIONS_ENABLED", "true")
    monkeypatch.setenv("CONTAINER_COLLECTIONS_ENABLED", "true")
    members = [
        {"id": mid, "type": "market", "class": s["key"], "source": "human"}
        for s in MANIFEST["sections"]
        for mid in s["market_ids"]
    ]

    async def published(db, slug):
        # The grade does not move the revision: membership is unchanged.
        return PublishedRead(state="published", slug=slug, container_id=901,
                             revision=7, members=members)

    state = {"graded_mid": None, "shape": None, "refused": {}}

    async def refused_prices(db, markets):
        return state["refused"]

    def session():
        db, state["refused"] = _database(state["graded_mid"], state["shape"])
        return db

    monkeypatch.setattr(containers, "read_published", published)
    monkeypatch.setattr(futures, "withheld_price_outcome_ids_for_markets", refused_prices)
    app = FastAPI()
    app.include_router(containers.router, prefix="/api/containers")
    app.dependency_overrides[get_db] = session
    containers._reset_read_cache_for_tests()
    with TestClient(app) as client:
        def read():
            response = client.get("/api/containers/midterms-2026")
            assert response.status_code == 200
            assert _cache_window_seconds(response.headers.get("cache-control")) <= REFRESH_SECONDS
            body = response.json()
            return body, {m["id"]: m["card"] for s in body["sections"] for m in s["members"]}

        yield state, read
    containers._reset_read_cache_for_tests()


@pytest.mark.parametrize("shape", SHAPES)
@pytest.mark.parametrize("graded_mid", KALSHI_IDS)
def test_a_kalshi_grade_is_on_the_very_next_read_of_the_collection(served, graded_mid, shape):
    state, read = served
    winner = _upset(graded_mid)

    # Read 1: the evening, nothing graded — the card is a live blended price.
    before_body, before = read()
    assert before_body["member_count"] == 14
    assert before[graded_mid].get("settled_winner") is None
    assert before[graded_mid]["status"] != "resolved"
    assert any(isinstance(o["probability"], float) for o in before[graded_mid]["top_outcomes"])

    # Kalshi grades the market; the twin on Polymarket is still trading.
    state.update(graded_mid=graded_mid, shape=shape)
    body, cards = read()

    card = cards[graded_mid]
    assert card["settled_winner"] == winner
    assert card["status"] == "resolved"
    assert [o["name"] for o in card["top_outcomes"] if o["is_winner"] is True] == [winner]
    assert all(o["is_winner"] is False for o in card["top_outcomes"] if o["name"] != winner)
    assert all(o["probability"] is None for o in card["top_outcomes"])
    assert {o["resolution_source"] for o in card["top_outcomes"]} == {"api_settlement"}
    if TWIN_OF[graded_mid] is not None:
        # The open twin still contributes; the official result overrides its price.
        assert card["sources"] == ["kalshi", "polymarket"]

    # Nothing else on the page settles with it.
    for mid, other in cards.items():
        if mid == graded_mid:
            continue
        assert other.get("settled_winner") is None, mid
        assert other["status"] != "resolved", mid

    # The Discover / Politics pin (same read, same 30 s clock) says it too.
    chamber = {108620: "Senate", 108621: "House"}.get(graded_mid)
    if chamber:
        assert f"{chamber} Settled - {winner}" in body["discover_pin"]["subtitle"]
