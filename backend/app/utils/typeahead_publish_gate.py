"""The publish-side gate for `warm-typeahead`, as a pure decision — NOT WIRED.

LAT-P073 (#1609, #1866). Fable's LAT-P073 item 2: *"is_due() publish-side gate:
bring me the PLAN — it lives inside gotcha #39's blast radius (beat scheduling
loop), so it ships only through pre-cert with a kill-switch and a registered halt
on cache-entry loss."*

**Nothing in this module runs in production.** It is imported by its test suite and
by nothing else, deliberately. It is the *pre-cert artifact*: the decision the
`celery.schedules.schedule` subclass will make, extracted from the scheduler so it
can be exhaustively tested and mutated without a beat process, a broker, or a Redis.
The wiring — the subclass, the Redis read, the beat-schedule edit — is specified in
`docs/audits/latency/lat-p073-publish-gate-plan.md` and is a separate change with
its own `beat_schedule_change: true`.

The split is the point. The hazard Fable named is that `is_due()` runs inside the
beat process's scheduling loop, so a fault there freezes **every beat in the
system** — gotcha #39 one level above where that gotcha was written. The only part
of the eventual subclass that can carry a policy bug is the decision; the only part
that can carry a #39 bug is the I/O. Separating them means the decision can be
certified to exhaustion here, and the I/O reviewed as five lines that do nothing but
fetch a number and hand it in.

## Why a publish-side gate at all, and why not the beat interval

LAT-P072 refused the beat cut (10 s -> 60 s): the beat interval is also the
quantiser of the warmer's pass period, `P(B) = B * ceil(max(wall, 30) / B)`, and at
B = 60 the quantiser is coarser than the entire measured wall distribution, so the
period lands at 60 s against a measured **45 s** cliff on every reachable wall. See
`typeahead_beat_budget.py`; do not re-derive it, and do not re-propose 60 s.

A publish-side gate cuts messages **without touching the firing opportunity**, so
the period — and therefore the cliff margin — are untouched by construction. That is
the entire reason this shape was chosen over every other lever.

## The correctness argument, in full, because the whole design rests on it

`_warm_typeahead` admits a pass only after two gates, in this order
(`tasks/typeahead_warmer.py`): it acquires `_LOCK_KEY`, and then — **under the
lock** — it requires `now - last_pass_start >= MIN_PASS_PERIOD_SECONDS` (30 s),
releasing the lock and returning `_no_work("min_period")` if not.

So a fire whose `last_pass_start` age is below the floor **cannot** start a pass. It
is guaranteed to be a no-op. Suppressing it at publish time therefore removes a
message that would have done nothing, and removes no opportunity at all.

⚠️ **The one place that argument needs care is the publish-to-consume delay.** The
beat reads the age at publish time; the worker re-reads it at execution time, which
is later, so the worker's age is always **larger**. A fire the beat sees at age 25 s
could be executed at age 31 s and legitimately start a pass. Suppressing it would
then cost a real opportunity, and one lost opportunity is +1 beat interval on the
period — which at today's 50 s period would push it to 60 s, over the cliff.

That case is bounded and, in the measured regime, empty:

* A lost opportunity requires the previous pass to have **finished** before the
  floor cleared, i.e. a wall shorter than 30 s. The measured wall distribution is
  29.4-44.6 s, so this is the extreme tail at worst.
* When the wall does clear under 30 s, the floor binds instead of the lock, and the
  period is 30 s -> the worst case with the gate is one interval later, 40 s. Still
  **under** the 45 s cliff. So even in the regime where the gate can cost an
  opportunity, it cannot cross the cliff.
* When the wall exceeds 30 s — which is every measured pass — the lock is still held
  throughout the suppression window, so the suppressed fires were lock-gated no-ops
  regardless of the floor, and nothing is lost even in principle.

**The lock is deliberately NOT consulted.** A gate that also suppressed while
`_LOCK_KEY` was held would remove ~80 % of messages instead of ~40 %, and it is
refused for the same reason 60 s was: the lock can be released between the beat's
read and the worker's, so suppressing on it costs an opportunity in the *ordinary*
regime, not the tail — +10 s on a 50 s period is 60 s, over the cliff. The
aggressive version is arithmetically attractive and unsafe; this is the version that
survives its own measurement.

## What this is worth, measured 2026-08-19T23:30Z rather than assumed

The queue staged this against "~82 % no-ops". **That figure is stale and this module
does not use it.** Production says:

* `warm_typeahead` executes **2.41/min** against a nominal 6.00/min publish rate
  (858 deliveries in 21,322 s; `deliveries` is wired to `task_prerun`, so it counts
  executions, not publishes).
* The shortfall is **`expires`**, not the scheduler. The set of beats reading
  `ratio < 0.6` is *exactly* the set carrying `expires` — 4 of 4, both directions,
  across 72 rate-armed entries, replicated on two independent reads. Every
  non-expiring beat reads 0.99-1.00, including `poll_live_prediction_markets` whose
  p95 (81.6 s) is longer than `warm_typeahead`'s (44.6 s). The background queue was
  0-2 deep throughout, so it is not list backlog.

So the honest payoff is **not** "82 % fewer no-op executions". It is: the beat stops
publishing ~40 % of its messages into a prefetch buffer that will discard them
unexecuted, which is queue occupancy spent on nothing. The registered prediction in
the plan doc is written against those numbers, not the stale ones.

## ⚠️⚠️ LAT-P075 — STILL NOT WIRED, AND THE PAYOFF ABOVE IS NOW STALE TOO

Fable's LAT-P075 directive said to wire this gate **if** the pass-result endpoint had
been deployed. It has been (`6e314028`, via INT-092). It was **still not wired**, for
three reasons, and the first two are new facts rather than caution:

1. **Step 2 of the forced ordering — "count publishes" — is UNREACHABLE, and deployment
   was never what was blocking it.** No instrument in the fleet counts publishes.
   `deliveries` is wired to celery's `task_prerun` (`tasks/redis_state.py`, and see
   LAT-P043/#1802 in the same file), so it counts **executions**; `queue_depths` is an
   `LLEN` and is blind to messages that are consumed as fast as they arrive; and
   `/api/admin/celery-debug` is refused by standing guidance. The endpoint shipping did
   not change this, because the endpoint reports **passes and skips** — also executions.

2. **The payoff quantity above was DELETED by a change in the same window.**
   `_EXPIRING_WARMER_BEATS["warm-typeahead"]` went 10 -> 120 (LAT-P075, see
   `typeahead_beat_budget.derive_message_expiry_s`). Nothing is discarded unexecuted any
   more. So "~40 % of publishes thrown away in the prefetch buffer" is no longer a cost
   this gate can remove — those messages now **execute**, as lock skips measured at
   <= 71 ms. The gate's remaining payoff is ~3 suppressed no-op executions per period,
   about **90 ms of worker-slot time per period, ~0.2 % of one slot.**

   That is a very small return for what this module's own docstring calls the hazard:
   `is_due()` runs inside the beat process's scheduling loop, so a fault there freezes
   **every beat in the system**. It is the highest-blast-radius change in the program.

3. **It does not address the headline.** This module says so at the top, by construction:
   a publish-side gate leaves the firing opportunity, and therefore the period, exactly
   as it is. The period regression's cause is `--concurrency=2` on `worker-background`
   shared by 57 beats — see `typeahead_beat_budget.background_slot_occupancy()`.

**What would make wiring it worth doing:** a re-derivation of the payoff against
post-deploy data, on the regime that actually exists after the expiry fix. If the
answer stays around 0.2 % of a slot, the correct outcome is to **delete this module
rather than wire it** — a certified artifact whose payoff has evaporated is not an asset,
and leaving it here invites a future window to wire it on the numbers above.

## What is deliberately NOT decided here

Reading Redis, choosing a client, bounding a socket, the kill-switch transport, and
the `next_check` contract with celery's beat loop are all *wiring*, and all live in
the plan doc. This module takes an age that somebody else fetched and returns a
verdict about it. It cannot hang, it cannot block, and it has no imports beyond the
standard library — which is the property that makes the eventual `is_due()` reviewable.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil
from typing import Optional

# ---------------------------------------------------------------------------
# Mirrored constants, pinned against their real definitions by
# `tests/test_typeahead_publish_gate.py`. Mirrored rather than imported for the
# same reason `typeahead_beat_budget.py` mirrors: this module must be importable
# without dragging `tasks/typeahead_warmer` (and therefore the whole task graph)
# into the beat process's import path at scheduling time.
#
# A drifted mirror is a RED TEST, never a silently wrong gate.
# ---------------------------------------------------------------------------

#: The warmer's floor on how often a pass may START. Mirrored from
#: `tasks/typeahead_warmer.MIN_PASS_PERIOD_SECONDS`. This is the ONLY quantity
#: the gate suppresses on: below it, the task's own gate guarantees a no-op.
MIN_PASS_PERIOD_S = 30.0

#: The beat interval in force. Mirrored from the `warm-typeahead` entry in
#: `tasks/__init__.py`. The gate does not change it — that is the whole design.
BEAT_INTERVAL_S = 10.0


def _fuse_limit(floor_s: float = MIN_PASS_PERIOD_S, beat_s: float = BEAT_INTERVAL_S) -> int:
    """How many consecutive suppressions can be legitimate. Derived, not chosen.

    A legitimate suppression run lasts exactly as long as the floor: it starts at
    the fire after a pass began and ends when the age reaches `floor_s`. At a beat
    of `beat_s` that is `ceil(floor_s / beat_s)` fires — 3 today. One more than
    that is not a floor, it is a stuck input, and the fuse publishes through it.

    This matters more than it looks. Fail-open covers Redis *erroring*; it does
    not cover Redis cheerfully returning a value that never ages — a future-dated
    stamp from a clock-skewed dyno, a key some other process keeps rewriting. In
    that state every individual decision is locally correct and the warmer stops
    forever, which on the adherence surface is indistinguishable from a quiet
    period. The fuse is the only guard that catches the *sequence* rather than the
    decision, and it costs nothing when things are healthy because a healthy run
    never reaches it.
    """
    return max(1, ceil(floor_s / beat_s))


#: Publish unconditionally after this many consecutive suppressions.
FUSE_MAX_CONSECUTIVE_SUPPRESSIONS = _fuse_limit()


class GateReason:
    """Why the gate decided what it decided. Every reason is reachable and tested.

    Named constants rather than free strings because these become log lines and
    metric labels in the wired version, and a reason nobody can grep for is a
    decision nobody can audit (ruling 074).
    """

    #: Kill switch is off. The gate is inert and every fire publishes.
    DISABLED = "gate_disabled"
    #: The age could not be established. FAIL OPEN — see `should_publish`.
    AGE_UNKNOWN = "age_unknown"
    #: The consecutive-suppression fuse blew. Publish regardless of the age.
    FUSE = "fuse_blown"
    #: The floor has cleared, so this fire could legitimately start a pass.
    FLOOR_CLEAR = "floor_clear"
    #: Below the floor. The task's own gate guarantees this fire would no-op.
    FLOOR_NOT_CLEAR = "floor_not_clear"


@dataclass(frozen=True)
class GateDecision:
    """One decision, with its workings.

    `next_check_s` is advice to the beat loop, never a promise the loop must keep;
    the wired `is_due()` caps it (see `should_publish`) so the gate can never
    lengthen the firing opportunity it exists to protect.
    """

    publish: bool
    reason: str
    next_check_s: float
    #: Consecutive suppressions AFTER this decision — the caller carries it forward.
    consecutive_suppressions: int

    @property
    def suppressed(self) -> bool:
        return not self.publish


def should_publish(
    *,
    age_since_last_pass_s: Optional[float],
    consecutive_suppressions: int = 0,
    enabled: bool = True,
    floor_s: float = MIN_PASS_PERIOD_S,
    beat_s: float = BEAT_INTERVAL_S,
    fuse: Optional[int] = None,
) -> GateDecision:
    """Decide whether this beat fire should publish. Pure; never raises on input.

    ``age_since_last_pass_s`` is seconds since the last pass STARTED, or ``None``
    when that is not knowable. ``None`` is not a number this function treats
    generously — it is the **only** signal that says "do not suppress", and every
    upstream failure is required to arrive as ``None`` rather than as a plausible
    number. The warmer's own `_seconds_since_last_pass` already collapses Redis
    errors, a missing key, an unparseable value and a negative delta to ``None``
    for exactly this reason; the wiring must do the same.

    **FAIL OPEN is the load-bearing property and it is asserted in both
    directions.** A Redis that does not answer must publish. A gate that failed
    closed would silently stop the warmer, which looks — on every instrument this
    program has — identical to a healthy quiet period, and the cost of an empty
    typeahead head is #1866's own number: a MISS is 1.16-2.29 s p50 against a
    <150 ms budget. Suppressing wrongly is expensive and invisible; publishing
    wrongly costs one 10 ms no-op.

    Order matters and is deliberate: the kill switch outranks everything (it must
    work even when the age is garbage), then fail-open, then the fuse, then the
    floor. The fuse sits above the floor so a permanently-fresh age cannot outvote
    it.
    """
    limit = _fuse_limit(floor_s, beat_s) if fuse is None else max(1, int(fuse))
    # Never advertise a check further out than one beat. Returning a long
    # `next_check` is hazard 3 from the queue: it starves the 10 s firing
    # opportunity that this whole design exists to preserve, and it would do so
    # while every individual decision still looked correct.
    beat_cap = max(0.1, float(beat_s))

    def _publish(reason: str) -> GateDecision:
        return GateDecision(True, reason, beat_cap, 0)

    if not enabled:
        return _publish(GateReason.DISABLED)

    if age_since_last_pass_s is None:
        return _publish(GateReason.AGE_UNKNOWN)

    if consecutive_suppressions >= limit:
        return _publish(GateReason.FUSE)

    if age_since_last_pass_s >= floor_s:
        return _publish(GateReason.FLOOR_CLEAR)

    remaining = float(floor_s) - float(age_since_last_pass_s)
    return GateDecision(
        publish=False,
        reason=GateReason.FLOOR_NOT_CLEAR,
        next_check_s=max(0.1, min(beat_cap, remaining)),
        consecutive_suppressions=consecutive_suppressions + 1,
    )


def suppressed_fires_per_period(
    period_s: float, floor_s: float = MIN_PASS_PERIOD_S, beat_s: float = BEAT_INTERVAL_S
) -> int:
    """How many fires in one pass period the gate removes. The payoff, derived.

    Fires land at `beat_s, 2*beat_s, ...` after a pass start. A fire is suppressed
    when its age is strictly below the floor, so the count is the number of beat
    multiples in the open interval `(0, floor_s)` — and only those that actually
    occur within the period.
    """
    if period_s <= 0 or beat_s <= 0 or floor_s <= 0:
        raise ValueError("period, beat and floor must all be positive")
    fires = int(period_s // beat_s)
    return sum(1 for k in range(1, fires + 1) if k * beat_s < floor_s)


def predicted_publish_cut(
    period_s: float, floor_s: float = MIN_PASS_PERIOD_S, beat_s: float = BEAT_INTERVAL_S
) -> float:
    """Fraction of published messages the gate removes at a given pass period.

    Reported as a fraction of *publishes*, never of executions. The two differ by
    the `expires` discard measured at 2026-08-19T23:30Z (executions are ~40 % of
    publishes), and conflating them is how the stale "82 % of fires are no-ops"
    figure came to be staged as this gate's payoff.
    """
    fires = int(period_s // beat_s)
    if fires <= 0:
        return 0.0
    return suppressed_fires_per_period(period_s, floor_s, beat_s) / fires
