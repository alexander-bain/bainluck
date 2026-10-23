import XCTest

/// #10877 — the iPhone props grid names what a reader taps: a prop line, as
/// the web grid does (PR #11551). "Question" stays an internal noun (types,
/// keys, functions); no literal a reader sees or hears in the grid says it.
final class PropsGridSaysPropLine10877Tests: XCTestCase {

    private func source(_ path: String) throws -> String {
        let url = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
            .appendingPathComponent("Bain Luck").appendingPathComponent(path)
        return try String(contentsOf: url, encoding: .utf8)
    }

    /// The literal text of every string passed straight to a reader-facing
    /// call, with `\( … )` interpolations removed (their code is not copy).
    private func readerLiterals(in text: String) -> [String] {
        let calls = ["Text(\"", ".accessibilityHint(\"", ".accessibilityLabel(\"", ".accessibilityValue(\"",
                     "Label(\"", "Button(\""]
        var found: [String] = []
        for call in calls {
            var search = text.startIndex..<text.endIndex
            while let hit = text.range(of: call, range: search) {
                var i = hit.upperBound
                var literal = ""
                var depth = 0
                var nestedString = false
                while i < text.endIndex {
                    let c = text[i]
                    if depth == 0 {
                        if c == "\\", text.index(after: i) < text.endIndex, text[text.index(after: i)] == "(" {
                            depth = 1
                            i = text.index(i, offsetBy: 2)
                            continue
                        }
                        if c == "\"" { break }
                        literal.append(c)
                    } else if nestedString {
                        if c == "\"" { nestedString = false }
                    } else if c == "\"" {
                        nestedString = true
                    } else if c == "(" {
                        depth += 1
                    } else if c == ")" {
                        depth -= 1
                    }
                    i = text.index(after: i)
                }
                found.append(literal)
                search = i..<text.endIndex
            }
        }
        return found
    }

    func testNoReaderLiteralInThePropsGridSaysQuestion() throws {
        let literals = readerLiterals(in: try source("Components/EventPropsMatrixView.swift"))
        XCTAssertGreaterThan(literals.count, 10, "the scan found too few reader strings to mean anything: \(literals)")
        let offenders = literals.filter { $0.localizedCaseInsensitiveContains("question") }
        XCTAssertEqual(offenders, [], "reader copy in the props grid still says question")
    }

    func testTheFiveEmptyUnavailableAndHintStringsSayPropLine() throws {
        let literals = readerLiterals(in: try source("Components/EventPropsMatrixView.swift"))
        for expected in ["This prop line isn't being offered right now.", "No prop lines for this stat",
                         "This prop line isn't available right now."] {
            XCTAssertTrue(literals.contains(expected), "missing: \(expected)")
        }
        XCTAssertEqual(literals.filter { $0 == "Shows this prop line and its sources" }.count, 2,
                       "the During and After cells both hint at the prop line")
    }

    /// The scanner itself: interpolated code is skipped, the copy around it is kept.
    func testTheScannerKeepsCopyAndDropsInterpolatedCode() {
        let sample = #"Text("\(row.subject.label) · \(EventPropsMatrixLayout.question(row, stat: "x")) left") "#
            + #".accessibilityHint("Shows this question")"#
        XCTAssertEqual(readerLiterals(in: sample), [" ·  left", "Shows this question"])
    }
}
