import Foundation

/// A market-wide maximum clock cannot order each outcome. Preserve each
/// already-observed quote and verdict before publishing the coherent detail.
nonisolated enum FuturesPriceReconciliation {
    static func isSettled(_ market: FuturesMarketDetail) -> Bool {
        FeedLifecycle.settledStatuses.contains(market.status ?? "")
            || market.outcomes.contains { $0.isWinner == true }
    }

    /// ISO8601DateFormatter truncates submillisecond precision on some runtimes.
    /// Preserve the producer's microseconds for ordering; never display this watermark.
    static func observationDate(_ raw: String?) -> Date? {
        guard let raw else { return nil }
        guard let fraction = raw.range(of: "\\.[0-9]+(?=Z|[+-][0-9]{2}:[0-9]{2}$)", options: .regularExpression) else {
            return raw.asDate
        }
        let base = String(raw[..<fraction.lowerBound]) + String(raw[fraction.upperBound...])
        guard let date = base.asDate, let subsecond = Double("0" + raw[fraction]) else { return nil }
        return date.addingTimeInterval(subsecond)
    }

    struct Withdrawal { let lastKnownObservation: Date? }

    static func adopting(_ incoming: FuturesMarketDetail, over held: FuturesMarketDetail?) -> FuturesMarketDetail {
        var withdrawals: [Int: Withdrawal] = [:]
        return adopting(incoming, over: held, withdrawals: &withdrawals)
    }

    static func adopting(_ incoming: FuturesMarketDetail, over held: FuturesMarketDetail?,
                         withdrawals: inout [Int: Withdrawal]) -> FuturesMarketDetail {
        guard let held else {
            for outcome in incoming.outcomes where outcome.probability == nil {
                withdrawals[outcome.id] = Withdrawal(lastKnownObservation: observationDate(outcome.lastUpdated))
            }
            return incoming
        }
        guard incoming.id == held.id else { return held }
        if isSettled(held) {
            guard isSettled(incoming) else { return held }
            let winners = Set(held.outcomes.filter { $0.isWinner == true }.map(\.id))
            if !winners.isEmpty,
               Set(incoming.outcomes.filter { $0.isWinner == true }.map(\.id)) != winners { return held }
        }
        guard Set(incoming.outcomes.map(\.id)).count == incoming.outcomes.count else { return held }
        let old = Dictionary(held.outcomes.map { ($0.id, $0) }, uniquingKeysWith: { a, _ in a })
        // Displayed probabilities in a mutually exclusive field share a divisor.
        // A newer sibling can legitimately move an unchanged-clock row; adopt
        // the full nonregressive vector, never splice old/new normalized bodies.
        let normalized = incoming.mutuallyExclusive == true || held.mutuallyExclusive == true
        let normalizedChange = normalized && (held.outcomes.count != incoming.outcomes.count
            || incoming.outcomes.contains { outcome in
                guard let prior = old[outcome.id] else { return true }
                if prior.probability != nil && outcome.probability == nil { return true }
                guard let after = observationDate(outcome.lastUpdated) else { return false }
                return observationDate(prior.lastUpdated).map { after > $0 } ?? true
            })
        var nextWithdrawals = withdrawals
        var preserved = false
        var outcomes = incoming.outcomes.map { outcome -> FuturesOutcome in
            guard let prior = old[outcome.id] else {
                if outcome.probability == nil {
                    nextWithdrawals[outcome.id] = Withdrawal(lastKnownObservation: observationDate(outcome.lastUpdated))
                }
                return outcome
            }
            if prior.isWinner == true && outcome.isWinner != true
                || prior.isWinner != nil && outcome.isWinner == nil {
                preserved = true
                return prior
            }
            // A newly authoritative settlement outranks an open quote. After
            // settlement, a missing/older price clock cannot undo that verdict.
            if !isSettled(held), isSettled(incoming), outcome.isWinner != nil {
                nextWithdrawals.removeValue(forKey: outcome.id)
                return outcome
            }
            // Withholding is an authoritative absence, not a conflicting quote.
            // Keep its ordering watermark privately: the wire clock stays unknown.
            if outcome.probability == nil {
                let watermark = [observationDate(prior.lastUpdated),
                    nextWithdrawals[outcome.id]?.lastKnownObservation].compactMap { $0 }.max()
                if let watermark, let after = observationDate(outcome.lastUpdated), after < watermark {
                    preserved = true
                    return prior
                }
                nextWithdrawals[outcome.id] = Withdrawal(lastKnownObservation:
                    [watermark, observationDate(outcome.lastUpdated)].compactMap { $0 }.max())
                return outcome
            }
            if let withdrawal = nextWithdrawals[outcome.id] {
                guard let after = observationDate(outcome.lastUpdated),
                      withdrawal.lastKnownObservation.map({ after > $0 }) ?? true else {
                    preserved = true
                    return prior
                }
                nextWithdrawals.removeValue(forKey: outcome.id)
            }
            if let before = observationDate(prior.lastUpdated) {
                guard let after = observationDate(outcome.lastUpdated), after >= before,
                      after != before || outcome.probability == prior.probability || normalizedChange else {
                    preserved = true
                    return prior
                }
            }
            return outcome
        }
        let included = Set(outcomes.map(\.id))
        for prior in held.outcomes where !normalized && !included.contains(prior.id) {
            preserved = true
            outcomes.append(prior)
        }
        guard preserved else { withdrawals = nextWithdrawals; return incoming }
        if normalized { return held }
        // A retained quote cannot wear a new provider identity. Wait for a
        // fully acceptable authoritative body if the market provenance changes.
        guard incoming.source == held.source, incoming.externalId == held.externalId,
              incoming.bookmakers == held.bookmakers else { return held }
        withdrawals = nextWithdrawals
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
            guard let after = observationDate(outcome.lastUpdated) else { return false }
            guard let prior = old[outcome.id], let before = observationDate(prior.lastUpdated) else { return true }
            return after > before
        }
    }
}

/// Cooldowns are transport control, never evidence of quote freshness.
nonisolated enum FuturesPriceReadCooldown {
    static func timelineRetrySeconds(for error: APIError) -> TimeInterval? {
        guard !error.isCancellation else { return nil }
        if let seconds = seconds(for: error) { return seconds }
        switch error {
        case .networkError: return 60
        case .httpError(let code, _) where (500...599).contains(code): return 60
        default: return nil
        }
    }

    static func seconds(for error: Error) -> TimeInterval? {
        guard let api = error as? APIError,
              case .httpError(let status, let body) = api, status == 429 else { return nil }
        let data = body?.data(using: .utf8)
        let object = data.flatMap { try? JSONSerialization.jsonObject(with: $0) } as? [String: Any]
        let raw = object?["retry_after"]
        let seconds = (raw as? Double) ?? (raw as? String).flatMap(Double.init)
        return seconds.flatMap { $0.isFinite && $0 > 0 ? $0 : nil } ?? 60
    }
}
