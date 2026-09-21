#!/usr/bin/env python3
"""native/282 — mutation run for #7533 (two undeclared caps on the category table).

The ship DELETES code: `.prefix(15)` from `CalibrationViewModel.categories` and
the whole `topCategoryRows` (`categoryRows.prefix(10)`) property. A deletion is
the hardest kind of fix to guard, because the tree after it contains no trace of
what was removed — every assertion is about a count that is now simply correct,
and a suite full of those passes just as happily on a tree where somebody put
one of the slices back somewhere else.

What this battery adds that the unit tests cannot:

  * THE TWO DEFECTS, SEPARATELY (1, 2). They were different numbers on different
    orderings, and #7302 proves they are removed one at a time: web deleted its
    15 and never had a 10. A suite that only counts rows cannot say WHICH cap
    came back, and a fix that removes one of two caps looks exactly like a fix.

  * THE CALL-SITE / INERT-FIX MUTANTS (3, 4). The view model can be perfect and
    the VIEW can still cap what it draws or describe an array that is not on
    screen. Nothing in the view model's own tests can see that — only the source
    scan can, and these mutants are what prove that scan is load-bearing rather
    than decorative.

  * THE BOUNDARY MUTANT (5). `>= minN` to `> minN` is a one-character edit that
    reads as a tightening and silently unpublishes every category sitting exactly
    ON the bar. The fixture carries a 1,000-outcome category against a 1,000 bar
    for this mutant and no other reason.

  * THE OVER-APPLICATION MUTANT (6). This ship widens what the table draws, so
    its own failure mode is drawing everything. Deleting the bar passes every
    assertion about the eleven categories that were missing.

  * THE COUPLING MUTANT (7). #7533 is what makes #7515's conditional clause fire
    on the default cohort: the sub-bar row it explains only reached the screen
    when these caps went. Nailing that down matters because the clause now looks
    unconditional in production and the branch is one edit from being dead code.

  * THE SELF-GRADING MUTANT (8). `.prefix(15)` and `.prefix(10)` appear in the
    doc comment explaining their own removal as often as they would in restored
    code, so a scan of the raw source is a guard grading its own explanation.
    This one is not hypothetical: it fired on the first run of this ship's gates.

A mutant that SURVIVES is a hole in the guard suite, not a curiosity. A mutant
the battery cannot APPLY is reported REFUSED and never counted as a kill.

Runs only from this lane's own worktree; every path below is absolute.

Usage:  python3 tools/native-282-mutations-7533-category-caps.py [--list]
"""
import subprocess, sys, pathlib, signal, atexit

WORKTREE = pathlib.Path("/Users/bain/bainluck-dev/native")
ROOT = WORKTREE / "ios/Bain Luck"
GUARD = WORKTREE / "tools/reserved-sim-guard.sh"
VM = ROOT / "Bain Luck/ViewModels/CalibrationViewModel.swift"
VIEW = ROOT / "Bain Luck/Views/CalibrationView.swift"
POPULATION = ROOT / "Bain Luck/Utilities/CalibrationPopulation.swift"
TESTS = ROOT / "BainLuckTests/CategoryTableDrawsEveryEligibleCategory7533Tests.swift"


def disposable_sim():
    """A device this run may install to, from the rig's shared picker.

    🪤 NOT A HARD-CODED UDID, AND NOT `name=iPhone 17`. Two simulators hold
    Alex's signed-in account and both carry that name, so a destination written
    by NAME resolves to one of them. `tools/reserved-sim-guard.sh` is the
    authority and asking it is the only spelling that stays correct when the
    list changes.
    """
    pick = subprocess.run(["bash", "-c", f'. "{GUARD}" && bl_default_shoot_sim'],
                          capture_output=True, text=True)
    udid = (pick.stdout or "").strip().splitlines()
    udid = udid[-1].strip() if udid else ""
    if not udid:
        sys.exit("FATAL: no disposable iPhone simulator on this machine")
    check = subprocess.run(["bash", "-c", f'. "{GUARD}" && bl_is_reserved_sim "{udid}"'])
    if check.returncode == 0:
        sys.exit(f"FATAL: the picker returned RESERVED device {udid} — refusing to install")
    return udid


SIM = disposable_sim()

# ── the shipped `categories` chain: the bar, the sort, and nothing else ──────
CHAIN_SHIPPED = """        return catMap
            .filter { $0.value >= minN }
            .sorted { $0.value > $1.value }
            .map { $0.key }"""

CHAIN_OUTCOMES_SLICE_BACK = """        return catMap
            .filter { $0.value >= minN }
            .sorted { $0.value > $1.value }
            .prefix(15)
            .map { $0.key }"""

CHAIN_BAR_GONE = """        return catMap
            .sorted { $0.value > $1.value }
            .map { $0.key }"""

CHAIN_BAR_EXCLUSIVE = """        return catMap
            .filter { $0.value > minN }
            .sorted { $0.value > $1.value }
            .map { $0.key }"""

# ── the view: what it DRAWS and what it DESCRIBES ────────────────────────────
FOREACH_SHIPPED = """                ForEach(Array(viewModel.categoryRows.enumerated()), id: \\.element.id) { idx, row in"""
FOREACH_CAP_BACK = """                ForEach(Array(viewModel.categoryRows.prefix(10).enumerated()), id: \\.element.id) { idx, row in"""

CAPTION_SHIPPED = """                        renderedRowOutcomes: viewModel.categoryRows.map(\\.n))) {"""
CAPTION_DETACHED = """                        renderedRowOutcomes: [])) {"""

# ── #7515's conditional clause, which #7533 is what finally fires ────────────
CLAUSE_LIVE = """        let anyBelowBar = renderedRowOutcomes.contains { $0 < bar }"""
CLAUSE_DEAD = """        let anyBelowBar = false"""

# ── this battery's own reading of the source ─────────────────────────────────
STRIPPER_ON = """        source
            .split(separator: "\\n", omittingEmptySubsequences: false)
            .filter { !$0.trimmingCharacters(in: .whitespaces).hasPrefix("//") }
            .joined(separator: "\\n")"""
STRIPPER_OFF = """        source"""

# (name, file, find, replace, why-it-matters)
MUTANTS = [
    ("1-the-outcomes-slice-is-back", VM, CHAIN_SHIPPED, CHAIN_OUTCOMES_SLICE_BACK,
     "THE REPORTED DEFECT, byte for byte — and the one web already deleted in "
     "#7302. Eleven categories that clear the bar fall between two lists a "
     "reader reads as exhaustive. If this survives, the ship proves nothing"),

    ("2-the-ece-slice-is-back-in-the-view", VIEW, FOREACH_SHIPPED, FOREACH_CAP_BACK,
     "THE SECOND CAP, restored where it does the damage. The view model is "
     "perfect and the table still draws ten — so every assertion on "
     "`vm.categoryRows` stays green. Only the source scan sees this, which is "
     "the whole reason the scan exists"),

    ("3-the-caption-is-detached-from-the-table", VIEW, CAPTION_SHIPPED, CAPTION_DETACHED,
     "THE INERT FIX from the other direction: the rows are right and the "
     "sentence above them now describes nothing. #7515's clause silently stops "
     "firing and the published 732-under-a-1.0K-bar row loses its explanation"),

    ("4-the-bar-becomes-exclusive", VM, CHAIN_SHIPPED, CHAIN_BAR_EXCLUSIVE,
     "THE BOUNDARY, one character. A category sitting exactly ON the bar is "
     "published — the caption says BELOW the bar is held out — and `>` "
     "unpublishes it with nothing on screen to show for it. The fixture's "
     "1,000-outcome category exists for this mutant"),

    ("5-the-bar-stops-filtering", VM, CHAIN_SHIPPED, CHAIN_BAR_GONE,
     "OVER-APPLICATION: this ship widens what the table draws, so its own "
     "failure mode is drawing EVERYTHING. A 400-outcome category is published "
     "as a graded curve, and every assertion about the eleven missing "
     "categories passes while it happens"),

    ("6-7515s-clause-is-hard-wired-off", POPULATION, CLAUSE_LIVE, CLAUSE_DEAD,
     "THE COUPLING. #7533 is what put a sub-bar row on this screen, so #7515's "
     "conditional clause fires on the default cohort for the first time. Hard "
     "-wired off it is invisible — the branch reads as dead code to the next "
     "reader, and the row it explains is back to being unexplained"),

    ("7-the-scan-reads-the-raw-file-again", TESTS, STRIPPER_ON, STRIPPER_OFF,
     "THE SELF-GRADING MUTANT, and it is not hypothetical — it fired on this "
     "ship's first gate run. `.prefix(15)` and `.prefix(10)` appear in the doc "
     "comment explaining their removal, so a raw-file scan reports the "
     "explanation of the fix as the defect"),

    ("8-an-unused-alias-is-added", VM,
     "    var categories: [String] {",
     "    var categoriesUnusedAlias: [String] { categories }\n"
     "    var categories: [String] {",
     "a no-op edit that must NOT be reported as a kill — the battery's own "
     "CONTROL. A run that 'kills' this is failing for a reason unrelated to "
     "the mutant"),
]

# TRAP (banked by native/234): on a FAILING run xcodebuild calls
# `simctl diagnose --timeout=600` — ~10 min per KILLED mutant.
# `-collect-test-diagnostics never` is the fix.
XCB = ["xcodebuild", "test",
       "-project", str(ROOT / "Bain Luck.xcodeproj"),
       "-scheme", "Bain Luck",
       "-destination", f"platform=iOS Simulator,id={SIM}",
       "-collect-test-diagnostics", "never",
       "-disableAutomaticPackageResolution",
       "-only-testing:BainLuckTests/CategoryTableDrawsEveryEligibleCategory7533Tests",
       "-only-testing:BainLuckTests/CategoryBarNamesItsPopulation7515Tests",
       "-only-testing:BainLuckTests/CalibrationSurfaceTests",
       "-only-testing:BainLuckTests/CalibrationRowOrderingTests",
       "-only-testing:BainLuckTests/CalibrationParityTests",
       "OTHER_SWIFT_FLAGS=$(inherited) -Xfrontend -disable-sandbox"]


def run_tests():
    r = subprocess.run(XCB, capture_output=True, text=True, cwd=str(ROOT))
    out = r.stdout + r.stderr
    return r.returncode, ("Executed" in out), out


# TRAP (also banked by native/234): `finally` does not survive SIGTERM.
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

    print(f"simulator {SIM} (disposable, via reserved-sim-guard)")
    print("baseline (unmutated tree)")
    code, _, _ = run_tests()
    if code != 0:
        print(f"  BASELINE IS RED (exit {code}) — fix that before reading any mutant")
        return 2
    print("  baseline GREEN\n")

    killed, survived = [], []
    for name, path, find, repl, why in MUTANTS:
        original = path.read_text()
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
    print("\n  (mutant 8 is the battery's CONTROL: it must SURVIVE. Any other survivor is a hole.)")

    dirty = subprocess.run(["git", "-C", str(WORKTREE), "diff", "--stat", "--", "ios/"],
                           capture_output=True, text=True).stdout.strip()
    print("\ntree on exit (expect ONLY this ship's own edits):")
    print("  " + (dirty.replace("\n", "\n  ") if dirty else "(clean)"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
