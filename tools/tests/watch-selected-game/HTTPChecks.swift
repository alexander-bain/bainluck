import Foundation

/// Every request is intercepted; these checks never contact the public API.
private final class WatchHTTPProtocol: URLProtocol, @unchecked Sendable {
    private static let lock = NSLock()
    private static var handler: ((URLRequest) -> Void)?

    static func install(_ callback: @escaping (URLRequest) -> Void) {
        lock.lock()
        handler = callback
        lock.unlock()
    }

    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

    override func startLoading() {
        Self.lock.lock()
        let callback = Self.handler
        Self.lock.unlock()
        callback?(request)
        if let error = request.value(forHTTPHeaderField: "X-Watch-Test-Network-Error") {
            client?.urlProtocol(self, didFailWithError: URLError(URLError.Code(rawValue: Int(error)!)))
            return
        }
        let status = Int(request.value(forHTTPHeaderField: "X-Watch-Test-Status")!)!
        let body = request.value(forHTTPHeaderField: "X-Watch-Test-Body")!
        let response = HTTPURLResponse(url: request.url!, statusCode: status,
                                       httpVersion: "HTTP/1.1", headerFields: request.value(forHTTPHeaderField: "X-Watch-Test-Retry-After").map { ["Retry-After": $0] })!
        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: Data(body.utf8))
        client?.urlProtocolDidFinishLoading(self)
    }

    override func stopLoading() {}
}

@MainActor func checkWatchHTTPTransport() async throws {
    func session(status: Int = 200, body: String = "{}", networkError: URLError.Code? = nil, retryAfter: String? = nil) -> URLSession {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [WatchHTTPProtocol.self]
        var headers = ["X-Watch-Test-Status": String(status), "X-Watch-Test-Body": body]
        if let networkError { headers["X-Watch-Test-Network-Error"] = String(networkError.rawValue) }
        if let retryAfter { headers["X-Watch-Test-Retry-After"] = retryAfter }
        configuration.httpAdditionalHeaders = headers
        return URLSession(configuration: configuration)
    }
    WatchHTTPProtocol.install { request in
        precondition(request.url?.scheme == "https" && request.url?.host == "api.bainluck.com")
        precondition(request.url?.path == "/api/events/1", "Fetch the selected event detail")
        precondition(request.timeoutInterval == 15, "Bound each request to fifteen seconds")
        precondition(request.cachePolicy == .reloadIgnoringLocalCacheData, "Refresh bypasses the local cache")
    }
    let validSession = session(body: "{\"id\":2,\"home_team\":\"Home\",\"away_team\":\"Away\"}")
    let game = try await WatchSelectedGameHTTPTransport(session: validSession).fetch(eventID: 1)
    precondition(game.id == 2 && game.homeTeam == "Home" && game.awayTeam == "Away",
                 "A selected alias may resolve to its canonical event")
    validSession.invalidateAndCancel()

    func expect(_ expected: WatchSelectedGameRequestError, status: Int, body: String = "{}", retryAfter: String? = nil) async throws {
        let testSession = session(status: status, body: body, retryAfter: retryAfter)
        defer { testSession.invalidateAndCancel() }
        do {
            _ = try await WatchSelectedGameHTTPTransport(session: testSession).fetch(eventID: 1)
            fatalError("HTTP \(status) must fail")
        } catch let actual as WatchSelectedGameRequestError {
            switch (actual, expected) {
            case (.unavailable, .unavailable), (.serviceBusy, .serviceBusy), (.invalidResponse, .invalidResponse): break
            case let (.retryAfter(actualDelay), .retryAfter(expectedDelay)):
                precondition(actualDelay == expectedDelay, "Preserve the server retry delay")
            default: fatalError("Wrong classification for HTTP \(status): \(actual)")
            }
        }
    }
    try await expect(.invalidResponse, status: 200)
    try await expect(.invalidResponse, status: 200, body: "not JSON")
    for status in [404, 410] { try await expect(.unavailable, status: status) }
    for status in [429, 503] { try await expect(.serviceBusy, status: status) }
    for status in [201, 204, 400, 401, 403, 500, 502] { try await expect(.invalidResponse, status: status) }

    for status in [429, 503] {
        try await expect(.retryAfter(120), status: status, retryAfter: "120")
        try await expect(.retryAfter(0), status: status, retryAfter: "0")
        try await expect(.retryAfter(3600), status: status, retryAfter: "7200")
        for invalid in ["-1", "1.5", "garbage", "Thu, 01 Jan 1970 00:00:00 GMT"] {
            try await expect(.serviceBusy, status: status, retryAfter: invalid)
        }
    }
    let httpDate = DateFormatter()
    httpDate.locale = Locale(identifier: "en_US_POSIX")
    httpDate.timeZone = TimeZone(secondsFromGMT: 0)
    httpDate.dateFormat = "EEE, dd MMM yyyy HH:mm:ss 'GMT'"
    for status in [429, 503] {
        let dateSession = session(status: status, retryAfter: httpDate.string(from: Date().addingTimeInterval(120)))
        defer { dateSession.invalidateAndCancel() }
        do {
            _ = try await WatchSelectedGameHTTPTransport(session: dateSession).fetch(eventID: 1)
            fatalError("Busy HTTP date must produce a retry hint")
        } catch let error as WatchSelectedGameRequestError {
            guard case let .retryAfter(delay) = error else { fatalError("HTTP date hint was lost") }
            precondition((115...120).contains(delay), "HTTP date becomes a relative retry delay")
        }
    }
    try await expect(.invalidResponse, status: 500, retryAfter: "120")
    let formatter = ISO8601DateFormatter()
    let reference = formatter.date(from: "2026-01-01T00:00:00Z")!
    let validDelays: [(String, TimeInterval)] = [
        ("0", 0), ("1", 1), ("3599", 3599), ("3600", 3600), ("3601", 3600),
        ("Thu, 01 Jan 2026 00:00:00 GMT", 0),
        ("Thu, 01 Jan 2026 00:02:00 GMT", 120),
        ("Thu, 01 Jan 2026 02:00:00 GMT", 3600),
    ]
    for (header, delay) in validDelays {
        precondition(WatchSelectedGameHTTPTransport.retryDelay(from: header, now: reference) == delay,
                     "Parse integer or HTTP-date retry delay and cap at one hour")
    }
    let invalidDelays: [String?] = [nil, "", "-1", "1.5", "+1", "NaN", "inf", "later",
                                  "2026-01-01T00:02:00Z", "Wed, 31 Dec 2025 23:59:59 GMT"]
    for header in invalidDelays {
        precondition(WatchSelectedGameHTTPTransport.retryDelay(from: header, now: reference) == nil,
                     "Missing, malformed, or expired hints do not impose a delay")
    }

    let offlineSession = session(networkError: .notConnectedToInternet)
    defer { offlineSession.invalidateAndCancel() }
    do {
        _ = try await WatchSelectedGameHTTPTransport(session: offlineSession).fetch(eventID: 1)
        fatalError("Network failures must propagate")
    } catch let error as URLError {
        precondition(error.code == .notConnectedToInternet, "Preserve the original network error")
    }
    print("PASS: isolated HTTP request contract, canonical alias decode, malformed success, unavailable/busy/status classification, network error propagation, bounded integer and HTTP-date retry hints")
}
