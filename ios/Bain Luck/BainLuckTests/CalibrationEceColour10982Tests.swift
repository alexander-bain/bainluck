import SwiftUI
import XCTest
@testable import Bain_Luck

/// #10982: the same Accuracy error is the same colour on the website and the
/// iPhone.
///
/// On the served default Accuracy view (2026-10-13), AFL 5.1, NRL 5.6 and
/// Lacrosse 6.9 were orange on a 390px web page and blue in the installed app;
/// Entertainment through Tech at 3.1–3.8 were blue on web and green in the app.
/// Web colours the hero, the cohort row and every category cell `< 3` green,
/// `< 5` blue, else orange, and `eceQualityLabel` cuts at the same 3 and 5.
/// `eceColor` alone used `< 4` / `< 8`.
///
/// The cross-surface coupling is pinned in jest
/// (`frontend/__tests__/ios/calibrationEceColourParity10982.test.ts`), because
/// this target does not run in CI; this file pins the colours themselves.
@MainActor
final class CalibrationEceColour10982Tests: XCTestCase {

    private struct StubError: Error {}

    private func model() -> CalibrationViewModel {
        CalibrationViewModel(fetcher: { throw StubError() })
    }

    /// The issue's specimens, read off the served view.
    func testTheIssuesCategoryValuesTakeTheWebsitesColour() {
        let vm = model()
        for (label, ece) in [("AFL", 5.1), ("NRL", 5.6), ("Lacrosse", 6.9)] {
            XCTAssertEqual(vm.eceColor(ece), .orange, "\(label) \(ece) is orange on web")
        }
        for ece in [3.1, 3.4, 3.8] {
            XCTAssertEqual(vm.eceColor(ece), .blue, "\(ece) is blue on web")
        }
        XCTAssertEqual(vm.eceColor(2.9), .green)
    }

    /// Web's comparisons are strict `<`: 3.0 is blue and 5.0 is orange.
    func testTheCutPointsAreWebsStrictBoundaries() {
        let vm = model()
        XCTAssertEqual(vm.eceColor(2.999), .green)
        XCTAssertEqual(vm.eceColor(3.0), .blue)
        XCTAssertEqual(vm.eceColor(4.999), .blue)
        XCTAssertEqual(vm.eceColor(5.0), .orange)
        XCTAssertEqual(vm.eceColor(12.0), .orange)
    }

    /// #3650 is unchanged: a withheld figure has no quality colour.
    func testAWithheldFigureStaysUncoloured() {
        XCTAssertEqual(model().eceColor(nil as Double?), .secondary)
    }
}
