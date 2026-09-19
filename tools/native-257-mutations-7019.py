#!/usr/bin/env python3
"""native/257 — mutation battery for #7019's guards.

#7019 is a chip that stopped ageing. The awkward thing about that class is that
EVERY plausible regression of it COMPILES AND DRAWS THE RIGHT NUMBER ONCE:

  * `formatCountdown(from: date)` — the `now` parameter has a default, so
    dropping it at the call site is a valid expression that silently restores
    the defect on all five surfaces.
  * `let clock = MinuteClock.shared` — a reference without `@ObservedObject`
    reads the instant at render and subscribes to nothing.
  * a `Timer` never added to a run loop.
  * `repeats: false` — ages once, then freezes for the rest of the session.

None of those is visible to a test of the formatter, which is why the issue's
own filing note says a guard "has to assert the recomputation, not the format".
This battery is how that claim is checked rather than asserted: every mutant
below restores some version of a frozen chip, and must turn at least one NAMED
test in `ACountdownChipKeepsAgeing7019Tests` RED.

Two of them found real holes while this file was being written, and the guards
were widened before the battery was run in anger — `repeats: false` survived a
single-tick assertion, and the 60-second default period was pinned by nothing.
A mutant that survives is either a hole or an equivalence, and which one it is
is a measurement.

ONE CONTROL changes nothing and must stay GREEN: a battery that reds on
everything, a broken harness included, reads as success.

    tools/native-257-mutations-7019.py            # the whole battery
    tools/native-257-mutations-7019.py --list     # print the mutants, run nothing
    tools/native-257-mutations-7019.py --only sub # re-run one, plus the control
"""

import pathlib
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parents[1]
IOS = REPO / "ios/Bain Luck/Bain Luck"
CLOCK = IOS / "ViewModels/MinuteClock.swift"
BADGE = IOS / "Components/StatusBadge.swift"
FORMAT = IOS / "Utilities/FormattingUtilities.swift"
CARD = IOS / "Components/EventCardView.swift"
MYSTUFF = IOS / "Views/MyStuffView.swift"

TEST_CLASS = "BainLuckTests/ACountdownChipKeepsAgeing7019Tests"
# iPhone 17 Pro, disposable. NOT DD0DC456 — that one holds Alex's signed-in
# account and no battery of mine touches it.
SIM = "D2DA47A0-85F6-4BF8-AEFF-33146AE3EB05"

# (name, file, old, new, why)
MUTANTS = [
    (
        "restore the defect: drop `now:` at the call site",
        BADGE,
        "               let countdown = formatCountdown(from: date, now: clock.now) {",
        "               let countdown = formatCountdown(from: date) {",
        "#7019 ITSELF, and the reason the scan exists. `now` has a default, so "
        "this compiles, draws the correct number when the row appears, and "
        "never ages again — on Discover, Sports, My Stuff, both search rows "
        "and the team schedule at once",
    ),
    (
        "hold the clock without subscribing to it",
        BADGE,
        "    @ObservedObject var clock = MinuteClock.shared",
        "    let clock = MinuteClock.shared",
        "the other half of the same freeze: the arm reads a live instant, but "
        "nothing invalidates the view, so `body` is never re-evaluated to read "
        "it. Also compiles and also draws correctly exactly once",
    ),
    (
        "build the timer and never add it to a run loop",
        CLOCK,
        "        RunLoop.main.add(timer, forMode: .common)\n",
        "",
        "⭐ THE ONE NO SOURCE SCAN CAN SEE. Every scan in the suite passes: the "
        "property is observed, the argument is passed, the type conforms. The "
        "published instant simply never moves",
    ),
    (
        "tick once instead of repeating",
        CLOCK,
        "        let timer = Timer(timeInterval: interval, repeats: true) { [weak self] _ in",
        "        let timer = Timer(timeInterval: interval, repeats: false) { [weak self] _ in",
        "the defect delayed by one period rather than removed — the chip ages "
        "once and freezes for the rest of the session. This SURVIVED the first "
        "draft of `testTheClockPublishes…`, which waited for a single move; the "
        "second-tick assertion was written because of it",
    ),
    (
        "coarsen the default period to an hour",
        CLOCK,
        "    init(interval: TimeInterval = 60, now: Date = Date()) {",
        "    init(interval: TimeInterval = 3_600, now: Date = Date()) {",
        "every behavioural class injects its own interval, so nothing else in "
        "the file can see this. An hourly chip is stale by up to 59 minutes in "
        "the hour before kickoff — the hour the number is actually read in. "
        "SURVIVED until `testTheDefaultPeriodIsStillSixtySeconds` was added",
    ),
    (
        "make the formatter ignore the instant it was handed",
        FORMAT,
        "    let interval = date.timeIntervalSince(now)",
        "    let interval = date.timeIntervalSinceNow",
        "the parameter accepted and discarded: the signature says the string is "
        "a function of `now` and the body says otherwise, which is the hidden "
        "input the whole ship is about removing",
    ),
    (
        "default the formatter's instant to the epoch",
        FORMAT,
        "func formatCountdown(from date: Date, now: Date = Date()) -> String? {",
        "func formatCountdown(from date: Date, now: Date = Date(timeIntervalSince1970: 0)) -> String? {",
        "the compatibility half: `now` became a parameter on a function with "
        "existing callers, and the claim that none of them moved is a claim "
        "about the DEFAULT, not about the new argument",
    ),
    (
        "let a countdown outlive its kickoff",
        FORMAT,
        "    guard interval > 0 else { return nil }",
        "    guard interval > -86_400 else { return nil }",
        "the expiry half. This is why the badge kept its `if let` instead of "
        "moving the arm inside a timeline closure: the ABSENCE of a countdown "
        "is time-dependent too, and a chip that keeps counting down to a "
        "kickoff that has happened is worse than a stale one",
    ),
    (
        "stop the chip saying the words",
        BADGE,
        "                    Text(\"In \\(countdown)\")",
        "                    Text(\"\\(countdown)\")",
        "an omission a ban cannot see (#4478, #6528): a chip that prints "
        "nothing ages perfectly and tells a reader nothing",
    ),
    (
        "fix one surface privately instead",
        CARD,
        "    private var topBar: some View {",
        "    private var frozenCountdown: String? {\n"
        "        guard let commence = event.commenceTime, let date = commence.asDate else { return nil }\n"
        "        return formatCountdown(from: date)\n"
        "    }\n"
        "\n"
        "    private var topBar: some View {",
        "how the hero and the rows came to disagree in the first place — a "
        "surface given its own copy of the number, with its own idea of when "
        "'now' is. The call-site class must refuse it even though it compiles",
    ),
    (
        "move the specimen out from under the guard",
        MYSTUFF,
        "feedSection(title: \"Upcoming\", systemImage: \"calendar\"",
        "feedSection(title: \"Coming up\", systemImage: \"calendar\"",
        "anti-vacuity for the specimen pin: if My Stuff's Upcoming section can "
        "be renamed or removed without a guard noticing, the claim that this "
        "issue's photographed row is drawn by EventCardView is a memory, not a "
        "check",
    ),
    (
        "CONTROL: change nothing",
        BADGE,
        "",
        "",
        "the xcodebuild harness must be capable of GREEN",
    ),
]


def run_tests() -> tuple[bool, str]:
    proc = subprocess.run(
        [
            "xcodebuild", "test",
            "-project", str(REPO / "ios/Bain Luck/Bain Luck.xcodeproj"),
            "-scheme", "Bain Luck",
            "-destination", f"platform=iOS Simulator,id={SIM}",
            "-disableAutomaticPackageResolution",
            "-only-testing:" + TEST_CLASS,
            "OTHER_SWIFT_FLAGS=$(inherited) -Xfrontend -disable-sandbox",
        ],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    # A compile failure is a RED for a mutant and a broken harness for the
    # control; either way SAY WHICH, because "0 tests executed" and "12 tests,
    # 3 failures" are different stories and only one of them is a guard biting.
    line = ""
    for ln in proc.stdout.splitlines():
        if "Executed" in ln and "test" in ln:
            line = ln.strip()
    if not line:
        return proc.returncode == 0, "NO TEST RAN (compile failure or harness error)"
    return proc.returncode == 0, line


def main() -> int:
    if "--list" in sys.argv:
        for name, path, old, new, why in MUTANTS:
            kind = "CONTROL" if old == new else f"mutates {path.name}"
            print(f"- {name}\n    {kind}: {why}")
        return 0

    only = None
    if "--only" in sys.argv:
        only = sys.argv[sys.argv.index("--only") + 1]

    results = []
    for name, path, old, new, why in MUTANTS:
        # The CONTROL always runs: a filtered battery with no control cannot
        # tell a kill from a broken harness. Case-insensitive, because a filter
        # that silently matches nothing reports a clean battery.
        if only is not None and only.lower() not in name.lower() and old != new:
            continue
        original = path.read_text(encoding="utf-8")
        is_control = old == new

        if not is_control:
            if original.count(old) != 1:
                # A needle that does not apply reads exactly like a kill.
                # Refuse rather than grade it.
                print(
                    f"!! NEEDLE NOT FOUND for {name!r}: {original.count(old)} matches "
                    f"in {path.name}",
                    file=sys.stderr,
                )
                return 2
            path.write_text(original.replace(old, new), encoding="utf-8")

        try:
            green, summary = run_tests()
        finally:
            # Always restore, Ctrl-C included: a mutant left in the tree is a
            # defect shipped by the battery that was meant to catch it.
            path.write_text(original, encoding="utf-8")

        if is_control:
            verdict = "GREEN (correct)" if green else "RED (HARNESS BROKEN)"
            ok = green
        else:
            verdict = "SURVIVED (gap)" if green else "killed"
            ok = not green
        results.append((ok, name, verdict, summary))
        print(f"[{'ok ' if ok else 'GAP'}] {name}\n      {verdict} — {summary}")

    killed = sum(1 for ok, _, v, _ in results if ok and "killed" in v)
    controls = sum(1 for ok, _, v, _ in results if ok and "GREEN" in v)
    gaps = [r for r in results if not r[0]]
    print(f"\n{killed} killed, {controls} control(s) green, {len(gaps)} gaps")
    for _, name, verdict, summary in gaps:
        print(f"  GAP {name}: {verdict} — {summary}")
    return 1 if gaps else 0


if __name__ == "__main__":
    sys.exit(main())
