import Combine
import Foundation
import os.log
import WatchKit

private let logger = Logger(subsystem: "com.bainluck.watch", category: "Guess")

@MainActor
final class WatchGuessViewModel: ObservableObject {
    @Published var loading = true
    @Published var currentQuestion: GuessQuestion?
    @Published var lastResult: GuessResult?
    @Published var streak: Int?
    @Published var error: String?
    /// Non-disruptive flag: the last guess was scored locally but not persisted to
    /// the backend. The result UI still shows; this just makes a failed save
    /// diagnosable instead of silently swallowed (L2-180).
    @Published var lastSaveFailed = false

    private var questions: [GuessQuestion] = []
    private var currentIndex = 0

    func loadQuestions(force: Bool = false) async {
        logger.info("Guess loadQuestions started (force=\(force))")
        loading = true
        error = nil
        defer { loading = false }

        do {
            let feed = try await WatchAPIClient.shared.fetchFeed(limit: 8, forceRefresh: force)
            logger.info("Guess feed received: \(feed.items.count) items")
            // Futures-only pool — an event id must never be submitted as market_id
            // (L2-180, mirrors web L2-178). See WatchGuessPool.
            questions = WatchGuessPool.buildQuestions(from: feed.items)
            logger.info("Guess: \(self.questions.count) questions from \(feed.items.count) items")
            questions.shuffle()
            currentIndex = 0
            currentQuestion = questions.first
        } catch {
            logger.error("Guess load failed: \(error.localizedDescription)")
            self.error = "Couldn't load"
            questions = []
            currentQuestion = nil
        }

        // Load streak
        do {
            let stats = try await WatchAPIClient.shared.fetchPredictionStats()
            logger.info("Guess streak loaded: \(stats.currentStreak ?? 0)")
            streak = stats.currentStreak
        } catch {
            logger.error("Guess streak fetch failed: \(error.localizedDescription)")
        }
    }

    func submitGuess(_ guess: String) async {
        guard let q = currentQuestion else { return }
        let isCorrect = guess == "higher" ? q.actualPct > q.threshold : q.actualPct < q.threshold
        lastResult = GuessResult(correct: isCorrect, guess: guess)
        lastSaveFailed = false

        // Haptic feedback
        WKInterfaceDevice.current().play(isCorrect ? .success : .failure)

        // Submit to backend. q.id is always a FuturesMarket.id (WatchGuessPool is
        // futures-only), so this is a valid market_id.
        do {
            _ = try await WatchAPIClient.shared.submitPrediction(
                marketId: q.id,
                guess: guess,
                threshold: q.threshold,
                actualProbability: q.actualProb,
                correct: isCorrect,
                category: q.category
            )
            let stats = try await WatchAPIClient.shared.fetchPredictionStats()
            streak = stats.currentStreak
        } catch {
            // Don't disrupt the result UI, but never swallow silently: surface a
            // diagnosable state + log so a failed save is visible (L2-180).
            lastSaveFailed = true
            logger.error("Guess submit failed for market \(q.id): \(error.localizedDescription)")
        }
    }

    func nextQuestion() {
        lastResult = nil
        currentIndex += 1
        if currentIndex < questions.count {
            currentQuestion = questions[currentIndex]
        } else {
            currentQuestion = nil
        }
    }
}
