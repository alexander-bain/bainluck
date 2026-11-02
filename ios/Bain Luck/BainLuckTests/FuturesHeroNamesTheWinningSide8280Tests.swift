import XCTest
@testable import Bain_Luck

/// #8280 on the market page — a settled game board's hero names the side that
/// won, not the first graded totals line. #11616 R1(c), lane1b's N6:
/// 0e5d583a/0d239c9d led with the first supported winner in served order, so
/// production `/futures/114108` (*Kings vs. Blue Jackets*, Polymarket,
/// `mutually_exclusive: false`) heroed **"O/U 5.5 Won"** while web heroes Kings
/// (`frontend/__tests__/lib/gameBoardHeroNamesTheWinningSide8280.test.ts`).
///
/// The rows below are the specimen's ids, names and served order. Web's fixture
/// carries `is_winner` only; here each graded leg also carries the terminal
/// price and tier-3 source the native row rule needs to call it Won/Lost, so the
/// test exercises the preference and not the #698 fallback.
final class FuturesHeroNamesTheWinningSide8280Tests: XCTestCase {

    private func row(_ id: Int, _ name: String, price: Double? = nil, won: Bool? = nil,
                     source: String? = nil, settlement: String? = nil) -> [String: Any] {
        var value: [String: Any] = ["id": id, "name": name,
            "probability": price.map { $0 as Any } ?? NSNull(),
            "is_winner": won.map { $0 as Any } ?? NSNull(),
            "resolution_source": source.map { $0 as Any } ?? NSNull()]
        if let settlement { value["settlement_display"] = ["verdict": settlement, "basis": "fixture"] }
        return value
    }

    private func market(_ outcomes: [[String: Any]], status: String = "resolved",
                        source: String = "polymarket") throws -> FuturesMarketDetail {
        let value: [String: Any] = ["id": 114108, "name": "Kings vs. Blue Jackets", "status": status,
            "source": source, "mutually_exclusive": false, "outcomes": outcomes]
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(FuturesMarketDetail.self, from: JSONSerialization.data(withJSONObject: value))
    }

    /// `/futures/114108` in served order; `contract` attaches the served verdicts.
    private func specimen(contract: Bool) -> [[String: Any]] {
        let won = { (id: Int, name: String) in
            self.row(id, name, price: 1.0, won: true, source: "clob_authoritative", settlement: contract ? "won" : nil)
        }
        let lost = { (id: Int, name: String) in
            self.row(id, name, price: 0.0, won: false, source: "clob_authoritative", settlement: contract ? "lost" : nil)
        }
        return [won(1632397, "O/U 5.5"), won(1632396, "O/U 6.5"), won(1632399, "Kings"),
                lost(1632398, "Spread -1.5"), lost(1632400, "Spread -1.5")]
    }

    // MARK: - The specimen

    func testTheKingsSpecimenHeroesKingsNotTheFirstTotalsLine() throws {
        for contract in [false, true] {
            let m = try market(specimen(contract: contract))
            let hero = try XCTUnwrap(futuresDetailHeroOutcome(m), "contract \(contract)")
            XCTAssertEqual(hero.id, 1632399, "0d239c9d heroed O/U 5.5 (contract \(contract))")
            XCTAssertEqual(futuresDetailHeroValue(m, hero: hero), .verdict(.won))
            XCTAssertEqual(futuresDetailShareMessage(m), "Kings: Won — Kings vs. Blue Jackets on Bain Luck")
            // The saved card reads the same choice.
            let card = FeedFuturesData(savedPinDetail: m)
            XCTAssertEqual(card.winner, "Kings")
            XCTAssertEqual(card.topOutcomes?.first?.id, 1632399)
        }
    }

    // MARK: - What the preference must not move (web's own controls)

    /// Every supported winner is a line: the first is still featured, no withholding.
    func testABoardWhoseWinnersAreAllLinesFeaturesTheFirst() throws {
        let m = try market([
            row(1, "Burnley FC vs. Brentford FC: O/U 1.5", price: 1, won: true, source: "clob_authoritative"),
            row(2, "Burnley FC vs. Brentford FC: Both Teams to Score", price: 1, won: true, source: "clob_authoritative"),
            row(3, "Burnley FC vs. Brentford FC: O/U 2.5", price: 1, won: true, source: "clob_authoritative"),
        ])
        XCTAssertEqual(futuresDetailHeroOutcome(m)?.id, 1)
    }

    /// It re-orders supported winners only: an UNGRADED side never outranks a
    /// graded line, and a LOST side is never featured.
    func testAnUngradedOrLosingSideIsNeverPromotedOverASupportedLine() throws {
        let m = try market([
            row(1, "O/U 5.5", price: 0.9995, won: true, source: "game_score"),
            row(2, "Kings", price: 0.0005, won: false, source: "game_score"),
            row(3, "Blue Jackets", price: 0.5),
        ], source: "kalshi")
        XCTAssertEqual(futuresDetailHeroOutcome(m)?.id, 1)
    }

    /// A raw `is_winner` on a side with no supported source is not a winner, so
    /// it cannot take the hero from a supported line.
    func testAnUnsupportedWinnerFlagOnASideDoesNotOutrankASupportedLine() throws {
        let m = try market([
            row(1, "O/U 5.5", price: 0.99, won: true, source: "game_score"),
            row(2, "Kings", price: 0.99, won: true, source: nil),
        ], source: "kalshi")
        XCTAssertEqual(futuresDetailHeroOutcome(m)?.id, 1)
    }

    /// A threshold ladder keeps its loosest graded rung (#6032): no rung is a line.
    func testAThresholdLadderKeepsItsFirstGradedRung() throws {
        let m = try market([
            row(1, "77° or above", won: true, source: "api_settlement"),
            row(2, "78° or above", won: true, source: "api_settlement"),
            row(3, "82° or above", won: true, source: "api_settlement"),
        ], source: "kalshi")
        XCTAssertEqual(futuresDetailHeroOutcome(m)?.id, 1)
    }

    /// The preference is a SETTLED-board rule (web: "a live board is untouched").
    /// An open board with several supported winners keeps served order.
    func testAnOpenBoardKeepsServedOrderAmongItsSupportedWinners() throws {
        let m = try market([
            row(1, "O/U 5.5", won: true, source: "api_settlement"),
            row(2, "Kings", won: true, source: "api_settlement"),
        ], status: "open", source: "kalshi")
        XCTAssertEqual(futuresDetailHeroOutcome(m)?.id, 1)
    }

    // MARK: - The patterns are web's

    private static var repoRoot: URL {
        URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()   // BainLuckTests
            .deletingLastPathComponent()   // Bain Luck (project dir)
            .deletingLastPathComponent()   // ios
            .deletingLastPathComponent()   // repo root
    }

    /// The regex literals inside web's `isLineOrPropLeg`, read from the web
    /// source, must be the Swift twin's patterns in the same order with the same
    /// case flag. If either side adds, drops or edits a shape, this fails.
    func testTheLineOrPropPatternsAreWebsVerbatim() throws {
        let web = try String(contentsOf: Self.repoRoot.appendingPathComponent("frontend/lib/futuresDetailDisplay.ts"),
                             encoding: .utf8)
        let start = try XCTUnwrap(web.range(of: "export function isLineOrPropLeg("))
        let end = try XCTUnwrap(web.range(of: "\n}\n", range: start.upperBound..<web.endIndex))
        let body = String(web[start.upperBound..<end.lowerBound])
        let literal = try NSRegularExpression(pattern: #"/((?:\\/|[^/\n])+)/([a-z]*)\.test\(n\)"#)
        let webPatterns: [(String, Bool)] = literal.matches(in: body, range: NSRange(body.startIndex..., in: body)).map {
            let source = String(body[Range($0.range(at: 1), in: body)!]).replacingOccurrences(of: #"\/"#, with: "/")
            let flags = String(body[Range($0.range(at: 2), in: body)!])
            return (source, flags.contains("i"))
        }
        XCTAssertEqual(webPatterns.count, 7, "web's isLineOrPropLeg shape count moved")
        XCTAssertEqual(webPatterns.map { $0.0 }, FuturesLineOrPropLeg8280.patterns.map { $0.0 })
        XCTAssertEqual(webPatterns.map { $0.1 }, FuturesLineOrPropLeg8280.patterns.map { $0.1 })
    }

    /// Web's own production shape lists (its #8280 test file) classify the same
    /// way through the Swift twin.
    func testWebsProductionShapesClassifyTheSame() throws {
        let tests = try String(contentsOf: Self.repoRoot
            .appendingPathComponent("frontend/__tests__/lib/gameBoardHeroNamesTheWinningSide8280.test.ts"), encoding: .utf8)
        func names(before marker: String) throws -> [String] {
            let close = try XCTUnwrap(tests.range(of: "])(\"%s \(marker)\""), marker)
            let open = try XCTUnwrap(tests.range(of: "it.each([", options: .backwards,
                                                 range: tests.startIndex..<close.lowerBound), marker)
            let list = String(tests[open.upperBound..<close.lowerBound])
            let quoted = try NSRegularExpression(pattern: #""([^"]*)""#)
            return quoted.matches(in: list, range: NSRange(list.startIndex..., in: list)).map {
                String(list[Range($0.range(at: 1), in: list)!])
            }
        }
        let lines = try names(before: "is a line or prop")
        let sides = try names(before: "names a side")
        XCTAssertGreaterThanOrEqual(lines.count, 10)
        XCTAssertGreaterThanOrEqual(sides.count, 5)
        for name in lines { XCTAssertTrue(FuturesLineOrPropLeg8280.matches(name), name) }
        for name in sides { XCTAssertFalse(FuturesLineOrPropLeg8280.matches(name), name) }
        XCTAssertFalse(FuturesLineOrPropLeg8280.matches(nil))
        XCTAssertFalse(FuturesLineOrPropLeg8280.matches("   "))
    }
}
