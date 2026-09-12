import XCTest
@testable import Bain_Luck

/// #5538 — the Discover event card's team line, which spent months rendering a
/// finished game as `"Seattle Mariners  Athletics"`.
///
/// The old expression was `"\(away) \(isDone ? "" : "@") \(home)"`. The ternary
/// was the visible part and the bug was the invisible part: both spaces sit
/// OUTSIDE the interpolation, so the finished arm produced a double space and no
/// separator token whatsoever. Photographed on production data at 06:07Z
/// 2026-09-12 on two cards at once (iPad shot
/// `app-store-package/2026-09-12/ipad-13-inch/01-discover.png`) while the live
/// card two rows above it read `"Seattle Mariners @ Athletics"` correctly.
///
/// The defect class is "a conditional separator whose spacing does not travel
/// with it", so the assertions below are written against the RENDERED STRING —
/// no double space, a real separator, both names present, order preserved —
/// rather than against the ternary that happened to cause it this time. A future
/// author who reintroduces a branch here fails on the property, not on the
/// spelling.
///
/// Standing notice 10: CI compiles no Swift, so the pass line for this file is
/// stated on the exact sha in the PR body.
final class DiscoverEventCardTitleTests: XCTestCase {

    // MARK: - The regression itself

    func testFinishedGameTitleHasNoDoubleSpace() {
        // The exact pair from the photograph that found this.
        let title = NativeEventDiscoverCard.matchTitle(away: "Seattle Mariners", home: "Athletics")
        XCTAssertFalse(
            title.contains("  "),
            "The card's team line must never contain a double space — that is the #5538 defect verbatim. Got: \(title)"
        )
        XCTAssertEqual(title, "Seattle Mariners @ Athletics")
    }

    func testTitleAlwaysCarriesASeparatorToken() {
        // Two team names with only whitespace between them do not say which
        // side is home; the separator is the whole content of the relationship.
        for (away, home) in [
            ("Seattle Mariners", "Athletics"),
            ("Philadelphia Phillies", "Atlanta Braves"),
            ("Kansas City Royals", "Boston Red Sox"),
        ] {
            let title = NativeEventDiscoverCard.matchTitle(away: away, home: home)
            XCTAssertTrue(title.contains(" @ "), "Expected an ' @ ' separator in: \(title)")
            XCTAssertFalse(title.contains("  "), "Unexpected double space in: \(title)")
        }
    }

    // MARK: - The property that outlives the current spelling

    func testTitleIsOneSpaceDelimitedAwayThenHome() {
        let title = NativeEventDiscoverCard.matchTitle(away: "Away Team", home: "Home Team")
        // Split on the separator rather than on spaces: team names contain
        // spaces themselves, which is exactly why the double space hid so long.
        let parts = title.components(separatedBy: " @ ")
        XCTAssertEqual(parts.count, 2, "Title should split into exactly two sides on ' @ ': \(title)")
        XCTAssertEqual(parts.first, "Away Team", "Away team must come first")
        XCTAssertEqual(parts.last, "Home Team", "Home team must come second")
    }

    func testTitleDoesNotDependOnGameState() {
        // `matchTitle` takes no status on purpose (notice 35: one card family
        // everywhere, and the web twin prints `{away} @ {home}` unconditionally).
        // If a status argument is ever added back, this test is the place that
        // has to be argued with first.
        let a = NativeEventDiscoverCard.matchTitle(away: "Kansas City Royals", home: "Boston Red Sox")
        let b = NativeEventDiscoverCard.matchTitle(away: "Kansas City Royals", home: "Boston Red Sox")
        XCTAssertEqual(a, b)
        XCTAssertEqual(a, "Kansas City Royals @ Boston Red Sox")
    }

    // MARK: - Degenerate inputs must not resurrect the double space

    func testEmptyTeamNameStillDoesNotProduceADoubleSpace() {
        // An empty side is a data defect, not a rendering one — but it must not
        // ALSO produce the #5538 string, or the guard above becomes unfalsifiable
        // on precisely the rows most likely to be broken.
        let title = NativeEventDiscoverCard.matchTitle(away: "", home: "Athletics")
        XCTAssertFalse(title.hasPrefix("  "), "Empty away side must not yield a leading double space: '\(title)'")
        XCTAssertEqual(title, " @ Athletics")
    }
}
