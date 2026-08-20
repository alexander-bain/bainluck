# LAT-P077 — the ≥6 h horizon re-read, and what it does to R2

Window: 2026-08-20, cycle 49. Issues: #2014, #1866, #1609, #1545.
Instrument: `GET /api/admin/typeahead-warmer/last` — the same endpoint, the same 32-record
ring, the same `period_s` field LAT-P076 graded R2 on.

> **Headline: R2 HOLDS at the ≥6 h horizon, so LAT-P076's un-demotion of #2014 is RETRACTED.**
> Period p95 at horizon is **292.7 s** against a pre-fix **176.5 s** — not "climbed back
> toward", *past*. But the retraction is narrower than it sounds, and §4 says why: the
> `expires` fix did halve cache-entry LOSS and keeps R1's pass. What it did not do is fix the
> period tail, which is what R2 measures and what LAT-P075 demoted #2014 over.

---

## 0. The horizon nearly did not exist, and the ring is why it does

Item 1 required a re-read **≥6 h after the last `worker-background` restart**. At Phase 0:

```
worker-background.1: up 2026/08/20 09:16:23 -0700   (7 minutes before this window opened)
```

All six dynos had restarted with deploy **v3873 / `086ce799`**. The ≥6 h horizon would not
reopen until ~15:16 PT, and the release cadence over the previous 20 releases is **15–60 min
during working hours**. On that cadence the read Fable asked for is close to unobtainable by
waiting.

**It was recovered instead of waited for.** The warmer's pass ring lives in **Redis**, which
survives a dyno restart, and at 16:24:23Z it still straddled the boundary:

| | records | window |
|---|---|---|
| **pre-restart** (build v3872) | **25** | 15:43:31Z – 16:15:41Z |
| post-restart (build v3873) | 7 | 16:17:13Z – 16:23:44Z |

The gap **v3872 → v3873 was 11 h 38 m** (2026-08-19 21:37:51 → 2026-08-20 09:16:02 PDT), so
every pre-restart record sits **~10.5–11.6 h** into that uptime window. The horizon
requirement is met per sample.

**And the comparison is unusually clean.** v3872 was the only build running across both
LAT-P076's read and this one. Same build, same instrument, same field — **time-since-restart
is the only variable.** That is a better control than the re-read was designed to get.

⚠️ Captured at 16:24Z because it was perishable: by 16:45Z only 8 of the 25 pre-restart
records were left in the 32-entry ring. Snapshots are committed alongside this document.

---

## 1. R2, re-graded

| | before (LAT-P075) | LAT-P076 @ 30–60 min | **LAT-P077 @ ~10.5–11.6 h** |
|---|---|---|---|
| build | pre-v3872 | v3872 | **v3872** |
| n | 32 | 32 | **25** |
| period p50 | 46.5 s | 40.5 / 45.2 s | **51.3 s** |
| **period p95** | **176.5 s** | **82.4 / 74.9 s** | **292.7 s** |
| period max | 326.3 s | 266.7 s | **330.6 s** |
| passes with loss | 15/32 (47 %) | 3–4/32 (9–12 %) | **6/25 (24 %)** |

R2's clause is *"period p95/max does **not** materially improve"*.

* p95 **292.7 s** vs 176.5 s — 1.66× **worse**, not improved.
* max **330.6 s** vs 326.3 s — +1.3 %, unchanged.
* p50 51.3 s vs 46.5 s — 10 % worse.

**R2 HOLDS.** The improvement LAT-P076 graded it FAILED on does not survive the horizon.

### The honest weakness of this reading, stated before anyone else has to

`p95` on n=25 is the **second-largest sample** — a two-point statistic. Taken alone it would
be thin. It is not taken alone:

* **`max` agrees** and is the half of R2 LAT-P076 already recorded as HOLDING (*"the 266.7 s
  max occurred 631 s before the read, not at boot, so the tail has not been eliminated"*).
* **`p50` agrees** directionally.
* The distribution is not one freak: 22 of 25 sit at 46–98 s, then 113.1, then 292.7 and
  330.6. Two samples define p95, and **three** exceed 100 s.

### A second cohort, which cuts against the simple story and is reported anyway

The post-restart v3873 cohort read at 16:45Z — **29 min uptime, the same horizon band
LAT-P076 used** — is n=24, p50 58.7 s, **p95 152.8 s**, max 247.9 s, loss **7/24 (29 %)**.

That is much worse than LAT-P076's same-horizon 82.4/74.9 s and 9–12 % loss. So the
30–60 min horizon does **not** reliably reproduce LAT-P076's numbers either. Two readings are
consistent with that: LAT-P076 sampled a favourable window, or between-window variance on
this queue is simply large. **This document does not claim to distinguish them**, and the
retraction below does not rest on this cohort — it rests on the same-build horizon
comparison in the table above.

---

## 2. 🔴 The retraction: #2014 goes back to p2

LAT-P075 demoted #2014 to p2, arguing `expires` was not the period's cause. LAT-P076 measured
p95 collapsing 176.5 → 82.4/74.9 s, graded **R2 FAILED**, and **un-demoted #2014 to p1** on
exactly that basis — LAT-P075 having registered that outcome as the one that would prove it
wrong.

That collapse was measured **30–60 minutes after a restart**, and LAT-P076 flagged the risk in
its own grade: *"A near-saturated queue looks best immediately after a restart… a
longer-horizon re-read is OWED before R2's failure is treated as settled."*

The re-read is in. **The un-demotion was taken on a restart artifact. It is retracted, and
#2014 returns to p2** — announced on the issue, the same way LAT-P076 announced that the
demotion had been wrong. Symmetry was the point.

**What is NOT retracted**, because it is a different clause and it held:

* **R1 still passes.** Executions per beat fire went 30.5 % → ≥100 %; the two-thirds discard
  is gone.
* **Cache-entry loss really did improve and the improvement is durable**: passes with loss
  47 % → **24 %** at horizon (and 29 % on v3873). Roughly halved, and holding.

The `expires: 10 → 120` change earned its place. It simply is not the period repair, which is
what LAT-P075 said and what R2 measures.

---

## 3. Measuring the prefetch-buffer mechanism before proposing anything on it

Fable: *measure it before proposing — the same discipline that just saved you from your own
rho model.*

LAT-P076 explained its period improvement with a mechanism: *"the pile drains on the first
free slot" is true of the pile and false of the prefetch buffer* — with `expires: 10` a freed
slot pulls already-expired messages and discards them one after another, and if the buffer
holds only expired messages the worker waits for the next fire.

**The measurement, and it is structural rather than statistical.** `expires: 120` does not
remove the discard cliff; it **moves it from 10 s to 120 s**. A stall longer than 120 s still
expires the entire buffer and still waits for the next fire, exactly as before.

Now look at where R2 lives. The two periods that define p95 and max at horizon are **292.7 s
and 330.6 s**. Subtract the ~47 s pass wall and the warmer's slot was unavailable for
**~245 s and ~284 s**. Both are far beyond the 120 s cliff, so:

> **The mechanism cannot act on the tail R2 measures, by construction.** It is not wrong as
> physics — it is inapplicable at the only place R2 looks.

And the reason it is inapplicable is the finding: once the slot frees, a fresh beat message
arrives within 10 s at any `expires` value. **The tail is slot UNAVAILABILITY, not message
delivery.** No value of `expires` can shorten it.

That is also why the two clauses split the way they did — `expires` governs whether a *queued*
message survives (R1, loss, improved and durable) and cannot govern whether a *slot* is free
(R2, period tail, unchanged).

**Proposal withheld.** #2014's own ask — a distinct `schedule-adherence` verdict for `expires`
discards — is unbuilt and stays unbuilt this window, because #2014 is now p2. See §5 for what
was measured about it anyway.

---

## 4. Where the period tail actually comes from, and the one thing shipped against it

Slot unavailability on `background` is #1609, and LAT-P076's census measured it: **90 % busy**
on `--concurrency=2` against **102 beats**, with `warm_typeahead` itself holding ~91 % of one
of the two slots.

Ruling 110 (this window) moves two explicitly-routed backfills off `background` onto `heavy`.
That is the only intervention this window ships, and it is aimed squarely at the mechanism
above: fewer competing occupants on `background` → fewer long slot-unavailability windows for
the warmer → a shorter period tail.

**Registered prediction, to be graded at a ≥6 h horizon after ruling 110 deploys:**

| # | prediction | grade on |
|---|---|---|
| **P1** | period **p95 falls below 200 s** at a ≥6 h horizon (from 292.7 s) | ring, n≥25 pre-restart |
| **P2** | passes-with-loss falls **below 20 %** (from 24 %) | ring, same cohort |
| **P3** | period **p50 does NOT materially move** (it is wall-bound at ~47 s, not contention-bound) | ring, same cohort |
| **P4** | the two movers' 24 h run counts **rise** toward schedule (31/72 and 45/96) — they are starved, not idle | task-metrics |

P3 is the control: it predicts *no* improvement in the median. A routing change that moved
p50 as well would mean the median was contention-bound too, and this document's reading of
the wall would be wrong.

⚠️ **P4 is also the falsifier's risk.** If the movers do run more often, `heavy` inherits more
than `background` sheds — see ruling 110 and `app/utils/heavy_routing_falsifier.py`.

---

## 5. Corrections this window owes to earlier ones

### 5.1 Lever E's payoff was overstated ~3× — measured, not modelled

LAT-P076 §4 priced the two movers from a 26-sample slot census at **32 % + 24 % = 56 % of one
slot**. From `recent_durations_ms` (n=50 each) against 24 h run counts:

| task | census | observed runs | if every fire ran |
|---|---|---|---|
| `backfill_market_shapes` | 32 % | **6.1 %** | 14.2 % |
| `precompute_backfill_progress` | 24 % | **12.8 %** | 27.3 % |
| **together** | **56 %** | **18.9 %** | **41.5 %** |

A per-task share taken from 26 slot observations has very large sampling error; the duration
route has n=50 per task plus exact 24 h counts. **`background` sheds ~19 %, not 56 %** — and
the move can still cost `heavy` up to 41.5 %, because both movers are running below schedule
*because they are starved*. Ruling 110 is granted on the corrected number and watches the
asymmetry.

### 5.2 #2014's "four behind beats" is now one, and `warm_typeahead` is not among them

`GET /api/admin/celery/celery/schedule-adherence` (pure Redis) at 16:26Z: `verdict_counts` =
`{on_schedule: 85, unmeasurable: 32, overruns: 2, behind: 1}` over 120 graded of 123.

* the single `behind` is **`precompute_discover_candidate_base`** (226 deliveries vs 458.1
  scheduled, ratio 0.49) — not a typeahead beat;
* **`warm_typeahead` reads `overruns`, not `behind`** (p95 48.6 s against a 10 s interval).

#2014's structural complaint survives regardless: `deliveries` is wired to `task_prerun` and
counts **executions**, so a `behind` verdict still cannot separate "discarded by `expires`"
from "the worker never got to it". Nothing in the system counts publishes. That remains
unbuilt, and at p2 it stays unbuilt.

### 5.3 🔴 #1800 produced THREE false `NO DATA` reads in this one window

`_tracked_run` registers metrics under a name that is frequently **not** the task name, so
`GET /api/admin/celery/task-metrics/<task>` answers with an empty body for a perfectly healthy
task:

```
app.tasks.backfill_market_shapes     -> "market_shape_backfill"
app.tasks.snapshot_coverage_metrics  -> "coverage_metrics"
compute_time_horizon_calibration / compute_fair_fight_comparison
                                     -> only under their FULL names
```

The first pass at ruling 110's baseline recorded 3 of 7 watched beats as unreadable and one of
the two movers as having no data at all. **A falsifier built on that read would have been
blind on 3 of its 7 subjects while reporting itself armed** — gotcha #53 one level up: not an
empty result mistaken for a fact, but an empty result mistaken for *coverage*. Pinned by
`test_metrics_names_match_tracked_run_registrations`.

### 5.4 Two protected calibration beats are already failing, before any move

Baselines taken for ruling 110 found `compute_calibration_prices` (p50 538.2 s, p95 599.9 s)
and `precompute_backfill_winners_status` (p50 518.4 s, p95 601.0 s) **pinned at their 600 s
soft limit with ZERO successes in 24 h**. They are censored — a beat clamped at its own
timeout reports the same number however much worse it gets — so they are excluded from the
falsifier's grade rather than counted as evidence of safety.

**This is not ruling 110's to fix, and it is not caused by it.** It is recorded here because
two of the seven beats the calibration-only rule exists to protect are, on today's
measurement, already broken.

---

## 6. 🔴 The user-felt number did not hold — and the probe that measures it is confounded

Fable: *the 80 % → 0 % cold result with the 95 s-spacing control is the program's best
after-column to date — it goes on the Monday scoreboard as measured.*

**It goes on the scoreboard with this attached, because it does not reproduce.**

### 6.1 The re-measure

Same five `_STATIC_FLOOR` terms, same 95 s spacing (the control beyond the 65 s response-cache
TTL), same endpoint `GET /api/events/typeahead`. All reads HTTP 200 with 658-byte payloads —
verified not throttled.

| run | horizon | n | cold | p50 | max |
|---|---|---|---|---|---|
| LAT-P075 "before" | — | 15 | **12/15 = 80 %** | 2,779 ms | 6,250 ms |
| LAT-P076 "after" | 30–60 min post-restart | 15 (+15 control) | **0/15 = 0 %** | 218 ms | 232 ms |
| **LAT-P077 t1** | 30 min post-restart | 15 | **11/15 = 73 %** | 3,782 ms | 8,032 ms |
| **LAT-P077 t2 (powered)** | 36–56 min post-restart | **60** | **27/60 = 45 %** | 470 ms | 7,806 ms |

t2 is twelve rounds rather than three, because a 15-read window is exactly the thin evidence
this document criticises elsewhere.

⚠️ **Neither t1 nor t2 is a ≥6 h read, and one could not be taken.** `worker-background`
restarted **twice inside this window** — v3873 at 09:16 PT and **v3874 at 10:46 PT**, 90 minutes
apart. Each reset the clock. §6.3's finding does not depend on the horizon (head membership is
driven by 24 h trending traffic, not by time-since-restart), but **the aggregate cold-rate
comparison against LAT-P076 does**, and it is therefore reported as same-horizon-band
(30–60 min) rather than as a horizon read.

**The user-felt horizon read cannot be recovered the way R2's was.** §0's trick works because
the ring is a *server-side* record sitting in Redis; a client-side latency probe leaves no such
trace. It can only be taken live, which means it can only be taken **in the overnight quiet
window** — the v3872 → v3873 gap of 11 h 38 m was the only ≥6 h gap in the last 20 releases.
That is the scheduling constraint the successor needs, and it is not a matter of trying harder
during the day.

**No warmer-path code changed between v3872 and v3873** (27 files; the only task files touched
are `flow_sentinel`, `prediction_market_matching`, `repair_event_espn_id`). This is not a code
regression.

### 6.2 The decomposition, which is the actual finding

The aggregate hides a completely stable structure:

| term | cold | p50 |
|---|---|---|
| `world series` | 1/12 | **272 ms** |
| `world cup` | 2/12 | **303 ms** |
| `super bowl` | 2/12 | **277 ms** |
| `stanley cup` | **11/12** | **6,251 ms** |
| `nba champion` | **11/12** | **6,378 ms** |

Three terms are always warm at ~280 ms. Two are always cold at ~6.3 s. For ten of twelve rounds
the pattern is *exactly* 2/5, on the same two terms. This is a property of the terms, not of
timing.

### 6.3 Why: `_STATIC_FLOOR` is not the warmed set

`resolve_head()` in `app/tasks/typeahead_warmer.py` returns, in order:

1. `search:trending:24h` — the live Redis zset;
2. `search_query_logs` — the 30-day query log;
3. `_STATIC_FLOOR` — **cold-start only, "for a fresh Redis and an empty table"**.

Every record in the ring reports `head_source: "redis:search:trending:24h"`. **The static floor
has not been the head in any observed pass.** So the five probe terms are warmed only if they
happen to sit in the live trending top-40.

That is directly confirmed by the protocol's own design: at 95 s spacing past a 65 s
response-cache TTL, **the only way a read can be warm is the warmer's index.** So
warm ⟺ in the warmed head, and the t2 run is a 20-minute measurement of head membership:
three of the five in, two out, stable throughout.

> **The `_STATIC_FLOOR` probe measures trending-head COMPOSITION, not warmer health.**

Which re-reads the whole series: 80 % → 0 % → 45 % across three windows on five fixed strings
is consistent with the head's composition drifting under real search traffic. LAT-P076's 0 %
is not thereby proved wrong — it is proved **unattributable**: nothing in that protocol
separates "the warmer got better" from "these five strings were in the head that afternoon".

⚠️ **LAT-P076's stated premise is wrong.** The LAT-P076 queue header says *"The five
`_STATIC_FLOOR` terms are warmed on EVERY pass"*. They are not, and the code says so.

### 6.4 A hypothesis of this window's own, registered and then FAILED

Because `/typeahead` runs `rc.zincrby("search:trending:24h", 1, normalized)` on **every call**
(`routes/events.py:4796`), the probe feeds the very zset the warmer heads from. Registered
before grading: *if the probe pollutes its own measurement, the cold count should decline
across the 12 rounds.*

| rounds 1–4 | rounds 9–12 |
|---|---|
| 8/20 cold | **8/20 cold** |

**Identical. The hypothesis FAILS**, and it is recorded as a failure rather than dropped. The
reason is quantified: the trending head's top entries carry counts of **~4,650**
(`GET /api/events/search/trending`: red sox 4667, world cup 4658, celtics 4657, yankees 4654,
patriots 4651). Twelve increments per term cannot move rank against that baseline.

So the confound in §6.3 is real but it is **not** self-pollution on this timescale — the probe
is a passenger of the head, not a driver of it. A long enough campaign at higher volume could
still drive it; this one demonstrably did not.

### 6.5 What the scoreboard should say

> **80 % → 0 % cold (LAT-P076, v3872, n=15 + 15 control) — measured, and NOT reproduced.**
> Re-measured 2026-08-20 at n=60: **45 % cold, p50 470 ms, p95 7,375 ms.** The probe set is
> confounded: `_STATIC_FLOOR` is the warmer's cold-start fallback, not its warmed set, so the
> number tracks trending-head composition. Two of the five terms (`stanley cup`,
> `nba champion`) are persistently cold at ~6.3 s.

**#1866 is not fixed.** A user typing "stanley cup" waits ~6.3 s against a `<150 ms` budget,
today, on the deployed build.

### 6.6 The instrument this needs, specified but NOT built

One intervention per window, and ruling 110 was it. Specified for the successor:

* probe the head the warmer **actually used** (the ring already records `head_source`; it does
  not record the head itself — adding the first N entries to the ring record is small), and
  report cold rate **against the warmed set** rather than against a fixed list;
* keep a fixed list too, but report it as **coverage of the floor terms by the head**, which is
  a different and also useful number;
* never report a single aggregate cold rate over a probe set whose membership in the warmed
  head is unmeasured — that is the number that swung 80 → 0 → 45 while telling nobody why.
