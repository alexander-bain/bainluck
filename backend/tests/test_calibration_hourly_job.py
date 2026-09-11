"""Guards for the hourly calibration rebuild as a Heroku one-off (#5001, THRU-B).

The ship: the rebuild stops being killed mid-build by every master merge, because
a Heroku one-off dyno is not cycled by an app release. The reader stops seeing a
/calibration page whose last good publish is hours stale.

Five classes of defect are guarded here, and each one is a way this ship could
land looking correct and do nothing:

1. **The switch reads any truthy string.** `CALIBRATION_BEAT_DISABLED=0` turning
   the beat OFF is silent and hourly.
2. **The one-off re-enqueues to `worker-heavy`.** The build then dies to exactly
   the release cycle this ship exists to survive, and every symptom is unchanged.
3. **The lease TTL is the module default.** 330 s against a ~1353 s p95 expires
   mid-build and admits the second concurrent copy the lease exists to refuse.
4. **The missing-run alert is keyed to the beat.** Disabling the beat then
   removes the monitor at the same instant it removes the runner.
5. **The default rots to "disabled".** Nobody notices until the page ages.
"""

from __future__ import annotations

import importlib.util
import os
import sys

import pytest

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT_PATH = os.path.join(BACKEND, "scripts", "run_calibration_hourly.py")


def _load_job():
    """Import the one-off entry point by path (it lives in scripts/, not a pkg)."""
    spec = importlib.util.spec_from_file_location("run_calibration_hourly", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules["run_calibration_hourly"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def job():
    return _load_job()


# ---------------------------------------------------------------------------
# 1. The founder switch — BOTH directions, and the non-"1" controls.
# ---------------------------------------------------------------------------

def test_switch_unset_leaves_the_beat_scheduled():
    """The default must stay ON. A default that rots to 'disabled' is silent."""
    from app.tasks import CALIBRATION_BEAT_ENTRY, apply_calibration_beat_switch

    schedule = {CALIBRATION_BEAT_ENTRY: {"task": "app.tasks.precompute_calibration_main"}}
    apply_calibration_beat_switch(schedule, env={})

    assert CALIBRATION_BEAT_ENTRY in schedule


def test_switch_exactly_one_removes_the_beat_entry():
    from app.tasks import (
        CALIBRATION_BEAT_DISABLED_ENV,
        CALIBRATION_BEAT_ENTRY,
        apply_calibration_beat_switch,
    )

    schedule = {
        CALIBRATION_BEAT_ENTRY: {"task": "app.tasks.precompute_calibration_main"},
        "some-other-beat": {"task": "app.tasks.other"},
    }
    apply_calibration_beat_switch(schedule, env={CALIBRATION_BEAT_DISABLED_ENV: "1"})

    assert CALIBRATION_BEAT_ENTRY not in schedule
    # It removes ONE entry, not the schedule.
    assert "some-other-beat" in schedule


@pytest.mark.parametrize("value", ["0", "false", "no", "", "true", "yes", " 1"])
def test_switch_non_exact_values_leave_the_beat_running(value):
    """Only the literal "1" disables it.

    `"0"`, `"false"` and `"no"` are what a person types to mean OFF; a switch
    that reads them as ON is the silent-hourly failure. `"true"`/`"yes"` are the
    opposite mistake and are ALSO controls: they leave the beat running, which is
    the safe direction — the rebuild keeps happening either way.

    `" 1"` (a stray space, the classic `config:set` paste) is here deliberately:
    it does NOT disable the beat. If the beat and the one-off ever both run they
    share a lease key, so the cost is a declined slot, not two builds.
    """
    from app.tasks import (
        CALIBRATION_BEAT_DISABLED_ENV,
        CALIBRATION_BEAT_ENTRY,
        apply_calibration_beat_switch,
    )

    schedule = {CALIBRATION_BEAT_ENTRY: {"task": "app.tasks.precompute_calibration_main"}}
    apply_calibration_beat_switch(schedule, env={CALIBRATION_BEAT_DISABLED_ENV: value})

    assert CALIBRATION_BEAT_ENTRY in schedule, f"{value!r} must not disable the beat"


def test_switch_is_idempotent_and_survives_a_missing_entry():
    from app.tasks import (
        CALIBRATION_BEAT_DISABLED_ENV,
        CALIBRATION_BEAT_ENTRY,
        apply_calibration_beat_switch,
    )

    schedule = {CALIBRATION_BEAT_ENTRY: {"task": "app.tasks.precompute_calibration_main"}}
    env = {CALIBRATION_BEAT_DISABLED_ENV: "1"}
    apply_calibration_beat_switch(schedule, env=env)
    apply_calibration_beat_switch(schedule, env=env)  # must not raise

    assert CALIBRATION_BEAT_ENTRY not in schedule


def test_the_live_schedule_still_carries_the_beat_by_default():
    """Not a restatement of the unit test above — this reads the REAL schedule.

    The switch is applied at import time against `os.environ`. CI runs without
    `CALIBRATION_BEAT_DISABLED`, so the shipped default must still schedule the
    rebuild. If this fails, production stopped rebuilding calibration.
    """
    from app.tasks import CALIBRATION_BEAT_ENTRY, celery_app

    if os.getenv("CALIBRATION_BEAT_DISABLED") == "1":
        pytest.skip("switch is set in this environment; the default is not under test")

    entry = celery_app.conf.beat_schedule[CALIBRATION_BEAT_ENTRY]
    assert entry["task"] == "app.tasks.precompute_calibration_main"
    assert entry["options"]["queue"] == "heavy"


def test_the_app_boots_with_the_switch_on():
    """A SUBPROCESS, because the switch is applied at IMPORT time.

    This is the branch that only ever runs in production, on the one occasion
    that matters: the moment Alex sets the config var. Every other test in this
    file drives `apply_calibration_beat_switch` as a function, which cannot
    catch an import-time failure — and there is a real one available. Later in
    the same module, `_EXPIRING_WARMER_BEATS` indexes `beat_schedule[name]`
    DIRECTLY and deliberately raises on a missing key ("a renamed beat must fail
    loudly here"). If the calibration entry ever joins that list, removing it
    would `KeyError` at import and the app would not boot — with the switch on,
    in production, at the worst possible moment.

    So: boot it for real, with the var set, and assert the app imports.
    """
    import subprocess

    env = dict(os.environ, CALIBRATION_BEAT_DISABLED="1")
    proc = subprocess.run(
        [
            sys.executable, "-c",
            "from app.tasks import celery_app, CALIBRATION_BEAT_ENTRY\n"
            "s = celery_app.conf.beat_schedule\n"
            "assert CALIBRATION_BEAT_ENTRY not in s, 'switch did not remove the entry'\n"
            "assert len(s) > 100, f'schedule collapsed to {len(s)} entries'\n"
            "from app.main import app\n"
            "print('OK', len(s), len(app.routes))\n"
        ],
        cwd=BACKEND, env=env, capture_output=True, text=True, timeout=300,
    )

    assert proc.returncode == 0, (
        f"the app does not boot with CALIBRATION_BEAT_DISABLED=1:\n{proc.stderr[-3000:]}"
    )
    assert proc.stdout.startswith("OK ")


# ---------------------------------------------------------------------------
# 2. The one-off runs the build HERE. It must never hand it back to heavy.
# ---------------------------------------------------------------------------

def test_the_job_never_re_enqueues_to_celery():
    """An AST read, because this is the defect that fakes success.

    `precompute_calibration_main.delay()` from a one-off returns instantly, exits
    0, logs happily — and hands the build straight back to `worker-heavy`, the
    process a release kills. Every symptom of #5001 would survive the fix.

    🔴 THIS IS AN AST WALK AND NOT A SUBSTRING SCAN, AND THE FIRST DRAFT PROVED
    WHY: the substring version failed on this very file's own docstring, which
    names `.delay()` to explain why it must not be used. A prose-sensitive
    census is the wrong instrument for a call-site question — it fires on
    comments and it would equally miss `getattr(task, "de" + "lay")`. The AST
    sees calls, and only calls.
    """
    import ast

    tree = ast.parse(open(SCRIPT_PATH, encoding="utf-8").read())
    forbidden = {"delay", "apply_async", "send_task"}

    offenders = [
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in forbidden
    ] + [
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in forbidden
    ]

    assert offenders == [], (
        f"{offenders} in the one-off re-enqueues the build onto worker-heavy, "
        "which is the exact process #5001 exists to stop depending on"
    )


def test_the_re_enqueue_guard_can_actually_fail():
    """The guard above passes on a file that never mentions Celery at all.

    So prove the instrument fires: the same walk, over a snippet that DOES
    re-enqueue, must find it. Without this, a walk that silently matched nothing
    (a renamed attribute, a wrong node type) would read as a clean pass forever.
    """
    import ast

    tree = ast.parse("precompute_calibration_main.delay()\nsend_task('x')\n")
    forbidden = {"delay", "apply_async", "send_task"}

    offenders = [
        node.func.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in forbidden
    ] + [
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in forbidden
    ]

    assert sorted(offenders) == ["delay", "send_task"]


def test_the_job_runs_the_build_through_the_beats_own_boundary(job):
    """Same entry point, same tracking boundary, same metric label as the beat.

    This is what keeps `task_verdict.ENFORCED_TASKS`, task-metrics and the
    site-health tile continuous across the cutover instead of starting an empty
    new series under a new name.
    """
    from app.utils.task_verdict import ENFORCED_TASKS

    source = open(SCRIPT_PATH, encoding="utf-8").read()
    assert "_tracked_run(" in source
    assert "_precompute_calibration_main()" in source
    assert job.METRIC_LABEL == "precompute_calibration_main"
    assert job.METRIC_LABEL in ENFORCED_TASKS, (
        "the label must stay enrolled in the verdict contract, or a run that "
        "banks nothing records as healthy"
    )


def test_the_lease_key_is_shared_with_the_beat(job):
    """Beat and one-off must contend on ONE key.

    During the attended cutover both can briefly be armed. Sharing the key makes
    that a declined slot instead of two concurrent builds of the same page.
    """
    from app.tasks import celery_app  # noqa: F401 — import proves the name resolves

    assert job.TASK_NAME == "app.tasks.precompute_calibration_main"


# ---------------------------------------------------------------------------
# 3. The runtime bound, and the lease TTL that must exceed it.
# ---------------------------------------------------------------------------

def test_runtime_bound_defaults_to_the_beats_soft_limit(job):
    assert job.runtime_bound_seconds(env={}) == 1500


def test_runtime_bound_matches_the_beats_declared_soft_time_limit(job):
    """Two constants answering one question must not be free to drift.

    The beat declares `soft_time_limit=1500`; the one-off restates it because a
    one-off has no Celery to enforce it. Assert the gap is zero rather than
    trusting two independently-edited numbers.
    """
    from app.tasks import celery_app

    task = celery_app.tasks["app.tasks.precompute_calibration_main"]
    assert task.soft_time_limit == job.DEFAULT_RUNTIME_BOUND_SECONDS


@pytest.mark.parametrize("raw", ["900", " 900 "])
def test_runtime_bound_accepts_an_override(job, raw):
    assert job.runtime_bound_seconds(env={job.RUNTIME_BOUND_ENV: raw}) == 900


@pytest.mark.parametrize("raw", ["", "abc", "1.5", "0", "-30", None])
def test_runtime_bound_falls_back_rather_than_raising(job, raw):
    """A typo in a config var must not be able to stop the rebuild entirely."""
    env = {} if raw is None else {job.RUNTIME_BOUND_ENV: raw}
    assert job.runtime_bound_seconds(env=env) == job.DEFAULT_RUNTIME_BOUND_SECONDS


def test_lease_ttl_strictly_exceeds_the_runtime_bound(job):
    for bound in (60, 900, 1500, 3000):
        assert job.lease_ttl_seconds(bound) > bound


def test_lease_ttl_is_not_the_module_default(job):
    """The trap this ship had to step over.

    `single_flight.DEFAULT_LEASE_TTL_SECONDS` is 330 s, derived from Celery's
    300 s GLOBAL hard kill — a bound `precompute_calibration_main` overrides
    with `soft_time_limit=1500`. Taking the default would expire the lease
    ~19 minutes into a ~23-minute build and let a second copy start.
    """
    from app.utils.single_flight import DEFAULT_LEASE_TTL_SECONDS

    ttl = job.lease_ttl_seconds(job.runtime_bound_seconds(env={}))
    assert ttl > DEFAULT_LEASE_TTL_SECONDS
    assert ttl > 1500


# ---------------------------------------------------------------------------
# 4. Exit codes — a declined slot is not a failure.
# ---------------------------------------------------------------------------

def test_complete_terminal_exits_zero(job):
    summary = {"phase_ledger": {"terminal": "complete", "health": "green"}}
    assert job.exit_code_for(summary) == job.EXIT_OK


@pytest.mark.parametrize(
    "terminal", ["partial", "failed", "interrupted", "cancelled"],
)
def test_non_publishable_terminals_exit_nonzero(job, terminal):
    summary = {"phase_ledger": {"terminal": terminal, "health": "red"}}
    assert job.exit_code_for(summary) == job.EXIT_FAILED


def test_declining_the_slot_exits_zero(job, monkeypatch):
    """A Scheduler firing while last hour is still building is CORRECT.

    Exiting non-zero there pages a human for the guard working. The build must
    not be called at all on this path.
    """
    from app.utils.single_flight import Lease

    called = []
    monkeypatch.setattr(job, "_run_build", lambda bound: called.append(bound))

    import contextlib

    refused = Lease(
        task=job.TASK_NAME, key="k", token=None, acquired=False, reason="already_running"
    )

    @contextlib.contextmanager
    def _refuse(task, ttl_seconds=None):
        yield refused

    monkeypatch.setattr("app.utils.single_flight.single_flight", _refuse)

    assert job.main() == job.EXIT_OK
    assert called == [], "a declined slot must not run the build"


# ---------------------------------------------------------------------------
# 4b. The SECOND lock (#5335) — the beat holds the checkpoint, not our lease.
#
# The script's own `single_flight` lease can only ever be held by another copy
# of the script. The beat in `worker-heavy` declines us from INSIDE the build
# instead, which arrives as a summary, not as a refused lease — so it lands in
# `exit_code_for`, where `verdict_for` rightly calls it non-COMPLETE and the
# process rightly used to exit 1 at an operator who was told to wait for a 0.
# ---------------------------------------------------------------------------

def _checkpoint_declined_summary():
    """The literal shape `_precompute_calibration_main` returns on REFUSE."""
    return {
        "status": "skipped",
        "reason": "checkpoint_leased",
        "owner": "e8da65af-505b-48d6-9d99-425bbfe5dc46:20",
        "ledger_write": "ok",
    }


def test_a_checkpoint_stand_down_exits_zero(job):
    """The #5335 regression, reproduced from production run.5277 / run.3049."""
    assert job.exit_code_for(_checkpoint_declined_summary()) == job.EXIT_OK


def test_a_checkpoint_stand_down_exits_zero_through_main(job, monkeypatch):
    """Through `main`, so the stand-down LOG branch is executed too.

    `exit_code_for` being right does not prove the process is: the branch that
    reports the stand-down reads `summary["owner"]`, and a mistake there raises
    on exactly the path this ship exists to make clean.
    """
    import contextlib

    from app.utils.single_flight import Lease

    monkeypatch.setattr(
        job, "_run_build", lambda bound: _checkpoint_declined_summary()
    )
    granted = Lease(
        task=job.TASK_NAME, key="k", token="t", acquired=True, reason=None
    )

    @contextlib.contextmanager
    def _grant(task, ttl_seconds=None):
        yield granted

    monkeypatch.setattr("app.utils.single_flight.single_flight", _grant)

    assert job.main() == job.EXIT_OK


@pytest.mark.parametrize(
    "reason",
    ["population_empty", "fingerprint_mismatch", "no_rows", "", None],
)
def test_a_skip_for_ANY_OTHER_reason_still_exits_one(job, reason):
    """The discriminator — without this, the fix is `status == "skipped"`.

    A build that did not happen for a reason nobody has vetted is exactly the
    silence #1515 was about. Only the checkpoint lease is exempt.
    """
    summary = {"status": "skipped", "reason": reason}
    assert job.exit_code_for(summary) == job.EXIT_FAILED


@pytest.mark.parametrize("summary", [None, "skipped", 0, [], ("skipped",)])
def test_a_non_dict_summary_is_never_a_stand_down(job, summary):
    """Totality: an unrecognised summary must not fall through to a clean exit."""
    assert job.is_checkpoint_declined(summary) is False


def test_the_stand_down_shape_still_matches_its_producer(job):
    """Drift guard: the two literals this job matches on are the two the task emits.

    A source read, so it proves the strings are still written in the REFUSE
    branch — NOT that the branch runs. It exists because the coupling is a pair
    of bare string literals in another module with no shared constant, so a
    rename there would silently turn this ship back off.
    """
    from pathlib import Path

    import app.tasks.precompute_calibration as pc

    CHECKPOINT_DECLINED_STATUS = job.CHECKPOINT_DECLINED_STATUS
    CHECKPOINT_DECLINED_REASON = job.CHECKPOINT_DECLINED_REASON

    source = Path(pc.__file__).read_text()

    # Anchor to the FUNCTION first. The module has more than one
    # `if action == REFUSE:` — a bare split lands in `_deferred_rebuild_pass`,
    # whose stand-down is a different summary and would pass this guard for the
    # wrong reason. (It did, on the first draft of this test.)
    body = source.split("async def _precompute_calibration_main(", 1)
    assert len(body) == 2, "_precompute_calibration_main was renamed — re-derive"
    body = body[1].split("\ndef ", 1)[0].split("\nasync def ", 1)[0]

    assert body.count("if action == REFUSE:") == 1, (
        "expected exactly one REFUSE branch in this function; the guard can no "
        "longer tell which stand-down it is reading"
    )
    branch = body.split("if action == REFUSE:", 1)[1][:1200]
    assert f'"status": "{CHECKPOINT_DECLINED_STATUS}"' in branch
    assert f'"reason": "{CHECKPOINT_DECLINED_REASON}"' in branch


# ---------------------------------------------------------------------------
# 5. The missing-run alert — and that it is NOT keyed to the beat.
# ---------------------------------------------------------------------------

def test_the_rebuild_has_a_site_health_tile():
    """Disabling the beat must not also remove the thing that notices silence."""
    from app.routes.admin_cockpit import _AUTOPILOT_BEATS

    labels = [b["label"] for b in _AUTOPILOT_BEATS]
    assert "precompute_calibration_main" in labels


def test_the_tile_is_keyed_to_the_metric_label_not_the_beat_schedule():
    """Carrier-agnostic: it must read true whichever process produced the run.

    If this tile were keyed on the beat schedule it would go dark the moment
    `CALIBRATION_BEAT_DISABLED=1` lands — removing the monitor at the same
    instant it removes the runner.
    """
    from app.routes.admin_cockpit import _AUTOPILOT_BEATS
    from app.tasks import CALIBRATION_BEAT_ENTRY

    beat = next(b for b in _AUTOPILOT_BEATS if b["label"] == "precompute_calibration_main")
    # The metric label `_tracked_run` writes, NOT the beat-schedule key.
    assert beat["label"] != CALIBRATION_BEAT_ENTRY
    assert beat["expected_24h"] == 24
    assert beat["stale_hours"] == 2


def test_the_tile_goes_red_when_an_hourly_slot_is_missed():
    from datetime import datetime, timedelta, timezone

    from app.routes.admin_cockpit import _AUTOPILOT_BEATS, _autopilot_tile

    beat = next(b for b in _AUTOPILOT_BEATS if b["label"] == "precompute_calibration_main")
    stale = (datetime.now(timezone.utc) - timedelta(hours=5)).isoformat()

    tile = _autopilot_tile(beat, {"last_success_at": stale, "successes_24h": 3})
    assert tile["status"] == "red"


def test_the_tile_is_green_on_a_healthy_hour():
    from datetime import datetime, timedelta, timezone

    from app.routes.admin_cockpit import _AUTOPILOT_BEATS, _autopilot_tile

    beat = next(b for b in _AUTOPILOT_BEATS if b["label"] == "precompute_calibration_main")
    fresh = (datetime.now(timezone.utc) - timedelta(minutes=20)).isoformat()

    tile = _autopilot_tile(beat, {"last_success_at": fresh, "successes_24h": 24})
    assert tile["status"] == "green"


def test_the_tile_never_fired_reads_red():
    from app.routes.admin_cockpit import _AUTOPILOT_BEATS, _autopilot_tile

    beat = next(b for b in _AUTOPILOT_BEATS if b["label"] == "precompute_calibration_main")
    tile = _autopilot_tile(beat, {})
    assert tile["status"] == "red"
    assert tile["value"] == "never fired"


def test_a_tile_without_a_rescued_field_still_renders():
    """`rescued_field` became optional in #5001; the two older tiles keep theirs."""
    from datetime import datetime, timedelta, timezone

    from app.routes.admin_cockpit import _AUTOPILOT_BEATS, _autopilot_tile

    beat = next(b for b in _AUTOPILOT_BEATS if b["label"] == "precompute_calibration_main")
    assert "rescued_field" not in beat

    fresh = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
    tile = _autopilot_tile(beat, {"last_success_at": fresh, "successes_24h": 24})
    assert "rescued" not in tile["detail"]

    # The beats that DO declare one still show it.
    priced = next(b for b in _AUTOPILOT_BEATS if b["label"] == "calibration_prices")
    tile = _autopilot_tile(priced, {"last_success_at": fresh, "successes_24h": 4, "last_result_summary": {"rescued": 7}})
    assert "7 rescued" in tile["detail"]
