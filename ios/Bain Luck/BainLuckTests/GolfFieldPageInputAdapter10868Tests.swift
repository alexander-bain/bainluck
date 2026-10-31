import SwiftUI
import XCTest
@testable import Bain_Luck

/// #10868 — the golf tournament adapter, part five (the whole page input) and
/// the host glue's pure builder, on the retained bodies in
/// `GolfFieldRetainedBodies10868`. The page's own composition rules are read
/// through the accepted `GolfEventPageModel10868`, never re-implemented.
///
/// PREPARED, NOT RUN: written under a source-only hold (no build, no XCTest).
///
/// CONSTRUCTED here, and named where used: the reader's calendar and `now`, the
/// host's cohort, selection and join, an open copy of the resolved Winner body
/// (`status` only), a basketball copy (`llm_sport_category` only) and one India
/// price changed (`probability` on one row).
@MainActor
final class GolfFieldPageInputAdapter10868Tests: XCTestCase {
    private typealias P = GolfFieldPageInputAdapter10868
    private typealias Host = GolfFieldEventPageHost10868
    private typealias R = GolfFieldRetainedBodies10868

    private static let finalNow = "2026-10-12T23:55:18Z"
    private static let beforeNow = "2026-10-07T12:00:00Z"

    private func sources(_ winnerJSON: String, _ historyJSON: String?) throws -> P.Sources {
        P.Sources(winner: try R.market(winnerJSON), history: try historyJSON.map { try R.history($0) })
    }

    private func figure(_ reading: FieldHistoryReading10868) -> String? {
        switch reading {
        case .observation(_, let figure, _), .independent(let figure, _): return figure
        case .absent: return nil
        }
    }

    // MARK: - Phases

    func testTheFinalPageIsOneCoherentScreenForOneSelectedGolfer() throws {
        let input = P.input(try sources(R.baycurrentWinner, R.baycurrentHistory),
                            reading: P.Reading(cohort: [R.schauffele, R.clark, R.morikawa], selected: R.schauffele),
                            host: R.host(Self.finalNow))
        let model = GolfEventPageModel10868(input)
        XCTAssertEqual(input.phase, .final)
        XCTAssertNil(input.status, "no golf reading-hold owner, so no status and no Pause / Resume control")
        XCTAssertNil(input.movement, "no tied pre-tournament pair owner")
        XCTAssertNil(input.contenders, "before the start date only")
        XCTAssertEqual(model.stories, [.finish])
        XCTAssertEqual(model.finish?.phase, .final)
        XCTAssertEqual(input.copy.eyebrow, "Final")
        XCTAssertEqual(input.history.selection, .series(id: "datagolf:64266833:\(R.schauffele)",
                                                        missingWords: "No chance history for the selected golfer in this chart."))
        XCTAssertEqual(input.finish?.golferName, "Xander Schauffele")
        XCTAssertEqual(input.finish?.win.color, input.history.series[0].tint, "the finish bars wear the golfer's line colour")
        XCTAssertEqual(input.finish?.win.before?.text, figure(input.history.series[0].before),
                       "one golfer reads the same in the chart key and the Win slot")
        XCTAssertEqual(input.chooser?.selected?.ref.outcomeID, String(R.schauffele))
        XCTAssertNil(model.statusAction(canAct: true))
    }

    func testTheBeforePageAddsWhoStartsStrongestFromTheSameReadings() throws {
        // CONSTRUCTED: the Winner body opened (`status` only), read before the start.
        let input = P.input(try sources(R.edited(R.baycurrentWinner, ["status"], to: "open"), R.baycurrentHistory),
                            reading: P.Reading(cohort: [R.schauffele, R.clark], selected: R.clark),
                            host: R.host(Self.beforeNow))
        let model = GolfEventPageModel10868(input)
        XCTAssertEqual(input.phase, .before)
        XCTAssertEqual(model.stories, [.finish, .contenders])
        XCTAssertEqual(model.contenders?.phase, .before)
        XCTAssertNil(model.movement)
        XCTAssertEqual(input.history.caption, "Before the start date · last 7 days")
        XCTAssertEqual(input.finish?.phase, .before)
        XCTAssertEqual(input.finish?.win.before?.text, figure(input.history.series[1].before))
        let bars = FieldOutlookModel10868(try XCTUnwrap(input.contenders)).bars
        XCTAssertEqual(bars.map(\.chance.fraction), [0.086583, 0.053967])
    }

    func testWithoutASelectionTheFinishCardSaysToChooseAGolfer() throws {
        let src = try sources(R.baycurrentWinner, R.baycurrentHistory)
        let none = P.input(src, reading: P.Reading(cohort: [R.schauffele]), host: R.host(Self.finalNow))
        XCTAssertNil(none.finish)
        XCTAssertEqual(none.copy.finishUnavailable, "Choose a golfer to see their finish chances.")
        XCTAssertEqual(none.history.selection, .none)

        let unknown = P.input(src, reading: P.Reading(cohort: [R.schauffele], selected: 1), host: R.host(Self.finalNow))
        XCTAssertNil(unknown.finish, "not a Winner outcome: nothing is borrowed")
        XCTAssertEqual(unknown.copy.finishUnavailable, "Finish chances unavailable for this golfer.")
    }

    func testAMissingHistoryLeavesTheRestOfThePageInPlace() throws {
        let input = P.input(try sources(R.baycurrentWinner, nil),
                            reading: P.Reading(cohort: [R.schauffele], selected: R.schauffele),
                            host: R.host(Self.finalNow))
        XCTAssertEqual(input.history.plotAbsence?.title, "History unavailable")
        XCTAssertNotNil(input.finish, "the finish card composes from the market alone")
        XCTAssertEqual(input.finish?.win.beforeMissing, "Before-start chance not recorded")
        XCTAssertNotNil(input.chooser)
        XCTAssertEqual(input.copy.title, "Baycurrent Classic - Winner")
    }

    func testWithoutAChooserNoControlOffersOne() throws {
        let input = P.input(try sources(R.baycurrentWinner, R.baycurrentHistory),
                            reading: P.Reading(cohort: [R.schauffele]), chooserAvailable: false,
                            host: R.host(Self.finalNow))
        XCTAssertNil(input.chooser)
        XCTAssertNil(input.history.moreOriginals)
    }

    func testTheIndiaFiveMarketsComposeAFiveFinishOutlookBeforeTheStart() throws {
        let legs = GolfFieldFinishAdapter10868.Legs(
            top5: .init(market: try R.market(R.indiaTop5), outcomes: [R.rory: 246352498]),
            top10: .init(market: try R.market(R.indiaTop10), outcomes: [R.rory: 246352556]),
            top20: .init(market: try R.market(R.indiaTop20), outcomes: [R.rory: 246352614]),
            makeCut: .init(market: try R.market(R.indiaMakeCut), outcomes: [R.rory: 246352672]))
        let input = P.input(P.Sources(winner: try R.market(R.indiaWin), history: nil, legs: legs),
                            reading: P.Reading(cohort: [R.rory, R.noren], selected: R.rory),
                            host: R.host("2026-10-12T23:28:52Z"))
        XCTAssertEqual(input.phase, .before)
        XCTAssertEqual(input.finish?.slots.map { $0.before?.text }, ["13%", "35%", "50%", "67%", "90%"])
        let model = GolfEventPageModel10868(input)
        XCTAssertEqual(model.stories, [.finish, .contenders])
        XCTAssertEqual(FieldOutlookModel10868(try XCTUnwrap(input.contenders)).bars.map(\.chance),
                       [.value(probability: 0.1271, fraction: 0.1271), .unavailable],
                       "Noren's missing price draws no bar, never his opening")
    }

    // MARK: - Host glue

    func testTheHostRoutesOnlyTheControlsItCanServe() {
        XCTAssertEqual(Host.route(GolfFieldHistoryAdapter10868.expandActionID), .expand)
        XCTAssertEqual(Host.route(GolfFieldHistoryAdapter10868.chooserActionID), .chooser)
        XCTAssertEqual(Host.route("golf.history.choose.242242520"), .choose(R.schauffele))
        XCTAssertEqual(Host.route(GolfFieldHistoryAdapter10868.detailsActionID), .none, "offered unavailable")
        XCTAssertEqual(Host.route("golf.history.choose.x"), .none)
        XCTAssertEqual(Host.route(GolfFieldHistoryAdapter10868.scaleActionID), .scale)
        XCTAssertEqual(Host.chartGolfers([R.clark], selected: R.schauffele), [R.clark, R.schauffele])
        XCTAssertEqual(Host.chartGolfers([R.clark, R.schauffele], selected: R.schauffele), [R.clark, R.schauffele])
        XCTAssertEqual(Host.chartGolfers([R.clark], selected: nil), [R.clark])
    }

    func testTheHostBuildKeepsTheSelectedGolferInViewAndIsTheAdaptersOwnOutput() throws {
        let winner = try R.market(R.baycurrentWinner)
        let history = try R.history(R.baycurrentHistory)
        let now = Self.finalNow.asDate!
        let built = Host.build(winner: winner, history: history, cohort: [R.clark],
                               choice: Host.Choice(selected: R.schauffele), now: now,
                               calendar: R.pacific, locale: Locale(identifier: "en_US"))
        let direct = P.input(P.Sources(winner: winner, history: history),
                             reading: P.Reading(cohort: [R.clark, R.schauffele], selected: R.schauffele),
                             host: R.host(Self.finalNow))
        XCTAssertEqual(built, direct)
        XCTAssertEqual(built.history.series.map(\.name), ["Wyndham Clark", "Xander Schauffele"])
        XCTAssertTrue(Host.applies(winner))
        // CONSTRUCTED: `llm_sport_category` "basketball" (one key).
        XCTAssertFalse(Host.applies(try R.market(R.edited(R.baycurrentWinner, ["llm_sport_category"], to: "basketball"))))
    }

    func testOneChangedPriceReachesTheBuiltInputOnTheNextPass() throws {
        let now = "2026-10-12T23:28:52Z".asDate!
        let first = Host.build(winner: try R.market(R.indiaWin), history: nil, cohort: [R.rory],
                               choice: Host.Choice(selected: R.rory), now: now,
                               calendar: R.pacific, locale: Locale(identifier: "en_US"))
        // CONSTRUCTED: Rory's Winner price changed to 0.2 (one key), same stamp.
        let changed = try R.market(R.edited(R.indiaWin, ["outcomes", 0, "probability"], to: 0.2))
        let second = Host.build(winner: changed, history: nil, cohort: [R.rory],
                                choice: Host.Choice(selected: R.rory), now: now,
                                calendar: R.pacific, locale: Locale(identifier: "en_US"))
        XCTAssertEqual(first.finish?.win.before?.text, "13%")
        XCTAssertEqual(second.finish?.win.before?.text, "20%", "no memo holds the old price")
        XCTAssertNotEqual(first, second)
    }

    func testTheReadersFullScaleChoiceReachesTheHistoryAndChangesNothingElse() throws {
        let winner = try R.market(R.baycurrentWinner)
        let history = try R.history(R.baycurrentHistory)
        let now = Self.finalNow.asDate!
        let build: (Bool) -> GolfEventPageInput10868 = { full in
            Host.build(winner: winner, history: history, cohort: [R.clark],
                       choice: Host.Choice(selected: R.schauffele, fullScale: full), now: now,
                       calendar: R.pacific, locale: Locale(identifier: "en_US"))
        }
        let auto = build(false)
        let full = build(true)
        // Schauffele's highest drawn final-frame reading is 0.095147; ×1.04 = 0.0990 → the 10% rung.
        XCTAssertEqual(auto.history.ceiling, 0.1)
        XCTAssertEqual(auto.history.scale?.label, "Auto scale · 0–10%")
        XCTAssertEqual(full.history.ceiling, 1)
        XCTAssertEqual(full.history.scale?.label, "Full scale · 0–100%")
        XCTAssertEqual(auto.history.series, full.history.series)
        XCTAssertEqual(auto.finish, full.finish, "the scale is the chart's only")
        // One flag in, one page out: the page and the full-size reader draw this same input, so the choice
        // holds across the reader and across a refresh that rebuilds with it.
        XCTAssertEqual(build(true), full)
    }
}
