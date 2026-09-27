import XCTest
@testable import Bain_Luck

/// #9109 — **the iPhone /politics card's "+N more" promised rows its page does
/// not have.**
///
/// `PoliticsView` printed `+\(outcomeCount - 3) more`. `outcome_count` is every
/// rung the ladder ever had, including passed deadlines, and since #7784 the
/// page the card opens drops those. On production 2026-09-27 14:25Z, 16 of the
/// 68 `/api/politics` cards printed a number that disagreed with their page:
/// "When will the Senate vote on the SAVE America Act?" read **+9 more** over a
/// page of two rows, both already on the card.
///
/// PR #9141 (lane1b) made the server count the page: `more_count` = the rungs
/// `/futures/{id}` shows that the card does not. The card now prints that, and
/// falls back to the ladder arithmetic only when a payload predates it — the
/// same rule the web card uses (`market.more_count ?? market.outcome_count - 3`).
///
/// The rows below are verbatim from that 14:25Z payload.
final class PoliticsCardMoreCountIsThePagesCount9109Tests: XCTestCase {

    /// The app's decoder, configured as `APIClient` configures it.
    private func decodeRow(_ json: String) throws -> CategoryMarketRow {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(CategoryMarketRow.self, from: Data(json.utf8))
    }

    /// The specimen. Old badge: +9 more. Page: the two rows the card already shows.
    private let saveAmericaAct = """
    {"q": "When will the Senate vote on the SAVE America Act?", "prob": 6.5, "src": "kalshi", \
    "market_id": 5466697, "top_outcomes": [{"name": "Before Nov 3, 2026", "prob": 6.5}, \
    {"name": "Before Oct 1, 2026", "prob": 1.0}], "outcome_count": 12, "more_count": 0}
    """

    /// A non-zero page count that still disagrees with the ladder (old: +2).
    private let natalieHarp = """
    {"q": "Natalie Harp White House departure announced?", "prob": 18.5, "src": "kalshi", \
    "market_id": 59693666, "top_outcomes": [{"name": "Before Jan 1, 2027", "prob": 18.5}, \
    {"name": "Before Dec 1, 2026", "prob": 11.5}, {"name": "Before Oct 1, 2026", "prob": 6.0}], \
    "outcome_count": 5, "more_count": 1}
    """

    func testTheSpecimenPromisesNothingMore() throws {
        let row = try decodeRow(saveAmericaAct)
        XCTAssertEqual(row.moreCount, 0, "`more_count` did not decode — the badge is back on the ladder arithmetic")
        XCTAssertEqual(
            row.overflowCount, 0,
            "The SAVE America Act card's page shows the two rows the card already shows; "
                + "the card must not promise more (it printed +9)."
        )
    }

    func testANonZeroPageCountIsPrintedAsServed() throws {
        let row = try decodeRow(natalieHarp)
        XCTAssertEqual(row.overflowCount, 1, "The page shows one row the card does not; the old badge said +2")
    }

    /// An older payload with no `more_count` still decodes and keeps the old
    /// behaviour, so a stale cache or an unreleased server never blanks the badge.
    func testAPayloadWithoutMoreCountFallsBackToTheLadder() throws {
        let row = try decodeRow("""
        {"q": "Q", "prob": 40.0, "src": "kalshi", "market_id": 1, \
        "top_outcomes": [{"name": "A", "prob": 40.0}], "outcome_count": 7}
        """)
        XCTAssertNil(row.moreCount)
        XCTAssertEqual(row.overflowCount, 4)
    }

    /// The view must print the served count. Reverting the view line to
    /// `outcomeCount - 3` passes every decode test above and re-ships the defect.
    func testTheCardPrintsTheServedCountNotTheLadder() throws {
        let source = try String(contentsOf: Self.politicsView, encoding: .utf8)
        XCTAssertTrue(
            source.contains("Text(\"+\\(m.overflowCount) more\")"),
            "PoliticsView's card badge no longer prints `overflowCount`"
        )
        XCTAssertFalse(
            source.contains("outcomeCount - 3"),
            "PoliticsView computes the badge from the ladder again — that is the +9-over-two defect (#9109)"
        )
    }

    private static var politicsView: URL {
        URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()   // BainLuckTests
            .deletingLastPathComponent()   // Bain Luck (project dir)
            .appendingPathComponent("Bain Luck/Views/PoliticsView.swift")
    }
}
