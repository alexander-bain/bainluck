import AppIntents
import Foundation

// Ruling 208-A, second pass (Fable 3:33 PM, Nov 16). Alex's first voice test:
// "Bain Luck chance" reached the app, but "the next Patriots game" listed
// George Mason and Arlington Baptist under "Other Basketball" and no New
// England game, and Alex said of the phrases that "no human being would ever
// say them". So:
//  - a team name finds the PRO team first, then a team in the reader's pins,
//    and goes straight to that team's live or next game (one answer, no list);
//  - phrases carry the team, the way a person asks: "Ask Bain Luck about the
//    Patriots";
//  - the league prints by name, never "Other Basketball".

/// One NFL, NBA, MLB or NHL team as Siri may hear it. `name` is the team's
/// full name exactly as search serves it (checked against production search
/// on Nov 16, 2026); `nickname` is what a person says.
nonisolated struct ProTeam208B: Equatable, Sendable {
    let name: String
    let nickname: String
    let sportKey: String

    /// The leagues whose teams win a spoken name over a college or club team
    /// of the same name. Ordered by nothing: a tie between two pro teams is
    /// settled by which one plays first (`TeamGameResolver208B`).
    static let proLeagueKeys: Set<String> = [
        "americanfootball_nfl", "basketball_nba", "baseball_mlb", "icehockey_nhl",
        "basketball_wnba", "soccer_usa_mls",
    ]

    /// Nicknames that are more than the last word of the full name.
    private static let multiWordNicknames: [String: String] = [
        "Boston Red Sox": "Red Sox", "Chicago White Sox": "White Sox",
        "Toronto Blue Jays": "Blue Jays", "Portland Trail Blazers": "Trail Blazers",
        "Columbus Blue Jackets": "Blue Jackets", "Detroit Red Wings": "Red Wings",
        "Toronto Maple Leafs": "Maple Leafs", "Vegas Golden Knights": "Golden Knights",
        "Athletics": "Athletics",
    ]

    var leagueName: String {
        switch sportKey {
        case "americanfootball_nfl": return "NFL"
        case "basketball_nba": return "NBA"
        case "baseball_mlb": return "MLB"
        case "icehockey_nhl": return "NHL"
        default: return ""
        }
    }

    static func nickname(for name: String) -> String {
        multiWordNicknames[name] ?? String(name.split(separator: " ").last ?? Substring(name))
    }

    private static func league(_ key: String, _ names: String) -> [ProTeam208B] {
        names.split(separator: "|").map { name in
            ProTeam208B(name: String(name), nickname: nickname(for: String(name)), sportKey: key)
        }
    }

    static let all: [ProTeam208B] =
        league("americanfootball_nfl", "Arizona Cardinals|Atlanta Falcons|Baltimore Ravens|Buffalo Bills|Carolina Panthers|Chicago Bears|Cincinnati Bengals|Cleveland Browns|Dallas Cowboys|Denver Broncos|Detroit Lions|Green Bay Packers|Houston Texans|Indianapolis Colts|Jacksonville Jaguars|Kansas City Chiefs|Las Vegas Raiders|Los Angeles Chargers|Los Angeles Rams|Miami Dolphins|Minnesota Vikings|New England Patriots|New Orleans Saints|New York Giants|New York Jets|Philadelphia Eagles|Pittsburgh Steelers|San Francisco 49ers|Seattle Seahawks|Tampa Bay Buccaneers|Tennessee Titans|Washington Commanders")
        + league("basketball_nba", "Atlanta Hawks|Boston Celtics|Brooklyn Nets|Charlotte Hornets|Chicago Bulls|Cleveland Cavaliers|Dallas Mavericks|Denver Nuggets|Detroit Pistons|Golden State Warriors|Houston Rockets|Indiana Pacers|Los Angeles Clippers|Los Angeles Lakers|Memphis Grizzlies|Miami Heat|Milwaukee Bucks|Minnesota Timberwolves|New Orleans Pelicans|New York Knicks|Oklahoma City Thunder|Orlando Magic|Philadelphia 76ers|Phoenix Suns|Portland Trail Blazers|Sacramento Kings|San Antonio Spurs|Toronto Raptors|Utah Jazz|Washington Wizards")
        + league("baseball_mlb", "Arizona Diamondbacks|Athletics|Atlanta Braves|Baltimore Orioles|Boston Red Sox|Chicago Cubs|Chicago White Sox|Cincinnati Reds|Cleveland Guardians|Colorado Rockies|Detroit Tigers|Houston Astros|Kansas City Royals|Los Angeles Angels|Los Angeles Dodgers|Miami Marlins|Milwaukee Brewers|Minnesota Twins|New York Mets|New York Yankees|Philadelphia Phillies|Pittsburgh Pirates|San Diego Padres|San Francisco Giants|Seattle Mariners|St. Louis Cardinals|Tampa Bay Rays|Texas Rangers|Toronto Blue Jays|Washington Nationals")
        + league("icehockey_nhl", "Anaheim Ducks|Boston Bruins|Buffalo Sabres|Calgary Flames|Carolina Hurricanes|Chicago Blackhawks|Colorado Avalanche|Columbus Blue Jackets|Dallas Stars|Detroit Red Wings|Edmonton Oilers|Florida Panthers|Los Angeles Kings|Minnesota Wild|Montreal Canadiens|Nashville Predators|New Jersey Devils|New York Islanders|New York Rangers|Ottawa Senators|Philadelphia Flyers|Pittsburgh Penguins|San Jose Sharks|Seattle Kraken|St Louis Blues|Tampa Bay Lightning|Toronto Maple Leafs|Utah Mammoth|Vancouver Canucks|Vegas Golden Knights|Washington Capitals|Winnipeg Jets")

    /// What else a person calls a team. Given to Siri as synonyms only.
    static let spokenAliases: [String: [String]] = [
        "49ers": ["Niners", "Forty Niners"], "76ers": ["Sixers"], "Cavaliers": ["Cavs"],
        "Mavericks": ["Mavs"], "Timberwolves": ["Wolves"], "Trail Blazers": ["Blazers"],
        "Diamondbacks": ["D-backs"], "Athletics": ["A's"], "Canadiens": ["Habs"],
        "Buccaneers": ["Bucs"],
    ]
}

/// A team Siri can hear inside a phrase. One entity per spoken nickname, so
/// "Giants" is one choice that holds the NFL and the MLB team; whichever plays
/// first answers (`TeamGameResolver208B.choose`).
nonisolated struct TeamEntity208B: AppEntity {
    let nickname: String
    let teams: [ProTeam208B]

    var id: String { nickname }

    static let typeDisplayRepresentation: TypeDisplayRepresentation = "Team"
    static let defaultQuery = TeamQuery208B()

    var displayRepresentation: DisplayRepresentation {
        let leagues = teams.map(\.leagueName).joined(separator: " · ")
        let synonyms = (teams.map(\.name) + (ProTeam208B.spokenAliases[nickname] ?? []))
            .map { LocalizedStringResource(stringLiteral: $0) }
        return DisplayRepresentation(
            title: "\(nickname)", subtitle: "\(leagues)", image: nil, synonyms: synonyms)
    }

    static let all: [TeamEntity208B] = {
        var order: [String] = []
        var groups: [String: [ProTeam208B]] = [:]
        for team in ProTeam208B.all {
            if groups[team.nickname] == nil { order.append(team.nickname) }
            groups[team.nickname, default: []].append(team)
        }
        return order.map { TeamEntity208B(nickname: $0, teams: groups[$0] ?? []) }
    }()
}

nonisolated struct TeamQuery208B: EntityStringQuery {
    func entities(for identifiers: [String]) async throws -> [TeamEntity208B] {
        TeamEntity208B.all.filter { identifiers.contains($0.id) }
    }

    /// A typed or spoken team: its nickname, full name, city or alias.
    func entities(matching string: String) async throws -> [TeamEntity208B] {
        TeamQuery208B.match(string)
    }

    /// Every team, so Siri knows the names it may hear inside a phrase. Public
    /// league rosters only; nothing about the reader.
    func suggestedEntities() async throws -> [TeamEntity208B] { TeamEntity208B.all }

    static func match(_ string: String) -> [TeamEntity208B] {
        let said = GameOrMarketCatalog10873.spokenQuery(string).lowercased()
        guard !said.isEmpty else { return [] }
        return TeamEntity208B.all.filter { entity in
            let names = [entity.nickname] + entity.teams.map(\.name)
                + (ProTeam208B.spokenAliases[entity.nickname] ?? [])
            return names.contains { name in
                let lower = name.lowercased()
                return lower == said || said.contains(lower) || lower.contains(said) && said.count >= 4
            }
        }
    }
}

/// Which team a spoken name means, and which of its games answers.
enum TeamGameResolver208B {
    /// Ruling 208-A: pro team first, then a team in the reader's pins, then
    /// search's own first named team. `pinnedGameTeams` holds the team names
    /// of games the reader has pinned; it only breaks ties and is never said.
    nonisolated static func chooseTeam(_ named: [SearchTeam], pinnedGameTeams: Set<String>) -> SearchTeam? {
        if let pro = named.first(where: { ProTeam208B.proLeagueKeys.contains($0.sportKey ?? "") }) {
            return pro
        }
        if let pinned = named.first(where: { pinnedGameTeams.contains($0.name) }) {
            return pinned
        }
        return named.first
    }

    /// The teams search says the words actually name, in search's order.
    nonisolated static func namedTeams(_ response: SearchResponse) -> [SearchTeam] {
        (response.teams ?? []).filter { $0.queryNamesTeam == true }
    }

    nonisolated static func isLive(_ status: String?) -> Bool {
        let s = (status ?? "").lowercased()
        return s == "live" || s == "in_progress" || s == "suspended"
    }

    nonisolated static func isUpcoming(_ status: String?) -> Bool {
        let s = (status ?? "").lowercased()
        return s == "scheduled" || s == "upcoming" || s == "pregame"
    }

    /// A team's game a reader means: live now, else the soonest upcoming, else
    /// the most recent final. Only games that team plays.
    nonisolated static func nextOrLive(team: String, games: [SearchEvent], now: Date = Date()) -> SearchEvent? {
        let own = games.filter { $0.homeTeam == team || $0.awayTeam == team }
        if let live = own.first(where: { isLive($0.status) }) { return live }
        let upcoming = own.filter { isUpcoming($0.status) }.sorted {
            ($0.commenceTime?.asDate ?? .distantFuture) < ($1.commenceTime?.asDate ?? .distantFuture)
        }
        if let next = upcoming.first { return next }
        return own.filter { $0.status == "completed" || $0.status == "closed" }.max {
            ($0.commenceTime?.asDate ?? .distantPast) < ($1.commenceTime?.asDate ?? .distantPast)
        }
    }

    /// Of several teams with one nickname ("Giants"), the one playing now, else
    /// the one playing first.
    nonisolated static func choose(_ candidates: [(team: ProTeam208B, game: SearchEvent)]) -> (team: ProTeam208B, game: SearchEvent)? {
        if let live = candidates.first(where: { isLive($0.game.status) }) { return live }
        let upcoming = candidates.filter { isUpcoming($0.game.status) }.min {
            ($0.game.commenceTime?.asDate ?? .distantFuture) < ($1.game.commenceTime?.asDate ?? .distantFuture)
        }
        return upcoming ?? candidates.first
    }

    /// The team's games: its team page (all of its upcoming and recent games),
    /// or search's rows when the page can't be read.
    static func games(for team: SearchTeam, searched: [SearchEvent]) async -> [SearchEvent] {
        if let slug = team.slug, !slug.isEmpty,
           let page = try? await APIClient.shared.fetchTeamPage(slug: slug) {
            return page.upcomingEvents + page.recentEvents
        }
        return searched
    }

    /// The pinned games' team names, from the rows search already returned.
    nonisolated static func pinnedGameTeams(in games: [SearchEvent], pinned: Set<Int>) -> Set<String> {
        Set(games.filter { pinned.contains($0.id) }.flatMap { [$0.homeTeam, $0.awayTeam] })
    }

    /// One answerable game for a spoken team name, or nil when the words name
    /// no team (the caller then lists what search found).
    static func game(forSaid query: String, response: SearchResponse, now: Date = Date()) async -> SearchEvent? {
        let named = namedTeams(response)
        guard !named.isEmpty else { return nil }
        let pinnedTeams = pinnedGameTeams(in: response.results, pinned: PinManager.storedEventIDs())
        guard let team = chooseTeam(named, pinnedGameTeams: pinnedTeams) else { return nil }
        return nextOrLive(team: team.name, games: await games(for: team, searched: response.results), now: now)
    }

    /// The answering game for a team said inside a phrase.
    static func game(for entity: TeamEntity208B, now: Date = Date()) async throws -> SearchEvent? {
        var candidates: [(team: ProTeam208B, game: SearchEvent)] = []
        for team in entity.teams {
            let response = try await APIClient.shared.fetchSearch(query: team.name)
            guard let row = (response.teams ?? []).first(where: {
                $0.name.caseInsensitiveCompare(team.name) == .orderedSame && $0.sportKey == team.sportKey
            }) else { continue }
            if let game = nextOrLive(team: row.name, games: await games(for: row, searched: response.results), now: now) {
                candidates.append((team, game))
            }
        }
        return choose(candidates)?.game
    }
}

/// "Ask Bain Luck about the Patriots": the team's live or next game, answered
/// for both sides, without opening the app or asking which game.
struct TeamChanceIntent208B: AppIntent {
    static let title: LocalizedStringResource = "Ask About a Team"
    static let description = IntentDescription(
        "Says the chances Bain Luck shows for a team's live or next game. After a game, says the final score and the chances before it.")

    @Parameter(title: "Team", requestValueDialog: "Which team?")
    var team: TeamEntity208B

    static var parameterSummary: some ParameterSummary {
        Summary("Ask about the \(\.$team)")
    }

    @MainActor
    func perform() async throws -> some IntentResult & ReturnsValue<String> & ProvidesDialog {
        let answer = await answer(now: Date())
        return .result(value: answer.text, dialog: IntentDialog("\(answer.text)"))
    }

    @MainActor
    private func answer(now: Date) async -> ProbabilityAnswer10873 {
        let entity = team
        do {
            let event = try await IntentReadDeadline10873.run { () -> EventDetail? in
                guard let game = try await TeamGameResolver208B.game(for: entity, now: now) else { return nil }
                return try await APIClient.shared.fetchEvent(id: game.id)
            }
            guard let event else {
                return ProbabilityAnswer10873(
                    kind: .unavailable,
                    text: "Bain Luck has no game listed for the \(entity.nickname) right now.",
                    figure: nil)
            }
            return ProbabilityAnswer10873.gameBothSides(event, now: now)
        } catch {
            return ProbabilityAnswer10873.failure(error, subject: "the \(entity.nickname)")
        }
    }
}
