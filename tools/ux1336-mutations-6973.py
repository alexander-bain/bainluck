#!/usr/bin/env python3
"""Mutation battery for #6973's guard — relatedFuturesMvpFamilyLabels6973.test.tsx.

The defect was an ORDERING one inside a chain of regex arms, and the harm was
delivered through a SECOND function that used the first's return value as an
identity key. Both are shapes a guard can appear to cover while covering
neither, so the mutants here are aimed at three separate things:

  * the specific arms existing at all      (finalist / championship / finals)
  * their POSITION above the generic arm   (the original bug, exactly)
  * the JOIN — the label being what dedupe keys on

That last one is the mutant worth having. On #6948 I mutated two fully-guarded
pure functions, found 10/10 killed, and the page was still wrong because nothing
tested the line that joined them. `dedupe-ignores-label` is that line here.

WHY IT REPORTS THE KILLING CLAUSE. Several mutants can read "1 failed" while
dying on different assertions; a count alone calls them one signature. Names
come from jest's `--json`, never from scraping the reporter — `--verbose` prints
no per-test lines here, and an empty scrape reads as agreement.

🪤 COMMIT FIRST: the battery refuses a dirty tree.
🪤 EVERY MUTANT ASSERTS ITS ANCHOR MATCHES EXACTLY ONCE, or it is a rig error —
   a drifted anchor patches nothing and reports a SURVIVOR that is really a
   broken mutant.

Usage: python3 tools/ux1336-mutations-6973.py
exit 0 = every mutant killed and the control stayed green · 1 = a survivor · 2 = rig error
"""
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "frontend/components/RelatedFutures.tsx"
PATTERN = "relatedFuturesMvpFamilyLabels6973"

FINALIST = '  if (/\\bfinalists?\\b/i.test(cleaned) && /\\bmvp\\b|most\\s+valuable/i.test(cleaned)) return "MVP Finalist";\n'
FINALS = '  if (/\\bfinals\\s+mvp\\b/i.test(cleaned)) return "Finals MVP";\n'
CHAMPIONSHIP = '  if (/\\b(?:championship|super\\s*bowl|world\\s+series|grand\\s+final)\\b[^.]*?\\bmvp\\b/i.test(cleaned)) return "Championship MVP";\n'
GENERIC = '  if (/\\bmvp\\b|most\\s+valuable/i.test(cleaned)) return "MVP";\n'


def die(msg: str) -> None:
    print(f"🔴 RIG: {msg}")
    sys.exit(2)


dirty = subprocess.run(
    ["git", "-C", str(ROOT), "status", "--porcelain", "--untracked-files=no"],
    capture_output=True, text=True,
).stdout.strip()
if dirty:
    die("the tree is dirty — commit first, or a restore will discard your work:\n" + dirty)


def run_guard() -> tuple[bool, list[str]]:
    report = Path(tempfile.gettempdir()) / "ux1336-guard-6973.json"
    report.unlink(missing_ok=True)
    p = subprocess.run(
        ["npx", "jest", f"--testPathPatterns={PATTERN}", "--json", f"--outputFile={report}"],
        cwd=ROOT / "frontend", capture_output=True, text=True,
    )
    if not report.exists():
        die(f"jest wrote no JSON report (exit {p.returncode}); the guard did not run:\n"
            f"{(p.stdout + p.stderr)[-2000:]}")
    data = json.loads(report.read_text())
    suites = data.get("testResults") or []
    if not suites:
        die("jest matched NO suite — a battery that runs no tests kills nothing.")
    if any(s.get("message") and not s.get("assertionResults") for s in suites):
        return False, ["<SUITE FAILED TO RUN — rig error, not a kill>"]
    failing = [
        a["fullName"] for s in suites for a in s.get("assertionResults", [])
        if a.get("status") == "failed"
    ]
    green = p.returncode == 0 and not failing
    if not green and not failing:
        die(f"jest exited {p.returncode} with no failing assertion — unexplained, not a kill.")
    return green, failing


def replace_once(text: str, needle: str, repl: str, *, name: str) -> str:
    n = text.count(needle)
    if n != 1:
        die(f"mutant `{name}`: anchor found {n} times, expected exactly 1. The source moved — "
            f"re-point the mutant rather than trusting the result.")
    return text.replace(needle, repl)


def m_finalist_arm_removed(src: str):
    """THE DEFECT ITSELF: "MVP Finalists" falls through to the generic arm."""
    return replace_once(src, FINALIST, "", name="finalist-arm-removed")


def m_arms_below_generic(src: str):
    """THE ORIGINAL BUG SHAPE, exactly: the three specific arms still EXIST but
    sit below the generic one, so none of them can ever fire. A guard that only
    checked the arms were present would sail straight through this."""
    src = replace_once(src, FINALIST + FINALS + CHAMPIONSHIP + GENERIC,
                       GENERIC + FINALIST + FINALS + CHAMPIONSHIP,
                       name="arms-below-generic")
    return src


def m_finalist_label_collides(src: str):
    """A rename that re-collides the key while looking like the fix is present."""
    return replace_once(src, FINALIST, FINALIST.replace('"MVP Finalist"', '"MVP"'),
                        name="finalist-label-collides")


def m_championship_arm_removed(src: str):
    """The arm with no live population — guarded here precisely because nothing
    on production would report its loss."""
    return replace_once(src, CHAMPIONSHIP, "", name="championship-arm-removed")


def m_finals_arm_removed(src: str):
    """The arm that WAS dead code before this ship. Removing it must not be silent."""
    return replace_once(src, FINALS, "", name="finals-arm-removed")


def m_dedupe_ignores_label(src: str):
    """THE JOIN. The label stops being part of the dedupe identity, so every award
    for one player merges into a single chip and the highest price wins again —
    the harm, reached without touching the label function at all. This is the
    mutant #6948 taught me to write."""
    return replace_once(
        src,
        'const awardKey = (f.merge_group || shortAwardLabel(f.market_name, f.clean_label)).toLowerCase();',
        'const awardKey = (f.merge_group || "award").toLowerCase();',
        name="dedupe-ignores-label",
    )


def m_control_unrelated_label(src: str):
    """THE CONTROL. An unrelated arm of the same function must NOT redden the
    guard; otherwise the kills above say nothing about aim."""
    return replace_once(src, 'if (/\\bheisman/i.test(cleaned)) return "Heisman";',
                        'if (/\\bheisman/i.test(cleaned)) return "Heisman Trophy";',
                        name="control-unrelated-label")


MUTANTS = [
    ("finalist-arm-removed", m_finalist_arm_removed, True),
    ("arms-below-generic", m_arms_below_generic, True),
    ("finalist-label-collides", m_finalist_label_collides, True),
    ("championship-arm-removed", m_championship_arm_removed, True),
    ("finals-arm-removed", m_finals_arm_removed, True),
    ("dedupe-ignores-label", m_dedupe_ignores_label, True),
    ("control-unrelated-label", m_control_unrelated_label, False),  # must SURVIVE
]

backup = Path(tempfile.mkdtemp(prefix="ux1336-6973-")) / "src"
shutil.copy(SRC, backup)

green, failing = run_guard()
if not green:
    shutil.copy(backup, SRC)
    die(f"the guard is RED on the unmutated tree — fix that first: {failing}")
print("baseline: guard GREEN on the unmutated tree\n")

results = []
try:
    for name, fn, must_die in MUTANTS:
        src0 = SRC.read_text()
        SRC.write_text(fn(src0))
        print(f"applied  {name}")
        g, fails = run_guard()
        SRC.write_text(src0)
        print(f"restored {name} -> {'SURVIVED' if g else 'killed'}")
        for f in fails:
            print(f"             killed by: {f}")
        results.append((name, must_die, g, tuple(sorted(fails))))
        print()
finally:
    shutil.copy(backup, SRC)

print("═" * 78)
bad = []
clause_sets = set()
for name, must_die, survived, fails in results:
    if must_die:
        if survived:
            bad.append(f"SURVIVOR: `{name}` — the guard cannot see this change.")
        else:
            clause_sets.add(fails)
    elif not survived:
        bad.append(f"CONTROL RED: `{name}` is unrelated to the invariant but reddened the guard: {fails}")

killed = sum(1 for n, m, s, f in results if m and not s)
total = sum(1 for n, m, s, f in results if m)
print(f"mutation: {killed}/{total} killed · {len(clause_sets)} DISTINCT clause-sets · "
      f"control {'green (correct)' if not any('CONTROL RED' in b for b in bad) else 'RED'}")
for b in bad:
    print(f"🔴 {b}")
sys.exit(1 if bad else 0)
