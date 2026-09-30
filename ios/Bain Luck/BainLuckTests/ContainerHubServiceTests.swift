import Foundation
import XCTest
@testable import Bain_Luck

@MainActor
final class ContainerHubServiceTests: XCTestCase {
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

    private func service() -> ContainerHubService {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [Origin.self]
        configuration.urlCache = URLCache(memoryCapacity: 1_000_000, diskCapacity: 0, diskPath: nil)
        return ContainerHubService(client: APIClient(session: URLSession(configuration: configuration)))
    }

    func testFreshPublishedReadCannotReuseWarmSlugCacheAfterWithdrawal() async throws {
        Origin.reset(body: try ContainerHubFixture.responseData("representative_nfl_week"))
        let service = service()
        let first = try await service.load(slug: "nfl-2026-week-5")
        XCTAssertEqual(first.revision, 4)
        var object = try JSONSerialization.jsonObject(with: ContainerHubFixture.responseData("representative_nfl_week")) as! [String: Any]
        object["state"] = "withdrawn"
        object["revision"] = 5
        Origin.replace(body: try JSONSerialization.data(withJSONObject: object))
        let second = try await service.load(slug: "nfl-2026-week-5")
        XCTAssertEqual(second.revision, 5)
        XCTAssertEqual(second.state, .withdrawn)
        XCTAssertTrue(second.sections.isEmpty)
        XCTAssertEqual(Origin.requests.count, 2)
        XCTAssertTrue(Origin.requests.allSatisfy { $0.url?.path == "/api/containers/nfl-2026-week-5" && $0.httpMethod == "GET" })
    }

    func testFlagOffOrMissingCollection404RemainsUnavailable() async throws {
        Origin.reset(body: Data(#"{"detail":{"state":"unavailable","slug":"mlb-2026-postseason"}}"#.utf8), status: 404)
        do {
            _ = try await service().load(slug: "mlb-2026-postseason")
            XCTFail("404 must not synthesize an empty published response")
        } catch let error as APIError {
            guard case .httpError(statusCode: 404, body: _) = error else { return XCTFail("Wrong error") }
        }
        XCTAssertEqual(Origin.requests.first?.url?.path, "/api/containers/mlb-2026-postseason")
    }
}
