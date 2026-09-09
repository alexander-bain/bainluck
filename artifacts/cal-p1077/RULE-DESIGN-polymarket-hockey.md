# CAL-P1077 — rank 10, `polymarket/hockey`: the named mechanism is not in the published cell

**Pillar: TRUTH. Ship: the calibration queue stops carrying a hockey fix that
cannot move the hockey number, so the next session spends its hour on the 1,548
rows that are actually wrong.**

Status: **mechanism REFUTED on the producer's own chain — zero rows.** No rule
designed, none needed. `git diff origin/master -- backend/app frontend` is empty on
this branch.

| | |
|---|---|
| board rank | 10 of 11 queued (live scorecard, 2026-09-09) |
| published cell | `polymarket/hockey` — ECE **6.59** pp, n **1,704**, gap **+0.70** |
| excess | **6,117** excess-outcomes |
| handed over by | `ARTIFACT-M-20260909-SUBCOHORT-polymarket-hockey-field.md` |

---

## The claim, and the fold that answers it

The handoff named it precisely, with a verbatim market: *"unresolved-candidate legs
('Player N'/'Other') priced exactly 1.0000 in award/draft markets"* — 21 unnamed legs
of "NHL Hart Memorial Trophy Winner", all 21 losing; the same shape on six trophies
and the 2026 draft. Predicted `field 21.43 → 9.35`.

`--by pubband` bands the price the reader is actually scored on,
`COALESCE(calibration_probability, opening_probability)`:

Folded twice, ~40 minutes apart, because the population was being written tonight
(see §0 of `RULE-DESIGN-polymarket-economics.md`):

| | run 1 | run 2 | payload |
|---|---|---|---|
| replica | 1,717 / 6.80 / +0.26 | 1,800 / 7.56 / +2.46 | 1,704 / 6.59 / +0.70 |
| vs payload | +0.76% rows | **+5.63% rows** | — |
| `z_pub_ordinary\|from_calibration` | 1,548 / 7.50 / +0.26 | 1,627 / 8.33 / +2.69 | — |
| `b_pub_near_certain\|from_calibration` | 160 / **0.34** / +0.34 | 164 / **0.34** / +0.34 | — |
| `b_pub_near_certain\|from_opening` | 9 / **0.01** / +0.01 | 9 / **0.01** / +0.01 | — |
| **`a_pub_certain`** | **0** | **0** | — |

The cell's totals moved and are not quotable. **The two readings this refutation
rests on did not:** the certain arm is empty in both runs, and the near-certain
shoulder folds at 0.34 and 0.01 in both.

**There are no legs at a certain price in the published cell.** The producer's
admission gate demands `opening_probability > 0 AND < 1`, and it removes them before
the curve ever sees them. The 1.0000 legs are real — the handoff read them out of the
database and they are there — but they are in the truth-eligible superset, not in the
9,779-row population the page publishes.

And the shoulder is the control that makes the refutation stick: the 169 legs that
*are* near-certain (≥0.99 / ≤0.01) fold at **ECE 0.34 and 0.01**. Near-certainty in
this cell is not merely present, it is the best-calibrated thing in it. A rule
excluding the high band would have deleted the cell's most accurate rows.

## Where the cell's error actually is

`z_pub_ordinary` — ~90% of the cell, in the ordinary price range, at 7.50 and 8.33 pp
across the two runs. Both readings are of a moving population so neither is the
number, but the shape is stable: **the error is in the ordinary price range, not at
the extremes.** Unqueued and undiagnosed; the honest next move is a shape or age
fold on a quiet population, not another exclusion hunt.

## 🔴 The trap this fold was one line away from falling into

The admission gate reads `opening_probability`; the published price is
`COALESCE(calibration_probability, opening_probability)`. Banding the first column
would have reported `a_pub_certain = 0` **as well** — the same empty arm, the same
sentence in this document — while measuring the gate instead of the cell. The
distinction is invisible in the output and decides whether "absent" means "already
excluded" or "my join was wrong".

`test_pubband_bands_the_published_price_not_the_admission_price` exists for exactly
that, and the mutation that swaps the COALESCE for the bare column reds it.
