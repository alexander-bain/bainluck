import SwiftUI
import UIKit
import Vision
import XCTest
@testable import Bain_Luck

/// #9483 — the first playable event page: routine headline metadata behind
/// the info control, uncertainty beside the price, and a subject for the pair.
final class HeadlineDisclosure9483Tests: XCTestCase {

    private let kickoff = Date(timeIntervalSince1970: 1_800_000_000)

    // MARK: Disclosure presentation

    func testRoutineDeliveryCollapsesToTheInfoMark() {
        for status in [LiveUpdateStatus.live, .hidden] {
            let shown = CompactEventPriceStatus(status: status, isDisclosure: true)
            XCTAssertTrue(shown.isVisible, "\(status): the info control is always reachable")
            XCTAssertFalse(shown.showsTitle, "\(status): routine status moves into details")
            XCTAssertFalse(shown.showsTrailingInfo)
            XCTAssertEqual(shown.glyph, "info.circle")
        }
    }

    func testUncertaintyStaysVisibleBesideThePrice() {
        for status in [LiveUpdateStatus.awaitingUpdate, .autoRefresh, .interrupted] {
            let shown = CompactEventPriceStatus(status: status, isDisclosure: true)
            XCTAssertTrue(shown.showsTitle, "\(status) must stay labelled in the hero")
            XCTAssertTrue(shown.showsTrailingInfo, "\(status) still offers the details")
            XCTAssertEqual(shown.title, status.title)
        }
    }

    func testEveryOtherCallerKeepsItsOriginalPresentation() {
        for status in [LiveUpdateStatus.hidden, .live, .awaitingUpdate, .autoRefresh, .interrupted] {
            let shown = CompactEventPriceStatus(status: status)
            XCTAssertEqual(shown.isVisible, status != .hidden)
            XCTAssertTrue(shown.showsTitle)
            XCTAssertFalse(shown.showsTrailingInfo)
            XCTAssertNotEqual(shown.glyph, "info.circle")
        }
    }

    func testReceiptGatesAreUnchangedByTheDisclosure() {
        XCTAssertTrue(CompactEventPriceStatus.acknowledgesReceipts(status: .live, sceneActive: true))
        XCTAssertFalse(CompactEventPriceStatus.acknowledgesReceipts(status: .hidden, sceneActive: true))
        XCTAssertFalse(CompactEventPriceStatus.acknowledgesReceipts(status: .interrupted, sceneActive: true))
        XCTAssertFalse(CompactEventPriceStatus.acknowledgesReceipts(status: .live, sceneActive: false))
    }

    // MARK: Rendered info control (replaces the page OCR "Win Probability" line)

    /// The control as the hero mounts it: disclosure mode, in the hero's 150pt
    /// verdict slot below `.xxLarge`, full width above it. Rendered at 3x;
    /// returns the image and its size in points.
    @MainActor
    private func render(_ status: LiveUpdateStatus, at size: DynamicTypeSize,
                        width: CGFloat? = nil, bare: Bool = false) throws -> (UIImage, CGSize) {
        let slot = width ?? EventDetailView.heroVerdictWidth(at: size) ?? 358
        let renderer = rendererForMeasurement(
            CompactEventPriceStatusView(status: status, sequence: 0, receivedAt: nil, isDisclosure: true)
                .frame(maxWidth: slot, minHeight: bare ? nil : 44)
                .frame(minWidth: 44)
                .fixedSize(horizontal: false, vertical: true)
                .frame(width: slot)
                .background(Color.white)
                .environment(\.colorScheme, .light),
            at: size)
        renderer.scale = 3
        let image = try XCTUnwrap(renderer.uiImage, "\(status) \(size) did not render")
        return (image, image.size)
    }

    private func recognizedText(_ image: UIImage) throws -> String {
        let request = VNRecognizeTextRequest(); request.recognitionLevel = .accurate
        try VNImageRequestHandler(cgImage: XCTUnwrap(image.cgImage)).perform([request])
        return (request.results ?? []).compactMap { $0.topCandidates(1).first?.string }.joined(separator: " ")
    }

    /// Share of pixels that are visibly not white: the glyph's ink.
    private func ink(_ image: UIImage) throws -> Double {
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
            return Double(dark) / Double(cg.width * cg.height)
        }
    }

    @MainActor
    func testRoutineDeliveryRendersOnlyTheInfoMarkAtEverySize() throws {
        for size in [DynamicTypeSize.large, .xxxLarge, .accessibility3] {
            let (image, fitted) = try render(.live, at: size)
            let text = try recognizedText(image)
            XCTAssertFalse(text.localizedCaseInsensitiveContains(LiveUpdateStatus.live.title),
                           "\(size): routine status printed in the hero: \(text)")
            XCTAssertGreaterThan(try ink(image), 0.002, "\(size): no info mark was drawn")
            XCTAssertGreaterThanOrEqual(fitted.height, 44, "\(size): the 44pt target")
        }
    }

    @MainActor
    func testUncertaintyRendersItsWordsAndTheInfoMarkOnOneLineInTheHeroSlot() throws {
        for status in [LiveUpdateStatus.awaitingUpdate, .autoRefresh, .interrupted] {
            for size in [DynamicTypeSize.large, .xxxLarge, .accessibility3] {
                let (image, _) = try render(status, at: size)
                let text = try recognizedText(image)
                XCTAssertTrue(text.contains(status.title), "\(status) \(size): \(text)")
            }
            // At the default size the words and their one mark share ONE line
            // in the 150pt slot. Measured without the 44pt target floor, which
            // would hide a two-line wrap; a line is the caption font's own line
            // height plus the control's 2pt vertical padding each side.
            let (_, labelled) = try render(status, at: .large, width: EventDetailView.verdictSlotWidth, bare: true)
            let line = UIFont.preferredFont(
                forTextStyle: .caption1,
                compatibleWith: UITraitCollection(preferredContentSizeCategory: .large)).lineHeight + 4
            XCTAssertLessThan(labelled.height, line * 1.5,
                              "\(status) wraps in the hero slot (\(labelled.height)pt, one line is \(line)pt)")
        }
    }

    // MARK: Phase label

    func testALiveQuoteIsTheCurrentChance() {
        XCTAssertEqual(EventHeadlinePhase9483.resolve(
            status: "live", commenceTime: kickoff, isOpeningLine: false,
            now: kickoff.addingTimeInterval(3600)), .current)
    }

    func testAQuoteBeforeTheOffIsTheCurrentChance() {
        XCTAssertEqual(EventHeadlinePhase9483.resolve(
            status: "scheduled", commenceTime: kickoff, isOpeningLine: false,
            now: kickoff.addingTimeInterval(-3600)), .current)
    }

    func testAStartedGameThatIsNotLiveIsOnlyTheLastRecordedChance() {
        for status in ["suspended", "scheduled", "delayed", nil] {
            XCTAssertEqual(EventHeadlinePhase9483.resolve(
                status: status, commenceTime: kickoff, isOpeningLine: false,
                now: kickoff.addingTimeInterval(600)), .lastRecorded, "\(status ?? "nil")")
        }
        // No clock at all fails toward "last recorded", never "current".
        XCTAssertEqual(EventHeadlinePhase9483.resolve(
            status: "scheduled", commenceTime: nil, isOpeningLine: false), .lastRecorded)
    }

    func testAnInterruptedPairIsOnlyTheLastRecordedChance() {
        // The status line beside it says "Update interrupted"; the subject
        // must not call the same pair current.
        for status in ["live", "scheduled"] {
            XCTAssertEqual(EventHeadlinePhase9483.resolve(
                status: status, commenceTime: kickoff, isOpeningLine: false,
                deliveryInterrupted: true, now: kickoff.addingTimeInterval(-60)),
                .lastRecorded, status)
        }
        // Control: the same live pair, delivery not interrupted, is current.
        XCTAssertEqual(EventHeadlinePhase9483.resolve(
            status: "live", commenceTime: kickoff, isOpeningLine: false,
            deliveryInterrupted: false, now: kickoff.addingTimeInterval(600)), .current)
        // A final keeps no phase label whatever the delivery state.
        XCTAssertNil(EventHeadlinePhase9483.resolve(
            status: "completed", commenceTime: kickoff, isOpeningLine: false,
            deliveryInterrupted: true, now: kickoff.addingTimeInterval(9000)))
    }

    func testAnOpeningLineOrAFinalGetsNoSecondLabel() {
        XCTAssertNil(EventHeadlinePhase9483.resolve(
            status: "scheduled", commenceTime: kickoff, isOpeningLine: true,
            now: kickoff.addingTimeInterval(-3600)))
        XCTAssertNil(EventHeadlinePhase9483.resolve(
            status: "completed", commenceTime: kickoff, isOpeningLine: false,
            now: kickoff.addingTimeInterval(9000)))
    }

    func testTheLabelsNameTheirReading() {
        XCTAssertEqual(EventHeadlinePhase9483.current.label, "Current win chance")
        XCTAssertEqual(EventHeadlinePhase9483.lastRecorded.label, "Last recorded win chance")
    }

    func testNoBaselineWithoutAPregameReading() {
        XCTAssertNil(EventHeadlinePhase9483.baselineText(
            prematch: nil, opening: nil, sport: "americanfootball_nfl",
            awayTeam: "Baltimore Ravens", homeTeam: "Dallas Cowboys"))
    }

    // MARK: Page wiring

    private func page() throws -> String {
        let here = URL(fileURLWithPath: #filePath)
        let url = here.deletingLastPathComponent().deletingLastPathComponent()
            .appendingPathComponent("Bain Luck/Views/EventDetailView.swift")
        return try String(contentsOf: url, encoding: .utf8)
    }

    func testTheHeroMountsTheDisclosureModeAndNoRoutineLabel() throws {
        let text = try page()
        let start = try XCTUnwrap(text.range(of: "private func probabilityDetails(confidenceTier: String?) -> some View {"))
        let end = try XCTUnwrap(text.range(of: "// MARK: - Chart Header Bar", range: start.upperBound..<text.endIndex))
        let body = String(text[start.upperBound..<end.lowerBound])
        XCTAssertTrue(body.contains("isDisclosure: true"))
        XCTAssertFalse(body.contains("Text(\"Win Probability\")"), "the routine label is back in the hero")
        XCTAssertFalse(body.contains("SignalBarsView("), "confidence bars belong in the popover")
        XCTAssertTrue(body.contains("FreshnessRevealView(status: vm.liveUpdateStatus"),
                      "the popover still carries confidence and the exact receipt")
    }

    func testThePhaseLabelIsMountedOnceUnderThePair() throws {
        let text = try page()
        XCTAssertEqual(text.components(separatedBy: "EventHeadlinePhaseLabel9483(").count - 1, 1)
        XCTAssertEqual(text.components(separatedBy: "EventHeadlinePhase9483.resolve(").count - 1, 1)
    }
}
