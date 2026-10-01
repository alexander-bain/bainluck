#!/usr/bin/env python3
"""#7074 — mutation run for the stale-cancellation generation guard.

The cancellation catch in `DiscoverViewModel.load()` now refuses to end a load
for a superseded generation. Each mutant breaks that guard one way; every one
must be KILLED by `DiscoverViewModelDeadlineTests`. A mutant whose anchor does
not match is a NON-RESULT (REFUSED), never a survivor or a kill.

Runs only from this lane's own worktree, on its own disposable simulator.
Usage:  python3 -u tools/native-7074-mutations-stale-cancel.py <sim-udid>
"""
import pathlib, subprocess, sys, time

WORKTREE = pathlib.Path("/Users/bain/bainluck-dev/native")
ROOT = WORKTREE / "ios/Bain Luck"
VM = ROOT / "Bain Luck/ViewModels/DiscoverViewModel.swift"
SIM = sys.argv[1]

GUARD = ("                guard generation == loadGeneration else { return .superseded }\n"
         "                loading = false\n"
         "                return .cancelled\n")

MUTANTS = [
    ("1 guard deleted (the pre-fix code)",
     "                loading = false\n                return .cancelled\n"),
    ("2 stale cancellation reports .cancelled",
     "                guard generation == loadGeneration else { return .cancelled }\n"
     "                loading = false\n                return .cancelled\n"),
    ("3 guard inverted (current generation refused)",
     "                guard generation != loadGeneration else { return .superseded }\n"
     "                loading = false\n                return .cancelled\n"),
    ("4 guard after the terminal write",
     "                loading = false\n"
     "                guard generation == loadGeneration else { return .superseded }\n"
     "                return .cancelled\n"),
]

original = VM.read_text()
results = []
try:
    for name, body in MUTANTS:
        if original.count(GUARD) != 1:
            results.append((name, f"REFUSED (anchor x{original.count(GUARD)})"))
            continue
        VM.write_text(original.replace(GUARD, body, 1))
        log = pathlib.Path(f"/tmp/n7074-mut-{name.split()[0]}.txt")
        with log.open("w") as fh:
            proc = subprocess.Popen(
                ["xcodebuild", "test", "-project", "Bain Luck.xcodeproj", "-scheme", "Bain Luck",
                 "-destination", f"id={SIM}", "-derivedDataPath", "/tmp/n7074-dd",
                 "-only-testing:BainLuckTests/DiscoverViewModelDeadlineTests",
                 "OTHER_SWIFT_FLAGS=$(inherited) -Xfrontend -disable-sandbox"],
                cwd=ROOT, stdout=fh, stderr=subprocess.STDOUT)
            # 🪤 xcodebuild can HANG after printing its verdict (a sandboxed
            # distributed-notification post, backtrace in the log) — measured on
            # this run's mutant 4 and its red run. Once the verdict line is in the
            # log, give it 20s to exit on its own, then stop it and read the exit
            # from the verdict line instead of the signal.
            verdict_seen_at = None
            while proc.poll() is None:
                time.sleep(2)
                body = log.read_text(errors="replace")
                if verdict_seen_at is None and ("** TEST FAILED **" in body or "** TEST SUCCEEDED **" in body):
                    verdict_seen_at = time.time()
                if verdict_seen_at and time.time() - verdict_seen_at > 20:
                    proc.terminate(); proc.wait()
                    break
            rc = proc.returncode
        text = log.read_text(errors="replace")
        if rc and rc < 0:
            rc = 0 if "** TEST SUCCEEDED **" in text else (65 if "** TEST FAILED **" in text else rc)
        failed = [l.split("[")[1].split("]")[0].split()[-1]
                  for l in text.splitlines() if "Test Case" in l and "' failed (" in l]
        # `xcodebuild test` exits 65 when tests FAIL (not only on build errors),
        # so the kill test is "the run reached TEST FAILED and named a failing
        # case" — a compile error prints neither and stays a NON-RESULT.
        if rc in (1, 65) and failed and "** TEST FAILED **" in text:
            results.append((name, "KILLED by " + ", ".join(failed)))
        elif rc == 0:
            results.append((name, "SURVIVED"))
        else:
            results.append((name, f"NON-RESULT (exit {rc}) — read {log}"))
        print(name, "->", results[-1][1], flush=True)
finally:
    VM.write_text(original)

print("\n=== SUMMARY")
for name, verdict in results:
    print(f"  mutant {name}: {verdict}")
killed = sum(v.startswith("KILLED") for _, v in results)
print(f"  {killed}/{len(MUTANTS)} killed")
sys.exit(0 if killed == len(MUTANTS) else 1)
