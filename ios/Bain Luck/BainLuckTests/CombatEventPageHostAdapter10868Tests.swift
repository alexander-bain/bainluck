import XCTest
@testable import Bain_Luck

/// #10868 — the combat event screen's host glue (`CombatEventPageHost10868`):
/// its pure `build` from the values the page already holds, on the REAL
/// retained bodies — the UFC 332 and boxing details
/// (`CombatBoutPageAdapter10868Tests`, byte for byte), the UFC 332 history and
/// `/game-markets` (`CombatHistoryAdapter10868Tests`,
/// `CombatOriginalsAdapter10868Tests`, reduced verbatim subsets). Source paths,
/// sha256 and what each subset kept are written in those files.
///
/// PREPARED, NOT RUN: written under a source-only hold (no build, no XCTest).
///
/// CONSTRUCTED here: the reader's calendar and `now`; the interrupted delivery
/// flag; a story `Membership` (no production owner supplies one — the proposed
/// mount passes none); the held reading state.
@MainActor
final class CombatEventPageHostAdapter10868Tests: XCTestCase {
    private typealias Host = CombatEventPageHost10868
    private typealias Fixtures = CombatBoutPageAdapter10868Tests
    private typealias Details = OriginalMarketDetails9483

    private func build(_ event: EventDetail, history: EventHistoryResponse?, markets: GameMarketsResponse?,
                       interrupted: Bool = false, membership: CombatStoryAdapter10868.Membership? = nil,
                       reading: Host.Reading = Host.Reading()) -> Host.Built {
        Host.build(event: event, history: history, markets: markets,
                   probabilityObservedAt: event.heroProbabilityObservedAt?.asDate, deliveryInterrupted: interrupted,
                   now: Fixtures.readAt.asDate!, membership: membership, reading: reading,
                   calendar: Fixtures.pacific, locale: Fixtures.locale)
    }

    /// CONSTRUCTED owner proof, naming served question keys.
    private let membership = CombatStoryAdapter10868.Membership(
        methods: [.init(id: "ko", label: "KO / TKO", questionKey: "m:63786874")],
        knockout: [.init(id: "kopylov", label: "Roman Kopylov", questionKey: "m:63900810")])

    // MARK: - The retained bout

    func testTheRetainedBoutComposesFromItsThreeBodiesWithNoStoryStream() throws {
        let event = try Fixtures.detail(Fixtures.mmaDetail)
        let history = try CombatHistoryAdapter10868Tests.response()
        let built = build(event, history: history, markets: try CombatOriginalsAdapter10868Tests.markets())
        XCTAssertEqual(built.input.phase, .during)
        XCTAssertEqual(built.input.history, CombatHistoryAdapter10868.history(
            history, event: event, phase: .during,
            host: CombatHistoryAdapter10868.Host(now: Fixtures.readAt.asDate!, calendar: Fixtures.pacific,
                                                 locale: Fixtures.locale)))
        XCTAssertEqual(built.input.history.series[0].runs.count, 1)
        XCTAssertEqual(built.originals.catalogue?.originals.count, 31)
        XCTAssertEqual(built.input.copy.allPropsLabel, "All 31 original props")
        XCTAssertNil(built.input.stream, "no production membership, no stories")
        XCTAssertNil(built.input.methods)
        XCTAssertNil(built.input.rounds)
        XCTAssertNil(built.input.knockout)
        XCTAssertNil(built.input.duration)
        XCTAssertNil(built.input.notice)
    }

    func testWithoutAHistoryResponseOnlyTheChartSlotIsUnavailable() throws {
        let event = try Fixtures.detail(Fixtures.mmaDetail)
        let markets = try CombatOriginalsAdapter10868Tests.markets()
        let withHistory = build(event, history: try CombatHistoryAdapter10868Tests.response(), markets: markets)
        let without = build(event, history: nil, markets: markets)
        XCTAssertEqual(without.input.history.plotAbsence?.title, "History unavailable")
        XCTAssertNil(without.input.history.expand)
        XCTAssertEqual(without.input.headline, withHistory.input.headline)
        XCTAssertEqual(without.input.about, withHistory.input.about)
        XCTAssertEqual(without.originals.catalogue, withHistory.originals.catalogue)
    }

    func testTheRetainedBoxingBoutUsesTheSameScreenWithNothingInAllProps() throws {
        let event = try Fixtures.detail(Fixtures.boxingDetail)
        let markets = try CombatOriginalsAdapter10868Tests.markets(Fixtures.boxingMarkets)
        let built = build(event, history: nil, markets: markets)
        XCTAssertTrue(Host.applies(event))
        XCTAssertEqual(built.input.phase, .during)
        XCTAssertEqual(built.input.headline.displayed.map(\.name), ["Ryusei Matsumoto", "Russell Acosta"])
        XCTAssertNil(built.originals.catalogue)
        XCTAssertNil(built.input.copy.allPropsLabel)
        XCTAssertEqual(built.originals.emptyWords, "No retained originals for this fight")
        XCTAssertEqual(built.input.history.plotAbsence?.title, "History unavailable", "no boxing history body is retained")
    }

    // MARK: - Stories (constructed membership)

    func testAProvedMembershipOffersItsStoriesAndTheHeldStoryIsShown() throws {
        let event = try Fixtures.detail(Fixtures.mmaDetail)
        let markets = try CombatOriginalsAdapter10868Tests.markets()
        let built = build(event, history: nil, markets: markets, membership: membership,
                          reading: Host.Reading(story: .knockout))
        let stream = try XCTUnwrap(built.input.stream)
        XCTAssertEqual(stream.cards.map(\.id), ["methods", "knockout"])
        XCTAssertEqual(stream.primary?.id, "knockout")
        XCTAssertEqual(stream.scope, "combat:15318681:during")
        XCTAssertEqual(built.input.stories.map(\.card), [.methods, .knockout])
        XCTAssertNotNil(built.input.methods)
        XCTAssertNotNil(built.input.knockout)
        XCTAssertNil(built.input.rounds)
        XCTAssertNil(built.input.duration)
    }

    // MARK: - Details from a card

    func testACardsDetailsOpenOnlyTheExactCatalogueOriginal() throws {
        let event = try Fixtures.detail(Fixtures.mmaDetail)
        let built = build(event, history: nil, markets: try CombatOriginalsAdapter10868Tests.markets(),
                          membership: membership)
        let side = try XCTUnwrap(built.input.methods?.methods.first?.originals.first)
        XCTAssertEqual(side.id, "240262496")
        XCTAssertEqual(side.marketID, "63786874")
        XCTAssertEqual(Host.detailsSelection(marketID: side.marketID, originalID: side.id, in: built.originals),
                       Details.Selection(scope: "combat:15318681:during:originals",
                                         identity: Details.Identity(source: "polymarket", market: "63786874",
                                                                    side: "240262496")))
        XCTAssertNil(Host.detailsSelection(marketID: "63786874", originalID: "240654996", in: built.originals),
                     "another market's side is never opened in its place")

        let boxing = build(try Fixtures.detail(Fixtures.boxingDetail), history: nil, markets: nil)
        XCTAssertNil(Host.detailsSelection(marketID: side.marketID, originalID: side.id, in: boxing.originals))
    }

    // MARK: - Purity

    func testBuildIsPureSoEveryChangedValueReachesTheNextPass() throws {
        let event = try Fixtures.detail(Fixtures.mmaDetail)
        let markets = try CombatOriginalsAdapter10868Tests.markets()
        let history = try CombatHistoryAdapter10868Tests.response()
        XCTAssertEqual(build(event, history: history, markets: markets).input,
                       build(event, history: history, markets: markets).input)
        let interrupted = build(event, history: history, markets: markets, interrupted: true)
        XCTAssertEqual(interrupted.input.notice, "Update interrupted · showing the last recorded chances")
        XCTAssertFalse(Host.applies(try Fixtures.edited(Fixtures.mmaDetail, ["sport": "icehockey_nhl"])))
    }
}
