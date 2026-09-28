import XCTest
@testable import Bain_Luck

/// #4961 — when the payload serves no stored line score, a baseball Game
/// Segments card is rebuilt from polled `espn_history` rows. The generic rule
/// (each inning's LAST polled row is its close) credited the Royals'
/// bottom-of-the-8th run to the 9th on 15319671, an inning they never batted.
/// These rows are that game's real readings; the stored line score is
/// `CLE 0 0 1 0 0 1 0 0 0 | 2`, `KC 1 0 0 0 1 0 0 1 X | 3`.
final class HalfInningFallbackPlacesRunsInTheirInning4961Tests: XCTestCase {

    private func snaps(_ rows: [(String, Int, Int)]) -> [HalfInningLineScore.Snapshot] {
        rows.map { .init(period: $0.0, homeScore: $0.1, awayScore: $0.2) }
    }

    /// 15319671 Guardians @ Royals, `/api/events/15319671/history`, (period, home, away).
    private let clevelandAtKansasCity: [(String, Int, Int)] = [
        ("Bottom 4th", 1, 1),
        ("Top 6th", 2, 2),
        ("Top 6th", 2, 2),
        ("Top 6th", 2, 2),
        ("Top 7th", 2, 2),
        ("Top 7th", 2, 2),
        ("Bottom 7th", 2, 2),
        ("Top 8th", 2, 2),
        ("Top 9th", 3, 2),
        ("Top 9th", 3, 2),
        ("Top 9th", 3, 2),
        ("Final", 3, 2),
    ]

    func testTheSpecimensRunIsInTheEighthAndTheNinthIsX() throws {
        let rows = try XCTUnwrap(HalfInningLineScore.rows(
            snaps(clevelandAtKansasCity), isFinished: true, homeFinal: 3, awayFinal: 2
        ))
        XCTAssertEqual(rows.home.map(\.text), ["·", "·", "·", "·", "·", "0", "0", "1", "X"])
        XCTAssertEqual(rows.away.map(\.text), ["·", "·", "·", "·", "·", "·", "0", "0", "0"])
    }

    /// Every number the card prints matches the stored line score.
    func testEveryPrintedNumberAgreesWithTheStoredLineScore() throws {
        let rows = try XCTUnwrap(HalfInningLineScore.rows(
            snaps(clevelandAtKansasCity), isFinished: true, homeFinal: 3, awayFinal: 2
        ))
        let storedHome: [Int?] = [1, 0, 0, 0, 1, 0, 0, 1, nil]
        let storedAway: [Int?] = [0, 0, 1, 0, 0, 1, 0, 0, 0]
        for (index, cell) in rows.home.enumerated() {
            if let points = cell.points { XCTAssertEqual(points, storedHome[index], "KC inning \(index + 1)") }
        }
        for (index, cell) in rows.away.enumerated() {
            if let points = cell.points { XCTAssertEqual(points, storedAway[index], "CLE inning \(index + 1)") }
        }
    }

    /// A live game in the top of the 2nd: the away side's running inning shows,
    /// the home side has not come up yet, later innings are blank.
    func testALiveTopHalfShowsTheAwayRunningScoreAndLeavesHomeUnplayed() throws {
        let rows = try XCTUnwrap(HalfInningLineScore.rows(
            snaps([
                ("Top 1st", 0, 0), ("Middle 1st", 0, 1), ("Bottom 1st", 0, 1),
                ("End 1st", 2, 1), ("Top 2nd", 2, 1),
            ]),
            isFinished: false, homeFinal: nil, awayFinal: nil
        ))
        XCTAssertEqual(rows.away.map(\.text), ["1", "0", "", "", "", "", "", "", ""])
        XCTAssertEqual(rows.home.map(\.text), ["2", "", "", "", "", "", "", "", ""])
        XCTAssertEqual(rows.lastObserved, 1)
    }

    /// A walk-off: the home side batted in the 9th, so it is never `X`. Its
    /// 9th is unknown (no reading closes it); the away side's 9th is known.
    func testCONTROLAWalkOffNinthIsNeverX() throws {
        let rows = try XCTUnwrap(HalfInningLineScore.rows(
            snaps([("End 8th", 2, 3), ("Top 9th", 2, 3), ("Bottom 9th", 2, 3)]),
            isFinished: true, homeFinal: 4, awayFinal: 3
        ))
        XCTAssertEqual(rows.home.last?.text, "·")
        XCTAssertEqual(rows.away.last?.text, "0")
    }

    /// A reading taken while the away side bats belongs to the inning being
    /// played: the away side scored twice before this `Top 3rd` row, and those
    /// runs are the 3rd's, not the 2nd's.
    func testATopHalfReadingDoesNotCloseTheAwaySidesPreviousInning() throws {
        let rows = try XCTUnwrap(HalfInningLineScore.rows(
            snaps([("Middle 2nd", 0, 1), ("Top 3rd", 0, 3), ("End 3rd", 1, 3)]),
            isFinished: false, homeFinal: nil, awayFinal: nil
        ))
        XCTAssertEqual(rows.away.prefix(3).map(\.text), ["·", "·", "2"])
    }

    /// A road win: nothing is polled after the top of the 9th, and the final
    /// score is what closes it (the away side cannot score after its last turn).
    func testTheFinalScoreClosesTheLastInning() throws {
        let rows = try XCTUnwrap(HalfInningLineScore.rows(
            snaps([("End 8th", 1, 3), ("Top 9th", 1, 3)]),
            isFinished: true, homeFinal: 1, awayFinal: 3
        ))
        XCTAssertEqual(rows.away.last?.text, "0")
        XCTAssertEqual(rows.home.last?.text, "0", "the home side batted, trailing, and did not score")
    }

    /// A stale poll that arrives late (a lower reading after a higher one)
    /// does not erase an inning the higher reading already closed.
    func testALateStaleReadingDoesNotEraseAClosedInning() throws {
        let rows = try XCTUnwrap(HalfInningLineScore.rows(
            snaps([("End 3rd", 2, 1), ("Top 5th", 3, 1), ("Bottom 4th", 2, 1)]),
            isFinished: false, homeFinal: nil, awayFinal: nil
        ))
        XCTAssertEqual(rows.home[3].text, "1")
    }

    func testReadingsThatGoBackwardsRefuseTheCard() {
        XCTAssertNil(HalfInningLineScore.rows(
            snaps([("End 3rd", 2, 1), ("End 4th", 1, 1)]),
            isFinished: false, homeFinal: nil, awayFinal: nil
        ))
    }

    func testCONTROLRowsWithNoHalfInningLabelLeaveTheGenericFallback() {
        XCTAssertNil(HalfInningLineScore.rows(
            snaps([("3rd Inning", 1, 0), ("Final", 2, 0)]),
            isFinished: true, homeFinal: 2, awayFinal: 0
        ))
    }

    func testTheOtherSpellingsOfAHalfInningAreRead() throws {
        let rows = try XCTUnwrap(HalfInningLineScore.rows(
            snaps([("Mid 1st", 0, 1), ("End of 1st Inning", 1, 1)]),
            isFinished: false, homeFinal: nil, awayFinal: nil
        ))
        XCTAssertEqual(rows.away.first?.text, "1")
        XCTAssertEqual(rows.home.first?.text, "1")
    }
}
