# LAT-P078 — the two censored beats, named and diagnosed

**Read:** 2026-08-21T14:0xZ (07:0x PDT), production build `ec636bae` / Heroku **v3881**,
released 2026-08-20 15:20:56 PT — a **15.6 h** post-deploy horizon.
**Instrument:** `GET /api/admin/celery/task-metrics/{name}`, admin-authenticated.
**Issue:** #2071. **Ruling amended:** `docs/rulings/110-*.md`.

Fable's directive of 2026-08-21 promoted ruling 110's censored-beats footnote from a flag to an
item: *"two of its seven beats sit at the 600 s soft limit with ZERO successes in 24 h, already
failing before any move; name them, diagnose, fix-or-file with the evidence — a falsifier
watching dead beats guards nothing."*

They are named below. **Neither is dead, they are not dead in the same way as each other, and
one of ruling 110's two factual claims about them is false as of today.**

---

## The #1800 precondition, applied before reading anything

`_tracked_run` registers metrics under a name that is frequently not the task name, and reading
the wrong one returns an empty body that looks exactly like a dead task. Checked in
`app/tasks/__init__.py` **first**, per the trap ruling 110 records:

| celery task | `_tracked_run` name | same? |
|---|---|---|
| `app.tasks.compute_calibration_prices` | `calibration_prices` | ❌ **differs** |
| `app.tasks.precompute_backfill_winners_status` | `precompute_backfill_winners_status` | ✅ |

Reading `task-metrics/compute_calibration_prices` would have returned NO DATA and "confirmed"
the beat was dead. That is the fourth instance of #1800 in two windows.

## Beat 1 — `calibration_prices`: budget-bounded, NOT timeout-clamped

| statistic | value |
|---|---|
| successes / failures / incompletes (24 h) | **0** / 0 / 2 |
| starts (24 h) | 1 |
| hard kills (24 h) | 0 |
| p50 duration | 538.9 s |
| p95 duration | 599.9 s |
| 10–100 s | 1 of 40 |
| 100–500 s | 1 of 40 |
| **500–598 s** | **35 of 40** |
| >= 598 s (the soft limit) | **3 of 40** |
| terminal | `partial` |
| `stopped_at` | `part_b` |
| `timed_out_parts` | `["part_b", "part_d"]` |
| `elapsed_s` | 538.4 |

**The 0 is real. "Already failing" is not.**

`app/tasks/backfill_winners.py::_compute_calibration_prices` declares its own deadline:

```
_CAL_DEADLINE_S = 540.0  # soft_time_limit=600, keep a 60s margin
```

and its own module comment states the intent — *"A run that hits the deadline returns cleanly
with `stopped_at` set (registers SUCCESS, not a timeout), and the next scheduled slot resumes
from the remaining NULLs — monotonic progress, never restart-from-scratch."*

It is doing exactly that. `app/utils/task_verdict.py` then grades `terminal: partial` as:

> Real, visible progress that is not a finished run. **Not a failure** — a resumable sweep
> returning `partial` is behaving as designed — but it can never read GREEN.

**Progress confirmed, not assumed.** `part_a_cursor` between the two independent reads:

```
2026-08-20T18:14:34Z   220,450,332      (ruling 110's pre-move baseline artifact)
2026-08-21T14:0xZ      220,617,056      (this read)                  delta +166,724
```

**So the shape is:** 35 of 40 runs stop on a 540 s clock the task owns; only 3 of 40 ever reach
the 600 s ceiling. The falsifier's exclusion is the right call, but ruling 110's stated
mechanism — *"a beat clamped at its own timeout reports the same number however much further
behind it falls"* — does not describe this beat. It is insensitive to contention because it
stops on its own clock, not because it is pinned against a ceiling.

🔴 **The distinction is load-bearing, not pedantry.** A truly clamped beat has no readable
signal at all. A budget-bounded beat has a perfectly good one — **work done per run**
(`stopped_at`, cursor delta, rows drained) — which is exactly what contention would move, and
which a p95-on-duration can never see. There is an instrument here the falsifier is declining
to use.

## Beat 2 — `precompute_backfill_winners_status`: ruling 110's "ZERO successes" is FALSE

| statistic | value |
|---|---|
| **successes / failures (24 h)** | **18 / 2** |
| starts (24 h) | 3 |
| p50 duration | 518.4 s |
| p95 duration | 600.1 s |
| max duration | 601.1 s |
| 10–100 s | 1 of 50 |
| **100–500 s** | **20 of 50** |
| **500–598 s** | **22 of 50** |
| >= 598 s | **7 of 50 (14 %)** |
| `recent_durations_saturated` | **true** — window 176,298 s (49 h), so the ring is NOT a 24 h view |
| last verdict | `unverified` — `not_enforced(complete:terminal:ok)` |

This beat runs, completes 18 times a day, and its durations span two and a half orders of
magnitude. It carries precisely the signal the falsifier wants.

**It is censored anyway — by a statistic, not by a fact about the beat.** The rule is

```
CENSOR_FRACTION_OF_SOFT_LIMIT = 0.98        # applied to p95
p95 >= 0.98 * 600s  ->  censored
```

A distribution with a **14 % clip rate** at the ceiling has a p95 *at the ceiling* by
arithmetic — any clip rate above 5 % saturates a p95 completely. The rule therefore discards
the beat on the strength of the 7 runs it cannot read, while ignoring the 43 it can.

Secondary finding: `last_verdict: unverified / not_enforced(complete:terminal:ok)` — it is not
enrolled in `ENFORCED_TASKS` with a `terminal`, so its verdict is non-authoritative and reads
GREEN by default. That is the known "enrolling a task without a `terminal` is a no-op" trap.

## What this does to ruling 110's guarantee

**Effective coverage today is 4 of 7, not 3 of 7.** The falsifier under-reports itself, and the
one beat it wrongly excludes is excluded by a statistic choice.

The error direction is the **safe** one: it excludes a beat rather than counting it as evidence
of safety, which is exactly what the three-valued design intends (`INCONCLUSIVE` is not
`HOLD`). **So this is not a reason to hold the routing move**, and the grant stands.

## Fix-or-file: FILED (#2071), deliberately not fixed

Three changes are proposed in the issue: censor on a statistic below the clip rate and report
the clip rate beside it; give `calibration_prices` a work-done comparator instead of a duration
comparator; enrol `precompute_backfill_winners_status` in `ENFORCED_TASKS` **with a terminal**.

None were made this window, for two reasons:

1. **The falsifier has never been read in production.**
   `GET /api/admin/heavy-move/falsifier` returns **HTTP 404** — `program/latency-70` is
   unmerged and `origin/master` is still its own base `ec636bae`. Changing the grading rule
   before its first read would mean the baseline pinned *before* the routing change gets graded
   by a rule that changed *after* pinning. That is the frozen-config defect, and refusing it is
   the entire content of ruling 110's general clause.
2. **One intervention per observation window.** LAT-P078's is the #1866 head-composition fix.

## Method note

Every number here is a single point-in-time read at one horizon, on a build whose routing
change is not live. Ruling 110's baseline was likewise a single read, which is how it recorded
`succ 24 h: 0` for a beat that does 18 — **the disagreement between the two reads is itself the
finding**, and neither read is more authoritative than the other. What can be said with
confidence is structural and re-derivable from source: the 540 s self-deadline, the `partial`
verdict semantics, the cursor advance, and the p95-under-clipping arithmetic. The success
counts are a snapshot and should be re-read, not cited as a constant.
