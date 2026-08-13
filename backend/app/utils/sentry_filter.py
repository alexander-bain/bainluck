"""ONE Sentry ``before_send`` filter, shared by every process that initialises the SDK.

Why this file exists (#1501, Alex ruling 2026-08-13 — "census then cut volume").

The free Developer plan (`am3_f`) allows 5,000 errors per billing month with
on-demand disabled, and the billing period runs the 21st to the 20th. Measured
via the org stats API, the last three cycles exhausted the quota on day 18, day
19 and then **day 8** (2026-07-21 -> 2026-07-28, ~6,584 accepted). Once the cap
is hit every subsequent error is dropped, so the rail goes dark for the rest of
the month and a green "0 events in 24h" read means nothing. That is the inverse
of gotcha #49: there the lifetime count overstates, here the 24h bucket
understates to zero.

A ``before_send`` filter written to kill exactly this noise ALREADY existed — in
``app/main.py``. The census found it was doing almost nothing, for two
independent reasons, and both are fixed here:

1. **It only ever ran in the web dyno.** Celery workers boot from
   ``app.tasks.celery_app`` and never import ``app.main``; ``app/tasks/__init__``
   called ``sentry_sdk.init()`` with no ``before_send`` at all. Every one of the
   top burners is worker-side, so the filter lived in the one process that does
   not produce the noise.

2. **The Redis test matched on the wrong string.** It asked for ``"redis" in
   str(exc)``, but redis-py's connection error reads ``Error 8 connecting to
   ec2-<addr>.compute-1.amazonaws.com:6379. nodename nor servname provided`` —
   it names the EC2 host and never the word "redis". So the single largest
   burner (1,829 events, 31% of the cycle, culprit
   ``redis.connection in connect_check_health``) passed the filter even in the
   web dyno. This module tests the exception's ``__module__`` instead, which is
   what actually identifies the library.

Two shapes get dropped, and the distinction matters:

* **Exception events** — matched on class name, or on the defining module for
  the redis transport churn.
* **Message/log events** — Celery worker deaths arrive from billiard as *log
  records*, not exceptions, so ``hint["exc_info"]`` is ``None`` and a
  name-based filter can never see them. ``ForkPoolWorker ... signal 9 (SIGKILL)``
  alone was 599 events. These are matched on the message text.

Everything dropped here is **transient infrastructure churn that recovers on its
own and has a non-Sentry alarm**: Redis reconnects, Celery restarts the worker,
and task death is already tracked in Redis task-metrics + the cockpit. Nothing
that carries unique diagnostic payload is filtered. In particular this does NOT
touch the four "Sentry-only" alert classes from #1158 — those are cut by
emission rate-limiting at the source (see ``app/tasks/watchdog.py``), never by
dropping the first occurrence.
"""

from __future__ import annotations

import re

# Exception CLASS NAMES that are pure infrastructure churn.
#
# Note "WorkerLostError", not "WorkerLost": the original list in main.py said
# "WorkerLost", but billiard's class is `billiard.exceptions.WorkerLostError`,
# so the name never matched and 246 events sailed through. Both spellings are
# kept — the wrong one costs nothing and protects against the reverse typo.
_DROP_EXC_NAMES = frozenset(
    {
        "WorkerLostError",       # billiard — worker killed; Celery restarts it
        "WorkerLost",            # defensive: the pre-#1501 spelling
        "Terminated",            # billiard — deliberate worker shutdown
        "TimeLimitExceeded",     # billiard — hard time limit, already metered
        "SoftTimeLimitExceeded", # celery — 614 events/cycle, was NOT in the list
        "PendingRollbackError",  # sqlalchemy — follow-on of an already-reported error
        "InvalidRequestError",   # sqlalchemy — ditto
    }
)

# Exception MODULES whose connection/transport errors are self-healing churn.
# Matching the module rather than the message is the fix for bug (2) above.
_DROP_CONNECTION_MODULES = ("redis", "kombu", "amqp")

# Exception names that are only dropped when raised from a module above —
# a ConnectionError from our own HTTP clients is real signal and must survive.
_CONNECTION_EXC_NAMES = frozenset(
    {"ConnectionError", "TimeoutError", "ConnectionResetError", "BusyLoadingError"}
)

# Substrings identifying LOG-RECORD events (no exc_info) that report a worker
# death already covered by Redis task-metrics and the cockpit tile.
_DROP_MESSAGE_SUBSTRINGS = (
    "exited with 'signal 9 (sigkill)'",
    "exited with 'signal 15 (sigterm)'",
    "hard time limit",
    "soft time limit",
    "worker exited prematurely",
    "connection to redis lost",
    "retry (",  # redis-py retry ladder: "Retry (15/20) in 1.00 second."
)


# redis-py renders connection failures as:
#   "Error 8 connecting to ec2-1-2-3-4.compute-1.amazonaws.com:6379. <detail>"
_CONNECTING_TO_RE = re.compile(r"connecting to ([^\s:,]+):(\d+)", re.IGNORECASE)

# Managed-broker domains whose transport churn is self-healing. Matched as a
# host SUFFIX against a parsed host, never as a free substring of the message.
_BROKER_HOST_SUFFIXES = (".compute-1.amazonaws.com", ".amazonaws.com")


def _module_of(exc_type) -> str:
    return getattr(exc_type, "__module__", "") or ""


def _is_broker_endpoint_error(text: str) -> bool:
    """True when ``text`` reports a failed connection to a managed broker host.

    Parses the host out of the message and compares domain suffixes, so a host
    that merely CONTAINS a broker domain somewhere in it does not match.
    """
    match = _CONNECTING_TO_RE.search(text or "")
    if not match:
        return False
    host = match.group(1).lower().rstrip(".")
    if host.endswith(_BROKER_HOST_SUFFIXES):
        return True
    # Local/CI brokers, where the host is literally named for the service.
    return host in ("redis", "localhost", "127.0.0.1")


def should_drop(exc_info, message: str | None) -> bool:
    """Pure predicate — the whole decision, with no SDK types involved.

    Split out from ``before_send`` so the policy is unit-testable without
    constructing Sentry event dicts.
    """
    if exc_info:
        exc_type = exc_info[0]
        exc_name = getattr(exc_type, "__name__", "") if exc_type else ""

        if exc_name in _DROP_EXC_NAMES:
            return True

        # Transport churn from the redis/broker client libraries.
        #
        # Match on the DEFINING MODULE plus the exception hierarchy, not on the
        # class name: redis-py raises a family here (ConnectionError,
        # TimeoutError, BusyLoadingError, and subclasses of each), and a
        # name-only list silently misses every subclass it did not enumerate.
        # Deliberately NOT every redis exception — a ResponseError can be a real
        # bug in our own command usage, so it must survive.
        if exc_type is not None:
            module_root = _module_of(exc_type).split(".", 1)[0]
            if module_root in _DROP_CONNECTION_MODULES:
                if exc_name in _CONNECTION_EXC_NAMES or (
                    isinstance(exc_type, type)
                    and issubclass(exc_type, (ConnectionError, TimeoutError, OSError))
                ):
                    return True

        if exc_name in _CONNECTION_EXC_NAMES:
            # Some socket errors surface with the builtin class (module
            # "builtins"), so the module test above cannot see them. Fall back to
            # the address in redis-py's message — but PARSE the host and match a
            # domain SUFFIX rather than searching for the domain as a substring.
            # A substring test would also match a host that merely contains the
            # text somewhere (CodeQL "incomplete URL substring sanitization"),
            # and here that would silently swallow a real error from an unrelated
            # endpoint.
            text = str(exc_info[1]) if len(exc_info) > 1 else ""
            if _is_broker_endpoint_error(text):
                return True

    if message:
        lowered = message.lower()
        for needle in _DROP_MESSAGE_SUBSTRINGS:
            if needle in lowered:
                return True

    return False


def before_send(event, hint):
    """Sentry ``before_send`` hook. Return ``None`` to drop the event.

    Wrapped defensively: a raising ``before_send`` is swallowed by the SDK and
    the event is sent anyway, so a bug here would silently restore the full
    burn rate rather than announce itself.
    """
    try:
        message = event.get("logentry", {}).get("message") or event.get("message")
        if not message:
            # Worker-death records arrive with the text only in the rendered
            # log entry's formatted field.
            message = event.get("logentry", {}).get("formatted")
        if should_drop(hint.get("exc_info"), message):
            return None
    except Exception:  # pragma: no cover - never let telemetry policy raise
        return event
    return event
