import XCTest
import SwiftUI
@testable import Bain_Luck

/// #8651 (build 30) — **a finger on the page's win-probability chart shows the
/// moment it is on, even before the game has a scoring play.**
///
/// WHAT THE READER SAW: Alex, installed build 30, Sep 28 2026: "timeline
/// scrubbing smooth but no tooltip appears". The page hands the chart its
/// readout card only for a live or finished game with a scoring play, so on a
/// pre-game page (CHC @ SD, 15320240) — and a scoreless live one — a scrub drew
/// a bare crosshair and nothing else. Simulator frames of that page, before and
/// after, under a held finger: `artifacts/native-8651-tooltip/`.
///
/// The fix floats the fullscreen chart's own card over the plot while a finger
/// is on it. These tests pin the decisions and the wiring; the frames show it
/// drawn.
final class TheInlineChartScrubShowsATooltip8651Tests: XCTestCase {

    private func point(scoringPlay: ScoringPlay? = nil) -> GamePlayPoint {
        GamePlayPoint(timestamp: "2026-09-27T20:06:00Z", homeProb: 0.53, awayProb: 0.47,
                      homeScore: nil, awayScore: nil, period: nil, clock: nil,
                      scoringPlay: scoringPlay)
    }

    private func card(page: GamePlayCardView? = nil, home: String? = "San Diego Padres",
                      finished: Bool = false) -> GamePlayCardView? {
        OddsChartView.inlineScrubCard(page: page, homeTeam: home, awayTeam: "Chicago Cubs",
                                      colors: nil, homeLogo: nil, awayLogo: nil, finished: finished)
    }

    // MARK: - Which charts float a card

    func testAPreGameChartGetsAFloatingCard() throws {
        let card = try XCTUnwrap(card(), "a pre-game chart must have something to show under a finger")
        XCTAssertTrue(card.floats)
        XCTAssertTrue(card.pinsProbabilities, "the card's job is the two numbers")
        XCTAssertEqual(card.homeTeam, "San Diego Padres")
        XCTAssertEqual(card.awayTeam, "Chicago Cubs")
        XCTAssertNil(card.lastPoint, "it shows only the scrubbed moment, never a resting one")
    }

    /// #925's card above the plot already rewrites under the finger: never two.
    func testAChartThePageGaveACardFloatsNone() {
        let page = GamePlayCardView(homeTeam: "Padres", awayTeam: "Cubs", lastPoint: point())
        XCTAssertNil(card(page: page))
    }

    func testNoNamesNoCard() {
        XCTAssertNil(card(home: nil))
    }

    func testAFinishedGamesCardPrintsItsResult() {
        XCTAssertEqual(card(finished: true)?.gameFinished, true)
        XCTAssertEqual(card(finished: false)?.gameFinished, false)
    }

    // MARK: - What it prints

    func testAFloatingCardStillPrintsTheNumbersOnAScoringPlay() throws {
        let json = #"{"description":"Solo home run","type":"Home Run"}"#
        let homer = try JSONDecoder().decode(ScoringPlay.self, from: Data(json.utf8))
        let rows = GamePlayCardView.rows(for: point(scoringPlay: homer), pinsProbabilities: true)
        XCTAssertTrue(rows.probabilities)
        XCTAssertTrue(rows.play)
    }

    /// A pre-game chart spans days; the card names the day like the axis does.
    func testTheFloatingClockNamesItsDay() throws {
        let p = point()
        let date = try XCTUnwrap(p.timestamp.asDate)
        let weekday = date.formatted(.dateTime.weekday(.abbreviated))
        XCTAssertTrue(p.datedWallClockDisplay.hasPrefix(weekday), p.datedWallClockDisplay)
        XCTAssertFalse(p.wallClockDisplay.hasPrefix(weekday), "the in-game card's bare clock is unchanged")
    }

    // MARK: - Where it sits

    func testTheCardSitsInTheCornerAwayFromTheCrosshair() {
        let alignment = OddsChartSelectionOverlay.floatingCardAlignment
        XCTAssertEqual(alignment(40, 300), .topTrailing)
        XCTAssertEqual(alignment(260, 300), .topLeading)
    }

    // MARK: - The wiring (comment-stripped scans: the bodies are not rendered in tests)

    private func code(_ path: String) throws -> String {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()   // BainLuckTests
            .deletingLastPathComponent()   // Bain Luck (project dir)
            .appendingPathComponent(path)
        return try String(contentsOf: url, encoding: .utf8)
            .split(separator: "\n", omittingEmptySubsequences: false)
            .map { line -> String in
                guard let slashes = line.range(of: "//") else { return String(line) }
                return String(line[line.startIndex..<slashes.lowerBound])
            }
            .joined(separator: "\n")
            .filter { !$0.isWhitespace }
    }

    /// Build 30's defect was the inline chart having NO card to show; the
    /// decisions above mean nothing unless the page's chart asks for one.
    func testTheInlineChartPassesItsFloatingCardToTheOverlay() throws {
        let chart = try code("Bain Luck/Components/OddsChartView.swift")
        XCTAssertTrue(chart.contains("sharesPageAxis:true,pageGaveCard:readout!=nil,floatingCard:Self.inlineScrubCard(page:readout,"),
                      "the page's chart no longer asks for its scrub tooltip")
        XCTAssertTrue(chart.contains("sportKey:sportKey,floatingCard:floatingCard)"),
                      "the chart no longer hands its tooltip to the selection overlay")
    }

    /// Only under a finger, and inside the selection leaf so a scrub still
    /// rebuilds nothing else (#8651's first half).
    func testTheOverlayDrawsTheCardOnlyWhileAFingerIsOnTheChart() throws {
        let overlay = try code("Bain Luck/Components/OddsChartSelection.swift")
        let scrubbing = try XCTUnwrap(overlay.range(of: "ifletdate=selection.date,letx=proxy.position(forX:date){"))
        let drawn = try XCTUnwrap(overlay.range(of: "floatingCard.showing(point)"))
        XCTAssertLessThan(scrubbing.lowerBound, drawn.lowerBound)
        let closing = try XCTUnwrap(overlay.range(of: "Color.clear", range: scrubbing.upperBound..<overlay.endIndex))
        XCTAssertLessThan(drawn.upperBound, closing.lowerBound, "the card escaped the selection branch")
    }
}
