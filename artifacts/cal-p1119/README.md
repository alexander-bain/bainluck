# CAL-P1119 — sizing #5401 on the published population

Cited from `app/tasks/precompute_calibration.py` (the `KALSHI_WRITER_BAR_MET`
block). This file is the evidence behind that comment's claim that **two
readings of `opening_source` were refuted by measurement** before the writer-bar
rule was written.

Every number here is folded through the producer's own chain
(`_calibration_population_ctes`) by
`backend/scripts/calibration_fold_opening_source.py`, so it cannot drift from
the curve. Only `kept_*` verdicts are counted — an already-excluded leg is not
in the curve, and counting it would over-state the ship.

The metric is **winners / implied winners**, where 1.0 is perfect. The board
control is 0.982.

## The instrument reproduces the served cells

| cell | implied | won | fold | served |
|---|---:|---:|---:|---:|
| `kalshi/golf` | 4,455.6 | 3,395 | 0.762 | 0.762 |
| `kalshi/entertainment` | 1,062.6 | 880 | 0.828 | 0.831 |

Reconciling before believing a shape is the point (`kalshi/golf` runs
73,970 → … → 22,074 through the pipeline; the fold lands at 22,141, +0.3%, the
documented `fm.id`-chunking approximation).

## The core claim SURVIVES

Deficit (implied − won) by cohort, published rows only:

* `kalshi/golf`: untagged **+1,128.8**, `bid_ask_midpoint` −80.8 (mildly
  *under*-priced), `first_snapshot` +12.6 — net 1,060.6.
* `kalshi/entertainment`: untagged ≥0.80 alone **+149.8** of net 182.6.

A leg carrying a basis is priced almost exactly right in both bands and both
cells. The untagged cohort *is* the miss.

## …but both proposed repairs are REFUTED

**REFUTED 1 — "untagged means no book."** Cross-tab of provenance against the
earliest snapshot's book shape:

| cohort | legs | mean price | realised |
|---|---:|---:|---:|
| tagged, no book at all recorded | 3,041 | 0.324 | **37.7%** |
| untagged, with a two-sided book | 7,543 | 0.313 | **22.4%** |

The book shape does not discriminate — the well-calibrated group is the one
with *no* book. So a second predicate in `kalshi_empty_book.py` cannot work.
**Do not build it.**

**REFUTED 2 — the ≥0.80 cut.** It reaches 287.2 of golf's 1,060.6 deficit
(27%); **79% of golf's deficit is below 0.80** (12,513 legs at a mean 0.181
realising 0.114). Entertainment is the mirror image — 82% *above*. The two
cells are one cohort in two shapes, and one band cut cannot serve both.

**REFUTED 3 — `first_snapshot` is already gone** from the published high band
(6 legs golf, 56 entertainment). Extending #4745's predicate recovers ~nothing.

The lesson, and why the shipped rule is not keyed on the tag: **a `*_source`
column can be an artifact of write-path bookkeeping rather than a record of
method.** An untagged leg here is one whose INSERT arm never named the column —
the defect PR #5410 fixes — not one priced badly on purpose. Split by
provenance to *find* a cohort; read the writer before keying a rule on the tag.

## The rule that was written instead

`KALSHI_LIQUIDITY_EXISTS` admits any leg that ever showed `yes_bid > 0` OR
`last_price > 0`. The Kalshi poller only *writes* an opening when
`yes_bid > 0 AND yes_ask IS NOT NULL AND (yes_ask − yes_bid) < 0.50`. **The
curve has been publishing openings the writer itself would have refused.**

On `kalshi/golf`:

| cut | population removed | deficit captured | cell after |
|---|---:|---:|---:|
| provenance (untagged) | 58.4% | 1,128.8 (106%) | 1.038 — overshoots |
| **writer bar** | **26.5%** | **903.6 (85%)** | **0.954** |

Half the population move, 85% of the miss, and it lands next to the 0.982
control instead of overshooting past 1.0. It is also statable as a sentence
rather than a threshold.

## The second cell does NOT behave like the first

`kalshi/entertainment`, same cut (`writer-bar-kalshi-entertainment.json`):

| cohort | n | won | implied | ratio |
|---|---:|---:|---:|---:|
| below the writer bar | 1,936 | 315 | 544.1 | 0.579 |
| meets the writer bar | 1,912 | 566 | 519.6 | **1.089** |
| whole cell | 3,848 | 881 | 1,063.7 | 0.828 |

The cut removes **50.3%** of the cell and takes it 0.828 → 1.089: the absolute
error roughly halves (0.172 → 0.089) but **flips sign**. The cell was 0.828 by
two opposite errors cancelling, and the book-backed remainder is genuinely
*under*-priced (+2.8σ). That residual is a separate defect — **#5431** — not an
argument against this rule, and not something this rule claims to fix.

## 🔴 What is NOT measured, and why the rule has not shipped

The writer bar is a **source-wide** predicate, and Kalshi is
**396,160 of 782,077 published curve observations — 50.6% of the whole curve**
(`GET /api/calibration`, `generated_at 2026-09-12T00:16:35Z`, q269).

It has been measured on two cells totalling ~26,000 observations, and those two
cells are Kalshi's *least* liquid: golf has 3,452 markets and entertainment
5,764, against baseball 68,653, tennis 41,941, soccer 39,090, esports 35,147 and
basketball 33,666. Game markets plausibly almost always carry a tight two-sided
book, so the source-wide below-bar rate is probably far below golf's 26.5% — but
"probably" is not a measurement.

This blocks the ship, because `CALIBRATION_POPULATION_DECLARATION` must state
the expected whole-population drop and the publish gate holds it to that word
within `tolerance_pct` (max 5.0pp). The plausible range for the source-wide drop
spans roughly **1%–13%** of total population, which is far wider than the
declaration can absorb. A declaration that misses is not a soft failure: the
gate refuses as `population_shrink`/`version_bump_undeclared`, **and a refusal
clears the checkpoint**, so every later rebuild is binned for the same reason
until another deploy corrects it.

**The measurement still owed** is the below-bar rate on Kalshi's big game
categories, folded through the same chain. It is expensive: the cost is the
`EXISTS` over `futures_odds_snapshots`, which is why one cell takes 100–250s of
chunked folding and why plain aggregates over that join time out at the
db-query default. `--category all` is *not* the way to get it — each chunk
covers ~20× the rows, times out, and adaptively splits until the pass would take
hours (measured: 10 chunks in 252s, reaching only `fm.id < 31,251` of 60M).
Fold the big categories **one at a time** instead.
