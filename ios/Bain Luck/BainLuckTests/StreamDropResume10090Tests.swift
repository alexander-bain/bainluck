import XCTest
@testable import Bain_Luck

/// #10090: a held page whose healthy stream is cut by the server gets back to
/// the latest probability in well under a second, not five.
///
/// THE SPECIMEN (production hold, event 15328994, 2026-10-12). Both of the
/// app's streams ended cleanly at 14:01:09.272Z after 82 s up. The app reopened
/// them 5.185 s later, which is `defaultRetryDelay` plus scheduling. Revisions
/// 1871–1875 were all published inside that window, and the new connection
/// replays only the latest frame, so the page went from 1870 straight to 1876
/// and read "Auto-refresh" in between.
///
/// The bytes travel over the REAL `LiveEventStreamTransport`, using a real
/// `URLSession` byte stream through a stubbed `URLProtocol` (the
/// `AReleaseDoesNotEndPushForTheMatch920Tests` seam). The held-page case adds
/// the real controller and `EventDetailViewModel`. Every timing is read on one
/// process clock.
///
/// What this does NOT claim: the quotes published while the page was
/// reconnecting are not recovered. The page resumes at the latest one, the way
/// the server's replay works. The test asserts that gap stays visible.
@MainActor
final class StreamDropResume10090Tests: XCTestCase {

    // MARK: - Server

    /// One scripted connection. `cutAfter` ends the body that long after the 200
    /// (nil = held open until the client leaves). `fail` answers with a transport
    /// error instead of a response.
    nonisolated struct Conn {
        var status = 200
        var cutAfter: TimeInterval?
        var fail = false
    }

    /// Serves scripted connections in order, and a shared publish timeline. Each
    /// connection sends `open`, replays the latest frame already published (the
    /// server's `latest_frames` replay), then forwards every later publish until
    /// it is cut. Records the uptime of every request and every cut.
    private nonisolated final class Server: URLProtocol, @unchecked Sendable {
        private static let lock = NSLock()
        nonisolated(unsafe) private static var conns: [Conn] = []
        nonisolated(unsafe) private static var publishes: [(at: TimeInterval, data: String)] = []
        nonisolated(unsafe) private static var t0: TimeInterval = 0
        nonisolated(unsafe) private static var requestAt: [TimeInterval] = []
        nonisolated(unsafe) private static var cutAt: [TimeInterval] = []
        private let queue = DispatchQueue(label: "drop-resume-server")
        private var stopped = false

        static func script(_ c: [Conn], publishes p: [(at: TimeInterval, data: String)] = []) {
            lock.lock(); defer { lock.unlock() }
            conns = c; publishes = p; requestAt = []; cutAt = []
            t0 = ProcessInfo.processInfo.systemUptime
        }

        /// Seconds since `script`, on the process uptime clock.
        static func now() -> TimeInterval {
            lock.lock(); defer { lock.unlock() }
            return ProcessInfo.processInfo.systemUptime - t0
        }
        static var requests: [TimeInterval] { lock.lock(); defer { lock.unlock() }; return requestAt }
        static var cuts: [TimeInterval] { lock.lock(); defer { lock.unlock() }; return cutAt }

        override class func canInit(with request: URLRequest) -> Bool {
            request.url?.path.hasSuffix("/stream") == true
        }
        override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

        override func startLoading() {
            Self.lock.lock()
            let now = ProcessInfo.processInfo.systemUptime - Self.t0
            let conn = Self.conns[min(Self.requestAt.count, Self.conns.count - 1)]
            Self.requestAt.append(now)
            let latest = Self.publishes.last { $0.at <= now }
            let later = Self.publishes.filter { $0.at > now }
            Self.lock.unlock()

            if conn.fail {
                client?.urlProtocol(self, didFailWithError: URLError(.networkConnectionLost))
                return
            }
            let response = HTTPURLResponse(url: request.url!, statusCode: conn.status, httpVersion: "HTTP/1.1",
                                           headerFields: ["Content-Type": "text/event-stream"])!
            client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
            guard conn.status == 200 else {
                client?.urlProtocolDidFinishLoading(self)
                return
            }
            var opening = "retry: 5000\n\n" + Self.frame("open", #"{"event_id":4242}"#)
            if let latest { opening += Self.frame("folded_probability", latest.data) }
            client?.urlProtocol(self, didLoad: Data(opening.utf8))

            let start = DispatchTime.now()
            let cut = conn.cutAfter.map { now + $0 }
            for p in later where cut.map({ p.at < $0 }) ?? true {
                queue.asyncAfter(deadline: start + (p.at - now)) { [self] in
                    guard !stopped else { return }
                    client?.urlProtocol(self, didLoad: Data(Self.frame("folded_probability", p.data).utf8))
                }
            }
            if let after = conn.cutAfter {
                queue.asyncAfter(deadline: start + after) { [self] in
                    guard !stopped else { return }
                    stopped = true
                    Self.lock.lock()
                    Self.cutAt.append(ProcessInfo.processInfo.systemUptime - Self.t0)
                    Self.lock.unlock()
                    // A clean end with no `closed`/`reconnect` frame: what a
                    // release leaves the client (`finished successfully`).
                    client?.urlProtocolDidFinishLoading(self)
                }
            }
        }

        override func stopLoading() { queue.async { [self] in stopped = true } }

        nonisolated static func frame(_ event: String, _ data: String) -> String {
            "event: \(event)\ndata: \(data)\n\n"
        }
    }

    private func session() -> URLSession {
        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [Server.self]
        return URLSession(configuration: config)
    }

    private func waitUntil(_ seconds: TimeInterval, _ done: () -> Bool) async {
        let deadline = Date().addingTimeInterval(seconds)
        while !done(), Date() < deadline { try? await Task.sleep(nanoseconds: 10_000_000) }
    }

    private func transport(retryDelay: TimeInterval = LiveEventStreamTransport.defaultRetryDelay)
        throws -> LiveEventStreamTransport {
        try LiveEventStreamTransport(eventId: 4242, baseURL: "https://stub.invalid", session: session(),
                                     retryDelay: retryDelay)
    }

    // MARK: - Transport cases

    /// The case, at the production delays: a stream up for longer than
    /// `retryDelay` is cut, and the next request goes out within a second.
    func testAHealthyStreamCutByTheServerReopensWithinASecond() async throws {
        Server.script([Conn(cutAfter: LiveEventStreamTransport.defaultRetryDelay + 0.3), Conn()])
        let t = try transport()
        var errors = 0
        t.on("error") { _ in errors += 1 }
        t.connect()
        await waitUntil(LiveEventStreamTransport.defaultRetryDelay + 7) { Server.requests.count >= 2 }
        t.close()

        let req = Server.requests, cuts = Server.cuts
        XCTAssertEqual(errors, 1, "one drop, reported once")
        guard req.count == 2, cuts.count == 1, let cut = cuts.first else {
            return XCTFail("expected 2 requests and 1 cut (the cut never retried?), got \(req.count) and \(cuts.count)")
        }
        let gap = req[1] - cut
        print(String(format: "DROP-RESUME-10090 healthy_cut_to_reopen_s=%.3f", gap))
        // 0.25 s, the shipped `defaultFirstRetryDelay`, written as a literal so
        // this file also compiles against the source from before it existed.
        XCTAssertGreaterThanOrEqual(gap, 0.25 - 0.02,
                                    "the first retry still waits a moment, so a restarted dyno is not stampeded")
        XCTAssertLessThan(gap, 1.0, "a healthy stream's cut waited \(gap)s, the five seconds the page lost quotes in")
    }

    /// Control: a connection that answers 200 and ends at once is not healthy,
    /// so it is still retried no faster than `retryDelay`.
    func testAStreamThatEndsAtOnceIsStillRetriedAtTheFullDelay() async throws {
        let delay: TimeInterval = 1.0
        Server.script([Conn(cutAfter: 0.05), Conn(cutAfter: 0.05), Conn()])
        let t = try transport(retryDelay: delay)
        t.connect()
        await waitUntil(5) { Server.requests.count >= 3 }
        t.close()

        let req = Server.requests, cuts = Server.cuts
        guard req.count >= 3, cuts.count >= 2 else {
            return XCTFail("expected 3 requests and 2 cuts, got \(req.count) and \(cuts.count)")
        }
        for i in 0..<2 {
            XCTAssertGreaterThanOrEqual(req[i + 1] - cuts[i], delay - 0.02,
                                        "a connection that never stayed up was retried early: a hammer")
        }
    }

    /// Repeated failure: after the one quick retry fails, the next waits the full
    /// `retryDelay`.
    func testAFailedQuickRetryBacksOffToTheFullDelay() async throws {
        let delay: TimeInterval = 1.0
        Server.script([Conn(cutAfter: delay + 0.2), Conn(fail: true), Conn(fail: true), Conn()])
        let t = try transport(retryDelay: delay)
        t.connect()
        await waitUntil(8) { Server.requests.count >= 4 }
        t.close()

        let req = Server.requests, cuts = Server.cuts
        guard req.count >= 4, cuts.count == 1, let cut = cuts.first else {
            return XCTFail("expected 4 requests and 1 cut, got \(req.count) and \(cuts.count)")
        }
        XCTAssertLessThan(req[1] - cut, 0.75, "the healthy cut gets the quick retry")
        XCTAssertGreaterThanOrEqual(req[2] - req[1], delay - 0.02, "a failed quick retry is not retried quickly again")
        XCTAssertGreaterThanOrEqual(req[3] - req[2], delay - 0.02)
        XCTAssertTrue(t.isClosed, "closed by the test")
    }

    /// A refusal on the quick retry is still terminal.
    func testARefusalOnTheQuickRetryIsStillTerminal() async throws {
        let delay: TimeInterval = 1.0
        Server.script([Conn(cutAfter: delay + 0.2), Conn(status: 409)])
        let t = try transport(retryDelay: delay)
        var errors = 0
        t.on("error") { _ in errors += 1 }
        t.connect()
        await waitUntil(5) { errors >= 2 }
        try? await Task.sleep(nanoseconds: UInt64(2 * delay * 1_000_000_000))

        XCTAssertEqual(errors, 2)
        XCTAssertTrue(t.isClosed, "a 409 is the server saying no")
        XCTAssertFalse(t.isConnecting)
        XCTAssertEqual(Server.requests.count, 2, "a refused endpoint must not be hammered")
    }

    /// `close()` while the quick retry is SLEEPING still ends the loop: the
    /// close lands 0.1 s after the drop is reported, inside the 0.25–0.5 s wait.
    func testCloseDuringTheQuickWaitEndsTheLoop() async throws {
        let delay: TimeInterval = 1.0
        Server.script([Conn(cutAfter: delay + 0.2), Conn()])
        let t = try transport(retryDelay: delay)
        var errored = false
        t.on("error") { _ in errored = true }
        t.connect()
        await waitUntil(5) { errored }
        XCTAssertTrue(errored, "the server never cut the stream")
        XCTAssertTrue(t.isConnecting, "the drop is a retry in progress, not a close")
        try? await Task.sleep(nanoseconds: 100_000_000)
        XCTAssertEqual(Server.requests.count, 1, "the quick retry fired before the close could land inside it")
        t.close()
        try? await Task.sleep(nanoseconds: 1_000_000_000)

        XCTAssertEqual(Server.requests.count, 1, "a closed transport reopened behind the controller's back")
        XCTAssertFalse(t.isConnecting)
    }

    // MARK: - Held page

    nonisolated private static let base: TimeInterval = 1_790_356_200

    nonisolated private static func stamp(_ offset: TimeInterval) -> String {
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime]
        return f.string(from: Date(timeIntervalSince1970: base + offset))
    }

    nonisolated private static func probability(_ rev: Int) -> Double { 0.40 + 0.01 * Double(rev - 20) }

    /// A folded blend quote at `rev`, observed `rev - 20` seconds after the held read.
    nonisolated private static func folded(_ rev: Int) -> String {
        let p = probability(rev)
        let c = stamp(Double(rev - 20))
        let quote = ##"{"event_id":4242,"hero_probability":\##(p),"hero_probability_away":\##(1 - p),"hero_probability_source":"blend","hero_probability_observed_at":"\##(c)","blend_fold_revision":{"4242":\##(rev),"999":5},"win_probability_sources":{"polymarket":{"value":\##(p),"display_name":"Polymarket","type":"market","color":"#000","updated_at":"\##(c)"}},"hero_sportsbook_count":null,"status":"live","sport":"basketball_nba","hero_settled_result":null}"##
        return #"{"event_id":4242,"p":0.9,"source":"polymarket","source_value":0.9,"updated_at":"\#(c)","status":"live","rev":{"4242":\#(rev)},"folded_quote":\#(quote)}"#
    }

    @MainActor
    private final class Client: EventDetailProviding {
        struct Missing: Error {}
        let response: EventDetail
        init(_ response: EventDetail) { self.response = response }
        func fetchEvent(id: Int) async throws -> EventDetail { response }
        func fetchEventHistory(id: Int, hours: Int) async throws -> EventHistoryResponse { throw Missing() }
        func fetchRelatedFutures(eventId: Int) async throws -> RelatedFuturesResponse { throw Missing() }
        func fetchTeamProgression(eventId: Int) async throws -> TeamProgressionResponse { throw Missing() }
        func fetchGameMarkets(eventId: Int) async throws -> GameMarketsResponse { throw Missing() }
        func fetchLineMovement(eventId: Int) async throws -> LineMovementResponse { throw Missing() }
    }

    /// The held page: a folded blend hero at revision 20, older than every quote.
    private func held() throws -> EventDetail {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(EventDetail.self, from: Data("""
        {"id":4242,"sport":"basketball_nba","home_team":"Celtics","away_team":"Knicks","status":"live",
         "home_score":50,"away_score":48,
         "current_odds":{"home_probability":0.6,"away_probability":0.4},
         "hero_probability":0.6,"hero_probability_source":"blend",
         "hero_probability_observed_at":"\(Self.stamp(0))",
         "blend_fold_revision":{"4242":20,"999":5},
         "win_probability_sources":{"polymarket":{"value":0.6,"updated_at":"\(Self.stamp(0))"}}}
        """.utf8))
    }

    /// The specimen's shape at the production delays. Revisions 21 and 22 arrive
    /// on a healthy connection, which the server then cuts. 23 and 24 are
    /// published in the next 0.2 s, while nothing is connected; 25 and 26 come
    /// seconds later. The page must be back on the latest revision within a
    /// second of the cut, every adoption must move forward, and the headline and
    /// chart edge must agree at the end. 23 was published before any reconnect
    /// could land and is never replayed, so it stays missing.
    func testAHeldPageResumesTheLatestProbabilityWithinASecondOfACut() async throws {
        var adopted: [(basis: String, at: TimeInterval)] = []
        var charted: [String] = []
        LiveTimingSeam.observer = { mark in
            if mark.name == .modelHeadlineAdopted, mark.basis.hasPrefix("rev:") {
                adopted.append((mark.basis, Server.now()))
            }
            if mark.name == .modelChartAppended, mark.basis.hasPrefix("rev:") { charted.append(mark.basis) }
        }
        defer { LiveTimingSeam.observer = nil }

        let cut = LiveEventStreamTransport.defaultRetryDelay + 0.5
        Server.script(
            [Conn(cutAfter: cut), Conn()],
            publishes: [(0.3, Self.folded(21)), (0.6, Self.folded(22)),
                        (cut + 0.1, Self.folded(23)), (cut + 0.2, Self.folded(24)),
                        (cut + 2.0, Self.folded(25)), (cut + 2.5, Self.folded(26))])
        let s = session()
        let vm = EventDetailViewModel(
            eventId: 4242, client: Client(try held()),
            makeStreamHandle: { id in
                let t = try LiveEventStreamTransport(eventId: id, baseURL: "https://stub.invalid", session: s)
                t.connect()
                return t
            },
            now: { Self.base - 595 },
            sleep: { _ in try? await Task.sleep(nanoseconds: 60_000_000_000) }
        )
        await vm.load()
        defer { vm.stopRefresh() }

        let last = "rev:4242=26;999=5"
        await waitUntil(cut + LiveEventStreamTransport.defaultRetryDelay + 5) { adopted.last?.basis == last }

        guard let cutAt = Server.cuts.first else { return XCTFail("the server never cut the stream") }
        let revs = adopted.compactMap { Int($0.basis.dropFirst("rev:4242=".count).prefix { $0.isNumber }) }
        XCTAssertEqual(revs, revs.sorted(), "an adoption moved backwards: \(revs)")
        XCTAssertEqual(Set(revs).count, revs.count, "a revision was adopted twice: \(revs)")
        XCTAssertEqual(Array(revs.prefix(2)), [21, 22], "the healthy connection delivered both")
        XCTAssertFalse(revs.contains(23), "23 was published while nothing was connected and is never replayed")
        XCTAssertEqual(revs.last, 26)
        XCTAssertEqual(charted, adopted.map(\.basis), "every adopted revision also got its chart point")

        let resumed = adopted.first { $0.at > cutAt }
        let lag = (resumed?.at ?? .infinity) - cutAt
        print(String(format: "DROP-RESUME-10090 held_cut_to_first_adoption_s=%.3f first=%@ revs=%@",
                     lag, resumed?.basis ?? "none", revs.map(String.init).joined(separator: ",")))
        XCTAssertEqual(resumed?.basis, "rev:4242=24;999=5",
                       "the reconnect's replay should be the latest revision published before it landed")
        XCTAssertLessThan(lag, 1.0, "the held page was \(lag)s behind after a cut")
        XCTAssertEqual(vm.event?.currentOdds?.homeProbability ?? -1, Self.probability(26), accuracy: 1e-9)
        XCTAssertEqual(vm.liveBlend.last?.homeProbability ?? -1, Self.probability(26), accuracy: 1e-9,
                       "the chart edge agrees with the headline")
    }
}
