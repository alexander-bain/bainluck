"""Queue 300R Item 1 — targeted Celery result retention.

Two failure modes are being defended against, and they pull in opposite
directions:

* **Too little suppression** — every beat writes a 24h ``celery-task-meta-*``
  key into a 50MB ``allkeys-lru`` Redis, and the eviction that follows takes
  out whatever was least recently used. That is the Queue 298 failure repeated.
* **Too much suppression** — an admin endpoint hands a caller a ``task_id``,
  the caller polls ``AsyncResult``, and it never resolves because the result
  was never stored. This one is silent and much worse.

So the pure rule (``beat_only_tasks``) is fixture-tested in both directions,
and the declared consumer set is re-derived from the real code by AST walk so
it cannot drift out of agreement with what the routes actually dispatch.
"""

from __future__ import annotations

import ast
import os
import re

import pytest

from app.tasks.result_retention import (
    RESULT_CONSUMER_TASKS,
    RESULT_EXPIRES_S,
    apply_result_suppression,
    beat_only_tasks,
)

APP_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app")

#: Celery's built-in default, which is exactly what this queue removes.
CELERY_DEFAULT_RESULT_EXPIRES_S = 86400


# ---------------------------------------------------------------------------
# Fixtures — a miniature schedule with one of every shape that matters
# ---------------------------------------------------------------------------

CONSUMERS = frozenset(
    {
        "app.tasks.admin_polled",          # beat AND admin-triggered
        "app.tasks.admin_only",            # admin-triggered, never scheduled
    }
)

SCHEDULE = {
    "fire-and-forget": {"task": "app.tasks.beat_only", "schedule": 60},
    "polled-beat": {"task": "app.tasks.admin_polled", "schedule": 300},
    "another-fire-and-forget": {"task": "app.tasks.beat_only_two", "schedule": 600},
}


class _FakeTask:
    def __init__(self, name: str) -> None:
        self.name = name
        self.ignore_result = False


class _FakeConf:
    def __init__(self, schedule) -> None:
        self.beat_schedule = schedule


class _FakeApp:
    def __init__(self, schedule, task_names) -> None:
        self.conf = _FakeConf(schedule)
        self.tasks = {n: _FakeTask(n) for n in task_names}


# ---------------------------------------------------------------------------
# The pure rule
# ---------------------------------------------------------------------------


def test_scheduled_task_with_no_consumer_is_suppressed():
    assert "app.tasks.beat_only" in beat_only_tasks(SCHEDULE, CONSUMERS)
    assert "app.tasks.beat_only_two" in beat_only_tasks(SCHEDULE, CONSUMERS)


def test_admin_polled_beat_keeps_its_result():
    """The whole point of "targeted": a beat that is ALSO admin-triggered has a
    consumer, so suppressing it would hang a status poll forever."""
    assert "app.tasks.admin_polled" not in beat_only_tasks(SCHEDULE, CONSUMERS)


def test_admin_only_task_is_never_in_the_set():
    """Not scheduled at all — it can only be reached by an admin trigger, so it
    must never appear even by accident."""
    assert "app.tasks.admin_only" not in beat_only_tasks(SCHEDULE, CONSUMERS)


def test_result_is_sorted_and_deduplicated():
    schedule = dict(SCHEDULE)
    schedule["duplicate-entry"] = {"task": "app.tasks.beat_only", "schedule": 60}
    out = beat_only_tasks(schedule, CONSUMERS)
    assert out == tuple(sorted(set(out)))
    assert out.count("app.tasks.beat_only") == 1


@pytest.mark.parametrize("schedule", [None, {}, ])
def test_missing_schedule_falls_back_to_empty(schedule):
    """Configuration fallback. Returning () keeps a redundant result; returning
    a name we could not justify would break a poll. Fail toward the harmless
    direction."""
    assert beat_only_tasks(schedule, CONSUMERS) == ()


def test_malformed_entries_are_skipped_not_fatal():
    schedule = {
        "not-a-mapping": ["app.tasks.beat_only"],
        "no-task-key": {"schedule": 60},
        "non-string-task": {"task": 42, "schedule": 60},
        "empty-task": {"task": "", "schedule": 60},
        "good": {"task": "app.tasks.beat_only", "schedule": 60},
    }
    assert beat_only_tasks(schedule, CONSUMERS) == ("app.tasks.beat_only",)


# ---------------------------------------------------------------------------
# Applying it to an app
# ---------------------------------------------------------------------------


def test_apply_sets_ignore_result_only_on_beat_only_tasks():
    app = _FakeApp(
        SCHEDULE,
        ["app.tasks.beat_only", "app.tasks.beat_only_two", "app.tasks.admin_polled"],
    )
    suppressed = apply_result_suppression(app, CONSUMERS)

    assert set(suppressed) == {"app.tasks.beat_only", "app.tasks.beat_only_two"}
    assert app.tasks["app.tasks.beat_only"].ignore_result is True
    assert app.tasks["app.tasks.admin_polled"].ignore_result is False


def test_unregistered_scheduled_task_is_skipped_not_raised():
    """A beat name with no registered task (import-order surprise) must not
    take the worker down over a cache optimisation."""
    app = _FakeApp(SCHEDULE, ["app.tasks.beat_only"])  # beat_only_two absent
    assert apply_result_suppression(app, CONSUMERS) == ("app.tasks.beat_only",)


def test_apply_is_idempotent_under_duplicate_delivery():
    """Two workers booting, or a reload, re-applies the same decision. Setting
    ignore_result twice must be a no-op, not an accumulation."""
    app = _FakeApp(SCHEDULE, ["app.tasks.beat_only", "app.tasks.admin_polled"])
    first = apply_result_suppression(app, CONSUMERS)
    second = apply_result_suppression(app, CONSUMERS)
    assert first == second
    assert app.tasks["app.tasks.admin_polled"].ignore_result is False


def test_consumer_set_is_resolved_at_call_time(monkeypatch):
    """Late binding: the module constant is the single source of truth, so an
    override reaches the pure rule instead of being frozen into a default."""
    monkeypatch.setattr(
        "app.tasks.result_retention.RESULT_CONSUMER_TASKS",
        frozenset({"app.tasks.beat_only"}),
    )
    out = beat_only_tasks(SCHEDULE)
    assert "app.tasks.beat_only" not in out
    assert "app.tasks.admin_polled" in out


def test_broken_conf_returns_empty_instead_of_raising():
    class _Broken:
        @property
        def conf(self):
            raise RuntimeError("no conf here")

    assert apply_result_suppression(_Broken()) == ()


# ---------------------------------------------------------------------------
# The real app
# ---------------------------------------------------------------------------


def test_result_expires_is_bounded_and_shorter_than_celery_default():
    from app.tasks import celery_app

    assert celery_app.conf.result_expires == RESULT_EXPIRES_S
    assert 0 < RESULT_EXPIRES_S < CELERY_DEFAULT_RESULT_EXPIRES_S


def test_real_app_suppresses_beats_and_preserves_consumers():
    from app.tasks import celery_app

    suppressed = set(beat_only_tasks(celery_app.conf.beat_schedule))
    assert suppressed, "expected at least some fire-and-forget beats"

    # Nothing an HTTP route can hand out a task_id for may be suppressed.
    assert suppressed.isdisjoint(RESULT_CONSUMER_TASKS)

    for name in suppressed:
        task = celery_app.tasks.get(name)
        if task is not None:
            assert task.ignore_result is True, f"{name} should be suppressed"

    for name in RESULT_CONSUMER_TASKS:
        task = celery_app.tasks.get(name)
        if task is not None:
            assert task.ignore_result is False, f"{name} is polled — keep its result"


def test_admin_polled_calibration_tasks_keep_results():
    """Named explicitly because both are ALSO scheduled beats, which is exactly
    the case a blanket task_ignore_result would have broken."""
    from app.tasks import celery_app

    for name in (
        "app.tasks.compute_calibration_prices",
        "app.tasks.snapshot_coverage_metrics",
        "app.tasks.backfill_winners",
        "app.tasks.match_prediction_markets",
    ):
        assert celery_app.tasks[name].ignore_result is False


def test_retry_configuration_survives_suppression():
    """`self.retry()` goes through the broker, not the result backend, so a
    suppressed task must keep retrying. Assert the retry contract is untouched
    on a task that IS suppressed."""
    from app.tasks import celery_app

    task = celery_app.tasks["app.tasks.poll_all_odds"]
    assert task.ignore_result is True
    assert task.max_retries == 3


def test_failure_observability_does_not_depend_on_the_result_backend(monkeypatch):
    """`_tracked_run` writes bainluck:task_metrics:* directly. That is what the
    cockpit, /api/admin/celery/task-metrics and the watchdogs read — so a
    suppressed task still reports success AND failure."""
    import app.tasks.redis_state as redis_state
    from app.tasks import _tracked_run

    recorded: dict[str, tuple] = {}
    monkeypatch.setattr(
        redis_state, "record_task_success",
        lambda n, d, s, **kw: recorded.__setitem__("success", (n, s)),
    )
    monkeypatch.setattr(
        redis_state, "record_task_failure",
        lambda n, d, e, **kw: recorded.__setitem__("failure", (n, e)),
    )
    monkeypatch.setattr(redis_state, "touch_worker_liveness", lambda: None)

    async def _ok():
        return {"rows": 1}

    assert _tracked_run("suppressed_beat", _ok()) == {"rows": 1}
    assert recorded["success"] == ("suppressed_beat", {"rows": 1})

    async def _boom():
        raise ValueError("kaboom")

    with pytest.raises(ValueError):
        _tracked_run("suppressed_beat", _boom())
    assert recorded["failure"][0] == "suppressed_beat"


# ---------------------------------------------------------------------------
# Drift guards — the reason this change is safe to leave unattended
# ---------------------------------------------------------------------------


def _dispatched_task_names() -> set[str]:
    """Re-derive the true consumer set by walking every dispatch site."""
    from app.tasks import celery_app

    dispatch_attrs = {"delay", "apply_async"}
    send_names = {"send_task", "safe_send_task", "_safe_send_task"}
    found: set[str] = set()

    for root in ("routes", "services", "utils"):
        for dirpath, _, files in os.walk(os.path.join(APP_DIR, root)):
            for fname in sorted(files):
                if not fname.endswith(".py"):
                    continue
                path = os.path.join(dirpath, fname)
                with open(path, errors="ignore") as fh:
                    try:
                        tree = ast.parse(fh.read())
                    except SyntaxError:  # pragma: no cover
                        continue

                imported = {}
                for node in ast.walk(tree):
                    if isinstance(node, ast.ImportFrom) and node.module:
                        for alias in node.names:
                            imported[alias.asname or alias.name] = alias.name

                for node in ast.walk(tree):
                    if not isinstance(node, ast.Call):
                        continue
                    func = node.func
                    if (
                        isinstance(func, ast.Attribute)
                        and func.attr in dispatch_attrs
                        and isinstance(func.value, ast.Name)
                    ):
                        origin = imported.get(func.value.id)
                        if origin:
                            for tname, task in celery_app.tasks.items():
                                run = getattr(task, "run", None)
                                if run is not None and getattr(run, "__name__", None) == origin:
                                    found.add(tname)
                                    break
                    called = (
                        func.attr if isinstance(func, ast.Attribute)
                        else func.id if isinstance(func, ast.Name)
                        else None
                    )
                    if called in send_names and node.args:
                        first = node.args[0]
                        if isinstance(first, ast.Constant) and isinstance(first.value, str):
                            found.add(first.value)
    return found


def test_result_consumer_set_matches_code():
    """If someone adds an admin trigger for a currently-suppressed beat, its
    status poll would silently never resolve. Fail here instead."""
    derived = _dispatched_task_names()
    # `_enqueue_bug_fixed_email` passes the name via a module constant, so the
    # literal scan cannot see it; it is declared and asserted separately.
    assert "app.tasks.send_bug_fixed_email" in RESULT_CONSUMER_TASKS
    derived.add("app.tasks.send_bug_fixed_email")

    missing = derived - RESULT_CONSUMER_TASKS
    assert not missing, (
        "these tasks are dispatched from an HTTP route but are not declared as "
        f"result consumers — their status polls would hang: {sorted(missing)}"
    )


def test_no_celery_canvas_primitives_exist():
    """A chord body reading a suppressed header result is how this change
    breaks a codebase. That shape does not exist here; keep it that way."""
    pattern = re.compile(
        r"from\s+celery(?:\.canvas)?\s+import\s+[^\n]*\b(chord|group|chain|signature)\b"
        r"|celery\.(?:canvas\.)?(?:chord|group|chain)\s*\("
    )
    offenders = []
    for dirpath, _, files in os.walk(APP_DIR):
        for fname in files:
            if not fname.endswith(".py"):
                continue
            path = os.path.join(dirpath, fname)
            with open(path, errors="ignore") as fh:
                for lineno, line in enumerate(fh, 1):
                    if pattern.search(line):
                        offenders.append(f"{path}:{lineno}")
    assert not offenders, (
        "Celery canvas primitives found — revisit result suppression before "
        f"using them: {offenders}"
    )


# ---------------------------------------------------------------------------
# Item 2 — the census has to be able to SEE the change it is measuring
# ---------------------------------------------------------------------------


class _FakeRedis:
    """Enough of a Redis to exercise the census without one running."""

    def __init__(self, keys, ttls):
        self._keys = list(keys)
        self._ttls = ttls

    def info(self, section):
        return {
            "memory": {
                "used_memory": 40 * 1024 * 1024,
                "used_memory_human": "40.00M",
                "used_memory_peak_human": "55.22M",
                "maxmemory": 50 * 1024 * 1024,
                "maxmemory_human": "50.00M",
                "maxmemory_policy": "allkeys-lru",
                "mem_fragmentation_ratio": 1.1,
            },
            "stats": {
                "evicted_keys": 239216,
                "expired_keys": 11,
                "keyspace_hits": 5,
                "keyspace_misses": 1,
                "rejected_connections": 248487,
            },
            "clients": {"connected_clients": 26, "blocked_clients": 2},
        }[section]

    def dbsize(self):
        return len(self._keys)

    def scan(self, cursor=0, count=500):
        return 0, [k.encode() for k in self._keys]

    def memory_usage(self, key, samples=0):
        return 700

    def ttl(self, key):
        return self._ttls.get(key, -1)


async def _run_census(monkeypatch, keys, ttls):
    import app.routes.admin_celery as mod
    import app.tasks.redis_state as redis_state

    monkeypatch.setattr(mod, "_check_admin_secret", lambda *a, **k: None)
    monkeypatch.setattr(redis_state, "get_redis_client", lambda *a, **k: _FakeRedis(keys, ttls))
    return await mod.redis_census(request=None, secret="x", scan_limit=1000, sample_per_class=12)


@pytest.mark.asyncio
async def test_census_reports_every_signal_item2_requires(monkeypatch):
    out = await _run_census(monkeypatch, ["celery-task-meta-abc"], {"celery-task-meta-abc": 1200})

    assert out["eviction"]["evicted_keys"] == 239216
    assert out["clients"]["rejected_connections"] == 248487
    assert out["clients"]["connected_clients"] == 26
    assert out["clients"]["blocked_clients"] == 2
    assert out["memory"]["maxmemory"] == 50 * 1024 * 1024
    assert out["memory"]["pct_of_maxmemory"] == 80.0


@pytest.mark.asyncio
async def test_census_exposes_the_retention_configuration(monkeypatch):
    """A TTL is uninterpretable without the expiry it was set from."""
    out = await _run_census(monkeypatch, ["celery-task-meta-abc"], {"celery-task-meta-abc": 1200})

    cr = out["celery_results"]
    assert cr["result_expires_s"] == RESULT_EXPIRES_S
    assert cr["suppressed_beat_tasks"] > 0
    assert cr["result_consumer_tasks"] == len(RESULT_CONSUMER_TASKS)


@pytest.mark.asyncio
async def test_census_derives_celery_result_key_age(monkeypatch):
    keys = ["celery-task-meta-a", "celery-task-meta-b"]
    out = await _run_census(monkeypatch, keys, {keys[0]: 3400, keys[1]: 1200})

    row = next(c for c in out["classes"] if c["class"] == "celery-task-meta-*")
    assert row["keys"] == 2
    # Oldest key is the one with the least TTL left.
    assert row["max_sampled_age_s"] == RESULT_EXPIRES_S - 1200
    assert row["min_sampled_age_s"] == RESULT_EXPIRES_S - 3400
    assert row["sampled_ttl_over_configured_expiry"] == 0


@pytest.mark.asyncio
async def test_census_counts_legacy_ttls_instead_of_reporting_negative_age(monkeypatch):
    """A key with 47,348s left cannot have been written under a 3,600s expiry —
    it is residue from the old 24h default. Subtracting gives a nonsense
    negative age, so count it instead. This is also the read that shows the old
    residue draining."""
    keys = ["celery-task-meta-legacy", "celery-task-meta-fresh"]
    out = await _run_census(
        monkeypatch, keys, {keys[0]: 47348, keys[1]: 900}
    )

    row = next(c for c in out["classes"] if c["class"] == "celery-task-meta-*")
    assert row["sampled_ttl_over_configured_expiry"] == 1
    assert row["configured_expiry_s"] == RESULT_EXPIRES_S
    # Only the in-config key contributes an age, and it is never negative.
    assert row["max_sampled_age_s"] == RESULT_EXPIRES_S - 900
    assert row["min_sampled_age_s"] == RESULT_EXPIRES_S - 900


@pytest.mark.asyncio
async def test_census_omits_age_when_every_sample_is_legacy(monkeypatch):
    keys = ["celery-task-meta-legacy"]
    out = await _run_census(monkeypatch, keys, {keys[0]: 82441})

    row = next(c for c in out["classes"] if c["class"] == "celery-task-meta-*")
    assert row["sampled_ttl_over_configured_expiry"] == 1
    assert "max_sampled_age_s" not in row
    assert "min_sampled_age_s" not in row


@pytest.mark.asyncio
async def test_census_age_is_omitted_for_classes_we_do_not_configure(monkeypatch):
    out = await _run_census(monkeypatch, ["bainluck:category:politics"], {"bainluck:category:politics": 600})

    row = next(c for c in out["classes"] if c["class"] == "bainluck:category")
    assert "max_sampled_age_s" not in row


def test_no_task_dispatches_another_task():
    """Same reasoning as the canvas guard: an intra-task dispatch could grow a
    result consumer the route scan would never see."""
    pattern = re.compile(r"\.(?:delay|apply_async)\s*\(|\bsend_task\s*\(")
    offenders = []
    tasks_dir = os.path.join(APP_DIR, "tasks")
    for dirpath, _, files in os.walk(tasks_dir):
        for fname in files:
            if not fname.endswith(".py"):
                continue
            path = os.path.join(dirpath, fname)
            with open(path, errors="ignore") as fh:
                for lineno, line in enumerate(fh, 1):
                    stripped = line.strip()
                    if stripped.startswith("#"):
                        continue
                    if pattern.search(line):
                        offenders.append(f"{path}:{lineno} {stripped[:80]}")
    assert not offenders, f"intra-task dispatch found: {offenders}"
