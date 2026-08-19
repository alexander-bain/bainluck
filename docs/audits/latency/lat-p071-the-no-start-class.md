# LAT-P071 — beats that never start: the mechanism, the census, and what the detector cannot see

**Window:** 2026-08-19 04:26Z – (open). **Fence:** nothing here deploys before 2026-08-19T17:01Z.
**Directive:** Fable, LAT-P071 item 3 — *"not 'why are tasks slow' but 'why do scheduled tasks not
run.'"*

Every number below is a production read taken this window, dated, with its instrument named. Where
a directive premise did not survive the measurement, the correction is stated before the finding
that replaces it — a predicted red graded against the wrong cause is worse than no read.

---

## §0 — The answer, and it is two causes that compose

A scheduled task does not start because **the background queue is FIFO and something is ahead of
it**. Nothing exotic underneath: kombu publishes with `lpush` and consumes with `rpop`,
`worker_prefetch_multiplier` is 1, and the worker has 2 slots. What makes it a headline is that the
"something ahead of it" is **two separate populations, and neither alone would do this**:

1. **The wall — who fills the queue.** One beat, `warm_typeahead`, every 10 seconds, is **72.0 % of
   everything scheduled into that queue**, and ~82 % of its fires are **10-millisecond no-ops**. It
   publishes 8,640 messages a day to do roughly 1,550 rebuilds. The other ~7,000 do nothing except
   take a place in line.
2. **The grinders — who hold the slots.** Measured continuously over 15 minutes:
   `match_prediction_markets` (p95 **840 s** against its own 900 s interval) and
   `precompute_backfill_winners_status` held **both** slots of one background worker in **19 of 19**
   observations. Nothing else got either slot.

Clearing a 10-millisecond no-op still requires a slot, and the slots are held for fourteen minutes at
a time. So the wall is only cheap to clear when there is a worker free to clear it, and there is not.
A message published now waits for **both** — which is why `turbo_collapse_futures` waited 123.6
minutes (§1) and why three unrelated beats at three different cadences all land at the same 0.15
adherence ratio (§2c).

**The single sentence, if there has to be one:** *a gate inside the task cannot protect the queue.*
`warm_typeahead` decides in 10 ms that there is nothing to do — but it must be published, queued and
handed a slot before it can decide, and the slot is the scarce resource (§4).

⚠️ **What this window got WRONG and then measured:** the obvious version of this story — that the
warmer's own no-ops are what the worker is busy chewing through — is refuted by the same sampler that
suggested it. `warm_typeahead` **has not executed since 01:55:32Z** and never once appeared in the
active set. It is not the consumer of the wall; it is starved behind it. That leaves the queue's
periodic 37–86-message drops unexplained, and **loss is now the leading candidate over consumption**
(§3c) — registered as an open question with a discriminating test, not resolved.

---

## §1 — The discriminating test (directive item 2), and it is answered

LAT-P070 left this registered:

> `turbo_collapse_futures` was published at 00:30Z and had **not started** 106 minutes later.
> Candidate **A** = queue delay, candidate **B** = the 00:54Z `v3851` restart. *"Not separable from
> here, so no cause is reported."* Discriminating test: watch `match_prediction_markets`' publish→start
> lag — a FIFO backlog cannot give it ~5 min and turbo 106.

**The 00:30Z message started at 02:33:35.816Z and succeeded at 02:59:36.141Z** (`task-metrics`,
read 04:27Z). Publish→start lag **123.6 min**; duration 1,560.3 s; 434,598 rows deleted. So the
sample LAT-P070 could not close now exists — and it closes the cause question by a cleaner route
than the registered one.

| | published | started | lag |
|---|---|---|---|
| `turbo_collapse_futures` | 00:30Z | **02:33:35.8Z** | **123.6 min** |
| `turbo_collapse_odds` | 00:45Z | **02:57:06.4Z** | **132.4 min** |

**Candidate B is REFUTED, and the refutation is `turbo_collapse_odds`.**

`worker-background.1` restarted at **02:32:58Z** (`heroku ps`; release v3854, `962f668a`). Futures
started **37 s** after it — which on its own looks like the restart released it. But odds started
**24 min 8 s** after the same restart. A restart that released the backlog would have released both
at once. Instead the two messages **kept their publish order and stretched their separation**:
900 s apart on the beat, **1,411 s apart at start**.

That is the same shape LAT-P069 measured on a different pair (900 s scheduled → **1,879 s** observed)
and Fable's directive named as the likely mechanism. It is now seen twice, on different tasks, on
different days. **A FIFO queue under saturation does not preserve the schedule's spacing; it
multiplies it.**

Three further facts make B unavailable rather than merely unlikely:

- **Four worker restarts fell inside the wait** — v3851 00:54Z, v3852 01:22Z, v3853 02:05Z,
  v3854 02:32Z. The message survived all four. With `task_acks_late` unset (default `False`) a
  *reserved* message is acked on delivery and would be destroyed by a restart; this one was not,
  so it was never reserved. It was sitting in the Redis list, un-consumed. That is candidate A's
  signature and not B's.
- **Candidate C (expiry) was eliminated in LAT-P070** — the task is in neither `_EXPIRING_WARMER_BEATS`
  nor `HEAVY_TASKS`.
- **The drain rate predicts the wait.** §3's sampler measures the background queue draining at
  ≈19.5 msg/min from ~2,700. A full drain is ~2.3 h. The observed wait was 2.06 h.

**Verdict: A (queue delay), confirmed on two independent lines. B refuted. C eliminated.** The 37-second
coincidence with the restart is recorded because it is genuinely striking and would otherwise be
rediscovered as a finding by the next window.

*Not run:* the originally-registered `match_prediction_markets` probe. It became unnecessary — the
odds/futures pair answers the same question with real production messages rather than a watch, and
`match_prediction_markets` returns `no_data` on `task-metrics` under its own name anyway (#1800:
task-metrics and schedule-adherence use two different identifier spaces).

---

## §2 — 🔴 The detector built to answer this question cannot see any of the three specimens

`GET /api/admin/celery/schedule-adherence` exists precisely to answer "did it run as often as it is
scheduled to?" Read 2026-08-19T04:3xZ:

```
scheduled_tasks 123   graded 121
verdicts: unmeasurable 71 · on_schedule 45 · behind 3 · overruns 2
```

**71 of 121 unmeasurable.** Fable named three specimens. The detector grades **none** of them, and
each is blind for a *different structural reason*:

| specimen | what the detector says | why |
|---|---|---|
| `turbo_collapse_futures` | `unmeasurable: window_too_short(expected=0.33<2.0)` | 6-hourly; gradeable only in the back half of each counter cycle — **genuinely transient** |
| `precompute_calibration_main` | `on_schedule`, ratio **1.07** | it is **not** in this class at all — see §5 |
| `refresh_hub` | **absent from the payload entirely** | not a beat. `beat_intervals()` reads `celery_app.conf.beat_schedule`; a request-dispatched task has no interval and is therefore invisible **by construction** |

### 2a — The permanent blind spot: 33 of 123 beats can never be graded

The rate arm needs `window_s / interval_s >= MIN_EXPECTED_FIRES` (2.0). `window_s` is the age of a
counter created `SET NX EX 86400` at its own first increment, so it is bounded above by
`WINDOW_COUNTER_TTL` and by nothing else:

```
gradeable  <=>  interval_s <= WINDOW_COUNTER_TTL / MIN_EXPECTED_FIRES  =  43,200 s  =  12 h
```

**33 of 123 scheduled entries are on the wrong side of that line** — every one 24-hourly or weekly.
A further 7 have no counter window at all. Each of the 33 reports
`window_too_short(expected=0.89<2.0)`: a string that reads as a condition about to clear. **It never
clears.** The counter cannot outlive its own TTL, so the expectation cannot reach 2.0, so the verdict
cannot change — not tomorrow, not ever, while both constants hold.

Among the 33: **`flow_sentinel`, `grid_sentinel`, `horizon_sentinel`, `settled_concept_sentinel`,
`board_sentinel`, `mlb_schedule_coverage`** — **all six of the tasks T5 grades.** That is not a
coincidence, and it is the structural reason the LAT-P070 T5 protocol had to abandon the counters and
grade on `last_success_at` instead. That protocol was written for one task under time pressure. It is
the general fix, and this window generalised it (§6).

### 2b — Same constant, two defects

`WINDOW_COUNTER_TTL = 86400` is compared against a task's cadence in two places and is wrong in both:

1. **TTL == cadence** → four independently-expiring counters race their own expiry once a day, and
   `starts` and `successes` can resolve the race in opposite directions. That produced LAT-P070's
   phantom hard kill (`mlb_schedule_coverage` reported `hard_kills_24h: 1` in a payload carrying that
   run's own `last_success_at`). Fixed on `-63`.
2. **TTL < 2 × cadence** → the beat is `unmeasurable` forever, in a word that means "not yet".
   Fixed here.

One constant. Two defects. Both from **comparing a TTL against a cadence** — which is doctrine, not
a bug report, and is banked as one.

### 2c — What the rate arm CAN see, and it is bad

Three beats are graded `behind`, and all three land at almost exactly the same ratio:

| task | interval | started | scheduled | ratio |
|---|---|---|---|---|
| `precompute_discover_candidate_base` | 120 s | 15 | 102.9 | **0.15** — and `terminals: 0`, `never_completes` |
| `refresh_open_commentary` | 180 s | 11 | 69.2 | **0.16** |
| `warm_event_concepts` | 300 s | 6 | 40.2 | **0.15** |

Three different cadences, one ratio. That is the signature of a shared resource, not three
independent bugs — they are all waiting on the same 2 slots.

⚠️ **Caveat, stated because it cuts the right way:** the numerator is `deliveries`, recorded from
celery's `task_prerun`, and **#1802 is open — that counter also counts retries and eager runs.**
Retries would *inflate* deliveries, so 0.15 is if anything an over-estimate of adherence. The
finding is conservative.

---

## §3 — The mechanism, watched directly: a sawtooth, not a drain

Sampler: `docs/audits/latency/lat-p071-no-start-sampler.jsonl` — background depth + slot occupancy
every ~20 s. Read-only. First 20 ticks, 04:35:24Z → 04:42:01Z:

```
04:35:24  2797      04:38:10  2728      04:40:36  2739
04:35:45  2801      04:38:31  2729      04:40:57  2737
04:36:05  2803      04:38:52  2728      04:41:20  2739
04:36:26  2805      04:39:13  2729      04:41:41  2742
04:36:47  2807      04:39:34  2731      04:42:01  2668   <-- drop of 74
04:37:08  2721  <-- drop of 86        
```

**Two regimes, alternating:**

- **Between drops: +2.55 per 20-second tick = +7.65 msg/min.** The scheduled background inflow is
  8.33/min (§3b). Arrivals are landing and essentially nothing is leaving.
- **The drops: 37–86 messages in under 20 seconds**, five of them across 44 ticks.

### 3a — 🔴 I predicted the drops were `warm_typeahead` no-ops. **The same sampler refuted it.**

The obvious reading of a ~80-message burst is the one LAT-P066 already named — *"+11-starts-in-6-seconds
bursts of 15 ms lock-skips"* — i.e. the worker chewing through a wall of `warm_typeahead` messages
that each find the work done and exit in 10 ms. The duration histogram supports it: last 50 runs,
**min 8 ms, p50 10 ms, p90 38,518 ms, p95 43,181 ms, mean 8,019 ms** — about nine real ~44 s rebuilds
and forty-one ~10 ms no-ops.

**It is wrong, and two independent readings in the same file say so:**

1. **`warm_typeahead.last_started_at` is frozen at `2026-08-19T01:55:32.141522Z` across all 44 ticks**
   (04:35:24Z → 04:50:04Z, sampled nine times). `warm_typeahead` calls `_tracked_run` unconditionally
   — there is no early return in front of it — so a stamp that has not moved in **2 h 55 m** means the
   task has not executed in 2 h 55 m.
2. **It appears in the `active` set ZERO times in 44 ticks.**

So `warm_typeahead` is not draining the queue. **It is the thing being starved** — the largest
publisher into the background queue is itself in the no-start class, behind its own wall.

**And the drops are therefore unexplained.** That is §3c, and it is this window's biggest open
question rather than a finding.

### 3b — Who actually holds the slots

The `active` census over the same 44 ticks, background/heavy pools (2 slots each):

```
celery@3f8b8ea5   match_prediction_markets          19 / 19 observations
                  precompute_backfill_winners_status 19 / 19 observations
celery@d965cd29   precompute_backfill_progress      19,  update_max_movement 6,
                  run_data_quality_watchdog 5, backfill_market_shapes 3, ...
celery@0da417b3   precompute_backfill_progress      12,  poll_polymarket_markets 12, ...
```

**`celery@3f8b8ea5` held BOTH its slots continuously for the entire 15-minute observation**, by two
tasks and only two. `match_prediction_markets` is the one the rate arm independently grades
`overruns` — p95 **840.0 s**, 0.93× its own 900 s interval. A task that occupies a slot for 14
minutes out of every 15 is not sharing a 2-slot pool; it is holding half of it permanently.

That is the actual starvation mechanism, and it is the grinder half of the split LAT-P066 named:
*"grinders occupy slots — that is what starves the warmer."* This window measures the grinders by
name, continuously, for the first time.

⚠️ The `warm_typeahead` occupancy numbers this program has recorded before — LAT-P068's **26.2 %** of
slot-observations over 62 min, and this window's **35.0 %** of slot-seconds over its last 50 runs
(401.0 s of execution in a 573 s span) — both describe windows in which it *was* running. Neither
describes 04:35–04:50Z, when it ran zero times. **They must not be averaged, and they must not be
read as a standing property.** Summing per-task occupancy across count-capped samples with different
spans is exactly the scope error #1790 was filed for.

### 3c — 🔴 OPEN: something removes ~80 messages at a time without executing them

Across 44 ticks the queue rose at +7.65/min and fell five times in bursts of 37–86, while:

* no `warm_typeahead` start stamp moved,
* `warm_typeahead` never appeared in `active`,
* the two visible background slots were held continuously by other tasks.

A 2-slot worker cannot *execute* 80 tasks in under 20 seconds unless each takes ≤0.5 s, and if it
did, the start stamps would move. **So the leading candidate is now message LOSS rather than
consumption.** Candidates, none yet eliminated:

| # | candidate | how to eliminate it |
|---|---|---|
| L1 | **deploy restarts** — `task_acks_late` is unset (default `False`), so a *reserved* message is acked on delivery and destroyed by a restart | prefetch is 1 on a 2-slot pool, so a restart should cost ~2–4 messages, not 80. Partially supported: the 04:42:01 (−74) and 04:42:22 (−37) drops fall within ~35 s of release **v3855** (04:41:47Z) — but 04:37:08 (−86), 04:48:37 (−71) and 04:49:19 (−62) do not |
| L2 | **Redis eviction** — the instance reports `used_memory_human: 41.45M` and the policy is `allkeys-lru` | LRU evicts whole keys, not list elements, so evicting `background` would drop all 2,700 at once. Needs `INFO stats evicted_keys` sampled across a drop |
| L3 | **kombu's unacked-restore cycle** moving messages between the queue key and `unacked` | this ADDS to the list rather than removing; would have to be inverted to explain a drop |
| L4 | **real consumption by a worker whose starts are not recorded** | discriminated directly by `stats.total`, below |

**The discriminating test is registered and its instrument is unambiguous.** celery's
`stats.{worker}.total` is a per-worker cumulative count of tasks *executed*. Sample it alongside
`llen` across a drop:

* drop of N with a total-delta of ≈N → **consumption** (and L4 is the answer);
* drop of N with a total-delta of ≈0 → **loss**, and L1/L2 are the live candidates.

There is no third reading. A first run
(`docs/audits/latency/lat-p071-drop-discriminator.jsonl`, 04:51–05:03Z) is recorded but
**contaminated and not graded** — releases **v3855 (04:41:47Z)** and **v3856 (04:50:54Z)** both land
inside it, and every dyno restarted at 04:51:2xZ, which is L1's own signature. A clean deploy-free
run is owed.

### 3d — A near-miss, recorded because the next window would otherwise repeat it

At 04:53Z `/api/events/typeahead?q=lakers` returned **30.2 s, twice**, at the H12 ceiling. Given
that `warm_typeahead` — the warmer that exists to prevent exactly that (#1866) — had just been shown
not to have run in three hours, the causal story was sitting right there and was very nearly written
down.

**It was not a typeahead finding.** The control settled that in one call: `/api/health` was *also*
503 at 30.2 s, and v3856 had restarted every dyno ~2 minutes earlier. At t+30 s health was 200 with
`uptime_seconds: 299`. **A cold-start reading is not a latency finding** — and the only reason this
one did not become one is that the control was taken before the conclusion.

But that was the *first* attribution, and it was also wrong. See §3e.

### 3e — 🔴 The outage was MINE, and the endpoint is the defect

At 05:00Z the API went 503 again — **with the web dyno's uptime unbroken**, so this one was not a
restart. It stayed down about ten minutes. `/api/health` included. `heroku ps` said `web.1: up` the
entire time.

**I caused it, and the cause is a real product defect.** `GET /api/admin/celery-debug` calls
`celery_app.control.inspect(...)` **four times, inline, at `timeout=5`, inside an `async def`**.
`inspect` is a *broadcast*: it publishes to a control exchange and blocks until every worker replies
or the timeout expires. So a single request can hold the one uvicorn event loop for up to twenty
seconds — and I had **two samplers polling it at 20 s and 8 s**, which guaranteed the loop was never
free.

The proof is the recovery. Killing the two pollers (by pid — never `pkill -f`, which would hit every
lane) returned p50 to **0.227 / 0.235 / 0.229 / 0.240 s**, four consecutive calls, within 25 seconds,
with `uptime_seconds` climbing 683 → 759 across the recovery. Nothing restarted. **The dyno was never
unhealthy; the loop was never free.**

Three things follow, and they are not the same size:

1. **This is a live P1 in its own right, independent of my having triggered it.** Any
   auto-refreshing admin dashboard tab, or two operators with the page open, can black out the
   production API. Nothing about the endpoint signals danger — it is read-only, has no writes, and
   is not even behind the destructive-secret guard. Fixed on this branch (`c6f9a571`): off-loop via
   `run_in_threadpool`, single-flighted, and memoised for 5 s with the cache state disclosed. Until
   that deploys after 17:01Z, **the mitigation is operational — do not poll it faster than 1/30 s.**
2. **Some of this window's readings are contaminated, and are marked so** — the drop-discriminator
   run (0 usable ticks) and the 04:53Z typeahead numbers (void). The depth and `active` readings from
   the 04:35–04:50Z sampler are kept, because they returned 200 and are internally consistent; but
   they were taken while the sampler was itself load on the thing it measured, and that is now part
   of their provenance.
3. **The instrument was part of the phenomenon.** The program is measuring why scheduled work does
   not get a slot, using an endpoint that consumes the web dyno's only loop to ask. That is worth
   stating in the doctrine, not just in a fix.

### 3b — Arrival share, recomputed from the live schedule

```
BACKGROUND — 8.33 msg/min (12,000/day) across 102 entries
  6.00/min  72.0%  warm_typeahead                       interval    10 s
  0.50/min   6.0%  precompute_discover_candidate_base   interval   120 s
  0.33/min   4.0%  refresh_open_commentary              interval   180 s
  0.20/min   2.4%  warm_event_concepts                  interval   300 s
REALTIME    9.67 msg/min      HEAVY  0.19 msg/min (277/day)
```

LAT-P066 measured 74.2 % for `warm_typeahead` on 08-18 by the same arithmetic; 72.0 % today. Stable,
and **not a new finding — it is the input to one.** What was missing was the service side.

### 3c — The three quantities, and why only the third answers the question

The program has now measured all three, and they are not the same resource:

| quantity | who measured it | `warm_typeahead` | what it predicts |
|---|---|---|---|
| **arrival share** (depth) | LAT-P066 | 74.2 % | how fast the number in #1609's title grows |
| **slot occupancy** (a share of sightings) | LAT-P068 | 26.2 % | who you see when you look |
| **slot-seconds** (offered load) | **LAT-P071** | **35.0 % of a 2-slot pool** | **whether the delay is bounded** |

Depth and occupancy are symptoms. **Only offered load decides whether a queue is stable, and only
stability decides whether a message ever starts.** #1609's headline metric is depth — the one that
responds to the cheapest non-curative change.

---

## §4 — The general defect: a gate on the wrong side of the queue

`warm_typeahead` fires every 10 s, and ~82 % of its fires decide in 10 milliseconds that there is
nothing to do. That decision is cheap. **Reaching it is not** — the message must first be published,
queued behind ~2,700 others, and handed a slot, and the slot is the scarce resource in this system.

The same shape appears three more times in this tree, which is what makes it a class:

- **`poll_all_odds`** — `should_poll_now()` declines *after* delivery. Documented in
  `schedule_adherence.py`'s own docstring, where it caused a two-month misreading of the fire rate.
- **`refresh_hub`** — a single-flight lock with `REFRESH_LOCK_TTL = 120` seconds. See §5b.
- **every self-gating beat** whose `starts` counter is written from inside `_tracked_run`, i.e. after
  the gate. LAT-P039 already found that this makes an intentional skip indistinguishable from a beat
  that never fired.

**The clause:** *a gate inside the task cannot protect the queue. If the cheap answer is "no work",
the cheapness is spent on the wrong side of the bottleneck — the message has already been published,
already queued, and already put itself in front of somebody else's.* Cheap work is not free work when
the scarce resource is the slot rather than the CPU.

This is deliberately **not** a proposal to revert the 10-second beat. LAT-P062 set it, it killed the
`{30,60}` quantisation and improved the tail 12.5 %, and the standing queue refuses the revert. The
remedies this clause points at are on the *publish* side, and are registered as predictions in §7 —
not shipped, because shipping a partial fix against an open p1's symptom is how a p1 gets quietly
downgraded.

---

## §5 — Two directive premises that did not survive measurement

### 5a — `refresh_hub` is a victim, not a contributor

> *"refresh_hub's background queue is 3,846 deep and ran ONCE in 24 hours."*

The depth is real; the attribution is not. **3,846 is the background queue's TOTAL depth**, shared by
102 beat entries. `refresh_hub`'s own contribution is negligible: **4 starts in 24 h**, and its last
50 runs span **548,939 s (6.4 days)** — 1.6 s mean. It appears in **zero** of the 20 consecutive
head-samples taken this window. It is one of the tasks *waiting behind* `warm_typeahead`, not one of
the tasks putting anything there.

Corrected: `refresh_hub` belongs in the no-start class as a **casualty**, and its own scheduling is
not the defect.

### 5b — But its amplifier is real, and latent

`_schedule_refresh` takes a single-flight lock with **`REFRESH_LOCK_TTL = 120` seconds** and
dispatches one rebuild. If that message does not *start* within 120 s the lock expires and the next
reader dispatches another one.

**The guard is a function of wall time; the thing it guards is a function of queue position.** Once
publish→start lag exceeds 120 s — and this window measured lags of **123 minutes** — single-flight
degrades to no-flight, and the dispatch rate becomes (hub readers ÷ 120 s) with no bound.

**It is not firing.** 4 starts in 24 h means at most a handful of cache-miss bursts; overnight hub
traffic is too low to drive it. So this is registered as a **prediction, not a finding** (§7, P2),
and it is the third instance this program has found of the same underlying error — a timeout chosen
against an assumed duration, in a system where the duration is now unbounded.

### 5c — The calibration producer is not in this class

> *"the calibration producer (starts_24h 19/24) … its START rate is a saturation property."*

Measured 04:47Z: **25 deliveries against 23.26 scheduled — ratio 1.07, verdict `on_schedule`.**
It starts fine. What it does not do is finish:

```
successes_24h 0 · failures_24h 23 · consecutive_failures 115
last_success_at   2026-08-14T00:16:08Z        (five days ago)
last_failure_at   2026-08-19T02:32:54Z
last_verdict      partial / StagedFuturesIncomplete
last_result_summary  "futures generation incomplete — units banked, nothing published"
```

That is the known second blocker behind #1680's budget fix (units bank; publish still refuses), and
it is a build-side defect, not a saturation one. **Directive item 4's framing would spend protected-
tenant reasoning on the wrong side of the producer's problem.** Its start rate does not need
protecting today; when the `-70` fix lands and it begins publishing again, its *duration* becomes a
pool question — a ~20-minute task on a 2-slot pool — and that is the point at which the tenancy
model matters.

---

## §6 — What shipped

Two commits, both behind the fence.

1. **`58267ed9` — the stamp arm.** Grades the 33 structurally-blind beats on `last_success_at` /
   `last_failure_at` / `last_started_at` instead of on counters, generalising T5 protocol §§3/6 from
   one task to all of them. A stamp is a moment: it carries its own age and needs no window, so the
   TTL that defeats the rate arm has no purchase on it. `STAMP_LATE_TOLERANCE = 2.0`, not 1.0,
   because a punctual daily beat sits at 0.99× its interval every cycle and a 1.0 threshold would
   replace one cadence-equals-threshold bug with another. No stamp at all stays `unmeasurable`, never
   `missing` — a beat never observed is not a beat that stopped. `arm_counts` reports the two arms
   separately so a stamp-arm pass cannot be read with a rate-arm pass's confidence.

2. **`e6da3a45` — the two-ended queue census.** `celery-debug` sampled `lrange(q, 0, 19)` under the
   comment "see what's piled up"; verified against the installed kombu, that is the **newest**
   twenty. The messages a starved beat waits behind were never once read. Adds both ends, plus
   `coverage` — a census that cannot say how much it saw is an anecdote with a total attached.

12 mutations across the two, all caught — **after two rounds that found three real gaps in my own
tests** (an ahead-drift guard duplicated in two places so deleting either was invisible; a uniform
fixture that could not tell the head of a slice from its tail; a coverage boundary no test sat on).

**Owed, and named:** the census's first production read. It deploys behind the 17:01Z fence, so the
oldest-end composition — the direct evidence for who the backlog is *made* of — could not be
collected in this window. §3's evidence is the arrival end plus publish-rate arithmetic, which agree
with each other but are not the same measurement.

---

## §7 — Registered predictions (nothing here is shipped)

Registered before the next window opens, so they cannot be scored after the fact.

- **P1 — the oldest end is `warm_typeahead`-dominated.** On the first post-fence read of
  `/celery/queue-census?queue=background&cap=2000`, `oldest_end` is ≥ 60 % `app.tasks.warm_typeahead`
  and `next_to_be_served` is `app.tasks.warm_typeahead`. **Refuted if** the oldest end is materially
  more diverse than the newest end — which would mean the wall is *not* what a starved beat waits
  behind, and §0's answer is wrong.
- **P2 — the `refresh_hub` amplifier fires under daytime load.** During a US-daytime hour with
  background depth > 1,000, `refresh_hub` `starts_24h` grows faster than the number of distinct hub
  slugs, i.e. duplicate dispatches per slug. **Refuted if** starts stay ≈ one per slug per TTL.
- **P3 — `expires` on the warmer beat is a depth cure and not a start cure.** If ruling 050's
  registered `"expires": 30` ever ships, background depth falls below 200 within 2 h **and**
  publish→start lag for a 6-hourly beat is unchanged (still > 30 min). The messages it discards are
  the ones that were costing 10 ms each; the slot-seconds are in the ~18 % that rebuild.
  **This is the prediction that decides whether depth-reduction work is worth doing at all.**

## §8 — Instruments and their limits

| instrument | what it answers | limit |
|---|---|---|
| `/celery/schedule-adherence` | did it run as often as scheduled | rate arm blind above 12 h (33 beats); request-dispatched tasks invisible entirely; `deliveries` counts retries (#1802) |
| `task-metrics?task=X` | stamps + duration sample | 59 of 101 tasks answer `no_data` under their own name (#1800); duration sample is count-capped, so its span differs per task (#1790) |
| `celery-debug` | depth + newest-20 + active set | wrong end of the list; 20 of 2,842 |
| **`/celery/queue-census`** (new) | both ends, with coverage | not yet deployed |
| `lat-p071-no-start-sampler.jsonl` | depth trend + occupancy | 20 s resolution — a burst shorter than a tick is invisible |
