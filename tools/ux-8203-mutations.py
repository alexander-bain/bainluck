#!/usr/bin/env python3
"""Mutation sweep for #8203 — does the guard suite actually hold the new rules down?

Each mutant is a plausible WRONG version of one rule the fix introduces. A mutant that
survives is a rule with no discriminating specimen: the suite would go on passing if
someone wrote it that way, so it is not guarded (ux/1457 §2 — two of seven survived last
time because every arm happened to agree).

The harness restores the tree in a finally-block on every path, including a crash
mid-loop: a harness that dies holding a mutant makes the bug its own baseline.

Usage: python3 tools/ux-8203-mutations.py
Exit:  0 every mutant killed · 1 one or more survived · 2 the tree was not clean to start
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FRONTEND = ROOT / "frontend"
AP = FRONTEND / "components/event/AdvancementPath.tsx"
RF = FRONTEND / "components/RelatedFutures.tsx"
SUITE = "advancementPathWithheldPriceIsNotZero8203"

# (name, file, find, replace, why this is a wrong version someone could plausibly write)
MUTANTS = [
    (
        "withheld ignores resolved",
        AP,
        "const withheld = p.prob == null && !p.resolved;",
        "const withheld = p.prob == null;",
        "drops the #8067 ordering — a clinch with no price would stop drawing its tick",
    ),
    (
        "withheld never fires",
        AP,
        "const withheld = p.prob == null && !p.resolved;",
        "const withheld = p.prob === undefined && !p.resolved;",
        "the classic null-vs-undefined slip; the wire sends null, so the branch goes dead",
    ),
    (
        "withheld row keeps its bar",
        AP,
        '                <div className="flex-1" />',
        '                <div className="flex-1 h-2 rounded-full bg-surface-border overflow-hidden">'
        '<div className="h-full rounded-full bg-violet-400" style={{ width: "0%" }} /></div>',
        "leaves the zero-width bar behind — the false zero drawn instead of written",
    ),
    (
        "withheld row prints a dash",
        AP,
        "                <div className=\"flex-1\" />",
        "                <div className=\"flex-1\" />\n"
        "                <div className=\"w-28 text-right\">—</div>",
        "reaches for NO_READING, which is what the formatter already did (#8067 forbids it)",
    ),
    (
        "withheld label widens",
        AP,
        '                <div className="text-sm w-36 shrink-0 text-text-secondary">{p.label}</div>\n'
        '                <div className="flex-1" />',
        '                <div className="text-sm flex-1 text-text-secondary">{p.label}</div>',
        "#8067's own classes, which on this rail ripple a mixed ladder out of alignment",
    ),
    (
        "bar width coerces null to zero",
        AP,
        "                  width: `${p.resolved || p.prob == null ? 100 : p.prob * 100}%`,",
        "                  width: `${p.resolved ? 100 : (p.prob ?? 0) * 100}%`,",
        "reintroduces the coercion this fix deletes, in the one place that still sees a null. "
        "EQUIVALENT: the early return leaves only two ways to reach this line and both forms "
        "give 100 on each, so no specimen can tell them apart. Listed to keep that on the "
        "record rather than deleted, which would read as never having been asked.",
    ),
    (
        "caller coerces to zero again",
        RF,
        "        prob: f.probability ?? null,",
        "        prob: f.probability || 0,",
        "the original defect, restored verbatim",
    ),
    (
        "caller uses || null",
        RF,
        "        prob: f.probability ?? null,",
        "        prob: f.probability || null,",
        "looks equivalent and is not: a GENUINE zero is falsy, so a real 0% gets suppressed",
    ),
]


def run_suite() -> int:
    return subprocess.run(
        ["npx", "jest", f"--testPathPatterns={SUITE}"],
        cwd=FRONTEND,
        capture_output=True,
        text=True,
    ).returncode


def main() -> int:
    originals = {p: p.read_text() for p in (AP, RF)}
    try:
        if run_suite() != 0:
            print("BASELINE IS RED — fix the tree before sweeping; a red baseline kills everything")
            return 2
        print("baseline GREEN\n")

        survivors = []
        for name, path, find, repl, why in MUTANTS:
            src = originals[path]
            if src.count(find) != 1:
                print(f"?? {name}: anchor matched {src.count(find)} times, not 1 — SKIPPED (stale anchor)")
                survivors.append((name, "stale anchor"))
                continue
            path.write_text(src.replace(find, repl))
            rc = run_suite()
            path.write_text(src)
            verdict = "KILLED" if rc != 0 else "SURVIVED"
            print(f"{'  ' if rc else '!!'} {verdict}: {name}\n      {why}")
            if rc == 0:
                survivors.append((name, why))

        print()
        killed = len(MUTANTS) - len(survivors)
        print(f"{killed}/{len(MUTANTS)} killed")
        for name, why in survivors:
            print(f"  SURVIVOR: {name} — {why}")
        return 1 if survivors else 0
    finally:
        for path, src in originals.items():
            path.write_text(src)
        print("tree restored")


if __name__ == "__main__":
    sys.exit(main())
