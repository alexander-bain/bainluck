#!/usr/bin/env python3
"""native/285 — mutation battery for #7794 (live sparkline flat-colour rule).

Same two harness rules as `native-284-mutations-7759.py` and `-284b-7780`: gate
on the EXIT CODE (65 xcodebuild / 1 jest), and match `with (\\d+) failures?` —
xcodebuild writes "with 1 failure", SINGULAR, and a plural-only regex reads a
sibling class's "0 failures" and reports a killed mutant as survived.

The mutants worth naming here:

  * M2 is the half-fix that a one-directional suite passes — silence the RED tie
    and leave the GREEN tie claiming a rise. 401 of ux's 467 tied windows were
    green, so a suite that only knew about the filed red specimen would ship it.
  * M3/M4 are the opposite degenerate fix — paint everything grey. Every
    "stops painting red" assertion in the world passes against them.
  * M6 moves the finiteness guard after the clamp. `max(0, .nan)` is 0 in Swift,
    so an unrenderable reading becomes a confident 0% instead of a refusal, and
    nothing about the rendered glyph looks wrong.
  * M10 mutates the CAMERA, not the product. The ink predicate used to count only
    green- or red-dominant pixels, so the instant a flat window drew grey it
    would have measured zero ink and `testAFlatMarketStaysFlat` would have kept
    passing `inkHeight < 12` against an empty image. This asserts that the
    non-vacuity line added beside it is load bearing.
"""

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GLYPH = ROOT / "ios/Bain Luck/Bain Luck/Components/LiveSparklineChart.swift"
CAMERA = ROOT / "ios/Bain Luck/BainLuckTests/LiveSparklineRenderSmokeTests.swift"
SIM = "D2DA47A0-85F6-4BF8-AEFF-33146AE3EB05"

MUTANTS = [
    ("M1 the original bug restored — direction reads the RAW probabilities",
     GLYPH,
     "guard let from = publishedPercent(first), let to = publishedPercent(last) else {",
     "guard let from = Optional(first), let to = Optional(last) else {", "swift"),

    ("M2 the half-fix — the RED tie is silenced, the GREEN tie still claims a rise",
     GLYPH, "if to > from { return .up }", "if to >= from { return .up }", "swift"),

    ("M3 paint everything grey (a rise stops being green)",
     GLYPH, "if to > from { return .up }", "if to > from { return .flat }", "swift"),

    ("M4 paint everything grey (a fall stops being red)",
     GLYPH, "if to < from { return .down }", "if to < from { return .flat }", "swift"),

    ("M5 the published percent goes back to a local `* 100`",
     GLYPH, "return renderedPercent(min(1, max(0, probability)))",
     "return Int((min(1, max(0, probability)) * 100).rounded())", "swift"),

    ("M6 the finiteness guard stops firing — NaN clamps to a confident 0%",
     GLYPH, "guard probability.isFinite else { return nil }",
     "guard true else { return nil }", "swift"),

    ("M7 the flat stroke is wired to the RED colour (arithmetic fine, reader lied to)",
     GLYPH, "case .flat: return Color(hex: strokeFlat)",
     "case .flat: return Color(hex: strokeDown)", "swift"),

    ("M8 the flat grey drifts one hex off the web's --text-muted",
     GLYPH, 'static let strokeFlat = "#9CA3AF"',
     'static let strokeFlat = "#9CA3B0"', "jest"),

    ("M9 the label rounds itself again, so the two channels can disagree",
     GLYPH, 'return "Last \\(minutes) minutes: \\(from)% to \\(to)%"',
     'return "Last \\(minutes) minutes: \\(Int((first.probability * 100).rounded()))%'
     ' to \\(Int((last.probability * 100).rounded()))%"', "swift"),

    ("M10 the CAMERA goes colour-blind to grey again (the vacuity this ship found)",
     CAMERA, "let candidates = target.map { [$0] } ?? [Self.up, Self.down, Self.flat]",
     "let candidates = target.map { [$0] } ?? [Self.up, Self.down]", "swift"),
]


def run_jest():
    p = subprocess.run(
        ["npx", "jest", "--testPathPatterns=liveSparklineDirectionParity7794"],
        cwd=ROOT / "frontend", capture_output=True, text=True,
    )
    return p.returncode, p.stdout + p.stderr


def run_swift():
    p = subprocess.run(
        ["xcodebuild", "-project", str(ROOT / "ios/Bain Luck/Bain Luck.xcodeproj"),
         "-scheme", "Bain Luck", "-destination", f"id={SIM}",
         "-disableAutomaticPackageResolution",
         "-only-testing:BainLuckTests/LiveSparklineDirectionTests",
         "-only-testing:BainLuckTests/LiveSparklineRenderSmokeTests",
         "-only-testing:BainLuckTests/LiveSparklineDomainTests",
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
            code, out = run_jest() if runner == "jest" else run_swift()
        finally:
            path.write_text(original)
        expected = 1 if runner == "jest" else 65
        if code == expected:
            verdict, detail = "KILLED", f"{runner} exit {code} — {label(out)}"
        elif code == 0:
            verdict, detail = "SURVIVED", f"{runner} exit 0 — NO TEST NOTICED"
        else:
            verdict, detail = "ERROR", f"{runner} exit {code} — harness, not a verdict"
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
