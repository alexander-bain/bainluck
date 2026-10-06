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

    struct MarketFence {
        var clocks: [String: Date] = [:]
        var withdrawn: Set<String> = []
    }

    private static func observation(_ raw: String?) -> Date? {
        guard let raw else { return nil }
        guard let fraction = raw.range(of: "\\.[0-9]+(?=Z|[+-][0-9]{2}:[0-9]{2}$)", options: .regularExpression) else { return raw.asDate }
        let base = String(raw[..<fraction.lowerBound]) + String(raw[fraction.upperBound...])
        guard let date = base.asDate, let part = Double("0" + raw[fraction]) else { return nil }
        return date.addingTimeInterval(part)
    }

    private static func clocks(_ market: FeedFuturesData) -> [String: Date] {
        var result: [String: Date] = [:]
        for (id, raw) in market.outcomeObservedAt ?? [:] { if let value = observation(raw) { result[id] = value } }
        for row in market.topOutcomes ?? [] where market.outcomeObservedAt?[String(row.id)] == nil {
            if let value = observation(row.priceObservedAt) { result[String(row.id)] = value }
        }
        return result
    }

    private static func priced(_ market: FeedFuturesData, _ id: String) -> Bool {
        market.topOutcomes?.contains { String($0.id) == id && $0.probability != nil } ?? false
    }

    private static func retainingFence(_ incoming: FeedItem, over held: FeedItem, previous: MarketFence?) -> MarketFence? {
        guard let next = incoming.futures, let old = held.futures else { return nil }
        var fence = previous ?? MarketFence()
        for (id, date) in clocks(old) { fence.clocks[id] = max(fence.clocks[id] ?? .distantPast, date) }
        let nextClocks = clocks(next)
        var advanced = false
        for (id, date) in nextClocks {
            if date > (fence.clocks[id] ?? .distantPast) {
                fence.clocks[id] = date; advanced = true
                if priced(next, id) { fence.withdrawn.remove(id) }
            }
        }
        for row in old.topOutcomes ?? [] {
            let id = String(row.id)
            if priced(old, id), !priced(next, id), !advanced || nextClocks[id] == nil { fence.withdrawn.insert(id) }
        }
        // A null row is explicitly withdrawn; a missing top-N row may merely
        // have changed rank. Neither case fabricates a public observation time.
        for row in next.topOutcomes ?? [] where row.probability == nil { fence.withdrawn.insert(String(row.id)) }
        return fence
    }

    static func canAdopt(_ incoming: FeedItem, over held: FeedItem,
                         authoritative: Bool = false, fence: MarketFence? = nil) -> Bool {
        guard incoming.id == held.id, incoming.type == held.type else { return false }
        if let old = held.event, let new = incoming.event {
            if EventState.isFinished(old.status) {
                if !EventState.isFinished(new.status) { return false }
                if let score = old.homeScore, new.homeScore != score { return false }
                if let score = old.awayScore, new.awayScore != score { return false }
            }
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
                guard (old.currentOdds == nil) == (new.currentOdds == nil),
                      old.currentOdds?.homeProbability == new.currentOdds?.homeProbability,
                      old.currentOdds?.awayProbability == new.currentOdds?.awayProbability,
                      old.heroProbabilitySource == nil || old.heroProbabilitySource == new.heroProbabilitySource
                else { return false }
            }
            if let prior = observation(old.heroProbabilityObservedAt) {
                guard let next = observation(new.heroProbabilityObservedAt), next >= prior else { return false }
            }
            return true
        }
        if let old = held.futures, let new = incoming.futures {
            guard old.groupId == new.groupId, old.groupType == new.groupType,
                  old.canonicalMarketKey == new.canonicalMarketKey,
                  old.source == new.source,
                  old.externalId == nil || new.externalId == nil || old.externalId == new.externalId else { return false }
            if let winner = old.winner?.trimmingCharacters(in: .whitespacesAndNewlines), !winner.isEmpty,
               winner != new.winner?.trimmingCharacters(in: .whitespacesAndNewlines) { return false }
            if marketIsResolved(old), !marketIsResolved(new) { return false }
            if !marketIsResolved(old), marketIsResolved(new) { return true }
            // The complete normalized body is one vector. Never splice rows
            // from different divisors, nor let a fresh sibling hide a regression.
            var priorClocks = clocks(old)
            for (id, stamp) in fence?.clocks ?? [:] { priorClocks[id] = max(priorClocks[id] ?? .distantPast, stamp) }
            let nextClocks = clocks(new)
            var advanced = false
            for (id, prior) in priorClocks {
                guard let next = nextClocks[id] else {
                    if authoritative, !priced(new, id), priced(old, id) || fence?.withdrawn.contains(id) == true { continue }
                    return false
                }
                if next < prior { return false }
                advanced = advanced || next > prior
            }
            var withdrawn = fence?.withdrawn ?? []
            for row in old.topOutcomes ?? [] where row.probability == nil { withdrawn.insert(String(row.id)) }
            for id in withdrawn where priced(new, id) {
                guard let next = nextClocks[id], next > (priorClocks[id] ?? .distantPast) else { return false }
            }
            let hasVector = !priorClocks.isEmpty || !(old.outcomeObservedAt?.isEmpty ?? true)
            if hasVector, !advanced {
                let oldRows = old.topOutcomes ?? [], newRows = new.topOutcomes ?? []
                let withdrawal = authoritative && oldRows.contains { priced(old, String($0.id)) && !priced(new, String($0.id)) }
                    && newRows.allSatisfy { row in oldRows.contains { $0.id == row.id } }
                if !withdrawal {
                    guard oldRows.count == newRows.count,
                          zip(oldRows, newRows).allSatisfy({ $0.id == $1.id && $0.probability == $1.probability }) else { return false }
                }
            }
            if !hasVector, let prior = observation(old.priceObservedAt) {
                guard let next = observation(new.priceObservedAt), next >= prior else { return false }
            }
            return true
        }
        return false
    }

    /// A score read does not order prices, lifecycle, period, or other metadata.
    /// Unstamped clearing is deliberately unorderable; never borrow the quote clock.
    private static func scoreClock(_ event: FeedEventData, now: Date) -> Date? {
        guard let home = event.homeScore, let away = event.awayScore,
              home >= 0, away >= 0,
              ["espn", "statpal", "odds_api"].contains(event.scoreSource ?? ""),
              let clock = observation(event.scoreObservedAt), clock <= now else { return nil }
        return clock
    }

    private static func reconcilingScore(in body: FeedItem, incoming: FeedItem,
                                        held: FeedItem, now: Date) -> FeedItem {
        guard incoming.id == held.id, incoming.type == held.type,
              let old = held.event, let next = incoming.event, var event = body.event,
              old.id == next.id else { return body }
        // Preserve the existing final-result authority and final-score fence.
        if EventState.isFinished(event.status) { return body }
        let score: FeedEventData
        if !EventState.isFinished(old.status),
           let nextClock = scoreClock(next, now: now),
           nextClock > (scoreClock(old, now: now) ?? .distantPast) {
            score = next
        } else {
            score = old
        }
        event.homeScore = score.homeScore
        event.awayScore = score.awayScore
        event.scoreSource = score.scoreSource
        event.scoreObservedAt = score.scoreObservedAt
        return replacing(body, with: body, event: event)
    }

    static func replacing(_ held: FeedItem, with fresh: FeedItem, event: FeedEventData? = nil) -> FeedItem {
        FeedItem(type: held.type, score: held.score, reason: held.reason,
                 headline: held.headline, contextSummary: held.contextSummary,
                 event: event ?? fresh.event, futures: fresh.futures,
                 tournament: held.tournament, concept: held.concept, bundle: held.bundle,
                 personalized: held.personalized, baseScore: held.baseScore,
                 multiplier: held.multiplier, personalizationReasons: held.personalizationReasons)
    }

    static func isStrictlyNewer(_ incoming: FeedItem, than held: FeedItem, fence: MarketFence? = nil) -> Bool {
        guard canAdopt(incoming, over: held, fence: fence) else { return false }
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
        if EventState.isFinished(old.status) {
            if let score = old.homeScore, new.homeScore != score { return false }
            if let score = old.awayScore, new.awayScore != score { return false }
        }
        let order = FoldRevision.compare(next, prior)
        return order == .newer || order == .same
    }

    /// Ordinary cached feed loads may change membership/editorials, but cannot
    /// roll an already accepted price body back to the older cached quotation.
    static func retainingPrices(_ incoming: [FeedItem], accepted: inout [String: FeedItem],
                                now: Date = Date()) -> [FeedItem] {
        var fences: [String: MarketFence] = [:]
        return retainingPrices(incoming, accepted: &accepted, fences: &fences, now: now)
    }

    static func retainingPrices(_ incoming: [FeedItem], accepted: inout [String: FeedItem],
                                fences: inout [String: MarketFence], now: Date = Date()) -> [FeedItem] {
        incoming.map { item in
            if let bundle = item.bundle {
                return item.withBundle(bundle.withItems(retainingPrices(bundle.items, accepted: &accepted, fences: &fences, now: now)))
            }
            guard let held = accepted[item.id] else { return item }
            let adoptsPrice = isStrictlyNewer(item, than: held, fence: fences[item.id])
            if adoptsPrice {
                fences[item.id] = retainingFence(item, over: held, previous: fences[item.id])
            }
            let body = adoptsPrice ? item : replacing(item, with: held)
            let merged = reconcilingScore(in: body, incoming: item, held: held, now: now)
            accepted[item.id] = merged
            return merged
        }
    }

    static func apply(_ response: DiscoverPriceCards, to painted: [FeedItem],
                      epochs: inout [String: Double], now: Date = Date()) -> [FeedItem] {
        var fences: [String: MarketFence] = [:]
        return apply(response, to: painted, epochs: &epochs, fences: &fences, now: now)
    }

    static func apply(_ response: DiscoverPriceCards, to painted: [FeedItem],
                      epochs: inout [String: Double], fences: inout [String: MarketFence],
                      now: Date = Date()) -> [FeedItem] {
        guard response.builtAt.isFinite else { return painted }
        let replacements = Dictionary(response.items.map { ($0.id, $0) }, uniquingKeysWith: { first, _ in first })
        func replace(_ item: FeedItem) -> FeedItem {
            if let bundle = item.bundle { return item.withBundle(bundle.withItems(bundle.items.map(replace))) }
            guard let fresh = replacements[item.id],
                  ["updated", "withheld"].contains(response.dispositions[item.id])
            else { return item }
            let adoptsPrice = response.builtAt >= (epochs[item.id] ?? -.infinity) &&
                (canAdopt(fresh, over: item, authoritative: true, fence: fences[item.id]) ||
                 (response.dispositions[item.id] == "withheld" && acceptsWithheldEvent(fresh, over: item)))
            if adoptsPrice {
                fences[item.id] = retainingFence(fresh, over: item, previous: fences[item.id])
            }
            let body = adoptsPrice ? replacing(item, with: fresh) : item
            let merged = reconcilingScore(in: body, incoming: fresh, held: item, now: now)
            if adoptsPrice || merged.event?.scoreObservedAt != item.event?.scoreObservedAt {
                // The caller retains accepted leaves using this marker, including
                // a score-only read. Never lower the price response fence.
                epochs[item.id] = max(epochs[item.id] ?? -.infinity, response.builtAt)
            }
            return merged
        }
        return painted.map(replace)
    }
}

/// A push burst causes one read plus a trailing coalesced read, never a
/// round-trip-speed request loop. This budget spans batches and reconnects.
nonisolated struct DiscoverPriceReadPacer {
    static let minimumGap: TimeInterval = 2
    private(set) var notBefore: TimeInterval = -.infinity

    func delay(at now: TimeInterval) -> TimeInterval { max(0, notBefore - now) }

    mutating func didDispatch(at now: TimeInterval) {
        notBefore = max(notBefore, now + Self.minimumGap)
    }

    @discardableResult
    mutating func observe(_ error: Error, at now: TimeInterval) -> Bool {
        guard let api = error as? APIError,
              case .httpError(let status, let body) = api, status == 429 else { return false }
        // The middleware emits the same seconds in JSON and Retry-After.
        // Generic APIError already preserves that body; no shared error-shape
        // change is needed. Unknown/malformed cooldown falls back conservatively.
        let data = body?.data(using: .utf8)
        let object = data.flatMap { try? JSONSerialization.jsonObject(with: $0) } as? [String: Any]
        let raw = object?["retry_after"]
        let seconds = (raw as? Double) ?? (raw as? String).flatMap(Double.init)
        let pause = seconds.flatMap { $0.isFinite && $0 > 0 ? $0 : nil } ?? 60
        notBefore = max(notBefore, now + pause)
        return true
    }
}
