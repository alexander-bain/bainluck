# LAT-P105 — the futures pool stops being scored twice on every cold Discover open

**Cycle:** LAT-P105 (cycle 77) · **Identity:** `LAT-P105-20260828-w1561` ·
**Branch:** `program/latency-91` · **Base:** `ea54da79` (= `-90` HEAD, UNMERGED) ·
**Commits:** 2 · **migration_slot: none** · **beat-schedule edits: none** · **DDL run: NONE** ·
**config vars changed at deploy: NONE** (`FEED_FUSED_BROADEN_PASS` defaults ON and exists only
so the rollback needs no deploy)

Ran from **FABLE'S RUNNER DIRECTIVE 2026-08-28** under Alex's standing authorization for this
lane. Lock claimed via `scripts/claim_lane_lock.py` — **exit 0**, prior owner explicitly
RELEASED, no takeover and no MALFORMED repair needed.

## The ship, in user terms

**Opening Discover cold stops paying for the futures pool to be scored twice.** The route
scored every candidate market once under strict staleness windows and then, on essentially
every build, scored the identical set again under relaxed windows and threw the duplicate
away. Measured median cost: **~383 ms of a ~1,594 ms cold build — 24 %.**

## Why this queue and not another

The directive's head was empty (LAT-P100's brief is consumed; all four of `-87`…`-90` are
READY and unmerged), so this is the top latency-area item of the census Top-20 not in flight:
**#1459**, the native Discover cold-compute tail, census rank 3.

LAT-P103's and LAT-P104's post-deploy checks are **still owed and still unrunnable** —
`/api/health` reads `6010f4b4`, which is `origin/master`, and none of the four ready branches
is on it. Nothing in this window could discharge them.

## The measurement, and what it isolated

Eight cold builds, eight fresh principals, eight unwarmed shapes (`limit=31..38`), production
slug `6010f4b4`, 2026-08-28 ~09:2x PDT, `x-feed-cache: miss` **8/8**, read from
`X-Feed-Stages`:

| n | limit | total ms | `futures` | `.market_load` | `.scoring_loop` | **unattributed inside `futures`** |
|--:|--:|--:|--:|--:|--:|--:|
| 1 | 31 | 2146.79 | 1410.94 | 518.12 | 381.54 | ~480 |
| 2 | 32 | 1626.95 | 1022.68 | 461.81 | 240.47 | ~300 |
| 3 | 33 | 1565.15 | 1350.11 | 560.16 | 303.69 | ~456 |
| 4 | 34 | 1143.51 |  929.95 | 239.21 | 288.73 | ~383 |
| 5 | 35 | 1660.10 | 1270.65 | 502.09 | 295.63 | ~452 |
| 6 | 36 | 1551.60 | 1127.42 | 448.48 | 285.02 | ~380 |
| 7 | 37 | 1925.70 | 1511.32 | 818.68 | 327.72 | ~335 |
| 8 | 38 | 1344.61 |  809.50 | 188.80 | 277.92 | ~330 |

`futures` is **75 %** of the median cold build. One admin trace
(`debug=true&debug_ground_truth=false`) gives the full stage list rather than the header's
top-8, so the gap is arithmetic rather than inference:

```
futures.candidate_base_fresh    3.57
futures.market_load           310.66
futures.canonical_counts       17.16
futures.interestingness_cache  10.97
futures.scoring_loop          323.78
futures.caps                    0.42     elapsed = 1597.88
futures                      1012.53     elapsed = 1943.81   <-- 345.93 ms, NO stage mark
```

Predicted second-pass cost: `scoring_loop 323.78 + canonical_counts 17.16 +
interestingness_cache 10.97 = 351.91` — **within 2 % of the measured gap**, and `market_load`
is correctly absent because Queue 305 already made the broaden pass reuse the hydrated base.

**Nothing else is in that window.** Between `_score_futures` returning and the `futures` mark
the route runs only the thin-pool broaden block and `_dedupe_futures_by_canonical` (an O(n)
dict walk over ~60 items). The gap is the second pass.

### Why it stayed hidden for four cycles

The broaden call passed **no `timing_records`**. It was invisible to `X-Feed-Stages`, to the
`debug=true` trace, and to the structured log line — every instrument this lane has been
reading. `tests/test_feed_broaden_pass_reuse.py`'s own docstring said so in April and the
sentence was true the whole time; Queue 305 acted on the half of it about `market_load` and
left the scoring loop.

## The fix

One pass produces both pools.

The two knobs the broaden pass varies — `stale_no_movement_days` and
`no_resolution_stale_days` — reach **exactly one decision** in the whole scoring path, the
`runtime_filters["eligible"]` gate at `feed.py`, and never a score. And the relaxed pair is
**never tighter** than the strict pair: `max(3s, 7) >= s` for every `s` (below 7 the floor
binds, above it the multiplier does), same for `max(2s, 14)`. So the strict pool is always a
**subset** of the relaxed pool.

The loop therefore gates on the relaxed thresholds and asks the same already-computed
intermediates — `days_stale`, `has_any_movement`, `resolution_date` — what the strict pair
would have said. Three comparisons per market, in place of a second pass over every market.
Both pools then run the **identical** dedupe + caps they ran before, separately, because the
caps are a function of the pool they see and the two passes always saw different pools.

`_market_runtime_filter_trace` returns `eligible_strict` **only when asked**. An
always-present key is a key someone starts reading.

## Identity is proven, not asserted

The legacy two-pass path stays **whole** in the tree behind `FEED_FUSED_BROADEN_PASS`
(default ON, read per call). It is three things at once: the rollback, the fallback, and the
**oracle** — a gate drives one fixture through both paths and requires the merged, served
list to be equal item for item, in order, including every score and reason.

The fixture is certified before it is trusted: a separate test asserts the two passes
genuinely **disagree** on it (strict admits 4 markets, relaxed admits 6). Without that, every
equality below it would hold no matter how badly the fusion were wired.

Three shapes are covered: the pools disagree, the pools coincide, and the strict pool is
**empty** (the shape #1090 exists for).

## Gates

**Full backend suite, ONE run, unpiped, exit code read by VALUE, on the committed tree
`64fbd218`:** `20462 passed, 112 skipped, 61 xfailed, 115 warnings in 841.86s (0:14:01)` —
**EXIT CODE: 0.** LAT-P104's baseline on the branch below this one was **20426**; delta
**+36**, exactly the new gate file. That number was predicted before the run and matched.

An earlier run of the same tree produced the identical counts but its exit code was **not
captured** — the launcher swallowed it. That run is **discarded, not quoted**: a summary line
is not an exit code (gotcha #124), and the gate was simply re-run. Both runs agreeing on
20462/0 is a reproducibility note, not the gate.

**RED-FIRST — eight mutations, each applied ALONE from a `cp` backup, every restore verified
by `cmp` AND `shasum` against a pristine manifest before the next was applied.** LAT-P100
lost an entire battery to mutations silently stacking on a restore that matched no pathspec
(gotcha #51); the manifest is the cheap defence. The harness also refuses a mutation whose
pattern matches nothing, so a no-op cannot read as a pass.

| | mutation | result |
|---|---|---:|
| M1 | the fused path returns the RELAXED pool as the strict one | **3 fail** |
| M2 | the relaxed windows stop being relaxed | **4 fail** |
| M3 | the second verdict always says yes (strict gate stops existing) | **4 fail** |
| M4 | the route reverts to two passes | **1 fail** |
| M5 | strict-only blockers derived at the RELAXED thresholds (copy-paste) | **4 fail** |
| M6 | the broadened pool skips the dedupe + caps | **3 fail** |
| M7 | the relaxed floor inverts (`min` for `max`) | **3 fail** |
| M8 | the broaden work goes back to being unnamed in the timings | **1 fail** |

**M1 is the load-bearing one** — it is the failure that would put stale cards on a real feed,
and it is the only mutation whose damage a user would see.

**M4 is named as a weakness, not a strength.** It is caught by exactly one test, and that
test is a *source* guard. No behavioural test can catch it, because the legacy path is
*correct* — just twice as slow. The behavioural sentinel for the win is therefore
`futures.broaden_finalize` in production's `X-Feed-Stages`, which is why that mark exists.

## What is NOT claimed

- **No wall-clock delta is claimed from a local run.** The cost is asserted as a **count** —
  the fused pass evaluates the runtime filter `N` times where the legacy path evaluates it
  `2N`. A wall clock in a test measures the laptop.
- **No production AFTER read.** Nothing here is deployed. The post-deploy bar is
  pre-registered in `lat-p105-fused-broaden-prereg.md`, committed **before the first build
  line**, and is OWED.
- **The saving is not the whole 383 ms in every case.** The fused pass does score the
  relaxed-only markets that a *fat*-pool build would previously have skipped entirely (today
  the second pass does not run when the pool is ≥ 100). In an off-season lull, where the pool
  is always thin, that case does not arise; in season it is a small, bounded addition against
  a large removal. It is not hidden and it is not modelled — it is a real, named difference.
- **One behaviour DOES change under budget pressure.** Today, if the primary pass finishes
  and the broaden pass then exceeds the remaining budget, the route serves the primary pool.
  Fused, there is one pass, so a timeout loses both and the build degrades to events-only.
  The window is narrower than before (one pass costs strictly less than two), but it is not
  zero, and `FEED_FUSED_BROADEN_PASS=0` restores the old failure mode without a deploy.

## Rollback

`heroku config:set FEED_FUSED_BROADEN_PASS=0 -a bainluck` — **no deploy**. Restores the legacy
two-pass path, including Queue 305's `market_load` reuse. Code revert is a single-commit
`git revert`. No migration, no beat change, no DDL, no index.
