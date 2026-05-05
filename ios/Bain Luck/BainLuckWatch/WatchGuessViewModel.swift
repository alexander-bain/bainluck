import Combine
import Foundation
import WatchKit

@MainActor
final class WatchGuessViewModel: ObservableObject {
    @Published var loading = true
    @Published var currentQuestion: GuessQuestion?
    @Published var lastResult: GuessResult?
    @Published var streak: Int?

    private var questions: [GuessQuestion] = []
    private var currentIndex = 0

    func loadQuestions() async {
        loading = true
        defer { loading = false }

        do {
            let feed = try await WatchAPIClient.shared.fetchFeed(limit: 30)
            questions = feed.items.compactMap { item -> GuessQuestion? in
                if item.type == "futures", let f = item.futures {
                    guard let leader = f.topOutcomes?.first,
                          let prob = leader.probability, prob > 0.05, prob < 0.95 else { return nil }
                    return GuessQuestion(
                        id: f.id,
                        title: f.name,
                        subject: leader.name,
                        actualProb: prob,
                        threshold: Self.generateThreshold(prob),
                        isEvent: false,
                        category: f.llmSportCategory
                    )
                } else if item.type == "event", let e = item.event {
                    guard let prob = e.currentOdds?.homeProbability,
                          prob > 0.05, prob < 0.95 else { return nil }
                    return GuessQuestion(
                        id: e.id,
                        title: "\(e.awayTeam) vs \(e.homeTeam)",
                        subject: "\(e.homeTeam) to win",
                        actualProb: prob,
                        threshold: Self.generateThreshold(prob),
                        isEvent: true,
                        category: e.sport
                    )
                }
                return nil
            }
            questions.shuffle()
            currentIndex = 0
            currentQuestion = questions.first
        } catch {
            questions = []
            currentQuestion = nil
        }

        // Load streak
        do {
            let stats = try await WatchAPIClient.shared.fetchPredictionStats()
            streak = stats.currentStreak
        } catch {}
    }

    func submitGuess(_ guess: String) async {
        guard let q = currentQuestion else { return }
        let isCorrect = guess == "higher" ? q.actualPct > q.threshold : q.actualPct < q.threshold
        lastResult = GuessResult(correct: isCorrect, guess: guess)

        // Haptic feedback
        WKInterfaceDevice.current().play(isCorrect ? .success : .failure)

        // Submit to backend
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
        } catch {}
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

    private static func generateThreshold(_ prob: Double) -> Int {
        let actual = Int((prob * 100).rounded())
        let offset = Int.random(in: 5...20)
        let direction = Bool.random()
        var threshold = direction ? actual + offset : actual - offset
        threshold = max(5, min(95, threshold))
        return threshold
    }
}
