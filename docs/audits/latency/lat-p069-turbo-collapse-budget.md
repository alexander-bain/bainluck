# LAT-P069 — #224 FIRST: bounding the `turbo_collapse` pair

date: 2026-08-18
lane: latency, cycle 41
issues: #1609 (p1), #224, #1922, #1917
branch: `program/latency-62`, stacked on `program/latency-61` @ `ba5b0dcc`
directive: Fable LAT-P068 ruling, item 2 — "FIRST: bound the turbo_collapse pair"

---

## §0 — The header answer: which #224 prediction shipped, and its halt state

**Prediction P3** (registered by LAT-P068, `lat-p068-real-occupant.md` §4) is the one this maps to.

> **P3 — the turbo pair is the largest lever.** Predicted: once instrumented,
> `turbo_collapse_futures` shows a p50 in the 400–900 s class […]
> 🔴 **HALT: if the measured p50 is under 120 s**, then the 13.6-minute sighting was an outlier and
> the 3600 s budget must **not** be touched on the strength of one observation.

**Halt state: NEITHER TRIPPED NOR CLEARED — P3 is UNRESOLVED, and the budget is therefore UNTOUCHED.**

The halt is conditioned on *the measured p50*, which requires the instrument. The instrument
(`_tracked_run` on both tasks, commit `de4bd1d4`) rides `program/latency-61`, which is
`ready_for_integration` and **not merged**. `/api/admin/task-metrics?task=turbo_collapse_futures`
answered **`no_data`** at 21:0xZ today, as it has all program long.

So the p95 the directive asks the budget to be derived from **could not be measured**, and per the
directive's own closing clause it renders as could-not-measure:

> "Could not measure" renders as could-not-measure, never as a default number.

**What shipped is therefore the derivation and its refusal, not a number.** The wire stays at
`soft_time_limit=3600` on both tasks — not because 3600 is right, but because nothing measured
today can justify replacing it, and my own lane registered the halt that says so.

---

## §1 — What ships

| | |
|---|---|
| **S4 entry/exit tags on both tasks** | ✅ **BUILT** — `de4bd1d4`, on `-61`, awaiting merge. Not rebuilt here. |
| **A `soft_time_limit` derived from measured p95** | ⛔ **COULD-NOT-MEASURE.** n=1 per task. No number shipped. |
| `app/utils/turbo_collapse_budget.py` | 🆕 the derivation + the ruling-075 refusal, 22 tests, 3 mutations proved |
| `ops-snapshot.turbo_collapse_budget` | 🆕 the reader, because ruling 086 is this lane's own |
| `get_hard_kill_census()` false zero | 🔧 **FIXED** — it now raises instead of returning `{}` |

**No occupancy change lands in this window.** That is deliberate and it is the second reason to
prefer this shape: the directive fences 2026-08-19 **07:50–17:01Z** for the T5 reads and forbids an
intervention landing inside it. A budget change merged tonight could deploy into that window. A
derivation that declines to change the budget cannot.

---

## §2 — The measurement, and why it is a floor and not a p95

Recovered from LAT-P068's S4 capture (`lat-p068-s4-occupancy.jsonl`), which sampled celery's
`active` set once a minute and recorded each occupant's `time_start` **as celery reported it**. A
completion is bracketed between the last sample where the task was present and the first where it
was gone. Both brackets here are closed by **good samples on both sides** (the run's one bad
sample, idx 35, falls outside both):

| task | `time_start` | last present | first absent | **completion** |
|---|---|---|---|---|
| `turbo_collapse_futures` | 19:23:52.08Z | 19:37:05.81Z (idx 18) | 19:38:05.84Z (idx 19) | **(793.7, 853.8] s** |
| `turbo_collapse_odds` | 19:55:11.12Z | 20:02:05.98Z (idx 43) | 20:03:05.99Z (idx 44) | **(414.9, 474.9] s** |

`MEASURED_FLOOR_S` records the **upper** end of each bracket, because that is the number a budget
must not fall below: it is a duration we have watched the task complete at. Killing under it kills
work we know is normal.

**Why this is not a p95, stated plainly:** n=1. At n=1 the p95 *is* the max — the same number
wearing a distribution's authority. `MIN_SAMPLES = 5` is the point at which a nearest-rank p95 stops
being a synonym for `max()`, and below it `derive_budget()` returns `could_not_measure` and no
number at all.

⚠️ **Clock skew, recorded because it bounds the precision:** `turbo_collapse_odds` was first *seen*
at 19:55:05.94Z, **5.19 s before** its own reported `time_start`. The observer's clock and the
worker's differ by about that. The 60 s brackets absorb it; a derivation finer than the 60 s
rounding would not.

### §2.1 — A correction to the directive's mechanical model, on measured evidence

The directive's premise for ruling FIRST:

> `soft_time_limit=3600` on an uninstrumented occupant **that can hold two slots for an hour** is
> the best mechanical explanation of the p90/max tail.

The *exposure* is real and is exactly why the pair deserves a budget. But **the hour was never
observed.** The two runs we have measured are **~14 min** and **~8 min**, and they did **not
overlap** — `futures` finished ~19:37Z, `odds` started ~19:55Z. So the specific "both slots for an
hour" scenario is a structural possibility that this window's data does not witness, and the golf
tail it is offered to explain has not been attributed to it. Recorded so the model is not carried
forward as measured.

**The genuinely new structural finding is adjacent, and it is worse than the schedule suggests:**

The two beats are 900 s apart on paper (`:30` and `:45`). **Their observed starts were 1,879 s
apart** — because each sat a *different* length of time in a saturated queue:

| task | published | started | **queue delay** |
|---|---|---|---|
| `turbo_collapse_futures` | 18:30:00Z | 19:23:52Z | **53.9 min** |
| `turbo_collapse_odds` | 18:45:00Z | 19:55:11Z | **70.2 min** |

So **the 15-minute schedule separation does not survive a saturated `background` queue** — and a
saturated queue is precisely the condition under which an overlap matters. Any argument of the form
"they cannot overlap, they are scheduled 15 minutes apart" is refuted by this measurement. Note
also that `futures`' measured completion (up to 853.8 s) is **94.9 % of the 900 s separation**: even
with zero queue delay the pair very nearly abuts.

**Not acted on here.** Re-timing a beat is a schedule change, which is a *different* intervention
from bounding a budget, and the directive allows one per observation window.

---

## §3 — Registered predictions (ruling 050 — armed, with halts)

**Controls, armed for all reads below:** `/api/health` **0.240 s** and `/api/golf` **0.455 s**
(LAT-P068 baseline). If either is more than ±20 % off when a read is taken, the system is in a load
episode and **the read is void** — retake it.

### P4 — the instrument will produce a p95 that clears `MIN_SAMPLES` within 30 h of deploy

Both tasks fire on `crontab(minute=30|45, hour="*/6")` = **4 runs/day each**. `MIN_SAMPLES = 5`
therefore needs **~30 h** of deployed instrument, not one night.

**Predicted:** `GET /api/admin/ops-snapshot?fresh=1` → `turbo_collapse_budget[*].samples_n` reaches
**≥ 5** by **2026-08-20 ~06:00Z**, and the verdict flips `could_not_measure` → `derived` or
`refused_below_floor`.

🔴 **HALT: `samples_n` still 0 more than 7 h after `-61` deploys.** That means `_tracked_run` is not
recording for these two at all, and the instrumentation commit is wrong — a gauge that reads zero
forever is ruling 086's exact defect and must be fixed before any budget is derived from its
silence. **Distinguish it from "no fire yet" by the beat clock**, not by the zero: after 7 h each
task has been published at least once.

### P5 — the derived budget lands well under 3600 s and above the measured floor

**Predicted:** once `samples_n ≥ 5`, `derived_soft_time_limit_s` for `turbo_collapse_futures` falls
in **1,020–2,400 s** (p95 in the 510–1,200 s class × the 2.0 safety factor), and for
`turbo_collapse_odds` in **600–1,800 s**. Both **≥ their measured floor**, which the module
guarantees rather than predicts.

🔴 **HALT: verdict `refused_below_floor`.** That means the recorded p95 is *below* a completion we
watched, which cannot be true of the same population — so either the durations are being recorded
wrong, or the S4 bracket was mis-read. **Do not clamp, do not widen the safety factor.** Re-derive
the floor from a fresh S4 capture first. This is ruling 075's self-locking shape and the refusal is
the only outcome in the family that leaves a readable artifact.

🔴 **SECOND HALT: derived p50 under 120 s** — LAT-P068's P3 halt, carried forward verbatim. The
13.6-minute sighting would then be an outlier and the 3600 s budget must not be touched on it.

### P6 — an armed NULL control: bounding the pair does NOT move the golf tail

**Predicted, and predicted as a NULL:** if and when P5's budget is wired, `/api/golf/tournaments/{slug}`
p90 under load moves by **< 2 s** from the 15.260 s baseline.

**Why register a null:** the directive offers the 3600 s budget as "the best mechanical explanation
of the p90/max tail". §2.1 shows the hour was never observed. If bounding the pair *does* collapse
the golf tail, that explanation is confirmed on evidence it does not currently have; if it does not,
the tail's cause is still unattributed and §4's probe is what finds it. Either way the answer is
worth more than the patch.

---

## §4 — The golf probe, registered BEFORE it is run (directive item 3)

The directive's ask: split the elevated window into **router-queue vs app vs DB** time, so
"system-wide contention" becomes an attributed mechanism rather than a description.

**Instrument — and it is NOT free yet. Measured, not assumed:**

The directive's premise is that "Heroku `X-Request-Start` gives queue time free". Heroku does send
the header on every inbound request, so the *data* is free. **The app never reads it:**

```
grep -rn "X-Request-Start\|x-request-start\|request_start" backend/app/   ->  0 hits
grep -c  "debug_timing" backend/app/routes/golf.py                        ->  0
```

So **both** terms of the requested split are currently unreachable:

| term | status | what it needs |
|---|---|---|
| **router queue** | ⛔ unreachable | middleware reading `X-Request-Start` and recording `now − header`. Nothing in `app/` touches the header today. |
| **app vs DB** | ⛔ unreachable *on golf* | `?debug_timing` exists on the **events** routes (`app/routes/events.py`, the #1197 precedent) and **zero** times in `app/routes/golf.py`. |

**This is a one-queue build, not a curl.** Recording it precisely because "the header is free"
and "the measurement is free" are different claims, and the second one is what the probe was
scoped against. Heroku router logs would answer it without app changes, but `heroku logs` is
EPERM-blocked from an agent session, so that path is closed here.

**The measured window to re-create:** loaded p50 **4.583 s** / p90 **15.260 s** / max **26.714 s**,
against quiet p50 2.096 s / p90 2.451 s / max 3.193 s, with `/api/health` at 0.370 s (vs 0.240) and
`/api/golf` at 0.604 s (vs 0.455) as the contention controls.

### The registered prediction

**Predicted: the elevation is DB-time dominated, not router-queue.** Specifically, of the
**~12.8 s** p90 excess (15.260 − 2.451):

| term | predicted share of the excess |
|---|---|
| **DB time** (query + buffer-pool eviction) | **> 70 %** |
| app CPU / GIL | 10–25 % |
| **router queue** | **< 10 %** |

**The reasoning, so the prediction is falsifiable rather than vague:** the `background` pool's
occupants are almost entirely DB-bound sweepers (`turbo_collapse_*` collapsing snapshot partitions,
`warm_typeahead` running trigram scans, `match_prediction_markets`). They contend for the *database
and the buffer pool*, which the web dynos share; they do not contend for web dynos' own CPU or for
router capacity. LAT-P068 already argued this in prose — "the contention is not for *slots*, it is
for the **database and the buffer pool**" — and this probe is what turns that sentence into a
measurement.

🔴 **HALT: router-queue time > 30 % of the excess.** Then the bottleneck is web-dyno capacity, not
DB contention, and **every "background saturation reaches users through the database" conclusion in
LAT-P068 §5 is re-derived before anything else ships.** That would also mean the fix is a dyno
count, not a query — a different owner and a different budget.

⚠️ **Also worth knowing before it is run:** the probe needs a *loaded* window to reproduce, and the
loaded window is created by the very occupancy the #224 work is trying to remove. **Take the probe
BEFORE the budget is wired**, or the baseline is gone. Sequencing, not a preference.

---

## §5 — The false zero this window closed

LAT-P068 found the hard-kill gauge's first production read returning `tasks_observed: 0`,
`total_hard_kills: 0` — **three minutes before the same Redis keys returned 117 tasks and 13
kills.** The cause was `get_hard_kill_census()` ending `except Exception: return {}`, so the
caller's perfectly good error branch was unreachable and an unreachable Redis rendered as a clean
bill of health.

Fixed here: the census raises `HardKillCensusUnavailable`, the route's existing `except` renders
`status: error`, and the test that asserted `get_hard_kill_census() == {}` — **a fixture that agreed
with the bug, ruling 072** — now asserts the raise. The write side still never raises; it is on
every task's hot path.

This is in scope because **P4 and P5's halts are read through this instrument.** A halt whose
reader can return a false zero is not armed.

---

## §5.5 — Pre-registered input for the GATED SECOND item (`warm_typeahead`, 26.2 %)

Not started — Fable gated it behind the FIRST read and forbade a blind W cut. But one cheap read
this window changes what its registered prediction has to say, so it is banked here rather than
rediscovered.

`warm_typeahead` **is** instrumented, so unlike the turbo pair it has a real distribution.
`GET /api/admin/task-metrics?task=warm_typeahead`, 2026-08-18 ~21:2xZ:

| | |
|---|---|
| `starts_24h` | **4,245** (successes 4,242, `hard_kills_24h` 0) |
| cadence | 50 samples over 726 s → **one run per ~14.5 s** |
| **p50** | **0.01 s** |
| p90 / p95 / max | **39.77 s** / **42.24 s** / 45.09 s |
| mean | 11.68 s |

⚠️ **Scope caveat, stated because the code itself warns about exactly this** (LAT-P040/#835):
`recent_durations_saturated: true` and `recent_durations_window_s: 726`. The 50-entry list is
bounded by COUNT, so this p95 describes **~12 minutes**, not 24 h. Do not read it as a standing
property.

**The distribution is BIMODAL, and that is the finding.** The median run costs **ten
milliseconds** — it finds the head warm and no-ops. Roughly one run in ten does a full pass at
**~40 s**, which matches LAT-P068's independently-measured warmer pass wall (median 38.5 s, 41 %
of passes losing the head against a 45 s TTL at a 43.5 s period median).

Duration × frequency cross-check: `mean 11.68 s × (1/14.5 s) ÷ 2 slots` = **40.2 %** of the pool,
against S4's directly-observed **26.2 %**. Same order, S4 lower — consistent with the 726 s window
catching a busier stretch. Two independent instruments agreeing on the rank is what matters here;
the point estimate is not settled.

### Why this makes a blind W cut worse than neutral

**The cost is not in the runs; it is in the misses.** Cutting warmer count reduces the frequency of
the *ten-millisecond* runs — the ones that cost nothing — while doing nothing about the ~40 s
passes, and it can plausibly make them *more* frequent by letting the head go cold more often. The
period median (43.5 s) already sits just under the 45 s TTL; that margin is what a W cut spends.

So the SECOND item's registered prediction must state **where the load goes** in these terms:
predicted change in the *fraction of passes that go cold*, and predicted DB hold %, not slot
occupancy. Fable's halt on DB hold % is the right instrument and this is the mechanism behind why.

---

## §6 — What this window did NOT establish

- **Either task's true p95, p50, or dispersion.** n=1 each. That is the whole §0.
- **Whether the pair explains the golf tail.** P6 is the null control; §4 is the probe.
- **Whether `limit=5000` bounds the duration.** If the observed run hit its partition cap, ~854 s is
  near a *structural* max rather than a sample from an open-ended tail — which would make 3600 s
  4.2× a bounded worst case and change the derivation's shape. The task's return summary carries the
  count and nothing recorded it; `-61`'s `_tracked_run` will, in `last_result_summary`. **Read it
  when P4 clears.**
- **`warm_typeahead` (26.2 %).** Fable gated it SECOND and required its registered prediction to
  state *where the load goes* and its halt to watch **DB hold %**, not slot occupancy. Not started;
  it is the next queue's item and it must not share an observation window with any of the above.
