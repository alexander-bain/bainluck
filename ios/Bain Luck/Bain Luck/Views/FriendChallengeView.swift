import Combine
import SwiftUI

struct FriendChallengeView: View {
    let challengeCode: String

    @StateObject private var vm = FriendChallengeViewModel()

    var body: some View {
        Group {
            if vm.loading {
                ProgressView("Loading challenge...")
            } else if let error = vm.error {
                VStack(spacing: 12) {
                    Image(systemName: "exclamationmark.triangle")
                        .font(.largeTitle)
                        .foregroundStyle(.secondary)
                    Text(error)
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                        .multilineTextAlignment(.center)
                    Button("Retry") { Task { await vm.load(code: challengeCode) } }
                        .buttonStyle(.borderedProminent)
                }
                .padding()
            } else if let challenge = vm.challenge {
                challengeContent(challenge)
            }
        }
        .navigationTitle("Friend Challenge")
        #if os(iOS)
        .navigationBarTitleDisplayMode(.inline)
        #endif
        .task { await vm.load(code: challengeCode) }
    }

    @ViewBuilder
    private func challengeContent(_ c: ChallengeResponse) -> some View {
        ScrollView {
            VStack(spacing: 24) {
                VStack(spacing: 8) {
                    Text(c.marketName)
                        .font(.headline)
                        .multilineTextAlignment(.center)
                    if let prob = c.currentProbability {
                        Text("\(Int(prob * 100))%")
                            .font(.caption)
                            .fontWeight(.semibold)
                            .padding(.horizontal, 10)
                            .padding(.vertical, 4)
                            .background(Color.blue.opacity(0.15), in: Capsule())
                    }
                }

                VStack(spacing: 4) {
                    Text("Threshold")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    Text("\(c.threshold)%")
                        .font(.system(size: 56, weight: .bold, design: .monospaced))
                }

                if c.friendGuess == nil && !vm.submitted {
                    VStack(spacing: 12) {
                        Text("What's your pick?")
                            .font(.subheadline.weight(.medium))
                        HStack(spacing: 16) {
                            Button {
                                Task { await vm.accept(code: challengeCode, guess: "higher") }
                            } label: {
                                Label("Higher", systemImage: "arrow.up")
                                    .frame(maxWidth: .infinity)
                            }
                            .buttonStyle(.borderedProminent)
                            .tint(.green)
                            .disabled(vm.submitting)

                            Button {
                                Task { await vm.accept(code: challengeCode, guess: "lower") }
                            } label: {
                                Label("Lower", systemImage: "arrow.down")
                                    .frame(maxWidth: .infinity)
                            }
                            .buttonStyle(.borderedProminent)
                            .tint(.red)
                            .disabled(vm.submitting)
                        }
                    }
                } else {
                    participantRows(c)
                }
            }
            .padding()
        }
    }

    @ViewBuilder
    private func participantRows(_ c: ChallengeResponse) -> some View {
        VStack(spacing: 12) {
            participantRow(
                label: "Challenger",
                guess: c.creatorGuess,
                correct: c.creatorCorrect
            )
            participantRow(
                label: "You",
                guess: vm.submitted ? vm.submittedGuess : c.friendGuess,
                correct: vm.submitted ? nil : c.friendCorrect
            )
        }
        .padding()
        .background(Color.systemGray6, in: RoundedRectangle(cornerRadius: 12))
    }

    private func participantRow(label: String, guess: String?, correct: Bool?) -> some View {
        HStack {
            Text(label)
                .font(.subheadline.weight(.medium))
            Spacer()
            if let guess {
                HStack(spacing: 6) {
                    Image(systemName: guess == "higher" ? "arrow.up" : "arrow.down")
                        .font(.caption.weight(.bold))
                        .foregroundStyle(guess == "higher" ? .green : .red)
                    Text(guess.capitalized)
                        .font(.subheadline)
                }
            } else {
                Text("Pending")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
            }
            if let correct {
                Image(systemName: correct ? "checkmark.circle.fill" : "xmark.circle.fill")
                    .foregroundStyle(correct ? .green : .red)
            }
        }
    }
}

@MainActor
final class FriendChallengeViewModel: ObservableObject {
    @Published var challenge: ChallengeResponse?
    @Published var loading = true
    @Published var error: String?
    @Published var submitting = false
    @Published var submitted = false
    @Published var submittedGuess: String?

    func load(code: String) async {
        loading = true
        error = nil
        do {
            challenge = try await APIClient.shared.fetchChallenge(code: code)
        } catch {
            self.error = error.localizedDescription
        }
        loading = false
    }

    func accept(code: String, guess: String) async {
        submitting = true
        do {
            _ = try await APIClient.shared.acceptChallenge(code: code, guess: guess)
            submitted = true
            submittedGuess = guess
        } catch {
            self.error = error.localizedDescription
        }
        submitting = false
    }
}
