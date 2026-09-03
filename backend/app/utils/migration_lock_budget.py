"""Bound how long a MIGRATION waits for its lock (#2724).

WHAT A READER SAW, AND WHY IT WAS NOT SLOW CODE

On 2026-09-02 production served four endpoints that took **100 to 440 seconds**
— ``/api/predictions/resolutions`` (440s), ``/api/feed`` (377s),
``/api/tournaments/by-event/{id}`` (180s) and ``/api/futures/{market_id}``
(101s). The browser's API client aborts at 20s and retries twice, so a reader
who arrived inside one of those windows saw an **empty page** and then gave up.

Three facts name the cause between them:

1. Every one of those endpoints reads ``futures_markets``.
2. The slow rows carry ``queries=1`` and ``db_ms == max_query_ms == total_ms``.
   One statement, and it was not computing — ``EXPLAIN ANALYZE`` of the
   ``/api/predictions/resolutions`` statement on production is **12ms**.
3. They finished in a **convoy**: 440s, 419s, 397s and 377s all completed
   within one second of each other at 08:59:53.

A plain ``SELECT`` holds ``ACCESS SHARE``, which conflicts with exactly one lock
mode: ``ACCESS EXCLUSIVE``. And both stall windows sit seconds after a deploy
that carried a migration doing ``ALTER TABLE futures_markets ADD COLUMN`` —
v3994/08:51:58 (``add_image_dimensions``) and v4001/15:12:39
(``kalshi_expiration_backstop``). The deploys either side of them carried no
migration and produced no cluster.

THE MECHANISM IS THE LOCK QUEUE, NOT THE ALTER

``ALTER TABLE … ADD COLUMN`` with no volatile default is a catalogue write:
once it HAS the lock it is instant. The 440 seconds is spent waiting for it,
behind some ordinary long-lived reader or a Celery transaction.

The damage is done by what happens *while* it waits. Postgres' lock queue is
FIFO, so a pending ``ACCESS EXCLUSIVE`` blocks every ``ACCESS SHARE`` that
arrives after it. One migration waiting on one straggler therefore stops **all**
reads of that table for as long as the straggler runs, and releases the whole
pile at once when it finally commits. That is the convoy.

THE FIX IS TO STOP WAITING

``lock_timeout`` puts a ceiling on the wait. The migration either takes its lock
promptly or aborts with SQLSTATE ``55P03`` — and an aborted ``ALTER`` is not
queued, so nothing piles up behind it. The reader's worst case stops being
"until the straggler finishes" and becomes :data:`DEFAULT_LOCK_TIMEOUT_MS`.

It is set as a libpq connection option (``-c lock_timeout=…``) rather than by
executing ``SET``, so it is in force from the first statement of the migration
and cannot be undone by a rollback. A migration that genuinely needs to wait
longer overrides it for itself with ``op.execute("SET lock_timeout = '60s'")``;
that is deliberate, local, and visible in the migration's own diff.

WHY THERE IS A RETRY, AND WHY IT CHECKS THE VERSION FIRST

Bounding the wait alone would convert roughly two of 2026-09-02's twenty-one
deploys from "the site blanks for seven minutes" into "the release fails". That
is already the better trade, but it is not the finished job, so a lock-timed-out
run is retried a few times with backoff — contention this coarse is transient.

The retry is only sound while nothing has been committed, and three historical
migrations break that assumption: ``add_market_tags`` and ``add_taxonomy_tags``
issue a bare ``op.execute("COMMIT")``, and ``add_prov_play_enum_value`` uses
``autocommit_block()``. Re-running a batch that already committed part of itself
is how a retry turns a clean failure into a corrupt one.

So the retry is gated on evidence rather than on the assumption:
:func:`should_retry` demands that the recorded ``alembic_version`` be
**unchanged** since before the attempt. If any migration in the batch committed,
the version has moved, and the failure is re-raised for a human instead. A guard
written against the invariant ("nothing was committed") outlives one written
against the migrations that existed when it was written.

THE BUDGET HAS TO FIT THE RELEASE PHASE

Heroku's release phase is where this runs, and gotcha #31 already records that
it is not a place to spend minutes. :func:`max_total_wait_s` is the worst case
this policy can cost — every attempt timing out, every backoff slept — and
``tests/test_migration_lock_budget.py`` asserts it stays under
:data:`RELEASE_PHASE_BUDGET_S`. A default that quietly grew past the release
window would trade a seven-minute outage for a deploy that can never land.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable, Mapping, Optional, TypeVar

from app.utils.repair_lock_budget import is_lock_timeout

T = TypeVar("T")

#: How long a migration may wait for its lock before giving up. Five seconds is
#: far longer than an uncontended ``ALTER TABLE`` on any table here (it is a
#: catalogue write) and comfortably under the 20s at which the frontend's API
#: client aborts — so a reader who arrives during a contended migration waits,
#: at worst, a beat, instead of being shown nothing.
DEFAULT_LOCK_TIMEOUT_MS = 5_000

#: Total attempts, not retries after the first. Contention on this scale is a
#: straggler transaction finishing, so a handful of spaced attempts clears it.
DEFAULT_ATTEMPTS = 4

#: Pause between attempts. Long enough for the straggler that caused the first
#: timeout to have committed; short enough that four attempts still fit the
#: release phase.
DEFAULT_BACKOFF_MS = 2_000

#: Never wait less than this for a lock. Below a second the timeout stops
#: measuring contention and starts measuring ordinary catalogue latency, which
#: would fail healthy deploys.
LOCK_TIMEOUT_FLOOR_MS = 1_000

#: Never wait more than this, however it is configured. Twenty seconds is where
#: the frontend's API client gives up: a migration permitted to hold the lock
#: queue longer than that is, by definition, showing someone a blank page.
LOCK_TIMEOUT_CEILING_MS = 20_000

#: The whole policy — every attempt timing out and every backoff slept — must
#: fit here with room for the migrations themselves to actually run. The release
#: phase also has to import the app and stamp a version.
RELEASE_PHASE_BUDGET_S = 120.0


@dataclass(frozen=True)
class MigrationLockSettings:
    """The resolved lock policy for one migration run."""

    lock_timeout_ms: int
    attempts: int
    backoff_ms: int

    @property
    def backoff_s(self) -> float:
        return self.backoff_ms / 1000.0


def _clamp(value: int, floor: int, ceiling: int) -> int:
    return max(floor, min(ceiling, value))


def _read_int(env: Mapping[str, str], key: str, default: int) -> int:
    """Read an integer setting, falling back to ``default`` on anything unusable.

    A malformed ``ALEMBIC_LOCK_TIMEOUT_MS`` must not stop a deploy: the whole
    point of this module is that migrations keep landing. An unreadable value
    is treated as "not set", which lands on a default that is known to be safe.
    """
    raw = env.get(key)
    if raw is None:
        return default
    try:
        parsed = int(str(raw).strip())
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def resolve_settings(env: Mapping[str, str]) -> MigrationLockSettings:
    """The lock policy for this run, from the environment, always usable.

    The release-phase budget is enforced HERE rather than documented as a range
    for each knob, because the knobs multiply: clamping each of them to a
    sane-looking maximum independently still permits 10 attempts x 20s of
    waiting plus 9 x 30s of backoff, which is a release that can never land.
    Attempts are dropped until :func:`max_total_wait_s` fits, so the invariant
    holds for every combination rather than for the ones anyone thought to try.
    """
    settings = MigrationLockSettings(
        lock_timeout_ms=_clamp(
            _read_int(env, "ALEMBIC_LOCK_TIMEOUT_MS", DEFAULT_LOCK_TIMEOUT_MS),
            LOCK_TIMEOUT_FLOOR_MS,
            LOCK_TIMEOUT_CEILING_MS,
        ),
        attempts=_clamp(
            _read_int(env, "ALEMBIC_LOCK_ATTEMPTS", DEFAULT_ATTEMPTS), 1, 10
        ),
        backoff_ms=_clamp(
            _read_int(env, "ALEMBIC_LOCK_BACKOFF_MS", DEFAULT_BACKOFF_MS), 0, 30_000
        ),
    )
    return _fit_to_release_budget(settings)


def _fit_to_release_budget(
    settings: MigrationLockSettings,
) -> MigrationLockSettings:
    """Drop attempts until the worst case fits :data:`RELEASE_PHASE_BUDGET_S`.

    One attempt is always kept: the job of this module is to make migrations
    land safely, never to refuse to run them. A single attempt costs at most
    :data:`LOCK_TIMEOUT_CEILING_MS`, which fits the budget by construction.
    """
    # `>=`, not `>`: a policy that consumes the budget EXACTLY leaves nothing
    # for the migrations it exists to let run.
    while (
        settings.attempts > 1 and max_total_wait_s(settings) >= RELEASE_PHASE_BUDGET_S
    ):
        settings = MigrationLockSettings(
            lock_timeout_ms=settings.lock_timeout_ms,
            attempts=settings.attempts - 1,
            backoff_ms=settings.backoff_ms,
        )
    return settings


def lock_timeout_option(lock_timeout_ms: int) -> str:
    """The libpq ``options`` string that arms ``lock_timeout`` at connect time.

    Handed to psycopg2 via ``connect_args`` rather than executed as ``SET``, so
    it is in force for the migration's very first statement and survives the
    rollback of any transaction inside it.
    """
    return f"-c lock_timeout={int(lock_timeout_ms)}"


def max_total_wait_s(settings: MigrationLockSettings) -> float:
    """Worst case this policy can add to a release: every attempt, every sleep."""
    lock_waits = settings.attempts * (settings.lock_timeout_ms / 1000.0)
    backoffs = max(0, settings.attempts - 1) * settings.backoff_s
    return lock_waits + backoffs


def should_retry(
    exc: BaseException,
    attempt: int,
    settings: MigrationLockSettings,
    version_before: Optional[str],
    version_after: Optional[str],
) -> bool:
    """Whether a failed migration attempt may be run again.

    Every clause is a reason NOT to retry, and each one is separately load
    bearing:

    * not a lock timeout — a genuine migration bug must surface on attempt one,
      not four times over;
    * no attempts left;
    * ``alembic_version`` moved — part of the batch committed, so re-running it
      would replay committed work. See the module docstring for the three
      migrations that make this reachable.
    """
    if not is_lock_timeout(exc):
        return False
    if attempt >= settings.attempts:
        return False
    return version_before == version_after


def run_with_lock_retry(
    attempt_once: Callable[[], T],
    settings: MigrationLockSettings,
    read_version: Callable[[], Optional[str]],
    sleep: Callable[[float], None] = time.sleep,
    on_retry: Optional[Callable[[int, Optional[str]], None]] = None,
) -> T:
    """Run ``attempt_once``, retrying only a lock timeout that committed nothing.

    ``read_version`` must open its OWN connection: it is called after a failure,
    when the migration's connection is in an aborted transaction and cannot
    answer a query. It returns ``None`` when the version cannot be read, and
    ``None == None`` is deliberately treated as "unchanged" — a database with no
    ``alembic_version`` row yet has, by definition, committed no migration.
    """
    last_error: BaseException | None = None
    for attempt in range(1, settings.attempts + 1):
        version_before = read_version()
        try:
            return attempt_once()
        except BaseException as exc:  # noqa: BLE001 - re-raised unless retryable
            last_error = exc
            version_after = read_version()
            if not should_retry(exc, attempt, settings, version_before, version_after):
                raise
            if on_retry is not None:
                on_retry(attempt, version_after)
            sleep(settings.backoff_s)

    # Unreachable: the loop either returns or re-raises on its final attempt.
    raise last_error  # type: ignore[misc]
