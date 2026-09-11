import XCTest
@testable import Bain_Luck

/// #4880 — every live soccer match's hero capsule read **`23' 23'`**.
///
/// ESPN serves soccer's `period` and `game_clock` as the SAME string, and six
/// call sites joined the pair with a space. This is #3273 recurring in the one
/// shape its fix could not cover: `liveBadgeLabel` strips a clock **prefix**
/// (`"5:11 - 1st Quarter"`), because that is what football sends. Soccer's period
/// does not CONTAIN the clock — it **equals** it, with no separator to find.
///
/// The old guard tested for containment-with-a-separator and never for equality,
/// which is why these tests are written against the pair rather than against a
/// single string: `liveBadgeLabel` is handed one string and cannot see the
/// collision. Only `liveStatusText` can.
final class LiveStatusTextTests: XCTestCase {

    // MARK: - The defect

    /// The three live UCL matches of 2026-09-10, measured on
    /// `GET /api/events/{id}` at 12:30pm PT. All three served `period` EQUAL to
    /// `game_clock`; all three printed it twice.
    private static let liveSoccerSpecimens = [
        (event: 15296763, period: "25'", clock: "25'"),
        (event: 15296764, period: "26'", clock: "26'"),
        (event: 15296765, period: "68'", clock: "68'"),
    ]

    func testSoccerPrintsTheMinuteExactlyOnce() {
        for specimen in Self.liveSoccerSpecimens {
            let text = PeriodLabel.liveStatusText(
                period: specimen.period, gameClock: specimen.clock)
            XCTAssertEqual(
                text, specimen.clock,
                "event \(specimen.event) must print \(specimen.clock) once, not twice")
        }
    }

    /// The regression stated as the reader sees it, so a future refactor that
    /// reintroduces the join fails on the symptom and not only on the shape.
    func testTheDoubledMinuteIsGone() {
        XCTAssertEqual(PeriodLabel.liveStatusText(period: "23'", gameClock: "23'"), "23'")
        XCTAssertNotEqual(PeriodLabel.liveStatusText(period: "23'", gameClock: "23'"), "23' 23'")
    }

    // MARK: - What must NOT change

    /// #3273's own case. The period embeds the clock with a separator, so the
    /// label shortens and BOTH halves still print — dropping the clock here
    /// would lose the only live information on the capsule.
    func testFootballKeepsItsShortenedQuarterAndItsClock() {
        XCTAssertEqual(
            PeriodLabel.liveStatusText(period: "5:11 - 1st Quarter", gameClock: "5:11"),
            "Q1 5:11")
    }

    /// **The production baseball case.** MLB serves `game_clock: null` — measured
    /// on 15308638 (Rangers at Mariners) — so the `"0:00"` guard is never reached
    /// and the nil path does the work. native/101 caught this: the old guard was
    /// written against the string values only, and nil is what is actually live.
    func testBaseballWithANilClockKeepsItsHalfInning() {
        XCTAssertEqual(
            PeriodLabel.liveStatusText(period: "Bottom 7th", gameClock: nil),
            "Bottom 7th")
    }

    /// Both meaningless-clock spellings ESPN has sent. A baseball capsule must
    /// never read `Bottom 7th 0:00`.
    func testAMeaninglessClockIsDroppedNotPrinted() {
        for clock in ["0:00", "0", "", "   "] {
            XCTAssertEqual(
                PeriodLabel.liveStatusText(period: "Bottom 7th", gameClock: clock),
                "Bottom 7th",
                "clock \(clock.debugDescription) is not a reading a person can use")
        }
    }

    /// Discover's card passes the clock alone (`EventCardView`) — the surface that
    /// was always clean, pinned so routing it through the shared rule cannot
    /// change it.
    func testAClockWithNoPeriodIsUnchanged() {
        XCTAssertEqual(PeriodLabel.liveStatusText(period: nil, gameClock: "4:21"), "4:21")
    }

    func testHockeyShortensItsPeriodAndKeepsTheClock() {
        XCTAssertEqual(
            PeriodLabel.liveStatusText(period: "2nd Period", gameClock: "12:30"),
            "P2 12:30")
    }

    // MARK: - Saying nothing

    /// `nil` means "say nothing about the clock", so each surface keeps its own
    /// fallback: the badge says `LIVE`, the watch row says nothing at all. An
    /// empty string here would print a stray separator on the nav title.
    func testNothingToSayReturnsNil() {
        XCTAssertNil(PeriodLabel.liveStatusText(period: nil, gameClock: nil))
        XCTAssertNil(PeriodLabel.liveStatusText(period: "", gameClock: ""))
        XCTAssertNil(PeriodLabel.liveStatusText(period: nil, gameClock: "0:00"))
        // A period `normalize` refuses (a leaked pre-game date string) plus no
        // clock is also nothing to say — not the raw date.
        XCTAssertNil(
            PeriodLabel.liveStatusText(period: "Wed, March 25th at 10:00 PM EDT", gameClock: nil))
    }

    /// The drop is asymmetric ON PURPOSE: `game_clock` is the field that is always
    /// a clock, where `period` is whatever ESPN chose to send. If the two ever
    /// collide in a case not seen yet, the surviving string must be the clock.
    func testTheLabelIsDroppedNeverTheClock() {
        XCTAssertEqual(PeriodLabel.liveStatusText(period: "45'", gameClock: "45'"), "45'")
        XCTAssertEqual(PeriodLabel.liveStatusText(period: "HT", gameClock: "ht"), "ht")
    }
}
