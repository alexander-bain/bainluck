import XCTest
@testable import Bain_Luck

/// #6444 line 18, the two RENDER halves: *"Search shows raw baseball_other and
/// unexplained excitement emoji; screenshot rows have no dates, so repeated
/// opponents cannot be distinguished from separate series games."*
///
/// (The `baseball_other` half is a server label, #5657/#6465, lane1's. Nothing
/// here touches it; `testTheFilterPillsAreTheOnesInTheScreenshot` only pins that
/// the fixture still carries the pill Alex saw, so this file cannot be read as
/// having fixed it.)
///
/// THE SCREENSHOT (`artifacts/alex-phone-20260915/Screenshot 2026-09-15 at
/// 3.47.41 PM.png`), three rows deep and nothing below the fold:
///
///     Boston Red Sox vs Baltimore Orioles    3 - 1   😴 34   >
///     MLB  FINAL
///     Boston Red Sox vs Baltimore Orioles    1 - 0   ⚡ 72   >
///     MLB  FINAL
///     Boston Red Sox vs Baltimore Orioles    6 - 5           >
///     MLB  FINAL
///
/// Two defects, and they are independent:
///
/// 1. **No row says when.** Every one of the three carries `commence_time` and
///    always has; `searchEventRow` drew it only on `status == "scheduled"`
///    rows, i.e. on the rows whose badge already reads "In 3h". A reader cannot
///    tell these three apart, and cannot tell a three-game series from three
///    copies of one game — which is the shape of a real matching defect
///    (gotcha: twins), so the page is unable to show a reader the difference
///    between a healthy result set and a broken one.
/// 2. **"😴 34" explains nothing.** Alex: "I wasn't sure how to interpret the
///    emoji." The same payload carries `"label": "Quiet"` and `"Exciting"`,
///    which the compact pill threw away in favour of the number.
final class SearchRowIsDatedAndExplained6444Tests: XCTestCase {

    // MARK: - The payload

    private func decodeFixture() throws -> SearchResponse {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(SearchResponse.self,
                                  from: Data(SearchRedSoxProdFixture.json.utf8))
    }

    /// The three FINAL rows of the screenshot, in the order they were drawn.
    private func orioleRows() throws -> [SearchEvent] {
        let rows = try decodeFixture().results.filter { EventState.isFinished($0.status) }
        XCTAssertEqual(rows.count, 3, "the fixture is no longer the three-row specimen")
        return rows
    }

    /// A fixed `now` so every date assertion below is a function of the code and
    /// not of the day the suite runs (gotcha #44). It is the afternoon Alex took
    /// the screenshot, so "yesterday" and "last week" mean what they meant to
    /// him.
    private let shotTime = ISO8601DateFormatter().date(from: "2026-09-15T22:47:41Z")!

    // MARK: - Half 1: every row says when

    /// The style the search row asks for on a settled row, so every assertion
    /// below is about the string the reader actually gets.
    private func rowDate(_ row: SearchEvent) -> String? {
        RelativeTimeText.text(
            for: row.commenceTime, now: shotTime,
            style: EventState.isFinished(row.status) ? .dayOnly : .full
        )
    }

    /// THE SHIP. Three rows that read identically now read differently, and the
    /// thing that differs is the date of the game.
    func testAlexsThreeIdenticalRowsNowEachPrintTheirOwnDate() throws {
        let dates = try orioleRows().map { row -> String in
            XCTAssertTrue(
                EventState.listRowPrintsDate(row.status),
                "a FINAL row is back to drawing no date"
            )
            return rowDate(row) ?? ""
        }
        for date in dates {
            XCTAssertFalse(date.isEmpty, "a row in the specimen drew no date at all")
        }
        XCTAssertEqual(
            Set(dates).count, 3,
            "the three rows still print the same line: \(dates)"
        )
    }

    /// ANTI-VACUITY, and the only honest way to state the defect: the deleted
    /// gate, run over the same rows. If this ever passes, the fixture has been
    /// recaptured from a tree where the bug is gone and every assertion above is
    /// agreeing with itself.
    func testTheDeletedGateDrewNothingOnAllThreeOfThem() throws {
        for row in try orioleRows() {
            // `searchEventRow`'s condition before this ship, verbatim in
            // behaviour.
            let oldGate = row.status == "scheduled"
            XCTAssertFalse(
                oldGate,
                "row \(row.id) is not FINAL, so it is not the specimen"
            )
        }
    }

    /// And the rest of the row really is identical, so the date is not a nicety
    /// on top of some other distinguisher. The scores differ (3-1, 1-0, 6-5) and
    /// that is not identity: a score says how a game went, never which game it
    /// was, and two of a series can end 1-0 twice.
    func testNothingElseOnThoseRowsTellsThemApart() throws {
        let rows = try orioleRows()
        let titles = rows.map { "\($0.awayTeam) vs \($0.homeTeam)" }
        XCTAssertEqual(Set(titles).count, 1, "the fixture rows no longer share a title")
        XCTAssertEqual(Set(rows.map { $0.sport ?? "" }).count, 1)
        XCTAssertEqual(Set(rows.map { $0.status ?? "" }).count, 1)
    }

    /// The scheduled row keeps exactly what it had. This ship widens a gate; a
    /// widened gate that moves the rows that already passed it is a rewrite.
    func testTheScheduledRowIsUnchanged() throws {
        let scheduled = try XCTUnwrap(
            try decodeFixture().results.first { $0.status == "scheduled" },
            "the fixture lost its scheduled control row"
        )
        XCTAssertTrue(EventState.listRowPrintsDate(scheduled.status))
        XCTAssertNotNil(RelativeTimeText.text(for: scheduled.commenceTime, now: shotTime))
    }

    /// The one state deliberately left out, asserted rather than left implicit:
    /// a live row's badge IS the clock ("Bottom 7th"), and it is the widest
    /// badge on the row.
    func testALiveRowStillPrintsNoDate() {
        XCTAssertFalse(EventState.listRowPrintsDate("live"))
    }

    /// The rule is positive, so the states nobody enumerated get the date too —
    /// that is the whole reason it is not a list of statuses. `postponed` is not
    /// a status this app handles anywhere, which is the point: it is the next
    /// one to arrive.
    func testEveryOtherStateIncludingUnknownOnesPrintsItsDate() {
        for status in ["completed", "closed", "suspended", "scheduled", "postponed", "delayed", nil] {
            XCTAssertTrue(
                EventState.listRowPrintsDate(status),
                "\(status ?? "nil") rows draw no date, which is the denylist shape #4021 was filed on"
            )
        }
    }

    // MARK: - Half 1, the format

    /// What the three rows actually say. Pinned by shape and by DIFFERENCE
    /// rather than by exact strings: the formatter is device-local by design
    /// (`DateFormatter` with no locale or time zone), so the month name and the
    /// hour are the simulator's, and an exact-string assertion here would be a
    /// test of the machine — the class `HostedMeasurement` documents.
    func testTheDatesReadAsDatesAndNotAsOffsets() throws {
        for row in try orioleRows() {
            let text = try XCTUnwrap(rowDate(row))
            // Sept 3/4/6 against a Sept 15 now: all three are more than a week
            // back, so all three take the month-and-day arm.
            for relative in ["Today", "Tomorrow", "Yesterday"] {
                XCTAssertFalse(
                    text.hasPrefix(relative),
                    "row \(row.id) printed \"\(text)\" about a game eleven days old"
                )
            }
            // A settled row prints the day and no clock — the measured wrap.
            XCTAssertFalse(
                text.contains(":"),
                "row \(row.id) printed \"\(text)\"; a played game's kick-off time is what wrapped the line"
            )
            XCTAssertTrue(
                text.contains(" "),
                "row \(row.id) printed \"\(text)\", which is not a month and a day"
            )
        }
    }

    /// The wrap this style exists for, as a measurement rather than as a
    /// sentence. The `dayOnly` string has to be materially shorter than the one
    /// that wrapped — a style that saves two characters would have been
    /// cosmetics.
    func testTheSettledFormIsTheShortOne() throws {
        for row in try orioleRows() {
            let full = try XCTUnwrap(
                RelativeTimeText.text(for: row.commenceTime, now: shotTime, style: .full))
            let short = try XCTUnwrap(rowDate(row))
            XCTAssertTrue(
                full.hasPrefix(short),
                "\"\(short)\" is not \"\(full)\" with the clock removed — the two forms have diverged"
            )
            XCTAssertLessThan(short.count, full.count - 6)
        }
    }

    /// The four arms, against a fixed clock. `Calendar.current`-relative, so
    /// stated as day offsets from the anchor rather than as literal dates — an
    /// anchor built by branching on the real clock is the trap gotcha #44 is
    /// about, and an anchor built by hand in one time zone is the same trap
    /// wearing a date.
    func testTheFourArmsOfTheFormatter() {
        let cal = Calendar.current
        func iso(_ date: Date) -> String {
            let f = ISO8601DateFormatter()
            f.formatOptions = [.withInternetDateTime]
            return f.string(from: date)
        }
        func text(daysFromNow days: Int) -> String {
            let noonToday = cal.date(byAdding: .hour, value: 12, to: cal.startOfDay(for: shotTime))!
            let date = cal.date(byAdding: .day, value: days, to: noonToday)!
            return RelativeTimeText.text(for: iso(date), now: shotTime) ?? ""
        }
        XCTAssertTrue(text(daysFromNow: 0).hasPrefix("Today "))
        XCTAssertTrue(text(daysFromNow: 1).hasPrefix("Tomorrow "))
        XCTAssertTrue(text(daysFromNow: -1).hasPrefix("Yesterday "))
        // Two to six days ahead is the weekday arm; anything else is the date.
        XCTAssertFalse(text(daysFromNow: 3).contains(","))
        XCTAssertTrue(text(daysFromNow: 30).contains(","))
        // A PAST week is deliberately NOT the weekday arm: "Wed 7:05 PM" about a
        // game eleven days ago would be read as the coming Wednesday.
        XCTAssertTrue(text(daysFromNow: -3).contains(","))

        // And the same four arms with the clock dropped. "Yesterday" beside
        // FINAL is the whole line a settled row wants; none of them carries a
        // time, which is the only thing this style changes.
        func dayOnly(daysFromNow days: Int) -> String {
            let noonToday = cal.date(byAdding: .hour, value: 12, to: cal.startOfDay(for: shotTime))!
            let date = cal.date(byAdding: .day, value: days, to: noonToday)!
            return RelativeTimeText.text(for: iso(date), now: shotTime, style: .dayOnly) ?? ""
        }
        XCTAssertEqual(dayOnly(daysFromNow: 0), "Today")
        XCTAssertEqual(dayOnly(daysFromNow: 1), "Tomorrow")
        XCTAssertEqual(dayOnly(daysFromNow: -1), "Yesterday")
        for days in [-30, -3, 3, 30] {
            XCTAssertFalse(
                dayOnly(daysFromNow: days).contains(":"),
                "the day-only form printed a clock \(days) days out"
            )
            XCTAssertFalse(dayOnly(daysFromNow: days).isEmpty)
        }
    }

    func testNoDateMeansNoLineRatherThanAnEmptyOne() {
        XCTAssertNil(RelativeTimeText.text(for: nil, now: shotTime))
        XCTAssertNil(RelativeTimeText.text(for: "", now: shotTime))
        XCTAssertNil(RelativeTimeText.text(for: "not a date", now: shotTime))
    }

    // MARK: - Half 2: the pill says a word

    /// Alex's two badges, by name. The pill he could not read said "34" and
    /// "72"; it now says what the server has been calling them all along.
    func testTheTwoBadgesInTheScreenshotNowPrintTheirServedWord() throws {
        let withEI = try orioleRows().compactMap { row -> (Int, EIData)? in
            guard let ei = row.ei ?? row.pulse else { return nil }
            return (row.id, ei)
        }
        XCTAssertEqual(withEI.count, 2, "the specimen no longer carries the two badges")

        let byID = Dictionary(uniqueKeysWithValues: withEI)
        let quiet = try XCTUnwrap(byID[15305465])      // 😴 34, the 3-1 game
        let exciting = try XCTUnwrap(byID[15302361])   // ⚡ 72, the 1-0 game

        XCTAssertEqual(EIBadgeView.compactText(for: quiet), "Quiet")
        XCTAssertEqual(EIBadgeView.compactText(for: exciting), "Exciting")

        // ANTI-VACUITY: the deleted line, over the same two.
        XCTAssertEqual("\(quiet.score ?? 0)", "34")
        XCTAssertEqual("\(exciting.score ?? 0)", "72")
        for (_, ei) in withEI {
            XCTAssertNotEqual(
                EIBadgeView.compactText(for: ei), "\(ei.score ?? 0)",
                "the pill is printing the bare score again"
            )
        }
    }

    /// The whole served vocabulary, so a pill cannot start printing a word this
    /// tier made up. These are `get_ei_label`'s eight
    /// (`backend/app/utils/excitement_index.py`).
    func testThePillPrintsTheServersWordUnchanged() {
        for word in ["Flat", "Quiet", "Average", "Competitive",
                     "Engaging", "Exciting", "Must-Watch", "Incredible"] {
            XCTAssertEqual(EIBadgeView.compactText(for: ei(score: 50, label: word)), word)
        }
    }

    /// A payload with no label degrades to the number rather than to a blank
    /// pill — the label is derived from the score by a total function server
    /// side, so this arm is unreachable today and is the fallback it looks like,
    /// not a second vocabulary.
    func testAnAbsentOrBlankLabelFallsBackToTheScoreItUsedToPrint() {
        XCTAssertEqual(EIBadgeView.compactText(for: ei(score: 34, label: nil)), "34")
        XCTAssertEqual(EIBadgeView.compactText(for: ei(score: 34, label: "")), "34")
        XCTAssertEqual(EIBadgeView.compactText(for: ei(score: 34, label: "   ")), "34")
        // And with neither, the pill still says something rather than nothing.
        XCTAssertEqual(
            EIBadgeView.compactText(for: EIData(score: nil, rawScore: 62, status: nil,
                                                label: nil, emoji: "😴", metadata: nil)),
            "62"
        )
    }

    private func ei(score: Int, label: String?) -> EIData {
        EIData(score: score, rawScore: score, status: nil, label: label,
               emoji: "⚡", metadata: nil)
    }

    // MARK: - The fixture is still the screenshot

    /// The other pill, and it is NOT this lane's and is NOT in this diff.
    ///
    /// Alex's screenshot shows two filter pills, "MLB" and **"baseball_other"** —
    /// the raw key printed as the name of a sport. That half is served
    /// (#5657, lane1) and it had already landed when this fixture was captured
    /// on 2026-09-15: the same facet now reads `name: "Other Baseball"` beside
    /// the unchanged `key: "baseball_other"`. So the assertion is that the
    /// PHONE prints a name and never a key — true of this capture because the
    /// server was fixed, and the thing that would go wrong on the phone is a
    /// pill built from `key` instead of `name`.
    func testTheFilterPillPrintsANameAndNeverTheRawKey() throws {
        let sports = try XCTUnwrap(try decodeFixture().sports)
        XCTAssertEqual(sports.map(\.key), ["baseball_mlb", "baseball_other"])
        XCTAssertEqual(sports.map(\.name), ["MLB", "Other Baseball"])
        for facet in sports {
            XCTAssertFalse(
                facet.name.contains("_"),
                "the pill would print \"\(facet.name)\" — an underscore is the raw key reaching a reader"
            )
        }
    }

    // MARK: - The call site

    /// Both halves live in functions a test can call, and a `ViewBuilder` can
    /// walk away from either without a test noticing — the date gate is one
    /// `if` in a 1,200-line view and the pill text is one interpolation. So the
    /// row is read for the two calls.
    func testTheSearchRowReadsTheSharedRuleRatherThanASecondCopy() throws {
        let text = try XCTUnwrap(
            appSource("Bain Luck/Views/SearchView.swift"),
            "the scan never reached SearchView"
        )
        let codeLines = text.components(separatedBy: .newlines)
            .map { $0.components(separatedBy: "//").first ?? $0 }

        XCTAssertTrue(
            codeLines.contains { $0.contains("EventState.listRowPrintsDate(") },
            "the search row no longer asks the shared rule whether to print a date"
        )
        for line in codeLines where line.contains("RelativeTimeText(") {
            XCTAssertFalse(
                line.contains("\"scheduled\""),
                "a date is gated on the scheduled status again: \(line)"
            )
        }
        XCTAssertFalse(
            codeLines.contains { $0.contains("status == \"scheduled\"") && $0.contains("commenceTime") },
            "the deleted gate is back on a row in SearchView"
        )
        XCTAssertTrue(
            codeLines.contains { $0.contains(".dayOnly") && $0.contains("isFinished") },
            "the settled row no longer picks the clockless form, and its date wraps"
        )
    }

    /// The pill is a shared component, and that is deliberate: search and the
    /// Discover/Sports card draw the same badge and Alex met the unexplained one
    /// on search first. A private copy in either would put the number back on
    /// one surface only.
    func testNoViewPrintsTheCompactBadgeItself() throws {
        let badge = try XCTUnwrap(
            appSource("Bain Luck/Components/EIBadgeView.swift"),
            "the scan never reached EIBadgeView"
        )
        XCTAssertTrue(badge.contains("static func compactText(for ei: EIData)"))
        XCTAssertFalse(
            badge.contains("Text(\"\\(displayScore)\")"),
            "the compact pill is interpolating the bare score again"
        )
        // `lg` keeps the number, because it prints the scale with it.
        XCTAssertTrue(
            badge.contains("\\(displayScore) / 100"),
            "the large badge lost the scored form, which is the one place the number reads"
        )
    }

    // MARK: - The tree scan

    private var projectRoot: URL {
        URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()   // BainLuckTests
            .deletingLastPathComponent()   // Bain Luck (project dir)
    }

    private func appSource(_ relativePath: String) -> String? {
        try? String(contentsOf: projectRoot.appendingPathComponent(relativePath), encoding: .utf8)
    }
}
