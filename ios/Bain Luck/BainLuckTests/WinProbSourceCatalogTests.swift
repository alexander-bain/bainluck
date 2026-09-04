import XCTest
@testable import Bain_Luck

/// native/001 finding 3 — the event page must name every source behind the
/// blended number, not just the sportsbooks.
///
/// Alex opened the upcoming Shelton–Shapovalov match and the only source
/// disclosure on the page said "Individual Sportsbooks". The API was serving all
/// three legs fresh at the time (measured 19:08Z 2026-09-03: kalshi 0.775,
/// polymarket 0.775, betting 0.7525 across 10 books) — the client simply had no
/// surface that read `win_probability_sources`.
///
/// The trap in that map is `betting_book_count`: it wears the same
/// `{value, display_name, type}` shape as a real reading but is a COUNT (10, not
/// 0.10). A consumer that iterates the keys prints a source called
/// "betting_book_count" reading 1000%. `WinProbSourceCatalog` filters to the
/// backend's own `SOURCE_WEIGHTS` allowlist, which is the same rule
/// `compute_aggregate_probability` uses to decide what feeds the blend.
final class WinProbSourceCatalogTests: XCTestCase {

    private func sources(_ json: String) throws -> [String: WinProbSource] {
        let dec = JSONDecoder()
        dec.keyDecodingStrategy = .convertFromSnakeCase
        return try dec.decode([String: WinProbSource].self, from: Data(json.utf8))
    }

    /// Event 15301215's `win_probability_sources`, verbatim.
    private func sheltonSources() throws -> [String: WinProbSource] {
        try sources("""
        {
          "kalshi": {"value": 0.775, "display_name": "Kalshi", "type": "market", "color": "#22c55e"},
          "betting": {"value": 0.7525, "display_name": "Betting Odds", "type": "market", "color": "#374151"},
          "polymarket": {"value": 0.775, "display_name": "Polymarket", "type": "market", "color": "#3b82f6"},
          "betting_book_count": {"value": 10.0, "display_name": "betting_book_count", "type": "model", "color": "#6b7280"}
        }
        """)
    }

    // MARK: - The reported defect

    func testPredictionMarketLegsAreNamed() throws {
        let entries = WinProbSourceCatalog.entries(from: try sheltonSources())
        let labels = entries.map(\.label)
        XCTAssertTrue(labels.contains("Kalshi"), "\(labels)")
        XCTAssertTrue(labels.contains("Polymarket"), "\(labels)")
        XCTAssertEqual(entries.count, 3, "three real legs — books, Kalshi, Polymarket")
    }

    func testEveryLegKeepsItsOwnProbability() throws {
        let byKey = Dictionary(
            uniqueKeysWithValues: WinProbSourceCatalog.entries(from: try sheltonSources())
                .map { ($0.key, $0.homeProbability) })
        XCTAssertEqual(byKey["kalshi"], 0.775)
        XCTAssertEqual(byKey["polymarket"], 0.775)
        XCTAssertEqual(byKey["betting"], 0.7525)
    }

    // MARK: - The metadata trap

    func testBookCountIsNeverRenderedAsASource() throws {
        let entries = WinProbSourceCatalog.entries(from: try sheltonSources())
        XCTAssertFalse(entries.contains { $0.key == "betting_book_count" })
        XCTAssertFalse(entries.contains { $0.label.contains("betting_book_count") })
        XCTAssertTrue(
            entries.allSatisfy { (0...1).contains($0.homeProbability) },
            "a counter (10.0) reaching the renderer would print as 1000%")
    }

    /// The count is not discarded — it becomes the sportsbook row's detail, which
    /// is the honest place for "how many books".
    func testBookCountBecomesTheSportsbookRowsDetail() throws {
        let entries = WinProbSourceCatalog.entries(from: try sheltonSources())
        XCTAssertEqual(entries.first { $0.key == "betting" }?.label, "Sportsbooks (10)")
    }

    func testSportsbookRowFallsBackWhenNoCountIsCarried() throws {
        let entries = WinProbSourceCatalog.entries(from: try sources("""
        {"betting": {"value": 0.61, "display_name": "Betting Odds", "type": "market"}}
        """))
        XCTAssertEqual(entries.map(\.label), ["Betting Odds"])
    }

    // MARK: - Shape tolerance

    /// The map's values are sometimes a bare number rather than an object.
    func testBareNumberEntriesDecodeAsSources() throws {
        let entries = WinProbSourceCatalog.entries(from: try sources("""
        {"kalshi": 0.42, "espn": 0.58}
        """))
        XCTAssertEqual(entries.map(\.key), ["espn", "kalshi"])
        XCTAssertEqual(entries.map(\.label), ["ESPN", "Kalshi"], "fallback names, never raw keys")
    }

    func testUnknownKeysAreIgnoredRatherThanGuessedAt() throws {
        let entries = WinProbSourceCatalog.entries(from: try sources("""
        {"kalshi": 0.42, "some_future_counter": 17.0}
        """))
        XCTAssertEqual(entries.map(\.key), ["kalshi"])
    }

    func testValuelessEntryIsDropped() throws {
        let entries = WinProbSourceCatalog.entries(from: try sources("""
        {"kalshi": {"display_name": "Kalshi", "type": "market"}}
        """))
        XCTAssertTrue(entries.isEmpty)
    }

    func testMissingMapIsEmptyNotACrash() {
        XCTAssertTrue(WinProbSourceCatalog.entries(from: nil).isEmpty)
    }

    /// Two renders of the same payload must produce the same row order — a
    /// dictionary's iteration order does not.
    func testOrderIsDeterministic() throws {
        let first = WinProbSourceCatalog.entries(from: try sheltonSources()).map(\.key)
        for _ in 0..<20 {
            XCTAssertEqual(WinProbSourceCatalog.entries(from: try sheltonSources()).map(\.key), first)
        }
        XCTAssertEqual(first, ["betting", "kalshi", "polymarket"])
    }

    /// The allowlist is the backend's `SOURCE_WEIGHTS`. If the blend learns a new
    /// source and this set does not, the app silently stops naming it.
    func testAllowlistMatchesTheBackendBlendInputs() {
        XCTAssertEqual(
            WinProbSourceCatalog.realSourceKeys,
            ["final_result", "betting", "espn", "stat_model", "kalshi", "polymarket", "mlb"])
    }
}
