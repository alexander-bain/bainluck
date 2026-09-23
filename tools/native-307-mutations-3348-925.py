#!/usr/bin/env python3
"""native/307 — mutation run for the #3348/#925 corrections package.

FIVE mutants, from two sources:

  * 1-3 are the three NATIVE-RUN.md asked for by name (the delivered
    package's own claims: the tolerant per-element decoder, the admission
    rule, the end-of-own-minute cutoff that replaced the +90s look-ahead).
  * 4-5 are THIS SESSION'S two repairs, which have no value unless a
    revert goes red. Mutant 4 is the delivered code verbatim: it restores
    `espnByTime.last(where:)` and must reproduce the 14 failures measured
    on the pristine tree.

A mutant that SURVIVES is a hole in the guard suite, not a curiosity. A
mutant whose anchor is missing is REFUSED and reported as a non-result —
a patch that changed nothing prints a green indistinguishable from an
unkillable mutant.

TRAP (banked by native/234, inherited here): on a FAILING run xcodebuild
calls `simctl diagnose --timeout=600`, i.e. ~10 minutes per KILLED
mutant. `-collect-test-diagnostics never` is not optional in this script.

Runs only from this lane's own worktree; every path is absolute.

Usage:  python3 tools/native-307-mutations-3348-925.py [--list]
"""
import subprocess, sys, pathlib, signal, atexit

WORKTREE = pathlib.Path("/Users/bain/bainluck-dev/native")
ROOT = WORKTREE / "ios/Bain Luck"
CHART = ROOT / "Bain Luck/Components/OddsChartView.swift"
CARD = ROOT / "Bain Luck/Components/GamePlayCardView.swift"
MODELS = ROOT / "Bain Luck/Models/HistoryModels.swift"
SIM = "D2DA47A0-85F6-4BF8-AEFF-33146AE3EB05"

# ── mutant 4: the delivered package's enrichment loop, verbatim ──────────
CURSOR = """            while espnIdx < espnByTime.count, espnByTime[espnIdx].date < cutoff {
                let row = espnByTime[espnIdx]
                if let hs = row.point.homeScore {
                    lastScore = (hs, row.point.awayScore ?? lastScore?.away ?? 0)
                    // A row that REPEATS the score is still an observation of it.
                    lastScoreObservedAt = row.date
                }
                if let p = row.point.period, !p.isEmpty {
                    lastPeriod = p
                    lastPeriodObservedAt = row.date
                }
                if let c = row.point.gameClock, !c.isEmpty {
                    lastClock = c
                    lastClockObservedAt = row.date
                }
                espnIdx += 1
            }"""

SINGLE_ROW_SAMPLE = """            if let nearest = espnByTime.last(where: { $0.date < cutoff }) {
                if let hs = nearest.point.homeScore {
                    lastScore = (hs, nearest.point.awayScore ?? lastScore?.away ?? 0)
                    lastScoreObservedAt = nearest.date
                }
                if let p = nearest.point.period, !p.isEmpty {
                    lastPeriod = p
                    lastPeriodObservedAt = nearest.date
                }
                if let c = nearest.point.gameClock, !c.isEmpty {
                    lastClock = c
                    lastClockObservedAt = nearest.date
                }
            }"""

# ── mutant 5: the as-of readout before the day-boundary repair ───────────
DATED_AS_OF = """        guard let pointDate, !calendar.isDate(observed, inSameDayAs: pointDate) else {
            return clockText(observed)
        }
        return observed.formatted(.dateTime.month(.abbreviated).day().hour().minute())"""

BARE_CLOCK_ALWAYS = """        return clockText(observed)"""

# ── mutant 1: the decoder before per-element tolerance ──────────────────
INTOLERANT_GUARD = """        guard let c = try? decoder.container(keyedBy: CodingKeys.self) else {
            timestamp = nil
            period = nil
            source = nil
            precision = nil
            notBefore = nil
            return
        }"""

# (name, file, find, replace, why-it-matters)
MUTANTS = [
    ("1-decoder-fails-the-whole-envelope-on-one-bad-element", MODELS,
     INTOLERANT_GUARD, "        let c = try decoder.container(keyedBy: CodingKeys.self)",
     "NATIVE-RUN #1. One scalar or null element in `period_markers` takes the "
     "whole history payload down — the chart loses every marker AND the price "
     "series, which is how a single malformed row blanks a page"),

    ("2-admission-treats-unknown-source-as-observed", CHART,
     "        for marker in served where marker.isObserved {",
     "        for marker in served where !marker.isEstimated {",
     "NATIVE-RUN #2. A marker with NO source is neither observed nor estimated, "
     "but `!isEstimated` admits it — missing evidence read as evidence of "
     "observation, and the phone draws a boundary nobody saw"),

    ("3-cutoff-reinstates-the-90s-lookahead", CHART,
     """        let minute = floor(pointDate.timeIntervalSince1970 / 60) * 60
        return Date(timeIntervalSince1970: minute + 60)""",
     "        return pointDate.addingTimeInterval(90)",
     "NATIVE-RUN #3. A first observation at 20:32:30 stands, unmarked and "
     "exact, on the 20:31:00 price — a state nobody had seen yet, presented as "
     "observed, at a minute the reader can tell apart"),

    ("4-enrichment-samples-one-row-per-point", CHART, CURSOR, SINGLE_ROW_SAMPLE,
     "THE DELIVERED PACKAGE VERBATIM. Every ESPN row falling between two price "
     "points is dropped, so a score-only row (the ordinary MLB shape) leaves "
     "the reader with NO half-inning rather than a dated one. Must reproduce "
     "the 14 failures measured on the pristine tree"),

    ("5-as-of-never-names-the-day", CARD, DATED_AS_OF, BARE_CLOCK_ALWAYS,
     "A state carried across local midnight prints `as of 11:58 PM` directly "
     "beneath a `12:30 AM` point: 32 minutes old, reading as twelve hours in "
     "the future. Codex's CODEX-0007 finding, native side"),
]

XCB = ["xcodebuild", "test",
       "-project", str(ROOT / "Bain Luck.xcodeproj"),
       "-scheme", "Bain Luck",
       "-destination", f"platform=iOS Simulator,id={SIM}",
       "-disableAutomaticPackageResolution",
       "-collect-test-diagnostics", "never",
       "-only-testing:BainLuckTests/ScrubReadoutDatesCarriedState925Tests",
       "-only-testing:BainLuckTests/PeriodMarkerProvenanceReachesThePhone3348Tests",
       "-only-testing:BainLuckTests/AChartMarkerSitsOnAnObservedTime6718Tests",
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
    code, _, out = run_tests()
    if code != 0:
        print(f"  BASELINE IS RED (exit {code}) — fix that before reading any mutant")
        for line in out.splitlines():
            if "Executed" in line:
                print("   ", line.strip())
        return 2
    # xcodebuild prints one `Executed N tests` line PER SUITE and then the
    # total, so the FIRST line is whichever class happens to run first — here
    # the 5-test 6718 class, against a real total of 56. A per-suite count
    # pasted into a PR body reads as the whole gate, so report the largest.
    counts = []
    for ln in out.splitlines():
        w = ln.split()
        if "Executed" not in w:
            continue
        n = w[w.index("Executed") + 1:w.index("Executed") + 2]
        if n and n[0].isdigit():
            counts.append(int(n[0]))
    if counts:
        print(f"    Executed {max(counts)} tests across the named classes, 0 failures")
    print("  baseline GREEN\n")

    killed, survived = [], []
    for name, path, find, repl, why in MUTANTS:
        original = path.read_text()
        # A refused patch prints a green indistinguishable from an unkillable
        # mutant, so refusal is reported as a NON-result, never a pass.
        if find not in original:
            print(f"  REFUSED  {name} — anchor not found in {path.name}; patched NOTHING")
            survived.append((name, "REFUSED"))
            continue
        if original.count(find) != 1:
            print(f"  REFUSED  {name} — anchor occurs {original.count(find)}x in {path.name}, not unique")
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
    print("\ntree on exit (expect CLEAN — every edit is committed):")
    print("  " + (dirty.replace("\n", "\n  ") if dirty else "(clean)"))
    return 0 if not survived else 1


if __name__ == "__main__":
    sys.exit(main())
