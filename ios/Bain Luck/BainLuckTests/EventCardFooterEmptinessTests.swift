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

    /// #5363 — every specimen in this file is Cardinals @ Giants or its
    /// neighbours, and the NFL prices no draw. Named rather than left to `nil`
    /// so these rows keep testing the two-way arm explicitly.
    private let twoWay = "americanfootball_nfl"
    private let soccer = "soccer_spain_la_liga"

    // MARK: - The settled card, which is the whole point

    func testSettledCardWithNoReasonHasNoFooter() {
        // What #4094 leaves on the wire for Cardinals @ Giants: reason "",
        // headline nil, game over so `isLive` false.
        XCTAssertFalse(
            Footer.hasContent(reason: "", isLive: false, awayOpening: 0.454, homeOpening: 0.546, sport: twoWay),
            "a finished card whose reason is empty must not draw a footer row"
        )
    }

    func testSettledCardWithNilReasonHasNoFooter() {
        XCTAssertFalse(
            Footer.hasContent(reason: nil, isLive: false, awayOpening: 0.454, homeOpening: 0.546, sport: twoWay)
        )
    }

    /// The opening prices are on a settled row too — they are what
    /// `preGameOddsLabel` prints up in the score line. They must NOT resurrect
    /// the footer, because "Opened X/Y" is the live strip and would double it.
    func testSettledOpeningPricesDoNotResurrectTheFooter() {
        XCTAssertFalse(
            Footer.hasContent(reason: nil, isLive: false, awayOpening: 0.4, homeOpening: 0.6, sport: twoWay)
        )
    }

    // MARK: - The other direction: everything that must still draw

    func testUpsetCardKeepsItsFooter() {
        // The one settled sentence #4094 deliberately preserves.
        XCTAssertTrue(
            Footer.hasContent(
                reason: "Won as 34% underdog", isLive: false,
                awayOpening: 0.6589, homeOpening: 0.3411, sport: twoWay
            )
        )
    }

    func testLiveCardWithBothOpeningPricesKeepsItsFooter() {
        XCTAssertTrue(
            Footer.hasContent(reason: nil, isLive: true, awayOpening: 0.45, homeOpening: 0.55, sport: twoWay),
            "the live 'Opened X/Y' strip is footer content on its own"
        )
    }

    func testLiveCardWithAReasonKeepsItsFooter() {
        XCTAssertTrue(
            Footer.hasContent(
                reason: "San Francisco Giants odds shifted 41%", isLive: true,
                awayOpening: nil, homeOpening: nil, sport: twoWay
            )
        )
    }

    func testScheduledCardWithAReasonKeepsItsFooter() {
        XCTAssertTrue(
            Footer.hasContent(reason: "Starting soon", isLive: false,
                              awayOpening: nil, homeOpening: nil, sport: twoWay)
        )
    }

    // MARK: - The mirror has to be exact

    /// `footerRow`'s "Opened X/Y" branch binds BOTH `awayProbability` and
    /// `homeProbability`, so one side alone renders nothing. If `hasContent`
    /// accepted a half-priced live row, the gap would come straight back on
    /// exactly the rows the strip cannot draw.
    func testALivePriceOnOneSideOnlyIsNotContent() {
        XCTAssertFalse(
            Footer.hasContent(reason: nil, isLive: true, awayOpening: 0.45, homeOpening: nil, sport: twoWay)
        )
        XCTAssertFalse(
            Footer.hasContent(reason: nil, isLive: true, awayOpening: nil, homeOpening: 0.55, sport: twoWay)
        )
    }

    func testLiveWithNoOpeningPricesAndNoReasonIsNotContent() {
        XCTAssertFalse(
            Footer.hasContent(reason: nil, isLive: true, awayOpening: nil, homeOpening: nil, sport: twoWay)
        )
    }

    // MARK: - #5363, where the mirror had to move

    /// A draw-priced sport draws the NAMED single-sided caption ("Opened Boca
    /// 68%"), so a live row holding only the home opening price IS content —
    /// the exact input the assertion above requires to be false on the NFL.
    ///
    /// This pair is the mirror test in both directions on one input, which is
    /// what makes it worth writing: the same arguments, two sports, opposite
    /// answers. A `hasContent` that ignored its new `sport` argument passes the
    /// two-way half and fails here.
    func testADrawPricedLiveRowWithOnlyTheHomePriceIsContent() {
        XCTAssertTrue(
            Footer.hasContent(reason: nil, isLive: true, awayOpening: nil,
                              homeOpening: 0.55, sport: soccer),
            "soccer's footer prints 'Opened <home> 55%', so home alone is content"
        )
        XCTAssertFalse(
            Footer.hasContent(reason: nil, isLive: true, awayOpening: nil,
                              homeOpening: 0.55, sport: twoWay),
            "the same row on a two-way sport still renders nothing"
        )
    }

    /// The home price is load-bearing on BOTH arms: the withheld caption is
    /// built on it, so a draw-priced row without it is as empty as any other.
    func testADrawPricedLiveRowWithNoHomePriceIsStillEmpty() {
        XCTAssertFalse(
            Footer.hasContent(reason: nil, isLive: true, awayOpening: 0.45,
                              homeOpening: nil, sport: soccer)
        )
        XCTAssertFalse(
            Footer.hasContent(reason: nil, isLive: true, awayOpening: nil,
                              homeOpening: nil, sport: soccer)
        )
    }

    /// `isLive` still gates the strip on a draw-priced sport — a settled soccer
    /// card must not acquire a footer the two-way card does not get.
    func testADrawPricedSettledRowGetsNoFooter() {
        XCTAssertFalse(
            Footer.hasContent(reason: nil, isLive: false, awayOpening: nil,
                              homeOpening: 0.55, sport: soccer)
        )
    }

    /// The exact value #4094 makes the backend return for a settled non-upset
    /// game. Deliberately `isEmpty` and not a trim: `footerRow` guards on
    /// `!reason.isEmpty`, and the mirror is only worth having while it is exact.
    func testEmptyStringIsNotAReason() {
        XCTAssertFalse(
            Footer.hasContent(reason: "", isLive: false, awayOpening: nil, homeOpening: nil, sport: twoWay)
        )
    }
}
