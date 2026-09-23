import XCTest
@testable import Bain_Luck

/// #7074 — THE DISCOVER FUTURES CARD DREW ITS OWN HEADER OFF ITS OWN PHOTOGRAPH.
///
/// The hero was a `ZStack(alignment: .bottomLeading)` holding two children with
/// independent heights: a backdrop pinned at `frame(height: 170)`, and an
/// overlay — the category and Trending pills, a 52pt `@ScaledMetric` numeral and
/// a leader name of up to three lines inside 14pt padding — that is free to be
/// taller. A `ZStack` takes its tallest child, so whenever the overlay won, the
/// difference came out of the TOP: a white band inside the card above the photo,
/// the two pills drawn on it in white-on-white, and the photograph's square top
/// corners sitting in the middle of a rounded card.
///
/// MEASURED on master `7980bbbdc`, iPhone 17 Pro, anonymous feed, the market
/// "Xi Jinping out before 2027?" — the same archetype as the bank-failure card
/// in Alex's `group-overlap.png`:
///
/// | Dynamic Type | artifact | card top → photo top |
/// |---|---|---|
/// | default (`large`) | `artifacts/native-239/BEFORE-discover-s2800.png` | y 1316 → 1339 = **23px @3x = 7.7pt** |
/// | `extra-extra-extra-large` | `artifacts/native-239/BEFORE-xxxl-s2800.png` | y 2235 → 2333 = **98px @3x = 32.7pt** |
///
/// It scales with the reader's text size, which is why Alex's phone lost most of
/// both pills to it and the default-size simulator lost a sliver. The fix makes
/// the backdrop the content's BACKGROUND, so there is one height instead of two,
/// and 170 becomes a floor.
///
/// ## Why a source scan and not a layout assertion
///
/// The defect is not a number, it is a SHAPE: two siblings whose heights are
/// allowed to disagree. No arithmetic can be written for it that is not a model
/// of SwiftUI's layout — the thing `DiscoverMasonry`'s doc comment calls "a table
/// of numbers nobody measured". What can be pinned exactly is that the hero no
/// longer expresses its height twice. The rendered proof is the frame pair
/// above and its AFTER twin; this file is the regression guard that stops the
/// fixed-height sibling coming back.
final class TheHeroBackdropIsAFloorNotAHeight7074Tests: XCTestCase {

    private func source(_ folder: String, _ file: String) throws -> String {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()   // BainLuckTests
            .deletingLastPathComponent()   // Bain Luck (project dir)
            .appendingPathComponent("Bain Luck")
            .appendingPathComponent(folder)
            .appendingPathComponent(file)
        return try PredictionsExperienceIsGatedEverywhere6501Tests
            .stripped(String(contentsOf: url, encoding: .utf8))
    }

    private func card() throws -> String {
        try source("Components", "DiscoverFuturesCard.swift")
    }

    /// The second instance of the same shape, found by reading the sibling while
    /// fixing the card: the futures DETAIL page's hero, `frame(height: 220)`
    /// under an overlay that can carry a RESOLVED badge and a winner row the
    /// card has no equivalent of.
    private func detail() throws -> String {
        try source("Views", "FuturesDetailView.swift")
    }

    /// Anti-vacuity: without this, every assertion below passes on "".
    func testTheScanReadsTheCard() throws {
        XCTAssertTrue(
            try card().contains("structNativeFuturesDiscoverCard:View"),
            "the scan is not reading DiscoverFuturesCard.swift"
        )
    }

    /// The floor is still 170 — a card that was short before must not have
    /// changed height. The fix was about the tall case; a regression that
    /// shrank every hero would be a new defect wearing the fix's name.
    func testTheHeroFloorIsUnchangedAtTheHeightTheCardAlwaysDrew() {
        XCTAssertEqual(FuturesHero.discoverCardMinimumHeight, 170)
    }

    /// The card reads the floor as a MINIMUM.
    func testTheCardAsksForAMinimumHeightAndNotAHeight() throws {
        XCTAssertTrue(
            try card().contains("minHeight:FuturesHero.discoverCardMinimumHeight"),
            """
            the hero no longer asks for `minHeight: FuturesHero.discoverCardMinimumHeight`. \
            A fixed height here is the defect: the overlay can exceed it, and \
            what exceeds it is drawn outside the photograph.
            """
        )
    }

    /// The backdrop is the content's background, so it cannot have a height of
    /// its own to disagree with.
    func testTheBackdropIsTheContentsBackground() throws {
        let code = try card()
        XCTAssertTrue(
            code.contains(".background{heroBackground}"),
            "the backdrop is not drawn as the hero content's background"
        )
        XCTAssertFalse(
            code.contains("heroBackground.frame(height:"),
            """
            the backdrop is a fixed-height view again. That is exactly the \
            shape #7074 was: a 170pt photograph underneath an overlay that is \
            free to be taller, with the overflow landing on the card's own \
            white background.
            """
        )
    }

    // MARK: - The same shape on the futures detail page

    func testTheScanReadsTheDetailPage() throws {
        XCTAssertTrue(
            try detail().contains("structFuturesDetailView:View"),
            "the scan is not reading FuturesDetailView.swift"
        )
    }

    func testTheDetailPageFloorIsUnchangedAtTheHeightItAlwaysDrew() {
        XCTAssertEqual(FuturesHero.detailPageMinimumHeight, 220)
    }

    /// Both heroes, one rule. A fix applied to the card and not to the page it
    /// opens is half a fix on the same reader's journey.
    func testTheDetailHeroIsAFloorToo() throws {
        let code = try detail()
        XCTAssertTrue(
            code.contains("minHeight:FuturesHero.detailPageMinimumHeight"),
            "the detail hero does not read the floor as a minimum"
        )
        XCTAssertTrue(
            code.contains(".background{heroBackground(market:market)}"),
            "the detail backdrop is not drawn as its content's background"
        )
        XCTAssertFalse(
            code.contains("heroBackground(market:market).frame(height:"),
            """
            the detail hero's backdrop is a fixed-height sibling again — the \
            #7074 shape, with a 220pt floor instead of 170.
            """
        )
    }

    // MARK: - The THIRD hero (#2095): the Discover GAME card
    //
    // #7074 fixed two heroes and there were three. #2095's acceptance asks for
    // the chip to be checked on every card kind that carries one, and the kind
    // nobody had photographed was the game card:
    //
    //     ZStack { gradient; VStack { chip row; Spacer; matchup } .padding(14) }
    //         .frame(height: 160)
    //         .clipShape(…)
    //
    // Same two-heights shape, different symptom. Here the fixed height is on
    // the ZStack and a `clipShape` follows it, so the surplus is not spilled
    // onto the card's white body — it is CUT OFF. MEASURED on master
    // `5e9cc2d5f`, iPhone 17 Pro, the live "Miami Marlins @ Chicago Cubs" card:
    // the hero drew 160.0pt at `large`, at `extra-extra-extra-large` AND at
    // `accessibility-extra-extra-extra-large`, and at that last size the `MLB`
    // chip and the `• LIVE` badge were not on screen at all. Frames:
    // `artifacts/native-301/`.

    private func eventCard() throws -> String {
        try source("Components", "DiscoverEventCard.swift")
    }

    /// Anti-vacuity: without this, every assertion below passes on "".
    func testTheScanReadsTheEventCard2095() throws {
        XCTAssertTrue(
            try eventCard().contains("structNativeEventDiscoverCard:View"),
            "the scan is not reading DiscoverEventCard.swift"
        )
    }

    /// The floor is the height the game card always drew.
    func testTheEventHeroFloorIsUnchangedAtTheHeightItAlwaysDrew2095() {
        XCTAssertEqual(EventHero.discoverCardMinimumHeight, 160)
    }

    /// Three heroes, one rule.
    func testTheEventHeroIsAFloorToo2095() throws {
        let code = try eventCard()
        XCTAssertTrue(
            code.contains("minHeight:EventHero.discoverCardMinimumHeight"),
            "the game card's hero does not read the floor as a minimum"
        )
        XCTAssertTrue(
            code.contains(".background{heroBackground}"),
            "the game card's backdrop is not drawn as its content's background"
        )
        XCTAssertFalse(
            code.contains(".frame(height:160)"),
            """
            the game card's hero is a fixed height again — the #7074 shape with \
            a clip in front of it, which does not misplace the category chip, \
            it deletes it (#2095).
            """
        )
    }

    /// The chip row and the matchup are still separated by the spacer that
    /// SPENDS the floor. Without it the floor would pad the bottom instead of
    /// holding the matchup down, and every game card would change shape at the
    /// default text size — a different defect wearing this fix's name.
    func testTheEventHeroStillSpendsItsFloorOnTheMatchup2095() throws {
        XCTAssertTrue(
            try eventCard().contains("Spacer(minLength:10)"),
            "the game hero's spacer is gone, so the floor no longer positions the matchup"
        )
    }

    /// The needles must be able to say NO. The pre-fix text contains the
    /// forbidden shape and none of the three required ones.
    func testTheEventScanWouldCatchTheOriginalShape2095() {
        let original = PredictionsExperienceIsGatedEverywhere6501Tests.stripped("""
        ZStack {
            LinearGradient(colors: [gradient.0, gradient.1],
                           startPoint: .topLeading, endPoint: .bottomTrailing)
            VStack(spacing: 0) { Text(sportLabel); Spacer(minLength: 10) }
                .padding(14)
        }
        .frame(height: 160)
        .clipShape(UnevenRoundedRectangle(topLeadingRadius: 18, topTrailingRadius: 18))
        """)
        XCTAssertTrue(
            original.contains(".frame(height:160)"),
            "the needle does not match the code it is meant to forbid"
        )
        XCTAssertFalse(
            original.contains("minHeight:EventHero.discoverCardMinimumHeight"),
            "the floor needle matches the pre-fix shape, so its presence proves nothing"
        )
        XCTAssertFalse(
            original.contains(".background{heroBackground}"),
            "the background needle matches the pre-fix shape, so its presence proves nothing"
        )
    }

    /// 🪤 #8097's trap, checked rather than assumed (n300): a `contains` needle
    /// that occurs TWICE stays green on a half-revert. Each needle this file
    /// asserts PRESENT must occur exactly once in the file it scans, or
    /// reverting one of the two sites leaves the scan satisfied by the other.
    func testEachEventNeedleOccursExactlyOnce2095() throws {
        let code = try eventCard()
        for needle in [
            "minHeight:EventHero.discoverCardMinimumHeight",
            ".background{heroBackground}",
            "Spacer(minLength:10)",
        ] {
            XCTAssertEqual(
                code.components(separatedBy: needle).count - 1, 1,
                "`\(needle)` does not occur exactly once — a count of 2 means a "
                + "revert of one site leaves this scan green on the defect"
            )
        }
    }

    /// The scan must be able to say NO, or "does not contain" is worthless.
    func testTheScanWouldCatchTheOriginalShape() {
        let original = PredictionsExperienceIsGatedEverywhere6501Tests.stripped("""
        ZStack(alignment: .bottomLeading) {
            heroBackground
                .frame(height: 170)
                .clipped()
            VStack { Text("x") }
        }
        """)
        XCTAssertTrue(
            original.contains("heroBackground.frame(height:"),
            "the needle does not match the code it is meant to forbid"
        )
        XCTAssertFalse(
            original.contains("minHeight:FuturesHero.discoverCardMinimumHeight"),
            "the needle matches the pre-fix shape, so its presence proves nothing"
        )
    }
}
