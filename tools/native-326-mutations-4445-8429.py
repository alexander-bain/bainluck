#!/usr/bin/env python3
"""native/326 — mutation battery for #4445 (legible maximum-size dates) + #8429 (whole names).

Each mutant breaks one half of the fix; the focused class must go RED. Restores the file after each.
Run from the worktree root after the gates (shares DerivedData with them).
"""
import subprocess, sys, pathlib
EVO = pathlib.Path("ios/Bain Luck/Bain Luck/Components/EvolutionChartView.swift")
ODDS = pathlib.Path("ios/Bain Luck/Bain Luck/Components/OddsChartView.swift")
MUTANTS = [
    ("M1 dates pinned at 9pt again", EVO,
     "return min(max(scaled, axisLabelBasePointSize), axisLabelMaxPointSize)", "return axisLabelBasePointSize"),
    ("M2 planner ignores the grown size", ODDS,
     "labelWidth: xAxisLabelWidth(for: style) * max(labelScale, 1),", "labelWidth: xAxisLabelWidth(for: style),"),
    ("M3 no endpoints fallback (one-stride axis kept)", EVO,
     "if span / nominalSeconds(of: plan) >= 2 {", "if span / nominalSeconds(of: plan) >= 0 {"),
    ("M4 participant never stacks", EVO,
     "        size.isAccessibilitySize\n    }", "        false\n    }"),
    ("M5 endpoints collapse to one style", EVO,
     "if !calendar.isDate(lo, inSameDayAs: hi) { return .dayAndTime }", "if !calendar.isDate(lo, inSameDayAs: hi) { return .hourOfDay }"),
]
SIM = sys.argv[1] if len(sys.argv) > 1 else "D2DA47A0-85F6-4BF8-AEFF-33146AE3EB05"
killed = 0
for name, path, old, new in MUTANTS:
    src = path.read_text()
    assert src.count(old) == 1, f"{name}: anchor not unique/missing"
    path.write_text(src.replace(old, new))
    try:
        # xcodebuild can hang AFTER the suite reports (seen this session), so read the
        # suite's own verdict line from the log and stop the process once it appears.
        import time
        log = pathlib.Path("/tmp/native326-mutant.txt")
        with log.open("w") as fh:
            proc = subprocess.Popen(["xcodebuild", "test", "-project", "ios/Bain Luck/Bain Luck.xcodeproj",
                "-scheme", "Bain Luck", "-destination", f"id={SIM}",
                "OTHER_SWIFT_FLAGS=$(inherited) -Xfrontend -disable-sandbox",
                "-only-testing:BainLuckTests/EvolutionMaximumTextDatesAndNames4445And8429Tests"],
                stdout=fh, stderr=subprocess.STDOUT)
            deadline = time.time() + 900
            while time.time() < deadline:
                out = log.read_text(errors="replace")
                if ("Test Suite 'Selected tests'" in out and ("passed at" in out or "failed at" in out)) \
                        or "Testing cancelled" in out or proc.poll() is not None:
                    break
                time.sleep(5)
            time.sleep(2)
            proc.kill()
        out = log.read_text(errors="replace")
        built = "Testing cancelled because the build failed" not in out
        red = "Test Suite 'Selected tests' failed" in out
        green = "Test Suite 'Selected tests' passed" in out
        verdict = "KILLED" if (red and built) else ("BUILD-FAIL" if not built else ("SURVIVED" if green else "NO-VERDICT"))
    finally:
        path.write_text(src)
    killed += verdict == "KILLED"
    print(f"{verdict:10} {name}", flush=True)
print(f"{killed}/{len(MUTANTS)} killed")
