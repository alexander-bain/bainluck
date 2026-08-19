# LAT-P072 — the W-move, derived and halted; the golf split, graded

**Window:** 2026-08-19 18:38Z – (open). **Directive:** Fable, LAT-P072 items 1–4.
**Lane identity:** `LAT-P072-20260819-w74279`. **Branch:** `program/latency-65`, stacked on the
**unmerged** `program/latency-64` @ `d1ce1c20`.

Every number below is either a production read taken this window, dated and with its instrument
named, or a measurement already in this tree with its citation. Where a directive premise did not
survive the arithmetic, the correction is stated before the finding that replaces it.

---

## §0 — The answer, in one paragraph

**Item 2's arrival arithmetic is right and its lever is wrong.** `warm_typeahead` at a 10 s beat
really is 72.0 % of everything published into `background`, and ~82 % of those fires really are
10-millisecond no-ops, so cutting the beat really would remove ~60 % of the queue's arrivals. What
the arrival share cannot see is that **the beat interval is also the quantiser of the warmer's pass
period**, and the pass period is measured against a hard 45-second cliff. At a 60 s beat the
quantiser becomes coarser than the entire measured pass-wall distribution, so the period is 60 s for
*every* reachable wall — there is no branch under 45 s. LAT-P063 measured, 20 passes for 20, that
every pass over that TTL loses cached entries and none under it loses any. **So the W-move as worded
converts a marginal cache into an empty one on every cycle, and the halt is met by measurement
already in the tree — before any deploy.** The goal survives; it has to be spent on the publish side,
where LAT-P071 §4's own clause already pointed.

---

## §1 — Item 2: the W-move, derived

### 1a — The cliff is measured, not reasoned

`/api/events/typeahead` writes its response cache with a **45-second** TTL
(`app/routes/events.py`, `setex(_cache_key, 45, ...)` — exactly one write site, now pinned by
`test_response_cache_ttl_mirror_matches_the_route`).

> 20 passes, **every** pass with `period_s > 45` lost entries (up to 39 of 40) and **not one** pass
> under 45 s lost any — 20 for 20. Crossing the TTL does not degrade the head gradually. It empties
> it.
> — `docs/audits/latency/lat-p063-wsweep-graded.md`

A step function with a measured location. "A bit over" is not a bit worse; it is the failure.

### 1b — The equation the arrival share cannot see

A pass may only START on a beat fire, and only once `MIN_PASS_PERIOD_SECONDS = 30` has elapsed since
the last start. So the period is the beat interval **quantised up**:

```
P(B) = B * ceil( max(pass_wall, 30) / B )
```

This is not a model. It is what LAT-P062 *measured* when it removed the 30 s beat: a ~31 s pass
inside a 30 s beat skipped every other fire and quantised to ~60 s — duty cycle 17.5 of 24, period
straddling the TTL. Shortening the beat to 10 s is what un-quantised it. Read in the other
direction, the same equation says a longer beat re-quantises it.

Live W=4 pass wall, measured: **32.0 s median, 29.4–42.6 s range** over 20 production passes.

| B | P at best wall (29.4 s) | P at median (32.0 s) | P at worst (42.6 s) | verdict |
|---|---|---|---|---|
| **10 s (today)** | 30 s | 40 s | **50 s** | `MARGINAL` — upper tail crosses |
| 22 s | 44 s | 44 s | 44 s | `MARGINAL` — 1.4 s of headroom is a coincidence |
| 30 s | 30 s | **60 s** | **60 s** | `UNSAFE` |
| **60 s (proposed)** | **60 s** | **60 s** | **60 s** | 🔴 `UNSAFE`, unconditionally |

**At B = 60 even the fastest measured pass quantises to 60 s.** That is what makes it unconditional
rather than a tail risk, and it is the single line that decides the item.

### 1c — 🔴 And the same table indicts today's value, which is reported rather than buried

At B = 10 the worst measured wall gives P = 50 s, over the cliff — and production has measured the
live period at **42.5–51.7 s** (LAT-P062, two reads). **The upper tail is already crossing today.**
Today is *marginal*; 60 s is *unconditional*. The guard is written to fail on `UNSAFE` and to
tolerate `MARGINAL` precisely so that it is not red on arrival and therefore disabled within a week
— but `test_todays_10s_beat_is_marginal_not_safe` pins the status quo as marginal so that #1866's
residual cannot read as clean.

### 1d — Why no beat interval is the answer

The gap between the worst measured wall (**42.6 s**) and the TTL (**45 s**) is **2.4 s**. Any beat
coarse enough to cut arrivals meaningfully is far coarser than 2.4 s, so it cannot land the period
inside that gap across the measured range. `B = 22` arithmetically fits (P = 44 s everywhere) and is
**still refused**: 1.4 s of headroom against a maximum drawn from a finite sample of 20 passes is not
a margin. `test_the_arithmetically_fitting_22s_is_still_refused_as_marginal` is where any future
decision to lower `SAFETY_MARGIN_S` and bless it becomes visible.

**The lever is wrong, not the goal.** Raising the beat couples two quantities that are independent
today: the *message rate* (which the W-move wants to cut) and the *pass period* (which must stay
under 45 s).

### 1e — The move that survives: the gate on the publish side

LAT-P071 §4's clause already names the remedy class:

> *a gate inside the task cannot protect the queue.* If the cheap answer is "no work", the cheapness
> is spent on the wrong side of the bottleneck.

The publish-side form of the W-move is a `celery.schedules.schedule` subclass whose `is_due()`
consults the warmer's own `_LAST_PASS_START_KEY` **in the beat process, before publishing**. It
removes the ~82 % of messages that would no-op while leaving the 10 s firing *opportunity* — and
therefore the period, and therefore the cliff margin — exactly as they are today. It gets the arrival
cut without paying the cache.

**It is designed here and deliberately NOT shipped**, for two stated reasons:

1. **One intervention per observation window.** This window's intervention budget is spent on
   measuring the first move, per the directive's own rule.
2. **It carries a real hazard that needs its own window.** `is_due()` runs inside the beat process's
   scheduling loop. A synchronous Redis client with no socket timeout there freezes *the scheduler
   itself* — gotcha #39's exact shape, one level up from where that gotcha was written. It needs a
   bounded client, a fail-open default (a Redis that does not answer must publish, never suppress),
   and a guard test that proves the fail-open direction. That is a queue, not a footnote.

### 1f — Registered prediction, for the branch where Alex overrides the halt

Registered **before** any such change, so it cannot be scored after the fact. Fable's item 2 asks for
the 42 s mode and the DB hold %; both are below, with the halt staged from the second.

- **W1 — the 42 s mode swallows the distribution.** At B = 10 the duration histogram is bimodal:
  p50 **10 ms**, p95 **42.2 s**, ~82 % no-ops. At B = 60 the 30 s floor can never bind, so
  essentially every fire does a real pass. **Predict: the no-op share falls from ~82 % to < 20 % and
  p50 rises from ~0.01 s to > 25 s.** *Refuted if* p50 stays under 1 s — which would mean something
  other than the floor is producing the no-ops, and §1b's model of the period is wrong.
- **W2 — DB hold % FALLS, and this is the one term that genuinely improves.** The warmer holds the
  database for **73 % of wall-clock during a pass** at W=4. At B = 10 the pass occupies ~32 s of a
  ~45 s period (duty ≈ 71 %), so warmer DB hold ≈ **52 %** of all wall-clock. At B = 60 the same
  ~32 s pass sits in a 60 s period (duty ≈ 53 %), so DB hold ≈ **39 %**. **Predict a fall of roughly
  a third, to 35–45 %.** *Refuted if* DB hold does not fall — which would mean the pass lengthens as
  the period does, i.e. the head is being rebuilt from cold every cycle, which is the failure W3
  halts on arriving by a second route.
- **🔴 W3 — THE HALT, and it is already met.** *Halt if any pass reports lost cached entries, or if
  `/api/events/typeahead` p50 exceeds 400 ms sustained.* **This condition does not need a deploy to
  evaluate: LAT-P063 measured it, 20 passes for 20 — every period over 45 s lost entries, up to 39 of
  40.** A B = 60 period is 60 s on every reachable wall. **The halt fires on existing evidence, so the
  change is not proposed.** The user-visible cost, if it were: a typeahead cache MISS is
  **1.16–2.29 s p50** against a `<150 ms` budget (#1866).

Note the shape: **W2, the improvement, is real.** Cutting the beat genuinely reduces warmer DB load
and genuinely removes ~60 % of background arrivals. The refusal is not "the move does nothing"; it is
that the move pays for those two real gains with the cache the warmer exists to maintain.

### 1g — What shipped for item 2

| file | what it is |
|---|---|
| `app/utils/typeahead_beat_budget.py` | the derivation, the three-valued verdict, and the refusal, with provenance |
| `tests/test_typeahead_beat_budget.py` | 21 tests; three mirror pins + the load-bearing `test_live_beat_interval_is_not_unsafe` |

**No production behaviour changes.** `beat_schedule_change: false` — the beat is untouched at 10.0.

**Mutations — 5, all caught.** M1 is the directive's own proposal:

| # | mutation | caught by | exit |
|---|---|---|---|
| M1 | live beat `10.0` → **`60.0`** | `test_live_beat_interval_is_not_unsafe` + the beat mirror | 1 |
| M2 | TTL mirror `45` → `60` | 5 tests incl. the route pin | 1 |
| M3 | quantiser drops the 30 s floor | `test_quantised_period_arithmetic[10.0-12.0-30.0]` | 1 |
| M4 | `REFUSED` collapsed into `UNSAFE` | `test_refused_is_distinct_from_unsafe` | 1 |
| M5 | `SAFETY_MARGIN_S` `5.0` → `0.0` (blesses B=22) | `test_the_arithmetically_fitting_22s_is_still_refused_as_marginal` | 1 |

Restore verified after each: 21 passed, exit 0.

---

## §2 — Item 1: the stamp-arm live read. **PRECONDITION UNMET, with its clock.**

The directive's item 1 opens *"After merge"*. It has not merged.

| commit | what | on `origin/master`? |
|---|---|---|
| `58267ed9` | **the stamp arm** | ❌ **NO** |
| `e6da3a45` | the two-ended queue census | ❌ NO |
| `c6f9a571` | the `celery-debug` availability fix (#1994) | ❌ NO |
| `de4bd1d4` | turbo_collapse instrument (LAT-P068) | ✅ yes |

`origin/master` is **`4eb2a725`** — *"Merge program/latency-63: LAT-P070"* — and `/api/health`
reports `commit: 4eb2a725`, `uptime_seconds: 3802` at 18:38:46Z, i.e. deployed ≈ **17:35Z**. So
**`-63` merged and the 17:01Z fence lifted, but `-64` did not merge.** The stamp arm is on `-64`.

Three consequences, and the third is operational:

1. **The 24 h stamp-arm read cannot start until `-64` deploys.** It is a *successor's* read by
   construction — 24 h does not fit in any window — but it cannot even be *started* here.
2. **The no-start class therefore stays graded on LAT-P071's evidence**, which is honest and already
   banked. Nothing is re-derived.
3. 🔴 **The `celery-debug` availability fix is NOT deployed, so the outage that fix exists to prevent
   is still reachable in production today.** The operational mitigation from LAT-P071 §3e stands and
   is restated because it is the thing most likely to be forgotten: **do not poll
   `/api/admin/celery-debug` faster than 1/30 s.** This window did not poll it at all.

**If `-64` merges before this branch does**, the first stamp-arm read is available ~immediately after
deploy and the 24 h grade completes one window later. Nothing here blocks on it.

---

## §3 — Item 3: #1996 held, and one thing added to the instrument it is waiting for

**HELD as directed.** No sampling of the drop phenomenon was attempted: its discriminator runs on
`celery-debug`, whose availability fix is unmerged (§2), and LAT-P071 already established that the
instrument fails under exactly the load that produces the phenomenon. Buying the instrument first is
correct and this window did not spend against it.

**One correction is banked now, because it is free and it changes the instrument's design.**
LAT-P071 §3c states the discriminator has exactly two readings:

> drop of N with a total-delta of ≈N → **consumption**; drop of N with a total-delta of ≈0 → **loss**.
> There is no third reading.

**There is a third reading, and it is already live in production: `expires`.** `warm-typeahead`
carries `"expires": 10` (`_EXPIRING_WARMER_BEATS`, confirmed on `origin/master`). A message whose
expiry has passed when a worker finally receives it is **discarded without executing** — so it
produces:

* no `task_prerun`, therefore **no start stamp moves**;
* **no appearance in `active`**;
* **no increment of `stats.total`**.

That is *identical* to the signature the table assigns to LOSS — and it is not loss, it is celery
working as configured. The phenomenon's other observed features fit it: the queue is saturated, so
essentially every `warm_typeahead` message ages past 10 s before a slot frees, and a worker that
finally gets a slot discards a run of them at near-zero cost — a drop of tens of messages in under
one 20 s sampler tick, with nothing to show for it anywhere else.

**This is registered as a candidate, not asserted as the answer.** It does not obviously explain a
drop of 74 against a ~72 % warm_typeahead mix, where the expected uninterrupted run of expired
messages is ~3.6. What it *does* establish is that **the discriminator as designed cannot return a
correct verdict**, because it has no branch for the third case and will label it LOSS. That is the
same defect class as the whole #1995 finding: a two-valued instrument over a three-valued world.

**Owed to #1996 before it is graded:** a third arm reading celery's `task-revoked` events (or the
worker's `expired` counter) alongside `llen` and `stats.total`. Commented on the issue.

---

## §4 — Item 4: the golf probe, graded — and the vacuum regime noted

The instrument shipped on `-63` and **is live**: `/api/golf/tournaments/{slug}` returns
`x-timing-split: wall=…;db=…;app=…;q=…;maxq=…;router=…`. Prediction and halt unchanged from
LAT-P069 §4, registered before the build: **DB > 70 %, app 10–25 %, router < 10 %, HALT at
router > 30 %.**

12 reads, two slugs, 18:47–18:50Z, ~70 min after the v-release at ≈17:35Z (outside the ~5 min
post-deploy taint window). Shares are of `edge = router_queue + wall`, computed in one place — the
four terms are never added.

| regime | n | edge median | **db %** | **app %** | **router %** | maxq |
|---|---|---|---|---|---|---|
| COLD (`bmw-championship` run 1) | 1 | 3784.3 ms | **94.23** | 5.71 | **0.06** | 2921.1 ms |
| WARM (all others) | 11 | 923.2 ms | **62.73** (46.41–78.07) | **37.09** (21.73–53.31) | **0.22** (0.15–0.45) | 272.2 ms |

**Grade — PARTIAL, and the halt is nowhere near.**

- ✅ **router < 10 %: CONFIRMED, emphatically.** Router queue is **0.06–0.45 %** of edge — 1.8–2.5 ms
  in absolute terms, on every one of 12 reads. **HALT (router > 30 %) not approached.** #1917's
  premise that the router is a meaningful term in this endpoint's latency is **refuted by direct
  measurement**.
- ⚠️ **DB > 70 %: CONFIRMED COLD (94.2 %), REFUTED WARM (median 62.7 %).**
- ❌ **app 10–25 %: REFUTED WARM (median 37.1 %, up to 53.3 %).** CONFIRMED-adjacent cold at 5.7 %,
  which is *below* the predicted band.

The registered prediction was written for the cold regime and holds there almost exactly. **Warm, the
app term is ~1.5× its predicted ceiling and the split is closer to 60/40 than 75/25.** That is a real
finding rather than a miss: there is ~340 ms of non-DB work per warm request on a 923 ms page, and no
part of the registered model accounts for it. `q = 12` queries on `bmw-championship` (9 on
`nexo-championship`) with `maxq` 272 ms warm — so it is not one pathological query warm; it is
serialised app-side work.

### 4a — The vacuum regime change, noted as directed

`pg_stat_user_tables`, read 18:52Z:

| table | live tuples | last autovacuum | last autoanalyze | autovacuum count |
|---|---|---|---|---|
| **`futures_outcomes`** | 3,538,133 | **2026-08-19 17:12:40Z** | **2026-08-19 18:40:38Z** | 4,442 |
| `futures_markets` | 824,985 | 2026-08-19 16:09:47Z | 2026-08-19 16:31:30Z | 3,128 |
| `events` | 177,801 | 2026-08-19 16:05:56Z | 2026-08-19 17:19:34Z | 5,500 |
| `typeahead_index` | 316,084 | 2026-08-19 12:35:16Z | 2026-08-19 16:33:32Z | 6 |

**`futures_outcomes` was autoanalyzed at 18:40:38Z — four minutes before the first golf read**, and
autovacuumed 95 minutes before it. It is the hottest table in the database by autovacuum count and it
is on the golf tournament page's read path.

**So these numbers are taken in a fresh-statistics regime**, and that is part of their provenance
rather than a caveat bolted on: a plan chosen against statistics four minutes old is not necessarily
the plan that was in force when LAT-P069 registered the prediction. The COLD read's 2,921 ms `maxq`
is the term most exposed to it. **This does not invalidate the router verdict** — a 2 ms router term
is not a planner artifact at any statistics age — but the DB/app split should be re-read in a
settled regime before the warm refutation is treated as final. Registered as owed, not as done.

---

## §5 — Instruments used, and what each could not answer

| instrument | used for | limit that bit this window |
|---|---|---|
| `x-timing-split` response header | §4's whole grade | client-settable `X-Request-Start`; router and dyno clocks differ |
| `/api/admin/db-query` | §4a vacuum regime | JSONB renders as Python repr, needs `ast.literal_eval` (gotcha #40) — hit and handled |
| `/api/health` | §2's deploy verdict | none |
| `git merge-base --is-ancestor` | §2's merge verdict | none — this is the only sound "has it landed" test after a merge commit |
| `/api/admin/celery-debug` | **NOT USED** | its availability fix is unmerged (§2); polling it is what took production down last window |
