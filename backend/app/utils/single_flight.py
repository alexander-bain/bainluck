"""One copy at a time: a Redis in-flight lease for beat tasks that lap (#3251).

A Celery beat entry publishes on a fixed period whether or not the previous
delivery has finished. When a task's duration exceeds its own interval it
**laps**: every tick adds a copy the worker will eventually have to run, and the
queue grows without bound. Measured on production 2026-09-05, `realtime` was
282 → 349 deep with **85 copies of `poll_all_odds`** queued against
`worker-realtime --concurrency=4`.

(That filing quoted the lap ratio as p95 ÷ interval = 3.94×. That framing is
wrong and is corrected under "WHY THIS IS ENOUGH" below: slot demand is
**mean** ÷ interval = 2.37×. The defect was real either way, but p95 misranks
the offenders — `warm_typeahead` looks like the second-worst lapper at 2.88×
p95 while actually holding 0.30 slots, because it is a fast task with a long
tail.)

The casualty was not odds polling — it was everything else sharing the queue.
`prewarm_live_feed_shapes`, the 40 s rail that is the only thing that can hold a
live-containing feed shape warm, carries `expires=40`, so once the queue's
service latency passed 40 s **every one of its messages was discarded on
arrival** — no start, no failure, `health: healthy`, and a front page costing
13.3 s cold instead of 0.2 s. (See `docs/gotchas-reference.md` and #3251: never
"fix" that by raising `expires`; the bound is correct. Fix the producers.)

So: before a lapping task does its work it takes a lease. If a previous copy
still holds it, this delivery logs one line and returns a `skipped` summary in
microseconds, and the queue cannot form a line.

**That stops the queue growing. It did NOT get the rail its slot back** — the
capped slot demand still exceeds the worker pool once every leased task is
counted, so no free slot appears inside the rail's 40 s `expires`. Measured, not
predicted: see "THERE IS NO MARGIN" and the warm-rail note below. The remaining
lever is capacity, and it is #3268, not this module.

Four properties this has to have, and how each is obtained:

* **A skip is not a failure.** The tick returns a summary; nothing raises,
  nothing retries, no price is cleared or aged out. A skipped tick performs no
  writes at all.
* **A crashed holder must not hold forever.** The lease carries a TTL, so a
  child SIGKILLed past its `finally` (gotcha: a hard kill reaches no handler)
  releases by expiry.
* **A slow holder must not release somebody else's lease.** The lease is a
  unique token and release is a compare-and-delete, exactly as
  `app/utils/event_concept_cache.py` does it: an unconditional `delete` in a
  `finally` is how #1678 admitted a third concurrent builder. A holder whose
  lease already expired deletes nothing.
* **Redis being down must not stop ingestion.** Acquisition FAILS OPEN — if the
  lease cannot be taken *or refused*, the work runs. Losing the guard degrades
  us to today's behaviour; letting the guard become a second outage would be
  worse than the one it repairs.

WHY THIS BOUNDS THE QUEUE BUT NOT THE WORK — and the arithmetic that says so
-----------------------------------------------------------------------------

A lease bounds the QUEUE, not the WORK. A pass longer than its own interval
still holds ONE FULL worker slot continuously; the lease only stops the surplus
deliveries from *piling up* behind it. The number to compute is
``sum(min(1, mean / interval))`` — **mean**, not p95: a slot is occupied for the
mean duration, and ranking by p95 misreads which task is actually the hog.
(Credit: latency/167, #3251. Measured on production 2026-09-05, 50-run duration
rings via `/api/admin/task-metrics`. Gotcha: that endpoint is keyed by the
`_tracked_run` LABEL, not the task name — `?task=poll_all_odds` says `no_data`,
`?task=poll_odds` returns the ring; `poll_live_prediction_markets` is
`prediction_market_live`.)

    label                      mean    interval   demand   capped
    poll_odds                  71.0s     30s       2.37     1.00
    prediction_market_live    191.3s    120s       1.59     1.00   ← leased
    espn_sync                  77.0s     60s       1.28     1.00
    datagolf_inplay            76.9s     90s       0.85     0.85
    prewarm_live_feed_shapes   19.7s     40s       0.49     0.49
    transition_statuses         7.7s     60s       0.13     0.13
    statpal_livescores          2.2s     30s       0.07     0.07
    statpal_plays / mlb_sync     —         —        0.01     0.01
                                                  -----    -----
                                                   6.80     4.56   vs concurrency=4

⚠️ THERE IS NO MARGIN. An earlier revision of this table omitted
`prediction_market_live` — the fourth leased task, and the second-largest single
consumer — and concluded "capped 3.56, a margin of 0.44 slots (11%), which is
thin". That was wrong in direction, not just magnitude: the correct capped sum is
**4.56 against 4 workers, a DEFICIT of 0.56 slots**. (Caught as CERT-1944's named
follow-up; the 4.56 independently reproduces latency/169's separately-measured
4.56, by a different route.) Never quote the 3.56.

Which makes the honest claim narrower than "this fixes the queue":

* **The queue drains anyway, and that is not a contradiction.** A declined
  delivery costs microseconds, so the backlog is *shed* cheaply even while all
  four workers stay saturated with real passes. Depth falling is the lease
  working; it is NOT evidence of spare capacity.
* **Real work still laps.** At 4.56 capped demand the four leased tasks run
  essentially back-to-back with no idle, which is why `poll_all_odds` accrues a
  decline on very nearly every tick.
* **So an unleased task can still starve.** `prewarm_live_feed_shapes` is not
  leased: its message waits for a genuinely free slot, and at a 0.56-slot deficit
  there is never one inside its 40 s `expires`. See the warm-rail note below —
  this is measured, not inferred.

The remaining lever is capacity (`--concurrency` on `worker-realtime`, against
the SQLAlchemy pool `pool_size=3, max_overflow=2`), not another lease: the two
unleased producers left, `warm_search_head` and `warm_typeahead`, are ~0.30 slots
each and cannot close a 0.56 gap. That ask is with Alex via latency/169–170.
Re-run this sum before adding anything to `realtime`, and include every leased
task when you do.

Observed after deploy (`a705abcc`, production 19:03Z): the pre-ship trend was
**+1.7/min sustained for hours** (454 → 796); after the ship the derivative
flipped sign and `realtime` fell 631 → 362 between 18:41Z and 19:48:40Z, a
measured **−4.0/min**, still falling at the last read. The derivative flipping
sign is the proof, not any single depth.

⚠️ DO NOT QUOTE THE FIRST DRAIN RATE. The initial post-deploy read looked like
**−11.9/min** and was briefly used to predict a ~70-minute clear. It is an
artifact and was retracted by the measuring lane (latency/168): a worker restart
dumps the messages already past their 40 s `expires` in one burst, so the first
minutes measure *discard*, not *drain*. A rate taken across a restart boundary
is not this guard's effect. The −4.0/min above is taken after that burst
settled. (A later "plateau at ~625, publication and consumption balanced" read
over a 25-minute window did not hold either — the queue kept draining to 362.
Sample longer than the thing you are trying to see.)

The instrument for this guard is NOT queue depth — depth moves for reasons that
have nothing to do with us. It is the skip counters, which count declines
directly: `bainluck:inflight:skipped:*`, read one key at a time via
``/api/admin/redis-read?key=bainluck:inflight:skipped:app.tasks.<task>``. Live
at 19:48:40Z: **266 / 52 / 31 / 17** for the four leased tasks (153 / 27 / 17 / 7
at 19:17Z). `poll_all_odds` accrues ~2.0 declines/min against a 30 s beat —
i.e. essentially every tick declines, which is what a 71 s mean pass on a 30 s
interval must look like when the guard is working.

Note `schedule-adherence` reports `self_gated_fires: null` for all four leased
tasks and always will: that field is withheld unless two counters' windows agree
within `SELF_GATE_WINDOW_TOLERANCE`, and it is *not* wired to this counter. Do
not read its `null` as "the lease never fired" — read the Redis counters above.

⚠️ A DRAINED QUEUE IS NOT A WARM FRONT PAGE — and this is now measured, not
predicted. At 19:48:40Z, with the queue down to 362 and skips firing,
`prewarm_live_feed_shapes` had **still not started once since 14:08:48Z** — 5h40m
dead on a 40 s beat, 5h20m of that with a lease in place. Freeing slots did not
revive it. Its messages carry `expires=40`, so it stays dark until service
latency is under 40 s, which draining to 362 did not achieve; and even when it
does run it spends mean 19.7s / p50 20.1 / max 20.2 against
`FEED_LIVE_REPUBLISH_BUDGET_S = 20`, so 49 of 50 runs cut off AT the budget —
a ceiling, not a measurement — and its last result was `0`. This ship does not
fix the cold front page. That is #3268; never read one claim as the other.

Trade-off, stated rather than hidden: the TTL is sized off the runtime's
*guaranteed* bound (`task_time_limit`), not off a measured p95 or max, because a
measured number rots and an enforced one cannot. The two errors are NOT
symmetric, which is the whole reason for the choice:

* **Too short** — the lease lapses mid-pass and a second copy starts while the
  first is still running. Both call The Odds API and bill the 5M/month quota
  twice for the same tick. Duplicate spend on the most constrained resource in
  the system, and it is silent.
* **Too long** — a hard-killed holder stalls its own task until the TTL expires.
  Bounded, self-correcting, and visible in the skip counter.

So the bound that cannot be undershot is the one we use. Concretely: a
198 s TTL (max-measured × 1.5, sized off latency/167's 131.8 s max) was
considered and REJECTED — the very next 50-run ring showed a 234.8 s pass, which
that TTL would have undershot, admitting exactly the double-billing above.

The residual cost is real and worth knowing: a clean Celery warm shutdown
unwinds the `with` and releases, so only a SIGKILL reaches the bad case — but
Heroku cycles workers on every master merge, and a 71 s mean pass will not
finish inside the 30 s grace, so it IS reachable. A kill at the 300 s limit
leaves only 30 s of dark; a kill 30 s into a pass leaves ~300 s. Releasing held
leases from a `worker_shutting_down` handler would close it; not done here
because it is new scope on a merged ship (filed rather than smuggled in).
"""

from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from dataclasses import dataclass
from uuid import uuid4

logger = logging.getLogger(__name__)

#: Every lease key lives under this prefix, so `/api/admin/redis-read` can read
#: one by name and the whole set is greppable in Redis.
LEASE_KEY_PREFIX = "bainluck:inflight:"

#: Skip counters, one per task, under the same prefix. Diagnostic only — this is
#: how production proves the guard actually fired without needing dyno logs.
SKIP_COUNTER_PREFIX = "bainluck:inflight:skipped:"

#: 24 h window on the skip counters. They are evidence, not state; nothing reads
#: them to make a decision.
SKIP_COUNTER_TTL_SECONDS = 86400

#: Celery's global hard kill bound (`task_time_limit` in `app/tasks/__init__.py`).
#: A task that reaches it is SIGKILLed, so no un-overridden task can still be
#: running past this point. Mirrored here rather than imported because
#: `app.tasks` imports this module's consumers; `tests/test_single_flight_lease.py`
#: asserts the two are equal, so they cannot drift.
CELERY_HARD_TASK_TIME_LIMIT_SECONDS = 300

#: Headroom over the kill bound: the SIGKILL lands *at* the limit, and the lease
#: must still be held when it does.
LEASE_TTL_MARGIN_SECONDS = 30

#: 300 + 30. Both terms are declared above; neither is a literal chosen to make
#: the arithmetic come out.
DEFAULT_LEASE_TTL_SECONDS = (
    CELERY_HARD_TASK_TIME_LIMIT_SECONDS + LEASE_TTL_MARGIN_SECONDS
)

#: Compare-and-delete. Releasing without proving ownership is the #1678 defect.
#:
#: 🔴 PUBLIC BECAUSE IT IS THE THIRD CALLER THAT MAKES A COPY A CLASS (CERT-2114).
#: `app/utils/event_concept_cache.py` already carries a byte-identical copy, and
#: `app/tasks/search_head_warmer.py` needed a third when its run lock became an
#: owned-token lock. A release that proves ownership is the ONLY correct release
#: in this repo — an unconditional `DEL` is how #1678 admitted a third concurrent
#: builder and how CERT-2114 found a walled release able to delete a successor's
#: lock — so the script is named once and imported, never retyped. Nothing about
#: it is specific to in-flight leases.
RELEASE_IF_OWNER_LUA = """
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('del', KEYS[1])
end
return 0
"""

#: The historical private name, kept so this module's own call sites and their
#: tests do not move in a commit that is about a different module.
_RELEASE_IF_OWNER_LUA = RELEASE_IF_OWNER_LUA


@dataclass(frozen=True)
class Lease:
    """The outcome of one attempt to take a task's in-flight lease.

    ``acquired`` is the only thing a caller must branch on. ``reason`` says WHY,
    and the three values are meaningfully different to an operator:

    * ``"acquired"``    — we hold it; nobody else is running.
    * ``"already_running"`` — refused; a previous copy is still in flight.
    * ``"redis_unavailable"`` — we could not ask. ``acquired`` is True (fail
      open) and ``token`` is None, so release is a no-op.
    """

    task: str
    key: str
    token: str | None
    acquired: bool
    reason: str

    def skipped_result(self) -> dict:
        """The summary a declining tick returns. Never a failure shape.

        Deliberately carries ``skipped: True`` and no ``terminal``/``status``
        key, so `app.utils.task_verdict` classifies it as a non-authoritative
        UNKNOWN if it ever reaches the verdict contract — a declined tick is not
        an incomplete run and must never move a health counter.
        """
        return {
            "skipped": True,
            "reason": self.reason,
            "task": self.task,
            "lease_key": self.key,
        }


def lease_key(task: str) -> str:
    return f"{LEASE_KEY_PREFIX}{task}"


def skip_counter_key(task: str) -> str:
    return f"{SKIP_COUNTER_PREFIX}{task}"


def _client():
    """The bounded shared client, or None.

    Gotcha #39: a sync Redis client with no socket timeout can freeze an async
    task, so this must route through `get_redis_client()` and never hand-roll
    one. Imported lazily — `app.tasks.redis_state` pulls in Celery config, and
    this module is imported from task bodies.
    """
    try:
        from app.tasks.redis_state import get_redis_client

        return get_redis_client()
    except Exception:  # noqa: BLE001 — a lease must never be why a task cannot start
        return None


def acquire(
    task: str, ttl_seconds: int = DEFAULT_LEASE_TTL_SECONDS, rc=None
) -> Lease:
    """Take ``task``'s in-flight lease, or report that somebody else holds it.

    Fails OPEN: any Redis problem yields ``acquired=True, token=None``.

    ``rc`` lets the caller supply the client so one lease costs one client, not
    two: `get_redis_client()` builds a fresh client and pool per call, and these
    tasks fire every 30–120 s.
    """
    key = lease_key(task)
    client = rc if rc is not None else _client()
    if client is None:
        return Lease(task, key, None, True, "redis_unavailable")

    token = f"{uuid4().hex}:{int(time.time())}"
    try:
        if client.set(key, token, nx=True, ex=ttl_seconds):
            return Lease(task, key, token, True, "acquired")
    except Exception as exc:  # noqa: BLE001 — see docstring: fail open
        logger.warning("single_flight: could not acquire %s (%s); running anyway", key, exc)
        return Lease(task, key, None, True, "redis_unavailable")

    # redis-py answers None for a refused NX. That is a refusal, not an error.
    _record_skip(client, task)
    return Lease(task, key, None, False, "already_running")


def release(lease: Lease, rc=None) -> bool:
    """Release ``lease`` iff it still owns the key. True when it removed it.

    Fails CLOSED. If the compare-and-delete cannot run, the lease is LEFT to
    expire on its TTL: the cost is one delayed tick, whereas deleting on a
    failed check hands the key to a second concurrent copy.
    """
    if not lease.acquired or not lease.token:
        return False
    client = rc if rc is not None else _client()
    if client is None:
        return False
    try:
        return bool(client.eval(_RELEASE_IF_OWNER_LUA, 1, lease.key, lease.token))
    except Exception:  # noqa: BLE001
        logger.warning(
            "single_flight: could not release %s; leaving it to expire", lease.key
        )
        return False


def _record_skip(rc, task: str) -> None:
    """Count this decline in a 24 h window. Best-effort; never raises.

    The counter exists because a skip is otherwise invisible: it records no
    start (`record_task_started` is inside `_tracked_run`, which a declining
    tick never reaches — deliberately, so millisecond skips cannot deflate the
    duration histogram that `schedule-adherence` reads to detect the very
    overrun this guard answers). Read it with
    ``/api/admin/redis-read?key=bainluck:inflight:skipped:<task>``.
    """
    try:
        key = skip_counter_key(task)
        pipe = rc.pipeline()
        pipe.set(key, 0, nx=True, ex=SKIP_COUNTER_TTL_SECONDS)
        pipe.incr(key)
        pipe.execute()
    except Exception:  # noqa: BLE001
        pass


@contextmanager
def single_flight(task: str, ttl_seconds: int = DEFAULT_LEASE_TTL_SECONDS):
    """Yield a :class:`Lease` for ``task``, releasing it on the way out.

    Usage in a task body — the decline path returns before `_tracked_run`, so a
    skipped tick records no start and no duration::

        with single_flight("app.tasks.sync_espn_live_events") as lease:
            if not lease.acquired:
                return lease.skipped_result()
            return _tracked_run("espn_sync", _sync_espn_live_events())

    The release is in a ``finally``, so it also runs when the body raises — a
    task that dies still frees its lease immediately, and one that is hard
    killed frees it by TTL.
    """
    rc = _client()
    lease = acquire(task, ttl_seconds=ttl_seconds, rc=rc)
    if not lease.acquired:
        logger.info(
            "single_flight: %s skipped — previous run still in flight (%s)",
            task,
            lease.key,
        )
    try:
        yield lease
    finally:
        # The same client, reused across a pass that can run for minutes. Safe
        # because `get_redis_client()` sets `health_check_interval=25`, so a
        # connection Heroku Redis idle-reaped is PINGed and recycled rather than
        # failing its next use with a TLS handshake error (#1197) — and if it
        # fails anyway, `release` leaves the lease to its TTL rather than
        # deleting blind.
        release(lease, rc=rc)
