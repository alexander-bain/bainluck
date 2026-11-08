import XCTest
@testable import Bain_Luck

/// #10880 — the Mac's "Add to Calendar…": the .ics it hands to Calendar, the
/// gate against a double click, and the menu reaching the Mac at all.
///
/// The file is read back the way a calendar app reads it (unfold, split, then
/// unescape), so a test passes only if Calendar would see the draft's own
/// title, start, end, link and notes. The handoff itself (NSWorkspace opening
/// the file) cannot run from these iOS tests; its source is held to "no
/// EventKit" instead.
final class CalendarICS10880Tests: XCTestCase {

    /// Fri 16 Oct 2026 21:00:00Z.
    private static let now = Date(timeIntervalSince1970: 1_792_184_400)
    /// Sun 18 Oct 2026 17:00:00Z, a 1:00 PM ET NFL kick-off.
    private static let kickoff = Date(timeIntervalSince1970: 1_792_342_800)

    private func draft(
        eventID: Int = 15_327_537,
        away: String = "Buffalo Bills",
        home: String = "Kansas City Chiefs",
        sportKey: String = "americanfootball_nfl",
        start: Date = kickoff
    ) throws -> CalendarEntryDraft10880 {
        let subject = CalendarSubject10880(
            eventID: eventID, awayName: away, homeName: home, sportKey: sportKey,
            start: start, startIsTbd: false, startIsFromSchedule: true,
            status: "scheduled", venueClosedNoWinner: false
        )
        guard case .offer(let d) = CalendarEntry10880.decide(for: subject, now: Self.now) else {
            throw XCTSkip("fixture must be an offer")
        }
        return d
    }

    /// Physical lines, as written (CRLF-separated, last one empty).
    private func physicalLines(_ document: String) -> [String] {
        document.components(separatedBy: "\r\n")
    }

    /// RFC 5545 §3.1 unfolding, then NAME:VALUE pairs of the one VEVENT.
    private func properties(_ document: String) -> [String: String] {
        let unfolded = document.replacingOccurrences(of: "\r\n ", with: "")
        var out: [String: String] = [:]
        var inEvent = false
        for line in unfolded.components(separatedBy: "\r\n") {
            if line == "BEGIN:VEVENT" { inEvent = true; continue }
            if line == "END:VEVENT" { inEvent = false; continue }
            guard inEvent, let colon = line.firstIndex(of: ":") else { continue }
            out[String(line[..<colon])] = String(line[line.index(after: colon)...])
        }
        return out
    }

    /// The reverse of §3.3.11, as a calendar app applies it.
    private func unescape(_ value: String) -> String {
        var out = ""
        var escaping = false
        for character in value {
            if escaping {
                out.append(character == "n" || character == "N" ? "\n" : character)
                escaping = false
            } else if character == "\\" {
                escaping = true
            } else {
                out.append(character)
            }
        }
        return out
    }

    // MARK: - The file

    func testTheFileIsOneEventCarryingTheDraftsOwnFields() throws {
        let d = try draft()
        let document = CalendarICS10880.document(for: d, eventID: 15_327_537, now: Self.now)
        XCTAssertTrue(document.hasPrefix("BEGIN:VCALENDAR\r\nVERSION:2.0\r\n"))
        XCTAssertTrue(document.hasSuffix("END:VCALENDAR\r\n"))
        XCTAssertEqual(document.components(separatedBy: "BEGIN:VEVENT").count, 2, "exactly one event")

        let p = properties(document)
        XCTAssertEqual(p["UID"], "event-15327537@bainluck.com")
        XCTAssertEqual(p["DTSTAMP"], "20261016T210000Z")
        XCTAssertEqual(p["DTSTART"], "20261018T170000Z", "the served instant, in UTC")
        XCTAssertEqual(p["DTEND"], "20261018T203000Z", "start plus the 3.5 h planning length")
        XCTAssertEqual(p["URL"], eventShareURL(15_327_537), "the link Share sends")
        XCTAssertEqual(unescape(p["SUMMARY"] ?? ""), d.title)
        XCTAssertEqual(unescape(p["DESCRIPTION"] ?? ""), d.notes)
        XCTAssertFalse(p["SUMMARY"]?.contains("%") ?? true, "no probability in a static title")
        for absent in ["VALARM", "ATTENDEE", "ORGANIZER", "RRULE", "LOCATION"] {
            XCTAssertFalse(document.contains(absent), "\(absent): nothing the draft doesn't hold")
        }
    }

    func testEveryLineEndsInCRLFAndNoBareLineBreakSurvives() throws {
        let d = try draft()
        let lines = physicalLines(CalendarICS10880.document(for: d, eventID: 1, now: Self.now))
        XCTAssertEqual(lines.last, "", "the file ends with CRLF")
        for line in lines {
            XCTAssertFalse(line.contains("\n") || line.contains("\r"), "bare line break in: \(line)")
        }
    }

    /// The notes are three paragraphs. Escaped, they travel as one property; a
    /// raw line break would end the property and Calendar would drop the rest.
    func testTheNotesLineBreaksAreEscapedNotWritten() throws {
        let d = try draft()
        XCTAssertTrue(d.notes.contains("\n\n"), "control: the notes do hold line breaks")
        let description = try XCTUnwrap(properties(
            CalendarICS10880.document(for: d, eventID: 1, now: Self.now))["DESCRIPTION"])
        XCTAssertTrue(description.contains("\\n\\n"))
        XCTAssertFalse(description.contains("\n"))
    }

    func testTextEscapesBackslashSemicolonCommaAndEveryKindOfLineBreak() {
        XCTAssertEqual(CalendarICS10880.text(#"a\b;c,d"#), #"a\\b\;c\,d"#)
        XCTAssertEqual(CalendarICS10880.text("one\ntwo\r\nthree\rfour"), #"one\ntwo\nthree\nfour"#)
        XCTAssertEqual(CalendarICS10880.text("Brighton & Hove Albion vs Arsenal"),
                       "Brighton & Hove Albion vs Arsenal", "nothing else is touched")
        XCTAssertEqual(unescape(CalendarICS10880.text(#"x\;,y"# + "\nz")), #"x\;,y"# + "\nz",
                       "a calendar app's unescape gives the text back")
    }

    /// 75 octets, counted in UTF-8, and a fold never lands inside a character:
    /// the accented letters, the flag and the emoji below are 2 to 8 bytes each.
    func testEveryLineIsAtMost75OctetsAndUnfoldingGivesTheValueBack() throws {
        let away = "Atlético Mineiro ⚽️ São Paulo Futebol Clube 🇧🇷 Associação"
        let home = "Borussia Mönchengladbach 🇩🇪 Eintracht Frankfurt e.V. Übersee"
        let d = try draft(away: away, home: home, sportKey: "soccer_brazil_campeonato")
        let document = CalendarICS10880.document(for: d, eventID: 7, now: Self.now)
        let lines = physicalLines(document)
        XCTAssertGreaterThan(lines.filter { $0.hasPrefix(" ") }.count, 2, "control: the title and notes do fold")
        for line in lines {
            XCTAssertLessThanOrEqual(line.utf8.count, 75, "over 75 octets: \(line)")
        }
        XCTAssertEqual(unescape(properties(document)["SUMMARY"] ?? ""), "\(away) vs \(home)")
    }

    func testAFoldCountsTheContinuationSpace() {
        let folded = CalendarICS10880.fold(String(repeating: "a", count: 75 + 74 + 1))
        XCTAssertEqual(folded.map(\.utf8.count), [75, 75, 2], "74 octets plus the leading space")
        XCTAssertEqual(CalendarICS10880.fold("SUMMARY:short"), ["SUMMARY:short"])
        let twoByte = CalendarICS10880.fold(String(repeating: "é", count: 40))
        XCTAssertEqual(twoByte.first?.utf8.count, 74, "a 2-byte letter that would make 76 goes to the next line")
    }

    /// Eastern clocks go back at 2026-11-01 06:00Z (2:00 AM EDT). A game across
    /// it keeps its elapsed length in UTC; Calendar shows the wall clock.
    func testAGameAcrossTheClockChangeKeepsItsElapsedLength() throws {
        let start = Date(timeIntervalSince1970: 1_793_509_200) // 2026-11-01 05:00:00Z, 1:00 AM EDT
        let d = try draft(sportKey: "basketball_nba", start: start)
        let p = properties(CalendarICS10880.document(for: d, eventID: 9, now: Self.now))
        XCTAssertEqual(p["DTSTART"], "20261101T050000Z")
        XCTAssertEqual(p["DTEND"], "20261101T073000Z", "2.5 h elapsed, not a wall-clock span")
    }

    func testUTCStampsDropFractionsAndPadEveryField() {
        XCTAssertEqual(CalendarICS10880.utc(Date(timeIntervalSince1970: 1_792_278_000.75)), "20261017T230000Z")
        XCTAssertEqual(CalendarICS10880.utc(Date(timeIntervalSince1970: 1_767_229_261)), "20260101T010101Z")
    }

    func testTheFileNameIsTheTitleWithoutPathCharacters() throws {
        let d = try draft(away: "Packers / Bears", home: "Lions: Week 10")
        XCTAssertEqual(CalendarICS10880.fileName(for: d), "Packers - Bears vs Lions- Week 10.ics")
    }

    // MARK: - One sheet at a time

    func testASecondOpenOfTheSameGameInsideTheWindowIsRefused() {
        var gate = CalendarHandoffGate10880()
        let t0 = Self.now
        XCTAssertTrue(gate.allows(eventID: 1, at: t0))
        XCTAssertFalse(gate.allows(eventID: 1, at: t0.addingTimeInterval(0.4)), "a double click")
        XCTAssertFalse(gate.allows(eventID: 1, at: t0.addingTimeInterval(2.9)))
        XCTAssertTrue(gate.allows(eventID: 1, at: t0.addingTimeInterval(3)), "the same game, later")
        XCTAssertTrue(gate.allows(eventID: 2, at: t0.addingTimeInterval(3.1)), "another game at once")
        XCTAssertTrue(gate.allows(eventID: 2, at: t0.addingTimeInterval(1)),
                      "a clock that went backwards never jams the gate shut")
    }

    // MARK: - Source: the Mac gets the menu, and the handoff stays out of EventKit

    private func appSource(_ parts: String...) throws -> String {
        var url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()   // BainLuckTests
            .deletingLastPathComponent()   // Bain Luck (project dir)
            .appendingPathComponent("Bain Luck")
        for part in parts { url.appendPathComponent(part) }
        // Comments stripped: the doc comments name what the code must not do.
        return try String(contentsOf: url, encoding: .utf8)
            .split(separator: "\n", omittingEmptySubsequences: false)
            .filter { !$0.trimmingCharacters(in: .whitespaces).hasPrefix("//") }
            .joined(separator: "\n")
    }

    func testTheMacHandoffOpensTheFileAndNeverTouchesEventKit() throws {
        let source = try appSource("Calendar10880", "CalendarICSHandoff10880.swift")
        XCTAssertTrue(source.hasPrefix("#if os(macOS)"))
        XCTAssertTrue(source.contains("NSWorkspace.shared.open(file)"), "control: the scan reads the handoff")
        XCTAssertTrue(source.contains("gate.allows(eventID: eventID, at: now)"))
        for forbidden in ["import EventKit", "EKEventStore", "EKEvent(", "requestAccess",
                          "requestFullAccessToEvents", "requestWriteOnlyAccessToEvents", "saved", "Saved"] {
            XCTAssertFalse(source.contains(forbidden), "\(forbidden) in the Mac handoff")
        }
    }

    func testThePageMenuAndTheCardMenuReachTheMac() throws {
        let menu = try appSource("Calendar10880", "CalendarDetailMenu10880.swift")
        XCTAssertFalse(menu.hasPrefix("#if os(iOS)"), "the whole menu was iPhone-only")
        XCTAssertTrue(menu.contains(#"Label("Add to Calendar…", systemImage: "calendar.badge.plus")"#))
        XCTAssertTrue(menu.contains("CalendarHandoff10880.add(draft, eventID: pageEventId)"))
        XCTAssertTrue(menu.contains("CalendarICSHandoff10880.shared.open(draft, eventID: eventID)"))
        XCTAssertTrue(menu.contains("CalendarEditorPresenter10880.shared.present(draft)"),
                      "the iPhone keeps its editor")

        let page = try appSource("Views", "EventDetailView.swift")
        let call = try XCTUnwrap(page.range(of: "CalendarDetailMenu10880(pageEventId: eventId, event: vm.event)"))
        let from = page.index(call.lowerBound, offsetBy: -400, limitedBy: page.startIndex) ?? page.startIndex
        let before = String(page[from..<call.lowerBound])
        XCTAssertFalse(before.contains("#if os(iOS)"), "the page's menu is no longer fenced to iOS")

        let card = try appSource("Components", "CardContextMenu.swift")
        XCTAssertTrue(card.contains("CalendarHandoff10880.add(draft, eventID: event.id)"))
        XCTAssertTrue(card.contains(#"Label("Add to Calendar…", systemImage: "calendar.badge.plus")"#))
        XCTAssertFalse(card.contains("CalendarEditorPresenter10880"), "the card goes through the one handoff")
    }
}
