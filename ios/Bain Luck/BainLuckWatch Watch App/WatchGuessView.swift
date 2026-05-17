import SwiftUI

struct WatchGuessView: View {
    @StateObject private var vm = WatchGuessViewModel()

    var body: some View {
        Group {
            if vm.loading {
                VStack(spacing: 10) {
                    ProgressView()
                        .scaleEffect(1.3)
                    Text("Loading...")
                        .font(.system(size: 14, weight: .medium))
                        .foregroundStyle(.secondary)
                }
            } else if let error = vm.error {
                VStack(spacing: 8) {
                    Image(systemName: "wifi.exclamationmark")
                        .font(.title2)
                        .foregroundStyle(.orange)
                    Text(error)
                        .font(.system(size: 14))
                        .foregroundStyle(.secondary)
                    Button("Retry") { Task { await vm.loadQuestions(force: true) } }
                        .font(.system(size: 13, weight: .semibold))
                }
            } else if let q = vm.currentQuestion {
                questionCard(q)
            } else {
                VStack(spacing: 8) {
                    Image(systemName: "checkmark.seal.fill")
                        .font(.title2)
                        .foregroundStyle(.orange)
                    Text("All caught up!")
                        .font(.system(size: 15, weight: .medium))
                        .foregroundStyle(.secondary)
                }
            }
        }
        .task { await vm.loadQuestions() }
        .task(id: "auto-retry") {
            while !Task.isCancelled {
                try? await Task.sleep(for: .seconds(15))
                if vm.error != nil || vm.currentQuestion == nil {
                    await vm.loadQuestions(force: true)
                }
            }
        }
    }

    @ViewBuilder
    private func questionCard(_ q: GuessQuestion) -> some View {
        if let result = vm.lastResult {
            resultView(result, q)
        } else {
            ScrollView(.vertical, showsIndicators: false) {
            VStack(spacing: 6) {
                Text("What are the odds?")
                    .font(.system(size: 12, weight: .bold))
                    .foregroundStyle(.secondary)
                    .textCase(.uppercase)

                Text(q.title)
                    .font(.system(size: 15, weight: .bold))
                    .minimumScaleFactor(0.7)
                    .multilineTextAlignment(.center)
                    .lineLimit(3)

                Text(q.subject)
                    .font(.system(size: 11))
                    .foregroundStyle(.secondary)
                    .lineLimit(2)
                    .multilineTextAlignment(.center)

                Text("\(q.threshold)%")
                    .font(.system(size: 44, weight: .heavy, design: .rounded))
                    .foregroundStyle(.blue)
                    .padding(.vertical, 2)

                HStack(spacing: 6) {
                    Button { Task { await vm.submitGuess("higher") } } label: {
                        Label("Higher", systemImage: "arrow.up")
                            .font(.system(size: 14, weight: .bold))
                            .frame(maxWidth: .infinity, minHeight: 44)
                    }
                    .tint(.green)

                    Button { Task { await vm.submitGuess("lower") } } label: {
                        Label("Lower", systemImage: "arrow.down")
                            .font(.system(size: 14, weight: .bold))
                            .frame(maxWidth: .infinity, minHeight: 44)
                    }
                    .tint(.red)
                }
            }
            .padding(.horizontal, 4)
            }
        }
    }

    private func resultView(_ result: GuessResult, _ q: GuessQuestion) -> some View {
        VStack(spacing: 6) {
            Image(systemName: result.correct ? "checkmark.circle.fill" : "xmark.circle.fill")
                .font(.title2)
                .foregroundStyle(result.correct ? .green : .red)

            Text(result.correct ? "Correct!" : "Not quite!")
                .font(.system(size: 14, weight: .bold))

            Text("\(q.actualPct)%")
                .font(.system(size: 38, weight: .heavy, design: .rounded))

            Text(q.subject)
                .font(.system(size: 12))
                .foregroundStyle(.secondary)
                .lineLimit(2)
                .multilineTextAlignment(.center)

            if let streak = vm.streak, streak > 1 {
                Text("\u{1F525} \(streak) in a row!")
                    .font(.system(size: 11, weight: .bold))
                    .foregroundStyle(.orange)
            }

            Button {
                vm.nextQuestion()
            } label: {
                Text("Next")
                    .font(.system(size: 12, weight: .bold))
                    .frame(maxWidth: .infinity)
            }
            .tint(.blue)
        }
        .padding(.horizontal, 4)
    }
}

struct GuessQuestion {
    let id: Int
    let title: String
    let subject: String
    let actualProb: Double
    let threshold: Int
    let isEvent: Bool
    let category: String?

    var actualPct: Int { Int((actualProb * 100).rounded()) }
}

struct GuessResult {
    let correct: Bool
    let guess: String
}
