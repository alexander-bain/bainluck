import XCTest
@testable import Bain_Luck

/// #6574 — the badge above the score on a FINISHED game read **"Final · Final"**.
///
/// Photographed on the simulator against production data, 2026-09-16, walking
/// the phone journey on event 14638896 (Broncos 10 – Chiefs 31, MNF, Final):
/// `artifacts/native-192/04-mnf-250.png`, the pill immediately under the
/// win-probability chart. The served payload is the whole explanation — the last
/// `espn_history` row of that game is
/// `{"game_clock": "Final", "period": "Final"}` — and `GamePlayPoint.timeDisplay`
/// joined the two with `" · "`.
///
/// **THIS IS #4880 IN ITS FOURTH CALL SITE, NOT A NEW CLASS.** Soccer's
/// `23' 23'` was the same collision (`period` EQUAL to `game_clock`, no
/// separator to strip), and `PeriodLabel.liveStatusText` was written then as the
/// one place allowed to print the pair, precisely because it is the only thing
/// handed BOTH strings. This card never went through it: #3273 pointed the card
/// at the shared PARSER and left the JOIN in the view.
///
/// **WHY THE GUARD DID NOT CATCH IT.** `periodLabelSingleSource.test.ts`
/// discovers the join by scanning for an array literal naming `period` and
/// `gameClock`. `EventDetailView` copies the pair into a view struct as
/// `period` / **`clock`**, so the identifier `gameClock` does not appear in
/// `GamePlayCardView.swift` at all and the scan read it as clean. The widened
/// tell ships with this fix; these cases are its Swift-side half — the scan can
/// only prove the join is gone, not that what replaced it is right.
final class GamePlayCardTimeDisplayTests: XCTestCase {

    private func display(period: String?, clock: String?) -> String {
        GamePlayPoint(
            timestamp: "2026-09-15T03:16:00+00:00",
            homeProb: 1.0,
            awayProb: 0.0,
            homeScore: 31,
            awayScore: 10,
            period: period,
            clock: clock
        ).timeDisplay
    }

    /// THE DEFECT. The specimen, verbatim from the served row.
    func testSettledRowPrintsFinalOnce() {
        XCTAssertEqual(display(period: "Final", clock: "Final"), "Final")
    }

    /// Case is not a second word. ESPN has sent both spellings of this state.
    func testCollisionIsCaseInsensitive() {
        XCTAssertEqual(display(period: "Final", clock: "FINAL"), "FINAL")
    }

    /// #4880's own shape, reaching this card for the first time: soccer serves
    /// the period and the clock as the same string with no separator.
    func testSoccerMinutePrintsOnce() {
        XCTAssertEqual(display(period: "25'", clock: "25'"), "25'")
    }

    /// THE OTHER DIRECTION, and the one that makes the test worth having: a
    /// clock that says something the period does not must still be printed. A
    /// fix that simply dropped the clock would pass every assertion above and
    /// silently delete the game clock from every live game.
    func testLiveFootballKeepsBothWhenTheyDiffer() {
        // #3273's shape: the period EMBEDS the clock, so the label is stripped
        // to the quarter and the clock is printed beside it exactly once.
        XCTAssertEqual(display(period: "5:13 - 4th Quarter", clock: "5:13"), "Q4 5:13")
        XCTAssertEqual(display(period: "1st Quarter", clock: "14:54"), "Q1 14:54")
    }

    /// Baseball has no clock, and production serves `game_clock: null` there.
    /// The half-inning is what the reader needs, and it survives alone.
    func testBaseballKeepsTheHalfInningWithNoClock() {
        XCTAssertEqual(display(period: "Bottom 7th", clock: nil), "Bottom 7th")
    }

    /// An empty display is the card's cue to draw no badge at all
    /// (`if !point.timeDisplay.isEmpty`), so "nothing to say" must stay "".
    func testNothingToSayYieldsNoBadge() {
        XCTAssertEqual(display(period: nil, clock: nil), "")
        XCTAssertEqual(display(period: "", clock: ""), "")
    }

    /// A clock reading zero is not a clock. Dropping it here is `liveStatusText`'s
    /// rule, and this pins that the card inherits it rather than printing
    /// "Q4 0:00" under a settled score.
    func testZeroClockIsNotPrinted() {
        XCTAssertEqual(display(period: "4th Quarter", clock: "0:00"), "Q4")
    }
}
