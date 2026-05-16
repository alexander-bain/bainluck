import Combine
import SwiftUI

struct DailyChallengeView: View {
    @StateObject private var vm = DailyChallengeViewModel()

    var body: some View {
        Group {
            if vm.loading {
                ProgressView("Loading today's challenge...")
            } else if vm.completed {
                completionView
            } else if let item = vm.currentItem {
                questionView(item)
            } else {
                VStack(spacing: 12) {
                    Image(systemName: "questionmark.circle")
                        .font(.largeTitle)
                        .foregroundStyle(.secondary)
                    Text("No challenges available right now.")
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                    Button("Retry") { Task { await vm.load() } }
                        .buttonStyle(.borderedProminent)
                }
            }
        }
        .navigationTitle("Daily Challenge")
        #if os(iOS)
        .navigationBarTitleDisplayMode(.inline)
        #endif
        .task { await vm.load() }
    }

    @ViewBuilder
    private func questionView(_ item: DailyChallengeItem) -> some View {
        VStack(spacing: 0) {
            progressBar

            ScrollView {
                VStack(spacing: 24) {
                    streakBadge

                    VStack(spacing: 8) {
                        Text("Question \(vm.currentIndex + 1) of \(vm.totalQuestions)")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                        Text(item.headline)
                            .font(.headline)
                            .multilineTextAlignment(.center)
                    }

                    VStack(spacing: 4) {
                        Text(item.subject)
                            .font(.subheadline)
                            .foregroundStyle(.secondary)
                        Text("\(item.threshold)%")
                            .font(.system(size: 64, weight: .bold, design: .monospaced))
                    }

                    if let result = vm.lastResult {
                        resultBanner(result)
                    } else {
                        HStack(spacing: 16) {
                            Button {
                                vm.guess("higher")
                            } label: {
                                Label("Higher", systemImage: "arrow.up")
                                    .frame(maxWidth: .infinity)
                                    .padding(.vertical, 8)
                            }
                            .buttonStyle(.borderedProminent)
                            .tint(.green)

                            Button {
                                vm.guess("lower")
                            } label: {
                                Label("Lower", systemImage: "arrow.down")
                                    .frame(maxWidth: .infinity)
                                    .padding(.vertical, 8)
                            }
                            .buttonStyle(.borderedProminent)
                            .tint(.red)
                        }
                    }
                }
                .padding()
            }
        }
    }

    private var progressBar: some View {
        GeometryReader { geo in
            ZStack(alignment: .leading) {
                Rectangle()
                    .fill(Color.systemGray5)
                Rectangle()
                    .fill(Color.orange)
                    .frame(width: geo.size.width * vm.progress)
                    .animation(.easeInOut(duration: 0.3), value: vm.progress)
            }
        }
        .frame(height: 4)
    }

    private var streakBadge: some View {
        HStack(spacing: 16) {
            VStack(spacing: 2) {
                Text("\(vm.stats?.currentStreak ?? 0)")
                    .font(.title3.weight(.bold))
                Text("Streak")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
            Divider().frame(height: 30)
            VStack(spacing: 2) {
                Text("\(vm.stats?.bestStreak ?? 0)")
                    .font(.title3.weight(.bold))
                Text("Best")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
            Divider().frame(height: 30)
            VStack(spacing: 2) {
                Text("\(vm.correctCount)/\(vm.answeredCount)")
                    .font(.title3.weight(.bold))
                Text("Today")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
        }
        .padding(.horizontal, 20)
        .padding(.vertical, 10)
        .background(Color.systemGray6, in: RoundedRectangle(cornerRadius: 12))
    }

    private func resultBanner(_ result: DailyChallengeResult) -> some View {
        VStack(spacing: 12) {
            HStack(spacing: 8) {
                Image(systemName: result.correct ? "checkmark.circle.fill" : "xmark.circle.fill")
                    .foregroundStyle(result.correct ? .green : .red)
                    .font(.title2)
                Text(result.correct ? "Correct!" : "Not quite")
                    .font(.headline)
            }
            Text("Actual: \(result.actual)%")
                .font(.subheadline)
                .foregroundStyle(.secondary)
            Button("Next") {
                vm.advance()
            }
            .buttonStyle(.borderedProminent)
        }
        .padding()
        .background(
            (result.correct ? Color.green : Color.red).opacity(0.08),
            in: RoundedRectangle(cornerRadius: 12)
        )
    }

    private var completionView: some View {
        VStack(spacing: 24) {
            Image(systemName: "trophy.fill")
                .font(.system(size: 48))
                .foregroundStyle(.orange)
            Text("Challenge Complete!")
                .font(.title2.weight(.bold))
            Text("\(vm.correctCount) of \(vm.totalQuestions) correct")
                .font(.title3)
            Text("\(Int(vm.accuracy))% accuracy")
                .font(.headline)
                .foregroundStyle(.secondary)
            streakBadge
            Button("Back to Discover") {
                vm.dismiss?()
            }
            .buttonStyle(.borderedProminent)
        }
        .padding()
    }
}

// MARK: - ViewModel

struct DailyChallengeItem {
    let id: Int
    let headline: String
    let subject: String
    let threshold: Int
    let actualProbability: Double
    let category: String?
    let marketId: Int
}

struct DailyChallengeResult {
    let correct: Bool
    let actual: Int
}

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
                    category: item.category,
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
