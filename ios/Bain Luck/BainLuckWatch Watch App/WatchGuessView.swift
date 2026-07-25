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
                // A guess is disabled while its save is in flight or awaiting a
                // retry — never let a failed/pending guess be double-submitted or
                // silently re-scored (L2-182).
                .disabled(vm.submission != .idle)

                if vm.submission == .submitting {
                    HStack(spacing: 6) {
                        ProgressView()
                        Text("Saving…")
                            .font(.system(size: 11))
                            .foregroundStyle(.secondary)
                    }
                    .padding(.top, 2)
                } else if vm.submission == .failed {
                    VStack(spacing: 4) {
                        Text("Couldn't save your guess")
                            .font(.system(size: 11))
                            .foregroundStyle(.orange)
                            .multilineTextAlignment(.center)
                        Button { Task { await vm.retrySubmit() } } label: {
                            Label("Retry", systemImage: "arrow.clockwise")
                                .font(.system(size: 13, weight: .semibold))
                                .frame(maxWidth: .infinity, minHeight: 40)
                        }
                        .tint(.blue)
                    }
                    .padding(.top, 2)
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

// `GuessQuestion` and `GuessResult` now live in WatchGuessPool.swift
// (Foundation-only) so the futures-only construction and the guess-result reveal
// path can be unit-tested without pulling SwiftUI/WatchKit into the test bundle.
