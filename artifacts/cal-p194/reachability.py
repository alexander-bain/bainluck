"""CAL-P194-1 — the fifth falsy zero, demonstrated on the REAL classes.

One beat's ledger simultaneously asserts "a unit completed and cost 0 ms" and
"nothing completed, so the basis fell back to the mixed mean".

Runnable from ANYWHERE (it bootstraps ``backend/`` onto sys.path itself):
    python3 artifacts/cal-p194/reachability.py

Read-only: constructs a PhaseLedger and calls its public API. No source edits,
no database, no network. Cannot move the input fingerprint.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

import app.utils.calibration_phase_ledger as cpl  # noqa: E402

NAME = "read:futures_unit"

ledger = cpl.PhaseLedger(
    plan=cpl.derive_plan({}, floors={}),
    population_version="q268",
    owner="p194",
    generation=1,
    input_fingerprint="fp",
)

# ONE unit that COMPLETED, in 0 ms. Reachable because record_stage_outcome
# floors with ``ms = max(0, int(duration_ms))`` — the same line that eats
# P192's -1 sentinel.
ledger.record_stage_outcome(NAME, 0, completed=True)

print("stage_completed_count      =", ledger.stage_completed_count(NAME))
print("stage_completed_mean_ms    =", ledger.stage_completed_mean_ms(NAME))
print(
    "stage_completed_max_ms     =",
    ledger.stage_completed_max_ms(NAME),
    "   <-- P193-1: says NOTHING finished",
)
print()

completed_mean = ledger.stage_completed_mean_ms(NAME)
print("--- what _record_staged_rate does with that mean (calibration_main_build) ---")
print(
    ":1572  completed_mean is None ->",
    completed_mean is None,
    "  => records staged:unit_ms_mean_completed =",
    int(completed_mean) if completed_mean is not None else None,
)
print(
    ":1613  completed_mean truthy  ->",
    bool(completed_mean),
    "  => projection_mean falls back to the MIXED mean",
)
print(
    ":1615  basis flag recorded    ->",
    "staged:beats_basis:completed" if completed_mean else "staged:beats_basis:mixed",
)

print()
print("EXPECTED (the defect):")
print("  count=1, mean=0.0, max=None, unit_ms_mean_completed=0, basis=mixed")
print("  -> the beat says a unit completed AND that nothing completed.")
