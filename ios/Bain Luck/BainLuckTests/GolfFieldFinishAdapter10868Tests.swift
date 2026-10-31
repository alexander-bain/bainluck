import SwiftUI
import XCTest
@testable import Bain_Luck

/// #10868 — the golf tournament adapter, part three (the selected golfer's
/// finish outlook), on the retained India five-market capture and the resolved
/// Baycurrent Classic Winner market in `GolfFieldRetainedBodies10868`.
///
/// PREPARED, NOT RUN: written under a source-only hold (no build, no XCTest).
///
/// CONSTRUCTED here, and named where used: the reader's calendar and `now`;
/// THE HOST'S JOIN from each Winner outcome to its Top 5 / Top 10 / Top 20 /
/// Make the Cut outcome (no production owner serves it — the ids are the ones
/// the retained markets serve for that golfer, the same ids Design's retained
/// five-finish packet carries); India read after its listed start; and one or
/// two grade keys on a Baycurrent row.
@MainActor
final class GolfFieldFinishAdapter10868Tests: XCTestCase {
    private typealias F = GolfFieldFinishAdapter10868
    private typealias H = GolfFieldHistoryAdapter10868
    private typealias A = GolfFieldPageAdapter10868
    private typealias R = GolfFieldRetainedBodies10868

    private static let indiaNow = "2026-10-12T23:28:52Z"

    /// CONSTRUCTED host join: Winner outcome id → that market's outcome id.
    private static let top5Join = [R.rory: 246352498, R.sharma: 246352530, R.noren: 245904764]
    private static let top10Join = [R.rory: 246352556, R.sharma: 246352588, R.noren: 245904896]
    private static let top20Join = [R.rory: 246352614, R.sharma: 246352646, R.noren: 245905028]
    private static let makeCutJoin = [R.rory: 246352672, R.sharma: 246352704, R.noren: 245905160]

    private func indiaLegs() throws -> F.Legs {
        F.Legs(top5: F.Leg(market: try R.market(R.indiaTop5), outcomes: Self.top5Join),
               top10: F.Leg(market: try R.market(R.indiaTop10), outcomes: Self.top10Join),
               top20: F.Leg(market: try R.market(R.indiaTop20), outcomes: Self.top20Join),
               makeCut: F.Leg(market: try R.market(R.indiaMakeCut), outcomes: Self.makeCutJoin))
    }

    private func field(_ winnerJSON: String, _ historyJSON: String?, now: String) throws -> H.Field {
        let winner = try R.market(winnerJSON)
        let history = try historyJSON.map { try R.history($0) }
        return GolfFieldPageInputAdapter10868.field(.init(winner: winner, history: history), now: now.asDate!)
    }

    private func updated(_ stamp: String, _ host: A.Host) -> String {
        "Updated \(A.clockWords(stamp.asDate!, host: host)) · DataGolf"
    }

    // MARK: - Before the start

    func testRorysFiveFinishesAreEachTheirOwnPriceAndClock() throws {
        let host = R.host(Self.indiaNow)
        let winner = try field(R.indiaWin, nil, now: Self.indiaNow)
        let input = try XCTUnwrap(F.finish(winner, golfer: R.rory, legs: try indiaLegs(), tint: .blue,
                                           selectedFinish: "ignored", host: host))
        XCTAssertEqual(input.phase, .before)
        XCTAssertEqual(input.slots.map(\.name), ["Win", "Top 5", "Top 10", "Top 20", "Make cut"])
        XCTAssertEqual(input.slots.map(\.selection), [
            "datagolf|65391342|246352440", "datagolf|65391343|246352498", "datagolf|65391344|246352556",
            "datagolf|65391345|246352614", "datagolf|65391346|246352672",
        ])
        XCTAssertEqual(input.slots.map { $0.before?.probability }, [0.1271, 0.351696, 0.498592, 0.665303, 0.896383])
        XCTAssertEqual(input.slots.map { $0.before?.text }, ["13%", "35%", "50%", "67%", "90%"])
        XCTAssertEqual(input.slots.map { $0.before?.accessibilityDetail }, [
            updated("2026-10-12T23:11:05.501054+00:00", host), updated("2026-10-12T23:11:06.747890+00:00", host),
            updated("2026-10-12T23:11:07.952964+00:00", host), updated("2026-10-12T23:11:09.073291+00:00", host),
            updated("2026-10-12T23:11:10.724619+00:00", host),
        ], "each finish keeps its own stamp")
        XCTAssertTrue(input.slots.allSatisfy { $0.recorded == nil }, "nothing is recorded before the start")
        XCTAssertEqual(input.golferName, "Rory McIlroy")
        XCTAssertEqual(input.title, "Finish outlook")
        XCTAssertEqual(input.context, "Before the start date · each chance keeps its own time")
        XCTAssertNil(input.actualSummary, "no confirmed finishing position source")
        XCTAssertNil(input.selected, "a selection is read only while recorded")
        XCTAssertEqual(input.layout, .bars)
    }

    func testAMissingPriceStaysNotRecordedAndNeverBorrowsTheUntimedOpening() throws {
        let host = R.host(Self.indiaNow)
        let winner = try field(R.indiaWin, nil, now: Self.indiaNow)
        let input = try XCTUnwrap(F.finish(winner, golfer: R.noren, legs: try indiaLegs(), tint: .blue,
                                           selectedFinish: nil, host: host))
        XCTAssertTrue(input.slots.allSatisfy { $0.before == nil }, "served with no price in every market")
        XCTAssertEqual(Set(input.slots.map(\.beforeMissing)), ["Before-start chance not recorded"])
        XCTAssertEqual(input.layout, .missingEstimates)
        XCTAssertEqual(input.slots.count, 5)
    }

    func testRealZeroAndTinyPricesStayValues() throws {
        let host = R.host(Self.indiaNow)
        let winner = try field(R.indiaWin, nil, now: Self.indiaNow)
        let jaglan = try XCTUnwrap(F.finish(winner, golfer: R.jaglan, legs: try indiaLegs(), tint: .blue,
                                            selectedFinish: nil, host: host))
        XCTAssertEqual(jaglan.win.before?.probability, 0, "a real zero is plotted")
        XCTAssertEqual(jaglan.win.before?.text, formatProbability(0))
        XCTAssertEqual(jaglan.top5.beforeMissing, "Top 5 chance unavailable", "the host's join names no Top 5 outcome for him")

        let sharma = try XCTUnwrap(F.finish(winner, golfer: R.sharma, legs: try indiaLegs(), tint: .blue,
                                            selectedFinish: nil, host: host))
        XCTAssertEqual(sharma.win.before?.text, "<1%")
        XCTAssertEqual(sharma.makeCut?.before?.text, "35%")
    }

    func testAMissingFinishMarketIsThatFinishsOwnAbsenceAndNoFifthSlotIsInvented() throws {
        let host = R.host(Self.indiaNow)
        let winner = try field(R.indiaWin, nil, now: Self.indiaNow)
        let legs = F.Legs(top5: F.Leg(market: try R.market(R.indiaTop5), outcomes: [:]))
        let input = try XCTUnwrap(F.finish(winner, golfer: R.rory, legs: legs, tint: .blue, selectedFinish: nil, host: host))
        XCTAssertEqual(input.win.before?.text, "13%")
        XCTAssertNil(input.top5.before)
        XCTAssertEqual(input.top5.beforeMissing, "Top 5 chance unavailable")
        XCTAssertEqual(input.top10.beforeMissing, "Top 10 chance unavailable")
        XCTAssertEqual(input.top20.selection, "golf.finish.top20.unavailable")
        XCTAssertNil(input.makeCut, "no Make the Cut market held: exactly the original four")
        XCTAssertEqual(input.slots.count, 4)
        XCTAssertEqual(Set(input.slots.map(\.selection)).count, 4, "selection ids stay unique")
    }

    func testTheGolferMustBeExactlyOneWinnerOutcome() throws {
        let host = R.host(Self.indiaNow)
        let winner = try field(R.indiaWin, nil, now: Self.indiaNow)
        XCTAssertNil(F.finish(winner, golfer: 1, legs: try indiaLegs(), tint: .blue, selectedFinish: nil, host: host))
    }

    // MARK: - During play

    func testDuringPlayAPreStartPriceIsNeverTheRecordedEstimate() throws {
        // CONSTRUCTED: India read at 2026-10-15T06:00Z, after its listed start.
        let host = R.host("2026-10-15T06:00:00Z")
        let winner = try field(R.indiaWin, nil, now: "2026-10-15T06:00:00Z")
        let input = try XCTUnwrap(F.finish(winner, golfer: R.rory, legs: try indiaLegs(), tint: .blue,
                                           selectedFinish: "datagolf|65391343|246352498", host: host))
        XCTAssertEqual(input.phase, .recorded)
        XCTAssertEqual(input.slots.map { $0.before?.text }, ["13%", "35%", "50%", "67%", "90%"],
                       "stamped before the start: the before reading")
        XCTAssertTrue(input.slots.allSatisfy { $0.recorded == nil }, "a pre-start quote is never the recorded estimate")
        XCTAssertEqual(Set(input.slots.map(\.recordedMissing)), ["Chance since the start not recorded"])
        XCTAssertEqual(input.selected, "datagolf|65391343|246352498")
        XCTAssertEqual(input.selectedSlot?.name, "Top 5")
        XCTAssertEqual(input.context, "Since the start date · each chance keeps its own time")
    }

    // MARK: - Final

    func testAtTheFinalEachResultIsItsMarketsOwnGradeNeverTheLine() throws {
        let host = R.host("2026-10-12T23:56:42Z")
        let winner = try field(R.baycurrentWinner, R.brennanHistory, now: "2026-10-12T23:56:42Z")
        let input = try XCTUnwrap(F.finish(winner, golfer: R.brennan, legs: F.Legs(), tint: .blue,
                                           selectedFinish: "datagolf|64266833|241857512", host: host))
        XCTAssertEqual(input.phase, .final)
        XCTAssertEqual(input.win.before?.probability, 0.026017)
        XCTAssertEqual(input.win.before?.text, "3%")
        XCTAssertEqual(input.win.before?.accessibilityDetail,
                       "Recorded \(A.clockWords("2026-10-06T13:08:40.644152+00:00".asDate!, host: host)) · DataGolf")
        // He won and his line reached 1.0, but the resolved market carries no grade.
        XCTAssertEqual(input.win.actual, GolfFinishResult10868(text: "Result unavailable", mark: .unknown))
        XCTAssertEqual(input.top5.actual.mark, .unknown, "no Top 5 market held")
        XCTAssertNil(input.selected, "no selection at the final")
        XCTAssertEqual(input.context, "Final · each result comes from its own market")
        XCTAssertEqual(input.layout, .bars)

        // CONSTRUCTED: Brennan's row graded won (`is_winner` + `resolution_source`).
        var won = try R.edited(R.baycurrentWinner, ["outcomes", 3, "is_winner"], to: true)
        won = try R.edited(won, ["outcomes", 3, "resolution_source"], to: "datagolf_settlement")
        let graded = try field(won, R.brennanHistory, now: "2026-10-12T23:56:42Z")
        let gradedInput = try XCTUnwrap(F.finish(graded, golfer: R.brennan, legs: F.Legs(), tint: .blue,
                                                 selectedFinish: nil, host: host))
        XCTAssertEqual(gradedInput.win.actual, GolfFinishResult10868(text: "Won", mark: .success))
        XCTAssertEqual(gradedInput.win.before, input.win.before, "a grade never replaces the before reading")

        // CONSTRUCTED: Schauffele's row graded lost (the same two keys).
        var lost = try R.edited(R.baycurrentWinner, ["outcomes", 0, "is_winner"], to: false)
        lost = try R.edited(lost, ["outcomes", 0, "resolution_source"], to: "datagolf_settlement")
        let lostField = try field(lost, R.baycurrentHistory, now: "2026-10-12T23:55:18Z")
        let lostInput = try XCTUnwrap(F.finish(lostField, golfer: R.schauffele, legs: F.Legs(), tint: .blue,
                                               selectedFinish: nil, host: host))
        XCTAssertEqual(lostInput.win.actual, GolfFinishResult10868(text: "Lost", mark: .failure))
    }
}
