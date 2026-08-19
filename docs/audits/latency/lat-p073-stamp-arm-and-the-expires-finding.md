# LAT-P073 — the stamp-arm read, the `expires` finding, and the golf split in a settled regime

Cycle 45. Branch `program/latency-66`, base `bac5fce7`. All production reads
2026-08-19T23:30–23:50Z, deployed commit `bac5fce7` (`/api/health`), dyno uptime 3.5 h at first
read — well outside the ~5 min post-deploy taint window.

**Fable's LAT-P073, four items.** Item 1 (start the 24 h stamp-arm read) is §1–§2. Item 2 (the gate
PLAN) is its own document. Items 3 and 4 (the settled-regime db/app re-read; golf probe grading
continues, router verdict stands) are §6, taken on the same probe.

§3 is not in the directive. It is what the item-1 read found on the way past, and it is the largest
result in this window.

---

## 1. Item 1 — the stamp arm is LIVE, and the no-start class is graded

Ruling (b) was correct: `-64` and `-65` are merged (`c289b62e`, `3bf70fd0`) and deployed.
`58267ed9` (the stamp arm, #1995) and `c6f9a571` (the `/celery-debug` blackout fix, #1994) are both
ancestors of `origin/master` and live. **The item-1 block is over and the read is started.**

**t0 = 2026-08-19T23:30:22Z.** First recorded series sample 23:36:43Z. Graded on
`GET /api/admin/celery/schedule-adherence`, **not** `celery-debug` — the endpoint is pure Redis
(`build_schedule_adherence` takes no celery broadcast), which is what makes it safe to sample at
all. Reading `celery-debug` for this is what took production down (#1994).

### The census, and why the headline number is not it

| | count |
|---|---|
| scheduled beat entries | **123** |
| graded | **106** |
| entries above the 12 h rate-arm ceiling (`WINDOW_COUNTER_TTL / MIN_EXPECTED_FIRES`) | **39** |
| — of those, **graded by the stamp arm** | **24** |
| — of those, still ungraded (`unmapped`) | **15** |

**All 24 stamp-armed entries graded `on_schedule`, every one of them on a `terminal` stamp** — not
a start stamp. So the class is not a no-start class at all: those beats start *and finish*.
`stamp_age_over_interval` spans 0.31–0.99, so the measure has real resolution and the verdict is
not vacuous — `sync_polymarket_resolved` sat at 0.99, one percent of its interval from flipping.

**The residual 15 is not a stamp-arm failure and does not belong to #1995.** They never reach either
arm: 12 report `no_metric_label_recorded` and 3 (all weekly) `label_recorded_but_no_metrics`.
Spot-checked `sync_rosters`, `audit_canonical_keys`, `calibration_sentinel` against
`/api/admin/celery/task-metrics/…` — all three return `{"status": "no_data"}`, which is **UNKNOWN,
not zero** (gotcha #53). **That is #1800's identifier-space split**, already open at p2, and it is
now sized: 15 entries, all above the ceiling, so #1800 is the last thing standing between this
surface and a fully-graded schedule.

### One instrument caveat, found by building the reader

`arm_counts.rate_arm_blind_total` reads **24**, and `_arm_counts`' own docstring says it "does not
move when the system is healthy" and cites 33 measured on 2026-08-19. Both are true and the number
still misleads: it counts only entries that reached `graded`, so **an entry that falls out of
`graded` into `unmapped` silently decreases it.** The headline improves because the instrument went
blinder.

Observed live inside this window: between 23:30:22Z and 23:36:43Z the stamp-armed count moved
29 → 28 (`sync_polymarket_resolved`'s counter aged into the rate arm) while the above-ceiling census
held at **39 in both reads**. The census is the stable quantity; the headline is not.
`backend/scripts/stamp_arm_read.py` reports `above_ceiling_total` for exactly this reason.

---

## 2. The 24 h read — started, running, and handed forward with its clock

A 24 h read does not fit in one window, so it was made to outlive it.

- **Instrument:** `backend/scripts/stamp_arm_read.py` (stdlib only, no repo imports, no DB). Takes
  one read, appends a compact record to a JSONL series, and `--grade` reduces the whole series.
- **Live series (the sampler appends here):** `/tmp/lat-p073-stamp-arm-series.jsonl`.
- **Committed snapshot (what existed at handoff):**
  `docs/audits/latency/lat-p073-stamp-arm-series.jsonl`. Two paths on purpose — a file the sampler
  appends to every 5 minutes cannot live in the worktree, or the tree is never clean and the lane
  can never hand off. **The successor grades the `/tmp` file** and commits a fresh snapshot.
- **Sampler:** detached `nohup` loop, 5 min cadence, 25 h budget, started 23:36Z. Restarted 23:56Z
  onto the `/tmp` path (same series, copied forward — no samples lost).
- **t0 = 2026-08-19T23:30:22Z. The grade is due after 2026-08-20T23:30Z.**
- ⚠️ **If `/tmp` has been cleared, the series is gone and the grade restarts** — say so rather than
  grading a truncated window, and re-run from a fresh t0. A short series honestly labelled beats a
  24 h claim resting on 4 samples.

**What the 24 h buys, stated so the successor does not re-take a read that is already taken.** A
stamp is a moment and carries its own age, so a *single* read already grades the class — §1 is that
grade and it is complete. The series answers the different question: **did any of the 24 flip?**
Run `python3 backend/scripts/stamp_arm_read.py --grade docs/audits/latency/lat-p073-stamp-arm-series.jsonl`
and read `stamp_tasks_ever_not_on_schedule` (must be empty) and `above_ceiling_stable` (must be
true; if the census moved, say which way and why — up is a new slow beat, **down is an entry that
stopped being graded at all, which reads as an improvement and is not one**).

---

## 3. 🔴 THE FINDING — `expires` is discarding 60–75 % of four beats' messages, and the health surface calls it `behind`

Not in the directive. Found while establishing item 1's baseline, and it is the largest result here.

### What was observed

`warm_typeahead` grades `overruns` at **ratio 0.40** — 858 deliveries against 2,132 scheduled fires
in 21,322 s. That is **2.41 executions/min against a nominal 6.00/min beat.** Three other beats read
`behind` at 0.25–0.29.

`record_task_delivery` is wired to celery's **`task_prerun`** (`tasks/redis_state.py`), so
`deliveries` counts *executions*, not publishes. Something removes ~60 % of the messages before any
body runs.

### The control that names it

The candidate causes were: the beat not firing, list backlog, worker starvation, and `expires`.

| observation | rules out |
|---|---|
| `poll_all_odds` (30 s beat) reads **1.00**; every non-expiring beat reads **0.99–1.00** | the beat process is fine |
| `queue-census` on `background`: depth **0, 2, 2** over 40 s | list backlog |
| `poll_live_prediction_markets` — p95 **81.6 s**, *longer* than `warm_typeahead`'s 44.6 s, no `expires` — reads **0.99** | "long tasks fall behind" |
| `starts` == `deliveries` exactly (858/858); `terminals` 855 | loss after prerun; crashes |

And the correspondence itself, across **72 rate-armed entries carrying a ratio**:

> **The set of beats reading `ratio < 0.6` is EXACTLY the set carrying `expires`. 4 of 4, both
> directions, zero false positives, zero false negatives — replicated on two independent reads
> 7 minutes apart.**

| beat | `expires` | interval | ratio t0 | ratio t1 | p95 |
|---|---|---|---|---|---|
| `warm_typeahead` | 10 s | 10 s | 0.40 | 0.39 | 44.6 s |
| `precompute_discover_candidate_base` | 120 s | 120 s | 0.25 | 0.26 | 18.7 s |
| `refresh_open_commentary` | 180 s | 180 s | 0.27 | 0.28 | 5.6 s |
| `warm_event_concepts` | 300 s | 300 s | 0.29 | 0.30 | 49.9 s |

`_EXPIRING_WARMER_BEATS` (`tasks/__init__.py`) sets `expires` to exactly one beat period on these
four and on no others.

### The mechanism, and why it is self-reinforcing

`llen` is 0–2, so the messages are not waiting in the Redis list — they are in the **worker's
prefetch buffer**, reserved and unacked, waiting for a free slot. `expires` is evaluated when the
worker picks the message up, so a message that waits longer than one beat period for a slot is
discarded without executing.

The four beats carrying `expires` are, with `poll_live_prediction_markets`, the longest-running
things on the `background` pool. **They expire each other's messages, and their own.**

### Two consequences

1. **The adherence surface is misattributing.** `behind` means "not running as often as scheduled" —
   a scheduler verdict — for what is a delivery policy working exactly as designed. This is the
   same shape as LAT-P043's `poll_all_odds` discovery (a task's own self-gate read as a scheduler
   failure) and gotcha #53's (a decision not to work, read as work that did not happen). Filed
   separately; the fix is a distinct verdict, not a re-tuned threshold.
2. **It changes the gate's payoff and it is the redesign #1996 needs.** See §4.

### What this does NOT establish

That expiry is the cause is inference from a 4/4 cross-sectional correspondence plus four excluded
alternatives — **not a directly observed expiry event.** No instrument in this tree counts publishes
or revocations, which is precisely #1996's gap. The honest status is: *the strongest available
evidence, one instrument short of proof.* §4 says what that instrument is.

---

## 4. #1996 — the hold is RESTATED, and the redesign now has a specification

Fable's ruling (d): the discriminator has two branches over a three-valued world, `expires: 10`
discard is byte-identical to LOSS, so it cannot return a correct verdict as designed. **#1996 stays
held. It was not run this window.**

What §3 adds is that the third value is no longer hypothetical — it is **measured, large, and
localised to four named beats** — and that the redesign does not need to catch a drop in flight:

1. **A publish counter in `is_due()`.** The only place a publish is observable. Gives the
   discriminator the numerator it has never had, and grades the gate's own P2.
2. **A revocation/expiry counter** — celery's `task-revoked` with `expired=True`, or the worker's
   `expired` stat — sampled beside `llen` and `stats.total`. This is the third arm, and §3 makes it
   a *known-positive* test rather than a fishing expedition: it should fire ~3.6/min on
   `warm_typeahead` alone. **An instrument that reads zero there is broken, not reassuring.**
3. **Then** the discriminator, in a deploy-free window.

The cross-sectional control in §3 is itself a better instrument than the original design, because
it needs no drop to occur: it compares matched populations that differ only in `expires`.

---

## 5. #1866 — the wall-to-TTL gap is 0.4 s, not 2.4 s

Fable's ruling (c) promoted LAT-P072's MARGINAL finding onto #1866. This read **sharpens it, in the
bad direction.**

`warm_typeahead`'s `p95_duration_ms` is **44,614 ms = 44.6 s**, against the `/typeahead` response
cache TTL of **45 s**. `typeahead_beat_budget.MEASURED_WALL_MAX_S` records the worst measured wall
as **42.6 s**, from 20 LAT-P062/P063 passes.

The p95 is over a *mixed* distribution — real passes plus 10 ms no-ops — and no-ops only drag a
percentile **down**. So 44.6 s is a **lower bound** on the real-pass p95, and the true worst wall is
higher still.

- **The gap Fable cited as 2.4 s is at most 0.4 s, and is probably negative.**
- `P(10) = 10 * ceil(44.6/10) = 50 s` — over the cliff, at p95 rather than at the extreme.
- LAT-P063 measured 20 passes for 20: **every** period over 45 s lost cached entries.

**`MEASURED_WALL_MAX_S = 42.6` is now known to be an underestimate.** It was **deliberately not
changed** in this window: the replacement must come from a clean pass-only measurement, not from a
percentile over a mixed distribution, and substituting one for the other is precisely the
projected-vs-measured trap that module's docstring exists to prevent. Registered as owed on #1866,
with the constant left honest about its provenance rather than quietly tightened.

The instrument that would settle it is the same one §6 of the plan doc blocks on: the warmer's own
pass result, which already reports `seconds_wall` and `period_s` per pass and is readable by nobody.

---

## 6. Items 3 and 4 — the golf split re-read in a settled regime; the router verdict stands

**Vacuum regime, checked first (`pg_stat_user_tables`, 23:33Z).** `futures_outcomes` (3,556,314 live
tuples, the hottest table on this read path) last autoanalyzed **22:00:44Z — 93 minutes before the
first read**, against LAT-P072's **4 minutes**. `futures_markets` 62 min, `events` 46 min. This is
the settled regime Fable asked for.

**Method, identical to LAT-P072 §4** so the two are comparable: 12 reads of
`/api/golf/tournaments/{slug}`, two slugs (`bmw-championship` q=12, `nexo-championship` q=9),
23:37–23:39Z, shares of `edge = router_queue + wall` computed in one place.

| regime | n | edge median | db % | app % | router % |
|---|---|---|---|---|---|
| LAT-P072 WARM (4 min after autoanalyze) | 11 | 923.2 ms | 62.73 | **37.09** | 0.22 |
| **LAT-P073 ALL (93 min after)** | **12** | **1900.7 ms** | **82.08** | **17.78** | **0.120** |
| LAT-P073 first-read of each slug | 2 | 3544.2 ms | 86.43 | 13.50 | 0.067 |
| LAT-P073 subsequent | 10 | 1748.7 ms | 82.06 | 17.78 | 0.134 |

### ✅ Item 4 — the router verdict stands, CONFIRMED again

**0.047–0.382 % of edge, 1.7–2.9 ms absolute, on all 12 reads.** HALT (router > 30 %) is nowhere
near — three orders of magnitude away. #1917's premise that the router is a meaningful term in this
endpoint is refuted a second time, in a second statistics regime, exactly as Fable's ruling stated.

### ⚠️ Item 3 — the share prediction now passes, and that is the *less* interesting half

Against LAT-P069's registered model (db > 70 %, app 10–25 %, router < 10 %): **all three now
CONFIRM.** db 82.1 % clears 70 %; app 17.78 % is inside 10–25 %; router is 0.12 %.

**But the app term did not shrink. The denominator grew.**

| | LAT-P072 warm | LAT-P073 settled |
|---|---|---|
| app **share** | 37.1 % | 17.8 % |
| app **absolute, median** | ~340 ms | **306.8 ms** |
| edge median | 923.2 ms | 1900.7 ms |

The share halved because the page got **2.06× slower**, not because the app work went away.

### The finding: ~300 ms of app work that is invariant to the database

Across the 12 reads, `db` swings **10.6×** (383.8 → 4060.1 ms) while `app` moves **2.4×**
(209.0 → 508.4 ms):

- **Pearson r(db, app) = +0.133** — the app term does not track database time.
- **Pearson r(q, app) = +0.236** — nor query count.
- app mean 329.8 ms, **CV 0.35**, against db CV 0.56.
- The floor is hard: the *cheapest* read of the whole set (`nexo`, db 383.8 ms, wall 600 ms) still
  spent **216.3 ms** in app.

**Fable's condition was "the golf-page thread to pull if it reproduces". It reproduces** — and the
settled-regime read is *stronger* evidence than the share ever was: a term that holds ~300 ms while
the database underneath it varies tenfold is fixed serialised work, not something proportional to
the data. Filed as its own issue, as the queue directed.

Per-slug medians (`bmw` q=12 → 390.9 ms; `nexo` q=9 → 234.6 ms) hint at a per-query app cost of
~50 ms, **but the distributions overlap almost entirely** (209–508 vs 216–492) at n=6 each, so that
is a hypothesis for the issue to test, not a result.

### One observation held back deliberately

The page is **2.06× slower** than LAT-P072 measured it 4 minutes after an autoanalyze. A tempting
reading is statistics decay on `futures_outcomes`. **It is not claimed**, because the two reads
differ in time of day (23:37Z vs 18:47Z), concurrent load and tournament state, and
`/api/admin/latency-stats` holds **1 sample** for this endpoint in the hour (it is not
always-sampled) so there is no independent baseline. Recorded as an observation with its
confounders named; settling it needs a paired read, not another single-armed one.

---

## 7. Instruments used, and what each could not answer

| instrument | used for | limit that bit |
|---|---|---|
| `GET /api/admin/celery/schedule-adherence` | §1, §2, §3 | `rate_arm_blind_total` shrinks when an entry goes `unmapped` (§1); `behind` misattributes `expires` (§3) |
| `GET /api/admin/celery/queue-census` | §3's backlog exclusion | `llen` is blind to the prefetch buffer, which is where §3 concludes the messages are |
| `GET /api/admin/celery/task-metrics/{t}` | §1's residual-15 spot check | `no_data` is UNKNOWN, not zero (#53) |
| `x-timing-split` on `/api/golf/tournaments/{slug}` | §6 | client-settable `X-Request-Start`; router and dyno clocks differ |
| `POST /api/admin/db-query` | §6's vacuum regime | none this window |
| `GET /api/admin/latency-stats` | §6's baseline attempt, §5's proxy check | **1 sample** for golf, **0** for typeahead — only `/api/feed` is always-sampled |
| `GET /api/health` | deploy verdict | none |
| `GET /api/admin/celery-debug` | **NOT USED** | item 1 exists to stop grading beats with it (#1994) |
| warmer pass result (`period_s`, `expired`) | **NOT READABLE** | no admin endpoint, no reachable log — blocks the gate's halt (plan doc §6) and §5 |
