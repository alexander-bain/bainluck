# LAT-P060 — the warmer arithmetic (#1866, #1545)

Branch `program/latency-55`, base `d99e5548` (= `origin/master` = the DEPLOYED commit, Heroku
**v3825**, released 2026-08-17 09:49:02 PDT).

**Fable directive, LAT-P060:** *"The real pass interval is 95.9s (30/50 lock skips) against a 45s
TTL, so 16/24 is the structural ceiling — fix the premise, not the target: align pass cadence with
TTL … with the ceiling recomputed and shown before the fix and the ≥20/24 criterion re-derived
after. Ruling 050: predict the post-fix hit rate and the mechanism before reading it."*

This document is written in that order, and **§1–§3 were written and committed before a line of
`typeahead_warmer.py` was changed.**

---

## §1 — The ceiling, RECOMPUTED. It is not 16 of 24. It is ~11 of 24, and the reason matters.

### §1.1 Independent re-measure of the cadence (not a re-quote of LAT-P059)

`GET /api/admin/task-metrics?task=warm_typeahead`, 2026-08-17 ~17:07 UTC, 50 most recent
invocations over a **1,246 s** window. LAT-P059 read a different 1,438 s window; these are two
independent samples, which is the point (ruling 064 — one read is never a number).

| band | n of 50 | durations | what it is |
|---|---|---|---|
| **< 100 ms** | **25** | 8–47 ms | **lock skip.** The previous pass still holds `bainluck:typeahead_warmer:running`. |
| **0.6–0.9 s** | **12** | 606–858 ms | **NO-OP PASS.** 40 queries × ~16 ms = a Redis GET each. It ran, reported `complete`, and rebuilt **nothing**. See §1.2 — this band is the finding. |
| **> 1 s** | **13** | 2.7 s – **58.9 s** (median **38.0 s**) | **real rebuild pass.** |

- beat spacing = 1,246 / 50 = **24.9 s** (nominal 30 s)
- **interval between REBUILD passes = 1,246 / 13 = 95.8 s** — LAT-P059 measured 95.9 s on a
  different window. The two agree to 0.1 s, so this number is now measured twice.
- pass duration has **GROWN** since LAT-P059: median 33.1 → **38.0 s**, and `seconds_total` on the
  last pass was **41.52 s** with `seconds_max` **5.617 s** for a single query.
- `hard_kills_24h` = **1**, against `soft_time_limit=100`. Worst pass 58.9 s. Gotcha #131.

### §1.2 🔴 The premise the directive told me to fix is NOT the one the queue named

The queue's model was *"the pass is slower than the beat, so beats get skipped."* True, and
incomplete. There is a second hole, and it is the one that sets the ceiling:

**A warming pass that finds the entry already cached extends NOTHING.**

`routes/events.py:4038` returns the cached value before reaching the `setex` at `:4780`. So an
entry's life is **45 s from its last REBUILD**, and a pass that hits the cache is a 16 ms Redis GET
that resets no clock. The 12 no-op passes in the band table above are that hole, visible in
production telemetry: **12 of 50 beats ran a full 40-query "warm" that could not have warmed
anything.**

That changes the arithmetic from a simple ratio into a sawtooth. With a pass period `T`, an entry is
rebuilt only on the first pass that finds it EXPIRED, so the rebuild period is `T·⌈45/T⌉` and

    warm duty cycle = min(45, T·⌈45/T⌉) / (T·⌈45/T⌉) = 45 / (T·⌈45/T⌉)

| pass period `T` | rebuild period | warm duty | expected pre-warmed of 24 |
|---|---|---|---|
| **95.8 s (today)** | 95.8 s | **47.0 %** | **11.3** |
| 60 s | 60 s | 75.0 % | 18.0 |
| **30 s (cadence fix alone)** | **60 s** | **75.0 %** | **18.0** |
| 25 s | 50 s | 90.0 % | 21.6 |
| 20 s | 60 s | 75.0 % | 18.0 |
| 15 s | 45 s | 100.0 % | 24.0 |

**Read the 30 s row.** Fixing only the cadence — making the pass fit inside the beat, which is what
the queue proposed — lands on **75 %, not 100 %**, and it does so *non-monotonically*: a 20 s pass is
no better than a 30 s one, and a 25 s pass beats both. Tuning `T` against a TTL the warmer cannot
refresh is tuning a sawtooth. **That is the premise to fix.**

### §1.3 So where did "16 of 24" come from, and is it right?

It came from LAT-P059's observation that round 0 was cold in all three probe runs (0/8, 0/8, 0/8),
promoted in the queue to *"round 0 can never be pre-warmed, so 16 of 24 is the structural maximum."*

**That promotion does not hold.** There is no mechanism that makes round 0 special: the probe reads
the same `bainluck:typeahead:{q}` key the warmer writes, and the round gap (55 s) exceeds the TTL,
so all three rounds are equally exposed to the warmer and equally independent of each other.

The duty-cycle model needs no such assumption and explains all three observations at once:

- **the mean** — 47.0 % × 24 = 11.3 predicted, against LAT-P059's measured 14 and 7 (mean **10.5**,
  43.8 %). The model is within 3 points of the observation.
- **the 2× run-to-run swing** — each round samples one phase of a 95.8 s oscillation, so a run is
  three coin flips, not 24.
- **round 0 being cold three times** — under this model that is a **p ≈ 0.53³ ≈ 15 %** coincidence.
  Unremarkable. It does not need a mechanism, and inventing one produced a ceiling 45 % too high.

**Recomputed pre-fix ceiling: ~11 of 24 in expectation (47.0 % duty × 24), not 16 of 24.** The
banked observations, 14 and 7, straddle it.

*(Ruled out, not assumed: head MEMBERSHIP is not the binding constraint. `GET
/api/events/search/trending` returns `red sox` 1712, `celtics` 1703, `yankees` 1702, `world cup`
1696, `patriots` 1690 — **five of the probe's eight arm queries occupy the entire trending top 5**,
so the arm is inside the warmed top-40 head. See §4 for what those scores turn out to mean.)*

---

## §2 — The fix, and why it is TWO changes rather than one

**Fix A — bounded concurrency**, so a pass fits inside the beat and stops being skipped.
**Fix B — refresh-ahead**, so a pass REBUILDS a nearly-expired entry instead of reading it back.

Neither alone reaches the target. A alone lands on the 75 % row of §1.2. B alone still leaves 25 of
50 beats skipped behind a 38 s pass, so the rebuild period stays ~96 s. Together the rebuild period
becomes the pass period, and the duty cycle becomes `min(45, T)/T` = **100 % for any T < 45 s**.

### Concurrency width = 4, and here is the measurement it comes from, not a round number

Two independent bounds, and 4 is the largest value satisfying both:

1. **Duration.** The pass must clear the 30 s beat with margin at the WORST observed pass, not the
   median. Worst = 58.9 s. `W=2` → 29.5 s, which is *inside* the beat by 0.5 s — no margin at all.
   `W=4` → **14.7 s worst, ~9.5 s median**, a 2× margin. `W=8` would buy 7 s more and cost double
   the concurrent load for it.
2. **Connections — a hard ceiling in the code, not a judgment.** `app/tasks/base.py`
   `_get_task_engine()` is `pool_size=3, max_overflow=2`, so **one engine can hand out at most 5
   concurrent connections.** `W=4` fits with one spare. `W=8` would silently serialise on pool
   checkout — the concurrency would be a lie the summary could not see.

Bound (2) is why the width is *measured* rather than chosen: at `W>5` the code physically cannot
deliver the concurrency, so any larger number is a claim the runtime would quietly refuse.

**The load-shape warning is answered, not waved:** 4 concurrent trigram reads against a 1 GiB
`shared_buffers` is not 4× the buffer pressure, because they touch the SAME `ix_futures_outcomes_name_trgm`
pages the warmer exists to keep resident — they contend for the pool less than four *different*
queries would. And per LAT-P056 these are I/O-wait-dominated (95–98 % `Shared I/O Read Time`), which
is precisely the case where concurrency overlaps waiting rather than multiplying work.

### Refresh-ahead: rebuild when remaining TTL is below the threshold

`rc.ttl(key)`; if the entry has more life than one pass period plus margin, skip it as `fresh`
(reported, not silently). Otherwise `delete` and let the route recompute and re-`setex`.

**The cost of this, stated up front because it is a real regression for a real user:** between the
delete and the route's write there is a window where a user typing that prefix pays a database read.
That window is bounded by one recompute — and because the warmer keeps the pages resident, a
recompute is the **hot** cost (5–27 ms, LAT-P056), not the 1.4 s cold cost. It replaces a **30–50 s
cold window per cycle** with a ~20 ms one, and it only ever fires on an entry that was seconds from
expiring anyway. That trade is the whole fix.

---

## §3 — REGISTERED PREDICTION (ruling 050). Written before the change; graded in §5.

| # | surface | prediction | mechanism | halt |
|---|---|---|---|---|
| 1 | `excluded_pre_warmed`, ≥ 2 runs | **21 of 24** (range 18–24) | duty cycle goes 47 % → **100 %** because the interval between REBUILDS drops below the TTL; residual loss is head membership, not phase | **≤ 14 of 24 HALTS** — the duty-cycle model is wrong and this window must say which model replaces it |
| 2 | pass duration (`seconds_total`) | **≤ 15 s immediately**, then **≤ 6 s** once residency holds | `W=4` divides the serial sum; then the 30 s rebuild period sits inside the <60 s residency decay measured by LAT-P056, so per-query cost falls from ~1.0 s toward the hot 5–27 ms | **> 30 s HALTS** — pass cost is not the per-query sum, contention dominates, and `W=4` is the wrong shape |
| 3 | lock skips per 50 beats | **25 → 0** | a 9–15 s pass cannot still be running when the next beat fires at 30 s | any skips at all ⇒ the beat is not 30 s, or the pass did not shrink |
| 4 | no-op passes (0.6–0.9 s band) | **12 → 0** | there is no longer such a thing as a pass that reads a warm entry and returns; refresh-ahead rebuilds it | a surviving band means the TTL threshold is set too low |
| 5 | head p50 wall clock | **NOT PREDICTED, AND DELIBERATELY NOT REGISTERED** | `usable = not pre_warmed` (`probe_typeahead_segments.py:208`), so warming REMOVES rows from the p50's population instead of shifting them | — |

**Re-derived criterion, per the directive.** With duty → 100 %, the only remaining loss is head
membership. LAT-P059 measured **7 of 8** pre-warmed in two separate rounds and never 8 of 8, so one
arm query is plausibly outside the top-40 or systematically slower than the 150 ms warm threshold.
Ceiling therefore = 24 × (7/8) = **21**, with 24 reachable if all eight are in the head.

> **≥ 20 of 24 is re-derived as a legitimate bar** — it sits just under a ceiling of 21 rather than
> 4 above a ceiling of 16. That is the whole content of *fix the premise, not the target*: the bar
> did not move, the thing it was measured against did.

**Row 5 restated for the record (measurement note carried from the directive):** LAT-P059's run 1
head p50 matched the banked 1,627.3 ms to **0.16 ms** and run 2, seven minutes later, read
**2,331.93 ms**. The match was a coincidence and the second read is the proof. One read is never a
number — which is why prediction 1 is graded over ≥ 2 runs and why §1.1 re-measured the cadence on a
fresh window rather than quoting LAT-P059's.
