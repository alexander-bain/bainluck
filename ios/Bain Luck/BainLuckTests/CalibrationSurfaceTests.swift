import XCTest
@testable import Bain_Luck

/// L2-231 Item 2 — the native calibration surface against the RESTORED payload.
///
/// `CalibrationMathTests` already proves the arithmetic matches the web page.
/// This suite proves the thing that arithmetic parity cannot: that native tells
/// the truth about WHICH payload it is rendering, and that it renders the same
/// story the public page does rather than a plausible-looking divergence.
///
/// Item 0's web/native matrix found four of those, all of them silent:
///
///   1. `CalibrationData` had no `cache` decode at all, so a payload the server
///      explicitly marked `stale` — a dated last-good copy — rendered on native
///      with no banner and no date, i.e. as current data. Web has bannered this
///      since Queue 297 Item 1.
///   2. No `population_version` decode, so a payload built under a population
///      contract this build was not written against could render under this
///      build's labels with nothing able to tell. Q299 bumped q267 -> q299 while
///      this suite was being written, which is exactly the live case.
///   3. The hero led with `total_outcomes` where web leads with the COHORT
///      count — two different numbers under the default cohort, presented
///      as the same claim on two surfaces.
///   4. The trading-activity section still printed
///      `"Markets with active trading are 0.6x more accurately calibrated."`,
///      the literal string L2-230 removed from web: a ratio below 1 sold as
///      superiority, inverting the two numbers rendered beside it.
///
/// Every fixture below is a payload STATE, not a happy path with variations.
final class CalibrationSurfaceTests: XCTestCase {

    // MARK: - Fixtures

    /// Buckets shared by every fixture. Deliberately reproduces the live 2026-08-02
    /// ordering — the price-MOVED cohort carrying the HIGHER error — because that
    /// is the case the shipped copy got backwards.
    ///
    /// moved: idx 2 -> n 200, winners 60 (avg 25.0, actual 30.0, err +5.0)
    /// unchanged: idx 5 -> n 100, winners 55 (avg 55.0, actual 55.0, err 0.0)
    private static let buckets = """
    {"bucket_idx": 2, "source": "kalshi", "category": "baseball_mlb", "price_moved": true, "n": 200, "winners": 60, "avg_prob": 0.25, "sum_prob": 50.0, "sum_sq_err": 44.0, "ci_lower": 0.21, "ci_upper": 0.31},
    {"bucket_idx": 5, "source": "polymarket", "category": "politics", "price_moved": false, "n": 100, "winners": 55, "avg_prob": 0.55, "sum_prob": 55.0, "sum_sq_err": 24.0, "ci_lower": 0.45, "ci_upper": 0.64},
    {"bucket_idx": 2, "source": "odds_api", "category": "baseball_mlb", "price_moved": null, "n": 400, "winners": 100, "avg_prob": 0.25, "sum_prob": 100.0, "sum_sq_err": 80.0, "ci_lower": 0.21, "ci_upper": 0.29}
    """

    /// A population version this build accepts, taken from the build's own set
    /// rather than written as a literal — L2-232's whole point is that the set
    /// changes and a hard-coded copy of it goes stale and starts lying.
    static let acceptedVersion: String = CalibrationViewModel
        .compatiblePopulationVersions.sorted().first ?? "q267"

    /// A well-formed version that is deliberately NOT in the compatible set.
    static let unknownVersion = "q400"

    /// A healthy, current payload at a population version this build accepts.
    /// Carries a parked category with Queue 299's machine-readable disposition.
    private static func healthy(
        populationVersion: String? = CalibrationSurfaceTests.acceptedVersion,
        cache: String? = nil
    ) -> String {
        let versionLine = populationVersion.map { "\"population_version\": \"\($0)\"," } ?? ""
        let cacheLine = cache.map { "\"cache\": \($0)," } ?? ""
        return """
        {
          \(cacheLine)
          \(versionLine)
          "buckets": [\(buckets)],
          "total_markets": 12,
          "total_outcomes": 700,
          "total_winners": 215,
          "mce_ci_lower": 0.6,
          "mce_ci_upper": 1.7,
          "mce_closing_line": 1.5,
          "mce_opening_price": 2.2,
          "generated_at": "2026-08-02T04:00:00+00:00",
          "min_category_outcomes": 1000,
          "small_sample_categories": [
            {"category": "cricket_ipl", "outcomes": 812, "disposition": "parked_below_publish_bar", "publish_bar": 1000, "ece": 8.6},
            {"category": "esports", "outcomes": 500}
          ],
          "date_range": {"start": "2021-07-13T00:00:00+00:00", "end": "2026-08-02T00:05:00+00:00"}
        }
        """
    }

    /// The Queue-297 degraded envelope: a durable last-good copy, honestly dated.
    private static let staleCache = """
    {"status": "stale", "reason": "main_key_absent_durable", "generated_at": "2026-08-01T09:00:00+00:00", "age_s": 68400}
    """

    private static func decode(_ json: String) throws -> CalibrationData {
        let dec = JSONDecoder()
        dec.keyDecodingStrategy = .convertFromSnakeCase
        return try dec.decode(CalibrationData.self, from: Data(json.utf8))
    }

    @MainActor
    private func model(_ json: String) throws -> CalibrationViewModel {
        CalibrationViewModel(preloaded: try Self.decode(json))
    }

    // MARK: - 1. Healthy restored payload

    @MainActor
    func testHealthyPayloadDeclaresItsPopulationVersionAndRendersCurrent() throws {
        let vm = try model(Self.healthy())
        XCTAssertEqual(vm.populationVersion, Self.acceptedVersion)
        XCTAssertEqual(vm.populationVersionState, .matched)
        XCTAssertFalse(vm.isIncompatible)
        // No cache envelope == current. Nothing dated, nothing suppressed.
        XCTAssertFalse(vm.isStale)
        XCTAssertNil(vm.staleBannerDetail)
    }

    @MainActor
    func testHealthyPayloadHeroNamesTheSamePopulationTheWebHeroDoes() throws {
        let vm = try model(Self.healthy())
        // Web's hero clause, word for word (L2-236's `describeCohort`, adopted
        // natively by L2-237). cohortN (price_moved != false) = 200 + 400 = 600;
        // fullN = 700; the 100 excluded are the never-moved rows.
        XCTAssertEqual(vm.cohortN, 600)
        XCTAssertEqual(vm.fullN, 700)
        XCTAssertEqual(
            vm.heroPopulationText,
            "600 resolved predictions \u{2014} every outcome except the 100 whose price never "
                + "moved off its opening line (700 in total)")
        // The pre-fix bug: leading with total_outcomes (700) under the default
        // cohort, i.e. a number the cohort below it contradicts.
        XCTAssertNotEqual(vm.heroPopulationText, vm.formattedTotalOutcomes)

        vm.includeThin = true
        XCTAssertEqual(vm.cohortN, 700)
        XCTAssertEqual(vm.heroPopulationText, "700 resolved predictions")
    }

    @MainActor
    func testHealthyPayloadCohortValuesMatchTheWebParityMath() throws {
        let vm = try model(Self.healthy())
        // Same aggregation the web page runs client-side; asserted here so a
        // native-only regression cannot pass the version check and still print
        // different digits from the public page.
        XCTAssertEqual(vm.movedECE, 5.0, accuracy: 0.001)
        XCTAssertEqual(vm.unchangedECE, 0.0, accuracy: 0.001)
        XCTAssertEqual(vm.movedN, 200)
        XCTAssertEqual(vm.unchangedN, 100)
    }

    // MARK: - 2. The activity claim (the L2-230 bug, still live on native)

    @MainActor
    func testActivityCopyNamesTheHigherErrorCohortAndNeverClaimsSuperiority() throws {
        let vm = try model(Self.healthy())
        let activity = vm.activity
        XCTAssertEqual(activity.direction, .movedHigher)
        let sentence = try XCTUnwrap(activity.sentence)
        XCTAssertTrue(sentence.contains("the price-moved cohort carries the higher calibration error"))
        // The exact strings L2-230 removed from web must never appear on native.
        XCTAssertFalse(sentence.localizedCaseInsensitiveContains("more accurately calibrated"))
        XCTAssertFalse(sentence.localizedCaseInsensitiveContains("better calibrated"))
        XCTAssertFalse(sentence.localizedCaseInsensitiveContains("dramatically"))
    }

    @MainActor
    func testActivityRatioIsSuppressedWhenTheLowerSideRoundsToZero() throws {
        // unchangedECE is exactly 0.0 here, which is what the OLD native code
        // divided by: `unchangedECE / movedECE` guarded only on `> 0`, so a
        // 0.0 lower side produced either a nonsense ratio or nothing at all
        // depending on which side hit zero. The ordering still renders.
        let vm = try model(Self.healthy())
        XCTAssertNil(vm.activity.ratioText)
        let sentence = try XCTUnwrap(vm.activity.sentence)
        XCTAssertFalse(sentence.contains("x the"))
        XCTAssertFalse(sentence.contains("inf"))
        XCTAssertFalse(sentence.contains("nan"))
    }

    /// Table-driven parity with the web formatter, including the live 1.7/1.0 case.
    func testActivityComparisonTable() {
        struct Case {
            let name: String
            let movedECE: Double?, movedN: Int?
            let unchangedECE: Double?, unchangedN: Int?
            let direction: CalibrationMath.ActivityDirection
            let ratio: String?
            let rendersSentence: Bool
        }
        let cases: [Case] = [
            // The literal production state on 2026-08-02: 1.7pp vs 1.0pp. The
            // shipped native string was "0.6x more accurately calibrated".
            .init(name: "live changed-worse", movedECE: 1.7162, movedN: 349_310,
                  unchangedECE: 1.0341, unchangedN: 263_022,
                  direction: .movedHigher, ratio: "1.7", rendersSentence: true),
            .init(name: "changed-better", movedECE: 1.0, movedN: 10,
                  unchangedECE: 2.0, unchangedN: 10,
                  direction: .unchangedHigher, ratio: "2.0", rendersSentence: true),
            .init(name: "exact tie", movedECE: 1.5, movedN: 10,
                  unchangedECE: 1.5, unchangedN: 10,
                  direction: .tied, ratio: nil, rendersSentence: true),
            // Both round to 1.5 at display precision, so prose must not rank them.
            .init(name: "tie by display rounding", movedECE: 1.4501, movedN: 10,
                  unchangedECE: 1.5, unchangedN: 10,
                  direction: .tied, ratio: nil, rendersSentence: true),
            // Straddles the rounding boundary the other way: 1.4 vs 1.5, ordered.
            .init(name: "ordered across the boundary", movedECE: 1.4499, movedN: 10,
                  unchangedECE: 1.5001, unchangedN: 10,
                  direction: .unchangedHigher, ratio: "1.1", rendersSentence: true),
            // Ordered at display precision (21.0 vs 20.9) but the RATIO rounds to
            // 1.0x, which reads as "the same" beside prose that just said one is
            // higher. The ordering is kept; the ratio clause is dropped.
            .init(name: "ratio would print 1.0x", movedECE: 21.0, movedN: 10,
                  unchangedECE: 20.9, unchangedN: 10,
                  direction: .movedHigher, ratio: nil, rendersSentence: true),
            .init(name: "zero lower side", movedECE: 2.0, movedN: 10,
                  unchangedECE: 0.0, unchangedN: 10,
                  direction: .movedHigher, ratio: nil, rendersSentence: true),
            .init(name: "both zero", movedECE: 0.0, movedN: 10,
                  unchangedECE: 0.0, unchangedN: 10,
                  direction: .tied, ratio: nil, rendersSentence: true),
            .init(name: "missing moved cohort", movedECE: nil, movedN: 10,
                  unchangedECE: 1.0, unchangedN: 10,
                  direction: .unknown, ratio: nil, rendersSentence: false),
            .init(name: "empty unchanged cohort", movedECE: 1.0, movedN: 10,
                  unchangedECE: 1.0, unchangedN: 0,
                  direction: .unknown, ratio: nil, rendersSentence: false),
            .init(name: "nil n", movedECE: 1.0, movedN: nil,
                  unchangedECE: 1.0, unchangedN: 10,
                  direction: .unknown, ratio: nil, rendersSentence: false),
            .init(name: "NaN", movedECE: Double.nan, movedN: 10,
                  unchangedECE: 1.0, unchangedN: 10,
                  direction: .unknown, ratio: nil, rendersSentence: false),
            .init(name: "positive infinity", movedECE: .infinity, movedN: 10,
                  unchangedECE: 1.0, unchangedN: 10,
                  direction: .unknown, ratio: nil, rendersSentence: false),
            .init(name: "negative infinity", movedECE: -.infinity, movedN: 10,
                  unchangedECE: 1.0, unchangedN: 10,
                  direction: .unknown, ratio: nil, rendersSentence: false),
            .init(name: "negative ECE", movedECE: -1.0, movedN: 10,
                  unchangedECE: 1.0, unchangedN: 10,
                  direction: .unknown, ratio: nil, rendersSentence: false),
            .init(name: "negative n", movedECE: 1.0, movedN: -5,
                  unchangedECE: 1.0, unchangedN: 10,
                  direction: .unknown, ratio: nil, rendersSentence: false),
        ]

        let banned = ["more accurately calibrated", "better calibrated", "dramatically", "improves"]

        for c in cases {
            let out = CalibrationMath.describeActivity(
                movedECE: c.movedECE, movedN: c.movedN,
                unchangedECE: c.unchangedECE, unchangedN: c.unchangedN
            )
            XCTAssertEqual(out.direction, c.direction, "direction for \(c.name)")
            XCTAssertEqual(out.ratioText, c.ratio, "ratio for \(c.name)")
            XCTAssertEqual(out.sentence != nil, c.rendersSentence, "sentence presence for \(c.name)")

            guard let sentence = out.sentence else { continue }

            // Invariants asserted across EVERY renderable case, not just the
            // interesting ones — this is what catches a new state added later.
            for phrase in banned {
                XCTAssertFalse(sentence.localizedCaseInsensitiveContains(phrase),
                               "\(c.name) must not say \"\(phrase)\"")
            }
            for token in ["nan", "inf", "nil", "Optional"] {
                XCTAssertFalse(sentence.localizedCaseInsensitiveContains(token),
                               "\(c.name) leaked \"\(token)\": \(sentence)")
            }
            if let ratio = out.ratioText {
                // A shown ratio is ALWAYS higher ÷ lower, so it can never be < 1.
                let value = try? XCTUnwrap(Double(ratio))
                XCTAssertGreaterThan(value ?? 0, 1.0, "ratio must exceed 1 for \(c.name)")
            }
        }
    }

    func testActivityComparisonIsSymmetricUnderArgumentSwap() {
        // Swapping the cohorts must change WHICH label is named and nothing else.
        let a = CalibrationMath.describeActivity(movedECE: 1.7, movedN: 100, unchangedECE: 1.0, unchangedN: 100)
        let b = CalibrationMath.describeActivity(movedECE: 1.0, movedN: 100, unchangedECE: 1.7, unchangedN: 100)
        XCTAssertEqual(a.direction, .movedHigher)
        XCTAssertEqual(b.direction, .unchangedHigher)
        XCTAssertEqual(a.ratioText, b.ratioText)
    }

    // MARK: - 3. Dated last-good payload

    @MainActor
    func testStalePayloadIsVisiblyDatedAndNeverPresentedAsCurrent() throws {
        let vm = try model(Self.healthy(cache: Self.staleCache))
        XCTAssertTrue(vm.isStale)
        let detail = try XCTUnwrap(vm.staleBannerDetail)
        // The formatted date is rendered in the DEVICE's timezone, deliberately —
        // so it is asserted as "a real date was formatted", not as a literal
        // string. Pinning "Aug 1" here would pass in PT and fail in CI's UTC,
        // which is a test bug masquerading as a rendering bug.
        XCTAssertFalse(detail.contains("earlier"), "banner must date the snapshot: \(detail)")
        XCTAssertTrue(detail.contains("Aug"), "banner must name the month: \(detail)")
        // The age IS timezone-free, so it is asserted exactly.
        XCTAssertTrue(detail.contains("19h ago"), "banner must age the snapshot: \(detail)")
        XCTAssertTrue(detail.contains("rebuilds hourly"))
        // Stale is a freshness state, not a contract failure — the curve renders.
        XCTAssertFalse(vm.isIncompatible)
        XCTAssertEqual(vm.cohortN, 600)
    }

    @MainActor
    func testStaleEnvelopeWithNoDateFallsBackToThePayloadsOwnTimestamp() throws {
        let vm = try model(Self.healthy(cache: #"{"status": "stale", "reason": "redis_unavailable"}"#))
        XCTAssertTrue(vm.isStale)
        let detail = try XCTUnwrap(vm.staleBannerDetail)
        // The envelope omits generated_at, so the payload's own is used before
        // giving up. A date is still shown, and no age clause is invented.
        XCTAssertFalse(detail.contains("earlier"), detail)
        XCTAssertFalse(detail.contains("ago"), "no age is known, so none is claimed: \(detail)")
        XCTAssertFalse(detail.localizedCaseInsensitiveContains("nil"))
    }

    @MainActor
    func testStalePayloadWithNoDateAnywhereStillBannersRatherThanGoingSilent() throws {
        // Dropping the banner because no date could be formatted would present
        // the snapshot as live — the exact failure the banner exists to prevent.
        // An undated stale banner is worse than a dated one and better than none.
        let undated = """
        {"cache": {"status": "stale"}, "buckets": [\(Self.buckets)],
         "total_markets": 1, "total_outcomes": 700}
        """
        let vm = try model(undated)
        XCTAssertTrue(vm.isStale)
        let detail = try XCTUnwrap(vm.staleBannerDetail)
        XCTAssertTrue(detail.contains("built earlier"), detail)
        XCTAssertTrue(detail.contains("rebuilds hourly"))
        XCTAssertFalse(detail.localizedCaseInsensitiveContains("nil"))
    }

    @MainActor
    func testFreshCacheEnvelopeIsNotTreatedAsStale() throws {
        let vm = try model(Self.healthy(cache: #"{"status": "fresh"}"#))
        XCTAssertFalse(vm.isStale)
        XCTAssertNil(vm.staleBannerDetail)
    }

    func testFormatAgeMatchesTheWebBanner() {
        XCTAssertEqual(CalibrationViewModel.formatAge(45), "45s")
        XCTAssertEqual(CalibrationViewModel.formatAge(600), "10m")
        XCTAssertEqual(CalibrationViewModel.formatAge(68_400), "19h")
        XCTAssertEqual(CalibrationViewModel.formatAge(-10), "0s")
    }

    // MARK: - 4. Version mismatch

    @MainActor
    func testVersionMismatchCannotMasqueradeAsCurrentData() throws {
        let vm = try model(Self.healthy(populationVersion: Self.unknownVersion))
        XCTAssertEqual(vm.populationVersionState, .mismatched(Self.unknownVersion))
        XCTAssertTrue(vm.isIncompatible)
        XCTAssertNotNil(vm.incompatibleMessage)
    }

    // MARK: - 4b. L2-232 — the set, and what it is for

    @MainActor
    func testEveryVersionInTheCompatibleSetIsAccepted() throws {
        // "previous-compatible". The set exists so a server roll-FORWARD or
        // roll-BACK between listed versions is a non-event on this surface. If
        // only one entry actually rendered, the set would be decoration — and
        // this is precisely the assertion that would have caught L2-231 shipping
        // a lone "q299" that `dc79c9b4` then invalidated by rolling back.
        for v in CalibrationViewModel.compatiblePopulationVersions {
            let vm = try model(Self.healthy(populationVersion: v))
            XCTAssertEqual(vm.populationVersionState, .matched, "version \(v)")
            XCTAssertFalse(vm.isIncompatible, "version \(v)")
            XCTAssertNil(vm.incompatibleMessage, "version \(v)")
        }
    }

    @MainActor
    func testTheCompatibleSetIsNotEmpty() {
        // An empty set refuses EVERY payload and takes the screen dark on a
        // typo — the same class of failure this whole change is about.
        XCTAssertFalse(CalibrationViewModel.compatiblePopulationVersions.isEmpty)
    }

    @MainActor
    func testTheRefusalNamesNoVersionToTheReader() throws {
        // L2-231 printed "This build reads calibration population q299, but the
        // server published q267" — unexplained jargon to every reader outside
        // this repo, and it blamed the server for a disagreement the client was
        // equally party to. The versions are diagnostic, not editorial.
        let vm = try model(Self.healthy(populationVersion: Self.unknownVersion))
        let message = try XCTUnwrap(vm.incompatibleMessage)
        XCTAssertFalse(message.contains(Self.unknownVersion), message)
        XCTAssertFalse(message.contains(Self.acceptedVersion), message)
        XCTAssertFalse(message.lowercased().contains("population"), message)
    }

    @MainActor
    func testBlankVersionIsUnverifiedRatherThanRefused() throws {
        // A whitespace-only value carries no claim. Refusing on it would let a
        // serialization quirk blank the screen — matching web's decision table.
        for blank in ["", "   "] {
            let vm = try model(Self.healthy(populationVersion: blank))
            XCTAssertEqual(vm.populationVersionState, .unverified, "blank \(blank.count)")
            XCTAssertFalse(vm.isIncompatible)
        }
    }

    @MainActor
    func testSurroundingWhitespaceDoesNotMakeAGoodVersionIncompatible() throws {
        let vm = try model(Self.healthy(populationVersion: " \(Self.acceptedVersion) "))
        XCTAssertEqual(vm.populationVersionState, .matched)
        XCTAssertFalse(vm.isIncompatible)
    }

    @MainActor
    func testAStaleAndIncompatiblePayloadRefusesRatherThanBannering() throws {
        // Poison ordering, native side. A dated "here's an older snapshot" frame
        // around numbers this build cannot label downgrades a major refusal to a
        // minor caveat. The refusal has to win.
        let vm = try model(Self.healthy(
            populationVersion: Self.unknownVersion,
            cache: #"{"status": "stale", "reason": "main_key_absent", "age_s": 34657}"#
        ))
        XCTAssertTrue(vm.isIncompatible)
    }

    @MainActor
    func testMissingVersionIsUnverifiedNotAssumedCompatible() throws {
        // A lean route-fallback payload predates the contract field. It still
        // renders — refusing every older payload would be its own dishonesty —
        // but it is never RECORDED as a verified match.
        let vm = try model(Self.healthy(populationVersion: nil))
        XCTAssertEqual(vm.populationVersionState, .unverified)
        XCTAssertNotEqual(vm.populationVersionState, .matched)
        XCTAssertFalse(vm.isIncompatible)
        XCTAssertNil(vm.populationVersion)
    }

    // MARK: - 5. Empty / failed payload

    @MainActor
    func testEmptyPayloadInventsNoNumbers() throws {
        let vm = try model("""
        {"buckets": [], "total_markets": 0, "total_outcomes": 0, "population_version": "\(Self.acceptedVersion)"}
        """)
        XCTAssertEqual(vm.cohortN, 0)
        XCTAssertEqual(vm.cohortECE, 0)
        XCTAssertTrue(vm.sources.isEmpty)
        XCTAssertTrue(vm.categories.isEmpty)
        // With no cohorts there is no ordering to state, so nothing is stated.
        XCTAssertNil(vm.activity.sentence)
        XCTAssertEqual(vm.activity.direction, .unknown)
        XCTAssertTrue(vm.smallSampleCategories.isEmpty)
    }

    @MainActor
    func testFailedLoadRendersAnEmDashRatherThanAZeroCurve() {
        // A view model that never received data must not report "0" — that is a
        // number, and a reader cannot tell it from a real one.
        let vm = CalibrationViewModel()
        XCTAssertNil(vm.data)
        XCTAssertEqual(vm.formattedCohortOutcomes, "\u{2014}")
        XCTAssertEqual(vm.formattedTotalOutcomes, "\u{2014}")
        // The hero clause keeps its noun (L2-237) so the sentence around it still
        // parses, but the count it names is the em-dash, never a fabricated 0.
        XCTAssertEqual(vm.heroPopulationText, "\u{2014} resolved predictions")
        XCTAssertFalse(vm.heroPopulationText.contains("0"), vm.heroPopulationText)
        XCTAssertFalse(vm.isStale)
        // Nothing decoded is UNVERIFIED, never a claimed match — and never an
        // "incompatible" banner either, which would blame the server for a
        // request that simply has not returned.
        XCTAssertEqual(vm.populationVersionState, .unverified)
        XCTAssertFalse(vm.isIncompatible)
    }

    // MARK: - 6. Parked category (Queue 299 contract)

    @MainActor
    func testParkedCategoryIsHeldOutAndCarriesItsDisposition() throws {
        let vm = try model(Self.healthy())
        let parked = try XCTUnwrap(vm.smallSampleCategories.first { $0.category == "cricket_ipl" })
        // Queue 299 publishes the disposition as DATA — never inferred from the
        // count, because "under the bar" and "parked after exclusions" are
        // different facts and only the server knows which one applies.
        XCTAssertTrue(parked.isParked)
        XCTAssertEqual(parked.disposition, SmallSampleCategory.parkedBelowPublishBar)
        XCTAssertEqual(parked.publishBar, 1000)
        XCTAssertEqual(parked.ece, 8.6)
        XCTAssertEqual(parked.outcomes, 812)
    }

    @MainActor
    func testParkedCategoryNeverAppearsInThePublishedCurveRows() throws {
        let vm = try model(Self.healthy())
        // The honest failure mode is a parked cohort quietly reappearing in the
        // published breakdown, where it reads as a graded, stood-behind curve.
        XCTAssertFalse(vm.categories.contains("cricket"))
        XCTAssertFalse(vm.categoryRows.contains { $0.category == "cricket" })
        // ...and equally, it must not vanish: it is accounted for in the held-out
        // list with its real count.
        XCTAssertTrue(vm.smallSampleCategories.contains { $0.category == "cricket_ipl" })
    }

    @MainActor
    func testUnmarkedSmallSampleCategoryIsNotClaimedAsParked() throws {
        // An older payload carries category + outcomes only. Absent a declared
        // disposition, native must not assert Queue 299's one on its behalf.
        let vm = try model(Self.healthy())
        let esports = try XCTUnwrap(vm.smallSampleCategories.first { $0.category == "esports" })
        XCTAssertNil(esports.disposition)
        XCTAssertFalse(esports.isParked)
        XCTAssertNil(esports.publishBar)
    }
}
