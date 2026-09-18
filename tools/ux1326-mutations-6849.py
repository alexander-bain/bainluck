#!/usr/bin/env python3
"""Mutation battery for #6849 — the unfurl pill and the duel pair.

A guard suite that passes proves nothing on its own; what matters is whether it
FAILS when the fix is removed. Each mutant below reverts one decision of the fix
by literal substitution, runs the guard suite, and expects a red. The control
changes a comment only and expects a green — without it, a battery whose runner
is broken reports a perfect score.

    python3 tools/ux1326-mutations-6849.py

Run from the repo root. Restores every file on exit, including on a crash.
"""

import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
FRONTEND = ROOT / "frontend"

SHARE_META = FRONTEND / "lib" / "eventConceptShareMeta.ts"
OG_ROUTE = FRONTEND / "app" / "event" / "[domain]" / "[slug]" / "opengraph-image.tsx"

# (name, file, find, replace, expect_red, what it proves)
MUTANTS = [
    (
        "pill-ignores-the-payload",
        OG_ROUTE,
        "conceptDomainLabel(concept?.event?.sport_label, domain)",
        "conceptDomainLabel(null, domain)",
        True,
        "the fetched sport_label is READ, not merely available — a real UFC "
        "card must not flatten to COMBAT",
    ),
    (
        "pill-back-to-the-url-segment",
        OG_ROUTE,
        "conceptDomainLabel(concept?.event?.sport_label, domain)",
        "domain.toUpperCase()",
        True,
        "the filed defect itself: the namespace naming the sport",
    ),
    (
        "pill-keeps-a-local-map",
        OG_ROUTE,
        "conceptDomainLabel(concept?.event?.sport_label, domain)",
        '(domain === "ufc" ? "UFC" : conceptDomainLabel(concept?.event?.sport_label, domain))',
        True,
        "a second label rule growing back beside the shared one",
    ),
    (
        "pairing-dropped",
        SHARE_META,
        "return competitors.length === 2 ? pairedDuel(priced) : priced;",
        "return priced;",
        True,
        "the 68/33 defect: two sides rounded separately",
    ),
    (
        "pairing-keyed-on-survivors",
        SHARE_META,
        "return competitors.length === 2 ? pairedDuel(priced) : priced;",
        "return pairedDuel(priced);",
        True,
        "the trap the first version fell into — a 4-way field whose two "
        "survivors total 0.99 by coincidence",
    ),
    (
        "pairing-order-flipped",
        SHARE_META,
        "renderedDuelPercents(priced[0].fraction, priced[1].fraction)",
        "renderedDuelPercents(priced[1].fraction, priced[0].fraction)",
        True,
        "the favourite is the side that survives rounding, and the two "
        "percents are not interchangeable",
    ),
    (
        "manufactured-certainty-allowed",
        SHARE_META,
        "  if (first >= 100) return [];\n",
        "",
        True,
        "#6029's rule re-checked on the number pairing produces, not the one "
        "that went in",
    ),
    (
        "CONTROL-comment-only",
        SHARE_META,
        "// TWO-SIDED IS A PROPERTY OF THE CONTEST",
        "// Two-sided is a property of the contest",
        False,
        "the runner reports a green when nothing behaves differently",
    ),
]

SUITE = "unfurlPillAndPair6849|lib/eventConceptShareMeta|eventConceptCertaintyUnfurl6029"


def run_suite() -> int:
    return subprocess.run(
        ["npx", "jest", "--silent", f"--testPathPatterns={SUITE}"],
        cwd=FRONTEND,
        capture_output=True,
        text=True,
    ).returncode


def main() -> int:
    originals = {path: path.read_text() for path in {SHARE_META, OG_ROUTE}}

    baseline = run_suite()
    if baseline != 0:
        print(f"BASELINE IS RED (exit {baseline}) — fix that before reading any mutant")
        return 2
    print("baseline: GREEN\n")

    failures = []
    try:
        for name, path, find, replace, expect_red, why in MUTANTS:
            source = originals[path]
            if source.count(find) != 1:
                failures.append(f"{name}: anchor matched {source.count(find)}x, expected 1")
                print(f"  SKIP  {name}: stale anchor")
                continue
            path.write_text(source.replace(find, replace))
            code = run_suite()
            path.write_text(source)

            died = code != 0
            ok = died == expect_red
            verdict = "KILLED" if died else "SURVIVED"
            print(f"  {'ok  ' if ok else 'FAIL'}  {name}: {verdict} (exit {code}) — {why}")
            if not ok:
                failures.append(f"{name}: expected {'red' if expect_red else 'green'}, got exit {code}")
    finally:
        for path, source in originals.items():
            path.write_text(source)

    print()
    if failures:
        print(f"{len(failures)} PROBLEM(S):")
        for line in failures:
            print(f"  - {line}")
        return 1
    print(f"{len(MUTANTS)}/{len(MUTANTS)} behaved as expected.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
