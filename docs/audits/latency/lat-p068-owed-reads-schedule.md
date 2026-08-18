# LAT-P068 — the owed reads: FIVE discharged, three still blocked, each with what it needs

The Fable directive named three owed reads (E1, T5's 24 h horizon, #1917's golf p50) and asked for
them to be **scheduled with what each needs**. Two of the three turned out to be *reachable now* and
have been taken rather than scheduled; the third genuinely is not, and its earliest honest time is
named below to the minute.

The table also carries the three reads this program is owed that the directive did not name, because
a schedule that omits them re-creates the eight-window `hard_kills` failure that ruling 078 was just
banked to end.

| # | read | status | when |
|---|---|---|---|
| 1 | **E1** — background depth < 100 at 2 h | 🔴 **DISCHARGED — REFUTED** | taken 19:31Z |
| 2 | **E2** — `warm_typeahead.starts_24h` falls below 2,816 | 🔴 **DISCHARGED — REFUTED** | taken 19:17Z |
| 3 | **#1917** — golf `{slug}` p50 unchanged | ✅ **DISCHARGED — CONFIRMED** | taken 19:40Z |
| 4 | **E3** — holes unchanged by `expires` alone | ✅ **DISCHARGED — CONFIRMED** (holds; nothing improved) | taken 20:23Z |
| 5 | **T5** — sentinels LATE, never MISSING, over 24 h | ⛔ **NOT REACHABLE** | **2026-08-19, 07:50Z–17:01Z** |
| 6 | **`hard_kills`** — eight windows owed | ✅ **DISCHARGED — 13 kills, 10 tasks** | taken 20:16Z, after `-60` deployed mid-window |
| 7 | **D3** — Option D sizing | ⛔ blocked on merge + index | after the runbook's §4 verify |
| 8 | **D2** — the 46 gold probes, armed null control | ⛔ blocked on D1 | before any read-path flip |

---

## 1 — E1: REFUTED, by 34×, and moving the wrong way

**Registered:** *"background depth falls and holds < 100 within 2 h; bar is depth < 100 at 2 h."*

The `expires` hygiene commit (`a25140cc`, in the `3ca79ddf` wave) reached production at
**17:01:53Z**. The 2 h mark was **19:01:53Z**.

| at | background | realtime | heavy |
|---|---|---|---|
| 19:14Z (claim) | 3,349 | 0 | 0 |
| 19:31:56Z | 3,421 | 0 | 0 |
| 19:32:39Z | 3,426 | 0 | 0 |

**3,426 against a bar of 100.** Not marginal, not a timing artifact: 2 h 31 m after the deploy, at
**34× the bar**, and *rising* — the S4 read measures the growth rate over a full hour at
**+3.6 messages/minute** (3,352 -> 3,573 across 61 consecutive samples), on a pool it independently
measured at **98.4 % utilisation**.

**REFUTED.** And the direction matters more than the magnitude: `expires` was supposed to bound
inflow. Depth is not merely failing to fall, it is climbing monotonically, which means arrivals
exceed departures continuously. Whatever `expires` bounds, it does not bound this.

⚠️ **Do not read this as evidence about the topology fix.** LAT-P066's attribution correction cuts
both ways and this is the second half of it: E1 is the **hygiene** commit's own metric. A failure
here is `expires`'s, exactly as a pass here would have been. It says nothing about `-59`'s re-route,
which was separately CONFIRMED on the wire.

## 2 — E2: REFUTED, and the comparison has a window caveat that must ride with it

**Registered:** *"`warm_typeahead.starts_24h` drops materially below 2,816; no burst in
`recent_durations_ms`."*

**Measured 19:17Z: `starts_24h` = 3,699, rising to 3,735 by 19:26Z.** Above 2,816, not materially
below it. **REFUTED.**

🔴 **The caveat, stated because #1790 is an open p1 about exactly this error:** `starts_24h` ships
with a `starts_window_s`, and mine is **15.0 h, not 24 h**. The 2,816 baseline was recorded without
its window. So the two numbers may not span equal time, and if the baseline was a true 24 h count
the gap is *wider* than it looks (3,735 in 15 h extrapolates to ~5,976/day). The verdict does not
turn on the extrapolation — 3,735 > 2,816 on the raw counts, over a *shorter* window — but nobody
should quote a ratio from this pair.

The second clause is **not** graded: I did not capture `recent_durations_ms` in a form that
distinguishes a burst from a run of legitimate short skips. Named as not-graded rather than passed.

## 3 — #1917: CONFIRMED unchanged, and the controls are what make it a verdict

**Registered:** *"`/api/golf/tournaments/{slug}` p50 unchanged"* after `GOLF_IDENTITY_SPLIT_SCAN` and
the `UNION` branch were deleted. Deletion is in `origin/master` (the guard test
`test_golf_identity_prefilter.py` is present there) and deployed.

**Baseline (LAT-P061, `lat-p058-golf-index-spec` era):** four *completed majors*, warm, pooled
p50 **2.35 s** — with controls `/api/golf` 0.47 s ×3 and `/api/health` 0.24 s.

### The first attempt was wrong, and how it was caught is the method

The first pass measured three *current* tournaments (`bmw-championship`, `adventhealth-championship`,
`nexo-championship`) and got p50 1.315 s. Against a 2.35 s baseline that reads as a 44 % improvement.
**It is not a result at all** — those are different specimens. The baseline's four majors are the
heavy ones (45 markets / 4,621 outcomes / 99–172 KB bodies); a light tournament is a different query.

Re-run on the **same four slugs**, payload sizes verified against the baseline's stated range
(98.6 / 121.6 / 172.4 / 102.8 KB vs "99–172 KB" — same specimens):

| slug | baseline | LAT-P068 quiet p50 | delta |
|---|---|---|---|
| `the-open-championship` | 2.87 s | **1.897 s** | −33.9 % |
| `pga-championship` | 2.43 s | **2.125 s** | −12.5 % |
| `us-open` | 2.23 s | **2.091 s** | −6.2 % |
| `the-open` | 2.26 s | **2.239 s** | −0.9 % |
| **pooled (n=16)** | **2.35 s** | **2.096 s** | **−10.8 %** |

Controls matched at both ends of the run: `/api/health` **0.240 s** (baseline 0.24 s), `/api/golf`
**0.455 s** (baseline 0.47 s).

**VERDICT: p50 unchanged — CONFIRMED.** −10.8 % pooled, every slug at or below baseline, controls on
their baseline values. The deletion cost nothing, which is what ruling 076 predicted when it ordered
the measured-worse arm removed rather than parked.

### 🔴 The other thing this read found, and it is bigger than the read

An **earlier** batch of the same 16 calls, taken ~15 minutes before, produced a completely different
distribution:

| | p50 | p90 | max |
|---|---|---|---|
| quiet (controls at baseline) | **2.096 s** | 2.451 s | 3.193 s |
| **loaded** (same slugs, same protocol) | **4.583 s** | **15.260 s** | **26.714 s** |

The controls are what separate the two and what stop this being attributed to golf: during the
loaded batch `/api/health` read **0.370 s** (vs 0.240 s) and `/api/golf` **0.604 s** (vs 0.455 s) —
both elevated, and neither touches a line of the golf tournament path.

So this is **system-wide contention, not a golf regression** — and `26.714 s` sits **3.3 s from the
30 s H12 timeout**. This is the first measurement in this program that connects the saturated
background pool to *user-facing* latency rather than to internal warmer cadence. It is carried into
`lat-p068-real-occupant.md` §5 as evidence, and it is why that document argues the pool is a
product problem and not a hygiene problem.

## 5 — T5: genuinely not reachable, and here is the earliest honest time

**Registered:** *"all 5 sentinels + `board_sentinel` + `mlb_schedule_coverage` record a run in the
24 h after deploy; **no `no_run_cached`**. If a sentinel is MISSING the safety argument is refuted.
Remedy is heavy concurrency 2 → 3, NOT sending the tasks back to background."*

The arithmetic that makes it unreachable, rather than merely inconvenient:

- Deploy: **2026-08-18T17:01:53Z**. The 24 h window closes **2026-08-19T17:01:53Z**.
- The sentinels are **daily morning beats**: flow 07:10Z, grid 07:25Z, horizon 07:40Z, settled
  07:45Z, plus `board_sentinel` and `mlb_schedule_coverage` at 07:05Z.
- **Every one of those fire times is earlier in the day than 17:01Z.** So the first fire inside the
  post-deploy window is tomorrow morning — and none has occurred yet.

**A read taken today can only report "not yet due", which is not evidence and must not be recorded
as a pass.**

🔴 **Take it holding one fact from §6:** `mlb_schedule_coverage` — one of the seven tasks T5 grades —
shows **1 attempt, 0 terminals, a 100 % hard-kill rate** in the lifecycle census. A task that dies
before writing a terminal will present to T5 as *missing*. If T5 fails on that task specifically,
the cause is the kill, **not** heavy-lane starvation, and the registered remedy (concurrency 2 -> 3)
would be aimed at the wrong thing.

```
WHEN:   2026-08-19, between 07:50Z and 17:01:53Z   (00:50–10:01 PDT)
        — after the 07:45Z settled sentinel, before the 24 h window closes.
WHAT:   curl -s -H "Authorization: Bearer $ADMIN_TOKEN" "$BAINLUCK_API/api/admin/ops-snapshot" \
          | python3 -c 'import sys,json;print(json.dumps(json.load(sys.stdin)["sentinels"],indent=1))'
        plus, per sentinel, /api/admin/task-metrics?task=<name> for last_started_at + verdict.
PASS:   all 7 record a run inside the window. LATE is a pass. Report the lateness in minutes.
FAIL:   any one reports `no_run_cached` or has no start inside the window.
REMEDY: heavy concurrency 2 -> 3 (Standard-2X has the RAM headroom).
        NEVER send them back to `background` — that trades a feared starvation for a MEASURED one,
        and this window measured it: the background pool was 2/2 saturated in 100% of samples.
NEEDS:  nothing but the clock. No merge, no deploy, no code. Do not let it slip a ninth time.
```

⚠️ **The 17:01:53Z anchor is the `3ca79ddf` deploy, not the `404210a3` restart at ~18:16Z.** Segment
by release and do not average across the restart (LAT-P066's rule). A dyno restart does not reset a
Redis-backed sentinel record, but it does reset worker counters.

## 6 — `hard_kills`: ✅ **DISCHARGED. Eight windows owed; taken 20:16:52 Z.**

**`program/latency-60` merged and deployed mid-window** (INT-086, landed `9e0f0f37`, Heroku v3843,
20:12 Z). That made LAT-P067's wiring live, and the read that eight windows could not take became a
single curl. Ruling 078 clause 3 discharged on its first day.

```
GET /api/admin/ops-snapshot?fresh=1     # generated_at 2026-08-18T20:16:52Z
```

**117 tasks observed. 10 with kills. 13 hard kills**, over a ~19.5 h window (`window_s` ≈ 70,000 s).
This is the *sound* instrument — written from celery's `task_prerun`/`task_postrun`, so the 30 tasks
that never call `_tracked_run` are counted like any other.

| task | attempts | terminals | hard kills | window |
|---|---|---|---|---|
| `precompute_backfill_progress` | 51 | 49 | **2** | 68,819 s |
| **`precompute_bookmaker_calibration`** | **3** | **1** | **2** | 63,094 s |
| `poll_all_odds` | 2,343 | 2,341 | 2 | 70,393 s |
| `precompute_backfill_winners_status` | 19 | 18 | 1 | 67,314 s |
| `heartbeat` | 1,168 | 1,167 | 1 | 70,333 s |
| **`mlb_schedule_coverage`** | **1** | **0** | **1** | 47,514 s |
| `compute_calibration_prices` | 3 | 2 | 1 | 43,614 s |
| `sync_statpal_live_plays` | 1,168 | 1,167 | 1 | 70,333 s |
| `warm_event_concepts` | 157 | 156 | 1 | 70,204 s |
| `precompute_calibration_main` | 20 | 19 | 1 | 68,514 s |

**Two of these are not rounding errors, and they are what the read was for:**

- **`precompute_bookmaker_calibration`: 2 hard kills out of 3 attempts — a 67 % death rate.**
- **`mlb_schedule_coverage`: 1 attempt, 0 terminals — 100 %.** And it is one of the **seven tasks T5
  grades** (07:05 Z, the protected sentinel window). A task that dies before writing a terminal will
  read to T5 as absent. **Read T5 with this in hand.**

Both are invisible to `task-metrics.hard_kills_24h`, which is why eight windows of asking the wrong
gauge returned nothing. Filed as follow-ups; neither is a latency-program fix.

### 🔴 And the first production read exposed a defect in the gauge itself

The read **immediately before** the fresh one returned:

```json
{"tasks_observed": 0, "tasks_with_kills": 0, "total_hard_kills": 0, "by_task": {}}
```

**That zero was false.** The same Redis keys — carrying `window_s` ≈ 70,000 s, so they long predate
both reads — returned 117 tasks under three minutes later. The zero came from
`get_hard_kill_census()`'s `except Exception: return {}`, which converts *any* failure into an empty
census, which `ops-snapshot` then renders as **`total_hard_kills: 0`**.

**A reader sees "0 hard kills" and reads health.** There is no `status: error`, no partial marker,
nothing to distinguish "nothing died" from "the census could not run". This is gotcha #53 — an empty
response and an absent one reading identically — **inside the very instrument ruling 078 was written
about**, on its first day in production.

The fix is small and is not this window's: the bare `except` must return a sentinel the route can
render as unknown, not `{}`. Until then, **treat `tasks_observed: 0` as UNKNOWN, never as zero** —
a real census observes 117 tasks, so `tasks_observed` is itself the tell.

⚠️ **`ops-snapshot` caches for 300 s and the cached copy is served with its original
`generated_at`.** Two identical reads three minutes apart returned the same stale payload. **Use
`?fresh=1`** for anything you intend to record.

## 6b — The ninth-window recommendation, superseded

Eight windows owed this. LAT-P067 finally wired the **sound** instrument — `get_hard_kill_census()`,
written from celery's `task_prerun`/`task_postrun` signals, correct for all 117 tasks — into
`/api/admin/ops-snapshot`.

**It is still not readable.** Production `ops-snapshot` returns `celery: {queue_depths, task_health}`
and **no `hard_kills` key**, because the wiring rides `program/latency-60`, which has not merged.
Verified this window at 19:14Z.

That is ruling 078 clause 3 in its first live application: *a gauge wired on an unmerged branch is
not yet a reader.* The debt closes on the **read**, not the commit.

**LAT-P067 recommended closing this as unmeasurable-by-construction. That would have been wrong,
and the window proved it within hours.** It was never unmeasurable; it was unwired. `-60` deployed
at 20:12 Z and the read was taken at 20:16 Z — **13 hard kills across 10 tasks that nobody had ever
seen.** Recorded because "we cannot measure this" is the most expensive sentence in an owed-read
ledger: it converts a debt into a closed question.

Partial reads available today, via the blind twin, recorded for what little they are worth:
`warm_typeahead.hard_kills_24h = 1`, `backfill_winners.hard_kills_24h = 0`. Both come from
`task-metrics`, the counter that **30 of 117 beat tasks never write at all**, so a zero there is not
a zero.

---

## What each of the three blocked reads needs, in one line

- **T5** — the clock only. 2026-08-19 07:50Z–17:01Z. *Nothing blocks this but attention.*
- ~~`hard_kills`~~ — **DONE.** `-60` deployed mid-window; read taken with `?fresh=1`.
- **D3 / D2** — `-60` merged, the fill task run, and the index built per
  `lat-p068-option-d-index-runbook.md`. D2 is armed and must be read *before* any read-path flip.
