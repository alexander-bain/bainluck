import AppIntents
import Foundation

// #11664 — "Ask Bain Luck if the Patriots win this weekend." Siri names the
// team's game this weekend first, its day and opponent, then says what the game
// page shows (`ProbabilityAnswer10873.game`: a current chance, a dated last
// reading, or the result once it is final), and opens that page. With no game
// this weekend it says so and names the next one.
//
// Alex's defaults (#11664 step 0, in force until he answers): NFL teams only;
// "this weekend" runs from Saturday 00:00 to Monday 00:00 on the phone's clock,
// and on a Saturday or Sunday it is the current weekend, finished games
// included. Apple requires the app's name in every phrase, so a bare "What are
// the Patriots' chances?" is not a phrase Siri can listen for.

/// The 32 NFL teams Siri may name. Each raw value is the team page's slug,
/// checked against `GET /api/teams/{slug}` on 2026-11-08: all 32 answered with
/// that slug, the name `teamName` builds, and `americanfootball_nfl`. Synonyms
/// are nicknames, unique across the league; a city two teams share (New York,
/// Los Angeles) is never one.
nonisolated enum SupportedTeam11664: String, AppEnum, CaseIterable {
    case arizonaCardinals = "arizona-cardinals"
    case atlantaFalcons = "atlanta-falcons"
    case baltimoreRavens = "baltimore-ravens"
    case buffaloBills = "buffalo-bills"
    case carolinaPanthers = "carolina-panthers"
    case chicagoBears = "chicago-bears"
    case cincinnatiBengals = "cincinnati-bengals"
    case clevelandBrowns = "cleveland-browns"
    case dallasCowboys = "dallas-cowboys"
    case denverBroncos = "denver-broncos"
    case detroitLions = "detroit-lions"
    case greenBayPackers = "green-bay-packers"
    case houstonTexans = "houston-texans"
    case indianapolisColts = "indianapolis-colts"
    case jacksonvilleJaguars = "jacksonville-jaguars"
    case kansasCityChiefs = "kansas-city-chiefs"
    case lasVegasRaiders = "las-vegas-raiders"
    case losAngelesChargers = "los-angeles-chargers"
    case losAngelesRams = "los-angeles-rams"
    case miamiDolphins = "miami-dolphins"
    case minnesotaVikings = "minnesota-vikings"
    case newEnglandPatriots = "new-england-patriots"
    case newOrleansSaints = "new-orleans-saints"
    case newYorkGiants = "new-york-giants"
    case newYorkJets = "new-york-jets"
    case philadelphiaEagles = "philadelphia-eagles"
    case pittsburghSteelers = "pittsburgh-steelers"
    case sanFrancisco49ers = "san-francisco-49ers"
    case seattleSeahawks = "seattle-seahawks"
    case tampaBayBuccaneers = "tampa-bay-buccaneers"
    case tennesseeTitans = "tennessee-titans"
    case washingtonCommanders = "washington-commanders"

    static let typeDisplayRepresentation: TypeDisplayRepresentation = "NFL Team"

    static let caseDisplayRepresentations: [SupportedTeam11664: DisplayRepresentation] = [
        .arizonaCardinals: DisplayRepresentation(title: "Arizona Cardinals", synonyms: ["Cardinals", "Cards"]),
        .atlantaFalcons: DisplayRepresentation(title: "Atlanta Falcons", synonyms: ["Falcons"]),
        .baltimoreRavens: DisplayRepresentation(title: "Baltimore Ravens", synonyms: ["Ravens"]),
        .buffaloBills: DisplayRepresentation(title: "Buffalo Bills", synonyms: ["Bills"]),
        .carolinaPanthers: DisplayRepresentation(title: "Carolina Panthers", synonyms: ["Panthers"]),
        .chicagoBears: DisplayRepresentation(title: "Chicago Bears", synonyms: ["Bears"]),
        .cincinnatiBengals: DisplayRepresentation(title: "Cincinnati Bengals", synonyms: ["Bengals"]),
        .clevelandBrowns: DisplayRepresentation(title: "Cleveland Browns", synonyms: ["Browns"]),
        .dallasCowboys: DisplayRepresentation(title: "Dallas Cowboys", synonyms: ["Cowboys"]),
        .denverBroncos: DisplayRepresentation(title: "Denver Broncos", synonyms: ["Broncos"]),
        .detroitLions: DisplayRepresentation(title: "Detroit Lions", synonyms: ["Lions"]),
        .greenBayPackers: DisplayRepresentation(title: "Green Bay Packers", synonyms: ["Packers"]),
        .houstonTexans: DisplayRepresentation(title: "Houston Texans", synonyms: ["Texans"]),
        .indianapolisColts: DisplayRepresentation(title: "Indianapolis Colts", synonyms: ["Colts"]),
        .jacksonvilleJaguars: DisplayRepresentation(title: "Jacksonville Jaguars", synonyms: ["Jaguars", "Jags"]),
        .kansasCityChiefs: DisplayRepresentation(title: "Kansas City Chiefs", synonyms: ["Chiefs"]),
        .lasVegasRaiders: DisplayRepresentation(title: "Las Vegas Raiders", synonyms: ["Raiders"]),
        .losAngelesChargers: DisplayRepresentation(title: "Los Angeles Chargers", synonyms: ["Chargers"]),
        .losAngelesRams: DisplayRepresentation(title: "Los Angeles Rams", synonyms: ["Rams"]),
        .miamiDolphins: DisplayRepresentation(title: "Miami Dolphins", synonyms: ["Dolphins"]),
        .minnesotaVikings: DisplayRepresentation(title: "Minnesota Vikings", synonyms: ["Vikings"]),
        .newEnglandPatriots: DisplayRepresentation(title: "New England Patriots", synonyms: ["Patriots", "Pats"]),
        .newOrleansSaints: DisplayRepresentation(title: "New Orleans Saints", synonyms: ["Saints"]),
        .newYorkGiants: DisplayRepresentation(title: "New York Giants", synonyms: ["Giants"]),
        .newYorkJets: DisplayRepresentation(title: "New York Jets", synonyms: ["Jets"]),
        .philadelphiaEagles: DisplayRepresentation(title: "Philadelphia Eagles", synonyms: ["Eagles"]),
        .pittsburghSteelers: DisplayRepresentation(title: "Pittsburgh Steelers", synonyms: ["Steelers"]),
        .sanFrancisco49ers: DisplayRepresentation(title: "San Francisco 49ers", synonyms: ["49ers", "Niners"]),
        .seattleSeahawks: DisplayRepresentation(title: "Seattle Seahawks", synonyms: ["Seahawks"]),
        .tampaBayBuccaneers: DisplayRepresentation(title: "Tampa Bay Buccaneers", synonyms: ["Buccaneers", "Bucs"]),
        .tennesseeTitans: DisplayRepresentation(title: "Tennessee Titans", synonyms: ["Titans"]),
        .washingtonCommanders: DisplayRepresentation(title: "Washington Commanders", synonyms: ["Commanders"]),
    ]

    /// The name the server writes on the team's games ("San Francisco 49ers").
    var teamName: String {
        rawValue.split(separator: "-").map { $0.prefix(1).uppercased() + $0.dropFirst() }.joined(separator: " ")
    }
}

/// "This weekend" on the phone's clock.
nonisolated enum WeekendWindow11664 {
    /// Saturday 00:00 up to Monday 00:00: the current weekend on a Saturday or
    /// Sunday, otherwise the next one. Days are added on the calendar, so a
    /// daylight-saving weekend is 49 or 47 hours long, not 48.
    static func window(at now: Date, timeZone: TimeZone = .current) -> DateInterval {
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = timeZone
        let today = calendar.startOfDay(for: now)
        let weekday = calendar.component(.weekday, from: today) // 1 Sunday … 7 Saturday
        let start = calendar.date(byAdding: .day, value: weekday == 1 ? -1 : 7 - weekday, to: today) ?? today
        let end = calendar.date(byAdding: .day, value: 2, to: start) ?? start.addingTimeInterval(2 * 86_400)
        return DateInterval(start: start, end: end)
    }
}

/// One of the team's games, as the pick reads it.
nonisolated struct WeekendGame11664: Equatable, Sendable {
    let id: Int
    let homeTeam: String
    let awayTeam: String
    let start: Date
    /// Over, by `EventState.isFinished`.
    let finished: Bool
    /// Postponed or canceled by the authority (`EventState.authorityStoppageLabel`).
    let stopped: Bool

    func isIn(_ window: DateInterval) -> Bool { window.start <= start && start < window.end }
}

/// Which game "this weekend" means for one team. Never the first search hit:
/// the team's own listed games, by day, with postponed and canceled ones out.
nonisolated enum WeekendGamePick11664: Equatable, Sendable {
    /// Exactly one game this weekend, and the team's side in it.
    case one(WeekendGame11664, side: GameSide10873)
    /// No game this weekend, and the team's next listed game, if there is one.
    case noGame(next: WeekendGame11664?)
    /// More than one game this weekend: the reader chooses.
    case several([WeekendGame11664])
    /// One game this weekend that names the team on neither side.
    case sideUnclear(WeekendGame11664)

    static func pick(team: String, games: [WeekendGame11664], window: DateInterval, now: Date) -> Self {
        var seen = Set<Int>()
        let listed = games.filter { !$0.stopped && seen.insert($0.id).inserted }
        let weekend = listed.filter { $0.isIn(window) }.sorted { $0.start < $1.start }
        switch weekend.count {
        case 0:
            let next = listed.filter { !$0.finished && $0.start > now && side(of: team, in: $0) != nil }
                .min { $0.start < $1.start }
            return .noGame(next: next)
        case 1:
            guard let side = side(of: team, in: weekend[0]) else { return .sideUnclear(weekend[0]) }
            return .one(weekend[0], side: side)
        default:
            return .several(weekend)
        }
    }

    /// The team's side, by its exact served name; nil when neither side or
    /// both sides carry it.
    static func side(of team: String, in game: WeekendGame11664) -> GameSide10873? {
        switch (game.homeTeam == team, game.awayTeam == team) {
        case (true, false): return .home
        case (false, true): return .away
        default: return nil
        }
    }
}

/// What Siri says about a weekend game, built on the game page's own answer.
enum WeekendChanceAnswer11664 {
    static func game(_ event: EventDetail, side: GameSide10873, now: Date,
                     timeZone: TimeZone = .current, locale: Locale = .current) -> String {
        let answer = ProbabilityAnswer10873.game(event, side: side, now: now)
        return "\(lead(event, side: side, timeZone: timeZone, locale: locale)) \(answer.text)"
    }

    /// "This weekend: Sunday, Nov 8, at home against the Green Bay Packers."
    static func lead(_ event: EventDetail, side: GameSide10873,
                     timeZone: TimeZone = .current, locale: Locale = .current) -> String {
        let opponent = side == .home ? event.awayTeam : event.homeTeam
        let place = side == .home ? "at home against the \(opponent)" : "at the \(opponent)"
        guard let start = event.commenceTime?.asDate else { return "This weekend, \(place)." }
        return "This weekend: \(day(start, timeZone: timeZone, locale: locale)), \(place)."
    }

    /// "The New England Patriots have no game this weekend. Their next game is
    /// Sunday, Nov 15, at the Detroit Lions."
    static func noGame(team: String, next: WeekendGame11664,
                       timeZone: TimeZone = .current, locale: Locale = .current) -> String {
        let opponent = next.homeTeam == team ? "against the \(next.awayTeam)" : "at the \(next.homeTeam)"
        return "The \(team) have no game this weekend. Their next game is \(day(next.start, timeZone: timeZone, locale: locale)), \(opponent)."
    }

    static func sideUnclear(team: String, game: WeekendGame11664,
                            timeZone: TimeZone = .current, locale: Locale = .current) -> String {
        "This weekend: \(day(game.start, timeZone: timeZone, locale: locale)), \(ProbabilityAnswer10873.matchup(away: game.awayTeam, home: game.homeTeam)). Bain Luck can't tell which side is the \(team), so here is the game."
    }

    /// The game's day on the phone's clock, the window's own clock.
    static func day(_ date: Date, timeZone: TimeZone, locale: Locale) -> String {
        var style = Date.FormatStyle(date: .omitted, time: .omitted, locale: locale, timeZone: timeZone)
            .weekday(.wide).month(.abbreviated).day()
        style.calendar = Calendar(identifier: .gregorian)
        return date.formatted(style)
    }
}

nonisolated struct WeekendChanceFailure11664: Error, CustomLocalizedStringResourceConvertible {
    let message: String

    init(_ message: String) {
        self.message = message
    }

    var localizedStringResource: LocalizedStringResource { "\(message)" }
}

struct GetWeekendChanceIntent11664: AppIntent {
    static let title: LocalizedStringResource = "Get Weekend Chance"
    static let description = IntentDescription(
        "Says when an NFL team plays this weekend and against whom, then the chance Bain Luck shows, or the result once it's final, and opens the game.")

    @Parameter(title: "Team", requestValueDialog: "Which team?")
    var team: SupportedTeam11664

    /// Asked for only when the team has more than one game this weekend.
    @Parameter(title: "Game")
    var game: GameOrMarketEntity10873?

    static var parameterSummary: some ParameterSummary {
        Summary("Get the \(\.$team) chance this weekend")
    }

    @MainActor
    func perform() async throws -> some IntentResult & ReturnsValue<String> & ProvidesDialog & OpensIntent {
        let now = Date()
        let window = WeekendWindow11664.window(at: now)
        let name = team.teamName
        let page: TeamPageResponse
        do {
            page = try await APIClient.shared.fetchTeamPage(slug: team.rawValue)
        } catch {
            throw WeekendChanceFailure11664(ProbabilityAnswer10873.failure(error, subject: name).text)
        }

        // A weekend game is read from its own game page, the answer's source, so
        // a postponement or a new date on that page decides before Siri speaks.
        let listed = Self.games(from: page.upcomingEvents + page.recentEvents)
        var pages: [Int: EventDetail] = [:]
        var checked: [WeekendGame11664] = []
        for candidate in listed where candidate.isIn(window) && pages[candidate.id] == nil {
            do {
                let event = try await APIClient.shared.fetchEvent(id: candidate.id)
                pages[candidate.id] = event
                checked.append(Self.game(from: event) ?? candidate)
            } catch APIError.httpError(let status, _) where status == 404 {
                continue
            } catch {
                throw WeekendChanceFailure11664(ProbabilityAnswer10873.failure(error, subject: name).text)
            }
        }
        let rest = listed.filter { !$0.isIn(window) && pages[$0.id] == nil }

        switch WeekendGamePick11664.pick(team: name, games: checked + rest, window: window, now: now) {
        case .one(let chosen, let side):
            guard let event = pages[chosen.id] else { throw Self.noAnswer(name) }
            let text = WeekendChanceAnswer11664.game(event, side: side, now: now)
            return .result(value: text, opensIntent: Self.open(GameOrMarketCatalog10873.entity(from: event)),
                           dialog: IntentDialog("\(text)"))
        case .sideUnclear(let chosen):
            guard let event = pages[chosen.id] else { throw Self.noAnswer(name) }
            let text = WeekendChanceAnswer11664.sideUnclear(team: name, game: chosen)
            return .result(value: text, opensIntent: Self.open(GameOrMarketCatalog10873.entity(from: event)),
                           dialog: IntentDialog("\(text)"))
        case .noGame(let next):
            guard let next else {
                throw WeekendChanceFailure11664("The \(name) have no game this weekend, and Bain Luck lists no upcoming game for them.")
            }
            let text = WeekendChanceAnswer11664.noGame(team: name, next: next)
            let entity = GameOrMarketEntity10873(
                kind: .game, recordID: next.id,
                title: ProbabilityAnswer10873.matchup(away: next.awayTeam, home: next.homeTeam), detail: nil)
            return .result(value: text, opensIntent: Self.open(entity), dialog: IntentDialog("\(text)"))
        case .several(let games):
            let choices = games.compactMap { pages[$0.id].map(GameOrMarketCatalog10873.entity(from:)) }
            let chosen = try await $game.requestDisambiguation(among: choices, dialog: "Which game?")
            guard let event = pages[chosen.recordID], let picked = Self.game(from: event),
                  let side = WeekendGamePick11664.side(of: name, in: picked) else { throw Self.noAnswer(name) }
            let text = WeekendChanceAnswer11664.game(event, side: side, now: now)
            return .result(value: text, opensIntent: Self.open(chosen), dialog: IntentDialog("\(text)"))
        }
    }

    private static func open(_ subject: GameOrMarketEntity10873) -> OpenGameOrMarketIntent10873 {
        var intent = OpenGameOrMarketIntent10873()
        intent.subject = subject
        return intent
    }

    private static func noAnswer(_ team: String) -> WeekendChanceFailure11664 {
        WeekendChanceFailure11664("Bain Luck couldn't read the \(team) game this weekend.")
    }

    static func games(from events: [SearchEvent]) -> [WeekendGame11664] {
        events.compactMap { event in
            guard let start = event.commenceTime?.asDate else { return nil }
            return WeekendGame11664(id: event.id, homeTeam: event.homeTeam, awayTeam: event.awayTeam, start: start,
                                    finished: EventState.isFinished(event.status),
                                    stopped: EventState.authorityStoppageLabel(event.espn?.period) != nil)
        }
    }

    static func game(from event: EventDetail) -> WeekendGame11664? {
        guard let start = event.commenceTime?.asDate else { return nil }
        return WeekendGame11664(id: event.id, homeTeam: event.homeTeam, awayTeam: event.awayTeam, start: start,
                                finished: EventState.isFinished(event.status),
                                stopped: EventState.authorityStoppageLabel(event.espn?.period) != nil)
    }
}
