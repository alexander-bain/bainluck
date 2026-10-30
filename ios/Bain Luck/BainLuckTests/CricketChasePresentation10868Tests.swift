import SwiftUI
import XCTest
@testable import Bain_Luck

/// #10868 — the cricket-live chase card as a stateless presentation leaf,
/// adaptive across before, during and final.
///
/// The view is SwiftUI and is not rasterised here. What is asserted is the
/// rules it defers to: phase gating (before suppresses every later field even
/// when supplied), the owner's run, target, wicket, overs and report words
/// shown verbatim, the pregame and recorded/current chances and their
/// separate clocks, the independent match and contract results, failed score
/// versus failed probability, zero versus unknown versus malformed rail
/// geometry, the exact Details reference, the pair geometry and the spoken
/// text. Nothing here claims a rendered fit, a native runtime, live app
/// delivery, T20 applicability or a production binding.
///
/// ARCHIVED raw values come from South Africa–Australia, first Test,
/// October 9–13, 2026 (route cricket-live, original event
/// KXTESTMATCH-26OCT090330AUSSA), as retained in
/// `shipping-adoption-20261027/CRICKET-CHASE-RETAINED-CASES.json`
/// (sha256 25f1fc6e…c01c). Original: Kalshi KXTESTMATCH-26OCT090330AUSSA-SA,
/// side Yes ("South Africa wins"). No internal app event/market/outcome id is
/// retained.
///   Pregame 0.48, hourly bar ending 2026-10-09T00:00Z.
///   Day-5 published score reports (publication, not exact ball time):
///     09:11:34Z  154/4  64.0 overs   recorded 0.03, bar end 09:11Z
///     09:49:56Z  166/6  73.0 (lunch) recorded 0.01, bar end 09:46Z
///     11:03:34Z  201/6  84.0 overs   recorded 0.02, bar end 11:03Z
///     11:11:58Z  201/8  85.0 overs   recorded 0.01, bar end 11:09Z
///   Target 421. Reference arithmetic only (not captured fields, not a leaf
///   policy): runs still needed 267/255/220/220, wickets left 6/4/4/2.
///   Final report 11:24:20Z: SA 206 all out (10 wickets), overs unknown;
///   Australia won by 214 runs; confirmation 11:26:55Z. Contract finalized
///   No, 2026-10-13T12:35:49.612166Z. 421 − 206 = 215 is runs short of the
///   target, not the victory margin.
///
/// CONSTRUCTED owner-resolved inputs (this leaf does not resolve them): every
/// display string (figures, local-calendar provenance, headings, captions,
/// overs, wickets and context words, result words), the owner's wicket
/// positions built from the ARCHIVED wicket counts, every action reference
/// (none is retained), and every phase-mismatch, missing, withheld,
/// unconfirmed, void, zero, malformed, target-crossing, unknown-wicket,
/// long-text and measured-width case.
final class CricketChasePresentation10868Tests: XCTestCase {

    // MARK: ARCHIVED source

    private static let ticker = "KXTESTMATCH-26OCT090330AUSSA-SA"
    private static let side = "Yes"
    private static let pregameProbability = 0.48
    private static let pregameBarEnd = "2026-10-09T00:00:00+00:00"
    private static let targetRuns = 421

    private struct RetainedFrame {
        /// ARCHIVED.
        let key: String
        let label: String
        let reportedAt: String
        let runs: Int
        let wickets: Int
        let overs: String
        let recordedProbability: Double
        let barEnd: String
        /// ARCHIVED reference arithmetic, not a captured field.
        let referenceRunsStillNeeded: Int
        let referenceWicketsRemaining: Int
        /// CONSTRUCTED owner text.
        let recordedText: String
        let recordedDetail: String
        let reportDetail: String
        let oversText: String
    }

    private static let frames: [RetainedFrame] = [
        RetainedFrame(
            key: "block-6acdf5298f084a13d13ca4ea", label: "Day 5 · 64 overs", reportedAt: "2026-10-13T09:11:34.000Z",
            runs: 154, wickets: 4, overs: "64.0", recordedProbability: 0.03, barEnd: "2026-10-13T09:11:00+00:00",
            referenceRunsStillNeeded: 267, referenceWicketsRemaining: 6,
            recordedText: "3%", recordedDetail: "Kalshi trade close · minute 2:10–2:11 AM PDT, Oct 13",
            reportDetail: "Score report published 2:11 AM PDT, Oct 13 · not the exact ball time",
            oversText: "64 overs played"
        ),
        RetainedFrame(
            key: "block-6acdfe288f08741d63f9bedf", label: "Day 5 · lunch", reportedAt: "2026-10-13T09:49:56.000Z",
            runs: 166, wickets: 6, overs: "73.0", recordedProbability: 0.01, barEnd: "2026-10-13T09:46:00+00:00",
            referenceRunsStillNeeded: 255, referenceWicketsRemaining: 4,
            recordedText: "1%", recordedDetail: "Kalshi trade close · minute 2:45–2:46 AM PDT, Oct 13",
            reportDetail: "Lunch · last score report before lunch, published 2:49 AM PDT, Oct 13 · not the exact ball time",
            oversText: "Lunch · 73 overs played"
        ),
        RetainedFrame(
            key: "block-6ace0f308f0874762783cf04", label: "Day 5 · 84 overs", reportedAt: "2026-10-13T11:03:34.000Z",
            runs: 201, wickets: 6, overs: "84.0", recordedProbability: 0.02, barEnd: "2026-10-13T11:03:00+00:00",
            referenceRunsStillNeeded: 220, referenceWicketsRemaining: 4,
            recordedText: "2%", recordedDetail: "Kalshi trade close · minute 4:02–4:03 AM PDT, Oct 13",
            reportDetail: "Score report published 4:03 AM PDT, Oct 13 · not the exact ball time",
            oversText: "84 overs played"
        ),
        RetainedFrame(
            key: "block-6ace11b98f0811efce0fe34a", label: "Day 5 · 85 overs", reportedAt: "2026-10-13T11:11:58.000Z",
            runs: 201, wickets: 8, overs: "85.0", recordedProbability: 0.01, barEnd: "2026-10-13T11:09:00+00:00",
            referenceRunsStillNeeded: 220, referenceWicketsRemaining: 2,
            recordedText: "1%", recordedDetail: "Kalshi trade close · minute 4:08–4:09 AM PDT, Oct 13",
            reportDetail: "Score report published 4:11 AM PDT, Oct 13 · not the exact ball time",
            oversText: "85 overs played"
        ),
    ]

    /// ARCHIVED final.
    private static let finalRuns = 206
    private static let finalWickets = 10
    private static let finalMarginRuns = 214

    // MARK: CONSTRUCTED owner words

    private static let subject = "South Africa wins"
    private static let pregameLabel = "Pregame"
    private static let recordedLabel = "Recorded win chance"
    private static let currentLabel = "Current win chance"
    private static let resultLabel = "Final"
    private static let pregameText = "48%"
    private static let pregameDetail = "Kalshi trade close · hour 4–5 PM PDT, Oct 8"
    private static let duringEyebrow = "South Africa · second innings"
    private static let finalEyebrow = "The chase · final"
    private static let beforeEyebrow = "South Africa · pregame"
    private static let notYetKnown = "Not known until the match is over"
    private static let currentUnavailable = "Current probability unavailable"
    private static let held = "Held — not current"
    private static let scoreUnavailable = "Score report unavailable"
    private static let notes = ["Reconstructed from published score reports and separately recorded trades — not a live feed."]
    private static let finalMatchText = "Australia won by 214 runs"
    private static let finalMatchDetail = "Final score report 4:24 AM PDT, Oct 13 · margin confirmed 4:26 AM"
    private static let gradedText = "Lost"
    private static let gradedDetail = "Kalshi finalized No · 5:35 AM PDT, Oct 13"
    private static let finalOvers = "Final overs unknown"
    private static let finalWicketsText = "All ten wickets lost"
    private static let finalReport = "Final score report published 4:24 AM PDT, Oct 13 · not the exact ball time"

    private static let ref = CricketChaseRef10868(event: "owner-event-1", market: "owner-market-1", outcome: "owner-outcome-1")

    private static var pregame: CricketChaseReading10868 {
        .observed(CricketChaseFigure10868(text: pregameText, detail: pregameDetail))
    }

    private static var graded: CricketChaseContractResult10868 {
        .graded(CricketChaseFigure10868(text: gradedText, detail: gradedDetail))
    }

    private static var finalMatch: CricketChaseMatchResult10868 {
        .reported(CricketChaseFigure10868(text: finalMatchText, detail: finalMatchDetail))
    }

    /// CONSTRUCTED owner resolution of an ARCHIVED wicket count.
    private static func ownerWickets(lost: Int, of total: Int) -> [CricketChaseWicket10868] {
        Array(repeating: .lost, count: lost) + Array(repeating: .remaining, count: total - lost)
    }

    private static func state(_ frame: RetainedFrame) -> CricketChaseState10868 {
        CricketChaseState10868(
            battingSubject: "South Africa",
            context: frame.label,
            runs: .reported(text: "\(frame.runs)", value: Double(frame.runs)),
            runsCaption: "runs scored",
            target: .reported(text: "\(targetRuns)", value: Double(targetRuns)),
            targetCaption: "runs",
            wickets: ownerWickets(lost: frame.wickets, of: 10),
            wicketsText: "\(frame.referenceWicketsRemaining) wickets left",
            oversText: frame.oversText,
            reportDetail: frame.reportDetail
        )
    }

    private static var finalState: CricketChaseState10868 {
        CricketChaseState10868(
            battingSubject: "South Africa",
            context: nil,
            runs: .reported(text: "\(finalRuns)", value: Double(finalRuns)),
            runsCaption: "all out",
            target: .reported(text: "\(targetRuns)", value: Double(targetRuns)),
            targetCaption: "runs",
            wickets: ownerWickets(lost: finalWickets, of: 10),
            wicketsText: finalWicketsText,
            oversText: finalOvers,
            reportDetail: finalReport
        )
    }

    /// Every field explicit: constructed cases never default through retained values.
    private static func make(
        phase: CricketChasePhase10868,
        eyebrow: String,
        headline: String?,
        pregame: CricketChaseReading10868,
        comparisonLabel: String,
        comparison: CricketChaseReading10868,
        contractResult: CricketChaseContractResult10868,
        matchResult: CricketChaseMatchResult10868,
        actual: CricketChaseActual10868,
        detailsRef: CricketChaseRef10868?,
        notes: [String]
    ) -> CricketChaseInput10868 {
        CricketChaseInput10868(
            phase: phase,
            subject: subject,
            eyebrow: eyebrow,
            headline: headline,
            pregameLabel: pregameLabel,
            pregame: pregame,
            comparisonLabel: comparisonLabel,
            comparison: comparison,
            resultLabel: resultLabel,
            contractResult: contractResult,
            matchResult: matchResult,
            actual: actual,
            detailsRef: detailsRef,
            notes: notes
        )
    }

    /// A retained in-play frame, with no retained reference.
    private static func during(_ index: Int) -> CricketChaseInput10868 {
        let frame = frames[index]
        return make(
            phase: .during,
            eyebrow: duringEyebrow,
            headline: "\(frame.referenceRunsStillNeeded) runs still needed",
            pregame: pregame,
            comparisonLabel: recordedLabel,
            comparison: .observed(CricketChaseFigure10868(text: frame.recordedText, detail: frame.recordedDetail)),
            contractResult: .unavailable(notYetKnown),
            matchResult: .unavailable(notYetKnown),
            actual: .reported(state(frame)),
            detailsRef: nil,
            notes: notes
        )
    }

    /// The retained final, with no retained reference.
    private static var finalInput: CricketChaseInput10868 {
        make(
            phase: .final,
            eyebrow: finalEyebrow,
            headline: nil,
            pregame: pregame,
            comparisonLabel: recordedLabel,
            comparison: .unavailable(currentUnavailable),
            contractResult: graded,
            matchResult: finalMatch,
            actual: .reported(finalState),
            detailsRef: nil,
            notes: notes
        )
    }

    /// CONSTRUCTED: a state whose runs and target are supplied explicitly.
    private static func constructedState(
        runs: CricketChaseQuantity10868,
        target: CricketChaseQuantity10868,
        wickets: [CricketChaseWicket10868],
        wicketsText: String
    ) -> CricketChaseState10868 {
        CricketChaseState10868(
            battingSubject: "South Africa",
            context: "Constructed context",
            runs: runs,
            runsCaption: "runs scored",
            target: target,
            targetCaption: "runs",
            wickets: wickets,
            wicketsText: wicketsText,
            oversText: "Constructed overs",
            reportDetail: "Constructed report clock"
        )
    }

    private static func constructedDuring(actual: CricketChaseActual10868, comparison: CricketChaseReading10868) -> CricketChaseInput10868 {
        make(
            phase: .during,
            eyebrow: duringEyebrow,
            headline: "Constructed headline",
            pregame: pregame,
            comparisonLabel: recordedLabel,
            comparison: comparison,
            contractResult: .unavailable(notYetKnown),
            matchResult: .unavailable(notYetKnown),
            actual: actual,
            detailsRef: nil,
            notes: []
        )
    }

    private static func allSpoken(_ input: CricketChaseInput10868) -> String {
        [
            input.accessibilityHeader,
            input.accessibilityChances,
            input.accessibilityRuns,
            input.accessibilityWickets,
            input.accessibilityReport,
            input.accessibilityNotes,
        ]
        .compactMap { $0 }
        .joined(separator: " | ")
    }

    // MARK: Retained packet

    func testRetainedPacketValuesAreTheArchivedOnes() {
        XCTAssertEqual(Self.frames.map(\.runs), [154, 166, 201, 201])
        XCTAssertEqual(Self.frames.map(\.wickets), [4, 6, 6, 8])
        XCTAssertEqual(Self.frames.map(\.overs), ["64.0", "73.0", "84.0", "85.0"])
        XCTAssertEqual(Self.frames.map(\.recordedProbability), [0.03, 0.01, 0.02, 0.01])
        XCTAssertEqual(Self.frames.map(\.barEnd), [
            "2026-10-13T09:11:00+00:00", "2026-10-13T09:46:00+00:00",
            "2026-10-13T11:03:00+00:00", "2026-10-13T11:09:00+00:00",
        ])
        XCTAssertEqual(Self.frames.map(\.reportedAt), [
            "2026-10-13T09:11:34.000Z", "2026-10-13T09:49:56.000Z",
            "2026-10-13T11:03:34.000Z", "2026-10-13T11:11:58.000Z",
        ])
        XCTAssertEqual(Self.frames.map(\.key), [
            "block-6acdf5298f084a13d13ca4ea", "block-6acdfe288f08741d63f9bedf",
            "block-6ace0f308f0874762783cf04", "block-6ace11b98f0811efce0fe34a",
        ])
        XCTAssertEqual(Self.pregameProbability, 0.48)
        XCTAssertEqual(Self.pregameBarEnd, "2026-10-09T00:00:00+00:00")
        XCTAssertEqual(Self.ticker, "KXTESTMATCH-26OCT090330AUSSA-SA")
        XCTAssertEqual(Self.side, "Yes")
        // The packet's reference arithmetic is consistent with its own fields;
        // the leaf never computes it.
        for frame in Self.frames {
            XCTAssertEqual(Self.targetRuns - frame.runs, frame.referenceRunsStillNeeded)
            XCTAssertEqual(10 - frame.wickets, frame.referenceWicketsRemaining)
        }
        XCTAssertEqual(Self.targetRuns - Self.finalRuns, 215)
        XCTAssertNotEqual(Self.targetRuns - Self.finalRuns, Self.finalMarginRuns)
    }

    func testRetainedFramesShowOwnerRunsTargetWicketsAndOversVerbatim() throws {
        for (index, frame) in Self.frames.enumerated() {
            let input = Self.during(index)
            XCTAssertEqual(input.visibleHeading, "\(frame.referenceRunsStillNeeded) runs still needed")
            XCTAssertNil(input.visibleHeadingDetail)
            let state = try XCTUnwrap(input.visibleState)
            XCTAssertEqual(state.runs, .reported(text: "\(frame.runs)", value: Double(frame.runs)))
            XCTAssertEqual(state.target, .reported(text: "421", value: 421))
            XCTAssertEqual(state.context, frame.label)
            XCTAssertEqual(state.oversText, frame.oversText)
            XCTAssertEqual(state.wicketsText, "\(frame.referenceWicketsRemaining) wickets left")
            XCTAssertNil(input.visibleActualWords)
        }
    }

    func testRetainedFramesKeepBaseline48BesideEachOwnRecordedChance() {
        for (index, frame) in Self.frames.enumerated() {
            let input = Self.during(index)
            XCTAssertEqual(input.pregame, Self.pregame)
            XCTAssertEqual(
                input.visibleComparison,
                .observed(CricketChaseFigure10868(text: frame.recordedText, detail: frame.recordedDetail))
            )
            XCTAssertNil(input.visibleContractResult)
            XCTAssertEqual(
                input.accessibilityChances,
                "Pregame: 48%, \(Self.pregameDetail). Recorded win chance: \(frame.recordedText), \(frame.recordedDetail)"
            )
        }
    }

    func testRetainedScoreAndProbabilityClocksStaySeparate() {
        for (index, frame) in Self.frames.enumerated() {
            let input = Self.during(index)
            XCTAssertTrue(input.accessibilityChances.contains(frame.recordedDetail))
            XCTAssertFalse(input.accessibilityChances.contains(frame.reportDetail))
            XCTAssertEqual(input.accessibilityReport, frame.reportDetail)
            XCTAssertFalse(input.accessibilityReport!.contains(frame.recordedDetail))
            XCTAssertFalse(input.accessibilityRuns!.contains(frame.recordedDetail))
        }
        // Lunch: the 09:46Z minute bar and the 09:49:56Z report are two clocks.
        let lunch = Self.during(1)
        XCTAssertTrue(lunch.accessibilityChances.contains("2:45–2:46 AM"))
        XCTAssertEqual(lunch.accessibilityReport, Self.frames[1].reportDetail)
        XCTAssertTrue(lunch.accessibilityReport!.contains("2:49 AM"))
        XCTAssertEqual(lunch.accessibilityWickets, "4 wickets left. Lunch · 73 overs played. Day 5 · lunch")
    }

    func testRetainedRowsCarryNoInventedReferenceSoNoDetails() {
        for index in Self.frames.indices {
            XCTAssertNil(Self.during(index).detailsRef)
            XCTAssertNil(Self.during(index).detailsAction(canOpenDetails: true))
        }
        XCTAssertNil(Self.finalInput.detailsAction(canOpenDetails: true))
    }

    func testRetainedRailPlacesRunsOnTheTargetDomain() throws {
        for (index, frame) in Self.frames.enumerated() {
            let geometry = try XCTUnwrap(Self.during(index).railGeometry)
            XCTAssertEqual(geometry.fill, Double(frame.runs) / 421, accuracy: 1e-12)
            XCTAssertEqual(geometry.target, 1)
            XCTAssertFalse(Self.during(index).showsRailNotDrawn)
        }
        let finalGeometry = try XCTUnwrap(Self.finalInput.railGeometry)
        XCTAssertEqual(finalGeometry.fill, 206.0 / 421, accuracy: 1e-12)
        XCTAssertEqual(finalGeometry.target, 1)
    }

    func testTenSourceWicketPositionsPerRetainedFrameAndFinal() {
        for (index, frame) in Self.frames.enumerated() {
            let wickets = Self.during(index).visibleWickets
            XCTAssertEqual(wickets.count, 10)
            XCTAssertEqual(wickets.filter { $0 == .lost }.count, frame.wickets)
            XCTAssertEqual(wickets.filter { $0 == .remaining }.count, 10 - frame.wickets)
            XCTAssertEqual(Array(wickets.prefix(frame.wickets)), Array(repeating: .lost, count: frame.wickets))
            XCTAssertFalse(wickets.contains(.unknown))
        }
        XCTAssertEqual(Self.finalInput.visibleWickets, Array(repeating: .lost, count: 10))
    }

    func testSpokenRetainedLunchFrameIsExact() {
        let lunch = Self.during(1)
        XCTAssertEqual(lunch.accessibilityHeader, "South Africa · second innings. 255 runs still needed")
        XCTAssertEqual(
            lunch.accessibilityRuns,
            "South Africa: 166 runs scored. Target to win: 421 runs. Target to win is not a projected finish"
        )
        XCTAssertEqual(lunch.accessibilityNotes, Self.notes[0])
    }

    // MARK: Owner words, not leaf arithmetic

    func testRunsNeededAndWicketsLeftAreOwnerTextNeverLeafOutput() {
        // CONSTRUCTED: the owner supplies no headline and its own wickets words.
        let state = CricketChaseState10868(
            battingSubject: "South Africa",
            context: nil,
            runs: .reported(text: "154", value: 154),
            runsCaption: "runs scored",
            target: .reported(text: "421", value: 421),
            targetCaption: "runs",
            wickets: Self.ownerWickets(lost: 4, of: 10),
            wicketsText: "Wickets in hand: see report",
            oversText: "64 overs played",
            reportDetail: "Constructed report clock"
        )
        let input = Self.make(
            phase: .during, eyebrow: Self.duringEyebrow, headline: nil, pregame: Self.pregame,
            comparisonLabel: Self.recordedLabel, comparison: .unavailable(Self.currentUnavailable),
            contractResult: .unavailable(Self.notYetKnown), matchResult: .unavailable(Self.notYetKnown),
            actual: .reported(state), detailsRef: nil, notes: []
        )
        XCTAssertNil(input.visibleHeading)
        let spoken = Self.allSpoken(input)
        XCTAssertFalse(spoken.contains("267"))
        XCTAssertFalse(spoken.contains("6 wickets"))
        XCTAssertTrue(spoken.contains("Wickets in hand: see report"))
    }

    func testTargetLabelAndNotAProjectionQualifierAreAlwaysPresent() {
        XCTAssertEqual(CricketChaseInput10868.targetLabel, "Target to win")
        XCTAssertTrue(CricketChaseInput10868.targetQualifier.contains("not a projected finish"))
        for input in Self.frames.indices.map(Self.during) + [Self.finalInput] {
            XCTAssertTrue(input.accessibilityRuns!.contains("Target to win: 421 runs"))
            XCTAssertTrue(input.accessibilityRuns!.contains(CricketChaseInput10868.targetQualifier))
            XCTAssertFalse(input.accessibilityRuns!.lowercased().contains("projected 421"))
            XCTAssertFalse(input.accessibilityRuns!.contains("%"))
        }
    }

    func testPhaseLabelsAreTheOwnersWords() {
        let current = Self.make(
            phase: .during, eyebrow: Self.duringEyebrow, headline: "Constructed headline", pregame: Self.pregame,
            comparisonLabel: Self.currentLabel,
            comparison: .observed(CricketChaseFigure10868(text: "2%", detail: "Constructed current clock")),
            contractResult: .unavailable(Self.notYetKnown), matchResult: .unavailable(Self.notYetKnown),
            actual: .unavailable(Self.scoreUnavailable), detailsRef: nil, notes: []
        )
        XCTAssertEqual(current.accessibilityChances, "Pregame: 48%, \(Self.pregameDetail). Current win chance: 2%, Constructed current clock")
        XCTAssertFalse(current.accessibilityChances.contains("Recorded"))
    }

    // MARK: Before

    func testBeforeSuppressesEveryFutureFieldDespiteSuppliedData() {
        let input = Self.make(
            phase: .before,
            eyebrow: Self.beforeEyebrow,
            headline: "267 runs still needed",
            pregame: Self.pregame,
            comparisonLabel: Self.recordedLabel,
            comparison: .observed(CricketChaseFigure10868(text: "3%", detail: Self.frames[0].recordedDetail)),
            contractResult: Self.graded,
            matchResult: Self.finalMatch,
            actual: .reported(Self.finalState),
            detailsRef: nil,
            notes: Self.notes
        )
        XCTAssertNil(input.visibleHeading)
        XCTAssertNil(input.visibleHeadingDetail)
        XCTAssertNil(input.visibleComparison)
        XCTAssertNil(input.visibleContractResult)
        XCTAssertNil(input.visibleActual)
        XCTAssertNil(input.visibleState)
        XCTAssertNil(input.visibleActualWords)
        XCTAssertEqual(input.visibleWickets, [])
        XCTAssertNil(input.railGeometry)
        XCTAssertFalse(input.showsRailNotDrawn)
        XCTAssertEqual(input.visibleNotes, [])
        XCTAssertNil(input.accessibilityRuns)
        XCTAssertNil(input.accessibilityWickets)
        XCTAssertNil(input.accessibilityReport)
        XCTAssertNil(input.accessibilityNotes)
        XCTAssertEqual(input.accessibilityHeader, Self.beforeEyebrow)
        XCTAssertEqual(input.accessibilityChances, "Pregame: 48%, \(Self.pregameDetail)")
        let spoken = Self.allSpoken(input)
        for leak in ["421", "206", "214", "267", "Lost", "3%", "all out", "Australia won", "wickets", "overs", "Target"] {
            XCTAssertFalse(spoken.contains(leak), leak)
        }
    }

    func testBeforeSuppressesAnUnavailableActualsWordsToo() {
        let input = Self.make(
            phase: .before, eyebrow: Self.beforeEyebrow, headline: nil, pregame: Self.pregame,
            comparisonLabel: Self.recordedLabel, comparison: .unavailable(Self.currentUnavailable),
            contractResult: .unavailable(Self.notYetKnown), matchResult: .unavailable(Self.notYetKnown),
            actual: .unavailable(Self.scoreUnavailable), detailsRef: nil, notes: []
        )
        XCTAssertNil(input.visibleActualWords)
        XCTAssertNil(input.accessibilityRuns)
        XCTAssertFalse(Self.allSpoken(input).contains(Self.scoreUnavailable))
    }

    func testBeforeKeepsAMissingPregamesOwnWords() {
        let input = Self.make(
            phase: .before, eyebrow: Self.beforeEyebrow, headline: nil,
            pregame: .unavailable("No pregame reading"),
            comparisonLabel: Self.recordedLabel, comparison: .unavailable(Self.currentUnavailable),
            contractResult: .unavailable(Self.notYetKnown), matchResult: .unavailable(Self.notYetKnown),
            actual: .unavailable(Self.scoreUnavailable), detailsRef: nil, notes: []
        )
        XCTAssertEqual(input.accessibilityChances, "Pregame: No pregame reading")
    }

    func testEachPhaseShowsOnlyItsOwnFields() {
        for phase in CricketChasePhase10868.allCases {
            let input = Self.make(
                phase: phase, eyebrow: "Constructed eyebrow", headline: "Constructed headline", pregame: Self.pregame,
                comparisonLabel: Self.recordedLabel,
                comparison: .observed(CricketChaseFigure10868(text: "3%", detail: "Constructed bar")),
                contractResult: Self.graded, matchResult: Self.finalMatch,
                actual: .reported(Self.finalState), detailsRef: nil, notes: Self.notes
            )
            XCTAssertEqual(input.visibleComparison != nil, phase == .during, "\(phase)")
            XCTAssertEqual(input.visibleContractResult != nil, phase == .final, "\(phase)")
            XCTAssertEqual(input.visibleHeadingDetail != nil, phase == .final, "\(phase)")
            XCTAssertEqual(input.visibleState != nil, phase != .before, "\(phase)")
            XCTAssertEqual(input.visibleNotes.isEmpty, phase == .before, "\(phase)")
            switch phase {
            case .before: XCTAssertNil(input.visibleHeading)
            case .during: XCTAssertEqual(input.visibleHeading, "Constructed headline")
            case .final: XCTAssertEqual(input.visibleHeading, Self.finalMatchText)
            }
        }
    }

    // MARK: Final

    func testFinalShowsReportedInningsMatchResultAndUnknownOvers() throws {
        let input = Self.finalInput
        XCTAssertEqual(input.visibleHeading, "Australia won by 214 runs")
        XCTAssertEqual(input.visibleHeadingDetail, Self.finalMatchDetail)
        let state = try XCTUnwrap(input.visibleState)
        XCTAssertEqual(state.runs, .reported(text: "206", value: 206))
        XCTAssertEqual(state.runsCaption, "all out")
        XCTAssertEqual(state.target, .reported(text: "421", value: 421))
        XCTAssertEqual(state.oversText, "Final overs unknown")
        XCTAssertNil(input.visibleComparison)
        XCTAssertEqual(input.visibleContractResult, Self.graded)
        XCTAssertEqual(
            input.accessibilityHeader,
            "The chase · final. Australia won by 214 runs. \(Self.finalMatchDetail)"
        )
        XCTAssertEqual(
            input.accessibilityChances,
            "Pregame: 48%, \(Self.pregameDetail). Final: Lost, \(Self.gradedDetail)"
        )
        XCTAssertEqual(
            input.accessibilityRuns,
            "South Africa: 206 all out. Target to win: 421 runs. Target to win is not a projected finish"
        )
        XCTAssertEqual(input.accessibilityWickets, "All ten wickets lost. Final overs unknown")
        XCTAssertEqual(input.accessibilityReport, Self.finalReport)
    }

    func testFinalClocksStaySeparate() {
        let spoken = Self.allSpoken(Self.finalInput)
        XCTAssertTrue(spoken.contains("4:24 AM"))
        XCTAssertTrue(spoken.contains("4:26 AM"))
        XCTAssertTrue(spoken.contains("5:35 AM"))
        XCTAssertFalse(Self.finalInput.accessibilityChances.contains("4:24 AM"))
        XCTAssertFalse(Self.finalInput.accessibilityReport!.contains("5:35 AM"))
    }

    func testFinalMarginIsTheOwnersNeverTargetMinusRuns() {
        XCTAssertFalse(Self.allSpoken(Self.finalInput).contains("215"))
        let unreported = Self.make(
            phase: .final, eyebrow: Self.finalEyebrow, headline: "Constructed in-play headline", pregame: Self.pregame,
            comparisonLabel: Self.recordedLabel, comparison: .unavailable(Self.currentUnavailable),
            contractResult: Self.graded, matchResult: .unavailable("Match result not yet reported"),
            actual: .reported(Self.finalState), detailsRef: nil, notes: []
        )
        XCTAssertEqual(unreported.visibleHeading, "Match result not yet reported")
        XCTAssertNil(unreported.visibleHeadingDetail)
        let spoken = Self.allSpoken(unreported)
        XCTAssertFalse(spoken.contains("214"))
        XCTAssertFalse(spoken.contains("215"))
        XCTAssertFalse(spoken.contains("Australia"))
        XCTAssertFalse(spoken.contains("Constructed in-play headline"))
    }

    func testFinalUnconfirmedAndVoidResultsStayWordsNeverALoss() {
        let cases: [CricketChaseContractResult10868] = [
            .unconfirmed("Result not yet confirmed"),
            .void("Market voided — no result"),
            .unavailable("Result unavailable"),
        ]
        for result in cases {
            let input = Self.make(
                phase: .final, eyebrow: Self.finalEyebrow, headline: nil, pregame: Self.pregame,
                comparisonLabel: Self.recordedLabel, comparison: .unavailable(Self.currentUnavailable),
                contractResult: result, matchResult: Self.finalMatch,
                actual: .reported(Self.finalState), detailsRef: nil, notes: []
            )
            XCTAssertEqual(input.visibleContractResult, result)
            XCTAssertFalse(input.accessibilityChances.contains("Lost"))
            XCTAssertTrue(input.accessibilityChances.hasPrefix("Pregame: 48%, \(Self.pregameDetail). Final: "))
            // The physical result stays visible beside an unknown contract result.
            XCTAssertEqual(input.visibleHeading, Self.finalMatchText)
        }
    }

    func testFinalNeverShowsASettledReadingAsAChance() {
        let input = Self.make(
            phase: .final, eyebrow: Self.finalEyebrow, headline: nil, pregame: Self.pregame,
            comparisonLabel: Self.currentLabel,
            comparison: .observed(CricketChaseFigure10868(text: "0%", detail: "Constructed settled price")),
            contractResult: .unconfirmed("Result not yet confirmed"), matchResult: Self.finalMatch,
            actual: .reported(Self.finalState), detailsRef: nil, notes: []
        )
        XCTAssertNil(input.visibleComparison)
        XCTAssertFalse(input.accessibilityChances.contains("Current win chance"))
        XCTAssertFalse(input.accessibilityChances.contains("Constructed settled price"))
    }

    func testContradictoryContractResultStaysIndependentOfPhysicalContext() throws {
        // CONSTRUCTED: runs past the target, with a supplied "Lost".
        let state = Self.constructedState(
            runs: .reported(text: "430", value: 430),
            target: .reported(text: "421", value: 421),
            wickets: Self.ownerWickets(lost: 3, of: 10),
            wicketsText: "7 wickets left"
        )
        let input = Self.make(
            phase: .final, eyebrow: Self.finalEyebrow, headline: nil, pregame: Self.pregame,
            comparisonLabel: Self.recordedLabel, comparison: .unavailable(Self.currentUnavailable),
            contractResult: Self.graded, matchResult: .reported(CricketChaseFigure10868(text: "Constructed result words", detail: "Constructed result clock")),
            actual: .reported(state), detailsRef: nil, notes: []
        )
        XCTAssertEqual(input.visibleContractResult, Self.graded)
        XCTAssertEqual(input.visibleHeading, "Constructed result words")
        let geometry = try XCTUnwrap(input.railGeometry)
        XCTAssertEqual(geometry.fill, 1)
        XCTAssertEqual(geometry.target, 421.0 / 430, accuracy: 1e-12)
    }

    // MARK: Failed score versus failed probability

    func testFailedProbabilityKeepsActualsAndBaseline() {
        let input = Self.constructedDuring(
            actual: .reported(Self.state(Self.frames[0])),
            comparison: .unavailable(Self.currentUnavailable)
        )
        XCTAssertNotNil(input.visibleState)
        XCTAssertNotNil(input.railGeometry)
        XCTAssertEqual(input.visibleWickets.count, 10)
        XCTAssertEqual(input.accessibilityChances, "Pregame: 48%, \(Self.pregameDetail). Recorded win chance: Current probability unavailable")
    }

    func testWithheldCurrentKeepsItsSlotAndShowsNoStaleValue() {
        let input = Self.constructedDuring(
            actual: .reported(Self.state(Self.frames[2])),
            comparison: .withheld(Self.held)
        )
        XCTAssertEqual(input.visibleComparison, .withheld(Self.held))
        XCTAssertEqual(input.accessibilityChances, "Pregame: 48%, \(Self.pregameDetail). Recorded win chance: Held — not current")
        XCTAssertFalse(input.accessibilityChances.contains("2%"))
    }

    func testFailedScoreKeepsRealProbabilities() {
        let input = Self.constructedDuring(
            actual: .unavailable(Self.scoreUnavailable),
            comparison: .observed(CricketChaseFigure10868(text: "3%", detail: Self.frames[0].recordedDetail))
        )
        XCTAssertNil(input.visibleState)
        XCTAssertEqual(input.visibleActualWords, Self.scoreUnavailable)
        XCTAssertNil(input.railGeometry)
        XCTAssertFalse(input.showsRailNotDrawn)
        XCTAssertEqual(input.visibleWickets, [])
        XCTAssertEqual(input.accessibilityRuns, Self.scoreUnavailable)
        XCTAssertNil(input.accessibilityWickets)
        XCTAssertNil(input.accessibilityReport)
        XCTAssertEqual(
            input.accessibilityChances,
            "Pregame: 48%, \(Self.pregameDetail). Recorded win chance: 3%, \(Self.frames[0].recordedDetail)"
        )
    }

    func testBothFailedKeepEveryOwnersWords() {
        let input = Self.make(
            phase: .during, eyebrow: Self.duringEyebrow, headline: nil,
            pregame: .withheld("Pregame not admitted"),
            comparisonLabel: Self.recordedLabel, comparison: .unavailable(Self.currentUnavailable),
            contractResult: .unavailable(Self.notYetKnown), matchResult: .unavailable(Self.notYetKnown),
            actual: .unavailable(Self.scoreUnavailable), detailsRef: nil, notes: []
        )
        XCTAssertEqual(input.accessibilityChances, "Pregame: Pregame not admitted. Recorded win chance: Current probability unavailable")
        XCTAssertEqual(input.accessibilityRuns, Self.scoreUnavailable)
    }

    // MARK: Rail geometry

    func testZeroRunsIsARealEmptyFill() {
        let input = Self.constructedDuring(
            actual: .reported(Self.constructedState(
                runs: .reported(text: "0", value: 0),
                target: .reported(text: "421", value: 421),
                wickets: Self.ownerWickets(lost: 0, of: 10),
                wicketsText: "10 wickets left"
            )),
            comparison: .unavailable(Self.currentUnavailable)
        )
        XCTAssertEqual(input.railGeometry, CricketChaseRailGeometry10868(fill: 0, target: 1))
        XCTAssertFalse(input.showsRailNotDrawn)
        XCTAssertTrue(input.accessibilityRuns!.hasPrefix("South Africa: 0 runs scored."))
    }

    func testUnknownRunsStayWordsNeverZero() {
        let input = Self.constructedDuring(
            actual: .reported(Self.constructedState(
                runs: .unknown("Runs not reported"),
                target: .reported(text: "421", value: 421),
                wickets: [],
                wicketsText: "Wickets unknown"
            )),
            comparison: .unavailable(Self.currentUnavailable)
        )
        XCTAssertNil(input.railGeometry)
        XCTAssertTrue(input.showsRailNotDrawn)
        XCTAssertEqual(
            input.accessibilityRuns,
            "South Africa: Runs not reported. Target to win: 421 runs. Target to win is not a projected finish. Run progress not drawn"
        )
        XCTAssertFalse(input.accessibilityRuns!.contains(" 0 "))
        XCTAssertEqual(input.visibleWickets, [])
    }

    func testUnknownTargetStaysWordsAndDrawsNoAxis() {
        let input = Self.constructedDuring(
            actual: .reported(Self.constructedState(
                runs: .reported(text: "154", value: 154),
                target: .unknown("Target not confirmed"),
                wickets: Self.ownerWickets(lost: 4, of: 10),
                wicketsText: "6 wickets left"
            )),
            comparison: .unavailable(Self.currentUnavailable)
        )
        XCTAssertNil(input.railGeometry)
        XCTAssertTrue(input.showsRailNotDrawn)
        XCTAssertTrue(input.accessibilityRuns!.contains("Target to win: Target not confirmed."))
    }

    func testMalformedRunsOrTargetDrawNoInventedAxis() {
        let badRuns: [Double] = [-1, -0.0001, .nan, .infinity, -.infinity]
        for runs in badRuns {
            XCTAssertNil(CricketChaseGeometry10868.rail(runs: runs, target: 421), "\(runs)")
        }
        let badTargets: [Double] = [0, -0.0, -421, .nan, .infinity, -.infinity]
        for target in badTargets {
            XCTAssertNil(CricketChaseGeometry10868.rail(runs: 154, target: target), "\(target)")
            XCTAssertNil(CricketChaseGeometry10868.rail(runs: 0, target: target), "\(target)")
        }
        XCTAssertNil(CricketChaseGeometry10868.rail(runs: nil, target: 421))
        XCTAssertNil(CricketChaseGeometry10868.rail(runs: 154, target: nil))
        // A tiny real target is drawn on its own domain, never lifted to 1.
        XCTAssertEqual(CricketChaseGeometry10868.rail(runs: 0.25, target: 0.5), CricketChaseRailGeometry10868(fill: 0.5, target: 1))
    }

    func testTargetCrossingStaysInsideTheVisibleDomain() throws {
        XCTAssertEqual(CricketChaseGeometry10868.rail(runs: 421, target: 421), CricketChaseRailGeometry10868(fill: 1, target: 1))
        let beyond = try XCTUnwrap(CricketChaseGeometry10868.rail(runs: 450, target: 421))
        XCTAssertEqual(beyond.fill, 1)
        XCTAssertEqual(beyond.target, 421.0 / 450, accuracy: 1e-12)
        let far = try XCTUnwrap(CricketChaseGeometry10868.rail(runs: 1e300, target: 421))
        XCTAssertEqual(far.fill, 1)
        XCTAssertGreaterThanOrEqual(far.target, 0)
        XCTAssertLessThanOrEqual(far.target, 1)
    }

    func testRailXKeepsTheEndMarkWhole() {
        XCTAssertEqual(CricketChaseGeometry10868.x(0, width: 300, inset: 1), 1)
        XCTAssertEqual(CricketChaseGeometry10868.x(1, width: 300, inset: 1), 299)
        XCTAssertEqual(CricketChaseGeometry10868.x(0.5, width: 300, inset: 0), 150)
        XCTAssertEqual(CricketChaseGeometry10868.x(1, width: 1, inset: 1), 1)
    }

    // MARK: Wickets

    func testConstructedUnknownWicketsStayOwnerPositionsAndWords() {
        let positions: [CricketChaseWicket10868] = [.lost, .lost, .lost, .unknown, .unknown, .unknown, .unknown, .unknown, .unknown, .unknown]
        let input = Self.constructedDuring(
            actual: .reported(Self.constructedState(
                runs: .reported(text: "120", value: 120),
                target: .reported(text: "421", value: 421),
                wickets: positions,
                wicketsText: "3 wickets lost · rest unconfirmed"
            )),
            comparison: .unavailable(Self.currentUnavailable)
        )
        XCTAssertEqual(input.visibleWickets, positions)
        XCTAssertEqual(input.accessibilityWickets, "3 wickets lost · rest unconfirmed. Constructed overs. Constructed context")
    }

    func testTheOwnerOwnsTheWicketCount() {
        let few = Array(repeating: CricketChaseWicket10868.remaining, count: 3)
        let input = Self.constructedDuring(
            actual: .reported(Self.constructedState(
                runs: .reported(text: "12", value: 12),
                target: .reported(text: "40", value: 40),
                wickets: few,
                wicketsText: "Constructed wickets words"
            )),
            comparison: .unavailable(Self.currentUnavailable)
        )
        XCTAssertEqual(input.visibleWickets, few)
        XCTAssertEqual(CricketChaseWicket10868.allCases, [.lost, .remaining, .unknown])
    }

    // MARK: Identity and actions

    func testDetailsRequiresAnExactReferenceAndACallback() {
        let input = Self.make(
            phase: .during, eyebrow: Self.duringEyebrow, headline: nil, pregame: Self.pregame,
            comparisonLabel: Self.recordedLabel, comparison: .unavailable(Self.currentUnavailable),
            contractResult: .unavailable(Self.notYetKnown), matchResult: .unavailable(Self.notYetKnown),
            actual: .unavailable(Self.scoreUnavailable), detailsRef: Self.ref, notes: []
        )
        XCTAssertEqual(input.detailsAction(canOpenDetails: true), .details(Self.ref))
        XCTAssertNil(input.detailsAction(canOpenDetails: false))
        XCTAssertEqual(input.detailsText, "South Africa wins · Details")

        var opened: [CricketChaseRef10868] = []
        input.detailsAction(canOpenDetails: true)?.perform(onDetails: { opened.append($0) })
        XCTAssertEqual(opened, [Self.ref])
        // A missing callback is a no-op, never a crash.
        input.detailsAction(canOpenDetails: true)?.perform(onDetails: nil)
        XCTAssertEqual(opened, [Self.ref])
    }

    func testHeldIdentityKeepsItsExactReferenceAndWithdrawnIdentityHasNone() {
        let earlier = Self.make(
            phase: .during, eyebrow: Self.duringEyebrow, headline: "267 runs still needed", pregame: Self.pregame,
            comparisonLabel: Self.recordedLabel,
            comparison: .observed(CricketChaseFigure10868(text: "3%", detail: Self.frames[0].recordedDetail)),
            contractResult: .unavailable(Self.notYetKnown), matchResult: .unavailable(Self.notYetKnown),
            actual: .reported(Self.state(Self.frames[0])), detailsRef: Self.ref, notes: []
        )
        let later = Self.make(
            phase: .during, eyebrow: Self.duringEyebrow, headline: "255 runs still needed", pregame: Self.pregame,
            comparisonLabel: Self.recordedLabel,
            comparison: .observed(CricketChaseFigure10868(text: "1%", detail: Self.frames[1].recordedDetail)),
            contractResult: .unavailable(Self.notYetKnown), matchResult: .unavailable(Self.notYetKnown),
            actual: .reported(Self.state(Self.frames[1])), detailsRef: Self.ref, notes: []
        )
        XCTAssertEqual(earlier.detailsAction(canOpenDetails: true), later.detailsAction(canOpenDetails: true))
        let withdrawn = Self.make(
            phase: .during, eyebrow: Self.duringEyebrow, headline: "255 runs still needed", pregame: Self.pregame,
            comparisonLabel: Self.recordedLabel, comparison: .withheld(Self.held),
            contractResult: .unavailable(Self.notYetKnown), matchResult: .unavailable(Self.notYetKnown),
            actual: .reported(Self.state(Self.frames[1])), detailsRef: nil, notes: []
        )
        XCTAssertNil(withdrawn.detailsAction(canOpenDetails: true))
    }

    func testStaticContentNeedsNoCallbackInAnyPhase() {
        for phase in CricketChasePhase10868.allCases {
            let input = Self.make(
                phase: phase, eyebrow: "Constructed eyebrow", headline: nil, pregame: Self.pregame,
                comparisonLabel: Self.recordedLabel, comparison: .unavailable(Self.currentUnavailable),
                contractResult: .unavailable(Self.notYetKnown), matchResult: .unavailable(Self.notYetKnown),
                actual: .unavailable(Self.scoreUnavailable), detailsRef: Self.ref, notes: []
            )
            XCTAssertNil(input.detailsAction(canOpenDetails: false), "\(phase)")
            XCTAssertFalse(input.accessibilityChances.isEmpty)
        }
    }

    func testAccessibilityIdentifiersAreStable() {
        XCTAssertEqual(CricketChaseAccessibilityID10868.header, "cricketChase10868.header")
        XCTAssertEqual(CricketChaseAccessibilityID10868.chances, "cricketChase10868.chances")
        XCTAssertEqual(CricketChaseAccessibilityID10868.runs, "cricketChase10868.runs")
        XCTAssertEqual(CricketChaseAccessibilityID10868.wickets, "cricketChase10868.wickets")
        XCTAssertEqual(CricketChaseAccessibilityID10868.report, "cricketChase10868.report")
        XCTAssertEqual(CricketChaseAccessibilityID10868.notes, "cricketChase10868.notes")
        XCTAssertEqual(CricketChaseAccessibilityID10868.details, "cricketChase10868.details")
    }

    // MARK: No parsed or derived inputs

    func testInputsCarryNoDerivedRunsNeededMarginProjectionOrParsedFields() {
        let inputLabels = Set(Mirror(reflecting: Self.finalInput).children.compactMap { $0.label })
        XCTAssertEqual(inputLabels, [
            "phase", "subject", "eyebrow", "headline", "pregameLabel", "pregame", "comparisonLabel",
            "comparison", "resultLabel", "contractResult", "matchResult", "actual", "detailsRef", "notes",
        ])
        let stateLabels = Set(Mirror(reflecting: Self.finalState).children.compactMap { $0.label })
        XCTAssertEqual(stateLabels, [
            "battingSubject", "context", "runs", "runsCaption", "target", "targetCaption",
            "wickets", "wicketsText", "oversText", "reportDetail",
        ])
        for forbidden in ["runsNeeded", "wicketsLeft", "margin", "projection", "winner", "ticker", "title", "probability"] {
            XCTAssertFalse(inputLabels.contains(forbidden), forbidden)
            XCTAssertFalse(stateLabels.contains(forbidden), forbidden)
        }
    }

    // MARK: Long words and dates

    func testLongQualifiedWordsAndDatesStayWhole() {
        let longDetail = "Kalshi trade close · minute ending 2:11 AM Pacific Daylight Time, Tuesday, October 13, 2026 · bar boundary, not the exact trade or arrival"
        let longReport = "Score report published 2:11 AM Pacific Daylight Time, Tuesday, October 13, 2026 · publication time, not the exact ball time"
        let state = CricketChaseState10868(
            battingSubject: "Constructed Extraordinarily-Long-Batting-Side-Name",
            context: "Day 5 · morning session · constructed long context",
            runs: .reported(text: "154", value: 154),
            runsCaption: "runs scored",
            target: .reported(text: "421", value: 421),
            targetCaption: "runs",
            wickets: Self.ownerWickets(lost: 4, of: 10),
            wicketsText: "6 wickets left",
            oversText: "64 overs played",
            reportDetail: longReport
        )
        let input = Self.make(
            phase: .during, eyebrow: Self.duringEyebrow, headline: "Constructed headline", pregame: Self.pregame,
            comparisonLabel: Self.recordedLabel,
            comparison: .observed(CricketChaseFigure10868(text: "3%", detail: longDetail)),
            contractResult: .unavailable(Self.notYetKnown), matchResult: .unavailable(Self.notYetKnown),
            actual: .reported(state), detailsRef: nil, notes: []
        )
        XCTAssertTrue(input.accessibilityChances.hasSuffix(longDetail))
        XCTAssertEqual(input.accessibilityReport, longReport)
        XCTAssertTrue(input.accessibilityRuns!.hasPrefix("Constructed Extraordinarily-Long-Batting-Side-Name: 154 runs scored."))
        XCTAssertEqual(
            CricketChaseGeometry10868.words("Constructed Extraordinarily-Long-Batting-Side-Name  runs\nscored"),
            ["Constructed", "Extraordinarily-Long-Batting-Side-Name", "runs", "scored"]
        )
    }

    // MARK: Measured layout (CONSTRUCTED widths)

    /// A subview that wraps down to `minimum` (its widest word or whole
    /// figure) and is `ideal` wide unconstrained.
    private static func measure(ideal: CGFloat, minimum: CGFloat) -> (CGFloat?) -> CGFloat {
        { proposal in
            guard let proposal else { return ideal }
            return max(minimum, min(ideal, proposal))
        }
    }

    /// Card content widths for 320, 375 and 393 pt screens with 16 pt card
    /// padding each side, and a wide reader.
    private static let contentWidths: [CGFloat] = [288, 343, 361, 700]

    func testChancePairSitsSideBySideWhenBothFiguresFit() {
        for width in Self.contentWidths {
            let arrangement = CricketChaseGeometry10868.pairArrangement(
                available: width, spacing: 16, equalColumns: true, forceStack: false,
                first: Self.measure(ideal: 160, minimum: 64),
                second: Self.measure(ideal: 200, minimum: 92)
            )
            XCTAssertEqual(arrangement, .sideBySide, "\(width)")
        }
    }

    func testChancePairStacksForAnOverWideFigureLongWordOrAccessibilitySize() {
        XCTAssertEqual(CricketChaseGeometry10868.pairArrangement(
            available: 288, spacing: 16, equalColumns: true, forceStack: false,
            first: Self.measure(ideal: 160, minimum: 64),
            second: Self.measure(ideal: 300, minimum: 140)
        ), .stacked)
        XCTAssertEqual(CricketChaseGeometry10868.pairArrangement(
            available: 700, spacing: 16, equalColumns: true, forceStack: true,
            first: Self.measure(ideal: 60, minimum: 60),
            second: Self.measure(ideal: 60, minimum: 60)
        ), .stacked)
        XCTAssertEqual(CricketChaseGeometry10868.pairArrangement(
            available: nil, spacing: 16, equalColumns: true, forceStack: false,
            first: Self.measure(ideal: 60, minimum: 60),
            second: Self.measure(ideal: 60, minimum: 60)
        ), .sideBySide)
    }

    func testRunsTargetAndWicketsLinesShareARowOnlyWhenBothIdealsFit() {
        // Standard type at 320: runs block 120, target block 100.
        XCTAssertEqual(CricketChaseGeometry10868.pairArrangement(
            available: 288, spacing: 16, equalColumns: false, forceStack: false,
            first: Self.measure(ideal: 120, minimum: 90),
            second: Self.measure(ideal: 100, minimum: 90)
        ), .sideBySide)
        // Large type at 320: 190 + 16 + 170 > 288.
        XCTAssertEqual(CricketChaseGeometry10868.pairArrangement(
            available: 288, spacing: 16, equalColumns: false, forceStack: false,
            first: Self.measure(ideal: 190, minimum: 120),
            second: Self.measure(ideal: 170, minimum: 120)
        ), .stacked)
        // The same at a wide reader fits.
        XCTAssertEqual(CricketChaseGeometry10868.pairArrangement(
            available: 700, spacing: 16, equalColumns: false, forceStack: false,
            first: Self.measure(ideal: 190, minimum: 120),
            second: Self.measure(ideal: 170, minimum: 120)
        ), .sideBySide)
        XCTAssertEqual(CricketChaseGeometry10868.pairArrangement(
            available: 288, spacing: 12, equalColumns: false, forceStack: false,
            first: { _ in .infinity },
            second: Self.measure(ideal: 10, minimum: 10)
        ), .stacked)
    }

    func testColumnSplits() {
        XCTAssertEqual(
            CricketChaseGeometry10868.columns(total: 288, secondIdeal: 0, spacing: 16, equalColumns: true),
            CricketChaseColumns10868(first: 136, second: 136)
        )
        XCTAssertEqual(
            CricketChaseGeometry10868.columns(total: 288, secondIdeal: 100, spacing: 16, equalColumns: false),
            CricketChaseColumns10868(first: 172, second: 100)
        )
        XCTAssertEqual(
            CricketChaseGeometry10868.columns(total: 100, secondIdeal: 400, spacing: 16, equalColumns: false),
            CricketChaseColumns10868(first: 0, second: 84)
        )
        XCTAssertEqual(CricketChaseGeometry10868.equalColumn(available: 10, spacing: 16), 0)
    }
}

/// #10868 — the cricket-live survival card ("Can they hold on?") as a
/// stateless, live-only presentation leaf in the chase package.
///
/// The view is SwiftUI and is not rasterised here. What is asserted is the
/// rules it defers to: live-only gating (before and final draw and speak
/// nothing even when later data is supplied), the owner's pregame and
/// separately admitted headline reading, each checkpoint's wicket shapes and
/// words, report provenance and separately recorded chance with its own bar
/// provenance, independent failures, real zero versus missing versus held,
/// owner order with no cap, exact select/Details targets (the checkpoint id
/// with the one shared original), duplicate, empty, inconsistent and
/// withdrawn identities, the tile grid geometry and the spoken text. Nothing
/// here claims a rendered fit, a native runtime, live app delivery or a
/// production binding.
///
/// ARCHIVED raw values come from South Africa–Australia, first Test, Day 5,
/// October 13, 2026 (route cricket-live), as retained in
/// `shipping-adoption-20261027/CRICKET-SURVIVAL-RETAINED-CASES.json`.
/// Original: Kalshi KXTESTMATCH-26OCT090330AUSSA-TIE, side Yes ("Draw/Tie").
/// No internal app event/market/outcome id is retained.
///   Pregame 0.09, hourly bar ending 2026-10-09T00:00Z.
///   Published score reports (publication, not exact ball time) and the
///   independently timed recorded draw/tie minute bars:
///     09:11:34Z  4 wickets  64.0 overs          recorded 0.35, bar end 09:11Z
///     09:49:56Z  6 wickets  73.0 overs (lunch)  recorded 0.17, bar end 09:45Z
///     11:03:34Z  6 wickets  84.0 overs          recorded 0.20, bar end 11:02Z
///     11:11:58Z  8 wickets  85.0 overs          recorded 0.03, bar end 11:11Z
///   Reference arithmetic only (not a captured field, not a leaf policy and
///   not a predictor): wickets left 6/4/4/2. The later finalized No is
///   future information and is never an input here.
///
/// CONSTRUCTED owner-resolved inputs (this leaf does not resolve them): every
/// display string (figures, local-calendar provenance, labels, wicket words,
/// notes), the owner's wicket positions built from the ARCHIVED counts, every
/// identity and action reference (none is retained; the canonical binding
/// gives all four retained keys one constructed original), and every phase,
/// headline, missing, withheld, zero, unknown-wicket, duplicate, withdrawn,
/// extra-checkpoint, long-text and measured-width case.
final class CricketSurvivalPresentation10868Tests: XCTestCase {

    // MARK: ARCHIVED source

    private static let ticker = "KXTESTMATCH-26OCT090330AUSSA-TIE"
    private static let side = "Yes"
    private static let pregameProbability = 0.09
    private static let pregameBarEnd = "2026-10-09T00:00:00+00:00"

    private struct RetainedCheckpoint {
        /// ARCHIVED.
        let key: String
        let label: String
        let reportedAt: String
        let wickets: Int
        let overs: String
        let recordedProbability: Double
        let barEnd: String
        /// ARCHIVED reference arithmetic, not a captured field.
        let referenceWicketsRemaining: Int
        /// CONSTRUCTED owner text.
        let ownerLabel: String
        let chanceText: String
        let barDetail: String
        let reportDetail: String
    }

    /// An ordered array, never a lookup: a constructed id cannot reach it.
    private static let retained: [RetainedCheckpoint] = [
        RetainedCheckpoint(
            key: "block-6acdf5298f084a13d13ca4ea", label: "Day 5 · 64 overs", reportedAt: "2026-10-13T09:11:34.000Z",
            wickets: 4, overs: "64.0", recordedProbability: 0.35, barEnd: "2026-10-13T09:11:00+00:00",
            referenceWicketsRemaining: 6,
            ownerLabel: "Day 5 · 64 overs", chanceText: "35%",
            barDetail: "Kalshi trade close · minute 2:10–2:11 AM PDT, Oct 13",
            reportDetail: "Score report published 2:11 AM PDT, Oct 13 · not the exact ball time"
        ),
        RetainedCheckpoint(
            key: "block-6acdfe288f08741d63f9bedf", label: "Day 5 · lunch", reportedAt: "2026-10-13T09:49:56.000Z",
            wickets: 6, overs: "73.0", recordedProbability: 0.17, barEnd: "2026-10-13T09:45:00+00:00",
            referenceWicketsRemaining: 4,
            ownerLabel: "Day 5 · lunch · 73 overs", chanceText: "17%",
            barDetail: "Kalshi trade close · minute 2:44–2:45 AM PDT, Oct 13",
            reportDetail: "Lunch · last score report before lunch, published 2:49 AM PDT, Oct 13 · not the exact ball time"
        ),
        RetainedCheckpoint(
            key: "block-6ace0f308f0874762783cf04", label: "Day 5 · 84 overs", reportedAt: "2026-10-13T11:03:34.000Z",
            wickets: 6, overs: "84.0", recordedProbability: 0.20, barEnd: "2026-10-13T11:02:00+00:00",
            referenceWicketsRemaining: 4,
            ownerLabel: "Day 5 · 84 overs", chanceText: "20%",
            barDetail: "Kalshi trade close · minute 4:01–4:02 AM PDT, Oct 13",
            reportDetail: "Score report published 4:03 AM PDT, Oct 13 · not the exact ball time"
        ),
        RetainedCheckpoint(
            key: "block-6ace11b98f0811efce0fe34a", label: "Day 5 · 85 overs", reportedAt: "2026-10-13T11:11:58.000Z",
            wickets: 8, overs: "85.0", recordedProbability: 0.03, barEnd: "2026-10-13T11:11:00+00:00",
            referenceWicketsRemaining: 2,
            ownerLabel: "Day 5 · 85 overs", chanceText: "3%",
            barDetail: "Kalshi trade close · minute 4:10–4:11 AM PDT, Oct 13",
            reportDetail: "Score report published 4:11 AM PDT, Oct 13 · not the exact ball time"
        ),
    ]

    // MARK: CONSTRUCTED owner words

    private static let subject = "Draw / tie · original market"
    private static let title = "Can they hold on?"
    private static let pregameLabel = "Pregame"
    private static let recordedLabel = "Recorded draw / tie chance"
    private static let currentLabel = "Current draw / tie chance"
    private static let checkpointsLabel = "Reported wickets remaining and separately timed draw or tie probabilities"
    private static let chanceLabel = "Recorded draw / tie"
    private static let pregameText = "9%"
    private static let pregameDetail = "Kalshi trade close · hour 4–5 PM PDT, Oct 8"
    private static let currentUnavailable = "Current probability unavailable"
    private static let pregameUnavailable = "Pregame probability unavailable"
    private static let notRecorded = "Not recorded"
    private static let held = "Held — not current"
    private static let reportUnavailable = "Score report unavailable"
    private static let notes = ["Wickets show the reported score. Percentages are separate market observations, not a prediction from wickets alone."]

    /// CONSTRUCTED canonical binding: every checkpoint reports on the one
    /// draw/tie original, so all of them share this one owner triple.
    private static let original = CricketChaseRef10868(event: "owner-event-1", market: "owner-market-tie", outcome: "owner-outcome-draw-tie")
    /// CONSTRUCTED disagreeing original, for the inconsistent case only.
    private static let otherOriginal = CricketChaseRef10868(event: "owner-event-1", market: "owner-market-tie", outcome: "owner-outcome-other")

    private static func target(_ checkpointID: String) -> CricketSurvivalTarget10868 {
        CricketSurvivalTarget10868(checkpointID: checkpointID, original: original)
    }

    private static var pregame: CricketChaseReading10868 {
        .observed(CricketChaseFigure10868(text: pregameText, detail: pregameDetail))
    }

    /// CONSTRUCTED owner resolution of an ARCHIVED wicket count.
    private static func ownerWickets(lost: Int, of total: Int) -> [CricketChaseWicket10868] {
        Array(repeating: .lost, count: lost) + Array(repeating: .remaining, count: total - lost)
    }

    private static func report(_ retained: RetainedCheckpoint) -> CricketSurvivalReport10868 {
        CricketSurvivalReport10868(
            wickets: ownerWickets(lost: retained.wickets, of: 10),
            wicketsText: "\(retained.referenceWicketsRemaining) wickets left",
            reportDetail: retained.reportDetail
        )
    }

    private static func recorded(_ retained: RetainedCheckpoint) -> CricketChaseReading10868 {
        .observed(CricketChaseFigure10868(text: retained.chanceText, detail: retained.barDetail))
    }

    /// Every field explicit: constructed checkpoints never default through
    /// retained values.
    private static func checkpoint(
        id: String,
        ref: CricketChaseRef10868?,
        label: String,
        actual: CricketSurvivalActual10868,
        chanceLabel: String,
        chance: CricketChaseReading10868
    ) -> CricketSurvivalCheckpoint10868 {
        CricketSurvivalCheckpoint10868(id: id, ref: ref, label: label, actual: actual, chanceLabel: chanceLabel, chance: chance)
    }

    /// A retained checkpoint, with no retained reference.
    private static func retainedCheckpoint(_ index: Int) -> CricketSurvivalCheckpoint10868 {
        let source = Self.retained[index]
        return checkpoint(
            id: source.key, ref: nil, label: source.ownerLabel,
            actual: .reported(report(source)), chanceLabel: chanceLabel, chance: recorded(source)
        )
    }

    private static var retainedCheckpoints: [CricketSurvivalCheckpoint10868] {
        retained.indices.map { retainedCheckpoint($0) }
    }

    /// A retained checkpoint under the CONSTRUCTED canonical binding: its
    /// ARCHIVED key with the one shared original.
    private static func boundCheckpoint(_ index: Int) -> CricketSurvivalCheckpoint10868 {
        let source = Self.retained[index]
        return checkpoint(
            id: source.key, ref: original, label: source.ownerLabel,
            actual: .reported(report(source)), chanceLabel: chanceLabel, chance: recorded(source)
        )
    }

    private static var boundCheckpoints: [CricketSurvivalCheckpoint10868] {
        retained.indices.map { boundCheckpoint($0) }
    }

    private static func make(
        phase: CricketChasePhase10868,
        pregame: CricketChaseReading10868,
        comparisonLabel: String,
        comparison: CricketChaseReading10868,
        checkpoints: [CricketSurvivalCheckpoint10868],
        selectedCheckpointID: String?,
        notes: [String]
    ) -> CricketSurvivalInput10868 {
        CricketSurvivalInput10868(
            phase: phase,
            subject: subject,
            title: title,
            pregameLabel: pregameLabel,
            pregame: pregame,
            comparisonLabel: comparisonLabel,
            comparison: comparison,
            checkpointsLabel: checkpointsLabel,
            checkpoints: checkpoints,
            selectedCheckpointID: selectedCheckpointID,
            notes: notes
        )
    }

    /// The retained live card. The headline reading is the owner's own
    /// admitted choice, supplied separately from the tiles.
    private static var live: CricketSurvivalInput10868 {
        make(
            phase: .during, pregame: pregame, comparisonLabel: recordedLabel,
            comparison: recorded(retained[3]), checkpoints: retainedCheckpoints,
            selectedCheckpointID: nil, notes: notes
        )
    }

    private static func lostCount(_ wickets: [CricketChaseWicket10868]) -> Int {
        wickets.filter { $0 == .lost }.count
    }

    // MARK: Retained cases

    func testRetainedPacketValuesAreTheArchivedOnes() {
        XCTAssertEqual(Self.ticker, "KXTESTMATCH-26OCT090330AUSSA-TIE")
        XCTAssertEqual(Self.side, "Yes")
        XCTAssertEqual(Self.pregameProbability, 0.09)
        XCTAssertEqual(Self.pregameBarEnd, "2026-10-09T00:00:00+00:00")
        XCTAssertEqual(Self.retained.map(\.wickets), [4, 6, 6, 8])
        XCTAssertEqual(Self.retained.map(\.overs), ["64.0", "73.0", "84.0", "85.0"])
        XCTAssertEqual(Self.retained.map(\.recordedProbability), [0.35, 0.17, 0.20, 0.03])
        XCTAssertEqual(Self.retained.map(\.label), ["Day 5 · 64 overs", "Day 5 · lunch", "Day 5 · 84 overs", "Day 5 · 85 overs"])
        XCTAssertEqual(
            Self.retained.map(\.barEnd),
            ["2026-10-13T09:11:00+00:00", "2026-10-13T09:45:00+00:00", "2026-10-13T11:02:00+00:00", "2026-10-13T11:11:00+00:00"]
        )
        XCTAssertEqual(
            Self.retained.map(\.reportedAt),
            ["2026-10-13T09:11:34.000Z", "2026-10-13T09:49:56.000Z", "2026-10-13T11:03:34.000Z", "2026-10-13T11:11:58.000Z"]
        )
        // Reference arithmetic is checked here, in the test, and never by the leaf.
        XCTAssertEqual(Self.retained.map { 10 - $0.wickets }, Self.retained.map(\.referenceWicketsRemaining))
        XCTAssertEqual(Self.retained.map(\.referenceWicketsRemaining), [6, 4, 4, 2])
        // Each bar closes before its report is published; neither is the other's clock.
        for retained in Self.retained {
            XCTAssertLessThan(retained.barEnd.prefix(19), retained.reportedAt.prefix(19), retained.key)
        }
        XCTAssertLessThan(Self.pregameBarEnd, Self.retained[0].barEnd)
    }

    func testRetainedCheckpointsKeepBaselineNineBesideEachOwnRecordedChance() {
        let input = Self.live
        XCTAssertTrue(input.isShown)
        XCTAssertEqual(input.visiblePregame, .observed(CricketChaseFigure10868(text: "9%", detail: Self.pregameDetail)))
        XCTAssertEqual(input.visibleCheckpoints.count, 4)
        XCTAssertEqual(input.visibleCheckpoints.map(\.id), Self.retained.map(\.key))
        XCTAssertEqual(
            input.visibleCheckpoints.map(\.label),
            ["Day 5 · 64 overs", "Day 5 · lunch · 73 overs", "Day 5 · 84 overs", "Day 5 · 85 overs"]
        )
        XCTAssertEqual(input.visibleCheckpoints.map(\.chance), Self.retained.map { Self.recorded($0) })
        XCTAssertEqual(input.visibleCheckpoints.map { $0.report?.wicketsText }, ["6 wickets left", "4 wickets left", "4 wickets left", "2 wickets left"])
        XCTAssertEqual(input.visibleCheckpoints.map { Self.lostCount($0.report?.wickets ?? []) }, [4, 6, 6, 8])
        XCTAssertEqual(input.visibleCheckpoints.map { $0.report?.wickets.count }, [10, 10, 10, 10])
        XCTAssertEqual(input.visibleCheckpoints.map(\.chanceLabel), Array(repeating: "Recorded draw / tie", count: 4))
        XCTAssertEqual(input.visibleCheckpoints.map(\.ref), [nil, nil, nil, nil])
        XCTAssertEqual(input.visibleNotes, Self.notes)
    }

    func testSpokenRetainedLunchCheckpointHeaderAndChancesAreExact() {
        let input = Self.live
        XCTAssertEqual(input.accessibilityHeader, "Draw / tie · original market. Can they hold on?")
        XCTAssertEqual(
            input.accessibilityChances,
            "Pregame: 9%, Kalshi trade close · hour 4–5 PM PDT, Oct 8. "
                + "Recorded draw / tie chance: 3%, Kalshi trade close · minute 4:10–4:11 AM PDT, Oct 13"
        )
        XCTAssertEqual(
            input.accessibilityCheckpoint(input.visibleCheckpoints[1]),
            "Day 5 · lunch · 73 overs. 4 wickets left. "
                + "Lunch · last score report before lunch, published 2:49 AM PDT, Oct 13 · not the exact ball time. "
                + "Recorded draw / tie: 17%, Kalshi trade close · minute 2:44–2:45 AM PDT, Oct 13"
        )
        XCTAssertEqual(input.accessibilityNotes, Self.notes[0])
    }

    func testReportAndBarClocksStayInTheirOwnSlots() throws {
        let input = Self.live
        for (index, checkpoint) in input.visibleCheckpoints.enumerated() {
            let report = try XCTUnwrap(checkpoint.report)
            guard case .observed(let figure) = checkpoint.chance else { return XCTFail("\(index)") }
            XCTAssertEqual(report.reportDetail, Self.retained[index].reportDetail)
            XCTAssertEqual(figure.detail, Self.retained[index].barDetail)
            XCTAssertNotEqual(report.reportDetail, figure.detail)
            let spoken = input.accessibilityCheckpoint(checkpoint)
            let reportRange = try XCTUnwrap(spoken.range(of: report.reportDetail))
            let barRange = try XCTUnwrap(spoken.range(of: figure.detail))
            XCTAssertLessThan(reportRange.lowerBound, barRange.lowerBound)
        }
        // Lunch: the 2:45 bar is not the 2:49 publication, and neither moves.
        guard case .observed(let lunchBar) = input.visibleCheckpoints[1].chance else { return XCTFail("lunch") }
        XCTAssertTrue(lunchBar.detail.contains("2:44–2:45 AM"))
        XCTAssertFalse(lunchBar.detail.contains("2:49"))
        XCTAssertTrue(try XCTUnwrap(input.visibleCheckpoints[1].report).reportDetail.contains("2:49 AM"))
        XCTAssertFalse(try XCTUnwrap(input.visibleCheckpoints[1].report).reportDetail.contains("2:45"))
    }

    func testEqualWicketsKeepTheirOwnDifferentChances() {
        let input = Self.live
        let lunch = input.visibleCheckpoints[1]
        let later = input.visibleCheckpoints[2]
        XCTAssertEqual(lunch.report?.wickets, later.report?.wickets)
        XCTAssertEqual(lunch.report?.wicketsText, later.report?.wicketsText)
        XCTAssertEqual(lunch.chance, .observed(CricketChaseFigure10868(text: "17%", detail: Self.retained[1].barDetail)))
        XCTAssertEqual(later.chance, .observed(CricketChaseFigure10868(text: "20%", detail: Self.retained[2].barDetail)))
        // More wickets and a missing chance: no chance is inferred from wickets.
        let noChance = Self.checkpoint(
            id: "c-constructed", ref: nil, label: "Constructed checkpoint",
            actual: .reported(Self.report(Self.retained[3])), chanceLabel: Self.chanceLabel, chance: .unavailable(Self.notRecorded)
        )
        XCTAssertEqual(noChance.chance, .unavailable(Self.notRecorded))
        XCTAssertFalse(Self.live.accessibilityCheckpoint(noChance).contains("%"))
    }

    // MARK: Headline readings

    func testHeadlineIsTheOwnersReadingNeverTheLastCheckpoint() {
        let input = Self.make(
            phase: .during, pregame: Self.pregame, comparisonLabel: Self.currentLabel,
            comparison: .observed(CricketChaseFigure10868(text: "5%", detail: "Constructed current reading · 4:20 AM PDT, Oct 13")),
            checkpoints: Self.retainedCheckpoints, selectedCheckpointID: nil, notes: []
        )
        XCTAssertEqual(input.visibleComparison, .observed(CricketChaseFigure10868(text: "5%", detail: "Constructed current reading · 4:20 AM PDT, Oct 13")))
        XCTAssertEqual(
            input.accessibilityChances,
            "Pregame: 9%, Kalshi trade close · hour 4–5 PM PDT, Oct 8. Current draw / tie chance: 5%, Constructed current reading · 4:20 AM PDT, Oct 13"
        )
        XCTAssertEqual(input.visibleCheckpoints.last?.chance, Self.recorded(Self.retained[3]))
    }

    func testMissingOrHeldCurrentKeepsPregameAndItsOwnSlot() {
        for (comparison, words) in [
            (CricketChaseReading10868.unavailable(Self.currentUnavailable), Self.currentUnavailable),
            (CricketChaseReading10868.withheld(Self.held), Self.held),
        ] {
            let input = Self.make(
                phase: .during, pregame: Self.pregame, comparisonLabel: Self.currentLabel, comparison: comparison,
                checkpoints: Self.retainedCheckpoints, selectedCheckpointID: nil, notes: []
            )
            XCTAssertEqual(input.visiblePregame, Self.pregame)
            XCTAssertEqual(input.visibleComparison, comparison)
            XCTAssertEqual(
                input.accessibilityChances,
                "Pregame: 9%, Kalshi trade close · hour 4–5 PM PDT, Oct 8. Current draw / tie chance: \(words)"
            )
            // Never the last tile, never zero, never pregame.
            XCTAssertFalse(input.accessibilityChances!.contains("3%"))
            XCTAssertFalse(input.accessibilityChances!.contains("0%"))
            XCTAssertFalse(input.accessibilityChances!.hasSuffix("9%"))
        }
        let noPregame = Self.make(
            phase: .during, pregame: .unavailable(Self.pregameUnavailable), comparisonLabel: Self.recordedLabel,
            comparison: Self.recorded(Self.retained[3]), checkpoints: [], selectedCheckpointID: nil, notes: []
        )
        XCTAssertEqual(
            noPregame.accessibilityChances,
            "Pregame: Pregame probability unavailable. Recorded draw / tie chance: 3%, Kalshi trade close · minute 4:10–4:11 AM PDT, Oct 13"
        )
    }

    // MARK: Independent failures

    func testChanceFailureKeepsActualsAndActualFailureKeepsChance() {
        let chanceFailed = Self.checkpoint(
            id: "c1", ref: nil, label: "Day 5 · 64 overs", actual: .reported(Self.report(Self.retained[0])),
            chanceLabel: Self.chanceLabel, chance: .unavailable(Self.notRecorded)
        )
        let heldChance = Self.checkpoint(
            id: "c2", ref: nil, label: "Day 5 · lunch · 73 overs", actual: .reported(Self.report(Self.retained[1])),
            chanceLabel: Self.chanceLabel, chance: .withheld(Self.held)
        )
        let actualFailed = Self.checkpoint(
            id: "c3", ref: nil, label: "Day 5 · 84 overs", actual: .unavailable(Self.reportUnavailable),
            chanceLabel: Self.chanceLabel, chance: Self.recorded(Self.retained[2])
        )
        let bothFailed = Self.checkpoint(
            id: "c4", ref: nil, label: "Day 5 · 85 overs", actual: .unavailable(Self.reportUnavailable),
            chanceLabel: Self.chanceLabel, chance: .unavailable(Self.notRecorded)
        )
        let input = Self.make(
            phase: .during, pregame: Self.pregame, comparisonLabel: Self.recordedLabel, comparison: .unavailable(Self.currentUnavailable),
            checkpoints: [chanceFailed, heldChance, actualFailed, bothFailed], selectedCheckpointID: nil, notes: []
        )
        XCTAssertEqual(input.visibleCheckpoints.count, 4)
        XCTAssertEqual(chanceFailed.report, Self.report(Self.retained[0]))
        XCTAssertNil(chanceFailed.actualWords)
        XCTAssertEqual(
            input.accessibilityCheckpoint(chanceFailed),
            "Day 5 · 64 overs. 6 wickets left. Score report published 2:11 AM PDT, Oct 13 · not the exact ball time. Recorded draw / tie: Not recorded"
        )
        XCTAssertEqual(
            input.accessibilityCheckpoint(heldChance),
            "Day 5 · lunch · 73 overs. 4 wickets left. "
                + "Lunch · last score report before lunch, published 2:49 AM PDT, Oct 13 · not the exact ball time. Recorded draw / tie: Held — not current"
        )
        XCTAssertNil(actualFailed.report)
        XCTAssertEqual(actualFailed.actualWords, Self.reportUnavailable)
        XCTAssertEqual(
            input.accessibilityCheckpoint(actualFailed),
            "Day 5 · 84 overs. Score report unavailable. Recorded draw / tie: 20%, Kalshi trade close · minute 4:01–4:02 AM PDT, Oct 13"
        )
        XCTAssertEqual(
            input.accessibilityCheckpoint(bothFailed),
            "Day 5 · 85 overs. Score report unavailable. Recorded draw / tie: Not recorded"
        )
    }

    func testRealZeroIsAValueNotMissing() {
        let zero = Self.checkpoint(
            id: "z1", ref: nil, label: "Constructed checkpoint", actual: .unavailable(Self.reportUnavailable),
            chanceLabel: Self.chanceLabel,
            chance: .observed(CricketChaseFigure10868(text: "0%", detail: "Constructed minute bar · 4:30–4:31 AM PDT, Oct 13"))
        )
        let input = Self.make(
            phase: .during, pregame: Self.pregame, comparisonLabel: Self.currentLabel,
            comparison: .observed(CricketChaseFigure10868(text: "0%", detail: "Constructed current reading · 4:31 AM PDT, Oct 13")),
            checkpoints: [zero], selectedCheckpointID: nil, notes: []
        )
        XCTAssertNotEqual(zero.chance, .unavailable(Self.notRecorded))
        XCTAssertEqual(
            input.accessibilityCheckpoint(zero),
            "Constructed checkpoint. Score report unavailable. Recorded draw / tie: 0%, Constructed minute bar · 4:30–4:31 AM PDT, Oct 13"
        )
        XCTAssertTrue(input.accessibilityChances!.hasSuffix("Current draw / tie chance: 0%, Constructed current reading · 4:31 AM PDT, Oct 13"))
    }

    // MARK: Wicket states

    func testUnknownMissingAndOwnerCountedWicketsStayTheOwners() {
        let noMarks = CricketSurvivalReport10868(wickets: [], wicketsText: "Wickets unknown", reportDetail: "Constructed report")
        let mixed = CricketSurvivalReport10868(
            wickets: [.lost, .unknown, .remaining, .unknown, .lost],
            wicketsText: "Some wickets unconfirmed",
            reportDetail: "Constructed report"
        )
        let eleven = CricketSurvivalReport10868(
            wickets: Self.ownerWickets(lost: 3, of: 11), wicketsText: "Constructed eleven positions", reportDetail: "Constructed report"
        )
        let checkpoints = [noMarks, mixed, eleven].enumerated().map { index, report in
            Self.checkpoint(
                id: "w\(index)", ref: nil, label: "Constructed \(index)", actual: .reported(report),
                chanceLabel: Self.chanceLabel, chance: .unavailable(Self.notRecorded)
            )
        }
        let input = Self.make(
            phase: .during, pregame: Self.pregame, comparisonLabel: Self.recordedLabel, comparison: .unavailable(Self.currentUnavailable),
            checkpoints: checkpoints, selectedCheckpointID: nil, notes: []
        )
        XCTAssertEqual(input.visibleCheckpoints[0].report?.wickets, [])
        XCTAssertEqual(input.visibleCheckpoints[1].report?.wickets, [.lost, .unknown, .remaining, .unknown, .lost])
        XCTAssertEqual(input.visibleCheckpoints[2].report?.wickets.count, 11)
        XCTAssertEqual(Self.lostCount(input.visibleCheckpoints[2].report?.wickets ?? []), 3)
        XCTAssertEqual(
            input.visibleCheckpoints.map { input.accessibilityCheckpoint($0) },
            [
                "Constructed 0. Wickets unknown. Constructed report. Recorded draw / tie: Not recorded",
                "Constructed 1. Some wickets unconfirmed. Constructed report. Recorded draw / tie: Not recorded",
                "Constructed 2. Constructed eleven positions. Constructed report. Recorded draw / tie: Not recorded",
            ]
        )
    }

    // MARK: Live only

    func testOutsideLiveTheCardDrawsAndSpeaksNothingDespiteSuppliedData() {
        let checkpoints = Self.boundCheckpoints
        // Control: the same supplied data is actionable and spoken in play.
        let during = Self.make(
            phase: .during, pregame: Self.pregame, comparisonLabel: Self.currentLabel,
            comparison: .observed(CricketChaseFigure10868(text: "0%", detail: "Constructed settlement-time reading")),
            checkpoints: checkpoints, selectedCheckpointID: Self.retained[0].key, notes: Self.notes
        )
        for checkpoint in checkpoints {
            XCTAssertEqual(during.actionTarget(checkpoint), Self.target(checkpoint.id))
            XCTAssertFalse(during.accessibilityCheckpoint(checkpoint).isEmpty)
        }
        for phase in [CricketChasePhase10868.before, .final] {
            for selected in [Self.retained[0].key, "withdrawn-id"] {
                let input = Self.make(
                    phase: phase, pregame: Self.pregame, comparisonLabel: Self.currentLabel,
                    comparison: .observed(CricketChaseFigure10868(text: "0%", detail: "Constructed settlement-time reading")),
                    checkpoints: checkpoints, selectedCheckpointID: selected, notes: Self.notes
                )
                XCTAssertFalse(input.isShown, "\(phase)")
                XCTAssertNil(input.visiblePregame, "\(phase)")
                XCTAssertNil(input.visibleComparison, "\(phase)")
                XCTAssertEqual(input.visibleCheckpoints, [], "\(phase)")
                XCTAssertEqual(input.visibleNotes, [], "\(phase)")
                XCTAssertNil(input.accessibilityHeader, "\(phase)")
                XCTAssertNil(input.accessibilityChances, "\(phase)")
                XCTAssertNil(input.accessibilityNotes, "\(phase)")
                XCTAssertEqual(input.selection, .none, "\(phase)")
                XCTAssertNil(input.selectionNotice, "\(phase)")
                XCTAssertNil(input.detailsAction(canOpenDetails: true), "\(phase)")
                XCTAssertNil(input.detailsText, "\(phase)")
                XCTAssertNil(input.accessibilityID(at: 0), "\(phase)")
                for checkpoint in checkpoints {
                    XCTAssertNil(input.checkpointAction(checkpoint, canSelect: true), "\(phase)")
                    XCTAssertNil(input.actionTarget(checkpoint), "\(phase)")
                    XCTAssertFalse(input.isSelected(checkpoint), "\(phase)")
                    // The raw spoken helper the view uses is empty too: no
                    // later wicket words, report clock or chance leaks.
                    XCTAssertEqual(input.accessibilityCheckpoint(checkpoint), "", "\(phase) \(checkpoint.id)")
                }
                // Also for a later checkpoint the input never carried.
                let later = Self.checkpoint(
                    id: "constructed-later", ref: Self.original, label: "Constructed later checkpoint",
                    actual: .reported(Self.report(Self.retained[3])), chanceLabel: Self.chanceLabel,
                    chance: .observed(CricketChaseFigure10868(text: "0%", detail: "Constructed settlement-time bar"))
                )
                XCTAssertEqual(input.accessibilityCheckpoint(later), "", "\(phase)")
                XCTAssertNil(input.actionTarget(later), "\(phase)")
            }
        }
    }

    // MARK: Actions

    func testExactSelectionAndDetailsHandBackTheCheckpointWithItsOriginal() {
        let first = Self.checkpoint(
            id: "c1", ref: Self.original, label: Self.retained[0].ownerLabel, actual: .reported(Self.report(Self.retained[0])),
            chanceLabel: Self.chanceLabel, chance: Self.recorded(Self.retained[0])
        )
        let lunch = Self.checkpoint(
            id: "c2", ref: Self.original, label: Self.retained[1].ownerLabel, actual: .reported(Self.report(Self.retained[1])),
            chanceLabel: Self.chanceLabel, chance: Self.recorded(Self.retained[1])
        )
        let input = Self.make(
            phase: .during, pregame: Self.pregame, comparisonLabel: Self.recordedLabel, comparison: Self.recorded(Self.retained[3]),
            checkpoints: [first, lunch], selectedCheckpointID: "c2", notes: []
        )
        XCTAssertEqual(input.selection, .checkpoint(lunch))
        XCTAssertFalse(input.isSelected(first))
        XCTAssertTrue(input.isSelected(lunch))
        XCTAssertNil(input.selectionNotice)
        XCTAssertFalse(input.hasInconsistentOriginals)
        XCTAssertEqual(input.checkpointAction(first, canSelect: true), .select(Self.target("c1")))
        XCTAssertEqual(input.checkpointAction(lunch, canSelect: true), .select(Self.target("c2")))
        XCTAssertNotEqual(input.checkpointAction(first, canSelect: true), input.checkpointAction(lunch, canSelect: true))
        XCTAssertEqual(input.detailsAction(canOpenDetails: true), .details(Self.target("c2")))
        XCTAssertEqual(input.detailsText, "Day 5 · lunch · 73 overs · Details")
        XCTAssertTrue(input.accessibilityCheckpoint(lunch).hasSuffix(". Selected"))
        XCTAssertFalse(input.accessibilityCheckpoint(first).contains("Selected"))

        var selected: [CricketSurvivalTarget10868] = []
        var opened: [CricketSurvivalTarget10868] = []
        input.checkpointAction(first, canSelect: true)?.perform(onSelect: { selected.append($0) }, onDetails: { opened.append($0) })
        input.detailsAction(canOpenDetails: true)?.perform(onSelect: { selected.append($0) }, onDetails: { opened.append($0) })
        XCTAssertEqual(selected, [CricketSurvivalTarget10868(checkpointID: "c1", original: Self.original)])
        XCTAssertEqual(opened, [CricketSurvivalTarget10868(checkpointID: "c2", original: Self.original)])
        // Missing callbacks are no-ops, never a crash.
        input.checkpointAction(first, canSelect: true)?.perform(onSelect: nil, onDetails: nil)
        XCTAssertEqual(selected, [Self.target("c1")])
    }

    func testStaticCheckpointsNeedNoCallbackOrReference() {
        let withRef = Self.checkpoint(
            id: "c1", ref: Self.original, label: "Constructed with ref", actual: .unavailable(Self.reportUnavailable),
            chanceLabel: Self.chanceLabel, chance: .unavailable(Self.notRecorded)
        )
        let noRef = Self.checkpoint(
            id: "c2", ref: nil, label: "Constructed without ref", actual: .unavailable(Self.reportUnavailable),
            chanceLabel: Self.chanceLabel, chance: .unavailable(Self.notRecorded)
        )
        let input = Self.make(
            phase: .during, pregame: Self.pregame, comparisonLabel: Self.recordedLabel, comparison: .unavailable(Self.currentUnavailable),
            checkpoints: [withRef, noRef], selectedCheckpointID: "c2", notes: []
        )
        XCTAssertNil(input.checkpointAction(withRef, canSelect: false))
        XCTAssertEqual(input.actionTarget(withRef), Self.target("c1"))
        XCTAssertNil(input.checkpointAction(noRef, canSelect: true))
        XCTAssertNil(input.actionTarget(noRef))
        XCTAssertTrue(input.isSelected(noRef))
        XCTAssertNil(input.detailsAction(canOpenDetails: true))
        XCTAssertNil(input.detailsAction(canOpenDetails: false))
        XCTAssertEqual(input.visibleCheckpoints, [withRef, noRef])
        XCTAssertFalse(input.accessibilityCheckpoint(noRef).lowercased().contains("tap"))
    }

    func testDuplicateIDsLoseActionsWhileASharedOriginalKeepsThem() {
        let checkpoints = [
            Self.checkpoint(id: "c1", ref: Self.original, label: "Constructed one", actual: .unavailable(Self.reportUnavailable),
                            chanceLabel: Self.chanceLabel, chance: .unavailable(Self.notRecorded)),
            Self.checkpoint(id: "c1", ref: Self.original, label: "Constructed one again", actual: .unavailable(Self.reportUnavailable),
                            chanceLabel: Self.chanceLabel, chance: .unavailable(Self.notRecorded)),
            Self.checkpoint(id: "c3", ref: Self.original, label: "Constructed three", actual: .unavailable(Self.reportUnavailable),
                            chanceLabel: Self.chanceLabel, chance: .unavailable(Self.notRecorded)),
            Self.checkpoint(id: "c4", ref: Self.original, label: "Constructed four", actual: .unavailable(Self.reportUnavailable),
                            chanceLabel: Self.chanceLabel, chance: .unavailable(Self.notRecorded)),
            Self.checkpoint(id: "c5", ref: Self.original, label: "Constructed five", actual: .unavailable(Self.reportUnavailable),
                            chanceLabel: Self.chanceLabel, chance: .unavailable(Self.notRecorded)),
        ]
        let input = Self.make(
            phase: .during, pregame: Self.pregame, comparisonLabel: Self.recordedLabel, comparison: .unavailable(Self.currentUnavailable),
            checkpoints: checkpoints, selectedCheckpointID: "c1", notes: []
        )
        XCTAssertEqual(input.visibleCheckpoints.map(\.label), checkpoints.map(\.label))
        XCTAssertEqual(input.duplicateCheckpointIDs, ["c1"])
        XCTAssertFalse(input.hasInconsistentOriginals)
        // The repeated id is ambiguous: both of its tiles are static.
        for checkpoint in checkpoints.prefix(2) {
            XCTAssertNil(input.checkpointAction(checkpoint, canSelect: true), checkpoint.label)
            XCTAssertNil(input.actionTarget(checkpoint), checkpoint.label)
        }
        // Unique ids sharing the one original stay distinct, exact targets.
        XCTAssertEqual(
            checkpoints.suffix(3).map { input.checkpointAction($0, canSelect: true) },
            [.select(Self.target("c3")), .select(Self.target("c4")), .select(Self.target("c5"))]
        )
        for checkpoint in checkpoints {
            XCTAssertFalse(input.isSelected(checkpoint), checkpoint.label)
        }
        XCTAssertEqual(input.selection, .unavailable("c1"))
        XCTAssertEqual(input.selectionNotice, "Selected checkpoint unavailable in this update.")
        XCTAssertNil(input.detailsAction(canOpenDetails: true))
        let ids = checkpoints.indices.compactMap { input.accessibilityID(at: $0) }
        XCTAssertEqual(ids.count, 5)
        XCTAssertEqual(Set(ids).count, 5)
        XCTAssertEqual(ids[2], "cricketSurvival10868.checkpoint.c3")
        XCTAssertEqual(ids[0], "cricketSurvival10868.checkpoint.c1.0")
        XCTAssertEqual(ids[1], "cricketSurvival10868.checkpoint.c1.1")
        XCTAssertNil(input.accessibilityID(at: 5))
    }

    func testWithdrawnSelectionSelectsNoNeighbourAndKeepsEveryTile() {
        let checkpoints = Self.retained.indices.map { index in
            Self.checkpoint(
                id: "c\(index)", ref: Self.original,
                label: Self.retained[index].ownerLabel, actual: .reported(Self.report(Self.retained[index])),
                chanceLabel: Self.chanceLabel, chance: Self.recorded(Self.retained[index])
            )
        }
        let input = Self.make(
            phase: .during, pregame: Self.pregame, comparisonLabel: Self.recordedLabel, comparison: Self.recorded(Self.retained[3]),
            checkpoints: checkpoints, selectedCheckpointID: "withdrawn", notes: []
        )
        XCTAssertEqual(input.selection, .unavailable("withdrawn"))
        XCTAssertEqual(input.selectionNotice, CricketSurvivalInput10868.selectionUnavailable)
        XCTAssertEqual(checkpoints.filter { input.isSelected($0) }, [])
        XCTAssertNil(input.detailsAction(canOpenDetails: true))
        XCTAssertNil(input.detailsText)
        XCTAssertEqual(input.visibleCheckpoints, checkpoints)
        // The tiles keep their own exact select actions.
        XCTAssertEqual(input.checkpointAction(checkpoints[2], canSelect: true), .select(Self.target("c2")))
        let none = Self.make(
            phase: .during, pregame: Self.pregame, comparisonLabel: Self.recordedLabel, comparison: Self.recorded(Self.retained[3]),
            checkpoints: checkpoints, selectedCheckpointID: nil, notes: []
        )
        XCTAssertEqual(none.selection, .none)
        XCTAssertNil(none.selectionNotice)
    }

    // MARK: Canonical binding: one original, many checkpoints

    func testFourRetainedCheckpointsBoundToOneOriginalAreFourExactTargets() {
        let checkpoints = Self.boundCheckpoints
        XCTAssertEqual(Set(checkpoints.compactMap(\.ref)), [Self.original])
        XCTAssertEqual(checkpoints.map(\.id), Self.retained.map(\.key))
        let unselected = Self.make(
            phase: .during, pregame: Self.pregame, comparisonLabel: Self.recordedLabel, comparison: Self.recorded(Self.retained[3]),
            checkpoints: checkpoints, selectedCheckpointID: nil, notes: Self.notes
        )
        XCTAssertFalse(unselected.hasInconsistentOriginals)
        XCTAssertEqual(unselected.duplicateCheckpointIDs, [])
        let expected = Self.retained.map { CricketSurvivalTarget10868(checkpointID: $0.key, original: Self.original) }
        XCTAssertEqual(checkpoints.map { unselected.actionTarget($0) }, expected)
        XCTAssertEqual(Set(expected).count, 4)
        XCTAssertNil(unselected.detailsAction(canOpenDetails: true))

        var selected: [CricketSurvivalTarget10868] = []
        var opened: [CricketSurvivalTarget10868] = []
        for checkpoint in checkpoints {
            unselected.checkpointAction(checkpoint, canSelect: true)?
                .perform(onSelect: { selected.append($0) }, onDetails: { opened.append($0) })
        }
        XCTAssertEqual(selected, expected)
        XCTAssertEqual(opened, [])

        // The host holds each selection in turn; Details opens exactly that
        // checkpoint, its own label, and marks no other tile.
        for (index, source) in Self.retained.enumerated() {
            let input = Self.make(
                phase: .during, pregame: Self.pregame, comparisonLabel: Self.recordedLabel, comparison: Self.recorded(Self.retained[3]),
                checkpoints: checkpoints, selectedCheckpointID: source.key, notes: Self.notes
            )
            XCTAssertEqual(input.selection, .checkpoint(checkpoints[index]), source.key)
            XCTAssertEqual(checkpoints.filter { input.isSelected($0) }, [checkpoints[index]], source.key)
            XCTAssertEqual(input.detailsAction(canOpenDetails: true), .details(expected[index]), source.key)
            XCTAssertEqual(input.detailsText, "\(source.ownerLabel) · Details")
            var details: [CricketSurvivalTarget10868] = []
            input.detailsAction(canOpenDetails: true)?.perform(onSelect: { _ in XCTFail("select") }, onDetails: { details.append($0) })
            XCTAssertEqual(details, [expected[index]], source.key)
            // No callback: static, and the target is still exact.
            XCTAssertNil(input.checkpointAction(checkpoints[index], canSelect: false), source.key)
            XCTAssertNil(input.detailsAction(canOpenDetails: false), source.key)
            XCTAssertEqual(input.actionTarget(checkpoints[index]), expected[index], source.key)
        }
    }

    func testEmptyIDsAndAbsentOrPartialOriginalsStayStatic() {
        let partials = [
            CricketChaseRef10868(event: "", market: "owner-market-tie", outcome: "owner-outcome-draw-tie"),
            CricketChaseRef10868(event: "owner-event-1", market: "", outcome: "owner-outcome-draw-tie"),
            CricketChaseRef10868(event: "owner-event-1", market: "owner-market-tie", outcome: ""),
        ]
        for partial in partials {
            let checkpoint = Self.checkpoint(
                id: "c-partial", ref: partial, label: "Constructed partial original", actual: .unavailable(Self.reportUnavailable),
                chanceLabel: Self.chanceLabel, chance: .unavailable(Self.notRecorded)
            )
            let input = Self.make(
                phase: .during, pregame: Self.pregame, comparisonLabel: Self.recordedLabel, comparison: .unavailable(Self.currentUnavailable),
                checkpoints: [checkpoint], selectedCheckpointID: "c-partial", notes: []
            )
            XCTAssertNil(input.actionTarget(checkpoint))
            XCTAssertNil(input.checkpointAction(checkpoint, canSelect: true))
            XCTAssertTrue(input.isSelected(checkpoint))
            XCTAssertNil(input.detailsAction(canOpenDetails: true))
        }
        let emptyID = Self.checkpoint(
            id: "", ref: Self.original, label: "Constructed empty id", actual: .unavailable(Self.reportUnavailable),
            chanceLabel: Self.chanceLabel, chance: .unavailable(Self.notRecorded)
        )
        let noRef = Self.checkpoint(
            id: "c-none", ref: nil, label: "Constructed no original", actual: .unavailable(Self.reportUnavailable),
            chanceLabel: Self.chanceLabel, chance: .unavailable(Self.notRecorded)
        )
        let good = Self.boundCheckpoint(0)
        for selectedID in ["", nil] as [String?] {
            let input = Self.make(
                phase: .during, pregame: Self.pregame, comparisonLabel: Self.recordedLabel, comparison: .unavailable(Self.currentUnavailable),
                checkpoints: [emptyID, noRef, good], selectedCheckpointID: selectedID, notes: []
            )
            XCTAssertEqual(input.visibleCheckpoints, [emptyID, noRef, good])
            XCTAssertNil(input.actionTarget(emptyID))
            XCTAssertNil(input.checkpointAction(emptyID, canSelect: true))
            XCTAssertNil(input.actionTarget(noRef))
            XCTAssertNil(input.checkpointAction(noRef, canSelect: true))
            // Their neighbour keeps its own exact target.
            XCTAssertEqual(input.checkpointAction(good, canSelect: true), .select(Self.target(Self.retained[0].key)))
            XCTAssertFalse(input.isSelected(emptyID))
            XCTAssertFalse(input.isSelected(good))
            XCTAssertNil(input.detailsAction(canOpenDetails: true))
        }
        let emptySelection = Self.make(
            phase: .during, pregame: Self.pregame, comparisonLabel: Self.recordedLabel, comparison: .unavailable(Self.currentUnavailable),
            checkpoints: [emptyID, noRef, good], selectedCheckpointID: "", notes: []
        )
        XCTAssertEqual(emptySelection.selection, .unavailable(""))
        XCTAssertEqual(emptySelection.selectionNotice, CricketSurvivalInput10868.selectionUnavailable)
    }

    func testInconsistentOriginalsLeaveEveryTileStatic() {
        var checkpoints = Self.boundCheckpoints
        checkpoints[2] = Self.checkpoint(
            id: Self.retained[2].key, ref: Self.otherOriginal, label: Self.retained[2].ownerLabel,
            actual: .reported(Self.report(Self.retained[2])), chanceLabel: Self.chanceLabel, chance: Self.recorded(Self.retained[2])
        )
        let input = Self.make(
            phase: .during, pregame: Self.pregame, comparisonLabel: Self.recordedLabel, comparison: Self.recorded(Self.retained[3]),
            checkpoints: checkpoints, selectedCheckpointID: Self.retained[1].key, notes: []
        )
        XCTAssertTrue(input.hasInconsistentOriginals)
        XCTAssertEqual(input.visibleCheckpoints, checkpoints)
        for checkpoint in checkpoints {
            XCTAssertNil(input.actionTarget(checkpoint), checkpoint.id)
            XCTAssertNil(input.checkpointAction(checkpoint, canSelect: true), checkpoint.id)
        }
        // The held selection still shows; nothing opens.
        XCTAssertTrue(input.isSelected(checkpoints[1]))
        XCTAssertNil(input.detailsAction(canOpenDetails: true))
        // A tile with no original does not make the others inconsistent.
        var withNil = Self.boundCheckpoints
        withNil[2] = Self.retainedCheckpoint(2)
        let partial = Self.make(
            phase: .during, pregame: Self.pregame, comparisonLabel: Self.recordedLabel, comparison: Self.recorded(Self.retained[3]),
            checkpoints: withNil, selectedCheckpointID: nil, notes: []
        )
        XCTAssertFalse(partial.hasInconsistentOriginals)
        XCTAssertEqual(
            withNil.map { partial.actionTarget($0) },
            [Self.target(Self.retained[0].key), Self.target(Self.retained[1].key), nil, Self.target(Self.retained[3].key)]
        )
        // Nor does a partial original: it is absent, not a second original.
        var withPartial = Self.boundCheckpoints
        withPartial[2] = Self.checkpoint(
            id: Self.retained[2].key,
            ref: CricketChaseRef10868(event: "owner-event-1", market: "owner-market-tie", outcome: ""),
            label: Self.retained[2].ownerLabel, actual: .reported(Self.report(Self.retained[2])),
            chanceLabel: Self.chanceLabel, chance: Self.recorded(Self.retained[2])
        )
        let partialRef = Self.make(
            phase: .during, pregame: Self.pregame, comparisonLabel: Self.recordedLabel, comparison: Self.recorded(Self.retained[3]),
            checkpoints: withPartial, selectedCheckpointID: nil, notes: []
        )
        XCTAssertFalse(partialRef.hasInconsistentOriginals)
        XCTAssertEqual(
            withPartial.map { partialRef.actionTarget($0) },
            [Self.target(Self.retained[0].key), Self.target(Self.retained[1].key), nil, Self.target(Self.retained[3].key)]
        )
    }

    func testWithdrawnTargetKeepsTheHeldSelectionButHandsNothingBack() {
        var checkpoints = Self.boundCheckpoints
        // The owner withdrew the selected checkpoint's original this update.
        checkpoints[1] = Self.retainedCheckpoint(1)
        let input = Self.make(
            phase: .during, pregame: Self.pregame, comparisonLabel: Self.recordedLabel, comparison: Self.recorded(Self.retained[3]),
            checkpoints: checkpoints, selectedCheckpointID: Self.retained[1].key, notes: []
        )
        XCTAssertEqual(input.selection, .checkpoint(checkpoints[1]))
        XCTAssertNil(input.actionTarget(checkpoints[1]))
        XCTAssertNil(input.checkpointAction(checkpoints[1], canSelect: true))
        XCTAssertNil(input.detailsAction(canOpenDetails: true))
        // No neighbour stands in for it.
        XCTAssertEqual(checkpoints.filter { input.isSelected($0) }, [checkpoints[1]])
        XCTAssertEqual(input.checkpointAction(checkpoints[0], canSelect: true), .select(Self.target(Self.retained[0].key)))
        // A checkpoint this update no longer carries hands nothing back.
        let dropped = Self.boundCheckpoint(3)
        let shorter = Self.make(
            phase: .during, pregame: Self.pregame, comparisonLabel: Self.recordedLabel, comparison: Self.recorded(Self.retained[3]),
            checkpoints: Array(Self.boundCheckpoints.prefix(3)), selectedCheckpointID: Self.retained[3].key, notes: []
        )
        XCTAssertNil(shorter.actionTarget(dropped))
        XCTAssertNil(shorter.checkpointAction(dropped, canSelect: true))
        XCTAssertEqual(shorter.selection, .unavailable(Self.retained[3].key))
        XCTAssertNil(shorter.detailsAction(canOpenDetails: true))
        // A changed checkpoint under the same id is not the carried one.
        let changed = Self.checkpoint(
            id: Self.retained[0].key, ref: Self.original, label: "Constructed changed label",
            actual: .reported(Self.report(Self.retained[0])), chanceLabel: Self.chanceLabel, chance: Self.recorded(Self.retained[0])
        )
        XCTAssertNil(shorter.actionTarget(changed))
    }

    // MARK: Owner order, no cap

    func testFiveOrMoreConstructedCheckpointsAreAllKeptInOwnerOrder() {
        let ids = ["k6", "k1", "k4", "k2", "k5", "k3"]
        let checkpoints = ids.map { id in
            Self.checkpoint(
                id: id, ref: nil, label: "Constructed \(id)", actual: .unavailable(Self.reportUnavailable),
                chanceLabel: Self.chanceLabel,
                chance: .observed(CricketChaseFigure10868(text: "\(id.count)%", detail: "Constructed bar \(id)"))
            )
        }
        let input = Self.make(
            phase: .during, pregame: Self.pregame, comparisonLabel: Self.recordedLabel, comparison: .unavailable(Self.currentUnavailable),
            checkpoints: checkpoints, selectedCheckpointID: nil, notes: []
        )
        XCTAssertEqual(input.visibleCheckpoints.map(\.id), ids)
        XCTAssertEqual(input.visibleCheckpoints.count, 6)
        XCTAssertEqual(CricketSurvivalGeometry10868.rows(count: 6, columns: 2), [[0, 1], [2, 3], [4, 5]])
        XCTAssertEqual(CricketSurvivalGeometry10868.rows(count: 5, columns: 2), [[0, 1], [2, 3], [4]])
        XCTAssertEqual(CricketSurvivalGeometry10868.rows(count: 5, columns: 1), [[0], [1], [2], [3], [4]])
        XCTAssertEqual(CricketSurvivalGeometry10868.rows(count: 3, columns: 0), [[0], [1], [2]])
        XCTAssertEqual(CricketSurvivalGeometry10868.rows(count: 0, columns: 2), [])
        XCTAssertEqual(CricketSurvivalGeometry10868.rows(count: 9, columns: 2).flatMap { $0 }, Array(0..<9))
    }

    // MARK: Long words

    func testLongQualifiersAndProvenanceStayVerbatim() {
        let longBar = "Kalshi trade close · minute ending 2:45 AM Pacific Daylight Time, Tuesday, October 13, 2026 · bar boundary, not the exact trade or arrival"
        let longReport = "Lunch · last score report before lunch, published 2:49 AM Pacific Daylight Time, Tuesday, October 13, 2026 · publication time, not the exact ball time"
        let longLabel = "Constructed Day 5 · lunch interval · 73 overs · Extraordinarily-Long-Checkpoint-Qualifier"
        let checkpoint = Self.checkpoint(
            id: "long", ref: nil, label: longLabel,
            actual: .reported(CricketSurvivalReport10868(
                wickets: Self.ownerWickets(lost: 6, of: 10),
                wicketsText: "4 wickets left · reported, not confirmed",
                reportDetail: longReport
            )),
            chanceLabel: "Recorded draw / tie (original market, separately timed)",
            chance: .observed(CricketChaseFigure10868(text: "17%", detail: longBar))
        )
        let input = Self.make(
            phase: .during, pregame: Self.pregame, comparisonLabel: "Recorded draw / tie chance · last admitted minute bar",
            comparison: .withheld(Self.held), checkpoints: [checkpoint], selectedCheckpointID: nil, notes: Self.notes
        )
        XCTAssertEqual(
            input.accessibilityCheckpoint(checkpoint),
            "\(longLabel). 4 wickets left · reported, not confirmed. \(longReport). "
                + "Recorded draw / tie (original market, separately timed): 17%, \(longBar)"
        )
        XCTAssertEqual(
            input.accessibilityChances,
            "Pregame: 9%, Kalshi trade close · hour 4–5 PM PDT, Oct 8. Recorded draw / tie chance · last admitted minute bar: Held — not current"
        )
        XCTAssertTrue(CricketChaseGeometry10868.words(longLabel).contains("Extraordinarily-Long-Checkpoint-Qualifier"))
    }

    // MARK: No chase or derived fields

    func testSurvivalInputsCarryNoChaseTargetRunsOrDerivedFields() {
        let input = Self.live
        let inputLabels = Mirror(reflecting: input).children.compactMap { $0.label }
        XCTAssertEqual(inputLabels, [
            "phase", "subject", "title", "pregameLabel", "pregame", "comparisonLabel", "comparison",
            "checkpointsLabel", "checkpoints", "selectedCheckpointID", "notes",
        ])
        let checkpointLabels = Mirror(reflecting: input.checkpoints[0]).children.compactMap { $0.label }
        XCTAssertEqual(checkpointLabels, ["id", "ref", "label", "actual", "chanceLabel", "chance"])
        let reportLabels = Mirror(reflecting: Self.report(Self.retained[0])).children.compactMap { $0.label }
        XCTAssertEqual(reportLabels, ["wickets", "wicketsText", "reportDetail"])
        // The action target is the two owner-supplied fields and nothing derived.
        let targetLabels = Mirror(reflecting: Self.target("c1")).children.compactMap { $0.label }
        XCTAssertEqual(targetLabels, ["checkpointID", "original"])
        let all = Set(inputLabels + checkpointLabels + reportLabels + targetLabels)
        for forbidden in [
            "target", "runs", "runsNeeded", "wicketsLeft", "overs", "probability", "price", "margin", "projection",
            "ticker", "result", "settlement", "latest", "current", "reportedAt", "barEnd",
        ] {
            XCTAssertFalse(all.contains(forbidden), forbidden)
        }
        // The chase input's field set is unchanged by the survival card.
        let chase = CricketChaseInput10868(
            phase: .during, subject: "Constructed", eyebrow: "Constructed", headline: nil,
            pregameLabel: Self.pregameLabel, pregame: Self.pregame, comparisonLabel: Self.recordedLabel,
            comparison: .unavailable(Self.currentUnavailable), resultLabel: "Final",
            contractResult: .unavailable("Constructed"), matchResult: .unavailable("Constructed"),
            actual: .unavailable(Self.reportUnavailable), detailsRef: nil, notes: []
        )
        XCTAssertEqual(Mirror(reflecting: chase).children.compactMap { $0.label }, [
            "phase", "subject", "eyebrow", "headline", "pregameLabel", "pregame", "comparisonLabel",
            "comparison", "resultLabel", "contractResult", "matchResult", "actual", "detailsRef", "notes",
        ])
    }

    // MARK: Identifiers

    func testAccessibilityIdentifiersAreStableAndDistinct() {
        let ids = [
            CricketSurvivalAccessibilityID10868.header,
            CricketSurvivalAccessibilityID10868.chances,
            CricketSurvivalAccessibilityID10868.checkpoints,
            CricketSurvivalAccessibilityID10868.selectionNotice,
            CricketSurvivalAccessibilityID10868.notes,
            CricketSurvivalAccessibilityID10868.details,
            CricketSurvivalAccessibilityID10868.checkpoint("c1"),
        ]
        XCTAssertEqual(ids, [
            "cricketSurvival10868.header",
            "cricketSurvival10868.chances",
            "cricketSurvival10868.checkpoints",
            "cricketSurvival10868.selectionNotice",
            "cricketSurvival10868.notes",
            "cricketSurvival10868.details",
            "cricketSurvival10868.checkpoint.c1",
        ])
        XCTAssertEqual(Set(ids).count, ids.count)
        XCTAssertFalse(ids.contains(CricketChaseAccessibilityID10868.chances))
        let input = Self.live
        XCTAssertEqual(
            input.visibleCheckpoints.indices.compactMap { input.accessibilityID(at: $0) },
            Self.retained.map { "cricketSurvival10868.checkpoint.\($0.key)" }
        )
    }

    // MARK: Measured layout (CONSTRUCTED widths)

    /// A tile that wraps down to `minimum` (its widest word, whole figure or
    /// ten wicket marks) and is `ideal` wide unconstrained.
    private static func measure(ideal: CGFloat, minimum: CGFloat) -> (Int, CGFloat?) -> CGFloat {
        { _, proposal in
            guard let proposal else { return ideal }
            return max(minimum, min(ideal, proposal))
        }
    }

    /// Card content widths for 320, 375 and 393 pt screens with 16 pt card
    /// padding each side, and a wide reader.
    private static let contentWidths: [CGFloat] = [288, 343, 361, 700]

    func testTilesSitTwoAcrossWhenEveryTileKeepsItsWholeWidth() {
        for width in Self.contentWidths {
            XCTAssertEqual(CricketSurvivalGeometry10868.columns(
                available: width, spacing: 12, count: 4, forceSingle: false,
                measure: Self.measure(ideal: 180, minimum: 120)
            ), 2, "\(width)")
        }
        XCTAssertEqual(CricketSurvivalGeometry10868.columns(
            available: nil, spacing: 12, count: 4, forceSingle: false,
            measure: Self.measure(ideal: 180, minimum: 120)
        ), 2)
    }

    func testTilesStackForAnOverWideTileOneTileOrAccessibilitySize() {
        // Column at 288 is 138: a 150 pt minimum tile cannot fit.
        XCTAssertEqual(CricketSurvivalGeometry10868.columns(
            available: 288, spacing: 12, count: 4, forceSingle: false,
            measure: Self.measure(ideal: 200, minimum: 150)
        ), 1)
        // The same tiles fit two across in a wide reader.
        XCTAssertEqual(CricketSurvivalGeometry10868.columns(
            available: 700, spacing: 12, count: 4, forceSingle: false,
            measure: Self.measure(ideal: 200, minimum: 150)
        ), 2)
        // One over-wide tile among narrow ones stacks them all.
        XCTAssertEqual(CricketSurvivalGeometry10868.columns(
            available: 343, spacing: 12, count: 5, forceSingle: false,
            measure: { index, proposal in index == 4 ? 300 : (proposal ?? 100) }
        ), 1)
        XCTAssertEqual(CricketSurvivalGeometry10868.columns(
            available: 700, spacing: 12, count: 4, forceSingle: true,
            measure: Self.measure(ideal: 60, minimum: 60)
        ), 1)
        XCTAssertEqual(CricketSurvivalGeometry10868.columns(
            available: 700, spacing: 12, count: 1, forceSingle: false,
            measure: Self.measure(ideal: 60, minimum: 60)
        ), 1)
        XCTAssertEqual(CricketSurvivalGeometry10868.columns(
            available: 700, spacing: 12, count: 0, forceSingle: false,
            measure: Self.measure(ideal: 60, minimum: 60)
        ), 1)
        XCTAssertEqual(CricketSurvivalGeometry10868.columns(
            available: .infinity, spacing: 12, count: 3, forceSingle: false,
            measure: { _, _ in .infinity }
        ), 2)
    }
}

/// #10868 (cricket-t20) — the chase card's optional limited-over context: the
/// phase's task pair, the legal-ball budget and the achieved and required
/// scoring rates on one shared ceiling, gated by the chase input's phase.
///
/// The view is SwiftUI and is not rasterised here. What is asserted is the
/// rules it defers to: before suppresses every supplied task, budget and rate;
/// play never shows the final pair; the final never shows a live task or the
/// required rate; a nil context leaves the unlimited-innings card unchanged;
/// owner counts and words shown verbatim with no parsed overs; zero versus
/// unknown versus malformed ball and rate geometry; one shared rate ceiling;
/// independent failures; the exact Details reference; measured pair
/// arithmetic and the spoken text. Nothing here claims a rendered fit, a
/// native runtime, live app delivery, route or phase completion, or a
/// production binding.
///
/// ARCHIVED raw values come from India–West Indies, second T20I, Ranchi,
/// October 9, 2026 (route cricket-t20, event KXT20MATCH-26OCT090930WIIND), as
/// retained in `shipping-adoption-20261027/T20-CHASE-REUSE-RETAINED-CASES.json`
/// (sha256 c7ef73fb…03cb). Two independently traded winner originals:
/// Kalshi KXT20MATCH-26OCT090930WIIND-WI (side Yes, "West Indies wins",
/// result yes) and …-IND (result no); settlement 2026-10-09T17:45:23.67777Z,
/// market close 17:40:24Z — neither is the match-finish or report clock. A
/// tie/no-result $0.50 payout is a settlement amount, not a third chance. No
/// internal app event/market/outcome id is retained.
///   India 249/5 (20.0 overs, report 15:24:19Z) ⇒ target 250, a threshold.
///   Pregame minute bar ending 12:57Z (report 12:57:17Z): WI 0.23, IND 0.78.
///   West Indies chase, published score reports (publication, not ball time):
///     13.0  170/3  report 16:46:44Z  bar end 16:46Z  WI 0.57  IND 0.44
///     15.0  187/4  report 16:57:47Z  bar end 16:57Z  WI 0.34  IND 0.67
///     17.0  223/4  report 17:06:58Z  bar end 17:06Z  WI 0.89  IND 0.12
///     18.0  240/4  report 17:12:01Z  bar end 17:12Z  WI 0.99  IND 0.01
///     final 252/4 at 18.3, report 17:19:41Z, bar end 17:19Z, WI 0.99, IND 0.01
///
/// CONSTRUCTED owner-resolved inputs (this leaf resolves none of them): the
/// packet's legal-ball and rate arithmetic (78/90/102/108/111 balls used,
/// 42/30/18/12 left and 9 to spare, 80/63/27/10 runs needed, the rate
/// fractions and example words, the 16 runs-per-over display ceiling), every
/// display string (figures, local-calendar provenance, labels, captions,
/// connectives, result words), the wicket positions built from the ARCHIVED
/// counts, every action reference (none is retained), and every phase-leak,
/// missing, withheld, zero, malformed, unknown-part, long-text and
/// measured-width case.
final class CricketChaseLimitedOvers10868Tests: XCTestCase {

    // MARK: ARCHIVED source

    private static let westIndiesTicker = "KXT20MATCH-26OCT090930WIIND-WI"
    private static let indiaTicker = "KXT20MATCH-26OCT090930WIIND-IND"
    private static let side = "Yes"
    private static let indiaFirstInnings = (runs: 249, wickets: 5, overs: "20.0")
    private static let targetRuns = 250
    private static let pregameWestIndies = 0.23
    private static let pregameIndia = 0.78
    private static let pregameBarEnd = "2026-10-09T12:57:00+00:00"
    private static let settlement = "2026-10-09T17:45:23.67777Z"
    private static let marketClose = "2026-10-09T17:40:24Z"

    private struct RetainedCheckpoint {
        /// ARCHIVED.
        let checkpoint: String
        let reportedAt: String
        let runs: Int
        let wickets: Int
        let overs: String
        let barEnd: String
        let westIndies: Double
        let india: Double
        /// CONSTRUCTED owner display arithmetic, fixture only — whole overs
        /// and balls kept apart, never a decimal.
        let completedOvers: Int
        let extraBalls: Int
        let ballsUsed: Int
        let ballsLeft: Int
        let runsNeeded: Int
        let wicketsLeft: Int
        let runRate: Double
        let runRateWords: String
        let requiredRate: Double?
        let requiredRateWords: String?
        /// CONSTRUCTED owner text.
        let taskLabel: String
        let recordedText: String
        let recordedDetail: String
        let reportDetail: String
        let oversText: String
    }

    private static let checkpoints: [RetainedCheckpoint] = [
        RetainedCheckpoint(
            checkpoint: "13.0", reportedAt: "2026-10-09T16:46:44+00:00", runs: 170, wickets: 3, overs: "13.0",
            barEnd: "2026-10-09T16:46:00+00:00", westIndies: 0.57, india: 0.44,
            completedOvers: 13, extraBalls: 0, ballsUsed: 78, ballsLeft: 42, runsNeeded: 80, wicketsLeft: 7,
            runRate: 170.0 / 13, runRateWords: "13.08", requiredRate: 80.0 / 7, requiredRateWords: "11.43",
            taskLabel: "Chase · 13 overs", recordedText: "57%",
            recordedDetail: "Kalshi trade close · minute 9:45–9:46 AM PDT, Oct 9",
            reportDetail: "Score report published 9:46 AM PDT, Oct 9 · not the exact ball time",
            oversText: "13 overs played"
        ),
        RetainedCheckpoint(
            checkpoint: "15.0", reportedAt: "2026-10-09T16:57:47+00:00", runs: 187, wickets: 4, overs: "15.0",
            barEnd: "2026-10-09T16:57:00+00:00", westIndies: 0.34, india: 0.67,
            completedOvers: 15, extraBalls: 0, ballsUsed: 90, ballsLeft: 30, runsNeeded: 63, wicketsLeft: 6,
            runRate: 187.0 / 15, runRateWords: "12.47", requiredRate: 63.0 / 5, requiredRateWords: "12.60",
            taskLabel: "Chase · 15 overs", recordedText: "34%",
            recordedDetail: "Kalshi trade close · minute 9:56–9:57 AM PDT, Oct 9",
            reportDetail: "Score report published 9:57 AM PDT, Oct 9 · not the exact ball time",
            oversText: "15 overs played"
        ),
        RetainedCheckpoint(
            checkpoint: "17.0", reportedAt: "2026-10-09T17:06:58+00:00", runs: 223, wickets: 4, overs: "17.0",
            barEnd: "2026-10-09T17:06:00+00:00", westIndies: 0.89, india: 0.12,
            completedOvers: 17, extraBalls: 0, ballsUsed: 102, ballsLeft: 18, runsNeeded: 27, wicketsLeft: 6,
            runRate: 223.0 / 17, runRateWords: "13.12", requiredRate: 9, requiredRateWords: "9.00",
            taskLabel: "Chase · 17 overs", recordedText: "89%",
            recordedDetail: "Kalshi trade close · minute 10:05–10:06 AM PDT, Oct 9",
            reportDetail: "Score report published 10:06 AM PDT, Oct 9 · not the exact ball time",
            oversText: "17 overs played"
        ),
        RetainedCheckpoint(
            checkpoint: "18.0", reportedAt: "2026-10-09T17:12:01+00:00", runs: 240, wickets: 4, overs: "18.0",
            barEnd: "2026-10-09T17:12:00+00:00", westIndies: 0.99, india: 0.01,
            completedOvers: 18, extraBalls: 0, ballsUsed: 108, ballsLeft: 12, runsNeeded: 10, wicketsLeft: 6,
            runRate: 40.0 / 3, runRateWords: "13.33", requiredRate: 5, requiredRateWords: "5.00",
            taskLabel: "Chase · 18 overs", recordedText: "99%",
            recordedDetail: "Kalshi trade close · minute 10:11–10:12 AM PDT, Oct 9",
            reportDetail: "Score report published 10:12 AM PDT, Oct 9 · not the exact ball time",
            oversText: "18 overs played"
        ),
    ]

    private static let finalCheckpoint = RetainedCheckpoint(
        checkpoint: "final", reportedAt: "2026-10-09T17:19:41+00:00", runs: 252, wickets: 4, overs: "18.3",
        barEnd: "2026-10-09T17:19:00+00:00", westIndies: 0.99, india: 0.01,
        completedOvers: 18, extraBalls: 3, ballsUsed: 111, ballsLeft: 9, runsNeeded: 0, wicketsLeft: 6,
        runRate: 504.0 / 37, runRateWords: "13.62", requiredRate: nil, requiredRateWords: nil,
        taskLabel: "The chase, completed", recordedText: "99%",
        recordedDetail: "Kalshi trade close · minute 10:18–10:19 AM PDT, Oct 9",
        reportDetail: "Final score report published 10:19 AM PDT, Oct 9 · not the exact ball time",
        oversText: "18.3 overs played"
    )

    // MARK: CONSTRUCTED owner words

    private static let subject = "West Indies wins"
    private static let pregameLabel = "Pregame"
    private static let recordedLabel = "Recorded win chance"
    private static let resultLabel = "Final"
    private static let pregameText = "23%"
    private static let pregameDetail = "Kalshi trade close · minute 5:56–5:57 AM PDT, Oct 9"
    private static let beforeEyebrow = "West Indies · pregame"
    private static let duringEyebrow = "West Indies · chasing 250"
    private static let finalEyebrow = "West Indies · the chase, final"
    private static let headline = "The chase is on"
    private static let notYetKnown = "Not known until the match is over"
    private static let currentUnavailable = "Current probability unavailable"
    private static let held = "Held — not current"
    private static let scoreUnavailable = "Score report unavailable"
    private static let notes = ["Reconstructed from published score reports and separately recorded trades — not a live feed."]
    private static let finalMatchText = "West Indies won by 6 wickets"
    private static let finalMatchDetail = "Final score report published 10:19 AM PDT, Oct 9 · not the exact finish time"
    private static let gradedText = "Won"
    private static let gradedDetail = "Kalshi settled Yes · 10:45 AM PDT, Oct 9"
    private static let ballsLabel = "Legal balls used"
    private static let ballsNotDrawn = "Ball progress not drawn"
    private static let achievedLabel = "Runs per over so far"
    private static let requiredLabel = "Needed from here, runs per over"
    private static let rateNotDrawn = "Rate bar not drawn"
    private static let rateCeiling = 16.0
    private static let scaleText = "Both bars share one scale: 0 to 16 runs per over"
    private static let ballLimit = 120

    private static let ref = CricketChaseRef10868(event: "owner-event-t20", market: "owner-market-wi", outcome: "owner-outcome-wi")

    private static var pregame: CricketChaseReading10868 {
        .observed(CricketChaseFigure10868(text: pregameText, detail: pregameDetail))
    }

    private static var graded: CricketChaseContractResult10868 {
        .graded(CricketChaseFigure10868(text: gradedText, detail: gradedDetail))
    }

    private static var finalMatch: CricketChaseMatchResult10868 {
        .reported(CricketChaseFigure10868(text: finalMatchText, detail: finalMatchDetail))
    }

    private static func recorded(_ checkpoint: RetainedCheckpoint) -> CricketChaseReading10868 {
        .observed(CricketChaseFigure10868(text: checkpoint.recordedText, detail: checkpoint.recordedDetail))
    }

    /// CONSTRUCTED owner resolution of an ARCHIVED wicket count.
    private static func ownerWickets(lost: Int, of total: Int) -> [CricketChaseWicket10868] {
        Array(repeating: .lost, count: lost) + Array(repeating: .remaining, count: total - lost)
    }

    private static func state(_ checkpoint: RetainedCheckpoint) -> CricketChaseState10868 {
        CricketChaseState10868(
            battingSubject: "West Indies",
            context: nil,
            runs: .reported(text: "\(checkpoint.runs)", value: Double(checkpoint.runs)),
            runsCaption: "runs scored",
            target: .reported(text: "\(targetRuns)", value: Double(targetRuns)),
            targetCaption: "runs",
            wickets: ownerWickets(lost: checkpoint.wickets, of: 10),
            wicketsText: "\(checkpoint.wicketsLeft) wickets left",
            oversText: checkpoint.oversText,
            reportDetail: checkpoint.reportDetail
        )
    }

    private static func liveTask(_ checkpoint: RetainedCheckpoint) -> CricketChaseTask10868 {
        CricketChaseTask10868(
            label: checkpoint.taskLabel,
            reading: .reported(
                lead: .reported(text: "\(checkpoint.runsNeeded)", caption: "runs needed"),
                connective: "from",
                trail: .reported(text: "\(checkpoint.ballsLeft)", caption: "balls left"),
                detail: nil
            )
        )
    }

    private static var finishPair: CricketChaseTask10868 {
        CricketChaseTask10868(
            label: finalCheckpoint.taskLabel,
            reading: .reported(
                lead: .reported(text: "\(finalCheckpoint.runs)", caption: "runs scored"),
                connective: "with",
                trail: .reported(text: "\(finalCheckpoint.ballsLeft)", caption: "balls to spare"),
                detail: nil
            )
        )
    }

    private static func balls(_ checkpoint: RetainedCheckpoint) -> CricketChaseBalls10868 {
        balls(text: "\(checkpoint.ballsUsed) of \(ballLimit)", used: Double(checkpoint.ballsUsed), limit: Double(ballLimit))
    }

    private static func balls(text: String, used: Double, limit: Double, detail: String? = nil) -> CricketChaseBalls10868 {
        CricketChaseBalls10868(
            label: ballsLabel,
            reading: .reported(text: text, used: used, limit: limit, detail: detail),
            notDrawn: ballsNotDrawn
        )
    }

    private static func achieved(_ checkpoint: RetainedCheckpoint) -> CricketChaseRateRow10868 {
        CricketChaseRateRow10868(
            label: achievedLabel,
            reading: .reported(text: checkpoint.runRateWords, value: checkpoint.runRate, detail: nil)
        )
    }

    private static func requiredRow(_ checkpoint: RetainedCheckpoint) -> CricketChaseRateRow10868? {
        guard let value = checkpoint.requiredRate, let words = checkpoint.requiredRateWords else { return nil }
        return CricketChaseRateRow10868(label: requiredLabel, reading: .reported(text: words, value: value, detail: nil))
    }

    private static func rates(
        ceiling: Double = rateCeiling,
        achieved: CricketChaseRateRow10868?,
        required: CricketChaseRateRow10868?
    ) -> CricketChaseRates10868 {
        CricketChaseRates10868(
            ceiling: ceiling, scaleText: scaleText, achieved: achieved, required: required, notDrawn: rateNotDrawn
        )
    }

    /// A retained checkpoint's context: no final pair.
    private static func context(_ checkpoint: RetainedCheckpoint) -> CricketChaseLimitedOvers10868 {
        CricketChaseLimitedOvers10868(
            task: liveTask(checkpoint),
            finish: nil,
            balls: balls(checkpoint),
            rates: rates(achieved: achieved(checkpoint), required: requiredRow(checkpoint))
        )
    }

    /// The retained final's context: no live task, no required rate.
    private static var finalContext: CricketChaseLimitedOvers10868 {
        CricketChaseLimitedOvers10868(
            task: nil,
            finish: finishPair,
            balls: balls(finalCheckpoint),
            rates: rates(achieved: achieved(finalCheckpoint), required: nil)
        )
    }

    /// CONSTRUCTED: every phase's facts supplied at once, for leak checks.
    private static var everythingContext: CricketChaseLimitedOvers10868 {
        CricketChaseLimitedOvers10868(
            task: liveTask(checkpoints[1]),
            finish: finishPair,
            balls: balls(finalCheckpoint),
            rates: rates(achieved: achieved(finalCheckpoint), required: requiredRow(checkpoints[3]))
        )
    }

    /// Every field explicit: constructed cases never default through retained values.
    private static func make(
        phase: CricketChasePhase10868,
        eyebrow: String,
        headline: String?,
        pregame: CricketChaseReading10868,
        comparison: CricketChaseReading10868,
        contractResult: CricketChaseContractResult10868,
        matchResult: CricketChaseMatchResult10868,
        actual: CricketChaseActual10868,
        detailsRef: CricketChaseRef10868?,
        notes: [String]
    ) -> CricketChaseInput10868 {
        CricketChaseInput10868(
            phase: phase,
            subject: subject,
            eyebrow: eyebrow,
            headline: headline,
            pregameLabel: pregameLabel,
            pregame: pregame,
            comparisonLabel: recordedLabel,
            comparison: comparison,
            resultLabel: resultLabel,
            contractResult: contractResult,
            matchResult: matchResult,
            actual: actual,
            detailsRef: detailsRef,
            notes: notes
        )
    }

    private static func during(_ index: Int) -> CricketChaseInput10868 {
        let checkpoint = checkpoints[index]
        return make(
            phase: .during, eyebrow: duringEyebrow, headline: headline, pregame: pregame,
            comparison: recorded(checkpoint),
            contractResult: .unavailable(notYetKnown), matchResult: .unavailable(notYetKnown),
            actual: .reported(state(checkpoint)), detailsRef: nil, notes: notes
        )
    }

    /// The retained final. The supplied 99% reading is a settled price the
    /// card must not show as a chance.
    private static var finalInput: CricketChaseInput10868 {
        make(
            phase: .final, eyebrow: finalEyebrow, headline: nil, pregame: pregame,
            comparison: recorded(finalCheckpoint),
            contractResult: graded, matchResult: finalMatch,
            actual: .reported(state(finalCheckpoint)), detailsRef: nil, notes: notes
        )
    }

    private static func visible(_ input: CricketChaseInput10868, _ context: CricketChaseLimitedOvers10868?) -> CricketChaseLimitedOversVisible10868? {
        CricketChaseLimitedOversVisible10868(phase: input.phase, context: context)
    }

    /// Everything the card speaks, base helpers and limited-over helpers alike.
    private static func allSpoken(_ input: CricketChaseInput10868, _ context: CricketChaseLimitedOvers10868?) -> String {
        let limited = visible(input, context)
        return [
            input.accessibilityHeader,
            input.accessibilityChances,
            limited?.accessibilityTask,
            input.accessibilityRuns,
            limited?.accessibilityBalls,
            limited?.accessibilityRates,
            input.accessibilityWickets,
            input.accessibilityReport,
            input.accessibilityNotes,
        ]
        .compactMap { $0 }
        .joined(separator: " | ")
    }

    // MARK: Retained packet

    func testRetainedT20PacketValuesAreTheArchivedOnes() {
        XCTAssertEqual(Self.westIndiesTicker, "KXT20MATCH-26OCT090930WIIND-WI")
        XCTAssertEqual(Self.indiaTicker, "KXT20MATCH-26OCT090930WIIND-IND")
        XCTAssertEqual(Self.side, "Yes")
        XCTAssertEqual(Self.checkpoints.map(\.checkpoint), ["13.0", "15.0", "17.0", "18.0"])
        XCTAssertEqual(Self.checkpoints.map(\.runs), [170, 187, 223, 240])
        XCTAssertEqual(Self.checkpoints.map(\.wickets), [3, 4, 4, 4])
        XCTAssertEqual(Self.checkpoints.map(\.westIndies), [0.57, 0.34, 0.89, 0.99])
        XCTAssertEqual(Self.checkpoints.map(\.india), [0.44, 0.67, 0.12, 0.01])
        XCTAssertEqual(Self.checkpoints.map(\.barEnd), [
            "2026-10-09T16:46:00+00:00", "2026-10-09T16:57:00+00:00",
            "2026-10-09T17:06:00+00:00", "2026-10-09T17:12:00+00:00",
        ])
        XCTAssertEqual(Self.checkpoints.map(\.reportedAt), [
            "2026-10-09T16:46:44+00:00", "2026-10-09T16:57:47+00:00",
            "2026-10-09T17:06:58+00:00", "2026-10-09T17:12:01+00:00",
        ])
        XCTAssertEqual(Self.finalCheckpoint.runs, 252)
        XCTAssertEqual(Self.finalCheckpoint.wickets, 4)
        XCTAssertEqual(Self.finalCheckpoint.overs, "18.3")
        XCTAssertEqual(Self.finalCheckpoint.reportedAt, "2026-10-09T17:19:41+00:00")
        XCTAssertEqual(Self.pregameWestIndies, 0.23)
        XCTAssertEqual(Self.pregameIndia, 0.78)
        XCTAssertEqual(Self.pregameBarEnd, "2026-10-09T12:57:00+00:00")
        // Settlement and market close are later and are not report clocks.
        XCTAssertLessThan(Self.finalCheckpoint.reportedAt.prefix(19), Self.marketClose.prefix(19))
        XCTAssertLessThan(Self.marketClose.prefix(19), Self.settlement.prefix(19))
        // The target follows India's innings; it is a threshold, not a finish.
        XCTAssertEqual(Self.indiaFirstInnings.runs + 1, Self.targetRuns)
        XCTAssertGreaterThan(Self.finalCheckpoint.runs, Self.targetRuns)
        // The two originals are independently traded: never a complementary pair.
        XCTAssertNotEqual(Self.pregameWestIndies + Self.pregameIndia, 1, accuracy: 0.001)
        XCTAssertNotEqual(Self.checkpoints[1].westIndies + Self.checkpoints[1].india, 1, accuracy: 0.001)
        // The packet's CONSTRUCTED arithmetic is consistent with its fields;
        // it is checked here, from whole overs and balls, and never by the leaf.
        for checkpoint in Self.checkpoints + [Self.finalCheckpoint] {
            XCTAssertEqual(checkpoint.completedOvers * 6 + checkpoint.extraBalls, checkpoint.ballsUsed, checkpoint.checkpoint)
            XCTAssertEqual(Self.ballLimit - checkpoint.ballsUsed, checkpoint.ballsLeft, checkpoint.checkpoint)
            XCTAssertEqual(10 - checkpoint.wickets, checkpoint.wicketsLeft, checkpoint.checkpoint)
        }
        for checkpoint in Self.checkpoints {
            XCTAssertEqual(Self.targetRuns - checkpoint.runs, checkpoint.runsNeeded, checkpoint.checkpoint)
        }
        XCTAssertEqual(Self.checkpoints.map(\.ballsUsed), [78, 90, 102, 108])
        XCTAssertEqual(Self.finalCheckpoint.ballsUsed, 111)
        XCTAssertEqual(Self.finalCheckpoint.ballsLeft, 9)
        XCTAssertNil(Self.finalCheckpoint.requiredRate)
    }

    // MARK: Four chase checkpoints

    func testFourCheckpointsShowTheOwnersTaskBallsAndRatesVerbatim() throws {
        for (index, checkpoint) in Self.checkpoints.enumerated() {
            let input = Self.during(index)
            let limited = try XCTUnwrap(Self.visible(input, Self.context(checkpoint)), checkpoint.checkpoint)
            XCTAssertEqual(limited.task, Self.liveTask(checkpoint), checkpoint.checkpoint)
            XCTAssertEqual(limited.balls, Self.balls(checkpoint), checkpoint.checkpoint)
            XCTAssertEqual(limited.rateRows, [Self.achieved(checkpoint), try XCTUnwrap(Self.requiredRow(checkpoint))])
            XCTAssertEqual(try XCTUnwrap(limited.ballFraction), Double(checkpoint.ballsUsed) / 120, accuracy: 1e-12)
            XCTAssertFalse(limited.showsBallsNotDrawn)
            XCTAssertEqual(try XCTUnwrap(limited.rateFraction(Self.achieved(checkpoint))), checkpoint.runRate / 16, accuracy: 1e-12)
            XCTAssertEqual(
                try XCTUnwrap(limited.rateFraction(try XCTUnwrap(Self.requiredRow(checkpoint)))),
                try XCTUnwrap(checkpoint.requiredRate) / 16,
                accuracy: 1e-12
            )
            XCTAssertEqual(
                limited.accessibilityTask,
                "\(checkpoint.taskLabel): \(checkpoint.runsNeeded) runs needed from \(checkpoint.ballsLeft) balls left"
            )
            XCTAssertEqual(limited.accessibilityBalls, "Legal balls used: \(checkpoint.ballsUsed) of 120")
            // The existing run rail still places runs on the target domain.
            let rail = try XCTUnwrap(input.railGeometry)
            XCTAssertEqual(rail.fill, Double(checkpoint.runs) / 250, accuracy: 1e-12)
            XCTAssertEqual(rail.target, 1)
        }
    }

    func testCheckpointChancesStayIndependentUnnormalizedAndTwoWay() {
        for (index, checkpoint) in Self.checkpoints.enumerated() {
            let input = Self.during(index)
            XCTAssertEqual(
                input.accessibilityChances,
                "Pregame: 23%, \(Self.pregameDetail). Recorded win chance: \(checkpoint.recordedText), \(checkpoint.recordedDetail)"
            )
            let spoken = Self.allSpoken(input, Self.context(checkpoint))
            // India's independent reading is never shown as this card's
            // complement, and a $0.50 tie payout is never a third chance.
            for leak in ["78%", "77%", "50%", "\(Int((checkpoint.india * 100).rounded()))%"] where leak != checkpoint.recordedText {
                XCTAssertFalse(spoken.contains(leak), "\(checkpoint.checkpoint) \(leak)")
            }
        }
        // 15 overs: 34% for West Indies while India traded at 67% — 101%.
        XCTAssertTrue(Self.during(1).accessibilityChances.hasSuffix("34%, \(Self.checkpoints[1].recordedDetail)"))
    }

    func testScoreReportAndBarClocksStaySeparateAtEveryCheckpoint() {
        for (index, checkpoint) in Self.checkpoints.enumerated() {
            let input = Self.during(index)
            let limited = Self.visible(input, Self.context(checkpoint))
            XCTAssertEqual(input.accessibilityReport, checkpoint.reportDetail)
            XCTAssertFalse(input.accessibilityChances.contains(checkpoint.reportDetail))
            XCTAssertFalse(limited?.accessibilityTask?.contains(checkpoint.recordedDetail) ?? true)
            XCTAssertFalse(limited?.accessibilityRates?.contains(checkpoint.recordedDetail) ?? true)
        }
    }

    func testSpokenFifteenOverCheckpointIsExact() throws {
        let input = Self.during(1)
        let limited = try XCTUnwrap(Self.visible(input, Self.context(Self.checkpoints[1])))
        XCTAssertEqual(input.accessibilityHeader, "West Indies · chasing 250. The chase is on")
        XCTAssertEqual(limited.accessibilityTask, "Chase · 15 overs: 63 runs needed from 30 balls left")
        XCTAssertEqual(
            input.accessibilityRuns,
            "West Indies: 187 runs scored. Target to win: 250 runs. Target to win is not a projected finish"
        )
        XCTAssertEqual(limited.accessibilityBalls, "Legal balls used: 90 of 120")
        XCTAssertEqual(
            limited.accessibilityRates,
            "Runs per over so far: 12.47. Needed from here, runs per over: 12.60. "
                + "Both bars share one scale: 0 to 16 runs per over. "
                + "Scoring rates are measured in runs per over. They are not projections or chances"
        )
        XCTAssertEqual(input.accessibilityWickets, "6 wickets left. 15 overs played")
        XCTAssertEqual(input.accessibilityReport, "Score report published 9:57 AM PDT, Oct 9 · not the exact ball time")
    }

    // MARK: Final

    func testFinalKeepsPregameBesideTheReportedFinishAndOriginalResult() throws {
        let input = Self.finalInput
        let limited = try XCTUnwrap(Self.visible(input, Self.finalContext))
        XCTAssertEqual(input.visibleHeading, "West Indies won by 6 wickets")
        XCTAssertEqual(input.visibleHeadingDetail, Self.finalMatchDetail)
        XCTAssertNil(input.visibleComparison)
        XCTAssertEqual(input.visibleContractResult, Self.graded)
        XCTAssertEqual(input.accessibilityChances, "Pregame: 23%, \(Self.pregameDetail). Final: Won, \(Self.gradedDetail)")
        XCTAssertEqual(limited.task, Self.finishPair)
        XCTAssertEqual(limited.accessibilityTask, "The chase, completed: 252 runs scored with 9 balls to spare")
        XCTAssertEqual(limited.accessibilityBalls, "Legal balls used: 111 of 120")
        XCTAssertEqual(try XCTUnwrap(limited.ballFraction), 111.0 / 120, accuracy: 1e-12)
        XCTAssertEqual(limited.rateRows, [Self.achieved(Self.finalCheckpoint)])
        XCTAssertEqual(try XCTUnwrap(limited.rateFraction(Self.achieved(Self.finalCheckpoint))), (504.0 / 37) / 16, accuracy: 1e-12)
        let spoken = Self.allSpoken(input, Self.finalContext)
        // The settled 99% is not a chance, no synthetic 0/100 point appears,
        // and the later settlement and market close stay out of the actuals.
        for leak in ["99%", "100%", "0%", "1%", "needed", "balls left", "Needed from here", "10:40"] {
            XCTAssertFalse(spoken.contains(leak), leak)
        }
        XCTAssertFalse(input.accessibilityReport!.contains("10:45"))
        XCTAssertTrue(input.accessibilityChances.contains("10:45 AM"))
    }

    func testFinalNeverShowsALiveTaskOrRequiredRateEvenWhenSupplied() throws {
        let input = Self.finalInput
        let limited = try XCTUnwrap(Self.visible(input, Self.everythingContext))
        XCTAssertEqual(limited.task, Self.finishPair)
        XCTAssertNil(limited.rates?.required)
        XCTAssertEqual(limited.rateRows.map(\.label), [Self.achievedLabel])
        let spoken = Self.allSpoken(input, Self.everythingContext)
        for leak in ["63 runs needed", "30 balls left", Self.requiredLabel, "5.00", "Chase · 15 overs"] {
            XCTAssertFalse(spoken.contains(leak), leak)
        }
        // A final with no completed pair says nothing about a remaining task.
        let noFinish = CricketChaseLimitedOvers10868(
            task: Self.liveTask(Self.checkpoints[3]), finish: nil,
            balls: Self.balls(Self.finalCheckpoint), rates: Self.rates(achieved: nil, required: Self.requiredRow(Self.checkpoints[3]))
        )
        let bare = try XCTUnwrap(Self.visible(input, noFinish))
        XCTAssertNil(bare.task)
        XCTAssertNil(bare.accessibilityTask)
        // A required row alone leaves no rate section at the final.
        XCTAssertNil(bare.rates)
        XCTAssertNil(bare.accessibilityRates)
        XCTAssertEqual(bare.rateRows, [])
        XCTAssertFalse(Self.allSpoken(input, noFinish).contains("needed"))
    }

    func testDuringNeverLeaksTheFinalPairOrResult() throws {
        let input = Self.during(1)
        let limited = try XCTUnwrap(Self.visible(input, Self.everythingContext))
        XCTAssertEqual(limited.task, Self.liveTask(Self.checkpoints[1]))
        let spoken = Self.allSpoken(input, Self.everythingContext)
        for leak in ["252", "balls to spare", "The chase, completed", "won", "Won", Self.finalMatchText] {
            XCTAssertFalse(spoken.contains(leak), leak)
        }
        // The supplied required rate shows in play.
        XCTAssertNotNil(limited.rates?.required)
    }

    func testActualBeyondTargetStaysInsideTheExistingRunRail() throws {
        let rail = try XCTUnwrap(Self.finalInput.railGeometry)
        XCTAssertEqual(rail.fill, 1)
        XCTAssertEqual(rail.target, 250.0 / 252, accuracy: 1e-12)
        XCTAssertGreaterThanOrEqual(rail.target, 0)
        XCTAssertLessThanOrEqual(rail.target, 1)
        XCTAssertFalse(Self.finalInput.showsRailNotDrawn)
        XCTAssertEqual(
            Self.finalInput.accessibilityRuns,
            "West Indies: 252 runs scored. Target to win: 250 runs. Target to win is not a projected finish"
        )
        XCTAssertFalse(Self.allSpoken(Self.finalInput, Self.finalContext).contains("projected 250"))
    }

    // MARK: Before

    func testBeforeSuppressesEverySuppliedTaskBudgetAndRate() {
        let input = Self.make(
            phase: .before, eyebrow: Self.beforeEyebrow, headline: Self.headline, pregame: Self.pregame,
            comparison: Self.recorded(Self.checkpoints[1]),
            contractResult: Self.graded, matchResult: Self.finalMatch,
            actual: .reported(Self.state(Self.finalCheckpoint)), detailsRef: nil, notes: Self.notes
        )
        XCTAssertNil(Self.visible(input, Self.everythingContext))
        XCTAssertNil(Self.visible(input, Self.context(Self.checkpoints[0])))
        XCTAssertNil(Self.visible(input, Self.finalContext))
        XCTAssertEqual(input.accessibilityChances, "Pregame: 23%, \(Self.pregameDetail)")
        let spoken = Self.allSpoken(input, Self.everythingContext)
        for leak in [
            "250", "252", "63", "30", "111", "120", "balls", "runs per over", "12.47", "13.62", "5.00",
            "Target", "wickets", "overs", "spare", "needed", "won", "34%",
        ] {
            XCTAssertFalse(spoken.contains(leak), leak)
        }
    }

    func testNilContextKeepsTheUnlimitedCardInEveryPhase() {
        for phase in CricketChasePhase10868.allCases {
            XCTAssertNil(CricketChaseLimitedOversVisible10868(phase: phase, context: nil), "\(phase)")
        }
        // The base helpers are the same with or without the context.
        let input = Self.during(1)
        XCTAssertNil(Self.visible(input, nil))
        XCTAssertEqual(
            Self.allSpoken(input, nil),
            [input.accessibilityHeader, input.accessibilityChances, input.accessibilityRuns,
             input.accessibilityWickets, input.accessibilityReport, input.accessibilityNotes]
                .compactMap { $0 }.joined(separator: " | ")
        )
        // The chase input's tested field set carries no limited-over field.
        XCTAssertEqual(Mirror(reflecting: input).children.compactMap { $0.label }, [
            "phase", "subject", "eyebrow", "headline", "pregameLabel", "pregame", "comparisonLabel",
            "comparison", "resultLabel", "contractResult", "matchResult", "actual", "detailsRef", "notes",
        ])
    }

    func testAnEmptyContextIsTheLimitedLayoutWithNothingInvented() throws {
        let empty = CricketChaseLimitedOvers10868(task: nil, finish: nil, balls: nil, rates: nil)
        let limited = try XCTUnwrap(Self.visible(Self.during(1), empty))
        XCTAssertNil(limited.task)
        XCTAssertNil(limited.balls)
        XCTAssertNil(limited.rates)
        XCTAssertNil(limited.ballFraction)
        XCTAssertFalse(limited.showsBallsNotDrawn)
        XCTAssertNil(limited.accessibilityTask)
        XCTAssertNil(limited.accessibilityBalls)
        XCTAssertNil(limited.accessibilityRates)
        // Nothing is derived from the score: no 63, no 30, no 120.
        let spoken = Self.allSpoken(Self.during(1), empty)
        for leak in ["63", "30 balls", "120", "runs per over"] {
            XCTAssertFalse(spoken.contains(leak), leak)
        }
    }

    // MARK: Owner counts, never parsed overs

    func testBallCountsAreTheOwnersNeverParsedOvers() throws {
        // 15.0 overs is 90 legal balls and 18.3 is 111 because the owner says so.
        let fifteen = try XCTUnwrap(Self.visible(Self.during(1), Self.context(Self.checkpoints[1])))
        XCTAssertEqual(fifteen.ballFraction, 0.75)
        let finalVisible = try XCTUnwrap(Self.visible(Self.finalInput, Self.finalContext))
        XCTAssertEqual(try XCTUnwrap(finalVisible.ballFraction), 111.0 / 120, accuracy: 1e-12)
        // A decimal-overs value passed as a count is not a count: no rail.
        let misread = CricketChaseLimitedOvers10868(
            task: nil, finish: Self.finishPair,
            balls: Self.balls(text: "18.3 of 120", used: 18.3, limit: 120), rates: nil
        )
        let misreadVisible = try XCTUnwrap(Self.visible(Self.finalInput, misread))
        XCTAssertNil(misreadVisible.ballFraction)
        XCTAssertTrue(misreadVisible.showsBallsNotDrawn)
        XCTAssertEqual(misreadVisible.accessibilityBalls, "Legal balls used: 18.3 of 120. Ball progress not drawn")
        // The overs string reaches the reader only as the owner's own words.
        XCTAssertEqual(Self.finalInput.accessibilityWickets, "6 wickets left. 18.3 overs played")
        // A different owner limit is the owner's: nothing assumes 120.
        XCTAssertEqual(CricketChaseLimitedOversGeometry10868.balls(used: 150, limit: 300), 0.5)
        XCTAssertEqual(CricketChaseLimitedOversGeometry10868.balls(used: 30, limit: 60), 0.5)
    }

    // MARK: Zero versus unknown

    func testRealZeroBallsAndRateAreValuesNotUnknown() throws {
        let zero = CricketChaseLimitedOvers10868(
            task: CricketChaseTask10868(
                label: "Chase · 0 overs",
                reading: .reported(
                    lead: .reported(text: "250", caption: "runs needed"), connective: "from",
                    trail: .reported(text: "120", caption: "balls left"), detail: nil
                )
            ),
            finish: nil,
            balls: Self.balls(text: "0 of 120", used: 0, limit: 120),
            rates: Self.rates(
                achieved: CricketChaseRateRow10868(label: Self.achievedLabel, reading: .reported(text: "0.00", value: 0, detail: nil)),
                required: CricketChaseRateRow10868(label: Self.requiredLabel, reading: .reported(text: "12.50", value: 12.5, detail: nil))
            )
        )
        let limited = try XCTUnwrap(Self.visible(Self.during(0), zero))
        XCTAssertEqual(limited.ballFraction, 0)
        XCTAssertFalse(limited.showsBallsNotDrawn)
        let achievedRow = try XCTUnwrap(limited.rates?.achieved)
        XCTAssertEqual(limited.rateFraction(achievedRow), 0)
        XCTAssertFalse(limited.showsRateNotDrawn(achievedRow))
        XCTAssertTrue(limited.accessibilityRates!.hasPrefix("Runs per over so far: 0.00. "))

        let unknown = CricketChaseLimitedOvers10868(
            task: nil, finish: nil,
            balls: CricketChaseBalls10868(label: Self.ballsLabel, reading: .unavailable("Legal balls not reported"), notDrawn: Self.ballsNotDrawn),
            rates: Self.rates(
                achieved: CricketChaseRateRow10868(label: Self.achievedLabel, reading: .unavailable("Rate unavailable")),
                required: CricketChaseRateRow10868(label: Self.requiredLabel, reading: .withheld(Self.held))
            )
        )
        let missing = try XCTUnwrap(Self.visible(Self.during(0), unknown))
        XCTAssertNil(missing.ballFraction)
        XCTAssertFalse(missing.showsBallsNotDrawn)
        XCTAssertEqual(missing.accessibilityBalls, "Legal balls used: Legal balls not reported")
        for row in missing.rateRows {
            XCTAssertNil(missing.rateFraction(row))
            XCTAssertFalse(missing.showsRateNotDrawn(row))
        }
        XCTAssertEqual(
            missing.accessibilityRates,
            "Runs per over so far: Rate unavailable. Needed from here, runs per over: Held — not current. "
                + "\(Self.scaleText). \(CricketChaseRates10868.qualifier)"
        )
        XCTAssertFalse(missing.accessibilityRates!.contains("0.00"))
        XCTAssertFalse(missing.accessibilityBalls!.contains(" 0 "))
    }

    // MARK: Independent failures

    func testEachFailureKeepsItsUsefulNeighbours() throws {
        let checkpoint = Self.checkpoints[1]
        // A failed chance keeps the task, budget and rates.
        let noChance = Self.make(
            phase: .during, eyebrow: Self.duringEyebrow, headline: Self.headline, pregame: .unavailable("No pregame reading"),
            comparison: .unavailable(Self.currentUnavailable),
            contractResult: .unavailable(Self.notYetKnown), matchResult: .unavailable(Self.notYetKnown),
            actual: .reported(Self.state(checkpoint)), detailsRef: nil, notes: []
        )
        let withChanceFailed = try XCTUnwrap(Self.visible(noChance, Self.context(checkpoint)))
        XCTAssertEqual(withChanceFailed.task, Self.liveTask(checkpoint))
        XCTAssertNotNil(withChanceFailed.ballFraction)
        XCTAssertEqual(withChanceFailed.rateRows.count, 2)
        XCTAssertEqual(noChance.accessibilityChances, "Pregame: No pregame reading. Recorded win chance: Current probability unavailable")

        // A failed score keeps the chances and the owner's independently
        // admitted task, budget and rates.
        let noScore = Self.make(
            phase: .during, eyebrow: Self.duringEyebrow, headline: Self.headline, pregame: Self.pregame,
            comparison: Self.recorded(checkpoint),
            contractResult: .unavailable(Self.notYetKnown), matchResult: .unavailable(Self.notYetKnown),
            actual: .unavailable(Self.scoreUnavailable), detailsRef: nil, notes: []
        )
        let withScoreFailed = try XCTUnwrap(Self.visible(noScore, Self.context(checkpoint)))
        XCTAssertEqual(noScore.accessibilityRuns, Self.scoreUnavailable)
        XCTAssertNil(noScore.railGeometry)
        XCTAssertEqual(withScoreFailed.accessibilityTask, "Chase · 15 overs: 63 runs needed from 30 balls left")
        XCTAssertEqual(withScoreFailed.accessibilityBalls, "Legal balls used: 90 of 120")
        XCTAssertTrue(noScore.accessibilityChances.hasSuffix("34%, \(checkpoint.recordedDetail)"))

        // A failed task keeps the budget and rates.
        let noTask = CricketChaseLimitedOvers10868(
            task: CricketChaseTask10868(label: checkpoint.taskLabel, reading: .unavailable("Chase task unavailable")),
            finish: nil, balls: Self.balls(checkpoint),
            rates: Self.rates(achieved: Self.achieved(checkpoint), required: Self.requiredRow(checkpoint))
        )
        let withTaskFailed = try XCTUnwrap(Self.visible(Self.during(1), noTask))
        XCTAssertEqual(withTaskFailed.accessibilityTask, "Chase · 15 overs: Chase task unavailable")
        XCTAssertEqual(withTaskFailed.ballFraction, 0.75)
        XCTAssertEqual(withTaskFailed.rateRows.count, 2)

        // A missing required rate keeps the achieved one, and vice versa.
        let noRequired = CricketChaseLimitedOvers10868(
            task: Self.liveTask(checkpoint), finish: nil, balls: Self.balls(checkpoint),
            rates: Self.rates(
                achieved: Self.achieved(checkpoint),
                required: CricketChaseRateRow10868(label: Self.requiredLabel, reading: .unavailable("Required rate unavailable"))
            )
        )
        let requiredFailed = try XCTUnwrap(Self.visible(Self.during(1), noRequired))
        XCTAssertEqual(requiredFailed.rateFraction(Self.achieved(checkpoint)), checkpoint.runRate / 16)
        XCTAssertTrue(requiredFailed.accessibilityRates!.contains("Needed from here, runs per over: Required rate unavailable"))
        let noAchieved = CricketChaseLimitedOvers10868(
            task: Self.liveTask(checkpoint), finish: nil, balls: nil,
            rates: Self.rates(
                achieved: CricketChaseRateRow10868(label: Self.achievedLabel, reading: .withheld(Self.held)),
                required: Self.requiredRow(checkpoint)
            )
        )
        let achievedFailed = try XCTUnwrap(Self.visible(Self.during(1), noAchieved))
        XCTAssertEqual(achievedFailed.rateFraction(try XCTUnwrap(Self.requiredRow(checkpoint))), 12.6 / 16)
        XCTAssertTrue(achievedFailed.accessibilityRates!.hasPrefix("Runs per over so far: Held — not current. Needed from here, runs per over: 12.60."))
        XCTAssertNil(achievedFailed.balls)
        XCTAssertNil(achievedFailed.accessibilityBalls)
    }

    func testUnknownTaskPartsStayTheOwnersWords() {
        let task = CricketChaseTask10868(
            label: "Chase · 15 overs",
            reading: .reported(
                lead: .reported(text: "63", caption: "runs needed"), connective: "from",
                trail: .unknown("balls left not reported"), detail: nil
            )
        )
        let context = CricketChaseLimitedOvers10868(task: task, finish: nil, balls: nil, rates: nil)
        let limited = Self.visible(Self.during(1), context)
        XCTAssertEqual(limited?.accessibilityTask, "Chase · 15 overs: 63 runs needed from balls left not reported")
        XCTAssertFalse(limited?.accessibilityTask?.contains("30") ?? true)
        let leadUnknown = CricketChaseTask10868(
            label: "Chase · 15 overs",
            reading: .reported(
                lead: .unknown("Runs needed unconfirmed"), connective: "from",
                trail: .reported(text: "30", caption: "balls left"), detail: nil
            )
        )
        XCTAssertEqual(
            Self.visible(Self.during(1), CricketChaseLimitedOvers10868(task: leadUnknown, finish: nil, balls: nil, rates: nil))?.accessibilityTask,
            "Chase · 15 overs: Runs needed unconfirmed from 30 balls left"
        )
    }

    // MARK: Malformed geometry

    func testMalformedBallCountsDrawNoRailAndKeepTheOwnersWords() throws {
        let bad: [(used: Double, limit: Double)] = [
            (121, 120), (1, 0), (0, 0), (0, -120), (-1, 120), (-0.5, 120),
            (.nan, 120), (90, .nan), (.infinity, 120), (90, .infinity), (-.infinity, 120),
            (90.5, 120), (90, 120.5),
        ]
        for (used, limit) in bad {
            XCTAssertNil(CricketChaseLimitedOversGeometry10868.balls(used: used, limit: limit), "\(used)/\(limit)")
            let context = CricketChaseLimitedOvers10868(
                task: nil, finish: nil, balls: Self.balls(text: "Owner words \(used) of \(limit)", used: used, limit: limit), rates: nil
            )
            let limited = try XCTUnwrap(Self.visible(Self.during(1), context))
            XCTAssertNil(limited.ballFraction, "\(used)/\(limit)")
            XCTAssertTrue(limited.showsBallsNotDrawn, "\(used)/\(limit)")
            XCTAssertEqual(
                limited.accessibilityBalls,
                "Legal balls used: Owner words \(used) of \(limit). Ball progress not drawn",
                "\(used)/\(limit)"
            )
        }
        // The domain ends are drawn whole, never clamped from outside.
        XCTAssertEqual(CricketChaseLimitedOversGeometry10868.balls(used: 0, limit: 120), 0)
        XCTAssertEqual(CricketChaseLimitedOversGeometry10868.balls(used: 120, limit: 120), 1)
        XCTAssertEqual(CricketChaseGeometry10868.x(0, width: 300, inset: 1), 1)
        XCTAssertEqual(CricketChaseGeometry10868.x(1, width: 300, inset: 1), 299)
    }

    func testMalformedRatesDrawNoBarAndKeepTheOwnersWords() throws {
        let badValues: [Double] = [16.01, 20, -0.01, -1, .nan, .infinity, -.infinity]
        for value in badValues {
            XCTAssertNil(CricketChaseLimitedOversGeometry10868.rate(value, ceiling: 16), "\(value)")
        }
        let badCeilings: [Double] = [0, -16, .nan, .infinity, -.infinity]
        for ceiling in badCeilings {
            XCTAssertNil(CricketChaseLimitedOversGeometry10868.rate(12.47, ceiling: ceiling), "\(ceiling)")
            XCTAssertNil(CricketChaseLimitedOversGeometry10868.rate(0, ceiling: ceiling), "\(ceiling)")
        }
        XCTAssertEqual(CricketChaseLimitedOversGeometry10868.rate(16, ceiling: 16), 1)
        // One bad row says so and keeps its words; its neighbour still draws
        // on the same ceiling.
        let context = CricketChaseLimitedOvers10868(
            task: nil, finish: nil, balls: nil,
            rates: Self.rates(
                achieved: Self.achieved(Self.checkpoints[1]),
                required: CricketChaseRateRow10868(label: Self.requiredLabel, reading: .reported(text: "21.00", value: 21, detail: nil))
            )
        )
        let limited = try XCTUnwrap(Self.visible(Self.during(1), context))
        let requiredRow = try XCTUnwrap(limited.rates?.required)
        XCTAssertNil(limited.rateFraction(requiredRow))
        XCTAssertTrue(limited.showsRateNotDrawn(requiredRow))
        XCTAssertEqual(limited.rateFraction(Self.achieved(Self.checkpoints[1])), (187.0 / 15) / 16)
        XCTAssertEqual(
            limited.accessibilityRates,
            "Runs per over so far: 12.47. Needed from here, runs per over: 21.00. Rate bar not drawn. "
                + "\(Self.scaleText). \(CricketChaseRates10868.qualifier)"
        )
        // A bad shared ceiling draws neither bar and keeps both figures.
        let badCeiling = CricketChaseLimitedOvers10868(
            task: nil, finish: nil, balls: nil,
            rates: Self.rates(ceiling: 0, achieved: Self.achieved(Self.checkpoints[1]), required: Self.requiredRow(Self.checkpoints[1]))
        )
        let noScale = try XCTUnwrap(Self.visible(Self.during(1), badCeiling))
        for row in noScale.rateRows {
            XCTAssertNil(noScale.rateFraction(row))
            XCTAssertTrue(noScale.showsRateNotDrawn(row))
        }
        XCTAssertTrue(noScale.accessibilityRates!.contains("12.47"))
        XCTAssertTrue(noScale.accessibilityRates!.contains("12.60"))
    }

    func testRatesShareOneCeilingWithNoPerRowScale() throws {
        let checkpoint = Self.checkpoints[1]
        let limited = try XCTUnwrap(Self.visible(Self.during(1), Self.context(checkpoint)))
        let achieved = try XCTUnwrap(limited.rateFraction(Self.achieved(checkpoint)))
        let required = try XCTUnwrap(limited.rateFraction(try XCTUnwrap(Self.requiredRow(checkpoint))))
        XCTAssertEqual(achieved, 12.466666666666667 / 16, accuracy: 1e-12)
        XCTAssertEqual(required, 12.6 / 16, accuracy: 1e-12)
        XCTAssertLessThan(achieved, required)
        // Changing one row does not rescale the other.
        let lowRequired = CricketChaseLimitedOvers10868(
            task: nil, finish: nil, balls: nil,
            rates: Self.rates(
                achieved: Self.achieved(checkpoint),
                required: CricketChaseRateRow10868(label: Self.requiredLabel, reading: .reported(text: "3.00", value: 3, detail: nil))
            )
        )
        let low = try XCTUnwrap(Self.visible(Self.during(1), lowRequired))
        XCTAssertEqual(try XCTUnwrap(low.rateFraction(Self.achieved(checkpoint))), achieved, accuracy: 1e-12)
        // A different owner ceiling moves both bars together.
        let wider = CricketChaseLimitedOvers10868(
            task: nil, finish: nil, balls: nil,
            rates: Self.rates(ceiling: 20, achieved: Self.achieved(checkpoint), required: Self.requiredRow(checkpoint))
        )
        let twenty = try XCTUnwrap(Self.visible(Self.during(1), wider))
        XCTAssertEqual(try XCTUnwrap(twenty.rateFraction(Self.achieved(checkpoint))), (187.0 / 15) / 20, accuracy: 1e-12)
        XCTAssertEqual(try XCTUnwrap(twenty.rateFraction(try XCTUnwrap(Self.requiredRow(checkpoint)))), 12.6 / 20, accuracy: 1e-12)
    }

    // MARK: Words, provenance and units

    func testRatesAreNeverAProjectionOrAProbability() {
        XCTAssertTrue(CricketChaseRates10868.qualifier.contains("not projections or chances"))
        for (index, checkpoint) in Self.checkpoints.enumerated() {
            let limited = Self.visible(Self.during(index), Self.context(checkpoint))
            for spoken in [limited?.accessibilityTask, limited?.accessibilityBalls, limited?.accessibilityRates] {
                XCTAssertFalse(spoken?.contains("%") ?? true, checkpoint.checkpoint)
                XCTAssertFalse(spoken?.lowercased().contains("projected") ?? true, checkpoint.checkpoint)
            }
            XCTAssertTrue(limited?.accessibilityRates?.hasSuffix(CricketChaseRates10868.qualifier) ?? false)
        }
    }

    func testSuppliedProvenanceIsSpokenInItsOwnSlot() throws {
        let taskDetail = "Owner task words from the 9:57 AM PDT, Oct 9 score report"
        let ballsDetail = "Legal deliveries from the 9:57 AM PDT, Oct 9 score report · not the exact ball time"
        let rateDetail = "From runs and legal balls in the 9:57 AM PDT, Oct 9 score report"
        let context = CricketChaseLimitedOvers10868(
            task: CricketChaseTask10868(
                label: "Chase · 15 overs",
                reading: .reported(
                    lead: .reported(text: "63", caption: "runs needed"), connective: "from",
                    trail: .reported(text: "30", caption: "balls left"), detail: taskDetail
                )
            ),
            finish: nil,
            balls: Self.balls(text: "90 of 120", used: 90, limit: 120, detail: ballsDetail),
            rates: Self.rates(
                achieved: CricketChaseRateRow10868(label: Self.achievedLabel, reading: .reported(text: "12.47", value: 187.0 / 15, detail: rateDetail)),
                required: nil
            )
        )
        let limited = try XCTUnwrap(Self.visible(Self.during(1), context))
        XCTAssertEqual(limited.accessibilityTask, "Chase · 15 overs: 63 runs needed from 30 balls left. \(taskDetail)")
        XCTAssertEqual(limited.accessibilityBalls, "Legal balls used: 90 of 120. \(ballsDetail)")
        XCTAssertEqual(
            limited.accessibilityRates,
            "Runs per over so far: 12.47, \(rateDetail). \(Self.scaleText). \(CricketChaseRates10868.qualifier)"
        )
    }

    func testLongOwnerWordsStayWholeAndVerbatim() throws {
        let longLabel = "Chase · 15 overs · reported, not the exact ball · Extraordinarily-Long-Checkpoint-Qualifier"
        let context = CricketChaseLimitedOvers10868(
            task: CricketChaseTask10868(
                label: longLabel,
                reading: .reported(
                    lead: .reported(text: "63", caption: "runs still needed to reach the target"), connective: "from",
                    trail: .reported(text: "30", caption: "legal balls remaining in the innings"), detail: nil
                )
            ),
            finish: nil, balls: nil, rates: nil
        )
        let limited = try XCTUnwrap(Self.visible(Self.during(1), context))
        XCTAssertEqual(
            limited.accessibilityTask,
            "\(longLabel): 63 runs still needed to reach the target from 30 legal balls remaining in the innings"
        )
        XCTAssertTrue(CricketChaseGeometry10868.words(longLabel).contains("Extraordinarily-Long-Checkpoint-Qualifier"))
    }

    // MARK: Identity and actions

    func testDetailsStayTheExactOwnerReferenceWithTheContext() {
        let input = Self.make(
            phase: .during, eyebrow: Self.duringEyebrow, headline: Self.headline, pregame: Self.pregame,
            comparison: Self.recorded(Self.checkpoints[1]),
            contractResult: .unavailable(Self.notYetKnown), matchResult: .unavailable(Self.notYetKnown),
            actual: .reported(Self.state(Self.checkpoints[1])), detailsRef: Self.ref, notes: []
        )
        XCTAssertNotNil(Self.visible(input, Self.context(Self.checkpoints[1])))
        XCTAssertEqual(input.detailsAction(canOpenDetails: true), .details(Self.ref))
        XCTAssertNil(input.detailsAction(canOpenDetails: false))
        XCTAssertEqual(input.detailsText, "West Indies wins · Details")
        var opened: [CricketChaseRef10868] = []
        input.detailsAction(canOpenDetails: true)?.perform(onDetails: { opened.append($0) })
        XCTAssertEqual(opened, [Self.ref])
        // Retained rows carry no reference, so no Details is invented.
        for index in Self.checkpoints.indices {
            XCTAssertNil(Self.during(index).detailsAction(canOpenDetails: true))
        }
        XCTAssertNil(Self.finalInput.detailsAction(canOpenDetails: true))
    }

    func testLimitedOverAccessibilityIdentifiersAreStableAndDistinct() {
        let ids = [
            CricketChaseAccessibilityID10868.task,
            CricketChaseAccessibilityID10868.balls,
            CricketChaseAccessibilityID10868.rates,
        ]
        XCTAssertEqual(ids, ["cricketChase10868.task", "cricketChase10868.balls", "cricketChase10868.rates"])
        let existing = [
            CricketChaseAccessibilityID10868.header, CricketChaseAccessibilityID10868.chances,
            CricketChaseAccessibilityID10868.runs, CricketChaseAccessibilityID10868.wickets,
            CricketChaseAccessibilityID10868.report, CricketChaseAccessibilityID10868.notes,
            CricketChaseAccessibilityID10868.details,
        ]
        XCTAssertEqual(Set(ids + existing).count, ids.count + existing.count)
    }

    // MARK: No parsed or derived fields

    func testLimitedOverContextCarriesNoDerivedOrParsedFields() {
        let context = Self.context(Self.checkpoints[1])
        let contextLabels = Mirror(reflecting: context).children.compactMap { $0.label }
        XCTAssertEqual(contextLabels, ["task", "finish", "balls", "rates"])
        let taskLabels = Mirror(reflecting: Self.liveTask(Self.checkpoints[1])).children.compactMap { $0.label }
        XCTAssertEqual(taskLabels, ["label", "reading"])
        let ballsLabels = Mirror(reflecting: Self.balls(Self.checkpoints[1])).children.compactMap { $0.label }
        XCTAssertEqual(ballsLabels, ["label", "reading", "notDrawn"])
        let ratesLabels = Mirror(reflecting: Self.rates(achieved: nil, required: nil)).children.compactMap { $0.label }
        XCTAssertEqual(ratesLabels, ["ceiling", "scaleText", "achieved", "required", "notDrawn"])
        let rowLabels = Mirror(reflecting: Self.achieved(Self.checkpoints[1])).children.compactMap { $0.label }
        XCTAssertEqual(rowLabels, ["label", "reading"])
        let all = Set(contextLabels + taskLabels + ballsLabels + ratesLabels + rowLabels)
        for forbidden in [
            "overs", "runsNeeded", "ballsLeft", "wicketsLeft", "target", "projection", "forecast", "probability",
            "winner", "result", "margin", "ticker", "title", "baseline", "currentness",
        ] {
            XCTAssertFalse(all.contains(forbidden), forbidden)
        }
    }

    // MARK: Measured layout (CONSTRUCTED widths)

    /// A subview that wraps down to `minimum` (its widest word or whole
    /// figure) and is `ideal` wide unconstrained.
    private static func measure(ideal: CGFloat, minimum: CGFloat) -> (CGFloat?) -> CGFloat {
        { proposal in
            guard let proposal else { return ideal }
            return max(minimum, min(ideal, proposal))
        }
    }

    /// Card content widths for 320, 375 and 393 pt screens with 16 pt card
    /// padding each side, and a wide reader.
    private static let contentWidths: [CGFloat] = [288, 343, 361, 700]

    func testTaskPairSharesARowAtPhoneAndWideWidthsWhenBothIdealsFit() {
        for width in Self.contentWidths {
            // Standard type: "63 / runs needed" beside "from 30 / balls left".
            XCTAssertEqual(CricketChaseGeometry10868.pairArrangement(
                available: width, spacing: 16, equalColumns: false, forceStack: false,
                first: Self.measure(ideal: 92, minimum: 86),
                second: Self.measure(ideal: 104, minimum: 98)
            ), .sideBySide, "\(width)")
            // "252 / runs scored" beside "with 9 / balls to spare".
            XCTAssertEqual(CricketChaseGeometry10868.pairArrangement(
                available: width, spacing: 16, equalColumns: false, forceStack: false,
                first: Self.measure(ideal: 92, minimum: 86),
                second: Self.measure(ideal: 104, minimum: 72)
            ), .sideBySide, "\(width)")
        }
    }

    func testTaskPairAndRowsStackForLargeTypeAtNarrowWidthsAndAlwaysAtAccessibilitySizes() {
        // Large type at 320: 170 + 16 + 180 > 288 — stacked; nothing shrinks.
        XCTAssertEqual(CricketChaseGeometry10868.pairArrangement(
            available: 288, spacing: 16, equalColumns: false, forceStack: false,
            first: Self.measure(ideal: 170, minimum: 130),
            second: Self.measure(ideal: 180, minimum: 140)
        ), .stacked)
        // The same at 375 and 393 still stacks; the wide reader fits.
        for width: CGFloat in [343, 361] {
            XCTAssertEqual(CricketChaseGeometry10868.pairArrangement(
                available: width, spacing: 16, equalColumns: false, forceStack: false,
                first: Self.measure(ideal: 170, minimum: 130),
                second: Self.measure(ideal: 180, minimum: 140)
            ), .stacked, "\(width)")
        }
        XCTAssertEqual(CricketChaseGeometry10868.pairArrangement(
            available: 700, spacing: 16, equalColumns: false, forceStack: false,
            first: Self.measure(ideal: 170, minimum: 130),
            second: Self.measure(ideal: 180, minimum: 140)
        ), .sideBySide)
        // Accessibility sizes stack the task pair and every label/value row.
        for width in Self.contentWidths {
            XCTAssertEqual(CricketChaseGeometry10868.pairArrangement(
                available: width, spacing: 12, equalColumns: false, forceStack: true,
                first: Self.measure(ideal: 40, minimum: 40),
                second: Self.measure(ideal: 40, minimum: 40)
            ), .stacked, "\(width)")
        }
        // Rate row at 320: a 190 pt label beside a 44 pt figure fits; a
        // 260 pt label does not, so the figure moves below it whole.
        XCTAssertEqual(CricketChaseGeometry10868.pairArrangement(
            available: 288, spacing: 12, equalColumns: false, forceStack: false,
            first: Self.measure(ideal: 190, minimum: 70),
            second: Self.measure(ideal: 44, minimum: 44)
        ), .sideBySide)
        XCTAssertEqual(CricketChaseGeometry10868.pairArrangement(
            available: 288, spacing: 12, equalColumns: false, forceStack: false,
            first: Self.measure(ideal: 260, minimum: 70),
            second: Self.measure(ideal: 44, minimum: 44)
        ), .stacked)
        // The figure column keeps its whole ideal width at the trailing edge.
        XCTAssertEqual(
            CricketChaseGeometry10868.columns(total: 288, secondIdeal: 44, spacing: 12, equalColumns: false),
            CricketChaseColumns10868(first: 232, second: 44)
        )
    }

    // MARK: Qualifier

    func testQualifierNamesTheUnitWithoutCallingRequiredPaceTheScoreSoFar() throws {
        // Required pace looks forward, so the shared qualifier names the unit
        // and never says every rate describes the score so far.
        let qualifier = CricketChaseRates10868.qualifier
        XCTAssertEqual(qualifier, "Scoring rates are measured in runs per over. They are not projections or chances")
        XCTAssertFalse(qualifier.lowercased().contains("so far"))
        XCTAssertFalse(qualifier.contains("describe the score"))
        // During play the two rows keep their distinct owner labels; only the
        // achieved label says "so far".
        for (index, checkpoint) in Self.checkpoints.enumerated() {
            let limited = try XCTUnwrap(Self.visible(Self.during(index), Self.context(checkpoint)))
            XCTAssertEqual(limited.rateRows.map(\.label), [Self.achievedLabel, Self.requiredLabel], checkpoint.checkpoint)
            let spoken = try XCTUnwrap(limited.accessibilityRates)
            XCTAssertTrue(spoken.hasPrefix("\(Self.achievedLabel): "), checkpoint.checkpoint)
            XCTAssertTrue(spoken.contains(". \(Self.requiredLabel): "), checkpoint.checkpoint)
            XCTAssertTrue(spoken.hasSuffix(qualifier), checkpoint.checkpoint)
            XCTAssertEqual(spoken.components(separatedBy: "so far").count - 1, 1, checkpoint.checkpoint)
        }
        // At the final only achieved pace remains, under the same qualifier,
        // even when a required row is supplied.
        for context in [Self.finalContext, Self.everythingContext] {
            let limited = try XCTUnwrap(Self.visible(Self.finalInput, context))
            XCTAssertEqual(limited.rateRows.map(\.label), [Self.achievedLabel])
            let spoken = try XCTUnwrap(limited.accessibilityRates)
            XCTAssertFalse(spoken.contains(Self.requiredLabel))
            XCTAssertTrue(spoken.hasSuffix(qualifier))
        }
    }
}

/// #10868 (cricket-t20) — the expectation-shift card: equal pregame and
/// recorded/current headline figures (the reported match result at the
/// final) above one row per owner score report, each row a hollow pregame
/// mark and a filled recorded mark on one shared zero-to-100% scale.
///
/// The view is SwiftUI and is not rasterised here. What is asserted is the
/// rules it defers to: before hides every supplied row, reading and result;
/// play shows only the owner's rows with its own independent headline; the
/// final keeps pregame beside the reported result and the historical rows
/// with no finish row or 0%/100% point; independent baseline, headline and
/// row failures; real 0 and 1 versus unknown versus malformed positions; one
/// fixed scale for every row and cohort; no segment between rows; owner
/// order without a cap; measured label-band and pair arithmetic; exact
/// Details; and the spoken text. Nothing here claims a rendered fit, a native
/// runtime, live app delivery, route or phase completion, or a production
/// binding.
///
/// ARCHIVED raw values come from India–West Indies, second T20I, Ranchi,
/// October 9, 2026 (route cricket-t20, event KXT20MATCH-26OCT090930WIIND), as
/// referenced by `shipping-adoption-20261027/T20-SHIFT-REUSE-RETAINED-CASES.json`
/// into the pinned `T20-CHASE-REUSE-RETAINED-CASES.json` (sha256
/// c7ef73fb…03cb). Original: Kalshi KXT20MATCH-26OCT090930WIIND-WI, side Yes
/// ("West Indies wins"). No internal app event/market/outcome id is retained.
///   Pregame WI 0.23, minute bar ending 12:57Z (raw index 51).
///   West Indies chase, published score reports (publication, not ball time):
///     13.0  170/3  report 16:46:44Z  bar end 16:46Z  WI 0.57  raw 280
///     15.0  187/4  report 16:57:47Z  bar end 16:57Z  WI 0.34  raw 291
///     17.0  223/4  report 17:06:58Z  bar end 17:06Z  WI 0.89  raw 300
///     18.0  240/4  report 17:12:01Z  bar end 17:12Z  WI 0.99  raw 306
///   Final match report 17:19:41Z: West Indies won by 6 wickets.
///
/// CONSTRUCTED owner-resolved inputs (this leaf resolves none of them): row
/// ids and labels, score words, the 0–100% ticks and their words, the
/// before/during-at-15-overs/final phase frames, every display string
/// (figures, local-calendar provenance, labels, result words), every action
/// reference (none is retained), and every absent, withheld, zero, one,
/// equal, close, malformed, unknown-report, empty-word, reordered, long-text
/// and measured-width case.
final class CricketChaseShift10868Tests: XCTestCase {

    // MARK: ARCHIVED source

    private static let ticker = "KXT20MATCH-26OCT090930WIIND-WI"
    private static let side = "Yes"
    private static let pregameProbability = 0.23
    private static let pregameBarEnd = "2026-10-09T12:57:00+00:00"
    private static let pregameRawIndex = 51
    private static let finalReportedAt = "2026-10-09T17:19:41+00:00"

    private struct RetainedCheckpoint {
        /// ARCHIVED.
        let overs: String
        let runs: Int
        let wickets: Int
        let reportedAt: String
        let barEnd: String
        let probability: Double
        let rawIndex: Int
        /// CONSTRUCTED owner identity and text.
        let ownerID: String
        let label: String
        let recordedText: String
        let recordedDetail: String
        let reportDetail: String
    }

    private static let checkpoints: [RetainedCheckpoint] = [
        RetainedCheckpoint(
            overs: "13.0", runs: 170, wickets: 3, reportedAt: "2026-10-09T16:46:44+00:00",
            barEnd: "2026-10-09T16:46:00+00:00", probability: 0.57, rawIndex: 280,
            ownerID: "constructed:checkpoint:13.0", label: "13.0 overs", recordedText: "57%",
            recordedDetail: "Kalshi trade close · minute 9:45–9:46 AM PDT, Oct 9",
            reportDetail: "Score report published 9:46 AM PDT, Oct 9 · not the exact ball time"
        ),
        RetainedCheckpoint(
            overs: "15.0", runs: 187, wickets: 4, reportedAt: "2026-10-09T16:57:47+00:00",
            barEnd: "2026-10-09T16:57:00+00:00", probability: 0.34, rawIndex: 291,
            ownerID: "constructed:checkpoint:15.0", label: "15.0 overs", recordedText: "34%",
            recordedDetail: "Kalshi trade close · minute 9:56–9:57 AM PDT, Oct 9",
            reportDetail: "Score report published 9:57 AM PDT, Oct 9 · not the exact ball time"
        ),
        RetainedCheckpoint(
            overs: "17.0", runs: 223, wickets: 4, reportedAt: "2026-10-09T17:06:58+00:00",
            barEnd: "2026-10-09T17:06:00+00:00", probability: 0.89, rawIndex: 300,
            ownerID: "constructed:checkpoint:17.0", label: "17.0 overs", recordedText: "89%",
            recordedDetail: "Kalshi trade close · minute 10:05–10:06 AM PDT, Oct 9",
            reportDetail: "Score report published 10:06 AM PDT, Oct 9 · not the exact ball time"
        ),
        RetainedCheckpoint(
            overs: "18.0", runs: 240, wickets: 4, reportedAt: "2026-10-09T17:12:01+00:00",
            barEnd: "2026-10-09T17:12:00+00:00", probability: 0.99, rawIndex: 306,
            ownerID: "constructed:checkpoint:18.0", label: "18.0 overs", recordedText: "99%",
            recordedDetail: "Kalshi trade close · minute 10:11–10:12 AM PDT, Oct 9",
            reportDetail: "Score report published 10:12 AM PDT, Oct 9 · not the exact ball time"
        ),
    ]

    // MARK: CONSTRUCTED owner words

    private static let subject = "West Indies wins"
    private static let eyebrow = "West Indies · expectation shift"
    private static let duringTitle = "How the chase changed"
    private static let finalTitle = "From outsider to winner"
    private static let pregameLabel = "Pregame"
    private static let comparisonLabel = "Recorded win chance"
    private static let resultLabel = "Actual result"
    private static let originalResultLabel = "Original result"
    private static let recordedLabel = "Last trade before report"
    private static let checkpointsLabel = "West Indies recorded win chances versus pregame at each captured score report"
    private static let scaleLabel = "Win chance"
    private static let baselineNotDrawn = "Pregame mark not drawn"
    private static let rowNotDrawn = "Recorded mark not drawn"
    private static let pregameText = "23%"
    private static let pregameDetail = "Kalshi trade close · minute 5:56–5:57 AM PDT, Oct 9"
    private static let pregameUnavailable = "Pregame probability unavailable"
    private static let currentUnavailable = "Current probability unavailable"
    private static let held = "Held — not current"
    private static let noTrade = "No trade before this report"
    private static let scoreUnavailable = "Score report unavailable"
    private static let notYetKnown = "Not known until the match is over"
    private static let notes = ["Historical probabilities paired with separately timed score reports."]
    private static let finalMatchText = "West Indies won by 6 wickets"
    private static let finalMatchDetail = "Final score report published 10:19 AM PDT, Oct 9 · not the exact finish time"
    private static let gradedText = "Won"
    private static let gradedDetail = "Kalshi settled Yes · 10:45 AM PDT, Oct 9"

    private static let ref = CricketChaseRef10868(event: "owner-event-t20", market: "owner-market-wi", outcome: "owner-outcome-wi")

    private static let ticks = [
        CricketChaseShiftTick10868(value: 0, words: "0%"),
        CricketChaseShiftTick10868(value: 0.5, words: "50%"),
        CricketChaseShiftTick10868(value: 1, words: "100%"),
    ]

    private static var pregame: CricketChaseReading10868 {
        .observed(CricketChaseFigure10868(text: pregameText, detail: pregameDetail))
    }

    /// The owner's own headline reading at 15 overs — supplied, not elected
    /// from the rows.
    private static var headlineAtFifteen: CricketChaseReading10868 {
        .observed(CricketChaseFigure10868(text: "34%", detail: checkpoints[1].recordedDetail))
    }

    private static var finalMatch: CricketChaseMatchResult10868 {
        .reported(CricketChaseFigure10868(text: finalMatchText, detail: finalMatchDetail))
    }

    private static var graded: CricketChaseContractResult10868 {
        .graded(CricketChaseFigure10868(text: gradedText, detail: gradedDetail))
    }

    /// CONSTRUCTED owner row from an ARCHIVED checkpoint.
    private static func row(_ checkpoint: RetainedCheckpoint) -> CricketChaseShiftRow10868 {
        CricketChaseShiftRow10868(
            id: checkpoint.ownerID,
            label: checkpoint.label,
            score: .reported(CricketChaseFigure10868(
                text: "\(checkpoint.runs)/\(checkpoint.wickets)", detail: checkpoint.reportDetail
            )),
            recorded: .observed(CricketChaseFigure10868(text: checkpoint.recordedText, detail: checkpoint.recordedDetail)),
            position: checkpoint.probability
        )
    }

    private static func constructedRow(
        id: String,
        label: String,
        score: CricketChaseShiftScore10868,
        recorded: CricketChaseReading10868,
        position: Double?
    ) -> CricketChaseShiftRow10868 {
        CricketChaseShiftRow10868(id: id, label: label, score: score, recorded: recorded, position: position)
    }

    private static func segment(_ lower: Double, _ upper: Double) -> CricketChaseShiftSegment10868 {
        CricketChaseShiftSegment10868(lower: lower, upper: upper)
    }

    /// Every field explicit: constructed cases never default through retained values.
    private static func make(
        phase: CricketChasePhase10868,
        title: String,
        pregame: CricketChaseReading10868,
        pregamePosition: Double?,
        comparison: CricketChaseReading10868,
        matchResult: CricketChaseMatchResult10868,
        originalResult: CricketChaseContractResult10868?,
        rows: [CricketChaseShiftRow10868],
        ticks: [CricketChaseShiftTick10868] = CricketChaseShift10868Tests.ticks,
        detailsRef: CricketChaseRef10868?,
        notes: [String]
    ) -> CricketChaseShiftInput10868 {
        CricketChaseShiftInput10868(
            phase: phase,
            subject: subject,
            eyebrow: eyebrow,
            title: title,
            pregameLabel: pregameLabel,
            pregame: pregame,
            pregamePosition: pregamePosition,
            comparisonLabel: comparisonLabel,
            comparison: comparison,
            resultLabel: resultLabel,
            matchResult: matchResult,
            originalResultLabel: originalResultLabel,
            originalResult: originalResult,
            recordedLabel: recordedLabel,
            checkpointsLabel: checkpointsLabel,
            scale: CricketChaseShiftScale10868(label: scaleLabel, ticks: ticks),
            rows: rows,
            baselineNotDrawn: baselineNotDrawn,
            rowNotDrawn: rowNotDrawn,
            detailsRef: detailsRef,
            notes: notes
        )
    }

    /// The constructed 15-overs frame: only the 13.0 and 15.0 rows.
    private static func during(
        pregame: CricketChaseReading10868 = CricketChaseShift10868Tests.pregame,
        pregamePosition: Double? = CricketChaseShift10868Tests.pregameProbability,
        comparison: CricketChaseReading10868 = CricketChaseShift10868Tests.headlineAtFifteen,
        rows: [CricketChaseShiftRow10868] = [CricketChaseShift10868Tests.row(CricketChaseShift10868Tests.checkpoints[0]), CricketChaseShift10868Tests.row(CricketChaseShift10868Tests.checkpoints[1])],
        detailsRef: CricketChaseRef10868? = nil
    ) -> CricketChaseShiftInput10868 {
        make(
            phase: .during, title: duringTitle, pregame: pregame, pregamePosition: pregamePosition,
            comparison: comparison, matchResult: .unavailable(notYetKnown), originalResult: nil,
            rows: rows, detailsRef: detailsRef, notes: notes
        )
    }

    /// The constructed final: all four historical rows. The supplied 99%
    /// headline is a settled price the card must not show as a chance.
    private static func finalInput(
        originalResult: CricketChaseContractResult10868? = nil,
        rows: [CricketChaseShiftRow10868] = CricketChaseShift10868Tests.checkpoints.map(CricketChaseShift10868Tests.row)
    ) -> CricketChaseShiftInput10868 {
        make(
            phase: .final, title: finalTitle, pregame: pregame, pregamePosition: pregameProbability,
            comparison: .observed(CricketChaseFigure10868(text: "99%", detail: checkpoints[3].recordedDetail)),
            matchResult: finalMatch, originalResult: originalResult,
            rows: rows, detailsRef: nil, notes: notes
        )
    }

    /// Everything the card speaks.
    private static func allSpoken(_ input: CricketChaseShiftInput10868) -> String {
        ([input.accessibilityHeader, input.accessibilityChances, input.accessibilityPlot]
            + input.rows.map { Optional(input.accessibilityRow($0)) }
            + [input.accessibilityNotes])
            .compactMap { $0 }
            .joined(separator: " | ")
    }

    // MARK: Retained packet

    func testRetainedShiftPacketValuesAreTheArchivedOnes() {
        XCTAssertEqual(Self.ticker, "KXT20MATCH-26OCT090930WIIND-WI")
        XCTAssertEqual(Self.side, "Yes")
        XCTAssertEqual(Self.pregameProbability, 0.23)
        XCTAssertEqual(Self.pregameBarEnd, "2026-10-09T12:57:00+00:00")
        XCTAssertEqual(Self.pregameRawIndex, 51)
        XCTAssertEqual(Self.checkpoints.map(\.overs), ["13.0", "15.0", "17.0", "18.0"])
        XCTAssertEqual(Self.checkpoints.map(\.runs), [170, 187, 223, 240])
        XCTAssertEqual(Self.checkpoints.map(\.wickets), [3, 4, 4, 4])
        XCTAssertEqual(Self.checkpoints.map(\.probability), [0.57, 0.34, 0.89, 0.99])
        XCTAssertEqual(Self.checkpoints.map(\.rawIndex), [280, 291, 300, 306])
        XCTAssertEqual(Self.checkpoints.map(\.reportedAt), [
            "2026-10-09T16:46:44+00:00", "2026-10-09T16:57:47+00:00",
            "2026-10-09T17:06:58+00:00", "2026-10-09T17:12:01+00:00",
        ])
        XCTAssertEqual(Self.checkpoints.map(\.barEnd), [
            "2026-10-09T16:46:00+00:00", "2026-10-09T16:57:00+00:00",
            "2026-10-09T17:06:00+00:00", "2026-10-09T17:12:00+00:00",
        ])
        // Publication and minute-bar end are different clocks at every row.
        for checkpoint in Self.checkpoints {
            XCTAssertNotEqual(checkpoint.reportedAt, checkpoint.barEnd, checkpoint.overs)
        }
        XCTAssertEqual(Self.finalReportedAt, "2026-10-09T17:19:41+00:00")
        XCTAssertEqual(Self.finalMatchText, "West Indies won by 6 wickets")
    }

    // MARK: Four checkpoints on one scale

    func testFourCheckpointsPlaceBesidePregameOnOneScale() {
        let input = Self.finalInput()
        XCTAssertEqual(input.baselinePosition, 0.23)
        XCTAssertEqual(input.visibleRows.map { input.rowPosition($0) }, [0.57, 0.34, 0.89, 0.99])
        XCTAssertEqual(input.visibleRows.map { input.rowSegment($0) }, [
            Self.segment(0.23, 0.57), Self.segment(0.23, 0.34), Self.segment(0.23, 0.89), Self.segment(0.23, 0.99),
        ])
        XCTAssertEqual(input.visibleRows.map(\.label), ["13.0 overs", "15.0 overs", "17.0 overs", "18.0 overs"])
        for row in input.visibleRows {
            XCTAssertFalse(input.showsRowNotDrawn(row), row.label)
        }
        XCTAssertFalse(input.showsBaselineNotDrawn)
    }

    // MARK: During

    func testDuringAtFifteenOversShowsOnlyTheOwnersRowsAndItsIndependentHeadline() {
        let input = Self.during()
        XCTAssertTrue(input.isShown)
        XCTAssertEqual(input.visibleRows.map(\.label), ["13.0 overs", "15.0 overs"])
        XCTAssertEqual(input.visibleComparison, Self.headlineAtFifteen)
        XCTAssertNil(input.visibleMatchResult)
        XCTAssertNil(input.visibleOriginalResult)
        XCTAssertEqual(input.accessibilityHeader, "West Indies · expectation shift. How the chase changed")
        XCTAssertEqual(
            input.accessibilityChances,
            "Pregame: 23%, Kalshi trade close · minute 5:56–5:57 AM PDT, Oct 9. "
                + "Recorded win chance: 34%, Kalshi trade close · minute 9:56–9:57 AM PDT, Oct 9"
        )
        let spoken = Self.allSpoken(input)
        for later in ["17.0 overs", "223/4", "89%", "18.0 overs", "240/4", "99%", Self.finalMatchText, Self.resultLabel] {
            XCTAssertFalse(spoken.contains(later), later)
        }
    }

    func testMissingOrHeldHeadlineKeepsBaselineAndRowsAndNeverBorrowsTheLastRow() throws {
        for (comparison, words) in [
            (CricketChaseReading10868.unavailable(Self.currentUnavailable), Self.currentUnavailable),
            (CricketChaseReading10868.withheld(Self.held), Self.held),
        ] {
            let input = Self.during(comparison: comparison)
            XCTAssertEqual(input.visibleComparison, comparison)
            XCTAssertEqual(input.baselinePosition, 0.23)
            XCTAssertEqual(input.visibleRows.map { input.rowPosition($0) }, [0.57, 0.34])
            let chances = try XCTUnwrap(input.accessibilityChances)
            XCTAssertTrue(chances.hasSuffix("\(Self.comparisonLabel): \(words)"), words)
            XCTAssertFalse(chances.contains("34%"), words)
            XCTAssertFalse(chances.contains("57%"), words)
        }
    }

    // MARK: Final

    func testFinalKeepsPregameBesideTheReportedResultAndAllFourHistoricalRows() {
        let input = Self.finalInput()
        XCTAssertNil(input.visibleComparison)
        XCTAssertEqual(input.visibleMatchResult, Self.finalMatch)
        XCTAssertNil(input.visibleOriginalResult)
        XCTAssertEqual(input.visibleRows, Self.checkpoints.map(Self.row))
        // No finish row and no synthetic 0% or 100% point.
        XCTAssertEqual(input.visibleRows.count, 4)
        for row in input.visibleRows {
            XCTAssertNotEqual(input.rowPosition(row), 1, row.label)
            XCTAssertNotEqual(input.rowPosition(row), 0, row.label)
        }
        XCTAssertEqual(
            input.accessibilityChances,
            "Pregame: 23%, Kalshi trade close · minute 5:56–5:57 AM PDT, Oct 9. "
                + "Actual result: West Indies won by 6 wickets, "
                + "Final score report published 10:19 AM PDT, Oct 9 · not the exact finish time"
        )
        XCTAssertEqual(input.accessibilityHeader, "West Indies · expectation shift. From outsider to winner")
        XCTAssertFalse(Self.allSpoken(input).contains(Self.comparisonLabel))
    }

    func testOriginalResultIsSeparatelyLabelledAndNeverReadFromTheMatch() throws {
        let gradedInput = Self.finalInput(originalResult: Self.graded)
        XCTAssertEqual(gradedInput.visibleOriginalResult, Self.graded)
        XCTAssertEqual(gradedInput.visibleMatchResult, Self.finalMatch)
        let spoken = try XCTUnwrap(gradedInput.accessibilityChances)
        XCTAssertTrue(spoken.hasSuffix("Original result: Won, Kalshi settled Yes · 10:45 AM PDT, Oct 9"))
        // A contradictory grade stays the owner's word; the leaf reconciles nothing.
        let contradictory = CricketChaseContractResult10868.graded(CricketChaseFigure10868(text: "Lost", detail: "Constructed contradiction"))
        let contradictoryInput = Self.finalInput(originalResult: contradictory)
        XCTAssertEqual(contradictoryInput.visibleOriginalResult, contradictory)
        XCTAssertEqual(contradictoryInput.visibleMatchResult, Self.finalMatch)
        XCTAssertTrue(try XCTUnwrap(contradictoryInput.accessibilityChances).hasSuffix("Original result: Lost, Constructed contradiction"))
        // Unconfirmed and void stay the owner's words, never a loss.
        for (result, words) in [
            (CricketChaseContractResult10868.unconfirmed("Awaiting settlement"), "Awaiting settlement"),
            (CricketChaseContractResult10868.void("Voided by the venue"), "Voided by the venue"),
        ] {
            let chances = try XCTUnwrap(Self.finalInput(originalResult: result).accessibilityChances)
            XCTAssertTrue(chances.hasSuffix("Original result: \(words)"), words)
            XCTAssertFalse(chances.contains("Lost"), words)
        }
        // No original result is invented when none is supplied, and none
        // shows in play even when supplied.
        XCTAssertFalse(try XCTUnwrap(Self.finalInput().accessibilityChances).contains(Self.originalResultLabel))
        let duringWithGrade = Self.make(
            phase: .during, title: Self.duringTitle, pregame: Self.pregame, pregamePosition: Self.pregameProbability,
            comparison: Self.headlineAtFifteen, matchResult: Self.finalMatch, originalResult: Self.graded,
            rows: [Self.row(Self.checkpoints[0])], detailsRef: nil, notes: []
        )
        XCTAssertNil(duringWithGrade.visibleOriginalResult)
        XCTAssertNil(duringWithGrade.visibleMatchResult)
        XCTAssertFalse(Self.allSpoken(duringWithGrade).contains(Self.gradedText))
    }

    // MARK: Before

    func testBeforeHidesTheCardAndEverySpokenFactDespiteSuppliedLaterFacts() {
        let input = Self.make(
            phase: .before, title: Self.duringTitle, pregame: Self.pregame, pregamePosition: Self.pregameProbability,
            comparison: Self.headlineAtFifteen, matchResult: Self.finalMatch, originalResult: Self.graded,
            rows: Self.checkpoints.map(Self.row), detailsRef: Self.ref, notes: Self.notes
        )
        XCTAssertFalse(input.isShown)
        XCTAssertNil(input.visiblePregame)
        XCTAssertNil(input.visibleComparison)
        XCTAssertNil(input.visibleMatchResult)
        XCTAssertNil(input.visibleOriginalResult)
        XCTAssertTrue(input.visibleRows.isEmpty)
        XCTAssertTrue(input.visibleTicks.isEmpty)
        XCTAssertTrue(input.visibleNotes.isEmpty)
        XCTAssertNil(input.baselinePosition)
        XCTAssertFalse(input.showsBaselineNotDrawn)
        XCTAssertNil(input.accessibilityHeader)
        XCTAssertNil(input.accessibilityChances)
        XCTAssertNil(input.accessibilityPlot)
        XCTAssertNil(input.accessibilityNotes)
        XCTAssertNil(input.detailsAction(canOpenDetails: true))
        XCTAssertNil(input.accessibilityID(at: 0))
        for row in input.rows {
            XCTAssertNil(input.rowPosition(row), row.label)
            XCTAssertNil(input.rowSegment(row), row.label)
            XCTAssertFalse(input.showsRowNotDrawn(row), row.label)
            XCTAssertEqual(input.accessibilityRow(row), "", row.label)
        }
        // Four supplied rows speak four empty strings and nothing else.
        XCTAssertEqual(Self.allSpoken(input).replacingOccurrences(of: " | ", with: ""), "")
    }

    // MARK: Independent absences

    func testAbsentOrHeldBaselineKeepsEveryRowObservation() {
        for (pregame, words) in [
            (CricketChaseReading10868.unavailable(Self.pregameUnavailable), Self.pregameUnavailable),
            (CricketChaseReading10868.withheld(Self.held), Self.held),
        ] {
            // A supplied position cannot place a pregame that carries no value.
            let input = Self.during(pregame: pregame, pregamePosition: Self.pregameProbability)
            XCTAssertNil(input.baselinePosition, words)
            XCTAssertFalse(input.showsBaselineNotDrawn, words)
            XCTAssertEqual(input.visibleRows.map { input.rowPosition($0) }, [0.57, 0.34], words)
            XCTAssertEqual(input.visibleRows.map { input.rowSegment($0) }, [nil, nil], words)
            XCTAssertEqual(input.accessibilityChances?.hasPrefix("\(Self.pregameLabel): \(words). "), true, words)
            XCTAssertEqual(
                input.accessibilityRow(input.visibleRows[1]),
                "15.0 overs. 187/4, Score report published 9:57 AM PDT, Oct 9 · not the exact ball time. "
                    + "Last trade before report: 34%, Kalshi trade close · minute 9:56–9:57 AM PDT, Oct 9. "
                    + "Pregame: \(words)",
                words
            )
        }
    }

    func testAbsentOrHeldRowReadingKeepsTheBaselineAndItsOwnReason() {
        let missing = Self.constructedRow(
            id: Self.checkpoints[1].ownerID, label: "15.0 overs",
            score: .reported(CricketChaseFigure10868(text: "187/4", detail: Self.checkpoints[1].reportDetail)),
            recorded: .unavailable(Self.noTrade), position: 0.34
        )
        let heldRow = Self.constructedRow(
            id: Self.checkpoints[2].ownerID, label: "17.0 overs",
            score: .reported(CricketChaseFigure10868(text: "223/4", detail: Self.checkpoints[2].reportDetail)),
            recorded: .withheld(Self.held), position: 0.89
        )
        let input = Self.finalInput(rows: [Self.row(Self.checkpoints[0]), missing, heldRow, Self.row(Self.checkpoints[3])])
        XCTAssertEqual(input.baselinePosition, 0.23)
        XCTAssertEqual(input.visibleRows.map { input.rowPosition($0) }, [0.57, nil, nil, 0.99])
        XCTAssertEqual(input.visibleRows.map { input.rowSegment($0) }, [
            Self.segment(0.23, 0.57), nil, nil, Self.segment(0.23, 0.99),
        ])
        XCTAssertFalse(input.showsRowNotDrawn(missing))
        XCTAssertFalse(input.showsRowNotDrawn(heldRow))
        XCTAssertEqual(
            input.accessibilityRow(missing),
            "15.0 overs. 187/4, Score report published 9:57 AM PDT, Oct 9 · not the exact ball time. "
                + "Last trade before report: No trade before this report. Pregame: 23%"
        )
        let heldSpoken = input.accessibilityRow(heldRow)
        XCTAssertTrue(heldSpoken.contains("Last trade before report: \(Self.held)"))
        for borrowed in ["57%", "99%", "89%", " 0%"] {
            XCTAssertFalse(input.accessibilityRow(missing).contains(borrowed), borrowed)
            XCTAssertFalse(heldSpoken.contains(borrowed), borrowed)
        }
    }

    // MARK: Zero, one and unknown

    func testRealZeroAndOneAreValuesAndUnknownIsNot() {
        XCTAssertEqual(CricketChaseShiftGeometry10868.position(0), 0)
        XCTAssertEqual(CricketChaseShiftGeometry10868.position(1), 1)
        XCTAssertNil(CricketChaseShiftGeometry10868.position(nil))
        let zero = Self.constructedRow(
            id: "constructed:zero", label: "Constructed zero",
            score: .reported(CricketChaseFigure10868(text: "120/9", detail: "Constructed report")),
            recorded: .observed(CricketChaseFigure10868(text: "0%", detail: "Constructed bar")), position: 0
        )
        let one = Self.constructedRow(
            id: "constructed:one", label: "Constructed one",
            score: .reported(CricketChaseFigure10868(text: "249/2", detail: "Constructed report")),
            recorded: .observed(CricketChaseFigure10868(text: "100%", detail: "Constructed bar")), position: 1
        )
        let unknown = Self.constructedRow(
            id: "constructed:unknown", label: "Constructed unknown",
            score: .reported(CricketChaseFigure10868(text: "200/4", detail: "Constructed report")),
            recorded: .observed(CricketChaseFigure10868(text: "57%", detail: "Constructed bar")), position: nil
        )
        let input = Self.during(pregamePosition: 0, rows: [zero, one, unknown])
        XCTAssertEqual(input.baselinePosition, 0)
        XCTAssertEqual(input.rowPosition(zero), 0)
        XCTAssertEqual(input.rowPosition(one), 1)
        XCTAssertNil(input.rowPosition(unknown))
        XCTAssertTrue(input.showsRowNotDrawn(unknown))
        XCTAssertEqual(input.rowSegment(zero), Self.segment(0, 0))
        XCTAssertEqual(input.rowSegment(one), Self.segment(0, 1))
        XCTAssertNil(input.rowSegment(unknown))
        // The end marks sit at the inset ends of the one shared track.
        XCTAssertEqual(CricketChaseGeometry10868.x(0, width: 288, inset: 9), 9)
        XCTAssertEqual(CricketChaseGeometry10868.x(1, width: 288, inset: 9), 279)
        XCTAssertEqual(CricketChaseGeometry10868.x(0.5, width: 288, inset: 9), 144)
    }

    // MARK: Equal and close endpoints

    func testEqualAndCloseEndpointsKeepBothMarks() {
        XCTAssertEqual(CricketChaseShiftGeometry10868.segment(from: 0.23, to: 0.23), Self.segment(0.23, 0.23))
        XCTAssertEqual(CricketChaseShiftGeometry10868.segment(from: 0.24, to: 0.23), Self.segment(0.23, 0.24))
        let equal = Self.constructedRow(
            id: "constructed:equal", label: "Constructed equal",
            score: .reported(CricketChaseFigure10868(text: "100/1", detail: "Constructed report")),
            recorded: .observed(CricketChaseFigure10868(text: "23%", detail: "Constructed bar")), position: 0.23
        )
        let input = Self.during(rows: [equal])
        XCTAssertEqual(input.baselinePosition, 0.23)
        XCTAssertEqual(input.rowPosition(equal), 0.23)
        XCTAssertEqual(input.rowSegment(equal), Self.segment(0.23, 0.23))
        // Two labels four points apart: the second moves down a line whole.
        XCTAssertEqual(
            CricketChaseShiftGeometry10868.labelPlacements(centers: [100, 104], widths: [40, 40], available: 288, spacing: 8),
            [
                CricketChaseShiftLabelPlacement10868(x: 80, line: 0),
                CricketChaseShiftLabelPlacement10868(x: 84, line: 1),
            ]
        )
    }

    // MARK: Malformed positions

    func testInvalidPositionsDrawNoMarkOrSegmentAndKeepTheOwnersWords() {
        let malformedPositions: [Double] = [.nan, .infinity, -Double.infinity, -0.01, 1.01, 57]
        for bad in malformedPositions {
            XCTAssertNil(CricketChaseShiftGeometry10868.position(bad), "\(bad)")
            let malformed = Self.constructedRow(
                id: Self.checkpoints[0].ownerID, label: "13.0 overs",
                score: .reported(CricketChaseFigure10868(text: "170/3", detail: Self.checkpoints[0].reportDetail)),
                recorded: .observed(CricketChaseFigure10868(text: "57%", detail: Self.checkpoints[0].recordedDetail)),
                position: bad
            )
            let rowInput = Self.during(rows: [malformed, Self.row(Self.checkpoints[1])])
            XCTAssertNil(rowInput.rowPosition(malformed), "\(bad)")
            XCTAssertNil(rowInput.rowSegment(malformed), "\(bad)")
            XCTAssertTrue(rowInput.showsRowNotDrawn(malformed), "\(bad)")
            XCTAssertEqual(rowInput.rowPosition(rowInput.visibleRows[1]), 0.34, "\(bad)")
            XCTAssertTrue(rowInput.accessibilityRow(malformed).contains(
                "Last trade before report: 57%, Kalshi trade close · minute 9:45–9:46 AM PDT, Oct 9. Recorded mark not drawn"
            ), "\(bad)")

            let baselineInput = Self.during(pregamePosition: bad)
            XCTAssertNil(baselineInput.baselinePosition, "\(bad)")
            XCTAssertTrue(baselineInput.showsBaselineNotDrawn, "\(bad)")
            XCTAssertEqual(baselineInput.accessibilityPlot?.hasSuffix(Self.baselineNotDrawn), true, "\(bad)")
            XCTAssertEqual(baselineInput.visibleRows.map { baselineInput.rowPosition($0) }, [0.57, 0.34], "\(bad)")
            XCTAssertEqual(baselineInput.visibleRows.map { baselineInput.rowSegment($0) }, [nil, nil], "\(bad)")
            XCTAssertTrue(baselineInput.accessibilityChances?.hasPrefix("Pregame: 23%, ") == true, "\(bad)")
        }
        XCTAssertNil(CricketChaseShiftGeometry10868.segment(from: .nan, to: 0.5))
        XCTAssertNil(CricketChaseShiftGeometry10868.segment(from: 0.5, to: 1.5))
    }

    // MARK: Missing words

    func testMissingReportAndEmptyProvenanceKeepTheRowUseful() {
        let noReport = Self.constructedRow(
            id: Self.checkpoints[1].ownerID, label: "15.0 overs", score: .unavailable(Self.scoreUnavailable),
            recorded: .observed(CricketChaseFigure10868(text: "34%", detail: Self.checkpoints[1].recordedDetail)),
            position: 0.34
        )
        let emptyWords = Self.constructedRow(
            id: Self.checkpoints[1].ownerID, label: "15.0 overs",
            score: .reported(CricketChaseFigure10868(text: "187/4", detail: "")),
            recorded: .observed(CricketChaseFigure10868(text: "34%", detail: "")),
            position: 0.34
        )
        let emptyLabel = Self.constructedRow(
            id: "constructed:empty-label", label: "",
            score: .reported(CricketChaseFigure10868(text: "187/4", detail: "")),
            recorded: .observed(CricketChaseFigure10868(text: "34%", detail: "")),
            position: 0.34
        )
        let input = Self.during(rows: [noReport, emptyWords, emptyLabel])
        XCTAssertEqual(input.rowPosition(noReport), 0.34)
        XCTAssertEqual(
            input.accessibilityRow(noReport),
            "15.0 overs. Score report unavailable. "
                + "Last trade before report: 34%, Kalshi trade close · minute 9:56–9:57 AM PDT, Oct 9. Pregame: 23%"
        )
        XCTAssertEqual(input.accessibilityRow(emptyWords), "15.0 overs. 187/4. Last trade before report: 34%. Pregame: 23%")
        XCTAssertEqual(input.accessibilityRow(emptyLabel), "187/4. Last trade before report: 34%. Pregame: 23%")
        for spoken in [input.accessibilityRow(emptyWords), input.accessibilityRow(emptyLabel)] {
            XCTAssertFalse(spoken.contains(", ."), spoken)
            XCTAssertFalse(spoken.contains(". ."), spoken)
            XCTAssertFalse(spoken.hasPrefix("."), spoken)
        }
    }

    // MARK: One common scale

    func testOneFixedScaleAcrossRowsPhasesAndCohorts() {
        let duringInput = Self.during()
        let finalInput = Self.finalInput()
        let extreme = Self.constructedRow(
            id: "constructed:extreme", label: "Constructed extreme",
            score: .reported(CricketChaseFigure10868(text: "250/4", detail: "Constructed report")),
            recorded: .observed(CricketChaseFigure10868(text: "100%", detail: "Constructed bar")), position: 1
        )
        let extremeInput = Self.during(rows: [Self.row(Self.checkpoints[0]), extreme])
        let first = Self.row(Self.checkpoints[0])
        // The same reading places identically whatever the other rows hold.
        for input in [duringInput, finalInput, extremeInput] {
            XCTAssertEqual(input.baselinePosition, 0.23)
            XCTAssertEqual(input.rowPosition(first), 0.57)
            XCTAssertEqual(input.rowSegment(first), Self.segment(0.23, 0.57))
            XCTAssertEqual(input.visibleTicks, Self.ticks)
        }
        for width: CGFloat in [288, 343, 361, 700] {
            let fromTwo = CricketChaseGeometry10868.x(duringInput.rowPosition(first) ?? -1, width: width, inset: 9)
            let fromFour = CricketChaseGeometry10868.x(finalInput.rowPosition(first) ?? -1, width: width, inset: 9)
            XCTAssertEqual(fromTwo, fromFour, "\(width)")
        }
    }

    func testNoSegmentJoinsOneRowToTheNext() {
        let input = Self.finalInput()
        for (index, row) in input.visibleRows.enumerated() {
            let value = Self.checkpoints[index].probability
            XCTAssertEqual(input.rowSegment(row), Self.segment(min(0.23, value), max(0.23, value)), row.label)
        }
        // The 15.0 row's segment ends at its own 34%, not at the 13.0 row's 57%.
        XCTAssertEqual(input.rowSegment(input.visibleRows[1])?.upper, 0.34)
        // Without a pregame no row borrows a neighbour as its other end.
        let noBaseline = Self.make(
            phase: .final, title: Self.finalTitle, pregame: .unavailable(Self.pregameUnavailable), pregamePosition: nil,
            comparison: Self.headlineAtFifteen, matchResult: Self.finalMatch, originalResult: nil,
            rows: Self.checkpoints.map(Self.row), detailsRef: nil, notes: []
        )
        XCTAssertEqual(noBaseline.visibleRows.map { noBaseline.rowSegment($0) }, [nil, nil, nil, nil])
        XCTAssertEqual(noBaseline.visibleRows.map { noBaseline.rowPosition($0) }, [0.57, 0.34, 0.89, 0.99])
    }

    // MARK: Owner order, no cap

    func testRowsKeepOwnerOrderWithoutSortFilterOrCap() {
        let values: [Double] = [0.9, 0.1, 0.5, 0.5, 0.02, 0.77]
        let rows = values.enumerated().map { index, value in
            Self.constructedRow(
                id: "constructed:order:\(index)", label: "Constructed checkpoint \(index)",
                score: .reported(CricketChaseFigure10868(text: "\(100 + index)/\(index)", detail: "Constructed report")),
                recorded: .observed(CricketChaseFigure10868(text: "Constructed \(index)", detail: "Constructed bar")),
                position: value
            )
        }
        let input = Self.during(rows: rows)
        XCTAssertEqual(input.visibleRows, rows)
        XCTAssertEqual(input.visibleRows.map { input.rowPosition($0) }, values.map { Optional($0) })
        XCTAssertEqual(input.visibleRows.map(\.label), (0..<6).map { "Constructed checkpoint \($0)" })
    }

    // MARK: Ticks

    func testTicksAreTheOwnersWordsAndInvalidTicksAreNotDrawn() {
        let mixed = Self.ticks + [
            CricketChaseShiftTick10868(value: .nan, words: "Constructed bad"),
            CricketChaseShiftTick10868(value: 1.5, words: "150%"),
        ]
        let input = Self.make(
            phase: .during, title: Self.duringTitle, pregame: Self.pregame, pregamePosition: Self.pregameProbability,
            comparison: Self.headlineAtFifteen, matchResult: .unavailable(Self.notYetKnown), originalResult: nil,
            rows: [Self.row(Self.checkpoints[0])], ticks: mixed, detailsRef: nil, notes: []
        )
        XCTAssertEqual(input.visibleTicks.map(\.words), ["0%", "50%", "100%"])
        XCTAssertEqual(input.accessibilityPlot?.contains("Win chance: 0%, 50%, 100%"), true)
        XCTAssertEqual(input.accessibilityPlot?.contains("150%"), false)
        let bare = Self.make(
            phase: .during, title: Self.duringTitle, pregame: Self.pregame, pregamePosition: Self.pregameProbability,
            comparison: Self.headlineAtFifteen, matchResult: .unavailable(Self.notYetKnown), originalResult: nil,
            rows: [Self.row(Self.checkpoints[0])], ticks: [], detailsRef: nil, notes: []
        )
        XCTAssertTrue(bare.visibleTicks.isEmpty)
        XCTAssertEqual(bare.accessibilityPlot?.hasSuffix(". \(Self.scaleLabel)"), true)
        // Ticks never move a mark.
        XCTAssertEqual(bare.rowPosition(bare.visibleRows[0]), 0.57)
    }

    // MARK: Spoken text

    func testSpokenPlotAndRowAreExact() {
        let input = Self.during()
        XCTAssertEqual(
            input.accessibilityPlot,
            "West Indies recorded win chances versus pregame at each captured score report. "
                + "Hollow mark: Pregame. Filled mark: Last trade before report. Win chance: 0%, 50%, 100%"
        )
        XCTAssertEqual(
            input.accessibilityRow(input.visibleRows[1]),
            "15.0 overs. 187/4, Score report published 9:57 AM PDT, Oct 9 · not the exact ball time. "
                + "Last trade before report: 34%, Kalshi trade close · minute 9:56–9:57 AM PDT, Oct 9. Pregame: 23%"
        )
        XCTAssertEqual(input.accessibilityNotes, "Historical probabilities paired with separately timed score reports.")
    }

    func testScoreAndProbabilityClocksStayInTheirOwnSlots() throws {
        let input = Self.finalInput()
        for (index, row) in input.visibleRows.enumerated() {
            let checkpoint = Self.checkpoints[index]
            let spoken = input.accessibilityRow(row)
            let report = try XCTUnwrap(spoken.range(of: checkpoint.reportDetail), checkpoint.overs)
            let reading = try XCTUnwrap(spoken.range(of: "\(Self.recordedLabel): \(checkpoint.recordedText), \(checkpoint.recordedDetail)"), checkpoint.overs)
            XCTAssertLessThan(report.upperBound, reading.lowerBound, checkpoint.overs)
            XCTAssertNotEqual(checkpoint.reportDetail, checkpoint.recordedDetail, checkpoint.overs)
            guard case .reported(let score) = row.score else { return XCTFail(checkpoint.overs) }
            XCTAssertEqual(score.detail, checkpoint.reportDetail)
            guard case .observed(let recorded) = row.recorded else { return XCTFail(checkpoint.overs) }
            XCTAssertEqual(recorded.detail, checkpoint.recordedDetail)
        }
    }

    // MARK: Identity and actions

    func testDetailsNeedsAnExactReferenceAndACallback() {
        let input = Self.during(detailsRef: Self.ref)
        XCTAssertEqual(input.detailsAction(canOpenDetails: true), .details(Self.ref))
        XCTAssertNil(input.detailsAction(canOpenDetails: false))
        XCTAssertEqual(input.detailsText, "West Indies wins · Details")
        var opened: [CricketChaseRef10868] = []
        input.detailsAction(canOpenDetails: true)?.perform(onDetails: { opened.append($0) })
        XCTAssertEqual(opened, [Self.ref])
        // Retained frames carry no reference, so no Details is invented.
        XCTAssertNil(Self.during().detailsAction(canOpenDetails: true))
        XCTAssertNil(Self.finalInput().detailsAction(canOpenDetails: true))
    }

    func testShiftAccessibilityIdentifiersAreStableAndDistinct() {
        let ids = [
            CricketChaseShiftAccessibilityID10868.header, CricketChaseShiftAccessibilityID10868.chances,
            CricketChaseShiftAccessibilityID10868.plot, CricketChaseShiftAccessibilityID10868.key,
            CricketChaseShiftAccessibilityID10868.notes, CricketChaseShiftAccessibilityID10868.details,
        ]
        XCTAssertEqual(ids, [
            "cricketShift10868.header", "cricketShift10868.chances", "cricketShift10868.plot",
            "cricketShift10868.key", "cricketShift10868.notes", "cricketShift10868.details",
        ])
        let existing = [
            CricketChaseAccessibilityID10868.header, CricketChaseAccessibilityID10868.chances,
            CricketChaseAccessibilityID10868.details, CricketSurvivalAccessibilityID10868.header,
            CricketSurvivalAccessibilityID10868.chances, CricketSurvivalAccessibilityID10868.details,
        ]
        XCTAssertEqual(Set(ids + existing).count, ids.count + existing.count)
        let input = Self.finalInput()
        XCTAssertEqual(input.accessibilityID(at: 0), "cricketShift10868.row.constructed:checkpoint:13.0")
        XCTAssertNil(input.accessibilityID(at: 4))
        // A repeated or empty id adds its position, so rows never share one.
        let repeatedRow = Self.row(Self.checkpoints[0])
        let unnamed = Self.constructedRow(
            id: "", label: "Constructed unnamed",
            score: .unavailable(Self.scoreUnavailable), recorded: .unavailable(Self.noTrade), position: nil
        )
        let repeated = Self.during(rows: [repeatedRow, repeatedRow, unnamed])
        XCTAssertEqual(repeated.accessibilityID(at: 0), "cricketShift10868.row.constructed:checkpoint:13.0.0")
        XCTAssertEqual(repeated.accessibilityID(at: 1), "cricketShift10868.row.constructed:checkpoint:13.0.1")
        XCTAssertEqual(repeated.accessibilityID(at: 2), "cricketShift10868.row..2")
        XCTAssertEqual(repeated.visibleRows.count, 3)
    }

    // MARK: No parsed or derived fields

    func testShiftInputCarriesNoParsedOrDerivedFields() {
        let inputLabels = Mirror(reflecting: Self.finalInput()).children.compactMap { $0.label }
        XCTAssertEqual(inputLabels, [
            "phase", "subject", "eyebrow", "title", "pregameLabel", "pregame", "pregamePosition",
            "comparisonLabel", "comparison", "resultLabel", "matchResult", "originalResultLabel", "originalResult",
            "recordedLabel", "checkpointsLabel", "scale", "rows", "baselineNotDrawn", "rowNotDrawn", "detailsRef", "notes",
        ])
        let rowLabels = Mirror(reflecting: Self.row(Self.checkpoints[0])).children.compactMap { $0.label }
        XCTAssertEqual(rowLabels, ["id", "label", "score", "recorded", "position"])
        let scaleLabels = Mirror(reflecting: CricketChaseShiftScale10868(label: Self.scaleLabel, ticks: Self.ticks))
            .children.compactMap { $0.label }
        XCTAssertEqual(scaleLabels, ["label", "ticks"])
        let all = Set(inputLabels + rowLabels + scaleLabels)
        for forbidden in [
            "overs", "runs", "wickets", "target", "delta", "change", "latest", "baselineIndex", "lower", "upper",
            "domain", "timestamp", "reportedAt", "barEnd", "ticker", "winner", "margin", "selectedCheckpointID",
            "currentness", "probabilityDifference",
        ] {
            XCTAssertFalse(all.contains(forbidden), forbidden)
        }
    }

    // MARK: Long words

    func testLongOwnerWordsStayWholeAndVerbatim() {
        let longLabel = "Thirteenth-over-completion checkpoint (constructed)"
        let longScore = "170/3 — Hetmyer-and-Powell-partnership-continuing"
        let longReport = "Score report published 9:46 AM Pacific Daylight Time, Thursday, October 9, 2026 · not the exact ball time"
        let longBar = "Kalshi trade close · one-minute bar 9:45–9:46 AM Pacific Daylight Time, Thursday, October 9, 2026"
        let row = Self.constructedRow(
            id: "constructed:long", label: longLabel,
            score: .reported(CricketChaseFigure10868(text: longScore, detail: longReport)),
            recorded: .observed(CricketChaseFigure10868(text: "57%", detail: longBar)), position: 0.57
        )
        let input = Self.during(rows: [row])
        let spoken = input.accessibilityRow(row)
        for words in [longLabel, longScore, longReport, longBar] {
            XCTAssertTrue(spoken.contains(words), words)
        }
        XCTAssertEqual(input.visibleRows, [row])
        XCTAssertEqual(CricketChaseGeometry10868.words(longScore).last, "Hetmyer-and-Powell-partnership-continuing")
    }

    // MARK: Measured layout (CONSTRUCTED widths)

    /// A subview that wraps down to `minimum` (its widest word or whole
    /// figure) and is `ideal` wide unconstrained.
    private static func measure(ideal: CGFloat, minimum: CGFloat) -> (CGFloat?) -> CGFloat {
        { proposal in
            guard let proposal else { return ideal }
            return max(minimum, min(ideal, proposal))
        }
    }

    /// Card content widths for 320, 375 and 393 pt screens with 16 pt card
    /// padding each side, and a wide reader.
    private static let contentWidths: [CGFloat] = [288, 343, 361, 700]

    func testHeadlinePairSitsSideBySideUntilAWordOrAccessibilitySizeForcesAStack() {
        for width in Self.contentWidths {
            // "Pregame / 23%" beside "Recorded win chance / 34%".
            XCTAssertEqual(CricketChaseGeometry10868.pairArrangement(
                available: width, spacing: 16, equalColumns: true, forceStack: false,
                first: Self.measure(ideal: 120, minimum: 60),
                second: Self.measure(ideal: 150, minimum: 90)
            ), .sideBySide, "\(width)")
            // The final result wraps between words beside pregame.
            XCTAssertEqual(CricketChaseGeometry10868.pairArrangement(
                available: width, spacing: 16, equalColumns: true, forceStack: false,
                first: Self.measure(ideal: 120, minimum: 60),
                second: Self.measure(ideal: 380, minimum: 85)
            ), .sideBySide, "\(width)")
            // Accessibility sizes always stack.
            XCTAssertEqual(CricketChaseGeometry10868.pairArrangement(
                available: width, spacing: 16, equalColumns: true, forceStack: true,
                first: Self.measure(ideal: 60, minimum: 60),
                second: Self.measure(ideal: 60, minimum: 60)
            ), .stacked, "\(width)")
        }
        // A 150 pt unbreakable word overflows a 136 pt column at 320: stacked;
        // the wide reader keeps it beside.
        XCTAssertEqual(CricketChaseGeometry10868.pairArrangement(
            available: 288, spacing: 16, equalColumns: true, forceStack: false,
            first: Self.measure(ideal: 120, minimum: 60),
            second: Self.measure(ideal: 300, minimum: 150)
        ), .stacked)
        XCTAssertEqual(CricketChaseGeometry10868.pairArrangement(
            available: 700, spacing: 16, equalColumns: true, forceStack: false,
            first: Self.measure(ideal: 120, minimum: 60),
            second: Self.measure(ideal: 300, minimum: 150)
        ), .sideBySide)
    }

    func testLabelBandsKeepTickAndValueWordsInsideAndApartAtEveryWidth() {
        let inset: CGFloat = 9
        for width in Self.contentWidths {
            let centers = [0.0, 0.5, 1.0].map { CricketChaseGeometry10868.x($0, width: width, inset: inset) }
            // Standard type: "0%", "50%", "100%" on one line, ends kept inside.
            let standard = CricketChaseShiftGeometry10868.labelPlacements(
                centers: centers, widths: [22, 30, 36], available: width, spacing: 8
            )
            XCTAssertEqual(standard.map(\.line), [0, 0, 0], "\(width)")
            XCTAssertEqual(standard.first?.x, 0, "\(width)")
            XCTAssertEqual(standard.last?.x, width - 36, "\(width)")
            // A value at 0% or 100% stays inside the band.
            let ends = CricketChaseShiftGeometry10868.labelPlacements(
                centers: [centers[0]], widths: [40], available: width, spacing: 8
            ) + CricketChaseShiftGeometry10868.labelPlacements(
                centers: [centers[2]], widths: [40], available: width, spacing: 8
            )
            XCTAssertEqual(ends.map(\.x), [0, width - 40], "\(width)")
        }
        // Accessibility type at 320: the 100% words would touch 50%, so they
        // take a second line whole instead of shrinking.
        let large = CricketChaseShiftGeometry10868.labelPlacements(
            centers: [9, 144, 279], widths: [70, 90, 100], available: 288, spacing: 8
        )
        XCTAssertEqual(large, [
            CricketChaseShiftLabelPlacement10868(x: 0, line: 0),
            CricketChaseShiftLabelPlacement10868(x: 99, line: 0),
            CricketChaseShiftLabelPlacement10868(x: 188, line: 1),
        ])
        // A label wider than the band leads; nothing is placed outside it.
        XCTAssertEqual(
            CricketChaseShiftGeometry10868.labelPlacements(centers: [144], widths: [400], available: 288, spacing: 8),
            [CricketChaseShiftLabelPlacement10868(x: 0, line: 0)]
        )
        XCTAssertTrue(CricketChaseShiftGeometry10868.labelPlacements(centers: [], widths: [], available: 288, spacing: 8).isEmpty)
    }
}

// MARK: - Label band fit (C1)

/// The band plan the view draws with: each label measured at the width it is
/// actually offered, its wrapped height planned into its line, and the same
/// offer kept for placement. Constructed widths stand in for type metrics;
/// nothing here is rasterised or claims a rendered fit.
extension CricketChaseShift10868Tests {
    /// A constructed label of whole words with fixed widths, wrapped the way
    /// width-respecting Text wraps: between words at the offered width, and a
    /// single word wider than the offer across as many lines as it needs.
    private struct WrappingLabel {
        let words: [CGFloat]
        var space: CGFloat = 4
        let lineHeight: CGFloat

        var natural: CGSize {
            guard !words.isEmpty else { return .zero }
            return CGSize(width: words.reduce(0, +) + space * CGFloat(words.count - 1), height: lineHeight)
        }

        func size(_ offer: CGFloat?) -> CGSize {
            guard let offer, offer < natural.width else { return natural }
            guard offer > 0 else { return CGSize(width: 0, height: lineHeight * CGFloat(words.count)) }
            var widths: [CGFloat] = []
            var current: CGFloat?
            for word in words {
                if let line = current, line + space + word <= offer {
                    current = line + space + word
                    continue
                }
                if let line = current { widths.append(line) }
                if word > offer {
                    let pieces = Int((word / offer).rounded(.up))
                    widths.append(contentsOf: Array(repeating: offer, count: pieces - 1))
                    current = word - offer * CGFloat(pieces - 1)
                } else {
                    current = word
                }
            }
            if let current { widths.append(current) }
            return CGSize(width: widths.max() ?? 0, height: lineHeight * CGFloat(widths.count))
        }
    }

    /// The view's own plan for a band of `labels` at `fractions`, recording
    /// every width each label was asked to measure at. Centres follow the
    /// Layout: a mismatched count has none.
    private static func bandPlan(
        _ labels: [WrappingLabel], fractions: [Double], width: CGFloat, inset: CGFloat = 9
    ) -> (plan: CricketChaseShiftLabelBandPlan10868, asked: [[CGFloat?]]) {
        var asked = Array(repeating: [CGFloat?](), count: labels.count)
        let plan = CricketChaseShiftGeometry10868.labelBand(
            count: labels.count,
            centers: fractions.count == labels.count
                ? fractions.map { CricketChaseGeometry10868.x($0, width: width, inset: inset) }
                : nil,
            available: width, spacing: 8, lineSpacing: 2
        ) { index, offer in
            asked[index].append(offer)
            return labels[index].size(offer)
        }
        return (plan, asked)
    }

    /// Every label sits inside the band at no more than its offer, no two on
    /// a line come within the spacing, and every line starts below the
    /// tallest label of the line above.
    private static func assertFits(
        _ plan: CricketChaseShiftLabelBandPlan10868, width: CGFloat, _ message: String,
        file: StaticString = #filePath, line: UInt = #line
    ) {
        let count = plan.placements.count
        XCTAssertEqual(plan.offers.count, count, message, file: file, line: line)
        XCTAssertEqual(plan.sizes.count, count, message, file: file, line: line)
        for index in 0..<count {
            let placement = plan.placements[index]
            let size = plan.sizes[index]
            XCTAssertLessThanOrEqual(plan.offers[index], width, "\(message) offer \(index)", file: file, line: line)
            XCTAssertLessThanOrEqual(size.width, plan.offers[index], "\(message) width \(index)", file: file, line: line)
            XCTAssertGreaterThanOrEqual(placement.x, 0, "\(message) leading \(index)", file: file, line: line)
            XCTAssertLessThanOrEqual(placement.x + size.width, width, "\(message) trailing \(index)", file: file, line: line)
            let bottom = plan.lineOffsets[placement.line] + size.height
            let limit = placement.line + 1 < plan.lineOffsets.count
                ? plan.lineOffsets[placement.line + 1] - 2
                : plan.height
            XCTAssertLessThanOrEqual(bottom, limit, "\(message) bottom \(index)", file: file, line: line)
            for other in 0..<index where plan.placements[other].line == placement.line {
                let a = placement.x...(placement.x + size.width)
                let b = plan.placements[other].x...(plan.placements[other].x + plan.sizes[other].width)
                XCTAssertTrue(
                    a.lowerBound >= b.upperBound + 8 || b.lowerBound >= a.upperBound + 8,
                    "\(message) apart \(other)/\(index)", file: file, line: line
                )
            }
        }
    }

    private static let tick0 = WrappingLabel(words: [22], lineHeight: 16)
    private static let tick50 = WrappingLabel(words: [30], lineHeight: 16)
    private static let tick100 = WrappingLabel(words: [36], lineHeight: 16)
    /// 96 + 120 + 80 + 92 with three 4 pt spaces: a natural 400 pt line,
    /// which wraps at 288 to 220 pt wide over two 24 pt lines.
    private static let wide400 = WrappingLabel(words: [96, 120, 80, 92], lineHeight: 24)

    func testWideLabelIsMeasuredAtTheOfferedWidthAndItsWrappedHeightSetsTheBand() {
        XCTAssertEqual(Self.wide400.natural, CGSize(width: 400, height: 24))
        let (plan, asked) = Self.bandPlan([Self.wide400], fractions: [0.5], width: 288)
        // Measured naturally, then at the band's width — the offer it is placed with.
        XCTAssertEqual(asked, [[nil, 288]])
        XCTAssertEqual(plan.offers, [288])
        XCTAssertEqual(plan.sizes, [CGSize(width: 220, height: 48)])
        // Still centred on its mark (x = 144), now that it really is 220 wide.
        XCTAssertEqual(plan.placements, [CricketChaseShiftLabelPlacement10868(x: 34, line: 0)])
        XCTAssertEqual(plan.lineOffsets, [0])
        // The wrapped two lines, never the natural single line's 24.
        XCTAssertEqual(plan.height, 48)
        Self.assertFits(plan, width: 288, "wide400@288")

        // One unbreakable 400 pt word takes the whole band over two lines.
        let word = WrappingLabel(words: [400], lineHeight: 24)
        let single = Self.bandPlan([word], fractions: [0.5], width: 288).plan
        XCTAssertEqual(single.offers, [288])
        XCTAssertEqual(single.sizes, [CGSize(width: 288, height: 48)])
        XCTAssertEqual(single.placements, [CricketChaseShiftLabelPlacement10868(x: 0, line: 0)])
        XCTAssertEqual(single.height, 48)
        Self.assertFits(single, width: 288, "word400@288")
    }

    func testANeighbourMovedBelowAWrappedLabelStartsBelowItsWrappedHeight() {
        // 0% | the wrapped 400 pt words at 50% | 100%. The 100% words would
        // touch the wrapped label, so they take the next line — which must
        // start below BOTH wrapped lines (48 + 2), not the natural 24 + 2.
        let (plan, _) = Self.bandPlan([Self.tick0, Self.wide400, Self.tick100], fractions: [0, 0.5, 1], width: 288)
        XCTAssertEqual(plan.placements, [
            CricketChaseShiftLabelPlacement10868(x: 0, line: 0),
            CricketChaseShiftLabelPlacement10868(x: 34, line: 0),
            CricketChaseShiftLabelPlacement10868(x: 252, line: 1),
        ])
        XCTAssertEqual(plan.offers, [22, 288, 36])
        XCTAssertEqual(plan.lineOffsets, [0, 50])
        XCTAssertEqual(plan.height, 66)
        Self.assertFits(plan, width: 288, "neighbour@288")

        // Two wrapped labels on close marks: the second line starts below
        // the first's wrapped height, and the band holds both.
        let (pair, _) = Self.bandPlan([Self.wide400, Self.wide400], fractions: [0.4, 0.6], width: 288)
        XCTAssertEqual(pair.sizes, [CGSize(width: 220, height: 48), CGSize(width: 220, height: 48)])
        XCTAssertEqual(pair.placements.map(\.line), [0, 1])
        XCTAssertEqual(pair.lineOffsets, [0, 50])
        XCTAssertEqual(pair.height, 98)
        Self.assertFits(pair, width: 288, "pair@288")
    }

    func testOrdinaryTickAndValueLabelsKeepTheirNaturalSizeAndPlacementAtEveryWidth() {
        // 320 / 375 / 393 phones and a wide reader.
        for width in Self.contentWidths {
            let fractions = [0.0, 0.5, 1.0]
            let (plan, asked) = Self.bandPlan([Self.tick0, Self.tick50, Self.tick100], fractions: fractions, width: width)
            let centers = fractions.map { CricketChaseGeometry10868.x($0, width: width, inset: 9) }
            XCTAssertEqual(
                plan.placements,
                CricketChaseShiftGeometry10868.labelPlacements(
                    centers: centers, widths: [22, 30, 36], available: width, spacing: 8
                ),
                "\(width)"
            )
            XCTAssertEqual(asked, [[nil, 22], [nil, 30], [nil, 36]], "\(width)")
            XCTAssertEqual(plan.offers, [22, 30, 36], "\(width)")
            XCTAssertEqual(plan.sizes, [CGSize(width: 22, height: 16), CGSize(width: 30, height: 16), CGSize(width: 36, height: 16)], "\(width)")
            XCTAssertEqual(plan.placements.map(\.line), [0, 0, 0], "\(width)")
            XCTAssertEqual(plan.placements.first?.x, 0, "\(width)")
            XCTAssertEqual(plan.placements.last?.x, width - 36, "\(width)")
            XCTAssertEqual(plan.height, 16, "\(width)")
            Self.assertFits(plan, width: width, "ticks@\(width)")

            // A row's recorded figure at the ends, the archived checkpoints
            // and pregame: natural size, centred and kept inside.
            let value = WrappingLabel(words: [40], lineHeight: 23)
            for position in [0.0, 0.23, 0.34, 0.57, 0.89, 0.99, 1.0] {
                let one = Self.bandPlan([value], fractions: [position], width: width).plan
                let center = CricketChaseGeometry10868.x(position, width: width, inset: 9)
                XCTAssertEqual(one.offers, [40], "\(width) \(position)")
                XCTAssertEqual(one.sizes, [CGSize(width: 40, height: 23)], "\(width) \(position)")
                XCTAssertEqual(one.placements, [
                    CricketChaseShiftLabelPlacement10868(x: min(max(0, center - 20), width - 40), line: 0),
                ], "\(width) \(position)")
                XCTAssertEqual(one.height, 23, "\(width) \(position)")
            }
            XCTAssertEqual(Self.bandPlan([value], fractions: [0], width: width).plan.placements.first?.x, 0, "\(width)")
            XCTAssertEqual(Self.bandPlan([value], fractions: [1], width: width).plan.placements.first?.x, width - 40, "\(width)")
        }
    }

    func testAccessibilityTypeWrapsOnlyWhatTheBandCannotHoldAndPlansItsHeight() {
        // Accessibility type at 320: whole labels move a line, as before, and
        // the band is planned at their full 60 pt height.
        let large = [
            WrappingLabel(words: [70], lineHeight: 60),
            WrappingLabel(words: [90], lineHeight: 60),
            WrappingLabel(words: [100], lineHeight: 60),
        ]
        let (ax, _) = Self.bandPlan(large, fractions: [0, 0.5, 1], width: 288)
        XCTAssertEqual(ax.placements, [
            CricketChaseShiftLabelPlacement10868(x: 0, line: 0),
            CricketChaseShiftLabelPlacement10868(x: 99, line: 0),
            CricketChaseShiftLabelPlacement10868(x: 188, line: 1),
        ])
        XCTAssertEqual(ax.offers, [70, 90, 100])
        XCTAssertEqual(ax.lineOffsets, [0, 62])
        XCTAssertEqual(ax.height, 122)
        Self.assertFits(ax, width: 288, "ax@288")

        // Two accessibility-size owner words, 150 + 14 + 170 = 334 pt: wrapped
        // at 320, one line from 375 up. Every word stays; nothing shrinks.
        let words = WrappingLabel(words: [150, 170], space: 14, lineHeight: 60)
        for width in Self.contentWidths {
            let (plan, asked) = Self.bandPlan([Self.tick0, words], fractions: [0, 0.5], width: width)
            let offer = min(334, width)
            XCTAssertEqual(asked[1], [nil, offer], "\(width)")
            XCTAssertEqual(plan.offers[1], offer, "\(width)")
            if width < 334 {
                XCTAssertEqual(plan.sizes[1], CGSize(width: 170, height: 120), "\(width)")
            } else {
                XCTAssertEqual(plan.sizes[1], CGSize(width: 334, height: 60), "\(width)")
            }
            let tallest = plan.placements.indices
                .filter { plan.placements[$0].line == plan.placements.last?.line }
                .map { plan.sizes[$0].height }
                .max() ?? 0
            XCTAssertEqual(plan.height, (plan.lineOffsets.last ?? 0) + tallest, "\(width)")
            XCTAssertGreaterThanOrEqual(plan.height, plan.sizes[1].height, "\(width)")
            Self.assertFits(plan, width: width, "axwords@\(width)")
        }
    }

    func testEveryBandPlanKeepsLabelsInsideApartAndBelowTheLineAbove() {
        let sets: [[WrappingLabel]] = [
            [Self.tick0, Self.tick50, Self.tick100],
            [Self.wide400],
            [Self.tick0, Self.wide400, Self.tick100],
            [Self.wide400, Self.wide400, Self.wide400],
            [WrappingLabel(words: [400], lineHeight: 24), Self.tick100],
            [WrappingLabel(words: [70], lineHeight: 60), WrappingLabel(words: [150, 170], space: 14, lineHeight: 60), WrappingLabel(words: [100], lineHeight: 60)],
        ]
        let positions: [Double] = [0, 0.02, 0.23, 0.5, 0.98, 1]
        for width in Self.contentWidths {
            for labels in sets {
                for start in positions {
                    let fractions = labels.indices.map { positions[(positions.firstIndex(of: start)! + $0) % positions.count] }
                    let plan = Self.bandPlan(labels, fractions: fractions, width: width).plan
                    Self.assertFits(plan, width: width, "\(width) \(labels.count) \(start)")
                }
            }
        }
    }

    func testBandWithoutTrustworthyPositionsLeadsEveryLabelOnItsOwnLine() {
        // Two labels, one position: no x is trusted, every label leads and
        // the wrapped one still plans its full height.
        let (plan, _) = Self.bandPlan([Self.wide400, Self.tick50], fractions: [0.5], width: 288)
        XCTAssertEqual(plan.placements, [
            CricketChaseShiftLabelPlacement10868(x: 0, line: 0),
            CricketChaseShiftLabelPlacement10868(x: 0, line: 1),
        ])
        XCTAssertEqual(plan.lineOffsets, [0, 50])
        XCTAssertEqual(plan.height, 66)
        Self.assertFits(plan, width: 288, "mismatch@288")

        let empty = Self.bandPlan([], fractions: [], width: 288).plan
        XCTAssertEqual(empty, CricketChaseShiftLabelBandPlan10868(placements: [], offers: [], sizes: [], lineOffsets: [], height: 0))
    }
}
