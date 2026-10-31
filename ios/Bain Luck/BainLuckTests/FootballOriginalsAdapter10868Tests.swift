import SwiftUI
import XCTest
@testable import Bain_Luck

/// #10868 — "All props" for the football screen: membership, order, identity,
/// labels and grade are the accepted hockey originals adapter's (H4), the
/// in-game reading the soccer adapter's; football supplies only the pregame
/// reading. On RETAINED REAL bodies (`FootballRetained10868`).
///
/// PREPARED, NOT RUN: written under a source-only hold (no build, no XCTest).
///
/// Served values used: live Philadelphia team field goals 1+ `pregame_mark`
/// 0.78 (Kalshi); final Jacksonville 1+ `is_winner` true, `api_settlement`;
/// pregame Rams team field goals 2+ 0.55 at 05:40:37Z (4.6 minutes before the
/// capture), Rams 1+ 0.755 with no observation clock.
@MainActor
final class FootballOriginalsAdapter10868Tests: XCTestCase {
    private typealias F = FootballRetained10868
    private typealias O = FootballOriginalsAdapter10868
    private typealias H4 = HockeyJourneyOriginalsAdapter10868
    private typealias Details = OriginalMarketDetails9483

    private func match(_ outcome: String, in markets: GameMarketsResponse, event: EventDetail,
                       now: Date) throws -> H4.Match {
        let found = H4.matched(markets, status: event.status, now: now).filter { $0.source.prop?.outcomeName == outcome }
        XCTAssertEqual(found.count, 1, outcome)
        return try XCTUnwrap(found.first)
    }

    private func original(_ match: H4.Match, in group: FootballEventPageOriginals10868) throws -> Details.Original {
        let identity = H4.identity(of: match.source)
        let found = group.catalogue?.originals.filter { $0.identity == identity } ?? []
        XCTAssertEqual(found.count, 1)
        return try XCTUnwrap(found.first)
    }

    func testTheLiveCatalogueIsH4sMembershipWithEachOriginalsOwnPregameMark() throws {
        let event = try F.detail(F.liveDetail)
        let markets = try F.markets(F.liveMarkets)
        let host = F.originalsHost(F.liveNow)
        let group = O.originals(event, markets: markets, host: host, tint: .blue)

        let matched = H4.matched(markets, status: event.status, now: F.liveNow)
        XCTAssertEqual(group.catalogue?.scope, "nfl:14639175:live:originals")
        XCTAssertEqual(group.catalogue?.originals.map(\.identity), matched.map { H4.identity(of: $0.source) })
        XCTAssertEqual(group.heading, "All props")
        XCTAssertEqual(group.context, "\(matched.count) originals")
        XCTAssertNil(group.selection)

        let fieldGoal = try match("Philadelphia: 1+", in: markets, event: event, now: F.liveNow)
        let made = try original(fieldGoal, in: group)
        XCTAssertEqual(made.mode, .comparison(.current))
        XCTAssertEqual(made.pregame, .value("78%", placement: 0.78,
                                           provenance: "Saved before the start · " + SourceLabels.label(for: "kalshi")))
        XCTAssertEqual(made.later, SoccerOriginalsAdapter10868.laterReading(fieldGoal, event: event, host: host).later)
        XCTAssertNil(made.grade)
        XCTAssertEqual(group.labels[made.identity], H4.label(fieldGoal.source, event: event))
    }

    func testTheFinalCatalogueGradesEachOriginalByItsOwnContract() throws {
        let event = try F.detail(F.finalDetail)
        let markets = try F.markets(F.finalMarkets)
        let group = O.originals(event, markets: markets, host: F.originalsHost(F.finalNow), tint: .blue)

        let fieldGoal = try match("Jacksonville: 1+", in: markets, event: event, now: F.finalNow)
        let made = try original(fieldGoal, in: group)
        XCTAssertEqual(made.mode, .result)
        XCTAssertNil(made.later)
        XCTAssertEqual(made.grade, H4.contractGrade(fieldGoal.source))
        XCTAssertNotNil(made.grade)
        XCTAssertEqual(made.pregame, .value("79%", placement: 0.785,
                                           provenance: "Saved before the start · " + SourceLabels.label(for: "kalshi")))
    }

    func testBeforeTheStartOnlyARecentQuoteOnItsOwnClockPrints() throws {
        let event = try F.detail(F.pregameDetail)
        let markets = try F.markets(F.pregameMarkets)
        let host = F.originalsHost(F.pregameNow)
        let group = O.originals(event, markets: markets, host: host, tint: .blue)

        let recent = try original(try match("Los Angeles Rams: 2+", in: markets, event: event, now: F.pregameNow),
                                  in: group)
        XCTAssertEqual(recent.mode, .pregame)
        let at = try XCTUnwrap("2026-10-12T05:40:37.022224+00:00".asDate)
        XCTAssertEqual(recent.pregame, .value(
            "55%", placement: 0.55,
            provenance: "Recorded " + SoccerMatchPageAdapter10868.clockWords(at, host: host.words)
                + " · " + SourceLabels.label(for: "kalshi")))

        let undated = try original(try match("Los Angeles Rams: 1+", in: markets, event: event, now: F.pregameNow),
                                   in: group)
        XCTAssertEqual(undated.pregame, .missing(AllMarketsCatalogView9483.noRecentPrice))
        let stale = try original(try match("Los Angeles Rams: 3+", in: markets, event: event, now: F.pregameNow),
                                 in: group)
        XCTAssertEqual(stale.pregame, .missing(AllMarketsCatalogView9483.noRecentPrice))
    }

    func testTheHeldSelectionIsPassedThroughForTheLeafToResolve() throws {
        let event = try F.detail(F.liveDetail)
        let selection = Details.Selection(scope: "nfl:14639175:live:originals",
                                          identity: Details.Identity(source: "kalshi", market: "65113446", side: "x"))
        let group = O.originals(event, markets: try F.markets(F.liveMarkets), host: F.originalsHost(F.liveNow),
                                tint: .blue, selection: selection)
        XCTAssertEqual(group.selection, selection)
    }

    func testNoServedOutcomeIsNoCatalogueAndSaysSo() throws {
        let event = try F.detail(F.liveDetail)
        let group = O.originals(event, markets: nil, host: F.originalsHost(F.liveNow), tint: .blue)
        XCTAssertNil(group.catalogue)
        XCTAssertNil(group.context)
        XCTAssertEqual(group.emptyWords, "No original props recorded for this game")
    }
}
