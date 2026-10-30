import SwiftUI
import XCTest
@testable import Bain_Luck

/// #9483 — the selected line's comparison above a player's milestone chart
/// (design ref player-milestone-comparison-20261026). Cards come from the
/// real builder (`NFLMilestoneCard9483.cards`) wherever its semantics are the
/// subject; boundary cases the builder cannot reach are CONSTRUCTED cards and
/// say so. The lines and numbers echo the reference's Trevor Lawrence 300+
/// passing-yards card (14% pregame, 331 final); the fixtures are ours.
@MainActor
final class PlayerMilestoneComparison9483Tests: XCTestCase {

    private let now = Date(timeIntervalSince1970: 1_800_000_000)
    private func t(_ minutes: Double) -> Date { now.addingTimeInterval(minutes * 60) }
    private func iso(_ date: Date) -> String { ISO8601DateFormatter().string(from: date) }

    private let lines: [Double] = [200, 250, 300, 350]
    /// Venue prices — what the card reads before kickoff.
    private let prices = [0.80, 0.50, 0.14, 0.05]
    /// Pregame marks — what the card reads once play starts. Deliberately not
    /// the prices, so a test can tell which one was printed.
    private let marks = [0.85, 0.55, 0.40, 0.10]

    private func row(_ subject: String, _ line: Double, price: Double?, mark: Double?,
                     actual: Double? = nil, hit: Bool? = nil) -> GameMarketPlayerProp {
        GameMarketPlayerProp(marketName: "Passing Yards",
                             outcomeName: "\(subject): \(PlayerPropsFamily.targetLabel(line)) Passing Yards",
                             threshold: line, overProbability: price, source: "kalshi", movement: nil,
                             playerHeadshot: nil, playerTeam: "away", actual: actual, hit: hit, pregameMark: mark,
                             observedAt: iso(t(-5)), _inverted: nil)
    }

    private func ladder(_ subject: String = "Trevor Lawrence", actual: Double? = nil,
                        hits: [Bool?]? = nil) -> [GameMarketPlayerProp] {
        lines.indices.map { i in
            row(subject, lines[i], price: prices[i], mark: marks[i], actual: actual, hit: hits?[i])
        }
    }

    private func card(status: String, commenceIn minutes: Double, props: [GameMarketPlayerProp]? = nil,
                      player: String = "Trevor Lawrence") throws -> NFLMilestoneCard9483 {
        try XCTUnwrap(NFLMilestoneCard9483.cards(
            props: props ?? ladder(), eventStatus: status, commenceTime: t(minutes),
            homeTeam: "Philadelphia Eagles", awayTeam: "Jacksonville Jaguars", now: now)
            .first { $0.player == player })
    }

    private func rowID(_ card: NFLMilestoneCard9483, line: Double) throws -> String {
        try XCTUnwrap(card.rungs.first { $0.threshold == line }?.rowID)
    }

    /// CONSTRUCTED: a card with chosen fields, from a builder card's rows.
    private func constructed(from card: NFLMilestoneCard9483, stat: String? = nil, basis: NFLMilestoneCard9483.Basis? = nil,
                             rungs: [NFLMilestoneCard9483.Rung]? = nil, actual: Double?) -> NFLMilestoneCard9483 {
        NFLMilestoneCard9483(id: card.id, player: card.player, stat: stat ?? card.stat, side: card.side,
                             basis: basis ?? card.basis, rungs: rungs ?? card.rungs, actual: actual)
    }

    private func rung(_ rung: NFLMilestoneCard9483.Rung, chance: Double?? = nil,
                      hit: Bool?? = nil) -> NFLMilestoneCard9483.Rung {
        .init(threshold: rung.threshold, chance: chance ?? rung.chance, observedAt: rung.observedAt,
              rowID: rung.rowID, hit: hit ?? rung.hit)
    }

    // MARK: - Before kickoff

    func testBeforeKickoffTheSelectedLinesPregameChanceShowsOnce() throws {
        let card = try card(status: "scheduled", commenceIn: 60)
        XCTAssertEqual(card.basis, .pregamePrice, "control: the builder's pre-kickoff basis")
        let readout = PlayerMilestoneComparison9483.readout(
            card: card, selectedRowID: try rowID(card, line: 300), isFinal: false)
        XCTAssertEqual(readout.targetText, "300+ Passing Yards")
        XCTAssertEqual(readout.pregameFigureText, "14%")
        XCTAssertEqual(readout.pregameCaption, "Chance to reach 300+")
        XCTAssertEqual(readout.layout, .pregameOnly, "one pregame figure, no second before-play column")
        XCTAssertNil(readout.actual)
        XCTAssertNil(readout.result)
    }

    /// The host's row decides the line; moving it moves the readout.
    func testTheReadoutFollowsExactlyTheSuppliedRow() throws {
        let card = try card(status: "scheduled", commenceIn: 60)
        let at350 = PlayerMilestoneComparison9483.readout(
            card: card, selectedRowID: try rowID(card, line: 350), isFinal: false)
        XCTAssertEqual(at350.targetText, "350+ Passing Yards")
        XCTAssertEqual(at350.pregameFigureText, "5%")
    }

    // MARK: - Selection never falls back

    func testNoSelectionSelectsNothingEvenWhenTheCardHasADefaultLine() throws {
        let card = try card(status: "scheduled", commenceIn: 60)
        XCTAssertNotNil(card.defaultRung, "control: the card would open on a line")
        let readout = PlayerMilestoneComparison9483.readout(card: card, selectedRowID: nil, isFinal: false)
        XCTAssertEqual(readout.selection, .none)
        XCTAssertEqual(readout.targetText, "No line selected")
        XCTAssertEqual(readout.pregame, .noLine)
        XCTAssertEqual(readout.pregameFigureText, absentProbabilityMarker, "never the default line's 50%")
    }

    /// A row missing from this update is unavailable here, not withdrawn by
    /// the venue: the card cannot tell why the row is absent.
    func testARowMissingFromThisUpdateIsUnavailableNeverANeighbour() throws {
        let card = try card(status: "scheduled", commenceIn: 60)
        let gone = try rowID(card, line: 350)
        // CONSTRUCTED: this update carries no 350+ row.
        let missing = constructed(from: card, rungs: Array(card.rungs.dropLast()), actual: nil)
        let readout = PlayerMilestoneComparison9483.readout(card: missing, selectedRowID: gone, isFinal: false)
        XCTAssertEqual(readout.selection, .unavailable)
        XCTAssertEqual(readout.targetText, "Selected line unavailable in this update")
        XCTAssertEqual(readout.targetSpoken, "Selected line unavailable in this update")
        XCTAssertFalse(readout.targetText.contains("no longer offered"), "absence is not a withdrawal")
        XCTAssertEqual(readout.pregameFigureText, absentProbabilityMarker, "not the 300+ row's 14%")
    }

    func testAnotherPlayersRowIsNotResolvedOnThisCard() throws {
        let props = ladder() + ladder("Jalen Hurts")
        let lawrence = try card(status: "scheduled", commenceIn: 60, props: props)
        let hurts = try card(status: "scheduled", commenceIn: 60, props: props, player: "Jalen Hurts")
        let readout = PlayerMilestoneComparison9483.readout(
            card: lawrence, selectedRowID: try rowID(hurts, line: 300), isFinal: false)
        XCTAssertEqual(readout.selection, .unavailable, "same line, other player: no borrowed number")
    }

    // MARK: - During play: the mark is pregame, current is unavailable

    func testDuringPlayTheMarkIsPregameAndTheCurrentChanceIsUnavailable() throws {
        let card = try card(status: "live", commenceIn: -40)
        XCTAssertEqual(card.basis, .pregameMark, "control: the builder's in-play basis")
        let readout = PlayerMilestoneComparison9483.readout(
            card: card, selectedRowID: try rowID(card, line: 300), isFinal: false)
        XCTAssertEqual(readout.pregameFigureText, "40%", "the pregame mark, not the venue's 14% price")
        XCTAssertTrue(readout.pregameSpoken.hasPrefix("Pregame chance"))
        XCTAssertEqual(readout.layout, .pregameAndUnavailableCurrent)
        XCTAssertEqual(PlayerMilestoneComparison9483.Readout.currentSpoken, "Current chance, unavailable")
        XCTAssertFalse(PlayerMilestoneComparison9483.Readout.currentSpoken.contains("40%"),
                       "the pregame mark is never relabelled current")
        XCTAssertNil(readout.actual)
        XCTAssertNil(readout.result)
    }

    /// The current column's words, on screen and spoken, are the same and
    /// claim nothing about the pregame column, so they stay true when that
    /// column is empty too.
    private func assertNeutralCurrentColumn(_ readout: PlayerMilestoneComparison9483.Readout,
                                            file: StaticString = #filePath, line: UInt = #line) {
        typealias R = PlayerMilestoneComparison9483.Readout
        XCTAssertEqual(readout.layout, .pregameAndUnavailableCurrent, file: file, line: line)
        XCTAssertEqual(R.currentLabelText, "Current", file: file, line: line)
        XCTAssertEqual(R.currentFigureText, "Unavailable", file: file, line: line)
        XCTAssertEqual(R.currentSpoken, "Current chance, unavailable", "spoken matches what is shown",
                       file: file, line: line)
        for words in [R.currentLabelText, R.currentFigureText, R.currentSpoken] {
            XCTAssertFalse(words.localizedCaseInsensitiveContains("pregame"),
                           "no claim that a pregame chance is shown", file: file, line: line)
        }
        XCTAssertEqual(readout.pregameFigureText, absentProbabilityMarker, "no pregame figure on screen",
                       file: file, line: line)
        XCTAssertNil(readout.actual, file: file, line: line)
        XCTAssertNil(readout.result, file: file, line: line)
    }

    func testDuringPlayWithNoPregameMarkTheCurrentColumnClaimsNoPregameChance() throws {
        let live = try card(status: "live", commenceIn: -40)
        // CONSTRUCTED: the selected line has no pregame mark.
        let markMissing = constructed(from: live, rungs: live.rungs.map {
            $0.threshold == 300 ? rung($0, chance: .some(nil)) : $0 }, actual: nil)
        let readout = PlayerMilestoneComparison9483.readout(
            card: markMissing, selectedRowID: try rowID(live, line: 300), isFinal: false)
        XCTAssertEqual(readout.pregame, .noPregameChance)
        XCTAssertEqual(readout.targetText, "300+ Passing Yards", "control: the line itself resolved")
        assertNeutralCurrentColumn(readout)
    }

    func testDuringPlayWithNoSelectionTheCurrentColumnClaimsNoPregameChance() throws {
        let live = try card(status: "live", commenceIn: -40)
        let readout = PlayerMilestoneComparison9483.readout(card: live, selectedRowID: nil, isFinal: false)
        XCTAssertEqual(readout.selection, .none)
        XCTAssertEqual(readout.pregame, .noLine)
        assertNeutralCurrentColumn(readout)
    }

    func testDuringPlayWithTheSelectedRowMissingTheCurrentColumnClaimsNoPregameChance() throws {
        let live = try card(status: "live", commenceIn: -40)
        let gone = try rowID(live, line: 350)
        // CONSTRUCTED: this update carries no 350+ row.
        let missing = constructed(from: live, rungs: Array(live.rungs.dropLast()), actual: nil)
        let readout = PlayerMilestoneComparison9483.readout(card: missing, selectedRowID: gone, isFinal: false)
        XCTAssertEqual(readout.selection, .unavailable)
        XCTAssertEqual(readout.targetText, "Selected line unavailable in this update")
        XCTAssertEqual(readout.pregame, .noLine)
        assertNeutralCurrentColumn(readout)
    }

    /// The builder also marks a card once the scheduled time passes with no
    /// live status; the comparison makes no game-state claim either way.
    func testAStartByTheClockAloneReadsTheSameAsLive() throws {
        let byClock = try card(status: "scheduled", commenceIn: -5)
        let live = try card(status: "live", commenceIn: -5)
        XCTAssertEqual(byClock.basis, .pregameMark, "control")
        XCTAssertEqual(
            PlayerMilestoneComparison9483.readout(card: byClock, selectedRowID: try rowID(byClock, line: 300), isFinal: false),
            PlayerMilestoneComparison9483.readout(card: live, selectedRowID: try rowID(live, line: 300), isFinal: false))
    }

    // MARK: - Final: pregame vs actual, and the server's grade apart

    func testAFinalComparesThePregameChanceWithTheActual() throws {
        let card = try card(status: "completed", commenceIn: -240,
                            props: ladder(actual: 331, hits: [true, true, true, false]))
        let readout = PlayerMilestoneComparison9483.readout(
            card: card, selectedRowID: try rowID(card, line: 300), isFinal: true)
        XCTAssertEqual(readout.layout, .pregameAndFinal)
        XCTAssertEqual(readout.pregameFigureText, "40%", "the pregame mark")
        XCTAssertEqual(readout.actualFigureText, "331")
        XCTAssertEqual(readout.actualCaption, card.stat, "the stat keeps its own unit words")
        XCTAssertEqual(readout.resultText, "Reached")
    }

    func testTheResultIsTheServersGradeNeverTheActualAgainstTheLine() throws {
        let built = try card(status: "completed", commenceIn: -240,
                             props: ladder(actual: 331, hits: [true, true, true, false]))
        // CONSTRUCTED: grades that disagree with 331-vs-line (a corrected or
        // voided settlement), so only the grade can produce the result.
        let disagreeing = constructed(from: built, rungs: built.rungs.map {
            rung($0, hit: .some($0.threshold == 300 ? false : $0.threshold == 350 ? true : $0.hit))
        }, actual: 331)
        XCTAssertEqual(PlayerMilestoneComparison9483.readout(
            card: disagreeing, selectedRowID: try rowID(built, line: 300), isFinal: true).resultText, "Not reached")
        XCTAssertEqual(PlayerMilestoneComparison9483.readout(
            card: disagreeing, selectedRowID: try rowID(built, line: 350), isFinal: true).resultText, "Reached")
    }

    func testAnUngradedLineIsNotALoss() throws {
        let built = try card(status: "completed", commenceIn: -240, props: ladder(actual: 331))
        let readout = PlayerMilestoneComparison9483.readout(
            card: built, selectedRowID: try rowID(built, line: 300), isFinal: true)
        XCTAssertEqual(readout.result, .ungraded)
        XCTAssertEqual(readout.resultText, "Not graded yet")
        XCTAssertEqual(readout.actualFigureText, "331", "the stat stands apart from the missing grade")
    }

    // MARK: - Absence is never zero; zero is zero

    func testAMissingActualIsNotZeroAndAZeroActualIsZero() throws {
        let built = try card(status: "completed", commenceIn: -240, props: ladder(actual: 331))
        let selected = try rowID(built, line: 300)
        // CONSTRUCTED: the final with no graded actual, then with a real 0.
        let missing = PlayerMilestoneComparison9483.readout(
            card: constructed(from: built, actual: nil), selectedRowID: selected, isFinal: true)
        XCTAssertEqual(missing.actual, .missing)
        XCTAssertEqual(missing.actualFigureText, absentProbabilityMarker)
        XCTAssertEqual(missing.actualCaption, "No final Passing Yards yet")
        let zero = PlayerMilestoneComparison9483.readout(
            card: constructed(from: built, actual: 0), selectedRowID: selected, isFinal: true)
        XCTAssertEqual(zero.actual, .figure("0"))
        XCTAssertEqual(zero.actualCaption, "Passing Yards")
        XCTAssertNotEqual(missing.actualSpoken, zero.actualSpoken)
    }

    func testAMissingPregameChanceKeepsItsBasisWordingAndIsNeverAPercent() throws {
        let before = try card(status: "scheduled", commenceIn: 60)
        let after = try card(status: "live", commenceIn: -40)
        // CONSTRUCTED: the selected line lost its number on each basis.
        let quoteGone = constructed(from: before, rungs: before.rungs.map {
            $0.threshold == 300 ? rung($0, chance: .some(nil)) : $0 }, actual: nil)
        let markMissing = constructed(from: after, rungs: after.rungs.map {
            $0.threshold == 300 ? rung($0, chance: .some(nil)) : $0 }, actual: nil)
        let a = PlayerMilestoneComparison9483.readout(card: quoteGone, selectedRowID: try rowID(before, line: 300), isFinal: false)
        let b = PlayerMilestoneComparison9483.readout(card: markMissing, selectedRowID: try rowID(after, line: 300), isFinal: false)
        XCTAssertEqual(a.pregame, .noRecentUpdate)
        XCTAssertEqual(a.pregameCaption, "No recent probability update")
        XCTAssertEqual(b.pregame, .noPregameChance)
        XCTAssertEqual(b.pregameCaption, "No pregame chance")
        for readout in [a, b] {
            XCTAssertEqual(readout.pregameFigureText, absentProbabilityMarker)
            XCTAssertFalse(readout.pregameFigureText.contains("%"), "not 0%, not <1%")
            XCTAssertEqual(readout.targetText, "300+ Passing Yards", "the line itself is still selected")
        }
    }

    // MARK: - The host's final flag decides the final layout

    func testAnActualAndGradesDoNotMakeTheComparisonFinal() throws {
        let built = try card(status: "completed", commenceIn: -240,
                             props: ladder(actual: 331, hits: [true, true, true, false]))
        let readout = PlayerMilestoneComparison9483.readout(
            card: built, selectedRowID: try rowID(built, line: 300), isFinal: false)
        XCTAssertEqual(readout.layout, .pregameAndUnavailableCurrent)
        XCTAssertNil(readout.actual)
        XCTAssertNil(readout.result)
    }

    func testAFinalWithNoSelectedLineStillShowsTheActualButNoResult() throws {
        let built = try card(status: "completed", commenceIn: -240,
                             props: ladder(actual: 331, hits: [true, true, true, false]))
        let readout = PlayerMilestoneComparison9483.readout(card: built, selectedRowID: nil, isFinal: true)
        XCTAssertEqual(readout.actualFigureText, "331", "the player's stat does not depend on a line")
        XCTAssertNil(readout.result, "no line, no line result")
    }

    // MARK: - Long text, size and VoiceOver

    func testALongStatIsKeptWholeInTheTargetAndTheActual() throws {
        let built = try card(status: "completed", commenceIn: -240, props: ladder(actual: 331))
        let long = "Longest Completion Including Overtime And Two-Point Attempts"
        // CONSTRUCTED: a long stat name.
        let readout = PlayerMilestoneComparison9483.readout(
            card: constructed(from: built, stat: long, actual: 331), selectedRowID: try rowID(built, line: 300), isFinal: true)
        XCTAssertEqual(readout.targetText, "300+ \(long)")
        XCTAssertEqual(readout.actualCaption, long)
    }

    func testFiguresAreLargeAndColumnsStackAtAccessibilitySizes() {
        XCTAssertGreaterThanOrEqual(PlayerMilestoneComparison9483.figurePointSize, 26)
        XCTAssertFalse(PlayerMilestoneComparison9483.stacks(at: .large))
        XCTAssertFalse(PlayerMilestoneComparison9483.stacks(at: .xxxLarge))
        XCTAssertTrue(PlayerMilestoneComparison9483.stacks(at: .accessibility1))
        XCTAssertTrue(PlayerMilestoneComparison9483.stacks(at: .accessibility5))
    }

    func testVoiceOverNamesTheTargetPregameActualAndResultApart() throws {
        let built = try card(status: "completed", commenceIn: -240,
                             props: ladder(actual: 331, hits: [true, true, true, false]))
        let readout = PlayerMilestoneComparison9483.readout(
            card: built, selectedRowID: try rowID(built, line: 300), isFinal: true)
        XCTAssertEqual(readout.targetSpoken, "Selected line, 300+ Passing Yards")
        XCTAssertEqual(readout.pregameSpoken, "Pregame chance to reach 300+, 40%")
        XCTAssertEqual(readout.actualSpoken, "Final Passing Yards, 331")
        XCTAssertEqual(readout.resultSpoken, "Line result, reached")
    }
}
