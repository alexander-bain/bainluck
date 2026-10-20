"""#1853 — the attended archive-grade repair says what a lost COMMIT acknowledgement left.

PILLAR: TRUTH. SHIP: a settled Kalshi question receives its venue-backed result
through a repair whose outcome remains explicit when a connection fails.

Root's source finding (2026-10-18, operator blob b916b4f2, helper blob 31a6572d):
``main()`` caught only ``Refused``, so a backup, apply or restore COMMIT whose
acknowledgement was lost — or the session wrapper's normal-exit COMMIT after an
acknowledged apply — escaped as a bare traceback with an empty stdout: no plan
identity, no affected set, no phase. These arms pin the repair:

1. **A COMMIT that does not return is UNKNOWN** (exit 3) with the plan digest, the
   planned set, what the phase carried and each phase's state; no undo line, no
   second COMMIT, no retry, no restore — and an earlier ACKNOWLEDGED phase still
   reads ``committed``. That holds whether the COMMIT landed or not, and both
   print the same receipt (CERT-4237's follow-up): only ``--status`` can tell.
2. **An acknowledged result survives the wrapper's exit**: a failure there after
   every COMMIT came back keeps the success output, its undo line and exit 0.
3. **Cancels and interrupts keep their type** and still print the receipt; a
   failing cleanup changes neither the receipt, the exit, nor that type.
4. **A failure BEFORE a COMMIT keeps its definite answer** (``not_committed``),
   and an ordinary one re-raises as the very exception that stopped the phase.
5. **A refusal survives a failing rollback** (Root, 28da829605): both backup
   refusals — a changed leg, a missing backup row — keep ``REFUSED``, their exact
   reason and exit 2 when the rollback after them fails; one rollback, no COMMIT.

Every arm drives the PRODUCTION ``app.tasks.base.get_task_session``; only the
engine and session factory it builds are inert recorders, so its normal-exit
COMMIT is real (the rig control proves it). The plan/backup/apply/restore SQL
bodies are doubles here — their Postgres behaviour is pinned in
``tests/integration/test_kalshi_archive_grades_1853_pg.py``.
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "repair_1853_archive_grades.py"
IDS = list(range(1000, 1022))
#: The delivered undo line, verbatim: the healthy output must not move.
UNDO = ("heroku run:detached -a bainluck-heavy -- python3 "
        "scripts/repair_1853_archive_grades.py --restore")


@pytest.fixture
def repair():
    spec = importlib.util.spec_from_file_location("repair_1853_commit_ack_under_test", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _ConnectionFailure(Exception):
    sqlstate = "08006"


def _lost_ack():
    from sqlalchemy.exc import OperationalError

    return OperationalError("COMMIT", {}, _ConnectionFailure("connection lost"))


class Session:
    """A session whose COMMIT makes its pending writes durable FIRST, then may lose
    the acknowledgement — the server applied it and the client never heard back.

    ``commit_raises`` maps the session's Nth COMMIT (1-based) to what it raises.
    """

    def __init__(self, calls, commit_raises=None, rollback_raises=None, close_raises=None):
        self.calls = calls
        self.info: dict = {}
        self.pending: list[str] = []
        self.durable: list[str] = []
        self.commits = 0
        self._commit_raises = commit_raises or {}
        self._rollback_raises = rollback_raises
        self._close_raises = close_raises

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def execute(self, statement, params=None):
        # Only the plan session's READ ONLY declaration reaches here: every SQL
        # body is a double. It is recorded before the first dispose, so the
        # write-session slices below never see it.
        self.calls.append(str(statement))

    async def commit(self):
        self.calls.append("commit")
        self.commits += 1
        self.durable += self.pending
        self.pending = []
        exc = self._commit_raises.get(self.commits)
        if exc is not None:
            raise exc

    async def rollback(self):
        # A client rollback cannot reach a COMMIT the server already made durable.
        self.calls.append("rollback")
        self.pending = []
        if self._rollback_raises is not None:
            raise self._rollback_raises

    async def close(self):
        self.calls.append("close")
        if self._close_raises is not None:
            raise self._close_raises


class _InertEngine:
    def __init__(self, calls, raises=None):
        self._calls, self._raises = calls, raises

    async def dispose(self):
        self._calls.append("dispose")
        if self._raises is not None:
            raise self._raises


def _grades(repair):
    return [
        repair.ApprovedGrade(i, f"SYNTHETIC-{i}", False, "finalized", "no",
                             json.dumps({"id": i, "resolution_source": None, "is_winner": None}))
        for i in IDS
    ]


def _wire(repair, monkeypatch, sessions, dispose_raises=None, apply_raises=None,
          backup_raises=None, backup_missing=0):
    """The production wrapper over inert engines; the SQL bodies as recorders."""
    import app.tasks.base as base

    assert base.get_task_session.__module__ == "app.tasks.base"
    assert base.get_task_session.__wrapped__.__qualname__ == "get_task_session"
    queue = list(sessions)
    calls = sessions[0].calls

    def engine_factory(**kwargs):
        return _InertEngine(calls, dispose_raises)

    def session_maker(bound, **kwargs):
        s = queue.pop(0)
        return lambda: s

    monkeypatch.setattr(base, "_get_task_engine", engine_factory)
    monkeypatch.setattr(base, "async_sessionmaker", session_maker)
    grades = _grades(repair)

    async def build_plan(session, legs):
        calls.append("plan")
        return grades, {}

    async def backup(session, grades_, digest):
        calls.append("backup")
        if backup_raises is not None:
            raise backup_raises
        session.pending.append("backup")
        return backup_missing

    async def apply(session, legs, digest):
        calls.append("apply")
        if apply_raises is not None:
            raise apply_raises
        session.pending.append("22-grades")
        return {"written_ids": list(IDS), "skipped_changed_since_backup": []}

    async def restore_report(session):
        calls.append("restore")
        session.pending.append("22-restored")
        return {"restored": list(IDS), "preserved_changed_since_apply": []}

    async def status_report(session):
        calls.append("status")
        return {"backup_table": "present", "digests": {}}

    monkeypatch.setattr(repair, "build_plan", build_plan)
    monkeypatch.setattr(repair, "backup", backup)
    monkeypatch.setattr(repair, "apply", apply)
    monkeypatch.setattr(repair, "restore_report", restore_report)
    # raising=False keeps the rig runnable against an operator without --status
    # (the delivered blob), so a red there is the arm's own, not the rig's.
    monkeypatch.setattr(repair, "status_report", status_report, raising=False)
    monkeypatch.setenv("HEROKU_APP_NAME", "bainluck-heavy")
    return grades


def _apply_argv(repair):
    return ["--backup", "--apply", "--digest", repair.plan_digest(_grades(repair))]


def _apply_run(repair, monkeypatch, write: Session, **kw):
    """Plan session (healthy) + the write session under test; returns main()'s code."""
    plan = Session(write.calls)
    _wire(repair, monkeypatch, [plan, write], **kw)
    return repair.main(_apply_argv(repair))


def _receipt(out: str) -> dict:
    return json.loads(out[out.index("{"):])


def _write_calls(s: Session) -> list[str]:
    """The write session's calls: everything after the plan session disposed."""
    return s.calls[s.calls.index("dispose") + 1:]


#: The wrapper's EXCEPTION exit: cleanup only. Its NORMAL exit is ["commit", ...].
_CLEANUP = ["rollback", "close", "dispose"]


# ── the rig ──────────────────────────────────────────────────────────────────


def test_the_rig_is_the_production_wrapper_and_its_normal_exit_commits(
    repair, monkeypatch, capsys
):
    # If the inert wiring dropped the after-yield COMMIT, every "no second
    # COMMIT" arm below would pass for the wrong reason.
    calls: list[str] = []
    write = Session(calls)
    assert _apply_run(repair, monkeypatch, write) == 0
    assert _write_calls(write) == [
        "backup", "commit", "apply", "commit", "commit", "close", "dispose",
    ]
    assert write.durable == ["backup", "22-grades"]
    captured = capsys.readouterr()
    out = _receipt(captured.out)
    # The healthy output is the original success shape, undo line and all.
    assert out["applied"]["written_ids"] == IDS
    assert out["undo"] == UNDO
    assert "outcome" not in out and "phases" not in out
    assert captured.err == ""


# ── 1. a COMMIT that does not return is UNKNOWN ──────────────────────────────


@pytest.mark.parametrize("raises", [_lost_ack(), ConnectionError("ack lost")],
                         ids=["dbapi-08006", "connection-error"])
def test_a_lost_backup_ack_is_unknown_and_the_apply_never_starts(
    repair, monkeypatch, capsys, raises
):
    calls: list[str] = []
    write = Session(calls, commit_raises={1: raises})
    assert _apply_run(repair, monkeypatch, write) == 3
    captured = capsys.readouterr()
    assert write.durable == ["backup"]  # the specimen: it DID land
    assert _write_calls(write) == ["backup", "commit", *_CLEANUP]
    r = _receipt(captured.out)
    assert r["outcome"] == "UNKNOWN" and r["mode"] == "apply"
    assert r["phases"] == {"backup": "UNKNOWN"}
    assert r["plan_digest"] == _apply_argv(repair)[-1]
    assert [p["outcome_id"] for p in r["planned"]] == IDS
    assert "applied" not in r and "undo" not in r
    assert r["readback"] == repair.STATUS_COMMAND
    assert r["error"].startswith(type(raises).__name__)
    assert "Traceback" not in captured.err


@pytest.mark.parametrize("then", ["lost", "ack"])
def test_a_lost_apply_ack_is_unknown_and_nothing_commits_after_it(
    repair, monkeypatch, capsys, then
):
    # ``then`` is what a later COMMIT would do if anything sent one; nothing may.
    calls: list[str] = []
    later = _lost_ack() if then == "lost" else None
    write = Session(calls, commit_raises={2: _lost_ack(), 3: later})
    assert _apply_run(repair, monkeypatch, write) == 3
    captured = capsys.readouterr()
    assert write.durable == ["backup", "22-grades"]
    assert write.commits == 2
    assert _write_calls(write) == ["backup", "commit", "apply", "commit", *_CLEANUP]
    r = _receipt(captured.out)
    assert r["outcome"] == "UNKNOWN"
    # The acknowledged backup is still known; only the apply is unknown.
    assert r["phases"] == {"backup": "committed", "apply": "UNKNOWN"}
    assert r["applied"]["written_ids"] == IDS
    assert "undo" not in r and "--restore" not in captured.out
    assert "Traceback" not in captured.err


class _NeverLandedSession(Session):
    """The other half of UNKNOWN: the configured COMMIT fails BEFORE the server made
    anything durable — the transaction never landed and the client cannot tell."""

    async def commit(self):
        if self.commits + 1 not in self._commit_raises:
            return await super().commit()
        self.calls.append("commit")
        self.commits += 1
        raise self._commit_raises[self.commits]


#: phase → (its COMMIT's ordinal in the write session, what is durable before it).
_PHASE_COMMIT = {"backup": (1, []), "apply": (2, ["backup"]), "restore": (1, [])}


def _run_phase(repair, monkeypatch, phase, write: Session) -> int:
    if phase == "restore":
        _wire(repair, monkeypatch, [write])
        return repair.main(["--restore"])
    return _apply_run(repair, monkeypatch, write)


@pytest.mark.parametrize("phase", list(_PHASE_COMMIT))
def test_a_commit_that_never_landed_is_unknown_too_and_nothing_commits_after_it(
    repair, monkeypatch, capsys, phase
):
    # CERT-4237's follow-up: every arm above loses the ack AFTER the write landed.
    # The client sees the same failure when it did not land, so the receipt must
    # be UNKNOWN there as well — never "not_committed", never an undo line.
    n, before = _PHASE_COMMIT[phase]
    calls: list[str] = []
    write = _NeverLandedSession(calls, commit_raises={n: _lost_ack()})
    assert _run_phase(repair, monkeypatch, phase, write) == 3
    captured = capsys.readouterr()
    assert write.durable == before  # the specimen: this phase's writes did NOT land
    assert write.pending == []  # the wrapper's rollback discarded them
    assert write.commits == n  # no retry, no wrapper COMMIT behind it
    assert calls[-3:] == _CLEANUP
    r = _receipt(captured.out)
    assert r["outcome"] == "UNKNOWN"
    assert r["phases"][phase] == "UNKNOWN"
    assert all(v == "committed" for k, v in r["phases"].items() if k != phase)
    assert "undo" not in r and "--restore" not in captured.out
    assert r["readback"] == repair.STATUS_COMMAND
    assert r["error"].startswith("OperationalError")
    assert "Traceback" not in captured.err


@pytest.mark.parametrize("phase", list(_PHASE_COMMIT))
def test_landed_and_never_landed_print_the_same_receipt(repair, monkeypatch, capsys, phase):
    # The client cannot tell the two apart, so neither may the receipt: the only
    # answer is the read-back. A receipt that differed would be claiming knowledge
    # it does not have.
    n, before = _PHASE_COMMIT[phase]
    receipts, durable = [], []
    for kind in (Session, _NeverLandedSession):
        write = kind([], commit_raises={n: _lost_ack()})
        assert _run_phase(repair, monkeypatch, phase, write) == 3
        receipts.append(_receipt(capsys.readouterr().out))
        durable.append(write.durable)
    assert durable[0] != durable[1] and durable[1] == before  # the two worlds differ
    assert receipts[0] == receipts[1]


def test_a_lost_restore_ack_is_unknown_with_the_restored_set(repair, monkeypatch, capsys):
    calls: list[str] = []
    write = Session(calls, commit_raises={1: _lost_ack()})
    _wire(repair, monkeypatch, [write])
    assert repair.main(["--restore"]) == 3
    captured = capsys.readouterr()
    assert write.durable == ["22-restored"]
    assert calls == ["restore", "commit", *_CLEANUP]
    r = _receipt(captured.out)
    assert r["outcome"] == "UNKNOWN" and r["mode"] == "restore"
    assert r["phases"] == {"restore": "UNKNOWN"}
    assert r["restored"] == IDS and r["readback"] == repair.STATUS_COMMAND
    assert "Traceback" not in captured.err


# ── 2. an acknowledged result survives the wrapper's exit ────────────────────


@pytest.mark.parametrize("where", ["exit-commit", "close", "dispose"])
def test_a_failure_leaving_the_wrapper_after_an_acknowledged_apply_keeps_the_result(
    repair, monkeypatch, capsys, where
):
    calls: list[str] = []
    write = Session(
        calls,
        commit_raises={3: _lost_ack()} if where == "exit-commit" else None,
        close_raises=RuntimeError("close") if where == "close" else None,
    )
    plan = Session(calls)
    dispose = RuntimeError("dispose") if where == "dispose" else None
    _wire(repair, monkeypatch, [plan, write])
    if dispose is not None:
        # Only the WRITE session's engine fails to dispose.
        import app.tasks.base as base

        engines = iter([_InertEngine(calls), _InertEngine(calls, dispose)])
        monkeypatch.setattr(base, "_get_task_engine", lambda **kw: next(engines))
    assert repair.main(_apply_argv(repair)) == 0
    captured = capsys.readouterr()
    assert write.durable == ["backup", "22-grades"]
    r = _receipt(captured.out)
    assert r["outcome"] == "COMMITTED"
    assert r["phases"] == {"backup": "committed", "apply": "committed"}
    assert r["applied"]["written_ids"] == IDS and r["undo"] == UNDO
    assert "error" not in r
    assert "after every COMMIT above was acknowledged" in captured.err
    assert "Traceback" not in captured.err


def test_a_restore_whose_wrapper_exit_fails_still_reports_it_committed(
    repair, monkeypatch, capsys
):
    calls: list[str] = []
    write = Session(calls, commit_raises={2: _lost_ack()})
    _wire(repair, monkeypatch, [write])
    assert repair.main(["--restore"]) == 0
    r = _receipt(capsys.readouterr().out)
    assert r["outcome"] == "COMMITTED" and r["phases"] == {"restore": "committed"}
    assert r["restored"] == IDS


# ── 3. cancels and interrupts keep their type ────────────────────────────────


@pytest.mark.parametrize("phase_commit", [1, 2], ids=["backup", "apply"])
def test_an_interrupted_commit_keeps_its_type_and_still_says_unknown(
    repair, monkeypatch, capsys, phase_commit
):
    calls: list[str] = []
    write = Session(calls, commit_raises={phase_commit: KeyboardInterrupt()})
    with pytest.raises(KeyboardInterrupt):
        _apply_run(repair, monkeypatch, write)
    r = _receipt(capsys.readouterr().out)
    assert r["outcome"] == "UNKNOWN"
    assert list(r["phases"].values())[-1] == "UNKNOWN"
    assert write.commits == phase_commit  # nothing COMMITs after the interrupted one


def test_a_cancelled_apply_commit_propagates_as_a_cancel(repair, monkeypatch, capsys):
    calls: list[str] = []
    write = Session(calls, commit_raises={2: asyncio.CancelledError()})
    with pytest.raises(asyncio.CancelledError):
        _apply_run(repair, monkeypatch, write)
    r = _receipt(capsys.readouterr().out)
    assert r["outcome"] == "UNKNOWN"
    assert r["phases"] == {"backup": "committed", "apply": "UNKNOWN"}
    assert r["error"].startswith("CancelledError")
    # The cancel bypasses the wrapper's rollback; it never sends a third COMMIT.
    assert write.commits == 2


def test_a_cleanup_failure_never_replaces_a_cancelled_commit(repair, monkeypatch, capsys):
    calls: list[str] = []
    write = Session(calls, commit_raises={2: asyncio.CancelledError()},
                    close_raises=RuntimeError("close on a dead connection"))
    with pytest.raises(asyncio.CancelledError):
        _apply_run(repair, monkeypatch, write)
    captured = capsys.readouterr()
    assert _receipt(captured.out)["outcome"] == "UNKNOWN"
    assert "cleanup raised RuntimeError" in captured.err


def test_an_interrupt_during_the_cleanup_after_unknown_propagates_as_itself(
    repair, monkeypatch, capsys
):
    calls: list[str] = []
    write = Session(calls, commit_raises={2: _lost_ack()}, rollback_raises=KeyboardInterrupt())
    with pytest.raises(KeyboardInterrupt):
        _apply_run(repair, monkeypatch, write)
    r = _receipt(capsys.readouterr().out)
    assert r["outcome"] == "UNKNOWN" and r["error"].startswith("OperationalError")


@pytest.mark.parametrize("what", ["rollback", "close", "dispose"])
def test_a_cleanup_failure_after_unknown_keeps_the_receipt_and_exit_3(
    repair, monkeypatch, capsys, what
):
    calls: list[str] = []
    broken = RuntimeError(f"{what} on a dead connection")
    write = Session(
        calls, commit_raises={2: _lost_ack()},
        rollback_raises=broken if what == "rollback" else None,
        close_raises=broken if what == "close" else None,
    )
    plan = Session(calls)
    _wire(repair, monkeypatch, [plan, write])
    if what == "dispose":
        import app.tasks.base as base

        engines = iter([_InertEngine(calls), _InertEngine(calls, broken)])
        monkeypatch.setattr(base, "_get_task_engine", lambda **kw: next(engines))
    assert repair.main(_apply_argv(repair)) == 3
    captured = capsys.readouterr()
    r = _receipt(captured.out)
    # The receipt names the COMMIT's failure, never the cleanup's.
    assert r["outcome"] == "UNKNOWN" and r["error"].startswith("OperationalError")
    assert r["phases"] == {"backup": "committed", "apply": "UNKNOWN"}
    assert "cleanup raised RuntimeError" in captured.err
    assert "Traceback" not in captured.err
    assert write.commits == 2


# ── 4. a failure BEFORE a COMMIT keeps its definite answer ───────────────────


def test_a_failure_inside_the_apply_is_not_committed_and_reraises_itself(
    repair, monkeypatch, capsys
):
    calls: list[str] = []
    boom = _lost_ack()
    write = Session(calls)
    with pytest.raises(type(boom)) as caught:
        _apply_run(repair, monkeypatch, write, apply_raises=boom)
    assert caught.value is boom  # the original exception, not a wrapper
    r = _receipt(capsys.readouterr().out)
    assert r["outcome"] == "NOT_COMMITTED"
    assert r["phases"] == {"backup": "committed", "apply": "not_committed"}
    assert write.durable == ["backup"] and write.commits == 1
    assert _write_calls(write) == ["backup", "commit", "apply", *_CLEANUP]


def test_the_original_failure_survives_a_failing_rollback(repair, monkeypatch, capsys):
    calls: list[str] = []
    boom = ValueError("statement failed")
    write = Session(calls, rollback_raises=RuntimeError("rollback"))
    with pytest.raises(ValueError) as caught:
        _apply_run(repair, monkeypatch, write, apply_raises=boom)
    assert caught.value is boom
    assert _receipt(capsys.readouterr().out)["outcome"] == "NOT_COMMITTED"


def test_a_cancel_before_the_commit_is_not_reported_unknown(repair, monkeypatch, capsys):
    calls: list[str] = []
    write = Session(calls)
    with pytest.raises(asyncio.CancelledError):
        _apply_run(repair, monkeypatch, write, apply_raises=asyncio.CancelledError())
    r = _receipt(capsys.readouterr().out)
    assert r["outcome"] == "NOT_COMMITTED"
    assert r["phases"] == {"backup": "committed", "apply": "not_committed"}
    assert write.commits == 1


def test_a_refusal_after_the_backup_says_the_backup_committed(repair, monkeypatch, capsys):
    calls: list[str] = []
    write = Session(calls)
    code = _apply_run(repair, monkeypatch, write, apply_raises=repair.Refused(
        "outcome 1000: frozen verdict no longer matches the listing"))
    assert code == 2
    r = _receipt(capsys.readouterr().out)
    assert r["outcome"] == "REFUSED"
    assert r["phases"] == {"backup": "committed", "apply": "not_committed"}
    assert "frozen verdict" in r["refusal"]
    assert write.commits == 1


def test_a_backup_refusal_commits_nothing(repair, monkeypatch, capsys):
    calls: list[str] = []
    write = Session(calls)
    code = _apply_run(repair, monkeypatch, write,
                      backup_raises=repair.Refused("legs [1000] changed since the plan"))
    assert code == 2
    r = _receipt(capsys.readouterr().out)
    assert r["outcome"] == "REFUSED" and r["phases"] == {"backup": "not_committed"}
    assert write.commits == 0 and write.durable == []


#: Both refusals the backup phase can raise, and how each reaches it.
_BACKUP_REFUSALS = {
    "changed-leg": ({"backup_raises": "REFUSAL"},
                    "legs [1000] changed since the plan was approved; nothing written"),
    "missing-backup-row": ({"backup_missing": 3},
                           "3 planned legs have no backup row; nothing written"),
}


@pytest.mark.parametrize("rollback", ["healthy", "broken"])
@pytest.mark.parametrize("branch", list(_BACKUP_REFUSALS))
def test_a_backup_refusal_keeps_its_reason_and_exit_2_whatever_the_rollback_does(
    repair, monkeypatch, capsys, branch, rollback
):
    # Root's sixth control on 28da829605: the phase rolled back BEFORE it recorded
    # the refusal, so a rollback failing on a dead connection became the receipt's
    # failure — NOT_COMMITTED, a RuntimeError traceback, the reason lost.
    kw, reason = _BACKUP_REFUSALS[branch]
    if kw.get("backup_raises") == "REFUSAL":
        kw = {"backup_raises": repair.Refused(reason)}
    calls: list[str] = []
    broken = RuntimeError("rollback transport failed")
    write = Session(calls, rollback_raises=broken if rollback == "broken" else None)
    assert _apply_run(repair, monkeypatch, write, **kw) == 2
    captured = capsys.readouterr()
    r = _receipt(captured.out)
    assert r["outcome"] == "REFUSED" and r["mode"] == "apply"
    assert r["refusal"] == reason
    assert r["error"] == f"Refused: {reason}"
    assert r["phases"] == {"backup": "not_committed"}
    assert "undo" not in r and "applied" not in r
    # It left the session exceptionally: ONE rollback (the wrapper's), no COMMIT.
    assert _write_calls(write) == ["backup", *_CLEANUP]
    assert write.commits == 0 and write.durable == []
    assert "apply" not in _write_calls(write)
    assert "Traceback" not in captured.err
    if rollback == "broken":
        assert ("cleanup raised RuntimeError after the Refused reported above"
                in captured.err)
    else:
        assert captured.err == ""


def test_a_refusal_before_any_write_keeps_its_original_shape(repair, monkeypatch, capsys):
    calls: list[str] = []
    plan = Session(calls)
    _wire(repair, monkeypatch, [plan])
    assert repair.main(["--backup", "--apply", "--digest", "not-the-plan"]) == 2
    out = json.loads(capsys.readouterr().out)
    assert set(out) == {"refused"} and "does not match this plan" in out["refused"]
    assert "backup" not in calls


# ── the read-only status packet ──────────────────────────────────────────────


def test_status_is_read_only(repair, monkeypatch, capsys):
    calls: list[str] = []
    s = Session(calls)
    _wire(repair, monkeypatch, [s])
    assert repair.main(["--status"]) == 0
    assert calls[:2] == ["status", "rollback"]
    assert s.durable == [] and "backup" not in calls and "apply" not in calls
    assert json.loads(capsys.readouterr().out)["backup_table"] == "present"


@pytest.mark.parametrize("flag", ["--backup", "--apply", "--restore"])
def test_status_refuses_a_write_flag(repair, monkeypatch, capsys, flag):
    assert repair.main(["--status", flag]) == 2
    assert "read-only" in json.loads(capsys.readouterr().out)["refused"]
