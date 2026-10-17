import XCTest
@testable import Bain_Luck

/// #10880 — the event page's "Add to Calendar" reads the served detail payload
/// through the same rule as a card, and offers only for the page's own game.
///
/// The JSON is SYNTHETIC but has the `/api/events/{id}` shape: `_format_event`
/// keys, snake case. `start_is_from_schedule` is new on that route in the same
/// change (`backend/tests/test_event_detail_serves_start_is_from_schedule_10880.py`
/// drives `get_event` for the producer half).
final class CalendarDetail10880Tests: XCTestCase {

    /// Fri 16 Oct 2026 21:00:00Z.
    private static let now = Date(timeIntervalSince1970: 1_792_184_400)
    private static let pageId = 15327537

    private func detail(_ extra: String, id: Int = pageId, status: String = "scheduled") throws -> EventDetail {
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        return try d.decode(EventDetail.self, from: Data("""
        {"id": \(id), "external_id": "abc123", "sport": "basketball_nba",
         "sport_name": "NBA", "home_team": "Philadelphia 76ers",
         "away_team": "Boston Celtics", "commence_time": "2026-10-16T23:00:00+00:00",
         "start_is_tbd": false, "completed_at": null, "status": "\(status)",
         "started_without_result": false, "home_score": null,
         "away_score": null\(extra)}
        """.utf8))
    }

    private func draft(_ event: EventDetail?) -> CalendarEntryDraft10880? {
        CalendarDetailMenu10880.draft(pageEventId: Self.pageId, event: event, now: Self.now)
    }

    private let fromSchedule = #", "start_is_from_schedule": true"#

    func testAScheduleStartedPageOffersTheSameDraftAsItsCard() throws {
        let page = try detail(fromSchedule)
        guard let d = draft(page) else {
            return XCTFail("a scheduled NBA game from a schedule must offer")
        }
        XCTAssertEqual(d.start, Date(timeIntervalSince1970: 1_792_191_600), "2026-10-16T23:00:00Z")
        XCTAssertEqual(d.title, "Boston Celtics vs Philadelphia 76ers")
        XCTAssertEqual(d.url.absoluteString, "https://bainluck.com/events/15327537")
        XCTAssertEqual(d.url.absoluteString, eventShareURL(Self.pageId), "the link Share sends")
        XCTAssertFalse(d.title.contains("%"), "no probability in a static title")
    }

    func testAnAbsentFlagHidesTheMenu() throws {
        let page = try detail("")
        XCTAssertNil(page.startIsFromSchedule)
        XCTAssertNil(draft(page), "an older server or cached payload must never offer")
        XCTAssertEqual(CalendarEntry10880.decide(for: page.calendarSubject10880, now: Self.now),
                       .hide(.startNotFromSchedule))
    }

    func testAFalseFlagHidesTheMenu() throws {
        XCTAssertNil(draft(try detail(#", "start_is_from_schedule": false"#)))
    }

    func testAPlaceholderHourHidesTheMenu() throws {
        XCTAssertNotNil(draft(try detail(fromSchedule)), "control: an announced hour offers")
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        let tbd = try d.decode(EventDetail.self, from: Data("""
        {"id": \(Self.pageId), "sport": "baseball_mlb", "home_team": "New York Yankees",
         "away_team": "Boston Red Sox", "commence_time": "2026-10-20T20:00:00+00:00",
         "start_is_tbd": true, "start_is_from_schedule": true, "status": "scheduled"}
        """.utf8))
        XCTAssertNil(draft(tbd))
    }

    func testOnlyAScheduledGameOffers() throws {
        for status in ["live", "completed", "closed", "postponed", "cancelled", "suspended"] {
            XCTAssertNil(draft(try detail(fromSchedule, status: status)), status)
        }
    }

    func testAVenueClosedGameHidesTheMenu() throws {
        XCTAssertNil(draft(try detail(fromSchedule + #", "venue_closed_no_winner": true"#)))
    }

    func testAStartedGameHidesTheMenuEvenIfStillScheduled() throws {
        let page = try detail(fromSchedule)
        let afterStart = Date(timeIntervalSince1970: 1_792_191_600)
        XCTAssertNil(CalendarDetailMenu10880.draft(pageEventId: Self.pageId, event: page, now: afterStart))
    }

    func testAnotherEventsPayloadOffersNothing() throws {
        // A page still showing the previous game, or a duplicate served as its
        // canonical row: the entry must link the page the reader opened.
        let other = try detail(fromSchedule, id: Self.pageId + 1)
        XCTAssertNotNil(CalendarEntry10880.decide(for: other.calendarSubject10880, now: Self.now)
            .offeredDraft, "control: the payload itself is eligible")
        XCTAssertNil(draft(other))
        XCTAssertNil(draft(nil), "no payload yet")
    }

    func testTheDetailSubjectReadsEveryServedField() throws {
        let page = try detail(fromSchedule + #", "venue_closed_no_winner": false"#)
        let s = page.calendarSubject10880
        XCTAssertEqual(s.eventID, Self.pageId)
        XCTAssertEqual(s.awayName, "Boston Celtics")
        XCTAssertEqual(s.homeName, "Philadelphia 76ers")
        XCTAssertEqual(s.sportKey, "basketball_nba")
        XCTAssertEqual(s.start, Date(timeIntervalSince1970: 1_792_191_600))
        XCTAssertFalse(s.startIsTbd)
        XCTAssertTrue(s.startIsFromSchedule)
        XCTAssertEqual(s.status, "scheduled")
        XCTAssertFalse(s.venueClosedNoWinner)
    }

    // MARK: - Placement (`CalendarDetailMenu10880`'s doc comment)

    private func source(_ parts: String...) throws -> String {
        var url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()   // BainLuckTests
            .deletingLastPathComponent()   // Bain Luck (project dir)
            .appendingPathComponent("Bain Luck")
        for part in parts { url.appendPathComponent(part) }
        return try String(contentsOf: url, encoding: .utf8)
    }

    func testTheMenuSitsAfterShareAndPinInTheToolbar() throws {
        let page = try source("Views", "EventDetailView.swift")
        guard let share = page.range(of: "ShareLink(item: shareURL)"),
              let pin = page.range(of: #"PinButton(type: "event", id: eventId)"#),
              let menu = page.range(of: "CalendarDetailMenu10880(pageEventId: eventId, event: vm.event)")
        else { return XCTFail("Share, Pin and the calendar menu must all be in the page") }
        XCTAssertLessThan(share.lowerBound, pin.lowerBound)
        XCTAssertLessThan(pin.lowerBound, menu.lowerBound, "the menu comes after Share and Pin")
        XCTAssertEqual(page.components(separatedBy: "CalendarDetailMenu10880(").count, 2,
                       "one entry on the page")
    }

    func testTheMenuIsQuiet() throws {
        let menu = try source("Calendar10880", "CalendarDetailMenu10880.swift")
        XCTAssertTrue(menu.contains(#"Label("Add to Calendar""#), "control: reading the menu")
        XCTAssertTrue(menu.contains(#".accessibilityLabel("More")"#))
        for loud in ["TipKit", "Tip(", ".popoverTip", ".badge(", ".disabled(", "requestAccess",
                     "requestFullAccessToEvents", "requestWriteOnlyAccessToEvents"] {
            XCTAssertFalse(menu.contains(loud), "\(loud) in the calendar menu")
        }
    }

    /// The control, not just its label, is 44 high. A frame on a Menu's label
    /// paints inside the toolbar-sized control (48×36 measured on f62502f156);
    /// Pin's `.plain` escape is what gives its control the label's size. The
    /// measured proof is `ATapNearTheMoreEdgeOpensItsMenu10880Tests` (opt-in).
    func testTheMoreControlTakesPinsPlainStyleSoItIs44High() throws {
        let menu = try source("Calendar10880", "CalendarDetailMenu10880.swift")
        XCTAssertTrue(menu.contains(".frame(width: 44, height: 44)"))
        XCTAssertTrue(menu.contains(".menuStyle(.button)"), "a button-style menu takes a button style")
        XCTAssertTrue(menu.contains(".buttonStyle(.plain)"), "the toolbar's style caps the control at 36")
        XCTAssertFalse(menu.contains("height: 36"), "never lower 44 to fit")
    }

    /// Off the toolbar's style the icon takes no toolbar colour; `.tint` drew it
    /// accent blue beside a black Share (native, 5d3931e735). It stays Share's.
    func testTheMoreIconKeepsSharesColourOffTheToolbarStyle() throws {
        let menu = try source("Calendar10880", "CalendarDetailMenu10880.swift")
        XCTAssertTrue(menu.contains(".foregroundStyle(.primary)"))
        XCTAssertFalse(menu.contains(".foregroundStyle(.tint)"), "accent blue beside a black Share")
    }
}

private extension CalendarEntry10880.Decision {
    var offeredDraft: CalendarEntryDraft10880? {
        if case .offer(let draft) = self { return draft }
        return nil
    }
}
