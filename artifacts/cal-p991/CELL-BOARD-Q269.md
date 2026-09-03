# CAL-P991 — the board, re-measured on the first q269 publish

**Measured:** 2026-09-02 evening PT / 2026-09-03 early UTC, against production.
**Curve:** `generated_at 2026-09-03T01:39:11.051660+00:00`, `population_version q269`.
**Instruments:** `backend/scripts/calibration_scorecard.py --live` (payload board),
`backend/scripts/calibration_cell_exact.py` (the producer's own CTE chain, folded per
sub-cohort), and two new folds added by this queue —
`backend/scripts/fold_shape_class_cell.py` and `backend/scripts/fold_dedup_verdict_cell.py`.

---

## 1. The board moved, for the first time since 2026-08-24

`ARTIFACT-M-20260902-Y.md` recorded **0 of 22 cells fixed, last cell movement 2026-08-24**.
That was measured while `/api/calibration` was 503-dark. q269 published at 01:39Z and the
board can be read again:

| | q268 @ 2026-08-31T04:37:36Z | **q269 @ 2026-09-03T01:39:11Z** |
|---|---|---|
| cells at bar | 31 / 49 | **34 / 48** |
| cells queued | 18 | **14** |
| queued excess outcomes | 455,808 | **200,573** (−56%) |
| material outcomes | 889,436 | 695,553 |

Both readings come from the same instrument (`calibration_scorecard.py`, self-check
`by_category: 34/34 cells reproduced exactly · by_source: 7/7 reproduced exactly` in both).
The q268 column is quoted from `ARTIFACT-M-R-NEEDLES-20260902-01.md`, which is the last
board reading taken before the dark window.

### The five cells that crossed off

| cell | q268 ece / n | q269 | mechanism |
|---|---|---|---|
| **polymarket/baseball** | 4.71 / 45,252 | **2.85 / 15,496** | K′ — `is_player_props_placeholder` (R1 half-spike pair + R2 published-pair incoherence + R3 props container). CAL-P168, CERT-652 → CERT-662, merged `2aac5843` 2026-09-01 |
| kalshi/economics | 5.40 / 30,187 | at bar | the `kalshi/economics` structural exclusion |
| polymarket/esports | 7.03 / 14,864 | 2.35 / 9,795 | esports bundle exclusion |
| polymarket/soccer | 3.36 / 107,850 | at bar | (was already flagged `refuted` by measured-sigma at q268) |
| kalshi/crypto | 7.12 / 4,624 | at bar | D12 crypto |

🔴 **The delta is NOT attributable to any single ship.** q269 is the first rebuild since
2026-08-31 and it carries D5 de-dup, RULE E, K′, D12 and the `odds_api_bookmaker` writer
repair all at once (CAL-P213 §3 makes the same point about the population count). The
polymarket/baseball line is the one with a pre-registered prediction — CAL-P119 predicted
**4.71 → 2.71** and the cell reads **2.85** — and even there the population moved by −66%,
so the prediction is *corroborated*, not *isolated*.

### One cell went the wrong way

`kalshi/entertainment` 5.09 → **6.29** and is now the largest queued cell by excess
(29,353). Not diagnosed here.

---

## 2. Sub-cohort board (`polymarket`, category × market_type) on the published curve

Folded through `_calibration_population_ctes()` — the producer's own chain — so these are
the numbers a reader of the curve is looking at, not a re-implementation. Ranked by
`n × (ece − 3)`.

| cell | n | ece | gap (w−p) |
|---|---:|---:|---:|
| baseball/quantity | 5,730 | 6.74 | +1.88 |
| **basketball/quantity** | **1,687** | **15.43** | **−9.45** |
| hockey/quantity | 1,101 | 12.00 | −1.88 |
| economics/quantity | 4,514 | 4.89 | −0.35 |
| baseball/container_member | 221 | 19.95 | −13.42 |
| politics/quantity | 1,167 | 5.43 | −5.43 |
| economics/container_member | 707 | 6.57 | −2.09 |
| golf/container_member | 107 | 26.00 | −4.44 |
| basketball/container_member | 248 | 9.99 | −3.10 |
| politics/container_member | 167 | 10.32 | −5.25 |
| esports/quantity | 707 | 3.78 | −3.24 |
| esports/container_member | 8,015 | 2.29 | −0.55 |
| geopolitics/quantity | 32 | 12.68 | −4.68 |
| geopolitics/container_member | 7 | 35.57 | +13.29 |

`soccer` and `tennis` are still folding at the time of writing; `table_tennis`, `hockey/cm`,
`golf/quantity` are n≈0 as the 2026-08-24 board already recorded.

⚠️ **These are NOT comparable to the 2026-08-24 `ece_eligible` column.** That column came
from `fold_cohort_cell_eligible.py`, which folds the RAW cell (no dedup, no producer
exclusions) restricted to truth-eligible rows. This table folds what publishes. On
`basketball/quantity` the two disagree by 10 pp (5.73 raw-eligible vs 15.43 published), and
§3 is why.

---

## 3. `polymarket/basketball/quantity` — the board's named mechanism is REFUTED, and the
real one is a half-book

The board (`SUBCOHORT_DIAGNOSIS.md` rank 6 and rank 13) names this cell and its
`container_member` sibling **"price-value (#1978) — fallback share 0 EXECUTED, value
pending"**, with a predicted landing of 24 → ~3–5.

### 3.1 What the price rails say — nothing

`fold_shape_class_cell.py`, raw cell, 15 sargable shards, 0 irreducible, 18.8 s:

| class | truth | n | ece | gap |
|---|---|---:|---:|---:|
| ou_half2 (R1's both-legs-0.5000 pair) | eligible | 180 | **3.00** | −0.95 |
| ou_priced | eligible | 1,910 | 6.30 | −0.32 |
| ou_half1 | ineligible | 537 | 3.25 | −1.17 |
| ou_half2 | ineligible | 642 | 20.91 | +15.74 |
| ou_priced | ineligible | 9,819 | 30.84 | +3.33 |

R1's class — the mechanism that fixed rank 1 in baseball — reads **3.00 pp on 180 legs**
here. `PLAYER_PROPS_PLACEHOLDER_EXCLUDED_CELLS` is scoped to `("polymarket", "baseball")`
and the staged design's §6 said the spike was *"likely wider — but likely is not measured"*.
It is measured now: **for basketball it is not the mechanism.** (On the published curve the
class is 107 legs at 27.64; extending R1 would be worth taking, but it is 6% of the cell.)

### 3.2 Which legs publish — the hard zero

`calibration_cell_exact.py --by ouside` (a dimension added by this queue), published
population, self-check `n −0.61%, ECE −0.03` against the payload:

| class | n | share | ECE | gap |
|---|---:|---:|---:|---:|
| over_partner_kept \| quantity | 638 | 8.5% | 29.99 | **+29.99** |
| under_partner_kept \| quantity | 638 | 8.5% | 30.55 | **−30.55** |
| **over_alone \| quantity** | **407** | 5.4% | **40.43** | **+39.83** |
| *(there is no `under_alone` class at all)* | 0 | | | |

`over_alone` is 407 legs at a mean published price of **0.4966** that win **9.8%**. Its
partner did not publish. Not one Under is ever the leg left alone.

`fold_dedup_verdict_cell.py` (also new here) assigns every captured leg the FIRST
`deduped` filter that drops it, in the file's own precedence order:

| verdict | side | n | won | win% |
|---|---|---:|---:|---:|
| kept_multi | over | 1,039 | 82 | **7.9%** |
| kept_multi | under | 638 | 592 | 92.8% |
| **x02_poly_placeholder** | **under** | **398** | 364 | 91.5% |
| kept_rn1 | over | 6 | 4 | 66.7% |
| x13/x14/x15 + other | | 21 | | |

**`POLY_PLACEHOLDER_EXCLUDE` fires on 398 Under legs and on zero Over legs.** It is a
PER-LEG rule on a market that has two of them.

### 3.3 Why it is one-sided — book presence, measured

`clob_authoritative` cohort of this cell, by side and by snapshot bid/trade evidence:

| family | book | side | n | won | win% |
|---|---|---|---:|---:|---:|
| 1H O/U | has_book | over | 148 | **0** | **0.0%** |
| 1H O/U | no_book | under | 141 | 141 | 100% |
| 1H O/U | has_book | under | 7 | 7 | 100% |
| full-game O/U | has_book | over | 531 | 15 | **2.8%** |
| full-game O/U | no_book | under | 511 | 501 | 98.0% |
| full-game O/U | has_book | under | 20 | 15 | 75.0% |

**1,045 of 1,045 Over legs carry a book. 652 of 1,045 Under legs never showed a bid or a
trade at any price.** The Under leg is the writer's arithmetic complement of the Over —
the same shape CAL-P094 measured in baseball (924 of 924 no-book Unders), in a cell the
exclusion does not cover.

`POLY_PLACEHOLDER_EXCLUDE` then removes the bookless half and keeps the booked half, and
the booked half is the Over, and the Over loses. **The curve publishes half a book.**

### 3.4 The winners are the venue's, not ours — checked at the venue

Three of the 660 defective pairs were read directly from
`https://clob.polymarket.com/markets/<condition_id>`:

| market | our grade | venue `tokens[].winner` |
|---|---|---|
| Trail Blazers vs. Spurs: 1H O/U 110.5 | Under | Over **False**, Under **True** |
| Knicks vs. Spurs: 1H O/U 100.5 | Under | Over **False**, Under **True** |
| Raptors vs. Cavaliers: 1H O/U 104.5 | Under | Over **False**, Under **True** |

3 of 3 agree. **This is not a grading defect and no re-grade is proposed** (gotcha #21 is
not engaged: nothing here writes `is_winner`). The Over token really did lose. What is
wrong is that we publish it as a forecast when the market it came from had one side of a
book and the other side invented.

### 3.5 Where it lives

Concentrated in `fm.id` band 34M–36M, `commence_time` 2026-03-13 → 2026-06-07: **639 pairs,
Over wins 3 (0.5%)**. The neighbouring band 36M–38M is healthy (Over wins 12 of 19, 63%),
which is why a 20-row sample from that band reads normal and the cell does not.

---

## 4. Two candidates, both folded through the producer's own chain. C1 REFUSED, C2 works.

### C1 — "no half-books" (REFUSED by its own measurement)

*If EITHER leg of a two-leg Polymarket market never showed a bid or a trade, the market had
no price discovery and BOTH legs leave.*

| cell | q269 published | under C1 |
|---|---|---|
| basketball/quantity | n 1,687 · **15.43** · gap −9.45 | n **149** · **8.15** · gap −3.15 |
| basketball/container_member | n 248 · 9.99 · gap −3.10 | n **20** · **20.20** · gap +0.00 |

**REFUSED.** It removes **91%** of the quantity cell, leaves the residual over the bar, and
makes `container_member` WORSE on 20 surviving legs. A rule that deletes nine rows in ten
is a population policy, not a cell fix, and its number would be a denominator move
(the warning `QUEUE-STAGED-CAL-EXCLUDE-HALF-SPIKE.md` §4 and CAL-P118 both leave on record).

### C2 — the exclusion must be PAIR-SYMMETRIC (works)

*If `POLY_PLACEHOLDER_EXCLUDE` removed one leg of a two-leg market, the partner may not
publish alone.* It touches only rows that are **already half-excluded**, picks no side,
reads no outcome, and is the same sentence R1 already enforces for the 0.5000 pair.

| cell | q269 published | **under C2** | Δ |
|---|---|---|---|
| **basketball/quantity** | n 1,687 · **15.43** · gap −9.45 | n **1,289** · **8.85** · gap **−0.35** | **−6.58 pp**, gap → ~0 |
| basketball/container_member | n 248 · 9.99 · gap −3.10 | n **231** · **9.53** · gap **−0.29** | −0.46 pp, gap → ~0 |
| **polymarket/basketball (payload cell)** | n 7,591 · **4.43** · gap +3.17 | n **7,130** · **2.25** · gap **+0.88** | **−2.18 pp — under the 3.0 bar** |
| basketball/field (untouched control) | n 5,494 · 3.74 · +1.77 | n **5,494** · **3.74** · **+1.77** | **0** |

The removal is **exactly 398 legs** from `quantity` — 1,687 − 1,289 — which is the orphan
count `fold_dedup_verdict_cell.py` predicted to the unit before the fold was run. The
`field` control does not move by a single row, because it has more than two legs and C2
cannot reach it.

The gap is the honest signature here, not the ECE: **−9.45 → −0.35**. A cell whose price
sum stops disagreeing with its outcome sum by nine points is not a cell whose denominator
was trimmed.

🔴 **Still not a closed cell.** 8.85 pp on 1,289 legs is over the bar. C2 removes the
half-book bias; what remains is the ordinary miscalibration of the pairs that DO have two
books, and it has not been diagnosed.

🔴 **NOT COMMITTED. `precompute_calibration.py` is frozen (ruling 009) and the freeze is
measured NOT MET:**

```
$ python3 backend/scripts/calibration_freeze_score.py
RULING 009 FREEZE SCORE — 22 of the last 24
  3/24 clean   (21 misses; 2 allowed)
  ....................###.   <- oldest ... newest
  VERDICT  NOT_MET
```

The three clean beats at the newest end are the publisher coming back. Twenty-one of the
window's twenty-four are the dark period. The earliest the condition can be met is roughly
a day of unbroken hourly beats from 2026-09-03 ~01:39Z.

Both candidates were applied to the WORKING TREE ONLY, long enough to fold the cell through
the producer's chain with each, and then reverted —
`git status backend/app/tasks/precompute_calibration.py` is clean on this branch and
`git diff origin/master -- backend/app/tasks/precompute_calibration.py` is empty, so
**ruling 009 is not engaged by anything this queue commits.**

Banked: `C1-half-book-candidate.patch`, `C2-pair-symmetric-placeholder.patch`,
`exact-poly-basketball-mtype-C1.json`, `exact-poly-basketball-mtype-C2.json`,
`exact-poly-baseball-mtype-C2.json` (the neighbouring already-fixed cell, as the
must-not-regress control).

### What is owed before C2 can ship

1. **The freeze.** 22 of the last 24 clean beats, `--baseline-at` the current deploy.
2. **A board-wide census of the rule.** C2 is scoped to nothing — it changes every
   Polymarket two-leg market whose partner is a near-0.50 no-book leg, in every category.
   Basketball and baseball are measured here; the other twenty cells are not.
3. **An independent cert.** This lane designed and measured it, so this lane does not
   grade it.
