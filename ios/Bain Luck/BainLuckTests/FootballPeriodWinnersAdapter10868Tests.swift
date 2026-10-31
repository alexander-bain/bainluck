import SwiftUI
import XCTest
@testable import Bain_Luck

/// #10868 — the restored final period-winner story (the approved
/// `FinalQuarterOutlooks` card on the completed `nfl-live` page), on RETAINED
/// REAL bodies: the completed Eagles–Jaguars detail (its own stored line score,
/// `box_score_data` 7·0·3·9 / 0·14·0·3) and `/game-markets`, whose reduced
/// verbatim subset now keeps all twelve quarter-winner period rows (sources,
/// sha256 and kept indexes in `FootballRetained10868`).
///
/// PREPARED, NOT RUN: written under a source-only hold (no build, no XCTest).
///
/// The owner binding (`FootballRetained10868.quarterBinding`) is CONSTRUCTED —
/// no production owner supplies one yet — from retained provider evidence:
/// side, ids, rules, candle value / end / volume / interval and the verified
/// kickoff. Further CONSTRUCTED variants are named where used (a removed or
/// invalid candle, a withdrawn row, a removed settlement source, no verified
/// kickoff, a live event).
@MainActor
final class FootballPeriodWinnersAdapter10868Tests: XCTestCase {
    private typealias F = FootballRetained10868
    private typealias W = FootballPeriodWinnersAdapter10868
    private typealias Copy = FootballPeriodWinnersCopy10868
    private typealias Details = OriginalMarketDetails9483

    private var event: EventDetail { get throws { try F.detail(F.finalDetail) } }
    private var markets: GameMarketsResponse { get throws { try F.markets(F.finalMarkets) } }

    private func admitted(_ binding: W.Binding? = nil, markets json: String? = nil) throws -> [W.Admitted] {
        W.admitted(try self.event, markets: try F.markets(json ?? F.finalMarkets),
                   binding: binding ?? F.quarterBinding, host: F.periodHost(F.finalNow))
    }

    private func card(_ binding: W.Binding? = nil, markets json: String? = nil,
                      selected: String? = nil) throws -> FootballPeriodWinnersInput10868 {
        try XCTUnwrap(W.input(try self.event, markets: try F.markets(json ?? F.finalMarkets),
                              binding: binding ?? F.quarterBinding, selectedID: selected,
                              host: F.periodHost(F.finalNow)))
    }

    private func one(_ period: Int, _ side: W.Side, in list: [W.Admitted]) throws -> W.Admitted {
        let found = list.filter { $0.original.period == period && $0.original.side == side }
        XCTAssertEqual(found.count, 1)
        return try XCTUnwrap(found.first)
    }

    /// CONSTRUCTED: the binding with one original's fields replaced.
    private func binding(replacing period: Int, _ side: W.Side,
                         with change: (W.Binding.Original) -> W.Binding.Original) -> W.Binding {
        W.Binding(eventID: F.quarterBinding.eventID, verifiedStart: F.quarterBinding.verifiedStart,
                  originals: F.quarterBinding.originals.map {
                      $0.period == period && $0.side == side ? change($0) : $0
                  })
    }

    private func with(_ o: W.Binding.Original, baseline: W.Binding.Baseline?) -> W.Binding.Original {
        W.Binding.Original(period: o.period, side: o.side, source: o.source, marketID: o.marketID,
                           outcomeIDs: o.outcomeIDs, marketType: o.marketType, regulationOnly: o.regulationOnly,
                           rules: o.rules, baseline: baseline)
    }

    // MARK: - Twelve exact originals

    func testAllTwelveOriginalIdentitiesArePreservedAndServed() throws {
        let list = try admitted()
        XCTAssertEqual(list.count, 12)
        XCTAssertTrue(list.allSatisfy { $0.state == .served })
        XCTAssertEqual(list.map(\.identity), F.quarterBinding.originals.map {
            Details.Identity(source: "kalshi", market: String($0.marketID),
                             side: $0.outcomeIDs.map(String.init).joined(separator: "+"))
        })
        XCTAssertEqual(Set(list.map(\.cellID)).count, 12)

        let input = try card()
        XCTAssertEqual(input.panels.map(\.period.label), ["Q1", "Q2", "Q3", "Q4"])
        XCTAssertEqual(input.series.map { $0.cells.count }, [4, 4, 4])
        XCTAssertEqual(Set(input.cells.map(\.id)), Set(list.map(\.cellID)))
        XCTAssertTrue(input.cells.allSatisfy { input.isUnique($0.id) })

        // The catalogue lists each of the twelve once, under the same identity.
        let originals = FootballOriginalsAdapter10868.originals(
            try self.event, markets: try self.markets, host: F.originalsHost(F.finalNow), tint: .blue, periodWinners: list)
        let catalogue = try XCTUnwrap(originals.catalogue)
        for entry in list {
            XCTAssertEqual(catalogue.originals.filter { $0.identity == entry.identity }.count, 1, entry.cellID)
        }
    }

    func testEachResultIsItsOwnContractsSettlementNeverAQuoteOrThePoints() throws {
        let list = try admitted()
        let won: [(Int, W.Side)] = [(1, .home), (2, .away), (3, .home), (4, .home)]
        for entry in list {
            let expected = won.contains { $0 == (entry.original.period, entry.original.side) }
            XCTAssertEqual(entry.result, expected ? .won(Copy.won) : .lost(Copy.lost),
                           "\(entry.original.period) \(entry.original.side)")
        }
        // CONSTRUCTED: Q2 Philadelphia's row without its resolution source. Its
        // served `probability` stays 1.0 — and is never read as the result.
        let rows = try periodRows().map { row -> [String: Any] in
            guard (row["contributor_outcome_ids"] as? [Int]) == [242843305] else { return row }
            var edited = row
            edited["resolution_source"] = NSNull()
            return edited
        }
        let json = try F.edited(F.finalMarkets, setting: ["period_markets": rows])
        let edited = try one(2, .away, in: try admitted(markets: json))
        XCTAssertEqual(edited.result, .unconfirmed(Copy.unconfirmed))
        XCTAssertEqual(edited.pregame?.probability, 0.29, "the trade is unaffected by the grade")
    }

    // MARK: - Pregame trades, as traded

    func testHourEndingAndMinuteEndingTradesKeepTheirOwnPrecision() throws {
        let list = try admitted()
        let host = F.periodHost(F.finalNow)
        for entry in list {
            let candle = try XCTUnwrap(entry.original.baseline)
            let clock = HockeyJourneyPageAdapter10868.clockWords(candle.endingAt, host: host.words)
            let hourly = (entry.original.period, entry.original.side) == (3, .away)
                || (entry.original.period, entry.original.side) == (4, .away)
            XCTAssertEqual(candle.interval, hourly ? .hour : .minute)
            XCTAssertEqual(entry.clock, hourly ? Copy.hourEnding(clock) : Copy.minuteEnding(clock))
            XCTAssertEqual(entry.pregame?.accessibilityDetail,
                           (entry.clock ?? "") + " · " + SourceLabels.label(for: "kalshi"))
        }
    }

    func testTheFourthQuarterKeepsItsThreeTradesUnnormalized() throws {
        let list = try admitted()
        let q4 = list.filter { $0.original.period == 4 }
        XCTAssertEqual(q4.compactMap { $0.pregame?.probability }, [0.56, 0.32, 0.15])
        XCTAssertEqual(q4.compactMap { $0.pregame?.text }, ["56%", "32%", "15%"])
        XCTAssertEqual(q4.compactMap { $0.pregame?.probability }.reduce(0, +), 1.03, accuracy: 1e-9)
        // The same raw values reach the dots' geometry.
        let input = try card()
        let q4ID = W.periodID(try self.event, 4)
        let q4Cells = input.cells.filter { $0.periodID == q4ID }
        XCTAssertEqual(q4Cells.compactMap { input.fraction($0) }, [0.56, 0.32, 0.15])
    }

    func testQ2PhiladelphiaIsTheUpsetWithItsOwnTradeAndItsOwnQuarterScore() throws {
        let event = try self.event
        let input = try card()
        let teams = FootballEventPageAdapter10868.teams(event)
        let q2 = try one(2, .away, in: try admitted())

        XCTAssertEqual(q2.pregame?.text, "29%")
        XCTAssertEqual(q2.result, .won(Copy.won))
        XCTAssertEqual(input.words.title, Copy.upsetTitle)
        XCTAssertEqual(input.words.summary, Copy.upsetSummary(team: teams.awayShort, period: "Q2", chance: "29%"))
        // The card opens on it.
        XCTAssertEqual(input.selectedID, q2.cellID)
        XCTAssertEqual(input.caption(q2.cellID), Copy.caption(period: "Q2", outcome: Copy.outscore(team: teams.awayShort)))

        // The quarter's own points, from the stored line score — not the running score.
        XCTAssertEqual(input.homeScoreLabel, "JAX")
        XCTAssertEqual(input.awayScoreLabel, "PHI")
        let scores = (1...4).map { input.score(W.periodID(event, $0), missing: "missing") }
        let expected: [(String, String)] = [("7", "0"), ("0", "14"), ("3", "0"), ("9", "3")]
        for (score, want) in zip(scores, expected) {
            guard case .reported(let home, let away, let provenance) = score else { return XCTFail("\(score)") }
            XCTAssertEqual(home, want.0)
            XCTAssertEqual(away, want.1)
            XCTAssertTrue(provenance.hasSuffix("exact quarter-end time unavailable"), provenance)
        }
    }

    func testOnlyTheContractThatSaysSoExcludesOvertime() throws {
        let input = try card()
        XCTAssertEqual(input.panels.map(\.note), [nil, nil, nil, Copy.regulationOnly])
        XCTAssertEqual(input.words.notes, [Copy.pointsNote, Copy.regulationOnlyNote(period: "Q4")])
        XCTAssertEqual(input.panels.last?.spokenLabel, PeriodLabel.spoken("Q4"))
    }

    // MARK: - Unavailable and withdrawn originals

    func testAMissingOrInvalidTradeIsUnavailableAndTheContractStillGrades() throws {
        // CONSTRUCTED: Q1 tie with no bound trade.
        let none = try one(1, .tie, in: try admitted(binding(replacing: 1, .tie) { with($0, baseline: nil) }))
        XCTAssertNil(none.pregame)
        XCTAssertEqual(none.pregameMissing, Copy.pregameUnavailable)
        XCTAssertEqual(none.result, .lost(Copy.lost))

        // CONSTRUCTED: candles no pregame trade can be — a 1.0 close, no volume,
        // and one ending after the verified kickoff.
        let original = try one(1, .home, in: try admitted()).original
        let candle = try XCTUnwrap(original.baseline)
        for bad in [W.Binding.Baseline(value: 1, endingAt: candle.endingAt, volume: candle.volume, interval: .minute),
                    W.Binding.Baseline(value: 0.54, endingAt: candle.endingAt, volume: 0, interval: .minute),
                    W.Binding.Baseline(value: 0.54, endingAt: "2026-10-11T13:31:00+00:00".asDate!,
                                       volume: candle.volume, interval: .minute)] {
            let entry = try one(1, .home, in: try admitted(binding(replacing: 1, .home) { with($0, baseline: bad) }))
            XCTAssertNil(entry.pregame, "\(bad)")
        }

        // CONSTRUCTED: no verified kickoff — no trade is admitted, results stay.
        let unverified = W.Binding(eventID: F.quarterBinding.eventID, verifiedStart: nil,
                                   originals: F.quarterBinding.originals)
        let list = try admitted(unverified)
        XCTAssertTrue(list.allSatisfy { $0.pregame == nil })
        XCTAssertEqual(try one(2, .away, in: list).result, .won(Copy.won))
    }

    func testAWithdrawnOriginalBorrowsNoTradeAndNoResult() throws {
        // CONSTRUCTED: the Q3 tie row no longer served.
        let json = try F.edited(F.finalMarkets, setting: ["period_markets": try periodRows(dropping: [242843333])])
        let list = try admitted(markets: json)
        let withdrawn = try one(3, .tie, in: list)
        XCTAssertEqual(withdrawn.state, .withdrawn)
        XCTAssertNil(withdrawn.pregame, "its bound trade needs its unchanged original")
        XCTAssertEqual(withdrawn.pregameMissing, Copy.originalUnavailable)
        XCTAssertEqual(withdrawn.result, .unconfirmed(Copy.unconfirmed))
        // The rest stand.
        XCTAssertEqual(list.filter { $0.state == .served }.count, 11)
        let input = try card(markets: json)
        XCTAssertTrue(input.cells.contains { $0.id == withdrawn.cellID && $0.result == .unconfirmed(Copy.unconfirmed) })
    }

    func testOnlyTheCompletedGameWithServedBoundOriginalsGetsTheCard() throws {
        // No binding, or nothing served: no story is offered.
        XCTAssertNil(W.input(try self.event, markets: try self.markets, binding: nil, selectedID: nil,
                             host: F.periodHost(F.finalNow)))
        XCTAssertNil(W.input(try self.event, markets: nil, binding: F.quarterBinding, selectedID: nil,
                             host: F.periodHost(F.finalNow)))
        // A live game: not this card's phase.
        let live = try F.detail(F.liveDetail)
        XCTAssertTrue(W.admitted(live, markets: try F.markets(F.liveMarkets), binding: F.quarterBinding,
                                 host: F.periodHost(F.liveNow)).isEmpty)
    }

    // MARK: - Selection and layout

    func testChangingThePeriodKeepsTheSelectedSideAndAHeldIdIsExact() throws {
        let event = try self.event
        let list = try admitted()
        let q2Away = try one(2, .away, in: list)
        let input = try card(selected: q2Away.cellID)
        XCTAssertEqual(input.selected?.cell.id, q2Away.cellID)
        XCTAssertEqual(input.idForPanel(W.periodID(event, 3)), try one(3, .away, in: list).cellID)
        XCTAssertEqual(input.idForPanel(W.periodID(event, 4)), try one(4, .away, in: list).cellID)
        XCTAssertEqual(input.selectedPeriodCells.map(\.cell.id), [
            try one(2, .home, in: list).cellID, q2Away.cellID, try one(2, .tie, in: list).cellID,
        ])
        // Every one of the twelve can be held.
        for entry in list {
            XCTAssertEqual(try card(selected: entry.cellID).selectedID, entry.cellID)
        }
        // An id that names nothing falls back to the opening original.
        XCTAssertEqual(try card(selected: "kalshi|1|1").selectedID, q2Away.cellID)
    }

    func testTwoAcrossOnAPhoneFourWideOneOrTwoAtAccessibilitySizes() {
        XCTAssertEqual(FootballPeriodWinnersInput10868.columns(wide: false, accessibility: false), 2)
        XCTAssertEqual(FootballPeriodWinnersInput10868.columns(wide: true, accessibility: false), 4)
        XCTAssertEqual(FootballPeriodWinnersInput10868.columns(wide: false, accessibility: true), 1)
        XCTAssertEqual(FootballPeriodWinnersInput10868.columns(wide: true, accessibility: true), 2)
    }

    func testTheCardFitsAPhoneAtStandardAndAccessibilityText() throws {
        let input = try card()
        for size in [DynamicTypeSize.large, .accessibility3] {
            let view = FootballPeriodWinnersPresentation10868(input: input, onSelect: { _ in }, onDetails: { _ in },
                                                              onExpand: {})
                .frame(width: 375)
                .environment(\.horizontalSizeClass, .compact)
            let host = hostForMeasurement(view, at: size)
            let fitted = host.sizeThatFits(in: CGSize(width: 375, height: CGFloat.greatestFiniteMagnitude))
            XCTAssertLessThanOrEqual(fitted.width, 375, "\(size)")
            XCTAssertGreaterThan(fitted.height, 0)
        }
    }

    // MARK: - Details through the same helper

    func testDetailsPrintTheSameAdmittedTradeAndTheContractsOwnRules() throws {
        let list = try admitted()
        let q2 = try one(2, .away, in: list)
        let originals = FootballOriginalsAdapter10868.originals(
            try self.event, markets: try self.markets, host: F.originalsHost(F.finalNow), tint: .blue, periodWinners: list)
        let made = try XCTUnwrap(originals.catalogue?.originals.first { $0.identity == q2.identity })
        XCTAssertEqual(made.pregame, .value("29%", placement: 0.29,
                                           provenance: Copy.baselineProvenance(q2.clock ?? "") + " · "
                                               + SourceLabels.label(for: "kalshi")))
        XCTAssertEqual(made.about.rules, .verified(q2.original.rules))
        XCTAssertEqual(made.mode, .result)
        // Without the story's admission the same original keeps the catalogue's own reading.
        let plain = FootballOriginalsAdapter10868.originals(
            try self.event, markets: try self.markets, host: F.originalsHost(F.finalNow), tint: .blue)
        XCTAssertNotEqual(plain.catalogue?.originals.first { $0.identity == q2.identity }?.about.rules,
                          .verified(q2.original.rules))
    }

    // MARK: - Helpers

    /// The final body's period rows as served.
    private func periodRows() throws -> [[String: Any]] {
        let object = try XCTUnwrap(JSONSerialization.jsonObject(with: Data(F.finalMarkets.utf8)) as? [String: Any])
        return try XCTUnwrap(object["period_markets"] as? [[String: Any]])
    }

    private func periodRows(dropping outcome: [Int]) throws -> [[String: Any]] {
        try periodRows().filter { ($0["contributor_outcome_ids"] as? [Int]) != outcome }
    }
}
