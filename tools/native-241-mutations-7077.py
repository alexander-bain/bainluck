#!/usr/bin/env python3
"""native/241 — mutation run for #7077 (the futures chart's window, axis and word).

The ship has FOUR rules and FOUR call sites, and the two families fail in
different ways, so both are mutated here:

  * RULE mutants (4-13): the planner's domain, the coverage note's threshold and
    its count branch, the vocabulary's default, the span word's boundary, the
    sparse limit. These are what a pure suite is for.
  * CALL-SITE mutants (1-3, 14): the chart reverting to the rule it used to use.
    🔴 THESE ARE THE ONES THAT MATTER. `.chartXAxis` and the chip's label live
    inside SwiftUI builders returning opaque types, so NO behavioural test can
    reach them — a body-level revert leaves a perfect rule suite entirely green.
    That is #4624's shape and `TeamLogoView.initialsFallback`'s shape. They are
    killed here only because
    `AFuturesChartSaysWhatItObserved7077Tests.testTheChartActuallyASKSTheseRules…`
    scans the call site, the way #5949's legend test already does.

A mutant that SURVIVES is a hole in the guard suite, not a curiosity.

Runs only from this lane's own worktree; every path is absolute.

Usage:  python3 tools/native-241-mutations-7077.py [--list]
"""
import subprocess, sys, pathlib, signal, atexit

WORKTREE = pathlib.Path("/Users/bain/bainluck-dev/native")
ROOT = WORKTREE / "ios/Bain Luck"
CHART = ROOT / "Bain Luck/Components/EvolutionChartView.swift"
SIM = "D2DA47A0-85F6-4BF8-AEFF-33146AE3EB05"

PLANNED_AXIS = """            let plan = Self.axisPlan(for: entries.map(\\.date), plotWidth: plotWidth)
            AxisMarks(values: .stride(by: plan.component, count: plan.count)) { value in
                AxisGridLine(stroke: StrokeStyle(lineWidth: 0.15))
                    .foregroundStyle(.secondary.opacity(0.3))
                AxisValueLabel(
                    format: plan.format,
                    anchor: OddsChartView.xAxisLabelAnchor(
                        index: value.index, count: value.count)
                )
                .font(.system(size: 9))
            }"""

# The rule as it stood when Alex photographed it.
CHIP_KEYED_AXIS = """            AxisMarks(values: .automatic(desiredCount: 5)) { _ in
                AxisGridLine(stroke: StrokeStyle(lineWidth: 0.15))
                    .foregroundStyle(.secondary.opacity(0.3))
                AxisValueLabel(
                    format: (selectedRange == .day || selectedRange == .today)
                        ? .dateTime.hour()
                        : selectedRange == .tournament
                            ? .dateTime.weekday(.abbreviated).day()
                            : .dateTime.month(.abbreviated).day()
                )
            }"""

CHART_CHOOSES_WORD = """            seasonWord: EvolutionRangeVocabulary.seasonWord(
                sportCategory: data?.sportCategory,
                hasTournamentDates: hasTournamentDates
            ),"""

# (name, find, replace, why-it-matters)
MUTANTS = [
    ("1-axis-reverts-to-the-chip-keyed-format", PLANNED_AXIS, CHIP_KEYED_AXIS,
     "THE REPORTED DEFECT VERBATIM: `Sep 18 · Sep 18 · Sep 18 · Sep 18 · Sep 18 · Sep…`. "
     "Unreachable by any behavioural assertion — a rule suite alone cannot see it"),

    ("2-chip-reverts-to-the-case-name", "Text(range.label(seasonWord: seasonWord))",
     "Text(range.rawValue)",
     "THE OTHER REPORTED DEFECT: `Season` over The Game Awards and over a Meta AI "
     "question. The vocabulary still computes the right word; nothing prints it"),

    ("3-chart-stops-choosing-the-word", CHART_CHOOSES_WORD,
     "            seasonWord: EvolutionTimeRange.season.rawValue,",
     "the bar's default is taken instead of the market's category — every chip reads "
     "`Season` again, and every vocabulary test still passes"),

    ("4-axis-planned-from-the-REQUESTED-window", "        return OddsChartView.xAxisPlan(for: lo...hi, plotWidth: plotWidth, calendar: calendar)",
     "        return OddsChartView.xAxisPlan(for: hi.addingTimeInterval(-168 * 3600)...hi, plotWidth: plotWidth, calendar: calendar)",
     "the whole bug in one line: plan the week that was ASKED for rather than the day "
     "that was observed"),

    ("5-vocabulary-default-claims-a-season", "            : genericWidestWindow",
     "            : EvolutionTimeRange.season.rawValue",
     "an allowlist MISS storing the specific claim instead of the honest generic — "
     "every sports category still reads correctly, so the diff looks harmless"),

    ("6-vocabulary-ignores-tournament-dates",
     "        if hasTournamentDates { return EvolutionTimeRange.season.rawValue }",
     "        if false { return EvolutionTimeRange.season.rawValue }",
     "golf's `Season` beside `Event` becomes `6M`: over-application, the direction a "
     "one-sided suite never checks"),

    ("7-vocabulary-stops-normalising-the-key",
     '        let key = (sportCategory ?? "").trimmingCharacters(in: .whitespacesAndNewlines).lowercased()',
     '        let key = (sportCategory ?? "")',
     "one capital letter from the server and a real season silently becomes `6M`"),

    ("8-coverage-note-never-fires",
     "        guard covered < Double(requestedHours) * 0.5 else { return nil }",
     "        guard covered < Double(requestedHours) * 0.0 else { return nil }",
     "the caption is wired, computed and never shown — the reader is back to a 7d "
     "chart that cannot say it holds one day"),

    ("9-coverage-note-always-fires",
     "        guard covered < Double(requestedHours) * 0.5 else { return nil }",
     "        guard covered < Double(requestedHours) * 1.0 else { return nil }",
     "diagnostic prose under every chart in the app (notice 34), including the ones "
     "with a full window"),

    ("10-coverage-note-drops-the-count-branch",
     "        if let seen = observationTimes, seen > 0, seen <= 3 {",
     "        if let seen = observationTimes, seen > 0, seen <= 0 {",
     "Meta's TWO prices are described as `Prices only go back 3d`, which implies a "
     "line where there are two dots"),

    ("11-coverage-note-reads-an-absence-as-zero",
     "        guard let covered = coverageHours, covered >= 0, requestedHours > 0 else { return nil }",
     "        let covered = coverageHours ?? 0\n        guard requestedHours > 0 else { return nil }",
     "an older server sends no coverage at all and every chart claims `under an hour` "
     "(gotcha #53: an absence and an instant must not share a shape)"),

    ("12-span-word-boundary-moves", "        if hours < 48 { return \"\\(Int(hours.rounded()))h\" }",
     "        if hours < 24 { return \"\\(Int(hours.rounded()))h\" }",
     "`48h` becomes `2d` — the unit a reader can hold turns into the one they cannot"),

    ("13-sparse-limit-swallows-every-chart",
     "        distinctInstants >= 1 && distinctInstants <= sparseObservationLimit",
     "        distinctInstants >= 1",
     "every dense series gets dotted into texture; the opposite mutant is below"),

    ("14-marks-dropped-from-the-line", "                .symbolSize(showsObservationMarks ? 14 : 0)",
     "                .symbolSize(0)",
     "the rule is perfect and the line draws nothing: Meta's two observations read as "
     "a steady three-day slide again. Another builder-only revert"),

    ("15-sparse-limit-turned-off", "        distinctInstants >= 1 && distinctInstants <= sparseObservationLimit",
     "        false",
     "the honest half deleted while the axis fix stays — the half of the ship a "
     "reviewer looking at the axis would not miss"),
]

# TRAP (banked by native/234): on a FAILING run xcodebuild calls
# `simctl diagnose --timeout=600`, i.e. ~10 minutes per KILLED mutant.
XCB = ["xcodebuild", "test",
       "-project", str(ROOT / "Bain Luck.xcodeproj"),
       "-scheme", "Bain Luck",
       "-destination", f"platform=iOS Simulator,id={SIM}",
       "-disableAutomaticPackageResolution",
       "-collect-test-diagnostics", "never",
       "-only-testing:BainLuckTests/AFuturesChartSaysWhatItObserved7077Tests",
       "-only-testing:BainLuckTests/EvolutionControlBarLayoutTests",
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
        for n, *_ in MUTANTS:
            print(f"  {n}")
        return 0

    print("baseline (unmutated tree)")
    code, _, _ = run_tests()
    if code != 0:
        print(f"  BASELINE IS RED (exit {code}) — fix that before reading any mutant")
        return 2
    print("  baseline GREEN\n")

    killed, survived = [], []
    for name, find, repl, why in MUTANTS:
        original = CHART.read_text()
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
            _IN_FLIGHT[CHART] = original
            CHART.write_text(original.replace(find, repl, 1))
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
            CHART.write_text(original)
            _IN_FLIGHT.pop(CHART, None)

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
