import XCTest
@testable import Bain_Luck

/// L2-231 (re-staged) — native calibration AVAILABILITY and COUNT truth.
///
/// `CalibrationSurfaceTests` proves the surface tells the truth about WHICH
/// payload it is rendering (dated last-good, version mismatch, parked category).
/// This suite proves the two things that sat underneath it and were never
/// exercised:
///
///   1. **Availability.** Every state between "a perfect payload" and "no
///      response" — one malformed bucket among sixteen hundred, a missing
///      `buckets` key, an empty array, a cancelled fetch, a refresh that failed
///      over good numbers. Each of those used to end in a generic error screen,
///      a discarded curve, or — worst — a rendered `0.0pp "Excellent"` assembled
///      out of no data.
///
///   2. **Count truth.** `price_moved` is a TRI-state, and the surface modelled
///      it as a boolean. On the frozen production payload the two rendered
///      cohorts summed to 612,332 against a stated population of 652,407, with
///      the 40,075 missing rows named nowhere and folded silently into a cohort
///      whose printed description does not describe them.
///
/// Every arithmetic assertion below runs against `CalibrationProdFixture` — one
/// real server response — with expected values computed independently from the
/// full 340 KB payload rather than read back out of this implementation.
final class CalibrationAvailabilityTests: XCTestCase {

    // MARK: - Helpers

    private func decode(_ json: String) throws -> CalibrationData {
        let dec = JSONDecoder()
        dec.keyDecodingStrategy = .convertFromSnakeCase
        return try dec.decode(CalibrationData.self, from: Data(json.utf8))
    }

    @MainActor
    private func model(_ json: String) throws -> CalibrationViewModel {
        CalibrationViewModel(preloaded: try decode(json))
    }

    @MainActor
    private func prodModel() throws -> CalibrationViewModel {
        try model(CalibrationProdFixture.json)
    }

    /// Grouped-decimal formatting, configured exactly as the view model's is.
    ///
    /// The assertions below are about WHICH COUNT a sentence names, not about
    /// digit-grouping conventions. Hard-coding `"349,310"` would make every one
    /// of them fail on a device whose locale groups differently — a test bug
    /// wearing a rendering bug's clothes.
    private func fmt(_ n: Int) -> String {
        let f = NumberFormatter(); f.numberStyle = .decimal
        return f.string(from: NSNumber(value: n)) ?? "\(n)"
    }

    // Expected values, computed from the FULL production payload with an
    // independent implementation of the web page's aggregation (sum n / winners /
    // sum_prob into bucket_idx bins; round to 0.1 before differencing) — not read
    // back from `CalibrationMath`. A shared bug would otherwise agree with itself.
    //
    // Written at full double precision on purpose, and compared at 1e-12. The
    // first draft of this table carried six printed decimals padded out to eight,
    // and the five Brier assertions failed on the invented digits. Numbers that
    // are quoted as measured have to BE measured, all the way down.
    private enum Prod {
        static let fullN = 652_407
        static let movedN = 349_310
        static let unchangedN = 263_022
        static let notApplicableN = 40_075
        static let cohortN = 389_385          // moved + not-applicable
        static let cohortECE = 1.5425470934935861
        static let cohortMCE = 1.45
        static let cohortBrier = 0.16493497335541943
        static let allECE = 1.2614602541051827
        static let allMCE = 1.24
        static let allBrier = 0.16375538337264928
        static let movedECE = 1.716231141393032
        static let unchangedECE = 1.0341499950574478
        static let notApplicableECE = 0.28600873362445417
        /// source -> (n, ece, mce, brier) within the default (price-moved) cohort.
        static let sourceRows: [String: (n: Int, ece: Double, mce: Double, brier: Double)] = [
            "kalshi": (267_121, 1.0553928743902576, 1.1400000000000001, 0.16024782177365315),
            "polymarket": (82_189, 4.8175351932740389, 4.29, 0.14606055554879607),
            "odds_api": (14_960, 1.3532018716577541, 1.1199999999999999, 0.21266273395721924),
            "odds_api_spreads": (12_410, 0.64699435938759065, 11.029999999999999, 0.24745518130539887),
            "odds_api_totals": (12_705, 1.1074065328610783, 16.4375, 0.24877779614325068),
        ]
    }

    // MARK: - 1. The frozen production payload decodes and is labellable

    @MainActor
    func testProductionPayloadDecodesCleanlyWithNoDroppedBuckets() throws {
        let vm = try prodModel()
        XCTAssertEqual(vm.droppedBuckets, 0, "the real payload must decode whole")
        XCTAssertNil(vm.partialDataNote)
        XCTAssertTrue(vm.hasRenderableCurve)
        XCTAssertNil(vm.unavailableMessage)
    }

    @MainActor
    func testShippedCompatibleSetAcceptsThePopulationProductionActuallyPublishes() throws {
        // The set is only worth having if it matches reality. L2-232 shipped a
        // one-entry set after a lone hard-coded version took the screen dark;
        // this is the assertion that catches the set drifting off the server.
        XCTAssertTrue(
            CalibrationViewModel.compatiblePopulationVersions
                .contains(CalibrationProdFixture.publishedPopulationVersion),
            "compatible set \(CalibrationViewModel.compatiblePopulationVersions) rejects the "
                + "published population \(CalibrationProdFixture.publishedPopulationVersion)"
        )
        let vm = try prodModel()
        XCTAssertEqual(vm.populationVersionState, .matched)
        XCTAssertFalse(vm.isIncompatible)
    }

    @MainActor
    func testProductionPayloadWasServedStaleAndIsRenderedAsDatedNotCurrent() throws {
        // This is not a hypothetical: the 2026-08-02 response carried
        // `cache.status = "stale", reason = "main_key_absent", age_s = 86461`.
        XCTAssertEqual(CalibrationProdFixture.servedCacheStatus, "stale")
        let vm = try prodModel()
        XCTAssertTrue(vm.isStale)
        let detail = try XCTUnwrap(vm.staleBannerDetail)
        XCTAssertTrue(detail.contains("24h ago"), detail)
        XCTAssertFalse(detail.contains("earlier"), detail)
        // Stale is a freshness state, not a refusal — the curve still renders.
        XCTAssertTrue(vm.hasRenderableCurve)
    }

    // MARK: - 2. The count bridge (Item 2)

    @MainActor
    func testActivityPartitionIsCompleteAndSumsToThePopulation() throws {
        let vm = try prodModel()
        XCTAssertEqual(vm.movedN, Prod.movedN)
        XCTAssertEqual(vm.unchangedN, Prod.unchangedN)
        XCTAssertEqual(vm.notApplicableN, Prod.notApplicableN)
        // The invariant the surface could not previously state: the three
        // activity states partition the population exactly.
        XCTAssertEqual(vm.movedN + vm.unchangedN + vm.notApplicableN, vm.fullN)
        XCTAssertEqual(vm.fullN, Prod.fullN)
        // ...and the shortfall that proves it was worth asserting.
        XCTAssertEqual(vm.movedN + vm.unchangedN, 612_332)
        XCTAssertNotEqual(vm.movedN + vm.unchangedN, vm.fullN)
    }

    @MainActor
    func testCohortCountBridgeReconcilesWithTheHeadlineTotal() throws {
        let vm = try prodModel()
        // The default cohort is `price_moved != false` = moved + not-applicable.
        XCTAssertEqual(vm.cohortN, Prod.cohortN)
        XCTAssertEqual(vm.cohortN, vm.movedN + vm.notApplicableN)
        XCTAssertEqual(vm.wellTradedN, vm.cohortN)
        // The toggle's "+N" is exactly the price-unchanged cohort.
        XCTAssertEqual(vm.thinAddN, vm.unchangedN)
        XCTAssertEqual(vm.cohortN + vm.thinAddN, vm.fullN)
        // The bucket sum must equal the server's own stated total — a mismatch
        // means the curve and the headline are describing different populations.
        XCTAssertEqual(vm.data?.totalOutcomes, vm.fullN)

        vm.includeThin = true
        XCTAssertEqual(vm.cohortN, vm.fullN)
        XCTAssertEqual(vm.thinAddN, vm.unchangedN, "thinAddN is cohort-independent")
    }

    @MainActor
    func testCohortAndActivityMetricsMatchTheIndependentlyComputedProductionValues() throws {
        let vm = try prodModel()
        XCTAssertEqual(vm.cohortECE, Prod.cohortECE, accuracy: 1e-12)
        XCTAssertEqual(vm.cohortMCE, Prod.cohortMCE, accuracy: 1e-12)
        XCTAssertEqual(vm.cohortBrier, Prod.cohortBrier, accuracy: 1e-12)
        XCTAssertEqual(vm.movedECE, Prod.movedECE, accuracy: 1e-12)
        XCTAssertEqual(vm.unchangedECE, Prod.unchangedECE, accuracy: 1e-12)
        XCTAssertEqual(
            CalibrationMath.ece(CalibrationMath.aggregate(vm.data?.buckets ?? []) { $0.priceMoved == nil }),
            Prod.notApplicableECE, accuracy: 1e-12
        )

        vm.includeThin = true
        XCTAssertEqual(vm.cohortECE, Prod.allECE, accuracy: 1e-12)
        XCTAssertEqual(vm.cohortMCE, Prod.allMCE, accuracy: 1e-12)
        XCTAssertEqual(vm.cohortBrier, Prod.allBrier, accuracy: 1e-12)
    }

    @MainActor
    func testPerSourceRowsMatchTheIndependentlyComputedProductionValues() throws {
        let vm = try prodModel()
        let rows = vm.sourceRows
        XCTAssertEqual(rows.count, Prod.sourceRows.count)
        for row in rows {
            let expected = try XCTUnwrap(Prod.sourceRows[row.source], "unexpected source \(row.source)")
            XCTAssertEqual(row.n, expected.n, "n for \(row.source)")
            XCTAssertEqual(row.ece, expected.ece, accuracy: 1e-12, "ECE for \(row.source)")
            XCTAssertEqual(row.mce, expected.mce, accuracy: 1e-12, "MCE for \(row.source)")
            XCTAssertEqual(row.brier, expected.brier, accuracy: 1e-12, "Brier for \(row.source)")
        }
        // Rows are the cohort's, so they must add up to the cohort, not the total.
        XCTAssertEqual(rows.reduce(0) { $0 + $1.n }, vm.cohortN)
    }

    @MainActor
    func testActivityDirectionOnTheProductionPayloadNamesTheHigherErrorCohort() throws {
        let vm = try prodModel()
        let activity = vm.activity
        XCTAssertEqual(activity.direction, .movedHigher)
        XCTAssertEqual(activity.movedText, "1.7")
        XCTAssertEqual(activity.unchangedText, "1.0")
        XCTAssertEqual(activity.ratioText, "1.7")
        let sentence = try XCTUnwrap(activity.sentence)
        XCTAssertTrue(sentence.contains("price-moved cohort carries the higher calibration error"))
        XCTAssertFalse(sentence.localizedCaseInsensitiveContains("more accurately calibrated"))
    }

    // MARK: - 3. The cohort label must match its predicate (Item 2 / L2-237)

    @MainActor
    func testDefaultCohortDetailDoesNotClaimTradingMovedTheNotApplicableRows() throws {
        let vm = try prodModel()
        XCTAssertGreaterThan(vm.notApplicableN, 0)
        let detail = vm.cohortDetail
        // The shipped sentence, verbatim. It described 389,385 rows as "where
        // real trading moved the price" when 40,075 of them carry no such flag.
        XCTAssertNotEqual(detail, "Where real trading moved the price. Thin markets can be noisy.")
        XCTAssertFalse(detail.hasPrefix("Where real trading moved the price"), detail)
        // Both halves of the cohort are named, with their counts...
        XCTAssertTrue(detail.contains(fmt(Prod.movedN)), detail)
        XCTAssertTrue(detail.contains(fmt(Prod.notApplicableN)), detail)
        XCTAssertTrue(detail.localizedCaseInsensitiveContains("doesn't apply"), detail)
        // ...and so is the third one, which the cohort excludes.
        XCTAssertTrue(detail.contains("Excluded: \(fmt(Prod.unchangedN)) outcomes"), detail)
    }

    /// L2-237 — the residual divergence L2-231 deferred and L2-236 decided.
    ///
    /// L2-231 fixed the CLAIM under the cohort on native and kept the NAME
    /// "well-traded", because the name was web's; renaming it on one surface
    /// would have manufactured a second divergence. L2-236 renamed it on web:
    /// "well-traded" is a LIQUIDITY claim over a MOVEMENT predicate, and the
    /// excluded side is not thin or untraded — those rows traded and never moved,
    /// and zero-bid outcomes are excluded upstream. This is native's half, and
    /// the strings below are web's `describeCohort` output word for word.
    @MainActor
    func testTheCohortNameIsThePredicateOnBothSurfaces() throws {
        let vm = try prodModel()
        XCTAssertEqual(
            vm.cohortHeadline,
            "Showing markets whose price moved, plus sportsbook lines (\(fmt(Prod.cohortN)))")
        XCTAssertEqual(vm.cohortShortLabel, "Price moved + sportsbook lines")
        XCTAssertEqual(vm.cohortToggleLabel, "Include never-moved (+\(fmt(Prod.unchangedN)))")
        XCTAssertEqual(
            vm.heroPopulationText,
            "\(fmt(Prod.cohortN)) resolved predictions \u{2014} every outcome except the "
                + "\(fmt(Prod.unchangedN)) whose price never moved off its opening line "
                + "(\(fmt(Prod.fullN)) in total)")

        vm.includeThin = true
        XCTAssertEqual(vm.cohortHeadline, "Showing all markets (\(fmt(Prod.fullN)))")
        XCTAssertEqual(vm.cohortShortLabel, "All markets")
        XCTAssertEqual(vm.cohortToggleLabel, "Exclude never-moved")
        XCTAssertEqual(vm.heroPopulationText, "\(fmt(Prod.fullN)) resolved predictions")
    }

    /// The guard, not the assertion: sweep EVERY cohort-facing string in both
    /// toggle states for the vocabulary this queue removed. A single-string
    /// assertion is satisfied by moving the claim one label to the left.
    @MainActor
    func testNoCohortStringMakesALiquidityClaim() throws {
        let vm = try prodModel()
        // "thin" is deliberately NOT bare: it is a substring of "within", and a
        // guard that fails on an innocent word gets deleted rather than fixed.
        let banned = ["well-traded", "well traded", "thinly", "thin markets",
                      "include thin", "untraded", "illiquid"]
        for includeNeverMoved in [false, true] {
            vm.includeThin = includeNeverMoved
            let strings: [(String, String)] = [
                ("headline", vm.cohortHeadline),
                ("detail", vm.cohortDetail),
                ("shortLabel", vm.cohortShortLabel),
                ("toggleLabel", vm.cohortToggleLabel),
                ("toggleA11y", vm.cohortToggleAccessibilityLabel),
                ("hero", vm.heroPopulationText),
                ("partitionNote", vm.activityPartitionNote ?? ""),
            ]
            for (name, value) in strings {
                for word in banned {
                    XCTAssertFalse(
                        value.localizedCaseInsensitiveContains(word),
                        "\(name) (includeNeverMoved=\(includeNeverMoved)) still claims "
                            + "\"\(word)\": \(value)")
                }
            }
        }
    }

    /// The accessibility reading of the toggle names what it acts on. The visible
    /// capsule is a two-word verb phrase; VoiceOver reads the button alone.
    @MainActor
    func testTheCohortToggleReadsItsTargetToVoiceOver() throws {
        let vm = try prodModel()
        XCTAssertEqual(
            vm.cohortToggleAccessibilityLabel,
            "Include the \(fmt(Prod.unchangedN)) outcomes whose price never moved off its opening line")
        vm.includeThin = true
        XCTAssertEqual(
            vm.cohortToggleAccessibilityLabel,
            "Exclude the \(fmt(Prod.unchangedN)) outcomes whose price never moved off its opening line")
    }

    // The arithmetic under these labels is asserted against the same production
    // fixture by `testCohortCountBridgeReconcilesWithTheHeadlineTotal` and
    // `testCohortAndActivityMetricsMatchTheIndependentlyComputedProductionValues`
    // above — a rename that moved a population would go red there, so it is not
    // re-asserted here.

    @MainActor
    func testDefaultCohortDetailKeepsTheSimpleSentenceWhenEveryRowReallyIsTraded() throws {
        // No not-applicable rows means the original claim is true, so it stands.
        // A caveat that appears on payloads it does not describe is noise.
        let vm = try model("""
        {"population_version": "\(CalibrationProdFixture.publishedPopulationVersion)",
         "total_markets": 2, "total_outcomes": 300,
         "buckets": [
           {"bucket_idx": 2, "source": "kalshi", "category": "politics", "price_moved": true, "n": 200, "winners": 60, "sum_prob": 50.0, "sum_sq_err": 44.0},
           {"bucket_idx": 5, "source": "kalshi", "category": "politics", "price_moved": false, "n": 100, "winners": 55, "sum_prob": 55.0, "sum_sq_err": 24.0}
         ]}
        """)
        XCTAssertEqual(vm.notApplicableN, 0)
        // Nothing is folded in that the plain claim does not cover, so it stands
        // — measured rather than assumed. The excluded side is still named.
        XCTAssertEqual(
            vm.cohortDetail,
            "Every outcome whose price real trading moved. Excluded: 100 outcomes whose "
                + "price never moved off its opening line.")
        // ...and with no sportsbook rows the name drops the clause about them.
        XCTAssertEqual(vm.cohortHeadline, "Showing markets whose price moved (200)")
        XCTAssertEqual(vm.cohortShortLabel, "Price moved")
        XCTAssertNil(vm.activityPartitionNote)
    }

    @MainActor
    func testIncludeThinDetailPublishesTheWholePartition() throws {
        let vm = try prodModel()
        vm.includeThin = true
        let detail = vm.cohortDetail
        XCTAssertTrue(detail.contains("\(fmt(Prod.movedN)) price moved"), detail)
        XCTAssertTrue(detail.contains("\(fmt(Prod.unchangedN)) price unchanged"), detail)
        XCTAssertTrue(detail.contains("\(fmt(Prod.notApplicableN)) not applicable"), detail)
        // The third term says WHICH rows are not applicable, matching web.
        XCTAssertTrue(detail.contains("not applicable (sportsbook lines)"), detail)
        // The shipped prefix asserted a property of the added rows that nothing
        // measured — they are the rows that never moved, not the untraded ones.
        XCTAssertFalse(detail.hasPrefix("Including thin / untraded"), detail)
    }

    @MainActor
    func testActivityPartitionNoteReconcilesTheTwoCardsWithThePopulation() throws {
        let vm = try prodModel()
        let note = try XCTUnwrap(vm.activityPartitionNote)
        XCTAssertTrue(note.contains(fmt(Prod.notApplicableN)), note)
        XCTAssertTrue(note.contains("\(fmt(Prod.movedN)) + \(fmt(Prod.unchangedN)) + \(fmt(Prod.notApplicableN)) = \(fmt(Prod.fullN))"), note)
        // The arithmetic in the sentence must be the arithmetic in the model.
        XCTAssertEqual(vm.movedN + vm.unchangedN + vm.notApplicableN, vm.fullN)
    }

    // MARK: - 4. Per-item decode containment (Item 1)

    /// Two good buckets and one poison one, at every position in the array.
    ///
    /// The failure this replaces: `buckets` was a non-optional array of a struct
    /// with no optional numeric fields, so ONE null `n` among ~1,600 rows threw
    /// out of `JSONDecoder` and the whole screen became a generic error.
    @MainActor
    func testOnePoisonBucketDoesNotDestroyTheOtherFifteenHundred() throws {
        let good1 = #"{"bucket_idx": 2, "source": "kalshi", "category": "politics", "price_moved": true, "n": 200, "winners": 60, "sum_prob": 50.0, "sum_sq_err": 44.0}"#
        let good2 = #"{"bucket_idx": 5, "source": "kalshi", "category": "politics", "price_moved": false, "n": 100, "winners": 55, "sum_prob": 55.0, "sum_sq_err": 24.0}"#
        let poisons = [
            "null-n": #"{"bucket_idx": 3, "source": "kalshi", "category": "politics", "price_moved": true, "n": null, "winners": 1, "sum_prob": 1.0, "sum_sq_err": 1.0}"#,
            "missing-winners": #"{"bucket_idx": 3, "source": "kalshi", "category": "politics", "price_moved": true, "n": 5, "sum_prob": 1.0, "sum_sq_err": 1.0}"#,
            "string-n": #"{"bucket_idx": 3, "source": "kalshi", "category": "politics", "price_moved": true, "n": "many", "winners": 1, "sum_prob": 1.0, "sum_sq_err": 1.0}"#,
            "not-an-object": #""garbage""#,
            "json-null": "null",
            "nested-array": "[1, 2, 3]",
        ]
        let positions = ["first", "middle", "last"]

        for (label, poison) in poisons {
            for position in positions {
                let rows: [String]
                switch position {
                case "first": rows = [poison, good1, good2]
                case "middle": rows = [good1, poison, good2]
                default: rows = [good1, good2, poison]
                }
                let name = "\(label)/\(position)"
                let vm = try model("""
                {"population_version": "\(CalibrationProdFixture.publishedPopulationVersion)",
                 "total_markets": 2, "total_outcomes": 300,
                 "buckets": [\(rows.joined(separator: ","))]}
                """)
                XCTAssertEqual(vm.data?.buckets.count, 2, "kept buckets for \(name)")
                XCTAssertEqual(vm.droppedBuckets, 1, "dropped count for \(name)")
                XCTAssertTrue(vm.hasRenderableCurve, "curve must survive \(name)")
                XCTAssertNil(vm.unavailableMessage, "\(name) must not blank the screen")
                // The two survivors are the ones that were kept — position of the
                // poison must not change WHICH rows come through.
                XCTAssertEqual(vm.movedN, 200, "moved n for \(name)")
                XCTAssertEqual(vm.unchangedN, 100, "unchanged n for \(name)")
                // ...and the loss is stated, never silent.
                let note = try XCTUnwrap(vm.partialDataNote, "partial note for \(name)")
                XCTAssertTrue(note.contains("1 of 3"), "\(name): \(note)")
            }
        }
    }

    @MainActor
    func testManyPoisonBucketsTerminateAndAreAllCounted() throws {
        // A malformed element must ADVANCE the decoder's cursor. Decoding an
        // element with `try?` directly does not reliably do that, which turns a
        // bad row into a hang rather than a dropped row. 200 of them, so a
        // non-advancing cursor cannot pass by luck.
        let poison = #"{"bucket_idx": 3, "source": "kalshi", "category": "politics", "price_moved": true, "n": null}"#
        let rows = Array(repeating: poison, count: 200).joined(separator: ",")
        let vm = try model("""
        {"population_version": "\(CalibrationProdFixture.publishedPopulationVersion)",
         "total_markets": 0, "total_outcomes": 0, "buckets": [\(rows)]}
        """)
        XCTAssertEqual(vm.droppedBuckets, 200)
        XCTAssertTrue(vm.data?.buckets.isEmpty == true)
        // Nothing readable came back, so this is an unavailable state — NOT a
        // 0.0pp "Excellent" curve drawn over an empty bucket list.
        XCTAssertFalse(vm.hasRenderableCurve)
        let message = try XCTUnwrap(vm.unavailableMessage)
        XCTAssertTrue(message.localizedCaseInsensitiveContains("empty"), message)
    }

    @MainActor
    func testSmallSampleAndCorrectionRowsAreContainedIndividually() throws {
        let vm = try model("""
        {"population_version": "\(CalibrationProdFixture.publishedPopulationVersion)",
         "total_markets": 2, "total_outcomes": 300,
         "buckets": [{"bucket_idx": 2, "source": "kalshi", "category": "politics", "price_moved": true, "n": 200, "winners": 60, "sum_prob": 50.0, "sum_sq_err": 44.0}],
         "small_sample_categories": [
           {"category": "cricket_ipl", "outcomes": 812},
           {"category": "broken"},
           {"category": "esports", "outcomes": 500}
         ],
         "corrections": [
           {"date": "2026-07-09", "title": "ok", "description": "kept"},
           {"title": "no date", "description": "dropped"},
           {"date": "2026-07-10", "title": "ok2", "description": "kept"}
         ]}
        """)
        XCTAssertEqual(vm.smallSampleCategories.count, 2)
        XCTAssertEqual(vm.smallSampleCategories.map(\.category), ["cricket_ipl", "esports"])
        XCTAssertEqual(vm.corrections.count, 2)
        XCTAssertEqual(vm.corrections.map(\.title), ["ok", "ok2"])
    }

    // MARK: - 5. Missing, extra and malformed top-level fields (Item 1)

    @MainActor
    func testAnUnreadableTopLevelFieldIsUnknownRatherThanZero() throws {
        // The old synthesized decode made `total_outcomes` required, so a string
        // there killed the payload. Making it optional-and-lenient must not swing
        // to the other failure: printing `0` for a number nobody measured.
        let vm = try model("""
        {"population_version": "\(CalibrationProdFixture.publishedPopulationVersion)",
         "total_markets": "lots", "total_outcomes": "loads",
         "buckets": [{"bucket_idx": 2, "source": "kalshi", "category": "politics", "price_moved": true, "n": 200, "winners": 60, "sum_prob": 50.0, "sum_sq_err": 44.0}]}
        """)
        XCTAssertNil(vm.data?.totalOutcomes)
        XCTAssertNil(vm.data?.totalMarkets)
        XCTAssertEqual(vm.formattedTotalOutcomes, "\u{2014}")
        XCTAssertEqual(vm.formattedMarkets, "\u{2014}")
        XCTAssertNotEqual(vm.formattedTotalOutcomes, "0")
        // The buckets are fine, so the curve renders.
        XCTAssertTrue(vm.hasRenderableCurve)
        XCTAssertEqual(vm.cohortN, 200)
    }

    @MainActor
    func testUnknownExtraFieldsAreIgnoredRatherThanFatal() throws {
        let vm = try model("""
        {"population_version": "\(CalibrationProdFixture.publishedPopulationVersion)",
         "total_markets": 1, "total_outcomes": 200,
         "a_field_from_a_later_backend": {"nested": [1, 2, 3]},
         "another": "surprise",
         "buckets": [{"bucket_idx": 2, "source": "kalshi", "category": "politics", "price_moved": true, "n": 200, "winners": 60, "sum_prob": 50.0, "sum_sq_err": 44.0, "future_column": 7}]}
        """)
        XCTAssertTrue(vm.hasRenderableCurve)
        XCTAssertEqual(vm.droppedBuckets, 0)
        XCTAssertEqual(vm.cohortN, 200)
    }

    /// `buckets` absent vs `buckets: []` are different facts and must read
    /// differently — one is "we could not read it", one is "there is nothing yet".
    @MainActor
    func testMissingUnreadableAndEmptyBucketsAreDistinguished() throws {
        struct Case { let name: String; let json: String; let present: Bool; let phrase: String }
        let version = CalibrationProdFixture.publishedPopulationVersion
        let cases = [
            Case(name: "key absent",
                 json: #"{"population_version": "\#(version)", "total_markets": 1, "total_outcomes": 200}"#,
                 present: false, phrase: "couldn't read"),
            Case(name: "object instead of array",
                 json: #"{"population_version": "\#(version)", "buckets": {"oops": 1}}"#,
                 present: false, phrase: "couldn't read"),
            Case(name: "string instead of array",
                 json: #"{"population_version": "\#(version)", "buckets": "none"}"#,
                 present: false, phrase: "couldn't read"),
            Case(name: "served empty",
                 json: #"{"population_version": "\#(version)", "buckets": [], "total_outcomes": 0}"#,
                 present: true, phrase: "came back empty"),
        ]
        for c in cases {
            let vm = try model(c.json)
            XCTAssertEqual(vm.data?.bucketsPresent, c.present, "bucketsPresent for \(c.name)")
            XCTAssertFalse(vm.hasRenderableCurve, "\(c.name) must have no curve")
            let message = try XCTUnwrap(vm.unavailableMessage, "message for \(c.name)")
            XCTAssertTrue(message.localizedCaseInsensitiveContains(c.phrase), "\(c.name): \(message)")
            // The honest states never coexist with a manufactured metric.
            XCTAssertEqual(vm.cohortN, 0)
            XCTAssertEqual(vm.formattedCohortOutcomes, "0")
        }
    }

    @MainActor
    func testAVersionMismatchOutranksAnEmptyPayload() throws {
        // Poison ordering: if both apply, the refusal must win — "there's nothing
        // to plot" invites a retry, while "we can't label what the server sent"
        // is the fact.
        let vm = try model(#"{"population_version": "q999-not-a-real-population", "buckets": []}"#)
        XCTAssertTrue(vm.isIncompatible)
        XCTAssertNil(vm.unavailableMessage)
        XCTAssertNotNil(vm.incompatibleMessage)
    }

    // MARK: - 6. Load lifecycle (Item 1)

    private struct StubError: Error, LocalizedError {
        var errorDescription: String? { "the network is having a moment" }
    }

    @MainActor
    private func payload() throws -> CalibrationData {
        try decode(CalibrationProdFixture.json)
    }

    @MainActor
    func testFirstLoadFailureShowsAnErrorAndNeverASpinnerForever() async throws {
        let vm = CalibrationViewModel(fetcher: { throw StubError() })
        await vm.load()
        XCTAssertFalse(vm.loading, "an infinite spinner is its own failure state")
        XCTAssertEqual(vm.error, StubError().errorDescription)
        XCTAssertNil(vm.data)
        XCTAssertFalse(vm.refreshFailed)
    }

    @MainActor
    func testRefreshFailureKeepsTheRenderedCurveAndStopsCallingItCurrent() async throws {
        let good = try payload()
        var shouldFail = false
        let vm = CalibrationViewModel(preloaded: good, fetcher: {
            if shouldFail { throw StubError() }
            return good
        })
        shouldFail = true

        await vm.load()

        // The whole point: the numbers are still there.
        XCTAssertNotNil(vm.data)
        XCTAssertEqual(vm.cohortN, Prod.cohortN)
        XCTAssertTrue(vm.hasRenderableCurve)
        // ...and they are no longer presented as current.
        XCTAssertTrue(vm.refreshFailed)
        let note = try XCTUnwrap(vm.refreshFailureNote)
        XCTAssertTrue(note.localizedCaseInsensitiveContains("couldn't refresh"), note)
        XCTAssertTrue(note.contains("Aug"), "the note must date the numbers it kept: \(note)")
        // A full-screen error over a readable curve is what this replaces.
        XCTAssertNil(vm.error)
        XCTAssertFalse(vm.loading)
    }

    @MainActor
    func testRefreshRecoveryClearsTheFailureNote() async throws {
        let good = try payload()
        var shouldFail = true
        let vm = CalibrationViewModel(preloaded: good, fetcher: {
            if shouldFail { throw StubError() }
            return good
        })
        await vm.load()
        XCTAssertTrue(vm.refreshFailed)

        shouldFail = false
        await vm.load()

        XCTAssertFalse(vm.refreshFailed)
        XCTAssertNil(vm.refreshFailureNote)
        XCTAssertNil(vm.error)
        XCTAssertTrue(vm.hasRenderableCurve)
    }

    @MainActor
    func testCancellationIsNotReportedAsAFailure() async throws {
        // SwiftUI cancels a `.task` whenever the user leaves the tab mid-fetch.
        // Reporting that as a server error is a lie about a routine gesture.
        for error in [CancellationError() as Error, URLError(.cancelled) as Error] {
            let vm = CalibrationViewModel(fetcher: { throw error })
            await vm.load()
            XCTAssertNil(vm.error, "cancellation surfaced as an error: \(error)")
            XCTAssertFalse(vm.loading)
            XCTAssertFalse(vm.refreshFailed)
            // Nothing was loaded and nothing pretended otherwise: the surface
            // lands on the honest "try again" state, not on a 0.0pp curve.
            XCTAssertFalse(vm.hasRenderableCurve)
            let message = try XCTUnwrap(vm.unavailableMessage)
            XCTAssertTrue(message.localizedCaseInsensitiveContains("try again"), message)
        }
    }

    @MainActor
    func testCancellingARefreshLeavesTheRenderedCurveUntouched() async throws {
        let good = try payload()
        let vm = CalibrationViewModel(preloaded: good, fetcher: { throw CancellationError() })
        await vm.load()
        XCTAssertEqual(vm.cohortN, Prod.cohortN)
        XCTAssertNil(vm.error)
        XCTAssertFalse(vm.refreshFailed, "a cancelled refresh is not a failed refresh")
        XCTAssertNil(vm.refreshFailureNote)
    }

    @MainActor
    func testLoadIfNeededDoesNotRefetchOrFlashASpinnerOverExistingData() async throws {
        let good = try payload()
        var calls = 0
        let vm = CalibrationViewModel(preloaded: good, fetcher: { calls += 1; return good })
        await vm.loadIfNeeded()
        XCTAssertEqual(calls, 0, "re-entering the tab must not refetch")
        XCTAssertFalse(vm.loading)
        XCTAssertTrue(vm.hasRenderableCurve)
    }

    @MainActor
    func testAnExplicitRefreshOverExistingDataNeverBlanksToASpinner() async throws {
        let good = try payload()
        let vm = CalibrationViewModel(preloaded: good, fetcher: { good })
        await vm.load()
        XCTAssertFalse(vm.loading)
        XCTAssertTrue(vm.hasRenderableCurve)
    }
}
