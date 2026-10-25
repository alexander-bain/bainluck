import XCTest
@testable import Bain_Luck

/// #10880 — when a game card offers "Add to Calendar", and what the entry says.
///
/// Every offer arm has a refusal arm that differs in ONE field, so a rule that
/// always offers, or never does, fails here. The time fixtures are instants
/// around real daylight-saving changes (US: Sun 1 Nov 2026 06:00Z; UK: Sun 25
/// Oct 2026 01:00Z), read back in named zones. That shows the entry keeps the
/// served instant and that its length is elapsed time, not a wall-clock span.
final class CalendarEntry10880Tests: XCTestCase {

    /// Fri 16 Oct 2026 21:00:00Z.
    private static let now = Date(timeIntervalSince1970: 1_792_184_400)
    /// Sun 18 Oct 2026 17:00:00Z, a 1:00 PM ET NFL kick-off.
    private static let kickoff = Date(timeIntervalSince1970: 1_792_342_800)

    private func subject(
        eventID: Int = 15_327_537,
        away: String = "Buffalo Bills",
        home: String = "Kansas City Chiefs",
        sportKey: String? = "americanfootball_nfl",
        start: Date? = kickoff,
        startIsTbd: Bool = false,
        startIsFromSchedule: Bool = true,
        status: String? = "scheduled",
        venueClosedNoWinner: Bool = false
    ) -> CalendarSubject10880 {
        CalendarSubject10880(
            eventID: eventID, awayName: away, homeName: home, sportKey: sportKey,
            start: start, startIsTbd: startIsTbd, startIsFromSchedule: startIsFromSchedule,
            status: status, venueClosedNoWinner: venueClosedNoWinner
        )
    }

    private func draft(
        _ s: CalendarSubject10880, now: Date = now,
        file: StaticString = #filePath, line: UInt = #line
    ) -> CalendarEntryDraft10880? {
        guard case .offer(let d) = CalendarEntry10880.decide(for: s, now: now) else {
            XCTFail("expected an offer for \(s)", file: file, line: line)
            return nil
        }
        return d
    }

    private func refusal(_ s: CalendarSubject10880, now: Date = now) -> CalendarEntry10880.Refusal? {
        if case .hide(let r) = CalendarEntry10880.decide(for: s, now: now) { return r }
        return nil
    }

    // MARK: - The entry

    func testAScheduledGameFromAScheduleOffersTheExactEntry() throws {
        let d = try XCTUnwrap(draft(subject()))
        XCTAssertEqual(d.title, "Buffalo Bills vs Kansas City Chiefs")
        XCTAssertEqual(d.start, Self.kickoff, "the start must be the served instant, unchanged")
        XCTAssertEqual(d.planningDuration, 3.5 * 3_600)
        XCTAssertEqual(d.end, Self.kickoff.addingTimeInterval(12_600))
        XCTAssertEqual(d.url.absoluteString, "https://bainluck.com/events/15327537")
        XCTAssertEqual(d.url.absoluteString, eventShareURL(15_327_537),
                       "the entry must carry the same canonical link Share and Copy Link use")
    }

    func testTheCalendarLinkIgnoresTheCardsCampaignStyle() throws {
        let d = try XCTUnwrap(draft(subject()))
        XCTAssertNil(d.url.query, "a calendar entry is not a share campaign")
        XCTAssertNotEqual(d.url.absoluteString, eventShareURL(15_327_537, style: .nativeCard))
    }

    func testTheNotesSayItIsOneTimeAndTheLengthIsAnEstimate() throws {
        let d = try XCTUnwrap(draft(subject()))
        XCTAssertEqual(d.notes, """
        Open on Bain Luck: https://bainluck.com/events/15327537

        Added once from Bain Luck. If the game is moved, this entry won't change, \
        so check the game on Bain Luck before it starts.

        The length (3 hours 30 minutes) is a planning estimate, not the scheduled end.
        """)
    }

    func testTheTitleAndNotesCarryNoProbabilityAndNoMarketWords() throws {
        let d = try XCTUnwrap(draft(subject()))
        for text in [d.title, d.notes] {
            XCTAssertFalse(text.contains("%"), text)
            for word in ["question", "market", "odds", "chance", "sportsbook"] {
                XCTAssertFalse(text.lowercased().contains(word), "\(word) in: \(text)")
            }
        }
    }

    func testEachSportGetsItsOwnNounAndPlanningLength() throws {
        let cases: [(String, String, TimeInterval, String)] = [
            ("americanfootball_nfl", "game", 3.5, "3 hours 30 minutes"),
            ("basketball_nba", "game", 2.5, "2 hours 30 minutes"),
            ("icehockey_nhl", "game", 2.5, "2 hours 30 minutes"),
            ("baseball_mlb", "game", 3, "3 hours"),
            ("soccer_epl", "match", 2, "2 hours"),
            ("tennis_atp_paris", "match", 2.5, "2 hours 30 minutes"),
            ("mma_mixed_martial_arts", "fight", 3, "3 hours"),
        ]
        for (key, noun, hours, text) in cases {
            let d = try XCTUnwrap(draft(subject(sportKey: key)), key)
            XCTAssertEqual(d.planningDuration, hours * 3_600, key)
            XCTAssertTrue(d.notes.contains("If the \(noun) is moved"), "\(key): \(d.notes)")
            XCTAssertTrue(d.notes.contains("(\(text))"), "\(key): \(d.notes)")
        }
        XCTAssertEqual(CalendarEntry10880.durationText(3_600), "1 hour")
    }

    func testSurroundingWhitespaceIsTrimmedFromTheNames() throws {
        let d = try XCTUnwrap(draft(subject(away: "  Buffalo Bills ", home: "Kansas City Chiefs\n")))
        XCTAssertEqual(d.title, "Buffalo Bills vs Kansas City Chiefs")
    }

    // MARK: - Eligibility: one field away from an offer

    func testAMarketsTimeIsNeverOffered() {
        XCTAssertEqual(refusal(subject(startIsFromSchedule: false)), .startNotFromSchedule)
    }

    func testAPlaceholderHourIsNeverOffered() {
        XCTAssertEqual(refusal(subject(startIsTbd: true)), .startIsTBA)
    }

    func testOnlyScheduledCounts() {
        for status in ["live", "completed", "closed", "suspended", "cancelled", "canceled", "postponed"] {
            XCTAssertEqual(refusal(subject(status: status)), .notScheduled(status), status)
        }
        XCTAssertEqual(refusal(subject(status: nil)), .notScheduled(nil),
                       "nil files as upcoming in EventState, but it is not a confirmed schedule")
    }

    func testAContestTheVenueClosedIsNeverOffered() {
        XCTAssertEqual(refusal(subject(venueClosedNoWinner: true)), .closedNoWinner)
    }

    func testAMissingStartIsNeverOffered() {
        XCTAssertEqual(refusal(subject(start: nil)), .noStart)
    }

    func testAnUnnamedSideIsNeverOffered() {
        XCTAssertEqual(refusal(subject(away: "")), .unnamedSide)
        XCTAssertEqual(refusal(subject(home: "   ")), .unnamedSide)
        XCTAssertEqual(refusal(subject(away: "TBD")), .unnamedSide)
        XCTAssertEqual(refusal(subject(home: "tba")), .unnamedSide)
    }

    func testTheStartMustBeStrictlyAfterNow() {
        XCTAssertEqual(refusal(subject(), now: Self.kickoff), .alreadyStarted)
        XCTAssertEqual(refusal(subject(), now: Self.kickoff.addingTimeInterval(60)), .alreadyStarted)
        XCTAssertNotNil(draft(subject(), now: Self.kickoff.addingTimeInterval(-1)),
                        "one second before kick-off is still upcoming")
    }

    // MARK: - Time zones and daylight saving

    private func wallClock(_ date: Date, _ zone: String) -> DateComponents {
        var cal = Calendar(identifier: .gregorian)
        cal.timeZone = TimeZone(identifier: zone)!
        return cal.dateComponents([.year, .month, .day, .hour, .minute], from: date)
    }

    private func assertWall(_ date: Date, _ zone: String, _ y: Int, _ mo: Int, _ d: Int,
                            _ h: Int, _ mi: Int, file: StaticString = #filePath, line: UInt = #line) {
        let c = wallClock(date, zone)
        XCTAssertEqual([c.year, c.month, c.day, c.hour, c.minute], [y, mo, d, h, mi],
                       "\(zone)", file: file, line: line)
    }

    func testANightGameCrossingTheUSFallBackKeepsItsElapsedLength() throws {
        // Sun 1 Nov 2026 04:30Z = 12:30 AM EDT. US clocks fall back at 06:00Z.
        let start = Date(timeIntervalSince1970: 1_793_507_400)
        let d = try XCTUnwrap(draft(subject(start: start), now: Self.now))
        XCTAssertEqual(d.end.timeIntervalSince(d.start), 12_600)
        assertWall(d.start, "America/New_York", 2026, 11, 1, 0, 30)
        // 3h30m of elapsed time ends at 3:00 AM EST: a 2h30m wall-clock span.
        assertWall(d.end, "America/New_York", 2026, 11, 1, 3, 0)
    }

    func testTheSameKickoffHourMovesOnTheWallClockAcrossTheUSChange() throws {
        // Sat 31 Oct 23:00Z = 7:00 PM EDT; Sun 1 Nov 23:00Z = 6:00 PM EST.
        let saturday = Date(timeIntervalSince1970: 1_793_487_600)
        let sunday = Date(timeIntervalSince1970: 1_793_574_000)
        assertWall(try XCTUnwrap(draft(subject(start: saturday))).start, "America/New_York", 2026, 10, 31, 19, 0)
        assertWall(try XCTUnwrap(draft(subject(start: sunday))).start, "America/New_York", 2026, 11, 1, 18, 0)
    }

    func testAUKMatchOnTheDayBritishClocksGoBack() throws {
        // Sun 25 Oct 2026 14:00Z. The UK left BST at 01:00Z that morning: 2:00 PM GMT.
        let start = Date(timeIntervalSince1970: 1_792_936_800)
        let d = try XCTUnwrap(draft(subject(sportKey: "soccer_epl", start: start)))
        assertWall(d.start, "Europe/London", 2026, 10, 25, 14, 0)
        assertWall(d.start, "America/New_York", 2026, 10, 25, 10, 0)
    }

    func testTheCalendarDayIsTheReadersNotUTCs() throws {
        // Sat 17 Oct 2026 02:00Z: Friday 7:00 PM in Los Angeles, Saturday 3:00 AM in London.
        let start = Date(timeIntervalSince1970: 1_792_202_400)
        let d = try XCTUnwrap(draft(subject(sportKey: "basketball_nba", start: start)))
        assertWall(d.start, "America/Los_Angeles", 2026, 10, 16, 19, 0)
        assertWall(d.start, "Europe/London", 2026, 10, 17, 3, 0)
    }

    // MARK: - One editor at a time

    func testASecondTapWhileOpeningOrOpenIsRefused() {
        var gate = CalendarPresentationGate10880()
        XCTAssertTrue(gate.requestOpen())
        XCTAssertFalse(gate.requestOpen(), "a second tap before the editor appears must not stack one")
        gate.didPresent()
        XCTAssertEqual(gate.state, .open)
        XCTAssertFalse(gate.requestOpen(), "a second tap while the editor is up must not stack one")
        gate.didFinish()
        XCTAssertTrue(gate.requestOpen(), "after Add or Cancel the action works again")
    }

    func testAVanishedEditorReleasesOnlyAnOpenGate() {
        var gate = CalendarPresentationGate10880()
        XCTAssertTrue(gate.requestOpen())
        gate.editorVanished()
        XCTAssertEqual(gate.state, .opening, "no editor exists yet while opening; that is not a vanish")
        gate.didPresent()
        gate.editorVanished()
        XCTAssertEqual(gate.state, .idle, "an editor swiped away without a completion must not jam the action")
    }

    func testDidPresentWithoutARequestDoesNotOpen() {
        var gate = CalendarPresentationGate10880()
        gate.didPresent()
        XCTAssertEqual(gate.state, .idle)
    }
}
