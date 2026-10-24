import XCTest
@testable import Bain_Luck

/// #9336 — the iPhone twin of web #6359 + #6853. The full-game margin card's
/// header printed `"\(abbr) \(Int((p * 100).rounded()))%"` in every lifecycle:
///
/// - Settled: Texans @ Colts (`/events/14782154`, FINAL 17–19) read `IND 93%`,
///   `current_odds.home_probability 0.9281` captured 50 s before the final
///   whistle, over the card's own `FINAL · IND by 2` tile.
/// - Live: an inline round, so a served 0.999 printed `100%` under a hero
///   reading `>99%`.
///
/// #9483 (Design, 2026-10-23) then removed the header in EVERY lifecycle: it
/// repeated the hero's blended winner over individually sourced venue rungs
/// (15195971: `OKC 56%` over `OKC by 1.5+ 62%`), which the card cannot present
/// as one family. So a settled card still prints no live price — no card
/// prints a header at all. `TheLiveMarginTileReadsTheHeadlinesPair9483Tests`
/// carries the live half.
final class AFinishedGamesMarginMapPrintsNoLivePrice9336Tests: XCTestCase {

    private func card() throws -> String {
        let root = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
        let file = root.appendingPathComponent("Bain Luck/Components/MarketMapView.swift")
        return try String(contentsOf: file, encoding: .utf8)
    }

    /// Every map card — full game and halves — hands `mapCard` an empty header,
    /// so no lifecycle can print a probability there.
    func testEveryMapCardPrintsNoHeader() throws {
        let source = try card()
        // Every argument passed under the label; the parameter's own
        // declaration (`headline: String`) is not a call.
        let headers = source.components(separatedBy: "headline: ").dropFirst()
            .map { $0.prefix(3) }.filter { $0 != "Str" }
        XCTAssertGreaterThanOrEqual(headers.count, 4, "the full-game card and the three other map cards")
        XCTAssertTrue(headers.allSatisfy { $0 == "\"\"," }, "a map card passes a header: \(headers)")
    }

    /// The probability the header used to print is not read at all.
    func testTheCardNoLongerTakesTheWinnerProbability() throws {
        let source = try card()
        XCTAssertFalse(source.contains("homeWinProb"))
        XCTAssertFalse(source.contains("awayWinProb"))
        XCTAssertFalse(source.contains("Int((side.probability * 100).rounded())"),
                       "an inline round skips both the settled rule and the >99%/<1% rule")
    }
}
