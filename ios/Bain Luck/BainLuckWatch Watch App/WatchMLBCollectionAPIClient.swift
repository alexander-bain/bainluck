import Foundation

nonisolated protocol WatchMLBCollectionTransport: Sendable {
    func collections(season: Int) async throws -> [WatchMLBCollection]
    func membership(collection: WatchMLBCollection) async throws -> WatchMLBMembership
}

nonisolated struct WatchMLBCollectionAPIClient: WatchMLBCollectionTransport {
    let session: URLSession
    init(session: URLSession = .shared) { self.session = session }
    func collections(season: Int) async throws -> [WatchMLBCollection] {
        guard (1903...9999).contains(season) else { throw WatchMLBCollectionError.invalid }
        var url = URLComponents(string: "https://api.bainluck.com/api/containers/discover")!
        url.queryItems = [URLQueryItem(name: "league", value: "mlb"),
                         URLQueryItem(name: "season", value: String(season)),
                         URLQueryItem(name: "limit", value: "20")]
        return try WatchMLBCollectionDecoder.collections(await fetch(url.url!), season: season)
    }
    func membership(collection: WatchMLBCollection) async throws -> WatchMLBMembership {
        guard collection.isValid(season: collection.edition.season) else { throw WatchMLBCollectionError.invalid }
        // Own members only: inherited child games need an independently supported
        // child edition/route contract, which the current MLB producer lacks.
        let url = URL(string: "https://api.bainluck.com/api/containers/\(collection.slug)?include_children=false")!
        return try WatchMLBCollectionDecoder.membership(await fetch(url), collection: collection)
    }
    private func fetch(_ url: URL) async throws -> Data {
        var request = URLRequest(url: url)
        request.timeoutInterval = 15
        request.cachePolicy = .reloadIgnoringLocalCacheData
        request.setValue("no-cache", forHTTPHeaderField: "Cache-Control")
        let (data, response) = try await session.data(for: request)
        guard let response = response as? HTTPURLResponse else { throw WatchMLBCollectionError.invalid }
        if [429, 503].contains(response.statusCode) { throw WatchMLBCollectionError.serviceBusy }
        guard response.statusCode == 200 else { throw WatchMLBCollectionError.invalid }
        return data
    }
}
