# RULE DESIGN — `polymarket/esports` (+6.50 pp, 66,832 excess-outcomes, rank 2)

**Status: designed, benched, holdout-validated. NOT built, NOT merged, worth 0.00 pp today.**
This document exists so that freeze-lift day is a merge, not a diagnosis. Per
`CALIBRATION-SCORECARD.md` §4, a rule that is not deployed and re-measured counts as **ZERO**.

Banked by CAL-P112, 2026-08-28, against the payload generated `2026-08-28T17:33:03Z`
(population `q268`).

---

## 1. The cell, as published

| | |
|---|---|
| cell | `polymarket/esports` |
| ECE | **8.08 pp** · gap **+6.50 pp** (over-predicts) · n **13,156** · σ 11.7 |
| excess over the 3.0 bar | **+5.08 pp**, **66,832 excess-outcomes** — rank 2 of 19 |
| mechanism status before today | ⚠️ *partial* — `esports_multi_bundle_filter` has been live since **2026-07-11** and the cell is still 8.08 |

A `price_moved` split of the payload's own buckets says the defect is not diffuse:
`price_moved=false` folds to ECE 7.34 / gap +5.06 on 11,822 rows, `price_moved=true` to
**ECE 19.31 / gap +19.31** on 1,334 — a stratum where *every* bin over-predicts, which is the
signature of probability mass with no winner behind it, not of noise.

## 2. Why the shipped filter did not clear it — the test is a REALIZATION, the defect is a STRUCTURE

`esports_multi_bundles` (Queue #159, `precompute_calibration.py`) excludes an esports market when
it has **≥3 outcomes and resolved with ≥2 winners**. Polymarket packs a whole match — cumulative
Total-Kills Over ladders, per-game winners, first-blood props — into one non-partition market, and
because the Over rungs are cumulative many resolve YES at once (gotcha #17). The filter has
removed **143,823 outcomes** and it is right to.

But `win_count ≥ 2` is a property of the *realization*, not of the *market*. The same structure
that usually resolves 6 YES sometimes resolves exactly 1 — a low-kill map, a short series — and
that realization walks straight past the filter. The 0-winner realizations are caught upstream by
`no_winner_markets`. **So what survives is precisely the exactly-1-winner tail of an already-
condemned class**, published at raw one-sided prices whose per-market sum is nowhere near 1.

It is not normalized either: `mex_field_candidates` requires PROVED exclusivity
(`market_type='field' AND shape.exhaustive='true' AND shape.expected_winners='1' AND
shape.outcome_relation ∈ {competitors, exclusive_ranges}`), and a cumulative-threshold ladder is
explicitly refused there (Queue 299 rung 4). Excluded from the exclusion, excluded from the
normalization, published raw.

## 3. Measured — the surviving cell, folded by market shape

`backend/scripts/calibration_cell_shape_fold.py --source polymarket --category esports`.
Shape classes key on `(n_outcomes, win_count)` over ALL of a market's outcomes — the same basis
`market_result_shape` uses.

| shape class | n | ECE pp | gap pp | what it is |
|---|--:|--:|--:|---|
| `bundle_multiwin` | 95,549 | 9.97 | +8.86 | **already excluded** by the shipped filter |
| `void_0win` | 5,704 | 45.71 | +45.71 | **already excluded** by `no_winner_markets` |
| **`field_1win`** | **4,030** | **27.07** | **+27.04** | ⬅ **the survivor tail — the defect** |
| `binary_1win` | 9,522 | 3.02 | −0.85 | the genuine scoreable core |
| `single` | 453 | 40.55 | −40.55 | 1 captured outcome, **453 of 453 are winners** |
| `binary_other` | 116 | 33.54 | −33.54 | 2 outcomes, both graded winners |

**Census self-check.** Pooling the four unexcluded classes gives **n=14,121, ECE 6.81,
gap +5.57** against the payload's **13,156 / 8.08 / +6.50**. 7.3% high on n, 1.27 pp low on ECE —
the residual is the dedup/liquidity/placeholder filters this census does not apply (it stops at
`ranked_outcomes`; see the script's docstring). Same sign, same order of magnitude, so the
decomposition is usable; the *absolute* post-rule ECE is not, and §6 gives a band rather than a
point.

**`field_1win` is a ladder, not a partition.** Per-market published price sum: median **2.26**,
p90 **5.54**, max **11.40**; 92.3% exceed 1.15. The `binary_1win` core, by contrast, has a median
sum of **1.000** and only 1.2% above 1.15. The price sum separates the two cleanly, and it does so
without asking how many winners the market happened to have.

## 4. THE RULE

Three disjoint exclusions. §6 shows why they ship as one package.

### RULE E — the bundle test becomes STRUCTURAL

> Within the categories on the bundle-exclusion allowlist, exclude a market with **≥3 captured
> outcomes** that is **not a proved-exclusive field**, when **either** it resolved with ≥2 winners
> (the shipped test, unchanged) **or** its published price sum exceeds `MEX_SUM_THRESHOLD` (1.15).

The added clause is one `OR` on the existing `esports_multi_bundles` CTE, reusing the
`mex_field_divisor` sum the population already computes. It is realization-independent: a
partition sums to ~1 whatever it resolves to, a bundle of independent binaries sums to N × p.
Read-side only, no regrade (gotcha #21) — the many-YES ladder grading is correct.

**Disjointness, stated because CERT-403B's blocked defect was exactly a filter broader than the
rule it claimed to be:** the `NOT proved-exclusive` clause is load-bearing. Complete
proved-exclusive fields are the `mex_field_candidates` population and are *normalized*, never
excluded; the two sets cannot overlap. The `≥3 outcomes` clause keeps it off every two-outcome
market whatever its sum.

### RULE E2 — the winner-only single capture

> Exclude a market whose entire captured population is **one outcome**, in a category where that
> class's measured win rate is degenerate.

453 markets, 453 outcomes, **453 winners — a win rate of 1.000 at an average published price of
0.59**. `orphan_partition_markets` deliberately does not catch this ("a standalone Yes/No claim
with one outcome is a complete, scoreable prediction"), and that reasoning is right in general and
false here: a population that is 100% winners is not a set of Yes/No claims being scored, it is
one-sided capture. Evidence-gated per cohort for exactly that reason — see §7 for the same class
in `kalshi/tech`, where it is 50/61 and needs its own read.

### RULE E3 — the malformed binary that escapes on a default-true column

> Drop the `mutually_exclusive = true` requirement from `malformed_binaries`.

58 markets / 116 outcomes are 2-outcome markets where **both** outcomes are graded winners —
structurally impossible for a partition — and they survive only because the market's
`mutually_exclusive` column is not set. Queue 299 already ruled that column *is not evidence*
(it defaults True and is set for Yes/No claims and duels alike) and removed it from the
normalization gate. Here it is doing the same damage in the other direction: requiring it to be
TRUE lets non-flagged malformed binaries through. Smallest possible change; the `n_outcomes = 2
AND win_count ≠ 1` test carries the whole rule already.

## 5. HOLDOUT — split on `market_id` (monotone with creation), rule never re-fitted

```
python3 backend/scripts/calibration_cell_shape_fold.py --source polymarket --category esports \
    --chunks 40 --holdout-at 34674514
```

The cut id becomes a chunk EDGE, so neither half is contaminated by the other's rows.

| split | class | n | ECE pp | gap pp |
|---|---|--:|--:|--:|
| **OLD** (`mid < 34,674,514`) | **`field_1win`** | 2,818 | **27.95** | **+27.87** |
| | `binary_1win` | 5,030 | **2.97** | −0.90 |
| | `single` | 37 | 43.54 | −43.54 |
| | *census before rule* | 7,885 | 10.44 | **+9.19** |
| **NEW** (`mid ≥ 34,674,514`) | **`field_1win`** | 1,212 | **25.10** | **+25.10** |
| | `binary_1win` | 4,492 | **3.23** | −0.80 |
| | `single` | 416 | 40.29 | −40.29 |
| | `binary_other` | 116 | 33.54 | −33.54 |
| | *census before rule* | 6,236 | 3.17 | **+0.99** |

**The target class carries +27.87 pp on the half the rule was designed on and +25.10 pp on the half
it was not.** The surviving core reads **2.97 / 3.23 pp ECE and −0.90 / −0.80 pp gap** — the same
answer twice, out of sample, straddling the 3.0 bar from both sides. That is the evidence the rule
removes a mechanism rather than fitting a sample.

*(The `before` numbers differ sharply across halves — 10.44 vs 3.17 — because the classes have
different vintages: `single` is almost all NEW, `field_1win` mostly OLD, and they point in opposite
directions. That is the §2 cancellation reproducing itself inside one cell, and it is the reason §6
exists.)*

## 6. PREDICTED PUBLISHED DELTA — and why partial shipping is the trap

Folded on the payload's own 10-bin structure, over the census population:

| population | n | ECE pp | gap pp |
|---|--:|--:|--:|
| today (census) | 14,121 | 6.81 | +5.57 |
| after **E** only | 10,091 | 3.98 | **−3.01** |
| after **E + E2** | 9,638 | 3.13 | −1.25 |
| after **E + E2 + E3** | **9,522** | **3.02** | **−0.85** |

> **Predicted published `polymarket/esports` after the full package: 3.0–4.3 pp.**
> The low end is the census's own post-rule fold (3.02). The high end applies the measured
> −3.79 pp *delta* to the published 8.08. The truth is between, because the census and the
> published set differ by ~965 rows. Excess-outcomes **66,832 → 0–11,400**, an 83–100% reduction
> and by a wide margin the largest published improvement this program would have made.

**The trap, named:** shipping **E alone** takes the gap from +5.57 to **−3.01** — it does not
halve the error, it *reverses its sign*, because E2 and E3 were partially cancelling E's class all
along. A queue that ships the biggest defect first and re-measures would read a 2.83 pp ECE
improvement and a cell that now under-predicts, and would have to diagnose the "new" defect it
created. **E, E2 and E3 ship together or the cell is worked twice.**

**It still does not clear the bar.** 3.02 pp on 9,522 rows is σ = 0.51, so the excess over 3.0 is
0.04σ — the cell leaves the queue by the significance gate, not by being demonstrably under the
bar. Stated in advance, per §7's precedent: expecting one rule to close one cell is what §8's
1.5-rules-per-cell assumption already prices in.

## 7. What this rule does NOT do

- **It does not touch `bundle_multiwin` outside the allowlist.** The category allowlist is
  unchanged by RULE E itself; extending it is `RULE-DESIGN-kalshi-tech.md`'s RULE T, and the two
  interact — read that document's §6 before landing either.
- **It does not re-grade anything.** Read-side only, forward-only, gotcha #21.
- **It leaves `single`/`binary_other` in every other cohort alone.** Both are evidence-gated on
  this cell's measured win rates; the same shapes elsewhere need their own census first.

## 8. Land-day checklist

1. `esports_multi_bundles` CTE: add the `OR cp_sum > MEX_SUM_THRESHOLD AND NOT proved-exclusive`
   clause; keep the counter in `esports_multi_bundle_filter.excluded` and add a second counter for
   the new clause so the two are separable in the payload.
2. `malformed_binaries` CTE: delete `AND mi.mutually_exclusive = true`.
3. New `single_capture_markets` CTE + per-outcome flag, category-allowlisted, with its own payload
   counter and rule text.
4. Guard tests RED-first: a 7-outcome / 1-winner / sum-2.85 market must be excluded and a
   7-outcome / 1-winner / sum-1.01 market must survive.
5. Deploy, then `python3 backend/scripts/calibration_scorecard.py --live --record` and record the
   measured delta against the 3.0–4.3 pp prediction **on this page**.

**Ruling 009 blocks steps 1–3**: all three edit `precompute_calibration.py`. They land when the
amended 22-of-24 condition is met against the `2026-08-28T18:55:19Z` baseline and the lift is
recorded.
