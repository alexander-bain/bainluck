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

---

## §4 — PRE-FIX VALIDATION: the model in §1 was graded against production before shipping

The prediction in §3 rests entirely on the duty-cycle model. So the model was
tested first, on the CURRENT (unfixed) deployment, twice (ruling 064).

`scripts/probe_typeahead_segments.py --rounds 3`, production `d99e5548` / v3825:

| run | captured (UTC) | pre-warmed | round 0 | round 1 | round 2 | head p50 wall |
|---|---|---|---|---|---|---|
| P060 run 1 | 17:30:38 | **14 of 24** | **8 of 8** | 2 of 8 | 4 of 8 | 1,740.01 ms |
| P060 run 2 | 17:34:25 | **8 of 24** | **0 of 8** | 1 of 8 | 7 of 8 | 2,462.06 ms |
| *(P059 run 1)* | *16:26* | *14 of 24* | *0 of 8* | *7 of 8* | *7 of 8* | *1,627.14 ms* |
| *(P059 run 2)* | *16:33* | *7 of 24* | *0 of 8* | *0 of 8* | *7 of 8* | *2,331.93 ms* |

### 🔴 "Round 0 can never be pre-warmed" is REFUTED, on the first fresh run

**Run 1's round 0 was 8 of 8 pre-warmed.** That is the assumption the 16-of-24
ceiling was built on, contradicted as directly as it can be. Run 2's round 0 was
0 of 8, from the same probe against the same build four minutes later — which is
the oscillation, not a property of round 0.

§1.3 argued this was a p ≈ 0.15 coincidence rather than a mechanism, and predicted
it would break. It broke immediately.

### The duty-cycle model predicts the mean, across four runs and two windows

| | value |
|---|---|
| model (§1.2), duty = 45 / 95.8 | **47.0 %** → **11.3 of 24** |
| P060 runs 1–2, mean | 11.0 of 24 (**45.8 %**) |
| all four runs (P059 + P060), mean | 10.75 of 24 (**44.8 %**) |

**Within 2.2 points on n = 4.** The model is not merely consistent with the data,
it predicted the mean of a fresh sample before that sample was taken. The ceiling
is ~11 of 24, and the pre-fix state is not "close to 16" — it is *at* its ceiling
already, which is exactly why no amount of retrying the old criterion was ever
going to reach 20.

### One ceiling term MOVED IN OUR FAVOUR, and it is measured, not hoped

§3 assumed head membership of **7 of 8** (LAT-P059 never saw 8 of 8 in a round).
Run 1's round 0 puts **all eight arm queries pre-warmed simultaneously**, and run
2 independently reaches 7 of 8 in round 2 including `election`. So every arm
query IS in the warmed top-40 head.

> **Membership is 8 of 8, so the post-fix ceiling is 24, not 21.** The registered
> point prediction of **21** therefore stands as registered and is now known to be
> *conservative*; **≥ 20 of 24 has four of slack under the ceiling** rather than
> sitting one under it. The bar re-derives comfortably.

### Measurement note (carried from the directive): one read is never a number

Head p50 wall, four reads of the same statistic on the same build class:
**1,627.14 → 2,331.93 → 1,740.01 → 2,462.06 ms.** Run-to-run spread is ~50 %, and
LAT-P059's run 1 matching the banked figure to **0.16 ms** was a coincidence that
three subsequent reads have now buried. Nothing in this document rests on a
single read: the cadence was re-measured on a fresh window (§1.1), the duty cycle
on two fresh probe runs (§4), and the pass-band decomposition on 50 invocations.

### ⚠️ AMENDMENT to prediction row 2, made BEFORE any post-fix read

Row 2 named its instrument as `seconds_total`. That was the wrong label for the
quantity intended, and the correction is recorded here rather than made silently
at grading time:

- `seconds_total` is the **SUM** of per-query times. Concurrency does not reduce
  it; only cheaper queries do.
- The quantity row 2 is about — and the one compared against the 30 s beat and the
  45 s TTL — is **wall duration**, which is what Celery's `recent_durations_ms`
  records and what produced the 38.0 s median. The code now emits it as
  **`seconds_wall`**.

**Row 2 is graded on `seconds_wall`: ≤ 15 s immediately, ≤ 6 s once residency
holds.** `seconds_total` is retained unchanged so every pre-P060 measurement stays
comparable, and is separately expected to fall only as residency makes queries
cheaper. No post-fix read had been taken when this amendment was written.

---

## §5 — Item 0: NOT GRADED. Third window running, and BOTH halves are missing.

| half | required | actual, 2026-08-17 10:0x PDT |
|---|---|---|
| branch-B index | `ix_fm_golf_identity_category` VALID | **`indisvalid=false`, `indisready=false`, 0 bytes** |
| the flag | `GOLF_IDENTITY_SPLIT_SCAN` set | **EMPTY — the `OR` is still live** |

Index catalogue, verbatim: `ix_fm_source_created_at` valid/ready 7,536 kB ·
`ix_fm_golf_identity_extid` valid/ready 40 kB · `ix_fm_golf_identity_category`
**invalid, not ready, 0 bytes**. The retry did not run.

Per ruling 050 and the standing directive, **nothing was graded** — not the
prediction table, not a single row of it. The registered prediction in
`lat-p058-golf-index-spec.md` §8 stands untouched and still owed.

**Naming the missing half, third time, without decay into a shrug:** the 0-byte
stub is **branch B**, which carries **7,263 of the 7,343 rows**. The DDL is 2-of-3
by count and **0-of-1 by effect**. The invalid index is also still **taxing every
write** to `futures_markets` and must be dropped before the retry (spec §7).


---

## §6 — Item 2: the evictor. Option A's write-cost premise-check PASSES, and finds something bigger.

`UPDATE futures_markets sub SET event_id = parent.event_id FROM futures_markets parent`
(`tasks/polymarket.py:1298–1313`, inside `_process_event_batch` — per batch, not per poll).

### The premise-check I was asked to take BEFORE recommending A

Option A is a partial index `(group_id) WHERE group_type='polymarket_sub_market' AND event_id IS
NULL AND group_id IS NOT NULL`. Its predicate contains `event_id IS NULL` — **the column this very
statement mutates** — so rows churn out of the index as they link, and that write cost had to be
priced first. Measured on production, 2026-08-17:

| quantity | measured |
|---|---|
| rows matching the index predicate | **213,228** (LAT-P059's scan examined 213,215 — the same rows) |
| distinct `group_id` among them | **22,886** (so the parent-side memoization collapses 213 K probes into 23 K) |
| new rows entering the predicate | **1,244 / 24 h** (8,610 / 7 d) |
| rows leaving the predicate | **≈ 1,231 / 24 h** (inferred: 1,244 created against a net +13) |
| ⇒ **total index tuple churn** | **≈ 2,475 / day ≈ 0.03 writes/second** |
| index size | ~8.5 MB (213,228 × ~40 B) — the queue's 8–10 MB estimate holds |

> **Verdict: the write cost is negligible and A's premise SURVIVES.** ~2,475 tuple operations a day
> on an 8.5 MB index, against 1,205 statement executions a day each currently seq-scanning a **977 MB
> heap**. The churn is three orders of magnitude smaller than the saving.

*(The departure figure is an INFERENCE across two instruments — LAT-P059's `EXPLAIN` row count
against today's exact `COUNT(*)` — and is labelled as one. It is not load-bearing: A survives at any
churn rate up to ~100× this.)*

**Not already covered by an existing index**, checked rather than assumed: `futures_markets` carries
`ix_futures_markets_group_id` (50 MB, plain btree on `group_id`) and `ix_futures_markets_event_id`
(23 MB). Neither can select on `group_type`/`event_id IS NULL`, so the planner would still have to
heap-fetch 792,479 rows to apply the filter — which is why it prefers the seq scan today.

### ⚠️ The risk that must go in A's runbook, because this program has been burned by exactly it

The partial index covers **213,228 of 792,479 rows — 27 % of the table.** Planners routinely reject
an index scan at that selectivity in favour of a seq scan. A's benefit is therefore **conditional on
the planner adopting it**, and that cannot be verified without building it.

So A ships with **§5.3-as-plan-shape**, LAT-P059's own correction: the post-DDL gate is *"does the
plan use `ix_fm_polysub_unlinked` on the sub side"*, **not** a cost number. LAT-P058's "landable"
query-shape change measured **1.99×** against the belief it was free; a numeric bar on a partially
indexed plan has already inverted once in this program.

### 🔴 What the premise-check turned up on the way, which is larger than the index

Of the **22,886** distinct `group_id`s in the predicate:

| | count | share |
|---|---|---|
| have a `polymarket_event` parent at all | **22,886** | **100 %** |
| whose parent is LINKED (`event_id IS NOT NULL`) — i.e. actually linkable | **2** | **0.009 %** |

**The statement is not slow because it lacks an index. It scans 213,228 rows to update 0 because
22,884 of 22,886 parents are themselves unlinked.** The parents exist; they have no `event_id`.

And that is overwhelmingly **correct behaviour, not a defect** — the distinction gotcha-#53's
neighbours keep demanding. Unlinked `polymarket_event` parents, by category:

    table_tennis 12,075 · esports 9,947 · tennis 8,068 · economics 1,562 · soccer 1,435
    cricket 1,010 · politics 510 · football 426 · geopolitics 280 · mma 275 · entertainment 249
    tech 248 · baseball 169 · golf 80 · basketball 57      (36,474 of 55,055 = 66.3 % unlinked)

**30,090 of 36,474 (82 %) are table tennis, esports and tennis** — sports for which we create no
`events` rows at all. Add economics/politics/geopolitics/entertainment/tech and it is
upstream-by-design, not a matching bug. There is a residual ~3,452 (soccer, cricket, football, mma,
baseball, golf, basketball) that arguably *should* link, but that is **team-identity/matching work
and is fenced out of this queue** — flagged, not touched.

**The consequence for Item 2 is a real one:** the 213 K population is *permanent*, not a backlog that
drains. So this statement is a permanent tax that yields ~0 forever.

- **A** makes the permanent tax cheap (977 MB → ~8.5 MB per call) with **zero semantic change**, and
  its premise-check passes. **Recommended, as an Integrator DDL runbook** (`CONCURRENTLY`, never a
  migration — gotcha #31), with the plan-shape gate above.
- **B** (bound the statement to the `group_id`s the batch just wrote) would remove the tax entirely,
  and the measurement makes its case *stronger* than the queue assumed — a full sweep is 99.99 %
  waste. But its later-batch hole is REAL and now quantified: parents are linked by
  `match_prediction_markets` (every 15 min), not by this poll, so a sub whose parent links later is
  caught only when a poll batch next touches that group. **B is not shipped.** It needs the periodic
  low-frequency sweep, a test, and a deliberate answer — which is what the queue said, and the
  measurement confirms rather than overturns.

**Neither taken as code this window.** A is a DDL proposal owned by the Integrator; B is out of scope
by its own semantics.

### The window caveat, restated so the number cannot travel without it

Do **not** quote "15.9 TB, the biggest in the database". On a rate basis over LAT-P059's fixed
interval this statement read **0.0 GB/day** — it is **bursty**, firing inside Polymarket poll
batches. Both numbers are true of different windows, `pg_stat_statements` is at its 5,000-entry cap,
and each entry spans a different unknown window.

---

## §7 — Corrections this window made to its own earlier text

Recorded rather than silently edited, because a document that quietly repairs itself teaches nothing.

1. **§2's bound (2) is stated more strongly than the shipped code earns.** The implementation opens
   `WARM_CONCURRENCY` *independent* `get_task_session()` contexts (one engine each), so the
   `pool_size=3 + max_overflow=2 = 5` ceiling is per-engine and is **not** the binding constraint on
   the shipped design. It is retained as a real bound because it is the ceiling a single-engine
   consolidation would hit, and the test pins `W ≤ 5` against it. The *operative* upper bound is the
   load shape: 3 ACTIVE backends against a 1 GiB `shared_buffers`. **Connections are not a bound at
   all** — measured `max_connections` 500, 21 in use.
2. **Prediction row 2's instrument** was corrected from `seconds_total` to `seconds_wall` — see §4,
   made before any post-fix read.
3. **The queue's "next free ruling number: 070" was three stale.** 070 (`lane1/q358`), 071 (master)
   and 072 (`program/ux-72`, claimed earlier the same day) were all held. Banked on **073** after
   sweeping all 342 refs. Seventh payout of the floor-not-oracle header; ruling 069's
   measure-never-quote is the only reason this did not collide.

---

## §8 — The post-fix read is OWED, with a receipt (ruling 066), because this lane cannot deploy

The fix is committed to `program/latency-55`. **It is not deployed**, and this lane never pushes, so
the post-fix half of §3 cannot be taken this window. Ruling 066: a deferral owes a falsifiable
artifact with a named exit condition, not an assertion.

**Exit condition — runnable verbatim by the next window, once `/api/health` reports a commit
containing `8a352501`:**

```bash
# 1. cadence. The bands are the grade: skips -> 0, the 0.6-0.9s no-op band -> 0.
curl -s -H "Authorization: Bearer $ADMIN_TOKEN" \
  "$BAINLUCK_API/api/admin/task-metrics?task=warm_typeahead" | python3 -m json.tool
#    read: recent_durations_ms banded at <100ms / 0.6-0.9s / >1s over its stated window,
#    and last_result_summary's NEW fields -- seconds_wall, rebuilt, fresh, concurrency.

# 2. duty cycle. TWICE (ruling 064); LAT-P059's two runs disagreed 2x and that was the finding.
source ~/.claude/.env
python3 scripts/probe_typeahead_segments.py --rounds 3 --out /tmp/p060-postfix-run1.json
sleep 120
python3 scripts/probe_typeahead_segments.py --rounds 3 --out /tmp/p060-postfix-run2.json
```

**Graded against §3, unchanged, with row 2 on `seconds_wall` per §4:**

| # | prediction | pass | HALT |
|---|---|---|---|
| 1 | `excluded_pre_warmed` **21 of 24** (18–24); criterion **≥ 20 of 24** against a measured ceiling of **24** | mean of 2 runs ≥ 20 | **≤ 14 HALTS** — the duty-cycle model is wrong; name the model that replaces it |
| 2 | `seconds_wall` **≤ 15 s**, then **≤ 6 s** | both runs | **> 30 s HALTS** — pass cost is not the per-query sum |
| 3 | lock skips **25 → 0** per ~50 beats | 0 | any skip ⇒ the pass did not shrink |
| 4 | no-op 0.6–0.9 s band **12 → 0** | 0 | a surviving band ⇒ threshold too low |

**Falsifiers, stated so this cannot be graded generously:**

- If pre-warmed lands **18 of 24 (75 %)**, the concurrency worked and the **refresh-ahead did not** —
  that is precisely the §1.2 sawtooth row for T=30, and it would mean `_drop_cached` is not reaching
  the key the route reads. Check the prefix first.
- If pre-warmed stays **~11 of 24**, neither half took effect; check `concurrency` in the summary
  before believing anything else — a serial pass reporting width 4 is the one failure the summary
  cannot self-detect (mutation M6/M7).
- If `rebuilt` is **0** while `fresh` is **40**, the threshold inverted and the warmer has stopped
  working while reporting `complete: 40/40` — the exact ten-week shape `task_verdict` exists to catch.

**Also owed and NOT taken here:** the residency second-order effect (prediction row 2's "≤ 6 s once
residency holds") needs a read at least 10 minutes after deploy, not immediately — the first passes
after a restart pay cold reads by construction.

---

## §8.1 — AMENDMENT to row 4, made by LAT-P061 BEFORE any post-fix read. Row 4 as written grades PASS on unchanged pre-fix code.

**Disclosed, not rewritten.** Ruling 050 registers a prediction so it cannot be tuned to the result;
the row above is left standing exactly as registered. This amendment sits below it, is dated before
the post-fix read exists, and states what forced it.

`-55` had still not deployed when LAT-P061 opened (`/api/health` = `160a7cdb`; `last_result_summary`
carried no `concurrency`/`seconds_wall`/`rebuilt`/`fresh`). So LAT-P061 re-read the **same pre-fix
task, same code, nothing changed**, and the bands had moved:

| band | LAT-P060 (pre-fix, 50 inv / 1,438 s) | LAT-P061 (pre-fix, 50 inv / 1,418 s) |
|---|---|---|
| lock skips `< 100 ms` | 25 | **12** |
| **no-op `0.6–0.9 s`** | **12** | **0** |
| **no-op `~300–400 ms`** | — | **13** |
| real passes `> 1 s` | 13 | **25** |
| max pass | 74.2 s | **65.7 s** |

**Row 4 reads "no-op 0.6–0.9 s band 12 → 0" and the honest answer today is already 0 — on code that
has not changed.** The no-op band did not close; it MOVED. Its duration is 40 sequential Redis GETs,
which measures Redis, not the warmer. A grader applying row 4 literally would have scored the
refresh-ahead fix as working before it shipped.

**Row 4 is therefore re-expressed as a predicate over work performed, per ruling 074:**

| # | prediction (amended) | pass | HALT |
|---|---|---|---|
| 4′ | on every pass reporting `terminal: complete`, **`rebuilt > 0`**; the count of complete-passes-with-`rebuilt == 0` goes **13 → 0** | 0 such passes across both runs | any surviving complete-pass with `rebuilt == 0` ⇒ refresh-ahead is not reaching the key the route reads — check the prefix, not the threshold |

`rebuilt` is a field `-55` adds precisely so this is answerable directly. Row 4′ cannot move when
Redis gets faster, and it is the question row 4 was always trying to ask.

⚠️ **Row 3 inherits the same defect and is left standing with a warning rather than amended**, because
it is closer to safe: "lock skips 25 → 0" is a count of a real behaviour (a beat that found the lock
held), but its `< 100 ms` band is still a duration proxy. The pre-fix skip count moved 25 → 12 on
unchanged code. **Grade row 3 against the concurrent pre-fix read (12), not against the registered 25**,
and treat any non-zero as the failure it describes.

**Consequence for row 1, stated because it is the one that matters:** the duty-cycle numbers this
window read on unchanged code — pre-warmed **13/24** and **8/24**, mean **10.5** — sit inside
LAT-P059's (14, 7) and LAT-P060's (14, 8) ranges. The pre-fix duty cycle is confirmed stable at
**~11 of 24 across six runs and three windows**, which is the baseline row 1's `≥ 20` is measured
against. That part of the registration is sound.

---

## §9 — Filed, not fixed: the head is a feedback loop the warmer feeds itself

Not in scope and **not touched**, but measured in passing and too load-bearing to leave unrecorded.

The head comes from `search:trending:24h`, which `/typeahead` increments **on the miss path only**
(`events.py:4790`; a cache hit returns before it). The warmer calls the route, and its calls miss,
so **the warmer votes for its own head on every pass.**

Measured: `GET /api/events/search/trending` returns `red sox` **1712**, `celtics` 1703, `yankees`
1702, `world cup` 1696, `patriots` 1690 — against **1,525 warmer successes in 24 h**. Roughly **89 %
of the head's score is the warmer's own echo**, and the `/search` log it is nominally modelled on
carries only 3,423 rows over **30 days**.

Consequence: **the head cannot adapt.** A genuinely trending new user query would need to out-vote
incumbents accumulating ~1,525 self-votes a day. The head is effectively frozen at whatever it was
when `-51` shipped.

Two notes for whoever takes it, one of which is a hazard created by *this* window's fix:

- Today's fix **keeps the warmer missing** (it drops the key deliberately), so the echo is unchanged.
  No new damage — but no improvement either.
- A future change that lets warm passes hit the cache would **silently stop the voting** and let the
  head drift. That is arguably correct, and it is certainly a behaviour change nobody would have
  predicted from the diff.

Filed as a finding for #1866/#993 triage. It is a head-SELECTION question with product consequences,
not a latency fix, and it is not a drive-by.
