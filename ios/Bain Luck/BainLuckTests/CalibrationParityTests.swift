import SwiftUI
import XCTest
@testable import Bain_Luck

/// CAL-P026 — exam item 5: the native calibration surface must agree with web.
///
/// ## The question this file answers, and why it needed a file
///
/// `docs/CALIBRATION-EXIT-EXAM.md` item 5 asks for native and web "showing the
/// same population version, the same generated-at, and the same headline
/// figures". That is a question about TWO surfaces, and until now only one of
/// them could answer it mechanically: `app/calibration/page.tsx` publishes
/// `data-population-version`, `data-cache-status`, `data-contract-state`,
/// `data-generated-at`, `data-cohort-n`, `data-full-n` and the partition counts,
/// and `calibrationAuditHooks.test.tsx` fails CI if one is dropped. Native
/// published nothing — zero `accessibilityIdentifier`s on the entire surface —
/// so the comparison could only be made by a person looking at two screenshots.
///
/// A parity that can only be checked by eye gets checked once, on the day
/// somebody cares, and drifts silently afterwards. That is the shape of failure
/// this exam has hit repeatedly, and web's own source anticipated it: the comment
/// above its population-count hook says *"a native surface reading the other one
/// diverges silently. Both are published here as data so the parity check reads
/// numbers, not text."* This is the parity check that comment was written for.
///
/// ## CAL-P043 (#1643): these numbers are now a RECORD, not this file's opinion
///
/// The constants below are the contents of
/// `fixtures/calibration/parity-record-2026-08-02.json`, the language-neutral
/// artifact web is graded against too. That file is the whole fix for codex
/// C236: native's figures need Swift to compute and web's need TypeScript, so
/// the two can never meet inside one process — they meet in the record instead,
/// and each side asserts in its own runner that it reproduces it.
///
/// `frontend/e2e/contract/calibrationSurfaceParity.contract.test.js` parses the
/// constants below OUT OF THIS FILE and asserts they equal the record, so a
/// value edited here without the record fails there, and a record edited without
/// this file fails here. They are mirrored, not merely coincident.
///
/// (They are still literals rather than a file read. An XCTest reading a
/// `#filePath`-relative JSON is host-filesystem-dependent; trading a verifiable
/// duplicate for an unverifiable load path is a bad trade. Same reasoning as
/// `CalibrationProdFixture`'s embed, whose byte-equality with the shared payload
/// that same contract test also checks.)
///
/// Their provenance: computed INDEPENDENTLY in Python, replicating
/// `CalibrationMath`'s definitions from its source, and reconciling with the
/// figures `docs/CALIBRATION-EXIT-EXAM.md` item 2 reports from the same
/// production response — 349,310 moved + 263,022 unchanged + 40,075
/// not-applicable = 652,407 — which CAL-P025 derived separately in TypeScript.
///
/// So a change that moves any number here is either a real behaviour change or a
/// real bug, and in both cases the right response is to look, not to re-baseline.
@MainActor
final class CalibrationParityTests: XCTestCase {

    // MARK: - The record: what the 2026-08-02 production payload publishes

    // Toggle-independent — facts about the payload and this build's judgement.
    private static let publishedPopulationVersion = "q267"
    private static let publishedGeneratedAt = "2026-08-02T03:23:54.886392+00:00"
    private static let publishedCacheStatus = "stale"
    private static let publishedContractState = "match"
    private static let publishedMarkets = 534_269

    private static let publishedFullN = 652_407
    private static let publishedMovedN = 349_310
    private static let publishedUnchangedN = 263_022
    private static let publishedNotApplicableN = 40_075

    // The default cohort: `price_moved != false`, i.e. moved + not-applicable.
    private static let defaultCohortN = 389_385
    private static let defaultECE = 1.542547
    private static let defaultMCE = 1.450000
    private static let defaultBrier = 0.164935

    // The toggle ON: every resolved outcome, including the never-moved ones.
    private static let allCohortN = 652_407
    private static let allECE = 1.261460
    private static let allMCE = 1.240000
    private static let allBrier = 0.163755

    private func prodModel(includeThin: Bool = false) throws -> CalibrationViewModel {
        let dec = JSONDecoder()
        dec.keyDecodingStrategy = .convertFromSnakeCase
        let data = try dec.decode(CalibrationData.self, from: Data(CalibrationProdFixture.json.utf8))
        let vm = CalibrationViewModel(preloaded: data)
        vm.includeThin = includeThin
        return vm
    }

    // MARK: - The parity set

    func testParityFiguresMatchWhatWebPublishesForTheSamePayload() throws {
        let p = try prodModel().parity

        XCTAssertEqual(p.populationVersion, Self.publishedPopulationVersion)
        XCTAssertEqual(p.generatedAt, Self.publishedGeneratedAt)
        XCTAssertEqual(p.cacheStatus, Self.publishedCacheStatus)
        XCTAssertEqual(p.contractState, Self.publishedContractState)
        XCTAssertEqual(p.markets, Self.publishedMarkets)

        XCTAssertEqual(p.fullN, Self.publishedFullN)
        XCTAssertEqual(p.cohortN, Self.defaultCohortN)
        XCTAssertEqual(p.movedN, Self.publishedMovedN)
        XCTAssertEqual(p.unchangedN, Self.publishedUnchangedN)
        XCTAssertEqual(p.notApplicableN, Self.publishedNotApplicableN)

        XCTAssertEqual(p.ece, Self.defaultECE, accuracy: 1e-6)
        XCTAssertEqual(p.mce, Self.defaultMCE, accuracy: 1e-6)
        XCTAssertEqual(p.brier, Self.defaultBrier, accuracy: 1e-6)
    }

    /// CAL-P043 (#1643): the OTHER cohort-toggle state, which nothing graded.
    ///
    /// C236 asked for the parity record on both states by name, and the reason
    /// is concrete: a surface that renders the toggle but publishes the default
    /// cohort's numbers in both states looks entirely plausible in a screenshot
    /// and in every single-state assertion. Only a comparison BETWEEN the two
    /// states shows the toggle is inert.
    func testParityFiguresMatchTheRecordWithTheToggleOn() throws {
        let p = try prodModel(includeThin: true).parity

        // Toggle-independent facts must not move.
        XCTAssertEqual(p.populationVersion, Self.publishedPopulationVersion)
        XCTAssertEqual(p.contractState, Self.publishedContractState)
        XCTAssertEqual(p.fullN, Self.publishedFullN)
        XCTAssertEqual(p.movedN, Self.publishedMovedN)
        XCTAssertEqual(p.unchangedN, Self.publishedUnchangedN)
        XCTAssertEqual(p.notApplicableN, Self.publishedNotApplicableN)

        // The cohort figures must.
        XCTAssertEqual(p.cohortN, Self.allCohortN)
        XCTAssertEqual(p.cohortN, p.fullN, "the toggle ON cohort IS the full population")
        XCTAssertEqual(p.ece, Self.allECE, accuracy: 1e-6)
        XCTAssertEqual(p.mce, Self.allMCE, accuracy: 1e-6)
        XCTAssertEqual(p.brier, Self.allBrier, accuracy: 1e-6)
    }

    /// The two states must be distinguishable, or grading both proves nothing.
    func testTheToggleActuallyMovesThePublishedRecord() throws {
        let off = CalibrationSurfaceView.provenanceValue(try prodModel(includeThin: false).parity)
        let on = CalibrationSurfaceView.provenanceValue(try prodModel(includeThin: true).parity)

        XCTAssertNotEqual(off, on)
        XCTAssertTrue(on.contains("cohort_n=\(Self.allCohortN)"), on)
        XCTAssertTrue(off.contains("cohort_n=\(Self.defaultCohortN)"), off)
        XCTAssertNotEqual(
            Self.defaultECE, Self.allECE,
            "if the two cohorts had the same ECE this whole comparison would be vacuous"
        )
    }

    /// Web publishes `data-partition-reconciles` because the three activity
    /// cohorts are a PARTITION of the population, and a surface that quietly
    /// dropped or double-counted a slice would still render plausible numbers.
    func testTheActivityPartitionReconcilesToTheFullPopulation() throws {
        let p = try prodModel().parity
        XCTAssertEqual(p.movedN + p.unchangedN + p.notApplicableN, p.fullN)
        XCTAssertTrue(p.reconciles)
    }

    /// The default cohort's predicate is `price_moved != false`, so it is exactly
    /// moved + not-applicable. Pinned because the cohort count is the number the
    /// hero LEADS with, and L2-231 already caught native leading with a different
    /// population than web once.
    func testTheDefaultCohortIsMovedPlusNotApplicable() throws {
        let p = try prodModel().parity
        XCTAssertEqual(p.cohortN, p.movedN + p.notApplicableN)
        XCTAssertNotEqual(p.cohortN, p.fullN, "a cohort equal to the full population would make this vacuous")
    }

    /// The version the server sent and this build's JUDGEMENT about it are two
    /// different facts, and web keeps them in two attributes for that reason.
    ///
    /// CAL-P043 (#1643): the expected value is `"match"`, not `"matched"`. Native
    /// used to publish its own spelling of web's vocabulary for the same field —
    /// a live cross-surface divergence that only survived because the gate
    /// claiming to compare the two surfaces never read a web value.
    func testContractStateIsPublishedSeparatelyFromTheVersion() throws {
        let p = try prodModel().parity
        XCTAssertEqual(p.populationVersion, Self.publishedPopulationVersion)
        XCTAssertEqual(p.contractState, "match")
    }

    func testAnUnknownPopulationIsPublishedAsMismatchedNotAsAbsent() throws {
        let json = CalibrationProdFixture.json.replacingOccurrences(
            of: "\"population_version\": \"q267\"",
            with: "\"population_version\": \"q999\""
        )
        let dec = JSONDecoder()
        dec.keyDecodingStrategy = .convertFromSnakeCase
        let data = try dec.decode(CalibrationData.self, from: Data(json.utf8))
        let p = CalibrationViewModel(preloaded: data).parity

        // Web's spelling for this state is "incompatible" (CAL-P043 / #1643).
        XCTAssertEqual(p.contractState, "incompatible")
        // The version still travels. A refusing surface that ALSO hid which
        // population it refused would make the incident undiagnosable from the
        // outside — which is what the 2026-08-02 q299 rollback needed.
        XCTAssertEqual(p.populationVersion, "q999")
    }

    // MARK: - The published provenance string

    func testProvenanceValueCarriesEveryStateWebPublishesAsAnAttribute() throws {
        let value = CalibrationSurfaceView.provenanceValue(try prodModel().parity)

        XCTAssertTrue(value.contains("population=q267"), value)
        XCTAssertTrue(value.contains("contract=match"), value)
        XCTAssertTrue(value.contains("cache=stale"), value)
        XCTAssertTrue(value.contains("generated=2026-08-02T03:23:54.886392+00:00"), value)
        XCTAssertTrue(value.contains("cohort_n=389385"), value)
        XCTAssertTrue(value.contains("full_n=652407"), value)
        XCTAssertTrue(value.contains("reconciles=true"), value)

        // CAL-P043 (#1643): the descriptor now carries the whole record, so the
        // figures a reader most wants to compare across surfaces are readable
        // without rasterising the view. Web publishes the identical keys in the
        // identical order as `data-parity`.
        XCTAssertTrue(value.contains("moved_n=\(Self.publishedMovedN)"), value)
        XCTAssertTrue(value.contains("unchanged_n=\(Self.publishedUnchangedN)"), value)
        XCTAssertTrue(value.contains("not_applicable_n=\(Self.publishedNotApplicableN)"), value)
        XCTAssertTrue(value.contains("markets=\(Self.publishedMarkets)"), value)
        XCTAssertTrue(value.contains("ece=1.5425"), value)
        XCTAssertTrue(value.contains("mce=1.4500"), value)
        XCTAssertTrue(value.contains("brier=0.1649"), value)

        // Raw, never display-formatted: no "pp" UNIT suffix on any value and no
        // thousands separators anywhere.
        //
        // Checked as a suffix rather than as a substring, because the key
        // `not_applicable_n` legitimately contains "pp" — a substring check here
        // failed on the real record the first time this test was run.
        for field in value.split(separator: " ") {
            XCTAssertFalse(field.hasSuffix("pp"), "\(field) carries a display unit")
        }
        XCTAssertFalse(value.contains(","), value)
    }

    /// An absent payload must not publish a confident-looking zero. `n=0` and
    /// "no data" are different facts, and gotcha #53 is precisely about a surface
    /// that renders one as the other.
    func testAnEmptyModelPublishesAbsenceRatherThanZeroedFigures() {
        let value = CalibrationSurfaceView.provenanceValue(CalibrationViewModel().parity)
        XCTAssertTrue(value.contains("population=none"), value)
        XCTAssertTrue(value.contains("generated=none"), value)
        XCTAssertTrue(value.contains("contract=unverified"), value)
    }

    // MARK: - Rendered evidence

    /// Rasterises the REAL surface from the 2026-08-02 production payload, which
    /// is the side-by-side counterpart to a browser screenshot of `/calibration`
    /// serving that same response.
    ///
    /// The existing L2-231 render smoke tests cover the degraded STATES from
    /// synthetic fixtures (n=600). None of them renders production's actual
    /// payload, so there was no native image to hold beside the web one — which
    /// is the literal artifact exam item 5 asks for.
    ///
    /// The assertions stay semantic: a real raster, and the stale branch actually
    /// taken. Pinning pixels would make an editorial reword look like a parity
    /// failure, which is how render gates get deleted.
    func testProductionPayloadRendersTheStaleSurfaceForSideBySideEvidence() throws {
        let vm = try prodModel()
        XCTAssertFalse(vm.loading, "a preloaded model must not rasterise the spinner (the L2-231 trap)")
        XCTAssertTrue(vm.isStale, "the 2026-08-02 payload is a dated last-good copy; the banner is the honesty check")
        XCTAssertFalse(vm.isIncompatible, "q267 is in the shipped compatible set, so the curve must render")

        let view = CalibrationSurfaceView(viewModel: vm, scrolls: false).frame(width: 390)
        let renderer = ImageRenderer(content: view)
        renderer.scale = 2
        let image = try XCTUnwrap(renderer.uiImage, "the production payload produced no raster")
        XCTAssertGreaterThan(image.size.width, 0)
        XCTAssertGreaterThan(image.size.height, 0)

        let png = try XCTUnwrap(image.pngData())
        let url = FileManager.default.temporaryDirectory
            .appendingPathComponent("calp026-native-calibration-prod.png")
        try? png.write(to: url)
        print("CAL-P026 render artifact [prod]: \(url.path) (\(png.count) bytes)")
        print("CAL-P026 parity [prod]: \(CalibrationSurfaceView.provenanceValue(vm.parity))")
    }

    // MARK: - The hooks themselves

    /// The identifiers are deliberately the SAME STRINGS as web's `data-testid`s.
    /// `frontend/e2e/contract/calibrationSurfaceParity.contract.test.js` asserts
    /// the two lists agree across the language boundary; this asserts the native
    /// half has not been renamed out from under it.
    func testHookNamesMatchWebsTestIds() {
        XCTAssertEqual(CalibrationSurfaceView.surfaceHook, "calibration-surface")
        XCTAssertEqual(CalibrationSurfaceView.generatedAtHook, "calibration-generated-at")
        XCTAssertEqual(CalibrationSurfaceView.outcomesHook, "calibration-stat-outcomes")
        XCTAssertEqual(CalibrationSurfaceView.eceHook, "calibration-stat-ece")
        XCTAssertEqual(CalibrationSurfaceView.brierHook, "calibration-stat-brier")
        XCTAssertEqual(CalibrationSurfaceView.marketsHook, "calibration-stat-markets")
    }
}
