import XCTest
import SwiftUI
@testable import Bain_Luck

/// #3850 — a finished game's "Projected scoring" card stops labelling
/// settlement-derived numbers `PRE-GAME`.
///
/// The view itself is SwiftUI and is not asserted here. What IS asserted is the
/// pure rule the view now defers to, which is where every claim in the fix
/// lives: `TotalPointsSpectrumView.ladderIndices` for WHICH rungs are drawn, and
/// `MarketMapRail.totalLadderResult` (#3823's, reused rather than re-derived)
/// for WHAT each rung says.
///
/// THE SPECIMEN, used throughout: event **15305475**, Minnesota 1 — Chicago WS
/// 10, `completed`, **11 runs**. `/api/events/15305475/game-markets` serves
/// eleven `Over N runs scored` lines, `2.5 … 12.5`, re-read from production
/// 2026-09-07.
final class TotalPointsSpectrumSettledTests: XCTestCase {

    /// The specimen's eleven lines, ascending — exactly as production serves them.
    private let specimenLines: [Double] = [2.5, 3.5, 4.5, 5.5, 6.5, 7.5, 8.5, 9.5, 10.5, 11.5, 12.5]
    private let specimenFinal = 11
    private let limit = TotalPointsSpectrumView.ladderRowLimit

    private func grade(_ threshold: Double, _ final: Int) -> MarketMapRail.TotalLadderResult {
        MarketMapRail.totalLadderResult(threshold: threshold, finalTotal: final)
    }

    // MARK: - The window is load-bearing, not cosmetic

    /// 🔴 THE MEASUREMENT THAT JUSTIFIES TOUCHING THE SELECTION AT ALL.
    ///
    /// Grading the OLD stride would have produced five identical verdicts, which
    /// is #3823's "the second fault survives fixing the first" on this card. If
    /// someone later reverts `ladderIndices` to a plain stride believing the
    /// verdict alone was the fix, this goes red and says why.
    func testTheOldStrideWouldHaveShownFiveIdenticalVerdicts() {
        // The stride the card used before #3850: step = count / limit.
        let step = max(1, specimenLines.count / limit)
        var old: [Int] = []
        var i = 0
        while i < specimenLines.count, old.count < limit {
            old.append(i)
            i += step
        }
        XCTAssertEqual(old, [0, 2, 4, 6, 8], "the stride this test is the control for has changed")
        XCTAssertEqual(old.map { specimenLines[$0] }, [2.5, 4.5, 6.5, 8.5, 10.5])

        let verdicts = Set(old.map { grade(specimenLines[$0], specimenFinal) })
        XCTAssertEqual(
            verdicts, [.over],
            "the old selection grades to one distinct verdict — five identical HITs, "
            + "which is exactly as uninformative as the five identical 99%s it replaced"
        )
        XCTAssertFalse(
            old.map { specimenLines[$0] }.contains(11.5),
            "the old stride never samples 11.5, the first line the game failed to clear — "
            + "the one rung that tells the reader the total was 11"
        )
    }

    /// The new selection centres on the step, so both sides of it are on screen.
    func testTheSettledWindowStraddlesTheStep() {
        let picks = TotalPointsSpectrumView.ladderIndices(
            sortedThresholds: specimenLines, finalTotal: specimenFinal, limit: limit
        )
        let lines = picks.map { specimenLines[$0] }
        XCTAssertEqual(lines, [8.5, 9.5, 10.5, 11.5, 12.5])

        let verdicts = lines.map { grade($0, specimenFinal) }
        XCTAssertEqual(verdicts, [.over, .over, .over, .under, .under])
        XCTAssertTrue(
            lines.contains(10.5) && lines.contains(11.5),
            "the last line cleared and the first line missed must BOTH be drawn — "
            + "the step between them is how the reader reads 11 off the card"
        )
        XCTAssertEqual(
            Set(verdicts).count, 2,
            "a settled ladder that shows only one distinct verdict has told the reader nothing"
        )
    }

    /// The verdict words, and that a settled rung never prints a percentage.
    func testEachDrawnRungPrintsAVerdictAndNotAPrice() {
        let picks = TotalPointsSpectrumView.ladderIndices(
            sortedThresholds: specimenLines, finalTotal: specimenFinal, limit: limit
        )
        let words = picks.map {
            MarketMapRail.totalLadderResultLabel(grade(specimenLines[$0], specimenFinal))
        }
        XCTAssertEqual(words, ["HIT", "HIT", "HIT", "MISS", "MISS"])
        for word in words {
            XCTAssertFalse(word.contains("%"), "a settled rung must not restate a settlement price")
            XCTAssertLessThanOrEqual(
                word.count, 4,
                "the verdict shares a fixed-width column with '100%' — four characters is the budget"
            )
        }
    }

    // MARK: - The push the old `>=` graded as a HIT

    /// The second defect in #3850: `Double(actual) >= threshold` called a line the
    /// game landed exactly on a HIT. Unreachable on today's all-half-line data,
    /// which is precisely why it survived — so it is asserted directly.
    func testAnIntegerLineTheGameLandsOnIsAPushNotAHit() {
        XCTAssertEqual(grade(11.0, 11), .push)
        XCTAssertEqual(MarketMapRail.totalLadderResultLabel(grade(11.0, 11)), "PUSH")

        // The old rule, stated so the difference is on the record.
        let oldRuleWouldSay = Double(11) >= 11.0
        XCTAssertTrue(oldRuleWouldSay, "the old `>=` graded this exact case as a HIT")
        XCTAssertNotEqual(grade(11.0, 11), .over, "and it is not one")

        // A push is not coloured as though something happened.
        XCTAssertEqual(TotalPointsSpectrumView.verdictColor(.push), TotalPointsSpectrumView.verdictPush)
        XCTAssertNotEqual(TotalPointsSpectrumView.verdictColor(.push),
                          TotalPointsSpectrumView.verdictColor(.over))
    }

    /// Half-lines either side still grade the ordinary way.
    func testHalfLinesEitherSideOfTheFinalGradeNormally() {
        XCTAssertEqual(grade(10.5, 11), .over)
        XCTAssertEqual(grade(11.5, 11), .under)
        XCTAssertEqual(MarketMapRail.totalLadderResultLabel(grade(10.5, 11)), "HIT")
        XCTAssertEqual(MarketMapRail.totalLadderResultLabel(grade(11.5, 11)), "MISS")
    }

    // MARK: - The unsettled card is the control and must not move

    /// A game that can still decide its own lines keeps the old spread of rungs.
    func testAnUnsettledLadderStillStridesTheWholeRange() {
        let picks = TotalPointsSpectrumView.ladderIndices(
            sortedThresholds: specimenLines, finalTotal: nil, limit: limit
        )
        XCTAssertEqual(picks, [0, 2, 4, 6, 8],
                       "the pre-game ladder's selection is unchanged by #3850")
        XCTAssertEqual(picks.map { specimenLines[$0] }, [2.5, 4.5, 6.5, 8.5, 10.5])
    }

    /// The NFL control from the same shoot: a scheduled game, nineteen totals
    /// lines, no final. Selection must not consult a score it does not have.
    func testAScheduledGameSelectsWithoutAFinal() {
        let nfl = stride(from: 23.5, through: 41.5, by: 1.0).map { $0 }
        XCTAssertGreaterThan(nfl.count, limit)
        let picks = TotalPointsSpectrumView.ladderIndices(
            sortedThresholds: nfl, finalTotal: nil, limit: limit
        )
        XCTAssertEqual(picks.count, limit)
        XCTAssertEqual(picks.first, 0, "an unsettled ladder still starts at the lowest line")
    }

    // MARK: - Shape guarantees, swept rather than sampled

    /// Proof for the deleted "top up" branch: past the `count > limit` guard the
    /// stride always fills the ladder, so the branch could never have fired.
    func testTheStrideAlwaysFillsTheLadder() {
        for count in (limit + 1) ... 40 {
            let lines = (0 ..< count).map { Double($0) + 0.5 }
            let picks = TotalPointsSpectrumView.ladderIndices(
                sortedThresholds: lines, finalTotal: nil, limit: limit
            )
            XCTAssertEqual(picks.count, limit, "stride returned \(picks.count) rungs for count \(count)")
        }
    }

    /// Both branches, every size: indices are in range, strictly increasing, and
    /// never more than the card draws.
    func testEverySelectionIsInRangeAndOrdered() {
        for count in 0 ... 40 {
            let lines = (0 ..< count).map { Double($0) + 0.5 }
            for final: Int? in [nil, 0, 5, 11, 100] {
                let picks = TotalPointsSpectrumView.ladderIndices(
                    sortedThresholds: lines, finalTotal: final, limit: limit
                )
                XCTAssertLessThanOrEqual(picks.count, min(limit, count))
                XCTAssertEqual(picks, picks.sorted(), "picks must be ascending (count \(count))")
                XCTAssertEqual(Set(picks).count, picks.count, "no rung may be drawn twice (count \(count))")
                for p in picks {
                    XCTAssertTrue(lines.indices.contains(p), "index \(p) out of range for count \(count)")
                }
            }
        }
    }

    /// A ladder no longer than the card draws is shown whole, settled or not.
    func testShortLaddersAreShownWhole() {
        let short: [Double] = [2.5, 3.5, 4.5]
        for final: Int? in [nil, 4] {
            XCTAssertEqual(
                TotalPointsSpectrumView.ladderIndices(
                    sortedThresholds: short, finalTotal: final, limit: limit
                ),
                [0, 1, 2]
            )
        }
        XCTAssertEqual(
            TotalPointsSpectrumView.ladderIndices(sortedThresholds: [], finalTotal: 11, limit: limit),
            []
        )
    }

    // MARK: - The ends behave without a special case

    /// A final that cleared every line, and one that cleared none. #3823's window
    /// slides back inside the array rather than special-casing either end; this
    /// card inherits that, so it is asserted here too.
    func testTheEndsOfTheLadderDoNotNeedASpecialCase() {
        let clearedAll = TotalPointsSpectrumView.ladderIndices(
            sortedThresholds: specimenLines, finalTotal: 99, limit: limit
        )
        XCTAssertEqual(clearedAll.map { specimenLines[$0] }, [8.5, 9.5, 10.5, 11.5, 12.5],
                       "a blowout shows the lines it came closest to failing")
        XCTAssertEqual(Set(clearedAll.map { grade(specimenLines[$0], 99) }), [.over])

        let clearedNone = TotalPointsSpectrumView.ladderIndices(
            sortedThresholds: specimenLines, finalTotal: 0, limit: limit
        )
        XCTAssertEqual(clearedNone.map { specimenLines[$0] }, [2.5, 3.5, 4.5, 5.5, 6.5],
                       "a shutout shows the lowest lines — the ones it came closest to clearing")
        XCTAssertEqual(Set(clearedNone.map { grade(specimenLines[$0], 0) }), [.under])
    }

    // MARK: - One rule, not two

    /// #3557's lesson, applied here: this card and the Runs map must grade a
    /// settled totals ladder identically, because they are the same rule and they
    /// sit on the same event page.
    func testThisCardAndTheRunsMapGradeTheSameLadderTheSameWay() {
        let window = MarketMapRail.settledLadderWindow(
            sortedThresholds: specimenLines, finalTotal: specimenFinal, limit: limit
        )
        XCTAssertEqual(
            TotalPointsSpectrumView.ladderIndices(
                sortedThresholds: specimenLines, finalTotal: specimenFinal, limit: limit
            ),
            Array(window),
            "the spectrum must defer to #3823's window, not carry a second copy of it"
        )
        XCTAssertEqual(TotalPointsSpectrumView.verdictColor(.over), Color(hex: "#10B981"))
        XCTAssertEqual(TotalPointsSpectrumView.verdictColor(.under), Color.red)
    }
}
