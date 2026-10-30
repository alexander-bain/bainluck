import SwiftUI
import XCTest
@testable import Bain_Luck

/// #11284 — the strikeout card's comparison (design ref #10868,
/// `native-baseball-paired-home-runs/strikeout-first`). The component only
/// draws `MLBMilestoneCard11284` with the host's selection, so these tests
/// read its choices, comparison words, plotted points, count domain and
/// callbacks against the card the real builder produces.
///
/// FIXTURES, AND WHAT EACH ONE IS (the same file `MLBFinalReader11284Tests`
/// pins):
/// - `event-15321836-game-markets-11284-mlb-final.20260930.json` — the
///   RETAINED captured Astros–White Sox final. Hunter Brown's ladder is
///   6+/7+/8+/9+/10+/12+ with no 12+ pregame mark, and 10237.v1 does not type
///   strikeouts, so as captured the official final is UNAVAILABLE. Its legacy
///   untyped `actual: 2` is never a final.
/// Cases that need another state are CONSTRUCTED: the reader tests' typed
/// 7+ question + official final of 2 (said where it happens), or a card
/// built field by field. Neither is claimed as observed data.
@MainActor
final class MLBStrikeoutComparison11284Tests: XCTestCase {
    private static let fixtures = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
        .appendingPathComponent("Fixtures")
    private static let capturedMarkets = "event-15321836-game-markets-11284-mlb-final.20260930.json"
    private static let sevenRowID = "Hunter Brown: Strikeouts O/U 6.5-Over"

    // MARK: - Helpers (the reader tests' fixture pattern)

    private func object(_ name: String) throws -> [String: Any] {
        let data = try Data(contentsOf: Self.fixtures.appendingPathComponent(name))
        return try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
    }

    private func decode<T: Decodable>(_ type: T.Type, _ dict: [String: Any]) throws -> T {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(type, from: JSONSerialization.data(withJSONObject: dict))
    }

    private func strikeouts(_ markets: [String: Any]) throws -> MLBMilestoneCard11284 {
        let cards = MLBFinalDeck11284.cards(MLBFinalDeckInput11284(
            eventID: 15321836, sportKey: "baseball_mlb", status: "completed",
            homeTeam: "Houston Astros", awayTeam: "Chicago White Sox",
            homeScore: 3, awayScore: 7,
            gameMarkets: try decode(GameMarketsResponse.self, markets),
            relatedFutures: nil))
        var dealt: MLBMilestoneCard11284?
        for case .strikeouts(let card) in cards { dealt = card }
        return try XCTUnwrap(dealt, "no strikeout card dealt")
    }

    /// RETAINED, unedited.
    private func captured() throws -> MLBMilestoneCard11284 {
        try strikeouts(object(Self.capturedMarkets))
    }

    /// CONSTRUCTED CONTROL: the capture plus a typed question for Brown's 7+
    /// Over contributor (239004630) and an official final of 2, exactly as
    /// `MLBFinalReader11284Tests` types it. No producer types this today.
    private func typedFinalOfTwo() throws -> MLBMilestoneCard11284 {
        var body = try object(Self.capturedMarkets)
        var after = try XCTUnwrap(body["after_player_props"] as? [String: Any])
        let subject: [String: Any] = ["key": "hunter brown", "label": "Hunter Brown", "kind": "player"]
        var questions = try XCTUnwrap(after["questions"] as? [[String: Any]])
        questions.append([
            "question_key": "s:hunter brown|pitching_strikeouts|full_game|ge:7|over",
            "actual_key": "s:hunter brown|pitching_strikeouts|full_game",
            "subject": subject, "stat_key": "pitching_strikeouts", "period_key": "full_game",
            "predicate": ["kind": "count_at_least", "count": 7, "side": "over", "label": "7+"],
            "expectation": ["state": "unavailable", "reason": "constructed", "contributors": [], "excluded": []],
            "comparison": ["state": "below"],
            "contributor_outcome_ids": [239004630],
        ])
        var actuals = try XCTUnwrap(after["actuals"] as? [[String: Any]])
        actuals.append([
            "actual_key": "s:hunter brown|pitching_strikeouts|full_game", "subject": subject,
            "stat_key": "pitching_strikeouts", "period_key": "full_game", "state": "final", "value": 2,
        ])
        after["questions"] = questions
        after["actuals"] = actuals
        body["after_player_props"] = after
        return try strikeouts(body)
    }

    /// CONSTRUCTED target. The original's ID is deliberately not the row ID,
    /// so a test can tell which one reached a callback.
    private func target(_ rowID: String, threshold: Double, milestone: Int,
                        pregame: Double?) -> MLBMilestoneCard11284.Target {
        MLBMilestoneCard11284.Target(
            rowID: rowID, threshold: threshold, milestone: milestone, pregame: pregame,
            original: MLBOriginal11284(id: "mlb-o:1:target:\(rowID)", title: rowID, sections: []))
    }

    /// CONSTRUCTED card, field by field.
    private func constructed(player: String = "Constructed Pitcher",
                             targets: [MLBMilestoneCard11284.Target]? = nil,
                             final: Int?) -> MLBMilestoneCard11284 {
        MLBMilestoneCard11284(
            eventID: 1, player: player, stat: "Strikeouts", source: "kalshi", side: .home,
            targets: targets ?? [
                target("c-5", threshold: 4.5, milestone: 5, pregame: 0.62),
                target("c-7", threshold: 7, milestone: 7, pregame: 0.31),
                target("c-9", threshold: 8.5, milestone: 9, pregame: nil),
            ],
            finalCount: final)
    }

    private func view(_ card: MLBMilestoneCard11284, selected: String?, expanded: Bool = false,
                      onSelect: @escaping (String) -> Void = { _ in },
                      onDetails: ((String) -> Void)? = nil) -> MLBStrikeoutComparison11284 {
        MLBStrikeoutComparison11284(card: card, selectedRowID: selected, color: .blue, expanded: expanded,
                                    onSelect: onSelect, onDetails: onDetails)
    }

    private func allWords(_ card: MLBMilestoneCard11284, selected: String?) -> [String] {
        let c = MLBStrikeoutComparison11284.comparison(card, selectedRowID: selected)
        return [c.targetHeading, c.targetSpoken, c.pregameText, c.pregameSpoken, c.finalText, c.finalSpoken,
                c.againstText, c.againstSpoken].compactMap { $0 }
            + MLBStrikeoutComparison11284.choices(card, selectedRowID: selected).flatMap { [$0.label, $0.spoken] }
            + [MLBStrikeoutComparison11284.chartSpoken(card, selectedRowID: selected)]
    }

    // MARK: - Targets, order and selection

    func testTheRetainedCaptureOffersAllSixTargetsInTheCardsOrderWithTheFinalUnavailable() throws {
        let card = try captured()
        let choices = MLBStrikeoutComparison11284.choices(card, selectedRowID: Self.sevenRowID)
        XCTAssertEqual(choices.map(\.id), card.targets.map(\.rowID), "IDs and order unchanged")
        XCTAssertEqual(choices.map(\.label), ["6+", "7+", "8+", "9+", "10+", "12+"],
                       "every target reachable, not the reference's five")
        XCTAssertEqual(choices.map(\.spoken).first, "6 or more strikeouts")
        let comparison = MLBStrikeoutComparison11284.comparison(card, selectedRowID: Self.sevenRowID)
        XCTAssertNil(comparison.finalText, "the legacy untyped 2 is never the official final")
        XCTAssertEqual(comparison.finalSpoken, "Official final unavailable")
        XCTAssertNil(comparison.againstText, "no performance without a typed final")
        XCTAssertNil(MLBStrikeoutComparison11284.shownFinal(card))
    }

    func testAnExactSelectionMarksOnlyThatTargetAndReadsItsOwnChance() throws {
        let card = try captured()
        let choices = MLBStrikeoutComparison11284.choices(card, selectedRowID: Self.sevenRowID)
        XCTAssertEqual(choices.filter(\.isSelected).map(\.id), [Self.sevenRowID])
        let comparison = MLBStrikeoutComparison11284.comparison(card, selectedRowID: Self.sevenRowID)
        XCTAssertEqual(comparison.targetHeading, "7+ strikeouts")
        XCTAssertEqual(comparison.pregameText, formatProbability(0.445), "the shipping formatter, not 44.5%")
        XCTAssertEqual(comparison.pregameSpoken, "Pregame chance, \(formatProbability(0.445))")
        let points = MLBStrikeoutComparison11284.points(card, selectedRowID: Self.sevenRowID)
        XCTAssertEqual(points.filter(\.isSelected).map(\.id), [Self.sevenRowID])
    }

    func testTargetAndDetailsCallbacksSendTheirIDsUnchanged() {
        let card = constructed(final: 6)
        var selected: [String] = []
        var details: [String] = []
        let comparisonView = view(card, selected: "c-7", onSelect: { selected.append($0) },
                                  onDetails: { details.append($0) })
        for choice in MLBStrikeoutComparison11284.choices(card, selectedRowID: "c-7") {
            comparisonView.select(choice)
        }
        XCTAssertEqual(selected, ["c-5", "c-7", "c-9"], "target.rowID, in order, unchanged")
        XCTAssertTrue(comparisonView.detailsAvailable)
        comparisonView.details()
        XCTAssertEqual(details, ["mlb-o:1:target:c-7"], "the selected original's ID, never the row ID")
    }

    func testANilSelectionStaysUnselectedWithNoDefaultAndNoDetails() throws {
        let card = try captured()
        XCTAssertEqual(card.defaultIndex, 1, "non-vacuous: the card has a default the host may choose")
        XCTAssertEqual(MLBStrikeoutComparison11284.selection(card, selectedRowID: nil), .unselected)
        XCTAssertFalse(MLBStrikeoutComparison11284.choices(card, selectedRowID: nil).contains(where: \.isSelected))
        XCTAssertFalse(MLBStrikeoutComparison11284.points(card, selectedRowID: nil).contains(where: \.isSelected))
        let comparison = MLBStrikeoutComparison11284.comparison(card, selectedRowID: nil)
        XCTAssertEqual(comparison.targetHeading, "Choose a target")
        XCTAssertNil(comparison.pregameText, "never the default target's chance")
        XCTAssertNil(comparison.detailsID)
        var details: [String] = []
        let unselected = view(card, selected: nil, onDetails: { details.append($0) })
        XCTAssertFalse(unselected.detailsAvailable)
        unselected.details()
        XCTAssertEqual(details, [], "no selection, no details action")
    }

    func testAnIDTheCardNoLongerCarriesIsUnavailableNotAnotherTarget() throws {
        let card = try captured()
        XCTAssertEqual(MLBStrikeoutComparison11284.selection(card, selectedRowID: "gone"), .unavailable)
        let comparison = MLBStrikeoutComparison11284.comparison(card, selectedRowID: "gone")
        XCTAssertEqual(comparison.targetHeading, "This target is unavailable in this update")
        XCTAssertNil(comparison.pregameText)
        XCTAssertNil(comparison.detailsID)
        XCTAssertFalse(MLBStrikeoutComparison11284.choices(card, selectedRowID: "gone").contains(where: \.isSelected))
        XCTAssertEqual(MLBStrikeoutComparison11284.choices(card, selectedRowID: "gone").count, 6,
                       "nothing is withdrawn")
        XCTAssertFalse(view(card, selected: "gone", onDetails: { _ in }).detailsAvailable)
    }

    func testDetailsNeedBothACallbackAndASelectedTarget() throws {
        let card = try captured()
        XCTAssertFalse(view(card, selected: Self.sevenRowID).detailsAvailable, "no callback, no button")
        XCTAssertTrue(view(card, selected: Self.sevenRowID, onDetails: { _ in }).detailsAvailable)
    }

    // MARK: - The missing baseline and admitted milestones

    func testTwelvePlusWithoutABaselineStaysReachableButDrawsNoPoint() throws {
        let card = try captured()
        let twelve = try XCTUnwrap(card.targets.last)
        XCTAssertEqual(twelve.milestone, 12)
        XCTAssertNil(twelve.pregame, "non-vacuous: the retained 12+ has no pregame mark")
        let comparison = MLBStrikeoutComparison11284.comparison(card, selectedRowID: twelve.rowID)
        XCTAssertEqual(comparison.targetHeading, "12+ strikeouts")
        XCTAssertNil(comparison.pregameText, "legible unavailable words, never a figure")
        XCTAssertEqual(comparison.pregameSpoken, "Pregame chance unavailable")
        XCTAssertEqual(comparison.detailsID, twelve.original.id, "its originals stay reachable")
        let points = MLBStrikeoutComparison11284.points(card, selectedRowID: twelve.rowID)
        XCTAssertEqual(points.map(\.count), [6, 7, 8, 9, 10], "no dot, and nothing interpolated, for 12+")
        XCTAssertEqual(points.map(\.chance), [0.57, 0.445, 0.275, 0.11, 0.07])
        XCTAssertTrue(MLBStrikeoutComparison11284.axisLabels(card, selectedRowID: nil).texts.contains("12+"),
                      "its position on the count axis stays")
    }

    func testAHalfLineIsDrawnAtTheAdmittedMilestoneNotTheRawThreshold() throws {
        let card = try captured()
        XCTAssertEqual(card.targets.map(\.threshold), [5.5, 6.5, 7.5, 8.5, 9.5, 11.5],
                       "non-vacuous: the venue serves half lines")
        let axis = MLBStrikeoutComparison11284.axisLabels(card, selectedRowID: nil)
        XCTAssertEqual(axis.values, [0, 6, 7, 8, 9, 10, 12])
        XCTAssertFalse(axis.values.contains(6.5))
        XCTAssertEqual(MLBStrikeoutComparison11284.points(card, selectedRowID: nil).map(\.count),
                       card.targets.filter { $0.pregame != nil }.map { Double($0.milestone) })
        XCTAssertEqual(MLBStrikeoutComparison11284.choices(card, selectedRowID: nil)[1].label, "7+",
                       "O/U 6.5 reads as the admitted 7+")
    }

    func testTheAxisKeepsZeroThenEveryTargetAndTheSelectedLabelFirst() throws {
        let card = try captured()
        let axis = MLBStrikeoutComparison11284.axisLabels(card, selectedRowID: Self.sevenRowID)
        XCTAssertEqual(axis.texts, ["0", "6+", "7+", "8+", "9+", "10+", "12+"])
        XCTAssertEqual(axis.keep, 2, "7+ is index 1 of the targets, after zero")
        XCTAssertNil(MLBStrikeoutComparison11284.axisLabels(card, selectedRowID: nil).keep)
    }

    // MARK: - The count domain

    func testTheCountDomainNeverMovesWithTheSelection() throws {
        let card = try captured()
        let expected = MLBStrikeoutComparison11284.domain(card)
        XCTAssertEqual(expected, 0...13, "zero, the 12+ milestone, one count of room")
        for selected in [nil, "gone"] + card.targets.map { $0.rowID as String? } {
            XCTAssertEqual(MLBStrikeoutComparison11284.domain(card), expected, "\(selected ?? "nil")")
            XCTAssertEqual(MLBStrikeoutComparison11284.axisLabels(card, selectedRowID: selected).values,
                           MLBStrikeoutComparison11284.axisLabels(card, selectedRowID: nil).values)
        }
    }

    func testTheDomainIncludesZeroAndAFinalOutsideTheLadder() {
        XCTAssertEqual(MLBStrikeoutComparison11284.domain(constructed(final: 14)), 0...15,
                       "a final above every milestone stays on the axis")
        XCTAssertEqual(MLBStrikeoutComparison11284.domain(constructed(final: 0)), 0...10,
                       "a final of zero sits on the axis at its start")
        XCTAssertEqual(MLBStrikeoutComparison11284.domain(constructed(final: nil)), 0...10)
    }

    // MARK: - The official final

    func testNilZeroAndPositiveFinalsReadDifferently() {
        let missing = MLBStrikeoutComparison11284.comparison(constructed(final: nil), selectedRowID: "c-7")
        XCTAssertNil(missing.finalText)
        XCTAssertEqual(missing.finalSpoken, "Official final unavailable")
        XCTAssertNil(missing.againstText)

        let zero = MLBStrikeoutComparison11284.comparison(constructed(final: 0), selectedRowID: "c-7")
        XCTAssertEqual(zero.finalText, "0", "a typed zero stays 0")
        XCTAssertEqual(zero.finalSpoken, "Official final, 0 strikeouts")
        XCTAssertEqual(zero.againstText, "Finished 7 short")

        let six = MLBStrikeoutComparison11284.comparison(constructed(final: 6), selectedRowID: "c-7")
        XCTAssertEqual(six.finalText, "6")
        XCTAssertEqual(six.againstSpoken, "Against this target, Finished 1 short")
        XCTAssertEqual(MLBStrikeoutComparison11284.finalRuleLabel(6), "Final 6")
    }

    func testTheConstructedTypedFinalOfTwoIsTheOneOfficialCount() throws {
        // CONSTRUCTED CONTROL (see `typedFinalOfTwo`), not observed data.
        let card = try typedFinalOfTwo()
        XCTAssertEqual(card.finalCount, 2)
        let comparison = MLBStrikeoutComparison11284.comparison(card, selectedRowID: Self.sevenRowID)
        XCTAssertEqual(comparison.finalText, "2")
        XCTAssertEqual(comparison.againstText, "Finished 5 short")
        XCTAssertEqual(MLBStrikeoutComparison11284.domain(card), 0...13, "2 is already inside 0…12")
        XCTAssertEqual(allWords(card, selected: Self.sevenRowID).filter { $0.contains("Official final, 2") }.count, 2,
                       "said once by the comparison and once by the chart summary, never as a second heading")
    }

    func testTheFinalIsTheSameWhicheverTargetIsSelected() throws {
        let card = try typedFinalOfTwo()
        let finals = Set(card.targets.map {
            MLBStrikeoutComparison11284.comparison(card, selectedRowID: $0.rowID).finalText
        })
        XCTAssertEqual(finals, ["2"])
        XCTAssertEqual(MLBStrikeoutComparison11284.comparison(card, selectedRowID: nil).finalText, "2",
                       "the final does not need a target")
    }

    // MARK: - Performance, not settlement; no current probability

    func testAgainstThisTargetIsPerformanceNeverTheVenuesGrade() throws {
        let card = try typedFinalOfTwo()
        let seven = try XCTUnwrap(card.targets.first { $0.rowID == Self.sevenRowID })
        let venue = seven.original.sections.flatMap(\.fields).filter { $0.label == "Venue result" }.map(\.value)
        XCTAssertEqual(venue, ["Pending", "Pending"], "non-vacuous: the venue has not graded the line")
        let comparison = MLBStrikeoutComparison11284.comparison(card, selectedRowID: Self.sevenRowID)
        XCTAssertEqual(comparison.againstText,
                       MLBMilestoneResult11284.result(actual: 2, milestone: 7), "the existing helper's words")
        for word in allWords(card, selected: Self.sevenRowID) {
            for grade in ["Won", "Lost", "Pending", "Settled", "Not confirmed"] {
                XCTAssertFalse(word.contains(grade), "\(word) must not read as a market result")
            }
        }
        let above = MLBStrikeoutComparison11284.comparison(constructed(final: 9), selectedRowID: "c-7")
        XCTAssertEqual(above.againstText, "Finished 2 above")
        XCTAssertEqual(MLBStrikeoutComparison11284.againstLabel, "Against this target")
    }

    func testNoCurrentOrRecordedProbabilityIsShownOrSpoken() throws {
        let card = try captured()
        XCTAssertTrue(card.targets[1].original.sections.flatMap(\.fields)
            .contains { $0.label == "Recorded in game" && $0.value == "Not captured" },
                      "non-vacuous: the original says it; Details keeps it reachable")
        for selected in [nil, "gone"] + card.targets.map { $0.rowID as String? } {
            for word in allWords(card, selected: selected) {
                for absent in ["Recorded", "recorded", "Not captured", "Current", "current", "Live", "live"] {
                    XCTAssertFalse(word.contains(absent), "\(word)")
                }
            }
        }
    }

    // MARK: - Words for VoiceOver

    func testTheChartSummaryCarriesEveryPlottedValueAndTheSelection() throws {
        let card = try captured()
        let spoken = MLBStrikeoutComparison11284.chartSpoken(card, selectedRowID: Self.sevenRowID)
        XCTAssertTrue(spoken.hasPrefix("Hunter Brown, pregame chance to reach each count: "))
        for chance in [0.57, 0.445, 0.275, 0.11, 0.07] {
            XCTAssertTrue(spoken.contains(formatProbability(chance)), "\(chance)")
        }
        XCTAssertTrue(spoken.contains("7 or more, \(formatProbability(0.445)), selected"))
        XCTAssertTrue(spoken.contains("12 or more, unavailable"))
        XCTAssertTrue(spoken.hasSuffix("Official final unavailable."))
        XCTAssertEqual(spoken.components(separatedBy: ", selected").count, 2, "one selection")
    }

    func testEachPartIsSpokenAsItsOwnThing() throws {
        let card = try typedFinalOfTwo()
        let comparison = MLBStrikeoutComparison11284.comparison(card, selectedRowID: Self.sevenRowID)
        XCTAssertEqual(comparison.targetSpoken, "Selected target, 7 or more strikeouts")
        XCTAssertTrue(comparison.pregameSpoken.hasPrefix("Pregame chance, "))
        XCTAssertEqual(comparison.finalSpoken, "Official final, 2 strikeouts")
        XCTAssertEqual(comparison.againstSpoken, "Against this target, Finished 5 short")
        XCTAssertEqual(MLBStrikeoutComparison11284.selectHintText, "Shows this target's pregame chance")
        XCTAssertEqual(MLBStrikeoutComparison11284.detailsHintText, "Shows both original sides of this line")
    }

    func testTheKickerKeepsTheVenuesStatWordsAndTheSourceLabel() throws {
        let card = try captured()
        let label = try XCTUnwrap(SourceLabels.label(for: card.source), "non-vacuous: polymarket has a label")
        XCTAssertEqual(MLBStrikeoutComparison11284.kicker(card), "Strikeouts · \(label)")
        let unsourced = MLBMilestoneCard11284(eventID: 1, player: "P", stat: "Strikeouts", source: nil,
                                              side: .unknown, targets: [], finalCount: nil)
        XCTAssertEqual(MLBStrikeoutComparison11284.kicker(unsourced), "Strikeouts", "no invented venue")
    }

    func testALongNameStaysWholeInEveryReading() {
        let name = "Constructed Bartholomew Montgomery-Fitzgerald Jr."
        let card = constructed(player: name, final: 3)
        XCTAssertTrue(MLBStrikeoutComparison11284.chartSpoken(card, selectedRowID: "c-5").hasPrefix("\(name), "))
        XCTAssertEqual(card.player, name)
    }

    // MARK: - Size, stacking and plot space

    func testAccessibilitySizesStackTheComparison() {
        for size in [DynamicTypeSize.accessibility1, .accessibility3, .accessibility5] {
            XCTAssertTrue(MLBStrikeoutComparison11284.stacks(at: size), "\(size)")
        }
        for size in [DynamicTypeSize.small, .large, .xxxLarge] {
            XCTAssertFalse(MLBStrikeoutComparison11284.stacks(at: size), "\(size)")
        }
    }

    func testFiguresAndControlsKeepTheirMinimums() {
        XCTAssertGreaterThanOrEqual(MLBStrikeoutComparison11284.figurePointSize, 28)
        XCTAssertGreaterThanOrEqual(MLBStrikeoutComparison11284.minimumControlHeight, 44)
    }

    func testThePlotKeepsItsUsefulHeightAndGrowsForTheFinalsLabel() {
        let compact = MLBStrikeoutComparison11284.chartHeight(expanded: false, axisFontSize: 12, hasFinal: false)
        let expanded = MLBStrikeoutComparison11284.chartHeight(expanded: true, axisFontSize: 12, hasFinal: false)
        XCTAssertGreaterThanOrEqual(compact, 150)
        XCTAssertGreaterThanOrEqual(expanded, 220)
        let labelled = MLBStrikeoutComparison11284.chartHeight(expanded: false, axisFontSize: 12, hasFinal: true)
        let larger = MLBStrikeoutComparison11284.chartHeight(expanded: false, axisFontSize: 16, hasFinal: true)
        XCTAssertGreaterThan(labelled, compact, "the final's label never takes plot space")
        XCTAssertGreaterThan(larger, labelled)
    }

    // MARK: - Empty input

    func testAnEmptyLadderNeverCrashesOrInventsATarget() {
        let card = MLBMilestoneCard11284(eventID: 1, player: "Empty", stat: "Strikeouts", source: nil,
                                         side: .unknown, targets: [], finalCount: nil)
        XCTAssertEqual(MLBStrikeoutComparison11284.choices(card, selectedRowID: nil), [])
        XCTAssertEqual(MLBStrikeoutComparison11284.points(card, selectedRowID: nil), [])
        XCTAssertEqual(MLBStrikeoutComparison11284.domain(card), 0...1)
        XCTAssertEqual(MLBStrikeoutComparison11284.axisLabels(card, selectedRowID: nil).values, [0])
        XCTAssertEqual(MLBStrikeoutComparison11284.selection(card, selectedRowID: nil), .unselected)
        XCTAssertEqual(MLBStrikeoutComparison11284.selection(card, selectedRowID: "x"), .unavailable)
        XCTAssertNil(MLBStrikeoutComparison11284.comparison(card, selectedRowID: "x").detailsID)
    }
}
