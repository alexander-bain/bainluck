#!/usr/bin/env python3
"""CAL-P143 — prove the pre-built 12-CAL suite is RED today and GREEN patched,
without ever writing to the frozen file.

Ruling 009 freezes ``backend/app/tasks/precompute_calibration.py``, so the patch
cannot be applied to check that the guards it ships with actually hold. This
verifier closes that gap the only way that is honest: it rebuilds the patched
producer as a SCRATCH COPY under /tmp, imports it under its own module name, and
runs the suite's own assertion function against both the real chain and the
patched one.

    real chain     -> assert_repaired_population MUST raise   (the defect is live)
    patched chain  -> assert_repaired_population MUST pass    (the fix works)

A pre-built regression suite that has never been run against the thing it is
meant to guard is a document, not a control. Run from ``backend/``::

    python3 ../artifacts/cal-p143/verify-12cal-suite.py
"""

from __future__ import annotations

import importlib.util
import pathlib
import subprocess
import sys
import types

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parents[1]
BACKEND = REPO / "backend"
SCRATCH = pathlib.Path("/tmp/cal-p143-verify")

sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(BACKEND / "scripts"))
sys.path.insert(0, str(HERE))


def build_scratch() -> tuple[pathlib.Path, pathlib.Path]:
    """Apply the patch to copies under /tmp. The worktree is never written."""
    prod_rel = "backend/app/tasks/precompute_calibration.py"
    cens_rel = "backend/scripts/calibration_missing_loser_census.py"
    guard_rel = "backend/tests/test_calibration_missing_loser_census_p122.py"
    for rel in (prod_rel, cens_rel, guard_rel):
        dst = SCRATCH / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes((REPO / rel).read_bytes())
    # ``patch`` rather than ``git apply``: the scratch tree is deliberately not
    # a git repository, and git apply refuses paths outside one.
    r = subprocess.run(
        ["patch", "-p1", "--batch", "--silent",
         "-i", str(HERE / "12cal-lost-losses.patch")],
        cwd=SCRATCH, capture_output=True, text=True,
    )
    if r.returncode != 0:
        sys.exit(f"FATAL: patch did not apply to the scratch copy:\n{r.stderr}")
    return SCRATCH / prod_rel, SCRATCH / cens_rel


def load(path: pathlib.Path, name: str) -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def main() -> int:
    prod_path, cens_path = build_scratch()

    import calibration_missing_loser_census as mlc_real
    from app.tasks.precompute_calibration import _calibration_population_ctes

    suite = load(HERE / "test_calibration_lost_losses_12cal.py",
                 "cal_p143_suite")

    ok = True

    # --- the red must be SUBSTANTIVE, not incidental -----------------------
    # The suite reads two constants the live instrument does not have yet, so
    # its failure alone would be red for the wrong reason. Pin the defect
    # directly: the live chain still carries the bare gate.
    live_sql = _calibration_population_ctes()
    live_gate = live_sql.split("clean_vms AS (", 1)[1].split(
        "\n            ),", 1)[0]
    if "AND has_winner >= 1" not in live_gate or "graded >= 1" in live_gate:
        ok = False
        print("  🔴 the live chain is NOT the unrepaired one this patch "
              "targets — re-derive the patch before landing it.")
    else:
        print("  live chain still carries the bare vm-level winner gate")

    # --- RED against the producer as it stands -----------------------------
    try:
        suite.assert_repaired_population(_calibration_population_ctes())
    except AssertionError as e:
        print(f"  RED  on the live chain, as it must be: {str(e)[:90]}")
    except AttributeError as e:
        print(f"  RED  on the live chain (instrument constants absent): {e}")
    else:
        ok = False
        print("  🔴 FAIL: the suite PASSES against the unpatched producer — it "
              "is not guarding anything.")

    # --- GREEN against the patched one -------------------------------------
    mlc_patched = load(cens_path, "mlc_p143_patched")
    prod_patched = load(prod_path, "precompute_calibration_p143_patched")

    # The suite reads the instrument through the module object it imported, so
    # point that at the patched instrument for the patched run.
    suite.mlc = mlc_patched
    try:
        suite.assert_repaired_population(
            prod_patched._calibration_population_ctes())
        print("  GREEN on the patched chain")
    except AssertionError as e:
        ok = False
        print(f"  🔴 FAIL: the patched chain does not satisfy the suite: {e}")

    # --- the pure boundary, on the patched instrument ----------------------
    cases = [(1, 1, 1, True), (1, 1, 0, False), (1, 2, 2, False),
             (2, 2, 2, False), (1, 3, 3, False), (3, 3, 3, False)]
    for mc, tout, graded, want in cases:
        got = mlc_patched.lone_claim_is_restorable(mc, tout, graded)
        if got is not want:
            ok = False
            print(f"  🔴 boundary wrong at ({mc},{tout},{graded}): {got}")
    print(f"  boundary table: {len(cases)} cases")

    for mc in range(1, 4):
        for tout in range(1, 4):
            arm = mlc_patched.classify_vm(mc, tout)
            r = mlc_patched.lone_claim_is_restorable(mc, tout, graded=tout)
            if (arm == mlc_patched.ARM_LONE) is not r:
                ok = False
                print(f"  🔴 producer arm != census arm at ({mc},{tout})")
    print("  census arm == producer arm on all 9 (market_count, total_outcomes)")

    # The live instrument must still pin the DEFECT while the defect is live.
    if mlc_real.CLEAN_VMS_GATE_FRAGMENT != "AND has_winner >= 1":
        ok = False
        print("  🔴 the live instrument no longer pins the live gate")

    print("VERDICT: " + ("PRE-BUILD VERIFIED" if ok else "🔴 PRE-BUILD BROKEN"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
