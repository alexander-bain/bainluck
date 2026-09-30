import Foundation
import XCTest
@testable import Bain_Luck

@MainActor
final class ContainerDiscoveryServiceTests: XCTestCase {
    private nonisolated final class Origin: URLProtocol, @unchecked Sendable {
        private static let lock = NSLock()
        nonisolated(unsafe) private static var body = Data()
        nonisolated(unsafe) private static var status = 200
        nonisolated(unsafe) private static var captured: [URLRequest] = []

        static func reset(body: Data, status: Int = 200) {
            lock.lock(); defer { lock.unlock() }
            self.body = body
            self.status = status
            captured = []
        }
        static func replace(body: Data, status: Int = 200) {
            lock.lock(); defer { lock.unlock() }
            self.body = body
            self.status = status
        }
        static var requests: [URLRequest] {
            lock.lock(); defer { lock.unlock() }
            return captured
        }
        override class func canInit(with request: URLRequest) -> Bool { true }
        override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
        override func startLoading() {
            Self.lock.lock()
            Self.captured.append(request)
            let data = Self.body, status = Self.status
            Self.lock.unlock()
            let response = HTTPURLResponse(url: request.url!, statusCode: status, httpVersion: "HTTP/1.1",
                headerFields: ["Content-Type": "application/json", "Cache-Control": "max-age=3600"])!
            client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .allowed)
            client?.urlProtocol(self, didLoad: data)
            client?.urlProtocolDidFinishLoading(self)
        }
        override func stopLoading() {}
    }

    private func service() -> ContainerDiscoveryService {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [Origin.self]
        configuration.urlCache = URLCache(memoryCapacity: 1_000_000, diskCapacity: 0, diskPath: nil)
        return ContainerDiscoveryService(client: APIClient(session: URLSession(configuration: configuration)))
    }

    func testBankedBrowsePayloadUsesRealEndpointAndExactLeagueSeasonLimit() async throws {
        Origin.reset(body: try ContainerHubFixture.responseData("browse_mlb"))
        let request = ContainerDiscoveryRequest(league: .mlb, season: 2026)
        let response = try await service().load(request)
        XCTAssertEqual(request.entries(in: response).first?.collection.name, "MLB 2026 · Postseason")
        let sent = try XCTUnwrap(Origin.requests.first)
        XCTAssertEqual(sent.url?.path, "/api/containers/discover")
        XCTAssertEqual(sent.httpMethod, "GET")
        let items = try XCTUnwrap(URLComponents(url: sent.url!, resolvingAgainstBaseURL: false)?.queryItems)
        XCTAssertEqual(Dictionary(uniqueKeysWithValues: items.map { ($0.name, $0.value ?? "") }),
            ["league": "mlb", "season": "2026", "limit": "20"])
        XCTAssertEqual(sent.cachePolicy, .reloadIgnoringLocalCacheData)
    }

    func testFreshRefreshRemovesPublishedCardWhenFlagsTurnOff() async throws {
        Origin.reset(body: try ContainerHubFixture.responseData("browse_mlb"))
        let service = service(), request = ContainerDiscoveryRequest(league: .mlb, season: 2026)
        let first = try await service.load(request)
        XCTAssertEqual(first.collections.count, 1)
        Origin.replace(body: Data(#"{"collections":[]}"#.utf8))
        let second = try await service.load(request)
        XCTAssertTrue(second.collections.isEmpty)
        XCTAssertEqual(Origin.requests.count, 2)
        XCTAssertTrue(Origin.requests.allSatisfy { $0.value(forHTTPHeaderField: "Cache-Control") == "no-cache" })
    }

    func testAbsentEndpointAndTransientErrorsAreNotSynthesizedAsEmptySuccess() async throws {
        for code in [404, 503] {
            Origin.reset(body: Data(#"{"detail":"Unavailable"}"#.utf8), status: code)
            do {
                _ = try await service().load(ContainerDiscoveryRequest(league: .nfl, season: 2026))
                XCTFail("HTTP error must propagate so optional Browse can hide without inventing absence")
            } catch let error as APIError {
                guard case .httpError(let status, _) = error else { return XCTFail("Wrong error") }
                XCTAssertEqual(status, code)
            }
        }
    }
}
