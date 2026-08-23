# STAGED ITEM — #2098: `mode_prices` / `deduped` must join on `source`

**Staged by CAL-P088, 2026-08-23, on the Fable directive of the same day (item 5).
NOT EXECUTED. Sequenced AFTER the apply blockers.**

Authority: **ruling 125** (`docs/rulings/125-a-row-deleting-join-must-carry-every-dimension-that-identifies-the-row.md`)
— banked in the same window, ahead of this fix, by design. The judgment that the current
behaviour is WRONG is settled. What follows is only the certification of the change.

---

## 0. Sequencing — read this before scheduling

This item is **blocked behind** the apply, not merely ordered after it:

1. `program/calibration-86` (#2111 + ruling 124) merges and **deploys**.
2. The attended one-off `--bank` fold runs (`§4` of this window's runbook,
   `.claude/handoff/QUEUE-STAGED-CAL-APPLY-HINDSIGHT-EXCLUSION.md` §5c).
3. Gate 5 reads a real verdict for the first time.
4. The hindsight-exclusion apply lands and its closing report quotes both number pairs.
5. **Only then** this item.

Reason it cannot jump the queue: this change moves `_main_input_fingerprint()`, which
invalidates every banked unit and restarts the convergence count. Doing that while Gate 5
is still waiting on its first successful fold would destroy the very population the fold
is trying to measure, and the apply's frozen befores
(`artifacts/cal-p087/ARTIFACT-CAL-P087-APPLY-BEFORES-PINNED.json`) would no longer describe
the curve the apply acts on.

## 1. The change

In `_calibration_population_ctes()` (`backend/app/tasks/precompute_calibration.py`):

```sql
-- mode_prices
GROUP BY vm_id, source, adj_opening_probability, eligible        -- + source

-- deduped
LEFT JOIN mode_prices mp
       ON mp.vm_id = ro.vm_id
      AND mp.source = ro.source                                  -- + this line
      AND mp.mode_price = ro.adj_opening_probability
```

Two lines. The size of the diff is not the size of the obligation.

## 2. Ruling 009 — the freeze exception this needs

`precompute_calibration.py` is FROZEN. This item requires, **before any edit**:

- [ ] A named exception granted by the freeze's owner, recorded the way
      `GO-CAL-P078-HINDSIGHT-EXCLUSION-EXCEPTION.md` was.
- [ ] An explicit **re-baseline declaration**: `_main_input_fingerprint()` moves, so every
      banked unit is invalidated and the convergence count restarts from zero. State the
      unit count being discarded, measured, not estimated.
- [ ] Confirmation that no other freeze exception is in flight against the same file
      (two exceptions to one frozen file in one cycle is a merge hazard, not a process one).

## 3. The cert — what must be measured, and in which order

**3a. The falsifier FIRST (doctrine clause 18, applied in reverse).**

Ruling 103 / clause 18 grade a row-**dropping** fix on the rows it KEEPS and on the CONTROL
cells where the mechanism is absent. This fix **restores** 35 rows, so the same two
obligations apply with the sign flipped:

- [ ] **Control cells.** Every cell NOT containing one of the 2 affected `vm_id`s must move
      by **0.000 pp**. Not "approximately" — this change cannot touch them, and if one
      moves, the join predicate is doing something other than what is claimed. This is the
      falsifier and it is attacked first.
- [ ] **The affected cells**, named, with before/after `n` and rate. Expect `n` to RISE by
      exactly the restored legs.

**3b. The restored rows are CORRECT, not merely present.**

- [ ] For `e:14887630`, show the 23 Kalshi legs returning, and show that the Polymarket
      legs are **still** deduped among themselves — the fix must not disable dedup, only
      scope it. A fix that restores rows by breaking the mechanism is worse than the defect.
- [ ] Confirm the restored legs' `is_winner` and `adj_opening_probability` are the values
      the source published, not nulls extended by a changed join shape.

**3c. Stated curve movement.**

- [ ] Full-population ECE/MCE before and after, from the same fold, quoted as a pair.
      35 rows against a ~870,000-outcome denominator should move the headline by
      approximately nothing — **and that is a prediction the cert must state in advance and
      then check**, because "the number barely moved" is equally consistent with the change
      not having applied at all (the mutation-must-prove-it-applied rule).
- [ ] A row count proving the change applied: `deduped` row count before vs after,
      expected delta **+35**.

**3d. Regression guard.**

- [ ] A test that fails if `mp.source = ro.source` is removed. Not a string assertion on
      the SQL — a fixture with one `event_id` reachable from two sources, proving the legs
      of one do not suppress the legs of the other. String assertions on frozen SQL have
      already produced one false sense of coverage in this module's history.

## 4. Expected outcome, stated in advance

- `deduped` gains **35 rows** (2 `vm_id`s).
- Control cells move **0.000 pp**.
- Headline ECE/MCE move **< 0.01 pp** — restated: this fix is a CORRECTNESS fix, not a
  metric fix, and if it materially improves the headline that is a finding requiring its
  own explanation, not a success.

## 5. What this item explicitly does NOT do

- It does not reopen source-chunking (#2076). Chunking was closed on cost and on the
  measured pushdown, independently of this defect. Removing one objection is not an
  argument.
- It does not change `vm_id` itself. Making the id source-carrying would be a much larger
  re-baseline touching `g:`, `e:` and `m:` arms and every downstream key. The join is where
  the defect acts; the join is where it is fixed.

## 6. Evidence this item inherits

- `artifacts/cal-p087/ARTIFACT-CAL-P087-2098-CROSS-SUPPRESSION.json` — the 35-row
  measurement, whole domain, 0 unswept ranges.
- `backend/scripts/measure_2098_mode_price_collision.py` — re-runnable; run it again
  immediately before the fix so the before is hours old, not days.
- Issue #2098 and ruling 125.
