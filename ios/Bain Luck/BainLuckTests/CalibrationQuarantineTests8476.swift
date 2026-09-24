import SwiftUI
import XCTest
@testable import Bain_Luck

/// #8476: the phone's Accuracy screen states the same held-out count the website does.
///
/// The #6275 identity quarantine takes outcomes out of every published curve and
/// the server discloses them in `quarantine`. Web has rendered that key as a
/// "Held out, under review" card since CAL-P067. Native never decoded it, so the
/// phone's curve came out shorter than the website's and never said why.
///
/// Web's copy is pinned in two places. The literal below is web's sentence, and
/// `frontend/e2e/contract/calibrationQuarantineCopy8476.contract.test.js` checks
/// that `page.tsx` and `CalibrationViewModel.swift` both still carry it. Change
/// the wording on one surface only and one of the two goes red.
@MainActor
final class CalibrationQuarantineTests8476: XCTestCase {

    private func decode(_ json: String) throws -> CalibrationData {
        let dec = JSONDecoder()
        dec.keyDecodingStrategy = .convertFromSnakeCase
        return try dec.decode(CalibrationData.self, from: Data(json.utf8))
    }

    /// The row the server builds (`precompute_calibration.py`, `"quarantine"`),
    /// with its real reader reason (`QUARANTINE_READER_REASON`).
    private static let serverRow = """
    {"reason": "Markets whose own ID names a different game day than the game they are attached to",
     "outcomes": 2069, "status": "under_review",
     "note": "market_identity_disputed: the method sentence web does not print", "markets": 431}
    """

    private static func payload(quarantine: String?) -> String {
        let line = quarantine.map { "\"quarantine\": \($0)," } ?? ""
        return """
        {
          \(line)
          "population_version": "\(CalibrationRenderSmokeTests.renderableVersion)",
          "buckets": [
            {"bucket_idx": 2, "source": "kalshi", "category": "baseball_mlb", "price_moved": true, "n": 200, "winners": 60, "avg_prob": 0.25, "sum_prob": 50.0, "sum_sq_err": 44.0, "ci_lower": 0.21, "ci_upper": 0.31},
            {"bucket_idx": 5, "source": "polymarket", "category": "politics", "price_moved": false, "n": 100, "winners": 55, "avg_prob": 0.55, "sum_prob": 55.0, "sum_sq_err": 24.0, "ci_lower": 0.45, "ci_upper": 0.64}
          ],
          "total_markets": 12, "total_outcomes": 300, "total_winners": 115,
          "generated_at": "2026-09-25T00:20:00+00:00",
          "min_category_outcomes": 1000
        }
        """
    }

    // MARK: - Decode

    func testTheServersQuarantineRowDecodesWithItsReasonAndCount() throws {
        let data = try decode(Self.payload(quarantine: "[\(Self.serverRow)]"))
        let held = try XCTUnwrap(data.quarantine, "a served quarantine list decoded as absent")
        XCTAssertEqual(held.count, 1)
        XCTAssertEqual(held[0].reason,
                       "Markets whose own ID names a different game day than the game they are attached to")
        XCTAssertEqual(held[0].outcomes, 2069)
        XCTAssertEqual(held[0].status, "under_review")
        XCTAssertEqual(held[0].markets, 431)
    }

    /// Absent means "we never looked" and `[]` means "we checked and hold nothing".
    /// Both hide the card, but a decode that collapses them loses the fact.
    func testAnAbsentKeyAndAnEmptyListStayDifferentFacts() throws {
        XCTAssertNil(try decode(Self.payload(quarantine: nil)).quarantine)
        XCTAssertEqual(try decode(Self.payload(quarantine: "[]")).quarantine?.count, 0)
    }

    /// Gotcha #42 on the client: one unreadable row must not take the good one
    /// with it, and must not take the rest of the payload with it either.
    func testOneMalformedRowDropsAloneAndThePayloadStillDecodes() throws {
        let data = try decode(Self.payload(quarantine: #"[{"reason": "no count"}, \#(Self.serverRow)]"#))
        XCTAssertEqual(data.quarantine?.map(\.outcomes), [2069])
        XCTAssertEqual(data.buckets.count, 2, "a bad quarantine row cost the curve")
    }

    // MARK: - What the reader reads

    func testTheCaptionIsWebsSentenceWithWebsNumber() throws {
        let vm = CalibrationViewModel(preloaded: try decode(Self.payload(quarantine: "[\(Self.serverRow)]")))
        XCTAssertEqual(vm.quarantineTotal, 2069)
        // Web: `{total.toLocaleString()} resolved {outcome is|outcomes are} excluded …`
        XCTAssertEqual(
            vm.quarantineCaption,
            "2,069 resolved outcomes are excluded from every curve on this page while we check them. "
                + "They are not graded, not counted, and not deleted \u{2014} a held-out row is a stated "
                + "exclusion we can reverse, which is the difference between a quarantine and a "
                + "quietly shorter denominator.")
        // The full number, not `compactCount`'s "2.1K": the two screens must print the same figure.
        XCTAssertEqual(vm.quarantineCount(2069), "2,069")
    }

    func testTheTotalSumsEveryRowAndOneOutcomeReadsSingular() throws {
        let two = CalibrationViewModel(preloaded: try decode(Self.payload(quarantine:
            #"[{"reason": "A", "outcomes": 5}, {"reason": "B", "outcomes": 7}]"#)))
        XCTAssertEqual(two.quarantineTotal, 12)
        XCTAssertTrue(two.quarantineCaption.hasPrefix("12 resolved outcomes are excluded"))

        let one = CalibrationViewModel(preloaded: try decode(Self.payload(quarantine:
            #"[{"reason": "A", "outcomes": 1}]"#)))
        XCTAssertTrue(one.quarantineCaption.hasPrefix("1 resolved outcome is excluded"),
                      one.quarantineCaption)
    }

    func testNoRowsMeansNoCardEitherWay() throws {
        for q in [nil, "[]"] as [String?] {
            let vm = CalibrationViewModel(preloaded: try decode(Self.payload(quarantine: q)))
            XCTAssertTrue(vm.quarantine.isEmpty)
            XCTAssertEqual(vm.quarantineTotal, 0)
        }
    }

    // MARK: - Render

    /// The card is on the real surface: a payload that holds rows rasterises
    /// differently from the same payload holding none, at phone width.
    func testThe390ptSurfaceDrawsTheCardOnlyWhenRowsAreHeld() throws {
        func render(_ q: String?, _ name: String) throws -> Data {
            let vm = CalibrationViewModel(preloaded: try decode(Self.payload(quarantine: q)))
            XCTAssertFalse(vm.isIncompatible, "\(name): fixture refused, the render proves nothing")
            let view = CalibrationSurfaceView(viewModel: vm, scrolls: false).frame(width: 390)
            let renderer = rendererForMeasurement(view)
            renderer.scale = 2
            let image = try XCTUnwrap(renderer.uiImage, "\(name) produced no raster")
            let png = try XCTUnwrap(image.pngData())
            let url = FileManager.default.temporaryDirectory
                .appendingPathComponent("cal-8476-\(name).png")
            try? png.write(to: url)
            print("#8476 render [\(name)]: \(url.path) h=\(image.size.height)")
            return png
        }
        let held = try render("[\(Self.serverRow)]", "held")
        let empty = try render("[]", "empty")
        let absent = try render(nil, "absent")
        XCTAssertNotEqual(held, empty, "the held-out card did not draw")
        XCTAssertEqual(empty, absent, "an empty list and an absent key must both draw nothing")
    }
}
