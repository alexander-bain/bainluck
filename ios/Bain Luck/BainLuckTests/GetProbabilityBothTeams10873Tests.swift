import XCTest
@testable import Bain_Luck

/// #10873 (Nov 9) — "Get Probability" on a game answers for both teams at once,
/// so Siri has nothing more to ask once a game is picked. On Alex's phone (1.0.6
/// TestFlight) Siri stopped on "Running your shortcut" where the action used to
/// ask "Which team?".
///
/// What these pin:
///  - PARITY: each figure in the both-teams answer is exactly the one the
///    one-team answer gives that team, with the same kind (current, last
///    recorded, opening line), across the hero's branches.
///  - The truth rules hold: a finished game answers with its result in the
///    winner's words, a draw-priced match prints the home chance alone, a game
///    with no pair says so.
///  - A game never asks "Which team?" any more, and a market still asks.
///  - The read gives up at its deadline instead of leaving Siri waiting.
///
/// Unit tests of the source. They do not show Siri on a phone.
@MainActor
final class GetProbabilityBothTeams10873Tests: XCTestCase {

    // A fixed clock (gotcha #44): every stamp below is relative to this.
    private let now = ISO8601DateFormatter().date(from: "2026-10-16T18:00:00Z")!
    private let freshStamp = "2026-10-16T17:55:00Z"  // 5 min old
    private let staleGameStamp = "2026-10-16T17:00:00Z"  // past the 30 min live bound
    private let futureStart = "2026-10-16T23:05:00Z"
    private let pastStart = "2026-10-16T16:00:00Z"

    private func event(_ fields: String) throws -> EventDetail {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(EventDetail.self, from: Data("""
        {"id":15320337,"home_team":"New York Yankees","away_team":"Boston Red Sox",\(fields)}
        """.utf8))
    }

    /// One fixture per branch of the hero's price pair.
    private func pricedGames() throws -> [(String, EventDetail)] {
        [
            ("fresh, scheduled", try event("""
            "status":"scheduled","commence_time":"\(futureStart)","sport":"baseball_mlb",
            "current_odds":{"home_probability":0.345,"away_probability":0.655},
            "hero_probability_observed_at":"\(freshStamp)"
            """)),
            ("live, served percents", try event("""
            "status":"live","commence_time":"\(pastStart)","home_score":2,"away_score":3,
            "current_odds":{"home_probability":0.405,"away_probability":0.595,
                            "home_rendered_percent":40,"away_rendered_percent":60},
            "hero_probability_observed_at":"\(freshStamp)"
            """)),
            ("stale", try event("""
            "status":"live","commence_time":"\(pastStart)",
            "current_odds":{"home_probability":0.6,"away_probability":0.4},
            "hero_probability_observed_at":"\(staleGameStamp)"
            """)),
            ("undated", try event("""
            "status":"scheduled","commence_time":"\(futureStart)",
            "current_odds":{"home_probability":0.6,"away_probability":0.4}
            """)),
            ("opening line", try event("""
            "status":"scheduled","commence_time":"\(futureStart)",
            "current_odds":{"home_probability":0.55,"away_probability":0.45},
            "hero_probability":0.6,"hero_probability_away":0.4,"hero_probability_source":"opening",
            "hero_probability_observed_at":"\(freshStamp)"
            """)),
            ("postponed after the start", try event("""
            "status":"suspended","commence_time":"\(pastStart)","espn":{"period":"Postponed"},
            "current_odds":{"home_probability":0.6,"away_probability":0.4},
            "hero_probability_observed_at":"\(freshStamp)"
            """)),
        ]
    }

    func testEachTeamsFigureIsExactlyItsOneTeamAnswer() throws {
        for (name, e) in try pricedGames() {
            let both = ProbabilityAnswer10873.gameBothSides(e, now: now)
            let away = ProbabilityAnswer10873.game(e, side: .away, now: now)
            let home = ProbabilityAnswer10873.game(e, side: .home, now: now)
            let figures = try XCTUnwrap(both.figures, name)
            XCTAssertEqual(figures.away, away.figure, name)
            XCTAssertEqual(figures.home, home.figure, name)
            XCTAssertEqual(both.kind, home.kind, name)
            XCTAssertEqual(both.kind, away.kind, name)
            // Away first, the matchup's order, each name beside its own figure.
            let awayFigure = try XCTUnwrap(away.figure, name)
            let homeFigure = try XCTUnwrap(home.figure, name)
            XCTAssertTrue(both.text.contains("Boston Red Sox \(awayFigure), New York Yankees \(homeFigure)"),
                          "\(name): \(both.text)")
        }
    }

    func testTheWordingFollowsTheOneTeamAnswersPhase() throws {
        let games = Dictionary(uniqueKeysWithValues: try pricedGames())
        let fresh = ProbabilityAnswer10873.gameBothSides(try XCTUnwrap(games["fresh, scheduled"]), now: now)
        XCTAssertTrue(fresh.text.contains("current win chances. Starts"), fresh.text)

        let live = ProbabilityAnswer10873.gameBothSides(try XCTUnwrap(games["live, served percents"]), now: now)
        XCTAssertEqual(live.text, "Boston Red Sox vs New York Yankees: Boston Red Sox 60%, New York Yankees 40%, current win chances. Live: Boston Red Sox 3, New York Yankees 2.")

        let stale = ProbabilityAnswer10873.gameBothSides(try XCTUnwrap(games["stale"]), now: now)
        XCTAssertTrue(stale.text.contains("last recorded win chances, recorded"), stale.text)
        XCTAssertFalse(stale.text.contains("current"), stale.text)

        let undated = ProbabilityAnswer10873.gameBothSides(try XCTUnwrap(games["undated"]), now: now)
        XCTAssertTrue(undated.text.contains("No time was recorded"), undated.text)

        let opening = ProbabilityAnswer10873.gameBothSides(try XCTUnwrap(games["opening line"]), now: now)
        XCTAssertTrue(opening.text.contains("from the opening line. No newer price has been quoted."), opening.text)

        let postponed = ProbabilityAnswer10873.gameBothSides(try XCTUnwrap(games["postponed after the start"]), now: now)
        XCTAssertTrue(postponed.text.hasSuffix("Game status: Postponed."), postponed.text)
    }

    func testAFinishedGameAnswersWithItsResultInTheWinnersWords() throws {
        let e = try event("""
        "status":"completed","commence_time":"\(pastStart)","home_score":2,"away_score":5,
        "hero_settled_result":"away",
        "current_odds":{"home_probability":0.01,"away_probability":0.99},
        "hero_probability_observed_at":"\(freshStamp)"
        """)
        let both = ProbabilityAnswer10873.gameBothSides(e, now: now)
        XCTAssertEqual(both, ProbabilityAnswer10873.game(e, side: .away, now: now))
        XCTAssertTrue(both.text.hasPrefix("Boston Red Sox won"), both.text)
        XCTAssertNil(both.figures)
        XCTAssertFalse(both.text.contains("%"), both.text)

        let draw = try event(#""status":"completed","home_score":1,"away_score":1,"hero_settled_result":"draw""#)
        XCTAssertTrue(ProbabilityAnswer10873.gameBothSides(draw, now: now).text.contains("ended in a draw"))
    }

    func testADrawPricedMatchStillPrintsTheHomeChanceAlone() throws {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let e = try decoder.decode(EventDetail.self, from: Data("""
        {"id":15310517,"home_team":"Arsenal","away_team":"Brighton & Hove Albion",
         "status":"scheduled","commence_time":"\(futureStart)","sport":"soccer_epl",
         "current_odds":{"home_probability":0.52,"away_probability":0.48},
         "hero_probability_observed_at":"\(freshStamp)"}
        """.utf8))
        let both = ProbabilityAnswer10873.gameBothSides(e, now: now)
        XCTAssertEqual(both.figures, ProbabilityAnswer10873.Figures(away: nil, home: "52%"))
        XCTAssertEqual(both.kind, .current)
        XCTAssertTrue(both.text.contains("Arsenal 52%, current win chance."), both.text)
        XCTAssertTrue(both.text.contains("doesn't show a separate chance for Brighton & Hove Albion"), both.text)
        XCTAssertFalse(both.text.contains("48%"), "an invented complement reached Siri: \(both.text)")
    }

    func testAGameWithNoPairSaysItHasNoChancesToShow() throws {
        let e = try event(#""status":"scheduled","commence_time":"2026-10-16T23:05:00Z""#)
        let both = ProbabilityAnswer10873.gameBothSides(e, now: now)
        XCTAssertEqual(both.kind, .unavailable)
        XCTAssertNil(both.figures)
        XCTAssertTrue(both.text.contains("no chances to show"), both.text)
    }

    /// A game must not ask "Which team?" again; a market with several outcomes
    /// still asks. `perform()` reads the network, so this is held by its source.
    func testAGameNeverAsksWhichTeamAndAMarketStillAsks() throws {
        let source = try String(contentsOf: Self.appDir.appendingPathComponent("Intents/BainLuckIntents10873.swift"),
                                encoding: .utf8)
        let intent = try XCTUnwrap(source.range(of: "struct GetProbabilityIntent10873"))
        let game = try XCTUnwrap(source.range(of: "case .game:", range: intent.upperBound..<source.endIndex))
        let market = try XCTUnwrap(source.range(of: "case .market:", range: game.upperBound..<source.endIndex))
        // Code only: the branch's comment may say what it used to ask.
        let gameBranch = source[game.upperBound..<market.lowerBound]
            .split(separator: "\n").map { $0.components(separatedBy: "//")[0] }.joined(separator: "\n")
        for asking in ["choose(", "requestDisambiguation", "requestValue", "needsValueError", "Which team"] {
            XCTAssertFalse(gameBranch.contains(asking), "the game branch asks again: \(asking)")
        }
        XCTAssertTrue(gameBranch.contains("gameBothSides"), "the game branch no longer answers both teams")
        let marketEnd = source.range(of: "private func choose", range: market.upperBound..<source.endIndex)?.lowerBound
            ?? source.endIndex
        XCTAssertTrue(source[market.upperBound..<marketEnd].contains("dialog: \"Which outcome?\""),
                      "a market with several outcomes stopped asking which one")
    }

    func testTheReadGivesUpAtItsDeadline() async throws {
        let started = Date()
        do {
            let _: Int = try await IntentReadDeadline10873.run(within: 0.05) {
                try await Task.sleep(nanoseconds: 3_000_000_000)
                return 1
            }
            XCTFail("a read slower than its deadline returned")
        } catch let error as IntentReadDeadline10873.TimedOut {
            XCTAssertEqual(error, IntentReadDeadline10873.TimedOut())
        }
        XCTAssertLessThan(Date().timeIntervalSince(started), 1.5, "the deadline waited for the slow read")
        let quick: Int = try await IntentReadDeadline10873.run(within: 2) { 7 }
        XCTAssertEqual(quick, 7)
        XCTAssertEqual(IntentReadDeadline10873.seconds, 10)
    }

    private static var appDir: URL {
        URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
            .appendingPathComponent("Bain Luck")
    }
}
