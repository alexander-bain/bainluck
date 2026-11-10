import XCTest
@testable import Bain_Luck

/// #12312 (the game page) — the page's small fixed point sizes grow with the
/// reader's text size. At the default size each scaled size starts at exactly
/// the point size it replaced, so nothing moves for a reader who never changed
/// the setting.
final class GamePageFontsScale12312Tests: XCTestCase {

    /// The literal sizes left on purpose, by file:
    /// - the game page: the 1 pt build counter (invisible) and the two toolbar
    ///   glyphs, which the navigation bar sizes;
    /// - the odds chart: the period chips, whose placement measures their width
    ///   at that size (`PeriodChipGeometry`);
    /// - the chart key: the overlay word, placed by measured geometry the same way.
    func testOnlyTheDeliberateFixedSizesRemain() throws {
        XCTAssertEqual(try Self.literalSizes(in: "Views/EventDetailView.swift", before: "private struct NavShowsScorePreferenceKey"),
                       ["1", "13", "14"])
        XCTAssertEqual(try Self.literalSizes(in: "Components/OddsChartView.swift", before: nil), ["10"])
        XCTAssertEqual(try Self.literalSizes(in: "Components/EventAtlasChartMarks11666.swift", before: nil), ["10"])
    }

    func testEachScaledSizeStartsAtTheSizeItReplaced() throws {
        let page = try Self.source("Views/EventDetailView.swift")
        XCTAssertTrue(page.contains("@ScaledMetric(relativeTo: .caption2) private var glyph8Size12312: CGFloat = 8"))
        XCTAssertTrue(page.contains("@ScaledMetric(relativeTo: .caption2) private var text10Size12312: CGFloat = 10"))
        XCTAssertTrue(page.contains("@ScaledMetric(relativeTo: .caption) private var text12Size12312: CGFloat = 12"))
        XCTAssertTrue(page.contains("@ScaledMetric(relativeTo: .title3) private var score20Size12312: CGFloat = 20"))
        let chart = try Self.source("Components/OddsChartView.swift")
        XCTAssertTrue(chart.contains("@ScaledMetric(relativeTo: .caption) private var expandGlyphSize12312: CGFloat = 12"))
        XCTAssertTrue(chart.contains("@ScaledMetric(relativeTo: .caption2) private var chevronSize12312: CGFloat = 8"))
        let key = try Self.source("Components/EventAtlasChartMarks11666.swift")
        XCTAssertTrue(key.contains("@ScaledMetric(relativeTo: .caption2) private var badgeSize12312: CGFloat = 9"))
    }

    func testTheScaledSizesAreTheOnesDrawn() throws {
        let page = try Self.source("Views/EventDetailView.swift")
        XCTAssertEqual(page.components(separatedBy: "size: text10Size12312").count - 1, 5,
                       "Game Info's rows, the bookmaker heading and the opening caption")
        XCTAssertEqual(page.components(separatedBy: "size: score20Size12312").count - 1, 2, "both scores")
        XCTAssertEqual(page.components(separatedBy: "size: glyph8Size12312").count - 1, 2)
        XCTAssertEqual(page.components(separatedBy: "size: text12Size12312").count - 1, 1)
        let chart = try Self.source("Components/OddsChartView.swift")
        XCTAssertEqual(chart.components(separatedBy: "size: chevronSize12312").count - 1, 2)
        XCTAssertEqual(chart.components(separatedBy: "size: expandGlyphSize12312").count - 1, 1)
        let key = try Self.source("Components/EventAtlasChartMarks11666.swift")
        XCTAssertEqual(key.components(separatedBy: "size: badgeSize12312").count - 1, 2)
    }

    // MARK: - Helpers

    static func source(_ relative: String) throws -> String {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent().deletingLastPathComponent()
            .appendingPathComponent("Bain Luck/\(relative)")
        return try String(contentsOf: url, encoding: .utf8)
    }

    /// Every `.font(.system(size: <number>` in the file (up to `before`, when given), in order.
    static func literalSizes(in relative: String, before marker: String?) throws -> [String] {
        var text = try source(relative)
        if let marker, let cut = text.range(of: marker) { text = String(text[..<cut.lowerBound]) }
        let regex = try NSRegularExpression(pattern: #"\.font\(\.system\(size:\s*([0-9.]+)"#)
        return regex.matches(in: text, range: NSRange(text.startIndex..., in: text)).compactMap {
            Range($0.range(at: 1), in: text).map { String(text[$0]) }
        }
    }
}
