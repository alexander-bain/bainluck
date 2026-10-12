import SwiftUI
import UIKit
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
/// one process clock.
///
/// Two observation cadences. Whole-second clocks are the retained control. The
/// quarter-second clocks are the case: each quote's own observation stamp is
/// 250 ms after the last, so the chart has to admit points closer together than
/// a second.
///
/// Two depths. The model cases stop at the view model's adoption marks. The
/// hosted cases mount the real `EventDetailView` in a key window on the
/// foreground-active scene at phone width. The page's own `.task` runs the load,
/// and the existing `LiveTimingSeam` view marks report what the hero and chart
/// were handed. Those marks are view INPUTS, not pixels.
///
/// History always throws here. The `reads >= 2` check only proves the page was
/// read again mid-burst (the poll alone pays it) and nothing rolled back. It does
/// not prove a resync or history recovery succeeded.
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

    /// Quote `i`'s observation clock: `i` seconds after the held read, or
    /// `i` quarter-seconds after it.
    nonisolated private static func clock(_ i: Int, quarter: Bool) -> String {
        stamp(quarter ? Double(i) * 0.25 : Double(i), fractional: quarter)
    }

    /// The held read's clock. The model cases keep 2026-09-25T17:10:00Z. The
    /// hosted page uses half a minute ago, because a live chart's axis ends at
    /// the real now and a September line would be squeezed against its left
    /// edge.
    nonisolated private static let fixedBase: TimeInterval = 1_790_356_200
    nonisolated private static func recentBase() -> TimeInterval { floor(Date().timeIntervalSince1970) - 30 }

    nonisolated private static func stamp(_ offset: TimeInterval, fractional: Bool = false) -> String {
        let f = ISO8601DateFormatter()
        f.formatOptions = fractional ? [.withInternetDateTime, .withFractionalSeconds] : [.withInternetDateTime]
        return f.string(from: Date(timeIntervalSince1970: PacedStream.base + offset))
    }

    nonisolated private static func raw(_ i: Int, quarter: Bool) -> String {
        #"{"event_id":4242,"p":0.9,"source":"polymarket","source_value":0.9,"updated_at":"\#(clock(i, quarter: quarter))","status":"live","rev":{"4242":\#(20 + i)},"folded_quote_pending":true}"#
    }

    nonisolated private static func folded(_ i: Int, quarter: Bool) -> String {
        let p = probability(i)
        let c = clock(i, quarter: quarter)
        let quote = ##"{"event_id":4242,"hero_probability":\##(p),"hero_probability_away":\##(1 - p),"hero_probability_source":"blend","hero_probability_observed_at":"\##(c)","blend_fold_revision":{"4242":\##(20 + i),"999":5},"win_probability_sources":{"polymarket":{"value":\##(p),"display_name":"Polymarket","type":"market","color":"#000","updated_at":"\##(c)"}},"hero_sportsbook_count":null,"status":"live","sport":"basketball_nba","hero_settled_result":null}"##
        return String(raw(i, quarter: quarter).dropLast()) + #","folded_quote":\#(quote)}"#
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
        nonisolated(unsafe) private static var quarter = false
        nonisolated(unsafe) private static var baseEpoch = SubsecondHeldDelivery10090Tests.fixedBase
        private let queue = DispatchQueue(label: "paced-stream")
        private var stopped = false

        static func reset(quarter: Bool, base: TimeInterval) {
            lock.lock(); emitted = [:]; finished = false; Self.quarter = quarter; baseEpoch = base; lock.unlock()
        }
        static var base: TimeInterval { lock.lock(); defer { lock.unlock() }; return baseEpoch }
        static var emittedAt: [String: UInt64] { lock.lock(); defer { lock.unlock() }; return emitted }
        static var done: Bool { lock.lock(); defer { lock.unlock() }; return finished }
        private static var isQuarter: Bool { lock.lock(); defer { lock.unlock() }; return quarter }

        override class func canInit(with request: URLRequest) -> Bool {
            request.url?.path.hasSuffix("/stream") == true
        }
        override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

        override func startLoading() {
            let quarter = Self.isQuarter
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
                        "probability", SubsecondHeldDelivery10090Tests.raw(i, quarter: quarter)))
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
                        "folded_probability", SubsecondHeldDelivery10090Tests.folded(i, quarter: quarter)))
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
        let history: EventHistoryResponse?
        private(set) var reads = 0
        init(_ response: EventDetail, history: EventHistoryResponse? = nil) {
            self.response = response; self.history = history
        }
        func fetchEvent(id: Int) async throws -> EventDetail { reads += 1; return response }
        func fetchEventHistory(id: Int, hours: Int) async throws -> EventHistoryResponse {
            guard let history else { throw Missing() }
            return history
        }
        func fetchRelatedFutures(eventId: Int) async throws -> RelatedFuturesResponse { throw Missing() }
        func fetchTeamProgression(eventId: Int) async throws -> TeamProgressionResponse { throw Missing() }
        func fetchGameMarkets(eventId: Int) async throws -> GameMarketsResponse { throw Missing() }
        func fetchLineMovement(eventId: Int) async throws -> LineMovementResponse { throw Missing() }
    }

    private static func decoder() -> JSONDecoder {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return decoder
    }

    /// The held page: a folded blend hero at revision 20, older than every quote.
    /// The hosted page also carries a tip-off, so its chart has a start.
    private func held(hosted: Bool = false) throws -> EventDetail {
        let tip = hosted ? #""commence_time":"\#(Self.stamp(-4200))","# : ""
        return try Self.decoder().decode(EventDetail.self, from: Data("""
        {"id":4242,"sport":"basketball_nba","home_team":"Celtics","away_team":"Knicks","status":"live",\(tip)
         "home_score":50,"away_score":48,
         "current_odds":{"home_probability":0.6,"away_probability":0.4},
         "hero_probability":0.6,"hero_probability_source":"blend",
         "hero_probability_observed_at":"\(Self.stamp(0))",
         "blend_fold_revision":{"4242":20,"999":5},
         "win_probability_sources":{"polymarket":{"value":0.6,"updated_at":"\(Self.stamp(0))"}}}
        """.utf8))
    }

    /// The hosted page's history: a blend line from tip-off that ends on the
    /// held hero, 60% at the held clock, so the chart draws before the burst and the
    /// page never falls through to the production history read.
    private func heldHistory() throws -> EventHistoryResponse {
        let rows: [(TimeInterval, Double)] = [(-4200, 0.50), (-2400, 0.54), (-600, 0.58), (0, 0.60)]
        func points() -> String {
            rows.map { #"{"timestamp":"\#(Self.stamp($0.0))","home_probability":\#($0.1)}"# }
                .joined(separator: ",")
        }
        return try Self.decoder().decode(EventHistoryResponse.self, from: Data("""
        {"event_id":4242,"home_team":"Celtics","away_team":"Knicks","status":"live",
         "history":[\(points())],"aggregate_line":[\(points())],
         "win_prob_history":{"polymarket":[\(points())]}}
        """.utf8))
    }

    private func waitUntil(_ seconds: TimeInterval, _ done: () -> Bool) async {
        let deadline = Date().addingTimeInterval(seconds)
        while !done(), Date() < deadline { try? await Task.sleep(nanoseconds: 10_000_000) }
    }

    /// The real page in a key window on the foreground-active scene, at phone
    /// width, so SwiftUI appears it and runs its own `.task` load. The
    /// `EventPublicationCaller4974Tests.MountedPage` pattern: no sceneless
    /// fallback. The test never forces a layout during the burst, so view
    /// updates happen on the run loop's own schedule.
    @MainActor
    private final class MountedPage {
        let window: UIWindow
        private let previousKeyWindow: UIWindow?

        init(_ vm: EventDetailViewModel) async throws {
            let deadline = CACurrentMediaTime() + 10
            func activeScene() -> UIWindowScene? {
                UIApplication.shared.connectedScenes
                    .compactMap { $0 as? UIWindowScene }
                    .first { $0.activationState == .foregroundActive }
            }
            while activeScene() == nil && CACurrentMediaTime() < deadline {
                try await Task.sleep(nanoseconds: 50_000_000)
            }
            let scene = try XCTUnwrap(activeScene(), "the hosted page needs a foreground-active window scene")
            previousKeyWindow = scene.windows.first { $0.isKeyWindow }
            let page = NavigationStack { EventDetailView(eventId: 4242, viewModel: vm) }
                .environmentObject(PinManager())
                .environment(\.colorScheme, .light)
            let host = hostForMeasurement(page, at: .large)
            host.view.frame = CGRect(x: 0, y: 0, width: 390, height: 844)
            window = UIWindow(windowScene: scene)
            window.frame = host.view.frame
            window.rootViewController = host
            window.makeKeyAndVisible()
        }

        /// The final page as drawn, taken after the measured burst.
        func capture(to path: String) throws {
            window.layoutIfNeeded()
            let image = UIGraphicsImageRenderer(bounds: window.bounds).image { _ in
                _ = window.drawHierarchy(in: window.bounds, afterScreenUpdates: true)
            }
            try XCTUnwrap(image.pngData()).write(to: URL(fileURLWithPath: path))
        }

        func close() {
            window.isHidden = true
            previousKeyWindow?.makeKey()
        }
    }

    // MARK: - Run

    private struct Run {
        let adopted: [(mark: LiveTimingSeam.Mark, at: UInt64)]
        let charted: [(mark: LiveTimingSeam.Mark, at: UInt64)]
        let viewHeadline: [(mark: LiveTimingSeam.Mark, at: UInt64)]
        let viewChart: [(mark: LiveTimingSeam.Mark, at: UInt64)]
        let emitted: [String: UInt64]
        let reads: Int
        let vm: EventDetailViewModel
    }

    private func run(quarter: Bool, hosted: Bool) async throws -> Run {
        PacedStream.reset(quarter: quarter, base: hosted ? Self.recentBase() : Self.fixedBase)
        let base = PacedStream.base
        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [PacedStream.self]
        let session = URLSession(configuration: config)
        // Only the hosted page gets a successful history; the model cases keep
        // the original throwing one.
        let client = hosted ? Client(try held(hosted: true), history: try heldHistory()) : Client(try held())
        let vm = EventDetailViewModel(
            eventId: 4242, client: client,
            makeStreamHandle: { id in
                let t = try LiveEventStreamTransport(eventId: id, baseURL: "https://stub.invalid", session: session)
                t.connect()
                return t
            },
            now: { base - 595 },
            sleep: { _ in try? await Task.sleep(nanoseconds: 60_000_000_000) }
        )
        var page: MountedPage?
        if hosted {
            // The page's own `.task` loads it; the test does not call load().
            page = try await MountedPage(vm)
            await waitUntil(10) { vm.event != nil }
            XCTAssertNotNil(vm.event, "the mounted page ran its own load")
        } else {
            await vm.load()
        }
        defer { page?.close(); vm.stopRefresh() }

        // A periodic poll lands mid-burst, carrying the older held read.
        let poll = Task { @MainActor in
            try? await Task.sleep(nanoseconds: 2_100_000_000)
            await vm.load()
        }
        let doneMark: LiveTimingSeam.Name = hosted ? .viewHeadlineUpdated : .modelHeadlineAdopted
        await waitUntil(Double(Self.quotes) * Self.spacing + 3) {
            PacedStream.done && marks.filter { $0.mark.name == doneMark && $0.mark.basis.hasPrefix("rev:") }
                .count >= Self.quotes
        }
        await poll.value
        try? await Task.sleep(nanoseconds: 300_000_000)

        // Everything measured is already marked; the capture can't move it.
        let measured = marks.count
        if let page {
            XCTAssertNotNil(vm.history, "the hosted chart drew from the supplied history, not production")
            let path = "/Users/bain/bainluck/artifacts/native-10090-subsecond-hosted/final-\(quarter ? "250ms" : "1s").png"
            try page.capture(to: path)
            print("SUBSECOND-10090 capture=\(path)")
        }
        marks = Array(marks.prefix(measured))

        return Run(
            adopted: marks.filter { $0.mark.name == .modelHeadlineAdopted },
            charted: marks.filter { $0.mark.name == .modelChartAppended },
            viewHeadline: marks.filter { $0.mark.name == .viewHeadlineUpdated },
            viewChart: marks.filter { $0.mark.name == .viewChartUpdated },
            emitted: PacedStream.emittedAt, reads: client.reads, vm: vm)
    }

    private var expected: [String] { (1...Self.quotes).map { "rev:4242=\(20 + $0);999=5" } }

    /// Emit → mark lags on one clock. A missing mark is simply absent here, so
    /// the count assertion beside it is what fails a dropped quote.
    private func lags(_ list: [(mark: LiveTimingSeam.Mark, at: UInt64)], basis: (LiveTimingSeam.Mark) -> String?,
                      emitted: [String: UInt64]) -> [Double] {
        list.compactMap { m in basis(m.mark).flatMap { emitted[$0] }.map { Double(m.at &- $0) / 1e6 } }
    }

    private func summary(_ name: String, _ lags: [Double]) -> String {
        let sorted = lags.sorted()
        guard let first = sorted.first, let last = sorted.last else { return "\(name) n=0" }
        return String(format: "%@ n=%d min=%.2f p50=%.2f max=%.2f", name, sorted.count, first,
                      sorted[sorted.count / 2], last)
    }

    private func assertModel(_ r: Run, quarter: Bool) -> [Double] {
        XCTAssertEqual(r.adopted.map(\.mark.basis), expected,
                       "every changed quote is adopted once, in revision order, and nothing rolls it back")
        XCTAssertEqual(r.adopted.map(\.mark.path), Array(repeating: "folded", count: Self.quotes))
        XCTAssertEqual(r.charted.map(\.mark.basis), expected, "every adopted quote also gets its own chart point")
        XCTAssertEqual(r.vm.event?.currentOdds?.homeProbability ?? -1, Self.probability(Self.quotes), accuracy: 1e-9)
        XCTAssertEqual(r.vm.liveBlend.last?.homeProbability ?? -1, Self.probability(Self.quotes), accuracy: 1e-9,
                       "the chart edge agrees with the headline")
        XCTAssertGreaterThanOrEqual(r.reads, 2, "the page was read again mid-burst and did not roll back")
        let lags = lags(r.adopted, basis: { $0.basis }, emitted: r.emitted)
        XCTAssertEqual(lags.count, Self.quotes)
        return lags
    }

    // MARK: - Model cases

    private func modelCase(quarter: Bool) async throws {
        let r = try await run(quarter: quarter, hosted: false)
        let lags = assertModel(r, quarter: quarter)
        let line = "SUBSECOND-10090 depth=model clocks=\(quarter ? "250ms" : "1s") "
            + summary("emit_to_model_ms", lags) + " spacing_ms=250 reads=\(r.reads)"
        print(line)
        XCTAssertLessThan(lags.max() ?? .infinity, Self.spacing * 1000,
                          "a quote was still unadopted when the next one was sent: \(line)")
    }

    /// The retained control: whole-second observation clocks.
    func testFourQuotesASecondEachReachTheHeadlineAndChartBeforeTheNextArrives() async throws {
        try await modelCase(quarter: false)
    }

    func testQuarterSecondObservationClocksEachGetTheirOwnHeadlineAndChartPoint() async throws {
        try await modelCase(quarter: true)
    }

    // MARK: - Hosted cases

    private func hostedCase(quarter: Bool) async throws {
        let r = try await run(quarter: quarter, hosted: true)
        let modelLags = assertModel(r, quarter: quarter)

        // The hero's input: one view mark per quote, in revision order.
        let headline = r.viewHeadline.filter { $0.mark.basis.hasPrefix("rev:") }
        XCTAssertEqual(headline.map(\.mark.basis), expected,
                       "every adopted quote reaches the hero's input once, in order")
        // The chart's input: one new edge per quote, the edges the model appended.
        let stampToBasis = Dictionary(r.charted.map { ($0.mark.stamp, $0.mark.basis) }, uniquingKeysWith: { a, _ in a })
        XCTAssertEqual(r.viewChart.map { stampToBasis[$0.mark.stamp] ?? "unmatched:\($0.mark.stamp)" }, expected,
                       "every appended point reaches the chart's input once, in order")

        let headLags = lags(headline, basis: { $0.basis }, emitted: r.emitted)
        let chartLags = lags(r.viewChart, basis: { stampToBasis[$0.stamp] }, emitted: r.emitted)
        XCTAssertEqual(headLags.count, Self.quotes)
        XCTAssertEqual(chartLags.count, Self.quotes)
        let line = "SUBSECOND-10090 depth=view-input clocks=\(quarter ? "250ms" : "1s") width=390 "
            + summary("emit_to_model_ms", modelLags) + " "
            + summary("emit_to_view_headline_ms", headLags) + " "
            + summary("emit_to_view_chart_ms", chartLags)
            + " view_headline_marks=\(r.viewHeadline.count) view_chart_marks=\(r.viewChart.count) reads=\(r.reads)"
        print(line)
        XCTAssertLessThan(max(headLags.max() ?? .infinity, chartLags.max() ?? .infinity), Self.spacing * 1000,
                          "a quote had not reached the view's inputs when the next one was sent: \(line)")
    }

    func testHostedPageHandsEveryWholeSecondQuoteToTheHeroAndChartInOrder() async throws {
        try await hostedCase(quarter: false)
    }

    func testHostedPageHandsEveryQuarterSecondQuoteToTheHeroAndChartInOrder() async throws {
        try await hostedCase(quarter: true)
    }
}
