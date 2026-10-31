import XCTest
@testable import Bain_Luck

/// #10868 — the first-team-to-score story, part six, on the RETAINED REAL
/// bodies (`SoccerRetained10868`) and the CONSTRUCTED owner admission.
///
/// PREPARED, NOT RUN: written under a source-only hold (no build, no XCTest).
@MainActor
final class SoccerFirstTeamAdapter10868Tests: XCTestCase {
    private typealias F = SoccerRetained10868
    private typealias T = SoccerFirstTeamAdapter10868
    private typealias R = SoccerPropReadingAdapter10868

    private func card(_ detail: String, _ markets: String, history: String?, admitted: Int?,
                      now: Date) throws -> FirstScorerComparisonInput10868 {
        try XCTUnwrap(T.input(try F.detail(detail), markets: try F.markets(markets),
                              history: try history.map { try F.history($0) },
                              admitted: admitted, host: F.propHost(now)))
    }

    func testDuringPlayEveryServedOutcomeIsARowNamedAsServedIncludingNeither() throws {
        let first = try card(F.liveDetail, F.liveMarkets, history: F.liveHistory,
                             admitted: F.liveAdmission.first, now: F.liveNow)
        XCTAssertEqual(first.phase, .during)
        XCTAssertEqual(first.title, T.Words.title)
        XCTAssertEqual(first.context, "Polymarket")
        XCTAssertEqual(first.overview.map(\.id), ["244237963", "244237965", "244237964"])
        XCTAssertEqual(first.overview.map(\.name), ["Real Valladolid CF", "Neither", "Albacete Balompié"])
        XCTAssertTrue(first.overview.allSatisfy { $0.team == nil })
        XCTAssertNil(first.confirmed)
        XCTAssertEqual(first.outcome, T.outcomeWords)
    }

    func testDuringPlayTheRecentQuotesAreCurrentAndTheOldOneIsStale() throws {
        let first = try card(F.liveDetail, F.liveMarkets, history: F.liveHistory,
                             admitted: F.liveAdmission.first, now: F.liveNow)
        guard case .recorded(let valladolid) = first.overview[0].current,
              case .recorded(let neither) = first.overview[1].current else {
            return XCTFail("both quotes observed 12:54:07 are own-clocked and recent")
        }
        XCTAssertEqual(valladolid.probability, 0.999)
        XCTAssertEqual(valladolid.text, formatProbability(0.999))
        XCTAssertEqual(neither.text, formatProbability(0.0005))
        // Albacete's 12:25:47 quote is just over 30 minutes old.
        XCTAssertEqual(first.overview[2].current, .stale(R.Words.noRecentUpdate))
        // Stored pins, not the current quotes.
        XCTAssertEqual(first.overview.map { $0.pregame?.probability }, [0.57, 0.065, 0.335])
    }

    func testDuringPlayTheScoreCheckpointsAreObservationTimesInServedOrder() throws {
        let first = try card(F.liveDetail, F.liveMarkets, history: F.liveHistory,
                             admitted: F.liveAdmission.first, now: F.liveNow)
        let path = try XCTUnwrap(first.scorePath)
        XCTAssertEqual(path.title, T.Words.checkpointsTitle)
        XCTAssertEqual(path.note, T.Words.checkpointsNote)
        XCTAssertEqual(path.observations.map(\.score), ["0–0", "1–0", "2–0", "3–0", "4–0"])
        XCTAssertEqual(path.observations.first?.id, "2026-10-12T12:02:45.588824+00:00")
        XCTAssertEqual(path.observations.first?.time,
                       SoccerMatchPageAdapter10868.timeWords("2026-10-12T12:02:45.588824+00:00".asDate!,
                                                            host: F.propHost(F.liveNow).words))
    }

    /// Without a history response the card keeps its outcomes and drops only
    /// the checkpoints.
    func testWithNoHistoryTheCheckpointsAreAbsentAndTheRowsStay() throws {
        let first = try card(F.liveDetail, F.liveMarkets, history: nil,
                             admitted: F.liveAdmission.first, now: F.liveNow)
        XCTAssertNil(first.scorePath)
        XCTAssertEqual(first.overview.count, 3)
    }

    func testAfterTheFinalEachOutcomeKeepsItsOwnResultAndNoCheckpointsAreShown() throws {
        let first = try card(F.finalDetail, F.finalMarkets, history: F.finalHistory,
                             admitted: F.liveAdmission.first, now: F.finalNow)
        XCTAssertEqual(first.phase, .final)
        XCTAssertEqual(first.overview.map(\.result),
                       [.won(OutcomeVerdict.won.label), .lost(OutcomeVerdict.lost.label), .lost(OutcomeVerdict.lost.label)])
        XCTAssertNil(first.scorePath)
        XCTAssertEqual(first.timing?.lines, ["\(T.outcomeWords.pregameTitle): \(R.Words.preMatchNotRecorded)",
                                             "\(T.outcomeWords.finalResultTitle): \(OutcomeVerdict.won.label)"])
    }

    func testBeforeKickoffOldQuotesAreNotPreMatchChances() throws {
        let first = try card(F.hullDetail, F.hullMarkets, history: F.hullHistory,
                             admitted: F.hullAdmission.first, now: F.hullNow)
        XCTAssertEqual(first.phase, .before)
        XCTAssertEqual(first.overview.map(\.name), ["Everton FC", "Hull City AFC", "Neither"])
        XCTAssertTrue(first.overview.allSatisfy { $0.pregame == nil && $0.pregameMissing == R.Words.noRecentUpdate })
        XCTAssertNil(first.scorePath)
    }

    func testNoAdmissionMakesNoCard() throws {
        XCTAssertNil(T.input(try F.detail(F.liveDetail), markets: try F.markets(F.liveMarkets),
                             history: nil, admitted: nil, host: F.propHost(F.liveNow)))
    }
}
