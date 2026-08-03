"""Queue 300B Item 1, runtime half — the tag actually reaches the backend.

``tests/test_db_session_identity_300b.py`` grades the pure rules. This file
grades the plumbing: that a scheduled calibration session really does write its
identity, that the identity is transaction-local (so a pooled web connection can
never inherit it), that the backend PID lands in the durable ledger, and that
none of it can take a build down.

The last property is the one worth being explicit about. This is a LABEL. A
label that can fail an hourly build has made the reliability situation worse,
not better, so every failure mode here degrades to "unlabelled and logged".
"""

from __future__ import annotations

import inspect
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.tasks.base import tag_task_session
from app.tasks.calibration_main_build import PhaseRunner, NullPhaseRunner
from app.utils.calibration_phase_ledger import (
    MAIN_BUILD_TASK,
    PHASE_FUTURES,
    derive_plan,
    new_main_checkpoint,
)
from app.utils.db_session_identity import (
    APPLICATION_NAME_MAX,
    KIND_CURRENT_BEAT,
    KIND_PREDEPLOY_RUN,
    classify_activity_row,
    parse_session_tag,
)

pytestmark = pytest.mark.asyncio

OWNER = "worker.3:41221"
VERSION = "q300b"
FINGERPRINT = "sha256:futures-population-v1"
GENERATION = 1_754_200_000_000


def _db(
    *,
    pid: int | None = 4080483,
    boom: Exception | None = None,
    boom_on: str = "set_config",
):
    """A session that records every statement it is asked to execute.

    ``boom_on`` scopes the failure to one kind of statement, so "the tag write
    failed" can be tested WITHOUT also breaking the statement_timeout that shares
    the call — which is the distinction the test below exists to draw.
    """
    seen: list[tuple[str, dict | None]] = []

    async def _execute(statement, params=None):
        seen.append((str(statement), params))
        if boom is not None and boom_on in str(statement):
            raise boom
        result = MagicMock()
        result.first.return_value = SimpleNamespace(
            name=params["tag"] if params else None, pid=pid
        )
        return result

    db = AsyncMock()
    db.execute.side_effect = _execute
    db.seen = seen
    return db


def _runner(*, generation: int = GENERATION, owner: str = OWNER) -> PhaseRunner:
    return PhaseRunner(
        plan=derive_plan({}),
        checkpoint=new_main_checkpoint(
            version=VERSION, fingerprint=FINGERPRINT, owner=owner, generation=generation
        ),
        checkpoint_action="fresh",
        population_version=VERSION,
        owner=owner,
        generation=generation,
        fingerprint=FINGERPRINT,
    )


# ---------------------------------------------------------------------------
# The tag reaches the backend
# ---------------------------------------------------------------------------


async def test_tagging_writes_a_parseable_identity_and_returns_the_pid():
    db = _db(pid=4080483)

    out = await tag_task_session(
        db, task=MAIN_BUILD_TASK, run_generation=GENERATION, owner=OWNER, build="abc123"
    )

    assert out["applied"] is True
    assert out["backend_pid"] == 4080483
    parsed = parse_session_tag(out["application_name"])
    assert parsed is not None
    assert parsed.task == MAIN_BUILD_TASK
    assert parsed.build == "abc123"


async def test_the_tag_is_transaction_local_so_a_pooled_session_cannot_inherit_it():
    """``is_local => true``. This is the whole pooled-session safety argument.

    A session-level ``SET`` would need a matching RESET on every exit path, and
    the exit path that matters — SIGKILL at the Celery hard limit — runs none of
    them. Transaction scope makes the reset automatic and unskippable.
    """
    db = _db()
    await tag_task_session(db, task=MAIN_BUILD_TASK, run_generation=GENERATION, owner=OWNER)

    sql, params = db.seen[0]
    assert "set_config" in sql
    # third argument is is_local
    assert sql.split("set_config(")[1].split(")")[0].strip().endswith("true")
    assert params == {"tag": params["tag"]} and ":tag" in sql


async def test_the_tag_travels_as_a_bind_parameter_not_as_sql():
    db = _db()
    await tag_task_session(
        db,
        task="'; DROP TABLE futures_outcomes; --",
        run_generation=GENERATION,
        owner=OWNER,
    )

    sql, params = db.seen[0]
    assert "DROP TABLE" not in sql
    assert "DROP" not in params["tag"]
    assert ";" not in params["tag"]


# ---------------------------------------------------------------------------
# A label must never fail a build
# ---------------------------------------------------------------------------


async def test_a_failed_tag_is_reported_not_raised():
    db = _db(boom=RuntimeError("connection reset by peer"))

    out = await tag_task_session(
        db, task=MAIN_BUILD_TASK, run_generation=GENERATION, owner=OWNER
    )

    assert out["applied"] is False
    assert out["backend_pid"] is None
    # The tag we WOULD have written is still reported, so the log line and the
    # ledger both say what identity was intended.
    assert parse_session_tag(out["application_name"]) is not None


async def test_a_tag_failure_does_not_stop_the_phase_timeout_being_armed():
    """Ordering matters: the DB backstop is the safety property, the tag is not."""
    runner = _runner()
    db = _db(boom=RuntimeError("nope"))

    await runner.apply_statement_timeout(db, PHASE_FUTURES)

    statements = [sql for sql, _ in db.seen]
    assert any("statement_timeout" in sql for sql in statements)
    assert runner.session_identity["applied"] is False


# ---------------------------------------------------------------------------
# Re-armed after every inter-phase commit
# ---------------------------------------------------------------------------


async def test_every_phase_re_arms_the_tag_because_commit_wipes_it():
    """``SET LOCAL`` dies at COMMIT, and the build commits between phases.

    Tag once at the top and phases two onward run anonymous — which would leave
    the LATER, slower phases (the ones that actually wedge) unlabelled.
    """
    runner = _runner()
    db = _db()

    await runner.apply_statement_timeout(db, PHASE_FUTURES)
    await runner.commit(db)
    await runner.apply_statement_timeout(db, PHASE_FUTURES)

    tag_calls = [params["tag"] for sql, params in db.seen if params and "tag" in params]
    assert len(tag_calls) == 2
    assert tag_calls[0] == tag_calls[1], "the identity must be stable across phases"


async def test_the_backend_pid_is_kept_even_if_a_later_re_tag_fails():
    """Losing the label later must not erase what we already proved."""
    runner = _runner()

    await runner.tag_session(_db(pid=4080483))
    assert runner.session_identity["backend_pid"] == 4080483

    await runner.tag_session(_db(boom=RuntimeError("blip")))
    assert runner.session_identity["backend_pid"] == 4080483


async def test_the_null_runner_tags_nothing():
    """The no-runner path has no ledger to join a PID back to."""
    runner = NullPhaseRunner()
    db = _db()

    out = await runner.tag_session(db)

    assert out["applied"] is False
    assert db.seen == []


# ---------------------------------------------------------------------------
# Server-visible identity survives losing the ledger
# ---------------------------------------------------------------------------


async def test_the_tag_alone_places_a_backend_without_the_ledger():
    """The hard-loss case: durable write failed, the run is gone, the row remains.

    Everything C127 needs to call this row ``predeploy`` and not ``current`` has
    to be legible from ``application_name`` by itself — no ledger, no checkpoint,
    no join.
    """
    db = _db()
    out = await tag_task_session(
        db,
        task=MAIN_BUILD_TASK,
        run_generation=GENERATION,
        owner=OWNER,
        build="oldbuild01",
    )

    row = {"application_name": out["application_name"]}
    verdict = classify_activity_row(row, current_build="newbuild02")
    assert verdict.kind == KIND_PREDEPLOY_RUN
    assert verdict.generation_relation == "predeploy"
    assert verdict.task == MAIN_BUILD_TASK

    same = classify_activity_row(row, current_build="oldbuild01")
    assert same.kind == KIND_CURRENT_BEAT


async def test_the_written_tag_is_bounded_and_redacted_on_the_real_task_name():
    db = _db()
    out = await tag_task_session(
        db,
        task=MAIN_BUILD_TASK,
        run_generation=GENERATION,
        owner="prod-worker-07.internal:4080483",
        build="a1b2c3d4e5",
    )

    tag = out["application_name"]
    assert len(tag.encode("utf-8")) <= APPLICATION_NAME_MAX
    assert "prod-worker-07" not in tag
    assert "4080483" not in tag


# ---------------------------------------------------------------------------
# The ledger records it
# ---------------------------------------------------------------------------


async def test_the_ledger_carries_the_session_identity():
    """Source-level, because the alternative is standing up a whole build.

    ``session_identity`` must be in the ledger ``extra`` on EVERY terminal — the
    timeouts and cancellations are precisely the runs whose backend may still be
    sitting on the database when someone comes looking.
    """
    from app.tasks import precompute_calibration

    src = inspect.getsource(precompute_calibration)
    assert '"session_identity": runner.session_identity' in src


async def test_the_main_build_tags_before_its_first_heavy_read():
    """A build that wedges in phase 1 never reaches a later re-tag."""
    from app.tasks import precompute_calibration

    src = inspect.getsource(precompute_calibration._run_calibration_main_build)
    tag_at = src.index("runner.tag_session(db)")
    compute_at = src.index("compute_calibration_payload(db")
    assert tag_at < compute_at


@pytest.mark.parametrize(
    "func_name",
    [
        "_compute_time_horizon_calibration",
        "_compute_fair_fight_comparison",
        "_snapshot_coverage_metrics",
    ],
)
async def test_every_scheduled_calibration_session_is_tagged(func_name):
    """Once they are ALL named, an untagged one is itself evidence.

    That is the property that makes this useful next time: a calibration-shaped
    backend with no ``application_name`` can only be a session that predates this
    change, which is a generation fact rather than an age guess.
    """
    from app.tasks import precompute_calibration

    src = inspect.getsource(getattr(precompute_calibration, func_name))
    assert "tag_scheduled_session" in src


# ---------------------------------------------------------------------------
# Web sessions stay untagged
# ---------------------------------------------------------------------------


async def test_no_route_module_can_tag_a_pooled_web_session():
    """Transaction scope is the guarantee; this is the second lock on the door.

    ``get_db`` hands out a connection from a pool shared by every request. A tag
    applied there would be wrong from the first reuse, so no request handler gets
    to reach the applier at all.
    """
    import pathlib

    routes = pathlib.Path(__file__).resolve().parents[1] / "app" / "routes"
    offenders = [
        path.name
        for path in routes.rglob("*.py")
        if "tag_task_session" in path.read_text(encoding="utf-8")
    ]
    assert offenders == []


async def test_the_web_session_factories_do_not_tag():
    from app.services import database

    for factory in (database.get_db, database.get_db_rw):
        src = inspect.getsource(factory)
        assert "application_name" not in src
        assert "tag_task_session" not in src
