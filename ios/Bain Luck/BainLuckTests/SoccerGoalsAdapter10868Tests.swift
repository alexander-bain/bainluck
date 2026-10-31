import XCTest
@testable import Bain_Luck

/// #10868 — the goal milestones story, part four, on the RETAINED REAL bodies
/// (`SoccerRetained10868`) and the CONSTRUCTED owner admission
/// `SoccerRetained10868.liveAdmission` / `hullAdmission`.
///
/// PREPARED, NOT RUN: written under a source-only hold (no build, no XCTest).
@MainActor
final class SoccerGoalsAdapter10868Tests: XCTestCase {
    private typealias F = SoccerRetained10868
    private typealias G = SoccerGoalsAdapter10868
    private typealias R = SoccerPropReadingAdapter10868
    private typealias T = TotalMilestoneInput10868

    private func liveCard() throws -> TotalMilestoneInput10868 {
        try XCTUnwrap(G.input(try F.detail(F.liveDetail), markets: try F.markets(F.liveMarkets),
                              admitted: F.liveAdmission.goals, host: F.propHost(F.liveNow)))
    }

    private func clock(_ stamp: String, _ now: Date) -> String {
        SoccerMatchPageAdapter10868.clockWords(stamp.asDate!, host: F.propHost(now).words)
    }

    func testDuringPlayEachAdmittedTotalIsOneMilestoneInAdmissionOrder() throws {
        let card = try liveCard()
        XCTAssertEqual(card.phase, .during)
        XCTAssertEqual(card.title, G.Words.liveTitle)
        XCTAssertEqual(card.milestones.map(\.id), ["242143183", "242143187", "242765587"])
        XCTAssertEqual(card.milestones.map(\.quantityLabel), ["3+", "5+", "6+"])
        XCTAssertEqual(card.milestones.map(\.title), ["3+ goals", "5+ goals", "6+ goals"])
        XCTAssertNil(card.projection)
        XCTAssertEqual(card.markStyle, .stems)
        XCTAssertEqual(card.quantityDomain, TotalMilestoneDomain10868(lower: 0, upper: 7))
    }

    /// The served totals rows all read 15% on a sibling-capped clock: none is
    /// the in-play chance. A milestone the score has passed says so instead.
    func testDuringPlayAReachedMilestoneSaysSoAndTheOthersWithholdTheSiblingClockedQuote() throws {
        let card = try liveCard()
        XCTAssertEqual(card.milestones[0].current, .reached(G.Words.reachedSoFar))
        XCTAssertNil(card.milestones[0].performance)
        XCTAssertEqual(card.milestones[1].current, .withheld(R.Words.noRecentUpdate))
        XCTAssertEqual(card.milestones[1].performance, "1 more for 5+")
        XCTAssertEqual(card.milestones[2].current, .withheld(R.Words.noRecentUpdate))
        XCTAssertEqual(card.milestones[2].performance, "2 more for 6+")
        XCTAssertFalse(card.milestones.contains {
            if case .recorded(let o, _) = $0.current { return o.probability == 0.15 }
            return false
        })
        // Nothing is settled during play: unknown, never a loss.
        XCTAssertTrue(card.milestones.allSatisfy { $0.result == .unconfirmed(R.Words.resultUnavailable) })
    }

    func testOnceStartedThePreMatchChancesAreTheStoredPinsAndTheDefaultIsNearestEvenOdds() throws {
        let card = try liveCard()
        XCTAssertEqual(card.milestones.map { $0.before?.probability }, [0.5, 0.13, 0.06])
        XCTAssertEqual(card.milestones.map { $0.before?.text },
                       [formatProbability(0.5), formatProbability(0.13), formatProbability(0.06)])
        XCTAssertEqual(card.selectedMilestoneID, "242143183")
        XCTAssertEqual(card.timing, TotalMilestoneTiming10868(
            milestoneID: "242143183", title: "3+ goals · \(G.Words.timingSuffix)",
            lines: ["\(T.pregameTitle): \(R.Words.savedBeforeStart) \(clock("2026-10-12T11:47:12.330899+00:00", F.liveNow)) · Polymarket",
                    "\(T.actualSoFarTitle): \(G.Words.reachedSoFar)"]))
    }

    func testDuringPlayTheCountIsTheProducersScoreDatedByItsOwnClock() throws {
        guard case .count(let count) = try liveCard().actual else { return XCTFail("the live body serves 4–0") }
        XCTAssertEqual(count.quantity, 4)
        XCTAssertEqual(count.text, "4")
        XCTAssertEqual(count.unit, "goals")
        XCTAssertEqual(count.ruleLabel, "4 so far")
    }

    func testAHeldMilestoneIsKeptAndItsTimingFollowsIt() throws {
        let card = try XCTUnwrap(G.input(try F.detail(F.liveDetail), markets: try F.markets(F.liveMarkets),
                                         admitted: F.liveAdmission.goals, host: F.propHost(F.liveNow),
                                         selectedMilestoneID: "242143187"))
        XCTAssertEqual(card.selectedMilestoneID, "242143187")
        XCTAssertEqual(card.timing?.lines.last, "\(T.currentStatusTitle): \(R.Words.noRecentUpdate)")
    }

    // MARK: - No milestone

    /// Hull–Everton's admitted O/U 4.5 is served as an Under row only: no
    /// milestone is made from its complement, so there is no card.
    func testAnUnderOnlyMarketMakesNoMilestone() throws {
        XCTAssertNil(G.input(try F.detail(F.hullDetail), markets: try F.markets(F.hullMarkets),
                             admitted: F.hullAdmission.goals, host: F.propHost(F.hullNow)))
    }

    /// The retained final body keeps no row of the admitted Polymarket totals.
    func testAfterTheFinalWithNoAdmittedRowThereIsNoCard() throws {
        XCTAssertNil(G.input(try F.detail(F.finalDetail), markets: try F.markets(F.finalMarkets),
                             admitted: F.liveAdmission.goals, host: F.propHost(F.finalNow)))
    }

    /// CONSTRUCTED admission: the final body's Kalshi "Total Goals" market,
    /// which serves two Over rows (0.5 and 1.5) under ONE market id. Two lines
    /// are not one original milestone, so neither is made.
    func testAMarketServingTwoOverLinesMakesNoMilestone() throws {
        XCTAssertNil(G.input(try F.detail(F.finalDetail), markets: try F.markets(F.finalMarkets),
                             admitted: [65568608], host: F.propHost(F.finalNow)))
    }

    func testNoAdmissionMakesNoCard() throws {
        XCTAssertNil(G.input(try F.detail(F.liveDetail), markets: try F.markets(F.liveMarkets),
                             admitted: [], host: F.propHost(F.liveNow)))
    }
}
