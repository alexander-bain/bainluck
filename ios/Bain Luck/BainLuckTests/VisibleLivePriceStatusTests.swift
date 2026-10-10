import Combine
import SwiftUI
import UIKit
import Vision
import XCTest
@testable import Bain_Luck

final class VisibleLivePriceStatusTests: XCTestCase {
    func testNewAcceptedReceiptEarnsCueEvenWhenPrintedPriceStays55() {
        var cue = LivePriceReceiptCue()
        let date = Date(timeIntervalSince1970: 1_790_600_000)
        XCTAssertFalse(cue.consume(sequence: 8, receivedAt: date, enabled: true), "mount is not receipt")
        XCTAssertTrue(cue.consume(sequence: 9, receivedAt: date.addingTimeInterval(1), enabled: true))
        XCTAssertFalse(cue.consume(sequence: 9, receivedAt: date.addingTimeInterval(1), enabled: true))
        XCTAssertFalse(cue.consume(sequence: 8, receivedAt: date, enabled: true), "old activity cannot pulse")
        XCTAssertFalse(cue.consume(sequence: 9, receivedAt: date, enabled: true), "old activity cannot lower the watermark")
    }

    func testNoReceiptAndInactiveChangesNeverReplayOnReturn() {
        var cue = LivePriceReceiptCue()
        XCTAssertFalse(cue.consume(sequence: 0, receivedAt: nil, enabled: true))
        XCTAssertFalse(cue.consume(sequence: 1, receivedAt: nil, enabled: true))
        let date = Date()
        XCTAssertFalse(cue.consume(sequence: 2, receivedAt: date, enabled: false))
        XCTAssertFalse(cue.consume(sequence: 2, receivedAt: date, enabled: true))
        XCTAssertTrue(cue.consume(sequence: 3, receivedAt: date, enabled: true))
    }

    func testDisclosureLabelsReceiptAsLocalAndKeepsStatusTruthful() {
        XCTAssertEqual(LivePriceReceiptCue.receiptText(nil), "No live update yet")
        XCTAssertTrue(LivePriceReceiptCue.accessibilityText(status: .awaitingUpdate, receivedAt: Date())
            .contains("Waiting for a live price update"))
        XCTAssertTrue(LivePriceReceiptCue.accessibilityText(status: .autoRefresh, receivedAt: Date())
            .contains("Checking automatically"))
        XCTAssertTrue(LivePriceReceiptCue.accessibilityText(status: .interrupted, receivedAt: Date())
            .contains("last refresh failed"))
        XCTAssertTrue(LivePriceReceiptCue.accessibilityText(status: .live, receivedAt: Date())
            .contains("received on this device"))
    }
}

@MainActor
extension VisibleLivePriceStatusTests {
    private final class PageClient: EventDetailProviding, @unchecked Sendable {
        struct Missing: Error {}
        let event: EventDetail
        init() throws {
            let decoder = JSONDecoder(); decoder.keyDecodingStrategy = .convertFromSnakeCase
            event = try decoder.decode(EventDetail.self, from: Data(#"{"id":4242,"home_team":"Dallas Cowboys","away_team":"Baltimore Ravens","sport":"americanfootball_nfl","status":"live","home_score":24,"away_score":27,"current_odds":{"home_probability":0.45,"away_probability":0.55,"home_rendered_percent":45,"away_rendered_percent":55},"hero_probability":0.45,"hero_probability_source":"blend","blend_fold_revision":{"4242":20},"win_probability_sources":{"kalshi":{"value":0.45,"updated_at":"2026-09-27T23:44:48Z"}}}"#.utf8))
        }
        func fetchEvent(id: Int) async throws -> EventDetail { event }
        func fetchEventHistory(id: Int, hours: Int) async throws -> EventHistoryResponse { throw Missing() }
        func fetchRelatedFutures(eventId: Int) async throws -> RelatedFuturesResponse { throw Missing() }
        func fetchTeamProgression(eventId: Int) async throws -> TeamProgressionResponse { throw Missing() }
        func fetchGameMarkets(eventId: Int) async throws -> GameMarketsResponse { throw Missing() }
        func fetchLineMovement(eventId: Int) async throws -> LineMovementResponse { throw Missing() }
    }

    private final class PageHandle: LiveStreamHandle, @unchecked Sendable {
        var isClosed = false
        var callbacks: [String: [@MainActor (String) -> Void]] = [:]
        func on(_ event: String, _ handler: @escaping @MainActor (String) -> Void) {
            callbacks[event, default: []].append(handler)
        }
        func close() { isClosed = true }
        func open() { for handler in callbacks["open"] ?? [] { handler("") } }
    }

    private final class Input: ObservableObject {
        @Published var sequence = 0
        @Published var status: LiveUpdateStatus = .live
        @Published var active = true
        let date = Date(timeIntervalSince1970: 1_790_600_000)
    }

    private struct Probe: View {
        @ObservedObject var input: Input
        var body: some View {
            VStack {
                Text("55% – 45%").font(.title)
                VisibleLivePriceStatusView(status: input.status, sequence: input.sequence,
                                          receivedAt: input.date.addingTimeInterval(Double(input.sequence)))
            }
            .frame(width: 300, height: 220).background(.white)
            .environment(\.scenePhase, input.active ? .active : .background)
            .environment(\.colorScheme, .light)
        }
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
        let url = FileManager.default.temporaryDirectory.appendingPathComponent("visible-live-\(name).png")
        try XCTUnwrap(image.pngData()).write(to: url)
        print("Visible live rendered evidence: \(url.path)")
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

    func testMountedSamePercentageReceiptIsVisibleThenStopsAndBackgroundCancels() throws {
        let input = Input()
        let host = hostForMeasurement(Probe(input: input), at: .large)
        host.view.frame = CGRect(x: 0, y: 0, width: 300, height: 220)
        let window = UIWindow(frame: host.view.frame); window.rootViewController = host; window.isHidden = false
        defer { window.isHidden = true }
        settle(host, 0.15)
        let initial = try green(shot(host, "initial"))
        input.sequence = 1; settle(host, 0.05)
        let received = try shot(host, "same55-received")
        XCTAssertGreaterThan(try green(received), initial + 0.2)
        XCTAssertTrue(try text(received).contains("55%"), "receipt must not fabricate a changed percentage")
        settle(host, 1.5)
        XCTAssertLessThan(try green(shot(host, "settled")), initial + 0.15)
        input.sequence = 2; settle(host, 0.05)
        input.active = false; settle(host, 0.1)
        XCTAssertLessThan(try green(shot(host, "background")), initial + 0.15)
        input.active = true; settle(host, 0.1)
        XCTAssertLessThan(try green(shot(host, "foreground-no-replay")), initial + 0.15)
    }

    func testActualStatusLabelsRemainReadableAtPhoneAndAccessibilitySizes() throws {
        for (name, status, size) in [
            ("waiting-default", LiveUpdateStatus.awaitingUpdate, DynamicTypeSize.large),
            ("live-xxxl", .live, .xxxLarge),
            ("fallback-accessibility", .autoRefresh, .accessibility3),
            ("interrupted-accessibility", .interrupted, .accessibility3)
        ] {
            let view = VisibleLivePriceStatusView(status: status, sequence: 5,
                receivedAt: Date(timeIntervalSince1970: 1_790_600_000))
                .frame(width: 320).padding().background(.white)
                .environment(\.scenePhase, .active).environment(\.colorScheme, .light)
            let host = hostForMeasurement(view, at: size)
            host.view.frame = CGRect(x: 0, y: 0, width: 390, height: 280)
            let window = UIWindow(frame: host.view.frame); window.rootViewController = host; window.isHidden = false
            defer { window.isHidden = true }
            settle(host, 0.1)
            let recognized = try text(shot(host, name))
            XCTAssertTrue(recognized.contains(status.title), recognized)
            XCTAssertTrue(recognized.contains("Received"), recognized)
        }
    }

    func testActualEventPageShowsWaitingBesideProbabilityWithoutOpeningDisclosure() async throws {
        for (name, size) in [("page-390", DynamicTypeSize.large), ("page-390-xxxl", .xxxLarge)] {
            let client = try PageClient(), handle = PageHandle()
            let vm = EventDetailViewModel(eventId: 4242, client: client, makeStreamHandle: { _ in handle })
            await vm.load(); handle.open()
            let page = NavigationStack { EventDetailView(eventId: 4242, viewModel: vm) }
                .environmentObject(PinManager())
                .environment(\.scenePhase, .active).environment(\.colorScheme, .light)
            let host = hostForMeasurement(page, at: size)
            host.view.frame = CGRect(x: 0, y: 0, width: 390, height: 844)
            let window = UIWindow(frame: host.view.frame); window.rootViewController = host; window.isHidden = false
            defer { vm.stopRefresh(); window.isHidden = true }
            settle(host, 0.4)
            let recognized = try text(shot(host, name))
            XCTAssertTrue(recognized.contains("Win Probability"), recognized)
            XCTAssertTrue(recognized.contains("Waiting for update"), recognized)
            // #8320 v24: the receipt row left the hero; the exact time is on tap only.
            XCTAssertNil(recognized.range(of: "No live.*update yet", options: .regularExpression), recognized)
            // #10830 — read as the hero's adjacent pair. With Start Live Activity
            // moved under the chart, page-wide OCR reads the pixel-identical hero
            // as "55% - 45" (the crest circle beside it swallows the trailing %).
            XCTAssertNotNil(recognized.range(of: #"55%\s*[-–—]?\s*45%?"#, options: .regularExpression), recognized)
        }
    }
}
