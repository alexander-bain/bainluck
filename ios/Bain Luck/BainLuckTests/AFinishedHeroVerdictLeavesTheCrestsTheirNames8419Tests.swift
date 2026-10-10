import XCTest
@testable import Bain_Luck

/// #8419 — A FINISHED HERO'S VERDICT LEAVES THE CRESTS THEIR NAMES.
///
/// Event `15313874` (Real Salt Lake 0 – 2 Seattle Sounders FC, Final): the
/// verdict "Seattle Sounders FC Win" and its caption "Pre-match Seattle
/// Sounders FC 55%" sat unbounded in the hero's fixed-size centre column, took
/// nearly the whole card, and cut the home crest's name to "Seattle Sounder…".
/// (`artifacts/native-8419/before-15313874.png` / `after-15313874.png`; the
/// short-verdict control `after-control-14780546.png` still reads
/// "Falcons Win" on one line.)
///
/// The pair's label is the FULL name whenever the short one would collide
/// (#3430), so its length is not ours to choose. Both lines take the same cap
/// the venue verdict already carries (`verdictSlotWidth`). The wiring lives in
/// a `View` body, so it is pinned by a comment-stripped source scan
/// (`ALiveHeroCarriesTheStoryNotTheContext8320Tests` is the model).
final class AFinishedHeroVerdictLeavesTheCrestsTheirNames8419Tests: XCTestCase {

    private func pageCode() throws -> String {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()   // BainLuckTests
            .deletingLastPathComponent()   // Bain Luck (project dir)
            .appendingPathComponent("Bain Luck")
            .appendingPathComponent("Views")
            .appendingPathComponent("EventDetailView.swift")
        return try String(contentsOf: url, encoding: .utf8)
            .split(separator: "\n", omittingEmptySubsequences: false)
            .map { line -> String in
                guard let slashes = line.range(of: "//") else { return String(line) }
                return String(line[line.startIndex..<slashes.lowerBound])
            }
            .joined(separator: "\n")
            .filter { !$0.isWhitespace }
    }

    /// The modifier chain of the `Text` opened by `anchor` (which must occur
    /// exactly once), up to the brace that closes its branch.
    private func chain(after anchor: String,
                       file: StaticString = #filePath, line: UInt = #line) throws -> String {
        let code = try pageCode()
        let hits = code.components(separatedBy: anchor).count - 1
        XCTAssertEqual(hits, 1, "anchor \(anchor) found \(hits) times", file: file, line: line)
        let lower = try XCTUnwrap(code.range(of: anchor), file: file, line: line)
        let upper = try XCTUnwrap(code.range(of: "}", range: lower.upperBound..<code.endIndex),
                                  file: file, line: line)
        return String(code[lower.upperBound..<upper.lowerBound])
    }

    func testTheWinnerVerdictIsBoundedToTheSlot() throws {
        let verdict = try chain(after: #"Text("\(winnerName)Win")"#)
        XCTAssertTrue(verdict.contains(".frame(maxWidth:Self.heroVerdictWidth(at:dynamicTypeSize))"),
                      "the finished verdict is unbounded again — a long winner name squeezes the crest names")
        XCTAssertTrue(verdict.contains(".lineLimit(2)"),
                      "the bounded verdict must be allowed to wrap, or it truncates itself instead")
        XCTAssertTrue(verdict.contains(".multilineTextAlignment(.center)"))
    }

    func testTheNamedPregameCaptionIsBoundedToTheSlot() throws {
        let caption = try chain(
            after: #"Text("\(pregameWord)\(named.home)\(formatProbability(opened.home))")"#)
        XCTAssertTrue(caption.contains(".frame(maxWidth:Self.heroVerdictWidth(at:dynamicTypeSize))"),
                      "the named pre-match caption is unbounded — it carries the same full name as the verdict")
        XCTAssertTrue(caption.contains(".lineLimit(2)"))
    }

    func testTheSlotIsStillUnderAThirdOfAnIPhone() {
        // 402pt iPhone 17: two crest columns share what the slot leaves.
        XCTAssertLessThanOrEqual(EventDetailView.verdictSlotWidth, 402 / 2.5)
    }
}
