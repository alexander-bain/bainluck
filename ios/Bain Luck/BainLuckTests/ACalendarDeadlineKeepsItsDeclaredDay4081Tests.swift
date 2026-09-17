import XCTest
@testable import Bain_Luck

/// #4081 (iOS half) — A "BY END OF <PERIOD>" MARKET RENDERED ITS DEADLINE A DAY EARLY.
///
/// Found on a D48 mystery-shop of the app, 2026-09-17: `bainluck://futures/114175`,
/// "Who will be UFC Heavyweight champion at the end of 2026?", drew
/// **"Resolves Dec 30, 2026"** over a wire value of `2026-12-31T00:00:00+00:00`.
/// A card whose title says "end of 2026" and whose deadline says Dec 30
/// contradicts itself on the one fact the reader needs.
///
/// Sized on production the same morning: **2,887 of 34,780** open futures markets
/// with a resolution date carry exactly `00:00:00` UTC, so the whole class lands a
/// day early for every reader west of UTC.
///
/// ## WHY THESE ASSERTIONS AND NOT THE OBVIOUS ONE
///
/// 🔴 THE OBVIOUS TEST IS VACUOUS HERE. The shift is `local − UTC`, and a test
/// environment running UTC has a shift of exactly zero: "renders Dec 31" is green
/// on the fix AND green on the bug. That is gotcha #44 wearing a timezone. So
/// every calendar-date case below pins an explicit WESTERN zone through
/// `localZone:` — the parameter exists for this — and would fail against the old
/// `Text(date, format:)` behaviour regardless of where the suite runs.
///
/// 🔴 THE CONTROL IS THE POINT. `instant_keeps_local_zone` is what stops the fix
/// being "format everything in UTC", which would swap one wrong date for another
/// on the 31,893 markets whose resolution really is an instant. A battery of only
/// calendar-date cases would grade that regression as perfect.
final class ACalendarDeadlineKeepsItsDeclaredDay4081Tests: XCTestCase {

    /// Pacific. UTC−8 in December, so a UTC-midnight instant lands on the
    /// PREVIOUS day here — the zone the defect was reported in.
    private let pacific = TimeZone(identifier: "America/Los_Angeles")!

    // MARK: - The rule

    /// THE PRODUCTION SPECIMEN, verbatim off the wire.
    func test_the_ufc_heavyweight_market_keeps_december_31() {
        XCTAssertEqual(
            CalendarDeadline.format("2026-12-31T00:00:00+00:00", style: .monthDayYear, localZone: pacific),
            "Dec 31, 2026",
            "market 114175 resolves at the end of 2026; Dec 30 is the defect this fixes"
        )
    }

    /// THE CONTROL. A real intraday deadline is an instant and must still be told
    /// in the reader's time. Without this the whole fix could be "always UTC".
    func test_instant_keeps_local_zone() {
        // 2026-12-31 03:00Z is Dec 30, 7:00pm in Pacific. The reader's day is the
        // right answer for a real closing time, so this MUST read Dec 30.
        XCTAssertEqual(
            CalendarDeadline.format("2026-12-31T03:00:00+00:00", style: .monthDayYear, localZone: pacific),
            "Dec 30, 2026",
            "a real instant keeps local conversion — shifting everything to UTC is the other bug"
        )
        XCTAssertNil(CalendarDeadline.declaredDay("2026-12-31T03:00:00+00:00"))
    }

    func test_bare_calendar_date_keeps_its_day() {
        XCTAssertEqual(
            CalendarDeadline.format("2026-12-31", style: .monthDayYear, localZone: pacific),
            "Dec 31, 2026"
        )
    }

    /// The leap-day case web's C270 P1 names: 2028-02-29 printed "Feb 28".
    func test_leap_day_keeps_its_day() {
        XCTAssertEqual(
            CalendarDeadline.format("2028-02-29T00:00:00+00:00", style: .monthDay, localZone: pacific),
            "Feb 29"
        )
    }

    /// Serialisers differ on the fractional part; all-zero fractions are still
    /// midnight, and `Z` and `+00:00` are the same zone.
    func test_midnight_spellings_are_all_calendar_dates() {
        for raw in [
            "2026-12-31T00:00:00Z",
            "2026-12-31T00:00:00+00:00",
            "2026-12-31T00:00:00+0000",
            "2026-12-31T00:00:00.000000+00:00",
            "2026-12-31t00:00:00z",
        ] {
            XCTAssertNotNil(CalendarDeadline.declaredDay(raw), "\(raw) is midnight UTC")
            XCTAssertEqual(
                CalendarDeadline.format(raw, style: .monthDayYear, localZone: pacific),
                "Dec 31, 2026",
                "\(raw) should keep its declared day"
            )
        }
    }

    /// THE NEAR-MISSES. Each is one character away from the shape above and is an
    /// instant — a discriminator that accepted these would drag the other 31,893
    /// markets into the UTC branch.
    func test_near_misses_are_instants_not_calendar_dates() {
        for raw in [
            "2026-12-31T00:00:00.5Z",       // half a second past midnight
            "2026-12-31T00:00:01Z",         // one second past
            "2026-12-31T00:00:00+05:00",    // midnight somewhere else, not UTC
            "2026-12-31T00:00:00-05:00",
            "2026-12-31T12:00:00Z",
            "not a date",
            "",
        ] {
            XCTAssertNil(CalendarDeadline.declaredDay(raw), "\(raw) is not a UTC-midnight calendar date")
        }
    }

    func test_unparseable_and_nil_render_nothing() {
        XCTAssertNil(CalendarDeadline.format(nil, style: .monthDay))
        XCTAssertNil(CalendarDeadline.format("not a date", style: .monthDay))
        XCTAssertNil(CalendarDeadline.format("2026-13-45", style: .monthDay))
    }

    /// The calendar-date branch must not consult the ambient zone AT ALL — that
    /// is the construction rule, not just an outcome. Same input, four zones
    /// spanning the date line, one answer.
    func test_calendar_date_is_zone_independent_by_construction() {
        let answers = ["America/Los_Angeles", "UTC", "Asia/Tokyo", "Pacific/Kiritimati"].map {
            CalendarDeadline.format("2026-12-31T00:00:00+00:00", style: .monthDayYear,
                                    localZone: TimeZone(identifier: $0)!)
        }
        XCTAssertEqual(Set(answers), ["Dec 31, 2026"], "the declared day cannot depend on where it is read")
    }

    // MARK: - A calendar date has no hour

    /// `.weekdayMonthDayTime` is the only style whose two branches differ, and the
    /// difference is the point: a declared calendar date declares no hour, so
    /// printing "at 12:00 AM" would invent a precision the wire value never had —
    /// the same lie as the wrong day, in a smaller font. A real instant keeps its
    /// time, which is why the style exists at all.
    func test_weekdayMonthDayTime_omits_the_hour_only_for_a_calendar_date() {
        XCTAssertEqual(
            CalendarDeadline.format("2026-12-31T00:00:00+00:00", style: .weekdayMonthDayTime, localZone: pacific),
            "Thu, Dec 31",
            "a declared calendar date has no time of day to print"
        )
        XCTAssertEqual(
            CalendarDeadline.format("2026-12-31T20:00:00+00:00", style: .weekdayMonthDayTime, localZone: pacific),
            "Thu, Dec 31 at 12:00 PM",
            "a real instant keeps both its local day and its hour"
        )
    }

    /// The weekday is computed in the DECLARED day's calendar, not the reader's.
    /// Off-by-one here would print the right date beside the wrong weekday.
    func test_weekday_matches_the_declared_day() {
        XCTAssertEqual(
            CalendarDeadline.format("2026-12-31T00:00:00+00:00", style: .weekdayMonthDay, localZone: pacific),
            "Thu, Dec 31"
        )
    }

    // MARK: - The call sites

    /// The rule is only worth having if the screens use it. A source scan for the
    /// same reason #6018's was: these deadlines are drawn inside large `ScrollView`
    /// bodies no test can instantiate headlessly, and CI compiles no Swift (#4302).
    ///
    /// COMMENTS ARE STRIPPED FIRST. The prose this fix just wrote names both the
    /// helper and the field, so an unstripped scan would be satisfied by its own
    /// documentation and would be vacuous from birth.
    func test_every_resolution_deadline_renders_through_the_helper() throws {
        let root = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()   // BainLuckTests
            .deletingLastPathComponent()   // Bain Luck
            .appendingPathComponent("Bain Luck")

        // Each site drew a resolution deadline through a local-zone formatter.
        let sites = [
            "Views/FuturesDetailView.swift",
            "Components/DistributionCardView.swift",
            "Components/ComparisonCardView.swift",
            "Components/HeatMapCardView.swift",
            "Components/FuturesBrowseComponents.swift",
            // Found by re-sweeping `resolutionDate` across the whole target after
            // the first five were converted — the first list was the specimen's
            // neighbourhood, not the class.
            "Components/RelatedFuturesView.swift",
            "Views/EntertainmentView.swift",
            "Views/DiscoverLabelingView.swift",
        ]

        for site in sites {
            let url = root.appendingPathComponent(site)
            let source = try String(contentsOf: url, encoding: .utf8)
            let code = Self.strippingComments(source)

            XCTAssertTrue(
                code.contains("CalendarDeadline"),
                "\(site) draws a resolution deadline and must route it through CalendarDeadline"
            )
        }
    }

    /// Line comments and block comments removed; string literals are not a concern
    /// here because no site names the helper inside one.
    private static func strippingComments(_ source: String) -> String {
        var out = source
        if let re = try? NSRegularExpression(pattern: #"/\*(?:.|\n)*?\*/"#) {
            out = re.stringByReplacingMatches(in: out, range: NSRange(out.startIndex..., in: out), withTemplate: "")
        }
        return out
            .split(separator: "\n", omittingEmptySubsequences: false)
            .map { line -> Substring in
                guard let r = line.range(of: "//") else { return line }
                return line[line.startIndex..<r.lowerBound]
            }
            .joined(separator: "\n")
    }
}
