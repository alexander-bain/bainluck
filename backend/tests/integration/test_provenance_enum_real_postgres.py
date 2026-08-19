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

import importlib.util
import os
import pathlib
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

_VERSIONS = pathlib.Path(__file__).resolve().parents[2] / "alembic/versions"


def _load(filename: str, name: str):
    spec = importlib.util.spec_from_file_location(name, _VERSIONS / filename)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


#: The two revisions under test, imported so their OWN constants and their OWN
#: SQL string drive this file. Nothing below re-spells a statement the schema
#: already spells — the previous version of this file built the enum from
#: `PROVENANCE_VALUES` and then asserted the result equalled `PROVENANCE_VALUES`,
#: which is a self-oracle: it could not have failed no matter what shipped.
_BASE = _load("add_disc_interactions_provenance.py", "_pg_prov_base")
_PLAY = _load("add_prov_play_enum_value.py", "_pg_prov_play")

#: What the base revision's source SAYS it created. Read from the module, so it
#: tracks any edit anyone makes to that file.
SIX_PER_SOURCE = _BASE.PROVENANCE_VALUES_AS_APPLIED

#: What production's `pg_enum` ACTUALLY holds — measured, not read from source:
#:
#:     SELECT enumlabel, enumsortorder FROM pg_enum e
#:       JOIN pg_type t ON t.oid = e.enumtypid
#:      WHERE t.typname = 'discover_provenance' ORDER BY enumsortorder;
#:     -- user 1 | warmer 2 | sentinel 3 | gold_session 4 | admin 5 | unknown 6
#:
#: Frozen deliberately, and NOT derived from the constant above. That
#: independence is the entire point: this literal cannot be moved by editing a
#: migration, so if someone edits the already-applied revision's tuple, the two
#: fixture paths stop agreeing and this file goes red. An in-place edit to a
#: revision that has already run is invisible to every source-reading assertion,
#: because source is the one thing such an edit definitely changes.
SIX_IN_PRODUCTION_2026_08_19 = (
    "user",
    "warmer",
    "sentinel",
    "gold_session",
    "admin",
    "unknown",
)


async def _create_enum(pg_session, labels):
    from sqlalchemy import text

    rendered = ", ".join(f"'{v}'" for v in labels)
    await pg_session.execute(text(f"CREATE TYPE {ENUM_NAME} AS ENUM ({rendered})"))
    await pg_session.commit()


async def _run_play_revision(pg_session):
    """Execute the play revision's OWN statement, not a copy of it."""
    from sqlalchemy import text

    # `ALTER TYPE … ADD VALUE` is what the migration runs inside
    # `op.get_context().autocommit_block()`. asyncpg gives each `execute` its own
    # implicit transaction here, and the commit below is the block's analogue.
    await pg_session.execute(text(_PLAY.add_value_sql(ENUM_NAME)))
    await pg_session.commit()


@pytest.fixture(params=["fresh_database", "migration_already_applied"])
async def provenance_enum(request, pg_session):
    """Build the enum by running the CHAIN, from both start states.

    This is the addendum's named verify, and it is two paths because the defect
    it guards is *exactly* the difference between them:

    * **fresh_database** — nothing exists, so BOTH revisions execute. The type is
      built from the base revision's own tuple **as its source currently reads**,
      then the play revision runs. This is CI.
    * **migration_already_applied** — the type already exists from an earlier
      deploy and `alembic_version` is at `add_disc_int_provenance`, so the base
      revision **never executes again**. The type is built from the six labels
      production was *measured* to hold, and only the play revision runs. This is
      production.

    The two paths differ in exactly one way, and it is the way that matters:
    the first follows the base revision's source, the second follows a frozen
    measurement of production that no source edit can move. Editing an
    already-applied revision changes the first and not the second, so the two
    stop agreeing and this file goes red — which is the whole failure mode. If
    both paths simply re-read the same constant, they are one path written
    twice, and the gate is decorative.

    Both must end at seven values *in the same order*. Parametrising the fixture
    means every assertion in this file is asked twice, once per path, rather
    than the two-path claim being made once and then left behind.
    """
    from sqlalchemy import text

    await pg_session.execute(text(f"DROP TYPE IF EXISTS {ENUM_NAME} CASCADE"))
    await pg_session.commit()

    if request.param == "fresh_database":
        await _create_enum(pg_session, SIX_PER_SOURCE)
    else:
        await _create_enum(pg_session, SIX_IN_PRODUCTION_2026_08_19)
    await _run_play_revision(pg_session)

    yield request.param
    await pg_session.execute(text(f"DROP TYPE IF EXISTS {ENUM_NAME} CASCADE"))
    await pg_session.commit()


class TestTheChainConvergesFromBothStartStates:
    async def test_the_play_revision_is_idempotent(self, pg_session, provenance_enum):
        """`IF NOT EXISTS` — because `autocommit_block()` means this statement is
        not rolled back with the rest of a failed revision, so a retry re-runs it.

        Also the thing that makes the two fixture paths safe to collapse if the
        base revision is ever partially applied.
        """
        from sqlalchemy import text

        await _run_play_revision(pg_session)
        await _run_play_revision(pg_session)
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
        assert len(rows) == 7, f"re-running ADD VALUE changed the enum: {rows}"

    async def test_play_lands_last_on_both_paths(self, pg_session, provenance_enum):
        """Ordinals, not just membership.

        Enum ordinals are what `ORDER BY provenance` and every btree range scan
        on the column mean. Seven values in two different orders is two types
        with one name, and the gate would be green against a shape production
        does not have.
        """
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

        expected = SIX_IN_PRODUCTION_2026_08_19 + ("play",)
        assert tuple(rows) == expected, (
            f"path={provenance_enum}: chain produced {rows}, expected {expected}"
        )
        # And the receiver's allowlist is that same tuple — the binding this
        # whole change exists to enforce, asked of PostgreSQL rather than source.
        assert tuple(rows) == PROVENANCE_VALUES


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
