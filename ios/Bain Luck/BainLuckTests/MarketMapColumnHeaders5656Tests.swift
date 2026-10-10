import XCTest
@testable import Bain_Luck

/// #5656 — a football match page printed `MARGIN MAPS` and `TOTAL MAPS`.
///
/// THE PHOTOGRAPH. ŠK Slovan Bratislava @ Paris Saint-Germain, a Champions
/// League tie, iPad Pro 13-inch (M5) simulator, 2026-09-12 —
/// `artifacts-native-020/ipad-02-event.png`. The card under `TOTAL MAPS` is the
/// "Goals map / Final goals" slider. "Map" is a Counter-Strike round; over a
/// football match it names nothing a reader has, and it sits directly above a
/// card that already titles itself.
///
/// THE MECHANISM. Both headers lived in `MarketMapView`'s WIDE branch only. The
/// narrow branch rendered the same two cards with no headers, so the iPhone had
/// never shown the words and the iPad always had — which is the real finding,
/// and it is bigger than two strings: **the wide layout is not the narrow layout
/// with more room, it is a second layout nobody walks.**
///
/// THE FIX is therefore structural as well as textual. Each column's cards are
/// now one `@ViewBuilder` rendered by both branches, so a label cannot be added
/// to the iPad alone — it appears on both or neither. That is standing notice 35
/// (no bespoke label because a page is wider) made impossible to break rather
/// than asked for in a comment.
///
/// WHAT THIS TEST IS WORTH. It is a source scan, so its failure mode is passing
/// because it read nothing. `testTheScanCanSeeTheFileItIsAbout` is the guard on
/// that: it asserts the scan finds the file AND finds a control string that is
/// certainly in it. Without that, every assertion here would pass on an empty
/// read.
final class MarketMapColumnHeaders5656Tests: XCTestCase {

    /// The shipping source of the view under test, walked from this test's own
    /// location — the idiom `ChartGutterLabelShapeTests` established.
    private func marketMapSource() throws -> String {
        let here = URL(fileURLWithPath: #filePath)
        let url = here
            .deletingLastPathComponent()   // BainLuckTests
            .deletingLastPathComponent()   // Bain Luck (project dir)
            .appendingPathComponent("Bain Luck")
            .appendingPathComponent("Components")
            .appendingPathComponent("MarketMapView.swift")
        return try String(contentsOf: url, encoding: .utf8)
    }

    // MARK: - Anti-vacuity

    /// If this fails, every other test in this file is asserting about an empty
    /// string and means nothing.
    func testTheScanCanSeeTheFileItIsAbout() throws {
        let source = try marketMapSource()
        XCTAssertGreaterThan(source.count, 5_000, "the scan read a file far too short to be MarketMapView")
        // Control strings: things that are certainly in this file. If the read
        // ever silently returns the wrong file, these go first.
        XCTAssertTrue(source.contains("struct MarketMapView"), "scan did not find MarketMapView's own declaration")
        XCTAssertTrue(source.contains("marginMapCard"), "scan did not find a control symbol")
        XCTAssertTrue(source.contains("halfTotalCard"), "scan did not find a control symbol")
    }

    // MARK: - The defect

    /// The two headers are gone. Rendered, not merely renamed — a reworded
    /// header would still be a label the phone does not have.
    func testNeitherColumnHeaderIsRenderedAnyMore() throws {
        let source = try marketMapSource()
        for header in ["MARGIN MAPS", "TOTAL MAPS"] {
            XCTAssertFalse(
                source.contains("Text(\"\(header)\")"),
                "\(header) is back on the iPad's event page — #5656"
            )
        }
    }

    /// The general rule behind #5656, not just its two instances: esports
    /// vocabulary has no place on a page that may be showing football.
    ///
    /// Scoped to strings the view RENDERS (`Text("…")`) rather than to the whole
    /// file, because "map" is the codebase's own word for this control —
    /// `MarketMapView`, `fullMarginMap`, `SpreadRungs.map` — and banning the
    /// substring outright would be banning the type's name.
    func testNoRenderedLiteralShoutsMAPS() throws {
        let source = try marketMapSource()
        let offenders = renderedLiterals(in: source).filter { $0.uppercased().contains("MAPS") }
        XCTAssertTrue(
            offenders.isEmpty,
            "these rendered strings say MAPS on a page that may be a football match: \(offenders)"
        )
    }

    // MARK: - The structural half

    /// Each column is one definition, rendered by both branches. This is what
    /// stops the iPad growing a label the iPhone lacks — the mechanism behind
    /// #5656, as opposed to its two symptoms.
    // #10830 — the two branches are now ONE: the maps are a single browsable
    // list on every size class, which is #5656's finding (the wide layout is a
    // second layout nobody walks) taken to its end. So the structural guard is
    // that no size-class branch exists to drift, and that the one list routes
    // every kind of card.
    func testThereIsOneLayoutForEverySizeClass() throws {
        let source = try marketMapSource()
        XCTAssertFalse(source.contains("horizontalSizeClass"),
                       "a size-class read is back — that is a second layout to drift")
        XCTAssertFalse(source.contains("useColumns"), "the column branch is back")
        XCTAssertEqual(occurrences(of: "var mapEntries: [MapEntry]", in: source), 1,
                       "the map list must be declared exactly once")
        XCTAssertEqual(occurrences(of: "items: mapEntries", in: source), 1,
                       "the map list must be what the one layout browses")
    }

    func testTheCardsThemselvesSurvive() throws {
        let source = try marketMapSource()
        let router = try XCTUnwrap(source.range(of: "func mapEntryCard(_ entry: MapEntry)"),
                                   "the card router is gone")
        let body = String(source[router.upperBound...].prefix(800))
        for card in ["marginMapCard", "halfMarginCard(", "totalMapCard", "halfTotalCard("] {
            XCTAssertTrue(body.contains(card),
                          "\(card) is no longer routed — the card was dropped, not just its header")
        }
    }

    // MARK: - Helpers

    /// Every `Text("…")` literal in the source — what a reader can actually be
    /// shown from this file.
    private func renderedLiterals(in source: String) -> [String] {
        var found: [String] = []
        var rest = Substring(source)
        while let open = rest.range(of: "Text(\"") {
            rest = rest[open.upperBound...]
            guard let close = rest.range(of: "\"") else { break }
            found.append(String(rest[..<close.lowerBound]))
            rest = rest[close.upperBound...]
        }
        return found
    }

    private func occurrences(of needle: String, in haystack: String) -> Int {
        var count = 0
        var rest = Substring(haystack)
        while let hit = rest.range(of: needle) {
            count += 1
            rest = rest[hit.upperBound...]
        }
        return count
    }
}
