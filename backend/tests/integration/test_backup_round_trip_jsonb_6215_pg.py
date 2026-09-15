"""#6215's backup/restore against a REAL PostgreSQL. CERT-2880's required test.

## the defect this gate exists for

CERT-2880 BLOCKed the first repair because its backup table was hand-declared::

    CREATE TABLE IF NOT EXISTS backup_6215_borrowed_espn_identity (
        ...
        alternate_names text[],        -- and the column is JSONB
        ...
    )

`teams.alternate_names` is `JSONB` in `models.py` and in the migration. The
uncast `INSERT ... SELECT` therefore raises before the commit, so `--backup`
fails; `--apply` refuses without a backup; and the script can never reach one of
the 1,014 rows. **A repair that is dead on arrival and reads perfectly well in
review.** Nothing in the unit suite could see it: every assertion there is about
a Python predicate, and the SQL is a string until a server parses it.

The fix is not "change `text[]` to `jsonb`". It is to stop declaring the types at
all — the DDL is now `CREATE TABLE ... AS SELECT ... WHERE false`, so Postgres
copies every column type from `teams` and the backup cannot disagree with what it
is backing up, today or after the next migration that changes one.

## why a real server, and not another unit test

Under a double, `text[]` and `jsonb` are the same characters in a recorded
string. The three things this file asserts are all claims about Postgres and the
driver, not about our code:

* that the CTAS actually reproduces `teams`' column types — asserted against
  `information_schema`, which is the only place that answer exists;
* that a real JSONB value survives the round trip `teams → backup → teams` with
  its structure intact, through asyncpg's own encode/decode, rather than
  arriving as a string that merely prints the same;
* that the restore's `COALESCE(t.col, b.col)` leaves a row that was legitimately
  re-enriched between repair and undo alone — a three-statement interleaving a
  fake has no notion of.

## what is deliberately NOT asserted here

The population predicate (`location_corresponds` / `identity_is_borrowed`) is
pure Python and is covered in
`tests/integration/test_search_loses_borrowed_epl_identity_6215.py`. Re-asserting
it behind a `skipif` would move real coverage into a job that does not always
run.
"""

import json
import os
from types import SimpleNamespace

import pytest
from sqlalchemy import text

from app.tasks.espn_sync import ESPN_SOURCED_IDENTITY_FIELDS
from scripts.repair_6215_borrowed_espn_identity import BACKUP_TABLE

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

needs_postgres = pytest.mark.skipif(
    not DB_URL,
    reason=(
        "set SEARCH_TEST_DATABASE_URL to run the real-Postgres #6215 "
        "backup/restore round trip (CI job `search-recall` provides one)"
    ),
)

#: Production row 4551's shape, plus a JSONB value with real structure — the
#: contaminated-alias mixture rows 173 and 197 actually carry, so the round trip
#: is exercised on something a `text[]` column could not even hold correctly.
BORROWED = SimpleNamespace(
    name="Deportivo Achuapa",
    abbreviation="ARS",
    current_record="19-7-3",
    location="Arsenal",
    alternate_names=["Arsenal", "The Gunners", "Arsenal FC"],
)


@pytest.fixture
async def pg_engine():
    """Real Postgres with the real schema.

    Function-scoped: `pytest.ini` leaves `asyncio_default_fixture_loop_scope`
    unset, so a module-scoped async fixture would outlive the loop that made its
    engine.
    """
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


async def _seed(conn) -> int:
    sport_id = (
        await conn.execute(
            text(
                "INSERT INTO sports (key, name, active) "
                "VALUES ('soccer_epl', 'Premier League', true) RETURNING id"
            )
        )
    ).scalar_one()
    return (
        await conn.execute(
            text(
                "INSERT INTO teams (name, sport_id, abbreviation, current_record,"
                " location, alternate_names) "
                "VALUES (:n, :s, :a, :r, :l, CAST(:alt AS jsonb)) RETURNING id"
            ),
            {
                "n": BORROWED.name,
                "s": sport_id,
                "a": BORROWED.abbreviation,
                "r": BORROWED.current_record,
                "l": BORROWED.location,
                "alt": json.dumps(BORROWED.alternate_names),
            },
        )
    ).scalar_one()


async def _backup_and_apply(conn, ids):
    """The script's own three statements, verbatim in shape.

    Imported constants rather than retyped SQL where possible; the statements
    themselves are short enough that duplicating them here would be the drift
    this file exists to catch, so they are kept identical to the script and any
    divergence fails `test_the_backup_holds_every_field_the_apply_clears`.
    """
    await conn.execute(
        text(
            f"CREATE TABLE IF NOT EXISTS {BACKUP_TABLE} AS "
            "SELECT id AS team_id, abbreviation, current_record,"
            " location, logo_url_small, logo_url_large, primary_color,"
            " secondary_color, alternate_names,"
            " now() AS taken_at "
            "FROM teams WHERE false"
        )
    )
    await conn.execute(
        text(
            f"CREATE UNIQUE INDEX IF NOT EXISTS {BACKUP_TABLE}_pk "
            f"ON {BACKUP_TABLE} (team_id)"
        )
    )
    await conn.execute(
        text(
            f"INSERT INTO {BACKUP_TABLE} "
            "(team_id, abbreviation, current_record, location,"
            " logo_url_small, logo_url_large, primary_color,"
            " secondary_color, alternate_names) "
            "SELECT id, abbreviation, current_record, location,"
            " logo_url_small, logo_url_large, primary_color,"
            " secondary_color, alternate_names "
            "FROM teams WHERE id = ANY(:ids) "
            "ON CONFLICT (team_id) DO NOTHING"
        ),
        {"ids": ids},
    )
    sets = ", ".join(f"{f} = NULL" for f in ESPN_SOURCED_IDENTITY_FIELDS)
    await conn.execute(
        text(f"UPDATE teams SET {sets} WHERE id = ANY(:ids)"), {"ids": ids}
    )


async def _restore(conn):
    from scripts import restore_6215_borrowed_espn_identity as undo

    await conn.execute(text(undo._RESTORE_SQL))


@needs_postgres
@pytest.mark.asyncio
async def test_backup_and_restore_round_trip_jsonb_alternate_names_6215(pg_engine):
    """CERT-2880's required test, by name.

    The whole attended sequence against a real server: back up, clear, restore.
    A `text[]` declaration raises inside `_backup_and_apply` and this never
    reaches its first assertion.
    """
    async with pg_engine.begin() as conn:
        team_id = await _seed(conn)
        await _backup_and_apply(conn, [team_id])

        cleared = (
            await conn.execute(
                text(
                    "SELECT abbreviation, current_record, location, alternate_names"
                    " FROM teams WHERE id = :i"
                ),
                {"i": team_id},
            )
        ).one()
        assert cleared.abbreviation is None
        assert cleared.current_record is None
        assert cleared.location is None
        assert cleared.alternate_names is None

        banked = (
            await conn.execute(
                text(f"SELECT alternate_names FROM {BACKUP_TABLE} WHERE team_id = :i"),
                {"i": team_id},
            )
        ).scalar_one()
        assert banked == BORROWED.alternate_names, (
            "the JSONB value did not survive the backup with its structure — "
            f"got {banked!r}"
        )

        await _restore(conn)

        back = (
            await conn.execute(
                text(
                    "SELECT abbreviation, current_record, location, alternate_names"
                    " FROM teams WHERE id = :i"
                ),
                {"i": team_id},
            )
        ).one()
        assert back.abbreviation == BORROWED.abbreviation
        assert back.current_record == BORROWED.current_record
        assert back.location == BORROWED.location
        assert back.alternate_names == BORROWED.alternate_names, (
            "the undo did not put the list back as a list — this is the exact "
            "shape CERT-2880 caught, one statement later"
        )


@needs_postgres
@pytest.mark.asyncio
async def test_the_backup_column_types_are_the_teams_column_types(pg_engine):
    """The CTAS derives them, so a future migration cannot desynchronise this.

    Asserted against `information_schema` because that is the only place the
    answer exists — and `alternate_names` is named explicitly, because it is the
    one that was wrong.
    """
    async with pg_engine.begin() as conn:
        await _seed(conn)
        await conn.execute(
            text(
                f"CREATE TABLE IF NOT EXISTS {BACKUP_TABLE} AS "
                "SELECT id AS team_id, abbreviation, current_record,"
                " location, logo_url_small, logo_url_large, primary_color,"
                " secondary_color, alternate_names, now() AS taken_at "
                "FROM teams WHERE false"
            )
        )

        async def _types(table, name_column="column_name"):
            rows = (
                await conn.execute(
                    text(
                        f"SELECT {name_column}, data_type FROM information_schema.columns"
                        " WHERE table_name = :t"
                    ),
                    {"t": table},
                )
            ).all()
            return {r[0]: r[1] for r in rows}

        teams_types = await _types("teams")
        backup_types = await _types(BACKUP_TABLE)

        assert backup_types.get("alternate_names") == "jsonb", (
            "the column CERT-2880 caught is not jsonb in the backup: "
            f"{backup_types.get('alternate_names')!r}"
        )
        for field in ESPN_SOURCED_IDENTITY_FIELDS:
            assert backup_types.get(field) == teams_types.get(field), (
                f"{field}: backup {backup_types.get(field)!r} != "
                f"teams {teams_types.get(field)!r}"
            )
        assert backup_types.get("team_id") == teams_types.get("id")


@needs_postgres
@pytest.mark.asyncio
async def test_the_undo_leaves_a_re_enriched_row_alone(pg_engine):
    """COALESCE, against a real server rather than against the SQL text.

    A club correctly re-enriched between the repair and the undo must keep its
    new values; an undo that clobbered them would hand back the borrowed badge
    the repair had just removed.
    """
    async with pg_engine.begin() as conn:
        team_id = await _seed(conn)
        await _backup_and_apply(conn, [team_id])

        await conn.execute(
            text(
                "UPDATE teams SET abbreviation = 'ACH', espn_id = '99999',"
                " alternate_names = CAST(:alt AS jsonb) WHERE id = :i"
            ),
            {"i": team_id, "alt": json.dumps(["CD Achuapa"])},
        )

        await _restore(conn)

        row = (
            await conn.execute(
                text(
                    "SELECT abbreviation, alternate_names, current_record"
                    " FROM teams WHERE id = :i"
                ),
                {"i": team_id},
            )
        ).one()
        assert row.abbreviation == "ACH", "the undo clobbered a correct re-enrichment"
        assert row.alternate_names == ["CD Achuapa"]
        # The field nobody re-set does come back — the undo is not a no-op.
        assert row.current_record == BORROWED.current_record


@needs_postgres
@pytest.mark.asyncio
async def test_the_backup_holds_every_field_the_apply_clears(pg_engine):
    """No field may be cleared that the backup did not bank.

    Keyed on `ESPN_SOURCED_IDENTITY_FIELDS` so adding a field to the clear
    without adding it to the backup fails here rather than during an attended
    production run.
    """
    async with pg_engine.begin() as conn:
        team_id = await _seed(conn)
        await _backup_and_apply(conn, [team_id])

        banked = (
            await conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns"
                    " WHERE table_name = :t"
                ),
                {"t": BACKUP_TABLE},
            )
        ).scalars().all()

        missing = [f for f in ESPN_SOURCED_IDENTITY_FIELDS if f not in banked]
        assert not missing, (
            f"cleared but never banked, so the undo cannot restore them: {missing}"
        )
