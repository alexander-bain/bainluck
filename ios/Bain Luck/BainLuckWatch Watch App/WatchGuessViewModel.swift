import Combine
import Foundation
import os.log
#if canImport(WatchKit)
import WatchKit
#endif

private let logger = Logger(subsystem: "com.bainluck.watch", category: "Guess")

/// The lifecycle of a single guess submission. A guess is only ever *revealed*
/// (graded result + haptic + streak) after `.submitting` completes successfully;
/// a failure lands in `.failed` and offers a retry without consuming the question
/// (L2-182).
enum GuessSubmission: Equatable {
    case idle
    case submitting
    case failed
}

@MainActor
final class WatchGuessViewModel: ObservableObject {
    @Published var loading = true
    @Published var currentQuestion: GuessQuestion?
    @Published var lastResult: GuessResult?
    @Published var streak: Int?
    @Published var error: String?
    /// State of the in-flight (or last) save. Views disable Higher/Lower/Next
    /// while `.submitting` and surface a Retry affordance on `.failed`.
    @Published private(set) var submission: GuessSubmission = .idle

    private let backend: WatchGuessBackend
    private var questions: [GuessQuestion] = []
    private var currentIndex = 0
    /// The guess awaiting a successful save, kept so Retry re-submits the SAME
    /// answer for the SAME question rather than silently re-scoring.
    private var pendingGuess: String?

    init(backend: WatchGuessBackend) {
        self.backend = backend
    }

    #if os(watchOS)
    /// Production initializer — the view uses `WatchGuessViewModel()`.
    convenience init() {
        self.init(backend: WatchAPIClient.shared)
    }
    #endif

    func loadQuestions(force: Bool = false) async {
        logger.info("Guess loadQuestions started (force=\(force))")
        loading = true
        error = nil
        defer { loading = false }

        do {
            let items = try await backend.fetchFeedItems(limit: 8, forceRefresh: force)
            logger.info("Guess feed received: \(items.count) items")
            // Futures-only pool — an event id must never be submitted as market_id
            // (L2-180, mirrors web L2-178). See WatchGuessPool.
            questions = WatchGuessPool.buildQuestions(from: items)
            logger.info("Guess: \(self.questions.count) questions from \(items.count) items")
            questions.shuffle()
            currentIndex = 0
            currentQuestion = questions.first
            lastResult = nil
            submission = .idle
            pendingGuess = nil
        } catch {
            logger.error("Guess load failed: \(error.localizedDescription)")
            self.error = "Couldn't load"
            questions = []
            currentQuestion = nil
        }

        // Load streak (cosmetic — never blocks the deck).
        if let streak = try? await backend.currentStreak() {
            logger.info("Guess streak loaded: \(streak ?? 0)")
            self.streak = streak
        }
    }

    func submitGuess(_ guess: String) async {
        guard let q = currentQuestion else { return }
        // Prevent double submission while a save is already in flight.
        guard submission != .submitting else { return }
        pendingGuess = guess
        submission = .submitting

        let isCorrect = guess == "higher" ? q.actualPct > q.threshold : q.actualPct < q.threshold

        // q.id is always a FuturesMarket.id (WatchGuessPool is futures-only), so
        // this is a valid market_id.
        do {
            try await backend.submitGuess(
                marketId: q.id,
                guess: guess,
                threshold: q.threshold,
                actualProbability: q.actualProb,
                correct: isCorrect,
                category: q.category
            )
        } catch {
            // Honest failure: never reveal a graded result, consume the question,
            // advance the deck, or touch the streak. Offer a retry for the same
            // guess. No token or personal data is logged (L2-182).
            submission = .failed
            logger.error("Guess submit failed for market \(q.id): \(error.localizedDescription)")
            return
        }

        // Saved. Only now reveal the graded result + haptic + advance-ready state.
        submission = .idle
        pendingGuess = nil
        lastResult = GuessResult(correct: isCorrect, guess: guess)
        playHaptic(correct: isCorrect)

        // Streak refresh is cosmetic; a failure here must not un-save the guess.
        if let newStreak = try? await backend.currentStreak() {
            streak = newStreak
        }
    }

    /// Re-submits the same guess for the same question after a save failure.
    func retrySubmit() async {
        guard submission == .failed, let guess = pendingGuess else { return }
        await submitGuess(guess)
    }

    func nextQuestion() {
        // Never advance while a save is in flight.
        guard submission != .submitting else { return }
        lastResult = nil
        submission = .idle
        pendingGuess = nil
        currentIndex += 1
        if currentIndex < questions.count {
            currentQuestion = questions[currentIndex]
        } else {
            currentQuestion = nil
        }
    }

    private func playHaptic(correct: Bool) {
        #if canImport(WatchKit)
        WKInterfaceDevice.current().play(correct ? .success : .failure)
        #endif
    }
}
