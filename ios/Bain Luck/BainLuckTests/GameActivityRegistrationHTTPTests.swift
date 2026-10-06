#if os(iOS)
import Foundation
import XCTest
@testable import Bain_Luck

private nonisolated final class RegistrationHTTPOrigin: URLProtocol, @unchecked Sendable {
    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        let status = Int(request.value(forHTTPHeaderField: "X-Test-Status") ?? "200")!
        let valid = request.value(forHTTPHeaderField: "Authorization") == "Bearer test-session"
            && request.url?.path == "/api/activitykit/registrations/activity"
            && request.timeoutInterval == 8
        let response = HTTPURLResponse(url: request.url!, statusCode: valid ? status : 400,
                                       httpVersion: nil, headerFields: nil)!
        let body = Data("{\"activity_id\":\"activity\",\"event_id\":42,\"version\":1,\"is_active\":true}".utf8)
        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: body)
        client?.urlProtocolDidFinishLoading(self)
    }
    override func stopLoading() {}
}

@MainActor final class GameActivityRegistrationHTTPTests: XCTestCase {
    private func client(status: Int) -> GameActivityRegistrationClient {
        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [RegistrationHTTPOrigin.self]
        config.httpAdditionalHeaders = ["X-Test-Status": String(status)]
        return .init(session: URLSession(configuration: config),
                     baseURL: URL(string: "https://activity.test")!)
    }
    func testAuthenticatedBoundedMetadataRead() async throws {
        let metadata = try await client(status: 200).read(id: "activity", bearer: "test-session")
        XCTAssertEqual(metadata.activityID, "activity")
        XCTAssertEqual(metadata.eventID, 42)
        XCTAssertEqual(metadata.version, 1)
    }
    func testConflictIsDistinctFromAcknowledgement() async {
        do {
            _ = try await client(status: 409).mutate(id: "activity", eventID: 42, token: nil,
                version: 0, mutationID: UUID(), bearer: "test-session")
            XCTFail("Conflict cannot confirm revocation")
        } catch GameActivityRegistrationError.conflict {} catch { XCTFail("Expected generic conflict") }
    }
    func testUnavailableAndUnauthorizedAreGeneric() async {
        for status in [401, 404, 503] {
            do {
                _ = try await client(status: status).read(id: "activity", bearer: "test-session")
                XCTFail("Unavailable endpoint cannot acknowledge registration")
            } catch GameActivityRegistrationError.unavailable {} catch { XCTFail("Expected generic unavailable") }
        }
    }
    func testAnonymousAndInvalidActivityFailBeforeHTTP() async {
        for (id, bearer) in [("activity", ""), ("../activity", "test-session")] {
            do {
                _ = try await client(status: 200).read(id: id, bearer: bearer)
                XCTFail("Invalid request must fail locally")
            } catch GameActivityRegistrationError.invalidResponse {} catch { XCTFail("Expected local validation") }
        }
    }
}
#endif
