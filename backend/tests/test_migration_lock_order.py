"""Every migration takes its tables in the app's lock order (#2782).

THE DEFECT THIS CATCHES. ``link_loss_receipts`` locked
``market_match_receipts`` (2 ADD COLUMN + 1 ALTER + 2 CREATE INDEX) and only
then reached for ``futures_markets``. Live code holds those two the other way
round, so the release phase and ``match_prediction_markets`` formed a lock
cycle. Four Heroku releases failed — v4016-v4019, CI green on every one — and
production sat on stale code for ~50 minutes, blocking every lane. No test
existed that could see it, because nothing was wrong with the SQL: the defect
was entirely in the ORDER of two statements that are individually correct.

THREE ARMS, AND THE THIRD IS THE ONE THAT ROTS. The detector is exercised
against synthetic sources it must flag and synthetic sources it must not
(:class:`TestTheDetector`); the corpus is swept (:class:`TestEveryMigration`);
and the sweep is proved non-vacuous (:class:`TestTheSweepIsNotVacuous`) — a
scan whose ranked-table set is empty, or whose table names are typos, passes
happily forever while enforcing nothing.

The permanent red-first anchor is :data:`THE_SHIPPED_INVERSION` — the body of
``link_loss_receipts.upgrade()`` exactly as it shipped and failed. That specimen
cannot be fixed away by the repair, so it keeps the detector honest after the
real file is clean.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from app.utils.migration_lock_order import (
    LOCK_ORDER,
    MIGRATION_FUNCTIONS,
    describe,
    first_acquisitions,
    rank,
    tables_in_sql,
    touches_ranked_table,
    unreadable_in_file,
    violations,
    violations_in_file,
)

VERSIONS = Path(__file__).resolve().parents[1] / "alembic" / "versions"
MODELS = Path(__file__).resolve().parents[1] / "app" / "models" / "models.py"


def _migrations() -> list[Path]:
    return sorted(p for p in VERSIONS.glob("*.py") if p.name != "__init__.py")


#: ``link_loss_receipts.upgrade()`` as it shipped on 2026-09-02 and deadlocked
#: four releases. Kept verbatim so the guard has a specimen that cannot be
#: repaired out from under it.
THE_SHIPPED_INVERSION = """
def upgrade() -> None:
    op.add_column(
        "market_match_receipts",
        sa.Column("previous_event_id", sa.Integer(), nullable=True),
    )
    op.create_index(
        "ix_match_receipt_prev_event",
        "market_match_receipts",
        ["previous_event_id"],
    )
    op.add_column(
        "futures_markets",
        sa.Column("settled_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_futures_markets_settled_at", "futures_markets", ["settled_at"]
    )
"""

THE_REPAIRED_ORDER = """
def upgrade() -> None:
    op.add_column(
        "futures_markets",
        sa.Column("settled_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_futures_markets_settled_at", "futures_markets", ["settled_at"]
    )
    op.add_column(
        "market_match_receipts",
        sa.Column("previous_event_id", sa.Integer(), nullable=True),
    )
    op.create_index(
        "ix_match_receipt_prev_event",
        "market_match_receipts",
        ["previous_event_id"],
    )
"""


class TestTheDetector:
    """Both arms. A detector that only ever says "clean" is not a detector."""

    def test_the_shipped_inversion_is_flagged(self):
        found = violations(THE_SHIPPED_INVERSION)
        assert len(found) == 1, describe(found)
        assert found[0].held.table == "market_match_receipts"
        assert found[0].taken.table == "futures_markets"

    def test_the_repaired_order_is_clean(self):
        assert violations(THE_REPAIRED_ORDER) == []

    def test_the_message_names_both_tables_and_both_lines(self):
        # A guard whose failure text does not say what to change costs the next
        # deploy the same fifty minutes in diagnosis instead of in retries.
        message = str(violations(THE_SHIPPED_INVERSION)[0])
        assert "market_match_receipts" in message
        assert "futures_markets" in message
        assert "#2782" in message

    def test_returning_to_a_table_already_held_is_free(self):
        # Once the migration holds ACCESS EXCLUSIVE it holds it for the whole
        # transaction, so a later statement against the same table acquires
        # nothing. Flagging it would red the natural spelling of "add the
        # column, then index it, then come back for the constraint".
        source = """
def upgrade():
    op.add_column("futures_markets", sa.Column("a", sa.Integer()))
    op.add_column("market_match_receipts", sa.Column("b", sa.Integer()))
    op.create_index("ix_a", "futures_markets", ["a"])
"""
        assert violations(source) == []

    def test_unranked_tables_are_not_constrained(self):
        # Only measured pairs are ranked; an invented rank would red honest
        # migrations for a reason nobody can check.
        source = """
def upgrade():
    op.add_column("users", sa.Column("a", sa.Integer()))
    op.add_column("futures_markets", sa.Column("b", sa.Integer()))
    op.add_column("teams", sa.Column("c", sa.Integer()))
"""
        assert violations(source) == []
        assert [a.table for a in first_acquisitions(source)] == ["futures_markets"]

    def test_the_third_rank_is_enforced_too(self):
        source = """
def upgrade():
    op.add_column("market_link_changes", sa.Column("a", sa.Integer()))
    op.add_column("market_match_receipts", sa.Column("b", sa.Integer()))
"""
        found = violations(source)
        assert len(found) == 1, describe(found)
        assert found[0].taken.table == "market_match_receipts"

    def test_keyword_spellings_are_read_as_well_as_positional(self):
        # Alembic accepts both. A guard that reads only one spelling is a guard
        # with a documented bypass.
        source = """
def upgrade():
    op.drop_index("ix_x", table_name="market_match_receipts")
    op.drop_column(table_name="futures_markets", column_name="settled_at")
"""
        assert len(violations(source)) == 1

    def test_raw_sql_is_read(self):
        source = """
def upgrade():
    op.execute("ALTER TABLE market_match_receipts ADD COLUMN x integer")
    op.execute("ALTER TABLE futures_markets ADD COLUMN y integer")
"""
        assert len(violations(source)) == 1

    def test_sql_comments_do_not_count_as_statements(self):
        # Gotcha #149's lesson one table over: a guard that reads prose reports
        # on prose. The comment must not create a phantom acquisition that
        # inverts an otherwise-correct migration.
        source = """
def upgrade():
    op.execute("-- ALTER TABLE market_match_receipts is done elsewhere\\n"
               "ALTER TABLE futures_markets ADD COLUMN y integer")
"""
        assert violations(source) == []

    def test_a_helper_in_the_same_file_cannot_hide_ddl(self):
        # One level of indirection is all it takes to slip past a source scan.
        source = """
def _receipts():
    op.add_column("market_match_receipts", sa.Column("b", sa.Integer()))

def upgrade():
    _receipts()
    op.add_column("futures_markets", sa.Column("a", sa.Integer()))
"""
        assert len(violations(source)) == 1

    def test_downgrade_is_checked_on_its_own_terms(self):
        source = THE_REPAIRED_ORDER + """
def downgrade():
    op.drop_column("market_match_receipts", "previous_event_id")
    op.drop_column("futures_markets", "settled_at")
"""
        assert violations(source, function="upgrade") == []
        assert len(violations(source, function="downgrade")) == 1
        assert len(violations_in_file(source)) == 1

    def test_a_computed_statement_is_reported_as_unreadable_not_as_clean(self):
        source = """
def upgrade():
    op.execute(build_sql())
"""
        assert unreadable_in_file(source) == [("upgrade", 3)]

    @pytest.mark.parametrize(
        "sql,expected",
        [
            (
                "ALTER TABLE public.futures_markets ADD COLUMN x int",
                ["futures_markets"],
            ),
            ('ALTER TABLE "futures_markets" DROP COLUMN x', ["futures_markets"]),
            (
                "ALTER TABLE IF EXISTS ONLY futures_markets RENAME x TO y",
                ["futures_markets"],
            ),
            ("CREATE INDEX ix_q ON futures_markets (x)", ["futures_markets"]),
            ("UPDATE market_match_receipts SET x = 1", ["market_match_receipts"]),
            ("DELETE FROM market_link_changes", ["market_link_changes"]),
            (
                "LOCK TABLE futures_markets IN ACCESS EXCLUSIVE MODE",
                ["futures_markets"],
            ),
        ],
    )
    def test_the_sql_reader_recognises_the_spellings_that_appear_here(
        self, sql, expected
    ):
        assert tables_in_sql(sql) == expected


class TestEveryMigration:
    """The corpus sweep — the arm that has to stay green forever."""

    @pytest.mark.parametrize("path", _migrations(), ids=lambda p: p.name)
    def test_the_migration_takes_its_tables_in_lock_order(self, path: Path):
        source = path.read_text(encoding="utf-8")
        found = violations_in_file(source)
        assert not found, (
            f"{path.name} acquires tables out of LOCK_ORDER:\n{describe(found)}\n"
            "Reorder the DDL, or split the contended tables into separate "
            "revisions. See app/utils/migration_lock_order.py."
        )

    @pytest.mark.parametrize("path", _migrations(), ids=lambda p: p.name)
    def test_a_migration_that_reaches_a_hot_table_is_statically_readable(
        self, path: Path
    ):
        # The order can only be PROVEN for statements this guard can read. A
        # computed statement next to a hot table is exactly where an unprovable
        # order becomes a deploy that hangs.
        source = path.read_text(encoding="utf-8")
        if not touches_ranked_table(source):
            return
        unreadable = unreadable_in_file(source)
        assert not unreadable, (
            f"{path.name} touches {LOCK_ORDER} but builds SQL at run time at "
            f"{unreadable}; the lock order cannot be checked. Write the DDL as "
            "a literal, or move the computed statement to its own revision."
        )


class TestTheSweepIsNotVacuous:
    """A green sweep over nothing is the failure mode this class exists for."""

    def test_the_corpus_was_actually_found(self):
        assert len(_migrations()) >= 100, len(_migrations())

    def test_every_ranked_name_is_a_real_table(self):
        # One typo in LOCK_ORDER silently disarms the whole guard: the misspelt
        # name matches nothing, every migration reads as unranked, and the
        # sweep stays green while enforcing nothing.
        declared = {
            node.value.value
            for node in ast.walk(ast.parse(MODELS.read_text(encoding="utf-8")))
            if isinstance(node, ast.Assign)
            and any(
                isinstance(t, ast.Name) and t.id == "__tablename__"
                for t in node.targets
            )
            and isinstance(node.value, ast.Constant)
        }
        assert declared, "no __tablename__ found — the check itself is broken"
        assert set(LOCK_ORDER) <= declared, set(LOCK_ORDER) - declared

    def test_the_ranks_are_distinct_and_ordered(self):
        assert [rank(t) for t in LOCK_ORDER] == list(range(len(LOCK_ORDER)))
        assert rank("events") is None

    def test_real_migrations_do_reach_the_ranked_tables(self):
        touching = [
            p.name
            for p in _migrations()
            if touches_ranked_table(p.read_text(encoding="utf-8"))
        ]
        assert len(touching) >= 20, touching

    def test_at_least_one_real_migration_orders_two_ranked_tables(self):
        # Without this the corpus sweep could be green because no file has two
        # ranked tables to order — a check that never runs on real input.
        multi = [
            p.name
            for p in _migrations()
            if any(
                len(first_acquisitions(p.read_text(encoding="utf-8"), function=f)) >= 2
                for f in MIGRATION_FUNCTIONS
            )
        ]
        assert multi, "no migration orders two ranked tables; the sweep is vacuous"
        assert "link_loss_receipts.py" in multi, multi

    def test_the_repaired_migration_is_the_one_that_was_broken(self):
        # Pins the repair itself: link_loss_receipts must take futures_markets
        # first in BOTH directions, which is the change #2782 asked for.
        source = (VERSIONS / "link_loss_receipts.py").read_text(encoding="utf-8")
        for function in MIGRATION_FUNCTIONS:
            ordered = [a.table for a in first_acquisitions(source, function=function)]
            assert ordered == ["futures_markets", "market_match_receipts"], (
                function,
                ordered,
            )
