"""#7345 — the same-instant refutation, against a real PostgreSQL.

The verdict is two LATERAL joins keyed on exact `commence_time` equality and
team-id arithmetic with NULL-false `<>`; a recording session cannot run any of
it. The production specimen (Arkansas State v South Alabama, 2026-09-12 23:00Z,
refuted by 15309107 and 15304849) is the first case; every other case is one
clause made false, so each arm of the SQL is shown to be load-bearing.

Narrow `events` + `futures_markets` tables in a private schema, so this runs on
the lane VM's Postgres 14 as well as in CI. Kick-offs are dated from the
SERVER's clock (`now() - interval`), because the verdict carries
`commence_time < :now` and a literal date would go vacuous the other way.
"""

import os
from types import SimpleNamespace

import pytest
from sqlalchemy import text

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not DB_URL,
        reason=(
            "set SEARCH_TEST_DATABASE_URL to run the real-Postgres #7345 "
            "same-instant refutation gate (CI job: search-recall)"
        ),
    ),
]

_SCHEMA = "same_instant_refutation_gate_7345"

ARST, USA, UWG, TULANE = 15330, 17178, 17109, 15305
PHANTOM, ARST_FINAL, USA_FINAL = 15306765, 15309107, 15304849


@pytest.fixture
async def pg():
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    engine = create_async_engine(
        DB_URL, connect_args={"server_settings": {"search_path": _SCHEMA}}
    )
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        await s.execute(text(f"DROP SCHEMA IF EXISTS {_SCHEMA} CASCADE"))
        await s.execute(text(f"CREATE SCHEMA {_SCHEMA}"))
        await s.execute(
            text(
                f"CREATE TABLE {_SCHEMA}.events (id bigint PRIMARY KEY, "
                "sport_id int NOT NULL, home_team_id int, away_team_id int, "
                "home_team_name varchar(200) NOT NULL, "
                "away_team_name varchar(200) NOT NULL, "
                "commence_time timestamptz NOT NULL, status varchar(20) NOT NULL, "
                "home_score int, away_score int, completed_at timestamptz, "
                "espn_id varchar(50), statpal_fixture_id varchar(100))"
            )
        )
        await s.execute(
            text(
                f"CREATE TABLE {_SCHEMA}.futures_markets (id bigint PRIMARY KEY, "
                "event_id bigint, source varchar(20) NOT NULL, "
                "external_id varchar(200) NOT NULL, name varchar(500) NOT NULL, "
                "category varchar(50) NOT NULL, status varchar(20) NOT NULL, "
                "mutually_exclusive boolean NOT NULL)"
            )
        )
        await s.commit()
        yield s
        await s.rollback()
        await s.execute(text(f"DROP SCHEMA IF EXISTS {_SCHEMA} CASCADE"))
        await s.commit()
    await engine.dispose()


async def _row(s, rid, home, away, *, minutes_ago=13 * 24 * 60, status="completed",
               score=(1, 0), espn=None, statpal=None, completed=True):
    await s.execute(
        text(
            "INSERT INTO events (id, sport_id, home_team_id, away_team_id, "
            "home_team_name, away_team_name, commence_time, status, home_score, "
            "away_score, completed_at, espn_id, statpal_fixture_id) VALUES "
            "(:id, 760, :h, :a, 'H', 'A', "
            "date_trunc('minute', now()) - make_interval(mins => :m), :st, :hs, :as_, "
            "CASE WHEN :c THEN now() ELSE NULL END, :e, :sp)"
        ),
        {
            "id": rid, "h": home, "a": away, "m": minutes_ago, "st": status,
            "hs": score[0] if score else None, "as_": score[1] if score else None,
            "c": completed, "e": espn, "sp": statpal,
        },
    )


async def _phantom(s, **kw):
    kw.setdefault("status", "suspended")
    kw.setdefault("score", None)
    kw.setdefault("completed", False)
    await _row(s, PHANTOM, ARST, USA, **kw)


async def _refuters(s, **kw):
    await _row(s, ARST_FINAL, ARST, UWG, score=(52, 7), espn="401868241", **kw)
    await _row(s, USA_FINAL, TULANE, USA, score=(28, 24), espn="401864575")


async def _verdict(s):
    from app.services.same_instant_refutation import same_instant_refuted_on_page

    got = await s.execute(
        text(
            "SELECT id, home_team_id, away_team_id, commence_time, home_score, "
            "away_score, completed_at, espn_id, statpal_fixture_id FROM events"
        )
    )
    rows = [SimpleNamespace(**r._mapping) for r in got]
    return await same_instant_refuted_on_page(s, rows)


class TestTheSpecimen:
    async def test_the_phantom_is_refuted_by_both_teams_finals(self, pg):
        await _phantom(pg)
        await _refuters(pg)
        assert await _verdict(pg) == {PHANTOM: (ARST_FINAL, USA_FINAL)}

    async def test_the_refuters_themselves_are_never_candidates(self, pg):
        await _refuters(pg)
        assert await _verdict(pg) == {}


class TestEachClauseIsLoadBearing:
    async def test_only_one_team_elsewhere_refutes_nothing(self, pg):
        await _phantom(pg)
        await _row(pg, ARST_FINAL, ARST, UWG, score=(52, 7), espn="401868241")
        assert await _verdict(pg) == {}

    async def test_the_real_game_reversed_never_refutes_it(self, pg):
        # South Alabama v Arkansas State at the same instant, ESPN-linked: this
        # is the game itself, oriented the other way. It names each side's
        # OWN opponent, so neither lateral may take it.
        await _phantom(pg)
        await _row(pg, ARST_FINAL, USA, ARST, score=(10, 3), espn="401869933")
        assert await _verdict(pg) == {}

    async def test_a_refuter_one_minute_off_refutes_nothing(self, pg):
        await _phantom(pg)
        await _refuters(pg, minutes_ago=13 * 24 * 60 - 1)
        assert await _verdict(pg) == {}

    async def test_a_refuter_without_an_espn_id_refutes_nothing(self, pg):
        await _phantom(pg)
        await _row(pg, ARST_FINAL, ARST, UWG, score=(52, 7), espn="")
        await _row(pg, USA_FINAL, TULANE, USA, score=(28, 24), espn="401864575")
        assert await _verdict(pg) == {}

    async def test_a_live_refuter_refutes_nothing(self, pg):
        await _phantom(pg)
        await _row(pg, ARST_FINAL, ARST, UWG, status="live", score=(52, 7),
                   espn="401868241", completed=False)
        await _row(pg, USA_FINAL, TULANE, USA, score=(28, 24), espn="401864575")
        assert await _verdict(pg) == {}

    async def test_a_listing_holding_a_market_is_never_hidden(self, pg):
        await _phantom(pg)
        await _refuters(pg)
        await pg.execute(
            text(
                "INSERT INTO futures_markets (id, event_id, source, external_id, "
                "name, category, status, mutually_exclusive) VALUES "
                "(1, :e, 'polymarket', 'x', 'Arkansas State v South Alabama', "
                "'game', 'open', true)"
            ),
            {"e": PHANTOM},
        )
        assert await _verdict(pg) == {}

    async def test_an_id_held_listing_is_the_registrys_not_this(self, pg):
        await _phantom(pg, statpal="99887766")
        await _refuters(pg)
        assert await _verdict(pg) == {}

    async def test_a_listing_with_a_score_is_never_hidden(self, pg):
        await _phantom(pg, score=(0, 0))
        await _refuters(pg)
        assert await _verdict(pg) == {}

    async def test_a_future_listing_is_not_asked_about(self, pg):
        await _phantom(pg, minutes_ago=-60)
        await _refuters(pg, minutes_ago=-60)
        assert await _verdict(pg) == {}
