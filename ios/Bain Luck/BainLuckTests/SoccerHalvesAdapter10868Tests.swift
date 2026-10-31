import XCTest
@testable import Bain_Luck

/// #10868 — the half-by-half story, part seven, on the RETAINED REAL bodies
/// (`SoccerRetained10868`) and the CONSTRUCTED owner admission of the two
/// half-result markets and their period identities.
///
/// PREPARED, NOT RUN: written under a source-only hold (no build, no XCTest).
@MainActor
final class SoccerHalvesAdapter10868Tests: XCTestCase {
    private typealias F = SoccerRetained10868
    private typealias H = SoccerHalvesAdapter10868
    private typealias R = SoccerPropReadingAdapter10868

    private func card(_ detail: String, _ markets: String, admitted: [R.Markets.Half],
                      now: Date) throws -> (PeriodOutcomeComparisonInput10868, EventDetail) {
        let event = try F.detail(detail)
        let input = try XCTUnwrap(H.input(event, markets: try F.markets(markets), admitted: admitted,
                                          host: F.propHost(now)))
        return (input, event)
    }

    private func recorded(_ cell: PeriodOutcomeCell10868) -> Double? {
        if case .recorded(let o) = cell.current { return o.probability }
        return nil
    }

    func testSeriesFollowTheServerProvedSideAndEachHalfKeepsItsOwnCell() throws {
        let (halves, event) = try card(F.liveDetail, F.liveMarkets, admitted: F.liveAdmission.halves, now: F.liveNow)
        let names = SoccerMatchPageAdapter10868.names(event)

        XCTAssertEqual(halves.phase, .during)
        XCTAssertEqual(halves.periods, [PeriodOutcomePeriod10868(id: "first", label: "First half"),
                                        PeriodOutcomePeriod10868(id: "second", label: "Second half")])
        XCTAssertEqual(halves.series.map(\.id), ["home", "draw", "away"])
        XCTAssertEqual(halves.series.map(\.label), [names.home, H.Words.draw, names.away])
        XCTAssertEqual(halves.series[0].cells.map(\.id), ["63178219:242338171", "63178218:246041831"])
        XCTAssertEqual(halves.series[1].cells.map(\.id), ["63178219:242338170", "63178218:245875499"])
        XCTAssertEqual(halves.series[2].cells.map(\.id), ["63178219:242338172", "63178218:245681743"])
        XCTAssertTrue(halves.series.allSatisfy { $0.cells.map(\.periodID) == ["first", "second"] })
    }

    func testDuringPlayEachCellHasItsOwnPinAndItsOwnCurrentChance() throws {
        let (halves, event) = try card(F.liveDetail, F.liveMarkets, admitted: F.liveAdmission.halves, now: F.liveNow)
        let names = SoccerMatchPageAdapter10868.names(event)

        XCTAssertEqual(halves.series.map { $0.cells.map { $0.pregame?.probability } },
                       [[0.375, 0.43], [0.425, 0.38], [0.205, 0.23]])
        XCTAssertEqual(halves.series.map { $0.cells.map(recorded) },
                       [[0.999, 0.3881], [0.0005, 0.3483], [0.0005, 0.2637]])
        XCTAssertEqual(halves.selectedSeriesID, "home")
        XCTAssertEqual(halves.resultsTitle, "\(H.Words.liveResults) · \(names.home)")
    }

    func testAfterTheFinalEachHalfKeepsItsOwnSettledResult() throws {
        let (halves, event) = try card(F.finalDetail, F.finalMarkets, admitted: F.liveAdmission.halves, now: F.finalNow)
        let names = SoccerMatchPageAdapter10868.names(event)
        let won = PeriodOutcomeResult10868.won(OutcomeVerdict.won.label)
        let lost = PeriodOutcomeResult10868.lost(OutcomeVerdict.lost.label)

        XCTAssertEqual(halves.phase, .final)
        XCTAssertEqual(halves.series.map { $0.cells.map(\.result) }, [[won, won], [lost, lost], [lost, lost]])
        // The final body's second-half Draw serves no price at all; its result
        // is still the venue's own grade.
        XCTAssertEqual(halves.series[1].cells[1].result, lost)
        XCTAssertTrue(halves.series.allSatisfy { $0.cells.allSatisfy { $0.pregameMissing == R.Words.preMatchNotRecorded } })
        XCTAssertEqual(halves.resultsTitle, "\(H.Words.finalResults) · \(names.home)")
    }

    func testBeforeKickoffOldQuotesAreNotPreMatchChancesAndThereIsNoResultsRow() throws {
        let (halves, _) = try card(F.hullDetail, F.hullMarkets, admitted: F.hullAdmission.halves, now: F.hullNow)
        XCTAssertEqual(halves.phase, .before)
        XCTAssertEqual(halves.series.map(\.id), ["home", "draw", "away"])
        XCTAssertTrue(halves.series.allSatisfy {
            $0.cells.allSatisfy { $0.pregame == nil && $0.pregameMissing == R.Words.noRecentUpdate }
        })
        XCTAssertNil(halves.resultsTitle)
    }

    /// CONSTRUCTED admission: the full-match three-way market (63178228). Its
    /// options are served with side `category` — no proved home/draw/away — so
    /// no series is made from them and there is no card.
    func testAMarketWithNoProvedSidesMakesNoSeries() throws {
        let event = try F.detail(F.liveDetail)
        XCTAssertNil(H.input(event, markets: try F.markets(F.liveMarkets),
                             admitted: [.init(marketID: 63178228, periodID: "match", label: "Match")],
                             host: F.propHost(F.liveNow)))
        XCTAssertNil(H.input(event, markets: try F.markets(F.liveMarkets), admitted: [], host: F.propHost(F.liveNow)))
    }
}
