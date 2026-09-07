import Combine
import Foundation

/// What one feed card asks, once it is known to be askable — the output of
/// ``DailyChallengeViewModel/question(from:)``, before a threshold is drawn.
///
/// Separate from ``DailyChallengeItem`` (which the view renders and which carries
/// the threshold) so that every decision about what the question SAYS is made in
/// one pure function and can be read in one place.
nonisolated struct DailyChallengeQuestion: Sendable {
    let id: Int
    let headline: String
    /// WHOSE number the card is about to show. `nil` only when the headline
    /// already says it — never an empty string, so the card cannot draw a blank
    /// line where a sentence belongs.
    let subject: String?
    let probability: Double
    let category: String?
}

@MainActor
final class DailyChallengeViewModel: ObservableObject {
    @Published private(set) var items: [DailyChallengeItem] = []
    @Published private(set) var currentIndex = 0
    @Published private(set) var loading = true
    @Published private(set) var lastResult: DailyChallengeResult?
    @Published private(set) var completed = false
    @Published private(set) var stats: PredictionStats?
    @Published private(set) var results: [DailyChallengeResult] = []
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

    /// What one feed item asks, before a threshold is drawn for it.
    ///
    /// #3858 — THE CARD SHOWED A NUMBER AND NEVER SAID WHOSE IT WAS. Photographed
    /// on `bainluck://daily` (`artifacts-native-053/LOOK-daily-phone.png`): a
    /// headline reading `Milwaukee Brewers vs Chicago Cubs`, a subject reading
    /// `Milwaukee Brewers vs Chicago Cubs`, and `56%` under both. The 56% is the
    /// HOME side's — `currentOdds.homeProbability`, chosen on purpose one line
    /// down — but the only text on screen names both clubs, so a reader has a
    /// coin's chance of reading it as the Cubs' number and nothing on the card can
    /// correct them. Naming the side is the one thing a Higher/Lower game must do.
    ///
    /// The futures branch had the identical defect one `else` later and it would
    /// have been easy to miss: the probability there belongs to the TOP OUTCOME
    /// while the subject named the MARKET, so "22%" sat under a championship
    /// question rather than under the team it belongs to. Fixing only the case in
    /// the photograph would have left the same card unanswerable on half its
    /// questions.
    ///
    /// The futures subject is the outcome's bare name, deliberately NOT suffixed
    /// with "to win" the way the event subject is. A moneyline probability really
    /// is a probability of winning; a futures market may be asking anything at
    /// all, and its top outcome is often "Yes" — "Yes to win" would be a new #3858
    /// rather than a fix for this one.
    ///
    /// Pure and static so it can be tested without a network: `load()` owns the
    /// feed call and the random threshold, this owns every decision about what the
    /// question SAYS.
    /// `nonisolated` because it is pure: no state, no network, no main-actor work.
    /// The class is `@MainActor` as a whole, which would otherwise make the copy
    /// decisions unreachable from a test without hopping — the reason this view
    /// model had no tests at all before #3858.
    nonisolated static func question(from item: FeedItem) -> DailyChallengeQuestion? {
        let probability: Double?
        let fallbackHeadline: String
        let subject: String
        let id: Int
        let category: String?

        if let eventData = item.event {
            probability = eventData.currentOdds?.homeProbability
            fallbackHeadline = "\(eventData.homeTeam) vs \(eventData.awayTeam)"
            subject = "\(eventData.homeTeam) to win"
            id = eventData.id
            // Keeps the original expression's fallback exactly, rather than
            // quietly narrowing an analytics field while fixing copy.
            category = eventData.sport ?? item.futures?.llmSportCategory
        } else if let futuresData = item.futures, let top = futuresData.topOutcomes?.first {
            probability = top.probability
            fallbackHeadline = futuresData.name
            subject = top.name
            id = futuresData.id
            category = futuresData.llmSportCategory
        } else {
            return nil
        }

        guard let p = probability, p > 0.05, p < 0.95, id > 0 else { return nil }

        let headline = item.headline ?? fallbackHeadline
        // #3858 second half — THE FALLBACK GUARANTEED A DUPLICATE. The card drew
        // `headline` and then `subject`, and `headline` fell back to the very
        // string `subject` was built from, so every item without a feed headline
        // printed one sentence twice. Naming the side fixes that for the common
        // case by making the two genuinely different; this covers the remainder,
        // where a market's name already IS its outcome. A card that would say the
        // same thing twice says it once.
        return DailyChallengeQuestion(
            id: id,
            headline: headline,
            subject: subject == headline ? nil : subject,
            probability: p,
            category: category
        )
    }

    func load() async {
        loading = true
        do {
            async let feedReq = APIClient.shared.fetchFeed(limit: 30, eventPct: 0.35)
            async let statsReq: PredictionStats? = try? APIClient.shared.fetchPredictionStats()
            let (feed, s) = try await (feedReq, statsReq)
            stats = s

            items = feed.items.compactMap { item -> DailyChallengeItem? in
                guard let question = Self.question(from: item) else { return nil }

                let threshold = Int(question.probability * 100) + [-8, -5, -3, 3, 5, 8].randomElement()!
                let clamped = max(5, min(95, threshold))

                return DailyChallengeItem(
                    id: question.id,
                    headline: question.headline,
                    subject: question.subject,
                    threshold: clamped,
                    actualProbability: question.probability,
                    category: question.category,
                    marketId: question.id
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
