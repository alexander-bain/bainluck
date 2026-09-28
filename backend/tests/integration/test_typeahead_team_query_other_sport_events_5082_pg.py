"""#5082 (event half) — a team nickname's dropdown, out of the REAL route against REAL Postgres.

Production 2026-09-28 21:4xZ, `GET /api/events/typeahead`:

    q=pats     row 7   Tamara Korpatsch at Taylah Preston      (tennis_wta_china_open)
    q=niners   row 2   Niners Chemnitz at Tofas SK Bursa       (basketball_other), above
               row 3   Denver Broncos at San Francisco 49ers   (the 49ers' own game)
    q=phins    row 7   Diamond Dolphins at Shimane Susanoo Magic (basketball_other)

`pats` is inside Kor·pats·ch: the event name arm matches `%pats%` anywhere, and
`_typeahead_stem_only_event` keeps every substring row on purpose. The other
two are real namesakes in another sport; the query named an NFL team.

    1. `pats` offers the Patriots' game and no Korpatsch match       infix drop
    2. `pats` still offers Korpatsch when the reader types her name   the seed is not vacuous
    3. `niners` ranks the 49ers' game above Niners Chemnitz           other-sport demotion
    4. `niners` still holds Niners Chemnitz                           demote, not remove
    5. `phins` ranks the Dolphins' game above Diamond Dolphins
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
            "event control (CI job `search-recall` provides one)"
        ),
    ),
    pytest.mark.asyncio,
]

PATRIOTS = "New England Patriots"
NINERS = "San Francisco 49ers"
DOLPHINS = "Miami Dolphins"

PATS_GAME = f"{PATRIOTS} at Buffalo Bills"
KORPATSCH = "Tamara Korpatsch at Taylah Preston"
NINERS_GAME = f"Denver Broncos at {NINERS}"
CHEMNITZ = "Niners Chemnitz at Tofas SK Bursa"
DOLPHINS_GAME = f"{DOLPHINS} at Minnesota Vikings"
DIAMOND = "Diamond Dolphins at Shimane Susanoo Magic"


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
    """Three NFL teams with their next game, and each one's other-sport lookalike.

    Every lookalike starts SOONER than the NFL game, as on production: the event
    fetch is ordered by start time, so the lookalike leads unless something
    ranks the team's own game first.
    """
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
    wta = await _sport("tennis_wta_china_open", "WTA China Open")
    bball = await _sport("basketball_other", "Basketball")

    # `alternate_names` as production stores them (read 2026-09-28).
    teams = {}
    for name, abbr, alts in (
        (PATRIOTS, "NE", '["Patriots", "pats"]'),
        (NINERS, "SF", '["9ers", "49ers", "niners"]'),
        (DOLPHINS, "MIA", '["Dolphins", "phins", "fins"]'),
    ):
        teams[name] = (
            await session.execute(
                text(
                    "INSERT INTO teams (sport_id, name, abbreviation, alternate_names) "
                    "VALUES (:sid, :n, :a, CAST(:alts AS JSONB)) RETURNING id"
                ),
                {"sid": nfl, "n": name, "a": abbr, "alts": alts},
            )
        ).scalar()

    async def _event(sid, away, home, days, home_id=None, away_id=None):
        await session.execute(
            text(
                """
                INSERT INTO events
                    (sport_id, home_team_name, away_team_name, home_team_id,
                     away_team_id, commence_time, status)
                VALUES (:sid, :home, :away, :hid, :aid, :ct, 'scheduled')
                """
            ),
            {
                "sid": sid,
                "home": home,
                "away": away,
                "hid": home_id,
                "aid": away_id,
                "ct": now + timedelta(days=days),
            },
        )

    await _event(nfl, PATRIOTS, "Buffalo Bills", 6, away_id=teams[PATRIOTS])
    await _event(nfl, "Denver Broncos", NINERS, 6, home_id=teams[NINERS])
    await _event(nfl, DOLPHINS, "Minnesota Vikings", 6, away_id=teams[DOLPHINS])
    await _event(wta, "Tamara Korpatsch", "Taylah Preston", 1)
    await _event(bball, "Niners Chemnitz", "Tofas SK Bursa", 1)
    await _event(bball, "Diamond Dolphins", "Shimane Susanoo Magic", 4)
    await session.commit()


async def _texts(session, q):
    from app.routes.events import typeahead_search

    payload = await typeahead_search(
        q=q, debug_evidence=False, debug_timing=False, db=session, request=None
    )
    return [r.get("text") for r in payload["suggestions"]]


class TestATeamNicknamesDropdownEvents:
    async def test_pats_offers_the_patriots_game_and_no_korpatsch_match(
        self, pg_session, _no_redis
    ):
        await _seed(pg_session)
        texts = await _texts(pg_session, "pats")
        assert PATS_GAME in texts, texts
        assert KORPATSCH not in texts, texts

    async def test_korpatsch_is_reachable_by_her_own_name(self, pg_session, _no_redis):
        # The anti-vacuity control: the seeded match is servable, so its
        # absence above is the drop's doing and not a broken seed.
        await _seed(pg_session)
        texts = await _texts(pg_session, "korpatsch")
        assert KORPATSCH in texts, texts

    async def test_niners_ranks_the_49ers_game_above_niners_chemnitz(
        self, pg_session, _no_redis
    ):
        await _seed(pg_session)
        texts = await _texts(pg_session, "niners")
        assert NINERS_GAME in texts, texts
        if CHEMNITZ in texts:
            assert texts.index(NINERS_GAME) < texts.index(CHEMNITZ), texts

    async def test_niners_still_holds_niners_chemnitz(self, pg_session, _no_redis):
        # Demote, not remove: Niners Chemnitz really is called that, and with
        # only two games in the pool it keeps a visible slot.
        await _seed(pg_session)
        texts = await _texts(pg_session, "niners")
        assert CHEMNITZ in texts, texts

    async def test_phins_ranks_the_dolphins_game_above_diamond_dolphins(
        self, pg_session, _no_redis
    ):
        await _seed(pg_session)
        texts = await _texts(pg_session, "phins")
        assert DOLPHINS_GAME in texts, texts
        if DIAMOND in texts:
            assert texts.index(DOLPHINS_GAME) < texts.index(DIAMOND), texts
