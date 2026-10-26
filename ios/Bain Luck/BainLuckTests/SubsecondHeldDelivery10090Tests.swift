import SwiftUI
import UIKit
import Vision
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
    /// The burst lands after the hosted page has loaded and drawn. It drains
    /// well before the 2.1 s poll, so the burst case is an UNLOADED control; the
    /// paced cases carry the poll and resync workload.
    nonisolated private static let burstAfter: TimeInterval = 1.5
    nonisolated private static let events: Set<Int> = [4242, burstEvent]

    private var marks: [(mark: LiveTimingSeam.Mark, at: UInt64)] = []

    override func setUp() async throws {
        marks = []
        // The host app runs its own live streams against production while the
        // tests run, and their marks reach this observer too. Keep this page's.
        LiveTimingSeam.observer = { [weak self] in
            guard Self.events.contains($0.eventId) else { return }
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

    // MARK: - The phone's burst

    /// The nine frames build 52 decoded in one 128 ms burst (revs 1440–1448 of
    /// event 15329605, 2026-10-13 22:59:52–55Z). The payloads are copied byte for
    /// byte from the Mac's wire capture of the same stream
    /// (`paired-sources/phone-attach/wire.jsonl`). Only the clocks are moved, by
    /// one shared offset, so they fall on the hosted chart's recent axis. Each
    /// entry is the frame's `p` and its microseconds after the held rev-1439 clock.
    nonisolated private static let burstEvent = 15329605
    nonisolated private static let burstFrames: [(p: String, after: Int64)] = [
        ("0.995", 9_122_053), ("0.9955", 9_369_861), ("0.995", 9_862_483),
        ("0.9955", 10_108_783), ("0.995", 10_634_906), ("0.9955", 11_108_875),
        ("0.995", 12_436_220), ("0.9955", 12_691_242), ("0.995", 12_929_543),
    ]
    /// The rev-1439 clock's microseconds past its whole second (22:59:42.880923Z).
    nonisolated private static let burstHeldMicros: Int64 = 880_923

    /// The wire's clock format: six fractional digits and `+00:00`.
    nonisolated private static func microClock(_ micros: Int64) -> String {
        let whole = Int64(PacedStream.base) * 1_000_000 + micros
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime]
        let seconds = f.string(from: Date(timeIntervalSince1970: TimeInterval(whole / 1_000_000)))
        return String(seconds.dropLast()) + String(format: ".%06lld+00:00", whole % 1_000_000)
    }

    nonisolated private static func burstBasis(_ i: Int) -> String { "rev:\(burstEvent)=\(1440 + i)" }

    /// All nine frames as one chunk, the way they reached the phone's decoder.
    /// `final` replaces only the last frame's `p` (the companion control); nil
    /// is the saved burst byte for byte.
    nonisolated private static func burstChunk(final: String? = nil) -> Data {
        var chunk = Data()
        for (i, f) in burstFrames.enumerated() {
            let clock = microClock(burstHeldMicros + f.after)
            let p = i == burstFrames.count - 1 ? final ?? f.p : f.p
            chunk += frame("probability", #"{"event_id": \#(burstEvent), "p": \#(p), "source": "polymarket", "source_value": \#(p), "updated_at": "\#(clock)", "status": "live", "rev": {"\#(burstEvent)": \#(1440 + i)}}"#)
        }
        return chunk
    }

    /// Streams one open, then a raw promise and its fold every `spacing`, from a
    /// background queue. It records when each fold's bytes were handed to
    /// URLSession, keyed by the fold's basis. In burst mode it instead hands the
    /// phone's nine frames to URLSession as one chunk, `burstAfter` after the open.
    private nonisolated final class PacedStream: URLProtocol, @unchecked Sendable {
        private static let lock = NSLock()
        nonisolated(unsafe) private static var emitted: [String: UInt64] = [:]
        nonisolated(unsafe) private static var finished = false
        nonisolated(unsafe) private static var quarter = false
        nonisolated(unsafe) private static var burst = false
        nonisolated(unsafe) private static var burstFinal: String?
        nonisolated(unsafe) private static var baseEpoch = SubsecondHeldDelivery10090Tests.fixedBase
        /// Diagnostics only: when the resync frame's bytes were handed to
        /// URLSession. Kept out of `emitted`, which the lags and the burst read.
        nonisolated(unsafe) private static var resyncEmitted: UInt64?
        private let queue = DispatchQueue(label: "paced-stream")
        private var stopped = false

        static func reset(quarter: Bool, base: TimeInterval, burst: Bool = false, burstFinal: String? = nil) {
            lock.lock(); emitted = [:]; finished = false; Self.quarter = quarter; Self.burst = burst
            Self.burstFinal = burstFinal; baseEpoch = base; lock.unlock()
            lock.lock(); resyncEmitted = nil; lock.unlock()
        }
        static var resyncEmittedAt: UInt64? { lock.lock(); defer { lock.unlock() }; return resyncEmitted }
        static var base: TimeInterval { lock.lock(); defer { lock.unlock() }; return baseEpoch }
        static var emittedAt: [String: UInt64] { lock.lock(); defer { lock.unlock() }; return emitted }
        static var done: Bool { lock.lock(); defer { lock.unlock() }; return finished }
        private static var isQuarter: Bool { lock.lock(); defer { lock.unlock() }; return quarter }
        private static var isBurst: Bool { lock.lock(); defer { lock.unlock() }; return burst }
        private static var finalValue: String? { lock.lock(); defer { lock.unlock() }; return burstFinal }

        override class func canInit(with request: URLRequest) -> Bool {
            request.url?.path.hasSuffix("/stream") == true
        }
        override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

        override func startLoading() {
            let quarter = Self.isQuarter
            let response = HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: "HTTP/1.1",
                                           headerFields: ["Content-Type": "text/event-stream"])!
            client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
            let id = Self.isBurst ? SubsecondHeldDelivery10090Tests.burstEvent : 4242
            client?.urlProtocol(self, didLoad: SubsecondHeldDelivery10090Tests.frame("open", #"{"event_id":\#(id)}"#))
            let start = DispatchTime.now()
            if Self.isBurst {
                let chunk = SubsecondHeldDelivery10090Tests.burstChunk(final: Self.finalValue)
                queue.asyncAfter(deadline: start + SubsecondHeldDelivery10090Tests.burstAfter) { [self] in
                    guard !stopped else { return }
                    let at = DispatchTime.now().uptimeNanoseconds
                    Self.lock.lock()
                    for i in SubsecondHeldDelivery10090Tests.burstFrames.indices {
                        Self.emitted[SubsecondHeldDelivery10090Tests.burstBasis(i)] = at
                    }
                    Self.lock.unlock()
                    client?.urlProtocol(self, didLoad: chunk)
                    Self.lock.lock(); Self.finished = true; Self.lock.unlock()
                }
                return
            }
            for i in 1...SubsecondHeldDelivery10090Tests.quotes {
                let at = Double(i) * SubsecondHeldDelivery10090Tests.spacing
                queue.asyncAfter(deadline: start + at) { [self] in
                    guard !stopped else { return }
                    client?.urlProtocol(self, didLoad: SubsecondHeldDelivery10090Tests.frame(
                        "probability", SubsecondHeldDelivery10090Tests.raw(i, quarter: quarter)))
                    if i == SubsecondHeldDelivery10090Tests.resyncAfter {
                        Self.lock.lock(); Self.resyncEmitted = DispatchTime.now().uptimeNanoseconds; Self.lock.unlock()
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
        /// Diagnostics only: each `fetchEvent` entry on the process clock.
        private(set) var readStamps: [UInt64] = []
        init(_ response: EventDetail, history: EventHistoryResponse? = nil) {
            self.response = response; self.history = history
        }
        func fetchEvent(id: Int) async throws -> EventDetail {
            readStamps.append(DispatchTime.now().uptimeNanoseconds)
            reads += 1; return response
        }
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

    /// The burst's held page: the phone's folded blend at the one row its frames
    /// write, rev 1439 at 99.1%, hosted with the same tip-off as the others.
    private func heldBeforeBurst() throws -> EventDetail {
        let id = Self.burstEvent
        let clock = Self.microClock(Self.burstHeldMicros)
        return try Self.decoder().decode(EventDetail.self, from: Data("""
        {"id":\(id),"sport":"basketball_nba","home_team":"Celtics","away_team":"Knicks","status":"live",
         "commence_time":"\(Self.stamp(-4200))","home_score":50,"away_score":48,
         "current_odds":{"home_probability":0.991,"away_probability":0.009},
         "hero_probability":0.991,"hero_probability_source":"blend",
         "hero_probability_observed_at":"\(clock)",
         "blend_fold_revision":{"\(id)":1439},
         "win_probability_sources":{"polymarket":{"value":0.991,"updated_at":"\(clock)"}}}
        """.utf8))
    }

    /// The history's readings before its last row (the held hero).
    nonisolated private static let heldHistoryLead: [Double] = [0.50, 0.54, 0.58]

    /// The hosted page's history: a blend line from tip-off that ends on the
    /// held hero, 60% at the held clock, so the chart draws before the burst and the
    /// page never falls through to the production history read.
    private func heldHistory(eventId: Int = 4242, end: Double = 0.60) throws -> EventHistoryResponse {
        let rows = Array(zip([-4200, -2400, -600, 0] as [TimeInterval], Self.heldHistoryLead + [end]))
        func points() -> String {
            rows.map { #"{"timestamp":"\#(Self.stamp($0.0))","home_probability":\#($0.1)}"# }
                .joined(separator: ",")
        }
        return try Self.decoder().decode(EventHistoryResponse.self, from: Data("""
        {"event_id":\(eventId),"home_team":"Celtics","away_team":"Knicks","status":"live",
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

        init(_ vm: EventDetailViewModel, eventId: Int = 4242) async throws {
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
            let page = NavigationStack { EventDetailView(eventId: eventId, viewModel: vm) }
                .environmentObject(PinManager())
                .environment(\.colorScheme, .light)
            let host = hostForMeasurement(page, at: .large)
            host.view.frame = CGRect(x: 0, y: 0, width: 390, height: 844)
            window = UIWindow(windowScene: scene)
            window.frame = host.view.frame
            window.rootViewController = host
            window.makeKeyAndVisible()
        }

        /// When the last `capture` finished drawing, on the process clock: the
        /// image's content is fixed here, after the wait and the draw, before it
        /// is encoded and written.
        private(set) var drawnAt: UInt64 = 0

        /// The final page, taken after the measured burst: the frame one display
        /// tick after the forced commit. `layoutIfNeeded` forces the pending
        /// update; then, value-blind (no condition on the image, no loop, no
        /// retry), the commit's completion and ONE display-link tick; then the
        /// window is drawn as it stands. Drawing inside the forced update
        /// (`afterScreenUpdates: true`) could, under load, snapshot Charts'
        /// image-queue layers an update behind the tip layer — a picture the
        /// screen never showed (#740: `0.3253970462539013`). One tick can still
        /// be too few under load; that red is a result, not a reason to wait more.
        /// `atDraw` runs straight after the draw, so what the test reads beside
        /// the image is from the same moment.
        func capture<T>(to url: URL, atDraw: () -> T) async throws -> (image: UIImage, atDraw: T) {
            window.layoutIfNeeded()
            await withCheckedContinuation { (committed: CheckedContinuation<Void, Never>) in
                CATransaction.begin()
                CATransaction.setCompletionBlock { committed.resume() }
                CATransaction.commit()
            }
            await DisplayTick.next()
            let image = UIGraphicsImageRenderer(bounds: window.bounds).image { _ in
                _ = window.drawHierarchy(in: window.bounds, afterScreenUpdates: false)
            }
            let observed = atDraw()
            drawnAt = DispatchTime.now().uptimeNanoseconds
            try XCTUnwrap(image.pngData()).write(to: url)
            return (image, observed)
        }

        func close() {
            window.isHidden = true
            previousKeyWindow?.makeKey()
        }
    }

    /// One display-link tick, once: `next()` returns at the first callback.
    @MainActor
    private final class DisplayTick: NSObject {
        private var ticked: CheckedContinuation<Void, Never>?

        static func next() async {
            let tick = DisplayTick()
            await withCheckedContinuation { (ticked: CheckedContinuation<Void, Never>) in
                tick.ticked = ticked
                CADisplayLink(target: tick, selector: #selector(fire(_:))).add(to: .main, forMode: .common)
            }
        }

        @objc private func fire(_ link: CADisplayLink) {
            link.invalidate()
            ticked?.resume()
            ticked = nil
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
        diagnostics = Diagnostics()
        diagnostics.loadStart = Self.loadAverage()
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
            self.diagnostics.pollStart = DispatchTime.now().uptimeNanoseconds
            await vm.load()
            self.diagnostics.pollEnd = DispatchTime.now().uptimeNanoseconds
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
            let dir = FileManager.default.temporaryDirectory.appendingPathComponent("native-10090-subsecond-hosted")
            try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
            let url = dir.appendingPathComponent("final-\(quarter ? "250ms" : "1s").png")
            _ = try await page.capture(to: url) {}
            print("SUBSECOND-10090 capture=\(url.path)")
        }
        marks = Array(marks.prefix(measured))
        diagnostics.reads = client.readStamps
        diagnostics.loadEnd = Self.loadAverage()

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

    // MARK: - Diagnostics (461be90b1c red; lane1 C1–C7)

    /// What a run records beside its marks, for the appended diagnostics only.
    /// Nothing here is asserted on. `anchorWall` and `anchorUptime` are one
    /// paired sample, taken as the run starts: the only bridge from the process
    /// clock to the wall clock the app's log lines and Spotlight's `viewedAt` use.
    private struct Diagnostics {
        var anchorWall = Date()
        var anchorUptime = DispatchTime.now().uptimeNanoseconds
        var loadStart: [Double] = []
        var loadEnd: [Double] = []
        var reads: [UInt64] = []
        var pollStart: UInt64?
        var pollEnd: UInt64?
    }

    private var diagnostics = Diagnostics()

    /// The host's 1, 5 and 15 minute load averages (the simulator shares the
    /// Mac's kernel), or none when the call fails.
    nonisolated private static func loadAverage() -> [Double] {
        var load = [Double](repeating: 0, count: 3)
        return getloadavg(&load, 3) == 3 ? load : []
    }

    /// The fields appended after `reads=N`. Every time is the process clock in
    /// ms, offset from the first fold's emit, so the quote that stalled and what
    /// ran beside it read on one timeline. Each per-quote list has 16 slots,
    /// slot i for `rev:4242=<20+i>`; a missing emit or mark prints `-`, so a gap
    /// never shifts the slots after it.
    ///
    /// Spotlight is read, never driven: no bind, refresh or recordViewed. Its
    /// `viewedAt` is when `recordViewed` ran; the CoreSpotlight writes run later,
    /// in the queued main-actor sync pass, which is not stamped here, so a sync
    /// stall would land after the `viewedAt` printed, not at it.
    private func diagnosticFields(_ r: Run, headline: [(mark: LiveTimingSeam.Mark, at: UInt64)]? = nil,
                                  chart: [(mark: LiveTimingSeam.Mark, at: UInt64)]? = nil,
                                  stampToBasis: [String: String] = [:]) -> String {
        let d = diagnostics
        let origin = r.emitted[expected[0]]
        func ms(_ at: UInt64?) -> String {
            guard let at, let origin else { return "-" }
            return String(format: "%.2f", Double(Int64(bitPattern: at &- origin)) / 1e6)
        }
        func byQuote(_ list: [(mark: LiveTimingSeam.Mark, at: UInt64)], _ basis: (LiveTimingSeam.Mark) -> String?) -> String {
            "[" + expected.map { b in
                guard let e = r.emitted[b], let m = list.first(where: { basis($0.mark) == b }) else { return "-" }
                return String(format: "%.2f", Double(Int64(bitPattern: m.at &- e)) / 1e6)
            }.joined(separator: ",") + "]"
        }
        func load(_ l: [Double]) -> String {
            l.isEmpty ? "-" : l.map { String(format: "%.2f", $0) }.joined(separator: "/")
        }
        // The wall clock at an uptime stamp, and back, through the one anchor.
        func wall(_ at: UInt64) -> Date {
            d.anchorWall.addingTimeInterval(Double(Int64(bitPattern: at &- d.anchorUptime)) / 1e9)
        }
        func uptime(_ date: Date) -> UInt64 {
            UInt64(bitPattern: Int64(bitPattern: d.anchorUptime) + Int64(date.timeIntervalSince(d.anchorWall) * 1e9))
        }

        var fields = "emit_ms=[" + expected.map { ms(r.emitted[$0]) }.joined(separator: ",") + "]"
        fields += " model_lag_ms=" + byQuote(r.adopted, { $0.basis })
        if let headline { fields += " view_headline_lag_ms=" + byQuote(headline, { $0.basis }) }
        if let chart { fields += " view_chart_lag_ms=" + byQuote(chart, { stampToBasis[$0.stamp] }) }
        fields += " resync_ms=" + ms(PacedStream.resyncEmittedAt)
        fields += " reads_ms=[" + d.reads.map { ms($0) }.joined(separator: ",") + "]"
        fields += " poll_ms=" + ms(d.pollStart) + "/" + ms(d.pollEnd)

        let index = SpotlightIndex10874.shared
        let readAt = Date()
        let viewed = index.entries.compactMap { e -> (SpotlightEntry10874, Date)? in
            guard let at = e.viewedAt, at >= d.anchorWall, at <= readAt else { return nil }
            return (e, at)
        }.sorted { $0.1 < $1.1 }
        fields += " spotlight_scope=" + (index.scope == nil ? "unbound" : "bound")
        fields += " spotlight_window_ms=" + ms(d.anchorUptime) + "/" + ms(uptime(readAt))
        let recorded: [String] = viewed.map { entry, at in
            "\(entry.subject.kind.rawValue):\(entry.subject.id)@" + ms(uptime(at))
        }
        fields += " spotlight_recorded_viewed_ms=" + (recorded.isEmpty ? "none" : "[" + recorded.joined(separator: ",") + "]")

        fields += " loadavg_start=" + load(d.loadStart) + " loadavg_end=" + load(d.loadEnd)
        let iso = ISO8601DateFormatter()
        iso.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        fields += " wall_at_first_emit=" + (origin.map { iso.string(from: wall($0)) } ?? "-")
        return fields
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
            + " \(diagnosticFields(r))"
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
            + " \(diagnosticFields(r, headline: headline, chart: r.viewChart, stampToBasis: stampToBasis))"
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

    // MARK: - Burst case

    /// The phone's nine frames arrive in ONE chunk on the hosted page. Every one
    /// is decoded, adopted and charted, in revision order, and the poll after it
    /// rolls nothing back. Lags are read from the moment the chunk was handed to
    /// URLSession, on the same process clock.
    ///
    /// The display is read from the page as drawn, captured within a second of
    /// the chunk and before the poll (`burstCase`): the hero prints the pair the
    /// last frame's 99.5% renders to, and the chart line ends there. The saved
    /// values alternate 99.5 / 99.55% and share one rounded headline, so an
    /// unchanged display need not produce a new view callback; the view marks
    /// are printed, not required (SwiftUI can skip the last `onChange`). The
    /// held 99.1% prints the same `<1%` / `>99%` pair and ends the line inside
    /// the same tolerance, so this display check cannot tell the last frame from
    /// the held page. This case proves drain, order, history and a correct final
    /// display; the companion below proves a visibly different last frame is
    /// drawn.
    func testHostedPageDrainsThePhonesNineFrameBurstToTheLatestHeadlineAndChart() async throws {
        try await burstCase(final: nil) { image, event in
            let drawn = try Self.readDrawn(image, expected: Self.burstWindow, final: 0.995)
            let labels = try XCTUnwrap(event.map(LivePriceActivity.displayedLabels(in:)))
            let (home, away) = try (XCTUnwrap(labels.home), XCTUnwrap(labels.away))
            print("SUBSECOND-10090 drawn=burst-final-saved \(drawn.ends) labels=\(away)|\(home) hero=\(drawn.hero.joined(separator: "|")) \(drawn.detail)")
            let printed = Set(drawn.hero.flatMap { $0.split(whereSeparator: { $0 == " " || $0 == "-" }).map(String.init) })
            XCTAssertTrue(printed.contains(home) && printed.contains(away),
                          "the hero prints the last frame's pair \(away) / \(home): \(drawn.hero)")
            if let end = Self.passingEnd(drawn) {
                XCTAssertEqual(end.bottom, 0.995, accuracy: 0.04,
                               "the chart line is drawn to the last frame's 99.5%")
            }
        }
    }

    /// Runs the saved burst. `final` replaces the last frame's `p` (nil = the
    /// saved bytes). The page is captured as soon as the model has adopted the
    /// last frame, and that capture must be taken within a second of the chunk
    /// reaching URLSession: a later capture is no timing result. It does not wait
    /// for the view marks, and it is taken before the poll. `drawn` reads the
    /// capture, with the event the model held when it was taken.
    private func burstCase(final: String?, drawn: (UIImage, EventDetail?) throws -> Void) async throws {
        PacedStream.reset(quarter: false, base: Self.recentBase(), burst: true, burstFinal: final)
        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [PacedStream.self]
        let session = URLSession(configuration: config)
        let base = PacedStream.base
        let client = Client(try heldBeforeBurst(), history: try heldHistory(eventId: Self.burstEvent, end: 0.991))
        let vm = EventDetailViewModel(
            eventId: Self.burstEvent, client: client,
            makeStreamHandle: { id in
                let t = try LiveEventStreamTransport(eventId: id, baseURL: "https://stub.invalid", session: session)
                t.connect()
                return t
            },
            now: { base - 595 },
            sleep: { _ in try? await Task.sleep(nanoseconds: 60_000_000_000) }
        )
        let page = try await MountedPage(vm, eventId: Self.burstEvent)
        defer { page.close(); vm.stopRefresh() }
        await waitUntil(10) { vm.event != nil }
        XCTAssertNotNil(vm.event, "the mounted page ran its own load")
        let loadReads = client.reads

        // The paced cases' poll, carrying the held read. It lands after the burst
        // has drained: it checks nothing rolls back, it does not load the drain.
        let poll = Task { @MainActor in
            try? await Task.sleep(nanoseconds: 2_100_000_000)
            await vm.load()
        }
        let last = Self.burstBasis(Self.burstFrames.count - 1)
        await waitUntil(Self.burstAfter + 1) {
            PacedStream.done && marks.contains { $0.mark.name == .modelHeadlineAdopted && $0.mark.basis == last }
        }
        let dir = FileManager.default.temporaryDirectory.appendingPathComponent("native-10090-subsecond-hosted")
        try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        let url = dir.appendingPathComponent("final-burst-\(final ?? "saved").png")
        let captureStart = DispatchTime.now().uptimeNanoseconds
        // The reads and the held event are taken at the draw, after the wait.
        let (image, (readsBefore, heldAtCapture)) = try await page.capture(to: url) { (client.reads, vm.event) }
        let writtenAt = DispatchTime.now().uptimeNanoseconds
        // The pixels go into the result bundle whatever happens (665 review R8):
        // the temp PNG dies with the simulator's app container.
        let attachment = XCTAttachment(image: image)
        attachment.name = "SUBSECOND-10090 final-burst-\(final ?? "saved")"
        attachment.lifetime = .keepAlways
        add(attachment)
        let chunkAt = try XCTUnwrap(PacedStream.emittedAt[last], "the burst was never handed to URLSession")
        // The deadline reads the moment the page was drawn; encoding and writing
        // the PNG afterwards is the test's own cost and is printed beside it.
        let capturedMs = Double(page.drawnAt &- chunkAt) / 1e6
        print(String(format: "SUBSECOND-10090 drawn=burst-final-%@ chunk_to_capture_start_ms=%.2f chunk_to_capture_ms=%.2f chunk_to_png_written_ms=%.2f reads_at_capture=%d capture=%@",
                     final ?? "saved", Double(captureStart &- chunkAt) / 1e6, capturedMs,
                     Double(writtenAt &- chunkAt) / 1e6, readsBefore, url.path))
        XCTAssertTrue(chunkAt < captureStart && captureStart <= page.drawnAt && page.drawnAt <= writtenAt,
                      "the capture stamps are ordered after the chunk")
        XCTAssertEqual(readsBefore, loadReads, "captured before the poll: the poll did not make it visible")
        XCTAssertLessThan(capturedMs, 1000, "late capture: no timing result")
        if capturedMs < 1000 { try drawn(image, heldAtCapture) }
        await poll.value
        try? await Task.sleep(nanoseconds: 300_000_000)
        XCTAssertNotNil(vm.history, "the hosted chart drew from the supplied history, not production")

        let expected = Self.burstFrames.indices.map(Self.burstBasis)
        let received = marks.filter { $0.mark.name == .frameReceived && $0.mark.basis.hasPrefix("rev:") }
        let adopted = marks.filter { $0.mark.name == .modelHeadlineAdopted && $0.mark.basis.hasPrefix("rev:") }
        let charted = marks.filter { $0.mark.name == .modelChartAppended }
        XCTAssertEqual(received.map(\.mark.basis), expected, "every frame is decoded once, in order")
        XCTAssertEqual(adopted.map(\.mark.basis), expected, "every frame is adopted once, in revision order")
        XCTAssertEqual(adopted.map(\.mark.path), Array(repeating: "stream", count: expected.count))
        XCTAssertEqual(charted.map(\.mark.basis), expected, "every adopted frame gets its own chart point")
        let latest = Double(final ?? Self.burstFrames[Self.burstFrames.count - 1].p) ?? -2
        XCTAssertEqual(vm.event?.currentOdds?.homeProbability ?? -1, latest, accuracy: 1e-9)
        XCTAssertEqual(vm.liveBlend.last?.homeProbability ?? -1, latest, accuracy: 1e-9,
                       "the chart edge agrees with the headline")
        XCTAssertGreaterThanOrEqual(client.reads, 2, "the page was read again and did not roll back")

        let viewHeadline = marks.filter { $0.mark.name == .viewHeadlineUpdated && $0.mark.basis.hasPrefix("rev:") }
        let lastStamp = charted.last?.mark.stamp
        let viewChart = marks.filter { $0.mark.name == .viewChartUpdated }
        func ms(_ at: UInt64?) -> Double { at.map { Double($0 &- chunkAt) / 1e6 } ?? .infinity }
        let latestHeadline = ms(viewHeadline.first { $0.mark.basis == last }?.at)
        let latestChart = ms(viewChart.first { $0.mark.stamp == lastStamp }?.at)
        let line = String(
            format: "SUBSECOND-10090 depth=\(final == nil ? "burst" : "burst-final-\(final!)") frames=%d bytes=%d chunk_to_first_received_ms=%.2f "
                + "chunk_to_last_received_ms=%.2f received_spread_ms=%.2f chunk_to_model_latest_ms=%.2f "
                + "chunk_to_view_headline_latest_ms=%.2f chunk_to_view_chart_latest_ms=%.2f "
                + "view_headline_marks=%d view_chart_marks=%d view_hook_latest=%@ reads=%d view_headline_revs=%@",
            received.count, Self.burstChunk(final: final).count, ms(received.first?.at), ms(received.last?.at),
            ms(received.last?.at) - ms(received.first?.at), ms(adopted.last?.at),
            latestHeadline, latestChart, viewHeadline.count, viewChart.count,
            latestHeadline.isFinite && latestChart.isFinite ? "present" : "missed", client.reads,
            viewHeadline.map { String($0.mark.basis.split(separator: "=").last ?? "?") }.joined(separator: ","))
        // The drawn page above is the display check; the view marks are hooks,
        // printed beside it (a missed last callback reads `inf`), not required.
        print(line)
    }

    /// Companion control: the saved burst with only its last `p` moved to 60%,
    /// far from the 99.5% the eight before it share, so the DRAWN page shows
    /// which frame it settled on. The hero's printed numbers and the chart
    /// line's drawn end are read from a capture taken within a second of the
    /// chunk and before the poll (`burstCase`). The view marks are the hook this
    /// control checks, so they are printed, not required.
    func testHostedPageDrawsTheBurstsChangedLastFrameInTheHeroAndAtTheChartEnd() async throws {
        try await burstCase(final: "0.6") { image, _ in
            let drawn = try Self.readDrawn(image, expected: Self.burstWindow, final: 0.6)
            print("SUBSECOND-10090 drawn=burst-final-0.6 \(drawn.ends) hero=\(drawn.hero.joined(separator: "|")) \(drawn.detail)")
            XCTAssertTrue(drawn.hero.contains { $0.contains("60%") } && drawn.hero.contains { $0.contains("40%") },
                          "the hero prints the last frame: \(drawn.hero)")
            if let end = Self.passingEnd(drawn) {
                XCTAssertEqual(end.bottom, 0.60, accuracy: 0.04,
                               "the chart line is drawn to the last frame's 60%, not held at the one before it")
            }
        }
    }

    // MARK: - Drawn-page reader (#10090 line 665; lane1b review R1–R8)

    /// The plot window the burst's chart shows. Pinned from the fixture, never
    /// derived from the model under test (R4);
    /// `testTheBurstFixturePinsItsPlotWindowAt40To100` proves the axis rule gives
    /// exactly this window for both burst cases.
    nonisolated static let burstWindow = ChartProbabilityAxis9483.Window(
        lowerPercent: 40, upperPercent: 100, tickPercents: [40, 50, 60, 70, 80, 90, 100])

    /// One text Vision read in the chart's left gutter, below its header, at its
    /// box's vertical middle in image pixels.
    nonisolated struct GutterText: Equatable {
        let text: String
        let y: CGFloat
        /// The leading `^\d{1,3}%` number as an axis label prints it ("50%" for
        /// "50% /", which the line can touch), or nil when the text is no label.
        var label: String? {
            text.range(of: #"^\d{1,3}%"#, options: .regularExpression)
                .flatMap { Int(text[$0].dropLast()) }.map { "\($0)%" }
        }
    }

    /// The gutter's labels matched, in order, to one window's ticks and fitted to
    /// a straight line of y against tick percent (R1–R3, R6).
    nonisolated struct AxisFit {
        nonisolated enum Status: Equatable {
            /// Fills the tick at `percent`, `residual` px from the fitted line.
            case matched(percent: Int, residual: CGFloat)
            /// Fits no tick and sits inside the matched span: the fit fails.
            case inside
            /// Fits no tick, above or below the matched span: printed only.
            case outside
            /// Below the fitted floor plus half a step: not the axis, printed only.
            case excluded
        }

        let window: ChartProbabilityAxis9483.Window
        /// Every axis-label text in the gutter, top to bottom, with its status.
        let labels: [(text: GutterText, status: Status)]
        /// y = intercept + slope × percent, in image pixels; nil below two matches.
        let line: (intercept: CGFloat, slope: CGFloat)?
        /// Why the fit does not pass, or nil when it passes.
        let failure: String?

        /// The fitted y of the window's lower bound: the plot's floor (R6).
        var floorY: CGFloat? { line.map { $0.intercept + $0.slope * CGFloat(window.lowerPercent) } }

        /// The probability the fitted axis puts at `y`.
        func probability(_ y: Int) -> Double? {
            line.map { Double((CGFloat(y) - $0.intercept) / $0.slope) / 100 }
        }
    }

    /// Matches the gutter top to bottom, keeping order, against `window`'s ticks
    /// as the chart prints them (R2): on a two-sided axis the 40 tick prints the
    /// away side's "60%", and only the 40 slot takes it. The longest such
    /// matching wins; a tie keeps the higher text. The fit passes only with at
    /// least 3 labels spanning at least 20 points, every one within 2 pt of the
    /// least-squares line, and no unmatched label inside their span (R3). Nothing
    /// is dropped and refitted (R5).
    nonisolated static func axisFit(gutter: [GutterText], expected window: ChartProbabilityAxis9483.Window,
                                    scale: CGFloat) -> AxisFit {
        let slots = window.ticks.reversed().map {
            (percent: Int(($0 * 100).rounded()), text: ChartProbabilityAxis9483.tick($0, sides: .homeAndAway).text)
        }
        let texts = gutter.filter { $0.label != nil }.sorted { $0.y < $1.y }
        let (n, m) = (texts.count, slots.count)
        var best = Array(repeating: Array(repeating: 0, count: m + 1), count: n + 1)
        for i in stride(from: n - 1, through: 0, by: -1) {
            for j in stride(from: m - 1, through: 0, by: -1) {
                best[i][j] = max(best[i + 1][j], best[i][j + 1],
                                 texts[i].label == slots[j].text ? best[i + 1][j + 1] + 1 : 0)
            }
        }
        var percent = [Int?](repeating: nil, count: n)
        var (i, j) = (0, 0)
        while i < n && j < m {
            if texts[i].label == slots[j].text && best[i][j] == best[i + 1][j + 1] + 1 {
                percent[i] = slots[j].percent
                (i, j) = (i + 1, j + 1)
            } else if best[i][j + 1] == best[i][j] {
                j += 1
            } else {
                i += 1
            }
        }

        let points = texts.indices.compactMap { k in percent[k].map { (x: CGFloat($0), y: texts[k].y) } }
        var line: (intercept: CGFloat, slope: CGFloat)?
        if points.count >= 2 {
            let count = CGFloat(points.count)
            let (mx, my) = (points.map(\.x).reduce(0, +) / count, points.map(\.y).reduce(0, +) / count)
            let sxx = points.map { ($0.x - mx) * ($0.x - mx) }.reduce(0, +)
            if sxx > 0 {
                let slope = points.map { ($0.x - mx) * ($0.y - my) }.reduce(0, +) / sxx
                line = (my - slope * mx, slope)
            }
        }

        let step = CGFloat(window.tickPercents.count > 1 ? window.tickPercents[1] - window.tickPercents[0]
                                                         : window.upperPercent - window.lowerPercent)
        let limit = line.map { $0.intercept + $0.slope * CGFloat(window.lowerPercent) + abs($0.slope) * step / 2 }
            ?? .infinity
        let matchedYs = texts.indices.filter { percent[$0] != nil }.map { texts[$0].y }
        let span = (matchedYs.min() ?? 0, matchedYs.max() ?? 0)
        let labels: [(text: GutterText, status: AxisFit.Status)] = texts.indices.map { k in
            let t = texts[k]
            if let p = percent[k] {
                let residual = line.map { t.y - ($0.intercept + $0.slope * CGFloat(p)) } ?? 0
                return (t, .matched(percent: p, residual: residual))
            }
            if t.y > limit { return (t, .excluded) }
            return (t, t.y > span.0 && t.y < span.1 ? .inside : .outside)
        }

        let matched = percent.compactMap { $0 }
        let worst = labels.compactMap { l -> (String, CGFloat)? in
            if case let .matched(_, r) = l.status { return (l.text.text, abs(r)) }
            return nil
        }.max { $0.1 < $1.1 }
        let failure: String?
        if matched.count < 3 {
            failure = "\(matched.count) labels match the window's ticks; at least 3 are needed"
        } else if (matched.max() ?? 0) - (matched.min() ?? 0) < 20 {
            failure = "the matched labels span \((matched.max() ?? 0) - (matched.min() ?? 0)) points; at least 20 are needed"
        } else if (line?.slope ?? 0) >= 0 {
            failure = "the matched labels do not fall down the gutter"
        } else if let worst, worst.1 > 2 * scale {
            failure = String(format: "label %@ is %.1f px off the axis line (limit %.1f px)", worst.0, worst.1, 2 * scale)
        } else if let stray = labels.first(where: { $0.status == .inside }) {
            failure = "label \(stray.text.text) fits no tick inside the matched span"
        } else {
            failure = nil
        }
        return AxisFit(window: window, labels: labels, line: line, failure: failure)
    }

    /// The rightmost drawn column of the line within `rows`, and its first and
    /// last line pixel. A line pixel is saturated or dark: not the white plot,
    /// the grey grid or the pale area fill. Every burst point is seconds apart on
    /// an hour-wide axis, so the line's end is one column.
    nonisolated static func readInk(_ cg: CGImage, rows: ClosedRange<Int>, scale: CGFloat) -> (x: Int, first: Int, last: Int)? {
        let (w, h) = (cg.width, cg.height)
        let rows = rows.clamped(to: 0 ... h - 1)
        var bytes = [UInt8](repeating: 0, count: w * h * 4)
        guard let ctx = CGContext(data: &bytes, width: w, height: h, bitsPerComponent: 8,
                                  bytesPerRow: w * 4, space: CGColorSpaceCreateDeviceRGB(),
                                  bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue) else { return nil }
        ctx.draw(cg, in: CGRect(x: 0, y: 0, width: w, height: h))
        func line(_ x: Int, _ y: Int) -> Bool {
            let i = (y * w + x) * 4
            let (r, g, b) = (Int(bytes[i]), Int(bytes[i + 1]), Int(bytes[i + 2]))
            return max(r, g, b) - min(r, g, b) > 60 || max(r, g, b) < 110
        }
        guard let right = stride(from: w - 1, through: w / 2, by: -1).first(where: { x in
            rows.filter { line(x, $0) }.count >= 2
        }) else { return nil }
        let band = max(w / 2, right - Int(scale) * 2) ... right
        let ys = rows.filter { y in band.contains { line($0, y) } }
        guard let first = ys.first, let last = ys.last else { return nil }
        return (right, first, last)
    }

    nonisolated struct PlotRead {
        let fit: AxisFit
        /// The window `.full` fit, made only when the expected window's fails (R5).
        let fullFit: AxisFit?
        /// `STALE-AXIS: …` or `AXIS-UNREADABLE (reader): …`; nil when the fit passed.
        let failure: String?
        /// Raw line pixels. On a failed axis the rows run from the first label to
        /// the last one read, and the pixels are printed, never converted.
        let ink: (x: Int, first: Int, last: Int)?
        /// The line's ends as probabilities, read only from a fit that passed.
        let end: (top: Double, bottom: Double)?
    }

    /// The axis check, then the line's ends on the fitted scale. A gutter that
    /// fails the expected window but fits `.full` is a stale axis (product or
    /// capture snapshot); anything else is a reader failure. Both fail the case;
    /// neither is retried, skipped or read on another scale (R5).
    nonisolated static func readPlot(gutter: [GutterText], image cg: CGImage,
                                     expected: ChartProbabilityAxis9483.Window, scale: CGFloat) throws -> PlotRead {
        let fit = axisFit(gutter: gutter, expected: expected, scale: scale)
        let labelYs = gutter.filter { $0.label != nil }.map(\.y)
        guard fit.failure == nil, let floorY = fit.floorY,
              let top = fit.labels.first(where: { if case .matched = $0.status { return true }; return false })
        else {
            let full = axisFit(gutter: gutter, expected: ChartProbabilityAxis9483.full, scale: scale)
            let failure = full.failure == nil
                ? "STALE-AXIS: drawn labels are the full window, model holds \(expected.lowerPercent)–\(expected.upperPercent) (product or capture snapshot; not a reader miss)"
                : "AXIS-UNREADABLE (reader): \(fit.failure ?? "no axis line")"
            var raw: (x: Int, first: Int, last: Int)?
            if let lo = labelYs.min(), let hi = labelYs.max() {
                raw = readInk(cg, rows: max(0, Int(lo) - 6) ... max(0, Int(lo) - 6, Int(hi)), scale: scale)
            }
            return PlotRead(fit: fit, fullFit: full, failure: failure, ink: raw, end: nil)
        }
        let ink = try XCTUnwrap(readInk(cg, rows: max(0, Int(top.text.y) - 6) ... max(0, Int(top.text.y) - 6, Int(floorY)),
                                        scale: scale), "a drawn line in the plot")
        let end = try (top: XCTUnwrap(fit.probability(ink.first)), bottom: XCTUnwrap(fit.probability(ink.last)))
        return PlotRead(fit: fit, fullFit: nil, failure: nil, ink: ink, end: end)
    }

    nonisolated struct Drawn {
        let hero: [String]
        let plot: PlotRead
        /// The durable record (R7): the whole gutter as text@y with each label's
        /// slot and residual, the class, the expected window, the raw ink and the
        /// image size. A recurrence is decided from this line alone.
        let detail: String

        var ends: String {
            plot.end.map { String(format: "end_top_p=%.3f end_bottom_p=%.3f", $0.top, $0.bottom) }
                ?? "end_top_p=none end_bottom_p=none"
        }
    }

    /// The line's ends when the axis passed. A failed axis fails the case with its
    /// class and the full record, and no end is asserted from it.
    nonisolated private static func passingEnd(_ drawn: Drawn, file: StaticString = #filePath,
                                               line: UInt = #line) -> (top: Double, bottom: Double)? {
        guard let failure = drawn.plot.failure else { return drawn.plot.end }
        XCTFail("\(failure); the line's end is not read from this axis. \(drawn.detail)", file: file, line: line)
        return nil
    }

    /// On a STALE-AXIS read only (lane1b 1841Z): where the line's raw end sits on
    /// the full window the labels fitted. MIXED when that is the height the
    /// expected window gives `final` (the tail projected on the new window under
    /// an old plot and axis: 0.33 for 60% on 40–100); COHERENT-STALE when it is
    /// 0.97 or above (the whole chart from before the last frame). Printed in the
    /// record so a red classifies itself without its pixels; it never changes
    /// what passes or fails.
    nonisolated static func staleClass(_ plot: PlotRead, expected: ChartProbabilityAxis9483.Window,
                                       final: Double) -> String? {
        guard plot.failure?.hasPrefix("STALE-AXIS:") == true, let full = plot.fullFit,
              let last = plot.ink?.last, let tail = full.probability(last) else { return nil }
        let projected = (final * 100 - Double(expected.lowerPercent))
            / Double(expected.upperPercent - expected.lowerPercent)
        let (mixed, stale) = (abs(tail - projected) <= 0.04, tail >= 0.97)
        let name = mixed && stale ? "MIXED-OR-COHERENT-STALE" : mixed ? "MIXED" : stale ? "COHERENT-STALE" : "UNCLASSIFIED"
        return String(format: "stale_class=%@ tail_full_p=%.3f new_window_p=%.3f", name, tail, projected)
    }

    nonisolated private static func describe(_ fit: AxisFit, gutter: [GutterText]) -> String {
        gutter.map { g in
            let at = String(format: "%@@%.1f", g.text, g.y)
            switch fit.labels.first(where: { $0.text == g })?.status {
            case let .matched(p, r)?: return at + String(format: "=%d(%+.1f)", p, r)
            case .inside?: return at + "!inside"
            case .outside?: return at + "~outside"
            case .excluded?: return at + "~excluded"
            case nil: return at
            }
        }.joined(separator: " ")
    }

    /// The page as drawn: the text printed above the chart, and the line's
    /// rightmost drawn column read on the chart's own axis labels, matched to
    /// `expected` (#11356: a focused window, not 0–100). Only text under the
    /// chart's own header is the gutter, so a hero number at the page's left edge
    /// is never read as a tick. `final` is the fixture's last frame, used only by
    /// the stale-axis class.
    nonisolated private static func readDrawn(_ image: UIImage, expected: ChartProbabilityAxis9483.Window,
                                              final: Double) throws -> Drawn {
        let cg = try XCTUnwrap(image.cgImage)
        let (w, h) = (cg.width, cg.height)
        let request = VNRecognizeTextRequest()
        request.recognitionLevel = .accurate
        request.usesLanguageCorrection = false
        try VNImageRequestHandler(cgImage: cg).perform([request])
        let texts: [(String, CGRect)] = (request.results ?? []).compactMap { o in
            guard let string = o.topCandidates(1).first?.string else { return nil }
            let b = o.boundingBox
            return (string, CGRect(x: b.minX * CGFloat(w), y: (1 - b.maxY) * CGFloat(h),
                                   width: b.width * CGFloat(w), height: b.height * CGFloat(h)))
        }
        let header = texts.first { $0.0.hasPrefix("Win Probability") }?.1.maxY ?? 0
        let gutter = texts.filter { $0.1.midX < CGFloat(w) * 0.3 && $0.1.minY > header }
            .map { GutterText(text: $0.0, y: $0.1.midY) }
            .sorted { $0.y < $1.y }
        let top = try XCTUnwrap(gutter.first { $0.label != nil }, "an axis label under the chart's header: \(texts.map(\.0))")
        let plot = try readPlot(gutter: gutter, image: cg, expected: expected, scale: image.scale)
        let line = plot.fit.line.map { String(format: "y=%.1f%+.3f*p", $0.intercept, $0.slope) } ?? "none"
        var detail = "axis=\(plot.failure.map { String($0.prefix { $0 != ":" && $0 != " " }) } ?? "PASS")"
            + " expected=\(expected.lowerPercent)-\(expected.upperPercent)/\(expected.tickPercents.map(String.init).joined(separator: ","))"
            + " fit=\(line) gutter=[\(describe(plot.fit, gutter: gutter))]"
        if let full = plot.fullFit { detail += " full_fit=[\(describe(full, gutter: gutter))]" }
        if let stale = staleClass(plot, expected: expected, final: final) { detail += " " + stale }
        detail += plot.ink.map { " ink_x=\($0.x) ink_y=\($0.first)-\($0.last)" } ?? " ink=none"
        detail += String(format: " img=%dx%d@%.0fx", w, h, image.scale)
        return Drawn(hero: texts.filter { $0.1.maxY < top.y }.map(\.0), plot: plot, detail: detail)
    }

    // MARK: - Drawn-page reader controls (lane1b 665 review K1–K10)

    // Pure, synthetic: no app render, no capture. The geometry is the reference
    // capture's: grid rows 1280.5…2105.5 px, 137.5 px per 10 points, 3x, ink top 1281.

    /// The window rule gives the pinned window for both burst cases: 4 history
    /// readings and 9 frames, the last frame must stay on the plot.
    func testTheBurstFixturePinsItsPlotWindowAt40To100() {
        for final in [nil, "0.6"] as [String?] {
            var frames = Self.burstFrames.compactMap { Double($0.p) }
            if let final, let p = Double(final) { frames[frames.count - 1] = p }
            XCTAssertEqual(frames.count, 9)
            XCTAssertEqual(ChartProbabilityAxis9483.window(readings: Self.heldHistoryLead + [0.991] + frames,
                                                           mustShow: [frames[frames.count - 1]]),
                           Self.burstWindow, "burst final \(final ?? "saved")")
        }
    }

    nonisolated private static func gridY(_ percent: Double) -> CGFloat { 1280.5 + CGFloat(100 - percent) * 13.75 }
    nonisolated private static func fullAxisY(_ percent: Double) -> CGFloat { 1280.5 + CGFloat(100 - percent) * 8.25 }

    /// The seven labels the pinned window prints, top to bottom, at their ticks.
    private var sevenLabels: [GutterText] {
        [("100%", 100), ("90%", 90), ("80%", 80), ("70%", 70), ("60%", 60), ("50%", 50), ("60%", 40)]
            .map { GutterText(text: $0.0, y: Self.gridY($0.1)) }
    }

    /// A white 60×2532 image with a dark 3 px line column from `top` to `bottom`.
    private func ink(from top: Int = 1281, to bottom: Int) throws -> CGImage {
        let (w, h) = (60, 2532)
        var bytes = [UInt8](repeating: 255, count: w * h * 4)
        for y in top ... bottom {
            for x in 48 ... 50 { bytes[(y * w + x) * 4 ..< (y * w + x) * 4 + 3] = [0, 0, 0] }
        }
        let provider = try XCTUnwrap(CGDataProvider(data: Data(bytes) as CFData))
        return try XCTUnwrap(CGImage(width: w, height: h, bitsPerComponent: 8, bitsPerPixel: 32, bytesPerRow: w * 4,
                                     space: CGColorSpaceCreateDeviceRGB(),
                                     bitmapInfo: CGBitmapInfo(rawValue: CGImageAlphaInfo.premultipliedLast.rawValue),
                                     provider: provider, decode: nil, shouldInterpolate: false, intent: .defaultIntent))
    }

    private func read(_ gutter: [GutterText], inkTo bottom: Int, from top: Int = 1281) throws -> PlotRead {
        try Self.readPlot(gutter: gutter, image: ink(from: top, to: bottom), expected: Self.burstWindow, scale: 3)
    }

    /// K1 — all seven labels, ink to the 60% line: passes and reads 0.60.
    func testDrawnReaderK1ReadsAllSevenLabelsAndTheLineTo60() throws {
        let r = try read(sevenLabels, inkTo: Int(Self.gridY(60)))
        XCTAssertNil(r.failure)
        XCTAssertEqual(r.end?.bottom ?? -1, 0.60, accuracy: 0.01)
    }

    /// K2 — the line hides "50%": the known occlusion stays green.
    func testDrawnReaderK2PassesWhenTheLineHides50() throws {
        let r = try read(sevenLabels.filter { $0.text != "50%" }, inkTo: Int(Self.gridY(60)))
        XCTAssertNil(r.failure)
        XCTAssertEqual(r.end?.bottom ?? -1, 0.60, accuracy: 0.01)
    }

    /// K3 — the away "60%" unread: the floor is still the fitted 40 line.
    func testDrawnReaderK3KeepsTheFitted40FloorWhenTheAwayLabelIsUnread() throws {
        let r = try read(Array(sevenLabels.dropLast()), inkTo: Int(Self.gridY(60)))
        XCTAssertNil(r.failure)
        XCTAssertEqual(r.fit.floorY ?? -1, Self.gridY(40), accuracy: 1)
        XCTAssertEqual(r.end?.bottom ?? -1, 0.60, accuracy: 0.01)
    }

    /// K4 — the retained failure as a stale axis: the full window's labels at
    /// full-axis heights, ink to 1834. The old reader returned 0.33 here.
    func testDrawnReaderK4FailsAStaleFullAxisAsStaleAxis() throws {
        let stale = [("100%", 100.0), ("75%", 75), ("50%", 50), ("75%", 25), ("100%", 0)]
            .map { GutterText(text: $0.0, y: Self.fullAxisY($0.1)) }
        let r = try read(stale, inkTo: 1834)
        XCTAssertTrue(r.failure?.hasPrefix("STALE-AXIS:") == true, r.failure ?? "passed")
        XCTAssertNil(r.end, "no end is read from a failed axis")
    }

    /// K12 (lane1b 1841Z) — the stale axis classifies its line's end on the full
    /// fit and still fails exactly as K4: MIXED at 1834 (0.33, the 60% tail on
    /// 40–100), COHERENT-STALE near the top, UNCLASSIFIED at 50%.
    func testDrawnReaderK12ClassifiesAStaleAxisWithoutChangingItsFailure() throws {
        let stale = [("100%", 100.0), ("75%", 75), ("50%", 50), ("75%", 25), ("100%", 0)]
            .map { GutterText(text: $0.0, y: Self.fullAxisY($0.1)) }
        for (bottom, name) in [(1834, "MIXED"), (1289, "COHERENT-STALE"), (Int(Self.fullAxisY(50)), "UNCLASSIFIED")] {
            let r = try read(stale, inkTo: bottom)
            XCTAssertTrue(r.failure?.hasPrefix("STALE-AXIS:") == true, r.failure ?? "passed")
            XCTAssertNil(r.end, "no end is read from a failed axis")
            let line = try XCTUnwrap(Self.staleClass(r, expected: Self.burstWindow, final: 0.6))
            XCTAssertTrue(line.hasPrefix("stale_class=\(name) "), line)
        }
        XCTAssertNil(Self.staleClass(try read(sevenLabels, inkTo: Int(Self.gridY(60))), expected: Self.burstWindow, final: 0.6),
                     "a passing axis has no stale class")
    }

    /// K5 — the retained failure as a misread: "70%" read as "50%", the rest
    /// right, ink to 1834. The old reader returned 0.33 here.
    func testDrawnReaderK5FailsA70ReadAs50AsUnreadable() throws {
        let misread = sevenLabels.map { $0.y == Self.gridY(70) ? GutterText(text: "50%", y: $0.y) : $0 }
        let r = try read(misread, inkTo: 1834)
        XCTAssertTrue(r.failure?.hasPrefix("AXIS-UNREADABLE (reader):") == true, r.failure ?? "passed")
        XCTAssertNil(r.end, "the least-squares line never rescues a misread label")
    }

    /// K6 — only "100%" and a "50%" at the plot's middle: the two-tick scale never passes.
    func testDrawnReaderK6NeverPassesTwoLabels() throws {
        let r = try read([GutterText(text: "100%", y: Self.gridY(100)), GutterText(text: "50%", y: Self.gridY(70))],
                         inkTo: 1834)
        XCTAssertTrue(r.failure?.hasPrefix("AXIS-UNREADABLE (reader):") == true, r.failure ?? "passed")
        XCTAssertNil(r.end)
    }

    /// K7 — an extra away "60%" at the home 60 height: one slot, one label.
    func testDrawnReaderK7FailsADuplicateSlot() throws {
        let r = try read(sevenLabels + [GutterText(text: "60%", y: Self.gridY(60))], inkTo: Int(Self.gridY(60)))
        XCTAssertNotNil(r.failure)
        XCTAssertNil(r.end)
    }

    /// K8 — the right axis with the line held near the top: it reads ≈0.97, so
    /// the 60% assertion still fails. The wrong end is not hidden.
    func testDrawnReaderK8ReadsAHeldLineAtItsOwnHeight() throws {
        let r = try read(sevenLabels, inkTo: 1319)
        XCTAssertNil(r.failure)
        let bottom = try XCTUnwrap(r.end?.bottom)
        XCTAssertEqual(bottom, 0.97, accuracy: 0.01)
        XCTAssertGreaterThan(abs(bottom - 0.60), 0.04)
    }

    /// K9 — the right axis with the line to 50%: it reads 0.50, which the 60% assertion fails.
    func testDrawnReaderK9ReadsALineTo50As50() throws {
        let r = try read(sevenLabels, inkTo: Int(Self.gridY(50)))
        XCTAssertNil(r.failure)
        let bottom = try XCTUnwrap(r.end?.bottom)
        XCTAssertEqual(bottom, 0.50, accuracy: 0.01)
        XCTAssertGreaterThan(abs(bottom - 0.60), 0.04)
    }

    /// K10 — a "62%" below the plot is excluded and printed, not a failure.
    func testDrawnReaderK10ExcludesALabelBelowThePlot() throws {
        let below = GutterText(text: "62%", y: 2200)
        let r = try read(sevenLabels + [below], inkTo: Int(Self.gridY(60)))
        XCTAssertNil(r.failure)
        XCTAssertEqual(r.fit.labels.first { $0.text == below }?.status, .excluded)
        XCTAssertEqual(r.end?.bottom ?? -1, 0.60, accuracy: 0.01)
    }

    /// K11 (native, from mutant M7) — R3's 2 pt bound: "70%" 4 pt off its line
    /// fails as unreadable; 1 pt off still passes.
    func testDrawnReaderK11HoldsEveryLabelWithin2PointsOfTheFit() throws {
        func shifted(_ points: CGFloat) -> [GutterText] {
            sevenLabels.map { $0.y == Self.gridY(70) ? GutterText(text: $0.text, y: $0.y + points * 3) : $0 }
        }
        let far = try read(shifted(4), inkTo: Int(Self.gridY(60)))
        XCTAssertTrue(far.failure?.hasPrefix("AXIS-UNREADABLE (reader): label 70%") == true, far.failure ?? "passed")
        XCTAssertNil(far.end)
        let near = try read(shifted(1), inkTo: Int(Self.gridY(60)))
        XCTAssertNil(near.failure)
        XCTAssertEqual(near.end?.bottom ?? -1, 0.60, accuracy: 0.01)
    }
}
