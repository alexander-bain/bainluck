import XCTest

@testable import Bain_Luck

/// #10313 / #10314 — two Discover cards that broke words apart at an
/// accessibility text size.
///
/// - #10313: the golf card's runner-up strip put three `percent · name` pairs in
///   one row, so each percent read "10" / "%" and the names cut to one or two
///   letters. At `isAccessibilitySize` the runners now stack one per line, and
///   the percent never wraps.
/// - #10314: the futures card's source mark sat in the footer row with the
///   price-age mark, signal bars and share button, and hyphenated as
///   "Polymar-" / "ket". At `isAccessibilitySize` the mark now takes its own
///   full-width line, where it wraps only between words.
///
/// Source-census guards, as in `WinProbabilityLabelTakesItsOwnLine8258Tests`: a
/// SwiftUI body is not reachable from XCTest here, so these pin the wiring that
/// the defects lived in. The renders are photographed on a simulator at a11y5
/// (see the PR).
final class DiscoverCardsKeepWholeWordsAtAccessibilitySizes10313Tests: XCTestCase {

    private func source(_ file: String) throws -> String {
        let here = URL(fileURLWithPath: #filePath)
        let url = here
            .deletingLastPathComponent()   // BainLuckTests
            .deletingLastPathComponent()   // Bain Luck (project dir)
            .appendingPathComponent("Bain Luck/Components/\(file)")
        return try String(contentsOf: url, encoding: .utf8)
    }

    /// Whitespace-collapsed, so the guards read structure rather than indentation.
    private func collapsed(_ text: String) -> String {
        text.components(separatedBy: .whitespacesAndNewlines)
            .filter { !$0.isEmpty }
            .joined(separator: " ")
    }

    private func occurrences(of needle: String, in haystack: String) -> Int {
        haystack.components(separatedBy: needle).count - 1
    }

    // MARK: #10313 — golf card runner-up strip

    func testTheRunnersStackAtAccessibilitySizes() throws {
        let text = collapsed(try source("DiscoverTournamentCard.swift"))
        XCTAssertEqual(
            occurrences(of: "let runnersStacked = dynamicTypeSize.isAccessibilitySize", in: text), 1,
            "the strip's shape is decided once, from the view's own text size")
        XCTAssertEqual(
            occurrences(of: "let runnerLayout = runnersStacked ? AnyLayout(VStackLayout(", in: text), 1,
            "at accessibility sizes the three runners need a line each")
        XCTAssertEqual(
            occurrences(of: ": AnyLayout(HStackLayout(spacing: 12))", in: text), 1,
            "below accessibility sizes the strip stays the row it always was")
        XCTAssertEqual(
            occurrences(of: "runnerLayout { ForEach(golfers.dropFirst().prefix(3))", in: text), 1,
            "the runners must be laid out by the chosen layout, not a fixed HStack")
    }

    func testARunnerPercentNeverWrapsItsPercentSign() throws {
        let text = collapsed(try source("DiscoverTournamentCard.swift"))
        let percent = "Text(FeedProbabilityScale.percentLabel(fromFraction: golfer.probability))"
            + " .font(.caption.bold()) .foregroundStyle(.white.opacity(0.9))"
        XCTAssertEqual(occurrences(of: percent, in: text), 1, "one runner percent in the strip")
        XCTAssertEqual(
            occurrences(of: percent + " .lineLimit(1) .fixedSize()", in: text), 1,
            "a runner percent without lineLimit(1)+fixedSize() breaks as '10' / '%'")
    }

    // MARK: #10314 — futures card source mark

    func testTheMarkTakesItsOwnLineAtAccessibilitySizes() throws {
        let text = collapsed(try source("DiscoverFuturesCard.swift"))
        XCTAssertEqual(
            occurrences(of: "let markOnOwnLine = dynamicTypeSize.isAccessibilitySize", in: text), 1,
            "the mark's placement is decided once, from the view's own text size")
        XCTAssertEqual(
            occurrences(of: "if markOnOwnLine, let mark = sourceMark { sourceMarkLabel(mark, onOwnLine: true) }", in: text), 1,
            "at accessibility sizes the mark needs its own full-width line above the footer row")
        XCTAssertEqual(
            occurrences(of: "HStack(spacing: 8) { if !markOnOwnLine, let mark = sourceMark { sourceMarkLabel(mark, onOwnLine: false) }", in: text), 1,
            "the in-row placement must be gated, or the mark is drawn twice and still squeezed")
    }

    func testTheMarkIsOneDefinition() throws {
        let text = try source("DiscoverFuturesCard.swift")
        XCTAssertEqual(occurrences(of: "Text(mark)", in: text), 1)
        XCTAssertEqual(
            occurrences(of: "sourceMarkLabel(", in: text), 3,
            "one declaration plus exactly two placements (own line, in row)")
    }

    func testTheMarkIsNeverPinnedToOneLine() throws {
        // The first repair pinned the mark with lineLimit(1)+fixedSize(). A
        // two-venue mark ("Kalshi + Polymarket") at a11y5 is wider than the card,
        // so the pinned mark made the footer row wider than the screen and pushed
        // the whole card off both edges (simulator, 2026-10-03). The mark may wrap
        // between words; it may never insist on one line.
        let text = collapsed(try source("DiscoverFuturesCard.swift"))
        guard let start = text.range(of: "private func sourceMarkLabel("),
              let end = text.range(of: "var body: some View", range: start.upperBound..<text.endIndex)
        else { return XCTFail("sourceMarkLabel must exist and precede body") }
        let definition = String(text[start.lowerBound..<end.lowerBound])
        XCTAssertFalse(definition.contains(".lineLimit(1)"), "a one-line mark overflows the card at a11y5")
        XCTAssertFalse(definition.contains(".fixedSize()"), "a fixed-width mark overflows the card at a11y5")
        XCTAssertEqual(
            occurrences(of: "if onOwnLine { label .fixedSize(horizontal: false, vertical: true)", in: definition), 1,
            "on its own line the mark wraps between words and keeps its full height")
    }
}
