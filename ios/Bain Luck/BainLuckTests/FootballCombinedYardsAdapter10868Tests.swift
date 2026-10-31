import XCTest
@testable import Bain_Luck

/// #10868 — combined rushing + receiving yards: the combined contract's own
/// milestone card beside the additive split leaf.
///
/// PREPARED, NOT RUN: written under a source-only hold (no build, no XCTest).
///
/// No retained NFL body serves a combined rushing + receiving market
/// (`FootballRetained10868`'s three `/game-markets` bodies hold none), so on
/// every real body this family draws nothing — that is the first test. The
/// card's shape is then proved on a CONSTRUCTED variant: Jalen Hurts's real
/// passing-yards rows (live and final bodies) with ONLY their `market_name`
/// replaced by "Philadelphia vs Jacksonville: Rushing + Receiving Yards". Every
/// mark, quote, clock, grade and the served actual (220) are the real rows'.
/// No component (rushing vs receiving) split is served anywhere, so the split
/// always says so.
@MainActor
final class FootballCombinedYardsAdapter10868Tests: XCTestCase {
    private typealias F = FootballRetained10868
    private typealias C = FootballCombinedYardsAdapter10868

    private static let combinedMarket = "Philadelphia vs Jacksonville: Rushing + Receiving Yards"

    /// CONSTRUCTED: Hurts's passing-yards rows renamed to the combined market.
    private func renamed(_ json: String) throws -> String {
        try F.editedProps(json, marketName: "Philadelphia vs Jacksonville: Passing Yards", subject: "Jalen Hurts",
                          setting: ["market_name": Self.combinedMarket])
    }

    func testNoServedCombinedMarketDrawsNoCombinedStory() throws {
        for (detail, markets, now) in [(F.pregameDetail, F.pregameMarkets, F.pregameNow),
                                       (F.liveDetail, F.liveMarkets, F.liveNow),
                                       (F.finalDetail, F.finalMarkets, F.finalNow)] {
            let event = try F.detail(detail)
            XCTAssertTrue(C.stories(event, markets: try F.markets(markets), deck: [], now: now).isEmpty)
        }
    }

    func testLiveTheCombinedCardKeepsItsPregameMarksAndClaimsNoActualSoFar() throws {
        let event = try F.detail(F.liveDetail)
        let markets = try F.markets(try renamed(F.liveMarkets))
        let stories = C.stories(event, markets: markets, deck: [], now: F.liveNow)

        XCTAssertEqual(stories.map(\.card.id), ["Jalen Hurts|" + Self.combinedMarket])
        let story = try XCTUnwrap(stories.first)
        XCTAssertEqual(story.card.basis, .pregameMark)
        XCTAssertEqual(story.card.rungs.map(\.chance), [0.725, 0.585, 0.425, 0.285, 0.185, 0.11])
        XCTAssertEqual(story.split.subject, "Jalen Hurts")
        XCTAssertEqual(story.split.totalName, "Combined")
        XCTAssertEqual(story.split.phase, .during)
        XCTAssertEqual(story.split.actual, .absent(C.Words.soFarUnavailable))
        XCTAssertNil(story.split.detailsID)
        XCTAssertEqual(story.split.axis.unit, "yards")
        XCTAssertTrue(story.split.axis.ticks.isEmpty)
        XCTAssertLessThanOrEqual(story.split.axis.lower, 150)
        XCTAssertGreaterThanOrEqual(story.split.axis.upper, 275)
    }

    func testACardTheDeckAlreadyDealsIsNeverDealtTwice() throws {
        let event = try F.detail(F.liveDetail)
        let markets = try F.markets(try renamed(F.liveMarkets))
        let deck = FootballDeckAdapter10868.deck(event, history: nil, markets: markets,
                                                 host: F.deckHost(F.liveNow, arrivedAt: nil))
        // Production's deck reads every player ladder, the combined one too.
        XCTAssertTrue(FootballDeckAdapter10868.milestoneCards(deck).contains {
            $0.id == "Jalen Hurts|" + Self.combinedMarket
        })
        XCTAssertTrue(C.stories(event, markets: markets, deck: deck, now: F.liveNow).isEmpty)
    }

    func testFinalTheTotalIsTheServedActualAndTheSplitSaysItIsUnavailable() throws {
        let event = try F.detail(F.finalDetail)
        let markets = try F.markets(try renamed(F.finalMarkets))
        let story = try XCTUnwrap(C.stories(event, markets: markets, deck: [], now: F.finalNow).first)

        XCTAssertEqual(story.card.actual, 220)
        XCTAssertEqual(story.split.phase, .final)
        XCTAssertEqual(story.split.actual, .final(AdditiveStatSplitReading10868(
            total: .value(AdditiveStatSplitFigure10868(text: "220", unit: "yards",
                                                        provenance: "Graded after the final")),
            split: .unavailable("Ground and air split unavailable"))))
        // The served actual sits inside the axis.
        XCTAssertLessThan(story.split.axis.lower, 220)
        XCTAssertGreaterThan(story.split.axis.upper, 220)
    }

    func testAFinalWithNoServedActualSaysSoAndInventsNone() throws {
        let event = try F.detail(F.finalDetail)
        // CONSTRUCTED on top of the rename: the served `actual` removed from those rows.
        let markets = try F.markets(try F.editedProps(
            try renamed(F.finalMarkets), marketName: Self.combinedMarket, subject: "Jalen Hurts",
            setting: ["actual": NSNull()]))
        let story = try XCTUnwrap(C.stories(event, markets: markets, deck: [], now: F.finalNow).first)
        XCTAssertNil(story.card.actual)
        XCTAssertEqual(story.split.actual, .absent(C.Words.finalUnavailable))
    }
}
