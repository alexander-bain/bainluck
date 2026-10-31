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

    /// "In-play chance unavailable · 99.9% recorded Oct 12, 5:54 AM · Polymarket".
    private func datedQuote(_ value: Double, _ stamp: String) -> PeriodOutcomeCurrent10868 {
        let clock = SoccerMatchPageAdapter10868.clockWords(stamp.asDate!, host: F.propHost(F.liveNow).words)
        return .stale("In-play chance unavailable · \(formatProbability(value)) recorded \(clock) · Polymarket")
    }

    /// Every cell's dated recorded quote in the retained live body, by series
    /// (home, Draw, away) and period (first, second), as served.
    private var retainedLiveQuotes: [[PeriodOutcomeCurrent10868]] {
        let firstHalf = "2026-10-12T12:54:07.360375+00:00"
        return [
            [datedQuote(0.999, firstHalf), datedQuote(0.3881, "2026-10-12T12:37:13.705918+00:00")],
            [datedQuote(0.0005, firstHalf), datedQuote(0.3483, "2026-10-12T12:36:27.513868+00:00")],
            [datedQuote(0.0005, firstHalf), datedQuote(0.2637, "2026-10-12T12:36:47.821894+00:00")],
        ]
    }

    /// Design, wave-1 review: a half's recent price alone must not read as a
    /// current chance. The REAL first-half home row (63178219 / 242338171) still
    /// quotes 99.9% at 12:54:07, after the half; the second-half rows were
    /// quoted at 12:36–12:37. No decoded field proves either half is in play, so
    /// every cell keeps only its own dated recorded quote, and no result is
    /// inferred.
    func testDuringPlayNoHalfQuoteIsTheCurrentChanceEachIsADatedRecordedQuote() throws {
        let (halves, event) = try card(F.liveDetail, F.liveMarkets, admitted: F.liveAdmission.halves, now: F.liveNow)
        let names = SoccerMatchPageAdapter10868.names(event)

        XCTAssertEqual(halves.series.map { $0.cells.map { $0.pregame?.probability } },
                       [[0.375, 0.43], [0.425, 0.38], [0.205, 0.23]])
        XCTAssertTrue(halves.series.allSatisfy { $0.cells.allSatisfy { recorded($0) == nil } })
        XCTAssertEqual(halves.series.map { $0.cells.map(\.current) }, retainedLiveQuotes)
        let unknown = PeriodOutcomeResult10868.unconfirmed(R.Words.resultUnavailable)
        XCTAssertTrue(halves.series.allSatisfy { $0.cells.allSatisfy { $0.result == unknown } })
        XCTAssertEqual(halves.selectedSeriesID, "home")
        XCTAssertEqual(halves.resultsTitle, "\(H.Words.liveResults) · \(names.home)")
    }

    /// CONSTRUCTED: the live body with the three first-half result rows carrying
    /// the grades the final body serves for the same outcome ids. During play a
    /// graded half shows its grade and no chance; the second half lends nothing
    /// and borrows nothing.
    func testDuringPlayAGradedHalfShowsItsGradeAndTheOtherHalfStaysUnknown() throws {
        let body = try F.graded(F.liveMarkets, [242338171: true, 242338170: false, 242338172: false])
        let (halves, _) = try card(F.liveDetail, body, admitted: F.liveAdmission.halves, now: F.liveNow)
        let won = PeriodOutcomeResult10868.won(OutcomeVerdict.won.label)
        let lost = PeriodOutcomeResult10868.lost(OutcomeVerdict.lost.label)
        let unknown = PeriodOutcomeResult10868.unconfirmed(R.Words.resultUnavailable)

        XCTAssertEqual(halves.series.map { $0.cells.map(\.result) }, [[won, unknown], [lost, unknown], [lost, unknown]])
        XCTAssertTrue(halves.series.allSatisfy { $0.cells[0].current == .unavailable(R.Words.settledNoChance) })
        XCTAssertEqual(halves.series.map { $0.cells[1].current }, retainedLiveQuotes.map { $0[1] })
    }

    /// CONSTRUCTED `now`: forty minutes later every quote is stale. Still none is
    /// current, and each keeps its own served date.
    func testAStaleHalfQuoteIsStillOnlyADatedRecordedQuote() throws {
        let (halves, _) = try card(F.liveDetail, F.liveMarkets, admitted: F.liveAdmission.halves, now: F.liveLaterNow)
        XCTAssertEqual(halves.series.map { $0.cells.map(\.current) }, retainedLiveQuotes)
    }

    /// CONSTRUCTED: the first-half home row with only its `probability` set to
    /// null. That cell has no quote to keep; its neighbours keep theirs.
    func testAHalfWithNoPriceSaysTheInPlayChanceIsUnavailable() throws {
        let body = try F.editedRow(F.liveMarkets, outcomeID: 242338171, setting: ["probability": NSNull()])
        let (halves, _) = try card(F.liveDetail, body, admitted: F.liveAdmission.halves, now: F.liveNow)
        XCTAssertEqual(halves.series[0].cells[0].current, .unavailable(R.Words.inPlayUnavailable))
        XCTAssertEqual(halves.series[0].cells[1].current, retainedLiveQuotes[0][1])
        XCTAssertEqual(halves.series[1].cells[0].current, retainedLiveQuotes[1][0])
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
