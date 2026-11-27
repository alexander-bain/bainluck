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

    private func cardCode() throws -> String {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()   // BainLuckTests
            .deletingLastPathComponent()   // Bain Luck (project dir)
            .appendingPathComponent("Bain Luck")
            .appendingPathComponent("Components")
            .appendingPathComponent("EventSportHeadlineCard12472.swift")
        return try String(contentsOf: url, encoding: .utf8)
            .split(separator: "\n", omittingEmptySubsequences: false)
            .map { line -> String in
                guard let slashes = line.range(of: "//") else { return String(line) }
                return String(line[line.startIndex..<slashes.lowerBound])
            }
            .joined(separator: "\n")
            .filter { !$0.isWhitespace }
    }

    /// Direction 199 replaced the centered verdict column in `EventDetailView`
    /// with unified horizontal rows in `EventSportHeadlineCard12472` where team
    /// names size to `sharedTeamNameFontSize`, reserve the winner tick, and
    /// stay cleanly inside the row alongside crests and `Pregame | Final`.
    func testTheWinnerVerdictIsBoundedToTheSlot() throws {
        let card = try cardCode()
        XCTAssertTrue(card.contains("privatefunccompetitorIdentityStack(_row:EventSportHeadlines12472.CompetitorRow)->someView{"),
                      "control: scan reads competitorIdentityStack")
        XCTAssertTrue(card.contains("scaledSize:sharedTeamNameFontSize)"),
                      "team names in the unified headline stopped sizing to sharedTeamNameFontSize")
        XCTAssertTrue(card.contains(".lineLimit(1).minimumScaleFactor(stacksRowsVertically?0.72:0.80)"),
                      "the bounded team name row lost its single-line scaling")
        XCTAssertTrue(card.contains("ifreservesWinnerTick{"),
                      "the unified finished hero no longer reserves the winner tick slot")
    }

    func testTheNamedPregameCaptionIsBoundedToTheSlot() throws {
        let card = try cardCode()
        XCTAssertTrue(card.contains("privatevarsharedTeamNameFontSize:CGFloat{"),
                      "control: scan reads sharedTeamNameFontSize")
        XCTAssertTrue(card.contains("max(measuredInnerWidth-crestSize-16-totalColumnsWidth,64)"),
                      "horizontal name budget stopped reserving crest and trailing Pregame | Final column widths")
    }

    func testTheSlotIsStillUnderAThirdOfAnIPhone() {
        // 402pt iPhone 17: two crest columns share what the slot leaves.
        XCTAssertLessThanOrEqual(EventDetailView.verdictSlotWidth, 402 / 2.5)
    }
}
