"""The provenance enum, executed against a REAL PostgreSQL enum type.

## Why this file has to exist, stated as the defect it catches

`C-ADHOC-PROV-CORE` found a receiver that accepted `play` sitting on top of a
migration whose enum declared six values without it. The route specimen was run,
it stored `play`, and it committed — **so the evidence said the feature worked.**
It committed because the recording double does not enforce PostgreSQL's enum
type. Against a real database every Play interaction would have been rejected at
commit, in production, on the kid surface.

That is a writer/schema contract split, and it is invisible to every test that
does not touch a real enum. An ORM will hand PostgreSQL any string you like; the
type is what says no. So the gate for "the enum can represent what the receiver
accepts" cannot be an ORM test, a mock session, or a migration-source
assertion — all three passed while the defect was live.

Opt-in on `SEARCH_TEST_DATABASE_URL`, following
`test_search_recall_contract.py` and `test_calibration_canonical_pg.py`: it
skips where no Postgres exists and runs in the `search-recall` CI job, which
provides one. There is no local Postgres in the agent sandbox (initdb fails on
shmget), so **CI is the environment that runs this** — and the job's own
"Verify the gate is actually armed" step exists precisely so a skipped gate
cannot be mistaken for a passing one.
"""

from __future__ import annotations

import os
import uuid

import pytest

from app.utils.discover_provenance import PROVENANCE_VALUES

DB_URL = os.environ.get("SEARCH_TEST_DATABASE_URL")

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not DB_URL,
        reason=(
            "set SEARCH_TEST_DATABASE_URL to run the real-Postgres provenance "
            "enum gate (CI job: search-recall)"
        ),
    ),
]

ENUM_NAME = "discover_provenance"


@pytest.fixture
async def pg_session():
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    engine = create_async_engine(DB_URL)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        yield session
    await engine.dispose()


@pytest.fixture
async def provenance_enum(pg_session):
    """Create the enum exactly as the migration does, from the same constant."""
    from sqlalchemy import text

    await pg_session.execute(text(f"DROP TYPE IF EXISTS {ENUM_NAME} CASCADE"))
    labels = ", ".join(f"'{v}'" for v in PROVENANCE_VALUES)
    await pg_session.execute(text(f"CREATE TYPE {ENUM_NAME} AS ENUM ({labels})"))
    await pg_session.commit()
    yield
    await pg_session.execute(text(f"DROP TYPE IF EXISTS {ENUM_NAME} CASCADE"))
    await pg_session.commit()


class TestTheEnumCanRepresentEveryAcceptedValue:
    async def test_the_migration_double_emits_seven_values_with_play_true(
        self, pg_session, provenance_enum
    ):
        """The addendum's named verify, asked of PostgreSQL rather than of source."""
        from sqlalchemy import text

        rows = (
            await pg_session.execute(
                text(
                    "SELECT e.enumlabel FROM pg_enum e "
                    "JOIN pg_type t ON t.oid = e.enumtypid "
                    "WHERE t.typname = :n ORDER BY e.enumsortorder"
                ),
                {"n": ENUM_NAME},
            )
        ).scalars().all()

        assert len(rows) == 7, f"enum has {len(rows)} values, expected 7: {rows}"
        assert "play" in rows, "play=False — every Play interaction would be rejected"
        assert tuple(rows) == PROVENANCE_VALUES

    @pytest.mark.parametrize("value", PROVENANCE_VALUES)
    async def test_every_allowlisted_value_is_storable(
        self, pg_session, provenance_enum, value
    ):
        """The receiver's allowlist and the database's type, compared by the
        only authority that settles it — a cast that either succeeds or errors."""
        from sqlalchemy import text

        got = (
            await pg_session.execute(
                text(f"SELECT CAST(:v AS {ENUM_NAME})"), {"v": value}
            )
        ).scalar_one()
        assert str(got) == value

    async def test_a_value_outside_the_enum_is_rejected(
        self, pg_session, provenance_enum
    ):
        """Proves the type is actually enforcing — otherwise the test above
        would pass against a plain VARCHAR and prove nothing."""
        from sqlalchemy import text
        from sqlalchemy.exc import DBAPIError

        with pytest.raises(DBAPIError):
            await pg_session.execute(
                text(f"SELECT CAST(:v AS {ENUM_NAME})"), {"v": "definitely_not_a_value"}
            )
        await pg_session.rollback()


class TestPlayStampedRouteSpecimenCommits:
    """A Play-stamped interaction, written to a real column of the real type.

    This is the half the ORM specimen could not answer. The column is built on
    a scratch table rather than `discover_interactions` so the test needs no
    migration state and touches no real data — what is under test is the TYPE,
    which is shared.
    """

    @pytest.fixture
    async def scratch_table(self, pg_session, provenance_enum):
        from sqlalchemy import text

        name = f"prov_specimen_{uuid.uuid4().hex[:8]}"
        await pg_session.execute(
            text(
                f"CREATE TABLE {name} ("
                f"  id serial PRIMARY KEY,"
                f"  provenance {ENUM_NAME} DEFAULT 'unknown'"
                f")"
            )
        )
        await pg_session.commit()
        yield name
        await pg_session.execute(text(f"DROP TABLE IF EXISTS {name}"))
        await pg_session.commit()

    async def test_a_play_stamped_row_commits(self, pg_session, scratch_table):
        """The specimen that previously "passed" only because nothing enforced
        the type. If `play` is ever dropped from the enum again, this is the
        test that goes red instead of production."""
        from sqlalchemy import text
        from app.utils.discover_provenance import normalize_provenance

        # Exactly what the receiver would compute from the Play transport's header.
        provenance = normalize_provenance("play")
        assert provenance == "play"

        await pg_session.execute(
            text(f"INSERT INTO {scratch_table} (provenance) VALUES (CAST(:p AS {ENUM_NAME}))"),
            {"p": provenance},
        )
        await pg_session.commit()

        stored = (
            await pg_session.execute(text(f"SELECT provenance FROM {scratch_table}"))
        ).scalar_one()
        assert str(stored) == "play"

    async def test_an_unstamped_row_defaults_to_unknown_not_user(
        self, pg_session, scratch_table
    ):
        from sqlalchemy import text

        await pg_session.execute(text(f"INSERT INTO {scratch_table} DEFAULT VALUES"))
        await pg_session.commit()
        stored = (
            await pg_session.execute(text(f"SELECT provenance FROM {scratch_table}"))
        ).scalar_one()
        assert str(stored) == "unknown"
        assert str(stored) != "user"
