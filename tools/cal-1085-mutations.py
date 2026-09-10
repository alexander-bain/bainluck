#!/usr/bin/env python3
"""Mutation battery for CAL-P1085 (#4745): does the guard suite actually bite?

Each mutation is a defect a future edit could plausibly introduce. A mutation
that leaves the suite GREEN is a guard that does not guard. The negative
control must stay green — otherwise the battery is only proving that editing
the file at all breaks it.

    python3 tools/cal-1085-mutations.py
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "backend"
UTIL = BACKEND / "app" / "utils" / "kalshi_empty_book.py"
PHASE = BACKEND / "app" / "tasks" / "backfill_winners.py"
TESTS = "tests/test_kalshi_empty_book.py"

# (name, file, old, new, expectation)
MUTATIONS = [
    (
        "ceiling widened past the poller's cap",
        UTIL,
        "ASK_ONLY_TRUSTED_MAX = 0.50",
        "ASK_ONLY_TRUSTED_MAX = 0.95",
        "red",
    ),
    (
        "a lone BID is refused too (the asymmetry is the whole finding)",
        UTIL,
        "    if yes_bid > 0:\n        return False\n",
        "",
        "red",
    ),
    (
        "a real trade no longer outranks the book it sits in",
        UTIL,
        "    if last_price is not None and last_price > 0:\n        return False\n",
        "",
        "red",
    ),
    (
        "a missing bid is treated as a zero bid",
        UTIL,
        "    if yes_bid is None or yes_ask is None:\n        return False\n",
        "    if yes_ask is None:\n        return False\n    yes_bid = 0.0 if yes_bid is None else yes_bid\n",
        "red",
    ),
    (
        "the ceiling becomes exclusive, flipping the at-ceiling book",
        UTIL,
        "    return yes_ask > ASK_ONLY_TRUSTED_MAX",
        "    return yes_ask >= ASK_ONLY_TRUSTED_MAX",
        "red",
    ),
    (
        "SQL treats a NULL bid as zero, disagreeing with Python",
        UTIL,
        'f"(COALESCE({alias}.yes_bid, -1) = 0"',
        'f"(COALESCE({alias}.yes_bid, 0) = 0"',
        "red",
    ),
    (
        "SQL drops a COALESCE and can go NULL under NOT",
        UTIL,
        'f" AND COALESCE({alias}.last_price, 0) = 0"',
        'f" AND {alias}.last_price = 0"',
        "red",
    ),
    (
        "the guard is dropped from Phase 0c-repair",
        PHASE,
        '                                  AND NOT {lone_ask_on_empty_book_sql("fos")}\n',
        "",
        "red",
    ),
    (
        "the guard moves to the outer WHERE, dropping whole legs",
        PHASE,
        '                                  AND NOT {lone_ask_on_empty_book_sql("fos")}\n'
        "                                ORDER BY fos.captured_at ASC\n",
        "                                ORDER BY fos.captured_at ASC\n",
        "red",
    ),
    (
        "NEGATIVE CONTROL: a comment reworded",
        UTIL,
        "#: Highest ask an ask-only book may carry and still be trusted as a price.",
        "#: The ask-only ceiling.",
        "green",
    ),
]


def run_suite() -> bool:
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", TESTS, "-q", "--no-header"],
        cwd=BACKEND,
        capture_output=True,
        text=True,
    )
    return proc.returncode == 0


def main() -> int:
    if not run_suite():
        print("BASELINE IS RED — fix the suite before mutating.")
        return 2
    print("baseline: GREEN\n")

    failures = []
    for name, path, old, new, expect in MUTATIONS:
        original = path.read_text()
        if old not in original:
            print(f"  SKIP  {name}\n        anchor not found in {path.name}")
            failures.append(name)
            continue
        backup = Path(tempfile.mkdtemp()) / path.name
        shutil.copy2(path, backup)
        try:
            path.write_text(original.replace(old, new, 1))
            green = run_suite()
        finally:
            shutil.copy2(backup, path)

        got = "green" if green else "red"
        ok = got == expect
        print(f"  {'OK  ' if ok else 'MISS'}  {name}\n        expected {expect}, got {got}")
        if not ok:
            failures.append(name)

    print()
    if failures:
        print(f"{len(failures)} of {len(MUTATIONS)} did NOT behave as expected:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print(f"{len(MUTATIONS)}/{len(MUTATIONS)} as expected, no survivors.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
