import XCTest
@testable import Bain_Luck

/// #888 — the league surfaces rendered a fraction of the markets they had
/// already downloaded, and on the league page itself they rendered none.
///
/// A league surface walks `LeagueMarketSections.order` and reads
/// `leagueData.sections[key]`. A dictionary miss and an empty section are
/// **indistinguishable** at that call site — no empty state, no count, nothing
/// that says content was skipped — so two keys the API never emits
/// (`playoff_props`, `novelty`) hid everything behind them, and the two keys it
/// does emit (`props`, `more_markets`) were never read. `more_markets` is the
/// classifier's default return, which makes it the biggest bucket on most
/// leagues.
///
/// Measured on production 2026-09-17: applying the old key list to the served
/// NBA payload keeps 11 markets of 64; NHL 4 of 41; UCL 3 of 38. On the phone
/// the number was lower still — zero — because the payload also failed to
/// decode (`LeagueMarketsDecodeAgainstProduction888Tests`). Two independent
/// defects on one reader path; this file is the vocabulary half.
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

    // MARK: - The defect

    func testEverySectionWeRenderIsOneTheAPIActuallyEmits() {
        for key in LeagueMarketSections.order {
            XCTAssertTrue(
                apiSectionKeys.contains(key),
                "the catalog renders '\(key)', which league_futures.py never emits — "
                + "the lookup misses silently, so every market behind it disappears with no empty state"
            )
        }
    }

    func testTheTwoDeadKeysAreGone() {
        XCTAssertFalse(LeagueMarketSections.order.contains("playoff_props"))
        XCTAssertFalse(LeagueMarketSections.order.contains("novelty"))
    }

    func testTheTwoKeysThatCarriedTheDroppedMarketsAreRendered() {
        XCTAssertTrue(
            LeagueMarketSections.order.contains("props"),
            "props was never read — 31 of NCAAF's markets live here"
        )
        XCTAssertTrue(
            LeagueMarketSections.order.contains("more_markets"),
            "more_markets is the classifier's DEFAULT bucket and the biggest section on most leagues"
        )
    }

    // MARK: - The next instance

    /// The arm that would have caught #888 the day the backend key set changed.
    func testNoAPISectionGoesUnrenderedWithoutBeingDeclared() {
        let rendered = Set(LeagueMarketSections.order)
        let unrendered = apiSectionKeys.subtracting(rendered)
        XCTAssertEqual(
            unrendered, LeagueMarketSections.deliberatelyNotRendered,
            "an API section is neither rendered nor declared unrendered. A section the "
            + "surfaces do not know about is invisible to a reader and to this file. Either "
            + "render it or add it to deliberatelyNotRendered with a reason."
        )
    }

    /// `deliberatelyNotRendered` must name real sections — otherwise a typo in the
    /// exemption list silently re-opens the hole it exists to keep closed.
    func testTheExemptionListNamesRealSections() {
        for key in LeagueMarketSections.deliberatelyNotRendered {
            XCTAssertTrue(
                apiSectionKeys.contains(key),
                "'\(key)' is exempted from rendering but the API does not emit it either"
            )
        }
    }

    // MARK: - The three parallel collections cannot drift

    /// `order`, `labels` and `icons` are three collections keyed by the same
    /// string. A key present in one and missing from another falls through to the
    /// catalog's fallback — which is how "More Markets" would quietly become
    /// "More Markets" spelled from the key on a rename.
    func testEveryRenderedSectionHasALabelAndAnIcon() {
        for key in LeagueMarketSections.order {
            XCTAssertNotNil(LeagueMarketSections.labels[key], "no label for '\(key)'")
            XCTAssertNotNil(LeagueMarketSections.icons[key], "no icon for '\(key)'")
        }
    }

    func testNoLabelOrIconIsStrandedOnAKeyNothingRenders() {
        let rendered = Set(LeagueMarketSections.order)
        XCTAssertEqual(
            Set(LeagueMarketSections.labels.keys).subtracting(rendered), [],
            "a label survives for a key the order dropped — the leftovers of the #888 rename"
        )
        XCTAssertEqual(
            Set(LeagueMarketSections.icons.keys).subtracting(rendered), [],
            "an icon survives for a key the order dropped"
        )
    }

    // MARK: - The wording the rename settles

    /// "Playoff Props" was wrong on most leagues carrying the section — NCAAF's 31
    /// are not playoff props, and several of these leagues are not in a playoff.
    func testThePropsSectionIsNotLabelledAsPlayoffOnly() {
        XCTAssertEqual(LeagueMarketSections.label(for: "props"), "Props")
        XCTAssertEqual(LeagueMarketSections.label(for: "more_markets"), "More Markets")
    }

    // MARK: - There is ONE copy of the vocabulary

    /// **THE DEFECT WAS WRITTEN TWICE.** `LeagueGridView` and `SportCategoryView`
    /// each carried their own literal of these five keys, and both were wrong the
    /// same way — so repairing the one named on the issue would have left the golf,
    /// tennis and category surfaces dropping the same buckets, with the same
    /// silence. Every assertion above reads the catalog, so every assertion above
    /// is blind to a second copy; this is the arm that is not.
    ///
    /// Scans the shipped sources for a section key written anywhere but the
    /// catalog. `season_stats` and `more_markets` are the two keys that belong to
    /// no other vocabulary in this app — `novelty`, by contrast, is a legitimate
    /// `RelatedFuturesView` category and is deliberately NOT scanned for, because a
    /// guard that fires on a correct file gets deleted.
    func testNoViewKeepsItsOwnCopyOfTheSectionVocabulary() throws {
        let appSources = Self.projectDirectory.appendingPathComponent("Bain Luck")
        let catalog = "LeagueMarketSections.swift"
        var offenders: [String] = []

        let enumerator = try XCTUnwrap(
            FileManager.default.enumerator(at: appSources, includingPropertiesForKeys: nil),
            "could not walk \(appSources.path) — the scan proves nothing if it reads no files"
        )
        var scanned = 0
        for case let url as URL in enumerator where url.pathExtension == "swift" {
            guard url.lastPathComponent != catalog else { continue }
            guard let text = try? String(contentsOf: url, encoding: .utf8) else { continue }
            scanned += 1
            for key in ["\"season_stats\"", "\"more_markets\"", "\"playoff_props\""]
            where text.contains(key) {
                offenders.append("\(url.lastPathComponent) carries \(key)")
            }
        }

        // A scan that reads nothing passes for free, which is the failure mode of
        // every source-scanning test ever written.
        XCTAssertGreaterThan(scanned, 50, "the scan read only \(scanned) Swift files; it is not looking at the app")
        XCTAssertEqual(
            offenders, [],
            "a league section key is spelled outside LeagueMarketSections: \(offenders). "
            + "That is a second copy of the vocabulary, and #888 is what a second copy costs."
        )
    }

    /// `#filePath` is `…/Bain Luck/BainLuckTests/<this file>`, so two parents up is
    /// the project directory holding both the app sources and the test target.
    private static var projectDirectory: URL {
        URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()   // BainLuckTests
            .deletingLastPathComponent()   // Bain Luck (project dir)
    }
}
