import Foundation
import XCTest
@testable import Bain_Luck

@MainActor
final class SignOutDeviceDetach12569Tests: XCTestCase {
    private nonisolated final class CapturedRequestURLProtocol: URLProtocol, @unchecked Sendable {
        struct CapturedRequest: Sendable {
            let method: String?
            let path: String
            let authorization: String?
            let sessionHeader: String?
            let bodyJSON: [String: String]
        }

        private static let lock = NSLock()
        private static var _requests: [CapturedRequest] = []

        static var requests: [CapturedRequest] { lock.withLock { _requests } }
        static func reset() { lock.withLock { _requests.removeAll() } }

        private static func readBody(from request: URLRequest) -> Data? {
            if let data = request.httpBody { return data }
            guard let stream = request.httpBodyStream else { return nil }
            stream.open()
            defer { stream.close() }
            var output = Data()
            var buffer = [UInt8](repeating: 0, count: 4096)
            while stream.hasBytesAvailable {
                let count = stream.read(&buffer, maxLength: buffer.count)
                if count <= 0 { break }
                output.append(buffer, count: count)
            }
            return output
        }

        override class func canInit(with request: URLRequest) -> Bool { true }
        override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

        override func startLoading() {
            guard let url = request.url else {
                client?.urlProtocol(self, didFailWithError: URLError(.badURL))
                return
            }
            let rawBody = Self.readBody(from: request) ?? Data()
            let decodedBody = (try? JSONSerialization.jsonObject(with: rawBody) as? [String: String]) ?? [:]
            Self.lock.withLock {
                Self._requests.append(
                    CapturedRequest(
                        method: request.httpMethod,
                        path: url.path,
                        authorization: request.value(forHTTPHeaderField: "Authorization"),
                        sessionHeader: request.value(forHTTPHeaderField: "X-Session-Id"),
                        bodyJSON: decodedBody
                    )
                )
            }

            let response = HTTPURLResponse(
                url: url, statusCode: 200, httpVersion: "HTTP/1.1",
                headerFields: ["Content-Type": "application/json"]
            )!
            client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
            client?.urlProtocol(self, didLoad: Data("{\"status\":\"ok\"}".utf8))
            client?.urlProtocolDidFinishLoading(self)
        }

        override func stopLoading() {}
    }

    private final class OrderingRecorder: @unchecked Sendable {
        private let lock = NSLock()
        var events: [String] = []
        var registeredPayloads: [(token: String, platform: String, userId: Int?, kind: String)] = []
        var unregisteredPayloads: [(token: String, platform: String, kind: String, auth: String)] = []

        func appendEvent(_ event: String) {
            lock.withLock { events.append(event) }
        }

        func recordUnregister(token: String, platform: String, kind: String, auth: String) {
            lock.withLock {
                unregisteredPayloads.append((token, platform, kind, auth))
                events.append("unregister:\(kind)")
            }
        }

        func recordRegister(token: String, platform: String, userId: Int?, kind: String) {
            lock.withLock {
                registeredPayloads.append((token, platform, userId, kind))
                events.append("register:\(kind):user=\(userId.map(String.init) ?? "nil")")
            }
        }
    }

    func testAPIClientUnregisterDeviceTokenSendsBearerAndSessionEvenAfterProviderCleared() async throws {
        CapturedRequestURLProtocol.reset()
        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [CapturedRequestURLProtocol.self]
        let client = APIClient(session: URLSession(configuration: config))
        await client.setAuthTokenProvider { nil }

        let response = try await client.unregisterDeviceToken(
            deviceToken: "apns-hex-1234",
            platform: "ios",
            tokenKind: "apns",
            authToken: "captured-signout-jwt"
        )
        XCTAssertEqual(response.status, "ok")

        let captured = CapturedRequestURLProtocol.requests
        XCTAssertEqual(captured.count, 1)
        let req = captured[0]
        XCTAssertEqual(req.method, "POST")
        XCTAssertEqual(req.path, "/api/notifications/unregister")
        XCTAssertEqual(req.authorization, "Bearer captured-signout-jwt")
        XCTAssertFalse((req.sessionHeader ?? "").isEmpty, "X-Session-Id header must be present")
        XCTAssertEqual(req.bodyJSON["device_token"], "apns-hex-1234")
        XCTAssertEqual(req.bodyJSON["platform"], "ios")
        XCTAssertEqual(req.bodyJSON["token_kind"], "apns")
        XCTAssertEqual(req.bodyJSON["session_id"], req.sessionHeader)
    }

    func testDetachAllTokensRunsStrictlyBeforeAnonymousReRegisterOnSignOut() async throws {
        let recorder = OrderingRecorder()
        let manager = NotificationManager(
            registerHandler: { token, platform, userId, kind in
                recorder.recordRegister(token: token, platform: platform, userId: userId, kind: kind)
                return NotificationRegisterResponse(status: "ok")
            },
            unregisterHandler: { token, platform, kind, auth in
                try? await Task.sleep(nanoseconds: 80_000_000)
                recorder.recordUnregister(token: token, platform: platform, kind: kind, auth: auth)
                return NotificationRegisterResponse(status: "ok")
            }
        )

        manager.setUser(id: 42)
        try await Task.sleep(nanoseconds: 30_000_000)
        manager.setTokensForTesting(apns: "apns-device-aaa", fcm: "fcm-token-bbb")

        let detachTask = manager.detachAllTokensForSignOut(authToken: "live-session-jwt")
        XCTAssertNotNil(detachTask)

        // Immediately simulate UI onChange(of: authManager.user) clearing userId to nil.
        manager.setUser(id: nil)

        await detachTask?.value
        for _ in 0..<25 where recorder.events.count < 4 {
            try await Task.sleep(nanoseconds: 20_000_000)
        }

        XCTAssertEqual(recorder.unregisteredPayloads.count, 2)
        XCTAssertEqual(recorder.unregisteredPayloads[0].auth, "live-session-jwt")
        XCTAssertEqual(recorder.unregisteredPayloads[1].auth, "live-session-jwt")

        let events = recorder.events
        XCTAssertEqual(events.prefix(2), ["unregister:apns", "unregister:fcm"])
        XCTAssertTrue(events.dropFirst(2).contains("register:apns:user=nil"), "Anonymous APNS register must follow detach: \(events)")
        XCTAssertTrue(events.dropFirst(2).contains("register:fcm:user=nil"), "Anonymous FCM register must follow detach: \(events)")
    }

    func testDetachAllTokensWithMissingAuthTokenSendsZeroRequests() async {
        let recorder = OrderingRecorder()
        let manager = NotificationManager(
            registerHandler: { token, platform, userId, kind in
                recorder.recordRegister(token: token, platform: platform, userId: userId, kind: kind)
                return NotificationRegisterResponse(status: "ok")
            },
            unregisterHandler: { token, platform, kind, auth in
                recorder.recordUnregister(token: token, platform: platform, kind: kind, auth: auth)
                return NotificationRegisterResponse(status: "ok")
            }
        )
        manager.setTokensForTesting(apns: "apns-device-aaa", fcm: "fcm-token-bbb")
        XCTAssertNil(manager.detachAllTokensForSignOut(authToken: nil))
        XCTAssertNil(manager.detachAllTokensForSignOut(authToken: ""))
        XCTAssertTrue(recorder.unregisteredPayloads.isEmpty)
    }

    func testSignedOutNewDeviceRegistrationContinuesToWorkAnonymously() async throws {
        let recorder = OrderingRecorder()
        let manager = NotificationManager(
            registerHandler: { token, platform, userId, kind in
                recorder.recordRegister(token: token, platform: platform, userId: userId, kind: kind)
                return NotificationRegisterResponse(status: "ok")
            },
            unregisterHandler: { token, platform, kind, auth in
                recorder.recordUnregister(token: token, platform: platform, kind: kind, auth: auth)
                return NotificationRegisterResponse(status: "ok")
            }
        )
        manager.didRegisterForRemoteNotifications(deviceToken: Data([0xaa, 0xbb, 0xcc, 0xdd]))
        for _ in 0..<25 where recorder.registeredPayloads.isEmpty {
            try await Task.sleep(nanoseconds: 20_000_000)
        }
        XCTAssertEqual(recorder.registeredPayloads.count, 1)
        XCTAssertEqual(recorder.registeredPayloads[0].token, "aabbccdd")
        XCTAssertNil(recorder.registeredPayloads[0].userId)
        XCTAssertEqual(recorder.registeredPayloads[0].kind, "apns")
        XCTAssertTrue(recorder.unregisteredPayloads.isEmpty)
    }
}
