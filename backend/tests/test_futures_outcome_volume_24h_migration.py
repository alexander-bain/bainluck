"""`futures_outcomes.volume_24h` / `.volume_24h_at`: does an unmeasured leg read UNKNOWN, or does it read "nobody is trading this"?

#7747 step 1. The column exists because two serve-time-only attempts at #7747's
ship were falsified against the venue (CERT-3242, CERT-3244) for the same
structural reason: **no stored field distinguishes a leg being traded at its ask
from one that is not.** The follow-up ship teaches
``utils/futures_unsupported_price`` to WITHHOLD a price on the strength of a
``volume_24h`` that reads zero.

🔴 THAT CONSUMER IS WHAT MAKES A DEFAULT ON THIS COLUMN DANGEROUS RATHER THAN
UNTIDY, and it is the single edit this file exists to stop. ``volume_24h`` has a
value — ``0`` — that is not a neutral placeholder but the exact reading the
consumer treats as proof that nobody is trading a leg. A
``server_default="0"`` would hand that proof to all **5,079,690** rows that
predate the first capture, in one statement, and every one of them would read as
*"the venue says this is untraded"* when the truth is *"we have never asked"*.
That is gotcha #53's empty-200 in DDL form, and it fails in the withholding
direction: prices vanish off boards fleet-wide. The same edit on
``volume_24h_at`` (``server_default=sa.func.now()``) is the same defect one
column over — it would stamp every unmeasured row as measured at migration time,
which is precisely the freshness claim the stamp was split out to make honest.

Nothing reads or writes either column yet, so no consumer test can protect them.
That is exactly when a column is easiest to break: the next person here sees a
nullable numeric with no default, reads it as an oversight, and tidies it — or
sees two decimal places on a "volume" and rounds them off. This file is the
reason they cannot do either.

═══ WHAT IS ACTUALLY PROVEN HERE, AND HOW ═══

The DDL is composed from the ``sa.Column`` objects the migration ITSELF hands to
``op.add_column``, never from constants in this file — otherwise these assertions
would prove that a string in this test describes a column, which is not a fact
about production. The substrate is a real SQLite database rather than a mock,
because the property under test is what an engine DOES to a row that omits a
column, and only an engine answers that; SQLite and Postgres agree on the two
semantics in play (an omitted column with no default is NULL; a declared DEFAULT
is applied on omission).

The pre-migration ``CREATE TABLE`` is written out literally on purpose: it is the
shipped shape this migration composes ONTO. Deriving it from today's model would
make the test tautological the moment the follow-up ship adds the mapped columns.

Shape and method follow ``test_search_log_origin_migration.py``, which is the
same class of attended additive migration; the assertions that turn on a string
WIDTH there turn on numeric RANGE here.
"""

from __future__ import annotations

import importlib.util
import re
import sqlite3
from decimal import Decimal
from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy.dialects.sqlite import dialect as sqlite_dialect

ROOT = Path(__file__).resolve().parents[1]
MIGRATION_PATH = (
    ROOT / "alembic" / "versions" / "fo_volume_24h_add_per_leg_venue_volume.py"
)

#: The complete set of columns this migration is allowed to add. Enumerated so a
#: third column added to the migration but not here fails loudly
#: (`test_upgrade_adds_exactly_the_columns_this_file_guards`) rather than shipping
#: with no default/nullable guard at all.
EXPECTED_COLUMNS = ("volume_24h", "volume_24h_at")

#: `futures_outcomes` as it stands on production BEFORE this migration —
#: `app/models/models.py::FuturesOutcome` minus the two columns being added.
#: Literal, not derived: see the module docstring.
PRE_MIGRATION_TABLE = """
    CREATE TABLE futures_outcomes (
        id INTEGER PRIMARY KEY,
        market_id INTEGER,
        external_id VARCHAR,
        name VARCHAR,
        team_id INTEGER,
        current_probability NUMERIC,
        current_american_odds INTEGER,
        current_yes_bid NUMERIC,
        current_yes_ask NUMERIC,
        opening_probability NUMERIC,
        opening_american_odds INTEGER,
        opening_captured_at TIMESTAMP,
        probability_change_24h NUMERIC,
        rank INTEGER,
        rank_change_24h INTEGER,
        is_winner BOOLEAN,
        last_updated TIMESTAMP,
        calibration_probability NUMERIC,
        resolution_source VARCHAR,
        opening_source VARCHAR,
        volume INTEGER,
        price_changed_at TIMESTAMP
    )
"""


def _load_migration():
    spec = importlib.util.spec_from_file_location("fo_volume_24h", MIGRATION_PATH)
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
    """The reconciliation that keeps every other test in this file honest."""
    assert set(_added_columns()) == set(EXPECTED_COLUMNS), (
        "the migration's columns and this file's guarded set have diverged; add the "
        "new column to EXPECTED_COLUMNS so it inherits the guards below."
    )


def test_an_unmeasured_leg_does_not_claim_the_venue_reported_zero_volume(migrated_db):
    """THE assertion this file exists for (gotcha #53; #7747's consumer).

    Every one of the 5,079,690 rows on production predates the first capture, so
    if this column defaulted to 0 the table would assert "the venue reports no
    trading" for all of them — and the follow-up ship WITHHOLDS a price on
    exactly that reading. A default here does not merely mislabel a row; it
    blanks prices fleet-wide.
    """
    migrated_db.execute(
        "INSERT INTO futures_outcomes (external_id) VALUES ('KXATP-27USO-MEN')"
    )
    (volume,) = migrated_db.execute(
        "SELECT volume_24h FROM futures_outcomes"
    ).fetchone()

    assert volume is None, (
        f"an unmeasured leg read {volume!r}. NULL means 'we never asked the venue', "
        "which is the truth; 0 means 'the venue says nobody is trading this', which "
        "is the one value the consumer treats as proof."
    )
    assert volume != 0


def test_an_unmeasured_leg_does_not_claim_a_freshly_observed_volume(migrated_db):
    """The stamp's half of the same property.

    `volume_24h_at` was split out from `last_updated` so a volume figure carries
    its own observation time (see the migration's "WHY TWO COLUMNS"). A
    `server_default=now()` would stamp every never-measured row as measured at
    migration time — reintroducing, in the fix for it, the exact conflation this
    ship was BLOCKed twice for.
    """
    migrated_db.execute(
        "INSERT INTO futures_outcomes (external_id) VALUES ('KXATP-27USO-MEN')"
    )
    (stamp,) = migrated_db.execute(
        "SELECT volume_24h_at FROM futures_outcomes"
    ).fetchone()

    assert stamp is None, (
        f"an unmeasured leg read {stamp!r}. A stamp on a reading that never "
        "happened makes a stale zero look like a fresh one."
    )


@pytest.mark.parametrize("name", EXPECTED_COLUMNS)
def test_the_migration_declares_no_server_default_and_stays_nullable(migrated_db, name):
    """The two properties that make the NULLs above reachable, read off the migration.

    Behavioural cover above proves the CURRENT shape; this proves the migration is
    not merely getting away with it — a NOT NULL column with no default would also
    fail the inserts above, but for the wrong reason and with a confusing message.
    """
    _table, column = _added_column(name)
    assert column.server_default is None, (
        f"{name}: server_default={column.server_default!r}. A default on this column "
        "converts 'we never asked' into a positive claim about all 5,079,690 rows "
        "that predate the first capture."
    )
    assert column.nullable is True
    assert column.index in (
        None,
        False,
    ), f"{name}: no reader measured; an index here is cost with no consumer"


def test_the_migration_adds_no_default_anywhere_even_if_a_column_is_renamed():
    """The guard above is parametrized by name; this one cannot be sidestepped.

    `EXPECTED_COLUMNS` is reconciled, so a renamed column fails loudly — but a
    rename PLUS an `EXPECTED_COLUMNS` edit passes every test above while shipping
    a default. Asserted over whatever `upgrade()` emitted, so it holds for columns
    this file has never heard of.
    """
    for name, (_table, column) in _added_columns().items():
        assert column.server_default is None, f"{name} ships a server_default"
        assert column.nullable is True, f"{name} is NOT NULL"


#: The smallest non-zero 24-hour volume in the set of legs that FALSIFIED this
#: ship's two previous predicates — Congo Republic, `$0.04` (CERT-3244). It is
#: the value the column must be able to tell apart from zero.
SMALLEST_FALSIFYING_VOLUME = Decimal("0.04")


def test_a_four_cent_trade_does_not_land_in_the_column_as_untraded(migrated_db):
    """🔴 THE TYPE ASSERTION THIS FILE EXISTS FOR, AND IT IS NOT ABOUT PRECISION.

    Kalshi reports this figure as a two-decimal fixed-point string, and the
    smallest non-zero value among the legs that falsified the previous two
    predicates is Congo Republic's **$0.04**. An integer column stores that as
    **0** — the one value the consumer reads as "the venue says nobody is trading
    this leg". So a narrow column here does not lose a rounding error; it
    manufactures the exact false reading CERT-3244 BLOCKed this ship for, on one
    of the very legs the grader named.

    Asserted behaviourally (the value survives a round trip and is still
    distinguishable from zero) rather than by comparing a type name, so it holds
    for any type that can actually carry the figure.
    """
    _table, column = _added_column("volume_24h")
    assert isinstance(column.type, sa.Numeric) and not isinstance(
        column.type, (sa.Integer, sa.BigInteger)
    ), (
        f"volume_24h is {column.type!r}. An integral column floors "
        f"{SMALLEST_FALSIFYING_VOLUME} to 0, which is the withhold trigger."
    )
    assert column.type.scale == 2, (
        f"scale={column.type.scale}; the venue publishes two decimals, and a "
        "scale of 0 or 1 rounds a four-cent trade to nothing."
    )

    migrated_db.execute(
        "INSERT INTO futures_outcomes (external_id, volume_24h) VALUES ('KXCOG', ?)",
        (str(SMALLEST_FALSIFYING_VOLUME),),
    )
    (stored,) = migrated_db.execute(
        "SELECT volume_24h FROM futures_outcomes ORDER BY id DESC LIMIT 1"
    ).fetchone()
    assert Decimal(str(stored)) == SMALLEST_FALSIFYING_VOLUME
    assert (
        Decimal(str(stored)) > 0
    ), "a leg that traded four cents must not read as one that traded nothing"


def test_volume_holds_a_figure_larger_than_a_32_bit_column_would(migrated_db):
    """The other end of the range, and the repo has already paid for the narrow one.

    `FuturesMarket.volume` carries the comment "BigInteger: prod ALTER applied
    2026-07-06 (#990) — World Cup volume exceeded" the int range. A 24-hour figure
    is smaller than a lifetime one but is drawn from the same venue on the same
    contracts, so the same ceiling applies; and the failure mode of getting this
    wrong is not a truncated display but a refused INSERT, which freezes the
    column at NULL for exactly the busiest markets — the ones whose prices most
    need backing. `Numeric(14, 2)` leaves 12 integral digits, four orders of
    magnitude beyond the int32 cap that already burned #990.
    """
    _table, column = _added_column("volume_24h")
    integral_digits = column.type.precision - column.type.scale
    assert integral_digits >= 10, (
        f"only {integral_digits} integral digits; #990 overflowed int32 (10 digits) "
        "on real World Cup volume."
    )

    beyond_int32 = Decimal(2**31 + 1)
    migrated_db.execute(
        "INSERT INTO futures_outcomes (external_id, volume_24h) VALUES ('KXSB-27', ?)",
        (str(beyond_int32),),
    )
    (stored,) = migrated_db.execute(
        "SELECT volume_24h FROM futures_outcomes ORDER BY id DESC LIMIT 1"
    ).fetchone()
    assert Decimal(str(stored)) == beyond_int32


def test_the_stamp_is_timezone_aware():
    """A naive stamp compared against an aware `last_updated` raises at serve time.

    Every other timestamp the consumer will read alongside this one
    (`last_updated`, `price_changed_at`) is `timestamptz`. Python refuses to
    subtract a naive datetime from an aware one, so a naive column here turns the
    first freshness comparison into a 500 on the futures detail page rather than a
    wrong answer — and it would do it only on rows that have been captured, i.e.
    not on any row that exists today.
    """
    _table, column = _added_column("volume_24h_at")
    assert isinstance(column.type, sa.DateTime)
    assert (
        column.type.timezone is True
    ), "volume_24h_at must be timestamptz to compare against last_updated"


def test_downgrade_drops_exactly_what_upgrade_added(migrated_db):
    """The D51 undo line (`alembic downgrade search_log_origin`) must be exact.

    An asymmetric pair does not fail at test time or at upgrade time — it fails in
    the Heroku release phase during a rollback, which is the worst place to find it
    and the one place nobody is watching. With two columns the cheap mistake is
    dropping one and forgetting the other, leaving a downgraded database that
    matches no revision.
    """
    added = _added_columns()
    recorder = _recorded("downgrade")

    dropped = []
    for kind, (down_table, name, _kwargs) in recorder.ops:
        assert kind == "drop_column", f"downgrade() emitted {kind}, not drop_column"
        assert name in added, f"downgrade() drops {name!r}, which upgrade() never added"
        assert down_table == added[name][0]
        dropped.append(name)

    assert set(dropped) == set(
        added
    ), f"upgrade() adds {sorted(added)} but downgrade() drops {sorted(dropped)}"
    assert dropped == list(reversed(list(added))), (
        "downgrade() should unwind in reverse order of upgrade(); it is the only "
        "ordering that stays correct if a future column gains a dependency."
    )


def test_the_revision_chain_and_id_are_shippable():
    """Gotcha #1 (≤32 chars) and the chain this links into.

    The parent is asserted as a PROPERTY of the revision graph, not as a literal
    position: a literal-parent assertion passes on exactly the graph that does not
    deploy (two revisions claiming one parent after a rebase) and fails on every
    harmless re-point. See `test_search_log_origin_migration.py`'s own docstring —
    this is the third time the repo has learned it.
    """
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    mod = _load_migration()
    assert len(mod.revision) <= 32
    assert mod.revision == "fo_volume_24h"
    assert mod.down_revision, "this migration must chain onto something"

    script = ScriptDirectory.from_config(Config(str(ROOT / "alembic.ini")))

    heads = script.get_heads()
    assert len(heads) == 1, (
        f"expected a single head, got {len(heads)}: {heads}. Two heads fail the "
        "Heroku release phase outright — nothing deploys. A migration added on a "
        "branch must chain onto the CURRENT head, and rebasing does not do that "
        "for you: the parent is data in the migration file, not a position in git "
        "history."
    )

    reachable = {rev.revision for rev in script.iterate_revisions(heads[0], "base")}
    assert mod.revision in reachable, (
        f"{mod.revision} is not reachable from the single head {heads[0]!r} — it is "
        "orphaned, so the release phase would never run it."
    )


def test_the_shipped_undo_line_names_the_real_parent():
    """The D51 undo line in the migration's own docstring must BE runnable.

    It is prose, so it is the half of a re-point that is silently forgotten, and it
    is read during a rollback — the worst moment to find it wrong.
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


def test_the_migration_creates_no_index(migrated_db):
    """Gotcha #31: an index in a Heroku release phase is the ~5-minute-timeout risk.

    This table carries 5,079,690 rows, so a non-concurrent `CREATE INDEX` here is
    exactly the May 22 outage. `ADD COLUMN ... NULL` with no default is
    catalog-only and instant; that property is the reason this migration is safe
    on a table this size, and it survives only while nothing else is added to it.
    """
    recorder = _recorded("upgrade")
    kinds = {kind for kind, _args in recorder.ops}
    assert kinds == {"add_column"}, (
        f"upgrade() emits {sorted(kinds)}. Only add_column is catalog-only; anything "
        "else on a 5M-row table risks the release-phase timeout (gotcha #31), and an "
        "index must go via psql CONCURRENTLY instead."
    )
