import SwiftUI
import XCTest
@testable import Bain_Luck

/// #10868 — two subjects' own chances of reaching the same stat milestone,
/// grouped on one stateless chart across pregame, live and final.
///
/// The view is SwiftUI and is not rasterised here. What is asserted is the
/// rules it defers to: which readings each phase shows for each subject, the
/// exact-id group selection, the action each control carries, the chart marks
/// and keys, the layout plan, and the spoken text. Nothing here claims a
/// rendered fit, VoiceOver behaviour or real delivery.
///
/// REAL values come from the Bears–Eagles retained game as retained in
/// `shipping-adoption-20261027/PAIRED-TEAM-MILESTONES-RETAINED-CASES.json`
/// (sha256 bc6708d2…d336), produced by the existing `teamMilestones` and
/// `probabilityLabel` helpers unchanged over `markets.json` (bb3c25a1…985f).
/// Original ids are the retained `row_key`s:
///   Team Sacks, market 62481362
///     Chicago      2+ 0.645 "64.5%" 848 Hit · 3+ 0.385 "38.5%" 849 Missed ·
///                  4+ 0.21 "21%" 850 Missed · 5+ 0.07 "7%" 851 Missed ·
///                  6+ 0.06 "6%" 852 Missed
///     Philadelphia 2+ 0.625 "62.5%" 853 · 3+ 0.405 "40.5%" 854 ·
///                  4+ 0.215 "21.5%" 855 · 5+ 0.145 "14.5%" 856 ·
///                  6+ 0.09 "9%" 857 — all Missed
///   Team Field Goals, market 62436325
///     Chicago      1+ 0.815 "81.5%" 488 Hit · 2+ 0.47 "47%" 489 Hit ·
///                  3+ 0.195 "19.5%" 490 Missed · 4+ 0.085 "8.5%" 491 Missed
///     Philadelphia 1+ 0.785 "78.5%" 492 · 2+ 0.505 "50.5%" 493 ·
///                  3+ 0.23 "23%" 494 · 4+ 0.09 "9%" 495 — all Missed
/// Results are retained for Final only. Every exact count (so far or final)
/// and every true current chance is absent in this capture; nothing here
/// supplies one for a real team in any phase, and no count is read off a Hit
/// or Missed. The row capture clock is not a stat time and is not used.
///
/// CONSTRUCTED owner-resolved inputs (this leaf does not resolve them): the
/// group ids and titles, original titles, subject ids, every spoken detail,
/// the absence and result-pending words, tick labels, card id and copy; and
/// every live, recorded, withheld, reached, zero, invalid, missing-sibling,
/// duplicate, reordered, count and wrong-kind count case, which uses the
/// subjects "Constructed Home" and "Constructed Away".
final class PairedMilestonePresentation10868Tests: XCTestCase {

    // MARK: Real fixtures

    private struct Real {
        let threshold: Int
        let probability: Double
        let text: String
        let row: Int
        let result: String
    }

    private enum Kind { case sacks, fieldGoals }

    private static let sacksBears = [
        Real(threshold: 2, probability: 0.645, text: "64.5%", row: 848, result: "Hit"),
        Real(threshold: 3, probability: 0.385, text: "38.5%", row: 849, result: "Missed"),
        Real(threshold: 4, probability: 0.21, text: "21%", row: 850, result: "Missed"),
        Real(threshold: 5, probability: 0.07, text: "7%", row: 851, result: "Missed"),
        Real(threshold: 6, probability: 0.06, text: "6%", row: 852, result: "Missed"),
    ]
    private static let sacksEagles = [
        Real(threshold: 2, probability: 0.625, text: "62.5%", row: 853, result: "Missed"),
        Real(threshold: 3, probability: 0.405, text: "40.5%", row: 854, result: "Missed"),
        Real(threshold: 4, probability: 0.215, text: "21.5%", row: 855, result: "Missed"),
        Real(threshold: 5, probability: 0.145, text: "14.5%", row: 856, result: "Missed"),
        Real(threshold: 6, probability: 0.09, text: "9%", row: 857, result: "Missed"),
    ]
    private static let goalsBears = [
        Real(threshold: 1, probability: 0.815, text: "81.5%", row: 488, result: "Hit"),
        Real(threshold: 2, probability: 0.47, text: "47%", row: 489, result: "Hit"),
        Real(threshold: 3, probability: 0.195, text: "19.5%", row: 490, result: "Missed"),
        Real(threshold: 4, probability: 0.085, text: "8.5%", row: 491, result: "Missed"),
    ]
    private static let goalsEagles = [
        Real(threshold: 1, probability: 0.785, text: "78.5%", row: 492, result: "Missed"),
        Real(threshold: 2, probability: 0.505, text: "50.5%", row: 493, result: "Missed"),
        Real(threshold: 3, probability: 0.23, text: "23%", row: 494, result: "Missed"),
        Real(threshold: 4, probability: 0.09, text: "9%", row: 495, result: "Missed"),
    ]

    private static let baselineDetail = "supplied pregame baseline, may be the opening quote · exact time unavailable · Kalshi"
    private static let noReading = PlayerContributionCurrent10868.unavailable("No in-game reading")
    private static let afterGame = PlayerContributionResult10868.unconfirmed("Result after game")
    private static let countUnavailable = PlayerContributionActual10868.unavailable("Count unavailable")
    private static let finalCountUnavailable = PlayerContributionActual10868.unavailable("Exact final count unavailable")
    /// The owner's words for an empty channel — for this phase, no count of its own kind.
    private static let countMissing = "Count not supplied"
    private static let ticks = [
        PlayerContributionTick10868(value: 0, text: "0%"),
        PlayerContributionTick10868(value: 0.5, text: "50%"),
        PlayerContributionTick10868(value: 1, text: "100%"),
    ]

    private static func obs(_ probability: Double, _ text: String, _ detail: String = baselineDetail) -> PlayerContributionObservation10868 {
        PlayerContributionObservation10868(probability: probability, text: text, accessibilityDetail: detail)
    }

    private static func groupID(_ kind: Kind, _ threshold: Int) -> String {
        "nfl-team-stats:\(kind == .sacks ? "sacks" : "field-goals"):\(threshold)"
    }

    private static func unit(_ kind: Kind) -> String { kind == .sacks ? "sacks" : "field goals" }

    /// One real original. Its retained result is carried only when asked —
    /// the retained Before/During capture has none.
    private static func original(_ real: Real, team: String, kind: Kind, carryResult: Bool,
                                 current: PlayerContributionCurrent10868 = noReading) -> PairedMilestoneOriginal10868 {
        let result: PlayerContributionResult10868
        if carryResult {
            result = real.result == "Hit" ? .reached(real.result) : .missed(real.result)
        } else {
            result = afterGame
        }
        return PairedMilestoneOriginal10868(
            id: "player_props:\(real.row)",
            title: "\(team) \(real.threshold)+ \(unit(kind))",
            before: obs(real.probability, real.text),
            beforeMissing: "Unavailable",
            current: current,
            result: result
        )
    }

    private static func realGroups(_ kind: Kind, carryResult: Bool,
                                   current: PlayerContributionCurrent10868 = noReading) -> [PairedMilestoneGroup10868] {
        let bears = kind == .sacks ? sacksBears : goalsBears
        let eagles = kind == .sacks ? sacksEagles : goalsEagles
        return zip(bears, eagles).map { b, e in
            PairedMilestoneGroup10868(
                id: groupID(kind, b.threshold),
                target: "\(b.threshold)+",
                title: "\(b.threshold)+ \(unit(kind))",
                first: .original(original(b, team: "Bears", kind: kind, carryResult: carryResult, current: current)),
                second: .original(original(e, team: "Eagles", kind: kind, carryResult: carryResult, current: current))
            )
        }
    }

    /// A real card. `carryResult` lets a test hand a Before/During card the
    /// retained final grades on purpose; `carriedCount` puts one constructed
    /// count in both channels on purpose. Otherwise each phase's own channel
    /// holds the owner's absence words: no real count exists in any phase.
    private static func real(_ kind: Kind, _ phase: PlayerContributionPhase10868, selected: Int? = nil,
                             carryResult: Bool? = nil,
                             carriedCount: PlayerContributionActual10868? = nil,
                             current: PlayerContributionCurrent10868 = noReading) -> PairedMilestoneInput10868 {
        let carry = carryResult ?? (phase == .final)
        let soFar = carriedCount ?? (phase == .during ? countUnavailable : nil)
        let final = carriedCount ?? (phase == .final ? finalCountUnavailable : nil)
        return PairedMilestoneInput10868(
            phase: phase,
            orientation: kind == .sacks ? .bars : .columns,
            cardID: kind == .sacks ? "nfl-team-stats:sacks" : "nfl-team-stats:field-goals",
            eyebrow: "TEAM MILESTONES",
            title: kind == .sacks ? "Quarterback pressure" : "The kicking game",
            definition: "Each team’s chance belongs to its own contract. The two do not add to 100%.",
            first: PairedMilestoneSubject10868(id: "Chicago", name: "Bears", detail: "Chicago",
                                               countSoFar: soFar, finalCount: final, countMissing: countMissing),
            second: PairedMilestoneSubject10868(id: "Philadelphia", name: "Eagles", detail: "Philadelphia",
                                                countSoFar: soFar, finalCount: final, countMissing: countMissing),
            groups: realGroups(kind, carryResult: carry, current: current),
            selectedGroupID: selected.map { groupID(kind, $0) },
            chartTitle: "Pregame chances · at least this many \(unit(kind))",
            ticks: ticks
        )
    }

    // MARK: Constructed fixtures

    private static func made(_ id: String, before: PlayerContributionObservation10868?,
                             current: PlayerContributionCurrent10868 = noReading,
                             result: PlayerContributionResult10868 = afterGame) -> PairedMilestoneOriginal10868 {
        PairedMilestoneOriginal10868(id: id, title: "Constructed \(id)", before: before, beforeMissing: "Unavailable",
                                     current: current, result: result)
    }

    private static func madeGroup(_ id: String, _ first: PairedMilestoneEntry10868,
                                  _ second: PairedMilestoneEntry10868) -> PairedMilestoneGroup10868 {
        PairedMilestoneGroup10868(id: id, target: "\(id)+", title: "\(id)+ constructed", first: first, second: second)
    }

    private static func constructed(_ phase: PlayerContributionPhase10868, _ groups: [PairedMilestoneGroup10868],
                                    selected: String? = nil, cardID: String? = "constructed-card",
                                    firstID: String = "home", secondID: String = "away",
                                    firstSoFar: PlayerContributionActual10868? = countUnavailable,
                                    firstFinal: PlayerContributionActual10868? = finalCountUnavailable,
                                    secondSoFar: PlayerContributionActual10868? = countUnavailable,
                                    secondFinal: PlayerContributionActual10868? = finalCountUnavailable,
                                    orientation: PlayerContributionOrientation10868 = .bars) -> PairedMilestoneInput10868 {
        PairedMilestoneInput10868(
            phase: phase,
            orientation: orientation,
            cardID: cardID,
            eyebrow: nil,
            title: "Constructed card",
            definition: nil,
            first: PairedMilestoneSubject10868(id: firstID, name: "Constructed Home", detail: nil,
                                               countSoFar: firstSoFar, finalCount: firstFinal, countMissing: countMissing),
            second: PairedMilestoneSubject10868(id: secondID, name: "Constructed Away", detail: nil,
                                                countSoFar: secondSoFar, finalCount: secondFinal, countMissing: countMissing),
            groups: groups,
            selectedGroupID: selected,
            chartTitle: nil,
            ticks: ticks
        )
    }

    private static let sides = PairedMilestoneSide10868.allCases

    // MARK: Real originals, both orientations

    func testSacksKeepAllTenRealOriginalsInOwnerOrderAsHorizontalBars() {
        let input = Self.real(.sacks, .before)
        XCTAssertEqual(input.groups.map(\.target), ["2+", "3+", "4+", "5+", "6+"])
        XCTAssertEqual(input.groups.flatMap { [$0.first.original?.id, $0.second.original?.id] },
                       (848...852).flatMap { ["player_props:\($0)", "player_props:\($0 + 5)"] as [String?] })
        XCTAssertEqual(input.groups.map { input.lane($0, side: .first).beforeFraction }, Self.sacksBears.map { $0.probability as Double? })
        XCTAssertEqual(input.groups.map { input.lane($0, side: .second).beforeFraction }, Self.sacksEagles.map { $0.probability as Double? })
        XCTAssertEqual(input.groups.map { input.lane($0, side: .first).pregame?.text }, Self.sacksBears.map { $0.text as String? })
        XCTAssertEqual(input.groups.map { input.lane($0, side: .second).pregame?.text }, Self.sacksEagles.map { $0.text as String? })
        XCTAssertEqual(input.chartForms(isAccessibilitySize: false), [.bars])
        XCTAssertEqual(input.chartForms(isAccessibilitySize: true), [.bars])
    }

    func testFieldGoalsKeepAllEightRealOriginalsAsPairedColumnsWithABarsFallback() {
        let input = Self.real(.fieldGoals, .before)
        XCTAssertEqual(input.groups.map(\.target), ["1+", "2+", "3+", "4+"])
        XCTAssertEqual(input.groups.flatMap { [$0.first.original?.id, $0.second.original?.id] },
                       (488...491).flatMap { ["player_props:\($0)", "player_props:\($0 + 4)"] as [String?] })
        XCTAssertEqual(input.groups.map { input.lane($0, side: .first).beforeFraction }, Self.goalsBears.map { $0.probability as Double? })
        XCTAssertEqual(input.groups.map { input.lane($0, side: .second).beforeFraction }, Self.goalsEagles.map { $0.probability as Double? })
        // Columns first; every group kept as bars when they do not fit.
        XCTAssertEqual(input.chartForms(isAccessibilitySize: false), [.columns, .bars])
        XCTAssertEqual(input.chartForms(isAccessibilitySize: true), [.bars])
    }

    func testEachTeamKeepsItsOwnNoncomplementChanceNeverNormalized() {
        let sacks = Self.real(.sacks, .before, selected: 2)
        let pair = Self.sides.map { sacks.reading(sacks.selection.group!, side: $0) }
        XCTAssertEqual(pair.map(\.pregame), [.figure(Self.obs(0.645, "64.5%")), .figure(Self.obs(0.625, "62.5%"))])
        // 127% together: two separate contracts, drawn at their own values.
        let fractions = Self.sides.compactMap { sacks.lane(sacks.selection.group!, side: $0).beforeFraction }
        XCTAssertEqual(fractions.reduce(0, +), 1.27, accuracy: 1e-9)

        let goals = Self.real(.fieldGoals, .before, selected: 1)
        XCTAssertEqual(Self.sides.map { goals.reading(goals.selection.group!, side: $0).pregame },
                       [.figure(Self.obs(0.815, "81.5%")), .figure(Self.obs(0.785, "78.5%"))])
    }

    // MARK: Phase gates

    func testBeforeHidesCarriedResultsCountsAndInGameReadings() {
        let carried = PlayerContributionActual10868.count(
            PlayerContributionCount10868(count: "9", unit: "sacks", breakdown: nil, accessibilityDetail: "constructed"))
        let input = Self.real(.sacks, .before, selected: 2, carryResult: true, carriedCount: carried,
                              current: .recorded(Self.obs(0.9, "90%", "constructed"), movement: "+25 points"))
        for side in Self.sides {
            let reading = input.reading(input.selection.group!, side: side)
            XCTAssertNil(reading.result)
            XCTAssertNil(reading.current)
            XCTAssertNil(reading.movement)
            XCTAssertNil(input.actualPresentation(side))
        }
        for group in input.groups {
            for side in Self.sides {
                let lane = input.lane(group, side: side)
                XCTAssertFalse(lane.hasCurrentLane)
                XCTAssertNil(lane.currentFraction)
                XCTAssertEqual(lane.statuses, [])
                XCTAssertEqual(input.slots(group, side: side).count, 1)
            }
        }
        XCTAssertFalse(input.showsFilledKey)
        XCTAssertNil(input.sharedActualAbsence)
    }

    func testGenuineDuringShowsLabelledMissingCurrentWordsAndNoFilledMark() {
        let input = Self.real(.fieldGoals, .during, selected: 1, carryResult: true)
        let group = input.selection.group!
        for side in Self.sides {
            let reading = input.reading(group, side: side)
            XCTAssertEqual(reading.current, .chanceStatus("No in-game reading"))
            XCTAssertEqual(reading.current?.title, "In-game chance")
            XCTAssertNil(reading.result, "a carried final grade stays hidden during play")
            XCTAssertEqual(input.actualPresentation(side),
                           PlayerContributionActualPresentation10868(title: "Count so far", actual: Self.countUnavailable))
        }
        for g in input.groups {
            for side in Self.sides {
                let lane = input.lane(g, side: side)
                XCTAssertTrue(lane.hasCurrentLane)
                XCTAssertNil(lane.currentFraction)
                XCTAssertEqual(lane.statuses, [PlayerContributionRowStatus10868(title: "In-game chance", words: "No in-game reading")])
                XCTAssertEqual(input.slots(g, side: side).count, 2)
            }
        }
        XCTAssertFalse(input.showsFilledKey)
        XCTAssertTrue(input.showsOutlinedKey)
    }

    func testConstructedLiveControlFillsOnlyARecordedChance() {
        let recorded = Self.made("r", before: Self.obs(0.4, "40%", "constructed pregame"),
                                 current: .recorded(Self.obs(0.55, "55%", "constructed live"), movement: "+15 points"))
        let withheld = Self.made("w", before: Self.obs(0.3, "30%", "constructed pregame"),
                                 current: .withheld("No recent probability update"))
        let reached = Self.made("x", before: Self.obs(0.2, "20%", "constructed pregame"), current: .reached("Reached so far"))
        let input = Self.constructed(.during, [Self.madeGroup("2", .original(recorded), .original(withheld)),
                                               Self.madeGroup("3", .original(reached), .missing("No original"))],
                                     selected: "2")
        let first = input.reading(input.groups[0], side: .first)
        XCTAssertEqual(first.current, .chance(Self.obs(0.55, "55%", "constructed live")))
        XCTAssertEqual(first.movement, "+15 points")
        XCTAssertEqual(input.lane(input.groups[0], side: .first).currentFraction, 0.55)

        let second = input.lane(input.groups[0], side: .second)
        XCTAssertNil(second.currentFraction, "a withheld chance is never filled")
        XCTAssertEqual(second.statuses, [PlayerContributionRowStatus10868(title: "In-game chance", words: "No recent probability update")])
        XCTAssertNil(input.reading(input.groups[0], side: .second).movement)

        let performance = input.lane(input.groups[1], side: .first)
        XCTAssertNil(performance.currentFraction, "reached is performance, never 100%")
        XCTAssertEqual(performance.statuses, [PlayerContributionRowStatus10868(title: "Actual so far", words: "Reached so far")])
        XCTAssertTrue(input.showsFilledKey)
    }

    func testRealZeroDrawsAVisibleZeroMarkWhileMissingDrawsNone() {
        let zero = Self.made("z", before: Self.obs(0, "0%", "constructed pregame"),
                             current: .recorded(Self.obs(0, "0%", "constructed live"), movement: nil))
        let absent = Self.made("a", before: nil, current: .unavailable("No in-game reading"))
        let input = Self.constructed(.during, [Self.madeGroup("1", .original(zero), .original(absent))])
        let lane = input.lane(input.groups[0], side: .first)
        XCTAssertEqual(lane.beforeFraction, 0)
        XCTAssertEqual(lane.currentFraction, 0)
        XCTAssertEqual(PlayerContributionGeometry10868.markLength(lane.beforeFraction, extent: 200),
                       PlayerContributionGeometry10868.minimumMark)
        let missing = input.lane(input.groups[0], side: .second)
        XCTAssertNil(missing.beforeFraction)
        XCTAssertNil(PlayerContributionGeometry10868.markLength(missing.beforeFraction, extent: 200))
        XCTAssertEqual(missing.statuses, [
            PlayerContributionRowStatus10868(title: "Pregame chance", words: "Unavailable"),
            PlayerContributionRowStatus10868(title: "In-game chance", words: "No in-game reading"),
        ])
    }

    // MARK: Final

    func testFinalSetsEachOwnPregameChanceBesideItsOwnRealResult() {
        let sacks = Self.real(.sacks, .final, selected: 2)
        let pair = Self.sides.map { sacks.reading(sacks.selection.group!, side: $0) }
        XCTAssertEqual(pair.map(\.pregame), [.figure(Self.obs(0.645, "64.5%")), .figure(Self.obs(0.625, "62.5%"))])
        XCTAssertEqual(pair.map(\.result), [.reached("Hit"), .missed("Missed")])
        XCTAssertEqual(pair.map(\.originalID), ["player_props:848", "player_props:853"])
        XCTAssertEqual(pair.map(\.current), [nil, nil])

        let goals = Self.real(.fieldGoals, .final)
        let grades = goals.groups.map { group in Self.sides.map { goals.reading(group, side: $0).result?.text } }
        XCTAssertEqual(grades, [["Hit", "Missed"], ["Hit", "Missed"], ["Missed", "Missed"], ["Missed", "Missed"]])
    }

    func testFinalGradeNeverBecomesAHundredOrZeroMark() {
        let input = Self.real(.fieldGoals, .final, current: .recorded(Self.obs(1, "100%", "constructed settled"), movement: nil))
        for (index, group) in input.groups.enumerated() {
            let first = input.lane(group, side: .first)
            let second = input.lane(group, side: .second)
            XCTAssertEqual(first.beforeFraction, Self.goalsBears[index].probability)
            XCTAssertEqual(second.beforeFraction, Self.goalsEagles[index].probability)
            XCTAssertNil(first.currentFraction)
            XCTAssertNil(second.currentFraction)
            XCTAssertFalse(first.hasCurrentLane)
            XCTAssertEqual(Self.sides.map { input.slots(group, side: $0).count }, [1, 1])
        }
        XCTAssertFalse(input.showsFilledKey)
    }

    func testFinalExactCountsStayUnavailableBesideSettledMilestones() {
        for kind in [Kind.sacks, .fieldGoals] {
            let input = Self.real(kind, .final, selected: kind == .sacks ? 2 : 1)
            for side in Self.sides {
                XCTAssertEqual(input.actualPresentation(side),
                               PlayerContributionActualPresentation10868(title: "Final count", actual: Self.finalCountUnavailable))
                XCTAssertEqual(input.accessibilityActual(input.actualPresentation(side)!), "Exact final count unavailable")
            }
            // Both absences are the same owner words: one explicit shared line, never a count.
            XCTAssertEqual(input.sharedActualAbsence,
                           PlayerContributionRowStatus10868(title: "Final count", words: "Exact final count unavailable"))
        }
        let during = Self.real(.sacks, .during)
        XCTAssertEqual(during.sharedActualAbsence,
                       PlayerContributionRowStatus10868(title: "Count so far", words: "Count unavailable"))
    }

    func testUnconfirmedResultStaysStatusAndAnotherSubjectsResultIsNotBorrowed() {
        let input = Self.constructed(.final, [Self.madeGroup("1",
            .original(Self.made("h", before: Self.obs(0.6, "60%", "constructed"), result: .reached("Hit"))),
            .original(Self.made("a", before: Self.obs(0.6, "60%", "constructed"), result: .unconfirmed("Result unconfirmed"))))],
            selected: "1")
        let away = input.reading(input.groups[0], side: .second)
        XCTAssertEqual(away.result, .unconfirmed("Result unconfirmed"))
        XCTAssertEqual(away.result?.isAdmitted, false)
    }

    // MARK: Missing and invalid

    func testMissingSiblingKeepsItsWordsAndIsNeverSynthesized() {
        let input = Self.constructed(.during, [Self.madeGroup("6",
            .original(Self.made("only", before: Self.obs(0.09, "9%", "constructed"))),
            .missing("No original for this milestone"))], selected: "6")
        let lane = input.lane(input.groups[0], side: .second)
        XCTAssertNil(lane.pregame)
        XCTAssertNil(lane.beforeFraction)
        XCTAssertFalse(lane.hasCurrentLane)
        XCTAssertEqual(lane.statuses, [PlayerContributionRowStatus10868(title: nil, words: "No original for this milestone")])
        let reading = input.reading(input.groups[0], side: .second)
        XCTAssertEqual(reading.missing, "No original for this milestone")
        XCTAssertNil(reading.pregame)
        XCTAssertNil(reading.originalID)
        XCTAssertNil(input.detailsAction(.second, canOpenDetails: true))
        XCTAssertEqual(input.detailsAction(.first, canOpenDetails: true), .details("only"))
    }

    func testInvalidGeometryDrawsNoMarkButKeepsTheOwnersText() {
        let input = Self.constructed(.before, [
            Self.madeGroup("1", .original(Self.made("over", before: Self.obs(1.2, "120%", "constructed"))),
                           .original(Self.made("nan", before: Self.obs(.nan, "—", "constructed")))),
            Self.madeGroup("2", .original(Self.made("neg", before: Self.obs(-0.1, "-10%", "constructed"))),
                           .original(Self.made("inf", before: Self.obs(.infinity, "∞", "constructed")))),
        ], selected: "1")
        for group in input.groups {
            for side in Self.sides { XCTAssertNil(input.lane(group, side: side).beforeFraction) }
        }
        XCTAssertEqual(input.lane(input.groups[0], side: .first).pregame?.text, "120%")
        XCTAssertEqual(input.reading(input.groups[0], side: .first).pregame, .words("120%"))
        XCTAssertFalse(input.showsOutlinedKey)
        let placed = PlayerContributionGeometry10868.visibleTicks(Self.ticks + [
            PlayerContributionTick10868(value: 1.5, text: "150%"),
            PlayerContributionTick10868(value: .nan, text: "NaN"),
        ])
        XCTAssertEqual(placed.map(\.text), ["0%", "50%", "100%"])
    }

    // MARK: Selection and actions

    func testSelectionIsExactAndNeverDefaultsOrJumpsToANeighbour() {
        let none = Self.real(.sacks, .before)
        XCTAssertEqual(none.selection, .none)
        XCTAssertNil(none.selectionNotice)
        XCTAssertNil(none.stepAction(1, canSelect: true))

        let withdrawn = Self.real(.sacks, .before, selected: 7)
        XCTAssertEqual(withdrawn.selection, .missing(Self.groupID(.sacks, 7)))
        XCTAssertEqual(withdrawn.selectionNotice, "Selected milestone unavailable.")
        XCTAssertFalse(withdrawn.groups.contains { withdrawn.isSelected($0) })
        XCTAssertNil(withdrawn.stepAction(-1, canSelect: true))
        XCTAssertNil(withdrawn.detailsAction(.first, canOpenDetails: true))

        let o = Self.made("d", before: Self.obs(0.5, "50%", "constructed"))
        let duplicate = Self.constructed(.before, [Self.madeGroup("1", .original(o), .missing("No original")),
                                                   Self.madeGroup("1", .missing("No original"), .missing("No original"))],
                                         selected: "1")
        XCTAssertEqual(duplicate.selection, .duplicate("1"))
        XCTAssertEqual(duplicate.selectionNotice, "Selected milestone unavailable.")
        XCTAssertNil(duplicate.groupAction(duplicate.groups[0], canSelect: true))
    }

    func testGroupActionsHandBackTheExactIdOnlyWithACallback() {
        let input = Self.real(.fieldGoals, .before, selected: 1)
        XCTAssertNil(input.groupAction(input.groups[2], canSelect: false))
        let action = input.groupAction(input.groups[2], canSelect: true)
        XCTAssertEqual(action, .select("nfl-team-stats:field-goals:3"))
        var received: [String] = []
        action?.perform(onSelect: { received.append($0) }, onDetails: { _ in XCTFail() }, onExpand: { _ in XCTFail() })
        XCTAssertEqual(received, ["nfl-team-stats:field-goals:3"])

        let unnamed = Self.constructed(.before, [Self.madeGroup("", .missing("No original"), .missing("No original"))])
        XCTAssertNil(unnamed.groupAction(unnamed.groups[0], canSelect: true))
    }

    func testPreviousAndNextFollowTheOwnersOrderAndStopAtEachEnd() {
        let first = Self.real(.sacks, .final, selected: 2)
        XCTAssertNil(first.stepAction(-1, canSelect: true))
        XCTAssertEqual(first.stepAction(1, canSelect: true), .select("nfl-team-stats:sacks:3"))
        XCTAssertNil(first.stepAction(1, canSelect: false))
        let last = Self.real(.sacks, .final, selected: 6)
        XCTAssertNil(last.stepAction(1, canSelect: true))
        XCTAssertEqual(last.stepAction(-1, canSelect: true), .select("nfl-team-stats:sacks:5"))

        // The owner's order, not a sort.
        let o = PairedMilestoneEntry10868.missing("No original")
        let reordered = Self.constructed(.before, [Self.madeGroup("4", o, o), Self.madeGroup("2", o, o), Self.madeGroup("3", o, o)],
                                         selected: "2")
        XCTAssertEqual(reordered.stepAction(-1, canSelect: true), .select("4"))
        XCTAssertEqual(reordered.stepAction(1, canSelect: true), .select("3"))
    }

    func testDetailsNeedACallbackAUniqueOriginalAndAResolvedPair() {
        let input = Self.real(.sacks, .final, selected: 3)
        XCTAssertNil(input.detailsAction(.first, canOpenDetails: false))
        XCTAssertEqual(input.detailsAction(.first, canOpenDetails: true), .details("player_props:849"))
        XCTAssertEqual(input.detailsAction(.second, canOpenDetails: true), .details("player_props:854"))
        var received: [String] = []
        input.detailsAction(.second, canOpenDetails: true)?
            .perform(onSelect: { _ in XCTFail() }, onDetails: { received.append($0) }, onExpand: { _ in XCTFail() })
        XCTAssertEqual(received, ["player_props:854"])

        let shared = Self.made("same", before: Self.obs(0.5, "50%", "constructed"))
        let reused = Self.constructed(.before, [Self.madeGroup("1", .original(shared), .original(shared))], selected: "1")
        XCTAssertNil(reused.detailsAction(.first, canOpenDetails: true), "one id on two slots is ambiguous")

        let collided = Self.constructed(.before, [Self.madeGroup("1",
            .original(Self.made("h", before: Self.obs(0.5, "50%", "constructed"))),
            .original(Self.made("a", before: Self.obs(0.5, "50%", "constructed"))))],
            selected: "1", firstID: "same", secondID: "same")
        XCTAssertEqual(collided.pairNotice, "Paired subjects unresolved.")
        XCTAssertNil(collided.detailsAction(.first, canOpenDetails: true))
        XCTAssertNil(Self.real(.sacks, .final, selected: 3).pairNotice)
    }

    func testExpandNeedsACallbackAndANonEmptyCardID() {
        let input = Self.real(.sacks, .before)
        XCTAssertNil(input.expandAction(canExpand: false))
        XCTAssertEqual(input.expandAction(canExpand: true), .expand("nfl-team-stats:sacks"))
        var received: [String] = []
        input.expandAction(canExpand: true)?
            .perform(onSelect: { _ in XCTFail() }, onDetails: { _ in XCTFail() }, onExpand: { received.append($0) })
        XCTAssertEqual(received, ["nfl-team-stats:sacks"])
        XCTAssertNil(Self.constructed(.before, [], cardID: nil).expandAction(canExpand: true))
        XCTAssertNil(Self.constructed(.before, [], cardID: "").expandAction(canExpand: true))
    }

    // MARK: Keys, layout and counts

    func testKeysAppearOnlyForMarksActuallyDrawn() {
        XCTAssertTrue(Self.real(.sacks, .before).showsOutlinedKey)
        XCTAssertFalse(Self.real(.sacks, .before).showsFilledKey)
        let blank = Self.constructed(.during, [Self.madeGroup("1", .missing("No original"),
                                                              .original(Self.made("b", before: nil)))])
        XCTAssertFalse(blank.showsOutlinedKey)
        XCTAssertFalse(blank.showsFilledKey)
        XCTAssertEqual(PairedMilestoneInput10868.outlinedKey, "Outlined · Pregame chance")
        XCTAssertEqual(PairedMilestoneInput10868.filledKey, "Filled · Recorded in-game")
    }

    func testLayoutPlanStacksWhenPairsDoNotFitAndAlwaysAtAccessibilitySizes() {
        let input = Self.real(.fieldGoals, .final, selected: 1)
        XCTAssertEqual(input.readoutLayouts(isAccessibilitySize: false), [.paired, .stacked])
        XCTAssertEqual(input.readoutLayouts(isAccessibilitySize: true), [.stacked])
        XCTAssertEqual(Self.constructed(.before, [], orientation: .columns).chartForms(isAccessibilitySize: false),
                       [.columns, .bars])
        // Bar groups: compact aligned rows first, stacked when they do not fit; AX sizes stack.
        XCTAssertEqual(input.barForms(isAccessibilitySize: false), [.compact, .stacked])
        XCTAssertEqual(input.barForms(isAccessibilitySize: true), [.stacked])
    }

    func testCountSoFarAndFinalCountKeepEachSubjectsOwnSlot() {
        let soFar = PlayerContributionActual10868.count(
            PlayerContributionCount10868(count: "2", unit: "sacks so far", breakdown: nil,
                                         accessibilityDetail: "as of 2nd quarter · constructed"))
        let final = PlayerContributionActual10868.count(
            PlayerContributionCount10868(count: "4", unit: "sacks", breakdown: nil, accessibilityDetail: "final · constructed"))
        let live = Self.constructed(.during, [], firstSoFar: soFar, firstFinal: final, secondSoFar: Self.countUnavailable)
        XCTAssertEqual(live.actualPresentation(.first), PlayerContributionActualPresentation10868(title: "Count so far", actual: soFar))
        XCTAssertEqual(live.accessibilityActual(live.actualPresentation(.first)!), "2 sacks so far, as of 2nd quarter · constructed")
        XCTAssertEqual(live.actualPresentation(.second)?.actual, Self.countUnavailable)
        XCTAssertNil(live.sharedActualAbsence, "a count keeps its own slot")

        let settled = Self.constructed(.final, [], firstSoFar: soFar, firstFinal: final)
        XCTAssertEqual(settled.actualPresentation(.first), PlayerContributionActualPresentation10868(title: "Final count", actual: final))
        XCTAssertEqual(settled.actualPresentation(.second)?.actual, Self.finalCountUnavailable)
        XCTAssertNil(Self.constructed(.before, [], firstSoFar: soFar, firstFinal: final).actualPresentation(.first))
    }

    func testWrongKindCountStaysUnavailableAndRealZeroStays() {
        let soFar = PlayerContributionActual10868.count(
            PlayerContributionCount10868(count: "2", unit: "sacks so far", breakdown: nil,
                                         accessibilityDetail: "as of 2nd quarter · constructed"))
        let final = PlayerContributionActual10868.count(
            PlayerContributionCount10868(count: "5", unit: "sacks", breakdown: nil, accessibilityDetail: "final · constructed"))
        let zeroSoFar = PlayerContributionActual10868.count(
            PlayerContributionCount10868(count: "0", unit: "sacks so far", breakdown: nil, accessibilityDetail: "as of 1st quarter · constructed"))
        let zeroFinal = PlayerContributionActual10868.count(
            PlayerContributionCount10868(count: "0", unit: "sacks", breakdown: nil, accessibilityDetail: "final · constructed"))
        let missing = PlayerContributionActual10868.unavailable(Self.countMissing)

        // A final count carried into play never shows as a count so far.
        let live = Self.constructed(.during, [], firstSoFar: nil, firstFinal: final, secondSoFar: zeroSoFar, secondFinal: nil)
        XCTAssertEqual(live.actualPresentation(.first), PlayerContributionActualPresentation10868(title: "Count so far", actual: missing))
        XCTAssertEqual(live.actualPresentation(.second)?.actual, zeroSoFar, "a real 0 so far stays a count")
        XCTAssertNil(live.sharedActualAbsence)

        // A partial count left at the final never shows as the final count.
        let settled = Self.constructed(.final, [], firstSoFar: soFar, firstFinal: nil, secondSoFar: nil, secondFinal: zeroFinal)
        XCTAssertEqual(settled.actualPresentation(.first), PlayerContributionActualPresentation10868(title: "Final count", actual: missing))
        XCTAssertEqual(settled.accessibilityActual(settled.actualPresentation(.first)!), Self.countMissing)
        XCTAssertEqual(settled.actualPresentation(.second)?.actual, zeroFinal, "a real final 0 stays a count")

        // Neither channel supplied: the owner's words in each phase, and one shared line.
        let none = Self.constructed(.final, [], firstSoFar: nil, firstFinal: nil, secondSoFar: nil, secondFinal: nil)
        XCTAssertEqual(Self.sides.map { none.actualPresentation($0)?.actual }, [missing, missing] as [PlayerContributionActual10868?])
        XCTAssertEqual(none.sharedActualAbsence, PlayerContributionRowStatus10868(title: "Final count", words: Self.countMissing))

        // Different absence reasons keep their own slots.
        let differing = Self.constructed(.final, [], firstFinal: nil, secondFinal: Self.finalCountUnavailable)
        XCTAssertEqual(differing.actualPresentation(.first)?.actual, missing)
        XCTAssertEqual(differing.actualPresentation(.second)?.actual, Self.finalCountUnavailable)
        XCTAssertNil(differing.sharedActualAbsence)

        // Before play no count shows, whichever channels are filled.
        let before = Self.constructed(.before, [], firstSoFar: soFar, firstFinal: final, secondSoFar: zeroSoFar, secondFinal: zeroFinal)
        XCTAssertEqual(Self.sides.map { before.actualPresentation($0) }, [nil, nil])
        XCTAssertNil(before.sharedActualAbsence)
    }

    func testCompactBarSlotsKeepEachSubjectsOwnMarkOrWords() {
        // Real Before: one outlined mark per team at its own value, no key mark needed.
        let sacks = Self.real(.sacks, .before)
        XCTAssertEqual(Self.sides.map { sacks.slots(sacks.groups[0], side: $0) }, [
            [.mark(Self.obs(0.645, "64.5%"), fraction: 0.645, filled: false)],
            [.mark(Self.obs(0.625, "62.5%"), fraction: 0.625, filled: false)],
        ])

        // Real During: the outlined mark, then the owner's in-game words — never a filled bar.
        let during = Self.real(.fieldGoals, .during)
        XCTAssertEqual(during.slots(during.groups[0], side: .second), [
            .mark(Self.obs(0.785, "78.5%"), fraction: 0.785, filled: false),
            .status(PlayerContributionRowStatus10868(title: "In-game chance", words: "No in-game reading")),
        ])

        // Constructed: recorded fills; withheld and reached keep words; missing pregame and a missing sibling keep words.
        let recorded = Self.made("r", before: Self.obs(0.4, "40%", "constructed pregame"),
                                 current: .recorded(Self.obs(0.55, "55%", "constructed live"), movement: "+15 points"))
        let withheld = Self.made("w", before: nil, current: .withheld("No recent probability update"))
        let reached = Self.made("x", before: Self.obs(0.2, "20%", "constructed pregame"), current: .reached("Reached so far"))
        let live = Self.constructed(.during, [Self.madeGroup("2", .original(recorded), .original(withheld)),
                                              Self.madeGroup("3", .original(reached), .missing("No original"))])
        XCTAssertEqual(live.slots(live.groups[0], side: .first), [
            .mark(Self.obs(0.4, "40%", "constructed pregame"), fraction: 0.4, filled: false),
            .mark(Self.obs(0.55, "55%", "constructed live"), fraction: 0.55, filled: true),
        ])
        XCTAssertEqual(live.slots(live.groups[0], side: .second), [
            .status(PlayerContributionRowStatus10868(title: "Pregame chance", words: "Unavailable")),
            .status(PlayerContributionRowStatus10868(title: "In-game chance", words: "No recent probability update")),
        ])
        XCTAssertEqual(live.slots(live.groups[1], side: .first)[1],
                       .status(PlayerContributionRowStatus10868(title: "Actual so far", words: "Reached so far")))
        XCTAssertEqual(live.slots(live.groups[1], side: .second),
                       [.status(PlayerContributionRowStatus10868(title: nil, words: "No original"))])

        // An unplaceable value keeps its text and draws no bar; a real 0 keeps its mark.
        let edge = Self.constructed(.before, [Self.madeGroup("1",
            .original(Self.made("over", before: Self.obs(1.2, "120%", "constructed"))),
            .original(Self.made("zero", before: Self.obs(0, "0%", "constructed"))))])
        XCTAssertEqual(edge.slots(edge.groups[0], side: .first), [.mark(Self.obs(1.2, "120%", "constructed"), fraction: nil, filled: false)])
        XCTAssertEqual(edge.slots(edge.groups[0], side: .second), [.mark(Self.obs(0, "0%", "constructed"), fraction: 0, filled: false)])
    }

    // MARK: VoiceOver

    func testSpokenGroupAndReadoutTextNameEachTeamAndItsOwnReadings() {
        let before = Self.real(.sacks, .before, selected: 2)
        XCTAssertEqual(before.accessibilityHeader, "TEAM MILESTONES. Quarterback pressure")
        XCTAssertEqual(before.accessibilitySubject(.first), "Bears, Chicago")
        XCTAssertEqual(before.accessibilityBothSubjects, "Bears and Eagles")
        XCTAssertEqual(before.accessibilityValue(for: before.groups[0]),
                       "Bears: Pregame chance: 64.5%, \(Self.baselineDetail). Eagles: Pregame chance: 62.5%, \(Self.baselineDetail)")

        let during = Self.real(.fieldGoals, .during, selected: 1)
        XCTAssertEqual(during.accessibilityReading(during.reading(during.groups[0], side: .second)),
                       "Pregame chance: 78.5%, \(Self.baselineDetail); In-game chance: No in-game reading")

        let final = Self.real(.fieldGoals, .final, selected: 1)
        XCTAssertEqual(final.accessibilityReading(final.reading(final.groups[0], side: .first)),
                       "Pregame chance: 81.5%, \(Self.baselineDetail); Final result: Hit")

        let missing = Self.constructed(.before, [Self.madeGroup("6", .missing("No original"),
            .original(Self.made("a", before: Self.obs(0.09, "9%", "constructed"))))], selected: "6")
        XCTAssertEqual(missing.accessibilityValue(for: missing.groups[0]),
                       "Constructed Home: No original. Constructed Away: Pregame chance: 9%, constructed")
        XCTAssertEqual(missing.accessibilityReading(missing.reading(missing.groups[0], side: .first)), "No original")
    }
}
