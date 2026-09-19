#!/usr/bin/env python3
"""native/243 — mutation run for #7074's pull arm (a pull completes, and says so).

The ship has two halves that fail in completely different ways, and the battery
is split along that line because only one of them is reachable by an assertion
on a value:

  * RULE mutants (6-12). `DiscoverPullRefreshNotice` is a pure value. Which
    phases speak, what each says, which decays, which carries the retry — an
    ordinary suite reaches all of it.

  * CALL-SITE mutants (1-5). 🔴 THESE ARE THE ONES THAT MATTER. The notice is
    rendered inside a SwiftUI builder returning an opaque type, so no
    behavioural test can reach it: every rule mutant above could be killed by a
    perfect suite with the row never drawn on the page at all. That is #4624's
    survivor and #7077's two photographed defects, one layer up, and it is why
    `testDiscoverDrawsTheNoticeAtTheTopFromTheLivePhase` scans the call site as
    source. Mutant 1 is the entire ship reverted; mutant 5 draws the notice
    correctly and puts it where the reader has to scroll to find out they no
    longer need to.

  * MODEL mutants (13-14) and STORE mutants (15-16). The controlled
    changed-response half: a refresh that republishes what it already had, a
    failure that reports success, and the two directions of the swipe store.

A mutant that SURVIVES is a hole in the guard suite, not a curiosity. A mutant
whose anchor does not match is a NON-RESULT and is reported as one — a refused
patch runs the unmutated tree and prints a green indistinguishable from an
unkillable mutant.

Runs only from this lane's own worktree; every path is absolute.

Usage:  python3 -u tools/native-243-mutations-7074-pull.py [--list]
        (`-u`: a buffered nohup log shows nothing for the whole run — n242 trap 5)
"""
import subprocess, sys, pathlib, signal, atexit

WORKTREE = pathlib.Path("/Users/bain/bainluck-dev/native")
ROOT = WORKTREE / "ios/Bain Luck"
VIEW = ROOT / "Bain Luck/Views/DiscoverView.swift"
RULE = ROOT / "Bain Luck/Utilities/DiscoverPullRefreshNotice.swift"
VM = ROOT / "Bain Luck/ViewModels/DiscoverViewModel.swift"
SIM = "D2DA47A0-85F6-4BF8-AEFF-33146AE3EB05"

# The ship's call site, verbatim. Mutant 1 deletes it; mutant 5 moves it.
CALL_SITE = """                if let notice = DiscoverPullRefreshNotice.forPhase(footerRefreshPhase) {
                    DiscoverPullRefreshNoticeRow(notice: notice) {
                        Task { await refreshFeed() }
                    }
                    .padding(.horizontal)
                    .padding(.bottom, 8)
                    .transition(.opacity)
                }
"""

GROUPED = "                let grouped = groupedItems\n"

# `load()` publishes through ONE of two branches, chosen by whether the server
# stamped an `edition` — and a mutant on the wrong one is dead code for your
# specimen. Measured: the first draft of mutant 13 patched `.repaint` alone and
# SURVIVED, not because the test was weak but because an editionless fixture can
# only ever take `.reconcile`. Both are patched, and the suite covers both.
REPAINT = "                case .repaint:\n                    items = Self.interleave(renderable)"
REPAINT_HELD = ("                case .repaint:\n"
                "                    if items.isEmpty { items = Self.interleave(renderable) }")
RECONCILE = ("                case .reconcile:\n"
             "                    items = DiscoverFeedReconcile.merge(\n"
             "                        painted: items, incoming: renderable, key: Self.itemKey)")
RECONCILE_HELD = ("                case .reconcile:\n"
                  "                    if items.isEmpty {\n"
                  "                        items = DiscoverFeedReconcile.merge(\n"
                  "                            painted: items, incoming: renderable, key: Self.itemKey)\n"
                  "                    }")


def move_below_the_grid(text):
    """Draw the notice correctly, one card grid too late."""
    return text.replace(CALL_SITE, "", 1).replace(GROUPED, GROUPED + CALL_SITE, 1)


def hold_the_painted_feed(text):
    """Both publication branches keep whatever is already on screen."""
    return text.replace(REPAINT, REPAINT_HELD, 1).replace(RECONCILE, RECONCILE_HELD, 1)


# Each mutant: (name, file, find, replace-or-callable, expected-anchor-count, why)
MUTANTS = [
    ("1-the-ship-reverted-notice-never-drawn", VIEW, CALL_SITE, "", 1,
     "ALEX'S REPORT VERBATIM: 'Pull gesture briefly shows activity with no apparent "
     "change.' Every rule test in the suite still passes — the value is perfect and "
     "nothing renders it. This is the mutant the whole file exists for"),

    ("2-notice-frozen-on-a-literal-phase", VIEW,
     "DiscoverPullRefreshNotice.forPhase(footerRefreshPhase)",
     "DiscoverPullRefreshNotice.forPhase(.refreshed)", 1,
     "'Checked just now' permanently pinned to the top of the feed, including for a "
     "reader who never pulled and for one whose pull FAILED. The compiler is happy "
     "and the rule is untouched"),

    ("3-retry-asks-for-a-scroll-it-does-not-need", VIEW,
     "Task { await refreshFeed() }",
     "Task { await refreshFeed(returningToTopWith: feedProxy) }", 1,
     "the control is AT the top of the feed and scrolls the reader to the top — "
     "#1472's own finding, re-made one control over"),

    ("4-retry-is-inert", VIEW, "Task { await refreshFeed() }", "Task { }", 1,
     "the failure notice's only answer does nothing. The row still draws, still says "
     "'Couldn't refresh', still offers the button"),

    ("5-notice-drawn-below-the-card-grid", VIEW, CALL_SITE, move_below_the_grid, 1,
     "the reader must scroll past the feed to learn they do not need to. Position is "
     "the whole of this ship — the phase has been correct at the FOOTER since #1472"),

    ("6-in-flight-phase-speaks-too", RULE,
     "        case .idle, .refreshing:\n            return nil",
     '        case .idle:\n            return nil\n        case .refreshing:\n'
     '            return DiscoverPullRefreshNotice(\n'
     '                text: "Checking", systemImage: "arrow.clockwise",\n'
     '                offersRetry: false, decays: true,\n'
     '                accessibilityLabel: "Checking for new markets.")', 1,
     "two in-flight markers for one request: the system's own pull spinner under the "
     "reader's finger and a second row directly beneath it"),

    ("7-success-offers-a-retry", RULE, "                offersRetry: false,",
     "                offersRetry: true,", 1,
     "the reader is invited to redo work that worked"),

    ("8-failure-clears-itself", RULE, "                decays: false,",
     "                decays: true,", 1,
     "the reader's ONLY notice of the failure, and the retry with it, disappears on a "
     "timer they did not start"),

    ("9-both-outcomes-draw-one-glyph", RULE,
     '                systemImage: "exclamationmark.triangle.fill",',
     '                systemImage: "checkmark.circle.fill",', 1,
     "success and failure differ by one short line of text and nothing else — the "
     "#1472 shape, where every phase produced a value and the values were the same"),

    ("10-both-outcomes-announce-identically", RULE,
     '                accessibilityLabel: "Couldn\'t refresh. Try again."',
     '                accessibilityLabel: "Feed refreshed. Checked just now."', 1,
     "a VoiceOver reader cannot tell a refreshed feed from one that never refreshed. "
     "Looks fine on screen, which is exactly why the ear is asserted separately"),

    ("11-success-copy-stops-borrowing-the-footers", RULE,
     '                text: NativeFeedEndCard.refreshPresentation(.refreshed).status ?? "",',
     '                text: "Refreshed",', 1,
     "two ends of one scroll view describing one event in two vocabularies (notice "
     "35). Nothing looks wrong in either place on its own"),

    ("12-failure-copy-speaks-in-jargon", RULE,
     '                text: NativeFeedEndCard.refreshPresentation(.failed).status ?? "",',
     '                text: "Feed request failed",', 1,
     "D102 / notice 34: the mechanism on the reader's screen instead of the outcome"),

    ("13-a-refresh-republishes-what-it-already-had", VM, REPAINT, hold_the_painted_feed, 1,
     "THE STATE ALEX COULD NOT DISTINGUISH FROM A WORKING REFRESH: the request goes "
     "out, the response comes back, the notice says 'Checked just now', and the rows "
     "are the ones that were already there. Every count-based witness passes"),

    ("13b-only-the-stamped-branch-holds", VM, REPAINT, REPAINT_HELD, 1,
     "the repaint path alone. A suite whose fixtures carry no `edition` cannot see "
     "this at all — it was mutant 13's first draft, and it survived for that reason "
     "and not for the reason a survivor usually means"),

    ("13c-only-the-unstamped-branch-holds", VM, RECONCILE, RECONCILE_HELD, 1,
     "the merge path alone, which is the one a server that does not stamp editions "
     "puts every reader through"),

    ("14-a-failed-refresh-reports-success", VM,
     '            error = "Showing recent markets — couldn\'t refresh"',
     "            error = nil", 2,
     "`refreshFeed` reads `vm.error == nil` as success, so a pull that failed draws "
     "'Checked just now' over a feed that was never refreshed — the worst reachable "
     "state of this ship, and one no screenshot could ever catch. TWO sites set this "
     "sentence and the test must not depend on which one its specimen takes"),

    ("15-a-pull-empties-the-swipe-store", VIEW,
     "        return store.filter { $0.value >= cutoff }", "        return [:]", 1,
     "every card the reader rejected this sitting comes straight back (#5951). "
     "codex's constraint on this arm names swipe history by name"),

    ("16-the-swipe-store-stops-ageing", VIEW,
     "        return store.filter { $0.value >= cutoff }", "        return store", 1,
     "the opposite direction, and the reason the preservation test has an "
     "anti-vacuity twin: a helper that returns its input satisfies 'nothing was lost'"),
]

# TRAP (banked by native/234): on a FAILING run xcodebuild calls
# `simctl diagnose --timeout=600`, i.e. ~10 minutes per KILLED mutant.
XCB = ["xcodebuild", "test",
       "-project", str(ROOT / "Bain Luck.xcodeproj"),
       "-scheme", "Bain Luck",
       "-destination", f"platform=iOS Simulator,id={SIM}",
       "-disableAutomaticPackageResolution",
       "-collect-test-diagnostics", "never",
       "-only-testing:BainLuckTests/APullOnDiscoverCompletesAndSaysSo7074Tests",
       "-only-testing:BainLuckTests/FooterRefreshSaysWhatItIsDoing1472Tests",
       "-only-testing:BainLuckTests/ARefreshDoesNotUndoASwipe5951Tests",
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
        # ALL occurrences, not the first: mutant 14's sentence is set at two sites
        # and patching one leaves the other to carry the test. `expected` above is
        # the count this mutant was written against, so a file that grows a third
        # site is REFUSED rather than silently half-patched.
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
