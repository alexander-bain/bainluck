import SwiftUI
import XCTest
@testable import Bain_Luck

/// #10868 — the racing adapter, part three ("All props": the original catalogue
/// and its Details), on the REAL retained Singapore Grand Prix driver-winner and
/// podium bodies, before and after the race (`RacingAdapterFixtures10868`).
///
/// CONSTRUCTED here, and only here: the reader's calendar and `now`, the tint,
/// the held selection, which market bodies the host holds, and — named in the one
/// test that does it — one served `probability` changed.
@MainActor
final class RacingOriginalsAdapter10868Tests: XCTestCase {
    private typealias A = RacingOriginalsAdapter10868
    private typealias Page = RacingFieldPageAdapter10868
    private typealias Details = OriginalMarketDetails9483
    private typealias F = RacingAdapterFixtures10868

    private func original(_ page: RacingEventPageOriginals10868, market: String, side: Int) throws -> Details.Original {
        let identity = Details.Identity(source: "polymarket", market: market, side: String(side))
        return try XCTUnwrap(page.catalogue?.originals.first { $0.identity == identity }, "\(identity)")
    }

    // MARK: Membership, order, identity

    func testBeforeEveryHeldOutcomeIsOneOriginalInServedOrderUnderItsServedIds() throws {
        let page = A.originals(race: try F.market(F.winnerBefore), markets: [try F.market(F.podiumBefore)],
                               host: F.host(F.beforeCapture), tint: .red)
        let catalogue = try XCTUnwrap(page.catalogue)
        XCTAssertEqual(catalogue.scope, "racing:63989371:before:originals")
        XCTAssertEqual(catalogue.originals.map(\.identity.market),
                       ["63989371", "63989371", "63989371", "63989371", "63989361", "63989361", "63989361"])
        XCTAssertEqual(catalogue.originals.map(\.identity.side),
                       ["241675151", "241675153", "241675154", "241675152", "242933922", "243467981", "243467982"])
        XCTAssertEqual(Set(catalogue.originals.map(\.identity.source)), ["polymarket"])
        XCTAssertEqual(catalogue.originals.first?.title, "Singapore Grand Prix: Driver Winner")
        XCTAssertEqual(catalogue.originals.last?.title, "Singapore Grand Prix: Driver Podium Finish")
        XCTAssertEqual(catalogue.originals.last?.outcome, "Lewis Hamilton")
        XCTAssertEqual(page.heading, "All props")
        XCTAssertEqual(page.context, "7 original outcomes")
        XCTAssertNil(page.controls)
    }

    func testAMarketHandedInTwiceIsOneSetOfOriginals() throws {
        let winner = try F.market(F.winnerFinal)
        let podium = try F.market(F.podiumFinal)
        let page = A.originals(race: winner, markets: [podium, winner, podium], host: F.host(F.finalCapture), tint: .red)
        let identities = try XCTUnwrap(page.catalogue).originals.map(\.identity)
        XCTAssertEqual(identities.count, 10)
        XCTAssertEqual(Set(identities).count, 10)
    }

    // MARK: Before — a recorded chance with its own clock, or history

    func testARecentPriceIsTheRecordedChanceWithItsOwnClockAndVenue() throws {
        let host = F.host(F.beforeCapture)
        let page = A.originals(race: try F.market(F.winnerBefore), markets: [try F.market(F.podiumBefore)],
                               host: host, tint: .red)
        let verstappen = try original(page, market: "63989371", side: F.verstappen)
        XCTAssertEqual(verstappen.mode, .pregame)
        XCTAssertEqual(verstappen.beforeLabel, "Recorded chance")
        XCTAssertEqual(verstappen.pregame, .value("62%", placement: 0.6162,
                                                  provenance: "\(Page.clockWords(F.beforeStamp.asDate!, host: host)) · Polymarket"))
        XCTAssertNil(verstappen.about.historicalQuote)
        // A podium contract keeps its own price and its own clock.
        let podium = try original(page, market: "63989361", side: 243467981)
        let stamp = "2026-10-11T04:49:59.592455+00:00"
        XCTAssertEqual(podium.pregame, .value("63%", placement: 0.63,
                                              provenance: "\(Page.clockWords(stamp.asDate!, host: host)) · Polymarket"))
        let content = try XCTUnwrap(Details.content(catalogue: page.catalogue,
                                                    selection: Details.Selection(scope: page.catalogue!.scope,
                                                                                 identity: verstappen.identity)))
        XCTAssertEqual(content.readings.map(\.label), ["Recorded chance"])
        XCTAssertEqual(content.readings.map(\.text), ["62%"])
    }

    func testAStalePriceStaysVisibleButOnlyAsAHistoricalQuote() throws {
        // CONSTRUCTED reader clock: past the futures bound for every kept price.
        let host = F.host("2026-10-11T10:30:00Z")
        let page = A.originals(race: try F.market(F.winnerBefore), host: host, tint: .red)
        let verstappen = try original(page, market: "63989371", side: F.verstappen)
        XCTAssertEqual(verstappen.mode, .pregame)
        XCTAssertEqual(verstappen.pregame, .missing(AllMarketsCatalogView9483.noRecentPrice))
        XCTAssertEqual(verstappen.about.historicalQuote, Details.HistoricalQuote(
            text: "62%", recorded: "\(Page.clockWords(F.beforeStamp.asDate!, host: host)) · Polymarket"))
        XCTAssertEqual(page.catalogue?.originals.count, 4)
    }

    // MARK: Final — each contract's own grade

    func testAtTheFinalEachContractCarriesItsOwnGradeNeverAPrice() throws {
        let page = A.originals(race: try F.market(F.winnerFinal), markets: [try F.market(F.podiumFinal)],
                               host: F.host(F.finalCapture), tint: .red)
        XCTAssertEqual(page.catalogue?.scope, "racing:63989371:final:originals")
        // Antonelli's two contracts settle independently: win Lost, podium Won.
        let grades: [(String, Int, String)] = [
            ("63989371", F.antonelli, "Lost"), ("63989361", 242025505, "Won"),
            ("63989371", F.verstappen, "Won"), ("63989361", 242933922, "Won"),
            ("63989371", F.leclerc, "Lost"), ("63989361", 243467981, "Won"),
            ("63989371", F.hamilton, "Lost"), ("63989361", 243467982, "Lost"),
        ]
        for (market, side, words) in grades {
            let found = try original(page, market: market, side: side)
            XCTAssertEqual(found.mode, .result, "\(market):\(side)")
            XCTAssertEqual(found.grade, Details.Grade(words: words, provenance: "Settled by Polymarket"), "\(market):\(side)")
            XCTAssertEqual(found.pregame, .missing("Pre-race chance unavailable"), "\(market):\(side)")
            XCTAssertEqual(found.beforeLabel, "Pre-race chance")
            // The served 1.0 / 0.0 is never kept as a price.
            XCTAssertNil(found.about.historicalQuote, "\(market):\(side)")
        }
        let antonelli = try original(page, market: "63989361", side: 242025505)
        let content = try XCTUnwrap(Details.content(catalogue: page.catalogue,
                                                    selection: Details.Selection(scope: page.catalogue!.scope,
                                                                                 identity: antonelli.identity)))
        XCTAssertEqual(content.result, Details.ShownResult(words: "Won", provenance: "Settled by Polymarket"))
        XCTAssertEqual(content.readings.map(\.isValue), [false])
    }

    func testASettledRowWithAnUnknownResultKeepsOnlyAnInsidePriceAsHistory() throws {
        // CONSTRUCTED: Verstappen's settled 1.0 served as 0.97 (`is_winner` still
        // true), which `SettledResultDisplay698` reads as an unknown result.
        let variant = F.replacing(F.winnerFinal, #""probability":1.0,"american_odds":null,"rank":1,"#,
                                  with: #""probability":0.97,"american_odds":null,"rank":1,"#)
        let host = F.host(F.finalCapture)
        let page = A.originals(race: try F.market(variant), host: host, tint: .red)
        let verstappen = try original(page, market: "63989371", side: F.verstappen)
        XCTAssertEqual(verstappen.mode, .result)
        XCTAssertEqual(verstappen.grade?.words, "Result unknown")
        let stamp = "2026-10-11T17:44:12.917499+00:00"
        XCTAssertEqual(verstappen.about.historicalQuote, Details.HistoricalQuote(
            text: "97%", recorded: "\(Page.clockWords(stamp.asDate!, host: host)) · Polymarket"))
        // Its neighbours keep their own served grades.
        XCTAssertEqual(try original(page, market: "63989371", side: F.hamilton).grade?.words, "Lost")
    }

    // MARK: Selection and About

    func testTheHeldSelectionPassesThroughAndResolvesOnlyByExactScopeAndIdentity() throws {
        let identity = Details.Identity(source: "polymarket", market: "63989361", side: "242025505")
        let selection = Details.Selection(scope: "racing:63989371:final:originals", identity: identity)
        let page = A.originals(race: try F.market(F.winnerFinal), markets: [try F.market(F.podiumFinal)],
                               host: F.host(F.finalCapture), tint: .red, selection: selection)
        XCTAssertEqual(page.selection, selection)
        XCTAssertEqual(Details.original(in: page.catalogue, selection: selection)?.outcome, "Kimi Antonelli")
        // A selection held from the before catalogue does not resolve here.
        let stale = Details.Selection(scope: "racing:63989371:before:originals", identity: identity)
        XCTAssertNil(Details.original(in: page.catalogue, selection: stale))
    }

    func testEveryOriginalNamesItsVenueItsIdsAndThatRulesAreUnavailable() throws {
        let page = A.originals(race: try F.market(F.winnerBefore), host: F.host(F.beforeCapture), tint: .red)
        let verstappen = try original(page, market: "63989371", side: F.verstappen)
        XCTAssertEqual(verstappen.about.source, "Polymarket")
        XCTAssertEqual(verstappen.about.rules, .unavailable("Rules unavailable"))
        XCTAssertEqual(verstappen.about.provenance, [Details.Row(label: "Market ID", value: "63989371"),
                                                     Details.Row(label: "Outcome ID", value: "241675151")])
        XCTAssertEqual(page.emptyWords, "No original outcomes for this race")
    }
}
