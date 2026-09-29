"""#9550 — the search dropdown stops denying a result the venue already named.

THE DEFECT, production 2026-09-29 ~05:05Z (ux's #9493 after-check, 390 px):
`Dickerson` offered *Pereira at Dickerson · No result reported*; one tap opened
`/events/15320435`, whose hero read *Settled · Pereira wins*. The detail route
served `venue_settled: true, venue_settled_result: "Pereira wins"`; the typeahead
row served `status: suspended` and neither key, so no client could say more.

THE TARGET: the suspended row carries the detail route's two keys, from the same
shared reader `/search` has called since #7092.
THE STRAWMAN swaps the attach for a no-op: the row is production's again (no
keys), so the target case testifies.
THE CONTROLS:
  * an ungraded suspended match gets the present-False pair, never a verdict;
  * a suspended match that HOLDS A SCORE and a graded leg gets nothing — the
    detail route's gate refuses a row with a score, and the dropdown row does not
    carry that score (#9226 scores only finished rows), so a gate reading the
    suggestion instead of the row would print a verdict the page never does.

Production shape of the specimen (db-query 2026-09-29 05:1xZ): event 15320435
`suspended`, home `Dickerson`, away `Pereira`, no score; Kalshi leg
`Dickerson vs Pereira` → outcome `Jose Pereira`, `is_winner` true,
`resolution_source` `api_settlement`.

    SEARCH_TEST_DATABASE_URL=postgresql+asyncpg://postgres@localhost/bl_searchtest \\
        python3 -m pytest tests/integration/test_typeahead_venue_settled_pg_9550.py -v
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import pytest

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

pytestmark = [
    pytest.mark.skipif(
        not DB_URL,
        reason="set SEARCH_TEST_DATABASE_URL to run the #9550 typeahead real-Postgres gate",
    ),
    pytest.mark.asyncio,
]

# Hours inside #9493's started-today window, whatever the clock (gotcha #44).
_STARTED = timedelta(hours=6)

# One query per case, so no case competes with another for a pool slot.
_SPECIMEN_Q, _SPECIMEN = "Dickerson", ("Pereira", "Dickerson")
_UNGRADED_Q, _UNGRADED = "Brennan", ("Navarro", "Brennan")
_SCORED_Q, _SCORED = "Kowalczyk", ("Almeida", "Kowalczyk")


async def _seed(session) -> dict[str, int]:
    from app.models.models import Event, FuturesMarket, FuturesOutcome, Sport

    now = datetime.now(timezone.utc)
    tennis = Sport(key="tennis_other", name="Tennis")
    session.add(tennis)
    await session.flush()

    def _match(pair, **kw) -> Event:
        away, home = pair
        return Event(
            sport_id=tennis.id,
            away_team_name=away,
            home_team_name=home,
            commence_time=now - _STARTED,
            status="suspended",
            **kw,
        )

    specimen = _match(_SPECIMEN)
    ungraded = _match(_UNGRADED)
    scored = _match(_SCORED, home_score=1, away_score=0)
    session.add_all([specimen, ungraded, scored])
    await session.flush()

    def _graded_leg(event, winner_full_name, ticker):
        away, home = event.away_team_name, event.home_team_name
        market = FuturesMarket(
            source="kalshi",
            external_id=ticker,
            name=f"{home} vs {away}",
            market_type="duel",
            status="closed",
            event_id=event.id,
            resolution_date=now + timedelta(days=14),
        )
        session.add(market)
        return market, winner_full_name

    legs = [
        _graded_leg(specimen, "Jose Pereira", "KXATPCHALLENGERMATCH-26SEP28DICPER"),
        _graded_leg(scored, "Kamil Kowalczyk", "KXATPCHALLENGERMATCH-26SEP28KOWALM"),
    ]
    await session.flush()
    for market, winner in legs:
        session.add(
            FuturesOutcome(
                market_id=market.id,
                external_id=f"{market.external_id}:{winner}",
                name=winner,
                is_winner=True,
                resolution_source="api_settlement",
            )
        )
    await session.commit()
    return {"specimen": specimen.id, "ungraded": ungraded.id, "scored": scored.id}


@pytest.fixture
async def typeahead():
    """The real route, the real schema, the seed above; Redis patched out.

    `typeahead_search` reads a cache before the database, and a hit would make
    every assertion here a test of Redis instead of the route.
    """
    from unittest.mock import patch

    from httpx import ASGITransport, AsyncClient
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    import app.models.models  # noqa: F401  — registers every table on Base
    from app.main import app
    from app.services.database import Base, get_db, get_db_rw

    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        ids = await _seed(session)

    async def _override():
        async with maker() as session:
            yield session

    app.dependency_overrides[get_db] = _override
    app.dependency_overrides[get_db_rw] = _override
    try:
        with patch(
            "app.tasks.redis_state.get_redis_client",
            side_effect=RuntimeError("no redis"),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:

                async def _row(q: str, key: str) -> dict:
                    resp = await client.get("/api/events/typeahead", params={"q": q})
                    assert resp.status_code == 200, f"{q!r} -> HTTP {resp.status_code}"
                    rows = [
                        r
                        for r in resp.json()["suggestions"]
                        if r.get("type") == "event" and r.get("event_id") == ids[key]
                    ]
                    assert (
                        rows
                    ), f"{q!r} did not offer {key}: {resp.json()['suggestions']}"
                    return rows[0]

                yield _row
    finally:
        app.dependency_overrides.clear()
        await engine.dispose()


async def test_the_suspended_row_carries_the_venue_verdict(typeahead):
    """The production specimen: the dropdown says what the event page says."""
    row = await typeahead(_SPECIMEN_Q, "specimen")
    assert row["status"] == "suspended", row
    assert row.get("venue_settled") is True, row
    assert row.get("venue_settled_result") == "Pereira wins", row


async def test_the_strawman_reproduces_production(typeahead, monkeypatch):
    """With the attach a no-op, the row is production's `No result reported` row."""
    from app.routes import events as events_module

    async def _noop(*a, **kw):
        return None

    monkeypatch.setattr(events_module, "_typeahead_attach_venue_settlement", _noop)
    row = await typeahead(_SPECIMEN_Q, "specimen")
    assert row["status"] == "suspended", row
    assert "venue_settled" not in row and "venue_settled_result" not in row, row


async def test_an_ungraded_suspended_match_gets_no_verdict(typeahead):
    row = await typeahead(_UNGRADED_Q, "ungraded")
    assert row["status"] == "suspended", row
    assert row.get("venue_settled") is False, row
    assert row.get("venue_settled_result") is None, row


async def test_a_suspended_match_holding_a_score_is_not_asked(typeahead):
    """The gate reads the ROW's score, which the suggestion does not carry.

    The detail route refuses this row (a score is our own result), so the
    dropdown must too — no keys at all, exactly as before #9550.
    """
    row = await typeahead(_SCORED_Q, "scored")
    assert row["status"] == "suspended", row
    assert "home_score" not in row, row  # the premise: the suggestion has no score
    assert "venue_settled" not in row and "venue_settled_result" not in row, row
