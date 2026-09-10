"""CAL-P1088 mutation battery: does each guard actually fail when its property breaks?

A guard that passes on the mutant is decoration. Each entry patches ONE property
in `repair_pm_ungraded_loss.py`, runs the named test, and requires a RED.
"""
import shutil, subprocess, sys, pathlib

RAIL = pathlib.Path("backend/app/tasks/repair_pm_ungraded_loss.py")
BAK = pathlib.Path("/tmp/cal1088-rail-original.py")

MUTANTS = [
    ("drop the market-level anti-join",
     "      AND {_MARKET_HAS_NO_GRADE}\n", "",
     "test_the_bound_is_gated_at_the_market"),
    ("widen the SET to stamp last_updated",
     "    SET is_winner = NULL\n",
     "    SET is_winner = NULL, last_updated = now()\n",
     "test_the_apply_writes_exactly_one_column"),
    ("crown a winner instead of withdrawing",
     "    SET is_winner = NULL\n", "    SET is_winner = true\n",
     "test_the_rail_crowns_nobody"),
    ("match NULL as well as false in the bound",
     "      AND fo.is_winner = false\n", "      AND fo.is_winner IS NOT TRUE\n",
     "test_the_bound_selects_only_an_affirmative_false"),
    ("let the backup overwrite an earlier row",
     "    ON CONFLICT (outcome_id) DO NOTHING\n", "\n",
     "test_the_backup_never_overwrites_an_earlier_row"),
    ("drop the keyset bound",
     "      AND fo.id > :after_id\n", "",
     "test_the_bound_is_keyset_paged_in_a_stable_order"),
]

shutil.copy(RAIL, BAK)
failures = []
try:
    for label, old, new, test in MUTANTS:
        src = BAK.read_text()
        if old not in src:
            failures.append(f"{label}: ANCHOR NOT FOUND (mutation never applied)")
            continue
        RAIL.write_text(src.replace(old, new, 1))
        r = subprocess.run(
            [sys.executable, "-m", "pytest",
             f"tests/test_repair_pm_ungraded_loss_4788.py::{test}", "-q"],
            cwd="backend", capture_output=True, text=True)
        verdict = "RED (guard works)" if r.returncode else "GREEN — SURVIVOR"
        print(f"{verdict:24} {label}  ->  {test}")
        if r.returncode == 0:
            failures.append(f"{label} survived {test}")
finally:
    shutil.copy(BAK, RAIL)

print()
print("SURVIVORS:", failures if failures else "none — every guard is load-bearing")
sys.exit(1 if failures else 0)
