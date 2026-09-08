import XCTest
import SwiftUI
@testable import Bain_Luck

/// #4094 — a settled card must not pay 8pt of dead space for a footer with
/// nothing in it.
///
/// `EventCardView.footer` is an unconditional child of the body's
/// `VStack(spacing: 8)`. An `HStack` holding only a `Spacer()` is not an
/// `EmptyView`, so it still takes its turn in that stack and still draws the
/// spacing above it. Before #4094 the empty footer was a rare card; #4094 stops
/// the backend captioning finished games with "odds shifted N% during the game",
/// which makes it most of Just Happened.
///
/// `EventCardFooter.hasContent` exists to agree with the two `if` branches
/// inside `footerRow`, so every test here asserts BOTH directions: a
/// hasContent-only suite would pass just as well against `return false`, which
/// would delete the live "Opened X/Y" strip along with the gap.
final class EventCardFooterEmptinessTests: XCTestCase {

    private typealias Footer = EventCardView.EventCardFooter

    // MARK: - The settled card, which is the whole point

    func testSettledCardWithNoReasonHasNoFooter() {
        // What #4094 leaves on the wire for Cardinals @ Giants: reason "",
        // headline nil, game over so `isLive` false.
        XCTAssertFalse(
            Footer.hasContent(reason: "", isLive: false, awayOpening: 0.454, homeOpening: 0.546),
            "a finished card whose reason is empty must not draw a footer row"
        )
    }

    func testSettledCardWithNilReasonHasNoFooter() {
        XCTAssertFalse(
            Footer.hasContent(reason: nil, isLive: false, awayOpening: 0.454, homeOpening: 0.546)
        )
    }

    /// The opening prices are on a settled row too — they are what
    /// `preGameOddsLabel` prints up in the score line. They must NOT resurrect
    /// the footer, because "Opened X/Y" is the live strip and would double it.
    func testSettledOpeningPricesDoNotResurrectTheFooter() {
        XCTAssertFalse(
            Footer.hasContent(reason: nil, isLive: false, awayOpening: 0.4, homeOpening: 0.6)
        )
    }

    // MARK: - The other direction: everything that must still draw

    func testUpsetCardKeepsItsFooter() {
        // The one settled sentence #4094 deliberately preserves.
        XCTAssertTrue(
            Footer.hasContent(
                reason: "Won as 34% underdog", isLive: false,
                awayOpening: 0.6589, homeOpening: 0.3411
            )
        )
    }

    func testLiveCardWithBothOpeningPricesKeepsItsFooter() {
        XCTAssertTrue(
            Footer.hasContent(reason: nil, isLive: true, awayOpening: 0.45, homeOpening: 0.55),
            "the live 'Opened X/Y' strip is footer content on its own"
        )
    }

    func testLiveCardWithAReasonKeepsItsFooter() {
        XCTAssertTrue(
            Footer.hasContent(
                reason: "San Francisco Giants odds shifted 41%", isLive: true,
                awayOpening: nil, homeOpening: nil
            )
        )
    }

    func testScheduledCardWithAReasonKeepsItsFooter() {
        XCTAssertTrue(
            Footer.hasContent(reason: "Starting soon", isLive: false,
                              awayOpening: nil, homeOpening: nil)
        )
    }

    // MARK: - The mirror has to be exact

    /// `footerRow`'s "Opened X/Y" branch binds BOTH `awayProbability` and
    /// `homeProbability`, so one side alone renders nothing. If `hasContent`
    /// accepted a half-priced live row, the gap would come straight back on
    /// exactly the rows the strip cannot draw.
    func testALivePriceOnOneSideOnlyIsNotContent() {
        XCTAssertFalse(
            Footer.hasContent(reason: nil, isLive: true, awayOpening: 0.45, homeOpening: nil)
        )
        XCTAssertFalse(
            Footer.hasContent(reason: nil, isLive: true, awayOpening: nil, homeOpening: 0.55)
        )
    }

    func testLiveWithNoOpeningPricesAndNoReasonIsNotContent() {
        XCTAssertFalse(
            Footer.hasContent(reason: nil, isLive: true, awayOpening: nil, homeOpening: nil)
        )
    }

    /// The exact value #4094 makes the backend return for a settled non-upset
    /// game. Deliberately `isEmpty` and not a trim: `footerRow` guards on
    /// `!reason.isEmpty`, and the mirror is only worth having while it is exact.
    func testEmptyStringIsNotAReason() {
        XCTAssertFalse(
            Footer.hasContent(reason: "", isLive: false, awayOpening: nil, homeOpening: nil)
        )
    }
}
