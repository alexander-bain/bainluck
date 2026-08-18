# LAT-P068 — the real occupant: re-deriving the #224 "deliberately left" call

**Directive (Fable, LAT-P068 item 2):**

> *THE REAL OCCUPANT: the 816s+ class (backfill_winners at 13.6min p50) was deliberately left per
> #224 — that call is now up for re-derivation with the S1 evidence: options (chunk it per #1887's
> budget rails, route to heavy, third slot) priced per 050 with a registered prediction. This is the
> fix the holes have been asking for; the last one treated a different patient.*

**The re-derivation is done, and it does not land where the directive expected.** The directive's own
standard is why it is reported this way: *T1's REFUTED — not rounded to PARTIAL — is the program's
standard on display.* The same standard, applied to the directive's own model, says
`backfill_winners` is **not** the occupant.

**`backfill_winners` p50 is 13.7 min — that number is exactly right, and it is the wrong statistic.**
Duration is not occupancy. It runs 4×/day, so it holds **4.90 % of one slot** (**2.45 % of the
2-slot pool**, ≈56 min/day), and it appeared in **0 of 122 slot-observations** across 62 minutes of
direct pool measurement. Meanwhile the pool ran at **98.4 % utilisation** with a backlog *growing*
3.6 messages/minute.

**The occupant is not one task.** It is `warm_typeahead` at 26.2 %, a pre-deploy message backlog
still delivering `match_prediction_markets` to `background` three hours after it was re-routed away,
and an unbounded, until-today *uninstrumented* pair of hour-budgeted collapse tasks at 18.1 %.

---

## §0 — The "post-backlog-drain" precondition was NOT met, and that is a finding

The directive's item 1 asked for the S1 re-measure **post-backlog-drain**, on the reasoning that the
pre-deploy-message caveat blocks a verdict on #1609's fix until the queue has cleared.

**It has not cleared, and on the current arithmetic it cannot.** At claim, background depth was
**3,349** — higher than LAT-P067's 3,014. Across the 62-minute observation it rose monotonically
**3,352 → 3,573**, i.e. **+3.6 messages/minute**, on a pool measured **98.4 % utilised**.

So the question was whether the queue holds **pre-deploy zombies** (which would drain, making the
wait worthwhile) or **live inflow that exceeds capacity** (which never will). The answer is **both,
and that is worse than either**:

1. **The head of the queue is fresh inflow.** `celery-debug`'s `queue_sample` reads
   `lrange("background", 0, 19)` — with `LPUSH`/`BRPOP` that is the **newest** 20, not the old tail.
   It returned **18 × `warm_typeahead`**, 1 × `precompute_discover_candidate_base`,
   1 × `refresh_open_commentary`. Current arrivals, not history.
2. **And the tail is still serving pre-deploy messages, three hours on.** `match_prediction_markets`
   was observed running under **two different `routing_key`s at once** — one `background` (published
   before `-59` re-routed it) and one `heavy` — and background-routed instances kept appearing for
   the **whole 62 minutes** (§2). A FIFO pops the *oldest* first, so a ~3,500-deep queue keeps
   delivering pre-`-59` messages long after the deploy.

**Therefore the precondition is unsatisfiable, not merely unmet.** Arrivals exceed departures, so the
tail never reaches the end. Waiting for the drain would have burned the window and produced nothing.

**What this costs the read, stated honestly:** the S1 re-measure is a **replicate of LAT-P067's
conditions**, not the clean post-drain read that was asked for. On its own it cannot separate "holes
caused by backlog" from "holes caused by an occupant", and the second signal above means the
`-59` re-route **has still never been observed operating on a clean queue**.

**What replaces it:** S4 supplies directly what the drain was supposed to supply by subtraction —
per-slot attribution of who held the pool, minute by minute. The attribution question is answered by
a better instrument instead of by waiting for a condition that will never arrive. That is the whole
reason this window built one.

---

## §1 — The instrument that was missing, and why every prior read was blind

Every previous latency read measured one of two things:

- **a backlog** — `ops-snapshot.queue_depths`, which is a plain `r.llen(queue)`; or
- **a task's own cadence** — `task-metrics`, which reports what a task did, not what stopped it.

Neither can answer *"what was holding the slot while the warmer was silent."* And on this pool the
blindness is structural, not incidental: **`background` has 2 slots.** A task can own half the pool
for fourteen minutes while the depth gauge reads a number with no relationship to it.

So LAT-P068 built **S4** (`backend/scripts/lat_p068_occupancy_observe.py`): sample
`/api/admin/celery-debug`'s `active` set, which carries each running task's `time_start` and its
**publish-time** `delivery_info.routing_key`, and turn it into per-slot occupancy intervals.

**S4 caught its own blind spot before it produced a number**, which is worth recording because it is
the same defect class: `celery-debug` builds `active`/`stats` from a broadcast `inspect` and
`queue_lengths` from Redis in *separate* try blocks, so a timed-out broadcast returns **HTTP 200 with
valid depths and an empty active set**. The first launch recorded exactly that and logged
`bg_busy: 0` — "both slots free" at the moment the pool was in fact saturated. `_inspect_answered()`
now fails those samples closed (gotcha #53, at the sub-field level).

Two other instrument facts, stated so the numbers can be checked:

- `celery-debug` costs **20.5 s** wall. The first launch at `interval=30` would have run it at 68 %
  duty and did produce two immediate `TimeoutError`s. Re-launched at 60 s / 45 s (~34 % duty).
- Occupancy is derived from **sample counts**, never from `now − time_start`. The run observed
  `running_s = −3.4` (worker clock ahead of local); any wall-clock arithmetic inherits that skew.

---

## §2 — Who actually holds the background pool

**62 minutes, 61 inspect-ok samples, 1 rejected. The pool was saturated at 2/2 in 96.7 % of samples
(59/61), and 120 of 122 slot-observations were occupied — 98.4 % utilisation.**

Shares below are **slot-observations**: for each sample, each of the 2 background slots is one
observation, so the denominator is `61 × 2 = 122`. This is the unbiased estimator and it is *not*
the interval-difference figure in the artifact's `per_task` block — see the correction note below.

| rank | task | share of the 2-slot pool | soft limit | instrumented? |
|---|---|---|---|---|
| 1 | `warm_typeahead` | **26.2 %** | — | yes |
| 2 | `match_prediction_markets` | **12.3 %** | 840 s | yes — but **all 15 sightings `rk=background`** |
| 3 | **`turbo_collapse_futures`** | **11.5 %** | **3600 s** | 🔴 **was invisible** |
| 4 | `precompute_backfill_progress` | 6.6 % | — | yes |
| 5 | **`turbo_collapse_odds`** | **6.6 %** | **3600 s** | 🔴 **was invisible** |
| 6 | `enrich_cu_v2_profiles` | 5.7 % | — | yes |
| 7 | `poll_kalshi_markets` | 4.9 % | — | yes — **also `rk=background`** |
| 8 | `warm_event_concepts` | 4.1 % | — | yes |
| 9 | `precompute_discover_candidate_base` | 4.1 % | — | yes |
| 10 | `precompute_admin_link_rate` | 3.3 % | — | yes |
| … | 8 more, each ≤ 2.5 % | | | |
| — | **`backfill_winners`** | **0 of 122 — ABSENT** (4.90 % of one slot long-run) | 840 s | yes |

**The turbo pair together is 18.1 %.** Depth over the same window: **3,352 → 3,573**, monotonic,
**+3.6 messages/minute**. Arrivals exceed departures continuously.

### 🔴 Correcting my own interim number, because the program's standard applies to me too

An interim read at 22 minutes put `turbo_collapse_futures` at **31.8 %** and ranked it first. **The
62-minute number is 11.5 %, and it ranks third.** The 22-minute window happened to contain most of
one 13-minute run, and a single long task inside a short window inflates its share.

This is exactly what P3's halt clause was written to catch, and it caught it — the difference is
that it caught my own interim figure rather than someone else's. **The 62-minute number is the one
that stands.** `turbo_collapse_futures` is a real and under-managed occupant; it is not the largest.

### 🔴 The re-route's benefit is gated behind the backlog it was meant to relieve

`match_prediction_markets` is 12.3 % of the **background** pool, and **every one of its 15 sightings
carried `routing_key: background`** — even though `-59` moved it to `heavy` and the re-route is
CONFIRMED working (heavy-routed instances were observed in the same window).

Routing keys are stamped at **PUBLISH**. So these are **pre-deploy messages still being consumed
more than three hours after the deploy**, and the mechanism is the queue itself: `background` is a
FIFO of ~3,500 messages (`LPUSH`/`BRPOP`), so the worker pops the *oldest* first. `poll_kalshi_markets`
(4.9 %, also `rk=background`) is the same story.

The interval view separates the cohorts cleanly: 6 distinct `match_prediction_markets` executions in
the window, **4 published to `heavy` and 2 to `background`**.

**This is a real and previously unstated limit on #1609's fix: a routing change only takes effect
for messages published after it, and this queue is deep enough to keep serving pre-deploy messages
for hours.** It does not rescue the causal model — the backlog is not draining, so the gate does not
open — but it does mean the re-route has never yet been observed operating on a clean queue.

### §2a — The occupant nobody could see

**The turbo pair holds 18.1 % of the background pool between them, and neither had a gauge at all.**

Neither called `_tracked_run`, so neither wrote a start or a terminal:
`/api/admin/task-metrics?task=turbo_collapse_futures` returns **NO DATA**, their durations were
unknowable, and `hard_kills` could not see them. **Every occupancy read this program has ever taken
omitted both.** S4 found them only by watching celery's `active` set directly, where
`turbo_collapse_futures` ran **13.6 minutes** and `turbo_collapse_odds` **7+ minutes**.

The exposure is structural rather than incidental:

- **`soft_time_limit = 3600`** — either may hold **half the background pool for a full hour**, four
  times a day. The observed runs used ~23 % and ~12 % of that budget; nothing bounds the rest.
- **They are twins fired 15 minutes apart** (`:30` and `:45`, every 6 h), so a long pair can hold
  **both slots at once** — a scheduled, total background outage with nothing else able to run.
- `turbo_collapse_futures` **started ≈53 minutes after its scheduled fire** — the queue delay made
  visible on a task nobody could see.

**This is the 816 s+ class the directive was looking for, and it is not `backfill_winners`** — with
the honest qualifier that at 11.5 % + 6.6 % the pair is the *third* and *fifth* occupant, not the
first. The reason it matters more than its share suggests is the **3600 s ceiling**: it is the only
resident whose worst case is bounded by nothing anyone has measured.

**Fixed this window (instrumentation only, no behaviour change):** both turbo tasks now call
`_tracked_run` under their own task names, so the next window can price the 3600 s budget against a
measured p50 instead of arguing about it. Ruling 078: a task with *no* gauge is the stronger case of
"the working gauge nobody reads."

### §2b — `warm_typeahead` is its own second-largest starver, and the mechanism is arithmetic

The warmer holds **26.2 %** of the pool. That would be acceptable if it were doing useful work. It
largely is not, and the module's own documentation says exactly why:

> *"LAT-P063 measured, 20 passes for 20, that EVERY pass with period > 45 s lost cached entries (up
> to 39 of 40) and no pass under 45 s lost any. **Crossing the TTL does not degrade the head
> gradually; it empties it.**"*
> — `typeahead_warmer.py`, on `WARM_CONCURRENCY`

The response TTL is **45 s**. The documented live operating point is *"W=4 wall is 32 s median
(29.4–42.6 s range)"* — comfortably under it.

**LAT-P068 measures the margin gone** — 37 passes, the clean pre-deploy segment:

| | documented / designed | LAT-P068 measured |
|---|---|---|
| pass wall, median | **32 s** (range 29.4–42.6) | **38.5 s** (range 33.2–57.2) |
| pass **period**, median | — | **43.5 s** — *1.5 s under the 45 s TTL* |
| per-query cost (`seconds_total`/40) | — | **3.70 s** |
| passes **crossing** the 45 s TTL | *"none"* at the documented wall | **15 of 37 — 41 %** |
| passes losing cached entries | *"none under 45 s"* | **15 of 37 — 41 %**, 9 of them *fully* cold |
| `fresh` / `rebuilt` | — | **0 / 40 every pass** |

⚠️ **Correcting an interim figure of my own again:** a 22-pass read put the period median at 46.3 s
and called it *"above the TTL"*. **On 37 clean passes it is 43.5 s — below it.** The stronger claim
does not survive the larger sample and is withdrawn.

**What survives is bad enough, and it is the accurate version:** the design bought a ~13 s margin
between a 32 s pass and a 45 s TTL, and **that margin is now essentially zero** — the median pass
lands 1.5 s inside the cliff, and **41 % of passes go over it**. Crossing is not graceful: the
head does not degrade, it **empties**. On every one of the four clean holes > 120 s the count was
`expired: 40` — all forty entries gone.

This is a treadmill with positive feedback: the warmer is slow because the surface it queries is
large → it holds a slot for ~43 s → it cannot come round before its own entries expire → the head is
cold → real user requests take the 1.16–2.29 s miss (#1866) → the warmer's next pass is slower
still. The pool saturation and the cold head are the same phenomenon seen from two ends.

**And the code already names the cure**, in the comment on the constant it forces:

> *"This cost is a workaround, not a design. The 688.6 MB trigram surface it exists to hold resident
> is 67 % of the buffer pool; **Option D replaces it with ~140 MB, after which this whole constant
> should stop being load-bearing.**"*

### §2c — T1, re-measured: REFUTED again, replicated

S1 ran **66.02 min probe-free** (1,292 ok samples, 6 `TimeoutError`, 101 distinct pass observations).
The window contains the **20:09:15 Z deploy of `9e0f0f37`**, so it is segmented by release —
LAT-P066's rule, never average across a restart.

| segment | length | passes | holes > 120 s | period median | crossed TTL |
|---|---|---|---|---|---|
| **pre-deploy 19:17:01 → 20:09:15** | **52.2 min** | 37 | **4** | 43.5 s | 41 % |
| post-deploy 20:09:15 → 20:23:02 (v3843) | 13.8 min | 14 | 1 — **spans the restart, contaminated** | 40.1 s | 29 % |

**The four clean holes:** 126.5 s, 401.2 s, 297.1 s, **584.2 s (9.7 min)** — every one `expired: 40`.

**T1's bar:** holes → ~0; **1–2 is PARTIAL, ≥3 is REFUTED.** Four clean holes in 52.2 probe-free,
deploy-free minutes — **4.75 normalised to LAT-P067's 62-minute window, against its 6.**

> ### 🔴 **T1 — REFUTED. Replicated, on a second independent read.**

Reported as REFUTED, not rounded to PARTIAL, per the standard the directive set.

**E3 — CONFIRMED.** E3 registered that hole frequency and duration would be **unchanged** by
`expires` alone, and predicted a PASS *meaning nothing improves*. 6 → ~4.75 per 62 min is unchanged
at the resolution two samples of this size can support. **E3 holds.**

**And E3 holding while T1 is refuted is the whole attribution**, exactly as LAT-P066 framed it: the
two commits ride one branch and nothing else separates them. Neither the hygiene commit nor the
re-route moved the holes. The routing fix is real, confirmed on the wire, and aimed at a patient who
was not the one bleeding.

The 23 skipped passes are worth one line, because they are *not* a defect: 22 `lock` + 1
`min_period`. A `lock` skip means a pass was already running — the expected outcome of a 10 s beat
against a ~38 s pass, and it costs ~8 ms. The skips are the beat working, not the warmer failing.

---

## §3 — So: re-deriving the #224 call

The `-59` routing block states the deliberate-leave precisely, and it is a *scoped* claim, not a
blanket one:

> *"Deliberately STILL NOT here: the big backfills (backfill_winners 840 s …). Moving THEM here would
> fill both heavy slots for ten-minute stretches and delay the hourly calibration warmer (observed
> live during the #224 rollout). That observation was about the 600–960 s class and it still holds
> for the 600–960 s class."*

**The call stands, and the evidence for it is now stronger than when it was made.** Two independent
reasons:

1. **The benefit is smaller than assumed.** `backfill_winners` is 4.90 % of one slot = **2.45 % of
   the pool**, sixth-ranked, and absent from 62 minutes of observation.
2. **The cost is larger than assumed.** When #224 was written, `heavy` was the empty lane — it
   *"measured depth 0 while background sat at 418."* It is not empty now. **`-59` itself moved
   `match_prediction_markets` onto it** (337.4 s p50 / 699.4 s p95, every 15 min — observed this
   window holding a heavy slot for **11+ minutes**), alongside `precompute_calibration_main` at
   **p90 1,149 s**. Heavy's spare capacity was spent by #1609's own fix.

**Routing `backfill_winners` to heavy is a worse trade today than the day it was refused.**

### The options, priced

| option | buys | costs | verdict |
|---|---|---|---|
| **(a) chunk per #1887's budget rails** | nothing in *total* occupancy — 4.90 % of one slot is 4.90 % whether contiguous or not. Only converts one 820 s block into N shorter ones | real work; #1887 is an open p1 worth fixing **on its own merits** (a callee budget measured from the wrong zero) | ⚖️ **do it for #1887's reasons, not for the holes** |
| **(b) route to heavy** | ≤ 2.45 % of the background pool | 4.90 % of a heavy slot that no longer has it; re-opens the exact #224 failure with *less* margin than 2026-06 | ❌ **REFUSE — the call is re-affirmed** |
| **(c) third background slot** | ~50 % more capacity | dyno RAM; and demand is **unbounded above** — depth rises 4.1/min, so a third slot may simply fill | ⚖️ **a real lever, but it treats the symptom; hold it as the T5 remedy** |
| **(d) Option D — collapse the warmer's cost** | up to **26.2 %** of the pool, and restores the TTL margin that makes the head stay warm | **built and MERGED mid-window** (`9e0f0f37`, v3843) — dark until the index + backfill | ✅ **this is the fix the holes have been asking for** |
| **(e) bound the turbo pair** | up to **18.1 %** of the pool; removes the both-slots-for-an-hour exposure | needs a measured p50 first — **now possible**, instrumented this window | ✅ **do it; the 3600 s ceiling is the only unbounded worst case on the pool** |

**The answer to the directive's framing:** the last fix treated a different patient, and so would
this one. The two levers that match the measurement are **(d)** and **(e)** — one is already written
and waiting on a merge, the other was invisible until this window and is now countable.

---

## §4 — Registered predictions (ruling 050 — armed, with halts)

Each carries a halt, because a control with no consequence attached can only confirm.

**Controls, armed for all three:** `/api/health` **0.240 s** and `/api/golf` **0.455 s**. If either
is more than ±20 % off when a read below is taken, the system is under a load episode and **the read
is void** — retake it. (§5 shows what happens when this is skipped.)

### P1 — Option D collapses the warmer, and the warmer stops starving the pool

| | now (measured) | predicted after D1 |
|---|---|---|
| per-query cost | 3.70 s | **< 1.8 s** |
| pass wall, median | 38.5 s | **< 20 s** |
| passes losing the head | 41 % | **< 10 %** |
| `warm_typeahead` share of pool | 26.2 % | **< 12 %** |

🔴 **HALT: pass wall median still > 35 s after D1.** That refutes the trigram-surface model of the
warmer's cost — the model the code's own comment rests on — and no further warmer tuning happens
until it is re-derived.

### P2 — moving `backfill_winners` changes nothing measurable *(an armed NULL control)*

**Predicted: < 1 hole per 62 min of difference** — inside the noise of a 4.75-to-6-hole baseline — whether it
is chunked or routed.

🔴 **HALT: if it moves holes materially, the occupancy model in §2 is WRONG** and every conclusion in
this document is re-derived before anything else ships. This is the cheap test of the whole
analysis, and it is the reason (a) and (b) are worth *stating* rather than silently dropping.

### P3 — the turbo pair is the largest lever

**Predicted: once instrumented, `turbo_collapse_futures` shows a p50 in the 400-900 s class**, with
a tail toward its 3600 s ceiling, and the two together account for **12-25 %** of background
slot-time over a 24 h window (they measured **18.1 %** over 62 min).

🔴 **HALT: if the measured p50 is under 120 s**, then the 13.6-minute sighting was an outlier and the
3600 s budget must **not** be touched on the strength of one observation. This clause has already
earned itself once: it is what forced the 31.8 % interim share down to the 11.5 % that 62 minutes
actually support.

⚠️ **This prediction is not actionable until the instrumentation deploys.** It rides
`program/latency-61`. Per ruling 078 clause 3, a gauge on an unmerged branch is not yet a reader.

---

## §5 — The finding that makes this a product problem, not a hygiene problem

Everything above is about internal cadence. This is not.

`/api/golf/tournaments/{slug}`, the same four completed majors, the same protocol, ~15 minutes apart:

| | p50 | p90 | max |
|---|---|---|---|
| **quiet** (controls at baseline) | **2.096 s** | 2.451 s | 3.193 s |
| **loaded** (same slugs, same protocol) | **4.583 s** | **15.260 s** | **26.714 s** |

The controls are what make this attributable: during the loaded batch `/api/health` read **0.370 s**
(vs 0.240 s) and `/api/golf` **0.604 s** (vs 0.455 s) — both elevated, neither touching a line of the
golf path. So it is **system-wide contention, not a golf regression**.

**`26.714 s` sits 3.3 s from the 30 s H12 timeout.**

This is the first measurement in this program that connects the saturated background pool to
*user-facing* latency rather than to internal warmer cadence. A 2-slot pool at 100 % saturation with
a monotonically rising backlog is not a tidiness problem awaiting a spare cycle; it is within a few
seconds of serving 503s on the event surfaces the north-star task runs on.

It also retires a convenient assumption: that background saturation is invisible to users because
nothing on a user path runs there. The contention is not for *slots*, it is for the **database and
the buffer pool**, and those are shared with every request the web dynos serve.

---

## §6 — What this window did NOT establish

- **Why the warmer's wall grew** from a documented 32 s median to 38.5 s. Data growth, load growth,
  and buffer-pool eviction are all consistent with the observation and none is measured. Option D
  makes the question moot if P1 holds; if P1 halts, this is the first thing to answer.
- **`turbo_collapse_futures`'s true p50.** One 13.6-minute sighting is one sighting. P3 is registered
  precisely so the next window measures it rather than assuming it.
- **Whether a third background slot would fill.** Demand is unbounded above in the current data
  (depth rising 4.1/min); nobody has measured the ceiling.
- **`discover_events`' real cost.** It piggybacks taxonomy updates *and* LLM enrichment inline —
  by design, because *"worker concurrency=2 means dedicated taxonomy tasks never get a slot"* — so
  its 6.8 % is three workloads wearing one name. It is a work-around for the very scarcity this
  document measures, and it is unpriced.
