import Combine
import XCTest
import SwiftUI
import UIKit
import Vision
@testable import Bain_Luck

final class LivePriceFeedbackPresentationTests: XCTestCase {
    func testRemountAndUnchangedActivityDoNotReplayFeedback() {
        XCTAssertFalse(LivePriceFeedbackPresentation.shouldShow(
            previousSequence: nil, sequence: 12, valueChanged: true, isEnabled: true))
        XCTAssertFalse(LivePriceFeedbackPresentation.shouldShow(
            previousSequence: 12, sequence: 12, valueChanged: true, isEnabled: true))
        XCTAssertFalse(LivePriceFeedbackPresentation.shouldShow(
            previousSequence: 12, sequence: 13, valueChanged: false, isEnabled: true))
    }

    func testOnlyEnabledNewDisplayedChangeEarnsFeedback() {
        XCTAssertTrue(LivePriceFeedbackPresentation.shouldShow(
            previousSequence: 12, sequence: 13, valueChanged: true, isEnabled: true))
        XCTAssertFalse(LivePriceFeedbackPresentation.shouldShow(
            previousSequence: 12, sequence: 13, valueChanged: true, isEnabled: false))
        XCTAssertFalse(LivePriceFeedbackPresentation.shouldShow(
            previousSequence: 12, sequence: 11, valueChanged: true, isEnabled: true))
    }

    func testLocalReceiptAgeDoesNotInventFreshnessOrNegativeTime() {
        let received = Date(timeIntervalSince1970: 1_800_000_000)
        func age(_ seconds: TimeInterval) -> String {
            LivePriceFeedbackPresentation.receiptAge(
                receivedAt: received, now: received.addingTimeInterval(seconds))
        }
        XCTAssertEqual(age(-5), "just now")
        XCTAssertEqual(age(0.5), "just now")
        XCTAssertEqual(age(1), "1 second ago")
        XCTAssertEqual(age(25), "25 seconds ago")
        XCTAssertEqual(age(61), "1 minute ago")
        XCTAssertEqual(age(121), "2 minutes ago")
        XCTAssertEqual(age(3601), "1 hour ago")
        XCTAssertEqual(age(86401), "1 day ago")
    }
}


@MainActor
extension LivePriceFeedbackPresentationTests {
    private final class FeedbackInput: ObservableObject {
        @Published var sequence = 0
    }

    private struct FeedbackProbe: View {
        @ObservedObject var input: FeedbackInput
        var body: some View {
            Text(input.sequence == 0 ? "60%" : "55%")
                .font(.system(size: 48, weight: .bold))
                .foregroundStyle(.black)
                .frame(width: 250, height: 90)
                .livePriceChangeFeedback(sequence: input.sequence, valueChanged: true, color: .green)
                .frame(width: 390, height: 120)
                .background(Color.white)
                .environment(\.scenePhase, .active)
                .environment(\.colorScheme, .light)
        }
    }

    private func settleView(_ host: UIViewController, seconds: TimeInterval) {
        let until = Date().addingTimeInterval(seconds)
        repeat {
            host.view.setNeedsLayout()
            host.view.layoutIfNeeded()
            RunLoop.current.run(until: min(until, Date().addingTimeInterval(0.01)))
        } while Date() < until
    }

    private func feedbackImage(_ host: UIViewController, name: String) throws -> UIImage {
        let image = UIGraphicsImageRenderer(bounds: host.view.bounds).image { _ in
            host.view.drawHierarchy(in: host.view.bounds, afterScreenUpdates: true)
        }
        let url = FileManager.default.temporaryDirectory.appendingPathComponent("candidate27-\(name).png")
        try XCTUnwrap(image.pngData()).write(to: url)
        print("Candidate27 rendered evidence: \(url.path)")
        return image
    }

    private func recognizedText(_ image: UIImage) throws -> String {
        let request = VNRecognizeTextRequest()
        request.recognitionLevel = .accurate
        try VNImageRequestHandler(cgImage: XCTUnwrap(image.cgImage)).perform([request])
        return (request.results ?? []).compactMap { $0.topCandidates(1).first?.string }.joined(separator: " ")
    }

    /// Average green excess on an explicit RGBA raster. Black text/white canvas
    /// contribute zero; only the actual green highlight earns the assertion.
    private func greenHighlight(_ image: UIImage) throws -> Double {
        let cg = try XCTUnwrap(image.cgImage)
        let width = cg.width, height = cg.height
        var rgba = [UInt8](repeating: 0, count: width * height * 4)
        let sum: Double = try rgba.withUnsafeMutableBytes { bytes in
            let context = try XCTUnwrap(CGContext(data: bytes.baseAddress, width: width, height: height,
                bitsPerComponent: 8, bytesPerRow: width * 4, space: CGColorSpaceCreateDeviceRGB(),
                bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue))
            context.draw(cg, in: CGRect(x: 0, y: 0, width: width, height: height))
            let values = bytes.bindMemory(to: UInt8.self)
            var total = 0.0
            for i in stride(from: 0, to: values.count, by: 4) {
                total += Double(max(0, Int(values[i + 1]) - max(Int(values[i]), Int(values[i + 2]))))
            }
            return total
        }
        return sum / Double(width * height)
    }

    func testActual390PointFreshnessRevealNamesLocalReceiptAndConfidence() throws {
        let reveal = FreshnessRevealView(status: .live,
            lastReceivedAt: Date().addingTimeInterval(-25), confidenceTier: "high")
            .frame(width: 390).background(Color.white)
            .environment(\.scenePhase, .active).environment(\.colorScheme, .light)
        let host = hostForMeasurement(reveal, at: .large)
        host.view.frame = CGRect(x: 0, y: 0, width: 390, height: 420)
        let window = UIWindow(frame: host.view.frame)
        window.rootViewController = host
        window.isHidden = false
        defer { window.isHidden = true }
        settleView(host, seconds: 0.15)
        let text = try recognizedText(feedbackImage(host, name: "freshness-390"))
        XCTAssertTrue(text.contains("Last price update received"), text)
        XCTAssertTrue(text.contains("Received on this device"), text)
        XCTAssertTrue(text.contains("High confidence"), text)
        XCTAssertFalse(text.contains("published"), "local receipt must never be called source publication: \(text)")
    }

    func testActualNumericHighlightAppearsThenClearsInCurrentAccessibilityEnvironment() throws {
        // Uses the real environment; rendered Reduce Motion coverage remains unpaid.
        do {
            let input = FeedbackInput()
            let host = hostForMeasurement(FeedbackProbe(input: input), at: .large)
            host.view.frame = CGRect(x: 0, y: 0, width: 390, height: 120)
            let window = UIWindow(frame: host.view.frame)
            window.rootViewController = host
            window.isHidden = false
            defer { window.isHidden = true }
            settleView(host, seconds: 0.15)
            let baseline = try greenHighlight(feedbackImage(host, name: "motion-default-initial"))
            XCTAssertLessThan(baseline, 0.1, "initial appearance must not flash")
            input.sequence = 1
            settleView(host, seconds: 0.05)
            let highlighted = try feedbackImage(host, name: "motion-default-highlight")
            let strength = try greenHighlight(highlighted)
            XCTAssertGreaterThan(strength, baseline + 0.2,
                                 "active accepted change did not visibly highlight")
            XCTAssertTrue(try recognizedText(highlighted).contains("55%"))
            settleView(host, seconds: 0.8)
            let settled = try greenHighlight(feedbackImage(host, name: "motion-default-settled"))
            XCTAssertLessThan(settled, baseline + 0.1, "highlight must clear without another update")
        }
    }
}
