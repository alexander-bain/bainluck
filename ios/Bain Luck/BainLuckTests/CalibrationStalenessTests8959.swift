import SwiftUI
import XCTest
@testable import Bain_Luck

/// #8959: the phone's Accuracy screen says what the website says about how
/// current its numbers are.
///
/// On 2026-09-26 22:40Z production served the envelope below. The website read
/// "The curve is current. The data behind it is older. The curve was rebuilt on
/// schedule, but the market data behind it was last staged Sep 26, 12:31 AM
/// (14 hr ago). So it describes the market as of then, not now." The phone
/// decoded `cache` alone — `null` on the main tier — and showed no banner.
///
/// Web's words are pinned against this port by
/// `frontend/e2e/contract/calibrationStalenessCopy8959.contract.test.js`; this
/// file pins the assembled sentences and the state decision.
@MainActor
final class CalibrationStalenessTests8959: XCTestCase {

    /// The production freshness envelope, verbatim (`/api/calibration`, 22:40Z).
    private static let prodProducer = """
    {"task": "precompute_calibration_main", "interval_s": 3600, "stall_after_s": 14400, "age_s": 1326, "beats_missed": 0, "stalled": false}
    """
    private static let prodStaged = """
    {"measured": true, "staged_at": "2026-09-26T07:31:37+00:00", "staged_age_s": 54491, "units_banked": 249, "units_this_beat": 6, "units_drifted": 248, "units_drift_checkable": 248, "units_drift_unknown": 1, "units_drifted_as_of": "2026-09-26T07:31:37+00:00", "bank_advanced_this_beat": true, "frozen_over_drift": true, "rebuild_units_this_beat": 6, "rebuild_units_banked": 64, "rolling_restage": true}
    """
    private static let prodGeneratedAt = "2026-09-26T22:17:42.047671+00:00"

    private static func payload(
        availability: String? = "stale",
        generatedAt: String? = prodGeneratedAt,
        cache: String? = nil,
        producer: String? = prodProducer,
        staged: String? = prodStaged
    ) -> String {
        var lines: [String] = []
        if let availability { lines.append("\"availability\": \"\(availability)\",") }
        if let generatedAt { lines.append("\"generated_at\": \"\(generatedAt)\",") }
        if let cache { lines.append("\"cache\": \(cache),") }
        if let producer { lines.append("\"producer\": \(producer),") }
        if let staged { lines.append("\"staged\": \(staged),") }
        return """
        {
          \(lines.joined(separator: "\n  "))
          "population_version": "\(CalibrationRenderSmokeTests.renderableVersion)",
          "buckets": [
            {"bucket_idx": 2, "source": "kalshi", "category": "baseball_mlb", "price_moved": true, "n": 200, "winners": 60, "avg_prob": 0.25, "sum_prob": 50.0, "sum_sq_err": 44.0, "ci_lower": 0.21, "ci_upper": 0.31},
            {"bucket_idx": 5, "source": "polymarket", "category": "politics", "price_moved": false, "n": 100, "winners": 55, "avg_prob": 0.55, "sum_prob": 55.0, "sum_sq_err": 24.0, "ci_lower": 0.45, "ci_upper": 0.64}
          ],
          "total_markets": 12, "total_outcomes": 300, "total_winners": 115,
          "min_category_outcomes": 1000
        }
        """
    }

    private func model(_ json: String) throws -> CalibrationViewModel {
        let dec = JSONDecoder()
        dec.keyDecodingStrategy = .convertFromSnakeCase
        return CalibrationViewModel(preloaded: try dec.decode(CalibrationData.self, from: Data(json.utf8)))
    }

    /// The date part is formatted in the DEVICE's zone (as web's is), so the
    /// expected string is built through the same formatter rather than pinned —
    /// "Sep 26, 12:31 AM" would pass in PT and fail in CI's UTC.
    private func when(_ iso: String) throws -> String {
        try XCTUnwrap(CalibrationStaleness.bannerDate(iso))
    }

    // MARK: - The defect, on the production envelope

    func testTheProductionEnvelopeBannersTheDatedMarketDataAsTheWebsiteDoes() throws {
        let vm = try model(Self.payload())
        let notice = try XCTUnwrap(vm.stalenessNotice, "the phone showed nothing over 15-hour-old data")
        XCTAssertEqual(notice.kind, .frozenInputs)
        XCTAssertEqual(vm.staleBannerHeadline, "The curve is current. The data behind it is older.")
        XCTAssertEqual(
            vm.staleBannerDetail,
            "The curve was rebuilt on schedule, but the market data behind it was last staged "
                + "\(try when("2026-09-26T07:31:37+00:00")) (15 hr ago). "
                + "So it describes the market as of then, not now."
        )
        // It is the INPUTS that are dated, not the artifact: not a last-good copy.
        XCTAssertFalse(vm.isStale)
        // Freshness is a disclosure, never a refusal — the curve still renders.
        XCTAssertTrue(vm.hasRenderableCurve)
    }

    func testTheSameEnvelopeDeclaredFreshSaysNothing() throws {
        // The control: the staged block alone is not the trigger — the server's
        // refusal of `fresh` is. Web returns `null` here; so must the phone.
        let vm = try model(Self.payload(availability: "fresh"))
        XCTAssertNil(vm.stalenessNotice)
        XCTAssertNil(vm.staleBannerHeadline)
        XCTAssertNil(vm.staleBannerDetail)
    }

    func testAnOlderPayloadWithNoAvailabilityKeepsThePreviousBehaviour() throws {
        // Absent is not `fresh` and not a problem: an older payload whose only
        // authority is `cache`. No cache ⇒ nothing to say.
        let vm = try model(Self.payload(availability: nil))
        XCTAssertNil(vm.stalenessNotice)
    }

    // MARK: - #4113: "the curve is current" needs the proof

    func testAMissedBeatWithholdsTheCurrencyClaim() throws {
        let vm = try model(Self.payload(
            producer: #"{"stalled": false, "beats_missed": 1, "age_s": 4000}"#))
        XCTAssertEqual(vm.staleBannerHeadline,
                       "We can't confirm the curve is current. The data behind it is older.")
        let detail = try XCTUnwrap(vm.staleBannerDetail)
        XCTAssertTrue(detail.hasPrefix("The market data behind it was last staged "), detail)
        XCTAssertFalse(detail.contains("rebuilt on schedule"), detail)
    }

    func testAMissingProducerBlockIsNotProofEither() throws {
        let vm = try model(Self.payload(producer: nil))
        XCTAssertEqual(vm.staleBannerHeadline,
                       "We can't confirm the curve is current. The data behind it is older.")
    }

    // MARK: - undisclosed

    func testAnEmptiedBankSaysSoAndStatesTheEarnedCadence() throws {
        // #5185 + the cadence control: the beat is proven landing, so "The curve
        // rebuilds hourly." is true here and must be said — deleting the sentence
        // is not a fix for it once being wrong.
        let vm = try model(Self.payload(
            staged: #"{"measured": false, "reason": "served_bank_empty"}"#))
        XCTAssertEqual(vm.stalenessNotice?.kind, .undisclosed)
        XCTAssertEqual(vm.staleBannerHeadline, "We can't confirm how current the data behind this is.")
        XCTAssertEqual(
            vm.staleBannerDetail,
            "These numbers were built \(try when(Self.prodGeneratedAt)) (22 min ago). "
                + "The curve rebuilds hourly. "
                + "The market data behind it is being gathered again from scratch, so it has no date to show. "
                + "We’d rather say so than call these numbers current."
        )
    }

    func testAnUnreadableBankWithNoDateAnywhereClaimsNothingItCannotSupport() throws {
        let vm = try model(Self.payload(generatedAt: nil, producer: nil, staged: nil))
        XCTAssertEqual(vm.staleBannerHeadline, "We can't confirm how current this is.")
        XCTAssertEqual(
            vm.staleBannerDetail,
            "We couldn’t read when the market data behind it was last staged. "
                + "We’d rather say so than call these numbers current."
        )
    }

    func testAWronglyTypedStagedFieldDoesNotEraseTheBlocksReason() throws {
        // Web reads `staged` field by field; a synthesized decode would throw the
        // whole block away on one bad `measured` and lose the #5185 reason.
        let vm = try model(Self.payload(
            staged: #"{"measured": "yes", "reason": "served_bank_empty"}"#))
        XCTAssertEqual(vm.stalenessNotice?.kind, .undisclosed)
        XCTAssertEqual(vm.stalenessNotice?.stagedReason, "served_bank_empty")
    }

    func testAStalledProducerIsDescribedWithTheCountFormattedAsWebDoes() throws {
        let vm = try model(Self.payload(
            producer: #"{"stalled": true, "beats_missed": 1130, "age_s": 4070000}"#,
            staged: #"{"measured": false}"#))
        let detail = try XCTUnwrap(vm.staleBannerDetail)
        XCTAssertTrue(detail.contains("(47 days ago). 1,130 hourly rebuilds have come and gone without a new snapshot. "), detail)
    }

    // MARK: - Precedence

    func testADatedLastGoodOutranksTheFrozenInputs() throws {
        let vm = try model(Self.payload(
            cache: #"{"status": "stale", "reason": "main_key_absent", "generated_at": "2026-09-25T00:00:00+00:00", "age_s": 90000}"#,
            producer: nil))
        XCTAssertEqual(vm.stalenessNotice?.kind, .lastGood)
        XCTAssertTrue(vm.isStale)
        XCTAssertEqual(vm.staleBannerHeadline, "Showing the last complete snapshot.")
        XCTAssertEqual(
            vm.staleBannerDetail,
            "These numbers were built \(try when("2026-09-25T00:00:00+00:00")) (25 hr ago) "
                + "and are not being refreshed right now."
        )
    }

    // MARK: - The banner is on the rendered surface

    func testTheBannerRendersAtTopOfThePhoneSurface() throws {
        let vm = try model(Self.payload())
        let surface = CalibrationSurfaceView(viewModel: vm, scrolls: false).frame(width: 390)
        let renderer = rendererForMeasurement(surface)
        renderer.scale = 2
        let image = try XCTUnwrap(renderer.uiImage, "surface produced no raster")
        let png = try XCTUnwrap(image.pngData())
        let url = FileManager.default.temporaryDirectory.appendingPathComponent("8959-staleness-390.png")
        try? png.write(to: url)
        print("#8959 render artifact: \(url.path) (\(image.size.width)x\(image.size.height)pt)")
        XCTAssertLessThanOrEqual(image.size.width, 390.5)
    }
}
