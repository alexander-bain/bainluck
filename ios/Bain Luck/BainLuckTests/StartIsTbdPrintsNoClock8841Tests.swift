import XCTest
@testable import Bain_Luck

/// #8841 — AN UNANNOUNCED START PRINTS ITS DAY AND "TBD", NOT A MADE-UP CLOCK.
///
/// StatPal lists MLB postseason games before MLB sets their times and stamps
/// them on the hour. The Red Sox @ Yankees Wild Card games (15319235 /
/// 15319236) sat at 20:00Z and every surface printed "Sep 29 1:00 PM" while
/// ESPN said `timeValid=false`. authority's PR #8856 (CERT-3567) serves
/// `start_is_tbd` on `/api/events`, search and the team brief; this is the
/// iPhone half, the web half is ux's PR #8873 and prints the same words.
///
/// Assertions test the PRESENCE OR ABSENCE OF A CLOCK, and every TBD arm has a
/// flag-absent control on the same input that DOES print one — without it a
/// formatter that never prints a clock would pass.
final class StartIsTbdPrintsNoClock8841Tests: XCTestCase {

    /// Wild Card game 1 as served on 2026-09-26: the placeholder instant.
    private let wildCardG1 = "2026-09-29T20:00:00+00:00"
    /// Noon Pacific on the day the issue was filed — Sep 26 in every US zone and
    /// in UTC, so "Today"/"Tomorrow" cannot flip with the simulator's zone.
    private let seenAt = ISO8601DateFormatter().date(from: "2026-09-26T19:00:00Z")!
    private let aClock = try! NSRegularExpression(pattern: #"\d{1,2}:\d{2}"#)

    private func hasClock(_ s: String?) -> Bool {
        guard let s else { return false }
        return aClock.firstMatch(in: s, range: NSRange(s.startIndex..., in: s)) != nil
    }

    // MARK: - The words

    func testTheSpecimenPrintsItsDayAndTBD() {
        XCTAssertEqual(RelativeTimeText.tbdText(for: wildCardG1, now: seenAt), "Sep 29 · TBD")
    }

    func testTodayAndTomorrowCompareAgainstTheReadersDay() {
        let g1Morning = ISO8601DateFormatter().date(from: "2026-09-29T17:00:00Z")!
        let dayBefore = ISO8601DateFormatter().date(from: "2026-09-28T17:00:00Z")!
        XCTAssertEqual(RelativeTimeText.tbdText(for: wildCardG1, now: g1Morning), "Today · TBD")
        XCTAssertEqual(RelativeTimeText.tbdText(for: wildCardG1, now: dayBefore), "Tomorrow · TBD")
    }

    /// The web's rule (`formatTbdStartLabel`): a placeholder is not an instant,
    /// so its day is read in UTC. 02:00Z on Sep 30 is 7 PM Sep 29 in Pacific;
    /// localising it would move the game a day.
    func testThePlaceholderDayIsReadInUTC() {
        XCTAssertEqual(
            RelativeTimeText.tbdText(for: "2026-09-30T02:00:00Z", now: seenAt), "Sep 30 · TBD")
    }

    func testTheHeroFormIsAbsoluteEvenOnTheDay() {
        let g1Morning = ISO8601DateFormatter().date(from: "2026-09-29T17:00:00Z")!
        XCTAssertEqual(
            RelativeTimeText.tbdText(for: wildCardG1, now: g1Morning, relativeDays: false),
            "Sep 29 · TBD")
    }

    func testAbsentOrUnparseableTimePrintsNothing() {
        XCTAssertNil(RelativeTimeText.tbdText(for: nil, now: seenAt))
        XCTAssertNil(RelativeTimeText.tbdText(for: "not a date", now: seenAt))
    }

    // MARK: - The row line (search + team schedule)

    func testTheRowLinePrintsNoClockWhenTheStartIsTBD() {
        let text = RelativeTimeText.text(for: wildCardG1, now: seenAt, startIsTbd: true)
        XCTAssertEqual(text, "Sep 29 · TBD")
        XCTAssertFalse(hasClock(text))
    }

    func testControlTheSameRowWithoutTheFlagPrintsItsClock() {
        let text = RelativeTimeText.text(for: wildCardG1, now: seenAt, startIsTbd: false)
        XCTAssertTrue(hasClock(text), "control lost its clock: \(text ?? "nil")")
        XCTAssertFalse(text?.contains("TBD") ?? true)
    }

    // MARK: - The countdown chip

    /// "In 3d 2h" is the placeholder clock restated as a duration.
    func testTheCountdownIsWithheldWhenTheStartIsTBD() {
        XCTAssertNil(StatusBadge.countdownText(
            commenceTime: wildCardG1, startIsTbd: true, now: seenAt))
    }

    func testControlTheCountdownIsDrawnWithoutTheFlag() {
        XCTAssertNotNil(StatusBadge.countdownText(
            commenceTime: wildCardG1, startIsTbd: false, now: seenAt))
    }

    // MARK: - The decode

    private func decode<T: Decodable>(_ type: T.Type, _ json: String) throws -> T {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(type, from: Data(json.utf8))
    }

    private func row(_ extra: String) -> String {
        #"{"id": 15319235, "home_team": "New York Yankees", "away_team": "Boston Red Sox", "commence_time": "2026-09-29T20:00:00+00:00", "status": "scheduled"\#(extra)}"#
    }

    /// Every model the four surfaces read names the key — a model that does not
    /// drops it in silence and the surface keeps printing 1:00 PM.
    func testEveryConsumerModelDecodesTheFlag() throws {
        let flagged = row(#", "start_is_tbd": true"#)
        XCTAssertEqual(try decode(SearchEvent.self, flagged).startIsTbd, true)
        XCTAssertEqual(try decode(EventDetail.self, flagged).startIsTbd, true)
        XCTAssertEqual(try decode(FeedEventData.self, flagged).startIsTbd, true)
    }

    /// An older server or cache omits the key; that is not a TBD.
    func testAnAbsentFlagDecodesAndIsNotTBD() throws {
        XCTAssertNil(try decode(SearchEvent.self, row("")).startIsTbd)
        XCTAssertNil(try decode(EventDetail.self, row("")).startIsTbd)
        XCTAssertNil(try decode(FeedEventData.self, row("")).startIsTbd)
    }

    // MARK: - The call sites

    /// The flag is only a fix where a surface hands it on. Comments are stripped
    /// so a docstring naming the flag cannot satisfy the scan.
    func testEachSurfaceHandsTheFlagOn() throws {
        let app = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()   // BainLuckTests
            .deletingLastPathComponent()   // Bain Luck (project dir)
            .appendingPathComponent("Bain Luck")
        let expected: [(String, Int)] = [
            ("Components/EventCardView.swift", 2),   // date line + badge
            ("Views/TeamDetailView.swift", 2),       // badge + date line
            ("Views/SearchView.swift", 2),           // badge + date line
            ("Views/EventDetailView.swift", 3),      // meta date + badge + Game Info
        ]
        for (path, minimum) in expected {
            let source = try String(contentsOf: app.appendingPathComponent(path), encoding: .utf8)
            let code = source.split(separator: "\n", omittingEmptySubsequences: false)
                .map { line -> Substring in
                    guard let r = line.range(of: "//") else { return line }
                    return line[..<r.lowerBound]
                }
                .joined(separator: "\n")
            let count = code.components(separatedBy: "startIsTbd == true").count - 1
            XCTAssertGreaterThanOrEqual(count, minimum, "\(path) no longer hands start_is_tbd on")
        }
    }
}
