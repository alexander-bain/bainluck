# RULE DESIGN — `kalshi/tech` (−9.49 pp, 9,663 excess-outcomes, rank 16, worst ECE on the board)

**Status: designed, benched, holdout-validated. NOT built, NOT merged, worth 0.00 pp today.**
Banked by CAL-P112, 2026-08-28, against the payload generated `2026-08-28T17:33:03Z`
(population `q268`).

---

## 1. The cell, as published

| | |
|---|---|
| cell | `kalshi/tech` |
| ECE | **11.10 pp** — the highest on the material board · gap **−9.49 pp** (under-predicts) · n **1,193** · σ 5.6 |
| excess over the 3.0 bar | **+8.10 pp**, 9,663 excess-outcomes |
| mechanism status before today | ❌ **none** |

The payload's own bins locate it: bin 5 (prices 0.50–0.60) carries **179 rows at an average
published price of 0.528 that win 90.5% of the time** — a −37.67 pp bin contributing 5.65 pp of the
cell's 11.10 on its own.

**Note for whoever reads the ±sign:** `polymarket/esports` over-predicts by +6.50 and this cell
under-predicts by −9.49. They are the same structural defect pointing in opposite directions, and
in the pooled headline they cancel. That is `CALIBRATION-SCORECARD.md` §2's argument, measured, in
one pair.

## 2. The mechanism: cumulative-threshold ladders published as if they were forecasts

`backend/scripts/calibration_cell_replica.py --source kalshi --category tech`, full published
predicate through `deduped`:

| shape class | n | ECE pp | gap pp | markets |
|---|--:|--:|--:|--:|
| **`bundle_multiwin`** (≥3 outcomes, ≥2 winners) | **958** | **12.68** | **−11.32** | 59 |
| `field_1win` | 199 | 4.41 | +3.77 | 64 |
| `single` (1 captured outcome) | 50 | 24.21 | −24.21 | 50 |
| `void_0win` (n=1, graded nobody) | 11 | 34.73 | +34.73 | 11 |

**79% of the published cell by row count is one shape**, and here is what those markets are:

| market | outcomes | winners | Σ published price |
|---|--:|--:|--:|
| Price of NVIDIA B200 compute by Apr 30, 2026? | 40 | **40** | 20.41 |
| Price of NVIDIA B200 compute on Mar 31, 2026? | 39 | **39** | 25.78 |
| Price of NVIDIA H200 compute on Mar 31, 2026? | 36 | **36** | 22.90 |
| Price of NVIDIA H200 compute by May 31, 2026? | 40 | **40** | 32.70 |
| Price of NVIDIA H100 compute by Apr 30, 2026? | 38 | **38** | 32.12 |
| What will Tim Cook say during Apple's WWDC26 Keynote? | 21 | 2 | 5.53 |

A 40-rung *cumulative* price ladder in which every rung resolves YES is not a question with one
answer; it is forty independent binaries mashed into one market (gotcha #17). Each rung is
published at its own one-sided price and the rungs sum to 20–33, while 40 of them win. Winners
exceed published mass, so the cell under-predicts — the mirror image of the esports case, where the
same shape realizes one winner against a sum of ~3 and over-predicts.

**This is not a new class.** It is exactly `nonexclusive_bundle_markets` — the category-independent
CTE `precompute_calibration.py` already computes and already publishes a census for. It excludes
the class from the curve **for `esports` only**, and the reason it stops there is on record and
still correct: a blanket exclusion "would delete 81% of hockey (ECE 0.87 pp) and 47% of tennis
(2.42 pp) — well-calibrated cohorts with no evidence of the esports defect."

**The census's own numbers say tech has that evidence.** From the served payload,
`nonexclusive_bundle_census.by_category`:

| category | published n | would-exclude n | would-exclude ECE | remainder n | remainder ECE |
|---|--:|--:|--:|--:|--:|
| **tech** | 3,850 | 2,589 | **8.27** | 1,261 | **6.08** |

The bundle cohort is materially worse than the remainder. That is the exact test the esports
exclusion was granted on, and tech passes it.

## 3. THE RULE

### RULE T — the bundle exclusion's category scope becomes an evidence-gated allowlist

> Replace `ESPORTS_MULTI_BUNDLE_CATEGORY = "esports"` with
> `NONPARTITION_BUNDLE_CATEGORIES = frozenset({"esports", "tech"})`, and gate membership on the
> census the payload already publishes: a category joins the allowlist when its bundle cohort's
> ECE materially exceeds its remainder's on a cohort that clears the sample bar.

Smallest durable change: one constant and one `=` → `IN` in the `esports_multi_bundles` CTE. The
counter, the rule text and the payload key already exist. Read-side only, no regrade (gotcha #21) —
the many-YES ladder grading is *correct*, which is why the class is excluded rather than fixed.

The allowlist, not a blanket rule, is the whole design. Hockey, tennis and table_tennis are the
counter-class the census was built to protect and they stay untouched.

## 4. MEASURED EFFECT — replica, and its self-check

| | n | ECE pp | gap pp |
|---|--:|--:|--:|
| replica of the published cell | **1,218** | **10.75** | **−8.97** |
| **payload's own `kalshi/tech`** | **1,193** | **11.10** | **−9.49** |
| after RULE T | **260** | **3.80** | **−0.30** |

The replica is 2.1% high on n and 0.35 pp low on ECE. It applies the published predicate from
`market_info` through `deduped`; the residual is the two approximations named in the script's
docstring (slice-local `vm_id` cardinality, and source-inapplicable filters omitted). Printed here
rather than asserted, because a rule benched on a population that does not reproduce is the CAL-P108
finding wearing an instrument's coat.

**A 9.49 pp cell becomes a 0.30 pp one.** Excess-outcomes **9,663 → 0**.

## 5. HOLDOUT — split on `market_id`, rule never re-fitted

| split | before | dropped cohort | after | after σ vs 3.0 |
|---|---|---|---|---|
| ALL | 1,218 / 10.75 / −8.97 | 958 / 12.68 / −11.32 | **260 / 3.80 / −0.30** | +0.26σ |
| **OLD** (`mid < 15,206,392`) | 746 / 11.81 / −9.87 | 596 / **13.55** / −12.13 | 150 / 5.24 / **−0.91** | +0.55σ |
| **NEW** (`mid ≥ 15,206,392`) | 472 / 11.14 / −7.53 | 362 / **13.57** / −9.98 | 110 / 7.80 / **+0.54** | +1.01σ |

**The dropped cohort reads 13.55 pp on the older half and 13.57 pp on the newer one** — the defect
is the same size out of sample, to two decimal places. The surviving cohort's **gap** goes to
−0.91 / +0.54: near zero in both halves, from opposite directions.

**The honest caveat, and it matters.** The surviving cohort's *ECE* reads 5.24 and 7.80 on the two
halves against 3.80 pooled. That is not the rule failing out of sample; it is what a 10-bin ECE does
at n≈130 (each bin holds ~13 rows, so every bin's empirical win rate is several pp off its own mean
by construction). **Gap is the statistic that survives the split here, and gap is what the rule
targets.** Anyone quoting the 3.80 should quote its σ of 3.10 with it.

## 6. WHAT THIS RULE COSTS — and the interaction that must not be missed

RULE T is a *category* allowlist, so it acts on **`polymarket/tech`** as well (rank 17,
ECE 5.40, n 2,657, 6,377 excess-outcomes). The shape census for that cell:

| shape class | n | ECE pp | gap pp |
|---|--:|--:|--:|
| `bundle_multiwin` | 929 | 5.95 | −2.00 |
| `field_1win` | 902 | **14.73** | **+14.05** |
| `binary_1win` | 236 | 6.84 | +0.74 |

> 🔴 **RULE T MUST NOT SHIP WITHOUT `RULE-DESIGN-polymarket-esports.md`'s RULE E.**
> In `polymarket/tech` the bundle class is the *better* half. Stripping only the ≥2-winner
> realizations leaves the 1-winner tail at 14.73 pp — the census-level fold moves 8.04 → **12.62**,
> i.e. **worse**. With RULE E's structural clause applied too, the same fold lands at
> 249 rows / 7.49 pp, below the 1,000-row materiality floor. In `kalshi/tech` the interaction is
> negligible (RULE E's clause moves 18 further rows), so the two cells argue for the two halves of
> one package and neither half is safe alone.

> ⚠️ **`polymarket/tech` is UNMEASURED, not estimated.** The replica does not reproduce that cell:
> **2,080 / 8.04 / +5.10** against the payload's **2,657 / 5.40 / −1.78** — 22% short on n and the
> **wrong sign** on the gap. The census above is a shape decomposition, not a published-cell
> prediction, and no number for `polymarket/tech` should be quoted from it. **Landing RULE T owes
> one measurement first**: a `polymarket/tech` fold that reproduces the payload. Parked to
> `PARKED-MEASUREMENTS.md`.

**After RULE T, `kalshi/tech` has 260 published rows** and leaves the queue on the materiality
floor (`min_category_outcomes: 1000`) as much as on its ECE. That is the correct outcome — those
rows were never scoreable forecasts of one question — but it should be said plainly rather than
reported as a cell that got good.

## 7. Two smaller classes this cell also carries, named and NOT ruled

- **`single`, 50 rows, ECE 24.21, win rate 1.000.** The same winner-only single capture that
  `polymarket/esports` carries at 453/453. Here the neighbouring `void_0win` class (n=1 markets that
  graded nobody) adds 11 rows in the other direction, so the combined single-capture class is 50/61
  winners at an average price of ~0.68 — over-represented by winners but not degenerate. Not the
  same open-and-shut case as esports; **it needs its own read before a rule.**
- **`void_0win` with `n_outcomes = 1`, 11 rows.** `no_winner_markets` requires `n_outcomes >= 2`,
  so a single-outcome market that graded nobody survives it. 11 rows at 34.73 pp — real, tiny,
  and a one-clause change if the single-capture class is ruled on.

Both parked, not dropped.

## 8. Land-day checklist

1. `ESPORTS_MULTI_BUNDLE_CATEGORY` → `NONPARTITION_BUNDLE_CATEGORIES = {"esports", "tech"}`;
   `mrs.category = '…'` → `mrs.category IN (…)`; rename the payload key or keep it and add the
   allowlist to its rule text (the key is a published contract — decide, do not drift).
2. Ship together with RULE E (§6).
3. Guard tests RED-first: a tech 40-rung / 40-winner market excluded, a hockey 20-outcome /
   6-winner market **untouched** (the counter-class assertion is the one that matters).
4. Re-run the `polymarket/tech` measurement owed in §6 **before** merge.
5. Deploy, then `calibration_scorecard.py --live --record`, and record the measured
   `kalshi/tech` delta against the 11.10 → ~3.8 prediction on this page.

**Ruling 009 blocks step 1**: it edits `precompute_calibration.py`. It lands when the amended
22-of-24 condition is met against the `2026-08-28T18:55:19Z` baseline and the lift is recorded.
