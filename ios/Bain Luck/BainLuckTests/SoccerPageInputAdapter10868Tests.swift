import SwiftUI
import XCTest
@testable import Bain_Luck

/// #10868 — the whole soccer page input and its manual story stream, part
/// nine, composed from the RETAINED REAL bodies (`SoccerRetained10868`) and
/// the CONSTRUCTED owner admission.
///
/// PREPARED, NOT RUN: written under a source-only hold (no build, no XCTest).
@MainActor
final class SoccerPageInputAdapter10868Tests: XCTestCase {
    private typealias F = SoccerRetained10868
    private typealias P = SoccerPageInputAdapter10868
    private typealias R = SoccerPropReadingAdapter10868

    private func page(_ detail: String, _ history: String, _ markets: String, admitted: R.Markets, now: Date,
                      originals: Int? = 19,
                      stream: P.StreamState = .init()) throws -> SoccerEventPageInput10868 {
        let event = try F.detail(detail)
        let served = try F.markets(markets)
        let props = F.propHost(now)
        let phase = SoccerMatchPageAdapter10868.phase(event, now: now)
        return P.input(
            event,
            history: SoccerHistoryAdapter10868.history(try F.history(history), event: event, phase: phase,
                                                       host: F.historyHost(now)),
            goals: SoccerGoalsAdapter10868.input(event, markets: served, admitted: admitted.goals, host: props),
            both: SoccerBothTeamsAdapter10868.input(event, markets: served, admitted: admitted.both, host: props),
            first: SoccerFirstTeamAdapter10868.input(event, markets: served, history: try F.history(history),
                                                     admitted: admitted.first, host: props),
            halves: SoccerHalvesAdapter10868.input(event, markets: served, admitted: admitted.halves, host: props),
            originalsCount: originals, stream: stream,
            host: F.pageHost(now, observedAt: event.heroProbabilityObservedAt?.asDate))
    }

    private func ref(_ card: SoccerEventPageCard10868, _ scope: String) -> StoryStreamPresentation10868.CardRef {
        .init(scope: scope, id: card.rawValue)
    }

    func testDuringPlayEveryStoryWithContentIsOfferedInTheScreensFixedOrder() throws {
        let input = try page(F.liveDetail, F.liveHistory, F.liveMarkets, admitted: F.liveAdmission, now: F.liveNow)
        let scope = "soccer:15325054:live"

        XCTAssertEqual(input.phase, .live)
        XCTAssertEqual(input.stream.scope, scope)
        XCTAssertEqual(input.stream.cards.map(\.id), ["goals", "both", "first", "halves"])
        XCTAssertEqual(input.stream.cards.map(\.name), [P.Words.goals, P.Words.both, P.Words.first, P.Words.halves])
        XCTAssertEqual(input.stories, [.init(cardID: "goals", card: .goals), .init(cardID: "both", card: .both),
                                       .init(cardID: "first", card: .first), .init(cardID: "halves", card: .halves)])
        XCTAssertNotNil(input.goals)
        XCTAssertNotNil(input.both)
        XCTAssertNotNil(input.first)
        XCTAssertNotNil(input.halves)
    }

    /// The stream is manual: no playback, no dwell, the held card is shown and
    /// Previous/Next name its neighbours.
    func testTheStreamShowsTheHeldCardAndOffersNoPlaybackOrDwell() throws {
        let scope = "soccer:15325054:live"
        let opening = try page(F.liveDetail, F.liveHistory, F.liveMarkets, admitted: F.liveAdmission, now: F.liveNow)
        XCTAssertEqual(opening.stream.primary, ref(.goals, scope))
        XCTAssertEqual(opening.stream.companion, ref(.both, scope))
        XCTAssertEqual(opening.stream.previous, ref(.halves, scope))
        XCTAssertEqual(opening.stream.next, ref(.both, scope))
        XCTAssertEqual(opening.stream.position, "1 of 4")
        XCTAssertEqual(opening.stream.status, P.Words.manualStatus)
        XCTAssertNil(opening.stream.playback)
        XCTAssertNil(opening.stream.dwellFraction)

        let held = try page(F.liveDetail, F.liveHistory, F.liveMarkets, admitted: F.liveAdmission, now: F.liveNow,
                            stream: .init(displayed: .first, readerOpen: true, wide: true))
        XCTAssertEqual(held.stream.primary, ref(.first, scope))
        XCTAssertEqual(held.stream.previous, ref(.both, scope))
        XCTAssertEqual(held.stream.next, ref(.halves, scope))
        XCTAssertEqual(held.stream.position, "3 of 4")
        XCTAssertTrue(held.stream.readerOpen)
        XCTAssertTrue(held.stream.wide)
    }

    /// After the final the retained body keeps no admitted goal total, so the
    /// goal story is not offered — and a host still holding it is shown the
    /// first offered story instead.
    func testAHeldStoryNoLongerOfferedFallsBackToTheFirstOfferedOne() throws {
        let input = try page(F.finalDetail, F.finalHistory, F.finalMarkets, admitted: F.liveAdmission,
                             now: F.finalNow, stream: .init(displayed: .goals))
        XCTAssertNil(input.goals)
        XCTAssertEqual(input.stream.cards.map(\.id), ["both", "first", "halves"])
        XCTAssertEqual(input.stream.primary, ref(.both, "soccer:15325054:final"))
    }

    func testWithNoAdmissionTheHeadlineAndHistoryStayAndNoStoryIsOffered() throws {
        let input = try page(F.liveDetail, F.liveHistory, F.liveMarkets, admitted: .init(), now: F.liveNow)
        XCTAssertTrue(input.stream.cards.isEmpty)
        XCTAssertTrue(input.stories.isEmpty)
        XCTAssertNil(input.stream.primary)
        XCTAssertNil(input.stream.companion)
        XCTAssertNil(input.stream.status)
        XCTAssertEqual(input.headline.home.primary, formatProbability(0.995))
        XCTAssertFalse(input.history.series[0].runs.isEmpty)
    }

    func testTheAllPropsEntryCountsTheCatalogueAndIsAbsentWhenEmpty() throws {
        let counted = try page(F.liveDetail, F.liveHistory, F.liveMarkets, admitted: F.liveAdmission, now: F.liveNow,
                               originals: 19)
        XCTAssertEqual(counted.copy, SoccerEventPageCopy10868(storiesLabel: P.Words.storiesLabel,
                                                              storyUnavailable: P.Words.storyUnavailable,
                                                              allPropsLabel: "\(P.Words.allProps) · 19"))
        XCTAssertNil(try page(F.liveDetail, F.liveHistory, F.liveMarkets, admitted: F.liveAdmission, now: F.liveNow,
                              originals: 0).copy.allPropsLabel)
        XCTAssertNil(try page(F.liveDetail, F.liveHistory, F.liveMarkets, admitted: F.liveAdmission, now: F.liveNow,
                              originals: nil).copy.allPropsLabel)
    }
}
