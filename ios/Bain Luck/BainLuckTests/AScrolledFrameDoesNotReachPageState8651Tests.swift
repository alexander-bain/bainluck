import XCTest
@testable import Bain_Luck

/// #8651 — **no scrolled frame reaches the event page's state.**
///
/// Build 23 scrolled choppily on Alex's phone. The cause, measured on its own
/// source: #8320 held the hero's bottom edge — a number that changes on every
/// scrolled frame — in `EventDetailView` `@State`, so every frame of every
/// scroll rebuilt the whole page (105 rebuilds across eight ordinary swipes,
/// one per ~0.25 s). The page now keeps only the bar's decision, which the
/// hero's own `GeometryReader` makes and which changes only at the crossing.
///
/// The interactive half is `AnOrdinaryScrollDoesNotRebuildTheGamePage8651Tests`
/// (UI target, counts rebuilds under real swipes). This is the fast half: the
/// wiring lives in a `View` body, so it is pinned by a comment-stripped scan of
/// the one place the page reads the scroll's geometry.
final class AScrolledFrameDoesNotReachPageState8651Tests: XCTestCase {

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

    func testTheOnlyScrollGeometryReadIsTurnedIntoTheDecisionOnTheSpot() throws {
        let code = try pageCode()
        let reads = code.components(separatedBy: ".named(Self.scrollSpace)").count - 1
        XCTAssertEqual(reads, 1, "the page reads the scroll's geometry \(reads) times; #8651 audited one")
        XCTAssertTrue(code.contains(
            "value:Self.navTitleShowsScore(heroBottom:proxy.frame(in:.named(Self.scrollSpace)).maxY,"),
            "the hero's scrolled position is published raw again — it will rebuild the page every frame")
    }

    func testThePageHoldsTheDecisionNotAPosition() throws {
        let code = try pageCode()
        XCTAssertTrue(code.contains("@StateprivatevarnavShowsScore=true"),
                      "the bar's decision is no longer page state (an unmeasured hero keeps the score)")
        XCTAssertFalse(code.contains("varheroBottom"), "the hero's position is page state again")
        XCTAssertTrue(code.contains("privatestructNavShowsScorePreferenceKey:PreferenceKey{staticletdefaultValue:Bool?=nil"),
                      "the published value is no longer a decision — every frame will be a new value")
    }
}
