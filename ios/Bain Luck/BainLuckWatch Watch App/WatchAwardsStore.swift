import Combine
import Foundation

/// Ephemeral ceremony navigation. Existing saved stories and game selection stay owned elsewhere.
final class WatchAwardsStore: ObservableObject {
    @Published private(set) var ceremony: WatchAwardsCeremony?
    @Published private(set) var page: WatchAwardsPage?
    @Published private(set) var isLoading = false
    @Published private(set) var errorMessage: String?
    private let transport: any WatchAwardsTransport
    private var revision = 0
    private var resolvedKey: String?

    init(transport: any WatchAwardsTransport = WatchAwardsAPIClient()) { self.transport = transport }

    @MainActor func cancel() {
        revision += 1
        isLoading = false
        page = nil
    }
    @MainActor func browse() {
        cancel()
        ceremony = nil; resolvedKey = nil; errorMessage = nil
    }
    @MainActor func open(_ ceremony: WatchAwardsCeremony) async {
        guard !Task.isCancelled else { return }
        self.ceremony = ceremony
        resolvedKey = nil
        await refresh()
    }
    @MainActor func refresh() async {
        guard !Task.isCancelled, let ceremony else { return }
        revision += 1
        let stamp = revision
        let key = resolvedKey ?? ceremony.key
        page = nil; errorMessage = nil; isLoading = true
        do {
            let result = try await transport.fetch(ceremony: ceremony, key: key)
            try Task.checkCancellation()
            guard stamp == revision, self.ceremony == ceremony else { return }
            guard ceremony.accepts(key: result.key), resolvedKey == nil || result.key == key else {
                throw WatchAwardsError.invalid
            }
            // Refresh remains on the accepted edition. Choosing a ceremony again
            // explicitly asks the producer for its current available edition.
            resolvedKey = result.key
            page = result
            isLoading = false
        } catch {
            guard stamp == revision else { return }
            isLoading = false
            guard !Task.isCancelled, !(error is CancellationError),
                  (error as? URLError)?.code != .cancelled else { return }
            switch error {
            case WatchAwardsError.unavailable:
                errorMessage = "This ceremony is currently unavailable. Try another ceremony or refresh."
            case WatchAwardsError.busy:
                errorMessage = "Service is busy. Try again shortly."
            case let network as URLError where [.notConnectedToInternet, .networkConnectionLost].contains(network.code):
                errorMessage = "Offline. Reconnect and refresh this ceremony."
            case let network as URLError where network.code == .timedOut:
                errorMessage = "Connection timed out. Refresh to try again."
            default:
                errorMessage = "Couldn't read this ceremony. Refresh to try again."
            }
        }
    }

    @MainActor func category(id: Int) -> WatchAwardsCategory? {
        guard !isLoading else { return nil }
        return page?.categories.first { $0.id == id }
    }
}
