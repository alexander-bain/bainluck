"""The two `turbo_collapse_*` tasks must stay instrumented (LAT-P068, #1609).

These are the largest structural exposure on the 2-slot `background` pool:
`soft_time_limit=3600` lets either hold half the pool for an hour, they fire
:30 and :45 of the same hours so a long pair can hold BOTH slots at once, and
until LAT-P068 neither wrote a single counter.

That combination is why they were invisible. `task-metrics` returned NO DATA for
both, so every occupancy read this program took — every one — omitted the task
that S4 then measured at **31.8 % of all background slot-time**, ahead of
`warm_typeahead`.

The regression these tests exist to stop is silent and easy: someone reverts a
`_tracked_run` wrapper while "simplifying", the task keeps working perfectly,
and the next occupancy audit is quietly wrong again in the same direction.
"""

from __future__ import annotations

import inspect

import pytest

import app.tasks as tasks_mod

TURBO_TASKS = ("turbo_collapse_futures", "turbo_collapse_odds")


@pytest.mark.parametrize("name", TURBO_TASKS)
def test_turbo_task_exists(name):
    assert hasattr(tasks_mod, name), f"{name} disappeared from app.tasks"


@pytest.mark.parametrize("name", TURBO_TASKS)
def test_turbo_task_records_its_run(name):
    """The body must go through `_tracked_run`, not a bare `run_async`.

    A bare `run_async` executes the work correctly and records nothing, which is
    exactly the failure mode: the task is healthy and unmeasurable at the same
    time.
    """
    src = inspect.getsource(getattr(tasks_mod, name).__wrapped__)
    assert "_tracked_run(" in src, (
        f"{name} no longer calls _tracked_run. It will execute fine and report "
        f"NOTHING: task-metrics returns NO DATA, durations are unknowable, and "
        f"hard_kills cannot see it. That is how it stayed invisible while "
        f"holding 31.8% of the background pool (LAT-P068)."
    )
    assert "return run_async(" not in src, (
        f"{name} reverted to a bare run_async — the untracked form."
    )


@pytest.mark.parametrize("name", TURBO_TASKS)
def test_turbo_task_is_tracked_under_its_own_task_name(name):
    """The metric label must equal the task name, or the read is unjoinable.

    #1800 is an open p1 about `task-metrics` and the beat schedule speaking two
    different identifier spaces (59 of 101 tasks unqueryable). Anyone reading
    these will curl `?task=turbo_collapse_futures`; if the label differs, they
    get NO DATA and reasonably conclude the task never ran.
    """
    src = inspect.getsource(getattr(tasks_mod, name).__wrapped__)
    assert f'_tracked_run(\n        "{name}"' in src or f'_tracked_run("{name}"' in src, (
        f"{name}'s _tracked_run label must be the bare task name so "
        f"/api/admin/task-metrics?task={name} resolves."
    )


@pytest.mark.parametrize("name", TURBO_TASKS)
def test_turbo_task_still_has_a_soft_time_limit(name):
    """A task without a soft limit vanishes into `no_data` on a hard kill.

    The global `task_time_limit=300` is HARD; these override it to 3600/3660.
    The pairing is what makes a long run *observable* rather than a
    disappearance (`project_celery_sigkill_untracked`).
    """
    task = getattr(tasks_mod, name)
    soft = task.soft_time_limit
    hard = task.time_limit
    assert soft is not None, f"{name} lost its soft_time_limit"
    assert hard is not None, f"{name} lost its time_limit"
    assert soft < hard, (
        f"{name}: soft_time_limit ({soft}) must be strictly below time_limit "
        f"({hard}) or the soft signal never fires and the task is SIGKILLed "
        f"with no terminal record."
    )


@pytest.mark.parametrize("name", TURBO_TASKS)
def test_the_hour_long_budget_is_stated_not_inherited(name):
    """Pin 3600 so a change to it is a DECISION someone made, not a drift.

    This is not an endorsement of 3600 — LAT-P068 flags it as the largest
    structural exposure on a 2-slot pool and registers a prediction about
    bounding it. It is pinned so that lowering it shows up as a deliberate edit
    with this test's failure attached, carrying the reason.
    """
    task = getattr(tasks_mod, name)
    assert task.soft_time_limit == 3600, (
        f"{name}'s soft_time_limit changed from 3600 to {task.soft_time_limit}. "
        f"If that is intentional, update this test and record the measurement "
        f"that justified it (LAT-P068 registered the prediction; it needs a "
        f"post-instrumentation p50 first)."
    )


def test_both_turbo_tasks_remain_on_background():
    """They must NOT be 'fixed' by moving them to heavy.

    Moving an hour-budgeted grinder onto the 2-slot heavy lane would fill both
    of its slots and re-starve the hourly calibration warmer — observed live
    during the #224 rollout, and heavy has LESS headroom now than it did then
    (#1609 moved `match_prediction_markets`, 337.4s p50 / 699.4s p95 every
    15 min, onto it).
    """
    heavy = tasks_mod.HEAVY_TASKS
    for name in TURBO_TASKS:
        assert f"app.tasks.{name}" not in heavy, (
            f"{name} was routed to `heavy`. An hour-budgeted grinder on a 2-slot "
            f"lane shared with precompute_calibration_main (p90 1,149s) is the "
            f"#224 failure, not a fix for it."
        )
