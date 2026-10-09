import Foundation
import Combine

/// Ephemeral detail state. The existing discovery cache is not rewritten.
final class WatchQuestionDetailStore: ObservableObject {
    @Published private(set) var detail: WatchQuestionDetail?
    @Published private(set) var loading = false
    @Published private(set) var error: String?
    private let transport: any WatchQuestionDetailTransport
    private var generation = 0
    private var requestedID: Int?

    init(transport: any WatchQuestionDetailTransport = WatchQuestionDetailAPIClient()) {
        self.transport = transport
    }
    // A new destination may render before its task begins. Never borrow another
    // question's loading/error state during that interval.
    func requestStatus(for id: Int) -> (loading: Bool, error: String?) {
        guard requestedID == id else { return (false, nil) }
        return (loading, error)
    }
    @MainActor func cancel() {
        generation += 1
        requestedID = nil
        detail = nil; error = nil; loading = false
    }
    @MainActor func load(id: Int) async {
        guard !Task.isCancelled else { return }
        generation += 1
        let stamp = generation
        requestedID = id
        detail = nil; error = nil; loading = true
        guard id > 0 else { loading = false; error = "This question is unavailable."; return }
        do {
            let result = try await transport.load(id: id)
            try Task.checkCancellation()
            guard stamp == generation else { return }
            guard result.id == id else { throw WatchQuestionDetailDecoder.Invalid.identity }
            detail = result; loading = false
        } catch {
            guard stamp == generation else { return }
            loading = false
            guard !Task.isCancelled, !(error is CancellationError),
                  (error as? URLError)?.code != .cancelled else { return }
            switch error {
            case WatchQuestionDetailServiceError.notFound:
                self.error = "This question is currently unavailable."
            case WatchQuestionDetailServiceError.busy:
                self.error = "Service is busy. Try again shortly."
            case let network as URLError where network.code == .notConnectedToInternet || network.code == .networkConnectionLost:
                self.error = "Offline. Reconnect and try again."
            case let network as URLError where network.code == .timedOut:
                self.error = "Connection timed out. Try again."
            default:
                self.error = "Couldn't read this question. Try again."
            }
        }
    }
}
