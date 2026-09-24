#!/usr/bin/env python3
"""native/320 (#8320 slice 3) — mutation battery for "an opened stream is not a pushed price".

Each mutant re-introduces one shape of the false push dot; the named tests must go red.
A fifth mutant ("stop keeps the claim") was EQUIVALENT and was removed with the
line it attacked: `stopStream` calls `controller.stop()`, which reports not-delivering,
and that callback already clears the claim. Run from the worktree root. Restores every file whatever happens.
Usage: tools/native-320-mutations-8320.py [--dry-run]
"""
import subprocess, sys, pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
APP = ROOT / "ios/Bain Luck/Bain Luck"
PAGE = APP / "Views/EventDetailView.swift"
VM = APP / "ViewModels/EventDetailViewModel.swift"
SIM = "D2DA47A0-85F6-4BF8-AEFF-33146AE3EB05"

MUTANTS = [
    ("indicator ignores the pushed price (the defect)", PAGE,
     "        guard pushedPrice else { return .polling }\n",
     ""),
    ("fallback keeps the old push", VM,
     "                if !delivering { self.streamHasPushedPrice = false }\n",
     ""),
    ("claim cleared on the way up too (erases a resumed stream's first price)", VM,
     "                if !delivering { self.streamHasPushedPrice = false }\n",
     "                self.streamHasPushedPrice = false\n"),
    ("apply never records the push", VM,
     "            streamHasPushedPrice = true\n",
     ""),
]

TESTS = ["AnOpenedStreamIsNotAPushedPrice8320Tests", "EventRefreshTruthTests"]

def run_tests():
    cmd = ["xcodebuild", "-project", str(ROOT / "ios/Bain Luck/Bain Luck.xcodeproj"),
           "-scheme", "Bain Luck", "-destination", f"platform=iOS Simulator,id={SIM}",
           "-disableAutomaticPackageResolution",
           "OTHER_SWIFT_FLAGS=$(inherited) -Xfrontend -disable-sandbox"]
    cmd += [f"-only-testing:BainLuckTests/{t}" for t in TESTS] + ["test"]
    r = subprocess.run(cmd, capture_output=True, text=True)
    out = r.stdout + r.stderr
    failed = sorted({l.split("[")[1].split("]")[0] for l in out.splitlines()
                     if "error: -[" in l and "failed" in l} |
                    {l.split("-[")[1].split("]")[0] for l in out.splitlines()
                     if l.strip().startswith("Test Case '-[") and "failed" in l})
    return r.returncode, failed

def main():
    dry = "--dry-run" in sys.argv
    for name, path, needle, _ in MUTANTS:
        n = path.read_text().count(needle)
        if n != 1:
            print(f"ANCHOR {'MISSING' if n == 0 else 'AMBIGUOUS'} ({n}): {name}")
            return 2
    if dry:
        print(f"dry-run: {len(MUTANTS)} mutants, every anchor found exactly once")
        return 0
    killed = 0
    for name, path, needle, repl in MUTANTS:
        original = path.read_text()
        try:
            path.write_text(original.replace(needle, repl, 1))
            code, failed = run_tests()
        finally:
            path.write_text(original)
        if code != 0 and failed:
            killed += 1
            print(f"KILLED   {name}: {', '.join(failed[:3])}")
        elif code != 0:
            print(f"BUILD?   {name}: exit {code} with no failing test named — not a kill")
        else:
            print(f"SURVIVED {name}")
    print(f"{killed}/{len(MUTANTS)} killed")
    return 0 if killed == len(MUTANTS) else 1

if __name__ == "__main__":
    sys.exit(main())
