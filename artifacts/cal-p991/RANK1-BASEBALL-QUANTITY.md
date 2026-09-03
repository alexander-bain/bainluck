# CAL-P991 — board rank 1, `polymarket/baseball/quantity`: the mechanism is a pair that does not sum to 1

**Measured:** 2026-09-02 evening PT / 2026-09-03 UTC, against production.
**Curve:** `population_version q269`, `generated_at` 04:33:51Z (the fold self-checks against
whichever rebuild it read; the q269 population is unchanged across them).
**Cell before:** published **n 5,730 · ECE 6.74 · gap −1.88** (`exact-poly-baseball-mtype.json`,
folded through `_calibration_population_ctes()` — the producer's own chain).

The cell the previous cert closed was rank 6 (`basketball/quantity`, a half-book). This is the
cell above it, and its mechanism is a **different** one. That is the finding as much as the
mechanism is: the two cells at the top of the board fail for unrelated reasons, and a rule
designed on either one does approximately nothing to the other (§5).

---

## 1. The shape says MIXTURE, not mispricing

Per-bin, published population:

| bin | n | mean p | win rate | Δ |
|---:|---:|---:|---:|---:|
| 0 | 874 | 0.0468 | **0.1705** | +0.124 |
| 1 | 635 | 0.1385 | **0.3055** | +0.167 |
| 2 | 821 | 0.2285 | 0.2375 | +0.009 |
| 3 | 509 | 0.3461 | 0.3752 | +0.029 |
| 4 | 503 | 0.4437 | 0.4652 | +0.022 |
| 5 | 617 | 0.5370 | 0.5186 | −0.018 |
| 6 | 465 | 0.6449 | 0.6344 | −0.011 |
| 7 | 400 | 0.7465 | 0.6825 | −0.064 |
| 8 | 424 | 0.8529 | **0.7453** | −0.108 |
| 9 | 482 | 0.9310 | **0.8237** | −0.107 |

Bins 2–6 are calibrated to within 3 pp. Both tails collapse toward the middle. **No monotone
mispricing produces that**; pooling a calibrated population with one whose outcome is independent
of its price does exactly that, because the decoupled rows sit at every price and win at the
pooled base rate. Solving the two-point mixture on bins 0 and 9 puts the decoupled share near
60% of the sub-family carrying it.

## 2. Which rows are decoupled — by prop family (`fold_prop_family_cell.py`, raw cell, 0 irreducible)

Polymarket names these markets `"<subject>: <family> O/U <line>"`. Splitting on the family and
reporting each with its own bins, truth-eligible arm:

| family | n | ECE | gap | win% at p<0.2 | win% at p>0.8 | **spread** |
|---|---:|---:|---:|---:|---:|---:|
| *(empty — game totals, `"A vs. B: O/U 8.5"`)* | 3,556 | **13.13** | −6.32 | 37.5 | 69.0 | **31.5** |
| Home Runs | 5,744 | 5.52 | −0.71 | 13.6 | 92.3 | 78.7 |
| Strikeouts | 1,002 | 2.64 | +0.85 | 12.0 | 87.5 | 75.5 |

The question is not which family is biggest, it is **which family's win rate is flat in price**.
The player-prop families move ~76–79 points from the cheap legs to the dear ones. The game-total
family moves 31.5, and inside it the first four bins are 0.368 / 0.382 / 0.380 / 0.393 while the
price runs 0.041 → 0.344. A price that does not move the outcome is not a mispriced forecast.

## 3. Reading the rows says why, in one line

```
Chicago White Sox vs. Detroit Tigers: O/U 7.5    Over 0.0100
Chicago White Sox vs. Detroit Tigers: O/U 8.5    Over 0.0800   <- WON
Chicago White Sox vs. Detroit Tigers: O/U 9.5    Over 0.0800
Chicago White Sox vs. Detroit Tigers: O/U 10.5   Over 0.0400 / Under 0.1500
Cincinnati Reds  vs. New York Yankees: O/U 7.5   Over 0.0010 / Under 0.0010   <- Under won
Milwaukee Brewers vs. Atlanta Braves:  O/U 6.5   Over 0.0100 / Under 0.0005   <- Under won
```

Two mutually exclusive legs of one question, published at a sum of **0.0020** and **0.0105**.
Exactly one of them wins, always, so the honest sum is 1.0. The run-total ladder on one game is
also non-monotone across its rungs (0.01, 0.08, 0.08, 0.04, 0.08) — but the ladder is spread
across SEPARATE two-leg markets, one per line, which is why every `>= 3`-outcome rule in the chain
is structurally blind to it.

## 4. The hole in the producer's chain, stated exactly

| rule | reads | shape it covers | direction |
|---|---|---|---|
| `malformed_binary_filter` | the **winner count** | 2-outcome mex | n/a |
| `mex_normalization` | the **price sum** | **>= 3** outcomes | **upward only** (`> 1.15`) |
| `nonexclusive_bundle_filter` | winners / price sum | **>= 3** outcomes | upward |
| `orphan_partition_filter` | member count | `field` shape only | n/a |

> **Nothing in the chain reads a BINARY's price sum, and nothing in the chain looks DOWNWARD.**

## 5. The pair-sum fold (`fold_pair_sum_band_cell.py`, raw cell, 0 irreducible, 34.6 s)

Bands were fixed before the fold ran, at the producer's own `MEX_NORMALIZE_THRESHOLD` and its
reciprocal, symmetric in log space around 1.0 — lesson 13, a correction expected to run one way
must be able to run both. Truth-eligible arm:

| band | n | ECE | gap |
|---|---:|---:|---:|
| `a_sum_lt_0.25` | 226 | **44.10** | −44.10 |
| `b_sum_0.25_0.87` | 1,310 | **21.18** | −20.76 |
| **`c_sum_coherent`** | **8,157** | **4.28** | **+0.03** |
| `d_sum_1.15_4` | 76 | 17.53 | +15.80 |
| `y_one_leg_priced` | 533 | 24.52 | +18.90 |
| `z_not_two_leg` (control) | 4 | — | — |

`c_sum_coherent` — the 79% of the cell whose two legs sum to ~1 — reads **4.28 pp at a gap of
+0.03**, and it is monotone in price at every bin. The whole of the flatness lives in the bands
that do not sum to 1.

`y_one_leg_priced` is held OUT of the rule on purpose. A pair only one of whose legs was ever
priced has no pair sum to judge: its low sum is the capture's, not the writer's. It is 533 legs at
24.52 and it is a real, separate, **unfixed** defect — see §8.

## 6. The candidate — D1, `incoherent_binaries`

> A resolved two-outcome mutually-exclusive market **both** of whose legs carry a published price,
> whose two published prices sum outside `[1/1.15, 1.15]`, does not publish.

It is `malformed_binaries`' own sentence applied to the price side and in both directions. It
reads no outcome, picks no side, and mutates nothing (gotcha #21 is not engaged). Implemented as
one CTE beside `mex_field_divisor`, one flag on `ranked_outcomes`, one `AND NOT` in `deduped`, and
a cell allowlist for the reason `NONEXCLUSIVE_BUNDLE_EXCLUDED_CELLS` has one: a shape rule measured
on one cell is not thereby measured on twenty.

**Raw truth-eligible cell, before → under D1:**

| | n | ECE | gap |
|---|---:|---:|---:|
| pooled | 10,306 | 6.02 | −2.48 |
| under D1 | 8,694 | **4.82** | **+1.19** |

**Published population, before → under D1:** *(pending — see §9)*

## 7. Board-wide census of the rule — every cell, measured, 0 irreducible

Owed before any rule of this shape ships. `fold_pair_sum_band_cell.py` per cell, truth-eligible:

| cell | eligible 2-leg legs | D1 hits | share | coherent | 1-leg |
|---|---:|---:|---:|---:|---:|
| **baseball/quantity** | 10,302 | **1,612** | **15.6%** | 8,157 | 533 |
| **soccer/quantity** (board rank 2) | 8,261 | **794** | 9.6% | 7,462 | 5 |
| **tennis/quantity** (board rank 8) | 1,518 | **170** | 11.2% | 1,343 | 5 |
| esports/quantity | 889 | 27 | 3.0% | 861 | 1 |
| basketball/quantity (rank 6) | 2,090 | 48 | 2.3% | 2,042 | 0 |
| hockey/quantity | 1,133 | 4 | 0.4% | 1,128 | 1 |
| table_tennis/quantity | 342 | 0 | 0.0% | 342 | 0 |
| every `container_member` cell, `economics/quantity`, `politics/quantity`, `soccer/cm`, `tennis/cm`, `geopolitics/*`, `golf/cm` | 0 | 0 | — | 0 | 0 |

Thirteen of the twenty cells hold **no two-leg Over/Under market at all**, so the rule cannot
reach them by construction — that is the `z_not_two_leg` control doing its job, board-wide.

Effect on the two other cells it does reach (raw truth-eligible):

| cell | pooled | under D1 |
|---|---|---|
| **tennis/quantity** | n 1,518 · **5.21** · gap −0.10 | n 1,348 · **1.03** · gap +0.06 |
| soccer/quantity | n 8,295 · 5.32 · gap −0.49 | n 7,501 · **4.78** · gap −0.01 |
| basketball/quantity | n 2,106 · 5.74 · gap −0.28 | n 2,058 · **5.69** · gap +0.08 |

**`tennis/quantity` crosses the bar, 5.21 → 1.03.** And it is the cell that vindicates the
symmetric banding: 84 of its 170 hits are on the **over**-summing side, which a one-directional
rule copied from `mex_normalization` would have left in place.

**`basketball/quantity` — rank 6 — does not move.** The cell the previous cert measured has a
half-book, not an incoherent pair, and this rule correctly does nothing to it. Two adjacent cells,
two mechanisms, each rule inert on the other's cell: that is the strongest available evidence that
neither is a denominator move dressed up.

## 8. What is NOT fixed, named with its number

* **`y_one_leg_priced` — 533 eligible legs at 24.52 pp**, deliberately outside D1. On the
  published population its counterpart is visible in `--by ouside`:
  `over_alone|quantity` **943 legs at 13.81, gap +9.71** and `under_alone|quantity`
  **91 legs at 56.78, gap −53.95**. This is the same *orphan half of a two-leg market* class the
  previous cert's C2 attacks from the placeholder side, and a rule covering both is the obvious
  successor. It is **not measured on the published population as a rule** and is not proposed here.
* **The coherent residual, 8,157 legs at 4.28 pp, is still over the bar.** D1 removes the rows
  whose price is not a forecast; the ordinary miscalibration of the pairs that DO sum to 1 is
  undiagnosed.
* **`hockey/quantity`'s 11.01 pp sits entirely in the coherent band** (1,128 of 1,133 legs). Its
  mechanism is not this one and this fold rules this one out for it.

## 9. Not shipped, and the reason is the same one as last time

`precompute_calibration.py` is frozen (ruling 009). `calibration_freeze_score.py` at 03:38Z:

```
RULING 009 FREEZE SCORE — 22 of the last 24
  4/24 clean   (20 misses; 2 allowed)
  ...................###.#   <- oldest ... newest
  VERDICT  NOT_MET
```

Twenty of the window's twenty-four beats are the dark period. The candidate was applied to the
WORKING TREE only, folded through the producer's own CTE chain, and reverted; the patch is banked
as `D1-incoherent-binary.patch`.

**Owed before D1 ships:** (1) the freeze, `--baseline-at` the current deploy; (2) the published
before/after on `soccer/quantity` and `tennis/quantity` if their cells are added to the allowlist
— §7 measures them on the RAW cell only, and the two populations are not the same one
(the allowlist as written contains `("polymarket", "baseball")` alone); (3) an independent cert,
because this lane designed it.

## 10. Two instrument defects found while measuring, both fixed and guarded

Neither is in the frozen file.

1. **A throttle read as an oversized range.** `POST /api/admin/db-query` refuses with
   `429 Rate limit exceeded: 300/minute` and a `retry_after`. Every sharded fold treated any
   not-ok answer as "this range is too big" and bisected — which DOUBLES the request rate against
   the limit that just refused. Measured: one throttled range produced 14 `IRREDUCIBLE` entries in
   90 seconds, every one clean when re-asked alone. An IRREDUCIBLE range taints the run
   (gotcha #53), so the fold does not fail — **it prints a table for a population it never read.**
   The same 429 killed a 29-minute `calibration_cell_exact.py` run outright, because that script's
   generic HTTPError backoff is 2/4/6 s and the window it was waiting out is 60.
2. **A read-guard refusal read as an oversized range.** One apostrophe inside a `--` comment
   ("the CAPTURE's, not the writer's") makes the guard's quote scanner read the rest of the
   statement as a string literal and answer `Only SELECT queries are allowed`. Refused at every
   width, so the sweep bisected to the floor: **100+ IRREDUCIBLE ranges and a printed table.**

`scripts/sharded_sweep.py` is the one sweep both new folds now use, and it keeps the three shapes
apart: a timeout SPLITS, a throttle WAITS and re-asks the same range, a guard refusal RAISES.
`calibration_cell_exact.py` honours the server's own `retry_after` and does not spend its failure
budget on a throttle. Guards: `tests/test_sharded_sweep.py` (13) and the throttle class added to
`tests/test_calibration_cell_exact_transport_retry.py` (6 more). Red-first proved by mutation —
stubbing `is_throttle` to `False` reds exactly the four throttle tests and leaves the split /
truncation / floor controls green in both arms.
