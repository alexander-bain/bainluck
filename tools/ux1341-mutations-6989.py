#!/usr/bin/env python3
"""#6989 mutation battery — does the guard suite die on each way the fix could be wrong?

Each mutant is a single textual edit to the shipped source, applied to a copy of
the tree's two changed files, graded by `allOutcomesAllWithheldNoFurniture6989`.
KILLED = the suite goes red. SURVIVED = a hole in the guard, not a win.

The control run (unmutated) must be GREEN, or every "kill" below is the harness
failing rather than the test working (gotcha #124: read the exit code's VALUE).
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "frontend/app/futures/[id]/page.tsx"
LIB = ROOT / "frontend/lib/futuresDetailDisplay.ts"

# (name, file, find, replace)  — `find` must appear exactly once.
MUTANTS = [
    ("rule-always-speaks", LIB,
     "return listedCount === 0 ? NO_PRICED_OUTCOMES_NOTE : null;",
     "return NO_PRICED_OUTCOMES_NOTE;"),
    ("rule-never-speaks", LIB,
     "return listedCount === 0 ? NO_PRICED_OUTCOMES_NOTE : null;",
     "return null;"),
    ("rule-inverted", LIB,
     "return listedCount === 0 ? NO_PRICED_OUTCOMES_NOTE : null;",
     "return listedCount !== 0 ? NO_PRICED_OUTCOMES_NOTE : null;"),
    ("rule-off-by-one", LIB,
     "return listedCount === 0 ? NO_PRICED_OUTCOMES_NOTE : null;",
     "return listedCount <= 1 ? NO_PRICED_OUTCOMES_NOTE : null;"),
    ("string-reworded", LIB,
     '"No current prices for this market."',
     '"No outcomes."'),
    # The plausible-but-wrong predicate the file's own trap comment names.
    ("keyed-on-withheld-count", PAGE,
     "const noPricesNote = noPricedOutcomesNote(pricedOutcomes.length);",
     "const noPricesNote = noPricedOutcomesNote(unpricedOutcomes.length);"),
    ("chips-gate-dropped", PAGE,
     '{!noPricesNote && (\n        <div data-testid="futures-sort-controls"',
     '{true && (\n        <div data-testid="futures-sort-controls"'),
    ("as-of-gate-dropped", PAGE,
     "{!isResolved && marketAsOf && !noPricesNote && (",
     "{!isResolved && marketAsOf && ("),
    ("note-not-rendered", PAGE,
     "{noPricesNote && (\n          <p\n            data-testid=\"futures-no-priced-outcomes\"",
     "{false && (\n          <p\n            data-testid=\"futures-no-priced-outcomes\""),
    # The harm mutant: suppressing one gate too far takes the section with it.
    ("section-suppressed-entirely", PAGE,
     "      {!hasOwnLadder && (\n      <div className=\"bg-surface-card rounded-card shadow-card p-6\">",
     "      {!hasOwnLadder && !noPricesNote && (\n      <div className=\"bg-surface-card rounded-card shadow-card p-6\">"),
    # withhold-never-rewrite: the fold must keep the rows, not drop them.
    ("folded-rows-dropped", PAGE,
     "{unpricedOutcomes.length > 0 && (\n          <details data-testid=\"futures-more-outcomes\"",
     "{false && (\n          <details data-testid=\"futures-more-outcomes\""),
]


def jest() -> bool:
    """True when the suite is GREEN."""
    r = subprocess.run(
        ["npx", "jest", "--testPathPatterns=allOutcomesAllWithheldNoFurniture6989"],
        cwd=ROOT / "frontend", capture_output=True, text=True,
    )
    if r.returncode not in (0, 1):
        sys.exit(f"HARNESS FAILURE: jest exited {r.returncode}\n{r.stderr[-2000:]}")
    return r.returncode == 0


def main() -> int:
    originals = {p: p.read_text() for p in (PAGE, LIB)}

    print("control (unmutated) ...", end=" ", flush=True)
    if not jest():
        sys.exit("CONTROL IS RED — every result below would be meaningless.")
    print("GREEN")

    survivors = []
    try:
        for name, path, find, repl in MUTANTS:
            src = originals[path]
            n = src.count(find)
            if n != 1:
                sys.exit(f"{name}: anchor appears {n} times, expected 1")
            path.write_text(src.replace(find, repl))
            green = jest()
            path.write_text(src)
            verdict = "SURVIVED" if green else "killed"
            if green:
                survivors.append(name)
            print(f"  {verdict:9} {name}")
    finally:
        for p, s in originals.items():
            p.write_text(s)

    print(f"\n{len(MUTANTS) - len(survivors)}/{len(MUTANTS)} killed")
    if survivors:
        print("SURVIVORS (holes in the guard):", ", ".join(survivors))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
