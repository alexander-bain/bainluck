import XCTest
@testable import Bain_Luck

/// #6268 — a source guard, and it knows what it is worth.
///
/// **The real guard is `BainLuckUITests/ATypeaheadRowIsTappableInItsMiddleTests`,**
/// which taps a short typeahead row at its own centre on a simulator and is red on
/// the unfixed build (verified: "tapped \"Boston Red Sox\" at the row's centre
/// (x=201.0, text ends at x=158.0) and the app did not navigate"). Hit-testing is
/// behaviour, and behaviour is measured by tapping.
///
/// This file exists because that test is in the UI target, and the gate a native
/// change routinely runs (`tools/native-gates.sh`) runs `BainLuckTests` — so a
/// refactor that drops the modifier would land green on the gate and be caught only
/// by whoever next remembered to run the UI scheme. It asserts the modifier is still
/// there and nothing more. **It cannot see whether the row is tappable**, and a green
/// here is not evidence that it is.
///
/// ═══ IT SCANS CODE, NOT PROSE ═══
///
/// The first draft counted `.buttonStyle(.plain)` over the raw text and read THREE in
/// a two-button list, because the fix's own comment explains the defect by naming the
/// modifier. A source-scanning guard whose answer moves when someone writes a sentence
/// is not measuring the source; every scan below runs over a comment-stripped copy.
final class TypeaheadRowHitAreaTests: XCTestCase {

    private var searchViewSource: String {
        get throws {
            // The test bundle sits inside DerivedData, so walk up to the repo from
            // this file's own path rather than guessing a working directory.
            let here = URL(fileURLWithPath: #filePath)          // …/BainLuckTests/this.swift
            let root = here
                .deletingLastPathComponent()                    // BainLuckTests
                .deletingLastPathComponent()                    // Bain Luck (project dir)
            let path = root
                .appendingPathComponent("Bain Luck/Views/SearchView.swift")
            return try String(contentsOf: path, encoding: .utf8)
        }
    }

    /// `suggestionList`'s body with `//` comments removed.
    ///
    /// Over-stripping is the safe direction and it is deliberate: a `//` inside a
    /// string literal would cut real code, and every assertion below would then go
    /// RED rather than quietly pass on a shorter body. A guard that fails closed on
    /// its own parsing is worth more than one that is clever about Swift's grammar.
    private func suggestionListCode(_ source: String) throws -> String {
        let start = try XCTUnwrap(
            source.range(of: "private var suggestionList: some View {"),
            "suggestionList is gone or renamed — re-aim this guard, do not delete it"
        )
        let rest = source[start.upperBound...]
        let end = rest.range(of: "// MARK:")?.lowerBound ?? rest.endIndex
        return String(rest[..<end])
            .split(separator: "\n", omittingEmptySubsequences: false)
            .map { line -> Substring in
                guard let comment = line.range(of: "//") else { return line }
                return line[..<comment.lowerBound]
            }
            .joined(separator: "\n")
    }

    /// Both `.buttonStyle(.plain)` rows in `suggestionList` — the suggestion rows and
    /// the "Showing results for" row above them — carry an explicit hit shape.
    ///
    /// Two, not one: the did-you-mean row has the same defect in a different dress
    /// (its content is a short caption, so the rest of the row took no touches), and
    /// fixing only the row the issue named is how a class comes back one component
    /// over.
    func testTheSuggestionRowsDeclareAHitShape() throws {
        let body = try suggestionListCode(try searchViewSource)

        // Split at each `.buttonStyle(.plain)` and look at the text BEFORE it — the
        // row that button styles. A bare count of each modifier over the whole list
        // would be satisfied by two hit shapes on one row and none on the other,
        // which is precisely the state this guard exists to refuse.
        let segments = body.components(separatedBy: ".buttonStyle(.plain)")
        let plainButtons = segments.count - 1
        XCTAssertEqual(
            plainButtons, 2,
            "suggestionList's shape changed (\(plainButtons) plain buttons, expected 2). "
            + "If a row was added, it needs a hit shape too — see #6268."
        )

        for (index, rowSource) in segments.dropLast().enumerated() {
            XCTAssertTrue(
                rowSource.contains(".contentShape(Rectangle())"),
                "#6268: plain-button row \(index + 1) of \(plainButtons) in the typeahead "
                + "list has no `.contentShape(Rectangle())`. `.plain` hit-tests the "
                + "rendered content and a `Spacer()` renders nothing, so without it the "
                + "middle of a short row is dead — measured: \"Boston Red Sox\" ends at "
                + "x=158 in a 402pt row, and a tap at x=201 did nothing at all."
            )
        }
    }

    /// The did-you-mean row must also be made full width, or its hit shape is only as
    /// wide as the caption and the fix is cosmetic.
    ///
    /// The suggestion rows below it need no such frame: their `HStack` holds a
    /// `Spacer()`, which is what made their centres dead in the first place and is
    /// also what makes them full width already.
    func testTheDidYouMeanRowIsWidenedBeforeItIsShaped() throws {
        let body = try suggestionListCode(try searchViewSource)
        let didYouMeanRow = try XCTUnwrap(
            body.components(separatedBy: ".buttonStyle(.plain)").first,
            "suggestionList has no rows at all — re-aim this guard"
        )
        XCTAssertTrue(
            didYouMeanRow.contains("Text(\"Showing results for\")"),
            "the did-you-mean row is no longer the FIRST plain-button row in "
            + "suggestionList, so this guard is now reading a different row — re-aim it"
        )
        XCTAssertTrue(
            didYouMeanRow.contains(".frame(maxWidth: .infinity"),
            "#6268: `.contentShape` on a row that does not fill its width only makes "
            + "the caption tappable. The did-you-mean row needs the frame too."
        )
    }

    /// The guard is only worth anything if it is pointed at a file that exists and can
    /// be read — a `try?` that swallowed a bad path would make every assertion above
    /// vacuous without failing.
    func testTheGuardCanActuallyReadTheFileItGuards() throws {
        let source = try searchViewSource
        XCTAssertGreaterThan(source.count, 10_000, "read something far too small to be SearchView.swift")
        XCTAssertTrue(source.contains("struct SearchView: View"))

        // And that the comment stripping did not eat the body it is meant to hand on.
        let body = try suggestionListCode(source)
        XCTAssertTrue(body.contains("ForEach(viewModel.suggestions)"), "the stripped body is not suggestionList")
        XCTAssertFalse(body.contains("#6268 —"), "comments survived the strip, so the counts above are prose-sensitive")
    }
}
