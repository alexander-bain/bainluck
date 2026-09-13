import XCTest
@testable import Bain_Luck

/// #5872 — a futures browse row with no price must say nothing about why.
///
/// `FuturesBrowseMarketRow` drew "Outcomes update when market prices are
/// available" in the body of every unpriced card. That is a sentence explaining
/// an emptiness, which notice 34 / D102 forbids on a reader's screen: "If a
/// number cannot be shown honestly, leave the space empty; do not explain the
/// emptiness in a paragraph." Photographed on production 2026-09-13 09:19Z,
/// `artifacts-native-142/futureslist.png`, directly above a row that had a price
/// and just showed it.
///
/// THIS GUARD IS A SOURCE SCAN, and that is the only instrument available: the
/// branch is an inline `if` inside a `ViewBuilder` with no value to assert on,
/// and lifting it into a testable predicate would be inventing a function to
/// have something to call. So the scan carries the whole weight, and every rule
/// below is written to survive a REWORDING rather than to pin one string — a
/// ban on an exact sentence is satisfied by "Outcomes will update once market
/// prices arrive", which is the same defect.
final class FuturesRowSaysNothingAboutAbsence5872Tests: XCTestCase {

    private func browseSource() throws -> String {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()   // BainLuckTests
            .deletingLastPathComponent()   // Bain Luck (project dir)
            .appendingPathComponent("Bain Luck")
            .appendingPathComponent("Components")
            .appendingPathComponent("FuturesBrowseComponents.swift")
        return try String(contentsOf: url, encoding: .utf8)
    }

    /// 🔴 COMMENTS STRIPPED FIRST. Every claim below is about CODE. This fix
    /// wrote the banned sentence into a comment beside the line it removed, so
    /// a scan that read the whole file would pass, then fail the day the comment
    /// is tidied, then pass forever once someone deletes the rule to fix it.
    private func browseCode() throws -> String {
        try browseSource()
            .split(separator: "\n", omittingEmptySubsequences: false)
            .map { line -> String in
                guard let slashes = line.range(of: "//") else { return String(line) }
                return String(line[line.startIndex..<slashes.lowerBound])
            }
            .joined(separator: "\n")
    }

    /// Anti-vacuity: if this fails, every rule below is asserting about the
    /// wrong file, or about nothing, and the comment-stripper has eaten the code.
    func testTheScanCanSeeTheFileItIsAbout() throws {
        let code = try browseCode()
        XCTAssertGreaterThan(code.count, 2_000, "the scan read something far too short to be FuturesBrowseComponents")
        XCTAssertTrue(code.contains("struct FuturesBrowseMarketRow"),
                      "the scan did not find the row it is about")
        XCTAssertTrue(code.contains("market.topOutcomes"),
                      "the scan did not find the branch it is about")
    }

    /// The defect itself, and the rewordings of it. Each phrase is a way of
    /// saying "there is no price here, and here is why", which is the class —
    /// not the one sentence that happened to ship.
    func testNoCopyExplainsWhyAPriceIsMissing() throws {
        let code = try browseCode().lowercased()
        for phrase in [
            "market prices are available",
            "prices are available",
            "update when",
            "will update",
            "when available",
            "not yet priced",
            "no outcomes yet",
            "check back",
        ] {
            XCTAssertFalse(
                code.contains(phrase),
                "\"\(phrase)\" is back in FuturesBrowseComponents — an unpriced row is explaining itself again")
        }
    }

    /// The other direction, and the one a "delete the whole branch" mutant
    /// fails: a row that HAS prices must still draw them. Without this, the
    /// rule above is satisfied by a row that shows no outcomes at all.
    func testAPricedRowStillDrawsItsOutcomes() throws {
        let code = try browseCode()
        XCTAssertTrue(
            code.contains("if let outcomes = market.topOutcomes, !outcomes.isEmpty {"),
            "the priced branch's own condition is gone")
        XCTAssertTrue(
            code.contains("FuturesBrowseOutcomeRow(outcome: outcome, tint: category.color)"),
            "the row stopped drawing its outcomes — this fix removed the prices, not the apology")
    }

    /// The branch takes no `else` at all. Pinned separately from the phrase ban
    /// because the next thing to land in that slot will not be one of the eight
    /// phrases above: an empty `Text("")`, a spacer, or a placeholder all put
    /// something back where nothing belongs.
    func testTheUnpricedBranchHasNoElse() throws {
        let code = try browseCode()
        guard let branch = code.range(of: "if let outcomes = market.topOutcomes, !outcomes.isEmpty {") else {
            return XCTFail("the branch this test is about is gone; testAPricedRowStillDrawsItsOutcomes says why")
        }
        // The 400 characters after the branch opens comfortably cover its body
        // (a VStack, a ForEach, one row) and any `else` hung off its close.
        let window = code[branch.lowerBound..<code.index(branch.lowerBound, offsetBy: 400, limitedBy: code.endIndex)!]
        XCTAssertFalse(
            window.contains("} else {"),
            "the unpriced branch grew an else again — an unpriced row draws nothing")
    }
}
