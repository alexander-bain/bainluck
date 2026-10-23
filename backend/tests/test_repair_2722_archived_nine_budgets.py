"""#2722 — every session the nine-row repair opens is bounded, and a bound that
fires is a refusal, never a retry or a restore.

PILLAR: TRUTH. SHIP: the nine venue-finalized archived questions show their
settled result instead of remaining Open, with a reversible first historical
repair.

``get_task_session()`` with no arguments rests at a 30-minute statement bound
and NO lock bound (#4482), and a bare ``SET`` on the session is lost at the
first commit or reconnect. So the plan, backup/apply and restore sessions each
pass ``STATEMENT_TIMEOUT_MS`` / ``LOCK_TIMEOUT_MS`` to ``get_task_session``,
which rides the connection's startup packet. The real-Postgres half (the GUCs
on the wire, a held row lock stopping the apply) lives in
``tests/integration/test_kalshi_archived_nine_repair_2722_pg.py``.
"""

from __future__ import annotations

import ast
import contextlib
import importlib.util
import json
import re
from pathlib import Path

import pytest
from sqlalchemy.exc import OperationalError

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "repair_2722_archived_nine.py"


@pytest.fixture
def repair():
    spec = importlib.util.spec_from_file_location("repair_2722_archived_nine", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ── the call sites ────────────────────────────────────────────────────────────


def _session_calls():
    tree = ast.parse(SCRIPT.read_text())
    return [
        n for n in ast.walk(tree)
        if isinstance(n, ast.Call)
        and getattr(n.func, "id", getattr(n.func, "attr", None)) == "get_task_session"
    ]


def test_every_session_site_carries_both_budgets_by_name():
    calls = _session_calls()
    # plan, backup/apply, restore, status — a fifth site must be added here deliberately.
    assert len(calls) == 4
    for call in calls:
        assert call.args == []
        kw = {k.arg: getattr(k.value, "id", None) for k in call.keywords}
        assert kw == {
            "statement_timeout_ms": "STATEMENT_TIMEOUT_MS",
            "lock_timeout_ms": "LOCK_TIMEOUT_MS",
        }, ast.unparse(call)


def test_no_bare_set_of_either_guc():
    src = SCRIPT.read_text()
    assert not re.search(r"\bSET\s+(LOCAL\s+)?(statement_timeout|lock_timeout)\b", src, re.I)


def test_the_budgets_are_ten_seconds_and_half_a_second(repair):
    assert repair.STATEMENT_TIMEOUT_MS == 10_000
    assert repair.LOCK_TIMEOUT_MS == 500


# ── what each mode actually opens ─────────────────────────────────────────────


class FakeSession:
    def __init__(self):
        self.commits = 0
        self.rollbacks = 0

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1


def _fake_task_session(session, seen, *, fail_on_exit=None):
    """get_task_session's contract: commit on a clean exit, roll back and
    re-raise on an exception."""

    @contextlib.asynccontextmanager
    async def fake(**kwargs):
        seen.append(kwargs)
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        if fail_on_exit is not None:
            raise fail_on_exit
        await session.commit()

    return fake


def _db_error(sqlstate):
    class _Orig(Exception):
        pass

    orig = _Orig("canceling statement due to timeout")
    orig.sqlstate = sqlstate
    return OperationalError("UPDATE futures_markets ...", {}, orig)


PLANNED = [{
    "market_id": 109776, "ticker": "KXTXPRIMARY-04R26",
    "resolution_date": "2027-11-03T15:00:00+00:00", "expiration_time": None,
    "venue_settled": True, "approved_before": '{"id": 109776}',
}]


@pytest.fixture
def rig(repair, monkeypatch):
    import app.tasks.base as base

    calls = {"build_plan": 0, "backup": 0, "apply": 0, "restore_report": 0}
    raise_in: dict = {}
    session = FakeSession()
    seen: list[dict] = []

    def stub(name, result):
        async def f(*a, **k):
            calls[name] += 1
            if name in raise_in:
                raise raise_in[name]
            return result
        return f

    monkeypatch.setattr(repair, "load_evidence", lambda: {})
    monkeypatch.setattr(repair, "build_plan", stub("build_plan", {
        "planned": PLANNED, "no_op": [], "stop_not_settled_from_archive": [],
        "voids_reported_not_written": [], "walk_stats": {},
    }))
    monkeypatch.setattr(repair, "backup", stub("backup", []))
    monkeypatch.setattr(repair, "apply", stub("apply", {
        "written_ids": [109776], "skipped_changed_since_backup": []}))
    monkeypatch.setattr(repair, "restore_report", stub("restore_report", {
        "restored": [109776], "preserved_changed_since_apply": []}))
    monkeypatch.setattr(base, "get_task_session", _fake_task_session(session, seen))
    monkeypatch.setenv("HEROKU_APP_NAME", "bainluck-heavy")
    return {"calls": calls, "raise_in": raise_in, "session": session, "seen": seen,
            "digest": repair.plan_digest(PLANNED), "base": base}


def _argv(rig, mode):
    return {
        "plan": [],
        "apply": ["--backup", "--apply", "--digest", rig["digest"]],
        "restore": ["--restore"],
    }[mode]


@pytest.mark.parametrize("mode,opened", [("plan", 1), ("apply", 2), ("restore", 1)])
def test_every_session_each_mode_opens_is_armed(repair, rig, capsys, mode, opened):
    assert repair.main(_argv(rig, mode)) == 0
    bounded = {"statement_timeout_ms": 10_000, "lock_timeout_ms": 500}
    assert rig["seen"] == [bounded] * opened
    out = json.loads(capsys.readouterr().out)
    assert ("undo" in out) == (mode == "apply")


# ── a bound that fires ────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "mode,phase,stub,sqlstate,consequence",
    [
        ("plan", "plan", "build_plan", "57014", "nothing written"),
        ("apply", "backup", "backup", "55P03", "nothing was backed up or written"),
        ("apply", "apply", "apply", "55P03", "nothing to restore"),
        ("restore", "restore", "restore_report", "57014", "no row was restored"),
    ],
)
def test_a_fired_budget_refuses_naming_phase_and_never_retries_or_restores(
    repair, rig, capsys, mode, phase, stub, sqlstate, consequence
):
    rig["raise_in"][stub] = _db_error(sqlstate)
    assert repair.main(_argv(rig, mode)) == 2
    out = json.loads(capsys.readouterr().out)
    assert set(out) == {"refused"}
    msg = out["refused"]
    assert f"stopped the {phase}" in msg and f"sqlstate {sqlstate}" in msg
    assert "rolled back" in msg and consequence in msg and "Not retried" in msg
    assert rig["calls"][stub] == 1  # no retry
    if mode != "restore":
        assert rig["calls"]["restore_report"] == 0  # no auto-restore
    assert rig["session"].rollbacks >= 1


def test_an_apply_that_times_out_leaves_only_the_backup_committed(repair, rig, capsys):
    rig["raise_in"]["apply"] = _db_error("55P03")
    assert repair.main(_argv(rig, "apply")) == 2
    # the plan session's clean close + the backup's explicit commit; the apply
    # never commits, and its session rolls back instead of closing clean
    assert rig["session"].commits == 2 and rig["session"].rollbacks == 1
    assert rig["calls"]["backup"] == 1 and rig["calls"]["apply"] == 1
    assert "undo" not in capsys.readouterr().out


@pytest.mark.parametrize("mode", ["apply", "restore"])
def test_an_error_after_the_durable_commit_is_never_reported_as_rolled_back(
    repair, rig, monkeypatch, capsys, mode
):
    err = _db_error("08006")
    monkeypatch.setattr(
        rig["base"], "get_task_session",
        _fake_task_session(rig["session"], rig["seen"], fail_on_exit=err)
        if mode == "restore" else _fail_on_last_exit(rig, err),
    )
    with pytest.raises(OperationalError):
        repair.main(_argv(rig, mode))
    assert "rolled back" not in capsys.readouterr().out


def _fail_on_last_exit(rig, err):
    """Plan session closes cleanly; the backup/apply session fails on exit,
    after both of its explicit commits."""
    opened = []

    @contextlib.asynccontextmanager
    async def fake(**kwargs):
        rig["seen"].append(kwargs)
        opened.append(1)
        yield rig["session"]
        if len(opened) == 2:
            raise err

    return fake


# ── a COMMIT that does not return (directive 024, CERT-4198's preserved caveat) ─


class _LostAck(Exception):
    """A commit whose acknowledgement never came back (not a DBAPIError)."""


def _lost_ack(kind):
    return _db_error("08006") if kind == "dbapi" else _LostAck("connection reset")


@pytest.mark.parametrize("kind", ["dbapi", "other"])
@pytest.mark.parametrize(
    "mode,commit_no,phase,certain",
    [
        # commit 1 is the plan session's clean close; 2 is the backup; 3 the apply
        ("apply", 2, "backup-commit", "futures_markets was not written"),
        ("apply", 3, "apply-commit", "the backup is committed"),
        ("restore", 1, "restore-commit", "restore's durability is UNKNOWN"),
    ],
)
def test_a_commit_that_does_not_return_is_unknown_never_a_no_write_claim(
    repair, rig, capsys, kind, mode, commit_no, phase, certain
):
    session = rig["session"]
    real_commit = session.commit

    async def commit():
        await real_commit()
        if session.commits == commit_no:
            raise _lost_ack(kind)

    session.commit = commit
    assert repair.main(_argv(rig, mode)) == 3
    out = json.loads(capsys.readouterr().out)
    assert out["outcome"] == "UNKNOWN" and out["phase"] == phase
    assert out["readback"].endswith("scripts/repair_2722_archived_nine.py --status")
    msg = out["unknown"]
    assert certain in msg and "Not retried, not restored" in msg
    for claim in ("rolled back", "nothing was backed up", "no row was restored",
                  "nothing to restore", "no row of futures_markets was written"):
        assert claim not in msg
    if mode == "apply":
        assert out["plan_digest"] == rig["digest"]
        assert rig["calls"]["apply"] == (0 if phase == "backup-commit" else 1)
        assert rig["calls"]["restore_report"] == 0  # never an automatic undo
        assert len(rig["seen"]) == 2  # no reconnect-write, no retry session
    else:
        assert rig["calls"]["restore_report"] == 1 and len(rig["seen"]) == 1
    assert session.commits == commit_no  # nothing committed after the lost ack


@pytest.mark.parametrize("mode", ["plan", "apply", "restore"])
def test_known_success_still_exits_zero_with_no_outcome_unknown(repair, rig, capsys, mode):
    assert repair.main(_argv(rig, mode)) == 0
    assert "UNKNOWN" not in capsys.readouterr().out


def test_status_is_a_mode_that_refuses_with_writes(repair, rig, capsys):
    """--status is the readback only: never combined with a write flag."""
    for extra in (["--backup"], ["--apply"], ["--restore"]):
        assert repair.main(["--status", *extra]) == 2
        assert "refused" in json.loads(capsys.readouterr().out)
    assert rig["seen"] == []


def test_the_status_sql_reads_only_the_nine_channel():
    """The readback names only this channel's table and the exact nine, and
    carries no write or DDL verb."""
    spec = importlib.util.spec_from_file_location("r2722", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    sql = mod.STATUS_SQL
    assert "backup_2722_archived_nine" in sql and "backup_2644" not in sql
    assert "unnest(CAST(:ids AS bigint[]))" in sql
    assert not re.search(r"\b(INSERT|UPDATE|DELETE|CREATE|DROP|ALTER|TRUNCATE)\b", sql, re.I)
    assert mod.STATUS_IDS == [i for i, _ in mod.NINE]
