"""#9017's attended repair against a REAL PostgreSQL — CERT-3604's follow-up.

**SHIP: searching "miami hurricanes" stops showing Miami (OH) wearing the
Hurricanes' crest and record** (Pillar: TRUTH). This file is how that repair's
write is trusted; it is not a ship of its own.

## what it proves

CERT-3604 granted the repair and asked for two guards on its apply
(`9017-REPAIR-APPLY-CARDINALITY-CAS`): a population ceiling, and a
stored-identity compare-and-set. The ceiling is pure Python and lives in the
unit file. The CAS is a claim about PostgreSQL — an `UPDATE ... FROM unnest(...)`
that must clear a row only while it still holds the `espn_id` AND `name` the
plan judged. Under a double that is just a string, so it is run here, through
the script's own `run()`, end to end: plan, backup, apply, read back, undo.

ESPN sync writes `teams` every few minutes on the same app, so the race is real:
the fake directory fetch — which runs between the candidate read and the write,
exactly where the script awaits ESPN — re-enriches one row with its own club's
id and renames another. Both must be left alone and reported; the untouched
foreign row must be cleared; the owner row must not move; and the undo must put
the cleared row back byte for byte.
"""

import argparse
import json
import os
from contextlib import asynccontextmanager

import pytest
from sqlalchemy import text

from scripts.repair_9017_foreign_espn_id import BACKUP_TABLE

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

needs_postgres = pytest.mark.skipif(
    not DB_URL,
    reason=(
        "set SEARCH_TEST_DATABASE_URL to run the real-Postgres #9017 apply CAS "
        "(CI job `search-recall` provides one)"
    ),
)


def _team(espn_id, display_name, name, short_name, location):
    from app.services.espn_api import ESPNTeam

    return ESPNTeam(
        espn_id=espn_id,
        name=name,
        abbreviation=None,
        display_name=display_name,
        short_name=short_name,
        nickname=short_name,
        primary_color=None,
        secondary_color=None,
        logo_url=None,
        logo_url_dark=None,
        record=None,
        location=location,
    )


#: ESPN's college-baseball directory as it answered on 2026-09-27 (subset).
DIRECTORY = [
    _team("176", "Miami Hurricanes", "Hurricanes", "Miami", "Miami"),
    _team("107", "Miami (OH) RedHawks", "RedHawks", "Miami OH", "Miami (OH)"),
    _team("126", "Texas Longhorns", "Longhorns", "Texas", "Texas"),
    _team("147", "Texas State Bobcats", "Bobcats", "Texas St", "Texas State"),
    _team("75", "Florida Gators", "Gators", "Florida", "Florida"),
    _team("296", "North Florida Ospreys", "Ospreys", "North Florida", "North Florida"),
]

#: (name, espn_id, current_record) — the production shapes.
SEED = {
    "miami_oh": ("Miami (OH)", "176", "35-15"),  # foreign, untouched mid-run
    "texas_state": ("Texas State", "126", "30-20"),  # foreign, re-enriched mid-run
    "north_florida": ("North Florida", "75", "28-22"),  # foreign, renamed mid-run
    "hurricanes": ("Miami Hurricanes", "176", "35-15"),  # the owner: never judged
}


@pytest.fixture
async def pg_engine():
    """Real Postgres with the real schema (function-scoped; see #6215's gate)."""
    from sqlalchemy.ext.asyncio import create_async_engine

    import app.models.models  # noqa: F401 — registers every table on Base
    from app.services.database import Base

    engine = create_async_engine(DB_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text(f"DROP TABLE IF EXISTS {BACKUP_TABLE}"))

    yield engine

    async with engine.begin() as conn:
        await conn.execute(text(f"DROP TABLE IF EXISTS {BACKUP_TABLE}"))
    await engine.dispose()


async def _seed(engine) -> dict:
    ids = {}
    async with engine.begin() as conn:
        sport_id = (
            await conn.execute(
                text(
                    "INSERT INTO sports (key, name, active) "
                    "VALUES ('baseball_ncaa', 'NCAA Baseball', true) RETURNING id"
                )
            )
        ).scalar_one()
        for key, (name, espn_id, record) in SEED.items():
            ids[key] = (
                await conn.execute(
                    text(
                        "INSERT INTO teams (name, sport_id, espn_id, current_record,"
                        " logo_url_small, alternate_names) "
                        "VALUES (:n, :s, :e, :r, :logo, CAST(:alt AS jsonb)) RETURNING id"
                    ),
                    {
                        "n": name,
                        "s": sport_id,
                        "e": espn_id,
                        "r": record,
                        "logo": f"https://a.espncdn.com/i/teamlogos/ncaa/500/{espn_id}.png",
                        "alt": json.dumps([name]),
                    },
                )
            ).scalar_one()
    return ids


async def _row(engine, team_id):
    async with engine.connect() as conn:
        return (
            await conn.execute(
                text(
                    "SELECT name, espn_id, current_record, logo_url_small, alternate_names "
                    "FROM teams WHERE id = :i"
                ),
                {"i": team_id},
            )
        ).one()


@needs_postgres
@pytest.mark.asyncio
async def test_the_apply_clears_only_rows_still_holding_the_judged_identity(
    pg_engine, monkeypatch, capsys
):
    from sqlalchemy.ext.asyncio import async_sessionmaker

    import app.services.espn_api as espn_api
    import app.tasks.base as base
    from scripts import repair_9017_foreign_espn_id as repair
    from scripts import restore_9017_foreign_espn_id as undo

    ids = await _seed(pg_engine)
    before = {k: await _row(pg_engine, v) for k, v in ids.items()}
    maker = async_sessionmaker(pg_engine, expire_on_commit=False)

    @asynccontextmanager
    async def _session():
        async with maker() as s:
            yield s

    async def _directory_while_espn_sync_writes(svc, key):
        # Runs after the candidate read and before the write — the script's
        # own await on ESPN. A sync pass lands in that window.
        async with pg_engine.begin() as conn:
            await conn.execute(
                text("UPDATE teams SET espn_id = '147', current_record = '40-10' WHERE id = :i"),
                {"i": ids["texas_state"]},
            )
            await conn.execute(
                text("UPDATE teams SET name = 'North Florida Ospreys' WHERE id = :i"),
                {"i": ids["north_florida"]},
            )
        return DIRECTORY

    monkeypatch.setenv("HEROKU_APP_NAME", "bainluck")
    monkeypatch.setattr(base, "get_task_session", _session)
    monkeypatch.setattr(espn_api, "ESPNAPIService", lambda: None)
    monkeypatch.setattr(repair, "fetch_directory", _directory_while_espn_sync_writes)

    rc = await repair.run(argparse.Namespace(backup=True, apply=True))
    out = capsys.readouterr().out

    assert rc == 0, out
    assert "foreign (name names a different ESPN club): 3" in out
    moved = sorted([ids["texas_state"], ids["north_florida"]])
    assert f"changed since the plan, NOT written: {moved}" in out
    assert "applied: 1 rows; still carrying identity: 0" in out

    cleared = await _row(pg_engine, ids["miami_oh"])
    assert cleared.name == "Miami (OH)"
    assert (cleared.espn_id, cleared.current_record, cleared.logo_url_small) == (None, None, None)
    assert cleared.alternate_names is None

    # The re-enriched and renamed rows keep what the sync wrote.
    texas = await _row(pg_engine, ids["texas_state"])
    assert (texas.espn_id, texas.current_record) == ("147", "40-10")
    florida = await _row(pg_engine, ids["north_florida"])
    assert (florida.name, florida.espn_id) == ("North Florida Ospreys", "75")
    # The owner was never judged.
    assert await _row(pg_engine, ids["hurricanes"]) == before["hurricanes"]

    async with pg_engine.begin() as conn:
        await conn.execute(text(undo._RESTORE_SQL))
    assert await _row(pg_engine, ids["miami_oh"]) == before["miami_oh"]
    assert (await _row(pg_engine, ids["texas_state"])).espn_id == "147"
