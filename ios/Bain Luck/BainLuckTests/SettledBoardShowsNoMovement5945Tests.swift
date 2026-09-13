import SwiftUI
import XCTest
@testable import Bain_Luck

/// A FINISHED DRAW PRINTED A PRICE MOVEMENT — `+93` IN GREEN, BESIDE `Won`.
///
/// Measured on production 2026-09-13, `/api/tournaments/us-open`, the women's
/// board sixteen hours after Rybakina won it: all 44 rows `probability: null`
/// (settled), and all 44 still carrying `trend` (19 points) and `trend_delta`.
/// `boardSection` fed that delta straight to `movementPoints`, so the phone drew
///
///     Settled · Elena Rybakina won the title.
///     1  Elena Rybakina      +93   Won
///     2  Aryna Sabalenka     -21   Out
///
/// The column beside the chip has ALREADY withdrawn the percent, and #5917's own
/// reason for withdrawing it is that "a probability to win a title nobody can
/// still win is not a number". The delta is a statement about exactly that
/// withdrawn number — so the board refused to print the value and then printed
/// its change. Green `+93` next to `Won` reads as a race still moving.
///
/// **The web twin has guarded this since #5934** —
/// `{!settled && row.trend_delta !== null && …}` in `TournamentBoard.tsx`, where
/// `settled` is `row.probability === null`. Native had no such test, and
/// `RaceChart.deltaWindowNote`'s docstring names the web as one contract whose
/// divergence IS the bug. This file closes the divergence with the same word.
///
/// WHY #5917's SUITE DID NOT CATCH IT — the trap worth keeping. Its `boardJSON`
/// builder emits settled rows with no `trend_delta` key at all, so
/// `movementPoints(nil)` returned nil and every assertion passed on a fixture
/// cleaner than the payload. Its
/// `testADecidedBoardWithNoHistoryDrawsNoChartFrame` even records the belief in
/// prose — "settled rows arrive with no price and no trend" — which production
/// contradicts: they arrive with no price and NINETEEN trend points. The chart
/// is nil because `RaceChart.series` filters on `probability`, not because the
/// history is absent. So every fixture here carries the history, and the
/// settled-ness is the payload's `probability: null`, exactly as served.
@MainActor
final class SettledBoardShowsNoMovement5945Tests: XCTestCase {

    // MARK: - 🔴 The settled board

    func testTheChampionsRowPrintsNoMovementChip() throws {
        let board = try XCTUnwrap(decided().boards.first)
        let champion = try XCTUnwrap(board.rows.first)

        XCTAssertEqual(champion.name, "Elena Rybakina")
        XCTAssertEqual(champion.percentText, "Won")
        XCTAssertNil(
            champion.deltaPoints,
            "+93 beside `Won` says the title race is still moving. The row has "
            + "already withdrawn the percent this delta measures the change in")
    }

    func testNoRowOfASettledBoardPrintsMovement() throws {
        let board = try XCTUnwrap(decided().boards.first)
        // Non-vacuity: the deltas ARE in the payload and ARE big enough to
        // print. A guard that passed because the fixture was empty would be
        // exactly the #5917 failure repeated.
        XCTAssertEqual(board.rows.count, 3)
        for row in board.rows {
            XCTAssertNil(
                row.deltaPoints,
                "\(row.name) printed a movement chip on a decided draw")
        }
    }

    func testTheSuppressionIsTheSettledTestAndNotASizeAccident() throws {
        // Rybakina's real delta is +0.926125 → 92.6 points, far over the 1-point
        // floor `movementPoints` applies. If the fix were ever re-implemented as
        // a threshold this fails, which is the point.
        let row = try XCTUnwrap(
            decided().boards.first?.rows.first)
        XCTAssertNil(row.deltaPoints)

        // The same delta on a row that is still live DOES print: the rule is
        // settled-ness, nothing else.
        let live = try XCTUnwrap(
            presentation(
                boardJSON(
                    decided: nil,
                    rows: [(key: "elena-rybakina", name: "Elena Rybakina",
                            state: "live", rank: 1, delta: 0.926125)],
                    probabilities: ["elena-rybakina": 0.99])
            ).boards.first?.rows.first)
        XCTAssertEqual(try XCTUnwrap(live.deltaPoints), 92.6125, accuracy: 0.001)
    }

    // MARK: - 🟢 The live board keeps its movement

    func testALiveBoardStillPrintsItsChips() throws {
        let board = try XCTUnwrap(liveBoard().boards.first)

        XCTAssertNil(board.settledNote)
        XCTAssertEqual(board.rows.map(\.name), ["Alexander Zverev", "Ben Shelton"])
        XCTAssertEqual(
            try XCTUnwrap(board.rows[0].deltaPoints), 37.97, accuracy: 0.01,
            "the men's final was live when this was measured and its movement is "
            + "the story — this fix must not reach it")
        XCTAssertEqual(
            try XCTUnwrap(board.rows[1].deltaPoints), 33.25, accuracy: 0.01)
    }

    // MARK: - The window note is relocated, not deleted (notice 34)

    func testTheDeltaWindowNoteIsStillComputedForGuardsAndProbes() throws {
        // Notice 34 took `Movement since 26 Aug.` out of the PAGE BODY, matching
        // the web's #4278 move to `data-delta-window`. The sentence itself is
        // unchanged and still on the model: relocating a method note and
        // deleting it are different changes, and #3033's finding stands.
        let board = try XCTUnwrap(liveBoard().boards.first)
        XCTAssertEqual(board.deltaWindowNote, "Movement since 11 Sep.")
    }

    // MARK: - Rendered evidence

    func testTheSettledBoardRasterises() throws {
        let surface = TournamentHubSurface(presentation: decided())
            .padding(16)
            .frame(width: 390)
        let renderer = rendererForMeasurement(surface)
        renderer.scale = 2
        let image = try XCTUnwrap(renderer.uiImage, "settled board produced no raster")
        let png = try XCTUnwrap(image.pngData(), "settled board produced no PNG")
        let url = FileManager.default.temporaryDirectory
            .appendingPathComponent("settled-board-5945.png")
        try? png.write(to: url)
        print("Settled board render artifact: \(url.path) (\(png.count) bytes)")
        XCTAssertGreaterThan(png.count, 0)
    }

    // MARK: - Fixtures

    /// The women's board as production served it on 2026-09-13: settled rows
    /// that still carry their whole history and their delta.
    private func decided() -> TournamentHubPresentation {
        presentation(
            boardJSON(
                decided: "elena-rybakina",
                rows: [
                    (key: "elena-rybakina", name: "Elena Rybakina",
                     state: "won", rank: 1, delta: 0.926125),
                    (key: "aryna-sabalenka", name: "Aryna Sabalenka",
                     state: "eliminated", rank: 2, delta: -0.20875),
                    (key: "anastasia-potapova", name: "Anastasia Potapova",
                     state: "eliminated", rank: 3, delta: -0.0025),
                ]))
    }

    /// The men's board the same day: two live contenders, priced, both moving.
    private func liveBoard() -> TournamentHubPresentation {
        presentation(
            boardJSON(
                label: "Men's Singles",
                draw: "mens-singles",
                decided: nil,
                rows: [
                    (key: "alexander-zverev", name: "Alexander Zverev",
                     state: "live", rank: 1, delta: 0.379669),
                    (key: "ben-shelton", name: "Ben Shelton",
                     state: "live", rank: 2, delta: 0.332476),
                ],
                probabilities: ["alexander-zverev": 0.76, "ben-shelton": 0.24]))
    }

    private func presentation(_ json: String) -> TournamentHubPresentation {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        // Force-try: the literal is in this file, so a broken one is a test bug
        // and must fail loudly rather than decode into an empty board.
        let response = try! decoder.decode(
            TournamentHubResponse.self, from: Data(json.utf8))
        return TournamentHubPresentation(response: response)
    }

    /// Unlike #5917's builder, every row here carries `trend` AND `trend_delta`,
    /// because that is what the server sends on a settled row (#5945).
    private func boardJSON(
        label: String = "Women's Singles",
        draw: String = "womens-singles",
        decided: String?,
        rows: [(key: String, name: String, state: String, rank: Int, delta: Double)],
        probabilities: [String: Double] = [:]
    ) -> String {
        let boardRows = rows.map { row in
            let probability = probabilities[row.key].map { "\($0)" } ?? "null"
            return """
            {"entity_key": "\(row.key)", "display_name": "\(row.name)",
             "state": "\(row.state)", "rank": \(row.rank),
             "probability": \(probability), "trend_delta": \(row.delta),
             "trend": [{"date": "2026-09-11", "probability": 0.4},
                       {"date": "2026-09-12", "probability": 0.5}]}
            """
        }.joined(separator: ", ")

        let decidedBlock = decided.map {
            """
            , "decided": {"winner_entity_key": "\($0)"}
            """
        } ?? ""

        return """
        {"slug": "us-open", "title": "US Open 2026",
         "slate": {"matches": []}, "results": {"matches": []},
         "boards": [{"draw": "\(draw)", "label": "\(label)",
                     "price_state": "dark", "rows": [\(boardRows)]\(decidedBlock)}],
         "bracket": {}, "event_links": {"by_espn": {}}, "broadcasts": []}
        """
    }
}
