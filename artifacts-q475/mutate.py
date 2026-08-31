#!/usr/bin/env python3
"""Mutation battery for LANE1-Q475 — the league rails' duplicate collapse.

Each mutant is a plausible WRONG version of the fix. A mutant that survives the
suite is a hole in the tests, not a curiosity. Every mutation:

  * is proven to have APPLIED (the source must actually change, and the script
    fails loudly if a needle is not found — a no-op mutation that "passes" is
    the failure mode this check exists for);
  * is restored inside ``finally:`` and verified byte-for-byte by sha256, so a
    crash cannot strand a mutant in the tree;
  * runs the FULL pinned band, not just the file it targets.

Run from the repo root:  python3 artifacts-q475/mutate.py
"""

from __future__ import annotations

import hashlib
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
ROUTE = BACKEND / "app" / "routes" / "league_futures.py"
CANDIDATES = BACKEND / "app" / "utils" / "feed_event_candidates.py"

PINNED = [
    "tests/test_league_rails_dedup_2057.py",
    "tests/test_league_rails_query_plan.py",
    "tests/test_feed_event_candidates.py",
    "tests/test_startup.py",
]

# (label, file, needle, replacement, why this is a plausible wrong fix)
MUTANTS = [
    (
        "A: no collapse at all — the pre-fix rail",
        ROUTE,
        '.where(Event.id.in_(surviving))\n        .order_by(\n            case((Event.status == "live", 0), else_=1),',
        '.where(*filters)\n        .order_by(\n            case((Event.status == "live", 0), else_=1),',
        "the blocked bytes: reverts the upcoming rail to selecting the raw pool",
    ),
    (
        "B: the inner cap is widened (results rail)",
        ROUTE,
        "        [collapsed.c.commence_time.desc(), collapsed.c.id.asc()],\n        RESULTS_LIMIT + 1,",
        "        [collapsed.c.commence_time.desc(), collapsed.c.id.asc()],\n        10_000,",
        "widens the inner cap so the plan hydrates every survivor before the "
        "sort discards them. Correct rows, 100x the blocks — a COST regression "
        "invisible to every executing test (no local Postgres), so it is pinned "
        "on the statement instead",
    ),
    (
        "B2: the inner cap is widened (upcoming rail)",
        ROUTE,
        "        UPCOMING_GAMES_LIMIT + 1,\n    )",
        "        10_000,\n    )",
        "the same cost regression on the sibling rail — B only reached the "
        "results one, and a battery that tests one of two arms tests neither",
    ),
    (
        "H2: the tiebreak is DEMOTED rather than deleted",
        ROUTE,
        "            collapsed.c.commence_time.asc(),\n            collapsed.c.id.asc(),",
        "            collapsed.c.id.asc(),\n            collapsed.c.commence_time.asc(),",
        "id-first orders the rail by creation order, not by kickoff — a deletion "
        "guard that only checks PRESENCE would let this through",
    ),
    (
        "C: survivor by lowest id — 'the original row wins'",
        CANDIDATES,
        "order_by=[scanned.c[label].desc() for label in SURVIVOR_SIGNAL_NAMES]\n                + [scanned.c.id.asc()],",
        "order_by=[scanned.c.id.asc()],",
        "#2213's exact mistake: keeps the schedule-only copy and renders a coin "
        "flip where a real blend existed",
    ),
    (
        "D: the fixture window swallows a doubleheader",
        CANDIDATES,
        "SAME_FIXTURE_SECONDS = 300",
        "SAME_FIXTURE_SECONDS = 30000",
        "over-collapse — the failure direction that HIDES a real game and leaves "
        "no trace on the page",
    ),
    (
        "E: the window is inert again (exact equality)",
        CANDIDATES,
        "SAME_FIXTURE_SECONDS = 300",
        "SAME_FIXTURE_SECONDS = 0",
        "under-collapse — the MLB 60s twins come straight back",
    ),
    (
        "F: rails share one collapse population",
        ROUTE,
        'collapsed = deduplicated_events(filters, "league_upcoming_games")',
        'collapsed = deduplicated_events(_recent_results_filters(sport_key, now), "league_upcoming_games")',
        "a finished twin would suppress the scheduled row it duplicates",
    ),
    (
        "G: the inner cap loses the live-first key",
        ROUTE,
        '            case((collapsed.c.status == "live", 0), else_=1),\n            collapsed.c.commence_time.asc(),',
        "            collapsed.c.commence_time.asc(),",
        "the inner and outer orderings disagree, so the nine ids picked are not "
        "the nine the rail wants — a live game falls off the page",
    ),
    (
        "H: the deterministic tiebreak is dropped",
        ROUTE,
        "            collapsed.c.commence_time.asc(),\n            collapsed.c.id.asc(),",
        "            collapsed.c.commence_time.asc(),",
        "tied kickoffs go back to being resolved by the plan",
    ),
    (
        "I: the optimization fence is removed",
        ROUTE,
        '        .offset(literal_column("0"))\n        .subquery()',
        "        .subquery()",
        "#2260's 4.9-second cold read on a quiet league",
    ),
    (
        "J: identity-incomplete rows are fused",
        CANDIDATES,
        '        Event.home_team_name == "",\n        Event.away_team_name == "",',
        '        Event.home_team_name == "\\x00NEVER",\n        Event.away_team_name == "\\x00NEVER",',
        "PARTITION BY treats NULLs as equal, so unnamed rows would fuse into one",
    ),
    (
        "K: the results rail forgets its lookback bound",
        ROUTE,
        "        Event.commence_time >= now - timedelta(days=RESULTS_LOOKBACK_DAYS),",
        "        Event.commence_time >= now - timedelta(days=RESULTS_LOOKBACK_DAYS * 1000),",
        "the only bound on the collapse's input set — cost as well as content",
    ),
]


def sha(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_pinned() -> tuple[int, str]:
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", *PINNED, "-q", "--no-header", "-x"],
        cwd=BACKEND,
        capture_output=True,
        text=True,
    )
    return proc.returncode, (proc.stdout + proc.stderr)[-500:]


def main() -> int:
    print("baseline: the pinned band must be GREEN before any mutation\n")
    code, tail = run_pinned()
    if code != 0:
        print(f"BASELINE IS RED (exit {code}) — nothing below means anything\n{tail}")
        return 2
    print(f"  baseline exit {code} — green\n")

    killed, survived = [], []
    for label, path, needle, repl, why in MUTANTS:
        original = path.read_text()
        before = sha(path)
        if needle not in original:
            print(
                f"!! {label}\n   NEEDLE NOT FOUND in {path.name} — mutation did not apply."
            )
            print("   This is a broken battery, not a passing one.")
            return 3
        try:
            mutated = original.replace(needle, repl, 1)
            assert mutated != original, "replacement was a no-op"
            path.write_text(mutated)
            assert sha(path) != before, "file unchanged on disk after write"
            code, tail = run_pinned()
            status = "KILLED " if code != 0 else "SURVIVED"
            (killed if code != 0 else survived).append(label)
            print(f"{status}  {label}\n          why: {why}")
            if code == 0:
                print(
                    f"          >>> the suite stayed green. HOLE IN THE TESTS.\n{tail}"
                )
        finally:
            path.write_text(original)
            after = sha(path)
            assert after == before, f"RESTORE FAILED for {path} ({before} -> {after})"

    print(f"\n{len(killed)} killed / {len(survived)} survived of {len(MUTANTS)}")
    for s in survived:
        print(f"  SURVIVED: {s}")
    return 0 if not survived else 1


if __name__ == "__main__":
    raise SystemExit(main())
