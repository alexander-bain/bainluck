import SwiftUI
import XCTest
@testable import Bain_Luck

/// #10868 — golf finish expectations as a stateless presentation leaf.
///
/// The view is SwiftUI and is not rasterised here. What is asserted is the
/// rules it defers to: the fixed four-slot order, the layout chosen for each
/// phase, which observation a bar and a hollow dot read, the selected pair,
/// the action each control carries, the plot geometry, the narrow/AX column
/// plan and the spoken text.
///
/// ARCHIVED raw values (probabilities, results, positions) come from the
/// retained Baycurrent Classic records, `datagolf:pga:527`:
/// `golf-native-ready-composition-20261026/support/finish-expectations-oracle.json`
/// (sha256 2878b5ca…0796) cases 4 (Xander Schauffele, recorded through
/// 2026-10-08T02:01:32Z), 95 (Michael Brennan, final, position 1), 212/215
/// (Zach Bauchou, recorded / final, position T9) and 1055 (Kihei Akina, final,
/// no position). Scores −16 / −12 are from `support/native/golf-journey.json`
/// `final.players`. The display strings, dates and source text are the
/// owner-resolved inputs this leaf expects; the visible ones match the approved
/// reference frames, the rest are CONSTRUCTED stand-ins. Zero, partial,
/// malformed, duplicate-id and long-label inputs are CONSTRUCTED.
final class GolfFinishExpectationPresentation10868Tests: XCTestCase {

    // MARK: Fixtures

    private static let beforeDetail = "recorded Oct 6, 6:08 AM PT · DataGolf consensus"
    private static let recordedDetail = "recorded Oct 7, 7:01 PM PT · DataGolf consensus"
    private static let unknown = GolfFinishResult10868(text: "Unknown", mark: .unknown)

    private static func obs(_ probability: Double, _ text: String, _ detail: String = beforeDetail) -> GolfFinishObservation10868 {
        GolfFinishObservation10868(probability: probability, text: text, accessibilityDetail: detail)
    }

    private static func slot(
        _ selection: String,
        _ name: String,
        before: GolfFinishObservation10868? = nil,
        recorded: GolfFinishObservation10868? = nil,
        actual: GolfFinishResult10868 = unknown
    ) -> GolfFinishSlot10868 {
        GolfFinishSlot10868(
            selection: selection,
            name: name,
            color: .blue,
            before: before,
            recorded: recorded,
            beforeMissing: "Not recorded before tournament",
            recordedMissing: "Not recorded during play",
            actual: actual
        )
    }

    private static func input(
        _ phase: GolfFinishPhase10868,
        _ slots: [GolfFinishSlot10868],
        selected: String? = nil,
        golferName: String? = nil,
        actualSummary: String? = nil
    ) -> GolfFinishExpectationInput10868 {
        GolfFinishExpectationInput10868(
            win: slots[0], top5: slots[1], top10: slots[2], top20: slots[3],
            phase: phase,
            title: nil,
            golferName: golferName,
            context: nil,
            actualSummary: actualSummary,
            selected: selected
        )
    }

    /// Oracle case 4. Win 8.7% → 14.2% is the approved recorded frame.
    private static var xanderRecorded: GolfFinishExpectationInput10868 {
        input(.recorded, [
            slot("64266833", "Win",
                 before: obs(0.086583, "8.7%"), recorded: obs(0.142239, "14.2%", recordedDetail)),
            slot("64266834", "Top 5",
                 before: obs(0.285359, "28.5%"), recorded: obs(0.4312, "43.1%", recordedDetail)),
            slot("64266835", "Top 10",
                 before: obs(0.440191, "44%"), recorded: obs(0.60332, "60.3%", recordedDetail)),
            slot("64266836", "Top 20",
                 before: obs(0.644658, "64.5%"), recorded: obs(0.78904, "78.9%", recordedDetail)),
        ], selected: "64266833", golferName: "Xander Schauffele")
    }

    /// Oracle case 95.
    private static var brennanFinal: GolfFinishExpectationInput10868 {
        let won = GolfFinishResult10868(text: "Won", mark: .success)
        let inside = GolfFinishResult10868(text: "Inside", mark: .success)
        return input(.final, [
            slot("64266833", "Win", before: obs(0.026017, "2.6%"), actual: won),
            slot("64266834", "Top 5", before: obs(0.11956, "12%"), actual: inside),
            slot("64266835", "Top 10", before: obs(0.225636, "22.6%"), actual: inside),
            slot("64266836", "Top 20", before: obs(0.411461, "41.1%"), actual: inside),
        ], golferName: "Michael Brennan", actualSummary: "Won · −16")
    }

    /// Oracle case 215: no baselines, known T9.
    private static var bauchouFinal: GolfFinishExpectationInput10868 {
        input(.final, [
            slot("bauchou.win", "Win", actual: .init(text: "Not won", mark: .failure)),
            slot("bauchou.top5", "Top 5", actual: .init(text: "Outside", mark: .failure)),
            slot("bauchou.top10", "Top 10", actual: .init(text: "Inside", mark: .success)),
            slot("bauchou.top20", "Top 20", actual: .init(text: "Inside", mark: .success)),
        ], golferName: "Zach Bauchou", actualSummary: "T9 · −12")
    }

    /// Oracle case 1055: no baselines, no result.
    private static var akinaFinal: GolfFinishExpectationInput10868 {
        input(.final, [
            slot("akina.win", "Win"), slot("akina.top5", "Top 5"),
            slot("akina.top10", "Top 10"), slot("akina.top20", "Top 20"),
        ], golferName: "Kihei Akina")
    }

    // MARK: Four fixed slots

    func testSlotsAreTheFourNamedFinishesInFixedOrder() {
        // CONSTRUCTED names that would sort differently, to prove nothing sorts.
        let input = Self.input(.before, [
            Self.slot("z", "Win", before: Self.obs(0.9, "90%")),
            Self.slot("a", "Top 5", before: Self.obs(0.1, "10%")),
            Self.slot("m", "Top 10"),
            Self.slot("b", "Top 20", before: Self.obs(0.5, "50%")),
        ])
        XCTAssertEqual(input.slots.map(\.selection), ["z", "a", "m", "b"])
        XCTAssertEqual(input.slots.map(\.name), ["Win", "Top 5", "Top 10", "Top 20"])
        XCTAssertEqual(input.slots, [input.win, input.top5, input.top10, input.top20])
    }

    // MARK: Phase decisions

    func testBeforePhaseDrawsOnlyPreTournamentReadings() {
        let base = Self.xanderRecorded
        let before = Self.input(.before, base.slots, selected: "64266833")
        XCTAssertEqual(before.layout, .bars)
        for slot in before.slots {
            XCTAssertEqual(before.plotted(slot), slot.before)
            XCTAssertNil(before.baseline(slot), "no hollow dot without a recorded bar")
        }
        XCTAssertNil(before.selectedSlot, "no recorded comparison before play")
        XCTAssertFalse(before.accessibilityValue(for: before.win).contains("Recorded estimate"))
    }

    func testRecordedPhasePlotsRecordedBarsWithBeforeDots() {
        let input = Self.xanderRecorded
        XCTAssertEqual(input.layout, .bars)
        XCTAssertEqual(input.slots.map { input.plotted($0)?.probability }, [0.142239, 0.4312, 0.60332, 0.78904])
        XCTAssertEqual(input.slots.map { input.baseline($0)?.probability }, [0.086583, 0.285359, 0.440191, 0.644658])
    }

    func testMissingRecordedIsNeverDrawnAsZero() {
        let input = Self.input(.recorded, [
            Self.slot("w", "Win", before: Self.obs(0.05, "5%")),
            Self.slot("t5", "Top 5", before: Self.obs(0.2, "20%"), recorded: Self.obs(0.3, "30%", Self.recordedDetail)),
            Self.slot("t10", "Top 10"),
            Self.slot("t20", "Top 20"),
        ])
        XCTAssertEqual(input.layout, .bars)
        XCTAssertNil(input.plotted(input.win), "absent, not a 0% bar")
        XCTAssertEqual(input.recordedReading(input.win), .missing("Not recorded during play"))
        XCTAssertEqual(input.baseline(input.win)?.text, "5%", "the baseline still shows")
    }

    func testRecordedWithNothingAtAllShowsExplanationAndFinishNames() {
        // Oracle case 212: Bauchou during play, every reading absent.
        let input = Self.input(.recorded, Self.bauchouFinal.slots)
        XCTAssertEqual(input.layout, .missingEstimates)
        XCTAssertEqual(input.explanation, "No recorded finish estimates for this golfer at this moment.")
        XCTAssertEqual(input.action(for: input.top10, canSelect: true, canOpenDetails: true), .select("bauchou.top10"))
    }

    func testBeforeWithNoBaselinesShowsExplanationNotAnEmptyPlot() {
        let input = Self.input(.before, Self.akinaFinal.slots)
        XCTAssertEqual(input.layout, .missingEstimates)
        XCTAssertEqual(input.explanation, "Pre-tournament chances weren’t recorded.")
    }

    func testFinalWithEveryBaselineAbsentUsesResultTiles() {
        let input = Self.bauchouFinal
        XCTAssertEqual(input.layout, .resultTiles)
        XCTAssertEqual(input.explanation, "Pre-tournament chances weren’t recorded.")
        XCTAssertEqual(input.slots.map(\.actual.mark), [.failure, .failure, .success, .success])
        XCTAssertEqual(input.slots.map(\.actual.text), ["Not won", "Outside", "Inside", "Inside"])
        XCTAssertEqual(input.accessibilityHeader, "Zach Bauchou. T9 · −12")
    }

    func testGenuineZeroAndPartialBaselinesStayOnTheChart() {
        let zero = Self.input(.final, [
            Self.slot("w", "Win", before: Self.obs(0, "0%")),
            Self.slot("t5", "Top 5"), Self.slot("t10", "Top 10"), Self.slot("t20", "Top 20"),
        ])
        XCTAssertEqual(zero.layout, .bars)
        XCTAssertEqual(GolfFinishGeometry10868.markHeight(zero.plotted(zero.win)!.probability), 0,
                       "a real zero keeps its explicit zero mark")
        XCTAssertNil(zero.plotted(zero.top5))
        XCTAssertEqual(zero.explanation, "Bars show recorded pre-tournament chances.")

        let partial = Self.input(.final, [
            Self.slot("w", "Win"), Self.slot("t5", "Top 5"), Self.slot("t10", "Top 10"),
            Self.slot("t20", "Top 20", before: Self.obs(0.31, "31%")),
        ])
        XCTAssertEqual(partial.layout, .bars)
        XCTAssertEqual(partial.beforeReading(partial.win), .missing("Not recorded before tournament"))
    }

    func testUnknownActualStaysUnknownNeverALoss() {
        let input = Self.akinaFinal
        XCTAssertEqual(input.layout, .resultTiles)
        XCTAssertEqual(Set(input.slots.map(\.actual.mark)), [.unknown])
        XCTAssertEqual(input.accessibilityValue(for: input.win),
                       "Before tournament: Not recorded before tournament; Actual finish: Unknown")
        XCTAssertEqual(input.accessibilityHeader, "Kihei Akina", "no invented result summary")
    }

    // MARK: Selected pair

    func testSelectedPairReadsEachObservationIndependently() throws {
        let input = Self.xanderRecorded
        let selected = try XCTUnwrap(input.selectedSlot)
        XCTAssertEqual(selected.selection, "64266833")
        XCTAssertEqual(input.beforeReading(selected), .value("8.7%"))
        XCTAssertEqual(input.recordedReading(selected), .value("14.2%"))
        XCTAssertTrue(input.isSelected(input.win))
        XCTAssertFalse(input.isSelected(input.top5))
    }

    func testOneReadingMissingNeverBorrowsTheOther() {
        let beforeOnly = Self.input(.recorded, [
            Self.slot("w", "Win", before: Self.obs(0.04, "4%")),
            Self.slot("t5", "Top 5", recorded: Self.obs(0.22, "22%", Self.recordedDetail)),
            Self.slot("t10", "Top 10"), Self.slot("t20", "Top 20"),
        ], selected: "w")
        XCTAssertEqual(beforeOnly.beforeReading(beforeOnly.win), .value("4%"))
        XCTAssertEqual(beforeOnly.recordedReading(beforeOnly.win), .missing("Not recorded during play"))

        let recordedOnly = Self.input(.recorded, beforeOnly.slots, selected: "t5")
        XCTAssertEqual(recordedOnly.beforeReading(recordedOnly.top5), .missing("Not recorded before tournament"))
        XCTAssertEqual(recordedOnly.recordedReading(recordedOnly.top5), .value("22%"))
        XCTAssertNil(recordedOnly.baseline(recordedOnly.top5))
    }

    func testMissingUnknownOrAmbiguousSelectionGetsNoSubstitute() {
        let slots = Self.xanderRecorded.slots
        XCTAssertNil(Self.input(.recorded, slots, selected: nil).selectedSlot)
        XCTAssertNil(Self.input(.recorded, slots, selected: "64266899").selectedSlot)
        XCTAssertNil(Self.input(.final, slots, selected: "64266833").selectedSlot)

        // CONSTRUCTED duplicate ids.
        let duplicate = Self.input(.recorded, [
            Self.slot("same", "Win", recorded: Self.obs(0.1, "10%")),
            Self.slot("same", "Top 5", recorded: Self.obs(0.3, "30%")),
            Self.slot("t10", "Top 10"), Self.slot("t20", "Top 20"),
        ], selected: "same")
        XCTAssertNil(duplicate.selectedSlot)
        XCTAssertNil(duplicate.sourceAction(canOpenDetails: true))
    }

    // MARK: Actions

    func testActionsCarryTheExactSuppliedIdentityAndVanishWithoutCallbacks() {
        let id = " market:64266833|outcome:242242520 "
        let slots = [Self.slot(id, "Win", before: Self.obs(0.1, "10%"), recorded: Self.obs(0.2, "20%"))]
            + Self.xanderRecorded.slots.dropFirst()
        let recorded = Self.input(.recorded, slots, selected: id)
        XCTAssertEqual(recorded.action(for: recorded.win, canSelect: true, canOpenDetails: true), .select(id))
        XCTAssertNil(recorded.action(for: recorded.win, canSelect: false, canOpenDetails: true))
        XCTAssertEqual(recorded.sourceAction(canOpenDetails: true), .details(id))
        XCTAssertNil(recorded.sourceAction(canOpenDetails: false))

        let final = Self.input(.final, slots)
        XCTAssertEqual(final.action(for: final.win, canSelect: true, canOpenDetails: true), .details(id))
        XCTAssertNil(final.action(for: final.win, canSelect: true, canOpenDetails: false))

        var selected: [String] = []
        var details: [String] = []
        GolfFinishAction10868.select(id).perform(onSelectFinish: { selected.append($0) }, onDetails: { details.append($0) })
        GolfFinishAction10868.details(id).perform(onSelectFinish: { selected.append($0) }, onDetails: { details.append($0) })
        GolfFinishAction10868.details(id).perform(onSelectFinish: nil, onDetails: nil)
        XCTAssertEqual(selected, [id])
        XCTAssertEqual(details, [id])
    }

    func testFootnoteExplainsOverlapAndOnlyPromptsForActionsThatExist() {
        let recorded = Self.xanderRecorded
        XCTAssertEqual(recorded.footnote(canSelect: true, canOpenDetails: true),
                       "Finishes overlap; winning also counts as Top 5. Select a finish to compare its chances.")
        XCTAssertEqual(recorded.footnote(canSelect: false, canOpenDetails: false),
                       "Finishes overlap; winning also counts as Top 5.")
        XCTAssertEqual(Self.brennanFinal.footnote(canSelect: false, canOpenDetails: true),
                       "Actual finish is separate from each pre-tournament chance. Finishes overlap; winning also counts as Top 5. Tap a bar for its recorded time and source.")
        XCTAssertEqual(Self.bauchouFinal.footnote(canSelect: false, canOpenDetails: true),
                       "Actual finish is separate from each pre-tournament chance. Finishes overlap; winning also counts as Top 5. Tap a finish for details.")
        XCTAssertEqual(Self.bauchouFinal.footnote(canSelect: true, canOpenDetails: false),
                       "Actual finish is separate from each pre-tournament chance. Finishes overlap; winning also counts as Top 5.")
    }

    // MARK: Overlap, not normalization

    func testOverlappingFinishesAreNeverNormalized() {
        let brennan = Self.brennanFinal
        XCTAssertEqual(brennan.layout, .bars)
        XCTAssertEqual(brennan.slots.map { brennan.plotted($0)?.probability }, [0.026017, 0.11956, 0.225636, 0.411461])
        XCTAssertEqual(Set(brennan.slots.map(\.actual.mark)), [.success], "a winner is inside every finish")

        let xander = Self.xanderRecorded
        let heights = xander.slots.compactMap { xander.plotted($0).flatMap { GolfFinishGeometry10868.markHeight($0.probability) } }
        XCTAssertEqual(heights.count, 4)
        XCTAssertGreaterThan(heights.reduce(0, +), GolfFinishGeometry10868.plotHeight, "four overlapping chances, each on its own 0–100% scale")
    }

    // MARK: Geometry and layout plan

    func testPlotGeometryEndpointsAndMalformedInput() {
        XCTAssertEqual(GolfFinishGeometry10868.plotHeight, 188)
        XCTAssertEqual(GolfFinishGeometry10868.markHeight(0), 0)
        XCTAssertEqual(GolfFinishGeometry10868.markHeight(1), 188)
        XCTAssertEqual(GolfFinishGeometry10868.markHeight(0.5), 94)
        XCTAssertEqual(GolfFinishGeometry10868.markHeight(0.142239)!, 26.740932, accuracy: 0.0001)
        for bad: Double in [-0.0001, 1.0001, .nan, .infinity, -.infinity] {
            XCTAssertNil(GolfFinishGeometry10868.markHeight(bad), "\(bad) is omitted, not clipped")
        }

        // CONSTRUCTED malformed reading: the owner's figure is still a value, not "missing".
        let malformed = Self.input(.before, [
            Self.slot("w", "Win", before: Self.obs(.nan, "8.7%")),
            Self.slot("t5", "Top 5"), Self.slot("t10", "Top 10"), Self.slot("t20", "Top 20"),
        ])
        XCTAssertEqual(malformed.layout, .bars)
        XCTAssertEqual(malformed.beforeReading(malformed.win), .value("8.7%"))
    }

    func testNarrowAndAccessibilityLayoutsStackBarsAndTiles() {
        XCTAssertEqual(GolfFinishGeometry10868.columnCandidates(isAccessibilitySize: false), [4, 2, 1])
        XCTAssertEqual(GolfFinishGeometry10868.columnCandidates(isAccessibilitySize: true), [2, 1])
        XCTAssertEqual(GolfFinishGeometry10868.tileColumns(isAccessibilitySize: false), 2)
        XCTAssertEqual(GolfFinishGeometry10868.tileColumns(isAccessibilitySize: true), 1)

        let names = Self.xanderRecorded.slots.map(\.name)
        XCTAssertEqual(GolfFinishGeometry10868.groups(names, columns: 4), [["Win", "Top 5", "Top 10", "Top 20"]])
        XCTAssertEqual(GolfFinishGeometry10868.groups(names, columns: 2), [["Win", "Top 5"], ["Top 10", "Top 20"]])
        XCTAssertEqual(GolfFinishGeometry10868.groups(names, columns: 1), [["Win"], ["Top 5"], ["Top 10"], ["Top 20"]])
    }

    // MARK: Spoken text and ids

    func testVoiceOverNamesBothObservationsWithDateSourceAndQualifiers() {
        let input = Self.xanderRecorded
        XCTAssertEqual(input.accessibilityHeader, "Xander Schauffele")
        XCTAssertEqual(input.accessibilityValue(for: input.win),
                       "Before tournament: 8.7%, recorded Oct 6, 6:08 AM PT · DataGolf consensus; "
                       + "Recorded estimate: 14.2%, recorded Oct 7, 7:01 PM PT · DataGolf consensus")

        let brennan = Self.brennanFinal
        XCTAssertEqual(brennan.accessibilityValue(for: brennan.top20),
                       "Before tournament: 41.1%, recorded Oct 6, 6:08 AM PT · DataGolf consensus; Actual finish: Inside")
        XCTAssertEqual(brennan.accessibilityHeader, "Michael Brennan. Won · −16")

        let summaryBeforeFinal = Self.input(.recorded, input.slots, golferName: "Xander Schauffele", actualSummary: "Won · −16")
        XCTAssertEqual(summaryBeforeFinal.accessibilityHeader, "Xander Schauffele", "a result is never spoken before the final")
    }

    func testSuppliedTextIsKeptVerbatim() {
        // CONSTRUCTED long label and unusual figure strings.
        let long = "Top 5 (including ties, settled on the 72-hole leaderboard)"
        let input = Self.input(.recorded, [
            Self.slot("w", "Win", before: Self.obs(0.0004, "<0.1%"), recorded: Self.obs(0.9996, ">99.9%", "via a very long owner source line")),
            Self.slot("t5", long),
            Self.slot("t10", "Top 10"), Self.slot("t20", "Top 20"),
        ])
        XCTAssertEqual(input.top5.name, long)
        XCTAssertEqual(input.footnote(canSelect: false, canOpenDetails: false), "Finishes overlap; winning also counts as \(long).")
        XCTAssertEqual(input.accessibilityValue(for: input.win),
                       "Before tournament: <0.1%, recorded Oct 6, 6:08 AM PT · DataGolf consensus; Recorded estimate: >99.9%, via a very long owner source line")
    }

    func testAccessibilityIdentifiersCarryTheExactSelection() {
        XCTAssertEqual(GolfFinishAccessibilityID10868.bar("64266833"), "golfFinish10868.bar.64266833")
        XCTAssertEqual(GolfFinishAccessibilityID10868.finish("a b"), "golfFinish10868.finish.a b")
        XCTAssertEqual(GolfFinishAccessibilityID10868.result("bauchou.top10"), "golfFinish10868.result.bauchou.top10")
        XCTAssertEqual(GolfFinishAccessibilityID10868.source("64266833"), "golfFinish10868.source.64266833")
    }
}

// MARK: - Five finishes: the optional Make cut slot

/// The fifth finish rides the same slot, observation, result and action rules.
///
/// RETAINED records come from the DP World India Championship capture
/// (`datagolf:euro:2026140`, captured 2026-10-12T23:29:57Z, start 2026-10-15),
/// `shipping-adoption-20261027/GOLF-OUTLOOK-FIVE-FINISH-RETAINED-CASES.json`
/// (sha256 5ea50120…3f4a): every one of the 190 golfers and 950 original
/// records, one line each, in the packet's own golfer and finish order. Each
/// line is golfer, finish, owner selection id, original record id, stored
/// probability, untimed opening probability, the record's own stored update
/// clock and the packet's reference figure, all verbatim ("-" is null). The
/// figures were produced by the approved reference, never by this app.
///
/// That capture is pre-tournament only. Every recorded, final and result
/// input below is CONSTRUCTED, not real phase evidence. The stored update
/// clock is not a provider generation time, and the untimed opening is never
/// a baseline.
extension GolfFinishExpectationPresentation10868Tests {

    private static let fiveLabels = ["Win", "Top 5", "Top 10", "Top 20", "Make cut"]
    /// The packet's absence words for every missing record.
    private static let retainedMissingWords = "Unavailable"

    private static func retainedDetail(_ record: GolfFinishRetainedRecord10868) -> String {
        "stored update \(record.lastUpdated) · DataGolf model estimate"
    }

    private static func retainedGolfers() throws -> [[GolfFinishRetainedRecord10868]] {
        let records = try retainedTable.split(separator: "\n").map { line -> GolfFinishRetainedRecord10868 in
            let fields = line.split(separator: "\t", omittingEmptySubsequences: false).map(String.init)
            XCTAssertEqual(fields.count, 8, String(line))
            func number(_ field: String) throws -> Double? {
                if field == "-" { return nil }
                return try XCTUnwrap(Double(field), field)
            }
            return GolfFinishRetainedRecord10868(
                golfer: fields[0], label: fields[1], selection: fields[2], rawID: fields[3],
                probability: try number(fields[4]), opening: try number(fields[5]),
                lastUpdated: fields[6], figure: fields[7]
            )
        }
        XCTAssertEqual(records.count % 5, 0)
        // Each golfer's own five lines, as listed; checked by label and golfer, never paired across golfers.
        return GolfFinishGeometry10868.groups(records, columns: 5)
    }

    private static func retainedSlot(_ record: GolfFinishRetainedRecord10868) -> GolfFinishSlot10868 {
        GolfFinishSlot10868(
            selection: record.selection,
            name: record.label,
            color: .blue,
            before: record.probability.map { obs($0, record.figure, retainedDetail(record)) },
            recorded: nil,
            beforeMissing: retainedMissingWords,
            // CONSTRUCTED: the capture has no during-play reading.
            recordedMissing: "Not recorded during play",
            actual: unknown
        )
    }

    private static func fiveInput(
        _ phase: GolfFinishPhase10868,
        _ slots: [GolfFinishSlot10868],
        selected: String? = nil,
        golferName: String? = nil,
        actualSummary: String? = nil
    ) -> GolfFinishExpectationInput10868 {
        GolfFinishExpectationInput10868(
            win: slots[0], top5: slots[1], top10: slots[2], top20: slots[3],
            phase: phase,
            title: nil,
            golferName: golferName,
            context: nil,
            actualSummary: actualSummary,
            selected: selected,
            makeCut: slots[4]
        )
    }

    private static func retainedInput(
        _ golfer: [GolfFinishRetainedRecord10868],
        _ phase: GolfFinishPhase10868 = .before
    ) -> GolfFinishExpectationInput10868 {
        fiveInput(phase, golfer.map(retainedSlot), golferName: golfer[0].golfer)
    }

    private static func retainedGolfer(_ name: String) throws -> [GolfFinishRetainedRecord10868] {
        try XCTUnwrap(retainedGolfers().first { $0[0].golfer == name }, name)
    }

    private static func withSlot(
        _ slot: GolfFinishSlot10868,
        before: GolfFinishObservation10868?? = .none,
        recorded: GolfFinishObservation10868? = nil,
        actual: GolfFinishResult10868? = nil,
        selection: String? = nil
    ) -> GolfFinishSlot10868 {
        GolfFinishSlot10868(
            selection: selection ?? slot.selection,
            name: slot.name,
            color: slot.color,
            before: before ?? slot.before,
            recorded: recorded ?? slot.recorded,
            beforeMissing: slot.beforeMissing,
            recordedMissing: slot.recordedMissing,
            actual: actual ?? slot.actual
        )
    }

    // MARK: Retained packet

    func testRetainedPacketKeepsEveryGolferAndOriginalRecord() throws {
        let golfers = try Self.retainedGolfers()
        XCTAssertEqual(golfers.count, 190)
        XCTAssertEqual(Set(golfers.map { $0[0].golfer }).count, 190)
        let records = golfers.flatMap { $0 }
        XCTAssertEqual(records.count, 950)
        XCTAssertEqual(Set(records.map(\.selection)).count, 950)
        XCTAssertEqual(Set(records.map(\.rawID)).count, 950)
        for golfer in golfers {
            XCTAssertEqual(golfer.map(\.label), Self.fiveLabels, golfer[0].golfer)
            XCTAssertEqual(Set(golfer.map(\.golfer)).count, 1, "each record is the golfer's own")
            for record in golfer {
                XCTAssertTrue(record.selection.hasSuffix("|\(record.rawID)"), record.selection)
            }
        }
        for label in Self.fiveLabels {
            let finish = records.filter { $0.label == label }
            XCTAssertEqual(finish.filter { $0.probability != nil }.count, 144, label)
            XCTAssertEqual(finish.filter { $0.probability == nil }.count, 46, label)
            XCTAssertEqual(finish.filter { $0.probability == 0 }.count, label == "Win" ? 2 : 0, label)
        }
        let missing = records.filter { $0.probability == nil }
        XCTAssertEqual(Set(missing.map(\.figure)), [Self.retainedMissingWords])
        XCTAssertEqual(missing.filter { $0.opening != nil }.count, 230, "an untimed opening sits beside a missing estimate")
    }

    func testEveryRetainedGolferShowsAllFiveFinishesWithItsOwnFiguresIdsAndClocks() throws {
        var plotted: [String: Int] = [:]
        var absent: [String: Int] = [:]
        for golfer in try Self.retainedGolfers() {
            let input = Self.retainedInput(golfer)
            let name = golfer[0].golfer
            XCTAssertEqual(input.slots.map(\.selection), golfer.map(\.selection), name)
            XCTAssertEqual(input.slots.map(\.name), Self.fiveLabels, name)
            XCTAssertEqual(input.makeCut?.selection, golfer[4].selection, name)
            XCTAssertEqual(input.layout, golfer.allSatisfy { $0.probability == nil } ? .missingEstimates : .bars, name)
            for (slot, record) in zip(input.slots, golfer) {
                XCTAssertEqual(input.action(for: slot, canSelect: true, canOpenDetails: true), .details(record.selection))
                XCTAssertNil(input.action(for: slot, canSelect: true, canOpenDetails: false))
                XCTAssertNil(input.baseline(slot), "no hollow dot before play")
                if let probability = record.probability {
                    plotted[record.label, default: 0] += 1
                    XCTAssertEqual(input.plotted(slot)?.probability, probability, record.selection)
                    XCTAssertNotNil(GolfFinishGeometry10868.markHeight(probability), record.selection)
                    XCTAssertEqual(input.beforeReading(slot), .value(record.figure), record.selection)
                    XCTAssertEqual(input.accessibilityValue(for: slot),
                                   "Before tournament: \(record.figure), \(Self.retainedDetail(record))")
                } else {
                    absent[record.label, default: 0] += 1
                    XCTAssertNil(input.plotted(slot), "missing is never a zero bar: \(record.selection)")
                    XCTAssertEqual(input.beforeReading(slot), .missing(Self.retainedMissingWords))
                    XCTAssertEqual(input.accessibilityValue(for: slot), "Before tournament: Unavailable")
                }
            }
        }
        XCTAssertEqual(plotted, Dictionary(uniqueKeysWithValues: Self.fiveLabels.map { ($0, 144) }))
        XCTAssertEqual(absent, Dictionary(uniqueKeysWithValues: Self.fiveLabels.map { ($0, 46) }))
    }

    func testRoryKeepsFiveIndependentEstimatesIdsAndClocks() throws {
        let rory = try Self.retainedGolfer("Rory McIlroy")
        let input = Self.retainedInput(rory)
        XCTAssertEqual(input.slots.compactMap { input.plotted($0)?.text }, ["12.7%", "35.2%", "49.9%", "66.5%", "89.6%"])
        XCTAssertEqual(input.slots.compactMap { input.plotted($0)?.probability }, [0.1271, 0.351696, 0.498592, 0.665303, 0.896383])
        XCTAssertEqual(input.slots.map(\.selection), [
            "constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|246352440",
            "constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|246352498",
            "constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|246352556",
            "constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|246352614",
            "constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|246352672",
        ])
        XCTAssertEqual(Set(rory.map(\.lastUpdated)).count, 5, "each finish carries its own clock")
        let makeCut = try XCTUnwrap(input.makeCut)
        XCTAssertEqual(input.accessibilityValue(for: makeCut),
                       "Before tournament: 89.6%, stored update 2026-10-12T23:11:10.724619+00:00 · DataGolf model estimate")

        // CONSTRUCTED recorded phase: every one of the five selects its own exact id.
        let recorded = Self.retainedInput(rory, .recorded)
        XCTAssertEqual(recorded.slots.compactMap { recorded.action(for: $0, canSelect: true, canOpenDetails: true) },
                       rory.map { GolfFinishAction10868.select($0.selection) })
    }

    func testGenuineZeroAndTinyFiguresStayVerbatim() throws {
        let records = try Self.retainedGolfers().flatMap { $0 }
        let zeros = records.filter { $0.probability == 0 }
        XCTAssertEqual(zeros.map(\.golfer), ["Shubham Jaglan", "Subash Tamang"])
        for zero in zeros {
            let golfer = try Self.retainedGolfer(zero.golfer)
            let input = Self.retainedInput(golfer)
            XCTAssertEqual(input.layout, .bars)
            let win = try XCTUnwrap(input.plotted(input.win))
            XCTAssertEqual(win.probability, 0)
            XCTAssertEqual(GolfFinishGeometry10868.markHeight(win.probability), 0, "a real zero keeps its explicit zero mark")
            XCTAssertEqual(input.beforeReading(input.win), .value("0%"))
        }
        let tiny = try XCTUnwrap(records.first { $0.figure == "<0.1%" })
        let tinyGolfer = try Self.retainedGolfer(tiny.golfer)
        let input = Self.retainedInput(tinyGolfer)
        let slot = try XCTUnwrap(input.slots.first { $0.selection == tiny.selection })
        XCTAssertEqual(input.beforeReading(slot), .value("<0.1%"))
    }

    // MARK: Compatibility

    func testOmittedMakeCutIsExactlyTheOriginalFourFinishes() {
        let four = Self.xanderRecorded
        XCTAssertNil(four.makeCut)
        XCTAssertEqual(four.slots, [four.win, four.top5, four.top10, four.top20])
        let explicitNil = GolfFinishExpectationInput10868(
            win: four.win, top5: four.top5, top10: four.top10, top20: four.top20,
            phase: four.phase, title: four.title, golferName: four.golferName,
            context: four.context, actualSummary: four.actualSummary, selected: four.selected,
            makeCut: nil
        )
        XCTAssertEqual(explicitNil, four)

        // CONSTRUCTED fifth finish on the same four.
        let cut = Self.slot("xander.makeCut", "Make cut",
                            before: Self.obs(0.93, "93%"), recorded: Self.obs(0.97, "97%", Self.recordedDetail))
        let five = Self.fiveInput(.recorded, four.slots + [cut], selected: four.selected, golferName: four.golferName)
        XCTAssertNotEqual(five, four)
        XCTAssertEqual(Array(five.slots.prefix(4)), four.slots)
        XCTAssertEqual(five.slots.last, cut)
        XCTAssertEqual(five.layout, four.layout)
        XCTAssertEqual(five.selectedSlot, four.selectedSlot)
        XCTAssertEqual(five.accessibilityHeader, four.accessibilityHeader)
        for (canSelect, canOpenDetails) in [(true, true), (false, true), (true, false), (false, false)] {
            XCTAssertEqual(five.footnote(canSelect: canSelect, canOpenDetails: canOpenDetails),
                           four.footnote(canSelect: canSelect, canOpenDetails: canOpenDetails))
            XCTAssertEqual(five.sourceAction(canOpenDetails: canOpenDetails), four.sourceAction(canOpenDetails: canOpenDetails))
            for slot in four.slots {
                XCTAssertEqual(five.action(for: slot, canSelect: canSelect, canOpenDetails: canOpenDetails),
                               four.action(for: slot, canSelect: canSelect, canOpenDetails: canOpenDetails))
            }
        }
        for slot in four.slots {
            XCTAssertEqual(five.accessibilityValue(for: slot), four.accessibilityValue(for: slot))
        }
        XCTAssertEqual(GolfFinishGeometry10868.columnCandidates(slotCount: four.slots.count, isAccessibilitySize: false), [4, 2, 1])
        XCTAssertEqual(GolfFinishGeometry10868.columnCandidates(slotCount: four.slots.count, isAccessibilitySize: true), [2, 1])
    }

    // MARK: Fifth slot independence

    func testMissingMakeCutStaysVisibleAndIndependentOfTheOtherFinishes() throws {
        let rory = try Self.retainedGolfer("Rory McIlroy").map(Self.retainedSlot)
        // CONSTRUCTED: the packet never misses Make cut alone.
        let missingCut = Self.withSlot(rory[4], before: .some(nil), selection: "constructed:make-cut-missing")
        let input = Self.fiveInput(.before, Array(rory.prefix(4)) + [missingCut], golferName: "Rory McIlroy")
        XCTAssertEqual(input.slots.count, 5)
        XCTAssertEqual(input.layout, .bars)
        XCTAssertNil(input.plotted(missingCut), "absent, not a 0% bar")
        XCTAssertEqual(input.beforeReading(missingCut), .missing(Self.retainedMissingWords))
        XCTAssertEqual(input.action(for: missingCut, canSelect: false, canOpenDetails: true), .details("constructed:make-cut-missing"))
        XCTAssertEqual(input.slots.prefix(4).compactMap { input.plotted($0)?.text }, ["12.7%", "35.2%", "49.9%", "66.5%"])

        // The reverse: four missing (retained) and a CONSTRUCTED Make cut keep the chart.
        let noren = try Self.retainedGolfer("Alex Noren").map(Self.retainedSlot)
        let cutOnly = Self.withSlot(noren[4], before: .some(Self.obs(0.62, "62%")))
        let reverse = Self.fiveInput(.before, Array(noren.prefix(4)) + [cutOnly])
        XCTAssertEqual(reverse.layout, .bars)
        XCTAssertEqual(reverse.slots.compactMap { reverse.plotted($0)?.text }, ["62%"])
        XCTAssertEqual(reverse.slots.prefix(4).map { reverse.beforeReading($0) },
                       Array(repeating: GolfFinishReading10868.missing(Self.retainedMissingWords), count: 4))
    }

    func testSelectedMakeCutComparisonAndSourceActionCarryItsOwnId() throws {
        let rory = try Self.retainedGolfer("Rory McIlroy")
        let slots = rory.map(Self.retainedSlot)
        let id = rory[4].selection
        // CONSTRUCTED recorded reading beside the retained pre-tournament one.
        let cut = Self.withSlot(slots[4], recorded: Self.obs(0.91, "91%", "constructed recorded · DataGolf model estimate"))
        let input = Self.fiveInput(.recorded, Array(slots.prefix(4)) + [cut], selected: id, golferName: "Rory McIlroy")
        let selected = try XCTUnwrap(input.selectedSlot)
        XCTAssertEqual(selected, cut)
        XCTAssertEqual(input.slots.map(input.isSelected), [false, false, false, false, true])
        XCTAssertEqual(input.beforeReading(selected), .value("89.6%"))
        XCTAssertEqual(input.recordedReading(selected), .value("91%"))
        XCTAssertEqual(input.baseline(selected)?.probability, 0.896383)
        XCTAssertEqual(input.action(for: selected, canSelect: true, canOpenDetails: true), .select(id))
        XCTAssertEqual(input.sourceAction(canOpenDetails: true), .details(id))
        XCTAssertNil(input.sourceAction(canOpenDetails: false))
        XCTAssertEqual(input.accessibilityValue(for: selected),
                       "Before tournament: 89.6%, stored update 2026-10-12T23:11:10.724619+00:00 · DataGolf model estimate; "
                       + "Recorded estimate: 91%, constructed recorded · DataGolf model estimate")

        var picked: [String] = []
        var opened: [String] = []
        input.action(for: selected, canSelect: true, canOpenDetails: true)?
            .perform(onSelectFinish: { picked.append($0) }, onDetails: { opened.append($0) })
        input.sourceAction(canOpenDetails: true)?
            .perform(onSelectFinish: { picked.append($0) }, onDetails: { opened.append($0) })
        XCTAssertEqual(picked, [id])
        XCTAssertEqual(opened, [id])
    }

    func testAllMissingAndFinalWithoutBaselinesKeepTheFifthSlot() throws {
        let noren = try Self.retainedGolfer("Alex Noren")
        let before = Self.retainedInput(noren)
        XCTAssertEqual(before.layout, .missingEstimates)
        XCTAssertEqual(before.explanation, "Pre-tournament chances weren’t recorded.")
        XCTAssertEqual(before.slots.map(\.name), Self.fiveLabels)
        XCTAssertEqual(before.action(for: before.slots[4], canSelect: true, canOpenDetails: true), .details(noren[4].selection))

        // CONSTRUCTED phases on the same retained ids.
        let recorded = Self.retainedInput(noren, .recorded)
        XCTAssertEqual(recorded.layout, .missingEstimates)
        XCTAssertEqual(recorded.action(for: recorded.slots[4], canSelect: true, canOpenDetails: true), .select(noren[4].selection))

        let results: [GolfFinishResult10868] = [
            .init(text: "Not won", mark: .failure), .init(text: "Outside", mark: .failure),
            .init(text: "Outside", mark: .failure), .init(text: "Inside", mark: .success),
            .init(text: "Made cut", mark: .success),
        ]
        let finalSlots = zip(noren.map(Self.retainedSlot), results).map { Self.withSlot($0, actual: $1) }
        let final = Self.fiveInput(.final, finalSlots, golferName: "Alex Noren", actualSummary: "T14 · −6")
        XCTAssertEqual(final.layout, .resultTiles)
        XCTAssertEqual(final.explanation, "Pre-tournament chances weren’t recorded.")
        XCTAssertEqual(final.slots.map(\.actual.text), ["Not won", "Outside", "Outside", "Inside", "Made cut"])
        XCTAssertEqual(final.action(for: final.slots[4], canSelect: true, canOpenDetails: true), .details(noren[4].selection))
        XCTAssertEqual(final.footnote(canSelect: false, canOpenDetails: true),
                       "Actual finish is separate from each pre-tournament chance. Finishes overlap; winning also counts as Top 5. Tap a finish for details.")
        XCTAssertEqual(final.accessibilityValue(for: final.slots[4]), "Before tournament: Unavailable; Actual finish: Made cut")
    }

    // MARK: Phases

    func testMakeCutPhasesNeverLeakLaterReadingsOrResults() throws {
        let rory = try Self.retainedGolfer("Rory McIlroy")
        let slots = rory.map(Self.retainedSlot)
        // CONSTRUCTED later reading (a genuine 100%) and result on the retained pre-tournament slot.
        let cut = Self.withSlot(slots[4],
                                recorded: Self.obs(1, "100%", "constructed recorded · DataGolf model estimate"),
                                actual: GolfFinishResult10868(text: "Made cut", mark: .success))
        let all = Array(slots.prefix(4)) + [cut]
        let detail = Self.retainedDetail(rory[4])

        let before = Self.fiveInput(.before, all, selected: cut.selection, actualSummary: "T3 · −15")
        XCTAssertEqual(before.plotted(cut)?.text, "89.6%")
        XCTAssertNil(before.baseline(cut))
        XCTAssertNil(before.selectedSlot)
        XCTAssertNil(before.accessibilityHeader, "no result summary before the final")
        XCTAssertEqual(before.accessibilityValue(for: cut), "Before tournament: 89.6%, \(detail)")

        let recorded = Self.fiveInput(.recorded, all, actualSummary: "T3 · −15")
        XCTAssertEqual(recorded.plotted(cut)?.text, "100%")
        let full = try XCTUnwrap(recorded.plotted(cut))
        XCTAssertEqual(GolfFinishGeometry10868.markHeight(full.probability), 188)
        XCTAssertEqual(recorded.baseline(cut)?.text, "89.6%")
        XCTAssertNil(recorded.accessibilityHeader)
        XCTAssertEqual(recorded.accessibilityValue(for: cut),
                       "Before tournament: 89.6%, \(detail); Recorded estimate: 100%, constructed recorded · DataGolf model estimate")

        let final = Self.fiveInput(.final, all, actualSummary: "T3 · −15")
        XCTAssertEqual(final.plotted(cut)?.text, "89.6%", "the final keeps the earlier chance, not a 100% bar")
        XCTAssertNil(final.baseline(cut))
        XCTAssertEqual(final.accessibilityHeader, "T3 · −15")
        XCTAssertEqual(final.accessibilityValue(for: cut), "Before tournament: 89.6%, \(detail); Actual finish: Made cut")
    }

    func testUnknownMakeCutResultIsNeverALoss() throws {
        let rory = try Self.retainedGolfer("Rory McIlroy")
        let slots = rory.map(Self.retainedSlot)
        let detail = Self.retainedDetail(rory[4])
        // CONSTRUCTED results.
        let unknown = Self.fiveInput(.final, Array(slots.prefix(4)) + [slots[4]])
        let missed = Self.fiveInput(.final, Array(slots.prefix(4)) + [Self.withSlot(slots[4], actual: GolfFinishResult10868(text: "Missed cut", mark: .failure))])
        XCTAssertEqual(unknown.makeCut?.actual.mark, .unknown)
        XCTAssertEqual(missed.makeCut?.actual.mark, .failure)
        XCTAssertEqual(unknown.accessibilityValue(for: try XCTUnwrap(unknown.makeCut)),
                       "Before tournament: 89.6%, \(detail); Actual finish: Unknown")
        XCTAssertEqual(missed.accessibilityValue(for: try XCTUnwrap(missed.makeCut)),
                       "Before tournament: 89.6%, \(detail); Actual finish: Missed cut")
        XCTAssertNil(unknown.accessibilityHeader, "no invented result summary")
    }

    // MARK: Layout plan

    func testFiveFinishPlanGroupsEveryFinishWithoutDroppingOrReordering() throws {
        let input = Self.retainedInput(try Self.retainedGolfer("Rory McIlroy"))
        let ids = input.slots.map(\.selection)
        XCTAssertEqual(GolfFinishGeometry10868.columnCandidates(slotCount: input.slots.count, isAccessibilitySize: false), [5, 3, 2, 1])
        XCTAssertEqual(GolfFinishGeometry10868.columnCandidates(slotCount: input.slots.count, isAccessibilitySize: true), [2, 1])
        XCTAssertEqual(GolfFinishGeometry10868.columnCandidates(isAccessibilitySize: false), [4, 2, 1], "the four-finish plan is unchanged")
        XCTAssertEqual(GolfFinishGeometry10868.columnCandidates(isAccessibilitySize: true), [2, 1])
        XCTAssertEqual(GolfFinishGeometry10868.tileColumns(isAccessibilitySize: false), 2)
        XCTAssertEqual(GolfFinishGeometry10868.tileColumns(isAccessibilitySize: true), 1)

        XCTAssertEqual(GolfFinishGeometry10868.groups(ids, columns: 5), [ids])
        XCTAssertEqual(GolfFinishGeometry10868.groups(ids, columns: 3), [Array(ids[0..<3]), Array(ids[3..<5])])
        XCTAssertEqual(GolfFinishGeometry10868.groups(ids, columns: 2), [Array(ids[0..<2]), Array(ids[2..<4]), [ids[4]]])
        XCTAssertEqual(GolfFinishGeometry10868.groups(ids, columns: 1), ids.map { [$0] })
        for isAccessibilitySize in [false, true] {
            for count in GolfFinishGeometry10868.columnCandidates(slotCount: input.slots.count, isAccessibilitySize: isAccessibilitySize) {
                let rows = GolfFinishGeometry10868.groups(ids, columns: count)
                XCTAssertEqual(rows.flatMap { $0 }, ids, "every finish once, in order")
                XCTAssertTrue(rows.allSatisfy { !$0.isEmpty && $0.count <= count })
                XCTAssertNotEqual(rows.map(\.count), [4, 1], "never four and an orphan")
            }
        }
    }
}

private struct GolfFinishRetainedRecord10868: Equatable {
    let golfer: String
    let label: String
    let selection: String
    let rawID: String
    let probability: Double?
    let opening: Double?
    let lastUpdated: String
    let figure: String
}

private let retainedTable = #"""
Rory McIlroy	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|246352440	246352440	0.1271	0.1271	2026-10-12T23:11:05.501054+00:00	12.7%
Rory McIlroy	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|246352498	246352498	0.351696	0.351696	2026-10-12T23:11:06.747890+00:00	35.2%
Rory McIlroy	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|246352556	246352556	0.498592	0.498592	2026-10-12T23:11:07.952964+00:00	49.9%
Rory McIlroy	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|246352614	246352614	0.665303	0.665303	2026-10-12T23:11:09.073291+00:00	66.5%
Rory McIlroy	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|246352672	246352672	0.896383	0.896383	2026-10-12T23:11:10.724619+00:00	89.6%
Tommy Fleetwood	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|246352441	246352441	0.067167	0.067167	2026-10-12T23:11:05.501054+00:00	6.7%
Tommy Fleetwood	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|246352499	246352499	0.249126	0.249126	2026-10-12T23:11:06.747890+00:00	24.9%
Tommy Fleetwood	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|246352557	246352557	0.394375	0.394375	2026-10-12T23:11:07.952964+00:00	39.4%
Tommy Fleetwood	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|246352615	246352615	0.578978	0.578978	2026-10-12T23:11:09.073291+00:00	57.9%
Tommy Fleetwood	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|246352673	246352673	0.87105	0.87105	2026-10-12T23:11:10.724619+00:00	87.1%
Min Woo Lee	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|246352442	246352442	0.0669	0.0669	2026-10-12T23:11:05.501054+00:00	6.7%
Min Woo Lee	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|246352500	246352500	0.23476	0.23476	2026-10-12T23:11:06.747890+00:00	23.5%
Min Woo Lee	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|246352558	246352558	0.367897	0.367897	2026-10-12T23:11:07.952964+00:00	36.8%
Min Woo Lee	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|246352616	246352616	0.543127	0.543127	2026-10-12T23:11:09.073291+00:00	54.3%
Min Woo Lee	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|246352674	246352674	0.850983	0.850983	2026-10-12T23:11:10.724619+00:00	85.1%
Eugenio Chacarra	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904631	245904631	0.0544	0.04145	2026-10-12T23:11:05.501054+00:00	5.4%
Eugenio Chacarra	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904763	245904763	0.213013	0.165032	2026-10-12T23:11:06.747890+00:00	21.3%
Eugenio Chacarra	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904895	245904895	0.349389	0.279395	2026-10-12T23:11:07.952964+00:00	34.9%
Eugenio Chacarra	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905027	245905027	0.533627	0.449587	2026-10-12T23:11:09.073291+00:00	53.4%
Eugenio Chacarra	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905159	245905159	0.852633	0.816833	2026-10-12T23:11:10.724619+00:00	85.3%
Robert MacIntyre	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|246352443	246352443	0.048083	0.048083	2026-10-12T23:11:05.501054+00:00	4.8%
Robert MacIntyre	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|246352501	246352501	0.190861	0.190861	2026-10-12T23:11:06.747890+00:00	19.1%
Robert MacIntyre	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|246352559	246352559	0.318564	0.318564	2026-10-12T23:11:07.952964+00:00	31.9%
Robert MacIntyre	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|246352617	246352617	0.497194	0.497194	2026-10-12T23:11:09.073291+00:00	49.7%
Robert MacIntyre	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|246352675	246352675	0.833067	0.833067	2026-10-12T23:11:10.724619+00:00	83.3%
Shane Lowry	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904630	245904630	0.045817	0.051233	2026-10-12T23:11:05.501054+00:00	4.6%
Shane Lowry	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904762	245904762	0.187908	0.190185	2026-10-12T23:11:06.747890+00:00	18.8%
Shane Lowry	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904894	245904894	0.317185	0.311706	2026-10-12T23:11:07.952964+00:00	31.7%
Shane Lowry	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905026	245905026	0.497302	0.479704	2026-10-12T23:11:09.073291+00:00	49.7%
Shane Lowry	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905158	245905158	0.83745	0.829517	2026-10-12T23:11:10.724619+00:00	83.7%
Aaron Rai	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|246352444	246352444	0.0249	0.0249	2026-10-12T23:11:05.501054+00:00	2.5%
Aaron Rai	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|246352502	246352502	0.125473	0.125473	2026-10-12T23:11:06.747890+00:00	12.5%
Aaron Rai	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|246352560	246352560	0.23238	0.23238	2026-10-12T23:11:07.952964+00:00	23.2%
Aaron Rai	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|246352618	246352618	0.403445	0.403445	2026-10-12T23:11:09.073291+00:00	40.3%
Aaron Rai	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|246352676	246352676	0.797767	0.797767	2026-10-12T23:11:10.724619+00:00	79.8%
Patrick Reed	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904633	245904633	0.023733	0.028017	2026-10-12T23:11:05.501054+00:00	2.4%
Patrick Reed	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904765	245904765	0.120682	0.126477	2026-10-12T23:11:06.747890+00:00	12.1%
Patrick Reed	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904897	245904897	0.228126	0.230918	2026-10-12T23:11:07.952964+00:00	22.8%
Patrick Reed	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905029	245905029	0.399542	0.396019	2026-10-12T23:11:09.073291+00:00	40%
Patrick Reed	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905161	245905161	0.796867	0.791817	2026-10-12T23:11:10.724619+00:00	79.7%
Jacob Skov Olesen	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904641	245904641	0.022867	0.0191	2026-10-12T23:11:05.501054+00:00	2.3%
Jacob Skov Olesen	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904773	245904773	0.108299	0.092519	2026-10-12T23:11:06.747890+00:00	10.8%
Jacob Skov Olesen	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904905	245904905	0.202846	0.173173	2026-10-12T23:11:07.952964+00:00	20.3%
Jacob Skov Olesen	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905037	245905037	0.360308	0.310331	2026-10-12T23:11:09.073291+00:00	36%
Jacob Skov Olesen	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905169	245905169	0.768517	0.72795	2026-10-12T23:11:10.724619+00:00	76.9%
Angel Ayora	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904643	245904643	0.022733	0.018933	2026-10-12T23:11:05.501054+00:00	2.3%
Angel Ayora	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904775	245904775	0.109575	0.089908	2026-10-12T23:11:06.747890+00:00	11%
Angel Ayora	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904907	245904907	0.202328	0.167647	2026-10-12T23:11:07.952964+00:00	20.2%
Angel Ayora	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905039	245905039	0.354438	0.300218	2026-10-12T23:11:09.073291+00:00	35.4%
Angel Ayora	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905171	245905171	0.757467	0.721133	2026-10-12T23:11:10.724619+00:00	75.7%
Casey Jarvis	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|246352445	246352445	0.022017	0.022017	2026-10-12T23:11:05.501054+00:00	2.2%
Casey Jarvis	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|246352503	246352503	0.10605	0.10605	2026-10-12T23:11:06.747890+00:00	10.6%
Casey Jarvis	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|246352561	246352561	0.198485	0.198485	2026-10-12T23:11:07.952964+00:00	19.8%
Casey Jarvis	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|246352619	246352619	0.348835	0.348835	2026-10-12T23:11:09.073291+00:00	34.9%
Casey Jarvis	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|246352677	246352677	0.755683	0.755683	2026-10-12T23:11:10.724619+00:00	75.6%
Tom McKibbin	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904634	245904634	0.0215	0.024517	2026-10-12T23:11:05.501054+00:00	2.2%
Tom McKibbin	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904766	245904766	0.110461	0.114142	2026-10-12T23:11:06.747890+00:00	11%
Tom McKibbin	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904898	245904898	0.210467	0.208236	2026-10-12T23:11:07.952964+00:00	21%
Tom McKibbin	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905030	245905030	0.378313	0.361263	2026-10-12T23:11:09.073291+00:00	37.8%
Tom McKibbin	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905162	245905162	0.784167	0.7698	2026-10-12T23:11:10.724619+00:00	78.4%
Justin Rose	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904639	245904639	0.018783	0.02005	2026-10-12T23:11:05.501054+00:00	1.9%
Justin Rose	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904771	245904771	0.09264	0.087758	2026-10-12T23:11:06.747890+00:00	9.3%
Justin Rose	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904903	245904903	0.174705	0.162257	2026-10-12T23:11:07.952964+00:00	17.5%
Justin Rose	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905035	245905035	0.316737	0.291933	2026-10-12T23:11:09.073291+00:00	31.7%
Justin Rose	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905167	245905167	0.729017	0.7054	2026-10-12T23:11:10.724619+00:00	72.9%
Daniel Hillier	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904635	245904635	0.018567	0.022567	2026-10-12T23:11:05.501054+00:00	1.9%
Daniel Hillier	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904767	245904767	0.095654	0.101502	2026-10-12T23:11:06.747890+00:00	9.6%
Daniel Hillier	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904899	245904899	0.183838	0.186678	2026-10-12T23:11:07.952964+00:00	18.4%
Daniel Hillier	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905031	245905031	0.333481	0.331676	2026-10-12T23:11:09.073291+00:00	33.3%
Daniel Hillier	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905163	245905163	0.74435	0.747017	2026-10-12T23:11:10.724619+00:00	74.4%
Ryan Fox	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|246352446	246352446	0.0185	0.0185	2026-10-12T23:11:05.501054+00:00	1.9%
Ryan Fox	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|246352504	246352504	0.096403	0.096403	2026-10-12T23:11:06.747890+00:00	9.6%
Ryan Fox	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|246352562	246352562	0.185214	0.185214	2026-10-12T23:11:07.952964+00:00	18.5%
Ryan Fox	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|246352620	246352620	0.339236	0.339236	2026-10-12T23:11:09.073291+00:00	33.9%
Ryan Fox	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|246352678	246352678	0.753833	0.753833	2026-10-12T23:11:10.724619+00:00	75.4%
Oliver Lindell	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904645	245904645	0.018317	0.01785	2026-10-12T23:11:05.501054+00:00	1.8%
Oliver Lindell	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904777	245904777	0.09444	0.087133	2026-10-12T23:11:06.747890+00:00	9.4%
Oliver Lindell	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904909	245904909	0.18507	0.165196	2026-10-12T23:11:07.952964+00:00	18.5%
Oliver Lindell	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905041	245905041	0.339455	0.302347	2026-10-12T23:11:09.073291+00:00	33.9%
Oliver Lindell	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905173	245905173	0.756483	0.735367	2026-10-12T23:11:10.724619+00:00	75.6%
Ewen Ferguson	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904644	245904644	0.015667	0.018483	2026-10-12T23:11:05.501054+00:00	1.6%
Ewen Ferguson	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904776	245904776	0.086561	0.089063	2026-10-12T23:11:06.747890+00:00	8.7%
Ewen Ferguson	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904908	245904908	0.171444	0.167641	2026-10-12T23:11:07.952964+00:00	17.1%
Ewen Ferguson	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905040	245905040	0.320031	0.305089	2026-10-12T23:11:09.073291+00:00	32%
Ewen Ferguson	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905172	245905172	0.742683	0.724667	2026-10-12T23:11:10.724619+00:00	74.3%
Antoine Rozner	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904649	245904649	0.015533	0.013933	2026-10-12T23:11:05.501054+00:00	1.6%
Antoine Rozner	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904781	245904781	0.083854	0.06924	2026-10-12T23:11:06.747890+00:00	8.4%
Antoine Rozner	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904913	245904913	0.166477	0.136073	2026-10-12T23:11:07.952964+00:00	16.6%
Antoine Rozner	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905045	245905045	0.310612	0.259914	2026-10-12T23:11:09.073291+00:00	31.1%
Antoine Rozner	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905177	245905177	0.7365	0.695033	2026-10-12T23:11:10.724619+00:00	73.7%
Thomas Detry	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904640	245904640	0.01445	0.0199	2026-10-12T23:11:05.501054+00:00	1.4%
Thomas Detry	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904772	245904772	0.076624	0.093458	2026-10-12T23:11:06.747890+00:00	7.7%
Thomas Detry	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904904	245904904	0.155081	0.176453	2026-10-12T23:11:07.952964+00:00	15.5%
Thomas Detry	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905036	245905036	0.298551	0.315686	2026-10-12T23:11:09.073291+00:00	29.9%
Thomas Detry	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905168	245905168	0.72475	0.7311	2026-10-12T23:11:10.724619+00:00	72.5%
Bernd Wiesberger	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904667	245904667	0.013417	0.0074	2026-10-12T23:11:05.501054+00:00	1.3%
Bernd Wiesberger	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904799	245904799	0.073145	0.044859	2026-10-12T23:11:06.747890+00:00	7.3%
Bernd Wiesberger	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904931	245904931	0.150714	0.094456	2026-10-12T23:11:07.952964+00:00	15.1%
Bernd Wiesberger	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905063	245905063	0.293956	0.199618	2026-10-12T23:11:09.073291+00:00	29.4%
Bernd Wiesberger	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905195	245905195	0.725767	0.649067	2026-10-12T23:11:10.724619+00:00	72.6%
Martin Couvra	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904673	245904673	0.01115	0.006383	2026-10-12T23:11:05.501054+00:00	1.1%
Martin Couvra	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904805	245904805	0.063377	0.036799	2026-10-12T23:11:06.747890+00:00	6.3%
Martin Couvra	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904937	245904937	0.1313	0.079674	2026-10-12T23:11:07.952964+00:00	13.1%
Martin Couvra	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905069	245905069	0.257306	0.170268	2026-10-12T23:11:09.073291+00:00	25.7%
Martin Couvra	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905201	245905201	0.69605	0.601467	2026-10-12T23:11:10.724619+00:00	69.6%
Joakim Lagergren	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904654	245904654	0.0106	0.01015	2026-10-12T23:11:05.501054+00:00	1.1%
Joakim Lagergren	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904786	245904786	0.059633	0.052113	2026-10-12T23:11:06.747890+00:00	6%
Joakim Lagergren	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904918	245904918	0.122221	0.104873	2026-10-12T23:11:07.952964+00:00	12.2%
Joakim Lagergren	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905050	245905050	0.242253	0.208616	2026-10-12T23:11:09.073291+00:00	24.2%
Joakim Lagergren	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905182	245905182	0.673417	0.626367	2026-10-12T23:11:10.724619+00:00	67.3%
Byeong Hun An	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|246352447	246352447	0.010533	0.010533	2026-10-12T23:11:05.501054+00:00	1.1%
Byeong Hun An	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|246352505	246352505	0.061933	0.061933	2026-10-12T23:11:06.747890+00:00	6.2%
Byeong Hun An	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|246352563	246352563	0.126827	0.126827	2026-10-12T23:11:07.952964+00:00	12.7%
Byeong Hun An	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|246352621	246352621	0.2497	0.2497	2026-10-12T23:11:09.073291+00:00	25%
Byeong Hun An	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|246352679	246352679	0.680767	0.680767	2026-10-12T23:11:10.724619+00:00	68.1%
Niklas Norgaard	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904655	245904655	0.010483	0.0101	2026-10-12T23:11:05.501054+00:00	1%
Niklas Norgaard	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904787	245904787	0.059822	0.054837	2026-10-12T23:11:06.747890+00:00	6%
Niklas Norgaard	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904919	245904919	0.123471	0.110336	2026-10-12T23:11:07.952964+00:00	12.3%
Niklas Norgaard	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905051	245905051	0.246567	0.216599	2026-10-12T23:11:09.073291+00:00	24.7%
Niklas Norgaard	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905183	245905183	0.67845	0.654567	2026-10-12T23:11:10.724619+00:00	67.8%
Francesco Laporta	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904659	245904659	0.010233	0.009	2026-10-12T23:11:05.501054+00:00	1%
Francesco Laporta	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904791	245904791	0.059516	0.046556	2026-10-12T23:11:06.747890+00:00	6%
Francesco Laporta	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904923	245904923	0.12595	0.098999	2026-10-12T23:11:07.952964+00:00	12.6%
Francesco Laporta	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905055	245905055	0.252359	0.201704	2026-10-12T23:11:09.073291+00:00	25.2%
Francesco Laporta	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905187	245905187	0.689217	0.642517	2026-10-12T23:11:10.724619+00:00	68.9%
Jayden Schaper	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904656	245904656	0.0088	0.009933	2026-10-12T23:11:05.501054+00:00	0.9%
Jayden Schaper	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904788	245904788	0.055263	0.054303	2026-10-12T23:11:06.747890+00:00	5.5%
Jayden Schaper	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904920	245904920	0.118259	0.114146	2026-10-12T23:11:07.952964+00:00	11.8%
Jayden Schaper	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905052	245905052	0.242755	0.228377	2026-10-12T23:11:09.073291+00:00	24.3%
Jayden Schaper	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905184	245905184	0.6869	0.665083	2026-10-12T23:11:10.724619+00:00	68.7%
Joost Luiten	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904666	245904666	0.008383	0.007667	2026-10-12T23:11:05.501054+00:00	0.8%
Joost Luiten	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904798	245904798	0.050411	0.04266	2026-10-12T23:11:06.747890+00:00	5%
Joost Luiten	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904930	245904930	0.109637	0.089612	2026-10-12T23:11:07.952964+00:00	11%
Joost Luiten	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905062	245905062	0.227479	0.185792	2026-10-12T23:11:09.073291+00:00	22.7%
Joost Luiten	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905194	245905194	0.671333	0.631367	2026-10-12T23:11:10.724619+00:00	67.1%
Nathan Kimsey	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904670	245904670	0.008317	0.0067	2026-10-12T23:11:05.501054+00:00	0.8%
Nathan Kimsey	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904802	245904802	0.049251	0.039138	2026-10-12T23:11:06.747890+00:00	4.9%
Nathan Kimsey	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904934	245904934	0.106656	0.083394	2026-10-12T23:11:07.952964+00:00	10.7%
Nathan Kimsey	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905066	245905066	0.220278	0.176158	2026-10-12T23:11:09.073291+00:00	22%
Nathan Kimsey	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905198	245905198	0.659283	0.603817	2026-10-12T23:11:10.724619+00:00	65.9%
Tom Vaillant	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904679	245904679	0.00805	0.006	2026-10-12T23:11:05.501054+00:00	0.8%
Tom Vaillant	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904811	245904811	0.048283	0.036491	2026-10-12T23:11:06.747890+00:00	4.8%
Tom Vaillant	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904943	245904943	0.10543	0.077658	2026-10-12T23:11:07.952964+00:00	10.5%
Tom Vaillant	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905075	245905075	0.217733	0.166384	2026-10-12T23:11:09.073291+00:00	21.8%
Tom Vaillant	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905207	245905207	0.656133	0.5924	2026-10-12T23:11:10.724619+00:00	65.6%
Adrian Meronk	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904653	245904653	0.007133	0.01045	2026-10-12T23:11:05.501054+00:00	0.7%
Adrian Meronk	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904785	245904785	0.045585	0.055394	2026-10-12T23:11:06.747890+00:00	4.6%
Adrian Meronk	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904917	245904917	0.097358	0.112865	2026-10-12T23:11:07.952964+00:00	9.7%
Adrian Meronk	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905049	245905049	0.208042	0.2251	2026-10-12T23:11:09.073291+00:00	20.8%
Adrian Meronk	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905181	245905181	0.64735	0.665683	2026-10-12T23:11:10.724619+00:00	64.7%
Laurie Canter	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|246352448	246352448	0.006983	0.006983	2026-10-12T23:11:05.501054+00:00	0.7%
Laurie Canter	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|246352506	246352506	0.045368	0.045368	2026-10-12T23:11:06.747890+00:00	4.5%
Laurie Canter	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|246352564	246352564	0.098055	0.098055	2026-10-12T23:11:07.952964+00:00	9.8%
Laurie Canter	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|246352622	246352622	0.207328	0.207328	2026-10-12T23:11:09.073291+00:00	20.7%
Laurie Canter	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|246352680	246352680	0.649417	0.649417	2026-10-12T23:11:10.724619+00:00	64.9%
JC Ritchie	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904676	245904676	0.006817	0.006167	2026-10-12T23:11:05.501054+00:00	0.7%
JC Ritchie	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904808	245904808	0.042643	0.036672	2026-10-12T23:11:06.747890+00:00	4.3%
JC Ritchie	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904940	245904940	0.091979	0.07866	2026-10-12T23:11:07.952964+00:00	9.2%
JC Ritchie	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905072	245905072	0.195218	0.170432	2026-10-12T23:11:09.073291+00:00	19.5%
JC Ritchie	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905204	245905204	0.631933	0.595317	2026-10-12T23:11:10.724619+00:00	63.2%
Angel Hidalgo	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904674	245904674	0.006683	0.006317	2026-10-12T23:11:05.501054+00:00	0.7%
Angel Hidalgo	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904806	245904806	0.043224	0.037014	2026-10-12T23:11:06.747890+00:00	4.3%
Angel Hidalgo	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904938	245904938	0.095744	0.079488	2026-10-12T23:11:07.952964+00:00	9.6%
Angel Hidalgo	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905070	245905070	0.203442	0.168417	2026-10-12T23:11:09.073291+00:00	20.3%
Angel Hidalgo	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905202	245905202	0.64315	0.596517	2026-10-12T23:11:10.724619+00:00	64.3%
Andy Sullivan	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904668	245904668	0.006417	0.007117	2026-10-12T23:11:05.501054+00:00	0.6%
Andy Sullivan	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904800	245904800	0.041048	0.038782	2026-10-12T23:11:06.747890+00:00	4.1%
Andy Sullivan	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904932	245904932	0.091148	0.083705	2026-10-12T23:11:07.952964+00:00	9.1%
Andy Sullivan	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905064	245905064	0.197509	0.177281	2026-10-12T23:11:09.073291+00:00	19.8%
Andy Sullivan	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905196	245905196	0.640367	0.610083	2026-10-12T23:11:10.724619+00:00	64%
Ugo Coussaud	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904675	245904675	0.006133	0.00625	2026-10-12T23:11:05.501054+00:00	0.6%
Ugo Coussaud	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904807	245904807	0.041074	0.038215	2026-10-12T23:11:06.747890+00:00	4.1%
Ugo Coussaud	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904939	245904939	0.091471	0.084625	2026-10-12T23:11:07.952964+00:00	9.1%
Ugo Coussaud	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905071	245905071	0.193465	0.176221	2026-10-12T23:11:09.073291+00:00	19.3%
Ugo Coussaud	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905203	245905203	0.6315	0.615983	2026-10-12T23:11:10.724619+00:00	63.2%
Romain Langasque	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904695	245904695	0.005767	0.003917	2026-10-12T23:11:05.501054+00:00	0.6%
Romain Langasque	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904827	245904827	0.037682	0.025568	2026-10-12T23:11:06.747890+00:00	3.8%
Romain Langasque	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904959	245904959	0.085318	0.060362	2026-10-12T23:11:07.952964+00:00	8.5%
Romain Langasque	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905091	245905091	0.188263	0.136801	2026-10-12T23:11:09.073291+00:00	18.8%
Romain Langasque	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905223	245905223	0.633517	0.5623	2026-10-12T23:11:10.724619+00:00	63.4%
Guido Migliozzi	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904658	245904658	0.005483	0.009383	2026-10-12T23:11:05.501054+00:00	0.5%
Guido Migliozzi	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904790	245904790	0.034661	0.05377	2026-10-12T23:11:06.747890+00:00	3.5%
Guido Migliozzi	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904922	245904922	0.079052	0.111158	2026-10-12T23:11:07.952964+00:00	7.9%
Guido Migliozzi	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905054	245905054	0.176065	0.222757	2026-10-12T23:11:09.073291+00:00	17.6%
Guido Migliozzi	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905186	245905186	0.61635	0.660167	2026-10-12T23:11:10.724619+00:00	61.6%
Julien Guerrier	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904687	245904687	0.00545	0.004733	2026-10-12T23:11:05.501054+00:00	0.5%
Julien Guerrier	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904819	245904819	0.035372	0.030512	2026-10-12T23:11:06.747890+00:00	3.5%
Julien Guerrier	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904951	245904951	0.07976	0.069593	2026-10-12T23:11:07.952964+00:00	8%
Julien Guerrier	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905083	245905083	0.174217	0.154835	2026-10-12T23:11:09.073291+00:00	17.4%
Julien Guerrier	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905215	245905215	0.6143	0.579433	2026-10-12T23:11:10.724619+00:00	61.4%
Joel Girrbach	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904698	245904698	0.00525	0.003567	2026-10-12T23:11:05.501054+00:00	0.5%
Joel Girrbach	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904830	245904830	0.034085	0.02383	2026-10-12T23:11:06.747890+00:00	3.4%
Joel Girrbach	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904962	245904962	0.078699	0.054898	2026-10-12T23:11:07.952964+00:00	7.9%
Joel Girrbach	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905094	245905094	0.179008	0.129457	2026-10-12T23:11:09.073291+00:00	17.9%
Joel Girrbach	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905226	245905226	0.61815	0.5501	2026-10-12T23:11:10.724619+00:00	61.8%
Freddy Schott	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904680	245904680	0.0052	0.006	2026-10-12T23:11:05.501054+00:00	0.5%
Freddy Schott	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904812	245904812	0.032621	0.034674	2026-10-12T23:11:06.747890+00:00	3.3%
Freddy Schott	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904944	245904944	0.072798	0.072777	2026-10-12T23:11:07.952964+00:00	7.3%
Freddy Schott	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905076	245905076	0.157959	0.150543	2026-10-12T23:11:09.073291+00:00	15.8%
Freddy Schott	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905208	245905208	0.578283	0.5596	2026-10-12T23:11:10.724619+00:00	57.8%
Davis Bryant	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904669	245904669	0.005167	0.006817	2026-10-12T23:11:05.501054+00:00	0.5%
Davis Bryant	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904801	245904801	0.036724	0.043038	2026-10-12T23:11:06.747890+00:00	3.7%
Davis Bryant	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904933	245904933	0.085053	0.092463	2026-10-12T23:11:07.952964+00:00	8.5%
Davis Bryant	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905065	245905065	0.191317	0.196304	2026-10-12T23:11:09.073291+00:00	19.1%
Davis Bryant	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905197	245905197	0.63745	0.6463	2026-10-12T23:11:10.724619+00:00	63.7%
Gregorio De Leo	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904681	245904681	0.00515	0.00575	2026-10-12T23:11:05.501054+00:00	0.5%
Gregorio De Leo	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904813	245904813	0.033124	0.035011	2026-10-12T23:11:06.747890+00:00	3.3%
Gregorio De Leo	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904945	245904945	0.075336	0.077252	2026-10-12T23:11:07.952964+00:00	7.5%
Gregorio De Leo	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905077	245905077	0.167665	0.16552	2026-10-12T23:11:09.073291+00:00	16.8%
Gregorio De Leo	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905209	245905209	0.606017	0.607833	2026-10-12T23:11:10.724619+00:00	60.6%
Manuel Elvira	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904690	245904690	0.004967	0.0045	2026-10-12T23:11:05.501054+00:00	0.5%
Manuel Elvira	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904822	245904822	0.034986	0.029297	2026-10-12T23:11:06.747890+00:00	3.5%
Manuel Elvira	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904954	245904954	0.0784	0.064583	2026-10-12T23:11:07.952964+00:00	7.8%
Manuel Elvira	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905086	245905086	0.173839	0.142435	2026-10-12T23:11:09.073291+00:00	17.4%
Manuel Elvira	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905218	245905218	0.6149	0.576917	2026-10-12T23:11:10.724619+00:00	61.5%
Dan Bradbury	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904682	245904682	0.004717	0.005467	2026-10-12T23:11:05.501054+00:00	0.5%
Dan Bradbury	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904814	245904814	0.030762	0.032815	2026-10-12T23:11:06.747890+00:00	3.1%
Dan Bradbury	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904946	245904946	0.07201	0.070452	2026-10-12T23:11:07.952964+00:00	7.2%
Dan Bradbury	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905078	245905078	0.160747	0.147684	2026-10-12T23:11:09.073291+00:00	16.1%
Dan Bradbury	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905210	245905210	0.593217	0.567467	2026-10-12T23:11:10.724619+00:00	59.3%
David Ravetto	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904678	245904678	0.004567	0.006067	2026-10-12T23:11:05.501054+00:00	0.5%
David Ravetto	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904810	245904810	0.030315	0.03734	2026-10-12T23:11:06.747890+00:00	3%
David Ravetto	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904942	245904942	0.06915	0.08064	2026-10-12T23:11:07.952964+00:00	6.9%
David Ravetto	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905074	245905074	0.15718	0.172769	2026-10-12T23:11:09.073291+00:00	15.7%
David Ravetto	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905206	245905206	0.591433	0.614767	2026-10-12T23:11:10.724619+00:00	59.1%
Ignacio Elvira Mijares	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904693	245904693	0.00435	0.0042	2026-10-12T23:11:05.501054+00:00	0.4%
Ignacio Elvira Mijares	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904825	245904825	0.033871	0.028417	2026-10-12T23:11:06.747890+00:00	3.4%
Ignacio Elvira Mijares	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904957	245904957	0.077069	0.065125	2026-10-12T23:11:07.952964+00:00	7.7%
Ignacio Elvira Mijares	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905089	245905089	0.172742	0.144765	2026-10-12T23:11:09.073291+00:00	17.3%
Ignacio Elvira Mijares	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905221	245905221	0.618117	0.572033	2026-10-12T23:11:10.724619+00:00	61.8%
Todd Clements	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904694	245904694	0.00425	0.004167	2026-10-12T23:11:05.501054+00:00	0.4%
Todd Clements	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904826	245904826	0.029684	0.028008	2026-10-12T23:11:06.747890+00:00	3%
Todd Clements	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904958	245904958	0.067421	0.063191	2026-10-12T23:11:07.952964+00:00	6.7%
Todd Clements	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905090	245905090	0.154699	0.141554	2026-10-12T23:11:09.073291+00:00	15.5%
Todd Clements	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905222	245905222	0.593383	0.56785	2026-10-12T23:11:10.724619+00:00	59.3%
Yuto Katsuragawa	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904700	245904700	0.0042	0.0035	2026-10-12T23:11:05.501054+00:00	0.4%
Yuto Katsuragawa	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904832	245904832	0.027476	0.021857	2026-10-12T23:11:06.747890+00:00	2.7%
Yuto Katsuragawa	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904964	245904964	0.064482	0.050818	2026-10-12T23:11:07.952964+00:00	6.4%
Yuto Katsuragawa	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905096	245905096	0.14983	0.119611	2026-10-12T23:11:09.073291+00:00	15%
Yuto Katsuragawa	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905228	245905228	0.58035	0.526217	2026-10-12T23:11:10.724619+00:00	58%
David Law	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904686	245904686	0.004167	0.005017	2026-10-12T23:11:05.501054+00:00	0.4%
David Law	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904818	245904818	0.02932	0.034389	2026-10-12T23:11:06.747890+00:00	2.9%
David Law	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904950	245904950	0.066346	0.076111	2026-10-12T23:11:07.952964+00:00	6.6%
David Law	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905082	245905082	0.152194	0.16431	2026-10-12T23:11:09.073291+00:00	15.2%
David Law	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905214	245905214	0.589167	0.60525	2026-10-12T23:11:10.724619+00:00	58.9%
Maximilian Steinlechner	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904688	245904688	0.004133	0.004717	2026-10-12T23:11:05.501054+00:00	0.4%
Maximilian Steinlechner	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904820	245904820	0.02974	0.028982	2026-10-12T23:11:06.747890+00:00	3%
Maximilian Steinlechner	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904952	245904952	0.067853	0.063289	2026-10-12T23:11:07.952964+00:00	6.8%
Maximilian Steinlechner	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905084	245905084	0.155395	0.140889	2026-10-12T23:11:09.073291+00:00	15.5%
Maximilian Steinlechner	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905216	245905216	0.5889	0.56935	2026-10-12T23:11:10.724619+00:00	58.9%
Marcus Armitage	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904683	245904683	0.004083	0.005367	2026-10-12T23:11:05.501054+00:00	0.4%
Marcus Armitage	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904815	245904815	0.02811	0.035889	2026-10-12T23:11:06.747890+00:00	2.8%
Marcus Armitage	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904947	245904947	0.065999	0.077866	2026-10-12T23:11:07.952964+00:00	6.6%
Marcus Armitage	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905079	245905079	0.152824	0.169932	2026-10-12T23:11:09.073291+00:00	15.3%
Marcus Armitage	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905211	245905211	0.591517	0.603567	2026-10-12T23:11:10.724619+00:00	59.2%
Darius Van Driel	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904713	245904713	0.00385	0.002483	2026-10-12T23:11:05.501054+00:00	0.4%
Darius Van Driel	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904845	245904845	0.028768	0.017355	2026-10-12T23:11:06.747890+00:00	2.9%
Darius Van Driel	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904977	245904977	0.068758	0.042375	2026-10-12T23:11:07.952964+00:00	6.9%
Darius Van Driel	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905109	245905109	0.156971	0.103984	2026-10-12T23:11:09.073291+00:00	15.7%
Darius Van Driel	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905241	245905241	0.595383	0.514	2026-10-12T23:11:10.724619+00:00	59.5%
Frederic LaCroix	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904697	245904697	0.003733	0.0038	2026-10-12T23:11:05.501054+00:00	0.4%
Frederic LaCroix	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904829	245904829	0.027684	0.024143	2026-10-12T23:11:06.747890+00:00	2.8%
Frederic LaCroix	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904961	245904961	0.065324	0.055611	2026-10-12T23:11:07.952964+00:00	6.5%
Frederic LaCroix	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905093	245905093	0.15111	0.129327	2026-10-12T23:11:09.073291+00:00	15.1%
Frederic LaCroix	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905225	245905225	0.58355	0.560483	2026-10-12T23:11:10.724619+00:00	58.4%
Oihan Guillamoundeguy	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904691	245904691	0.003717	0.0045	2026-10-12T23:11:05.501054+00:00	0.4%
Oihan Guillamoundeguy	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904823	245904823	0.026176	0.028072	2026-10-12T23:11:06.747890+00:00	2.6%
Oihan Guillamoundeguy	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904955	245904955	0.061618	0.062525	2026-10-12T23:11:07.952964+00:00	6.2%
Oihan Guillamoundeguy	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905087	245905087	0.141802	0.137618	2026-10-12T23:11:09.073291+00:00	14.2%
Oihan Guillamoundeguy	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905219	245905219	0.56925	0.561983	2026-10-12T23:11:10.724619+00:00	56.9%
Andreas Halvorsen	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|246352449	246352449	0.0037	0.0037	2026-10-12T23:11:05.501054+00:00	0.4%
Andreas Halvorsen	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|246352507	246352507	0.028037	0.028037	2026-10-12T23:11:06.747890+00:00	2.8%
Andreas Halvorsen	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|246352565	246352565	0.0633	0.0633	2026-10-12T23:11:07.952964+00:00	6.3%
Andreas Halvorsen	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|246352623	246352623	0.142762	0.142762	2026-10-12T23:11:09.073291+00:00	14.3%
Andreas Halvorsen	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|246352681	246352681	0.5659	0.5659	2026-10-12T23:11:10.724619+00:00	56.6%
Matteo Manassero	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904701	245904701	0.003667	0.003483	2026-10-12T23:11:05.501054+00:00	0.4%
Matteo Manassero	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904833	245904833	0.027616	0.024407	2026-10-12T23:11:06.747890+00:00	2.8%
Matteo Manassero	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904965	245904965	0.065174	0.057222	2026-10-12T23:11:07.952964+00:00	6.5%
Matteo Manassero	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905097	245905097	0.153962	0.13498	2026-10-12T23:11:09.073291+00:00	15.4%
Matteo Manassero	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905229	245905229	0.602017	0.568267	2026-10-12T23:11:10.724619+00:00	60.2%
Thriston Lawrence	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904716	245904716	0.003283	0.00235	2026-10-12T23:11:05.501054+00:00	0.3%
Thriston Lawrence	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904848	245904848	0.022301	0.016265	2026-10-12T23:11:06.747890+00:00	2.2%
Thriston Lawrence	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904980	245904980	0.05278	0.038221	2026-10-12T23:11:07.952964+00:00	5.3%
Thriston Lawrence	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905112	245905112	0.126215	0.09373	2026-10-12T23:11:09.073291+00:00	12.6%
Thriston Lawrence	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905244	245905244	0.548517	0.502417	2026-10-12T23:11:10.724619+00:00	54.9%
Johannes Veerman	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904706	245904706	0.003283	0.002883	2026-10-12T23:11:05.501054+00:00	0.3%
Johannes Veerman	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904838	245904838	0.021666	0.019983	2026-10-12T23:11:06.747890+00:00	2.2%
Johannes Veerman	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904970	245904970	0.05031	0.046957	2026-10-12T23:11:07.952964+00:00	5%
Johannes Veerman	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905102	245905102	0.118544	0.109025	2026-10-12T23:11:09.073291+00:00	11.9%
Johannes Veerman	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905234	245905234	0.535883	0.5097	2026-10-12T23:11:10.724619+00:00	53.6%
Adrian Otaegui	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904704	245904704	0.003217	0.00295	2026-10-12T23:11:05.501054+00:00	0.3%
Adrian Otaegui	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904836	245904836	0.027726	0.019095	2026-10-12T23:11:06.747890+00:00	2.8%
Adrian Otaegui	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904968	245904968	0.065284	0.045546	2026-10-12T23:11:07.952964+00:00	6.5%
Adrian Otaegui	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905100	245905100	0.155329	0.10729	2026-10-12T23:11:09.073291+00:00	15.5%
Adrian Otaegui	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905232	245905232	0.599117	0.513833	2026-10-12T23:11:10.724619+00:00	59.9%
Filippo Celli	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904692	245904692	0.003117	0.004317	2026-10-12T23:11:05.501054+00:00	0.3%
Filippo Celli	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904824	245904824	0.023359	0.025659	2026-10-12T23:11:06.747890+00:00	2.3%
Filippo Celli	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904956	245904956	0.056206	0.058168	2026-10-12T23:11:07.952964+00:00	5.6%
Filippo Celli	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905088	245905088	0.133819	0.131169	2026-10-12T23:11:09.073291+00:00	13.4%
Filippo Celli	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905220	245905220	0.555967	0.547683	2026-10-12T23:11:10.724619+00:00	55.6%
Rocco Repetto Taylor	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|246352450	246352450	0.003017	0.003017	2026-10-12T23:11:05.501054+00:00	0.3%
Rocco Repetto Taylor	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|246352508	246352508	0.018782	0.018782	2026-10-12T23:11:06.747890+00:00	1.9%
Rocco Repetto Taylor	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|246352566	246352566	0.044828	0.044828	2026-10-12T23:11:07.952964+00:00	4.5%
Rocco Repetto Taylor	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|246352624	246352624	0.104544	0.104544	2026-10-12T23:11:09.073291+00:00	10.5%
Rocco Repetto Taylor	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|246352682	246352682	0.4991	0.4991	2026-10-12T23:11:10.724619+00:00	49.9%
Niklas Lemke	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904732	245904732	0.003	0.001217	2026-10-12T23:11:05.501054+00:00	0.3%
Niklas Lemke	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904864	245904864	0.019745	0.010222	2026-10-12T23:11:06.747890+00:00	2%
Niklas Lemke	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904996	245904996	0.047953	0.025972	2026-10-12T23:11:07.952964+00:00	4.8%
Niklas Lemke	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905128	245905128	0.117085	0.06541	2026-10-12T23:11:09.073291+00:00	11.7%
Niklas Lemke	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905260	245905260	0.534583	0.422433	2026-10-12T23:11:10.724619+00:00	53.5%
Felix Mory	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|246352451	246352451	0.002817	0.002817	2026-10-12T23:11:05.501054+00:00	0.3%
Felix Mory	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|246352509	246352509	0.0175	0.0175	2026-10-12T23:11:06.747890+00:00	1.8%
Felix Mory	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|246352567	246352567	0.041294	0.041294	2026-10-12T23:11:07.952964+00:00	4.1%
Felix Mory	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|246352625	246352625	0.101867	0.101867	2026-10-12T23:11:09.073291+00:00	10.2%
Felix Mory	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|246352683	246352683	0.505583	0.505583	2026-10-12T23:11:10.724619+00:00	50.6%
Kota Kaneko	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|246352452	246352452	0.002767	0.002767	2026-10-12T23:11:05.501054+00:00	0.3%
Kota Kaneko	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|246352510	246352510	0.023007	0.023007	2026-10-12T23:11:06.747890+00:00	2.3%
Kota Kaneko	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|246352568	246352568	0.057126	0.057126	2026-10-12T23:11:07.952964+00:00	5.7%
Kota Kaneko	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|246352626	246352626	0.139049	0.139049	2026-10-12T23:11:09.073291+00:00	13.9%
Kota Kaneko	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|246352684	246352684	0.57955	0.57955	2026-10-12T23:11:10.724619+00:00	58%
Sean Crocker	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904719	245904719	0.002683	0.002167	2026-10-12T23:11:05.501054+00:00	0.3%
Sean Crocker	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904851	245904851	0.021835	0.01597	2026-10-12T23:11:06.747890+00:00	2.2%
Sean Crocker	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904983	245904983	0.053001	0.037562	2026-10-12T23:11:07.952964+00:00	5.3%
Sean Crocker	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905115	245905115	0.130352	0.089801	2026-10-12T23:11:09.073291+00:00	13%
Sean Crocker	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905247	245905247	0.555317	0.4848	2026-10-12T23:11:10.724619+00:00	55.5%
Sebastian Soderberg	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904708	245904708	0.002617	0.0028	2026-10-12T23:11:05.501054+00:00	0.3%
Sebastian Soderberg	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904840	245904840	0.019013	0.020418	2026-10-12T23:11:06.747890+00:00	1.9%
Sebastian Soderberg	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904972	245904972	0.046127	0.048136	2026-10-12T23:11:07.952964+00:00	4.6%
Sebastian Soderberg	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905104	245905104	0.112257	0.110804	2026-10-12T23:11:09.073291+00:00	11.2%
Sebastian Soderberg	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905236	245905236	0.5237	0.52425	2026-10-12T23:11:10.724619+00:00	52.4%
Nicolai Von Dellingshausen	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904718	245904718	0.002517	0.0022	2026-10-12T23:11:05.501054+00:00	0.3%
Nicolai Von Dellingshausen	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904850	245904850	0.019093	0.016477	2026-10-12T23:11:06.747890+00:00	1.9%
Nicolai Von Dellingshausen	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904982	245904982	0.045335	0.039934	2026-10-12T23:11:07.952964+00:00	4.5%
Nicolai Von Dellingshausen	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905114	245905114	0.113436	0.094757	2026-10-12T23:11:09.073291+00:00	11.3%
Nicolai Von Dellingshausen	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905246	245905246	0.527633	0.491667	2026-10-12T23:11:10.724619+00:00	52.8%
Marcus Kinhult	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|246352453	246352453	0.0024	0.0024	2026-10-12T23:11:05.501054+00:00	0.2%
Marcus Kinhult	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|246352511	246352511	0.018876	0.018876	2026-10-12T23:11:06.747890+00:00	1.9%
Marcus Kinhult	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|246352569	246352569	0.045944	0.045944	2026-10-12T23:11:07.952964+00:00	4.6%
Marcus Kinhult	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|246352627	246352627	0.113828	0.113828	2026-10-12T23:11:09.073291+00:00	11.4%
Marcus Kinhult	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|246352685	246352685	0.532183	0.532183	2026-10-12T23:11:10.724619+00:00	53.2%
Daniel Rodrigues	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904709	245904709	0.002383	0.002733	2026-10-12T23:11:05.501054+00:00	0.2%
Daniel Rodrigues	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904841	245904841	0.013958	0.017295	2026-10-12T23:11:06.747890+00:00	1.4%
Daniel Rodrigues	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904973	245904973	0.035434	0.040719	2026-10-12T23:11:07.952964+00:00	3.5%
Daniel Rodrigues	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905105	245905105	0.090609	0.097818	2026-10-12T23:11:09.073291+00:00	9.1%
Daniel Rodrigues	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905237	245905237	0.489367	0.502033	2026-10-12T23:11:10.724619+00:00	48.9%
Brandon Robinson Thompson	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904710	245904710	0.002167	0.002683	2026-10-12T23:11:05.501054+00:00	0.2%
Brandon Robinson Thompson	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904842	245904842	0.018498	0.017908	2026-10-12T23:11:06.747890+00:00	1.8%
Brandon Robinson Thompson	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904974	245904974	0.04447	0.042024	2026-10-12T23:11:07.952964+00:00	4.4%
Brandon Robinson Thompson	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905106	245905106	0.112047	0.098266	2026-10-12T23:11:09.073291+00:00	11.2%
Brandon Robinson Thompson	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905238	245905238	0.529333	0.496167	2026-10-12T23:11:10.724619+00:00	52.9%
Jorge Campillo	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904717	245904717	0.001983	0.002267	2026-10-12T23:11:05.501054+00:00	0.2%
Jorge Campillo	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904849	245904849	0.017555	0.017137	2026-10-12T23:11:06.747890+00:00	1.8%
Jorge Campillo	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904981	245904981	0.044821	0.042012	2026-10-12T23:11:07.952964+00:00	4.5%
Jorge Campillo	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905113	245905113	0.113016	0.103475	2026-10-12T23:11:09.073291+00:00	11.3%
Jorge Campillo	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905245	245905245	0.537633	0.507833	2026-10-12T23:11:10.724619+00:00	53.8%
Anirban Lahiri	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|246352454	246352454	0.001933	0.001933	2026-10-12T23:11:05.501054+00:00	0.2%
Anirban Lahiri	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|246352512	246352512	0.014551	0.014551	2026-10-12T23:11:06.747890+00:00	1.5%
Anirban Lahiri	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|246352570	246352570	0.03544	0.03544	2026-10-12T23:11:07.952964+00:00	3.5%
Anirban Lahiri	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|246352628	246352628	0.089762	0.089762	2026-10-12T23:11:09.073291+00:00	9%
Anirban Lahiri	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|246352686	246352686	0.475333	0.475333	2026-10-12T23:11:10.724619+00:00	47.5%
Eddie Pepperell	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904712	245904712	0.001933	0.002567	2026-10-12T23:11:05.501054+00:00	0.2%
Eddie Pepperell	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904844	245904844	0.01725	0.019121	2026-10-12T23:11:06.747890+00:00	1.7%
Eddie Pepperell	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904976	245904976	0.043049	0.04524	2026-10-12T23:11:07.952964+00:00	4.3%
Eddie Pepperell	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905108	245905108	0.108751	0.110302	2026-10-12T23:11:09.073291+00:00	10.9%
Eddie Pepperell	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905240	245905240	0.534283	0.533017	2026-10-12T23:11:10.724619+00:00	53.4%
Quim Vidal	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904727	245904727	0.001917	0.001483	2026-10-12T23:11:05.501054+00:00	0.2%
Quim Vidal	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904859	245904859	0.013864	0.010804	2026-10-12T23:11:06.747890+00:00	1.4%
Quim Vidal	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904991	245904991	0.033742	0.027653	2026-10-12T23:11:07.952964+00:00	3.4%
Quim Vidal	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905123	245905123	0.085744	0.067447	2026-10-12T23:11:09.073291+00:00	8.6%
Quim Vidal	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905255	245905255	0.476467	0.436933	2026-10-12T23:11:10.724619+00:00	47.6%
Jason Scrivener	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904725	245904725	0.001917	0.001533	2026-10-12T23:11:05.501054+00:00	0.2%
Jason Scrivener	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904857	245904857	0.014442	0.01304	2026-10-12T23:11:06.747890+00:00	1.4%
Jason Scrivener	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904989	245904989	0.037729	0.032671	2026-10-12T23:11:07.952964+00:00	3.8%
Jason Scrivener	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905121	245905121	0.096087	0.083857	2026-10-12T23:11:09.073291+00:00	9.6%
Jason Scrivener	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905253	245905253	0.513567	0.487217	2026-10-12T23:11:10.724619+00:00	51.4%
Grant Forrest	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904743	245904743	0.001883	0.000833	2026-10-12T23:11:05.501054+00:00	0.2%
Grant Forrest	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904875	245904875	0.014801	0.006287	2026-10-12T23:11:06.747890+00:00	1.5%
Grant Forrest	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245905007	245905007	0.035881	0.016273	2026-10-12T23:11:07.952964+00:00	3.6%
Grant Forrest	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905139	245905139	0.091251	0.044779	2026-10-12T23:11:09.073291+00:00	9.1%
Grant Forrest	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905271	245905271	0.485333	0.36525	2026-10-12T23:11:10.724619+00:00	48.5%
Euan Walker	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|246352455	246352455	0.001833	0.001833	2026-10-12T23:11:05.501054+00:00	0.2%
Euan Walker	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|246352513	246352513	0.014952	0.014952	2026-10-12T23:11:06.747890+00:00	1.5%
Euan Walker	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|246352571	246352571	0.038123	0.038123	2026-10-12T23:11:07.952964+00:00	3.8%
Euan Walker	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|246352629	246352629	0.098529	0.098529	2026-10-12T23:11:09.073291+00:00	9.9%
Euan Walker	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|246352687	246352687	0.51695	0.51695	2026-10-12T23:11:10.724619+00:00	51.7%
Ricardo Gouveia	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904711	245904711	0.001833	0.002617	2026-10-12T23:11:05.501054+00:00	0.2%
Ricardo Gouveia	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904843	245904843	0.0156	0.017994	2026-10-12T23:11:06.747890+00:00	1.6%
Ricardo Gouveia	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904975	245904975	0.038436	0.04219	2026-10-12T23:11:07.952964+00:00	3.8%
Ricardo Gouveia	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905107	245905107	0.094628	0.099911	2026-10-12T23:11:09.073291+00:00	9.5%
Ricardo Gouveia	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905239	245905239	0.494467	0.49875	2026-10-12T23:11:10.724619+00:00	49.4%
Ross Fisher	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904702	245904702	0.001767	0.003467	2026-10-12T23:11:05.501054+00:00	0.2%
Ross Fisher	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904834	245904834	0.014393	0.022761	2026-10-12T23:11:06.747890+00:00	1.4%
Ross Fisher	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904966	245904966	0.036916	0.052196	2026-10-12T23:11:07.952964+00:00	3.7%
Ross Fisher	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905098	245905098	0.09411	0.119435	2026-10-12T23:11:09.073291+00:00	9.4%
Ross Fisher	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905230	245905230	0.49705	0.541217	2026-10-12T23:11:10.724619+00:00	49.7%
Michael Hollick	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904714	245904714	0.001767	0.002367	2026-10-12T23:11:05.501054+00:00	0.2%
Michael Hollick	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904846	245904846	0.014155	0.016907	2026-10-12T23:11:06.747890+00:00	1.4%
Michael Hollick	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904978	245904978	0.036345	0.039834	2026-10-12T23:11:07.952964+00:00	3.6%
Michael Hollick	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905110	245905110	0.093526	0.096601	2026-10-12T23:11:09.073291+00:00	9.4%
Michael Hollick	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905242	245905242	0.495183	0.489417	2026-10-12T23:11:10.724619+00:00	49.5%
Rikuya Hoshino	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904726	245904726	0.001717	0.0015	2026-10-12T23:11:05.501054+00:00	0.2%
Rikuya Hoshino	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904858	245904858	0.012593	0.013243	2026-10-12T23:11:06.747890+00:00	1.3%
Rikuya Hoshino	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904990	245904990	0.033242	0.033968	2026-10-12T23:11:07.952964+00:00	3.3%
Rikuya Hoshino	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905122	245905122	0.088129	0.085972	2026-10-12T23:11:09.073291+00:00	8.8%
Rikuya Hoshino	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905254	245905254	0.488833	0.49045	2026-10-12T23:11:10.724619+00:00	48.9%
Kiradech Aphibarnrat	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904740	245904740	0.001683	0.001	2026-10-12T23:11:05.501054+00:00	0.2%
Kiradech Aphibarnrat	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904872	245904872	0.013275	0.008864	2026-10-12T23:11:06.747890+00:00	1.3%
Kiradech Aphibarnrat	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245905004	245905004	0.034873	0.023638	2026-10-12T23:11:07.952964+00:00	3.5%
Kiradech Aphibarnrat	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905136	245905136	0.088254	0.063082	2026-10-12T23:11:09.073291+00:00	8.8%
Kiradech Aphibarnrat	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905268	245905268	0.486183	0.433283	2026-10-12T23:11:10.724619+00:00	48.6%
Cameron Adam	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|246352456	246352456	0.001683	0.001683	2026-10-12T23:11:05.501054+00:00	0.2%
Cameron Adam	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|246352514	246352514	0.012837	0.012837	2026-10-12T23:11:06.747890+00:00	1.3%
Cameron Adam	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|246352572	246352572	0.032222	0.032222	2026-10-12T23:11:07.952964+00:00	3.2%
Cameron Adam	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|246352630	246352630	0.081851	0.081851	2026-10-12T23:11:09.073291+00:00	8.2%
Cameron Adam	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|246352688	246352688	0.465133	0.465133	2026-10-12T23:11:10.724619+00:00	46.5%
Ivan Cantero Gutierrez	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904722	245904722	0.001633	0.0019	2026-10-12T23:11:05.501054+00:00	0.2%
Ivan Cantero Gutierrez	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904854	245904854	0.012875	0.013299	2026-10-12T23:11:06.747890+00:00	1.3%
Ivan Cantero Gutierrez	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904986	245904986	0.033313	0.030943	2026-10-12T23:11:07.952964+00:00	3.3%
Ivan Cantero Gutierrez	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905118	245905118	0.085331	0.078215	2026-10-12T23:11:09.073291+00:00	8.5%
Ivan Cantero Gutierrez	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905250	245905250	0.472867	0.450483	2026-10-12T23:11:10.724619+00:00	47.3%
Scott Jamieson	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|246352457	246352457	0.001617	0.001617	2026-10-12T23:11:05.501054+00:00	0.2%
Scott Jamieson	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|246352515	246352515	0.012958	0.012958	2026-10-12T23:11:06.747890+00:00	1.3%
Scott Jamieson	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|246352573	246352573	0.033822	0.033822	2026-10-12T23:11:07.952964+00:00	3.4%
Scott Jamieson	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|246352631	246352631	0.086415	0.086415	2026-10-12T23:11:09.073291+00:00	8.6%
Scott Jamieson	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|246352689	246352689	0.48625	0.48625	2026-10-12T23:11:10.724619+00:00	48.6%
Stefano Mazzoli	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904734	245904734	0.001617	0.001133	2026-10-12T23:11:05.501054+00:00	0.2%
Stefano Mazzoli	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904866	245904866	0.013017	0.00938	2026-10-12T23:11:06.747890+00:00	1.3%
Stefano Mazzoli	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904998	245904998	0.033304	0.023377	2026-10-12T23:11:07.952964+00:00	3.3%
Stefano Mazzoli	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905130	245905130	0.087677	0.058113	2026-10-12T23:11:09.073291+00:00	8.8%
Stefano Mazzoli	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905262	245905262	0.486483	0.400067	2026-10-12T23:11:10.724619+00:00	48.6%
Renato Paratore	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904724	245904724	0.001517	0.00155	2026-10-12T23:11:05.501054+00:00	0.2%
Renato Paratore	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904856	245904856	0.011784	0.012101	2026-10-12T23:11:06.747890+00:00	1.2%
Renato Paratore	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904988	245904988	0.029505	0.029959	2026-10-12T23:11:07.952964+00:00	3%
Renato Paratore	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905120	245905120	0.077616	0.074319	2026-10-12T23:11:09.073291+00:00	7.8%
Renato Paratore	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905252	245905252	0.464017	0.4587	2026-10-12T23:11:10.724619+00:00	46.4%
Ben Schmidt	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904729	245904729	0.001517	0.00145	2026-10-12T23:11:05.501054+00:00	0.2%
Ben Schmidt	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904861	245904861	0.013372	0.011456	2026-10-12T23:11:06.747890+00:00	1.3%
Ben Schmidt	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904993	245904993	0.032945	0.028746	2026-10-12T23:11:07.952964+00:00	3.3%
Ben Schmidt	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905125	245905125	0.083536	0.071799	2026-10-12T23:11:09.073291+00:00	8.4%
Ben Schmidt	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905257	245905257	0.47545	0.435383	2026-10-12T23:11:10.724619+00:00	47.5%
Elvis Smylie	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904715	245904715	0.001467	0.002367	2026-10-12T23:11:05.501054+00:00	0.1%
Elvis Smylie	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904847	245904847	0.013238	0.01582	2026-10-12T23:11:06.747890+00:00	1.3%
Elvis Smylie	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904979	245904979	0.03503	0.037297	2026-10-12T23:11:07.952964+00:00	3.5%
Elvis Smylie	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905111	245905111	0.089542	0.090707	2026-10-12T23:11:09.073291+00:00	9%
Elvis Smylie	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905243	245905243	0.494033	0.49255	2026-10-12T23:11:10.724619+00:00	49.4%
Dylan Frittelli	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904733	245904733	0.00145	0.001217	2026-10-12T23:11:05.501054+00:00	0.1%
Dylan Frittelli	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904865	245904865	0.011123	0.009565	2026-10-12T23:11:06.747890+00:00	1.1%
Dylan Frittelli	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904997	245904997	0.02788	0.023235	2026-10-12T23:11:07.952964+00:00	2.8%
Dylan Frittelli	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905129	245905129	0.072097	0.060147	2026-10-12T23:11:09.073291+00:00	7.2%
Dylan Frittelli	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905261	245905261	0.448417	0.4159	2026-10-12T23:11:10.724619+00:00	44.8%
Jens Dantorp	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904739	245904739	0.001383	0.001033	2026-10-12T23:11:05.501054+00:00	0.1%
Jens Dantorp	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904871	245904871	0.012735	0.008532	2026-10-12T23:11:06.747890+00:00	1.3%
Jens Dantorp	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245905003	245905003	0.032848	0.021959	2026-10-12T23:11:07.952964+00:00	3.3%
Jens Dantorp	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905135	245905135	0.085075	0.059352	2026-10-12T23:11:09.073291+00:00	8.5%
Jens Dantorp	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905267	245905267	0.47925	0.429317	2026-10-12T23:11:10.724619+00:00	47.9%
Tobias Jonsson	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|246352458	246352458	0.001267	0.001267	2026-10-12T23:11:05.501054+00:00	0.1%
Tobias Jonsson	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|246352516	246352516	0.009385	0.009385	2026-10-12T23:11:06.747890+00:00	0.9%
Tobias Jonsson	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|246352574	246352574	0.025343	0.025343	2026-10-12T23:11:07.952964+00:00	2.5%
Tobias Jonsson	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|246352632	246352632	0.066312	0.066312	2026-10-12T23:11:09.073291+00:00	6.6%
Tobias Jonsson	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|246352690	246352690	0.430617	0.430617	2026-10-12T23:11:10.724619+00:00	43.1%
Rafa Cabrera Bello	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904735	245904735	0.001133	0.001117	2026-10-12T23:11:05.501054+00:00	0.1%
Rafa Cabrera Bello	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904867	245904867	0.008761	0.009415	2026-10-12T23:11:06.747890+00:00	0.9%
Rafa Cabrera Bello	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904999	245904999	0.022725	0.023744	2026-10-12T23:11:07.952964+00:00	2.3%
Rafa Cabrera Bello	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905131	245905131	0.061085	0.061997	2026-10-12T23:11:09.073291+00:00	6.1%
Rafa Cabrera Bello	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905263	245905263	0.421317	0.42725	2026-10-12T23:11:10.724619+00:00	42.1%
Albin Bergstrom	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|246352459	246352459	0.001067	0.001067	2026-10-12T23:11:05.501054+00:00	0.1%
Albin Bergstrom	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|246352517	246352517	0.009029	0.009029	2026-10-12T23:11:06.747890+00:00	0.9%
Albin Bergstrom	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|246352575	246352575	0.023097	0.023097	2026-10-12T23:11:07.952964+00:00	2.3%
Albin Bergstrom	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|246352633	246352633	0.062457	0.062457	2026-10-12T23:11:09.073291+00:00	6.2%
Albin Bergstrom	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|246352691	246352691	0.420233	0.420233	2026-10-12T23:11:10.724619+00:00	42%
Hugo Townsend	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|246352460	246352460	0.001033	0.001033	2026-10-12T23:11:05.501054+00:00	0.1%
Hugo Townsend	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|246352518	246352518	0.008106	0.008106	2026-10-12T23:11:06.747890+00:00	0.8%
Hugo Townsend	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|246352576	246352576	0.02202	0.02202	2026-10-12T23:11:07.952964+00:00	2.2%
Hugo Townsend	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|246352634	246352634	0.058898	0.058898	2026-10-12T23:11:09.073291+00:00	5.9%
Hugo Townsend	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|246352692	246352692	0.4084	0.4084	2026-10-12T23:11:10.724619+00:00	40.8%
Pablo Larrazabal	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904745	245904745	0.001	0.0007	2026-10-12T23:11:05.501054+00:00	0.1%
Pablo Larrazabal	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904877	245904877	0.010292	0.008024	2026-10-12T23:11:06.747890+00:00	1%
Pablo Larrazabal	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245905009	245905009	0.02783	0.02112	2026-10-12T23:11:07.952964+00:00	2.8%
Pablo Larrazabal	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905141	245905141	0.077976	0.055295	2026-10-12T23:11:09.073291+00:00	7.8%
Pablo Larrazabal	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905273	245905273	0.4696	0.401033	2026-10-12T23:11:10.724619+00:00	47%
Danny Willett	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904730	245904730	0.000967	0.0014	2026-10-12T23:11:05.501054+00:00	<0.1%
Danny Willett	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904862	245904862	0.008874	0.011237	2026-10-12T23:11:06.747890+00:00	0.9%
Danny Willett	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904994	245904994	0.023306	0.029053	2026-10-12T23:11:07.952964+00:00	2.3%
Danny Willett	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905126	245905126	0.063677	0.074663	2026-10-12T23:11:09.073291+00:00	6.4%
Danny Willett	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905258	245905258	0.432917	0.45445	2026-10-12T23:11:10.724619+00:00	43.3%
Jordan Gumberg	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904741	245904741	0.000967	0.001	2026-10-12T23:11:05.501054+00:00	<0.1%
Jordan Gumberg	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904873	245904873	0.007162	0.007327	2026-10-12T23:11:06.747890+00:00	0.7%
Jordan Gumberg	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245905005	245905005	0.019184	0.018185	2026-10-12T23:11:07.952964+00:00	1.9%
Jordan Gumberg	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905137	245905137	0.051956	0.047579	2026-10-12T23:11:09.073291+00:00	5.2%
Jordan Gumberg	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905269	245905269	0.3893	0.372567	2026-10-12T23:11:10.724619+00:00	38.9%
Marcel Siem	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904744	245904744	0.00095	0.000767	2026-10-12T23:11:05.501054+00:00	<0.1%
Marcel Siem	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904876	245904876	0.007853	0.006524	2026-10-12T23:11:06.747890+00:00	0.8%
Marcel Siem	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245905008	245905008	0.019472	0.017103	2026-10-12T23:11:07.952964+00:00	1.9%
Marcel Siem	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905140	245905140	0.052122	0.045231	2026-10-12T23:11:09.073291+00:00	5.2%
Marcel Siem	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905272	245905272	0.386117	0.371817	2026-10-12T23:11:10.724619+00:00	38.6%
Jack Senior	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904738	245904738	0.00095	0.00105	2026-10-12T23:11:05.501054+00:00	<0.1%
Jack Senior	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904870	245904870	0.007972	0.009501	2026-10-12T23:11:06.747890+00:00	0.8%
Jack Senior	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245905002	245905002	0.022691	0.024657	2026-10-12T23:11:07.952964+00:00	2.3%
Jack Senior	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905134	245905134	0.06294	0.064513	2026-10-12T23:11:09.073291+00:00	6.3%
Jack Senior	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905266	245905266	0.432633	0.4259	2026-10-12T23:11:10.724619+00:00	43.3%
Veer Ahlawat	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|246352461	246352461	0.00095	0.00095	2026-10-12T23:11:05.501054+00:00	<0.1%
Veer Ahlawat	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|246352519	246352519	0.006857	0.006857	2026-10-12T23:11:06.747890+00:00	0.7%
Veer Ahlawat	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|246352577	246352577	0.019083	0.019083	2026-10-12T23:11:07.952964+00:00	1.9%
Veer Ahlawat	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|246352635	246352635	0.054782	0.054782	2026-10-12T23:11:09.073291+00:00	5.5%
Veer Ahlawat	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|246352693	246352693	0.40625	0.40625	2026-10-12T23:11:10.724619+00:00	40.6%
Yurav Premlall	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904721	245904721	0.000867	0.00195	2026-10-12T23:11:05.501054+00:00	<0.1%
Yurav Premlall	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904853	245904853	0.007758	0.013825	2026-10-12T23:11:06.747890+00:00	0.8%
Yurav Premlall	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904985	245904985	0.021476	0.033153	2026-10-12T23:11:07.952964+00:00	2.1%
Yurav Premlall	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905117	245905117	0.061829	0.084631	2026-10-12T23:11:09.073291+00:00	6.2%
Yurav Premlall	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905249	245905249	0.429717	0.481533	2026-10-12T23:11:10.724619+00:00	43%
Daniel Young	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|246352462	246352462	0.000833	0.000833	2026-10-12T23:11:05.501054+00:00	<0.1%
Daniel Young	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|246352520	246352520	0.007498	0.007498	2026-10-12T23:11:06.747890+00:00	0.7%
Daniel Young	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|246352578	246352578	0.020486	0.020486	2026-10-12T23:11:07.952964+00:00	2%
Daniel Young	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|246352636	246352636	0.05906	0.05906	2026-10-12T23:11:09.073291+00:00	5.9%
Daniel Young	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|246352694	246352694	0.416433	0.416433	2026-10-12T23:11:10.724619+00:00	41.6%
Junghwan Lee	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|246352463	246352463	0.000783	0.000783	2026-10-12T23:11:05.501054+00:00	<0.1%
Junghwan Lee	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|246352521	246352521	0.006227	0.006227	2026-10-12T23:11:06.747890+00:00	0.6%
Junghwan Lee	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|246352579	246352579	0.017676	0.017676	2026-10-12T23:11:07.952964+00:00	1.8%
Junghwan Lee	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|246352637	246352637	0.050664	0.050664	2026-10-12T23:11:09.073291+00:00	5.1%
Junghwan Lee	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|246352695	246352695	0.394933	0.394933	2026-10-12T23:11:10.724619+00:00	39.5%
Yuvraj Singh Sandhu	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|246352464	246352464	0.000783	0.000783	2026-10-12T23:11:05.501054+00:00	<0.1%
Yuvraj Singh Sandhu	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|246352522	246352522	0.007051	0.007051	2026-10-12T23:11:06.747890+00:00	0.7%
Yuvraj Singh Sandhu	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|246352580	246352580	0.019385	0.019385	2026-10-12T23:11:07.952964+00:00	1.9%
Yuvraj Singh Sandhu	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|246352638	246352638	0.054996	0.054996	2026-10-12T23:11:09.073291+00:00	5.5%
Yuvraj Singh Sandhu	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|246352696	246352696	0.408533	0.408533	2026-10-12T23:11:10.724619+00:00	40.9%
Richard Sterne	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904747	245904747	0.000767	0.00045	2026-10-12T23:11:05.501054+00:00	<0.1%
Richard Sterne	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904879	245904879	0.006821	0.004633	2026-10-12T23:11:06.747890+00:00	0.7%
Richard Sterne	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245905011	245905011	0.018211	0.013393	2026-10-12T23:11:07.952964+00:00	1.8%
Richard Sterne	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905143	245905143	0.050171	0.039476	2026-10-12T23:11:09.073291+00:00	5%
Richard Sterne	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905275	245905275	0.39765	0.359417	2026-10-12T23:11:10.724619+00:00	39.8%
Zander Lombard	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|246352465	246352465	0.000733	0.000733	2026-10-12T23:11:05.501054+00:00	<0.1%
Zander Lombard	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|246352523	246352523	0.005792	0.005792	2026-10-12T23:11:06.747890+00:00	0.6%
Zander Lombard	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|246352581	246352581	0.015231	0.015231	2026-10-12T23:11:07.952964+00:00	1.5%
Zander Lombard	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|246352639	246352639	0.044419	0.044419	2026-10-12T23:11:09.073291+00:00	4.4%
Zander Lombard	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|246352697	246352697	0.371683	0.371683	2026-10-12T23:11:10.724619+00:00	37.2%
Sebastian Garcia Rodriguez	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904731	245904731	0.000633	0.001283	2026-10-12T23:11:05.501054+00:00	<0.1%
Sebastian Garcia Rodriguez	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904863	245904863	0.006316	0.00862	2026-10-12T23:11:06.747890+00:00	0.6%
Sebastian Garcia Rodriguez	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904995	245904995	0.017587	0.022792	2026-10-12T23:11:07.952964+00:00	1.8%
Sebastian Garcia Rodriguez	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905127	245905127	0.050005	0.057551	2026-10-12T23:11:09.073291+00:00	5%
Sebastian Garcia Rodriguez	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905259	245905259	0.38915	0.41085	2026-10-12T23:11:10.724619+00:00	38.9%
Gaganjeet Bhullar	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|246352466	246352466	0.000633	0.000633	2026-10-12T23:11:05.501054+00:00	<0.1%
Gaganjeet Bhullar	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|246352524	246352524	0.005499	0.005499	2026-10-12T23:11:06.747890+00:00	0.5%
Gaganjeet Bhullar	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|246352582	246352582	0.015048	0.015048	2026-10-12T23:11:07.952964+00:00	1.5%
Gaganjeet Bhullar	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|246352640	246352640	0.044568	0.044568	2026-10-12T23:11:09.073291+00:00	4.5%
Gaganjeet Bhullar	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|246352698	246352698	0.35735	0.35735	2026-10-12T23:11:10.724619+00:00	35.7%
Luke Donald	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|246352467	246352467	0.000583	0.000583	2026-10-12T23:11:05.501054+00:00	<0.1%
Luke Donald	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|246352525	246352525	0.005684	0.005684	2026-10-12T23:11:06.747890+00:00	0.6%
Luke Donald	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|246352583	246352583	0.015558	0.015558	2026-10-12T23:11:07.952964+00:00	1.6%
Luke Donald	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|246352641	246352641	0.046964	0.046964	2026-10-12T23:11:09.073291+00:00	4.7%
Luke Donald	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|246352699	246352699	0.39245	0.39245	2026-10-12T23:11:10.724619+00:00	39.2%
Khalin H Joshi	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|246352468	246352468	0.00055	0.00055	2026-10-12T23:11:05.501054+00:00	<0.1%
Khalin H Joshi	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|246352526	246352526	0.003752	0.003752	2026-10-12T23:11:06.747890+00:00	0.4%
Khalin H Joshi	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|246352584	246352584	0.01104	0.01104	2026-10-12T23:11:07.952964+00:00	1.1%
Khalin H Joshi	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|246352642	246352642	0.034616	0.034616	2026-10-12T23:11:09.073291+00:00	3.5%
Khalin H Joshi	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|246352700	246352700	0.339533	0.339533	2026-10-12T23:11:10.724619+00:00	34%
Shaurya Bhattacharya	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|246352469	246352469	0.0005	0.0005	2026-10-12T23:11:05.501054+00:00	<0.1%
Shaurya Bhattacharya	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|246352527	246352527	0.004559	0.004559	2026-10-12T23:11:06.747890+00:00	0.5%
Shaurya Bhattacharya	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|246352585	246352585	0.012316	0.012316	2026-10-12T23:11:07.952964+00:00	1.2%
Shaurya Bhattacharya	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|246352643	246352643	0.035675	0.035675	2026-10-12T23:11:09.073291+00:00	3.6%
Shaurya Bhattacharya	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|246352701	246352701	0.349217	0.349217	2026-10-12T23:11:10.724619+00:00	34.9%
Karandeep Kochhar	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|246352470	246352470	0.000433	0.000433	2026-10-12T23:11:05.501054+00:00	<0.1%
Karandeep Kochhar	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|246352528	246352528	0.003853	0.003853	2026-10-12T23:11:06.747890+00:00	0.4%
Karandeep Kochhar	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|246352586	246352586	0.010431	0.010431	2026-10-12T23:11:07.952964+00:00	1%
Karandeep Kochhar	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|246352644	246352644	0.031351	0.031351	2026-10-12T23:11:09.073291+00:00	3.1%
Karandeep Kochhar	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|246352702	246352702	0.3302	0.3302	2026-10-12T23:11:10.724619+00:00	33%
Anthony Quayle	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|246352471	246352471	0.000417	0.000417	2026-10-12T23:11:05.501054+00:00	<0.1%
Anthony Quayle	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|246352529	246352529	0.003178	0.003178	2026-10-12T23:11:06.747890+00:00	0.3%
Anthony Quayle	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|246352587	246352587	0.009059	0.009059	2026-10-12T23:11:07.952964+00:00	0.9%
Anthony Quayle	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|246352645	246352645	0.028636	0.028636	2026-10-12T23:11:09.073291+00:00	2.9%
Anthony Quayle	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|246352703	246352703	0.310483	0.310483	2026-10-12T23:11:10.724619+00:00	31%
Shubhankar Sharma	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|246352472	246352472	0.000383	0.000383	2026-10-12T23:11:05.501054+00:00	<0.1%
Shubhankar Sharma	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|246352530	246352530	0.003972	0.003972	2026-10-12T23:11:06.747890+00:00	0.4%
Shubhankar Sharma	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|246352588	246352588	0.012081	0.012081	2026-10-12T23:11:07.952964+00:00	1.2%
Shubhankar Sharma	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|246352646	246352646	0.034549	0.034549	2026-10-12T23:11:09.073291+00:00	3.5%
Shubhankar Sharma	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|246352704	246352704	0.345817	0.345817	2026-10-12T23:11:10.724619+00:00	34.6%
Ryan Peake	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|246352473	246352473	0.000367	0.000367	2026-10-12T23:11:05.501054+00:00	<0.1%
Ryan Peake	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|246352531	246352531	0.003429	0.003429	2026-10-12T23:11:06.747890+00:00	0.3%
Ryan Peake	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|246352589	246352589	0.010212	0.010212	2026-10-12T23:11:07.952964+00:00	1%
Ryan Peake	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|246352647	246352647	0.028998	0.028998	2026-10-12T23:11:09.073291+00:00	2.9%
Ryan Peake	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|246352705	246352705	0.315867	0.315867	2026-10-12T23:11:10.724619+00:00	31.6%
Jeong Weon Ko	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904753	245904753	0.00035	0.000183	2026-10-12T23:11:05.501054+00:00	<0.1%
Jeong Weon Ko	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904885	245904885	0.00272	0.001893	2026-10-12T23:11:06.747890+00:00	0.3%
Jeong Weon Ko	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245905017	245905017	0.007551	0.006145	2026-10-12T23:11:07.952964+00:00	0.8%
Jeong Weon Ko	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905149	245905149	0.021783	0.018329	2026-10-12T23:11:09.073291+00:00	2.2%
Jeong Weon Ko	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905281	245905281	0.2707	0.256633	2026-10-12T23:11:10.724619+00:00	27.1%
James Morrison	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904748	245904748	0.000317	0.000417	2026-10-12T23:11:05.501054+00:00	<0.1%
James Morrison	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904880	245904880	0.003667	0.004102	2026-10-12T23:11:06.747890+00:00	0.4%
James Morrison	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245905012	245905012	0.011313	0.011861	2026-10-12T23:11:07.952964+00:00	1.1%
James Morrison	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905144	245905144	0.034577	0.034241	2026-10-12T23:11:09.073291+00:00	3.5%
James Morrison	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905276	245905276	0.35795	0.359633	2026-10-12T23:11:10.724619+00:00	35.8%
Matthew Baldwin	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|246352474	246352474	0.000233	0.000233	2026-10-12T23:11:05.501054+00:00	<0.1%
Matthew Baldwin	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|246352532	246352532	0.002265	0.002265	2026-10-12T23:11:06.747890+00:00	0.2%
Matthew Baldwin	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|246352590	246352590	0.006926	0.006926	2026-10-12T23:11:07.952964+00:00	0.7%
Matthew Baldwin	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|246352648	246352648	0.022391	0.022391	2026-10-12T23:11:09.073291+00:00	2.2%
Matthew Baldwin	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|246352706	246352706	0.289933	0.289933	2026-10-12T23:11:10.724619+00:00	29%
Dylan Naidoo	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904752	245904752	0.0002	0.00025	2026-10-12T23:11:05.501054+00:00	<0.1%
Dylan Naidoo	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904884	245904884	0.002109	0.00275	2026-10-12T23:11:06.747890+00:00	0.2%
Dylan Naidoo	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245905016	245905016	0.006158	0.007537	2026-10-12T23:11:07.952964+00:00	0.6%
Dylan Naidoo	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905148	245905148	0.020476	0.022551	2026-10-12T23:11:09.073291+00:00	2%
Dylan Naidoo	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905280	245905280	0.2782	0.281317	2026-10-12T23:11:10.724619+00:00	27.8%
Joshua Berry	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|246352475	246352475	0.000183	0.000183	2026-10-12T23:11:05.501054+00:00	<0.1%
Joshua Berry	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|246352533	246352533	0.001148	0.001148	2026-10-12T23:11:06.747890+00:00	0.1%
Joshua Berry	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|246352591	246352591	0.003486	0.003486	2026-10-12T23:11:07.952964+00:00	0.3%
Joshua Berry	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|246352649	246352649	0.011137	0.011137	2026-10-12T23:11:09.073291+00:00	1.1%
Joshua Berry	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|246352707	246352707	0.217867	0.217867	2026-10-12T23:11:10.724619+00:00	21.8%
Saptak Talwar	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|246352476	246352476	0.000167	0.000167	2026-10-12T23:11:05.501054+00:00	<0.1%
Saptak Talwar	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|246352534	246352534	0.002249	0.002249	2026-10-12T23:11:06.747890+00:00	0.2%
Saptak Talwar	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|246352592	246352592	0.007107	0.007107	2026-10-12T23:11:07.952964+00:00	0.7%
Saptak Talwar	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|246352650	246352650	0.022512	0.022512	2026-10-12T23:11:09.073291+00:00	2.3%
Saptak Talwar	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|246352708	246352708	0.290667	0.290667	2026-10-12T23:11:10.724619+00:00	29.1%
Honey Baisoya	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|246352477	246352477	0.000133	0.000133	2026-10-12T23:11:05.501054+00:00	<0.1%
Honey Baisoya	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|246352535	246352535	0.000721	0.000721	2026-10-12T23:11:06.747890+00:00	<0.1%
Honey Baisoya	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|246352593	246352593	0.002336	0.002336	2026-10-12T23:11:07.952964+00:00	0.2%
Honey Baisoya	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|246352651	246352651	0.007006	0.007006	2026-10-12T23:11:09.073291+00:00	0.7%
Honey Baisoya	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|246352709	246352709	0.1586	0.1586	2026-10-12T23:11:10.724619+00:00	15.9%
Ryggs Johnston	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904754	245904754	0.000117	0.00015	2026-10-12T23:11:05.501054+00:00	<0.1%
Ryggs Johnston	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904886	245904886	0.001694	0.001917	2026-10-12T23:11:06.747890+00:00	0.2%
Ryggs Johnston	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245905018	245905018	0.004942	0.005013	2026-10-12T23:11:07.952964+00:00	0.5%
Ryggs Johnston	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905150	245905150	0.016375	0.014793	2026-10-12T23:11:09.073291+00:00	1.6%
Ryggs Johnston	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905282	245905282	0.249533	0.228817	2026-10-12T23:11:10.724619+00:00	25%
Rashid Khan	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|246352479	246352479	0.0001	0.0001	2026-10-12T23:11:05.501054+00:00	<0.1%
Rashid Khan	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|246352537	246352537	0.000944	0.000944	2026-10-12T23:11:06.747890+00:00	<0.1%
Rashid Khan	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|246352595	246352595	0.003313	0.003313	2026-10-12T23:11:07.952964+00:00	0.3%
Rashid Khan	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|246352653	246352653	0.010602	0.010602	2026-10-12T23:11:09.073291+00:00	1.1%
Rashid Khan	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|246352711	246352711	0.20485	0.20485	2026-10-12T23:11:10.724619+00:00	20.5%
Manu Gandas	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|246352478	246352478	0.0001	0.0001	2026-10-12T23:11:05.501054+00:00	<0.1%
Manu Gandas	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|246352536	246352536	0.001027	0.001027	2026-10-12T23:11:06.747890+00:00	0.1%
Manu Gandas	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|246352594	246352594	0.003442	0.003442	2026-10-12T23:11:07.952964+00:00	0.3%
Manu Gandas	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|246352652	246352652	0.011722	0.011722	2026-10-12T23:11:09.073291+00:00	1.2%
Manu Gandas	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|246352710	246352710	0.217733	0.217733	2026-10-12T23:11:10.724619+00:00	21.8%
Angad Cheema	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|246352480	246352480	8.3e-05	8.3e-05	2026-10-12T23:11:05.501054+00:00	<0.1%
Angad Cheema	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|246352538	246352538	0.001342	0.001342	2026-10-12T23:11:06.747890+00:00	0.1%
Angad Cheema	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|246352596	246352596	0.004195	0.004195	2026-10-12T23:11:07.952964+00:00	0.4%
Angad Cheema	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|246352654	246352654	0.014509	0.014509	2026-10-12T23:11:09.073291+00:00	1.5%
Angad Cheema	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|246352712	246352712	0.235817	0.235817	2026-10-12T23:11:10.724619+00:00	23.6%
Dhruv Sheoran	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|246352481	246352481	6.7e-05	6.7e-05	2026-10-12T23:11:05.501054+00:00	<0.1%
Dhruv Sheoran	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|246352539	246352539	0.000711	0.000711	2026-10-12T23:11:06.747890+00:00	<0.1%
Dhruv Sheoran	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|246352597	246352597	0.002336	0.002336	2026-10-12T23:11:07.952964+00:00	0.2%
Dhruv Sheoran	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|246352655	246352655	0.008559	0.008559	2026-10-12T23:11:09.073291+00:00	0.9%
Dhruv Sheoran	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|246352713	246352713	0.19225	0.19225	2026-10-12T23:11:10.724619+00:00	19.2%
Amardip Malik	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|246352482	246352482	5e-05	5e-05	2026-10-12T23:11:05.501054+00:00	<0.1%
Amardip Malik	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|246352540	246352540	0.000623	0.000623	2026-10-12T23:11:06.747890+00:00	<0.1%
Amardip Malik	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|246352598	246352598	0.002052	0.002052	2026-10-12T23:11:07.952964+00:00	0.2%
Amardip Malik	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|246352656	246352656	0.008313	0.008313	2026-10-12T23:11:09.073291+00:00	0.8%
Amardip Malik	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|246352714	246352714	0.194567	0.194567	2026-10-12T23:11:10.724619+00:00	19.5%
Kshitij Naveed Kaul	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|246352483	246352483	5e-05	5e-05	2026-10-12T23:11:05.501054+00:00	<0.1%
Kshitij Naveed Kaul	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|246352541	246352541	0.000692	0.000692	2026-10-12T23:11:06.747890+00:00	<0.1%
Kshitij Naveed Kaul	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|246352599	246352599	0.002327	0.002327	2026-10-12T23:11:07.952964+00:00	0.2%
Kshitij Naveed Kaul	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|246352657	246352657	0.007373	0.007373	2026-10-12T23:11:09.073291+00:00	0.7%
Kshitij Naveed Kaul	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|246352715	246352715	0.177383	0.177383	2026-10-12T23:11:10.724619+00:00	17.7%
Jamal Hossain	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|246352486	246352486	3.3e-05	3.3e-05	2026-10-12T23:11:05.501054+00:00	<0.1%
Jamal Hossain	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|246352544	246352544	0.000426	0.000426	2026-10-12T23:11:06.747890+00:00	<0.1%
Jamal Hossain	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|246352602	246352602	0.001292	0.001292	2026-10-12T23:11:07.952964+00:00	0.1%
Jamal Hossain	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|246352660	246352660	0.005236	0.005236	2026-10-12T23:11:09.073291+00:00	0.5%
Jamal Hossain	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|246352718	246352718	0.148933	0.148933	2026-10-12T23:11:10.724619+00:00	14.9%
Ajeetesh Sandhu	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|246352484	246352484	3.3e-05	3.3e-05	2026-10-12T23:11:05.501054+00:00	<0.1%
Ajeetesh Sandhu	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|246352542	246352542	0.000766	0.000766	2026-10-12T23:11:06.747890+00:00	<0.1%
Ajeetesh Sandhu	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|246352600	246352600	0.003037	0.003037	2026-10-12T23:11:07.952964+00:00	0.3%
Ajeetesh Sandhu	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|246352658	246352658	0.011067	0.011067	2026-10-12T23:11:09.073291+00:00	1.1%
Ajeetesh Sandhu	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|246352716	246352716	0.22465	0.22465	2026-10-12T23:11:10.724619+00:00	22.5%
Kartik Singh	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|246352485	246352485	3.3e-05	3.3e-05	2026-10-12T23:11:05.501054+00:00	<0.1%
Kartik Singh	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|246352543	246352543	0.000195	0.000195	2026-10-12T23:11:06.747890+00:00	<0.1%
Kartik Singh	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|246352601	246352601	0.000745	0.000745	2026-10-12T23:11:07.952964+00:00	<0.1%
Kartik Singh	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|246352659	246352659	0.002921	0.002921	2026-10-12T23:11:09.073291+00:00	0.3%
Kartik Singh	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|246352717	246352717	0.1067	0.1067	2026-10-12T23:11:10.724619+00:00	10.7%
Akshay Sharma	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|246352487	246352487	1.7e-05	1.7e-05	2026-10-12T23:11:05.501054+00:00	<0.1%
Akshay Sharma	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|246352545	246352545	0.000216	0.000216	2026-10-12T23:11:06.747890+00:00	<0.1%
Akshay Sharma	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|246352603	246352603	0.000892	0.000892	2026-10-12T23:11:07.952964+00:00	<0.1%
Akshay Sharma	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|246352661	246352661	0.004323	0.004323	2026-10-12T23:11:09.073291+00:00	0.4%
Akshay Sharma	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|246352719	246352719	0.141383	0.141383	2026-10-12T23:11:10.724619+00:00	14.1%
Mohd Azhar	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|246352489	246352489	1.7e-05	1.7e-05	2026-10-12T23:11:05.501054+00:00	<0.1%
Mohd Azhar	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|246352547	246352547	0.000529	0.000529	2026-10-12T23:11:06.747890+00:00	<0.1%
Mohd Azhar	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|246352605	246352605	0.002044	0.002044	2026-10-12T23:11:07.952964+00:00	0.2%
Mohd Azhar	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|246352663	246352663	0.007204	0.007204	2026-10-12T23:11:09.073291+00:00	0.7%
Mohd Azhar	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|246352721	246352721	0.170867	0.170867	2026-10-12T23:11:10.724619+00:00	17.1%
Anshul Kabthiyal	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|246352490	246352490	1.7e-05	1.7e-05	2026-10-12T23:11:05.501054+00:00	<0.1%
Anshul Kabthiyal	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|246352548	246352548	0.000235	0.000235	2026-10-12T23:11:06.747890+00:00	<0.1%
Anshul Kabthiyal	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|246352606	246352606	0.000898	0.000898	2026-10-12T23:11:07.952964+00:00	<0.1%
Anshul Kabthiyal	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|246352664	246352664	0.003496	0.003496	2026-10-12T23:11:09.073291+00:00	0.3%
Anshul Kabthiyal	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|246352722	246352722	0.1166	0.1166	2026-10-12T23:11:10.724619+00:00	11.7%
Om Prakash Chouhan	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|246352491	246352491	1.7e-05	1.7e-05	2026-10-12T23:11:05.501054+00:00	<0.1%
Om Prakash Chouhan	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|246352549	246352549	0.000278	0.000278	2026-10-12T23:11:06.747890+00:00	<0.1%
Om Prakash Chouhan	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|246352607	246352607	0.000965	0.000965	2026-10-12T23:11:07.952964+00:00	<0.1%
Om Prakash Chouhan	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|246352665	246352665	0.003826	0.003826	2026-10-12T23:11:09.073291+00:00	0.4%
Om Prakash Chouhan	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|246352723	246352723	0.133017	0.133017	2026-10-12T23:11:10.724619+00:00	13.3%
Viraj Madappa	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|246352492	246352492	1.7e-05	1.7e-05	2026-10-12T23:11:05.501054+00:00	<0.1%
Viraj Madappa	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|246352550	246352550	0.000272	0.000272	2026-10-12T23:11:06.747890+00:00	<0.1%
Viraj Madappa	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|246352608	246352608	0.000784	0.000784	2026-10-12T23:11:07.952964+00:00	<0.1%
Viraj Madappa	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|246352666	246352666	0.003015	0.003015	2026-10-12T23:11:09.073291+00:00	0.3%
Viraj Madappa	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|246352724	246352724	0.1053	0.1053	2026-10-12T23:11:10.724619+00:00	10.5%
Manoj S	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|246352493	246352493	1.7e-05	1.7e-05	2026-10-12T23:11:05.501054+00:00	<0.1%
Manoj S	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|246352551	246352551	0.000874	0.000874	2026-10-12T23:11:06.747890+00:00	<0.1%
Manoj S	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|246352609	246352609	0.003093	0.003093	2026-10-12T23:11:07.952964+00:00	0.3%
Manoj S	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|246352667	246352667	0.010483	0.010483	2026-10-12T23:11:09.073291+00:00	1%
Manoj S	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|246352725	246352725	0.194233	0.194233	2026-10-12T23:11:10.724619+00:00	19.4%
Shiv Kapur	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|246352494	246352494	1.7e-05	1.7e-05	2026-10-12T23:11:05.501054+00:00	<0.1%
Shiv Kapur	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|246352552	246352552	0.000386	0.000386	2026-10-12T23:11:06.747890+00:00	<0.1%
Shiv Kapur	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|246352610	246352610	0.001508	0.001508	2026-10-12T23:11:07.952964+00:00	0.2%
Shiv Kapur	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|246352668	246352668	0.005788	0.005788	2026-10-12T23:11:09.073291+00:00	0.6%
Shiv Kapur	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|246352726	246352726	0.141917	0.141917	2026-10-12T23:11:10.724619+00:00	14.2%
Vishesh Sharma	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|246352495	246352495	1.7e-05	1.7e-05	2026-10-12T23:11:05.501054+00:00	<0.1%
Vishesh Sharma	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|246352553	246352553	0.000534	0.000534	2026-10-12T23:11:06.747890+00:00	<0.1%
Vishesh Sharma	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|246352611	246352611	0.001822	0.001822	2026-10-12T23:11:07.952964+00:00	0.2%
Vishesh Sharma	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|246352669	246352669	0.005462	0.005462	2026-10-12T23:11:09.073291+00:00	0.5%
Vishesh Sharma	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|246352727	246352727	0.141333	0.141333	2026-10-12T23:11:10.724619+00:00	14.1%
Stepan Danek	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|246352488	246352488	1.7e-05	1.7e-05	2026-10-12T23:11:05.501054+00:00	<0.1%
Stepan Danek	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|246352546	246352546	0.000264	0.000264	2026-10-12T23:11:06.747890+00:00	<0.1%
Stepan Danek	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|246352604	246352604	0.000772	0.000772	2026-10-12T23:11:07.952964+00:00	<0.1%
Stepan Danek	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|246352662	246352662	0.002903	0.002903	2026-10-12T23:11:09.073291+00:00	0.3%
Stepan Danek	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|246352720	246352720	0.100767	0.100767	2026-10-12T23:11:10.724619+00:00	10.1%
Shubham Jaglan	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|246352496	246352496	0	-	2026-10-12T23:11:05.501054+00:00	0%
Shubham Jaglan	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|246352554	246352554	0.000164	0.000164	2026-10-12T23:11:06.747890+00:00	<0.1%
Shubham Jaglan	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|246352612	246352612	0.000543	0.000543	2026-10-12T23:11:07.952964+00:00	<0.1%
Shubham Jaglan	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|246352670	246352670	0.002049	0.002049	2026-10-12T23:11:09.073291+00:00	0.2%
Shubham Jaglan	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|246352728	246352728	0.095883	0.095883	2026-10-12T23:11:10.724619+00:00	9.6%
Subash Tamang	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|246352497	246352497	0	-	2026-10-12T23:11:05.501054+00:00	0%
Subash Tamang	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|246352555	246352555	7.3e-05	7.3e-05	2026-10-12T23:11:06.747890+00:00	<0.1%
Subash Tamang	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|246352613	246352613	0.000413	0.000413	2026-10-12T23:11:07.952964+00:00	<0.1%
Subash Tamang	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|246352671	246352671	0.001823	0.001823	2026-10-12T23:11:09.073291+00:00	0.2%
Subash Tamang	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|246352729	246352729	0.087483	0.087483	2026-10-12T23:11:10.724619+00:00	8.7%
Alex Noren	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904632	245904632	-	0.0283	2026-10-12T19:09:44.432467+00:00	Unavailable
Alex Noren	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904764	245904764	-	0.129657	2026-10-12T19:09:46.711391+00:00	Unavailable
Alex Noren	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904896	245904896	-	0.230104	2026-10-12T19:09:47.805511+00:00	Unavailable
Alex Noren	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905028	245905028	-	0.391612	2026-10-12T19:09:49.369336+00:00	Unavailable
Alex Noren	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905160	245905160	-	0.78065	2026-10-12T19:09:51.639944+00:00	Unavailable
Mikael Lindberg	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904663	245904663	-	0.008033	2026-10-12T19:09:44.432467+00:00	Unavailable
Mikael Lindberg	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904795	245904795	-	0.045575	2026-10-12T19:09:46.711391+00:00	Unavailable
Mikael Lindberg	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904927	245904927	-	0.091028	2026-10-12T19:09:47.805511+00:00	Unavailable
Mikael Lindberg	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905059	245905059	-	0.183749	2026-10-12T19:09:49.369336+00:00	Unavailable
Mikael Lindberg	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905191	245905191	-	0.6029	2026-10-12T19:09:51.639944+00:00	Unavailable
Hennie Du Plessis	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904672	245904672	-	0.00655	2026-10-12T19:09:44.432467+00:00	Unavailable
Hennie Du Plessis	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904804	245904804	-	0.037743	2026-10-12T19:09:46.711391+00:00	Unavailable
Hennie Du Plessis	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904936	245904936	-	0.079987	2026-10-12T19:09:47.805511+00:00	Unavailable
Hennie Du Plessis	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905068	245905068	-	0.172117	2026-10-12T19:09:49.369336+00:00	Unavailable
Hennie Du Plessis	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905200	245905200	-	0.603433	2026-10-12T19:09:51.639944+00:00	Unavailable
Yanhan Zhou	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904707	245904707	-	0.00285	2026-10-12T19:09:44.432467+00:00	Unavailable
Yanhan Zhou	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904839	245904839	-	0.017785	2026-10-12T19:09:46.711391+00:00	Unavailable
Yanhan Zhou	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904971	245904971	-	0.040819	2026-10-12T19:09:47.805511+00:00	Unavailable
Yanhan Zhou	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905103	245905103	-	0.095003	2026-10-12T19:09:49.369336+00:00	Unavailable
Yanhan Zhou	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905235	245905235	-	0.48675	2026-10-12T19:09:51.639944+00:00	Unavailable
Ashun Wu	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904728	245904728	-	0.001483	2026-10-12T19:09:44.432467+00:00	Unavailable
Ashun Wu	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904860	245904860	-	0.01128	2026-10-12T19:09:46.711391+00:00	Unavailable
Ashun Wu	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904992	245904992	-	0.030338	2026-10-12T19:09:47.805511+00:00	Unavailable
Ashun Wu	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905124	245905124	-	0.079653	2026-10-12T19:09:49.369336+00:00	Unavailable
Ashun Wu	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905256	245905256	-	0.4618	2026-10-12T19:09:51.639944+00:00	Unavailable
Alejandro Rodriguez Andreu	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904758	245904758	-	3.3e-05	2026-10-12T19:09:44.432467+00:00	Unavailable
Alejandro Rodriguez Andreu	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904890	245904890	-	0.000424	2026-10-12T19:09:46.711391+00:00	Unavailable
Alejandro Rodriguez Andreu	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245905022	245905022	-	0.00156	2026-10-12T19:09:47.805511+00:00	Unavailable
Alejandro Rodriguez Andreu	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905154	245905154	-	0.005008	2026-10-12T19:09:49.369336+00:00	Unavailable
Alejandro Rodriguez Andreu	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905286	245905286	-	0.13615	2026-10-12T19:09:51.639944+00:00	Unavailable
Jose Luis Ballester	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904647	245904647	-	0.017333	2026-10-12T19:09:44.432467+00:00	Unavailable
Jose Luis Ballester	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904779	245904779	-	0.081861	2026-10-12T19:09:46.711391+00:00	Unavailable
Jose Luis Ballester	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904911	245904911	-	0.152616	2026-10-12T19:09:47.805511+00:00	Unavailable
Jose Luis Ballester	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905043	245905043	-	0.277925	2026-10-12T19:09:49.369336+00:00	Unavailable
Jose Luis Ballester	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905175	245905175	-	0.691467	2026-10-12T19:09:51.639944+00:00	Unavailable
Joe Dean	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904652	245904652	-	0.0117	2026-10-12T19:09:44.432467+00:00	Unavailable
Joe Dean	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904784	245904784	-	0.059781	2026-10-12T19:09:46.711391+00:00	Unavailable
Joe Dean	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904916	245904916	-	0.118362	2026-10-12T19:09:47.805511+00:00	Unavailable
Joe Dean	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905048	245905048	-	0.233003	2026-10-12T19:09:49.369336+00:00	Unavailable
Joe Dean	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905180	245905180	-	0.670283	2026-10-12T19:09:51.639944+00:00	Unavailable
Marco Penge	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904638	245904638	-	0.020267	2026-10-12T19:09:44.432467+00:00	Unavailable
Marco Penge	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904770	245904770	-	0.08799	2026-10-12T19:09:46.711391+00:00	Unavailable
Marco Penge	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904902	245904902	-	0.159816	2026-10-12T19:09:47.805511+00:00	Unavailable
Marco Penge	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905034	245905034	-	0.284603	2026-10-12T19:09:49.369336+00:00	Unavailable
Marco Penge	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905166	245905166	-	0.693767	2026-10-12T19:09:51.639944+00:00	Unavailable
Ludvig Aberg	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904629	245904629	-	0.113067	2026-10-12T19:09:44.432467+00:00	Unavailable
Ludvig Aberg	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904761	245904761	-	0.316914	2026-10-12T19:09:46.711391+00:00	Unavailable
Ludvig Aberg	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904893	245904893	-	0.457692	2026-10-12T19:09:47.805511+00:00	Unavailable
Ludvig Aberg	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905025	245905025	-	0.623582	2026-10-12T19:09:49.369336+00:00	Unavailable
Ludvig Aberg	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905157	245905157	-	0.881983	2026-10-12T19:09:51.639944+00:00	Unavailable
David Puig	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904636	245904636	-	0.021483	2026-10-12T19:09:44.432467+00:00	Unavailable
David Puig	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904768	245904768	-	0.097941	2026-10-12T19:09:46.711391+00:00	Unavailable
David Puig	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904900	245904900	-	0.180376	2026-10-12T19:09:47.805511+00:00	Unavailable
David Puig	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905032	245905032	-	0.320618	2026-10-12T19:09:49.369336+00:00	Unavailable
David Puig	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905164	245905164	-	0.737583	2026-10-12T19:09:51.639944+00:00	Unavailable
Matthew Jordan	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904648	245904648	-	0.014017	2026-10-12T19:09:44.432467+00:00	Unavailable
Matthew Jordan	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904780	245904780	-	0.068797	2026-10-12T19:09:46.711391+00:00	Unavailable
Matthew Jordan	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904912	245904912	-	0.136191	2026-10-12T19:09:47.805511+00:00	Unavailable
Matthew Jordan	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905044	245905044	-	0.25805	2026-10-12T19:09:49.369336+00:00	Unavailable
Matthew Jordan	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905176	245905176	-	0.6844	2026-10-12T19:09:51.639944+00:00	Unavailable
Sam Bairstow	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904651	245904651	-	0.01285	2026-10-12T19:09:44.432467+00:00	Unavailable
Sam Bairstow	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904783	245904783	-	0.066885	2026-10-12T19:09:46.711391+00:00	Unavailable
Sam Bairstow	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904915	245904915	-	0.131723	2026-10-12T19:09:47.805511+00:00	Unavailable
Sam Bairstow	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905047	245905047	-	0.251185	2026-10-12T19:09:49.369336+00:00	Unavailable
Sam Bairstow	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905179	245905179	-	0.685817	2026-10-12T19:09:51.639944+00:00	Unavailable
Calum Hill	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904657	245904657	-	0.009817	2026-10-12T19:09:44.432467+00:00	Unavailable
Calum Hill	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904789	245904789	-	0.052447	2026-10-12T19:09:46.711391+00:00	Unavailable
Calum Hill	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904921	245904921	-	0.107047	2026-10-12T19:09:47.805511+00:00	Unavailable
Calum Hill	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905053	245905053	-	0.21096	2026-10-12T19:09:49.369336+00:00	Unavailable
Calum Hill	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905185	245905185	-	0.641517	2026-10-12T19:09:51.639944+00:00	Unavailable
Thomas Rosenmueller	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904661	245904661	-	0.008417	2026-10-12T19:09:44.432467+00:00	Unavailable
Thomas Rosenmueller	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904793	245904793	-	0.04833	2026-10-12T19:09:46.711391+00:00	Unavailable
Thomas Rosenmueller	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904925	245904925	-	0.10139	2026-10-12T19:09:47.805511+00:00	Unavailable
Thomas Rosenmueller	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905057	245905057	-	0.204384	2026-10-12T19:09:49.369336+00:00	Unavailable
Thomas Rosenmueller	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905189	245905189	-	0.6435	2026-10-12T19:09:51.639944+00:00	Unavailable
Richard Mansell	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904662	245904662	-	0.008117	2026-10-12T19:09:44.432467+00:00	Unavailable
Richard Mansell	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904794	245904794	-	0.041166	2026-10-12T19:09:46.711391+00:00	Unavailable
Richard Mansell	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904926	245904926	-	0.084768	2026-10-12T19:09:47.805511+00:00	Unavailable
Richard Mansell	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905058	245905058	-	0.174981	2026-10-12T19:09:49.369336+00:00	Unavailable
Richard Mansell	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905190	245905190	-	0.6053	2026-10-12T19:09:51.639944+00:00	Unavailable
MJ Daffue	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904664	245904664	-	0.007867	2026-10-12T19:09:44.432467+00:00	Unavailable
MJ Daffue	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904796	245904796	-	0.043698	2026-10-12T19:09:46.711391+00:00	Unavailable
MJ Daffue	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904928	245904928	-	0.088705	2026-10-12T19:09:47.805511+00:00	Unavailable
MJ Daffue	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905060	245905060	-	0.181476	2026-10-12T19:09:49.369336+00:00	Unavailable
MJ Daffue	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905192	245905192	-	0.6023	2026-10-12T19:09:51.639944+00:00	Unavailable
Dan Brown	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904665	245904665	-	0.007833	2026-10-12T19:09:44.432467+00:00	Unavailable
Dan Brown	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904797	245904797	-	0.045591	2026-10-12T19:09:46.711391+00:00	Unavailable
Dan Brown	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904929	245904929	-	0.095907	2026-10-12T19:09:47.805511+00:00	Unavailable
Dan Brown	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905061	245905061	-	0.198971	2026-10-12T19:09:49.369336+00:00	Unavailable
Dan Brown	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905193	245905193	-	0.638017	2026-10-12T19:09:51.639944+00:00	Unavailable
Jeff Winther	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904671	245904671	-	0.006667	2026-10-12T19:09:44.432467+00:00	Unavailable
Jeff Winther	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904803	245904803	-	0.039909	2026-10-12T19:09:46.711391+00:00	Unavailable
Jeff Winther	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904935	245904935	-	0.085543	2026-10-12T19:09:47.805511+00:00	Unavailable
Jeff Winther	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905067	245905067	-	0.1827	2026-10-12T19:09:49.369336+00:00	Unavailable
Jeff Winther	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905199	245905199	-	0.627983	2026-10-12T19:09:51.639944+00:00	Unavailable
Alejandro Del Rey	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904677	245904677	-	0.006067	2026-10-12T19:09:44.432467+00:00	Unavailable
Alejandro Del Rey	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904809	245904809	-	0.036032	2026-10-12T19:09:46.711391+00:00	Unavailable
Alejandro Del Rey	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904941	245904941	-	0.07582	2026-10-12T19:09:47.805511+00:00	Unavailable
Alejandro Del Rey	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905073	245905073	-	0.157319	2026-10-12T19:09:49.369336+00:00	Unavailable
Alejandro Del Rey	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905205	245905205	-	0.5757	2026-10-12T19:09:51.639944+00:00	Unavailable
Paul Waring	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904684	245904684	-	0.0051	2026-10-12T19:09:44.432467+00:00	Unavailable
Paul Waring	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904816	245904816	-	0.02954	2026-10-12T19:09:46.711391+00:00	Unavailable
Paul Waring	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904948	245904948	-	0.063441	2026-10-12T19:09:47.805511+00:00	Unavailable
Paul Waring	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905080	245905080	-	0.13832	2026-10-12T19:09:49.369336+00:00	Unavailable
Paul Waring	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905212	245905212	-	0.54925	2026-10-12T19:09:51.639944+00:00	Unavailable
Brandon Stone	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904685	245904685	-	0.005083	2026-10-12T19:09:44.432467+00:00	Unavailable
Brandon Stone	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904817	245904817	-	0.03411	2026-10-12T19:09:46.711391+00:00	Unavailable
Brandon Stone	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904949	245904949	-	0.074531	2026-10-12T19:09:47.805511+00:00	Unavailable
Brandon Stone	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905081	245905081	-	0.159968	2026-10-12T19:09:49.369336+00:00	Unavailable
Brandon Stone	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905213	245905213	-	0.58685	2026-10-12T19:09:51.639944+00:00	Unavailable
Kazuma Kobori	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904689	245904689	-	0.0046	2026-10-12T19:09:44.432467+00:00	Unavailable
Kazuma Kobori	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904821	245904821	-	0.029274	2026-10-12T19:09:46.711391+00:00	Unavailable
Kazuma Kobori	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904953	245904953	-	0.067133	2026-10-12T19:09:47.805511+00:00	Unavailable
Kazuma Kobori	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905085	245905085	-	0.153313	2026-10-12T19:09:49.369336+00:00	Unavailable
Kazuma Kobori	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905217	245905217	-	0.592917	2026-10-12T19:09:51.639944+00:00	Unavailable
Bubba Watson	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904696	245904696	-	0.003867	2026-10-12T19:09:44.432467+00:00	Unavailable
Bubba Watson	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904828	245904828	-	0.025109	2026-10-12T19:09:46.711391+00:00	Unavailable
Bubba Watson	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904960	245904960	-	0.055701	2026-10-12T19:09:47.805511+00:00	Unavailable
Bubba Watson	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905092	245905092	-	0.127368	2026-10-12T19:09:49.369336+00:00	Unavailable
Bubba Watson	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905224	245905224	-	0.544917	2026-10-12T19:09:51.639944+00:00	Unavailable
Marcus Helligkilde	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904703	245904703	-	0.003417	2026-10-12T19:09:44.432467+00:00	Unavailable
Marcus Helligkilde	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904835	245904835	-	0.023702	2026-10-12T19:09:46.711391+00:00	Unavailable
Marcus Helligkilde	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904967	245904967	-	0.053001	2026-10-12T19:09:47.805511+00:00	Unavailable
Marcus Helligkilde	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905099	245905099	-	0.117436	2026-10-12T19:09:49.369336+00:00	Unavailable
Marcus Helligkilde	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905231	245905231	-	0.525783	2026-10-12T19:09:51.639944+00:00	Unavailable
Jeremy Paul	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904705	245904705	-	0.002917	2026-10-12T19:09:44.432467+00:00	Unavailable
Jeremy Paul	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904837	245904837	-	0.019604	2026-10-12T19:09:46.711391+00:00	Unavailable
Jeremy Paul	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904969	245904969	-	0.045138	2026-10-12T19:09:47.805511+00:00	Unavailable
Jeremy Paul	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905101	245905101	-	0.10779	2026-10-12T19:09:49.369336+00:00	Unavailable
Jeremy Paul	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905233	245905233	-	0.5117	2026-10-12T19:09:51.639944+00:00	Unavailable
Connor Syme	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904720	245904720	-	0.002	2026-10-12T19:09:44.432467+00:00	Unavailable
Connor Syme	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904852	245904852	-	0.014168	2026-10-12T19:09:46.711391+00:00	Unavailable
Connor Syme	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904984	245904984	-	0.035695	2026-10-12T19:09:47.805511+00:00	Unavailable
Connor Syme	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905116	245905116	-	0.087214	2026-10-12T19:09:49.369336+00:00	Unavailable
Connor Syme	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905248	245905248	-	0.473467	2026-10-12T19:09:51.639944+00:00	Unavailable
Alfredo Garcia-Heredia	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904736	245904736	-	0.0011	2026-10-12T19:09:44.432467+00:00	Unavailable
Alfredo Garcia-Heredia	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904868	245904868	-	0.007167	2026-10-12T19:09:46.711391+00:00	Unavailable
Alfredo Garcia-Heredia	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245905000	245905000	-	0.018183	2026-10-12T19:09:47.805511+00:00	Unavailable
Alfredo Garcia-Heredia	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905132	245905132	-	0.048178	2026-10-12T19:09:49.369336+00:00	Unavailable
Alfredo Garcia-Heredia	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905264	245905264	-	0.3769	2026-10-12T19:09:51.639944+00:00	Unavailable
Michael Stewart	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904746	245904746	-	0.0006	2026-10-12T19:09:44.432467+00:00	Unavailable
Michael Stewart	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904878	245904878	-	0.005017	2026-10-12T19:09:46.711391+00:00	Unavailable
Michael Stewart	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245905010	245905010	-	0.013368	2026-10-12T19:09:47.805511+00:00	Unavailable
Michael Stewart	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905142	245905142	-	0.038265	2026-10-12T19:09:49.369336+00:00	Unavailable
Michael Stewart	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905274	245905274	-	0.356567	2026-10-12T19:09:51.639944+00:00	Unavailable
Sergio Jimenez Romero	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904749	245904749	-	0.00035	2026-10-12T19:09:44.432467+00:00	Unavailable
Sergio Jimenez Romero	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904881	245904881	-	0.003787	2026-10-12T19:09:46.711391+00:00	Unavailable
Sergio Jimenez Romero	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245905013	245905013	-	0.010282	2026-10-12T19:09:47.805511+00:00	Unavailable
Sergio Jimenez Romero	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905145	245905145	-	0.027939	2026-10-12T19:09:49.369336+00:00	Unavailable
Sergio Jimenez Romero	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905277	245905277	-	0.2934	2026-10-12T19:09:51.639944+00:00	Unavailable
David Micheluzzi	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904750	245904750	-	0.000317	2026-10-12T19:09:44.432467+00:00	Unavailable
David Micheluzzi	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904882	245904882	-	0.002544	2026-10-12T19:09:46.711391+00:00	Unavailable
David Micheluzzi	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245905014	245905014	-	0.007094	2026-10-12T19:09:47.805511+00:00	Unavailable
David Micheluzzi	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905146	245905146	-	0.023587	2026-10-12T19:09:49.369336+00:00	Unavailable
David Micheluzzi	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905278	245905278	-	0.2816	2026-10-12T19:09:51.639944+00:00	Unavailable
Thomas Aiken	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904751	245904751	-	0.0003	2026-10-12T19:09:44.432467+00:00	Unavailable
Thomas Aiken	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904883	245904883	-	0.003504	2026-10-12T19:09:46.711391+00:00	Unavailable
Thomas Aiken	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245905015	245905015	-	0.010077	2026-10-12T19:09:47.805511+00:00	Unavailable
Thomas Aiken	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905147	245905147	-	0.030867	2026-10-12T19:09:49.369336+00:00	Unavailable
Thomas Aiken	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905279	245905279	-	0.3157	2026-10-12T19:09:51.639944+00:00	Unavailable
Ockie Strydom	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904755	245904755	-	0.000133	2026-10-12T19:09:44.432467+00:00	Unavailable
Ockie Strydom	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904887	245904887	-	0.001336	2026-10-12T19:09:46.711391+00:00	Unavailable
Ockie Strydom	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245905019	245905019	-	0.003697	2026-10-12T19:09:47.805511+00:00	Unavailable
Ockie Strydom	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905151	245905151	-	0.011372	2026-10-12T19:09:49.369336+00:00	Unavailable
Ockie Strydom	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905283	245905283	-	0.210567	2026-10-12T19:09:51.639944+00:00	Unavailable
Juan Salama	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904756	245904756	-	8.3e-05	2026-10-12T19:09:44.432467+00:00	Unavailable
Juan Salama	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904888	245904888	-	0.000693	2026-10-12T19:09:46.711391+00:00	Unavailable
Juan Salama	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245905020	245905020	-	0.002037	2026-10-12T19:09:47.805511+00:00	Unavailable
Juan Salama	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905152	245905152	-	0.006062	2026-10-12T19:09:49.369336+00:00	Unavailable
Juan Salama	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905284	245905284	-	0.145583	2026-10-12T19:09:51.639944+00:00	Unavailable
Gonzalo Banos Ramos	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904757	245904757	-	8.3e-05	2026-10-12T19:09:44.432467+00:00	Unavailable
Gonzalo Banos Ramos	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904889	245904889	-	0.000553	2026-10-12T19:09:46.711391+00:00	Unavailable
Gonzalo Banos Ramos	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245905021	245905021	-	0.001552	2026-10-12T19:09:47.805511+00:00	Unavailable
Gonzalo Banos Ramos	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905153	245905153	-	0.004908	2026-10-12T19:09:49.369336+00:00	Unavailable
Gonzalo Banos Ramos	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905285	245905285	-	0.132217	2026-10-12T19:09:51.639944+00:00	Unavailable
Daniel Gavins	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904759	245904759	-	3.3e-05	2026-10-12T19:09:44.432467+00:00	Unavailable
Daniel Gavins	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904891	245904891	-	0.000293	2026-10-12T19:09:46.711391+00:00	Unavailable
Daniel Gavins	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245905023	245905023	-	0.000899	2026-10-12T19:09:47.805511+00:00	Unavailable
Daniel Gavins	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905155	245905155	-	0.003677	2026-10-12T19:09:49.369336+00:00	Unavailable
Daniel Gavins	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905287	245905287	-	0.122383	2026-10-12T19:09:51.639944+00:00	Unavailable
Sebastian Desoisa	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904760	245904760	-	1.7e-05	2026-10-12T19:09:44.432467+00:00	Unavailable
Sebastian Desoisa	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904892	245904892	-	0.00029	2026-10-12T19:09:46.711391+00:00	Unavailable
Sebastian Desoisa	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245905024	245905024	-	0.001016	2026-10-12T19:09:47.805511+00:00	Unavailable
Sebastian Desoisa	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905156	245905156	-	0.003455	2026-10-12T19:09:49.369336+00:00	Unavailable
Sebastian Desoisa	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905288	245905288	-	0.109933	2026-10-12T19:09:51.639944+00:00	Unavailable
Wenyi Ding	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904742	245904742	-	0.000967	2026-10-12T19:09:44.432467+00:00	Unavailable
Wenyi Ding	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904874	245904874	-	0.00819	2026-10-12T19:09:46.711391+00:00	Unavailable
Wenyi Ding	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245905006	245905006	-	0.020904	2026-10-12T19:09:47.805511+00:00	Unavailable
Wenyi Ding	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905138	245905138	-	0.055924	2026-10-12T19:09:49.369336+00:00	Unavailable
Wenyi Ding	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905270	245905270	-	0.4108	2026-10-12T19:09:51.639944+00:00	Unavailable
Sami Valimaki	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904660	245904660	-	0.008983	2026-10-12T19:09:44.432467+00:00	Unavailable
Sami Valimaki	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904792	245904792	-	0.049031	2026-10-12T19:09:46.711391+00:00	Unavailable
Sami Valimaki	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904924	245904924	-	0.099887	2026-10-12T19:09:47.805511+00:00	Unavailable
Sami Valimaki	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905056	245905056	-	0.202335	2026-10-12T19:09:49.369336+00:00	Unavailable
Sami Valimaki	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905188	245905188	-	0.628167	2026-10-12T19:09:51.639944+00:00	Unavailable
Victor Perez	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904642	245904642	-	0.019	2026-10-12T19:09:44.432467+00:00	Unavailable
Victor Perez	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904774	245904774	-	0.092361	2026-10-12T19:09:46.711391+00:00	Unavailable
Victor Perez	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904906	245904906	-	0.175374	2026-10-12T19:09:47.805511+00:00	Unavailable
Victor Perez	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905038	245905038	-	0.316319	2026-10-12T19:09:49.369336+00:00	Unavailable
Victor Perez	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905170	245905170	-	0.735817	2026-10-12T19:09:51.639944+00:00	Unavailable
Sergio Garcia	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904646	245904646	-	0.017833	2026-10-12T19:09:44.432467+00:00	Unavailable
Sergio Garcia	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904778	245904778	-	0.082572	2026-10-12T19:09:46.711391+00:00	Unavailable
Sergio Garcia	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904910	245904910	-	0.153286	2026-10-12T19:09:47.805511+00:00	Unavailable
Sergio Garcia	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905042	245905042	-	0.279331	2026-10-12T19:09:49.369336+00:00	Unavailable
Sergio Garcia	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905174	245905174	-	0.6957	2026-10-12T19:09:51.639944+00:00	Unavailable
Francesco Molinari	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904699	245904699	-	0.003533	2026-10-12T19:09:44.432467+00:00	Unavailable
Francesco Molinari	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904831	245904831	-	0.024189	2026-10-12T19:09:46.711391+00:00	Unavailable
Francesco Molinari	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904963	245904963	-	0.056466	2026-10-12T19:09:47.805511+00:00	Unavailable
Francesco Molinari	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905095	245905095	-	0.131929	2026-10-12T19:09:49.369336+00:00	Unavailable
Francesco Molinari	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905227	245905227	-	0.57155	2026-10-12T19:09:51.639944+00:00	Unavailable
Jacques Kruyswijk	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904737	245904737	-	0.001067	2026-10-12T19:09:44.432467+00:00	Unavailable
Jacques Kruyswijk	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904869	245904869	-	0.009338	2026-10-12T19:09:46.711391+00:00	Unavailable
Jacques Kruyswijk	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245905001	245905001	-	0.023005	2026-10-12T19:09:47.805511+00:00	Unavailable
Jacques Kruyswijk	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905133	245905133	-	0.063096	2026-10-12T19:09:49.369336+00:00	Unavailable
Jacques Kruyswijk	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905265	245905265	-	0.4488	2026-10-12T19:09:51.639944+00:00	Unavailable
Luke List	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904723	245904723	-	0.001667	2026-10-12T19:09:44.432467+00:00	Unavailable
Luke List	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904855	245904855	-	0.010765	2026-10-12T19:09:46.711391+00:00	Unavailable
Luke List	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904987	245904987	-	0.025368	2026-10-12T19:09:47.805511+00:00	Unavailable
Luke List	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905119	245905119	-	0.062314	2026-10-12T19:09:49.369336+00:00	Unavailable
Luke List	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905251	245905251	-	0.411333	2026-10-12T19:09:51.639944+00:00	Unavailable
Tyrrell Hatton	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904637	245904637	-	0.020883	2026-10-12T19:09:44.432467+00:00	Unavailable
Tyrrell Hatton	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904769	245904769	-	0.097079	2026-10-12T19:09:46.711391+00:00	Unavailable
Tyrrell Hatton	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904901	245904901	-	0.176277	2026-10-12T19:09:47.805511+00:00	Unavailable
Tyrrell Hatton	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905033	245905033	-	0.313891	2026-10-12T19:09:49.369336+00:00	Unavailable
Tyrrell Hatton	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905165	245905165	-	0.730883	2026-10-12T19:09:51.639944+00:00	Unavailable
Nicolai Hojgaard	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904650	245904650	-	0.012917	2026-10-12T19:09:44.432467+00:00	Unavailable
Nicolai Hojgaard	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904782	245904782	-	0.062987	2026-10-12T19:09:46.711391+00:00	Unavailable
Nicolai Hojgaard	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904914	245904914	-	0.122432	2026-10-12T19:09:47.805511+00:00	Unavailable
Nicolai Hojgaard	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905046	245905046	-	0.231002	2026-10-12T19:09:49.369336+00:00	Unavailable
Nicolai Hojgaard	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905178	245905178	-	0.650267	2026-10-12T19:09:51.639944+00:00	Unavailable
"""#
