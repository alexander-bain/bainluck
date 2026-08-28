# RULE DESIGN — `kalshi/economics` (CAL-P114, #1978)

**Cell rank 2 of 19 · ECE 5.29 pp on 28,613 published outcomes · gap −0.47 · 65,524
excess-outcomes** (payload `2026-08-28T20:37:41Z`, population `q268`).

Status: **DESIGNED, NOT BUILT. Worth 0.00 pp today.** Banked so freeze-lift day is a merge, not
a cold start. The frozen file is untouched — `git diff origin/master -- backend/app/` is empty
on this branch.

---

## 0. The one-paragraph version

`kalshi/economics` is not a miscalibrated cell. It is a **mis-populated** one: 99.7% of it is
cumulative intraday index and commodity ladders — "Dow Jones above X at 2 PM", 35 rungs at the
median — published as 35 independent forecasts whose prices sum to a median of **21.66** instead
of 1. It is the third and largest instance of the defect CAL-P112 already designed rules for, so
it needs **no new mechanism**. What it needs is one correction to CAL-P112's banked design, and
the correction is forced by measurement rather than argued: **the bundle-exclusion allowlist must
be keyed on `(source, category)`, not on `category`.** Keyed on category, the rule that takes
`kalshi/economics` from 5.29 to **2.61 (PASS)** simultaneously takes `polymarket/economics` from
3.91 to **17.75**.

---

## 1. Why nothing could measure this cell until today, and what that cost

Both banked CAL-P112 instruments were run against this cell first. Neither reproduces it:

| rail | n | ECE | gap | verdict |
|---|--:|--:|--:|---|
| `calibration_cell_shape_fold` (shape census) | 69,653 | 4.65 | **+4.27** | 2.4x the rows, **wrong sign** |
| the same, with the truth-eligibility gate added | 55,425 | 3.41 | **+2.19** | 1.9x the rows, **wrong sign** |
| `calibration_cell_replica` | — | — | — | **cannot run** — caps at ~6,000 candidate rows; this cell has 69,653 |
| **`calibration_cell_exact` (CAL-P114, new)** | **28,738** | **5.29** | **−0.47** | **+0.55% on n; ECE and gap identical to 2 dp** |
| payload, same instant | 28,613 | 5.29 | −0.47 | |

This is not a pedantic point about instrument hygiene. **The census produced a confident,
monotone, entirely false mechanism**, and it would have been shipped:

| last pre-close snapshot age | census ECE | **exact ECE** |
|---|--:|--:|
| < 15 min | 2.86 | **8.81** |
| 1 h – 4 h | 6.35 | 6.62 |
| 4 h – 1 d | 8.89 | **4.70** |
| > 7 d | 10.52 | **3.81** |

On the census the story is clean and mechanical — *the price is stale, staleness is monotone with
error, exclude the stale rows*. On the rail that reproduces the cell the ordering **reverses**:
the freshest bucket is the worst and the stalest is the best, and there is no age mechanism at
all. Same dimension, same day, opposite conclusion.

> **The general clause.** A rail that has not been shown to reproduce the cell will still rank
> that cell's sub-classes, and the ranking will look like a mechanism. Reproduction is not a
> hygiene step performed before the real work — it is the thing that decides whether the real
> work is about the published population or about a different one.

`calibration_cell_exact` closes this permanently for every cell, not just this one: it does not
re-implement the predicate, it **imports `_calibration_population_ctes` from the producer** and
appends a `GROUP BY`. Three non-obvious things had to be true (§7).

---

## 2. Two hypotheses killed before the design, both by measurement

Recording them because the next lane will otherwise re-open both.

**A. "Part B of `backfill_winners` picks the FIRST price, not the last."** True, and a real
oddity — `backfill_winners.py:7495-7506` names its subquery `settled` and orders
`captured_at ASC LIMIT 1`, taking the first snapshot an hour after the market opened, while Parts
A, A2 and C all order `DESC`. It is **not this cell's defect**: 100.0% of `kalshi/economics`
candidate rows (69,653 outcomes / 2,507 markets) are `event_id IS NULL` **and**
`commence_time IS NOT NULL`, which is Part **A2**'s population — `DESC`, last snapshot before
close. Part B never touches them. *Parked to `PARKED-MEASUREMENTS.md`: which cells Part B DOES
own, and whether ASC is deliberate there.*

**B. "The price is captured too early."** `commence_time` for these markets is the answer
instant, not a start (`KXWTIH-26JUL2013` = "WTI price on July 20 at 1:00 PM ET",
`commence_time` = 2026-07-20 17:00Z). `resolution_date` sits a uniform 7 days later for 87% of
the cell and is a settlement-window artifact, not when the answer is known. Part A2's anchor is
correct, and §1's table shows the age dimension carries no signal on the exact rail.

---

## 3. What the cell actually is

Folded on the exact rail by market shape — the same `(n_outcomes, win_count)` basis
`market_result_shape` uses, which is *identical* to the producer's own
`nonexclusive_bundle_markets` predicate (`n_outcomes >= 3 AND win_count >= 2`):

| shape | n | share | ECE | gap |
|---|--:|--:|--:|--:|
| `bundle_multiwin` (>=3 outcomes, >=2 winners) | 24,794 | **86.3%** | 5.67 | −1.45 |
| `field_1win` (>=3 outcomes, exactly 1 winner) | 3,863 | 13.4% | 6.48 | **+6.48** |
| `single` | 73 | 0.3% | 29.23 | −29.23 |
| `binary_1win` | 5 | 0.0% | 21.20 | −20.00 |
| `binary_other` | 3 | 0.0% | 66.00 | −66.00 |

99.7% of the cell is one structure. Concretely — `KXDJI-26JUL2814`, "Dow Jones Industrial
Average price", `mutually_exclusive = false`, `market_type = quantity`: **76 outcomes, 76
winners, published price sum 72.48.** Across the 84 KXDJI markets in the population the median
is **35 rungs, 24.5 winners, price sum 21.66**.

By series, the cell is dominated by intraday index and commodity ladders:

| series | n | share | ECE | gap | what it is |
|---|--:|--:|--:|--:|---|
| `KXNASDAQ100U` | 3,870 | 13.5% | 10.88 | +1.61 | hourly Nasdaq-100 price ladder |
| `KXINXU` | 3,068 | 10.7% | 11.67 | −2.01 | hourly S&P 500 price ladder |
| `KXNATGASD` | 1,722 | 6.0% | 7.39 | +4.79 | daily natural gas |
| **`KXDJI`** | 1,702 | 5.9% | **23.49** | **−23.49** | Dow ladder |
| `KXNASDAQ100` | 876 | 3.0% | 4.99 | +4.94 | |
| *(~200 further series, none above 3%)* | | | | | |

`KXDJI`'s `gap == −ECE` exactly: **every** bin under-predicts, with no cancellation anywhere in
the cell's worst series.

### 3a. The finding that is bigger than this cell: the σ gate is inflated here

Criterion 3 of the scorecard gates on `σ = 50/√n` with `n` = published **rows**. In a cumulative
ladder the rungs are near-perfectly correlated — on any given afternoon the whole ladder lands on
one side of the index — so 28,613 rows carry roughly **2,507 markets** of independent
information. The gate reads **7.8σ**; on the market count it would read about 2.3σ. The cell is
established either way, and this is **not** an argument for keeping it. It is an argument that
criterion 3 overstates significance on exactly the cells that are dominated by bundles, which is
the population criterion 6 was proposed for. **Flagged for the threshold table, not resolved
here — this page does not get to redefine its own finish line.**

---

## 4. The rule

CAL-P112 banked two rules for this defect. Restated:

* **RULE T** — the bundle exclusion's *scope* becomes an evidence-gated allowlist instead of
  `category = 'esports'`.
* **RULE E** — the bundle *test* becomes STRUCTURAL: `>=2 winners` **OR** published price
  sum > 1.15, and never a proved-exclusive field. Plus **E2** (winner-only single capture) and
  **E3** (malformed binaries without the default-true `mutually_exclusive` gate).

Benched on the exact rail, cumulatively:

| policy | n | ECE | gap | excess-outcomes | verdict |
|---|--:|--:|--:|--:|---|
| **A_today** (control) | 28,738 | 5.29 | −0.47 | 65,810 | — |
| **B — T only** (drop realized >=2-winner bundles) | 3,944 | **5.73** | +5.73 | 10,767 | **WORSE than doing nothing** |
| **C — E** (drop bundle OR published sum > 1.15) | 1,722 | **3.00** | +0.24 | 0 | exactly at the bar |
| **D — E + E2 + E3** | **1,641** | **2.61** | +1.74 | **0** | **PASS, and still material** |

Two things a reader must not skip:

1. 🔴 **T alone makes this cell worse** (5.29 → 5.73). Stripping only the realized-many-winners
   half leaves the *same ladders on a quiet day* — `field_1win` at +6.48 — as the entire
   remainder. This is the identical trap CAL-P112 flagged for `polymarket/tech`, now measured a
   second time. **T must never ship into a cell without E.**
2. **D leaves 1,641 rows — above the 1,000 materiality floor.** Unlike `kalshi/tech` (which
   CAL-P112 correctly said falls below the floor and becomes an absence), this cell survives its
   own fix and **passes on the published curve**. That is a cell genuinely crossed off, not a
   cell that vanished.

The price-sum cross is what carries the argument, because it separates a real partition from a
ladder that happened to realize one winner:

| shape ǀ published price sum | n | ECE | gap |
|---|--:|--:|--:|
| `field1` ǀ **<= 1.15** — a genuine partition | 1,641 | **2.61** | +1.74 |
| `field1` ǀ 1.15–2 | 1,246 | 4.09 | +4.09 |
| `field1` ǀ 2–5 | 857 | **15.67** | +15.67 |
| `field1` ǀ 5–15 | 119 | **30.75** | +30.75 |
| `bundle` ǀ > 15 | 10,203 | 7.01 | −1.41 |
| `bundle` ǀ 5–15 | 9,334 | 5.46 | −1.67 |
| `bundle` ǀ 2–5 | 3,731 | 4.43 | −1.08 |

The `field_1win` class is not one class. Sorted by price sum it runs 2.61 → 4.09 → 15.67 →
30.75, monotone, and only the sum ≤ 1.15 slice is a forecast of one question. **A realization
test cannot see this and a structural test cannot miss it.**

---

## 5. 🔴 THE CORRECTION THIS QUEUE FORCES ON CAL-P112's BANKED DESIGN

`esports_multi_bundles` filters on `mrs.category` and **not on source**
(`precompute_calibration.py:1922-1928`). RULE T inherits that shape and proposes a **category**
allowlist. Measured on the exact rail, category-only scoping is wrong, and it is wrong in the
same direction twice:

All four cells the allowlist can reach, benched on the exact rail (ECE, with n in brackets):

| cell | A_today | B — T only | C — E | D — E+E2+E3 | verdict |
|---|--:|--:|--:|--:|---|
| **`kalshi/economics`** | 5.29 (28,738) | 5.73 (3,944) | 3.00 (1,722) | **2.61 (1,641)** | **ADMIT — PASS, still material** |
| **`polymarket/economics`** | 3.91 (12,952) | **7.01** (3,398) | **17.75** (1,117) | 5.10 (457) | **REFUSE — below floor at a worse error** |
| `kalshi/tech` | 11.01 (1,208) | 4.65 (250) | 7.24 (233) | 4.53 (183) | admit — but it becomes an ABSENCE |
| `polymarket/tech` | 5.04 (2,745) | 4.80 (1,144) | 4.48 (769) | 3.90 (707) | **REFUSE — below floor** |

Adding `economics` to a **category** allowlist fixes rank 2 and destroys rank 13: 3.91 → 17.75
under E, and under D the cell drops to 457 rows and leaves the board as an **absence at a worse
error**, which is ruling 075's second clause arriving on the scoreboard.

The two cells are the same word and different objects. `kalshi/economics` is intraday index
ladders where the bundle shape is 86.3% of the population and both halves are defective.
`polymarket/economics` carries a `single|sum<=1.15` class of 506 rows at **43.16 ECE / −43.16
gap** (a winner-only capture artifact, E2's population) and a `bundle|d_sum_5_15` class of 6,741
rows at **3.98 / +0.03** — a bundle class that is very nearly calibrated and is half the cell.

> **THE DESIGN CHANGE: the bundle-exclusion allowlist is keyed on `(source, category)`, and the
> evidence gate is evaluated per `(source, category)`.** `{('kalshi','economics')}` is admitted;
> `('polymarket','economics')` is not. This is one extra column in a tuple and it is the
> difference between crossing a cell off and silently deleting a different one.

### 5b. CAL-P112's parked `polymarket/tech` debt is DISCHARGED — and its direction was wrong

CAL-P112 could not land RULE T because `polymarket/tech` was **UNMEASURED**: the shape census
read 2,080 / 8.04 / **+5.10** against the payload's 2,657 / 5.40 / **−1.78** — 22% short on n and
the wrong sign. On the exact rail:

| rail | n | ECE | gap |
|---|--:|--:|--:|
| `calibration_cell_exact` | 2,745 | 5.04 | −1.09 |
| payload, same instant | 2,779 | 4.91 | −0.85 |
| *(CAL-P112's census, for contrast)* | *2,080* | *8.04* | *+5.10* |

Measured, **CAL-P112's stated cost for T on this cell does not reproduce.** That queue predicted
*"the census-level fold moves 8.04 → 12.62, i.e. worse"*. On the published population T alone
moves it **5.04 → 4.80 — marginally BETTER, not worse.** The census was wrong about the
direction, exactly as CAL-P112 suspected when it refused to claim the cell.

`polymarket/tech` is still **refused** from the allowlist, but for a different and now-measured
reason: the full rule takes it to 707 rows, **below the 1,000 materiality floor**, so it would
leave the board as an absence rather than a pass. The old reason ("T makes it worse") should not
be quoted again.

The same correction applies to `kalshi/tech`, which CAL-P112 landed honestly: it is admitted and
it still becomes an absence (183 rows). That was stated in CAL-P112 and remains true here.

### 5a. RULE T's evidence gate is mis-specified, and this cell is the specimen

RULE T admits a category when its bundle class is **worse than the remainder**
(`tech`: bundle 8.27 vs remainder 6.08). On `kalshi/economics` the gate reads bundle **5.67** vs
remainder **6.48** — bundle is *better* — so the gate **REFUSES the cell that the rule fixes by
2.68 pp.**

The gate presumes the remainder is a clean control. Here the remainder is 13.4% `field_1win`,
which is *the same ladders on a day the index landed on one rung*. There is no control in this
cell to contrast against.

Criterion 6 of CAL-P112's threshold table proposes the alternative in words: *"a cell whose
published population is dominated by non-partition bundle rows is queued for a population fix,
not scored as a calibration failure."* **Measured, dominance does not discriminate either**, and
this is worth stating before anyone writes it into a predicate — non-partition rows (bundle, or
published price sum > 1.15) as a share of the published cell:

| cell | non-partition share | D's verdict |
|---|--:|---|
| `kalshi/economics` | **94.0%** | PASS, still material |
| `polymarket/economics` | **91.4%** | below floor at a WORSE error — refuse |
| `kalshi/tech` | 80.7% | below floor — absence |
| `polymarket/tech` | 72.0% | below floor — absence |

94.0% and 91.4% are the same number for this purpose, and they sit on opposite sides of the
decision. **So neither contrast (§5a) nor dominance is a sufficient admission gate.**

> **The admission gate is the BENCH.** A `(source, category)` pair is admitted only when this
> rail, run on that pair, shows the cell ending **under the bar AND above the materiality
> floor** — with the before/after and the holdout recorded in its own design document. Dominance
> stays as a *necessary* precondition and a triage signal; it is not evidence on its own. Stated
> this way because the tempting version — a single percentage in a config — is exactly what the
> table above falsifies, and a threshold that cannot separate 94.0 from 91.4 is not a threshold
> (ruling 124).

---

## 6. Holdout — split on `market_id` 12,000,000, rule never re-fitted

`market_id` is monotone with creation, so NEW is genuinely later data, and the id is forced to be
a chunk EDGE so neither half is contaminated.

| half | cell today | after D | σ of the survivor |
|---|---|---|---|
| **OLD** (< 12,000,000) | 9,338 @ **6.55** / +0.25 | **441 @ 3.31** / +1.25 | 2.38 |
| **NEW** (>= 12,000,000) | 19,400 @ **4.69** / −0.81 | **1,200 @ 2.75** / +1.91 | 1.44 |

Both halves improve by roughly the same large margin (−3.24 and −1.94), so the rule is not fitted
to the half it was designed on. **What must be said plainly: the surviving core sits AT the bar,
not comfortably under it.** OLD reads 3.31 — over — on 441 rows; NEW reads 2.75 on 1,200. Pooled
it is 2.61 because opposite-signed bins cancel. A population shift toward the OLD half's mix
would put this cell back on the board, and the honest claim is *"this rule moves the cell from
5.29 to about 2.6–3.3, which is at or just under the bar"* — not *"this cell is fixed forever"*.

---

## 7. The instrument, and the three things that made it possible

`backend/scripts/calibration_cell_exact.py` — new file, no production code.

1. **`market_info_extra` is a documented parameter of the producer's chain** (the horizon surface
   at `precompute_calibration.py:5583` already uses it this way). Every downstream CTE joins
   `market_info`, so scoping it scopes the whole chain to one cell.
2. **`POST /api/admin/db-query` refuses the chain verbatim** — `"Multi-statement queries not
   allowed"`. The producer's SQL carries prose comments and some contain a semicolon. Comments
   are stripped quote-safely; a naive `split('--')` would corrupt literals that legitimately
   contain `--`, which is guarded RED-first.
3. **The whole-cell chain exceeds the row path's hard 10 s budget**, so it is chunked on `fm.id`
   through the same hook, and a chunk that still times out is SPLIT rather than retried.

**The one approximation, measured rather than described.** Chunking on `fm.id` can split a
`group_id`/`event_id` cluster, so `virtual_market`'s ">= 3 markets in the same source" test could
see a partial cluster. `--edge-check` re-runs the whole sweep at half the chunk width:
**n=28,738 / ECE 5.29 / gap −0.47 at both widths — IDENTICAL.** Chunk boundaries do not move this
cell. The residual +0.55% on n is therefore the *category* scoping (siblings in another category
are invisible to the slice), the same class the replica documents, and it does not move ECE or
gap at two decimals on any of the four cells measured.

**One measured performance defect, worth carrying forward.** The shape join aggregates
`futures_outcomes`; without `market_id IN (SELECT market_id FROM market_info)` the planner has no
predicate and prices a full 3.3M-row scan — the first `--by shape` run never returned a single
chunk and recursively split to the depth limit. It is CAL-P039's `vm_stats` defect arriving
through a different door: a planner hint spelled as a predicate, redundant with the join and
load-bearing. Guarded structurally.

---

## 8. What this rule is worth, and what it is not

* **Published delta, predicted in advance so it can be checked rather than narrated:**
  `kalshi/economics` **5.29 → 2.61 pp**, **65,524 → 0 excess-outcomes**, cell leaves the queue,
  1,641 rows still published. Realistic band **2.6 – 3.3 pp** (§6).
* **It removes 27,097 of 28,738 rows — 94.3% of the cell, and ~3.0% of the entire published
  curve.** A change that large to what publishes is **Alex's call**, on the same footing as
  ruling 103's 9.3%. This document is PLAN ONLY.
* **The headline `mce_closing_line` delta is NOT predicted here.** The payload's headline is not
  reproducible as a pooled fold of its own buckets (pooled-by-`bucket_idx` gives 1.3517 against a
  published 1.89), so any headline number this document quoted would be arithmetic wearing a
  measurement's clothes. Parked with the instrument to compute it.
* **It is not a new mechanism.** It is the CAL-P112 defect, third instance, largest, plus one
  forced correction to that queue's scoping (§5).

## 9. Order of landing, once ruling 009's condition is met

1. **E, E2, E3 and the `(source, category)` keying ship together.** T alone is a regression on
   this cell (5.73) and on `polymarket/tech` (CAL-P112 §6). E alone on esports reverses its sign.
2. Admit exactly `('kalshi','economics')`, `('kalshi','tech')`, `('polymarket','esports')` —
   each benched on this rail, each with its own before/after in its own design document.
   `('polymarket','economics')` and `('polymarket','tech')` are **refused by measurement**, and
   the refusals are the evidence that the gate works.
3. Re-measure the published curve and record the delta against the 2.61 prediction. **A cell is
   crossed off only when the published number moved.**
