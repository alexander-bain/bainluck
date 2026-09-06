import XCTest
@testable import Bain_Luck

/// native/013 — the event page must speak the unit the match is played in.
///
/// Measured on the live Pegula–Fernandez US Open match (event 15301138,
/// 2026-09-04 17:20–17:27Z, `tennis_wta_us_open`, 1–1 in sets). The phone drew,
/// on one screen:
///
/// * a hero reading `Proj. 13-13` — the books' GAME projection, unlabelled,
///   two lines under a 1–1 SET score;
/// * "Score Differential" with an "Actual Score Diff" line that was the SET
///   difference (0, −1, 0) stepped across the same ±6 axis as the GAME spread;
/// * a margin rail labelled "Fernandez by 18+ … Pegula by 18+" — basketball's
///   range, on a sport whose quoted spread is ±4.5 games;
/// * "Total map / Projected total **points**" over a 26.5 GAME line, its left
///   edge at −7.
///
/// One defect, four faces: a number printed in a unit the match is not played
/// in. The web settled this in ux/1034 B5 / #2441 (`frontend/lib/marketMapUtils.ts`)
/// and wrote the rule down — *a number in the wrong unit is worse than an
/// absent one, because it looks sourced.* `SportVocab` is that table on iOS,
/// and these tests pin the row that was missing.
final class SportVocabTests: XCTestCase {

    // MARK: - The row that was missing

    /// The live match's own sport key, verbatim from `/api/events/15301138`.
    func testUSOpenSportKeyResolvesToTennis() {
        let vocab = SportVocab.forSport("tennis_wta_us_open")
        XCTAssertEqual(vocab.marginTitle, "Game margin map")
        XCTAssertEqual(vocab.totalTitle, "Games map")
        XCTAssertEqual(vocab.unit, "games")
        XCTAssertEqual(vocab.unitSingular, "game")
        XCTAssertEqual(vocab.marginRange, 6, "±18 was basketball's rail on a ±4.5-game market")
    }

    /// The whole point of the substring table: nobody has to list the tours.
    func testEveryTennisTourKeyMatchesTheSameRow() {
        for key in ["tennis_atp", "tennis_wta", "tennis_atp_us_open",
                    "tennis_wta_us_open", "TENNIS_ATP_WIMBLEDON"] {
            XCTAssertEqual(SportVocab.forSport(key).unit, "games", "\(key) must read as tennis")
        }
    }

    // MARK: - Which sports may state a scoreboard number

    /// Tennis is the ONE declared sport whose scoreboard counts something else.
    /// This is the switch every suppressed widget hangs off, so it is pinned
    /// both ways: false for tennis, true for everything else declared.
    func testOnlyTennisRefusesTheScoreboardsNumber() {
        XCTAssertFalse(SportVocab.forSport("tennis_wta_us_open").scoreboardCountsTheUnit)
        XCTAssertEqual(SportVocab.forSport("tennis_atp").scoreboardUnit, "sets")

        for key in ["baseball_mlb", "icehockey_nhl", "soccer_epl", "soccer_uefa_champs_league",
                    "basketball_nba", "basketball_wnba", "americanfootball_nfl",
                    "americanfootball_ncaaf"] {
            XCTAssertTrue(
                SportVocab.forSport(key).scoreboardCountsTheUnit,
                "\(key) counts the unit its market quotes — suppressing its score would delete a true line"
            )
        }
    }

    /// An undeclared sport keeps its scoreboard (the default runs the opposite
    /// way from the rail width on purpose — see the field's own note).
    func testUndeclaredSportKeepsItsScoreboardAndNamesNoUnit() {
        for key in ["cricket_ipl", "rugbyleague_nrl", nil, ""] {
            let vocab = SportVocab.forSport(key)
            XCTAssertTrue(vocab.scoreboardCountsTheUnit)
            XCTAssertEqual(vocab.unit, "", "an undeclared sport must not be given a unit this table invented")
            XCTAssertEqual(vocab.totalTitle, "Scoring map")
            XCTAssertEqual(vocab.marginRange, 6)
        }
    }

    // MARK: - The sentence a suppressed widget owes the reader

    /// A widget that just goes quiet reads as broken, so the note names both
    /// units. It exists ONLY where the mismatch does.
    func testUnitMismatchNoteIsTennisOnlyAndNamesBothUnits() {
        let note = SportVocab.forSport("tennis_wta_us_open").unitMismatchNote()
        XCTAssertNotNil(note)
        XCTAssertTrue(note!.contains("sets"), "must name what the scoreboard reports")
        XCTAssertTrue(note!.contains("games"), "must name what the market quotes")

        for key in ["baseball_mlb", "basketball_nba", "americanfootball_nfl", "cricket_ipl", ""] {
            XCTAssertNil(SportVocab.forSport(key).unitMismatchNote(),
                         "\(key) has no mismatch to explain")
            XCTAssertNil(SportVocab.forSport(key).unitMismatchNote(settled: true),
                         "\(key) has no mismatch to explain once it is over either")
            XCTAssertNil(SportVocab.forSport(key).projectedMarginNote(),
                         "\(key) has no line to explain away")
            XCTAssertNil(SportVocab.forSport(key).projectedMarginNote(settled: true),
                         "\(key) has no line to explain away once it is over either")
        }
    }

    // MARK: - #3465: the sentence is tensed to whether the match is over

    /// A settled US Open match (Tabilo 0-3 Zverev, event 15304537) read
    /// *"Played games are not captured YET … The line below IS the books'
    /// PROJECTED game margin"* under a hero reading `FINAL · Zverev Win`.
    ///
    /// 🔴 BOTH DIRECTIONS. The damaging regression is the mirror one —
    /// past-tensing a match still being played, where "not captured yet" is
    /// true and useful — so the live reading is pinned as hard as the settled
    /// one. A test that only checked the settled string would go green on a
    /// function that returned the past tense unconditionally.
    func testTheChartsNoteIsTensedToWhetherTheMatchIsOver() {
        let vocab = SportVocab.forSport("tennis_atp_us_open")

        XCTAssertEqual(
            vocab.projectedMarginNote(),
            "Played games are not captured yet — the scoreboard reports sets. "
                + "The line below is the books' projected game margin.")
        XCTAssertEqual(
            vocab.projectedMarginNote(settled: true),
            "Played games were not captured — the scoreboard reported sets. "
                + "The line below was the books' projected game margin.")
    }

    func testTheMapsNoteIsTensedToWhetherTheMatchIsOver() {
        let vocab = SportVocab.forSport("tennis_atp_us_open")

        XCTAssertEqual(
            vocab.unitMismatchNote(),
            "The scoreboard reports sets, this market quotes games — "
                + "we do not hold the games played yet.")
        XCTAssertEqual(
            vocab.unitMismatchNote(settled: true),
            "The scoreboard reported sets, this market quoted games — "
                + "we did not hold the games played.")
    }

    /// The tense-carrying words, asserted as present/absent rather than through
    /// a substring both strings satisfy (UX-P238-5). `"sets"` appears in both
    /// tenses, so a `contains("sets")` check cannot tell them apart.
    func testNoPresentTenseSurvivesTheFinalWhistleAndNoPastTensePrecedesIt() {
        let vocab = SportVocab.forSport("tennis_wta_us_open")

        for live in [vocab.projectedMarginNote()!, vocab.unitMismatchNote()!] {
            XCTAssertTrue(live.contains("yet"), "a match still on IS still waiting: \(live)")
            XCTAssertTrue(live.contains("reports"))
            XCTAssertFalse(live.contains("reported"))
            XCTAssertFalse(live.contains("was the books'"))
        }

        for done in [vocab.projectedMarginNote(settled: true)!,
                     vocab.unitMismatchNote(settled: true)!] {
            XCTAssertFalse(done.contains("yet"),
                           "a finished match is not waiting for anything: \(done)")
            XCTAssertTrue(done.contains("reported"))
            XCTAssertFalse(done.contains("reports"))
        }
    }

    // MARK: - Naming a number

    /// `"13-13"` → `"13-13 games"`; the hero's whole fix is this one word.
    func testWithUnitNamesTheUnitAndStaysSilentWhenThereIsNone() {
        XCTAssertEqual(SportVocab.forSport("tennis_wta_us_open").withUnit("13-13"), "13-13 games")
        XCTAssertEqual(SportVocab.forSport("baseball_mlb").withUnit("5-3"), "5-3 runs")
        XCTAssertEqual(SportVocab.forSport("cricket_ipl").withUnit("180-176"), "180-176",
                       "an undeclared sport prints the market's number and no unit")
    }

    // MARK: - The table's own shape

    /// Ranges are the sport's realistic outcome spread, not a round number.
    /// A regression here re-widens the rail that made a 4.5-game market look
    /// like a blowout market.
    func testMarginRangesAreTheSportsOwn() {
        XCTAssertEqual(SportVocab.forSport("baseball_mlb").marginRange, 5)
        XCTAssertEqual(SportVocab.forSport("icehockey_nhl").marginRange, 5)
        XCTAssertEqual(SportVocab.forSport("soccer_epl").marginRange, 5)
        XCTAssertEqual(SportVocab.forSport("tennis_atp").marginRange, 6)
        XCTAssertEqual(SportVocab.forSport("basketball_nba").marginRange, 18)
        XCTAssertEqual(SportVocab.forSport("americanfootball_nfl").marginRange, 18)
    }

    /// First match wins, in table order — `basketball_nba` must not be reached
    /// through some other row's substring.
    func testKeysResolveToExactlyOneRow() {
        XCTAssertEqual(SportVocab.forSport("basketball_nba").totalTitle, "Points map")
        XCTAssertEqual(SportVocab.forSport("americanfootball_ncaaf").totalTitle, "Points map")
        XCTAssertEqual(SportVocab.forSport("icehockey_nhl").totalTitle, "Goals map")
    }
}
