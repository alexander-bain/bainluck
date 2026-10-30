import SwiftUI
import XCTest
@testable import Bain_Luck

/// The dial's decisions, read through the unchanged adapter on the producer's
/// route harness plus explicit comparison mutations. These are constructed
/// controls, not captured production-game data, and they are not render,
/// focus or VoiceOver evidence for a mounted view.
@MainActor
final class MarketChanceComparisonDial10238Tests: XCTestCase {
    private typealias Dial = MarketChanceComparisonDial10238
    private let countKey = "q:count|points|game|full_game|ge:211"
    private let homeSpreadKey = "q:handicap|points|home|full_game|-3.5"
    private let headToHeadKey = "m:104"
    private let threeWayKey = "m:108"

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
            throw NSError(domain: "Dial10238", code: 1)
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
    private func mutated(_ key: String, option index: Int = 0, value: Double? = 0.52, state: String = "quoted",
                         result: QuestionMatrixResult? = nil,
                         comparison: QuestionMatrixComparison?) throws -> EventQuestionMatrix {
        var matrix = try fixture()
        let q = try XCTUnwrap(matrix.questions.firstIndex { $0.questionKey == key })
        let o = matrix.questions[q].options[index]
        matrix.questions[q].options[index] = QuestionMatrixOption(
            optionKey: o.optionKey, label: o.label, side: o.side,
            marketIds: o.marketIds, contributorOutcomeIds: o.contributorOutcomeIds,
            published: QuestionMatrixPublished(value: value, valueState: state, basis: o.published.basis,
                source: o.published.source, observedAt: o.published.observedAt),
            sourceEvidence: o.sourceEvidence, result: result, comparison: comparison)
        return matrix
    }

    private func resolved(_ key: String, option index: Int = 0, in matrix: EventQuestionMatrix,
                          canSelect: Bool = false) throws -> Dial.Resolved {
        let selection = try row(matrix, key).options[index].selection
        return try XCTUnwrap(Dial.resolve(try detail(selection, matrix), canSelect: canSelect))
    }

    private func visibleAndSpoken(_ r: Dial.Resolved) -> [String] {
        [r.title, r.outcome, r.pregame.label, r.pregame.text, r.later.label, r.later.text,
         r.change.text, Dial.Change.qualifier, r.change.spoken, r.spokenSummary, Dial.disclosureTitle]
            + (r.period.map { [$0] } ?? [])
    }

    // MARK: - Binding to the served comparison

    func testHarnessComparisonBindsServedBaselineLatestPointsAndClocks() throws {
        let matrix = try fixture()
        let r = try resolved(homeSpreadKey, in: matrix)
        XCTAssertEqual(r.title, "Boston Celtics -3.5 points")
        XCTAssertEqual(r.period, "Game")
        XCTAssertEqual(r.outcome, "Boston Celtics -3.5")
        XCTAssertEqual(r.pregame.probability, 0.4)
        XCTAssertEqual(r.later.probability, 0.54)
        XCTAssertEqual(r.pregame.text, "40%")
        XCTAssertEqual(r.later.text, "54%")
        XCTAssertEqual(r.change, Dial.Change(direction: .up, magnitude: "14.0"))
        XCTAssertEqual(r.pregame.observedAt, "2026-05-17T22:00:00+00:00")
        XCTAssertEqual(r.later.observedAt, "2026-05-17T23:27:00+00:00")
    }

    func testPublishedFiftyTwoNeverStandsInForLatestSixtyOrServedTwentyPoints() throws {
        // R5: published 52%, comparison.latest 60%, baseline 40%, served +20.
        let matrix = try mutated(countKey, value: 0.52, comparison: comparison(0.4, 0.6, points: 20))
        let selection = try row(matrix, countKey).options[0].selection
        let shown = try detail(selection, matrix)
        XCTAssertEqual(shown.option.value, .quoted(0.52), "the published value is still the host's")
        let r = try XCTUnwrap(Dial.resolve(shown, canSelect: false))
        XCTAssertEqual(r.pregame.text, "40%")
        XCTAssertEqual(r.later.text, "60%")
        XCTAssertEqual(r.later.probability, 0.6)
        XCTAssertEqual(r.change.text, "Up 20.0 points")
        // Time-free strings only: a reader-local clock may legitimately hold "12".
        for text in [r.pregame.text, r.later.text, r.change.text, r.change.spoken, r.title, r.outcome] {
            XCTAssertFalse(text.contains("52"), "published value leaked into \(text)")
            XCTAssertFalse(text.contains("12"), "published-derived delta leaked into \(text)")
        }
        // The later mark sits at the comparison's 60%, not the published 52%.
        let mark = Dial.DialGeometry.point(r.later.probability)
        XCTAssertEqual(mark.x, Dial.DialGeometry.point(0.6).x, accuracy: 1e-9)
        XCTAssertNotEqual(mark.x, Dial.DialGeometry.point(0.52).x, accuracy: 1e-6)
    }

    func testServedPointsAreNeverRecomputedFromEitherProbability() throws {
        // 0.4 → 0.6 is 20 points by arithmetic; the server's 19.9 is what prints.
        let matrix = try mutated(countKey, comparison: comparison(0.4, 0.6, points: 19.9))
        XCTAssertEqual(try resolved(countKey, in: matrix).change.magnitude, "19.9")
    }

    // MARK: - Percents and movement

    func testExactEndpointsStayQuotesAndNearEndpointsKeepTheSharedGuards() throws {
        XCTAssertEqual(Dial.chanceText(0), "0%")
        XCTAssertEqual(Dial.chanceText(1), "100%")
        XCTAssertEqual(Dial.chanceText(0.004), formatProbability(0.004))
        XCTAssertEqual(Dial.chanceText(0.996), formatProbability(0.996))
        XCTAssertEqual(Dial.chanceText(0.715), formatProbability(0.715), "whole percents, the shared formatter's")
        let matrix = try mutated(countKey, comparison: comparison(0, 1, points: 100))
        let r = try resolved(countKey, in: matrix)
        XCTAssertEqual([r.pregame.text, r.later.text], ["0%", "100%"])
    }

    func testMovementWordsCarryTheServedSignAndNeverPrintZeroForAMove() {
        XCTAssertEqual(Dial.change(points: 11.5).text, "Up 11.5 points")
        XCTAssertEqual(Dial.change(points: -11.5).text, "Down 11.5 points")
        XCTAssertEqual(Dial.change(points: 0).text, "No change")
        XCTAssertEqual(Dial.change(points: 0).direction, .none)
        XCTAssertEqual(Dial.change(points: 0.04).text, "Up <0.1 points")
        XCTAssertEqual(Dial.change(points: -0.04).text, "Down <0.1 points")
        XCTAssertEqual(Dial.change(points: 0.1).magnitude, deltaPointsNumber(0.1))
        XCTAssertEqual(Dial.change(points: -20).spoken, "Down 20.0 percentage points since pregame")
        for points in [0.0001, -0.0001, 0.04, -0.049] {
            XCTAssertFalse(Dial.change(points: points).text.contains("0.0"))
            XCTAssertNotEqual(Dial.change(points: points).direction, .none)
        }
    }

    // MARK: - Declining

    func testNoComparisonMeansNoDial() throws {
        let matrix = try fixture()
        // Served `unavailable` (leg_is_complement): the host keeps its renderer.
        let count = try detail(try row(matrix, countKey).options[0].selection, matrix)
        XCTAssertNil(count.comparison)
        XCTAssertNil(Dial.resolve(count, canSelect: true))
    }

    func testRawSourceSelectionNeverGainsADial() throws {
        let matrix = try mutated(homeSpreadKey, value: 0.54, comparison: comparison(0.4, 0.54, points: 14))
        let option = try XCTUnwrap(matrix.question(homeSpreadKey)?.options.first)
        let outcome = try XCTUnwrap(option.sourceEvidence?.first?.outcomeId)
        let raw = QuestionMatrixSelection(scope: .game, questionKey: homeSpreadKey,
                                          optionKey: option.optionKey, outcomeId: outcome)
        XCTAssertNil(Dial.resolve(try detail(raw, matrix), canSelect: true))
    }

    func testSettledRefusedAndUnpricedValuesNeverGainADialOrTerminalJourney() throws {
        let served = comparison(0.4, 0.6, points: 20)
        let cases: [(Double?, String, QuestionMatrixResult?)] = [
            (1, "result", QuestionMatrixResult(state: "won", evidenceKind: "resolved")),
            (0, "result", QuestionMatrixResult(state: "lost", evidenceKind: "resolved")),
            (0.6, "refused", nil),
            (nil, "unpriced", nil),
        ]
        for (value, state, result) in cases {
            let matrix = try mutated(countKey, value: value, state: state, result: result, comparison: served)
            let d = try detail(try row(matrix, countKey).options[0].selection, matrix)
            XCTAssertNil(Dial.resolve(d, canSelect: true), "\(state) drew a dial")
        }
    }

    func testMissingSelectionLeavesNothingToDraw() throws {
        let matrix = try fixture()
        let gone = QuestionMatrixSelection(scope: .game, questionKey: homeSpreadKey, optionKey: "o:missing")
        XCTAssertEqual(EventQuestionMatrixAdapter.detail(for: gone, in: matrix), .unavailable(.optionGone))
    }

    // MARK: - Side controls

    func testTwoOptionCompleteRowOffersBothServedOptionsVerbatimOnlyWithACallback() throws {
        let matrix = try mutated(headToHeadKey, value: 0.55, comparison: comparison(0.5, 0.55, points: 5))
        let served = try row(matrix, headToHeadKey)
        let r = try resolved(headToHeadKey, in: matrix, canSelect: true)
        let controls = try XCTUnwrap(r.controls)
        XCTAssertEqual(controls.map(\.label), served.options.map(\.label))
        XCTAssertEqual(controls.map(\.label), ["Scheffler", "McIlroy"])
        XCTAssertEqual(controls.map(\.selection), served.options.map(\.selection))
        XCTAssertEqual(controls.map(\.isSelected), [true, false])
        XCTAssertEqual(controls[1].spokenLabel, "McIlroy, Head-to-Head: Scheffler vs McIlroy")
        XCTAssertNil(try resolved(headToHeadKey, in: matrix, canSelect: false).controls,
                     "no callback, no controls")
    }

    func testRowsOutsideTheTwoOptionShapeGetNoControls() throws {
        // Three served options.
        let three = try mutated(threeWayKey, value: 0.52, comparison: comparison(0.4, 0.52, points: 12))
        XCTAssertNil(try resolved(threeWayKey, in: three, canSelect: true).controls)
        // One served option on a row the server cannot vouch for.
        let spread = try mutated(homeSpreadKey, value: 0.54, comparison: comparison(0.4, 0.54, points: 14))
        XCTAssertNil(try resolved(homeSpreadKey, in: spread, canSelect: true).controls)

        let base = try mutated(headToHeadKey, value: 0.55, comparison: comparison(0.5, 0.55, points: 5))
        let q = try XCTUnwrap(base.questions.firstIndex { $0.questionKey == headToHeadKey })
        var explicitlyIncomplete = base
        explicitlyIncomplete.questions[q].complete = false
        XCTAssertNil(try resolved(headToHeadKey, in: explicitlyIncomplete, canSelect: true).controls)
        var missingLeg = base
        missingLeg.questions[q].missingOptions = [
            QuestionMatrixMissingOption(optionKey: "o:99", outcomeId: 99, label: "Tie", side: "draw", valueState: "unpriced")
        ]
        XCTAssertNil(try resolved(headToHeadKey, in: missingLeg, canSelect: true).controls)
        var vouched = base
        vouched.questions[q].complete = true
        XCTAssertEqual(try resolved(headToHeadKey, in: vouched, canSelect: true).controls?.count, 2)
    }

    func testPerformHandsTheOwnerOnlyTheExactUnselectedSibling() throws {
        let matrix = try mutated(headToHeadKey, value: 0.55, comparison: comparison(0.5, 0.55, points: 5))
        let controls = try XCTUnwrap(try resolved(headToHeadKey, in: matrix, canSelect: true).controls)
        var received: [QuestionMatrixSelection] = []
        Dial.perform(controls[0], onSelect: { received.append($0) })
        XCTAssertTrue(received.isEmpty, "the selected side is not re-sent")
        Dial.perform(controls[1], onSelect: { received.append($0) })
        let sibling = try row(matrix, headToHeadKey).options[1].selection
        XCTAssertEqual(received, [sibling])
        XCTAssertEqual(received.first?.scope, .game)
        XCTAssertEqual(received.first?.questionKey, headToHeadKey)
        XCTAssertNil(received.first?.outcomeId, "never a source selection")
        Dial.perform(controls[1], onSelect: nil)
    }

    func testSelectedSideIsMatchedByFullIdentityNotByLabelOrKeyAlone() throws {
        let matrix = try mutated(headToHeadKey, value: 0.55, comparison: comparison(0.5, 0.55, points: 5))
        let resolvedDetail = try detail(try row(matrix, headToHeadKey).options[0].selection, matrix)
        let o = resolvedDetail.option
        // Same question and option keys and label, other scope: not this row's option.
        let otherScope = EventQuestionMatrixAdapter.Option(
            selection: QuestionMatrixSelection(scope: .series, questionKey: o.selection.questionKey,
                                               optionKey: o.selection.optionKey),
            label: o.label, side: o.side, value: o.value, observedAt: o.observedAt,
            basis: o.basis, result: o.result)
        let crossed = EventQuestionMatrixAdapter.Detail(row: resolvedDetail.row, option: otherScope,
            sources: resolvedDetail.sources, selectedSource: nil, comparison: resolvedDetail.comparison)
        XCTAssertNil(Dial.controls(for: crossed, canSelect: true))
        XCTAssertNotNil(Dial.controls(for: resolvedDetail, canSelect: true))
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
        XCTAssertEqual(r.later.timeText, Dial.timeUnavailableText)
        XCTAssertEqual(r.later.observedAt, "stamp")
        XCTAssertNotNil(r.pregame.localTime)
    }

    // MARK: - Geometry

    func testZeroIsLeftHalfIsTopAndOneIsRight() {
        let g = Dial.DialGeometry.self
        let zero = g.point(0), half = g.point(0.5), one = g.point(1)
        XCTAssertEqual(zero.x, g.center.x - g.radius, accuracy: 1e-9)
        XCTAssertEqual(zero.y, g.center.y, accuracy: 1e-9)
        XCTAssertEqual(half.x, g.center.x, accuracy: 1e-9)
        XCTAssertEqual(half.y, g.center.y - g.radius, accuracy: 1e-9)
        XCTAssertEqual(one.x, g.center.x + g.radius, accuracy: 1e-9)
        XCTAssertEqual(one.y, g.center.y, accuracy: 1e-9)
        // Monotonic left to right; every mark on or above the baseline.
        let xs = stride(from: 0.0, through: 1.0, by: 0.1).map { g.point($0).x }
        XCTAssertEqual(xs, xs.sorted())
        for p in stride(from: 0.0, through: 1.0, by: 0.1) {
            XCTAssertLessThanOrEqual(g.point(p).y, g.center.y + 1e-9)
        }
        XCTAssertEqual(g.maxWidth, 240)
    }

    func testSegmentRunsFromPregameToLaterInTheRightDirectionAndIsAbsentWhenEqual() throws {
        let g = Dial.DialGeometry.self
        let rise = try XCTUnwrap(g.segment(from: 0.4, to: 0.6))
        XCTAssertEqual(rise.start, 252, accuracy: 1e-9)
        XCTAssertEqual(rise.end, 288, accuracy: 1e-9)
        XCTAssertFalse(rise.clockwise)
        let fall = try XCTUnwrap(g.segment(from: 0.6, to: 0.4))
        XCTAssertEqual(fall.start, 288, accuracy: 1e-9)
        XCTAssertEqual(fall.end, 252, accuracy: 1e-9)
        XCTAssertTrue(fall.clockwise)
        XCTAssertNil(g.segment(from: 0.5, to: 0.5), "no fabricated separation")
        // Identical served chances still resolve to two named readings.
        let same = try mutated(countKey, comparison: comparison(0.5, 0.5, points: 0))
        let r = try resolved(countKey, in: same)
        XCTAssertEqual(r.readings.map(\.label), [Dial.pregameLabel, Dial.laterLabel])
        XCTAssertEqual(r.change.text, "No change")
    }

    // MARK: - Arrangement and words

    func testAccessibilitySizesStackAndLargerSizesMoveTheChangeOutOfTheDial() {
        XCTAssertEqual(Dial.arrangement(typeSize: .large), .init(stacksReadings: false, changeInsideDial: true))
        XCTAssertEqual(Dial.arrangement(typeSize: .xLarge), .init(stacksReadings: false, changeInsideDial: true))
        XCTAssertEqual(Dial.arrangement(typeSize: .xxLarge), .init(stacksReadings: false, changeInsideDial: false))
        XCTAssertEqual(Dial.arrangement(typeSize: .accessibility1), .init(stacksReadings: true, changeInsideDial: false))
        XCTAssertEqual(Dial.arrangement(typeSize: .accessibility5), .init(stacksReadings: true, changeInsideDial: false))
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
        for text in visibleAndSpoken(r) where text != r.title && text != r.outcome {
            for word in ["question", "saved", "current"] {
                XCTAssertFalse(text.lowercased().contains(word), "\(word) in \(text)")
            }
        }
    }
}
