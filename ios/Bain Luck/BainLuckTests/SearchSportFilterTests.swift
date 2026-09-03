import XCTest
@testable import Bain_Luck

/// native/001 finding 2 — Search's sport filter row.
///
/// The row used to be a hand-written list of seven sport FAMILIES —
/// `basketball`, `americanfootball`, `baseball`, `icehockey`, `soccer`, `golf`,
/// `mma` — sent as the API's `sport` parameter. That parameter is an exact
/// `Sport.key` match (`routes/events.py`: `Sport.key == sport`), and none of
/// those seven is a key. Measured against production 2026-09-03:
///
///   `?q=lakers`                     → 5 results, facet `basketball_nba: 5`
///   `?q=lakers&sport=basketball`    → **0 results**
///
/// So every pill in the row was dead. Alex reported the part he could see —
/// there was no tennis pill — while `?q=shelton` returns 11 tennis events across
/// five `tennis_*` keys.
///
/// The row is now the server's own `sports` facet, which speaks exact keys by
/// construction. These pin the ranking rule and the reason the facet is held
/// from the unfiltered response.
final class SearchSportFilterTests: XCTestCase {

    private func facets(_ json: String) throws -> [SportFacet] {
        let dec = JSONDecoder()
        dec.keyDecodingStrategy = .convertFromSnakeCase
        return try dec.decode([SportFacet].self, from: Data(json.utf8))
    }

    /// The real facet for `?q=shelton`, verbatim.
    private func sheltonFacet() throws -> [SportFacet] {
        try facets("""
        [
          {"key": "tennis_atp_us_open", "name": "ATP US Open", "count": 3},
          {"key": "tennis_atp", "name": "Tennis Atp", "count": 1},
          {"key": "tennis_atp_cincinnati_open", "name": "ATP Cincinnati Open", "count": 1},
          {"key": "tennis_atp_canadian_open", "name": "ATP Canadian Open", "count": 5},
          {"key": "tennis_other", "name": "tennis_other", "count": 1}
        ]
        """)
    }

    // MARK: - The reported defect

    /// Searching a tennis player now yields tennis pills — and every one of them
    /// carries an EXACT sport key, which is the only thing the API will honour.
    func testTennisQueryProducesTennisPillsWithExactKeys() throws {
        let ranked = SearchViewModel.rankedFacets(try sheltonFacet())
        XCTAssertFalse(ranked.isEmpty, "a tennis search must offer a tennis filter")
        XCTAssertTrue(ranked.allSatisfy { $0.key.hasPrefix("tennis_") })
        // The dead family token must never be sent as a filter again.
        XCTAssertFalse(ranked.contains { $0.key == "tennis" })
    }

    func testBiggestBucketLeads() throws {
        let ranked = SearchViewModel.rankedFacets(try sheltonFacet())
        XCTAssertEqual(ranked.first?.key, "tennis_atp_canadian_open")
        XCTAssertEqual(ranked.first?.count, 5)
        XCTAssertEqual(ranked.map(\.count), [5, 3, 1, 1, 1])
    }

    /// Ties resolve by name so two identical searches draw the same row — a row
    /// that reshuffles between renders reads as a bug.
    func testTiesAreOrderedDeterministically() throws {
        let ranked = SearchViewModel.rankedFacets(try sheltonFacet())
        let tied = ranked.filter { $0.count == 1 }.map(\.name)
        XCTAssertEqual(tied, tied.sorted())
    }

    /// A pill that can only ever return nothing is the defect being replaced.
    func testZeroCountFacetsAreDropped() throws {
        let ranked = SearchViewModel.rankedFacets(try facets("""
        [
          {"key": "basketball_nba", "name": "NBA", "count": 5},
          {"key": "soccer_epl", "name": "EPL", "count": 0}
        ]
        """))
        XCTAssertEqual(ranked.map(\.key), ["basketball_nba"])
    }

    /// A futures-only query (the server's facet counts events) draws no row at
    /// all rather than an empty or stale one.
    func testAbsentFacetYieldsNoRow() {
        XCTAssertTrue(SearchViewModel.rankedFacets(nil).isEmpty)
        XCTAssertTrue(SearchViewModel.rankedFacets([]).isEmpty)
    }

    // MARK: - Icons

    /// Every facet key resolves to a symbol; tennis in particular, since a key
    /// with no icon was part of why tennis never appeared in this row.
    func testSportSymbolsResolveByKeyPrefix() {
        XCTAssertEqual(sportSymbolName(forSportKey: "tennis_atp_us_open"), "figure.tennis")
        XCTAssertEqual(sportSymbolName(forSportKey: "tennis_wta"), "figure.tennis")
        XCTAssertEqual(sportSymbolName(forSportKey: "basketball_nba"), "basketball.fill")
        XCTAssertEqual(sportSymbolName(forSportKey: "americanfootball_nfl"), "football.fill")
        XCTAssertEqual(sportSymbolName(forSportKey: "icehockey_nhl"), "hockey.puck.fill")
        XCTAssertEqual(sportSymbolName(forSportKey: "soccer_epl"), "soccerball")
        XCTAssertEqual(sportSymbolName(forSportKey: "golf_pga"), "figure.golf")
        // Unknown families still get a symbol rather than an empty slot.
        XCTAssertEqual(sportSymbolName(forSportKey: "kabaddi_pro"), "sportscourt")
    }
}
