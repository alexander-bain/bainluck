import SwiftUI
import XCTest
@testable import Bain_Luck

/// #10868 — the golf tournament adapter, part two (each golfer's readings and
/// the named "Chance to win" history), on the retained Baycurrent Classic and
/// India bodies in `GolfFieldRetainedBodies10868`.
///
/// PREPARED, NOT RUN: written under a source-only hold (no build, no XCTest).
///
/// The served Baycurrent Winner market is RESOLVED, so its real phase is final.
/// The before and recorded frames below replay it as CONSTRUCTED: the same body
/// with `status` "open" (one key) read at a CONSTRUCTED `now` — 2026-10-07T12:00Z
/// (before the listed start) or 2026-10-08T00:30Z (after it). In those replays
/// every detail price is stamped Oct 11, after the reader's now, so no detail
/// price is ever read: only the served history is.
///
/// Other CONSTRUCTED variants, each named where used: a grade on one row
/// (`is_winner` + `resolution_source`), a settlement point (`bookmaker` on one
/// row), a missing price (`probability` on one row) and India read after its
/// listed start. Runs are the runs OF THE SUBSET (see the fixture's notes).
@MainActor
final class GolfFieldHistoryAdapter10868Tests: XCTestCase {
    private typealias H = GolfFieldHistoryAdapter10868
    private typealias A = GolfFieldPageAdapter10868
    private typealias R = GolfFieldRetainedBodies10868

    private static let beforeNow = "2026-10-07T12:00:00Z"
    private static let recordedNow = "2026-10-08T00:30:00Z"
    private static let finalNow = "2026-10-12T23:55:18Z"

    private func field(_ winnerJSON: String, _ historyJSON: String?, now: String) throws -> H.Field {
        let winner = try R.market(winnerJSON)
        let history = try historyJSON.map { try R.history($0) }
        return GolfFieldPageInputAdapter10868.field(.init(winner: winner, history: history), now: now.asDate!)
    }

    private func openWinner() throws -> String {
        try R.edited(R.baycurrentWinner, ["status"], to: "open")
    }

    private func x(_ stamp: String) -> Double { stamp.asDate!.timeIntervalSince1970 }

    /// Each run's first and last time.
    private func bounds(_ series: FieldHistorySeries10868) -> [[Double]] {
        series.runs.map { [$0.points.first?.x ?? .nan, $0.points.last?.x ?? .nan] }
    }

    private func clock(_ stamp: String, _ host: H.Host) -> String {
        A.clockWords(stamp.asDate!, host: host)
    }

    private func pid(_ outcome: Int, _ stamp: String) -> String {
        "datagolf:64266833:\(outcome)#\(stamp)"
    }

    // MARK: - Recorded

    func testRecordedFrameDrawsEachGolfersOwnLineFromSixHoursBeforeTheStartToNow() throws {
        let host = R.host(Self.recordedNow)
        let field = try field(openWinner(), R.baycurrentHistory, now: Self.recordedNow)
        XCTAssertEqual(field.phase, .recorded)
        let input = H.history(field, cohort: [R.schauffele, R.clark, R.morikawa, R.thorbjornsen], selected: R.schauffele,
                              chooserAvailable: true, host: host)

        XCTAssertEqual(input.series.map(\.id), [R.schauffele, R.clark, R.morikawa, R.thorbjornsen].map { "datagolf:64266833:\($0)" })
        XCTAssertEqual(input.series.map(\.name), ["Xander Schauffele", "Wyndham Clark", "Collin Morikawa", "Michael Thorbjornsen"])
        XCTAssertEqual(input.series.map(\.shape), [.circle, .square, .diamond, .triangle])
        XCTAssertEqual(input.series.map(\.tint), (0..<4).map { Color(hex: EvolutionOutcomeColour.markHex(nil, index: $0)) })

        // Oct 5/6 readings are older than the frame (start less six hours); the
        // 00:32:03 and 00:36:33 rows are after the reader's now and are not drawn.
        XCTAssertEqual(bounds(input.series[0]), [[x("2026-10-08T00:02:03.231914+00:00"), x("2026-10-08T00:27:33.145591+00:00")]])
        XCTAssertEqual(input.series[0].runs[0].points.count, 6)
        XCTAssertEqual(bounds(input.series[1]), [[x("2026-10-08T00:02:03.231914+00:00"), x("2026-10-08T00:27:33.145591+00:00")]])
        XCTAssertEqual(input.series[1].runs[0].points.count, 5)
        XCTAssertEqual(input.series[2].runs[0].points.count, 5)
        XCTAssertTrue(input.series[3].runs.isEmpty, "Thorbjornsen has no served line in this history")
        XCTAssertTrue(input.series.flatMap { $0.runs.flatMap(\.points) }.allSatisfy { $0.style == .filled },
                      "the before reading is outside the frame, so nothing is hollow")

        XCTAssertEqual(input.readout, .beforeAndRecorded(beforeLabel: "Before start", recordedLabel: "Latest recorded"))
        XCTAssertEqual(input.series[0].before,
                       .independent(figure: "9%", provenance: "Recorded \(clock("2026-10-06T13:08:40.644152+00:00", host)) · DataGolf"))
        XCTAssertEqual(input.series[0].recorded,
                       .observation(pointID: pid(R.schauffele, "2026-10-08T00:27:33.145591+00:00"), figure: "9%",
                                    provenance: "Recorded \(clock("2026-10-08T00:27:33.145591+00:00", host)) · DataGolf"))
        XCTAssertEqual(input.series[1].recorded,
                       .observation(pointID: pid(R.clark, "2026-10-08T00:27:33.145591+00:00"), figure: "6%",
                                    provenance: "Recorded \(clock("2026-10-08T00:27:33.145591+00:00", host)) · DataGolf"))
        // A detail price stamped after the reader's now is never read.
        XCTAssertEqual(input.series[3].before, .absent(words: "Before-start chance not recorded"))
        XCTAssertEqual(input.series[3].recorded, .absent(words: "Chance since the start not recorded"))
        XCTAssertEqual(input.series[3].absentWords, "No recorded history")

        XCTAssertEqual(input.domain, FieldHistoryDomain10868(lower: x("2026-10-08T00:02:03.231914+00:00"),
                                                             upper: x("2026-10-08T00:27:33.145591+00:00")))
        // Auto scale: the highest plotted point is Schauffele's 0.090287; ×1.04 = 0.0939 → the 10% rung.
        XCTAssertEqual(input.ceiling, 0.1)
        XCTAssertEqual(input.yTicks, [0, 0.05, 0.1].map { FieldHistoryTick10868(value: $0, lines: [OddsChartView.axisLabel(for: $0)]) })
        XCTAssertEqual(input.scale?.label, "Auto scale · 0–10%")
        XCTAssertFalse(input.xTicks.isEmpty)
        XCTAssertTrue(input.guides.isEmpty, "no round start is claimed")
        XCTAssertEqual(input.caption, "Since the start date")
        XCTAssertEqual(input.notes, ["Probabilities from the DataGolf model",
                                     "“Before start” uses the tournament’s start date, not a tee time.",
                                     "Gaps remain blank."])
        XCTAssertEqual(input.selection, .series(id: "datagolf:64266833:\(R.schauffele)",
                                                missingWords: "No chance history for the selected golfer in this chart."))
        XCTAssertEqual(input.details?.isAvailable, false, "no Details destination exists")
        XCTAssertEqual(input.expand?.id, H.expandActionID)
        XCTAssertEqual(input.moreOriginals?.id, H.chooserActionID)
        XCTAssertNil(input.inspect)
        XCTAssertNil(input.inspection)
        XCTAssertEqual(input.series[0].choose?.id, "golf.history.choose.\(R.schauffele)")
        XCTAssertNil(input.plotAbsence)
    }

    // MARK: - Final

    func testFinalFrameBreaksWhereTheFuturesChartBreaksAndReadsOnlyTheBeforeReading() throws {
        let host = R.host(Self.finalNow)
        let field = try field(R.baycurrentWinner, R.baycurrentHistory, now: Self.finalNow)
        XCTAssertEqual(field.phase, .final)
        let input = H.history(field, cohort: [R.clark, R.schauffele], selected: nil, chooserAvailable: true, host: host)

        let clark = input.series[0]
        XCTAssertEqual(bounds(clark), [
            [x("2026-10-08T00:02:03.231914+00:00"), x("2026-10-08T00:32:03.148937+00:00")],
            [x("2026-10-10T02:01:32.388551+00:00"), x("2026-10-10T02:27:02.431908+00:00")],
            [x("2026-10-11T22:08:55.891004+00:00"), x("2026-10-11T22:08:55.891004+00:00")],
        ])
        // The same break rule the futures chart applies, over the same observations.
        let instants = clark.runs.flatMap(\.points).map { Date(timeIntervalSince1970: $0.x) }
        XCTAssertEqual(EvolutionSeriesGaps.runs(instants), [0, 0, 0, 0, 0, 0, 1, 1, 2])

        let schauffele = input.series[1]
        XCTAssertEqual(bounds(schauffele), [
            [x("2026-10-08T00:02:03.231914+00:00"), x("2026-10-08T00:27:33.145591+00:00")],
            [x("2026-10-11T06:02:25.916250+00:00"), x("2026-10-11T06:06:55.965994+00:00")],
            [x("2026-10-11T22:08:55.891004+00:00"), x("2026-10-11T22:08:55.891004+00:00")],
        ])
        XCTAssertEqual(schauffele.runs[1].points.last?.probability, 0, "a real 0 is a value")

        XCTAssertEqual(input.readout, .singleBefore(label: "Before start"))
        XCTAssertEqual(schauffele.before,
                       .independent(figure: "9%", provenance: "Recorded \(clock("2026-10-06T13:08:40.644152+00:00", host)) · DataGolf"))
        // The last served row (re-served Oct 6 prices at 22:08Z) is drawn as the
        // chart draws it, and never read out.
        XCTAssertEqual(schauffele.recorded, .absent(words: "Not recorded"))
        XCTAssertNil(schauffele.keyContext, "served with no grade: no result")
        XCTAssertEqual(input.caption, "Tournament history")
    }

    func testBrennansWinningLineIsDrawnAsServedAndHisResultComesOnlyFromAGrade() throws {
        let host = R.host("2026-10-12T23:56:42Z")
        let field = try field(R.baycurrentWinner, R.brennanHistory, now: "2026-10-12T23:56:42Z")
        let input = H.history(field, cohort: [R.brennan], selected: R.brennan, chooserAvailable: true, host: host)
        let brennan = input.series[0]
        XCTAssertEqual(bounds(brennan), [
            [x("2026-10-08T00:02:03.231914+00:00"), x("2026-10-08T00:27:33.145591+00:00")],
            [x("2026-10-11T06:32:25.936365+00:00"), x("2026-10-11T06:41:26.165769+00:00")],
            [x("2026-10-11T22:08:55.891004+00:00"), x("2026-10-11T22:08:55.891004+00:00")],
        ])
        XCTAssertEqual(brennan.runs[1].points.last?.probability, 1.0, "the model's served 1.0 is a reading, not a result")
        XCTAssertEqual(brennan.before,
                       .independent(figure: "3%", provenance: "Recorded \(clock("2026-10-06T13:08:40.644152+00:00", host)) · DataGolf"))
        XCTAssertNil(brennan.keyContext, "the market is resolved with no grade, so no result is claimed")

        // CONSTRUCTED: Brennan's row graded (`is_winner` true, `resolution_source`
        // "datagolf_settlement" — the two grade keys only).
        var graded = try R.edited(R.baycurrentWinner, ["outcomes", 3, "is_winner"], to: true)
        graded = try R.edited(graded, ["outcomes", 3, "resolution_source"], to: "datagolf_settlement")
        let gradedField = try self.field(graded, R.brennanHistory, now: "2026-10-12T23:56:42Z")
        let gradedInput = H.history(gradedField, cohort: [R.brennan], selected: nil, chooserAvailable: true, host: host)
        XCTAssertEqual(gradedInput.series[0].keyContext,
                       FieldHistoryKeyContext10868(label: "Result", words: "Won", spoken: "Final result: Won"))
        XCTAssertEqual(gradedInput.series[0].runs, brennan.runs, "a grade never moves a point")
        XCTAssertNil(gradedField.price(gradedField.outcome(R.brennan)!), "a graded row's price is never read")
    }

    func testASettlementPointIsRemovedAndAMissingPriceBreaksTheLine() throws {
        let host = R.host("2026-10-12T23:56:42Z")
        // CONSTRUCTED: the 22:08:55 row's `bookmaker` set to "settlement" (one key).
        let settled = try R.edited(R.brennanHistory, ["outcomes", 0, "history", 11, "bookmaker"], to: "settlement")
        let field = try self.field(R.baycurrentWinner, settled, now: "2026-10-12T23:56:42Z")
        let input = H.history(field, cohort: [R.brennan], selected: nil, chooserAvailable: true, host: host)
        XCTAssertEqual(input.series[0].runs.count, 2, "removed outright: no point and no gap")
        XCTAssertEqual(input.domain.upper, x("2026-10-11T06:41:26.165769+00:00"))

        // CONSTRUCTED: Schauffele's 00:16:55 price set to null (one key).
        let gap = try R.edited(R.baycurrentHistory, ["outcomes", 1, "history", 5, "probability"], to: NSNull())
        let recorded = try self.field(openWinner(), gap, now: Self.recordedNow)
        let broken = H.history(recorded, cohort: [R.schauffele], selected: nil, chooserAvailable: true,
                               host: R.host(Self.recordedNow))
        XCTAssertEqual(bounds(broken.series[0]), [
            [x("2026-10-08T00:02:03.231914+00:00"), x("2026-10-08T00:11:13.058928+00:00")],
            [x("2026-10-08T00:23:03.133505+00:00"), x("2026-10-08T00:27:33.145591+00:00")],
        ], "the chart would join across it; the line breaks here")
    }

    // MARK: - Before

    func testBeforeFrameIsTheWeekBeforeNowWithTheLatestReadingHollow() throws {
        let host = R.host(Self.beforeNow)
        let field = try field(openWinner(), R.brennanHistory, now: Self.beforeNow)
        XCTAssertEqual(field.phase, .before)
        let input = H.history(field, cohort: [R.brennan], selected: nil, chooserAvailable: true, host: host)
        let brennan = input.series[0]
        // Three observations: under the futures chart's four-point floor there is
        // no cadence, so it draws them as one line, each observation marked.
        XCTAssertEqual(bounds(brennan), [[x("2026-10-05T01:08:38.821032+00:00"), x("2026-10-06T13:08:40.644152+00:00")]])
        XCTAssertEqual(brennan.runs[0].points.map(\.style), [.filled, .filled, .hollow])
        XCTAssertEqual(input.readout, .singleBefore(label: "Before start"))
        XCTAssertEqual(brennan.before,
                       .observation(pointID: pid(R.brennan, "2026-10-06T13:08:40.644152+00:00"), figure: "3%",
                                    provenance: "Recorded \(clock("2026-10-06T13:08:40.644152+00:00", host)) · DataGolf"))
        XCTAssertEqual(input.markKey.hollow, "Hollow · last chance before the start date")
        XCTAssertEqual(input.caption, "Before the start date · last 7 days")
        XCTAssertEqual(input.notes, ["Probabilities from the DataGolf model", "Gaps remain blank."])
    }

    // MARK: - Absence and selection

    func testNoHistoryResponseLeavesOnlyTheChartSlotUnavailable() throws {
        let winner = try R.market(R.baycurrentWinner)
        let input = H.unavailable(winner, cohort: [R.schauffele, R.clark], selected: R.schauffele,
                                  phase: .final, chooserAvailable: true)
        XCTAssertEqual(input.plotAbsence, FieldHistoryPlotAbsence10868(title: "History unavailable", words: nil))
        XCTAssertEqual(input.series.map(\.name), ["Xander Schauffele", "Wyndham Clark"])
        XCTAssertTrue(input.series.allSatisfy { $0.runs.isEmpty && $0.choose == nil })
        XCTAssertNil(input.expand)
        XCTAssertEqual(input.details?.isAvailable, false)
        XCTAssertEqual(input.summary, "History unavailable")
        XCTAssertTrue(input.notes.isEmpty, "no source is named for a chart that did not load")

        // Golfers with no served line in a loaded history: the plot's own absence.
        let host = R.host(Self.finalNow)
        let field = try field(R.baycurrentWinner, R.baycurrentHistory, now: Self.finalNow)
        let empty = H.history(field, cohort: [R.thorbjornsen, R.mitchell], selected: nil, chooserAvailable: false, host: host)
        XCTAssertEqual(empty.plotAbsence?.title, "No recorded history")
        XCTAssertNil(empty.moreOriginals, "no chooser, no chooser control")
    }

    func testSelectionNamesOnlyAGolferInTheChart() throws {
        let host = R.host(Self.finalNow)
        let field = try field(R.baycurrentWinner, R.baycurrentHistory, now: Self.finalNow)
        XCTAssertEqual(H.history(field, cohort: [R.clark], selected: R.brennan, chooserAvailable: true, host: host).selection,
                       .unavailable(words: "The selected golfer isn’t in this chart."))
        XCTAssertEqual(H.history(field, cohort: [R.clark], selected: nil, chooserAvailable: true, host: host).selection, .none)
        // A repeated or unknown cohort id is drawn once, or not at all.
        let input = H.history(field, cohort: [R.clark, R.clark, 1], selected: nil, chooserAvailable: true, host: host)
        XCTAssertEqual(input.series.map(\.name), ["Wyndham Clark"])
    }

    // MARK: - Readings

    func testAPreStartPriceIsNeverTheRecordedEstimateAndAnOpeningIsNeverAReading() throws {
        // CONSTRUCTED: India read at 2026-10-15T06:00Z, after its listed start
        // (served `status` "open"; every price stamped Oct 12).
        let field = try field(R.indiaWin, nil, now: "2026-10-15T06:00:00Z")
        XCTAssertEqual(field.phase, .recorded)
        let before = try XCTUnwrap(field.before(R.rory))
        XCTAssertEqual(before.probability, 0.1271)
        XCTAssertEqual(before.date, "2026-10-12T23:11:05.501054+00:00".asDate)
        XCTAssertEqual(before.kind, .price(renderedPercent: futuresDetailRenderedPercents(field.market.outcomes)[R.rory]))
        XCTAssertEqual(H.figure(before), "13%")
        XCTAssertNil(field.later(R.rory), "stamped before the start: never the recorded estimate")
        XCTAssertNil(field.before(R.noren), "no price; the untimed 0.0283 opening is never read")
        XCTAssertEqual(H.figure(try XCTUnwrap(field.before(R.jaglan))), "<1%")

        // Before the start, the same price is the before reading.
        let early = try self.field(R.indiaWin, nil, now: "2026-10-12T23:28:52Z")
        XCTAssertEqual(early.before(R.rory)?.probability, 0.1271)
        XCTAssertNil(early.later(R.rory), "a later reading exists only while recorded")
    }

    // MARK: - The approved Auto / Full scale (Design 2026-10-31, `chartCeiling`)

    private func plottedPeak(_ input: FieldHistoryInput10868) -> Double {
        input.series.flatMap { $0.runs.flatMap { $0.points.map(\.probability) } }.max() ?? 0
    }

    func testAutoIsTheFirstRungAboveThePeakWithFourPercentHeadroom() {
        XCTAssertEqual(H.ceiling(peak: 0, full: false), 0.025)
        XCTAssertEqual(H.ceiling(peak: 0.02, full: false), 0.025)    // 0.0208
        XCTAssertEqual(H.ceiling(peak: 0.0241, full: false), 0.05)   // 0.025064 is past 2.5%
        // The 4% boundary at 10%: 0.096 × 1.04 = 0.09984 fits; 0.0962 × 1.04 = 0.100048 does not.
        XCTAssertEqual(H.ceiling(peak: 0.096, full: false), 0.1)
        XCTAssertEqual(H.ceiling(peak: 0.0962, full: false), 0.15)
        XCTAssertEqual(H.ceiling(peak: 0.76, full: false), 0.8)      // 0.7904
        XCTAssertEqual(H.ceiling(peak: 0.77, full: false), 1)        // 0.8008 is past 80%
        XCTAssertEqual(H.ceiling(peak: 0.97, full: false), 1, "no rung above, so the whole range")
        for peak in [0, 0.02, 0.5, 1.0] {
            XCTAssertEqual(H.ceiling(peak: peak, full: true), 1, "Full is always 0–100%")
        }
    }

    func testEveryTickLabelIsExactlyItsValue() {
        XCTAssertEqual(H.tickValues(ceiling: 0.025), [0, 0.01, 0.02], "1.25% and 2.5% would print rounded")
        XCTAssertEqual(H.tickValues(ceiling: 0.05), [0, 0.05])
        XCTAssertEqual(H.tickValues(ceiling: 0.1), [0, 0.05, 0.1])
        XCTAssertEqual(H.tickValues(ceiling: 0.15), [0, 0.15])
        XCTAssertEqual(H.tickValues(ceiling: 1), [0, 0.5, 1])
        XCTAssertEqual(H.yTicks(ceiling: 0.025).map(\.lines), [["0%"], ["1%"], ["2%"]])
        XCTAssertEqual(H.scaleAction(ceiling: 0.025, full: false).label, "Auto scale · 0–2.5%", "never rounded to 3%")
        XCTAssertEqual(H.scaleAction(ceiling: 0.1, full: false).label, "Auto scale · 0–10%")
        XCTAssertEqual(H.scaleAction(ceiling: 1, full: true).label, "Full scale · 0–100%")
        XCTAssertEqual(H.scaleAction(ceiling: 0.1, full: false).spokenLabel, "Show full zero to 100 percent scale")
        XCTAssertEqual(H.scaleAction(ceiling: 1, full: true).spokenLabel, "Use automatic probability scale")
        XCTAssertEqual(H.scaleAction(ceiling: 1, full: true).id, H.scaleActionID)
    }

    func testAutoKeepsEveryPlottedPointAndFullChangesOnlyTheScale() throws {
        let host = R.host(Self.recordedNow)
        let field = try field(openWinner(), R.baycurrentHistory, now: Self.recordedNow)
        let cohort = [R.schauffele, R.clark, R.morikawa]
        let auto = H.history(field, cohort: cohort, selected: R.schauffele, chooserAvailable: true, host: host)
        let full = H.history(field, cohort: cohort, selected: R.schauffele, chooserAvailable: true, full: true, host: host)
        XCTAssertGreaterThanOrEqual(auto.ceiling, plottedPeak(auto), "no point is clipped or clamped")
        XCTAssertEqual(auto.ceiling, H.ceiling(peak: plottedPeak(auto), full: false))
        XCTAssertEqual(full.ceiling, 1)
        XCTAssertEqual(full.scale?.label, "Full scale · 0–100%")
        // Same points, runs, gaps, times, cohort, selection and readouts either way.
        XCTAssertEqual(auto.series, full.series)
        XCTAssertEqual(auto.domain, full.domain)
        XCTAssertEqual(auto.xTicks, full.xTicks)
        XCTAssertEqual(auto.selection, full.selection)
        XCTAssertEqual(auto.readout, full.readout)
        XCTAssertEqual(auto.notes, full.notes)
    }

    func testLowPreTournamentChancesGetALowCeiling() throws {
        let host = R.host(Self.beforeNow)
        let field = try field(openWinner(), R.brennanHistory, now: Self.beforeNow)
        let input = H.history(field, cohort: [R.brennan], selected: R.brennan, chooserAvailable: true, host: host)
        // Brennan's week before the start sits at 2.6–4.3%: the 5% rung, not a flat line at the bottom of 0–100%.
        XCTAssertEqual(input.ceiling, 0.05)
        XCTAssertEqual(input.scale?.label, "Auto scale · 0–5%")
        XCTAssertGreaterThanOrEqual(input.ceiling, plottedPeak(input))
    }

    func testTheCeilingFollowsTheDrawnGolfers() throws {
        let host = R.host(Self.recordedNow)
        // CONSTRUCTED: Clark's 00:27:33 reading set to 0.2 (one key); every other row as served.
        let edited = try R.edited(R.baycurrentHistory, ["outcomes", 0, "history", 6, "probability"], to: 0.2)
        let field = try field(openWinner(), edited, now: Self.recordedNow)
        let withClark = H.history(field, cohort: [R.schauffele, R.clark], selected: nil, chooserAvailable: true, host: host)
        let without = H.history(field, cohort: [R.schauffele, R.morikawa], selected: nil, chooserAvailable: true, host: host)
        XCTAssertEqual(withClark.ceiling, 0.25, "0.2 × 1.04 = 0.208")
        XCTAssertEqual(without.ceiling, 0.1)
    }

    func testAPeakNearCertaintyUsesTheWholeRangeOnAuto() throws {
        let host = R.host(Self.finalNow)
        let field = try field(R.baycurrentWinner, R.brennanHistory, now: Self.finalNow)
        let input = H.history(field, cohort: [R.brennan], selected: R.brennan, chooserAvailable: true, host: host)
        XCTAssertEqual(input.ceiling, 1, "Brennan's drawn 1.0 needs the whole range")
        XCTAssertEqual(input.scale?.label, "Auto scale · 0–100%")
    }

    func testAnotherMarketsHistoryIsRefusedEvenWhenOutcomeIdsOverlap() throws {
        let host = R.host(Self.recordedNow)
        // CONSTRUCTED: the same history body with `market_id` changed (one key); outcome ids still overlap.
        let foreign = try R.edited(R.baycurrentHistory, ["market_id"], to: 64266834)
        let refused = try field(openWinner(), foreign, now: Self.recordedNow)
        let accepted = try field(openWinner(), R.baycurrentHistory, now: Self.recordedNow)
        XCTAssertNil(refused.entries(R.schauffele))
        XCTAssertNotNil(accepted.entries(R.schauffele))
        let input = H.history(refused, cohort: [R.schauffele, R.clark], selected: nil, chooserAvailable: true, host: host)
        XCTAssertTrue(input.series.allSatisfy { $0.runs.isEmpty }, "no foreign line is drawn")
        XCTAssertEqual(input.plotAbsence?.title, "No recorded history")
        XCTAssertNil(input.scale, "no scale over an empty plot")
        // The detail's own price stays independently governed: stamped after this now, it is not read.
        XCTAssertNil(refused.before(R.schauffele))
    }
}
