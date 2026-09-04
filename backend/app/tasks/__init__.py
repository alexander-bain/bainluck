"""
Celery tasks for background odds polling.

This module sets up periodic tasks to:
1. Fetch odds from The Odds API
2. Store events and snapshots in the database
3. Calculate probabilities

Tiered polling (optimized for 5M calls/month):
- Only polls sports with games starting within 6 hours
- Live games: Poll every 32 seconds
- Games starting in 0-2 hours: Poll every 60 seconds
- Games starting in 2-6 hours: Poll every 2 minutes
- No games in 6 hours: Don't poll that sport at all

Adaptive slowdown: If odds aren't changing, polling slows down automatically
to conserve API calls.

Estimated capacity: ~1.9 calls/second, ~166K calls/day.
"""

import logging
import os

import sentry_sdk
from celery import Celery
from celery.schedules import crontab
from sentry_sdk.integrations.celery import CeleryIntegration

from app.tasks.base import run_async

# #2236: the live republish period is declared beside the live cache ceiling it
# has to stay under, not beside the beat that consumes it. See feed_cache.py.
from app.utils.feed_cache import FEED_LIVE_REPUBLISH_PERIOD_S

import time as _time

# ---------------------------------------------------------------------------
# Structured JSON logging for production (Heroku)
# ---------------------------------------------------------------------------
if os.getenv("DYNO"):
    from pythonjsonlogger import jsonlogger

    _json_handler = logging.StreamHandler()
    _json_handler.setFormatter(jsonlogger.JsonFormatter(
        fmt="%(asctime)s %(levelname)s %(name)s %(message)s",
        rename_fields={"asctime": "timestamp", "levelname": "level"},
    ))
    logging.root.handlers = [_json_handler]
    logging.root.setLevel(logging.INFO)

logger = logging.getLogger(__name__)


def _is_staged_futures_incomplete(exc: BaseException) -> bool:
    """Is this the calibration build's "banked progress, nothing to publish" signal?

    CAL-P040 (codex C283). Imported lazily and inside a guard for two reasons,
    both of which matter more than the tidiness of a module-scope import:

    * ``_tracked_run`` is the boundary for ~125 tasks. Only one of them can ever
      raise this type, so the cost belongs on the exception path, not on every
      task's import.
    * This runs while an exception is already in flight. An import that raised
      here would replace the real terminal with an ``ImportError`` — the failure
      mode is *losing the thing we came to record*. Returning ``False`` degrades
      to the previous behaviour (record a failure), which is wrong but honest.
    """
    try:
        from app.tasks.calibration_main_build import StagedFuturesIncomplete
    except Exception:  # noqa: BLE001 — see docstring: never mask the live exception
        return False
    return isinstance(exc, StagedFuturesIncomplete)


def _tracked_run(task_name: str, async_fn):
    """Run an async task and record its HONEST outcome in Redis.

    Queue 300H (#1515). This used to record a success for any invocation that
    returned without raising, which is how three calibration tasks reported
    ``health: healthy`` while producing nothing: a time-horizon build that
    returned ``horizons_done: 0/4`` every 6h, a price sweep that returned
    ``terminal: partial`` on every deadline-truncated run, and a coverage
    snapshot that swallowed its own exception and returned ``terminal:
    "failed"``. The returned summary was right there in every case; nothing
    read it.

    Now the summary is classified by the pure contract in
    ``app.utils.task_verdict`` and the verdict decides which counter moves:

    * ``complete``   → success, as before
    * ``partial``    → incomplete: no success, no escalation, never GREEN
    * ``failed``     → failure (returned, not thrown) → degraded immediately
    * ``unknown``    → authoritative: incomplete. Legacy (no terminal truth in
      the summary at all): recorded as a success exactly as before, but stamped
      ``unverified`` — the invocation returned, which is not proof of work.

    Enforcement is scoped to ``task_verdict.ENFORCED_TASKS`` — the four
    calibration adapters. Every other task classifies to a non-authoritative
    ``unknown`` and records exactly as it did before, because a ``status`` key
    means "no live games" or "nothing to backfill" in most of this codebase and
    reading it as a terminal would swap one false GREEN for thirty false REDs.

    Thrown exceptions keep their existing behaviour, with ONE named exception
    (CAL-P040, codex C283): :class:`~app.tasks.calibration_main_build.StagedFuturesIncomplete`
    is the calibration build's designed "units banked, nothing published" signal,
    and it was being counted as a thrown failure like anything else. See the
    handler below — that single miscount is why ``incompletes_24h`` sat at 0
    against ``consecutive_failures`` 201 while the clean partial path existed and
    worked.

    ``BaseException`` is now caught rather than ``Exception`` so a cancellation
    or a warm-shutdown kill records a terminal before propagating — an in-flight
    beat killed by a deploy used to vanish from both the ledger and the counters
    (r346).
    """
    from app.tasks.redis_state import (
        record_task_incomplete,
        record_task_label,
        record_task_started,
        record_task_success,
        record_task_failure,
        touch_worker_liveness,
    )
    from app.utils.task_verdict import (
        COMPLETE,
        FAILED,
        PARTIAL,
        UNKNOWN,
        describe_worker_shutdown,
        verdict_for,
    )

    # #1280 Item 3: every task run refreshes this worker generation's liveness so
    # the phase-heartbeat watchdog can tell a frozen marker owned by a live
    # generation (real wedge → RED) from one left by a dead/restarted generation
    # (stale → reconcile, no page). Best-effort; never blocks the task.
    touch_worker_liveness()
    # CAL-P024b: the FIRE is recorded here, before the work, because every other
    # counter in this function is written by a handler and a hard kill reaches
    # no handler. Without it "started 24 times and died 24 times" and "never
    # scheduled" are the same observation — which is how a memory kill was read
    # as a scheduling fault for a week. Fix the instrument before the patient.
    record_task_started(task_name)
    # LAT-P022 (#1609): remember which celery task name this metric label
    # belongs to. The beat schedule speaks `app.tasks.foo`; every counter in
    # this module is keyed by the short label passed to `_tracked_run`, and
    # nothing anywhere joined the two — which is why the only cadence-aware
    # health surface in the app (`_AUTOPILOT_BEATS`) is a hand-written list of
    # TWO of the 125 beat entries, with their cadences transcribed by hand and
    # free to drift from the schedule they describe. Recorded here, from the
    # live request, because this is the one place both names are known at once,
    # and a mapping observed from real runs cannot go stale the way a
    # transcribed one does.
    record_task_label(task_name)
    start = _time.monotonic()
    try:
        result = run_async(async_fn)
        duration_ms = (_time.monotonic() - start) * 1000
        # Extract summary from task result (most tasks return dicts)
        summary = result if isinstance(result, dict) else {"result": str(result)[:200]}
        verdict = verdict_for(task_name, result)

        if verdict.verdict == COMPLETE:
            record_task_success(
                task_name, duration_ms, summary,
                verdict=COMPLETE, verdict_reason=verdict.reason,
            )
        elif verdict.verdict == FAILED:
            # #2222: pass the summary. A RETURNED failure has one — it is the
            # task's own account of what it did — and it is the single most
            # useful thing an operator can read. Only the thrown path below has
            # nothing to pass, because there the result is the exception.
            record_task_failure(
                task_name, duration_ms,
                f"task returned a failed terminal ({verdict.reason})",
                verdict=FAILED, verdict_reason=verdict.reason,
                result_summary=summary,
            )
        elif verdict.verdict == UNKNOWN and not verdict.authoritative:
            # Legacy shape: preserve the pre-300H recording so ~100 tasks that
            # predate the contract keep a usable health surface, but say plainly
            # that nothing was verified.
            record_task_success(
                task_name, duration_ms, summary,
                verdict="unverified", verdict_reason=verdict.reason,
            )
        else:
            record_task_incomplete(
                task_name, duration_ms,
                verdict=verdict.verdict, verdict_reason=verdict.reason,
                result_summary=summary,
            )
        return result
    except BaseException as exc:  # noqa: BLE001 — cancellation must leave a terminal
        duration_ms = (_time.monotonic() - start) * 1000
        if _is_staged_futures_incomplete(exc):
            # CAL-P040, from codex C283's BLOCK on CAL-P038.
            #
            # CAL-P038 made the build STOP at a unit boundary and raise this
            # instead of letting Postgres cancel its last unit — its fix works.
            # But the type is raised, and every raise reached the generic handler
            # below, so the honest partial was recorded as a thrown failure at the
            # one boundary CAL-P038's unit tests stopped below. Production said so
            # plainly and for a long time: ``incompletes_24h`` **0** against
            # ``consecutive_failures`` **201**, with a ledger whose own terminal
            # already read ``cancelled``. Two boundaries, one event, two verdicts.
            #
            # This is not "an error we tolerate". ``StagedFuturesIncomplete``
            # documents itself as the one way this build stops that is neither a
            # bug nor a resource problem, and ``PhaseRunner.classify_failure``
            # already maps it to ``cancelled`` rather than ``failed`` so that "a
            # working build does not page anybody RED for doing exactly what it
            # was designed to do". Recording a failure here defeated that in the
            # only place an operator actually looks.
            #
            # Consequences worth stating, because they are visible in production
            # the moment this deploys:
            #   * ``incompletes_24h`` starts moving.
            #   * ``consecutive_failures`` FREEZES rather than climbing —
            #     ``record_task_incomplete`` deliberately leaves it alone. That is
            #     the counter no longer being lied to, NOT the build recovering.
            #     Nothing here makes a beat converge.
            #   * ``last_verdict`` becomes ``partial``, which keeps the task out
            #     of GREEN exactly as before. An incomplete build is still not a
            #     healthy one.
            summary = {
                "status": "incomplete",
                # ``cancelled`` is not decoration: it is in
                # ``task_verdict._TERMINAL_PARTIAL``, so this summary classifies
                # as PARTIAL if it is ever fed back through the contract. The two
                # paths cannot drift into disagreeing about the same event.
                "terminal": "cancelled",
                "reason": str(exc) or type(exc).__name__,
            }
            record_task_incomplete(
                task_name, duration_ms,
                verdict=PARTIAL, verdict_reason=type(exc).__name__,
                result_summary=summary,
            )
            # RETURN rather than re-raise, deliberately, and this is the one
            # judgement call in the change. Re-raising would move the counter
            # correctly and then mark the Celery task FAILURE and emit a Sentry
            # event for behaviour the design calls correct — reintroducing the
            # false RED one layer up from the one being removed. Nothing retries
            # this task and nothing reads its Celery state, so returning costs no
            # signal; the counters above carry the whole truth, and the ledger
            # (already written by the build before it raised) carries the detail.
            return summary
        if isinstance(exc, SystemExit):
            # CAL-P081 (#2052, #2007). A ``SystemExit`` reaching a task is the
            # RUNTIME tearing the worker down, never the task's own fault —
            # nothing in ``app/`` raises one. Recording it as a thrown failure is
            # #2052's false RED one layer up: ``consecutive_failures`` climbing
            # against a build that was working and got interrupted.
            #
            # On 2026-08-20 this task read ``consecutive_failures: 2`` with
            # ``last_error: "-241"`` — a bare ``str(exc)`` that names neither the
            # class nor the cause. Attribution took a manual cross-reference
            # against ``heroku releases``, twice; ``describe_worker_shutdown``
            # writes the half that was missing (the release and its age at the
            # instant of teardown) into the record, so the next one is
            # attributable from the record alone.
            #
            # RE-RAISED, unconditionally. A ``SystemExit`` that a handler
            # swallows is a worker that will not shut down, which is a far worse
            # bug than the one being fixed.
            record_task_incomplete(
                task_name, duration_ms,
                verdict=PARTIAL, verdict_reason=f"interrupted:{type(exc).__name__}",
                result_summary=describe_worker_shutdown(exc),
            )
            raise
        record_task_failure(
            task_name, duration_ms,
            str(exc) or type(exc).__name__,
            verdict="thrown", verdict_reason=type(exc).__name__,
        )
        raise

# Redis URL from environment
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# Handle Heroku Redis SSL (rediss:// URLs require ssl_cert_reqs=None)
broker_use_ssl = None
if REDIS_URL.startswith("rediss://"):
    import ssl
    broker_use_ssl = {
        "ssl_cert_reqs": ssl.CERT_NONE,
    }

# #1197: explicit TCP keepalive timers shared by the broker + result backend and
# the get_redis_client helpers (single source in config.py). Empty {} on platforms
# without TCP_KEEPIDLE (macOS CI) — redis-py then falls back to plain keepalive.
from app.tasks.config import socket_keepalive_options as _socket_keepalive_options
from app.tasks.result_retention import RESULT_EXPIRES_S as _RESULT_EXPIRES_S
from app.tasks.result_retention import apply_result_suppression as _apply_result_suppression

_KEEPALIVE_OPTS = _socket_keepalive_options()

# Create Celery app
celery_app = Celery(
    "bainluck",
    broker=REDIS_URL,
    backend=REDIS_URL,
)

# Celery configuration
celery_config = {
    "task_serializer": "json",
    "accept_content": ["json"],
    "result_serializer": "json",
    "timezone": "UTC",
    "enable_utc": True,
    "task_track_started": True,
    "task_time_limit": 300,  # 5 minute timeout
    "worker_prefetch_multiplier": 1,
    # Queue 300R Item 1: bound result residency explicitly. Celery's default is
    # 24h, and on a 50MB allkeys-lru instance a 24h result key is not "stored",
    # it is queued for eviction alongside everything else. Admin status polls
    # read a task_id while the operator is on the page, so an hour is generous.
    # The per-task half of this (suppressing results nothing can poll) is
    # applied after the beat schedule — see result_retention.py.
    "result_expires": _RESULT_EXPIRES_S,
    # ------------------------------------------------------------------------
    # Redis connection stability (#1197). The sustained TLS
    # `[SSL: UNEXPECTED_EOF_WHILE_READING]` ConnectionError volume (~135-180/24h,
    # firstSeen Feb) is Heroku-Redis idle-connection churn: the stacktrace lands
    # in celery/backends/redis.py `get()` → `connect_check_health` → TLS
    # `do_handshake`, i.e. a connection Heroku had idle-closed is being
    # re-established and the handshake EOFs. TCP keepalive keeps pooled
    # connections alive so they aren't idle-reaped (fewer reconnects = fewer
    # handshake EOFs), and a health-check interval makes redis-py proactively
    # PING+recycle a stale connection instead of failing on first reuse. Applied
    # to BOTH the broker and the result backend (the trace is the backend; the
    # sibling Sentry groups on the broker share the same root cause).
    "redis_socket_keepalive": True,          # result-backend TCP keepalive
    "redis_backend_health_check_interval": 25,
    "redis_socket_connect_timeout": 5,       # bound the handshake (was unbounded)
    # #1197 (r246 option a) — the pool/recycle tuning the #233 keepalive-alone
    # didn't deliver (churn rose 135→294/24h after it). Two levers:
    #   1) socket_keepalive_options: explicit TCP KEEPIDLE/INTVL/CNT so pooled
    #      connections are probed BEFORE Heroku's idle-reap window instead of dying
    #      on next reuse with a TLS EOF (bare socket_keepalive=True uses the ~2h OS
    #      default idle — longer than the reap, so it never helped). See config.py.
    #   2) retry_on_timeout + broker_connection_retry_on_startup: a transient
    #      handshake EOF/timeout retries transparently instead of surfacing as a
    #      ConnectionError. Applied to BOTH broker and result backend.
    "redis_retry_on_timeout": True,          # result-backend transient-error retry
    "broker_connection_retry_on_startup": True,
    "broker_connection_retry": True,
    "broker_transport_options": {
        "socket_keepalive": True,
        "socket_keepalive_options": _KEEPALIVE_OPTS,
        "health_check_interval": 25,
        "retry_on_timeout": True,
    },
    "result_backend_transport_options": {
        "socket_keepalive": True,
        "socket_keepalive_options": _KEEPALIVE_OPTS,
        "health_check_interval": 25,
        "retry_on_timeout": True,
    },
}

if broker_use_ssl:
    celery_config["broker_use_ssl"] = broker_use_ssl
    celery_config["redis_backend_use_ssl"] = broker_use_ssl

celery_app.conf.update(**celery_config)

# #1280 Item 3: refresh this worker generation's liveness on every Celery
# heartbeat, independent of task execution. This keeps the liveness key fresh
# even for a briefly-idle worker (so the phase-heartbeat watchdog never mis-reads
# a healthy generation as dead), and — because the heartbeat is emitted by the
# worker's main process, not the wedged task's event loop — it stays fresh during
# a genuine event-loop wedge, so a real stall still reads RED. Wrapped
# defensively: a signal-API change must never block worker startup.
try:  # pragma: no cover - signal wiring exercised by the worker, not unit tests
    from celery.signals import worker_heartbeat as _worker_heartbeat

    @_worker_heartbeat.connect
    def _refresh_worker_liveness(**_kwargs):
        try:
            from app.tasks.redis_state import touch_worker_liveness

            touch_worker_liveness()
        except Exception:
            pass
except Exception:  # pragma: no cover - defensive
    pass

# LAT-P039 (#1609, #1716): count the DELIVERY of every task here, in celery's
# own pre-run signal, rather than inside `_tracked_run`.
#
# `_tracked_run` is called BY THE TASK BODY, which means the only fires it can
# count are the ones a body decides to hand it — and a body decides that after
# its own gate has run. Two whole classes of task were therefore uncountable,
# and both read as a scheduling fault:
#
#   * A self-gating task (`poll_all_odds` -> `should_poll_now()`) returns before
#     `_tracked_run`, so its deliberate skips presented as missing fires. That
#     is the entirety of #1609's "the beat is firing at half its schedule": the
#     beat was firing at exactly 30.0s throughout.
#   * 30 of 117 beat-scheduled tasks never call `_tracked_run` at all, so they
#     never reached `record_task_label` and could not be joined to the schedule.
#     They are 30 of the 34 `unmapped` entries on the adherence surface (#1716).
#
# The signal sees every delivery of every task before any body runs, so neither
# class can hide from it, and — unlike a decorator or a base class — it cannot
# be forgotten when someone adds task 118. The label map is written here too,
# from the same request, so a task that never calls `_tracked_run` still joins.
#
# Wrapped defensively for the same reason as the heartbeat above: a signal-API
# change must never block worker startup, and observability must never be why a
# task fails to start.
#
# LAT-P043 (codex C-RV-1, #1802): `task_prerun` fires before every EXECUTION
# ATTEMPT, and two kinds of attempt are not a beat fire:
#
#   * A RETRY. `self.retry()` re-publishes the same task id from inside the
#     body, so a failing beat task manufactures up to `max_retries + 1`
#     deliveries out of one scheduled fire — inflating the denominator that
#     hides the missed schedule. `sync_sports`, `discover_events` and the 30s
#     `poll_all_odds` all retry, and `poll_all_odds` is the task the surface
#     exists to grade.
#   * An EAGER call. `task_always_eager` executes in-process with no broker and
#     no publication at all. Not enabled in production, but a local or test
#     run against a shared Redis would write schedule evidence for a fire that
#     never crossed a wire.
#
# Both are the same shape as the defect this counter was built to fix: a fact
# about the TASK read as a fact about the SCHEDULER. The residual boundary is
# named rather than papered over — a manual `.delay()` is indistinguishable
# from a beat publication at this signal, because celery beat stamps nothing on
# the message that says so. Deliveries are therefore "broker publications this
# process consumed, first attempt only", which is an upper bound on beat fires.
try:  # pragma: no cover - signal wiring exercised by the worker, not unit tests
    from celery.signals import task_prerun as _task_prerun

    @_task_prerun.connect
    def _record_delivery(sender=None, task=None, **_kwargs):
        try:
            from app.tasks.redis_state import record_task_attempt, record_task_delivery

            name = getattr(sender, "name", None) or getattr(task, "name", None)
            request = getattr(sender, "request", None)
            if request is None:
                request = getattr(task, "request", None)
            # #1501 item 2: the ATTEMPT is recorded first and unconditionally,
            # BEFORE the two schedule-semantics filters below. The two counters
            # answer different questions and must not share a predicate:
            # `deliveries` grades a SCHEDULE, so a retry is not a fire; the
            # lifecycle pair detects DEATH, and a retry that dies is a death.
            # Filtering it here would leave a terminal with no attempt and drive
            # the difference negative — which floors to zero and reads healthy.
            record_task_attempt(name)
            # An unreadable request must not silently zero the counter: the
            # count is the point, and losing it is worse than an upper bound.
            if request is not None:
                if (getattr(request, "retries", 0) or 0) > 0:
                    return
                if getattr(request, "is_eager", False):
                    return
            record_task_delivery(name)
        except Exception:
            pass
except Exception:  # pragma: no cover - defensive
    pass

# #1501 item 2 (codex C-CERT-SENTRY-R2): the TERMINAL half of the lifecycle
# pair. `task_postrun` fires after the body returns or raises, for every task,
# with no cooperation from the body — so `attempts - terminals` is a death count
# that holds for the 30 tasks which never call `_tracked_run`, and for a child
# killed before it gets there. Without this half, the parent-side
# `WorkerLostError` that Sentry DROPS has no compensating observer at all: the
# drop was justified by `hard_kills_24h`, and that counter is written from
# inside `_tracked_run`, i.e. below the boundary where these deaths happen.
#
# See `redis_state.TASK_LIFECYCLE_PREFIX` for the two named residuals.
try:  # pragma: no cover - signal wiring exercised by the worker, not unit tests
    from celery.signals import task_postrun as _task_postrun

    @_task_postrun.connect
    def _record_terminal(sender=None, task=None, **_kwargs):
        try:
            from app.tasks.redis_state import record_task_terminal

            name = getattr(sender, "name", None) or getattr(task, "name", None)
            record_task_terminal(name)
        except Exception:
            pass
except Exception:  # pragma: no cover - defensive
    pass

# =============================================================================
# Queue routing: realtime vs background vs heavy workers
#
# realtime (Standard-2X, concurrency=4):
#   High-frequency tasks driving user-visible live game data.
#   Never blocked by batch jobs.
#
# background (Standard-1X, concurrency=2):
#   Short (<300s) hourly/daily batch tasks and the merge drivers. Latency-
#   tolerant but must still fire promptly — so it must NOT share slots with
#   300s+ grinders. Memory budget: 2 × 200MB + ~100MB overhead ≈ 500MB, which
#   fits a 512MB Standard-1X *exactly*: concurrency here is a MEMORY bound, not
#   a preference, so "just raise it to 4" is a dyno upgrade, not a config edit.
#   NOTE (#233): the sentinels moved OFF background onto `heavy` — the ~40-beat,
#   2-slot queue was starving their morning fires (no_run_cached).
#
#   ⚠️ THE STANDING FACT ABOUT THIS QUEUE (#1609, measured LAT-P064/P065):
#   `warm_typeahead` runs 36.3s p50 against a 30s floor, i.e. it is
#   APPROXIMATELY ONE PERMANENTLY-OCCUPIED SLOT OF TWO. Background therefore has
#   ~ONE effective slot for ~40 beats. Anything multi-minute placed here does
#   not "share" the queue; it closes it. Price a new background beat against one
#   slot, never two.
#
# heavy (Standard-2X, concurrency=2):
#   ISOLATION LANE for the calibration precompute family — the user-facing
#   cache-warmers (precompute_calibration_main hourly, calibration_prices,
#   time_horizon, fair_fight, source_intelligence, coverage,
#   backfill_winners_status). These are 600s-class but latency-relevant: they
#   warm /calibration and the source dashboards. On a dedicated 2-slot worker
#   they can NEVER starve — at most 2-3 of them ever fire in the same minute
#   (only precompute_calibration_main is hourly; the rest are 6h and staggered
#   :00/:10/:15/:30), so 2 slots always suffice. This is the structural fix for
#   the recurring background-queue starvation (cal_price #183, then
#   time_horizon, then precompute_calibration_main #223) that per-task
#   minute-offset juggling could not durably solve.
#
#   Also here (#233): the 5 sentinels (flow/grid/horizon/settled daily
#   07:10-07:45 UTC + calibration weekly). They are daily and cheap (~5s
#   detect-only) — the antithesis of a slot-filler — but were dying as
#   no_run_cached on the congested background queue every morning (#232's
#   diagnosis). Their staggered daily fires never collide with the hourly
#   :15 precompute, so the 2 heavy slots absorb them without starving the
#   cache-warmers. Sentinels must fire PROMPTLY (they are alarms); heavy is
#   the only lane that guarantees a free slot at 07:10-07:45.
#
#   Also here since #1609 (LAT-P065): the three multi-minute BACKGROUND
#   residents. This REVERSES the #224-era pin below for exactly three tasks, on
#   today's numbers rather than on the shape of the old argument:
#
#     task                        p50      p95     cadence   duty (p50, 1 slot)
#     prediction_market_match    337.4s   699.4s   15 min    37.5%
#     poll_kalshi                320.2s   399.7s    2 h       4.4%
#     precompute_admin_link_rate  71.8s   122.2s   30 min     4.0%
#
#   Against the ~ONE effective background slot noted above, those three were
#   ~46% of everything background had — and `prediction_market_match` alone is
#   77.7% of a slot at p95, which is what actually produced the measured
#   `warm_typeahead` dispatch holes (five clean holes in 55.8 probe-free
#   minutes, one per 11.2 min; the warmer NOT RUNNING 30.0% of wall-clock).
#   They are latency-TOLERANT (a linkage pass and two cache warmers; no user
#   waits on any of them) and they were starving a latency-CRITICAL warmer, so
#   the #233 argument applies to them verbatim — it was simply never run on
#   these three.
#
#   Why heavy absorbs them: heavy is a **Standard-2X** (1 GB), not the
#   Standard-1X this comment claimed for months. 2 × 200MB children + overhead
#   is ~40% of its RAM, and it measured depth **0** while background sat at
#   **418**. Adding 45.9% of one slot to a 2-slot (200%) lane whose largest
#   resident is the hourly precompute_calibration_main leaves real margin.
#
#   🔶 REGISTERED COST, not hidden (ruling 050): `prediction_market_match` fires
#   :05/:20/:35/:50 and `precompute_calibration_main` at :15 can run to 19 min
#   (p95 1159s), so the 07:10-07:45 UTC sentinel window can now find both heavy
#   slots busy and DELAY a daily alarm by minutes. A delayed sentinel is not
#   #233's failure (that was `no_run_cached` — never running at all), and heavy
#   is the only lane where a delayed task still runs. If a sentinel is ever
#   observed missing rather than late, the remedy is heavy's concurrency (it has
#   the RAM headroom for 3), NOT sending these three back to background.
#
#   Deliberately STILL NOT here: the big backfills (backfill_winners 840s, the
#   kalshi/polymarket backfills 600-960s). They stay on `background` where they
#   have always lived — moving THEM here would fill both heavy slots for
#   ten-minute stretches and delay the hourly calibration warmer (observed live
#   during the #224 rollout). That observation was about the 600-960s class and
#   it still holds for the 600-960s class; it was never measured against the
#   300s class, and #1609 is what measured it.
#
# HEAVY membership rule: the calibration/precompute cache-warmer family + the
# 5 sentinels (#233) + the three multi-minute ex-background residents (#1609).
# Applied programmatically to both task_routes and the beat schedule's per-entry
# `options["queue"]` (beat options override task_routes, so both must agree —
# see the loop after the beat_schedule definition).
# =============================================================================

from kombu import Queue

celery_app.conf.task_queues = [
    Queue("realtime", routing_key="realtime"),
    Queue("background", routing_key="background"),
    Queue("heavy", routing_key="heavy"),
]

celery_app.conf.task_default_queue = "background"

celery_app.conf.task_routes = {
    # --- Realtime: live game data (30s-120s cycle) ---
    "app.tasks.poll_all_odds": {"queue": "realtime"},
    "app.tasks.poll_datagolf_inplay": {"queue": "realtime"},
    "app.tasks.poll_sport_odds": {"queue": "realtime"},
    "app.tasks.sync_espn_live_events": {"queue": "realtime"},
    "app.tasks.poll_live_prediction_markets": {"queue": "realtime"},
    "app.tasks.sync_mlb_win_probability": {"queue": "realtime"},
    "app.tasks.sync_statpal_live_plays": {"queue": "realtime"},
    "app.tasks.sync_statpal_livescores": {"queue": "realtime"},
    "app.tasks.poll_live_tennis_scores": {"queue": "realtime"},
    "app.tasks.heartbeat": {"queue": "realtime"},
    "app.tasks.transition_event_statuses": {"queue": "realtime"},
    # #2236 (LAT-P101). A warmer on `realtime` looks out of place, so the reason
    # is written here rather than left to be re-litigated. This is not a cost
    # decision, it is a CORRECTNESS one.
    #
    # The task's whole contract is "republish before the 60s live ceiling
    # expires", expressed as `PERIOD (40) + BUDGET (20) <= 60`. That arithmetic
    # assumes the pass STARTS at its period. `background` is documented three
    # dozen lines above as having ~one effective slot for ~45 beats, is measured
    # at ~90 % slot occupancy, and its own budget module says "ordinary co-tenant
    # bursts produce multi-minute waits". A pass that starts two minutes late
    # publishes nothing in time — the key already expired and the user already
    # paid the cold build. The fix would have been PARTIALLY INERT there, and
    # inert in the silent way: the beat would report success on every pass it
    # eventually ran.
    #
    # And it is the queue's own stated purpose: "high-frequency tasks driving
    # user-visible live game data. Never blocked by batch jobs." This fires only
    # while a live card is on the page, at a 40s cadence, to keep a live score
    # from going stale in front of somebody. Cost against the 4-slot pool: ~0.15
    # slots in the working case, <=0.5 in the pathological one (20s budget / 40s
    # period), and ~0 when nothing is live.
    "app.tasks.prewarm_live_feed_shapes": {"queue": "realtime"},
    # --- Everything else routes to background (default queue) ---
    # --- 600s-class grinders route to `heavy` (applied below) ---
}

# The big backfills + fast tasks stay on `background` (their historical home).
# Listed here for documentation / the guard test: these must NOT leak onto the
# heavy calibration lane, or they'd fill its 2 slots and re-starve the hourly
# /calibration warmer (observed live during the #224 rollout). Backfill-vs-fast
# contention on background was never the reported problem.
_HEAVY_KEEP_ON_BACKGROUND = {
    # NOTE (#1609, LAT-P065): match_prediction_markets and poll_kalshi_markets
    # were pinned here and MOVED TO HEAVY. They were 337.4s and 320.2s p50 on a
    # queue with ~one effective slot, and they were the measured cause of the
    # `warm_typeahead` dispatch holes. See the routing comment block above.
    "app.tasks.merge_duplicate_events",     # matching pipeline
    "app.tasks.merge_degenerate_combat_events",
    # NOTE: the 5 sentinels moved to HEAVY_TASKS (Queue #233) — see below.
    # the big backfills — deliberately NOT on heavy (see comment above)
    "app.tasks.backfill_winners",
    "app.tasks.backfill_kalshi_candlestick",
    "app.tasks.backfill_kalshi_history",
    "app.tasks.kalshi_cliff_drain",
    "app.tasks.reconcile_unanchored_events",
    "app.tasks.backfill_kalshi_settled",
    "app.tasks.backfill_kalshi_trades",
    "app.tasks.backfill_kalshi_volume",
    "app.tasks.backfill_polymarket_history",
    "app.tasks.backfill_polymarket_winners",
    # live/035 — same family: a multi-minute network sweep over an EXPIRING
    # population (Kalshi purges a settled market's candlesticks at ~47-86 days).
    "app.tasks.backfill_event_chart_history",
    "app.tasks.backfill_thin_event_charts",
    # live/059 — the outright-chart sibling of the two above. Same family: a
    # multi-minute paced network sweep, this one over tier-1 winner FIELDS
    # rather than games, filling the venue price history the futures sampler
    # cannot see between its ~78-minute readings.
    "app.tasks.fill_futures_chart_series",
    # live/039 — the one-time 30-day drain. Same family again, and the longest
    # runner of the three: re-triggered until it reports a TERMINAL verdict —
    # `drained`, or `drained_with_failures` when it gave up on events the venue
    # would not serve (live/042). Both stop the loop; only the first is clean.
    "app.tasks.backfill_thirty_day_charts",
    "app.tasks.backfill_espn_win_prob",
    "app.tasks.backfill_team_identities",
    # #2077 (queue 419). Same class as `kalshi_cliff_drain` two lines up and
    # placed here for the same reason: a multi-minute network sweep over an
    # EXPIRING population. It belongs to the 600-960s backfill family the
    # routing block above keeps off `heavy` — the observation that moving that
    # class here fills both heavy slots for ten-minute stretches and delays the
    # hourly calibration warmer was made about exactly this shape. Declared
    # rather than left to `task_default_queue`, because a default is not a
    # decision and the next reader of the routing block needs to see an
    # objection, not a silence.
    "app.tasks.run_settlement_sweep",
}

# The heavy lane = the calibration/precompute cache-warmer family PLUS the
# daily/weekly sentinels (Queue #233). Kept explicit (not derived from
# decorators) so routing is greppable and stable.
HEAVY_TASKS = {
    "app.tasks.precompute_calibration_main",       # hourly :15 — the frozen one (#223)
    "app.tasks.compute_calibration_prices",        # cal_price (#183)
    "app.tasks.compute_time_horizon_calibration",  # time_horizon (r228: prior fix didn't take)
    "app.tasks.compute_fair_fight_comparison",
    "app.tasks.precompute_source_intelligence",
    "app.tasks.snapshot_coverage_metrics",
    "app.tasks.precompute_backfill_winners_status",
    # Sentinels (Queue #233): moved off `background` because the morning beats
    # (flow 07:10 / grid 07:25 / horizon 07:40 / settled 07:45 UTC) were dying
    # as no_run_cached on the congested ~40-beat, 2-slot background queue
    # (#232's diagnosis). They are daily (calibration weekly) and cheap (~5s
    # detect-only), so 2 heavy slots absorb them with room to spare — the hourly
    # precompute (:15) never collides with the staggered :10/:25/:40/:45 fires.
    # All 5 sentinels move together (the code has always treated them as one
    # group); horizon at 07:40 is inside the protected window, so leaving it on
    # background would keep a beat contending exactly where #233 needs quiet.
    "app.tasks.flow_sentinel",
    "app.tasks.grid_sentinel",
    "app.tasks.grid_register_sentinel",
    "app.tasks.tournament_register_sentinel",
    "app.tasks.horizon_sentinel",
    "app.tasks.settled_concept_sentinel",
    "app.tasks.calibration_sentinel",
    # #2853 — the anchor-schedule rail's nightly read-only driver. Same family
    # and the same reason: a daily detect-only sentinel that must not sit on the
    # congested background queue. It is the most network-bound of the group
    # (one ESPN `summary?event=` per row, budget-capped at 300s), which is an
    # argument for the protected slot, not against it.
    "app.tasks.anchor_schedule_sentinel",
    # Queue #258: the Board Sentinel keeps the board itself honest (duplicate
    # fingerprints, stale Inbox, template-P1 share, blocked-in-Inbox, missing
    # area labels). Cheap + daily like its siblings; heavy queue for a free slot.
    "app.tasks.board_sentinel",
    # #2706: the matching reconciliation job. Same shape as the sentinels above
    # (read-only detect + deduped file) and it runs on the same cadence as the
    # matcher it guards, so it belongs on the same queue as `match_prediction_markets`
    # rather than contending for background's one effective slot.
    "app.tasks.matching_reconciliation",
    # #1201/#1193/#1202: daily MLB schedule self-heal + coverage. Cheap and daily
    # like the sentinels, and it must fire promptly at 07:05 so the standing
    # inverted rows are healed before the 07:10 flow sentinel reads resolved_state.
    "app.tasks.mlb_schedule_coverage",
    # --- #1609 (LAT-P065): the three multi-minute ex-`background` residents. ---
    # These are the TOPOLOGY FIX for the background-queue starvation, not new
    # heavy work. Each is latency-TOLERANT and each was measured holding a slot
    # on a queue that has ~one effective slot, starving the latency-CRITICAL
    # `warm_typeahead`. Full arithmetic + the registered sentinel-delay cost are
    # in the routing comment block above; do not move them back without
    # re-measuring background's effective slot count first.
    "app.tasks.match_prediction_markets",    # 337.4s p50 / 699.4s p95, every 15 min
    "app.tasks.poll_kalshi_markets",         # 320.2s p50, every 2 h
    "app.tasks.precompute_admin_link_rate",  # 71.8s p50 / 122.2s p95 — an ADMIN
                                             # cache warmer no user waits on, and
                                             # it was directly observed holding a
                                             # slot through a measured hole.
    # --- Option D (#1866, LAT-P067): the typeahead index builder + its sentinel.
    # These go on `heavy` and NOT on `background`, and the arithmetic is the
    # reason rather than the habit. `background` is the queue #1609 just proved
    # has ~ONE effective slot; putting a new multi-minute latency-TOLERANT
    # resident there would re-create the exact starvation that commit cures, on
    # the very queue whose depth read 3,014 at this window's Phase 0.
    #
    # The cost to `heavy` is bounded and small, stated so it can be checked: the
    # builder is capped at 90s and fires twice an hour (:23/:53) = ~2.5% of ONE
    # of heavy's two slots; the sentinel is a daily ~5s detect-only read at 07:50
    # UTC, deliberately AFTER the 07:45 settled sentinel so it never contends
    # inside #233's protected morning window. That is the whole added load, on a
    # lane that #1609 just added 45.9% of a slot to.
    "app.tasks.rebuild_typeahead_index",
    "app.tasks.typeahead_index_sentinel",
    # --- RULING 110 (#1609, LAT-P077): the SCOPED exception, two tasks BY NAME.
    # These are the only two entries in this set that are NOT calibration/
    # precompute/sentinel work, and they are here by an explicit Fable ruling
    # that names them individually. It is NOT a class, NOT a prefix, and NOT
    # "big backfills may now use heavy" — the rest of that family stays in
    # `_HEAVY_KEEP_ON_BACKGROUND` above and the guard test asserts it.
    #
    # The grant is CONDITIONAL and its condition is armed in
    # `app/utils/heavy_routing_falsifier.py`: if any calibration heavy-beat's
    # latency degrades measurably against the baseline pinned there, the
    # routing reverts THE SAME WINDOW and the calibration-only rule re-hardens.
    # `GET /api/admin/heavy-move/falsifier` reads that verdict.
    #
    # ⚠️ MEASURED COST, and it does not point the way the census did.
    # LAT-P076's slot census priced these at 32% + 24% = 56% of one background
    # slot. From durations (n=50 each) x 24h run counts they are 6.1% + 12.8% =
    # ~19% observed. AND both run far below schedule (31 of 72 fires, 45 of 96)
    # BECAUSE they are starved — so `heavy` may inherit up to 41.5% of a slot
    # while `background` sheds only 19%. That asymmetry is the risk the
    # falsifier watches; it is not a reason to skip the move, it is the reason
    # the move is watched. Full arithmetic in the falsifier's docstring.
    "app.tasks.backfill_market_shapes",
    "app.tasks.precompute_backfill_progress",
    # #2199, hourly :50. Not part of the conditional calibration grant above —
    # this one is here on the plain reading of the background note: its wall
    # budget is 420s, and background has ~one effective slot for ~40 beats, so
    # placing it there would close the queue rather than share it. It cannot
    # collide with the :15 precompute, and it is the only heavy beat at :50.
    "app.tasks.refresh_stale_futures_prices",
}

for _heavy_task in HEAVY_TASKS:
    celery_app.conf.task_routes[_heavy_task] = {"queue": "heavy"}

#: Sentry Crons is OFF and stays off. See `build_celery_integration`.
#:
#: A named constant rather than a bare literal so the guard test has something to
#: pin that is not the source text of a call site.
SENTRY_MONITOR_BEAT_TASKS = False


def build_celery_integration() -> CeleryIntegration:
    """The worker's Sentry Celery integration, with cron monitoring OFF.

    ** THE CAPABILITY IS DELETED, NOT REMEMBERED. ** `monitor_beat_tasks=True`
    makes the SDK auto-create one Sentry cron monitor per beat task on first
    dispatch. It created **129 PAID monitors** and spent the whole $100
    pay-as-you-go budget in 4 days (Fable/Alex, 2026-08-21).

    `beat_schedule` carried **132** entries when that was measured (2026-08-21)
    and **141** on this tree, not 129 — the reported monitor count is monitors
    that had DISPATCHED at least once, so the two numbers are not the same
    quantity and the gap was three beats that had not yet fired. Recorded rather
    than reconciled, because the cost scales with the schedule, the schedule is
    the larger number, and it only ever grows.

    Nothing is lost by turning it off. Beat observability here is `task-metrics`
    plus the samplers — our own rail, already the thing every latency and
    calibration read is taken against. Sentry Crons was a second, billed copy of
    a signal we already own, and it was never the one anybody consulted.

    Post-deploy the 129 monitors simply stop receiving check-ins and go quiet;
    deleting them in the Sentry UI is cosmetic cleanup, not part of the fix.
    """
    return CeleryIntegration(monitor_beat_tasks=SENTRY_MONITOR_BEAT_TASKS)


# Initialize Sentry for Celery workers
# Set SENTRY_DSN env var in Heroku to enable
sentry_dsn = os.getenv("SENTRY_DSN")
if sentry_dsn:
    # #1501: this init had NO before_send, while app/main.py has carried one for
    # months — and every top quota consumer is worker-side. Measured over the
    # 2026-07-21 -> 07-29 billing cycle: 6,584 billable events (3,585 `error` +
    # 2,999 `default`) against a 5,000/MONTH allowance, i.e. the month spent on
    # day 8. The filter existed; it was wired to the one process that does not
    # generate the flood. Shared policy, both entry points.
    from app.utils.sentry_filter import build_before_send

    # WE KEEP ZERO SENTRY CRON MONITORS. `monitor_beat_tasks=True` auto-created
    # ONE PAID CRON MONITOR PER BEAT TASK — 129 of them — and consumed the entire
    # $100 pay-as-you-go budget in 4 days (Fable/Alex ruling, 2026-08-21). Beat
    # observability is our own `task-metrics` rail and the samplers; the Sentry
    # crons product duplicated it at a per-monitor price.
    #
    # ** `False` IS THE SDK'S OWN DEFAULT — we had explicitly turned this ON. **
    # It is nonetheless passed explicitly, and through a factory rather than
    # inline, for two reasons: the explicit kwarg records that OFF is a decision
    # rather than an omission, and the factory is what lets the guard test
    # introspect the integration this init actually builds instead of asserting
    # on source text. A grep cannot prove a flag is wired.
    sentry_sdk.init(
        dsn=sentry_dsn,
        environment=os.getenv("SENTRY_ENVIRONMENT", "production"),
        release=os.getenv("HEROKU_SLUG_COMMIT"),
        traces_sample_rate=0.05,  # 5% of tasks for performance monitoring
        send_default_pii=False,
        before_send=build_before_send(),
        integrations=[
            build_celery_integration(),
        ],
    )


# =============================================================================
# Task definitions
#
# Each task is a thin wrapper that calls run_async() on the async implementation
# from the appropriate submodule. The name= parameter is pinned to "app.tasks.*"
# to match the beat schedule and preserve backward compatibility.
# =============================================================================


# --- Sports & Event Discovery ---

@celery_app.task(bind=True, max_retries=3, name="app.tasks.sync_sports")
def sync_sports(self):
    """Sync available sports from The Odds API to database."""
    from app.tasks.sports import _sync_sports
    try:
        return run_async(_sync_sports())
    except Exception as exc:
        raise self.retry(exc=exc, countdown=60)


@celery_app.task(bind=True, max_retries=3, name="app.tasks.discover_events")
def discover_events(self):
    """Discover events for ALL active sports, then update taxonomy tags."""
    from app.tasks.sports import _discover_events
    try:
        result = _tracked_run("discover_events", _discover_events())
        # Piggyback taxonomy update — worker concurrency=2 means dedicated
        # taxonomy tasks never get a slot. Run inline after discovery.
        try:
            from app.tasks.taxonomy import _update_event_tags_impl
            tag_result = _tracked_run("update_event_tags", _update_event_tags_impl(500))
            result["taxonomy"] = tag_result
        except Exception as tag_exc:
            logger.warning("Taxonomy update failed: %s", tag_exc)
            result["taxonomy_error"] = str(tag_exc)[:200]
        # LLM enrichment — gated to run at most every 10 min
        try:
            from app.tasks.redis_state import get_redis_client
            r = get_redis_client()
            lock_key = "bainluck:llm_enrich_gate"
            if r.set(lock_key, "1", nx=True, ex=600):  # 10 min TTL
                from app.tasks.taxonomy import _enrich_taxonomy_llm_impl
                llm_result = _tracked_run(
                    "enrich_taxonomy_llm",
                    _enrich_taxonomy_llm_impl(event_limit=50, market_limit=30),
                )
                result["llm_enrichment"] = llm_result
            else:
                result["llm_enrichment"] = "skipped (gate)"
        except Exception as llm_exc:
            logger.warning("LLM enrichment failed: %s", llm_exc)
            result["llm_enrichment_error"] = str(llm_exc)[:200]
        # Piggyback DataGolf hourly poll — same starvation issue as taxonomy
        try:
            from app.tasks.redis_state import get_redis_client as _get_rc
            _r = _get_rc()
            dg_gate_key = "bainluck:datagolf_poll_gate"
            if _r.set(dg_gate_key, "1", nx=True, ex=3600):  # 1 hour TTL
                from app.tasks.datagolf import _poll_datagolf_markets
                dg_result = _tracked_run("poll_datagolf", _poll_datagolf_markets())
                result["datagolf"] = dg_result
            else:
                result["datagolf"] = "skipped (gate)"
        except Exception as dg_exc:
            logger.warning("DataGolf poll failed: %s", dg_exc)
            result["datagolf_error"] = str(dg_exc)[:200]
        return result
    except Exception as exc:
        raise self.retry(exc=exc, countdown=120)


# --- Odds Polling ---

@celery_app.task(bind=True, max_retries=3, name="app.tasks.poll_all_odds")
def poll_all_odds(self):
    """Poll odds for all configured sports with adaptive polling."""
    from app.tasks.odds_polling import _poll_all_odds
    from app.tasks.redis_state import should_poll_now

    should_poll, reason = should_poll_now()
    if not should_poll:
        return {"skipped": True, "reason": reason}

    try:
        result = _tracked_run("poll_odds", _poll_all_odds())
        # Piggyback DataGolf live poll — Redis-gated to 5 min
        try:
            from app.tasks.redis_state import get_redis_client
            r = get_redis_client()
            dg_live_key = "bainluck:datagolf_live_gate"
            if r.set(dg_live_key, "1", nx=True, ex=300):  # 5 min TTL
                from app.tasks.datagolf import _poll_datagolf_live
                dg_result = _tracked_run("datagolf_live", _poll_datagolf_live())
                result["datagolf_live"] = dg_result
            else:
                result["datagolf_live"] = "skipped (gate)"
        except Exception as dg_exc:
            logger.warning("DataGolf live poll failed: %s", dg_exc)
            result["datagolf_live_error"] = str(dg_exc)[:200]
        return {**result, "poll_reason": reason}
    except Exception as exc:
        raise self.retry(exc=exc, countdown=60)


@celery_app.task(bind=True, name="app.tasks.poll_sport_odds")
def poll_sport_odds(self, sport_key: str):
    """Poll odds for a single sport."""
    from app.tasks.odds_polling import _poll_sport_odds
    return run_async(_poll_sport_odds(sport_key))


@celery_app.task(bind=True, name="app.tasks.poll_mlb_pregame")
def poll_mlb_pregame(self):
    """MLB pre-game odds polling tier — densely samples the T-48h..T-2h dark
    window the main loop misses (issue #892)."""
    from app.tasks.odds_polling import _poll_mlb_pregame
    return _tracked_run("poll_mlb_pregame", _poll_mlb_pregame())


# --- Excitement Index (EI) ---

@celery_app.task(bind=True, name="app.tasks.compute_gei_for_event")
def compute_gei_for_event(self, event_id: int):
    """Compute EI for a single completed event. (Task name kept for beat schedule compat.)"""
    from app.tasks.excitement_index import _compute_ei_for_event
    return run_async(_compute_ei_for_event(event_id))


@celery_app.task(bind=True, name="app.tasks.compute_gei_batch")
def compute_gei_batch(self, limit: int = 100):
    """Compute EI for a batch of completed events. (Task name kept for beat schedule compat.)"""
    from app.tasks.excitement_index import _compute_ei_batch
    return run_async(_compute_ei_batch(limit))


@celery_app.task(bind=True, name="app.tasks.compute_gei_percentiles")
def compute_gei_percentiles(self):
    """Recompute EI percentile thresholds for all scopes. (Task name kept for beat schedule compat.)"""
    from app.tasks.excitement_index import _compute_ei_percentiles
    return run_async(_compute_ei_percentiles())


# --- Futures (The Odds API) ---

@celery_app.task(bind=True, name="app.tasks.poll_futures_odds")
def poll_futures_odds(self):
    """Poll futures/outrights odds from The Odds API."""
    from app.tasks.futures import _poll_futures_odds
    return _tracked_run("poll_futures", _poll_futures_odds())


# --- Kalshi ---

@celery_app.task(bind=True, name="app.tasks.poll_kalshi_markets", soft_time_limit=600, time_limit=660)
def poll_kalshi_markets(self):
    """Poll prediction markets from Kalshi (11 min limit for market backfill)."""
    from app.tasks.kalshi import _poll_kalshi_markets
    return _tracked_run("poll_kalshi", _poll_kalshi_markets())


@celery_app.task(name="app.tasks.run_freshness_watchdog")
def run_freshness_watchdog():
    """#995 NEVER-AGAIN: alert the moment market CREATION stalls per source, or a
    poll's phase marker stops advancing (suspected event-loop block). This is the
    creates-specific + heartbeat signal the 28-day freeze needed — the coarse
    "updated in 24h" check below stayed green throughout it."""
    from app.tasks.watchdog import _run_freshness_watchdog
    return _tracked_run("freshness_watchdog", _run_freshness_watchdog())


@celery_app.task(name="app.tasks.check_kalshi_freshness")
def check_kalshi_freshness():
    """Daily check: alert if no Kalshi markets were updated in the last 24 hours."""
    from sqlalchemy import text as sa_text

    async def _check():
        from app.tasks.base import get_task_session
        async with get_task_session() as session:
            result = await session.execute(
                sa_text(
                    "SELECT COUNT(*) FROM futures_markets "
                    "WHERE source = 'kalshi' AND updated_at > NOW() - INTERVAL '24 hours'"
                )
            )
            count = result.scalar()
        if count == 0:
            logger.critical("No Kalshi markets updated in 24h — ingestion may be broken")
            sentry_sdk.capture_message(
                "No Kalshi markets updated in 24h — ingestion may be broken",
                level="error",
            )
        return {"kalshi_updated_24h": count, "alert": count == 0}

    return run_async(_check())


# --- Cross-source futures price refresh ---

@celery_app.task(
    bind=True,
    name="app.tasks.refresh_stale_futures_prices",
    soft_time_limit=540,
    time_limit=600,
)
def refresh_stale_futures_prices(self, budget: int = 0):
    """#2199: price-refresh high-value open futures the discovery polls cannot reach.

    Both discovery scans are bounded by an ordering that puts already-known
    markets last — Polymarket's newest-startDate-first window spans about ten
    hours, Kalshi defers existing events behind new ones past its deadline — so
    long-lived championship fields went 8-32 days without a capture while the
    polls reported success. Full mechanism: ``app/tasks/futures_price_refresh``.
    """
    from app.tasks.futures_price_refresh import (
        DEFAULT_MARKET_BUDGET,
        _refresh_stale_futures_prices,
    )
    return _tracked_run(
        "futures_price_refresh",
        _refresh_stale_futures_prices(budget=budget or DEFAULT_MARKET_BUDGET),
    )


# --- Polymarket ---

@celery_app.task(bind=True, name="app.tasks.poll_polymarket_markets", soft_time_limit=540, time_limit=600)
def poll_polymarket_markets(self):
    """Poll prediction markets from Polymarket (no API key needed)."""
    from app.tasks.polymarket import _poll_polymarket_markets
    return _tracked_run("poll_polymarket", _poll_polymarket_markets())


@celery_app.task(bind=True, soft_time_limit=240, time_limit=300,
                 name="app.tasks.refresh_registered_tournament_prices")
def refresh_registered_tournament_prices(self):
    """Re-price exactly the Polymarket markets a tournament register pins (UX-P139).

    The scanning poll rotates a 20-page window under Gamma's offset-2000 cap,
    so a given event is re-priced only when the cursor reaches it. Measured
    2026-08-26 that left all 336 US Open round-advancement markets — the entire
    content of the bracket grid — 27 hours old while Polymarket snapshots
    overall were current to the minute. The register names those markets
    exactly, so this asks for them by condition id (a Gamma read that does not
    paginate and is therefore not capped) rather than waiting to be scanned.

    Prices only: never creates a market, never touches identity. ~11 batched
    Gamma calls per run.
    """
    from app.tasks.tournament_price_refresh import _refresh_registered_tournament_prices
    return _tracked_run(
        "tournament_price_refresh", _refresh_registered_tournament_prices()
    )


@celery_app.task(bind=True, soft_time_limit=180, time_limit=240,
                 name="app.tasks.link_tournament_matchups")
def link_tournament_matchups(self):
    """Bind registered fixtures to the match markets that price them (Q426).

    The draw census asked "does a market exist for this fixture?" once, at the
    ceremony, and wrote `missing` for all 96 US Open R128 fixtures — true then,
    false by the next morning, and never re-asked. Kalshi quoted every one of
    those matches while the cards rendered blank.

    This re-asks on a beat and writes an overlay to Redis. It never writes the
    committed register and can only fill a block the register itself marked
    `missing`; a curated pin is untouchable. Kalshi only, because a Kalshi match
    outcome names its own player and Polymarket's decomposed sub-market is an
    unlabelled Yes/No — see the resolver's docstring for why guessing there
    would trade a blank card for a backwards one.

    One indexed query per tournament, no third-party calls.
    """
    from app.tasks.tournament_matchup_linker import _link_tournament_matchups
    return _tracked_run("tournament_matchup_linker", _link_tournament_matchups())


@celery_app.task(bind=True, soft_time_limit=120, time_limit=180,
                 name="app.tasks.sync_tournament_results")
def sync_tournament_results(self):
    """Fetch ESPN's tennis results into Redis for the tournament hub (UX-P139).

    Alex's item 9: "Decided-match scores come from the ESPN API we already use
    for other scores — wire it." ESPN's tennis scoreboard carries the US Open
    with per-set line scores and a winner flag, grouped by slugs that ARE the
    register's own draw names. Nothing in our own tables holds a tennis result:
    checked 2026-08-26, zero `events` rows exist for any registered matchup.

    The fetch lives in a task rather than in the route because a third-party
    call inside a GET is the shape the feed's standing rule forbids by name.
    Two requests every three minutes.
    """
    from app.tasks.tournament_price_refresh import _sync_tournament_results
    return _tracked_run("tournament_results_sync", _sync_tournament_results())


@celery_app.task(bind=True, soft_time_limit=900, time_limit=960, name="app.tasks.backfill_polymarket_history")
def backfill_polymarket_history(self, limit: int = 500, fidelity: int = 60, interval: str = "max", mode: str = "resolved_zero"):
    """Backfill historical prices from Polymarket CLOB API for outcomes with sparse data."""
    from app.tasks.polymarket import _backfill_polymarket_price_history
    return _tracked_run("polymarket_history", _backfill_polymarket_price_history(limit, fidelity, interval, mode))


@celery_app.task(bind=True, soft_time_limit=900, time_limit=960, name="app.tasks.sync_polymarket_resolved")
def sync_polymarket_resolved(self):
    """Scan closed Polymarket events and update market status to 'resolved'."""
    from app.tasks.polymarket import _sync_polymarket_resolved_status
    return _tracked_run("polymarket_resolved_sync", _sync_polymarket_resolved_status())


@celery_app.task(bind=True, soft_time_limit=900, time_limit=960, name="app.tasks.backfill_kalshi_history")
def backfill_kalshi_history(self, limit: int = 500, mode: str = "resolved_zero"):
    """Backfill historical prices from Kalshi candlesticks API for outcomes with sparse data."""
    from app.tasks.kalshi import _backfill_kalshi_price_history
    return _tracked_run("kalshi_history", _backfill_kalshi_price_history(limit, mode))


@celery_app.task(bind=True, soft_time_limit=900, time_limit=960, name="app.tasks.backfill_event_chart_history")
def backfill_event_chart_history(self, event_ids=None, limit: int = 40, dry_run: bool = False):
    """live/035: draw an event's whole win-prob lifetime from its venues' history.

    For prediction-market-native events the `events` row is routinely created
    AFTER the match it describes (the Vallejo v Monfils specimen: event minted
    2026-09-01, market listed 2026-08-27), so every sampler-style win-prob writer
    we have is structurally incapable of the pre-match and in-match curve. Kalshi
    candlesticks and the Polymarket CLOB still hold it.

    Called with `event_ids` for a named repair; called bare it selects the
    thinnest charts still inside Kalshi's retention window.
    """
    from app.tasks.event_chart_backfill import run_event_chart_backfill
    return _tracked_run(
        "event_chart_backfill",
        run_event_chart_backfill(event_ids, limit=limit, dry_run=dry_run),
    )


@celery_app.task(bind=True, soft_time_limit=900, time_limit=960, name="app.tasks.backfill_thin_event_charts")
def backfill_thin_event_charts(self, limit: int = 90):
    """Nightly: pre-warm the thin charts a reader is likely to reach.

    Bounded at both ends (gotcha #41): the floor keeps it off markets Kalshi has
    provably purged, and inside that floor it works oldest-first so the at-risk
    edge is reached before it expires rather than after.

    live/036 (b): its population is no longer "every event we could fix". It is
    the ±7-day reader window on reader-reachable sports — 1,152 events measured,
    down from 44,315 — because the wide version lost ground every night and no
    budget fixed that. Anything outside it fills on demand when someone opens
    the page.
    """
    from app.tasks.event_chart_backfill import run_event_chart_backfill
    return _tracked_run(
        "thin_event_charts", run_event_chart_backfill(None, limit=limit)
    )


@celery_app.task(bind=True, soft_time_limit=900, time_limit=960, name="app.tasks.fill_futures_chart_series")
def fill_futures_chart_series(self, market_ids=None, limit: int = 25, dry_run: bool = False):
    """live/059: draw an outright's race from the VENUES' minutes, not our glance.

    `futures_odds_snapshots` is a sampler — roughly one reading per 78 minutes —
    and Kalshi quotes a 33-way field in whole cents, so a week of the US Open
    men's title race renders as fifteen distinct values (measured 2026-09-03:
    Alcaraz 129 points, 20 changes). The CLOB serves 1,441 one-minute points for
    the last day and reaches the January listing at `fidelity=720`; Kalshi's
    candlesticks serve 816 one-minute points for the same day. This fetches
    both, layers them fine-tier-first, blends the venues into the one number the
    doctrine requires, and caches the result per market.

    Called with `market_ids` for a named fill (the concept page's on-demand
    claim does exactly that); called bare it walks the eligible tier-1 outright
    population.
    """
    from app.tasks.futures_chart_series_fill import run_futures_chart_series_fill
    return _tracked_run(
        "futures_chart_series",
        run_futures_chart_series_fill(market_ids, limit=limit, dry_run=dry_run),
    )


@celery_app.task(bind=True, soft_time_limit=900, time_limit=960, name="app.tasks.backfill_thirty_day_charts")
def backfill_thirty_day_charts(
    self, limit: int = 200, dry_run: bool = False,
    min_period_minutes=None, only_tier=None,
):
    """live/039: the ONE-TIME drain of the last 30 days of attached events.

    Alex: "if we had Polymarket integration we could backfill all the events we
    don't have probabilities for from the last 30 days."

    Deliberately NOT on the beat schedule. The two steady-state rails already
    exist — `backfill_thin_event_charts` pre-warms the ±7-day reader window and
    `plan_on_demand_fill` catches what a reader opens — and this is the one-off
    backlog bite those two were told to stop chasing. It checkpoints per tier in
    Redis and is re-triggered until its verdict is TERMINAL: `drained` (every
    event asked and answered) or `drained_with_failures` (it gave up on events
    the venue would not serve). Anything else means there is more behind it.
    """
    from app.tasks.chart_backfill_thirty_day import run_thirty_day_chart_drain
    return _tracked_run(
        "thirty_day_chart_drain",
        run_thirty_day_chart_drain(
            limit=limit, dry_run=dry_run,
            min_period_minutes=min_period_minutes, only_tier=only_tier,
        ),
    )


@celery_app.task(bind=True, soft_time_limit=900, time_limit=960, name="app.tasks.backfill_kalshi_settled")
def backfill_kalshi_settled(self, limit: int = 5000, only_series=None):
    """Recover prices from Kalshi settled events API (much faster than candlesticks).

    ``only_series`` (#227 Item 2) pins the scan to specific series prefixes (e.g.
    ``["KXPGA"]`` for the Open) to settle an already-concluded event NOW."""
    from app.tasks.kalshi import _backfill_from_settled_events
    return _tracked_run("kalshi_settled", _backfill_from_settled_events(limit, only_series=only_series))


@celery_app.task(bind=True, soft_time_limit=420, time_limit=480, name="app.tasks.backfill_settled_gap_creation")
def backfill_settled_gap_creation(self, limit: int = 1500):
    """#138/#995: create Kalshi markets that opened+settled during the 2026-06-09→
    07-08 creation freeze (gotcha #38) — invisible to the open-poll and only
    UPDATEd (never created) by backfill_kalshi_settled. Bounded + resumable."""
    from app.tasks.kalshi import _backfill_settled_gap_creation
    return _tracked_run("kalshi_gap_creation", _backfill_settled_gap_creation(limit))


@celery_app.task(bind=True, soft_time_limit=600, time_limit=660, name="app.tasks.recover_datagolf_participation")
def recover_datagolf_participation(self, limit: int = 150):
    """#994 recover-first: reclassify wrongly-VOIDed DataGolf losers back into the
    calibration curve. Dedicated task (NOT a backfill_winners phase) because that
    pipeline is budget-starved before Phase 0g; this drains the ~17K DNP cohort
    reliably (bounded + resumable, quota-polite)."""
    from app.tasks.backfill_winners import _recover_datagolf_participation
    return _tracked_run("datagolf_recovery", _recover_datagolf_participation(limit=limit))


@celery_app.task(bind=True, soft_time_limit=120, time_limit=180, name="app.tasks.regrade_polymarket_under_signflip")
def regrade_polymarket_under_signflip(self):
    """#145 Item 1: run the #137 Polymarket Under/No sign-flip re-grade as a
    DEDICATED task. It was a backfill_winners phase positioned AFTER
    calibration_prices, but that pipeline hits its 840s budget guard and returns
    partial (stopped_before=calibration_prices) BEFORE the #137 integrity block
    ever runs — so the regrade applied 0 despite ~36K rows matching in prod. This
    single cheap set-based UPDATE (flips cp AND opening, so it's durable against a
    later cal-price fallback) drains the class reliably each cycle. Idempotent."""
    from app.tasks.backfill_winners import _regrade_polymarket_under_signflip
    return _tracked_run("poly_under_signflip", _regrade_polymarket_under_signflip())


@celery_app.task(bind=True, soft_time_limit=120, time_limit=180, name="app.tasks.unresolve_datagolf_premature")
def unresolve_datagolf_premature(self):
    """#146 Item 2: starvation sibling of the #145 poly flip. The #137
    calibration-integrity block runs AFTER calibration_prices, which the
    backfill_winners budget guard stops before — so this un-resolve of
    prematurely-resolved DataGolf markets never runs in prod. Dedicated task;
    cheap idempotent set-based UPDATE."""
    from app.tasks.backfill_winners import _unresolve_datagolf_premature
    return _tracked_run("datagolf_premature_unresolve", _unresolve_datagolf_premature())


@celery_app.task(bind=True, soft_time_limit=120, time_limit=180, name="app.tasks.null_impossible_both_sides_openings")
def null_impossible_both_sides_openings(self):
    """#146 Item 2: starvation sibling of the #145 poly flip (same budget guard).
    Nulls impossible both-sides=1.0 binary openings/cp that poison the calibration
    curve. Dedicated task; cheap idempotent set-based UPDATE."""
    from app.tasks.backfill_winners import _null_impossible_both_sides_openings
    return _tracked_run("impossible_both_sides_null", _null_impossible_both_sides_openings())


@celery_app.task(bind=True, soft_time_limit=120, time_limit=180, name="app.tasks.correct_both_winner_guess_side")
def correct_both_winner_guess_side(self):
    """#997: starvation sibling of the #146 integrity beats. Demotes the tier-0
    guess side of a both-winner mutually-exclusive binary to loser when a
    strictly-higher authority sibling already won. The in-drain call is
    budget-guarded out on heavy cycles, so this dedicated beat guarantees it
    runs. Cheap idempotent set-based UPDATE."""
    from app.tasks.backfill_winners import _correct_both_winner_guess_side
    return _tracked_run("both_winner_guess_flip", _correct_both_winner_guess_side())


@celery_app.task(bind=True, soft_time_limit=900, time_limit=960, name="app.tasks.kalshi_cliff_drain")
def kalshi_cliff_drain(self, limit: int = 400):
    """#1586 (queue 355): fetch-now-or-never Kalshi price history.

    Oldest-first INSIDE the 86-day retention floor (both bounds — gotcha #41),
    resumable through a Redis watermark so outcomes that yield nothing are
    passed permanently instead of re-ground every run. ~7,800 markets cross the
    cliff each week and nothing recovers them afterwards."""
    import time as _time

    from app.tasks.kalshi_cliff import run_cliff_drain

    # Leave the soft limit a margin: the drain banks its watermark at the
    # deadline, so a truncated run is resumable rather than lost.
    return _tracked_run(
        "kalshi_cliff_drain",
        run_cliff_drain(limit=limit, deadline=_time.monotonic() + 780),
    )


@celery_app.task(
    bind=True,
    soft_time_limit=900,
    time_limit=960,
    name="app.tasks.run_settlement_sweep",
)
def run_settlement_sweep(self, budget: int = 0, concurrency: int = 0):
    """#2077 (queue 419): drain the settlement-capture backlog on a schedule.

    The runner is certified and unchanged — CERT-405 / `C-CAPTURE-AUTH-BACKOFF-1`
    GREEN, `C-CAPTURE-LIVELOCK-1` GREEN — and it has fired twice in production,
    3,000 rows each night with `rate_limited` 0. Both fires happened because a
    person pasted a `heroku run:detached` line. This is that line, on beat.

    Nothing here plans, queries or writes: it opens a session and calls
    `run_sweep`. Full reasoning — why no explicit sweep label is passed, why the
    deadline sits inside the soft limit, and why the four terminals must survive
    the wrapper — is in `app/tasks/settlement_sweep`, with a gate per property in
    `tests/test_settlement_sweep_beat.py`.
    """
    from app.services.settlement_sweep_runner import DEFAULT_BUDGET, DEFAULT_CONCURRENCY
    from app.tasks.settlement_sweep import SWEEP_DEADLINE_S, _run_settlement_sweep

    return _tracked_run(
        "settlement_sweep",
        _run_settlement_sweep(
            budget=budget or DEFAULT_BUDGET,
            concurrency=concurrency or DEFAULT_CONCURRENCY,
            deadline_s=SWEEP_DEADLINE_S,
        ),
    )


@celery_app.task(bind=True, soft_time_limit=600, time_limit=660, name="app.tasks.backfill_kalshi_candlestick")
def backfill_kalshi_candlestick(self, limit: int = 500):
    """Backfill hourly snapshots from Kalshi candlestick API for sparse outcomes."""
    from app.tasks.kalshi import _backfill_candlestick_snapshots
    return _tracked_run("kalshi_candlestick", _backfill_candlestick_snapshots(limit))


@celery_app.task(bind=True, soft_time_limit=600, time_limit=660, name="app.tasks.backfill_kalshi_volume")
def backfill_kalshi_volume(self):
    """Fast volume-only backfill — skips all phases except volume writes."""
    from app.tasks.kalshi import _backfill_volume_only
    return _tracked_run("kalshi_volume", _backfill_volume_only())


@celery_app.task(bind=True, soft_time_limit=600, time_limit=660, name="app.tasks.backfill_kalshi_trades")
def backfill_kalshi_trades(self, limit: int = 500):
    """Backfill snapshots from Kalshi trade history for outcomes missing cal_prob."""
    from app.tasks.kalshi import _backfill_trade_history
    return _tracked_run("kalshi_trades", _backfill_trade_history(limit))


@celery_app.task(bind=True, soft_time_limit=840, time_limit=900, name="app.tasks.backfill_polymarket_winners")
def backfill_polymarket_winners(self, limit: int = 10000):
    """Resolve Polymarket winners from Gamma API settlement data."""
    from app.tasks.backfill_winners import _backfill_polymarket_winners_from_api
    return _tracked_run("polymarket_winners", _backfill_polymarket_winners_from_api(limit))


@celery_app.task(bind=True, soft_time_limit=840, time_limit=900, name="app.tasks.clob_resolve_drain")
def clob_resolve_drain(self, limit: int = 300, dry_run: bool = False):
    """#989: authoritatively re-resolve the curve-dropped Polymarket cohort
    (pass2_loser/all_losers) via the CLOB API. Writes is_winner with
    resolution_source='clob_authoritative' for the confident resolved_direct /
    resolved_name_match tiers only; void/ambiguous stay excluded. Cursor-resumable."""
    from app.tasks.clob_resolve import (
        clob_resolve_drain as _drain,
        _DEFAULT_WRITE_TIERS,
    )
    # Amendment 1 — ordinal tier CAPPED ENABLE (#989 Item 2, Queue #124). Batch-0
    # PASSED (25/25 label-agree, 0 disagreements, vintage-stratified). Enable the
    # ordinal tier in the beat, capped at _ORDINAL_FIRST_BATCH_CAP=2,000 cumulative
    # writes (Redis-tracked; the drain stops writing ordinal once the cap is hit).
    # The cap holds until winrate + curve stability are verified on the first
    # ≤2,000; uncapping for the full ~15K drain is a deliberate later step.
    tiers = _DEFAULT_WRITE_TIERS + ("resolved_ordinal",)
    return _tracked_run("clob_resolve_drain", _drain(
        limit=limit, dry_run=dry_run, write_tiers=tiers, enable_ordinal=True,
    ))


# --- Categorization ---

@celery_app.task(bind=True, name="app.tasks.categorize_futures")
def categorize_futures_task(self, limit: int = 100, force_llm: bool = False):
    """Categorize uncategorized futures markets (background task)."""
    from app.tasks.futures import _categorize_futures_impl
    return run_async(_categorize_futures_impl(limit, force_llm))


@celery_app.task(bind=True, soft_time_limit=900, time_limit=960, name="app.tasks.recategorize_other")
def recategorize_other_task(self, limit: int = 500, from_category: str = None):
    """Re-run rules on 'other' (or specified category) markets to fix miscategorizations."""
    from app.tasks.futures import _recategorize_other_impl
    return run_async(_recategorize_other_impl(limit, from_category=from_category))


@celery_app.task(bind=True, soft_time_limit=900, time_limit=960, name="app.tasks.regenerate_tags")
def regenerate_tags_task(self, limit: int = 5000, category: str = None):
    """Regenerate category_tags for existing markets using current patterns."""
    from app.tasks.futures import _regenerate_tags_impl
    return run_async(_regenerate_tags_impl(limit, category=category))


@celery_app.task(bind=True, name="app.tasks.mark_resolved_futures")
def mark_resolved_futures(self):
    """Mark futures markets as resolved when their resolution_date has passed."""
    from app.tasks.futures import _mark_resolved_impl
    return run_async(_mark_resolved_impl())


@celery_app.task(bind=True, name="app.tasks.resolve_winners", soft_time_limit=540, time_limit=600)
def resolve_winners(self, limit: int = 2000):
    """RETIRED from the beat schedule 2026-07-06 (#991) — kept dormant/registered
    for a cheap re-add, NOT currently dispatched. See the retirement note at the
    'backfill-historical-links' beat entry for the bounded re-add path.

    Dedicated winner resolution — API settlement + score-based only.

    Runs independently from the full backfill_winners pipeline, which
    spends most of its 14-min budget on calibration price computation,
    DataGolf leaderboards, golf/hockey commence_time fixes, and other
    non-resolution work. This task focuses solely on resolving is_winner
    from authoritative sources.
    """
    from app.tasks.backfill_winners import _resolve_winners_only
    return _tracked_run("resolve_winners", _resolve_winners_only(limit=limit))


@celery_app.task(bind=True, name="app.tasks.backfill_winners", soft_time_limit=840, time_limit=900)
def backfill_winners(self, dry_run: bool = False, limit: int = 2000):
    """Backfill is_winner on FuturesOutcome from Kalshi settlement + Polymarket resolution."""
    from app.tasks.backfill_winners import _backfill_all_winners
    return _tracked_run("backfill_winners", _backfill_all_winners(dry_run=dry_run, limit=limit))

@celery_app.task(bind=True, name="app.tasks.check_snapshot_sparsity", soft_time_limit=600, time_limit=660)
def check_snapshot_sparsity(self):
    """Daily check for sparse snapshot events + auto-backfill from historical API."""
    from app.tasks.snapshot_sparsity import check_and_backfill_sparse_snapshots
    try:
        result = _tracked_run("check_snapshot_sparsity", check_and_backfill_sparse_snapshots())
        return result
    except Exception as exc:
        logger.exception("check_snapshot_sparsity failed")
        raise self.retry(exc=exc, countdown=300)


@celery_app.task(bind=True, name="app.tasks.backfill_historical_odds", soft_time_limit=1800, time_limit=1860)
def backfill_historical_odds_task(self, sport: str = "baseball_mlb", days_back: int = 30, max_events: int = 500):
    """Backfill sparse events from The Odds API historical endpoint. Runs in background."""
    from app.tasks.snapshot_sparsity import _backfill_historical_for_sport
    try:
        result = _tracked_run(
            "backfill_historical_odds",
            _backfill_historical_for_sport(sport=sport, days_back=days_back, max_events=max_events),
        )
        return result
    except Exception as exc:
        logger.exception("backfill_historical_odds failed for %s", sport)
        raise self.retry(exc=exc, countdown=60, max_retries=1)


@celery_app.task(bind=True, name="app.tasks.lookup_and_backfill_extids", soft_time_limit=1800, time_limit=1860)
def lookup_and_backfill_extids_task(self, sport: str = "baseball_mlb", days_back: int = 30, max_events: int = 50):
    """Find events without external_id, look them up in historical API, link and backfill."""
    from app.tasks.snapshot_sparsity import _lookup_and_backfill_missing_extids
    try:
        result = _tracked_run(
            "lookup_and_backfill_extids",
            _lookup_and_backfill_missing_extids(sport=sport, days_back=days_back, max_events=max_events),
        )
        return result
    except Exception as exc:
        logger.exception("lookup_and_backfill_extids failed for %s", sport)
        raise self.retry(exc=exc, countdown=60, max_retries=1)






@celery_app.task(bind=True, name="app.tasks.backfill_historical_links", soft_time_limit=300, time_limit=360)
def backfill_historical_links(self, batch_size: int = 100):
    """Link past-game Kalshi markets to their closed/completed events."""
    from app.tasks.prediction_market_matching import _backfill_historical_links
    return run_async(_backfill_historical_links(batch_size=batch_size))


@celery_app.task(bind=True, name="app.tasks.fix_outcome_names")
def fix_outcome_names(self):
    """Fix Polymarket outcome names using groupItemTitle from Gamma API."""
    from app.tasks.futures import _fix_outcome_names_impl
    return run_async(_fix_outcome_names_impl())


# --- ESPN ---

@celery_app.task(bind=True, name="app.tasks.enrich_events_metadata")
def enrich_events_metadata(self, limit: int = 50):
    """Enrich events with LLM-generated metadata."""
    from app.tasks.espn_sync import _enrich_events_metadata
    return run_async(_enrich_events_metadata(limit))


@celery_app.task(bind=True, name="app.tasks.sync_espn_live_events")
def sync_espn_live_events(self):
    """Sync live event data from ESPN for all sports with active games."""
    from app.tasks.espn_sync import _sync_espn_live_events
    return _tracked_run("espn_sync", _sync_espn_live_events())


@celery_app.task(bind=True, name="app.tasks.backfill_team_logos")
def backfill_team_logos(self):
    """Fetch all teams from ESPN's /teams endpoint and fill in missing logos."""
    from app.tasks.espn_sync import _backfill_team_logos
    return run_async(_backfill_team_logos())


@celery_app.task(bind=True, soft_time_limit=900, time_limit=960, name="app.tasks.ensure_perf_indexes")
def ensure_perf_indexes(self):
    """#1197: build the missing team-route event indexes CONCURRENTLY at runtime
    (gotcha #31 — never in a migration). High time limit: CONCURRENTLY on the
    events table can take a while; idempotent (IF NOT EXISTS)."""
    from app.utils.ensure_indexes import ensure_perf_indexes as _run
    return run_async(_run())


@celery_app.task(bind=True, name="app.tasks.cleanup_bad_espn_matches")
def cleanup_bad_espn_matches(self):
    """Validate existing ESPN ID assignments and clear bad matches."""
    from app.tasks.espn_sync import _cleanup_bad_espn_matches
    return run_async(_cleanup_bad_espn_matches())


@celery_app.task(bind=True, name="app.tasks.backfill_box_scores")
def backfill_box_scores(self, limit: int = 100, priority_calibration: bool = False):
    """Fetch ESPN box scores for completed events missing box_score_data."""
    from app.tasks.espn_sync import _backfill_box_scores
    return _tracked_run("backfill_box_scores", _backfill_box_scores(limit=limit, priority_calibration=priority_calibration))


@celery_app.task(bind=True, name="app.tasks.backfill_espn_ids")
def backfill_espn_ids(self, limit: int = 1000):
    """Match completed events to ESPN IDs for box score backfilling."""
    from app.tasks.espn_sync import _backfill_espn_ids
    return run_async(_backfill_espn_ids(limit=limit))


@celery_app.task(bind=True, soft_time_limit=300, time_limit=360, name="app.tasks.sync_tennis_from_espn")
def sync_tennis_from_espn(self, limit: int = 1000, dates: str = None):
    """Anchor tennis events to ESPN competitions and let ESPN write their state.

    The sport `espn_sync` never covered: zero of 30,199 tennis rows carried an
    `espn_id` on 2026-09-02, so the authority had no channel to correct a tennis
    fixture and a wall-clock staleness net corrected it instead — three US Open
    rows holding `live` and a `completed_at` at once. lane1/057 STEP 0.
    """
    from app.tasks.espn_sync import _sync_tennis_from_espn
    return _tracked_run("tennis_espn_sync", _sync_tennis_from_espn(limit=limit, dates=dates))


@celery_app.task(bind=True, soft_time_limit=45, time_limit=60, name="app.tasks.poll_live_tennis_scores")
def poll_live_tennis_scores(self, limit: int = 200):
    """Move the live tennis card at ESPN's grain — every published game.

    live/058 / #2746. The sibling above owns the LINK and runs every 10 minutes;
    this owns the SCORE and runs every 20 seconds, which it can afford because
    it does none of the anchor's work — it reads already-anchored rows by
    `espn_id` and writes `linescore` plus the set count off one board.

    Timeboxed hard (45s soft) so a slow ESPN read can never overlap its own next
    beat on the realtime queue.
    """
    from app.tasks.espn_sync import _poll_live_tennis_scores
    return _tracked_run("live_tennis_scores", _poll_live_tennis_scores(limit=limit))


@celery_app.task(bind=True, soft_time_limit=600, time_limit=660, name="app.tasks.backfill_espn_win_prob")
def backfill_espn_win_prob(self, limit: int = 200, oldest_first: bool = False):
    """Backfill ESPN win probability history for completed events with sparse snapshots.

    oldest_first=True reaches the OLD tail the newest-first pass starves (gotcha #41).
    """
    from app.tasks.espn_sync import _backfill_espn_win_probability
    return _tracked_run("espn_win_prob_backfill", _backfill_espn_win_probability(limit, oldest_first))


@celery_app.task(bind=True, soft_time_limit=300, time_limit=360, name="app.tasks.compute_game_moments")
def compute_game_moments(self, limit: int = 60):
    """THE MOMENTS ENGINE (#1168): join scoring plays to win-prob swings for
    recently-completed MLB games, persist confident moments, and report the MLB
    ground-truth agreement rate. Soft limit set because it makes per-event MLB API
    calls (gotcha #51)."""
    from app.tasks.game_moments import _compute_game_moments
    return _tracked_run("game_moments", _compute_game_moments(limit=limit))


# --- Team Linking (Futures → Teams) ---

@celery_app.task(bind=True, name="app.tasks.backfill_team_links")
def backfill_team_links(self, limit: int = 200, use_llm: bool = True):
    """Backfill team_id on futures outcomes and market_tier on futures markets."""
    from app.tasks.team_linking import _backfill_team_links
    return run_async(_backfill_team_links(limit, use_llm))


@celery_app.task(bind=True, name="app.tasks.backfill_canonical_keys")
def backfill_canonical_keys(self, limit: int = 500):
    """Backfill canonical_market_key and llm_league on futures markets."""
    from app.tasks.team_linking import _backfill_canonical_keys
    return run_async(_backfill_canonical_keys(limit))


@celery_app.task(
    bind=True,
    name="app.tasks.backfill_market_shapes",
    time_limit=660,
    soft_time_limit=600,
)
def backfill_market_shapes(self, limit: int = 40000, dry_run: bool = False):
    """Classify + persist market shape into market_type (Queue #194 Item 1).

    Bounded/resumable/deadline-guarded. Only touches market_type IS NULL rows,
    so it also shapes freshly-ingested markets each run."""
    from app.tasks.backfill_market_shapes import _backfill_market_shapes
    return _tracked_run(
        "market_shape_backfill",
        _backfill_market_shapes(limit=limit, dry_run=dry_run),
    )


# --- Prediction Market → Event Matching ---

@celery_app.task(bind=True, name="app.tasks.match_prediction_markets", time_limit=870, soft_time_limit=840)
def match_prediction_markets(self, limit: int = 500):
    """Match game-level prediction markets to events and write win_prob_snapshots."""
    from app.tasks.prediction_market_matching import _match_prediction_markets
    return _tracked_run("prediction_market_match", _match_prediction_markets(limit))


@celery_app.task(bind=True, name="app.tasks.poll_live_prediction_markets")
def poll_live_prediction_markets(self):
    """Fast-poll prices for prediction markets linked to live events (every 2 min)."""
    from app.tasks.prediction_market_matching import _poll_live_prediction_market_prices
    return _tracked_run("prediction_market_live", _poll_live_prediction_market_prices())


@celery_app.task(bind=True, name="app.tasks.backfill_polymarket_win_prob")
def backfill_polymarket_win_prob(self, market_id: int, event_id: int):
    """Backfill win_prob_snapshots from Polymarket CLOB price history."""
    from app.tasks.prediction_market_matching import _backfill_polymarket_win_prob_history
    return run_async(_backfill_polymarket_win_prob_history(market_id, event_id))


# --- MLB Live Win Probability ---

@celery_app.task(bind=True, name="app.tasks.sync_mlb_win_probability")
def sync_mlb_win_probability(self):
    """Sync live MLB win probabilities from the MLB Stats API (every 2 min during games)."""
    from app.tasks.mlb_sync import _sync_mlb_win_probability
    return _tracked_run("mlb_sync", _sync_mlb_win_probability())


@celery_app.task(bind=True, soft_time_limit=240, time_limit=300, name="app.tasks.mlb_schedule_coverage")
def mlb_schedule_coverage(self):
    """#1201/#1193/#1202: daily MLB schedule self-heal + coverage. Repairs the
    standing inverted / future-settled rows (gotcha #32/#46) via MLB ground truth,
    then runs the read-only coverage check so the 07:10 Flow Sentinel resolved_state
    reads a clean slate. Heavy queue (#233) — cheap, daily, must fire promptly."""
    from app.tasks.schedule_coverage import run_mlb_schedule_coverage_and_repair
    return _tracked_run("mlb_schedule_coverage", run_mlb_schedule_coverage_and_repair())


# --- Roster Sync (ESPN + MLB Stats API) ---

@celery_app.task(bind=True, name="app.tasks.sync_rosters", time_limit=300, soft_time_limit=270)
def sync_rosters(self, sport_key: str = None):
    """Sync player rosters from ESPN + MLB Stats API to Team.roster_players."""
    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"sync_rosters starting (sport_key={sport_key})")
    from app.tasks.roster_sync import _sync_rosters
    result = run_async(_sync_rosters(sport_key))
    logger.info(f"sync_rosters completed: {result}")
    return result


# --- StatPal (Schedules, Injuries, Play-by-Play) ---

@celery_app.task(bind=True, name="app.tasks.sync_statpal_schedules")
def sync_statpal_schedules(self, sport_key: str = None):
    """Sync fixture schedules from StatPal — corrects commence_time, populates end_time."""
    from app.tasks.statpal_sync import _sync_statpal_schedules
    return _tracked_run("statpal_schedules", _sync_statpal_schedules(sport_key))


@celery_app.task(bind=True, name="app.tasks.sync_statpal_injuries")
def sync_statpal_injuries(self, sport_key: str = None):
    """Sync injury reports from StatPal for line movement context."""
    from app.tasks.statpal_sync import _sync_statpal_injuries
    return _tracked_run("statpal_injuries", _sync_statpal_injuries(sport_key))


@celery_app.task(bind=True, name="app.tasks.sync_statpal_live_plays")
def sync_statpal_live_plays(self, sport_key: str = None):
    """Fetch play-by-play data from StatPal for live games."""
    from app.tasks.statpal_sync import _sync_statpal_live_plays
    return _tracked_run("statpal_plays", _sync_statpal_live_plays(sport_key))


@celery_app.task(bind=True, name="app.tasks.enrich_market_images")
def enrich_market_images(self, limit: int = 50):
    """Fetch images from Pexels API for markets missing image_url."""
    from app.tasks.enrich_markets import enrich_market_images as _enrich
    return _tracked_run("enrich_images", _enrich(limit))


@celery_app.task(
    bind=True,
    name="app.tasks.enrich_tmdb_images",
    soft_time_limit=300,
    time_limit=360,
)
def enrich_tmdb_images(self, limit: int = 50):
    """#882: real TMDB artwork for quoted-title entertainment markets."""
    from app.tasks.enrich_tmdb import enrich_tmdb_images as _enrich
    return _tracked_run("enrich_tmdb", _enrich(limit))


@celery_app.task(
    bind=True,
    name="app.tasks.backfill_image_dimensions",
    soft_time_limit=300,
    time_limit=360,
)
def backfill_image_dimensions(self, limit: int = 150):
    """True pixel size for artwork enriched before those columns existed."""
    from app.tasks.image_dimensions_backfill import (
        backfill_image_dimensions as _backfill,
    )
    return _tracked_run("backfill_image_dims", _backfill(limit))


@celery_app.task(
    bind=True,
    name="app.tasks.enrich_market_hooks",
    soft_time_limit=600,
    time_limit=660,
)
def enrich_market_hooks(self, limit: int = 50):
    """Generate LLM hook descriptions for markets missing hook_description.

    #967 (same class as #966): this makes up to `limit` sequential OpenAI calls,
    so the batch can exceed the GLOBAL 300s ``task_time_limit`` (a HARD limit →
    SIGKILL, which is NOT a catchable exception → ``_tracked_run`` records
    neither success nor failure → silent ``no_data``). Mirror the working
    ``enrich_cu_v2_profiles``: a 600s SOFT limit raises a catchable
    SoftTimeLimitExceeded (overruns are recorded + free the slot) under a 660s
    hard limit that gives the batch room to finish.
    """
    from app.tasks.enrich_markets import enrich_market_hooks as _enrich
    return _tracked_run("enrich_hooks", _enrich(limit))


@celery_app.task(
    bind=True,
    name="app.tasks.enrich_discover_llm_metadata",
    soft_time_limit=600,
    time_limit=660,
)
def enrich_discover_llm_metadata(self, limit: int = 100):
    """Generate cached structured LLM metadata for Discover candidates.

    #966: this task makes up to `limit` sequential OpenAI calls (30s client
    timeout each), so the batch routinely exceeds the GLOBAL 300s
    ``task_time_limit`` (a HARD limit → Celery SIGKILLs the worker child).
    SIGKILL is not a catchable Python exception, so ``_tracked_run`` recorded
    neither success nor failure and the task sat at ``no_data`` for ~40h while
    the enrichment backlog froze. Mirror the working sibling
    ``enrich_cu_v2_profiles``: a 600s SOFT limit raises a catchable
    SoftTimeLimitExceeded (an overrun is recorded as a failure and frees the
    worker slot) under a 660s hard limit that gives the LLM batch room to finish.
    """
    from app.tasks.enrich_markets import enrich_discover_llm_metadata as _enrich
    return _tracked_run("enrich_discover_llm", _enrich(limit))


@celery_app.task(bind=True, name="app.tasks.enrich_cu_v2_profiles", soft_time_limit=600, time_limit=660)
def enrich_cu_v2_profiles(self, limit: int = 125):
    """Generate Content Understanding v2 profiles for feed-shaped markets."""
    from app.tasks.enrich_markets import enrich_cu_v2_profiles as _enrich
    return _tracked_run("enrich_cu_v2", _enrich(limit))


@celery_app.task(bind=True, name="app.tasks.enrich_snippet_angles", soft_time_limit=300, time_limit=360)
def enrich_snippet_angles(self, limit: int = 125):
    """Compute and cache snippet angles for feed-shaped markets."""
    from app.tasks.enrich_markets import enrich_snippet_angles as _enrich
    return _tracked_run("enrich_snippet_angles", _enrich(limit))


@celery_app.task(bind=True, name="app.tasks.generate_discover_comparison_candidates")
def generate_discover_comparison_candidates(self, limit: int = 60):
    """Generate cached cross-category comparison-game candidates."""
    from app.tasks.enrich_markets import generate_discover_comparison_candidates as _generate
    return _tracked_run("discover_comparisons", _generate(limit))


@celery_app.task(bind=True, name="app.tasks.evaluate_discover_with_llm")
def evaluate_discover_with_llm(self, limit: int = 50):
    """Grade Discover cards daily and log LLM proposals for admin review."""
    from app.tasks.enrich_markets import evaluate_discover_with_llm as _evaluate
    return _tracked_run("discover_llm_eval", _evaluate(limit))


@celery_app.task(bind=True, name="app.tasks.snapshot_discover_ground_truth_diagnostics")
def snapshot_discover_ground_truth_diagnostics(self, limit: int = 50):
    """Persist advisory Discover ground-truth hit/miss diagnostics."""
    from app.utils.discover_ground_truth_diagnostics import (
        DEFAULT_FEED_URL,
        build_diagnostic_rows_from_debug_payload,
        fetch_debug_payload,
        persist_diagnostic_rows,
    )

    admin_secret = os.getenv("ADMIN_TOKEN")
    if not admin_secret:
        return {"status": "skipped", "reason": "ADMIN_TOKEN missing"}

    feed_url = os.getenv("DISCOVER_GROUND_TRUTH_SNAPSHOT_FEED_URL", DEFAULT_FEED_URL)
    payload = fetch_debug_payload(
        feed_url=feed_url,
        admin_secret=admin_secret,
        limit=limit,
    )
    rows = build_diagnostic_rows_from_debug_payload(payload)
    inserted = _tracked_run(
        "discover_gt_diagnostics",
        persist_diagnostic_rows(rows),
    )
    return {
        "status": "ok",
        "inserted": inserted,
        "limit": limit,
        "feed_url": feed_url,
    }


@celery_app.task(bind=True, name="app.tasks.snapshot_discover_label_eval_run")
def snapshot_discover_label_eval_run(
    self,
    days: int = 30,
    top_k: int = 20,
    limit: int = 5000,
    surface: str | None = None,
    reviewer: str | None = None,
):
    """Persist advisory Discover human-label eval metrics."""
    from app.services.database import async_session_maker
    from app.utils.discover_label_eval_runs import (
        snapshot_discover_label_eval_run as _snapshot_label_eval_run,
    )

    async def _snapshot():
        async with async_session_maker() as db:
            run = await _snapshot_label_eval_run(
                db,
                days=days,
                top_k=top_k,
                limit=limit,
                surface=surface,
                reviewer=reviewer,
            )
            return {
                "status": run.status,
                "run_id": run.run_id,
                "row_count": run.row_count,
                "top_k": run.top_k,
            }

    return _tracked_run("discover_label_eval_snapshot", _snapshot())


@celery_app.task(bind=True, name="app.tasks.snapshot_discover_candidate_pool")
def snapshot_discover_candidate_pool(
    self,
    limit: int = 300,
    retention_days: int = 30,
):
    """Persist the pre-ranking Discover candidate pool for offline replay (#142)."""
    from app.services.database import async_session_maker
    from app.utils.discover_candidate_snapshot import (
        snapshot_discover_candidate_pool as _snapshot_candidate_pool,
    )

    async def _snapshot():
        async with async_session_maker() as db:
            return await _snapshot_candidate_pool(
                db,
                limit=limit,
                retention_days=retention_days,
            )

    return _tracked_run("discover_candidate_snapshot", _snapshot())


@celery_app.task(bind=True, name="app.tasks.import_external_curator_ground_truth")
def import_external_curator_ground_truth(self):
    """Persist configured reviewed external-curator/social ground truth."""
    from app.tasks.base import get_task_session
    from app.utils.external_curator_ground_truth import (
        load_external_curator_ground_truth_report_from_env,
    )
    from app.utils.persisted_external_curator_ground_truth import (
        import_external_curator_ground_truth_rows,
    )

    report = load_external_curator_ground_truth_report_from_env()

    async def _persist():
        async with get_task_session() as session:
            result = await import_external_curator_ground_truth_rows(
                session,
                report["items"],
            )
        return {
            "status": "ok" if report["metadata"].get("configured") else "skipped",
            "metadata": report["metadata"],
            **result,
        }

    return _tracked_run("external_curator_gt_import", _persist())


@celery_app.task(bind=True, name="app.tasks.capture_featured_markets")
def capture_featured_markets(self):
    """Daily capture of top-volume Kalshi/Polymarket markets as featured proxy."""
    from app.tasks.base import get_task_session
    from app.utils.featured_market_capture import capture_all_featured

    async def _capture():
        async with get_task_session() as session:
            return await capture_all_featured(session)

    return _tracked_run("capture_featured_markets", _capture())


@celery_app.task(bind=True, name="app.tasks.check_ground_truth_health")
def check_ground_truth_health(self):
    """Record daily health for advisory Discover ground-truth sources."""
    from app.utils.external_curator_ground_truth import (
        load_external_curator_ground_truth_report_from_env,
    )
    from app.utils.ground_truth_health import (
        assess_ground_truth_report_health,
        summarize_ground_truth_health,
    )
    from app.utils.polymarket_email_ground_truth import (
        load_polymarket_email_ground_truth_report_from_env,
    )

    email_report = load_polymarket_email_ground_truth_report_from_env()
    curator_report = load_external_curator_ground_truth_report_from_env()
    result = summarize_ground_truth_health(
        [
            assess_ground_truth_report_health(
                email_report,
                label="polymarket_email",
            ),
            assess_ground_truth_report_health(
                curator_report,
                label="external_curator",
            ),
        ]
    )

    async def _result():
        return result

    return _tracked_run("ground_truth_health", _result())


@celery_app.task(
    bind=True,
    name="app.tasks.precompute_interestingness",
    soft_time_limit=240,
)
def precompute_interestingness(self):
    """Precompute market interestingness scores and cache in Redis (every 2h).

    ``soft_time_limit`` is DEFENCE, NOT THE FIX (LAT-P042, #1716). This task was
    hard-killed 6/6 runs and the standing diagnosis blamed the global hard
    ``task_time_limit=300``; measurement says otherwise — the pass takes ~15s
    and dies at **515 MB RSS** on a 512 MB ``worker-background`` dyno. The real
    repair is the keyset chunking in ``tasks/precompute_interestingness.py``.

    The soft limit is still worth having, because it is the difference between
    a future overrun that RAISES ``SoftTimeLimitExceeded`` — catchable, and
    recorded by the end handler — and one that vanishes into a SIGKILL with no
    duration, no failure, and no terminal, which is the state that let this go
    unnoticed for months. 240s leaves 60s of headroom under the hard limit for
    the handler to actually run.
    """
    from app.tasks.precompute_interestingness import _precompute_interestingness
    return _tracked_run("precompute_interestingness", _precompute_interestingness())


@celery_app.task(bind=True, name="app.tasks.check_aggregation_quality")
def check_aggregation_quality(self):
    """Daily: sample events, measure source diversity, alert on single-source spikes."""
    from app.tasks.monitoring import check_aggregation_quality as _check
    return _tracked_run("aggregation_quality", _check())


@celery_app.task(bind=True, name="app.tasks.sync_statpal_livescores")
def sync_statpal_livescores(self):
    """Poll StatPal livescores for real-time game state (every 30s)."""
    from app.tasks.statpal_sync import _sync_statpal_livescores
    return _tracked_run("statpal_livescores", _sync_statpal_livescores())


@celery_app.task(bind=True, name="app.tasks.sync_statpal_rosters")
def sync_statpal_rosters(self, sport_key: str = None):
    """Sync team rosters from StatPal (supplements ESPN roster data)."""
    from app.tasks.statpal_sync import _sync_statpal_rosters
    return run_async(_sync_statpal_rosters(sport_key))


@celery_app.task(bind=True, name="app.tasks.sync_statpal_standings")
def sync_statpal_standings(self, sport_key: str = None):
    """Sync league standings from StatPal."""
    from app.tasks.statpal_sync import _sync_statpal_standings
    return _tracked_run("statpal_standings", _sync_statpal_standings(sport_key))


@celery_app.task(bind=True, name="app.tasks.sync_statpal_team_stats")
def sync_statpal_team_stats(self, sport_key: str = None):
    """Sync season-level team statistics from StatPal."""
    from app.tasks.statpal_sync import _sync_statpal_team_stats
    return _tracked_run("statpal_team_stats", _sync_statpal_team_stats(sport_key))


# --- Daily Digest ---

@celery_app.task(bind=True, name="app.tasks.send_daily_digest")
def send_daily_digest_task(self):
    """Send daily digest email to subscribers."""
    import os
    async def _send():
        from app.tasks.base import get_task_session
        from app.tasks.daily_digest import send_daily_digest
        recipients = os.environ.get("DAILY_DIGEST_RECIPIENTS", "").split(",")
        recipients = [r.strip() for r in recipients if r.strip()]
        if not recipients:
            return {"status": "no_recipients"}
        async with get_task_session() as db:
            results = {}
            for email in recipients:
                results[email] = await send_daily_digest(db, email)
            return results
    return run_async(_send())


@celery_app.task(bind=True, max_retries=3, name="app.tasks.send_bug_fixed_email")
def send_bug_fixed_email_task(self, report_id: int):
    """Send a fixed-bug notification email for one bug report."""

    async def _send():
        from app.tasks.base import get_task_session
        from app.tasks.bug_notifications import send_bug_fixed_email

        async with get_task_session() as db:
            return await send_bug_fixed_email(report_id, db)

    try:
        return run_async(_send())
    except Exception as exc:
        raise self.retry(exc=exc, countdown=60)


# --- Bug Report → GitHub Issue ---

@celery_app.task(bind=True, max_retries=2, name="app.tasks.create_github_issue_for_bug_report")
def create_github_issue_for_bug_report_task(self, report_id: int):
    """Create a GitHub Issue from a rage-shake bug report."""

    async def _create():
        from app.tasks.base import get_task_session
        from app.tasks.bug_report_github import (
            GITHUB_TOKEN, build_labels, compute_severity,
            create_github_issue, format_issue_body, format_issue_title,
            add_to_project_board, is_owner_email, should_file_individual_issue,
            compute_fingerprint, comment_on_issue, FRONTEND_URL,
        )
        from app.models.models import BugReport
        from sqlalchemy import select, update as sa_update
        from datetime import datetime as _dt, timedelta as _td, timezone as _tz

        if not GITHUB_TOKEN:
            logger.warning("GITHUB_TOKEN not set — skipping issue creation for report #%d", report_id)
            return None

        async with get_task_session() as db:
            report = await db.get(BugReport, report_id)
            if not report:
                logger.error("Bug report #%d not found", report_id)
                return None

            if report.backlog_ref:
                logger.info("Bug report #%d already linked to %s — skipping", report_id, report.backlog_ref)
                return None

            if not report.description and not report.screenshot_base64:
                logger.info("Bug report #%d has no description and no screenshot — skipping", report_id)
                return None

            # #885: reporter provenance + routing. Owner reports always file an
            # individual issue; a non-owner feature-request / product
            # misunderstanding is taken "with a grain of salt" — NOT filed
            # individually (it remains in the admin staging archive). Bugs from
            # anyone are filed and severity-labeled.
            is_owner = is_owner_email(report.user_email)
            if not should_file_individual_issue(report.category, is_owner):
                logger.info(
                    "Bug report #%d is an external '%s' (non-bug) — skipping "
                    "individual GitHub issue per #885 routing; kept in staging.",
                    report_id,
                    report.category,
                )
                return {
                    "skipped_routing": True,
                    "report_id": report_id,
                    "category": report.category,
                    "reporter": "external",
                }

            # #975: cross-report dedup. If a DIFFERENT report with the same
            # page+category+diagnosis fingerprint already filed an issue within
            # the last 7 days, comment on it instead of filing a duplicate (a
            # recurring bug accretes evidence on one issue, not N). The existing
            # backlog_ref check only catches the SAME report re-submitted.
            fp = compute_fingerprint(report.app_state, report.category, report.description)
            cutoff = _dt.now(_tz.utc) - _td(days=7)
            recent = await db.execute(
                select(BugReport)
                .where(
                    BugReport.id != report_id,
                    BugReport.backlog_ref.isnot(None),
                    BugReport.created_at >= cutoff,
                )
                .order_by(BugReport.created_at.desc())
                .limit(200)
            )
            for prior in recent.scalars().all():
                ref = (prior.backlog_ref or "").lstrip("#")
                if not ref.isdigit():
                    continue
                if compute_fingerprint(prior.app_state, prior.category, prior.description) != fp:
                    continue
                try:
                    comment_on_issue(
                        int(ref),
                        f"Recurrence: rage-shake report #{report_id} matches this "
                        f"issue's fingerprint (same page + category + diagnosis). "
                        f"[Admin detail]({FRONTEND_URL}/admin/bug-reports)",
                    )
                except Exception:
                    logger.warning(
                        "dedup comment on %s failed — filing a new issue instead",
                        prior.backlog_ref, exc_info=True,
                    )
                    break  # comment failed → fall through to filing a fresh issue
                await db.execute(
                    sa_update(BugReport).where(BugReport.id == report_id).values(backlog_ref=prior.backlog_ref)
                )
                logger.info(
                    "Bug report #%d deduped onto %s (fingerprint %s)",
                    report_id, prior.backlog_ref, fp,
                )
                return {"deduped_onto": prior.backlog_ref, "report_id": report_id, "fingerprint": fp}

            severity = compute_severity(report.description)
            title = format_issue_title(report.description)
            body = format_issue_body(
                report_id=report.id,
                description=report.description,
                category=report.category,
                app_state=report.app_state,
                has_screenshot=bool(report.screenshot_base64),
            )
            labels = build_labels(report.category, severity, is_owner=is_owner)

            issue_number, issue_node_id = create_github_issue(title, body, labels)

            await db.execute(
                sa_update(BugReport).where(BugReport.id == report_id).values(backlog_ref=f"#{issue_number}")
            )
            logger.info("Created GitHub issue #%d for bug report #%d", issue_number, report_id)

            try:
                add_to_project_board(issue_node_id)
            except Exception:
                logger.warning("Failed to add issue #%d to project board (non-fatal)", issue_number, exc_info=True)

            return {"issue_number": issue_number, "report_id": report_id}

    try:
        return run_async(_create())
    except Exception as exc:
        raise self.retry(exc=exc, countdown=60)


@celery_app.task(bind=True, name="app.tasks.digest_external_feature_requests")
def digest_external_feature_requests_task(self):
    """#975: weekly roll-up of external (non-owner) feature-request shakes.

    Per #885 these are NOT filed as individual issues (taken "with a grain of
    salt") — they sit in the admin staging archive with backlog_ref NULL. This
    rolls the past week's batch into ONE digest issue so they're reviewable in
    aggregate, and stamps their backlog_ref to the digest so they aren't
    re-digested next week (reuses the existing column — no migration).
    """

    async def _digest():
        from app.tasks.base import get_task_session
        from app.tasks.bug_report_github import (
            GITHUB_TOKEN, create_github_issue, format_digest_body, is_owner_email,
        )
        from app.utils.issue_labels import priority_label
        from app.models.models import BugReport
        from sqlalchemy import select, update as sa_update
        from datetime import datetime as _dt, timedelta as _td, timezone as _tz

        if not GITHUB_TOKEN:
            logger.warning("GITHUB_TOKEN not set — skipping feature-request digest")
            return {"skipped": "no_token"}

        now = _dt.now(_tz.utc)
        cutoff = now - _td(days=7)
        async with get_task_session() as db:
            result = await db.execute(
                select(BugReport)
                .where(
                    BugReport.category == "feature_request",
                    BugReport.backlog_ref.is_(None),
                    BugReport.created_at >= cutoff,
                )
                .order_by(BugReport.created_at.desc())
                .limit(500)
            )
            rows = result.scalars().all()
            # external-only (owner feature-requests are filed individually, but
            # guard anyway in case provenance changes)
            external = [r for r in rows if not is_owner_email(r.user_email)]
            if not external:
                logger.info("Feature-request digest: nothing external this week")
                return {"digested": 0}

            reports = [
                {
                    "id": r.id,
                    "page": (r.app_state or {}).get("current_page")
                    or (r.app_state or {}).get("current_tab")
                    or "?",
                    "description": r.description,
                    "user_email": r.user_email,
                }
                for r in external
            ]
            week_label = now.strftime("%Y-%m-%d")
            body = format_digest_body(reports, week_label)
            title = f"Weekly external feature-request digest — {week_label} ({len(reports)})"
            # A weekly roll-up of external feature requests is a P3 by family
            # (BOARD-TAXONOMY "digest"/parked tier) — it is a reading queue, not a
            # defect. Before Q434 it carried no priority and no area at all, so every
            # digest was born failing board lint's priority+area invariant.
            issue_number, _ = create_github_issue(
                title,
                body,
                [
                    "alert-intake",
                    "type:feature",
                    "reporter:external",
                    "area:frontend",
                    priority_label(family="digest"),
                ],
            )

            # stamp each report's backlog_ref to the digest so it is not
            # re-digested next week (no schema migration; reuses the column)
            ids = [r.id for r in external]
            await db.execute(
                sa_update(BugReport)
                .where(BugReport.id.in_(ids))
                .values(backlog_ref=f"#{issue_number}")
            )
            logger.info(
                "Feature-request digest: rolled %d external reports into issue #%d",
                len(ids), issue_number,
            )
            return {"digested": len(ids), "issue_number": issue_number}

    return _tracked_run("feature_request_digest", _digest())


@celery_app.task(bind=True, name="app.tasks.compare_ws_shadow")
def compare_ws_shadow_task(self):
    """#836 Batch 2 (SHADOW): compute the WS-shadow-vs-current is_winner match
    rate per source and store it in Redis for review (no live watching). Gates
    the eventual flip to WS-authoritative — flip only when agreement is high."""

    async def _compare():
        import json as _json
        from app.tasks.base import get_task_session
        from app.tasks.redis_state import get_async_redis_client
        from app.services.ws_shadow import compare_shadow_verdicts, SHADOW_COMPARISON_KEY

        async with get_task_session() as session:
            report = await compare_shadow_verdicts(session)
        try:
            rc = get_async_redis_client()
            await rc.set(SHADOW_COMPARISON_KEY, _json.dumps(report), ex=14 * 86400)
            await rc.aclose()
        except Exception:
            logger.warning("ws_shadow: failed to store comparison", exc_info=True)
        logger.info("ws_shadow comparison: %s", report.get("total"))
        return report

    return _tracked_run("ws_shadow_comparison", _compare())


# --- Calibration Prices ---

@celery_app.task(bind=True, soft_time_limit=600, time_limit=660, name="app.tasks.compute_calibration_prices")
def compute_calibration_prices(self):
    """Compute calibration_probability on resolved outcomes (Parts A/B/C)."""
    from app.tasks.backfill_winners import _compute_calibration_prices
    return _tracked_run("calibration_prices", _compute_calibration_prices())


@celery_app.task(
    bind=True,
    # CAL-P134 (#1835): 600 -> 1800. This is the first version of this number
    # that is MEASURED rather than inherited. The sweep is 372 non-empty
    # (category, month) cells over 15,948 eligible events; a stratified sample
    # of 64 of them — the 20 largest plus every eighth of the rest — took 377 s
    # through db-query, with 24 of those 64 hitting db-query's own 10 s row-path
    # cap so their true cost is a lower bound. The whole grid does not fit in
    # 600 s and never did; the 23-hour publish outage of 2026-08-29 is what that
    # looked like from outside.
    #
    # Raising a limit is normally the wrong move, and it is only safe here
    # because of the two things that landed with it: no single statement can run
    # longer than ``_CHUNK_TIMEOUT_S`` (45 s), so the longest uninterrupted
    # operation is bounded far below the limit; and the Redis write happens once,
    # at the end, after every slice has landed — so a run killed at the limit
    # publishes NOTHING rather than a short curve.
    soft_time_limit=1800,
    time_limit=1860,
    name="app.tasks.precompute_bookmaker_calibration",
)
def precompute_bookmaker_calibration(self):
    """Per-bookmaker moneyline calibration → Redis (#1835).

    CAL-P051. The starvation sibling of ``compute_calibration_prices`` directly
    above, and the one the #180 fix left behind: ``_precompute_bookmaker_
    calibration`` was reachable ONLY as a ``backfill_winners`` phase, sitting
    immediately behind that pipeline's FIRST budget guard. Measured 2026-08-13,
    the guard is where the pipeline stops — ``stopped_before:
    "bookmaker_closing"``, with ``successes_24h: 0`` and runs pinned at the 840s
    soft wall — so the writer had not executed, the 24h key had expired, and
    ``odds_api_bookmaker`` was simply absent from the live payload.

    Its own beat, so it drains regardless of what resolution costs that cycle.

    Idempotent and safe to re-run: one read-only aggregate, then one ``setex``
    of the whole bucket set. There is no cursor and no partial write — a
    soft-limit kill loses the run's compute and nothing else, and the next fire
    recomputes from scratch.

    ⚠️ 600s DID turn out to be too short, exactly as the paragraph this replaces
    warned, and the terminal contract worked: the run read NOT-GREEN instead of
    vanishing. What it could not do was keep the site publishing — the Redis key
    aged out of its 24h TTL and /api/calibration went 23 hours without a fresh
    curve. CAL-P134 took the next step that paragraph named, "a bounded or
    incremental query": the sweep is now 372 bounded (category, month) slices
    with a 45s per-statement ceiling and adaptive splitting, the statement
    itself is a single pass rather than two, and the limit above is measured.
    See ``_precompute_bookmaker_calibration`` for the numbers.
    """
    from app.tasks.backfill_winners import _precompute_bookmaker_calibration
    return _tracked_run("bookmaker_calibration", _precompute_bookmaker_calibration())


# --- Snapshot Retention ---

@celery_app.task(bind=True, soft_time_limit=1700, time_limit=1800, name="app.tasks.collapse_snapshots")
def collapse_snapshots(self, min_age_hours: int = 48, table: str = "odds", limit: int = 200):
    """Collapse consecutive identical snapshot rows for one table at a time."""
    from app.tasks.retention import _collapse_snapshots_impl
    return run_async(_collapse_snapshots_impl(min_age_hours, table, limit))


# --- Matching Audits ---

@celery_app.task(bind=True, soft_time_limit=600, time_limit=660, name="app.tasks.audit_canonical_keys")
def audit_canonical_keys(self, limit: int = 50):
    """Audit canonical key dedup quality with LLM verification."""
    from app.tasks.matching_audit import _audit_canonical_keys_impl
    return run_async(_audit_canonical_keys_impl(limit))


@celery_app.task(bind=True, soft_time_limit=600, time_limit=660, name="app.tasks.audit_prediction_market_links")
def audit_prediction_market_links(self, limit: int = 50):
    """Audit prediction market → event link quality with LLM verification."""
    from app.tasks.matching_audit import _audit_prediction_market_links_impl
    return run_async(_audit_prediction_market_links_impl(limit))


@celery_app.task(bind=True, soft_time_limit=600, time_limit=660, name="app.tasks.audit_related_futures")
def audit_related_futures(self, limit: int = 30):
    """Audit related futures coverage with LLM verification."""
    from app.tasks.matching_audit import _audit_related_futures_impl
    return run_async(_audit_related_futures_impl(limit))


# --- Matching Eval Metrics ---

@celery_app.task(bind=True, soft_time_limit=120, time_limit=150, name="app.tasks.compute_matching_metrics")
def compute_matching_metrics(self):
    """Compute prediction market matching coverage and accuracy metrics."""
    from app.tasks.matching_audit import _compute_matching_metrics_impl
    return run_async(_compute_matching_metrics_impl())


# --- Entity Registry Seeds (#171 execution rails; seed is on-demand only. The
# poly matchup backfill now ALSO has a 6h catch-up beat — #173/#1024 — since the
# ingest write-hook needs a net for the historical backlog + any missed rows) ---

@celery_app.task(
    bind=True,
    soft_time_limit=1500,
    time_limit=1560,
    name="app.tasks.seed_entity_registry",
)
def seed_entity_registry(self, persons_only: bool = True):
    """#171/#1020 — Run the A1 entity-registry fold-in seed in-worker.

    Removes the ``heroku run`` requirement (EPERM from the sandboxed crank). The
    person fold-in scans all individual-sport events + golf/motorsport futures
    outcomes, so it can exceed the GLOBAL 300s ``task_time_limit`` (a HARD limit →
    SIGKILL); a 1500s SOFT limit under a 1560s hard limit gives it room while
    keeping the overrun catchable. Idempotent + commits per batch, so a re-trigger
    resumes and a soft-limit overrun leaves committed progress intact.
    """
    from app.tasks.entity_seed import seed_entity_registry_impl
    return run_async(seed_entity_registry_impl(persons_only))


@celery_app.task(
    bind=True,
    soft_time_limit=900,
    time_limit=960,
    name="app.tasks.canonicalize_entities",
)
def canonicalize_entities_task(self, dry_run: bool = False):
    """#175 Item 1 — collapse same-family duplicate entities in-worker.

    On-demand merge of edition-multiplied person/team dups (e.g. "Alexandra Eala"
    ×15 across tennis tournament sport_keys) into one canonical entity, aliases
    repointed. Census-gated (cross-family homonyms left apart), additive-first,
    idempotent. 900s soft limit keeps the overrun catchable above the 300s cap.
    """
    from app.tasks.entity_seed import canonicalize_entities_impl
    return run_async(canonicalize_entities_impl(dry_run))


@celery_app.task(
    bind=True,
    soft_time_limit=900,
    time_limit=960,
    name="app.tasks.backfill_polymarket_matchups",
)
def backfill_polymarket_matchups(self, all_groups: bool = False):
    """#171/#1021 — Backfill ``matchup_title`` on poly game sub-markets in-worker.

    Recovers the "A vs. B" matchup from a sibling row in the same Polymarket group
    so the resolution engine reads both participants. Idempotent (only writes where
    missing); commits every 2000 rows. 900s soft limit keeps the overrun catchable
    above the global 300s hard cap.
    """
    from app.tasks.entity_seed import backfill_polymarket_matchups_impl
    return run_async(backfill_polymarket_matchups_impl(all_groups))


# --- Tier 1 Event Coverage Monitoring ---

@celery_app.task(bind=True, soft_time_limit=120, time_limit=150, name="app.tasks.check_tier1_coverage")
def check_tier1_coverage(self):
    """Alert when Tier 1 Kalshi game markets have no matching event."""
    from app.tasks.monitoring import check_tier1_event_coverage
    return run_async(check_tier1_event_coverage())


@celery_app.task(bind=True, soft_time_limit=300, time_limit=360, name="app.tasks.compute_snapshot_distribution")
def compute_snapshot_distribution(self):
    """Compute snapshot count distribution and cache in Redis."""
    from app.tasks.monitoring import compute_snapshot_distribution_impl
    return run_async(compute_snapshot_distribution_impl())


#: The window `probability_change_24h` and `max_movement_24h` are NAMED for, and
#: which `/api/futures/movers` publishes to callers as `timeframe_hours`. It is a
#: constant rather than a literal because three statements below have to agree
#: with each other AND with that payload field; when they drifted apart nobody
#: could see it, which is the defect in `_expire_stale_deltas`' docstring.
MOVEMENT_WINDOW_HOURS = 24

#: Rows retired per run of `update_max_movement`, biggest mover first.
#:
#: BOUNDED ON PURPOSE, and the bound is not cosmetic. When this shipped there
#: were **1,604,840** expired deltas standing (measured on production
#: 2026-08-31), and one unbounded `UPDATE` over them would have blown this
#: task's own 120 s `soft_time_limit`, held the row locks against four live
#: pollers, and left 1.6 M dead tuples behind in a single transaction. At this
#: size the task converges over roughly three hours of its ten-minute cadence
#: while every individual run stays small.
#:
#: ORDERED BY MAGNITUDE, which is the half that matters to a reader: the 102,625
#: expired rows claiming a swing of ten points or more are exactly the ones that
#: reach `/api/futures/movers`, so the FIRST run clears the whole visible lie and
#: the long tail of small deltas drains behind it. Oldest-first or unordered
#: leaves the strip wrong for hours (gotcha #41 — ask what the ordering starts
#: on).
STALE_DELTA_BATCH = 100_000

#: Rows retired per run by statement A2, the GRADED sweep, biggest mover first.
#:
#: A separate constant from `STALE_DELTA_BATCH` because it drains a separate,
#: larger backlog against a different plan, and the two have to be tunable
#: without moving each other. Measured on production 2026-08-31: A2's selection
#: at this limit runs in **2.13 s** (parallel seq scan + external merge sort,
#: 20.9 MB spilled) against A's 3.7 s, so a run doing both stays far inside this
#: task's 120 s `soft_time_limit`.
#:
#: The backlog it drains is **1,870,447** graded outcomes still carrying a delta
#: (85.5% of all 2,186,901 non-null deltas), of which **134,277** claim a swing
#: of ten points or more. Magnitude-ordered for the same reason A is: the visible
#: rows go first and the tail follows (gotcha #41).
#:
#: WHAT ONE RUN ACTUALLY CLEARS, measured rather than claimed: the 100,000th
#: graded row by magnitude sits at **0.2300**, so the first run retires every
#: graded delta of >= 23 points — which covers the whole strip-visible set
#: named above, the worst of it at 0.45 — and the >= 10-point tail needs a
#: SECOND run, i.e. ~20 minutes on this task's 10-minute beat. The full
#: 1.87 M drains in ~19 runs, a little over three hours. Say two runs; do not
#: round it to one.
GRADED_DELTA_BATCH = 100_000


@celery_app.task(bind=True, soft_time_limit=120, time_limit=150, name="app.tasks.update_max_movement")
def update_max_movement(self):
    """Retire expired movement deltas, recompute max_movement_24h, publish movers.

    LAT-P115: this task WRITES the column `/api/futures/movers` ranks by, so it
    is also the honest place to publish that answer. The warm runs AFTER the
    commit and inside its own guard — the column update is this task's job and a
    cache write must never be able to fail it or roll it back.

    ── WHY THERE ARE THREE STATEMENTS AND NOT ONE (item 12 / CAL-P159) ─────────

    `probability_change_24h` is not a 24-hour change. All four writers
    (`tasks/kalshi.py`, `tasks/polymarket.py` x2, `tasks/futures.py`) store
    `new - previous` at write time — a PER-WRITE delta — and nothing ever
    recomputed it over a window. So it FREEZES: a row that stops being written
    keeps serving its last delta forever, and the column's name keeps promising
    that the number describes the last day.

    Measured on production 2026-08-31, which is what sized the batch above:
    2,186,901 outcomes carried a non-null delta and **1,604,840 of them (73%)
    had not been touched in 24 hours**; 26,076 of the 31,568 open markets
    carrying a `max_movement_24h` had no fresh outcome at all. On the strip
    itself — `GET /api/futures/movers?limit=20`, which labels itself
    `timeframe_hours: 24` — **17 of the 20 served rows were older than 24 hours
    and the oldest was six weeks old.** Alex read one of them on market 109441 as
    a genuine -71.5 point day.

    The fix is upstream of every reader, and that is deliberate. LAT-P108 already
    measured the obvious read-side freshness filter and REFUSED it (see the long
    comment over `_MOVERS_POOLED` in `routes/futures.py`): `/api/futures/movers`
    ranks a candidate pool by `max_movement_24h`, which is only a provable
    SUPERSET of the answer while it equals `MAX(ABS(change))` over ALL of a
    market's outcomes. Filtering the answer by freshness while ranking the pool
    unfiltered breaks that bound — at limit 20 the two arms disagree on VALUES.
    Clearing the column here keeps the identity exactly true, so the bound and
    every one of the ~130 other readers stay correct for free. Do not re-derive
    the read-side fix; `tests/test_futures_stamp_semantics.py` also rejects one.

    Statement C exists because statement B structurally cannot lower a market.
    B drives off `GROUP BY market_id` over non-null deltas, so a market whose
    last delta just expired vanishes from the aggregate and RETAINS its old
    `max_movement_24h` forever. That is the 26,076, and clearing A without C
    would have left them ranked exactly as they are today.
    """
    async def _impl():
        from app.tasks.base import get_task_session
        from sqlalchemy import text
        async with get_task_session() as session:
            # A. Retire deltas whose row has not been written inside the window.
            #    `last_updated` is the right stamp and `price_changed_at` is the
            #    wrong one: this asks "has any writer touched this row", not "did
            #    the price move". A price parked at 3% for a week is being polled
            #    and its ~0 delta is honest; the rows here are ones NOTHING has
            #    written, whose delta therefore predates the window by
            #    construction. (#2024 records that reading as POLLER ALIVE.)
            expired = await session.execute(
                text("""
                    UPDATE futures_outcomes
                    SET probability_change_24h = NULL
                    WHERE id IN (
                        SELECT id
                        FROM futures_outcomes
                        WHERE probability_change_24h IS NOT NULL
                          AND last_updated < now() - (:window_hours * interval '1 hour')
                        ORDER BY abs(probability_change_24h) DESC
                        LIMIT :batch
                    )
                """),
                {"window_hours": MOVEMENT_WINDOW_HOURS, "batch": STALE_DELTA_BATCH},
            )

            # A2. Retire deltas on GRADED outcomes, whatever their stamp says.
            #
            #     A alone cannot reach these, and the reason is the whole defect
            #     (CERT-627). A gates on `last_updated`, which — exactly as A's
            #     own comment says — means "has any writer touched this row".
            #     Grading writers touch it constantly WITHOUT polling a price:
            #     `backfill_winners` stamps `last_updated = NOW()` at ~25 sites
            #     every 6 hours, `clob_resolve` at one, and each of those writes
            #     leaves `probability_change_24h` frozen at whatever it was when
            #     the market was last live. So the deadest rows in the table are
            #     precisely the ones A can never expire, and their immunity is
            #     RE-ARMED every 6 hours. Time cannot fix a row that is being
            #     touched; only a predicate on deadness can.
            #
            #     Measured on production 2026-08-31, which is why this statement
            #     exists rather than a widening of A: of the 2,186,901 non-null
            #     deltas, **1,870,447 (85.5%) sit on graded outcomes** and
            #     134,277 of those claim a swing of >= 10 points. Simulating the
            #     post-A state, 26 of the 120 strip-eligible open markets were
            #     fully-settled ones, the first at **rank 30** ("CA-34 House
            #     winner?"), followed by a settled IndyCar champion market and a
            #     cluster of FINISHED US Open matches at ranks 49-60.
            #
            #     `resolution_source IS NOT NULL` is the predicate, NOT
            #     `is_winner`. `is_winner` IS nullable — the model and
            #     production agree on that (see
            #     `tests/test_model_nullability_matches_production.py`) — but it
            #     carries a server DEFAULT false, so an ungraded row almost
            #     always STORES False rather than NULL, and the column therefore
            #     carries next to no grading information. Measured on production
            #     2026-08-31: `count(*) FILTER (WHERE is_winner IS NULL)` =
            #     2,536 out of 3,893,126 rows, so testing for NULL would find
            #     0.07% of the ungraded population. That is why deadness is read
            #     off `resolution_source` and never off `is_winner`.
            #
            #     Clearing is safe against regrades and self-healing: if an
            #     outcome is ever re-opened, the next poll writes a fresh delta.
            #     Every reader of this column already treats NULL as "no
            #     movement" (~10 call sites incl. `daily_digest`,
            #     `push_notifications`, `precompute_interestingness`), so a
            #     settled market also stops generating big-move pushes and
            #     digest rows — the same bug on two quieter surfaces.
            graded = await session.execute(
                text("""
                    UPDATE futures_outcomes
                    SET probability_change_24h = NULL
                    WHERE id IN (
                        SELECT id
                        FROM futures_outcomes
                        WHERE probability_change_24h IS NOT NULL
                          AND resolution_source IS NOT NULL
                        ORDER BY abs(probability_change_24h) DESC
                        LIMIT :batch
                    )
                """),
                {"batch": GRADED_DELTA_BATCH},
            )

            # B. Recompute the per-market maximum over what survived A and A2.
            result = await session.execute(text("""
                UPDATE futures_markets fm
                SET max_movement_24h = sub.max_mv
                FROM (
                    SELECT fo.market_id, MAX(ABS(fo.probability_change_24h)) AS max_mv
                    FROM futures_outcomes fo
                    WHERE fo.probability_change_24h IS NOT NULL
                    GROUP BY fo.market_id
                ) sub
                WHERE fm.id = sub.market_id
                  AND fm.status IN ('open', 'active')
                  AND (fm.max_movement_24h IS DISTINCT FROM sub.max_mv)
            """))

            # C. A market with no surviving delta has no maximum. NULL is the
            #    honest value — "we do not know", which is what every reader
            #    already handles — and it keeps
            #    `max_movement_24h == MAX(ABS(change))` exactly true, which is
            #    the identity /movers' pool bound rests on.
            cleared = await session.execute(text("""
                UPDATE futures_markets fm
                SET max_movement_24h = NULL
                WHERE fm.status IN ('open', 'active')
                  AND fm.max_movement_24h IS NOT NULL
                  AND NOT EXISTS (
                      SELECT 1
                      FROM futures_outcomes fo
                      WHERE fo.market_id = fm.id
                        AND fo.probability_change_24h IS NOT NULL
                  )
            """))

            # One commit for all three: a reader must never see A's cleared
            # outcomes against B and C's un-recomputed markets, because between
            # those two states the superset bound is false.
            await session.commit()
            updated = result.rowcount
            expired_rows = expired.rowcount
            graded_rows = graded.rowcount
            cleared_markets = cleared.rowcount

            # Reported, not swallowed: a warm that never ran must be visible in
            # the task result rather than inferred from a latency graph
            # (gotcha #53 — "it returned" is not "it worked").
            try:
                from app.tasks.futures_movers_warm import warm_futures_movers

                warm = await warm_futures_movers(session)
            except Exception as exc:  # noqa: BLE001 — never fail the column update
                logger.warning("update_max_movement: warm failed: %s", exc, exc_info=True)
                warm = {"terminal": "failed", "completed": 0, "reason": "error"}

            # `expired` and `backlog_drained` are reported so the drain is
            # observable while it runs: a run that retires exactly
            # STALE_DELTA_BATCH rows means more are waiting, and the day the
            # count sits below the batch the backlog is gone. Without them the
            # only signal would be the strip quietly getting better.
            return {
                "updated": updated,
                "expired": expired_rows,
                "graded_retired": graded_rows,
                "cleared_markets": cleared_markets,
                # Both backlogs have to be empty before the strip is honest, so
                # `backlog_drained` reports the AND. Reporting only A's would go
                # true while 1.87 M graded deltas were still standing — a green
                # light for the exact state this statement exists to end.
                "backlog_drained": (
                    expired_rows < STALE_DELTA_BATCH
                    and graded_rows < GRADED_DELTA_BATCH
                ),
                "graded_backlog_drained": graded_rows < GRADED_DELTA_BATCH,
                "window_hours": MOVEMENT_WINDOW_HOURS,
                "movers_warm": warm,
            }
    return run_async(_impl())


# --- Data Quality Monitoring ---

@celery_app.task(bind=True, name="app.tasks.check_data_quality")
def check_data_quality(self):
    """Check classification and matching health, alert on issues."""
    from app.tasks.data_quality import _check_data_quality
    return _tracked_run("check_data_quality", _check_data_quality())


@celery_app.task(bind=True, soft_time_limit=300, time_limit=360, name="app.tasks.run_data_quality_watchdog")
def run_data_quality_watchdog(self):
    """Run data quality watchdog: check freshness, coverage, sparsity; alert on failures."""
    from app.tasks.data_quality_watchdog import _run_data_quality_watchdog
    return _tracked_run("data_quality_watchdog", _run_data_quality_watchdog())


@celery_app.task(bind=True, soft_time_limit=840, time_limit=900, name="app.tasks.calibration_sentinel")
def calibration_sentinel(self, file_issues=True, suppress_known=True):
    """Calibration Sentinel (#1054): mine resolved-outcome cohorts across
    category × source × series × structure × table-provenance, n-weighted MCE per
    cohort, evidence-pack each break, and file ONE deduped GitHub issue per cohort
    fingerprint. Read-only detection — never writes market data (gotcha #21).
    The 840s soft limit (under the 900s hard limit, clear of the global 300s) plus
    the task's own 600s inner deadline keep it from SIGKILLing untracked (#966)."""
    from app.tasks.calibration_sentinel import _run_calibration_sentinel
    return _tracked_run(
        "calibration_sentinel",
        _run_calibration_sentinel(file_issues=file_issues, suppress_known=suppress_known),
    )


@celery_app.task(bind=True, soft_time_limit=840, time_limit=900, name="app.tasks.flow_sentinel")
def flow_sentinel(self, file_issues=True, canary=False):
    """Flow Sentinel (#1078): drive the six scripted user flows against
    production (search gold-set, duplicate events, event completeness, resolved
    state, chart density, category/Discover), assert a concrete correctness
    condition per flow, and file ONE deduped GitHub issue per failing flow. This
    is the reliability/design program's measurement — it removes Alex from the
    detection loop. Read-only against production; the sentinel files work, never
    writes data. The 840s soft limit (under the 900s hard limit, clear of the
    global 300s) plus the run's 540s inner deadline keep it from SIGKILLing
    untracked (#966)."""
    from app.tasks.flow_sentinel import _run_flow_sentinel
    return _tracked_run(
        "flow_sentinel",
        _run_flow_sentinel(file_issues=file_issues, canary=canary),
    )


@celery_app.task(bind=True, soft_time_limit=840, time_limit=900, name="app.tasks.grid_sentinel")
def grid_sentinel(self, file_issues=True):
    """Grid Sentinel (Queue #196): audit each championship grid (MLB/NBA/NHL),
    classify every finding as REAL vs an EXPLAINED calendar/blend artifact so RED
    always means REAL, and file ONE deduped GitHub issue per league with real
    defects. Includes the ground-truth envelope self-check (merged prob must live
    inside its source envelope) + a DB freshness self-check — retiring the Manus
    ground-truth file from accuracy duty. Read-only; never writes market data
    (gotcha #21). The 840s soft limit (under the 900s hard limit, clear of the
    global 300s) plus the run's 480s inner deadline keep it from SIGKILLing
    untracked (#966)."""
    from app.tasks.grid_sentinel import _run_grid_sentinel
    return _tracked_run(
        "grid_sentinel",
        _run_grid_sentinel(file_issues=file_issues),
    )


@celery_app.task(bind=True, soft_time_limit=840, time_limit=900,
                 name="app.tasks.anchor_schedule_sentinel")
def anchor_schedule_sentinel(self, file_issues=True):
    """Anchor-Schedule Sentinel (#2853): dereference every anchored, unfinished,
    near-future row BY ID and report the ones whose kickoff disagrees with the
    game their own ESPN anchor names — the December-anchor-on-a-September-row
    class that no scoreboard pass ever visits (#2804). Pages the window under a
    300s budget and a 12-page cap, resuming by cursor, and files ONE deduped
    issue; closes it only on a COMPLETE clean sweep, never on a truncated one.

    READ-ONLY: `apply=False` at the one call site and this wrapper exposes no
    apply flag — the correction stays attended (the moves are large and a
    reviewer should see the plan). Excludes tennis, which answers for no anchor
    (#2852). The 840s soft limit (under the 900s hard limit, clear of the global
    300s) plus the run's 300s inner deadline keep it from SIGKILLing untracked
    (#966)."""
    from app.tasks.anchor_schedule_sentinel import _run_anchor_schedule_sentinel
    return _tracked_run(
        "anchor_schedule_sentinel",
        _run_anchor_schedule_sentinel(file_issues=file_issues),
    )


@celery_app.task(bind=True, soft_time_limit=600, time_limit=660,
                 name="app.tasks.grid_register_sentinel")
def grid_register_sentinel(self, apply=False, file_issues=True):
    """Grid Register Sentinel (Queue #295): diff each committed grid register
    against current source inventory. Unambiguous drift (exact-identity ticker
    rename, authoritative settlement) proposes a validated next version;
    ambiguous drift is never applied and files ONE deduped P2 needs-triage issue
    per league with an MC-ready question. Defaults to ``apply=False`` (dry-run /
    diff only) so publication is an explicit choice. Identity only — reads no
    probabilities and writes no market data (gotcha #21). The 600s soft limit
    sits under the 660s hard limit and above the run's 240s inner deadline, so
    it can never SIGKILL untracked (#966)."""
    from app.tasks.grid_register_sentinel import _run_grid_register_sentinel
    return _tracked_run(
        "grid_register_sentinel",
        _run_grid_register_sentinel(apply=apply, file_issues=file_issues),
    )


@celery_app.task(bind=True, soft_time_limit=300, time_limit=360,
                 name="app.tasks.tournament_register_sentinel")
def tournament_register_sentinel(self, file_issues=True):
    """Tournament Register Sentinel (UX-P134): diff each committed tournament
    register against current source inventory, daily, from the day its page
    goes live. `/tournaments/us-open` pins 211 players, 66 matchups and 4
    curated props to exact `(source, market_id, outcome_id)` triples; a pinned
    register that drifts renders nothing, or renders a name against a market
    that is no longer that player's, and neither has a symptom the page can
    show. Files ONE deduped P2 per tournament and closes it when the drift
    clears. NEVER republishes: the register is a committed file reviewed as
    code, so a drift ruling during a live tournament is a human's. Identity
    only — reads no probabilities and writes no market data (gotcha #21). The
    300s soft limit sits under the 360s hard limit and above the run's 180s
    inner deadline, so it can never SIGKILL untracked (#966)."""
    from app.tasks.tournament_register_sentinel import _run_tournament_register_sentinel
    return _tracked_run(
        "tournament_register_sentinel",
        _run_tournament_register_sentinel(file_issues=file_issues),
    )


@celery_app.task(bind=True, soft_time_limit=840, time_limit=900, name="app.tasks.horizon_sentinel")
def horizon_sentinel(self, file_issues=True):
    """Horizon Sentinel (Queue #223): read THE HORIZON CALENDAR
    (app/config/majors_calendar.yaml — every knowable major through 2030) and
    escalate as each event nears — T-30 candidate, T-14 needs-page, T-7 marquee
    escalation, IN-PROGRESS-WITHOUT-PAGE = P0 — filing ONE deduped GitHub issue
    per uncovered event. A marquee event should never arrive without a page (The
    Open / World Cup top-slot failure class). Read-only; files work, never data.
    The 840s soft limit (under the 900s hard limit, clear of the global 300s) plus
    the run's 180s inner deadline keep it from SIGKILLing untracked (#966)."""
    from app.tasks.horizon_sentinel import _run_horizon_sentinel
    return _tracked_run(
        "horizon_sentinel",
        _run_horizon_sentinel(file_issues=file_issues),
    )


@celery_app.task(bind=True, soft_time_limit=840, time_limit=900, name="app.tasks.settled_concept_sentinel")
def settled_concept_sentinel(self, file_issues=True):
    """Settled-Concept Sentinel (Queue #226): within ~24h of any marquee concept
    settling (THE HORIZON CALENDAR knows the dates), read the LIVE event-concept
    surface and assert the settled contract — champion hero (winner market,
    won:true, top prob), field membership (round/leader markets show only real
    competitors), evolution chart resolves to one ~100% winner line (no 0.99-wall,
    no fizzle), and no double-graded round markets. Classifies REAL vs EXPLAINED so
    RED means REAL, and files ONE deduped GitHub issue per concept with REAL
    defects. The guard #225 earned. Read-only; files work, never data (gotcha #21).
    The 840s soft limit (under the 900s hard limit, clear of the global 300s) plus
    the run's 240s inner deadline keep it from SIGKILLing untracked (#966)."""
    from app.tasks.settled_concept_sentinel import _run_settled_concept_sentinel
    return _tracked_run(
        "settled_concept_sentinel",
        _run_settled_concept_sentinel(file_issues=file_issues),
    )


@celery_app.task(bind=True, soft_time_limit=840, time_limit=900, name="app.tasks.board_sentinel")
def board_sentinel(self, file_issues=True):
    """Board Sentinel (Queue #258): keep GitHub `Ready` a trustworthy execution
    source by keeping the BOARD itself honest. Daily checks — duplicate sentinel
    fingerprints among open alert-intake (the r252 dupe class), untriaged Inbox
    cards >48h, template-P1 share above the documented cap, blocked/parked cards in
    Inbox, and alert-intake issues missing every area:* label. Classifies REAL vs
    UNKNOWN (API/auth inability is never GREEN, never a cleanup accusation); files
    ONE deduped board-cleanup issue on RED and closes it on GREEN via the shared
    filing rail. Read-only against GitHub — never bulk-mutates the board (Ops owns
    the one-time cleanup). The 840s soft limit (under the 900s hard limit) plus the
    run's 120s inner deadline keep it from SIGKILLing untracked (#966)."""
    from app.tasks.board_sentinel import _run_board_sentinel
    return _tracked_run(
        "board_sentinel",
        _run_board_sentinel(file_issues=file_issues),
    )


@celery_app.task(bind=True, soft_time_limit=240, time_limit=300, name="app.tasks.matching_reconciliation")
def matching_reconciliation(self, file_issues=True):
    """Matching reconciliation (#2706): re-check the 709-pair golden set and the
    three INVARIANTS-2026-09-02 queries against PRODUCTION every matching cycle,
    and auto-file a deduped `matching-drift` issue per subject on any regression
    or violation — closing it again on recovery, via the shared sentinel rail.

    The CI gate catches a change to the matcher's logic before it merges; this
    catches production data moving under a matcher nobody changed, which is how
    every failure in the #2693 program actually arrived. Read-only against market
    data: it files GitHub metadata and nothing else. A check that cannot RUN is
    recorded as unmeasurable, never as GREEN, so a failed query can never close a
    real issue."""
    from app.tasks.matching_reconciliation import _run_matching_reconciliation
    return _tracked_run(
        "matching_reconciliation",
        _run_matching_reconciliation(file_issues=file_issues),
    )


@celery_app.task(bind=True, soft_time_limit=60, time_limit=90, name="app.tasks.sentry_snapshot")
def sentry_snapshot(self):
    """#237 Item 1: cache the top Sentry issues by 24h volume to Redis
    (bainluck:sentry:top_24h) so the ops-snapshot endpoint reads a warm key instead
    of calling Sentry live on the request path. No-ops (writes a no_token status)
    when SENTRY_AUTH_TOKEN is absent. Light HTTP task — runs on the background
    queue; the 60s soft limit keeps it clear of the global 300s hard limit."""
    from app.tasks.sentry_snapshot import _run_sentry_snapshot
    return _tracked_run("sentry_snapshot", _run_sentry_snapshot())


# --- Team Identity Backfill ---

@celery_app.task(bind=True, soft_time_limit=600, time_limit=660, name="app.tasks.backfill_team_identities")
def backfill_team_identities(self):
    from app.tasks.team_identity_backfill import _backfill_team_identities
    return run_async(_backfill_team_identities())


# --- Game State Backfill ---

@celery_app.task(bind=True, soft_time_limit=1800, time_limit=1860, name="app.tasks.backfill_game_state")
def backfill_game_state(self, limit=500, sport_filter=None):
    from app.tasks.game_state_backfill import _backfill_game_state
    return run_async(_backfill_game_state(limit=limit, sport_filter=sport_filter))


# --- DataGolf ---

@celery_app.task(bind=True, name="app.tasks.poll_datagolf_markets")
def poll_datagolf_markets(self):
    """Poll DataGolf schedule + pre-tournament predictions (hourly)."""
    from app.tasks.datagolf import _poll_datagolf_markets
    return _tracked_run("poll_datagolf", _poll_datagolf_markets())


@celery_app.task(bind=True, name="app.tasks.poll_datagolf_live")
def poll_datagolf_live(self):
    """Poll DataGolf live in-play probabilities (every 5 min, Redis-gated)."""
    from app.tasks.datagolf import _poll_datagolf_live, LIVE_KEY_PREFIX, POLL_TOURS
    from app.tasks.redis_state import get_redis_client

    # Only run if there's a live tournament (set by the live task itself or hourly poll)
    r = get_redis_client()
    any_live = any(r.get(f"{LIVE_KEY_PREFIX}:{tour}") for tour in POLL_TOURS)
    if not any_live:
        # Still run to detect if a tournament just went live
        pass

    return _tracked_run("datagolf_live", _poll_datagolf_live())


@celery_app.task(bind=True, name="app.tasks.poll_datagolf_inplay")
def poll_datagolf_inplay(self):
    """#144: dedicated ~90s in-play golf poll (schedule-window gated).

    Decoupled from poll_all_odds so live golf keeps a sub-minute-feeling cadence
    even when no ball sports are live. The window guard inside makes this a single
    Redis check off-tournament (near-zero cost)."""
    from app.tasks.datagolf import _poll_datagolf_inplay
    return _tracked_run("datagolf_inplay", _poll_datagolf_inplay())


# --- Golf Leaderboard Snapshot ---

@celery_app.task(bind=True, name="app.tasks.snapshot_golf_leaderboard")
def snapshot_golf_leaderboard(self):
    """Snapshot golf leaderboard positions/probs at start of day for delta computation."""
    from app.tasks.datagolf import _snapshot_leaderboard
    return _tracked_run("golf_leaderboard_snapshot", _snapshot_leaderboard())


# --- March Madness Bracket Sync ---

@celery_app.task(bind=True, name="app.tasks.sync_mm_bracket")
def sync_mm_bracket(self):
    """Sync NCAA tournament bracket data from ESPN (seeds, regions, rounds)."""
    from app.tasks.march_madness import _sync_march_madness_bracket
    return _tracked_run("mm_bracket_sync", _sync_march_madness_bracket())


# --- Event Taxonomy ---

@celery_app.task(bind=True, name="app.tasks.update_event_tags")
def update_event_tags(self, limit: int = 500):
    """Compute and persist event_tags + market_tags for events and futures."""
    from app.tasks.taxonomy import _update_event_tags_impl
    return _tracked_run("update_event_tags", _update_event_tags_impl(limit))


@celery_app.task(bind=True, soft_time_limit=600, time_limit=660,
                 name="app.tasks.enrich_taxonomy_llm")
def enrich_taxonomy_llm(self, event_limit: int = 50, market_limit: int = 30):
    """Enrich events and futures with LLM-generated taxonomy tags (stakes, narrative, audience, structure)."""
    from app.tasks.taxonomy import _enrich_taxonomy_llm_impl
    return _tracked_run("enrich_taxonomy_llm", _enrich_taxonomy_llm_impl(event_limit, market_limit))


@celery_app.task(bind=True, soft_time_limit=600, time_limit=660, name="app.tasks.reconcile_unanchored_events")
def reconcile_unanchored_events_task(self, apply: bool = False, limit: int = 1000):
    """Ruling 048's bounding clause, finally given an implementation (#1798).

    048 accepts rising duplicates as a BOUNDED cost, bounded because "id-keyed
    reconciliation drains the duplicate when an id arrives". That drain never
    existed: the provenance meter has read `created 500 / reconciled 0` since the
    ruling landed. Until this runs, the accepted cost has no bound.

    DRY-RUN by default — the apply path DELETEs. Enrolled in ENFORCED_TASKS from
    birth (#1884 precedent) with a real `terminal`, because a drain with nothing
    to drain must not report SUCCESS (gotcha #53 / #683's ten green weeks)."""
    from app.tasks.reconcile_unanchored_events import run_reconcile_unanchored
    return _tracked_run(
        "reconcile_unanchored_events",
        run_reconcile_unanchored(apply=apply, limit=limit),
    )


# --- Duplicate Event Cleanup ---


@celery_app.task(bind=True, soft_time_limit=600, time_limit=660, name="app.tasks.merge_duplicate_events")
def merge_duplicate_events_task(self, dry_run: bool = True):
    """Find and merge duplicate events (StatPal + Odds API race condition)."""
    from app.tasks.sports import _merge_duplicate_events_impl
    return run_async(_merge_duplicate_events_impl(dry_run=dry_run))


@celery_app.task(bind=True, soft_time_limit=600, time_limit=660, name="app.tasks.merge_degenerate_combat_events")
def merge_degenerate_combat_events_task(self, dry_run: bool = True, limit: int = 500):
    """#175 Item 3 — merge degenerate home==away fight events into their real
    odds-registry event so orphaned Kalshi fight markets assemble multi-source."""
    from app.tasks.sports import _merge_degenerate_combat_events_impl
    return run_async(_merge_degenerate_combat_events_impl(dry_run=dry_run, limit=limit))


# --- Cleanup ---

@celery_app.task(bind=True, soft_time_limit=1800, time_limit=1860, name="app.tasks.cleanup_crypto")
def cleanup_crypto(self, batch_size: int = 5000):
    """Delete all crypto futures data (markets, outcomes, snapshots)."""
    from app.tasks.retention import _cleanup_crypto_impl
    return run_async(_cleanup_crypto_impl(batch_size))


# ⚠️ LAT-P068 (#1609): these two are the LARGEST STRUCTURAL EXPOSURE on the
# 2-slot `background` pool, and until this commit they were the only residents
# of it with NO GAUGE AT ALL.
#
# `soft_time_limit=3600` means either one may hold **half the background pool
# for a full hour**, four times a day; they fire :30 and :45 of the same hours,
# so a long pair can hold BOTH slots simultaneously — a scheduled, total
# background outage window with nothing else able to run.
#
# Neither called `_tracked_run`, so neither wrote a start or a terminal, so
# `/api/admin/task-metrics?task=turbo_collapse_futures` returned NO DATA and
# `hard_kills` could not see them. They were invisible to every latency read
# taken in this program. S4 caught `turbo_collapse_futures` only by watching
# celery's `active` set directly: **13.6 minutes observed, 31.8 % of all
# background slot-time in a 22-minute window — the single largest occupant,
# ahead of `warm_typeahead`.**
#
# This change is instrumentation ONLY: no limit, no schedule, no behaviour is
# touched. Neither name is in `task_verdict.ENFORCED_TASKS`, so both classify to
# a non-authoritative `unknown` and record exactly as an untracked task did
# before — they simply become countable. Ruling 078: measure before you tune,
# and a task with no gauge is a stronger case of it than a gauge with no reader.
@celery_app.task(bind=True, soft_time_limit=3600, time_limit=3660, name="app.tasks.turbo_collapse_futures")
def turbo_collapse_futures(self, limit: int = 5000):
    """Aggressive collapse pass for futures snapshots — high partition limit."""
    from app.tasks.retention import _collapse_snapshots_impl
    return _tracked_run(
        "turbo_collapse_futures",
        _collapse_snapshots_impl(min_age_hours=24, table="futures", limit=limit),
    )


@celery_app.task(bind=True, soft_time_limit=3600, time_limit=3660, name="app.tasks.turbo_collapse_odds")
def turbo_collapse_odds(self, limit: int = 5000):
    """Aggressive collapse pass for odds snapshots — high partition limit."""
    from app.tasks.retention import _collapse_snapshots_impl
    return _tracked_run(
        "turbo_collapse_odds",
        _collapse_snapshots_impl(min_age_hours=24, table="odds", limit=limit),
    )


# --- StatPal Usage Tracking ---

@celery_app.task(name="app.tasks.track_statpal_usage")
def track_statpal_usage():
    """Fetch and record StatPal API daily request count (every 15 min)."""
    from app.services.statpal_api import get_statpal_request_count
    from app.tasks.redis_state import record_statpal_usage

    async def _impl():
        data = await get_statpal_request_count()
        if data and data.get("request_count") is not None:
            record_statpal_usage(data["request_count"], data.get("current_date", ""))
            return {"recorded": True, **data}
        return {"recorded": False, "reason": "no_data"}

    return run_async(_impl())


# --- Heartbeat ---

@celery_app.task(bind=True, name="app.tasks.export_engagement")
def export_engagement(self):
    """Nightly export of Discover engagement data for ranking review."""
    from app.tasks.export_engagement import _export_engagement_impl
    return _tracked_run("export_engagement", _export_engagement_impl())


# --- Push Notifications ---

@celery_app.task(bind=True, name="app.tasks.send_daily_challenge_push")
def send_daily_challenge_push(self):
    """Send daily challenge push notification to all opted-in device tokens."""
    from app.tasks.push_notifications import _send_daily_challenge_push
    return _tracked_run("daily_challenge_push", _send_daily_challenge_push())


@celery_app.task(bind=True, name="app.tasks.send_big_move_alerts")
def send_big_move_alerts(self):
    """Send push alerts for futures markets with >15pp movement to users who pinned them."""
    from app.tasks.push_notifications import _send_big_move_alerts
    return _tracked_run("big_move_alerts", _send_big_move_alerts())


@celery_app.task(bind=True, soft_time_limit=240, time_limit=300, name="app.tasks.send_morning_digest")
def send_morning_digest(self):
    """Morning Digest v1 (Queue #200): once daily (~7 AM PT) push the 3-5 most
    interesting probabilities to opted-in device tokens. Reuses the cached
    Discover interestingness scores (one content brain, cheap reads only)."""
    from app.tasks.morning_digest import _run_morning_digest
    return _tracked_run("morning_digest", _run_morning_digest())


# Queue 272 (#1459): the canonical compute is a single frozen-semantics CTE whose
# wall time on the production population VARIES widely with concurrent DB load —
# measured 605.8s at a quiet moment (18:24 UTC) but 910s under a 399-deep
# background backfill queue (22:33 UTC). At the old 600s (then 900s) soft limit it
# kept dying with SoftTimeLimitExceeded BEFORE it could publish, so once the 2h
# TTL expired the cache blanked and /api/calibration 503'd. The gates forbid
# chunking/changing the query, so the fix is real headroom over the observed
# contended range: soft 1500 / hard 1560 (25/26 min). One successful run warms the
# fresh key AND the durable 7-day last-good key (see _precompute_calibration_main),
# after which any later overrun is invisible to the route (it serves last-good as
# stale). Memory is unchanged (same payload); the heavy lane (concurrency 2,
# hourly cadence, siblings 6h-staggered) absorbs the longer hold. The underlying
# query cost / backfill DB-contention is a separate perf follow-up (#1197 stays
# open) — this queue restores availability, not compute speed.
@celery_app.task(bind=True, soft_time_limit=1500, time_limit=1560, name="app.tasks.precompute_calibration_main")
def precompute_calibration_main(self):
    """Precompute main /api/calibration response and cache in Redis (every 1h)."""
    from app.tasks.precompute_calibration import _precompute_calibration_main
    return _tracked_run("precompute_calibration_main", _precompute_calibration_main())


@celery_app.task(bind=True, soft_time_limit=1500, time_limit=1560,
                 name="app.tasks.cohort_cell_census")
def cohort_cell_census(self, page_size=1000, resume=True):
    """#1978: the all-cells provenance census, as a resumable worker.

    NOT on the beat schedule, deliberately. It reads the same population the
    deadline-critical q268 producer reads hourly from :15 to ~:35, and CAL-P074
    measured self-inflicted contention costing a cell its whole first pass. It is
    operator-triggered (``POST /api/admin/cohort-cell-census/run``) so the quiet
    window is a choice a human makes, not a cron guess.

    Resumable by design rather than budgeted: the same job measured 645
    markets/s quiet and 101 markets/s contended, and ruling 089 is precisely
    about a bound derived from the quiet number cancelling every contended run.
    It checkpoints per page, so a cancellation costs one page. Re-invoke until
    ``complete: true``. Reads only; writes no market data (gotcha #21)."""
    from app.tasks.cohort_cell_census_worker import run_cohort_cell_census
    return _tracked_run(
        "cohort_cell_census",
        run_cohort_cell_census(page_size=int(page_size), resume=bool(resume)),
    )


@celery_app.task(bind=True, soft_time_limit=1800, time_limit=1860,
                 name="app.tasks.calibration_published_twin")
def calibration_published_twin(self, timeout_ms=None):
    """CAL-P080 (#2007): Gate 0's DB-direct twin, run where its budget fits.

    NOT on the beat schedule, for the same reason ``cohort_cell_census`` is not:
    it reads the heavy published-curve population that the deadline-critical
    hourly q268 producer reads from :15 to ~:35, and CAL-P074 measured
    self-inflicted contention costing a cell its whole first pass. Operator
    triggered (``POST /api/admin/calibration-twin/run``) so the quiet window is
    a choice a human makes, not a cron guess.

    The time limits are the point of the task. The instrument's own budget is
    240 s and the admin ``db-query`` rail hardcodes 10 s, so the fold had no
    reachable home; here it does. Reads only, writes no market data (gotcha
    #21). Enrolled in ``task_verdict.ENFORCED_TASKS`` WITH a terminal, so a run
    that measured nothing cannot report GREEN.

    **CAL-P084 (#2076): 1500 s -> 1800 s soft, on a measurement.** The fold was
    cancelled at ``fold_duration_s 901.96`` against the then-ceiling of 900 s
    (2026-08-21 16:55:05Z), as it had been at 241.18 against 240 s. The ceiling
    moves to 1 350 000 ms and the soft limit has to clear it with room for the
    two disclosure reads, the payload read and the durable write — a statement
    allowed to outlive the soft limit is killed mid-flight and writes no
    artifact, which is worse than a timeout because it leaves no diagnosis."""
    from app.tasks.calibration_published_twin_worker import (
        DEFAULT_TIMEOUT_MS,
        run_published_twin,
    )

    budget = DEFAULT_TIMEOUT_MS if timeout_ms is None else timeout_ms
    return _tracked_run(
        "calibration_published_twin",
        run_published_twin(timeout_ms=budget),
    )


@celery_app.task(bind=True, soft_time_limit=120, time_limit=180,
                 name="app.tasks.calibration_beat_gauge_sampler")
def calibration_beat_gauge_sampler(self):
    """CAL-P084 (#2007): bank each beat's fixed gauge set before it is overwritten.

    ``durable_state_snapshots`` keeps ONE row per identity, so
    ``calibration:main:phase_ledger`` is overwritten every beat and the beat
    that promotes the bank is observable for about an hour. The bound's first
    descent (2026-08-21 12:30:24Z) was captured only because a PREVIOUS window
    had left ``scripts/sample_calibration_beats.py`` running in a terminal.
    This task is that observer, made permanent.

    Two small reads and at most one small write, so the time limits are tight
    on purpose: anything that takes two minutes here has gone wrong, and a
    ``soft_time_limit`` well inside the beat's quiet window means it can never
    still be holding a connection when the producer starts at :15.

    Enrolled in ``task_verdict.ENFORCED_TASKS`` WITH terminals — a run that
    captured nothing, or that ran cleanly over a producer that has stopped,
    must not read GREEN."""
    from app.tasks.calibration_beat_gauge_sampler import run_beat_gauge_sample

    return _tracked_run("calibration_beat_gauge_sampler", run_beat_gauge_sample())


@celery_app.task(bind=True, soft_time_limit=600, time_limit=660, name="app.tasks.compute_time_horizon_calibration")
def compute_time_horizon_calibration(self):
    """Precompute time-horizon calibration and cache in Redis (every 6h)."""
    from app.tasks.precompute_calibration import _compute_time_horizon_calibration
    return _tracked_run("compute_time_horizon_calibration", _compute_time_horizon_calibration())


@celery_app.task(bind=True, soft_time_limit=600, time_limit=660, name="app.tasks.compute_fair_fight_comparison")
def compute_fair_fight_comparison(self):
    """Precompute fair-fight source comparison and cache in Redis (every 6h)."""
    from app.tasks.precompute_calibration import _compute_fair_fight_comparison
    return _tracked_run("compute_fair_fight_comparison", _compute_fair_fight_comparison())


@celery_app.task(bind=True, soft_time_limit=600, time_limit=660, name="app.tasks.precompute_source_intelligence")
def precompute_source_intelligence(self):
    """Precompute the Source-Intelligence ("Measure") snapshot into Redis (every 6h).

    L2-129 / #206: keeps the 4 heavy corpus queries off the request path and never
    caches a degraded/empty build (the blank-page poisoning bug)."""
    from app.tasks.precompute_source_intelligence import _compute_source_intelligence
    return _tracked_run("precompute_source_intelligence", _compute_source_intelligence())


@celery_app.task(bind=True, soft_time_limit=600, time_limit=660, name="app.tasks.snapshot_coverage_metrics")
def snapshot_coverage_metrics(self):
    """Daily snapshot of coverage metrics for tracking progress."""
    from app.tasks.precompute_calibration import _snapshot_coverage_metrics
    return _tracked_run("coverage_metrics", _snapshot_coverage_metrics())


@celery_app.task(bind=True, soft_time_limit=300, time_limit=360, name="app.tasks.precompute_category_pages")
def precompute_category_pages(self):
    """Precompute category page responses and cache in Redis (every 1h)."""
    from app.tasks.precompute_category_pages import _precompute_all_category_pages
    return _tracked_run("precompute_category_pages", _precompute_all_category_pages())


@celery_app.task(bind=True, soft_time_limit=240, time_limit=280, name="app.tasks.warm_event_concepts")
def warm_event_concepts(self):
    """Keep the golf-major concept payloads warm (#1107, LAT-P021, every 5 min).

    Budget: four measured builds total ~82s (worst case ~100s) and each ONE is
    bounded at 55s inside the task, so the soft limit here bounds the run and
    PER_KEY_TIMEOUT_SECONDS bounds the longest single uninterrupted op. Both are
    under the 300s hard SIGKILL that would otherwise be recorded as no_data.
    """
    # NOTE the module is `event_concept_warmer`, not `warm_event_concepts`: a
    # submodule sharing a name with a registered task is shadowed by the task on
    # `from app.tasks import <name>`, which is a trap for anything importing it.
    from app.tasks.event_concept_warmer import _warm_event_concepts
    return _tracked_run("warm_event_concepts", _warm_event_concepts())


@celery_app.task(
    bind=True,
    soft_time_limit=60,
    time_limit=75,
    name="app.tasks.warm_futures_categories",
)
def warm_futures_categories(self):
    """Keep the Search page's category census warm (LAT-P137, every 5 min).

    Budget: ONE census build, measured 1.37-1.59 s, bounded inside the task at
    `BUILD_TIMEOUT_SECONDS` (30 s) — that is the longest uninterrupted op, and
    the soft limit here is twice it so a wedged build is reported by the inner
    timeout with a reason rather than killed by the outer one without.

    NOTE the module is `futures_categories_warm`, not `warm_futures_categories`:
    a submodule sharing a name with a registered task is shadowed by the task on
    `from app.tasks import <name>`, the trap `warm_event_concepts` records above.
    """
    from app.tasks.futures_categories_warm import _warm_futures_categories
    return _tracked_run("warm_futures_categories", _warm_futures_categories())


@celery_app.task(bind=True, soft_time_limit=100, time_limit=115, name="app.tasks.warm_typeahead")
def warm_typeahead(self, head_size: int = None):
    """Keep `/typeahead`'s hot pages resident so a user never pays the cold read.

    #1866 / LAT-P056. The miss cost was decomposed at the transport boundary
    (n=24 pairs): 99.74% of it is the server segment, and EXPLAIN ANALYZE on
    production showed 95-98% of THAT is `Shared I/O Read Time` on non-resident
    pg_trgm GIN pages — same plan, same rows, 1094.5ms cold vs 27.1ms hot.

    Budget: the first (cold) run pays the real reads and is the worst case at
    ~40 queries; every query after that is served from resident pages. ONE query
    is bounded at `PER_QUERY_TIMEOUT_SECONDS=10` inside the task, so the longest
    single uninterrupted op is bounded rather than only the loop boundary, and
    both limits sit under the 300s hard SIGKILL that would be recorded as
    `no_data`.
    """
    # NOTE the module is `typeahead_warmer`, not `warm_typeahead`: a submodule
    # sharing a name with a registered task is shadowed by the task on
    # `from app.tasks import <name>` — the same trap `warm_event_concepts`
    # records two definitions below.
    from app.tasks.typeahead_warmer import DEFAULT_HEAD_SIZE, _warm_typeahead

    size = DEFAULT_HEAD_SIZE if head_size is None else int(head_size)
    return _tracked_run("warm_typeahead", _warm_typeahead(head_size=size))


@celery_app.task(bind=True, soft_time_limit=120, time_limit=140, name="app.tasks.warm_search_head")
def warm_search_head(self, head_size: int = None):
    """Keep the head of the `/search` distribution inside its response cache.

    LAT-P090/#2211, and it is the lever the LAT-P088 index gate pointed at after
    the index itself was dropped. The pre-registered budget arm came back RED
    (median per-term collapse 0.7194 vs a 0.5 ceiling), and the per-term table
    underneath it split by term FREQUENCY: rare phrases collapsed (`super bowl`
    0.078, `world series` 0.083) while the common-word head did not (`winner`
    0.979, `election` 0.998). A trigram index is a selectivity instrument and
    `%winner%` matches 42,336 of 858,938 rows, so the head cannot be fixed by
    any string index — only answered before it is asked.

    Budget: 8 head queries at concurrency 2, one query bounded at
    `PER_QUERY_TIMEOUT_SECONDS = 25` INSIDE the task so the longest uninterrupted
    op is bounded and not merely the loop boundary, and a `MIN_PASS_PERIOD_SECONDS
    = 45` floor bounding how often a pass may start at all. Both limits sit under
    the 300 s global hard `task_time_limit`, which is a SIGKILL that would be
    recorded as `no_data` rather than as a failure.
    """
    # NOTE the module is `search_head_warmer`, not `warm_search_head`: a
    # submodule sharing a name with a registered task is shadowed by the task on
    # `from app.tasks import <name>` — the trap `warm_typeahead` and
    # `warm_event_concepts` both record above.
    from app.tasks.search_head_warmer import DEFAULT_HEAD_SIZE as _SEARCH_HEAD_SIZE
    from app.tasks.search_head_warmer import _warm_search_head

    size = _SEARCH_HEAD_SIZE if head_size is None else int(head_size)
    return _tracked_run("warm_search_head", _warm_search_head(head_size=size))


@celery_app.task(
    bind=True,
    soft_time_limit=90,
    time_limit=120,
    name="app.tasks.flush_search_gin_pending_lists",
)
def flush_search_gin_pending_lists(self):
    """Keep the search path's trigram GIN pending lists from filling up.

    LAT-P109/#2255. Measured on production 2026-08-28: the identical futures
    query in `/api/events/search` cost 148.9 ms and then 27.8 ms eleven minutes
    apart, same rows in and out, and a `%zzqqxxvv%` probe — a pattern that
    matches nothing and can do no useful work — cost 49.9 ms over 507 shared
    blocks, then 0.3 ms over 31. 507 pages is `gin_pending_list_limit = 4MB`
    being read start to finish by every reader. Every trigram index on the
    search read path climbs to that limit and is flushed by whichever INSERT
    crosses it, so cold search is a coin flip between the two numbers.

    Budget: the longest uninterrupted operation is ONE index flush, and that is
    what carries the bound (`PER_INDEX_TIMEOUT_MS = 15s`), not the loop
    boundary. Seven indexes at the 2-minute beat, each inside its own
    savepoint — the full reasoning and the sawtooth measurement are in
    `app/tasks/gin_pending_lists.py`.
    """
    from app.tasks.gin_pending_lists import _flush_gin_pending_lists

    return _tracked_run(
        "flush_search_gin_pending_lists", _flush_gin_pending_lists()
    )


@celery_app.task(
    bind=True, soft_time_limit=150, time_limit=180, name="app.tasks.rebuild_typeahead_index"
)
def rebuild_typeahead_index(
    self, budget_seconds: int = None, page_size: int = None, entity_types=None
):
    """Option D (#1866): project the searchable entities into `typeahead_index`.

    Bounded and resumable. The default 90s budget sits well under the 150s soft
    limit, which sits under the 180s hard limit — and a single page is separately
    bounded at 25s inside the task, so the LONGEST UNINTERRUPTED OP is bounded and
    not just the loop boundary. All three are under the 300s global hard
    `task_time_limit`, which is a SIGKILL that would be recorded as `no_data`
    rather than as a failure.

    Enrolled in `task_verdict.ENFORCED_TASKS`, with a real `terminal`: a
    budget-truncated pass returns `partial` and must never read GREEN, because
    "the sweep is behind" and "the sweep is caught up" are the two states this
    task exists to distinguish and they look identical from outside.

    ALSO the one-off-dyno entry point for the initial ~380k-row fill, which is
    condition 3 of the assigned migration slot (the backfill is a TASK, never a
    migration step):

        heroku run:detached --size=standard-2x -a bainluck -- \\
          python3 -c "from app.tasks import rebuild_typeahead_index as t; \\
                      print(t.apply(kwargs={'budget_seconds': 1500}).get())"

    ⚠️ `.apply()` AND NOT `.delay()`, and the difference is not stylistic.
    `.apply()` runs the task EAGERLY in the one-off dyno's own process, where
    the pool's time limits do not apply, so a 1500s budget is honoured.
    `.delay()` would hand it to a WORKER, where the 150s soft limit above kills
    it at 150s — the run would look like it accepted a 1500s budget and would
    silently bank a tenth of it. The budget argument is not a promise the worker
    can keep; only the eager path can.

    Note `run:detached` — a non-detached `heroku run` silently fails to execute
    in this sandbox (gotcha #48), so verify by census, never by stdout.
    """
    from app.tasks.typeahead_index import (
        DEFAULT_BUDGET_SECONDS,
        PAGE_SIZE,
        _rebuild_typeahead_index,
    )

    return _tracked_run(
        "rebuild_typeahead_index",
        _rebuild_typeahead_index(
            budget_seconds=DEFAULT_BUDGET_SECONDS if budget_seconds is None else int(budget_seconds),
            page_size=PAGE_SIZE if page_size is None else int(page_size),
            entity_types=entity_types,
        ),
    )


@celery_app.task(
    bind=True, soft_time_limit=240, time_limit=280, name="app.tasks.typeahead_index_sentinel"
)
def typeahead_index_sentinel(self, sample_size: int = None):
    """Option D's D4 gate: prove `typeahead_index` still agrees with its sources.

    NOT a follow-up and not a nice-to-have — the table ships with this or the
    table does not ship. `typeahead_index` is a SECOND COPY OF TRUTH, and #1866's
    history is instruments that reported success while doing nothing (gotcha #53).
    A denormalised index that silently goes stale is a worse defect than the slow
    query it replaces, because the slow query was at least correct.

    Enrolled in `ENFORCED_TASKS`. Drift above the threshold returns
    `terminal: failed` — loudly not-GREEN — rather than reporting its own finding
    as a healthy run. An empty index returns `no_work`, because "the backfill has
    not run yet" is not drift and an alarm that screams through the whole initial
    build is an alarm nobody reads.
    """
    from app.tasks.typeahead_index import (
        SENTINEL_SAMPLE_SIZE,
        _run_typeahead_index_sentinel,
    )

    return _tracked_run(
        "typeahead_index_sentinel",
        _run_typeahead_index_sentinel(
            sample_size=SENTINEL_SAMPLE_SIZE if sample_size is None else int(sample_size)
        ),
    )


@celery_app.task(bind=True, soft_time_limit=90, time_limit=120, name="app.tasks.refresh_event_concept")
def refresh_event_concept(self, key: str, token: str | None = None):
    """Revalidate one concept key after the route served its 24h mirror.

    Dispatched from `routes/event.py` under a single-flight lock, so a burst of
    readers behind one TTL expiry produces one of these, not one per reader.

    `token` is the refresh-lock owner token the route acquired: the acquire and
    the release are in different processes, so ownership has to travel with the
    message (#1678 finding 1). It is optional ONLY so that messages already in the
    broker when this deploys still execute — a task signature that drops an
    argument rejects every in-flight message with a TypeError.
    """
    from app.tasks.event_concept_warmer import _refresh_event_concept
    return _tracked_run("refresh_event_concept", _refresh_event_concept(key, token))


@celery_app.task(bind=True, soft_time_limit=90, time_limit=120, name="app.tasks.refresh_hub")
def refresh_hub(self, slug: str, token: str | None = None):
    """Revalidate one competition hub after the route served its 24h mirror (#1651).

    Dispatched from `routes/hub.py` under a single-flight lock, so a burst of
    readers behind one TTL expiry produces one of these, not one per reader.

    `token` is the refresh-lock owner token the route acquired; the acquire and the
    release are in different processes, so ownership has to travel with the message
    (#1678 finding 1). Optional so that messages already in the broker when this
    deploys still execute.

    Not on the beat schedule on purpose: stale-while-revalidate keeps these warm
    off real traffic, and a scheduled second producer racing the route's lock is
    exactly the shape #1678 finding 1 was.
    """
    from app.tasks.hub_refresh import _refresh_hub
    return _tracked_run("refresh_hub", _refresh_hub(slug, token))


@celery_app.task(
    bind=True, soft_time_limit=120, time_limit=180,
    name="app.tasks.refresh_prop_families",
)
def refresh_prop_families(self, team_id: int, cap: int = 400, token: str | None = None):
    """Rebuild ONE team's prop families (LAT-P138, #1249 follow-up).

    Dispatched two ways, both under the same single-flight lock: by
    `routes/prop_families.py` after it served the 24h mirror, and by
    `warm_prop_families` below. `token` is the owner token the dispatcher
    acquired — the acquire and the release are in different processes, so
    ownership travels with the message (#1678 finding 1).

    `soft_time_limit` is 120s against a slowest measured cold build of 16.8s: the
    build's own `asyncio.wait_for` is the 60s bound that reports a wedge, and this
    is the backstop above it. Both stay under the 300s hard `task_time_limit`
    (project_celery_sigkill_untracked).
    """
    from app.tasks.prop_families_warm import _refresh_prop_families
    return _tracked_run(
        "refresh_prop_families", _refresh_prop_families(team_id, cap, token)
    )


@celery_app.task(
    bind=True, soft_time_limit=260, time_limit=290,
    name="app.tasks.warm_prop_families",
)
def warm_prop_families(self):
    """Keep the reachable teams' prop-family mirrors alive (LAT-P138).

    Unlike `refresh_hub` above, this tier HAS a scheduled producer, and the
    reason is size, not preference: a hub rebuild was 2.7s at its worst, a
    prop-families rebuild is 2.6-16.8s. The race a second producer would create
    is closed by taking the SAME refresh lock the route takes, so a pass arriving
    while a reader's rebuild is in flight skips that team.

    It rebuilds INLINE rather than fanning out one message per team, because
    `test_no_task_dispatches_another_task` forbids intra-task dispatch — the
    result-consumer set is derived by scanning routes, services and utils, so a
    task that dispatches a task can grow a consumer that scan never sees.

    The limits are derived from the work, not chosen: `PASS_BUDGET_SECONDS` (180)
    plus one whole `PER_TEAM_TIMEOUT_SECONDS` (60) for a team that starts on the
    last tick of the budget is 240 s, so the soft limit is 260 and the hard one
    290 — both inside the 300 s global `task_time_limit` that arrives as an
    untracked SIGKILL (project_celery_sigkill_untracked).
    """
    from app.tasks.prop_families_warm import _warm_prop_families
    return _tracked_run("warm_prop_families", _warm_prop_families())


@celery_app.task(bind=True, soft_time_limit=90, time_limit=120, name="app.tasks.refresh_league")
def refresh_league(self, sport_key: str, token: str | None = None):
    """Revalidate one league after the route served its 24h mirror (#1767).

    Dispatched from `routes/league_futures.py` under a single-flight lock, so a
    burst of readers behind one TTL expiry produces one of these, not one per
    reader.

    `token` is the refresh-lock owner token the route acquired; the acquire and the
    release are in different processes, so ownership has to travel with the message
    (#1678 finding 1). Optional so that messages already in the broker when this
    deploys still execute.

    Not on the beat schedule on purpose: stale-while-revalidate keeps these warm
    off real traffic, and a scheduled second producer racing the route's lock is
    exactly the shape #1678 finding 1 was.
    """
    from app.tasks.league_refresh import _refresh_league
    return _tracked_run("refresh_league", _refresh_league(sport_key, token))


@celery_app.task(bind=True, soft_time_limit=120, time_limit=180, name="app.tasks.precompute_discover_candidate_base")
def precompute_discover_candidate_base(self):
    """Precompute + publish the anonymous Discover candidate-ID base (Queue 285)."""
    from app.tasks.precompute_category_pages import _precompute_discover_candidate_base
    return _tracked_run(
        "precompute_discover_candidate_base", _precompute_discover_candidate_base()
    )


#: #2236. The limits are derived from the period, not chosen: the hard limit is
#: BELOW `FEED_LIVE_REPUBLISH_PERIOD_S` so a wedged pass is dead before its
#: successor fires, which is what makes an overlap lock unnecessary rather than
#: merely unlikely. Soft sits under hard so the pass raises `SoftTimeLimitExceeded`
#: and gets logged, instead of vanishing into an untracked SIGKILL (gotcha:
#: "Celery SIGKILL untracked" — a hard-killed task reports nothing at all).
_LIVE_PREWARM_HARD_LIMIT_S = 35
_LIVE_PREWARM_SOFT_LIMIT_S = 28


@celery_app.task(
    bind=True,
    soft_time_limit=_LIVE_PREWARM_SOFT_LIMIT_S,
    time_limit=_LIVE_PREWARM_HARD_LIMIT_S,
    name="app.tasks.prewarm_live_feed_shapes",
)
def prewarm_live_feed_shapes(self):
    """Republish live-containing feed shapes inside the #2216 60s ceiling (#2236)."""
    from app.tasks.precompute_category_pages import _prewarm_live_feed_shapes

    return _tracked_run("prewarm_live_feed_shapes", _prewarm_live_feed_shapes())


@celery_app.task(bind=True, soft_time_limit=60, time_limit=90, name="app.tasks.refresh_open_commentary")
def refresh_open_commentary(self):
    """Refresh the live AI commentary box for The Open Championship (Open-only,
    live-only). Cheap Redis-gated skip off-tournament; one OpenAI call per run
    while live. See app/tasks/golf_commentary.py."""
    from app.tasks.golf_commentary import _refresh_open_commentary
    return _tracked_run("refresh_open_commentary", _refresh_open_commentary())


@celery_app.task(bind=True, soft_time_limit=300, time_limit=360, name="app.tasks.precompute_admin_audit_all")
def precompute_admin_audit_all(self):
    """Precompute /api/admin/audit/all (4 grid subprocesses) into Redis (L2-90)."""
    from app.tasks.precompute_admin_health import _precompute_admin_audit_all
    return _tracked_run("precompute_admin_audit_all", _precompute_admin_audit_all())


@celery_app.task(bind=True, soft_time_limit=120, time_limit=180, name="app.tasks.precompute_admin_link_rate")
def precompute_admin_link_rate(self):
    """Precompute /api/admin/prediction-markets/link-rate into Redis (L2-90)."""
    from app.tasks.precompute_admin_health import _precompute_admin_link_rate
    return _tracked_run("precompute_admin_link_rate", _precompute_admin_link_rate())


@celery_app.task(bind=True, soft_time_limit=120, time_limit=180, name="app.tasks.precompute_admin_matured_linkage")
def precompute_admin_matured_linkage(self):
    """Precompute the matured-linkage metric into Redis (Queue #220/221 Item 2)."""
    from app.tasks.precompute_admin_health import _precompute_admin_matured_linkage
    return _tracked_run("precompute_admin_matured_linkage", _precompute_admin_matured_linkage())


@celery_app.task(bind=True, soft_time_limit=600, time_limit=660, name="app.tasks.precompute_backfill_winners_status")
def precompute_backfill_winners_status(self):
    """Precompute backfill-winners/status response and cache in Redis (every 1h)."""
    from app.tasks.precompute_backfill_winners_status import _precompute_backfill_winners_status
    return _tracked_run("precompute_backfill_winners_status", _precompute_backfill_winners_status())


@celery_app.task(bind=True, soft_time_limit=280, time_limit=300, name="app.tasks.precompute_backfill_progress")
def precompute_backfill_progress(self):
    """Precompute backfill-progress heavy census (density + June ledger) — #179/#1052."""
    from app.tasks.precompute_backfill_progress import _precompute_backfill_progress
    return _tracked_run("precompute_backfill_progress", _precompute_backfill_progress())


@celery_app.task(bind=True, soft_time_limit=280, time_limit=300, name="app.tasks.backfill_combat_wps")
def backfill_combat_wps(self, limit: int = 500, dry_run: bool = False):
    """Combat-targeted oldest-first WPS backfill — reaches the settled-fight tail (#178)."""
    from app.tasks.backfill_combat_wps import _backfill_combat_wps
    return _tracked_run("backfill_combat_wps", _backfill_combat_wps(limit=limit, dry_run=dry_run))


@celery_app.task(name="app.tasks.heartbeat")
def heartbeat():
    """Write a heartbeat timestamp to Redis for health monitoring."""
    from datetime import datetime, timezone
    from app.tasks.redis_state import get_redis_client
    try:
        r = get_redis_client()
        r.set("bainluck:heartbeat", datetime.now(timezone.utc).isoformat(), ex=300)
        return {"status": "ok"}
    except Exception as e:
        return {"status": "error", "error": str(e)}


@celery_app.task(name="app.tasks.transition_event_statuses")
def transition_event_statuses():
    """Transition event statuses based on commence_time (no API calls needed).

    Fixes the circular dependency where status='live' is required by ESPN/StatPal/
    prediction market tasks, but was only set by Odds API polling which may be
    throttled by quota conservation or adaptive slowdown.

    Runs every 60s on the realtime queue:
    - scheduled → live: when commence_time <= now
    - live → closed: when commence_time + max_sport_duration has passed and no
      recent data updates (staleness fallback)
    """
    from app.tasks.espn_sync import _transition_event_statuses_impl
    return _tracked_run("transition_statuses", _transition_event_statuses_impl())


# =============================================================================
# Beat schedule
# =============================================================================


def _futures_categories_warm_minutes() -> int:
    """The `warm-futures-categories` cadence, in whole minutes.

    LAT-P137. A one-line indirection so the beat entry below spells a DERIVED
    period (`futures_categories_warm.warm_period_minutes()`, computed from the
    tier's own stale-serve ceiling) instead of a literal that can fall out of
    step with the contract it exists to cover. Kept as a named function rather
    than an inline import so the beat entry reads as a schedule rather than as
    an import statement.
    """
    from app.tasks.futures_categories_warm import warm_period_minutes

    return warm_period_minutes()


celery_app.conf.beat_schedule = {
    "poll-odds-adaptive": {
        "task": "app.tasks.poll_all_odds",
        "schedule": 30.0,
    },
    "poll-datagolf-inplay": {
        # #144: dedicated ~90s in-play golf poll. Decoupled from poll_all_odds
        # (whose tick rate — bounded by live ball-sports — throttled the L2-66
        # piggyback to ~5min in the golf-only summer window). Self-gates on a
        # Redis schedule-window flag so it's a single Redis check off-tournament
        # (near-zero cost). Realtime queue for the fast cadence.
        "task": "app.tasks.poll_datagolf_inplay",
        "schedule": 90.0,
    },
    "refresh-open-commentary": {
        # Same-day live feature (2026-07-19): AI commentary box for The Open
        # Championship. Self-gates on the golf in-play window (cheap Redis skip
        # off-tournament) and generates only while The Open is LIVE — one OpenAI
        # call per run, at most. Background queue (runs the full golf aggregation).
        "task": "app.tasks.refresh_open_commentary",
        "schedule": 180.0,
        "options": {"queue": "background"},
    },
    "poll-mlb-pregame": {
        # MLB-only pre-game tier (issue #892): fills the T-48h..T-2h dark
        # window the 6h-lookahead main loop misses. Self-gates (quota guard,
        # main-loop-active check, no-games check) so most fires are cheap skips.
        "task": "app.tasks.poll_mlb_pregame",
        "schedule": crontab(minute="*/30"),
    },
    "sync-sports-hourly": {
        "task": "app.tasks.sync_sports",
        "schedule": crontab(minute=0),
    },
    "discover-new-events": {
        "task": "app.tasks.discover_events",
        "schedule": crontab(minute="5,35"),  # Every 30 min (was 15)
    },
    "compute-gei-batch": {
        "task": "app.tasks.compute_gei_batch",
        "schedule": crontab(minute="*/30"),  # Every 30 min (was 10)
        "kwargs": {"limit": 50},
    },
    "compute-gei-percentiles-hourly": {
        "task": "app.tasks.compute_gei_percentiles",
        "schedule": crontab(minute=5),
    },
    "poll-futures-every-4h": {
        "task": "app.tasks.poll_futures_odds",
        "schedule": crontab(minute=30, hour="*/4"),  # Every 4 hours — futures change very slowly, quota conservation
    },
    "poll-kalshi": {
        "task": "app.tasks.poll_kalshi_markets",
        "schedule": crontab(minute=45, hour="*/2"),  # Every 2 hours — markets created days ahead, pricing appears day-of
        # #1609 moved this to `heavy` (320.2s p50). Stated LITERALLY rather than
        # left to the post-schedule loop — see the literal-vs-effective note on
        # that loop.
        "options": {"queue": "heavy"},
    },
    "check-kalshi-freshness-daily": {
        "task": "app.tasks.check_kalshi_freshness",
        "schedule": crontab(minute=0, hour=9),  # Daily at 9:00 AM UTC — alert if no updates in 24h
        "options": {"queue": "background"},
    },
    "run-freshness-watchdog": {
        # #995 NEVER-AGAIN: creates-specific freshness + poll phase-heartbeat.
        # Every 10 min so a 10-min event-loop-block heartbeat has resolution;
        # both checks are cheap (2 indexed MAX queries + a few Redis reads).
        "task": "app.tasks.run_freshness_watchdog",
        "schedule": crontab(minute="*/10"),
        "options": {"queue": "background"},
    },
    "poll-polymarket-hourly": {
        "task": "app.tasks.poll_polymarket_markets",
        "schedule": crontab(minute=15),
    },
    "refresh-stale-futures-prices-hourly": {
        # #2199. Runs at :50 — after both discovery polls have had their turn, so
        # this sweeps what they could not reach rather than racing them for the
        # same rows. Hourly matches the 6h staleness window with margin: a market
        # has six chances to be refreshed before it can breach.
        #
        # `heavy`, NOT `background`, and stated literally rather than left to the
        # post-schedule loop. Its 420s wall budget makes it exactly the
        # multi-minute beat the standing background note forbids: that queue has
        # ~one effective slot for ~40 beats, so a task like this does not share
        # it, it closes it. Heavy is the 600s-class isolation lane; the hourly
        # precompute there fires at :15 and cannot collide with :50.
        "task": "app.tasks.refresh_stale_futures_prices",
        "schedule": crontab(minute=50),
        "options": {"queue": "heavy"},
    },
    # UX-P139. Every 10 minutes, and it is cheap because the register bounds
    # it: ~11 Gamma calls for the whole US Open. The hourly scan above cannot
    # reach these markets reliably (offset-2000 cap + rotating cursor), and the
    # bracket grid is 336 of them.
    "refresh-registered-tournament-prices": {
        "task": "app.tasks.refresh_registered_tournament_prices",
        "schedule": crontab(minute="*/10"),
        "options": {"queue": "background"},
    },
    # UX-P139 item 9. Two ESPN scoreboard requests; the route only ever reads
    # what this writes, so no request pays a third-party round trip.
    "sync-tournament-results": {
        "task": "app.tasks.sync_tournament_results",
        "schedule": 180.0,
        "options": {"queue": "background"},
    },
    # Q426. A first-round market can be listed at any hour, and the gap between
    # it being listed and the card showing a number is time the reader spends
    # looking at a blank fixture. Cheap by construction — one indexed query
    # bounded by an explicit series list, then pure in-memory resolution over a
    # few hundred candidates, and no third-party call at all.
    #
    # A CRONTAB, NOT AN INTERVAL, AND THAT IS DELIBERATE. `300.0` here would
    # have joined `BACKGROUND_INTERVAL_FLOOR` — the background beats that fire
    # on a fixed period, which the settlement sweep shares its slot with no
    # matter where it is placed. That set's own rule is `period <= 180.0`: a
    # slower beat is not a continuous floor and must be reasoned about as a
    # discrete co-fire rather than absorbed into "unavoidable anyway".
    #
    # `*/10` RATHER THAN `*/5`, MEASURED NOT ASSUMED. Census over the hour-10
    # window the sweep occupies (10:31 + 13 min), run three ways: baseline
    # **13** fires, `*/10` → **14**, `*/5` → **15**. Five minutes buys a reader
    # nothing here — main-draw markets list hours ahead of the match — and it
    # costs the sweep a second fire inside its own run window. `*/10` also
    # matches `refresh-registered-tournament-prices` exactly, so tournament
    # upkeep reads as one cadence instead of two.
    "link-tournament-matchups": {
        "task": "app.tasks.link_tournament_matchups",
        "schedule": crontab(minute="*/10"),
        "options": {"queue": "background"},
    },
    "enrich-events-hourly": {
        "task": "app.tasks.enrich_events_metadata",
        "schedule": crontab(minute=20),
        "kwargs": {"limit": 50},
    },
    "sync-espn-live": {
        "task": "app.tasks.sync_espn_live_events",
        "schedule": 60.0,
    },
    # THE SPORT `sync-espn-live` NEVER COVERED (lane1/057 STEP 0).
    #
    # A CRONTAB, NOT AN INTERVAL, for the reason `link-tournament-matchups`
    # states three entries below: a numeric schedule joins
    # `BACKGROUND_INTERVAL_FLOOR`, the continuous floor the settlement sweep
    # shares its slot with wherever it is placed. This is tournament upkeep —
    # discrete, bounded, and reasonable to reason about as a co-fire.
    #
    # `*/5`, and the cadence is argued rather than copied. The defect it closes
    # persists for HOURS unattended (Bergs v Taberner carried a phantom
    # completion from 02:40Z to past 21:00Z), and the standing bar is that
    # nothing the authority knows about is wrong for more than an hour — so five
    # minutes is not a latency requirement, it is a wide margin under one. It is
    # slower than `tournament_slate`'s three-minute read of the same scoreboard
    # ON PURPOSE: the slate renders the live card, so it wants the tighter
    # rhythm, while this writes the durable row and wants the cheaper one.
    "sync-tennis-from-espn": {
        "task": "app.tasks.sync_tennis_from_espn",
        "schedule": crontab(minute="*/10"),
        "options": {"queue": "background"},
    },
    # THE SCORE HALF OF THE SAME RAIL, AT A DIFFERENT CADENCE (live/058, #2746).
    #
    # `20.0`, and the number is derived rather than picked. The acceptance bar is
    # a MEDIAN under 30 s from ESPN publishing to our card showing, and the two
    # terms that make it up are both grids we control:
    #
    #     write grid   20 s  -> median 10 s (uniform over the interval)
    #     read cache   10 s  -> median  5 s  (`_EVENT_DETAIL_LIVE_TTL_TENNIS`)
    #                          ───────
    #                           15 s, plus the fetch itself
    #
    # Halving this to 10 s buys 5 s of median against double the requests, which
    # is the wrong trade under a 30 s bar; doubling it to 40 s spends the whole
    # margin on the write grid alone. The read cache is the other half and is
    # named here because tuning one without the other is how a beat gets faster
    # and the card does not (LAT-P187: an endpoint is not a surface).
    #
    # TWO ESPN requests per pass, AND ONLY WHEN A LIVE TENNIS ROW EXISTS — the
    # task's population query runs before any fetch and returns `no_live_tennis`
    # when it is empty. Off-season that is every pass, for the cost of one
    # indexed query.
    "poll-live-tennis-scores": {
        "task": "app.tasks.poll_live_tennis_scores",
        "schedule": 20.0,
        "options": {"queue": "realtime"},
    },
    "backfill-team-logos": {
        "task": "app.tasks.backfill_team_logos",
        "schedule": crontab(minute=15, hour="*/6"),
    },
    "heartbeat": {
        "task": "app.tasks.heartbeat",
        "schedule": 60.0,
    },
    "transition-event-statuses": {
        "task": "app.tasks.transition_event_statuses",
        "schedule": 60.0,
    },
    "match-prediction-markets": {
        "task": "app.tasks.match_prediction_markets",
        "schedule": crontab(minute="5,20,35,50"),  # Every 15 min — link new markets ASAP
        "kwargs": {"limit": 500},
        # #1609 moved this to `heavy` (337.4s p50 / 699.4s p95 — 77.7% of one
        # background slot at p95, the single biggest starver). Stated LITERALLY.
        "options": {"queue": "heavy"},
    },
    "matching-reconciliation": {
        "task": "app.tasks.matching_reconciliation",
        # Every matching cycle, 7 minutes behind it. The matcher fires at
        # :05/:20/:35/:50 and takes 337s p50, so :12 reads a cycle that has
        # usually just finished; on a p95 run it reads the previous cycle's
        # result instead, which is a staleness of one cycle and not a
        # correctness problem for a read-only regression check.
        "schedule": crontab(minute="12,27,42,57"),
        "options": {"queue": "heavy"},
    },
    # DISABLED: replaced by worker-ws WebSocket consumer (#836/#837).
    "poll-live-prediction-markets": {
        "task": "app.tasks.poll_live_prediction_markets",
        "schedule": 120.0,  # Every 2 minutes — covers live + upcoming (3h) games
    },
    "sync-mlb-win-probability": {
        "task": "app.tasks.sync_mlb_win_probability",
        "schedule": 120.0,  # Every 2 minutes during MLB season
    },
    "compute-game-moments": {
        "task": "app.tasks.compute_game_moments",
        "schedule": crontab(minute=20, hour="*/2"),  # Every 2h — offline join over recently-completed MLB games
    },
    "track-statpal-usage": {
        "task": "app.tasks.track_statpal_usage",
        "schedule": crontab(minute="*/15"),  # Every 15 minutes
    },
    "check-tier1-coverage": {
        "task": "app.tasks.check_tier1_coverage",
        "schedule": crontab(minute=30),  # Every hour at :30
    },
    "backfill-team-links": {
        "task": "app.tasks.backfill_team_links",
        "schedule": crontab(minute=50),  # Every hour — roster matching is cheap, large backlog to clear
        "kwargs": {"limit": 2000, "use_llm": False},
    },
    # #1798 / ruling 048: the reconciliation drain the acceptance ASSUMED.
    # Runs 12 minutes before the half-hour merge sweep so an id that arrived
    # since the last cycle is reconciled into a drainable pair before the
    # ordinary drain looks. DRY-RUN until Alex rules on the apply — the census
    # and its verdict are the point of scheduling it now, because an unmeasured
    # cost cannot be called bounded.
    "reconcile-unanchored-events": {
        "task": "app.tasks.reconcile_unanchored_events",
        "schedule": crontab(minute="18,48"),
        "kwargs": {"apply": False, "limit": 1000},
        "options": {"queue": "background"},
    },
    "merge-duplicate-events": {
        "task": "app.tasks.merge_duplicate_events",
        "schedule": crontab(minute="*/30"),  # Every 30 min (was 10)
        "kwargs": {"dry_run": False},
    },
    "merge-degenerate-combat-events": {
        # #175 Item 3 — self-heal the "15132461 class": degenerate home==away
        # fight events (a combat market whose matchup parsed to one competitor)
        # get folded into their real odds-registry event so the page unifies and
        # the Kalshi market repoints. Every 6h catches weekend fight-night events
        # same-day. Idempotent (skips 0/>1 real matches; never guesses).
        "task": "app.tasks.merge_degenerate_combat_events",
        "schedule": crontab(minute=25, hour="*/6"),
        "kwargs": {"dry_run": False, "limit": 500},
        "options": {"queue": "background"},
    },
    "canonicalize-entities-daily": {
        # #175 Item 1 — self-heal same-family duplicate person/team entities
        # (edition-multiplied across sport_keys). Idempotent: a clean registry
        # yields 0 merges. Census-gated so cross-family homonyms are left apart.
        # Also runs post-seed inside seed_entity_registry_impl; the two paths are
        # safe to overlap because each merge is a no-op once collapsed.
        "task": "app.tasks.canonicalize_entities",
        "schedule": crontab(minute=15, hour=8),  # Daily 08:15 UTC
        "kwargs": {"dry_run": False},
        "options": {"queue": "background"},
    },
    "sync-rosters-daily": {
        "task": "app.tasks.sync_rosters",
        "schedule": crontab(minute=0, hour=10),  # Daily at 10:00 AM UTC — moved from 7 AM to avoid contention with snapshot collapse tasks
    },
    # StatPal schedule sync — one per major sport to avoid timeout
    # (soccer returns thousands of global fixtures and overwhelms a single run)
    "sync-statpal-schedules-nba": {
        "task": "app.tasks.sync_statpal_schedules",
        "schedule": crontab(minute=0),
        "kwargs": {"sport_key": "basketball_nba"},
    },
    "sync-statpal-schedules-nhl": {
        "task": "app.tasks.sync_statpal_schedules",
        "schedule": crontab(minute=1),
        "kwargs": {"sport_key": "icehockey_nhl"},
    },
    "sync-statpal-schedules-mlb": {
        "task": "app.tasks.sync_statpal_schedules",
        "schedule": crontab(minute=2),
        "kwargs": {"sport_key": "baseball_mlb"},
    },
    "sync-statpal-schedules-nfl": {
        "task": "app.tasks.sync_statpal_schedules",
        "schedule": crontab(minute=3),
        "kwargs": {"sport_key": "americanfootball_nfl"},
    },
    "sync-statpal-injuries": {
        "task": "app.tasks.sync_statpal_injuries",
        "schedule": crontab(minute=20),  # Hourly at :20 — injuries cached with 2h TTL anyway (was every 15 min)
    },
    "sync-statpal-live-plays": {
        "task": "app.tasks.sync_statpal_live_plays",
        "schedule": 60.0,  # Every 60 seconds — play-by-play for live NFL games only
    },
    "sync-statpal-livescores": {
        "task": "app.tasks.sync_statpal_livescores",
        "schedule": 30.0,  # Every 30 seconds — real-time scores for all live games
    },
    "sync-statpal-rosters-daily": {
        "task": "app.tasks.sync_statpal_rosters",
        "schedule": crontab(minute=30, hour=7),  # Daily at 7:30 AM UTC — after ESPN roster sync (7:00)
    },
    "sync-statpal-standings-daily": {
        "task": "app.tasks.sync_statpal_standings",
        "schedule": crontab(minute=0, hour=8),  # Daily at 8:00 AM UTC
    },
    "sync-statpal-team-stats-weekly": {
        "task": "app.tasks.sync_statpal_team_stats",
        "schedule": crontab(minute=0, hour=9, day_of_week=1),  # Weekly Monday 9:00 AM UTC
    },
    # #975: weekly roll-up of external feature-request shakes into one digest issue
    "digest-external-feature-requests-weekly": {
        "task": "app.tasks.digest_external_feature_requests",
        "schedule": crontab(minute=0, hour=14, day_of_week=1),  # Weekly Monday 2:00 PM UTC
        "options": {"queue": "background"},
    },
    # #836 Batch 2 (SHADOW): refresh the WS-shadow-vs-current match rate for review
    "compare-ws-shadow": {
        "task": "app.tasks.compare_ws_shadow",
        "schedule": crontab(minute=20, hour="*/6"),
        "options": {"queue": "background"},
    },
    # March Madness bracket sync — disabled (season over). Re-enable in March.
    # "sync-mm-bracket": {
    #     "task": "app.tasks.sync_mm_bracket",
    #     "schedule": crontab(minute="*/15", hour="*", day_of_month="15-30", month_of_year="3,4"),
    # },
    "enrich-market-hooks": {
        "task": "app.tasks.enrich_market_hooks",
        # Feed-prioritized only; keep volume modest to avoid spending on the
        # entire open-market backlog.
        "schedule": crontab(minute=40, hour="*/6"),
        "kwargs": {"limit": 100},
    },
    "enrich-discover-llm-metadata": {
        "task": "app.tasks.enrich_discover_llm_metadata",
        # Async/cached only: enrich feed-shaped cards, never on feed request.
        "schedule": crontab(minute=10, hour="*/6"),
        "kwargs": {"limit": 125},
    },
    "enrich-snippet-angles": {
        "task": "app.tasks.enrich_snippet_angles",
        "schedule": crontab(minute=30, hour="*/6"),
        "kwargs": {"limit": 125},
        "options": {"queue": "background"},
    },
    "enrich-cu-v2-profiles": {
        "task": "app.tasks.enrich_cu_v2_profiles",
        "schedule": crontab(minute=50, hour="*/12"),
        "kwargs": {"limit": 125},
        "options": {"queue": "background"},
    },
    "generate-discover-comparison-candidates": {
        "task": "app.tasks.generate_discover_comparison_candidates",
        "schedule": crontab(minute=20, hour=9),
        "kwargs": {"limit": 60},
    },
    "evaluate-discover-with-llm-daily": {
        "task": "app.tasks.evaluate_discover_with_llm",
        "schedule": crontab(minute=35, hour=9),
        "kwargs": {"limit": 50},
    },
    "snapshot-discover-ground-truth-diagnostics-daily": {
        "task": "app.tasks.snapshot_discover_ground_truth_diagnostics",
        "schedule": crontab(minute=50, hour=9),
        "kwargs": {"limit": 50},
        "options": {"queue": "background"},
    },
    # #142/RANK-2: human-label gold-set eval, snapshotted daily so tapworthy@20 /
    # boring@20 / love-recall trend over time and thin strata surface.
    "snapshot-discover-label-eval-run-daily": {
        "task": "app.tasks.snapshot_discover_label_eval_run",
        "schedule": crontab(minute=55, hour=9),
        "options": {"queue": "background"},
    },
    # #142/RANK-2: pre-ranking candidate-pool snapshot for the offline replay
    # harness (per-candidate features + served rank + score anatomy).
    "snapshot-discover-candidate-pool-daily": {
        "task": "app.tasks.snapshot_discover_candidate_pool",
        "schedule": crontab(minute=5, hour=10),
        "kwargs": {"limit": 300, "retention_days": 30},
        "options": {"queue": "background"},
    },
    "import-external-curator-ground-truth-daily": {
        "task": "app.tasks.import_external_curator_ground_truth",
        "schedule": crontab(minute=45, hour=9),
        "options": {"queue": "background"},
    },
    "check-ground-truth-health-daily": {
        "task": "app.tasks.check_ground_truth_health",
        "schedule": crontab(minute=40, hour=9),
        "options": {"queue": "background"},
    },
    "capture-featured-markets-daily": {
        "task": "app.tasks.capture_featured_markets",
        "schedule": crontab(minute=0, hour=6),  # Daily at 6:00 AM UTC
        "options": {"queue": "background"},
    },
    "enrich-market-images": {
        "task": "app.tasks.enrich_market_images",
        "schedule": crontab(minute=50, hour="*/4"),  # 6x daily — fetch Pexels images
        "kwargs": {"limit": 200},
    },
    "enrich-tmdb-images": {
        "task": "app.tasks.enrich_tmdb_images",
        "schedule": crontab(minute=35, hour="*/6"),  # #882: real TMDB art for quoted-title entertainment
        "kwargs": {"limit": 50},
        "options": {"queue": "background"},
    },
    "backfill-image-dimensions": {
        "task": "app.tasks.backfill_image_dimensions",
        # Every 6h at :05. THE CADENCE IS DERIVED FROM THE POPULATION, not
        # chosen: 6,034 distinct un-sized photos back the open markets, so at
        # 150 per pass this drains in ~10 days and then idles at zero work
        # forever — it only wakes up again for newly-enriched artwork.
        "schedule": crontab(minute=5, hour="*/6"),
        "kwargs": {"limit": 150},
        "options": {"queue": "background"},
    },
    "precompute-interestingness": {
        "task": "app.tasks.precompute_interestingness",
        "schedule": crontab(minute=20, hour="*/2"),  # Every 2 hours at :20
        "options": {"queue": "background"},
    },
    "precompute-category-pages": {
        "task": "app.tasks.precompute_category_pages",
        "schedule": crontab(minute=25),  # Every hour at :25 — warm caches for politics/entertainment/economics/weather
        "options": {"queue": "background"},
    },
    "warm-prop-families": {
        "task": "app.tasks.warm_prop_families",
        # Hourly at :43 (LAT-P138). THE PERIOD IS DERIVED FROM COVERAGE, not
        # chosen. Each pass is budgeted in SECONDS (the build is 2.6-16.8s and
        # varies with roster size), so what the cadence has to satisfy is:
        #
        #   passes to cover a full list x period  <=  the mirror's lifetime
        #   ceil(200 / (180 // 17)) x 3600 = 20 x 3600 = 72,000s  <=  86,400s
        #
        # i.e. even at the pessimistic rate of one slowest-measured build per
        # team, every team in a maxed-out reachable set is rebuilt inside the 24h
        # mirror with four hours to spare. `test_the_cadence_covers_the_reachable
        # _set_inside_the_mirror` asserts that arithmetic from the constants, so
        # widening the cap or shrinking the budget moves the cadence instead of
        # quietly leaving teams uncovered.
        #
        # It is NOT sub-TTL of the 900s primary, on purpose. Past the primary a
        # reader gets the mirror in milliseconds and schedules one rebuild, so
        # that expiry is a freshness event, not a latency one; chasing it would
        # be 82 multi-second rebuilds every fifteen minutes to save nobody
        # anything.
        #
        # 🔴 THE FIRE MINUTE IS :53 AND IT WAS MOVED THERE BY A CENSUS, NOT
        # CHOSEN. The first draft fired at :43, which lands inside the nightly
        # settlement sweep's own 10:31+13m window — `test_the_run_window_does_
        # not_sit_under_a_growing_pile` went red at 15 co-fires against a
        # declared ceiling of 14. Ceilings like that exist to be respected, not
        # re-derived upward for the convenience of the beat that broke them
        # (#1910), so this moved instead. A minute census over the assembled
        # schedule says :53 carries one other beat, against 33 at :00, 24 at :30
        # and 15 at :45.
        "schedule": crontab(minute=53),
        "options": {"queue": "background"},
    },
    "warm-event-concepts": {
        "task": "app.tasks.warm_event_concepts",
        # Every 5 min — keep the four golf-major concept payloads content-fresh
        # (#1107, LAT-P021). NOT sub-TTL on purpose: the primary TTL is 60s and
        # the four builds measured ~82s, so a sub-60s cadence cannot finish. It
        # does not need to — `routes/event.py` serves the 24h mirror on a miss
        # in ~0.44s and schedules one revalidation, so this cadence governs
        # content freshness, not user-visible latency.
        "schedule": crontab(minute="*/5"),
        "options": {"queue": "background"},
    },
    "warm-futures-categories": {
        "task": "app.tasks.warm_futures_categories",
        # LAT-P137. The Search page's category grid. LAT-P122 gave that census a
        # shared slot and a 24h mirror but no producer, so the tier still costs
        # 1,365 ms — measured on production 2026-08-30 — to whoever opens
        # `/search` more than `stale_serve_ceiling_seconds()` (25 min) after the
        # last build. This beat is that producer.
        #
        # 🔴 THE PERIOD IS DERIVED, NOT TYPED. `warm_period_minutes()` divides
        # the tier's own stale-serve ceiling by one more than the number of
        # missed deliveries it must survive, so a queue that shortens the
        # ceiling shortens this cadence with it instead of leaving a warmer
        # that quietly no longer covers the gap it was added for (#2236's
        # shape: a 120 in one file and a 60 in another with nothing comparing
        # them).
        #
        # COST, stated: one build per period. The build is 1.37-1.59 s measured,
        # so at */5 this is ~0.46 % of one `background` slot-day — declared here
        # rather than left for the next re-derivation of BACKGROUND_BEAT_COUNT
        # to discover.
        "schedule": crontab(minute=f"*/{_futures_categories_warm_minutes()}"),
        "options": {"queue": "background"},
    },
    "warm-typeahead": {
        "task": "app.tasks.warm_typeahead",
        # Every 30s — keep the head of the `/typeahead` distribution warm
        # (#1866, LAT-P056). THE NUMBER IS MEASURED, and the first draft of this
        # entry had it wrong at */2 min, which is why the measurement exists.
        #
        # The cost being avoided is not compute, it is a cold read: same query,
        # same plan, same rows, 1094.5ms with 710 `Shared Read Blocks` vs 27.1ms
        # with 0. So the cadence question is "how long do the pages stay
        # resident", and that was measured directly with EXPLAIN (ANALYZE,
        # BUFFERS) on production rather than reasoned about:
        #
        #     t=0 cold  245 read blocks / 221.7ms
        #     t=2s        0 / 35.5ms      t=30s   0 / 16.8ms
        #     t=15s       0 /  7.2ms      t=45s   0 /  9.9ms
        #     ...and a second query at t=60s: 701 blocks, fully EVICTED.
        #
        # Residency survives 45s and is gone by 60s, so a 2-minute cadence would
        # have left the pages cold for most of every interval — the warmer would
        # have run, reported success, and delivered nothing. 30s sits inside the
        # measured window with margin.
        #
        # 30s ALSO sits inside the route's 45s response TTL, which is the
        # stronger of the two effects and the one the head actually rides on: a
        # head entry refreshed every 30s never expires, so those users never
        # reach the database at all. Page residency is the weaker, shared
        # benefit that reaches tail queries too — real, but decaying inside a
        # minute, so it is not what the head's guarantee rests on.
        #
        # Why eviction is that fast: `ix_futures_outcomes_name_trgm` (406 MB) +
        # `ix_futures_name_trgm` (172 MB) want 56% of a 1 GB `shared_buffers`,
        # and the prediction-market matcher sweeps it every 15 min with 13-21s
        # scans over a 977 MB table.
        #
        # A cold run cannot pile up behind the next beat: the task takes a Redis
        # single-run lock and SKIPS if one is already in flight.
        #
        # ⚠️ 30.0 -> 10.0, LAT-P062. THE BEAT IS NO LONGER THE CADENCE; THE
        # FLOOR IS. Read the two together or neither makes sense.
        #
        # At a 30s beat the single-run lock QUANTISED the pass period: a pass
        # measures 27-38s wall, so it does not fit inside one beat, the next
        # beat skips on the lock, and the real period jumps to ~60s — against a
        # 45s response TTL. Measured on production v3829 over two settled
        # reads: 27 real passes / 1396s and 31 / 1319s, mean period **51.7s and
        # 42.5s**, straddling the TTL. Duty cycle 16/24 and 19/24.
        #
        # The pass/skip sequence shows it is a VARIANCE problem, not a mean one
        # (the 42.5s mean is already under 45s):
        #
        #     PPPPPPPP.P...P...P.PPPPPPP...PPPPPPPPP.P.P...P...P
        #
        # The `PPPPPPPPP` stretches run at a ~31s period and are 100% warm; the
        # `P...P...P` stretches run one pass per four beats, near 105s, and the
        # head is dead for most of it.
        #
        # period = beat * ceil(wall / beat). At beat 30 with wall 27-38 that is
        # {30, 60}; at beat 10 it is {30, 40} — both under the 45s TTL.
        #
        # A shorter beat on its own would also remove the only bound on how
        # OFTEN the warmer may run, and the warmer is not free: it holds the
        # database 73% of wall-clock at concurrency 4, ~2.9 backend-equivalents
        # against a production baseline of ~3 ACTIVE backends. So the bound
        # moves into the task as `MIN_PASS_PERIOD_SECONDS = 30`, which caps the
        # load increase at +42% worst case (+6% to +29% expected).
        #
        # Consequence for whoever reads `recent_durations_ms` next: at beat 10
        # roughly three of every four invocations are ~10ms lock skips, so the
        # 50-entry window now covers ~12 real passes rather than ~27. Read the
        # summary's new `period_s` field instead of reconstructing the cadence
        # from the duration histogram — that is what it is for.
        #
        # Registered prediction and grading rows: `lat-p062-warmer-graded.md` §3.
        "schedule": 10.0,
        "options": {"queue": "background"},
    },
    "rebuild-typeahead-index": {
        "task": "app.tasks.rebuild_typeahead_index",
        # Option D (#1866). :23 and :53 — deliberately in the quiet half of the
        # hour, clear of `prediction_market_match` (:05/:20/:35/:50) and of
        # `precompute_calibration_main` (:15), the two things that can hold both
        # `heavy` slots. A 90s-capped pass twice an hour is ~2.5% of ONE of
        # heavy's two slots.
        #
        # WHY IT IS ON `heavy` AT ALL, since #1609 just loaded that lane: the
        # alternative is `background`, which is the queue #1609 proved has ~one
        # effective slot and whose depth read 3,014 at LAT-P067's Phase 0. A new
        # latency-tolerant multi-minute resident belongs there least of all.
        #
        # Incremental by design: the upsert only writes rows whose content_hash
        # actually changed, so a steady-state pass is nearly free and `written`
        # is a real measure of change rather than of activity. The FIRST fill is
        # ~380k rows and is NOT meant to happen here — it is a one-off dyno run
        # with a 1500s budget (see the task docstring), which is condition 3 of
        # the assigned migration slot.
        "schedule": crontab(minute="23,53"),
        "options": {"queue": "heavy"},
    },
    "warm-search-head": {
        "task": "app.tasks.warm_search_head",
        # Every 20s — LAT-P090/#2211. The BEAT is the fire rate; the PASS rate is
        # bounded separately at 45s inside the task
        # (`MIN_PASS_PERIOD_SECONDS`), so roughly two of every three fires take
        # the ~10ms floor-skip path. That split is deliberate and it is the
        # lesson from `warm-typeahead` directly above: a beat that is also the
        # only bound on how often a warmer may run cannot be shortened to close a
        # duty-cycle hole without also multiplying the load.
        #
        # WHY 45/60/25 AND NOT SOME OTHER TRIPLE. An entry lives 60s
        # (`SEARCH_RESPONSE_TTL_SECONDS`); a pass arrives at worst every 45s and
        # rebuilds anything with under 25s left. The head never goes cold iff
        # `45 < 60` and `60 - 45 <= 25`, both of which hold with margin.
        # `test_the_refresh_ahead_window_actually_keeps_the_head_alive` asserts
        # the relation rather than the numbers, because tuning one of the three
        # alone is how `/typeahead` sat at a 47% duty cycle for two cycles while
        # reporting 40/40 every pass.
        #
        # ✅ IT SHIPS ENABLED SINCE LAT-P102. It shipped DISABLED under LAT-P090
        # because #1916 blocks sourcing a warmer head from `search_query_logs`
        # until a clean distribution exists. That distribution turned out to be
        # readable without a migration — `session_id` is a write-time flag every
        # real client attaches and no probe does — so the block moved out of the
        # env var and into the head QUERY, which filters to attested rows and
        # floors on distinct sessions. See `search_head_warmer`'s docstring for
        # the census (the table is 99.66% session-less automation).
        #
        # COST, RE-STATED FOR THE ENABLED STATE, and it is far below the estimate
        # this comment used to carry. The bound is `min(8, terms two different
        # sessions asked in 30 days)`, and at the 2026-08-27 census that is
        # exactly ONE term. So a steady-state pass rebuilds 1 `/search` answer,
        # not 8: ~1-2s of database time per 45s against `background`'s roughly
        # one effective slot (#1609). The 8-at-~4-8s figure is the CEILING the
        # head would have to grow into, and it can only get there by real people
        # asking the same questions. Every knob is set below its
        # `warm-typeahead` sibling's (8 terms not 40, width 2 not 4, floor 45s
        # not 30s) precisely because a `/search` call is the heavier one.
        #
        # `background` rather than `heavy`: heavy is the calibration/precompute
        # family and a user-latency warmer does not belong behind a 25-minute
        # calibration pass. Same queue as `warm-typeahead`, and the contention
        # that creates is declared for Integrator review rather than discovered.
        "schedule": 20.0,
        "options": {"queue": "background"},
    },
    "flush-search-gin-pending-lists": {
        "task": "app.tasks.flush_search_gin_pending_lists",
        # Every 2 min — LAT-P109/#2255. NOT a warmer: there is nothing to warm
        # and nothing to invalidate. It moves index entries that already exist
        # from the GIN pending list into the tree, which is work an inserting
        # backend would do anyway at the 4 MB limit; this takes it off the read
        # path instead of leaving it on a coin flip.
        #
        # WHY 2 MINUTES. The pending lists refill at a measured rate:
        # `futures_outcomes.name` ~50 pages/min, `events.home_team_name` ~20.
        # The limit is 512 pages (4 MB) and the reader pays the WHOLE list on
        # every scan, so the cost a search sees is linear in how long the list
        # has been accumulating. At 2 min the worst case is ~100 pages (~10 ms
        # per index) against the 512-page (~50-92 ms per index) sawtooth peak
        # this replaces. A shorter beat buys progressively less; a longer one
        # lets `futures_outcomes` — the most expensive of the seven — get most
        # of the way back to the limit between passes.
        #
        # `background` rather than `realtime`: this is maintenance, and it must
        # never contend with the 2-minute live price poll it shares a period
        # with. `expires` is set so a backlogged queue drops stale fires rather
        # than running a pile of them back to back — a flush that is two
        # minutes late has been superseded by the next one.
        "schedule": 120.0,
        "options": {"queue": "background", "expires": 110},
    },
    "typeahead-index-sentinel": {
        "task": "app.tasks.typeahead_index_sentinel",
        # Option D's D4 gate. 07:50 UTC — daily, and deliberately AFTER the
        # 07:45 settled-concept sentinel so it never contends inside #233's
        # protected morning window. ~5s, detect-only, files nothing.
        #
        # It ships in the SAME commit as the table on purpose. A second copy of
        # truth with no sentinel is the next gotcha #53 entry, and #1866 has
        # supplied three of them already.
        "schedule": crontab(hour=7, minute=50),
        "options": {"queue": "heavy"},
    },
    "precompute-discover-candidate-base": {
        "task": "app.tasks.precompute_discover_candidate_base",
        # Every 2 min — keep the anonymous Discover candidate-ID base warm so cold
        # feed pages skip the ~3–6s nine-query discovery (Queue 285). The 60s
        # freshness window (CANDIDATE_BASE_FRESH_SECONDS) enforces the "no looser
        # than the anon feed freshness contract" bound; the bounded last-good key
        # + request-path publish keep cold pages covered between beats.
        "schedule": crontab(minute="*/2"),
        "options": {"queue": "background"},
    },
    "prewarm-live-feed-shapes": {
        "task": "app.tasks.prewarm_live_feed_shapes",
        # #2236. The beat above cannot cover a payload whose stale mirror dies at
        # 60s — it ticks at 120s, so the key is gone for a full minute before its
        # next chance. This is the narrow republisher for exactly those shapes.
        #
        # The period is IMPORTED from `feed_cache.py`, where it sits three lines
        # under `FEED_RESPONSE_STALE_TTL_LIVE_SECONDS`. That is the whole repair:
        # #2236 was a 120 here and a 60 there with nothing comparing them, and a
        # literal in this file would rebuild that arrangement exactly. Whoever
        # next shortens the live ceiling will now be editing the period's
        # neighbour, and `test_feed_live_prewarm.py` fails if they do not.
        #
        # Cost: `HGETALL` on an empty live set when nothing is live (the common
        # case, and the reason a 40s beat is affordable at all), otherwise one
        # feed build per LIVE shape inside a 20s pass budget.
        #
        # `realtime`, NOT `background` — and both routing surfaces say so, since
        # beat options override `task_routes` and a disagreement would make the
        # queue depend on whether the task was published by beat or by hand. The
        # argument is at the `task_routes` entry: a 40s deadline cannot survive a
        # queue whose own budget module documents multi-minute co-tenant waits.
        "schedule": float(FEED_LIVE_REPUBLISH_PERIOD_S),
        "options": {"queue": "realtime"},
    },
    "precompute-backfill-winners-status": {
        "task": "app.tasks.precompute_backfill_winners_status",
        "schedule": crontab(minute=35),  # Every hour at :35 — cache expensive backfill status queries
        "options": {"queue": "heavy"},
    },
    "precompute-backfill-progress": {
        "task": "app.tasks.precompute_backfill_progress",
        "schedule": crontab(minute="*/15"),  # Every 15 min — #179/#1052 progress census (density + June ledger)
        # RULING 110 (LAT-P077): moved background -> heavy under the scoped
        # two-task exception. Literal must match the effective queue, which
        # `test_heavy_beat_literals_match_their_effective_queue` reads from
        # SOURCE TEXT — a revert must change this line too, not just HEAVY_TASKS.
        "options": {"queue": "heavy"},
    },
    "backfill-combat-wps": {
        "task": "app.tasks.backfill_combat_wps",
        "schedule": crontab(minute=50, hour=9),  # Daily 09:50 UTC — self-heal the settled-fight blend tail (#178)
        "options": {"queue": "background"},
    },
    "check-aggregation-quality": {
        "task": "app.tasks.check_aggregation_quality",
        "schedule": crontab(minute=0, hour=7),  # Daily at 7:00 AM UTC
    },
    "update-max-movement": {
        "task": "app.tasks.update_max_movement",
        "schedule": crontab(minute="*/10"),  # Every 10 minutes
        "options": {"queue": "background"},
    },
    "collapse-odds-snapshots-daily": {
        "task": "app.tasks.collapse_snapshots",
        "schedule": crontab(minute=30, hour=6),  # Daily at 6:30 AM UTC
        "kwargs": {"table": "odds", "limit": 500},
    },
    "collapse-winprob-snapshots-daily": {
        "task": "app.tasks.collapse_snapshots",
        "schedule": crontab(minute=35, hour=6),  # Daily at 6:35 AM UTC
        "kwargs": {"table": "winprob", "limit": 500},
    },
    "collapse-futures-snapshots-daily": {
        "task": "app.tasks.collapse_snapshots",
        "schedule": crontab(minute=40, hour=6),  # Daily at 6:40 AM UTC
        "kwargs": {"table": "futures", "limit": 500},
    },
    "turbo-collapse-futures": {
        "task": "app.tasks.turbo_collapse_futures",
        "schedule": crontab(minute=30, hour="*/6"),  # Every 6 hours — catch up on backlog
        "kwargs": {"limit": 5000},
    },
    "turbo-collapse-odds": {
        "task": "app.tasks.turbo_collapse_odds",
        "schedule": crontab(minute=45, hour="*/6"),  # Every 6 hours
        "kwargs": {"limit": 5000},
    },
    "matching-metrics-daily": {
        "task": "app.tasks.compute_matching_metrics",
        "schedule": crontab(minute=0, hour=10),  # Daily at 10:00 AM UTC
    },
    "check-data-quality-daily": {
        "task": "app.tasks.check_data_quality",
        "schedule": crontab(minute=0, hour=11),  # Daily at 11:00 AM UTC (4 AM PT)
    },
    "data-quality-watchdog": {
        "task": "app.tasks.run_data_quality_watchdog",
        "schedule": crontab(minute=45, hour="*/2"),  # Every 2 hours at :45
        "options": {"queue": "background"},
    },
    "calibration-sentinel-weekly": {
        # #1054: self-serve calibration break detection → evidence pack → issue
        # filing. Weekly (Monday 06:20 UTC) — resolved-outcome cohorts move slowly,
        # and the new-format early-warning tier catches a broken format long before
        # a 50K-outcome pileup, so a weekly cadence is enough. heavy queue (#233).
        "task": "app.tasks.calibration_sentinel",
        "schedule": crontab(minute=20, hour=6, day_of_week=1),  # Weekly Monday 06:20 UTC
        "options": {"queue": "heavy"},
    },
    "mlb-schedule-coverage-daily": {
        # #1201/#1193/#1202: daily MLB schedule self-heal + coverage. Runs at 07:05
        # UTC — 5 min BEFORE the flow sentinel (07:10) — so the standing inverted /
        # future-settled MLB rows (gotcha #32/#46) are re-dated/voided and the
        # official-slate reconciliation is fresh when resolved_state reads. heavy
        # queue (#233 — must fire promptly; no bg starvation).
        "task": "app.tasks.mlb_schedule_coverage",
        "schedule": crontab(minute=5, hour=7),  # Daily 07:05 UTC
        "options": {"queue": "heavy"},
    },
    "flow-sentinel-daily": {
        # #1078: scripted user-flow acceptance sentinel against production. Daily
        # (07:10 UTC) — user-facing regressions (search break, unmerged dup,
        # empty live game, resolved-shown-as-live, dark charts, empty category)
        # need faster detection than the weekly calibration cadence. Files one
        # deduped issue per failing flow. heavy queue (#233 — no bg starvation).
        "task": "app.tasks.flow_sentinel",
        "schedule": crontab(minute=10, hour=7),  # Daily 07:10 UTC
        "options": {"queue": "heavy"},
    },
    "grid-sentinel-daily": {
        # Queue #196: championship grid reliability sentinel. Daily (07:25 UTC,
        # after the flow sentinel) — grid defects (missing teams/columns,
        # monotonicity, envelope corruption, stale-when-active futures) need
        # daily detection. Classifies findings against the season-window artifact
        # registry so RED means REAL; files one deduped issue per RED league.
        # heavy queue (#233).
        "task": "app.tasks.grid_sentinel",
        "schedule": crontab(minute=25, hour=7),  # Daily 07:25 UTC
        "options": {"queue": "heavy"},
    },
    "grid-register-sentinel-daily": {
        # Queue #295: diff every committed grid register against live source
        # inventory. Runs at 07:32 UTC — after the grid sentinel (07:25) so the
        # two never contend for the heavy dyno, and before the horizon sentinel
        # (07:40). Dry-run by default: it proposes and reports versions but does
        # not publish until apply=True is passed explicitly.
        "task": "app.tasks.grid_register_sentinel",
        "schedule": crontab(minute=32, hour=7),  # Daily 07:32 UTC
        "options": {"queue": "heavy"},
    },
    "tournament-register-sentinel-daily": {
        # UX-P134: the US Open register goes live for main-draw Sunday, so its
        # daily drift guard registers now. 07:36 UTC — after the grid register
        # sentinel (07:32) and before the horizon sentinel (07:40), so the
        # three never contend for the heavy dyno. Detect-and-file only; there
        # is no apply flag because a committed register is never republished by
        # a task.
        "task": "app.tasks.tournament_register_sentinel",
        "schedule": crontab(minute=36, hour=7),  # Daily 07:36 UTC
        "options": {"queue": "heavy"},
    },
    "horizon-sentinel-daily": {
        # Queue #223: marquee-event early-warning sentinel. Daily (07:40 UTC,
        # after the grid sentinel) — reads THE HORIZON CALENDAR
        # (app/config/majors_calendar.yaml) and escalates each major as it nears
        # (T-30 candidate, T-14 needs-page, T-7 marquee escalation,
        # IN-PROGRESS-WITHOUT-PAGE = P0), filing one deduped issue per uncovered
        # event so a marquee never arrives without a page. heavy queue (#233).
        "task": "app.tasks.horizon_sentinel",
        "schedule": crontab(minute=40, hour=7),  # Daily 07:40 UTC
        "options": {"queue": "heavy"},
    },
    "settled-concept-sentinel-daily": {
        # Queue #226: within ~24h of any marquee concept settling (THE HORIZON
        # CALENDAR knows the dates), assert the settled contract on the LIVE
        # event-concept surface — champion hero, field membership, evolution chart
        # resolves, no double-graded round markets — classifying REAL vs EXPLAINED
        # so RED means REAL, filing one deduped issue per concept with REAL
        # defects. The guard #225 earned. Daily (07:45 UTC, after the horizon
        # sentinel). heavy queue (#233).
        "task": "app.tasks.settled_concept_sentinel",
        "schedule": crontab(minute=45, hour=7),  # Daily 07:45 UTC
        "options": {"queue": "heavy"},
    },
    "board-sentinel-daily": {
        # Queue #258: keep the BOARD honest so GitHub `Ready` stays a trustworthy
        # execution source — duplicate sentinel fingerprints, stale Inbox cards,
        # template-P1 share, blocked-in-Inbox, missing area labels. Classifies REAL
        # vs UNKNOWN so RED means real; files one deduped cleanup issue and closes
        # it on green via the shared filing rail. Daily (07:50 UTC, after the other
        # sentinels so it observes a settled board). heavy queue (#233).
        "task": "app.tasks.board_sentinel",
        "schedule": crontab(minute=50, hour=7),  # Daily 07:50 UTC
        "options": {"queue": "heavy"},
    },
    "anchor-schedule-sentinel-daily": {
        # #2853: the anchor-schedule rail existed since #2697 but ran only when a
        # person asked, so the December-anchor-on-a-September-row defect (#2804)
        # was caught days after a fan could already see the wrong kickoff. This
        # is its nightly read-only driver: page the anchored near-future window,
        # ask ESPN what game each anchor NAMES, file one deduped issue on drift.
        # Never writes — the correction stays attended.
        #
        # 06:40 UTC, and the time is a decision, not a free slot. It is the only
        # sentinel that is network-bound per ROW (one `summary?event=` each,
        # budget-capped at 300s), so dropping it into the 07:05–07:50 block would
        # hold one of the two heavy slots for five minutes and starve exactly the
        # beats #233 moved here to protect. Running it 25 minutes ahead also puts
        # its issue on the board BEFORE the board sentinel reads the board at
        # 07:50. heavy queue (#233).
        "task": "app.tasks.anchor_schedule_sentinel",
        "schedule": crontab(minute=40, hour=6),  # Daily 06:40 UTC
        "options": {"queue": "heavy"},
    },
    "recategorize-other-daily": {
        "task": "app.tasks.recategorize_other",
        "schedule": crontab(minute=0, hour=8),  # Daily at 8:00 AM UTC
        "kwargs": {"limit": 2000},
    },
    "sentry-snapshot-15min": {
        # #237 Item 1: cache the top Sentry issues by 24h volume so the ops-snapshot
        # endpoint reads a warm Redis key instead of calling Sentry live. Light HTTP
        # task on the background queue; no-ops without SENTRY_AUTH_TOKEN.
        "task": "app.tasks.sentry_snapshot",
        "schedule": crontab(minute="*/15"),
    },
    "mark-resolved-futures": {
        "task": "app.tasks.mark_resolved_futures",
        "schedule": crontab(minute=15, hour="2,8,14,20"),  # Every 6 hours — keeps resolved futures from cluttering feed (was daily)
    },
    "backfill-winners": {
        "task": "app.tasks.backfill_winners",
        "schedule": crontab(minute=45, hour="3,9,15,21"),  # Every 6 hours, offset from mark-resolved
    },
    # #991: resolve-winners beat entry RETIRED 2026-07-06. The standalone task
    # stopped being dispatched after 3 soft-limit failures (round 82) and is
    # redundant — backfill_winners runs the same shared `_resolve_winners_only`
    # path and covers the clean_resolution work at scale (~559K is_winner marks
    # /2h, OPS-343). The task def is kept (dormant, unscheduled) for a cheap
    # re-add. RE-ADD PATH if 2h freshness ever proves insufficient (watch feed
    # R6 resolved-suppression): re-add as a BOUNDED forward-only pass — small
    # limit + statement_timeout inner-op bound (NOT limit-only, which is a
    # non-fix per #969) on the realtime queue.
    "backfill-historical-links": {
        "task": "app.tasks.backfill_historical_links",
        "schedule": crontab(minute=30, hour="2,5,8,11,14,17,20,23"),  # 8x/day
        "kwargs": {"batch_size": 500},
        "options": {"queue": "background"},
    },
    "backfill-polymarket-price-history": {
        "task": "app.tasks.backfill_polymarket_history",
        "schedule": crontab(minute=0, hour="4,10,16,22"),  # Every 6h, offset from backfill-winners
        "kwargs": {"limit": 500},
        "options": {"queue": "background"},
    },
    "backfill-kalshi-price-history": {
        "task": "app.tasks.backfill_kalshi_history",
        "schedule": crontab(minute=30, hour="4,10,16,22"),  # Every 6h, 30min after Polymarket
        "kwargs": {"limit": 500},
        "options": {"queue": "background"},
    },
    # #1586 (queue 355): the cliff drain. HOURLY, deliberately — unlike every
    # other backfill here, the work this one does not do today cannot be done
    # at all: ~7,800 Kalshi markets cross the 86-day retention horizon every
    # week and their price history is deleted upstream. 400/run x 24 = ~9,600
    # outcomes/day, comfortably ahead of the ~1,100/day expiry rate, so the
    # at-risk band is reached before it dies rather than after.
    "kalshi-cliff-drain": {
        "task": "app.tasks.kalshi_cliff_drain",
        "schedule": crontab(minute=20),  # hourly, off the :00/:15/:30/:45 crowd
        "kwargs": {"limit": 400},
        "options": {"queue": "background"},
    },
    # live/035: the nightly chart-completeness sweep. 08:40 UTC = 01:40 PDT —
    # after the morning sentinels (07:10/07:25/07:40/07:45) have had the queue
    # and before the day's slate starts creating new thin charts, so a run is
    # never competing with an attended fold. Nightly rather than hourly because
    # the population it drains is created by yesterday's finished events, not
    # continuously; the cliff-drain one line up is the hourly rail for the
    # genuinely expiring cohort.
    # live/036 (b): `limit` raised 60 -> 90 when the population was narrowed to
    # the reader window. It is sized against INFLOW, not against a backlog: the
    # narrowed set measured 1,152 events turning over across its own 14-day
    # window, so ~82 enter per day and 90 covers that with a little room. It is
    # NOT sized higher, because the 900s soft limit at ~10s/event is the real
    # bound (~90) and a nightly killed mid-event is worse than a nightly that
    # leaves eight charts for tomorrow. What this misses, the on-demand fill on
    # `/api/events/{id}/history` catches the moment someone opens the page.
    "backfill-thin-event-charts": {
        "task": "app.tasks.backfill_thin_event_charts",
        "schedule": crontab(minute=40, hour=8),
        "kwargs": {"limit": 90},
        "options": {"queue": "background"},
    },
    # --- live/059: the outright chart's venue history --------------------------
    #
    # SIZED AGAINST ITS POPULATION, WHICH IS SIZED AGAINST WHAT A READER SCRUBS.
    # Measured 2026-09-04: 1,113 tier-1 open Kalshi/Polymarket fields exist, and
    # 107 of them resolve inside the 30-day horizon `eligible_market_ids` warms.
    # 12 markets an hour is 288 fills a day over 107 markets — every race gets
    # re-fetched roughly every nine hours, and the gap between a fetch and now is
    # covered by the sampled captures the read path layers on top. It is NOT
    # sized to keep every market minute-fresh: the page somebody is actually
    # reading triggers its own on-demand refill the moment its series is older
    # than three hours, which is a far better use of the same requests.
    #
    # :13 is chosen, not defaulted. Odd, so the `*/2` fire misses it; not a
    # multiple of 5, 10, 15, 20 or 30, so every recurring background beat misses
    # it too; and minute 13 carries no fixed-minute crontab anywhere in the
    # assembled schedule (CERT-418's rule: a minute is only clear if the FULL
    # schedule says so, not if the daily beats do).
    "fill-futures-chart-series": {
        "task": "app.tasks.fill_futures_chart_series",
        "schedule": crontab(minute=13),
        "kwargs": {"limit": 12},
        "options": {"queue": "background"},
    },
    # --- #2077 (queue 419): the settlement-capture sweep, on a schedule -------
    #
    # The RUN has fired twice in production — 2026-08-25 and 2026-08-26, 3,000
    # rows each, `rate_limited` 0 both nights — and both times because a person
    # pasted a shell line. The population it drains does not wait for that:
    # C-KALSHI-RETENTION-1 measured market-level purge starting at 47 days with
    # NON-MONOTONIC age ordering, so there is no cliff to beat and no step
    # function to notice a miss by. A skipped week is simply rows gone.
    #
    # 10:31 UTC = 03:31 PDT / 02:31 PST. Chosen, not defaulted — and the choice
    # is ENFORCED by `TestG8TheFireMinuteIsClearOnItsOwnQueue`, not by this
    # comment. Read that gate, not this paragraph: the first attempt at this
    # entry sat at :10 under a comment claiming :10 was "the only clear minute
    # in that hour", and CERT-418 BLOCKed it. The claim was true of hour 10's
    # DAILY beats and false of the schedule that runs — `*/2`, `*/5` and two
    # `*/10` background beats all fire at :10. A minute is only clear if the
    # FULL assembled schedule says so.
    #   * :31 carries zero other background crontab fires. Every even minute is
    #     spoken for by `precompute-discover-candidate-base` (*/2), so the
    #     minute has to be odd; :05/:10/:15/... are taken by the */5 and */10
    #     warmers and watchdogs.
    #   * the sweep's own 780 s deadline ends it by :44, so its whole run window
    #     is clear of the :45 and :00 crowds. Of the 22 collision-free minutes
    #     in the hour, :31 has the lightest 13-minute window (12 fires, 7 of
    #     them the */2 warmer that no minute avoids).
    #   * three background beats are pure intervals (10 s, 20 s, 180 s) and fire
    #     during every minute of the day. No choice of minute avoids them; they
    #     are named and pinned in the G8 section rather than filtered away.
    #   * one fire a night, not an interval — the cohort re-cuts daily and a
    #     second fire inside the same day resumes the same date-derived sweep
    #     rather than re-probing, so an extra fire would be safe but pointless.
    #
    # `budget`/`concurrency` are stated literally and pinned EQUAL to the
    # runner's own DEFAULT_BUDGET / DEFAULT_CONCURRENCY by a test, so the two
    # cannot drift into two opinions. 3,000 is not comfort: `plan_sweep` caps
    # the terminal bucket at `budget * (1 - NON_TERMINAL_RESERVE)`, so the
    # budget has to be read through the reserve.
    "settlement-capture-sweep-nightly": {
        "task": "app.tasks.run_settlement_sweep",
        "schedule": crontab(minute=31, hour=10),
        "kwargs": {"budget": 3000, "concurrency": 4},
        "options": {"queue": "background"},
    },
    "backfill-polymarket-open-sparse": {
        "task": "app.tasks.backfill_polymarket_history",
        "schedule": crontab(minute=15, hour="3,9,15,21"),  # Every 6h, offset from resolved
        "kwargs": {"limit": 100, "mode": "open_sparse"},
        "options": {"queue": "background"},
    },
    "backfill-kalshi-open-sparse": {
        "task": "app.tasks.backfill_kalshi_history",
        "schedule": crontab(minute=45, hour="3,9,15,21"),  # Every 6h, 30min after Polymarket
        "kwargs": {"limit": 100, "mode": "open_sparse"},
        "options": {"queue": "background"},
    },
    "backfill-kalshi-settled-events": {
        "task": "app.tasks.backfill_kalshi_settled",
        "schedule": crontab(minute=0, hour="5,11,17,23"),  # Every 6h, offset from candlestick backfill
        "kwargs": {"limit": 5000},
        "options": {"queue": "background"},
    },
    "backfill-kalshi-trade-history": {
        "task": "app.tasks.backfill_kalshi_trades",
        "schedule": crontab(minute=15, hour="5,11,17,23"),  # Every 6h, 15min after settled
        "kwargs": {"limit": 500},
        "options": {"queue": "background"},
    },
    "backfill-settled-gap-creation": {
        # #138/#995: create the freeze-gap markets (2026-06-09→07-08). Runs 30min
        # after the settled-events pass so it creates missing markets that the
        # settled/candlestick/calibration passes then enrich next cycle.
        "task": "app.tasks.backfill_settled_gap_creation",
        "schedule": crontab(minute=30, hour="5,11,17,23"),
        "kwargs": {"limit": 1500},
        "options": {"queue": "background"},
    },
    "backfill-polymarket-matchups": {
        # #173/#1024: catch-up net for matchup_title. The ingest write-hook now
        # stamps fresh poly game sub-markets at birth, but the historical backlog
        # (rows ingested before the hook) still needs the one-shot logic, and any
        # row that slips through (e.g. a sibling that named the matchup was absent
        # in the ingested batch) converges here. Idempotent (writes only where
        # missing); runs 45min after the gap-creation pass so newly-created rows
        # get a title the same cycle. Previously on-demand only (no beat).
        "task": "app.tasks.backfill_polymarket_matchups",
        "schedule": crontab(minute=45, hour="5,11,17,23"),
        "kwargs": {"all_groups": True},
        "options": {"queue": "background"},
    },
    "recover-datagolf-participation": {
        # #994: re-enabled after diagnosis (#136). The "400s" that blocked the
        # first attempt were mostly 429 rate-limits — DataGolf caps at 45 req/min
        # and the old 0.5s pacing = 120/min. The recovery now paces BEFORE every
        # request (1.5s = 40/min) and stops-and-resumes on any residual 429, so it
        # drains autonomously (the ~189-market cohort in 1-2 beats) with no manual
        # trigger. Genuinely-invalid tours (e.g. 'alt') → residual/symmetric-
        # exclude. Offset from the other datagolf tasks to avoid sharing the cap.
        "task": "app.tasks.recover_datagolf_participation",
        "schedule": crontab(minute=30, hour="4,10,16,22"),
        "kwargs": {"limit": 200},
        "options": {"queue": "background"},
    },
    "regrade-polymarket-under-signflip": {
        # #145 Item 1: dedicated task — the #137 poly Under/No sign-flip regrade
        # was a backfill_winners phase that never ran (pipeline budget-guards out
        # before calibration_prices). One cheap idempotent UPDATE; drains the
        # ~36K-row class and forward-fixes any rows the poller re-introduces.
        "task": "app.tasks.regrade_polymarket_under_signflip",
        "schedule": crontab(minute=45, hour="5,11,17,23"),
        "options": {"queue": "background"},
    },
    "unresolve-datagolf-premature": {
        # #146 Item 2: starvation sibling of the poly flip — the #137 integrity
        # block never runs (budget guard stops before calibration_prices).
        "task": "app.tasks.unresolve_datagolf_premature",
        "schedule": crontab(minute=50, hour="5,11,17,23"),
        "options": {"queue": "background"},
    },
    "null-impossible-both-sides-openings": {
        # #146 Item 2: starvation sibling of the poly flip (same reason).
        "task": "app.tasks.null_impossible_both_sides_openings",
        "schedule": crontab(minute=55, hour="5,11,17,23"),
        "options": {"queue": "background"},
    },
    "correct-both-winner-guess-side": {
        # #997: starvation sibling of the #146 integrity beats — demote the
        # guess side of both-winner mutually-exclusive binaries. Offset a few
        # minutes after the both-sides null so they never contend for the worker.
        "task": "app.tasks.correct_both_winner_guess_side",
        "schedule": crontab(minute=58, hour="5,11,17,23"),
        "options": {"queue": "background"},
    },
    "compute-calibration-prices": {
        # #180 Item 1 — THE autopilot fix. `_compute_calibration_prices` was ONLY
        # a backfill_winners phase, but that pipeline budget-guards out at
        # `stopped_before: calibration_prices` on EVERY run (the 840s guard is spent
        # on resolution before it reaches the pricing step), so the pricing step
        # NEVER ran in production. Result: recent-cohort cal_prob coverage collapsed
        # (kalshi 24.2%→4.2%, poly 80.2%→9.2%, June→July 2026). Extracted to its own
        # dedicated task (same pattern as the #145/#146 integrity siblings above) so
        # it drains autonomously. Monotonic + resumable by construction: every part
        # selects `calibration_probability IS NULL` and commits per 100K batch, so a
        # soft-limit kill just resumes from the remaining NULL rows next run — it
        # NEVER restarts from scratch (gotcha #34). Runs in the empty 2/8/14/20 hour
        # windows (clear of backfill_winners :45@3,9,15,21 and the :40-:58@5,11,17,23
        # integrity beats) so it prices the freshly-resolved/nulled rows those beats
        # leave behind. 10-min soft-limit (600s) matches the task def.
        #
        # #183 Item 3 de-contention (r178: zero SCHEDULED fires observed): the
        # background worker is Standard-1X concurrency=2 (only two slots). The
        # original :15 minute collided EVERY slot with a pile-up of ~9 background
        # beats — critically `precompute-calibration-main` (minute=15 HOURLY, also a
        # 600s calibration grinder) AND `mark-resolved-futures` (:15 @ 2,8,14,20) —
        # so calibration_prices routinely arrived as the 3rd+ task at :15 and lost
        # the 2-slot race, never getting to run (gotcha #12/#39 discipline: a long
        # co-scheduled task can starve a beat on a shared worker). Moved to :10,
        # which fires only three fast */10 Redis cache-warmers (freshness-watchdog,
        # max-movement, admin-link-rate) in these hours — no 600s contender — so the
        # task now gets a free slot at dispatch. Still clear of backfill_winners and
        # the integrity beats; ordering vs the resolution beats is preserved.
        "task": "app.tasks.compute_calibration_prices",
        "schedule": crontab(minute=10, hour="2,8,14,20"),
        "options": {"queue": "heavy"},
    },
    "precompute-bookmaker-calibration": {
        # #1835 (CAL-P051): the starvation sibling the #180 fix left behind.
        # `_precompute_bookmaker_calibration` was ONLY a backfill_winners phase
        # and sat behind that pipeline's FIRST budget guard, so it never ran —
        # measured `stopped_before: "bookmaker_closing"`, successes_24h 0, runs
        # pinned at the 840s wall — the 24h Redis key expired, and the
        # `odds_api_bookmaker` source (the per-bookmaker moneyline, which
        # dominates Odds API volume) disappeared from the published payload
        # entirely. Same remedy as compute-calibration-prices above: its own
        # beat, so a heavy resolution cycle cannot starve it.
        #
        # Slot chosen the way #183 Item 3 says to choose one — by checking what
        # else fires there, not by picking a round number. The background worker
        # is Standard-1X concurrency=2, so a long co-scheduled task starves a
        # beat. At :55 the ONLY other background fire is `warm-event-concepts`
        # (*/5, a fast Redis warmer); :55 is not a multiple of 10, 15, 20 or 30,
        # so none of the other periodic warmers land on it, and hours 0/6/12/18
        # are clear of backfill_winners (:45 @ 3,9,15,21), the integrity beats
        # (:40-:58 @ 5,11,17,23) and compute-calibration-prices (:10 @ 2,8,14,20).
        #
        # Cadence matches the 6h refresh the 24h TTL was written for, and lands
        # 20 minutes before the hourly `precompute-calibration-main` (:15) that
        # consumes the key.
        "task": "app.tasks.precompute_bookmaker_calibration",
        "schedule": crontab(minute=55, hour="0,6,12,18"),
        "options": {"queue": "background"},
    },
    "sync-polymarket-resolved-status": {
        "task": "app.tasks.sync_polymarket_resolved",
        "schedule": crontab(minute=30, hour="5,11,17,23"),  # Every 6h, 30min after Kalshi settled
        "options": {"queue": "background"},
    },
    "backfill-polymarket-winners": {
        "task": "app.tasks.backfill_polymarket_winners",
        "schedule": crontab(minute=45, hour="5,11,17,23"),  # Every 6h, 15min after PM sync
        "kwargs": {"limit": 10000},
        "options": {"queue": "background"},
    },
    "clob-resolve-drain": {
        "task": "app.tasks.clob_resolve_drain",
        "schedule": crontab(minute=20, hour="1,7,13,19"),  # Every 6h, clear of :40-:58 cal windows
        # #989: Batch-0 PASSED (16/16 resolved_direct hand-verified, zero wrong
        # maps, self-validating exact-label tier; revertible via the distinct
        # resolution_source). Auto-write enabled for resolved_direct /
        # resolved_name_match only; ambiguous/void stay excluded.
        "kwargs": {"limit": 300, "dry_run": False},
        "options": {"queue": "background"},
    },
    "backfill-box-scores": {
        "task": "app.tasks.backfill_box_scores",
        "schedule": crontab(minute=15, hour="5,11,17,23"),  # Every 6h, offset from others
        "kwargs": {"limit": 500, "priority_calibration": True},
        "options": {"queue": "background"},
    },
    "backfill-espn-ids": {
        "task": "app.tasks.backfill_espn_ids",
        "schedule": crontab(minute=45, hour="5,11,17,23"),  # Every 6h, 30min after box scores
        "kwargs": {"limit": 1000},
        "options": {"queue": "background"},
    },
    "backfill-espn-win-prob": {
        "task": "app.tasks.backfill_espn_win_prob",
        "schedule": crontab(minute=0, hour="6,12,18,0"),  # Every 6h, offset from ESPN IDs
        "kwargs": {"limit": 200},
        "options": {"queue": "background"},
    },
    "backfill-espn-win-prob-oldest": {
        # #207 Item 2: oldest-first pass drains the OLD tail the newest-first run
        # can never reach (gotcha #41). Daily so both ends make progress.
        "task": "app.tasks.backfill_espn_win_prob",
        "schedule": crontab(minute=20, hour=3),  # Daily 03:20 UTC, off-peak
        "kwargs": {"limit": 200, "oldest_first": True},
        "options": {"queue": "background"},
    },
    "backfill-canonical-keys-daily": {
        "task": "app.tasks.backfill_canonical_keys",
        "schedule": crontab(minute=30, hour=8),  # Daily at 8:30 AM UTC
        "kwargs": {"limit": 2000},
    },
    "backfill-market-shapes": {
        # Queue #194 Item 1 / Queue #260 — recompute + persist the semantics v2
        # contract (display shape in market_type; relation/exhaustive/
        # expected_winners/fingerprint in market_metadata.shape).
        # Every 20 min: rolls over all rows in bounded/resumable cursor passes,
        # recomputing on NULL / version-old / fingerprint-change and writing
        # only on change (so a converged table costs reads only).
        "task": "app.tasks.backfill_market_shapes",
        "schedule": crontab(minute="*/20"),
        "kwargs": {"limit": 40000},
        # RULING 110 (LAT-P077): moved background -> heavy under the scoped
        # two-task exception. See the note on `precompute-backfill-progress`.
        "options": {"queue": "heavy"},
    },
    "audit-canonical-keys-daily": {
        "task": "app.tasks.audit_canonical_keys",
        "schedule": crontab(minute=0, hour=9),  # Daily at 9:00 AM UTC
        "kwargs": {"limit": 50},
    },
    "snapshot-golf-leaderboard-daily": {
        "task": "app.tasks.snapshot_golf_leaderboard",
        "schedule": crontab(minute=0, hour=10),  # Daily at 10:00 AM UTC (~6am ET) — before tournament rounds start
    },
    "audit-prediction-market-links-daily": {
        "task": "app.tasks.audit_prediction_market_links",
        "schedule": crontab(minute=15, hour=9),  # Daily at 9:15 AM UTC
        "kwargs": {"limit": 50},
    },
    "audit-related-futures-daily": {
        "task": "app.tasks.audit_related_futures",
        "schedule": crontab(minute=30, hour=9),  # Daily at 9:30 AM UTC
        "kwargs": {"limit": 30},
    },
    # Note: enrich-market-hooks and enrich-market-images schedules above
    # already handle both initial generation and regeneration.
    # Note: update_event_tags, enrich_taxonomy_llm, and DataGolf polls are
    # piggybacked on discover_events and poll_all_odds respectively.
    # With dual workers (realtime + background), these could be split out
    # into standalone tasks. Kept as piggybacked for now since the pattern
    # works and reduces scheduling complexity. DataGolf hourly poll is
    # Redis-gated to 1h on discover_events; live poll is gated to 5min on
    # poll_all_odds. Admin endpoints run tasks inline (not via .delay()).
    "daily-digest": {
        "task": "app.tasks.send_daily_digest",
        "schedule": crontab(hour=13, minute=0),  # 8am ET (UTC-5) / 6am PT
        "options": {"queue": "background"},
    },
    "export-engagement-nightly": {
        "task": "app.tasks.export_engagement",
        "schedule": crontab(hour=2, minute=0),  # 2:00 AM UTC
        "options": {"queue": "background"},
    },
    "snapshot-coverage-metrics-daily": {
        "task": "app.tasks.snapshot_coverage_metrics",
        "schedule": crontab(hour=3, minute=0),  # 3:00 AM UTC daily
        "options": {"queue": "heavy"},
    },
    "daily-challenge-push": {
        "task": "app.tasks.send_daily_challenge_push",
        "schedule": crontab(hour=14, minute=0),  # 2:00 PM UTC (10am ET / 7am PT)
        "options": {"queue": "background"},
    },
    "big-move-alerts": {
        "task": "app.tasks.send_big_move_alerts",
        "schedule": crontab(minute="*/30"),  # Every 30 minutes
        "options": {"queue": "background"},
    },
    "morning-digest-daily": {
        # Queue #200: notifications v1 — one daily push of the 3-5 most
        # interesting probabilities to opted-in device tokens. Reuses cached
        # Discover interestingness (one content brain). 14:05 UTC = 7:05 AM PT
        # (staggered 5 min after the daily-challenge push).
        "task": "app.tasks.send_morning_digest",
        "schedule": crontab(hour=14, minute=5),
        "options": {"queue": "background"},
    },
    "precompute-calibration-main": {
        "task": "app.tasks.precompute_calibration_main",
        "schedule": crontab(minute=15),  # Every 1 hour at :15
        "options": {"queue": "heavy"},
    },
    "calibration-beat-gauge-sampler": {
        # CAL-P084 (#2007): capture each beat's fixed gauge set before the
        # single-row phase ledger is overwritten by the next one.
        #
        # TWICE per beat, and both times are chosen against known hazards
        # rather than picked round:
        #   :45 — the beat starts :15 and finishes ~:33-:37, so this is the
        #         first safe read of the row it just wrote.
        #   :05 — the redundant one. The safe DEPLOY window is :35-:05
        #         (README "PRODUCER BEAT DISCIPLINE"), so a release can SIGTERM
        #         the :45 sample; the ledger row survives until ~:35 next hour,
        #         so :05 still catches that beat. One sample per beat would make
        #         the instrument's coverage a function of the deploy schedule.
        # Both sit OUTSIDE :15-:35, so this never contends with the producer —
        # the contention CAL-P074 measured costing a cell its whole first pass.
        # Duplicate reads dedupe on `generation`, so twice per beat still banks
        # one row per beat.
        "task": "app.tasks.calibration_beat_gauge_sampler",
        "schedule": crontab(minute="5,45"),
        "options": {"queue": "background"},
    },
    "compute-time-horizon-calibration": {
        "task": "app.tasks.compute_time_horizon_calibration",
        "schedule": crontab(minute=0, hour="1,7,13,19"),  # Every 6 hours
        "options": {"queue": "heavy"},
    },
    "compute-fair-fight-comparison": {
        "task": "app.tasks.compute_fair_fight_comparison",
        "schedule": crontab(minute=15, hour="1,7,13,19"),  # Every 6 hours, offset 15min
        "options": {"queue": "heavy"},
    },
    "precompute-source-intelligence": {
        "task": "app.tasks.precompute_source_intelligence",
        "schedule": crontab(minute=30, hour="1,7,13,19"),  # Every 6 hours, offset 30min
        "options": {"queue": "heavy"},
    },
    # ── CADENCE ↔ TTL HYGIENE, LAT-P062 (Item 3). All three below cache at
    # `ex=3600` and were recomputing FOUR to SIX times per cache lifetime.
    #
    # The premise-check that gates this ran in LAT-P061 and PASSED: the writer
    # is the scheduled task itself and it `setex`es unconditionally, so these
    # caches DO extend on every pass — the mirror image of `/typeahead`'s early
    # return, where a warm read extends nothing. That matters because it means
    # the extra recomputes buy exactly NOTHING: the cache would not have expired
    # either way, so every run past the second is pure waste rather than a
    # freshness/cost trade.
    #
    # `*/30` keeps TWO refreshes inside every 3600s TTL — one is a single point
    # of failure, so the cadence is not taken to `*/60`.
    #
    # ⚠️ Worth ~20 GB/day, which is **0.7%**. This is HYGIENE, NOT A FIX, and it
    # must not be reported as one. It is folded in here only because the beat
    # file was already open for the warmer change above, and because removing
    # background read pressure from the buffer pool is the one thing that helps
    # the trigram indexes #1866 is about — a rounding error with the right sign.
    "precompute-admin-audit-all": {
        "task": "app.tasks.precompute_admin_audit_all",
        # */15 -> */30 (LAT-P062). Was 4 recomputes per 3600s TTL; now 2.
        "schedule": crontab(minute="*/30"),
        "options": {"queue": "background"},
    },
    "precompute-admin-link-rate": {
        "task": "app.tasks.precompute_admin_link_rate",
        # */10 -> */30 (LAT-P062). Was 6 recomputes per 3600s TTL; now 2.
        # background -> heavy (#1609, LAT-P065): 71.8s p50 / 122.2s p95 on a
        # queue with ~one effective slot, for an ADMIN panel no user waits on.
        # It was directly observed holding a slot through a measured
        # `warm_typeahead` hole. It is in HEAVY_TASKS, so the loop below the
        # beat schedule would pin this to heavy regardless — stated literally
        # here so the source reads true rather than relying on the override.
        "schedule": crontab(minute="*/30"),
        "options": {"queue": "heavy"},
    },
    "precompute-admin-matured-linkage": {
        "task": "app.tasks.precompute_admin_matured_linkage",
        # */10 -> */30 (LAT-P062). Was 6 recomputes per 3600s TTL; now 2.
        # Matured-linkage headline (Item 2).
        "schedule": crontab(minute="*/30"),
        "options": {"queue": "background"},
    },
}

# Route the heavy grinder class onto the dedicated `heavy` worker. Beat entries
# pin `options["queue"]` explicitly, which OVERRIDES task_routes at dispatch
# time — so both must agree. This loop is the BACKSTOP: it flips every
# HEAVY_TASKS beat entry to the heavy queue regardless of what it was authored
# with. (See the queue-routing comment block above for the rationale.)
#
# ⚠️ IT IS A BACKSTOP AND NOT A LICENCE, and LAT-P067 fixed the debt that
# distinction had already accumulated. Because this loop always wins, NINE beat
# entries could sit in this file literally reading `"queue": "background"` (or
# carrying no `options` at all) while dispatching to `heavy` — and they did:
# the seven calibration/precompute warmers plus `poll-kalshi` and
# `match-prediction-markets`. Every one now states its real queue literally.
#
# WHY THAT MATTERED WHEN THE EFFECTIVE ROUTING WAS ALWAYS CORRECT: the source is
# what a human reads. Nine entries whose text said `background` were nine
# entries that read as evidence for "the calibration family is starving
# background" — an explanation that was FALSE, sitting in the file, in exactly
# the investigation #1609 spent windows on. A backstop that silently corrects
# the text it corrects is a backstop that makes the text lie.
#
# `test_heavy_beat_entries_pin_heavy_queue` cannot catch this: it runs after
# this loop and therefore reads the corrected value. Only a SOURCE-TEXT read
# can, which is what `test_heavy_beat_literals_match_their_effective_queue`
# does — the guard and the fix ship in one commit, deliberately, because a fix
# without the guard is a fix that decays back.
for _beat_entry in celery_app.conf.beat_schedule.values():
    if _beat_entry.get("task") in HEAVY_TASKS:
        _beat_entry.setdefault("options", {})["queue"] = "heavy"


# =============================================================================
# #1609 HYGIENE — bound the lifetime of a cache-warmer beat message.
#
# ⚠️ THIS IS HYGIENE, NOT THE CURE, AND IT IS LABELLED SO ON PURPOSE.
# The cure for #1609 is the topology change above (the three multi-minute
# residents moved off `background`). This block ships BEHIND it and carries a
# registered CONTROL that predicts NO user-visible improvement from it alone:
#
#   E1  background depth falls and holds < 100 within 2 h        (expected)
#   E2  `starts_24h` falls toward real passes; the burst pattern
#       (+11 starts in 6 s of 15 ms lock-skips) disappears        (expected)
#   E3  `warm_typeahead` HOLE FREQUENCY AND DURATION UNCHANGED    (expected)
#
# E3 is the honest control. If someone later reports "expires fixed #1609",
# E3 is the row that says it did not: this shortens the QUEUE, it does not
# return a SLOT. A remedy that makes the depth number look better while the
# starvation continues is worse than no remedy, because it retires the alarm.
#
# There was no `task_expires` anywhere in this config (LAT-P064 §1922-E):
# nothing discarded a stale beat message, so `warm_typeahead`'s 10 s beat
# published 8,640 messages/day against ~2,530 measured starts and the surplus
# ripped through later in bursts. #1609's own queue sample showed the same
# shape for `precompute_discover_candidate_base` (x6 enqueued) and
# `refresh_open_commentary` (x5) — which is acceptance criterion 2 on that
# issue, "no periodic task has more than one instance enqueued at a time".
#
# THE RULE IS ONE BEAT PERIOD, not a per-task magic number. For an idempotent
# cache warmer, a message still queued when its successor is published is by
# definition superseded — running it recomputes a value that is about to be
# recomputed. `expires` is therefore set to exactly one period, and a guard
# test asserts both that every name here exists and that the value never
# exceeds the beat's own period.
#
# Deliberately NOT expired: anything that writes durable rows. Dropping a
# superseded WARM is free; dropping a superseded WRITE loses data.
# =============================================================================
_EXPIRING_WARMER_BEATS = {
    # beat name -> expires seconds.
    #
    # ⚠️⚠️ **10 -> 120, LAT-P075.** The rule "expires == one beat period" is now
    # DERIVED per beat rather than applied flat — see `derive_message_expiry_s()`
    # in `app/utils/typeahead_beat_budget.py` for the full derivation.
    #
    # 🔴 **THIS IS NOT THE PERIOD REPAIR, AND AN EARLIER DRAFT OF THIS COMMENT
    # SAID IT WAS.** The correction is recorded rather than quietly edited out,
    # because the reasoning that produced it is the reasoning a reader will
    # repeat. `expires: 10` was named as the period regression's mechanism
    # (#2014) on a 4/4 both-directions correlation, and the arithmetic below does
    # show it discarding two thirds of the warmer's messages. But discarding a
    # message and lengthening the PERIOD are different claims, and continuing to
    # sample separated them: during the long stalls the broker pile drains on the
    # first free slot either way, so the next pass starts at the same instant
    # whether the older messages were discarded or executed as no-ops.
    #
    # What this change buys is stated honestly at the bottom of this comment. The
    # period's actual cause is `--concurrency=2` on `worker-background` against
    # 57 beats, one of which is this one; see `docs/audits/latency/`.
    #
    # The old value and its reasoning are kept here because the reasoning was
    # right about a different task. It ran: `expires` bounds the MESSAGE, the beat
    # publishes every 10 s, so anything above 10 leaves several messages alive at
    # once and re-admits lapping. **That holds when a task's wall is SHORTER than
    # its beat period. `warm_typeahead`'s is 4-6x LONGER** — 39.3-61.3 s against a
    # 10 s beat — and in that regime the fires landing during a pass are not
    # superseded messages at all. They are the only start opportunities there are,
    # every one of them held off by the run lock until the pass ends, and a 10 s
    # expiry kills all of them except those published in the pass's final 10 s.
    #
    # 🔴 MEASURED, not argued. The share of fires that can execute at all is
    # `(expires + max(0, period - wall)) / period`. At expires 10, wall p50 45.7 s,
    # period p50 53.5 s that predicts **32.7 %** — and the deployed pass-ring
    # instrument's own counters read **30.5 %** (26 ringed passes + 41 counted
    # skips = 67 executions against ~220 fires over 2,196 s, 2026-08-20T02:5xZ).
    # Two thirds of the warmer's firing opportunities were discarded unexecuted.
    #
    # 120 is `_LOCK_TTL_SECONDS`, deliberately a CONSTANT and not the sampled
    # worst wall: the lock cannot be held past its own TTL, so a message older
    # than that is provably not waiting on the lock and IS genuinely superseded —
    # the discard the bound was always meant to make. A sampled maximum would not
    # do, because this program has now read one as a bound and been wrong twice
    # (42.6 by 11.3 s, then 53.920 by 7.36 s).
    #
    # WHAT IT BUYS, claimed no wider than it was measured:
    #   1. The discard stops. Two thirds of fires became executions rather than
    #      silent drops, which is a correctness fix on its own terms — a bound is
    #      not entitled to throw away messages it was never aimed at.
    #   2. Saturation becomes READABLE. Today a wedged background pool and a quiet
    #      one produce the same evidence: no pass, no skip, nothing. With a message
    #      that outlives the pile, the backlog drains as a burst of counted
    #      `skips:lock` on the first free slot, so `skips` finally discriminates
    #      "the pool was blocked" from "nothing was published" (gotcha #53's shape:
    #      an absence that two different causes produce is not evidence).
    #   3. Up to one beat interval off each period, since a queued message can
    #      start a pass the instant the lock releases instead of waiting for the
    #      next fire. ~4 s against a p50 of 50.1 s. Small, and it is the only
    #      period effect claimed.
    #
    # COST, stated: every fire now executes, and the ones that cannot start a pass
    # take the lock-skip path at <= 71 ms measured. ~0.4 s of slot time per minute,
    # ~0.7 % of one slot. **Publishes do not change** — this bound is delivery-side
    # only — so #1609's background arrival share moves in neither direction.
    "warm-typeahead": 120,

    "precompute-discover-candidate-base": 120,   # */2 min — #1609 saw 6 enqueued

    # #2236. One period, so the flat #1609 rule applies unamended — this pass's
    # wall is far shorter than its period (a `HGETALL` when nothing is live, one
    # feed build per live shape inside a 20 s budget otherwise), so a fire that
    # could not start IS superseded. It is superseded HARDER than most: the whole
    # point of the task is to publish a payload no older than 60 s, and a message
    # that has been queued past its own period would republish a build the next
    # fire is about to redo. Expiring it is not hygiene here, it is the contract.
    "prewarm-live-feed-shapes": int(FEED_LIVE_REPUBLISH_PERIOD_S),
    "refresh-open-commentary": 180,          # 180 s — #1609 saw 5 enqueued; also the only
                                             # OpenAI caller, so dropping stale work saves spend
    "warm-event-concepts": 300,              # */5 min

    # LAT-P137. One period, so #1609's flat rule applies unamended: the pass is
    # one ~1.4 s build against a 300 s beat, so a fire that could not start IS
    # superseded by the next one — and superseded exactly, because the next fire
    # rebuilds the same census from the same predicate. The bound is DERIVED
    # from the period for the same reason the period is derived from the tier's
    # ceiling: three numbers that must agree, and only one of them typed.
    "warm-futures-categories": _futures_categories_warm_minutes() * 60,

    # LAT-P090/#2211. 20 s == the beat period, so the flat #1609 rule applies
    # unamended: this task's WALL (~4-8 s steady state, ~10 ms on a floor skip)
    # is shorter than its period, so a fire that could not start a pass IS a
    # superseded message and must not outlive its replacement. That is the
    # opposite of `warm-typeahead`, whose 39-61 s wall against a 10 s beat makes
    # its held-off fires the only start opportunities that exist — which is why
    # that one needs a derived bound and this one does not.
    "warm-search-head": 20,
}

for _warmer_beat, _expires_s in _EXPIRING_WARMER_BEATS.items():
    # No silent skip: a renamed beat must fail loudly here rather than quietly
    # lose its bound. The guard test asserts the same thing at collection time.
    celery_app.conf.beat_schedule[_warmer_beat].setdefault("options", {})[
        "expires"
    ] = _expires_s


# Queue 300R Item 1 — targeted result suppression. Must run AFTER the beat
# schedule exists (it is derived from it) and after every task decorator has
# run. Beat-only tasks with no HTTP dispatcher stop writing a celery-task-meta
# key; anything an admin route can hand a task_id for keeps its result. Health
# and observability are unaffected — those read the `bainluck:task_metrics:*`
# hash written by `_tracked_run`, not the result backend. See
# app/tasks/result_retention.py for the full argument and the drift guard.
_SUPPRESSED_RESULT_TASKS = _apply_result_suppression(celery_app)


# =============================================================================
# Backward-compatible re-exports
#
# These allow existing code that does `from app.tasks import _infer_base_sport`
# or `from app.tasks import celery_app` to keep working.
# =============================================================================

from app.tasks.futures import _infer_base_sport  # noqa: E402, F401 (used by routes/futures.py)
from app.tasks.snapshots import _create_or_update_win_prob_snapshot  # noqa: E402, F401
from app.tasks.cohort_market_type import build_cohort_market_type  # noqa: E402, F401
