# LAT-P075 — the period regression, traced to capacity; and two changes that are not the repair

**Window:** 2026-08-19 evening PDT. **Branch:** `program/latency-68`, base `6e314028`.
**Issues:** #1866 (p1), #2014 (p2), #1609 (p1).
**Authority:** Fable GO ruling 4 (2026-08-19) — TTL 65 ratified, TTL derivation CLOSED,
the period regression named as the next headline.

---

## 0. USER-FELT DELTA, measured before the fix — and it is worse than the record

The five terms in `typeahead_warmer._STATIC_FLOOR` are warmed on **every single pass**.
There is no head-resolution ambiguity about them: if the warmer ran, they are warm.

Primed all five, then read them three times at 60-second spacing (past the live 45 s TTL):

| round | world series | stanley cup | world cup | super bowl | nba champion | cold |
|---|---|---|---|---|---|---|
| 1 | 221 ms | **4,703 ms** | 233 ms | 231 ms | **2,371 ms** | 2/5 |
| 2 | **4,130 ms** | **6,250 ms** | **2,978 ms** | **2,779 ms** | **3,272 ms** | 5/5 |
| 3 | **2,073 ms** | **2,226 ms** | **2,022 ms** | **1,729 ms** | **1,973 ms** | 5/5 |

> **12 of 15 guaranteed-warmed reads were COLD — 80 %.**
> **Cold cost p50 2.779 s, max 6.250 s.** Warm cost p50 0.225 s (n=8, tight: p95 0.248 s).

Two things follow, and both are escalations:

1. **The cold cost on record is stale and too low.** #1866 carries **1.16–2.29 s p50**.
   Measured today on real head terms: **1.15–5.33 s**, and on the static floor **up to
   6.25 s**. Against a `<150 ms` budget.
2. **Rounds 2 and 3 are a stall landing on users.** 5/5 cold twice running is not a TTL
   edge effect; it is a window in which no pass ran at all.

Warm reads include this measurement point's network RTT, so 225 ms is an upper bound on
the warm path and the cold/warm ratio (~12x) is if anything understated.

---

## 1. The period, read from the deployed instrument for the first time

`GET /api/admin/typeahead-warmer/last` shipped on `-67` and deployed in `6e314028`.
First read plus 1,713 s of sampling (`/tmp/lat75-period-series.jsonl`, 112 samples,
snapshot committed beside this file):

```
period_s   n=32   min 39.974   p50 46.484   p95 176.523   max 326.250
wall_s     n=32   min 34.547   p50 41.649   p95  51.465   max  56.333
expired    passes_with_loss 15/32   worst 40   total 501
skips      87, by_reason {"lock": 87}   (zero of any other reason)
```

**The p50 is fine. The tail is the defect** — p95 176.5 s and max 326.3 s against a 45 s
cliff. Any period over the TTL empties the head (LAT-P063: 20 passes for 20).

---

## 2. What the tail is NOT

### 2a. Not the TTL

Fable's ruling already said so and the arithmetic agrees: time-weighted head-cold rate at
the measured periods is **49.7 %** at TTL 45 and **38.9 %** at TTL 65 — the 5.7-point
neighbourhood Fable quoted, ±. Zeroing it needs TTL ≥ 553 s. A TTL that survives the
regressed period is a decision to serve stale data.

### 2b. Not `expires: 10` — and this corrects a claim this window drafted

`expires: 10` **is** doing real damage, and the damage is precisely quantified below. But
it is not the period tail, and an earlier draft of this cycle's commit said it was.

The registered prediction (`/tmp/lat75-prediction.md`, written before any sampling) was
**P1: during a stall the skip counter stays FLAT**, which would mean messages were not
arriving at all — the `expires` discard signature. That prediction **held**: the decisive
observation is a **323.7 s gap with `skips_delta = 0`** while the run lock was free and
the floor clear. Nothing arrived to skip.

**But holding P1 does not establish the period claim, and continuing to sample is what
separated them.** During a stall the broker pile drains on the first free slot regardless:
with `expires: 10` the worker discards the stale messages and runs a fresh one; with a
longer expiry it runs a surviving one. **The next pass starts at the same instant either
way.** The discard is real; the period repair was not.

Recorded rather than edited out, because the reasoning that produced it — a 4/4
both-directions correlation between `ratio < 0.6` and carrying `expires`, replicated three
times — is exactly the reasoning a reader will repeat. The correlation is real. It
predicts the *discard*, not the *period*.

---

## 3. What the tail IS: `--concurrency=2` against 57 beats

```
backend/Procfile:
worker-background: celery ... --concurrency=2 --queues=background --max-memory-per-child=200000
```

**57 beat entries route to `background`.** One of them is `warm-typeahead`.

The regression has a single moving part. The beat was 10 s at LAT-P062 and is 10 s now.
What changed is the **pass wall: 32.0 s → 45.7 s median**, against a period that barely
moved. So the warmer's share of one of the two slots went:

| | wall | period | occupancy of one slot |
|---|---|---|---|
| LAT-P062 | 32.0 s | ~50 s | **64 %** |
| today | 45.7 s | 50.1 s | **91 %** |

`background` is **one FIFO with no priority**. When the warmer's pass ends and releases
its slot, that slot goes to whichever of the other 56 beats' messages is at the head of
the list — not back to the warmer. Behind one 150 s `rebuild_typeahead_index` (p95
150,062 ms) or a 77 s `warm_event_concepts`, the warmer waits that long, and the
co-tenants cluster on :00/:15/:30/:45. That is the shape of a 326 s stall.

An earlier draft of this analysis claimed "less than one slot free". **That is false** —
2 − 0.91 = 1.09. The starvation is FIFO position, not slot count, and the corrected
statement is pinned in `test_the_warmer_now_owns_most_of_one_background_slot`.

### The remedies, all of them capacity or isolation

| lever | change | why it is not shipped here |
|---|---|---|
| raise `--concurrency` on background | 2 → 3 or 4 | dyno-memory decision: `--max-memory-per-child=200000` (200 MB) × children against the dyno size |
| dedicated queue + worker for the warmer | new Procfile entry + dyno | recurring cost |
| move long backfills off `background` | routing change | `heavy` is reserved for calibration precompute; needs a ruling |
| shorten the pass | `WARM_CONCURRENCY` 4 → higher | more concurrent DB sessions; a separate derivation |

**The number is brought, not spent** — same shape as the TTL. Every lever is an infra or
cost decision, and this lane does not deploy.

---

## 4. What DID ship, and the honest boundary on each

### 4a. TTL 45 → 65 (ratified, GO ruling 4)

Three coupled edits: `routes/events.py` setex, the `RESPONSE_CACHE_TTL_S` mirror, and the
`MEASURED_WALL_*` ← `PASS_ONLY_WALL_*` swap the halt existed to force.

**🔴 Disclosure: the input moved before the number shipped.** 65 was derived from
`PASS_ONLY_WALL_MAX_S = 53.920` (n=17). The instrument's first read says **61.282 s**
(n=26) — **+7.36 s**, the third time a sampled maximum in this program proved to be a
lower bound (42.6 was wrong by 11.3 s). At 61.282 the same grader returns **MARGINAL, not
the SAFE the ratification cites**; 75 s would be SAFE.

**65 ships anyway.** Ruling 4 forecloses chasing the TTL upward. Pinned in
`test_the_ring_wall_grades_the_ratified_ttl_marginal`, which goes red if anyone edits
`RING_WALL_MAX_S` down or re-derives upward to reach SAFE.

### 4b. `expires` 10 → 120 on `warm-typeahead`

The flat `expires ≤ beat period` rule is correct for a task whose wall is shorter than its
period. This warmer's wall is 4–6× **longer**, so fires during a pass are not superseded
messages — they are the only start opportunities there are, all held by the run lock.

Executable share of fires = `(expires + max(0, period − wall)) / period`:

- **predicted 32.7 %** at expires 10, wall 45.687, period 53.521
- **measured 30.5 %** — 26 ringed passes + 41 counted skips = 67 executions vs ~220 fires
  over 2,196 s

Derived from `_LOCK_TTL_SECONDS` (a **constant**), not from the sampled wall, precisely
because that sample has been a lower bound twice.

**Claimed payoff, no wider than measured:** delivery goes to 100 %; background saturation
becomes *readable* as a burst of counted `skips:lock` instead of an absence indistinguishable
from a quiet period (gotcha #53's shape); and at most **one beat interval (~4 s)** off the
period. **Not the 176.5 s p95 tail.** Pinned in
`test_the_expires_fix_does_not_claim_a_period_repair`.

---

## 5. A gate that stopped covering its case

Fable's standing rule of 2026-08-19: *a green gate is evidence only if you can state what
it would have to see to go red, and that statement matches the defect class you claim it
covers.*

Applying it to this module's own load-bearing guard found a live instance:

`test_live_beat_interval_is_not_unsafe` fails **only on `UNSAFE`**. Raising the TTL
45 → 65 moved the refused 60 s W-move from UNSAFE to **MARGINAL** (ring wall) and to
**SAFE** (swapped wall, by exactly zero headroom). So after this cycle's own change, that
guard would go red only at a beat **≥ 70 s**. **It would not go red on the 60 s move it was
written to catch.**

Coverage restored in `test_the_proposed_60s_w_move_is_still_refused_on_the_newest_measurement`,
graded on the **quantity** (a 120 s period at the worst wall) rather than on a verdict label
that stopped carrying it.

---

## 6. The coverage census, kept wired (Fable item 4)

`stamp_arm_read.py --grade` over `/tmp/lat-p073-stamp-arm-series.jsonl`:

```
samples 38   span_h 3.16   (t0 2026-08-19T23:36Z)
stamp_tasks_covered_per_sample  [24, 25, 27, 28, 29, 31, 32]
above_ceiling_total_values      [39]
above_ceiling_stable            true
stamp_tasks_ever_not_on_schedule {}
```

**The 24 h grade is NOT due until 2026-08-20T23:30Z.** This is 3.16 h of it, stated as
such rather than graded as whole.

🔴 **And the census fired harder than last cycle.** LAT-P074 saw coverage `[27, 28]`; this
read has **seven distinct values spanning 24→32** — a quarter of the arm churning — while
`above_ceiling_total` never moves off 39. `above_ceiling_stable: true` is therefore a green
computed over a population that is not stable, which is exactly the banked doctrine: *a
metric that improves while its denominator shrinks is a defect until proven otherwise.*
Naming what it would have to see to go red: it reds only if the ceiling total takes a
second value — it **cannot** see a task leaving the arm while another arrives and holds the
total constant by composition. The census is the only instrument that can, and it stays on.

---

## 7. Registered predictions, to be graded next cycle on the endpoint

This lane does not deploy, so no "after" measurement exists yet. Graded on
`GET /api/admin/typeahead-warmer/last` and a repeat of §0 after `-68` is live.

- **R1 (expires).** Executions per beat fire go 30.5 % → **≥ 95 %**. `skips.by_reason.lock`
  rises roughly 4–5× per pass. Confidence: high — it is arithmetic.
- **R2 (expires, period).** Period p50 improves by **≤ 1 beat interval** (46.5 s → ~42–46 s).
  **p95 and max do NOT materially improve.** *This is the prediction that says the expires
  change is not the period fix. If p95 collapses, I was wrong to demote #2014 and should say so.*
- **R3 (TTL).** Time-weighted head-cold rate improves ~**10 points** at unchanged periods
  (49.7 % → 38.9 % on this window's distribution). The §0 static-floor cold rate improves
  but stays **well above zero** — predicted 80 % → 55–70 %.
- **R4 (capacity, UNSHIPPED).** If background concurrency goes 2 → 3, period p95 drops
  below 90 s. Untested; the basis for the proposal in §3.
