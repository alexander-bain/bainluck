#!/usr/bin/env python3
"""LAT-P133 mutation battery — does the guard suite hold #2303's fix down?

The defect was a **missing** ``except``: a Postgres ``statement_timeout``
(SQLSTATE 57014) fired below `/api/playoffs/{league}`'s own 25 s wall, so all of
#1484's truthful-degradation work was bypassed and the user got a bare 500. A
fix for a missing branch has two ways to be wrong and they point in opposite
directions:

* **too narrow** — the branch does not recognise the real production shape
  (``DBAPIError`` wrapping asyncpg's ``QueryCanceledError``), so the 500 comes
  back;
* **too wide** — the branch contains everything, so a syntax error, a dead
  connection or a constraint violation is reported to the user as "degraded,
  try later" and nobody ever chases it.

The mutants below pull in **both** directions on purpose. A suite that only
kills the narrowing half is a suite that would wave through a catch-all, and a
catch-all is how this class of defect gets rewritten as a worse one.

Each mutant edits its target, asserts the edit CHANGED the file (a mutation that
fails to apply reports green and proves nothing), runs both guard suites, and
restores from a byte-for-byte backup in a ``finally``.

Both suites run, not just the new one: #1484's existing degradation contract has
to survive this change, and a mutant that satisfies the new file while breaking
the old one is not killed, it is traded.

Run from ``backend/``:  ``python3 scripts/lat_p133_mutation_battery.py``
"""

import hashlib
import shutil
import subprocess
import sys
from pathlib import Path

ROUTE = Path("app/routes/playoffs.py")
UTIL = Path("app/utils/db_cancellation.py")
TARGETS = [ROUTE, UTIL]
SUITES = [
    "tests/test_grid_db_cancel_degradation_lat_p133.py",
    "tests/test_playoff_grid_degradation.py",
]

# (name, target, description, old, new)
MUTANTS = [
    # -- the predicate: too narrow ------------------------------------------
    (
        "M-WRONG-SQLSTATE",
        UTIL,
        "match 57P01 (admin_shutdown) instead — a plausible neighbour in the same class",
        'QUERY_CANCELED_SQLSTATE = "57014"',
        'QUERY_CANCELED_SQLSTATE = "57P01"',
    ),
    (
        "M-NO-SQLSTATE-TEST",
        UTIL,
        "delete the SQLSTATE branch — only the class name is left",
        """        for attr in ("sqlstate", "pgcode"):
            if getattr(candidate, attr, None) == QUERY_CANCELED_SQLSTATE:
                return True""",
        """        for attr in ():
            if getattr(candidate, attr, None) == QUERY_CANCELED_SQLSTATE:
                return True""",
    ),
    (
        "M-NO-PGCODE",
        UTIL,
        "asyncpg only — a psycopg2-shaped error stops being recognised",
        '        for attr in ("sqlstate", "pgcode"):',
        '        for attr in ("sqlstate",):',
    ),
    (
        "M-NO-CLASSNAME-TEST",
        UTIL,
        "delete the subordinate branch — a driver with no SQLSTATE 500s again",
        """        if type(candidate).__name__ == QUERY_CANCELED_CLASS_NAME:
            return True""",
        """        if False:
            return True""",
    ),
    (
        "M-NO-ORIG",
        UTIL,
        "stop reading SQLAlchemy's .orig — THE PRODUCTION SHAPE, unrecognised",
        '        for attr in ("orig", "__cause__", "__context__"):',
        '        for attr in ("__cause__", "__context__"):',
    ),
    (
        "M-NO-CAUSE",
        UTIL,
        "stop following an explicit raise-from",
        '        for attr in ("orig", "__cause__", "__context__"):',
        '        for attr in ("orig", "__context__"):',
    ),
    (
        "M-NO-CONTEXT",
        UTIL,
        "stop following an implicit re-raise",
        '        for attr in ("orig", "__cause__", "__context__"):',
        '        for attr in ("orig", "__cause__"):',
    ),
    (
        "M-DEPTH-ZERO",
        UTIL,
        "bound the walk at the exception itself — one link is all production needs",
        "_MAX_CHAIN_DEPTH = 8",
        "_MAX_CHAIN_DEPTH = 0",
    ),
    # -- the predicate: too wide --------------------------------------------
    (
        "M-SQLSTATE-CLASS-PREFIX",
        UTIL,
        "match the SQLSTATE CLASS (57xxx) — admin shutdown reads as a timeout",
        "            if getattr(candidate, attr, None) == QUERY_CANCELED_SQLSTATE:",
        "            if str(getattr(candidate, attr, None)).startswith(QUERY_CANCELED_SQLSTATE[:2]):",
    ),
    (
        "M-ALLOW-CANCELLED",
        UTIL,
        "drop the CancelledError guard — a client hang-up carrying 57014 reads as a DB timeout",
        """    if isinstance(exc, asyncio.CancelledError):
        return False""",
        """    if False:
        return False""",
    ),
    (
        "M-MESSAGE-SNIFF",
        UTIL,
        "the predicate this one replaced — match the server's ERROR text",
        "        if type(candidate).__name__ == QUERY_CANCELED_CLASS_NAME:",
        "        if 'statement timeout' in str(candidate).lower() or type(candidate).__name__ == QUERY_CANCELED_CLASS_NAME:",
    ),
    # -- the route: restore the defect --------------------------------------
    (
        "M-NO-DB-CATCH",
        ROUTE,
        "#2303 itself — every database error propagates, the 500 comes back",
        "        if not is_query_canceled(exc):\n            raise",
        "        if True:\n            raise",
    ),
    (
        "M-CATCH-ALL",
        ROUTE,
        "THE SECOND DOOR — contain everything; a query bug is served as 'try later'",
        "        if not is_query_canceled(exc):\n            raise",
        "        if False:\n            raise",
    ),
    # -- the route: degrade, but not truthfully ------------------------------
    (
        "M-SAME-REASON",
        ROUTE,
        "collapse the two causes — the sentinel can no longer tell wall from database",
        "            league_slug, cache_key, cache_eligible, GRID_FAILURE_DB_CANCELED",
        "            league_slug, cache_key, cache_eligible, GRID_FAILURE_TIMEOUT",
    ),
    (
        "M-NOT-DEGRADED",
        ROUTE,
        "label the serve routine-stale instead of degraded — #1484's exact defect",
        '        return _mark_last_good(last_good, reason, degraded=True)',
        '        return _mark_last_good(last_good, reason, degraded=False)',
    ),
    (
        "M-LAUNDER-UNUSABLE",
        ROUTE,
        "serve an empty last-good — a failure wearing a 200",
        """                candidate = json.loads(raw)
                if _grid_payload_usable(candidate):
                    last_good = candidate""",
        """                candidate = json.loads(raw)
                if True:
                    last_good = candidate""",
    ),
    (
        "M-500-NOT-503",
        ROUTE,
        "keep the status the defect produced — degradation that reads as a crash",
        "    raise HTTPException(\n        status_code=503,",
        "    raise HTTPException(\n        status_code=500,",
    ),
    (
        "M-IGNORE-CACHE-ELIGIBILITY",
        ROUTE,
        "look for last-good on a debug/param request that has no cache key",
        "    last_good = None\n    if cache_eligible:",
        "    last_good = None\n    if True:",
    ),
]


def run_suites() -> int:
    return subprocess.run(
        [sys.executable, "-m", "pytest", *SUITES, "-q", "--no-header"],
        capture_output=True,
        text=True,
    ).returncode


def main() -> int:
    for target in TARGETS:
        if not target.is_file():
            print(f"FATAL: run from backend/ — {target} not found")
            return 2

    backups = {}
    originals = {}
    shas = {}
    for target in TARGETS:
        backup = Path(f"/tmp/lat_p133_{target.name}.backup")
        shutil.copy2(target, backup)
        backups[target] = backup
        originals[target] = backup.read_text()
        shas[target] = hashlib.sha256(originals[target].encode()).hexdigest()

    print(f"denominator: {len(MUTANTS)} mutants queued")
    print(f"targets:     {' '.join(str(t) for t in TARGETS)}")
    print(f"suites:      {' '.join(SUITES)}")
    baseline = run_suites()
    print(
        f"baseline:    suites on the unmutated tree -> exit {baseline} "
        f"({'GREEN' if baseline == 0 else 'RED'})"
    )
    if baseline != 0:
        print("FATAL: baseline is not green; every 'killed' would be meaningless")
        for target, backup in backups.items():
            shutil.copy2(backup, target)
        return 2

    killed, survived, harness = [], [], []
    try:
        for name, target, desc, old, new in MUTANTS:
            original = originals[target]
            if old not in original:
                harness.append(name)
                print(f"{name:<28} HARNESS-FAIL  anchor not found — never applied")
                continue
            mutated = original.replace(old, new, 1)
            if mutated == original:
                harness.append(name)
                print(f"{name:<28} HARNESS-FAIL  replace was a no-op")
                continue
            target.write_text(mutated)
            assert target.read_text() != original, "mutation did not reach disk"
            rc = run_suites()
            target.write_text(original)
            if rc != 0:
                killed.append(name)
                print(f"{name:<28} killed    {desc}")
            else:
                survived.append(name)
                print(f"{name:<28} SURVIVED  {desc}")
    finally:
        for target, backup in backups.items():
            shutil.copy2(backup, target)
            restored = hashlib.sha256(target.read_text().encode()).hexdigest()
            assert restored == shas[target], f"restore failed for {target} — tree is dirty"
            print(f"restore:     {target} SHA-256 identical ({restored[:16]}…)")

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
