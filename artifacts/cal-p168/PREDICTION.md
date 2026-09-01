# PREDICTION — rank 1 `polymarket/baseball`, K′ = R1 + R2 + R3 + M1

**CAL-P168, 2026-08-31.** Written **before** the code, as CAL-P162 did, and as
`PORT-SCOPE-rank1-polymarket-baseball.md` §6 and directive `933` both require. Everything below is
a claim that the next published curve can refute.

## 0. Provenance of these numbers — they are NOT mine

Every figure here is quoted from `artifacts/cal-p117/RULE-DESIGN-polymarket-baseball.md`, measured
by CAL-P117 on 2026-08-28 against the `2026-08-28T20:37:41Z` payload using the exact rail
(`calibration_cell_exact.py`, folding the producer's own `_calibration_population_ctes()`).
**This session re-measured nothing.** That is the honest frame for the whole document: I am
transplanting a ruled design and predicting that the design's own measurement reproduces. If it
does not, the first suspect is the four-session gap between the fold and the deploy, not the code.

⚠️ **The rail runs 5.7% low on absolute row counts for this cell** (design §1 — `market_info_extra`
scopes to one `(source, category)` and Polymarket's `virtual_market` grouping crosses
`llm_sport_category`, so a market that groups in production can read ungrouped on the rail). ECEs
agree with the payload to 0.11 pp; **row counts are quoted as the rail measured them and are
expected to land ~5–6% HIGHER in the payload.** A row count 5% off is a confirmation, not a miss.

## 1. THE HEADLINE PREDICTION

| quantity | before | **predicted after** |
|---|--:|--:|
| `polymarket/baseball` ECE | 4.71 pp | **2.71 pp** |
| cell n (rail) | 41,127 | **17,827** |
| cell n (scaled to payload) | ≈43,768 | **≈18,900** |
| gap | +3.29 | **−1.21** |
| excess-outcomes `n × (ECE − 3.0)` | **78,782** | **0** |
| holdout OLD | 6.83 | **2.90** |
| holdout NEW | 4.96 | **2.63** |

**Rank 1 crosses off the burn-down board.** It is the largest single item remaining on it.

🔴 **The margin is thin and stated up front: 2.71 against a 3.0 bar is 0.77σ under it**
(σ = 50/√17,827 = 0.37). This is a pass, not a comfortable one. **A reading of 2.9–3.1 does not
refute the design** — it is inside one sigma. What would refute it is ≥3.4, or either holdout half
over the bar.

## 2. WHAT I PREDICT FOR THE HEADLINE CURVE

`mce_closing_line` is **1.86 pp** today and has been for five sessions.

K′ removes ≈24,800 outcomes ≈ **2.7% of the published curve** (913,849 outcomes). Those rows carry
a much-worse-than-average error, so the headline should **fall**. I decline to predict a precise
value — the headline is a pooled reweighting across ~48 cells and CAL-P162's still-ungraded
prediction (1.78, band 1.70–1.86) is already in flight on the same publish. **Predicted direction:
DOWN. Predicted band with RULE E also landing: 1.62–1.80.**

⚠️ **Do not read a headline drop as this rule working.** Two ships publish together. The cell-level
number in §1 is the falsifiable one; the headline is a joint outcome of both and cannot attribute.

## 3. WHAT THE USER SEES — the ship, not the measurement

On https://bainluck.com/calibration, in the exclusions list:

> **Part of this is temporary by design.** polymarket/baseball — returns when *&lt;condition&gt;*.
> Those rows are real questions whose published price was written wrong, not rows that were never
> forecasts…

**That sentence has never rendered.** `temporary_by_cell` has shipped as `{}` since CAL-P162 and
the page is gated on it being non-empty. This is the first payload that fills it. A reader learns
that ~24,800 forecasts were set aside **because we wrote the price wrong, not because the market
did**, and learns the condition under which they come back.

## 4. PER-ARM PREDICTIONS (design §4 / §7 — each independently checkable)

| policy | predicted n | predicted ECE | note |
|---|--:|--:|---|
| control | 41,127 | 4.71 | |
| R1 alone | 40,317 | 4.28 | |
| R2 alone | 40,919 | 4.58 | **−0.11 pp solo, and load-bearing** |
| R3 alone | 19,245 | 4.00 | |
| R1+R2 | 39,878 | 4.19 | fails |
| R1+R2+R3 | 17,961 | 2.79 | passes |
| **K′ = R1+R2+R3+M1** | **17,827** | **2.71** | **ships** |

**I predict dropping R2 puts the cell at 3.10 — over the bar.** If a later session finds R2 inert
it has mis-transplanted it, not discovered it is unnecessary.

## 5. FOUR THINGS I PREDICT WILL *NOT* HAPPEN

1. **`polymarket/economics` will not move.** Scope is `(source, category)`, never category alone.
   CAL-P114 measured category-only scoping taking that cell 3.91 → 17.75. If it moves, the
   allowlist leaked.
2. **`kalshi/economics` and `kalshi/crypto` will not move.** K′ is a *separate* predicate on a
   *separate* allowlist. The two filters share a payload key and nothing else. If rank 2's count
   changes, I have wired K′ into RULE E's arm — the exact error design §9.3 forbids.
3. **`is_nonexclusive_bundle` will not be extended to baseball.** Measured 8.35 there, and RULE E
   alone 9.02 — nearly double the control. The bundle shape is not what is wrong with this cell.
4. **No row is re-graded.** Read-side only (gotcha #21). `is_winner` is untouched.

## 6. THE FALSIFIER FOR THE DIAGNOSIS ITSELF (design §9.2 clause 4)

When lane1 queue 022 repairs the writer, **this exclusion must empty itself**. If the writer fix
lands and `excluded_by_cell["polymarket/baseball"]` does *not* fall, then §3's diagnosis was wrong —
the near-0.50 spray was not the writer — and **the exclusion must be re-argued from scratch, never
extended**. R1 and R2 are expected to *stay* (1,258 of their 1,284 rows are historical residue in
the OLD half); only the M1/R3 population returns.

## 7. HOW TO GRADE THIS

```
curl -s https://api.bainluck.com/api/calibration | python3 -c "
import sys,json; d=json.load(sys.stdin)
f=d['nonexclusive_bundle_filter']
print('temporary:', f.get('temporary_by_cell'))
print('by_cell  :', f.get('excluded_by_cell'))
print('headline :', d['mce_closing_line'], d['generated_at'])
print('baseball :', [c for c in d['by_category'] if 'baseball' in str(c)][:2])
"
```
Grade §1 first (the cell), §3 second (the sentence rendered), §2 last and only as direction.

---

## 8. AMENDMENT — CERT-647 (CAL-P170, 2026-09-01 ~04:3xZ / 2026-08-31 ~9:3x pm PT)

🔴 **§6 ABOVE IS NOT REWRITTEN AND MUST NOT BE.** It is the pre-registered bar and it keeps its
registered shape. This section records that §6 contradicts itself, which half was right, and what
the ship was changed to.

**The contradiction, in §6's own two sentences:**

> "When lane1 queue 022 repairs the writer, **this exclusion must empty itself**. […] R1 and R2 are
> expected to *stay* (1,258 of their 1,284 rows are historical residue in the OLD half); only the
> M1/R3 population returns."

Both cannot be true. The second sentence is the correct one — it is the measured one — and the
first is the slogan inherited from design §9.2 clause 4.

**CERT-647 blocked the ship on the slogan having reached the payload.** `temporary_excluded`
published the whole R1+R2+R3+M1 union, and `temporary_by_cell` was emitted unconditionally from a
module constant, so the page rendered "part of this is temporary … this exclusion empties itself"
over a count whose majority never returns. The prediction was right and the payload disagreed with
it; that is the defect, and it is repaired on this branch rather than argued away.

**The falsifier now has a field that can actually falsify it.** §6 keys on
`excluded_by_cell["polymarket/baseball"]`, which is the UNION and therefore falls only partly even
when the diagnosis is completely correct — an untestable bar. Read it on `temporary_excluded`
instead, which counts the M1/R3 cohort alone:

| after the writer repair | correct diagnosis | §3 was wrong |
|---|---|---|
| `temporary_excluded` | → **0** | stays non-zero |
| `temporary_by_cell` | → **`{}`** (sentence leaves the page) | still carries the cell |
| `excluded_by_cell["polymarket/baseball"]` | falls to ≈ the R1/R2 residue, **not to 0** | unchanged |
| `historical_excluded` | ≈ unchanged — this is expected, not a failure | — |

**§7's grading command still works** and now prints the split. Add `temporary_excluded` and
`historical_excluded` to what you read off it; `temporary_by_cell` going `{}` is the sentence
leaving the page, which is clause 3 of the design becoming a true statement rather than an
intention.

**What did NOT change:** no predicate, no allowlist, no row. K′ is the same four arms over the same
cell and the published curve contains exactly the rows it contained before this amendment —
`test_the_temporary_flag_gates_no_curve_row_of_its_own` pins that. §1-§5 are graded unchanged.
