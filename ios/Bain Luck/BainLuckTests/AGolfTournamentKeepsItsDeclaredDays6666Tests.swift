import XCTest
@testable import Bain_Luck

/// #6666 — GOLF DATES RENDERED A DAY EARLY EVERYWHERE WEST OF UTC.
///
/// Found on a LOOK during #1471 (native/198, 2026-09-16): the Biltmore
/// Championship Asheville card read **`Sep 16–19`** for a tournament the server
/// dates `2026-09-17` → `2026-09-20`. One day early, at both ends.
///
/// `formatDateRange` formatted through `_monthDay`/`_dayOnly`, neither of which
/// pins a zone, and `app/routes/golf.py:1179` builds the wire value as
/// `f"{t.start_date}T00:00:00+00:00"` from a **date** column. `2026-09-17T00:00:00Z`
/// is 17:00 on the 16th in Pacific time, so the day component rendered as 16.
/// Re-measured on production 2026-09-20, the morning this was fixed: **212 of
/// 212** `/api/golf` date values carry exactly that suffix — the whole
/// population, not a specimen — and the live `current_event` was Biltmore
/// itself, ending that same day while the card called it finished the day
/// before.
///
/// ## WHY THESE ASSERTIONS AND NOT THE OBVIOUS ONE
///
/// 🔴 **THE OBVIOUS TEST IS VACUOUS UNDER A UTC HARNESS.** The shift is
/// `local − UTC`, which is exactly zero in UTC: "renders Sep 17" passes on the
/// fix AND on the bug. That is gotcha #44 wearing a timezone. So every case here
/// does BOTH of the things that can make it fail on the defect: it pins the
/// process zone (`NSTimeZone.default`, which is what an un-zoned `DateFormatter`
/// follows) and it passes an explicit `localZone:`. Pacific is the zone the
/// defect was reported in; Kiritimati (UTC+14) is the other side of the line,
/// and it is here because "subtract a day" would pass a Pacific-only battery.
///
/// 🔴 **THE CONTROLS ARE THE POINT.** Three of them stop this fix becoming
/// "render everything in UTC", which would swap one wrong day for another:
/// `test_a_real_instant_keeps_the_readers_day` (a range end that genuinely is an
/// instant), `test_formattedShortDate_still_reads_in_the_readers_zone` (concept
/// cards, whose population is mixed — `event_concept.py` serialises
/// `start_date or commence_time`), and `test_the_browse_clock_did_not_move`
/// (`isBeingPlayed` parses a real 06:00Z instant, so a "fix" inside
/// `parseFlexibleDate` would silently move which hubs say "live").
final class AGolfTournamentKeepsItsDeclaredDays6666Tests: XCTestCase {

    /// The zone the defect was reported in. UTC−7 in September, so a
    /// UTC-midnight value lands on the PREVIOUS day here.
    private let pacific = TimeZone(identifier: "America/Los_Angeles")!
    /// UTC+14 — the far side. A UTC-midnight value is already that day here, so
    /// a fix that simply subtracts a day breaks this one.
    private let kiritimati = TimeZone(identifier: "Pacific/Kiritimati")!

    private var originalZone: TimeZone!

    override func setUp() {
        super.setUp()
        originalZone = NSTimeZone.default
    }

    override func tearDown() {
        NSTimeZone.default = originalZone
        super.tearDown()
    }

    /// Pin the process zone as well as the argument. An un-zoned `DateFormatter`
    /// reads `NSTimeZone.default`, so this is what makes a reverted fix fail
    /// here rather than only on a developer's laptop.
    @discardableResult
    private func inZone<T>(_ zone: TimeZone, _ body: () throws -> T) rethrows -> T {
        NSTimeZone.default = zone
        defer { NSTimeZone.default = originalZone }
        return try body()
    }

    // MARK: - The production specimen

    /// Biltmore, verbatim off `/api/golf` on 2026-09-20. `Sep 16–19` is the
    /// defect: a tournament whose final round is being played today, dated as
    /// having finished yesterday.
    func test_the_biltmore_range_keeps_the_days_the_server_declared() {
        for zone in [pacific, kiritimati] {
            inZone(zone) {
                XCTAssertEqual(
                    formatDateRange(
                        start: "2026-09-17T00:00:00+00:00",
                        end: "2026-09-20T00:00:00+00:00",
                        localZone: zone
                    ),
                    "Sep 17\u{2013}20",
                    "declared days must read the same in \(zone.identifier) as on the wire"
                )
            }
        }
    }

    /// The same value through the tournament page's view model, so the fix is
    /// proven where the reader meets it and not only on the free function.
    /// This one calls `formatDateRange` with NO `localZone:` argument — through
    /// the view model, the way the page does — so the default is under guard
    /// too. A fix that only works when a test passes the zone in is not a fix.
    func test_the_tournament_page_header_carries_the_declared_range() throws {
        let rendered = try inZone(pacific) { try biltmorePresentation().dateRange }
        XCTAssertEqual(rendered, "Sep 17\u{2013}20")
    }

    // MARK: - The shapes the formatter has to keep

    func test_a_range_that_crosses_a_month_keeps_both_months() {
        inZone(pacific) {
            XCTAssertEqual(
                formatDateRange(
                    start: "2026-09-30T00:00:00+00:00",
                    end: "2026-10-01T00:00:00+00:00",
                    localZone: pacific
                ),
                "Sep 30 \u{2013} Oct 1"
            )
        }
    }

    /// The month comparison and the printed days must come from the same
    /// calendar. Read in Pacific, this range is Sep 30 – Sep 30 (one month);
    /// read as declared it is Oct 1 – Oct 2. Either answer is self-consistent;
    /// a mix prints "Oct 1–2" under the cross-month rule or "Sep 30 – Oct 1"
    /// under the same-month one.
    func test_a_range_that_only_crosses_a_month_in_the_readers_zone_is_not_split() {
        inZone(pacific) {
            XCTAssertEqual(
                formatDateRange(
                    start: "2026-10-01T00:00:00+00:00",
                    end: "2026-10-02T00:00:00+00:00",
                    localZone: pacific
                ),
                "Oct 1\u{2013}2"
            )
        }
    }

    func test_one_end_only_prints_that_end() {
        inZone(pacific) {
            XCTAssertEqual(
                formatDateRange(start: "2026-09-17T00:00:00+00:00", end: nil, localZone: pacific),
                "Sep 17"
            )
            XCTAssertEqual(
                formatDateRange(start: nil, end: "2026-09-20T00:00:00+00:00", localZone: pacific),
                "Sep 20"
            )
        }
    }

    /// The Korn Ferry row on `/api/golf` today carries `null` at both ends. A
    /// row with nothing to say says nothing.
    func test_no_dates_prints_nothing() {
        inZone(pacific) {
            XCTAssertNil(formatDateRange(start: nil, end: nil, localZone: pacific))
            XCTAssertNil(formatDateRange(start: "", end: "", localZone: pacific))
            XCTAssertNil(formatDateRange(start: "not a date", end: nil, localZone: pacific))
        }
    }

    /// A bare `yyyy-MM-dd` is a day too, and means the same day everywhere.
    func test_a_bare_date_keeps_its_day_in_both_hemispheres() {
        for zone in [pacific, kiritimati] {
            inZone(zone) {
                XCTAssertEqual(
                    formatDateRange(start: "2026-09-17", end: "2026-09-20", localZone: zone),
                    "Sep 17\u{2013}20"
                )
            }
        }
    }

    // MARK: - CONTROL: what must NOT move

    /// A value that is genuinely an instant is still told in the reader's time.
    /// `2026-09-18T02:00:00Z` is 7pm on the 17th in Pacific, and that is the
    /// right answer for a real clock time. Without this, "render everything in
    /// UTC" grades as a perfect fix.
    func test_a_real_instant_keeps_the_readers_day() {
        inZone(pacific) {
            XCTAssertEqual(
                formatDateRange(start: "2026-09-18T02:00:00+00:00", end: nil, localZone: pacific),
                "Sep 17"
            )
        }
        inZone(kiritimati) {
            // The same instant is already the 18th at UTC+14.
            XCTAssertEqual(
                formatDateRange(start: "2026-09-18T02:00:00+00:00", end: nil, localZone: kiritimati),
                "Sep 18"
            )
        }
    }

    /// Concept cards are the mixed population this fix deliberately did not
    /// touch: `event_concept.py` serialises `start_date or commence_time`, so a
    /// UTC pin there would push an evening kickoff a day LATE.
    func test_formattedShortDate_still_reads_in_the_readers_zone() {
        inZone(pacific) {
            XCTAssertEqual(formattedShortDate("2026-09-18T02:00:00+00:00"), "Sep 17")
        }
    }

    /// `FeaturedTournaments.isBeingPlayed` parses `liveThrough` — a real instant
    /// chosen for its hour (`2026-09-14T06:00:00+00:00`) — through
    /// `parseFlexibleDate`. Moving that parse is the tempting one-line "fix"
    /// this range defect invites, and it would quietly change which hubs Browse
    /// calls live.
    func test_the_browse_clock_did_not_move() {
        XCTAssertEqual(
            parseFlexibleDate("2026-09-14T06:00:00+00:00"),
            Date(timeIntervalSince1970: 1_789_365_600),
            "06:00Z, not a local midnight"
        )
        let hub = FeaturedTournament(
            slug: "us-open",
            title: "US Open",
            liveSubtitle: "Live matches, results, title odds",
            restingSubtitle: "Results and title odds",
            liveThrough: "2026-09-14T06:00:00+00:00",
            icon: "sportscourt"
        )
        XCTAssertTrue(hub.isBeingPlayed(asOf: Date(timeIntervalSince1970: 1_789_362_000)), "05:00Z is inside")
        XCTAssertFalse(hub.isBeingPlayed(asOf: Date(timeIntervalSince1970: 1_789_369_200)), "07:00Z is outside")
    }

    // MARK: - The round strip, which reads the same field

    /// 6pm Pacific on the 16th: the tournament starts TOMORROW. The old
    /// arithmetic subtracted two instants, so it had already counted an hour
    /// past the start and lit R1 — on the evening before the first tee.
    func test_no_round_is_lit_the_evening_before_the_first_round() {
        XCTAssertNil(
            tournamentRoundNumber(
                start: "2026-09-17T00:00:00+00:00",
                now: date("2026-09-17T01:00:00Z"),
                calendar: calendar(pacific)
            )
        )
    }

    func test_each_tournament_day_lights_its_own_round() {
        let cases: [(String, Int)] = [
            ("2026-09-17T17:00:00Z", 1),   // Thu 10:00 PDT
            ("2026-09-18T17:00:00Z", 2),
            ("2026-09-19T17:00:00Z", 3),
            ("2026-09-20T17:00:00Z", 4),   // Sun 10:00 PDT, the final round
        ]
        for (instant, expected) in cases {
            XCTAssertEqual(
                tournamentRoundNumber(
                    start: "2026-09-17T00:00:00+00:00",
                    now: date(instant),
                    calendar: calendar(pacific)
                ),
                expected,
                "\(instant) is round \(expected) in Pacific"
            )
        }
    }

    /// 7pm Pacific on the final day is four elapsed days from UTC midnight, so
    /// the old rule fell out of its own window and the strip DISAPPEARED while
    /// the final round was still being played.
    func test_the_strip_survives_the_evening_of_the_final_round() {
        XCTAssertEqual(
            tournamentRoundNumber(
                start: "2026-09-17T00:00:00+00:00",
                now: date("2026-09-21T02:00:00Z"),
                calendar: calendar(pacific)
            ),
            4
        )
    }

    func test_the_strip_is_gone_the_day_after_the_tournament() {
        XCTAssertNil(
            tournamentRoundNumber(
                start: "2026-09-17T00:00:00+00:00",
                now: date("2026-09-21T17:00:00Z"),
                calendar: calendar(pacific)
            )
        )
    }

    /// East of the line the day must not run early either: 00:30 on the 17th in
    /// Kiritimati is day one, and 23:30 on the 16th there is not.
    func test_the_round_follows_the_readers_own_day_east_of_utc() {
        XCTAssertEqual(
            tournamentRoundNumber(
                start: "2026-09-17T00:00:00+00:00",
                now: date("2026-09-16T10:30:00Z"),      // Sep 17, 00:30 at UTC+14
                calendar: calendar(kiritimati)
            ),
            1
        )
        XCTAssertNil(
            tournamentRoundNumber(
                start: "2026-09-17T00:00:00+00:00",
                now: date("2026-09-16T09:30:00Z"),      // Sep 16, 23:30 at UTC+14
                calendar: calendar(kiritimati)
            )
        )
    }

    func test_no_start_date_lights_no_round() {
        XCTAssertNil(tournamentRoundNumber(start: nil, now: date("2026-09-18T17:00:00Z")))
        XCTAssertNil(tournamentRoundNumber(start: "not a date", now: date("2026-09-18T17:00:00Z")))
    }

    // MARK: - The day question itself

    func test_the_day_offset_counts_calendar_days_not_elapsed_hours() {
        // One minute apart, either side of local midnight: one day, not zero.
        XCTAssertEqual(
            backendDayOffset(
                from: "2026-09-17T00:00:00+00:00",
                to: date("2026-09-18T06:59:00Z"),       // Sep 17, 23:59 PDT
                calendar: calendar(pacific)
            ),
            0
        )
        XCTAssertEqual(
            backendDayOffset(
                from: "2026-09-17T00:00:00+00:00",
                to: date("2026-09-18T07:01:00Z"),       // Sep 18, 00:01 PDT
                calendar: calendar(pacific)
            ),
            1
        )
    }

    // MARK: - Fixtures

    private func calendar(_ zone: TimeZone) -> Calendar {
        var c = Calendar(identifier: .gregorian)
        c.timeZone = zone
        return c
    }

    private func date(_ iso: String) -> Date {
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime]
        guard let d = f.date(from: iso) else {
            XCTFail("fixture instant \(iso) does not parse")
            return Date(timeIntervalSince1970: 0)
        }
        return d
    }

    /// `/api/golf/tournaments/biltmore-championship-asheville`, trimmed to the
    /// fields this guard reads. Decoded rather than hand-built: these models are
    /// `Decodable`-only, and going through the decoder is what proves the dates
    /// survive the wire as well as the formatter.
    private static let biltmorePayload = """
    {
      "tournament": {
        "name": "Biltmore Championship Asheville",
        "slug": "biltmore-championship-asheville",
        "key": "biltmore_championship_asheville",
        "tour_label": "PGA Tour",
        "is_major": false,
        "start_date": "2026-09-17T00:00:00+00:00",
        "end_date": "2026-09-20T00:00:00+00:00",
        "venue": "The Cliffs at Walnut Cove",
        "location": "Arden, NC"
      },
      "golfers": [],
      "biggest_movers": []
    }
    """

    private func biltmorePresentation() throws -> GolfTournamentPresentation {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let response = try decoder.decode(
            GolfTournamentDetailResponse.self, from: Data(Self.biltmorePayload.utf8))
        return GolfTournamentPresentation(response: response)
    }
}
