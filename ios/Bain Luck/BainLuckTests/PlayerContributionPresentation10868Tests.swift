import SwiftUI
import XCTest
@testable import Bain_Luck

/// #10868 — a player's points or assists as one stateless presentation leaf
/// across pregame, live and final.
///
/// The view is SwiftUI and is not rasterised here. What is asserted is the
/// rules it defers to: which readings each phase shows, the exact-id milestone
/// selection and player choice, the action each control carries, the timing it
/// may show, the chart geometry and label planning, and the spoken text.
/// Nothing here claims a rendered fit.
///
/// ARCHIVED raw values come from Minnesota–Boston, event 15169793, as copied in
/// `shipping-adoption-20261027/CONTRIBUTION-RETAINED-CASES.json` (sha256
/// 554d1795…c9fb8) from `hockeyContributions.json` (dae3c3ea…de30) and
/// `hockeyLive.json` (60c5a526…e434). Keys are
/// `nhl-15169793-game-markets.json:player_props:N`:
///   points market 64871068
///     Hughes   64 1+ 0.69 @ 2026-10-03T23:55Z · 65 2+ 0.33 @ 23:51Z · 66 3+ none
///              final 2 points (1 goal + 1 assist); 1+/2+ is_winner true, 3+ false
///     Kaprizov 59 1+ 0.72 @ 19:22Z · 60 2+ 0.39 @ 19:51Z · 61 3+ none
///              live 60: 0.54 @ 2026-10-04T01:44Z; 59: 0.99 @ 01:24Z
///              stage "Late second period" 01:45:25Z: 1 point (1 goal, 0 assists)
///              final 2 points (2 goals + 0 assists)
///     Shabanov 62 1+ none (is_winner true) · 63 2+ none (is_winner false);
///              exact final count unknown
///   assists market 64870807
///     Hughes   40 1+ 0.63 @ 23:54Z · 41 2+ 0.27 @ 23:58Z · 42 3+ none
///              final 1 assist; 1+ is_winner true, 2+/3+ false
///     Shabanov 38 1+ observations 0.40 @ 13:23Z and 0.34 @ 22:47Z (is_winner
///              true) · 39 2+ none (is_winner false)
/// Where a record holds more than one pregame observation, the one used here
/// is a CONSTRUCTED owner election (the last retained); this view never elects.
/// The 01:44Z reading and the 01:45:25Z count keep their own clocks.
///
/// CONSTRUCTED owner-resolved inputs (this leaf does not resolve them): every
/// display string and PT time/source line; target labels; result words;
/// count units, breakdowns and progress status/fractions; the movement
/// string; tick labels; the player choices; the reached/withheld/unavailable
/// states; and the malformed, stale, duplicate, out-of-range, long-text and
/// five-milestone cases. The checkpoints are reconstructed archive evidence,
/// not proof of historical app arrival.
final class PlayerContributionPresentation10868Tests: XCTestCase {

    // MARK: Fixtures

    private static func key(_ index: Int) -> String { "nhl-15169793-game-markets.json:player_props:\(index)" }

    private static func obs(_ probability: Double, _ text: String, _ detail: String) -> PlayerContributionObservation10868 {
        PlayerContributionObservation10868(probability: probability, text: text, accessibilityDetail: detail)
    }

    private static let noReading = PlayerContributionCurrent10868.unavailable("No in-game reading")
    private static let pending = PlayerContributionResult10868.unconfirmed("Result unconfirmed")
    private static let reached = PlayerContributionResult10868.reached("Reached")
    private static let missed = PlayerContributionResult10868.missed("Missed")

    private static func milestone(
        _ index: Int,
        _ target: String,
        _ title: String,
        before: PlayerContributionObservation10868?,
        current: PlayerContributionCurrent10868 = noReading,
        progress: PlayerContributionProgress10868? = nil,
        result: PlayerContributionResult10868 = pending
    ) -> PlayerContributionMilestone10868 {
        PlayerContributionMilestone10868(
            id: key(index),
            target: target,
            title: title,
            before: before,
            beforeMissing: "Unavailable",
            current: current,
            progress: progress,
            result: result
        )
    }

    private static let ticks = [
        PlayerContributionTick10868(value: 0, text: "0%"),
        PlayerContributionTick10868(value: 0.5, text: "50%"),
        PlayerContributionTick10868(value: 1, text: "100%"),
    ]

    private static func input(
        _ phase: PlayerContributionPhase10868,
        _ player: PlayerContributionPlayer10868?,
        orientation: PlayerContributionOrientation10868 = .columns,
        selected: String? = nil,
        chooser: PlayerContributionChooser10868? = nil,
        timing: PlayerContributionTiming10868? = nil
    ) -> PlayerContributionInput10868 {
        PlayerContributionInput10868(
            phase: phase,
            orientation: orientation,
            eyebrow: orientation == .columns ? "PLAYER POINTS" : "PLAYER ASSISTS",
            title: orientation == .columns ? "Points in context" : "Who set them up?",
            definition: orientation == .columns
                ? "One point for each goal or assist."
                : "An assist credits a player who helped create a goal.",
            player: player,
            selectedMilestoneID: selected,
            chartTitle: "Pre-game chances · at least this many",
            ticks: ticks,
            chooser: chooser,
            timing: timing
        )
    }

    // Pregame baselines (ARCHIVED value and time, CONSTRUCTED text/detail).
    private static let hughes1Pts = obs(0.69, "69%", "minute ending Oct 3, 4:55 PM PT · Kalshi")
    private static let hughes2Pts = obs(0.33, "33%", "minute ending Oct 3, 4:51 PM PT · Kalshi")
    private static let hughes1Ast = obs(0.63, "63%", "minute ending Oct 3, 4:54 PM PT · Kalshi")
    private static let hughes2Ast = obs(0.27, "27%", "minute ending Oct 3, 4:58 PM PT · Kalshi")
    private static let kaprizov1Pts = obs(0.72, "72%", "minute ending Oct 3, 12:22 PM PT · Kalshi")
    private static let kaprizov2Pts = obs(0.39, "39%", "minute ending Oct 3, 12:51 PM PT · Kalshi")
    private static let shabanov1Ast = obs(0.34, "34%", "minute ending Oct 3, 3:47 PM PT · Kalshi")

    /// ARCHIVED live reading for Kaprizov 2+ (0.54 @ 01:44Z), CONSTRUCTED text and movement.
    private static let kaprizov2Live = obs(0.54, "54%", "recorded Oct 3, 6:44 PM PT · Kalshi")
    private static let kaprizovMovement = "+15 percentage points since pregame"

    /// A settled price that must never read as a chance (CONSTRUCTED).
    private static let settledHundred = obs(1.0, "100%", "settled Oct 3, 7:58 PM PT · Kalshi")

    private static let hughesFinalPoints = PlayerContributionActual10868.count(
        PlayerContributionCount10868(count: "2", unit: "points", breakdown: "1 goal + 1 assist",
                                     accessibilityDetail: "final box score · ESPN")
    )
    private static let kaprizovSoFar = PlayerContributionActual10868.count(
        PlayerContributionCount10868(count: "1", unit: "point so far", breakdown: "1 goal + 0 assists",
                                     accessibilityDetail: "as of 6:45 PM PT, 2nd period, 4:09 left · ESPN")
    )

    private static func hughesPoints(
        actual: PlayerContributionActual10868 = hughesFinalPoints,
        current: (Int) -> PlayerContributionCurrent10868 = { _ in noReading },
        result: (Int) -> PlayerContributionResult10868 = { _ in pending }
    ) -> PlayerContributionPlayer10868 {
        PlayerContributionPlayer10868(
            id: "4320548",
            name: "Quinn Hughes",
            team: "Minnesota",
            milestones: [
                milestone(64, "1+", "1+ points", before: hughes1Pts, current: current(64), result: result(64)),
                milestone(65, "2+", "2+ points", before: hughes2Pts, current: current(65), result: result(65)),
                milestone(66, "3+", "3+ points", before: nil, current: current(66), result: result(66)),
            ],
            actual: actual
        )
    }

    private static var hughesPointsFinal: PlayerContributionPlayer10868 {
        hughesPoints(result: { $0 == 66 ? missed : reached })
    }

    private static func hughesAssists(result: (Int) -> PlayerContributionResult10868 = { $0 == 40 ? reached : missed })
        -> PlayerContributionPlayer10868 {
        PlayerContributionPlayer10868(
            id: "4320548",
            name: "Quinn Hughes",
            team: "Minnesota",
            milestones: [
                milestone(40, "1+", "1+ assists", before: hughes1Ast, result: result(40)),
                milestone(41, "2+", "2+ assists", before: hughes2Ast, result: result(41)),
                milestone(42, "3+", "3+ assists", before: nil, result: result(42)),
            ],
            actual: .count(PlayerContributionCount10868(count: "1", unit: "assist", breakdown: nil,
                                                        accessibilityDetail: "final box score · ESPN"))
        )
    }

    /// Late second period: 1+ already reached, 2+ recorded at 01:44Z, 3+ no reading.
    private static var kaprizovLive: PlayerContributionPlayer10868 {
        PlayerContributionPlayer10868(
            id: "3942335",
            name: "Kirill Kaprizov",
            team: "Minnesota",
            milestones: [
                milestone(59, "1+", "1+ points", before: kaprizov1Pts, current: .reached("Reached so far"),
                          progress: PlayerContributionProgress10868(status: "Milestone reached so far", fraction: 1),
                          result: reached),
                milestone(60, "2+", "2+ points", before: kaprizov2Pts,
                          current: .recorded(kaprizov2Live, movement: kaprizovMovement),
                          progress: PlayerContributionProgress10868(status: "1 more for 2+", fraction: 0.5),
                          result: reached),
                milestone(61, "3+", "3+ points", before: nil, current: noReading,
                          progress: PlayerContributionProgress10868(status: "2 more for 3+", fraction: 1.0 / 3.0),
                          result: missed),
            ],
            actual: kaprizovSoFar
        )
    }

    private static func shabanovPoints() -> PlayerContributionPlayer10868 {
        PlayerContributionPlayer10868(
            id: "shabanov-49",
            name: "Max Shabanov",
            team: "Minnesota",
            milestones: [
                milestone(62, "1+", "1+ points", before: nil, result: reached),
                milestone(63, "2+", "2+ points", before: nil, result: missed),
            ],
            actual: .unavailable("Exact final count unavailable")
        )
    }

    private static func shabanovAssists() -> PlayerContributionPlayer10868 {
        PlayerContributionPlayer10868(
            id: "shabanov-49",
            name: "Max Shabanov",
            team: "Minnesota",
            milestones: [
                milestone(38, "1+", "1+ assists", before: shabanov1Ast, result: reached),
                milestone(39, "2+", "2+ assists", before: nil, result: missed),
            ],
            actual: .unavailable("Exact final count unavailable")
        )
    }

    private static let chooser = PlayerContributionChooser10868(
        title: "Choose player · 3",
        choices: [
            PlayerContributionChoice10868(id: "3942335", name: "Kirill Kaprizov", detail: "Minnesota"),
            PlayerContributionChoice10868(id: "4320548", name: "Quinn Hughes", detail: "Minnesota"),
            PlayerContributionChoice10868(id: "shabanov-49", name: "Max Shabanov", detail: nil),
        ]
    )

    // MARK: Before play

    func testBeforeShowsOnlyPregameChancesEvenWhenLaterInputsArePresent() {
        let player = Self.hughesPoints(current: { _ in .recorded(Self.settledHundred, movement: "+31 points") },
                                       result: { _ in Self.reached })
        let input = Self.input(.before, player, selected: Self.key(65), chooser: Self.chooser)

        XCTAssertEqual(input.selection.milestone?.id, Self.key(65))
        for milestone in player.milestones {
            XCTAssertNil(input.currentReading(milestone))
            XCTAssertNil(input.currentFraction(milestone))
            XCTAssertNil(input.secondReading(milestone))
            XCTAssertNil(input.result(milestone))
            XCTAssertNil(input.movement(milestone))
            XCTAssertFalse(input.showsCurrentKey(milestone))
        }
        XCTAssertNil(input.actualPresentation, "No count before play, not even a zero")
        XCTAssertFalse(input.showsChartKey)
        XCTAssertEqual(input.accessibilityComparison(for: player.milestones[1]),
                       "Pregame chance: 33%, minute ending Oct 3, 4:51 PM PT · Kalshi")
    }

    func testBeforeHidesProgressAndKeepsMissingMilestoneWithoutAZeroBar() {
        let player = Self.kaprizovLive
        let input = Self.input(.before, player, selected: Self.key(60))

        XCTAssertNil(input.progress(player.milestones[1]))
        XCTAssertEqual(player.milestones.map(\.id), [Self.key(59), Self.key(60), Self.key(61)])
        XCTAssertEqual(input.beforeFraction(player.milestones[0]), 0.72)
        XCTAssertEqual(input.beforeFraction(player.milestones[1]), 0.39)
        XCTAssertNil(input.beforeFraction(player.milestones[2]), "3+ is absent, so no bar — never a zero")
        XCTAssertEqual(input.beforeReading(player.milestones[2]), .missing("Unavailable"))
    }

    // MARK: During play

    func testDuringPairsPregameWithTheRecordedChanceAndKeepsTheCountApart() {
        let player = Self.kaprizovLive
        let input = Self.input(.during, player, selected: Self.key(60))
        let twoPlus = player.milestones[1]

        XCTAssertEqual(input.secondReading(twoPlus), .current(.chance(Self.kaprizov2Live)))
        XCTAssertTrue(input.showsCurrentKey(twoPlus))
        XCTAssertEqual(input.beforeFraction(twoPlus), 0.39)
        XCTAssertEqual(input.currentFraction(twoPlus), 0.54)
        XCTAssertEqual(input.movement(twoPlus), Self.kaprizovMovement, "Movement is the owner's string, never derived")
        XCTAssertNil(input.result(twoPlus), "A supplied result is not shown during play")
        XCTAssertEqual(input.actualPresentation,
                       PlayerContributionActualPresentation10868(title: "Count so far", actual: Self.kaprizovSoFar))
        XCTAssertEqual(input.progress(twoPlus)?.status, "1 more for 2+")
    }

    func testDuringReadingAndCountKeepTheirOwnClocks() {
        let input = Self.input(.during, Self.kaprizovLive, selected: Self.key(60))
        let comparison = input.accessibilityComparison(for: Self.kaprizovLive.milestones[1])
        let count = input.accessibilityActual(input.actualPresentation!)

        XCTAssertTrue(comparison.contains("6:44 PM PT"))
        XCTAssertFalse(comparison.contains("6:45 PM PT"))
        XCTAssertTrue(count.contains("6:45 PM PT"))
        XCTAssertFalse(count.contains("6:44 PM PT"))
    }

    func testDuringReachedMilestoneHasNoMarkAndIsNeitherSettlementNorHundred() {
        let input = Self.input(.during, Self.kaprizovLive, selected: Self.key(59))
        let onePlus = Self.kaprizovLive.milestones[0]

        XCTAssertEqual(input.secondReading(onePlus), .current(.actual("Reached so far")))
        XCTAssertEqual(input.currentReading(onePlus)?.title, "Actual so far", "Reached is performance, not a chance")
        XCTAssertNil(input.currentFraction(onePlus))
        XCTAssertFalse(input.showsCurrentKey(onePlus))
        XCTAssertNil(input.result(onePlus))
        XCTAssertNil(input.movement(onePlus))
        let spoken = input.accessibilityComparison(for: onePlus)
        XCTAssertEqual(spoken, "Pregame chance: 72%, minute ending Oct 3, 12:22 PM PT · Kalshi; Actual so far: Reached so far")
        XCTAssertFalse(spoken.contains("In-game chance"), "Reached is never spoken as a chance")
        XCTAssertFalse(spoken.contains("100%"))
        XCTAssertFalse(spoken.contains("Reached;"), "The contract result is not spoken during play")
    }

    func testDuringWithheldAndUnavailableKeepTheOwnersWordsAndDrawNoMark() {
        let withheld = Self.milestone(60, "2+", "2+ points", before: Self.kaprizov2Pts,
                                      current: .withheld("No update since goal"))
        let player = PlayerContributionPlayer10868(id: "3942335", name: "Kirill Kaprizov", team: "Minnesota",
                                                   milestones: [withheld, Self.kaprizovLive.milestones[2]],
                                                   actual: Self.kaprizovSoFar)
        let input = Self.input(.during, player, selected: Self.key(60))

        XCTAssertEqual(input.currentReading(withheld), .chanceStatus("No update since goal"))
        XCTAssertEqual(input.currentReading(withheld)?.title, "In-game chance")
        XCTAssertNil(input.currentFraction(withheld))
        XCTAssertNil(input.movement(withheld))
        XCTAssertEqual(input.currentReading(player.milestones[1]), .chanceStatus("No in-game reading"))
        XCTAssertNil(input.currentFraction(player.milestones[1]))
        XCTAssertEqual(input.accessibilityValue(for: player.milestones[1]),
                       "Pregame chance: Unavailable; In-game chance: No in-game reading")
    }

    func testDuringCountUnavailableStaysWordsNeverZero() {
        let player = PlayerContributionPlayer10868(id: "shabanov-49", name: "Max Shabanov", team: nil,
                                                   milestones: Self.shabanovPoints().milestones,
                                                   actual: .unavailable("Count unavailable"))
        let input = Self.input(.during, player)

        XCTAssertEqual(input.actualPresentation?.actual, .unavailable("Count unavailable"))
        XCTAssertEqual(input.accessibilityActual(input.actualPresentation!), "Count unavailable")
    }

    // MARK: Reached is performance

    func testReachedReadsAsActualSoFarOnTheRowAndInSpeechWhileTheCountKeepsItsClock() {
        let input = Self.input(.during, Self.kaprizovLive, selected: Self.key(60))
        let onePlus = Self.kaprizovLive.milestones[0]

        XCTAssertEqual(input.row(onePlus).statuses,
                       [PlayerContributionRowStatus10868(title: "Actual so far", words: "Reached so far")])
        XCTAssertEqual(input.accessibilityValue(for: onePlus),
                       "Pregame chance: 72%, minute ending Oct 3, 12:22 PM PT · Kalshi; Actual so far: Reached so far")
        XCTAssertEqual(input.actualPresentation?.title, "Count so far", "The clocked count stays its own block")
        XCTAssertTrue(input.accessibilityActual(input.actualPresentation!).contains("6:45 PM PT"))
        XCTAssertFalse(input.accessibilityValue(for: onePlus).contains("6:45 PM PT"), "No count-derived status")
    }

    func testUnavailableAndWithheldKeepChanceWording() {
        XCTAssertEqual(PlayerContributionCurrentReading10868.chanceStatus("No recent probability update").title, "In-game chance")
        XCTAssertEqual(PlayerContributionCurrentReading10868.chanceStatus("No update since goal").spokenTitle, "In-game chance")
        XCTAssertEqual(PlayerContributionCurrentReading10868.actual("Reached so far").title, "Actual so far")
        XCTAssertEqual(PlayerContributionCurrentReading10868.actual("Reached so far").spokenTitle, "Actual so far")
        XCTAssertEqual(PlayerContributionCurrentReading10868.chance(Self.kaprizov2Live).title, "Recorded in-game")
        XCTAssertEqual(PlayerContributionCurrentReading10868.chance(Self.kaprizov2Live).spokenTitle, "Recorded in-game chance")
    }

    func testReachedWithAMissingBaselineKeepsBothLabelledWords() {
        let reachedNoBaseline = Self.milestone(62, "1+", "1+ points", before: nil, current: .reached("Reached so far"))
        let player = PlayerContributionPlayer10868(id: "shabanov-49", name: "Max Shabanov", team: "Minnesota",
                                                   milestones: [reachedNoBaseline], actual: .unavailable("Count unavailable"))
        let input = Self.input(.during, player, selected: Self.key(62))

        XCTAssertEqual(input.row(reachedNoBaseline).statuses, [
            PlayerContributionRowStatus10868(title: "Pregame chance", words: "Unavailable"),
            PlayerContributionRowStatus10868(title: "Actual so far", words: "Reached so far"),
        ])
        XCTAssertEqual(input.accessibilityComparison(for: reachedNoBaseline),
                       "Pregame chance: Unavailable; Actual so far: Reached so far")
    }

    // MARK: Row status, both orientations

    func testUnselectedMilestonesKeepTheirStatusWordsWhateverIsSelected() {
        let milestones = Self.kaprizovLive.milestones
        let expected = [
            PlayerContributionRowPresentation10868(
                pregame: Self.kaprizov1Pts, current: nil, hasCurrentLane: true,
                statuses: [PlayerContributionRowStatus10868(title: "Actual so far", words: "Reached so far")]),
            PlayerContributionRowPresentation10868(
                pregame: Self.kaprizov2Pts, current: Self.kaprizov2Live, hasCurrentLane: true, statuses: []),
            PlayerContributionRowPresentation10868(
                pregame: nil, current: nil, hasCurrentLane: true,
                statuses: [PlayerContributionRowStatus10868(title: "Pregame chance", words: "Unavailable"),
                           PlayerContributionRowStatus10868(title: "In-game chance", words: "No in-game reading")]),
        ]
        for selected in [Self.key(59), Self.key(60), Self.key(61), nil, Self.key(41)] {
            for orientation in [PlayerContributionOrientation10868.columns, .bars] {
                let input = Self.input(.during, Self.kaprizovLive, orientation: orientation, selected: selected)
                XCTAssertEqual(milestones.map { input.row($0) }, expected,
                               "selected \(selected ?? "none"), \(orientation)")
            }
        }
    }

    func testWithheldStatusesStayOnUnselectedRowsWithNoCurrentMark() {
        let sinceGoal = Self.milestone(59, "1+", "1+ points", before: Self.kaprizov1Pts, current: .withheld("No update since goal"))
        let notRecent = Self.milestone(61, "3+", "3+ points", before: nil, current: .withheld("No recent probability update"))
        let recorded = Self.kaprizovLive.milestones[1]
        let player = PlayerContributionPlayer10868(id: "3942335", name: "Kirill Kaprizov", team: "Minnesota",
                                                   milestones: [sinceGoal, recorded, notRecent], actual: Self.kaprizovSoFar)
        let input = Self.input(.during, player, selected: Self.key(60))

        XCTAssertFalse(input.isSelected(sinceGoal))
        XCTAssertEqual(input.row(sinceGoal).statuses,
                       [PlayerContributionRowStatus10868(title: "In-game chance", words: "No update since goal")])
        XCTAssertEqual(input.row(notRecent).statuses, [
            PlayerContributionRowStatus10868(title: "Pregame chance", words: "Unavailable"),
            PlayerContributionRowStatus10868(title: "In-game chance", words: "No recent probability update"),
        ])
        for milestone in [sinceGoal, notRecent] {
            XCTAssertNil(input.row(milestone).current, "No current probability mark for a status")
            XCTAssertNil(input.currentFraction(milestone))
            XCTAssertTrue(input.row(milestone).hasCurrentLane, "The in-game lane stays, empty, so the scale lines up")
        }
        XCTAssertEqual(input.row(sinceGoal).pregame, Self.kaprizov1Pts, "The pregame direct value stays")
    }

    func testRowLabelsPregameMissingOnlyWhenAnInGameReadingCanSitBesideIt() {
        let player = Self.hughesPoints(current: { _ in .reached("Reached so far") }, result: { _ in Self.reached })
        let threePlus = player.milestones[2]

        let before = Self.input(.before, player, selected: Self.key(64)).row(threePlus)
        XCTAssertEqual(before.statuses, [PlayerContributionRowStatus10868(title: nil, words: "Unavailable")])

        let during = Self.input(.during, player, selected: Self.key(64)).row(threePlus)
        XCTAssertEqual(during.statuses, [
            PlayerContributionRowStatus10868(title: "Pregame chance", words: "Unavailable"),
            PlayerContributionRowStatus10868(title: "Actual so far", words: "Reached so far"),
        ])

        let final = Self.input(.final, player, selected: Self.key(64)).row(threePlus)
        XCTAssertEqual(final.statuses, [PlayerContributionRowStatus10868(title: nil, words: "Unavailable")])
    }

    func testBeforeAndFinalSuppressEveryLiveStatusOnEveryRow() {
        let states: [PlayerContributionCurrent10868] = [
            .reached("Reached so far"), .withheld("No update since goal"),
            .withheld("No recent probability update"), .unavailable("No in-game reading"),
            .recorded(Self.settledHundred, movement: "+31 points"),
        ]
        for state in states {
            let player = Self.hughesPoints(current: { _ in state }, result: { $0 == 66 ? Self.missed : Self.reached })
            for phase in [PlayerContributionPhase10868.before, .final] {
                for selected in [Self.key(65), nil] {
                    let input = Self.input(phase, player, selected: selected)
                    for milestone in player.milestones {
                        let row = input.row(milestone)
                        XCTAssertNil(row.current)
                        XCTAssertFalse(row.hasCurrentLane)
                        XCTAssertTrue(row.statuses.allSatisfy { $0.title == nil }, "\(phase) \(state)")
                        XCTAssertEqual(row.statuses.map(\.words), milestone.before == nil ? ["Unavailable"] : [])
                        XCTAssertFalse(input.accessibilityValue(for: milestone).contains("so far"))
                        XCTAssertFalse(input.accessibilityValue(for: milestone).contains("update"))
                    }
                }
            }
        }
    }

    func testAssistsBarsCarryTheSameRowSemantics() {
        let onePlus = Self.milestone(40, "1+", "1+ assists", before: Self.hughes1Ast, current: .reached("Reached so far"))
        let twoPlus = Self.milestone(41, "2+", "2+ assists", before: Self.hughes2Ast, current: .withheld("No update since goal"))
        let threePlus = Self.milestone(42, "3+", "3+ assists", before: nil, current: .unavailable("No in-game reading"))
        let player = PlayerContributionPlayer10868(id: "4320548", name: "Quinn Hughes", team: "Minnesota",
                                                   milestones: [onePlus, twoPlus, threePlus],
                                                   actual: .count(PlayerContributionCount10868(
                                                       count: "1", unit: "assist so far", breakdown: nil,
                                                       accessibilityDetail: "as of 6:45 PM PT, 2nd period · ESPN")))
        let input = Self.input(.during, player, orientation: .bars, selected: nil)

        XCTAssertEqual(input.row(onePlus).statuses.map(\.title), ["Actual so far"])
        XCTAssertEqual(input.row(twoPlus).statuses.map(\.title), ["In-game chance"])
        XCTAssertEqual(input.row(threePlus).statuses.map(\.title), ["Pregame chance", "In-game chance"])
        XCTAssertEqual(input.row(onePlus).pregame, Self.hughes1Ast)
        XCTAssertFalse(input.showsChartKey, "No filled marks, no key")
    }

    // MARK: After the final

    func testFinalComparesPregameWithTheResultAndShowsTheFinalCount() {
        let player = Self.hughesPointsFinal
        let input = Self.input(.final, player, selected: Self.key(65))
        let twoPlus = player.milestones[1]

        XCTAssertEqual(input.secondReading(twoPlus), .result(.reached("Reached")))
        XCTAssertEqual(input.beforeFraction(twoPlus), 0.33, "Final keeps the pregame marks")
        XCTAssertEqual(input.actualPresentation?.title, "Final count")
        XCTAssertEqual(input.accessibilityActual(input.actualPresentation!), "2 points, 1 goal + 1 assist, final box score · ESPN")
        XCTAssertNil(input.progress(twoPlus))
        XCTAssertEqual(input.accessibilityComparison(for: twoPlus),
                       "Pregame chance: 33%, minute ending Oct 3, 4:51 PM PT · Kalshi; Final result: Reached")
    }

    func testFinalNeverRelabelsASettledPriceAsAChance() {
        let player = Self.hughesPoints(current: { _ in .recorded(Self.settledHundred, movement: "+67 points") },
                                       result: { $0 == 66 ? Self.missed : Self.reached })
        let input = Self.input(.final, player, selected: Self.key(65))

        for milestone in player.milestones {
            XCTAssertNil(input.currentReading(milestone))
            XCTAssertNil(input.currentFraction(milestone))
            XCTAssertNil(input.movement(milestone))
            XCTAssertFalse(input.accessibilityValue(for: milestone).contains("100%"))
            XCTAssertFalse(input.accessibilityComparison(for: milestone).contains("100%"))
        }
        XCTAssertFalse(input.showsChartKey)
    }

    func testFinalKnownResultWithUnknownCountStaysExplicit() {
        let player = Self.shabanovPoints()
        let input = Self.input(.final, player, selected: Self.key(62))

        XCTAssertEqual(input.secondReading(player.milestones[0]), .result(.reached("Reached")))
        XCTAssertEqual(input.secondReading(player.milestones[1]), .result(.missed("Missed")))
        XCTAssertEqual(input.actualPresentation?.actual, .unavailable("Exact final count unavailable"))
        XCTAssertEqual(input.beforeReading(player.milestones[0]), .missing("Unavailable"))
        XCTAssertEqual(input.accessibilityComparison(for: player.milestones[0]),
                       "Pregame chance: Unavailable; Final result: Reached")
    }

    func testResultIsNeverDerivedFromTheCount() {
        // Hughes finished with one assist; the owner has not admitted the 2+ result.
        let player = Self.hughesAssists(result: { _ in Self.pending })
        let input = Self.input(.final, player, orientation: .bars, selected: Self.key(41))
        let twoPlus = player.milestones[1]

        XCTAssertEqual(input.secondReading(twoPlus), .result(.unconfirmed("Result unconfirmed")))
        XCTAssertFalse(PlayerContributionResult10868.unconfirmed("Result unconfirmed").isAdmitted)
        XCTAssertTrue(Self.missed.isAdmitted)
        XCTAssertEqual(input.accessibilityComparison(for: twoPlus),
                       "Pregame chance: 27%, minute ending Oct 3, 4:58 PM PT · Kalshi; Final result: Result unconfirmed")
    }

    func testAssistsFinalKeepsOwnerElectedBaselineAndMissingSecondMilestone() {
        let player = Self.shabanovAssists()
        let input = Self.input(.final, player, orientation: .bars, selected: Self.key(38))

        XCTAssertEqual(input.beforeFraction(player.milestones[0]), 0.34)
        XCTAssertNil(input.beforeFraction(player.milestones[1]))
        XCTAssertEqual(input.secondReading(player.milestones[0]), .result(.reached("Reached")))
    }

    // MARK: Milestone selection

    func testExactSelectionKeepsOwnerOrderAndMarksOneMilestone() {
        let player = Self.hughesPointsFinal
        let input = Self.input(.final, player, selected: Self.key(66))

        XCTAssertEqual(input.milestones, player.milestones, "Membership and order are the owner's")
        XCTAssertEqual(player.milestones.filter { input.isSelected($0) }.map(\.id), [Self.key(66)])
        XCTAssertNil(input.selectionNotice)
    }

    func testMissingSelectionSelectsNobody() {
        let input = Self.input(.final, Self.hughesPointsFinal, selected: Self.key(41),
                               timing: PlayerContributionTiming10868(milestoneID: Self.key(41), title: "t", lines: []))

        XCTAssertEqual(input.selection, .missing(Self.key(41)))
        XCTAssertEqual(input.selectionNotice, "Selected milestone unavailable.")
        XCTAssertFalse(input.milestones.contains { input.isSelected($0) })
        XCTAssertNil(input.detailsAction(canOpenDetails: true))
        XCTAssertNil(input.timingPresentation(hasBinding: false))
    }

    func testDuplicateSelectionSelectsNobodyAndKeepsBothRows() {
        let first = Self.milestone(65, "2+", "2+ points", before: Self.hughes2Pts)
        let twin = Self.milestone(65, "2+", "2+ points (repeat)", before: Self.hughes2Pts)
        let player = PlayerContributionPlayer10868(id: "4320548", name: "Quinn Hughes", team: "Minnesota",
                                                   milestones: [first, twin], actual: Self.hughesFinalPoints)
        let input = Self.input(.before, player, selected: Self.key(65))

        XCTAssertEqual(input.selection, .duplicate(Self.key(65)))
        XCTAssertEqual(input.selectionNotice, "Selected milestone unavailable.")
        XCTAssertEqual(input.milestones.count, 2)
        XCTAssertFalse(input.isSelected(first))
        XCTAssertFalse(input.isSelected(twin))
    }

    func testNoSelectionShowsTheChartWithoutComparisonOrNotice() {
        let input = Self.input(.before, Self.hughesPoints(), selected: nil)

        XCTAssertEqual(input.selection, .none)
        XCTAssertNil(input.selectionNotice)
        XCTAssertEqual(input.milestones.count, 3)
        XCTAssertNil(input.detailsAction(canOpenDetails: true))
    }

    func testMissingPlayerShowsANoticeAndNoMilestonesOrCount() {
        let input = Self.input(.final, nil, selected: Self.key(65), chooser: Self.chooser)

        XCTAssertEqual(input.selection, .none)
        XCTAssertEqual(input.selectionNotice, "Selected player unavailable.")
        XCTAssertTrue(input.milestones.isEmpty)
        XCTAssertNil(input.actualPresentation)
        XCTAssertFalse(Self.chooser.choices.contains { input.isChosen($0) })
        XCTAssertNotNil(input.chooserPresentation(hasBinding: false), "The page's choices stay reachable")
    }

    // MARK: Player choice

    func testChooserMarksOnlyTheExactUniquePlayer() {
        let input = Self.input(.final, Self.hughesPointsFinal, chooser: Self.chooser)
        XCTAssertEqual(Self.chooser.choices.filter { input.isChosen($0) }.map(\.id), ["4320548"])

        let doubled = PlayerContributionChooser10868(title: "Choose player · 2", choices: [
            PlayerContributionChoice10868(id: "4320548", name: "Quinn Hughes", detail: nil),
            PlayerContributionChoice10868(id: "4320548", name: "Q. Hughes", detail: nil),
        ])
        let duplicate = Self.input(.final, Self.hughesPointsFinal, chooser: doubled)
        XCTAssertFalse(doubled.choices.contains { duplicate.isChosen($0) })

        let absent = PlayerContributionChooser10868(title: "Choose player · 1", choices: [Self.chooser.choices[0]])
        let notListed = Self.input(.final, Self.hughesPointsFinal, chooser: absent)
        XCTAssertFalse(notListed.isChosen(absent.choices[0]), "No first-choice fallback")
    }

    func testChooserIsADisclosureOnlyWithAPageBinding() {
        let input = Self.input(.during, Self.kaprizovLive, chooser: Self.chooser)
        XCTAssertEqual(input.chooserPresentation(hasBinding: true), .disclosure(Self.chooser))
        XCTAssertEqual(input.chooserPresentation(hasBinding: false), .expanded(Self.chooser))

        let empty = Self.input(.during, Self.kaprizovLive,
                               chooser: PlayerContributionChooser10868(title: "Choose player · 0", choices: []))
        XCTAssertNil(empty.chooserPresentation(hasBinding: true))
        XCTAssertNil(Self.input(.during, Self.kaprizovLive).chooserPresentation(hasBinding: true))
    }

    // MARK: Callbacks

    func testActionsCarryExactOriginalIDs() {
        let input = Self.input(.final, Self.hughesPointsFinal, selected: Self.key(65), chooser: Self.chooser)
        var selected: [String] = []
        var chosen: [String] = []
        var details: [String] = []

        for milestone in input.milestones {
            input.milestoneAction(milestone, canSelect: true)?
                .perform(onSelect: { selected.append($0) }, onChoosePlayer: { chosen.append($0) }, onDetails: { details.append($0) })
        }
        input.choiceAction(Self.chooser.choices[2], canChoose: true)?
            .perform(onSelect: { selected.append($0) }, onChoosePlayer: { chosen.append($0) }, onDetails: { details.append($0) })
        input.detailsAction(canOpenDetails: true)?
            .perform(onSelect: { selected.append($0) }, onChoosePlayer: { chosen.append($0) }, onDetails: { details.append($0) })

        XCTAssertEqual(selected, [Self.key(64), Self.key(65), Self.key(66)])
        XCTAssertEqual(chosen, ["shabanov-49"])
        XCTAssertEqual(details, [Self.key(65)])
    }

    func testNoCallbackMeansNoAction() {
        let input = Self.input(.final, Self.hughesPointsFinal, selected: Self.key(65), chooser: Self.chooser)

        XCTAssertNil(input.milestoneAction(input.milestones[0], canSelect: false))
        XCTAssertNil(input.choiceAction(Self.chooser.choices[0], canChoose: false))
        XCTAssertNil(input.detailsAction(canOpenDetails: false))
    }

    // MARK: Timing

    func testTimingBelongsOnlyToTheSelectedMilestone() {
        let timing = PlayerContributionTiming10868(
            milestoneID: Self.key(60),
            title: "Kirill Kaprizov 2+ points · probability timing",
            lines: ["Pregame: minute ending Oct 3, 12:51 PM PT", "In-game: recorded Oct 3, 6:44 PM PT"]
        )
        let mine = Self.input(.during, Self.kaprizovLive, selected: Self.key(60), timing: timing)
        XCTAssertEqual(mine.timingPresentation(hasBinding: true), .disclosure(timing))
        XCTAssertEqual(mine.timingPresentation(hasBinding: false), .expanded(timing))

        let other = Self.input(.during, Self.kaprizovLive, selected: Self.key(59), timing: timing)
        XCTAssertNil(other.timingPresentation(hasBinding: true))
        XCTAssertNil(Self.input(.during, Self.kaprizovLive, timing: timing).timingPresentation(hasBinding: false))
    }

    @MainActor
    func testPageOwnedFlagsPassThroughUntouched() {
        var choices = false
        var timing = true
        let view = PlayerContributionPresentation10868(
            input: Self.input(.during, Self.kaprizovLive, selected: Self.key(60), chooser: Self.chooser),
            choicesExpanded: Binding(get: { choices }, set: { choices = $0 }),
            timingExpanded: Binding(get: { timing }, set: { timing = $0 })
        )

        XCTAssertEqual(view.choicesExpanded?.wrappedValue, false)
        XCTAssertEqual(view.timingExpanded?.wrappedValue, true)
        XCTAssertFalse(choices)
        XCTAssertTrue(timing)
        XCTAssertNil(view.onSelect)
        XCTAssertNil(view.onChoosePlayer)
        XCTAssertNil(view.onDetails)
    }

    // MARK: Geometry

    func testFractionAcceptsOnlyFiniteProbabilities() {
        XCTAssertEqual(PlayerContributionGeometry10868.fraction(0), 0)
        XCTAssertEqual(PlayerContributionGeometry10868.fraction(0.54), 0.54)
        XCTAssertEqual(PlayerContributionGeometry10868.fraction(1), 1)
        XCTAssertNil(PlayerContributionGeometry10868.fraction(-0.01))
        XCTAssertNil(PlayerContributionGeometry10868.fraction(1.01))
        XCTAssertNil(PlayerContributionGeometry10868.fraction(.nan))
        XCTAssertNil(PlayerContributionGeometry10868.fraction(.infinity))
    }

    func testZeroIsAVisibleMarkAndMissingIsNone() {
        XCTAssertEqual(PlayerContributionGeometry10868.markLength(0, extent: 150), PlayerContributionGeometry10868.minimumMark)
        XCTAssertEqual(PlayerContributionGeometry10868.markLength(0.33, extent: 150)!, 49.5, accuracy: 0.0001)
        XCTAssertEqual(PlayerContributionGeometry10868.markLength(1, extent: 150), 150)
        XCTAssertNil(PlayerContributionGeometry10868.markLength(nil, extent: 150))
        XCTAssertNil(PlayerContributionGeometry10868.markLength(1.2, extent: 150))
        XCTAssertNil(PlayerContributionGeometry10868.markLength(0.5, extent: 0))

        // A real 0% observation is a mark; a missing one is not.
        let zero = Self.milestone(66, "3+", "3+ points", before: Self.obs(0, "0%", "minute ending Oct 3, 4:59 PM PT · Kalshi"))
        let input = Self.input(.before, PlayerContributionPlayer10868(id: "4320548", name: "Quinn Hughes", team: nil,
                                                                      milestones: [zero], actual: Self.hughesFinalPoints))
        XCTAssertEqual(input.beforeFraction(zero), 0)
        XCTAssertEqual(input.beforeReading(zero), .value(Self.obs(0, "0%", "minute ending Oct 3, 4:59 PM PT · Kalshi")))
    }

    func testInvalidGeometryOmitsTheMarkButKeepsTheRowAndText() {
        let broken = Self.milestone(64, "1+", "1+ points", before: Self.obs(.nan, "69%", "minute ending Oct 3, 4:55 PM PT · Kalshi"),
                                    current: .recorded(Self.obs(1.4, "140%", "recorded Oct 3, 6:44 PM PT · Kalshi"), movement: nil))
        let player = PlayerContributionPlayer10868(id: "4320548", name: "Quinn Hughes", team: "Minnesota",
                                                   milestones: [broken, Self.milestone(65, "2+", "2+ points", before: Self.hughes2Pts)],
                                                   actual: Self.hughesFinalPoints)
        let input = Self.input(.during, player, selected: Self.key(64))

        XCTAssertNil(input.beforeFraction(broken))
        XCTAssertNil(input.currentFraction(broken))
        XCTAssertEqual(input.milestones.count, 2)
        XCTAssertEqual(input.beforeReading(broken).text, "69%")
        XCTAssertEqual(input.currentReading(broken)?.text, "140%")
        XCTAssertTrue(input.accessibilityValue(for: broken).contains("69%"))
    }

    func testPositionsShareOneScale() {
        XCTAssertEqual(PlayerContributionGeometry10868.x(0, width: 106, inset: 3), 3)
        XCTAssertEqual(PlayerContributionGeometry10868.x(1, width: 106, inset: 3), 103)
        XCTAssertEqual(PlayerContributionGeometry10868.x(0.5, width: 106, inset: 3), 53)
        XCTAssertNil(PlayerContributionGeometry10868.x(0.5, width: 6, inset: 3))
        XCTAssertEqual(PlayerContributionGeometry10868.y(1, height: 150), 0)
        XCTAssertEqual(PlayerContributionGeometry10868.y(0, height: 150), 150)
        XCTAssertEqual(PlayerContributionGeometry10868.y(0.5, height: 150), 75)
        XCTAssertNil(PlayerContributionGeometry10868.y(.nan, height: 150))
    }

    func testOnlyUnplaceableTicksAreDropped() {
        let ticks = [
            PlayerContributionTick10868(value: 1, text: "100%"),
            PlayerContributionTick10868(value: 1.5, text: "150%"),
            PlayerContributionTick10868(value: 0, text: "0%"),
            PlayerContributionTick10868(value: .nan, text: "?"),
            PlayerContributionTick10868(value: 0.5, text: "50%"),
        ]
        XCTAssertEqual(PlayerContributionGeometry10868.visibleTicks(ticks), [
            PlayerContributionPlacedTick10868(fraction: 1, text: "100%"),
            PlayerContributionPlacedTick10868(fraction: 0, text: "0%"),
            PlayerContributionPlacedTick10868(fraction: 0.5, text: "50%"),
        ])
    }

    func testCrowdedLabelsMoveToNewLanesWithoutLeavingTheirPositions() {
        let lanes = PlayerContributionGeometry10868.lanes(centers: [5, 50, 95], lengths: [60, 60, 60], extent: 100)
        XCTAssertEqual(lanes.map(\.origin), [0, 20, 40])
        XCTAssertEqual(lanes.map(\.lane), [0, 1, 2])

        let roomy = PlayerContributionGeometry10868.lanes(centers: [10, 90], lengths: [20, 20], extent: 100)
        XCTAssertEqual(roomy.map(\.origin), [0, 80])
        XCTAssertEqual(roomy.map(\.lane), [0, 0])
    }

    func testUnsortedTiedAndOversizeLabelsAreAllPlacedInOwnerOrder() {
        let lanes = PlayerContributionGeometry10868.lanes(centers: [95, 5, 5, 50], lengths: [20, 20, 20, 120], extent: 100)

        XCTAssertEqual(lanes.map(\.index), [0, 1, 2, 3])
        XCTAssertEqual(lanes[1].lane, 0)
        XCTAssertEqual(lanes[2].lane, 1, "A tie keeps the owner's order and drops a lane")
        XCTAssertEqual(lanes[0].origin, 80)
        XCTAssertEqual(lanes[0].lane, 0)
        XCTAssertTrue(lanes[3].oversize)
        XCTAssertEqual(lanes[3].origin, 0)
        XCTAssertEqual(lanes[3].lane, 2, "An oversize label has a lane of its own")
    }

    func testHorizontalAxisPlanReservesEveryRowAndWrapsAnOversizeLabel() {
        let plan = PlayerContributionGeometry10868.axisPlan(
            axis: .horizontal,
            centers: [5, 50, 95],
            natural: Array(repeating: CGSize(width: 60, height: 14), count: 3),
            atExtent: Array(repeating: CGSize(width: 60, height: 14), count: 3),
            extent: 100
        )
        XCTAssertEqual(plan.frames.map(\.origin), [CGPoint(x: 0, y: 0), CGPoint(x: 20, y: 16), CGPoint(x: 40, y: 32)])
        XCTAssertEqual(plan.size, CGSize(width: 100, height: 46))

        let wide = PlayerContributionGeometry10868.axisPlan(
            axis: .horizontal,
            centers: [50],
            natural: [CGSize(width: 140, height: 14)],
            atExtent: [CGSize(width: 96, height: 30)],
            extent: 100
        )
        XCTAssertEqual(wide.frames, [CGRect(x: 0, y: 0, width: 96, height: 30)])
        XCTAssertEqual(wide.size, CGSize(width: 100, height: 30))

        let tooWide = PlayerContributionGeometry10868.axisPlan(
            axis: .horizontal, centers: [50], natural: [CGSize(width: 140, height: 14)],
            atExtent: [CGSize(width: 120, height: 30)], extent: 100
        )
        XCTAssertEqual(tooWide.size.width, 120, "Overflow is reported, not hidden")
    }

    func testVerticalAxisPlanPutsCrowdedLabelsInColumnsBesideThePlot() {
        // Ticks at 0% and 5% on a 150pt plot sit 7.5pt apart: one column cannot hold both.
        let plan = PlayerContributionGeometry10868.axisPlan(
            axis: .vertical,
            centers: [150, 142.5, 0],
            natural: [CGSize(width: 18, height: 13), CGSize(width: 18, height: 13), CGSize(width: 30, height: 13)],
            atExtent: [CGSize(width: 18, height: 13), CGSize(width: 18, height: 13), CGSize(width: 30, height: 13)],
            extent: 150,
            laneGap: 6
        )
        // Sorted top to bottom: 100% (y 0) then 5% then 0%. 100% and 5% share column 0; 0% overlaps 5% and moves to column 1.
        XCTAssertEqual(plan.size, CGSize(width: 30 + 6 + 18, height: 150))
        XCTAssertEqual(plan.frames[2], CGRect(x: 54 - 30, y: 0, width: 30, height: 13), "First column sits beside the plot, trailing-aligned")
        XCTAssertEqual(plan.frames[1], CGRect(x: 54 - 18, y: 136, width: 18, height: 13))
        XCTAssertEqual(plan.frames[0], CGRect(x: 54 - 30 - 6 - 18, y: 137, width: 18, height: 13))
    }

    func testColumnsFallBackToBarsWithEveryMilestone() {
        XCTAssertEqual(PlayerContributionOrientation10868.columns.forms, [.columns, .bars])
        XCTAssertEqual(PlayerContributionOrientation10868.bars.forms, [.bars])

        // CONSTRUCTED: five milestones — more than the three the reference draws.
        let five = (1...5).map { n in
            Self.milestone(100 + n, "\(n)+", "\(n)+ points",
                           before: Self.obs(1.0 / Double(n + 1), "\(Int(100.0 / Double(n + 1)))%", "constructed"))
        }
        let player = PlayerContributionPlayer10868(id: "4320548", name: "Quinn Hughes", team: "Minnesota",
                                                   milestones: five, actual: Self.hughesFinalPoints)
        let input = Self.input(.before, player, selected: Self.key(105))

        XCTAssertEqual(input.milestones.map(\.id), five.map(\.id), "No cap to three, no reordering")
        XCTAssertEqual(input.selection.milestone?.id, Self.key(105))
        XCTAssertEqual(five.compactMap { input.beforeFraction($0) }.count, 5)
    }

    func testChartKeyOnlyWhenTheComparisonDoesNotCarryIt() {
        XCTAssertFalse(Self.input(.during, Self.kaprizovLive, selected: Self.key(60)).showsChartKey,
                       "The selected recorded comparison already shows the hollow/filled key")
        XCTAssertTrue(Self.input(.during, Self.kaprizovLive, selected: Self.key(59)).showsChartKey)
        XCTAssertTrue(Self.input(.during, Self.kaprizovLive, selected: nil).showsChartKey)
        XCTAssertFalse(Self.input(.during, Self.hughesPoints(), selected: nil).showsChartKey, "No filled marks, no key")
    }

    // MARK: Spoken text and ids

    func testSpokenHeaderPlayerAndChartValues() {
        let input = Self.input(.during, Self.kaprizovLive, selected: Self.key(60))
        let milestones = Self.kaprizovLive.milestones

        XCTAssertEqual(input.accessibilityHeader, "PLAYER POINTS. Points in context")
        XCTAssertEqual(input.accessibilityPlayer, "Kirill Kaprizov, Minnesota")
        XCTAssertEqual(input.accessibilityValue(for: milestones[1]),
                       "Pregame chance: 39%, minute ending Oct 3, 12:51 PM PT · Kalshi; Recorded in-game chance: 54%, recorded Oct 3, 6:44 PM PT · Kalshi")
        XCTAssertEqual(input.accessibilityComparison(for: milestones[1]),
                       "Pregame chance: 39%, minute ending Oct 3, 12:51 PM PT · Kalshi; Recorded in-game chance: 54%, recorded Oct 3, 6:44 PM PT · Kalshi; Change since pregame: +15 percentage points since pregame")
        XCTAssertEqual(input.accessibilityActual(input.actualPresentation!),
                       "1 point so far, 1 goal + 0 assists, as of 6:45 PM PT, 2nd period, 4:09 left · ESPN")
        XCTAssertEqual(input.accessibilityProgressLabel(for: milestones[1]), "Progress toward 2+ points")
    }

    func testOwnerStringsAreShownVerbatim() {
        // CONSTRUCTED long and qualified owner strings.
        let tiny = Self.milestone(64, "1+", "1+ points", before: Self.obs(0.004, "<1%", "minute ending Oct 3, 4:55 PM PT · Kalshi"))
        let precise = PlayerContributionMilestone10868(
            id: Self.key(65), target: "2+ or more points scored in regulation and overtime",
            title: "2+ points (regulation and overtime)", before: Self.obs(0.125, "12.5%", "minute ending Oct 3, 4:51 PM PT · Kalshi"),
            beforeMissing: "Unavailable before puck drop", current: .withheld("No recent probability update"),
            progress: nil, result: Self.pending
        )
        let player = PlayerContributionPlayer10868(id: "x", name: "Maximilian Alexander Shabanov-Kuznetsov",
                                                   team: "Team unavailable", milestones: [tiny, precise],
                                                   actual: .unavailable("Count unavailable"))
        let input = Self.input(.during, player, selected: Self.key(65))

        XCTAssertEqual(input.beforeReading(tiny).text, "<1%")
        XCTAssertEqual(input.beforeReading(precise).text, "12.5%")
        XCTAssertEqual(input.currentReading(precise)?.text, "No recent probability update")
        XCTAssertEqual(input.accessibilityPlayer, "Maximilian Alexander Shabanov-Kuznetsov, Team unavailable")
        XCTAssertEqual(input.selection.milestone?.target, "2+ or more points scored in regulation and overtime")
    }

    func testAccessibilityIdentifiersCarryExactIDs() {
        XCTAssertEqual(PlayerContributionAccessibilityID10868.milestone(Self.key(60)),
                       "playerContribution10868.milestone.nhl-15169793-game-markets.json:player_props:60")
        XCTAssertEqual(PlayerContributionAccessibilityID10868.comparison(Self.key(60)),
                       "playerContribution10868.comparison.nhl-15169793-game-markets.json:player_props:60")
        XCTAssertEqual(PlayerContributionAccessibilityID10868.details(Self.key(41)),
                       "playerContribution10868.details.nhl-15169793-game-markets.json:player_props:41")
        XCTAssertEqual(PlayerContributionAccessibilityID10868.actual("3942335"), "playerContribution10868.actual.3942335")
        XCTAssertEqual(PlayerContributionAccessibilityID10868.choice("shabanov-49"), "playerContribution10868.choice.shabanov-49")
    }
}

/// #10868 player-duel — two players' made and missed threes beside each
/// player's own head-to-head contract, as one stateless presentation leaf.
///
/// The view is SwiftUI and is not rasterised here. What is asserted is the
/// rules it defers to: which readings each phase shows, how a chance is drawn
/// or kept in words, the shot marks and their rows, the exact-id selection and
/// actions, the layout forms it tries, and the spoken text. Nothing here claims
/// a rendered fit or rendered accessibility.
///
/// ARCHIVED values come from Knicks–Spurs, Game 1, Jun 3 2026, as retained in
/// `shipping-adoption-20261027/PLAYER-DUEL-RETAINED-CASES.json` (sha256
/// af58febc…2248), from the existing `playerDuelEvidence.ts` helpers:
///   KXNBAH2H3PT-26JUN03JCHAMPAGNIE30OANUNOBY8-JCHAMPAGNIE30
///     Julian Champagnie (ESPN 4592479, team 24) · final 5 made / 10 attempts
///     · contract result yes · duelPregameWinChance null (tie_splits_payout)
///     · contract value 0.57 at minute ending 2026-06-04T00:29Z (NOT a chance)
///   KXNBAH2H3PT-26JUN03JCHAMPAGNIE30OANUNOBY8-OANUNOBY8
///     OG Anunoby (ESPN 3934719, team 18) · final 3 made / 6 attempts
///     · contract result no · duelPregameWinChance null (tie_splits_payout)
///     · contract value 0.47 at minute ending 2026-06-03T23:23Z (NOT a chance)
/// Original titles are the retained `original.title` strings. Only before and
/// final phases were retained; before carries no actual counts.
///
/// CONSTRUCTED owner-resolved inputs (this leaf does not resolve them): every
/// display and spoken string (figures, units, attempts words, "50% from
/// three", "Unavailable", "Won"/"Lost", team words, title, context, rule,
/// clock/source lines); and every during-play, admitted-chance, zero, invalid,
/// unconfirmed, contradictory, duplicate, foreign, incomplete-pair and
/// long-text case. None is an actual live capture.
final class PlayerDuelPresentation10868Tests: XCTestCase {

    // MARK: Fixtures

    private static let champagnieOriginal = "KXNBAH2H3PT-26JUN03JCHAMPAGNIE30OANUNOBY8-JCHAMPAGNIE30"
    private static let anunobyOriginal = "KXNBAH2H3PT-26JUN03JCHAMPAGNIE30OANUNOBY8-OANUNOBY8"
    /// A different original on the same game — never a substitute.
    private static let knicksOriginal = "KXNBAGAME-26JUN03NYKSAS-NYK"

    private static let unavailable = PlayerContributionReading10868.missing("Unavailable")
    private static let noInGame = PlayerContributionReading10868.missing("No in-game reading")
    private static let pending = PlayerContributionResult10868.unconfirmed("Result unconfirmed")
    private static let won = PlayerContributionResult10868.reached("Won")
    private static let lost = PlayerContributionResult10868.missed("Lost")

    private static func obs(_ probability: Double, _ text: String, _ detail: String) -> PlayerContributionObservation10868 {
        PlayerContributionObservation10868(probability: probability, text: text, accessibilityDetail: detail)
    }

    private static func shots(_ made: Int, _ attempts: Int, figure: String? = nil, unit: String? = "made",
                              accuracy: String? = nil, detail: String = "final box score · ESPN") -> PlayerDuelShots10868 {
        PlayerDuelShots10868(made: made, attempts: attempts, figure: figure ?? "\(made)", unit: unit,
                             attemptsText: "\(attempts) attempts", accuracy: accuracy,
                             spoken: "\(made) made in \(attempts) attempts", accessibilityDetail: detail)
    }

    /// ARCHIVED counts, CONSTRUCTED words.
    private static let champagnieFinal = PlayerDuelActual10868.shots(shots(5, 10, accuracy: "50% from three"))
    private static let anunobyFinal = PlayerDuelActual10868.shots(shots(3, 6, accuracy: "50% from three"))
    private static let countUnavailable = PlayerDuelActual10868.unavailable("Count unavailable")

    private static func champagnie(
        id: String = "4592479",
        originalID: String = champagnieOriginal,
        pregame: PlayerContributionReading10868 = unavailable,
        current: PlayerContributionReading10868 = noInGame,
        actual: PlayerDuelActual10868 = champagnieFinal,
        result: PlayerContributionResult10868 = won
    ) -> PlayerDuelSide10868 {
        PlayerDuelSide10868(
            id: id,
            originalID: originalID,
            originalTitle: "Will Julian Champagnie record more made three pointers than OG Anunoby?",
            name: "Julian Champagnie",
            team: "Spurs",
            pregame: pregame,
            current: current,
            actual: actual,
            result: result
        )
    }

    private static func anunoby(
        id: String = "3934719",
        originalID: String = anunobyOriginal,
        pregame: PlayerContributionReading10868 = unavailable,
        current: PlayerContributionReading10868 = noInGame,
        actual: PlayerDuelActual10868 = anunobyFinal,
        result: PlayerContributionResult10868 = lost
    ) -> PlayerDuelSide10868 {
        PlayerDuelSide10868(
            id: id,
            originalID: originalID,
            originalTitle: "Will OG Anunoby record more made three pointers than Julian Champagnie?",
            name: "OG Anunoby",
            team: "Knicks",
            pregame: pregame,
            current: current,
            actual: actual,
            result: result
        )
    }

    private static func input(
        _ phase: PlayerContributionPhase10868,
        _ sides: [PlayerDuelSide10868]? = nil,
        selected: String? = nil
    ) -> PlayerDuelInput10868 {
        PlayerDuelInput10868(
            phase: phase,
            eyebrow: "PLAYER HEAD-TO-HEAD · MADE THREES",
            title: phase == .final ? "Same accuracy.\nTwo more threes." : "Who makes more threes?",
            context: phase == .final ? "Knicks 105–95 Spurs · Final" : "Knicks vs Spurs · Before game",
            payoutRule: "A tie splits the payout. A separate win chance isn’t supplied.",
            sides: sides ?? [champagnie(), anunoby()],
            selectedOriginalID: selected
        )
    }

    private static func filled(_ made: Int, outlined missed: Int) -> [Bool] {
        Array(repeating: true, count: made) + Array(repeating: false, count: missed)
    }

    // MARK: Retained final

    func testRetainedFinalKeepsEachPlayersOwnOriginalCountAndExplicitAbsence() {
        let input = Self.input(.final, selected: Self.champagnieOriginal)
        let (champagnie, anunoby) = (input.sides[0], input.sides[1])

        XCTAssertTrue(input.isPairResolved)
        XCTAssertNil(input.pairNotice)
        XCTAssertEqual(input.sides.map(\.originalID), [Self.champagnieOriginal, Self.anunobyOriginal], "Owner order, own originals")
        XCTAssertEqual(input.pregame(champagnie), .words("Unavailable"))
        XCTAssertEqual(input.pregame(anunoby), .words("Unavailable"))
        XCTAssertNil(input.current(champagnie), "No in-game slot after the final")
        XCTAssertEqual(input.actualPresentation(champagnie),
                       PlayerDuelActualPresentation10868(title: "Final count",
                                                         content: .counted(Self.shots(5, 10, accuracy: "50% from three"),
                                                                           marks: Self.filled(5, outlined: 5))))
        XCTAssertEqual(input.actualPresentation(anunoby)?.title, "Final count")
        XCTAssertEqual(input.result(champagnie), Self.won)
        XCTAssertEqual(input.result(anunoby), Self.lost)
        XCTAssertTrue(input.showsShotKey)
    }

    func testRetainedCountsReconcileWithTheirMarks() {
        let champagnie = PlayerDuelGeometry10868.marks(made: 5, attempts: 10)!
        let anunoby = PlayerDuelGeometry10868.marks(made: 3, attempts: 6)!

        XCTAssertEqual(champagnie.filter { $0 }.count, 5)
        XCTAssertEqual(champagnie.filter { !$0 }.count, 5)
        XCTAssertEqual(anunoby.filter { $0 }.count, 3)
        XCTAssertEqual(anunoby.filter { !$0 }.count, 3)
        XCTAssertEqual(PlayerDuelGeometry10868.rows(champagnie), [Self.filled(5, outlined: 0), Self.filled(0, outlined: 5)],
                       "Made first, then missed — grouped counts")
        XCTAssertEqual(PlayerDuelGeometry10868.rows(anunoby), [Self.filled(3, outlined: 2), Self.filled(0, outlined: 1)])
    }

    func testHalfPayoutValuesNeverBecomeAWinChance() {
        let input = Self.input(.final, selected: Self.champagnieOriginal)
        for side in input.sides {
            guard case .words(let words) = input.pregame(side) else {
                return XCTFail("A tie-splitting contract value has no win-chance figure")
            }
            XCTAssertEqual(words, "Unavailable")
            let spoken = input.accessibilityValue(for: side)
            for leaked in ["57", "47", "¢"] {
                XCTAssertFalse(spoken.contains(leaked), "No contract value in cents or as a percent: \(leaked)")
            }
            XCTAssertTrue(spoken.contains("Pregame win chance: Unavailable"))
            // Equal shooting accuracy is performance, kept with the count, never a 50% chance.
            XCTAssertNotEqual(input.pregame(side), .words("50% from three"))
            XCTAssertTrue(spoken.hasPrefix("Final count: "))
            XCTAssertTrue(spoken.contains("50% from three"))
            XCTAssertFalse(spoken.contains("Pregame win chance: 50%"))
        }
    }

    // MARK: Before play

    func testBeforeShowsOnlyEarlierChanceEvenWhenLaterInputsArePresent() {
        // The retained raw originals already carry results; a host passing them early must not leak them.
        let sides = [
            Self.champagnie(current: .value(Self.obs(0.61, "61%", "recorded · constructed"))),
            Self.anunoby(),
        ]
        let input = Self.input(.before, sides, selected: Self.anunobyOriginal)

        for side in sides {
            XCTAssertNil(input.actualPresentation(side), "No count before play, not even a zero")
            XCTAssertNil(input.marks(side))
            XCTAssertNil(input.current(side))
            XCTAssertNil(input.result(side), "No original result before the final")
            XCTAssertEqual(input.accessibilityValue(for: side), "Pregame win chance: Unavailable")
        }
        XCTAssertFalse(input.showsShotKey)
        XCTAssertEqual(input.selection.side?.originalID, Self.anunobyOriginal)
    }

    func testBeforeKeepsAnAdmittedPregameChanceAsAFigure() {
        // CONSTRUCTED: an owner-admitted outright chance, which the retained capture does not supply.
        let chance = Self.obs(0.52, "52%", "minute ending Jun 3, 5:29 PM PT · constructed")
        let input = Self.input(.before, [Self.champagnie(pregame: .value(chance)), Self.anunoby()])

        XCTAssertEqual(input.pregame(input.sides[0]), .figure(chance))
        XCTAssertEqual(input.pregame(input.sides[1]), .words("Unavailable"), "Each player keeps only its own reading")
        XCTAssertEqual(input.accessibilityValue(for: input.sides[0]),
                       "Pregame win chance: 52%, minute ending Jun 3, 5:29 PM PT · constructed")
    }

    // MARK: Final results

    func testFinalResultIsIndependentOfTheCountsAndOfTheOtherPlayer() {
        // CONSTRUCTED: Anunoby's result unconfirmed though his count is lower.
        let unknown = Self.input(.final, [Self.champagnie(), Self.anunoby(result: Self.pending)])
        XCTAssertEqual(unknown.result(unknown.sides[1]), Self.pending)
        XCTAssertFalse(unknown.result(unknown.sides[1])!.isAdmitted)
        XCTAssertTrue(unknown.accessibilityValue(for: unknown.sides[1]).hasSuffix("Final result: Result unconfirmed"))

        // CONSTRUCTED: contradictory admitted results are each shown as admitted, never reconciled.
        let both = Self.input(.final, [Self.champagnie(), Self.anunoby(result: Self.won)])
        XCTAssertEqual(both.result(both.sides[0]), Self.won)
        XCTAssertEqual(both.result(both.sides[1]), Self.won)
        XCTAssertNil(both.pairNotice)
        XCTAssertNil(both.selectionNotice)

        // CONSTRUCTED: a known result with an unknown count stays explicit.
        let noCount = Self.input(.final, [Self.champagnie(actual: Self.countUnavailable), Self.anunoby()])
        XCTAssertEqual(noCount.actualPresentation(noCount.sides[0])?.content, .words("Count unavailable"))
        XCTAssertEqual(noCount.result(noCount.sides[0]), Self.won)
    }

    // MARK: During play (all CONSTRUCTED)

    func testDuringShowsOwnCurrentChanceAndCountSoFarNeverAResult() {
        let live = Self.obs(0.61, "61%", "recorded Jun 3, 6:12 PM PT · constructed")
        let soFar = PlayerDuelShots10868(made: 2, attempts: 4, figure: "2", unit: "made so far",
                                         attemptsText: "4 attempts so far", accuracy: nil,
                                         spoken: "2 made in 4 attempts so far",
                                         accessibilityDetail: "as of 6:14 PM PT, 2nd quarter, 3:10 left · ESPN")
        let input = Self.input(.during, [Self.champagnie(current: .value(live), actual: .shots(soFar)), Self.anunoby()])
        let champagnie = input.sides[0]

        XCTAssertEqual(input.current(champagnie), .figure(live))
        XCTAssertEqual(input.pregame(champagnie), .words("Unavailable"), "The pregame absence stays beside the live chance")
        XCTAssertEqual(input.actualPresentation(champagnie),
                       PlayerDuelActualPresentation10868(title: "Count so far", content: .counted(soFar, marks: Self.filled(2, outlined: 2))))
        XCTAssertNil(input.result(champagnie), "A supplied result is not shown during play")
        XCTAssertEqual(input.accessibilityValue(for: champagnie),
                       "Count so far: 2 made in 4 attempts so far, as of 6:14 PM PT, 2nd quarter, 3:10 left · ESPN; Grouped counts, not shot order; Pregame win chance: Unavailable; In-game win chance: 61%, recorded Jun 3, 6:12 PM PT · constructed")
    }

    func testDuringCurrentWordsAndMissingCountStayWordsNeverZero() {
        let input = Self.input(.during, [Self.champagnie(actual: Self.countUnavailable), Self.anunoby(actual: Self.countUnavailable)])

        for side in input.sides {
            XCTAssertEqual(input.current(side), .words("No in-game reading"))
            XCTAssertEqual(input.actualPresentation(side)?.content, .words("Count unavailable"))
            XCTAssertNil(input.marks(side), "A missing count draws no marks")
        }
        XCTAssertFalse(input.showsShotKey)
    }

    // MARK: Chances

    func testProbabilityDisplayIsAFigureOnlyForAPlaceableValue() {
        let zero = Self.obs(0, "0%", "constructed")
        XCTAssertEqual(PlayerDuelInput10868.display(.value(zero)), .figure(zero), "0% is a real observation")
        XCTAssertEqual(PlayerDuelInput10868.display(.value(Self.obs(1, "100%", "constructed"))), .figure(Self.obs(1, "100%", "constructed")))
        for bad in [Double.nan, .infinity, -0.01, 1.2] {
            XCTAssertEqual(PlayerDuelInput10868.display(.value(Self.obs(bad, "57%", "constructed"))), .words("57%"),
                           "An unplaceable value keeps the owner's words at reading size")
        }
        XCTAssertEqual(PlayerDuelInput10868.display(Self.unavailable), .words("Unavailable"))
    }

    // MARK: Shot marks

    func testZeroMadeDrawsMissedRingsAndZeroAttemptsDrawsNothing() {
        XCTAssertEqual(PlayerDuelGeometry10868.marks(made: 0, attempts: 4), Self.filled(0, outlined: 4))
        XCTAssertEqual(PlayerDuelGeometry10868.marks(made: 0, attempts: 0), [])
        XCTAssertEqual(PlayerDuelGeometry10868.marks(made: 4, attempts: 4), Self.filled(4, outlined: 0))
        XCTAssertEqual(PlayerDuelGeometry10868.rows([]), [])

        let input = Self.input(.final, [Self.champagnie(actual: .shots(Self.shots(0, 4))), Self.anunoby(actual: .shots(Self.shots(0, 0)))])
        XCTAssertEqual(input.marks(input.sides[0]), Self.filled(0, outlined: 4))
        XCTAssertNil(input.marks(input.sides[1]), "0 attempts: the figure stays, no marks")
        XCTAssertEqual(input.actualPresentation(input.sides[1])?.content, .counted(Self.shots(0, 0), marks: []))
        XCTAssertTrue(input.showsShotKey)
        XCTAssertFalse(input.accessibilityValue(for: input.sides[1]).contains("Grouped counts"))
    }

    func testInvalidCountsDrawNoMarksAndKeepTheOwnersWords() {
        XCTAssertNil(PlayerDuelGeometry10868.marks(made: 5, attempts: 3))
        XCTAssertNil(PlayerDuelGeometry10868.marks(made: -1, attempts: 3))
        XCTAssertNil(PlayerDuelGeometry10868.marks(made: 0, attempts: -1))

        let input = Self.input(.final, [Self.champagnie(actual: .shots(Self.shots(5, 3))), Self.anunoby(actual: .shots(Self.shots(-1, 6)))])
        XCTAssertEqual(input.actualPresentation(input.sides[0])?.content, .words("5 made in 3 attempts"))
        XCTAssertEqual(input.actualPresentation(input.sides[1])?.content, .words("-1 made in 6 attempts"))
        XCTAssertNil(input.marks(input.sides[0]))
        XCTAssertFalse(input.showsShotKey)
        XCTAssertEqual(input.result(input.sides[0]), Self.won, "The result is untouched by a broken count")
    }

    func testMarksAreNeverCappedAndRowsKeepOrder() {
        let seventeen = PlayerDuelGeometry10868.marks(made: 7, attempts: 17)!
        let rows = PlayerDuelGeometry10868.rows(seventeen)

        XCTAssertEqual(seventeen.count, 17)
        XCTAssertEqual(rows.map(\.count), [5, 5, 5, 2])
        XCTAssertEqual(rows.flatMap { $0 }, seventeen)
        XCTAssertEqual(PlayerDuelGeometry10868.rows(Self.filled(5, outlined: 0)), [Self.filled(5, outlined: 0)], "Exactly one full row")
        XCTAssertEqual(PlayerDuelGeometry10868.rows(Self.filled(1, outlined: 5)).map(\.count), [5, 1])
        XCTAssertEqual(PlayerDuelGeometry10868.rows(Self.filled(2, outlined: 1), perRow: 0), [Self.filled(2, outlined: 1)])
    }

    // MARK: Selection and identity

    func testExactSelectionMarksOnePlayer() {
        let input = Self.input(.final, selected: Self.anunobyOriginal)

        XCTAssertEqual(input.selection, .selected(input.sides[1]))
        XCTAssertFalse(input.isSelected(input.sides[0]))
        XCTAssertTrue(input.isSelected(input.sides[1]))
        XCTAssertNil(input.selectionNotice)

        let none = Self.input(.final)
        XCTAssertEqual(none.selection, .none)
        XCTAssertNil(none.selectionNotice)
        XCTAssertFalse(none.sides.contains { none.isSelected($0) })
    }

    func testMissingWithdrawnAndForeignSelectionSelectsNobody() {
        let foreign = Self.input(.final, selected: Self.knicksOriginal)
        XCTAssertEqual(foreign.selection, .missing(Self.knicksOriginal))
        XCTAssertEqual(foreign.selectionNotice, "Selected head-to-head unavailable.")
        XCTAssertFalse(foreign.sides.contains { foreign.isSelected($0) })

        // CONSTRUCTED: Anunoby withdrawn by the owner; his selection is not moved to Champagnie.
        let withdrawn = Self.input(.final, [Self.champagnie()], selected: Self.anunobyOriginal)
        XCTAssertEqual(withdrawn.selection, .missing(Self.anunobyOriginal))
        XCTAssertFalse(withdrawn.isSelected(withdrawn.sides[0]))
        XCTAssertNil(withdrawn.detailsAction(canOpenDetails: true))

        // A player id is not an original id.
        XCTAssertEqual(Self.input(.final, selected: "4592479").selection, .missing("4592479"))
    }

    func testSharedIdentitiesAreUnresolvedAndNeverSubstitute() {
        // CONSTRUCTED: both panels carry Champagnie's original.
        let sharedOriginal = Self.input(.final, [Self.champagnie(), Self.anunoby(originalID: Self.champagnieOriginal)],
                                        selected: Self.champagnieOriginal)
        XCTAssertEqual(sharedOriginal.selection, .duplicate(Self.champagnieOriginal))
        XCTAssertFalse(sharedOriginal.isPairResolved)
        XCTAssertEqual(sharedOriginal.pairNotice, "Head-to-head pair incomplete.")
        XCTAssertEqual(sharedOriginal.sides.count, 2, "Both panels stay")
        XCTAssertTrue(sharedOriginal.sides.allSatisfy { sharedOriginal.sideAction($0, canSelect: true) == nil })

        // CONSTRUCTED: one player identity on two originals.
        let sharedPlayer = Self.input(.final, [Self.champagnie(), Self.anunoby(id: "4592479")], selected: Self.anunobyOriginal)
        XCTAssertEqual(sharedPlayer.selection, .duplicate(Self.anunobyOriginal))
        XCTAssertFalse(sharedPlayer.sides.contains { sharedPlayer.isSelected($0) })
        XCTAssertTrue(sharedPlayer.sides.allSatisfy { sharedPlayer.sideAction($0, canSelect: true) == nil })
        XCTAssertNil(sharedPlayer.detailsAction(canOpenDetails: true))
    }

    func testIncompletePairKeepsEveryGivenPlayer() {
        let one = Self.input(.final, [Self.anunoby()])
        XCTAssertEqual(one.pairNotice, "Head-to-head pair incomplete.")
        XCTAssertEqual(one.sides.map(\.originalID), [Self.anunobyOriginal], "No neighbouring player fills the gap")

        // CONSTRUCTED third player with its own identity and original.
        let third = Self.champagnie(id: "third", originalID: "third-original")
        let three = Self.input(.final, [Self.champagnie(), Self.anunoby(), third], selected: "third-original")
        XCTAssertEqual(three.pairNotice, "Head-to-head pair incomplete.")
        XCTAssertEqual(three.sides.count, 3, "Never pruned to two")
        XCTAssertEqual(three.selection.side?.originalID, "third-original")

        let empty = Self.input(.final, [])
        XCTAssertEqual(empty.pairNotice, "Head-to-head pair incomplete.")
        XCTAssertFalse(empty.showsShotKey)
    }

    // MARK: Callbacks

    func testActionsCarryExactOriginalIDs() {
        let input = Self.input(.final, selected: Self.anunobyOriginal)
        var selected: [String] = []
        var details: [String] = []

        for side in input.sides {
            input.sideAction(side, canSelect: true)?
                .perform(onSelect: { selected.append($0) }, onChoosePlayer: nil, onDetails: { details.append($0) })
        }
        input.detailsAction(canOpenDetails: true)?
            .perform(onSelect: { selected.append($0) }, onChoosePlayer: nil, onDetails: { details.append($0) })

        XCTAssertEqual(selected, [Self.champagnieOriginal, Self.anunobyOriginal])
        XCTAssertEqual(details, [Self.anunobyOriginal])
    }

    @MainActor
    func testNoCallbackMeansNoActionAndTheCardIsStatic() {
        let input = Self.input(.final, selected: Self.champagnieOriginal)
        let view = PlayerDuelPresentation10868(input: input)

        XCTAssertNil(view.onSelect)
        XCTAssertNil(view.onDetails)
        XCTAssertNil(view.portrait, "No portrait unless the caller supplies one")
        XCTAssertTrue(input.sides.allSatisfy { input.sideAction($0, canSelect: false) == nil })
        XCTAssertNil(input.detailsAction(canOpenDetails: false))
        XCTAssertNil(Self.input(.final).detailsAction(canOpenDetails: true), "No selection, no Details")
    }

    // MARK: Layout

    func testLayoutTriesTwoPanelsThenStacksAndAccessibilitySizesStack() {
        let input = Self.input(.final)
        XCTAssertEqual(input.layouts(isAccessibilitySize: false), [.paired, .stacked])
        XCTAssertEqual(input.layouts(isAccessibilitySize: true), [.stacked])
    }

    // MARK: Spoken text and ids

    func testSpokenHeaderPanelsAndShotKey() {
        let input = Self.input(.final, selected: Self.champagnieOriginal)

        XCTAssertEqual(input.accessibilityHeader, "PLAYER HEAD-TO-HEAD · MADE THREES. Same accuracy.\nTwo more threes.")
        XCTAssertEqual(input.accessibilityLabel(for: input.sides[0]), "Julian Champagnie, Spurs")
        XCTAssertEqual(input.accessibilityLabel(for: input.sides[1]), "OG Anunoby, Knicks")
        XCTAssertEqual(input.accessibilityValue(for: input.sides[0]),
                       "Final count: 5 made in 10 attempts, 50% from three, final box score · ESPN; Grouped counts, not shot order; Pregame win chance: Unavailable; Final result: Won")
        XCTAssertEqual(input.accessibilityValue(for: input.sides[1]),
                       "Final count: 3 made in 6 attempts, 50% from three, final box score · ESPN; Grouped counts, not shot order; Pregame win chance: Unavailable; Final result: Lost")
        XCTAssertEqual(input.accessibilityShotKey, "Filled: made · outlined: missed. Grouped counts, not shot order")
    }

    func testOwnerStringsAreShownVerbatim() {
        // CONSTRUCTED long and qualified owner strings.
        let long = PlayerDuelSide10868(
            id: "x", originalID: "x-original",
            originalTitle: "Will Maximilian Alexander Shabanov-Kuznetsov record more made three pointers in regulation and overtime?",
            name: "Maximilian Alexander Shabanov-Kuznetsov", team: nil,
            pregame: .missing("Unavailable: a tie splits the payout"),
            current: .missing("No recent probability update"),
            actual: .shots(Self.shots(12, 23, figure: "12", unit: nil, accuracy: "52.2% from three")),
            result: .unconfirmed("Result unconfirmed")
        )
        let input = Self.input(.during, [long, Self.anunoby()], selected: "x-original")

        XCTAssertEqual(input.pregame(long), .words("Unavailable: a tie splits the payout"))
        XCTAssertEqual(input.current(long), .words("No recent probability update"))
        XCTAssertEqual(input.accessibilityLabel(for: long), "Maximilian Alexander Shabanov-Kuznetsov")
        XCTAssertEqual(input.selection.side?.originalTitle, long.originalTitle)
        XCTAssertEqual(input.marks(long)?.count, 23, "Every attempt drawn")
    }

    func testAccessibilityIdentifiersCarryExactIDs() {
        XCTAssertEqual(PlayerDuelAccessibilityID10868.side(Self.champagnieOriginal),
                       "playerDuel10868.side.KXNBAH2H3PT-26JUN03JCHAMPAGNIE30OANUNOBY8-JCHAMPAGNIE30")
        XCTAssertEqual(PlayerDuelAccessibilityID10868.details(Self.anunobyOriginal),
                       "playerDuel10868.details.KXNBAH2H3PT-26JUN03JCHAMPAGNIE30OANUNOBY8-OANUNOBY8")
        XCTAssertEqual(PlayerDuelAccessibilityID10868.shotKey, "playerDuel10868.shotKey")
    }
}

/// #10868 player-duel "Market value history" — each player's own contract
/// value, earlier and later, in cents per $1 contract, as one stateless
/// presentation leaf over one owner-admitted frame.
///
/// The view is SwiftUI and is not rasterised here. What is asserted is the
/// rules it defers to: which reading each endpoint draws or keeps in words,
/// the exact original and observation ties, the connector, the inset track
/// geometry, the exact-id selection and actions, the layout forms it tries,
/// and the spoken text. Nothing here claims a rendered fit or rendered
/// accessibility.
///
/// ARCHIVED values come from Knicks–Spurs, Game 1, Jun 3 2026, as retained in
/// `shipping-adoption-20261027/PLAYER-DUEL-VALUE-RETAINED-CASES.json` (sha256
/// c0dce536…85d6f2), produced by the existing `playerDuelMovement` /
/// `duelPriceChange` / `duelCents` reference helpers, and copied from
/// `PLAYER-DUEL-VALUE-RETAINED-FIXTURES.swift` (sha256 eb763143…62c0e6).
/// Times are minute-ending traded-minute closes, shown in
/// America/Los_Angeles, never a precise trade time or the actual tipoff:
///   before (first captured → last before the listed start)
///     JCHAMPAGNIE30  0.62 @ 1780496520 (Jun 3, 7:22 AM) → 0.57 @ 1780532940 (5:29 PM)  −5¢
///     OANUNOBY8      0.52 @ 1780506360 (Jun 3, 10:06 AM) → 0.47 @ 1780528980 (4:23 PM) −5¢
///   final (pre-start baseline → last later captured trade)
///     JCHAMPAGNIE30  0.57 @ 1780532940 (5:29 PM) → 0.99 @ 1780537500 (6:45 PM)  +42¢
///     OANUNOBY8      0.47 @ 1780528980 (4:23 PM) → 0.02 @ 1780535280 (6:08 PM)  −45¢
/// 99¢ and 2¢ are trades, not a settled 100%/0% and not a grade. Only the
/// before and final frames were retained.
///
/// CONSTRUCTED owner-resolved inputs (this leaf does not resolve them): every
/// label, time, source, figure, change and rule string as owner copy; the
/// observation ids (original id + "@" + minute-ending seconds); and every
/// live, missing, foreign, duplicate, invalid, zero, one, unchanged,
/// third-row and long-text case. None is an actual live capture.
final class PlayerDuelValuePresentation10868Tests: XCTestCase {

    // MARK: Fixtures

    private static let champagnieOriginal = "KXNBAH2H3PT-26JUN03JCHAMPAGNIE30OANUNOBY8-JCHAMPAGNIE30"
    private static let anunobyOriginal = "KXNBAH2H3PT-26JUN03JCHAMPAGNIE30OANUNOBY8-OANUNOBY8"
    /// A different original on the same game — never a substitute.
    private static let knicksOriginal = "KXNBAGAME-26JUN03NYKSAS-NYK"
    private static let source = "Kalshi · traded minute close"
    private static let quantity = "Value per $1 contract"
    private static let tieRule = "A tie pays 50¢. This is not a win probability."
    private static let finalNote = "Last trade isn’t the final result. No values are filled in between these readings."

    private static func value(_ original: String, _ fraction: Double, _ figure: String, _ minuteEnding: Int,
                              _ time: String, id: String? = nil) -> PlayerDuelValueObservation10868 {
        PlayerDuelValueObservation10868(originalID: original, observationID: id ?? "\(original)@\(minuteEnding)",
                                        fractionOfDollar: fraction, figure: figure, time: time, sourceWords: source)
    }

    private static func endpoint(_ label: String, _ observation: PlayerDuelValueObservation10868?,
                                 missing: String = "No captured trade") -> PlayerDuelValueEndpoint10868 {
        PlayerDuelValueEndpoint10868(label: label, reading: observation.map { .value($0) } ?? .missing(missing))
    }

    // ARCHIVED endpoints.
    private static let cBeforeFirst = value(champagnieOriginal, 0.62, "62¢", 1780496520, "Jun 3, 7:22 AM")
    private static let cPregame = value(champagnieOriginal, 0.57, "57¢", 1780532940, "Jun 3, 5:29 PM")
    private static let cLastTrade = value(champagnieOriginal, 0.99, "99¢", 1780537500, "Jun 3, 6:45 PM")
    private static let aBeforeFirst = value(anunobyOriginal, 0.52, "52¢", 1780506360, "Jun 3, 10:06 AM")
    private static let aPregame = value(anunobyOriginal, 0.47, "47¢", 1780528980, "Jun 3, 4:23 PM")
    private static let aLastTrade = value(anunobyOriginal, 0.02, "2¢", 1780535280, "Jun 3, 6:08 PM")

    private static func row(playerID: String, original: String, title: String, name: String,
                            earlier: PlayerDuelValueEndpoint10868, later: PlayerDuelValueEndpoint10868,
                            change: String) -> PlayerDuelValueRow10868 {
        PlayerDuelValueRow10868(playerID: playerID, originalID: original, originalTitle: title, name: name,
                                earlier: earlier, later: later, change: change)
    }

    private static let champagnieTitle = "Will Julian Champagnie record more made three pointers than OG Anunoby?"
    private static let anunobyTitle = "Will OG Anunoby record more made three pointers than Julian Champagnie?"

    private static func champagnie(earlier: PlayerDuelValueEndpoint10868, later: PlayerDuelValueEndpoint10868, change: String,
                                   playerID: String = "4592479", original: String = champagnieOriginal) -> PlayerDuelValueRow10868 {
        row(playerID: playerID, original: original, title: champagnieTitle, name: "Julian Champagnie",
            earlier: earlier, later: later, change: change)
    }

    private static func anunoby(earlier: PlayerDuelValueEndpoint10868, later: PlayerDuelValueEndpoint10868, change: String,
                                playerID: String = "3934719", original: String = anunobyOriginal) -> PlayerDuelValueRow10868 {
        row(playerID: playerID, original: original, title: anunobyTitle, name: "OG Anunoby",
            earlier: earlier, later: later, change: change)
    }

    private static let beforeRows = [
        champagnie(earlier: endpoint("First captured", cBeforeFirst), later: endpoint("Last before game", cPregame), change: "−5¢"),
        anunoby(earlier: endpoint("First captured", aBeforeFirst), later: endpoint("Last before game", aPregame), change: "−5¢"),
    ]

    private static let finalRows = [
        champagnie(earlier: endpoint("Pre-game", cPregame), later: endpoint("Last trade", cLastTrade), change: "+42¢"),
        anunoby(earlier: endpoint("Pre-game", aPregame), later: endpoint("Last trade", aLastTrade), change: "−45¢"),
    ]

    private static let ticks = [
        PlayerDuelValueTick10868(fractionOfDollar: 0, text: "0¢"),
        PlayerDuelValueTick10868(fractionOfDollar: 0.5, text: "50¢"),
        PlayerDuelValueTick10868(fractionOfDollar: 1, text: "100¢"),
    ]

    private static func input(_ rows: [PlayerDuelValueRow10868], selected: String? = nil, note: String? = nil,
                              context: String? = "Knicks 105–95 Spurs · Final",
                              ticks: [PlayerDuelValueTick10868] = PlayerDuelValuePresentation10868Tests.ticks) -> PlayerDuelValueInput10868 {
        PlayerDuelValueInput10868(
            eyebrow: "MADE THREES · CONTRACT VALUES",
            title: "How the market moved",
            context: context,
            quantity: quantity,
            tieRule: tieRule,
            ticks: ticks,
            rows: rows,
            phaseNote: note,
            selectedOriginalID: selected
        )
    }

    // MARK: Retained frames

    func testRetainedBeforeKeepsEachPlayersOwnEndpointsAndChange() {
        let input = Self.input(Self.beforeRows, context: "Knicks vs Spurs · Before game")
        let (champagnie, anunoby) = (input.rows[0], input.rows[1])

        XCTAssertEqual(input.rows.map(\.originalID), [Self.champagnieOriginal, Self.anunobyOriginal], "Owner order, own originals")
        XCTAssertEqual(input.earlier(champagnie), .marked(Self.cBeforeFirst, fraction: 0.62))
        XCTAssertEqual(input.later(champagnie), .marked(Self.cPregame, fraction: 0.57))
        XCTAssertEqual(input.earlier(anunoby), .marked(Self.aBeforeFirst, fraction: 0.52))
        XCTAssertEqual(input.later(anunoby), .marked(Self.aPregame, fraction: 0.47))
        XCTAssertEqual(input.connector(champagnie), PlayerDuelValueConnector10868(earlier: 0.62, later: 0.57))
        XCTAssertEqual(input.connector(anunoby), PlayerDuelValueConnector10868(earlier: 0.52, later: 0.47))
        XCTAssertEqual(input.rows.map(\.change), ["−5¢", "−5¢"], "The owner's change words, never re-derived")
        XCTAssertEqual(input.rows.map(\.earlier.label), ["First captured", "First captured"])
        XCTAssertEqual(input.rows.map(\.later.label), ["Last before game", "Last before game"])
        XCTAssertTrue(input.showsMarkKey)
        XCTAssertNil(input.phaseNote)
    }

    func testRetainedFinalKeepsOwnBaselineLastTradeAndTheWarning() {
        let input = Self.input(Self.finalRows, note: Self.finalNote)
        let (champagnie, anunoby) = (input.rows[0], input.rows[1])

        XCTAssertEqual(input.earlier(champagnie), .marked(Self.cPregame, fraction: 0.57))
        XCTAssertEqual(input.later(champagnie), .marked(Self.cLastTrade, fraction: 0.99))
        XCTAssertEqual(input.earlier(anunoby), .marked(Self.aPregame, fraction: 0.47))
        XCTAssertEqual(input.later(anunoby), .marked(Self.aLastTrade, fraction: 0.02))
        XCTAssertEqual(input.rows.map(\.change), ["+42¢", "−45¢"])
        XCTAssertEqual(input.phaseNote, Self.finalNote)
    }

    func testEachPlayerKeepsItsOwnClocks() {
        let before = Self.input(Self.beforeRows)
        let final = Self.input(Self.finalRows)

        // The players' clocks differ; no shared time is elected.
        XCTAssertEqual(before.accessibilityValue(for: before.rows[0]),
                       "Value per $1 contract; Change: −5¢; First captured: 62¢, Jun 3, 7:22 AM, Kalshi · traded minute close; Last before game: 57¢, Jun 3, 5:29 PM, Kalshi · traded minute close")
        XCTAssertEqual(before.accessibilityValue(for: before.rows[1]),
                       "Value per $1 contract; Change: −5¢; First captured: 52¢, Jun 3, 10:06 AM, Kalshi · traded minute close; Last before game: 47¢, Jun 3, 4:23 PM, Kalshi · traded minute close")
        XCTAssertEqual(final.accessibilityValue(for: final.rows[0]),
                       "Value per $1 contract; Change: +42¢; Pre-game: 57¢, Jun 3, 5:29 PM, Kalshi · traded minute close; Last trade: 99¢, Jun 3, 6:45 PM, Kalshi · traded minute close")
        XCTAssertEqual(final.accessibilityValue(for: final.rows[1]),
                       "Value per $1 contract; Change: −45¢; Pre-game: 47¢, Jun 3, 4:23 PM, Kalshi · traded minute close; Last trade: 2¢, Jun 3, 6:08 PM, Kalshi · traded minute close")
    }

    // MARK: Quantity and tie terms

    func testValuesAreCentsWithTieTermsNeverAWinChance() {
        let input = Self.input(Self.finalRows, note: Self.finalNote)

        XCTAssertEqual(input.ruleText, "Value per $1 contract · A tie pays 50¢. This is not a win probability.")
        XCTAssertEqual(input.accessibilityRule, "Value per $1 contract. A tie pays 50¢. This is not a win probability.")
        for row in input.rows {
            let spoken = input.accessibilityValue(for: row)
            XCTAssertTrue(spoken.hasPrefix("Value per $1 contract; "), "Every row speaks its quantity first")
            XCTAssertFalse(spoken.contains("%"), "No value is spoken as a percent")
            XCTAssertFalse(spoken.lowercased().contains("chance"))
        }
        XCTAssertEqual(input.visibleTicks.map(\.text), ["0¢", "50¢", "100¢"], "The owner's cents scale")
    }

    func testLastTradeIsNeverSettlement() {
        let input = Self.input(Self.finalRows, note: Self.finalNote)

        // 99¢ and 2¢ stay trades: never 100%/0%, never moved to the scale's ends, never a grade.
        XCTAssertEqual(input.later(input.rows[0]).fraction, 0.99)
        XCTAssertEqual(input.later(input.rows[1]).fraction, 0.02)
        for row in input.rows {
            let spoken = input.accessibilityValue(for: row)
            for leaked in ["100", "Won", "Lost", "Final result", "settled"] {
                XCTAssertFalse(spoken.contains(leaked), "No settlement or grade: \(leaked)")
            }
        }
        XCTAssertNotEqual(input.later(input.rows[0]), .marked(Self.cLastTrade, fraction: 1))
    }

    // MARK: Own readings only

    func testMissingEndpointKeepsItsOwnWordsAndTheNeighbourIsUnaffected() {
        let rows = [
            Self.champagnie(earlier: Self.endpoint("Pre-game", Self.cPregame),
                            later: Self.endpoint("Last trade", nil, missing: "No later captured trade"), change: "No later trade"),
            Self.finalRows[1],
        ]
        let input = Self.input(rows)

        XCTAssertEqual(input.earlier(input.rows[0]), .marked(Self.cPregame, fraction: 0.57))
        XCTAssertEqual(input.later(input.rows[0]), .words("No later captured trade"))
        XCTAssertNil(input.connector(input.rows[0]), "One endpoint draws no connector")
        XCTAssertEqual(input.later(input.rows[1]), .marked(Self.aLastTrade, fraction: 0.02), "The neighbour keeps its own reading")
        XCTAssertNotNil(input.connector(input.rows[1]))
        XCTAssertTrue(input.accessibilityValue(for: input.rows[0]).hasSuffix("Last trade: No later captured trade"))
    }

    func testForeignReadingIsNeverBorrowed() {
        // CONSTRUCTED: Anunoby's later slot carries Champagnie's last trade.
        let rows = [
            Self.finalRows[0],
            Self.anunoby(earlier: Self.endpoint("Pre-game", Self.aPregame), later: Self.endpoint("Last trade", Self.cLastTrade), change: "−45¢"),
        ]
        let input = Self.input(rows)

        XCTAssertEqual(input.later(input.rows[1]), .words("Value unavailable"))
        XCTAssertNil(input.connector(input.rows[1]))
        XCTAssertEqual(input.earlier(input.rows[1]), .marked(Self.aPregame, fraction: 0.47), "Its own earlier reading stays")
        XCTAssertFalse(input.accessibilityValue(for: input.rows[1]).contains("99¢"))
        XCTAssertEqual(input.later(input.rows[0]), .marked(Self.cLastTrade, fraction: 0.99), "The owner keeps its reading")

        // A reading of a different original on the same game is foreign too.
        let game = Self.value(Self.knicksOriginal, 0.61, "61¢", 1780532940, "Jun 3, 5:29 PM")
        let other = Self.input([Self.champagnie(earlier: Self.endpoint("Pre-game", game), later: Self.endpoint("Last trade", Self.cLastTrade), change: "+42¢")])
        XCTAssertEqual(other.earlier(other.rows[0]), .words("Value unavailable"))
        XCTAssertNil(other.connector(other.rows[0]))
    }

    func testRepeatedObservationIdentityDrawsNoneOfItsReadings() {
        // CONSTRUCTED: one observation id used as both endpoints of a row.
        let twice = Self.value(Self.champagnieOriginal, 0.99, "99¢", 1780537500, "Jun 3, 6:45 PM", id: "obs-1")
        let sameRow = Self.input([
            Self.champagnie(earlier: Self.endpoint("Pre-game", twice), later: Self.endpoint("Last trade", twice), change: "Unchanged"),
            Self.finalRows[1],
        ])
        XCTAssertEqual(sameRow.earlier(sameRow.rows[0]), .words("Value unavailable"))
        XCTAssertEqual(sameRow.later(sameRow.rows[0]), .words("Value unavailable"), "Neither end is elected")
        XCTAssertNil(sameRow.connector(sameRow.rows[0]))
        XCTAssertNotNil(sameRow.connector(sameRow.rows[1]), "The neighbour is unaffected")

        // CONSTRUCTED: two distinct originals whose providers reuse one opaque
        // observation id. Ids are scoped to their original, so both keep their readings.
        let cShared = Self.value(Self.champagnieOriginal, 0.99, "99¢", 1780537500, "Jun 3, 6:45 PM", id: "obs-2")
        let aShared = Self.value(Self.anunobyOriginal, 0.02, "2¢", 1780535280, "Jun 3, 6:08 PM", id: "obs-2")
        let crossRow = Self.input([
            Self.champagnie(earlier: Self.endpoint("Pre-game", Self.cPregame), later: Self.endpoint("Last trade", cShared), change: "+42¢"),
            Self.anunoby(earlier: Self.endpoint("Pre-game", Self.aPregame), later: Self.endpoint("Last trade", aShared), change: "−45¢"),
        ])
        XCTAssertEqual(crossRow.earlier(crossRow.rows[0]), .marked(Self.cPregame, fraction: 0.57))
        XCTAssertEqual(crossRow.later(crossRow.rows[0]), .marked(cShared, fraction: 0.99), "Champagnie keeps 99¢")
        XCTAssertEqual(crossRow.earlier(crossRow.rows[1]), .marked(Self.aPregame, fraction: 0.47))
        XCTAssertEqual(crossRow.later(crossRow.rows[1]), .marked(aShared, fraction: 0.02), "Anunoby keeps 2¢")
        XCTAssertEqual(crossRow.connector(crossRow.rows[0]), PlayerDuelValueConnector10868(earlier: 0.57, later: 0.99))
        XCTAssertEqual(crossRow.connector(crossRow.rows[1]), PlayerDuelValueConnector10868(earlier: 0.47, later: 0.02))
        XCTAssertTrue(crossRow.accessibilityValue(for: crossRow.rows[0]).hasSuffix("Last trade: 99¢, Jun 3, 6:45 PM, Kalshi · traded minute close"))
        XCTAssertTrue(crossRow.accessibilityValue(for: crossRow.rows[1]).hasSuffix("Last trade: 2¢, Jun 3, 6:08 PM, Kalshi · traded minute close"))

        // CONSTRUCTED: a foreign endpoint in Anunoby's row carries Champagnie's reading
        // and token. It is refused there and does not poison Champagnie's own reading.
        let cToken = Self.value(Self.champagnieOriginal, 0.99, "99¢", 1780537500, "Jun 3, 6:45 PM", id: "obs-3")
        let foreignToken = Self.input([
            Self.champagnie(earlier: Self.endpoint("Pre-game", Self.cPregame), later: Self.endpoint("Last trade", cToken), change: "+42¢"),
            Self.anunoby(earlier: Self.endpoint("Pre-game", Self.aPregame), later: Self.endpoint("Last trade", cToken), change: "−45¢"),
        ])
        XCTAssertEqual(foreignToken.later(foreignToken.rows[1]), .words("Value unavailable"), "Never borrowed")
        XCTAssertEqual(foreignToken.earlier(foreignToken.rows[1]), .marked(Self.aPregame, fraction: 0.47))
        XCTAssertNil(foreignToken.connector(foreignToken.rows[1]))
        XCTAssertEqual(foreignToken.later(foreignToken.rows[0]), .marked(cToken, fraction: 0.99), "The neighbour is not poisoned")
        XCTAssertEqual(foreignToken.connector(foreignToken.rows[0]), PlayerDuelValueConnector10868(earlier: 0.57, later: 0.99))

        // CONSTRUCTED: a foreign endpoint inside Champagnie's own row reuses the token of
        // the row's other endpoint. Only the own reading counts, so it stays drawn.
        let gameToken = Self.value(Self.knicksOriginal, 0.61, "61¢", 1780532940, "Jun 3, 5:29 PM", id: "obs-3")
        let foreignInRow = Self.input([
            Self.champagnie(earlier: Self.endpoint("Pre-game", gameToken), later: Self.endpoint("Last trade", cToken), change: "+42¢"),
            Self.finalRows[1],
        ])
        XCTAssertEqual(foreignInRow.earlier(foreignInRow.rows[0]), .words("Value unavailable"))
        XCTAssertEqual(foreignInRow.later(foreignInRow.rows[0]), .marked(cToken, fraction: 0.99), "Its own reading stays")
        XCTAssertNil(foreignInRow.connector(foreignInRow.rows[0]))
        XCTAssertEqual(foreignInRow.later(foreignInRow.rows[1]), .marked(Self.aLastTrade, fraction: 0.02), "The neighbour is unaffected")

        // No observation id: ties rest on the original alone.
        let anonymous = PlayerDuelValueObservation10868(originalID: Self.champagnieOriginal, observationID: nil, fractionOfDollar: 0.57,
                                                        figure: "57¢", time: "Jun 3, 5:29 PM", sourceWords: nil)
        let plain = Self.input([Self.champagnie(earlier: Self.endpoint("Pre-game", anonymous), later: Self.endpoint("Last trade", anonymous), change: "Unchanged")])
        XCTAssertEqual(plain.connector(plain.rows[0]), PlayerDuelValueConnector10868(earlier: 0.57, later: 0.57))
        XCTAssertEqual(plain.accessibilityValue(for: plain.rows[0]),
                       "Value per $1 contract; Change: Unchanged; Pre-game: 57¢, Jun 3, 5:29 PM; Last trade: 57¢, Jun 3, 5:29 PM")
    }

    func testSharedOriginalDrawsNoValuesAndSharedPlayerIsNotSelectable() {
        // CONSTRUCTED: both rows carry Champagnie's original.
        let sharedOriginal = Self.input([
            Self.finalRows[0],
            Self.anunoby(earlier: Self.endpoint("Pre-game", Self.cPregame), later: Self.endpoint("Last trade", Self.cLastTrade),
                         change: "+42¢", original: Self.champagnieOriginal),
        ], selected: Self.champagnieOriginal)
        XCTAssertEqual(sharedOriginal.rows.count, 2, "Both rows stay")
        for row in sharedOriginal.rows {
            XCTAssertEqual(sharedOriginal.earlier(row), .words("Value unavailable"), "An ambiguous original lends no reading")
            XCTAssertNil(sharedOriginal.connector(row))
            XCTAssertNil(sharedOriginal.rowAction(row, canSelect: true))
        }
        XCTAssertEqual(sharedOriginal.selection, .duplicate(Self.champagnieOriginal))
        XCTAssertFalse(sharedOriginal.showsMarkKey)

        // CONSTRUCTED: one player identity on two originals keeps each own reading but selects nothing.
        let sharedPlayer = Self.input([
            Self.finalRows[0],
            Self.anunoby(earlier: Self.endpoint("Pre-game", Self.aPregame), later: Self.endpoint("Last trade", Self.aLastTrade),
                         change: "−45¢", playerID: "4592479"),
        ], selected: Self.anunobyOriginal)
        XCTAssertEqual(sharedPlayer.later(sharedPlayer.rows[1]), .marked(Self.aLastTrade, fraction: 0.02))
        XCTAssertEqual(sharedPlayer.selection, .duplicate(Self.anunobyOriginal))
        XCTAssertTrue(sharedPlayer.rows.allSatisfy { sharedPlayer.rowAction($0, canSelect: true) == nil })
        XCTAssertNil(sharedPlayer.detailsAction(canOpenDetails: true))
    }

    // MARK: Values on the scale

    func testInvalidValuesKeepTheOwnersFigureAndDrawNoMarkOrConnector() {
        for bad in [Double.nan, .infinity, -.infinity, -0.01, 1.2] {
            let broken = Self.value(Self.champagnieOriginal, bad, "57¢", 1780532940, "Jun 3, 5:29 PM")
            let input = Self.input([
                Self.champagnie(earlier: Self.endpoint("Pre-game", broken), later: Self.endpoint("Last trade", Self.cLastTrade), change: "+42¢"),
                Self.finalRows[1],
            ])
            // Matched by case: NaN never equals itself, so the whole value is not compared.
            guard case .unplaced(let shown) = input.earlier(input.rows[0]) else {
                return XCTFail("\(bad): readable owner words at reading size, no mark")
            }
            XCTAssertEqual(shown.originalID, Self.champagnieOriginal)
            XCTAssertEqual(shown.figure, "57¢")
            XCTAssertEqual(shown.time, "Jun 3, 5:29 PM")
            XCTAssertNil(input.earlier(input.rows[0]).fraction)
            XCTAssertNil(input.connector(input.rows[0]), "No connector without two drawn endpoints")
            XCTAssertEqual(input.later(input.rows[0]), .marked(Self.cLastTrade, fraction: 0.99), "The other endpoint stays")
            XCTAssertTrue(input.accessibilityValue(for: input.rows[0]).contains("Pre-game: 57¢, Jun 3, 5:29 PM"))
        }
    }

    func testZeroAndOneAreRealEndpoints() {
        // CONSTRUCTED values at the scale's ends.
        let zero = Self.value(Self.anunobyOriginal, 0, "0¢", 1780535280, "Jun 3, 6:08 PM")
        let one = Self.value(Self.champagnieOriginal, 1, "100¢", 1780537500, "Jun 3, 6:45 PM")
        let input = Self.input([
            Self.champagnie(earlier: Self.endpoint("Pre-game", Self.cPregame), later: Self.endpoint("Last trade", one), change: "+43¢"),
            Self.anunoby(earlier: Self.endpoint("Pre-game", Self.aPregame), later: Self.endpoint("Last trade", zero), change: "−47¢"),
        ])

        XCTAssertEqual(input.later(input.rows[0]), .marked(one, fraction: 1))
        XCTAssertEqual(input.later(input.rows[1]), .marked(zero, fraction: 0), "0 is an observation, not an absence")
        XCTAssertEqual(input.connector(input.rows[1]), PlayerDuelValueConnector10868(earlier: 0.47, later: 0))
    }

    func testUnchangedValueKeepsBothMarksAtOnePlace() {
        let later = Self.value(Self.champagnieOriginal, 0.57, "57¢", 1780537500, "Jun 3, 6:45 PM")
        let input = Self.input([Self.champagnie(earlier: Self.endpoint("Pre-game", Self.cPregame), later: Self.endpoint("Last trade", later), change: "Unchanged")])
        let row = input.rows[0]

        XCTAssertEqual(input.connector(row), PlayerDuelValueConnector10868(earlier: 0.57, later: 0.57))
        XCTAssertEqual(PlayerDuelValueGeometry10868.x(input.earlier(row), width: 300, inset: 8),
                       PlayerDuelValueGeometry10868.x(input.later(row), width: 300, inset: 8))
        XCTAssertEqual(row.change, "Unchanged")
    }

    // MARK: Frames

    func testBeforeOnlyFrameHasNoLaterMarkOrConnector() {
        // CONSTRUCTED: an early before frame with no later captured trade yet.
        let rows = [
            Self.champagnie(earlier: Self.endpoint("First captured", Self.cBeforeFirst),
                            later: Self.endpoint("Last before game", nil, missing: "No later captured trade"), change: "No later trade"),
            Self.anunoby(earlier: Self.endpoint("First captured", nil), later: Self.endpoint("Last before game", nil, missing: "No later captured trade"),
                         change: "No later trade"),
        ]
        let input = Self.input(rows, context: "Knicks vs Spurs · Before game")

        XCTAssertEqual(input.earlier(input.rows[0]), .marked(Self.cBeforeFirst, fraction: 0.62))
        XCTAssertEqual(input.later(input.rows[0]), .words("No later captured trade"))
        XCTAssertEqual(input.earlier(input.rows[1]), .words("No captured trade"))
        XCTAssertTrue(input.rows.allSatisfy { input.connector($0) == nil })
        XCTAssertTrue(input.showsMarkKey, "One drawn mark still needs the key")

        let empty = Self.input([rows[1]])
        XCTAssertFalse(empty.showsMarkKey, "No mark, no key")
    }

    func testConstructedLiveFrameIsShownAsGiven() {
        // CONSTRUCTED: an owner-admitted live frame; not real live evidence.
        let live = Self.value(Self.champagnieOriginal, 0.71, "71¢", 1780535000, "Jun 3, 6:03 PM · constructed")
        let rows = [
            Self.champagnie(earlier: Self.endpoint("Pre-game", Self.cPregame), later: Self.endpoint("Latest trade", live), change: "+14¢"),
            Self.anunoby(earlier: Self.endpoint("Pre-game", Self.aPregame), later: Self.endpoint("Latest trade", nil, missing: "No trade since the start"),
                         change: "No later trade"),
        ]
        let input = Self.input(rows, note: "Values are still trading.", context: "Knicks 52–48 Spurs · 2nd quarter")

        XCTAssertEqual(input.later(input.rows[0]), .marked(live, fraction: 0.71))
        XCTAssertEqual(input.later(input.rows[1]), .words("No trade since the start"))
        XCTAssertEqual(input.rows[0].later.label, "Latest trade")
        XCTAssertEqual(input.phaseNote, "Values are still trading.")
    }

    func testRowsBeyondTwoKeepOwnerOrderAndOwnClocks() {
        // CONSTRUCTED third row with its own identity, original and times.
        let third = Self.row(playerID: "third", original: "third-original", title: "Third original", name: "Third Player",
                             earlier: Self.endpoint("Pre-game", Self.value("third-original", 0.30, "30¢", 1780530000, "Jun 3, 4:40 PM")),
                             later: Self.endpoint("Last trade", Self.value("third-original", 0.35, "35¢", 1780536000, "Jun 3, 6:20 PM")),
                             change: "+5¢")
        let input = Self.input([Self.finalRows[1], third, Self.finalRows[0]], selected: "third-original")

        XCTAssertEqual(input.rows.map(\.originalID), [Self.anunobyOriginal, "third-original", Self.champagnieOriginal], "Never re-sorted")
        XCTAssertEqual(input.connector(input.rows[1]), PlayerDuelValueConnector10868(earlier: 0.30, later: 0.35))
        XCTAssertEqual(input.selection.row?.originalID, "third-original")
        XCTAssertTrue(input.accessibilityValue(for: input.rows[1]).hasSuffix("Last trade: 35¢, Jun 3, 6:20 PM, Kalshi · traded minute close"))
        XCTAssertEqual(input.later(input.rows[2]), .marked(Self.cLastTrade, fraction: 0.99))
    }

    // MARK: Selection

    func testExactSelectionMarksOneRow() {
        let input = Self.input(Self.finalRows, selected: Self.anunobyOriginal)
        XCTAssertEqual(input.selection, .selected(input.rows[1]))
        XCTAssertFalse(input.isSelected(input.rows[0]))
        XCTAssertTrue(input.isSelected(input.rows[1]))
        XCTAssertNil(input.selectionNotice)

        let none = Self.input(Self.finalRows)
        XCTAssertEqual(none.selection, .none)
        XCTAssertFalse(none.rows.contains { none.isSelected($0) })
    }

    func testMissingWithdrawnAndForeignSelectionSelectsNobody() {
        let foreign = Self.input(Self.finalRows, selected: Self.knicksOriginal)
        XCTAssertEqual(foreign.selection, .missing(Self.knicksOriginal))
        XCTAssertEqual(foreign.selectionNotice, "Selected contract unavailable.")
        XCTAssertFalse(foreign.rows.contains { foreign.isSelected($0) })

        // CONSTRUCTED: Anunoby withdrawn; the selection is not moved to Champagnie.
        let withdrawn = Self.input([Self.finalRows[0]], selected: Self.anunobyOriginal)
        XCTAssertEqual(withdrawn.selection, .missing(Self.anunobyOriginal))
        XCTAssertNil(withdrawn.detailsAction(canOpenDetails: true))
        XCTAssertEqual(withdrawn.later(withdrawn.rows[0]), .marked(Self.cLastTrade, fraction: 0.99))

        // A player id is not an original id.
        XCTAssertEqual(Self.input(Self.finalRows, selected: "4592479").selection, .missing("4592479"))
    }

    // MARK: Callbacks

    func testActionsCarryExactOriginalIDs() {
        let input = Self.input(Self.finalRows, selected: Self.anunobyOriginal)
        var selected: [String] = []
        var details: [String] = []

        for row in input.rows {
            input.rowAction(row, canSelect: true)?
                .perform(onSelect: { selected.append($0) }, onChoosePlayer: nil, onDetails: { details.append($0) })
        }
        input.detailsAction(canOpenDetails: true)?
            .perform(onSelect: { selected.append($0) }, onChoosePlayer: nil, onDetails: { details.append($0) })

        XCTAssertEqual(selected, [Self.champagnieOriginal, Self.anunobyOriginal])
        XCTAssertEqual(details, [Self.anunobyOriginal])
    }

    @MainActor
    func testNoCallbackMeansNoActionAndTheCardIsStatic() {
        let input = Self.input(Self.finalRows, selected: Self.champagnieOriginal)
        let view = PlayerDuelValuePresentation10868(input: input)

        XCTAssertNil(view.onSelect)
        XCTAssertNil(view.onDetails)
        XCTAssertTrue(input.rows.allSatisfy { input.rowAction($0, canSelect: false) == nil })
        XCTAssertNil(input.detailsAction(canOpenDetails: false))
        XCTAssertNil(Self.input(Self.finalRows).detailsAction(canOpenDetails: true), "No selection, no Details")
    }

    // MARK: Geometry and layout

    func testInsetKeepsRealEndsInsideAndTheConnectorJoinsOwnMarks() {
        let inset = PlayerDuelValueGeometry10868.inset(markDiameter: 14)
        XCTAssertEqual(inset, 8)
        XCTAssertEqual(PlayerDuelValueGeometry10868.inset(markDiameter: 0), 0)
        XCTAssertEqual(PlayerDuelValueGeometry10868.inset(markDiameter: .nan), 0)

        let one = Self.value(Self.champagnieOriginal, 1, "100¢", 1780537500, "Jun 3, 6:45 PM")
        let zero = Self.value(Self.champagnieOriginal, 0, "0¢", 1780532940, "Jun 3, 5:29 PM")
        let ends = Self.input([Self.champagnie(earlier: Self.endpoint("Pre-game", zero), later: Self.endpoint("Last trade", one), change: "+100¢")])
        let x0 = PlayerDuelValueGeometry10868.x(ends.earlier(ends.rows[0]), width: 300, inset: inset)!
        let x1 = PlayerDuelValueGeometry10868.x(ends.later(ends.rows[0]), width: 300, inset: inset)!
        XCTAssertEqual(x0, 8)
        XCTAssertEqual(x1, 292)
        XCTAssertGreaterThanOrEqual(x0 - 7, 0, "A real 0¢ ring sits inside the track")
        XCTAssertLessThanOrEqual(x1 + 7, 300, "A real 100¢ ring sits inside the track")

        let final = Self.input(Self.finalRows)
        let span = PlayerDuelValueGeometry10868.span(final.connector(final.rows[0]), width: 300, inset: inset)!
        XCTAssertEqual(span[0], PlayerDuelValueGeometry10868.x(final.earlier(final.rows[0]), width: 300, inset: inset))
        XCTAssertEqual(span[1], PlayerDuelValueGeometry10868.x(final.later(final.rows[0]), width: 300, inset: inset))
        XCTAssertEqual(span[0], 8 + 284 * 0.57, accuracy: 0.0001)
        XCTAssertEqual(span[1], 8 + 284 * 0.99, accuracy: 0.0001)
        XCTAssertNil(PlayerDuelValueGeometry10868.span(nil, width: 300, inset: inset))
        XCTAssertNil(PlayerDuelValueGeometry10868.x(.words("No captured trade"), width: 300, inset: inset))
        XCTAssertNil(PlayerDuelValueGeometry10868.span(final.connector(final.rows[0]), width: 16, inset: inset), "No usable track, no connector")
    }

    func testScaleDrawsOnlyPlaceableOwnerTicks() {
        let ticks = Self.ticks + [PlayerDuelValueTick10868(fractionOfDollar: 1.5, text: "150¢"),
                                  PlayerDuelValueTick10868(fractionOfDollar: .nan, text: "?")]
        let input = Self.input(Self.finalRows, ticks: ticks)
        XCTAssertEqual(input.visibleTicks, [
            PlayerContributionPlacedTick10868(fraction: 0, text: "0¢"),
            PlayerContributionPlacedTick10868(fraction: 0.5, text: "50¢"),
            PlayerContributionPlacedTick10868(fraction: 1, text: "100¢"),
        ])
        XCTAssertEqual(Self.input(Self.finalRows, ticks: []).visibleTicks, [])
    }

    func testValuesPairThenStackAndAccessibilitySizesStack() {
        let input = Self.input(Self.finalRows)
        XCTAssertEqual(input.layouts(isAccessibilitySize: false), [.paired, .stacked])
        XCTAssertEqual(input.layouts(isAccessibilitySize: true), [.stacked])
    }

    // MARK: Spoken text and ids

    func testSpokenHeaderRuleAndKey() {
        let input = Self.input(Self.finalRows, note: Self.finalNote)
        XCTAssertEqual(input.accessibilityHeader, "MADE THREES · CONTRACT VALUES. How the market moved")
        XCTAssertEqual(input.accessibilityKey,
                       "Hollow: earlier value · filled: later value. Each player has their own trade times. The line compares values, not elapsed time.")
    }

    func testOwnerStringsAreShownVerbatim() {
        // CONSTRUCTED long and qualified owner strings.
        let long = Self.row(playerID: "x", original: "x-original",
                            title: "Will Maximilian Alexander Shabanov-Kuznetsov record more made three pointers in regulation and overtime?",
                            name: "Maximilian Alexander Shabanov-Kuznetsov",
                            earlier: Self.endpoint("Pre-game baseline (last trade before the listed start)",
                                                   Self.value("x-original", 0.415, "41.5¢", 1780530000, "Wednesday, June 3, 4:40 PM Pacific")),
                            later: Self.endpoint("Last trade", nil, missing: "No later captured trade in this market"),
                            change: "No later trade")
        let input = Self.input([long, Self.finalRows[1]], selected: "x-original")

        XCTAssertEqual(input.earlier(long), .marked(Self.value("x-original", 0.415, "41.5¢", 1780530000, "Wednesday, June 3, 4:40 PM Pacific"), fraction: 0.415))
        XCTAssertEqual(input.later(long), .words("No later captured trade in this market"))
        XCTAssertEqual(input.selection.row?.originalTitle, long.originalTitle)
        XCTAssertEqual(input.selection.row?.name, "Maximilian Alexander Shabanov-Kuznetsov")
    }

    func testAccessibilityIdentifiersCarryExactIDs() {
        XCTAssertEqual(PlayerDuelValueAccessibilityID10868.row(Self.champagnieOriginal),
                       "playerDuelValue10868.row.KXNBAH2H3PT-26JUN03JCHAMPAGNIE30OANUNOBY8-JCHAMPAGNIE30")
        XCTAssertEqual(PlayerDuelValueAccessibilityID10868.details(Self.anunobyOriginal),
                       "playerDuelValue10868.details.KXNBAH2H3PT-26JUN03JCHAMPAGNIE30OANUNOBY8-OANUNOBY8")
        XCTAssertEqual(PlayerDuelValueAccessibilityID10868.key, "playerDuelValue10868.key")
    }
}
