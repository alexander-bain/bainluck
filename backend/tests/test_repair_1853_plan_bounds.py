"""#1853 — the archive-grade plan read is bounded and READ ONLY.

PILLAR: TRUTH. SHIP: decided Europa Conference League score questions receive
venue-backed results through a plan check that refuses excessive waits.

Root's finding (2026-10-20, source at 188d2d2717): the plan session called
``get_task_session()`` with no budgets, so it rested at the helper's thirty-minute
statement bound and no lock bound, and its read-only behaviour had no
transaction-level ``READ ONLY`` declaration. These arms pin the correction:

1. **Budgets propagate**: the plan engine is built with 2000 ms / 500 ms and those
   reach the connection's startup ``server_settings``; the write session's engine
   is unchanged (its resting bound, no lock bound) — paired in one run.
2. **READ ONLY comes first**: the declaration is the plan transaction's first
   statement, before either data read, and the write session never makes it.
3. **A healthy complete plan** on the real 2026-10-15 stored read and retained
   archive bytes still plans the 22 under the same digest, with no write session.
4. **A slow, lock-refused or cancelled plan stops**: no digest printed, no write
   session, no COMMIT, at either read and in plan or ``--apply`` mode — each paired
   with the identical healthy run.

Every arm drives the PRODUCTION ``get_task_session`` and ``_get_task_engine`` (so
the real ``build_connect_args``); only ``create_async_engine`` and the session
factory are inert. The plan's SQL runs against a fake that models Postgres's
"read-write mode must be set before any query" rule. The write-path commit-ack
controls stay in ``tests/test_repair_1853_commit_ack.py``.
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "repair_1853_archive_grades.py"
STORED = json.loads((ROOT / "tests" / "fixtures" / "kalshi_archive_1853_stored.json").read_text())
UNGRADED = sorted(r["outcome_id"] for r in STORED["stored"] if r["resolution_source"] is None)
READ_ONLY = "SET TRANSACTION READ ONLY"
ASYNCPG_URL = "postgresql+asyncpg://plan@localhost/bainluck_test"


@pytest.fixture
def repair():
    spec = importlib.util.spec_from_file_location("repair_1853_plan_bounds_under_test", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _PgError(Exception):
    def __init__(self, sqlstate, message):
        super().__init__(message)
        self.sqlstate = sqlstate


def _timeout():
    from sqlalchemy.exc import OperationalError

    return OperationalError("SELECT", {}, _PgError(
        "57014", "canceling statement due to statement timeout"))


def _lock_timeout():
    from sqlalchemy.exc import OperationalError

    return OperationalError("SELECT", {}, _PgError(
        "55P03", "canceling statement due to lock timeout"))


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return list(self._rows)


def _kind(sql: str) -> str:
    if sql.strip() == READ_ONLY:
        return "read_only"
    if "JOIN futures_markets" in sql:
        return "stored_legs"
    if "to_jsonb(fo)::text" in sql:
        return "approved"
    return sql.strip().split()[0].lower()


class PlanSession:
    """The plan's reads against the real 2026-10-15 stored legs.

    Models Postgres: ``SET TRANSACTION READ ONLY`` after a query in the same
    transaction is an error, and a rollback starts a new transaction. ``fault``
    is raised by the read named ``fault_at``.
    """

    def __init__(self, calls, fault=None, fault_at=None):
        self.calls = calls
        self.info: dict = {}
        self.statements: list[tuple[str, bool]] = []  # (kind, read_only at the time)
        self.commits = 0
        self._fault, self._fault_at = fault, fault_at
        self._read_only = False
        self._queried = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def execute(self, statement, params=None):
        kind = _kind(str(statement))
        self.calls.append(kind)
        if kind == "read_only":
            if self._queried:
                raise RuntimeError("transaction read-write mode must be set before any query")
            self._read_only = True
            return _Result([])
        self._queried = True
        self.statements.append((kind, self._read_only))
        if kind == self._fault_at:
            raise self._fault
        if kind == "stored_legs":
            assert params == {"event_ticker": STORED["event_ticker"]}
            return _Result([
                (r["outcome_id"], r["external_id"], r["resolution_source"], r["is_winner"])
                for r in STORED["stored"]
            ])
        if kind == "approved":
            return _Result([
                (i, json.dumps({"id": i, "resolution_source": None, "is_winner": None}))
                for i in params["ids"] if i in UNGRADED
            ])
        raise AssertionError(f"the plan session ran an unexpected statement: {kind}")

    def _end(self):
        self._read_only = False
        self._queried = False

    async def commit(self):
        self.calls.append("commit")
        self.commits += 1
        self._end()

    async def rollback(self):
        self.calls.append("rollback")
        self._end()

    async def close(self):
        self.calls.append("close")


class WriteSession(PlanSession):
    """The write session: its SQL bodies are recorders (stubbed below)."""


class _InertEngine:
    def __init__(self, calls):
        self._calls = calls

    async def dispose(self):
        self._calls.append("dispose")


def _wire(repair, monkeypatch, sessions):
    """Production wrapper and engine builder; inert engine and session factory.

    Returns the per-engine records: what ``_get_task_engine`` was asked for and the
    ``connect_args`` the real ``build_connect_args`` produced from it.
    """
    import app.tasks.base as base

    assert base.get_task_session.__wrapped__.__qualname__ == "get_task_session"
    engines: list[dict] = []
    queue = list(sessions)
    calls = sessions[0].calls
    real_engine = base._get_task_engine

    def get_task_engine(**kwargs):
        engines.append({"asked": dict(kwargs)})
        return real_engine(**kwargs)

    def create_async_engine(url, **kwargs):
        engines[-1]["connect_args"] = kwargs["connect_args"]
        return _InertEngine(calls)

    def session_maker(bound, **kwargs):
        if not queue:
            raise AssertionError("a session opened that this run never provided")
        s = queue.pop(0)
        return lambda: s

    monkeypatch.setattr(base, "DATABASE_URL", ASYNCPG_URL)
    monkeypatch.setattr(base, "_get_task_engine", get_task_engine)
    monkeypatch.setattr(base, "create_async_engine", create_async_engine)
    monkeypatch.setattr(base, "async_sessionmaker", session_maker)

    async def backup(session, grades, digest):
        calls.append("backup")
        return 0

    async def apply(session, legs, digest):
        calls.append("apply")
        return {"written_ids": [g.outcome_id for g in grades_seen], "skipped_changed_since_backup": []}

    grades_seen: list = []
    real_build_plan = repair.build_plan

    async def build_plan(session, legs):
        grades, refused = await real_build_plan(session, legs)
        grades_seen[:] = grades
        return grades, refused

    monkeypatch.setattr(repair, "build_plan", build_plan)
    monkeypatch.setattr(repair, "backup", backup)
    monkeypatch.setattr(repair, "apply", apply)
    monkeypatch.setenv("HEROKU_APP_NAME", "bainluck-heavy")
    return engines


def _healthy_digest(repair, monkeypatch, capsys) -> str:
    calls: list[str] = []
    _wire(repair, monkeypatch, [PlanSession(calls)])
    assert repair.main([]) == 0
    return json.loads(capsys.readouterr().out)["plan_digest"]


# ── 1. budgets propagate, and only to the plan ───────────────────────────────


def test_the_plan_constants_are_the_proposed_bounds(repair):
    assert repair.PLAN_STATEMENT_TIMEOUT_MS == 2_000
    assert repair.PLAN_LOCK_TIMEOUT_MS == 500


def test_the_plan_budgets_reach_the_connection_and_the_write_session_keeps_its_own(
    repair, monkeypatch, capsys
):
    from app.services.database import DB_STATEMENT_TIMEOUT_MS

    digest = _healthy_digest(repair, monkeypatch, capsys)
    calls: list[str] = []
    plan, write = PlanSession(calls), WriteSession(calls)
    engines = _wire(repair, monkeypatch, [plan, write])
    assert repair.main(["--backup", "--apply", "--digest", digest]) == 0
    assert len(engines) == 2
    plan_engine, write_engine = engines
    assert plan_engine["asked"] == {"statement_timeout_ms": 2_000, "lock_timeout_ms": 500}
    assert plan_engine["connect_args"]["server_settings"] == {
        "statement_timeout": "2000", "lock_timeout": "500",
    }
    # The paired control: the write session is outside this delta, unchanged.
    assert write_engine["asked"] == {"statement_timeout_ms": None, "lock_timeout_ms": None}
    assert write_engine["connect_args"]["server_settings"] == {
        "statement_timeout": str(DB_STATEMENT_TIMEOUT_MS),
    }
    assert DB_STATEMENT_TIMEOUT_MS > repair.PLAN_STATEMENT_TIMEOUT_MS
    out = json.loads(capsys.readouterr().out)
    assert out["plan_digest"] == digest and out["applied"]["written_ids"] == UNGRADED


# ── 2. READ ONLY comes first, and only on the plan ───────────────────────────


def test_read_only_is_declared_before_either_plan_read(repair, monkeypatch, capsys):
    calls: list[str] = []
    plan = PlanSession(calls)
    _wire(repair, monkeypatch, [plan])
    assert repair.main([]) == 0
    assert calls[:3] == ["read_only", "stored_legs", "approved"]
    assert plan.statements == [("stored_legs", True), ("approved", True)]


def test_the_write_session_never_declares_read_only(repair, monkeypatch, capsys):
    digest = _healthy_digest(repair, monkeypatch, capsys)
    calls: list[str] = []
    plan, write = PlanSession(calls), WriteSession(calls)
    _wire(repair, monkeypatch, [plan, write])
    assert repair.main(["--backup", "--apply", "--digest", digest]) == 0
    write_calls = calls[calls.index("dispose") + 1:]
    assert write_calls == ["backup", "commit", "apply", "commit", "commit", "close", "dispose"]
    assert calls.count("read_only") == 1


# ── 3. a healthy complete plan is unchanged ──────────────────────────────────


def test_a_healthy_plan_on_the_specimen_plans_the_22_and_opens_no_write_session(
    repair, monkeypatch, capsys
):
    calls: list[str] = []
    plan = PlanSession(calls)
    engines = _wire(repair, monkeypatch, [plan])
    assert repair.main([]) == 0
    out = json.loads(capsys.readouterr().out)
    assert [p["outcome_id"] for p in out["planned"]] == UNGRADED and len(UNGRADED) == 22
    assert all(p["is_winner"] is False for p in out["planned"])
    assert len(out["refused"]["already_graded"]) == 8
    assert "stop" not in out and "applied" not in out and "undo" not in out
    assert len(engines) == 1
    # Read-only declaration and two SELECTs; the rollback ends the transaction
    # before the wrapper's normal exit, so its COMMIT carries nothing.
    assert calls == ["read_only", "stored_legs", "approved",
                     "rollback", "commit", "close", "dispose"]
    assert "backup" not in calls and "apply" not in calls


# ── 4. a slow, lock-refused or cancelled plan stops ──────────────────────────


_FAULTS = {
    "statement-timeout": _timeout,
    "lock-timeout": _lock_timeout,
}


@pytest.mark.parametrize("mode", ["plan", "apply"])
@pytest.mark.parametrize("fault_at", ["stored_legs", "approved"])
@pytest.mark.parametrize("fault", list(_FAULTS))
def test_a_plan_read_past_its_budget_prints_no_digest_and_writes_nothing(
    repair, monkeypatch, capsys, mode, fault_at, fault
):
    digest = _healthy_digest(repair, monkeypatch, capsys)
    argv = [] if mode == "plan" else ["--backup", "--apply", "--digest", digest]
    calls: list[str] = []
    boom = _FAULTS[fault]()
    plan = PlanSession(calls, fault=boom, fault_at=fault_at)
    # A second session is offered so that opening one is observable, not a crash.
    write = WriteSession(calls)
    engines = _wire(repair, monkeypatch, [plan, write])
    with pytest.raises(type(boom)) as caught:
        repair.main(argv)
    assert caught.value is boom  # the plan's own failure, not a wrapper or a refusal
    captured = capsys.readouterr()
    assert "plan_digest" not in captured.out and digest not in captured.out
    assert captured.out == ""
    assert len(engines) == 1  # no write session
    assert plan.commits == 0  # the wrapper left by its exception path
    assert calls[-3:] == ["rollback", "close", "dispose"]
    assert "backup" not in calls and "apply" not in calls and write.commits == 0


@pytest.mark.parametrize("mode", ["plan", "apply"])
def test_the_paired_healthy_run_prints_the_digest_the_faulted_one_withheld(
    repair, monkeypatch, capsys, mode
):
    # The control for every arm above: the identical rig with no fault.
    digest = _healthy_digest(repair, monkeypatch, capsys)
    argv = [] if mode == "plan" else ["--backup", "--apply", "--digest", digest]
    calls: list[str] = []
    engines = _wire(repair, monkeypatch, [PlanSession(calls), WriteSession(calls)])
    assert repair.main(argv) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["plan_digest"] == digest
    assert len(engines) == (1 if mode == "plan" else 2)


@pytest.mark.parametrize("mode", ["plan", "apply"])
def test_a_cancelled_plan_propagates_as_a_cancel_and_writes_nothing(
    repair, monkeypatch, capsys, mode
):
    digest = _healthy_digest(repair, monkeypatch, capsys)
    argv = [] if mode == "plan" else ["--backup", "--apply", "--digest", digest]
    calls: list[str] = []
    plan = PlanSession(calls, fault=asyncio.CancelledError(), fault_at="stored_legs")
    engines = _wire(repair, monkeypatch, [plan, WriteSession(calls)])
    with pytest.raises(asyncio.CancelledError):
        repair.main(argv)
    assert capsys.readouterr().out == ""
    assert len(engines) == 1 and plan.commits == 0
    assert "backup" not in calls and "apply" not in calls
