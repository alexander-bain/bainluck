"""The router-queue / app / DB split for one HTTP request.

LAT-P070 (#1917, #1609). This module is the instrument the golf probe was scoped
against, and it exists because LAT-P069 measured that the probe's premise was
false: the *data* is free, the *measurement* was not.

```
grep -rn "X-Request-Start" backend/app/          ->  0 hits   (LAT-P069)
grep -c  "debug_timing"    backend/app/routes/golf.py  ->  0   (LAT-P069)
```

Both terms of the requested split were unreachable, so the probe was a one-queue
build rather than a curl. This is that build.

## What the three numbers are, and why they do NOT sum to one whole

Getting this wrong is the easiest way to publish a false attribution, so it is
stated before the code:

| term | measured as | contains |
|---|---|---|
| `router_queue_ms` | dyno receive time − `X-Request-Start` | Heroku router hold + edge→dyno network |
| `db_ms` | Σ per-cursor `after − before` | time inside the driver, including waiting on a contended buffer pool |
| `app_ms` | `wall_ms − db_ms` | Python/CPU/GIL, serialisation, Redis, outbound HTTP |
| `wall_ms` | app-observed request duration | `app_ms + db_ms` |

`wall_ms = app_ms + db_ms`. **`router_queue_ms` is NOT part of `wall_ms`** — the
app cannot observe time it did not yet have the request for. End-to-end is
`router_queue_ms + wall_ms`, exposed as `edge_ms`. A reader who adds all four
double-counts, which is precisely how a "router is 40 % of the request" claim
gets minted out of arithmetic rather than measurement.

## The registered prediction this feeds (LAT-P069 §4, unchanged)

Of the ~12.8 s p90 excess on `/api/golf/tournaments/{slug}`: **DB > 70 %**, app
CPU/GIL 10–25 %, **router queue < 10 %**.

🔴 **HALT: `router_queue_ms` > 30 % of the excess** ⇒ the bottleneck is web-dyno
capacity, not DB contention, and every "background saturation reaches users
through the database" conclusion in LAT-P068 §5 is re-derived before anything
else ships.

## Two honest limits on `X-Request-Start`, neither of which is fixable here

1. **It is client-settable.** Heroku's router is documented to set the header,
   but whether it *overwrites* a caller-supplied one is not something this lane
   verified, and an unverified assumption dressed as a guarantee is the failure
   this program keeps writing rulings about. The defence is therefore not trust,
   it is the plausibility window below: a value that cannot be a real queue is
   reported as `None` (unusable) rather than as a number. Blast radius of a
   forged header is a wrong row in our own diagnostics — it mints no Redis key
   (the bucket is the route template, #1500/r329-B2) and reaches no user.
2. **Router and dyno clocks are not the same clock.** LAT-P068's S4 capture
   measured a ~5.2 s skew between an observer and a worker. A small negative
   delta is therefore skew, not a time machine, and clamps to `0.0`; a *large*
   negative one is a broken input and returns `None`.

## Why the accumulator is a mutable object in a ContextVar

The subtle part, recorded because it is the thing most likely to be "simplified"
into breakage by a later reader. **Both statements below are measured, and the
first draft of this docstring got the mechanism wrong** — it blamed the greenlet,
and the guard written to prove that claim refuted it instead:

* **The greenlet boundary is NOT the problem.** SQLAlchemy's async engine runs
  the DBAPI call inside `greenlet_spawn`, and on the pinned versions
  (SQLAlchemy 2.0.50 / greenlet 3.5.1) that greenlet shares the caller's Context
  outright — a `ContextVar.set()` inside it propagates *back out*. Measured, not
  assumed. It is also **not depended on**, precisely because it is a library
  implementation detail that could change under us.
* **The asyncio task boundary IS the problem, and it is the one we actually
  cross.** `BaseHTTPMiddleware.call_next` runs the downstream app in a separate
  task, and a task gets a *copy* of the Context. A `set()` performed downstream
  is invisible to the middleware that awaits it; a **mutation of the object the
  ContextVar already points at** is visible, because both contexts hold the same
  reference.

So the ContextVar is set exactly once, on the way in, to a **mutable**
:class:`DbTiming`, and the listener only ever mutates its fields. Never rebind
it mid-request: on the greenlet path that would silently work, and on the task
path it would silently lose every query — the worst possible combination,
because it would pass a casual test and under-report DB time in production,
which is the exact direction that would falsely clear the DB of the golf tail.

`tests/test_lat_p070_request_timing.py` pins both boundaries against the real
mechanisms rather than against a description of them.
"""

from __future__ import annotations

import logging
import math
import time
from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

#: The header Heroku's router stamps on every inbound request. Lower-cased
#: because Starlette's header mapping is case-insensitive but plain dict lookups
#: in tests are not.
REQUEST_START_HEADER = "x-request-start"

#: The response header carrying the split. One header rather than four so a
#: proxy that drops unknown headers drops all-or-nothing instead of leaving a
#: reader with two thirds of an attribution.
SPLIT_HEADER = "X-Timing-Split"

#: A delta above this is not a queue, it is a bad input (a stale, forged or
#: wrongly-scaled header). Generous on purpose: Heroku queue time genuinely
#: reaches tens of seconds under the saturation this probe is built to measure,
#: so the bound has to sit well above the phenomenon or it would censor the
#: finding. 300 s is ~11× the worst golf observation on record (26.714 s).
MAX_PLAUSIBLE_QUEUE_S = 300.0

#: A negative delta up to this magnitude is router/dyno clock skew and clamps to
#: zero. Beyond it, the input is refused. LAT-P068 measured ~5.2 s of skew
#: between two clocks in this system; 10 s is that with headroom.
MAX_CLOCK_SKEW_S = 10.0

#: Epoch magnitude thresholds. `X-Request-Start` is milliseconds on Heroku, but
#: nginx sends `t=<seconds.millis>` and some proxies send microseconds, and a
#: unit misread is a 1000× error in the one number this probe exists to publish.
_MICROS_MIN = 1e14
_MILLIS_MIN = 1e11
_SECONDS_MIN = 1e8

#: Emitting a split for an endpoint that ran no queries is not noise — "the DB
#: was not the problem" is a finding. But an unbounded query count in a header
#: is, so it is capped for display only; the accumulator itself keeps counting.
_QUERY_COUNT_DISPLAY_MAX = 100_000


@dataclass
class DbTiming:
    """Per-request DB accumulator. **Mutated in place — never rebound.**"""

    total_ms: float = 0.0
    queries: int = 0
    #: Longest single statement in the request. A 12 s request made of one 11 s
    #: query and a 3 s request made of 300 × 10 ms queries are different bugs
    #: with different owners, and a sum alone cannot tell them apart.
    max_query_ms: float = 0.0
    #: Statements that started but never recorded a finish (an exception between
    #: the two events). Counted rather than silently dropped, so a partial
    #: `total_ms` announces itself instead of reading as a fast request.
    unfinished: int = field(default=0)

    def record(self, elapsed_ms: float) -> None:
        if not math.isfinite(elapsed_ms) or elapsed_ms < 0:
            return
        self.total_ms += elapsed_ms
        self.queries += 1
        if elapsed_ms > self.max_query_ms:
            self.max_query_ms = elapsed_ms


_db_timing: ContextVar[Optional[DbTiming]] = ContextVar("lat_p070_db_timing", default=None)


def begin_db_timing() -> Token:
    """Start accumulating for this request. Returns the token to reset with."""
    return _db_timing.set(DbTiming())


def current_db_timing() -> Optional[DbTiming]:
    """The accumulator for the request in flight, or ``None`` outside one.

    ``None`` is the normal state for Celery tasks and for anything that runs
    before the middleware: the listener is installed process-wide, so "no
    accumulator" is how non-request DB work stays out of request timings.
    """
    return _db_timing.get()


def end_db_timing(token: Optional[Token]) -> None:
    """Reset the ContextVar. Safe to call with ``None`` or a stale token."""
    if token is None:
        return
    try:
        _db_timing.reset(token)
    except (ValueError, RuntimeError):
        # ValueError: token minted in a different Context (BaseHTTPMiddleware can
        # run dispatch and the downstream app in different tasks).
        # RuntimeError: token already used — CPython raises this, not ValueError,
        # and catching only ValueError let a double teardown escape as a 500 from
        # inside an observability rail. Found by the guard below, not by review.
        # Either way clearing is correct, and strictly better than leaking an
        # accumulator into the next request this worker serves.
        _db_timing.set(None)


def record_query(elapsed_ms: float, *, finished: bool = True) -> None:
    """Add one statement's duration. No-op when no request is in flight.

    **The only write path.** The engine listener used to call ``acc.record()``
    directly, which made this a second implementation of the same write — and a
    mutation that broke `record_query` left the listener working, so the guard
    reported the instrument healthy while the path production actually uses was
    untested. One path, so one mutation covers both callers.
    """
    acc = _db_timing.get()
    if acc is None:
        return
    if finished:
        acc.unfinished = max(0, acc.unfinished - 1)
    acc.record(elapsed_ms)


def note_query_started() -> None:
    """Mark a statement in flight, so a statement that raises is not silent."""
    acc = _db_timing.get()
    if acc is not None:
        acc.unfinished += 1


def parse_request_start(raw) -> Optional[float]:
    """Epoch **seconds** from an ``X-Request-Start`` value, or ``None``.

    Accepts every form this fleet could plausibly be handed, because guessing
    the unit wrong is a 1000× error:

    * ``"1787000000000"``      Heroku, milliseconds
    * ``"t=1787000000000"``    the ``t=`` prefixed form
    * ``"1787000000.123"``     seconds
    * ``"1787000000000000"``   microseconds

    Anything non-numeric, non-finite, or outside a plausible epoch returns
    ``None`` — the caller must render that as "unusable", never as ``0``.
    """
    if raw is None:
        return None
    if isinstance(raw, bytes):
        try:
            raw = raw.decode("ascii")
        except UnicodeDecodeError:
            return None
    if isinstance(raw, (int, float)):
        text = repr(float(raw))
    elif isinstance(raw, str):
        text = raw.strip()
    else:
        return None
    if not text:
        return None
    # `t=1787...`, and the `t=1787..., t=1787...` list form a chained proxy can
    # produce — take the first, which is the outermost hop.
    if "," in text:
        text = text.split(",", 1)[0].strip()
    if text.lower().startswith("t="):
        text = text[2:].strip()
    try:
        value = float(text)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(value) or value <= 0:
        return None
    if value >= _MICROS_MIN:
        return value / 1e6
    if value >= _MILLIS_MIN:
        return value / 1e3
    if value >= _SECONDS_MIN:
        return value
    return None


def router_queue_ms(raw, *, now: Optional[float] = None) -> Optional[float]:
    """Milliseconds between the router stamping the request and this call.

    ``None`` — meaning **unusable**, not zero — when the header is absent,
    unparseable, implausibly old, or implausibly far in the future. Small
    negative deltas are clock skew and clamp to ``0.0``.
    """
    started = parse_request_start(raw)
    if started is None:
        return None
    now = time.time() if now is None else now
    delta = now - started
    if delta < 0:
        return 0.0 if delta >= -MAX_CLOCK_SKEW_S else None
    if delta > MAX_PLAUSIBLE_QUEUE_S:
        return None
    return delta * 1000.0


def build_split(
    *,
    wall_ms: float,
    db: Optional[DbTiming],
    router_ms: Optional[float],
) -> dict:
    """The attributed split for one request, as plain data.

    ``app_ms`` is a residual, so it is floored at zero: the DB clock and the
    wall clock are taken at different layers and a few hundred microseconds of
    disagreement must not render as negative app time.
    """
    wall = float(wall_ms) if math.isfinite(wall_ms) and wall_ms >= 0 else 0.0
    db_ms = float(db.total_ms) if db is not None else 0.0
    if not math.isfinite(db_ms) or db_ms < 0:
        db_ms = 0.0
    # A DB total above wall means the two clocks disagree, or (more usefully) that
    # concurrent statements on one request overlapped. Report it rather than
    # hiding it: `db_ms > wall_ms` is itself a finding about concurrency.
    app_ms = max(0.0, wall - db_ms)
    split = {
        "wall_ms": round(wall, 1),
        "db_ms": round(db_ms, 1),
        "app_ms": round(app_ms, 1),
        "queries": min(db.queries, _QUERY_COUNT_DISPLAY_MAX) if db is not None else 0,
        "max_query_ms": round(db.max_query_ms, 1) if db is not None else 0.0,
        "router_queue_ms": None if router_ms is None else round(float(router_ms), 1),
    }
    if db is not None and db.unfinished:
        split["unfinished_queries"] = db.unfinished
    split["edge_ms"] = round(wall + (router_ms or 0.0), 1) if router_ms is not None else None
    # The share a reader actually wants, computed once here so three call sites
    # cannot compute it three ways.
    if wall > 0:
        split["db_share"] = round(min(db_ms, wall) / wall, 3)
    else:
        split["db_share"] = None
    return split


def format_split_header(split: dict) -> str:
    """``wall=..;db=..;app=..;q=..;router=..`` — ``na`` for an unusable term.

    ``na`` rather than omitting the key or writing ``0``: gotcha #53's shape.
    "We could not measure the router" and "the router took no time" are
    different claims, and a reader handed ``router=0`` will make the second one.
    """
    router = split.get("router_queue_ms")
    parts = [
        f"wall={split.get('wall_ms', 0)}",
        f"db={split.get('db_ms', 0)}",
        f"app={split.get('app_ms', 0)}",
        f"q={split.get('queries', 0)}",
        f"maxq={split.get('max_query_ms', 0)}",
        f"router={'na' if router is None else router}",
    ]
    if split.get("unfinished_queries"):
        parts.append(f"unfinished={split['unfinished_queries']}")
    return ";".join(parts)


_INSTALLED_FLAG = "_lat_p070_db_timer_installed"
_START_KEY = "_lat_p070_query_t0"


def install_request_db_timer(async_engine) -> bool:
    """Attach the per-statement timer to an engine. Idempotent.

    Returns ``True`` if it installed, ``False`` if it was already there — so a
    double call during a reload cannot double-count every query in the fleet.

    Accepts an ``AsyncEngine`` (uses ``.sync_engine``) or a plain ``Engine``,
    which is what makes the mechanism testable without a Postgres this sandbox
    does not have (no local PG — real-engine gates are CI-only).
    """
    from sqlalchemy import event

    target = getattr(async_engine, "sync_engine", async_engine)
    if getattr(target, _INSTALLED_FLAG, False):
        return False

    @event.listens_for(target, "before_cursor_execute")
    def _before(conn, cursor, statement, parameters, context, executemany):  # noqa: ANN001
        # Stored on the CONNECTION, not a contextvar: `before`/`after` are
        # guaranteed to be the same connection, and a contextvar here would be
        # rebound inside the greenlet (see module docstring).
        conn.info[_START_KEY] = time.perf_counter()
        note_query_started()

    @event.listens_for(target, "after_cursor_execute")
    def _after(conn, cursor, statement, parameters, context, executemany):  # noqa: ANN001
        t0 = conn.info.pop(_START_KEY, None)
        if t0 is None:
            return
        record_query((time.perf_counter() - t0) * 1000.0)

    try:
        setattr(target, _INSTALLED_FLAG, True)
    except AttributeError:  # pragma: no cover — Engine allows attribute set
        logger.debug("Could not mark engine as instrumented", exc_info=True)
    return True
