# LAT-P070 — the T5 grading protocol, pre-registered before the window opens

**Fence: 2026-08-19 07:50–17:01Z. READ ONLY.** Nothing deploys and nothing intervenes inside it
(Fable, LAT-P069 directive item 1). This document exists so tomorrow's read is *mechanical* — the
rubric is fixed now, before any number is seen, and the two tasks that cannot be graded against
#1609 are named now rather than argued about afterwards.

Fable's standing instruction is the reason for every section below:

> Grade `mlb_schedule_coverage` separately from #1609 exactly as you pre-registered — **a predicted
> red graded against the wrong cause is worse than no read.**

This window found that the same sentence applies to a *second* task, and that the metric T5 was
going to be graded on is unsound for **all seven**. Both are recorded here, with the measurement.

---

## §1 — What T5 actually says

Registered in `lat-p065-1609-topology-fix-predictions.md`:

> **T5** — sentinels may now be **late**, never **missing**: all 5 sentinels + `board_sentinel` +
> `mlb_schedule_coverage` record a run in the 24 h after deploy; **no `no_run_cached`**.
>
> Halt/remedy if a sentinel is MISSING: **heavy concurrency 2 → 3**, *not* reverting the three
> tasks to `background`.

Horizon: the topology deploy reached production at **2026-08-18T17:01:53Z**, so the 24 h window
closes **2026-08-19T17:01Z**. The read opens at **07:50Z** because that is the last of the seven
beats to fire (see §2) — a read before it would score a task red for not having run yet.

---

## §2 — The cadence table, which decides what is gradeable at all

Measured from `backend/app/tasks/__init__.py` on `program/latency-63`:

| task | beat | fires inside the 24 h horizon? |
|---|---|---|
| `mlb_schedule_coverage` | daily **07:05Z** | ✅ once |
| `flow_sentinel` | daily **07:10Z** | ✅ once |
| `grid_sentinel` | daily **07:25Z** | ✅ once |
| `horizon_sentinel` | daily **07:40Z** | ✅ once |
| `settled_concept_sentinel` | daily **07:45Z** | ✅ once |
| `board_sentinel` | daily **07:50Z** | ✅ once |
| `calibration_sentinel` | **weekly, Monday 06:20Z** | 🔴 **NO** |

🔴 **`calibration_sentinel` CANNOT satisfy T5, and its failure would carry no information.**
2026-08-17 was a Monday; the next fire is **2026-08-24T06:20Z**, seven days outside the horizon.
A weekly beat's `successes_24h` is zero on six days in seven *by construction*. It is
**pre-registered as EXCLUDED — cadence-ineligible**, and it must not be counted toward "all 5
sentinels", nor reported as a #1609 regression. Its last run (2026-08-17T06:24:26Z, 266 s,
2,670 cohorts, 0 errors) is healthy.

**T5's real denominator is therefore 6, not 7**, and one of those six is graded separately (§4).

---

## §3 — 🔴 The metric T5 names is unsound. Grade on the stamp, not the counter.

**Do not grade any task on `successes_24h`.** Measured this window, and fixed on
`program/latency-63` (`ef782755`):

`hard_kills_24h` is derived as `starts − (successes + failures + incompletes)`, and those four
counters **do not share a window** — each is stamped `SET NX EX 86400` at its own first increment.
`WINDOW_COUNTER_TTL` is **86400 s**, which for a *daily* beat is exactly its cadence. So every
daily task races its own key expiry once a day, and the race can resolve **differently for `starts`
and `successes`**, which are written a fraction of a second apart.

**Measured 2026-08-18T22:45Z — one morning, two of the seven T5 tasks, the same race resolving in
opposite directions:**

| task | `starts_24h` | `successes_24h` | derived | truth |
|---|---|---|---|---|
| `mlb_schedule_coverage` | 1 | **0** (`successes_window_s: null`) | `hard_kills_24h: 1`, `health: critical` | ran at 07:05:00.095Z, **succeeded at 07:05:00.851Z**, 734 ms, full result summary |
| `grid_sentinel` | **0** | 1 | clamped to 0 | ran 07:25:06Z, 6.7 s, 0 errors |

The `mlb` payload asserted *"1 runs started, none reached an end handler — hard-killed (memory /
hard time limit)"* while **carrying that run's `last_success_at`, `last_duration_ms` and
`last_result_summary`** — the end handler's own writes.

**Consequence for the rubric: a task "records a run" iff `last_success_at` (or `last_failure_at`)
falls inside the horizon.** The counters are corroborating evidence at best. This is doctrine
clause 1 in counter form: *could-not-compare* must not render as *hard-killed*.

---

## §4 — `mlb_schedule_coverage`, graded separately and against a named cause

Fable's item 1. Three candidate causes, distinguished by evidence, decided **before** the read:

| # | cause | evidence that selects it | is it #1609? |
|---|---|---|---|
| A | counter-window artifact (§3) | `last_success_at` inside the horizon, `last_duration_ms` present, `last_result_summary` dated today | **NO** — instrument |
| B | genuine hard kill | `last_started_at` inside the horizon, **no** terminal stamp after it, no result summary | **NO** — its own 240 s/300 s limits; the task is not one of #1609's three re-routed tasks |
| C | never fired | no `last_started_at` inside the horizon at all | **possibly** — a beat/scheduler fault is the only route by which #1609 could reach it |

**On today's pre-window evidence the answer is A**, and A is already fixed on `-63`. If tomorrow
reads A again, that is the un-deployed fix, not a regression: **`-63` deploys only after 17:01Z**,
so the T5 window necessarily runs on the *old* census. Expect the phantom, name it, do not file it.

**Only branch C may be attributed to #1609 at all**, and even then the attribution needs the beat
to be shown missing — not inferred from a zero counter.

Separately noted, not part of T5: the run's payload reports real DATA defects — 7 ×
`premature_settle` and 1 × `duplicate_events` (gotcha #32/#46 shape, `passed: false`). Those belong
to #1201/#1193/#1202 and are outside this program's scope. **The task is doing its job; the finding
is that its job keeps finding things.**

---

## §5 — Confounds inside the horizon, listed now so they cannot be discovered afterwards

Six releases landed between the topology deploy and this window's close, none of them latency-lane
routing changes, all of them worker restarts:

| release | commit | UTC |
|---|---|---|
| v3844 | `75c32aa2` | 20:18 |
| v3845 | `342b5a79` | 20:49 |
| v3846 | `8db839e7` | 21:03 |
| v3847 | `dc7fe742` | 21:22 |
| v3848 | `c6f68547` | 21:59 |
| v3849 | `43f33396` | 22:29 |

All six fall **after** 17:01Z on 2026-08-18 and **before** 07:05Z on 2026-08-19, so none of them
overlaps the 07:05–07:50Z beat run that T5 grades. Any release landing *during* 07:05–07:50Z
tomorrow is a confound and must be recorded against the affected task by name — a restart mid-run
produces branch B's signature (start, no terminal) without being a kill.

---

## §6 — The commands, and the verdict rubric

```bash
source ~/.claude/.env
for t in mlb_schedule_coverage flow_sentinel grid_sentinel horizon_sentinel \
         settled_concept_sentinel board_sentinel calibration_sentinel; do
  curl -s -H "Authorization: Bearer $ADMIN_TOKEN" \
    "$BAINLUCK_API/api/admin/task-metrics?task=$t"; echo; sleep 1.2
done
```

Space the calls: the public API is 60/min and a throttled response parses as `None`, which reads as
a phantom regression.

**Per task, in this order:**

1. `last_success_at` (or `last_failure_at`) inside 2026-08-18T17:01Z → 2026-08-19T17:01Z? → **PASS
   (ran)**. Lateness is expected and is not a fail — T5 says *late, never missing*.
2. Else `last_started_at` inside the horizon with no terminal after it → **branch B**, record the
   duration limit and check §5 for a restart.
3. Else no start inside the horizon → **branch C = MISSING**. This is the only reading that
   triggers T5's halt.
4. `calibration_sentinel` → **EXCLUDED, cadence-ineligible** (§2). Not a pass, not a fail.

**T5 verdict:** PASS iff all six eligible tasks reach step 1. A single branch-C task refutes T5's
safety argument and the standing remedy is **heavy concurrency 2 → 3** — *not* reverting the three
tasks to `background`, which would restore a measured starvation to avoid a feared one.

**Report the denominator as 6 and name the exclusion.** "6/6 with `calibration_sentinel` excluded
for cadence" is an honest PASS; "6/7" without the reason is a fail that is not one.
