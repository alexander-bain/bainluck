import Foundation
import XCTest
@testable import Bain_Luck

/// #9490: a finished card paints the winner's pre-match number upset-orange
/// only when the winner was priced BELOW the side it beat, on the same reading.
///
/// The card cut at a fixed `< 0.4` on the winner alone. On a board that prices
/// a draw, 39.5% can be the favourite. Specimen: event 15304745, Turkey v Italy
/// (UEFA Nations League, 1–4), `prematch_odds` home 0.325 / away 0.395 from
/// Kalshi, as `/api/events/15304745` served it on 2026-09-28. The web hero
/// printed "Italy WON · Upset · 40% pregame". On the phone the away side of a
/// draw-priced card is withheld, so the defect lands on the mirror: a HOME win
/// at 39.5% v 32.5%.
final class AFavouritesWinIsNotAnUpset9490Tests: XCTestCase {

    private func decoder() -> JSONDecoder {
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        return d
    }

    private func reading(_ json: String) throws -> PrematchReading {
        let served = try decoder().decode(PrematchOdds.self, from: Data(json.utf8))
        return try XCTUnwrap(PrematchReading.resolve(prematch: served, opening: nil))
    }

    // MARK: - Three-way boards

    /// 15304745 as served: Italy (away) won at 39.5% over Turkey's 32.5%.
    func testTheSpecimensFavouriteWinningIsNotAnUpset() throws {
        let r = try reading("""
        {"home_probability": 0.325, "away_probability": 0.395,
         "home_rendered_percent": 33, "away_rendered_percent": 40, "source": "kalshi"}
        """)
        XCTAssertFalse(r.awayIsComplement, "both sides were served")
        XCTAssertFalse(r.winnerWasUnderdog(homeWon: false, awayWon: true, pricesADraw: true),
                       "39.5% beat 32.5%: the favourite won")
    }

    /// The phone-visible shape: the same prices with the favourite at home.
    /// The old `< 0.4` cut painted this orange.
    func testAHomeFavouriteUnderFortyPercentWinningIsNotAnUpset() throws {
        let r = try reading("""
        {"home_probability": 0.395, "away_probability": 0.325, "source": "kalshi"}
        """)
        XCTAssertFalse(r.winnerWasUnderdog(homeWon: true, awayWon: false, pricesADraw: true))
    }

    /// A real three-way upset: the 33.5% away side beat the 42.5% home side.
    func testARealThreeWayUpsetStillReads() throws {
        let r = try reading("""
        {"home_probability": 0.425, "away_probability": 0.335, "source": "kalshi"}
        """)
        XCTAssertTrue(r.winnerWasUnderdog(homeWon: false, awayWon: true, pricesADraw: true))
        XCTAssertFalse(r.winnerWasUnderdog(homeWon: true, awayWon: false, pricesADraw: true),
                       "the favourite winning the same board is not one")
    }

    /// A draw-priced board whose away number is only `1 − home` carries the
    /// draw inside it; comparing against it would call a 35% home win an upset
    /// over a "65%" that no side was ever priced at.
    func testAComplementCannotAnswerOnADrawPricedBoard() throws {
        let r = try reading("""
        {"home_probability": 0.35, "source": "kalshi"}
        """)
        XCTAssertTrue(r.awayIsComplement)
        XCTAssertFalse(r.winnerWasUnderdog(homeWon: true, awayWon: false, pricesADraw: true))
    }

    func testADrawNamesNoUnderdog() throws {
        let r = try reading("""
        {"home_probability": 0.425, "away_probability": 0.335, "source": "kalshi"}
        """)
        XCTAssertFalse(r.winnerWasUnderdog(homeWon: false, awayWon: false, pricesADraw: true))
    }

    // MARK: - Two-way control: unchanged

    func testTwoWayUnderdogWinsStillRead() throws {
        let r = try reading("""
        {"home_probability": 0.62, "away_probability": 0.38, "source": "kalshi"}
        """)
        XCTAssertTrue(r.winnerWasUnderdog(homeWon: false, awayWon: true, pricesADraw: false))
        XCTAssertFalse(r.winnerWasUnderdog(homeWon: true, awayWon: false, pricesADraw: false))
    }

    /// On a two-way board the complement IS the away price, so it still answers.
    func testTwoWayComplementStillAnswers() throws {
        let r = try reading("""
        {"home_probability": 0.35, "source": "polymarket"}
        """)
        XCTAssertTrue(r.winnerWasUnderdog(homeWon: true, awayWon: false, pricesADraw: false))
    }

    func testTheOpeningFallbackKnowsItsComplement() throws {
        let opening = try decoder().decode(OpeningOdds.self, from: Data("""
        {"home_probability": 0.3252, "away_probability": 0.3936, "favorite": "away"}
        """.utf8))
        let r = try XCTUnwrap(PrematchReading.resolve(prematch: nil, opening: opening))
        XCTAssertFalse(r.awayIsComplement)
        XCTAssertFalse(r.winnerWasUnderdog(homeWon: false, awayWon: true, pricesADraw: true))
    }

    // MARK: - The card is wired to it

    /// Comments stripped, whitespace removed, so prose beside the line cannot
    /// satisfy the scan.
    private func cardCode() throws -> String {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("Bain Luck/Components/EventCardView.swift")
        return try String(contentsOf: url, encoding: .utf8)
            .split(separator: "\n", omittingEmptySubsequences: false)
            .map { line -> String in
                guard let slashes = line.range(of: "//") else { return String(line) }
                return String(line[line.startIndex..<slashes.lowerBound])
            }
            .joined(separator: "\n")
            .filter { !$0.isWhitespace }
    }

    func testTheFinishedRowAsksTheReadingNotAFixedCut() throws {
        let code = try cardCode()
        let start = try XCTUnwrap(code.range(of: "privatefuncpreGameOddsLabel(forside:TeamSide)"),
                                  "the scan is not reading EventCardView.swift")
        let body = String(code[start.upperBound...].prefix(1200))
        XCTAssertTrue(body.contains(
            "letisUpset=won&&(reading?.winnerWasUnderdog(homeWon:homeWon,awayWon:awayWon,pricesADraw:awayIsWithheld)??false)"))
        XCTAssertFalse(body.contains("prob<0.4"), "the fixed cut is back")
        XCTAssertFalse(body.contains("wasUnderdog"), "a second winner-alone cut is back")
    }
}
