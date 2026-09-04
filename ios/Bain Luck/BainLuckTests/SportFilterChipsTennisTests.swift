import XCTest

@testable import Bain_Luck

/// native/007 Item 1 (#2560, native side) — the Sports tab admits tennis exists.
///
/// The chip row shipped NBA · NFL · MLB · NHL · Soccer · Golf · Politics · Entmt ·
/// Econ · Weather. During the US Open, on a tab whose first screen was three tennis
/// cards, there was no way to ask for tennis. native/001 added tennis to Browse and
/// Search and stopped short of this row.
///
/// Two things are pinned here. The chip exists — and it points at the CATEGORY route,
/// not the league grid. `/api/leagues/tennis` answers 200 with `total_markets: 0`, so a
/// `.leagueGrid(slug: "tennis")` chip would look wired and land on an empty screen: the
/// worst of the three outcomes, because it is the one nobody reports as broken.
final class SportFilterChipsTennisTests: XCTestCase {
    private func category(_ id: String) throws -> SportCategory {
        try XCTUnwrap(sportCategories.first { $0.id == id }, "no chip with id \(id)")
    }

    private func decodeItem(_ json: String) throws -> FeedItem {
        let dec = JSONDecoder()
        dec.keyDecodingStrategy = .convertFromSnakeCase
        return try dec.decode(FeedItem.self, from: Data(json.utf8))
    }

    // MARK: - The chip is there, and it goes somewhere real

    func testTennisChipExists() throws {
        let tennis = try category("tennis")
        XCTAssertEqual(tennis.name, "Tennis")
    }

    func testTennisChipRoutesToTheCategoryNotTheEmptyLeagueGrid() throws {
        let tennis = try category("tennis")
        XCTAssertEqual(
            tennis.route,
            .sportCategory(key: "tennis", name: "Tennis"),
            "`/api/leagues/tennis` serves total_markets: 0 — the league grid is a dead end"
        )
        if case .leagueGrid = tennis.route {
            XCTFail("tennis must never route to a league grid")
        }
    }

    /// `tennis_atp` answers, but only for one tour and with no futures. The category key
    /// is the one that carries both draws plus the Slam winner markets.
    func testTennisChipAsksForBothToursNotJustATP() throws {
        guard case .sportCategory(let key, _) = try XCTUnwrap(category("tennis").route) else {
            return XCTFail("expected a category route")
        }
        XCTAssertEqual(key, "tennis")
        XCTAssertNotEqual(key, "tennis_atp")
        XCTAssertNotEqual(key, "tennis_wta")
    }

    func testTennisSitsWithTheOtherSportsAheadOfTheNonSportChips() throws {
        let ids = sportCategories.map(\.id)
        let tennis = try XCTUnwrap(ids.firstIndex(of: "tennis"))
        let soccer = try XCTUnwrap(ids.firstIndex(of: "soccer"))
        let politics = try XCTUnwrap(ids.firstIndex(of: "politics"))
        XCTAssertGreaterThan(tennis, soccer)
        XCTAssertLessThan(tennis, politics, "tennis is a sport; it belongs before the category chips")
    }

    // MARK: - Classification (`matches`) agrees with what production serves

    /// Production serves tennis events as `tennis_wta_us_open` / `tennis_atp_us_open`,
    /// never a bare `tennis`. A prefix list of `["tennis"]` is what makes both land.
    func testMatchesTennisEventsFromEitherTour() throws {
        let tennis = try category("tennis")
        for sport in ["tennis_wta_us_open", "tennis_atp_us_open", "tennis_atp"] {
            let item = try decodeItem("""
            { "type": "event", "score": 98,
              "data": { "id": 15300832, "sport": "\(sport)",
                        "home_team": "Maria Sakkari", "away_team": "Yuliia Starodubtseva" } }
            """)
            XCTAssertTrue(tennis.matches(item), "\(sport) must classify as tennis")
        }
    }

    func testMatchesTheSlamFuturesByLLMCategory() throws {
        let tennis = try category("tennis")
        let item = try decodeItem("""
        { "type": "futures", "score": 81,
          "data": { "id": 34277822, "name": "US Open Men's Singles Winner",
                    "llm_sport_category": "tennis" } }
        """)
        XCTAssertTrue(tennis.matches(item))
    }

    func testTennisDoesNotSwallowOtherSports() throws {
        let tennis = try category("tennis")
        let baseball = try decodeItem("""
        { "type": "event", "score": 50,
          "data": { "id": 1, "sport": "baseball_mlb",
                    "home_team": "Red Sox", "away_team": "Yankees" } }
        """)
        XCTAssertFalse(tennis.matches(baseball))
    }

    func testNoOtherChipClaimsATennisEvent() throws {
        let item = try decodeItem("""
        { "type": "event", "score": 98,
          "data": { "id": 15300832, "sport": "tennis_wta_us_open",
                    "home_team": "Maria Sakkari", "away_team": "Yuliia Starodubtseva" } }
        """)
        let claimants = sportCategories.filter { $0.id != "all" && $0.matches(item) }.map(\.id)
        XCTAssertEqual(claimants, ["tennis"], "exactly one chip owns a tennis event")
    }

    // MARK: - Class guards: what made this bug possible in the first place

    /// A non-"all" chip does not filter, it navigates (`chipButton` calls `onNavigate`).
    /// A chip with a nil route is therefore a button that does nothing when tapped.
    func testEveryNonAllChipHasARoute() {
        for category in sportCategories where category.id != "all" {
            XCTAssertNotNil(category.route, "\(category.id) chip would be inert")
        }
    }

    /// The icon switch falls through to "sportscourt". A new chip that forgets its case
    /// ships looking like a placeholder, which is how tennis would have landed here.
    func testEveryChipCarriesItsOwnIcon() {
        let fallback = "sportscourt"
        for category in sportCategories where category.id != "all" {
            XCTAssertNotEqual(
                SportFilterChips.chipIcon(for: category.id), fallback,
                "\(category.id) has no icon case and renders the generic fallback"
            )
        }
    }

    /// Every chip must be reachable by a distinct id — a duplicate would make
    /// `isSelected` and the `ForEach` identity ambiguous.
    func testChipIdsAreUnique() {
        XCTAssertEqual(Set(sportCategories.map(\.id)).count, sportCategories.count)
    }
}
