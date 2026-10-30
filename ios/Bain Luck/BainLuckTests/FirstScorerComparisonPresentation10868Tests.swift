import SwiftUI
import XCTest
@testable import Bain_Luck

/// #10868 — "Who scored first?" as a stateless presentation leaf across
/// pregame, live and final.
///
/// The view is SwiftUI and is not rasterised here. What is asserted is the
/// rules it defers to: which readings each phase shows, the exact-id
/// selection, when the confirmed-winner return appears, the action each
/// control carries, the timing it may show, the plot geometry and the spoken
/// text. Nothing here claims a rendered fit.
///
/// ARCHIVED raw values come from Minnesota–Boston, event 15169793, first-scorer
/// market 64870910 (independent of anytime-goals market 64870965), as copied in
/// `shipping-adoption-20261027/FIRST-SCORER-RETAINED-CASES.json` from
/// `hockeyScoring.json` (9fd311a6…8d2e) and `hockeyFirstPregame.json`
/// (b51e6058…63dd):
///   Jeannot  :other:0   no first-scorer baseline; is_winner true (api_settlement)
///   Coleman  :other:1   0.06 @ 2026-10-03T23:11Z; is_winner false
///   Eriksson Ek :other:14 0.08 @ 23:34Z; is_winner false
///   Kaprizov :other:17  0.10 @ 23:57Z; is_winner false
///   Boldy    :other:22  0.09 @ 23:50Z; is_winner false
///   Shabanov :other:23  0.08 @ 23:53Z; is_winner false
/// Jeannot's anytime 8% belongs to the other market and is never used here.
///
/// CONSTRUCTED owner-resolved inputs (this leaf does not resolve them): every
/// display string and PT time/source line; the result words; the axis bounds
/// and tick labels; the confirmed-winner caption; every during-play state —
/// there is no retained live first-scorer price series, so the recorded
/// in-game readings below are synthetic owner inputs, never captured quotes;
/// and the malformed, duplicate, mismatched and long-text cases.
final class FirstScorerComparisonPresentation10868Tests: XCTestCase {

    // MARK: Fixtures

    private static func pid(_ index: Int) -> String { "nhl-15169793-game-markets.json:other:\(index)" }

    private static func obs(_ probability: Double, _ text: String, _ detail: String) -> FirstScorerObservation10868 {
        FirstScorerObservation10868(probability: probability, text: text, accessibilityDetail: detail)
    }

    private static let noCurrent = FirstScorerCurrent10868.unavailable("No in-game reading")
    private static let pending = FirstScorerResult10868.unconfirmed("No first goal yet")
    private static let scoredFirst = FirstScorerResult10868.scoredFirst("Scored first")
    private static let notFirst = FirstScorerResult10868.notFirst("Not first")

    private static func row(
        _ index: Int,
        _ name: String,
        team: String? = "Minnesota",
        pregame: FirstScorerObservation10868?,
        current: FirstScorerCurrent10868 = noCurrent,
        result: FirstScorerResult10868 = pending
    ) -> FirstScorerRow10868 {
        FirstScorerRow10868(
            id: pid(index),
            name: name,
            team: team,
            pregame: pregame,
            pregameMissing: "Unavailable",
            current: current,
            result: result
        )
    }

    /// The reference's shared 0–10% scale (CONSTRUCTED labels).
    private static let tenPercent = FirstScorerAxis10868(
        lower: 0,
        upper: 0.10,
        ticks: [
            FirstScorerTick10868(value: 0, text: "0%"),
            FirstScorerTick10868(value: 0.05, text: "5%"),
            FirstScorerTick10868(value: 0.10, text: "10%"),
        ]
    )

    private static let jeannotConfirmed = FirstScorerConfirmed10868(
        id: pid(0), name: "Tanner Jeannot", caption: "First goalscorer · confirmed result"
    )

    private static func input(
        _ phase: FirstScorerPhase10868,
        _ overview: [FirstScorerRow10868],
        selectedID: String? = nil,
        selectedRow: FirstScorerRow10868? = nil,
        axis: FirstScorerAxis10868 = tenPercent,
        coverage: String? = nil,
        confirmed: FirstScorerConfirmed10868? = nil,
        timing: FirstScorerTiming10868? = nil
    ) -> FirstScorerComparisonInput10868 {
        FirstScorerComparisonInput10868(
            phase: phase,
            title: "Who scored first?",
            context: "Kalshi · first goalscorer",
            overview: overview,
            selectedID: selectedID,
            selectedRow: selectedRow,
            plotTitle: "Highest captured pregame chances",
            axis: axis,
            coverage: coverage,
            confirmed: confirmed,
            timing: timing
        )
    }

    // First-scorer baselines (ARCHIVED value and time, CONSTRUCTED text/detail).
    private static let kaprizovPregame = obs(0.10, "10%", "minute ending Oct 3, 4:57 PM PT · Kalshi")
    private static let boldyPregame = obs(0.09, "9%", "minute ending Oct 3, 4:50 PM PT · Kalshi")
    private static let erikssonEkPregame = obs(0.08, "8%", "minute ending Oct 3, 4:34 PM PT · Kalshi")
    private static let shabanovPregame = obs(0.08, "8%", "minute ending Oct 3, 4:53 PM PT · Kalshi")
    private static let colemanPregame = obs(0.06, "6%", "minute ending Oct 3, 4:11 PM PT · Kalshi")

    /// CONSTRUCTED in-game reading before the first goal — not a captured quote.
    private static let boldyRecorded = obs(0.14, "14%", "recorded Oct 3, 5:10 PM PT · Kalshi")

    private static func plotRows(result: (Int) -> FirstScorerResult10868) -> [FirstScorerRow10868] {
        [
            row(17, "Kirill Kaprizov", pregame: kaprizovPregame, result: result(17)),
            row(22, "Matt Boldy", pregame: boldyPregame, result: result(22)),
            row(14, "Joel Eriksson Ek", pregame: erikssonEkPregame, result: result(14)),
            row(23, "Max Shabanov", team: "Team unavailable", pregame: shabanovPregame, result: result(23)),
        ]
    }

    private static var pregameRows: [FirstScorerRow10868] { plotRows { _ in pending } }
    private static var finalRows: [FirstScorerRow10868] { plotRows { _ in notFirst } }

    private static var jeannotFinal: FirstScorerRow10868 {
        row(0, "Tanner Jeannot", team: "Boston", pregame: nil, result: scoredFirst)
    }

    // MARK: Pregame

    func testBeforeShowsSavedChancesAndTheSelectedPlayerWithNoResultOrCurrentColumn() {
        let rows = Self.pregameRows
        let input = Self.input(.before, rows, selectedID: Self.pid(22))

        XCTAssertEqual(input.selection, .overview(rows[1]))
        for row in rows {
            XCTAssertNil(input.secondReading(row), "no current, result or actual column before play")
            XCTAssertFalse(input.showsCurrentMark(row))
        }
        XCTAssertEqual(input.pregameReading(rows[1]), .value(Self.boldyPregame))
        XCTAssertEqual(input.accessibilityComparison(for: rows[1]),
                       "Pregame first-goalscorer chance: 9%, minute ending Oct 3, 4:50 PM PT · Kalshi")
    }

    func testBeforeIgnoresAResultOrConfirmedWinnerTheOwnerPassed() {
        let early = Self.row(17, "Kirill Kaprizov", pregame: Self.kaprizovPregame,
                             current: .recorded(Self.obs(0.11, "11%", "recorded Oct 3, 4:59 PM PT · Kalshi")),
                             result: Self.notFirst)
        let input = Self.input(.before, [early], selectedID: Self.pid(17), confirmed: Self.jeannotConfirmed)
        XCTAssertNil(input.secondReading(early))
        XCTAssertNil(input.confirmedShortcut, "no confirmed result can exist before play")
        XCTAssertFalse(input.accessibilityComparison(for: early).contains("Not first"))
        XCTAssertFalse(input.accessibilityComparison(for: early).contains("11%"))
    }

    // MARK: Anytime is not first scorer

    func testJeannotsMissingFirstScorerBaselineStaysMissingAndBorrowsNoAnytimeChance() {
        let input = Self.input(.final, Self.finalRows, selectedID: Self.pid(0), selectedRow: Self.jeannotFinal,
                               confirmed: Self.jeannotConfirmed)
        let jeannot = Self.jeannotFinal
        XCTAssertEqual(input.selection, .outside(jeannot))
        XCTAssertEqual(input.pregameReading(jeannot), .missing("Unavailable"))
        XCTAssertEqual(input.secondReading(jeannot), .result(Self.scoredFirst))
        let spoken = input.accessibilityComparison(for: jeannot)
        XCTAssertEqual(spoken, "Pregame first-goalscorer chance: Unavailable; First-goalscorer result: Scored first")
        XCTAssertFalse(spoken.contains("8%"), "his anytime 8% is another market")
    }

    // MARK: During play

    func testDuringShowsARecordedReadingBesideThePregameChanceWithNoDelta() {
        let boldy = Self.row(22, "Matt Boldy", pregame: Self.boldyPregame, current: .recorded(Self.boldyRecorded))
        let input = Self.input(.during, [boldy], selectedID: Self.pid(22))
        XCTAssertEqual(input.secondReading(boldy), .current(.value(Self.boldyRecorded)))
        XCTAssertTrue(input.showsCurrentMark(boldy))
        XCTAssertEqual(input.pregameReading(boldy), .value(Self.boldyPregame), "the plot and baseline stay pregame")
        let spoken = input.accessibilityComparison(for: boldy)
        XCTAssertEqual(spoken,
                       "Pregame first-goalscorer chance: 9%, minute ending Oct 3, 4:50 PM PT · Kalshi; "
                       + "Recorded in-game first-goalscorer chance: 14%, recorded Oct 3, 5:10 PM PT · Kalshi")
        XCTAssertFalse(spoken.contains("5%"), "no movement figure is derived")
    }

    func testDuringStaleAndUnavailableKeepTheOwnersWordsAndDrawNoMark() {
        let stale = Self.row(23, "Max Shabanov", pregame: Self.shabanovPregame, current: .stale("No update since 5:03 PM"))
        let unavailable = Self.row(14, "Joel Eriksson Ek", pregame: Self.erikssonEkPregame, current: .unavailable("No in-game reading"))
        let input = Self.input(.during, [stale, unavailable])
        XCTAssertEqual(input.secondReading(stale), .current(.missing("No update since 5:03 PM")))
        XCTAssertEqual(input.secondReading(unavailable), .current(.missing("No in-game reading")))
        XCTAssertFalse(input.showsCurrentMark(stale))
        XCTAssertFalse(input.showsCurrentMark(unavailable))
        XCTAssertEqual(input.accessibilityComparison(for: unavailable),
                       "Pregame first-goalscorer chance: 8%, minute ending Oct 3, 4:34 PM PT · Kalshi; "
                       + "Recorded in-game first-goalscorer chance: No in-game reading")
    }

    func testAResultAdmittedWhileTheMatchIsLiveIsShownAndReplacesAnySettledPrice() {
        // The first goal (Jeannot) came early; the owner admits the result before the final.
        let jeannot = Self.row(0, "Tanner Jeannot", team: "Boston", pregame: nil,
                               current: .recorded(Self.obs(1.0, "100%", "recorded Oct 3, 5:20 PM PT · Kalshi")),
                               result: Self.scoredFirst)
        let kaprizov = Self.row(17, "Kirill Kaprizov", pregame: Self.kaprizovPregame,
                                current: .recorded(Self.obs(0.0, "0%", "recorded Oct 3, 5:20 PM PT · Kalshi")),
                                result: Self.notFirst)
        let input = Self.input(.during, [kaprizov], selectedID: Self.pid(17), confirmed: Self.jeannotConfirmed)

        XCTAssertEqual(input.secondReading(jeannot), .result(Self.scoredFirst))
        XCTAssertEqual(input.secondReading(kaprizov), .result(Self.notFirst))
        XCTAssertFalse(input.showsCurrentMark(kaprizov))
        XCTAssertEqual(input.resultTitle, FirstScorerComparisonInput10868.liveResultTitle)
        XCTAssertEqual(input.confirmedShortcut, Self.jeannotConfirmed, "the return appears during play once admitted")
        let spoken = input.accessibilityComparison(for: kaprizov)
        XCTAssertTrue(spoken.hasSuffix("First-goalscorer result: Not first"))
        XCTAssertFalse(spoken.contains("5:20 PM"), "a settled price is never shown as a chance")
        XCTAssertFalse(input.accessibilityComparison(for: jeannot).contains("100%"))
        XCTAssertFalse(input.accessibilityComparison(for: jeannot).contains("5:20 PM"))
    }

    func testDuringAnUnconfirmedResultIsNotAResult() {
        let boldy = Self.row(22, "Matt Boldy", pregame: Self.boldyPregame,
                             current: .unavailable("No in-game reading"), result: .unconfirmed("Unconfirmed"))
        let input = Self.input(.during, [boldy])
        XCTAssertEqual(input.secondReading(boldy), .current(.missing("No in-game reading")),
                       "with neither a reading nor a result, the owner's unavailable words show")
        XCTAssertFalse(input.accessibilityComparison(for: boldy).contains("Not first"))
    }

    // MARK: Final

    func testFinalPairsThePregameChanceWithTheResultAndIgnoresInGamePrices() {
        let kaprizov = Self.row(17, "Kirill Kaprizov", pregame: Self.kaprizovPregame,
                                current: .recorded(Self.obs(0.0, "0%", "recorded Oct 3, 7:40 PM PT · Kalshi")),
                                result: Self.notFirst)
        let input = Self.input(.final, [kaprizov], selectedID: Self.pid(17))
        XCTAssertEqual(input.secondReading(kaprizov), .result(Self.notFirst))
        XCTAssertEqual(input.resultTitle, "Final result")
        XCTAssertEqual(input.accessibilityComparison(for: kaprizov),
                       "Pregame first-goalscorer chance: 10%, minute ending Oct 3, 4:57 PM PT · Kalshi; "
                       + "First-goalscorer result: Not first")
    }

    func testAMissingResultIsUnconfirmedAndNeverNotFirst() {
        let unknown = Self.row(22, "Matt Boldy", pregame: Self.boldyPregame, result: .unconfirmed("Unconfirmed"))
        let input = Self.input(.final, [unknown], selectedID: Self.pid(22))
        XCTAssertEqual(input.secondReading(unknown), .result(.unconfirmed("Unconfirmed")))
        XCTAssertFalse(FirstScorerResult10868.unconfirmed("Unconfirmed").isAdmitted)
        XCTAssertTrue(Self.notFirst.isAdmitted)
        XCTAssertTrue(Self.scoredFirst.isAdmitted)
        XCTAssertFalse(input.accessibilityComparison(for: unknown).contains("Not first"))
    }

    // MARK: Membership and selection

    func testPlotMembershipAndOrderAreTheOwnersOwn() {
        // Deliberately not sorted by chance, longer than the reference's four,
        // and including a missing-baseline player.
        let coleman = Self.row(1, "Blake Coleman", team: "Boston", pregame: Self.colemanPregame, result: Self.notFirst)
        let rows = [coleman] + Self.finalRows + [Self.jeannotFinal]
        let input = Self.input(.final, rows, coverage: "25 of 36 players have a captured pregame trade.")
        XCTAssertEqual(input.overview, rows)
        XCTAssertEqual(input.overview.map(\.id), [1, 17, 22, 14, 23, 0].map(Self.pid))
        XCTAssertEqual(input.coverage, "25 of 36 players have a captured pregame trade.")
    }

    func testASelectedPlotRowIsMarkedOnce() {
        let rows = Self.finalRows
        let input = Self.input(.final, rows, selectedID: Self.pid(22), selectedRow: rows[1])
        XCTAssertEqual(input.selection, .overview(rows[1]))
        XCTAssertEqual(rows.filter { input.isSelected($0) }.map(\.id), [Self.pid(22)])
        XCTAssertNil(input.selectionNotice)
    }

    func testAPlayerOutsideThePlotStillGetsTheNamedComparison() {
        let coleman = Self.row(1, "Blake Coleman", team: "Boston", pregame: Self.colemanPregame, result: Self.notFirst)
        let input = Self.input(.final, Self.finalRows, selectedID: Self.pid(1), selectedRow: coleman)
        XCTAssertEqual(input.selection, .outside(coleman))
        XCTAssertTrue(Self.finalRows.allSatisfy { !input.isSelected($0) }, "no plot row is marked for him")
        XCTAssertEqual(input.overview.count, 4, "he is not added to the plot")
        XCTAssertEqual(input.accessibilityComparison(for: coleman),
                       "Pregame first-goalscorer chance: 6%, minute ending Oct 3, 4:11 PM PT · Kalshi; "
                       + "First-goalscorer result: Not first")
    }

    func testAMissingSelectionFallsBackToNobody() {
        let input = Self.input(.final, Self.finalRows, selectedID: Self.pid(99), confirmed: Self.jeannotConfirmed)
        XCTAssertEqual(input.selection, .missing(Self.pid(99)))
        XCTAssertNil(input.selection.row)
        XCTAssertTrue(Self.finalRows.allSatisfy { !input.isSelected($0) })
        XCTAssertEqual(input.selectionNotice, FirstScorerComparisonInput10868.selectionUnavailable)
        XCTAssertNil(input.detailsAction(canOpenDetails: true))
        XCTAssertNil(input.timingPresentation(hasBinding: true))
    }

    func testASelectedRowWithAnotherIDIsNotUsed() {
        let input = Self.input(.final, Self.finalRows, selectedID: Self.pid(1), selectedRow: Self.jeannotFinal)
        XCTAssertEqual(input.selection, .missing(Self.pid(1)))
    }

    func testADuplicatedSelectionIsExplicitAndPicksNoRow() {
        let twice = Self.finalRows + [Self.finalRows[0]]
        let input = Self.input(.final, twice, selectedID: Self.pid(17))
        XCTAssertEqual(input.selection, .duplicate(Self.pid(17)))
        XCTAssertTrue(twice.allSatisfy { !input.isSelected($0) })
        XCTAssertEqual(input.selectionNotice, FirstScorerComparisonInput10868.selectionUnavailable)
        XCTAssertEqual(input.overview.count, 5, "the duplicate is shown as supplied, not dropped")
    }

    func testNoSelectionIsNotANotice() {
        let input = Self.input(.before, Self.pregameRows)
        XCTAssertEqual(input.selection, .none)
        XCTAssertNil(input.selectionNotice)
    }

    // MARK: Confirmed first scorer

    func testTheConfirmedReturnAppearsOnlyWhenAnotherPlayerIsSelected() {
        let onKaprizov = Self.input(.final, Self.finalRows, selectedID: Self.pid(17), confirmed: Self.jeannotConfirmed)
        XCTAssertEqual(onKaprizov.confirmedShortcut, Self.jeannotConfirmed)

        let onJeannot = Self.input(.final, Self.finalRows, selectedID: Self.pid(0), selectedRow: Self.jeannotFinal,
                                   confirmed: Self.jeannotConfirmed)
        XCTAssertNil(onJeannot.confirmedShortcut, "selecting the winner does not repeat the banner")

        XCTAssertEqual(Self.input(.final, Self.finalRows, confirmed: Self.jeannotConfirmed).confirmedShortcut,
                       Self.jeannotConfirmed)
        XCTAssertNil(Self.input(.final, Self.finalRows, selectedID: Self.pid(17)).confirmedShortcut,
                     "no owner-confirmed winner, no shortcut — never inferred from the rows")
    }

    func testTheConfirmedReturnSelectsTheExactIDOrIsStaticWithoutACallback() {
        let input = Self.input(.final, Self.finalRows, selectedID: Self.pid(17), confirmed: Self.jeannotConfirmed)
        XCTAssertEqual(input.confirmedAction(canSelect: true), .select(Self.pid(0)))
        XCTAssertNil(input.confirmedAction(canSelect: false), "static context, no false tap")
        XCTAssertEqual(input.accessibilityConfirmed(Self.jeannotConfirmed),
                       "First goalscorer · confirmed result: Tanner Jeannot")
    }

    // MARK: Callbacks

    func testActionsCarryExactIDsAndDisappearWithoutCallbacks() {
        let coleman = Self.row(1, "Blake Coleman", team: "Boston", pregame: Self.colemanPregame, result: Self.notFirst)
        let input = Self.input(.final, Self.finalRows, selectedID: Self.pid(1), selectedRow: coleman)
        XCTAssertEqual(input.rowAction(Self.finalRows[1], canSelect: true), .select(Self.pid(22)))
        XCTAssertNil(input.rowAction(Self.finalRows[1], canSelect: false))
        XCTAssertEqual(input.detailsAction(canOpenDetails: true), .details(Self.pid(1)))
        XCTAssertNil(input.detailsAction(canOpenDetails: false))

        var selected: [String] = []
        var details: [String] = []
        FirstScorerAction10868.select(Self.pid(22)).perform(onSelect: { selected.append($0) }, onDetails: { details.append($0) })
        FirstScorerAction10868.details(Self.pid(1)).perform(onSelect: { selected.append($0) }, onDetails: { details.append($0) })
        FirstScorerAction10868.select(Self.pid(22)).perform(onSelect: nil, onDetails: nil)
        XCTAssertEqual(selected, [Self.pid(22)])
        XCTAssertEqual(details, [Self.pid(1)])
    }

    // MARK: Timing

    func testTimingBelongsToItsPlayerAndIsPresentedThePageOwnersWay() {
        let timing = FirstScorerTiming10868(
            playerID: Self.pid(17),
            title: "Kirill Kaprizov · probability timing",
            lines: ["Pregame trade · minute ending Oct 3, 4:57 PM"]
        )
        let onKaprizov = Self.input(.final, Self.finalRows, selectedID: Self.pid(17), timing: timing)
        XCTAssertEqual(onKaprizov.timingPresentation(hasBinding: true), .disclosure(timing))
        XCTAssertEqual(onKaprizov.timingPresentation(hasBinding: false), .expanded(timing))

        // Selection moved to Boldy, timing still Kaprizov's: nothing stale is shown.
        XCTAssertNil(Self.input(.final, Self.finalRows, selectedID: Self.pid(22), timing: timing).timingPresentation(hasBinding: true))
    }

    @MainActor
    func testThePageOwnedTimingFlagIsHandedThroughUntouched() {
        var expanded = true
        let binding = Binding(get: { expanded }, set: { expanded = $0 })
        let view = FirstScorerComparisonPresentation10868(
            input: Self.input(.final, Self.finalRows, selectedID: Self.pid(22)),
            timingExpanded: binding
        )
        XCTAssertEqual(view.timingExpanded?.wrappedValue, true)
        expanded = false
        XCTAssertEqual(view.timingExpanded?.wrappedValue, false)
    }

    // MARK: Plot geometry

    func testValuesSitOnTheCallersDomainAndAreNotNormalized() {
        let axis = Self.tenPercent
        XCTAssertEqual(FirstScorerGeometry10868.fraction(0.10, axis: axis)!, 1, accuracy: 1e-9)
        XCTAssertEqual(FirstScorerGeometry10868.fraction(0.09, axis: axis)!, 0.9, accuracy: 1e-9)
        XCTAssertEqual(FirstScorerGeometry10868.fraction(0.0, axis: axis)!, 0, accuracy: 1e-9)
        // The same 10% on a wider owner domain sits half way — the domain is the caller's.
        let twenty = FirstScorerAxis10868(lower: 0, upper: 0.20, ticks: [])
        XCTAssertEqual(FirstScorerGeometry10868.fraction(0.10, axis: twenty)!, 0.5, accuracy: 1e-9)
        // The five baselines sum to 0.41: nothing rescales them to 100%.
        let total = Self.finalRows.compactMap { $0.pregame?.probability }.reduce(0, +) + Self.colemanPregame.probability
        XCTAssertEqual(total, 0.41, accuracy: 1e-9)
    }

    func testOutOfDomainOrNonFiniteValuesOmitTheMarkButKeepTheRowAndFigure() {
        for bad in [0.12, -0.01, .nan, .infinity, -.infinity] {
            XCTAssertNil(FirstScorerGeometry10868.fraction(bad, axis: Self.tenPercent), "\(bad) is omitted, never clamped")
        }
        for axis in [FirstScorerAxis10868(lower: 0.1, upper: 0.1, ticks: []),
                     FirstScorerAxis10868(lower: 0.2, upper: 0.1, ticks: []),
                     FirstScorerAxis10868(lower: 0, upper: .nan, ticks: [])] {
            XCTAssertFalse(axis.isValid)
            XCTAssertNil(FirstScorerGeometry10868.fraction(0.05, axis: axis))
        }
        let outside = Self.row(17, "Kirill Kaprizov", pregame: Self.obs(0.12, "12%", "minute ending Oct 3, 4:57 PM PT · Kalshi"))
        let input = Self.input(.before, [outside])
        XCTAssertEqual(input.overview, [outside], "the row stays")
        XCTAssertEqual(input.pregameReading(outside).text, "12%", "the owner's figure stays")
    }

    func testMarksStayWhollyInsideTheTrack() {
        let inset = FirstScorerGeometry10868.trackInset
        XCTAssertEqual(inset, 5, "half the 8pt mark plus half its 2pt stroke")
        XCTAssertEqual(FirstScorerGeometry10868.x(0, width: 100), 5)
        XCTAssertEqual(FirstScorerGeometry10868.x(1, width: 100), 95)
        XCTAssertEqual(FirstScorerGeometry10868.x(0.5, width: 100), 50)
        XCTAssertNil(FirstScorerGeometry10868.x(0.5, width: 10), "no usable width, no mark")
        XCTAssertNil(FirstScorerGeometry10868.x(1.2, width: 100))
        XCTAssertNil(FirstScorerGeometry10868.x(.nan, width: 100))
    }

    func testAnAxisThatIsNotAProbabilityScaleIsInvalidAndPlacesNothing() {
        let malformed = [
            FirstScorerAxis10868(lower: -1, upper: 2, ticks: []),
            FirstScorerAxis10868(lower: 0, upper: 1.5, ticks: []),
            FirstScorerAxis10868(lower: -0.1, upper: 0.1, ticks: []),
            FirstScorerAxis10868(lower: -.infinity, upper: 1, ticks: []),
            FirstScorerAxis10868(lower: 0, upper: .infinity, ticks: []),
            FirstScorerAxis10868(lower: .nan, upper: 1, ticks: []),
            FirstScorerAxis10868(lower: 0.3, upper: 0.3, ticks: []),
            FirstScorerAxis10868(lower: 0.5, upper: 0.2, ticks: []),
        ]
        for axis in malformed {
            XCTAssertFalse(axis.isValid, "\(axis.lower)...\(axis.upper) is not a probability scale")
            XCTAssertNil(FirstScorerGeometry10868.fraction(0.05, axis: axis), "no mark, never clamped")
            XCTAssertNil(FirstScorerGeometry10868.fraction(0.5, axis: axis))
        }
        XCTAssertTrue(FirstScorerAxis10868(lower: 0, upper: 1, ticks: []).isValid)
        XCTAssertTrue(FirstScorerAxis10868(lower: 0.02, upper: 0.14, ticks: []).isValid)
        // Ticks on a malformed axis are not placed either, even where they look plausible.
        let wide = FirstScorerAxis10868(lower: -1, upper: 2, ticks: [
            FirstScorerTick10868(value: 0, text: "0%"),
            FirstScorerTick10868(value: 0.5, text: "50%"),
        ])
        XCTAssertTrue(FirstScorerGeometry10868.visibleTicks(wide).isEmpty)
        // Values outside 0...1 have no place on a valid scale.
        let full = FirstScorerAxis10868(lower: 0, upper: 1, ticks: [])
        for bad in [-0.01, 1.01, 2, .nan, .infinity, -.infinity] {
            XCTAssertNil(FirstScorerGeometry10868.fraction(bad, axis: full), "\(bad) draws no mark")
        }
        // The row and the owner's figure survive a malformed axis.
        let kaprizov = Self.row(17, "Kirill Kaprizov", pregame: Self.obs(0.10, "10%", "minute ending Oct 3, 4:57 PM PT · Kalshi"))
        let input = Self.input(.before, [kaprizov], selectedID: kaprizov.id, axis: wide)
        XCTAssertEqual(input.overview, [kaprizov])
        XCTAssertEqual(input.pregameReading(kaprizov).text, "10%")
    }

    /// Every narrow label inside the plot, every label once, and no two labels
    /// on one row closer than the gap.
    private func assertWhole(_ plan: FirstScorerLabelPlan10868, width: CGFloat, count: Int,
                             gap: CGFloat = 4, file: StaticString = #filePath, line: UInt = #line) {
        XCTAssertEqual(plan.placements.map(\.index), Array(0..<count), "every label, in the owner's order", file: file, line: line)
        for p in plan.placements where !p.wrapped {
            XCTAssertGreaterThanOrEqual(p.origin.x, 0, file: file, line: line)
            XCTAssertLessThanOrEqual(p.origin.x + p.size.width, width, file: file, line: line)
        }
        for p in plan.placements {
            XCTAssertLessThanOrEqual(p.origin.y + p.size.height, plan.size.height, "the block reserves every row", file: file, line: line)
            XCTAssertLessThanOrEqual(p.origin.x + p.size.width, plan.size.width, "the block reserves every extent", file: file, line: line)
            for q in plan.placements where q.index > p.index && q.row == p.row {
                let (left, right) = p.origin.x <= q.origin.x ? (p, q) : (q, p)
                XCTAssertLessThanOrEqual(left.origin.x + left.size.width + gap, right.origin.x,
                                         "labels \(p.index) and \(q.index) overlap", file: file, line: line)
            }
        }
    }

    private static func sizes(_ widths: [CGFloat], height: CGFloat = 14) -> [CGSize] {
        widths.map { CGSize(width: $0, height: height) }
    }

    /// Geometry only — label sizes are CONSTRUCTED measured extents, not a rendered fit.
    func testTickLabelsStayCentredWholeAndApartOnOneRowWhenTheyFit() {
        // 0% / 5% / 10% over a 100pt plot: the end labels shift inward, the middle stays centred.
        let plan = FirstScorerGeometry10868.labelPlan(centers: [5, 50, 95], natural: Self.sizes([20, 20, 26]),
                                                      atWidth: Self.sizes([20, 20, 26]), width: 100)
        assertWhole(plan, width: 100, count: 3)
        XCTAssertEqual(plan.placements.map(\.origin.x), [0, 40, 74])
        XCTAssertEqual(plan.placements.map(\.row), [0, 0, 0])
        XCTAssertEqual(plan.size, CGSize(width: 100, height: 14))
        let empty = FirstScorerGeometry10868.labelPlan(centers: [], natural: [], atWidth: [], width: 100)
        XCTAssertEqual(empty.placements, [])
        let mismatched = FirstScorerGeometry10868.labelPlan(centers: [5], natural: [], atWidth: [], width: 100)
        XCTAssertEqual(mismatched.placements, [], "counts that disagree place nothing rather than guess")
    }

    /// Geometry only — CONSTRUCTED extents. The packing the brief showed was impossible.
    func testTickLabelsThatCannotShareARowDropToTheNextRowAndTheBlockReservesIt() {
        // Three 60pt labels over 100pt cannot share one row: the old packing gave [0, 0, 40].
        let plan = FirstScorerGeometry10868.labelPlan(centers: [5, 50, 95], natural: Self.sizes([60, 60, 60]),
                                                      atWidth: Self.sizes([60, 60, 60]), width: 100)
        assertWhole(plan, width: 100, count: 3)
        XCTAssertEqual(plan.placements.map(\.row), [0, 1, 2])
        XCTAssertEqual(plan.placements.map(\.origin.x), [0, 20, 40], "each stays as near its gridline as the plot allows")
        XCTAssertEqual(plan.placements.map(\.origin.y), [0, 16, 32])
        XCTAssertEqual(plan.size, CGSize(width: 100, height: 46), "three rows and two row gaps are reserved")
        XCTAssertEqual(plan.placements.map(\.size), Self.sizes([60, 60, 60]), "no label is shrunk")

        // A later label reuses the first row that has room.
        let packed = FirstScorerGeometry10868.labelPlan(centers: [5, 30, 95], natural: Self.sizes([30, 30, 30]),
                                                        atWidth: Self.sizes([30, 30, 30]), width: 100)
        assertWhole(packed, width: 100, count: 3)
        XCTAssertEqual(packed.placements.map(\.row), [0, 1, 0])
        XCTAssertEqual(packed.size.height, 30)

        // Two ticks on one gridline are both kept, one above the other.
        let same = FirstScorerGeometry10868.labelPlan(centers: [50, 50], natural: Self.sizes([20, 24]),
                                                      atWidth: Self.sizes([20, 24]), width: 100)
        assertWhole(same, width: 100, count: 2)
        XCTAssertEqual(same.placements.map(\.row), [0, 1])
        XCTAssertEqual(same.placements.map(\.origin.x), [40, 38])
    }

    /// Geometry only — CONSTRUCTED extents.
    func testUnsortedOwnerTicksArePlacedByGridlineAndReturnedInTheOwnersOrder() {
        let plan = FirstScorerGeometry10868.labelPlan(centers: [95, 5, 50], natural: Self.sizes([26, 20, 20]),
                                                      atWidth: Self.sizes([26, 20, 20]), width: 100)
        assertWhole(plan, width: 100, count: 3)
        XCTAssertEqual(plan.placements.map(\.origin.x), [74, 0, 40])
        XCTAssertEqual(plan.placements.map(\.row), [0, 0, 0])
    }

    /// Geometry only — CONSTRUCTED extents; whether a real label wraps this way is unverified.
    func testALabelWiderThanThePlotGetsItsOwnRowAtItsWrappedSizeAndAnyOverflowIsReserved() {
        let natural = [CGSize(width: 20, height: 14), CGSize(width: 140, height: 14)]
        let wraps = FirstScorerGeometry10868.labelPlan(centers: [5, 50], natural: natural,
                                                       atWidth: [natural[0], CGSize(width: 96, height: 30)], width: 100)
        assertWhole(wraps, width: 100, count: 2)
        XCTAssertEqual(wraps.placements[1], FirstScorerLabelPlacement10868(
            index: 1, origin: CGPoint(x: 0, y: 16), size: CGSize(width: 96, height: 30), row: 1, wrapped: true))
        XCTAssertEqual(wraps.size, CGSize(width: 100, height: 46), "the wrapped height is reserved")

        // If even the plot-width size is wider, the block says how wide rather than hiding it.
        let unbreakable = FirstScorerGeometry10868.labelPlan(centers: [50], natural: [CGSize(width: 140, height: 14)],
                                                             atWidth: [CGSize(width: 120, height: 14)], width: 100)
        XCTAssertEqual(unbreakable.placements.map(\.wrapped), [true])
        XCTAssertEqual(unbreakable.size, CGSize(width: 120, height: 14))

        // A narrow label never shares the wide label's row.
        let after = FirstScorerGeometry10868.labelPlan(centers: [50, 95], natural: [CGSize(width: 140, height: 14), CGSize(width: 20, height: 14)],
                                                       atWidth: [CGSize(width: 96, height: 30), CGSize(width: 20, height: 14)], width: 100)
        assertWhole(after, width: 100, count: 2)
        XCTAssertEqual(after.placements.map(\.row), [0, 1])
    }

    func testOnlyPlaceableTicksAreLabelled() {
        let axis = FirstScorerAxis10868(lower: 0, upper: 0.10, ticks: [
            FirstScorerTick10868(value: 0, text: "0%"),
            FirstScorerTick10868(value: 0.15, text: "15%"),
            FirstScorerTick10868(value: 0.10, text: "10%"),
        ])
        XCTAssertEqual(FirstScorerGeometry10868.visibleTicks(axis), [
            FirstScorerPlacedTick10868(fraction: 0, text: "0%"),
            FirstScorerPlacedTick10868(fraction: 1, text: "10%"),
        ], "a tick the axis cannot place is omitted, labels are the owner's")
        XCTAssertTrue(FirstScorerGeometry10868.visibleTicks(FirstScorerAxis10868(lower: 1, upper: 0, ticks: axis.ticks)).isEmpty)
    }

    // MARK: VoiceOver and text

    func testSpokenTextNamesTheHeaderPlayerAndBaseline() {
        let input = Self.input(.final, Self.finalRows)
        let shabanov = Self.finalRows[3]
        XCTAssertEqual(input.accessibilityHeader, "Kalshi · first goalscorer. Who scored first?")
        XCTAssertEqual(input.accessibilityLabel(for: shabanov), "Max Shabanov, Team unavailable")
        XCTAssertEqual(input.accessibilityValue(for: shabanov),
                       "Pregame first-goalscorer chance: 8%, minute ending Oct 3, 4:53 PM PT · Kalshi")
        XCTAssertEqual(input.accessibilityValue(for: Self.jeannotFinal), "Pregame first-goalscorer chance: Unavailable")
        let noTeam = Self.row(14, "Joel Eriksson Ek", team: nil, pregame: Self.erikssonEkPregame)
        XCTAssertEqual(input.accessibilityLabel(for: noTeam), "Joel Eriksson Ek")
    }

    func testOwnerStringsArePassedThroughVerbatim() {
        let long = Self.row(
            7, "Jean-Gabriel Pageau-Longname of the Very Long Surname",
            pregame: Self.obs(0.004, "<1%", "minute ending Oct 3, 4:52 PM PT · Kalshi"),
            result: .notFirst("Did not score first")
        )
        let axis = FirstScorerAxis10868(lower: 0, upper: 0.125, ticks: [FirstScorerTick10868(value: 0.125, text: "12.5%")])
        let input = Self.input(.final, [long], selectedID: Self.pid(7), axis: axis)
        XCTAssertEqual(input.pregameReading(long).text, "<1%")
        XCTAssertEqual(input.overview[0].name, "Jean-Gabriel Pageau-Longname of the Very Long Surname")
        XCTAssertEqual(input.secondReading(long), .result(.notFirst("Did not score first")))
        XCTAssertEqual(FirstScorerGeometry10868.visibleTicks(axis).map(\.text), ["12.5%"])
    }

    func testAccessibilityIdentifiersCarryTheExactPropID() {
        let id = Self.pid(17)
        XCTAssertEqual(FirstScorerAccessibilityID10868.row(id), "firstScorer10868.row.\(id)")
        XCTAssertEqual(FirstScorerAccessibilityID10868.comparison(id), "firstScorer10868.comparison.\(id)")
        XCTAssertEqual(FirstScorerAccessibilityID10868.confirmed(id), "firstScorer10868.confirmed.\(id)")
        XCTAssertEqual(FirstScorerAccessibilityID10868.details(id), "firstScorer10868.details.\(id)")
    }

    // MARK: - First team to score (soccer), through the optional outcome context

    // ARCHIVED from `shipping-adoption-20261027/FIRST-TEAM-RETAINED-CASES.json`
    // (liveSoccer.json d835ccdf…27d2, soccerFinal.json 05de3275…8ffe):
    // Valladolid–Albacete, event 15325054, first-team-to-score market 63178217.
    //   244237963 "Real Valladolid CF"  pregame 0.57  @ 2026-10-12T11:47:12.426013Z; live current null, result pending; final won
    //   244237965 "Neither"             pregame 0.065 @ the same pin;               live current null, result pending; final lost
    //   244237964 "Albacete Balompié"   pregame 0.335 @ the same pin;               live current null, result pending; final lost
    // in that supplied order, plus five score checkpoints 0–0, 1–0, 2–0, 3–0,
    // 4–0 observed at 12:02:45.588824Z, 12:17:47.333487Z, 12:28:24.555020Z,
    // 12:33:45.571562Z and 12:38:45.543600Z — observation times, not goal times.
    // The raw last quotes (0.999 / 0.0005 / 0.0005) are never an input here.
    //
    // CONSTRUCTED: every display string (figures, PT captions, provenance,
    // context words, missing/stale/result words), the 0–100% axis and ticks,
    // every current-chance and admitted-during-play case, the Neither-won case,
    // the real 0%, missing, duplicate and long-text cases, and all flow sizes.

    private static func fid(_ outcome: Int) -> String { "other:63178217:\(outcome)" }

    private static let valladolidID = fid(244237963)
    private static let neitherID = fid(244237965)
    private static let albaceteID = fid(244237964)

    /// The caller's explicit words for an outcome market. None names a player
    /// or says anyone scored first (CONSTRUCTED).
    private static let teamWords = FirstScorerOutcomeContext10868(
        pregameTitle: "Pre-match chance",
        currentTitle: "Current chance",
        liveResultTitle: "Result",
        finalResultTitle: "Final result",
        selectionUnavailable: "Selected outcome unavailable.",
        spokenPregame: "Pre-match chance",
        spokenCurrent: "Current chance",
        spokenResult: "Result",
        selectHint: "Selects this outcome’s comparison"
    )

    private static let pinDetail = "pinned Oct 12, 4:47 AM PT · Polymarket"
    private static let valladolidPregame = obs(0.57, "57%", pinDetail)
    private static let neitherPregame = obs(0.065, "6.5%", pinDetail)
    private static let albacetePregame = obs(0.335, "33.5%", pinDetail)

    /// The retained live state: no admitted current chance (CONSTRUCTED words for null).
    private static let noCurrentChance = FirstScorerCurrent10868.unavailable("Current chance unavailable")
    private static let resultPending = FirstScorerResult10868.unconfirmed("Result pending")
    private static let won = FirstScorerResult10868.won("Won")
    private static let lost = FirstScorerResult10868.lost("Lost")

    private static func outcome(
        _ id: String,
        _ name: String,
        pregame: FirstScorerObservation10868?,
        current: FirstScorerCurrent10868 = noCurrentChance,
        result: FirstScorerResult10868 = resultPending
    ) -> FirstScorerRow10868 {
        FirstScorerRow10868(id: id, name: name, team: nil, pregame: pregame,
                            pregameMissing: "No pre-match chance", current: current, result: result)
    }

    private static func outcomes(
        current: [FirstScorerCurrent10868] = [noCurrentChance, noCurrentChance, noCurrentChance],
        result: [FirstScorerResult10868] = [resultPending, resultPending, resultPending]
    ) -> [FirstScorerRow10868] {
        [
            outcome(valladolidID, "Real Valladolid CF", pregame: valladolidPregame, current: current[0], result: result[0]),
            outcome(neitherID, "Neither", pregame: neitherPregame, current: current[1], result: result[1]),
            outcome(albaceteID, "Albacete Balompié", pregame: albacetePregame, current: current[2], result: result[2]),
        ]
    }

    private static var finalOutcomes: [FirstScorerRow10868] { outcomes(result: [won, lost, lost]) }

    private static let fullScale = FirstScorerAxis10868(lower: 0, upper: 1, ticks: [
        FirstScorerTick10868(value: 0, text: "0%"),
        FirstScorerTick10868(value: 0.5, text: "50%"),
        FirstScorerTick10868(value: 1, text: "100%"),
    ])

    private static func checkpoint(_ index: Int, _ score: String, _ time: String, _ spoken: String) -> FirstScorerScoreObservation10868 {
        FirstScorerScoreObservation10868(id: "15325054:score:\(index)", score: score, time: time, accessibilityText: spoken)
    }

    /// ARCHIVED scores and order; CONSTRUCTED text, PT captions and provenance.
    private static let observed = FirstScorerScorePath10868(
        title: "Observed scores",
        note: "Observation times, not exact goal times.",
        observations: [
            checkpoint(0, "0–0", "5:02 AM", "Real Valladolid CF 0, Albacete Balompié 0 · observed Oct 12, 5:02:45 AM PT"),
            checkpoint(1, "1–0", "5:17 AM", "Real Valladolid CF 1, Albacete Balompié 0 · observed Oct 12, 5:17:47 AM PT"),
            checkpoint(2, "2–0", "5:28 AM", "Real Valladolid CF 2, Albacete Balompié 0 · observed Oct 12, 5:28:24 AM PT"),
            checkpoint(3, "3–0", "5:33 AM", "Real Valladolid CF 3, Albacete Balompié 0 · observed Oct 12, 5:33:45 AM PT"),
            checkpoint(4, "4–0", "5:38 AM", "Real Valladolid CF 4, Albacete Balompié 0 · observed Oct 12, 5:38:45 AM PT"),
        ]
    )

    private static func soccer(
        _ phase: FirstScorerPhase10868,
        _ overview: [FirstScorerRow10868],
        selectedID: String? = nil,
        confirmed: FirstScorerConfirmed10868? = nil,
        scorePath: FirstScorerScorePath10868? = observed
    ) -> FirstScorerComparisonInput10868 {
        FirstScorerComparisonInput10868(
            phase: phase,
            title: "First team to score",
            context: "Polymarket · first team to score",
            overview: overview,
            selectedID: selectedID,
            selectedRow: nil,
            plotTitle: "Bars · each outcome’s pre-match chance",
            axis: fullScale,
            coverage: nil,
            confirmed: confirmed,
            timing: nil,
            outcome: teamWords,
            scorePath: scorePath
        )
    }

    /// Words this layer itself must never put beside a team or Neither.
    private func assertNoScorerWording(_ text: String, file: StaticString = #filePath, line: UInt = #line) {
        for word in ["player", "goalscorer", "Scored first", "scored first", "Not first"] {
            XCTAssertFalse(text.contains(word), "“\(word)” in “\(text)”", file: file, line: line)
        }
    }

    func testWithoutAnOutcomeContextTheHockeyCardKeepsItsWordsAndPregameOnlyRows() {
        let boldy = Self.row(22, "Matt Boldy", pregame: Self.boldyPregame,
                             current: .recorded(Self.boldyRecorded), result: Self.notFirst)
        for phase in [FirstScorerPhase10868.before, .during, .final] {
            let input = Self.input(phase, [boldy], selectedID: Self.pid(99))
            XCTAssertNil(input.outcome)
            XCTAssertNil(input.scorePath)
            XCTAssertFalse(input.showsRowReadings)
            XCTAssertEqual(input.words, .firstGoalscorer)
            XCTAssertNil(input.rowReading(boldy), "rows stay pregame-only in \(phase)")
            XCTAssertNil(input.visibleScorePath)
            XCTAssertEqual(input.accessibilityValue(for: boldy),
                           "Pregame first-goalscorer chance: 9%, minute ending Oct 3, 4:50 PM PT · Kalshi")
            XCTAssertEqual(input.selectionNotice, "Selected player unavailable.")
        }
        let words = FirstScorerOutcomeContext10868.firstGoalscorer
        XCTAssertEqual(words.pregameTitle, "Pregame chance")
        XCTAssertEqual(words.currentTitle, "Recorded in-game")
        XCTAssertEqual(words.liveResultTitle, "First-goalscorer result")
        XCTAssertEqual(words.finalResultTitle, "Final result")
        XCTAssertEqual(words.spokenCurrent, "Recorded in-game first-goalscorer chance")
        XCTAssertEqual(words.selectHint, "Selects this player’s comparison")
        // The old eleven-argument form and the new one with nils are the same input.
        let explicit = FirstScorerComparisonInput10868(
            phase: .final, title: "Who scored first?", context: "Kalshi · first goalscorer", overview: [boldy],
            selectedID: Self.pid(99), selectedRow: nil, plotTitle: "Highest captured pregame chances", axis: Self.tenPercent,
            coverage: nil, confirmed: nil, timing: nil, outcome: nil, scorePath: nil)
        XCTAssertEqual(explicit, Self.input(.final, [boldy], selectedID: Self.pid(99)))
        // The original result cases keep their meaning.
        XCTAssertEqual(Self.scoredFirst.mark, .positive)
        XCTAssertEqual(Self.notFirst.mark, .negative)
        XCTAssertNil(Self.pending.mark)
        XCTAssertEqual(Self.notFirst.text, "Not first")
    }

    func testBeforeShowsTheThreeOriginalChancesInSuppliedOrderAndHidesEverythingLater() {
        // CONSTRUCTED later inputs supplied too early: a current chance, results and the checkpoints.
        let rows = Self.outcomes(current: [.recorded(Self.obs(0.91, "91%", "recorded Oct 12, 5:20 AM PT · Polymarket")),
                                           .stale("No update since 5:20 AM"), Self.noCurrentChance],
                                 result: [Self.won, Self.lost, Self.lost])
        let input = Self.soccer(.before, rows, selectedID: Self.valladolidID)

        XCTAssertEqual(input.overview.map(\.id), [Self.valladolidID, Self.neitherID, Self.albaceteID], "supplied order, not sorted")
        XCTAssertEqual(input.overview.compactMap { $0.pregame?.probability }, [0.57, 0.065, 0.335])
        XCTAssertEqual(input.overview.compactMap { $0.pregame?.probability }.reduce(0, +), 0.97, accuracy: 1e-9,
                       "the originals are independent; nothing rescales them to 100%")
        for row in rows {
            XCTAssertNil(input.secondReading(row))
            XCTAssertNil(input.rowReading(row), "no current or result before play")
            XCTAssertEqual(input.accessibilityValue(for: row), "Pre-match chance: \(row.pregame!.text), \(Self.pinDetail)")
            assertNoScorerWording(input.accessibilityValue(for: row))
        }
        XCTAssertNil(input.visibleScorePath, "every supplied later checkpoint stays hidden before play")
        XCTAssertEqual(input.accessibilityComparison(for: rows[0]), "Pre-match chance: 57%, \(Self.pinDetail)")
        XCTAssertFalse(input.accessibilityComparison(for: rows[0]).contains("91%"))
        XCTAssertFalse(input.accessibilityComparison(for: rows[0]).contains("Won"))
    }

    func testDuringTheRetainedLiveStateKeepsEveryRowsUnavailableWordsAndRevivesNoRawQuote() {
        let rows = Self.outcomes()
        let input = Self.soccer(.during, rows)
        XCTAssertEqual(input.selection, .none)
        for row in rows {
            XCTAssertEqual(input.rowReading(row), .current(.missing("Current chance unavailable")))
            XCTAssertFalse(input.showsCurrentMark(row))
            let spoken = input.accessibilityValue(for: row)
            XCTAssertEqual(spoken, "Pre-match chance: \(row.pregame!.text), \(Self.pinDetail); Current chance: Current chance unavailable")
            for raw in ["99.9", "0.05%", "100%"] { XCTAssertFalse(spoken.contains(raw), "the raw last quote is never revived") }
            assertNoScorerWording(spoken)
        }
        XCTAssertEqual(input.visibleScorePath, Self.observed)
    }

    func testDuringEachNonselectedRowKeepsItsOwnRecordedStaleOrAdmittedState() {
        // CONSTRUCTED: an admitted current chance, a stale one, and a result admitted during play.
        let recorded = Self.obs(0.91, "91%", "recorded Oct 12, 5:20 AM PT · Polymarket")
        let rows = Self.outcomes(current: [.recorded(recorded), .stale("No update since 5:20 AM"), Self.noCurrentChance],
                                 result: [Self.resultPending, Self.resultPending, Self.lost])
        let input = Self.soccer(.during, rows, selectedID: Self.neitherID)

        XCTAssertEqual(input.rowReading(rows[0]), .current(.value(recorded)))
        XCTAssertTrue(input.showsCurrentMark(rows[0]), "the filled key sits only beside a recorded chance")
        XCTAssertEqual(input.rowReading(rows[1]), .current(.missing("No update since 5:20 AM")))
        XCTAssertFalse(input.showsCurrentMark(rows[1]))
        XCTAssertEqual(input.rowReading(rows[2]), .result(Self.lost), "an admitted result replaces the in-game reading")
        XCTAssertEqual(input.resultTitle, "Result")
        XCTAssertEqual(input.accessibilityValue(for: rows[0]),
                       "Pre-match chance: 57%, \(Self.pinDetail); Current chance: 91%, recorded Oct 12, 5:20 AM PT · Polymarket")
        XCTAssertEqual(input.accessibilityValue(for: rows[2]), "Pre-match chance: 33.5%, \(Self.pinDetail); Result: Lost")
        XCTAssertFalse(input.accessibilityValue(for: rows[0]).contains("34"), "no movement is derived")
        // The selected Neither keeps its comparison while the others keep their own rows.
        XCTAssertEqual(input.selection, .overview(rows[1]))
        XCTAssertEqual(input.accessibilityComparison(for: rows[1]),
                       "Pre-match chance: 6.5%, \(Self.pinDetail); Current chance: No update since 5:20 AM")
        XCTAssertEqual(rows.filter { input.isSelected($0) }.map(\.id), [Self.neitherID])
    }

    func testObservedScoresKeepTheirOrderAndClocksAndSettleNothing() {
        let rows = Self.outcomes()
        let input = Self.soccer(.during, rows)
        let path = input.visibleScorePath
        XCTAssertEqual(path?.observations.map(\.score), ["0–0", "1–0", "2–0", "3–0", "4–0"])
        XCTAssertEqual(path?.observations.map(\.time), ["5:02 AM", "5:17 AM", "5:28 AM", "5:33 AM", "5:38 AM"])
        XCTAssertEqual(path?.observations.map(\.id), (0..<5).map { "15325054:score:\($0)" })
        XCTAssertEqual(path?.observations[1].accessibilityText,
                       "Real Valladolid CF 1, Albacete Balompié 0 · observed Oct 12, 5:17:47 AM PT")
        XCTAssertEqual(path?.title, "Observed scores")
        XCTAssertEqual(path?.note, "Observation times, not exact goal times.")
        // 4–0 leaves every result, chance and shortcut exactly as the owner supplied them.
        for row in rows {
            XCTAssertFalse(row.result.isAdmitted)
            XCTAssertEqual(input.rowReading(row), .current(.missing("Current chance unavailable")))
        }
        XCTAssertNil(input.confirmedShortcut, "a scored team is not a confirmed result")
        XCTAssertEqual(input.selection, .none, "showing the scores selects nothing")
        XCTAssertNil(input.detailsAction(canOpenDetails: true))
    }

    func testObservedScoresAppearOnlyDuringPlayAndAreNeverMadeUp() {
        let rows = Self.finalOutcomes
        XCTAssertNil(Self.soccer(.before, rows).visibleScorePath)
        XCTAssertNil(Self.soccer(.final, rows).visibleScorePath, "the final returns to the original results")
        XCTAssertNil(Self.soccer(.during, rows, scorePath: nil).visibleScorePath)
        let empty = FirstScorerScorePath10868(title: "Observed scores", note: nil, observations: [])
        XCTAssertNil(Self.soccer(.during, rows, scorePath: empty).visibleScorePath, "no 0–0 is fabricated")
        // An unknown time stays the owner's words; a repeated id is shown as supplied.
        let odd = FirstScorerScorePath10868(title: "Observed scores", note: nil, observations: [
            Self.checkpoint(1, "1–0", "Time not recorded", "Real Valladolid CF 1, Albacete Balompié 0 · time not recorded"),
            Self.checkpoint(1, "2–0", "5:28 AM", "Real Valladolid CF 2, Albacete Balompié 0 · observed Oct 12, 5:28:24 AM PT"),
        ])
        let shown = Self.soccer(.during, rows, scorePath: odd).visibleScorePath
        XCTAssertEqual(shown, odd)
        XCTAssertEqual(shown?.observations.map(\.time), ["Time not recorded", "5:28 AM"])
        XCTAssertEqual(FirstScorerAccessibilityID10868.score("15325054:score:1"), "firstScorer10868.score.15325054:score:1")
    }

    func testFinalPairsEachOriginalChanceWithItsRecordedResult() {
        let rows = Self.finalOutcomes
        let input = Self.soccer(.final, rows, selectedID: Self.valladolidID)
        XCTAssertEqual(rows.compactMap { input.rowReading($0) },
                       [FirstScorerSecondReading10868.result(Self.won), .result(Self.lost), .result(Self.lost)])
        XCTAssertEqual(rows.compactMap(\.result.mark), [FirstScorerResultMark10868.positive, .negative, .negative])
        XCTAssertEqual(rows.map { input.accessibilityValue(for: $0) }, [
            "Pre-match chance: 57%, \(Self.pinDetail); Final result: Won",
            "Pre-match chance: 6.5%, \(Self.pinDetail); Final result: Lost",
            "Pre-match chance: 33.5%, \(Self.pinDetail); Final result: Lost",
        ])
        XCTAssertEqual(input.resultTitle, "Final result")
        XCTAssertEqual(input.secondReading(rows[0]), .result(Self.won), "the selected comparison keeps 57% vs Won")
        XCTAssertNil(input.visibleScorePath)
        // A supplied in-game price never shows as a chance after the final.
        let priced = Self.outcomes(current: [.recorded(Self.obs(1.0, "100%", "recorded Oct 12, 6:55 AM PT · Polymarket")),
                                             Self.noCurrentChance, Self.noCurrentChance],
                                   result: [Self.won, Self.lost, Self.lost])
        XCTAssertFalse(Self.soccer(.final, priced).accessibilityValue(for: priced[0]).contains("100%"))
    }

    func testNeitherCanWinAsAnOriginalOutcomeWithoutAnyScorerWording() {
        // CONSTRUCTED: the owner admits Neither as the winning original outcome.
        let rows = Self.outcomes(result: [Self.lost, Self.won, Self.lost])
        let confirmed = FirstScorerConfirmed10868(id: Self.neitherID, name: "Neither", caption: "First team to score · confirmed result")
        let input = Self.soccer(.final, rows, selectedID: Self.albaceteID, confirmed: confirmed)

        XCTAssertEqual(input.rowReading(rows[1]), .result(Self.won))
        XCTAssertEqual(rows[1].result.mark, .positive)
        XCTAssertEqual(input.accessibilityValue(for: rows[1]), "Pre-match chance: 6.5%, \(Self.pinDetail); Final result: Won")
        XCTAssertEqual(input.confirmedShortcut, confirmed)
        XCTAssertEqual(input.confirmedAction(canSelect: true), .select(Self.neitherID))
        XCTAssertEqual(input.accessibilityConfirmed(confirmed), "First team to score · confirmed result: Neither")
        for text in rows.map({ input.accessibilityValue(for: $0) }) + [input.accessibilityComparison(for: rows[2]),
                                                                       input.words.selectHint, input.resultTitle] {
            assertNoScorerWording(text)
        }
        XCTAssertEqual(input.words.selectHint, "Selects this outcome’s comparison")
    }

    func testAnUnknownResultIsNotALossAndARealZeroIsNotMissing() {
        // CONSTRUCTED: an unconfirmed final, a real 0% pregame chance and an absent one.
        let zero = Self.outcome(Self.neitherID, "Neither", pregame: Self.obs(0, "0%", Self.pinDetail), result: Self.lost)
        let unknown = Self.outcome(Self.albaceteID, "Albacete Balompié", pregame: Self.albacetePregame,
                                   result: .unconfirmed("Result unconfirmed"))
        let absent = Self.outcome(Self.valladolidID, "Real Valladolid CF", pregame: nil, result: Self.won)
        let input = Self.soccer(.final, [absent, zero, unknown])

        XCTAssertEqual(input.rowReading(unknown), .result(.unconfirmed("Result unconfirmed")))
        XCTAssertNil(unknown.result.mark, "no ✕ for an unknown result")
        XCTAssertFalse(input.accessibilityValue(for: unknown).contains("Lost"))
        XCTAssertEqual(input.pregameReading(zero), .value(Self.obs(0, "0%", Self.pinDetail)))
        XCTAssertEqual(FirstScorerGeometry10868.fraction(0, axis: Self.fullScale) ?? -1, 0, accuracy: 1e-9, "0% is a mark at the origin")
        XCTAssertEqual(input.pregameReading(absent), .missing("No pre-match chance"))
        XCTAssertEqual(input.accessibilityValue(for: absent), "Pre-match chance: No pre-match chance; Final result: Won")
        XCTAssertEqual(input.overview.count, 3, "every original stays")
    }

    func testOnlyAContextualFinalAnnouncesTheFinalResultTitle() {
        // CONSTRUCTED: distinct words for each title, so the spoken one is unambiguous.
        let words = FirstScorerOutcomeContext10868(
            pregameTitle: "Pre-match chance", currentTitle: "Current chance",
            liveResultTitle: "Shown live result", finalResultTitle: "Final result",
            selectionUnavailable: "Selected outcome unavailable.", spokenPregame: "Pre-match chance",
            spokenCurrent: "Current chance", spokenResult: "Spoken live result",
            selectHint: "Selects this outcome’s comparison")
        let rows = Self.outcomes(result: [Self.won, Self.resultPending, Self.lost])
        func contextual(_ phase: FirstScorerPhase10868) -> FirstScorerComparisonInput10868 {
            FirstScorerComparisonInput10868(
                phase: phase, title: "First team to score", context: "Polymarket · first team to score",
                overview: rows, selectedID: Self.albaceteID, selectedRow: nil,
                plotTitle: "Bars · each outcome’s pre-match chance", axis: Self.fullScale, coverage: nil,
                confirmed: nil, timing: nil, outcome: words, scorePath: nil)
        }

        // During play: an admitted result keeps the supplied spoken result title.
        let during = contextual(.during)
        XCTAssertEqual(during.spokenResultTitle, "Spoken live result")
        XCTAssertEqual(during.accessibilityValue(for: rows[0]), "Pre-match chance: 57%, \(Self.pinDetail); Spoken live result: Won")
        XCTAssertEqual(during.accessibilityComparison(for: rows[2]), "Pre-match chance: 33.5%, \(Self.pinDetail); Spoken live result: Lost")

        // After the final: the supplied final title, on every row and the selected comparison.
        let afterFinal = contextual(.final)
        XCTAssertEqual(afterFinal.spokenResultTitle, "Final result")
        XCTAssertEqual(afterFinal.accessibilityValue(for: rows[0]), "Pre-match chance: 57%, \(Self.pinDetail); Final result: Won")
        XCTAssertEqual(afterFinal.accessibilityComparison(for: rows[2]), "Pre-match chance: 33.5%, \(Self.pinDetail); Final result: Lost")
        XCTAssertFalse(afterFinal.accessibilityValue(for: rows[0]).contains("live result"))

        // Without a context the first-goalscorer card keeps its original spoken result, final included.
        let boldy = Self.row(22, "Matt Boldy", pregame: Self.boldyPregame, result: Self.notFirst)
        for phase in [FirstScorerPhase10868.during, .final] {
            let legacy = Self.input(phase, [boldy], selectedID: Self.pid(22))
            XCTAssertEqual(legacy.spokenResultTitle, "First-goalscorer result")
            XCTAssertEqual(legacy.accessibilityComparison(for: boldy),
                           "Pregame first-goalscorer chance: 9%, minute ending Oct 3, 4:50 PM PT · Kalshi; "
                           + "First-goalscorer result: Not first")
        }
    }

    func testMissingAndDuplicateSelectionsUseTheCallersWordsAndPickNobody() {
        let rows = Self.outcomes()
        let missing = Self.soccer(.during, rows, selectedID: Self.fid(244237999))
        XCTAssertEqual(missing.selection, .missing(Self.fid(244237999)))
        XCTAssertEqual(missing.selectionNotice, "Selected outcome unavailable.")
        XCTAssertTrue(rows.allSatisfy { !missing.isSelected($0) })
        XCTAssertNil(missing.detailsAction(canOpenDetails: true))

        let twice = rows + [rows[1]]
        let duplicate = Self.soccer(.during, twice, selectedID: Self.neitherID)
        XCTAssertEqual(duplicate.selection, .duplicate(Self.neitherID))
        XCTAssertEqual(duplicate.selectionNotice, "Selected outcome unavailable.")
        XCTAssertEqual(duplicate.overview.count, 4, "the duplicate is shown as supplied")
        XCTAssertTrue(twice.allSatisfy { duplicate.rowReading($0) != nil }, "every row keeps its own reading")
        XCTAssertNil(Self.soccer(.during, rows).selectionNotice, "no selection is not a notice")
    }

    func testEveryOriginalCarriesItsExactIDOnSelectAndDetails() {
        let rows = Self.finalOutcomes
        let input = Self.soccer(.final, rows, selectedID: Self.albaceteID)
        XCTAssertEqual(rows.compactMap { input.rowAction($0, canSelect: true) },
                       [FirstScorerAction10868.select(Self.valladolidID), .select(Self.neitherID), .select(Self.albaceteID)])
        XCTAssertTrue(rows.allSatisfy { input.rowAction($0, canSelect: false) == nil }, "no callback, static rows")
        XCTAssertEqual(input.detailsAction(canOpenDetails: true), .details(Self.albaceteID))
        XCTAssertEqual(FirstScorerAccessibilityID10868.row(Self.neitherID), "firstScorer10868.row.other:63178217:244237965")

        var selected: [String] = []
        var details: [String] = []
        for row in rows { input.rowAction(row, canSelect: true)?.perform(onSelect: { selected.append($0) }, onDetails: { details.append($0) }) }
        input.detailsAction(canOpenDetails: true)?.perform(onSelect: { selected.append($0) }, onDetails: { details.append($0) })
        XCTAssertEqual(selected, [Self.valladolidID, Self.neitherID, Self.albaceteID])
        XCTAssertEqual(details, [Self.albaceteID])
    }

    func testLongOutcomeNamesAndFiguresAreKeptWhole() {
        let long = Self.outcome(Self.fid(244237966), "Real Valladolid Club de Fútbol (reserve side, extended label)",
                                pregame: Self.obs(0.004, "<1%", Self.pinDetail), result: .won("Won after review"))
        let input = Self.soccer(.final, Self.finalOutcomes + [long])
        XCTAssertEqual(input.overview.last?.name, "Real Valladolid Club de Fútbol (reserve side, extended label)")
        XCTAssertEqual(input.accessibilityLabel(for: long), "Real Valladolid Club de Fútbol (reserve side, extended label)",
                       "no team line is added for an outcome")
        XCTAssertEqual(input.pregameReading(long).text, "<1%")
        XCTAssertEqual(input.rowReading(long), .result(.won("Won after review")))
        XCTAssertEqual(input.overview.count, 4, "nothing is capped")
    }

    /// Geometry only — CONSTRUCTED entry extents, not a rendered fit.
    func testObservedScoresWrapIntoWholeRowsAndNeverShrinkOrDrop() {
        let width: CGFloat = 327
        // Five compact entries fit one row at a phone width.
        let compact = Self.sizes([56, 56, 56, 56, 56], height: 44)
        let oneRow = FirstScorerGeometry10868.flowPlan(natural: compact, atWidth: compact, width: width)
        XCTAssertEqual(oneRow.frames.map(\.minY), [0, 0, 0, 0, 0])
        XCTAssertEqual(oneRow.frames.map(\.minX), [0, 64, 128, 192, 256])
        XCTAssertEqual(oneRow.size, CGSize(width: width, height: 44))

        // Large type: three to a row, the rest wrap below in order, nothing shrunk.
        let large = Self.sizes([96, 96, 96, 96, 96], height: 70)
        let wrapped = FirstScorerGeometry10868.flowPlan(natural: large, atWidth: large, width: width)
        XCTAssertEqual(wrapped.frames.map(\.minY), [0, 0, 0, 78, 78])
        XCTAssertEqual(wrapped.frames.map(\.size), large)
        XCTAssertEqual(wrapped.size.height, 148, "both rows and the gap are reserved")
        for frame in wrapped.frames { XCTAssertLessThanOrEqual(frame.maxX, width) }

        // One entry wider than the whole width takes its own row at its wrapped size.
        let natural = [CGSize(width: 56, height: 44), CGSize(width: 400, height: 44), CGSize(width: 56, height: 44)]
        let atWidth = [natural[0], CGSize(width: 320, height: 80), natural[2]]
        let wide = FirstScorerGeometry10868.flowPlan(natural: natural, atWidth: atWidth, width: width)
        XCTAssertEqual(wide.frames.map(\.origin), [CGPoint(x: 0, y: 0), CGPoint(x: 0, y: 52), CGPoint(x: 0, y: 140)])
        XCTAssertEqual(wide.frames[1].size, CGSize(width: 320, height: 80))
        XCTAssertEqual(wide.size, CGSize(width: width, height: 184))

        // Wider even when wrapped: the plan says so rather than hiding it.
        let unbreakable = FirstScorerGeometry10868.flowPlan(natural: [CGSize(width: 400, height: 44)],
                                                            atWidth: [CGSize(width: 360, height: 44)], width: width)
        XCTAssertEqual(unbreakable.size, CGSize(width: 360, height: 44))
        XCTAssertEqual(FirstScorerGeometry10868.flowPlan(natural: [], atWidth: [], width: width).frames, [])
        XCTAssertEqual(FirstScorerGeometry10868.flowPlan(natural: compact, atWidth: [], width: width).frames, [],
                       "counts that disagree place nothing rather than guess")
    }
}
