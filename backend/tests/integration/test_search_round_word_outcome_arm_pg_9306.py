"""#9306 — `alds` shows the ALDS markets, not a page of Byron Donalds politics.

THE DEFECT, read on production 2026-09-28 06:4xZ (`700f4060`):
`/search?q=alds` FUTURES & MARKETS served the two ALDS markets, then eight
politics markets — "Florida Governor winner?" (Byron Donalds 79%), "Republican
Presidential Nominee 2028", "Time's Person of the Year for 2026" (Jimmy
Donaldson) … — and `/typeahead?q=alds` slotted "Florida Governor winner?" and
"Florida Governor Election Winner" at 4–5. None of those NAMES holds `alds`; the
futures OUTCOME arm reached them through `ILIKE '%alds%'` inside Don(alds).

Now a round word (`_TEAM_PREFIX_REFUSED_TOKENS`) matches an outcome only as a
whole word, on both screens. Every other query's outcome arm is unchanged —
#5773 measured the general word test down (`lebro` would lose all 367 LeBron
markets), and the controls here pin that.

THE STRAWMAN removes the round-word set: the fixture then serves the Donalds
market on both screens, as production did.
THE CONTROLS: `donalds` still finds the governor market through its outcome
(the whole word), and `lebro` still reaches the LeBron market through an
outcome it is only the start of.

WHY THE ROUTE AND POSTGRES: the fix is a `~*` POSIX regex with `[[:alnum:]]`,
and the arm is wired inside two route bodies. SQLite serves neither.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import pytest

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not DB_URL,
        reason=(
            "set SEARCH_TEST_DATABASE_URL to run the real-Postgres #9306 round-"
            "word gate (CI job `search-recall` provides one)"
        ),
    ),
]

ALDS_MARKET = "MLB Playoffs: Team to advance to ALDS"
GOVERNOR = "Florida Governor winner?"
PERSON_OF_YEAR = "Time's Person of the Year for 2026"
LEBRON_MARKET = "Most points in a single game this season?"

# (external_id, market name, outcome names). The outcomes are the production
# rows' own spellings.
SEEDS = [
    ("KXMLBALDS-26", ALDS_MARKET, ["Boston Red Sox", "Houston Astros"]),
    ("KXGOVFL-26", GOVERNOR, ["Byron Donalds", "David Jolly"]),
    ("KXPERSONYEAR-26", PERSON_OF_YEAR, ["Jimmy Donaldson", "Pope Leo XIV"]),
    ("KXNBAPTS-26", LEBRON_MARKET, ["LeBron James", "Luka Doncic"]),
]


@pytest.fixture
async def maker():
    """A clean schema per test — the `search-recall` database is shared."""
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    import app.models.models  # noqa: F401 — registers every table on Base
    from app.models.models import FuturesMarket, FuturesOutcome
    from app.services.database import Base

    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    async with session_maker() as session:
        for external_id, name, outcomes in SEEDS:
            market = FuturesMarket(
                source="kalshi",
                external_id=external_id,
                name=name,
                status="open",
                # The route filters `resolution_date IS NULL OR >= now()`.
                resolution_date=datetime.now(timezone.utc) + timedelta(days=90),
            )
            session.add(market)
            await session.flush()
            for outcome in outcomes:
                session.add(
                    FuturesOutcome(
                        market_id=market.id,
                        external_id=f"{external_id}:{outcome}",
                        name=outcome,
                        current_probability=0.5,
                    )
                )
        await session.commit()

    yield session_maker

    await engine.dispose()


@pytest.fixture
async def get(maker):
    """`GET` either screen against the real app and the real database.

    Redis raises so both response caches miss, as in the sibling gates.
    """
    from unittest.mock import patch

    from httpx import ASGITransport, AsyncClient

    from app.dependencies.auth import get_optional_user
    from app.main import app
    from app.services.database import get_db, get_db_rw

    async def _override():
        async with maker() as session:
            yield session

    app.dependency_overrides[get_db] = _override
    app.dependency_overrides[get_db_rw] = _override
    app.dependency_overrides[get_optional_user] = lambda: None

    with patch(
        "app.tasks.redis_state.get_redis_client",
        side_effect=RuntimeError("no redis in the recall gate"),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as http:

            async def _get(path: str, q: str) -> dict:
                resp = await http.get(f"/api/events/{path}", params={"q": q})
                assert resp.status_code == 200, f"{path} {q!r} -> {resp.status_code}"
                return resp.json()

            yield _get

    app.dependency_overrides.clear()


def _search_names(payload: dict) -> list[str]:
    assert "futures" in payload, f"no `futures` key; got {sorted(payload)}"
    return [f.get("name") for f in payload["futures"]]


def _typeahead_texts(payload: dict) -> list[str]:
    assert "suggestions" in payload, f"no `suggestions` key; got {sorted(payload)}"
    return [s.get("text") for s in payload["suggestions"] if s.get("type") == "futures"]


def _disarm(monkeypatch) -> None:
    from app.routes import events as events_module

    monkeypatch.setattr(events_module, "_TEAM_PREFIX_REFUSED_TOKENS", frozenset())


SCREENS = [("search", _search_names), ("typeahead", _typeahead_texts)]


@pytest.mark.parametrize("path, read", SCREENS)
async def test_alds_serves_the_alds_market_and_no_donalds(get, path, read):
    names = read(await get(path, "alds"))
    assert ALDS_MARKET in names, (
        f"the ALDS market itself must still be served, or this tests nothing: {names}"
    )
    assert GOVERNOR not in names and PERSON_OF_YEAR not in names, (
        f"`alds` still reaches a market through Don(alds) / Don(alds)on: {names}"
    )


@pytest.mark.parametrize("path, read", SCREENS)
async def test_without_the_round_word_set_donalds_comes_back(
    get, path, read, monkeypatch
):
    """Strawman: the fixture reproduces #9306 with the rule removed."""
    _disarm(monkeypatch)
    names = read(await get(path, "alds"))
    assert GOVERNOR in names and PERSON_OF_YEAR in names, names


@pytest.mark.parametrize("path, read", SCREENS)
async def test_the_whole_word_still_reaches_the_outcome(get, path, read):
    """Control: typing the surname finds the governor market by its outcome."""
    names = read(await get(path, "donalds"))
    assert GOVERNOR in names, names


@pytest.mark.parametrize("path, read", SCREENS)
async def test_progressive_typing_still_reaches_an_outcome(get, path, read):
    """Control: #5773's reason the general word test was refused. `lebro` is the
    start of "LeBron", not a whole word, and must keep reaching the market."""
    names = read(await get(path, "lebro"))
    assert LEBRON_MARKET in names, names
