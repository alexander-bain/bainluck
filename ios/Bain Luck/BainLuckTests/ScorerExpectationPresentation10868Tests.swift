import SwiftUI
import XCTest
@testable import Bain_Luck

/// #10868 — "Who found the net?" as a stateless presentation leaf across
/// pregame, live and final.
///
/// The view is SwiftUI and is not rasterised here. What is asserted is the
/// rules it defers to: which readings each phase shows, zero versus unknown,
/// the exact-id selection, the action each control carries, the timing it may
/// show, the ring and pip geometry, the column plan and the spoken text.
/// Nothing here claims a rendered fit.
///
/// ARCHIVED raw values come from Minnesota–Boston, event 15169793, as extracted
/// in `shipping-adoption-20261027/SCORER-LIFECYCLE-RETAINED-CASES.json`
/// (sha256 0babf072…bd23f), which binds the three originals:
/// `hockeyScoring.json` (9fd311a6…8d2e) for ids, teams and final counts,
/// `hockeyScorerPregame.json` (88cd833c…d2e0) for the pregame baselines the
/// reviewed reference supplies (the hockeyScoring records themselves carry nil
/// pregame), and `hockeyLiveGoals.json` (7cc31253…af826) for the goal timeline
/// and recorded observations:
///   Jeannot :0  baseline 0.08 @ 2026-10-03T21:42Z (anytime, NOT first-scorer), final 1
///   Spurgeon :1 no baseline, final 1
///   Kaprizov :2 baseline 0.43 @ 23:57Z, final 2
///   Hughes :3   baseline 0.19 @ 23:57Z, final 1
///   Boldy :23   baseline 0.40 @ 23:59Z, recorded 0.23 @ 2026-10-04T02:15Z, final 0
///   Shabanov :24 baseline 0.23 @ 23:52Z, actual nil, contract Lost
///   McCarron :25 baseline 0.11 @ 23:52Z, final 0, contract Lost
/// The live checkpoint is 02:15Z (7:15 PM PT), just after Spurgeon's goal at
/// 02:13:55Z made it 3–1: Kaprizov, Hughes, Jeannot and Spurgeon have 1 goal
/// each and Boldy 0. Kaprizov's second goal is at 02:45:07Z.
///
/// CONSTRUCTED owner-resolved inputs (this leaf does not resolve them): every
/// display string and PT time/source line; the live counts, "Scored", stale and
/// unavailable states (the live boundary in the retained cases says they must be
/// explicit owner inputs); team display text; the result line wording; and the
/// malformed, duplicate, mismatched and long-text cases.
final class ScorerExpectationPresentation10868Tests: XCTestCase {

    // MARK: Fixtures

    private static func pid(_ index: Int) -> String { "nhl-15169793-game-markets.json:player_props:\(index)" }

    private static func obs(_ probability: Double, _ text: String, _ detail: String) -> ScorerObservation10868 {
        ScorerObservation10868(probability: probability, text: text, accessibilityDetail: detail)
    }

    private static func liveCount(_ value: Int, _ text: String, _ unit: String) -> ScorerActual10868 {
        .count(ScorerGoalCount10868(value: value, text: text, unit: unit, accessibilityDetail: "3rd period, 14:34 left · ESPN"))
    }

    private static func finalCount(_ value: Int, _ text: String, _ unit: String) -> ScorerActual10868 {
        .count(ScorerGoalCount10868(value: value, text: text, unit: unit, accessibilityDetail: nil))
    }

    private static let notStarted = ScorerActual10868.unknown("Not started")
    private static let noCurrent = ScorerCurrent10868.unavailable("No in-game reading")

    private static func row(
        _ index: Int,
        _ name: String,
        team: String? = "Minnesota",
        pregame: ScorerObservation10868?,
        current: ScorerCurrent10868 = noCurrent,
        actual: ScorerActual10868 = notStarted,
        result: String? = nil
    ) -> ScorerRow10868 {
        ScorerRow10868(
            id: pid(index),
            name: name,
            team: team,
            color: .blue,
            pregame: pregame,
            pregameMissing: "Unavailable",
            current: current,
            actual: actual,
            result: result
        )
    }

    private static func input(
        _ phase: ScorerPhase10868,
        _ overview: [ScorerRow10868],
        selectedID: String? = nil,
        selectedRow: ScorerRow10868? = nil,
        timing: ScorerTiming10868? = nil,
        summary: String? = nil
    ) -> ScorerExpectationInput10868 {
        ScorerExpectationInput10868(
            phase: phase,
            title: "Who found the net?",
            context: "Kalshi · player goals",
            overview: overview,
            selectedID: selectedID,
            selectedRow: selectedRow,
            summary: summary,
            timing: timing
        )
    }

    // Pregame observations (ARCHIVED value, CONSTRUCTED text/detail).
    private static let kaprizovPregame = obs(0.43, "43%", "recorded Oct 3, 4:57 PM PT · Kalshi")
    private static let hughesPregame = obs(0.19, "19%", "recorded Oct 3, 4:57 PM PT · Kalshi")
    private static let jeannotPregame = obs(0.08, "8%", "recorded Oct 3, 2:42 PM PT · Kalshi")
    private static let boldyPregame = obs(0.40, "40%", "recorded Oct 3, 4:59 PM PT · Kalshi")
    private static let shabanovPregame = obs(0.23, "23%", "recorded Oct 3, 4:52 PM PT · Kalshi")
    private static let mccarronPregame = obs(0.11, "11%", "recorded Oct 3, 4:52 PM PT · Kalshi")
    /// Boldy's recorded observation at 2026-10-04T02:15Z.
    private static let boldyRecorded = obs(0.23, "23%", "recorded Oct 3, 7:15 PM PT · Kalshi")

    /// 02:15Z checkpoint, 3–1.
    private static var duringRows: [ScorerRow10868] {
        [
            row(2, "Kirill Kaprizov", pregame: kaprizovPregame, current: .reached("Scored"), actual: liveCount(1, "1", "goal so far")),
            row(3, "Quinn Hughes", pregame: hughesPregame, current: .reached("Scored"), actual: liveCount(1, "1", "goal so far")),
            row(0, "Tanner Jeannot", team: "Boston", pregame: jeannotPregame, current: .reached("Scored"), actual: liveCount(1, "1", "goal so far")),
            row(1, "Jared Spurgeon", pregame: nil, current: .reached("Scored"), actual: liveCount(1, "1", "goal so far")),
            row(23, "Matt Boldy", pregame: boldyPregame, current: .recorded(boldyRecorded), actual: liveCount(0, "0", "goals so far")),
        ]
    }

    private static let lost = "1+ goals outcome · Lost"

    private static var finalRows: [ScorerRow10868] {
        [
            row(2, "Kirill Kaprizov", pregame: kaprizovPregame, actual: finalCount(2, "2", "Final goals")),
            row(1, "Jared Spurgeon", pregame: nil, actual: finalCount(1, "1", "Final goal")),
            row(3, "Quinn Hughes", pregame: hughesPregame, actual: finalCount(1, "1", "Final goal")),
            row(0, "Tanner Jeannot", team: "Boston", pregame: jeannotPregame, actual: finalCount(1, "1", "Final goal")),
        ]
    }

    private static var shabanovFinal: ScorerRow10868 {
        row(24, "Max Shabanov", team: "Team unavailable", pregame: shabanovPregame,
            actual: .unknown("Final count unavailable"), result: lost)
    }

    private static var mccarronFinal: ScorerRow10868 {
        row(25, "Michael McCarron", pregame: mccarronPregame, actual: finalCount(0, "0", "Final goals"), result: lost)
    }

    // MARK: Pregame

    func testBeforeShowsOnlyThePregameRingWithNoActualOrInGameColumn() {
        let rows = [
            Self.row(2, "Kirill Kaprizov", pregame: Self.kaprizovPregame),
            Self.row(23, "Matt Boldy", pregame: Self.boldyPregame),
        ]
        let input = Self.input(.before, rows, selectedID: Self.pid(23))

        XCTAssertFalse(input.showsActual)
        for row in rows {
            XCTAssertNil(input.actualReading(row), "no actual column before play")
            XCTAssertNil(input.currentReading(row), "no in-game column before play")
            XCTAssertNil(input.pipCount(row))
            XCTAssertFalse(input.showsCurrentMark(row))
            XCTAssertNil(input.resultLine(row))
        }
        XCTAssertEqual(input.pregameReading(rows[1]), .value(Self.boldyPregame))
        XCTAssertEqual(input.legend, "Rings: pregame chance of scoring at least once")
        XCTAssertEqual(input.accessibilityValue(for: rows[1]),
                       "Pregame chance: 40%, recorded Oct 3, 4:59 PM PT · Kalshi")
        XCTAssertFalse(input.accessibilityComparison(for: rows[1]).contains("0 goals"))
    }

    func testBeforeNeverInventsAZeroEvenWhenTheOwnerPassedACount() {
        // A count passed before play is still not shown — the before phase omits the column.
        let early = Self.row(23, "Matt Boldy", pregame: Self.boldyPregame, actual: Self.finalCount(0, "0", "goals so far"))
        let input = Self.input(.before, [early])
        XCTAssertNil(input.actualReading(early))
        XCTAssertFalse(input.accessibilityValue(for: early).contains("0 goals"))
    }

    // MARK: During play

    func testDuringRingStaysPregameWhileTheCountSaysGoalsSoFar() {
        let input = Self.input(.during, Self.duringRows)
        let kaprizov = Self.duringRows[0]
        XCTAssertEqual(input.pregameReading(kaprizov), .value(Self.kaprizovPregame))
        XCTAssertEqual(ScorerGeometry10868.ringFraction(Self.kaprizovPregame.probability), 0.43)
        XCTAssertEqual(input.actualReading(kaprizov), Self.liveCount(1, "1", "goal so far"))
        XCTAssertEqual(input.pipCount(kaprizov), 1)
        XCTAssertEqual(input.legend, "Rings: pregame scoring chance · counts: goals so far")
        XCTAssertEqual(input.comparisonHeading, "Chance to score at least once")
    }

    func testDuringRecordedObservationIsComparedWithPregameAndNoDeltaIsInvented() {
        let input = Self.input(.during, Self.duringRows, selectedID: Self.pid(23))
        let boldy = Self.duringRows[4]
        XCTAssertEqual(input.selection, .overview(boldy))
        XCTAssertEqual(input.pregameReading(boldy), .value(Self.boldyPregame))
        XCTAssertEqual(input.currentReading(boldy), .value(Self.boldyRecorded))
        XCTAssertTrue(input.showsCurrentMark(boldy))
        XCTAssertEqual(input.actualReading(boldy), Self.liveCount(0, "0", "goals so far"))
        XCTAssertEqual(input.pipCount(boldy), 0, "a real zero is zero pips, not omitted")

        let spoken = input.accessibilityComparison(for: boldy)
        XCTAssertEqual(spoken,
                       "Pregame: 40%, recorded Oct 3, 4:59 PM PT · Kalshi; "
                       + "Recorded in-game: 23%, recorded Oct 3, 7:15 PM PT · Kalshi; "
                       + "0 goals so far, 3rd period, 14:34 left · ESPN")
        XCTAssertFalse(spoken.contains("17"), "no movement figure is derived")
    }

    func testReachedIsASportingStateNeverAHundredPercentChance() {
        let input = Self.input(.during, Self.duringRows, selectedID: Self.pid(2))
        let kaprizov = Self.duringRows[0]
        XCTAssertEqual(input.currentReading(kaprizov), .reached("Scored"))
        XCTAssertFalse(input.showsCurrentMark(kaprizov), "no in-game mark without an admitted observation")
        let spoken = input.accessibilityComparison(for: kaprizov)
        XCTAssertTrue(spoken.contains("Recorded in-game: Scored"))
        XCTAssertFalse(spoken.contains("100"))
    }

    func testStaleAndUnavailableKeepTheOwnersWordsAndDrawNoMark() {
        // Shabanov's last raw reading is 0.11 @ 02:03Z, twelve minutes before the checkpoint.
        let stale = Self.row(24, "Max Shabanov", team: "Team unavailable", pregame: Self.shabanovPregame,
                             current: .stale("No update since 7:03 PM"), actual: .unknown("Count unavailable"))
        let unavailable = Self.row(25, "Michael McCarron", pregame: Self.mccarronPregame,
                                   current: .unavailable("No in-game reading"), actual: Self.liveCount(0, "0", "goals so far"))
        let input = Self.input(.during, [stale, unavailable])

        XCTAssertEqual(input.currentReading(stale), .missing("No update since 7:03 PM"))
        XCTAssertEqual(input.currentReading(unavailable), .missing("No in-game reading"))
        XCTAssertFalse(input.showsCurrentMark(stale))
        XCTAssertFalse(input.showsCurrentMark(unavailable))
        XCTAssertFalse(input.accessibilityComparison(for: stale).contains("11%"), "a stale value is never shown as current")
    }

    func testMissingBaselineStillShowsTheKnownCountAndBorrowsNothing() {
        let input = Self.input(.during, Self.duringRows, selectedID: Self.pid(1))
        let spurgeon = Self.duringRows[3]
        XCTAssertEqual(input.pregameReading(spurgeon), .missing("Unavailable"))
        XCTAssertEqual(input.actualReading(spurgeon), Self.liveCount(1, "1", "goal so far"))
        XCTAssertEqual(input.accessibilityValue(for: spurgeon),
                       "Pregame chance: Unavailable; 1 goal so far, 3rd period, 14:34 left · ESPN")
    }

    func testAnInGameReadingIsNeverBorrowedAsTheMissingBaseline() {
        let recordedOnly = Self.row(1, "Jared Spurgeon", pregame: nil,
                                    current: .recorded(Self.obs(0.97, "97%", "recorded Oct 3, 7:15 PM PT · Kalshi")),
                                    actual: Self.liveCount(1, "1", "goal so far"))
        let input = Self.input(.during, [recordedOnly])
        XCTAssertEqual(input.pregameReading(recordedOnly), .missing("Unavailable"))
        XCTAssertTrue(input.accessibilityValue(for: recordedOnly).hasPrefix("Pregame chance: Unavailable"))
        XCTAssertFalse(input.accessibilityValue(for: recordedOnly).contains("97%"), "a tile speaks no in-game value")
    }

    func testJeannotsAnytimeChanceIsTheAnytimeRingOnly() {
        // 8% is to score at least once; this card never labels it a first-scorer chance.
        let input = Self.input(.final, Self.finalRows)
        let jeannot = Self.finalRows[3]
        XCTAssertEqual(input.pregameReading(jeannot), .value(Self.jeannotPregame))
        XCTAssertFalse(input.legend.lowercased().contains("first"))
        XCTAssertFalse(input.accessibilityValue(for: jeannot).lowercased().contains("first"))
    }

    // MARK: Final

    func testFinalComparesPregameChanceWithFinalGoalsAndIgnoresInGameState() {
        let kaprizov = Self.row(2, "Kirill Kaprizov", pregame: Self.kaprizovPregame,
                                current: .recorded(Self.obs(0.99, "99%", "recorded Oct 3, 7:16 PM PT · Kalshi")),
                                actual: Self.finalCount(2, "2", "Final goals"))
        let input = Self.input(.final, [kaprizov], selectedID: Self.pid(2))
        XCTAssertNil(input.currentReading(kaprizov), "no in-game or settlement figure after the final")
        XCTAssertEqual(input.pregameReading(kaprizov), .value(Self.kaprizovPregame))
        XCTAssertEqual(input.actualReading(kaprizov), Self.finalCount(2, "2", "Final goals"))
        XCTAssertEqual(input.pipCount(kaprizov), 2)
        XCTAssertEqual(input.legend, "Rings: pregame scoring chance · counts: final goals")
        XCTAssertEqual(input.comparisonHeading, "Pregame chance and final goals")
        XCTAssertEqual(input.accessibilityComparison(for: kaprizov),
                       "Pregame: 43%, recorded Oct 3, 4:57 PM PT · Kalshi; 2 Final goals")
    }

    func testZeroGoalsAndUnknownGoalsStayDifferent() {
        let input = Self.input(.final, Self.finalRows)
        let mccarron = Self.mccarronFinal
        let shabanov = Self.shabanovFinal

        XCTAssertEqual(input.actualReading(mccarron), Self.finalCount(0, "0", "Final goals"))
        XCTAssertEqual(input.pipCount(mccarron), 0)
        XCTAssertEqual(input.actualReading(shabanov), .unknown("Final count unavailable"))
        XCTAssertNil(input.pipCount(shabanov), "unknown draws no pips — not zero pips")
        XCTAssertTrue(input.accessibilityValue(for: mccarron).hasSuffix("0 Final goals"))
        XCTAssertTrue(input.accessibilityValue(for: shabanov).hasSuffix("Final count unavailable"))
        XCTAssertFalse(input.accessibilityValue(for: shabanov).contains("0"))
    }

    func testTheContractResultStaysSeparateFromActualGoals() {
        let input = Self.input(.final, Self.finalRows, selectedID: Self.pid(24), selectedRow: Self.shabanovFinal)
        let shabanov = Self.shabanovFinal
        XCTAssertEqual(input.resultLine(shabanov), Self.lost)
        XCTAssertEqual(input.actualReading(shabanov), .unknown("Final count unavailable"), "Lost is not 0 goals")
        XCTAssertEqual(input.accessibilityComparison(for: shabanov),
                       "Pregame: 23%, recorded Oct 3, 4:52 PM PT · Kalshi; Final count unavailable; 1+ goals outcome · Lost")

        let noResult = Self.row(2, "Kirill Kaprizov", pregame: Self.kaprizovPregame, actual: Self.finalCount(2, "2", "Final goals"))
        XCTAssertNil(input.resultLine(noResult), "a missing result is not a loss")
        XCTAssertNil(Self.input(.during, [shabanov]).resultLine(shabanov), "results only after the final")
    }

    // MARK: Membership and selection

    func testOverviewOrderAndMembershipAreTheOwnersOwn() {
        // Deliberately not sorted by chance or count, and longer than four.
        let rows = [Self.mccarronFinal, Self.shabanovFinal] + Self.finalRows
        let input = Self.input(.final, rows)
        XCTAssertEqual(input.overview, rows)
        XCTAssertEqual(input.overview.map(\.id), [25, 24, 2, 1, 3, 0].map(Self.pid))
    }

    func testASelectedOverviewPlayerIsMarkedOnceAndNotRepeated() {
        let input = Self.input(.final, Self.finalRows, selectedID: Self.pid(3), selectedRow: Self.finalRows[2])
        XCTAssertEqual(input.selection, .overview(Self.finalRows[2]))
        XCTAssertNil(input.outsideRow, "no second tile for a player already in the overview")
        XCTAssertEqual(Self.finalRows.filter { input.isSelected($0) }.map(\.id), [Self.pid(3)])
        XCTAssertNil(input.selectionNotice)
    }

    func testASelectedZeroGoalPlayerOutsideTheOverviewIsShownWithItsExactIdentity() {
        let input = Self.input(.final, Self.finalRows, selectedID: Self.pid(25), selectedRow: Self.mccarronFinal)
        XCTAssertEqual(input.selection, .outside(Self.mccarronFinal))
        XCTAssertEqual(input.outsideRow?.id, Self.pid(25))
        XCTAssertTrue(Self.finalRows.allSatisfy { !input.isSelected($0) })
        XCTAssertNil(input.selectionNotice)
    }

    func testAMissingSelectionFallsBackToNobody() {
        let input = Self.input(.final, Self.finalRows, selectedID: Self.pid(99))
        XCTAssertEqual(input.selection, .missing(Self.pid(99)))
        XCTAssertNil(input.selection.row)
        XCTAssertTrue(Self.finalRows.allSatisfy { !input.isSelected($0) })
        XCTAssertEqual(input.selectionNotice, ScorerExpectationInput10868.selectionUnavailable)
        XCTAssertNil(input.detailsAction(canOpenDetails: true))
    }

    func testASelectedRowWithAnotherIDIsNotUsed() {
        let input = Self.input(.final, Self.finalRows, selectedID: Self.pid(24), selectedRow: Self.mccarronFinal)
        XCTAssertEqual(input.selection, .missing(Self.pid(24)))
        XCTAssertNil(input.outsideRow)
    }

    func testADuplicatedSelectionIsExplicitAndPicksNoTile() {
        let twice = Self.finalRows + [Self.finalRows[0]]
        let input = Self.input(.final, twice, selectedID: Self.pid(2))
        XCTAssertEqual(input.selection, .duplicate(Self.pid(2)))
        XCTAssertTrue(twice.allSatisfy { !input.isSelected($0) })
        XCTAssertEqual(input.selectionNotice, ScorerExpectationInput10868.selectionUnavailable)
        XCTAssertEqual(input.overview.count, 5, "the duplicate is shown as supplied, not dropped")
    }

    func testNoSelectionIsNotANotice() {
        let input = Self.input(.during, Self.duringRows)
        XCTAssertEqual(input.selection, .none)
        XCTAssertNil(input.selectionNotice)
    }

    // MARK: Callbacks

    func testActionsCarryExactIDsAndDisappearWithoutCallbacks() {
        let input = Self.input(.final, Self.finalRows, selectedID: Self.pid(25), selectedRow: Self.mccarronFinal)
        XCTAssertEqual(input.tileAction(Self.finalRows[1], canSelect: true), .select(Self.pid(1)))
        XCTAssertNil(input.tileAction(Self.finalRows[1], canSelect: false))
        XCTAssertEqual(input.detailsAction(canOpenDetails: true), .details(Self.pid(25)))
        XCTAssertNil(input.detailsAction(canOpenDetails: false))
        XCTAssertEqual(input.instruction(canSelect: true), "Choose a player to compare.")
        XCTAssertNil(input.instruction(canSelect: false), "no tap is asked for without a callback")

        var selected: [String] = []
        var details: [String] = []
        ScorerAction10868.select(Self.pid(1)).perform(onSelect: { selected.append($0) }, onDetails: { details.append($0) })
        ScorerAction10868.details(Self.pid(25)).perform(onSelect: { selected.append($0) }, onDetails: { details.append($0) })
        XCTAssertEqual(selected, [Self.pid(1)])
        XCTAssertEqual(details, [Self.pid(25)])
    }

    // MARK: Timing

    func testTimingBelongsToItsPlayerAndIsPresentedThePageOwnersWay() {
        let timing = ScorerTiming10868(
            playerID: Self.pid(25),
            title: "Michael McCarron · probability timing",
            lines: ["Pregame chance 11%, recorded Oct 3, 4:52 PM (minute ending)."]
        )
        let onMcCarron = Self.input(.final, Self.finalRows, selectedID: Self.pid(25), selectedRow: Self.mccarronFinal, timing: timing)
        XCTAssertEqual(onMcCarron.timingPresentation(hasBinding: true), .disclosure(timing))
        XCTAssertEqual(onMcCarron.timingPresentation(hasBinding: false), .expanded(timing))

        // Selection moved to Shabanov, timing still McCarron's: nothing stale is shown.
        let moved = Self.input(.final, Self.finalRows, selectedID: Self.pid(24), selectedRow: Self.shabanovFinal, timing: timing)
        XCTAssertNil(moved.timingPresentation(hasBinding: true))
        XCTAssertNil(Self.input(.final, Self.finalRows, selectedID: Self.pid(99), timing: timing).timingPresentation(hasBinding: true))
    }

    @MainActor
    func testThePageOwnedTimingFlagIsHandedThroughUntouched() {
        // The view has no timing state of its own: the flag lives in the page's binding.
        var expanded = true
        let binding = Binding(get: { expanded }, set: { expanded = $0 })
        let view = ScorerExpectationPresentation10868(
            input: Self.input(.final, Self.finalRows, selectedID: Self.pid(24), selectedRow: Self.shabanovFinal),
            timingExpanded: binding
        )
        XCTAssertEqual(view.timingExpanded?.wrappedValue, true)
        expanded = false
        XCTAssertEqual(view.timingExpanded?.wrappedValue, false)
    }

    // MARK: Geometry and layout

    func testRingGeometryUsesOnlyFiniteValuesInZeroToOne() {
        XCTAssertEqual(ScorerGeometry10868.ringFraction(0), 0)
        XCTAssertEqual(ScorerGeometry10868.ringFraction(1), 1)
        XCTAssertEqual(ScorerGeometry10868.ringFraction(0.08), 0.08)
        for bad in [-0.01, 1.01, .nan, .infinity, -.infinity] {
            XCTAssertNil(ScorerGeometry10868.ringFraction(bad), "\(bad) is omitted, never clipped")
        }
        // A malformed value keeps the owner's figure.
        let malformed = Self.row(2, "Kirill Kaprizov", pregame: Self.obs(1.43, "43%", "recorded Oct 3, 4:57 PM PT · Kalshi"))
        XCTAssertEqual(Self.input(.before, [malformed]).pregameReading(malformed).text, "43%")
    }

    /// Geometry only — measured figure sizes are CONSTRUCTED stand-ins, not a
    /// rendered fit. An ordinary figure keeps the compact ring; a wider owner
    /// figure (a CONSTRUCTED "≥99.5%") widens the ring and never shrinks.
    func testTheRingKeepsItsCompactSizeAndWidensOnlyForAFigureThatWouldNotFitInside() {
        let compact: CGFloat = 64
        // 3×4×5: a 30×40 box has a 50pt diagonal; 50 + 2×4.5 = 59 fits inside 64.
        XCTAssertEqual(ScorerGeometry10868.ringSide(minimum: compact, figure: CGSize(width: 30, height: 40)), compact)
        // 60×80 → 100 + 9 = 109: the ring grows to hold the whole box.
        XCTAssertEqual(ScorerGeometry10868.ringSide(minimum: compact, figure: CGSize(width: 60, height: 80)), 109)
        XCTAssertEqual(ScorerGeometry10868.ringSide(minimum: compact, figure: .zero), compact)
        XCTAssertEqual(ScorerGeometry10868.ringSide(minimum: compact, figure: CGSize(width: CGFloat.infinity, height: 24)),
                       compact, "a non-finite measurement leaves the compact ring, never an infinite frame")
        let qualified = Self.row(2, "Kirill Kaprizov", pregame: Self.obs(0.996, "≥99.5%", "recorded Oct 3, 4:57 PM PT · Kalshi"))
        XCTAssertEqual(Self.input(.before, [qualified]).pregameReading(qualified).text, "≥99.5%",
                       "the qualifier and decimal reach the ring verbatim")
    }

    func testPipsOmitInvalidCountsAndNeverSynthesizeZero() {
        XCTAssertNil(ScorerGeometry10868.pipCount(nil))
        XCTAssertNil(ScorerGeometry10868.pipCount(-1))
        XCTAssertNil(ScorerGeometry10868.pipCount(ScorerGeometry10868.maxPips + 1))
        XCTAssertEqual(ScorerGeometry10868.pipCount(0), 0)
        XCTAssertEqual(ScorerGeometry10868.pipCount(2), 2)

        let figureOnly = Self.row(2, "Kirill Kaprizov", pregame: Self.kaprizovPregame,
                                  actual: .count(ScorerGoalCount10868(value: nil, text: "2", unit: "Final goals", accessibilityDetail: nil)))
        let input = Self.input(.final, [figureOnly])
        XCTAssertNil(input.pipCount(figureOnly))
        XCTAssertTrue(input.accessibilityValue(for: figureOnly).hasSuffix("2 Final goals"), "the figure still speaks")
    }

    func testColumnPlanTriesTwoColumnsThenOneAndStacksAtAccessibilitySizes() {
        XCTAssertEqual(ScorerGeometry10868.plans(isAccessibilitySize: false), [
            ScorerGridPlan10868(columns: 2, arrangement: .sideBySide),
            ScorerGridPlan10868(columns: 2, arrangement: .stacked),
            ScorerGridPlan10868(columns: 1, arrangement: .sideBySide),
            ScorerGridPlan10868(columns: 1, arrangement: .stacked),
        ])
        XCTAssertEqual(ScorerGeometry10868.plans(isAccessibilitySize: true), [
            ScorerGridPlan10868(columns: 1, arrangement: .sideBySide),
            ScorerGridPlan10868(columns: 1, arrangement: .stacked),
        ])
        XCTAssertEqual(ScorerGeometry10868.groups([1, 2, 3, 4, 5], columns: 2), [[1, 2], [3, 4], [5]])
        XCTAssertEqual(ScorerGeometry10868.groups([1, 2, 3], columns: 1), [[1], [2], [3]])
    }

    // MARK: VoiceOver and text

    func testSpokenTextNamesThePlayerTeamAndEachObservation() {
        let input = Self.input(.during, Self.duringRows, selectedID: Self.pid(0))
        let jeannot = Self.duringRows[2]
        XCTAssertEqual(input.accessibilityHeader, "Kalshi · player goals. Who found the net?")
        XCTAssertEqual(input.accessibilityLabel(for: jeannot), "Tanner Jeannot, Boston")
        XCTAssertEqual(input.accessibilityValue(for: jeannot),
                       "Pregame chance: 8%, recorded Oct 3, 2:42 PM PT · Kalshi; 1 goal so far, 3rd period, 14:34 left · ESPN")
        let noTeam = Self.row(24, "Max Shabanov", team: nil, pregame: Self.shabanovPregame)
        XCTAssertEqual(input.accessibilityLabel(for: noTeam), "Max Shabanov")
    }

    func testOwnerStringsArePassedThroughVerbatim() {
        let long = Self.row(
            7, "Jean-Gabriel Pageau-Longname of the Very Long Surname",
            team: "Minnesota",
            pregame: Self.obs(0.004, "<1%", "recorded Oct 3, 4:52 PM PT · Kalshi"),
            actual: Self.finalCount(0, "0", "Final goals")
        )
        let input = Self.input(.final, [long], summary: "30 recorded zero goals · 2 goal totals unavailable")
        XCTAssertEqual(input.pregameReading(long).text, "<1%")
        XCTAssertEqual(input.overview[0].name, "Jean-Gabriel Pageau-Longname of the Very Long Surname")
        XCTAssertEqual(input.summary, "30 recorded zero goals · 2 goal totals unavailable")
    }

    func testAccessibilityIdentifiersCarryTheExactPropID() {
        let id = Self.pid(24)
        XCTAssertEqual(ScorerAccessibilityID10868.tile(id), "scorer10868.tile.\(id)")
        XCTAssertEqual(ScorerAccessibilityID10868.outside(id), "scorer10868.outside.\(id)")
        XCTAssertEqual(ScorerAccessibilityID10868.comparison(id), "scorer10868.comparison.\(id)")
        XCTAssertEqual(ScorerAccessibilityID10868.details(id), "scorer10868.details.\(id)")
    }
}
