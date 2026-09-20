#!/usr/bin/env python3
"""native/261 — mutation run for #6666, golf dates a day early west of UTC.

THE SHIP. A tournament's `start_date` is a DATE; the midnight on it is an
artifact of `f"{t.start_date}T00:00:00+00:00"` in `app/routes/golf.py`. Read in
the reader's zone that instant is 17:00 the previous day, so every golf date in
the app — hero, tour rows, tournament page — printed a day early anywhere west
of UTC, and the round strip beside it counted from the same wrong day.

The battery is split the way this ship fails:

  * DISCRIMINATOR mutants (1-5). The whole fix is one question — is this wire
    value a declared DAY or a real INSTANT — asked through `CalendarDeadline`.
    Mutant 2 answers "instant" for everything (the defect) and mutant 3 answers
    "day" for everything (the over-fix, which is a different wrong date on a
    different population). A battery that only had the first would grade the
    second as perfect.

  * DAY-ARITHMETIC mutants (6-9). A round number is elapsed days between two
    CALENDAR DAYS, not between two instants. Mutant 8 is the original
    arithmetic, restored.

  * CALL-SITE mutants (10-12). 🔴 THESE ARE THE ONES THAT MATTER. Every mutant
    above can be killed by a suite that never touches the card, and a pair of
    perfect helpers the hero does not call is precisely the state this file's
    guards were in before `currentRound`/`formattedDateRange` were made
    reachable at a stated instant. Mutant 11 is the subtlest thing here: it
    reads `Date()` instead of the injected instant, which the "final round"
    card test cannot see today — only the "evening before" one can.

A mutant that SURVIVES is a hole in the guard suite, not a curiosity. A mutant
whose anchor does not match is a NON-RESULT and is reported as one: a refused
patch runs the unmutated tree and prints a green indistinguishable from an
unkillable mutant.

Runs only from this lane's own worktree; every path is absolute.

Usage:  python3 -u tools/native-261-mutations-6666.py [--list] [--only <substr>]
"""
import subprocess, sys, pathlib, signal, atexit

WORKTREE = pathlib.Path("/Users/bain/bainluck-dev/native")
ROOT = WORKTREE / "ios/Bain Luck"
TEXT = ROOT / "Bain Luck/Utilities/TextFormatting.swift"
DEADLINE = ROOT / "Bain Luck/Utilities/CalendarDeadline.swift"
HERO = ROOT / "Bain Luck/Components/TournamentHeroCard.swift"
SIM = "D2DA47A0-85F6-4BF8-AEFF-33146AE3EB05"

# ── anchors, verbatim ────────────────────────────────────────────────────────

RANGE_BODY = """    let startDay = CalendarDeadline.displayDay(start, localZone: localZone)
    let endDay = CalendarDeadline.displayDay(end, localZone: localZone)
    let startText = CalendarDeadline.format(start, style: .monthDay, localZone: localZone)
    let endText = CalendarDeadline.format(end, style: .monthDay, localZone: localZone)

    switch (startDay, endDay) {
    case let (s?, e?):
        guard let startText, let endText else { return startText ?? endText }
        if s.year == e.year && s.month == e.month {
            // "Sep 24-27"
            return "\\(startText)\\u{2013}\\(e.day)"
        }
        // "Sep 24 - Oct 1"
        return "\\(startText) \\u{2013} \\(endText)"
    case (_?, nil):
        return startText
    case (nil, _?):
        return endText
    case (nil, nil):
        return nil
    }"""

# The pre-fix implementation, restored verbatim from 29c73aa5b.
RANGE_BODY_REVERTED = """    let startDate = parseFlexibleDate(start)
    let endDate = parseFlexibleDate(end)

    switch (startDate, endDate) {
    case let (s?, e?):
        let cal = Calendar.current
        let sameMonth = cal.isDate(s, equalTo: e, toGranularity: .month)
            && cal.isDate(s, equalTo: e, toGranularity: .year)
        if sameMonth {
            return "\\(_monthDay.string(from: s))\\u{2013}\\(_dayOnly.string(from: e))"
        }
        return "\\(_monthDay.string(from: s)) \\u{2013} \\(_monthDay.string(from: e))"
    case let (s?, nil):
        return _monthDay.string(from: s)
    case let (nil, e?):
        return _monthDay.string(from: e)
    case (nil, nil):
        return nil
    }"""

DISPLAY_DAY_DECLARED = """        if let declared = declaredDay(raw) { return declared }
        guard let date = raw.asDate else { return nil }"""

DISPLAY_DAY_ZONE = "        cal.timeZone = localZone"

SAME_MONTH = "        if s.year == e.year && s.month == e.month {"
SAME_MONTH_END_DAY = '            return "\\(startText)\\u{2013}\\(e.day)"'

ROUND_WINDOW = """    guard let daysSinceStart = backendDayOffset(from: start, to: now, calendar: calendar),
          daysSinceStart >= 0, daysSinceStart < roundCount
    else { return nil }"""

OFFSET_BODY = """    guard let day = CalendarDeadline.displayDay(raw, localZone: calendar.timeZone),
          let named = calendar.date(
              from: DateComponents(year: day.year, month: day.month, day: day.day)
          )
    else { return nil }
    return calendar.dateComponents(
        [.day],
        from: calendar.startOfDay(for: named),
        to: calendar.startOfDay(for: now)
    ).day"""

# The pre-fix arithmetic: two instants, subtracted.
OFFSET_BODY_REVERTED = """    guard let startDate = parseFlexibleDate(raw) else { return nil }
    return calendar.dateComponents([.day], from: startDate, to: now).day"""

OFFSET_IGNORES_SEAM = OFFSET_BODY.replace("calendar.", "Calendar.current.").replace(
    "localZone: Calendar.current.timeZone", "localZone: Calendar.current.timeZone")

HERO_ROUND = "        tournamentRoundNumber(start: tournament.startDate, now: now)"
HERO_RANGE = "        formatDateRange(start: tournament.startDate, end: tournament.endDate)"

MUTANTS = [
    ("1-the-range-fix-reverted", TEXT, RANGE_BODY, RANGE_BODY_REVERTED, 1,
     "THE SHIP'S RANGE HALF, GONE. This is the exact text that was on master this morning and that "
     "printed 'Sep 16-19' on a tournament being played that day"),

    ("2-every-value-is-treated-as-an-instant", DEADLINE, DISPLAY_DAY_DECLARED,
     "        guard let date = raw.asDate else { return nil }", 1,
     "the discriminator always answers 'instant', so a declared day is read in the reader's zone "
     "again — the defect, reintroduced one layer down where the range text still looks right and "
     "only the DAY INTEGERS are wrong, which prints 'Sep 17-19'"),

    ("3-every-value-is-treated-as-a-declared-day", DEADLINE, DISPLAY_DAY_ZONE,
     "        cal.timeZone = TimeZone(secondsFromGMT: 0)!", 1,
     "THE OVER-FIX. 'render everything in UTC' fixes the 212 golf dates and breaks every real "
     "instant on the other side of it — an evening kickoff moves a day LATE. Without a control "
     "this grades as a perfect fix"),

    ("4-a-year-apart-counts-as-the-same-month", TEXT, SAME_MONTH,
     "        if s.month == e.month {", 1,
     "two tournaments a year apart print as one four-day range: 'Sep 17-20' for 2026-09-17 to "
     "2027-09-20. A plausible string, which is the dangerous kind"),

    ("5-the-range-ends-where-it-started", TEXT, SAME_MONTH_END_DAY,
     '            return "\\(startText)\\u{2013}\\(s.day)"', 1,
     "'Sep 17-17' — the same-month arm prints the start day twice, so every multi-day tournament "
     "reads as a one-day event"),

    ("6-a-fifth-round", TEXT, ROUND_WINDOW,
     ROUND_WINDOW.replace("daysSinceStart < roundCount", "daysSinceStart <= roundCount"), 1,
     "the strip stays lit the day AFTER the tournament, showing a round nobody played"),

    ("7-a-round-before-the-tournament", TEXT, ROUND_WINDOW,
     ROUND_WINDOW.replace("daysSinceStart >= 0, ", ""), 1,
     "a negative offset becomes a round number, so the strip lights before the first tee — the "
     "original defect's most visible symptom"),

    ("8-the-round-counts-elapsed-hours-again", TEXT, OFFSET_BODY, OFFSET_BODY_REVERTED, 1,
     "THE ORIGINAL ARITHMETIC. Two instants subtracted: west of UTC the round rolls over at 17:00 "
     "local, lighting R1 the evening before and dropping the strip on the evening of the final"),

    ("9-the-injected-calendar-is-ignored", TEXT, OFFSET_BODY, OFFSET_IGNORES_SEAM, 1,
     "the seam is decoration: the rule always answers for whatever zone the process happens to be "
     "in, so every guard that pins a zone is vacuous and only the machine the suite ran on was "
     "ever tested"),

    ("10-the-card-does-its-own-arithmetic-again", HERO, HERO_ROUND,
     "        guard let startDate = parseFlexibleDate(tournament.startDate) else { return nil }\n"
     "        let daysSinceStart = Calendar.current.dateComponents([.day], from: startDate, to: now).day ?? 0\n"
     "        guard daysSinceStart >= 0 && daysSinceStart < 4 else { return nil }\n"
     "        return daysSinceStart + 1", 1,
     "THE MUTANT THIS FILE EXISTS FOR: the helper is perfect and the card ignores it. Mutants 6-9 "
     "are all killed by a suite that never builds a card"),

    ("11-the-card-reads-the-wall-clock", HERO, HERO_ROUND,
     "        tournamentRoundNumber(start: tournament.startDate, now: Date())", 1,
     "the injected instant is dropped, so every card guard silently asserts against TODAY — green "
     "this week, and a different answer every day of the tournament. The 'final round' card test "
     "cannot see this one; only the 'evening before' test can"),

    ("12-the-hero-dates-both-ends-from-the-end", HERO, HERO_RANGE,
     "        formatDateRange(start: tournament.endDate, end: tournament.endDate)", 1,
     "the card's own call passes the wrong field and prints 'Sep 20' for a four-day tournament — "
     "the free function is still perfect and still tested"),
]

XCB = ["xcodebuild", "test",
       "-project", str(ROOT / "Bain Luck.xcodeproj"),
       "-scheme", "Bain Luck",
       "-destination", f"platform=iOS Simulator,id={SIM}",
       "-disableAutomaticPackageResolution",
       "-collect-test-diagnostics", "never",
       "-only-testing:BainLuckTests/AGolfTournamentKeepsItsDeclaredDays6666Tests",
       "-only-testing:BainLuckTests/ACalendarDeadlineKeepsItsDeclaredDay4081Tests",
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
    print("\ntree on exit (expect clean — the ship is committed):")
    print("  " + (dirty.replace("\n", "\n  ") if dirty else "(clean)"))
    return 0 if not survived else 1


if __name__ == "__main__":
    sys.exit(main())
