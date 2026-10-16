import XCTest
#if os(iOS)
import EventKit
#endif
@testable import Bain_Luck

/// #10880 — the served feed card reaches the calendar rule, the editor opens
/// with exactly the draft, and the presenter source stays inside its privacy
/// list.
///
/// The card JSON is SYNTHETIC but has the `/api/feed` shape: `format_event_data`
/// keys, snake case. `start_is_from_schedule` is new in the same change
/// (`backend/tests/test_feed_card_serves_start_is_from_schedule_10880.py`
/// asserts the producer half).
final class CalendarFeedCard10880Tests: XCTestCase {

    /// Fri 16 Oct 2026 21:00:00Z.
    private static let now = Date(timeIntervalSince1970: 1_792_184_400)

    private func card(_ extra: String) throws -> FeedEventData {
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        return try d.decode(FeedEventData.self, from: Data("""
        {"id": 15327537, "external_id": "abc123", "sport": "basketball_nba",
         "sport_name": "NBA", "home_team": "Philadelphia 76ers",
         "away_team": "Boston Celtics", "commence_time": "2026-10-16T23:00:00+00:00",
         "start_is_tbd": false, "status": "scheduled", "home_score": null,
         "away_score": null\(extra)}
        """.utf8))
    }

    private func decision(_ extra: String) throws -> CalendarEntry10880.Decision {
        CalendarEntry10880.decide(for: try card(extra).calendarSubject10880, now: Self.now)
    }

    func testAScheduleStartedCardOffersTheServedInstant() throws {
        guard case .offer(let d) = try decision(#", "start_is_from_schedule": true"#) else {
            return XCTFail("a scheduled NBA game from a schedule must offer")
        }
        XCTAssertEqual(d.start, Date(timeIntervalSince1970: 1_792_191_600), "2026-10-16T23:00:00Z")
        XCTAssertEqual(d.title, "Boston Celtics vs Philadelphia 76ers")
        XCTAssertEqual(d.url.absoluteString, "https://bainluck.com/events/15327537")
    }

    func testAnAbsentFlagHidesTheAction() throws {
        XCTAssertEqual(try card("").startIsFromSchedule, nil)
        XCTAssertEqual(try decision(""), .hide(.startNotFromSchedule),
                       "an older server or a cached payload must never offer")
    }

    func testAFalseFlagHidesTheAction() throws {
        XCTAssertEqual(try decision(#", "start_is_from_schedule": false"#), .hide(.startNotFromSchedule))
    }

    func testAServedPlaceholderHourHidesTheAction() throws {
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        let tbd = try d.decode(FeedEventData.self, from: Data("""
        {"id": 15319235, "sport": "baseball_mlb", "home_team": "New York Yankees",
         "away_team": "Boston Red Sox", "commence_time": "2026-10-20T20:00:00+00:00",
         "start_is_tbd": true, "start_is_from_schedule": true, "status": "scheduled"}
        """.utf8))
        XCTAssertEqual(CalendarEntry10880.decide(for: tbd.calendarSubject10880, now: Self.now),
                       .hide(.startIsTBA))
    }

    func testAServedFractionalSecondStartStillParses() throws {
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        let event = try d.decode(FeedEventData.self, from: Data("""
        {"id": 7, "sport": "icehockey_nhl", "home_team": "Boston Bruins",
         "away_team": "Toronto Maple Leafs", "commence_time": "2026-10-17T23:00:00.000000+00:00",
         "start_is_from_schedule": true, "status": "scheduled"}
        """.utf8))
        guard case .offer(let draft) = CalendarEntry10880.decide(
            for: event.calendarSubject10880, now: Self.now) else {
            return XCTFail("a fractional-second start is still a start")
        }
        XCTAssertEqual(draft.start, Date(timeIntervalSince1970: 1_792_278_000))
    }

    #if os(iOS)
    func testTheEditorOpensWithExactlyTheDraftAndNoCalendarOrAlert() throws {
        guard case .offer(let draft) = try decision(#", "start_is_from_schedule": true"#) else {
            return XCTFail("expected an offer")
        }
        let event = CalendarEditorPresenter10880.event(from: draft, in: EKEventStore())
        XCTAssertEqual(event.title, draft.title)
        XCTAssertEqual(event.startDate, draft.start)
        XCTAssertEqual(event.endDate, draft.end)
        XCTAssertEqual(event.url, draft.url)
        XCTAssertEqual(event.notes, draft.notes)
        XCTAssertFalse(event.isAllDay)
        XCTAssertNotNil(event.timeZone, "a nil zone would make the entry a floating time")
        XCTAssertNil(event.alarms?.first, "no alert is preselected")
        XCTAssertNil(event.location, "no venue is asserted; the feed serves none")
    }
    #endif

    // MARK: - The privacy list (`CalendarEditorPresenter10880`'s doc comment)

    private func calendarSource(_ name: String) throws -> String {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()   // BainLuckTests
            .deletingLastPathComponent()   // Bain Luck (project dir)
            .appendingPathComponent("Bain Luck")
            .appendingPathComponent("Calendar10880")
            .appendingPathComponent(name)
        // Comments stripped: the doc comment names every forbidden call.
        return try String(contentsOf: url, encoding: .utf8)
            .split(separator: "\n", omittingEmptySubsequences: false)
            .filter { !$0.trimmingCharacters(in: .whitespaces).hasPrefix("//") }
            .joined(separator: "\n")
    }

    func testThePresenterNeverAsksForAccessSavesReadsOrPicksForTheReader() throws {
        let source = try calendarSource("CalendarEditorPresenter10880.swift")
        XCTAssertTrue(source.contains("EKEventEditViewController()"),
                      "control: the scan is reading the presenter")
        for forbidden in [
            "requestFullAccessToEvents", "requestWriteOnlyAccessToEvents", "requestAccess(",
            ".save(", "events(matching", "calendars(for", "defaultCalendarForNewEvents",
            ".calendar =", "EKAlarm", "addAlarm", "alarms =", "cancelEditing",
        ] {
            XCTAssertFalse(source.contains(forbidden), "\(forbidden) in the presenter")
        }
    }
}
