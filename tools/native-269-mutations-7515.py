#!/usr/bin/env python3
"""native/269 — mutation run for #7515 (the category bar names its population).

Ten mutants. The defect returning is only one of them; the rest are the ways a
copy guard stops meaning anything:

  * 2 and 3 are the clause STUCK ON and STUCK OFF. Stuck off is the defect for
    the reader who sees a sub-bar row; stuck on is a permanent paragraph about a
    row that is not on screen, which is what standing notice 34 bans. A suite
    that only ever asserts "the clause is there" cannot tell those apart, so
    both directions have to be asserted.
  * 5 and 6 are the bar drifting away from the payload and away from the
    column's own characters. The bar is Redis-tunable (#997), so a literal reads
    correctly today; and a caption saying "1,000" over a column printing "0.7K"
    is the #7515 defect wearing different digits.
  * 8 is the one this ship is most exposed to: the clause keyed on
    `categoryRows` (all 15) instead of `topCategoryRows` (the 10 drawn). It is
    still "derived", still passes any assertion that only looks for the helper
    call, and describes rows the reader cannot see. That is the whole reason the
    scan pins the argument and not just the call.
  * 10 swaps `contains` for `allSatisfy`. Both read as "is a row below the bar";
    they differ on the empty table and on one sub-bar row among many, which is
    every real case.

A mutant that SURVIVES is a hole in the guard suite, not a curiosity.

Runs only from this lane's own worktree; every path is absolute.

Usage:  python3 tools/native-269-mutations-7515.py [--list]
"""
import subprocess, sys, pathlib, signal, atexit

WORKTREE = pathlib.Path("/Users/bain/bainluck-dev/native")
ROOT = WORKTREE / "ios/Bain Luck"
LIB = ROOT / "Bain Luck/Utilities/CalibrationPopulation.swift"
VIEW = ROOT / "Bain Luck/Views/CalibrationView.swift"
GUARD = WORKTREE / "tools/reserved-sim-guard.sh"


def disposable_sim():
    """A device this run may install to, from the rig's shared picker.

    🪤 NOT A HARD-CODED UDID. Two simulators hold Alex's signed-in account and
    both are named `iPhone 17`, so a destination written by NAME resolves to one
    of them — which is what this script did on its first run (76D961F0, twelve
    install-and-launch cycles; the data container and keychain survived, but
    that was luck, not design). `tools/reserved-sim-guard.sh` is the authority
    on which devices are protected, and asking it is the only spelling that
    stays correct when the list changes.
    """
    pick = subprocess.run(["bash", "-c", f'. "{GUARD}" && bl_default_shoot_sim'],
                          capture_output=True, text=True)
    udid = (pick.stdout or "").strip().splitlines()
    udid = udid[-1].strip() if udid else ""
    if not udid:
        sys.exit("FATAL: no disposable iPhone simulator on this machine")
    # Belt and braces: the picker is also the thing that got this wrong once.
    check = subprocess.run(["bash", "-c", f'. "{GUARD}" && bl_is_reserved_sim "{udid}"'])
    if check.returncode == 0:
        sys.exit(f"FATAL: the picker returned RESERVED device {udid} — refusing to install")
    return udid


SIM = disposable_sim()

UNITS_WIRED = '''            + "That bar counts every resolved outcome, traded or not"
            + (anyBelowBar
               ? ", so a row here can show fewer than \\(label) in the Outcomes column."
               : ".")'''
UNITS_DELETED = '''            + ""'''
UNITS_STUCK_ON = '''            + "That bar counts every resolved outcome, traded or not"
            + ", so a row here can show fewer than \\(label) in the Outcomes column."'''
UNITS_SECOND_SPELLING = '''            + "That bar counts every resolved outcome, traded or not"
            + (anyBelowBar
               ? ", so a row here can show fewer than \\(bar) in the Outcomes column."
               : ".")'''

CAPTION_WIRED = '''        return "Raw leagues are rolled up into product-level categories, sorted by ECE. "
            + "Categories below \\(label) resolved outcomes are held out — see below. "'''
CAPTION_HARDCODED_BAR = '''        return "Raw leagues are rolled up into product-level categories, sorted by ECE. "
            + "Categories below 1.0K resolved outcomes are held out — see below. "'''

PRED_WIRED = '''        let anyBelowBar = renderedRowOutcomes.contains { $0 < bar }'''
PRED_STUCK_OFF = '''        let anyBelowBar = false'''
PRED_BOUNDARY = '''        let anyBelowBar = renderedRowOutcomes.contains { $0 <= bar }'''
PRED_ALLSATISFY = '''        let anyBelowBar = renderedRowOutcomes.allSatisfy { $0 < bar }'''

VIEW_WIRED = '''                    sub: CalibrationPopulation.categoryTableNote(
                        bar: viewModel.minCategoryOutcomes,
                        renderedRowOutcomes: viewModel.topCategoryRows.map(\\.n))) {'''
VIEW_PRE_7515 = '''                    sub: "Raw leagues are rolled up into product-level categories, sorted by ECE. Categories below \\(fmtN(viewModel.minCategoryOutcomes)) resolved outcomes are held out — see below.") {'''
VIEW_WRONG_ARRAY = '''                    sub: CalibrationPopulation.categoryTableNote(
                        bar: viewModel.minCategoryOutcomes,
                        renderedRowOutcomes: viewModel.categoryRows.map(\\.n))) {'''

FMT_WIRED = '''    private func fmtN(_ n: Int) -> String {
        CalibrationPopulation.compactCount(n)
    }'''
FMT_SECOND_COPY = '''    private func fmtN(_ n: Int) -> String {
        n >= 1000 ? String(format: "%.1fK", Double(n) / 1000) : "\\(n)"
    }'''

# (name, file, find, replace, why-it-matters)
MUTANTS = [
    ("1-the-bar-stops-naming-its-population", LIB,
     UNITS_WIRED, UNITS_DELETED,
     "THE REPORTED DEFECT. The caption states a 1.0K bar over a column counted "
     "on a different population and names neither"),

    ("2-the-consequence-clause-is-stuck-on", LIB,
     UNITS_WIRED, UNITS_STUCK_ON,
     "a permanent paragraph explaining a row that is not on screen — notice 34. "
     "A suite that only ever asserts the clause is PRESENT cannot see this"),

    ("3-the-consequence-clause-is-stuck-off", LIB,
     PRED_WIRED, PRED_STUCK_OFF,
     "the reader who spots a 732 under a 1.0K bar gets no answer. This is the "
     "half of the defect that survives adding the units clause alone"),

    ("4-the-boundary-moves-onto-the-bar", LIB,
     PRED_WIRED, PRED_BOUNDARY,
     "a row sitting exactly ON the bar is published, so warning that rows can "
     "be BELOW the bar because of it is a claim about nothing"),

    ("5-the-stated-bar-is-hard-coded", LIB,
     CAPTION_WIRED, CAPTION_HARDCODED_BAR,
     "`min_category_outcomes` is Redis-tunable (#997). A literal reads correctly "
     "today and lies the first time the threshold moves — silently, because the "
     "column keeps following the payload"),

    ("6-the-two-mentions-of-the-bar-disagree", LIB,
     UNITS_WIRED, UNITS_SECOND_SPELLING,
     "the rule says 1.0K and its consequence says 1000, over a column printing "
     "1.0K. The reader is handed two numbers and no way to compare them — the "
     "#7515 defect in different digits"),

    ("7-the-view-unwires-and-keeps-the-old-literal", VIEW,
     VIEW_WIRED, VIEW_PRE_7515,
     "the helper is perfect and unreferenced. This is the mutant that proves the "
     "unit cases are not the whole guard"),

    ("8-the-clause-is-keyed-on-rows-the-table-does-not-draw", VIEW,
     VIEW_WIRED, VIEW_WRONG_ARRAY,
     "THE LIVE HAZARD. `categoryRows` is 15 rows, `topCategoryRows` is the 10 "
     "drawn. Still derived, still gated on data, and now describing rows the "
     "reader cannot see — invisible to any assertion that only finds the call"),

    ("9-the-view-keeps-a-second-count-formatter", VIEW,
     FMT_WIRED, FMT_SECOND_COPY,
     "two formatters is how the caption and the column drift apart. It is "
     "byte-identical behaviour TODAY, which is exactly why a scan has to refuse "
     "it rather than a value assertion"),

    ("10-contains-becomes-allsatisfy", LIB,
     PRED_WIRED, PRED_ALLSATISFY,
     "reads as the same question and answers a different one: no warning when "
     "one row of ten is sub-bar, and a warning on an empty table"),
]

# TRAP (banked by native/234): on a FAILING test run xcodebuild runs
# `simctl diagnose --timeout=600`. `-collect-test-diagnostics never` is the fix.
XCB = ["xcodebuild", "test",
       "-project", str(ROOT / "Bain Luck.xcodeproj"),
       "-scheme", "Bain Luck",
       "-destination", f"platform=iOS Simulator,id={SIM}",
       "-collect-test-diagnostics", "never",
       "-only-testing:BainLuckTests/CategoryBarNamesItsPopulation7515Tests",
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
