import SwiftUI
import XCTest
@testable import Bain_Luck

/// L2-231 Item 2 — deterministic, network-free RENDER evidence for the native
/// calibration surface (the L2-225 pattern).
///
/// The states this queue is about are states of the SERVER, not of the app: a
/// dated last-good snapshot, a population-version mismatch, an empty payload. No
/// screenshot of today's app can prove any of them, because whether they appear
/// depends on what `/api/calibration` happens to be serving at the moment the
/// screenshot is taken. (While this was written, production was serving
/// `503 no_trustworthy_snapshot` — Q299's population bump to `q299` invalidated
/// every cached snapshot — so the ONE state a live capture could have shown was
/// the failure state.)
///
/// So the real `CalibrationView` is driven through `ImageRenderer` from fixed
/// payloads instead, and every branch is rasterised on every test run.
///
/// Assertions stay semantic, not pixel-exact: each state must produce a real
/// image, and states that must look different must actually differ. That catches
/// the regression that matters — a stale payload rendering identically to a
/// current one — without pinning fonts, colours, or copy. PNGs are written to the
/// temp dir and their paths logged so a run can be eyeballed afterwards.
@MainActor
final class CalibrationRenderSmokeTests: XCTestCase {

    private func decode(_ json: String) throws -> CalibrationData {
        let dec = JSONDecoder()
        dec.keyDecodingStrategy = .convertFromSnakeCase
        return try dec.decode(CalibrationData.self, from: Data(json.utf8))
    }

    private func render(_ json: String, name: String) throws -> Data {
        let vm = CalibrationViewModel(preloaded: try decode(json))
        // The trap this catches, found the hard way: the surface's `.task` used
        // to call `load()` unconditionally, and `load()` sets `loading = true`
        // before it awaits. Under ImageRenderer that fired, so EVERY fixture
        // rasterised the spinner — byte-identical images that looked like a
        // passing "nothing differs" run rather than the empty renders they were.
        XCTAssertFalse(vm.loading, "\(name): preloaded model must not be loading")
        print("L2-231 state [\(name)]: n=\(vm.cohortN) stale=\(vm.isStale) incompatible=\(vm.isIncompatible)")
        // `scrolls: false` only removes the ScrollView container (see the flag's
        // docs). Every branch, section and colour decision below it is the real
        // production body.
        let view = CalibrationSurfaceView(viewModel: vm, scrolls: false).frame(width: 390)
        let renderer = ImageRenderer(content: view)
        renderer.scale = 2
        let image = try XCTUnwrap(renderer.uiImage, "\(name) produced no raster")
        XCTAssertGreaterThan(image.size.width, 0, "\(name) rendered zero-width")
        XCTAssertGreaterThan(image.size.height, 0, "\(name) rendered zero-height")

        let png = try XCTUnwrap(image.pngData(), "\(name) produced no PNG data")
        let url = FileManager.default.temporaryDirectory
            .appendingPathComponent("l2231-calibration-\(name).png")
        try? png.write(to: url)
        print("L2-231 render artifact [\(name)]: \(url.path) (\(png.count) bytes)")
        return png
    }

    private static let buckets = """
    {"bucket_idx": 2, "source": "kalshi", "category": "baseball_mlb", "price_moved": true, "n": 200, "winners": 60, "avg_prob": 0.25, "sum_prob": 50.0, "sum_sq_err": 44.0, "ci_lower": 0.21, "ci_upper": 0.31},
    {"bucket_idx": 5, "source": "polymarket", "category": "politics", "price_moved": false, "n": 100, "winners": 55, "avg_prob": 0.55, "sum_prob": 55.0, "sum_sq_err": 24.0, "ci_lower": 0.45, "ci_upper": 0.64},
    {"bucket_idx": 2, "source": "odds_api", "category": "baseball_mlb", "price_moved": null, "n": 400, "winners": 100, "avg_prob": 0.25, "sum_prob": 100.0, "sum_sq_err": 80.0, "ci_lower": 0.21, "ci_upper": 0.29}
    """

    /// L2-232: taken from the build's own compatible set, never written as a
    /// literal.
    ///
    /// These fixtures used to hard-code `"q299"` as the HEALTHY version. When
    /// L2-232 corrected the compatible set to the population the server actually
    /// publishes, every "healthy" fixture silently became an INCOMPATIBLE one —
    /// so all three states rasterised to the same refusal screen and the three
    /// "these must differ" assertions went red at 47,296 identical bytes.
    ///
    /// That red was the suite doing its job, and it is worth stating why: a
    /// hard-coded version in a test fixture is the same fragility as a
    /// hard-coded version in a client, and it fails the same way — silently
    /// asserting the wrong thing until something forces it into the open.
    static let renderableVersion: String = CalibrationViewModel
        .compatiblePopulationVersions.sorted().first ?? "q267"

    /// Well-formed, and deliberately outside the compatible set.
    static let unrenderableVersion = "q400"

    private static func payload(
        cache: String? = nil,
        version: String? = CalibrationRenderSmokeTests.renderableVersion
    ) -> String {
        let cacheLine = cache.map { "\"cache\": \($0)," } ?? ""
        let versionLine = version.map { "\"population_version\": \"\($0)\"," } ?? ""
        return """
        {
          \(cacheLine) \(versionLine)
          "buckets": [\(buckets)],
          "total_markets": 12, "total_outcomes": 700, "total_winners": 215,
          "mce_ci_lower": 0.6, "mce_ci_upper": 1.7,
          "mce_closing_line": 1.5, "mce_opening_price": 2.2,
          "generated_at": "2026-08-02T04:00:00+00:00",
          "min_category_outcomes": 1000,
          "small_sample_categories": [
            {"category": "cricket_ipl", "outcomes": 812, "disposition": "parked_below_publish_bar", "publish_bar": 1000, "ece": 8.6}
          ],
          "date_range": {"start": "2021-07-13T00:00:00+00:00", "end": "2026-08-02T00:05:00+00:00"}
        }
        """
    }

    private static let staleCache = """
    {"status": "stale", "reason": "main_key_absent_durable", "generated_at": "2026-08-01T09:00:00+00:00", "age_s": 68400}
    """

    /// L2-232. Every "differs from healthy" assertion below is worthless if the
    /// healthy fixture is not actually renderable — three refusal screens differ
    /// from nothing, and that is exactly how this suite failed when the compatible
    /// set moved out from under a hard-coded fixture version. Asserted directly so
    /// the next drift reports its own cause instead of "47,296 == 47,296".
    func testTheFixtureVersionsAreWhatTheyClaimToBe() throws {
        let healthy = CalibrationViewModel(preloaded: try decode(Self.payload()))
        XCTAssertFalse(healthy.isIncompatible,
                       "the healthy fixture (\(Self.renderableVersion)) is being refused")
        XCTAssertEqual(healthy.populationVersionState, .matched)

        let refused = CalibrationViewModel(
            preloaded: try decode(Self.payload(version: Self.unrenderableVersion)))
        XCTAssertTrue(refused.isIncompatible,
                      "the mismatch fixture (\(Self.unrenderableVersion)) is being accepted")
    }

    func testHealthyStaleAndIncompatibleAllRenderAndAreVisiblyDistinct() throws {
        let healthy = try render(Self.payload(), name: "healthy")
        let stale = try render(Self.payload(cache: Self.staleCache), name: "stale-last-good")
        let mismatch = try render(
            Self.payload(version: Self.unrenderableVersion), name: "version-mismatch")

        for (name, png) in [("healthy", healthy), ("stale", stale), ("mismatch", mismatch)] {
            XCTAssertGreaterThan(png.count, 1_000, "\(name) render is suspiciously empty")
        }

        // The whole point of Item 2: a dated last-good must not be pixel-identical
        // to a current snapshot. Before this queue native had no `cache` decode at
        // all, so these two WOULD have been identical.
        XCTAssertNotEqual(healthy, stale,
                          "a stale payload rendered identically to a current one")
        // An incompatible payload must not render the curve at all.
        XCTAssertNotEqual(healthy, mismatch,
                          "a version-mismatched payload rendered as though current")
        XCTAssertNotEqual(stale, mismatch)
    }

    func testEmptyPayloadRendersWithoutCrashingAndDiffersFromHealthy() throws {
        let empty = try render(
            // `\#(...)` — the raw-string form. A plain `\(...)` inside `#"…"#`
            // is not interpolation, it is four literal characters, and the
            // payload would carry the source text instead of a version.
            #"{"buckets": [], "total_markets": 0, "total_outcomes": 0, "population_version": "\#(Self.renderableVersion)"}"#,
            name: "empty")
        XCTAssertGreaterThan(empty.count, 500)
        XCTAssertNotEqual(empty, try render(Self.payload(), name: "healthy-vs-empty"))
    }

    // MARK: - L2-231 (re-staged) — the availability states

    /// Rasterises the REAL frozen production response, not a hand-built one.
    ///
    /// Item 3 asks for rendered evidence "against the exact Queue 297 payload
    /// fixture". Everything else in this file is a hand-authored state; this is
    /// the one case where the numbers on the image are the numbers the server
    /// actually served on 2026-08-02 — including the `stale` envelope it was
    /// serving at the time, so the dated banner is rendered from real provenance
    /// rather than from a fixture written to produce it.
    func testTheFrozenProductionPayloadRendersItsRealNumbers() throws {
        let vm = CalibrationViewModel(preloaded: try decode(CalibrationProdFixture.json))
        XCTAssertTrue(vm.isStale, "the frozen response was served stale")
        XCTAssertTrue(vm.hasRenderableCurve)
        XCTAssertEqual(vm.cohortN, 389_385)
        XCTAssertEqual(vm.movedN + vm.unchangedN + vm.notApplicableN, vm.fullN)
        print("L2-231 prod render: cohortN=\(vm.cohortN) fullN=\(vm.fullN) "
            + "ECE=\(String(format: "%.1f", vm.cohortECE))pp "
            + "moved=\(vm.movedN) unchanged=\(vm.unchangedN) na=\(vm.notApplicableN)")
        // L2-237: the exact strings on the raster, logged so the rendered proof
        // carries the copy it is proof of — including what VoiceOver reads for
        // the toggle, which no screenshot can show.
        print("L2-237 prod hero: \(vm.heroPopulationText)")
        print("L2-237 prod cohort headline: \(vm.cohortHeadline)")
        print("L2-231 prod cohort detail: \(vm.cohortDetail)")
        print("L2-237 prod cohort short label: \(vm.cohortShortLabel)")
        print("L2-237 prod toggle label: \(vm.cohortToggleLabel)")
        print("L2-237 prod toggle a11y: \(vm.cohortToggleAccessibilityLabel)")
        print("L2-231 prod partition note: \(vm.activityPartitionNote ?? "nil")")
        let png = try render(CalibrationProdFixture.json, name: "production-2026-08-02")
        XCTAssertGreaterThan(png.count, 1_000)
    }

    /// Drives a model through a real `load()` so the RESULT of a failure is what
    /// gets rasterised, not a hand-set flag.
    @discardableResult
    private func renderAfterFailedRefresh(name: String) throws -> Data {
        struct Boom: Error, LocalizedError { var errorDescription: String? { "offline" } }
        let vm = CalibrationViewModel(preloaded: try decode(Self.payload()),
                                      fetcher: { throw Boom() })
        let expectation = expectation(description: "refresh")
        Task { @MainActor in await vm.load(); expectation.fulfill() }
        wait(for: [expectation], timeout: 5)
        XCTAssertTrue(vm.refreshFailed, "\(name): the fixture did not reach the failed state")
        XCTAssertNotNil(vm.data, "\(name): the curve was discarded")

        let view = CalibrationSurfaceView(viewModel: vm, scrolls: false).frame(width: 390)
        let renderer = ImageRenderer(content: view)
        renderer.scale = 2
        let image = try XCTUnwrap(renderer.uiImage, "\(name) produced no raster")
        let png = try XCTUnwrap(image.pngData())
        let url = FileManager.default.temporaryDirectory
            .appendingPathComponent("l2231-calibration-\(name).png")
        try? png.write(to: url)
        print("L2-231 render artifact [\(name)]: \(url.path) (\(png.count) bytes)")
        return png
    }

    func testAFailedRefreshKeepsTheCurveOnScreenAndLooksDifferentFromACurrentOne() throws {
        let healthy = try render(Self.payload(), name: "healthy-vs-refresh-failed")
        let failed = try renderAfterFailedRefresh(name: "refresh-failed")
        // The curve survived — a failure page would be a fraction of this size.
        XCTAssertGreaterThan(failed.count, 1_000)
        // ...and it is visibly not being presented as current.
        XCTAssertNotEqual(healthy, failed,
                          "a stale-after-failed-refresh screen rendered identically to a fresh one")
    }

    func testAPartiallyReadablePayloadSaysSoOnScreen() throws {
        // One poison bucket among three. The curve is drawn from what survived,
        // and the banner states the shortfall — a silently thinned curve looks
        // exactly like a complete one.
        let poisoned = """
        {
          "population_version": "\(Self.renderableVersion)",
          "buckets": [
            \(Self.buckets),
            {"bucket_idx": 7, "source": "kalshi", "category": "politics", "price_moved": true, "n": null}
          ],
          "total_markets": 12, "total_outcomes": 700, "total_winners": 215,
          "generated_at": "2026-08-02T04:00:00+00:00"
        }
        """
        let vm = CalibrationViewModel(preloaded: try decode(poisoned))
        XCTAssertEqual(vm.droppedBuckets, 1)
        XCTAssertNotNil(vm.partialDataNote)
        let partial = try render(poisoned, name: "partial-decode")
        XCTAssertGreaterThan(partial.count, 1_000)
        XCTAssertNotEqual(partial, try render(Self.payload(), name: "healthy-vs-partial"),
                          "a partially-read payload rendered identically to a whole one")
    }

    func testAnUnreadablePayloadRendersTheUnavailableStateNotAZeroCurve() throws {
        // `buckets` absent entirely. Every metric on this screen divides by a
        // bucket count, so the pre-fix path drew "0.0pp — Excellent" over nothing.
        let unreadable = #"{"population_version": "\#(Self.renderableVersion)", "total_outcomes": 700}"#
        let vm = CalibrationViewModel(preloaded: try decode(unreadable))
        XCTAssertFalse(vm.hasRenderableCurve)
        XCTAssertNotNil(vm.unavailableMessage)
        let png = try render(unreadable, name: "unreadable")
        XCTAssertGreaterThan(png.count, 500)
        XCTAssertNotEqual(png, try render(Self.payload(), name: "healthy-vs-unreadable"))
    }

    // MARK: - Layout envelopes (Item 3)

    /// Rasterises one payload across the width and text-size envelopes the app
    /// actually ships into, and asserts each one produced a real, differently
    /// laid-out image.
    ///
    /// This is a CLIPPING and LAYOUT check, not a pixel check. The states this
    /// queue added are text — a dated banner, a two-clause cohort description, a
    /// three-term partition sentence — and text is exactly what a 900pt regular
    /// width or an accessibility text size breaks differently from a 390pt
    /// compact one.
    func testTheSurfaceRendersAcrossWidthAndTextSizeEnvelopes() throws {
        let payload = CalibrationProdFixture.json
        let vm = CalibrationViewModel(preloaded: try decode(payload))

        struct Envelope { let name: String; let width: CGFloat; let regular: Bool; let size: DynamicTypeSize }
        let envelopes = [
            Envelope(name: "iphone-390", width: 390, regular: false, size: .large),
            Envelope(name: "iphone-320-se", width: 320, regular: false, size: .large),
            Envelope(name: "ipad-mac-1024-regular", width: 1024, regular: true, size: .large),
            Envelope(name: "iphone-390-accessibility3", width: 390, regular: false, size: .accessibility3),
        ]

        var sizes: [String: CGSize] = [:]
        for envelope in envelopes {
            let view = CalibrationSurfaceView(viewModel: vm, scrolls: false)
                .environment(\.horizontalSizeClass, envelope.regular ? .regular : .compact)
                .environment(\.dynamicTypeSize, envelope.size)
                .frame(width: envelope.width)
            let renderer = ImageRenderer(content: view)
            renderer.scale = 2
            let image = try XCTUnwrap(renderer.uiImage, "\(envelope.name) produced no raster")
            XCTAssertGreaterThan(image.size.height, 100, "\(envelope.name) collapsed")
            // The content is width-capped at 900pt in the regular class, so a
            // 1024pt canvas must still render the full stack rather than a
            // clipped or zero-height one.
            XCTAssertEqual(image.size.width, envelope.width, accuracy: 1,
                           "\(envelope.name) did not fill its canvas")
            // The raster IS the assertion; the file is only for eyeballing. At
            // accessibility sizes the surface grows past the point where
            // `pngData()` will encode it, and failing the layout check on the
            // encoder's limit would report the wrong thing entirely.
            let url = FileManager.default.temporaryDirectory
                .appendingPathComponent("l2231-calibration-env-\(envelope.name).png")
            let png = image.pngData()
            if let png { try? png.write(to: url) }
            print("L2-231 envelope [\(envelope.name)]: \(Int(image.size.width))x\(Int(image.size.height))"
                + " -> \(png == nil ? "(too large to encode)" : url.path)")
            sizes[envelope.name] = image.size
        }

        // Accessibility text must actually reflow — an identical height would
        // mean the environment was ignored and the check proved nothing.
        let base = try XCTUnwrap(sizes["iphone-390"])
        let large = try XCTUnwrap(sizes["iphone-390-accessibility3"])
        XCTAssertGreaterThan(large.height, base.height,
                             "accessibility text size did not reflow the surface")
    }

    func testActivityDirectionDrivesTheRenderedComparison() throws {
        // Same page, two orderings. The pre-fix native code hard-coded the moved
        // cohort green and printed a superiority claim regardless of the numbers,
        // so these two would have rendered the same colours and the same shape of
        // sentence with only the ratio changing.
        let movedWorse = Self.payload()
        let movedBetter = """
        {
          "population_version": "\(Self.renderableVersion)",
          "buckets": [
            {"bucket_idx": 2, "source": "kalshi", "category": "baseball_mlb", "price_moved": true, "n": 200, "winners": 50, "avg_prob": 0.25, "sum_prob": 50.0, "sum_sq_err": 44.0, "ci_lower": 0.21, "ci_upper": 0.31},
            {"bucket_idx": 5, "source": "polymarket", "category": "politics", "price_moved": false, "n": 100, "winners": 75, "avg_prob": 0.55, "sum_prob": 55.0, "sum_sq_err": 24.0, "ci_lower": 0.65, "ci_upper": 0.84}
          ],
          "total_markets": 4, "total_outcomes": 300, "total_winners": 125,
          "mce_ci_lower": 0.6, "mce_ci_upper": 1.7,
          "mce_closing_line": 1.5, "mce_opening_price": 2.2,
          "generated_at": "2026-08-02T04:00:00+00:00"
        }
        """
        XCTAssertNotEqual(
            try render(movedWorse, name: "activity-moved-worse"),
            try render(movedBetter, name: "activity-moved-better"),
            "the activity section rendered identically under opposite orderings")
    }
}
