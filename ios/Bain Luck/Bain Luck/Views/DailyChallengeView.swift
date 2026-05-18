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
