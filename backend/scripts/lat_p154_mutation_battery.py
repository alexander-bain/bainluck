#!/usr/bin/env python3
"""LAT-P154 mutation battery — do the guards actually hold score_resolution down?

THE DEFECT WAS A PHASE THAT SPENT THE WHOLE BUDGET RE-DOING WORK IT HAD ALREADY
DONE. `backfill_winners` returned `partial_budget_guard(prob_and_datagolf)` at
553.6 s with `score_resolution: 397.0` (production task-metrics,
2026-08-30T15:54:13Z), so the merged q436 calibration fix never executed. A
read-only production probe split those 397 s six ways; the fixes here address
five of the six lines, and each mutant below puts one of them back.

A cost fix has TWO failure directions and only one of them is slow:

* **It stops helping** — the shared scan runs twice again, the block prefetch
  degenerates to one round trip per market, the polymarket prefilter comes out
  of the statement. Costs seconds. Invisible to any test that only asks
  "did the resolver resolve?".
* **It stops being correct** — the sibling resolver skips markets it should
  have processed because the locked set over-reports, or it re-processes ones
  the old code would have dropped because the locked set under-reports.
  Costs graded outcomes, silently.

Both directions are represented. The LOCK-* mutants are the point of the file:
every functional test of the resolvers stays green through all of them,
because a resolver that processes the wrong SET of markets is still a correct
resolver of the markets it processes.

Each mutant asserts its edit CHANGED the file before running anything (a
mutation that fails to apply reports green and proves nothing), refuses a
non-unique anchor rather than editing whichever copy `str.replace` reaches
first, and every target is restored from a byte-for-byte backup in a `finally`
with a SHA-256 compare.

Backups are namespaced by the WORKTREE, not just the filename: /tmp is shared
across worktrees and a battery here must never restore a sibling's file.

Run from `backend/`:  `python3 scripts/lat_p154_mutation_battery.py`
"""

import hashlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]

TASK = BACKEND / "app" / "tasks" / "backfill_winners.py"
TARGETS = [TASK]

#: The new battery plus every pre-existing suite over this file — a cost fix
#: that quietly changes resolution semantics must be caught by the OLD guards,
#: not only by the ones written alongside it.
PYTEST_ARGS = [
    "tests/test_score_resolution_cost_latp154.py",
    "tests/test_backfill_winners.py",
    "tests/test_boxscore_resolver_memory.py",
    "tests/test_resolution_authority_038.py",
]

# (name, target, why it must die, needle, replacement)
MUTANTS = [
    # -- the sharing: the 46 s scan runs twice again -------------------------
    (
        "M-SCAN-NOT-SHARED",
        TASK,
        "the identical 46 s candidate statement runs twice per cycle again",
        "score_stats = await _timed_sub(\n        \"game_scores\", _resolve_kalshi_from_scores(scan_out=_game_scan)\n    )",
        "score_stats = await _timed_sub(\n        \"game_scores\", _resolve_kalshi_from_scores()\n    )",
    ),
    (
        "M-SIBLING-IGNORES-THE-SCAN",
        TASK,
        "the handoff is built and then not consumed — pure waste, still 2 scans",
        "        _resolve_kalshi_spread_total_from_scores(scan_in=_game_scan),",
        "        _resolve_kalshi_spread_total_from_scores(),",
    ),
    (
        "M-SCAN-NEVER-RELEASED",
        TASK,
        "~92K candidate rows stay alive through the 14-minute maintenance tail (#899)",
        "    _game_scan.clear()\n    # #140: grade ungraded Polymarket full-game Over/Under from linked scores.",
        "    # #140: grade ungraded Polymarket full-game Over/Under from linked scores.",
    ),
    # -- the sharing: it is no longer EQUIVALENT -----------------------------
    (
        "M-LOCK-IGNORED-BY-SIBLING",
        TASK,
        "reuses the pre-write set: re-processes markets the re-run would have dropped",
        "                markets = [m for m in reused if m.market_id not in locked]",
        "                markets = list(reused)",
    ),
    (
        "M-LOCK-ON-ANY-WRITE",
        TASK,
        "locks a market whose only write was a LOSER — the sibling silently skips it",
        "                    resolved_any = True\n                    if won:\n                        locked_market_ids.add(row.market_id)",
        "                    resolved_any = True\n                    locked_market_ids.add(row.market_id)",
    ),
    (
        "M-LOCK-ON-BTTS-NO",
        TASK,
        "a BTTS 'no' writes only False, so the market stays selectable — locking it drops work",
        "                    if btts_yes:\n                        locked_market_ids.add(row.market_id)",
        "                    locked_market_ids.add(row.market_id)",
    ),
    (
        "M-LOCK-NEVER-EXPORTED",
        TASK,
        "scan_out carries candidates but no locked set — the sibling reuses a stale set",
        "    if scan_out is not None:\n        scan_out[\"locked_market_ids\"] = locked_market_ids",
        "    if scan_out is not None:\n        pass",
    ),
    # -- the block prefetch: back to one round trip per market ---------------
    (
        "M-MONEYLINE-PER-MARKET-FETCH",
        TASK,
        "59,047 round trips a cycle again in the moneyline resolver",
        "                outs = block_outcomes.get(row.market_id, [])",
        "                outs = (await session.execute(text(\n                    \"SELECT id, name FROM futures_outcomes \"\n                    \"WHERE market_id = :mid ORDER BY id\"),\n                    {\"mid\": row.market_id})).all()",
    ),
    (
        "M-SPREAD-PER-MARKET-FETCH",
        TASK,
        "91,776 round trips a cycle again — the single biggest line in the 397 s",
        "                outcomes_list = block_outcomes.get(row.market_id, [])",
        "                outcomes_list = (await session.execute(text(\n                    \"SELECT id, name FROM futures_outcomes \"\n                    \"WHERE market_id = :mid\"),\n                    {\"mid\": row.market_id})).all()",
    ),
    (
        "M-PREFETCH-ONLY-FIRST-BLOCK",
        TASK,
        "block 2 onward reads an empty map — every market past 2,000 silently skipped",
        "                if i % _OUTCOME_PREFETCH_BLOCK == 0:\n                    # LAT-P154: one round trip per block instead of one per\n                    # market. Bounded memory: a block is 2,000 markets.",
        "                if i == 0:\n                    # LAT-P154: one round trip per block instead of one per\n                    # market. Bounded memory: a block is 2,000 markets.",
    ),
    (
        "M-PREFETCH-UNORDERED",
        TASK,
        "outcome order left to the plan — the moneyline resolver's ORDER BY id is gone",
        "            WHERE market_id = ANY(:ids) ORDER BY market_id, id",
        "            WHERE market_id = ANY(:ids)",
    ),
    (
        "M-PREFETCH-EMPTY-HITS-THE-DB",
        TASK,
        "`= ANY('{}')` issued for every empty tail block",
        "    ids = list(market_ids)\n    if not ids:\n        return by_market",
        "    ids = list(market_ids)",
    ),
    # -- the polymarket O/U prefilter ---------------------------------------
    (
        "M-POLY-PREFILTER-DROPPED",
        TASK,
        "LIMIT 20000 saturates with permanently-ungradable rows again (56.2 s, 0 graded)",
        "                      AND m.name ~* ':[[:space:]]*o/u'\n",
        "",
    ),
    (
        "M-POLY-PREFILTER-TOO-TIGHT",
        TASK,
        "an end-anchored SQL filter can under-include; the python parse must stay the authority",
        "                      AND m.name ~* ':[[:space:]]*o/u'\n",
        "                      AND m.name ~* ':[[:space:]]*o/u[[:space:]]*$'\n",
    ),
    # -- the box-score resolvers: back to the futures_markets seq scan -------
    (
        "M-PLAYER-PROPS-INLINE-NULL-CHECK",
        TASK,
        "44.7 s seq scan of futures_markets (1.6 GB) to apply a ticker prefix",
        "                      AND fm.event_id = ANY(:bs_event_ids)\n                      AND (fo.resolution_source IS NULL",
        "                      AND e.box_score_data IS NOT NULL\n                      AND (fo.resolution_source IS NULL",
    ),
    (
        "M-TOTAL-BASES-INLINE-NULL-CHECK",
        TASK,
        "17.9 s seq scan of futures_markets to return ZERO rows",
        "                      AND fm.event_id = ANY(:bs_event_ids)\n                      AND fo.is_winner IS NULL",
        "                      AND e.box_score_data IS NOT NULL\n                      AND fo.is_winner IS NULL",
    ),
    # -- the instrumentation the next cycle needs ----------------------------
    (
        "M-SPLIT-MISSING-ON-GUARD-PATH",
        TASK,
        "the partial_budget_guard return is the path that has fired on EVERY recent run",
        "            # LAT-P154: which of score_resolution's six resolvers spent the\n            # phase's seconds — the question the flat 397.0 s could not answer.\n            \"score_resolution_sub_s\": dict(_score_sub),\n",
        "",
    ),
    (
        "M-SUB-TIMER-NOT-IN-FINALLY",
        TASK,
        "a resolver that raises is the one whose cost we need, and it goes unrecorded",
        "        _sub_t0 = _t.monotonic()\n        try:\n            return await coro\n        finally:",
        "        _sub_t0 = _t.monotonic()\n        if True:\n            return await coro\n        if False:",
    ),
]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_suite() -> bool:
    """True when the guards PASS (i.e. the mutant survived)."""
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", *PYTEST_ARGS],
        cwd=BACKEND,
        capture_output=True,
        text=True,
        env={**os.environ, "TZ": "UTC"},
    )
    # Gotcha #54: `1` is a result, anything else is a story about the harness.
    if proc.returncode not in (0, 1):
        raise RuntimeError(
            "pytest exited %d — the gate never ran:\n%s\n%s"
            % (proc.returncode, proc.stdout[-3000:], proc.stderr[-2000:])
        )
    return proc.returncode == 0


def which_suite_killed() -> str:
    """Name the suite(s) that failed, so a hole in one is not hidden by another."""
    killers = []
    for arg in PYTEST_ARGS:
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", arg],
            cwd=BACKEND,
            capture_output=True,
            text=True,
            env={**os.environ, "TZ": "UTC"},
        )
        if proc.returncode == 1:
            killers.append(Path(arg).stem.replace("test_", ""))
    return "+".join(killers) if killers else "?"


def main() -> int:
    # Namespaced by worktree — /tmp is shared and a sibling's file must never be
    # restored from this run's backup.
    tag = hashlib.sha256(str(BACKEND).encode()).hexdigest()[:12]
    backups = {t: Path("/tmp/lat_p154_%s_%s.bak" % (tag, t.name)) for t in TARGETS}
    originals = {}
    for t in TARGETS:
        if not t.is_file():
            print("FAIL: missing target %s" % t, file=sys.stderr)
            return 2
        shutil.copy2(t, backups[t])
        originals[t] = sha256(t)

    print("LAT-P154 mutation battery — the phase that spent the whole budget")
    print("target  : %s" % TASK.relative_to(BACKEND))
    print("suites  : %s" % " ".join(PYTEST_ARGS))
    print("mutants : %d\n" % len(MUTANTS))

    killed, survived, broken = 0, [], []
    try:
        if not run_suite():
            print("FAIL: the guards are RED before any mutation was applied.")
            return 2
        print("baseline: guards green on the unmutated tree\n")

        for name, target, why, needle, replacement in MUTANTS:
            source = target.read_text()
            occurrences = source.count(needle)
            if occurrences != 1:
                print("  %-34s HARNESS FAIL — anchor appears %dx, need 1"
                      % (name, occurrences))
                broken.append(name)
                continue

            target.write_text(source.replace(needle, replacement, 1))
            if sha256(target) == originals[target]:
                print("  %-34s HARNESS FAIL — edit did not change the file" % name)
                broken.append(name)
                target.write_text(source)
                continue

            try:
                mutant_survived = run_suite()
                killer = "" if mutant_survived else which_suite_killed()
            finally:
                target.write_text(source)
                if sha256(target) != originals[target]:
                    raise RuntimeError("restore of %s did not match original" % target)

            if mutant_survived:
                print("  %-34s SURVIVED  <-- %s" % (name, why))
                survived.append((name, why))
            else:
                killed += 1
                print("  %-34s killed by %s" % (name, killer))
    finally:
        for t in TARGETS:
            shutil.copy2(backups[t], t)
            if sha256(t) != originals[t]:
                print("FAIL: %s not restored byte-for-byte" % t, file=sys.stderr)
                return 2
            backups[t].unlink(missing_ok=True)

    print("\n%d/%d killed, %d survived, %d harness failures"
          % (killed, len(MUTANTS), len(survived), len(broken)))
    for name, why in survived:
        print("  SURVIVOR %s: %s" % (name, why))
    if broken:
        print("  harness failures make this run inconclusive, not clean.")
    return 0 if (not survived and not broken) else 1


if __name__ == "__main__":
    sys.exit(main())
