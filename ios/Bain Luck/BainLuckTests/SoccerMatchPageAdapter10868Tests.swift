import SwiftUI
import XCTest
@testable import Bain_Luck

/// #10868 — the soccer match adapter, part one (phase, header, three-outcome
/// headline), on the RETAINED REAL bodies in `SoccerRetainedAdapter10868Tests`
/// (`SoccerRetained10868`): Hull City v Everton before kickoff, and Real
/// Valladolid CF v Albacete live at 4–0 and after its 5–0 final.
///
/// PREPARED, NOT RUN: written under a source-only hold (no build, no XCTest).
///
/// Every expected figure is the production formatter's own output for the
/// served value (`formatProbability`), and every clock or name is the adapter's
/// own words for the served instant, so a test pins the rule, not a spelling
/// that a locale could move. CONSTRUCTED variants change exactly the one key
/// they name.
@MainActor
final class SoccerMatchPageAdapter10868Tests: XCTestCase {
    private typealias F = SoccerRetained10868
    private typealias A = SoccerMatchPageAdapter10868

    private func observed(_ event: EventDetail) -> Date? { event.heroProbabilityObservedAt?.asDate }

    // MARK: - Phase

    func testEachRetainedBodyReadsAsItsOwnPhase() throws {
        XCTAssertEqual(A.phase(try F.detail(F.hullDetail), now: F.hullNow), .before)
        XCTAssertEqual(A.phase(try F.detail(F.liveDetail), now: F.liveNow), .live)
        XCTAssertEqual(A.phase(try F.detail(F.finalDetail), now: F.finalNow), .final)
    }

    /// CONSTRUCTED: the live body with only `status` changed to `suspended`. A
    /// started suspended match is during play and wears the one suspended label.
    func testAStartedSuspendedMatchWearsTheSuspendedTreatment() throws {
        let event = try F.detail(F.edited(F.liveDetail, setting: ["status": "suspended"]))
        XCTAssertEqual(A.phase(event, now: F.liveNow), .live)
        let header = A.header(event, host: F.pageHost(F.liveNow, observedAt: observed(event)))
        XCTAssertEqual(header.state, EventState.suspendedLabel(authorityPeriod: nil))
    }

    // MARK: - Headline

    func testBeforeKickoffTheHomeChanceIsTheHerosCurrentPairAndDrawAndAwayKeepTheirWords() throws {
        let event = try F.detail(F.hullDetail)
        let host = F.pageHost(F.hullNow, observedAt: observed(event))
        let headline = A.headline(event, host: host)

        // The hero's home price, rounded alone as the draw-priced hero rounds it.
        XCTAssertEqual(headline.home.primary, formatProbability(0.265))
        XCTAssertEqual(headline.primaryHeading.title, EventHeadlinePhase9483.current.label)
        XCTAssertEqual(headline.primaryHeading.context,
                       "Recorded \(A.clockWords(observed(event)!, host: host))")
        XCTAssertNil(headline.comparisonHeading)
        // Every sportsbook row serves an away figure; none is the away win chance.
        XCTAssertNil(headline.away.primary)
        XCTAssertEqual(headline.away.primaryUnavailable, A.Words.awayChanceUnavailable)
        XCTAssertNil(headline.draw.primary)
        XCTAssertEqual(headline.draw.primaryUnavailable, A.Words.drawChanceUnavailable)
        XCTAssertEqual(headline.outcomes.map(\.label),
                       [A.Words.outcome(A.names(event).home), "Draw", A.Words.outcome(A.names(event).away)])
    }

    func testDuringPlayTheCurrentHomeChanceSitsBesideTheOpeningFallbackNamedAsSuch() throws {
        let event = try F.detail(F.liveDetail)
        let headline = A.headline(event, host: F.pageHost(F.liveNow, observedAt: observed(event)))

        XCTAssertEqual(headline.home.primary, formatProbability(0.995))
        XCTAssertEqual(headline.primaryHeading.title, EventHeadlinePhase9483.current.label)
        // `prematch_odds` is null on this body: the reading is `opening_odds`,
        // and it is named an opening chance, not a pre-match one.
        XCTAssertEqual(headline.comparisonHeading?.title, A.Words.openingChance)
        XCTAssertEqual(headline.home.comparison, formatProbability(0.4929))
        XCTAssertEqual(headline.comparisonText(for: headline.draw), .unavailable(A.Words.drawChanceUnavailable))
        // The served three-way rows on `/game-markets` (Draw 0.4%) are not read.
        XCTAssertNil(headline.draw.primary)
        XCTAssertNil(headline.away.comparison)
    }

    /// CONSTRUCTED: the same live body with delivery interrupted.
    func testAnInterruptedPageCallsItsPairLastRecorded() throws {
        let event = try F.detail(F.liveDetail)
        let host = A.Host(probabilityObservedAt: observed(event), deliveryInterrupted: true, now: F.liveNow,
                          calendar: F.pacific, locale: F.locale)
        XCTAssertEqual(A.headline(event, host: host).primaryHeading.title, EventHeadlinePhase9483.lastRecorded.label)
    }

    func testAfterTheFinalThePreMatchChanceLeadsAndTheServedAwayFigureIsWithheld() throws {
        let event = try F.detail(F.finalDetail)
        let headline = A.headline(event, host: F.pageHost(F.finalNow, observedAt: observed(event)))

        XCTAssertEqual(headline.primaryHeading.title, A.Words.preMatchChance)
        XCTAssertEqual(headline.primaryHeading.context, "Polymarket")
        XCTAssertEqual(headline.home.primary, formatProbability(0.51))
        // `prematch_odds.away_probability` 0.225 is served; a draw-priced sport
        // never prints it as the away win chance.
        XCTAssertNil(headline.away.primary)
        XCTAssertNil(headline.comparisonHeading)
        // The settled hero 1.0 is a result, never a chance on the headline.
        XCTAssertNotEqual(headline.home.primary, formatProbability(1.0))
    }

    // MARK: - Header

    func testBeforeKickoffTheHeaderSaysKickoffAndShowsNoScoreOrClock() throws {
        let event = try F.detail(F.hullDetail)
        let host = F.pageHost(F.hullNow, observedAt: observed(event))
        let header = A.header(event, host: host)
        let start = event.commenceTime!.asDate!

        XCTAssertEqual(header.state, A.Words.beforeKickoff)
        XCTAssertEqual(header.date, "\(A.dayWords(start, host: host)) · Kickoff \(A.timeWords(start, host: host))")
        XCTAssertNil(header.score)
        XCTAssertNil(header.clock)
        // No sportsbook or ladder pair is served for this fixture.
        XCTAssertEqual(header.projection?.reading, .unavailable(A.Words.projectionUnavailable))
    }

    func testDuringPlayTheScoreKeepsItsOwnClockAndTheMatchClockIsUnavailable() throws {
        let event = try F.detail(F.liveDetail)
        let host = F.pageHost(F.liveNow, observedAt: observed(event))
        let header = A.header(event, host: host)
        let names = A.names(event)
        let scoredAt = event.scoreObservedAt!.asDate!

        XCTAssertEqual(header.state, A.Words.inPlay)
        XCTAssertEqual(header.score, .actual(home: "4", away: "0",
                                             context: "Score observed \(A.clockWords(scoredAt, host: host))",
                                             spoken: "\(names.home) 4, \(names.away) 0"))
        // ESPN serves no period or clock for this match.
        XCTAssertEqual(header.clock, .unavailable(A.Words.clockUnavailable))
        // No in-play projection object is served: H1's live arm says so and
        // never falls back to the ladders' pair.
        XCTAssertEqual(header.projection?.reading, .unavailable(A.Words.projectionUnavailable))
        XCTAssertNil(header.projection?.comparison)
    }

    func testAfterTheFinalTheStateNamesTheServedWinnerAndTheScoreIsFinal() throws {
        let event = try F.detail(F.finalDetail)
        let header = A.header(event, host: F.pageHost(F.finalNow, observedAt: observed(event)))
        let names = A.names(event)

        XCTAssertEqual(header.state, "Final · \(names.home) won")
        XCTAssertEqual(header.score, .actual(home: "5", away: "0", context: "Final score",
                                             spoken: "Final: \(names.home) 5, \(names.away) 0"))
        XCTAssertNil(header.clock)
        XCTAssertEqual(header.projection?.reading, .unavailable(A.Words.projectionUnavailable))
    }

    /// CONSTRUCTED: the live body with `home_score` removed. A missing score is
    /// the slot's own words, never a 0.
    func testAMissingScoreIsUnavailableNeverZero() throws {
        let event = try F.detail(F.edited(F.liveDetail, removing: ["home_score"]))
        let header = A.header(event, host: F.pageHost(F.liveNow, observedAt: observed(event)))
        XCTAssertEqual(header.score, .unavailable(A.Words.scoreUnavailable))
    }
}
