import XCTest
import SwiftUI

@testable import Bain_Luck

/// #8144 — the Discover game card's status column is sized to its own ink and
/// reflows when it no longer fits, instead of being pinned at 50pt.
///
/// ## Why half of this file reads the SOURCE
///
/// `GameCardStatusColumn` takes `availableWidth` as a parameter, so the defect
/// this ship repairs — a hardcoded width at the call site — **cannot be written
/// inside the model at all.** No test of the model alone could fail on the old
/// behaviour, which is the trap native/n304 walked into on #7547: a pure helper
/// extracted from a defective call site does not inherit the defect's guard.
///
/// So the model tests below pin the RULE, and the source guards pin the WIRING:
/// the literal is gone, the model is called, the hero measures itself, and the
/// label is drawn in the face the model measures. Sever any one of those and the
/// model is still perfectly correct and completely inert.
final class TheInningColumnIsMeasuredNotPinned8144Tests: XCTestCase {

    // Hero content width = screen − 32 (the feed's `.padding(.horizontal)`)
    // − 28 (`heroContent.padding(14)`). Asserted against those numbers in
    // `testTheHeroWidthsThisFileReasonsAboutMatchTheCardsOwnPadding`.
    private let narrowPhoneHero: Double = 315   // 375pt
    private let widePhoneHero: Double = 380     // 440pt

    /// The literal this ship deletes. Named once, so a test that still mentions
    /// it is obviously about the old behaviour.
    private let theOldLiteral: Double = 50

    // MARK: - The rule

    /// The anti-literal assertion, in BOTH directions — which is the whole point
    /// of measuring. A replacement literal could satisfy one of these; only ink
    /// satisfies both.
    func testTheDefaultSizeColumnIsTheInkAndNotFiftyPoints() {
        let long = GameCardStatusColumn.layout(
            statusText: "Bottom 6th", isLive: true, scores: ["4", "2"],
            availableWidth: narrowPhoneHero, typeSize: .large)
        let short = GameCardStatusColumn.layout(
            statusText: "Q3", isLive: true, scores: ["21", "17"],
            availableWidth: narrowPhoneHero, typeSize: .large)

        guard case let .inline(longWidth) = long, case let .inline(shortWidth) = short else {
            return XCTFail("both fit between the crests at the default size: \(long) / \(short)")
        }

        XCTAssertGreaterThan(
            longWidth, theOldLiteral,
            """
            `Bottom 6th` is 65.2pt of ink in the face this card draws. The 50pt \
            box was over-run at the DEFAULT text size, which is why it has always \
            wrapped to two lines — the accessibility report is the same defect \
            further along its curve, not a separate one.
            """)
        XCTAssertLessThan(
            shortWidth, theOldLiteral,
            """
            `Q3` is 16.5pt. Sizing to ink has to hand width BACK on a short \
            period as well as take it for a long one, or it is just a bigger \
            literal.
            """)
    }

    /// The reason the trigger is measured rather than declared: it lands on a
    /// different text size on each phone, for the same string.
    func testTheSamePeriodStacksOnTheNarrowPhoneWhileTheWideOneStillFitsIt() {
        let narrow = GameCardStatusColumn.layout(
            statusText: "Bottom 6th", isLive: true, scores: ["4", "2"],
            availableWidth: narrowPhoneHero, typeSize: .accessibility1)
        let wide = GameCardStatusColumn.layout(
            statusText: "Bottom 6th", isLive: true, scores: ["4", "2"],
            availableWidth: widePhoneHero, typeSize: .accessibility1)

        XCTAssertEqual(
            narrow, .stacked,
            "111.4pt of ink is over the 105pt a third of a 375pt phone's hero comes to")
        guard case .inline = wide else {
            return XCTFail(
                "a 440pt phone's third is 126.7pt and still holds it inline, got \(wide)")
        }
    }

    /// The bound that the obvious model does not have, on the ordinary specimen.
    ///
    /// A baseball card's scores are single digits, so the team floor never rises
    /// above the avatar and "does it fit beside the crests" answers YES all the
    /// way up: at a11y3 the status would draw itself 160pt wide in a 315pt hero.
    /// Nothing is truncated and nothing overlaps — it is simply the wrong shape,
    /// and the acceptance criteria this ship is written against would have been
    /// satisfied by it. Only the share bound refuses.
    func testAPeriodWiderThanEitherCrestStacksEvenThoughItWouldHaveFit() {
        let scores = ["4", "2"]
        let size = DynamicTypeSize.accessibility3

        // Bound 1 alone is not binding here — this is the premise, asserted, so
        // the test cannot quietly become a second copy of the one above.
        let floor = GameCardStatusColumn.teamColumnFloor(scores: scores, typeSize: size)
        XCTAssertEqual(floor, GameCardStatusColumn.avatarWidth, accuracy: 0.01)
        let ink = GameCardStatusColumn.statusWidth("Bottom 6th", isLive: true, typeSize: size)
        XCTAssertLessThan(
            ink, narrowPhoneHero - floor * 2,
            "premise: the crests leave room for this string, so bound 1 would allow it")
        XCTAssertGreaterThan(
            ink, narrowPhoneHero * GameCardStatusColumn.maximumInlineStatusShare,
            "premise: and it is over a third of the row, so bound 2 should refuse it")

        XCTAssertEqual(
            GameCardStatusColumn.layout(
                statusText: "Bottom 6th", isLive: true, scores: scores,
                availableWidth: narrowPhoneHero, typeSize: size),
            .stacked,
            "the period is wider than either crest; equal thirds is the limit")
    }

    /// And the mirror case, so BOTH bounds have a specimen only they refuse.
    ///
    /// A basketball game at 104–98 reading `LIVE` at a11y5: the string is short
    /// enough to be well inside a third of the row, and the thing that has no room
    /// for it is the pair of three-digit scores either side. Delete the team floor
    /// and the share bound alone says inline — over the top of both scores.
    func testAShortStatusStacksWhenTheScoresThemselvesLeaveNoRoom() {
        let scores = ["104", "98"]
        let size = DynamicTypeSize.accessibility5

        let ink = GameCardStatusColumn.statusWidth("LIVE", isLive: true, typeSize: size)
            + GameCardStatusColumn.inkSlack
        XCTAssertLessThan(
            ink, narrowPhoneHero * GameCardStatusColumn.maximumInlineStatusShare,
            "premise: `LIVE` is well under a third of the row, so bound 2 would allow it")
        XCTAssertGreaterThan(
            ink, narrowPhoneHero
                - GameCardStatusColumn.teamColumnFloor(scores: scores, typeSize: size) * 2,
            "premise: and two 116.7pt scores leave less than that, so bound 1 should refuse")

        XCTAssertEqual(
            GameCardStatusColumn.layout(
                statusText: "LIVE", isLive: true, scores: scores,
                availableWidth: narrowPhoneHero, typeSize: size),
            .stacked,
            "the scores are the thing with no room; the status yields to them")
    }

    /// And the share is a proportion, so it says the same thing about any row.
    func testTheShareBoundIsAProportionAndNotAPointCountInDisguise() {
        XCTAssertEqual(GameCardStatusColumn.maximumInlineStatusShare, 1.0 / 3.0, accuracy: 0.0001)
        for hero in [280.0, 315.0, 380.0, 700.0] {
            let atTheLimit = hero * GameCardStatusColumn.maximumInlineStatusShare
            XCTAssertEqual(
                atTheLimit, (hero - atTheLimit) / 2, accuracy: 0.01,
                "at the limit the status and each team column are the same width")
        }
    }

    /// And on a different text size for each string, on the SAME phone. A
    /// declared `dynamicTypeSize >= .accessibility1` would stack this one.
    func testAShortPeriodStaysBetweenTheCrestsEvenAtTheLargestSize() {
        let layout = GameCardStatusColumn.layout(
            statusText: "Q3", isLive: true, scores: ["21", "17"],
            availableWidth: narrowPhoneHero, typeSize: .accessibility5)

        guard case let .inline(width) = layout else {
            return XCTFail("`Q3` is 58.1pt at a11y5 against an 81.6pt budget — inline, got \(layout)")
        }
        XCTAssertGreaterThan(width, theOldLiteral, "and it needs MORE than the old box to do it")
    }

    /// The floor the status yields to is the team column's own content, and past
    /// the default sizes that is the SCORE rather than the avatar.
    func testTheTeamFloorIsTheAvatarUntilTheScoreOutgrowsIt() {
        XCTAssertEqual(
            GameCardStatusColumn.teamColumnFloor(scores: ["104", "98"], typeSize: .large),
            GameCardStatusColumn.avatarWidth, accuracy: 0.01,
            "`104` is 45.5pt at .large — under the 52pt avatar, so the avatar is the floor")

        XCTAssertGreaterThan(
            GameCardStatusColumn.teamColumnFloor(scores: ["104", "98"], typeSize: .accessibility5),
            GameCardStatusColumn.avatarWidth,
            "`104` is 116.7pt at a11y5 — a floor that stayed 52 would let the status eat the score")
    }

    func testAScheduledGameWithNoScoreFloorsOnTheAvatarAlone() {
        XCTAssertEqual(
            GameCardStatusColumn.teamColumnFloor(scores: [], typeSize: .accessibility5),
            GameCardStatusColumn.avatarWidth, accuracy: 0.01)
    }

    /// The team NAME is deliberately not part of the floor. If it were, every
    /// card would stack at every accessibility size and the measurement would be
    /// decoration on a declared threshold.
    func testTheTeamNameIsNotChargedToTheFloor() {
        let withLongNames = GameCardStatusColumn.layout(
            statusText: "Q3", isLive: true, scores: [],
            availableWidth: narrowPhoneHero, typeSize: .accessibility5)
        guard case .inline = withLongNames else {
            return XCTFail("`Chicago Cubs` is 279.1pt at a11y5; charging it would stack this, got \(withLongNames)")
        }
    }

    /// Before the first `GeometryReader` pass there is no width to reason about.
    func testAnUnmeasuredHeroDrawsTheShapeTheCardHasAlwaysDrawn() {
        let layout = GameCardStatusColumn.layout(
            statusText: "Bottom 6th", isLive: true, scores: ["4", "2"],
            availableWidth: 0, typeSize: .large)
        guard case .inline = layout else {
            return XCTFail("an unmeasured first frame must not flash a reflow it then undoes, got \(layout)")
        }
    }

    /// The promise the doc comment makes, asserted rather than trusted.
    ///
    /// `EventSourceLabelColumn` wrote exactly this promise about its own column
    /// ("a long label takes two lines; it does not truncate"), and #4233 found it
    /// false at a11y3 — two sizes below where its own issue title said. A
    /// measured promise that nothing re-measures is a comment.
    func testEveryStatusStringThisCardCanDrawFitsItsStackedLine() {
        let live = ["Q3", "Top 9th", "Bottom 6th", "End 5th", "Halftime",
                    "LIVE", "2nd Half", "1st Period", "End of 3rd"]
        let staticStrings = ["vs", "Final", "Paused", "104 - 98", "3 - 2"]
        let sizes: [DynamicTypeSize] = [
            .large, .xLarge, .xxLarge, .xxxLarge, .accessibility1,
            .accessibility2, .accessibility3, .accessibility4, .accessibility5,
        ]

        var offenders: [String] = []
        for size in sizes {
            for (strings, isLive) in [(live, true), (staticStrings, false)] {
                for string in strings {
                    let lines = GameCardStatusColumn.statusLineCount(
                        string, isLive: isLive, width: narrowPhoneHero, typeSize: size)
                    if lines > GameCardStatusColumn.maximumStackedStatusLines {
                        offenders.append("\(string) at \(size) = \(lines) lines")
                    }
                }
            }
        }
        XCTAssertTrue(offenders.isEmpty, "stacked strings over the line budget: \(offenders)")
    }

    /// The widths this file reasons about are the card's own padding, not two
    /// numbers that happen to agree with it.
    func testTheHeroWidthsThisFileReasonsAboutMatchTheCardsOwnPadding() throws {
        let card = try Self.source("Components/DiscoverEventCard.swift")
        XCTAssertTrue(
            card.contains(".padding(14)"),
            "the hero's own padding moved; the 315/380 widths above are now fiction")
        XCTAssertEqual(narrowPhoneHero, 375 - 32 - 28, accuracy: 0.01)
        XCTAssertEqual(widePhoneHero, 440 - 32 - 28, accuracy: 0.01)
    }

    // MARK: - The wiring, which no test of the model can see

    private static func source(_ relativePath: String) throws -> String {
        let here = URL(fileURLWithPath: #filePath)
        let appRoot = here
            .deletingLastPathComponent()   // BainLuckTests
            .deletingLastPathComponent()   // Bain Luck (project dir)
            .appendingPathComponent("Bain Luck")
        return try String(
            contentsOf: appRoot.appendingPathComponent(relativePath), encoding: .utf8)
    }

    /// Comments are where this file's own subject is DESCRIBED, at length. A
    /// guard that scanned them would pass on a card whose code had been reverted
    /// and whose comments still explained the fix.
    private static func strippedSource(_ relativePath: String) throws -> String {
        try source(relativePath)
            .components(separatedBy: .newlines)
            .filter { !$0.trimmingCharacters(in: .whitespaces).hasPrefix("//") }
            .joined(separator: "\n")
    }

    /// Anti-vacuity: the strip has to remove the prose AND leave the code. A
    /// stripper that returned "" would make every guard below pass.
    func testTheCommentStripLeavesRealCodeStanding() throws {
        let stripped = try Self.strippedSource("Components/DiscoverEventCard.swift")
        XCTAssertTrue(
            stripped.contains("struct NativeEventDiscoverCard: View {"),
            "the strip ate the code; every needle below would then be vacuous")
        XCTAssertFalse(
            stripped.contains("#8144 — the status column between the crests is sized"),
            "the strip left doc comments in, so a needle could match prose about the fix")
        XCTAssertFalse(
            stripped.contains("sized for \"Q3\""),
            "the stale live/048 claim is comment text and must not be matched as code")
    }

    func testTheFixedWidthStatusColumnIsGoneFromTheCard() throws {
        let stripped = try Self.strippedSource("Components/DiscoverEventCard.swift")
        XCTAssertFalse(
            stripped.contains(".frame(width: 50)"),
            """
            `.frame(width: 50)` is back on the status column. That literal is the \
            whole of #8144: it was chosen for `Q3` and `Bottom 6th` over-runs it \
            at the DEFAULT text size.
            """)
    }

    func testTheCardAsksTheModelWhereTheStatusGoes() throws {
        let stripped = try Self.strippedSource("Components/DiscoverEventCard.swift")
        XCTAssertTrue(
            stripped.contains("GameCardStatusColumn.layout("),
            "the model is not called, so its correctness is inert")
        XCTAssertTrue(
            stripped.contains("statusLayout == .stacked"),
            "the card never draws the reflowed arm, so the model can only ever say inline")
        XCTAssertTrue(
            stripped.contains("case let .inline(statusWidth)"),
            "the card never reads the measured width, so it is drawing some other number")
    }

    /// The two inputs the model cannot get for itself. Delete either and the
    /// model still answers — with a width for a hero of 0pt, or for the app's
    /// text size instead of this view's.
    func testTheCardMeasuresItsOwnHeroAndReadsItsOwnTextSize() throws {
        let stripped = try Self.strippedSource("Components/DiscoverEventCard.swift")
        for needle in [
            "@Environment(\\.dynamicTypeSize) private var dynamicTypeSize",
            "GeometryReader { geo in",
            "key: HeroContentWidthKey.self",
            ".onPreferenceChange(HeroContentWidthKey.self)",
            "heroContentWidth = width",
            "availableWidth: heroContentWidth",
            "typeSize: dynamicTypeSize",
        ] {
            XCTAssertTrue(
                stripped.contains(needle),
                "the measurement wiring is cut at `\(needle)` — the model goes inert, silently")
        }
    }

    /// #4107's trap from the other direction: a model that sizes a column
    /// against a font the view does not draw.
    func testTheLabelIsDrawnInTheFaceTheModelMeasures() throws {
        let stripped = try Self.strippedSource("Components/DiscoverEventCard.swift")
        XCTAssertTrue(
            stripped.contains(
                ".font((isLive ? Font.caption2 : Font.footnote).weight(.heavy).monospacedDigit())"),
            """
            The drawn face changed. `GameCardStatusColumn.statusFont` measures \
            caption2/footnote + heavy + monospacedDigit; if the view draws \
            anything else the column is sized against a string nothing renders.
            """)

        let model = try Self.strippedSource("Utilities/GameCardStatusColumn.swift")
        for needle in ["isLive ? .caption2 : .footnote", "weight: .heavy",
                       "monospacedDigitSystemFont"] {
            XCTAssertTrue(model.contains(needle), "the model stopped measuring `\(needle)`")
        }
    }

    /// One label, one face, wherever the row puts it.
    func testTheStatusIsDrawnFromOneLabelRatherThanTwoCopies() throws {
        let stripped = try Self.strippedSource("Components/DiscoverEventCard.swift")
        let occurrences = stripped.components(separatedBy: "Text(statusText)").count - 1
        XCTAssertEqual(
            occurrences, 1,
            """
            `Text(statusText)` occurs \(occurrences) times. Two copies are two \
            faces the first time either is edited, and the model measures one of \
            them. #8097/#8109 both shipped a needle that occurred twice so a \
            half-revert stayed green; this asserts the count.
            """)
    }
}
