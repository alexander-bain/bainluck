import XCTest
@testable import Bain_Luck

/// #11616 — the My Stuff card for a saved market (`FeedFuturesData(savedPinDetail:)`)
/// reads the SAME `/api/futures/{id}` body its market page reads, so it must make
/// the page's choices: which row leads, which row is a result, and which whole
/// percent each row prints.
///
/// Before this, the adapter crowned with `SettledResultDisplay698.heroWearsWinnerBadge`,
/// whose untargeted branch is raw `is_winner == true`; an open Kalshi row at 0.55
/// with `is_winner = true` and no resolution source was named the WINNER, and
/// `FeedLifecycle.futuresIsSettled` then read an open question as settled. The
/// page prints that row as 55%. The card also printed `formatProbability` of each
/// selected row on its own, never the page's full-field integer.
///
/// Model-level guards only: no mounted SwiftUI render or device run here.
@MainActor
final class SavedMarketCardReadsItsMarketPage11616Tests: XCTestCase {
    private func row(_ id: Int, _ name: String, price: Double? = nil, won: Bool? = nil,
                     source: String? = nil, settlement: String? = nil, percent: Int? = nil) -> [String: Any] {
        var value: [String: Any] = ["id": id, "name": name,
            "probability": price.map { $0 as Any } ?? NSNull(),
            "is_winner": won.map { $0 as Any } ?? NSNull(),
            "resolution_source": source.map { $0 as Any } ?? NSNull()]
        if let settlement { value["settlement_display"] = ["verdict": settlement, "basis": "fixture"] }
        if let percent { value["rendered_percent"] = percent }
        return value
    }

    private func market(_ outcomes: [[String: Any]], status: String = "open", source: String = "kalshi",
                        exclusive: Bool? = nil) throws -> FuturesMarketDetail {
        var value: [String: Any] = ["id": 11616, "name": "Saved field", "status": status,
                                    "source": source, "outcomes": outcomes]
        if let exclusive { value["mutually_exclusive"] = exclusive }
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(FuturesMarketDetail.self, from: JSONSerialization.data(withJSONObject: value))
    }

    private func pageValue(_ outcome: FuturesOutcome, _ m: FuturesMarketDetail) -> FuturesDetailRowValue {
        FuturesDetailRowValue.of(outcome, marketStatus: m.status, marketSource: m.source)
    }

    // MARK: - Result selection

    /// The coordinator's counterexample: open, kalshi, 0.55, `is_winner = true`,
    /// no resolution source, no settlement display.
    func testAnUnsupportedOpenWinnerFlagIsNotCrownedAndTheCardStaysOpen() throws {
        let m = try market([row(1, "Contender", price: 0.55, won: true), row(2, "Field", price: 0.3)])
        XCTAssertEqual(pageValue(m.outcomes[0], m), .price(0.55), "the page prints a price")
        let card = FeedFuturesData(savedPinDetail: m)
        XCTAssertNil(card.winner)
        XCTAssertNil(card.winnerOpeningProbability)
        XCTAssertFalse(FeedLifecycle.futuresIsSettled(card, now: Date(timeIntervalSince1970: 0)))
        XCTAssertEqual(card.topOutcomes?.first?.id, 1)
        XCTAssertEqual(card.topOutcomes?.first?.detailValue, .price(0.55))
    }

    /// Control: the same row with the venue's own settlement IS the page's
    /// answer on an open board, so the card names it.
    func testAGenuineAuthoritativeOpenWinnerIsNamedAsThePageHeroesIt() throws {
        let m = try market([row(1, "Contender", won: true, source: "api_settlement"), row(2, "Field", price: 0.3)])
        XCTAssertEqual(futuresDetailHeroOutcome(m)?.id, 1)
        let card = FeedFuturesData(savedPinDetail: m)
        XCTAssertEqual(card.winner, "Contender")
        XCTAssertTrue(FeedLifecycle.futuresIsSettled(card, now: Date(timeIntervalSince1970: 0)))
        XCTAssertEqual(card.topOutcomes?.first?.detailValue, .verdict(.won))
        XCTAssertNil(card.topOutcomes?.first?.barProbability, "a result draws no bar")
    }

    /// N1 on the card: an open independent board leads with its live rung, and a
    /// graded rung is a result on its row, not the card's winner.
    func testAnOpenIndependentBoardLeadsWithTheLiveRungAndNamesNoWinner() throws {
        let m = try market([row(2, "Above 4.00%", price: 0.95, won: true, source: "api_settlement"),
                            row(1, "Above 4.25%", price: 0.97), row(3, "Above 4.50%", price: 0.2)],
                           exclusive: false)
        let card = FeedFuturesData(savedPinDetail: m)
        XCTAssertEqual(card.topOutcomes?.first?.id, futuresDetailHeroOutcome(m)?.id)
        XCTAssertEqual(card.topOutcomes?.map(\.id), [1, 2, 3])
        XCTAssertNil(card.winner)
        XCTAssertEqual(card.topOutcomes?[1].detailValue, .verdict(.won))
    }

    /// N2 on the card: a resolved field of losers names nobody.
    func testAResolvedFieldOfLosersNamesNoWinner() throws {
        let m = try market([row(1, "Rider A", price: 0.0, won: false, source: "api_settlement"),
                            row(2, "Rider B", price: 0.0, won: false, source: "api_settlement")], status: "resolved")
        let card = FeedFuturesData(savedPinDetail: m)
        XCTAssertNil(card.winner)
        XCTAssertEqual(card.topOutcomes?.compactMap(\.detailValue), [.verdict(.lost), .verdict(.lost)])
    }

    /// #698 on the card: a settled row whose result is unknown reads "Result
    /// unknown" (never a price or a crown); withheld/null prints nothing.
    func testUnknownAndWithheldRowsCarryThePagesDecision() throws {
        let settled = try market([row(1, "Yes", price: 0.5, won: true, source: "clob_authoritative", settlement: "unknown"),
                                  row(2, "No", price: 0.5, won: false, source: "clob_authoritative", settlement: "unknown")],
                                 status: "resolved", source: "polymarket")
        let card = FeedFuturesData(savedPinDetail: settled)
        XCTAssertNil(card.winner)
        XCTAssertEqual(card.topOutcomes?.compactMap(\.detailValue),
                       [.resultUnknown(lastRecorded: 0.5), .resultUnknown(lastRecorded: 0.5)])
        XCTAssertTrue(card.topOutcomes?.allSatisfy { $0.barProbability == nil } == true)

        let open = try market([row(1, "Priced", price: 0.4), row(2, "Withheld")])
        let withheld = try XCTUnwrap(FeedFuturesData(savedPinDetail: open).topOutcomes?.first { $0.id == 2 })
        XCTAssertEqual(withheld.detailValue, FuturesDetailRowValue.none)
        XCTAssertNil(withheld.detailRenderedPercent)
        XCTAssertNil(withheld.barProbability)
    }

    // MARK: - Integers

    /// The card prints the page's full-field integer for every selected row,
    /// served or locally decided, never a re-rounding of the top three.
    func testSelectedRowsCarryThePagesFullFieldIntegers() throws {
        let served = try market([row(1, "A", price: 0.405, percent: 40), row(2, "B", price: 0.295, percent: 30),
                                 row(3, "C", price: 0.2, percent: 20), row(4, "D", price: 0.1, percent: 10)],
                                exclusive: true)
        let legacy = try market([row(1, "Not Dallas", price: 0.595), row(2, "Dallas", price: 0.405)], exclusive: true)
        for m in [served, legacy] {
            let page = futuresDetailRenderedPercents(m.outcomes)
            let shown = try XCTUnwrap(FeedFuturesData(savedPinDetail: m).topOutcomes)
            XCTAssertEqual(shown.count, min(3, m.outcomes.count))
            for o in shown {
                XCTAssertEqual(o.detailRenderedPercent, page[o.id], "row \(o.id)")
                let p = try XCTUnwrap(o.probability)
                XCTAssertEqual(futuresProbabilityLabel(p, renderedPercent: o.detailRenderedPercent),
                               futuresProbabilityLabel(p, renderedPercent: page[o.id]))
            }
        }
        // The served integer survives even where single-value rounding differs.
        let first = try XCTUnwrap(FeedFuturesData(savedPinDetail: served).topOutcomes?.first)
        XCTAssertEqual(first.detailRenderedPercent, 40)
        XCTAssertEqual(futuresProbabilityLabel(0.405, renderedPercent: first.detailRenderedPercent), "40%")
        // The complement pair sums to 100 on the card as on the page.
        let pair = try XCTUnwrap(FeedFuturesData(savedPinDetail: legacy).topOutcomes)
        XCTAssertEqual(pair.compactMap(\.detailRenderedPercent).reduce(0, +), 100)
    }

    /// A real zero is a price the page prints as 0%, not "<1%" and not a result.
    func testARealZeroStaysAZeroPrice() throws {
        let m = try market([row(1, "Leader", price: 0.9), row(2, "Zero", price: 0.0)], exclusive: true)
        let zero = try XCTUnwrap(FeedFuturesData(savedPinDetail: m).topOutcomes?.first { $0.id == 2 })
        XCTAssertEqual(zero.detailValue, .price(0.0))
        XCTAssertEqual(futuresProbabilityLabel(0.0, renderedPercent: zero.detailRenderedPercent), "0%")
        XCTAssertEqual(zero.barProbability, 0.0)
    }

    // MARK: - Feed cards are untouched

    /// The two new fields are adapter-only: a decoded feed outcome (even one the
    /// server stamped with `rendered_percent`) carries neither, so every feed
    /// card keeps its existing label and bar.
    func testADecodedFeedOutcomeCarriesNoPageDecision() throws {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let o = try decoder.decode(FeedFuturesOutcome.self, from: Data(#"""
        {"id": 7, "name": "Feed row", "probability": 0.405, "rank": 1, "movement": 0.01, "rendered_percent": 40}
        """#.utf8))
        XCTAssertNil(o.detailValue)
        XCTAssertNil(o.detailRenderedPercent)
        XCTAssertEqual(o.barProbability, 0.405)
        XCTAssertEqual(o.movement, 0.01)
    }
}
