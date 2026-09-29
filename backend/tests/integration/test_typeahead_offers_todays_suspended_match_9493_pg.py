"""#9493 — the search dropdown offers today's suspended match, against a real Postgres.

Production 2026-09-28 23:32Z (Alex, build 31), `GET /api/events/typeahead?q=Dickerson`:

    event    15320316  Dickerson/Rodriguez at Soto/Zeballos   scheduled, tomorrow
    futures  62900257  Curitiba: Ryan Dickerson vs Jose Pereira  (Polymarket)
    futures  62932041  Dickerson vs Pereira  (Kalshi, event_id=15320435)
    ...
    event    15320435  Pereira at Dickerson, started 17:10Z, `suspended`  ABSENT

`/search?q=Dickerson` returned 15320435 because `_SEARCH_STATUSES` admits
`suspended`. Every typeahead event arm did not. The fix is a WHERE clause and an
ORDER BY term, which a session double cannot observe, so the route runs
against real rows here. Wired as its own step in the `search-recall` CI job,
with skip, zero-count and short-count refusals.

    SEARCH_TEST_DATABASE_URL=postgresql+asyncpg://postgres@localhost/bl_searchtest \\
        python3 -m pytest tests/integration/test_typeahead_offers_todays_suspended_match_9493_pg.py -v
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import pytest

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

pytestmark = [
    pytest.mark.skipif(
        not DB_URL,
        reason="set SEARCH_TEST_DATABASE_URL to run the #9493 real-Postgres gate",
    ),
    pytest.mark.asyncio,
]

# Offsets from the real clock, taken once per seed. Each margin is hours wide,
# so no run can straddle a boundary (gotcha #44: offset first, no branch).
_SUSPENDED_TODAY = timedelta(hours=6)  # the specimen: 17:10Z start, read at 23:32Z
_SUSPENDED_STALE = timedelta(hours=13)  # past the 12h ceiling (#5028's bucket)
_SUSPENDED_FUTURE = timedelta(hours=-20)  # the #4114 mislabel: dated tomorrow
_DOUBLES_TOMORROW = timedelta(hours=-14)  # scheduled, names the query

_SPECIMEN = "Pereira at Dickerson"
_DOUBLES = "Soto/Zeballos at Dickerson/Rodriguez"
_STALE = "Ortega at Dickerson"
_FUTURE = "Moreno at Dickerson"

# Broad-query control: a sport-alias-free query that matches many rows. Nine
# scheduled matches fill the 8-row fetch, and the suspended one must not take a
# slot from any of them.
_BROAD_TOKEN = "Zzqtest"
_BROAD_SCHEDULED = [f"{_BROAD_TOKEN} Opp{i} at {_BROAD_TOKEN} Home{i}" for i in range(9)]
_BROAD_SUSPENDED = f"{_BROAD_TOKEN} Late at {_BROAD_TOKEN} Stopped"


_KALSHI_MARKET = "Dickerson vs Pereira"


async def _seed(session):
    from app.models.models import Event, FuturesMarket, FuturesOutcome, Sport

    now = datetime.now(timezone.utc)
    tennis = Sport(key="tennis_other", name="Tennis")
    session.add(tennis)
    await session.flush()

    def _match(away: str, home: str, ago: timedelta, status: str) -> Event:
        return Event(
            sport_id=tennis.id,
            away_team_name=away,
            home_team_name=home,
            commence_time=now - ago,
            status=status,
        )

    specimen = _match("Pereira", "Dickerson", _SUSPENDED_TODAY, "suspended")
    session.add_all([
        specimen,
        _match("Soto/Zeballos", "Dickerson/Rodriguez", _DOUBLES_TOMORROW, "scheduled"),
        _match("Ortega", "Dickerson", _SUSPENDED_STALE, "suspended"),
        _match("Moreno", "Dickerson", _SUSPENDED_FUTURE, "suspended"),
    ])
    for i in range(9):
        session.add(
            _match(
                f"{_BROAD_TOKEN} Opp{i}",
                f"{_BROAD_TOKEN} Home{i}",
                timedelta(hours=-(2 + i)),
                "scheduled",
            )
        )
    session.add(
        _match(f"{_BROAD_TOKEN} Late", f"{_BROAD_TOKEN} Stopped", _SUSPENDED_TODAY, "suspended")
    )
    await session.flush()
    # Kalshi's winner market for the specimen, linked to it (production
    # `futures_markets` 62932041, `event_id=15320435`). Dated by the venue's
    # close, two weeks out, as production's row is.
    market = FuturesMarket(
        source="kalshi",
        external_id="KXATPCHALLENGERMATCH-26SEP28DICPER",
        name=_KALSHI_MARKET,
        market_type="duel",
        status="open",
        event_id=specimen.id,
        resolution_date=now + timedelta(days=14),
    )
    session.add(market)
    await session.flush()
    for name, price in (("Ryan Dickerson", 0.51), ("Jose Pereira", 0.485)):
        session.add(
            FuturesOutcome(
                market_id=market.id,
                external_id=f"KXATPCHALLENGERMATCH-26SEP28DICPER:{name}",
                name=name,
                current_probability=price,
            )
        )
    await session.commit()


@pytest.fixture
async def typeahead():
    """The real route, the real schema, the seed above; Redis patched out.

    `typeahead_search` reads a cache before the database, and a hit would make
    every assertion here a test of Redis instead of the WHERE clause.
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
        await _seed(session)

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

                async def _do(q: str) -> list[dict]:
                    resp = await client.get("/api/events/typeahead", params={"q": q})
                    assert resp.status_code == 200, f"{q!r} -> HTTP {resp.status_code}"
                    return resp.json()["suggestions"]

                yield _do
    finally:
        app.dependency_overrides.clear()
        await engine.dispose()


def _events(rows: list[dict]) -> dict[str, dict]:
    return {r["text"]: r for r in rows if r.get("type") == "event"}


async def test_todays_suspended_match_is_offered(typeahead):
    """The production specimen: `Dickerson` six hours after a suspended start."""
    events = _events(await typeahead("Dickerson"))
    assert _SPECIMEN in events, f"today's suspended match is missing: {list(events)}"
    assert events[_SPECIMEN]["status"] == "suspended"


def _futures(rows: list[dict]) -> list[str]:
    return [r["text"] for r in rows if r.get("type") == "futures"]


async def test_the_matchs_own_kalshi_market_leaves_once_the_match_is_offered(typeahead):
    """#9493 defect 2: one match, one row, and the tap lands on the match.

    No new code for this half. #9415 already withholds a game's own winner
    market when that game is among the rows served. It could not fire while the
    game was never served.
    """
    rows = await typeahead("Dickerson")
    assert _SPECIMEN in _events(rows), [r["text"] for r in rows]
    assert _KALSHI_MARKET not in _futures(rows), [r["text"] for r in rows]


async def test_the_scheduled_doubles_row_is_still_offered(typeahead):
    """The row that was already there stays: the change only adds."""
    events = _events(await typeahead("Dickerson"))
    assert _DOUBLES in events, list(events)


async def test_a_suspended_row_past_the_ceiling_is_not_offered(typeahead):
    """gotcha #41's second bound: 13h after its start, the #5028 bucket stays out."""
    events = _events(await typeahead("Dickerson"))
    assert _STALE not in events, list(events)


async def test_a_future_dated_suspended_row_is_not_offered(typeahead):
    """A suspended row that has not started is #4114's mislabel, not a stopped match."""
    events = _events(await typeahead("Dickerson"))
    assert _FUTURE not in events, list(events)


async def test_a_full_pool_keeps_every_scheduled_row_it_had(typeahead):
    """Suspended sorts LAST, so a pool the scheduled rows fill loses none of them.

    Nine scheduled rows exceed the 8-row fetch and the 4-slot cut. The
    suspended row started before all of them, so without the sort term it
    would take the first slot.
    """
    events = _events(await typeahead(_BROAD_TOKEN))
    assert _BROAD_SUSPENDED not in events, list(events)
    scheduled_served = [t for t in events if t in _BROAD_SCHEDULED]
    assert scheduled_served, f"no scheduled row served at all: {list(events)}"
    # The earliest scheduled rows, in start order, are the ones kept.
    assert scheduled_served == _BROAD_SCHEDULED[: len(scheduled_served)], scheduled_served


async def test_the_strawman_window_reproduces_production(typeahead, monkeypatch):
    """With the old live/scheduled-only window, the specimen is gone.

    Proves the seed can express the defect. Without this, a green run could
    mean only that the rig never built a row the old window would drop.
    """
    from sqlalchemy import and_

    from app.models.models import Event
    from app.routes import events as events_module

    monkeypatch.setattr(
        events_module,
        "_typeahead_event_pool_window",
        lambda now: and_(
            Event.status.in_(["live", "scheduled"]),
            events_module._pool_start_floor(now),
        ),
    )
    rows = await typeahead("Dickerson")
    events = _events(rows)
    assert _SPECIMEN not in events, list(events)
    assert _DOUBLES in events, list(events)
    # And the reported half: the match's own market stands in for it.
    assert _KALSHI_MARKET in _futures(rows), [r["text"] for r in rows]


async def test_the_strawman_order_lets_suspended_take_a_full_pools_slot(
    typeahead, monkeypatch
):
    """Without the suspended-last term, the broad query's pool changes.

    Proves the full-pool control can fail: a suspended row sorted by start
    time alone takes a slot a scheduled row had.
    """
    from sqlalchemy import literal

    from app.routes import events as events_module

    monkeypatch.setattr(events_module, "_typeahead_suspended_last", lambda: literal(0))
    events = _events(await typeahead(_BROAD_TOKEN))
    assert _BROAD_SUSPENDED in events, list(events)
