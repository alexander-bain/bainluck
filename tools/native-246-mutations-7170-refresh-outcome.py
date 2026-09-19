#!/usr/bin/env python3
"""native/246 — mutation run for #7170 (a refresh reports the outcome of its own request).

The ship is two changes that fail in completely different ways, and the battery
is split along that line:

  * CONTRACT mutants (7-13). `load()` now returns what its generation did. Each
    terminal is patched to claim `.published` — the lie the ship exists to make
    impossible — and an ordinary behavioural test reaches every one of them.

  * CALL-SITE mutants (1-2). 🔴 THESE ARE THE ONES THAT MATTER, and neither is
    reachable by a behavioural test: both halves live inside `refreshFeed`, an
    `async` method on a `View`. Mutant 1 reverts the phase to the `error == nil`
    sniff — the entire defect restored, with the contract still perfect and
    nothing reading it. Mutant 2 reverts the unstructured `Task` and the pull is
    cancelled again; a fake client is never cancelled by a SwiftUI gesture
    teardown, so no unit test can see it. Both are pinned by source scans, the
    pattern `APullOnDiscoverCompletesAndSaysSo7074Tests` established.

  * RULE mutants (3-5). `refreshPhase(for:)`, the pure mapping hoisted out of the
    view precisely so it could be pinned here.

  * WITNESS mutant (6). The rig badge field that produced the diagnosis. If the
    vocabulary collapses, the journey reads a plausible wrong word.

A mutant that SURVIVES is a hole in the guard suite, not a curiosity. A mutant
whose anchor does not match is a NON-RESULT and is reported as one — a refused
patch runs the unmutated tree and prints a green indistinguishable from an
unkillable mutant.

Runs only from this lane's own worktree; every path is absolute.

Usage:  python3 -u tools/native-246-mutations-7170-refresh-outcome.py [--list]
        (`-u`: a buffered nohup log shows nothing for the whole run — n242 trap 5)
"""
import subprocess, sys, pathlib, signal, atexit

WORKTREE = pathlib.Path("/Users/bain/bainluck-dev/native")
ROOT = WORKTREE / "ios/Bain Luck"
VIEW = ROOT / "Bain Luck/Views/DiscoverView.swift"
VM = ROOT / "Bain Luck/ViewModels/DiscoverViewModel.swift"
SIM = "D2DA47A0-85F6-4BF8-AEFF-33146AE3EB05"

# ── the two call-site lines, verbatim ────────────────────────────────────────
PHASE_LINE = "        footerRefreshPhase = Self.refreshPhase(for: outcome)"
# The defect as it shipped: infer the outcome from the error string. `.refreshed`
# is assigned in the branch below, so reverting is a one-line swap plus the guard.
PHASE_REVERTED = "        footerRefreshPhase = vm.error == nil ? .refreshed : .failed"

DETACHED = "        let outcome = await Task { @MainActor in await vm.load() }.value"
STRUCTURED = "        let outcome = await vm.load()"

# ── the pure rule ────────────────────────────────────────────────────────────
# 🪤 ANCHORED ON THE `return` ALONE, NOT ON `case ...:\n return ...`. The first
# draft paired each case label with its return and BOTH were REFUSED (0x) —
# `refreshPhase`'s arms carry explanatory comments between the label and the
# return, so the two-line anchor matches nothing. A refused mutant is a
# non-result, and two of them read as "9/11 killed" until the report is read
# properly. Each return below is unique in the file (asserted by `expected=1`),
# so a one-line anchor is exact here and cannot silently hit a sibling.
SILENT_ARM = "            return .idle"
SILENT_ARM_LIES = "            return .refreshed"
PUBLISHED_ARM = "            return .refreshed"
PUBLISHED_ARM_MUTE = "            return .idle"
FAILED_ARM = ("        case .failed:\n"
              "            return .failed")
FAILED_ARM_LIES = ("        case .failed:\n"
                   "            return .refreshed")

# ── the rig witness ──────────────────────────────────────────────────────────
WORDS = ('        case .published: return "published"\n'
         '        case .failed: return "failed"\n'
         '        case .superseded: return "superseded"\n'
         '        case .cancelled: return "cancelled"')
WORDS_COLLAPSED = ('        case .published: return "published"\n'
                   '        case .failed: return "published"\n'
                   '        case .superseded: return "published"\n'
                   '        case .cancelled: return "published"')

# ── the contract's terminals ─────────────────────────────────────────────────
SUPERSEDED_GUARD = "guard generation == loadGeneration else { return .superseded }"
SUPERSEDED_LIES = "guard generation == loadGeneration else { return .published }"

CANCEL_TERMINAL = "                loading = false\n                return .cancelled"
CANCEL_LIES = "                loading = false\n                return .published"

SUCCESS_TERMINAL = "                return .published"
SUCCESS_MUTED = "                return .cancelled"

UNAVAILABLE_TERMINAL = "                    return .failed"
UNAVAILABLE_LIES = "                    return .published"

POSTLOOP_TERMINAL = "        return .failed\n    }"
POSTLOOP_LIES = "        return .published\n    }"


# Each mutant: (name, file, find, replace-or-callable, expected-anchor-count, why)
MUTANTS = [
    ("1-the-ship-reverted-phase-read-from-the-error-string", VIEW,
     PHASE_LINE, PHASE_REVERTED, 1,
     "#7170 RESTORED IN ONE LINE. `load()` still reports honestly, `refreshPhase(for:)` is "
     "still a perfect rule, and nothing reads it — so a cancelled or superseded refresh "
     "draws 'Feed refreshed. Checked just now.' again. Every contract test below still "
     "passes. This is the mutant the source scan exists for"),

    ("2-the-refresh-load-is-a-child-of-the-gesture-again", VIEW,
     DETACHED, STRUCTURED, 1,
     "MEASURED as `OUTCOME cancelled · FEED 1 → 1 · PULLS 0 → 1`: `.refreshable` tears its "
     "task down while the reader is still on Discover and takes the request with it, so the "
     "pull publishes nothing. No unit test can reach this — a fake client is never cancelled "
     "by a gesture teardown"),

    ("3-a-silent-terminal-claims-the-success-row", VIEW,
     SILENT_ARM, SILENT_ARM_LIES, 1,
     "the #7170 lie relocated into the rule itself: a refresh that published nothing is "
     "handed the row that says it did"),

    ("4-a-published-refresh-says-nothing", VIEW,
     PUBLISHED_ARM, PUBLISHED_ARM_MUTE, 1,
     "the opposite direction, and the reason the rule needs a positive assertion: a mapping "
     "that answers `.idle` to everything can never tell the reader a lie, and can never tell "
     "them anything. Alex's build-15 report verbatim"),

    ("5-a-failed-refresh-reports-success", VIEW,
     FAILED_ARM, FAILED_ARM_LIES, 1,
     "the honest failure terminal — the one that ALREADY worked before this ship — rerouted "
     "to the success row"),

    ("6-the-badge-vocabulary-collapses", VIEW,
     WORDS, WORDS_COLLAPSED, 1,
     "the witness that produced the diagnosis reads 'published' for every terminal, so the "
     "journey passes on a build where the pull is cancelled. An instrument that reports the "
     "answer it was built to test for"),

    ("7-every-superseded-guard-claims-it-published", VM,
     SUPERSEDED_GUARD, SUPERSEDED_LIES, 8,
     "the eight silent generation exits announce a refresh. This is the terminal #7170 "
     "NAMED as the cause — wrongly, as it turned out — and it is still one lie away"),

    ("8-the-cancellation-terminal-claims-it-published", VM,
     CANCEL_TERMINAL, CANCEL_LIES, 1,
     "🔴 THE MEASURED ONE. This is the terminal the live defect actually reached. Quiet to "
     "the screen is correct (L2-214 Item 2); quiet to the caller is the bug"),

    ("9-the-success-terminal-under-reports", VM,
     SUCCESS_TERMINAL, SUCCESS_MUTED, 1,
     "the only publishing terminal calls itself cancelled, so a working refresh goes silent "
     "forever — the anti-vacuity direction for every `.published` assertion"),

    ("10-the-unavailable-refusal-claims-it-published", VM,
     UNAVAILABLE_TERMINAL, UNAVAILABLE_LIES, 1,
     "a typed-UNAVAILABLE body knows nothing about the feed, is correctly refused, and then "
     "reports a completed refresh. The case a reader reaches by pulling twice quickly"),

    ("11-the-all-attempts-failed-terminal-claims-it-published", VM,
     POSTLOOP_TERMINAL, POSTLOOP_LIES, 1,
     "every attempt failed, the banner says so, and the refresh announces success beside it — "
     "two surfaces contradicting each other about one request"),
]

# TRAP (banked by native/234): on a FAILING run xcodebuild calls
# `simctl diagnose --timeout=600`, i.e. ~10 minutes per KILLED mutant.
XCB = ["xcodebuild", "test",
       "-project", str(ROOT / "Bain Luck.xcodeproj"),
       "-scheme", "Bain Luck",
       "-destination", f"platform=iOS Simulator,id={SIM}",
       "-disableAutomaticPackageResolution",
       "-collect-test-diagnostics", "never",
       "-only-testing:BainLuckTests/ARefreshReportsItsOwnOutcome7170Tests",
       # The two suites that own the superseded arms (mutant 7): the late-response
       # race and the identity rebind. They were already green before this ship and
       # now assert the outcome as well, so mutant 7 has a killer that is not mine.
       "-only-testing:BainLuckTests/DiscoverViewModelLoadTests",
       "-only-testing:BainLuckTests/DiscoverViewModelRebindTests",
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
        for m in MUTANTS:
            print(f"  {m[0]}  [{m[1].name}]")
        return 0

    print("baseline (unmutated tree)")
    code, _, out = run_tests()
    if code != 0:
        print(f"  BASELINE IS RED (exit {code}) — fix that before reading any mutant")
        print("\n".join(out.splitlines()[-25:]))
        return 2
    print("  baseline GREEN\n")

    killed, survived = [], []
    for name, path, find, repl, expected, why in MUTANTS:
        original = path.read_text()
        # A refused patch prints a green indistinguishable from an unkillable
        # mutant, so refusal is reported as a NON-result, never a pass.
        found = original.count(find)
        if found != expected:
            print(f"  REFUSED  {name} — anchor occurs {found}x in {path.name}, expected {expected}")
            survived.append((name, "REFUSED"))
            continue
        mutated = repl(original) if callable(repl) else original.replace(find, repl)
        if mutated == original:
            print(f"  REFUSED  {name} — the patch changed nothing")
            survived.append((name, "REFUSED-NOOP"))
            continue
        try:
            _IN_FLIGHT[path] = original
            path.write_text(mutated)
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
    print("\ntree on exit (expect ONLY this ship's own edits):")
    print("  " + (dirty.replace("\n", "\n  ") if dirty else "(clean)"))
    return 0 if not survived else 1


if __name__ == "__main__":
    sys.exit(main())
