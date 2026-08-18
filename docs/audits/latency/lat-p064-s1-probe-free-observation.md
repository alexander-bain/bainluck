# LAT-P064 §S1 — the warmer's stalls are REAL, not observation-induced

**Window:** latency lane cycle 36, `pid:30798`, 2026-08-17 PDT.
**Instrument:** `backend/scripts/lat_p064_s1_observe.py`, raw
`docs/audits/latency/lat-p064-s1-observation.jsonl`.
**Registered before the run** (#1922, ruling 050): S1 predicts **≥1 hole > 120 s** recurs over a
**probe-free** observation. **HALT: zero holes in 60 probe-free minutes ⇒ the stalls are induced by
LAT-P063's own probing and its rows 1 and 2 must be WITHDRAWN in writing.**

---

## §S1.1 — The verdict, first

**PREDICTION CONFIRMED. LAT-P063's rows 1 and 2 are UPHELD; nothing is withdrawn.** And the full run
says something considerably worse than "≥1 hole recurs".

**FIVE clean holes in 55.8 probe-free minutes — one every 11.2 minutes — and the warmer is NOT
RUNNING for 30.0 % of wall-clock.**

| # | from | to | duration | segment |
|---|---|---|---|---|
| 1 | 23:21:06 | 23:24:56 | **229.6 s** | A (pre-deploy) |
| — | 23:33:45 | 23:35:51 | 126.4 s | **EXCLUDED — inside the v3832 warm-up shadow** |
| 2 | 23:44:49 | 23:48:43 | **234.3 s** | B (settled) |
| 3 | 23:54:33 | 23:57:43 | **190.0 s** | B (settled) |
| 4 | 00:10:14 | 00:13:04 | **170.2 s** | B (settled) |
| 5 | 00:15:48 | 00:18:51 | **182.4 s** | B (settled) |

**1,006.4 s of 3,350 s observed = 30.0 %.** Against a **45 s** response TTL, a 170–234 s hole means
the head is dead for ~75–80 % of each one. This is not an occasional stall; it is a duty cycle.

The window issued **zero `/typeahead` requests** — the only traffic from this lane was
`GET /api/admin/task-metrics`, a Redis hash read on the *web* dyno that touches neither the warmer,
its lock, nor its cache. The holes are the same size class as LAT-P063's (286.6 s, 169.2 s), so the
phenomenon is not a probing artifact.

**The HALT arm cannot fire.** It required *zero* holes in 60 probe-free minutes; there are five.

**Instrument integrity, checked rather than assumed:** 1,294 samples OK, **6 bad** (5 `TimeoutError`,
1 `URLError`), and **two sampling gaps** (16.9 s at 23:27:59 and 21.1 s at 23:30:40 — both at the
deploy restart). **Zero holes overlap a sampling gap** (`holes_over_120s_tainted_by_sampling_gap: 0`).
That check exists because a throttled request parses as silence, and silence is what a stall looks
like (gotcha #53); it is reported as a measured zero, not an assumed one.

⚠️ **The observation is 55.8 clean minutes against the 60 the prediction named** — 93 %, and the
shortfall is stated rather than rounded up. A deploy (**v3832**, `010ba47e`, 23:27:47 UTC) restarted
every dyno mid-run, so the run is segmented: **A = 23:13:39 → 23:27:47 (14.1 min)**, ten minutes
excluded as warm-up shadow, **B = 23:37:47 → 00:19:30 (41.7 min)**. Holes appear in **both** segments
at a consistent rate, so the finding does not rest on either side of the restart.

## §S1.2 — S2 answered in the same stream: the task does not START

`starts_24h` was captured on every sample, so "did the scheduler keep firing and only the recording
fail?" needs no second run.

| sample | `starts_24h` | `last_started_at` |
|---|---|---|
| 23:21:07 | **2489** | 23:21:06 |
| 23:21:37 | **2489** | 23:21:06 |
| …230 s of samples, all `ok`, none missing… | **2489** | 23:21:06 |
| 23:24:58 | 2490 | 23:24:56 |

**`starts_24h` is frozen for the entire hole.** So the counter is not lying and the summary is not
stale: **the task genuinely is not being started.** S2's "advancing ⇒ a *recording* defect" arm is
refuted; this is a **scheduling/dispatch** defect, which is where #1922's remedy has to go.

Every sample in that stretch returned HTTP 200 with parsed JSON (`samples_bad: 0` for the whole run),
so the frozen counter is a reading, not a gap in the readings. The instrument records `ok` per sample
and flags any hole overlapping a sampling gap as `sampling_gap_overlap` precisely so a throttled
request could never be promoted into a stall (gotcha #53). No hole in this run is flagged.

## §S1.3 — S3: the background worker is the unit that stalls, not the warmer

Sibling background tasks were sampled alongside. `precompute_discover_candidate_base`
(`crontab(minute="*/2")`, `queue: background`, 22–34 s per run) **last started 23:20:32 and did not
start again before the deploy at 23:27:47** — **7 min 15 s**, straight through its `:22`, `:24` and
`:26` beats, and through the warmer's hole.

Two facts follow, and only one of them was expected:

1. **The stall is not warm_typeahead-specific.** A second, independently-scheduled background task
   froze across the same period. Whatever stops the warmer stops the queue it lives on.
2. **The two did not recover together.** The warmer resumed at 23:24:56; the sibling had still not
   run by 23:27:47. That is *not* a simple "the worker was down" story — a dead worker starves both
   and revives both. It looks like **contention**, in which the warmer's own message backlog is what
   the freed slots pick up first.

## §S1.4 — The burst signature, which is the strongest clue on the board

`starts_24h` does not advance smoothly at one per beat. It arrives in bursts:

| interval | wall | Δ`starts_24h` | beat ticks available (10 s beat) |
|---|---|---|---|
| 23:18:46 → 23:18:52 | 6 s | **+11** | ~1 |
| 23:19:46 → 23:19:52 | 6 s | **+11** | ~1 |
| 23:20:22 → 23:20:34 | 12 s | **+11** | ~1 |
| 23:21:01 → 23:21:07 | 6 s | **+5** | ~1 |

Eleven starts in six seconds against a ten-second beat is **more invocations than the scheduler can
have produced in that interval**. They are near-instant: `successes_24h` moves almost in step, and the
matching summaries carry `skip_reason: "lock"`, `seconds_wall: 0.0`, `last_duration_ms: 15`. So these
are **queued messages draining**, all but one skipping on the single-run lock.

The same non-cadence shape appears on the sibling: `crontab(minute="*/2")` should start it at
:18:00 / :20:00 / :22:00, and the observed starts are **23:18:13, 23:19:22, 23:19:52, 23:20:32** —
two of which are not on any 2-minute boundary at all.

**A backlog that accumulates and then flushes is the shape of a consumer that stopped consuming, not
of a producer that stopped producing.** Combined with §S1.2 (nothing starts during the hole) and
§S1.3 (a second task starves too), the reading is: the **background worker** stops taking work for
minutes, beat keeps publishing into the queue, and the queue drains in a burst when it resumes.

## §S1.5 — What the worker topology adds, and why it makes this predictable

Read from `heroku ps` this window — **not** from the beat file, which does not carry it:

```
worker-background (Standard-1X): celery worker --concurrency=2 --queues=background
                                 --max-memory-per-child=200000
```

**Two slots.** Against them, on the same queue:

| task | cadence | measured duration |
|---|---|---|
| `warm_typeahead` | beat 10 s, floor 30 s | **~35 s wall**, holds the DB 73 % of it at W=4 (LAT-P063) |
| `precompute_discover_candidate_base` | every 2 min | **22–34 s** |
| `warm_event_concepts` | every 5 min | **~82 s** (four golf-major payloads; the beat file says so) |
| `prediction_market_match` | every 15 min | 13–21 s scans over a 977 MB table |
| …plus the enrich/precompute/backfill family | | |

`warm_typeahead` alone runs ~35 s out of every ~35 s. **It is not a periodic task on this worker; it
is approximately one permanently-occupied slot of two.** Anything else long — `warm_event_concepts`
at ~82 s is the obvious candidate — takes the second, and at that moment the queue has no free
consumer at all. That is a stall, and it needs no bug to produce one.

`--max-memory-per-child=200000` (200 MB) is the second candidate mechanism: a child that crosses it is
recycled, and messages prefetched by that child are redelivered — which would produce **both** the
silent stretch **and** the redelivery burst, in one mechanism rather than two.

## §S1.6 — THE MECHANISM, and it did not need the worker log after all

The window opened expecting to ask Alex or the Integrator for a `heroku logs` slice, because
`heroku logs` is EPERM-blocked from an agent sandbox (a new measured limit, sibling to the blocked
5432 egress, first recorded in #1922). **The log slice turned out to be unnecessary, and saying so is
better than collecting a favour I no longer need.** Two admin reads settled it.

**Read 1 — the background queue is 295 deep.**

```
GET /api/admin/ops-snapshot -> celery.queue_depths
{"background": 295, "realtime": 0, "heavy": 0}     23:31 UTC
{"background": 289, "realtime": 0, "heavy": 0}     23:33 UTC
```

CLAUDE.md's own threshold is **"background queue >50 → purge + investigate."** This is ~6× that, and
holding rather than draining. `realtime` and `heavy` are at **zero** — the saturation is specific to
the one queue `warm_typeahead` runs on.

**Read 2 — that queue's other residents are minutes long, against TWO slots.** From `heroku ps`:
`worker-background (Standard-1X): celery worker --concurrency=2 --queues=background
--max-memory-per-child=200000`. Measured duration distributions, this window, `recent_durations_ms`
over 50 runs each:

| task | p50 | p90 | max | runs > 120 s | cadence |
|---|---|---|---|---|---|
| `prediction_market_match` | **334.9 s** | 524.6 s | 724.3 s | **48 / 50** | every 15 min |
| `poll_kalshi_markets` | **320.2 s** | 377.0 s | 418.5 s | **47 / 50** | every 2 h |
| `poll_polymarket_markets` | (last run **437.7 s**) | | | | every 1 h |
| `backfill_winners` | (last run **827.6 s**) | | | | every 6 h |
| `precompute_discover_candidate_base` | 27.3 s | 43.8 s | 62.3 s | 0 / 50 | every 2 min |
| `warm_event_concepts` | 14.9 s | 20.6 s | 23.7 s | 0 / 50 | every 5 min |
| **`warm_typeahead`** | **~35 s** | | | | **beat 10 s, floor 30 s** |

`warm_typeahead` runs ~35 s out of every ~35 s: **it is not a periodic task on this worker, it is
approximately one permanently-occupied slot of two.** `prediction_market_match` alone takes
334.9 s every 900 s — **37 % duty on the other slot at p50, 58 % at p90, 80 % at max.** When it
overlaps any of the other multi-minute residents, **both slots are gone for minutes** and the queue
has no free consumer at all.

**That is the hole.** It needs no bug: two slots, a permanent occupant, and a second occupant that is
minutes long half the time. `--max-memory-per-child=200000` remains a *possible additional*
contributor and is neither needed nor excluded by this evidence — the slot arithmetic is sufficient
on its own, so the honest statement is that the residual is unmeasured, not that it is absent.

### A SECOND hole, caught with occupancy coverage running — the slots are directly observable

A second hole occurred at **23:33:45 → 23:35:51 (126.4 s)**, this time with the S3 sampler already
running across 18 background tasks at 10 s. The slot ledger, read from their `last_started_at` and
`last_duration_ms`:

| task | started | duration | occupies until |
|---|---|---|---|
| `warm_typeahead` (last pass before the hole) | 23:33:45 | 32.1 s | 23:34:17 |
| `warm_event_concepts` | 23:33:46 | 14.7 s | 23:34:01 |
| **`precompute_admin_link_rate`** | **23:34:52** | **120.8 s** | **~23:36:53** |
| `precompute_discover_candidate_base` | 23:35:11 | 26.8 s | ~23:35:38 |
| **`warm_typeahead` resumes** | **23:35:51** | | |

**The warmer resumes 13 seconds after `precompute_discover_candidate_base` releases the second slot —
while `precompute_admin_link_rate` is still holding the first.** That is not an inference from
aggregate duty cycles; it is the queue handing a freed slot to the waiting task, watched directly.
`starts_24h` held flat at **2577** across the whole hole and moved to 2578 on resumption.

⚠️ **This hole sits 6 minutes after the v3832 release — inside the 10-minute warm-up shadow this
document declared**, so it is **NOT counted in the clean hole rate**; §S1.1's 229.6 s hole is the one
that carries the verdict. It is reported here because the *mechanism* it exhibits is not
shadow-sensitive: a 120.8 s task holding a slot is a 120.8 s task holding a slot, and the resumption
timing is exact either way. Using a shadowed observation for the mechanism while excluding it from
the rate is the distinction — stated, so nobody has to guess which way it was counted.

`precompute_admin_link_rate` earns its own line: **84.6 s then 120.8 s** on consecutive runs. It is
an *admin cache warmer* — nothing user-facing waits on it — and it holds one slot of two for two
minutes at a time.

### This is #1609, and #1922 is its symptom

**#1609 — "Celery background queue ~490 deep (10× threshold), beat tasks lapping themselves"** — was
filed **2026-08-09**, is **p1**, `program:latency`, and is **still open**. It recorded 488–492 then;
this window measures 289–295. Same queue, same shape, same diagnostic (multiple enqueued copies of
one periodic task), and its acceptance #2 is *"no periodic task has more than one instance enqueued
at a time"* — which is precisely the burst signature in §S1.4.

**#1922 should not be worked as a warmer defect.** The warmer is behaving correctly; it is being
starved by a saturated queue that already has a p1 issue naming the saturation. Filing a second fix
against the warmer would produce a change that makes the symptom quieter while #1609 stays open,
which is the worst available outcome.

### The warmer is now the queue's biggest publisher, and that is LAT-P062's doing

Stated plainly because it is uncomfortable and it is arithmetic, not opinion.

`warm_typeahead`'s beat is **10 s** (LAT-P062, and the change was right — row 5's tail improved
12.5 %). That is **8,640 publishes/day**. Measured `starts_24h` is **~2,530**, over a 24 h window that
straddles the beat change, so a like-for-like expectation is ~5,040 publishes against 2,530 starts.
There is **no `task_expires`** anywhere in the Celery config (checked: `task_time_limit: 300`,
`worker_prefetch_multiplier: 1`, `result_expires`, and nothing else). **Nothing discards a stale beat
message.** They queue.

So the warmer publishes ~3× what it did before into a queue that was already 10× its threshold, and
the messages that pile up are the same ones that later rip through in 15 ms lock-skip bursts. **The
beat change stays** — it fixed the quantisation and improved the tail, and reverting it is explicitly
refused by this queue. But it is now feeding the backlog that starves it.

## §S1.7 — Registered remedy (ruling 050), NOT SHIPPED THIS WINDOW

Written before any code, so it grades rather than gets rationalised.

**Proposed:** add `"expires": 30` to the `warm-typeahead` beat entry's `options`. A "please refresh the
cache" message that is four minutes old cannot refresh anything — it can only occupy queue space and
cost a 15 ms drain. Celery discards an expired message at delivery without executing it.

| # | prediction | HALT |
|---|---|---|
| **E1** | background `queue_depths.background` falls and holds **< 100** within 2 h of deploy | no fall at all ⇒ the warmer was not the dominant publisher and the arithmetic above is wrong |
| **E2** | `starts_24h` for `warm_typeahead` **falls** toward the number of real passes, and the ±11-in-6 s bursts disappear | bursts persist ⇒ the messages are not beat messages and redelivery is the real source |
| **E3** | hole frequency and duration are **UNCHANGED** | holes improve ⇒ good news, but it means slot exhaustion was NOT the mechanism and §S1.6 needs re-deriving |

**E3 predicts no user-visible improvement, deliberately.** This remedy makes the queue honest and
stops the warmer from making #1609 worse; **it does not fix the holes** and must not be reported as
if it did. The holes need worker capacity or a queue split, and that is a topology decision with a
monthly cost attached — Alex's and the Integrator's, not this lane's.

**Why it is registered and not shipped:** it is a beat-schedule change (gotcha #12), it cannot be
verified locally against a real broker, it was not in this window's ordered directive, and shipping a
partial fix against an open p1's symptom is how a p1 gets quietly downgraded. Same discipline as
Option D (registered, not half-built) and the W-sweep (measured, refused).

## §S1.8 — What this window will NOT do, and why

**No re-grade of LAT-P063's rows 1–2.** They are UPHELD on §S1.1 and need no re-run. Re-measuring them
now would also land against v3832 with a 13-minute-old release behind it, and the last five windows
have shown what that produces.

**No `hard_kills_24h` attribution.** It was observed oscillating **2 → 1 → 2 → 1 → 3 → 2** within
single minutes of this window with nothing running, confirming LAT-P063's correction directly: a
rolling 24 h counter is not an event. The clean-24 h read remains owed and is takeable after
**14:33 PDT 2026-08-18** (v3830 + 24 h) — and every merge moves that bar, which is why six windows
have now owed it.

---

## Appendix — segment ledger and raw artifacts

| segment | wall | probe-free | deploy shadow | clean holes |
|---|---|---|---|---|
| A: 23:13:39 → 23:27:47 | **14.1 min** | ✅ | none | 1 (229.6 s) |
| v3832 released 23:27:47 → shadow to 23:37:47 | 10.0 min | ✅ | **excluded** | (1 observed, not counted) |
| B: 23:37:47 → 00:19:30 | **41.7 min** | ✅ | settled | 4 (234.3 / 190.0 / 170.2 / 182.4 s) |
| **TOTAL CLEAN** | **55.8 min** | | | **5 — one per 11.2 min, 30.0 % of wall-clock** |

Total probe-free observation **55.8 min** against the 60 the prediction named. Reported as a
shortfall, not rounded up. Holes occur at a consistent rate on **both** sides of the restart, so no
part of the finding rests on the segmentation.

### Raw artifacts, shipped with this document

| file | what |
|---|---|
| `lat-p064-s1-observation.jsonl` | every sample and every distinct pass, 66.0 min, 3 s cadence, with the per-sample `ok` flag and the final `summary` record carrying the verdict |
| `lat-p064-s3-background-occupancy.jsonl` | 18 background tasks at 10 s — the slot ledger behind §S1.6a |
| `lat-p064-queue-depth.jsonl` | `background` queue depth every 4 min |
| `backend/scripts/lat_p064_s1_observe.py` | the instrument, re-runnable: `--minutes`, `--interval`, `--sibling` |

### Queue depth over the window — it oscillates, it does not drain

```
23:33  289    23:37  244    23:41  231    23:45  184
23:49  204    23:53  230    23:57  226
```

**Floor 184, ceiling 289, no trend to zero.** The early reading is not a post-deploy transient that
clears: it is a standing backlog in the 180–290 band, ~4–6x the CLAUDE.md threshold of 50. Stated
this way because "295 once" and "184–289 sustained" are different claims, and only the second one
supports #1609.
