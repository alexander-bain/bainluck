import XCTest

@testable import Bain_Luck

/// #8258 — on the Discover live game card at an accessibility text size, the
/// strip's centre label read "Win" / "Probabili-" / "ty" and each percentage
/// wrapped its `%` onto a second line: the label sat in an `HStack` between two
/// `.title3` numerals and got whatever width they left.
///
/// The repair: at `isAccessibilitySize` the label leaves the row for its own
/// full-width line above it, and the numerals never wrap. Below accessibility
/// sizes the row is the one it always was.
///
/// Source-census guards, as in `DiscoverCardDynamicTypeTests`: a SwiftUI body is
/// not reachable from XCTest here, so these pin the wiring that the defect lived
/// in. The render itself is photographed on a simulator at a11y5 (see the PR).
final class WinProbabilityLabelTakesItsOwnLine8258Tests: XCTestCase {

    private func cardSource() throws -> String {
        let here = URL(fileURLWithPath: #filePath)
        let url = here
            .deletingLastPathComponent()   // BainLuckTests
            .deletingLastPathComponent()   // Bain Luck (project dir)
            .appendingPathComponent("Bain Luck/Components/DiscoverEventCard.swift")
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

    func testTheDecisionIsTheAccessibilityTextSize() throws {
        let text = collapsed(try cardSource())
        XCTAssertEqual(
            occurrences(of: "let labelOnOwnLine = dynamicTypeSize.isAccessibilitySize", in: text), 1,
            "the label moves off the row at accessibility sizes, decided once from the view's own text size")
    }

    func testTheLabelIsDrawnOnItsOwnLineAtAccessibilitySizes() throws {
        let text = collapsed(try cardSource())
        XCTAssertEqual(
            occurrences(of: "if labelOnOwnLine { winProbabilityLabel", in: text), 1,
            "at accessibility sizes the label needs its own line above the numerals")
    }

    func testBothInlinePlacementsStepAsideAtAccessibilitySizes() throws {
        // Two strip shapes: the pair (away · label · home) and the lone named
        // number (label · side · number). If either drew the label inline
        // unconditionally, it would print twice at a11y sizes and still be
        // squeezed in the row.
        let text = collapsed(try cardSource())
        XCTAssertEqual(
            occurrences(of: "if !labelOnOwnLine { winProbabilityLabel", in: text), 2,
            "both inline placements must be gated, or the label is drawn twice and still squeezed")
    }

    func testTheLabelIsOneDefinition() throws {
        // One literal, so the inline and own-line copies cannot drift in wording.
        let text = try cardSource()
        XCTAssertEqual(occurrences(of: "Text(\"Win Probability\")", in: text), 1)
        XCTAssertEqual(
            occurrences(of: "winProbabilityLabel", in: text), 4,
            "one declaration plus exactly three placements (own line, pair inline, lone inline)")
    }

    func testTheStripNumeralsNeverWrapTheirPercentSign() throws {
        // Every `.title3` black numeral in this card is a strip numeral; each one
        // keeps its whole width so `39` and `%` stay on one line.
        let text = collapsed(try cardSource())
        let numeral = ".font(.title3.weight(.black).monospacedDigit())"
        let guarded = numeral + " .lineLimit(1) .fixedSize()"
        let total = occurrences(of: numeral, in: text)
        XCTAssertEqual(total, 3, "the pair's two numerals plus the lone number")
        XCTAssertEqual(
            occurrences(of: guarded, in: text), total,
            "a strip numeral without lineLimit(1)+fixedSize() can break its % onto a second line")
    }
}
