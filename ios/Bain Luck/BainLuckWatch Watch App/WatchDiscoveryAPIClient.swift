import Foundation

nonisolated protocol WatchDiscoveryTransport: Sendable {
    func fetch() async throws -> [WatchDiscoveryReading]
}

nonisolated enum WatchDiscoveryRequestError: Error {
    case serviceBusy
    case invalidResponse
}

/// Public Discover selection. The Watch preserves order and never ranks stories.
nonisolated struct WatchDiscoveryAPIClient: WatchDiscoveryTransport {
    let session: URLSession
    init(session: URLSession = .shared) { self.session = session }

    func fetch() async throws -> [WatchDiscoveryReading] {
        let url = URL(string: "https://api.bainluck.com/api/feed?limit=30&mode=discover")!
        var request = URLRequest(url: url)
        request.timeoutInterval = 15
        request.cachePolicy = .reloadIgnoringLocalCacheData
        let (data, response) = try await session.data(for: request)
        guard let response = response as? HTTPURLResponse else {
            throw WatchDiscoveryRequestError.invalidResponse
        }
        if [429, 503].contains(response.statusCode) { throw WatchDiscoveryRequestError.serviceBusy }
        guard response.statusCode == 200 else { throw WatchDiscoveryRequestError.invalidResponse }
        do { return try WatchDiscoveryDecoder.decode(data) }
        catch { throw WatchDiscoveryRequestError.invalidResponse }
    }
}
