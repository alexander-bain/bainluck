# CAL-P1077 — rank 10, `polymarket/hockey`: the named mechanism is not in the published cell

**Pillar: TRUTH. Ship: the calibration queue stops carrying a hockey fix that
cannot move the hockey number, so the next session spends its hour on the 1,548
rows that are actually wrong.**

Status: **mechanism REFUTED on the producer's own chain — zero rows**, and
re-confirmed on the whole-virtual-market rail after CERT-2428 (see the repair
section below: two folds, 27 minutes apart, byte-identical roster, certain arm
absent in both). No rule designed, none needed.
This subject writes no production code: `git diff origin/master -- backend/app
frontend` is empty on this branch, whose commits touch only `backend/scripts`,
`backend/tests` and `artifacts/`. CAL-P1078's frontend commit was SPLIT OFF onto
its own branch off clean master under CERT-2436's required repair
`1078-SPLIT-BLOCKED-P1077-FROM-READER-SHIP`, so the reader ship is not gated on
this measurement.

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

## 🔴 CERT-2428 REPAIR — re-folded on the whole-virtual-market rail. THE REFUTATION HOLDS.

Both runs above came from `calibration_cell_exact`'s `sweep()`, which partitions on
raw `futures_markets.id` ranges and re-derives `group_sizes` / `event_sizes` inside
every slice — the rail that reproduced only 8,426 of `polymarket/basketball`'s
13,135 published rows (**−35.85%**). An ABSENCE is the most dangerous thing that
rail can report, because a re-derivation that moves rows out of a class prints the
same empty arm a genuinely empty class does. CERT-2428 blocked it on exactly that,
and the block was right to be made whether or not it changed the answer.

Re-folded on `backend/scripts/calibration_whole_vm_fold.py` (frozen generation,
replayed through the producer's own `plan_units`, a `vm_id` never split), **twice,
27.0 minutes apart, on a byte-identical roster** (5,498 rows, sha256
`579acc1dae05a8f3` both times, 0 markets entered, 0 left):

| | whole-vm fold 1 | whole-vm fold 2 | id-range (blocked) | payload |
|---|---|---|---|---|
| replica | 1,801 / 7.57 / +2.45 | 1,801 / 7.57 / +2.45 | 1,800 / 7.56 / +2.46 | 1,704 / 6.59 / +0.70 |
| `z_pub_ordinary\|from_calibration` | 1,628 / 8.34 / +2.67 | 1,628 / 8.34 / +2.67 | 1,627 / 8.33 / +2.69 | — |
| `b_pub_near_certain\|from_calibration` | 164 / **0.34** / +0.34 | 164 / **0.34** / +0.34 | 164 / 0.34 / +0.34 | — |
| `b_pub_near_certain\|from_opening` | 9 / **0.01** / +0.01 | 9 / **0.01** / +0.01 | 9 / 0.01 / +0.01 | — |
| **`a_pub_certain`** | **ABSENT** | **ABSENT** | ABSENT | — |

**The certain arm is empty on the correct rail too, in both folds. Rank 10 comes off
the queue.** The shoulder control is identical to the row on all four readings, so
the "a high-band exclusion would have deleted the cell's best-calibrated rows"
argument is unchanged.

And the exposure here was not small — it was the largest on the board. Reading the
frozen roster offline against `sweep()`'s own slices (width 1,000,000, origin
`MIN(id)` per SOURCE = 112,847 for polymarket), **465 of hockey's 498 grouped virtual
questions (93.4%), carrying 3,614 of its 5,498 markets (65.7%), straddle a slice
boundary** and would have been re-derived under a different identity by the blocked
rail. The two rails then returned the same fold to within ONE row, while economics —
exposed at 9.5% — moved by 38. That is worth writing down in both directions: the
id-range rail's damage is not predictable from how exposed a cell is, so it can
neither be assumed nor argued away, only measured. Banked as
`id-range-rail-exposure.json`.

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
