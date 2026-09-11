import XCTest
@testable import Bain_Luck

/// #4900 — the event page's inline nav title truncated before the second score,
/// so a reader scrolled past the hero saw one team's number and not the other's.
///
/// THE FIXTURES ARE THE FOUR PHOTOGRAPHED SPECIMENS, with the strings the bar
/// actually printed quoted beside them. Every expectation below is a literal —
/// none of it is re-derived by calling the rule under test, which is the trap
/// `OddsChartAxisFitTests` fell into.
///
/// What this file can and cannot prove: the LADDER is decidable here — which
/// rungs exist, in what order, and that no rung ever drops a score. Whether a
/// given rung FITS is the bar's measurement and belongs to the screenshot on
/// the issue, because the four specimens broke between 16 and 24 characters in
/// the same title bar and no character count asserted here would agree with any
/// two of them.
final class EventNavTitleTests: XCTestCase {

    // MARK: The four photographed specimens

    /// `BODO 0 - Munich...` — 15296763, UCL, actual 0 – 0.
    func testTheBodoBayernTitleKeepsBothScoresOnEveryRung() {
        let rungs = EventNavTitle.rungs(
            away: "Bodø/Glimt", home: "Bayern Munich",
            awayScore: 0, homeScore: 0, state: "45'"
        )
        for rung in rungs.ordered {
            XCTAssertEqual(rung.awayScore, "0", rung.text)
            XCTAssertEqual(rung.homeScore, "0", rung.text)
        }
        XCTAssertEqual(rungs.compact.text, "BOD 0 - MUN 0")
    }

    /// `Sabah FK 0 - MAN...` — 15296764, UCL, actual 0 – 3. The home THREE is
    /// the number the reader lost.
    func testTheSabahUnitedTitleKeepsTheHomeThree() {
        let rungs = EventNavTitle.rungs(
            away: "Sabah FK", home: "Manchester United",
            awayScore: 0, homeScore: 3, state: "45'"
        )
        for rung in rungs.ordered {
            XCTAssertEqual(rung.homeScore, "3", rung.text)
        }
        // `MAN`, not `MUN` — the crest badge's own answer for Manchester
        // United, and the designator the photographed frame itself printed.
        // The title inherits it rather than spelling a second one.
        XCTAssertEqual(rungs.compact.text, "SAB 0 - MAN 3")
    }

    /// `Rangers 0 - Marin...` — 15308638, MLB, actual 0 – 0, Bottom 2nd. This
    /// is the specimen that isolates the STATE as sufficient on its own: the
    /// designators here are already short and already consistent, so the rung
    /// that buys width by dropping ` • Bottom 2nd` is the whole fix for it.
    func testTheRangersMarinersTitleFitsOnceTheStateIsDropped() {
        let rungs = EventNavTitle.rungs(
            away: "Texas Rangers", home: "Seattle Mariners",
            awayScore: 0, homeScore: 0, state: "Bottom 2nd"
        )
        XCTAssertEqual(rungs.withState?.text, "Rangers 0 - Mariners 0 • Bottom 2nd")
        XCTAssertEqual(rungs.labelled.text, "Rangers 0 - Mariners 0")
        XCTAssertEqual(rungs.compact.text, "RAN 0 - MAR 0")
    }

    /// `Al-Ittihad 2 - Al-Fa...` — Saudi league, actual 2 – 1, and the frame
    /// carried NO state at all. It is the proof that dropping the state alone
    /// does not fix this issue, so the compact rung has to exist.
    func testTheAlIttihadTitleTruncatesWithNoStateToDrop() {
        let rungs = EventNavTitle.rungs(
            away: "Al-Ittihad", home: "Al-Fateh",
            awayScore: 2, homeScore: 1, state: ""
        )
        XCTAssertNil(rungs.withState, "there was no state on the frame")
        XCTAssertEqual(rungs.labelled.text, "Al-Ittihad 2 - Al-Fateh 1")
        XCTAssertTrue(
            rungs.compact.text.count < rungs.labelled.text.count,
            "the floor must be narrower than the rung above it or it buys nothing: "
                + rungs.compact.text
        )
        XCTAssertEqual(rungs.compact.awayScore, "2")
        XCTAssertEqual(rungs.compact.homeScore, "1")
    }

    // MARK: The ladder's shape

    func testTheStateRungIsFirstAndIsTheOnlyRungCarryingState() {
        let rungs = EventNavTitle.rungs(
            away: "Texas Rangers", home: "Seattle Mariners",
            awayScore: 4, homeScore: 7, state: "Bottom 2nd"
        )
        XCTAssertEqual(rungs.ordered.first, rungs.withState)
        XCTAssertEqual(rungs.ordered.filter { !$0.state.isEmpty }.count, 1)
    }

    func testAWhitespaceOnlyStateIsNotARung() {
        let rungs = EventNavTitle.rungs(
            away: "Texas Rangers", home: "Seattle Mariners",
            awayScore: 0, homeScore: 0, state: "   "
        )
        XCTAssertNil(rungs.withState)
        XCTAssertEqual(rungs.ordered.count, 2)
    }

    /// A served pair that is already a code is both the label and the floor;
    /// `ordered` must not print the same title twice.
    func testAnIdenticalFloorIsNotRepeated() {
        let rungs = EventNavTitle.rungs(
            away: "Los Angeles Rams", home: "San Francisco 49ers",
            awayScore: 7, homeScore: 3,
            awayServed: "LAR", homeServed: "SF"
        )
        XCTAssertEqual(rungs.labelled.text, "LAR 7 - SF 3")
        XCTAssertEqual(rungs.compact, rungs.labelled)
        XCTAssertEqual(rungs.ordered.count, 1)
    }

    /// Widest first is the contract `ViewThatFits` is handed; a ladder that is
    /// not monotonic would have it stop on a rung wider than one below it.
    func testTheLadderNeverWidens() {
        let rungs = EventNavTitle.rungs(
            away: "Bodø/Glimt", home: "Bayern Munich",
            awayScore: 0, homeScore: 5, state: "FT"
        )
        let widths = rungs.ordered.map(\.text.count)
        XCTAssertEqual(widths, widths.sorted(by: >), "\(rungs.ordered.map(\.text))")
    }

    /// #3430's rule reaches the title through this type, not around it: two
    /// sides of one matchup never print the same label.
    func testTheClemsonLSUTitleStillNamesBothSides() {
        let rungs = EventNavTitle.rungs(
            away: "Clemson Tigers", home: "LSU Tigers",
            awayScore: 10, homeScore: 51, state: "FT"
        )
        XCTAssertEqual(rungs.labelled.text, "Clemson Tigers 10 - LSU Tigers 51")
        XCTAssertEqual(rungs.compact.text, "CLE 10 - LSU 51")
    }

    // MARK: Pre-game

    func testAScorelessTitleIsTheMatchup() {
        XCTAssertEqual(
            EventNavTitle.scoreless(away: "Texas Rangers", home: "Seattle Mariners"),
            "Rangers vs Mariners"
        )
    }
}
