import XCTest
@testable import Bain_Luck

/// #4306 — a single probability drawn beside a two-name title describes the side
/// named FIRST.
///
/// ## The defect these rows are taken from
///
/// `SearchView.searchEventRow` built its title away-first — the house convention,
/// 6 of the 7 sites in the app that build one — and then drew `homeProbability`
/// beside it with no label. A reader anchors a lone number to the name they read
/// first, so every scheduled row published the market backwards. The finished arm
/// of that same function already printed its score `away - home`, so one row
/// contradicted itself depending on whether the match had started.
///
/// `DiscoverEventCard.shareMessage` did the same thing in prose — and that one
/// leaves the app and arrives in someone else's messages, where there is no page
/// underneath it to check against.
///
/// ## Where the rows come from
///
/// `GET /api/events/search?q=US Open` on production, 2026-09-09 ~04:40 PT: every
/// scheduled row that carried odds, 6 of 6, taken verbatim. They are the
/// measurement that made the issue, kept so the class cannot come back as a
/// one-row regression.
///
/// 🔴 THE CONTROLS ARE THE POINT. A fixture that misrepresents production passes
/// every ship assertion written against it — so `testTheSpecimensCanFailThisSuite`
/// asserts the properties that make these rows a real test: each pair is a
/// complement, the two sides never round to the same integer (or "away" and
/// "home" would be indistinguishable and the suite would pass while inverted),
/// and the away side is the favourite in some rows and the underdog in others (or
/// "always draw the favourite" would pass too, and it is a different rule).
final class LoneProbabilityNamesItsSideTests: XCTestCase {

    private struct Row {
        let away: String
        let home: String
        let awayProbability: Double
        let homeProbability: Double
        /// The whole percent the row must print, which is the AWAY side's.
        let expected: Int
    }

    /// The sport these rows actually are, stated rather than defaulted (#5363).
    ///
    /// Every specimen below is a US Open singles match, and tennis does not price
    /// a draw — which is the whole reason they still read away-first. Passing the
    /// real key rather than `nil` means these assertions exercise the SPORT GATE
    /// on its two-way arm instead of the undeclared fallback, so transposing the
    /// `winnerMarketPricesADraw` flag onto tennis in `SportVocab` fails here.
    private let usOpen = "tennis_atp_us_open"

    private let specimens: [Row] = [
        Row(away: "Elena Rybakina", home: "Qinwen Zheng",
            awayProbability: 0.72, homeProbability: 0.28, expected: 72),
        Row(away: "Coco Gauff", home: "Mirra Andreeva",
            awayProbability: 0.645, homeProbability: 0.355, expected: 65),
        // 39 and not 40. 0.395 rounds to 40 on its own, but the pair rule anchors
        // the FAVOURITE and lands the derived point on the underdog, so Khachanov
        // takes 61 and this side takes the remaining 39 (`renderedDuelPercents`).
        // Written out because the first draft of this table said 40, and the
        // suite — correctly — refused it.
        //
        // 🔴 AND THE SCREENSHOT ON THE PR SHOWS THIS ROW AT 40%, WHICH IS NOT A
        // CONTRADICTION. These probabilities are FROZEN at 04:40 PT; this one
        // had moved to 0.3982/0.6018 by the 05:02 frame, which the same rule
        // renders as 40. A live price moving is what a fixture exists to be
        // immune to — do not "correct" this row against a later reading.
        Row(away: "Alexander Blockx", home: "Karen Khachanov",
            awayProbability: 0.395, homeProbability: 0.605, expected: 39),
        Row(away: "Botic van de Zandschulp", home: "Alexander Zverev",
            awayProbability: 0.138, homeProbability: 0.862, expected: 14),
        Row(away: "Jessica Pegula", home: "Aryna Sabalenka",
            awayProbability: 0.38, homeProbability: 0.62, expected: 38),
        Row(away: "Ben Shelton", home: "Frances Tiafoe",
            awayProbability: 0.72, homeProbability: 0.28, expected: 72),
    ]

    // MARK: - The rule

    func testTheNumberDrawnIsTheFirstNamedSides() {
        for row in specimens {
            let reading = firstNamedSideNumber(
                away: row.awayProbability,
                home: row.homeProbability,
                servedAway: nil,
                servedHome: nil,
                sport: usOpen
            )
            XCTAssertFalse(
                reading?.isHome ?? true,
                "\(row.away) vs \(row.home): tennis prices no draw, so the row still names the away side"
            )
            XCTAssertEqual(
                reading?.percent, row.expected,
                "\(row.away) vs \(row.home) must print \(row.away)'s number"
            )
            XCTAssertEqual(reading?.probability, row.awayProbability)
        }
    }

    /// The failure the issue was filed on: the old expression, still runnable, on
    /// the same rows. If this ever stops differing, the specimens have gone flat
    /// and the suite above proves nothing.
    func testTheOldHomeSideReadingDisagreesOnEverySpecimen() {
        for row in specimens {
            let drawn = firstNamedSideNumber(
                away: row.awayProbability,
                home: row.homeProbability,
                servedAway: nil,
                servedHome: nil,
                sport: usOpen
            )?.percent
            let oldReading = Int((row.homeProbability * 100).rounded())
            XCTAssertNotEqual(
                drawn, oldReading,
                "\(row.away) vs \(row.home): the fixed and broken readings agree, so this row cannot catch the defect"
            )
        }
    }

    func testTheSpecimensCanFailThisSuite() {
        var awayWasFavourite = 0
        var awayWasUnderdog = 0
        for row in specimens {
            XCTAssertEqual(
                row.awayProbability + row.homeProbability, 1.0, accuracy: 0.0005,
                "\(row.away) vs \(row.home) is not a complement pair"
            )
            XCTAssertNotEqual(
                Int((row.awayProbability * 100).rounded()),
                Int((row.homeProbability * 100).rounded()),
                "\(row.away) vs \(row.home) rounds both sides to one integer, so it cannot tell them apart"
            )
            if row.awayProbability > row.homeProbability { awayWasFavourite += 1 } else { awayWasUnderdog += 1 }
        }
        XCTAssertGreaterThan(awayWasFavourite, 0, "no row where the first-named side is the favourite")
        XCTAssertGreaterThan(awayWasUnderdog, 0, "no row where the first-named side is the underdog")
    }

    // MARK: - The pair contract it inherits

    func testTheServedPairIsUsedWholeOrNotAtAll() {
        // Both served: they are the answer, and no local rounding runs.
        XCTAssertEqual(
            firstNamedSideNumber(away: 0.505, home: 0.495, servedAway: 50, servedHome: 50, sport: usOpen)?.percent,
            50
        )
        // Half a served pair is not a served pair (#2279) — it falls back WHOLE.
        XCTAssertEqual(
            firstNamedSideNumber(away: 0.505, home: 0.495, servedAway: 50, servedHome: nil, sport: usOpen)?.percent,
            renderedDuelPercents(away: 0.505, home: 0.495)[0]
        )
    }

    // MARK: - No row that had a number loses one

    func testAHomeOnlyPayloadStillDrawsTheFirstNamedSide() {
        let reading = firstNamedSideNumber(away: nil, home: 0.28, servedAway: nil, servedHome: nil, sport: usOpen)
        XCTAssertEqual(reading?.percent, 72, "the row drew a number before this fix and must still draw one")
        XCTAssertEqual(reading?.probability ?? 0, 0.72, accuracy: 0.0001)
    }

    func testNoOddsAtAllDrawsNothing() {
        XCTAssertNil(firstNamedSideNumber(away: nil, home: nil, servedAway: nil, servedHome: nil, sport: usOpen))
    }

    // MARK: - #5363, the sport that has no away price to name

    /// The same rows, transposed onto a draw-priced sport: the number moves to
    /// HOME and the caller is told to name it.
    ///
    /// Written against the tennis specimens deliberately — the numbers are the
    /// ones the two-way assertions above use, so anything that differs here is
    /// the sport gate and nothing else.
    func testADrawPricedRowHandsBackTheHomeSide() {
        for row in specimens {
            let reading = firstNamedSideNumber(
                away: row.awayProbability,
                home: row.homeProbability,
                servedAway: nil,
                servedHome: nil,
                sport: "soccer_epl"
            )
            XCTAssertEqual(reading?.isHome, true,
                           "\(row.away) vs \(row.home): a draw-priced row names home")
            XCTAssertEqual(reading?.probability, row.homeProbability)
            XCTAssertEqual(reading?.percent, Int((row.homeProbability * 100).rounded()))
        }
    }

    /// The served pair describes a complement, so it may not decide the withheld
    /// side's survivor either: `servedHome` is `100 − servedAway`, which is a
    /// number about the very reading this arm refuses. It rounds the home
    /// probability itself and ignores both served fields.
    func testADrawPricedRowIgnoresTheServedComplementPair() {
        let reading = firstNamedSideNumber(
            away: 0.505, home: 0.495,
            servedAway: 50, servedHome: 50,
            sport: "soccer_epl"
        )
        XCTAssertEqual(reading?.isHome, true)
        XCTAssertEqual(reading?.percent, 50)
        XCTAssertEqual(reading?.probability, 0.495)
    }

    /// A draw-priced row with no HOME price has nothing left to print — the away
    /// figure cannot stand in for it, which is the whole rule.
    func testADrawPricedRowWithNoHomePriceDrawsNothing() {
        XCTAssertNil(firstNamedSideNumber(
            away: 0.72, home: nil,
            servedAway: nil, servedHome: nil,
            sport: "soccer_epl"
        ))
    }

    // MARK: - The sentence that leaves the app

    func testShareMessageNamesBothSidesBesideTheirOwnNumbers() {
        XCTAssertEqual(
            eventShareMessage(away: "Elena Rybakina", home: "Qinwen Zheng", awayPercent: 72, homePercent: 28),
            "Elena Rybakina 72% vs Qinwen Zheng 28% on Bain Luck"
        )
    }

    /// The old sentence for this row was
    /// "Elena Rybakina vs Qinwen Zheng — 28% on Bain Luck": Rybakina named first,
    /// Zheng's number, nothing saying so. No number may appear in the message
    /// without a name in front of it.
    func testNoPercentAppearsWithoutANameInFrontOfIt() {
        for row in specimens {
            let duel = duelPercents(
                away: row.awayProbability,
                home: row.homeProbability,
                servedAway: nil,
                servedHome: nil
            )
            let message = eventShareMessage(
                away: row.away, home: row.home,
                awayPercent: duel[0], homePercent: duel[1]
            )
            XCTAssertTrue(
                message.contains("\(row.away) \(row.expected)%"),
                "share message must attribute \(row.expected)% to \(row.away): \(message)"
            )
            XCTAssertFalse(
                message.contains("vs \(row.home) — "),
                "share message reverted to the unattributed form: \(message)"
            )
        }
    }

    func testAShareWithoutPricesQuotesNoNumber() {
        let message = eventShareMessage(
            away: "Elena Rybakina", home: "Qinwen Zheng", awayPercent: nil, homePercent: nil
        )
        XCTAssertEqual(message, "Elena Rybakina vs Qinwen Zheng on Bain Luck")
        XCTAssertFalse(message.contains("%"), "a price we do not have is not a price")
    }

    /// Half a pair is not a pair here either: quoting one side's percent beside a
    /// bare name is the unattributed form again.
    func testAShareWithHalfAPairQuotesNoNumber() {
        XCTAssertEqual(
            eventShareMessage(away: "A", home: "B", awayPercent: 72, homePercent: nil),
            "A vs B on Bain Luck"
        )
    }
}
