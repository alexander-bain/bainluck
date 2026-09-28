"""#9444 — the dropdown asks the search page's same-question fold, out of the REAL route against REAL Postgres.

Production 2026-09-28 ~19:00Z, `oscars` typed into the search box at 390px:

    Oscars 2027: Best Picture Winner   The Odyssey 49% · La Bola Negra 23%    polymarket 57313556
    Oscar Winner: Best Picture         The Odyssey 49% · The Black Ball 27%   kalshi 6173044

One question, two rows. `/api/events/search?q=oscars` served Best Picture once:
#8851's fold (`_search_same_question_folded_ids`) runs there as a post-pass over
the page, and #9404 gave the dropdown only the per-row `_admit_search_future`.

`tests/test_search_folds_the_same_question_8851.py` pins the fold on these rows.
What it cannot see is whether `typeahead_search` asks it — so this file drives
the route.

    1. `oscars` offers one Best Picture row, and Best Actor still     the fix
    2. the Kalshi board IS offered when it is the only one            not vacuous
    3. two categories of one ceremony stay two rows                   the control
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import pytest

from tests.integration.test_typeahead_final_seven_route_control_pg import _FakeRedis

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

pytestmark = [
    pytest.mark.skipif(
        not DB_URL,
        reason=(
            "set SEARCH_TEST_DATABASE_URL to run the #9444 real-Postgres typeahead "
            "control (CI job `search-recall` provides one)"
        ),
    ),
    pytest.mark.asyncio,
]

# (name, source, legs) — the production rows' titles and top five, read 2026-09-26/28.
PICTURE_POLY = ("Oscars 2027: Best Picture Winner", "polymarket", (
    ("The Odyssey", 0.49), ("La Bola Negra", 0.245), ("Dune: Part Three", 0.105),
    ("Wild Horse Nine", 0.036), ("The Debut", 0.02),
))
PICTURE_KALSHI = ("Oscar Winner: Best Picture", "kalshi", (
    ("The Odyssey", 0.485), ("The Black Ball", 0.265), ("Dune: Part Three", 0.105),
    ("Wild Horse Nine", 0.035), ("The Debut", 0.025),
))
ACTOR_KALSHI = ("Oscar Winner: Best Actor", "kalshi", (
    ("John Malkovich", 0.315), ("Matt Damon", 0.255), ("Andrew Scott", 0.185),
    ("Tom Cruise", 0.125), ("Robert Pattison", 0.105),
))


@pytest.fixture
def _no_redis(monkeypatch):
    client = _FakeRedis()
    monkeypatch.setattr(
        "app.tasks.redis_state.get_redis_client", lambda *a, **k: client
    )
    return client


@pytest.fixture
async def pg_session():
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
        yield session

    await engine.dispose()


async def _seed(session, *rows):
    """Each row an open entertainment board with priced outcomes; returns name -> id.

    Seeded in argument order, so the first row gets the lower id and the higher
    volume: the route's own ranking leads with it, as production led with the
    Polymarket board.
    """
    from sqlalchemy import text

    now = datetime.now(timezone.utc)
    ids = {}
    for i, (name, source, legs) in enumerate(rows):
        mid = (
            await session.execute(
                text(
                    """
                    INSERT INTO futures_markets
                        (name, source, category, mutually_exclusive, status,
                         resolution_date, external_id, llm_sport_category,
                         market_tier, volume)
                    VALUES (:n, :src, 'entertainment', TRUE, 'open', :rd, :xid,
                            'entertainment', 2, :vol)
                    RETURNING id
                    """
                ),
                {
                    "n": name,
                    "src": source,
                    "rd": now + timedelta(days=200),
                    "xid": f"PGX-9444-{i}",
                    "vol": 900_000 - 100_000 * i,
                },
            )
        ).scalar()
        for j, (o, p) in enumerate(legs):
            await session.execute(
                text(
                    "INSERT INTO futures_outcomes (market_id, external_id, name, "
                    "current_probability, last_updated) "
                    "VALUES (:m, :x, :n, :p, :now)"
                ),
                {"m": mid, "x": f"PGX-9444-{i}-{j}", "n": o, "p": p, "now": now},
            )
        ids[name] = mid
    await session.commit()
    return ids


async def _market_ids(session, q):
    from app.routes.events import typeahead_search

    body = await typeahead_search(
        q=q, debug_evidence=False, debug_timing=False, db=session, request=None
    )
    return [r.get("market_id") for r in body["suggestions"] if r.get("type") == "futures"]


class TestTheDropdownFoldsTheSameQuestion:
    async def test_oscars_offers_best_picture_once(self, pg_session, _no_redis):
        ids = await _seed(pg_session, PICTURE_POLY, PICTURE_KALSHI, ACTOR_KALSHI)
        got = await _market_ids(pg_session, "oscars")
        picture = [m for m in got if m in (ids[PICTURE_POLY[0]], ids[PICTURE_KALSHI[0]])]
        assert len(picture) == 1, got
        assert ids[ACTOR_KALSHI[0]] in got, got

    async def test_the_kalshi_board_is_offered_when_it_is_the_only_one(
        self, pg_session, _no_redis
    ):
        # Anti-vacuity: the route really reaches the Kalshi row for this query,
        # so its absence above is the fold's doing, not recall's.
        ids = await _seed(pg_session, PICTURE_KALSHI)
        got = await _market_ids(pg_session, "oscars")
        assert ids[PICTURE_KALSHI[0]] in got, got

    async def test_two_categories_of_one_ceremony_stay_two_rows(
        self, pg_session, _no_redis
    ):
        # Control: Picture and Actor share a ceremony, a venue family and a title
        # shape, and list no one in common — two questions.
        poly_actor = ("Oscars 2027: Best Actor Winner", "polymarket", ACTOR_KALSHI[2])
        ids = await _seed(pg_session, PICTURE_POLY, poly_actor)
        got = await _market_ids(pg_session, "oscars")
        assert ids[PICTURE_POLY[0]] in got, got
        assert ids[poly_actor[0]] in got, got
