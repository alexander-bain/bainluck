# LAT-P081 GATE 1 — the ruling-110 re-grade, taken at the gate

**Fired 2026-08-22 09:08:50 PDT.** Not before 09:08 per Fable's directive item 2, which is
`ROUTING_CHANGE_AT_EPOCH` (2026-08-21 09:08:40 PDT, v3882) + `RUN_COUNTER_WINDOW_S` (86,400 s).

```
horizon 24.0 h        counters_clear_the_move: TRUE
```

Production `a13239f1` / **v3884, unchanged since 2026-08-21 11:37:18** — a deploy watcher ran from
06:46 PDT through the gate and recorded **no release**. `worker-heavy.1` up 18 h+, untouched; all
nine watched beats are on `heavy`, so the `worker-background` recycle at 04:03 does not reach this
read.

Predictions for this gate were committed at 06:45 PDT in `lat-p081-pregate-predictions.md`, before
the read. **All nine held.**

---

## 1. The headline, and then the thing the headline hides

```
falsifier verdict : REVERT          (unchanged)
P3  FAILED        2/7 beats gradeable  [mirror]   ·  1/7  [live production]
P4  FAILED        flat_or_fell on BOTH movers
P5  PRE_HORIZON
exit code 1  (a prediction failed; no revert obliged — P5 is PRE_HORIZON, not REVERT)
```

**The routing stays HELD** (ruling 119). Nothing in this read disturbs that, and this section
explains why the REVERT is again not attributable — with a stronger control than yesterday's.

## 2. 🔴 THE CONTROL, SHOWN EXPLICITLY — it fires at 5.32×

`precompute_calibration_main`, 50-deep ring, split on each sample's own stamp against
`ROUTING_CHANGE_AT_EPOCH`. Pinned baseline p50 **214.7 s**; threshold 1.25× ⇒ anything above
**268.4 s** grades degraded.

| arm | n | min | **p50** | p95 | max | **ratio vs pinned** | fires? |
|---|---|---|---|---|---|---|---|
| **PRE-move — THE CONTROL** | 26 | 78.6 s | **1142.7 s** | 1356.7 s | 1397.8 s | **5.32×** | 🔴 **YES** |
| **POST-move — the treated arm** | 24 | 164.1 s | **1304.7 s** | 1399.9 s | 1407.0 s | **6.08×** | yes |

**The control fires at 5.32× — up from 1.82× yesterday.** The gap widened because the ring rolled
and the fast regime-A samples are aging out of *both* arms.

### The number that settles it

> **treated / control = 1304.7 / 1142.7 = 1.14×**
>
> which is **below the 1.25× threshold the instrument uses to declare degradation.**

Graded against its own control rather than against a baseline pinned before a regime change, the
routing shows **no degradation at all**. The 6.08× is the distance from a stale baseline; the
1.14× is the distance from the untreated concurrent arm, and only the second is an effect of the
move.

## 3. BOTH RING MODES, shown explicitly

| mode | n | range | median |
|---|---|---|---|
| **MODE 1 (fast)** | **6** | 78.6 – 165.0 s | 151.9 s |
| **MODE 2 (slow)** | **44** | 391.2 – 1407.0 s | 1276.4 s |
| between the modes (205–924 s) | 3 | 391.2 · 778.1 · 924.0 | — |

**The fast mode is dying out of the ring, exactly as the step-change model predicts.** Its count
has gone **21 → 9 → 6** across three consecutive daily reads while the ratio against the pinned
baseline has stayed ≈6×. That is the proof that the 6× is a **baseline** problem and not a
distribution problem: when the bimodality is fully gone tomorrow, the ratio will still be ≈6×,
because the baseline was pinned on the other side of a step that happened on **2026-08-20 at
~11:15 PDT — 21.5 h before the routing move** (cause: CAL-P078 in v3874; see #2102).

## 4. What the unmerged #2071 fix buys — exactly one row

The live endpoint and the offline mirror were graded on the same production observations at the
same instant. They differ in **one** place:

| beat | LIVE (prod `a13239f1`, old p95 censoring) | MIRROR (#2071 fix in place) |
|---|---|---|
| `precompute_calibration_main` | degraded 6.104× | degraded 6.104× |
| `compute_calibration_prices` | censored | censored |
| `compute_time_horizon_calibration` | no_new_runs | no_new_runs |
| `compute_fair_fight_comparison` | pre_horizon | pre_horizon |
| `precompute_source_intelligence` | pre_horizon | pre_horizon |
| `snapshot_coverage_metrics` | no_new_runs | no_new_runs |
| **`precompute_backfill_winners_status`** | **censored** | **`hold` 1.112×** |

⇒ **coverage 1/7 → 2/7**, and `observed_clip_rate = 0.4167` rides on the HOLD — #2071's own
clause, visible in production data: *a beat can hold on its median while a rising share of its
runs clip at the clamp.* 41.7 % of its runs are clipping and its median is still fine.

## 5. 🔴 P4 FAILED, AND THE FAILURE IS THE INSTRUMENT'S (#2110)

This was **prediction 6, recorded before the gate**, and it is the sharpest result of the window:
a prediction that the instrument would return the wrong answer, confirmed live.

| mover | raw | its ACTUAL window | **per 24 h** | scheduled | pinned | pre-move | **now** | falsifier | truth |
|---|---|---|---|---|---|---|---|---|---|
| `backfill_market_shapes` | 28 | **9.32 h** | **72.1** | 72 | 31 | 43 % | **100.1 %** | `flat_or_fell` | **ROSE** |
| `precompute_backfill_progress` | 43 | **10.37 h** | **99.5** | 96 | 45 | 47 % | **103.6 %** | `flat_or_fell` | **ROSE** |

`summarize_movers` compares a **9.32-hour count against a pinned 24-hour count** and concludes the
movers did not rise. `backfill_market_shapes` is running at **72.1 fires per 24 h against a
schedule of exactly 72**.

P4's literal claim is *"the two moved tasks' 24 h run counts RISE toward schedule, because they
were starved rather than idle."* **Both movers have reached schedule.** The prediction is
satisfied about as completely as it is possible to satisfy it, and the instrument grades it
FAILED.

**Cross-checked across two disjoint window lengths**, which is why this is not a one-read artifact:

| read | window | `backfill_market_shapes` | `precompute_backfill_progress` |
|---|---|---|---|
| 06:22 PDT | 6.45 h / 7.51 h | 74.4 /24 h | 102.3 /24 h |
| 09:08 PDT | 9.32 h / 10.37 h | 72.1 /24 h | 99.5 /24 h |

Two different windows, consistent rates. Filed as **#2110**.

## 6. Verdict

* **The routing is HELD.** Ruling 119 stands, on a control that is now 5.32× rather than 1.82×,
  and on a treated/control ratio of **1.14× — under the degradation threshold**.
* **P3's REVERT remains unattributable**, and #2102 now supplies the named, dated cause.
* **P4 is PASSED in substance and FAILED by the instrument.** The grade of record is FAILED
  because that is what the instrument returned; the finding of record is that the instrument is
  wrong, filed, reproducible, and predicted in advance.
* **P5 stays PRE_HORIZON** — `compute_fair_fight_comparison` and `precompute_source_intelligence`
  hold 3 post-move samples each against `MIN_POST_MOVE_SAMPLES = 8`, firing 4×/day, so 8 is not
  reached before ~2026-08-23.
* **Nothing here authorises a revert**, and `grade_ruling_110.py` exits 1, not 2.
