"""`championship series` leads with the ALCS/NLCS markets, not NFL season-series boards.

THE DEFECT, read on production `fa40adc3` (#9356 live), Monday 2026-09-28
12:3xZ: `/search?q=championship series` served "MLB Championship Series
Matchup" and then nine "NFL: Cardinals vs. 49ers Season Series Winner"
boards; the 390px page printed them under a "CHAMPIONSHIP SERIES" heading. The
open ALCS/NLCS markets exist (`alcs` serves six) and none reached the page.
The dropdown was the same. `championship` carries the `winner` synonym, so
"Season Series Winner" matches every typed word by NAME (tier 0) and fills
the 20-row window above the abbreviation alias arm (tier 1).

THE FIX: when the query IS a spelled-out round (`_POSTSEASON_NAMED_ROUNDS`,
optionally with its own league word), the round's whole-word abbreviation
markets lead — in the /search window's tier (-1), the dropdown pool's first
ORDER key and the shared reranker's last partition. The same rule #9333 uses
for `wild card`, with the round's NAME abbreviation instead of its ticker code.

THE STRAWMAN: the lead rule disarmed -> the NFL boards take the page again
(the seed reproduces production's order). THE CONTROLS: `season series
winner` still leads with the NFL boards. (`nfl championship series` is pinned
by the pure tests in `tests/test_championship_series_lead_9340.py`, not here:
its recall arm needs `nfl` in the name, so the route never fetches the MLB
round for it and a route control could not fail.)
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
            "set SEARCH_TEST_DATABASE_URL to run the real-Postgres championship-"
            "series lead gate (CI job `search-recall` provides one)"
        ),
    ),
]

LCS = {
    "MLB Playoffs: Team to advance to ALCS",
    "Will New York Yankees advance to the ALCS in the 2026 MLB Playoffs?",
    "MLB NLCS Qualifiers",
}
DIVISION = {
    "MLB Playoffs: Team to advance to ALDS",
    "Will Chicago Cubs advance to the NLDS in the 2026 MLB Playoffs?",
}
# More than the 20-row window, and far more volume than the round's markets:
# production had one per NFL division rivalry.
_CLUBS = [
    "Cardinals", "49ers", "Lions", "Packers", "Seahawks", "Cowboys", "Commanders",
    "Bengals", "Browns", "Dolphins", "Patriots", "Bills", "Broncos", "Chiefs",
    "Chargers", "Raiders", "Jets", "Giants", "Eagles", "Bears", "Vikings",
    "Saints", "Falcons", "Panthers", "Buccaneers", "Rams", "Texans", "Colts",
    "Titans", "Jaguars", "Ravens", "Steelers",
]
NFL = {
    f"NFL: {a} vs. {b} Season Series Winner"
    for a, b in zip(_CLUBS[0::2], _CLUBS[1::2])
} | {
    f"NFL: {a} vs. {b} Season Series Winner"
    for a, b in zip(_CLUBS[1::2], _CLUBS[2::2])
}
MATCHUP = "MLB Championship Series Matchup"


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
    rows = (
        [(n, "baseball", 100.0) for n in sorted(LCS | DIVISION)]
        + [(MATCHUP, "baseball", 5_000.0)]
        + [(n, "football", 250_000.0) for n in sorted(NFL)]
    )
    session_maker = async_sessionmaker(engine, expire_on_commit=False)
    async with session_maker() as session:
        for i, (name, category, volume) in enumerate(rows):
            market = FuturesMarket(
                source="kalshi", external_id=f"lcs-lead-{i}", name=name,
                status="open", resolution_date=now + timedelta(days=20),
                llm_sport_category=category, volume=volume,
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


def _leads_with(names: list[str], lead: set[str]) -> bool:
    return bool(names) and set(names[: len(lead)]) == lead


@pytest.mark.parametrize(
    "q", ["championship series", "Championship Series", "mlb championship series"]
)
async def test_search_leads_with_the_lcs_markets(get, q):
    futures = _search_futures(await get("search", q))
    assert _leads_with(futures, LCS), f"{q!r} served {futures[:6]}"


async def test_the_dropdown_leads_with_them_too(get):
    texts = _typeahead_futures(await get("typeahead", "championship series"))
    served = [t for t in texts if t in LCS]
    assert served and texts[: len(served)] == served, f"dropdown led with {texts[:4]}"


async def test_division_series_still_leads_with_its_round(get):
    futures = _search_futures(await get("search", "division series"))
    assert _leads_with(futures, DIVISION), futures[:6]


async def test_control_season_series_winner_is_the_nfl_boards(get):
    futures = _search_futures(await get("search", "season series winner"))
    assert futures and futures[0] in NFL and not set(futures) & LCS, futures[:6]


async def test_strawman_without_the_lead_rule_the_nfl_boards_take_the_page(
    get, monkeypatch
):
    """The seed reproduces production: disarm the rule and NFL leads."""
    from app.routes import events as events_module

    monkeypatch.setattr(events_module, "_POSTSEASON_NAMED_ROUNDS", {})
    futures = _search_futures(await get("search", "championship series"))
    assert futures and futures[0] not in LCS, futures[:6]
    assert set(futures[:5]) & NFL, futures[:6]
