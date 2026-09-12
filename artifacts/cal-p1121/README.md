# CAL-P1121 — sizing the writer bar over the WHOLE published population (#5401)

> ## THE ANSWER (measured 2026-09-12, both arms complete, 0 irreducible chunks)
>
> | | |
> |---|---:|
> | baseline arm (master semantics) | **399,618** |
> | repaired arm (writer bar applied) | **305,484** |
> | rows the bar removes | **94,134** |
> | as a share of Kalshi | **23.56%** |
> | **as a share of the published population → `expected_drop_pct`** | **12.04%** |
>
> **This is at the very top of CAL-P1120's honest 1–13% bracket and three times
> the ~4% the ship was scoped around** (this file's own earlier draft reasoned
> from "Kalshi's own 8-9%"). It is not a tidy repair, and it is NOT declared:
> `CALIBRATION_POPULATION_VERSION` is still `q269` on this branch on purpose.
> See "Why this is measured but not declared" below.



CAL-P1120 built the writer-bar exclusion, measured it on two cells, and stopped:
`CALIBRATION_POPULATION_DECLARATION` states the move over the whole curve and
`evaluate_publish` refuses the rebuild if the realised move misses it by more
than `tolerance_pct` — and **a refusal clears the checkpoint**, so every later
rebuild is binned for the same reason until another deploy corrects it. The
handoff's honest bracket was ~1%–13% against a 5.0pp hard maximum tolerance, so
the number had to be measured.

This directory is that measurement. The headline is in
`population-move.txt`; this file is why it is believed.

## The handoff's plan could not have produced a declarable number

It was: fold the seven big Kalshi categories one at a time with
`calibration_fold_opening_source.py --split writer_bar`, sum the below-bar
`kept_*` rows, divide by 782,077. Three independent defects break that.

### 1. The fold's `--max-id` default was stale, by 15.1% of the source

`--max-id` defaulted to the literal `60_097_325`, measured once in CAL-P1118.
Measured 2026-09-12:

| | markets |
|---|---:|
| Kalshi markets total | 316,132 |
| …with `id >= 60,097,325` (invisible at defaults) | **47,767 (15.1%)** |

It is not spread evenly. The `other` category is **11,755 of 11,858 above the
bound — 99.1% invisible**; baseball loses 8,110, soccer 6,880, tennis 5,509.
A ceiling over a table that only grows has to be read, not remembered.

*The two banked cells survive this*: golf has **40** markets above the bound of
3,452 (1.2%) and entertainment **318** of 5,764 (5.5%). CAL-P1120's
0.762 → 0.954 and 0.828 → 1.089 stand. It is the source-wide sum that could not.

Fixed: `--max-id` now defaults to `None` and is measured at run time in both
`calibration_fold_opening_source.py` and `fold_dedup_verdict_cell.py`, guarded
by `test_no_id_sweep_carries_a_frozen_upper_bound` /
`test_the_bound_is_actually_measured_before_use` (both red-checked three ways:
restore the literal, delete the resolution, rename the helper).

### 2. Chunking by `fm.id` changes the population it is measuring

`event_sizes` and `group_sizes` are computed **inside** `market_info_extra`, so
an event whose markets straddle a chunk boundary is counted short, its
`event_size >= 3` test flips, and its markets fall out of their grouped `vm_id`
into singletons — moving `is_grouped`, `vm_stats`, `field_completeness` and the
`deduped` ladder. That is not a rounding error; it changes **which rows the
measurement believes are published**.

Measured on Kalshi, of 13,782 event-groups with ≥3 markets (91,469 markets):

| id-span of the group | groups |
|---|---:|
| < 1k | 8,360 |
| 1k – 100k | 869 |
| 100k – 1M | 3,265 |
| ≥ 1M | **1,288** (max span 58,659,423) |

So the fold's default 1M width splits 1,288 groups *by construction*, and
adaptive splitting on timeout makes the answer depend on **where the timeouts
happened** — the same sweep twice can disagree.

A useful fact found on the way: **every Kalshi market has a unique `group_id`**
(316,132 groups of size 1), so the `group_size >= 3` arm never fires for this
source and `event_id` is the only cross-market key that matters here. 141,645
Kalshi markets carry an `event_id`; the other ~174k are `m:` singletons that no
id boundary can split.

### 3. The fold's `kept_*` verdict cannot express the second-order drop

The writer bar is wired into `field_completeness` as well as `deduped`, so a
field that loses **one** member to the bar becomes PARTIAL and is dropped
**whole** — above-bar members included. `VERDICT_CASE` has no writer-bar arm but
it does read `is_field_incomplete`, which on this branch is already computed
*with* the bar. So the fold's "before" arm is a hybrid: the bar is off at the
representative ladder and on inside field completeness. Counting the below-bar
cohort therefore **understates** the move — in the one direction that trips
`population_shrink`.

## What was measured instead

Not the below-bar cohort: **the published population itself**, twice, in the
same window.

`deduped` is the CTE `bucketed` selects from, and `COUNT(*)` over it is the
payload's `total_outcomes` — confirmed against the live q269 payload, where
`by_source` sums to 782,077 exactly and the buckets sum to the same. So:

* **baseline arm** — `is_below_writer_bar` forced to `false`. This is master's
  semantics *exactly*: `git diff origin/master` on the producer is **145
  insertions, 0 deletions**, and inside the CTE builder those are one column
  plus three `AND NOT ro.is_below_writer_bar` clauses, so neutralising the
  column neutralises all three at once. The substitution asserts it matched
  exactly once and raises otherwise — measuring one arm twice would report a
  move of zero and read as "the repair does nothing".
* **repaired arm** — the branch as it stands.

Both arms are chunked **event-atomically**: markets carrying an `event_id` are
partitioned by half-open ranges of the `event_id` *value*, so every market of an
event lands in the same chunk whatever the row counts do; markets without one
are partitioned by `fm.id`. Splits on timeout halve the *key* range, so they
stay event-atomic too. The top bound is open-ended, so markets ingested during
the sweep are counted rather than silently dropped.

Boundaries are weighted by **outcomes, not markets**
(`calibration_population_boundaries_5401.py`). Equal-market chunks still
death-spiralled: around `event_id` 12,080,xxx sit events carrying 16–17 markets
and 200–315 outcomes each, so a chunk with its fair share of markets held many
times its share of outcomes — 5 chunks yielded 170 rows in 54s. Outcome
weighting cut the split count from 22 to 5 over the same opening stretch.

**The drop is the difference between the two arms, never `published payload
minus measured arm`.** `futures_markets` grows while a ~40-minute sweep runs, so
an arm measured now against a bank published hours ago carries that growth as if
it were the repair's effect. The payload's Kalshi count is used only as a
**control** on the baseline arm.

### The control

The baseline arm must reproduce the live payload's `by_source` Kalshi `n`
(**396,160** at q269, `generated_at 2026-09-12T00:16:35Z`). That one number
tests the id bound, the event-atomic chunking and the per-source restriction at
once. Compare against `by_source` and never `by_category` — the latter sums to
756,873 because `min_category_outcomes = 1000` gates small cells out of that
breakdown only, which would look like a 25,204-row discrepancy that is not one.

`irreducible` chunks are fatal, not cosmetic: their rows are simply missing, so
`calibration_declaration_5401.py` refuses to compute a move if either arm
recorded any.

## Is the rule an improvement? Yes in aggregate, and no on most cells

Judged on the cells a reader can actually see — `min_category_outcomes = 1000`
gates the rest out of `by_category` entirely, so `sumo` 29→0, `olympics` 36→2,
`energy` 415→16 and `athletics` 1→0 are not cells vanishing from the page; they
were never on it. **No displayed cell falls below the display floor.**

| | before | after |
|---|---:|---:|
| weighted mean \|ratio−1\| | 0.0666 | **0.0370** |
| unweighted mean \|ratio−1\| | 0.0761 | **0.0590** |

So the curve gets substantially more accurate overall — and **10 of the 16
displayed cells move AWAY from 1.0.** The gain is concentrated in the cells that
were badly broken (golf 0.248→0.051, entertainment 0.170→0.073, economics
0.126→0.054, motorsports 0.170→0.115, and baseball — 44% of Kalshi's rows —
0.080→0.017). The losses are mostly small degradations of cells that were
already good: weather 0.001→0.022, esports 0.003→0.026, football 0.010→0.016.
The worst regression is **hockey 0.014→0.092**; soccer 0.087→0.117 was already
poor and gets poorer.

**Every cell's ratio moves in the same direction — up.** That is the signature
of removing a cohort in which implied winners systematically exceed real ones,
not of a filter that happens to help some cells. Whether a cell moving away from
1.0 is *damage* is genuinely undecided: #5431 found `kalshi/entertainment`'s
0.828 was two opposite errors cancelling, so a cell that reads 1.003 today may
be cancelling too, and removing one error legitimately exposes the other. This
table cannot tell those apart and should not be read as if it can.

One shape worth knowing: **`other` goes UP, 1,409 → 1,436.** A pure exclusion
cannot add rows. The bar also feeds `field_completeness` and the grouping, so
dropping members can take an event under `event_size >= 3`, splitting a grouped
`vm_id` into singletons and *increasing* that cell's published count. The
headline is the net, which is what the two arms measure.

## Why this is measured but not declared

Three reasons, and the third is the one that bites.

1. **12.04% is not 4%.** A bump was authorised (Fable 1815PT 9/11) on a number
   nobody had yet; the number is three times the working assumption and removes
   an eighth of the published curve. That is a product-visible change to the
   accuracy page, not a tuning fix.
2. **The rebuild is stalled.** At the time of writing the curve has not
   published since `00:16:35Z` (~4 h) and four consecutive beats completed
   **zero** units (`staged:unit_cost_reason:no_unit_completed`), with
   `rebuild_units_banked` pinned at **50 of 128**. A version bump is the
   `checkpoint_version`, and WIP explicitly discards on mismatch ("recompute
   from scratch"), so bumping now throws away the 50 banked units and restarts a
   rebuild that currently cannot finish a unit. Written up in
   `runner-inbox/fable/FROM-calibration-1121-0311Z-…`.
3. **The realised drop DECAYS with the delay, and that is a property of the
   gate, not of this measurement.** `evaluate_publish` computes
   `drop_pct = (prev_pop − cand_pop) / prev_pop` against the *banked* q269
   population (782,077, fixed at `00:16:35Z`). The candidate is measured
   whenever the rebuild finishes, by which time the population has grown, and
   growth **offsets** the drop:

   ```
   realised drop_pct ≈ (94,134 − growth_since_the_q269_bank) / 782,077
   ```

   `overshoot = |drop_pct − expected_drop_pct|` must stay inside
   `tolerance_pct`, whose hard maximum is 5.0pp. So a declaration of 12.04 is
   only correct if the rebuild lands promptly after the bump; a long delay walks
   the realised number down out of its own band, and **a refusal clears the
   checkpoint**, binning every later rebuild until another deploy corrects it.

   **I could not pin the growth rate, and I am not going to pretend otherwise.**
   `futures_outcomes.last_updated` is useless for it (bulk writers touch it —
   one hour shows 80,763 "resolutions"), the ring carries no population gauge,
   and `durable_state_snapshots` keeps one row per identity so there is no
   history of past banks. The only bound is this rig's own control: the baseline
   arm reproduces the published Kalshi count to **+3,458 (+0.87%)**, which is
   growth and rig error *together* and cannot be split. Read it as the
   declaration's precision floor: ≈0.9% of Kalshi ≈ **0.44pp** of the total.

   Consequently **`tolerance_pct` is a timing decision, not a number to pick off
   this page.** If the bump and a completing rebuild are hours apart, 12.04 with
   a wide tolerance (4–5pp) is defensible. If the rebuild stays stalled, no
   tolerance inside the 5.0 ceiling is safe, because the offset is unbounded.

A known bias, small at this magnitude: the two arms are ~1.5 h apart (baseline
midpoint ~02:11Z, repaired ~03:42Z) rather than in the same window as the method
above intends, so growth during the gap inflates the repaired arm and
**understates** the drop — the direction that trips `population_shrink`. Bounded
by the same 0.87% control, that is ≈0.35pp against a 12.04pp move (≈3%), which
is why a third arm to correct it was not run.

## Files

| file | what |
|---|---|
| `boundaries.json` | the measured chunk boundaries + the method that produced them |
| `population-baseline.json` | master semantics, Kalshi published rows per category |
| `population-repaired.json` | the branch, same shape |
| `population-move.txt` | the control, the move, the per-cell table, the declaration |

Reproduce:

```bash
source ~/.claude/.env
python3 backend/scripts/calibration_population_boundaries_5401.py \
    --target-outcomes 2500 --out artifacts/cal-p1121/boundaries.json
python3 backend/scripts/calibration_population_move_5401.py --arm baseline \
    --boundaries artifacts/cal-p1121/boundaries.json \
    --out artifacts/cal-p1121/population-baseline.json
python3 backend/scripts/calibration_population_move_5401.py --arm repaired \
    --boundaries artifacts/cal-p1121/boundaries.json \
    --out artifacts/cal-p1121/population-repaired.json
python3 backend/scripts/calibration_declaration_5401.py \
    --baseline artifacts/cal-p1121/population-baseline.json \
    --repaired artifacts/cal-p1121/population-repaired.json
```

Each arm takes ~40 minutes at ~15 requests/min. The two can run concurrently
(~30/min stays under the 60/min per-identity limiter, and doing so did not raise
the split rate), but a third reader alongside them would not.
