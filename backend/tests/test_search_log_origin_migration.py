"""`search_query_logs.origin` / `.top_result_kind`: does an unrecorded row read UNKNOWN, or does it lie?

#1916 step 2 (lane1/220) plus #4836's discriminator, folded into the one attended
migration. Both columns exist for the same reason, stated once: **an absence must
stay readable as an absence.**

* ``origin`` — #1916's acceptance line, "``user`` is a positive assertion, not a
  default-by-absence".
* ``top_result_kind`` — 556 of 1,261 answered searches (44%) over 7 days carry a
  NULL ``top_result_id`` because ``results`` is the events array only. A default
  of ``'event'`` would assert that every one of those searches was led by an
  event, which is the precise falsehood the column is being added to end.

For each column there is exactly one edit that destroys its reason while leaving
every other test in the suite green: adding a ``server_default`` to its
``add_column``. Nothing reads either column yet, so no consumer test can protect
them. That is precisely when a column is easiest to break: the next person to
touch this migration sees a nullable column with no default, reads it as an
oversight, and "tidies" it. This file is the reason they cannot.

═══ WHAT IS ACTUALLY PROVEN HERE, AND HOW ═══

The DDL is composed from the ``sa.Column`` objects the migration ITSELF hands to
``op.add_column``, never from constants in this file. Constants would let the
behavioural assertions below keep passing while ``server_default``, ``nullable``
or a width quietly changed in the migration — they would be proving that a string
in this test describes a column, which is not a fact about production.

The substrate is a real SQLite database rather than a mock, because the property
under test is what Postgres DOES to a row that omits a column, and only an engine
answers that. SQLite and Postgres agree on the two semantics in play here (an
omitted column with no default is NULL; a declared DEFAULT is applied on
omission), which is the whole of what the assertions turn on.

The pre-migration ``CREATE TABLE`` is written out literally on purpose: it is the
shipped shape this migration must compose ONTO, and deriving it from today's
model would make the test tautological — the model already carries both columns.

═══ WHY THE COLUMNS ARE ENUMERATED, NOT ASSUMED ═══

``EXPECTED_COLUMNS`` below is the ONE place this file states what the migration
should add. Every test derives from what ``upgrade()`` actually emitted and
reconciles against that set, so adding a third column to the migration without
adding it here fails loudly (``test_upgrade_adds_exactly_the_columns_this_file_guards``)
rather than sliding in ungarded. The previous single-column version of this file
enforced the same invariant by unpacking a one-element list; this is that guard
generalised, not relaxed.
"""

from __future__ import annotations

import importlib.util
import re
import sqlite3
from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy.dialects.sqlite import dialect as sqlite_dialect

ROOT = Path(__file__).resolve().parents[1]
MIGRATION_PATH = ROOT / "alembic" / "versions" / "search_log_origin.py"

#: The complete set of columns this migration is allowed to add, and the width
#: each one's future writer needs. `origin` truncates the verbatim
#: `x-bainluck-origin` header to 64; `top_result_kind` holds one of four literals
#: whose longest is `'event_concept'` (13), so 32 is headroom, not a guess.
EXPECTED_COLUMNS = {"origin": 64, "top_result_kind": 32}

#: The four values `top_result_kind` exists to distinguish — one per section
#: `/api/events/search` answers out of (latency/313, #4836).
TOP_RESULT_KINDS = ("event", "team", "futures", "event_concept")

#: `search_query_logs` as it stands on production BEFORE this migration —
#: `app/models/models.py::SearchQueryLog` minus the columns being added. Literal,
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
        #: ONE interleaved log, so a migration that adds a column it never drops,
        #: or drops the wrong one in `downgrade()`, cannot hide between two
        #: separate lists — and so ORDER stays assertable.
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


def _added_columns() -> dict[str, tuple[str, sa.Column]]:
    """Every (table, Column) `upgrade()` actually asked for, keyed by column name."""
    recorder = _recorded("upgrade")
    added: dict[str, tuple[str, sa.Column]] = {}
    for kind, (table, column, _kwargs) in recorder.ops:
        assert kind == "add_column", f"upgrade() emitted {kind}, not add_column"
        assert column.name not in added, f"upgrade() adds {column.name!r} twice"
        added[column.name] = (table, column)
    return added


def _added_column(name: str) -> tuple[str, sa.Column]:
    added = _added_columns()
    assert name in added, f"upgrade() never adds {name!r}; it adds {sorted(added)}"
    return added[name]


def _ddl_from(table: str, column: sa.Column) -> str:
    """Compose executable DDL from the Column object the MIGRATION built.

    Renders `server_default` if the migration set one — which is the point. A
    composer that ignored it would make the defaulting tests below unfalsifiable.
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
    for table, column in _added_columns().values():
        conn.execute(_ddl_from(table, column))
    yield conn
    conn.close()


def test_upgrade_adds_exactly_the_columns_this_file_guards():
    """The reconciliation that keeps every other test in this file honest.

    A third column added to the migration but not to `EXPECTED_COLUMNS` would
    otherwise ship with no default/nullable/width guard at all — the columns here
    have no consumers yet, so nothing else in the suite would notice.
    """
    assert set(_added_columns()) == set(EXPECTED_COLUMNS), (
        "the migration's columns and this file's guarded set have diverged; add the "
        "new column to EXPECTED_COLUMNS so it inherits the guards below."
    )


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


def test_a_row_written_without_a_kind_does_not_claim_an_event_led_it(migrated_db):
    """#4836's half of the same property, and it is not hypothetical.

    44% of answered searches carry a NULL `top_result_id` today precisely because
    they were led by a team or a futures market. A `server_default='event'` here
    would relabel every one of them as event-led — inventing the discriminator's
    answer for exactly the rows it was added to disambiguate.
    """
    migrated_db.execute("INSERT INTO search_query_logs (query) VALUES ('pats')")
    (kind,) = migrated_db.execute(
        "SELECT top_result_kind FROM search_query_logs"
    ).fetchone()

    assert kind is None, (
        f"an unrecorded row read {kind!r}. NULL must keep meaning 'not recorded', "
        "never 'led by an event'."
    )
    assert kind not in TOP_RESULT_KINDS


@pytest.mark.parametrize("name", sorted(EXPECTED_COLUMNS))
def test_the_migration_declares_no_server_default_and_stays_nullable(migrated_db, name):
    """The two properties that make the NULLs above reachable, read off the migration.

    Behavioural cover above proves the CURRENT shape; this proves the migration
    is not merely getting away with it — a NOT NULL column with no default would
    also fail the inserts above, but for the wrong reason and with a confusing
    message.
    """
    _table, column = _added_column(name)
    assert column.server_default is None, (
        f"{name}: server_default={column.server_default!r}. A default on this column "
        "converts 'unknown' into a positive claim about every row that predates the stamp."
    )
    assert column.nullable is True
    assert column.index in (None, False), (
        f"{name}: no reader measured; an index here is cost with no consumer"
    )


@pytest.mark.parametrize("name,width", sorted(EXPECTED_COLUMNS.items()))
def test_the_column_accepts_the_full_width_its_writer_will_write(migrated_db, name, width):
    """Each store must accept everything its future writer can hand it.

    A store narrower than its writer's bound refuses the write, and a guard that
    refuses to write freezes the old value — here, freezes NULL — so the column
    would silently keep reading 'unknown' for exactly the traffic it was added to
    name.
    """
    _table, column = _added_column(name)
    assert column.type.length == width

    value = "w" * width
    migrated_db.execute(
        f"INSERT INTO search_query_logs (query, {name}) VALUES ('red sox', ?)", (value,)
    )
    (stored,) = migrated_db.execute(
        f"SELECT {name} FROM search_query_logs ORDER BY id DESC LIMIT 1"
    ).fetchone()
    assert stored == value


def test_top_result_kind_holds_every_value_it_is_meant_to_discriminate(migrated_db):
    """The width is only correct relative to the vocabulary it must carry.

    `'event_concept'` is the longest of the four and the one a narrower column
    would truncate into `'event_concep'` — a value that reads as a typo rather
    than as an overflow, and that silently collapses toward `'event'` in any
    prefix comparison a consumer writes.
    """
    _table, column = _added_column("top_result_kind")
    for kind in TOP_RESULT_KINDS:
        assert len(kind) <= column.type.length, f"{kind!r} does not fit in {column.type}"
        migrated_db.execute(
            "INSERT INTO search_query_logs (query, top_result_kind) VALUES ('q', ?)",
            (kind,),
        )
    stored = {
        row[0]
        for row in migrated_db.execute(
            "SELECT top_result_kind FROM search_query_logs WHERE top_result_kind IS NOT NULL"
        )
    }
    assert stored == set(TOP_RESULT_KINDS)


@pytest.mark.parametrize("name", sorted(EXPECTED_COLUMNS))
def test_the_model_and_the_migration_can_hold_the_same_value(migrated_db, name):
    """Two declarations of one column; a drift between them is a production error.

    Asserted as capability rather than as a field-by-field comparison: what
    matters is that a value the migration's column accepts is a value the ORM
    column accepts, and that NEITHER declaration carries a default. The ORM half
    is the one that would ship a `server_default` without touching `alembic/` at
    all, so it needs its own assertion and not an inherited one.
    """
    from app.models.models import SearchQueryLog

    orm_column = SearchQueryLog.__table__.c[name]
    _table, migration_column = _added_column(name)

    assert orm_column.server_default is None
    assert orm_column.default is None, (
        "a Python-side default is the same defect wearing a different hat — it "
        "stamps at INSERT time from the application, where nothing knows the origin."
    )
    assert orm_column.nullable is True
    assert orm_column.type.length >= migration_column.type.length


def test_downgrade_drops_exactly_what_upgrade_added(migrated_db):
    """The D51 undo line (`alembic downgrade <parent>`) must be exact.

    An asymmetric pair here does not fail at test time or at upgrade time — it
    fails in the Heroku release phase during a rollback, which is the worst place
    to find it and the one place nobody is watching. With two columns the cheap
    mistake is dropping one and forgetting the other, which leaves a downgraded
    database that no longer matches any revision.
    """
    added = _added_columns()
    recorder = _recorded("downgrade")

    dropped = []
    for kind, (down_table, name, _kwargs) in recorder.ops:
        assert kind == "drop_column", f"downgrade() emitted {kind}, not drop_column"
        assert name in added, f"downgrade() drops {name!r}, which upgrade() never added"
        assert down_table == added[name][0]
        dropped.append(name)

    assert set(dropped) == set(added), (
        f"upgrade() adds {sorted(added)} but downgrade() drops {sorted(dropped)}"
    )
    assert dropped == list(reversed(list(added))), (
        "downgrade() should unwind in reverse order of upgrade(); it is the only "
        "ordering that stays correct if a future column gains a dependency."
    )


def test_the_revision_chain_and_id_are_shippable():
    """Gotcha #1 (≤32 chars) and the chain this links into, in one place.

    THE PARENT USED TO BE PINNED TO A LITERAL (``== "containers_phase1"``) AND
    THAT IS WHY THIS BRANCH ALMOST BROKE THE DEPLOY. LAT-P232's
    ``add_client_timing_events`` landed on master while the branch sat unmerged
    and chained onto ``containers_phase1`` as well, so after the rebase two
    revisions claimed the same parent: a branchpoint, two heads, and a Heroku
    release phase that fails outright. A literal-parent assertion cannot see
    that — it passes on exactly the graph that does not deploy, and fails on
    every harmless re-point. It asserts a POSITION; the deploy turns on a
    PROPERTY.

    So the property is asserted against the revision graph, which is where a
    branchpoint lives:

    1. **One head** — the condition that breaks the release phase.
    2. **This revision is reachable from it** — so a "single head" that simply
       orphaned this migration cannot read as success.

    Both survive the next migration chaining on; neither survives a real
    branchpoint. This is the third time the repo has learned this — see
    ``test_uq_event_espn_id_migration.py::test_is_an_ancestor_of_the_single_head``
    and the docstring on
    ``test_containers_migration_real_postgres.py::test_head_is_single_after_this_migration``,
    whose own conclusion was: state the property generally so the next migration
    does not have to come back here. This is that, one link along.
    """
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    mod = _load_migration()
    assert len(mod.revision) <= 32
    assert mod.revision == "search_log_origin"
    assert mod.down_revision, "this migration must chain onto something"

    script = ScriptDirectory.from_config(Config(str(ROOT / "alembic.ini")))

    heads = script.get_heads()
    assert len(heads) == 1, (
        f"expected a single head, got {len(heads)}: {heads}. Two heads fail the "
        "Heroku release phase outright — nothing deploys. A migration added on a "
        "branch must chain onto the CURRENT head, and rebasing does not do that "
        "for you: the parent is data in the migration file, not a position in "
        "git history."
    )

    reachable = {rev.revision for rev in script.iterate_revisions(heads[0], "base")}
    assert mod.revision in reachable, (
        f"{mod.revision} is not reachable from the single head {heads[0]!r} — it "
        "is orphaned, so the release phase would never run it."
    )


def test_the_shipped_undo_line_names_the_real_parent():
    """The D51 undo line in the migration's own docstring must BE runnable.

    ``alembic downgrade <rev>`` is the one-command restore D51(b) requires, and
    it is prose — so it is the half of a re-point that is silently forgotten.
    A re-point that updates ``down_revision`` and leaves the docstring behind
    ships an undo line that rolls back to a revision this migration no longer
    sits above: it either errors or unwinds the wrong distance, and it does so
    during a rollback, which is the worst moment to discover it and the one
    nobody is watching.

    Both halves moved by hand in the 2026-09-12 re-point. This is what makes
    that a fact about the file rather than a thing someone remembered.
    """
    mod = _load_migration()
    text = MIGRATION_PATH.read_text()

    undo_lines = re.findall(r"alembic downgrade (\S+)", text)
    assert undo_lines, "the migration must ship its D51 undo line in the docstring"
    assert set(undo_lines) == {mod.down_revision}, (
        f"the docstring's undo line(s) name {sorted(set(undo_lines))} but "
        f"down_revision is {mod.down_revision!r} — the shipped restore command "
        "would unwind to the wrong revision."
    )
