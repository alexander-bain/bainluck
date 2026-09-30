"""`playoffs` leads with the postseason in progress, not next season's boards.

THE DEFECT, read on production Monday 2026-09-28 10:3xZ, the day before MLB's
Wild Card round: `/search?q=playoffs` led its futures with "Will the VALORANT
Champions 2026 champion go undefeated…" and nine "…advance to the Second Round
of the 2027 Stanley Cup Playoffs?" boards, and the dropdown with VALORANT and
four 2027 College Football Playoff boards. ~615 open names carry the word and
all tie on the name tier and `ts_rank_cd`; `market_tier` then filled the
twenty-row window, and every MLB postseason board is tier 5 (#9340).

THE FIX: `_futures_postseason_now_order_key` — for a query that is only a
postseason word, team-sport rows resolving within 45 days sort first, inside
the name tier, on both screens.

THE STRAWMEN: (1) the SQL key removed -> the MLB boards are cut by the window and
the page is next season's; (2) esports admitted to the key -> a Rainbow Six
playoff series (tier 4, resolves tomorrow) joins the lead; (3) the Python
partition removed -> the reranker's name/volume sort undoes the fetch.
THE CONTROLS: `stanley cup playoffs` still serves the Stanley Cup boards (the
key is None for any query naming more than the postseason), and `mlb playoffs`
serves MLB.

WHY THE ROUTE AND POSTGRES: the key is an ORDER BY term over a twenty-row
LIMIT window inside two route bodies; only a real database cuts that window.
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
            "set SEARCH_TEST_DATABASE_URL to run the real-Postgres playoffs "
            "gate (CI job `search-recall` provides one)"
        ),
    ),
]

# (name, days to resolution, market_tier, volume)
MLB = {
    "MLB Playoffs: Team to advance to ALDS": (7, 5, 7118.0),
    "MLB Playoffs: Team to advance to NLCS": (17, 5, 9941.0),
    "Boston: First Playoff Opponent": (34, 5, 213.0),
    "How many playoff games will New York Y host this season?": (34, 5, 6016.0),
    "Will Boston Red Sox advance to the ALDS in the 2026 MLB Playoffs?": (7, 5, None),
    "Will Chicago Cubs advance to the NLDS in the 2026 MLB Playoffs?": (7, 5, None),
    "Will New York Yankees advance to the ALCS in the 2026 MLB Playoffs?": (17, 5, None),
}
ESPORTS = {
    "Rainbow Six Siege: Weibo Gaming vs Fury (BO3) - Asia Pacific League Playoffs": (1, 4, None),
}
VALORANT = "Will the VALORANT Champions 2026 champion go undefeated on maps in the Playoffs?"
# Production held ~615 such names; the gate needs more than the window (20)
# plus the refill (40) of them, or the refill would reach the MLB rows anyway.
NHL_TEAMS = [
    "Boston Bruins", "Buffalo Sabres", "Detroit Red Wings", "Florida Panthers",
    "Montreal Canadiens", "Ottawa Senators", "Tampa Bay Lightning", "Toronto Maple Leafs",
    "Carolina Hurricanes", "Columbus Blue Jackets", "New Jersey Devils",
    "New York Islanders", "New York Rangers", "Philadelphia Flyers",
    "Pittsburgh Penguins", "Washington Capitals", "Chicago Blackhawks",
    "Colorado Avalanche", "Dallas Stars", "Minnesota Wild", "Nashville Predators",
    "St. Louis Blues", "Utah Mammoth", "Winnipeg Jets", "Anaheim Ducks",
    "Calgary Flames", "Edmonton Oilers", "Los Angeles Kings", "San Jose Sharks",
    "Seattle Kraken", "Vancouver Canucks", "Vegas Golden Knights",
]
CFP_TEAMS = [
    "Alabama", "Georgia", "Ohio St.", "Texas", "Oregon", "Notre Dame",
    "Penn St.", "Michigan", "LSU", "Miami (FL)", "Clemson", "Tennessee",
]
NHL_ROUNDS = ["Second Round", "Conference Finals"]
NEXT_SEASON = {
    **{
        f"Will {t} advance to the {r} of the 2027 Stanley Cup Playoffs?": (219, 1, None, "hockey")
        for t in NHL_TEAMS for r in NHL_ROUNDS
    },
    **{
        f"Will {t} Make the 2027 College Football Playoff National Championship?": (134, 1, None, "football")
        for t in CFP_TEAMS
    },
    VALORANT: (51, 1, 536.0, "esports"),
}


def _seed_rows():
    for name, (days, tier, vol) in MLB.items():
        yield name, days, tier, vol, "baseball"
    for name, (days, tier, vol) in ESPORTS.items():
        yield name, days, tier, vol, "esports"
    for name, (days, tier, vol, cat) in NEXT_SEASON.items():
        yield name, days, tier, vol, cat


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
        for i, (name, days, tier, vol, cat) in enumerate(_seed_rows()):
            market = FuturesMarket(
                source="polymarket", external_id=f"playoffs-now-{i}", name=name,
                status="open", resolution_date=now + timedelta(days=days),
                market_tier=tier, volume=vol, llm_sport_category=cat,
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


def _search_futures(payload: dict) -> list[str]:
    assert "futures" in payload, f"no `futures` key; got {sorted(payload)}"
    return [f["name"] for f in payload["futures"] or []]


def _typeahead_futures(payload: dict) -> list[str]:
    assert "suggestions" in payload, f"no `suggestions` key; got {sorted(payload)}"
    return [s["text"] for s in payload["suggestions"] if s.get("type") == "futures"]


def _lead_block(names: list[str]) -> list[str]:
    """The rows before the first one that is not an MLB postseason board."""
    lead = []
    for n in names:
        if n not in MLB:
            break
        lead.append(n)
    return lead


@pytest.mark.parametrize("q", ["playoffs", "Playoffs", "playoff"])
async def test_search_leads_with_the_postseason_in_progress(get, q):
    futures = _search_futures(await get("search", q))
    lead = _lead_block(futures)
    # Every MLB board the page carries is in the lead block, and it has several.
    assert len(lead) >= 3 and set(futures) & set(MLB) == set(lead), futures
    assert not set(futures) & set(ESPORTS), futures


async def test_the_dropdown_offers_the_postseason_in_progress(get):
    texts = _typeahead_futures(await get("typeahead", "playoffs"))
    assert len(_lead_block(texts)) >= 3, f"dropdown offered {texts}"
    assert not set(texts) & set(ESPORTS) and VALORANT not in texts[:3], texts


async def test_stanley_cup_playoffs_still_serves_the_stanley_cup_boards(get):
    """Control: a query naming more than the postseason compiles no key."""
    futures = _search_futures(await get("search", "stanley cup playoffs"))
    assert futures and all("Stanley Cup" in n for n in futures), futures


async def test_mlb_playoffs_serves_mlb(get):
    """Control: the league word already finds its boards."""
    futures = _search_futures(await get("search", "mlb playoffs"))
    assert futures and set(futures) <= set(MLB), futures


async def test_without_the_key_the_window_cuts_the_mlb_boards(get, monkeypatch):
    """Strawman 1: the fixture reproduces production's page."""
    from app.routes import events as events_module

    monkeypatch.setattr(
        events_module, "_futures_postseason_now_order_key", lambda terms, now: None
    )
    futures = _search_futures(await get("search", "playoffs"))
    assert not set(futures) & set(MLB), futures
    texts = _typeahead_futures(await get("typeahead", "playoffs"))
    assert not set(texts) & set(MLB), texts


async def test_admitting_esports_puts_a_rainbow_six_series_first(get, monkeypatch):
    """Strawman 2: the sport clause is what keeps the esports series out."""
    from app.routes import events as events_module

    monkeypatch.setattr(
        events_module,
        "_POSTSEASON_NOW_SPORT_CATEGORIES",
        events_module._POSTSEASON_NOW_SPORT_CATEGORIES | {"esports"},
    )
    futures = _search_futures(await get("search", "playoffs"))
    assert set(ESPORTS) & set(futures[: len(MLB) + 1]), futures


async def test_without_the_python_partition_the_rerank_undoes_the_fetch(get, monkeypatch):
    """Strawman 3: the SQL key alone fetches the rows; the reranker's name/volume
    sort then hands the VALORANT novelty a slot above the Kalshi boards."""
    from app.routes import events as events_module

    monkeypatch.setattr(
        events_module, "_postseason_now_first", lambda markets, terms: markets
    )
    texts = _typeahead_futures(await get("typeahead", "playoffs"))
    assert VALORANT in texts[:3] or len(_lead_block(texts)) < 3, texts
