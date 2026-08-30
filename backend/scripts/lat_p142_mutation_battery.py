#!/usr/bin/env python3
"""LAT-P142 mutation battery — do the guards hold the search debounce down?

THE DEFECT WAS A KEYSTROKE THAT WAS A DATABASE SCAN.
``CategoryBrowser``'s in-category search box put its raw input value into the
SWR key, so typing "super" issued five requests to ``/api/futures/browse``.
Those requests are not equally priced. ``q`` arrives as an unanchored
``name ILIKE '%q%'`` and the GIN trigram index that serves it needs THREE
characters before it can produce a trigram to look up. Production, 2026-08-30,
``category=politics``, ``EXPLAIN (ANALYZE, BUFFERS)``::

    q='s'     132.8 ms   4,821 shared blocks   Bitmap Heap Scan, no trigram
    q='sup'    16.1 ms      40 shared blocks   BitmapAnd, ix_futures_name_trgm

The first two letters of every search cost ~120x the buffer traffic of the query
that immediately supersedes them, and nobody reads their results.

A debounce has TWO failure directions and only one of them is slow:

* **It stops helping** — the key goes back to the raw value, the debouncer is
  rebuilt every render so nothing coalesces, the delay drops to zero. Costs
  buffer traffic. Invisible to a test that only asks "does the box search?".
* **It stops the box working** — the commit never fires, the input lags the
  keyboard by 200 ms, the mount guard goes and wipes the first page that had
  just loaded, paging resets at the wrong moment. Costs the feature outright.

Both directions are represented below. The wiring mutants are the point of the
file: `searchDebounce.test.ts` proves the primitive coalesces and would stay
green through every one of them, because a debouncer that nothing consults is
still a correct debouncer.

Each mutant asserts its edit CHANGED the file before running anything (a
mutation that fails to apply reports green and proves nothing), refuses a
non-unique anchor rather than editing whichever copy ``str.replace`` reaches
first, and every target is restored from a byte-for-byte backup in a ``finally``
with a SHA-256 compare.

Backups are namespaced by the WORKTREE, not just the filename: /tmp is shared
across worktrees and a battery here must never restore a sibling's file.

Run from ``backend/``:  ``python3 scripts/lat_p142_mutation_battery.py``
"""

import hashlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
FRONTEND = BACKEND.parent / "frontend"

PRIMITIVE = FRONTEND / "lib" / "searchDebounce.ts"
COMPONENT = FRONTEND / "components" / "CategoryBrowser.tsx"
TARGETS = [PRIMITIVE, COMPONENT]

#: Both suites run for every mutant. A mutant killed by neither is a hole; a
#: mutant killed by the wiring suite alone is exactly the case the pure suite
#: cannot see, and vice versa — so the report prints which one caught it.
JEST_PATTERN = "searchDebounce|categoryBrowserDebounceWiring"

# (name, target, why it must die, needle, replacement)
MUTANTS = [
    # -- the wiring: the debouncer exists but nothing consults it -----------
    (
        "M-KEY-USES-RAW-INPUT",
        COMPONENT,
        "SWR keys on the keystroke again — five requests per word, debouncer idle",
        '["futures-browse", category, offset, committedQuery]',
        '["futures-browse", category, offset, searchQuery]',
    ),
    (
        "M-FETCH-SENDS-RAW-INPUT",
        COMPONENT,
        "key is debounced but the request still sends the keystroke value",
        "q: committedQuery || undefined,",
        "q: searchQuery || undefined,",
    ),
    (
        "M-DEBOUNCER-REBUILT-EACH-RENDER",
        COMPONENT,
        "no useRef: every render gets a fresh timer, so nothing ever coalesces",
        "useRef(createSearchDebouncer(SEARCH_DEBOUNCE_MS))",
        "(createSearchDebouncer(SEARCH_DEBOUNCE_MS))",
    ),
    (
        "M-DELAY-ZERO",
        COMPONENT,
        "a 0 ms debounce is not a debounce — every keystroke fires again",
        "export const SEARCH_DEBOUNCE_MS = 200;",
        "export const SEARCH_DEBOUNCE_MS = 0;",
    ),
    # -- the wiring: the box stops working ---------------------------------
    (
        "M-MOUNT-GUARD-DROPPED",
        COMPONENT,
        "on mount both are '' — without the early return the timer wipes page one",
        "if (searchQuery === committedQuery) return;",
        "if (false) return;",
    ),
    (
        "M-NO-CANCEL-ON-TEARDOWN",
        COMPONENT,
        "pending commit outlives the component — a set on an unmounted tree",
        "return () => debouncer.cancel();",
        "return undefined;",
    ),
    (
        "M-INPUT-SHOWS-COMMITTED",
        COMPONENT,
        "debouncing the RENDER, not the request — the box lags the keyboard 200 ms",
        "value={searchQuery}",
        "value={committedQuery}",
    ),
    (
        "M-ONCHANGE-REFETCHES",
        COMPONENT,
        "the keystroke handler resets paging again — skeletons flash on every letter",
        "onChange={(e) => setSearchQuery(e.target.value)}",
        "onChange={(e) => { setSearchQuery(e.target.value); setAllItems([]); }}",
    ),
    (
        "M-PAGING-RESET-DROPPED",
        COMPONENT,
        "a new query keeps the old offset — page 3 of a search that just started",
        "      setOffset(0);\n      setAllItems([]);",
        "      setAllItems([]);",
    ),
    # -- the primitive: coalescing and cancellation -------------------------
    (
        "M-SCHEDULE-DOES-NOT-REPLACE",
        PRIMITIVE,
        "no clear() first: every keystroke keeps its own timer and all of them fire",
        "    schedule(value, commit) {\n      clear();",
        "    schedule(value, commit) {",
    ),
    (
        "M-CANCEL-IS-A-NOOP",
        PRIMITIVE,
        "cancel() stops cancelling — the unmount guard silently does nothing",
        "    cancel: clear,",
        "    cancel: () => {},",
    ),
    (
        "M-CLEAR-LEAVES-TIMER-RUNNING",
        PRIMITIVE,
        "handle dropped without clearTimeout — the superseded query still fires",
        "    if (handle !== null) timers.clearTimeout(handle as never);",
        "    if (false) timers.clearTimeout(handle as never);",
    ),
    (
        "M-PENDING-NEVER-CLEARS",
        PRIMITIVE,
        "pendingValue keeps reporting a commit that already fired",
        "        handle = null;\n        pending = undefined;\n        commit(value);",
        "        handle = null;\n        commit(value);",
    ),
    (
        "M-COMMITS-STALE-PENDING",
        PRIMITIVE,
        "dispatches the bookkeeping slot instead of the captured value",
        "        commit(value);",
        "        commit(pending as string);",
    ),
    (
        "M-IGNORES-INJECTED-TIMERS",
        PRIMITIVE,
        "falls back to globals — every fake-timer guard above measures nothing",
        "      handle = timers.setTimeout(() => {",
        "      handle = (globalThis as never as typeof timers).setTimeout(() => {",
    ),
]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_suite() -> bool:
    """True when the guards PASS (i.e. the mutant survived)."""
    env = {**os.environ, "TZ": "UTC"}
    proc = subprocess.run(
        ["npx", "jest", f"--testPathPatterns={JEST_PATTERN}"],
        cwd=FRONTEND,
        capture_output=True,
        text=True,
        env=env,
    )
    # Gotcha #54: `1` is a result, anything else is a story about the harness.
    if proc.returncode not in (0, 1):
        raise RuntimeError(
            f"jest exited {proc.returncode} — the gate never ran:\n"
            f"{proc.stdout[-2000:]}\n{proc.stderr[-2000:]}"
        )
    return proc.returncode == 0


def which_suite_killed() -> str:
    """Name the suite that failed, so a hole in one is not hidden by the other."""
    env = {**os.environ, "TZ": "UTC"}
    killers = []
    for name, pattern in (("pure", "searchDebounce"), ("wiring", "categoryBrowserDebounceWiring")):
        proc = subprocess.run(
            ["npx", "jest", f"--testPathPatterns={pattern}"],
            cwd=FRONTEND,
            capture_output=True,
            text=True,
            env=env,
        )
        if proc.returncode == 1:
            killers.append(name)
    return "+".join(killers) if killers else "?"


def main() -> int:
    if not FRONTEND.is_dir():
        print(f"FAIL: no frontend at {FRONTEND}", file=sys.stderr)
        return 2

    # Namespaced by worktree — /tmp is shared and a sibling's file must never be
    # restored from this run's backup.
    tag = hashlib.sha256(str(FRONTEND).encode()).hexdigest()[:12]
    backups = {t: Path(f"/tmp/lat_p142_{tag}_{t.name}.bak") for t in TARGETS}
    originals = {}
    for t in TARGETS:
        if not t.is_file():
            print(f"FAIL: missing target {t}", file=sys.stderr)
            return 2
        shutil.copy2(t, backups[t])
        originals[t] = sha256(t)

    print("LAT-P142 mutation battery — the keystroke that was a table scan")
    print(f"targets : {PRIMITIVE.name}, {COMPONENT.name}")
    print(f"suites  : {JEST_PATTERN}")
    print(f"mutants : {len(MUTANTS)}\n")

    killed, survived, broken = 0, [], []
    try:
        # The unmutated tree must be green, or every "killed" below is a lie.
        if not run_suite():
            print("FAIL: the guards are RED before any mutation was applied.")
            return 2
        print("baseline: guards green on the unmutated tree\n")

        for name, target, why, needle, replacement in MUTANTS:
            source = target.read_text()
            occurrences = source.count(needle)
            if occurrences != 1:
                print(f"  {name:<32} HARNESS FAIL — anchor appears {occurrences}x, need 1")
                broken.append(name)
                continue

            target.write_text(source.replace(needle, replacement, 1))
            if sha256(target) == originals[target]:
                print(f"  {name:<32} HARNESS FAIL — edit did not change the file")
                broken.append(name)
                target.write_text(source)
                continue

            try:
                mutant_survived = run_suite()
            finally:
                target.write_text(source)
                if sha256(target) != originals[target]:
                    raise RuntimeError(f"restore of {target} did not match original")

            if mutant_survived:
                print(f"  {name:<32} SURVIVED  <-- {why}")
                survived.append((name, why))
            else:
                killed += 1
                print(f"  {name:<32} killed")
    finally:
        for t in TARGETS:
            shutil.copy2(backups[t], t)
            if sha256(t) != originals[t]:
                print(f"FAIL: {t} not restored byte-for-byte", file=sys.stderr)
                return 2
            backups[t].unlink(missing_ok=True)

    print(f"\n{killed}/{len(MUTANTS)} killed, {len(survived)} survived, {len(broken)} harness failures")
    for name, why in survived:
        print(f"  SURVIVOR {name}: {why}")
    if broken:
        print("  harness failures make this run inconclusive, not clean.")
    return 0 if (not survived and not broken) else 1


if __name__ == "__main__":
    sys.exit(main())
