import SwiftUI
import XCTest
@testable import Bain_Luck

/// The movement track's decisions, read through the unchanged adapter on the
/// producer's route harness plus explicit comparison mutations. These are
/// constructed controls, not captured production-game data, and they are not
/// render, focus or VoiceOver evidence for a mounted view. The 11% → 16% / +5
/// case is a RETAINED VISUAL NUMERIC CONTROL from the Astros–White Sox
/// reference, not a typed production capture.
@MainActor
final class MarketChanceMovementTrack10238Tests: XCTestCase {
    private typealias Track = MarketChanceMovementTrack10238
    private let countKey = "q:count|points|game|full_game|ge:211"
    private let homeSpreadKey = "q:handicap|points|home|full_game|-3.5"

    private func fixture() throws -> EventQuestionMatrix {
        let url = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
            .appendingPathComponent("Fixtures")
            .appendingPathComponent("game-markets-10238-question-matrix.route-harness.json")
        let body = try XCTUnwrap(JSONSerialization.jsonObject(with: Data(contentsOf: url)) as? [String: Any])
        let matrix = try XCTUnwrap(body["game_question_matrix"] as? [String: Any])
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(EventQuestionMatrix.self, from: JSONSerialization.data(withJSONObject: matrix))
    }

    private func row(_ matrix: EventQuestionMatrix, _ key: String) throws -> EventQuestionMatrixAdapter.Row {
        try XCTUnwrap(EventQuestionMatrixAdapter.rows(in: matrix, scope: .game).first { $0.id.questionKey == key })
    }

    private func detail(_ selection: QuestionMatrixSelection, _ matrix: EventQuestionMatrix) throws -> EventQuestionMatrixAdapter.Detail {
        guard case .available(let detail) = EventQuestionMatrixAdapter.detail(for: selection, in: matrix) else {
            XCTFail("exact served selection must resolve")
            throw NSError(domain: "Track10238", code: 1)
        }
        return detail
    }

    private func comparison(_ baseline: Double, _ latest: Double, points: Double,
                            baselineAt: String = "2026-10-03T10:00:00Z",
                            latestAt: String = "2026-10-03T11:00:00Z") -> QuestionMatrixComparison {
        QuestionMatrixComparison(state: "comparable", reason: nil,
            baseline: QuestionMatrixBaseline(probability: baseline, observedAt: baselineAt, basis: "pregame_pin"),
            latest: QuestionMatrixLatest(probability: latest, observedAt: latestAt), deltaPoints: points)
    }

    /// The fixture with one option's published value and comparison replaced
    /// — everything else, including its source evidence, as served.
    private func mutated(_ key: String, value: Double? = 0.52, state: String = "quoted",
                         result: QuestionMatrixResult? = nil,
                         comparison: QuestionMatrixComparison?) throws -> EventQuestionMatrix {
        var matrix = try fixture()
        let q = try XCTUnwrap(matrix.questions.firstIndex { $0.questionKey == key })
        let o = matrix.questions[q].options[0]
        matrix.questions[q].options[0] = QuestionMatrixOption(
            optionKey: o.optionKey, label: o.label, side: o.side,
            marketIds: o.marketIds, contributorOutcomeIds: o.contributorOutcomeIds,
            published: QuestionMatrixPublished(value: value, valueState: state, basis: o.published.basis,
                source: o.published.source, observedAt: o.published.observedAt),
            sourceEvidence: o.sourceEvidence, result: result, comparison: comparison)
        return matrix
    }

    private func resolvedDetail(_ key: String, in matrix: EventQuestionMatrix) throws -> EventQuestionMatrixAdapter.Detail {
        try detail(try row(matrix, key).options[0].selection, matrix)
    }

    private func resolved(_ key: String, in matrix: EventQuestionMatrix) throws -> Track.Resolved {
        try XCTUnwrap(Track.resolve(try resolvedDetail(key, in: matrix)))
    }

    // MARK: - Binding to the served comparison

    func testHarnessComparisonBindsServedBaselineLatestPointsAndClocks() throws {
        let r = try resolved(homeSpreadKey, in: try fixture())
        XCTAssertEqual(r.title, "Boston Celtics -3.5 points")
        XCTAssertEqual(r.period, "Game")
        XCTAssertEqual(r.outcome, "Boston Celtics -3.5")
        XCTAssertEqual(r.pregame.probability, 0.4)
        XCTAssertEqual(r.later.probability, 0.54)
        XCTAssertEqual(r.pregame.text, "40%")
        XCTAssertEqual(r.later.text, "54%")
        XCTAssertEqual(r.change, Track.Change(direction: .up, magnitude: "14.0"))
        XCTAssertEqual(r.pregame.observedAt, "2026-05-17T22:00:00+00:00")
        XCTAssertEqual(r.later.observedAt, "2026-05-17T23:27:00+00:00")
        XCTAssertEqual(r.domain, .whole, "54% needs the 0–100% scale")
    }

    func testPublishedFiftyTwoNeverStandsInForLatestSixtyOrServedTwentyPoints() throws {
        // R5: published 52%, comparison.latest 60%, baseline 40%, served +20.
        let matrix = try mutated(countKey, value: 0.52, comparison: comparison(0.4, 0.6, points: 20))
        let shown = try resolvedDetail(countKey, in: matrix)
        XCTAssertEqual(shown.option.value, .quoted(0.52), "the published value is still the host's")
        let r = try XCTUnwrap(Track.resolve(shown))
        XCTAssertEqual(r.pregame.text, "40%")
        XCTAssertEqual(r.later.text, "60%")
        XCTAssertEqual(r.later.probability, 0.6)
        XCTAssertEqual(r.change.text, "Up 20.0 percentage points since pregame")
        // Time-free strings only: a reader-local clock may legitimately hold "12".
        for text in [r.pregame.text, r.later.text, r.change.text, r.title, r.outcome] {
            XCTAssertFalse(text.contains("52"), "published value leaked into \(text)")
            XCTAssertFalse(text.contains("12"), "published-derived delta leaked into \(text)")
        }
        // The later mark sits at the comparison's 60%, not the published 52%.
        let domain = try XCTUnwrap(r.domain)
        let width: CGFloat = 360
        let mark = Track.TrackGeometry.x(r.later.probability, domain: domain, width: width)
        XCTAssertEqual(mark, Track.TrackGeometry.x(0.6, domain: domain, width: width), accuracy: 1e-9)
        XCTAssertNotEqual(mark, Track.TrackGeometry.x(0.52, domain: domain, width: width), accuracy: 1e-6)
    }

    func testServedPointsAreNeverRecomputedFromEitherProbability() throws {
        // 0.4 → 0.6 is 20 points by arithmetic; the server's 19.9 is what prints.
        let matrix = try mutated(countKey, comparison: comparison(0.4, 0.6, points: 19.9))
        XCTAssertEqual(try resolved(countKey, in: matrix).change.magnitude, "19.9")
        // 0.115 → 0.155 would print 12% → 16% (4 apart); the served 4.0 stays 4.0,
        // never a difference of the printed percents.
        let rounded = try mutated(countKey, comparison: comparison(0.115, 0.155, points: 4))
        XCTAssertEqual(try resolved(countKey, in: rounded).change.magnitude, "4.0")
    }

    // MARK: - Declining

    func testNoComparisonMeansNoTrack() throws {
        let matrix = try fixture()
        // Served `unavailable` (leg_is_complement): the host keeps its renderer.
        let count = try resolvedDetail(countKey, in: matrix)
        XCTAssertNil(count.comparison)
        XCTAssertNil(Track.resolve(count))
    }

    func testRawSourceSelectionNeverGainsATrack() throws {
        let matrix = try mutated(homeSpreadKey, value: 0.54, comparison: comparison(0.4, 0.54, points: 14))
        let option = try XCTUnwrap(matrix.question(homeSpreadKey)?.options.first)
        let outcome = try XCTUnwrap(option.sourceEvidence?.first?.outcomeId)
        let raw = QuestionMatrixSelection(scope: .game, questionKey: homeSpreadKey,
                                          optionKey: option.optionKey, outcomeId: outcome)
        XCTAssertNil(Track.resolve(try detail(raw, matrix)))
    }

    func testSettledRefusedAndUnpricedValuesNeverGainATrackOrTerminalJourney() throws {
        let served = comparison(0.4, 0.6, points: 20)
        let cases: [(Double?, String, QuestionMatrixResult?)] = [
            (1, "result", QuestionMatrixResult(state: "won", evidenceKind: "resolved")),
            (0, "result", QuestionMatrixResult(state: "lost", evidenceKind: "resolved")),
            (0.6, "refused", nil),
            (nil, "unpriced", nil),
        ]
        for (value, state, result) in cases {
            let matrix = try mutated(countKey, value: value, state: state, result: result, comparison: served)
            XCTAssertNil(Track.resolve(try resolvedDetail(countKey, in: matrix)), "\(state) drew a track")
        }
    }

    // MARK: - Percents and movement

    func testExactEndpointsStayQuotesAndNearEndpointsKeepTheSharedGuards() throws {
        XCTAssertEqual(Track.chanceText(0), "0%")
        XCTAssertEqual(Track.chanceText(1), "100%")
        XCTAssertEqual(Track.chanceText(0.004), formatProbability(0.004))
        XCTAssertEqual(Track.chanceText(0.996), formatProbability(0.996))
        XCTAssertEqual(Track.chanceText(0.115), formatProbability(0.115), "whole percents, the shared formatter's")
        let matrix = try mutated(countKey, comparison: comparison(0, 1, points: 100))
        let r = try resolved(countKey, in: matrix)
        XCTAssertEqual([r.pregame.text, r.later.text], ["0%", "100%"])
        XCTAssertEqual(r.domain, .whole)
    }

    func testMovementWordsCarryTheServedSignAndNeverPrintZeroForAMove() {
        XCTAssertEqual(Track.change(points: 5).text, "Up 5.0 percentage points since pregame")
        XCTAssertEqual(Track.change(points: -11.5).text, "Down 11.5 percentage points since pregame")
        XCTAssertEqual(Track.change(points: 0).text, "No change since pregame")
        XCTAssertEqual(Track.change(points: 0).direction, .none)
        XCTAssertEqual(Track.change(points: 0.04).text, "Up <0.1 percentage points since pregame")
        XCTAssertEqual(Track.change(points: -0.04).text, "Down <0.1 percentage points since pregame")
        XCTAssertEqual(Track.change(points: 0.1).magnitude, deltaPointsNumber(0.1))
        for points in [0.0001, -0.0001, 0.04, -0.049] {
            let change = Track.change(points: points)
            XCTAssertFalse(change.text.contains("0.0"))
            XCTAssertFalse(change.text.contains("No change"))
            XCTAssertNotEqual(change.direction, .none)
        }
    }

    // MARK: - Clocks

    func testEachChanceKeepsItsOwnSuppliedClock() throws {
        let matrix = try mutated(countKey, comparison: comparison(0.4, 0.6, points: 20,
            baselineAt: "2026-10-03T10:00:00Z", latestAt: "2026-10-03T11:27:00Z"))
        let r = try resolved(countKey, in: matrix)
        XCTAssertEqual(r.pregame.observedAt, "2026-10-03T10:00:00Z")
        XCTAssertEqual(r.later.observedAt, "2026-10-03T11:27:00Z")
        XCTAssertEqual(r.pregame.localTime, SourceAge.preciseStamp("2026-10-03T10:00:00Z"))
        XCTAssertEqual(r.later.localTime, SourceAge.preciseStamp("2026-10-03T11:27:00Z"))
        XCTAssertNotEqual(r.pregame.localTime, r.later.localTime, "no implied simultaneity")
        XCTAssertTrue(r.spokenSummary.contains(try XCTUnwrap(r.pregame.localTime)))
        XCTAssertTrue(r.spokenSummary.contains(try XCTUnwrap(r.later.localTime)))
    }

    func testAnUnreadableClockSaysSoAndNeverBorrowsTheOther() throws {
        let matrix = try mutated(countKey, comparison: comparison(0.4, 0.6, points: 20,
            baselineAt: "2026-10-03T10:00:00Z", latestAt: "stamp"))
        let r = try resolved(countKey, in: matrix)
        XCTAssertNil(r.later.localTime)
        XCTAssertEqual(r.later.timeText, Track.timeUnavailableText)
        XCTAssertEqual(r.later.observedAt, "stamp")
        XCTAssertNotNil(r.pregame.localTime)
        XCTAssertTrue(r.spokenSummary.contains("Later chance 60%, Time unavailable"))
    }

    // MARK: - Details

    func testDetailsHandsTheOwnerExactlyTheResolvedSelection() throws {
        let matrix = try mutated(countKey, comparison: comparison(0.4, 0.6, points: 20))
        let shown = try resolvedDetail(countKey, in: matrix)
        let r = try XCTUnwrap(Track.resolve(shown))
        XCTAssertEqual(r.selection, shown.option.selection)
        var received: [QuestionMatrixSelection] = []
        Track.performDetails(r, onDetails: { received.append($0) })
        XCTAssertEqual(received, [shown.option.selection])
        XCTAssertEqual(received.first?.scope, .game)
        XCTAssertEqual(received.first?.questionKey, countKey)
        XCTAssertNil(received.first?.outcomeId, "never a source selection")
        XCTAssertEqual(Track.detailsSpokenLabel(r), "Details, 211+ points, Under 210.5")
    }

    func testAbsentCallbackIsANoOpAndTheViewDefaultsToNoControl() throws {
        let matrix = try mutated(countKey, comparison: comparison(0.4, 0.6, points: 20))
        let shown = try resolvedDetail(countKey, in: matrix)
        Track.performDetails(try XCTUnwrap(Track.resolve(shown)), onDetails: nil)
        let view = Track(detail: shown, pregameColor: .blue, laterColor: .green)
        XCTAssertNil(view.onDetails, "no callback, no control")
        XCTAssertTrue(view.showsHeading)
    }

    // MARK: - Scale

    func testScaleIsTheSmallestZeroBasedRangeHoldingBothValues() {
        let d = Track.TrackDomain.self
        XCTAssertEqual(d.smallest(containing: 0.11, 0.16), .low)
        XCTAssertEqual(d.smallest(containing: 0, 0), .low)
        XCTAssertEqual(d.smallest(containing: 0.25, 0.1), .low, "an exact top is inside")
        XCTAssertEqual(d.smallest(containing: 0.2501, 0.1), .half)
        // Either value can be the larger one: a fall from 45% needs the half scale.
        XCTAssertEqual(d.smallest(containing: 0.45, 0.05), .half)
        XCTAssertEqual(d.smallest(containing: 0.05, 0.45), .half)
        XCTAssertEqual(d.smallest(containing: 0.5, 0.5), .half)
        XCTAssertEqual(d.smallest(containing: 0.4, 0.6), .whole)
        XCTAssertEqual(d.smallest(containing: 1, 0), .whole)
    }

    func testMalformedValuesGetNoScaleRatherThanAValuePulledToZero() throws {
        let d = Track.TrackDomain.self
        for bad in [Double.nan, .infinity, -.infinity, -0.01, 1.01] {
            XCTAssertNil(d.smallest(containing: 0.2, bad), "\(bad) was fitted to a scale")
        }
        // A Detail constructed directly (the adapter refuses this comparison):
        // the values are carried unclipped and no track position is invented.
        let served = try resolvedDetail(homeSpreadKey, in: try fixture())
        let malformed = EventQuestionMatrixAdapter.Detail(
            row: served.row, option: served.option, sources: served.sources,
            selectedSource: served.selectedSource,
            comparison: EventQuestionMatrixAdapter.Comparison(
                baseline: 0.2, baselineObservedAt: "2026-10-03T10:00:00Z",
                latest: 1.2, latestObservedAt: "2026-10-03T11:00:00Z", points: 100))
        let r = try XCTUnwrap(Track.resolve(malformed))
        XCTAssertNil(r.domain)
        XCTAssertEqual(r.pregame.probability, 0.2)
        XCTAssertEqual(r.later.probability, 1.2, "never clipped to 1 or pulled to 0")
    }

    func testTicksDescribeEachScaleAndCompactKeepsBothEnds() {
        XCTAssertEqual(Track.TrackDomain.low.tickPercents, [0, 5, 10, 15, 20, 25])
        XCTAssertEqual(Track.TrackDomain.half.tickPercents, [0, 10, 20, 30, 40, 50])
        XCTAssertEqual(Track.TrackDomain.whole.tickPercents, [0, 20, 40, 60, 80, 100])
        XCTAssertEqual(Track.TrackDomain.tickLabel(0), "0%", "a scale label, not the <1% quote guard")
        XCTAssertEqual(Track.TrackDomain.tickLabel(25), "25%")
        let g = Track.TrackGeometry.self
        XCTAssertEqual(g.labelledTickPercents(.low, width: 360, compact: false), [0, 5, 10, 15, 20, 25])
        XCTAssertEqual(g.labelledTickPercents(.low, width: 360, compact: true), [0, 25])
        XCTAssertEqual(g.labelledTickPercents(.half, width: 200, compact: false), [0, 50])
        XCTAssertEqual(g.labelledTickPercents(.whole, width: 200, compact: true), [0, 100])
    }

    // MARK: - Geometry

    func testRetainedElevenToSixteenControlPlacesBothMarksOnTheQuarterScale() throws {
        // RETAINED VISUAL NUMERIC CONTROL (Astros–White Sox reference: 11% before,
        // 16% recorded, +5 points). The clocks are this file's constructed ones.
        let matrix = try mutated(countKey, comparison: comparison(0.11, 0.16, points: 5))
        let r = try resolved(countKey, in: matrix)
        XCTAssertEqual([r.pregame.text, r.later.text], ["11%", "16%"])
        XCTAssertEqual(r.change.text, "Up 5.0 percentage points since pregame")
        let domain = try XCTUnwrap(r.domain)
        XCTAssertEqual(domain, .low, "11 → 16 is never drawn on 0–100")
        let g = Track.TrackGeometry.self
        let width = g.maxWidth
        let usable = width - 2 * g.inset
        XCTAssertEqual(g.x(0.11, domain: domain, width: width), g.inset + 0.44 * usable, accuracy: 1e-9)
        XCTAssertEqual(g.x(0.16, domain: domain, width: width), g.inset + 0.64 * usable, accuracy: 1e-9)
        let span = try XCTUnwrap(g.span(from: r.pregame.probability, to: r.later.probability,
                                        domain: domain, width: width))
        XCTAssertEqual(span.lowerBound, g.x(0.11, domain: domain, width: width), accuracy: 1e-9)
        XCTAssertEqual(span.upperBound, g.x(0.16, domain: domain, width: width), accuracy: 1e-9)
    }

    func testEndsSitInsideThePlotAndRiseAndFallPlaceTheRightMarks() throws {
        let g = Track.TrackGeometry.self
        let width: CGFloat = 320
        for domain in Track.TrackDomain.allCases {
            let zero = g.x(0, domain: domain, width: width)
            let top = g.x(domain.upper, domain: domain, width: width)
            XCTAssertEqual(zero, g.inset, accuracy: 1e-9)
            XCTAssertEqual(top, width - g.inset, accuracy: 1e-9)
            XCTAssertGreaterThanOrEqual(zero - g.pregameMarkDiameter / 2, 0, "the hollow ring fits at 0")
            XCTAssertLessThanOrEqual(top + g.pregameMarkDiameter / 2, width, "the hollow ring fits at the top")
        }
        XCTAssertEqual(g.maxWidth, 360)

        let rise = try resolved(countKey, in: try mutated(countKey, comparison: comparison(0.3, 0.45, points: 15)))
        let fall = try resolved(countKey, in: try mutated(countKey, comparison: comparison(0.45, 0.3, points: -15)))
        let domain = try XCTUnwrap(rise.domain)
        XCTAssertEqual(fall.domain, domain)
        XCTAssertLessThan(g.x(rise.pregame.probability, domain: domain, width: width),
                          g.x(rise.later.probability, domain: domain, width: width), "a rise puts later to the right")
        XCTAssertGreaterThan(g.x(fall.pregame.probability, domain: domain, width: width),
                             g.x(fall.later.probability, domain: domain, width: width), "a fall puts later to the left")
        XCTAssertEqual(rise.change.direction, .up)
        XCTAssertEqual(fall.change.direction, .down)
        // The emphasised stretch covers the same two coordinates either way.
        XCTAssertEqual(g.span(from: 0.3, to: 0.45, domain: domain, width: width),
                       g.span(from: 0.45, to: 0.3, domain: domain, width: width))
    }

    func testIdenticalChancesShareOneCoordinateWithNoInventedStretch() throws {
        let matrix = try mutated(countKey, comparison: comparison(0.2, 0.2, points: 0))
        let r = try resolved(countKey, in: matrix)
        let domain = try XCTUnwrap(r.domain)
        let g = Track.TrackGeometry.self
        XCTAssertEqual(g.x(r.pregame.probability, domain: domain, width: 300),
                       g.x(r.later.probability, domain: domain, width: 300), "same place, no displacement")
        XCTAssertNil(g.span(from: r.pregame.probability, to: r.later.probability, domain: domain, width: 300))
        XCTAssertGreaterThan(g.pregameMarkDiameter, g.laterMarkDiameter, "the dot stays visible inside the ring")
        XCTAssertEqual(r.readings.map(\.label), [Track.pregameLabel, Track.laterLabel])
        XCTAssertEqual(r.change.text, "No change since pregame")
    }

    // MARK: - Arrangement and words

    func testAccessibilitySizesStackAndLargeTextLabelsOnlyTheEnds() {
        XCTAssertEqual(Track.arrangement(typeSize: .large), .init(stacksReadings: false, compactAxis: false))
        XCTAssertEqual(Track.arrangement(typeSize: .xLarge), .init(stacksReadings: false, compactAxis: false))
        XCTAssertEqual(Track.arrangement(typeSize: .xxLarge), .init(stacksReadings: false, compactAxis: true))
        XCTAssertEqual(Track.arrangement(typeSize: .accessibility1), .init(stacksReadings: true, compactAxis: true))
        XCTAssertEqual(Track.arrangement(typeSize: .accessibility5), .init(stacksReadings: true, compactAxis: true))
    }

    func testSpokenSummaryNamesMarketOutcomeBothChancesAndTheChange() throws {
        let matrix = try mutated(countKey, comparison: comparison(0.4, 0.6, points: 20))
        let r = try resolved(countKey, in: matrix)
        XCTAssertTrue(r.spokenSummary.hasPrefix("211+ points. Game. Under 210.5. Pregame chance 40%, "))
        XCTAssertTrue(r.spokenSummary.contains("Later chance 60%, "))
        XCTAssertTrue(r.spokenSummary.hasSuffix("Up 20.0 percentage points since pregame"))
    }

    func testReaderWordsNeverSayQuestionSavedOrCurrent() throws {
        let matrix = try mutated(countKey, comparison: comparison(0.4, 0.6, points: 20))
        let r = try resolved(countKey, in: matrix)
        let words = [r.pregame.label, r.pregame.text, r.later.label, r.later.text, r.change.text,
                     r.spokenSummary, Track.disclosureTitle, Track.detailsTitle, Track.timeUnavailableText]
        for text in words {
            for word in ["question", "saved", "current"] {
                XCTAssertFalse(text.lowercased().contains(word), "\(word) in \(text)")
            }
        }
    }
}
