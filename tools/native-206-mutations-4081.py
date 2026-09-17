#!/usr/bin/env python3
"""native/206 — mutation battery for #4081's iOS half (CalendarDeadline).

A guard is only worth its runtime if it FAILS on the defect it names. Each
mutation below reintroduces one specific way this fix could be wrong, and names
the test case that must go red for it. A mutation that survives is a guard that
would have graded the bug as fixed.

The battery deliberately includes the two SHAPES that a naive fix takes:

  * M2 — the calendar branch never fires (the pre-fix behaviour, everything local)
  * M3 — the calendar branch ALWAYS fires (the over-correction: format everything
    in UTC, which breaks the 31,893 markets whose deadline really is an instant)

M3 is the one a battery of only calendar-date cases would miss, which is why
`test_instant_keeps_local_zone` exists as the control.

Usage:  python3 tools/native-206-mutations-4081.py [--list]
"""

import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
IOS = REPO / "ios" / "Bain Luck"
PROJECT = IOS / "Bain Luck.xcodeproj"
SCHEME = "Bain Luck"
SWIFT_FLAGS = "$(inherited) -Xfrontend -disable-sandbox"

HELPER = IOS / "Bain Luck" / "Utilities" / "CalendarDeadline.swift"
DETAIL = IOS / "Bain Luck" / "Views" / "FuturesDetailView.swift"
CARD = IOS / "Bain Luck" / "Components" / "DistributionCardView.swift"
ENT = IOS / "Bain Luck" / "Views" / "EntertainmentView.swift"

TESTCLASS = "ACalendarDeadlineKeepsItsDeclaredDay4081Tests"


class Mutation:
    def __init__(self, key, path, old, new, killer, why):
        self.key, self.path, self.old, self.new = key, path, old, new
        self.killer, self.why = killer, why


MUTATIONS = [
    Mutation(
        "M1-detail-site-reverts-to-local",
        DETAIL,
        'let text = CalendarDeadline.format(market.resolutionDate, style: .monthDayYear) {',
        'let d = market.resolutionDate?.asDate, '
        'let text = Optional(d.formatted(.dateTime.month(.abbreviated).day().year())) {',
        "test_every_resolution_deadline_renders_through_the_helper",
        "the screen the defect was photographed on stops using the rule",
    ),
    Mutation(
        "M2-calendar-branch-never-fires",
        HELPER,
        "let pattern = #\"^(\\d{4})-(\\d{2})-(\\d{2})(?:[Tt]00:00:00(?:\\.0+)?(?:[Zz]|\\+00:?00))?$\"#",
        "let pattern = #\"^(?!)$\"#",
        "test_the_ufc_heavyweight_market_keeps_december_31",
        "the pre-fix behaviour: every deadline localises, Dec 31 prints as Dec 30",
    ),
    Mutation(
        "M3-everything-is-a-calendar-date",
        HELPER,
        "let pattern = #\"^(\\d{4})-(\\d{2})-(\\d{2})(?:[Tt]00:00:00(?:\\.0+)?(?:[Zz]|\\+00:?00))?$\"#",
        "let pattern = #\"^(\\d{4})-(\\d{2})-(\\d{2}).*$\"#",
        "test_instant_keeps_local_zone",
        "THE OVER-CORRECTION — a real 3pm deadline gets dragged into the UTC branch",
    ),
    Mutation(
        "M4-any-time-counts-as-midnight",
        HELPER,
        "(?:[Tt]00:00:00(?:\\.0+)?(?:[Zz]|\\+00:?00))?$",
        "(?:[Tt]\\d{2}:\\d{2}:\\d{2}(?:\\.\\d+)?(?:[Zz]|\\+00:?00))?$",
        "test_near_misses_are_instants_not_calendar_dates",
        "one second past midnight is no longer told from midnight",
    ),
    Mutation(
        "M5-midnight-in-another-zone-counts",
        HELPER,
        "(?:[Zz]|\\+00:?00))?$",
        "(?:[Zz]|[+-]\\d{2}:?\\d{2}))?$",
        "test_near_misses_are_instants_not_calendar_dates",
        "midnight in +05:00 is a different instant and must stay local",
    ),
    Mutation(
        "M6-utc-formatting-falls-back-to-ambient",
        HELPER,
        "return formatter(style.template, zone: utcZone).string(from: date)",
        "return formatter(style.template, zone: localZone).string(from: date)",
        "test_calendar_date_is_zone_independent_by_construction",
        "the declared day is round-tripped through the reader's zone after all",
    ),
    Mutation(
        # The two-template split is the only place a style's branches differ, and
        # it can be wrong in either direction. M8 loses a real deadline's hour;
        # M9 invents an hour for a date that declared none.
        "M8-instant-loses-its-hour",
        HELPER,
        "case .weekdayMonthDayTime: return \"EEE, MMM d 'at' h:mm a\"\n            default: return template",
        "default: return template",
        "test_weekdayMonthDayTime_omits_the_hour_only_for_a_calendar_date",
        "a real 3pm deadline stops saying 3pm",
    ),
    Mutation(
        "M9-calendar-date-invents-midnight",
        HELPER,
        "return formatter(style.template, zone: utcZone).string(from: date)",
        "return formatter(style.instantTemplate, zone: utcZone).string(from: date)",
        "test_weekdayMonthDayTime_omits_the_hour_only_for_a_calendar_date",
        "a declared calendar date prints 'at 12:00 AM' — a precision it never had",
    ),
    Mutation(
        # The source scan must read CODE, not the prose this fix wrote. If the
        # strip is removed, a comment naming the helper satisfies the claim and
        # the scan is vacuous from birth.
        "M7-scan-satisfied-by-its-own-comment",
        CARD,
        "guard let text = CalendarDeadline.format(data.resolutionDate, style: .monthDay) else { return nil }\n        return \"Resolves \\(text)\"",
        "// this row used to go through CalendarDeadline.format and no longer does\n"
        "        guard let rd = data.resolutionDate, let d = rd.asDate else { return nil }\n"
        "        let f = DateFormatter(); f.dateFormat = \"MMM d\"\n"
        "        return \"Resolves \\(f.string(from: d))\"",
        "test_every_resolution_deadline_renders_through_the_helper",
        "a site reverts to local formatting while its DOC COMMENT still names the helper",
    ),
    Mutation(
        # The second batch of call sites was found by sweeping the whole target,
        # not the specimen's neighbourhood. The scan list has to actually cover
        # them, or the sweep bought nothing.
        "M10-second-batch-site-reverts",
        ENT,
        "CalendarDeadline.format(iso, style: .monthDay) ?? iso",
        "{ let f = ISO8601DateFormatter()\n"
        "          f.formatOptions = [.withFullDate, .withDashSeparatorInDate]\n"
        "          guard let d = f.date(from: String(iso.prefix(10))) else { return iso }\n"
        "          let o = DateFormatter(); o.dateFormat = \"MMM d\"\n"
        "          return o.string(from: d) }()",
        "test_every_resolution_deadline_renders_through_the_helper",
        "the entertainment cards go back to prefix(10)-then-localise",
    ),
]


def run_tests(udid):
    cmd = [
        "xcodebuild", "test",
        "-project", str(PROJECT),
        "-scheme", SCHEME,
        "-destination", f"id={udid}",
        f"OTHER_SWIFT_FLAGS={SWIFT_FLAGS}",
        "-only-testing:BainLuckTests/" + TESTCLASS,
    ]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=1500)
    return p.returncode, p.stdout + p.stderr


def failing_cases(log):
    return sorted(set(re.findall(r"test_[A-Za-z0-9_]+(?=\]' failed)", log)))


def booted_udid():
    out = subprocess.run(["xcrun", "simctl", "list", "devices", "booted"],
                         capture_output=True, text=True).stdout
    m = re.search(r"\(([0-9A-F-]{36})\) \(Booted\)", out)
    if not m:
        sys.exit("no booted simulator — boot one first")
    return m.group(1)


def main():
    if "--list" in sys.argv:
        for m in MUTATIONS:
            print(f"{m.key:38s} kills-> {m.killer}")
        return 0

    udid = booted_udid()
    print(f"simulator: {udid}")
    print(f"only-testing: BainLuckTests/{TESTCLASS}\n")

    rc, log = run_tests(udid)
    if rc != 0:
        print("BASELINE IS RED — fix that before mutating.")
        print("\n".join(log.splitlines()[-25:]))
        return 2
    print("baseline: GREEN\n")

    killed = survived = 0
    for m in MUTATIONS:
        src = m.path.read_text()
        if m.old not in src:
            print(f"  SKIP  {m.key} — anchor not found in {m.path.name}")
            survived += 1
            continue
        # `src` IS the backup. The first cut copied the file to a
        # `tempfile.mktemp` path, which CodeQL correctly flags as insecure (the
        # name is handed out and then opened, so the window between the two is
        # somebody else's to fill) — and the copy bought nothing, because the
        # pre-mutation bytes are already in memory two lines up.
        try:
            m.path.write_text(src.replace(m.old, m.new, 1))
            rc, log = run_tests(udid)
            fails = failing_cases(log)
            if rc != 0 and m.killer in fails:
                print(f"  KILLED   {m.key}")
                print(f"           by {m.killer} — {m.why}")
                killed += 1
            elif rc != 0:
                print(f"  KILLED*  {m.key} (red, but NOT by its named case)")
                print(f"           expected {m.killer}, got {fails or 'a compile error'}")
                killed += 1
            else:
                print(f"  SURVIVED {m.key}  <-- {m.why}")
                survived += 1
        finally:
            m.path.write_text(src)

    print(f"\n{killed}/{len(MUTATIONS)} mutants killed, {survived} survived")
    return 0 if survived == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
