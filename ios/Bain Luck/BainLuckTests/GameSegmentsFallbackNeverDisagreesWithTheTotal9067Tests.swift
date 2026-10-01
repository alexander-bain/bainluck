import XCTest
@testable import Bain_Luck

/// #9067 (live's contract note on PR #9129) — `home/away_period_scores` are
/// served only when they sum to that response's score, so an ABSENT array means
/// "don't trust a line score here" and Game Segments falls back to its
/// `espn_history` inference. That fallback must keep the card's one promise
/// too: its known cells never add up to something the total disagrees with.
///
/// Before this, only the stored-array path reconciled. The fallback differences
/// polled cumulative scores, so on a live game whose last poll trailed the
/// scoreboard it printed a complete row short of its total — the rage #159
/// shape (Georgia Tech @ Stanford: `7 3 17` beside 34) with no `·` to carry the
/// missing points.
final class GameSegmentsFallbackNeverDisagreesWithTheTotal9067Tests: XCTestCase {

    private func cells(_ points: [Int?]) -> [LineScoreCell] {
        points.map { $0.map(LineScoreCell.score) ?? .unknown }
    }

    /// Stanford 7 / 3 / 17 polled, scoreboard 34: the running quarter takes the
    /// `·`; the closed quarters keep their numbers.
    func testACompleteRowShortOfItsTotalHandsTheGapToTheLastObservedSegment() throws {
        let squared = try XCTUnwrap(StoredLineScore.squared(
            home: cells([7, 3, 17]), away: cells([10, 10, 0]),
            homeTotal: 34, awayTotal: 20, lastObserved: 2
        ))
        XCTAssertEqual(squared.home.map(\.text), ["7", "3", "·"])
        XCTAssertEqual(squared.away.map(\.text), ["10", "10", "0"], "a row that adds up is untouched")
    }

    func testARowPastItsTotalIsRefused() {
        XCTAssertNil(StoredLineScore.squared(
            home: cells([7, 3, 17]), away: cells([10, 10, 0]),
            homeTotal: 24, awayTotal: 20, lastObserved: 2
        ))
    }

    // MARK: - Controls

    func testCONTROLARowThatAddsUpIsUnchanged() throws {
        let squared = try XCTUnwrap(StoredLineScore.squared(
            home: cells([7, 3, 17, 7]), away: cells([10, 10, 0, 0]),
            homeTotal: 34, awayTotal: 20, lastObserved: 3
        ))
        XCTAssertEqual(squared.home.map(\.text), ["7", "3", "17", "7"])
    }

    /// A row that already carries a `·` is honest short of its total — the dot
    /// is where the missing points live — so nothing moves.
    func testCONTROLARowWithAGapAlreadyCarriesItsShortfall() throws {
        let squared = try XCTUnwrap(StoredLineScore.squared(
            home: cells([7, nil, 3]), away: cells([10, nil, 0]),
            homeTotal: 19, awayTotal: 20, lastObserved: 2
        ))
        XCTAssertEqual(squared.home.map(\.text), ["7", "·", "3"])
    }

    func testCONTROLNoScoreboardTotalLeavesTheRowAlone() throws {
        let squared = try XCTUnwrap(StoredLineScore.squared(
            home: cells([7, 3]), away: cells([0, 0]),
            homeTotal: nil, awayTotal: nil, lastObserved: 1
        ))
        XCTAssertEqual(squared.home.map(\.text), ["7", "3"])
    }

    // MARK: - The fallback asks

    /// `SegmentBreakdown` is private to the event page, so the one fact about
    /// it — the fallback runs its rows through `squared` — is read as text, the
    /// idiom `APreKickoffCertaintyIsNotALivePriceTests` uses for the same reason.
    func testTheEspnHistoryFallbackSquaresItsRows() throws {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("Bain Luck/Views/EventDetailView.swift")
        let source = try String(contentsOf: url, encoding: .utf8)
        let fallback = try XCTUnwrap(
            source.range(of: "guard let espnHistory = history?.espnHistory else { return nil }"),
            "the espn_history fallback moved; move this test with it"
        )
        let end = try XCTUnwrap(source.range(of: "self.awayTotal = resolvedAway\n    }", range: fallback.upperBound..<source.endIndex))
        let body = source[fallback.upperBound..<end.lowerBound]
        XCTAssertTrue(body.contains("StoredLineScore.squared("), "the fallback no longer squares its rows with the total")
        XCTAssertTrue(body.contains("segments = segments.indices.map"), "the squared cells are computed but never drawn")
    }
}
