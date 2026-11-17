import XCTest
@testable import Bain_Luck

/// #10864 — the DEBUG demo's canned readings decode as real ones do.
final class GameActivityDemo10864Tests: XCTestCase {
    func testTheLiveReadingDecodes() throws {
        let live = try XCTUnwrap(GameActivityDemo10864.snapshot("live"))
        XCTAssertEqual(live.lifecycle, .live)
        XCTAssertEqual(live.homeScore, 21)
    }

    func testTheFinalReadingDecodesAsAFinal() throws {
        let final = try XCTUnwrap(GameActivityDemo10864.snapshot("final"))
        XCTAssertTrue(final.isFinal)
        XCTAssertEqual(final.homeScore, 35)
        XCTAssertEqual(final.awayScore, 12)
    }
}
