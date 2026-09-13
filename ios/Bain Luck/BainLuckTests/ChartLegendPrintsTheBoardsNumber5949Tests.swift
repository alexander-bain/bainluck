import XCTest
@testable import Bain_Luck

/// #5949 — THE CARD ANSWERED ITS OWN QUESTION TWICE, TWO CENTIMETRES APART.
///
/// US Open hub, MEN'S SINGLES, production 15:51Z on finals day, one frame and no
/// scrolling between the two lines (`artifacts-native-020/n147-hub-AFTER-s07.png`):
///
///     legend:  ● A. Zverev 59%   ● B. Shelton 42%   ● G. Dimitrov <1%
///     rows:    1 Alexander Zverev 59%    2 Ben Shelton 41%
///
/// #5893 gave the board's ROW LIST the pair rule — a draw down to its final asks
/// one question, so the two percentages are rounded ONCE and the second side is
/// derived. The chart legend directly above those rows was never in that fix:
/// `RaceChartView.legend` called `formatProbabilityOrDash(entry.probability)`
/// with no rendered percent, so it rounded each contender alone. `0.585 / 0.415`
/// is the complement pair on the venues' half-cent grid that half-up sends BOTH
/// up — 59 and 42 — which is #2452 / #2060 / UX-P114 for the sixth time.
///
/// The fix is the one the rows already use: the board's decided percent travels
/// onto the series, keyed by `entity_key`, and the legend prints THAT. The pair
/// rule is deliberately NOT re-derived in the chart — a second copy of the
/// [0.99, 1.01] band is a second place for it to drift.
final class ChartLegendPrintsTheBoardsNumber5949Tests: XCTestCase {

    // MARK: - 🔴 The defect

    func testTheLegendPrintsTheSameNumberAsTheRowBeneathIt() throws {
        let board = try XCTUnwrap(duel().boards.first)
        let chart = try XCTUnwrap(board.chart)

        let legend = chart.series.map {
            formatProbabilityOrDash($0.probability, renderedPercent: $0.renderedPercent)
        }
        XCTAssertEqual(legend, ["59%", "41%"])
        XCTAssertEqual(
            legend, board.rows.map(\.percentText),
            "one card, one question, one answer — the legend and the rows are "
            + "the same two numbers or the card is lying to a reader who can "
            + "see both of them at once")
    }

    func testTheMeasurementCanActuallySeeTheDefect() {
        // Without this arm the assertion above passes on any pair that happens
        // not to straddle a half-cent, forever. 0.415 rounded ALONE is the 42%
        // that was on Alex's screen.
        XCTAssertEqual(formatProbabilityOrDash(0.415), "42%")
        XCTAssertEqual(formatProbabilityOrDash(0.585), "59%")
    }

    func testTheSeriesCarriesTheBoardsIntegerNotItsOwn() throws {
        let chart = try XCTUnwrap(try XCTUnwrap(duel().boards.first).chart)
        XCTAssertEqual(chart.series.map(\.renderedPercent), [59, 41])
    }

    // MARK: - 🟢 Everywhere the pair rule does not fire

    func testAMultiWayBoardKeepsItsOwnPerRowRounding() throws {
        // Three priced contenders is not a duel (#2997 pins the board OUT of the
        // rule), so every legend cell is that row's own number and the fix must
        // not have quietly widened the pair rule to a field.
        let board = try XCTUnwrap(
            presentation(
                boardJSON([
                    (key: "a", name: "A", probability: 0.585, rank: 1),
                    (key: "b", name: "B", probability: 0.415, rank: 2),
                    (key: "c", name: "C", probability: 0.2, rank: 3),
                ])
            ).boards.first)
        let chart = try XCTUnwrap(board.chart)

        XCTAssertEqual(
            chart.series.map {
                formatProbabilityOrDash($0.probability, renderedPercent: $0.renderedPercent)
            },
            ["59%", "42%", "20%"],
            "a three-way field prints three independent numbers, and 0.415 is "
            + "42% when nothing derives it")
        XCTAssertEqual(board.rows.map(\.percentText), ["59%", "42%", "20%"])
    }

    func testASeriesBuiltWithNoBoardMapFallsThroughToItsOwnProbability() {
        // Every other caller of `RaceChart.series` — and any future one — gets
        // the old behaviour by default rather than a nil percent that renders
        // as a dash.
        let rows = [boardRow(key: "a", probability: 0.415)]
        let series = RaceChart.series(from: rows)

        XCTAssertEqual(series.first?.renderedPercent, nil)
        XCTAssertEqual(
            formatProbabilityOrDash(
                series.first?.probability, renderedPercent: series.first?.renderedPercent ?? nil),
            "42%")
    }

    func testAContenderMissingFromTheBoardsMapStillPrintsItsPrice() {
        // A map that does not name this row is not an instruction to print
        // nothing. `boardRenderedPercents` only carries rows it could render.
        let rows = [boardRow(key: "a", probability: 0.415)]
        let series = RaceChart.series(from: rows, renderedPercents: ["someone-else": 99])

        XCTAssertNil(series.first?.renderedPercent)
        XCTAssertEqual(
            formatProbabilityOrDash(
                series.first?.probability, renderedPercent: series.first?.renderedPercent ?? nil),
            "42%")
    }

    // MARK: - The VIEW is the thing on screen

    func testTheLegendItselfPrintsTheCarriedPercentAndNotItsOwnRounding() throws {
        // Every arm above measures the RULE, and the rule can be perfect while
        // the one line that draws the legend still calls the one-argument
        // formatter — which is exactly the state this issue was filed in. A
        // measurement that builds its own label cannot see that; only a scan
        // anchored on the card's own line can.
        let view = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()      // BainLuckTests
            .deletingLastPathComponent()      // Bain Luck (project dir)
            .appendingPathComponent("Bain Luck/Components/RaceChartView.swift")
        let source = try String(contentsOf: view, encoding: .utf8)

        XCTAssertTrue(
            source.contains("renderedPercent: entry.renderedPercent"),
            "RaceChartView's legend must print the percent the board decided")
        XCTAssertFalse(
            source.contains("formatProbabilityOrDash(entry.probability))"),
            "the one-argument call is the #5949 defect: it re-rounds 0.415 to "
            + "42% under a row printing 41%")
    }

    // MARK: - Fixtures

    /// The men's board as production served it this morning: two contenders left,
    /// a complement pair sitting exactly on the half-cent grid.
    private func duel() -> TournamentHubPresentation {
        presentation(
            boardJSON([
                (key: "alexander-zverev", name: "Alexander Zverev",
                 probability: 0.585, rank: 1),
                (key: "ben-shelton", name: "Ben Shelton", probability: 0.415, rank: 2),
            ]))
    }

    private func boardRow(key: String, probability: Double) -> TournamentHubBoardRow {
        let json = """
        {"entity_key": "\(key)", "display_name": "\(key)", "state": "live",
         "probability": \(probability), "rank": 1,
         "trend": [{"date": "2026-09-11", "probability": 0.4},
                   {"date": "2026-09-12", "probability": \(probability)}]}
        """
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try! decoder.decode(TournamentHubBoardRow.self, from: Data(json.utf8))
    }

    private func presentation(_ json: String) -> TournamentHubPresentation {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return TournamentHubPresentation(
            response: try! decoder.decode(TournamentHubResponse.self, from: Data(json.utf8)))
    }

    private func boardJSON(
        _ rows: [(key: String, name: String, probability: Double, rank: Int)]
    ) -> String {
        let boardRows = rows.map { row in
            """
            {"entity_key": "\(row.key)", "display_name": "\(row.name)",
             "state": "live", "rank": \(row.rank), "probability": \(row.probability),
             "trend": [{"date": "2026-09-11", "probability": 0.4},
                       {"date": "2026-09-12", "probability": \(row.probability)}]}
            """
        }.joined(separator: ", ")

        return """
        {"slug": "us-open", "title": "US Open 2026",
         "slate": {"matches": []}, "results": {"matches": []},
         "boards": [{"draw": "mens-singles", "label": "Men's Singles",
                     "price_state": "live", "rows": [\(boardRows)]}],
         "bracket": {}, "event_links": {"by_espn": {}}, "broadcasts": []}
        """
    }
}
