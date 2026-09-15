#!/usr/bin/env python3
"""#6358 — mutation sweep for the venue-ticker fold beyond soccer (authority/338).

Each mutant reverts ONE decision this ship made, back to the text that is on
master (or to the plausible weaker spelling a later reader would reach for), then
runs the guard classes. A mutant that SURVIVES is a guard that would not have
caught the defect it was written for.

Two rules carried from the harnesses before this one:

  * A survivor may be EQUIVALENT — look at the mutant before weakening an
    assertion. M11 is the case in point: counting all rows instead of the keyed
    ones is only observable when the two differ, which is why the floor test
    builds a population carrying no ticker at all.
  * A mutant that dies at IMPORT is a weaker kill. Every mutant below is valid
    Python that imports cleanly, so a red is a test result and not a syntax
    error.

It runs against the tree it lives in — `parents[1]` is this worktree, never the
shared master checkout — because a mutation sweep WRITES to the files it mutates
and gotcha #51's directory rule applies to a script exactly as it does to a git
verb.

Usage:  python3 tools/authority-338-mutations-6358.py [--list]
"""

from __future__ import annotations

import argparse
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
GUARDS = [
    "tests/test_venue_ticker_fold_beyond_soccer_6358.py",
    "tests/test_kalshi_fixture_identity_6316.py",
    "tests/test_soccer_ghost_twin_sweep_5896.py",
    "tests/test_soccer_ghost_twins_5896.py",
    "tests/test_soccer_stranded_markets_3813.py",
]

JUDGE = "app/utils/soccer_ghost_twins.py"
TASK = "app/tasks/soccer_ghost_twin_sweep.py"

# (id, file, what it is, shipped text, mutated text)
MUTANTS = [
    (
        "M1",
        JUDGE,
        "the wide ghost arm goes back to the strict one",
        "    return not row.is_fixture_anchored and row.status != LIVE_STATUS",
        "    return row_could_be_a_ghost(row)",
    ),
    (
        "M2",
        JUDGE,
        "the wide arm stops excluding a match in progress",
        "    return not row.is_fixture_anchored and row.status != LIVE_STATUS",
        "    return not row.is_fixture_anchored",
    ),
    (
        "M3",
        JUDGE,
        "the wide arm stops asking whether an authority names the row",
        "    return not row.is_fixture_anchored and row.status != LIVE_STATUS",
        "    return row.status != LIVE_STATUS",
    ),
    (
        "M4",
        JUDGE,
        "the fifth pass's call site reverts to the strict ghost arm",
        "        if row_could_be_a_venue_ticker_ghost(r)",
        "        if row_could_be_a_ghost(r)",
    ),
    (
        "M5",
        JUDGE,
        "the fifth pass drops the kickoff grace",
        "        if row_could_be_a_venue_ticker_ghost(r)\n"
        "        and not (now - GHOST_KICKOFF_GRACE < r.commence_time <= now)",
        "        if row_could_be_a_venue_ticker_ghost(r)",
    ),
    (
        "M6",
        JUDGE,
        "the first pass is handed every sport again",
        "    for row in soccer_rows:\n"
        "        blocks[block_key(row.sport_key, row.home_team_name, row.away_team_name)]",
        "    for row in rows:\n"
        "        blocks[block_key(row.sport_key, row.home_team_name, row.away_team_name)]",
    ),
    (
        "M7",
        JUDGE,
        "the residual (second) pass is handed every sport again",
        "= residual_pass(\n        soccer_rows,",
        "= residual_pass(\n        rows,",
    ),
    (
        "M16",
        JUDGE,
        "the ticker (third) pass is handed every sport again",
        "= ticker_pass(\n        soccer_rows,",
        "= ticker_pass(\n        rows,",
    ),
    (
        "M8",
        JUDGE,
        "the stranded (fourth) pass is handed every sport again",
        "= stranded_market_pass(\n        soccer_rows,",
        "= stranded_market_pass(\n        rows,",
    ),
    (
        "M9",
        JUDGE,
        "the fifth pass is confined to soccer again, which is the whole defect",
        "= fixture_ticker_pass(\n        rows,",
        "= fixture_ticker_pass(\n        soccer_rows,",
    ),
    (
        "M10",
        JUDGE,
        "the partition predicate admits everything",
        '    return str(row.sport_key or "").startswith(SOCCER_KEY_PREFIX)',
        "    return True",
    ),
    (
        "M11",
        JUDGE,
        "the ticker population counts every row instead of the keyed ones",
        "        ticker_rows_considered=sum(1 for row in rows if row.ticker_event_key),",
        "        ticker_rows_considered=len(rows),",
    ),
    (
        "M12",
        TASK,
        "the read goes back to soccer only",
        "         s.key LIKE 'soccer%%'\n"
        "         OR EXISTS (SELECT 1\n"
        "                      FROM futures_markets fm\n"
        "                     WHERE fm.event_id = e.id\n"
        "                       AND fm.source = 'kalshi')",
        "         s.key LIKE 'soccer%%'",
    ),
    (
        "M13",
        TASK,
        "the soccer floor is asked of the total read again",
        "    if plan.soccer_rows_considered < MIN_EXPECTED_ROWS:",
        "    if plan.rows_considered < MIN_EXPECTED_ROWS:",
    ),
    (
        "M14",
        TASK,
        "the ticker floor is asked of the total read, so a dead ticker rail clears it",
        "    if plan.ticker_rows_considered < MIN_EXPECTED_TICKER_ROWS:",
        "    if plan.rows_considered < MIN_EXPECTED_TICKER_ROWS:",
    ),
    (
        "M15",
        TASK,
        "the verdict stops reporting which half of the read it saw",
        '                "soccer_rows_read": plan.soccer_rows_considered,\n'
        '                "ticker_rows_read": plan.ticker_rows_considered,\n',
        "",
    ),
]


def run_guards() -> tuple[int, str]:
    p = subprocess.run(
        [sys.executable, "-m", "pytest", *GUARDS, "-q"],
        cwd=BACKEND,
        capture_output=True,
        text=True,
    )
    return p.returncode, p.stdout + p.stderr


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true", help="print the mutants and stop")
    args = ap.parse_args()

    if args.list:
        for mid, path, what, _, _ in MUTANTS:
            print(f"{mid}  {path}\n      {what}")
        return 0

    code, out = run_guards()
    if code != 0:
        print("BASELINE IS RED — fix that before reading any mutant")
        print(out[-2000:])
        return 2
    print(f"baseline GREEN: {out.strip().splitlines()[-1]}\n")

    results = []
    for mid, rel, what, shipped, mutated in MUTANTS:
        path = BACKEND / rel
        original = path.read_text(encoding="utf-8")
        if original.count(shipped) != 1:
            print(f"{mid}: shipped text found {original.count(shipped)}x — sweep stale")
            results.append((mid, "STALE", what))
            continue
        try:
            path.write_text(original.replace(shipped, mutated), encoding="utf-8")
            code, out = run_guards()
        finally:
            path.write_text(original, encoding="utf-8")
        verdict = "KILLED" if code != 0 else "SURVIVED"
        results.append((mid, verdict, what))
        print(f"{mid}: {verdict} — {what}")

    killed = sum(1 for _, v, _ in results if v == "KILLED")
    print(f"\n{killed}/{len(results)} killed")
    for mid, verdict, what in results:
        if verdict != "KILLED":
            print(f"  {verdict}: {mid} — {what}")
    return 0 if killed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
