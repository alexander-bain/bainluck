import SwiftUI
import XCTest
@testable import Bain_Luck

/// #10868 — the baseball game adapter, part five ("All props", the original
/// catalogue and its Details), on the RETAINED REAL `/game-markets` of the
/// White Sox–Astros game (`BaseballRetained10868`).
///
/// PREPARED, NOT RUN: written under a source-only hold (no build, no XCTest).
///
/// Membership, order, identity, readings and grade are the accepted originals
/// adapter's (H4, `HockeyJourneyOriginalsAdapter10868`), called, not copied.
/// What is baseball's own, and pinned here: its scope, its words, and that
/// exactly two of H4's absence words are said in chance-and-availability
/// words while every other field stays H4's.
@MainActor
final class BaseballOriginalsAdapter10868Tests: XCTestCase {
    private typealias F = BaseballRetained10868
    private typealias O = BaseballOriginalsAdapter10868
    private typealias H4 = HockeyJourneyOriginalsAdapter10868
    private typealias Details = OriginalMarketDetails9483

    private static let tint = Color(red: 0.0, green: 0.18, blue: 0.38)

    func testAfterTheFinalAllPropsListsEveryServedOriginalOnceInTheCataloguesOrder() throws {
        let event = try F.finalEvent()
        let markets = try F.markets()
        let host = F.originalsHost(F.finalNow)
        let group = O.originals(event, markets: markets, host: host, tint: Self.tint)
        let found = H4.matched(markets, status: event.status, now: F.finalNow)
        let catalogue = try XCTUnwrap(group.catalogue)
        let shared = found.map { H4.original($0, event: event, phase: .final, started: true, host: host) }

        XCTAssertFalse(found.isEmpty)
        XCTAssertEqual(catalogue.scope, "mlb:15321836:final:originals")
        XCTAssertEqual(catalogue.originals.map(\.identity), shared.map(\.identity), "H4's members, in H4's order")
        XCTAssertEqual(Set(catalogue.originals.map(\.identity)).count, catalogue.originals.count, "each once")
        XCTAssertEqual(catalogue.originals, shared.map(O.reworded))
        XCTAssertTrue(catalogue.originals.allSatisfy { $0.mode == .result }, "after the final each shows its own grade")
        XCTAssertEqual(group.labels.count, catalogue.originals.count)
        XCTAssertEqual(group.heading, "All props")
        XCTAssertEqual(group.context, "\(found.count) originals")
        XCTAssertEqual(group.emptyWords, "No original props recorded for this game")
        XCTAssertEqual(group.unavailableChoice, "Unnamed original")
        XCTAssertEqual(group.tint, Self.tint)
        XCTAssertNil(group.selection)

        // H4's two absence words never reach the reader in their old form.
        XCTAssertFalse(catalogue.originals.contains { $0.pregame == Details.Reading.missing(H4.Words.noPregameChance) })
        XCTAssertFalse(catalogue.originals.contains { $0.later == Details.Reading.missing(H4.Words.noInGameReading) })
        XCTAssertEqual(catalogue.originals.filter { $0.pregame == Details.Reading.missing("Pregame chance unavailable") }.count,
                       shared.filter { $0.pregame == Details.Reading.missing(H4.Words.noPregameChance) }.count)
    }

    /// CONSTRUCTED: the event is `liveEvent`.
    func testDuringPlayTheSameMembersAreReadInTheirLivePhaseAndScope() throws {
        let event = try F.liveEvent()
        let markets = try F.markets()
        let host = F.originalsHost(F.liveNow)
        let group = O.originals(event, markets: markets, host: host, tint: Self.tint)
        let catalogue = try XCTUnwrap(group.catalogue)
        let found = H4.matched(markets, status: event.status, now: F.liveNow)
        let shared = found.map { H4.original($0, event: event, phase: .live, started: true, host: host) }

        XCTAssertEqual(catalogue.scope, "mlb:15321836:live:originals")
        XCTAssertEqual(catalogue.originals, shared.map(O.reworded))
        XCTAssertFalse(catalogue.originals.contains { $0.mode == .result }, "no grade is read during play")
        XCTAssertFalse(catalogue.originals.contains { $0.later == Details.Reading.missing(H4.Words.noInGameReading) })
    }

    /// CONSTRUCTED: the final detail with only `id` changed.
    func testAnotherEventsMarketsOrNoneAreNoCatalogue() throws {
        let other = try F.detail(F.edited(F.finalDetail, setting: ["id": 1]))
        let host = F.originalsHost(F.finalNow)
        let group = O.originals(other, markets: try F.markets(), host: host, tint: Self.tint)
        XCTAssertNil(group.catalogue)
        XCTAssertNil(group.context)
        XCTAssertEqual(group.emptyWords, "No original props recorded for this game")
        XCTAssertNil(O.originals(try F.finalEvent(), markets: nil, host: host, tint: Self.tint).catalogue)
    }

    func testRewordingChangesOnlyTheTwoAbsenceWordsAndKeepsEveryOtherField() throws {
        let event = try F.finalEvent()
        let markets = try F.markets()
        let host = F.originalsHost(F.finalNow)
        let match = try XCTUnwrap(H4.matched(markets, status: event.status, now: F.finalNow).first)
        let real = H4.original(match, event: event, phase: .final, started: true, host: host)

        // CONSTRUCTED readings on a real original.
        func with(pregame: Details.Reading, later: Details.Reading?) -> Details.Original {
            Details.Original(identity: real.identity, title: real.title, outcome: real.outcome, mode: real.mode,
                             pregame: pregame, later: later, grade: real.grade, about: real.about,
                             beforeLabel: "Before first pitch")
        }
        let reworded = O.reworded(with(pregame: .missing(H4.Words.noPregameChance),
                                       later: Details.Reading.missing(H4.Words.noInGameReading)))
        XCTAssertEqual(reworded, with(pregame: .missing("Pregame chance unavailable"),
                                      later: Details.Reading.missing("In-game chance unavailable")))

        let kept = with(pregame: .value("59%", placement: 0.59, provenance: "Saved before the start"),
                        later: Details.Reading.missing("No current chance"))
        XCTAssertEqual(O.reworded(kept), kept, "a figure and every other reason are H4's, unchanged")
        XCTAssertEqual(O.reworded(with(pregame: .missing("Rules unavailable"), later: nil)),
                       with(pregame: .missing("Rules unavailable"), later: nil))
        XCTAssertEqual(O.scope(event, phase: .before), "mlb:15321836:before:originals")
    }
}
