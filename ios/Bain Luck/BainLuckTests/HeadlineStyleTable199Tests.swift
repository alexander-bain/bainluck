import XCTest
@testable import Bain_Luck

/// Direction 199 / ruling 200-B: on every surface that draws the game headline,
/// "Now" is the largest number. Includes the Live Activity's Lock Screen and
/// expanded Dynamic Island, which the Apple lane draws from this one table.
final class HeadlineStyleTable199Tests: XCTestCase {
    func testNowIsTheLargestNumberOnEverySurface() {
        for surface in HeadlineStyleTable199.Surface.allCases {
            let now = HeadlineStyleTable199.nowBaseSize(surface)
            for prominent in [false, true] {
                XCTAssertGreaterThan(
                    now, HeadlineStyleTable199.secondNumberBaseSize(surface, prominent: prominent),
                    "\(surface.rawValue): Now must be larger than every second number (prominent: \(prominent))")
            }
            XCTAssertGreaterThan(now, HeadlineStyleTable199.nameBaseSize(surface), surface.rawValue)
            XCTAssertGreaterThan(now, HeadlineStyleTable199.quietTextBaseSize(surface), surface.rawValue)
            XCTAssertGreaterThan(now, HeadlineStyleTable199.headerBaseSize(surface), surface.rawValue)
        }
    }

    func testTheLiveActivityHasItsOwnTwoSurfaces() {
        let names = HeadlineStyleTable199.Surface.allCases.map(\.rawValue)
        XCTAssertTrue(names.contains("lockScreen"))
        XCTAssertTrue(names.contains("island"))
    }
}
