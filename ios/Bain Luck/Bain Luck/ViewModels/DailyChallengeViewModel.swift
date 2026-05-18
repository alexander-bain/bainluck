import Combine
import Foundation

@MainActor
final class DailyChallengeViewModel: ObservableObject {
    @Published var items: [DailyChallengeItem] = []
    @Published var currentIndex = 0
    @Published var loading = true
    @Published var lastResult: DailyChallengeResult?
    @Published var completed = false
    @Published var stats: PredictionStats?
    @Published var results: [DailyChallengeResult] = []
    var dismiss: (() -> Void)?

    let totalQuestions = 5

    var currentItem: DailyChallengeItem? {
        guard currentIndex < items.count else { return nil }
        return items[currentIndex]
    }

    var progress: Double {
        guard totalQuestions > 0 else { return 0 }
        return Double(answeredCount) / Double(totalQuestions)
    }

    var answeredCount: Int { results.count }
    var correctCount: Int { results.filter(\.correct).count }
    var accuracy: Double {
        guard answeredCount > 0 else { return 0 }
        return Double(correctCount) / Double(answeredCount) * 100
    }

    func load() async {
        loading = true
        do {
            async let feedReq = APIClient.shared.fetchFeed(limit: 30, eventPct: 0.35)
            async let statsReq: PredictionStats? = try? APIClient.shared.fetchPredictionStats()
            let (feed, s) = try await (feedReq, statsReq)
            stats = s

            items = feed.items.compactMap { item -> DailyChallengeItem? in
                let prob: Double?
                let name: String
                let id: Int

                if let eventData = item.event {
                    prob = eventData.currentOdds?.homeProbability
                    name = "\(eventData.homeTeam) vs \(eventData.awayTeam)"
                    id = eventData.id
                } else if let futuresData = item.futures {
                    prob = futuresData.topOutcomes?.first?.probability
                    name = futuresData.name
                    id = futuresData.id
                } else {
                    return nil
                }

                guard let p = prob, p > 0.05, p < 0.95, id > 0 else { return nil }
                let threshold = Int(p * 100) + [-8, -5, -3, 3, 5, 8].randomElement()!
                let clamped = max(5, min(95, threshold))

                return DailyChallengeItem(
                    id: id,
                    headline: item.headline ?? name,
                    subject: name,
                    threshold: clamped,
                    actualProbability: p,
                    category: item.event?.sport ?? item.futures?.llmSportCategory,
                    marketId: id
                )
            }
            .prefix(totalQuestions)
            .map { $0 }
        } catch {
            // Silently fall through — items will be empty
        }
        loading = false
    }

    func guess(_ direction: String) {
        guard let item = currentItem else { return }
        let actual = Int(item.actualProbability * 100)
        let correct: Bool
        if direction == "higher" {
            correct = actual >= item.threshold
        } else {
            correct = actual < item.threshold
        }

        let result = DailyChallengeResult(correct: correct, actual: actual)
        results.append(result)
        lastResult = result

        Task {
            try? await APIClient.shared.submitPrediction(PredictionRequest(
                marketId: item.marketId,
                guess: direction,
                threshold: item.threshold,
                actualProbability: item.actualProbability,
                correct: correct,
                category: item.category
            ))
        }

        AnalyticsService.trackScreen(name: "daily_challenge_guess", type: "daily_challenge")
    }

    func advance() {
        lastResult = nil
        if currentIndex + 1 >= totalQuestions || currentIndex + 1 >= items.count {
            completed = true
        } else {
            currentIndex += 1
        }
    }
}
