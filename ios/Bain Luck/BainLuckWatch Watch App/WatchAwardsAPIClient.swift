import Foundation

nonisolated protocol WatchAwardsTransport: Sendable {
    func fetch(ceremony: WatchAwardsCeremony, key: String) async throws -> WatchAwardsPage
}

nonisolated struct WatchAwardsAPIClient: WatchAwardsTransport {
    let session: URLSession
    init(session: URLSession = .shared) { self.session = session }

    func fetch(ceremony: WatchAwardsCeremony, key: String) async throws -> WatchAwardsPage {
        guard ceremony.accepts(key: key) else { throw WatchAwardsError.invalid }
        // Keys are validated canonical ASCII tokens, never caller-supplied URLs.
        let url = URL(string: "https://api.bainluck.com/api/event/")!.appendingPathComponent(key)
        var request = URLRequest(url: url)
        request.timeoutInterval = 15
        request.cachePolicy = .reloadIgnoringLocalCacheData
        request.setValue("no-cache", forHTTPHeaderField: "Cache-Control")
        let (data, response) = try await session.data(for: request)
        guard let http = response as? HTTPURLResponse else { throw WatchAwardsError.invalid }
        switch http.statusCode {
        case 200: break
        case 404, 410: throw WatchAwardsError.unavailable
        case 429, 503: throw WatchAwardsError.busy
        default: throw WatchAwardsError.invalid
        }
        return try WatchAwardsDecoder.decode(data, ceremony: ceremony, requestedKey: key)
    }
}
