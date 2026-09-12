# SUPERSEDED — these two folds ran on the id-range rail. Do not quote them.

CERT-2428 (2026-09-10 00:52Z) blocked CAL-P1077's first presentation on the
POPULATION, not the arithmetic. Both files here were written by
`backend/scripts/calibration_cell_exact.py`'s `sweep()`, which partitions on raw
`futures_markets.id` ranges and **re-derives `group_sizes` / `event_sizes` inside
every slice**. That is the CAL-P124 defect: on `polymarket/basketball` the same
rail reproduced 8,426 of the cell's 13,135 published rows (**−35.85%**), and the
missing rows are not a sample — the mechanism also re-assigns markets between
the very classes a dimension names, changing virtual-question identity, the
representative pick, and the arms being graded.

So a conclusion about the **published** cell cannot be read off these files
however stable the number is. Repetition proves the returned partition is
stable; it does not prove it equals the published partition.

They are kept, not deleted, for two reasons:

1. **They are the negative control** for
   `test_the_id_range_rail_really_does_leave_a_different_fingerprint`
   (`backend/tests/test_calibration_cell_exact_p1077_dims.py`). That guard needs
   a real specimen of each rail on the SAME two cells, or "the artifact names
   the whole-vm rail" is a check on a key that everything happens to carry.
2. **The arithmetic inside them was independently verified by review** — the
   review recomputed economics `z_not_lone` 9,224 / 3.78 / +1.55 and hockey's
   near-certain arms 164 / 0.34 and 9 / 0.01 from these very files. Deleting
   them would delete the evidence of what the wrong rail said, which is what
   makes the re-fold's agreements and disagreements readable.

The rail that supersedes them is `backend/scripts/calibration_whole_vm_fold.py`
(CAL-P125): Stage A freezes the virtual-market generation ONCE for the whole
cell, Stage B replays that frozen roster per unit through the producer's own
`plan_units`, and a `vm_id` is never split. Its artifacts carry `"rail":
"whole_vm"` and no `width`; these carry `width` and no `rail`.

The banked folds are the four `whole-vm-fold{1,2}-*.json` files one directory up.
