import Combine
import Foundation
import os

private let logger = Logger(subsystem: "com.bainluck", category: "tournamentHub")

/// Loads one registered tournament hub and reduces it to a presentation value.
///
/// The reduction happens here rather than in the view so the screen never holds
/// the 903 KB response: `TournamentHubPresentation` keeps ~25 rows, and the
/// decoded tree is released as soon as `load()` returns.
final class TournamentHubViewModel: ObservableObject {
    enum State: Equatable {
        case loading
        case loaded(TournamentHubPresentation)
        case error(String)
    }

    @Published private(set) var state: State = .loading

    let slug: String

    init(slug: String) {
        self.slug = slug
    }

    @MainActor
    func load() async {
        // A refresh keeps the last good screen up while it runs. Dropping back
        // to a skeleton on every pull-to-refresh is how a live page flickers.
        if case .loaded = state {} else { state = .loading }

        do {
            let response = try await APIClient.shared.fetchTournamentHub(slug: slug)
            state = .loaded(TournamentHubPresentation(response: response))
            logger.info("Tournament hub \(self.slug, privacy: .public) loaded")
        } catch {
            if case .loaded = state {
                // Keep showing what we had; a failed refresh is not an empty
                // tournament.
                logger.error("Tournament hub \(self.slug, privacy: .public) refresh failed: \(error)")
            } else {
                state = .error(error.localizedDescription)
                logger.error("Tournament hub \(self.slug, privacy: .public) error: \(error)")
            }
        }
    }
}
