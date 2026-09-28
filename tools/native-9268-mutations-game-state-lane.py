#!/usr/bin/env python3
"""native — mutation battery for #9268 (the pushed slow lane re-reads game state).

Each mutant is applied to the tree, the #9268 test class is run, and the file is
restored byte-for-byte. A mutant whose needle is not found is REFUSED, never
counted as a kill. The clean tree runs LAST and must pass.
Usage: tools/native-9268-mutations-game-state-lane.py <SIM_UDID> [--dry-run] [--only M1[,M2...]]
"""
import re, subprocess, sys, pathlib
ROOT = pathlib.Path(__file__).resolve().parent.parent
IOS = ROOT / "ios/Bain Luck"
PLAN = "Bain Luck/Utilities/EventRefreshPlan.swift"
VM = "Bain Luck/ViewModels/EventDetailViewModel.swift"
READ = "    private func rereadGameState() async {\n        do {\n            adopt(try await client.fetchEvent(id: eventId))\n            error = nil\n"
MUTANTS = [
    ("M1 slow lane never cut (the old loop)", PLAN,
     "        guard plan == .poll(every: livePushPollInterval) else { return 1 }\n",
     "        return 1\n"),
    ("M2 every plan is cut", PLAN,
     "guard plan == .poll(every: livePushPollInterval) else { return 1 }",
     "guard plan != .idle else { return 1 }"),
    ("M3 state read at the slow cadence", PLAN,
     "static let liveStatePollInterval: TimeInterval = 30",
     "static let liveStatePollInterval: TimeInterval = 120"),
    ("M4 every slot is a full load", VM,
     "                if slot < slots {\n", "                if false {\n"),
    ("M5 state read fetches but never adopts", VM, READ,
     READ.replace("adopt(try await client.fetchEvent(id: eventId))", "_ = try await client.fetchEvent(id: eventId)")),
    ("M6 state read bypasses the push-preserving adopt", VM, READ,
     READ.replace("adopt(try await client.fetchEvent(id: eventId))", "event = try await client.fetchEvent(id: eventId)")),
    ("M7 state read claims to be a load", VM, READ,
     READ + "            lastLoadedAt = Date()\n"),
    ("M8 state read never re-plans", VM,
     "        // just as a load would; unchanged, this leaves the running loop alone.\n        configureAutoRefresh()\n",
     "        // just as a load would; unchanged, this leaves the running loop alone.\n"),
]

def run(sim):
    cmd = ["xcodebuild", "test", "-scheme", "Bain Luck", "-destination", f"id={sim}",
           "-derivedDataPath", "/tmp/n9268-dd",
           "-only-testing:BainLuckTests/AGameClockKeepsUpWithPushedPrices9268Tests",
           "OTHER_SWIFT_FLAGS=$(inherited) -Xfrontend -disable-sandbox"]
    r = subprocess.run(cmd, cwd=IOS, capture_output=True, text=True)
    failed = sorted(set(re.findall(r"AGameClockKeepsUpWithPushedPrices9268Tests (test\w+)\]' failed", r.stdout)))
    executed = [l.strip() for l in r.stdout.splitlines() if "Executed" in l and "tests" in l]
    return r.returncode, ("Testing cancelled because the build failed" in r.stdout), failed, (executed[-1] if executed else "no Executed line")

def main():
    sim = sys.argv[1]; dry = "--dry-run" in sys.argv
    only = sys.argv[sys.argv.index("--only") + 1].split(",") if "--only" in sys.argv else None
    chosen = [m for m in MUTANTS if only is None or m[0].split()[0] in only]
    results = []
    for name, rel, needle, repl in chosen:
        p = IOS / rel; orig = p.read_bytes(); text = orig.decode()
        if text.count(needle) != 1:
            results.append((name, f"REFUSED (needle count {text.count(needle)})")); continue
        if dry: results.append((name, "applies")); continue
        p.write_text(text.replace(needle, repl))
        try:
            rc, build_failed, failed, executed = run(sim)
        finally:
            p.write_bytes(orig)
        assert p.read_bytes() == orig
        if build_failed: verdict = "KILLED (build)"
        elif rc == 0: verdict = "SURVIVED"
        elif failed: verdict = f"KILLED by {', '.join(failed)}"
        else: verdict = f"UNEXPLAINED rc={rc} ({executed})"
        results.append((name, verdict))
        print(name, verdict, flush=True)
    if not dry:
        rc, _, _, executed = run(sim)
        results.append(("clean control", f"PASS ({executed})" if rc == 0 else f"FAIL rc={rc}"))
    for n, v in results: print(f"{n}: {v}")
    killed = sum(1 for _, v in results if v.startswith("KILLED"))
    print(f"{killed}/{len(chosen)} killed")
    bad = any(v.startswith(("SURVIVED", "REFUSED", "FAIL", "UNEXPLAINED")) for _, v in results)
    sys.exit(1 if bad else 0)

main()
