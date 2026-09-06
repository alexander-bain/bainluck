import XCTest
@testable import Bain_Luck

/// #3550 — an Additional Markets row must not restate the heading printed
/// directly above it.
///
/// THE MECHANISM, from `/api/events/15305553/game-markets` on 2026-09-06
/// (Cerundolo v Blockx, US Open ATP): every one of the mini-card's fifteen rows
/// sits under the heading `"US Open ATP: Francisco Cerundolo vs Alexander
/// Blockx"`, and thirteen of them are NAMED that plus a suffix. Photographed at
/// `artifacts-native-037/BEFORE-cerundolo-blockx-15305553.png`: thirteen
/// two-line rows, all beginning with the same 52 characters, on a page whose
/// title bar already reads *Blockx vs Cerundolo*.
///
/// The strings below are verbatim production, not paraphrases. A paraphrase
/// here would be a test of a shape nobody serves — the exact failure the
/// golden-set rule exists to stop.
final class RedundantHeadingLabelTests: XCTestCase {

    /// The heading the mini-card prints, and the thirteen rows served under it.
    private static let heading = "US Open ATP: Francisco Cerundolo vs Alexander Blockx"
    private static let servedRows: [(outcome: String, reads: String)] = [
        ("US Open ATP: Francisco Cerundolo vs Alexander Blockx Set 1 Winner", "Set 1 Winner"),
        ("US Open ATP: Francisco Cerundolo vs Alexander Blockx Set 2 Winner", "Set 2 Winner"),
        ("US Open ATP: Francisco Cerundolo vs Alexander Blockx Set 3 Winner", "Set 3 Winner"),
        ("US Open ATP: Francisco Cerundolo vs Alexander Blockx Set Handicap +/-1.5", "Set Handicap +/-1.5"),
        ("US Open ATP: Francisco Cerundolo vs Alexander Blockx Set Handicap +/-2.5", "Set Handicap +/-2.5"),
        // The colon goes with the heading it joined — web's `COLON_BEFORE_OU`.
        ("US Open ATP: Francisco Cerundolo vs Alexander Blockx Total Sets: O/U 3.5", "Total Sets O/U 3.5"),
        ("US Open ATP: Francisco Cerundolo vs Alexander Blockx Total Sets: O/U 4.5", "Total Sets O/U 4.5"),
        ("US Open ATP: Francisco Cerundolo vs Alexander Blockx Game Spread +/-3.5", "Game Spread +/-3.5"),
        ("US Open ATP: Francisco Cerundolo vs Alexander Blockx Set 1 O/U 9.5", "Set 1 O/U 9.5"),
        ("US Open ATP: Francisco Cerundolo vs Alexander Blockx Set 1 O/U 10.5", "Set 1 O/U 10.5"),
        ("US Open ATP: Francisco Cerundolo vs Alexander Blockx Set 3 O/U 10.5", "Set 3 O/U 10.5"),
        ("US Open ATP: Francisco Cerundolo vs Alexander Blockx Match O/U 36.5", "Match O/U 36.5"),
        ("US Open ATP: Francisco Cerundolo vs Alexander Blockx Match O/U 38.5", "Match O/U 38.5"),
    ]

    // MARK: - The ship

    func testEveryServedRowKeepsOnlyWhatDistinguishesIt() {
        for row in Self.servedRows {
            XCTAssertEqual(
                labelWithoutRedundantHeading(row.outcome, under: Self.heading),
                row.reads,
                "the reader has to find this row's meaning at the end of a wrapped second line"
            )
        }
    }

    /// The six shapes the 2026-09-06 census found across all 260 prefixed rows,
    /// under a DIFFERENT heading — so a fix that happened to hard-code one
    /// match's name cannot pass.
    func testTheSameRuleHoldsUnderADifferentMatchesHeading() {
        let heading = "US Open ATP (Doubles): Helioevaara/Patten vs Arnaldi/Struff"
        XCTAssertEqual(
            labelWithoutRedundantHeading("\(heading) Total Sets: O/U 2.5", under: heading),
            "Total Sets O/U 2.5"
        )
    }

    // MARK: - The two surfaces must print the same string

    /// This function is the Swift half of `frontend/lib/otherMarketGroups.ts`
    /// (`stripCardPrefix`), which fixed these same rows on web in live/065
    /// (#2746). The rows below are that module's own fixture — the verbatim
    /// wire of the live Pegula–Fernandez match, `/api/events/15301138/game-markets`
    /// at 2026-09-04 09:58 PT — with web's expected output. iOS reading one
    /// character differently is the #3503 failure: two surfaces, one question,
    /// two answers, and only the reader who owns both devices ever finds out.
    func testEveryRowReadsExactlyAsTheWebPrintsIt() {
        let match = "US Open WTA: Jessica Pegula vs Leylah Fernandez"
        let webParity: [(String, String)] = [
            ("\(match) Set 1 Winner", "Set 1 Winner"),
            ("\(match) Set 2 Winner", "Set 2 Winner"),
            ("\(match) Set Handicap +/-1.5", "Set Handicap +/-1.5"),
            ("\(match) Total Sets: O/U 2.5", "Total Sets O/U 2.5"),
            ("\(match) Game Spread +/-4.5", "Game Spread +/-4.5"),
            ("\(match) Match O/U 21.5", "Match O/U 21.5"),
            // Rows web returns byte-identical, for the same reasons.
            ("Jessica Pegula", "Jessica Pegula"),
            ("Yes", "Yes"),
            ("No", "No"),
            (match, match),
        ]
        for (outcome, web) in webParity {
            XCTAssertEqual(
                labelWithoutRedundantHeading(outcome, under: match), web,
                "web prints \"\(web)\" for this row; the phone must not print something else"
            )
        }
    }

    /// A colon that is NOT introducing an O/U line stays put — web's rule is
    /// lookahead-anchored, and a blanket colon strip would rewrite labels the
    /// venue punctuated on purpose.
    func testOnlyTheColonBeforeAnOverUnderIsDropped() {
        let heading = "US Open ATP: Francisco Cerundolo vs Alexander Blockx"
        XCTAssertEqual(
            labelWithoutRedundantHeading("\(heading) Retirement: Yes", under: heading),
            "Retirement: Yes"
        )
    }

    /// The `Text` is `.lineLimit(2)` at 11pt, so the whole point is the row
    /// getting shorter. A rule that shortened nothing would pass a test that
    /// only asserted "does not crash".
    func testTheLabelActuallyGetsDramaticallyShorter() {
        let long = "US Open ATP: Francisco Cerundolo vs Alexander Blockx Match O/U 36.5"
        let short = labelWithoutRedundantHeading(long, under: Self.heading)
        XCTAssertEqual(long.count, 67)
        XCTAssertEqual(short.count, 14)
    }

    // MARK: - Guard 1: the heading must end on a whole word

    /// `"Set 1"` against `"Set 10 Winner"` must not leave `"0 Winner"`. This is
    /// the one failure mode where the tidy-up would make a row say something
    /// FALSE rather than merely something long, so it is refused outright
    /// rather than patched up.
    func testAPartialWordMatchIsRefusedRatherThanSliced() {
        XCTAssertEqual(
            labelWithoutRedundantHeading("Set 10 Winner", under: "Set 1"),
            "Set 10 Winner"
        )
        XCTAssertEqual(
            labelWithoutRedundantHeading("Matchup Winner", under: "Match"),
            "Matchup Winner"
        )
    }

    // MARK: - Guard 2: never a blank row

    /// An outcome named exactly its own market strips to nothing, and a blank
    /// label beside a live 80% bar reads as data we failed to load. Served
    /// today: market and outcome are both `"US Open WTA: Iga Swiatek vs Qinwen
    /// Zheng"` on event 15305580.
    func testAnOutcomeNamedExactlyItsMarketKeepsItsName() {
        let same = "US Open WTA: Iga Swiatek vs Qinwen Zheng"
        XCTAssertEqual(labelWithoutRedundantHeading(same, under: same), same)
    }

    func testAHeadingFollowedByOnlyPunctuationKeepsTheOriginal() {
        XCTAssertEqual(
            labelWithoutRedundantHeading("Total Sets:", under: "Total Sets"),
            "Total Sets:"
        )
    }

    // MARK: - Everything else is untouched

    /// Zero of the 260 prefixed rows measured were outside tennis. Every other
    /// sport's rows must come back byte-identical, or this "tidy-up" is a
    /// rewrite of labels nobody complained about.
    func testRowsThatDoNotRestateTheirHeadingAreReturnedUntouched() {
        let heading = "NE Patriots vs SEA Seahawks"
        for untouched in ["Yes", "No", "Francisco Cerundolo", "Over 44.5", "Seattle Seahawks -1.5"] {
            XCTAssertEqual(labelWithoutRedundantHeading(untouched, under: heading), untouched)
        }
    }

    func testAnEmptyHeadingStripsNothing() {
        XCTAssertEqual(labelWithoutRedundantHeading("Set 1 Winner", under: ""), "Set 1 Winner")
        XCTAssertEqual(labelWithoutRedundantHeading("Set 1 Winner", under: "   "), "Set 1 Winner")
    }
}
