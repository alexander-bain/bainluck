#!/usr/bin/env python3
"""native/269 — mutation run for #7536 (the "How We Compare" card's five defects).

Twelve mutants. Restoring each of the shipped defects is only half of them; the
rest are the ways this particular guard suite could stop meaning anything:

  * 1-4 are the four defects as they shipped: the 2-5pp range plotted as a solid
    bar at its 3.5 midpoint, the Iowa Electronic Markets row (a vote-SHARE
    error) back beside our calibration error, `eceColor` applied to every
    published figure, and our row's cohort tag dropped.
  * 5 and 6 are the range drawn WRONG rather than not at all — the figure still
    prints "2-5pp" while the ink says something else. A suite that only asserts
    `isRange` cannot tell those from the fix.
  * 7 puts the `per-bucket` qualifier on somebody else's figure, which claims we
    know how they averaged it.
  * 8 removes the clamp. It is byte-identical behaviour on today's payload —
    every figure is under the axis maximum — which is exactly why it needs an
    assertion rather than a render.
  * 9 and 10 are the VIEW ignoring a correct model: the colour ungated, and the
    cohort tag never drawn. No Swift test in this suite can see either (a
    raster measures size, not hue), so they are killed by the jest source scan,
    which is also the only half of this ship CI can reach — CI compiles no
    Swift, and that is how three web repairs drifted past this card.
  * 11 and 12 are #7531, added by native/270 when web's half landed under this
    branch: Metaculus back to the 2.5 midpoint of its published ~2-3pp, and the
    subtler one — a range with the WRONG far end, which prints a range, draws a
    band, satisfies every structural assertion and disagrees with the other
    surface by 1pp.

🪤 MUTANT 3 IS THE ONE TO WATCH, AND IT IS WHY THIS FILE WAS RE-RUN RATHER THAN
TRUSTED. `isGraded` is `isOurs && !isRange`. Before #7531 the card shipped a
published POINT (Metaculus, 2.5) and the shipped list distinguished that rule
from `!isRange`. #7531 made that row a range, leaving one point value on the
card and it is ours — so the mutant that drops the `isOurs` conjunct grades
exactly the same three rows, and every assertion reading only the shipped list
goes quiet. `testAPointBenchmarkThatIsNotOursIsNotGradedHoweverWellItWouldScore`
constructs the specimen the card no longer has. A fix that empties a shipped
list of the case a guard was standing on silently disarms that guard.

A mutant that SURVIVES is a hole in the guard suite, not a curiosity.

Runs only from this lane's own worktree; every path is absolute.

Usage:  python3 tools/native-269-mutations-7536.py [--list]
"""
import subprocess, sys, pathlib, signal, atexit

WORKTREE = pathlib.Path("/Users/bain/bainluck-dev/native")
ROOT = WORKTREE / "ios/Bain Luck"
ROWS = ROOT / "Bain Luck/Utilities/CalibrationBenchmarks.swift"
VIEW = ROOT / "Bain Luck/Views/CalibrationView.swift"
GUARD = WORKTREE / "tools/reserved-sim-guard.sh"


def disposable_sim():
    """A device this run may install to, from the rig's shared picker.

    🪤 NOT A HARD-CODED UDID. Two simulators hold Alex's signed-in account and
    both are named `iPhone 17`, so a destination written by NAME resolves to one
    of them. `tools/reserved-sim-guard.sh` is the authority on which devices are
    protected, and asking it is the only spelling that stays correct when the
    list changes (native/269's own near miss on #7515).
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

# ── the rows ────────────────────────────────────────────────────────────────

ARROW_WIRED = '''            .range("Academic consensus", low: 2, high: 5, detail: "Arrow et al. 2008"),'''
ARROW_MIDPOINT = '''            .point("Academic consensus", 3.5, detail: "Arrow et al. 2008 (2\\u{2013}5pp)"),'''
ARROW_PLUS_IEM = '''            .point("Iowa Electronic Markets", 1.5, detail: "Berg et al. 2008"),
            .range("Academic consensus", low: 2, high: 5, detail: "Arrow et al. 2008"),'''

METACULUS_WIRED = '''            .range("Metaculus", low: 2, high: 3, detail: "Self-reported"),'''
METACULUS_MIDPOINT = '''            .point("Metaculus", 2.5, detail: "Self-reported"),'''
METACULUS_WRONG_END = '''            .range("Metaculus", low: 2, high: 4, detail: "Self-reported"),'''

GRADED_WIRED = '''        var isGraded: Bool { isOurs && !isRange }'''
GRADED_EVERY_ROW = '''        var isGraded: Bool { !isRange }'''

OURS_WIRED = '''            .point("Bain Luck", ourMCE, detail: "\\(ourOutcomes) outcomes",
                   cohortTag: cohort, isOurs: true),'''
OURS_UNTAGGED = '''            .point("Bain Luck", ourMCE, detail: "\\(ourOutcomes) outcomes",
                   cohortTag: nil, isOurs: true),'''

LEADING_WIRED = '''            Self.clamp((rangeLow ?? 0) / axisMaxPP)'''
LEADING_FROM_EDGE = '''            0'''

WIDTH_WIRED = '''                return min(1 - barLeadingFraction, Self.clamp((high - low) / axisMaxPP))'''
WIDTH_TO_HIGH = '''                return min(1 - barLeadingFraction, Self.clamp(high / axisMaxPP))'''

QUALIFIER_WIRED = '''        var figureQualifier: String? { isGraded ? "per-bucket" : nil }'''
QUALIFIER_EVERYWHERE = '''        var figureQualifier: String? { "per-bucket" }'''

CLAMP_WIRED = '''            guard f.isFinite else { return 0 }
            return min(1, max(0, f))'''
CLAMP_REMOVED = '''            guard f.isFinite else { return 0 }
            return f'''

# ── the view ────────────────────────────────────────────────────────────────

COLOUR_WIRED = '''                    .foregroundColor(row.isGraded
                        ? viewModel.eceColor(row.value ?? 0)
                        : Color.secondary)'''
COLOUR_UNGATED = '''                    .foregroundColor(viewModel.eceColor(row.value ?? 0))'''

TAG_WIRED = '''                    if let tag = row.cohortTag {
                        Text(tag).font(.system(size: 10)).foregroundStyle(.secondary)
                    }'''
TAG_NEVER_DRAWN = '''                    EmptyView()'''

# name, file, find, replace, runner, why-a-survivor-matters
MUTANTS = [
    ("1-the-range-goes-back-to-its-midpoint", ROWS, ARROW_WIRED, ARROW_MIDPOINT, "both",
     "THE SHIPPED DEFECT. A solid bar at 3.5 beside a caption reading (2-5pp) — "
     "a number that appears nowhere else on the screen, contradicting its own row"),

    ("2-the-vote-share-row-comes-back", ROWS, ARROW_WIRED, ARROW_PLUS_IEM, "both",
     "#7524. Berg's 1.5pp is an absolute error on predicted vote SHARE drawn on "
     "a calibration-error axis beside ours — the bars read 'we beat IEM by 0.5pp'"),

    ("3-every-published-figure-is-graded-again", ROWS, GRADED_WIRED, GRADED_EVERY_ROW, "swift",
     "#6278 item 2. Our green/blue/orange over somebody else's published number. "
     "Every value is under 4, so the card looks IDENTICAL except that the colour "
     "now means nothing — the reason this shipped three times"),

    ("4-our-row-loses-its-cohort-tag", ROWS, OURS_WIRED, OURS_UNTAGGED, "swift",
     "#6278 item 1. The one row that moves under the reader's hands is the one "
     "row that stops saying so"),

    ("5-the-band-is-drawn-from-the-leading-edge", ROWS, LEADING_WIRED, LEADING_FROM_EDGE, "swift",
     "the figure still prints 2-5pp and the ink says 0-3. A guard that only "
     "asserts `isRange` reads this as fixed"),

    ("6-the-band-ends-at-the-high-value-not-the-span", ROWS, WIDTH_WIRED, WIDTH_TO_HIGH, "swift",
     "the same class one step subtler: right start, wrong length"),

    ("7-per-bucket-is-claimed-for-everyone", ROWS, QUALIFIER_WIRED, QUALIFIER_EVERYWHERE, "swift",
     "#7225's rule inverted: we cannot say how Metaculus averaged its figure, and "
     "labelling it per-bucket asserts we can"),

    ("8-the-axis-clamp-is-removed", ROWS, CLAMP_WIRED, CLAMP_REMOVED, "swift",
     "byte-identical on today's payload and a bar off the end of the card on a "
     "bad one — the mutant that proves the suite tests the rule, not the render"),

    ("9-the-view-ungates-the-colour", VIEW, COLOUR_WIRED, COLOUR_UNGATED, "jest",
     "a correct model and a view that ignores it. No Swift test here can see a "
     "hue; the jest scan is the only guard, and the only one CI runs"),

    ("10-the-view-never-draws-the-cohort-tag", VIEW, TAG_WIRED, TAG_NEVER_DRAWN, "jest",
     "the same hole for item 1: the tag is carried, computed, asserted — and "
     "not on screen"),

    ("11-metaculus-goes-back-to-its-midpoint", ROWS, METACULUS_WIRED, METACULUS_MIDPOINT, "both",
     "#7531, and the state this branch was actually IN when web's half merged "
     "underneath it. 2.5 is the midpoint of the ~2-3pp Metaculus publishes, and "
     "this app has no Further Reading section, so it was sourced nowhere at all"),

    ("12-the-range-has-the-wrong-far-end", ROWS, METACULUS_WIRED, METACULUS_WRONG_END, "both",
     "prints a range, draws a band, is a range, passes every structural "
     "assertion — and says 2-4pp where the source says 2-3. Only a guard that "
     "names the ENDS, and the cross-surface comparison, can see it"),
]

# TRAP (banked by native/234): on a FAILING test run xcodebuild runs
# `simctl diagnose --timeout=600`. `-collect-test-diagnostics never` is the fix.
XCB = ["xcodebuild", "test",
       "-project", str(ROOT / "Bain Luck.xcodeproj"),
       "-scheme", "Bain Luck",
       "-destination", f"platform=iOS Simulator,id={SIM}",
       "-collect-test-diagnostics", "never",
       "-only-testing:BainLuckTests/CalibrationBenchmarkTests",
       "OTHER_SWIFT_FLAGS=$(inherited) -Xfrontend -disable-sandbox"]

JEST = ["npx", "jest", "--testPathPatterns", "calibrationBenchmarkParity7536"]


def run_swift():
    r = subprocess.run(XCB, capture_output=True, text=True, cwd=str(ROOT))
    out = r.stdout + r.stderr
    return r.returncode, ("Executed" in out)


def run_jest():
    r = subprocess.run(JEST, capture_output=True, text=True,
                       cwd=str(WORKTREE / "frontend"))
    out = r.stdout + r.stderr
    # A suite that never ran is not a pass and not a kill — it is a broken rig.
    return r.returncode, ("Tests:" in out)


def run(runner):
    """Returns (red, reached) — `reached` is False when the check never ran at all."""
    if runner == "swift":
        return run_swift()
    if runner == "jest":
        return run_jest()
    swift_code, swift_ran = run_swift()
    jest_code, jest_ran = run_jest()
    return (swift_code or jest_code), (swift_ran and jest_ran)


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
        for n, f, _, _, runner, _ in MUTANTS:
            print(f"  {n}  ({f.name}, {runner})")
        return 0

    print("baseline (unmutated tree)")
    code, reached = run("both")
    if code != 0 or not reached:
        print(f"  BASELINE IS RED (exit {code}) — fix that before reading any mutant")
        return 2
    print("  baseline GREEN\n")

    killed, survived = [], []
    for name, path, find, repl, runner, why in MUTANTS:
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
            code, reached = run(runner)
            if code != 0:
                how = "assertions" if reached else "COMPILE/RIG ONLY"
                print(f"  killed   {name}  [{runner}: {how}]")
                if not reached:
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
