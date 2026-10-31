import XCTest
@testable import Bain_Luck

/// #10868 — the both-teams-to-score story, part five, on the RETAINED REAL
/// bodies (`SoccerRetained10868`) and the CONSTRUCTED owner admission.
///
/// PREPARED, NOT RUN: written under a source-only hold (no build, no XCTest).
@MainActor
final class SoccerBothTeamsAdapter10868Tests: XCTestCase {
    private typealias F = SoccerRetained10868
    private typealias B = SoccerBothTeamsAdapter10868
    private typealias R = SoccerPropReadingAdapter10868
    private typealias T = BothTeamsScoreInput10868

    private func card(_ detail: String, _ markets: String, admitted: Int?, now: Date,
                      selected: String? = nil) throws -> BothTeamsScoreInput10868 {
        try XCTUnwrap(B.input(try F.detail(detail), markets: try F.markets(markets), admitted: admitted,
                              host: F.propHost(now), selectedOutcomeID: selected))
    }

    func testDuringPlayYesAndNoAreIndependentCurrentChancesNeverAComplement() throws {
        let both = try card(F.liveDetail, F.liveMarkets, admitted: F.liveAdmission.both, now: F.liveNow)
        XCTAssertEqual(both.phase, .during)
        XCTAssertEqual(both.marketID, "64353426")
        XCTAssertEqual(both.outcomes.map(\.id), ["242143190", "242143189"])
        XCTAssertEqual(both.outcomes.map(\.label), ["No", "Yes"])

        let currents: [Double?] = both.outcomes.map {
            if case .recorded(let o, _) = $0.current { return o.probability }
            return nil
        }
        // 50.5% and 49%: as served, never forced to sum to 100%.
        XCTAssertEqual(currents, [0.505, 0.49])
        XCTAssertEqual(both.outcomes.map { $0.before?.probability }, [0.455, 0.55])
        XCTAssertTrue(both.outcomes.allSatisfy { $0.result == .unconfirmed(R.Words.resultUnavailable) })
    }

    // MARK: - The current slot (Design, wave-1 review 2026-10-31: H3/H4 rules)

    /// THE REAL-ROW PROOF. The retained live body's both-teams market 64353426:
    /// outcome 242143190 "No" 50.5% and outcome 242143189 "Yes" 49%, each its own
    /// Polymarket `other` row (its own clock), observed 12:54:58 — after the
    /// 12:00 kickoff, 64 s before `now`, unsettled. Every source, lifecycle and
    /// currentness check passes, so each fills its own current slot, with its
    /// own clock and venue.
    func testDuringPlayTheRetainedYesAndNoRowsFillTheCurrentSlotOnlyBecauseEveryCheckPasses() throws {
        let event = try F.detail(F.liveDetail)
        let host = F.propHost(F.liveNow)
        let legs = R.legs(64353426, in: try F.markets(F.liveMarkets))
        XCTAssertEqual(legs.map(\.id), ["242143190", "242143189"])
        XCTAssertTrue(legs.allSatisfy { $0.clockIsOwn && $0.row.source == "polymarket" && R.settlement($0) == nil })
        let stamp = "2026-10-12T12:54:58.549918+00:00"
        let observed = try XCTUnwrap(stamp.asDate)
        XCTAssertGreaterThanOrEqual(observed, try XCTUnwrap(event.commenceTime?.asDate))
        XCTAssertTrue(NFLMilestoneCard9483.isRecent(stamp, now: F.liveNow))

        let both = try card(F.liveDetail, F.liveMarkets, admitted: 64353426, now: F.liveNow)
        let words = host.words
        let clock = SoccerMatchPageAdapter10868.clockWords(observed, host: words)
        let time = SoccerMatchPageAdapter10868.timeWords(observed, host: words)
        func expected(_ value: Double) -> BothTeamsCurrent10868 {
            .recorded(BothTeamsObservation10868(probability: value, text: formatProbability(value), timeText: time,
                                                accessibilityDetail: "recorded \(clock) · Polymarket"),
                      movement: nil)
        }
        XCTAssertEqual(both.outcomes.map(\.current), [expected(0.505), expected(0.49)])
    }

    /// Settled control. CONSTRUCTED: the live body with both rows carrying the
    /// grades the final body serves for the same outcome ids. A settled row has
    /// no current chance; its grade is its result.
    func testDuringPlayASettledYesOrNoHasNoCurrentChanceAndShowsItsGrade() throws {
        let body = try F.graded(F.liveMarkets, [242143190: true, 242143189: false])
        let both = try card(F.liveDetail, body, admitted: F.liveAdmission.both, now: F.liveNow)
        XCTAssertTrue(both.outcomes.allSatisfy { $0.current == .unavailable(R.Words.settledNoChance) })
        XCTAssertEqual(both.outcomes.map(\.result), [.won(OutcomeVerdict.won.label), .lost(OutcomeVerdict.lost.label)])
    }

    /// Stale control. CONSTRUCTED `now`: forty minutes later the same rows are
    /// no recent update — never the current chance.
    func testDuringPlayAStaleYesOrNoIsNoRecentUpdate() throws {
        let both = try card(F.liveDetail, F.liveMarkets, admitted: F.liveAdmission.both, now: F.liveLaterNow)
        XCTAssertTrue(both.outcomes.allSatisfy { $0.current == .withheld(R.Words.noRecentUpdate) })
        XCTAssertTrue(both.outcomes.allSatisfy { $0.result == .unconfirmed(R.Words.resultUnavailable) })
    }

    /// Missing control. CONSTRUCTED: the Yes row with only its `probability` set
    /// to null. Yes says its in-play chance is unavailable; No is untouched and
    /// never completes it.
    func testDuringPlayAYesWithNoPriceIsUnavailableAndNoIsNotItsComplement() throws {
        let body = try F.editedRow(F.liveMarkets, outcomeID: 242143189, setting: ["probability": NSNull()])
        let both = try card(F.liveDetail, body, admitted: F.liveAdmission.both, now: F.liveNow)
        XCTAssertEqual(both.outcomes[1].current, .unavailable(R.Words.inPlayUnavailable))
        guard case .recorded(let no, _) = both.outcomes[0].current else { return XCTFail("No keeps its own quote") }
        XCTAssertEqual(no.probability, 0.505)
    }

    /// Pre-kickoff control. CONSTRUCTED: the Yes row with only its `observed_at`
    /// moved before the 12:00 kickoff — a pre-match quote is never the in-play
    /// chance.
    func testDuringPlayAYesQuotedBeforeKickoffIsNotTheCurrentChance() throws {
        let body = try F.editedRow(F.liveMarkets, outcomeID: 242143189,
                                   setting: ["observed_at": "2026-10-12T11:59:00+00:00"])
        let both = try card(F.liveDetail, body, admitted: F.liveAdmission.both, now: F.liveNow)
        XCTAssertEqual(both.outcomes[1].current, .unavailable(R.Words.inPlayUnavailable))
    }

    func testTheDefaultPickIsYesAndAHeldPickIsKept() throws {
        let live = try card(F.liveDetail, F.liveMarkets, admitted: F.liveAdmission.both, now: F.liveNow)
        XCTAssertEqual(live.selectedOutcomeID, "242143189")
        XCTAssertEqual(live.timing?.title, "Yes · \(B.Words.timingSuffix)")
        let held = try card(F.liveDetail, F.liveMarkets, admitted: F.liveAdmission.both, now: F.liveNow,
                            selected: "242143190")
        XCTAssertEqual(held.selectedOutcomeID, "242143190")
        XCTAssertEqual(held.timing?.outcomeID, "242143190")
    }

    func testDuringPlayEachTeamsGoalsAreObservedStateNotASettlement() throws {
        let both = try card(F.liveDetail, F.liveMarkets, admitted: F.liveAdmission.both, now: F.liveNow)
        XCTAssertEqual(both.scoring.title, B.Words.actualGoals)
        XCTAssertEqual(both.scoring.home.actual, .count(text: "4", status: B.Words.hasScored))
        XCTAssertEqual(both.scoring.away.actual, .count(text: "0", status: B.Words.yetToScore))
        XCTAssertEqual(both.scoring.clock,
                       "Observed \(SoccerMatchPageAdapter10868.timeWords("2026-10-12T12:54:19.676980+00:00".asDate!, host: F.propHost(F.liveNow).words))")
    }

    func testAfterTheFinalEachOutcomeKeepsItsOwnSettledResult() throws {
        let both = try card(F.finalDetail, F.finalMarkets, admitted: F.liveAdmission.both, now: F.finalNow)
        XCTAssertEqual(both.phase, .final)
        XCTAssertEqual(both.outcomes.map(\.result), [.won(OutcomeVerdict.won.label), .lost(OutcomeVerdict.lost.label)])
        // The retained final body serves no stored pin: said, not invented.
        XCTAssertTrue(both.outcomes.allSatisfy { $0.before == nil && $0.beforeMissing == R.Words.preMatchUnavailable })
        XCTAssertEqual(both.scoring.title, B.Words.finalGoals)
        XCTAssertEqual(both.scoring.home.actual, .count(text: "5", status: nil))
        XCTAssertEqual(both.timing?.lines, ["\(T.pregameTitle): \(R.Words.preMatchUnavailable)",
                                            "\(T.resultTitle): \(OutcomeVerdict.lost.label) · settled by Polymarket"])
    }

    func testBeforeKickoffTheChancesAreTheRecentQuotesAndNoGoalsAreShown() throws {
        let both = try card(F.hullDetail, F.hullMarkets, admitted: F.hullAdmission.both, now: F.hullNow)
        XCTAssertEqual(both.phase, .before)
        XCTAssertEqual(both.outcomes.map { $0.before?.probability }, [0.535, 0.465])
        XCTAssertEqual(both.selectedOutcomeID, "238847205")
        XCTAssertEqual(both.scoring.home.actual, .unavailable(B.Words.notStarted))
        XCTAssertEqual(both.scoring.away.actual, .unavailable(B.Words.notStarted))
        XCTAssertNil(both.scoring.clock)
    }

    func testNoAdmissionOrNoServedRowMakesNoCard() throws {
        XCTAssertNil(B.input(try F.detail(F.liveDetail), markets: try F.markets(F.liveMarkets), admitted: nil,
                             host: F.propHost(F.liveNow)))
        XCTAssertNil(B.input(try F.detail(F.liveDetail), markets: try F.markets(F.liveMarkets), admitted: 99_999_999,
                             host: F.propHost(F.liveNow)))
    }
}
