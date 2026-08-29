#!/usr/bin/env python3
"""LAT-P132 mutation battery — does the guard suite actually hold the fix down?

The defect this ship fixes was **invisible in results**: the candidate scan
selected exactly the right rows, and its only symptom was a query plan and a
16.2 s ``maxq``. So every mutant below leaves the row set unchanged and breaks
only the shape or the bounds — which is precisely the class a results test
cannot see. If any of these survives, the guard is decorative.

Each mutant edits ``app/routes/playoffs.py``, asserts the edit CHANGED the file
(a mutation that fails to apply reports green and proves nothing), runs the
guard suites, and restores the original from a byte-for-byte backup in a
``finally``.

Both suites run, not just the new one: LAT-P129's source-scoping and its
behavioural evaluator have to survive this change, and a mutant that satisfies
the new file while breaking the old one is not killed, it is traded.

Run from ``backend/``:  ``python3 scripts/lat_p132_mutation_battery.py``
"""

import hashlib
import shutil
import subprocess
import sys
from pathlib import Path

TARGET = Path("app/routes/playoffs.py")
BACKUP = Path("/tmp/lat_p132_playoffs_backup.py")
SUITES = [
    "tests/test_grid_external_id_range_lat_p132.py",
    "tests/test_playoff_grid_source_scoped_candidates_lat_p129.py",
]

# (name, description, old, new)
MUTANTS = [
    (
        "M-NO-RANGE",
        "restore the defect — bare ILIKE, back to the 266K-row heap recheck",
        """    ilike = FuturesMarket.external_id.ilike(f"{prefix}%")
    bounds = external_id_prefix_range(prefix)""",
        """    ilike = FuturesMarket.external_id.ilike(f"{prefix}%")
    bounds = None if prefix else external_id_prefix_range(prefix)""",
    ),
    (
        "M-RANGE-REPLACES-ILIKE",
        "P129-3's REJECTED FORM — drop the ILIKE and let the range be the authority",
        """    return and_(
        FuturesMarket.external_id >= low,
        FuturesMarket.external_id < high,
        ilike,
    )""",
        """    return and_(
        FuturesMarket.external_id >= low,
        FuturesMarket.external_id < high,
    )""",
    ),
    (
        "M-TIGHTEN-LOW",
        "THE ONE CHARACTER THE PROOF LIVES IN — low = prefix, P129's unsafe bound",
        "    stem = prefix[:-1]\n    return stem, stem + chr(ord(last) + 1)",
        "    stem = prefix[:-1]\n    return prefix, stem + chr(ord(last) + 1)",
    ),
    (
        "M-NO-UPPER-BOUND",
        "keep the low bound only — the index scan runs to the end of the source",
        """    return and_(
        FuturesMarket.external_id >= low,
        FuturesMarket.external_id < high,
        ilike,
    )""",
        """    return and_(
        FuturesMarket.external_id >= low,
        ilike,
    )""",
    ),
    (
        "M-NO-LOWER-BOUND",
        "keep the upper bound only — the scan starts at the beginning of the source",
        """    return and_(
        FuturesMarket.external_id >= low,
        FuturesMarket.external_id < high,
        ilike,
    )""",
        """    return and_(
        FuturesMarket.external_id < high,
        ilike,
    )""",
    ),
    (
        "M-ALLOW-Z",
        "'z' + 1 == '{' — punctuation, which en_US.UTF-8 IGNORES at the primary level",
        '_PREFIX_UNINCREMENTABLE = frozenset("zZ9")',
        '_PREFIX_UNINCREMENTABLE = frozenset("")',
    ),
    (
        "M-ALLOW-ANY-CHAR",
        "accept any prefix alphabet — a wildcard or a space becomes a silent bound",
        """    if any(ch not in _PREFIX_SAFE_CHARS for ch in prefix):
        return None""",
        """    if False:
        return None""",
    ),
    (
        "M-ONE-CHAR-PREFIX",
        "allow a 1-char prefix — low becomes '' and the range bounds nothing below",
        "    if len(prefix) < 2:",
        "    if len(prefix) < 1:",
    ),
    (
        "M-BOUNDS-SWAPPED",
        "emit high as the floor and low as the ceiling — an empty range, no rows",
        """    return and_(
        FuturesMarket.external_id >= low,
        FuturesMarket.external_id < high,
        ilike,
    )""",
        """    return and_(
        FuturesMarket.external_id >= high,
        FuturesMarket.external_id < low,
        ilike,
    )""",
    ),
    (
        "M-DECREMENT-HIGH",
        "off-by-one the successor — the prefix's own last character falls outside",
        "    return stem, stem + chr(ord(last) + 1)",
        "    return stem, stem + chr(ord(last))",
    ),
    (
        # 🔴 The first version of this mutant wrapped `prefix_conditions` in a
        # redundant `or_()` and SURVIVED — correctly, because it changed nothing.
        # Recorded rather than quietly swapped: a surviving mutant is a claim
        # about the guard until you prove it was a claim about the mutant.
        "M-BOUNDS-IN-AN-OR",
        "OR the bounds with the ILIKE instead of ANDing — the range stops restricting",
        """    return and_(
        FuturesMarket.external_id >= low,
        FuturesMarket.external_id < high,
        ilike,
    )""",
        """    return or_(
        and_(
            FuturesMarket.external_id >= low,
            FuturesMarket.external_id < high,
        ),
        ilike,
    )""",
    ),
    (
        "M-DROP-SOURCE-SCOPING",
        "P129's own fix — unscope the id space and the 911K seq scan comes back",
        """            id_space_conditions.append(
                and_(FuturesMarket.source == source, or_(*prefix_conditions))
            )""",
        """            id_space_conditions.append(or_(*prefix_conditions))""",
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
                print(f"{name:<34} HARNESS-FAIL  anchor not found — never applied")
                continue
            mutated = original.replace(old, new, 1)
            if mutated == original:
                harness.append(name)
                print(f"{name:<34} HARNESS-FAIL  replace was a no-op")
                continue
            TARGET.write_text(mutated)
            assert TARGET.read_text() != original, "mutation did not reach disk"
            rc = run_suites()
            TARGET.write_text(original)
            if rc != 0:
                killed.append(name)
                print(f"{name:<34} killed    {desc}")
            else:
                survived.append(name)
                print(f"{name:<34} SURVIVED  {desc}")
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
