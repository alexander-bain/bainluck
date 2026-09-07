#!/usr/bin/env python3
"""latency/182 — CERT-2053's NAMED REGRESSION, built, run, and NOT shipped.

CERT-2053 asked, by name, for: "simulate the real 02:08 compaction plus 02:10
four-job arrival set on two slots with the 10s warmer cadence/120s expiry and
require every warmer fire to start before expiry; fail this SHA."

This is that simulator. It is an ARTIFACT and not a guard, and the reason is the
whole point of the exercise — read `RESULT` at the bottom before reusing it.

Run from `backend/`:  python3 ../artifacts/latency-182/cert-2053-named-regression.py
"""
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, ".")
os.environ.setdefault("DATABASE_URL", "postgresql://x/x")

from app.tasks import celery_app
from app.utils.schedule_adherence import (
    beat_queues, crontab_fire_times, effective_hold_s, warmer_expiry_budget_s,
)

#: The warmer's own self-gate, from `app/tasks/typeahead_warmer.py`. Without it
#: the simulation is simply wrong: the beat fires every 10s but the task declines
#: to start within 30s of its own last start, and declines again while a previous
#: pass holds the lock. Production counted 85,293 such declines
#: ({lock: 40,514, min_period: 44,779}) against a handful of real passes. A
#: simulator that treats all 180 fires in half an hour as work to be scheduled is
#: modelling a task that does not exist.
MIN_PASS_PERIOD_SECONDS = 30

def simulate(beat_schedule, soft_limits, queues, *, start,
                               minutes, slots, global_hard_limit=None,
                               warmer_beat="warm-typeahead", queue="background",
                               warmer_slots=None):
    """Run the pool forward and count warmer fires that expire before a slot frees.

    CERT-2053 named this scenario and asked for it by name: the real 02:08Z
    compaction start against the 02:10Z arrival cluster, on two slots, with the
    warmer's 10s cadence and 120s expiry, requiring every warmer fire to start
    before it expires. This is that, built as a general simulator over the LIVE
    schedule rather than as a transcription of one morning — the same discipline
    as every other check in this module, and for the same reason: a transcribed
    scenario passes forever after someone edits the beat it was copied from.

    Model, stated so it can be argued with:

    *   every beat on ``queue`` contributes its enumerated fires in the window,
        each occupying one slot for its DECLARED hold (soft limit, else the
        global hard limit);
    *   ``slots`` workers, FIFO, no priority — celery's actual dispatch;
    *   the warmer fires on its own beat cadence and each message carries its
        ``expires`` budget. A message still waiting when its budget elapses is
        DISCARDED UNSTARTED, which is the mechanism the whole ship is about: the
        pass does not run late, it does not run at all, and nothing errors.

    ``warmer_slots``, when given, runs the warmer against a SEPARATE pool of that
    size — the dedicated-worker purchase, priced executably rather than argued.

    ⚠️ DECLARED HOLDS, NOT MEASURED ONES, and this overstates residency. It is
    the right model for a GUARANTEE ("is a slot certain to be free inside the
    budget?") and the wrong one for an expectation. Anyone costing the purchase
    should read measured occupancy; see the disclosure on
    :func:`queues_that_cannot_guarantee_a_slot`.

    Returns ``{"fires", "started", "expired", "worst_wait_s", "p50_wait_s",
    "unenumerable"}``. ``expired > 0`` is the defect reproducing.
    """
    from datetime import timedelta

    end = start + timedelta(minutes=minutes)
    budget = warmer_expiry_budget_s(beat_schedule, warmer_beat)

    warmer_entry = (beat_schedule or {})[warmer_beat]
    warmer_task = warmer_entry.get("task")
    warmer_hold = effective_hold_s(soft_limits.get(warmer_task), global_hard_limit) or 0.0

    unenumerable, arrivals = [], []
    for name, entry in (beat_schedule or {}).items():
        task = entry.get("task")
        if not task or name == warmer_beat:
            continue
        if queue not in (queues.get(task) or []):
            continue
        fires = crontab_fire_times(entry.get("schedule"), start, days=1)
        if fires is None:
            unenumerable.append(name)
            continue
        hold = effective_hold_s(soft_limits.get(task), global_hard_limit)
        if hold is None:
            # No bound of any kind: it can never be shown to release. Modelled as
            # holding to the end of the window rather than skipped, because
            # skipping it would understate exactly the case that is worst.
            hold = (end - start).total_seconds()
        for f in fires:
            if start <= f < end:
                arrivals.append((f, hold, False))

    warmer_fires = crontab_fire_times(warmer_entry.get("schedule"), start, days=1)
    if warmer_fires is None:
        raise ValueError(
            f"{warmer_beat!r} has a schedule this simulator cannot enumerate, so its "
            "fires cannot be counted. That is a gap, not a pass."
        )
    for f in warmer_fires:
        if start <= f < end:
            arrivals.append((f, warmer_hold, True))
    arrivals.sort(key=lambda a: (a[0], a[2]))  # competitors ahead of the warmer on a tie

    # `free[i]` is the epoch second at which slot i next comes free.
    t0 = start.timestamp()
    free = [t0] * int(slots)
    warmer_free = [t0] * int(warmer_slots) if warmer_slots else None

    fires = started = expired = 0
    waits = []
    for at, hold, is_warmer in arrivals:
        now = at.timestamp()
        pool = warmer_free if (is_warmer and warmer_free is not None) else free
        i = min(range(len(pool)), key=lambda k: pool[k])
        avail = max(pool[i], now)
        wait = avail - now
        if is_warmer:
            fires += 1
            if wait > budget:
                expired += 1
                continue  # discarded unstarted: it never occupies the slot
            started += 1
            waits.append(wait)
        pool[i] = avail + hold

    waits.sort()
    return {
        "fires": fires,
        "started": started,
        "expired": expired,
        "worst_wait_s": waits[-1] if waits else 0.0,
        "p50_wait_s": waits[len(waits) // 2] if waits else 0.0,
        "unenumerable": sorted(unenumerable),
    }


def main():
    bs = celery_app.conf.beat_schedule
    queues = beat_queues(bs, celery_app.conf.task_routes,
                         celery_app.conf.task_default_queue)
    softs = {n: (getattr(t, "soft_time_limit", None) or 0)
             for n, t in celery_app.tasks.items()}
    hard = celery_app.conf.task_time_limit
    start = datetime(2026, 9, 7, 2, 0, tzinfo=timezone.utc)

    print("The scenario CERT-2053 named, confirmed against the LIVE schedule:")
    print("  02:08:00  turbo-collapse-futures        declared hold 3600s")
    print("  02:10:00  run-freshness-watchdog                       300s")
    print("  02:10:00  sync-tennis-from-espn                        300s")
    print("  02:10:00  refresh-registered-tournament-prices         240s")
    print("  02:10:00  warm-event-concepts                          240s")
    print("  02:10:00  link-tournament-matchups                     180s")
    print("  (five over-budget arrivals, not four -- the block undercounted by one)\n")

    shared = simulate(bs, softs, queues, start=start, minutes=30, slots=2,
                      global_hard_limit=hard)
    bought = simulate(bs, softs, queues, start=start, minutes=30, slots=2,
                      global_hard_limit=hard, warmer_slots=1)
    print("shared 2-slot background pool :", shared)
    print("dedicated 1-slot warmer pool  :", bought)
    print(RESULT)


RESULT = """
RESULT — WHY THIS IS AN ARTIFACT AND NOT A GUARD.

    shared 2-slot pool      180 fires, 0 started, 180 expired   (100% loss)
    dedicated 1-slot pool   180 fires, 20 started, 160 expired  (89% loss)

Production, measured over the same warmer's own 32-deep ring on 2026-09-06:
period p50 44.1s, p95 189.0s, and passes completing 40/40. A model that says the
warmer never starts, and that BUYING THE DEDICATED WORKER still loses 89% of
fires, is not describing this system.

Two model errors, and neither is fixable from declarations:

1.  SELF-GATING IS NOT MODELLED. The beat fires every 10s; the task declines to
    start within `MIN_PASS_PERIOD_SECONDS` (30) of its own last start and while a
    previous pass holds the lock. Those declines are NORMAL -- 85,293 of them
    against a handful of real passes -- and this simulator scores every one as a
    starved fire. That alone accounts for the dedicated-pool number: a 100s task
    fired every 10s onto one slot backs up, which is exactly what the self-gate
    exists to prevent.

2.  DECLARED HOLDS OVERSTATE RESIDENCY ~5x. Only six background tasks have a
    measured p95 over the 120s budget; 59 DECLARE one, and 78 of 110 have no
    recorded duration at all. The declared model is sound for a yes/no about a
    GUARANTEE and useless for a QUANTITY, and this simulator asks for a quantity.

So the named regression cannot be calibrated today, and shipping it as a guard
would bank a number that contradicts the production ring. What CAN be answered
from declarations is the yes/no the purchase actually turns on -- "is there any
queue we already pay for where a slot is guaranteed inside the budget?" -- and
that is shipped, as
`TestNoQueueWeAlreadyPayForIsAHomeForTheWarmer`.

WHAT WOULD MAKE THIS SHIPPABLE. LAT-P242 (#3466, merged) is the instrument that
gives the 78 unlabelled beats a duration. Once it has a week of data, re-run this
against MEASURED p95s instead of declared soft limits, and model the self-gate.
Then the quantity becomes real and this becomes the guard CERT-2053 asked for.
"""


if __name__ == "__main__":
    main()
