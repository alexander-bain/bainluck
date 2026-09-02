#!/usr/bin/env python3
"""Q050 mutation battery (frontend) — does the duplicate url actually MOVE?

The ship: `/events/15300759` is a `kalshi_ticker` duplicate of `/events/15293804`,
the completed US Open match ESPN had final at 2026-09-01 23:05Z. The API now
answers the first url with the second row, and the page must then move — every
sibling fetch on it (history, game markets, tournament, team progression) is
keyed on the ROUTE's id, so rendering the canonical event in place would put a
FINAL hero above an empty chart and no markets. Half a fix, and a worse-looking
one than the bug.

Two layers are under test and each is useless alone:

* `lib/canonicalEventUrl.ts` — the decision, unit-testable because it is pure.
  It stays green if the page stops calling it.
* `app/events/[id]/page.tsx` — the wiring, covered by a source-shape guard
  because `frontend/jest` is `testEnvironment: node` with no jsdom, so a
  `useEffect` has no render path to assert against.

F1 is the RED-FIRST mutant: the navigation deleted outright, i.e. the state of
this page before Q050. If F1 survives, nothing here ships anything.

Comment-stripping in the source guard is itself under test (F9): the page
carries a comment block naming `router.replace` and `canonicalEventHref`, so a
guard that read raw source would match the explanation and pass over deleted
code.

This harness carries its own residue check because
`backend/scripts/evals/scan_mutation_residue.py` globs `*_mutations.py` under
`backend/scripts/evals/` and does not reach the frontend batteries — the same
note `uxp238_mutation_battery.py` carries.

Run from `frontend/`:  python3 scripts/q050_mutation_battery.py
Exit: 0 = every mutant killed. 1 = at least one survived. Anything else is the
      harness failing, not a verdict (gotcha #54).
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path

LIB = Path("lib/canonicalEventUrl.ts")
PAGE = Path("app/events/[id]/page.tsx")

TARGETS = (LIB, PAGE)

TEST_PATTERN = "canonicalEventUrl|eventPageCorrectsADuplicateUrl"

# (id, file, find, replace, what it models)
MUTANTS: list[tuple[str, Path, str, str, str]] = [
    (
        "F1",
        PAGE,
        """  useEffect(() => {
    if (!canonicalHref) return;
    router.replace(canonicalHref);
  }, [canonicalHref, router]);""",
        """  useEffect(() => {
    if (!canonicalHref) return;
  }, [canonicalHref, router]);""",
        "RED-FIRST: the href is computed and never navigated to — the literal "
        "pre-Q050 page, and the exact shape of a ship that looks done in a diff",
    ),
    (
        "F2",
        PAGE,
        "    router.replace(canonicalHref);",
        "    router.push(canonicalHref);",
        "push instead of replace: the ghost url stays in history, so Back lands "
        "on it and redirects again — a page the reader cannot leave",
    ),
    (
        "F3",
        PAGE,
        """  const canonicalHref = canonicalEventHref(
    eventId,
    canonicalEventId,""",
        """  const canonicalHref = canonicalEventHref(
    canonicalEventId,
    eventId,""",
        "the two ids swapped, which sends every CORRECTLY addressed event page "
        "off to itself",
    ),
    (
        "F4",
        PAGE,
        "  const canonicalEventId = event?.id;",
        "  const canonicalEventId = eventId;",
        "the served id read from the route instead of the payload, so the page "
        "can never learn it is on a duplicate",
    ),
    (
        "F5",
        PAGE,
        "    if (!canonicalHref) return;\n",
        "",
        "the null guard dropped — `router.replace(null)` on every event page "
        "on the site, not just the 505 duplicates",
    ),
    (
        "F6",
        LIB,
        "  if (!servedEventId || servedEventId === requestedEventId) return null;",
        "  if (!servedEventId) return null;",
        "a url that was already right redirects to itself: `router.replace` "
        "with the current href, every render, forever",
    ),
    (
        "F7",
        LIB,
        "  if (!servedEventId || servedEventId === requestedEventId) return null;",
        "  if (servedEventId === requestedEventId) return null;",
        "no payload is read as a duplicate — `/events/undefined` before the "
        "first fetch resolves",
    ),
    (
        "F8",
        LIB,
        '  const suffix = query ? `?${query}` : "";',
        '  const suffix = "";',
        "the query string dropped, so a shared link loses its utm_* attribution "
        "the moment it lands on a duplicate",
    ),
    (
        "F9",
        LIB,
        "  if (!Number.isFinite(requestedEventId)) return null;",
        "  if (false) return null;",
        "a NaN route id (`/events/whatever`) is treated as a duplicate to "
        "redirect rather than a bad url",
    ),
]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_guards() -> int:
    proc = subprocess.run(
        ["npx", "jest", "--testPathPatterns", TEST_PATTERN],
        capture_output=True,
        text=True,
        env={**os.environ, "TZ": "UTC"},
    )
    return proc.returncode


def main() -> int:
    originals = {p: p.read_text() for p in TARGETS}
    original_shas = {p: sha(p) for p in TARGETS}

    print(f"denominator: {len(MUTANTS)} mutants queued against "
          f"{LIB.name} + {PAGE.name}")
    baseline = run_guards()
    if baseline != 0:
        print(f"BASELINE IS NOT GREEN (exit {baseline}) — battery is meaningless")
        return 2
    print("baseline: GREEN\n")

    killed, survived = [], []
    try:
        for mid, path, find, repl, why in MUTANTS:
            src = originals[path]
            if src.count(find) != 1:
                print(
                    f"{mid}: ANCHOR NOT UNIQUE in {path} "
                    f"({src.count(find)} hits) — battery invalid"
                )
                return 2
            mutated = src.replace(find, repl)
            assert mutated != src, f"{mid}: mutation is a no-op"
            path.write_text(mutated)
            # Prove it applied: the file on disk differs, and it differs the way
            # the mutant says. A no-op mutant that "survives" is a broken mutant,
            # not a finding about the guard.
            assert sha(path) != original_shas[path], f"{mid}: file unchanged on disk"
            assert find not in path.read_text(), f"{mid}: original text still present"

            code = run_guards()
            path.write_text(src)
            assert sha(path) == original_shas[path], f"{mid}: restore not byte-identical"

            if code != 0:
                killed.append(mid)
                print(f"{mid}: KILLED (exit {code}) — {why}")
            else:
                survived.append(mid)
                print(f"{mid}: *** SURVIVED *** — {why}")
    finally:
        for path, src in originals.items():
            path.write_text(src)
            assert sha(path) == original_shas[path], f"RESIDUE: {path} not restored"
        print("\nall sources restored, sha256 verified")

    print(f"\n{len(killed)}/{len(MUTANTS)} killed")
    if survived:
        print(f"SURVIVORS: {', '.join(survived)}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
