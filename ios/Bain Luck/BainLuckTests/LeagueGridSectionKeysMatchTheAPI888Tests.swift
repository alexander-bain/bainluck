import XCTest
@testable import Bain_Luck

/// #888 — the league page rendered 189 markets and silently dropped 378.
///
/// `leagueMarketSections` walks `sectionOrder` and reads `leagueData.sections[key]`.
/// A dictionary miss and an empty section are **indistinguishable** at that call
/// site — no empty state, no count, nothing that says content was skipped — so
/// two keys that the API never emits (`playoff_props`, `novelty`) hid everything
/// behind them, and the two keys it does emit (`props`, `more_markets`) were
/// never read. `more_markets` is the classifier's default return, which makes it
/// the biggest bucket on most leagues.
///
/// Measured on production 2026-09-17 (ux/1305): NBA rendered 11 of 64, NHL 4 of
/// 41, UCL 3 of 38.
///
/// Both directions are asserted, and the second one is the one that matters:
///
///   * no key we render is absent from the API  → the shipped defect;
///   * no key the API emits is unrendered by accident → the NEXT instance. A new
///     server-side section must fail this test rather than quietly never appear.
final class LeagueGridSectionKeysMatchTheAPI888Tests: XCTestCase {

    /// Exactly the dictionary `league_futures.py:2380` initialises. Order is the
    /// literal's; membership is what this test is about.
    private let apiSectionKeys: Set<String> = [
        "futures", "series", "matches", "awards", "props", "season_stats", "more_markets",
    ]

    /// Sections the API can emit that the league grid deliberately does not draw.
    /// Neither is populated for a team league and the API omits empty sections.
    /// Adding to this set is a decision; it should be hard to do by accident.
    private let deliberatelyNotRendered: Set<String> = ["futures", "matches"]

    // MARK: - The defect

    func testEverySectionWeRenderIsOneTheAPIActuallyEmits() {
        for key in LeagueGridView.sectionOrder {
            XCTAssertTrue(
                apiSectionKeys.contains(key),
                "sectionOrder renders '\(key)', which league_futures.py never emits — "
                + "the lookup misses silently, so every market behind it disappears with no empty state"
            )
        }
    }

    func testTheTwoDeadKeysAreGone() {
        XCTAssertFalse(LeagueGridView.sectionOrder.contains("playoff_props"))
        XCTAssertFalse(LeagueGridView.sectionOrder.contains("novelty"))
    }

    func testTheTwoKeysThatCarriedTheDroppedMarketsAreRendered() {
        XCTAssertTrue(
            LeagueGridView.sectionOrder.contains("props"),
            "props was never read — 31 of NCAAF's markets live here"
        )
        XCTAssertTrue(
            LeagueGridView.sectionOrder.contains("more_markets"),
            "more_markets is the classifier's DEFAULT bucket and the biggest section on most leagues"
        )
    }

    // MARK: - The next instance

    /// The arm that would have caught #888 the day the backend key set changed.
    func testNoAPISectionGoesUnrenderedWithoutBeingDeclared() {
        let rendered = Set(LeagueGridView.sectionOrder)
        let unrendered = apiSectionKeys.subtracting(rendered)
        XCTAssertEqual(
            unrendered, deliberatelyNotRendered,
            "an API section is neither rendered nor declared unrendered. A section the "
            + "grid does not know about is invisible to a reader and to this file. Either "
            + "render it or add it to deliberatelyNotRendered with a reason."
        )
    }

    /// `deliberatelyNotRendered` must name real sections — otherwise a typo in the
    /// exemption list silently re-opens the hole it exists to keep closed.
    func testTheExemptionListNamesRealSections() {
        for key in deliberatelyNotRendered {
            XCTAssertTrue(
                apiSectionKeys.contains(key),
                "'\(key)' is exempted from rendering but the API does not emit it either"
            )
        }
    }

    // MARK: - The three parallel collections cannot drift

    /// `sectionOrder`, `sectionLabels` and `sectionIcons` are three collections keyed
    /// by the same string. A key present in one and missing from another falls back to
    /// `key.capitalized` / `list.bullet` — which is how "More Markets" would silently
    /// become "More_markets" on a rename.
    func testEveryRenderedSectionHasALabelAndAnIcon() {
        for key in LeagueGridView.sectionOrder {
            XCTAssertNotNil(LeagueGridView.sectionLabels[key], "no label for '\(key)'")
            XCTAssertNotNil(LeagueGridView.sectionIcons[key], "no icon for '\(key)'")
        }
    }

    func testNoLabelOrIconIsStrandedOnAKeyNothingRenders() {
        let rendered = Set(LeagueGridView.sectionOrder)
        XCTAssertEqual(
            Set(LeagueGridView.sectionLabels.keys).subtracting(rendered), [],
            "a label survives for a key sectionOrder dropped — the leftovers of the #888 rename"
        )
        XCTAssertEqual(
            Set(LeagueGridView.sectionIcons.keys).subtracting(rendered), [],
            "an icon survives for a key sectionOrder dropped"
        )
    }

    // MARK: - The wording the rename settles

    /// "Playoff Props" was wrong on most leagues carrying the section — NCAAF's 31
    /// are not playoff props, and several of these leagues are not in a playoff.
    func testThePropsSectionIsNotLabelledAsPlayoffOnly() {
        XCTAssertEqual(LeagueGridView.sectionLabels["props"], "Props")
        XCTAssertEqual(LeagueGridView.sectionLabels["more_markets"], "More Markets")
    }
}
