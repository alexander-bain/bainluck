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

    # --- CERT-2524: the page is frozen and the write is backed ---------------
    # Each of these five IS the blocked behaviour, put back one property at a
    # time. A guard that stays green here is a guard that would have passed the
    # original apply, which is the thing that got blocked.
    ("let the write re-derive its own scope instead of the frozen page",
     "      AND fo.id = ANY(:page_ids)\n      AND EXISTS (",
     "      AND EXISTS (",
     "test_only_the_plan_read_is_limited_and_keyset_paged"),
    ("write without joining the durable backup",
     "    FROM {BAK_TABLE} b\n    WHERE b.outcome_id = fo.id\n"
     "      AND fo.id = ANY(:page_ids)\n",
     "    WHERE fo.id = ANY(:page_ids)\n",
     "test_the_write_can_only_reach_a_row_the_backup_already_holds"),
    ("trust the plan's market gate instead of re-testing it at write time",
     "      AND {_MARKET_HAS_NO_GRADE}\n    RETURNING fo.id",
     "    RETURNING fo.id",
     "test_the_write_re_tests_the_market_gate_it_was_planned_under"),
    ("lock only the page's own legs, leaving a split market's sibling free",
     "    WHERE fo.market_id = ANY(:market_ids)\n",
     "    WHERE fo.id = ANY(:page_ids)\n",
     "test_the_lock_covers_every_leg_of_the_market_not_just_the_page"),
    ("let a late undo overwrite a verdict written since the withdrawal",
     "      AND fo.resolution_source IS NULL\n"
     "      AND fo.is_winner IS DISTINCT FROM b.is_winner",
     "      AND fo.is_winner IS DISTINCT FROM b.is_winner",
     "test_the_undo_will_not_overwrite_a_verdict_somebody_else_wrote"),
]

#: Mutants whose only witness is a real server, listed so the gap is a NAMED
#: one rather than a silence. `initdb` cannot run on this machine at all — the
#: SysV interlock segment is refused (`shmget ... Operation not permitted`)
#: even with `shared_memory_type=mmap` and even outside the agent sandbox — so
#: these are proven by the CI `search-recall` job, not here.
PG_ONLY = [
    ("keep the backup row for a leg the write conceded to a grader",
     "stale_backup = sorted(inserted - set(changed_ids))", "stale_backup = []",
     "test_apply_cannot_withdraw_or_unback_a_page_when_a_grader_commits_"
     "between_backup_and_update"),
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
