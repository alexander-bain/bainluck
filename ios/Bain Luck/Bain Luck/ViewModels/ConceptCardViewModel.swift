import Combine
import Foundation
import os

private let logger = Logger(subsystem: "com.bainluck", category: "conceptCard")

/// Loads one fight card (#6667).
///
/// Shaped after `GolfTournamentViewModel` (#1471) on purpose — same
/// keep-the-last-good-screen refresh rule — with ONE more state, and it is the
/// reason this is not a copy: **a 404 is an answer, not a failure.**
///
/// The server refuses keys on purpose. A rumoured card the feed suppresses now
/// 404s on its page too (#6733), and a card whose markets have closed stops
/// resolving — measured 2026-09-17: `event:ufc:26sep12`, served on the 12th,
/// answers 404 on the 17th. A phone holding a cached feed can tap either. Web
/// learned this as UX-P031 (#1599): retrying a 404 cannot change the answer.
/// So `.unavailable` draws no Retry — a button that cannot work is the
/// Biltmore screen again.
final class ConceptCardViewModel: ObservableObject {
    enum State: Equatable {
        case loading
        case loaded(ConceptCardPresentation)
        /// The server said this card does not exist (HTTP 404).
        case unavailable
        /// Anything else — offline, 5xx, a body that did not decode. Retry can help.
        case error(String)
    }

    @Published private(set) var state: State = .loading

    let key: String

    init(key: String) {
        self.key = key
    }

    @MainActor
    func load() async {
        if case .loaded = state {} else { state = .loading }

        do {
            let response = try await APIClient.shared.fetchEventConcept(key: key)
            state = .loaded(ConceptCardPresentation(response: response))
            logger.info("Concept \(self.key, privacy: .public) loaded")
        } catch {
            state = Self.state(after: error, current: state)
            logger.error("Concept \(self.key, privacy: .public) failed: \(error)")
        }
    }

    /// What a failure does to the screen. The rule itself is
    /// `ConceptCardFailure.classify` (pure, tested); this only reads the status
    /// out of the transport error.
    nonisolated static func state(after error: Error, current: State) -> State {
        var status: Int?
        if case APIError.httpError(let statusCode, _) = error { status = statusCode }
        var hasLoadedScreen = false
        if case .loaded = current { hasLoadedScreen = true }

        switch ConceptCardFailure.classify(httpStatus: status, hasLoadedScreen: hasLoadedScreen) {
        case .gone: return .unavailable
        case .keepShowing: return current
        case .retryable: return .error(error.localizedDescription)
        }
    }
}
