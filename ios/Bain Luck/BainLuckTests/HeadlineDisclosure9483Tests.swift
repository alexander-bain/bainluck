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

    // MARK: #11285 — every status behind the adopted headline's info control

    /// Alex, build 65: "Waiting for updates" beside the top-right control
    /// squeezed the headline. In the adopted header no state prints words
    /// there; each is said in the details and the control's label instead.
    func testTheAdoptedControlPrintsNoStatusWordsInAnyState() {
        for status in [LiveUpdateStatus.hidden, .live, .awaitingUpdate, .autoRefresh, .interrupted] {
            let shown = CompactEventPriceStatus(status: status, isDisclosure: true, statusInDetails: true)
            XCTAssertTrue(shown.isVisible, "\(status): the info control is always reachable")
            XCTAssertFalse(shown.showsTitle, "\(status): status words beside the control")
            XCTAssertFalse(shown.showsTrailingInfo, "\(status): one glyph slot only")
        }
    }

    /// An interruption keeps a warning mark (and its amber tint) without the
    /// words; every other state is the plain info mark.
    func testAnInterruptionStillShowsAWarningMarkWithoutWords() {
        XCTAssertEqual(CompactEventPriceStatus(status: .interrupted, isDisclosure: true, statusInDetails: true).glyph,
                       "exclamationmark.triangle.fill")
        for status in [LiveUpdateStatus.hidden, .live, .awaitingUpdate, .autoRefresh] {
            XCTAssertEqual(CompactEventPriceStatus(status: status, isDisclosure: true, statusInDetails: true).glyph,
                           "info.circle", "\(status)")
        }
    }

    /// `statusInDetails` means nothing outside the disclosure: a bare cue
    /// keeps its words and glyph.
    func testStatusInDetailsDoesNotReachANonDisclosureCue() {
        for status in [LiveUpdateStatus.live, .awaitingUpdate, .autoRefresh, .interrupted] {
            let bare = CompactEventPriceStatus(status: status, statusInDetails: true)
            XCTAssertTrue(bare.showsTitle, "\(status)")
            XCTAssertEqual(bare.glyph, CompactEventPriceStatus(status: status).glyph, "\(status)")
        }
    }

    /// The details still say every state: the popover heads with the status
    /// title and VoiceOver hears the delivery sentence.
    func testEveryStateIsStillSaidInTheDetailsAndToVoiceOver() {
        for status in [LiveUpdateStatus.live, .awaitingUpdate, .autoRefresh, .interrupted] {
            XCTAssertFalse(status.title.isEmpty, "\(status): the popover's heading")
            XCTAssertFalse(LivePriceReceiptCue.accessibilityText(status: status, receivedAt: nil).isEmpty,
                           "\(status): the control's spoken status")
        }
    }

    @MainActor
    private func renderAdopted(_ status: LiveUpdateStatus, at size: DynamicTypeSize) throws -> (UIImage, CGSize) {
        let renderer = rendererForMeasurement(
            CompactEventPriceStatusView(status: status, sequence: 0, receivedAt: nil,
                                        isDisclosure: true, statusInDetails: true)
                .frame(maxWidth: EventDetailView.heroVerdictWidth(at: size), minHeight: 44)
                .frame(minWidth: 44)
                .fixedSize()
                .background(Color.white)
                .environment(\.colorScheme, .light),
            at: size)
        renderer.scale = 3
        let image = try XCTUnwrap(renderer.uiImage, "\(status) \(size) did not render")
        return (image, image.size)
    }

    @MainActor
    func testTheAdoptedControlRendersOnlyItsMarkInEveryStateAndSize() throws {
        for status in [LiveUpdateStatus.awaitingUpdate, .autoRefresh, .interrupted, .live] {
            for size in [DynamicTypeSize.large, .xxxLarge, .accessibility3] {
                let (image, fitted) = try renderAdopted(status, at: size)
                let text = try recognizedText(image)
                XCTAssertFalse(text.localizedCaseInsensitiveContains("update"),
                               "\(status) \(size): status words printed beside the control: \(text)")
                XCTAssertFalse(text.localizedCaseInsensitiveContains("refresh"), "\(status) \(size): \(text)")
                XCTAssertGreaterThan(try ink(image), 0.002, "\(status) \(size): no mark was drawn")
                XCTAssertGreaterThanOrEqual(fitted.height, 44, "\(status) \(size): the 44pt target")
                XCTAssertGreaterThanOrEqual(fitted.width, 44, "\(status) \(size): the 44pt target")
                // A mark, not a sentence: the old "Waiting for update ⓘ" took
                // the whole 150pt slot.
                XCTAssertLessThan(fitted.width, 80, "\(status) \(size): the control still takes headline width")
            }
        }
    }

    func testTheAdoptedHeaderMountsItsControlWithEveryStatusInDetails() throws {
        let text = try page()
        let start = try XCTUnwrap(text.range(of: "private func nflPairedDetails(_ event: EventDetail) -> some View {"))
        let body = String(text[start.upperBound...].prefix(600))
        XCTAssertTrue(body.contains("statusInDetails: true)"),
                      "the adopted header's control prints status words beside the headline again")
    }

    // MARK: Phase label

    /// A quote one minute older than the instant it is read at.
    private func fresh(_ now: Date) -> Date { now.addingTimeInterval(-60) }

    func testALiveQuoteIsTheCurrentChance() {
        let now = kickoff.addingTimeInterval(3600)
        XCTAssertEqual(EventHeadlinePhase9483.resolve(
            status: "live", commenceTime: kickoff, isOpeningLine: false,
            observedAt: fresh(now), now: now), .current)
    }

    func testAQuoteBeforeTheOffIsTheCurrentChance() {
        let now = kickoff.addingTimeInterval(-3600)
        XCTAssertEqual(EventHeadlinePhase9483.resolve(
            status: "scheduled", commenceTime: kickoff, isOpeningLine: false,
            observedAt: fresh(now), now: now), .current)
    }

    func testAStartedGameThatIsNotLiveIsOnlyTheLastRecordedChance() {
        let now = kickoff.addingTimeInterval(600)
        for status in ["suspended", "scheduled", "delayed", nil] {
            XCTAssertEqual(EventHeadlinePhase9483.resolve(
                status: status, commenceTime: kickoff, isOpeningLine: false,
                observedAt: fresh(now), now: now), .lastRecorded, "\(status ?? "nil")")
        }
        // No clock at all fails toward "last recorded", never "current".
        XCTAssertEqual(EventHeadlinePhase9483.resolve(
            status: "scheduled", commenceTime: nil, isOpeningLine: false,
            observedAt: fresh(Date())), .lastRecorded)
    }

    func testAnInterruptedPairIsOnlyTheLastRecordedChance() {
        // The status line beside it says "Update interrupted"; the subject
        // must not call the same pair current.
        let before = kickoff.addingTimeInterval(-60)
        for status in ["live", "scheduled"] {
            XCTAssertEqual(EventHeadlinePhase9483.resolve(
                status: status, commenceTime: kickoff, isOpeningLine: false,
                observedAt: fresh(before), deliveryInterrupted: true, now: before),
                .lastRecorded, status)
        }
        // Control: the same live pair, delivery not interrupted, is current.
        let during = kickoff.addingTimeInterval(600)
        XCTAssertEqual(EventHeadlinePhase9483.resolve(
            status: "live", commenceTime: kickoff, isOpeningLine: false,
            observedAt: fresh(during), deliveryInterrupted: false, now: during), .current)
        // A final keeps no phase label whatever the delivery state.
        let after = kickoff.addingTimeInterval(9000)
        XCTAssertNil(EventHeadlinePhase9483.resolve(
            status: "completed", commenceTime: kickoff, isOpeningLine: false,
            observedAt: fresh(after), deliveryInterrupted: true, now: after))
    }

    // MARK: The quote's own clock (native review of 5f542c7b96, F1)

    func testAnAgedLiveQuoteIsOnlyTheLastRecordedChance() {
        // The acceptance-pack replays: PHI–JAX live at ~26 h, SA–PHX at ~36 h.
        let now = kickoff.addingTimeInterval(3600)
        for age: TimeInterval in [26 * 3600, 36 * 3600] {
            XCTAssertEqual(EventHeadlinePhase9483.resolve(
                status: "live", commenceTime: kickoff, isOpeningLine: false,
                observedAt: now.addingTimeInterval(-age), now: now),
                .lastRecorded, "live quote \(age / 3600)h old")
        }
    }

    func testAnAgedPregameQuoteIsOnlyTheLastRecordedChance() {
        // The acceptance-pack replay: BUF–LAR pregame at ~11.5 h.
        let now = kickoff.addingTimeInterval(-3600)
        XCTAssertEqual(EventHeadlinePhase9483.resolve(
            status: "scheduled", commenceTime: kickoff, isOpeningLine: false,
            observedAt: now.addingTimeInterval(-11.5 * 3600), now: now), .lastRecorded)
    }

    func testAPairWithNoQuoteClockIsOnlyTheLastRecordedChance() {
        for (status, now) in [("live", kickoff.addingTimeInterval(600)),
                              ("scheduled", kickoff.addingTimeInterval(-3600))] {
            XCTAssertEqual(EventHeadlinePhase9483.resolve(
                status: status, commenceTime: kickoff, isOpeningLine: false,
                observedAt: nil, now: now), .lastRecorded, status)
        }
    }

    func testTheStaleBoundIsTheLiveSourceBoundInclusive() {
        // Production 14780558 read 0.4 min old: current. The bound is
        // `SourceAge.liveStaleAfter` with `isStale`'s strict `>`, so exactly
        // 30 minutes is still current and one second past it is not.
        let bound = SourceAge.liveStaleAfter
        XCTAssertEqual(bound, 30 * 60)
        for (status, now) in [("live", kickoff.addingTimeInterval(3600)),
                              ("scheduled", kickoff.addingTimeInterval(-3600))] {
            XCTAssertEqual(EventHeadlinePhase9483.resolve(
                status: status, commenceTime: kickoff, isOpeningLine: false,
                observedAt: now.addingTimeInterval(-24), now: now), .current, "\(status) 0.4 min")
            XCTAssertEqual(EventHeadlinePhase9483.resolve(
                status: status, commenceTime: kickoff, isOpeningLine: false,
                observedAt: now.addingTimeInterval(-bound), now: now), .current, "\(status) at bound")
            XCTAssertEqual(EventHeadlinePhase9483.resolve(
                status: status, commenceTime: kickoff, isOpeningLine: false,
                observedAt: now.addingTimeInterval(-bound - 1), now: now), .lastRecorded, "\(status) past bound")
        }
    }

    func testAnOpeningLineOrAFinalGetsNoSecondLabel() {
        XCTAssertNil(EventHeadlinePhase9483.resolve(
            status: "scheduled", commenceTime: kickoff, isOpeningLine: true,
            observedAt: nil, now: kickoff.addingTimeInterval(-3600)))
        XCTAssertNil(EventHeadlinePhase9483.resolve(
            status: "completed", commenceTime: kickoff, isOpeningLine: false,
            observedAt: nil, now: kickoff.addingTimeInterval(9000)))
        XCTAssertFalse(EventHeadlinePhase9483.applies(status: "scheduled", isOpeningLine: true))
        XCTAssertFalse(EventHeadlinePhase9483.applies(status: "completed", isOpeningLine: false))
        XCTAssertTrue(EventHeadlinePhase9483.applies(status: "live", isOpeningLine: false))
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
        // #11285 — the signature gained `statusInDetails` (default false).
        let start = try XCTUnwrap(text.range(of: "private func probabilityDetails(confidenceTier: String?, statusInDetails: Bool = false) -> some View {"))
        let end = try XCTUnwrap(text.range(of: "// MARK: - Chart Header Bar", range: start.upperBound..<text.endIndex))
        let body = String(text[start.upperBound..<end.lowerBound])
        XCTAssertTrue(body.contains("isDisclosure: true"))
        XCTAssertTrue(body.contains("statusInDetails: statusInDetails)"),
                      "the control drops the caller's choice")
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

    func testThePageResolvesThePhaseOnTheQuotesOwnClockEachMinute() throws {
        let text = try page()
        let call = try XCTUnwrap(text.range(of: "EventHeadlinePhase9483.resolve("))
        let args = String(text[call.upperBound...].prefix(500))
        // #10090 — the displayed number's clock: committed, or a shown preview's own;
        // decision J: aged by a confirmation of it (`displayedProbabilityAgeClock`).
        XCTAssertTrue(args.contains("observedAt: vm.displayedProbabilityAgeClock(event)"),
                      "the phase must read the hero quote's own clock")
        // #9483 — on the page's display clock, which is the tick in production.
        XCTAssertTrue(args.contains("now: displayNow(tick.date)"), "the phase must age on the minute tick")
        let before = String(text[..<call.lowerBound].suffix(300))
        XCTAssertTrue(before.contains("TimelineView(.periodic(from: .now, by: 60)) { tick in"))
    }
}
