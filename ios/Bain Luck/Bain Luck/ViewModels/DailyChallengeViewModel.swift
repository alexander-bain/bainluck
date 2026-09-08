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
    ///
    /// #3864 item 2 — NEVER ASK A READER TO PREDICT SOMETHING THAT HAS ALREADY
    /// HAPPENED. Both the Watch (`WatchGuessPool`, L2-225) and web have carried
    /// this guard for as long as they have had a deck; the phone never has. Its
    /// whole filter was `p > 0.05, p < 0.95, id > 0` — three tests about a number
    /// and an id, and no lifecycle test of any kind. A settled card keeps a
    /// perfectly plausible-looking price, so without one the deck can serve a
    /// Higher/Lower question whose answer is fixed, and then grade the guess
    /// against it. That is Alex's standing "settled means settled", and it is the
    /// fourth payment on it in as many sessions (#3821 → #3823 → #3859 → this).
    ///
    /// 🟠 **MEASURED BEFORE BUILDING, AND THE MEASUREMENT IS NARROWER THAN THE
    /// HEADLINE.** Production, 2026-09-07 03:20 PT, against exactly what `load()`
    /// requests (`/api/feed?limit=30&offset=0&event_pct=0.35`):
    ///
    /// - Of 54 event cards over three pulls, **30 were `completed`**, and **12 of
    ///   those passed the old `p`/`id` filter** — i.e. were servable as questions.
    /// - But in the order `load()` consumes them, the **first already-decided
    ///   question sits at position 10 of 22**, and the deck is `prefix(5)`. So
    ///   today the deck does NOT serve one.
    ///
    /// 🔴 Which is the reason to build it, stated honestly: the deck's correctness
    /// here is **an accident of Discover's ranking, not a property of the Daily
    /// Challenge**. This view model applies no stale gate of its own — it takes
    /// whatever the feed hands it — and the margin is five cards. Four of the 22
    /// askable questions in a single payload are already decided. Any re-rank, or
    /// five leading cards failing the price filter, and a reader is asked to call
    /// a game that finished hours ago.
    ///
    /// The event half is ``EventState/isFinished(_:)`` and the futures half is
    /// ``FeedLifecycle/futuresIsSettled(_:now:)`` — the surfaces' own authorities,
    /// not a fourth opinion. `FeedLifecycle` is the one web's `_futuresIsSettled`
    /// mirrors field for field, and its `resolution_date` arm is the authority
    /// that actually fires in production, because gotcha #33 means a settled
    /// Kalshi market keeps `status='open'` forever.
    ///
    /// 🟠 **ITEM 1 OF #3864 IS DELIBERATELY NOT FIXED HERE.** The phone still
    /// submits an events-table id as `user_predictions.market_id`. That half has a
    /// product decision in it — futures-only would change what the Daily Challenge
    /// *contains*, since this deck is event-heavy by request — and #3864 lays out
    /// three options for Alex. This half has no decision in it, so it ships alone.
    ///
    /// - Parameter now: injected so a fixture cannot branch on the clock
    ///   (gotcha #44). `load()` takes the default.
    nonisolated static func question(
        from item: FeedItem,
        now: Date = Date()
    ) -> DailyChallengeQuestion? {
        let probability: Double?
        let fallbackHeadline: String
        let subject: String
        let id: Int
        let category: String?

        if let eventData = item.event {
            // #3864 — a decided game is not a question. `isFinished` is the
            // event page's own terminal test, kept in step with
            // `frontend/lib/eventState.ts` and the backend's `SETTLED_STATUSES`.
            // `suspended` is deliberately NOT refused: it is non-terminal, no
            // result was ever reported, and the answer is not fixed.
            guard !EventState.isFinished(eventData.status) else { return nil }
            probability = eventData.currentOdds?.homeProbability
            fallbackHeadline = "\(eventData.homeTeam) vs \(eventData.awayTeam)"
            subject = "\(eventData.homeTeam) to win"
            id = eventData.id
            // Keeps the original expression's fallback exactly, rather than
            // quietly narrowing an analytics field while fixing copy.
            category = eventData.sport ?? item.futures?.llmSportCategory
        } else if let futuresData = item.futures, let top = futuresData.topOutcomes?.first {
            // #3864 — the same refusal the Watch deck makes (L2-225), through the
            // native authority web's `_futuresIsSettled` mirrors. Four arms:
            // resolved flag, named winner, terminal status, past resolution date.
            guard !FeedLifecycle.futuresIsSettled(futuresData, now: now) else { return nil }
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
