import XCTest
@testable import Bain_Luck

/// #10090 — changed quotes arriving faster than once a second keep up on a held
/// page. Each one is adopted into the headline and the chart, in revision order,
/// before the next one arrives. A recovery resync and a periodic poll that land
/// mid-burst don't roll the page back.
///
/// The bytes travel over the REAL `LiveEventStreamTransport`, using a real
/// `URLSession` byte stream through a stubbed `URLProtocol` (the
/// `AReleaseDoesNotEndPushForTheMatch920Tests` seam). From there they go through
/// the real controller and `EventDetailViewModel`, and every timing is read on
/// one process clock. Model adoption only: SwiftUI view evaluation and paint are
/// outside this test.
@MainActor
final class SubsecondHeldDelivery10090Tests: XCTestCase {

    nonisolated private static let quotes = 16
    nonisolated private static let spacing: TimeInterval = 0.25
    nonisolated private static let rawToFold: TimeInterval = 0.05
    nonisolated private static let resyncAfter = 8

    private var marks: [(mark: LiveTimingSeam.Mark, at: UInt64)] = []

    override func setUp() async throws {
        marks = []
        LiveTimingSeam.observer = { [weak self] in
            self?.marks.append(($0, DispatchTime.now().uptimeNanoseconds))
        }
    }

    override func tearDown() async throws {
        LiveTimingSeam.observer = nil
    }

    // MARK: - Wire

    nonisolated private static func probability(_ i: Int) -> Double { 0.40 + 0.01 * Double(i) }

    nonisolated private static func clock(_ i: Int) -> String { String(format: "2026-09-25T17:10:%02dZ", i) }

    nonisolated private static func raw(_ i: Int) -> String {
        #"{"event_id":4242,"p":0.9,"source":"polymarket","source_value":0.9,"updated_at":"\#(clock(i))","status":"live","rev":{"4242":\#(20 + i)},"folded_quote_pending":true}"#
    }

    nonisolated private static func folded(_ i: Int) -> String {
        let p = probability(i)
        let quote = ##"{"event_id":4242,"hero_probability":\##(p),"hero_probability_away":\##(1 - p),"hero_probability_source":"blend","hero_probability_observed_at":"\##(clock(i))","blend_fold_revision":{"4242":\##(20 + i),"999":5},"win_probability_sources":{"polymarket":{"value":\##(p),"display_name":"Polymarket","type":"market","color":"#000","updated_at":"\##(clock(i))"}},"hero_sportsbook_count":null,"status":"live","sport":"basketball_nba","hero_settled_result":null}"##
        return String(raw(i).dropLast()) + #","folded_quote":\#(quote)}"#
    }

    nonisolated private static func frame(_ event: String, _ data: String) -> Data {
        Data("event: \(event)\ndata: \(data)\n\n".utf8)
    }

    /// Streams one open, then a raw promise and its fold every `spacing`, from a
    /// background queue. It records when each fold's bytes were handed to
    /// URLSession, keyed by the fold's basis.
    private nonisolated final class PacedStream: URLProtocol, @unchecked Sendable {
        private static let lock = NSLock()
        nonisolated(unsafe) private static var emitted: [String: UInt64] = [:]
        nonisolated(unsafe) private static var finished = false
        private let queue = DispatchQueue(label: "paced-stream")
        private var stopped = false

        static func reset() { lock.lock(); emitted = [:]; finished = false; lock.unlock() }
        static var emittedAt: [String: UInt64] { lock.lock(); defer { lock.unlock() }; return emitted }
        static var done: Bool { lock.lock(); defer { lock.unlock() }; return finished }

        override class func canInit(with request: URLRequest) -> Bool {
            request.url?.path.hasSuffix("/stream") == true
        }
        override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

        override func startLoading() {
            let response = HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: "HTTP/1.1",
                                           headerFields: ["Content-Type": "text/event-stream"])!
            client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
            client?.urlProtocol(self, didLoad: SubsecondHeldDelivery10090Tests.frame("open", #"{"event_id":4242}"#))
            let start = DispatchTime.now()
            for i in 1...SubsecondHeldDelivery10090Tests.quotes {
                let at = Double(i) * SubsecondHeldDelivery10090Tests.spacing
                queue.asyncAfter(deadline: start + at) { [self] in
                    guard !stopped else { return }
                    client?.urlProtocol(self, didLoad: SubsecondHeldDelivery10090Tests.frame(
                        "probability", SubsecondHeldDelivery10090Tests.raw(i)))
                    if i == SubsecondHeldDelivery10090Tests.resyncAfter {
                        client?.urlProtocol(self, didLoad: SubsecondHeldDelivery10090Tests.frame(
                            "resync", #"{"generation":1}"#))
                    }
                }
                queue.asyncAfter(deadline: start + at + SubsecondHeldDelivery10090Tests.rawToFold) { [self] in
                    guard !stopped else { return }
                    let basis = "rev:4242=\(20 + i);999=5"
                    Self.lock.lock(); Self.emitted[basis] = DispatchTime.now().uptimeNanoseconds; Self.lock.unlock()
                    client?.urlProtocol(self, didLoad: SubsecondHeldDelivery10090Tests.frame(
                        "folded_probability", SubsecondHeldDelivery10090Tests.folded(i)))
                    if i == SubsecondHeldDelivery10090Tests.quotes {
                        Self.lock.lock(); Self.finished = true; Self.lock.unlock()
                    }
                }
            }
            // The connection is left open, the way a held page sees a live
            // stream. The test closes it.
        }

        override func stopLoading() { queue.async { [self] in stopped = true } }
    }

    // MARK: - Page

    @MainActor
    private final class Client: EventDetailProviding {
        struct Missing: Error {}
        let response: EventDetail
        private(set) var reads = 0
        init(_ response: EventDetail) { self.response = response }
        func fetchEvent(id: Int) async throws -> EventDetail { reads += 1; return response }
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
         "hero_probability_observed_at":"2026-09-25T17:10:00Z",
         "blend_fold_revision":{"4242":20,"999":5},
         "win_probability_sources":{"polymarket":{"value":0.6,"updated_at":"2026-09-25T17:10:00Z"}}}
        """.utf8))
    }

    private func waitUntil(_ seconds: TimeInterval, _ done: () -> Bool) async {
        let deadline = Date().addingTimeInterval(seconds)
        while !done(), Date() < deadline { try? await Task.sleep(nanoseconds: 10_000_000) }
    }

    // MARK: - Case

    func testFourQuotesASecondEachReachTheHeadlineAndChartBeforeTheNextArrives() async throws {
        PacedStream.reset()
        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [PacedStream.self]
        let session = URLSession(configuration: config)
        let client = Client(try held())
        let vm = EventDetailViewModel(
            eventId: 4242, client: client,
            makeStreamHandle: { id in
                let t = try LiveEventStreamTransport(eventId: id, baseURL: "https://stub.invalid", session: session)
                t.connect()
                return t
            },
            now: { 1_790_355_605 },
            sleep: { _ in try? await Task.sleep(nanoseconds: 60_000_000_000) }
        )
        await vm.load()
        defer { vm.stopRefresh() }

        // A periodic poll lands mid-burst, carrying the older held read.
        let poll = Task { @MainActor in
            try? await Task.sleep(nanoseconds: 2_100_000_000)
            await vm.load()
        }
        await waitUntil(Double(Self.quotes) * Self.spacing + 3) {
            PacedStream.done && marks.filter { $0.mark.name == .modelHeadlineAdopted && $0.mark.path == "folded" }
                .count >= Self.quotes
        }
        await poll.value
        try? await Task.sleep(nanoseconds: 300_000_000)

        let adopted = marks.filter { $0.mark.name == .modelHeadlineAdopted }
        let charted = marks.filter { $0.mark.name == .modelChartAppended }
        let expected = (1...Self.quotes).map { "rev:4242=\(20 + $0);999=5" }

        XCTAssertEqual(adopted.map(\.mark.basis), expected,
                       "every changed quote is adopted once, in revision order, and nothing rolls it back")
        XCTAssertEqual(adopted.map(\.mark.path), Array(repeating: "folded", count: Self.quotes))
        XCTAssertEqual(charted.map(\.mark.basis), expected, "every adopted quote also gets its own chart point")
        XCTAssertEqual(vm.event?.currentOdds?.homeProbability ?? -1, Self.probability(Self.quotes), accuracy: 1e-9)
        XCTAssertEqual(vm.liveBlend.last?.homeProbability ?? -1, Self.probability(Self.quotes), accuracy: 1e-9,
                       "the chart edge agrees with the headline")
        XCTAssertGreaterThanOrEqual(client.reads, 2, "the resync or the poll actually read the page again")

        // Emit → adoption on one clock. Each quote should be adopted well before
        // the next one is sent, so nothing piles up behind it.
        let emitted = PacedStream.emittedAt
        let lags = adopted.compactMap { a in emitted[a.mark.basis].map { Double(a.at &- $0) / 1e6 } }
        XCTAssertEqual(lags.count, Self.quotes)
        let sorted = lags.sorted()
        let line = String(format: "SUBSECOND-10090 n=%d emit_to_model_ms min=%.2f p50=%.2f max=%.2f spacing_ms=%.0f reads=%d",
                          sorted.count, sorted.first ?? -1, sorted[sorted.count / 2], sorted.last ?? -1,
                          Self.spacing * 1000, client.reads)
        print(line)
        XCTAssertLessThan(sorted.last ?? .infinity, Self.spacing * 1000,
                          "a quote was still unadopted when the next one was sent: \(line)")
    }
}
