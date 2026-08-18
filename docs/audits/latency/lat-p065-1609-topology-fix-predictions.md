# LAT-P065 — #1609 topology fix: registered predictions (ruling 050)

**Registered BEFORE merge, as the directive required.** Nothing in this file was written after
seeing a post-deploy number. The grading rows are deliberately gradeable by someone who is not me,
with instruments that already exist.

- **Change:** `match_prediction_markets`, `poll_kalshi_markets`, `precompute_admin_link_rate`
  moved `background` → `heavy` (commit `d3c28eb5`).
- **Behind it:** `expires` on four cache-warmer beats (commit `a25140cc`) — hygiene, with E3 as its
  own control. Its predictions live in that commit message and in the code comment; they are
  repeated in §3 here only so a grader has one page.
- **Not deployed by this window.** A program lane does not push. Every row below is owed to the
  first post-merge read.

---

## 1. The pre-state, measured 2026-08-17 ~17:40–18:10 PDT (v3836, master `5542f8c4`)

This is the baseline the predictions are against. Take the same reads post-deploy.

| quantity | value | source |
|---|---|---|
| `background` queue depth | **418** | `/api/admin/ops-snapshot` → `celery.queue_depths` |
| `heavy` queue depth | **0** | same |
| `realtime` queue depth | 0 | same |
| `prediction_market_match` p50 / p95 | **337.4 s / 699.4 s** | `/api/admin/task-metrics?task=prediction_market_match`, 50-sample window, entries > 1 s |
| `poll_kalshi` p50 / p95 | **320.2 s / 399.7 s** | same, `?task=poll_kalshi` |
| `precompute_admin_link_rate` p50 / p95 | **71.8 s / 122.2 s** | same |
| `precompute_calibration_main` p50 / p95 | 99.7 s / **1159.1 s** | same |
| `warm_typeahead` real-pass p50 | 36.3 s (17 of 50 samples > 1 s; the other 33 are lock skips) | same |
| warmer holes | **5 clean holes > 120 s in 55.8 probe-free min = one per 11.2 min** | LAT-P064 `lat-p064-s1-probe-free-observation.md` |
| warmer not running | **30.0 % of wall-clock** | same |

⚠️ **The identifier space is not the task name** (#1800). `?task=match_prediction_markets` returns
`no_data`; the metric lives under **`prediction_market_match`**, and `poll_kalshi_markets` under
**`poll_kalshi`**. A grader who uses the task names from `HEAVY_TASKS` will read `no_data` and may
mistake it for "the task stopped running". Use the names in the table.

---

## 2. Registered predictions for the topology fix — the four the directive named

Grade with **`backend/scripts/lat_p064_s1_observe.py`** (already in the tree, already used for the
baseline) and `/api/admin/ops-snapshot`. Do not build a new instrument; comparability is the point.

| # | prediction | pass condition | refuted by |
|---|---|---|---|
| **T1** | **Hole frequency → ~0 in a deploy-free hour** | `holes_over_120s_clean == 0` over ≥ 60 probe-free minutes with **no release inside the window** | **≥ 3 clean holes** (half the 5-per-55.8-min baseline rate). 1–2 holes is a **PARTIAL**, not a pass and not a refutation — say which. |
| **T2** | **Warmer share of beats ≥ its healthy band** | mean real-pass period ≤ **45 s** — the route's own response TTL, which is the thing users ride on. Compute as `duration_min * 60 / distinct_passes` from the S1 summary | mean period > 45 s, i.e. the head can expire between passes |
| **T3** | **Background depth sustained < 50** | 3 reads ≥ 10 min apart, all < 50 | any read ≥ 50 after 2 h |
| **T4** | **Heavy depth > 0 and draining** | heavy observed > 0 at least once (the work arrived) **and** not monotonically rising across 3 reads (it is being consumed) | heavy rising across all 3 reads ⇒ the work moved onto a lane that cannot absorb it |

**T4 is the one that can fail in a way that matters, so read it as a pair.** Heavy staying at 0
forever would mean the routing never took effect — that is a silent no-op, and gotcha #53's shape:
"heavy is at 0" reads like health and would here mean the change did nothing. Heavy rising without
bound means the starvation relocated. Only "> 0, then down" is the pass.

### T5 — the registered COST, not a prediction of success

| # | cost | pass condition | what it means if it fails |
|---|---|---|---|
| **T5** | Sentinels may now be **late**, never **missing** | all 5 sentinels + `board_sentinel` + `mlb_schedule_coverage` record a run in the 24 h after deploy; **no `no_run_cached`** | If a sentinel is MISSING, the safety argument is refuted. **Remedy is heavy's concurrency (2 → 3; it is a Standard-2X with the RAM headroom), NOT sending the three tasks back to background.** Sending them back restores a starvation we have measured against one we have only feared. |

Why the exposure exists, stated in advance: `prediction_market_match` fires :05/:20/:35/:50 and
`precompute_calibration_main` (:15) can run 19 min at p95, so the 07:10–07:45 UTC sentinel window
can find both heavy slots busy.

---

## 3. The `expires` hygiene — its control is the point

| # | prediction | pass condition |
|---|---|---|
| **E1** | background depth falls and holds < 100 within 2 h | depth < 100 at 2 h |
| **E2** | `starts_24h` falls toward real passes; the burst pattern (+11 starts in 6 s of 15 ms lock-skips) disappears | `warm_typeahead.starts_24h` drops materially below 2,816; no burst in `recent_durations_ms` |
| **E3** | **hole frequency and duration UNCHANGED by `expires` alone** | **E3 is expected to PASS, i.e. nothing improves** |

**E3 is why this is labelled hygiene.** If T1 passes and someone attributes it to `expires`, E3 is
the row that says otherwise: `expires` shortens the QUEUE, the routing change returns the SLOT. The
two shipped in one branch, so they cannot be separated by observation after the fact — which is
exactly why the attribution is registered here in advance rather than argued later.

**One deviation from LAT-P064's registration, taken deliberately:** it registered `expires: 30` for
`warm_typeahead`; shipped at **10**. 30 was reasoned from `MIN_PASS_PERIOD_SECONDS`, which floors
real *passes*; `expires` bounds the *message*, and the beat publishes every 10 s, so 30 keeps three
messages alive and re-admits the lapping at 1/3 scale. A guard test caught it
(`test_1609_expires_never_exceeds_the_beat_period`) on a value hand-typed from the registration.

---

## 4. What this does NOT claim

- It does not claim #1609 is closed. #1609's acceptance 3 is
  `/api/admin/backfill-winners/status` serving a fresh cached result; that is a downstream
  consequence and is **unread by this window**.
- It does not claim #1922 is fixed. #1922 is `blocked` on #1609 and stays that way until T1 is
  graded on a deploy-free hour.
- It does not claim the 600–960 s backfill class is safe to move. That is #224's finding, still
  standing, now guarded by a test.
- **It is not verified in production by this window at all.** The branch is unmerged.
