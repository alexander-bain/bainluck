# LAT-P076 — the background queue is oversubscribed, and two of LAT-P075's facts about it were wrong

**Window:** 2026-08-19 21:00 PDT → (2026-08-20 04:00Z →). **Branch:** `program/latency-69`.
**Issues:** #1866 (p1), #2014 (p2), #1609 (p1).
**Authority:** Fable directive 2026-08-20, item 3 — "measure and propose the fix shape".

---

## 0. THE GATE IS UNMET: `-68` is not deployed, so R1–R3 cannot be graded

Fable's directive is explicit that R1–R3, the gate re-derivation and the user-felt
after-column are **gated on the Integrator deploying `latency-68`**.

```
origin/master            de9340f6      (moved twice during this window)
program/latency-68       b785a44e      NOT an ancestor of origin/master
GET /api/health          commit = eb098da3
```

`b785a44e` is not merged and not deployed. The Integrator is holding it **deliberately** and
says so in its own lock: *"program/latency-68 (LAT-P075) is ready but carries
beat_schedule_change: TRUE — a beat change must not deploy under an outstanding apply."*

So this window grades **nothing** against production that depends on `-68`:

| owed | status | why |
|---|---|---|
| R1 (expires → executions ≥ 95 %) | **NOT GRADED** | requires `expires: 120` live |
| R2 (period p95/max unchanged) | **NOT GRADED** | same |
| R3 (TTL 65 → head-cold ~38.9 %) | **NOT GRADED** | requires TTL 65 live |
| user-felt `_STATIC_FLOOR` after-column | **NOT TAKEN** | measuring it now would re-measure the BEFORE |
| #1609 gate payoff re-derivation | **NOT DONE** | Fable: "re-derive **post-deploy**" |

**The after-column is deliberately not taken.** Running the §0 protocol against `eb098da3`
would produce a second BEFORE reading and a table with two before-columns, which is the shape
that gets quoted later as a null result. Ruling 046's clause applies directly: *a stacked
change is measured on its OWN deploy.*

**Item 4 (the 24 h stamp census) is also not due.** t0 was 2026-08-19T23:36Z; the grade is due
after 2026-08-20T23:30Z. At this window's close that is ~19.5 h away.

Everything below is the part of the directive that is **not** gated on the deploy.

---

## 1. Two corrections to LAT-P075's §3, both in the direction that flattered the queue

### 1a. `rebuild_typeahead_index` is on `heavy`. It cannot starve the warmer.

LAT-P075 §3 named it as the co-tenant: *"Behind one 150 s `rebuild_typeahead_index` (p95
150,062 ms) … the warmer waits that long."* The claim was repeated in the module docstring and
in this suite's own comment.

```python
beat_schedule["rebuild-typeahead-index"]["options"]["queue"]      == "heavy"
task_routes["app.tasks.rebuild_typeahead_index"]["queue"]         == "heavy"
```

It contends for `worker-heavy`'s two slots and never for `worker-background`'s. **It cannot
delay the warmer by one millisecond.**

This is not tidiness. A named cause is what the next window acts on, and "move
`rebuild_typeahead_index` off `background`" is a plausible-looking remedy that would have
changed nothing. Pinned by
`test_rebuild_typeahead_index_is_on_heavy_and_cannot_starve_the_warmer`.

### 1b. It is **102** beats on `background`, not 57 — and the extra 45 are there by accident

```
task_default_queue = "background"
```

57 beat entries name `background` explicitly. **45 more name no queue at all** and fall through
the default. Effective total **102**.

The fall-throughs are not the light ones. They include the heaviest work on the queue:

| task | mean duration | on `background` because |
|---|---|---|
| `turbo_collapse_futures` | **1,859 s** | no queue declared |
| `backfill_winners` | 868 s | no queue declared |
| `poll_polymarket_markets` | 304 s | no queue declared |
| `discover_events` | — | no queue declared |

**This changes the remedy question.** A queue that 57 tasks were assigned to is a sizing
problem. A queue that 45 further tasks landed on because nobody chose a queue is a *default*
problem, and the cheapest lever is to stop the fall-through rather than buy slots for it.

Pinned by `test_the_background_queue_carries_102_beats_not_57`, which asserts the **split**
(57 explicit / 45 implicit) and not just the total — a total holds constant while 45 becomes 60.

---

## 2. The real mechanism: rho >= 1. The tail is a deficit, not a fluctuation.

Method: the **live beat schedule** (exact intervals, from config — not a sampled fire rate)
joined to per-task durations from `/api/admin/celery/schedule-adherence` and
`/api/admin/task-metrics`. Demand in slot-seconds per hour = Σ (3600 / interval_s) × duration.

`warm_typeahead` is excluded from the sum and re-added at its **measured** draw, because it is
self-gated: its 360 fires/hour are not 360 passes, they are ~72 passes and ~288
lock-skips/discards. Counting the fires would have produced 19,909 slot-s/h of pure fiction.
Its real draw is wall 45.7 s / period 50.1 s = 91 % of one slot = **3,276 slot-s/h**.

Everything is **bracketed by the duration estimator** — a p95-weighted sum prices every run at
its slowest (upper bound), a mean-weighted sum is the lower one. Neither is presented as *the*
number.

| queue | concurrency | capacity | demand (mean) | demand (p95) | **rho** |
|---|---|---|---|---|---|
| `realtime` | 4 | 14,400 | 4,534 | 8,945 | **0.31 – 0.62** |
| `heavy` | 2 | 7,200 | 4,283 | 5,863 | **0.59 – 0.81** |
| **`background`** | **2** | **7,200** | **7,814** | **10,822** | **🔴 1.09 – 1.50** |

> **Both ends of the bracket are above 1.0.**

A queue at rho >= 1 does not have a long tail; it has **no steady state**. The backlog grows
until something sheds it, and on this queue the thing that sheds it is `expires` discarding
warmer messages — which is exactly why the discard measured 30.5 %, and why raising `expires`
made saturation *readable* without making it smaller.

**That both estimators clear 1.0 is what makes this actionable.** Had the mean estimator come
in at 0.8, the honest report would have been "we cannot tell", because the bracket would
contain the answer "there is no problem".

### It is over capacity even without the warmer

`background` excluding `warm_typeahead` entirely: **4,538 – 7,546 slot-s/h**, rho **0.63 – 1.05**.

So moving the warmer elsewhere **rescues the warmer but does not repair `background`.** Two of
the four levers below only do the former. That is a real distinction and the remedy table has
to carry it.

### 🔴 This retires the FIFO-position story, including this lane's own correction of it

LAT-P075 corrected an earlier draft's "less than one slot free" to "the starvation is FIFO
position, not slot count", and pinned it. That correction was right about the arithmetic
(2 − 0.91 = 1.09) and **still understates the defect**. A FIFO-position story implies the wait
is a fluctuation — sometimes the warmer is behind something long, usually not, so the p50 is
fine. It is consistent with the 46.5 s p50 and it does not explain a 326 s max. Oversubscription
does.

### 🔴 And it withdraws support from R4

LAT-P075's R4 predicted period p95 < 90 s at `--concurrency=3`. At three slots the bracket is
**0.72 – 1.00** — it *straddles* 1.0. The upper end is exactly capacity, which is still no
steady state.

**R4 is NOT SUPPORTED BY MEASUREMENT.** This is a refusal to predict, not a prediction of
failure: R4 may hold if the mean estimator is the right one. What cannot be said is that
measurement backs it. Pinned by `test_R4_is_not_supported_by_measurement_at_concurrency_3`.

The measured-safe step is **2 → 4** (bracket 0.54 – 0.75), not 2 → 3.

---

## 3. Caught in the act: the slot census

`/api/admin/celery/inspect` sampled at 45 s spacing. (Deliberately **not**
`/api/admin/celery-debug`, which the queue forbids; `inspect` is off-loop, single-flighted and
memoised.)

The very first sample showed the mechanism directly:

```
worker celery@990f49f7  (worker-background)
  active   : discover_events, warm_event_concepts     <- BOTH slots held
  reserved : warm_typeahead, warm_typeahead           <- TWO warmer messages waiting
```

Both slots held by long co-tenants, two warmer messages queued behind them, and **neither
occupant is `rebuild_typeahead_index`**. `discover_events` is one of the 45 default-queue
fall-throughs.

### The census, n=26 samples over 29 minutes

`2026-08-20T04:07:09Z → 04:36:10Z`. **25 readable, 1 unreadable** (a timed-out curl). The
unreadable one is reported as unreadable and excluded, not counted as an idle worker — an empty
read and an observed absence are different facts (gotcha #53).

| | |
|---|---|
| slot-observations | 50 (25 samples x 2 slots) |
| **slot BUSY** | **45/50 = 90 %** |
| **BOTH slots busy** | **20/25 samples = 80 %** |
| **`warm_typeahead` queued but NOT running** | **6/25 samples = 24 %** |

| occupant | slot-obs | % of one slot | routed |
|---|---|---|---|
| `warm_typeahead` | 17 | 68 % | explicit |
| `backfill_market_shapes` | 8 | 32 % | explicit |
| `precompute_backfill_progress` | 6 | 24 % | explicit |
| `discover_events` | 3 | 12 % | **fall-through** |
| `poll_polymarket_markets` | 3 | 12 % | **fall-through** |
| `precompute_discover_candidate_base` | 2 | 8 % | explicit |
| `warm_event_concepts` | 2 | 8 % | explicit |
| `sync_statpal_injuries` | 1 | 4 % | **fall-through** |
| `kalshi_cliff_drain`, `precompute_category_pages`, `backfill_kalshi_history` | 1 each | 4 % | explicit |

Reserved (prefetched, waiting) across the window: `warm_typeahead` **14**, then
`refresh_open_commentary` 6, `precompute_discover_candidate_base` 5, `track_statpal_usage` 3.

**Three things this confirms independently of the arithmetic:**

1. **90 % busy with the warmer queued 24 % of the time** is the deficit, observed. This is a
   direct occupancy count, not a duration model, and it agrees with rho >= 1.
2. **`rebuild_typeahead_index` appears ZERO times** in 50 slot-observations. Correction 1a
   holds empirically as well as by routing.
3. 🔴 **It corrects §4's framing of lever D, which this document overstated.** Default-queue
   fall-throughs are only **7 of 45 busy observations = 16 %** of observed occupancy. The
   dominant co-tenants — `backfill_market_shapes` (32 % of a slot) and
   `precompute_backfill_progress` (24 %) — are **explicitly routed to `background`**. Removing
   the fall-through would not clear the deficit. The remedy table below is corrected
   accordingly rather than left to read better than the measurement supports.

---

## 4. The costed choice. No shape dominates, so this comes back as a ruling.

Fable: *"if the shapes genuinely trade off, the choice comes back as a ruling BEFORE it ships;
if one dominates on measurement, ship it with the measurement pinned."*

**They genuinely trade off. Nothing is shipped.**

### First, the memory constraint, because it eliminates the obvious answer

```
worker-background:  Standard-1X  (512 MB = 488 MiB)
                    --concurrency=2  --max-memory-per-child=200000   (200,000 KiB = 195.3 MiB)
```

| children | child ceiling | + parent (~50–80 MiB) | vs 488 MiB |
|---|---|---|---|
| 2 (today) | 390.6 MiB | ~440–470 MiB | ✅ tight |
| 3 | 585.9 MiB | ~636–666 MiB | ❌ **over before the parent** |

**`--concurrency=3` is not available on the current dyno at the current recycle ceiling.** It
needs either a lower `--max-memory-per-child` (which recycles children mid-work more often) or
Standard-2X.

⚠️ **This is arithmetic on configured constants, not a measurement of actual RSS, and the
measurement is not available.** `log-runtime-metrics` is **OFF** for this app (`heroku labs`),
the metrics API 404s, and the `/celery/inspect` route does not surface `rusage`. So the capacity
decision Fable is being asked to make **has no memory instrument behind it** — which is its own
finding, and the cheapest fix in this document: `heroku labs:enable log-runtime-metrics`.

### The four levers, costed

| # | lever | effect on the warmer | effect on `background` | cost | measured? |
|---|---|---|---|---|---|
| **A** | route `warm_typeahead` → `realtime` | rho 0.54–0.85 on its new queue | ⚠️ **unchanged at 0.63–1.05, still saturated** | **$0**, one-line | yes |
| **B** | dedicated queue + worker for the warmer | warmer alone: 0.91 of one slot | unchanged, still saturated | **+$25/mo** (Standard-1X) | yes |
| **C** | `--concurrency` 2 → 4 + Standard-2X | fixes both | rho 0.54–0.75 ✅ | **+$25/mo** | yes |
| **D** | give the 45 fall-throughs an explicit home | small | ⚠️ **only 16 % of observed occupancy** | $0 code, needs a ruling | yes — and it under-delivers |
| **E** | move the two big *explicit* backfills to `heavy` | large | −56 % of one slot | $0 code, needs a ruling | yes |

**Why A does not simply win despite being free.** It puts a 45 s task into the queue that
serves live odds at a 32 s cadence. `realtime` goes to rho 0.85 on the upper estimator — still
under 1, but that is the queue where saturation is *user-visible as stale prices*, and this
program has spent three cycles establishing that the upper estimator has been the right one
twice. Trading a typeahead stall for an odds stall is a product call, not a latency call.

**Why C is the honest technical answer.** It is the only lever that clears rho < 1 on both
estimators for the whole queue, with no routing judgement required. It costs $25/mo. Note it
must be **2 → 4**, not 2 → 3.

**🔴 Why D is weaker than this document first said.** An earlier draft of §4 called D "the only
lever that treats the CAUSE", on the strength of the demand table — where the fall-throughs
include `turbo_collapse_futures` at 1,859 s mean. **The census does not support that.**
Fall-throughs were **7 of 45 busy slot-observations (16 %)**; the heavy tail beats fire so
rarely (`turbo_collapse_futures` at 0.17/h) that they were never observed holding a slot at
all. D remains worth doing — it is how unreviewed heavy work arrives on a user-facing queue,
and it is free — but **it is hygiene against recurrence, not a fix for the present deficit.**
Stated here because the demand table and the occupancy census disagree, and the census is the
one that measured what actually happened.

**Why E is the lever the census actually points at.** `backfill_market_shapes` (32 % of one
slot) and `precompute_backfill_progress` (24 %) together hold **56 % of one slot** and are
explicitly routed to `background`. `heavy` is at rho 0.59–0.81 with room. Moving those two is
free and larger than D — but it is exactly the move the standing "`heavy` is calibration-only"
constraint forbids, so it needs the same ruling.

### What this lane recommends, stated as a recommendation and not as a fact

**E first, then C if E is refused or insufficient; D as hygiene either way.** E is free, is
aimed at the measured occupants rather than the modelled ones, and needs only a relaxation of
"`heavy` is calibration-only". **A should be refused** unless Alex is comfortable putting
typeahead work on the live-odds queue.

**This ordering is a judgement over a bracket, not a derivation.** E's effect on rho is not
measured — freeing 56 % of a slot removes ~2,000 slot-s/h, which clears the mean estimator
(rho → 0.81) but not the p95 (rho → 1.22). So **E alone may not be enough, and C may be needed
anyway.** That is the honest state and it is why this is a ruling request rather than a ship.

**Nothing here ships without a ruling.** Per the directive, worker topology is the
highest-blast-radius change in the program.

---

## 5. Registered prediction for whichever lever is chosen

**R5.** If `background` concurrency reaches 4 (lever C), period p95 drops below **90 s** and
the `_STATIC_FLOOR` cold rate drops below **30 %**. If it reaches only 3, **no prediction is
registered** — the bracket straddles 1.0 and a prediction over a straddle is a guess wearing a
number.

**R6.** If lever A ships alone, the warmer's period improves but `background`'s own lapping set
(`find_lapping`) does **not** shrink, because the queue stays at rho 0.63–1.05 without the
warmer. This is the prediction that distinguishes "we rescued the warmer" from "we fixed the
queue", and it is designed to be able to embarrass lever A.
