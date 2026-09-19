#!/usr/bin/env python3
"""Mutation battery for #7064 — does the guard suite actually bite?

Each mutant is a single, plausible way the fix could be wrong: a guard dropped, a boolean
loosened, one of the two arrays forgotten, the call site un-wired. A SURVIVOR is a mutant the
suite let through, and it names a hole in the tests, not a nit.

Rig rules this obeys (they are house rules because each was paid for once):
  * the tree must be COMMITTED and clean before we start — the restore is `git checkout` of the
    committed blob, so an uncommitted edit here would be destroyed;
  * every mutant asserts its anchor appears EXACTLY ONCE. An anchor that matches zero times, or
    twice, means the patch did not land where it was aimed and the run measured nothing — that is
    reported as ANCHOR NOT FOUND, never quietly counted as a kill;
  * applied/restored is printed for every mutant so a crash mid-run leaves a readable trail.
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"
LIB = FRONTEND / "lib" / "eventOwnMoneyline.ts"
PAGE = FRONTEND / "app" / "events" / "[id]" / "page.tsx"
TEST = "eventOwnMoneylineNotAProp7064"

# (label, file, anchor, replacement)
MUTANTS = [
    (
        "fold stops lowercasing — a venue's capitalisation defeats the match",
        LIB,
        "    .toLowerCase()\n    .replace(/[.,]/g, \" \")",
        '    .replace(/[.,]/g, " ")',
    ),
    (
        "props_script matched on the WHOLE key instead of its family",
        LIB,
        "        const family = propFamilyName(mark?.key);\n        return family === null || !isOwn(family);",
        "        return !isOwn(String(mark?.key));",
    ),
    (
        "both-sides AND loosened to OR — one matching side is enough",
        LIB,
        "(labelNamesSide(first, awayTeam) && labelNamesSide(second, homeTeam)) ||\n    (labelNamesSide(first, homeTeam) && labelNamesSide(second, awayTeam))",
        "(labelNamesSide(first, awayTeam) || labelNamesSide(second, homeTeam)) ||\n    (labelNamesSide(first, homeTeam) || labelNamesSide(second, awayTeam))",
    ),
    (
        "props_script left unfiltered — THE SCRIPT keeps answering the question",
        LIB,
        "        const family = propFamilyName(mark?.key);\n        return family === null || !isOwn(family);",
        "        return true;",
    ),
    (
        "player_props left unfiltered — THE DIVERGENCE keeps the row",
        LIB,
        "  const keptProps = props.filter((row) => !isOwn(row?.market_name));",
        "  const keptProps = props.slice();",
    ),
    (
        "affix test loses its space — a bare prefix names the club",
        LIB,
        't.startsWith(l + " ") || t.endsWith(" " + l)',
        "t.startsWith(l) || t.endsWith(l)",
    ),
    (
        "affix test dropped entirely — only an exact spelling names the club",
        LIB,
        'return l === t || t.startsWith(l + " ") || t.endsWith(" " + l);',
        "return l === t;",
    ),
    (
        "always returns a fresh object — the error boundaries' resetKey churns",
        LIB,
        "  if (propsUnchanged && scriptUnchanged) return payload;",
        "  if (false && propsUnchanged && scriptUnchanged) return payload;",
    ),
    (
        "an unreadable key is treated as the moneyline — deletes the concept page's marks",
        LIB,
        "        return family === null || !isOwn(family);",
        "        return family !== null && !isOwn(family);",
    ),
    (
        "separator narrowed to 'vs' only — 'at' and '@' fixtures stop being caught",
        LIB,
        "const SIDE_SEPARATOR = /^(.+?)\\s+(?:vs\\.?|v\\.?|at|@)\\s+(.+)$/i;",
        "const SIDE_SEPARATOR = /^(.+?)\\s+vs\\s+(.+)$/i;",
    ),
    (
        "both sides compared against the HOME team",
        LIB,
        "    isEventOwnMoneylineMarket(marketName, payload.home_team, payload.away_team);",
        "    isEventOwnMoneylineMarket(marketName, payload.home_team, payload.home_team);",
    ),
    (
        "call site un-wired — the filter exists and nothing runs it",
        PAGE,
        "    () => (servedGameMarkets ? withoutEventOwnMoneyline(servedGameMarkets) : servedGameMarkets),",
        "    () => servedGameMarkets,",
    ),
]


def run(cmd, **kw):
    return subprocess.run(cmd, cwd=FRONTEND, capture_output=True, text=True, **kw)


def restore(path: Path) -> None:
    rel = path.relative_to(ROOT)
    subprocess.run(["git", "checkout", "--", str(rel)], cwd=ROOT, check=True)


def main() -> int:
    dirty = subprocess.run(
        ["git", "status", "--porcelain", "--", "frontend"],
        cwd=ROOT, capture_output=True, text=True,
    ).stdout.strip()
    if dirty:
        print("REFUSING: frontend/ has uncommitted changes; commit first (the restore is a checkout).")
        print(dirty)
        return 2

    baseline = run(["npx", "jest", f"--testPathPatterns={TEST}"])
    if baseline.returncode != 0:
        print("REFUSING: the suite is not green before mutating — nothing below would mean anything.")
        print(baseline.stderr[-2000:])
        return 2
    print("baseline: suite GREEN on the committed tree\n")

    killed, survived, broken = 0, [], []
    for i, (label, path, anchor, repl) in enumerate(MUTANTS, 1):
        src = path.read_text()
        count = src.count(anchor)
        if count != 1:
            print(f"{i:2}. ANCHOR NOT FOUND ({count} matches) — {label}")
            print("    MEASURED NOTHING for this mutant.")
            broken.append(label)
            continue
        path.write_text(src.replace(anchor, repl))
        print(f"{i:2}. applied   — {label}")
        try:
            res = run(["npx", "jest", f"--testPathPatterns={TEST}"])
            if res.returncode != 0:
                killed += 1
                print("    KILLED")
            else:
                survived.append(label)
                print("    🔴 SURVIVED — the suite did not notice")
        finally:
            restore(path)
            print("    restored")

    print(f"\n{killed}/{len(MUTANTS)} killed")
    if broken:
        print(f"{len(broken)} anchor(s) NOT FOUND — those mutants measured nothing:")
        for b in broken:
            print(f"  - {b}")
    if survived:
        print(f"{len(survived)} SURVIVOR(S):")
        for s in survived:
            print(f"  - {s}")
    return 0 if (not survived and not broken) else 1


if __name__ == "__main__":
    sys.exit(main())
