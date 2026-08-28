# LAT-P105 — pre-registration: the second futures scoring pass

Written **before** the first build line, committed with nothing else. Identity
`LAT-P105-20260828-w1561`. Parent issue **#1459** (native Discover cold-compute tail),
program issue **#1545**.

## The ship, in user terms

**Opening Discover cold stops paying for the futures pool to be scored twice.**

## The BEFORE measurement (production, already taken, `6010f4b4`, 2026-08-28 ~09:2x PDT)

Eight cold builds, eight fresh principals, eight unwarmed shapes (`limit=31..38`),
`x-feed-cache: miss` **8/8**, read from `X-Feed-Stages`:

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

Median total **1,594 ms**; median `futures` **1,199 ms** (**75 %** of the cold build);
median unattributed **~383 ms** (**24 %** of the cold build).

One admin `debug=true&debug_ground_truth=false` trace on the same slug gives the exact
timeline (`elapsed_ms` deltas, so the gap is arithmetic, not inference):

```
futures.caps          ms=  0.42   elapsed=1597.88
futures               ms=1012.53  elapsed=1943.81      <-- 345.93 ms with NO stage mark
```

## What the gap is

`feed.py` runs `_score_futures` a **second time** when the post-filter pool is thin
(`_THIN_FUTURES_POOL_FLOOR = 100`, #1090's broaden pass). The second call re-scores the
**identical candidate base** under relaxed staleness windows and then discards every
market the primary already returned. It passes **no `timing_records`**, so it is invisible
to `X-Feed-Stages` and to the debug trace — `tests/test_feed_broaden_pass_reuse.py`'s own
docstring already says so. Queue 305 removed that pass's `market_load`; its **scoring loop
was left in place**.

Predicted composition of the 345.93 ms gap: `scoring_loop` 323.78 + `canonical_counts`
17.16 + `interestingness_cache` 10.97 = **351.91**. Within 2 % of the measured gap.

## The claim this queue will make

Every candidate market is scored **once** per cold build instead of twice, and the served
feed is **byte-identical**.

Identity is provable rather than asserted, because the two staleness knobs the relaxed
pass changes (`stale_no_movement_days`, `no_resolution_stale_days`) feed exactly one
consumer — the `runtime_filters["eligible"]` gate at `feed.py:7133` — and never any score.
Relaxed thresholds are `max(strict*3, 7)` and `max(strict*2, 14)`, so they are **never
smaller** than strict, so `eligible_strict ⟹ eligible_relaxed` and the strict set is
always a subset of the relaxed set.

## Pre-registered gates (a failure of 1 or 2 is a ROLLBACK, not a re-interpretation)

1. **PRIMARY — identity.** A test drives the SAME fixture through the fused path and the
   legacy two-pass path and asserts the merged futures list is **equal**, item for item,
   in order. This must hold before any timing claim is read.
2. **The relaxed thresholds must never be tighter than the strict ones** — an executed
   test over the derivation, not a comment.
3. **The second pass must become visible.** After this change `X-Feed-Stages` names the
   broaden work under its own key, so the next window can read the gap rather than
   compute it from a subtraction.

## Pre-registered post-deploy bar (run on the first release that carries this commit)

Ten cold builds, ten fresh principals, `limit=31..41`, `x-feed-cache: miss` required
**10/10** (a miss rate below that VOIDS the run, exactly as LAT-P103/P104 pre-registered).

- **PRIMARY:** median unattributed-inside-`futures` (i.e. `futures` minus the sum of its
  own `futures.*` sub-stages) drops from **~383 ms** to **< 80 ms**.
- **SECONDARY:** median `X-Feed-Elapsed-Ms` on a cold build drops. Recorded, **not**
  graded — LAT-P100 measured one shape at 383.5 ms interleaved vs 1,034.5 ms paired,
  2.7× from Postgres buffer sharing alone, so a paired wall-clock read cannot carry a
  claim here.
- **GUARD:** `X-Feed-Counts` `type_futures` and `total` must stay inside the pre-change
  range (`total` 88 ± 15, `type_futures` ≥ 15). This change must not move how many cards
  a person is shown; if it does, it is a ranking change wearing a latency change's
  clothes, and it rolls back.

## Rollback

`heroku config:set FEED_FUSED_BROADEN_PASS=0 -a bainluck` — **no deploy**. The legacy
two-pass path stays in the tree, is the thing the identity test compares against, and is
what the flag restores.
