import Foundation

nonisolated protocol WatchNFLCollectionTransport: Sendable {
    func weeks(season: Int) async throws -> [WatchNFLWeek]
    func membership(week: WatchNFLWeek) async throws -> WatchNFLMembership
}

nonisolated struct WatchNFLCollectionAPIClient: WatchNFLCollectionTransport {
    let session: URLSession
    init(session: URLSession = .shared) { self.session = session }

    func weeks(season: Int) async throws -> [WatchNFLWeek] {
        guard season > 0 else { throw WatchNFLDecodeError.invalid }
        var url = URLComponents(string: "https://api.bainluck.com/api/containers/discover")!
        url.queryItems = [URLQueryItem(name: "league", value: "nfl"),
                         URLQueryItem(name: "season", value: String(season)),
                         URLQueryItem(name: "limit", value: "20")]
        return try WatchNFLCollectionDecoder.weeks(await fetch(url.url!), season: season)
    }
    func membership(week: WatchNFLWeek) async throws -> WatchNFLMembership {
        guard week.isValid(season: week.edition.season) else { throw WatchNFLDecodeError.invalid }
        // Validation restricts slug to the exact producer edition grammar.
        let url = URL(string: "https://api.bainluck.com/api/containers/\(week.slug)")!
        return try WatchNFLCollectionDecoder.membership(await fetch(url), week: week)
    }
    private func fetch(_ url: URL) async throws -> Data {
        var request = URLRequest(url: url)
        request.timeoutInterval = 15
        request.cachePolicy = .reloadIgnoringLocalCacheData
        request.setValue("no-cache", forHTTPHeaderField: "Cache-Control")
        let (data, response) = try await session.data(for: request)
        guard let response = response as? HTTPURLResponse else { throw WatchDiscoveryRequestError.invalidResponse }
        if [429, 503].contains(response.statusCode) { throw WatchDiscoveryRequestError.serviceBusy }
        guard response.statusCode == 200 else { throw WatchDiscoveryRequestError.invalidResponse }
        return data
    }
}
