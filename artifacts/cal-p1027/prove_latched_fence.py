#!/usr/bin/env python3
"""CAL-P1027 — prove the calibration futures rebuild is LATCHED, not slow.

Run:  cd backend && python3 ../artifacts/cal-p1027/prove_latched_fence.py

The claim under test, from production's own ledger
(``calibration:main:phase_ledger``, generated_at 2026-09-06 05:19:04Z):

    the beat refuses to START any unit, with 18.9 minutes of window unused,
    and the refusal re-derives itself identically every hour forever.

Both halves of the loop are driven by PRODUCTION code, imported, never
re-implemented here:

  * ``_unit_fits_in_window``      — the admission fence (precompute_calibration)
  * ``PhaseLedger.measured_unit_ms`` — the carried cost that feeds it (phase ledger)

Re-deriving either formula locally would make this script agree with production
by construction and it could never see that production is wrong, so it does not.
The only numbers written by hand are the ones READ OFF production's ledger, and
they are all named in OBSERVED below.
"""

import pathlib
import sys

# Running a FILE puts the script's own directory on sys.path, not the cwd, so
# `app` is not importable however you invoke it. Anchor on the repo layout
# instead of on how the script was called.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "backend"))

from app.tasks.precompute_calibration import (
    STAGED_UNIT_WINDOW_SAFETY,
    _unit_fits_in_window,
)
from app.utils.calibration_phase_ledger import PhaseBudget, PhasePlan, PhaseLedger

# --- Observed on production, 2026-09-06 05:19:04Z -----------------------------
# calibration:main:phase_ledger -> stages / unit_costs / plan
OBSERVED = {
    "window_left_ms": 1_136_180,   # stages["staged:window_left_ms"]
    "prior_unit_ms": 928_347,      # stages["staged:prior_unit_ms"]
    "units_done": 6,               # unit_costs["futures"]["units_done"]
    "units_total": 128,            # unit_costs["futures"]["units_total"]
    "units_this_beat": 0,          # stages["staged:units_this_beat"]
    "generation_freeze_ms": 226_604,  # stages["read:futures_generation"]
    "deadline_ms": 1_380_000,      # plan["deadline_ms"]
}

FAILURES: list[str] = []


def check(label: str, got, want) -> None:
    ok = got == want
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}: got {got!r}, want {want!r}")
    if not ok:
        FAILURES.append(label)


def carried_ledger() -> PhaseLedger:
    """A ledger carrying EXACTLY what production carried into the 05:15Z beat."""
    budget = PhaseBudget(
        name="futures",
        required=True,
        budget_ms=1_267_625,
        statement_timeout_ms=1_237_625,
        measured_input=True,
        observations=10,
        unit_ms=OBSERVED["prior_unit_ms"],
        units_total=OBSERVED["units_total"],
        units_done=OBSERVED["units_done"],
    )
    return PhaseLedger(
        plan=PhasePlan(budgets=(budget,)),
        population_version="q269",
        owner="prove-latched-fence",
        generation=0,
        input_fingerprint="c1d6afbc16f728bb345de20f075b017e",
    )


print(__doc__.splitlines()[0])
print(f"\nSTAGED_UNIT_WINDOW_SAFETY = {STAGED_UNIT_WINDOW_SAFETY}\n")

# -- 1. The refusal reproduces on production's own numbers ---------------------
print("1. The 05:15Z beat, replayed through the real fence")
admits = _unit_fits_in_window(
    OBSERVED["window_left_ms"], 0.0, float(OBSERVED["prior_unit_ms"])
)
required = OBSERVED["prior_unit_ms"] * STAGED_UNIT_WINDOW_SAFETY
short = required - OBSERVED["window_left_ms"]
print(f"  required = {required:,.0f} ms   have = {OBSERVED['window_left_ms']:,} ms"
      f"   short by {short:,.0f} ms ({short / OBSERVED['window_left_ms'] * 100:.1f}%)")
check("beat admits a unit", admits, False)
check("production also ran zero units", OBSERVED["units_this_beat"], 0)

# -- 2. The carried cost is what feeds it, and it does not decay ---------------
print("\n2. Where prior_unit_ms comes from (production's own accessor)")
ledger = carried_ledger()
check("measured_unit_ms('futures')", ledger.measured_unit_ms("futures"),
      OBSERVED["prior_unit_ms"])
print("  (read off the carried plan — refreshes only when a unit COMPLETES)")

# -- 3. The loop has no exit ---------------------------------------------------
print("\n3. Twenty-four consecutive beats, nothing else changing")
banked = 0
for beat in range(1, 25):
    led = carried_ledger()          # the carry survives the beat, so rebuild it
    prior = float(led.measured_unit_ms("futures") or 0.0)
    # worst_unit_ms is 0.0 because no unit completed THIS beat -- and none can,
    # which is the whole point.
    if _unit_fits_in_window(OBSERVED["window_left_ms"], 0.0, prior):
        banked += 1                  # a unit runs -> the cost would re-measure
print(f"  units admitted across 24 beats: {banked}")
check("24 beats bank nothing", banked, 0)
check("units still short of a generation", OBSERVED["units_done"] < OBSERVED["units_total"], True)

# -- 4. How close the latch is, and what would reopen it -----------------------
print("\n4. The margin — why this reads as flakiness, not a hard stop")
freeze_budget = OBSERVED["deadline_ms"] - required
print(f"  a unit fits again once the generation freeze drops below {freeze_budget:,.0f} ms")
print(f"  it measured {OBSERVED['generation_freeze_ms']:,} ms"
      f"  -> {OBSERVED['generation_freeze_ms'] - freeze_budget:,.0f} ms the wrong side")
check("freeze is the wrong side of the line",
      OBSERVED["generation_freeze_ms"] > freeze_budget, True)

# A faster freeze DOES reopen it -- proving the latch is marginal, not absolute.
reopened = _unit_fits_in_window(
    OBSERVED["deadline_ms"] - 200_000, 0.0, float(OBSERVED["prior_unit_ms"])
)
check("a 200s freeze would admit a unit (control)", reopened, True)

print("\n" + "=" * 72)
if FAILURES:
    print(f"FAILED: {len(FAILURES)} check(s): {', '.join(FAILURES)}")
    sys.exit(1)
print("PROVEN: the fence is latched shut and cannot reopen from the inside.")
print("A unit must complete to refresh prior_unit_ms; no unit may start until it does.")
sys.exit(0)
