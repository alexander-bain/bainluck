import XCTest
@testable import Bain_Luck

/// #9483 / #11296 — ONE DISPLAY CLOCK (Design, MISSING-SURFACE-DISPOSITION,
/// 2026-10-23). A retained live payload rendered hours later read the host's
/// wall clock in three places the view model's frozen clock never reaches: the
/// headline's phase and age, the chart's current-quote test and live window,
/// and the NBA ladders' quote eligibility (15195971, 403 0547Z: "Last recorded
/// win chance", ladders "Before tip-off", no end dot, an axis to ~10:45 PM).
///
/// The seam is one optional instant on the page. Nil — every production
/// mount — is the real clock, read where each reader read it before; set, all
/// of them read that one held moment. No served timestamp is touched.
@MainActor
final class TheEventPageReadsOneDisplayClock9483Tests: XCTestCase {

    private static let held = ISO8601DateFormatter().date(from: "2026-10-23T03:14:01Z")!
    private static let tick = ISO8601DateFormatter().date(from: "2026-10-23T05:42:00Z")!

    func testProductionReadsTheTickAndARetainedCheckReadsTheHeldInstant() {
        XCTAssertEqual(EventDetailView.displayNow(asOf: nil, tick: Self.tick), Self.tick)
        XCTAssertEqual(EventDetailView.displayNow(asOf: Self.held, tick: Self.tick), Self.held)
    }

    /// The live window the page hands both charts ends at the clock it is
    /// given — the held instant, not the host's.
    func testTheLiveChartWindowEndsOnTheClockItIsHanded() throws {
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        let event = try d.decode(EventDetail.self, from: Data(#"""
        {"id": 15195971, "sport": "basketball_nba", "home_team": "Oklahoma City Thunder", "away_team": "Denver Nuggets", "commence_time": "2026-10-23T01:30:00+00:00", "status": "live", "home_score": 55, "away_score": 58}
        """#.utf8))
        let domain = try XCTUnwrap(EventDetailView.pageLegacyChartDomain(
            event: event, history: nil, range: .sinceStart,
            now: EventDetailView.displayNow(asOf: Self.held, tick: Self.tick)))
        XCTAssertEqual(domain.upperBound, Self.held.addingTimeInterval(60))
    }

    // MARK: - Wiring: every reader goes through the one clock

    private func page() throws -> String {
        let root = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
        return try String(contentsOf: root.appendingPathComponent("Bain Luck/Views/EventDetailView.swift"),
                          encoding: .utf8)
    }

    func testTheSeamDefaultsToTheRealClock() throws {
        let text = try page()
        XCTAssertTrue(text.contains("init(eventId: Int, viewModel: EventDetailViewModel? = nil, displayAsOf: Date? = nil)"))
        XCTAssertTrue(text.contains("static func displayNow(asOf: Date?, tick: Date) -> Date { asOf ?? tick }"))
    }

    func testNoFreshnessReaderReadsTheTickOrTheWallClockDirectly() throws {
        let text = try page()
        XCTAssertFalse(text.contains("now: tick.date"), "a minute tick reaches a reader only through displayNow")
        XCTAssertEqual(text.components(separatedBy: "now: displayNow(tick.date)").count - 1, 3,
                       "the chart's currentness, its settled decline and the headline phase")
        XCTAssertFalse(text.contains("now: Date())"), "no reader takes the wall clock inline")
        XCTAssertTrue(text.contains("homeShort: names.home, awayShort: names.away, now: displayNow())"),
                      "the NBA ladders' eligibility reads the display clock")
        XCTAssertEqual(text.components(separatedBy: "now: displayNow())").count - 1, 3,
                       "both chart windows and the ladders read the display clock")
        let shared = try XCTUnwrap(text.range(of: "private var sharedChartDomain: ClosedRange<Date>? {"))
        XCTAssertTrue(text[shared.upperBound...].prefix(300).contains("now: displayNow())"))
        let legacy = try XCTUnwrap(text.range(of: "private var legacyChartDataDomain: ClosedRange<Date>? {"))
        XCTAssertTrue(text[legacy.upperBound...].prefix(300).contains("now: displayNow())"))
    }
}
