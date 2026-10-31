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
        XCTAssertTrue(both.outcomes.allSatisfy { $0.before == nil && $0.beforeMissing == R.Words.preMatchNotRecorded })
        XCTAssertEqual(both.scoring.title, B.Words.finalGoals)
        XCTAssertEqual(both.scoring.home.actual, .count(text: "5", status: nil))
        XCTAssertEqual(both.timing?.lines, ["\(T.pregameTitle): \(R.Words.preMatchNotRecorded)",
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
