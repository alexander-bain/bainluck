"""R4's merge half, asserted POSITIVELY — the merge rails repoint every event child.

Replaces ``test_r4_the_merge_rails_fk_list_is_still_short_and_that_is_a_LIVE_defect``
in ``test_prune_unanchored_duplicates_2020.py``, which pinned the defect's *numbers*
("exactly these two tables are missing") so that fixing it would go red. That shape can
only ever catch the fix. These assert the fixed state, so they catch the REGRESSION —
which is the failure mode that actually recurs, since the original list did not start
out short, it went short when the schema grew past it.

Three rails transfer-then-DELETE the loser event: ``_merge_duplicate_events_impl``,
``_merge_degenerate_combat_events_impl``, and ``reconcile_unanchored_events._absorb``.
All three shared a hand-written eight-tuple while metadata declared ten FKs to
``events.id``, and the two omissions failed in OPPOSITE directions —
``game_moments`` (``ON DELETE CASCADE``) was silently destroyed on every merge,
``ranking_judgments`` (no ``ON DELETE`` action) failed the parent DELETE outright.
"""

import inspect
import re

import pytest

from app.utils.event_child_repoint import (
    EVENT_SCOPED_UNIQUE_KEYS,
    event_fk_tables,
    repoint_event_children,
)
from app.utils.event_fk_inventory import derive_event_child_tables


class _Result:
    def __init__(self, rowcount=0, rows=()):
        self.rowcount = rowcount
        self._rows = list(rows)

    def all(self):
        return self._rows


class _RecordingSession:
    """Records every statement, and answers a fixed rowcount to each."""

    def __init__(self, rowcount=1):
        self.statements: list[tuple[str, dict]] = []
        self._rowcount = rowcount

    async def execute(self, stmt, params=None):
        self.statements.append((str(stmt), params or {}))
        return _Result(self._rowcount)

    def sql(self) -> str:
        return "\n".join(s for s, _ in self.statements)


class TestTheListIsDerivedAndComplete:
    # There is deliberately NO `assert set(event_fk_tables()) == set(
    # derive_event_child_tables())` here. It reads like the whole of R4 in one line and
    # is a tautology — `event_fk_tables` returns `derive_event_child_tables()`, so the
    # assertion holds even if both are empty or both are wrong. The contract that
    # matters is that the rail ISSUES A STATEMENT for every derived table, which is
    # `test_every_derived_table_is_actually_issued_a_statement` below, against the SQL
    # the rail really emits. A pinned explicit ten follows, so a metadata-wide breakage
    # cannot pass by making every side equally empty.

    def test_the_derived_set_is_the_expected_twelve(self):
        """Named explicitly so a metadata-wide breakage cannot make the equality above
        pass by making BOTH sides wrong (e.g. an import failure yielding two empties).

        WAS TEN until 2026-08-26 (#2213, queue 413). `event_provider_anchors` has
        existed in Postgres since the 2026-08-24 `anchors_and_captures` migration and
        was invisible to this derivation until it gained an ORM model. It needs no
        entry in `EVENT_SCOPED_UNIQUE_KEYS`: its unique key is
        `(source, source_id, id_kind)` and does NOT include `event_id`, so two rows
        being merged cannot hold the same anchor key — the index already made that
        impossible — and a plain repoint cannot collide. That was checked rather than
        assumed, because it is the exact property the other two entries exist for.

        WAS ELEVEN until 2026-09-05 (#2927, container graph Phase 1).
        `event_participants` is the opposite case to the anchor above and is why
        that paragraph checks rather than assumes: its unique key IS event-scoped
        — `uq_event_participant_slot (event_id, side, position)` — so two rows for
        one game both hold a `(home, 0)` and a plain repoint WOULD collide. It
        therefore takes an entry in `EVENT_SCOPED_UNIQUE_KEYS` and the pre-dedupe
        path. The sync test below is what caught it, before the merge rail could
        start raising IntegrityError on the first merged event with participants.
        """
        assert set(event_fk_tables()) == {
            "espn_snapshots",
            "event_participants",
            "event_provider_anchors",
            "futures_markets",
            "game_moments",
            "line_movement_analyses",
            "odds_aggregated",
            "odds_snapshots",
            "ranking_judgments",
            "score_snapshots",
            "scoring_plays",
            "win_prob_snapshots",
        }

    def test_the_two_that_were_missing_are_repointed(self):
        """Named individually. They failed in opposite directions, and a set equality
        would still pass if a future edit dropped one and added another."""
        tables = event_fk_tables()
        # was ON DELETE CASCADE — silently destroyed, unnamed in any response
        assert "game_moments" in tables
        # was NO ACTION — made the parent DELETE fail with an FK violation
        assert "ranking_judgments" in tables

    def test_it_is_a_function_not_a_module_constant(self):
        """A constant evaluated at import time is still a snapshot of ``Base.metadata``,
        taken before every model module is necessarily registered — which is the same
        way the hand-written tuple was short. Callability is the guarantee."""
        assert callable(event_fk_tables)
        assert callable(derive_event_child_tables)

    def test_the_retired_hand_list_is_really_gone(self):
        """Not merely unused — ABSENT. A leftover ``_EVENT_FK_TABLES`` is a loaded gun:
        it still reads like the answer to "which tables does a merge touch"."""
        import app.tasks.sports as sports

        assert not hasattr(sports, "_EVENT_FK_TABLES")


class TestNoCallSiteKeepsItsOwnList:
    """The original defect had TWO copies: a module tuple and an inline literal in
    ``_merge_duplicate_events_impl``. Deriving one and leaving the other would have
    fixed nothing at the site that actually ran most often."""

    @pytest.mark.parametrize(
        "func_path",
        [
            "app.tasks.sports._merge_duplicate_events_impl",
            "app.tasks.sports._merge_degenerate_combat_events_impl",
            "app.tasks.reconcile_unanchored_events._absorb",
        ],
    )
    def test_the_rail_calls_the_shared_repoint(self, func_path):
        module_name, _, attr = func_path.rpartition(".")
        module = __import__(module_name, fromlist=[attr])
        source = inspect.getsource(getattr(module, attr))
        assert "repoint_event_children" in source, (
            f"{func_path} does not go through the shared derived repoint"
        )

    @pytest.mark.parametrize(
        "func_path",
        [
            "app.tasks.sports._merge_duplicate_events_impl",
            "app.tasks.sports._merge_degenerate_combat_events_impl",
            "app.tasks.reconcile_unanchored_events._absorb",
        ],
    )
    def test_no_rail_builds_its_own_repoint_sql(self, func_path):
        """An ``UPDATE <table> SET event_id`` written at a call site is a hand-list
        wearing a different hat — it names its tables in the f-string's loop."""
        module_name, _, attr = func_path.rpartition(".")
        module = __import__(module_name, fromlist=[attr])
        source = inspect.getsource(getattr(module, attr))
        # Comments legitimately quote the old statement while explaining the fix;
        # strip them before looking for live SQL.
        code = "\n".join(
            line for line in source.splitlines() if not line.lstrip().startswith("#")
        )
        assert not re.search(r"UPDATE\s*\{?\w*\}?\s*SET event_id", code), (
            f"{func_path} still composes its own event_id repoint statement"
        )


class TestEventScopedUniqueConstraintsArePreDeduped:
    """A repoint into an occupied UNIQUE key raises ``IntegrityError``, and the merge
    rail's entire population is pairs describing the SAME game — which is exactly when
    both sides hold a child under the same key. Two of the ten children are affected.
    """

    def test_the_declared_collision_keys_match_the_schema(self):
        """Derived in BOTH directions. A new event-scoped UNIQUE constraint must turn
        this red rather than turning merges into IntegrityErrors in production."""
        from app.models.models import Base

        actual: dict[str, tuple[str, ...]] = {}
        for table in Base.metadata.tables.values():
            if table.name not in set(derive_event_child_tables()):
                continue
            uniques = [
                tuple(c.name for c in con.columns)
                for con in table.constraints
                if con.__class__.__name__ == "UniqueConstraint"
            ] + [
                tuple(c.name for c in ix.columns)
                for ix in table.indexes
                if ix.unique
            ]
            for cols in uniques:
                if "event_id" in cols:
                    actual[table.name] = tuple(
                        c for c in cols if c != "event_id"
                    )

        assert actual == EVENT_SCOPED_UNIQUE_KEYS, (
            "the set of event-scoped UNIQUE constraints on event children changed. "
            "Each one needs a pre-dedupe in repoint_event_children or a merge will "
            f"raise IntegrityError. schema={actual} declared={EVENT_SCOPED_UNIQUE_KEYS}"
        )

    def test_game_moments_is_one_of_them(self):
        """The newly-repointed table is ALSO the colliding one — adding it to the list
        without the pre-dedupe would have traded silent data loss for a hard failure.
        ``canonical_dedupe_key`` is the source play's identity and carries no event id,
        so two duplicates of one game over one provider feed produce identical keys."""
        assert EVENT_SCOPED_UNIQUE_KEYS["game_moments"] == ("dedupe_key",)

    def test_odds_aggregated_was_already_exposed(self):
        """It was in the shipped eight, so this rail could already raise on it before
        game_moments was ever added. Pinned so the fix is not read as new-code-only."""
        assert EVENT_SCOPED_UNIQUE_KEYS["odds_aggregated"] == ("period_start",)

    @pytest.mark.asyncio
    async def test_colliding_tables_get_a_guarded_update_and_an_explicit_delete(self):
        session = _RecordingSession()
        await repoint_event_children(session, keep_id=1, orphan_id=2)
        sql = session.sql()

        for table, cols in EVENT_SCOPED_UNIQUE_KEYS.items():
            update = next(
                s for s, _ in session.statements
                if s.startswith(f"UPDATE {table} ")
            )
            assert "NOT EXISTS" in update, (
                f"{table} carries an event-scoped UNIQUE key but is repointed with a "
                "bare UPDATE — this raises IntegrityError on a real merge"
            )
            for col in cols:
                assert col in update, f"{table}'s pre-dedupe ignores {col}"
            # The remainder must be removed by a statement that NAMES the table:
            # CASCADE would take game_moments unmentioned, and NO ACTION would make
            # odds_aggregated fail the parent DELETE.
            assert f"DELETE FROM {table} WHERE event_id = :orphan" in sql, (
                f"{table}'s colliding remainder is left to the FK to resolve"
            )

    @pytest.mark.asyncio
    async def test_non_colliding_tables_get_a_plain_update(self):
        """The guarded form is not applied where it is not needed — an unnecessary
        NOT EXISTS over odds_snapshots would be a per-row subquery on a huge table."""
        session = _RecordingSession()
        await repoint_event_children(session, keep_id=1, orphan_id=2)

        for table in event_fk_tables():
            if table in EVENT_SCOPED_UNIQUE_KEYS:
                continue
            update = next(
                s for s, _ in session.statements
                if s.startswith(f"UPDATE {table} ")
            )
            assert "NOT EXISTS" not in update
            assert f"DELETE FROM {table}" not in session.sql()

    @pytest.mark.asyncio
    async def test_every_derived_table_is_actually_issued_a_statement(self):
        """The list being right is worthless if the loop skips a member."""
        session = _RecordingSession()
        await repoint_event_children(session, keep_id=1, orphan_id=2)
        sql = session.sql()
        for table in derive_event_child_tables():
            assert f"UPDATE {table} " in sql, f"{table} was derived but never repointed"


class TestTheMovesAreReported:
    """R4's other half: an effect nothing in the output mentions is an effect nobody
    reviews. ``game_moments`` disappearing was invisible precisely because no response
    named it."""

    @pytest.mark.asyncio
    async def test_repoint_returns_per_table_counts(self):
        session = _RecordingSession(rowcount=3)
        out = await repoint_event_children(session, keep_id=1, orphan_id=2)

        assert set(out) == {"repointed", "dropped_as_duplicate", "markets"}
        assert out["repointed"]["game_moments"] == 3
        assert out["repointed"]["ranking_judgments"] == 3
        assert out["dropped_as_duplicate"]["game_moments"] == 3
        # only the colliding tables can drop rows
        assert set(out["dropped_as_duplicate"]) == set(EVENT_SCOPED_UNIQUE_KEYS)

    @pytest.mark.asyncio
    async def test_zero_counts_are_omitted_not_reported_as_zero(self):
        """A response full of zeroes is a response nobody reads."""
        session = _RecordingSession(rowcount=0)
        out = await repoint_event_children(session, keep_id=1, orphan_id=2)
        assert out == {
            "repointed": {}, "dropped_as_duplicate": {}, "markets": [],
        }

    @pytest.mark.asyncio
    async def test_a_missing_rowcount_does_not_break_the_merge(self):
        """Bookkeeping must never be the thing that fails a merge. Nothing in the
        repoint branches on these counts, so a driver without rowcount reports zero."""

        class _NoRowcountSession(_RecordingSession):
            async def execute(self, stmt, params=None):
                self.statements.append((str(stmt), params or {}))
                return object()

        session = _NoRowcountSession()
        out = await repoint_event_children(session, keep_id=1, orphan_id=2)
        assert out == {
            "repointed": {}, "dropped_as_duplicate": {}, "markets": [],
        }
        # +1 for the futures_markets pre-read (LINKLOSS-02): the markets whose
        # link this merge is about to move, read before the UPDATE erases where
        # they came from.
        assert len(session.statements) == 1 + len(event_fk_tables()) + len(
            EVENT_SCOPED_UNIQUE_KEYS
        )

    @pytest.mark.parametrize(
        "func_path",
        [
            "app.tasks.sports._merge_duplicate_events_impl",
            "app.tasks.sports._merge_degenerate_combat_events_impl",
        ],
    )
    def test_the_merge_rails_surface_the_counts(self, func_path):
        module_name, _, attr = func_path.rpartition(".")
        module = __import__(module_name, fromlist=[attr])
        source = inspect.getsource(getattr(module, attr))
        assert "child_rows_repointed" in source
        assert "child_rows_dropped_as_duplicate" in source


class TestThePruneRailStillCannotRepoint:
    """The merge rail's repoint lives in its own module for a reason. Ruling 048's harm
    IS a repoint, so the PRUNE rail's vocabulary deliberately cannot spell one, and this
    change must not have leaked the verb across that line."""

    def test_disposition_still_has_no_transfer(self):
        from app.utils.event_fk_inventory import Disposition

        args = getattr(Disposition, "__args__", ())
        assert set(args) == {"SUBSTANCE", "POINTER"}
        assert "TRANSFER" not in args

    def test_the_inventory_module_defines_no_repoint(self):
        """Comments and docstrings are stripped first, deliberately: that module's
        prose QUOTES ``SET event_id = :keep`` in order to explain why it refuses to
        implement it, and a naive substring search would read the explanation as the
        offence. What must be absent is executable SQL."""
        import ast

        import app.utils.event_fk_inventory as inventory

        source = inspect.getsource(inventory)
        tree = ast.parse(source)
        strings = [
            node.value
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
        ]
        docstrings = {
            ast.get_docstring(n)
            for n in ast.walk(tree)
            if isinstance(n, (ast.Module, ast.FunctionDef, ast.ClassDef))
        }
        live = [s for s in strings if s not in docstrings]

        offenders = [s for s in live if "SET event_id" in s]
        assert not offenders, (
            "the prune rail's inventory now contains a repoint statement — that is the "
            f"operation ruling 048 exists to prevent this rail from learning: {offenders}"
        )
