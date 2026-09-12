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
        XCTAssertTrue(source.contains("fullMarginMap"), "scan did not find a control symbol")
        XCTAssertTrue(source.contains("halfTotalMaps"), "scan did not find a control symbol")
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
    func testEachColumnHasExactlyOneDefinitionSharedByBothBranches() throws {
        let source = try marketMapSource()
        for column in ["marginCards", "totalCards"] {
            XCTAssertEqual(
                occurrences(of: "private var \(column)", in: source), 1,
                "\(column) must be declared exactly once"
            )
            // Once in the wide branch, once in the narrow branch.
            XCTAssertEqual(
                occurrences(of: column, in: source) - 1, 2,
                "\(column) must be rendered by BOTH layout branches, so neither can drift"
            )
        }
    }

    /// The cards themselves must not have been dropped along with the headers —
    /// a "fix" that removed the maps would also pass the assertions above.
    ///
    /// Counted, not merely `contains`: every one of these is DECLARED in this
    /// file, so a presence check passes even when nothing renders it. Two is a
    /// declaration plus at least one render site; one is an orphan.
    func testTheCardsThemselvesSurvive() throws {
        let source = try marketMapSource()
        for card in ["fullMarginMap", "halfMarginMaps", "fullTotalMap", "halfTotalMaps"] {
            XCTAssertGreaterThanOrEqual(
                occurrences(of: card, in: source), 2,
                "\(card) is declared but never rendered — the card was dropped, not just its header"
            )
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
