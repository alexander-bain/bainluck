#!/usr/bin/env python3
"""LAT-P131 mutation battery — does the guard suite actually hold the fix down?

Each mutant edits ``app/tasks/precompute_category_pages.py``, asserts the edit
CHANGED the file (a mutation that fails to apply reports green and proves
nothing), runs the guard suites, and restores the original from a byte-for-byte
backup in a ``finally``.

Both suites run, not just the new one: the widening also had to leave #901's
golf assertion standing, and a mutant that satisfies the new file while breaking
the old one is not killed, it is traded.

Run from ``backend/``:  ``python3 scripts/lat_p131_mutation_battery.py``
"""

import hashlib
import shutil
import subprocess
import sys
from pathlib import Path

TARGET = Path("app/tasks/precompute_category_pages.py")
BACKUP = Path("/tmp/lat_p131_precompute_backup.py")
SUITES = [
    "tests/test_precompute_grids_budget.py",
    "tests/test_precompute_grids_warm.py",
]

# (name, description, old, new)
MUTANTS = [
    (
        "M-SHRINK",
        "restore the defect — warm only the original four leagues",
        '''GRID_WARM_LEAGUES = [
    "la-liga",''',
        '''GRID_WARM_LEAGUES = ["mlb", "nba", "nhl", "golf"]
_LAT_P131_DEAD = [
    "la-liga",''',
    ),
    (
        "M-NOBUDGET",
        "THE SECOND DOOR — compute the deadline, report it, hand wait_for the ceiling",
        "                    timeout=deadline_s,",
        "                    timeout=GRID_WARM_TIMEOUT_S,",
    ),
    (
        "M-NOCEILING",
        "drop the per-league ceiling so a big budget hands out an unbounded slice",
        "        deadline_s = min(float(GRID_WARM_TIMEOUT_S), share)",
        "        deadline_s = share",
    ),
    (
        "M-GREEDY",
        "gotcha #34 — give each league everything that is LEFT instead of its share",
        "        share = _prewarm_target_deadline(budget_left, len(GRID_WARM_LEAGUES) - index)",
        "        share = budget_left",
    ),
    (
        "M-CHARGE-ON-SUCCESS",
        "charge the budget only when a league succeeds — the expensive failure is free",
        """        finally:
            # Charge the pass for the wall time actually spent, whatever the
            # outcome. A `finally` and not four call sites: a league that raises
            # spends the budget exactly as a league that succeeds does, and the
            # one debt the budget must never miss is the expensive failure.
            budget_left = max(0.0, budget_left - (_time.monotonic() - started))""",
        """            budget_left = max(0.0, budget_left - (_time.monotonic() - started))""",
    ),
    (
        "M-NO-EMPTY-GUARD",
        "publish whatever was built — an empty grid clobbers the 24h last-good",
        "                if not _grid_payload_usable(result):",
        "                if False:",
    ),
    (
        "M-EMPTY-READS-OK",
        "record the refused empty build as 'ok' — the report stops being truthful",
        '''                        "outcome": "empty",''',
        '''                        "outcome": "ok",''',
    ),
    (
        "M-LEN-NOT-PREDICATE",
        "hand-roll the usability check so an error envelope with teams publishes",
        "                if not _grid_payload_usable(result):",
        "                if not (result.get('teams') or []):",
    ),
    (
        "M-EXHAUSTED-IS-NOTATTEMPTED",
        "#1484 — make 'never reached' indistinguishable from 'grids never ran'",
        '''                "outcome": "budget_exhausted",''',
        '''                "outcome": "not_attempted",''',
    ),
    (
        "M-BUDGET-OVERRUNS-TASK",
        "raise the pass budget past what the task's soft_time_limit can host",
        "GRID_WARM_PASS_BUDGET_S = 180.0",
        "GRID_WARM_PASS_BUDGET_S = 300.0",
    ),
    (
        "M-WARM-WRONG-ARGS",
        "warm with hours=24 — populates a key no cache-eligible request ever reads",
        "                    get_playoff_grid(slug, hours=None, top=10, debug=False, db=session),",
        "                    get_playoff_grid(slug, hours=24, top=10, debug=False, db=session),",
    ),
    (
        "M-STALE-TTL",
        "shorten the last-good mirror so it no longer outlives the fresh key",
        '                    rc.setex(f"{cache_key}:stale", 86400, payload)',
        '                    rc.setex(f"{cache_key}:stale", 3600, payload)',
    ),
    (
        # Was M-READD-UNBUILDABLE until LAT-P132 (#2302) fixed the build and put
        # `ncaa-basketball` IN the list — at which point re-adding it stopped
        # being a mutation and the mutant would have SURVIVED, quietly turning a
        # 13/13 into a 12/13 that nobody re-read. Inverted rather than deleted:
        # the invariant it guards (the list is a decision, not a default) is
        # unchanged, only its direction is.
        "M-DROP-NCAAB",
        "drop the league LAT-P132 fixed — its first visitor of the day pays 6 s again",
        '''    "mlb",
    "ncaa-basketball",
]''',
        '''    "mlb",
]''',
    ),
]


def run_suites() -> int:
    return subprocess.run(
        [sys.executable, "-m", "pytest", *SUITES, "-q", "--no-header"],
        capture_output=True,
        text=True,
    ).returncode


def main() -> int:
    if not TARGET.is_file():
        print(f"FATAL: run from backend/ — {TARGET} not found")
        return 2
    shutil.copy2(TARGET, BACKUP)
    original = BACKUP.read_text()
    original_sha = hashlib.sha256(original.encode()).hexdigest()

    print(f"denominator: {len(MUTANTS)} mutants queued against {TARGET}")
    print(f"suites:      {' '.join(SUITES)}")
    baseline = run_suites()
    print(
        f"baseline:    suites on the unmutated tree -> exit {baseline} "
        f"({'GREEN' if baseline == 0 else 'RED'})"
    )
    if baseline != 0:
        print("FATAL: baseline is not green; every 'killed' would be meaningless")
        shutil.copy2(BACKUP, TARGET)
        return 2

    killed, survived, harness = [], [], []
    try:
        for name, desc, old, new in MUTANTS:
            if old not in original:
                harness.append(name)
                print(f"{name:<28} HARNESS-FAIL  anchor not found — never applied")
                continue
            mutated = original.replace(old, new, 1)
            if mutated == original:
                harness.append(name)
                print(f"{name:<28} HARNESS-FAIL  replace was a no-op")
                continue
            TARGET.write_text(mutated)
            assert TARGET.read_text() != original, "mutation did not reach disk"
            rc = run_suites()
            TARGET.write_text(original)
            if rc != 0:
                killed.append(name)
                print(f"{name:<28} killed    {desc}")
            else:
                survived.append(name)
                print(f"{name:<28} SURVIVED  {desc}")
    finally:
        shutil.copy2(BACKUP, TARGET)
        restored_sha = hashlib.sha256(TARGET.read_text().encode()).hexdigest()
        assert restored_sha == original_sha, "restore failed — tree is dirty"
        print(f"restore:     SHA-256 identical ({restored_sha[:16]}…)")

    print(
        f"\n{len(killed)}/{len(MUTANTS)} killed, {len(survived)} survived, "
        f"{len(harness)} harness failures"
    )
    if harness:
        print("🔴 a harness failure is NOT a pass — the mutant never ran")
        return 2
    return 0 if len(killed) == len(MUTANTS) else 1


if __name__ == "__main__":
    sys.exit(main())
