#!/usr/bin/env python3
"""native/287 — mutation battery for #920 (the phone's frozen match chart).

Harness rules inherited from `native-286-mutations-7722.py`, and they are not
optional:

  * Gate on the EXIT CODE (65 xcodebuild), never on parsed output — gotcha #124:
    only `1` is a result, everything else is a story about the harness.
  * Match `with (\\d+) failures?` — xcodebuild writes "with 1 failure", SINGULAR,
    and a plural-only regex reads a sibling class's "0 failures" and reports a
    killed mutant as SURVIVED.
  * Refuse an anchor that does not match EXACTLY ONCE, which is what catches an
    explaining docstring colliding with the code it describes.

The mutants worth naming:

  * M1 and M2 are the two halves of the defect itself, restored. If anything in
    this battery survives it must not be one of these: M1 puts the pushed frames
    back in the bin, M2 puts the chart back to refusing every fresher payload.
  * M4 is the dangerous one. It widens what counts as "the backend published a
    blend" to any source at all, which MINTS the aggregate series on a payload
    that has none — and because `defaultVisibleSources` returns `["aggregate"]`
    the moment one such point exists, that hides the consensus line the reader
    was reading and draws nothing in its place. A chart that goes blank is a
    worse outcome than the freeze this ship removes, so the refusal that
    prevents it is the single most load-bearing line in the diff.
  * M5 and M6 are the two arms of one compound guard ("refuse a finished payload
    — by status, or by completion"). Implementing or keeping only one arm is a
    capability regression that a single-arm test cannot see, so both are here.
  * M14 mutates the GUARD, not the product, and it is the only mutant in the
    battery that the product cannot notice. It makes the fail-closed fixture
    single-source, so `chartPoints` returns early and the refusal test STILL
    PASSES — for the wrong reason, proving the single-source early return rather
    than the fail-closed guard it is named for. Only the fixture-premise case
    (`testTheFixturesAreAboutWhatTheseTestsClaim`) can catch that. It is here to
    prove that case is load bearing and not decoration.
"""

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EDGE = ROOT / "ios/Bain Luck/Bain Luck/Utilities/LiveChartEdge.swift"
CHART = ROOT / "ios/Bain Luck/Bain Luck/Components/OddsChartView.swift"
VM = ROOT / "ios/Bain Luck/Bain Luck/ViewModels/EventDetailViewModel.swift"
GUARD = ROOT / "ios/Bain Luck/BainLuckTests/LiveChartEdgeTests920.swift"
SIM = "D2DA47A0-85F6-4BF8-AEFF-33146AE3EB05"

MUTANTS = [
    ("M1 the defect restored — pushed frames never reach the chart",
     CHART,
     "return extendingBlendToLiveEdge(points, with: liveFrames, history: history)",
     "return points", "swift"),

    ("M2 the defect restored — the chart refuses every fresher payload",
     EDGE, "        return freshEdge >= currentEdge", "        return false", "swift"),

    ("M3 the adoption stops being monotonic — a slow fetch can step it backwards",
     EDGE, "        return freshEdge >= currentEdge", "        return true", "swift"),

    ("M4 'the backend published a blend' widens to any source — MINTS the blend",
     CHART, '            .filter { $0.source == "aggregate" }\n            .map(\\.date)',
     "            .map(\\.date)", "swift"),

    ("M5 the settled guard loses its completion arm",
     CHART,
     "guard !EventState.isFinished(history.status), history.completedAt == nil else { return points }",
     "guard !EventState.isFinished(history.status) else { return points }", "swift"),

    ("M6 the settled guard loses its status arm",
     CHART,
     "guard !EventState.isFinished(history.status), history.completedAt == nil else { return points }",
     "guard history.completedAt == nil else { return points }", "swift"),

    ("M7 'strictly past the backend's edge' relaxes to 'at or past' — double-draws",
     CHART, "for frame in liveFrames where frame.date > publishedEdge",
     "for frame in liveFrames where frame.date >= publishedEdge", "swift"),

    ("M8 the pushed point starts its own line instead of extending the blend",
     CHART,
     'ChartDataPoint(date: frame.date, probability: frame.homeProbability, source: "aggregate")',
     'ChartDataPoint(date: frame.date, probability: frame.homeProbability, source: "live")',
     "swift"),

    ("M9 the buffer stops dropping a replayed stamp — a reconnect kinks the line",
     EDGE, "if let last = buffer.last, point.date <= last.date { return buffer }",
     "if let last = buffer.last, point.date < last.date { return buffer }", "swift"),

    ("M10 the buffer loses its bound — a page left open grows without limit",
     EDGE, "        if next.count > capacity { next.removeFirst(next.count - capacity) }\n",
     "", "swift"),

    ("M11 freshness stops reading the win-prob series — an advancing line is missed",
     EDGE,
     "        for series in (history.winProbHistory ?? [:]).values {\n"
     "            for point in series { offer(point.timestamp) }\n        }\n",
     "", "swift"),

    ("M12 the producing half is removed — apply stops recording frames at all",
     VM,
     "        if let p = frame.p, let stamped = frame.updatedAt?.asDate {\n"
     "            liveBlend = LiveBlendBuffer.appending(\n"
     "                LiveBlendPoint(date: stamped, homeProbability: p),\n"
     "                to: liveBlend\n            )\n        }\n",
     "", "swift"),

    ("M13 the frame is drawn where it ARRIVED rather than where it was stamped",
     VM, "LiveBlendPoint(date: stamped, homeProbability: p)",
     "LiveBlendPoint(date: Date(), homeProbability: p)", "swift"),

    ("M14 the buffer stops refusing a value that is not a probability",
     EDGE,
     "        guard point.homeProbability.isFinite, (0...1).contains(point.homeProbability) else {\n"
     "            return buffer\n        }\n",
     "", "swift"),

    ("M15 the probability guard over-refuses — a blowout's 0 or 1 is dropped",
     EDGE, "(0...1).contains(point.homeProbability)",
     "(0.01..<1).contains(point.homeProbability)", "swift"),

    ("M16 the GUARD's fail-closed fixture goes single-source (product cannot see it)",
     GUARD,
     '      "win_prob_history": {\n'
     '        "espn": [\n'
     '          {"timestamp": "2026-09-21T12:01:00Z", "home_probability": 0.50},\n'
     '          {"timestamp": "2026-09-21T12:06:00Z", "home_probability": 0.47}\n'
     '        ]\n      }\n',
     '      "win_prob_history": {}\n', "swift"),
]


def run_swift():
    p = subprocess.run(
        ["xcodebuild", "-project", str(ROOT / "ios/Bain Luck/Bain Luck.xcodeproj"),
         "-scheme", "Bain Luck", "-destination", f"id={SIM}",
         "-disableAutomaticPackageResolution",
         "-only-testing:BainLuckTests/LiveChartEdgeTests920",
         "-only-testing:BainLuckTests/LiveBlendCaptureTests920",
         "-only-testing:BainLuckTests/OddsChartPointsTests",
         "OTHER_SWIFT_FLAGS=$(inherited) -Xfrontend -disable-sandbox", "test"],
        capture_output=True, text=True,
    )
    return p.returncode, p.stdout + p.stderr


COUNT = re.compile(r"with (\d+) failures?")


def label(out):
    hits = [int(m) for m in COUNT.findall(out)]
    return f"{sum(hits)} failing assertion group(s)" if hits else "no count line"


def main():
    results = []
    for name, path, find, repl, runner in MUTANTS:
        original = path.read_text()
        if original.count(find) != 1:
            results.append((name, "ERROR", f"anchor matches {original.count(find)}x, want 1"))
            print(f"  {results[-1][1]:9} {name}  ({results[-1][2]})", flush=True)
            continue
        path.write_text(original.replace(find, repl, 1))
        try:
            code, out = run_swift()
        finally:
            path.write_text(original)
        if code == 65:
            verdict, detail = "KILLED", f"exit 65 — {label(out)}"
        elif code == 0:
            verdict, detail = "SURVIVED", "exit 0 — NO TEST NOTICED"
        else:
            verdict, detail = "ERROR", f"exit {code} — harness, not a verdict"
        results.append((name, verdict, detail))
        print(f"  {verdict:9} {name}  ({detail})", flush=True)

    killed = sum(1 for _, v, _ in results if v == "KILLED")
    print(f"\n{killed}/{len(MUTANTS)} killed")
    for n, v, d in results:
        if v != "KILLED":
            print(f"  {v}: {n} — {d}")
    return 0 if killed == len(MUTANTS) else 1


if __name__ == "__main__":
    sys.exit(main())
