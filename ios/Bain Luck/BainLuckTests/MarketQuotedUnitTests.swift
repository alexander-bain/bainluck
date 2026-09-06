import XCTest
@testable import Bain_Luck

/// native/036, #3509 — a totals widget must name the unit ITS OWN markets
/// quote, not the one its sport usually quotes.
///
/// Found on the D48 LOOK. A tennis "Total Sets" market printed as **"Projected
/// combined games: 2.5+"**, and there is no tennis match in which 2.5 games is
/// a meaningful total. `SportVocab.forSport` was doing its job correctly — it
/// answers *"what does this SPORT's market quote?"* and for tennis "games" is
/// right — but nothing asked the second question, *"and what does THIS market
/// quote?"*, so a sets line inherited the games label.
///
/// Measured on production 2026-09-06, open linked markets with
/// `llm_sport_category='tennis'` and "total" in the name: **210 quote SETS, 2
/// quote GAMES**, across 187 events. In tennis this is not an edge case, it is
/// nearly the whole population.
///
/// Every market name in this file is VERBATIM from a production payload
/// (`/api/events/<id>/game-markets`, `totals[].market_name`, sampled
/// 2026-09-06 across 37 events and 8 sports) or from `futures_markets.name`.
/// Names are the input this parse exists to survive, so inventing them would
/// make the whole file agree with itself by construction.
final class MarketQuotedUnitTests: XCTestCase {

    // MARK: - The photographed defect

    /// Event 15305808 (Marrero v Kasnikowski), the payload behind #3509: the
    /// ONLY totals rung is a sets line, so the whole widget is mislabelled.
    func testTennisTotalSetsMarketQuotesSetsNotGames() {
        XCTAssertEqual(
            SportVocab.declaredUnit(
                inMarketName: "Ivan Marrero vs. Maks Kasnikowski: Total Sets O/U 2.5"),
            "sets"
        )
        let tennis = SportVocab.forSport("tennis_atp_us_open")
        XCTAssertEqual(tennis.unit, "games", "the SPORT still quotes games — that row is not the bug")
        XCTAssertEqual(
            tennis.totalsUnit(quotedBy: ["Ivan Marrero vs. Maks Kasnikowski: Total Sets O/U 2.5"]),
            "sets",
            "the widget labels itself from the market, so 'Projected combined games: 2.5+' cannot recur"
        )
    }

    /// The other half of the ruling: a market that declares nothing keeps
    /// inheriting its sport's unit. Without this, fixing the sets label would
    /// strip the unit off every honest totals widget in the app.
    func testMatchTotalDeclaresNothingAndInheritsTheSport() {
        for name in [
            "Shelton vs. Hurkacz: Match O/U 36.5",
            "Kalinskaya vs. Navarro: Match O/U 21.5",
            "Sabalenka vs. Townsend: Match O/U 23.5",
        ] {
            XCTAssertNil(SportVocab.declaredUnit(inMarketName: name),
                         "\(name) names no unit; 'match' is a SCOPE word")
        }
        XCTAssertEqual(
            SportVocab.forSport("tennis_atp_us_open").totalsUnit(
                quotedBy: ["Shelton vs. Hurkacz: Match O/U 36.5",
                           "Shelton vs. Hurkacz: Match O/U 40.5"]),
            "games"
        )
    }

    // MARK: - The same defect outside tennis

    /// This is why the fix reads the market and does not special-case tennis.
    /// Each of these is live on production and each names a unit its sport
    /// does not quote.
    func testOtherSportsDeclareUnitsTheirSportDoesNotQuote() {
        XCTAssertEqual(
            SportVocab.declaredUnit(inMarketName: "FC Anyang vs. Gangwon FC - Total Corners"),
            "corners",
            "soccer's unit is goals; a corners line on a goals map is the same defect")
        XCTAssertEqual(
            SportVocab.declaredUnit(inMarketName: "O/U 0.5 Rounds"),
            "rounds",
            "MMA declares no unit at all, so this widget used to say 'scoring'")
        XCTAssertEqual(
            SportVocab.declaredUnit(inMarketName: "Bryce Harper: Total Bases O/U 3.5"),
            "bases",
            "baseball's unit is runs")
        // …and where the market agrees with its sport, the answer is a no-op.
        XCTAssertEqual(
            SportVocab.declaredUnit(inMarketName: "St. Louis vs Colorado: Total Runs"), "runs")
        XCTAssertEqual(
            SportVocab.declaredUnit(inMarketName: "Chicago vs Carolina: Total Points"), "points")
    }

    /// MMA has no row in the table, so before #3509 this widget said "scoring".
    func testUndeclaredSportStillGetsTheMarketsOwnUnit() {
        XCTAssertEqual(SportVocab.forSport("mma_mixed_martial_arts").unit, "")
        XCTAssertEqual(
            SportVocab.forSport("mma_mixed_martial_arts").totalsUnit(quotedBy: ["O/U 0.5 Rounds"]),
            "rounds"
        )
    }

    // MARK: - The subject is not a unit

    /// The regression this parse is most likely to cause, and the reason the
    /// `<noun> O/U <n>` position is narrowed to units we have vocabulary for:
    /// a venue writes the SUBJECT in exactly that position too. Reading
    /// "calcio" as a unit would be this same bug in a new costume.
    func testTeamNameBeforeTheLineIsNotReadAsAUnit() {
        for name in [
            "Udinese Calcio vs. SS Lazio: Udinese Calcio O/U 0.5",
            "Udinese Calcio vs. SS Lazio: SS Lazio O/U 1.5",
            "Manchester United FC O/U 2.5",
            "Brighton & Hove Albion FC O/U 3.5",
            "Real Sociedad de Fútbol O/U 2.5",
        ] {
            XCTAssertNil(SportVocab.declaredUnit(inMarketName: name),
                         "\(name) names a CLUB before the line, not a unit")
        }
        // So a soccer map of them still says goals, exactly as it did before.
        XCTAssertEqual(
            SportVocab.forSport("soccer_italy_serie_a").totalsUnit(
                quotedBy: ["Udinese Calcio vs. SS Lazio: Udinese Calcio O/U 0.5",
                           "Udinese Calcio vs. SS Lazio: O/U 2.5"]),
            "goals"
        )
    }

    /// A bare line with no noun anywhere is the commonest shape in the app.
    func testBareOverUnderDeclaresNothing() {
        for name in [
            "Edmonton Elks vs. Calgary Stampeders: O/U 58.5",
            "Las Vegas Aces vs. Seattle Storm: O/U 173.5",
            "Udinese Calcio vs. SS Lazio: O/U 2.5",
            "O/U 55.5",
        ] {
            XCTAssertNil(SportVocab.declaredUnit(inMarketName: name), name)
        }
        XCTAssertEqual(
            SportVocab.forSport("basketball_wnba").totalsUnit(
                quotedBy: ["Las Vegas Aces vs. Seattle Storm: O/U 173.5"]),
            "points",
            "WNBA points must survive a fix aimed at tennis")
    }

    // MARK: - The scope word that reaches the same position

    /// `"Set 1 Games O/U 8.5"` is set-SCOPED but quoted in GAMES — the noun
    /// next to the line is the unit, and the leading "Set 1" is scope. It is
    /// the case that proves the parse reads a unit rather than grepping for
    /// the word "set".
    func testSetScopedGamesLineQuotesGames() {
        XCTAssertEqual(
            SportVocab.declaredUnit(inMarketName: "Swiatek vs. Podoroska: Set 1 Games O/U 8.5"),
            "games")
        XCTAssertEqual(
            SportVocab.declaredUnit(inMarketName: "Medvedev vs. Gorzny: Set 4 Games O/U 9.5"),
            "games")
    }

    // MARK: - Two units on one map

    /// Reachable TODAY, which is why `totalsUnit` takes the whole list.
    ///
    /// The backend drops sets rungs from a tennis map whenever a match-scope
    /// rung survives (`_match_scope_tennis_totals`), but that guard keys on the
    /// sport PREFIX — and real ATP/WTA matches are currently classified
    /// `table_tennis` upstream, so they walk past it. Swiatek v Podoroska
    /// served both rungs together on 2026-09-06.
    ///
    /// No single noun is true of both, and this codebase's standing rule is
    /// that a number in the wrong unit is worse than an absent one *because it
    /// looks sourced*. So: no noun.
    func testMixedUnitsOnOneMapStateNoUnitAtAll() {
        let mixed = ["Iga Swiatek vs. Nadia Podoroska: Total Sets O/U 2.5",
                     "Swiatek vs. Podoroska: Set 1 Games O/U 8.5"]
        XCTAssertEqual(SportVocab.forSport("tennis_wta_us_open").totalsUnit(quotedBy: mixed), "",
                       "neither 'sets' nor 'games' is true of both rungs")
        // …and the sport's own unit is NOT the fallback here: it is one of the
        // two wrong answers, which is the trap this case exists to hold shut.
        XCTAssertNotEqual(SportVocab.forSport("tennis_wta_us_open").totalsUnit(quotedBy: mixed),
                          "games")
    }

    /// Agreement across several rungs is the normal case and must stay quiet.
    func testAgreeingRungsKeepTheirDeclaredUnit() {
        XCTAssertEqual(
            SportVocab.forSport("tennis_atp_us_open").totalsUnit(
                quotedBy: ["Helioevaara/Patten vs. Arnaldi/Struff: Total Sets O/U 2.5",
                           "Krawietz/Puetz vs. Rojer/Winegar: Total Sets O/U 2.5"]),
            "sets")
    }

    /// An empty map, and a list of nameless rungs, both fall back to the sport.
    func testEmptyAndNilNamesFallBackToTheSport() {
        let tennis = SportVocab.forSport("tennis_atp")
        XCTAssertEqual(tennis.totalsUnit(quotedBy: []), "games")
        XCTAssertEqual(tennis.totalsUnit(quotedBy: [nil, nil]), "games")
        XCTAssertEqual(tennis.totalsUnit(quotedBy: [""]), "games")
        XCTAssertNil(SportVocab.declaredUnit(inMarketName: nil))
    }

    // MARK: - The title and the rail read the same selector as the subtitle

    /// Found on the LOOK of this fix, not by a test — the Braves–Phillies map
    /// read **"Runs map"** over **"Projected total bases"**. Every test was
    /// green while the card contradicted itself in two adjacent lines.
    func testMapTitleFollowsTheMarketNotTheSport() {
        let mlb = SportVocab.forSport("baseball_mlb")
        let bases = ["Bryce Harper: Total Bases O/U 3.5",
                     "Drake Baldwin: Total Bases O/U 4.5"]
        XCTAssertEqual(mlb.totalTitle, "Runs map", "the sport's own title is unchanged")
        XCTAssertEqual(mlb.totalTitle(quotedBy: bases), "Bases map",
                       "…but this card's rungs are bases, and its title has to say so")
        XCTAssertEqual(mlb.totalsUnit(quotedBy: bases), "bases",
                       "title and subtitle must agree — they are one sentence to a reader")
    }

    /// The sport's own phrasing is returned verbatim wherever it still applies,
    /// so no surface that was already right moves.
    func testMapTitleIsUntouchedWhereTheSportStillSpeaksForTheMarket() {
        XCTAssertEqual(
            SportVocab.forSport("tennis_atp").totalTitle(
                quotedBy: ["Shelton vs. Hurkacz: Match O/U 36.5"]), "Games map")
        XCTAssertEqual(
            SportVocab.forSport("baseball_mlb").totalTitle(
                quotedBy: ["St. Louis vs Colorado: Total Runs"]), "Runs map")
        XCTAssertEqual(
            SportVocab.forSport("basketball_wnba").totalTitle(quotedBy: []), "Points map")
        XCTAssertEqual(
            SportVocab.forSport("cricket_the_hundred").totalTitle(quotedBy: []), "Scoring map",
            "an undeclared sport keeps the title that names no unit at all")
    }

    /// A card that cannot state one unit must not assert one in its title.
    func testMixedMapTitleNamesNoUnit() {
        XCTAssertEqual(
            SportVocab.forSport("tennis_wta_us_open").totalTitle(
                quotedBy: ["Iga Swiatek vs. Nadia Podoroska: Total Sets O/U 2.5",
                           "Swiatek vs. Podoroska: Set 1 Games O/U 8.5"]),
            "Scoring map")
    }

    /// `totalRange` is documented as a span "in ``unit``", so it cannot be lent
    /// to a map quoted in something else — that is #3503's defect with a
    /// different literal. The bases map was drawn on baseball's 4…14 RUNS rail.
    func testSportSpanIsWithheldFromAMapQuotedInAnotherUnit() {
        let mlb = SportVocab.forSport("baseball_mlb")
        XCTAssertEqual(mlb.totalRange, 4...14)
        XCTAssertNil(mlb.totalRange(quotedBy: ["Bryce Harper: Total Bases O/U 3.5"]),
                     "4…14 runs is not a bases span; the rail must come from the lines")
        XCTAssertEqual(mlb.totalRange(quotedBy: ["St. Louis vs Colorado: Total Runs"]), 4...14,
                       "a runs map keeps the runs span")
        XCTAssertNil(
            SportVocab.forSport("tennis_atp").totalRange(
                quotedBy: ["Marrero vs. Kasnikowski: Total Sets O/U 2.5"]),
            "12…48 games would put a 2.5-SET line at the very bottom of a games rail")
        XCTAssertEqual(
            SportVocab.forSport("tennis_atp").totalRange(
                quotedBy: ["Shelton vs. Hurkacz: Match O/U 36.5"]), 12...48)
    }

    // MARK: - The derived allowlist

    /// `knownUnits` narrows ONE ambiguous position, and it is derived from the
    /// table so that declaring a sport extends it for free. If someone
    /// hand-writes it into a literal list this test is what notices.
    func testKnownUnitsIsDerivedFromTheTable() {
        XCTAssertEqual(SportVocab.knownUnits,
                       ["runs", "goals", "games", "points", "sets"],
                       "every unit in the table, plus every scoreboard unit — and nothing typed twice")
        for unit in SportVocab.knownUnits {
            XCTAssertEqual(SportVocab.declaredUnit(inMarketName: "Someone vs. Someone: \(unit) O/U 4.5"),
                           unit,
                           "a unit the table knows must be readable in the ambiguous position")
        }
    }
}
