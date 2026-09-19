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
