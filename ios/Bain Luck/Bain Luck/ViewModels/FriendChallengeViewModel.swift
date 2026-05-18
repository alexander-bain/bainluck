import Combine
import Foundation

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
