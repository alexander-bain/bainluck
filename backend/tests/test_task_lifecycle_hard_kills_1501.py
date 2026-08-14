"""#1501 item 2 — a compensating instrument that starts below the failure
boundary is not a compensating instrument.

``app/utils/sentry_filter.py`` DROPS the parent-side task deaths
(``WorkerLostError``, ``Terminated``, ``TimeLimitExceeded``) on the stated
premise that a Redis counter observes them instead:

    hard_kills_24h = starts_24h - (successes + failures + incompletes)

Codex C-CERT-SENTRY-R2 finding 2 established that the premise is false, and it
is false in the direction that hides deaths:

* ``record_task_started`` — the ``starts`` half — is called from inside
  ``_tracked_run``, which is a helper **the task body elects to enter**. A child
  killed before it gets there contributes no start, so it cannot appear in a
  difference computed FROM starts.
* **32 of the 119 beat-scheduled tasks never call ``_tracked_run`` at all**
  (computed below, not transcribed). For every one of them ``starts_24h`` is
  permanently 0, so ``hard_kills_24h`` is permanently 0 — whether the task is
  healthy or dying every single run.

For those tasks a hard kill and a healthy no-op delivery were the same
observation, in the counter AND in Sentry, because the event that would have
shown it was dropped on the strength of the counter. That is gotcha #53's shape
— an absence and a fact sharing one reading — relocated into the instrument.

The repair is a lifecycle pair written from celery's OWN ``task_prerun`` /
``task_postrun`` signals, which fire for every execution of every task with no
cooperation from any body. These tests hold the property that matters: **the
zero-start case is expressible and observable.** The predecessor's tests could
not express it — ``test_started_and_killed_reads_critical_not_no_data`` seeds 24
starts, and ``test_parent_side_task_death_is_dropped`` asserts the drop FROM the
premise the counter covers it, never constructing the case that falsifies it.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from app.tasks import redis_state
from app.tasks.redis_state import (
    TASK_LIFECYCLE_PREFIX,
    get_hard_kill_census,
    record_task_attempt,
    record_task_terminal,
)
from app.utils.sentry_filter import DROP_EXC_NAMES, VERDICT_DROP, classify

TASKS_INIT = Path(__file__).resolve().parents[1] / "app" / "tasks" / "__init__.py"


class _Redis:
    """Enough Redis for the lifecycle counters' write and read paths."""

    def __init__(self):
        self.strings = {}
        self.ttls = {}

    def pipeline(self):
        return self

    def execute(self):
        return []

    def set(self, key, value, ex=None, nx=False):
        if nx and key in self.strings:
            return None
        self.strings[key] = str(value).encode()
        if ex is not None:
            self.ttls[key] = ex
        return True

    def incr(self, key):
        self.strings[key] = str(int(self.strings.get(key, b"0")) + 1).encode()

    def expire(self, key, ttl):
        if key in self.strings:
            self.ttls[key] = ttl

    def get(self, key):
        return self.strings.get(key)

    def ttl(self, key):
        if key not in self.strings:
            return -2
        return self.ttls.get(key, -1)

    def keys(self, pattern):
        prefix = pattern.rstrip("*")
        return [k.encode() for k in self.strings if k.startswith(prefix)]


@pytest.fixture
def fake(monkeypatch):
    r = _Redis()
    monkeypatch.setattr(redis_state, "get_redis_client", lambda: r)
    return r


def _tasks_ast():
    source = TASKS_INIT.read_text()
    return ast.parse(source), source


def _scheduled_task_names(source: str) -> set[str]:
    return set(re.findall(r'"task":\s*"([^"]+)"', source))


def _functions_calling_tracked_run(tree) -> set[str]:
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if any(
                isinstance(c, ast.Call) and getattr(c.func, "id", None) == "_tracked_run"
                for c in ast.walk(node)
            ):
                out.add(node.name)
    return out


# ---------------------------------------------------------------------------
# THE ZERO-START CASE — the test the predecessor suite could not express
# ---------------------------------------------------------------------------

class TestTheZeroStartCase:
    """A task dies before ``_tracked_run``. Is the death observable anywhere?"""

    TASK = "app.tasks.collapse_snapshots"  # one of the 32; never calls the helper

    def test_a_death_before_the_helper_is_visible_in_the_lifecycle_gap(self, fake):
        """Prerun fires, the child is SIGKILLed, postrun never runs."""
        record_task_attempt(self.TASK)
        # ... SIGKILL here. No postrun, no except block, no handler at all.
        census = get_hard_kill_census()
        assert census[self.TASK]["attempts"] == 1
        assert census[self.TASK]["terminals"] == 0
        assert census[self.TASK]["hard_kills"] == 1, (
            "a pre-body death is invisible again — this is the whole finding"
        )

    def test_the_same_death_is_INVISIBLE_to_the_starts_based_counter(self):
        """The falsifying case, stated as a property of the code rather than a
        claim: ``starts`` can only be written from inside ``_tracked_run``, and
        this task never calls it — so no amount of dying moves that counter.
        """
        tree, source = _tasks_ast()
        callers = _functions_calling_tracked_run(tree)
        assert self.TASK.split(".")[-1] not in callers

        started_calls = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and getattr(node.func, "id", None) == "record_task_started"
        ]
        assert started_calls, "record_task_started is no longer called at all"
        tracked = next(
            n for n in ast.walk(tree)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            and n.name == "_tracked_run"
        )
        inside = {n.lineno for n in ast.walk(tracked) if isinstance(n, ast.Call)}
        assert all(c.lineno in inside for c in started_calls), (
            "record_task_started escaped _tracked_run — re-derive this finding"
        )

    def test_a_healthy_run_leaves_no_gap(self, fake):
        record_task_attempt(self.TASK)
        record_task_terminal(self.TASK)
        assert get_hard_kill_census()[self.TASK]["hard_kills"] == 0

    def test_a_HANDLED_failure_is_a_terminal_not_a_kill(self, fake):
        """``task_postrun`` fires after the body raises, so a task that fails
        loudly is not a hard kill. The gap must mean the one thing."""
        record_task_attempt(self.TASK)
        record_task_terminal(self.TASK)  # postrun runs even on exception
        assert get_hard_kill_census()[self.TASK]["hard_kills"] == 0

    def test_deaths_accumulate_rather_than_latching(self, fake):
        for _ in range(24):
            record_task_attempt(self.TASK)
        record_task_terminal(self.TASK)
        assert get_hard_kill_census()[self.TASK]["hard_kills"] == 23


# ---------------------------------------------------------------------------
# The 32 tasks, COMPUTED — the enumeration codex asked to see
# ---------------------------------------------------------------------------

class TestTheUntrackedTasksAreCoveredByConstruction:

    def test_the_untracked_set_is_real_and_is_computed_not_transcribed(self):
        tree, source = _tasks_ast()
        scheduled = _scheduled_task_names(source)
        callers = _functions_calling_tracked_run(tree)
        untracked = {n for n in scheduled if n.split(".")[-1] not in callers}
        # Pinned as a floor, not an equality: the count moves whenever a beat is
        # added, and an equality here would fail on unrelated work and get
        # "fixed" by editing the number — which is how a census becomes a
        # decoration. What must not silently become false is that the class
        # EXISTS and is large.
        assert len(untracked) >= 25, (
            f"only {len(untracked)} untracked scheduled tasks — if this class is "
            "genuinely gone, delete this suite deliberately rather than by drift"
        )
        assert "app.tasks.collapse_snapshots" in untracked

    def test_the_rail_does_not_depend_on_the_task_body_at_all(self):
        """Why the 32 need no per-task work: the recorders are wired to celery
        signals, so no body can opt out and task 120 cannot forget to join."""
        tree, source = _tasks_ast()
        assert "task_postrun" in source and "record_task_terminal" in source

        tracked = next(
            n for n in ast.walk(tree)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            and n.name == "_tracked_run"
        )
        inside = {n.lineno for n in ast.walk(tracked) if hasattr(n, "lineno")}
        for name in ("record_task_attempt", "record_task_terminal"):
            calls = [
                n for n in ast.walk(tree)
                if isinstance(n, ast.Call) and getattr(n.func, "id", None) == name
            ]
            assert calls, f"{name} is not called anywhere"
            assert not any(c.lineno in inside for c in calls), (
                f"{name} was moved inside _tracked_run — that restores the exact "
                "defect this rail exists to fix"
            )

    def test_the_attempt_is_recorded_BEFORE_the_retry_and_eager_filters(self):
        """The two counters must not share a predicate.

        ``deliveries`` grades a SCHEDULE, so a retry is not a fire. The
        lifecycle pair detects DEATH, and a retry that dies is a death. If the
        attempt were filtered like a delivery, a dying retry would leave a
        terminal with no attempt, the difference would go negative, and
        ``max(0, ...)`` would render it as perfect health.
        """
        tree, _ = _tasks_ast()
        receiver = next(
            n for n in ast.walk(tree)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            and n.name == "_record_delivery"
        )
        attempt_line = min(
            c.lineno for c in ast.walk(receiver)
            if isinstance(c, ast.Call)
            and getattr(c.func, "id", None) == "record_task_attempt"
        )
        returns = [r.lineno for r in ast.walk(receiver) if isinstance(r, ast.Return)]
        assert returns, "the retry/eager filters are gone — re-read LAT-P043"
        assert attempt_line < min(returns), (
            "record_task_attempt is behind an early return, so retries and eager "
            "runs record a terminal with no attempt"
        )


# ---------------------------------------------------------------------------
# Counter mechanics
# ---------------------------------------------------------------------------

class TestLifecycleCounterMechanics:

    def test_counts_by_full_celery_name_under_its_own_prefix(self, fake):
        record_task_attempt("app.tasks.poll_odds")
        assert f"{TASK_LIFECYCLE_PREFIX}:app.tasks.poll_odds:attempts" in fake.strings

    def test_names_containing_dots_survive_the_key_split(self, fake):
        record_task_attempt("app.tasks.deeply.nested.name")
        record_task_terminal("app.tasks.deeply.nested.name")
        census = get_hard_kill_census()
        assert "app.tasks.deeply.nested.name" in census
        assert census["app.tasks.deeply.nested.name"]["terminals"] == 1

    def test_empty_name_writes_nothing(self, fake):
        record_task_attempt("")
        record_task_terminal(None)
        assert fake.strings == {}

    def test_never_raises_when_redis_is_down(self, monkeypatch):
        def boom():
            raise ConnectionError("redis is exactly the thing that is down")

        monkeypatch.setattr(redis_state, "get_redis_client", boom)
        record_task_attempt("app.tasks.poll_odds")   # must not raise
        record_task_terminal("app.tasks.poll_odds")  # must not raise
        assert get_hard_kill_census() == {}

    def test_the_window_is_stamped_once_and_never_slides(self, fake):
        record_task_attempt("app.tasks.poll_odds")
        fake.ttls[f"{TASK_LIFECYCLE_PREFIX}:app.tasks.poll_odds:attempts"] = 1_000
        record_task_attempt("app.tasks.poll_odds")
        assert fake.ttls[f"{TASK_LIFECYCLE_PREFIX}:app.tasks.poll_odds:attempts"] == 1_000

    def test_a_negative_difference_floors_at_zero(self, fake):
        """Counters expire independently, so terminals can outrun attempts
        across a boundary. That is an artifact, not a negative death count."""
        record_task_terminal("app.tasks.poll_odds")
        record_task_terminal("app.tasks.poll_odds")
        assert get_hard_kill_census()["app.tasks.poll_odds"]["hard_kills"] == 0

    def test_a_count_is_never_handed_over_without_its_window(self, fake):
        record_task_attempt("app.tasks.poll_odds")
        assert "window_s" in get_hard_kill_census()["app.tasks.poll_odds"]


# ---------------------------------------------------------------------------
# The Sentry side of the contract
# ---------------------------------------------------------------------------

class TestTheDropIsNowJustified:

    @pytest.mark.parametrize("name", ["WorkerLostError", "Terminated", "TimeLimitExceeded"])
    def test_parent_side_task_death_is_still_dropped(self, name):
        event = {"exception": {"values": [{"type": name, "module": "billiard.pool",
                                           "value": "worker exited"}]},
                 "culprit": "billiard.pool in mark_as_worker_lost"}
        assert classify(event, None) == VERDICT_DROP
        assert name in DROP_EXC_NAMES

    def test_and_the_drop_now_names_a_rail_that_sees_the_pre_body_case(self):
        """The drop is only defensible while the compensating rail observes the
        failure from ABOVE the boundary. Assert the justification cites the
        lifecycle pair rather than the starts-based counter it outgrew — a
        stale rationale is how the first version survived certification twice.
        """
        source = Path(__file__).resolve().parents[1].joinpath(
            "app", "utils", "sentry_filter.py"
        ).read_text()
        drop_doc = source.split("DROP_EXC_NAMES")[0]
        assert "record_task_attempt" in drop_doc and "record_task_terminal" in drop_doc
        assert "task_prerun" in drop_doc or "task_postrun" in drop_doc
