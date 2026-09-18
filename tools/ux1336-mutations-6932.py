#!/usr/bin/env python3
"""Mutation battery for #6932's guard — politicsHeroActionsWrap6932.test.ts.

A guard that only ever runs against the fixed tree proves nothing: it may be
restating the diff. This reintroduces the defect, and each WRONG FIX near it, and
requires the guard to go red for each.

WHY IT REPORTS THE KILLING CLAUSE, NOT JUST A COUNT. Three different mutants can
each read "1 failed, 3 passed" while dying on entirely different assertions — a
count alone calls them one signature and overstates the guard's reach. So every
mutant records the NAMES of the tests that failed it, and the summary reports how
many DISTINCT clause-sets the battery exercised. (Learned the hard way on #6853.)

🪤 COMMIT FIRST. The battery refuses a dirty tree, because a `git checkout` to
restore a mutant would delete uncommitted work along with it.

🪤 EVERY MUTANT ASSERTS ITS ANCHOR MATCHES EXACTLY ONCE. A mutant whose anchor
drifted silently patches nothing, the guard stays green, and the battery reports
a SURVIVOR that is really a broken mutant. Anchor count != 1 is a hard error.

Usage: python3 tools/ux1336-mutations-6932.py
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
CSS = ROOT / "frontend/app/politics/politics.module.css"
PAGE = ROOT / "frontend/app/politics/page.tsx"
PATTERN = "politicsHeroActionsWrap6932"

MOBILE = "@media (max-width: 720px)"


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
    """(green, [full names of failing tests]).

    🪤 `--verbose` DOES NOT PRINT PER-TEST LINES under this repo's reporter — it
    emits the summary block and nothing else. Scraping `✕` off it returns an empty
    list for every mutant, every clause-set is then identical, and the battery
    reports "1 distinct clause-set" for a guard that is actually killing on five.
    An empty scrape reads as agreement. So the names come from `--json`, which is
    a contract rather than a rendering, and an unparseable result is a rig error.
    """
    report = Path(tempfile.gettempdir()) / "ux1336-guard.json"
    report.unlink(missing_ok=True)
    p = subprocess.run(
        ["npx", "jest", f"--testPathPatterns={PATTERN}", "--json", f"--outputFile={report}"],
        cwd=ROOT / "frontend", capture_output=True, text=True,
    )
    if not report.exists():
        die(f"jest wrote no JSON report (exit {p.returncode}). The guard did not run:\n"
            f"{(p.stdout + p.stderr)[-2000:]}")
    data = json.loads(report.read_text())
    suites = data.get("testResults") or []
    if not suites:
        die("jest matched NO suite for the guard — a battery that runs no tests kills nothing.")
    if any(s.get("message") and not s.get("assertionResults") for s in suites):
        # A suite that cannot even load is not a kill: the guard never ran.
        return False, ["<SUITE FAILED TO RUN — rig error, not a kill>"]
    failing = [
        a["fullName"]
        for s in suites
        for a in s.get("assertionResults", [])
        if a.get("status") == "failed"
    ]
    green = p.returncode == 0 and not failing
    if not green and not failing:
        die(f"jest exited {p.returncode} with no failing assertion — unexplained, not a kill.")
    return green, failing


def mobile_span(text: str) -> tuple[int, int]:
    start = text.index(MOBILE)
    return start, len(text)


# ── the mutants ─────────────────────────────────────────────────────────────
# Each: (name, file, why it matters, transform). A transform returns the mutated
# text and asserts its own anchor count internally via `sub_once`.

def sub_once(text: str, pattern: str, repl: str, *, name: str, where: tuple[int, int] | None = None) -> str:
    lo, hi = where or (0, len(text))
    region = text[lo:hi]
    n = len(re.findall(pattern, region))
    if n != 1:
        die(f"mutant `{name}`: anchor matched {n} times, expected exactly 1. "
            f"The source moved — re-point the mutant rather than trusting the result.")
    return text[:lo] + re.sub(pattern, repl, region) + text[hi:]


def m_wrap_removed(css: str, page: str):
    """THE DEFECT ITSELF: the block holds its intrinsic width and leaves the card."""
    return sub_once(css, r"\.presHeroActions \{\n    flex-wrap: wrap;\n  \}", "",
                    name="wrap-removed", where=mobile_span(css)), page


def m_wrap_hoisted_to_desktop(css: str, page: str):
    """A plausible 'tidy-up': move the rule to the base declaration.

    It happens to WORK on a phone (the base rule cascades in), which is exactly
    why it needs pinning — it silently changes the desktop row the first time a
    label grows, and it voids the probe's 1280px control arm."""
    css = sub_once(css, r"  \.presHeroActions \{\n    flex-wrap: wrap;\n  \}\n", "",
                   name="wrap-hoisted(remove)", where=mobile_span(css))
    return sub_once(css, r"(\.presHeroActions \{\n  margin-left: auto;)",
                    r"\1\n  flex-wrap: wrap;", name="wrap-hoisted(add)"), page


def m_head_wrap_removed(css: str, page: str):
    """#4651's half of the pair. Without it the block never gets the full interior."""
    return sub_once(css, r"\.presHeroHead \{\n    flex-wrap: wrap;\n  \}", "",
                    name="head-wrap-removed", where=mobile_span(css)), page


def m_wrap_pushed_to_leaf(css: str, page: str):
    """THE WRONG FIX. Fits the row by fragmenting the segmented control —
    `Polymarket` on a second line inside the grey pill."""
    return sub_once(css, r"(\.sourceToggle \{\n  display: inline-flex;)",
                    r"\1\n  flex-wrap: wrap;", name="wrap-pushed-to-leaf"), page


def m_leaf_stops_being_flex(css: str, page: str):
    """Pins the PREMISE of the nowrap arm: nowrap on a non-flex box is vacuous."""
    return sub_once(css, r"(\.sourceToggle \{\n  )display: inline-flex;",
                    r"\1display: block;", name="leaf-not-flex"), page


def m_control_group_dropped(css: str, page: str):
    """The markup arm: the row loses a control group. A guard that only read the
    stylesheet would sail through this."""
    return css, sub_once(page, r"            <SourceToggle mode=\{sourceMode\} onChange=\{setSourceMode\} />\n",
                         "", name="control-group-dropped")


def m_component_root_renamed(css: str, page: str):
    """The resolution step: <SourceToggle/> no longer renders `s.sourceToggle`.
    The guard must NOTICE rather than quietly hold a class nobody renders."""
    return css, sub_once(page, r"(function SourceToggle\([\s\S]*?return \(\n    <div className=\{s\.)sourceToggle(\}>)",
                         r"\1heroVariantToggle\2", name="component-root-renamed")


def m_control_unrelated_colour(css: str, page: str):
    """THE CONTROL. An unrelated edit in the same file must NOT redden the guard;
    otherwise the kills above say nothing about aim."""
    return sub_once(css, r"(\.presHero \{\n  background: )#fff;", r"\1#fefefe;",
                    name="control-unrelated-colour"), page


MUTANTS = [
    ("wrap-removed", m_wrap_removed, True),
    ("wrap-hoisted-to-desktop", m_wrap_hoisted_to_desktop, True),
    ("head-wrap-removed", m_head_wrap_removed, True),
    ("wrap-pushed-to-leaf", m_wrap_pushed_to_leaf, True),
    ("leaf-not-flex", m_leaf_stops_being_flex, True),
    ("control-group-dropped", m_control_group_dropped, True),
    ("component-root-renamed", m_component_root_renamed, True),
    ("control-unrelated-colour", m_control_unrelated_colour, False),  # must SURVIVE
]

# ── run ─────────────────────────────────────────────────────────────────────

backup = Path(tempfile.mkdtemp(prefix="ux1336-"))
shutil.copy(CSS, backup / "css")
shutil.copy(PAGE, backup / "page")

green, failing = run_guard()
if not green:
    shutil.copy(backup / "css", CSS)
    shutil.copy(backup / "page", PAGE)
    die(f"the guard is RED on the unmutated tree — fix that first: {failing}")
print("baseline: guard GREEN on the unmutated tree\n")

results = []
try:
    for name, fn, must_die in MUTANTS:
        css0, page0 = CSS.read_text(), PAGE.read_text()
        css1, page1 = fn(css0, page0)
        CSS.write_text(css1)
        PAGE.write_text(page1)
        changed = [f for f, a, b in (("css", css0, css1), ("page", page0, page1)) if a != b]
        print(f"applied  {name:26s} ({', '.join(changed)})")

        g, fails = run_guard()
        CSS.write_text(css0)
        PAGE.write_text(page0)
        print(f"restored {name:26s} -> {'SURVIVED' if g else 'killed'}")
        if not g:
            for f in fails:
                print(f"             killed by: {f}")
        results.append((name, must_die, g, tuple(sorted(fails))))
        print()
finally:
    shutil.copy(backup / "css", CSS)
    shutil.copy(backup / "page", PAGE)

print("═" * 78)
bad = []
clause_sets = set()
for name, must_die, survived, fails in results:
    if must_die:
        if survived:
            bad.append(f"SURVIVOR: `{name}` — the guard cannot see this change.")
        else:
            clause_sets.add(fails)
    else:
        if not survived:
            bad.append(f"CONTROL RED: `{name}` is unrelated to the invariant but reddened the guard: {fails}")

killed = sum(1 for n, m, s, f in results if m and not s)
total = sum(1 for n, m, s, f in results if m)
print(f"mutation: {killed}/{total} killed · {len(clause_sets)} DISTINCT clause-sets · "
      f"control {'green (correct)' if not any('CONTROL RED' in b for b in bad) else 'RED'}")
for b in bad:
    print(f"🔴 {b}")
sys.exit(1 if bad else 0)
