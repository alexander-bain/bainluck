"""`/api/events/search` stops announcing a correction the page does not need (#8750).

Production, 2026-09-27 ~00:50Z, `GET /api/events/search`:

    q=Warsh          did_you_mean "Ware FC"          1 FA Cup game   10 futures
    q=kevin warsh    did_you_mean "Kevin Walsh"      0 games         10 futures
    q=taylor swift   did_you_mean "Taylor Sullivan"  0 games         10 futures

`/search?q=taylor swift` at 390px was headed "Showing results for Taylor
Sullivan" above ten Taylor Swift markets. The fuzzy arm fires on "no GAMES
matched" and runs before the futures stage, so it cannot see that the typed text
already answered.

The typed text matched markets -> the correction is withdrawn whole (banner, the
corrected query's games, their pill and count). Kill control: the same query with
the market closed gets the correction back.

NOT withdrawn: a correction that found no games. On an empty page the web prints
"No results ... Did you mean X?" as a link, a real next step, and #8250's
contract holds `/search` and `/typeahead` to the same correction there.

And the regression the withdrawal must never cause (#8155's blank page): a real
misspelling whose typed text matches no market is still corrected.

The route runs only on PostgreSQL (`similarity()` / `%` behind `SET LOCAL
pg_trgm.similarity_threshold`), so CI's `search-recall` job grades this.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import pytest

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

pytestmark = [pytest.mark.asyncio]

needs_postgres = pytest.mark.skipif(
    not DB_URL,
    reason=(
        "set SEARCH_TEST_DATABASE_URL to run the real-Postgres did-you-mean "
        "contract (CI job `search-recall` provides one)"
    ),
)

# `similarity('Ware FC', 'warsh')` = 3/11 = 0.27 > the 0.25 the route pins —
# the production pair, not a tuned one.
WARSH_CLUB = "Ware FC"
WARSH_MARKET = "Will Kevin Warsh be confirmed as Fed Chair?"
# The #8155 shape: a misspelling with games and no market.
TIGERS = "Tigers"


async def _seed(session):
    from app.models.models import Event, FuturesMarket, FuturesOutcome, Sport, Team

    fa_cup = Sport(key="soccer_fa_cup", name="FA Cup")
    mlb = Sport(key="baseball_mlb", name="MLB")
    session.add_all([fa_cup, mlb])
    await session.flush()

    start = datetime.now(timezone.utc) + timedelta(days=2)
    session.add_all(
        [
            Team(sport_id=fa_cup.id, name=WARSH_CLUB, abbreviation="WAR"),
            Team(sport_id=mlb.id, name=TIGERS, abbreviation="DET"),
        ]
    )
    ware_game = Event(
        sport_id=fa_cup.id,
        home_team_name=WARSH_CLUB,
        away_team_name="Hitchin Town",
        commence_time=start,
        status="scheduled",
    )
    tigers_game = Event(
        sport_id=mlb.id,
        home_team_name="Detroit Tigers",
        away_team_name="Chicago White Sox",
        commence_time=start,
        status="scheduled",
    )
    session.add_all([ware_game, tigers_game])

    market = FuturesMarket(
        source="kalshi",
        external_id="KXFEDCHAIR-8750",
        name=WARSH_MARKET,
        status="open",
        resolution_date=datetime.now(timezone.utc) + timedelta(days=90),
    )
    session.add(market)
    await session.flush()
    for outcome_name in ("Yes", "No"):
        session.add(
            FuturesOutcome(
                market_id=market.id,
                external_id=f"KXFEDCHAIR-8750:{outcome_name}",
                name=outcome_name,
                current_probability=0.6 if outcome_name == "Yes" else 0.4,
            )
        )
    await session.commit()
    return {
        "fa_cup": fa_cup.id,
        "ware_game": ware_game.id,
        "tigers_game": tigers_game.id,
        "market": market.id,
    }


@pytest.fixture
async def seeded():
    """Real Postgres, real schema, real `pg_trgm`; function-scoped (see
    `test_search_proven_duplicate_pg.py` for why not module-scoped)."""
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    import app.models.models  # noqa: F401 — registers every table on Base
    from app.services.database import Base

    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        ids = await _seed(session)

    yield maker, ids

    await engine.dispose()


@pytest.fixture
async def client(seeded):
    """The real app against the real database, with Redis refused — `/search`
    has a full response cache and every kill control below asks a question a
    second time."""
    from unittest.mock import patch

    from httpx import ASGITransport, AsyncClient

    from app.dependencies.auth import get_optional_user
    from app.main import app
    from app.services.database import get_db, get_db_rw

    maker, ids = seeded

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

            async def _search(q: str) -> dict:
                resp = await http.get("/api/events/search", params={"q": q})
                assert resp.status_code == 200, f"search {q!r} -> {resp.status_code}"
                return resp.json()

            yield _search, maker, ids

    app.dependency_overrides.clear()


def _result_ids(payload: dict) -> list[int]:
    return [r["id"] for r in payload.get("results") or []]


def _futures_ids(payload: dict) -> list[int]:
    return [f["id"] for f in payload.get("futures") or []]


async def _close_the_market(maker, market_id):
    from sqlalchemy import update

    from app.models.models import FuturesMarket

    async with maker() as session:
        await session.execute(
            update(FuturesMarket)
            .where(FuturesMarket.id == market_id)
            .values(status="closed")
        )
        await session.commit()


# ---------------------------------------------------------------------------
# 1. The typed text already answered — the correction is withdrawn whole
# ---------------------------------------------------------------------------


@needs_postgres
async def test_a_query_that_matched_markets_is_not_corrected(client):
    search, _maker, ids = client

    payload = await search("warsh")

    assert ids["market"] in _futures_ids(payload), (
        "the Warsh market is not served, so this test is not exercising the "
        f"arm it names; futures: {payload.get('futures')}"
    )
    assert "did_you_mean" not in payload
    assert ids["ware_game"] not in _result_ids(payload)
    assert payload["sports"] == []
    assert payload["pagination"]["total_results"] == 0


@needs_postgres
async def test_kill_control_the_same_query_with_the_market_closed_is_corrected(client):
    search, maker, ids = client

    await _close_the_market(maker, ids["market"])
    payload = await search("warsh")

    assert ids["market"] not in _futures_ids(payload)
    assert payload.get("did_you_mean") == WARSH_CLUB
    assert ids["ware_game"] in _result_ids(payload)
    assert [s["key"] for s in payload["sports"]] == ["soccer_fa_cup"]


# ---------------------------------------------------------------------------
# 2. The regression the withdrawal must never cause: #8155's blank page
# ---------------------------------------------------------------------------


@needs_postgres
async def test_a_real_misspelling_with_no_market_is_still_corrected(client):
    search, _maker, ids = client

    payload = await search("tigerz")

    assert payload.get("futures") == []
    assert payload.get("did_you_mean") == TIGERS
    assert ids["tigers_game"] in _result_ids(payload)
