import Foundation

/// #12417 — what Siri's "Get Probability" and Spotlight offer for one search
/// response, read from the server's `answer` (search answer contract v0,
/// #12290). This reads the answer; it never makes one. A bare team, a
/// sentence or a set is the server's to understand, so Siri and the Search
/// tab can't disagree.
///
/// - `game`: the one game. Siri answers it at once.
/// - `outcome`: the market with the outcome the answer named. Siri answers for
///   that outcome without asking "Which outcome?".
/// - `market`: the whole market. Siri asks "Which outcome?".
/// - `set`: the set's first few games, a short list to choose from.
/// - `list`: today's list, when `answer` is null, a best guess (`exact: false`,
///   the guess first) or missing the object its kind promises.
nonisolated enum SearchAnswerPlan12417 {
    case game(GameOrMarketEntity10873)
    case outcome(GameOrMarketEntity10873)
    case market(GameOrMarketEntity10873)
    case set([GameOrMarketEntity10873])
    case list([GameOrMarketEntity10873])

    /// A set reads as a short list: enough to choose from without a page read aloud.
    static let setLimit = 5

    var entities: [GameOrMarketEntity10873] {
        switch self {
        case .game(let entity), .outcome(let entity), .market(let entity): return [entity]
        case .set(let entities), .list(let entities): return entities
        }
    }

    /// The plan's name, for tests and for the table on #12417.
    var name: String {
        switch self {
        case .game: return "game"
        case .outcome: return "outcome"
        case .market: return "market"
        case .set: return "set"
        case .list: return "list"
        }
    }

    static func plan(for response: SearchResponse) -> SearchAnswerPlan12417 {
        let list = GameOrMarketCatalog10873.listEntities(from: response)
        guard let answer = response.answer, let read = read(answer, facets: response.sports ?? []) else {
            return .list(list)
        }
        guard answer.exact else {
            // A best guess is offered first, never spoken as the answer.
            let guess = read.entities.first
            return .list((guess.map { [$0] } ?? []) + list.filter { $0.id != guess?.id })
        }
        return read
    }

    /// The answer as a plan, or nil when the object its kind promises is missing.
    private static func read(_ answer: SearchAnswer12417, facets: [SportFacet]) -> SearchAnswerPlan12417? {
        switch answer.kind {
        case .game:
            return answer.game.map { .game(GameOrMarketCatalog10873.gameEntity($0, facets: facets)) }
        case .outcome:
            guard let market = answer.market, let outcome = answer.outcome else { return nil }
            return .outcome(GameOrMarketCatalog10873.marketEntity(market, outcome: outcome))
        case .market:
            return answer.market.map { .market(GameOrMarketCatalog10873.marketEntity($0)) }
        case .set:
            guard let items = answer.set?.items, !items.isEmpty else { return nil }
            return .set(items.prefix(setLimit).map { GameOrMarketCatalog10873.gameEntity($0, facets: facets) })
        }
    }
}
