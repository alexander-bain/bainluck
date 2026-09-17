#!/usr/bin/env python3
"""native/207 — mutation battery for #6718 (a chart marker sits on an observed time).

Each mutant rewrites the SHIPPED Swift and asks whether
`AChartMarkerSitsOnAnObservedTime6718Tests` notices. A mutant the guard does not
notice is a hole in the guard, not a curiosity.

═══ WHY THIS BATTERY IS SHAPED THE WAY IT IS ═══

#6718's fix is a DELETION, and a deletion is the hardest thing to guard. There is
no new function to call: `extractPeriodMarkers` is `private` on a SwiftUI `View`
and returns a `private struct`, so the guard is source scans plus a verbatim
control. Source scans have two characteristic ways of being worthless, and both
are graded here rather than asserted:

  * **A mutant that does not COMPILE is killed by the compiler, not by the scan.**
    That is a false kill, and it is the trap this battery could most easily fall
    into: the obvious way to reinstate the defect is to call
    `inferFirstPeriodLabel`, which no longer exists, so the mutant would never
    build and the battery would report a clean sheet having tested nothing.
    EVERY defect mutant below is written to compile. M1-M4 reinstate the defect
    in forms Swift accepts.

  * **A scan can be satisfied by the file's own prose.** The subject documents
    the defect it removed, quoting `gameStartDate` and `firstSeen.insert(`
    verbatim so the next reader knows what used to be there. `code(at:)` strips
    comment lines for exactly this reason. E2 puts the forbidden token in a
    COMMENT and requires the guard to stay GREEN — if that mutant is "killed",
    the strip is broken and every scan in the file is grading prose.

The two negative scans are deliberately independent, and M2/M3 prove each one
carries its own weight: M2 evades the `firstSeen.insert(` scan and must die on
`gameStartDate`; M3 evades the `gameStartDate` scan by reaching for
`commenceTime?.asDate` directly and must die on the insert. A battery of only
M1 would grade a guard with one live arm and one decorative one as perfect.

Run with `python3 -u`: `print()` to a redirected file is block-buffered, so a
long battery looks hung for most of it.

Four things this battery does on purpose, inherited from native/201:

  * **A mutant that did not apply reads exactly like a kill.** A missing needle
    is reported NEEDLE-NOT-FOUND and graded as a FAILURE of the battery.
  * **A needle that matches more than once grades code nobody chose.** Every
    needle is asserted unique in the file before it is used.
  * **The dirty-tree guard is SCOPED to the files it mutates**, with
    `--untracked-files=no` — a bare porcelain refuses on the lane's
    `artifacts/` directory, which exists every session.
  * Restores with `git checkout HEAD -- <file>`, never `git checkout -- <file>`:
    the latter reads the INDEX, so a stale `git add` silently reverts newer work.
    COMMIT THE FIX BEFORE RUNNING THIS — `HEAD` is what it restores to.

Usage:  python3 -u tools/native-207-mutations-6718.py
"""

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

VIEW = "ios/Bain Luck/Bain Luck/Components/OddsChartView.swift"
FILES = [VIEW]

PROJECT = ROOT / "ios/Bain Luck/Bain Luck.xcodeproj"
SCHEME = "Bain Luck"
SWIFT_FLAGS = "$(inherited) -Xfrontend -disable-sandbox"
TEST_CLASS = "BainLuckTests/AChartMarkerSitsOnAnObservedTime6718Tests"

# The anchor every reinstatement is grafted in front of: the half-time block,
# which is the next thing in the function after the deleted code.
ANCHOR = '        if firstSeen.isEmpty, !seenLabels.contains("HT") {'

# The whole half-time block, needed by M5 to remove a POSITIVE arm's subject.
HALVES_BLOCK = '''        if firstSeen.isEmpty, !seenLabels.contains("HT") {
            let inferred = HalvesFromGap.markers(
                sportKey: sportKey,
                espnDates: (history.espnHistory ?? []).compactMap { $0.timestamp.asDate }
            )
            if !inferred.isEmpty {
                firstSeen = inferred
                seenLabels = Set(inferred.map(\\.label))
            }
        }
'''

# ── The defect, reinstated in four shapes that all compile ──────────────────

# M1: the original, rewritten without the deleted helper so it builds.
M1_DEFECT = '''        if isGameStarted, let startDate = gameStartDate, !firstSeen.isEmpty {
            if let first = firstSeen.first?.label, first.hasPrefix("Q"), first != "Q1",
               !seenLabels.contains("Q1") {
                firstSeen.insert(("Q1", startDate), at: 0)
            }
        }
'''

# M2: places the marker by APPENDING, so the `firstSeen.insert(` scan never
# fires. Only the `gameStartDate` scan can see this one.
M2_DEFECT = '''        if isGameStarted, let startDate = gameStartDate, !firstSeen.isEmpty {
            if !seenLabels.contains("Q1") {
                firstSeen.append(("Q1", startDate))
                seenLabels.insert("Q1")
            }
        }
'''

# M3: reaches past the property to the raw wire field, so the `gameStartDate`
# scan never fires. Only the `firstSeen.insert(` scan can see this one.
M3_DEFECT = '''        if isGameStarted, let startDate = commenceTime?.asDate, !firstSeen.isEmpty {
            if !seenLabels.contains("Q1") {
                firstSeen.insert(("Q1", startDate), at: 0)
            }
        }
'''

# M4: the helper comes back, unused. An unused `private func` is a warning, not
# an error, so this compiles — and only the whole-file name scan sees it.
M4_HELPER = '''    private func inferFirstPeriodLabel(from labels: [String]) -> String? {
        guard let first = labels.first else { return nil }
        if first.hasPrefix("Q") && first != "Q1" { return "Q1" }
        return nil
    }

'''

# (name, file, needle, replacement, what a reader would see if this shipped)
MUTANTS = [
    (
        "M1 the original defect, reinstated (compiles)",
        VIEW,
        ANCHOR,
        M1_DEFECT + ANCHOR,
        "a Q1 chip reappears at the SCHEDULED kickoff on every late-attached game",
    ),
    (
        "M2 same defect, APPENDED — evades the insert scan",
        VIEW,
        ANCHOR,
        M2_DEFECT + ANCHOR,
        "same invented marker; proves the `gameStartDate` scan is load-bearing on its own",
    ),
    (
        "M3 same defect via `commenceTime?.asDate` — evades the gameStartDate scan",
        VIEW,
        ANCHOR,
        M3_DEFECT + ANCHOR,
        "same invented marker; proves the `firstSeen.insert(` scan is load-bearing on its own",
    ),
    (
        "M4 the deleted helper returns, unused",
        VIEW,
        "    private func normalizePeriodLabel(_ raw: String) -> String {",
        M4_HELPER + "    private func normalizePeriodLabel(_ raw: String) -> String {",
        "the inference rule is back in the file, one call site away from being live again",
    ),
    (
        "M5 the half-time inference is deleted (attacks a POSITIVE arm)",
        VIEW,
        HALVES_BLOCK,
        "",
        "soccer charts silently lose 1H/HT/2H — the guard must require what it keeps, "
        "not only forbid what it removed",
    ),
]

# Mutants that MUST SURVIVE. A guard that kills these reads cosmetics as
# contract, and the next legitimate edit to this function fails for no reason.
EQUIVALENT = [
    (
        "E1 a purely syntactic rewrite of the sort",
        VIEW,
        "let sorted = firstSeen.sorted { $0.date < $1.date }",
        "let sorted = firstSeen.sorted(by: { $0.date < $1.date })",
    ),
    (
        "E2 THE FORBIDDEN TOKENS, IN A COMMENT (proves the strip works)",
        VIEW,
        ANCHOR,
        "        // gameStartDate / firstSeen.insert( / inferFirstPeriodLabel\n" + ANCHOR,
    ),
]


def udid() -> str:
    listing = subprocess.run(
        ["xcrun", "simctl", "list", "devices", "available"],
        capture_output=True, text=True, check=True,
    ).stdout
    for line in listing.splitlines():
        if re.match(r"^\s+iPhone ", line):
            found = re.search(r"\(([0-9A-Fa-f-]{36})\)", line)
            if found:
                return found.group(1)
    raise SystemExit("NO iPhone SIMULATOR AVAILABLE — the battery cannot run.")


def run_guard(device: str) -> tuple[bool, bool]:
    """`(built, green)` for the one test class.

    gotcha #124: read the exit code's VALUE. 65 is 'the tests failed', which is
    this battery working. 70/127/137/143 mean xcodebuild never ran the tests at
    all, and grading those as a kill would manufacture a clean sheet.

    `xcodebuild test` also exits 65 when the BUILD failed, which is a different
    thing entirely: a mutant killed by the type checker says nothing about the
    guard. The two are told apart by the banner xcodebuild prints, so this costs
    no extra build — a separate `build-for-testing` pass would double the
    battery's runtime to learn the same fact.
    """
    result = subprocess.run(
        ["xcodebuild", "test",
         "-project", str(PROJECT), "-scheme", SCHEME,
         "-destination", f"id={device}",
         "-only-testing:" + TEST_CLASS,
         f"OTHER_SWIFT_FLAGS={SWIFT_FLAGS}"],
        cwd=ROOT, capture_output=True, text=True,
    )
    if result.returncode not in (0, 65):
        raise SystemExit(
            f"xcodebuild exited {result.returncode} — the gate never ran, so nothing "
            f"here can be graded.\n{result.stdout[-3000:]}"
        )
    built = "** TEST BUILD FAILED **" not in result.stdout
    return built, result.returncode == 0


def restore() -> None:
    subprocess.run(["git", "checkout", "HEAD", "--", *FILES], cwd=ROOT, check=True)


def main() -> int:
    dirty = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=no", "--", *FILES],
        cwd=ROOT, capture_output=True, text=True,
    ).stdout.strip()
    if dirty:
        print(f"REFUSING: a mutated file has uncommitted changes — commit first.\n{dirty}")
        return 2

    device = udid()
    print(f"simulator: {device}\n", flush=True)

    originals = {f: (ROOT / f).read_text() for f in FILES}

    print("BASE: ", end="", flush=True)
    base_built, base_green = run_guard(device)
    if not (base_built and base_green):
        print("RED before any mutant. The battery cannot grade anything.")
        return 2
    print("GREEN\n", flush=True)

    killed, survived, unapplied = [], [], []

    for name, target, needle, replacement, harm in MUTANTS:
        source = originals[target]
        hits = source.count(needle)
        if hits == 0:
            unapplied.append(f"{name} (needle absent)")
            print(f"  NEEDLE NOT FOUND  {name}", flush=True)
            continue
        if hits > 1:
            unapplied.append(f"{name} (needle matches {hits}x)")
            print(f"  NEEDLE AMBIGUOUS  {name} — matches {hits} places, grades code nobody chose",
                  flush=True)
            continue
        (ROOT / target).write_text(source.replace(needle, replacement, 1))
        built, green = run_guard(device)
        restore()

        # The whole point: a kill only counts if the mutant BUILT.
        if not built:
            unapplied.append(f"{name} (did not compile — the compiler killed it, not the guard)")
            print(f"  DID NOT COMPILE   {name}  <- FALSE KILL, rewrite the mutant", flush=True)
            continue

        if green:
            survived.append((name, harm))
            print(f"  SURVIVED          {name}\n                    -> {harm}", flush=True)
        else:
            killed.append(name)
            print(f"  killed            {name}", flush=True)

    print(flush=True)
    for name, target, needle, replacement in EQUIVALENT:
        source = originals[target]
        if source.count(needle) != 1:
            unapplied.append(f"{name} (needle not unique)")
            print(f"  NEEDLE NOT FOUND  {name}", flush=True)
            continue
        (ROOT / target).write_text(source.replace(needle, replacement, 1))
        built, green = run_guard(device)
        restore()
        if not built:
            unapplied.append(f"{name} (did not compile)")
            print(f"  DID NOT COMPILE   {name}", flush=True)
            continue
        print(f"  {'survived (correct)' if green else 'KILLED (over-tight — BAD)'}  {name}",
              flush=True)
        if not green:
            survived.append((name, "the guard reads cosmetics as contract"))

    print(f"\n{len(killed)}/{len(MUTANTS)} defect mutants killed.")
    if unapplied:
        print(f"BATTERY FAILURE — {len(unapplied)} mutant(s) never graded: {unapplied}")
        return 2
    if survived:
        print("SURVIVORS — the guard has holes:")
        for name, harm in survived:
            print(f"  {name}: {harm}")
        return 1
    print("No survivors.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
