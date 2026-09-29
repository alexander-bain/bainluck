import Foundation

/// A market-wide maximum clock cannot order each outcome. Preserve each
/// already-observed quote and verdict before publishing the coherent detail.
nonisolated enum FuturesPriceReconciliation {
    static func isSettled(_ market: FuturesMarketDetail) -> Bool {
        FeedLifecycle.settledStatuses.contains(market.status ?? "")
            || market.outcomes.contains { $0.isWinner == true }
    }

    static func adopting(_ incoming: FuturesMarketDetail, over held: FuturesMarketDetail?) -> FuturesMarketDetail {
        guard let held else { return incoming }
        guard incoming.id == held.id else { return held }
        if isSettled(held) {
            guard isSettled(incoming) else { return held }
            let winners = Set(held.outcomes.filter { $0.isWinner == true }.map(\.id))
            if !winners.isEmpty,
               Set(incoming.outcomes.filter { $0.isWinner == true }.map(\.id)) != winners { return held }
        }
        guard Set(incoming.outcomes.map(\.id)).count == incoming.outcomes.count else { return held }
        let old = Dictionary(held.outcomes.map { ($0.id, $0) }, uniquingKeysWith: { a, _ in a })
        var preserved = false
        var outcomes = incoming.outcomes.map { outcome -> FuturesOutcome in
            guard let prior = old[outcome.id] else { return outcome }
            if prior.isWinner == true && outcome.isWinner != true
                || prior.isWinner != nil && outcome.isWinner == nil {
                preserved = true
                return prior
            }
            // A newly authoritative settlement outranks an open quote. After
            // settlement, a missing/older price clock cannot undo that verdict.
            if !isSettled(held), isSettled(incoming), outcome.isWinner != nil { return outcome }
            if let before = prior.lastUpdated?.asDate {
                guard let after = outcome.lastUpdated?.asDate, after >= before,
                      after != before || outcome.probability == prior.probability else {
                    preserved = true
                    return prior
                }
            }
            return outcome
        }
        let included = Set(outcomes.map(\.id))
        for prior in held.outcomes where !included.contains(prior.id) {
            preserved = true
            outcomes.append(prior)
        }
        guard preserved else { return incoming }
        // A retained quote cannot wear a new provider identity. Wait for a
        // fully acceptable authoritative body if the market provenance changes.
        guard incoming.source == held.source, incoming.externalId == held.externalId,
              incoming.bookmakers == held.bookmakers else { return held }
        return FuturesMarketDetail(id: incoming.id, name: incoming.name,
            description: incoming.description, sport: incoming.sport, sportName: incoming.sportName,
            category: incoming.category, llmSportCategory: incoming.llmSportCategory,
            status: incoming.status, source: held.source, externalId: held.externalId,
            mutuallyExclusive: incoming.mutuallyExclusive, commenceTime: incoming.commenceTime,
            resolutionDate: incoming.resolutionDate, updatedAt: held.updatedAt,
            outcomeCount: outcomes.count, bookmakers: held.bookmakers, outcomes: outcomes,
            hookDescription: incoming.hookDescription, imageUrl: incoming.imageUrl,
            leadOutcomeId: incoming.leadOutcomeId)
    }

    /// Only an accepted, dated new quote or authoritative result is activity.
    /// A heartbeat, invalidation, identical read or unknown clock is not one.
    static func hasNewObservation(_ incoming: FuturesMarketDetail, over held: FuturesMarketDetail) -> Bool {
        if !isSettled(held), isSettled(incoming) { return true }
        let old = Dictionary(held.outcomes.map { ($0.id, $0) }, uniquingKeysWith: { a, _ in a })
        return incoming.outcomes.contains { outcome in
            guard let after = outcome.lastUpdated?.asDate else { return false }
            guard let prior = old[outcome.id], let before = prior.lastUpdated?.asDate else { return true }
            return after > before
        }
    }
}
