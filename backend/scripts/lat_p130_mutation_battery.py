#!/usr/bin/env python3
"""LAT-P130 — prove the golf-grid guard suite kills the defects it claims to.

A guard test that has never seen its own defect is a hope. This battery plants
each defect back into ``app/routes/playoffs.py`` one at a time and asserts the
suite goes RED, then restores the file byte-for-byte.

Two things it is careful about, both learned the hard way:

* **A mutation that fails to APPLY reports green.** Every mutation asserts its
  own edit landed (the ``old`` text was found and exactly one substitution was
  made) before the suite runs. "No occurrences" is a battery failure, not a
  passing mutant.
* **The restore is asserted, not assumed.** The original bytes are held and
  written back in a ``finally``, and the final SHA-256 is compared to the
  starting one. This file is not covered by the ``evals/*_mutations.py`` residue
  scanner — that trade is stated here rather than hidden.

Usage:  cd backend && python3 scripts/lat_p130_mutation_battery.py
Exit:   0 = every mutant killed · 1 = a mutant survived · 2 = could not measure
"""

from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
TARGET = BACKEND / "app" / "routes" / "playoffs.py"
SUITE = "tests/test_golf_grid_candidate_scan_lat_p130.py"


# (name, what the defect is, old_text, new_text)
MUTATIONS: list[tuple[str, str, str, str]] = [
    (
        "flat-or",
        "the original defect: drop the source scope, OR across two columns",
        """        market_filter = or_(
            and_(
                FuturesMarket.source == _GOLF_SPORT_KEY_ID_SPACE_SOURCE,
                or_(*sport_key_prefixes),
            ),
            category_branch,
        )""",
        """        market_filter = or_(*sport_key_prefixes, category_branch)""",
    ),
    (
        "second-door",
        "scope BOTH id spaces to odds_api — fast, silent, and empties the grid",
        """            category_branch,
        )
    return [""",
        """            and_(
                FuturesMarket.source == _GOLF_SPORT_KEY_ID_SPACE_SOURCE,
                category_branch,
            ),
        )
    return [""",
    ),
    (
        "wrong-id-space",
        "scope the sport-key branch to kalshi instead of odds_api",
        '_GOLF_SPORT_KEY_ID_SPACE_SOURCE = "odds_api"',
        '_GOLF_SPORT_KEY_ID_SPACE_SOURCE = "kalshi"',
    ),
    (
        "drop-resolved-exclusion",
        "stop excluding resolved markets",
        """        market_filter,
        FuturesMarket.status != "resolved",
        FuturesMarket.source != "datagolf",""",
        """        market_filter,
        FuturesMarket.source != "datagolf",""",
    ),
    (
        "drop-datagolf-exclusion",
        "stop excluding datagolf rows",
        """        FuturesMarket.status != "resolved",
        FuturesMarket.source != "datagolf",
    ]""",
        """        FuturesMarket.status != "resolved",
    ]""",
    ),
    (
        "no-memo",
        "the second defect: reload the candidate set on every consumer",
        """        if self._markets is None:
            self._markets = await _load_golf_candidate_markets(self._db, self._config)
            self.loads += 1
        return self._markets""",
        """        self._markets = await _load_golf_candidate_markets(self._db, self._config)
        self.loads += 1
        return self._markets""",
    ),
    (
        "empty-list-reloads",
        "treat an empty result as unloaded, so an empty corpus rescans forever",
        "        if self._markets is None:",
        "        if not self._markets:",
    ),
    (
        "unwired-tour-grid",
        "stop handing the shared holder to each tour grid",
        """                service, tour, config, db, trend_hours, top, candidates=candidates,""",
        """                service, tour, config, db, trend_hours, top,""",
    ),
    (
        "unwired-major-grid",
        "stop handing the shared holder to the upcoming-major grid",
        """                        top=top,
                        candidates=candidates,
                    )""",
        """                        top=top,
                    )""",
    ),
    (
        "class-level-state",
        "hold the candidate set on the class — ORM rows outliving their session",
        '''    __slots__ = ("_db", "_config", "_markets", "loads")''',
        """    _markets = None""",
    ),
]


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _run_suite() -> int:
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", SUITE, "-q", "--no-header", "-x"],
        cwd=BACKEND,
        capture_output=True,
        text=True,
    )
    return proc.returncode


def main() -> int:
    if not TARGET.exists():
        print(f"CANNOT MEASURE: {TARGET} not found")
        return 2

    original_bytes = TARGET.read_bytes()
    original_sha = _sha(TARGET)
    backup = TARGET.with_suffix(".py.lat_p130.bak")
    backup.write_bytes(original_bytes)
    original_text = original_bytes.decode()

    print(f"target      {TARGET.relative_to(BACKEND)}")
    print(f"sha256      {original_sha}")
    print(f"backup      {backup.name}")
    print()

    baseline = _run_suite()
    if baseline != 0:
        print(f"CANNOT MEASURE: the suite is not green before mutating (exit {baseline})")
        TARGET.write_bytes(original_bytes)
        backup.unlink(missing_ok=True)
        return 2
    print("baseline    suite GREEN (exit 0)\n")

    killed, survived, unapplied = [], [], []
    try:
        for name, why, old, new in MUTATIONS:
            count = original_text.count(old)
            if count != 1:
                # An edit that does not land makes a mutant look killed by a
                # suite that never saw it. That is a battery failure.
                unapplied.append((name, f"anchor found {count}x, expected exactly 1"))
                print(f"  UNAPPLIED  {name:<24} anchor found {count}x")
                continue

            mutated = original_text.replace(old, new, 1)
            if mutated == original_text:
                unapplied.append((name, "substitution produced identical text"))
                print(f"  UNAPPLIED  {name:<24} no-op substitution")
                continue

            TARGET.write_text(mutated)
            try:
                rc = _run_suite()
            finally:
                TARGET.write_bytes(original_bytes)

            if rc == 0:
                survived.append((name, why))
                print(f"  SURVIVED   {name:<24} {why}")
            elif rc == 1:
                killed.append(name)
                print(f"  killed     {name:<24} {why}")
            else:
                # Exit 1 is a result. Anything else is a story about the harness
                # (collection error, import failure, SIGKILL) and must not be
                # scored as a kill.
                unapplied.append((name, f"pytest exit {rc} — harness, not a result"))
                print(f"  UNSCORED   {name:<24} pytest exit {rc} (harness)")
    finally:
        TARGET.write_bytes(original_bytes)
        restored = _sha(TARGET)
        backup.unlink(missing_ok=True)

    print()
    print(f"restored    sha256 {restored}")
    if restored != original_sha:
        print("CANNOT MEASURE: the target was not restored byte-for-byte")
        return 2

    total = len(MUTATIONS)
    print(f"result      {len(killed)}/{total} mutants killed")
    if unapplied:
        for name, reason in unapplied:
            print(f"            UNMEASURED {name}: {reason}")
        return 2
    if survived:
        for name, why in survived:
            print(f"            SURVIVED {name}: {why}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
