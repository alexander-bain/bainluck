import XCTest
@testable import Bain_Luck

/// Ruling 208-A, second pass. Alex's voice test: "the next Patriots game" listed
/// George Mason and Arlington Baptist under "Other Basketball" and no New
/// England game, because their games were sooner. A team name finds the pro
/// team first, then a pinned team, and answers with that team's one live or
/// next game; the phrases carry the team; the league prints by name.
final class SiriTeamPhrases208BTests: XCTestCase {
    private let now = Date(timeIntervalSince1970: 1_950_000_000)

    // MARK: - Which team a spoken name means

    func testTheProTeamWinsOverASoonerCollegeTeam() throws {
        let teams = try Self.teams("""
        [{"id":3509,"name":"George Mason Patriots","sport_key":"basketball_ncaab","query_names_team":true},
         {"id":11,"name":"New England Patriots","sport_key":"americanfootball_nfl","query_names_team":true}]
        """)
        XCTAssertEqual(TeamGameResolver208B.chooseTeam(teams, pinnedGameTeams: [])?.id, 11)
    }

    func testAPinnedTeamBreaksATieBetweenNonProTeams() throws {
        let teams = try Self.teams("""
        [{"id":3509,"name":"George Mason Patriots","sport_key":"basketball_ncaab","query_names_team":true},
         {"id":894,"name":"Dallas Baptist Patriots","sport_key":"baseball_ncaa","query_names_team":true}]
        """)
        XCTAssertEqual(TeamGameResolver208B.chooseTeam(teams, pinnedGameTeams: ["Dallas Baptist Patriots"])?.id, 894)
        XCTAssertEqual(TeamGameResolver208B.chooseTeam(teams, pinnedGameTeams: [])?.id, 3509, "else search's first")
    }

    func testOnlyTeamsTheWordsNameAreCandidates() throws {
        let response = try Self.response(results: "[]", teams: """
        [{"id":11,"name":"New England Patriots","sport_key":"americanfootball_nfl","query_names_team":true},
         {"id":17637,"name":"St Kitts & Nevis Patriots","sport_key":"cricket_caribbean_premier_league","query_names_team":false}]
        """)
        XCTAssertEqual(TeamGameResolver208B.namedTeams(response).map(\.id), [11])
    }

    // MARK: - Which of the team's games answers

    func testTheNextGameAnswersAfterAByeEvenWhenItIsWeeksAway() throws {
        let games = try Self.events([
            (1, "New England Patriots", "Detroit Lions", "completed", -2 * 86_400),
            (2, "Los Angeles Chargers", "New England Patriots", "scheduled", 14 * 86_400),
            (3, "New England Patriots", "Buffalo Bills", "scheduled", 20 * 86_400),
            (4, "George Mason Patriots", "Princeton Tigers", "scheduled", 2 * 86_400),
        ])
        XCTAssertEqual(TeamGameResolver208B.nextOrLive(team: "New England Patriots", games: games, now: now)?.id, 2)
    }

    func testALiveGameAnswersFirstAndAFinalOnlyWhenNothingIsNext() throws {
        let live = try Self.events([
            (2, "Los Angeles Chargers", "New England Patriots", "scheduled", 86_400),
            (5, "New England Patriots", "New York Jets", "live", -3_600),
        ])
        XCTAssertEqual(TeamGameResolver208B.nextOrLive(team: "New England Patriots", games: live, now: now)?.id, 5)
        let finals = try Self.events([
            (6, "New England Patriots", "Miami Dolphins", "completed", -9 * 86_400),
            (7, "Green Bay Packers", "New England Patriots", "completed", -2 * 86_400),
        ])
        XCTAssertEqual(TeamGameResolver208B.nextOrLive(team: "New England Patriots", games: finals, now: now)?.id, 7)
    }

    func testTwoProTeamsWithOneNicknameAnswerWithWhicheverPlaysFirst() throws {
        let nfl = ProTeam208B(name: "New York Giants", nickname: "Giants", sportKey: "americanfootball_nfl")
        let mlb = ProTeam208B(name: "San Francisco Giants", nickname: "Giants", sportKey: "baseball_mlb")
        let games = try Self.events([
            (10, "San Francisco Giants", "Los Angeles Dodgers", "completed", -40 * 86_400),
            (11, "New York Giants", "Dallas Cowboys", "scheduled", 3 * 86_400),
        ])
        let picked = TeamGameResolver208B.choose([(mlb, games[0]), (nfl, games[1])])
        XCTAssertEqual(picked?.team, nfl)
        XCTAssertEqual(picked?.game.id, 11)
    }

    // MARK: - The league by name

    func testACatchAllKeyPrintsItsSportNeverOtherBasketball() {
        let facets = [SportFacet(key: "basketball_other", name: "Other Basketball", count: 6)]
        XCTAssertEqual(GameOrMarketCatalog10873.leagueName("basketball_other", facets: facets), "Basketball")
        XCTAssertEqual(GameOrMarketCatalog10873.leagueName("americanfootball_nfl", facets: []), "NFL")
        XCTAssertEqual(GameOrMarketCatalog10873.leagueName("basketball_ncaab", facets: []), "NCAAB")
    }

    // MARK: - The team inside the phrase

    func testEveryProTeamIsOneSpokenNameAndSharedNicknamesAreOneChoice() {
        XCTAssertEqual(ProTeam208B.all.count, 124)
        XCTAssertEqual(Set(ProTeam208B.all.map(\.name)).count, 124)
        let byName = Dictionary(uniqueKeysWithValues: TeamEntity208B.all.map { ($0.nickname, $0) })
        XCTAssertEqual(byName["Patriots"]?.teams.map(\.name), ["New England Patriots"])
        XCTAssertEqual(Set(byName["Giants"]?.teams.map(\.sportKey) ?? []), ["americanfootball_nfl", "baseball_mlb"])
        XCTAssertEqual(byName["Red Sox"]?.teams.map(\.name), ["Boston Red Sox"])
        XCTAssertEqual(byName["Maple Leafs"]?.teams.map(\.name), ["Toronto Maple Leafs"])
        XCTAssertEqual(byName["Athletics"]?.teams.map(\.sportKey), ["baseball_mlb"])
        XCTAssertEqual(byName["Blues"]?.teams.map(\.name), ["St Louis Blues"], "search's own spelling")
        for entity in TeamEntity208B.all {
            XCTAssertFalse(entity.teams.isEmpty)
            XCTAssertTrue(entity.teams.allSatisfy { !$0.leagueName.isEmpty }, entity.nickname)
        }
    }

    func testATypedOrSpokenTeamFindsItsEntity() {
        XCTAssertEqual(TeamQuery208B.match("the next Patriots game").map(\.nickname), ["Patriots"])
        XCTAssertEqual(TeamQuery208B.match("New England Patriots").map(\.nickname), ["Patriots"])
        XCTAssertEqual(TeamQuery208B.match("Sixers").map(\.nickname), ["76ers"])
        XCTAssertEqual(TeamQuery208B.match("Red Sox").map(\.nickname), ["Red Sox"])
    }

    func testThePhrasesCarryTheTeamAndTheRejectedOnesAreGone() throws {
        let source = try String(contentsOf: Self.repoFile("Bain Luck/Intents/BainLuckIntents10873.swift"), encoding: .utf8)
        for phrase in [
            #""Ask \(.applicationName) about the \(\.$team)""#,
            #""Ask \(.applicationName) about the \(\.$team) game""#,
            #""Ask \(.applicationName) how the \(\.$team) are doing""#,
            #""Ask \(.applicationName) if the \(\.$team) will win""#,
            #""\(.applicationName) chance""#,
        ] {
            XCTAssertTrue(source.contains(phrase), phrase)
        }
        for rejected in [
            #""Get a probability from \(.applicationName)""#,
            #""Check a chance in \(.applicationName)""#,
            #""What's the chance in \(.applicationName)""#,
        ] {
            XCTAssertFalse(source.contains(rejected), rejected)
        }
        XCTAssertTrue(source.contains("BainLuckShortcuts10873.updateAppShortcutParameters()"))
        let app = try String(contentsOf: Self.repoFile("Bain Luck/Bain_LuckApp.swift"), encoding: .utf8)
        XCTAssertTrue(app.contains("SiriPhrases208B.refreshTeamNames()"))
    }

    func testThePinnedGamesOnlyNameTeamsAndAreReadFromTheRememberedAccount() throws {
        let defaults = try XCTUnwrap(UserDefaults(suiteName: "siri208b-\(UUID().uuidString)"))
        defaults.set(try JSONEncoder().encode([7, 9]), forKey: "bainluck_pins.user.42.Events")
        XCTAssertEqual(PinManager.storedEventIDs(defaults: defaults, userID: "42"), [7, 9])
        XCTAssertEqual(PinManager.storedEventIDs(defaults: defaults, userID: nil), [])
        let games = try Self.events([(9, "Dallas Baptist Patriots", "Rice Owls", "scheduled", 86_400)])
        XCTAssertEqual(TeamGameResolver208B.pinnedGameTeams(in: games, pinned: [9]),
                       ["Dallas Baptist Patriots", "Rice Owls"])
    }

    // MARK: - Fixtures

    private static func decoder() -> JSONDecoder {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return decoder
    }

    private static func teams(_ json: String) throws -> [SearchTeam] {
        try decoder().decode([SearchTeam].self, from: Data(json.utf8))
    }

    private static func response(results: String, teams: String) throws -> SearchResponse {
        try decoder().decode(SearchResponse.self, from: Data(
            #"{"query":"Patriots","teams":\#(teams),"results":\#(results),"futures":[]}"#.utf8))
    }

    /// (id, home, away, status, start offset from the tests' `now` in seconds).
    private static func events(_ rows: [(Int, String, String, String, TimeInterval)], now: Date = Date(timeIntervalSince1970: 1_950_000_000)) throws -> [SearchEvent] {
        let format = ISO8601DateFormatter()
        let objects: [[String: Any]] = rows.map { row in
            ["id": row.0, "home_team": row.1, "away_team": row.2, "status": row.3,
             "commence_time": format.string(from: now.addingTimeInterval(row.4))]
        }
        return try decoder().decode([SearchEvent].self, from: JSONSerialization.data(withJSONObject: objects))
    }

    private static func repoFile(_ relative: String) -> URL {
        URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent().deletingLastPathComponent()
            .appendingPathComponent(relative)
    }
}
