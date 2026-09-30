#!/usr/bin/env python3
"""native — mutation battery for #9051 (iPhone live headline ordered by fold revision).

Each mutant is applied to the tree, the #9051 test class is run, and the file is
restored byte-for-byte. A mutant whose needle is not found exactly once is
REFUSED, never counted as a kill. The clean tree runs LAST and must pass.
Usage: tools/native-9051-mutations-fold-revision.py <SIM_UDID> [--dry-run] [--only M2[,M5...]]
"""
import subprocess, sys, pathlib
ROOT = pathlib.Path(__file__).resolve().parent.parent
IOS = ROOT / "ios/Bain Luck"
F = "Bain Luck/Utilities/FoldRevision.swift"
R = "Bain Luck/Utilities/LiveEventPriceReconciliation.swift"
V = "Bain Luck/ViewModels/EventDetailViewModel.swift"
MUTANTS = [
    ("M1 poll: older frame falls through to clocks", R, "            return order == .newer\n", "            if order == .newer { return true }\n"),
    ("M2 stream: fold gate ignored", V, "priceIsNotNewer = foldOrder != .newer", "priceIsNotNewer = false"),
    ("M3 stream: no re-read on incomparable", V, "if foldOrder == .incomparable { requestRevisionRefetch() }", "if false { requestRevisionRefetch() }"),
    ("M4 load: held headline never kept", V, "fetched = LiveEventPriceReconciliation.keepingNewerHeldHeadline(fetched, held: event)", "_ = event"),
    ("M5 keep: unversioned response wins", R,
     "        if let polledRevision = pairedFoldRevision(in: polled),\n           FoldRevision.compare(polledRevision, heldRevision) != .older { return polled }",
     "        guard let polledRevision = pairedFoldRevision(in: polled),\n           FoldRevision.compare(polledRevision, heldRevision) == .older else { return polled }"),
    ("M6 frame: folded hero orderable", F, "guard held.rows.count == 1, let frame, frame.rows.count == 1 else", "guard let frame else"),
    ("M7 frame: unversioned frame is no claim", F,
     "guard held.rows.count == 1, let frame, frame.rows.count == 1 else { return .incomparable }",
     "guard let frame else { return nil }\n        guard held.rows.count == 1, frame.rows.count == 1 else { return .incomparable }"),
    ("M8 compare: row count unchecked", F, "guard incoming.rows.count == held.rows.count,\n              held.rows.keys", "guard held.rows.keys"),
    ("M9 compare: mixed reads newer", F, "if higher && lower { return .incomparable }", "if false && lower { return .incomparable }"),
    ("M10 parse: negative accepted", F, "$0 >= 0 && ", ""),
    ("M11 parse: past 2^53 accepted", F, " && $0 <= Self.maxSafeInteger", ""),
    ("M12 pairing unchecked", R, "        return shown == hero\n", "        _ = shown; return true\n"),
    ("M13 frame revision not carried", R, "event.blendFoldRevision = ServedFoldRevision(frame.rev?.revision)", "_ = frame.rev"),
    ("M14 chart: incomparable asks nothing", R, "guard order == .newer || order == .incomparable else { return nil }", "guard order == .newer else { return nil }"),
    ("M15 chart: pushed edge ignored", R, "let drawnEdge = liveBlend.filter", "let drawnEdge = [LiveBlendPoint]().filter"),
    ("M16 keep: response sources replace held", R, "kept.winProbabilitySources = held.winProbabilitySources", "_ = held.winProbabilitySources"),
    ("M17 keep: withheld away refilled", R, "odds.awayProbability = odds.awayProbability == nil ? nil : heldOdds.awayProbability", "odds.awayProbability = heldOdds.awayProbability"),
]

def run(sim):
    cmd = ["xcodebuild", "test", "-project", "Bain Luck.xcodeproj", "-scheme", "Bain Luck",
           "-destination", f"platform=iOS Simulator,id={sim}", "-disableAutomaticPackageResolution",
           "-only-testing:BainLuckTests/ARemovedSourceStaysOutOfTheLiveHeadline9051Tests", "-collect-test-diagnostics", "never",
           "OTHER_SWIFT_FLAGS=$(inherited) -Xfrontend -disable-sandbox"]
    r = subprocess.run(cmd, cwd=IOS, capture_output=True, text=True)
    return r.returncode, ("Testing cancelled because the build failed" in r.stdout or "** BUILD FAILED **" in r.stdout)

def main():
    sim = sys.argv[1]; dry = "--dry-run" in sys.argv
    only = sys.argv[sys.argv.index("--only") + 1].split(",") if "--only" in sys.argv else None
    chosen = [m for m in MUTANTS if only is None or m[0].split()[0] in only]
    results = []
    for name, rel, needle, repl in chosen:
        p = IOS / rel; orig = p.read_bytes(); text = orig.decode()
        if text.count(needle) != 1:
            results.append((name, f"REFUSED (needle count {text.count(needle)})")); print(name, results[-1][1], flush=True); continue
        if dry: results.append((name, "applies")); continue
        p.write_text(text.replace(needle, repl))
        try:
            rc, build_failed = run(sim)
        finally:
            p.write_bytes(orig)
        assert p.read_bytes() == orig
        results.append((name, "KILLED (build)" if build_failed else ("KILLED" if rc != 0 else "SURVIVED")))
        print(name, results[-1][1], flush=True)
    if not dry:
        rc, _ = run(sim)
        results.append(("clean control", "PASS" if rc == 0 else f"FAIL rc={rc}"))
    for n, v in results: print(f"{n}: {v}")
    killed = sum(1 for _, v in results if v.startswith("KILLED"))
    print(f"{killed}/{len(chosen)} killed")
    bad = any(v.startswith(("SURVIVED", "REFUSED", "FAIL")) for _, v in results)
    sys.exit(1 if bad else 0)

if __name__ == "__main__":
    main()
