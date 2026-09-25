"""#5082 — a team query's dropdown, out of the REAL route against REAL Postgres.

Production 2026-09-25 05:25Z (`x-bainluck-origin: agent-latency`):

    /typeahead?q=pats   5-7  TX-04 / NC-10 / NY-18 House election: Pat ... vote percent
    /typeahead?q=dodg   2    Will Dodge release a new Challenger Hellcat before 2027?

`tests/test_typeahead_team_query_cross_sport_5082.py` pins the two helpers and
the call's AST. What neither can see is that the route hands them the right
inputs from a live pool: that the english stemmer really admits `Pat Fallon` for
`pats` (it runs nowhere but PostgreSQL), that `team_pool` really carries the
Dodgers' `sport_key`, and that the demotion survives the scorer and the slice.
So this file drives the route.

    1. `pats` offers the Patriots' market and no House race     the stem gate
    2. `dodg` offers the Dodgers' markets ABOVE the Hellcat     the sport demotion
    3. the Hellcat is still in the pool for `dodg`              demote, not remove
    4. the House race IS in the pool when no team resolves it   the seed is not vacuous
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
            "set SEARCH_TEST_DATABASE_URL to run the #5082 real-Postgres typeahead "
            "control (CI job `search-recall` provides one)"
        ),
    ),
    pytest.mark.asyncio,
]

PATRIOTS = "New England Patriots"
DODGERS = "Los Angeles Dodgers"
HOUSE = "TX-04 House election: Pat Fallon vote percent"
HELLCAT = "Will Dodge release a new Challenger Hellcat before 2027?"
PATS_OWN = "Will the New England Patriots make the 2027 NFL Playoffs?"
DODGERS_OWN = (
    "Los Angeles Dodgers vs. San Francisco Giants",
    "Los Angeles Dodgers vs. San Francisco Giants - 2nd Inning Winner",
)


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


async def _seed(session):
    """Two teams, and for each its own market plus the cross-category row."""
    from sqlalchemy import text

    now = datetime.now(timezone.utc)

    async def _sport(key, name):
        return (
            await session.execute(
                text(
                    "INSERT INTO sports (key, name, active) VALUES (:k, :n, TRUE) "
                    "RETURNING id"
                ),
                {"k": key, "n": name},
            )
        ).scalar()

    nfl = await _sport("americanfootball_nfl", "NFL")
    mlb = await _sport("baseball_mlb", "MLB")
    # `alternate_names` as production stores them (read 2026-09-25): `pats`
    # resolves the Patriots through that alias, never through the name, and
    # without it no lead team exists and neither gate can open.
    for sid, name, abbr, alts in (
        (nfl, PATRIOTS, "NE", '["pats", "Patriots"]'),
        (mlb, DODGERS, "LAD", '["Los Angeles", "Dodgers"]'),
    ):
        await session.execute(
            text(
                "INSERT INTO teams (sport_id, name, abbreviation, alternate_names) "
                "VALUES (:sid, :n, :a, CAST(:alts AS JSONB))"
            ),
            {"sid": sid, "n": name, "a": abbr, "alts": alts},
        )

    async def _market(name, category, tier, xid, *outcomes):
        mid = (
            await session.execute(
                text(
                    """
                    INSERT INTO futures_markets
                        (name, source, category, mutually_exclusive, status,
                         resolution_date, external_id, llm_sport_category,
                         market_tier)
                    VALUES (:n, 'kalshi', 'prop', FALSE, 'open', :rd, :xid,
                            :cat, :tier)
                    RETURNING id
                    """
                ),
                {
                    "n": name,
                    "rd": now + timedelta(days=30),
                    "xid": xid,
                    "cat": category,
                    "tier": tier,
                },
            )
        ).scalar()
        for j, o in enumerate(outcomes):
            await session.execute(
                text(
                    "INSERT INTO futures_outcomes (market_id, external_id, name, "
                    "current_probability, last_updated) "
                    "VALUES (:m, :x, :n, 0.5, :now)"
                ),
                {"m": mid, "x": f"{xid}-{j}", "n": o, "now": now},
            )
        return mid

    ids = {
        HOUSE: await _market(HOUSE, "politics", 2, "PGX-5082-H", "At least 60%"),
        PATS_OWN: await _market(PATS_OWN, "football", 1, "PGX-5082-P", "Yes", "No"),
        HELLCAT: await _market(HELLCAT, "auto", 5, "PGX-5082-C", "Yes", "No"),
    }
    for i, name in enumerate(DODGERS_OWN):
        ids[name] = await _market(
            name, "baseball", 1, f"PGX-5082-D{i}", DODGERS, "San Francisco Giants"
        )
    await session.commit()
    return ids


async def _payload(session, q, debug_evidence=False):
    from app.routes.events import typeahead_search

    return await typeahead_search(
        q=q,
        debug_evidence=debug_evidence,
        debug_timing=False,
        db=session,
        request=None,
    )


def _texts(rows):
    return [r.get("text") for r in rows]


class TestATeamQuerysDropdown:
    async def test_pats_offers_the_patriots_and_no_house_race(self, pg_session, _no_redis):
        await _seed(pg_session)
        texts = _texts((await _payload(pg_session, "pats"))["suggestions"])
        assert PATS_OWN in texts, texts
        assert HOUSE not in texts, texts

    async def test_dodg_ranks_the_dodgers_markets_above_the_hellcat(
        self, pg_session, _no_redis
    ):
        await _seed(pg_session)
        texts = _texts((await _payload(pg_session, "dodg"))["suggestions"])
        own = [texts.index(n) for n in DODGERS_OWN if n in texts]
        assert own, texts
        if HELLCAT in texts:
            assert max(own) < texts.index(HELLCAT), texts

    async def test_dodg_still_holds_the_hellcat_in_its_pool(self, pg_session, _no_redis):
        # Demote, not remove: with only three futures in the pool the Hellcat
        # keeps a visible slot, below the Dodgers.
        await _seed(pg_session)
        texts = _texts((await _payload(pg_session, "dodg"))["suggestions"])
        assert HELLCAT in texts, texts

    async def test_the_house_race_is_reachable_when_no_team_is_named(
        self, pg_session, _no_redis
    ):
        # The anti-vacuity control: the stemmer really does admit `Pat Fallon`
        # to this pool, so its absence above is the gate's doing.
        await _seed(pg_session)
        texts = _texts((await _payload(pg_session, "pat fallon"))["suggestions"])
        assert HOUSE in texts, texts
