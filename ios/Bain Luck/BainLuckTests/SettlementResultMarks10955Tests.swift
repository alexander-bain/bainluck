import XCTest
@testable import Bain_Luck

/// #10955 — a settled line shows its result as a mark, never as a price.
///
/// Every `bookmaker: "settlement"` point is a RESULT, whatever its
/// `settlement_basis`: `resolution_date` is a schedule, `settled_at` is when this
/// system noticed, and `last_observation` / `clock` / missing / anything else
/// claim no time at all. None of them may become a run, a bridge, a crosshair
/// stop, an axis bound, a Sum input or a price count. The line keeps its real
/// prices; one Won/Lost mark sits on its own last price (or, for a winner with
/// no prices, at the last instant any line was priced).
///
/// These run the chart's own stages in its own order — decode with the app's
/// decoder, `VerifiedTitleHistory.drawing` / `settlementResults` (what `loadData`
/// stores), `EvolutionChartView.chartPoints` (what `chartEntries` returns),
/// `gapBridges`, `resultMarks`, the crosshair's `ChartCrosshairPolicy`, the axis
/// domain and `cardBody` — rather than a parallel model of them.
@MainActor
final class SettlementResultMarks10955Tests: XCTestCase {
    private typealias G = ASettlementPointIsNotAPrice10955Tests

    static let chiefs = (id: 1_309_490, name: "Kansas City Chiefs")
    static let allNames = ["Buffalo Bills", "Los Angeles Rams", "San Francisco 49ers",
                           "Kansas City Chiefs", "Los Angeles Chargers", "New York Giants",
                           "New York Jets"]

    /// Every basis the server can serve, plus none and one it does not know,
    /// each at the x it would carry (relative to the line's last price).
    static let bases: [(basis: String?, offset: TimeInterval)] = [
        ("resolution_date", 3600),          // a scheduled close, inside the gap threshold
        ("settled_at", 400 * 86400),        // a notice, long after
        ("last_observation", 1),            // nudged to one second after the last price
        ("clock", 3 * 86400),               // the moving clock
        (nil, 3600),                        // no key at all
        ("venue_close_v2", 2 * 3600),       // a basis this build has never heard of
    ]

    /// What the chart holds and draws for one `/history` body.
    struct Chart {
        let drawn: ProbabilityTimelineResponse
        let results: [SettlementResult]
        let entries: [EvolutionPoint]
        let bridges: [EvolutionGapBridge]
        let marks: [EvolutionResultMarks.Placement]

        func leg(_ name: String) -> [EvolutionPoint] {
            entries.filter { !$0.isCombined && $0.name == name }
        }

        /// `updateCrosshair`'s candidates: the real points of the selected lines.
        func crosshair(at date: Date, selected: Set<String>) -> (date: Date, entries: [ScrubCandidate])? {
            let candidates = entries
                .filter { !$0.isCombined && selected.contains($0.name) }
                .map { ScrubCandidate(date: $0.date, name: $0.name, probability: $0.probability) }
            return ChartCrosshairPolicy.resolve(at: date, among: candidates)
        }

        /// The x-axis domain: `chartSection` plans it off `entries.map(\.date)`.
        var domain: ClosedRange<Date>? {
            guard let lo = entries.map(\.date).min(), let hi = entries.map(\.date).max() else { return nil }
            return lo...hi
        }
    }

    static func chart(_ history: FuturesHistoryResponse, names: [String] = allNames,
                      selected: Set<String>? = nil) throws -> Chart {
        let timeline = try G.timeline()
        let drawn = VerifiedTitleHistory.drawing(history, over: timeline)
        let results = VerifiedTitleHistory.settlementResults(history, over: timeline)
        let entries = EvolutionChartView.chartPoints(
            timeline: drawn.timeline, names: Set(names), selected: selected ?? Set(names),
            cutoff: nil, showCombined: true, supportsCombined: true)
        return Chart(drawn: drawn, results: results, entries: entries,
                     bridges: EvolutionChartView.gapBridges(entries),
                     marks: EvolutionChartView.resultMarks(results, entries: entries, names: names))
    }

    static let realBills = (0..<8).map { G.lastPrice.addingTimeInterval(Double($0 - 7) * 3600) }

    // MARK: - G1: every basis is a result mark on the line's own last price

    func testEveryBasisIsOneResultMarkAtTheLinesOwnLastPriceAndNeverAPoint() throws {
        for (basis, offset) in Self.bases {
            let label = basis ?? "missing"
            let settledAt = G.lastPrice.addingTimeInterval(offset)
            let chart = try Self.chart(G.history([
                (G.bills.id, G.bills.name,
                 G.hourly(0.10, step: 0.002) + [G.settlement(0.0, at: settledAt, basis: basis)]),
                (G.rams.id, G.rams.name, G.hourly(0.09, step: 0.001)),
            ], coverageHours: offset / 3600 + 7, observationTimes: 9))

            let bills = chart.leg(G.bills.name)
            XCTAssertEqual(bills.map(\.date), Self.realBills, "\(label): only the prices are points")
            XCTAssertEqual(bills.map(\.probability), (0..<8).map { (0.10 + Double($0) * 0.002) * 100 },
                           "\(label): every price keeps its value")
            XCTAssertFalse(chart.entries.contains { $0.date == settledAt },
                           "\(label): nothing — not the Sum line either — is drawn at the settlement x")
            XCTAssertEqual(Set(bills.map(\.run)), [0], "\(label): one solid run, nothing joined to the result")
            XCTAssertFalse(bills.contains { $0.standsAlone }, "\(label): no observation dot for the result")
            XCTAssertTrue(chart.bridges.isEmpty, "\(label): no dotted bridge out to the result")

            XCTAssertEqual(chart.marks, [EvolutionResultMarks.Placement(
                name: G.bills.name, date: G.lastPrice, y: (0.10 + 7 * 0.002) * 100, outcome: .lost)],
                "\(label): exactly one mark, at the line's own last price, saying Lost")

            // The raw point is kept as served — value, stamp and basis — never moved.
            XCTAssertEqual(chart.results, [SettlementResult(
                name: G.bills.name, probability: 0.0, timestamp: G.stamp(settledAt), basis: basis)],
                "\(label)")
        }
    }

    // MARK: - G3: crosshair, domain, freshness and the Sum line see prices only

    func testTheCrosshairNeverRestsOnTheSettlementAndTheAxisEndsAtTheLastPrice() throws {
        for (basis, offset) in Self.bases {
            let label = basis ?? "missing"
            let settledAt = G.lastPrice.addingTimeInterval(offset)
            let chart = try Self.chart(G.history([
                (G.bills.id, G.bills.name,
                 G.hourly(0.10, step: 0.002) + [G.settlement(0.0, at: settledAt, basis: basis)]),
                (G.rams.id, G.rams.name, G.hourly(0.09, step: 0.001)),
            ], coverageHours: offset / 3600 + 7, observationTimes: 9))

            XCTAssertEqual(chart.domain?.upperBound, G.lastPrice, "\(label): the axis ends at the last price")
            XCTAssertTrue(chart.marks.allSatisfy { chart.domain?.contains($0.date) == true },
                          "\(label): the mark sits inside the axis, never past it")

            // A finger anywhere — on the settlement x, past it, on the last price —
            // rests on a real instant and reads real prices.
            let selected: Set = [G.bills.name, G.rams.name]
            for x in [settledAt, settledAt.addingTimeInterval(86400), G.lastPrice,
                      G.lastPrice.addingTimeInterval(1800), Self.realBills[0]] {
                let read = try XCTUnwrap(chart.crosshair(at: x, selected: selected), label)
                XCTAssertTrue(Self.realBills.contains(read.date), "\(label): rests on a price instant")
                XCTAssertNotEqual(read.date, settledAt, "\(label): never prints the settlement's time")
                XCTAssertFalse(read.entries.contains { $0.probability == 0 || $0.probability == 100 },
                               "\(label): never reads the result out as a price")
            }

            // Freshness: the server counted the settlement as a price; the chart does not.
            XCTAssertEqual(chart.drawn.observationTimes, 8, label)
            XCTAssertEqual(chart.drawn.coverageHours, 7.0, label)

            // The Sum line adds the prices drawn at each price instant, nothing else.
            let sum = chart.entries.filter(\.isCombined)
            XCTAssertEqual(sum.map(\.date), Self.realBills, label)
            XCTAssertEqual(sum.last?.probability ?? 0, (0.114 + 0.097) * 100, accuracy: 1e-9, label)
        }
    }

    // MARK: - G4: a winner with no prices; a chart with none at all

    func testASynthesisedWinnerIsMarkedAtTheLastPricedInstantAndMovesNothing() throws {
        for (basis, offset) in [("last_observation", 0.0), ("resolution_date", 5 * 86400.0),
                                ("settled_at", 400 * 86400.0)] as [(String, TimeInterval)] {
            let settledAt = G.lastPrice.addingTimeInterval(offset)
            let chart = try Self.chart(G.history([
                (G.bills.id, G.bills.name, G.hourly(0.10, step: 0.002)),
                (G.rams.id, G.rams.name, G.hourly(0.09, step: 0.001)),
                (Self.chiefs.id, Self.chiefs.name, [G.settlement(1.0, at: settledAt, basis: basis)]),
            ], coverageHours: offset / 3600 + 7, observationTimes: 9))

            XCTAssertTrue(chart.leg(Self.chiefs.name).isEmpty, "\(basis): the winner has no line")
            XCTAssertEqual(chart.marks, [EvolutionResultMarks.Placement(
                name: Self.chiefs.name, date: G.lastPrice, y: 100, outcome: .won)],
                "\(basis): one Won mark at the last priced instant, whatever its served x")
            XCTAssertEqual(chart.domain?.upperBound, G.lastPrice, "\(basis): the axis is not extended")
            let read = try XCTUnwrap(chart.crosshair(
                at: settledAt, selected: [G.bills.name, Self.chiefs.name]))
            XCTAssertEqual(read.date, G.lastPrice, basis)
            XCTAssertEqual(read.entries.map(\.name), [G.bills.name], "\(basis): the winner is no crosshair stop")
        }
    }

    func testAChartWithNoPricesAtAllStaysSparseAndDrawsNoMark() throws {
        for (basis, offset) in Self.bases {
            let label = basis ?? "missing"
            let chart = try Self.chart(G.history([
                (Self.chiefs.id, Self.chiefs.name,
                 [G.settlement(1.0, at: G.lastPrice.addingTimeInterval(offset), basis: basis)]),
            ], coverageHours: 0.0, observationTimes: 1))

            XCTAssertTrue(chart.drawn.timeline.isEmpty, "\(label): no instant is invented")
            XCTAssertTrue(chart.entries.isEmpty, label)
            XCTAssertTrue(chart.marks.isEmpty, "\(label): no dot at a notice time or the clock")
            XCTAssertEqual(chart.results.count, 1, "\(label): the result is kept, just not drawn")
            XCTAssertEqual(chart.drawn.observationTimes, 0, label)
            XCTAssertNil(chart.drawn.coverageHours, "\(label): no prices is not an instant of prices")
            XCTAssertEqual(EvolutionChartView.cardBody(
                windowPoints: chart.entries.count, windowInstants: chart.drawn.timeline.count,
                totalInstants: chart.drawn.timeline.count, windowWord: "in this range"),
                .sparse(.init(note: "No price history yet", hint: nil)), label)
        }
    }

    /// A one-price line plus its settlement used to reach the plot's two-point
    /// bar; one price is still one price.
    func testTheSettlementDoesNotCountTowardTheTwoPointsAPlotNeeds() throws {
        let price = G.lastPrice
        let chart = try Self.chart(G.history([
            (G.bills.id, G.bills.name,
             [["timestamp": G.stamp(price), "probability": 0.2, "american_odds": NSNull(),
               "bookmaker": "consensus"],
              G.settlement(0.0, at: price.addingTimeInterval(3600), basis: "resolution_date")]),
        ], coverageHours: 1.0, observationTimes: 2), names: [G.bills.name])
        XCTAssertEqual(chart.entries.count, 1)
        XCTAssertEqual(EvolutionChartView.cardBody(
            windowPoints: chart.entries.count, windowInstants: chart.drawn.timeline.count,
            totalInstants: chart.drawn.timeline.count, windowWord: "in this range"),
            .sparse(.init(note: "Only one price seen so far", hint: nil)))
    }

    // MARK: - G5: a line with no settlement point draws exactly as before

    func testAHealthyLineBesideASettledOneIsUntouchedIncludingItsGaps() throws {
        // Rams carries a real ten-hour hole: its bridge, runs and lone point must
        // come out the same whether or not the Bills line beside it settled.
        var early: [[String: Any]] = []
        for hoursBefore in [21, 20, 19, 18] {
            let at = G.lastPrice.addingTimeInterval(TimeInterval(-hoursBefore * 3600))
            early.append(["timestamp": G.stamp(at), "probability": 0.05,
                          "american_odds": NSNull(), "bookmaker": "consensus"])
        }
        let rams = early + G.hourly(0.09, step: 0.001)
        let healthy = try Self.chart(G.history([
            (G.bills.id, G.bills.name, G.hourly(0.10, step: 0.002)),
            (G.rams.id, G.rams.name, rams),
        ], coverageHours: 21.0, observationTimes: 12))
        let settled = try Self.chart(G.history([
            (G.bills.id, G.bills.name,
             G.hourly(0.10, step: 0.002) + [G.settlement(0.0, at: G.lastPrice.addingTimeInterval(3600),
                                                         basis: "resolution_date")]),
            (G.rams.id, G.rams.name, rams),
        ], coverageHours: 22.0, observationTimes: 13))

        func shape(_ chart: Chart, _ name: String) -> [String] {
            chart.leg(name).map { "\($0.date.timeIntervalSince1970)|\($0.probability)|\($0.run)|\($0.standsAlone)" }
        }
        XCTAssertEqual(shape(settled, G.rams.name), shape(healthy, G.rams.name))
        XCTAssertEqual(Set(healthy.leg(G.rams.name).map(\.run)), [0, 1], "the control has a real gap")
        XCTAssertEqual(settled.bridges.map(\.id), healthy.bridges.map(\.id))
        XCTAssertEqual(settled.bridges.map(\.id), ["gap:Los Angeles Rams#1"])
        XCTAssertEqual(shape(settled, G.bills.name), shape(healthy, G.bills.name),
                       "the settled line's prices draw exactly as the healthy one's")
        XCTAssertTrue(healthy.marks.isEmpty && healthy.results.isEmpty)
        XCTAssertEqual(healthy.drawn.coverageHours, 21.0, "no settlement: the server's keys pass through")
        XCTAssertEqual(healthy.drawn.observationTimes, 12)
        XCTAssertEqual(settled.drawn.coverageHours, 21.0, "re-measured over the same prices")
        XCTAssertEqual(settled.drawn.observationTimes, 12)
    }

    // MARK: - Reading the grade, and where a mark is not drawn

    func testTheMarkReadsTheServedGradeAndNeverRegradesIt() {
        XCTAssertEqual(EvolutionResultMarks.outcome(of: 1.0), .won)
        XCTAssertEqual(EvolutionResultMarks.outcome(of: 0.0), .lost)
        XCTAssertEqual(EvolutionResultMarks.outcome(of: 0.5), .settled)
        XCTAssertEqual(EvolutionResultMarks.Outcome.won.spoken, "Won")
        XCTAssertEqual(EvolutionResultMarks.Outcome.lost.spoken, "Lost")
        XCTAssertEqual(EvolutionResultMarks.Outcome.settled.spoken, "Settled")
        for outcome in [EvolutionResultMarks.Outcome.won, .lost, .settled] {
            XCTAssertFalse(outcome.spoken.contains("%"), "a result is never spoken as a price")
        }
    }

    func testALineTheChartIsNotShowingGetsNoMark() throws {
        let chart = try Self.chart(G.history([
            (G.bills.id, G.bills.name,
             G.hourly(0.10, step: 0.002) + [G.settlement(0.0, at: G.lastPrice.addingTimeInterval(3600),
                                                         basis: "resolution_date")]),
            (G.rams.id, G.rams.name, G.hourly(0.09, step: 0.001)),
        ], coverageHours: 8.0, observationTimes: 9), names: [G.rams.name])
        XCTAssertTrue(chart.marks.isEmpty)
        XCTAssertEqual(chart.results.map(\.name), [G.bills.name])
    }

    func testTwoSettlementPointsOnOneLineStillMakeOneMark() throws {
        let chart = try Self.chart(G.history([
            (G.bills.id, G.bills.name,
             G.hourly(0.10, step: 0.002)
                + [G.settlement(0.0, at: G.lastPrice.addingTimeInterval(60), basis: "last_observation"),
                   G.settlement(0.0, at: G.lastPrice.addingTimeInterval(3600), basis: "resolution_date")]),
        ], coverageHours: 8.0, observationTimes: 10), names: [G.bills.name])
        XCTAssertEqual(chart.marks.count, 1)
        XCTAssertEqual(chart.results.map(\.basis), ["resolution_date"], "the last served wins")
    }

    // MARK: - The view draws this

    /// The stages above are the view's own; this reads that the view calls them
    /// where it draws (comments stripped, so only code can meet a pin).
    func testTheChartHoldsTheResultsApartAndDrawsOneMarkPerSettledLine() throws {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("Bain Luck/Components/EvolutionChartView.swift")
        let code = try String(contentsOf: url, encoding: .utf8)
            .split(separator: "\n", omittingEmptySubsequences: false)
            .filter { !$0.trimmingCharacters(in: .whitespaces).hasPrefix("//") }
            .joined(separator: "\n")
        XCTAssertTrue(code.contains("struct EvolutionChartView"), "the strip left nothing to read")
        XCTAssertTrue(code.contains(
            "settlementResults = lines.map { VerifiedTitleHistory.settlementResults($0, over: result) } ?? []"))
        XCTAssertTrue(code.contains("return Self.chartPoints(\n            timeline: data.timeline,"),
                      "chartEntries must be the stage these tests run")
        XCTAssertTrue(code.contains(
            "let results = Self.resultMarks(settlementResults, entries: entries, names: displayedNames)"))
        XCTAssertTrue(code.contains("ForEach(results) { mark in\n                PointMark("))
        XCTAssertTrue(code.contains(".accessibilityValue(mark.outcome.spoken)"))
        XCTAssertEqual(code.components(separatedBy: "PointMark(").count - 1, 1,
                       "the result mark is the chart's only point mark")
    }
}
