import XCTest
@testable import Bain_Luck

/// #10246 — the iPhone Market Details card read "Starts Sep 30, 2026" over
/// "Resolves Oct 4, 2026" for the Alfred Dunhill Links Championship (futures
/// 62904927, DataGolf), whose first round was Thursday Oct 1.
///
/// The wire values are the specimen's served values, verbatim
/// (`GET /api/futures/62904927`, 2026-10-02 23:3xZ).
///
/// The harness pins UTC, where local IS UTC and the bug cannot show (the
/// #4081 trap). Every assertion that is about the shift therefore names a real
/// western zone, and the strawman proves that zone reproduces the defect.
final class AFuturesStartPrintsItsDeclaredDay10246Tests: XCTestCase {

    private let specimenCommence = "2026-10-01T00:00:00+00:00"
    private let specimenResolves = "2026-10-04T00:00:00+00:00"
    private let pacific = TimeZone(identifier: "America/Los_Angeles")!
    private let tokyo = TimeZone(identifier: "Asia/Tokyo")!

    private func localInstant(_ raw: String, _ zone: TimeZone) -> String? {
        guard let date = raw.asDate else { return nil }
        let f = DateFormatter()
        f.locale = Locale(identifier: "en_US_POSIX")
        f.dateFormat = "MMM d, yyyy"
        f.timeZone = zone
        return f.string(from: date)
    }

    func test_strawman_the_old_local_formatting_printed_the_day_before_in_pacific() {
        // If this were "Oct 1", every assertion below would pass for the wrong reason.
        XCTAssertEqual(localInstant(specimenCommence, pacific), "Sep 30, 2026")
    }

    func test_the_specimen_starts_on_its_declared_day_in_pacific() {
        XCTAssertEqual(FuturesStartDate.label(commenceTime: specimenCommence,
                                              resolutionDate: specimenResolves,
                                              localZone: pacific),
                       "Oct 1, 2026")
    }

    func test_the_specimen_starts_on_its_declared_day_east_of_utc() {
        XCTAssertEqual(FuturesStartDate.label(commenceTime: specimenCommence,
                                              resolutionDate: specimenResolves,
                                              localZone: tokyo),
                       "Oct 1, 2026")
    }

    func test_starts_and_resolves_read_their_days_from_the_same_rule() {
        // The Resolves row beneath it (#4081) already read Oct 4 correctly.
        XCTAssertEqual(CalendarDeadline.format(specimenResolves, style: .monthDayYear,
                                               localZone: pacific),
                       "Oct 4, 2026")
    }

    func test_a_real_instant_start_keeps_the_readers_local_day() {
        // 02:00Z on Oct 25 is the evening of Oct 24 in Pacific: an instant, not a date.
        let commence = "2026-10-25T02:00:00+00:00"
        XCTAssertEqual(FuturesStartDate.label(commenceTime: commence,
                                              resolutionDate: "2026-11-01T00:00:00+00:00",
                                              localZone: pacific),
                       "Oct 24, 2026")
    }

    func test_the_9107_rule_still_decides_whether_a_start_is_printed() {
        XCTAssertNil(FuturesStartDate.label(commenceTime: "2027-10-25T14:00:00+00:00",
                                            resolutionDate: "2026-10-25T14:00:00+00:00",
                                            localZone: pacific))
        XCTAssertNil(FuturesStartDate.label(commenceTime: specimenResolves,
                                            resolutionDate: specimenResolves,
                                            localZone: pacific))
        XCTAssertNil(FuturesStartDate.label(commenceTime: nil,
                                            resolutionDate: specimenResolves,
                                            localZone: pacific))
    }

    func test_no_resolve_date_keeps_the_start_on_its_declared_day() {
        XCTAssertEqual(FuturesStartDate.label(commenceTime: specimenCommence,
                                              resolutionDate: nil,
                                              localZone: pacific),
                       "Oct 1, 2026")
    }

    func test_the_view_prints_the_starts_row_through_the_label() {
        // The helper is inert if the card still formats the Date itself.
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent().deletingLastPathComponent()
            .appendingPathComponent("Bain Luck/Views/FuturesDetailView.swift")
        guard let src = try? String(contentsOf: url, encoding: .utf8) else {
            return XCTFail("could not read \(url.path)")
        }
        XCTAssertTrue(src.contains("FuturesStartDate.label("))
        XCTAssertFalse(src.contains("Text(date, format: .dateTime.month(.abbreviated).day().year())"))
    }
}
