#!/usr/bin/env python3
"""LAT-P134 mutation battery — prove the guards are RED against the defect.

A guard suite that has never been shown failing is a guard suite nobody has
tested. This plants each way LAT-P134 can regress, runs
`tests/test_typeahead_warmer_overwrites_not_deletes.py`, and requires a
non-zero exit for every one. Then it restores the files and verifies the
restore by SHA-256 against the bytes read at the start — a battery that
corrupts the tree it was checking is worse than no battery (gotcha: a mutation
that fails to APPLY reports green).

Exit 0 = every mutant killed AND both files restored byte-identical.
Exit 1 = a mutant SURVIVED, or a restore drifted.
Anything else = the harness failed (gotcha #54); do not read it as a pass.

The mutants pull in BOTH directions on purpose:
  * back toward the DELETE (the defect being removed)
  * onward past it, to a flag that also suppresses the WRITE (the defect that
    replacing a delete with a bypass invites, and the one that would make the
    warmer report success while warming nothing)
"""

from __future__ import annotations

import hashlib
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
WARMER = ROOT / "app" / "tasks" / "typeahead_warmer.py"
ROUTE = ROOT / "app" / "routes" / "events.py"
SUITE = "tests/test_typeahead_warmer_overwrites_not_deletes.py"

# (id, file, find, replace, what it proves)
MUTANTS = [
    (
        "M1-DELETE-RETURNS",
        WARMER,
        "    _force_token = _force_cache_rebuild.set(True)",
        "    _force_token = _force_cache_rebuild.set(True)\n"
        "    __import__('app.tasks.redis_state', fromlist=['x'])"
        ".get_redis_client().delete(_CACHE_KEY_PREFIX + q)",
        "the DELETE comes back alongside the flag",
    ),
    (
        "M2-FLAG-NEVER-SET",
        WARMER,
        "    _force_token = _force_cache_rebuild.set(True)",
        "    _force_token = _force_cache_rebuild.set(False)",
        "the warmer stops forcing the rebuild and is served the stale entry",
    ),
    (
        "M3-NO-RESET",
        WARMER,
        "        _force_cache_rebuild.reset(_force_token)",
        "        pass",
        "the flag leaks past a failed rebuild into the next caller",
    ),
    (
        "M4-NO-WRITE-IS-OK",
        WARMER,
        'return {"q": q, "ok": reason != "no_write", "reason": reason,',
        'return {"q": q, "ok": True, "reason": reason,',
        "a pass that wrote nothing reports itself a success",
    ),
    (
        "M5-TTL-NOT-RECHECKED",
        WARMER,
        "    ttl_after = _cache_ttl_seconds(q)",
        "    ttl_after = 10 ** 9",
        "the write verification is stubbed and can never fail",
    ),
    (
        "M6-UNVERIFIED-IS-A-DEFECT",
        WARMER,
        '        reason = "warmed_unverified"',
        '        reason = "no_write"',
        "an unreadable Redis is laundered into a reported warmer defect",
    ),
    (
        "M7-NO-WRITE-HIDES-IN-COMPLETE",
        WARMER,
        "            if head and not timeouts and not errors and not no_writes",
        "            if head and not timeouts and not errors",
        "a no-write pass hides inside `complete`",
    ),
    (
        "M8-UNVERIFIED-NOT-A-REBUILD",
        WARMER,
        'rebuilt = [r for r in results if r["reason"] in ("warmed", "warmed_unverified")]',
        'rebuilt = [r for r in results if r["reason"] == "warmed"]',
        "a Redis blink reads as `the refresh threshold did not fire`",
    ),
    (
        "M9-ROUTE-IGNORES-THE-FLAG",
        ROUTE,
        "    if not debug_evidence and not debug_timing and not _force_cache_rebuild.get():",
        "    if not debug_evidence and not debug_timing:",
        "the route serves the warmer the entry it came to replace",
    ),
    (
        "M10-FLAG-SUPPRESSES-THE-WRITE",
        ROUTE,
        "    if not _ta_degraded and not debug_evidence and not debug_timing:",
        "    if not _ta_degraded and not debug_evidence and not debug_timing "
        "and not _force_cache_rebuild.get():",
        "🔴 the warmer runs the full query path and warms NOTHING, silently",
    ),
    (
        "M11-ROUTE-SETS-THE-FLAG",
        ROUTE,
        "    _cache_key = f\"bainluck:typeahead:{q.lower().strip()}\"",
        "    _force_cache_rebuild.set(True)\n"
        "    _cache_key = f\"bainluck:typeahead:{q.lower().strip()}\"",
        "the route forces its own misses — every user pays the build",
    ),
    (
        "M12-SKIP-SHAPE-DROPS-THE-KEYS",
        WARMER,
        '            "no_writes": [],\n            "unverified": 0,',
        "",
        "a consumer must branch on `terminal` to know a field exists",
    ),
]


def _sha(p: pathlib.Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main() -> int:
    originals = {p: p.read_text() for p in (WARMER, ROUTE)}
    before = {p: _sha(p) for p in (WARMER, ROUTE)}

    # A battery whose baseline is red proves nothing about its mutants.
    base = subprocess.run(
        [sys.executable, "-m", "pytest", SUITE, "-q"],
        cwd=ROOT, capture_output=True, text=True,
    )
    if base.returncode != 0:
        print("HARNESS FAILURE: the suite is not green before mutation")
        print(base.stdout[-3000:])
        return 2

    killed, survived = [], []
    for mid, path, find, repl, why in MUTANTS:
        src = originals[path]
        if src.count(find) != 1:
            print(f"HARNESS FAILURE: {mid} anchor matched {src.count(find)}x, need exactly 1")
            for p, text in originals.items():
                p.write_text(text)
            return 2
        try:
            path.write_text(src.replace(find, repl, 1))
            r = subprocess.run(
                [sys.executable, "-m", "pytest", SUITE, "-q"],
                cwd=ROOT, capture_output=True, text=True,
            )
            # Only exit 1 is a RESULT. Anything else is a story about the
            # harness (gotcha #124) and must not be counted as a kill.
            if r.returncode == 1:
                killed.append((mid, why))
                print(f"  KILLED   {mid}  — {why}")
            elif r.returncode == 0:
                survived.append((mid, why, "suite stayed green"))
                print(f"  SURVIVED {mid}  — {why}")
            else:
                survived.append((mid, why, f"exit {r.returncode}, not a result"))
                print(f"  HARNESS  {mid}  exit {r.returncode} — counted as SURVIVED")
        finally:
            path.write_text(originals[path])

    after = {p: _sha(p) for p in (WARMER, ROUTE)}
    drifted = [p.name for p in before if before[p] != after[p]]

    print()
    print(f"battery: {len(killed)}/{len(MUTANTS)} killed")
    print(f"restore: {'CLEAN' if not drifted else 'DRIFTED ' + ', '.join(drifted)}")
    for p in before:
        print(f"  {p.name}  sha256 {after[p]}")

    if survived:
        print("\nSURVIVORS — the guard, not the mutant, is what to fix first:")
        for mid, why, how in survived:
            print(f"  {mid}: {why}  [{how}]")
    return 1 if (survived or drifted) else 0


if __name__ == "__main__":
    sys.exit(main())
