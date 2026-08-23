# RULING 124 — A threshold that can be tripped by a single observation is not a threshold

date: 2026-08-23
author: Fable (directive pasted and reviewed by Alex)
issues: #2007, #2111, #1544

Gate 5's `published_only_in_scope` gets a **MIN-N FLOOR**: a cell with `n <= 2` is
**reported** in the gate output and can **never alone force `disagrees`**.

## What this is amending, and why it is not a retreat

CAL-P086B found that Gate 0 could say `agrees` over 28.8% of the curve. The fold's
population is futures-only, so **203 of 285 published cells (71.2%)** can never have a
twin row; `reconcile` counted them into `published_only` and the **verdict never read the
count**. Worse, the same hole meant **a fold that produced nothing read as agreement** —
Gate 5 was meetable by a timeout, which is the single failure mode the gate exists to
prevent.

The fix was right: split `published_only` into out-of-scope (a declared, counted limit)
and in-scope (the twin and the producer disagreeing about the population), and let
in-scope force `disagrees`.

**It also changed what kind of rule Gate 0 is.** The verdict now answers to the *key set*
as well as to tolerance — and `published_only_in_scope` is **not tolerance-scaled**. One
thin bucket forces `disagrees` at any bound, including the 100 pp bound the bank's own
128/128 drift currently pins. Since the bound cannot loosen further, there is no setting
of the instrument at which a single two-row bucket stops deciding the gate.

## The general clause

> Wherever a gate's subject is a SET rather than a magnitude, it must state a minimum cell
> occupancy. The tail of any partitioned population is populated by ones and twos — that is
> a property of partitioning, not of correctness — so a rule that weighs a two-row cell
> equally with a five-hundred-row cell is a rule that can never go green **for reasons
> unrelated to the thing it grades**.

A threshold that a single observation can trip is not measuring the population. It is
measuring whether the population has a tail, and every population has a tail.

## Why this is safe here, which is the whole argument

A floor is legitimate **only** if the set it discounts is a minority of the evidence.
Otherwise it is an escape hatch: it would hand Gate 5 back the `agrees`-by-timeout that
CAL-P086B just took away.

Measured 2026-08-22 on the served payload, frozen in
`artifacts/cal-p087/ARTIFACT-CAL-P087-GATE0-SPLIT-PRE-READ.json`:

| | |
|---|---|
| in-scope bucket keys | **608** |
| of those, `n <= 2` | **159** |
| **surviving the floor** | **449** |

**449 in-scope misses still force `disagrees`, so Gate 0 reads RED today and
`agrees`-by-timeout stays dead.** A fold that produces zero rows leaves all 449 unmatched
and above the floor. That is the ruling's precondition, not a happy accident, and it is
pinned by an executing test —
`test_cal_p088_min_n_floor.py::test_floor_cannot_resurrect_agrees_by_timeout` — which
reads the artifact rather than restating it, so if the population ever shifts under the
floor the test fails instead of the gate quietly softening.

## Two obligations that travel with it

**1. The floor is reported, never silent.** Discounted keys appear under
`published_only_in_scope_below_floor` with their own counts, and they remain in the
`published_only_in_scope` union so no reader loses a row. *No thin cells* and *thin cells
discounted* must be distinguishable from the artifact alone — gotcha #53 applied to the
instrument's own output. A floor that removed rows from the reported set would be
indistinguishable from a fold that found them.

**2. An UNDISCLOSED `n` is not a thin cell.** A payload that does not say how big a bucket
is has not said it is small. Discounting it would let an undisclosed population buy
silence — the same move `tolerance_pp` already refuses one level up, where an
undisclosed drift yields `unmeasurable` rather than a default bound. Undisclosed counts
toward the verdict.

This second clause was **not in the directive**; it was found by an existing CAL-P078
fixture that publishes a bucket with no `n` at all, which the first implementation
silently treated as `n = 0` and discounted. The test caught the ruling being written one
notch too loose, which is the argument for banking the floor with its implementation
rather than ahead of it.

## Scope

This narrows **which** in-scope misses may force the verdict. It does not touch:

* the out-of-scope split — those were already excluded, for a different and structural
  reason, and merging the two silences would be one bucket again;
* `db_only` — the twin seeing more than the payload is a different asymmetry;
* the tolerance path — `outside` still forces `disagrees` at any `n`.

Implemented in the split reconcile (`app/utils/calibration_published_twin.py`) with a test
on **each side** of the floor, and mutation-tested: dropping the floor to 0, letting thin
rows force the verdict, discounting an undisclosed `n`, and omitting the below-floor
report were each introduced deliberately and each turned the suite red on the first pass.
