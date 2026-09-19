#!/usr/bin/env python3
"""native/244 — mutation run for #7074's controlled changed-response arm.

THE SHIP. A rig affordance (`-launch_changed_refresh N`) that withholds the
first N cards from a refresh, so a journey with a REAL FINGER can perform a
controlled changed-response experiment against the real network — the thing the
issue asks for ("Prove gesture→request→completion and useful stable position on
a controlled changed-response test") and the thing native/243 said plainly it
could not do from the `DiscoverFeedProviding` seam.

The battery is split the way the ship fails:

  * RULE mutants (1-6). `rigStagedRefresh` is a pure generic function and an
    ordinary suite reaches all of it: which payloads it stages, which it
    refuses, whether the survivors keep their order, whether the edition is
    restamped.

  * FLAG mutants (7-8). `LaunchRig.changedRefreshDrop` — a value that would
    stage an unchanged refresh is the one thing this affordance must never
    quietly accept, because an unchanged refresh is precisely the state the
    journey exists to tell apart from a changed one.

  * CALL-SITE mutants (9-12). 🔴 THESE ARE THE ONES THAT MATTER, and every rule
    mutant above can be killed by a perfect suite while these are live. A pure
    function wired into nothing is a journey that pulls, measures an unchanged
    refresh, and reports that the feed did not change — green, and asserting
    nothing. Mutant 9 is the entire ship reverted; mutant 12 removes the
    compile-time Release guard, which is the difference between a test
    affordance and a shipped defect that shortens a reader's feed.

A mutant that SURVIVES is a hole in the guard suite, not a curiosity. A mutant
whose anchor does not match is a NON-RESULT and is reported as one — a refused
patch runs the unmutated tree and prints a green indistinguishable from an
unkillable mutant.

Runs only from this lane's own worktree; every path is absolute (n239 trap 7).

Usage:  python3 -u tools/native-244-mutations-7074-changed-response.py [--list]
        (`-u`: a buffered nohup log shows nothing for the whole run)
"""
import subprocess, sys, pathlib, signal, atexit

WORKTREE = pathlib.Path("/Users/bain/bainluck-dev/native")
ROOT = WORKTREE / "ios/Bain Luck"
VM = ROOT / "Bain Luck/ViewModels/DiscoverViewModel.swift"
RIG = ROOT / "Bain Luck/Utilities/LaunchRig.swift"
SIM = "D2DA47A0-85F6-4BF8-AEFF-33146AE3EB05"

# The rule, verbatim.
GUARD = ("        guard let drop, drop > 0, hasPaintedFeed, !items.isEmpty else {\n"
         "            return (items, edition)\n"
         "        }")
# The WHOLE body. Mutant 1 replaces this rather than just the guard: patching the
# guard alone leaves `withheld` referring to an unbound `drop` and the mutant dies
# at COMPILE time, which proves the compiler noticed and says nothing about
# whether the suite would. A mutant that does not build is not a test of a test.
BODY = (GUARD + "\n"
        "        let withheld = Swift.min(drop, items.count - 1)\n"
        "        guard withheld > 0 else { return (items, edition) }\n"
        '        return (Array(items.dropFirst(withheld)), "\\(edition ?? "none")+rig-withheld-\\(withheld)")')
WITHHELD = "        let withheld = Swift.min(drop, items.count - 1)"
RETURN = ('        return (Array(items.dropFirst(withheld)), "\\(edition ?? "none")+rig-withheld-\\(withheld)")')

# The call site, verbatim.
CALL_SITE = """                #if DEBUG
                let rigDrop = LaunchRig.changedRefreshDrop()
                #else
                let rigDrop: Int? = nil
                #endif
                let staged = Self.rigStagedRefresh(
                    items: Self.renderable(response.items),
                    edition: response.edition,
                    hasPaintedFeed: !items.isEmpty,
                    drop: rigDrop
                )
                let renderable = staged.items
"""
CALL_SITE_REVERTED = "                let renderable = Self.renderable(response.items)\n"


def revert_the_ship(text):
    """The rig is a pure function nobody calls, and the feed is the raw payload."""
    return (text.replace(CALL_SITE, CALL_SITE_REVERTED, 1)
                .replace("incomingEdition: staged.edition", "incomingEdition: response.edition", 1)
                .replace("paintedEdition = staged.edition", "paintedEdition = response.edition", 1))


def ship_it_to_release(text):
    """Honour the flag in EVERY configuration — a reader can shorten their feed."""
    return text.replace(CALL_SITE, CALL_SITE.replace(
        "                #if DEBUG\n"
        "                let rigDrop = LaunchRig.changedRefreshDrop()\n"
        "                #else\n"
        "                let rigDrop: Int? = nil\n"
        "                #endif\n",
        "                let rigDrop = LaunchRig.changedRefreshDrop()\n"), 1)


# Each mutant: (name, file, find, replace-or-callable, expected-anchor-count, why)
MUTANTS = [
    ("1-the-rig-stages-nothing", VM, BODY,
     "        return (items, edition)", 1,
     "the affordance is inert: the journey pulls, the response is byte-identical, and it reports "
     "'the feed did not change' — Alex's own report, manufactured by the instrument"),

    ("2-a-readers-ordinary-refresh-is-shortened", VM, GUARD,
     "        guard hasPaintedFeed, !items.isEmpty else {\n            return (items, edition)\n        }\n"
     "        let drop = drop ?? 1", 1,
     "THE WORST REACHABLE STATE OF THIS SHIP: with no launch argument at all, every refresh silently "
     "withholds a card. This is why the no-drop assertion is the first test in the file"),

    ("3-the-first-paint-is-shortened-too", VM, GUARD,
     "        guard let drop, drop > 0, !items.isEmpty else {\n            return (items, edition)\n        }", 1,
     "payload A is shortened as well, so the journey compares two shortened lists and calls the "
     "difference between them the experiment's result"),

    ("4-the-edition-is-not-restamped", VM, RETURN,
     '        return (Array(items.dropFirst(withheld)), edition)', 1,
     "a genuinely different list carrying the token of the list it replaced: DiscoverFeedReconcile "
     "reconciles it in place, so the journey silently exercises the branch that runs when NOTHING "
     "changed — and still goes green on its count-based witnesses"),

    ("5-the-cards-come-off-the-bottom", VM, RETURN,
     '        return (Array(items.dropLast(withheld)), "\\(edition ?? "none")+rig-withheld-\\(withheld)")', 1,
     "the list really is shorter and the TOP of it is identical, so the reader sees no change at the "
     "only place the journey looks"),

    ("6-the-feed-may-be-emptied", VM, WITHHELD,
     "        let withheld = Swift.min(drop, items.count)", 1,
     "an over-sized drop empties the feed, which is mayReplaceRendered's refusal terminal and "
     "Discover's empty state — the rig manufactures a different defect and the journey photographs it"),

    ("7-the-flag-accepts-a-drop-of-zero", RIG,
     "count > 0\n        else { return nil }", "count >= 0\n        else { return nil }", 1,
     "`-launch_changed_refresh 0` stages an UNCHANGED refresh while the journey believes it asked for "
     "a changed one: a green run of an experiment that was never performed"),

    ("8-an-absent-flag-withholds-a-card", RIG,
     "        else { return nil }\n        return count",
     "        else { return 1 }\n        return count", 1,
     "every reader's feed, in the configuration that has a call site — and the rig's siblings are all "
     "read-only, so nothing else here would make anyone look"),

    ("9-the-ship-reverted-rig-wired-to-nothing", VM, CALL_SITE, revert_the_ship, 1,
     "THE MUTANT THIS FILE EXISTS FOR. Every rule mutant above is killed by a suite that still passes "
     "here: a perfect pure function called by nobody. The journey pulls, measures no change, and "
     "reports the feed unchanged"),

    ("10-the-decision-reads-the-raw-edition", VM,
     "incomingEdition: staged.edition", "incomingEdition: response.edition", 1,
     "the staged list is judged by the token of the list it replaced, so it reconciles in place: the "
     "changed-response branch is never taken and nothing on screen says so"),

    ("11-the-painted-token-describes-a-list-never-painted", VM,
     "paintedEdition = staged.edition", "paintedEdition = response.edition", 1,
     "the NEXT refresh compares against a token no list ever had"),

    ("12-the-flag-is-honoured-in-a-shipping-build", VM, CALL_SITE, ship_it_to_release, 1,
     "the one affordance here that withholds CARDS, live in Release. A TestFlight reader who passes "
     "the argument serves themselves a shortened feed and the failure looks like a backend defect"),
]

# TRAP (banked by native/234): on a FAILING run xcodebuild calls
# `simctl diagnose --timeout=600`, i.e. ~10 minutes per KILLED mutant.
XCB = ["xcodebuild", "test",
       "-project", str(ROOT / "Bain Luck.xcodeproj"),
       "-scheme", "Bain Luck",
       "-destination", f"platform=iOS Simulator,id={SIM}",
       "-disableAutomaticPackageResolution",
       "-collect-test-diagnostics", "never",
       "-only-testing:BainLuckTests/AControlledChangedRefresh7074Tests",
       "-only-testing:BainLuckTests/LaunchRigContractTests",
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

    # `--only <substring>`: re-run one mutant after fixing a BATTERY defect (a
    # stale anchor, a compile-only kill) without paying for the other eleven.
    # Never a way to report a subset as the run: the summary says what it ran.
    selected = MUTANTS
    if "--only" in sys.argv:
        needle = sys.argv[sys.argv.index("--only") + 1]
        selected = [m for m in MUTANTS if needle in m[0]]
        if not selected:
            print(f"no mutant matches '{needle}'")
            return 2
        print(f"PARTIAL RUN — {len(selected)} of {len(MUTANTS)} mutants match '{needle}'\n")

    print("baseline (unmutated tree)")
    code, _, out = run_tests()
    if code != 0:
        print(f"  BASELINE IS RED (exit {code}) — fix that before reading any mutant")
        print("\n".join(out.splitlines()[-25:]))
        return 2
    print("  baseline GREEN\n")

    killed, survived = [], []
    for name, path, find, repl, expected, why in selected:
        original = path.read_text()
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

    print(f"\n{len(killed)}/{len(selected)} killed")
    for n, s in survived:
        print(f"  {s}: {n}")

    dirty = subprocess.run(["git", "-C", str(WORKTREE), "diff", "--stat", "--", "ios/"],
                           capture_output=True, text=True).stdout.strip()
    print("\ntree on exit (expect ONLY this ship's own edits):")
    print("  " + (dirty.replace("\n", "\n  ") if dirty else "(clean)"))
    return 0 if not survived else 1


if __name__ == "__main__":
    sys.exit(main())
