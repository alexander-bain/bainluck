import Foundation
import XCTest
@testable import Bain_Luck

/// Intercepts every request; no test contacts the public API.
private nonisolated final class DiscoveryHTTPOrigin: URLProtocol, @unchecked Sendable {
    private static let lock = NSLock()
    nonisolated(unsafe) private static var captured: [String: URLRequest] = [:]

    static func takeRequest(_ token: String) -> URLRequest? {
        lock.lock()
        defer { lock.unlock() }
        return captured.removeValue(forKey: token)
    }

    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        guard let token = request.value(forHTTPHeaderField: "X-Discovery-Test-Token"),
              let status = request.value(forHTTPHeaderField: "X-Discovery-Test-Status").flatMap(Int.init),
              let encodedBody = request.value(forHTTPHeaderField: "X-Discovery-Test-Body"),
              let body = Data(base64Encoded: encodedBody),
              let url = request.url else {
            client?.urlProtocol(self, didFailWithError: URLError(.badServerResponse))
            return
        }
        Self.lock.lock()
        Self.captured[token] = request
        Self.lock.unlock()
        if let raw = request.value(forHTTPHeaderField: "X-Discovery-Test-Network-Error"),
           let code = Int(raw) {
            client?.urlProtocol(self, didFailWithError: URLError(URLError.Code(rawValue: code)))
            return
        }
        guard let response = HTTPURLResponse(url: url, statusCode: status,
                                            httpVersion: "HTTP/1.1", headerFields: nil) else {
            client?.urlProtocol(self, didFailWithError: URLError(.badServerResponse))
            return
        }
        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: body)
        client?.urlProtocolDidFinishLoading(self)
    }
    override func stopLoading() {}
}

final class WatchDiscoveryHTTPTests: XCTestCase {
    private func session(status: Int = 200, body: String = "{}",
                         networkError: URLError.Code? = nil) -> (URLSession, String) {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [DiscoveryHTTPOrigin.self]
        let token = UUID().uuidString
        var headers = ["X-Discovery-Test-Token": token, "X-Discovery-Test-Status": String(status),
                       "X-Discovery-Test-Body": Data(body.utf8).base64EncodedString()]
        if let networkError { headers["X-Discovery-Test-Network-Error"] = String(networkError.rawValue) }
        configuration.httpAdditionalHeaders = headers
        return (URLSession(configuration: configuration), token)
    }

    func testRealFeedShapeAndBoundedPublicDiscoverRequest() async throws {
        let body = """
        {"items":[{"type":"futures","data":{"id":301,"name":"Will inflation fall below 3%?",
        "price_observed_at":"2026-10-05T12:00:00Z","top_outcomes":[{"id":401,"name":"Yes","probability":0.455}]}}]}
        """
        let (session, token) = session(body: body)
        defer { session.invalidateAndCancel(); _ = DiscoveryHTTPOrigin.takeRequest(token) }
        let readings = try await WatchDiscoveryAPIClient(session: session).fetch()
        XCTAssertEqual(readings.count, 1)
        XCTAssertEqual(readings.first?.id, 301)
        XCTAssertEqual(readings.first?.question, "Will inflation fall below 3%?")
        XCTAssertEqual(readings.first?.outcomeName, "Yes")
        XCTAssertEqual(readings.first?.probability, 0.455)
        XCTAssertNil(readings.first?.observedAt, "Aggregate card clock cannot date the displayed outcome")
        let request = try XCTUnwrap(DiscoveryHTTPOrigin.takeRequest(token))
        XCTAssertEqual(request.url?.scheme, "https")
        XCTAssertEqual(request.url?.host, "api.bainluck.com")
        XCTAssertEqual(request.url?.path, "/api/feed")
        let components = try XCTUnwrap(request.url.flatMap { URLComponents(url: $0, resolvingAgainstBaseURL: false) })
        XCTAssertEqual(components.queryItems, [URLQueryItem(name: "limit", value: "30"),
                                               URLQueryItem(name: "mode", value: "discover")])
        XCTAssertNil(request.value(forHTTPHeaderField: "Authorization"))
        XCTAssertEqual(request.timeoutInterval, 15)
        XCTAssertEqual(request.cachePolicy, .reloadIgnoringLocalCacheData)
    }

    func testBusyOtherStatusAndMalformedSuccessAreDistinctFailures() async throws {
        for (status, body, busy) in [(429, "{}", true), (503, "{}", true),
                                    (201, "{}", false), (204, "", false), (404, "{}", false),
                                    (500, "{}", false), (200, "not JSON", false), (200, "{}", false)] {
            let (session, token) = session(status: status, body: body)
            defer { session.invalidateAndCancel(); _ = DiscoveryHTTPOrigin.takeRequest(token) }
            do {
                _ = try await WatchDiscoveryAPIClient(session: session).fetch()
                XCTFail("HTTP \(status) with this body must fail")
            } catch let error as WatchDiscoveryRequestError {
                switch error {
                case .serviceBusy: XCTAssertTrue(busy)
                case .invalidResponse: XCTAssertFalse(busy)
                }
            } catch { XCTFail("Unexpected error: \(error)") }
        }
    }

    func testNetworkErrorsPropagateUnchanged() async throws {
        for code in [URLError.Code.notConnectedToInternet, .timedOut, .cancelled] {
            let (session, token) = session(networkError: code)
            defer { session.invalidateAndCancel(); _ = DiscoveryHTTPOrigin.takeRequest(token) }
            do {
                _ = try await WatchDiscoveryAPIClient(session: session).fetch()
                XCTFail("Network error must propagate")
            } catch let error as URLError { XCTAssertEqual(error.code, code) }
            catch { XCTFail("Unexpected error: \(error)") }
        }
    }
}
