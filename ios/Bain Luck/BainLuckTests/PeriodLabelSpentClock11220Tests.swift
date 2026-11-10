import XCTest
@testable import Bain_Luck

/// #11220 — a finished NBA game's title read "UTAH 100 - MIN 115 • **Final 0.0**".
/// Production serves `period: "Final"` with `game_clock: "0.0"` (event 15343949,
/// read 12:05 PM PT Tue Nov 10): basketball's clock runs out in tenths, and
/// `liveStatusText` only blanked the `"0:00"` and `"0"` spellings.
final class PeriodLabelSpentClock11220Tests: XCTestCase {

    func testAFinishedBasketballGameSaysFinalAlone() {
        XCTAssertEqual(PeriodLabel.liveStatusText(period: "Final", gameClock: "0.0"), "Final")
    }

    func testEverySpellingOfARunOutClockSaysNothing() {
        for spent in ["0", "0:00", "0.0", "0:00.0", "00:00", "0.00", " 0.0 "] {
            XCTAssertEqual(PeriodLabel.liveStatusText(period: "Final", gameClock: spent), "Final",
                           "\"\(spent)\" is a clock that has run out")
            XCTAssertNil(PeriodLabel.liveStatusText(period: nil, gameClock: spent),
                         "alone, \"\(spent)\" says nothing")
        }
    }

    func testAClockWithTimeLeftIsKept() {
        XCTAssertEqual(PeriodLabel.liveStatusText(period: "4th Quarter", gameClock: "0.4"), "Q4 0.4",
                       "four tenths left is a real clock")
        XCTAssertEqual(PeriodLabel.liveStatusText(period: "4th Quarter", gameClock: "10.0"), "Q4 10.0")
        XCTAssertEqual(PeriodLabel.liveStatusText(period: "2nd Quarter", gameClock: "5:11"), "Q2 5:11")
    }

    func testTheSpentClockRuleItself() {
        XCTAssertTrue(PeriodLabel.isSpentClock("0.0"))
        XCTAssertTrue(PeriodLabel.isSpentClock("0:00"))
        XCTAssertFalse(PeriodLabel.isSpentClock(""), "an empty clock is handled as absent, not spent")
        XCTAssertFalse(PeriodLabel.isSpentClock(":."), "no digits is not a clock")
        XCTAssertFalse(PeriodLabel.isSpentClock("0.4"))
        XCTAssertFalse(PeriodLabel.isSpentClock("10.0"))
        XCTAssertFalse(PeriodLabel.isSpentClock("25'"))
    }
}
