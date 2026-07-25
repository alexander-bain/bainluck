import Foundation

// MARK: - Guess Question

/// A single Higher/Lower question on the Watch.
///
/// `id` is submitted to `/api/predictions` as `market_id`, which the backend and
/// every downstream stats/resolution join treat **strictly** as a
/// `FuturesMarket.id`. It must therefore only ever be a decoded futures market
/// id — never an events-table id. See `WatchGuessPool.buildQuestions`.
struct GuessQuestion {
    /// A `FuturesMarket.id`. Never an `Event.id` (see the type doc above).
    let id: Int
    let title: String
    let subject: String
    let actualProb: Double
    let threshold: Int
    let category: String?

    var actualPct: Int { Int((actualProb * 100).rounded()) }
}

/// The graded outcome of a submitted guess. Foundation-only (lives here rather
/// than in the SwiftUI view) so the view model's result-reveal path is unit
/// testable off-watchOS (L2-182).
struct GuessResult: Equatable {
    let correct: Bool
    let guess: String
}

// MARK: - Guess Pool (pure, testable)

/// Builds the Watch Higher/Lower question deck from a decoded feed.
///
/// L2-180 (mirrors the web L2-178 fix): **only** futures cards become questions.
/// An event card carries an events-table id with no linked futures-market id on
/// the feed payload; submitting it as `user_predictions.market_id` poisons stats
/// and resolution (the `FuturesOutcome` lookup misses, the client `correct` is
/// trusted, and the row joins to an unrelated market by numeric-id collision).
/// Event cards may still appear elsewhere on Watch (glances / live view) — those
/// write interactions, not predictions — but are excluded from this pool until
/// the backend exposes a typed event-prediction contract.
enum WatchGuessPool {
    /// The playable probability band for a Higher/Lower question.
    static let minProb = 0.05
    static let maxProb = 0.95

    static func buildQuestions(from items: [WatchFeedItem]) -> [GuessQuestion] {
        items.compactMap { item -> GuessQuestion? in
            // Futures only. Do NOT add an `event` branch here — see the enum doc.
            guard item.type == "futures", let f = item.futures else { return nil }
            guard let leader = f.topOutcomes?.first,
                  let prob = leader.probability,
                  prob > minProb, prob < maxProb else { return nil }
            return GuessQuestion(
                id: f.id,                 // FuturesMarket.id — the only id we ever submit
                title: f.name,
                subject: leader.name,
                actualProb: prob,
                threshold: generateThreshold(prob),
                category: f.llmSportCategory
            )
        }
    }

    static func generateThreshold(_ prob: Double) -> Int {
        let actual = Int((prob * 100).rounded())
        let offset = Int.random(in: 5...20)
        let direction = Bool.random()
        var threshold = direction ? actual + offset : actual - offset
        threshold = max(5, min(95, threshold))
        return threshold
    }
}
