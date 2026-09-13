import XCTest
@testable import Bain_Luck

/// #5990 — A DECIDED DRAW LOST THE PICTURE OF THE RACE THAT DECIDED IT.
///
/// Photographed on production on finals day, 20:46Z
/// (`artifacts-native-020/womens-settled-820.png`): the women's card reads
/// "Settled · Elena Rybakina won the title." over `Won` / `Out` rows and
/// "Top 6 of 44 in the final standings" — and the fortnight that produced that
/// champion is drawn nowhere on the phone. The web twin draws it on the same
/// payload; that is #5934, and Alex's standing ruling in as many words:
/// *settled means settled — charts show the completed journey.*
///
/// THE CAUSE WAS A COMMENT THAT HAD STOPPED BEING TRUE. `RaceChart.series`
/// filtered `probability != nil` and called itself "`chartSeries` on the web",
/// but the web moved off that test to DRAWABILITY in #5934. The old rule was
/// right about the LINE and wrong about the HISTORY: every row of a finished
/// draw arrives `probability: null`, so the series emptied and
/// `TournamentHubPresentation`'s no-history guard nil'd the whole card.
///
/// THIS IS THE SHIPPED PAYLOAD, NOT A HYPOTHETICAL — and that is exactly what
/// #5917's own suite could not see, because its fixture builder emits settled
/// rows with no `trend` key at all. #5945 keeps `trend`/`trend_hourly` on
/// settled rows: measured at 20:44Z, every settled women's row carried 19 daily
/// points (Rybakina `probability: null`, `trend_delta: +0.926125`). So every
/// settled row in this file carries history, which is the whole difference
/// between a fixture that reproduces the defect and one that cannot.
///
/// 🔵 THE PRICE IS NOT RESURRECTED. The line may end at 99; the label says
/// `Won`. Reading the last chart point into the legend cell would put back the
/// "RYBAKINA 99%" that #5917 removed from the board two inches below it, and
/// the guards below spend as much effort on that as on the missing frame.
final class ASettledDrawKeepsItsChart5990Tests: XCTestCase {

    // MARK: - 🔴 The defect

    func testADecidedDrawStillDrawsTheRaceThatDecidedIt() throws {
        let board = try XCTUnwrap(decidedWithHistory().boards.first)
        let chart = try XCTUnwrap(
            board.chart,
            "the title-race card vanished from a finished draw — the completed "
            + "journey is the one thing a settled board still has to show")

        XCTAssertEqual(
            chart.series.map(\.entityKey),
            ["elena-rybakina", "aryna-sabalenka", "anastasia-potapova"],
            "board order IS the finish once nothing is priced: champion first, "
            + "exactly the three lines the chart drew the minute before")
        XCTAssertNil(
            chart.emptyNote,
            "\"No contender on this board has a price to chart\" is a sentence "
            + "about a market, printed over a question that is over")
    }

    /// A frame is not a picture. The suite would pass with three empty series.
    func testTheDrawnLinesAreTheRealHistoryAndNotAnEmptyFrame() throws {
        let chart = try XCTUnwrap(try XCTUnwrap(decidedWithHistory().boards.first).chart)

        for entry in chart.series {
            XCTAssertEqual(
                entry.points.map(\.date), ["2026-09-11", "2026-09-12", "2026-09-13"],
                "\(entry.entityKey) drew no points, so its line is a legend "
                + "entry with nothing under it")
        }
        XCTAssertTrue(
            RaceChart.isDrawable(chart.series, range: chart.initialRange, starts: chart.starts),
            "the range the chart OPENS on has to have two readings to join, or "
            + "the reader meets a blank plot and a chip they have to guess at")
    }

    // MARK: - 🔴 The legend says the result, never the last reading

    func testASettledContendersLegendCellIsItsResult() {
        XCTAssertEqual(RaceChart.legendValue(settled("won", last: 0.99)), "Won")
        XCTAssertEqual(RaceChart.legendValue(settled("eliminated", last: 0.87)), "Out")
    }

    func testTheLegendNeverReachesIntoThePointsForANumber() {
        let champion = settled("won", last: 0.99)
        let value = RaceChart.legendValue(champion)

        XCTAssertFalse(
            value.contains("99"),
            "the line ends at 99 and the label printed it — \"RYBAKINA 99%\" "
            + "sixteen hours after she won is the exact sentence #5917 removed")
        XCTAssertFalse(
            value.contains("%"),
            "a percentage in this cell is a claim about now, on a question that "
            + "is over")
    }

    /// One word source. A legend and the rows two inches below it cannot label
    /// the same player differently (notice 35, one card family).
    func testTheLegendAndTheBoardRowPrintTheSameWordForTheSamePlayer() throws {
        let board = try XCTUnwrap(decidedWithHistory().boards.first)
        let chart = try XCTUnwrap(board.chart)

        for entry in chart.series {
            let row = try XCTUnwrap(board.rows.first { $0.name == entry.displayName })
            XCTAssertEqual(
                RaceChart.legendValue(entry), row.percentText,
                "\(entry.displayName) is \"\(RaceChart.legendValue(entry))\" in "
                + "the legend and \"\(row.percentText)\" in the list")
        }
    }

    func testTheTwoWordsAreTheWebsTwoWords() {
        XCTAssertEqual(RaceChart.legendStateLabel("won"), "Won")
        XCTAssertEqual(RaceChart.legendStateLabel("eliminated"), "Out")
    }

    /// A state we do not recognise gets no invented word — the caller falls
    /// through to the number, which is the honest answer for "we do not know".
    func testAnUnrecognisedStateInventsNoWord() {
        XCTAssertNil(RaceChart.legendStateLabel("withdrew"))
        XCTAssertEqual(
            RaceChart.legendValue(
                RaceChartSeries(
                    entityKey: "x", displayName: "X", colorIndex: 0,
                    probability: nil, state: "withdrew",
                    points: [RaceChartPoint(date: "2026-09-12", probability: 0.4)])),
            absentProbabilityMarker)
    }

    // MARK: - 🟢 What the fix must not break

    /// The rule that keeps this from being a regression dressed as a fix.
    /// Mid-tournament a board carries both, and a player who is OUT must never
    /// open the chart ahead of one still in the draw on board rank alone.
    func testAPricedContenderNeverLosesAChartSlotToAnEliminatedOne() throws {
        let built = RaceChart.series(from: try rows("""
        [{"entity_key":"out-1","display_name":"Out One","state":"eliminated","probability":null,
          "trend":[{"date":"2026-09-11","probability":0.30},{"date":"2026-09-12","probability":0.05}]},
         {"entity_key":"out-2","display_name":"Out Two","state":"eliminated","probability":null,
          "trend":[{"date":"2026-09-11","probability":0.20},{"date":"2026-09-12","probability":0.04}]},
         {"entity_key":"live-1","display_name":"Live One","state":"live","probability":0.55,
          "trend":[{"date":"2026-09-11","probability":0.40},{"date":"2026-09-12","probability":0.55}]},
         {"entity_key":"live-2","display_name":"Live Two","state":"live","probability":0.30,
          "trend":[{"date":"2026-09-11","probability":0.25},{"date":"2026-09-12","probability":0.30}]},
         {"entity_key":"live-3","display_name":"Live Three","state":"live","probability":0.10,
          "trend":[{"date":"2026-09-11","probability":0.12},{"date":"2026-09-12","probability":0.10}]},
         {"entity_key":"live-4","display_name":"Live Four","state":"live","probability":0.05}]
        """))

        XCTAssertEqual(built.map(\.entityKey), ["live-1", "live-2", "live-3"])
        XCTAssertEqual(built.map(\.colorIndex), [0, 1, 2])
    }

    /// The guard the presentation still needs: a decided board with nothing to
    /// draw gets no frame, rather than an empty one captioned with a sentence
    /// about prices nobody is waiting for (the web's #5934, arm 5).
    func testADecidedBoardWithNoHistoryStillDrawsNoFrame() throws {
        XCTAssertTrue(RaceChart.series(from: try rows("""
        [{"entity_key":"a","display_name":"A","state":"won","probability":null},
         {"entity_key":"b","display_name":"B","state":"eliminated","probability":null}]
        """)).isEmpty)

        XCTAssertNil(
            try XCTUnwrap(decidedWithoutHistory().boards.first).chart,
            "no price and no history is the one case the old rule got right")
    }

    /// #5949, unchanged: the legend prints the integer the BOARD decided, never
    /// this file's own rounding of the same fraction.
    func testALivePricedContendersLegendStillPrintsTheBoardsInteger() {
        let live = RaceChartSeries(
            entityKey: "alexander-zverev", displayName: "Alexander Zverev",
            colorIndex: 0, probability: 0.585, renderedPercent: 58, state: "live",
            points: [RaceChartPoint(date: "2026-09-12", probability: 0.5)])

        XCTAssertEqual(RaceChart.legendValue(live), "58%")
    }

    func testALiveBoardDrawsExactlyWhatItDrewBefore() throws {
        let board = try XCTUnwrap(
            presentation(
                boardJSON(
                    label: "Men's Singles", draw: "mens-singles", decided: nil,
                    rows: [
                        (key: "alexander-zverev", name: "Alexander Zverev", state: "live", rank: 1),
                        (key: "ben-shelton", name: "Ben Shelton", state: "live", rank: 2),
                    ],
                    probabilities: ["alexander-zverev": 0.585, "ben-shelton": 0.415],
                    history: true)).boards.first)
        let chart = try XCTUnwrap(board.chart)

        XCTAssertEqual(chart.series.map(\.entityKey), ["alexander-zverev", "ben-shelton"])
        XCTAssertEqual(chart.series.map { RaceChart.legendValue($0) }, ["59%", "41%"])
        XCTAssertNil(board.settledNote)
    }

    /// An unpriced row with no history is still skipped — the rule that widened
    /// is DRAWABILITY, and a row with neither is drawable by nobody's reading.
    func testAnUnpricedRowWithNoHistoryIsStillSkipped() throws {
        XCTAssertEqual(
            RaceChart.series(from: try rows("""
            [{"entity_key":"a","display_name":"A","probability":null},
             {"entity_key":"b","display_name":"B","probability":0.3},
             {"entity_key":"c","display_name":"C","probability":0.2},
             {"entity_key":"d","display_name":"D","probability":0.1}]
            """)).map(\.entityKey),
            ["b", "c", "d"])
    }

    // MARK: - ⚫️ Non-vacuity
    //
    // Both arms exist because the fixture is the whole experiment here: #5917's
    // suite HAD a decided board and still could not see this, purely because
    // its settled rows carried no `trend` key. A fixture that does not carry
    // history tests the old rule and reports green.

    func testTheFixtureIsTheDefectsOwnShapeAndNotTheEasyOne() throws {
        let board = try XCTUnwrap(decidedHubRows().first)
        XCTAssertNil(board.probability, "a fixture with a price cannot reach the new branch")
        XCTAssertFalse(
            (board.trend ?? []).isEmpty,
            "settled-with-history is the shape production sends (#5945) and the "
            + "only one that reproduces #5990")
    }

    func testTheRuleThisReplacedWouldHaveDrawnNothingAtAll() throws {
        let priceOnly = try decidedHubRows().filter { $0.probability != nil }
        XCTAssertTrue(
            priceOnly.isEmpty,
            "the pre-#5990 filter was `probability != nil`; if it can still "
            + "select a row from this fixture then the test above passes "
            + "without the fix and proves nothing")
    }

    // MARK: - Fixtures

    /// The women's board as production served it on finals day: the champion
    /// `won`, the field `eliminated`, every probability null — and every row
    /// still carrying the daily trend #5945 keeps on settled rows.
    private func decidedWithHistory() -> TournamentHubPresentation {
        presentation(boardJSON(decided: "elena-rybakina", rows: settledRows, history: true))
    }

    private func decidedWithoutHistory() -> TournamentHubPresentation {
        presentation(boardJSON(decided: "elena-rybakina", rows: settledRows))
    }

    private func decidedHubRows() throws -> [TournamentHubBoardRow] {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let response = try decoder.decode(
            TournamentHubResponse.self,
            from: Data(boardJSON(decided: "elena-rybakina", rows: settledRows, history: true).utf8))
        return try XCTUnwrap(response.boards.first).rows
    }

    private let settledRows: [(key: String, name: String, state: String, rank: Int)] = [
        (key: "elena-rybakina", name: "Elena Rybakina", state: "won", rank: 1),
        (key: "aryna-sabalenka", name: "Aryna Sabalenka", state: "eliminated", rank: 2),
        (key: "anastasia-potapova", name: "Anastasia Potapova", state: "eliminated", rank: 3),
    ]

    /// A settled series whose line ends high — the shape that tempts a legend
    /// into printing a number.
    private func settled(_ state: String, last: Double) -> RaceChartSeries {
        RaceChartSeries(
            entityKey: "elena-rybakina", displayName: "Elena Rybakina",
            colorIndex: 0, probability: nil, state: state,
            points: [
                RaceChartPoint(date: "2026-09-11", probability: 0.42),
                RaceChartPoint(date: "2026-09-12", probability: last),
            ])
    }

    private func rows(_ json: String) throws -> [TournamentHubBoardRow] {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode([TournamentHubBoardRow].self, from: Data(json.utf8))
    }

    private func presentation(_ json: String) -> TournamentHubPresentation {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        // Force-try: the literal is in this file, so a broken one is a test bug
        // and must fail loudly rather than decode into an empty board.
        let response = try! decoder.decode(TournamentHubResponse.self, from: Data(json.utf8))
        return TournamentHubPresentation(response: response)
    }

    private func boardJSON(
        label: String = "Women's Singles",
        draw: String = "womens-singles",
        decided: String?,
        rows: [(key: String, name: String, state: String, rank: Int)],
        probabilities: [String: Double] = [:],
        history: Bool = false
    ) -> String {
        let boardRows = rows.map { row in
            let probability = probabilities[row.key].map { "\($0)" } ?? "null"
            let trend = history
                ? """
                , "trend": [{"date": "2026-09-11", "probability": 0.28},
                            {"date": "2026-09-12", "probability": 0.51},
                            {"date": "2026-09-13", "probability": 0.93}]
                """
                : ""
            return """
            {"entity_key": "\(row.key)", "display_name": "\(row.name)",
             "state": "\(row.state)", "rank": \(row.rank),
             "probability": \(probability)\(trend)}
            """
        }.joined(separator: ", ")

        let decidedBlock = decided.map { ", \"decided\": {\"winner_entity_key\": \"\($0)\"}" } ?? ""

        return """
        {"slug": "us-open", "title": "US Open 2026",
         "slate": {"matches": []}, "results": {"matches": []},
         "boards": [{"draw": "\(draw)", "label": "\(label)",
                     "price_state": "dark", "rows": [\(boardRows)]\(decidedBlock)}],
         "bracket": {}, "event_links": {"by_espn": {}}, "broadcasts": []}
        """
    }
}
