"""`division series` finds the ALDS/NLDS markets, and never Byron Don(alds).

THE DEFECT, read on production Monday 2026-09-28 08:4xZ: `/search?q=division
series` served nothing at all — results 0, futures 0 — with eight open markets
about the round ("MLB Playoffs: Team to advance to ALDS", "Will Boston Red Sox
advance to the ALDS in the 2026 MLB Playoffs?"). The venues name the round only
by abbreviation (#9340).

THE FIX: `_QUERY_PHRASE_ALIASES` maps the spelled-out rounds to their
abbreviations, and `_alias_futures_arms` compiles them whole-word.

THE STRAWMEN: (1) the two aliases removed -> `division series` goes back to
serving nothing; (2) the alias arm compiled by plain substring -> the Byron
Donalds market and the Wealdstone market ride in on `%alds%`.
THE CONTROL: `alds` itself still serves the ALDS markets and not Byron Donalds
(#9306's rule), so the seed can tell the two apart.

WHY THE ROUTE AND POSTGRES: the whole-word test is a `~*` regex beside a
trigram ILIKE, wired as a UNION arm inside two route bodies.
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
            "set SEARCH_TEST_DATABASE_URL to run the real-Postgres division-series "
            "gate (CI job `search-recall` provides one)"
        ),
    ),
]

DIVISION = {
    "MLB Playoffs: Team to advance to ALDS",
    "MLB Playoffs: Team to advance to NLDS",
    "Will Boston Red Sox advance to the ALDS in the 2026 MLB Playoffs?",
    "Will Chicago Cubs advance to the NLDS in the 2026 MLB Playoffs?",
}
CHAMPIONSHIP = {
    "MLB Playoffs: Team to advance to ALCS",
    "Pro Baseball NLCS Matchup",
}
# The route prints Kalshi's "Pro Baseball" as MLB.
CHAMPIONSHIP_SERVED = {
    "MLB Playoffs: Team to advance to ALCS",
    "MLB NLCS Matchup",
}
# `%alds%` is inside both names; neither is the round.
COLLISIONS = {
    "Florida Governor election: Byron Donalds vote percent",
    "Wealdstone to win the National League?",
}


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

    now = datetime.now(timezone.utc)
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    async with session_maker() as session:
        for i, name in enumerate(sorted(DIVISION | CHAMPIONSHIP | COLLISIONS)):
            market = FuturesMarket(
                source="polymarket", external_id=f"round-word-{i}", name=name,
                status="open", resolution_date=now + timedelta(days=20),
            )
            session.add(market)
            await session.flush()
            for outcome, p in (("Yes", 0.4), ("No", 0.6)):
                session.add(FuturesOutcome(
                    market_id=market.id, name=outcome, current_probability=p,
                    external_id=f"{market.external_id}:{outcome}",
                ))
        await session.commit()

    yield session_maker

    await engine.dispose()


@pytest.fixture
async def get(maker):
    """`GET` either screen against the real app and the real database."""
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


def _search_futures(payload: dict) -> set[str]:
    assert "futures" in payload, f"no `futures` key; got {sorted(payload)}"
    return {f["name"] for f in payload["futures"] or []}


def _typeahead_texts(payload: dict) -> set[str]:
    assert "suggestions" in payload, f"no `suggestions` key; got {sorted(payload)}"
    return {s["text"] for s in payload["suggestions"]}


@pytest.mark.parametrize("q", ["division series", "Division Series", "mlb division series"])
async def test_search_serves_the_division_series_markets(get, q):
    futures = _search_futures(await get("search", q))
    assert futures == DIVISION, f"{q!r} served {futures}"


async def test_the_dropdown_offers_them_and_no_collision(get):
    texts = _typeahead_texts(await get("typeahead", "division series"))
    assert texts & DIVISION, f"typeahead offered none of the round: {texts}"
    assert not texts & COLLISIONS, f"typeahead offered a collision: {texts}"


async def test_championship_series_serves_the_lcs_markets(get):
    futures = _search_futures(await get("search", "championship series"))
    assert futures == CHAMPIONSHIP_SERVED, futures
    texts = _typeahead_texts(await get("typeahead", "championship series"))
    assert texts & CHAMPIONSHIP_SERVED and not texts & COLLISIONS, texts


async def test_alds_itself_is_the_round_not_the_surname(get):
    """Control: the seed separates the whole word from the substring."""
    alds = {n for n in DIVISION if "ALDS" in n}
    assert _search_futures(await get("search", "alds")) == alds
    texts = _typeahead_texts(await get("typeahead", "alds"))
    assert texts & alds and not texts & COLLISIONS, texts


async def test_without_the_aliases_division_series_serves_nothing(get, monkeypatch):
    """Strawman 1: the fixture reproduces production's empty answer."""
    from app.routes import events as events_module

    table = {
        k: v for k, v in events_module._QUERY_PHRASE_ALIASES.items()
        if k not in {("division", "series"), ("championship", "series")}
    }
    monkeypatch.setattr(events_module, "_QUERY_PHRASE_ALIASES", table)
    assert _search_futures(await get("search", "division series")) == set()


async def test_a_substring_alias_arm_brings_byron_donalds_back(get, monkeypatch):
    """Strawman 2: the whole-word compile is what keeps the collisions out."""
    from app.routes import events as events_module

    monkeypatch.setattr(
        events_module, "_build_round_word_ilike", events_module._build_expanded_ilike
    )
    futures = _search_futures(await get("search", "division series"))
    assert DIVISION <= futures and futures & COLLISIONS, futures
