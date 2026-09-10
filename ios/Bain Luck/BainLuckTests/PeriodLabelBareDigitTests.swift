import XCTest
@testable import Bain_Luck

/// #4888 — a BARE period number says which unit it is counting.
///
/// Handed to native by ux/1184 after Alex's 2026-09-09 iPad pass (item 6): the
/// web's win-probability chart drew dashed rules captioned bare `3` and `4`,
/// and a reader had no way to learn those meant quarters.
///
/// **THIS FIXES A LATENT BRANCH, NOT A SURFACE.** Measured on production
/// 2026-09-10 before writing a line: bare digits reach a client through exactly
/// one carrier, `period_markers` with `source: espn_box`, and iOS does not
/// decode `period_markers` at all. The three sources iOS *does* read carry no
/// bare digit anywhere — `espn_snapshots.period` (176,609 rows; the only
/// space-free values are `Halftime` and `Delayed`), `win_prob_snapshots
/// .game_state->>'period'` (305,197 rows; `Halftime`/`Final`/`Start`/
/// `Postponed`/`Scheduled`/`Delayed`/`Q1`–`Q4`/`Final/OT`), and the
/// `scoring_plays` table (0 rows, ever). On Alex's own specimen, event
/// 14780138, the web chart draws `3`/`4` and the phone draws `Q3`/`Q4`, because
/// the phone reads a richer source.
///
/// So these are the ONLY instrument that can hold this rule. There is no LOOK
/// that shows a difference, and the PR does not claim one.
///
/// **THE LEAVE-IT-ALONE DIRECTION IS THE POINT.** ux flagged it and it is worth
/// repeating: a test asserting only `"3"` → `"Q3"` passes just as well against a
/// helper that hardcoded `Q`, which would relabel every NHL and MLB chart. Every
/// completion below is paired with a sport that must NOT be completed.
final class PeriodLabelBareDigitTests: XCTestCase {

    // MARK: - The completions

    func testBareDigitTakesTheSportsOwnUnit() {
        XCTAssertEqual(PeriodLabel.normalize("3", sport: "americanfootball_nfl"), "Q3")
        XCTAssertEqual(PeriodLabel.normalize("4", sport: "americanfootball_ncaaf"), "Q4")
        XCTAssertEqual(PeriodLabel.normalize("2", sport: "basketball_nba"), "Q2")
        XCTAssertEqual(PeriodLabel.normalize("1", sport: "basketball_wnba"), "Q1")
        XCTAssertEqual(PeriodLabel.normalize("3", sport: "icehockey_nhl"), "P3")
        XCTAssertEqual(PeriodLabel.normalize("2", sport: "soccer_epl"), "2H")
    }

    /// Alex's specimen, end to end: event 14780138 is `americanfootball_nfl` and
    /// its `period_markers` are exactly `"2"`, `"3"`, `"4"`.
    func testAlexsSpecimenReadsAsQuarters() {
        let served = ["2", "3", "4"]
        XCTAssertEqual(
            served.map { PeriodLabel.normalize($0, sport: "americanfootball_nfl") },
            ["Q2", "Q3", "Q4"]
        )
    }

    // MARK: - The leave-it-alone direction

    /// Baseball is the sport this branch used to answer for everybody, and it is
    /// the one sport that must keep the bare-ordinal answer: `T3` and `B3` are
    /// different moments and the digit does not say which.
    func testBaseballKeepsItsOrdinalAndGainsNoHalf() {
        XCTAssertEqual(PeriodLabel.normalize("3", sport: "baseball_mlb"), "3rd")
        XCTAssertEqual(PeriodLabel.normalize("9", sport: "baseball_mlb"), "9th")
        XCTAssertEqual(PeriodLabel.normalize("1", sport: "baseball_ncaa"), "1st")
    }

    /// An unknown or absent sport reproduces the pre-#4888 output exactly, which
    /// is what makes the new parameter safe to not pass.
    func testUnknownOrAbsentSportIsUnchanged() {
        XCTAssertEqual(PeriodLabel.normalize("3"), "3rd")
        XCTAssertEqual(PeriodLabel.normalize("3", sport: nil), "3rd")
        XCTAssertEqual(PeriodLabel.normalize("3", sport: ""), "3rd")
        XCTAssertEqual(PeriodLabel.normalize("3", sport: "tennis_atp_us_open"), "3rd")
        XCTAssertEqual(PeriodLabel.normalize("3", sport: "mma_mixed_martial_arts"), "3rd")
        XCTAssertEqual(PeriodLabel.normalize("3", sport: "golf_pga"), "3rd")
    }

    /// Men's college basketball plays two HALVES. This is the collision the
    /// `columnLabel` doc already warned about, and the reason the table is
    /// prefix-matched and order-sensitive rather than a `basketball_` catch-all.
    func testMensCollegeBasketballPlaysHalvesAndWomensPlaysQuarters() {
        XCTAssertEqual(PeriodLabel.normalize("1", sport: "basketball_ncaab"), "1H")
        XCTAssertEqual(PeriodLabel.normalize("2", sport: "basketball_ncaab"), "2H")
        // `basketball_wncaab` must NOT be swallowed by the `basketball_ncaab`
        // row — as a PREFIX it is not, and a substring match would break this.
        XCTAssertEqual(PeriodLabel.normalize("3", sport: "basketball_wncaab"), "Q3")
        XCTAssertEqual(PeriodLabel.normalize("4", sport: "basketball_wncaab"), "Q4")
    }

    /// Past regulation the numbering runs into overtime, and completing it with
    /// the regulation unit invents a period that does not exist. There is no
    /// third half of soccer and no fifth quarter of football, so those fall
    /// through to the vague-but-true ordinal.
    func testNumbersPastRegulationAreNotCompleted() {
        XCTAssertEqual(PeriodLabel.normalize("5", sport: "americanfootball_nfl"), "5th")
        XCTAssertEqual(PeriodLabel.normalize("3", sport: "soccer_epl"), "3rd")
        XCTAssertEqual(PeriodLabel.normalize("4", sport: "icehockey_nhl"), "4th")
        XCTAssertEqual(PeriodLabel.normalize("3", sport: "basketball_ncaab"), "3rd")
        XCTAssertEqual(PeriodLabel.normalize("5", sport: "basketball_nba"), "5th")
    }

    /// `"0"` is "not started", never a chip. This split is OLDER than #4888 and
    /// must survive it — it is why the bare-integer case was lifted out of the
    /// "already short" alternation in the first place.
    func testZeroIsStillNoChipForEverySport() {
        for sport in ["americanfootball_nfl", "basketball_nba", "icehockey_nhl",
                      "soccer_epl", "baseball_mlb", "basketball_ncaab", nil] {
            XCTAssertEqual(
                PeriodLabel.normalize("0", sport: sport), "",
                "a period number of zero is 'not started' — sport \(sport ?? "nil")"
            )
        }
    }

    // MARK: - Nothing that carries its own noun consults the sport

    /// The whole argument for taking a sport key here is that a bare digit has
    /// no unit noun. Every string that HAS one must read identically whatever
    /// sport is passed — otherwise this parameter has widened past its warrant
    /// and `columnLabel`'s "the noun beats the sport key" note stops being true.
    func testAVerbosePeriodIgnoresTheSportEntirely() {
        let sports: [String?] = [nil, "americanfootball_nfl", "baseball_mlb",
                                 "icehockey_nhl", "soccer_epl", "basketball_ncaab"]
        let cases: [(raw: String, expected: String)] = [
            ("1st Quarter", "Q1"),
            ("0:24 - 2nd Quarter", "Q2"),
            ("End of 3rd Quarter", "Q3"),
            ("2nd Period", "P2"),
            ("1st Half", "1H"),
            ("Top 3rd", "3rd"),
            ("Bottom 9th", "9th"),
            // A LITERAL bare ordinal `"3rd"` has returned `"Q3"` since long
            // before #4888 — the `lower == "3rd"` quarter branch sits above the
            // inning branch, so `1st`–`4th` are read as quarters and `5th`+ as
            // innings. That asymmetry is not this change's and is not touched by
            // it; what matters here is that the sport does not move it either
            // way. Not reachable in any case: production serves no bare ordinal
            // on the two paths iOS reads (measured, see the type doc).
            ("3rd", "Q3"),
            ("9th", "9th"),
            ("Halftime", "HT"),
            ("Overtime", "OT"),
            ("2nd Overtime", "OT2"),
            ("Q1", "Q1"),
            ("P2", "P2"),
            ("1H", "1H"),
            ("R2", "R2"),
            ("Round 3", "R3"),
            ("playoff", "PO"),
        ]
        for (raw, expected) in cases {
            for sport in sports {
                XCTAssertEqual(
                    PeriodLabel.normalize(raw, sport: sport), expected,
                    "\"\(raw)\" names its own unit and must ignore sport \(sport ?? "nil")"
                )
            }
        }
    }

    /// The two surfaces that deliberately do NOT take a sport key keep their
    /// pre-#4888 answers, so this change cannot have leaked into them.
    func testColumnAndBadgeSurfacesAreUntouched() {
        XCTAssertEqual(PeriodLabel.columnLabel("3"), "3")
        XCTAssertEqual(PeriodLabel.columnLabel("0:00 - 3rd Quarter"), "Q3")
        XCTAssertEqual(PeriodLabel.liveBadgeLabel("3"), "3rd")
        XCTAssertEqual(PeriodLabel.liveBadgeLabel("Bottom 7th"), "Bottom 7th")
    }
}
