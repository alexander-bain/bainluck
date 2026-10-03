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
///   "Polymar-" / "ket". The mark now keeps its whole width.
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

    func testTheSourceMarkKeepsItsWholeWidth() throws {
        let text = collapsed(try source("DiscoverFuturesCard.swift"))
        let mark = "Text(mark) .font(.caption2.weight(.heavy))"
        XCTAssertEqual(occurrences(of: mark, in: text), 1, "one source mark on the card")
        XCTAssertEqual(
            occurrences(of: mark + " .lineLimit(1) .fixedSize()", in: text), 1,
            "a source mark without lineLimit(1)+fixedSize() hyphenates as 'Polymar-' / 'ket'")
    }
}
