"""The `events.espn_id` unique index: does its precondition hold, and does the invariant bite?

#2693 step 2 (lane1/058, held open by lane1/065). The migration
`uq_event_espn_id` is the structural half of "one game, one authority id" — the
half that stops the collision population re-growing after the
`authority-id-collisions` repair drains it.

═══ WHY THIS FILE EXISTS AT ALL ═══

The migration shipped once without a guard and was pulled again before it ran.
Two things about it are load-bearing and neither was tested:

* **It must REFUSE rather than let Postgres raise.** `backend/Procfile` wraps
  `alembic upgrade heads` in `|| echo` (#2741), so a raise in the release phase
  is swallowed and the deploy proceeds. The only thing that survives that
  swallowing is the *message*, in the release log a human is reading. A raise
  that says `duplicate key value violates unique constraint` names one id and no
  remedy; this one has to name the size of the problem and the rail that fixes
  it, or the swallowing costs us the whole diagnosis.
* **The index has to actually bite.** `unique=True` in an `op.create_index`
  call is an assertion about intent. What matters is whether a second row can
  still take an id that is already worn — and whether the NULLs, which are the
  ordinary state for 228,451 of 236,786 production rows, are still free to
  repeat. Those are two different questions and only a real INSERT answers
  either.

So this file tests the precondition against a stubbed bind (no Postgres in the
sandbox) and the invariant against a real SQLite database, where a partial
unique index has the same NULL semantics Postgres gives it.
"""

from __future__ import annotations

import importlib.util
import sqlite3
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory

ROOT = Path(__file__).resolve().parents[1]
MIGRATION_PATH = ROOT / "alembic" / "versions" / "uq_event_espn_id.py"


def _ddl_from(recorder) -> str:
    """Compose executable DDL from the `create_index` call the migration MADE.

    Deliberately not a hand-written constant. A constant would let the
    behavioural tests below keep passing while `unique=True` or the partial
    predicate quietly left the migration — they would be proving that a string
    in this file describes an index, which is not a fact about production.
    """
    ((name, table, columns, kwargs),) = recorder.created
    unique = "UNIQUE " if kwargs.get("unique") else ""
    where = kwargs.get("postgresql_where")
    predicate = f" WHERE {where}" if where is not None else ""
    return (
        f"CREATE {unique}INDEX {name} ON {table} " f"({', '.join(columns)}){predicate}"
    )


def _load_migration():
    spec = importlib.util.spec_from_file_location("uq_event_espn_id", MIGRATION_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _StubResult:
    def __init__(self, scalar=None, rows=()):
        self._scalar = scalar
        self._rows = list(rows)

    def scalar(self):
        return self._scalar

    def all(self):
        return self._rows


class _StubBind:
    """Answers the two queries `upgrade()` asks, and records that it asked."""

    def __init__(self, contested: int, sample=()):
        self.contested = contested
        self.sample = sample
        self.executed: list[str] = []

    def execute(self, statement, *args, **kwargs):
        text = str(statement)
        self.executed.append(text)
        # The count query wraps the GROUP BY in a subselect; the sample query
        # selects the ids themselves. Distinguished by the aggregate.
        if "count(*) FROM (" in text:
            return _StubResult(scalar=self.contested)
        return _StubResult(rows=self.sample)


class _RecordingOp:
    """Stands in for `alembic.op`, recording DDL instead of emitting it."""

    def __init__(self, bind):
        self._bind = bind
        self.created: list[tuple] = []
        self.dropped: list[tuple] = []
        #: One INTERLEAVED log, because `created` and `dropped` read separately
        #: cannot see ordering. `downgrade()` swapping its two statements leaves
        #: both of those lists identical and is a real defect: it opens a window
        #: with no index on `espn_id` at all.
        self.ops: list[tuple[str, str]] = []

    @property
    def executed(self) -> list[str]:
        """The queries the migration asked, in order."""
        return self._bind.executed

    def get_bind(self):
        return self._bind

    def create_index(self, name, table, columns, **kwargs):
        self.created.append((name, table, tuple(columns), kwargs))
        self.ops.append(("create", name))

    def drop_index(self, name, **kwargs):
        self.dropped.append((name, kwargs))
        self.ops.append(("drop", name))


def _run(monkeypatch, contested: int, sample=(), direction: str = "upgrade"):
    mod = _load_migration()
    bind = _StubBind(contested, sample)
    recorder = _RecordingOp(bind)
    monkeypatch.setattr(mod, "op", recorder)
    getattr(mod, direction)()
    return recorder


class TestThePrecondition:
    """A contested column must stop the migration, and say why in one message."""

    def test_refuses_when_any_id_is_contested(self, monkeypatch):
        with pytest.raises(RuntimeError) as excinfo:
            _run(monkeypatch, contested=8, sample=[("401873756", 3), ("748503", 2)])

        message = str(excinfo.value)
        # The SIZE of the problem, not just that there is one.
        assert "8" in message
        # The REMEDY, in the release log the operator is already reading.
        assert "authority-id-collisions" in message
        # The WORST OFFENDERS, so the first diagnostic step needs no query.
        assert "401873756" in message and "3 rows" in message

    def test_refusal_creates_no_index_and_drops_nothing(self, monkeypatch):
        mod = _load_migration()
        bind = _StubBind(1, [("401873756", 3)])
        recorder = _RecordingOp(bind)
        monkeypatch.setattr(mod, "op", recorder)

        with pytest.raises(RuntimeError):
            mod.upgrade()

        # A half-applied migration is the failure mode gotcha #31 is about.
        # In particular the LOOSE index must survive: dropping it and then
        # failing to create the unique one would leave `espn_sync`'s lookup
        # column with no index at all.
        assert recorder.created == []
        assert recorder.dropped == []

    def test_asks_the_precondition_before_any_ddl(self, monkeypatch):
        recorder = _run(monkeypatch, contested=0)
        assert recorder.executed, "upgrade() emitted DDL without asking the question"
        assert "count(*) FROM (" in recorder.executed[0]

    def test_does_not_read_the_sample_when_there_is_nothing_to_report(
        self, monkeypatch
    ):
        # The sample query is a diagnostic, not part of the happy path. Running
        # it unconditionally would be a second full GROUP BY over `events` on
        # every deploy for no reader.
        recorder = _run(monkeypatch, contested=0)
        assert len(recorder.executed) == 1


class TestTheDDLShape:
    """What it builds when the precondition holds."""

    def test_creates_a_partial_unique_index(self, monkeypatch):
        recorder = _run(monkeypatch, contested=0)

        assert len(recorder.created) == 1
        name, table, columns, kwargs = recorder.created[0]
        assert name == "uq_events_espn_id"
        assert table == "events"
        assert columns == ("espn_id",)
        assert kwargs.get("unique") is True
        # Partial, because NULL is the ordinary state for 228,451 of 236,786
        # production rows and the index should be the size of the population
        # that actually has the property.
        where = str(kwargs.get("postgresql_where"))
        assert "espn_id IS NOT NULL" in where

    def test_drops_the_now_redundant_loose_index(self, monkeypatch):
        recorder = _run(monkeypatch, contested=0)
        # Same interleaving argument as the downgrade: the unique index is
        # created BEFORE the loose one goes, so the column is never unindexed.
        assert recorder.ops == [
            ("create", "uq_events_espn_id"),
            ("drop", "ix_events_espn_id"),
        ]

    def test_downgrade_restores_the_loose_index_before_dropping_the_unique_one(
        self, monkeypatch
    ):
        recorder = _run(monkeypatch, contested=0, direction="downgrade")

        # Order matters and is the whole point: `espn_sync` looks up through
        # this column on every correction, so there must never be a window in
        # which it has no index at all. Asserted on the INTERLEAVED log —
        # checking `created` and `dropped` separately passes just as happily
        # when the two statements are swapped, which is the defect.
        assert recorder.ops == [
            ("create", "ix_events_espn_id"),
            ("drop", "uq_events_espn_id"),
        ]

    def test_downgrade_asks_no_precondition(self, monkeypatch):
        # Going back must always be possible, whatever the data says.
        recorder = _run(monkeypatch, contested=999, direction="downgrade")
        assert recorder.executed == []


class TestTheInvariantBites:
    """`unique=True` is intent. These are INSERTs.

    Run against SQLite, which supports partial indexes and gives NULLs the same
    "distinct from each other" treatment Postgres does — so both halves of the
    invariant are observable without a Postgres the sandbox cannot reach.
    """

    @staticmethod
    def _db(monkeypatch):
        recorder = _run(monkeypatch, contested=0)
        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE TABLE events (id INTEGER PRIMARY KEY, espn_id TEXT)")
        conn.execute(_ddl_from(recorder))
        return conn

    def test_a_second_row_cannot_take_an_id_already_worn(self, monkeypatch):
        conn = self._db(monkeypatch)
        conn.execute("INSERT INTO events VALUES (1, '401873756')")
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("INSERT INTO events VALUES (2, '401873756')")

    def test_many_rows_may_carry_no_id_at_all(self, monkeypatch):
        # 228,451 production rows do, so if this were ever false it would be a
        # site-wide write outage rather than a subtle defect.
        #
        # Worth being exact about what holds it up: it is NOT the partial
        # clause. Both Postgres and SQLite treat NULLs as distinct from one
        # another in a unique index, so the NULLs would repeat freely even
        # without `WHERE espn_id IS NOT NULL` — the migration's own docstring
        # says so. The partial clause buys index SIZE and an honest statement of
        # the invariant, and `test_creates_a_partial_unique_index` is the only
        # thing guarding it. This test guards the property that matters to
        # writers, which is a different property.
        conn = self._db(monkeypatch)
        for i in range(50):
            conn.execute("INSERT INTO events (id, espn_id) VALUES (?, NULL)", (i,))
        assert conn.execute("SELECT count(*) FROM events").fetchone()[0] == 50

    def test_distinct_ids_are_unaffected(self, monkeypatch):
        conn = self._db(monkeypatch)
        conn.execute("INSERT INTO events VALUES (1, '401873756')")
        conn.execute("INSERT INTO events VALUES (2, '748503')")
        assert conn.execute("SELECT count(*) FROM events").fetchone()[0] == 2

    def test_a_row_may_hand_its_id_back_and_another_may_take_it(self, monkeypatch):
        # This is exactly what the `authority-id-collisions` repair does:
        # UPDATE events SET espn_id = NULL WHERE id = :id AND espn_id = :contested.
        # The index must not make the repair's own writes impossible.
        conn = self._db(monkeypatch)
        conn.execute("INSERT INTO events VALUES (1, '401873756')")
        conn.execute("UPDATE events SET espn_id = NULL WHERE id = 1")
        conn.execute("INSERT INTO events VALUES (2, '401873756')")
        rows = conn.execute("SELECT id, espn_id FROM events ORDER BY id").fetchall()
        assert rows == [(1, None), (2, "401873756")]


class TestItIsReachable:
    """A migration that is not on the chain runs on nobody's deploy."""

    def test_is_the_single_head(self):
        script = ScriptDirectory.from_config(Config("alembic.ini"))
        heads = list(script.get_heads())
        assert heads == ["uq_event_espn_id"], f"expected a single head, got {heads}"

    def test_chains_onto_a_revision_that_exists(self):
        """Its parent must resolve, and the chain must reach base.

        Deliberately NOT pinned to a parent by NAME. This file sat out of tree
        while lane1b's `link_loss_receipts` → `link_change_history` (#2758)
        landed off `match_receipts`, turning that into a branchpoint — so the
        parent it must name is whatever the head is on the day it lands, and a
        name assertion here only ever produces a second failure to fix after the
        head assertion above already caught the real one. What must be true is
        that the parent resolves and the chain is walkable.

        Worth recording why the head check is the one that matters: a local
        `alembic heads` on an un-rebased branch reads SINGLE while the merge ref
        CI actually runs reads TWO. Rebase before trusting it.
        """
        script = ScriptDirectory.from_config(Config("alembic.ini"))
        revision = script.get_revision("uq_event_espn_id")

        assert revision.down_revision is not None, "orphan: no parent"
        parent = script.get_revision(revision.down_revision)
        assert parent is not None

        walked = [r.revision for r in script.walk_revisions("base", "uq_event_espn_id")]
        assert "uq_event_espn_id" in walked
        assert revision.down_revision in walked

    def test_revision_id_fits_alembics_column(self):
        # Gotcha #1: alembic_version.version_num is VARCHAR(32).
        assert len("uq_event_espn_id") <= 32
