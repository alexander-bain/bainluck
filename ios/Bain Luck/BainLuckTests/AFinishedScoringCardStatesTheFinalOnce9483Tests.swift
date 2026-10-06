import SwiftUI
import XCTest
@testable import Bain_Luck

/// #9483 C1 — a finished event page stops restating its score in a large
/// "Final total runs / 7" tile on the scoring card.
///
/// Alex's build 37 frame: SD 3 – MIL 4, `completed`. The hero says 3–4, the runs
/// map above says "Final runs distribution" and grades its rungs, and the
/// scoring card then drew `FINAL TOTAL RUNS` / **7** in 28 pt, above a ladder
/// whose every rung the map had already drawn. The reader had to scroll past a
/// third statement of one score to reach the questions under it.
///
/// After: a finished card has no projection strip. If every rung it prints is
/// already on the map, #4782's suppression hides the card. If it holds a rung
/// of its own, it keeps the ladder and states the final once, in the ladder's
/// heading: `Final combined runs · 7`.
///
/// The view is SwiftUI and is not rasterised. What is asserted is the rules it
/// defers to (`TotalPointsSpectrumView.projectionTense`,
/// `MarketMapRail.spectrumDrawsNothingNew`, `MarketMapRail.spectrumLadderTitle`)
/// plus a narrow wiring pin, because a strip re-added inside the view would
/// pass every rule test.
final class AFinishedScoringCardStatesTheFinalOnce9483Tests: XCTestCase {

    /// The specimen's shape: ten `Over N` runs lines, 3.5 … 12.5, final 7.
    private let lines: [Double] = [3.5, 4.5, 5.5, 6.5, 7.5, 8.5, 9.5, 10.5, 11.5, 12.5]
    private let finalTotal = 7

    /// The rungs the scoring card prints, by the card's own selection rule.
    private func spectrumPrints(_ lines: [Double]) -> [Double] {
        TotalPointsSpectrumView.ladderIndices(
            sortedThresholds: lines, finalTotal: finalTotal,
            limit: TotalPointsSpectrumView.ladderRowLimit
        ).map { lines[$0] }
    }

    /// The rungs the runs map above draws, by the map's own rule.
    private func mapDraws(_ lines: [Double]) -> [Double] {
        MarketMapRail.drawnFullTotalRungs(
            outcomeNames: lines.map { "Over \($0)" },
            thresholds: lines,
            overProbabilities: lines.map { $0 < Double(finalTotal) ? 0.99 : 0.01 },
            settledTotal: finalTotal,
            limit: MarketMapRail.totalMapLadderLimit
        ).map(\.threshold)
    }

    private func finishedStrip() -> TotalPointsSpectrumView.ProjectionTense? {
        TotalPointsSpectrumView.projectionTense(
            eventStatus: "completed", canStillBeGraded: false,
            scoreboardCountsTheUnit: true, hasLiveProjection: false
        )
    }

    // MARK: - The specimen: every rung already on the map

    func testTheFinishedSpecimenWithEveryRungOnTheMapDrawsNothing() {
        let printed = spectrumPrints(lines)
        let shown = mapDraws(lines)
        XCTAssertEqual(printed, [5.5, 6.5, 7.5, 8.5, 9.5], "the card's settled window around 7")
        XCTAssertEqual(shown, [4.5, 5.5, 6.5, 7.5, 8.5, 9.5], "the map's settled window around 7")
        XCTAssertTrue(
            MarketMapRail.totalsAreRestated(printing: printed, alreadyShown: shown),
            "control: every rung the card prints is already on the map"
        )

        XCTAssertNil(finishedStrip(), "a finished card has no strip, so nothing else holds it up")
        XCTAssertTrue(
            MarketMapRail.spectrumDrawsNothingNew(
                printing: printed, alreadyShown: shown,
                isMinimalLayout: false, hasProjectionStrip: finishedStrip() != nil
            ),
            "the card would be a heading over rows the map already drew, so it goes"
        )
    }

    /// Before #9483 the 28 pt final tile counted as a strip, and that was the
    /// only thing keeping this card on the page.
    func testTheOldFinalTileWasTheOnlyThingKeepingTheCard() {
        XCTAssertFalse(MarketMapRail.spectrumDrawsNothingNew(
            printing: spectrumPrints(lines), alreadyShown: mapDraws(lines),
            isMinimalLayout: false, hasProjectionStrip: true
        ))
    }

    // MARK: - A rung of its own keeps the ladder, with the total once

    func testAFinishedCardWithAnUnshownRungKeepsItsLadderAndStatesTheTotalOnce() {
        let printed = spectrumPrints(lines)
        // The map quotes fewer `Over` lines than the card's ladder, so 9.5 is
        // only on this card.
        let shown = mapDraws([4.5, 5.5, 6.5, 7.5, 8.5])
        XCTAssertFalse(shown.contains(9.5), "control: the map did not draw 9.5")
        XCTAssertFalse(
            MarketMapRail.totalsAreRestated(printing: printed, alreadyShown: shown),
            "the card holds a rung the map does not, so it keeps its ladder"
        )
        XCTAssertFalse(MarketMapRail.spectrumDrawsNothingNew(
            printing: printed, alreadyShown: shown,
            isMinimalLayout: false, hasProjectionStrip: finishedStrip() != nil
        ), "the card draws")

        let section = MarketMapRail.spectrumSectionTitle(
            finalTotal: finalTotal, isSettled: true, canStillBeGraded: false
        )
        let ladder = MarketMapRail.spectrumLadderTitle(
            finalTotal: finalTotal, unit: "runs", isSettled: true, canStillBeGraded: false
        )
        XCTAssertEqual(section, "Final scoring")
        XCTAssertEqual(ladder, "Final combined runs · 7")
        let headings = section + " " + ladder
        XCTAssertEqual(
            headings.components(separatedBy: "7").count - 1, 1,
            "'\(headings)': the total is stated once on the card"
        )
    }

    // MARK: - No final, no number

    func testACardWithNoFinalInItsUnitStatesNoTotal() {
        let cases: [(String, String)] = [
            // A finished game with a missing score, or tennis, whose scoreboard
            // counts sets: `actualTotal` is nil.
            (MarketMapRail.spectrumLadderTitle(finalTotal: nil, unit: "games", isSettled: true,
                                               canStillBeGraded: false),
             "Settled combined games"),
            (MarketMapRail.spectrumLadderTitle(finalTotal: nil, unit: "runs", isSettled: true,
                                               canStillBeGraded: false),
             "Settled combined runs"),
            // A canceled game: not over, cannot be graded.
            (MarketMapRail.spectrumLadderTitle(finalTotal: nil, unit: "runs", isSettled: false,
                                               canStillBeGraded: false),
             "Last quoted combined runs"),
            // Upcoming or live.
            (MarketMapRail.spectrumLadderTitle(finalTotal: nil, unit: "runs", isSettled: false,
                                               canStillBeGraded: true),
             "Projected combined runs"),
        ]
        for (title, expected) in cases {
            XCTAssertEqual(title, expected)
            XCTAssertFalse(title.contains("·"), "'\(title)' states a total it does not have")
        }
    }

    /// A 0–0 final is a final: nil-vs-zero, never truthiness.
    func testAZeroFinalIsStatedAsZero() {
        XCTAssertEqual(
            MarketMapRail.spectrumLadderTitle(finalTotal: 0, unit: "runs", isSettled: true),
            "Final combined runs · 0"
        )
    }

    // MARK: - The strip: finished goes, pregame and live are unchanged

    func testAFinishedGameDrawsNoStripWhateverElseIsTrue() {
        for status in ["completed", "closed"] {
            for gate in [true, false] {
                for counts in [true, false] {
                    for pace in [true, false] {
                        XCTAssertNil(TotalPointsSpectrumView.projectionTense(
                            eventStatus: status, canStillBeGraded: gate,
                            scoreboardCountsTheUnit: counts, hasLiveProjection: pace
                        ), "\(status) gate=\(gate) counts=\(counts) pace=\(pace)")
                    }
                }
            }
        }
    }

    func testThePregameAndLiveStripsAreUnchanged() {
        typealias V = TotalPointsSpectrumView
        for status: String? in [nil, "scheduled", "suspended"] {
            XCTAssertEqual(V.projectionTense(eventStatus: status, canStillBeGraded: true,
                                             scoreboardCountsTheUnit: false, hasLiveProjection: false),
                           .pregame, "\(String(describing: status)) that can still be graded")
            XCTAssertNil(V.projectionTense(eventStatus: status, canStillBeGraded: false,
                                           scoreboardCountsTheUnit: true, hasLiveProjection: true),
                         "#4018: \(String(describing: status)) that cannot be graded draws no forecast")
        }
        XCTAssertEqual(V.projectionTense(eventStatus: "live", canStillBeGraded: true,
                                         scoreboardCountsTheUnit: true, hasLiveProjection: true),
                       .live)
        XCTAssertNil(V.projectionTense(eventStatus: "live", canStillBeGraded: true,
                                       scoreboardCountsTheUnit: false, hasLiveProjection: true),
                     "tennis: the scoreboard counts sets, so there is no pace in games")
        XCTAssertNil(V.projectionTense(eventStatus: "live", canStillBeGraded: true,
                                       scoreboardCountsTheUnit: true, hasLiveProjection: false),
                     "#9708: no pace with standing, no live strip")
    }

    // MARK: - The wiring, which no rule test can see

    func testTheViewDrawsNoFinalTileAndKeepsTheSuppression() throws {
        let code = try Self.code(at: "Bain Luck/Components/TotalPointsSpectrumView.swift")

        XCTAssertFalse(code.contains("finalStrip"), "the 28 pt final tile is gone, not renamed")
        for name in ["projectionStrip", "fullView"] {
            let body = try XCTUnwrap(Self.function(named: name, in: code), name)
            XCTAssertFalse(body.contains("actualTotal"),
                           "\(name) states the final again — the ladder heading is its one place")
        }
        let strip = try XCTUnwrap(Self.function(named: "strip", in: code))
        XCTAssertTrue(strip.contains("Self.projectionTense("),
                      "the view's strip is the rule these tests ask")
        XCTAssertTrue(code.contains("hasProjectionStrip: strip != nil"),
                      "#4782's suppression reads the strip the view will actually draw")
        let body = try XCTUnwrap(Self.function(named: "body", in: code))
        XCTAssertTrue(body.contains("else if saysNothingNew { EmptyView() }"),
                      "#4782's suppression still hides a card with nothing new")
        let ladder = try XCTUnwrap(Self.function(named: "ladderView", in: code))
        XCTAssertTrue(ladder.contains("finalTotal: actualTotal, unit: unit"),
                      "the heading's total is the value the rungs are graded with")
    }

    // MARK: - Fit

    /// The heading slot has no fixed frame. The longest graded heading must still
    /// fit the narrowest phone card on one line (320 pt less page and card
    /// insets), measured in the type the card draws.
    @MainActor
    func testTheGradedHeadingFitsTheNarrowestCard() {
        let card: CGFloat = 320 - 2 * 16 - 2 * 12
        for title in [
            MarketMapRail.spectrumLadderTitle(finalTotal: 231, unit: "points", isSettled: true),
            MarketMapRail.spectrumLadderTitle(finalTotal: 100, unit: "scoring", isSettled: true),
        ] {
            let host = hostForMeasurement(
                Text(title).font(TotalPointsSpectrumView.ladderTitleFont).lineLimit(1))
            host.view.setNeedsLayout()
            host.view.layoutIfNeeded()
            let width = host.sizeThatFits(
                in: CGSize(width: CGFloat.greatestFiniteMagnitude,
                           height: CGFloat.greatestFiniteMagnitude)).width
            XCTAssertLessThanOrEqual(width, card, "'\(title)' is \(width) pt")
        }
    }

    // MARK: - Source helpers (same idiom as #6290 / #7655)

    private static func code(at path: String) throws -> String {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()               // …/BainLuckTests
            .deletingLastPathComponent()               // …/ios/Bain Luck
            .appendingPathComponent(path)
        return try String(contentsOf: url, encoding: .utf8)
            .split(separator: "\n", omittingEmptySubsequences: false)
            .filter { !$0.trimmingCharacters(in: .whitespaces).hasPrefix("//") }
            .joined(separator: "\n")
    }

    private static func function(named name: String, in code: String) -> String? {
        let lines = code.split(separator: "\n", omittingEmptySubsequences: false).map(String.init)
        guard let start = lines.firstIndex(where: {
            $0.contains("func \(name)(") || $0.contains("var \(name):")
        }) else { return nil }
        let indent = lines[start].prefix(while: { $0 == " " }).count
        let close = String(repeating: " ", count: indent) + "}"
        guard let end = lines[(start + 1)...].firstIndex(where: { $0 == close }) else { return nil }
        return lines[start...end].joined(separator: "\n")
    }
}
