import Combine
import SwiftUI
import UIKit
import Vision
import XCTest
@testable import Bain_Luck

/// #8320 (v24) — the event hero carries ONE compact delivery cue, and the exact
/// device receipt time is disclosed on tap only.
///
/// Alex, build 32 (`chart-9655-after.md`): a receipt time with seconds in the
/// centre of the hero was "embarrassing"; build 27 (BAL–DAL): a real update whose
/// rounded value did not move must still visibly acknowledge receipt, and first
/// load, cache rereads and socket heartbeats must never pulse.
final class CompactEventPriceStatusTests: XCTestCase {

    // MARK: - Receipt acknowledgement (the gate the mounted leaf runs)

    /// The leaf's own gate, composed exactly as its `.task` composes it.
    private func ack(_ cue: inout LivePriceReceiptCue, sequence: Int, receivedAt: Date?,
                     status: LiveUpdateStatus = .live, active: Bool = true) -> Bool {
        cue.consume(sequence: sequence, receivedAt: receivedAt,
                    enabled: CompactEventPriceStatus.acknowledgesReceipts(status: status, sceneActive: active))
    }

    func testANewerAcceptedReceiptAtTheSame55IsAcknowledged() {
        var cue = LivePriceReceiptCue()
        let t = Date(timeIntervalSince1970: 1_790_600_000)
        XCTAssertFalse(ack(&cue, sequence: 8, receivedAt: t), "first load is not a receipt")
        XCTAssertTrue(ack(&cue, sequence: 9, receivedAt: t.addingTimeInterval(1)),
                      "a newer accepted revision is acknowledged even though 55% did not move")
    }

    func testFirstLoadHeartbeatAndCacheRereadNeverAcknowledge() {
        var cue = LivePriceReceiptCue()
        let t = Date(timeIntervalSince1970: 1_790_600_000)
        XCTAssertFalse(ack(&cue, sequence: 4, receivedAt: t), "first load")
        // A heartbeat re-renders with the same sequence, possibly a new status.
        XCTAssertFalse(ack(&cue, sequence: 4, receivedAt: t, status: .awaitingUpdate), "heartbeat")
        XCTAssertFalse(ack(&cue, sequence: 4, receivedAt: t, status: .live), "heartbeat")
        // A cache reread hands back an older or equal revision.
        XCTAssertFalse(ack(&cue, sequence: 3, receivedAt: t), "older cached revision")
        XCTAssertFalse(ack(&cue, sequence: 4, receivedAt: t), "same revision reread")
        XCTAssertTrue(ack(&cue, sequence: 5, receivedAt: t.addingTimeInterval(2)), "control: a real receipt still acks")
    }

    func testMissingReceiptNeverBecomesAnAcknowledgement() {
        var cue = LivePriceReceiptCue()
        XCTAssertFalse(ack(&cue, sequence: 0, receivedAt: nil))
        XCTAssertFalse(ack(&cue, sequence: 1, receivedAt: nil))
    }

    func testFinalHiddenAndInterruptedNeverAcknowledgeAndBackgroundNeverReplays() {
        XCTAssertEqual(LiveUpdateStatus.decide(status: "final", delivering: true, acceptedUpdate: true,
                                               refreshFailed: false), .hidden,
                       "control: a finished game reaches this leaf as hidden")
        XCTAssertFalse(CompactEventPriceStatus.acknowledgesReceipts(status: .hidden, sceneActive: true))
        XCTAssertFalse(CompactEventPriceStatus.acknowledgesReceipts(status: .interrupted, sceneActive: true))
        XCTAssertFalse(CompactEventPriceStatus.acknowledgesReceipts(status: .live, sceneActive: false))

        var cue = LivePriceReceiptCue()
        let t = Date()
        XCTAssertFalse(ack(&cue, sequence: 1, receivedAt: t))
        XCTAssertFalse(ack(&cue, sequence: 2, receivedAt: t, active: false), "arrived while backgrounded")
        XCTAssertFalse(ack(&cue, sequence: 2, receivedAt: t), "returning does not replay it")
        XCTAssertFalse(ack(&cue, sequence: 3, receivedAt: t, status: .interrupted))
        XCTAssertFalse(ack(&cue, sequence: 4, receivedAt: t, status: .hidden))
    }

    // MARK: - What the collapsed line says

    func testTheCollapsedLineCarriesNoReceiptTimeAndEachStateReadsDistinctly() {
        let states: [LiveUpdateStatus] = [.awaitingUpdate, .live, .autoRefresh, .interrupted]
        let shown = states.map { CompactEventPriceStatus(status: $0) }
        XCTAssertTrue(shown.allSatisfy(\.isVisible))
        XCTAssertEqual(Set(shown.map(\.title)).count, states.count, "titles must not collapse two states")
        XCTAssertEqual(Set(shown.map(\.glyph)).count, states.count, "glyphs must not collapse two states")
        for item in shown {
            XCTAssertNil(item.title.range(of: #"\d"#, options: .regularExpression),
                         "\(item.title): a time or age in the hero line")
            XCTAssertFalse(item.title.contains("Received"), item.title)
            XCTAssertNotEqual(item.glyph, CompactEventPriceStatus.receiptGlyph,
                              "a resting state must not look like a receipt")
        }
        XCTAssertFalse(CompactEventPriceStatus(status: .hidden).isVisible)
    }

    func testVoiceOverStillSpeaksStateAndReceiptDistinctly() {
        let t = Date(timeIntervalSince1970: 1_790_600_000)
        let spoken = LivePriceReceiptCue.accessibilityText(status: .live, receivedAt: t)
        XCTAssertTrue(spoken.hasPrefix(LiveUpdateStatus.live.accessibilityText), spoken)
        XCTAssertTrue(spoken.contains("received on this device"), spoken)
        XCTAssertTrue(LivePriceReceiptCue.accessibilityText(status: .awaitingUpdate, receivedAt: nil)
            .contains("No live update received on this page yet"))
    }

    // MARK: - The mounted contract (source scans; comments stripped first)

    private func code(_ directory: String, _ file: String) throws -> String {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()   // BainLuckTests
            .deletingLastPathComponent()   // Bain Luck (project dir)
            .appendingPathComponent("Bain Luck")
            .appendingPathComponent(directory)
            .appendingPathComponent(file)
        return try String(contentsOf: url, encoding: .utf8)
            .split(separator: "\n", omittingEmptySubsequences: false)
            .map { line -> String in
                guard let slashes = line.range(of: "//") else { return String(line) }
                return String(line[line.startIndex..<slashes.lowerBound])
            }
            .joined(separator: "\n")
            .filter { !$0.isWhitespace }
    }

    private func occurrences(of needle: String, in haystack: String) -> Int {
        haystack.components(separatedBy: needle).count - 1
    }

    /// The disclosure button's body, from its declaration to the next member.
    private func probabilityDetailsBody() throws -> String {
        let page = try code("Views", "EventDetailView.swift")
        guard let start = page.range(of: "privatefuncprobabilityDetails(confidenceTier:String?)->someView{") else {
            XCTFail("probabilityDetails moved; re-aim this scan"); return ""
        }
        let rest = page[start.upperBound...]
        let end = rest.range(of: "privatefuncchartHeaderBar(")?.lowerBound ?? rest.endIndex
        return String(rest[..<end])
    }

    func testThePageMountsOneCompactCueInsideTheExistingDisclosureButton() throws {
        let page = try code("Views", "EventDetailView.swift")
        let body = try probabilityDetailsBody()
        XCTAssertTrue(body.hasPrefix("Button{showProbabilityDetails.toggle()}label:{"),
                      "control: the scan is reading the disclosure button")
        XCTAssertEqual(occurrences(of: "CompactEventPriceStatusView(status:vm.liveUpdateStatus", in: page), 1)
        XCTAssertEqual(occurrences(of: "CompactEventPriceStatusView(status:vm.liveUpdateStatus", in: body), 1)
        XCTAssertEqual(occurrences(of: "VisibleLivePriceStatusView(", in: page), 0, "a second cue beside the new one")
        XCTAssertEqual(occurrences(of: "LiveUpdateStatusView(status:vm.liveUpdateStatus)", in: page), 0)
        XCTAssertTrue(body.contains("sequence:vm.priceActivity?.sequence??0"))
        XCTAssertTrue(body.contains("receivedAt:vm.priceActivity?.receivedAt"))
    }

    func testTheExactReceiptStaysInTheTapDisclosureWithItsTargetAndAccessibility() throws {
        let body = try probabilityDetailsBody()
        XCTAssertTrue(body.contains("minHeight:44"), "the 44pt tap target")
        XCTAssertTrue(body.contains(".popover(isPresented:$showProbabilityDetails,arrowEdge:.top){FreshnessRevealView(status:vm.liveUpdateStatus,lastReceivedAt:vm.priceActivity?.receivedAt"))
        XCTAssertTrue(body.contains("LivePriceReceiptCue.accessibilityText(status:vm.liveUpdateStatus"))
        XCTAssertTrue(body.contains(".accessibilityHint(\"Showsconnectionstatusandwhenthelastpriceupdatereachedthisphone\")"))
    }

    func testTheLeafHasNoButtonNoClockAndNoLoop() throws {
        let leaf = try code("Components", "CompactEventPriceStatusView.swift")
        XCTAssertTrue(leaf.contains("structCompactEventPriceStatusView:View{"), "control: scanning the leaf")
        for banned in ["Button", "Timer", "TimelineView", "repeatForever", "receiptText", ".formatted("] {
            XCTAssertFalse(leaf.contains(banned), "the compact leaf contains \(banned)")
        }
    }
}

// MARK: - Rendered evidence

@MainActor
extension CompactEventPriceStatusTests {
    private final class PageClient: EventDetailProviding, @unchecked Sendable {
        struct Missing: Error {}
        let event: EventDetail
        init() throws {
            let decoder = JSONDecoder(); decoder.keyDecodingStrategy = .convertFromSnakeCase
            event = try decoder.decode(EventDetail.self, from: Data(#"{"id":4243,"home_team":"Dallas Cowboys","away_team":"Baltimore Ravens","sport":"americanfootball_nfl","status":"live","home_score":24,"away_score":27,"current_odds":{"home_probability":0.45,"away_probability":0.55,"home_rendered_percent":45,"away_rendered_percent":55},"hero_probability":0.45,"hero_probability_source":"blend","blend_fold_revision":{"4243":20},"win_probability_sources":{"kalshi":{"value":0.45,"updated_at":"2026-09-27T23:44:48Z"}}}"#.utf8))
        }
        func fetchEvent(id: Int) async throws -> EventDetail { event }
        func fetchEventHistory(id: Int, hours: Int) async throws -> EventHistoryResponse { throw Missing() }
        func fetchRelatedFutures(eventId: Int) async throws -> RelatedFuturesResponse { throw Missing() }
        func fetchTeamProgression(eventId: Int) async throws -> TeamProgressionResponse { throw Missing() }
        func fetchGameMarkets(eventId: Int) async throws -> GameMarketsResponse { throw Missing() }
        func fetchLineMovement(eventId: Int) async throws -> LineMovementResponse { throw Missing() }
    }

    private final class PageHandle: LiveStreamHandle, @unchecked Sendable {
        var callbacks: [String: [@MainActor (String) -> Void]] = [:]
        func on(_ event: String, _ handler: @escaping @MainActor (String) -> Void) {
            callbacks[event, default: []].append(handler)
        }
        func close() {}
        func open() { for handler in callbacks["open"] ?? [] { handler("") } }
    }

    private final class Input: ObservableObject {
        @Published var sequence = 0
        @Published var active = true
        let date = Date(timeIntervalSince1970: 1_790_600_000)
    }

    private struct Probe: View {
        @ObservedObject var input: Input
        var body: some View {
            VStack(spacing: 2) {
                Text("55% – 45%").font(.title3)
                CompactEventPriceStatusView(status: .live, sequence: input.sequence,
                    receivedAt: input.date.addingTimeInterval(Double(input.sequence)))
            }
            .frame(width: 180, height: 70).background(.white)
            .environment(\.scenePhase, input.active ? .active : .background)
            .environment(\.colorScheme, .light)
        }
    }

    private func window(_ host: UIViewController, _ size: CGSize) -> UIWindow {
        host.view.frame = CGRect(origin: .zero, size: size)
        let window = UIWindow(frame: host.view.frame)
        window.rootViewController = host; window.isHidden = false
        return window
    }

    private func settle(_ host: UIViewController, _ seconds: TimeInterval) {
        let until = Date().addingTimeInterval(seconds)
        repeat {
            host.view.setNeedsLayout(); host.view.layoutIfNeeded()
            RunLoop.current.run(until: min(until, Date().addingTimeInterval(0.01)))
        } while Date() < until
    }

    private func shot(_ host: UIViewController, _ name: String) throws -> UIImage {
        let image = UIGraphicsImageRenderer(bounds: host.view.bounds).image { _ in
            host.view.drawHierarchy(in: host.view.bounds, afterScreenUpdates: true)
        }
        let url = FileManager.default.temporaryDirectory.appendingPathComponent("compact-price-status-\(name).png")
        try XCTUnwrap(image.pngData()).write(to: url)
        print("Compact price status rendered evidence: \(url.path)")
        return image
    }

    private func text(_ image: UIImage) throws -> String {
        let request = VNRecognizeTextRequest(); request.recognitionLevel = .accurate
        try VNImageRequestHandler(cgImage: XCTUnwrap(image.cgImage)).perform([request])
        return (request.results ?? []).compactMap { $0.topCandidates(1).first?.string }.joined(separator: " ")
    }

    private func green(_ image: UIImage) throws -> Double {
        let cg = try XCTUnwrap(image.cgImage)
        var bytes = [UInt8](repeating: 0, count: cg.width * cg.height * 4)
        return try bytes.withUnsafeMutableBytes { buffer in
            let ctx = try XCTUnwrap(CGContext(data: buffer.baseAddress, width: cg.width, height: cg.height,
                bitsPerComponent: 8, bytesPerRow: cg.width * 4, space: CGColorSpaceCreateDeviceRGB(),
                bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue))
            ctx.draw(cg, in: CGRect(x: 0, y: 0, width: cg.width, height: cg.height))
            let values = buffer.bindMemory(to: UInt8.self)
            var total = 0.0
            for i in stride(from: 0, to: values.count, by: 4) {
                total += Double(max(0, Int(values[i + 1]) - max(Int(values[i]), Int(values[i + 2]))))
            }
            return total / Double(cg.width * cg.height)
        }
    }

    func testMountedSame55ReceiptIsAcknowledgedOnceThenSettlesWithoutAClock() throws {
        let input = Input()
        let host = hostForMeasurement(Probe(input: input), at: .large)
        let win = window(host, CGSize(width: 180, height: 70))
        defer { win.isHidden = true }
        settle(host, 0.15)
        let initialShot = try shot(host, "initial")
        let initial = try green(initialShot)
        XCTAssertTrue(try text(initialShot).contains("Live updates"), "control: the leaf rendered")

        input.sequence = 1; settle(host, 0.05)
        let received = try shot(host, "same55-received")
        XCTAssertGreaterThan(try green(received), initial + 0.2, "a real same-value receipt is visible")
        let receivedText = try text(received)
        XCTAssertTrue(receivedText.contains("55%"), "the receipt must not fabricate a changed percentage")
        XCTAssertNil(receivedText.range(of: #"\d{1,2}:\d{2}"#, options: .regularExpression),
                     "a receipt time reached the hero: \(receivedText)")

        settle(host, 1.5)
        XCTAssertLessThan(try green(shot(host, "settled")), initial + 0.1, "the acknowledgement is finite")
        settle(host, 1.0)
        XCTAssertLessThan(try green(shot(host, "still-settled")), initial + 0.1, "no periodic pulse")

        input.sequence = 2; settle(host, 0.05)
        input.active = false; settle(host, 0.1)
        XCTAssertLessThan(try green(shot(host, "background")), initial + 0.1)
        input.active = true; settle(host, 0.1)
        XCTAssertLessThan(try green(shot(host, "foreground-no-replay")), initial + 0.1)
    }

    func testEveryStateStaysReadableAtPhoneAndAccessibilitySizes() throws {
        for (name, status, size) in [
            ("waiting-default", LiveUpdateStatus.awaitingUpdate, DynamicTypeSize.large),
            ("live-xxxl", .live, .xxxLarge),
            ("fallback-accessibility", .autoRefresh, .accessibility3),
            ("interrupted-accessibility", .interrupted, .accessibility3)
        ] {
            let view = CompactEventPriceStatusView(status: status, sequence: 5,
                receivedAt: Date(timeIntervalSince1970: 1_790_600_000))
                .frame(width: 150).padding().background(.white)
                .environment(\.scenePhase, .active).environment(\.colorScheme, .light)
            let host = hostForMeasurement(view, at: size)
            let win = window(host, CGSize(width: 390, height: 280))
            defer { win.isHidden = true }
            settle(host, 0.1)
            let recognized = try text(shot(host, name))
            XCTAssertTrue(recognized.contains(status.title), "\(name): \(recognized)")
            XCTAssertFalse(recognized.contains("Received"), "\(name): \(recognized)")
        }
    }

    func testActualEventPageShowsOneCompactLineBesideTheProbability() async throws {
        for (name, size) in [("page-390", DynamicTypeSize.large), ("page-390-xxxl", .xxxLarge)] {
            let client = try PageClient(), handle = PageHandle()
            let vm = EventDetailViewModel(eventId: 4243, client: client, makeStreamHandle: { _ in handle })
            await vm.load(); handle.open()
            let page = NavigationStack { EventDetailView(eventId: 4243, viewModel: vm) }
                .environmentObject(PinManager())
                .environment(\.scenePhase, .active).environment(\.colorScheme, .light)
            let host = hostForMeasurement(page, at: size)
            let win = window(host, CGSize(width: 390, height: 844))
            defer { vm.stopRefresh(); win.isHidden = true }
            settle(host, 0.4)
            let recognized = try text(shot(host, name))
            XCTAssertTrue(recognized.contains("Win Probability"), recognized)
            XCTAssertTrue(recognized.contains("Waiting for update"), recognized)
            XCTAssertTrue(recognized.contains("55%"), recognized)
            XCTAssertTrue(recognized.contains("45%"), recognized)
            XCTAssertNil(recognized.range(of: "No live.*update yet", options: .regularExpression),
                         "the old second receipt row is back: \(recognized)")
            XCTAssertFalse(recognized.contains("Received"), "a receipt time in the hero: \(recognized)")
        }
    }
}
