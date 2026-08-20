"""#2048 — the drain throws on 100% of what it identifies as drainable.

Ruling 048 accepts duplicates as a **bounded** cost, and names the bound:

    *"id-keyed reconciliation drains the duplicate when an id arrives."*

Queue 382 measured that reconciliation against production at two window sizes and
found the same number twice:

    | scanned | DRAINABLE | errors | reconciled |
    |------:|---:|---:|---:|
    |   200 |  2 |  2 |  0 |
    |  2000 |  2 |  2 |  0 |

``DRAINABLE == len(errors)`` at every scan size. The twin lookup runs *only* for
drainable rows, so ``reconciled: 0`` was never "there was nothing to drain" — it was
the drain failing on everything it found. Ruling 048's cost bound has therefore never
been measured, not once, since the ruling landed.

TWO DEFECTS, AND THE SECOND IS WHY THE FIRST LOOKED SMALLER THAN IT IS
----------------------------------------------------------------------

**1. The bind is untypeable.** ``_TWIN_SQL`` writes ``:external_id IS NOT NULL``. A
parameter inside a ``NullTest`` gets no type context, so PostgreSQL mints the ``Param``
node as ``UNKNOWNOID``; the later ``o.external_id = :external_id`` resolves the *slot*
but not the node already built, and parse analysis ends with
``could not determine data type of parameter $N``. The equality does not rescue the
null test, because the null test came first.

**2. One failure poisons the rest of the pass.** The per-row ``except`` appends to
``errors`` and ``continue``s — but a failed statement aborts the whole PostgreSQL
transaction, so every row after the first fails too, on a *different* error. That is
why production reported ``ProgrammingError`` for one row and ``DBAPIError`` for the
next: only the first error is real, the second is the corpse of the transaction. The
per-item try/except reads like gotcha #42's isolation and provides none of it.

Both are asserted here. The first is asserted against the **compiled** SQL rather than
a live database, because the defect is in what PostgreSQL is handed — and there is no
local Postgres in this sandbox to hand it to.
"""

import ast
import importlib.util
import inspect
import re

import pytest
from sqlalchemy.dialects import postgresql

from app.tasks import reconcile_unanchored_events as mod
from app.tasks.reconcile_unanchored_events import (
    UNANCHORED_TAG,
    _TWIN_SQL,
    reconcile,
    run_reconcile_unanchored,
)


def _compiled_twin_sql() -> str:
    """``_TWIN_SQL`` exactly as asyncpg will hand it to PostgreSQL."""
    return str(_TWIN_SQL.compile(dialect=postgresql.asyncpg.dialect()))


# ── defect 1: the untypeable bind ──────────────────────────────────────────


class TestTheBindIsTypeable:
    def test_no_parameter_is_null_tested_without_a_type(self):
        """The defect, stated as the thing PostgreSQL objects to.

        ``$2 IS NOT NULL`` gives parse analysis nothing to infer from. Every
        provider-id bind in this query is null-tested, so before the fix this
        finds three of them and the drain cannot run at all.
        """
        sql = _compiled_twin_sql()
        bare = re.findall(r"\$\d+\s+IS\s+(?:NOT\s+)?NULL", sql, flags=re.IGNORECASE)

        assert bare == [], (
            "a bind parameter is null-tested with no type context — PostgreSQL will "
            f"raise 'could not determine data type of parameter': {bare}"
        )

    def test_every_provider_id_bind_is_cast(self):
        """The fix, stated positively, so a future edit cannot silently undo it.

        ``_CENSUS_SQL`` in the same module already casts its one bind
        (``CAST(:tag AS jsonb)``). This asserts the twin lookup does the same for
        all three of its provider-id binds rather than relying on the equality
        that demonstrably does not rescue them.
        """
        sql = _compiled_twin_sql().upper()

        assert sql.count("CAST(") >= 3, (
            "expected one CAST per provider-id bind (external_id, espn_id, "
            f"statpal_fixture_id); found {sql.count('CAST(')}"
        )

    def test_the_casts_name_the_column_type(self):
        """VARCHAR, because all three columns are ``String`` on ``Event``.

        Casting to the wrong type would compare a varchar column against a
        coerced value and could quietly match nothing — a drain that runs and
        finds no twins is the exact failure this issue is about, one layer down.
        """
        sql = _compiled_twin_sql().upper()
        assert sql.count("AS VARCHAR)") >= 3, sql


# ── defect 2: one bad row must not wipe the pass ───────────────────────────


class _Savepoint:
    def __init__(self, session):
        self._session = session

    async def __aenter__(self):
        self._session.savepoints_opened += 1
        return self

    async def __aexit__(self, exc_type, exc, tb):
        if exc_type is not None:
            self._session.savepoints_rolled_back += 1
        return False


class _Row:
    def __init__(self, **kw):
        defaults = {
            "id": 1, "sport_id": 53232, "commence_time": None, "status": "closed",
            "home_team_name": "Home FC", "away_team_name": "Away FC",
            "event_tags": [UNANCHORED_TAG], "external_id": None, "espn_id": None,
            "statpal_fixture_id": None, "twin_count": 0,
        }
        defaults.update(kw)
        for k, v in defaults.items():
            setattr(self, k, v)

    def get(self, key):
        return getattr(self, key, None)


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def mappings(self):
        return self

    def all(self):
        return self._rows


class _PoisonableSession:
    """A session that behaves like PostgreSQL: a failed statement aborts the tx.

    Once a statement raises, every later statement raises too — with a *different*
    exception — until the savepoint that contained the failure is rolled back. That
    is the production signature (``ProgrammingError`` then ``DBAPIError``) and it is
    the thing the per-row ``except`` does nothing about today.
    """

    def __init__(self, census_rows, twin_rows, fail_on_event_ids):
        self._census = census_rows
        self._twins = twin_rows
        self._fail_on = set(fail_on_event_ids)
        self.calls = 0
        self.aborted = False
        self.savepoints_opened = 0
        self.savepoints_rolled_back = 0
        self.twin_lookups = []
        self.writes: list = []

    def begin_nested(self):
        self.aborted = False  # a savepoint is the repair boundary
        return _Savepoint(self)

    async def execute(self, stmt, params=None):
        self.calls += 1
        if self.calls == 1:
            return _Result(self._census)

        if self.aborted:
            raise RuntimeError(
                "current transaction is aborted, commands ignored until "
                "end of transaction block"
            )

        sql = str(stmt)
        if "DELETE FROM events" in sql or sql.strip().startswith("UPDATE "):
            self.writes.append((sql.strip().split("\n")[0], params))
            return _Result([])

        eid = (params or {}).get("eid")
        self.twin_lookups.append(eid)
        if eid in self._fail_on:
            self.aborted = True
            raise RuntimeError('could not determine data type of parameter $2')
        return _Result([t for t in self._twins if t["_for"] == eid])

    async def commit(self):
        pass


class TestTheTaskCanActuallyStart:
    """#2051 — filed separately, fixed here, because #2048 is unmeasurable without it.

    The scheduled entry point imported ``app.database``, which has never existed in
    this repo. Deferred imports are invisible until the beat fires, and then they fire
    every time: 48 crashes a day, ``consecutive_failures: 97``, zero successes ever.
    Fixing the twin lookup without fixing this would produce a green PR and an
    unchanged production number.
    """

    def test_every_deferred_app_import_in_this_module_resolves(self):
        """The class of defect, not just the instance.

        Every ``from app.… import`` inside a function body in this module is checked
        for importability. A module-level import would have been caught by
        ``test_startup.py`` on the first CI run; these were not, which is exactly why
        they need their own assertion.
        """
        tree = ast.parse(inspect.getsource(mod))
        unresolved = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("app."):
                if importlib.util.find_spec(node.module) is None:
                    unresolved.append(f"{node.module} (line {node.lineno})")

        assert unresolved == [], (
            "deferred import(s) name a module that does not exist — the task will "
            f"raise ModuleNotFoundError every time the beat fires: {unresolved}"
        )

    @pytest.mark.asyncio
    async def test_the_entry_point_runs_instead_of_raising_modulenotfound(self, monkeypatch):
        """End to end through the real entry point, with only the session faked."""
        from contextlib import asynccontextmanager

        session = _PoisonableSession([], [], fail_on_event_ids=set())

        @asynccontextmanager
        async def _fake_session():
            yield session

        monkeypatch.setattr("app.tasks.base.get_task_session", _fake_session)

        out = await run_reconcile_unanchored(apply=False, limit=10)

        assert out["measured"] is True
        assert out["task"] == "reconcile_unanchored_events"


class TestOneBadRowDoesNotWipeThePass:
    @pytest.mark.asyncio
    async def test_a_second_drainable_row_still_reconciles_after_the_first_throws(self):
        """gotcha #42, on the rail that grades ruling 048.

        Row 11's twin lookup fails. Row 12's must still run AND succeed. Without a
        savepoint the aborted transaction takes row 12 down with it, and the census
        reports two errors where there is one defect — which is exactly how a
        one-row bug was reported as 'two deterministically-throwing rows'.
        """
        rows = [
            _Row(id=11, espn_id="401816407", twin_count=1),
            _Row(id=12, espn_id="401816408", twin_count=1),
        ]
        twins = [{
            "_for": 12, "id": 22, "espn_id": "401816408", "external_id": None,
            "statpal_fixture_id": None, "home_team_name": "Home FC",
            "away_team_name": "Away FC", "commence_time": None,
        }]
        session = _PoisonableSession(rows, twins, fail_on_event_ids={11})

        out = await reconcile(session, apply=False)

        assert session.twin_lookups == [11, 12], (
            "row 12's twin lookup must be attempted after row 11 failed"
        )
        assert out["errors"] == ["twin lookup for 11: RuntimeError"], out["errors"]
        assert out["reconciled"] == 1, (
            "the healthy sibling must survive the poisoned one — got "
            f"{out['reconciled']} with errors {out['errors']}"
        )
        assert out["drained"][0]["unanchored_event_id"] == 12

    @pytest.mark.asyncio
    async def test_the_failure_is_contained_by_a_savepoint(self):
        """Named explicitly, because ``rollback()`` would be the wrong repair.

        A bare ``session.rollback()`` in an ``apply=True`` pass discards every merge
        already applied in this run. The containment must be per-row.
        """
        rows = [_Row(id=11, espn_id="401816407", twin_count=1)]
        session = _PoisonableSession(rows, [], fail_on_event_ids={11})

        await reconcile(session, apply=False)

        assert session.savepoints_opened >= 1
        assert session.savepoints_rolled_back >= 1

    @pytest.mark.asyncio
    async def test_the_terminal_is_partial_not_failed_when_one_row_throws(self):
        """A pass that drained one of two is neither green nor a total loss."""
        rows = [
            _Row(id=11, espn_id="401816407", twin_count=1),
            _Row(id=12, espn_id="401816408", twin_count=1),
        ]
        twins = [{
            "_for": 12, "id": 22, "espn_id": "401816408", "external_id": None,
            "statpal_fixture_id": None, "home_team_name": "Home FC",
            "away_team_name": "Away FC", "commence_time": None,
        }]
        out = await reconcile(
            _PoisonableSession(rows, twins, fail_on_event_ids={11}), apply=False
        )
        assert out["terminal"] == "partial"
        assert out["reason"] == "errors_during_drain"
