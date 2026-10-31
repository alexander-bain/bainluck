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
                      originals: Int? = 19, halvesAdmission: P.HalvesAdmission = .routeDefault,
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
            halves: try suppliedHalves(detail, markets, admitted: admitted, now: now),
            halvesAdmission: halvesAdmission,
            originalsCount: originals, stream: stream,
            host: F.pageHost(now, observedAt: event.heroProbabilityObservedAt?.asDate))
    }

    /// What the reusable halves adapter supplies, before the page decides
    /// whether to offer it.
    private func suppliedHalves(_ detail: String, _ markets: String, admitted: R.Markets,
                                now: Date) throws -> PeriodOutcomeComparisonInput10868? {
        SoccerHalvesAdapter10868.input(try F.detail(detail), markets: try F.markets(markets),
                                       admitted: admitted.halves, host: F.propHost(now))
    }

    private func ref(_ card: SoccerEventPageCard10868, _ scope: String) -> StoryStreamPresentation10868.CardRef {
        .init(scope: scope, id: card.rawValue)
    }

    /// The live route's stories, in the screen's fixed order — and, by the
    /// approved route-phase membership, no half-by-half card although the
    /// halves adapter has content for this match.
    func testDuringPlayTheLiveRouteStoriesAreOfferedInTheScreensFixedOrder() throws {
        let input = try page(F.liveDetail, F.liveHistory, F.liveMarkets, admitted: F.liveAdmission, now: F.liveNow)
        let scope = "soccer:15325054:live"

        XCTAssertEqual(input.phase, .live)
        XCTAssertEqual(input.stream.scope, scope)
        XCTAssertEqual(input.stream.cards.map(\.id), ["goals", "both", "first"])
        XCTAssertEqual(input.stream.cards.map(\.name), [P.Words.goals, P.Words.both, P.Words.first])
        XCTAssertEqual(input.stories, [.init(cardID: "goals", card: .goals), .init(cardID: "both", card: .both),
                                       .init(cardID: "first", card: .first)])
        XCTAssertNotNil(input.goals)
        XCTAssertNotNil(input.both)
        XCTAssertNotNil(input.first)
        XCTAssertNotNil(try suppliedHalves(F.liveDetail, F.liveMarkets, admitted: F.liveAdmission, now: F.liveNow))
        XCTAssertNil(input.halves)
    }

    /// The stream is manual: no playback, no dwell, the held card is shown and
    /// Previous/Next name its neighbours.
    func testTheStreamShowsTheHeldCardAndOffersNoPlaybackOrDwell() throws {
        let scope = "soccer:15325054:live"
        let opening = try page(F.liveDetail, F.liveHistory, F.liveMarkets, admitted: F.liveAdmission, now: F.liveNow)
        XCTAssertEqual(opening.stream.primary, ref(.goals, scope))
        XCTAssertEqual(opening.stream.companion, ref(.both, scope))
        XCTAssertEqual(opening.stream.previous, ref(.first, scope))
        XCTAssertEqual(opening.stream.next, ref(.both, scope))
        XCTAssertEqual(opening.stream.position, "1 of 3")
        XCTAssertEqual(opening.stream.status, P.Words.manualStatus)
        XCTAssertNil(opening.stream.playback)
        XCTAssertNil(opening.stream.dwellFraction)

        let held = try page(F.liveDetail, F.liveHistory, F.liveMarkets, admitted: F.liveAdmission, now: F.liveNow,
                            stream: .init(displayed: .first, readerOpen: true, wide: true))
        XCTAssertEqual(held.stream.primary, ref(.first, scope))
        XCTAssertEqual(held.stream.previous, ref(.both, scope))
        XCTAssertEqual(held.stream.next, ref(.goals, scope))
        XCTAssertEqual(held.stream.position, "3 of 3")
        XCTAssertTrue(held.stream.readerOpen)
        XCTAssertTrue(held.stream.wide)
    }

    // MARK: - The half-by-half card's route-phase membership (Design, wave-1 review)

    func testTheDefaultAdmissionOffersHalvesAfterTheFinalOnly() {
        XCTAssertFalse(P.offersHalves(phase: .before, admission: .routeDefault))
        XCTAssertFalse(P.offersHalves(phase: .live, admission: .routeDefault))
        XCTAssertTrue(P.offersHalves(phase: .final, admission: .routeDefault))
        XCTAssertTrue([SoccerEventPagePhase10868.before, .live, .final].allSatisfy {
            P.offersHalves(phase: $0, admission: .explicit)
        })
    }

    /// Before kickoff the halves adapter has content (Hull–Everton's two half
    /// markets) but the before route does not carry the card.
    func testBeforeKickoffTheHalvesCardIsAbsentByDefault() throws {
        let input = try page(F.hullDetail, F.hullHistory, F.hullMarkets, admitted: F.hullAdmission, now: F.hullNow)
        XCTAssertEqual(input.phase, .before)
        XCTAssertNotNil(try suppliedHalves(F.hullDetail, F.hullMarkets, admitted: F.hullAdmission, now: F.hullNow))
        XCTAssertNil(input.halves)
        XCTAssertFalse(input.stream.cards.map(\.id).contains("halves"))
        XCTAssertFalse(input.stories.contains { $0.card == .halves })
    }

    func testAfterTheFinalTheHalvesCardIsOfferedByDefault() throws {
        let input = try page(F.finalDetail, F.finalHistory, F.finalMarkets, admitted: F.liveAdmission, now: F.finalNow)
        XCTAssertEqual(input.phase, .final)
        XCTAssertNotNil(input.halves)
        XCTAssertEqual(input.stream.cards.map(\.id).last, "halves")
        XCTAssertTrue(input.stories.contains(.init(cardID: "halves", card: .halves)))
    }

    /// The journey and replay hosts — or any other owner-supplied context —
    /// admit the card explicitly in any phase.
    func testAnExplicitAdmissionOffersTheHalvesCardBeforeKickoffAndDuringPlay() throws {
        let live = try page(F.liveDetail, F.liveHistory, F.liveMarkets, admitted: F.liveAdmission, now: F.liveNow,
                            halvesAdmission: .explicit)
        XCTAssertEqual(live.stream.cards.map(\.id), ["goals", "both", "first", "halves"])
        XCTAssertEqual(live.halves,
                       try suppliedHalves(F.liveDetail, F.liveMarkets, admitted: F.liveAdmission, now: F.liveNow))

        let before = try page(F.hullDetail, F.hullHistory, F.hullMarkets, admitted: F.hullAdmission, now: F.hullNow,
                              halvesAdmission: .explicit)
        XCTAssertNotNil(before.halves)
        XCTAssertTrue(before.stream.cards.map(\.id).contains("halves"))
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
