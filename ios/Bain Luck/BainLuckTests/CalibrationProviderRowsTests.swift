import XCTest
@testable import Bain_Luck

/// #8485 — the phone's Source Comparison tells the website's story.
///
/// Photographed 2026-09-24 on the live payload, same minute: web drew ONE
/// "Sportsbooks (Odds API)" row (155,127 outcomes, 1.1pp); the phone drew the
/// four Odds API keys as four rows and ranked "Spreads (Odds API)" FIRST at
/// 0.3pp — a composition effect over a 14.9pp per-bucket error — above Kalshi.
/// And under the traded 0.9pp it printed "95% CI: 0.3–1.2pp", the interval of
/// the whole 747,028 (#7374).
final class CalibrationProviderRowsTests: XCTestCase {

    /// Spreads shaped the way production has it: a big bucket just under the
    /// diagonal and a small one far over it, so its n-weighted ECE is tiny and
    /// its per-bucket mean is huge. As its OWN row it would rank first.
    static let spreadsShapedPayload: String = {
        let version = CalibrationRenderSmokeTests.renderableVersion
        return """
        {
          "population_version": "\(version)",
          "total_markets": 10, "total_outcomes": 2600, "total_winners": 1000,
          "generated_at": "2026-09-24T23:00:00+00:00",
          "mce_ci_lower": 0.33, "mce_ci_upper": 1.19,
          "buckets": [
            {"bucket_idx": 4, "source": "kalshi", "category": "baseball", "price_moved": true,
             "n": 1000, "winners": 440, "sum_prob": 450.0, "sum_sq_err": 240.0},
            {"bucket_idx": 4, "source": "odds_api_bookmaker", "category": "baseball", "price_moved": null,
             "n": 600, "winners": 240, "sum_prob": 270.0, "sum_sq_err": 150.0},
            {"bucket_idx": 4, "source": "odds_api_spreads", "category": "baseball", "price_moved": null,
             "n": 400, "winners": 200, "sum_prob": 200.4, "sum_sq_err": 100.0},
            {"bucket_idx": 9, "source": "odds_api_spreads", "category": "baseball", "price_moved": null,
             "n": 2, "winners": 0, "sum_prob": 1.9, "sum_sq_err": 1.8},
            {"bucket_idx": 6, "source": "kalshi", "category": "baseball", "price_moved": false,
             "n": 596, "winners": 390, "sum_prob": 387.4, "sum_sq_err": 130.0}
          ]
        }
        """
    }()

    @MainActor
    private func model() throws -> CalibrationViewModel {
        let dec = JSONDecoder()
        dec.keyDecodingStrategy = .convertFromSnakeCase
        return CalibrationViewModel(
            preloaded: try dec.decode(CalibrationData.self, from: Data(Self.spreadsShapedPayload.utf8)))
    }

    /// The specimen, end to end: one sportsbook row, and Spreads is not ranked.
    @MainActor
    func testSportsbooksAreOneRowAndSpreadsIsNotRankedOnItsOwn() throws {
        let vm = try model()
        let rows = vm.sourceRows
        let buckets = try XCTUnwrap(vm.data).buckets
        XCTAssertEqual(rows.map(\.source).sorted(), ["kalshi", "odds_api_family"],
                       "one row per provider, as web draws it; got \(rows.map(\.name))")
        XCTAssertFalse(rows.contains { $0.name.hasPrefix("Spreads") },
                       "a shape is never ranked as if it were a provider")

        // The control: as a raw key Spreads WOULD have led the table, so the
        // assertion above is about the grouping and not about this fixture.
        let spreadsAlone = CalibrationMath.ece(CalibrationMath.aggregate(buckets) {
            $0.source == "odds_api_spreads"
        })
        let kalshi = try XCTUnwrap(rows.first { $0.source == "kalshi" }?.ece)
        XCTAssertLessThan(spreadsAlone, kalshi, "the control must be a Spreads-leads payload")

        let family = try XCTUnwrap(rows.first { $0.source == "odds_api_family" })
        XCTAssertEqual(family.name, "Sportsbooks (Odds API)")
        XCTAssertEqual(family.memberNames, ["Per-sportsbook", "Spreads"],
                       "members named under the row without the repeated qualifier")
        XCTAssertEqual(family.n, 1002, "the pooled members' outcomes")
        // Pooled buckets, the same metric — not an average of member summaries.
        let pooled = CalibrationMath.aggregate(buckets) {
            CalibrationViewModel.providerOf($0.source) == "odds_api_family"
        }
        XCTAssertEqual(try XCTUnwrap(family.ece), CalibrationMath.ece(pooled), accuracy: 1e-12)
        XCTAssertEqual(try XCTUnwrap(family.mce), CalibrationMath.mce(pooled), accuracy: 1e-12)
        XCTAssertEqual(rows.reduce(0) { $0 + $1.n }, vm.cohortN)
    }

    /// Kalshi and Polymarket are one-member providers, not exemptions, and an
    /// unknown key is its own provider.
    @MainActor
    func testProviderOfIsTotalAndOnlyFoldsTheOddsApiFamily() {
        XCTAssertEqual(CalibrationViewModel.providerOf("odds_api"), "odds_api_family")
        XCTAssertEqual(CalibrationViewModel.providerOf("odds_api_totals"), "odds_api_family")
        XCTAssertEqual(CalibrationViewModel.providerOf("odds_api_bookmaker"), "odds_api_family")
        XCTAssertEqual(CalibrationViewModel.providerOf("kalshi"), "kalshi")
        XCTAssertEqual(CalibrationViewModel.providerOf("datagolf"), "datagolf")
        XCTAssertEqual(CalibrationViewModel.providerOf("odds"), "odds")

        let groups = CalibrationViewModel.providerGroups(
            ["kalshi", "odds_api_bookmaker", "polymarket", "odds_api", "odds_api_totals", "datagolf"])
        XCTAssertEqual(groups.map(\.provider), ["kalshi", "odds_api_family", "polymarket", "datagolf"])
        XCTAssertEqual(groups[1].members, ["odds_api_bookmaker", "odds_api", "odds_api_totals"])
        XCTAssertEqual(CalibrationViewModel.providerDisplayName("kalshi"), "Kalshi")
    }

    /// Web's `withoutGroupQualifier`, case for case.
    @MainActor
    func testMemberNamesDropOnlyTheGroupsOwnQualifier() {
        let g = "Sportsbooks (Odds API)"
        XCTAssertEqual(CalibrationViewModel.withoutGroupQualifier("Totals (Odds API)", groupName: g), "Totals")
        XCTAssertEqual(CalibrationViewModel.withoutGroupQualifier("Moneylines (Odds API)", groupName: g), "Moneylines")
        XCTAssertEqual(CalibrationViewModel.withoutGroupQualifier("Totals (Other)", groupName: g), "Totals (Other)")
        XCTAssertEqual(CalibrationViewModel.withoutGroupQualifier("(Odds API)", groupName: g), "(Odds API)",
                       "stripping to nothing keeps the name")
        XCTAssertEqual(CalibrationViewModel.withoutGroupQualifier("Kalshi", groupName: "Kalshi"), "Kalshi")
    }

    // MARK: - The interval prints only over its own population (web #7374)

    @MainActor
    func testTheIntervalIsWithheldOnTheTradedViewAndShownOverEveryOutcome() throws {
        let vm = try model()
        XCTAssertLessThan(vm.cohortN, vm.fullN, "the fixture must have an excluded cohort")
        XCTAssertNil(vm.cohortInterval,
                     "the traded view must not print the all-outcomes interval")
        vm.includeThin = true
        XCTAssertEqual(vm.cohortN, vm.fullN)
        let ci = try XCTUnwrap(vm.cohortInterval, "over every outcome it is the published pair")
        XCTAssertEqual(ci.lower, 0.33); XCTAssertEqual(ci.upper, 1.19)
    }

    @MainActor
    func testTheIntervalKeysOnThePopulationNotTheToggle() {
        // No untraded outcomes: one population in both states, so it prints.
        XCTAssertNotNil(CalibrationViewModel.intervalForCohort(lower: 0.3, upper: 1.2, cohortN: 50, fullN: 50))
        XCTAssertNil(CalibrationViewModel.intervalForCohort(lower: 0.3, upper: 1.2, cohortN: 49, fullN: 50))
        XCTAssertNil(CalibrationViewModel.intervalForCohort(lower: nil, upper: 1.2, cohortN: 50, fullN: 50))
        XCTAssertNil(CalibrationViewModel.intervalForCohort(lower: 1.3, upper: 1.2, cohortN: 50, fullN: 50),
                     "an inverted pair is not an interval")
        XCTAssertNil(CalibrationViewModel.intervalForCohort(lower: 0.3, upper: 1.2, cohortN: 0, fullN: 0))
    }
}
