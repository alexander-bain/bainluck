import Foundation

nonisolated enum WatchQuestionDetailServiceError: Error {
    case notFound, busy, invalidResponse

    static func validate(status: Int?) throws {
        switch status {
        case 200: return
        case 404: throw Self.notFound
        case 429, 503: throw Self.busy
        default: throw Self.invalidResponse
        }
    }
}

nonisolated protocol WatchQuestionDetailTransport: Sendable {
    func load(id: Int) async throws -> WatchQuestionDetail
}

nonisolated struct WatchQuestionDetailAPIClient: WatchQuestionDetailTransport {
    let session: URLSession
    init(session: URLSession = .shared) { self.session = session }
    func load(id: Int) async throws -> WatchQuestionDetail {
        guard id > 0 else { throw WatchQuestionDetailDecoder.Invalid.identity }
        var request = URLRequest(url: URL(string: "https://api.bainluck.com/api/futures/\(id)")!)
        request.timeoutInterval = 15
        request.cachePolicy = .reloadIgnoringLocalCacheData
        request.setValue("no-cache", forHTTPHeaderField: "Cache-Control")
        let (data, response) = try await session.data(for: request)
        try Task.checkCancellation()
        try WatchQuestionDetailServiceError.validate(status: (response as? HTTPURLResponse)?.statusCode)
        return try WatchQuestionDetailDecoder.decode(data, expectedID: id)
    }
}
