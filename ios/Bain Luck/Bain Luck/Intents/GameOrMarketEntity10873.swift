import AppIntents
import Foundation

/// #10873 — the one identity Siri and Shortcuts may pick: a game (`/events/<id>`)
/// or a market (`/futures/<id>`). Only what the three actions need — no general
/// entity layer.
///
/// The identifier IS the canonical id ("game-15320337", "market-63856441"), so
/// a saved shortcut re-resolves to the same row and nothing is matched by name.
/// The subtitle carries what tells two same-named rows apart (league, status,
/// date, source), because Siri's "Which one?" list is the only place a reader
/// can tell the Tuesday game from the Wednesday game.
nonisolated struct GameOrMarketEntity10873: AppEntity {
    enum Kind: String, Sendable {
        case game
        case market
    }

    let kind: Kind
    let recordID: Int
    let title: String
    let detail: String?

    var id: String { Self.identifier(kind: kind, recordID: recordID) }

    static let typeDisplayRepresentation: TypeDisplayRepresentation = "Game or Market"
    static let defaultQuery = GameOrMarketQuery10873()

    var displayRepresentation: DisplayRepresentation {
        if let detail {
            return DisplayRepresentation(title: "\(title)", subtitle: "\(detail)")
        }
        return DisplayRepresentation(title: "\(title)")
    }

    /// The link the app's own router already opens for this row.
    var link: URL? {
        switch kind {
        case .game: return IntentLinks10873.event(id: recordID)
        case .market: return IntentLinks10873.market(id: recordID)
        }
    }

    static func identifier(kind: Kind, recordID: Int) -> String {
        "\(kind.rawValue)-\(recordID)"
    }

    /// Parses an identifier back into its kind and id; nil for anything else.
    static func reference(_ identifier: String) -> (kind: Kind, recordID: Int)? {
        let parts = identifier.split(separator: "-", omittingEmptySubsequences: false)
        guard parts.count == 2,
              let kind = Kind(rawValue: String(parts[0])),
              let id = Int(parts[1]), id > 0,
              String(id) == parts[1] else { return nil }
        return (kind, id)
    }
}

nonisolated struct GameOrMarketQuery10873: EntityStringQuery {
    func entities(for identifiers: [String]) async throws -> [GameOrMarketEntity10873] {
        var found: [GameOrMarketEntity10873] = []
        for identifier in identifiers {
            guard let ref = GameOrMarketEntity10873.reference(identifier) else { continue }
            do {
                found.append(try await GameOrMarketCatalog10873.entity(kind: ref.kind, recordID: ref.recordID))
            } catch APIError.httpError(let status, _) where status == 404 {
                continue // gone: no stand-in is offered under its name
            }
        }
        return found
    }

    /// Every match the canonical search returns, ranked as search ranks them.
    /// Never narrowed to the first hit: when more than one comes back, the
    /// system asks the reader which one.
    func entities(matching string: String) async throws -> [GameOrMarketEntity10873] {
        try await GameOrMarketCatalog10873.search(string)
    }

    /// No suggestions. Saved pins belong to whoever is signed in, and a list
    /// built from them could outlive a sign-out, so nothing private is offered
    /// here. The reader names what they want.
    func suggestedEntities() async throws -> [GameOrMarketEntity10873] { [] }
}

/// Builds entities from the app's existing search and detail reads.
enum GameOrMarketCatalog10873 {
    /// Per kind. Enough to disambiguate a series or a daily repeat without
    /// reading a whole results page aloud.
    static let perKindLimit = 10

    static func search(_ text: String) async throws -> [GameOrMarketEntity10873] {
        let query = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !query.isEmpty else { return [] }
        let response = try await APIClient.shared.fetchSearch(query: query)
        return entities(from: response)
    }

    static func entities(from response: SearchResponse) -> [GameOrMarketEntity10873] {
        let facets = response.sports ?? []
        let games = response.results.prefix(perKindLimit).map { event in
            GameOrMarketEntity10873(
                kind: .game,
                recordID: event.id,
                title: ProbabilityAnswer10873.matchup(away: event.awayTeam, home: event.homeTeam),
                detail: gameDetail(
                    league: sportKeyDisplayName(event.sport, facets: facets),
                    status: event.status,
                    authorityPeriod: event.authorityPeriod,
                    commenceTime: event.commenceTime,
                    startIsTbd: event.startIsTbd == true))
        }
        // Families first, as search draws them, then the flat rows; each market once.
        var seen = Set<Int>()
        var markets: [SearchFuturesMarket] = []
        for family in response.futuresFamilies ?? [] {
            for market in [family.headline] + family.members where seen.insert(market.id).inserted {
                markets.append(market)
            }
        }
        for market in response.futures where seen.insert(market.id).inserted {
            markets.append(market)
        }
        let marketEntities = markets.prefix(perKindLimit).map { market in
            GameOrMarketEntity10873(
                kind: .market,
                recordID: market.id,
                title: market.name,
                detail: marketDetail(
                    category: market.llmSportCategory ?? market.category,
                    source: market.source,
                    status: market.status,
                    resolutionDate: market.resolutionDate))
        }
        return Array(games) + Array(marketEntities)
    }

    static func entity(kind: GameOrMarketEntity10873.Kind, recordID: Int) async throws -> GameOrMarketEntity10873 {
        switch kind {
        case .game:
            return entity(from: try await APIClient.shared.fetchEvent(id: recordID))
        case .market:
            return entity(from: try await APIClient.shared.fetchFuturesDetail(
                id: recordID, representation: .verifiedTitle))
        }
    }

    static func entity(from event: EventDetail) -> GameOrMarketEntity10873 {
        GameOrMarketEntity10873(
            kind: .game,
            recordID: event.id,
            title: ProbabilityAnswer10873.matchup(away: event.awayTeam, home: event.homeTeam),
            detail: gameDetail(
                league: sportKeyDisplayName(event.sport, facets: []),
                status: event.status,
                authorityPeriod: event.espn?.period,
                commenceTime: event.commenceTime,
                startIsTbd: event.startIsTbd == true))
    }

    static func entity(from market: FuturesMarketDetail) -> GameOrMarketEntity10873 {
        GameOrMarketEntity10873(
            kind: .market,
            recordID: market.id,
            title: market.name,
            detail: marketDetail(
                category: market.llmSportCategory ?? market.category,
                source: market.source,
                status: market.status,
                resolutionDate: market.resolutionDate))
    }

    /// "MLB · Final · Oct 14, 2026", "NFL · Oct 18, 1:00 PM", "MLB · Live".
    static func gameDetail(
        league: String?, status: String?, authorityPeriod: String?,
        commenceTime: String?, startIsTbd: Bool, now: Date = Date()
    ) -> String? {
        var parts: [String] = []
        if let league, !league.isEmpty { parts.append(league) }
        if status == "live" {
            parts.append("Live")
        } else if EventState.isFinished(status) {
            parts.append("Final")
        } else if EventState.isSuspendedAndStarted(status, commenceTime: commenceTime?.asDate, now: now) {
            // #4021: a future-dated suspended row is not a stopped game yet.
            parts.append(EventState.suspendedLabel(authorityPeriod: authorityPeriod))
        }
        if EventState.isFinished(status) {
            if let date = commenceTime?.asDate {
                parts.append(date.formatted(.dateTime.month(.abbreviated).day().year()))
            }
        } else if status != "live",
                  let start = ProbabilityAnswer10873.startText(commenceTime: commenceTime, startIsTbd: startIsTbd) {
            parts.append(start)
        }
        return parts.isEmpty ? nil : parts.joined(separator: " · ")
    }

    /// "Politics · Kalshi · Resolves Nov 3, 2026", "Soccer · Polymarket · Settled".
    static func marketDetail(
        category: String?, source: String?, status: String?, resolutionDate: String?
    ) -> String? {
        var parts: [String] = []
        if let category, !category.isEmpty { parts.append(sportCategoryDisplayName(category)) }
        // The same title can be listed by two venues; the venue tells them apart.
        if let source, let label = SourceLabels.label(for: source) { parts.append(label) }
        if status == "resolved" {
            parts.append(EventState.venueSettledLabel)
        } else if let deadline = CalendarDeadline.format(resolutionDate, style: .monthDayYear) {
            parts.append("Resolves \(deadline)")
        }
        return parts.isEmpty ? nil : parts.joined(separator: " · ")
    }
}

/// #10873 — one named outcome of the chosen game or market: a team, or a
/// market's listed outcome. Its identifier carries its subject's identifier,
/// so an outcome saved with one game can never answer for another.
nonisolated struct OutcomeEntity10873: AppEntity {
    let subjectID: String
    /// "home"/"away" for a game, the outcome's id for a market.
    let key: String
    let name: String
    let subjectTitle: String

    var id: String { "\(subjectID)-\(key)" }

    static let typeDisplayRepresentation: TypeDisplayRepresentation = "Outcome"
    static let defaultQuery = OutcomeQuery10873()

    var displayRepresentation: DisplayRepresentation {
        DisplayRepresentation(title: "\(name)", subtitle: "\(subjectTitle)")
    }

    /// Splits "game-123-home" into ("game-123", "home"); nil for anything else.
    static func reference(_ identifier: String) -> (subjectID: String, key: String)? {
        let parts = identifier.split(separator: "-", omittingEmptySubsequences: false)
        guard parts.count == 3 else { return nil }
        let subjectID = "\(parts[0])-\(parts[1])"
        guard let subject = GameOrMarketEntity10873.reference(subjectID) else { return nil }
        let key = String(parts[2])
        switch subject.kind {
        case .game:
            guard GameSide10873(rawValue: key) != nil else { return nil }
        case .market:
            guard let id = Int(key), id > 0, String(id) == key else { return nil }
        }
        return (subjectID, key)
    }

    /// The outcomes a reader may choose from, in the order the detail lists them:
    /// a game's two teams away-then-home (its matchup's order), a market's
    /// outcomes by printed chance, highest first (the market page's headline order).
    static func options(for event: EventDetail) -> [OutcomeEntity10873] {
        let subject = GameOrMarketEntity10873.identifier(kind: .game, recordID: event.id)
        let title = ProbabilityAnswer10873.matchup(away: event.awayTeam, home: event.homeTeam)
        return GameSide10873.allCases.map { side in
            OutcomeEntity10873(
                subjectID: subject, key: side.rawValue,
                name: side == .home ? event.homeTeam : event.awayTeam,
                subjectTitle: title)
        }
    }

    static func options(for market: FuturesMarketDetail) -> [OutcomeEntity10873] {
        let subject = GameOrMarketEntity10873.identifier(kind: .market, recordID: market.id)
        let ordered = market.outcomes.sorted { a, b in
            let lhs = a.probability ?? -1
            let rhs = b.probability ?? -1
            if lhs != rhs { return lhs > rhs }
            return a.id < b.id
        }
        return ordered.map { outcome in
            OutcomeEntity10873(
                subjectID: subject, key: String(outcome.id),
                name: outcome.name, subjectTitle: market.name)
        }
    }
}

nonisolated struct OutcomeQuery10873: EntityQuery {
    @IntentParameterDependency<GetProbabilityIntent10873>(\.$subject)
    var intent

    func entities(for identifiers: [String]) async throws -> [OutcomeEntity10873] {
        var found: [OutcomeEntity10873] = []
        for identifier in identifiers {
            guard let ref = OutcomeEntity10873.reference(identifier),
                  let subject = GameOrMarketEntity10873.reference(ref.subjectID) else { continue }
            do {
                let options = try await OutcomeCatalog10873.options(kind: subject.kind, recordID: subject.recordID)
                if let match = options.first(where: { $0.id == identifier }) { found.append(match) }
            } catch APIError.httpError(let status, _) where status == 404 {
                continue
            }
        }
        return found
    }

    /// The chosen game's or market's own outcomes, and nothing before one is chosen.
    func suggestedEntities() async throws -> [OutcomeEntity10873] {
        guard let subject = intent?.subject else { return [] }
        return try await OutcomeCatalog10873.options(kind: subject.kind, recordID: subject.recordID)
    }
}

enum OutcomeCatalog10873 {
    static func options(kind: GameOrMarketEntity10873.Kind, recordID: Int) async throws -> [OutcomeEntity10873] {
        switch kind {
        case .game:
            return OutcomeEntity10873.options(for: try await APIClient.shared.fetchEvent(id: recordID))
        case .market:
            return OutcomeEntity10873.options(for: try await APIClient.shared.fetchFuturesDetail(
                id: recordID, representation: .verifiedTitle))
        }
    }
}
