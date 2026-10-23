import XCTest
import SwiftUI
@testable import Bain_Luck

/// #11285 — Alex's installed build 65 (TestFlight 1.0.4 (65)) on the upcoming
/// 49ers–Commanders page: the projected final left its row's right half empty,
/// "Open full size" promised a screen-filling view the reader does not draw,
/// and the player-prop text was unreadably small. (The info control's half is
/// in `HeadlineDisclosure9483Tests`.)
///
/// Behaviour is asserted where it is a value; the layout halves are source
/// guards, because the page's helpers are private to `EventDetailView` and the
/// rendered acceptance is Native's and Design's, not a unit test's.
@MainActor
final class NFLReaderBuild65Feedback11285Tests: XCTestCase {

    private func source(_ path: String) throws -> String {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()   // BainLuckTests
            .deletingLastPathComponent()   // Bain Luck (project dir)
            .appendingPathComponent("Bain Luck")
            .appendingPathComponent(path)
        return try String(contentsOf: url, encoding: .utf8)
    }

    /// Anti-vacuity: every scan below reads a real file.
    func testTheScansCanSeeTheirFiles() throws {
        XCTAssertTrue(try source("Views/EventDetailView.swift").contains("struct EventDetailView"))
        XCTAssertTrue(try source("Components/NFLEventCards9483.swift").contains("struct NFLEventCardDeckView9483"))
        XCTAssertTrue(try source("Components/NBAStoryStreamView9483.swift").contains("struct NBAStoryStreamView9483"))
        XCTAssertTrue(try source("Components/PlayerPropsCardView.swift").contains("struct PlayerPropsCardView"))
        XCTAssertTrue(try source("Components/PropsStatGroupHeader.swift").contains("struct PropsStatGroupHeader"))
    }

    // MARK: - 2. The pregame projection uses the row

    func testThePregamePairSplitsOnlyAPlainAwayHomeFigure() {
        let pair = EventDetailView.projectedPair11285("24-21")
        XCTAssertEqual(pair?.away, 24)
        XCTAssertEqual(pair?.home, 21)
        XCTAssertNil(EventDetailView.projectedPair11285("13-13 games"), "a named unit prints whole")
        XCTAssertNil(EventDetailView.projectedPair11285("24"))
        XCTAssertNil(EventDetailView.projectedPair11285("24-21-3"))
        XCTAssertNil(EventDetailView.projectedPair11285("a-b"))
    }

    /// The spoken label reads the same split, so what VoiceOver says and what
    /// the halves draw are one parse.
    func testTheSpokenLabelIsUnchangedAndReadsTheSameSplit() {
        XCTAssertEqual(EventDetailView.projectionAccessibilityLabel9483(
            figure: "24-21", names: ("49ers", "Commanders")), "Projected final, 49ers 24, Commanders 21")
        XCTAssertEqual(EventDetailView.projectionAccessibilityLabel9483(
            figure: "13-13 games", names: ("A", "B")), "Projected final, 13-13 games")
    }

    /// Before the game (a "vs" centre) the projection draws through the
    /// balanced pregame row, inside `projectionText`'s gate; with a score the
    /// live/final figure-over-caption arm is unchanged.
    func testThePregameArmDrawsTheBalancedRowInsideTheGate() throws {
        let page = try source("Views/EventDetailView.swift")
        let gate = try XCTUnwrap(page.range(of: "if let projection = projectionText(event, hasScore: hasScore) {"))
        let arm = String(page[gate.upperBound...].prefix(1_400))
        let pregame = try XCTUnwrap(arm.range(of: "if headline.center == .versus {"))
        let row = try XCTUnwrap(arm.range(of: "adoptedPregameProjection11285(figure: figure, label: label,"))
        let other = try XCTUnwrap(arm.range(of: "} else {"))
        XCTAssertLessThan(pregame.lowerBound, row.lowerBound)
        XCTAssertLessThan(row.lowerBound, other.lowerBound, "the pregame row left the versus arm")
        XCTAssertTrue(arm[other.upperBound...].contains(".font(.system(size: eventHeadlineScoreSize9483"),
                      "the scored arm's figure-over-caption is not this ship")
    }

    /// Root 2018Z / Design: label on the left, the named pair on the right,
    /// wrapping (never shrinking) at larger text. A lone leading figure is
    /// what Alex saw.
    func testThePregameRowIsLabelLeftAndNamedPairRight() throws {
        let page = try source("Views/EventDetailView.swift")
        let start = try XCTUnwrap(page.range(of: "private func adoptedPregameProjection11285("))
        let end = try XCTUnwrap(page.range(of: "struct AdoptedSide9483", range: start.upperBound..<page.endIndex))
        let body = String(page[start.upperBound..<end.lowerBound])
        let fits = try XCTUnwrap(body.range(of: "ViewThatFits(in: .horizontal) {"))
        let oneLine = String(body[fits.upperBound...].prefix(260))
        XCTAssertTrue(oneLine.contains("label.fixedSize()"), "the label leads the one-line row")
        XCTAssertTrue(oneLine.contains("Spacer(minLength: 0)"))
        XCTAssertTrue(oneLine.contains("scoreline"), "the named pair trails the one-line row")
        XCTAssertTrue(body.contains("VStack(alignment: .trailing, spacing: 2) {"), "wrapped, the pair stays right")
        XCTAssertTrue(body.contains("projectedTeam11285(names.away, color: colors.away)"))
        XCTAssertTrue(body.contains("projectedTeam11285(names.home, color: colors.home)"))
        let away = try XCTUnwrap(body.range(of: "projectedPoints11285(pair.away)"))
        let home = try XCTUnwrap(body.range(of: "projectedPoints11285(pair.home)"))
        XCTAssertLessThan(away.lowerBound, home.lowerBound, "away first, as the chances are")
        XCTAssertFalse(body.contains("minimumScaleFactor"), "names wrap, never shrink")
        XCTAssertFalse(body.contains("Text(\"Projected final\")"), "the label stays the gate's one spelling (#5697)")
        // Points below the chances' size.
        XCTAssertTrue(body.contains(".font(.headline.monospacedDigit())"))
        XCTAssertFalse(body.contains("eventHeadlineChanceSize9483"))
    }

    // MARK: - 3. The opener says what it opens

    func testTheOpenerIsOpenStoryAndVoiceOverNamesTheCard() {
        XCTAssertEqual(NFLEventCardDeckView9483.openerTitle, "Open story")
        XCTAssertEqual(NFLEventCardDeckView9483.openerAccessibilityLabel("Brock Purdy · Passing yards"),
                       "Open Brock Purdy · Passing yards")
        XCTAssertFalse(NFLEventCardDeckView9483.openerTitle.localizedCaseInsensitiveContains("full"))
    }

    func testBothOpenersUseTheOneSpellingAndNoneSaysFullSize() throws {
        let deck = try source("Components/NFLEventCards9483.swift")
        let stream = try source("Components/NBAStoryStreamView9483.swift")
        for (name, text) in [("deck", deck), ("NBA stream", stream)] {
            XCTAssertFalse(text.contains("Label(\"Open full size\""), "\(name) still says Open full size")
            XCTAssertFalse(text.contains(" full size\")"), "\(name)'s spoken label still says full size")
            XCTAssertTrue(text.contains("openerTitle, systemImage: \"arrow.up.left.and.arrow.down.right\")"),
                          "\(name) lost the expansion icon or the shared title")
            XCTAssertTrue(text.contains("openerAccessibilityLabel(card.title))"), name)
            XCTAssertTrue(text.contains("openerIdentifier)"), name)
            XCTAssertTrue(text.contains(".frame(maxWidth: .infinity, minHeight: 44)"), "\(name): the 44pt target")
        }
    }

    // MARK: - 4. Prop text in the reader's text style

    /// The ladder, field and unpriced rows drew 10pt names and percentages
    /// shrinking toward 7pt, 7–8pt marks and an 8pt stat header, none of which
    /// grew with the text setting. Only the avatar's initials — a fixed circle
    /// — keep a point size.
    func testNoPropRowTextIsAFixedPointSizeOrShrinks() throws {
        let card = try source("Components/PlayerPropsCardView.swift")
        let fixed = card.components(separatedBy: ".font(.system(size:").count - 1
        XCTAssertEqual(fixed, 3, "a prop row drew a fixed point size again (the 3 are the avatar initials)")
        XCTAssertEqual(card.components(separatedBy: ".font(.system(size: 12, weight: .bold))").count - 1, 3)
        XCTAssertFalse(card.contains("minimumScaleFactor(0.7)"), "a percentage shrinks toward 7pt again")
        XCTAssertFalse(card.contains("minimumScaleFactor(0.8)"), "a field name shrinks again")
        let header = try source("Components/PropsStatGroupHeader.swift")
        XCTAssertFalse(header.contains(".font(.system(size:"), "the stat header is a fixed point size again")
    }

    /// Each row keeps its track (the dense graphic), and accessibility sizes
    /// move it under the words rather than squeezing them.
    func testTheRungRowKeepsItsTrackAndStacksItAtAccessibilitySizes() throws {
        let card = try source("Components/PlayerPropsCardView.swift")
        let start = try XCTUnwrap(card.range(of: "private func rungRow("))
        let end = try XCTUnwrap(card.range(of: "private func lookupActualValue(", range: start.upperBound..<card.endIndex))
        let body = String(card[start.upperBound..<end.lowerBound])
        XCTAssertTrue(body.contains("if typeSize.isAccessibilitySize {"))
        XCTAssertTrue(body.contains("PlayerPropsScript.tickFraction("), "the pregame tick is gone")
        XCTAssertTrue(body.contains("PlayerPropsPricing.displayPercent(rung.probability)"), "#5137's rounding")
        XCTAssertTrue(body.contains(".frame(minWidth: figureColumn, alignment: .trailing)"))
    }

    func testTheFieldRowKeepsItsNameWholeAndItsTrack() throws {
        let card = try source("Components/PlayerPropsCardView.swift")
        let start = try XCTUnwrap(card.range(of: "private func fieldRow("))
        let end = try XCTUnwrap(card.range(of: "// MARK: - Unpriced ladders", range: start.upperBound..<card.endIndex))
        let body = String(card[start.upperBound..<end.lowerBound])
        XCTAssertTrue(body.contains("Text(candidate.name)"))
        XCTAssertFalse(body.contains("lineLimit(1)"), "a long name is truncated again")
        XCTAssertTrue(body.contains(".fixedSize(horizontal: false, vertical: true)"), "the name wraps")
        XCTAssertTrue(body.contains("PlayerPropsScript.tickFraction("), "the field's pregame tick is gone")
    }

    // MARK: Measured: the header grows with the text setting

    private func height(_ view: some View, width: CGFloat, at size: DynamicTypeSize) -> CGFloat {
        hostForMeasurement(view, at: size)
            .sizeThatFits(in: CGSize(width: width, height: .greatestFiniteMagnitude)).height
    }

    func testTheStatHeaderGrowsWithTheReadersTextSize() {
        let header = PropsStatGroupHeader(label: "RECEIVING YARDS", caption: nil)
        let normal = height(header, width: 330, at: .large)
        let small = height(header, width: 330, at: .xSmall)
        let large = height(header, width: 330, at: .accessibility3)
        XCTAssertGreaterThan(normal, small, "the header ignores a smaller text setting")
        XCTAssertGreaterThan(large, normal * 1.5, "the header ignores a larger text setting")
        XCTAssertGreaterThanOrEqual(normal, 14, "the header is still caption-sized at the default setting")
    }

    /// At accessibility sizes a long name wraps on its own lines instead of
    /// being clipped, and "Final N" still shows.
    func testALongStatNameWrapsRatherThanClipsAtAccessibilitySizes() throws {
        let label = "MOST RECEIVING YARDS"
        let oneLine = height(PropsStatGroupHeader(label: label, caption: nil), width: 1_000, at: .accessibility3)
        let narrow = height(PropsStatGroupHeader(label: label, caption: nil, finalText: "Final 112"),
                            width: 200, at: .accessibility3)
        XCTAssertGreaterThan(narrow, oneLine * 1.5, "the name was clipped to one line, or Final N vanished")
    }
}
