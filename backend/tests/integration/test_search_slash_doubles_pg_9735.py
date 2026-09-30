"""#9735 — searching one player of a doubles pair finds the pair's match.

THE DEFECT, measured on production 2026-09-30 05:04Z: ``q=Winegar`` served 0
games while 15321506 *Rojer/Winegar v Stevenson/Willis* was live, and
``q=Bolelli`` served two settled US Open cards but not Thursday's Tokyo match
15321376 *Bolelli/Vavassori v Mochizuki/Watanabe*. 93 rows in the ±10-day
window are spelled ``A/B`` with no spaces (17 live).

THE CAUSE is the parser, not the data. ``_event_name_match`` ANDs a whole-word
``to_tsvector`` test onto the substring ILIKE (LAT-P034), and Postgres reads an
unspaced ``Rojer/Winegar`` as ONE ``file`` token::

    to_tsvector('simple','Rojer/Winegar')       -> 'rojer/winegar':1
    to_tsvector('simple','Bolelli / Vavassori') -> 'bolelli':1 'vavassori':2

so the ILIKE found the row and the word test threw it away. The Kalshi-minted
rows are spelled ``A / B`` and were always searchable — they are the CONTROL.

WHY POSTGRES AND WHY THE ROUTE. The tokeniser is the whole defect; SQLite has
none, and a helper-level test would pass against a predicate the route may not
build (#5821's lesson, quoted in ``test_search_diacritic_fold_pg_6977``). Every
case drives ``GET /api/events/search`` over a real database.

THE WORD TEST MUST SURVIVE. The fix gives the test a split reading; it must not
turn the test into a substring match. ``fed`` inside ``Fedorova/Smith`` is the
LAT-P034 class (``fed`` -> Federico) wearing a slash, and it stays out.
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
            "set SEARCH_TEST_DATABASE_URL to run the real-Postgres slash-doubles "
            "contract (CI job `search-recall` provides one)"
        ),
    ),
]

# ── The specimens, transcribed from production ──────────────────────────────
LIVE_UNSPACED = ("Rojer/Winegar", "Stevenson/Willis", "live")
THURSDAY_UNSPACED = ("Bolelli/Vavassori", "Mochizuki/Watanabe", "scheduled")
#: Kalshi's spelling of the same pair — searchable before the fix.
SPACED_CONTROL = ("Bolelli / Vavassori", "Harrison / Skupski", "scheduled")
#: A prefix of a player's surname, not a player: LAT-P034 keeps it out.
PREFIX_NOISE = ("Fedorova/Smith", "Jones/Brown", "scheduled")


@pytest.fixture
async def maker():
    """A clean schema and a sessionmaker, per test (`drop_all` first: shared DB)."""
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    import app.models.models  # noqa: F401 — registers every table on Base
    from app.services.database import Base

    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    yield async_sessionmaker(engine, expire_on_commit=False)

    await engine.dispose()


@pytest.fixture
async def search(maker):
    """`GET /api/events/search` against the real app and the real database.

    Redis is patched to raise so the LAT-P090 response cache cannot serve one
    case's answer to the next; both routes treat a raising client as a miss.
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

            async def _search(q: str) -> dict:
                resp = await http.get("/api/events/search", params={"q": q})
                assert resp.status_code == 200, f"search {q!r} -> {resp.status_code}"
                return resp.json()

            yield _search

    app.dependency_overrides.clear()


async def _seed(session):
    """Four doubles fixtures on one tour. Kickoffs are RELATIVE (gotcha #44)."""
    from app.models.models import Event, Sport

    now = datetime.now(timezone.utc)
    tour = Sport(key="tennis_other", name="Tennis")
    session.add(tour)
    await session.flush()

    for hours, (home, away, status) in enumerate(
        (LIVE_UNSPACED, THURSDAY_UNSPACED, SPACED_CONTROL, PREFIX_NOISE), start=1
    ):
        session.add(
            Event(
                sport_id=tour.id,
                home_team_name=home,
                away_team_name=away,
                commence_time=now + timedelta(hours=hours * 6 - 8),
                status=status,
                event_tags=["provenance:source:statpal"],
            )
        )
    await session.commit()


def _homes(payload) -> set[str]:
    """Home names of the game cards. The key is `results`, asserted present."""
    assert "results" in payload, f"no `results` key; got {sorted(payload)}"
    return {e["home_team"] for e in payload["results"]}


async def test_one_player_finds_the_live_unspaced_pair(maker, search):
    """The live specimen: `Winegar` served 0 games on production."""
    async with maker() as session:
        await _seed(session)

    assert LIVE_UNSPACED[0] in _homes(await search("Winegar"))


async def test_the_away_pair_is_searchable_too(maker, search):
    """The away name gets the same split — `Molteni` missed live 15321505."""
    async with maker() as session:
        await _seed(session)

    assert LIVE_UNSPACED[0] in _homes(await search("Stevenson"))


async def test_one_player_finds_both_spellings_of_the_pair(maker, search):
    """`Bolelli`: the unspaced Thursday row joins the spaced control."""
    async with maker() as session:
        await _seed(session)

    homes = _homes(await search("Bolelli"))
    assert SPACED_CONTROL[0] in homes, "control: the spaced row always matched"
    assert THURSDAY_UNSPACED[0] in homes


async def test_both_players_find_the_pair(maker, search):
    """Two terms, each ANDed through its own word test (one arm per term)."""
    async with maker() as session:
        await _seed(session)

    assert LIVE_UNSPACED[0] in _homes(await search("rojer winegar"))


async def test_the_pair_typed_as_stored_still_matches(maker, search):
    """The unsplit arm is kept: `rojer/winegar` is one token on both sides."""
    async with maker() as session:
        await _seed(session)

    assert LIVE_UNSPACED[0] in _homes(await search("rojer/winegar"))


async def test_a_surname_prefix_is_still_not_a_player(maker, search):
    """LAT-P034 holds through the split: `fed` is spelled inside Fedorova only."""
    async with maker() as session:
        await _seed(session)

    assert PREFIX_NOISE[0] not in _homes(await search("fed"))
    assert PREFIX_NOISE[0] in _homes(await search("Fedorova")), (
        "control: the row is reachable by the whole word, so the refusal above "
        "is the word test and not a missing row"
    )


async def test_the_unspaced_pair_ranks_like_the_spaced_one(maker):
    """The rank vector gets the split too, and only where it is missing.

    Without it the unspaced row ranks 0.0 against the spaced row's 1.0 and sinks
    under every word hit. Splitting a SPACED name again would count each player
    twice (2.0 vs 1.0, measured on production) — so the two must tie exactly.
    A rank read, not a route read: the page's order is also shaped by status and
    kickoff, which would make a position assertion about something else.
    """
    from sqlalchemy import func, select

    from app.models.models import Event
    from app.routes.events import _event_search_vector, _search_tsquery

    async with maker() as session:
        await _seed(session)
        rank = func.ts_rank_cd(_event_search_vector(), _search_tsquery("Bolelli"))
        rows = dict(
            (await session.execute(select(Event.home_team_name, rank))).all()
        )

    assert rows[THURSDAY_UNSPACED[0]] > 0
    assert rows[THURSDAY_UNSPACED[0]] == rows[SPACED_CONTROL[0]]
    assert rows[LIVE_UNSPACED[0]] == 0, "control: a row not naming Bolelli"
