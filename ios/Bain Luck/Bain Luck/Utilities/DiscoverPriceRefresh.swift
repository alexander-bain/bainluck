import Foundation

nonisolated struct DiscoverPriceCards: Decodable, Sendable {
    let items: [FeedItem]
    let dispositions: [String: String]
    let builtAt: Double
}

protocol DiscoverPriceCardsProviding: Sendable {
    nonisolated func fetchDiscoverPriceCards(eventIds: [Int], marketIds: [Int]) async throws -> DiscoverPriceCards
}
extension APIClient: DiscoverPriceCardsProviding {}

/// Adopt whole authoritative price/source bodies without changing editorial
/// membership, ranking, grouping or the reader's position. Unknown clocks never
/// overrule known ordering. An omitted/refused identity is not a deletion.
nonisolated enum DiscoverPriceRefresh {
    static func marketIsResolved(_ market: FeedFuturesData) -> Bool {
        market.resolved == true || !(market.winner?.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ?? true)
            || FeedLifecycle.settledStatuses.contains((market.status ?? "").lowercased())
    }

    static func leaves(_ items: [FeedItem]) -> [FeedItem] {
        items.flatMap { item in item.bundle.map { leaves($0.items) } ?? [item] }
    }

    static func canAdopt(_ incoming: FeedItem, over held: FeedItem) -> Bool {
        guard incoming.id == held.id, incoming.type == held.type else { return false }
        if let old = held.event, let new = incoming.event {
            if EventState.isFinished(old.status), !EventState.isFinished(new.status) { return false }
            // Match results have their own authority; settling does not require
            // a new probability fold or invent an observation timestamp.
            if !EventState.isFinished(old.status), EventState.isFinished(new.status) { return true }
            // The endpoint's current_odds and provenance describe one accepted
            // hero. Fold ordering wins over response and observation clocks.
            if let prior = old.blendFoldRevision?.revision {
                guard let next = new.blendFoldRevision?.revision else { return false }
                let order = FoldRevision.compare(next, prior)
                guard order == .newer || order == .same else { return false }
                if order == .newer { return true }
            }
            if let prior = old.heroProbabilityObservedAt?.asDate {
                guard let next = new.heroProbabilityObservedAt?.asDate, next >= prior else { return false }
            }
            return true
        }
        if let old = held.futures, let new = incoming.futures {
            guard old.groupId == new.groupId, old.groupType == new.groupType,
                  old.canonicalMarketKey == new.canonicalMarketKey,
                  old.source == new.source else { return false }
            if marketIsResolved(old), !marketIsResolved(new) { return false }
            if !marketIsResolved(old), marketIsResolved(new) { return true }
            // Compare every raw leg, not max(clock) or only the displayed top N.
            // A changed divisor can legitimately change an equal-clock leg's
            // displayed normalized value when another raw leg advances.
            var priorClocks = old.outcomeObservedAt ?? [:]
            for row in old.topOutcomes ?? [] where priorClocks[String(row.id)] == nil {
                if let stamp = row.priceObservedAt { priorClocks[String(row.id)] = stamp }
            }
            var advanced = false
            for (id, raw) in priorClocks {
                guard let prior = raw?.asDate else { continue }
                let rowStamp = new.topOutcomes?.first(where: { String($0.id) == id })?.priceObservedAt
                guard let next = (new.outcomeObservedAt?[id] ?? rowStamp)?.asDate,
                      next >= prior else { return false }
                advanced = advanced || next > prior
            }
            if !priorClocks.isEmpty, !advanced {
                let oldRows = old.topOutcomes ?? []
                let newRows = new.topOutcomes ?? []
                guard oldRows.count == newRows.count,
                      zip(oldRows, newRows).allSatisfy({ $0.id == $1.id && $0.probability == $1.probability })
                else { return false }
            }
            if priorClocks.isEmpty, let prior = old.priceObservedAt?.asDate {
                guard let next = new.priceObservedAt?.asDate, next >= prior else { return false }
            }
            return true
        }
        return false
    }

    static func replacing(_ held: FeedItem, with fresh: FeedItem) -> FeedItem {
        FeedItem(type: held.type, score: held.score, reason: held.reason,
                 headline: held.headline, contextSummary: held.contextSummary,
                 event: fresh.event, futures: fresh.futures,
                 tournament: held.tournament, concept: held.concept, bundle: held.bundle,
                 personalized: held.personalized, baseScore: held.baseScore,
                 multiplier: held.multiplier, personalizationReasons: held.personalizationReasons)
    }

    static func isStrictlyNewer(_ incoming: FeedItem, than held: FeedItem) -> Bool {
        guard canAdopt(incoming, over: held) else { return false }
        if let old = held.event, let new = incoming.event,
           let prior = old.blendFoldRevision?.revision, let next = new.blendFoldRevision?.revision {
            return FoldRevision.compare(next, prior) == .newer ||
                (!EventState.isFinished(old.status) && EventState.isFinished(new.status))
        }
        return !canAdopt(held, over: incoming)
    }

    private static func acceptsWithheldEvent(_ incoming: FeedItem, over held: FeedItem) -> Bool {
        guard let old = held.event, let new = incoming.event,
              new.currentOdds == nil,
              !(EventState.isFinished(old.status) && !EventState.isFinished(new.status)),
              let prior = old.blendFoldRevision?.revision,
              let next = new.blendFoldRevision?.revision else { return false }
        let order = FoldRevision.compare(next, prior)
        return order == .newer || order == .same
    }

    /// Ordinary cached feed loads may change membership/editorials, but cannot
    /// roll an already accepted price body back to the older cached quotation.
    static func retainingPrices(_ incoming: [FeedItem], accepted: inout [String: FeedItem]) -> [FeedItem] {
        incoming.map { item in
            if let bundle = item.bundle {
                return item.withBundle(bundle.withItems(retainingPrices(bundle.items, accepted: &accepted)))
            }
            guard let held = accepted[item.id] else { return item }
            if isStrictlyNewer(item, than: held) {
                accepted[item.id] = item
                return item
            }
            return replacing(item, with: held)
        }
    }

    static func apply(_ response: DiscoverPriceCards, to painted: [FeedItem],
                      epochs: inout [String: Double]) -> [FeedItem] {
        guard response.builtAt.isFinite else { return painted }
        let replacements = Dictionary(response.items.map { ($0.id, $0) }, uniquingKeysWith: { first, _ in first })
        func replace(_ item: FeedItem) -> FeedItem {
            if let bundle = item.bundle { return item.withBundle(bundle.withItems(bundle.items.map(replace))) }
            guard let fresh = replacements[item.id],
                  ["updated", "withheld"].contains(response.dispositions[item.id]),
                  response.builtAt >= (epochs[item.id] ?? -.infinity),
                  (canAdopt(fresh, over: item) ||
                   (response.dispositions[item.id] == "withheld" && acceptsWithheldEvent(fresh, over: item)))
            else { return item }
            epochs[item.id] = response.builtAt
            return replacing(item, with: fresh)
        }
        return painted.map(replace)
    }
}
