import XCTest
import SwiftUI
@testable import Bain_Luck

/// native/268 (#7512) — an entertainment section's heading counts the rows it
/// actually draws.
///
/// **What a reader saw.** Two flat sections took their heading from one place
/// and their cards from another, measured on the bank served 2026-09-20 14:05Z:
///
/// | section | heading | cards |
/// |---|---|---|
/// | Tech & Culture | **49** (`themes.tech_culture.count`) | **10** (`prefix(10)`) |
/// | Pop culture feed | **20** (`markets.count`) | **12** (`prefix(12)`) |
///
/// A number over a shorter list, with nothing to say whether the rest were
/// loading, filtered, or never there.
///
/// ⭐ **ux/1391 routed the first one and this file carries both, because the
/// second was found by counting rather than by reading the issue.** #7512 names
/// Tech & Culture only. Surveying every `SectionTitle(count:)` in the view found
/// five, and measuring each against the served payload sorted them: Pop culture
/// feed is the same defect (20 over 12) and is fixed here; "What's hot" is
/// count 5 over a lead plus `prefix(4)` = 5, which agrees today; Music (252) and
/// Film/TV (149) are **tabbed** sections whose count names the whole theme while
/// a visible tab bar shows the partition — a different claim, deliberately left
/// alone. That sorting is the reason this is two sites and not five.
///
/// **Why the assertions are on the ROWS, not on a rendered view.** A heading and
/// a grid can both be present, correct and in order while disagreeing by eight
/// cards; only comparing the two numbers catches it. The seam exists so there is
/// one array to compare against, and the source scans below are what prove the
/// view still reads it.
final class EntertainmentSectionCountsMatchTheirRows7512Tests: XCTestCase {

    private typealias R = EntertainmentSectionRows

    // MARK: - The reported shape, from the payload that reported it

    /// 🔴 The specimen: `count` 49 over a served list of 15. Both numbers are
    /// real and today's; the heading used to print the first one over ten cards.
    func testTheTechCultureHeadingCountsTheMarketsItWasServedNotTheProducersBucket() throws {
        let data = try techCulture(count: 49, markets: 15)

        XCTAssertEqual(R.techCulture(data).count, 15,
                       "the heading is still counting something other than the rows")
        XCTAssertNotEqual(R.techCulture(data).count, data.count,
                          "this payload's two numbers are equal, so it cannot prove anything")
    }

    /// ⭐ And it does not wait on #7432. ux's producer fix moves `count` 49 → 15;
    /// this asserts the heading is right **either way**, which is what makes the
    /// two halves independent rather than a pair someone has to land together.
    func testTheTechCultureHeadingIsRightBeforeAndAfterTheProducerFix() throws {
        for producerCount in [49, 15] {
            let data = try techCulture(count: producerCount, markets: 15)
            XCTAssertEqual(R.techCulture(data).count, 15,
                           "heading disagrees with its rows when count == \(producerCount)")
        }
    }

    /// Pop culture feed — the site #7512 does not name. 20 served, 12 drawn.
    func testThePopCultureFeedDrawsEveryMomentItCounts() throws {
        let markets = try rows(20)

        XCTAssertEqual(R.cultural(markets).count, 20,
                       "the feed is still capped under a heading that counts past the cap")
    }

    /// The general claim both sites now satisfy, swept over sizes that straddle
    /// the two caps this fix removed (10 and 12). A single size passes on a
    /// `prefix` whose bound happens to sit above it.
    func testAHeadingNeverPromisesMoreRowsThanItDraws() throws {
        for n in [0, 1, 9, 10, 11, 12, 13, 15, 20, 40] {
            let cultural = R.cultural(try rows(n))
            XCTAssertEqual(cultural.count, n, "cultural lost rows at n=\(n)")

            let tech = R.techCulture(try techCulture(count: 999, markets: n))
            XCTAssertEqual(tech.count, n, "tech & culture lost rows at n=\(n)")
        }
    }

    /// An absent `markets` is a section with nothing in it — a heading of zero
    /// and no grid, never a heading of 49 over nothing. `markets` is optional on
    /// the wire, so this is a real payload and not a hypothetical.
    func testAnAbsentMarketsListIsAHeadingOfZeroNotTheProducersNumber() throws {
        let data = try decode(EntThemeTechCulture.self, from: ["count": 49])

        XCTAssertEqual(R.techCulture(data).count, 0)
        XCTAssertTrue(R.techCulture(data).isEmpty)
    }

    // MARK: - The wiring, which no assertion above can reach

    /// Every assertion above can be perfect while the view goes on printing
    /// `data.count` over `prefix(10)`. These scans are the only thing that fails.
    func testBothSectionsReadOneArrayForTheHeadingAndTheGrid() throws {
        let body = try String(contentsOf: Self.viewURL, encoding: .utf8)

        XCTAssertTrue(body.contains("SectionTitle(title: \"Platform bets & social\", count: shown.count)"),
                      "the Tech & Culture heading is not counting the array its grid draws")
        XCTAssertTrue(body.contains("SectionTitle(title: \"Pop culture feed\", count: shown.count)"),
                      "the Pop culture heading is not counting the array its grid draws")

        // The exact strings the pre-#7512 view carried, and the exact strings a
        // mutant in `tools/native-268c-mutations-7512.py` writes back — so
        // neither of these is an absence that could never occur.
        XCTAssertFalse(body.contains("SectionTitle(title: \"Platform bets & social\", count: data.count)"),
                       "Tech & Culture is printing the producer's bucket again")
        XCTAssertFalse(body.contains("marketGrid(Array(markets.prefix(10)))"),
                       "the Tech & Culture grid is capped under its heading again")
        XCTAssertFalse(body.contains("ForEach(markets.prefix(12))"),
                       "the Pop culture grid is capped under its heading again")

        // 🪤 THE HALF-RETURN, and the reason the three lines above are not
        // enough. Mutation put each cap BACK on the resolved array —
        // `marketGrid(Array(shown.prefix(10)))`, `ForEach(shown.prefix(12))` —
        // and both survived: the heading still follows `shown`, so it is
        // arithmetically perfect while the grid quietly draws ten of fifteen.
        // Every assertion in this file that compares two numbers is blind to it,
        // because there is only one number. A cap re-added to a correctly-wired
        // label is invisible to a label-vs-rows test BY CONSTRUCTION, so the
        // grid has to be asserted to draw the array WHOLE.
        XCTAssertTrue(body.contains("marketGrid(shown)"),
                      "the Tech & Culture grid no longer draws its array whole")
        XCTAssertTrue(body.contains("ForEach(shown) { m in"),
                      "the Pop culture grid no longer draws its array whole")
        XCTAssertFalse(body.contains("shown.prefix("),
                       "a cap is back on a resolved section array — the heading will follow it "
                           + "and read as correct while rows go missing under it")
    }

    /// 🪤 The tabbed sections are NOT swept, and that is a decision rather than
    /// an oversight — so it is asserted, not left to a comment. Music and Film/TV
    /// still print the theme's own count beside a tab bar, and if someone ever
    /// flattens one of those into a single capped grid this goes red and they
    /// re-read the paragraph above.
    func testTheTabbedSectionsStillCountTheirWholeThemeBesideATabBar() throws {
        let body = try String(contentsOf: Self.viewURL, encoding: .utf8)

        XCTAssertTrue(body.contains("SectionTitle(title: \"Charts, drops & streams\", count: data.count)"))
        XCTAssertTrue(body.contains("SectionTitle(title: \"Scores, box office & reality\", count: data.count)"))
        XCTAssertTrue(body.contains("musicTabBar(data)"),
                      "Music lost its tab bar, so its whole-theme count is now a bare over-claim")
    }

    /// Strawman: the scans read a real file with real content, so the
    /// `XCTAssertFalse`s above cannot be passing because a read failed.
    func testTheSourceScanIsReadingTheFileItThinksItIs() throws {
        let body = try String(contentsOf: Self.viewURL, encoding: .utf8)
        XCTAssertGreaterThan(body.count, 20_000, "EntertainmentView.swift read back far too small")
        XCTAssertTrue(body.contains("import SwiftUI"), "that is not the Swift file")
    }

    // MARK: - Fixtures

    private func techCulture(count: Int, markets: Int) throws -> EntThemeTechCulture {
        try decode(EntThemeTechCulture.self,
                   from: ["count": count, "markets": marketJSON(markets)])
    }

    private func rows(_ n: Int) throws -> [EntMarketRow] {
        try decode([EntMarketRow].self, from: marketJSON(n))
    }

    /// The wire shape, not a hand-built value: `market_id`, `outcome_count` and
    /// `top_outcomes` come through `.convertFromSnakeCase` the way the route
    /// sends them, and every non-optional field of `EntMarketRow` is present —
    /// a fixture that fails to decode would make these tests pass on a throw.
    private func marketJSON(_ n: Int) -> [[String: Any]] {
        (0..<n).map { i in
            ["q": "Market \(i)", "prob": 0.5, "src": "kalshi",
             "market_id": 900_000 + i, "outcome_count": 2,
             "top_outcomes": [["name": "Yes", "prob": 0.5]]]
        }
    }

    private func decode<T: Decodable>(_ type: T.Type, from json: Any) throws -> T {
        let data = try JSONSerialization.data(withJSONObject: json)
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(type, from: data)
    }

    /// 🪤 `#filePath` keeps the spelling the compiler was given while
    /// `FileManager` standardises it, so prefix arithmetic between the two eats
    /// the middle out of the path. Going up the URL avoids the subtraction.
    private static var viewURL: URL {
        URL(fileURLWithPath: #filePath)            // …/BainLuckTests/<this file>.swift
            .deletingLastPathComponent()           // …/BainLuckTests
            .deletingLastPathComponent()           // …/ios/Bain Luck
            .appendingPathComponent("Bain Luck")
            .appendingPathComponent("Views/EntertainmentView.swift")
    }
}
