import Foundation
import OSLog
import XCTest
@testable import Bain_Luck

/// #10090 — the detail read's clock exchange (`ClockExchange`). Build 96 had
/// none, so every installed-iPhone hold was scored on an ASSUMED phone↔server
/// clock. A `GET /api/events/<id>` now writes `clock.exchange.sent` before the
/// request leaves and `clock.exchange.received` after the body lands, both
/// Default lines in the `liveTiming` log, the second with the response's
/// database-clock window. Real APIClient + real URLSession; only the server is
/// stubbed, through a test-local URLProtocol on an ephemeral session. Each test
/// uses its own event id, so lines from another test never count.
final class DetailReadClockExchange10090Tests: XCTestCase {
    private nonisolated final class Origin: URLProtocol, @unchecked Sendable {
        enum Reply {
            case serve(status: Int, body: Data)
            case fail(URLError.Code)
        }

        private static let lock = NSLock()
        nonisolated(unsafe) private static var reply = Reply.fail(.notConnectedToInternet)
        nonisolated(unsafe) private static var arrivals: [String] = []
        /// The server's arrival goes on the LOG clock, as a row of its own, so
        /// the bracket is ordered against it on one clock. A `Date()` here is a
        /// different clock from an os_log row's and can read microseconds off.
        private static let arrivalLog = Logger(subsystem: "com.bainluck", category: "liveTiming.testOrigin")

        static func reset(_ next: Reply) {
            lock.lock(); defer { lock.unlock() }
            reply = next; arrivals = []
        }
        static var reached: [String] {
            lock.lock(); defer { lock.unlock() }
            return arrivals
        }

        override class func canInit(with request: URLRequest) -> Bool { true }
        override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
        override func startLoading() {
            let path = request.url?.path ?? ""
            Self.arrivalLog.notice("origin.arrived \(path, privacy: .public)")
            Self.lock.lock()
            Self.arrivals.append(path)
            let next = Self.reply
            Self.lock.unlock()
            switch next {
            case .serve(let status, let body):
                let response = HTTPURLResponse(url: request.url!, statusCode: status, httpVersion: "HTTP/1.1",
                                               headerFields: ["Content-Type": "application/json"])!
                client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
                client?.urlProtocol(self, didLoad: body)
                client?.urlProtocolDidFinishLoading(self)
            case .fail(let code):
                client?.urlProtocol(self, didFailWithError: URLError(code))
            }
        }
        override func stopLoading() {}
    }

    private func client(_ reply: Origin.Reply) -> APIClient {
        Origin.reset(reply)
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [Origin.self]
        return APIClient(session: URLSession(configuration: configuration))
    }

    private static let notBefore = "2026-10-31T20:00:00.123456+00:00"
    private static let notAfter = "2026-10-31T20:00:00.125+00:00"

    /// A detail body as `get_event` serves it, with the window and its flag.
    private static func detail(_ id: Int, fresh: Bool? = true) -> Data {
        let window = fresh.map {
            ",\"state_read_not_before\":\"\(notBefore)\",\"state_read_not_after\":\"\(notAfter)\""
                + ",\"state_read_fresh\":\($0)"
        } ?? ""
        return Data("""
        {"id":\(id),"home_team":"Home","away_team":"Away","sport":"americanfootball_nfl","status":"live",
         "current_odds":{"home_probability":0.6,"away_probability":0.4}\(window)}
        """.utf8)
    }

    /// The exchange lines `event` wrote since `since`, oldest first.
    private func exchange(_ event: Int, since: Date) throws -> [OSLogEntryLog] {
        let store = try OSLogStore(scope: .currentProcessIdentifier)
        return try store.getEntries(at: store.position(date: since),
                                    matching: NSPredicate(format: "subsystem == %@ AND category == %@",
                                                          "com.bainluck", "liveTiming"))
            .compactMap { $0 as? OSLogEntryLog }
            .filter { $0.composedMessage.hasPrefix("clock.exchange.")
                && $0.composedMessage.contains(" event=\(event) ") }
    }

    // MARK: - The path

    func testOnlyTheDetailPathIsAnExchange() {
        XCTAssertEqual(ClockExchange.eventId(path: "/api/events/15334124"), 15334124)
        for path in ["/api/events/15334124/history", "/api/events/15334124/publications", "/api/events/live",
                     "/api/events/", "/api/events/-1", "/api/events/+1", "/api/events/12a", "/api/futures/1",
                     "/api/events/search"] {
            XCTAssertNil(ClockExchange.eventId(path: path), path)
        }
    }

    // MARK: - The pair

    func testAFreshDetailReadBracketsItsRequestWithTwoDefaultLinesCarryingTheServerWindow() async throws {
        let since = Date()
        let api = client(.serve(status: 200, body: Self.detail(910_090)))

        let event = try await api.fetchFreshEvent(id: 910_090)
        XCTAssertEqual(event.id, 910_090)

        let lines = try exchange(910_090, since: since)
        XCTAssertEqual(lines.map(\.composedMessage), [
            "clock.exchange.sent seq=1 event=910090 fresh_ask=1",
            "clock.exchange.received seq=1 event=910090 http=200 fresh=true"
                + " not_before=\(Self.notBefore) not_after=\(Self.notAfter)",
        ])
        XCTAssertEqual(lines.map(\.level), [.notice, .notice], "Default lines, which a long hold keeps")

        // The bracket encloses the server's handling: sent before the request
        // arrived, received after, all three rows on the log's one clock. That
        // is the whole claim a reader rests on.
        guard lines.count == 2 else { return XCTFail("one sent and one received line, got \(lines.count)") }
        let store = try OSLogStore(scope: .currentProcessIdentifier)
        let arrived = try XCTUnwrap(try store.getEntries(at: store.position(date: since),
                                                         matching: NSPredicate(format: "subsystem == %@ AND category == %@",
                                                                               "com.bainluck", "liveTiming.testOrigin"))
            .compactMap { $0 as? OSLogEntryLog }
            .first { $0.composedMessage == "origin.arrived /api/events/910090" }).date
        XCTAssertLessThanOrEqual(lines[0].date, arrived, "sent before the server saw the request")
        XCTAssertGreaterThanOrEqual(lines[1].date, arrived, "received after the server saw it")
    }

    func testAnOrdinaryReadOfACachedBuildSaysItAskedNothingAndGotACachedWindow() async throws {
        let since = Date()
        let api = client(.serve(status: 200, body: Self.detail(910_091, fresh: false)))

        _ = try await api.fetchEvent(id: 910_091)
        // Inside the TTL the second read never reaches the wire: no exchange.
        _ = try await api.fetchEvent(id: 910_091)

        XCTAssertEqual(try exchange(910_091, since: since).map(\.composedMessage), [
            "clock.exchange.sent seq=1 event=910091 fresh_ask=0",
            "clock.exchange.received seq=1 event=910091 http=200 fresh=false"
                + " not_before=\(Self.notBefore) not_after=\(Self.notAfter)",
        ])
    }

    func testEveryReadThatLeavesNumbersItsOwnPair() async throws {
        let since = Date()
        let api = client(.serve(status: 200, body: Self.detail(910_092)))

        _ = try await api.fetchFreshEvent(id: 910_092)
        _ = try await api.fetchFreshEvent(id: 910_092)

        XCTAssertEqual(try exchange(910_092, since: since).map { $0.composedMessage.split(separator: " ").prefix(2) },
                       [["clock.exchange.sent", "seq=1"], ["clock.exchange.received", "seq=1"],
                        ["clock.exchange.sent", "seq=2"], ["clock.exchange.received", "seq=2"]])
    }

    // MARK: - No anchor

    func testAFailedReadStillAnswersItsSentLineWithNoAnchor() async throws {
        let since = Date()
        let refused = client(.serve(status: 503, body: Data("{\"detail\":\"busy\"}".utf8)))
        do { _ = try await refused.fetchFreshEvent(id: 910_093); XCTFail("a 503 throws") } catch {}

        let offline = client(.fail(.notConnectedToInternet))
        do { _ = try await offline.fetchFreshEvent(id: 910_093); XCTFail("a transport failure throws") } catch {}

        XCTAssertEqual(try exchange(910_093, since: since).map(\.composedMessage), [
            "clock.exchange.sent seq=1 event=910093 fresh_ask=1",
            "clock.exchange.received seq=1 event=910093 http=503 fresh=- not_before=- not_after=-",
            "clock.exchange.sent seq=1 event=910093 fresh_ask=1",
            "clock.exchange.received seq=1 event=910093 http=- fresh=- not_before=- not_after=-",
        ])
    }

    func testABodyWithoutTheWindowPrintsNoAnchor() async throws {
        let since = Date()
        let api = client(.serve(status: 200, body: Self.detail(910_094, fresh: nil)))

        _ = try await api.fetchFreshEvent(id: 910_094)

        XCTAssertEqual(try exchange(910_094, since: since).last?.composedMessage,
                       "clock.exchange.received seq=1 event=910094 http=200 fresh=- not_before=- not_after=-")
    }

    func testAStampThatWouldSplitTheLinePrintsNoAnchor() {
        let body = Data("""
        {"state_read_not_before":"2026-10-31 20:00:00","state_read_not_after":"","state_read_fresh":true}
        """.utf8)
        XCTAssertEqual(ClockExchange.receivedLine(seq: 7, eventId: 1, status: 200, body: body),
                       "clock.exchange.received seq=7 event=1 http=200 fresh=true not_before=- not_after=-")
    }

    func testTheEventsOtherReadsPrintNoExchange() async throws {
        let since = Date()
        let api = client(.serve(status: 200, body: Data("""
        {"event_id":910095,"home_team":"Home","away_team":"Away","status":"live","history":[]}
        """.utf8)))

        _ = try? await api.fetchFreshEventHistory(id: 910_095, hours: 168)

        XCTAssertEqual(Origin.reached, ["/api/events/910095/history"], "the read did leave")
        XCTAssertEqual(try exchange(910_095, since: since).count, 0)
    }
}
