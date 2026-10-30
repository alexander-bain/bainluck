import SwiftUI
import XCTest
@testable import Bain_Luck

/// #10868 — "Both teams to score" as a stateless presentation leaf across
/// pregame, live and final.
///
/// The view is SwiftUI and is not rasterised here. What is asserted is the
/// rules it defers to: which readings each phase shows, the independence of the
/// two original outcomes, zero versus unknown, the exact-id selection, the
/// action each control carries, the timing it may show, the ring and pair
/// geometry and the spoken text. Nothing here claims a rendered fit.
///
/// ARCHIVED raw values come from Valladolid–Albacete, event 15325054, as
/// extracted in `shipping-adoption-20261027/BOTH-TEAMS-RETAINED-CASES.json`
/// (sha256 67f1e3fa…c1929), which binds `liveSoccer.json` (d835ccdf…7d2) and
/// `soccerFinal.json` (05de3275…8ffe):
///   market 64353426 "Both teams to score"
///   Yes 242143189: pregame_pin 0.55  @ 2026-10-12T11:47:12.295868Z, final result lost
///   No  242143190: pregame_pin 0.455 @ 2026-10-12T11:47:12.295868Z, final result won
///   (0.55 + 0.455 = 1.005 — independent readings, not complements)
///   Live: current null for both. The last raw quotes Yes 0.49 / No 0.505
///   @ 12:54:58.549918Z are NOT admitted current readings and are not inputs.
///   Live score 4–0 observed 12:54:19.676980Z; final 5–0, completed 13:57:41Z.
///
/// CONSTRUCTED owner-resolved inputs (this leaf does not resolve them): every
/// display string and PT time/source line, the scoring status words, the
/// headline and context lines, the result wording, every admitted current
/// observation (the retained fixture has none), withheld/reached states,
/// movement text, and the malformed, duplicate, missing and long-figure cases.
final class BothTeamsScorePresentation10868Tests: XCTestCase {

    // MARK: Fixtures

    private static let eventID = "15325054"
    private static let marketID = "64353426"
    private static let yesID = "242143189"
    private static let noID = "242143190"

    private static func obs(_ probability: Double, _ text: String, _ time: String?, _ detail: String) -> BothTeamsObservation10868 {
        BothTeamsObservation10868(probability: probability, text: text, timeText: time, accessibilityDetail: detail)
    }

    // Pregame (ARCHIVED value and clock, CONSTRUCTED text).
    private static let yesPregame = obs(0.55, "55%", "4:47 AM PT", "recorded Oct 12, 4:47 AM PT · Polymarket")
    private static let noPregame = obs(0.455, "45.5%", "4:47 AM PT", "recorded Oct 12, 4:47 AM PT · Polymarket")

    /// CONSTRUCTED admitted current observation with its own clock.
    private static let yesCurrent = obs(0.62, "62%", "5:55 AM PT", "recorded Oct 12, 5:55 AM PT · Polymarket")

    private static let noCurrent = BothTeamsCurrent10868.unavailable("No current chance")
    private static let pending = BothTeamsResult10868.unconfirmed("Result pending")

    private static func outcome(
        _ id: String,
        _ label: String,
        pregame: BothTeamsObservation10868?,
        current: BothTeamsCurrent10868 = noCurrent,
        result: BothTeamsResult10868 = pending
    ) -> BothTeamsOutcome10868 {
        BothTeamsOutcome10868(
            id: id,
            label: label,
            before: pregame,
            beforeMissing: "No pregame chance",
            current: current,
            result: result
        )
    }

    private static func team(_ name: String, _ text: String, _ status: String?) -> BothTeamsTeam10868 {
        BothTeamsTeam10868(name: name, actual: .count(text: text, status: status))
    }

    /// 12:54:19Z checkpoint, 4–0 (ARCHIVED counts, CONSTRUCTED words).
    private static let liveScoring = BothTeamsScoring10868(
        title: "Actual goals",
        home: team("Valladolid", "4", "has scored"),
        away: team("Albacete", "0", "yet to score"),
        clock: "Recorded 5:54 AM PT",
        accessibilityDetail: "score recorded Oct 12, 5:54 AM PT · ESPN"
    )

    /// Final 5–0 (ARCHIVED counts, CONSTRUCTED words).
    private static let finalScoring = BothTeamsScoring10868(
        title: "Final goals",
        home: team("Valladolid", "5", nil),
        away: team("Albacete", "0", nil),
        clock: "Final · 6:57 AM PT",
        accessibilityDetail: nil
    )

    private static let notStarted = BothTeamsScoring10868(
        title: "Actual goals",
        home: BothTeamsTeam10868(name: "Valladolid", actual: .unavailable("Not started")),
        away: BothTeamsTeam10868(name: "Albacete", actual: .unavailable("Not started")),
        clock: nil,
        accessibilityDetail: nil
    )

    private static func input(
        _ phase: BothTeamsPhase10868,
        _ outcomes: [BothTeamsOutcome10868],
        selected: String? = yesID,
        scoring: BothTeamsScoring10868 = liveScoring,
        timing: BothTeamsTiming10868? = nil,
        beforeContext: String? = "At least one goal each"
    ) -> BothTeamsScoreInput10868 {
        BothTeamsScoreInput10868(
            phase: phase,
            eventID: eventID,
            marketID: marketID,
            eyebrow: "Both teams to score",
            subtitle: nil,
            title: nil,
            beforeContext: beforeContext,
            outcomes: outcomes,
            selectedOutcomeID: selected,
            scoring: scoring,
            timing: timing
        )
    }

    /// The retained live rows: both currents absent, no admitted result yet.
    private static var retainedLive: [BothTeamsOutcome10868] {
        [outcome(yesID, "Yes", pregame: yesPregame), outcome(noID, "No", pregame: noPregame)]
    }

    /// The retained final rows: Yes lost, No won (prop-64353426.json).
    private static var retainedFinal: [BothTeamsOutcome10868] {
        [
            outcome(yesID, "Yes", pregame: yesPregame, result: .lost("Lost")),
            outcome(noID, "No", pregame: noPregame, result: .won("Won")),
        ]
    }

    /// Every later input supplied, to prove the earlier phases hide them.
    private static var everythingSupplied: [BothTeamsOutcome10868] {
        [
            outcome(yesID, "Yes", pregame: yesPregame, current: .recorded(yesCurrent, movement: "+7 points since pregame"), result: .lost("Lost")),
            outcome(noID, "No", pregame: noPregame, current: .withheld("No update since goal"), result: .won("Won")),
        ]
    }

    // MARK: Before

    func testBeforeHidesScoringCurrentMovementAndResult() {
        let model = Self.input(.before, Self.everythingSupplied)
        XCTAssertFalse(model.showsScoring)
        XCTAssertNil(model.visibleScoring)
        XCTAssertNil(model.accessibilityScoring)
        XCTAssertNil(model.comparisonOutcome)
        XCTAssertNil(model.selectedResult)
        for outcome in model.outcomes {
            XCTAssertNil(model.currentReading(outcome))
            XCTAssertNil(model.currentTitle(outcome))
            XCTAssertNil(model.movement(outcome))
            XCTAssertNil(model.result(outcome))
            XCTAssertFalse(model.showsCurrentMark(outcome))
        }
        XCTAssertEqual(model.visibleBeforeContext, "At least one goal each")
        XCTAssertEqual(model.ring, .value(label: "Yes", observation: Self.yesPregame))
        XCTAssertEqual(model.ringTimeText, "4:47 AM PT")
    }

    func testBeforeSpokenTextCarriesNoLaterFacts() {
        let model = Self.input(.before, Self.everythingSupplied)
        let yes = model.outcomes[0]
        let spoken = model.accessibilityOptionValue(yes)
        XCTAssertEqual(spoken, "Pregame chance: 55%; Selected")
        for later in ["62%", "Lost", "Won", "4", "Result", "Current"] {
            XCTAssertFalse(spoken.contains(later), later)
        }
        XCTAssertTrue(model.accessibilityHeader.hasSuffix("Before play"))
    }

    func testBeforeContextIsReadOnlyBeforePlay() {
        XCTAssertNil(Self.input(.during, Self.retainedLive).visibleBeforeContext)
        XCTAssertNil(Self.input(.final, Self.retainedFinal, scoring: Self.finalScoring).visibleBeforeContext)
        XCTAssertNil(Self.input(.before, Self.retainedLive, beforeContext: nil).visibleBeforeContext)
    }

    // MARK: Independence

    func testYesAndNoPregameAreIndependentNotComplements() {
        let yesModel = Self.input(.before, Self.retainedLive, selected: Self.yesID)
        let noModel = Self.input(.before, Self.retainedLive, selected: Self.noID)
        XCTAssertEqual(yesModel.ring, .value(label: "Yes", observation: Self.yesPregame))
        XCTAssertEqual(noModel.ring, .value(label: "No", observation: Self.noPregame))
        // The No ring is its own 0.455 — not 1 − 0.55 — and the figures are verbatim.
        XCTAssertEqual(BothTeamsGeometry10868.ringFraction(Self.noPregame.probability), 0.455)
        XCTAssertNotEqual(BothTeamsGeometry10868.ringFraction(Self.noPregame.probability), 1 - 0.55)
        XCTAssertEqual(noModel.ringCaption, "Pregame · No")
        XCTAssertEqual(yesModel.beforeReading(yesModel.outcomes[1]), .value(Self.noPregame))
        XCTAssertTrue(yesModel.accessibilityOptionValue(yesModel.outcomes[1]).hasPrefix("Pregame chance: 45.5%"))
    }

    // MARK: During

    func testDuringRetainedFourNilSeparatesPregameCurrentAndActual() {
        // A supplied result must not appear during play.
        let rows = [
            Self.outcome(Self.yesID, "Yes", pregame: Self.yesPregame, result: .lost("Lost")),
            Self.outcome(Self.noID, "No", pregame: Self.noPregame, result: .won("Won")),
        ]
        let model = Self.input(.during, rows)
        let yes = model.outcomes[0]
        XCTAssertEqual(model.comparisonOutcome, yes)
        XCTAssertEqual(model.beforeReading(yes), .value(Self.yesPregame))
        XCTAssertEqual(model.currentReading(yes), .missing("No current chance"))
        XCTAssertEqual(model.currentTitle(yes), "Current chance")
        XCTAssertFalse(model.showsCurrentMark(yes))
        XCTAssertEqual(model.visibleScoring, Self.liveScoring)
        XCTAssertNil(model.result(yes))
        XCTAssertNil(model.selectedResult)
        XCTAssertNil(model.ringTimeText, "during play the comparison carries the pregame clock")
    }

    func testDuringLastRawQuoteIsNeverACurrentReading() {
        // The retained fixture's only current input is the owner's absence words.
        let model = Self.input(.during, Self.retainedLive)
        for outcome in model.outcomes {
            let spoken = model.accessibilityComparison(outcome) + model.accessibilityOptionValue(outcome)
            XCTAssertFalse(spoken.contains("49%"))
            XCTAssertFalse(spoken.contains("50.5%"))
            XCTAssertTrue(spoken.contains("Current chance: No current chance"))
        }
    }

    func testDuringConstructedAdmittedCurrentHasItsOwnClockAndMovement() {
        let rows = [
            Self.outcome(Self.yesID, "Yes", pregame: Self.yesPregame, current: .recorded(Self.yesCurrent, movement: "+7 points since pregame")),
            Self.outcome(Self.noID, "No", pregame: Self.noPregame),
        ]
        let model = Self.input(.during, rows)
        let yes = model.outcomes[0]
        XCTAssertEqual(model.currentReading(yes), .value(Self.yesCurrent))
        XCTAssertTrue(model.showsCurrentMark(yes))
        XCTAssertEqual(model.movement(yes), "+7 points since pregame")
        XCTAssertEqual(Self.yesPregame.timeText, "4:47 AM PT")
        XCTAssertEqual(Self.yesCurrent.timeText, "5:55 AM PT")
        XCTAssertEqual(
            model.accessibilityComparison(yes),
            "Pregame chance: 55%, recorded Oct 12, 4:47 AM PT · Polymarket; "
                + "Current chance: 62%, recorded Oct 12, 5:55 AM PT · Polymarket; +7 points since pregame"
        )
        // The other outcome's current state is its own, not derived from Yes.
        XCTAssertEqual(model.currentReading(model.outcomes[1]), .missing("No current chance"))
    }

    func testDuringWithheldAndUnavailableKeepTheirWords() {
        let rows = [
            Self.outcome(Self.yesID, "Yes", pregame: Self.yesPregame, current: .withheld("No update since goal")),
            Self.outcome(Self.noID, "No", pregame: Self.noPregame, current: .unavailable("No current chance")),
        ]
        let model = Self.input(.during, rows)
        XCTAssertEqual(model.currentReading(model.outcomes[0]), .missing("No update since goal"))
        XCTAssertEqual(model.currentReading(model.outcomes[1]), .missing("No current chance"))
        XCTAssertNil(model.movement(model.outcomes[0]))
        XCTAssertFalse(model.showsCurrentMark(model.outcomes[0]))
        XCTAssertEqual(model.accessibilityOptionValue(model.outcomes[1]), "Pregame chance: 45.5%; Current chance: No current chance")
    }

    func testDuringReachedIsActualSoFarNotAChanceOrResult() {
        let rows = [
            Self.outcome(Self.yesID, "Yes", pregame: Self.yesPregame, current: .reached("Both teams have scored")),
            Self.outcome(Self.noID, "No", pregame: Self.noPregame),
        ]
        let model = Self.input(.during, rows)
        let yes = model.outcomes[0]
        XCTAssertEqual(model.currentReading(yes), .reached("Both teams have scored"))
        XCTAssertEqual(model.currentTitle(yes), "Actual so far")
        XCTAssertEqual(model.currentShortTitle(yes), "Actual so far")
        XCTAssertFalse(model.showsCurrentMark(yes))
        XCTAssertNil(model.result(yes))
        let spoken = model.accessibilityComparison(yes)
        XCTAssertTrue(spoken.contains("Actual so far: Both teams have scored"))
        XCTAssertFalse(spoken.contains("100%"))
        XCTAssertFalse(spoken.contains("Won"))
    }

    func testOneMissingActualIsWordsNotZero() {
        let scoring = BothTeamsScoring10868(
            title: "Actual goals",
            home: Self.team("Valladolid", "4", "has scored"),
            away: BothTeamsTeam10868(name: "Albacete", actual: .unavailable("Score unavailable")),
            clock: nil,
            accessibilityDetail: nil
        )
        let model = Self.input(.during, Self.retainedLive, scoring: scoring)
        XCTAssertEqual(model.accessibilityScoring, "Actual goals: Valladolid 4, has scored; Albacete: Score unavailable")
        XCTAssertFalse(model.accessibilityScoring?.contains("Albacete 0") ?? true)
    }

    func testKnownZeroDiffersFromUnknownCount() {
        let zero = Self.input(.during, Self.retainedLive)
        let unknown = Self.input(.during, Self.retainedLive, scoring: Self.notStarted)
        XCTAssertEqual(
            zero.accessibilityScoring,
            "Actual goals: Valladolid 4, has scored; Albacete 0, yet to score. score recorded Oct 12, 5:54 AM PT · ESPN"
        )
        XCTAssertEqual(unknown.accessibilityScoring, "Actual goals: Valladolid: Not started; Albacete: Not started")
        XCTAssertNotEqual(zero.scoring.away.actual, unknown.scoring.away.actual)
    }

    // MARK: Final

    func testFinalRetainedFiveNilYesLostNoWon() {
        let model = Self.input(.final, Self.retainedFinal, scoring: Self.finalScoring)
        let yes = model.outcomes[0]
        let no = model.outcomes[1]
        XCTAssertEqual(model.result(yes), .lost("Lost"))
        XCTAssertEqual(model.result(no), .won("Won"))
        XCTAssertEqual(model.ring, .value(label: "Yes", observation: Self.yesPregame))
        XCTAssertEqual(model.ringTimeText, "4:47 AM PT")
        XCTAssertEqual(model.visibleScoring, Self.finalScoring)
        XCTAssertEqual(model.accessibilityScoring, "Final goals: Valladolid 5; Albacete 0")
        XCTAssertEqual(model.selectedResult?.outcome, yes)
        XCTAssertEqual(model.selectedResult?.result, .lost("Lost"))
        XCTAssertEqual(model.accessibilityResult(yes, .lost("Lost")), "Result for Yes: Lost")
        XCTAssertEqual(model.accessibilityOptionValue(no), "Pregame chance: 45.5%; Result: Won")
        XCTAssertTrue(model.accessibilityHeader.hasSuffix("Final"))
    }

    func testFinalIgnoresSuppliedCurrentSoSettlementIsNeverAChance() {
        let settled = Self.obs(1.0, "100%", "6:58 AM PT", "settled price")
        let rows = [
            Self.outcome(Self.yesID, "Yes", pregame: Self.yesPregame, current: .recorded(Self.obs(0.0, "0%", nil, "settled price"), movement: "−55 points"), result: .lost("Lost")),
            Self.outcome(Self.noID, "No", pregame: Self.noPregame, current: .recorded(settled, movement: nil), result: .won("Won")),
        ]
        let model = Self.input(.final, rows, scoring: Self.finalScoring)
        XCTAssertNil(model.comparisonOutcome)
        for outcome in model.outcomes {
            XCTAssertNil(model.currentReading(outcome))
            XCTAssertNil(model.movement(outcome))
            XCTAssertFalse(model.showsCurrentMark(outcome))
            let spoken = model.accessibilityOptionValue(outcome)
            XCTAssertFalse(spoken.contains("100%"))
            XCTAssertFalse(spoken.contains("0%;"))
        }
        XCTAssertEqual(model.ring, .value(label: "Yes", observation: Self.yesPregame))
    }

    func testFinalUnconfirmedResultIsNotALoss() {
        let model = Self.input(.final, Self.retainedLive, scoring: Self.finalScoring)
        let yes = model.outcomes[0]
        XCTAssertEqual(model.result(yes), .unconfirmed("Result pending"))
        XCTAssertEqual(model.accessibilityResult(yes, .unconfirmed("Result pending")), "Result for Yes: Result pending")
        XCTAssertFalse(model.accessibilityOptionValue(yes).contains("Lost"))
    }

    func testActualAndResultAreSeparateAdmissions() {
        // Result known, final count unknown: both stay explicit.
        let unknownCount = BothTeamsScoring10868(
            title: "Final goals",
            home: BothTeamsTeam10868(name: "Valladolid", actual: .unavailable("Final score unavailable")),
            away: BothTeamsTeam10868(name: "Albacete", actual: .unavailable("Final score unavailable")),
            clock: nil,
            accessibilityDetail: nil
        )
        let known = Self.input(.final, Self.retainedFinal, scoring: unknownCount)
        XCTAssertEqual(known.result(known.outcomes[0]), .lost("Lost"))
        XCTAssertEqual(known.accessibilityScoring, "Final goals: Valladolid: Final score unavailable; Albacete: Final score unavailable")
        // Count known (5–0), result not yet admitted: no result is derived from the count.
        let unresolved = Self.input(.final, Self.retainedLive, scoring: Self.finalScoring)
        XCTAssertEqual(unresolved.result(unresolved.outcomes[0]), .unconfirmed("Result pending"))
        XCTAssertEqual(unresolved.result(unresolved.outcomes[1]), .unconfirmed("Result pending"))
    }

    func testVoidResultKeepsOwnerWords() {
        let rows = [Self.outcome(Self.yesID, "Yes", pregame: Self.yesPregame, result: .void("Void · refunded"))]
        let model = Self.input(.final, rows, scoring: Self.finalScoring)
        XCTAssertEqual(model.result(model.outcomes[0])?.text, "Void · refunded")
    }

    // MARK: Selection and callbacks

    func testMissingSelectionKeepsBothOptionsAndResolvesNobody() {
        let model = Self.input(.during, Self.retainedLive, selected: "242143999")
        XCTAssertEqual(model.selection, .missing("242143999"))
        XCTAssertEqual(model.selectionNotice, "Selected outcome unavailable.")
        XCTAssertEqual(model.outcomes.map(\.id), [Self.yesID, Self.noID])
        XCTAssertFalse(model.outcomes.contains { model.isSelected($0) })
        XCTAssertNil(model.comparisonOutcome)
        XCTAssertEqual(model.ring, .unselected("Selected outcome unavailable."))
        XCTAssertNil(model.detailsAction(canOpenDetails: true))
        XCTAssertNotNil(model.optionAction(model.outcomes[1], canSelect: true))
    }

    func testDuplicateSelectionResolvesNobody() {
        let rows = Self.retainedLive + [Self.outcome(Self.yesID, "Yes", pregame: Self.yesPregame)]
        let model = Self.input(.final, rows, scoring: Self.finalScoring)
        XCTAssertEqual(model.selection, .duplicate(Self.yesID))
        XCTAssertEqual(model.outcomes.count, 3)
        XCTAssertFalse(model.outcomes.contains { model.isSelected($0) })
        XCTAssertNil(model.selectedResult)
        XCTAssertEqual(model.ring, .unselected("Selected outcome unavailable."))
        XCTAssertEqual(model.ringCaption, "Pregame chance")
    }

    func testNoSelectionIsQuietAndTheRingStaysNamed() {
        let model = Self.input(.during, Self.retainedLive, selected: nil)
        XCTAssertEqual(model.selection, .none)
        XCTAssertNil(model.selectionNotice)
        XCTAssertEqual(model.ring, .unselected("No outcome selected"))
        XCTAssertEqual(model.ringCaption, "Pregame chance")
        XCTAssertEqual(model.accessibilityRing, "Pregame chance: No outcome selected")
        XCTAssertNil(model.ringTimeText)
    }

    func testSelectAndDetailsPassExactOriginalIdentity() {
        let model = Self.input(.during, Self.retainedLive)
        var selected: [BothTeamsOutcomeRef10868] = []
        var opened: [BothTeamsOutcomeRef10868] = []
        let onSelect: (BothTeamsOutcomeRef10868) -> Void = { selected.append($0) }
        let onDetails: (BothTeamsOutcomeRef10868) -> Void = { opened.append($0) }

        model.optionAction(model.outcomes[1], canSelect: true)?.perform(onSelect: onSelect, onDetails: onDetails)
        model.detailsAction(canOpenDetails: true)?.perform(onSelect: onSelect, onDetails: onDetails)

        XCTAssertEqual(selected, [BothTeamsOutcomeRef10868(eventID: "15325054", marketID: "64353426", outcomeID: "242143190")])
        XCTAssertEqual(opened, [BothTeamsOutcomeRef10868(eventID: "15325054", marketID: "64353426", outcomeID: "242143189")])
    }

    func testNoCallbackMeansNoActionAndNoInstruction() {
        let model = Self.input(.during, Self.retainedLive)
        for outcome in model.outcomes {
            XCTAssertNil(model.optionAction(outcome, canSelect: false))
        }
        XCTAssertNil(model.detailsAction(canOpenDetails: false))
        XCTAssertNil(model.instruction(canSelect: false))
        XCTAssertEqual(model.instruction(canSelect: true), "Choose an outcome to compare.")
        XCTAssertNil(Self.input(.during, []).instruction(canSelect: true))
    }

    func testSelectionUsesExactIDNotLabel() {
        // A label match is not an id match.
        let model = Self.input(.during, Self.retainedLive, selected: "Yes")
        XCTAssertEqual(model.selection, .missing("Yes"))
    }

    // MARK: Geometry

    func testRingFractionForZeroOneAndInvalid() {
        XCTAssertEqual(BothTeamsGeometry10868.ringFraction(0), 0)
        XCTAssertEqual(BothTeamsGeometry10868.ringFraction(1), 1)
        XCTAssertEqual(BothTeamsGeometry10868.ringFraction(0.55), 0.55)
        XCTAssertNil(BothTeamsGeometry10868.ringFraction(-0.01))
        XCTAssertNil(BothTeamsGeometry10868.ringFraction(1.01))
        XCTAssertNil(BothTeamsGeometry10868.ringFraction(.nan))
        XCTAssertNil(BothTeamsGeometry10868.ringFraction(.infinity))
    }

    func testMissingPregameIsNotAZeroRing() {
        let rows = [Self.outcome(Self.yesID, "Yes", pregame: nil), Self.outcome(Self.noID, "No", pregame: Self.noPregame)]
        let model = Self.input(.before, rows)
        XCTAssertEqual(model.ring, .missing(label: "Yes", words: "No pregame chance"))
        XCTAssertEqual(model.ringCaption, "Pregame · Yes")
        XCTAssertNil(model.ringTimeText)
        XCTAssertEqual(model.accessibilityRing, "Pregame chance, Yes: No pregame chance")
        XCTAssertEqual(model.beforeReading(model.outcomes[0]), .missing("No pregame chance"))
        // A real zero is a value with a zero arc, not the missing state.
        let zeroRows = [Self.outcome(Self.yesID, "Yes", pregame: Self.obs(0, "0%", nil, "recorded"))]
        XCTAssertEqual(Self.input(.before, zeroRows).ring, .value(label: "Yes", observation: Self.obs(0, "0%", nil, "recorded")))
    }

    func testRingGrowsToReserveTheWholeFigure() {
        // CONSTRUCTED measured sizes; no rendered fit is claimed.
        let ordinary = BothTeamsGeometry10868.ringSide(minimum: 104, figure: CGSize(width: 70, height: 38))
        XCTAssertEqual(ordinary, 104)
        let wide = BothTeamsGeometry10868.ringSide(minimum: 104, figure: CGSize(width: 120, height: 50))
        XCTAssertEqual(wide, (130 + 2 * BothTeamsGeometry10868.ringInset).rounded(.up))
        XCTAssertGreaterThan(wide, 104)
        XCTAssertEqual(BothTeamsGeometry10868.ringSide(minimum: 104, figure: CGSize(width: CGFloat.infinity, height: 10)), 104)
        XCTAssertEqual(BothTeamsGeometry10868.ringInset, BothTeamsGeometry10868.ringLineWidth + 4)
    }

    func testPairArrangementKeepsWholeWidthsOrStacks() {
        typealias G = BothTeamsGeometry10868
        // Equal columns: each column must fit the wider figure.
        XCTAssertEqual(G.pairArrangement(available: 300, first: 120, second: 140, spacing: 16, equalColumns: true, forceStack: false), .sideBySide)
        XCTAssertEqual(G.pairArrangement(available: 290, first: 120, second: 140, spacing: 16, equalColumns: true, forceStack: false), .stacked)
        // Unequal: the sum must fit.
        XCTAssertEqual(G.pairArrangement(available: 290, first: 120, second: 140, spacing: 16, equalColumns: false, forceStack: false), .sideBySide)
        XCTAssertEqual(G.pairArrangement(available: 270, first: 120, second: 140, spacing: 16, equalColumns: false, forceStack: false), .stacked)
        // Accessibility sizes always stack; an unspecified width keeps the pair.
        XCTAssertEqual(G.pairArrangement(available: 2000, first: 10, second: 10, spacing: 16, equalColumns: true, forceStack: true), .stacked)
        XCTAssertEqual(G.pairArrangement(available: nil, first: 120, second: 140, spacing: 16, equalColumns: true, forceStack: false), .sideBySide)
        XCTAssertEqual(G.pairArrangement(available: 300, first: .nan, second: 140, spacing: 16, equalColumns: true, forceStack: false), .stacked)
    }

    func testColumnWidths() {
        typealias G = BothTeamsGeometry10868
        XCTAssertEqual(G.columns(total: 316, first: 120, spacing: 16, equalColumns: true), BothTeamsColumns10868(first: 150, second: 150))
        XCTAssertEqual(G.columns(total: 316, first: 120, spacing: 16, equalColumns: false), BothTeamsColumns10868(first: 120, second: 180))
        XCTAssertEqual(G.neededWidth(first: 120, second: 140, spacing: 16, equalColumns: true), 296)
        XCTAssertEqual(G.neededWidth(first: 120, second: 140, spacing: 16, equalColumns: false), 276)
    }

    // MARK: Timing and spoken text

    func testTimingOnlyForTheResolvedSelection() {
        let timing = BothTeamsTiming10868(outcomeID: Self.yesID, title: "Yes · probability timing", lines: ["Pregame recorded Oct 12, 4:47 AM PT"])
        let model = Self.input(.during, Self.retainedLive, timing: timing)
        XCTAssertEqual(model.timingPresentation(hasBinding: true), .disclosure(timing))
        XCTAssertEqual(model.timingPresentation(hasBinding: false), .expanded(timing))
        XCTAssertNil(Self.input(.during, Self.retainedLive, selected: Self.noID, timing: timing).timingPresentation(hasBinding: true))
        XCTAssertNil(Self.input(.during, Self.retainedLive, selected: nil, timing: timing).timingPresentation(hasBinding: true))
        XCTAssertNil(Self.input(.during, Self.retainedLive, selected: "x", timing: timing).timingPresentation(hasBinding: true))
    }

    func testSpokenPhaseLabels() {
        XCTAssertEqual(Self.input(.before, Self.retainedLive).phaseSpoken, "Before play")
        XCTAssertEqual(Self.input(.during, Self.retainedLive).phaseSpoken, "During play")
        XCTAssertEqual(Self.input(.final, Self.retainedFinal, scoring: Self.finalScoring).phaseSpoken, "Final")
        let titled = BothTeamsScoreInput10868(
            phase: .during, eventID: Self.eventID, marketID: Self.marketID,
            eyebrow: "Both teams to score", subtitle: "One team is still scoreless",
            title: "Still waiting for Albacete.", beforeContext: nil,
            outcomes: Self.retainedLive, selectedOutcomeID: Self.yesID,
            scoring: Self.liveScoring, timing: nil
        )
        XCTAssertEqual(titled.accessibilityHeader, "Both teams to score. One team is still scoreless. Still waiting for Albacete.. During play")
    }

    func testSpokenRingNamesTheOutcomeAndItsProvenance() {
        let model = Self.input(.during, Self.retainedLive)
        XCTAssertEqual(model.accessibilityRing, "Pregame chance, Yes: 55%, recorded Oct 12, 4:47 AM PT · Polymarket")
        XCTAssertEqual(model.ringCaption, "Pregame · Yes")
    }

    func testOptionSpokenValuePerPhase() {
        let rows = Self.everythingSupplied
        let before = Self.input(.before, rows)
        let during = Self.input(.during, rows)
        let final = Self.input(.final, rows, scoring: Self.finalScoring)
        XCTAssertEqual(before.accessibilityOptionValue(rows[1]), "Pregame chance: 45.5%")
        XCTAssertEqual(during.accessibilityOptionValue(rows[0]), "Pregame chance: 55%; Current chance: 62%; Selected")
        XCTAssertEqual(during.accessibilityOptionValue(rows[1]), "Pregame chance: 45.5%; Current chance: No update since goal")
        XCTAssertEqual(final.accessibilityOptionValue(rows[0]), "Pregame chance: 55%; Result: Lost; Selected")
    }

    func testAccessibilityIdentifiersCarryExactIDs() {
        XCTAssertEqual(BothTeamsAccessibilityID10868.option(Self.yesID), "bothTeams10868.option.242143189")
        XCTAssertEqual(BothTeamsAccessibilityID10868.details(Self.noID), "bothTeams10868.details.242143190")
        XCTAssertEqual(BothTeamsAccessibilityID10868.comparison(Self.yesID), "bothTeams10868.comparison.242143189")
        XCTAssertEqual(BothTeamsAccessibilityID10868.result(Self.noID), "bothTeams10868.result.242143190")
    }
}
