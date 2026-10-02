"""#9208 — the search dropdown's called-off game carries ESPN's word, against a real Postgres.

THE DEFECT (native's iOS half, 2026-10-02): search rows, team rows, the event
hero and the cards all say "Canceled"/"Postponed", but a TYPEAHEAD suggestion
for the same game served `{status: suspended}` and no word, so the row could
only print "No result reported". The team brief has served `stoppage` since
#9208's first half (Orioles @ Yankees 15319530).

THE TARGET: today's suspended game with ESPN period "Canceled" carries
`stoppage: "Canceled"`.
THE STRAWMAN swaps the rule for one that returns nothing: the row is
production's bare `suspended` again, so the target case testifies.
THE CONTROLS: a suspended rain delay (period "7") and a scheduled game carry no
`stoppage` key at all.

WHY POSTGRES: a suspended row reaches this pool only through #9493's WHERE
clause (started today, under the 12h ceiling), which a session double cannot
observe.

    SEARCH_TEST_DATABASE_URL=postgresql+asyncpg://postgres@localhost/bl_searchtest \\
        python3 -m pytest tests/integration/test_typeahead_stoppage_pg_9208.py -v
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import pytest

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

pytestmark = [
    pytest.mark.skipif(
        not DB_URL,
        reason="set SEARCH_TEST_DATABASE_URL to run the #9208 typeahead real-Postgres gate",
    ),
    pytest.mark.asyncio,
]

# Offsets from the real clock, taken once per seed. Each margin is hours wide,
# so no run can straddle a boundary (gotcha #44: offset first, no branch).
_STARTED_TODAY = timedelta(hours=6)  # inside #9493's 12h ceiling
_TOMORROW = timedelta(hours=-20)

CANCELED = "Baltimore Orioles at New York Yankees"
DELAYED = "Toronto Blue Jays at Tampa Bay Rays"
NEXT = "New York Yankees at Boston Red Sox"


async def _seed(session):
    from app.models.models import Event, Sport

    now = datetime.now(timezone.utc)
    mlb = Sport(key="baseball_mlb", name="MLB")
    session.add(mlb)
    await session.flush()

    def _game(away: str, home: str, ago: timedelta, status: str, period=None) -> Event:
        return Event(
            sport_id=mlb.id,
            away_team_name=away,
            home_team_name=home,
            commence_time=now - ago,
            status=status,
            period=period,
        )

    session.add_all([
        _game("Baltimore Orioles", "New York Yankees", _STARTED_TODAY, "suspended", "Canceled"),
        _game("Toronto Blue Jays", "Tampa Bay Rays", _STARTED_TODAY, "suspended", "7"),
        _game("New York Yankees", "Boston Red Sox", _TOMORROW, "scheduled"),
    ])
    await session.commit()


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


def _row(rows: list[dict], text: str) -> dict:
    events = [r for r in rows if r.get("type") == "event" and r.get("text") == text]
    assert events, f"{text!r} not offered: {[r.get('text') for r in rows]}"
    return events[0]


async def test_the_canceled_game_carries_the_word(typeahead):
    canceled = _row(await typeahead("Yankees"), CANCELED)
    assert canceled["status"] == "suspended", canceled
    assert canceled.get("stoppage") == "Canceled", canceled


async def test_the_strawman_reproduces_production(typeahead, monkeypatch):
    """With the rule returning nothing, the row is production's bare `suspended`."""
    from app.routes import events as events_module

    monkeypatch.setattr(events_module, "_typeahead_stoppage", lambda *a: {})
    canceled = _row(await typeahead("Yankees"), CANCELED)
    assert canceled["status"] == "suspended", canceled
    assert "stoppage" not in canceled, canceled


async def test_a_rain_delay_carries_no_word(typeahead):
    delayed = _row(await typeahead("Rays"), DELAYED)
    assert delayed["status"] == "suspended", delayed
    assert "stoppage" not in delayed, delayed


async def test_the_next_game_carries_no_word(typeahead):
    nxt = _row(await typeahead("Yankees"), NEXT)
    assert nxt["status"] == "scheduled", nxt
    assert "stoppage" not in nxt, nxt
