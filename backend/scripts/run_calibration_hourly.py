"""Run the hourly calibration rebuild in THIS process (#5001, THRU-B).

WHY THIS EXISTS

`precompute_calibration_main` is the hourly :15 beat that rebuilds and publishes
the /calibration page. Its p95 is 1352.8 s against a 3600 s period, so it is in
flight for roughly a third of every hour — and **every master merge cycles
`worker-heavy`**, which SIGTERMs whatever that worker is running. D45 records the
cause on the ledger: a release lands, the beat dies mid-build, and the next
scheduled slot starts over. Runs 2580 and 4937 both died that way (standing
notice 2); 4937 was killed at ~110/128 phases.

Heroku **one-off dynos are not cycled by an app release**. So the same build, run
from a one-off started by Heroku Scheduler, survives the deploy that would have
killed the beat. That is the whole ship: the reader stops seeing a calibration
page whose last good publish is hours old because the rebuild kept being
interrupted.

WHAT THIS IS NOT

It does **not** re-enqueue anything. `precompute_calibration_main.delay()` from a
one-off would hand the work straight back to `worker-heavy` — the process a
release kills — and buy nothing at all. This calls the async entry point
directly and runs it here, in the one-off's own process.

It also does not reimplement the build, the publish validation, or the metrics.
It calls `_tracked_run`, the same boundary the beat calls, with the same metric
label. So `precompute_calibration_main` is still enrolled in
`task_verdict.ENFORCED_TASKS` (its terminal is read from `phase_ledger.terminal`
+ `.health`), `/api/admin/celery/task-metrics/precompute_calibration_main` keeps
reading true, and the site-health tile added with this change cannot tell — and
must not care — whether the beat or this job produced the run.

THE FOUR PROPERTIES, AND WHERE EACH COMES FROM

* **One copy at a time.** `app.utils.single_flight` — the same Redis NX lease
  `poll_all_odds` and `sync_espn_live_events` take, keyed on the same task name.
  A second invocation logs one line and **exits 0**: a Scheduler that fires while
  the previous hour is still building is not an error, and a non-zero exit there
  would page somebody for correct behaviour.

  ⚠️ The lease TTL is passed EXPLICITLY and is not the module default. That
  default is 330 s, derived from Celery's 300 s global hard kill — a bound this
  task overrides (`soft_time_limit=1500`). Taking the default would expire the
  lease ~19 minutes into a ~23-minute build and let a second copy in, which is
  the precise failure the lease exists to prevent.

* **An explicit runtime bound.** Outside a Celery worker there is no
  `soft_time_limit`, so the coroutine is wrapped in `asyncio.wait_for`. Honest
  limit: that bounds the build at its **await points**. It cannot interrupt a
  blocking C-level call (gotcha #38 — `json.loads` holds the GIL for the whole
  parse). A build wedged inside one is bounded by the dyno, not by this; the
  lease TTL is sized so that case still cannot admit a second copy.

* **A missing run is visible.** Adding this job removes the beat, and removing a
  beat silently removes whatever noticed it was not firing. So this ship also
  puts `precompute_calibration_main` on the `_AUTOPILOT_BEATS` tiles in
  `app/routes/admin_cockpit.py` — RED at >2 h since the last success. That tile
  reads the metric label, NOT the beat schedule, which is exactly why it keeps
  working across the cutover in both directions.

* **Rollback is one config var.** `CALIBRATION_BEAT_DISABLED=1` removes the beat
  entry; unset it and the beat comes back on the next dyno restart. Nothing here
  needs to be un-deployed to roll back.

EXIT CODES

    0  the build ran and reported a publishable terminal, OR a previous copy
       still holds the lease (a declined slot is not a failure)
    1  the build raised, or returned a terminal that is not publishable

Heroku Scheduler does not retry, so the exit code is a signal for the log and
for anybody reading `heroku ps`; the tile above is the thing that actually
alerts.

RUN IT

    python3 scripts/run_calibration_hourly.py
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logger = logging.getLogger("calibration_hourly")

#: The Celery task name — the lease key, so the beat and this job can never both
#: hold it. Not a display string.
TASK_NAME = "app.tasks.precompute_calibration_main"

#: The metric label `_tracked_run` writes under. Deliberately identical to the
#: beat's, so task-metrics and the site-health tile are continuous across the
#: cutover rather than starting a fresh, empty series.
METRIC_LABEL = "precompute_calibration_main"

#: Mirrors `soft_time_limit=1500` on the beat (`app/tasks/__init__.py`). Same
#: bound, restated here because a one-off has no Celery to enforce it.
DEFAULT_RUNTIME_BOUND_SECONDS = 1500

#: Headroom between the runtime bound and the lease TTL. The bound fires first
#: and unwinds the `with`, releasing the lease; this margin only matters when the
#: process is hard-killed and the lease has to expire on its own.
LEASE_TTL_MARGIN_SECONDS = 120

#: Env var for the runtime bound, so Alex can widen it without a deploy.
RUNTIME_BOUND_ENV = "CALIBRATION_HOURLY_TIMEOUT_S"

EXIT_OK = 0
EXIT_FAILED = 1


def runtime_bound_seconds(env: dict | None = None) -> int:
    """The build's wall-clock bound, in seconds.

    Pure over ``env`` so it tests without a process. An unset, empty,
    non-numeric or non-positive value falls back to the default rather than
    raising: a typo in a config var must not be able to stop the rebuild from
    running at all, which would be a strictly worse outcome than running it with
    the bound it has always had.
    """
    raw = (env if env is not None else os.environ).get(RUNTIME_BOUND_ENV)
    if raw is None:
        return DEFAULT_RUNTIME_BOUND_SECONDS
    try:
        value = int(str(raw).strip())
    except (TypeError, ValueError):
        logger.warning(
            "%s=%r is not an integer; using the default bound %ds",
            RUNTIME_BOUND_ENV, raw, DEFAULT_RUNTIME_BOUND_SECONDS,
        )
        return DEFAULT_RUNTIME_BOUND_SECONDS
    if value <= 0:
        logger.warning(
            "%s=%r is not positive; using the default bound %ds",
            RUNTIME_BOUND_ENV, raw, DEFAULT_RUNTIME_BOUND_SECONDS,
        )
        return DEFAULT_RUNTIME_BOUND_SECONDS
    return value


def lease_ttl_seconds(bound_seconds: int) -> int:
    """Lease TTL for a build bounded at ``bound_seconds``.

    Strictly greater than the bound, always — a TTL that can expire while the
    holder is still legitimately building is the #1678 shape: it admits a second
    concurrent copy of the exact task the lease is protecting.
    """
    return bound_seconds + LEASE_TTL_MARGIN_SECONDS


def exit_code_for(summary) -> int:
    """Map the build's own summary to this process's exit code.

    Reads the SAME contract the health counters read (`app.utils.task_verdict`),
    so the exit code and the task metrics can never disagree about whether the
    hour's build worked — the divergence that let three calibration tasks report
    ``health: healthy`` while producing nothing (queue 300H, #1515).

    A declined slot never reaches here; `main` returns before the build.
    """
    from app.utils.task_verdict import COMPLETE, verdict_for

    verdict = verdict_for(METRIC_LABEL, summary)
    return EXIT_OK if verdict.verdict == COMPLETE else EXIT_FAILED


def _run_build(bound_seconds: int):
    """Run the rebuild here, through the beat's own tracking boundary."""
    from app.tasks import _tracked_run
    from app.tasks.precompute_calibration import _precompute_calibration_main

    # `_tracked_run` calls `asyncio.run` on whatever it is handed, so the bound
    # is applied by wrapping the coroutine rather than by racing a timer.
    return _tracked_run(
        METRIC_LABEL,
        asyncio.wait_for(_precompute_calibration_main(), timeout=bound_seconds),
    )


def main(argv=None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    from app.utils.single_flight import single_flight

    bound = runtime_bound_seconds()
    ttl = lease_ttl_seconds(bound)
    started = time.monotonic()

    logger.info(
        "calibration hourly job starting — bound %ds, lease ttl %ds, task %s",
        bound, ttl, TASK_NAME,
    )

    with single_flight(TASK_NAME, ttl_seconds=ttl) as lease:
        if not lease.acquired:
            # The previous hour is still building. Correct, expected, and not a
            # failure — say so on one line and leave with a clean exit.
            logger.info(
                "calibration hourly job DECLINED this slot — a previous run still "
                "holds %s (%s). Exiting 0; the run in flight will publish.",
                lease.key, lease.reason,
            )
            return EXIT_OK

        try:
            summary = _run_build(bound)
        except asyncio.TimeoutError:
            logger.error(
                "calibration hourly job exceeded its %ds bound and was cancelled; "
                "no publish this hour", bound,
            )
            return EXIT_FAILED
        except BaseException:  # noqa: BLE001 — log, then report a failure exit
            logger.exception("calibration hourly job raised")
            return EXIT_FAILED

    elapsed = time.monotonic() - started
    code = exit_code_for(summary)
    logger.info(
        "calibration hourly job finished in %.1fs — exit %d, summary %.400s",
        elapsed, code, summary,
    )
    return code


if __name__ == "__main__":
    sys.exit(main())
