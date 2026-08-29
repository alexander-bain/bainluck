# RULE DESIGN — `kalshi/economics` (CAL-P114, #1978)

**Cell rank 2 of 19 · ECE 5.29 pp on 28,613 published outcomes · gap −0.47 · 65,524
excess-outcomes** (payload `2026-08-28T20:37:41Z`, population `q268`).

Status: **RULED BY ALEX AND LANDABLE — 2026-08-28, option (b), APPROVED WITH DISCLOSURE.** Still
NOT BUILT and still worth 0.00 pp today (the frozen file is untouched — `git diff origin/master --
backend/app/` is empty on this branch), but the decision it was waiting on has been taken. It
ships when ruling 009's amended freeze lifts. **§9 is the ruling and the contract it obliges.**

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

### 5c. `polymarket/esports` — CAL-P112's banked design is CONFIRMED on a rail that reproduces

Worth running because CAL-P112 designed that cell on the same census that misled this one. It
holds. Exact rail **14,169 / 7.17 / +5.79** against the payload's **14,053 / 7.59 / +6.02**
(+0.83% on n).

| policy | n | ECE | gap | excess-outcomes |
|---|--:|--:|--:|--:|
| A_today (control) | 14,169 | 7.17 | +5.79 | 59,085 |
| **E — drop `field1` with published sum > 1.15** | 11,624 | **3.29** | +0.57 | **3,371** |
| E + E2 | 11,405 | 3.70 | +1.36 | 7,984 |

**CAL-P112 predicted "8.08 → 3.0–4.3 pp, 66,832 → 0–11,400 excess-outcomes". Measured on the
published population: 3.29 (E) and 3.70 (E+E2), 3,371 and 7,984. Both inside the predicted
band.** The census got this cell's *number* right even though it got `kalshi/economics`'s sign
wrong — which is the argument for running the exact rail on every cell rather than for
distrusting CAL-P112.

Two things the exact rail adds that the census could not see:

1. **There is no `bundle` class in published esports at all — zero rows.**
   `esports_multi_bundle_filter` has been live since 2026-07-11 and already removes it. The
   entire residual error is the **1-winner tail** the filter cannot reach, which is exactly what
   CAL-P112 said RULE E is for. Confirmed, not assumed.
2. 🔴 **E2 makes this cell WORSE (3.29 → 3.70), and it should still ship.** The
   `single|a_sum_le_1.15` class is 219 rows at gap **−40.35** — under-prediction that was
   *cancelling* the residual +0.57 over-prediction. Removing 219 rows that were never forecasts
   un-cancels an error that was always there. **§2 of the scorecard is the whole argument: an
   ECE that rises because two real errors stopped hiding each other is a more honest number, not
   a regression.** Named here so nobody reads the +0.41 pp as a reason to drop E2.

Holdout is **weak on this cell and says so**: `polymarket/esports` is recent, so OLD holds only
764 of 14,169 rows (5.4%). OLD 764 @ 24.48 → 213 @ 6.87; NEW 13,405 @ 6.34 → 11,192 @ 3.69. The
NEW half carries the result and the OLD half is too small to corroborate it.

*Not a rule, but recorded because it is half the cell:* `binary` markets whose two published
sides sum to 1.15–2 are **50.2%** of published esports (7,116 rows @ 4.01) — the population
CAL-P100's published-pair coherence rule targets. Excluding them takes the cell to 3,873 @
**4.58**, i.e. **worse**. CAL-P100 is not an esports fix.

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

---

## 9. THE RULING — Alex, 2026-08-28: option (b), APPROVED WITH DISCLOSURE

Staged to this lane as `runner-inbox/calibration/017-econ-rule-b.md`, in Alex's decision:

> *The kalshi/economics population fix is APPROVED WITH DISCLOSURE: the correlated intraday
> index-ladder rungs stop entering the published curve (5.29 -> 2.61pp, cell stays material and
> PASSES), AND the removed rows are disclosed on the page as a named, counted exclusion exactly
> like the other 13 filters — "nobody later reads the smaller curve as a fixed one."*

**The exclusion and its disclosure are one deliverable.** A release that lands the filter without
the page copy has not executed this ruling; it has executed half of it, and the half it dropped is
the half that protects the reader.

### 9.1 What lands in the frozen file, when the freeze lifts

`is_nonexclusive_bundle` **already exists in the producer** as a census flag, with
`NONEXCLUSIVE_BUNDLE_CENSUS_RULE_TEXT` and the comment *"this flag does NOT gate `deduped` outside
esports"*. The rule is that flag's promotion, not a new predicate:

| | |
|---|---|
| test | `n_outcomes >= 3 AND win_count >= 2` **OR** published price sum > **1.15**, and never a proved-exclusive field — RULE E, §4 |
| scope | an allowlist keyed on **`(source, category)`**, seeded `{(kalshi, economics)}`. **Never category alone** — CAL-P114 measured that `polymarket/economics` goes 3.91 → **17.75** under category-only scoping |
| shipped with | **E2** (winner-only single capture) and **E3** (`malformed_binaries` stops requiring the default-true `mutually_exclusive` column). E alone lands the cell at 3.00, exactly at the bar; E+E2+E3 lands it at **2.61** |
| never | with **T alone** — T without E takes this cell 5.29 → **5.73**, worse than doing nothing (§4, note 1) |
| payload key | **`nonexclusive_bundle_filter`** — a NEW key, so the live `esports_multi_bundle_filter` contract does not change shape or meaning under existing consumers |

### 9.2 The disclosure contract, and it is BUILT

The payload key must carry `{applies_to, rule, excluded, included?, excluded_by_cell}`, where
`excluded_by_cell` is keyed `"<source>/<category>"`. **The per-cell map is not optional detail:**
the filter is allowlisted per cell, so a single total would hide which cell shrank, and the whole
point of the ruling is that the reader can see that.

The page half **is already on this branch and green** — `frontend/app/calibration/page.tsx`,
in the exclusions list between `esports_multi_bundle_filter` and `exclusion_symmetry`, gated on
`excluded > 0` exactly like the four filters above it, so it renders **nothing** until the backend
key exists. Type: `CalibrationNonexclusiveBundleFilter` in `frontend/lib/api.ts`. Guard:
`frontend/__tests__/lib/calibrationNonexclusiveBundleDisclosure.test.tsx`, 6 tests, mutation-checked
(softening the closing clause reds it; zeroing the count binding reds it).

Three things the copy says, each pinned by a test because each is a clause of the ruling:

1. the rule text and the total, from the payload;
2. **the per-cell counts**, sorted biggest-first;
3. *"This one shrank the curve rather than improving it: the error on these cells fell because rows
   that were never forecasts of a single question stopped being counted, not because our prices got
   better. We publish the count per cell so that is checkable and so the smaller curve is never read
   as a fixed one."*

### 9.3 What the ruling does NOT cover, and must not be read as covering

**`polymarket/baseball` (rank 1) is a separate decision.** Its rule (CAL-P117, K′) removes a
further **~2.7% of the published curve** on the same argument, and the two together come to
**~5.7%**. Alex has ruled the 3.0%; he has not been asked about the 5.7%. It is item 9 in
`YOUR-TURN.md`. The disclosure *mechanism* built here is deliberately general — the payload key is
`nonexclusive_bundle_filter`, not `economics_ladder_filter`, and `excluded_by_cell` takes any
number of cells — so if rank 1 is approved it inherits the surface rather than needing a second
one. **That is the mechanism generalising, not the ruling.**

> ### ↻ ANSWERED 2026-08-28 — rank 1 was ruled, and it inherited the surface with one addition
>
> Alex ruled `polymarket/baseball` the same evening: **EXCLUDE NOW + FIX WRITER**
> (`runner-inbox/calibration/018-baseball-exclusion-ruled.md`, CAL-P119). The pair is now decided
> and the ~5.7% was put in front of him as a pair, which is what this section asked for. Rank 1 did
> inherit `nonexclusive_bundle_filter` rather than needing a second key — the prediction above
> holds.
>
> 🔴 **But the two exclusions are not the same kind, and this document must not be read as though
> they were.** `kalshi/economics` leaves because its **rows** were never competing answers to one
> question: structural, and **permanent**. `polymarket/baseball` leaves because a **writer**
> manufactured its published prices (a leg quoted 0.0355 published at 0.5005) while the market's own
> quote stayed intact: **temporary by design**, and it ends when lane1 queue 022 repairs the writer.
>
> The surface gained one field for exactly that difference — `temporary_by_cell`, keyed
> `"<source>/<category>"` and valued with the condition that ends the exclusion. **It is empty for
> this cell, deliberately.** A payload carrying only `kalshi/economics` renders no claim that
> anything comes back, because the ruling that approved *this* rule said no such thing. Full
> reasoning: `artifacts/cal-p117/RULE-DESIGN-polymarket-baseball.md` §9.1–9.2.
