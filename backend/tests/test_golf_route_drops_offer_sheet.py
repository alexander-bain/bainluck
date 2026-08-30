"""Q446 — the RENDER proof: an offer-sheet field never reaches `GET /api/golf`.

A pure-predicate guard stays green when the render drops the call, so this file
drives `get_golf` itself with the two production specimens seeded side by side:

  * `Omega European Masters Winner` (kalshi 59759220) — four golfers, each at an
    identical 10%, `yes_bid 0.0000 / yes_ask 0.1000` behind every one, no trade in
    any snapshot the market has ever taken. Must NOT appear.
  * `Husqvarna British Masters` (a real DP World Tour field with real two-sided
    books) — must appear, with its numbers intact.

Both are golf, both pass `_is_golf_market`, both are in the same response. The
control is what makes the assertion mean something: a fix that emptied the golf
page would also make the first assertion pass.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.routes.golf import get_golf


def _outcome(oid, name, prob, bid, ask):
    return SimpleNamespace(
        id=oid,
        name=name,
        current_probability=prob,
        current_yes_bid=bid,
        current_yes_ask=ask,
        opening_probability=None,
        probability_change_24h=None,
    )


def _market(mid, name, source, external_id, outcomes, *, commence=None):
    return SimpleNamespace(
        id=mid,
        name=name,
        source=source,
        external_id=external_id,
        outcomes=outcomes,
        commence_time=commence,
        resolution_date=None,
        status="open",
        llm_sport_category="golf",
        market_tier=1,
        market_metadata=None,
    )


#: market 59759220, verbatim — four identical no-bid asks.
OMEGA = _market(
    59759220,
    "Omega European Masters Winner",
    "kalshi",
    "KXDPWORLDTOUR-OMEM26",
    [
        _outcome(222605753, "Andreas Halvorsen", 0.10, 0.0, 0.10),
        _outcome(222605754, "Adrian Meronk", 0.10, 0.0, 0.10),
        _outcome(222605755, "Eddie Pepperell", 0.10, 0.0, 0.10),
        _outcome(222605756, "Antoine Rozner", 0.10, 0.0, 0.10),
    ],
)

#: The control — a real field with real two-sided books and a real spread.
HUSQVARNA = _market(
    59512401,
    "Husqvarna British Masters hosted by Sir Nick Faldo Winner",
    "kalshi",
    "KXDPWORLDTOUR-HBM26",
    [
        _outcome(1, "Marco Penge", 0.184, 0.17, 0.20),
        _outcome(2, "Daniel Hillier", 0.119, 0.11, 0.13),
        _outcome(3, "Tom McKibbin", 0.042, 0.03, 0.05),
        _outcome(4, "Shaun Norris", 0.045, 0.04, 0.05),
        _outcome(5, "Jacob Skov Olesen", 0.025, 0.02, 0.03),
    ],
)


@pytest.fixture
def golf_db():
    """A db whose market query returns the two seeded fields and no snapshots."""
    markets_result = MagicMock()
    markets_result.scalars.return_value.unique.return_value.all.return_value = [
        OMEGA,
        HUSQVARNA,
    ]
    empty = MagicMock()
    empty.__iter__ = lambda self: iter(())

    session = AsyncMock()
    calls = {"n": 0}

    async def _execute(*_args, **_kwargs):
        calls["n"] += 1
        return markets_result if calls["n"] == 1 else empty

    session.execute.side_effect = _execute
    return session


@pytest.fixture(autouse=True)
def _no_schedule(monkeypatch):
    async def _empty():
        return []

    monkeypatch.setattr("app.routes.golf._get_golf_schedule", _empty)


def _by_name(body):
    return {t["name"]: t for t in body["tournaments"]}


async def test_offer_sheet_tournament_does_not_render(golf_db):
    body = await get_golf(golf_db)
    names = _by_name(body)

    assert not any("Omega" in n for n in names), (
        "Omega European Masters is an offer sheet — four identical no-bid asks — "
        f"and must not render as a forecast. Got: {sorted(names)}"
    )


async def test_the_real_field_next_to_it_still_renders(golf_db):
    """THE CONTROL. Emptying the golf page would pass the test above."""
    body = await get_golf(golf_db)
    names = _by_name(body)

    real = next((t for n, t in names.items() if "Husqvarna" in n), None)
    assert real is not None, f"the real DP World field vanished. Got: {sorted(names)}"

    golfers = {g["name"]: g["probability"] for g in real["golfers"]}
    assert "Marco Penge" in golfers
    # Its numbers are untouched — this rule drops fields, it does not rescale them.
    assert golfers["Marco Penge"] == pytest.approx(0.184, abs=0.002)
    assert len({round(p, 3) for p in golfers.values()}) > 1, (
        "a real field has a spread; if every golfer reads the same number here, the "
        "control has stopped being a control"
    )


async def test_no_golfer_from_the_offer_sheet_leaks_into_any_tournament(golf_db):
    """The four names must be absent from the whole payload, not just from a card."""
    body = await get_golf(golf_db)
    rendered = {
        g["name"]
        for t in body["tournaments"]
        for g in t.get("golfers", [])
    }
    for name in ("Andreas Halvorsen", "Adrian Meronk", "Eddie Pepperell", "Antoine Rozner"):
        assert name not in rendered, f"{name} came from the offer sheet"


async def test_movers_never_carry_an_offer_sheet_price(golf_db):
    body = await get_golf(golf_db)
    movers = {m.get("name") for m in body.get("biggest_movers") or []}
    assert "Andreas Halvorsen" not in movers
