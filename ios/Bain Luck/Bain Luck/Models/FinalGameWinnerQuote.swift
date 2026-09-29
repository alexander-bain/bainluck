import Foundation

/// A venue contract that remains open after the sporting result is final.
/// This never feeds Event probability, score, status, or result presentation.
nonisolated struct FinalGameWinnerQuote: Decodable, Equatable, Sendable {
    let eventId: Int
    let marketId: Int
    let marketName: String
    let source: String
    let status: String
    /// Oldest actual constituent observation, nil when any age is unknown.
    let observedAt: String?
    let outcomes: [FinalGameWinnerQuoteOutcome]

    var contributorOutcomeIds: Set<String> { Set(outcomes.map { String($0.outcomeId) }) }

    var printableProbabilities: [Int: String] {
        let percents = renderedCardPercents(outcomes.map { $0.probability })
        return Dictionary(zip(outcomes, percents).map { outcome, percent in
            (outcome.outcomeId, formatProbability(outcome.probability, renderedPercent: percent))
        }, uniquingKeysWith: { first, _ in first })
    }

    func isPresentable(eventId: Int, eventStatus: String?, closedMarketIds: Set<Int>) -> Bool {
        guard self.eventId == eventId, eventId > 0, marketId > 0,
              EventState.isFinished(eventStatus), status == "open",
              ["kalshi", "polymarket"].contains(source), !closedMarketIds.contains(marketId),
              !marketName.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
              (2...3).contains(outcomes.count),
              Set(outcomes.map(\.outcomeId)).count == outcomes.count,
              Set(outcomes.map(\.side)).count == outcomes.count,
              Set(outcomes.map(\.side)).isSuperset(of: [.home, .away]) else { return false }
        return outcomes.allSatisfy {
            $0.outcomeId > 0 && !$0.name.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                && $0.probability.isFinite && (0...1).contains($0.probability)
        }
    }
}

nonisolated struct FinalGameWinnerQuoteOutcome: Decodable, Equatable, Identifiable, Sendable {
    enum Side: String, Decodable, Equatable, Sendable { case home, away, draw }
    var id: Int { outcomeId }
    let outcomeId: Int
    let side: Side
    let name: String
    let probability: Double
    let observedAt: String?
}

/// Kept for a held page's lifetime, including quote withdrawals. A missing
/// quote is not terminal evidence; only the server's exact closed IDs are.
nonisolated struct FinalGameWinnerQuoteFence {
    private(set) var closedMarketIds: Set<Int> = []

    mutating func recordClosed(_ ids: [Int]?) {
        closedMarketIds.formUnion((ids ?? []).filter { $0 > 0 })
    }

    func visible(_ quote: FinalGameWinnerQuote?, eventId: Int, eventStatus: String?) -> FinalGameWinnerQuote? {
        guard let quote,
              quote.isPresentable(eventId: eventId, eventStatus: eventStatus,
                                  closedMarketIds: closedMarketIds) else { return nil }
        return quote
    }
}
