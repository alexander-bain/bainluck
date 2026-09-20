#!/usr/bin/env python3
"""native/268 — mutation run for #7512 (an entertainment heading counts its rows).

Six mutants. The two that matter most are not the defect returning — they are the
two ways a "heading == rows" guard stops meaning anything:

  * 3 and 4 restore each CAP on its own, with the heading still reading `shown`.
    That is the shape a later pacing tweak produces, and it is silently correct
    from the label's point of view: the heading follows the array, so if the
    scan does not also refuse the `prefix`, half the defect can come back with
    the tests green. (This is why the fix removes the caps rather than mirroring
    them into the label.)
  * 6 makes `EntertainmentSectionRows.cultural` an identity that TRUNCATES. The
    seam is a one-line function and a one-line function is exactly where a
    "harmless" bound gets added.

Mutant 5 is the tabbed-section control: it flattens Music's whole-theme count
into the swept class. The suite must NOT go green on that just because the two
flat sections are still correct — the file asserts the tabbed sections are
deliberately excluded, and that assertion has to be load-bearing.

A mutant that SURVIVES is a hole in the guard suite, not a curiosity.

Runs only from this lane's own worktree; every path is absolute.

Usage:  python3 tools/native-268c-mutations-7512.py [--list]
"""
import subprocess, sys, pathlib, signal, atexit

WORKTREE = pathlib.Path("/Users/bain/bainluck-dev/native")
ROOT = WORKTREE / "ios/Bain Luck"
VIEW = ROOT / "Bain Luck/Views/EntertainmentView.swift"
SIM = "D2DA47A0-85F6-4BF8-AEFF-33146AE3EB05"

TECH_HEAD_WIRED = '''                SectionTitle(title: "Platform bets & social", count: shown.count)'''
TECH_HEAD_PRE = '''                SectionTitle(title: "Platform bets & social", count: data.count)'''

TECH_GRID_WIRED = '''            if !shown.isEmpty {
                marketGrid(shown)
            }'''
TECH_GRID_CAPPED = '''            if !shown.isEmpty {
                marketGrid(Array(shown.prefix(10)))
            }'''

CULT_HEAD_WIRED = '''                SectionTitle(title: "Pop culture feed", count: shown.count)'''
CULT_HEAD_PRE = '''                SectionTitle(title: "Pop culture feed", count: markets.count)'''

CULT_GRID_WIRED = '''                ForEach(shown) { m in'''
CULT_GRID_CAPPED = '''                ForEach(shown.prefix(12)) { m in'''

MUSIC_TABBED = '''                SectionTitle(title: "Charts, drops & streams", count: data.count)'''
MUSIC_FLATTENED = '''                SectionTitle(title: "Charts, drops & streams", count: 6)'''

SEAM_WIRED = '''    static func cultural(_ markets: [EntMarketRow]) -> [EntMarketRow] {
        markets
    }'''
SEAM_TRUNCATING = '''    static func cultural(_ markets: [EntMarketRow]) -> [EntMarketRow] {
        Array(markets.prefix(12))
    }'''

# (name, file, find, replace, why-it-matters)
MUTANTS = [
    ("1-tech-heading-reads-the-producers-bucket-again", VIEW,
     TECH_HEAD_WIRED, TECH_HEAD_PRE,
     "THE REPORTED DEFECT: 49 printed over the 15 the payload served, over the "
     "10 the grid drew"),

    ("2-cultural-heading-decoupled-from-its-grid", VIEW,
     CULT_HEAD_WIRED, CULT_HEAD_PRE,
     "the second site, which #7512 does not name — the heading reads the input "
     "list while the grid reads the resolved one, so a later cap desynchronises "
     "them again with no edit to the label"),

    ("3-tech-grid-recapped-under-a-correct-heading", VIEW,
     TECH_GRID_WIRED, TECH_GRID_CAPPED,
     "THE HALF-RETURN. The heading follows `shown` and is arithmetically fine; "
     "the grid quietly draws ten of fifteen. Only a scan that refuses the "
     "`prefix` can see this — a label-vs-rows assertion on the seam cannot"),

    ("4-cultural-grid-recapped-under-a-correct-heading", VIEW,
     CULT_GRID_WIRED, CULT_GRID_CAPPED,
     "the same on the feed: 20 counted, 12 drawn, label innocent"),

    ("5-music-count-flattened-into-the-swept-class", VIEW,
     MUSIC_TABBED, MUSIC_FLATTENED,
     "THE EXCLUSION CONTROL. Music and Film/TV are deliberately NOT in this "
     "class — their count names the whole theme beside a visible tab bar. If "
     "that exclusion is not asserted, it is a comment, and the next reader "
     "'fixes' a section that was never broken"),

    ("6-the-seam-itself-truncates", VIEW,
     SEAM_WIRED, SEAM_TRUNCATING,
     "THE SEAM MUTANT. One line, both halves still reading it, heading and grid "
     "in perfect agreement — on twelve of twenty rows. The whole fix is that "
     "these two read one array; nothing about that stops the array being short"),
]

# TRAP (banked by native/234): on a FAILING test run xcodebuild runs
# `simctl diagnose --timeout=600`. `-collect-test-diagnostics never` is the fix.
XCB = ["xcodebuild", "test",
       "-project", str(ROOT / "Bain Luck.xcodeproj"),
       "-scheme", "Bain Luck",
       "-destination", f"platform=iOS Simulator,id={SIM}",
       "-collect-test-diagnostics", "never",
       "-only-testing:BainLuckTests/EntertainmentSectionCountsMatchTheirRows7512Tests",
       "OTHER_SWIFT_FLAGS=$(inherited) -Xfrontend -disable-sandbox"]


def run_tests():
    r = subprocess.run(XCB, capture_output=True, text=True, cwd=str(ROOT))
    out = r.stdout + r.stderr
    return r.returncode, ("Executed" in out), out


_IN_FLIGHT = {}


def _restore_all(*_):
    for path, original in list(_IN_FLIGHT.items()):
        try:
            path.write_text(original)
            print(f"  restored {path.name} on exit")
        except Exception as e:      # noqa: BLE001 — best effort on the way down
            print(f"  !! COULD NOT RESTORE {path}: {e}\n     git checkout it BY HAND before committing")
        _IN_FLIGHT.pop(path, None)


atexit.register(_restore_all)
for _sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
    signal.signal(_sig, lambda s, f: (_restore_all(), sys.exit(128 + s)))


def main():
    if "--list" in sys.argv:
        for n, f, *_ in MUTANTS:
            print(f"  {n}  ({f.name})")
        return 0

    print("baseline (unmutated tree)")
    code, _, _ = run_tests()
    if code != 0:
        print(f"  BASELINE IS RED (exit {code}) — fix that before reading any mutant")
        return 2
    print("  baseline GREEN\n")

    killed, survived = [], []
    for name, path, find, repl, why in MUTANTS:
        original = path.read_text()
        # A refused patch prints a green indistinguishable from an unkillable
        # mutant, so refusal is reported as a NON-result, never a pass.
        if find not in original:
            print(f"  REFUSED  {name} — anchor not found; the mutant patched NOTHING")
            survived.append((name, "REFUSED"))
            continue
        if original.count(find) != 1:
            print(f"  REFUSED  {name} — anchor occurs {original.count(find)}x, not unique")
            survived.append((name, "REFUSED-AMBIGUOUS"))
            continue
        try:
            _IN_FLIGHT[path] = original
            path.write_text(original.replace(find, repl, 1))
            code, compiled, _ = run_tests()
            if code != 0:
                how = "assertions" if compiled else "COMPILE ONLY"
                print(f"  killed   {name}  [{how}]")
                if not compiled:
                    print("           ^ a compile kill does not prove the suite would catch it")
                killed.append(name)
            else:
                print(f"  SURVIVED {name}\n           {why}")
                survived.append((name, "SURVIVED"))
        finally:
            path.write_text(original)
            _IN_FLIGHT.pop(path, None)

    print(f"\n{len(killed)}/{len(MUTANTS)} killed")
    for n, s in survived:
        print(f"  {s}: {n}")

    dirty = subprocess.run(["git", "-C", str(WORKTREE), "diff", "--stat", "--", "ios/"],
                           capture_output=True, text=True).stdout.strip()
    print("\ntree on exit (expect ONLY this ship's own edits):")
    print("  " + (dirty.replace("\n", "\n  ") if dirty else "(clean)"))
    return 0 if not survived else 1


if __name__ == "__main__":
    sys.exit(main())
