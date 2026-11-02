import SwiftUI
import UIKit
import Vision
import XCTest
@testable import Bain_Luck

/// #10090 (Alex 69, after installing build 95) — "We probably don't need ...
/// the 'i' with the circle around it, b/c clicking the ekg can just bring up
/// the same pop-up that the i previously brought up."
///
/// Beside a drawn EKG the hero's info control draws no (i): routine delivery
/// draws nothing, a state worth seeing keeps its words and glyph (decision 67,
/// "status line only when wrong"), and a page without the EKG keeps its (i)
/// so the details stay reachable.
final class TheEkgReplacesTheInfoMark10090Tests: XCTestCase {

    // MARK: Presentation

    func testBesideADrawnEkgRoutineDeliveryDrawsNoInfoMark() {
        for statusInDetails in [false, true] {
            let shown = CompactEventPriceStatus(status: .live, isDisclosure: true,
                                                statusInDetails: statusInDetails, ekgDrawn: true)
            XCTAssertNotEqual(shown.glyph, "info.circle", "statusInDetails=\(statusInDetails)")
            XCTAssertFalse(shown.showsTrailingInfo, "statusInDetails=\(statusInDetails)")
            XCTAssertFalse(shown.isVisible, "statusInDetails=\(statusInDetails): the control draws nothing")
            XCTAssertTrue(shown.collapsesBesideEkg, "statusInDetails=\(statusInDetails)")
        }
        // #11285 — the adopted header says waiting in its details only; with the
        // EKG there is nothing left to draw for it either.
        let waiting = CompactEventPriceStatus(status: .awaitingUpdate, isDisclosure: true,
                                              statusInDetails: true, ekgDrawn: true)
        XCTAssertFalse(waiting.isVisible)
        XCTAssertNotEqual(waiting.glyph, "info.circle")
    }

    func testBesideADrawnEkgAWarningKeepsItsGlyphAndWords() {
        let headerWarning = CompactEventPriceStatus(status: .interrupted, isDisclosure: true,
                                                    statusInDetails: true, ekgDrawn: true)
        XCTAssertTrue(headerWarning.isVisible)
        XCTAssertFalse(headerWarning.collapsesBesideEkg)
        XCTAssertEqual(headerWarning.glyph, "exclamationmark.triangle.fill")

        for status in [LiveUpdateStatus.awaitingUpdate, .autoRefresh, .interrupted] {
            let shown = CompactEventPriceStatus(status: status, isDisclosure: true, ekgDrawn: true)
            XCTAssertTrue(shown.isVisible, "\(status)")
            XCTAssertFalse(shown.collapsesBesideEkg, "\(status)")
            XCTAssertTrue(shown.showsTitle, "\(status): its words stay beside the price")
            XCTAssertFalse(shown.showsTrailingInfo, "\(status): no (i) after the words")
            XCTAssertEqual(shown.glyph, CompactEventPriceStatus(status: status).glyph,
                           "\(status): the state's own glyph leads instead")
            XCTAssertNotEqual(shown.glyph, "info.circle", "\(status)")
        }
    }

    func testWithoutAnEkgTheInfoMarkStays() {
        for statusInDetails in [false, true] {
            let shown = CompactEventPriceStatus(status: .live, isDisclosure: true,
                                                statusInDetails: statusInDetails, ekgDrawn: false)
            XCTAssertTrue(shown.isVisible)
            XCTAssertFalse(shown.collapsesBesideEkg)
            XCTAssertEqual(shown.glyph, "info.circle", "statusInDetails=\(statusInDetails)")
        }
        let waiting = CompactEventPriceStatus(status: .awaitingUpdate, isDisclosure: true)
        XCTAssertTrue(waiting.showsTrailingInfo, "control: the words still carry the trailing (i)")
        // Non-disclosure callers never read the flag.
        let other = CompactEventPriceStatus(status: .live, ekgDrawn: true)
        XCTAssertTrue(other.isVisible)
        XCTAssertFalse(other.collapsesBesideEkg)
        XCTAssertEqual(other.glyph, "circle.fill")
    }

    func testTheHeartbeatIsTheReceiptSoTheCheckDoesNotDrawBesideIt() {
        XCTAssertTrue(CompactEventPriceStatus.acknowledgesReceipts(status: .live, sceneActive: true),
                      "control: without the EKG a receipt is acknowledged")
        XCTAssertFalse(CompactEventPriceStatus.acknowledgesReceipts(status: .live, sceneActive: true,
                                                                    ekgDrawn: true))
        XCTAssertFalse(CompactEventPriceStatus.acknowledgesReceipts(status: .awaitingUpdate, sceneActive: true,
                                                                    ekgDrawn: true))
    }

    // MARK: Rendered

    @MainActor
    private func render(_ status: LiveUpdateStatus, statusInDetails: Bool = false,
                        ekgDrawn: Bool) throws -> UIImage {
        let renderer = rendererForMeasurement(
            CompactEventPriceStatusView(status: status, sequence: 0, receivedAt: nil, isDisclosure: true,
                                        statusInDetails: statusInDetails, ekgDrawn: ekgDrawn)
                .frame(width: 150, height: 44)
                .background(Color.white)
                .environment(\.colorScheme, .light),
            at: .large)
        renderer.scale = 3
        return try XCTUnwrap(renderer.uiImage, "\(status) ekgDrawn=\(ekgDrawn) did not render")
    }

    /// Pixels that are visibly not white.
    private func inkPixels(_ image: UIImage) throws -> Int {
        let cg = try XCTUnwrap(image.cgImage)
        var bytes = [UInt8](repeating: 0, count: cg.width * cg.height * 4)
        return try bytes.withUnsafeMutableBytes { buffer in
            let ctx = try XCTUnwrap(CGContext(data: buffer.baseAddress, width: cg.width, height: cg.height,
                bitsPerComponent: 8, bytesPerRow: cg.width * 4, space: CGColorSpaceCreateDeviceRGB(),
                bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue))
            ctx.draw(cg, in: CGRect(x: 0, y: 0, width: cg.width, height: cg.height))
            let values = buffer.bindMemory(to: UInt8.self)
            var dark = 0
            for i in stride(from: 0, to: values.count, by: 4)
            where Int(values[i]) + Int(values[i + 1]) + Int(values[i + 2]) < 690 { dark += 1 }
            return dark
        }
    }

    private func recognizedText(_ image: UIImage) throws -> String {
        let request = VNRecognizeTextRequest(); request.recognitionLevel = .accurate
        try VNImageRequestHandler(cgImage: XCTUnwrap(image.cgImage)).perform([request])
        return (request.results ?? []).compactMap { $0.topCandidates(1).first?.string }.joined(separator: " ")
    }

    @MainActor
    func testALiveHeroBesideTheEkgRendersNoMarkAndWithoutItRendersTheInfoMark() throws {
        for statusInDetails in [false, true] {
            XCTAssertEqual(try inkPixels(render(.live, statusInDetails: statusInDetails, ekgDrawn: true)), 0,
                           "statusInDetails=\(statusInDetails): a mark drew beside the EKG")
            XCTAssertGreaterThan(try inkPixels(render(.live, statusInDetails: statusInDetails, ekgDrawn: false)), 30,
                                 "control, statusInDetails=\(statusInDetails): the (i) draws without the EKG")
        }
    }

    @MainActor
    func testAnInterruptionBesideTheEkgStillRendersItsWords() throws {
        let image = try render(.interrupted, ekgDrawn: true)
        XCTAssertTrue(try recognizedText(image).localizedCaseInsensitiveContains("interrupted"))
        XCTAssertGreaterThan(try inkPixels(render(.interrupted, statusInDetails: true, ekgDrawn: true)), 30,
                             "the header's warning glyph")
    }

    // MARK: Mounted (source scans; comments stripped first)

    private func page() throws -> String {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent().deletingLastPathComponent()
            .appendingPathComponent("Bain Luck/Views/EventDetailView.swift")
        return try String(contentsOf: url, encoding: .utf8)
            .split(separator: "\n", omittingEmptySubsequences: false)
            .map { line -> String in
                guard let slashes = line.range(of: "//") else { return String(line) }
                return String(line[line.startIndex..<slashes.lowerBound])
            }
            .joined(separator: "\n")
            .filter { !$0.isWhitespace }
    }

    private func span(_ text: String, from: String, to: String) throws -> String {
        let lo = try XCTUnwrap(text.range(of: from), "missing: \(from)")
        let hi = try XCTUnwrap(text.range(of: to, range: lo.upperBound..<text.endIndex), "missing: \(to)")
        return String(text[lo.upperBound..<hi.lowerBound])
    }

    func testTheControlAndTheEkgReadOneAnswerAndTheEkgCarriesTheControlsHint() throws {
        let text = try page()
        let ekg = try span(text, from: "privatefuncheroEkg(_event:EventDetail,isOpeningLine:Bool)->someView{",
                           to: "privatefuncprobabilityDetails(")
        XCTAssertTrue(ekg.hasPrefix("ifheroEkgDrawn(event,isOpeningLine:isOpeningLine){"))
        XCTAssertTrue(ekg.contains("Button{showProbabilityDetails=true}"), "the EKG opens the one popover")
        XCTAssertTrue(ekg.contains(".accessibilityHint(Self.probabilityDetailsHint(forecastShown:revealForecast11296!=nil))"),
                      "the EKG says what its tap opens, as the (i) did")
        XCTAssertFalse(ekg.contains(".accessibilityLabel("), "the heartbeat keeps its own label (\"Markets reporting\")")

        let control = try span(text, from: "privatefuncprobabilityDetails(", to: "privatefuncchartHeaderBar(")
        XCTAssertTrue(control.contains("statusInDetails:statusInDetails,ekgDrawn:ekgDrawn)"),
                      "the control drops the page's EKG answer")
        let collapse = "detailsCollapseBesideEkg(statusInDetails:statusInDetails,ekgDrawn:ekgDrawn)"
        XCTAssertTrue(control.contains(".frame(height:\(collapse)?0:nil)"),
                      "the row collapses; the width the stacked caption overlay is proposed stays")
        XCTAssertFalse(control.contains(".frame(width:\(collapse)"))
        XCTAssertTrue(control.contains(".allowsHitTesting(!\(collapse))"))
        XCTAssertTrue(control.contains(".accessibilityHidden(\(collapse))"))
        // The collapse sits before the popover, so the popover stays anchored on it.
        let popover = try XCTUnwrap(control.range(of: ".popover(isPresented:$showProbabilityDetails"))
        XCTAssertNotNil(control.range(of: ".accessibilityHidden(\(collapse))", range: control.startIndex..<popover.lowerBound))

        XCTAssertTrue(text.contains("probabilityDetails(confidenceTier:confidenceTier,"
            + "ekgDrawn:heroEkgDrawn(event,isOpeningLine:shown.isOpeningLine))"), "the legacy hero's control")
        XCTAssertTrue(text.contains("statusInDetails:true,ekgDrawn:heroEkgDrawn(event,isOpeningLine:false))"),
                      "the paired page's control")
        XCTAssertTrue(text.contains("ifpriceStreamingEligible{probabilityDetails(confidenceTier:nil)}"),
                      "an unpriced 'vs' hero draws no EKG, so it keeps its (i)")
    }
}
