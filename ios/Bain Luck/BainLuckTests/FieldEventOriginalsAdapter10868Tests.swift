import SwiftUI
import XCTest
@testable import Bain_Luck

/// #10868 — part four (`FieldEventOriginalsAdapter10868`): "All props" and each
/// original's Details, on the retained REAL chess and resolved series bodies
/// (`FieldEventAdapterFixtures10868`), read through the existing Details model
/// (`OriginalMarketDetails9483.content`) so what is asserted is what Details
/// prints. PREPARED / NOT RUN.
@MainActor
final class FieldEventOriginalsAdapter10868Tests: XCTestCase {
    private typealias O = FieldEventOriginalsAdapter10868
    private typealias A = FieldEventPageAdapter10868
    private typealias D = OriginalMarketDetails9483
    private typealias F = FieldEventAdapterFixtures10868

    private func content(_ originals: FieldEventPageOriginals10868, _ market: FuturesMarketDetail,
                         _ id: Int) throws -> D.Content {
        let identity = D.Identity(source: "kalshi", market: String(market.id), side: String(id))
        let selection = D.Selection(scope: try XCTUnwrap(originals.catalogue?.scope), identity: identity)
        return try XCTUnwrap(D.content(catalogue: originals.catalogue, selection: selection))
    }

    func testEveryChessOutcomeIsOneOriginalInServedOrder() throws {
        let market = try F.market(F.chessBefore)
        let originals = O.originals(field: market, host: F.host(F.chessCapture), tint: A.tint(0))
        let catalogue = try XCTUnwrap(originals.catalogue)
        XCTAssertEqual(catalogue.scope, "field:62383719:before:originals")
        XCTAssertEqual(catalogue.originals.map(\.outcome), market.outcomes.map(\.name))
        XCTAssertEqual(Set(catalogue.originals.map(\.identity)).count, 12)
        XCTAssertEqual(originals.context, "12 original outcomes")
        XCTAssertEqual(originals.heading, "All props")
        XCTAssertEqual(originals.emptyWords, "No original outcomes for this field")
        // A market handed in twice is one set of originals.
        let twice = O.originals(field: market, markets: [market], host: F.host(F.chessCapture), tint: A.tint(0))
        XCTAssertEqual(twice.catalogue?.originals.count, 12)
    }

    func testEachRowPrintsItsOwnReadingOrItsOwnWords() throws {
        let market = try F.market(F.chessBefore)
        let host = F.host(F.chessCapture)
        let originals = O.originals(field: market, host: host, tint: A.tint(0))
        // Recent: one recorded chance with its own clock and venue.
        let alice = try content(originals, market, F.aliceLee)
        XCTAssertEqual(alice.readings.map(\.label), ["Recorded chance"])
        XCTAssertEqual(alice.readings.map(\.text), ["86%"])
        XCTAssertEqual(alice.readings.first?.provenance,
                       "\(A.clockWords("2026-10-15T08:01:07.824368+00:00".asDate!, host: host)) · Kalshi")
        XCTAssertNil(alice.result)
        // Stale: no current chance; the value is kept, dated, as history only.
        let tatev = try content(originals, market, F.tatevAbrahamyan)
        XCTAssertEqual(tatev.readings.map(\.text), [AllMarketsCatalogView9483.noRecentPrice])
        let clock = A.clockWords("2026-10-14T21:45:42.318171+00:00".asDate!, host: host)
        XCTAssertTrue(tatev.about.contains(D.Row(label: D.historicalLabel, value: "2%, recorded \(clock) · Kalshi")))
        // Served null: the catalogue's own words, never 0%.
        let anna = try content(originals, market, F.annaSargsyan)
        XCTAssertEqual(anna.readings.map(\.text), [AllMarketsCatalogView9483.unavailablePrice])
        XCTAssertTrue(anna.about.contains(D.Row(label: "Market ID", value: "62383719")))
        XCTAssertTrue(anna.about.contains(D.Row(label: "Outcome ID", value: "235705522")))
        XCTAssertTrue(anna.about.contains(D.Row(label: "Source", value: "Kalshi")))
        XCTAssertEqual(anna.rules, .unavailable("Rules unavailable"))
    }

    func testASettledRowIsItsOwnResultNeverAChance() throws {
        let market = try F.market(F.seriesFinal)
        let originals = O.originals(field: market, host: F.host(F.seriesCapture), tint: A.tint(0))
        XCTAssertEqual(originals.catalogue?.scope, "field:62898789:final:originals")
        let won = try content(originals, market, F.cwsTwoNil)
        XCTAssertEqual(won.readings.map(\.label), ["Pre-event chance"])
        XCTAssertEqual(won.readings.map(\.text), ["Pre-event chance unavailable"])
        XCTAssertEqual(won.result, D.ShownResult(words: "Won", provenance: "Settled by Kalshi"))
        XCTAssertFalse(won.about.contains { $0.label == D.historicalLabel }, "a settled 100% is never kept as a chance")
        let lost = try content(originals, market, F.houTwoNil)
        XCTAssertEqual(lost.result, D.ShownResult(words: "Lost", provenance: "Settled by Kalshi"))
    }

    func testAFieldCardRefOpensExactlyItsOwnOriginal() throws {
        let market = try F.market(F.rugbyBefore)
        let host = F.host(F.rugbyCapture)
        let originals = O.originals(field: market, host: host, tint: A.tint(0))
        let card = try XCTUnwrap(FieldEventStoriesAdapter10868.field(market, host: host))
        let france = try XCTUnwrap(card.displayed.first { $0.label == "France" }).ref
        let selection = try XCTUnwrap(O.selection(for: france, in: originals))
        XCTAssertEqual(selection.scope, originals.catalogue?.scope)
        XCTAssertEqual(D.original(in: originals.catalogue, selection: selection)?.outcome, "France")
        // CONSTRUCTED refs: another market's, or an outcome the board does not serve, open nothing.
        let foreign = FieldChooserOriginalRef10868(scope: france.scope, source: "kalshi", marketID: "62383719",
                                                   outcomeID: france.outcomeID)
        XCTAssertNil(O.selection(for: foreign, in: originals))
        let unknown = FieldChooserOriginalRef10868(scope: france.scope, source: "kalshi", marketID: "60473053",
                                                   outcomeID: "999")
        XCTAssertNil(O.selection(for: unknown, in: originals))
    }
}
