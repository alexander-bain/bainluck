#!/usr/bin/env python3
"""LAT-P129 mutation battery — does the guard suite actually hold the fix down?

Each mutant edits ``app/routes/playoffs.py``, asserts the edit CHANGED the file
(a mutation that fails to apply reports green and proves nothing), runs the
guard suite, and restores the original from a byte-for-byte backup.

Run from ``backend/``:  ``python3 scripts/lat_p129_mutation_battery.py``
"""

import shutil
import subprocess
import sys
from pathlib import Path

TARGET = Path("app/routes/playoffs.py")
BACKUP = Path("/tmp/lat_p129_playoffs_backup.py")
SUITE = "tests/test_playoff_grid_source_scoped_candidates_lat_p129.py"

# (name, description, old, new)
MUTANTS = [
    (
        "M-FLAT",
        "restore the defect — flatten both id spaces into a bare OR",
        """        if prefix_conditions:
            id_space_conditions.append(
                and_(FuturesMarket.source == source, or_(*prefix_conditions))
            )""",
        """        if prefix_conditions:
            id_space_conditions.extend(prefix_conditions)""",
    ),
    (
        "M-BOTH-KALSHI",
        "scope BOTH id spaces to kalshi — fast plan, Odds API markets vanish",
        '''GRID_ID_SPACE_SOURCE: dict[str, str] = {
    "sport_keys": "odds_api",
    "external_id_prefixes": "kalshi",
}''',
        '''GRID_ID_SPACE_SOURCE: dict[str, str] = {
    "sport_keys": "kalshi",
    "external_id_prefixes": "kalshi",
}''',
    ),
    (
        "M-SWAP",
        "swap the pairing — sport keys to kalshi, tickers to odds_api",
        '''GRID_ID_SPACE_SOURCE: dict[str, str] = {
    "sport_keys": "odds_api",
    "external_id_prefixes": "kalshi",
}''',
        '''GRID_ID_SPACE_SOURCE: dict[str, str] = {
    "sport_keys": "kalshi",
    "external_id_prefixes": "odds_api",
}''',
    ),
    (
        "M-DROP-TICKER",
        "drop the Kalshi id space entirely",
        '''GRID_ID_SPACE_SOURCE: dict[str, str] = {
    "sport_keys": "odds_api",
    "external_id_prefixes": "kalshi",
}''',
        '''GRID_ID_SPACE_SOURCE: dict[str, str] = {
    "sport_keys": "odds_api",
}''',
    ),
    (
        "M-STATUS-COLLAPSE",
        "let the category path see resolved markets too",
        """            and_(category_filter, FuturesMarket.status.in_(("open", "closed")))""",
        """            and_(category_filter, FuturesMarket.status.in_(("open", "closed", "resolved")))""",
    ),
    (
        "M-BARE-STATUS",
        "leak a status term into the bare filter the backfill reuses",
        """    market_filter = (
        or_(*id_space_conditions, *category_conditions)
        if id_space_conditions or category_conditions
        else None
    )""",
        """    market_filter = (
        and_(
            or_(*id_space_conditions, *category_conditions),
            FuturesMarket.status.in_(("open", "closed")),
        )
        if id_space_conditions or category_conditions
        else None
    )""",
    ),
    (
        "M-NONAME",
        "stop pushing the league name filter to SQL (path B.2 loads the category)",
        """            category_conditions.append(
                and_(
                    FuturesMarket.llm_sport_category == config.sport_category,
                    FuturesMarket.name.ilike(f"%{sql_pattern}%"),
                )
            )""",
        """            category_conditions.append(
                FuturesMarket.llm_sport_category == config.sport_category
            )""",
    ),
    (
        "M-PATTERN",
        "'repair' the regex->ILIKE conversion so \\s+ becomes % (widens every grid)",
        """    sql_pattern = re.sub(r"\\\\[bs]", "", pattern_str)
    sql_pattern = re.sub(r"\\\\s\\+|\\\\s\\*", "%", sql_pattern)""",
        """    sql_pattern = re.sub(r"\\\\s\\+|\\\\s\\*", "%", pattern_str)
    sql_pattern = re.sub(r"\\\\[bs]", "", sql_pattern)""",
    ),
]


def run_suite() -> int:
    return subprocess.run(
        [sys.executable, "-m", "pytest", SUITE, "-q", "--no-header", "-x"],
        capture_output=True,
        text=True,
    ).returncode


def main() -> int:
    if not TARGET.is_file():
        print(f"FATAL: run from backend/ — {TARGET} not found")
        return 2
    shutil.copy2(TARGET, BACKUP)
    original = BACKUP.read_text()

    print(f"denominator: {len(MUTANTS)} mutants queued against {TARGET}")
    baseline = run_suite()
    print(f"baseline: suite on the unmutated tree -> exit {baseline}"
          f" ({'GREEN' if baseline == 0 else 'RED'})")
    if baseline != 0:
        print("FATAL: baseline is not green; every 'killed' would be meaningless")
        shutil.copy2(BACKUP, TARGET)
        return 2

    killed, survived, harness = [], [], []
    try:
        for name, desc, old, new in MUTANTS:
            if old not in original:
                harness.append(name)
                print(f"{name:<18} HARNESS-FAIL  anchor not found — mutation never applied")
                continue
            mutated = original.replace(old, new, 1)
            if mutated == original:
                harness.append(name)
                print(f"{name:<18} HARNESS-FAIL  replace was a no-op")
                continue
            TARGET.write_text(mutated)
            assert TARGET.read_text() != original, "mutation did not reach disk"
            rc = run_suite()
            TARGET.write_text(original)
            if rc != 0:
                killed.append(name)
                print(f"{name:<18} killed    {desc}")
            else:
                survived.append(name)
                print(f"{name:<18} SURVIVED  {desc}")
    finally:
        shutil.copy2(BACKUP, TARGET)
        assert TARGET.read_text() == original, "restore failed"

    print(
        f"\n{len(killed)}/{len(MUTANTS)} killed, {len(survived)} survived, "
        f"{len(harness)} harness failures"
    )
    return 0 if len(killed) == len(MUTANTS) else 1


if __name__ == "__main__":
    sys.exit(main())
