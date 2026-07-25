import Foundation

/// The Watch Higher/Lower flow's backend dependency, extracted as a protocol so
/// `WatchGuessViewModel` can be driven by a deterministic mock in tests (L2-182).
///
/// It is intentionally pure Foundation (no `WatchKit`, no `PredictionStats`) so
/// the file compiles into the iOS test host — that is what lets the view model
/// itself be exercised for success / failure / retry / double-tap without a
/// network. The live conformance is `WatchAPIClient` (see its extension), which
/// adapts `fetchFeed`/`submitPrediction`/`fetchPredictionStats` onto this shape.
protocol WatchGuessBackend: Sendable {
    /// The decoded feed items the question deck is built from (futures-only pool
    /// is enforced downstream by `WatchGuessPool.buildQuestions`).
    func fetchFeedItems(limit: Int, forceRefresh: Bool) async throws -> [WatchFeedItem]

    /// Persists a guess. Throws on any non-2xx / transport failure — the caller
    /// treats a throw as "not saved" and must not reveal a graded result.
    func submitGuess(
        marketId: Int,
        guess: String,
        threshold: Int,
        actualProbability: Double,
        correct: Bool,
        category: String?
    ) async throws

    /// The current streak, or nil when unavailable. This is cosmetic: a failure
    /// here must never un-save a guess that already persisted.
    func currentStreak() async throws -> Int?
}
