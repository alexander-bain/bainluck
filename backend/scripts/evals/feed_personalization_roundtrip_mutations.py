#!/usr/bin/env python3
"""LAT-P113 red-first battery — prove each guard fails against a broken fix.

Discipline inherited from this lane's prior cycles and applied literally:

* every mutation is applied ALONE, from a ``cp`` backup of the pristine file
* the harness REFUSES a pattern that matches other than exactly once, so a
  silent no-op mutation cannot be scored as "the test passed for a reason"
  (LAT-P100 stacked seven mutations that way and the output looked plausible)
* every restore is verified by BOTH ``filecmp`` and ``sha256``, not by trusting
  that the write happened
* the exit code is read by VALUE (gotcha #124): pytest ``1`` is a verdict,
  anything else is a story about the harness
"""

from __future__ import annotations

import filecmp
import hashlib
import shutil
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
TARGET = BACKEND / "app" / "routes" / "feed.py"
BACKUP = BACKEND / ".p113-feed.py.bak"
TESTS = "tests/test_feed_personalization_roundtrips_p113.py"

# (id, description, old, new, tests that MUST go red)
MUTATIONS: list[tuple[str, str, str, str, str]] = [
    (
        "M1",
        "revert the fix: ask all three tables always, gated on a constant false "
        "for the anonymous principal (the exact pre-LAT-P113 behaviour)",
        """    if user:
        favorites_result = await db.execute(
            select(UserFavorite).where(UserFavorite.user_id == user.id)
        )""",
        """    if True:
        favorites_result = await db.execute(
            select(UserFavorite).where(
                UserFavorite.user_id == user.id if user else False
            )
        )""",
        "test_anonymous_principal_issues_exactly_four_round_trips",
    ),
    (
        "M2",
        "skip the user-scoped reads for EVERYONE, including a real user",
        """    pins: list[UserPin] = []
    if user:""",
        """    pins: list[UserPin] = []
    if False:""",
        "test_authenticated_principal_still_issues_all_seven",
    ),
    (
        "M3",
        "keep the round trip but neuter the pins predicate inside the user "
        "branch — SURVIVED the first battery, which is how the guard's hole "
        "was found; the constant-false property was widened to both principals",
        "            select(UserPin).where(UserPin.user_id == user.id)",
        "            select(UserPin).where(False)",
        "test_no_statement_is_ever_gated_on_a_constant_false",
    ),
    (
        "M4",
        "run the pins query and drop its result on the floor",
        "        pins = list(pins_result.scalars().all())",
        "        pins = []",
        "test_authenticated_principal_still_loads_favorites_prefs_and_pins",
    ),
    (
        "M5",
        "break LAT-P089's premise: the anonymous context stops equalling default",
        "        is_authenticated=bool(user),",
        "        is_authenticated=True,",
        "test_the_anonymous_context_still_equals_the_default",
    ),
    (
        "M6",
        "remove the zero-identity short circuit",
        """    if not user and not session_id:
        return PersonalizationContext()""",
        """    if False:
        return PersonalizationContext()""",
        "test_a_principal_with_neither_user_nor_session_still_short_circuits",
    ),
    (
        "M7",
        "run the favorites query and drop its result on the floor",
        "        favorites = list(favorites_result.scalars().all())",
        "        favorites = []",
        "test_authenticated_principal_still_loads_favorites_prefs_and_pins",
    ),
    (
        "M8",
        "re-introduce ONE provably-empty round trip on the anonymous path — the "
        "regression this guard exists to catch, in its most likely future form",
        "    # Recent Discover behaviour",
        """    await db.execute(select(UserPin).where(False))
    # Recent Discover behaviour""",
        "test_no_statement_is_ever_gated_on_a_constant_false",
    ),
]


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    pristine_sha = _sha(TARGET)
    shutil.copy2(TARGET, BACKUP)
    assert filecmp.cmp(TARGET, BACKUP, shallow=False), "backup did not take"

    results: list[tuple[str, str, int, str]] = []
    try:
        for mid, desc, old, new, must_fail in MUTATIONS:
            source = TARGET.read_text()
            hits = source.count(old)
            if hits != 1:
                print(f"{mid}: REFUSED — pattern matched {hits} times, need exactly 1")
                results.append((mid, desc, -1, "PATTERN-REFUSED"))
                continue

            TARGET.write_text(source.replace(old, new, 1))
            assert _sha(TARGET) != pristine_sha, f"{mid}: mutation was a no-op"

            proc = subprocess.run(
                [sys.executable, "-m", "pytest", TESTS, "-q", "--no-header"],
                cwd=BACKEND,
                capture_output=True,
                text=True,
            )
            code = proc.returncode
            named_went_red = f"{must_fail}" in proc.stdout and (
                "FAILED" in proc.stdout or "failed" in proc.stdout
            )
            summary = [
                ln
                for ln in proc.stdout.splitlines()
                if "passed" in ln or "failed" in ln or "error" in ln
            ]
            tail = summary[-1] if summary else proc.stdout.strip()[-160:]

            verdict = "RED" if code == 1 else f"NOT-A-VERDICT(exit {code})"
            if code == 1 and not named_went_red:
                verdict = "RED but NOT via the named test"
            results.append((mid, desc, code, f"{verdict} :: {tail}"))
            print(f"{mid}: exit {code} — {verdict}")
            print(f"     {tail}")

            # restore, and PROVE the restore
            shutil.copy2(BACKUP, TARGET)
            assert filecmp.cmp(TARGET, BACKUP, shallow=False), f"{mid}: restore failed"
            assert _sha(TARGET) == pristine_sha, f"{mid}: restored sha mismatch"
    finally:
        shutil.copy2(BACKUP, TARGET)
        ok = filecmp.cmp(TARGET, BACKUP, shallow=False) and _sha(TARGET) == pristine_sha
        BACKUP.unlink(missing_ok=True)
        print(f"\nFINAL RESTORE: {'VERIFIED' if ok else 'FAILED'} sha={_sha(TARGET)}")

    print("\n==== SUMMARY ====")
    killed = 0
    for mid, desc, code, note in results:
        status = "KILLED" if code == 1 and "NOT via" not in note else "SURVIVED"
        if status == "KILLED":
            killed += 1
        print(f"{mid} {status}: {desc}")
        print(f"    {note}")
    print(f"\n{killed}/{len(MUTATIONS)} mutants killed")
    return 0 if killed == len(MUTATIONS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
