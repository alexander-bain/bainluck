import XCTest
@testable import Bain_Luck

/// #10236 — a live prop quote last observed more than 30 minutes ago is not a
/// current chance (Root 0704Z, mirroring the question catalog's live rule,
/// #10877: `SourceAge.liveStaleAfter`, strict `>`, an undatable stamp shown
/// with no age claim).
///
/// Retained 15195971 (Nuggets @ Thunder, Q3, read at 03:14:01Z) drew
/// Hartenstein 9+ at 47% from a quote observed 630.4 minutes earlier, beside
/// Chet 15+ observed 3.35 seconds earlier. The route body below
/// (`Fixtures/game-markets-10236-during-matrix.route.json`, quotes observed
/// 07:08Z on 2026-10-03) carries those AGES: each edited row takes one of the
/// specimen's served `observed_at` stamps and is read at the specimen's clock.
/// The prices stay the route body's own.
@MainActor
final class AStaleLivePropIsNotACurrentChance10236Tests: XCTestCase {

    private static let fixtureURL =
        URL(fileURLWithPath: #filePath).deletingLastPathComponent()
            .appendingPathComponent("Fixtures")
            .appendingPathComponent("game-markets-10236-during-matrix.route.json")

    private static let judge1 = "s:aaron judge|hits|full_game|ge:1|over"
    private static let judge2 = "s:aaron judge|hits|full_game|ge:2|over"
    private static let judge3 = "s:aaron judge|hits|full_game|ge:3|over"
    private static let judge4 = "s:aaron judge|hits|full_game|ge:4|over"

    /// The specimen's clock and three of its served stamps.
    private static let specimenNow = "2026-10-23T03:14:01Z".asDate!
    private static let hartenstein = "2026-10-22T16:43:34.717526+00:00"   // 630.4 min
    private static let shai = "2026-10-23T02:54:46.900866+00:00"          // 19.2 min
    private static let chet = "2026-10-23T03:13:57.646761+00:00"          // 3.35 s

    /// The route body with the named rows' `observed_at` replaced, and — when
    /// `others` is given — every other row's too.
    private func during(_ stamps: [String: Any], others: Any? = nil) throws -> DuringPlayerProps {
        var dict = try XCTUnwrap(JSONSerialization.jsonObject(with: Data(contentsOf: Self.fixtureURL)) as? [String: Any])
        var block = try XCTUnwrap(dict["during_player_props"] as? [String: Any])
        var rows = try XCTUnwrap(block["rows"] as? [[String: Any]])
        if let others {
            for i in rows.indices {
                var current = try XCTUnwrap(rows[i]["current"] as? [String: Any])
                current["observed_at"] = others
                rows[i]["current"] = current
            }
        }
        for (key, stamp) in stamps {
            let i = try XCTUnwrap(rows.firstIndex { $0["question_key"] as? String == key }, key)
            var current = try XCTUnwrap(rows[i]["current"] as? [String: Any])
            current["observed_at"] = stamp
            rows[i]["current"] = current
        }
        block["rows"] = rows
        dict["during_player_props"] = block
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try XCTUnwrap(try decoder.decode(
            GameMarketsResponse.self, from: JSONSerialization.data(withJSONObject: dict)).duringPlayerProps)
    }

    private func row(_ props: DuringPlayerProps, _ key: String) throws -> DuringPropRow {
        try XCTUnwrap(props.rows.first { $0.questionKey == key })
    }

    private func specimenAges() throws -> DuringPlayerProps {
        try during([Self.judge2: Self.hartenstein, Self.judge3: Self.shai], others: Self.chet)
    }

    // MARK: - The specimen's ages

    func testAQuoteHoursOldPrintsNoCurrentNumberAndKeepsItsLastQuote() throws {
        let old = try row(try specimenAges(), Self.judge2)
        XCTAssertEqual(old.current.quotedProbability, 0.48, "the served quote itself is untouched")
        XCTAssertTrue(old.current.isStale(now: Self.specimenNow))
        XCTAssertNil(old.current.currentProbability(now: Self.specimenNow))
        XCTAssertEqual(EventPropsMatrixLayout.cellText(old, now: Self.specimenNow), EventPropsMatrixLayout.staleCellText)
        XCTAssertNotEqual(EventPropsMatrixLayout.cellText(old, now: Self.specimenNow), absentProbabilityMarker,
                          "stale is not the dash, which means no price exists")
        XCTAssertNotNil(EventPropsMatrixLayout.basisText(old), "provenance stays for the detail")
    }

    func testAStaleQuoteIsComparedWithNothingAndNotSpokenAsCurrent() throws {
        let old = try row(try specimenAges(), Self.judge2)
        XCTAssertEqual(old.comparison?.isComparable, true, "control: the server proved a pregame delta")
        XCTAssertNil(EventPropsMatrixLayout.changePoints(old, now: Self.specimenNow))
        XCTAssertNil(EventPropsMatrixLayout.changeText(old, now: Self.specimenNow))
        let spoken = EventPropsMatrixLayout.accessibilityLabel(old, stat: nil, now: Self.specimenNow)
        XCTAssertTrue(spoken.contains("no recent probability update"), spoken)
        XCTAssertFalse(spoken.contains("48"), "the old number is not spoken: \(spoken)")
        XCTAssertFalse(spoken.contains("since pregame"), spoken)
    }

    func testFreshQuotesAndAFreshZeroStayCurrent() throws {
        let props = try specimenAges()
        let zero = try row(props, Self.judge4)
        XCTAssertEqual(EventPropsMatrixLayout.cellText(zero, now: Self.specimenNow), "<1%",
                       "a quoted 0 seen 3 seconds ago is a real, current quote")
        let nineteen = try row(props, Self.judge3)
        XCTAssertEqual(nineteen.current.currentProbability(now: Self.specimenNow), nineteen.current.quotedProbability,
                       "19.2 minutes is inside the 30-minute bound")
        let fresh = try row(props, Self.judge1)
        XCTAssertEqual(EventPropsMatrixLayout.changeText(fresh, now: Self.specimenNow), "+17%",
                       "a current quote keeps its comparable delta")
    }

    func testTheGridCountsTheStaleQuotesForItsLegend() throws {
        let grid = try XCTUnwrap(EventPropsMatrixLayout.grid(try specimenAges(), statKey: "hits", now: Self.specimenNow))
        XCTAssertEqual(grid.staleCount, 1)
        let drawn = grid.players.flatMap { $0.cells.values }.map(\.questionKey)
        XCTAssertTrue(drawn.contains(Self.judge2), "the stale question stays in the grid and opens")
    }

    // MARK: - The boundary, crossing and recovery

    func testThirtyMinutesExactlyIsCurrentAndOneSecondMoreIsNot() throws {
        let observed = "2026-10-03T07:08:40Z"
        let at = observed.asDate!
        let props = try during([Self.judge2: observed])
        let cell = try row(props, Self.judge2)
        XCTAssertEqual(EventPropsMatrixLayout.cellText(cell, now: at.addingTimeInterval(30 * 60)), "48%",
                       "strict >: at 30 minutes the quote is still current")
        XCTAssertEqual(EventPropsMatrixLayout.cellText(cell, now: at.addingTimeInterval(30 * 60 + 1)),
                       EventPropsMatrixLayout.staleCellText, "a cell left on screen flips as the clock passes")
    }

    func testANewerObservationOfTheSameValueRestoresIt() throws {
        let now = "2026-10-03T08:00:00Z".asDate!
        let old = try row(try during([Self.judge2: "2026-10-03T07:08:40+00:00"]), Self.judge2)
        let seenAgain = try row(try during([Self.judge2: "2026-10-03T07:59:30+00:00"]), Self.judge2)
        XCTAssertEqual(old.current.quotedProbability, seenAgain.current.quotedProbability, "same value")
        XCTAssertNil(old.current.currentProbability(now: now))
        XCTAssertEqual(EventPropsMatrixLayout.cellText(seenAgain, now: now), "48%")
        XCTAssertEqual(EventPropsMatrixLayout.changeText(seenAgain, now: now), "+10%")
    }

    func testAnUndatedQuoteIsShownWithNoAgeClaim() throws {
        let undated = try row(try during([Self.judge2: NSNull()]), Self.judge2)
        XCTAssertNil(undated.current.observedAt)
        XCTAssertFalse(undated.current.isStale(now: .distantFuture), "a price we cannot date is not called stale")
        XCTAssertEqual(EventPropsMatrixLayout.cellText(undated, now: .distantFuture), "48%")
    }

    // MARK: - Wiring

    private func source(_ path: String) throws -> String {
        let root = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
        return try String(contentsOf: root.appendingPathComponent(path), encoding: .utf8)
    }

    func testThePageHandsTheMatrixItsDisplayClockAndTheMatrixTicks() throws {
        let page = try source("Bain Luck/Views/EventDetailView.swift")
        let mount = try XCTUnwrap(page.range(of: "EventPropsMatrixView("))
        XCTAssertTrue(page[mount.upperBound...].prefix(1200).contains("displayAsOf: displayAsOf,"))
        let matrix = try source("Bain Luck/Components/EventPropsMatrixView.swift")
        XCTAssertEqual(matrix.components(separatedBy: "let now = displayAsOf ?? tick.date").count - 1, 2,
                       "the matrix and its detail sheet each read the display clock on a minute tick")
        XCTAssertFalse(matrix.contains("row.current.quotedProbability == nil ?"),
                       "a cell's weight follows the current chance, not the raw quote")
        XCTAssertTrue(matrix.contains("Text(\"Last quote \\(EventPropsMatrixLayout.exactPercent(last))\")"),
                      "the detail keeps the last quote, named as the last one")
    }
}
