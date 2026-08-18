"""ONE Sentry ``before_send`` policy, shared by every process that inits the SDK (#1501).

## Why this exists

The org runs the free Developer plan: **5,000 error events per billing month**,
billing period the 21st → the 20th, on-demand disabled. Measured through the org
stats + Discover APIs for the 2026-07-21 → 2026-07-29 cycle:

| event type    | accepted in 8 days |
|---------------|--------------------|
| ``error``     | 3,585              |
| ``default``   | 2,999              |
| **billable**  | **6,584**          |
| ``transaction`` (own quota, healthy) | 7,659 |

6,584 in eight days against a 5,000/month allowance is the whole month spent on
day 8 — and every event after that is refused. The cost is not "we lose some
noise": it is that **a green Sentry read means nothing**. #1445 and #1199 both
failed silently behind a "0 events in 24h" bucket that only ever meant the quota
was gone. This is the inverse of gotcha #49 — there the lifetime count
overstates; here the recent bucket understates to zero.

## The two structural bugs in the filter that already existed

A ``before_send`` written to kill exactly this noise lived inline in
``app/main.py``. It did almost nothing, for two independent reasons:

1. **It only ever ran in the web dyno.** Celery workers boot from
   ``app.tasks.celery_app`` and never import ``app.main``; ``app/tasks/__init__``
   called ``sentry_sdk.init()`` with **no** ``before_send`` at all. Every top
   burner is worker-side, so the filter was installed in the one process that
   does not produce the flood.
2. **Its name list did not match reality.** It said ``"WorkerLost"``; billiard's
   class is ``WorkerLostError`` (246 events). ``SoftTimeLimitExceeded`` (~640
   events) was absent entirely. And its Redis test asked for ``"redis" in
   str(exc)``, but redis-py's message names the EC2 endpoint and never the word
   "redis" — so the single largest signature (1,878 events, 29% of the cycle,
   culprit ``redis.connection in connect_check_health``) passed straight through
   even in the web dyno.

## Three tiers, and why not uniform sampling

* **DROP** — stateless, provenance-bound infrastructure churn that recovers on
  its own and has a non-Sentry alarm. Nothing here carries a unique diagnostic.
* **THROTTLE** — real but chronic classes (Celery task death, event-loop
  teardown). One event per signature per window keeps ``lastSeen`` honest and
  the issue alive in the UI instead of hiding the class outright. Task death is
  independently metered in Redis task-metrics (``failures_24h``) and, since
  #1501 item 2, by the signal-driven lifecycle pair
  (``attempts - terminals``) that observes every task from ABOVE
  ``_tracked_run`` — so a throttle here is not a blind spot.
* **PASS** — everything else at full fidelity, subject only to the backstop.

The **backstop** is the part that does not depend on the census being right.
Every signature — including one nobody has identified — is capped per window. A
novel signature always sends its first event immediately; only a *repeating* one
is capped. Blanket ``sample_rate`` does the opposite: it drops a fraction of
everything and loses exactly the single-occurrence novel error you most want.

## Two things this module is deliberately honest about

**Drops are bound to PROVENANCE, never to a hostname substring.** An earlier
draft matched Redis noise with ``"compute-1.amazonaws.com" in message`` — which
also matches a genuine upstream outage of any AWS-hosted third-party API (see
``_is_broker_endpoint_error`` and its hostile-specimen test). Redis churn is
identified by the *defining module* of the exception, or by a parsed host that
**equals** a host in our own configured broker/cache URLs. Log-record drops
additionally require the record to come from a known infrastructure logger.

**Throttle state is per-process, so its fleet ceiling is a multiple of the cap.**
State is in-process and lock-guarded rather than Redis-backed on purpose: this
code runs on the exception path and the single biggest error class IS Redis
being unreachable; a filter that needs Redis to decide whether to report a Redis
failure fails exactly when it matters (gotcha #39). The price is that N process
incarnations each get their own allowance. That multiplier is **measured, not
assumed** — see ``tests/test_sentry_filter.py::TestFleetVolumeCeiling`` and
``FORMATION`` in ``tests/fixtures/sentry_formation.py``, which derive it from
``backend/Procfile`` and from the observed per-day distinct ``server_name``
count. Do not quote a per-day number from this docstring; run the replay.
"""

from __future__ import annotations

import logging
import os
import re
import threading
import time
from typing import Any, Callable, Iterable
from urllib.parse import urlsplit

from app.utils import sentry_budget

logger = logging.getLogger(__name__)


# =============================================================================
# Tier 1 — DROP. Stateless, provenance-bound.
# =============================================================================

#: Exception class names dropped outright.
#:
#: Two families, and the line between "drop" and "throttle" is drawn on ONE
#: question: does the Sentry event carry a diagnostic that the compensating rail
#: cannot? Verified in ``app/tasks/redis_state.py`` +
#: ``app/tasks/__init__.py``, not assumed:
#:
#: * ``record_task_attempt`` / ``record_task_terminal`` fire from celery's OWN
#:   ``task_prerun`` / ``task_postrun`` signals, so ``attempts - terminals`` is
#:   the SIGKILL / hard-``time_limit`` population for **every task**, with no
#:   cooperation from any task body (see ``TASK_LIFECYCLE_PREFIX``);
#: * ``record_task_failure(..., verdict_reason=type(exc).__name__)`` records any
#:   thrown exception by class, with ``last_failure_at``.
#:
#: ``WorkerLostError`` / ``TimeLimitExceeded`` / ``Terminated`` are raised in the
#: pool PARENT (culprits ``billiard.pool in mark_as_worker_lost`` /
#: ``on_hard_timeout``), so their stack is billiard's own teardown and says
#: nothing about where the child actually was. They are a strict duplicate of
#: the lifecycle gap and are dropped.
#:
#: **This drop was WRONG for two cycles and the repair is the point** (codex
#: C-CERT-SENTRY-R2 finding 2). The rail named here used to be
#: ``hard_kills_24h = starts - terminals``, whose ``starts`` are written by
#: ``record_task_started`` — which lives INSIDE ``_tracked_run``, a helper the
#: task body elects to call. A child lost before reaching it contributed no
#: start and so could not appear in the difference, and **30 scheduled tasks
#: never call the helper at all**. For those, a hard kill and a healthy no-op
#: delivery were the same observation in the counter, while the parent-side
#: event that would have shown it was dropped here on the strength of that very
#: counter. The diagnostic was absent from Sentry AND from the metric.
#:
#: The general form, worth more than the instance: **a compensating instrument
#: that starts below the failure boundary is not a compensating instrument.**
#: Same shape as gotcha #53 — an absence and a fact sharing one reading. Before
#: adding anything to this set, check that its named rail observes the failure
#: from ABOVE the boundary where the failure occurs.
#:
#: ``SoftTimeLimitExceeded`` is deliberately NOT here: it is raised *into the
#: task*, so its stack names the exact operation that overran, which no counter
#: records. It is throttled instead — see :data:`THROTTLE_EXC_NAMES`.
DROP_EXC_NAMES = frozenset({
    # SQLAlchemy session-state cascades: always a SECOND error caused by a first
    # one that reports on its own. Keeping them doubles the volume of every DB
    # incident without adding information.
    "PendingRollbackError",
    "InvalidRequestError",
    # billiard/celery parent-side task death, fully covered by hard_kills_24h.
    "WorkerLostError",   # billiard's real class name; the old inline filter said
    "WorkerLost",        # "WorkerLost", which never matched anything.
    "Terminated",
    "TimeLimitExceeded",
})

#: Defining modules whose connection/transport errors are self-healing churn.
#: Matching the module rather than the message is the fix for the "redis" bug:
#: redis-py raises a family here (ConnectionError, TimeoutError, BusyLoadingError
#: and subclasses of each) and a name-only list silently misses every subclass it
#: did not enumerate. Deliberately NOT every redis exception — a ``ResponseError``
#: can be a real bug in our own command usage, so it must survive.
DROP_CONNECTION_MODULES = ("redis", "kombu", "amqp")

#: Connection-family names, only dropped with broker provenance attached.
CONNECTION_EXC_NAMES = frozenset({
    "ConnectionError",
    "TimeoutError",
    "ConnectionResetError",
    "BusyLoadingError",
    "SSLEOFError",
})

#: Loggers owned by the task/broker infrastructure. A message-shaped drop rule
#: requires the record to come from one of these, so no rule can ever fire on an
#: application log line that happens to contain a matching phrase.
INFRA_LOGGERS = frozenset({
    "multiprocessing",
    "billiard",
    "billiard.pool",
    "celery.backends.redis",
    "celery.backends.asynchronous",
    "celery.worker.consumer.consumer",
    "celery.worker.consumer",
    "celery.redirected",
    # emits the "Hard/Soft time limit (Ns) exceeded for <task>" records
    "celery.worker.request",
})


# redis-py renders connection failures as
#   "Error 8 connecting to ec2-1-2-3-4.compute-1.amazonaws.com:6379. <detail>"
# and celery's consumer as
#   "consumer: Cannot connect to rediss://:**@host:10819//: ..."
_CONNECTING_TO_RE = re.compile(r"connecting to ([A-Za-z0-9_.\-]+):(\d+)", re.IGNORECASE)
_BROKER_URL_RE = re.compile(r"\b(?:redis|rediss|amqp|amqps)://[^\s/]*?([A-Za-z0-9_.\-]+):\d+", re.IGNORECASE)

#: Env vars that define endpoints whose transport churn we own and already alarm
#: on elsewhere. A host is broker provenance only if it EQUALS one of these.
BROKER_URL_ENV_VARS = (
    "CELERY_BROKER_URL",
    "BROKER_URL",
    "CELERY_RESULT_BACKEND",
    "REDIS_URL",
    "REDIS_TLS_URL",
    "HEROKU_REDIS_URL",
)

#: Hosts that are a broker by name in local/CI topologies.
_LOCAL_BROKER_HOSTS = frozenset({"redis", "localhost", "127.0.0.1", "::1"})

_broker_hosts_cache: frozenset[str] | None = None
_broker_hosts_lock = threading.Lock()


def configured_broker_hosts(*, refresh: bool = False) -> frozenset[str]:
    """Hosts parsed out of OUR OWN broker/cache URLs.

    This is the provenance anchor for the endpoint fallback. It is deliberately
    an exact-host set and never a domain suffix: ``.amazonaws.com`` — or worse,
    the substring ``compute-1.amazonaws.com`` — also describes every AWS-hosted
    third-party API we depend on, and a real outage of one of those is precisely
    the signal we are trying to preserve.
    """
    global _broker_hosts_cache
    if _broker_hosts_cache is not None and not refresh:
        return _broker_hosts_cache
    hosts = set(_LOCAL_BROKER_HOSTS)
    for var in BROKER_URL_ENV_VARS:
        raw = os.getenv(var)
        if not raw:
            continue
        try:
            host = urlsplit(raw).hostname
        except Exception:
            host = None
        if host:
            hosts.add(host.lower().rstrip("."))
    with _broker_hosts_lock:
        _broker_hosts_cache = frozenset(hosts)
    return _broker_hosts_cache


def _is_broker_endpoint_error(text: str) -> bool:
    """True when ``text`` reports a failed connection to a host WE configured.

    The host is parsed out of the message and compared for equality against
    :func:`configured_broker_hosts`. A substring or suffix test here is the
    "incomplete URL substring sanitization" shape, and in this codebase it has a
    concrete cost: ``api-v2.ec2-44-201-2-3.compute-1.amazonaws.com`` refusing a
    connection is a third-party API outage, not Redis churn, and swallowing it
    would make an upstream failure invisible.
    """
    if not text:
        return False
    hosts = configured_broker_hosts()
    for match in _CONNECTING_TO_RE.finditer(text):
        if match.group(1).lower().rstrip(".") in hosts:
            return True
    for match in _BROKER_URL_RE.finditer(text):
        if match.group(1).lower().rstrip(".") in hosts:
            return True
    return False


def _all_tokens(text: str, tokens: Iterable[str]) -> bool:
    return all(t in text for t in tokens)


#: Message-shaped DROP rules: ``(logger, required-token-groups)``.
#:
#: Each rule needs an infra logger AND every token in one group. Tokens are
#: matched against the concatenation of the log record's ``formatted`` text, its
#: unrendered template and its params, because the LoggingIntegration sends
#: ``"Process %r pid:%r exited with %r"`` plus params rather than the rendered
#: line — so a single rendered-form regex would silently never match.
_DROP_MESSAGE_RULES: tuple[tuple[str, ...], ...] = (
    # billiard worker recycle: SIGKILL (max-memory-per-child / OOM) and SIGTERM
    # (dyno cycle). Celery restarts the child; task death is metered separately.
    ("exited with", "signal 9"),
    ("exited with", "sigkill"),
    ("exited with", "signal 15"),
    ("exited with", "sigterm"),
    # celery's Redis reconnect ladder — up to 20 events for ONE blip.
    ("connection to redis lost", "retry ("),
    ("retry limit exceeded", "reconnect"),
    ("cannot connect to", "redis"),
    # "Hard time limit (300s) exceeded for app.tasks.x[uuid]" — the log twin of
    # the TimeLimitExceeded exception above. It names the task and carries no
    # stack, so it adds nothing to hard_kills_24h. The SOFT twin is dropped for
    # the same reason; the soft *exception*, which does carry a stack, is
    # throttled rather than dropped.
    ("hard time limit", "exceeded for"),
    ("soft time limit", "exceeded for"),
)


# =============================================================================
# Tier 2 — THROTTLE. Chronic but real: keep the first, drop the repeats.
# =============================================================================

THROTTLE_EXC_NAMES = frozenset({
    # Raised INTO the task, so the stack names the operation that overran —
    # the one thing task-metrics cannot tell you. Chronic, so capped at one per
    # signature per window rather than dropped.
    "SoftTimeLimitExceeded",
    # Beat failing to enqueue, usually a Redis blip. Rare enough to keep, too
    # bursty to keep unbounded.
    "SchedulingError",
    "RuntimeError",      # narrowed by the event-loop markers below
})

#: A RuntimeError is only throttled when it is the known async-teardown message;
#: every other RuntimeError is a real bug and passes at full fidelity.
_EVENT_LOOP_MARKERS = ("event loop is closed", "attached to a different loop")


# =============================================================================
# Caps. Per signature, per PROCESS, per window.
# =============================================================================

THROTTLE_PER_WINDOW = 1
THROTTLE_WINDOW_S = 86400
#: Lowered 3 -> 1 by codex C-CERT-SENTRY-R2 finding 1, and the reason it had to
#: move is worth keeping: at 3 the measured replay sat at 157.0/day against a
#: 164.47/day budget, and **both** of the negative controls the certification
#: demanded pushed it over — one novel high-frequency worker signature costs
#: ``cap x 4 prefork children`` (+12/day at 3), and the watchdog cooldown's
#: tested Redis-down path (it fails OPEN by design, so an infra failure never
#: swallows an alarm) reaches the background children's backstops.
#:
#: At 1, three things happen at once, all measured in
#: ``TestFleetVolumeCeiling``: the replay drops to 123.6/day non-watchdog, one
#: novel worker signature costs 4/day instead of 12, and the watchdog's
#: fail-open path stops costing anything at all — because ``1 x 2 background
#: children`` is BELOW the 4-per-day the working cooldown already allows, so the
#: backstop binds first and the failure mode is bounded by the same number as
#: the healthy one.
#:
#: What is NOT lost: a novel signature still always sends its **first** event
#: (that is the ``count < limit`` path, not the cap), and with ~70 process
#: incarnations a day a genuinely high-frequency class is still plainly visible
#: fleet-wide. What IS lost is repeat-within-one-process detail, which is the
#: cheapest information in the system to give up.
#:
#: **#1894 / C-CERT-SENTRY-R3 finding 1: this is no longer a typed number.** It is
#: SOLVED from the quota by ``app/utils/sentry_budget.py`` — the largest cap whose
#: complete priced cost (census replay + novel-signature reserve + the watchdog
#: fail-open ceiling that the old model asserted beside itself instead of inside
#: itself) fits ``quota / days-in-this-cycle`` with the 12% floor taken off.
#:
#: You cannot set this above affordance because you do not set it. When nothing
#: is affordable the solve returns 0 and this floors at ``MINIMUM_VIABLE_CAP``
#: — deliberately, because muting the fleet to fit a bill re-breaks codex finding
#: (b) and inverts the purpose of the instrument. That state is reported, not
#: absorbed: see ``BUDGET_VERDICT`` below and the CRITICAL log beside it.
#: ⚠️ Import-time READING, kept only for readers that want "what did this
#: process boot with". It is NOT what the filter enforces — see
#: :func:`sentry_budget.current_backstop_per_window`. Freezing the enforced cap
#: here is C-CERT-SENTRY-R4 finding P1: a dyno outlives a billing cycle, so a
#: process that booted in a 28-day cycle went on enforcing its cap, and
#: exporting its verdict, after a 31-day cycle opened.
BACKSTOP_PER_WINDOW_AT_IMPORT = sentry_budget.effective_backstop_per_window()
BACKSTOP_PER_WINDOW = BACKSTOP_PER_WINDOW_AT_IMPORT
BACKSTOP_WINDOW_S = 86400
_MAX_TRACKED_SIGNATURES = 512

#: The full arithmetic as a readable dict, computed once at import. Carried into
#: the exported counters so an operator reading the discard rate also sees the
#: budget it is being spent against — a rate without its budget is the same
#: uninterpretable number the old log line was.
BUDGET_VERDICT_AT_IMPORT = sentry_budget.budget_verdict()
BUDGET_VERDICT = BUDGET_VERDICT_AT_IMPORT

if sentry_budget.BUDGET_OVERCOMMITTED:
    # The "loudly" half of "impossible or loudly impossible". Not an exception:
    # refusing to boot the API because Sentry's plan is one tier too small would
    # be a monitoring system taking production down to protect its own bill.
    logger.critical(
        "sentry_budget OVERCOMMITTED: policy prices %.2f/day against %.2f/day "
        "affordable (quota %d over a %d-day cycle); shortfall %.2f/day; a "
        "monthly quota of >=%d closes it at cap %d",
        BUDGET_VERDICT["priced_per_day"],
        BUDGET_VERDICT["affordable_per_day"],
        BUDGET_VERDICT["quota_per_month"],
        BUDGET_VERDICT["cycle_days"],
        BUDGET_VERDICT["shortfall_per_day"],
        BUDGET_VERDICT["required_monthly_quota"],
        BUDGET_VERDICT["backstop_per_window"],
    )


class _SignatureThrottle:
    """Per-signature token counter with a bounded, self-evicting table.

    In-process and lock-guarded rather than Redis-backed on purpose (gotcha #39):
    this runs on the exception path, and the biggest error class IS Redis being
    unreachable.

    Per-process state means every process incarnation gets its own allowance.
    That is a real multiplier on the fleet/day total, it is measured rather than
    assumed, and the measurement lives in the test suite — not in a comment here,
    because a number in a comment is what let the previous draft ship an
    unverifiable "42/day".
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._buckets: dict[str, tuple[float, int]] = {}

    def allow(self, signature: str, *, limit: int, window_s: int, now: float | None = None) -> bool:
        now = time.monotonic() if now is None else now
        with self._lock:
            existing = self._buckets.get(signature)
            # Membership, NOT truthiness: a window that opened at monotonic 0.0
            # is a real window, and `not started` would reset it on every call —
            # silently disabling the throttle for that signature forever.
            if existing is None:
                self._buckets[signature] = (now, 1)
                self._evict_if_needed()
                return True
            started, count = existing
            if (now - started) >= window_s:
                self._buckets[signature] = (now, 1)
                self._evict_if_needed()
                return True
            self._buckets[signature] = (started, count + 1)
            return count < limit

    def _evict_if_needed(self) -> None:
        """Drop the oldest windows once the table is full. Caller holds the lock."""
        overflow = len(self._buckets) - _MAX_TRACKED_SIGNATURES
        if overflow <= 0:
            return
        victims = sorted(self._buckets.items(), key=lambda kv: kv[1][0])
        for key, _ in victims[:overflow]:
            self._buckets.pop(key, None)

    def snapshot(self) -> dict[str, int]:
        with self._lock:
            return {k: v[1] for k, v in self._buckets.items()}


# =============================================================================
# Event introspection
# =============================================================================

def _exc_identity(event: dict[str, Any], hint: dict[str, Any] | None) -> tuple[str, str, str]:
    """``(class name, defining module, message)`` for the OUTERMOST exception.

    ``exception.values`` is ordered oldest-first, so ``values[-1]`` is what was
    actually raised — which for the Redis churn is the ``redis.exceptions``
    wrapper around an inner ``ssl.SSLEOFError``. Reading ``values[0]`` would see
    ``ssl`` and lose the provenance the whole drop rule rests on.
    """
    hint = hint or {}
    exc_info = hint.get("exc_info")
    if exc_info and exc_info[0] is not None:
        exc_type = exc_info[0]
        name = getattr(exc_type, "__name__", "") or ""
        module = getattr(exc_type, "__module__", "") or ""
        try:
            return name, module, str(exc_info[1] or "")
        except Exception:
            return name, module, ""
    values = ((event or {}).get("exception") or {}).get("values") or []
    if values:
        last = values[-1] or {}
        return (
            str(last.get("type") or ""),
            str(last.get("module") or ""),
            str(last.get("value") or ""),
        )
    return "", "", ""


def _message_text(event: dict[str, Any]) -> str:
    """Lower-cased haystack for the message rules.

    Concatenates the rendered line, the unrendered template AND the params: the
    LoggingIntegration ships ``logentry.message`` as the ``%``-template with
    ``logentry.params`` alongside, so ``"exited with 'signal 9 (SIGKILL)'"``
    never appears as one contiguous string. Token-group matching over the
    concatenation is what makes both shapes match.
    """
    event = event or {}
    entry = event.get("logentry") or {}
    parts: list[str] = []
    for key in ("formatted", "message"):
        val = entry.get(key)
        if isinstance(val, str):
            parts.append(val)
    params = entry.get("params")
    if isinstance(params, (list, tuple)):
        parts.extend(str(p) for p in params)
    elif params:
        parts.append(str(params))
    top = event.get("message")
    if isinstance(top, str):
        parts.append(top)
    elif isinstance(top, dict):
        for key in ("formatted", "message"):
            val = top.get(key)
            if isinstance(val, str):
                parts.append(val)
    return " ".join(parts).lower()


def _failure_site(event: dict[str, Any], hint: dict[str, Any] | None) -> str:
    """A stable identity for WHERE the error was raised.

    Codex C-CERT-SENTRY (b): a signature of only class + transaction collapses
    every distinct failure site inside one Celery task into a single bucket, so
    the third and fourth novel bugs in ``app.tasks.poll_odds`` are suppressed by
    the first two and the failure-site diagnostic is unrecoverable — task metrics
    count failures, they do not name lines.

    Resolution order, most authoritative first:

    1. an explicit ``event["fingerprint"]`` (Sentry's own grouping, set by e.g.
       the watchdog's ``scope.fingerprint``);
    2. the deepest ``in_app`` stack frame, as ``module:function`` — deliberately
       WITHOUT ``lineno``, because a line number changes on every unrelated edit
       above it and would re-open the whole budget on each deploy;
    3. the live traceback from ``hint["exc_info"]`` when the event carries no
       frames yet;
    4. ``culprit``, which Sentry computes with the same intent.
    """
    event = event or {}

    fingerprint = event.get("fingerprint")
    if isinstance(fingerprint, (list, tuple)):
        parts = [str(p) for p in fingerprint if p and str(p) != "{{ default }}"]
        if parts:
            return "fp:" + "|".join(parts)

    values = (event.get("exception") or {}).get("values") or []
    for value in reversed(values):
        frames = ((value or {}).get("stacktrace") or {}).get("frames") or []
        in_app = [f for f in frames if isinstance(f, dict) and f.get("in_app")]
        candidates = in_app or [f for f in frames if isinstance(f, dict)]
        if candidates:
            frame = candidates[-1]
            where = frame.get("module") or frame.get("filename") or frame.get("abs_path") or "?"
            return f"{where}:{frame.get('function') or '?'}"

    exc_info = (hint or {}).get("exc_info")
    tb = exc_info[2] if exc_info and len(exc_info) > 2 else None
    if tb is not None:
        deepest = tb
        while getattr(deepest, "tb_next", None) is not None:
            deepest = deepest.tb_next
        frame = getattr(deepest, "tb_frame", None)
        code = getattr(frame, "f_code", None)
        if code is not None:
            module = (getattr(frame, "f_globals", {}) or {}).get("__name__") or "?"
            return f"{module}:{code.co_name}"

    culprit = event.get("culprit")
    if culprit:
        return str(culprit)
    return "?"


#: Exceptions INJECTED into a task from outside it, rather than raised BY the
#: code at the frame they land on.
#:
#: For these the deepest frame is a **sampling artifact**: celery's soft-timeout
#: signal handler fires wherever the interpreter happens to be at the instant the
#: timer expires, so one chronically overrunning task fragments into a different
#: "failure site" per run. Measured in the 2026-07-21 census, schema 2:
#: ``SoftTimeLimitExceeded`` in ``refresh_open_commentary`` produced **11
#: distinct sites** — ``selectors:select`` (396 events),
#: ``app.routes.golf:_build_completed_tournament`` (68),
#: ``asyncpg.pgproto:numeric_decode_binary_`` (8), even ``?:<module>``. That is
#: ONE condition holding ELEVEN throttle allowances, and none of the eleven
#: names the bug.
#:
#: This is not a retreat from codex finding (b), it is its boundary. A site is
#: identity when the code at that site raised; it is noise when the exception
#: arrived from a signal handler, a pool parent, or a revoke. Distinguishing the
#: two is what lets the signature be fine-grained where fineness is information
#: and coarse where it is sampling noise.
#:
#: An explicit ``fingerprint`` still wins — that is deliberate grouping by the
#: code that raised, and the watchdog relies on it.
SITE_AGNOSTIC_EXC_NAMES = frozenset({
    "SoftTimeLimitExceeded",
    "TimeLimitExceeded",
    "Terminated",
    "WorkerLostError",
    "WorkerLost",
})


#: Event ``type`` values that are NOT errors and must never be judged by an
#: error-volume policy (#1894).
#:
#: ``sentry_sdk/client.py:872-875`` excludes only ``type == "transaction"`` from
#: ``before_send``. Everything else arrives here, including Celery Beat cron
#: check-ins — which ``CeleryIntegration(monitor_beat_tasks=True)``
#: (``app/tasks/__init__.py:617``) emits once per due-task dispatch via
#: ``sentry_sdk/integrations/celery/beat.py:152``.
#:
#: Two independent reasons either of which is sufficient:
#:
#: 1. A check-in is monitoring, not an error. Throttling it does not save error
#:    quota; it silently disables Sentry Crons for every beat task.
#: 2. ``client.py:883`` records a ``before_send`` drop as
#:    ``data_category="error"`` — **hardcoded, whatever the event actually was**.
#:    So dropping a check-in does not merely fail to help the error budget, it
#:    CORRUPTS the metric the budget is enforced against. Measured 2026-08-14..16:
#:    18,761 / 19,202 / 19,066 "errors" per day that were not errors.
NON_ERROR_EVENT_TYPES = frozenset({"check_in", "log", "metric", "feedback", "profile"})

#: Low-cardinality identity field per event type, for events that carry no
#: exception and no frames. ``check_in_id`` is deliberately NOT used: it is a
#: fresh uuid per event, so keying on it would give every check-in its own
#: signature and defeat throttling in the opposite direction.
_TYPE_DISCRIMINATORS = {"check_in": "monitor_slug", "transaction": "transaction"}

#: What the signature is when the event supplied nothing to identify it with.
#: A distinct, NAMED value rather than a coincidence of empty strings, because
#: the whole #1894 defect was an absence wearing the costume of an identity.
UNIDENTIFIED_SIGNATURE = "unidentified|?|?"

_VARIABLE_TOKEN_RE = re.compile(r"\b(?:0x)?[0-9a-f]{6,}\b|\d+", re.IGNORECASE)


def _message_shape(text: str) -> str:
    """A message with its variable parts collapsed, so repeats group.

    Messages carry hostnames, pids, row ids and hour-values, which is exactly how
    one condition ends up spending a whole month's quota as a thousand distinct
    issues (the reason :func:`event_signature` prefers the failure site). When
    the message is the ONLY identity an event has, it still must not be used raw.
    """
    return _VARIABLE_TOKEN_RE.sub("#", text)[:120].strip()


def _structural_identity(event: dict[str, Any]) -> str:
    """Identity for an event with no exception, no frames, no culprit, no transaction.

    **This is the general form of the #1894 defect.** The old signature was
    ``f"{exc_name or 'unknown'}|{where}|{site}"`` with every part independently
    able to be unknown, so any event shape that supplies none of them collapsed
    to one string — and ``BACKSTOP_PER_WINDOW`` then destroyed all but the first
    per process per day. Cron check-ins were the instance that got measured; the
    defect is that the collapse is silent and shape-agnostic, so the next event
    class to arrive without a stack inherits the same fate.

    The fix is a fallback that keeps descending instead of giving up: the event's
    declared ``type``, then a bounded per-type discriminator, then the shape of
    its message, and only then an explicitly NAMED unidentified bucket that the
    counters report rather than silently absorb.
    """
    event = event or {}
    etype = str(event.get("type") or "event")

    field = _TYPE_DISCRIMINATORS.get(etype)
    if field:
        value = event.get(field)
        if value:
            return f"type:{etype}|{field}:{value}"

    for key in ("monitor_slug", "logger", "server_name"):
        value = event.get(key)
        if value:
            return f"type:{etype}|{key}:{value}"

    text = _message_text(event)
    if text:
        return f"type:{etype}|msg:{_message_shape(text)}"

    return UNIDENTIFIED_SIGNATURE


def is_non_error_event(event: dict[str, Any]) -> bool:
    """True when this event is not an error and the policy must not judge it."""
    return str((event or {}).get("type") or "") in NON_ERROR_EVENT_TYPES


def event_signature(event: dict[str, Any], exc_name: str, hint: dict[str, Any] | None = None) -> str:
    """``class | where | failure-site`` — the throttling key.

    Uses the transaction and the failure site rather than the message, because
    messages carry hostnames, PIDs, hour-values and row ids that defeat
    de-duplication entirely — which is precisely how one class ends up spending a
    whole month's quota. But it does NOT stop at the transaction: see
    :func:`_failure_site`.

    The one exception is :data:`SITE_AGNOSTIC_EXC_NAMES`, where the site is
    where a signal LANDED rather than where anything went wrong.
    """
    event = event or {}
    where = event.get("transaction") or event.get("logger") or "?"
    if exc_name in SITE_AGNOSTIC_EXC_NAMES:
        fingerprint = (event.get("fingerprint") or []) if isinstance(
            event.get("fingerprint"), (list, tuple)
        ) else []
        parts = [str(p) for p in fingerprint if p and str(p) != "{{ default }}"]
        site = "fp:" + "|".join(parts) if parts else "signal"
        return f"{exc_name}|{where}|{site}"
    site = _failure_site(event, hint)
    # #1894: when class, transaction AND failure site are all absent, the old
    # code emitted "unknown|?|?" — one bucket for every unidentifiable event in
    # the process. Descend into the event's own shape instead of collapsing.
    if not exc_name and where == "?" and site == "?":
        return _structural_identity(event)
    return f"{exc_name or 'unknown'}|{where}|{site}"


# =============================================================================
# Policy
# =============================================================================

VERDICT_DROP = "drop"
VERDICT_THROTTLE = "throttle"
VERDICT_PASS = "pass"


def classify(event: dict[str, Any], hint: dict[str, Any] | None = None) -> str:
    """Pure tier decision — no counters, no state. The whole policy, testable."""
    exc_name, exc_module, exc_message = _exc_identity(event, hint)
    text = _message_text(event)
    haystack = f"{text} {exc_message.lower()}".strip()
    event_logger = str((event or {}).get("logger") or "")

    # --- DROP ---------------------------------------------------------------
    if exc_name and exc_name in DROP_EXC_NAMES:
        return VERDICT_DROP

    module_root = exc_module.split(".", 1)[0] if exc_module else ""
    if module_root in DROP_CONNECTION_MODULES and exc_name in CONNECTION_EXC_NAMES:
        return VERDICT_DROP

    # Socket errors that surface with the BUILTIN class carry no module
    # provenance, so fall back to the endpoint — matched against our own
    # configured broker hosts by equality, never by substring.
    if exc_name in CONNECTION_EXC_NAMES and _is_broker_endpoint_error(exc_message):
        return VERDICT_DROP

    if event_logger in INFRA_LOGGERS and any(
        _all_tokens(haystack, tokens) for tokens in _DROP_MESSAGE_RULES
    ):
        return VERDICT_DROP

    # --- THROTTLE -----------------------------------------------------------
    if exc_name in THROTTLE_EXC_NAMES:
        if exc_name != "RuntimeError" or any(m in haystack for m in _EVENT_LOOP_MARKERS):
            return VERDICT_THROTTLE

    return VERDICT_PASS


class SentryVolumeFilter:
    """The ``before_send`` callable, with counters for post-deploy verification."""

    def __init__(self) -> None:
        self._throttle = _SignatureThrottle()
        self._lock = threading.Lock()
        #: ``not_error`` and ``unidentified`` are new in #1894 and both exist to
        #: make a previously silent path countable. ``not_error`` is the cron /
        #: telemetry passthrough; ``unidentified`` is every event the signature
        #: fallback still could not name, which is the early warning that a new
        #: event shape has arrived and needs a discriminator.
        self.counts = {
            "passed": 0,
            "dropped": 0,
            "throttled": 0,
            "backstopped": 0,
            "not_error": 0,
            "unidentified": 0,
        }
        self._started_at = time.monotonic()
        # Start the 60s clock NOW rather than at 0.0. With 0.0 the first event a
        # process ever sees fires the summary immediately — which in a test run
        # that builds hundreds of filter instances means hundreds of Redis
        # round-trips, and in production means a burst at every dyno boot.
        self._last_log = self._started_at
        self._export_muted_until = 0.0

    def _bump(self, key: str) -> None:
        with self._lock:
            self.counts[key] += 1

    def _maybe_log(self) -> None:
        """Summarise at most once a minute, so the filter itself is auditable.

        Without this the filter is invisible: you cannot tell "the fix worked"
        from "the errors stopped happening", and #1501 is entirely a story about
        an absence being mistaken for health.
        """
        now = time.monotonic()
        with self._lock:
            if now - self._last_log < 60:
                return
            self._last_log = now
            snapshot = dict(self.counts)
            uptime = max(1.0, now - self._started_at)
        logger.info("sentry_filter: %s", snapshot)
        # #1894 finding 2: a per-process log line is not observability. Alex:
        # "a discard counter nobody can read is the same defect one level up."
        # Push the same numbers somewhere a reader who is not this process can
        # get them (ops-snapshot reads the aggregate).
        self._export(snapshot, uptime)

    def _export(self, snapshot: dict[str, int], uptime_s: float) -> None:
        """Best-effort push of this process's counters to the shared census.

        Called at most once a minute, from the 60s log tick — deliberately NOT
        from every event. gotcha #39 still applies (the biggest error class IS
        Redis being unreachable, and this code runs on the exception path), so
        three things bound the exposure: the bounded client's 5s socket timeout,
        a 5-minute mute after any failure so an outage is paid for once rather
        than every minute, and a total swallow of the exception. A filter that
        cannot report its counters must still filter.
        """
        if not EXPORT_ENABLED:
            return
        now = time.monotonic()
        if now < self._export_muted_until:
            return
        try:
            export_counts(snapshot, uptime_s)
        except Exception:
            self._export_muted_until = now + 300
            logger.debug("sentry_filter: counter export unavailable", exc_info=True)

    def __call__(
        self, event: dict[str, Any], hint: dict[str, Any] | None = None
    ) -> dict[str, Any] | None:
        try:
            return self._decide(event, hint)
        except Exception:  # never let the filter break error reporting
            logger.exception("sentry_filter failed open")
            return event

    def _decide(
        self, event: dict[str, Any], hint: dict[str, Any] | None
    ) -> dict[str, Any] | None:
        # #1894, BEFORE any tier decision: an error-volume policy may only judge
        # errors. A cron check-in that reaches this function has already been
        # mis-typed by the SDK (client.py:872-875 excludes only transactions);
        # dropping it here would disable Sentry Crons AND bill the loss to the
        # error category (client.py:883 hardcodes data_category="error").
        if is_non_error_event(event):
            self._bump("not_error")
            return event

        verdict = classify(event, hint)
        if verdict == VERDICT_DROP:
            self._bump("dropped")
            self._maybe_log()
            return None

        exc_name, _, _ = _exc_identity(event, hint)
        signature = event_signature(event, exc_name, hint)
        if signature == UNIDENTIFIED_SIGNATURE:
            # Countable, not silent. The old code had no way to distinguish "one
            # signature repeated 19,000 times" from "19,000 events we could not
            # tell apart", and those need opposite responses.
            self._bump("unidentified")

        if verdict == VERDICT_THROTTLE:
            if self._throttle.allow(
                signature, limit=THROTTLE_PER_WINDOW, window_s=THROTTLE_WINDOW_S
            ):
                self._bump("passed")
                return event
            self._bump("throttled")
            self._maybe_log()
            return None

        # PASS, but nothing is unbounded. A novel signature always gets its first
        # event through immediately; only a repeating one is capped.
        if self._throttle.allow(
            signature,
            limit=sentry_budget.current_backstop_per_window(),
            window_s=BACKSTOP_WINDOW_S,
        ):
            self._bump("passed")
            return event
        self._bump("backstopped")
        self._maybe_log()
        return None


#: Loggers whose ERROR records are a strict DUPLICATE of a richer event we send
#: ourselves, so the log-derived copy is pure waste.
#:
#: ``app.tasks.watchdog`` measured 1,588 events in the 2026-07-21 cycle — 24% of
#: the whole month's allowance — and it was TWO events per reading: 805 from
#: ``sentry_sdk.capture_message`` (fingerprinted on ``[alert_class, provider]``,
#: tagged, the #219E fix) and 774 from the ``logger.critical`` beside it, which
#: the SDK's LoggingIntegration promotes to an event of its own because its
#: default ``event_level`` is ``logging.ERROR``. The capture is strictly the
#: better of the two, so the log record is silenced FOR SENTRY only — the line
#: still goes to the dyno logs, and the GitHub filing rail is untouched.
DUPLICATE_EVENT_LOGGERS = ("app.tasks.watchdog",)


def install_logger_ignores() -> tuple[str, ...]:
    """Stop :data:`DUPLICATE_EVENT_LOGGERS` from generating log-derived events.

    Called from both ``sentry_sdk.init`` sites. Uses the SDK's own
    ``ignore_logger`` rather than a rule in :func:`classify`, because the intent
    is "this logger is already reported elsewhere", not "this content is noise" —
    and a policy rule would have to guess at message text to say the same thing.
    """
    try:
        from sentry_sdk.integrations.logging import ignore_logger
    except Exception:  # pragma: no cover - SDK shape change must not break boot
        logger.warning("sentry_filter: ignore_logger unavailable; duplicate log events will send")
        return ()
    for name in DUPLICATE_EVENT_LOGGERS:
        ignore_logger(name)
    return DUPLICATE_EVENT_LOGGERS


def build_before_send() -> Callable[[dict, dict | None], dict | None]:
    """Construct the filter. One instance per process (state is per-process)."""
    install_logger_ignores()
    return SentryVolumeFilter()


# =============================================================================
# Observability — #1894 finding 2, second half
#
# Alex, 2026-08-17: "a discard counter nobody can read is the same defect one
# level up." Before this, the ONLY record of what the filter destroyed was
# `logger.info("sentry_filter: %s", ...)` on each dyno, once a minute. Finding
# that number required already suspecting the problem AND reaching `heroku logs`
# — and in this sandbox the logs CLI is EPERM-blocked, so #1894 had to be read
# through the Platform API. A counter behind that much friction is not observed.
#
# Idiom deliberately copied from `redis_state.get_hard_kill_census()`: each
# process writes its own self-expiring key; a reader SCANs the prefix and totals
# them. Self-expiring matters here — ~72 process incarnations a day means a hash
# of permanent per-process fields would grow without bound and would keep
# reporting dead processes' discards as if they were current.
# =============================================================================

#: One key per live process incarnation. TTL slightly over an hour so a dyno that
#: dies stops contributing within the hour instead of forever.
FILTER_COUNTS_PREFIX = "bainluck:sentry:filter_counts:"
FILTER_COUNTS_TTL_S = 3900

#: The census is a PRODUCTION instrument. Off the dyno there is no fleet to
#: aggregate, and leaving it on made a unit-test run open a Redis connection for
#: every filter instance the census replay constructs — hundreds of them, each
#: paying the client's connect retry budget. ``export_counts`` itself stays
#: callable regardless, so the export path is still directly testable; this gates
#: only the automatic push from the 60s tick.
EXPORT_ENABLED = bool(os.getenv("DYNO"))


def _process_identity() -> str:
    """Stable within one process, distinct across incarnations."""
    import socket

    try:
        host = socket.gethostname()
    except Exception:  # pragma: no cover - hostname is never load-bearing
        host = "unknown"
    return f"{host}:{os.getpid()}"


def export_counts(snapshot: dict[str, int], uptime_s: float) -> None:
    """Write this process's counters to the shared census. Raises on failure.

    Raising is deliberate — the caller (:meth:`SentryVolumeFilter._export`) owns
    the swallow and the failure mute, so this function stays testable and a
    direct caller gets a real error instead of a silent no-op.
    """
    import json

    from app.tasks.redis_state import get_redis_client

    payload = dict(snapshot)
    payload["window_s"] = round(uptime_s, 1)
    payload["cap"] = sentry_budget.current_backstop_per_window()
    # fast_fail: this runs on the exception path (gotcha #39). A churning
    # connection must degrade in a fraction of a second, not spend the full
    # 3-attempt retry budget while an error is waiting to be reported.
    get_redis_client(fast_fail=True).setex(
        FILTER_COUNTS_PREFIX + _process_identity(),
        FILTER_COUNTS_TTL_S,
        json.dumps(payload),
    )


def _read_filter_counts() -> dict[str, dict]:
    """``{process identity: counters}`` across every live SDK process."""
    import json

    from app.tasks.redis_state import get_redis_client

    rows: dict[str, dict] = {}
    r = get_redis_client()
    for key in r.keys(f"{FILTER_COUNTS_PREFIX}*"):
        key_str = key.decode() if isinstance(key, bytes) else key
        raw = r.get(key_str)
        if not raw:
            continue
        try:
            rows[key_str[len(FILTER_COUNTS_PREFIX):]] = json.loads(raw)
        except (TypeError, ValueError):
            continue
    return rows


#: Counter keys that represent an event the filter DESTROYED. ``not_error`` is
#: excluded on purpose: a passthrough is the opposite of a discard, and folding
#: it in here would let the cron fix look like the flood it removed.
_DISCARD_KEYS = ("dropped", "throttled", "backstopped")


def summarize_filter_counts(rows: dict[str, dict]) -> dict:
    """Aggregate per-process counters into one verdict-carrying reading.

    Pure over ``rows`` so it unit-tests without Redis.

    The two things this must never do, both of them #1894's own failure mode:
    report a rate without the window that makes it a rate, and report an ABSENCE
    of reporting processes as a healthy zero.
    """
    if not rows:
        return {
            "status": "no_data",
            "processes": 0,
            "discarded": 0,
            "discarded_per_day": None,
            # Derived live, like every other display of this number. The
            # import-time constant froze the cycle length at boot; showing it
            # here is how R4's 5,292-displayed / 5,859-enforced split reached an
            # operator's screen.
            "ceiling_per_day": sentry_budget.discard_ceiling_per_day(),
            "over_ceiling": None,
            "note": "no SDK process has reported counters — an absence, not a zero",
        }

    totals: dict[str, int] = {}
    window_s = 0.0
    for row in rows.values():
        for key, value in row.items():
            if key in ("window_s", "cap"):
                continue
            try:
                totals[key] = totals.get(key, 0) + int(value)
            except (TypeError, ValueError):
                continue
        try:
            window_s = max(window_s, float(row.get("window_s") or 0))
        except (TypeError, ValueError):
            pass

    discarded = sum(totals.get(k, 0) for k in _DISCARD_KEYS)
    window_s = max(window_s, 1.0)
    # ONE derivation (C-CERT-SENTRY-R4). The rate, the ceiling and the verdict
    # come from the same call, so the number shown IS the number compared
    # against. Reading the ceiling separately for display is what split them.
    reading = sentry_budget.discard_ceiling_reading(discarded, window_s)
    return {
        "status": "ok",
        "processes": len(rows),
        "counts": totals,
        "discarded": discarded,
        "window_s": round(window_s, 1),
        "discarded_per_day": reading["discarded_per_day"],
        "ceiling_per_day": reading["ceiling_per_day"],
        "over_ceiling": reading["over_ceiling"],
        "unidentified": totals.get("unidentified", 0),
        "not_error_passthrough": totals.get("not_error", 0),
        "budget": sentry_budget.current_budget_verdict(),
    }


def filter_discard_census() -> dict:
    """The reading an operator (or ``/api/admin/ops-snapshot``) consumes."""
    try:
        return summarize_filter_counts(_read_filter_counts())
    except Exception as exc:  # noqa: BLE001
        # A read failure is NOT "no discards". Say which one it is.
        return {
            "status": "unavailable",
            "error_class": exc.__class__.__name__,
            "over_ceiling": None,
            "ceiling_per_day": sentry_budget.discard_ceiling_per_day(),
        }
