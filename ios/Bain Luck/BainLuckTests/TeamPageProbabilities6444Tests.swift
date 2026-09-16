import XCTest
@testable import Bain_Luck

/// #6444 — THE TEAM PAGE DECODED ITS OWN PROBABILITIES AWAY.
///
/// Alex, on a physical phone, 2026-09-15:
///
/// > "the Red Sox team page … shows the team's next 5 games, but no associated
/// > probabilities, not even for the game which starts in an hour. Similarly,
/// > the 'Recent' section shows no probabilities."
///
/// THE DEFECT. `TeamDetailView.gameRow` drew a percentage from exactly one
/// expression — `event.currentOdds?.homeProbability` — and `GET /api/teams/{slug}`
/// has never served `current_odds`. `_format_event_brief`'s whole key set is
/// `id · home_team · away_team · home_score · away_score · status · commence_time ·
/// sport_key · is_home · opponent · win_probability · pregame_win_probability ·
/// completed_at`. `SearchEvent` named neither of the two probability fields, so
/// `Decodable` dropped them in silence and the `else if` could never bind. This
/// is #4967 one route over: that fix named the fields the *events* route serves,
/// the team rails serve two differently-named ones, and the bug survived.
///
/// 🔴 AND THE FIX HAD A TRAP IN IT. `win_probability` on a settled row is not the
/// result — it is the last mid-game blend, frozen where capture stopped, and it
/// contradicts the event page one tap away. Measured on production 2026-09-15:
///
/// | game | score | team brief | event page |
/// |---|---|---|---|
/// | 15309637 BOS (H) | 2–3 L | **0.079** | 0.0 (`source: settled`) |
/// | 15311111 BOS (H) | 4–1 W | **0.999** | 1.0 |
/// | 15312924 BOS (A) | 2–4 L | **0.036** | 0.0 |
///
/// 0 of 3 matched. So a finished row prints `pregame_win_probability` as the call
/// we made, never the current number — the rule the web card's docstring states
/// and this suite pins.
///
/// THE CORPUS IS TWO VERBATIM PRODUCTION CAPTURES (`Fixtures/`), not a sample:
/// Alex's own MLB page, and Arsenal's as the draw-priced control.
final class TeamPageProbabilities6444Tests: XCTestCase {

    // MARK: - Corpus

    private var fixtureDir: URL {
        URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .appendingPathComponent("Fixtures")
    }

    private func page(_ file: String) throws -> TeamPageResponse {
        let data = try Data(contentsOf: fixtureDir.appendingPathComponent(file))
        let decoder = JSONDecoder()
        // The app's own strategy (`APIClient.init`). Naming the fields IS the
        // decode, so a test that decoded differently would prove nothing.
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(TeamPageResponse.self, from: data)
    }

    private func redSox() throws -> TeamPageResponse {
        try page("teams-boston-red-sox-mlb.20260916.json")
    }

    private func arsenal() throws -> TeamPageResponse {
        try page("teams-arsenal-epl.20260916.json")
    }

    // MARK: - The report, reproduced and then fixed

    /// The old renderer's ONLY source of a number is absent from every row of
    /// both captures. This is the defect itself, stated as the payload fact that
    /// caused it — so the suite fails if anyone repoints the row at `currentOdds`
    /// again believing it binds.
    func testNoRowInEitherCaptureCarriesCurrentOdds() throws {
        for page in [try redSox(), try arsenal()] {
            for event in page.upcomingEvents + page.recentEvents {
                XCTAssertNil(
                    event.currentOdds,
                    "event \(event.id): the team brief does not serve current_odds — "
                    + "a row that reads it draws nothing, which is #6444"
                )
                XCTAssertNil(event.heroProbability, "event \(event.id): nor hero_probability")
            }
        }
    }

    /// Alex's five upcoming rows, one of which starts within the hour.
    func testUpcomingRowsNowCarryTheServedNumber() throws {
        let page = try redSox()
        XCTAssertEqual(page.upcomingEvents.count, 5)

        let priced = page.upcomingEvents.compactMap { TeamGameRow.livePrice($0) }
        XCTAssertEqual(priced.count, 3, "3 of Alex's 5 upcoming rows carry a server number")

        // By id, not by position: the row order is the server's and may change.
        let byID = Dictionary(uniqueKeysWithValues: page.upcomingEvents.map { ($0.id, $0) })
        XCTAssertEqual(TeamGameRow.livePrice(try XCTUnwrap(byID[15313146])), 0.485)
        XCTAssertEqual(TeamGameRow.livePrice(try XCTUnwrap(byID[15310821])), 0.515)
        XCTAssertEqual(TeamGameRow.livePrice(try XCTUnwrap(byID[15310827])), 0.455)

        // The two genuine blanks are NOT ours: 15311233 and 15312114 carry
        // `win_probability_sources = {}` and zero odds snapshots upstream
        // (an MLB attachment gap, #2693 / notice 14). A row with nothing to say
        // says nothing — it must not acquire a placeholder here.
        XCTAssertNil(TeamGameRow.livePrice(try XCTUnwrap(byID[15311233])))
        XCTAssertNil(TeamGameRow.livePrice(try XCTUnwrap(byID[15312114])))
    }

    /// The Recent rail: a result, and the call we made — never the frozen blend.
    func testRecentRowsPrintThePreGameCallAndNeverTheFrozenBlend() throws {
        let page = try redSox()
        let team = page.team.name
        XCTAssertEqual(page.recentEvents.count, 5)

        for event in page.recentEvents {
            XCTAssertNil(
                TeamGameRow.livePrice(event),
                "event \(event.id): a settled row must not print win_probability — "
                + "it is the last mid-game blend and the event page says otherwise"
            )
            XCTAssertNotNil(event.winProbability, "the field is present; the REFUSAL is the fix")
            XCTAssertNotNil(
                TeamGameRow.expectation(event, teamName: team),
                "event \(event.id): every recent row carries a pre-game number"
            )
        }
    }

    /// The three rows measured against their own event pages, by name.
    func testTheFrozenBlendWouldHaveContradictedTheEventPage() throws {
        let page = try redSox()
        let byID = Dictionary(uniqueKeysWithValues: page.recentEvents.map { ($0.id, $0) })

        // (id, team-brief win_probability, the event page's settled hero for the
        // same side, measured 2026-09-15 via /api/events/{id}).
        let measured: [(id: Int, brief: Double, eventPage: Double)] = [
            (15309637, 0.079, 0.0),   // BOS home, lost 2–3
            (15311111, 0.999, 1.0),   // BOS home, won 4–1
            (15312924, 0.036, 0.0),   // BOS away, lost 2–4
        ]
        for row in measured {
            let event = try XCTUnwrap(byID[row.id])
            XCTAssertEqual(try XCTUnwrap(event.winProbability), row.brief, accuracy: 0.0005)
            XCTAssertNotEqual(
                row.brief, row.eventPage,
                "if these ever agree the trap is gone and this test should be re-read"
            )
            XCTAssertNil(TeamGameRow.livePrice(event), "so the row prints neither")
        }
    }

    // MARK: - Orientation

    /// The served `is_home` decides the side, and the score follows it.
    func testOrientationComesFromTheServedFieldNotTheName() throws {
        let page = try redSox()
        let team = page.team.name
        let byID = Dictionary(
            uniqueKeysWithValues: (page.upcomingEvents + page.recentEvents).map { ($0.id, $0) }
        )

        // Texas 4 – 2 Boston: Boston are away and lost.
        let away = try XCTUnwrap(byID[15312924])
        XCTAssertEqual(away.isHome, false)
        XCTAssertFalse(TeamGameRow.isHome(away, teamName: team))
        XCTAssertEqual(TeamGameRow.opponent(away, teamName: team), "Texas Rangers")
        let awayResult = try XCTUnwrap(TeamGameRow.result(away, teamName: team))
        XCTAssertEqual(awayResult, TeamGameRow.Result(teamScore: 2, oppScore: 4))
        XCTAssertEqual(awayResult.char, "L")

        // Boston 4 – 1 Kansas City: Boston are home and won.
        let home = try XCTUnwrap(byID[15311111])
        XCTAssertTrue(TeamGameRow.isHome(home, teamName: team))
        XCTAssertEqual(TeamGameRow.opponent(home, teamName: team), "Kansas City Royals")
        XCTAssertEqual(
            TeamGameRow.result(home, teamName: team),
            TeamGameRow.Result(teamScore: 4, oppScore: 1)
        )
    }

    /// The served field WINS over the name comparison, which is the point of
    /// reading it: one spelling variant used to flip a row to the wrong side.
    func testServedIsHomeBeatsADisagreeingName() throws {
        let event = try decodeEvent(#"""
        {"id": 1, "home_team": "Red Sox", "away_team": "Texas Rangers",
         "home_score": 7, "away_score": 1, "status": "completed",
         "is_home": true, "opponent": "Texas Rangers",
         "win_probability": 0.9, "pregame_win_probability": 0.6}
        """#)
        // "Red Sox" != "Boston Red Sox": the name test would say AWAY and hand
        // the reader a 1–7 defeat.
        XCTAssertNotEqual(event.homeTeam, "Boston Red Sox")
        XCTAssertTrue(TeamGameRow.isHome(event, teamName: "Boston Red Sox"))
        XCTAssertEqual(
            TeamGameRow.result(event, teamName: "Boston Red Sox"),
            TeamGameRow.Result(teamScore: 7, oppScore: 1)
        )
    }

    /// With no `is_home` the fallback still answers — a search row, or any future
    /// payload that omits it, does not crash or blank.
    func testNameFallbackStillWorksWhenTheFieldIsAbsent() throws {
        let event = try decodeEvent(#"""
        {"id": 2, "home_team": "Boston Red Sox", "away_team": "Texas Rangers",
         "status": "scheduled"}
        """#)
        XCTAssertNil(event.isHome)
        XCTAssertTrue(TeamGameRow.isHome(event, teamName: "Boston Red Sox"))
        XCTAssertEqual(TeamGameRow.opponent(event, teamName: "Boston Red Sox"), "Texas Rangers")
        XCTAssertNil(TeamGameRow.livePrice(event), "no number served, none invented")
    }

    // MARK: - The draw-priced control

    /// #5363's hazard was a CLIENT-SIDE `1 − P(home)` on a three-way price. This
    /// route serves a server-oriented number off the two-way normalised blend, and
    /// the capture is the witness: for Arsenal away at Brighton the complement of
    /// the blend (0.730) and the stored away column (0.737) agree to 0.7pp. So the
    /// row prints what it is given — a second complement here would be the defect,
    /// not the guard.
    func testSoccerAwayRowIsAlreadyTeamRelative() throws {
        let page = try arsenal()
        let team = page.team.name
        XCTAssertEqual(page.team.sportKey, "soccer_epl")

        let brighton = try XCTUnwrap(page.upcomingEvents.first { $0.id == 15305234 })
        XCTAssertFalse(TeamGameRow.isHome(brighton, teamName: team), "Arsenal are away")
        XCTAssertEqual(TeamGameRow.livePrice(brighton), 0.73)
        let pre = try XCTUnwrap(brighton.pregameWinProbability)
        XCTAssertEqual(pre, 0.737, accuracy: 0.0005)
        XCTAssertEqual(
            try XCTUnwrap(TeamGameRow.livePrice(brighton)), pre, accuracy: 0.02,
            "the two independent derivations agree, so the served number needs no "
            + "client complement — taking 1 − it would print 27% for a favourite"
        )
    }

    /// Every Arsenal recent row is settled, so not one of them may print a price.
    func testNoSettledRowInEitherCapturePrintsAPrice() throws {
        for page in [try redSox(), try arsenal()] {
            for event in page.recentEvents where SettledQuote.isSettled(event.status) {
                XCTAssertNil(TeamGameRow.livePrice(event), "event \(event.id)")
            }
        }
    }

    // MARK: - What a row may claim

    /// A score is not a result. A suspended row carries the last score play
    /// reached, and grading it prints a Final nobody reported.
    func testASuspendedRowShowsItsScoreWithNoVerdictAndKeepsItsPrice() throws {
        let event = try decodeEvent(#"""
        {"id": 3, "home_team": "Boston Red Sox", "away_team": "Texas Rangers",
         "home_score": 1, "away_score": 2, "status": "suspended",
         "is_home": true, "win_probability": 0.4, "pregame_win_probability": 0.55}
        """#)
        let team = "Boston Red Sox"
        XCTAssertNil(TeamGameRow.result(event, teamName: team), "no final may be claimed")
        XCTAssertNil(TeamGameRow.expectation(event, teamName: team), "so no call to grade")
        let score = try XCTUnwrap(TeamGameRow.score(event, teamName: team))
        XCTAssertEqual(score.team, 1)
        XCTAssertEqual(score.opp, 2)
        XCTAssertEqual(TeamGameRow.livePrice(event), 0.4, "not settled, so the price stands")
    }

    /// Half a score is no score (the partial-line trap, CERT-752).
    func testHalfAScoreIsNoScore() throws {
        let event = try decodeEvent(#"""
        {"id": 4, "home_team": "Boston Red Sox", "away_team": "Texas Rangers",
         "home_score": 3, "status": "completed", "is_home": true,
         "pregame_win_probability": 0.62}
        """#)
        XCTAssertNil(TeamGameRow.score(event, teamName: "Boston Red Sox"))
        XCTAssertNil(TeamGameRow.result(event, teamName: "Boston Red Sox"))
        XCTAssertNil(
            TeamGameRow.expectation(event, teamName: "Boston Red Sox"),
            "\"we had them at 62%\" under a game whose score never arrived is the "
            + "web's #3791 defect; the gate on `result` is what stops it"
        )
    }

    /// A finished row with no pre-game number prints the result alone rather than
    /// reaching for the frozen blend to fill the space.
    func testNoPreGameNumberMeansNoLine() throws {
        let event = try decodeEvent(#"""
        {"id": 5, "home_team": "Boston Red Sox", "away_team": "Texas Rangers",
         "home_score": 5, "away_score": 2, "status": "completed", "is_home": true,
         "win_probability": 0.997}
        """#)
        XCTAssertNotNil(TeamGameRow.result(event, teamName: "Boston Red Sox"))
        XCTAssertNil(TeamGameRow.expectation(event, teamName: "Boston Red Sox"))
        XCTAssertNil(TeamGameRow.livePrice(event))
    }

    /// The upset arm, at the threshold and on both sides of it.
    func testUpsetArmFiresOnlyForAWinFromBelowTheThreshold() throws {
        func expectation(pre: Double, homeScore: Int, awayScore: Int) throws -> TeamGameRow.Expectation? {
            let event = try decodeEvent(#"""
            {"id": 6, "home_team": "Boston Red Sox", "away_team": "Texas Rangers",
             "home_score": \#(homeScore), "away_score": \#(awayScore),
             "status": "completed", "is_home": true,
             "pregame_win_probability": \#(pre)}
            """#)
            return TeamGameRow.expectation(event, teamName: "Boston Red Sox")
        }

        XCTAssertEqual(try expectation(pre: 0.2, homeScore: 4, awayScore: 1), .upset(0.2))
        XCTAssertEqual(try expectation(pre: 0.34, homeScore: 4, awayScore: 1), .upset(0.34))
        // Strictly below, as web spells it (`pre < 0.35`).
        XCTAssertEqual(try expectation(pre: 0.35, homeScore: 4, awayScore: 1), .had(0.35))
        // A LOSS from a long price is not an upset, it is the expected thing.
        XCTAssertEqual(try expectation(pre: 0.2, homeScore: 1, awayScore: 4), .had(0.2))
        // A tie is not a win.
        XCTAssertEqual(try expectation(pre: 0.2, homeScore: 2, awayScore: 2), .had(0.2))
    }

    // MARK: - The renderer

    /// The view no longer reads a key this route does not serve. A source scan,
    /// because the failure mode is textual: the next person to want a percentage
    /// here reaches for `currentOdds` exactly as the last one did.
    func testTeamDetailViewDoesNotReadCurrentOdds() throws {
        let view = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()      // BainLuckTests
            .deletingLastPathComponent()      // Bain Luck (project dir)
            .appendingPathComponent("Bain Luck/Views/TeamDetailView.swift")
        let source = try String(contentsOf: view, encoding: .utf8)
        XCTAssertTrue(source.contains("TeamGameRow.livePrice"), "the row reads the served field")

        // CODE ONLY. The doc comment above `gameRow` names `event.currentOdds`
        // to say why it is gone, and a scan that cannot tell an explanation from
        // a call fails on its own documentation — which is what this test did
        // first time out.
        let code = source
            .split(separator: "\n", omittingEmptySubsequences: false)
            .filter { !$0.trimmingCharacters(in: .whitespaces).hasPrefix("//") }
            .joined(separator: "\n")
        XCTAssertTrue(code.contains("TeamGameRow.livePrice"), "the filter kept the code")
        for call in ["event.currentOdds", ".currentOdds?"] {
            XCTAssertFalse(
                code.contains(call),
                "TeamDetailView reads \(call) again — /api/teams/{slug} does not serve it"
            )
        }
    }

    // MARK: - Helpers

    private func decodeEvent(_ json: String) throws -> SearchEvent {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(SearchEvent.self, from: Data(json.utf8))
    }
}
