"""`search_query_logs.origin`: does an unstamped row read UNKNOWN, or does it read HUMAN?

#1916 step 2 (lane1/220). The column exists for exactly one reason — the issue's
acceptance line "``user`` is a positive assertion, not a default-by-absence" —
and there is exactly one edit that destroys that reason while leaving every other
test in the suite green: adding ``server_default='user'`` to the ``add_column``.

Nothing reads the column yet, so no consumer test can protect it. That is
precisely when a column is easiest to break: the next person to touch this
migration sees a nullable column with no default, reads it as an oversight, and
"tidies" it. This file is the reason they cannot.

═══ WHAT IS ACTUALLY PROVEN HERE, AND HOW ═══

The DDL is composed from the ``sa.Column`` object the migration ITSELF hands to
``op.add_column``, never from a constant in this file. A constant would let the
behavioural assertions below keep passing while ``server_default``, ``nullable``
or the width quietly changed in the migration — they would be proving that a
string in this test describes a column, which is not a fact about production.

The substrate is a real SQLite database rather than a mock, because the property
under test is what Postgres DOES to a row that omits the column, and only an
engine answers that. SQLite and Postgres agree on the two semantics in play here
(an omitted column with no default is NULL; a declared DEFAULT is applied on
omission), which is the whole of what the assertions turn on.

The pre-migration ``CREATE TABLE`` is written out literally on purpose: it is the
shipped shape this migration must compose ONTO, and deriving it from today's
model would make the test tautological — the model already carries ``origin``.
"""

from __future__ import annotations

import importlib.util
import sqlite3
from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy.dialects.sqlite import dialect as sqlite_dialect

ROOT = Path(__file__).resolve().parents[1]
MIGRATION_PATH = ROOT / "alembic" / "versions" / "search_log_origin.py"

#: `search_query_logs` as it stands on production BEFORE this migration —
#: `app/models/models.py::SearchQueryLog` minus the column being added. Literal,
#: not derived: see the module docstring.
PRE_MIGRATION_TABLE = """
    CREATE TABLE search_query_logs (
        id INTEGER PRIMARY KEY,
        user_id INTEGER,
        session_id VARCHAR(100),
        query VARCHAR(300) NOT NULL,
        result_count INTEGER,
        top_result_id INTEGER,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
"""


def _load_migration():
    spec = importlib.util.spec_from_file_location("search_log_origin", MIGRATION_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _RecordingOp:
    """Stands in for `alembic.op`, recording DDL instead of emitting it."""

    def __init__(self) -> None:
        #: ONE interleaved log, so a future migration that adds a second column,
        #: or drops the wrong one in `downgrade()`, cannot hide between two
        #: separate lists.
        self.ops: list[tuple[str, tuple]] = []

    def add_column(self, table, column, **kwargs):
        self.ops.append(("add_column", (table, column, kwargs)))

    def drop_column(self, table, name, **kwargs):
        self.ops.append(("drop_column", (table, name, kwargs)))


def _recorded(direction: str) -> _RecordingOp:
    mod = _load_migration()
    recorder = _RecordingOp()
    mod.op = recorder
    getattr(mod, direction)()
    return recorder


def _added_column() -> tuple[str, sa.Column]:
    """The (table, Column) pair `upgrade()` actually asked for. Exactly one."""
    recorder = _recorded("upgrade")
    ((kind, (table, column, _kwargs)),) = recorder.ops
    assert kind == "add_column", f"upgrade() emitted {kind}, not add_column"
    return table, column


def _ddl_from(table: str, column: sa.Column) -> str:
    """Compose executable DDL from the Column object the MIGRATION built.

    Renders `server_default` if the migration set one — which is the point. A
    composer that ignored it would make the defaulting test below unfalsifiable.
    """
    type_sql = column.type.compile(sqlite_dialect())
    null_sql = "" if column.nullable else " NOT NULL"
    default = column.server_default
    default_sql = ""
    if default is not None:
        default_sql = f" DEFAULT {getattr(default, 'arg', default)}"
    return f"ALTER TABLE {table} ADD COLUMN {column.name} {type_sql}{null_sql}{default_sql}"


@pytest.fixture()
def migrated_db():
    conn = sqlite3.connect(":memory:")
    conn.execute(PRE_MIGRATION_TABLE)
    table, column = _added_column()
    conn.execute(_ddl_from(table, column))
    yield conn
    conn.close()


def test_a_row_written_without_a_stamp_reads_null_and_is_not_silently_human(migrated_db):
    """THE assertion this file exists for (#1916 acceptance; gotcha #53).

    Every row on production is written by a path that does not yet stamp, so if
    the column defaulted to `'user'` the table would assert humanity for 6,725
    machine-and-human rows indiscriminately — the exact false reading #1916 was
    filed to end, arriving in the fix for it.
    """
    migrated_db.execute("INSERT INTO search_query_logs (query) VALUES ('red sox')")
    (origin,) = migrated_db.execute("SELECT origin FROM search_query_logs").fetchone()

    assert origin is None, (
        f"an unstamped row read {origin!r}. A NULL here means 'nobody said', which is "
        "the truth; any other value is this migration asserting something no writer did."
    )
    assert origin != "user"


def test_the_migration_declares_no_server_default_and_stays_nullable(migrated_db):
    """The two properties that make the NULL above reachable, read off the migration.

    Behavioural cover above proves the CURRENT shape; this proves the migration
    is not merely getting away with it — a NOT NULL column with no default would
    also fail the insert above, but for the wrong reason and with a confusing
    message.
    """
    _table, column = _added_column()
    assert column.server_default is None, (
        f"server_default={column.server_default!r}. A default on this column converts "
        "'unknown' into a positive claim about every row that predates the stamp."
    )
    assert column.nullable is True
    assert column.index in (None, False), "no reader measured; an index here is cost with no consumer"


def test_the_column_accepts_the_full_width_the_stamp_will_write(migrated_db):
    """The stamp truncates the verbatim header to 64. The store must accept 64.

    A store narrower than its writer's bound refuses the write, and a guard that
    refuses to write freezes the old value — here, freezes NULL — so the column
    would silently keep reading 'unknown' for the loudest automation we have.
    """
    _table, column = _added_column()
    assert column.type.length == 64

    value = "w" * 64
    migrated_db.execute(
        "INSERT INTO search_query_logs (query, origin) VALUES ('red sox', ?)", (value,)
    )
    (stored,) = migrated_db.execute(
        "SELECT origin FROM search_query_logs ORDER BY id DESC LIMIT 1"
    ).fetchone()
    assert stored == value


def test_the_model_and_the_migration_can_hold_the_same_value(migrated_db):
    """Two declarations of one column; a drift between them is a production error.

    Asserted as capability rather than as a field-by-field comparison: what
    matters is that a value the migration's column accepts is a value the ORM
    column accepts, and that NEITHER declaration carries a default. The ORM half
    is the one that would ship a `server_default` without touching `alembic/` at
    all, so it needs its own assertion and not an inherited one.
    """
    from app.models.models import SearchQueryLog

    orm_column = SearchQueryLog.__table__.c.origin
    _table, migration_column = _added_column()

    assert orm_column.server_default is None
    assert orm_column.default is None, (
        "a Python-side default is the same defect wearing a different hat — it "
        "stamps at INSERT time from the application, where nothing knows the origin."
    )
    assert orm_column.nullable is True
    assert orm_column.type.length >= migration_column.type.length


def test_downgrade_drops_exactly_what_upgrade_added(migrated_db):
    """The D51 undo line (`alembic downgrade containers_phase1`) must be exact.

    An asymmetric pair here does not fail at test time or at upgrade time — it
    fails in the Heroku release phase during a rollback, which is the worst place
    to find it and the one place nobody is watching.
    """
    table, column = _added_column()
    recorder = _recorded("downgrade")
    ((kind, (down_table, name, _kwargs)),) = recorder.ops

    assert kind == "drop_column"
    assert (down_table, name) == (table, column.name)


def test_the_revision_chain_and_id_are_shippable():
    """Gotcha #1 (≤32 chars) and the chain this links into, in one place."""
    mod = _load_migration()
    assert len(mod.revision) <= 32
    assert mod.revision == "search_log_origin"
    assert mod.down_revision == "containers_phase1"
