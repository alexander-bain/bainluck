import XCTest
@testable import Bain_Luck

/// #8313 — on the iPhone, the futures page stops printing an opening price that
/// its own odds say belongs to the other side.
///
/// **The specimen.** 13795456 *Iran leadership change by December 31?*, served
/// 2026-10-17 15:45Z (`/api/futures/13795456`, the app's own route). No reads
/// `opening_probability 0.31` beside `opening_american_odds -223` (0.6905, the
/// complement); Yes reads 0.31 beside +223 (0.3099, its own). The No row printed
/// "from 31%".
///
/// **The control.** 61318328 *US x Iran ceasefire continues through October 31?*,
/// same minute: Yes 0.73 / −270 and No 0.27 / +270, each agreeing with its own odds.
///
/// The rule is web's (`openingIsTheOtherSidesPrice`, `frontend/lib/futuresDetailDisplay.ts`)
/// with web's numbers. Fixtures are the served payloads verbatim, decoded with the
/// app's decoder.
final class FuturesOpeningOnTheOtherSideIsNotPrinted8313Tests: XCTestCase {

    // MARK: - Harness

    private static func detail(_ file: String) throws -> FuturesMarketDetail {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .appendingPathComponent("Fixtures")
            .appendingPathComponent(file)
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(FuturesMarketDetail.self, from: Data(contentsOf: url))
    }

    private static func leg(_ name: String, in d: FuturesMarketDetail) throws -> FuturesOutcome {
        try XCTUnwrap(d.outcomes.first { $0.name == name }, "no \(name) leg")
    }

    private static let specimen = "futures-13795456-detail-8313.20261017T1545Z.json"
    private static let control = "futures-61318328-detail-8313.20261017T1545Z.json"

    // MARK: - Served payloads

    func testTheSpecimensNoOpeningIsWithheldAndYesKeepsItsOwn() throws {
        let d = try Self.detail(Self.specimen)
        let no = try Self.leg("No", in: d)
        let yes = try Self.leg("Yes", in: d)

        // The fixture is the defect: both legs serve 0.31, with opposite odds.
        XCTAssertEqual(no.openingProbability, 0.31)
        XCTAssertEqual(no.openingAmericanOdds, -223)
        XCTAssertEqual(yes.openingProbability, 0.31)
        XCTAssertEqual(yes.openingAmericanOdds, 223)

        XCTAssertNil(FuturesReadableOpening8313.of(no), "No's 31% is Yes's price")
        XCTAssertEqual(FuturesReadableOpening8313.of(yes), 0.31, "Yes's 31% agrees with +223")
    }

    func testTheControlsHonestOpeningsAreBothKept() throws {
        let d = try Self.detail(Self.control)
        XCTAssertEqual(FuturesReadableOpening8313.of(try Self.leg("Yes", in: d)), 0.73)
        XCTAssertEqual(FuturesReadableOpening8313.of(try Self.leg("No", in: d)), 0.27)
    }

    // MARK: - The rule's edges (web's, unchanged)

    private func readable(_ open: Double?, _ odds: Int?) -> Double? {
        FuturesReadableOpening8313.of(opening: open, openingAmericanOdds: odds)
    }

    func testOnlyTheComplementSignatureIsWithheld() {
        // Odds that sit on 1 − opening: withheld, either side of even.
        XCTAssertNil(readable(0.31, -223))
        XCTAssertNil(readable(0.69, 223))
        // A stale opening odds that is neither the opening nor its complement is
        // an honest opening with stale odds: kept.
        XCTAssertEqual(readable(0.31, -150), 0.31)
        XCTAssertEqual(readable(0.31, 400), 0.31)
    }

    func testTheToleranceIsWebs() {
        // 1 − 0.30 = 0.70; −233 is 0.6997 (inside), −257 is 0.7199 (outside).
        XCTAssertNil(readable(0.30, -233))
        XCTAssertEqual(readable(0.30, -257), 0.30)
        XCTAssertEqual(FuturesReadableOpening8313.roundingTolerance, 0.005)
    }

    func testNearEvenNothingIsWithheld() {
        // Within 1 pt of 50% the two readings overlap; a swap moves < 1 pt.
        XCTAssertEqual(readable(0.504, 101), 0.504)   // +101 = 0.4975 ≈ 1 − 0.504
        XCTAssertEqual(readable(0.496, -102), 0.496)  // −102 = 0.5050 ≈ 1 − 0.496
        // Just outside the band the rule reads again.
        XCTAssertNil(readable(0.52, 108))             // +108 = 0.4808 ≈ 0.48
    }

    func testMissingOrImpossibleInputsKeepTodaysBehaviour() {
        XCTAssertNil(readable(nil, -223))
        XCTAssertEqual(readable(0.31, nil), 0.31)
        XCTAssertEqual(readable(0.31, 50), 0.31, "|odds| < 100 is not an American price")
        XCTAssertEqual(readable(0.31, -99), 0.31)
        XCTAssertEqual(readable(0, -100), 0)
        XCTAssertEqual(readable(1, 100), 1)
        XCTAssertEqual(readable(1.2, -223), 1.2)
        XCTAssertTrue(readable(.nan, -223)?.isNaN ?? false)
    }

    // MARK: - Every reader goes through the rule

    private static func source(_ relative: String) throws -> String {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent(relative)
        // Comment lines dropped, so a pin can only be met by code.
        return try String(contentsOf: url, encoding: .utf8)
            .split(separator: "\n", omittingEmptySubsequences: false)
            .filter { !$0.trimmingCharacters(in: .whitespaces).hasPrefix("//") }
            .joined(separator: "\n")
    }

    /// The row's "from N%" and the saved pin's winner opening are the two app
    /// readers of `FuturesOutcome.openingProbability`. Both read through the rule,
    /// so a withheld opening is withheld everywhere, never checked in one place
    /// and printed in another.
    func testTheRowAndTheSavedPinReadTheOpeningThroughTheRule() throws {
        let view = try Self.source("Bain Luck/Views/FuturesDetailView.swift")
        XCTAssertTrue(view.contains("if let opening = FuturesReadableOpening8313.of(outcome), let current = outcome.probability"))
        XCTAssertFalse(view.contains(".openingProbability"),
                       "the futures page must not read the served opening directly")

        let pin = try Self.source("Bain Luck/ViewModels/SavedPinContentViewModel.swift")
        XCTAssertTrue(pin.contains("winnerOpeningProbability: winner.flatMap(FuturesReadableOpening8313.of)"))
        XCTAssertFalse(pin.contains("?.openingProbability"))
    }
}
