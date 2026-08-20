"""Bound the STATEMENT, not the gap between rows (#2016).

WHAT THE 20s BUDGET COULD NOT SEE

Every attended repair rail that writes per row checks a wall clock at the TOP of
its loop::

    if time.monotonic() - started > APPLY_TIME_BUDGET_S:
        stopped_on_time_budget = True
        break

That bounds loop BOUNDARIES. It cannot bound a single statement, because it is
not running while one is in flight. Measured live on
``POST /api/admin/repairs/team-identity-mapping-repair`` in queue 377: a Celery
task held one transaction open for **8m59s** across a run of fast per-event
``SELECT events…``, so the rail's ``UPDATE team_identity_mapping`` sat in
``Lock: transactionid`` for 3m52s and the NEXT apply call then sat 2m39s behind
the first call's ``Lock: advisory``. Heroku returned H12 at 30s to both clients;
both dynos kept running and kept blocking. Call 3 lost its response and had
still committed 21 rows; call 4 returned 503 having committed zero. Those two
outcomes are indistinguishable to the operator, which is the actual defect —
per-row commits already made the data safe.

THE FIX IS TWO HALVES, AND BOTH ARE NEEDED

1. :data:`SET_LOCK_TIMEOUT_SQL` — ask Postgres to stop WAITING. A statement that
   would block longer than the timeout aborts with SQLSTATE ``55P03``, which is
   a fact the rail can name per row instead of a hang the operator has to guess
   about.
2. :class:`ApplyBudget` — start the wall clock at REQUEST ENTRY rather than at
   loop entry, so the plan load and the gate query are charged against it too.
   A budget that starts after the two slowest pre-loop reads is not a budget for
   the request the dyno is actually serving.

WHY ``set_config``, AND WHY IT IS RE-ISSUED EVERY ROW

``SET LOCAL lock_timeout = :ms`` cannot be written: Postgres ``SET`` takes no
bind parameters, so it would have to be assembled by string formatting.
``set_config(name, value, is_local => true)`` is the parameterisable spelling of
exactly the same thing.

``is_local=true`` is **transaction**-scoped. These rails commit per row — that
is deliberate, ``team_identity_mapping`` and ``events`` are both written by live
traffic — so each commit ends the transaction the setting lived in. Hoisting one
``set_config`` above the loop therefore protects the FIRST row and silently
protects nothing after it: a guard that looks present in the diff, applies once,
and leaves every later row exposed. It is re-issued inside every row's
transaction, and ``tests/test_repair_lock_budget.py`` models the transaction
scope in its double so that hoisting it reds a test.
"""

from __future__ import annotations

import time

from sqlalchemy import text

#: Postgres raises this SQLSTATE — ``lock_not_available`` — when ``lock_timeout``
#: fires. Classification is by SQLSTATE and never by message text: the message is
#: localised and version-dependent, the code is contractual.
LOCK_NOT_AVAILABLE_SQLSTATE = "55P03"

#: Transaction-scoped ``lock_timeout``. See the module docstring for why this is
#: ``set_config`` rather than ``SET LOCAL`` (bind params) and why it is issued
#: per row rather than once (transaction scope).
SET_LOCK_TIMEOUT_SQL = text(
    "SELECT set_config('lock_timeout', CAST(:ms AS text), true)"
)

#: A contended row must never be given more than this share of what is left of
#: the request. Half: the rail still has a verification query and a response to
#: serialise after the loop, and a second contended row should still be reachable.
LOCK_TIMEOUT_SHARE = 0.5

#: Never wait less than this. Below a few hundred milliseconds the timeout stops
#: measuring contention and starts measuring ordinary write latency, which would
#: turn healthy rows into false LOCK_TIMEOUT findings.
LOCK_TIMEOUT_FLOOR_MS = 250

#: Never wait more than this, however much budget is left. Three seconds is far
#: longer than any uncontended write on these tables and far shorter than the
#: 30s wall, so a row that exceeds it is contended, not slow.
LOCK_TIMEOUT_CEILING_MS = 3000

#: Do not START a row with less than this left in the request. A row costs a
#: ``set_config``, an advisory lock, a write and a commit; beginning one with
#: 200ms left is how a loop-boundary check still overruns the wall.
MIN_ROW_BUDGET_S = 1.0


def lock_timeout_value(ms: int) -> str:
    """The parameter value for :data:`SET_LOCK_TIMEOUT_SQL`, units included.

    ``lock_timeout`` accepts a bare integer and reads it as milliseconds, but a
    bare integer in a log line reads as anything. Spelling the unit means the
    value in the response body and the value Postgres received are the same
    string.
    """
    return f"{int(ms)}ms"


def is_lock_timeout(exc: BaseException) -> bool:
    """True iff ``exc`` is Postgres refusing to keep WAITING for a lock.

    Walks the driver-exception chain, because SQLAlchemy wraps asyncpg's
    ``LockNotAvailableError`` in an ``OperationalError`` and the SQLSTATE lives
    on the inner one. Anything that is not ``55P03`` returns False and must be
    re-raised by the caller: a rail that swallowed every exception here would
    turn a genuine write failure into a row that merely "timed out", which is
    the gotcha-#36 shape one table over.
    """
    seen: set[int] = set()
    cur: BaseException | None = exc
    while cur is not None and id(cur) not in seen:
        seen.add(id(cur))
        for attr in ("sqlstate", "pgcode"):
            if getattr(cur, attr, None) == LOCK_NOT_AVAILABLE_SQLSTATE:
                return True
        nxt = getattr(cur, "orig", None)
        if nxt is None or nxt is cur:
            nxt = cur.__cause__
        cur = nxt
    return False


class ApplyBudget:
    """The wall clock for ONE attended apply request, started at request entry.

    Constructed by the rail's ``repair()`` entry point rather than by its write
    loop, so the plan load and the live gate query — the two slowest reads on
    the path, and both capable of blocking — are charged against the same budget
    the loop spends. The loop's own check then asks the honest question ("how
    much of the REQUEST is left") instead of a question about itself.
    """

    def __init__(self, total_s: float, *, clock=None):
        # The clock is injectable so a test can prove the bound deterministically
        # without patching the stdlib for the whole process (gotcha #44: a guard
        # whose evidence depends on the wall clock is not a guard).
        self._clock = clock or time.monotonic
        self._total = float(total_s)
        self._started = self._clock()

    @property
    def total_s(self) -> float:
        return self._total

    def elapsed_s(self) -> float:
        return self._clock() - self._started

    def remaining_s(self) -> float:
        return self._total - self.elapsed_s()

    def has_room_for_a_row(self, *, floor_s: float = MIN_ROW_BUDGET_S) -> bool:
        """Whether another row may be STARTED, not whether time is left."""
        return self.remaining_s() > floor_s

    def lock_timeout_ms(self) -> int:
        """How long the next statement may wait, clamped into the sane band."""
        remaining = self.remaining_s()
        proposed = int(max(remaining, 0.0) * 1000 * LOCK_TIMEOUT_SHARE)
        return max(LOCK_TIMEOUT_FLOOR_MS, min(LOCK_TIMEOUT_CEILING_MS, proposed))
