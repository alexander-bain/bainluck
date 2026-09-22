import XCTest
@testable import Bain_Luck

/// native/292 — #7943: a played half's map states the half's own result.
///
/// THE PHOTOGRAPH. Event 14780545 (NY Giants 6 – LA Rams 28, NFL, **Final**),
/// iPhone 17 simulator, 2026-09-21 21:22 PDT, `--scroll 1500` —
/// `artifacts/native-292/BEFORE-half-cards.png`. The full-game **Points map**
/// drew `FINAL 34 points`, a marker on its rail and a HIT/MISS ladder. The four
/// half maps directly beneath it — 1st/2nd half margin, 1st/2nd half total —
/// drew a distribution and **nothing else at all** on a game that was over.
///
/// THE NUMBER WAS NEVER MISSING. `/api/events/14780545/history` carries the
/// CUMULATIVE score against a period label, and the halftime boundary is
/// observed twelve times at 14–3 against a `Final` of 28–6. Both settled venue
/// ladders in `/game-markets` independently pin LAR by 11 in each half
/// (`LA Rams wins 1H by over 10.5` = 0.99, `… by over 13.5` = 0.01).
///
/// 🔴 WHY A FORECAST-SHAPED RAIL WAS NOT ALREADY TELLING THE READER THE ANSWER.
/// `buildDensityFromSpreads` bins each rung by its margin and SUMS the cover
/// probabilities into the bin. A spread ladder is cumulative, so the mass always
/// piles where the favourite's LOW thresholds cluster: the seven `0.99` rungs at
/// LAR by 2.5…10.5 put the peak at LAR by ~2.6–7.7 against a true margin of 11.
/// The full-game card survives that because it also prints the result. The half
/// cards printed only the histogram, so the histogram read as the claim. Fixing
/// the binning rule is a separate and much wider change (it is shared with the
/// full-game card on every sport) and is deliberately NOT what this ship did —
/// see #7943's scope note before "simplifying" these tests into that one.
final class HalfMapsStateTheHalfsResult7943Tests: XCTestCase {

    private func at(_ minute: Int) -> Date {
        Date(timeIntervalSince1970: 1_758_500_000 + Double(minute) * 60)
    }

    /// The measured specimen, digit for digit.
    private func mondayNightReadings() -> [HalfScoreReading] {
        [
            HalfScoreReading(period: "15:00 - 1st Quarter", home: 0, away: 0, date: at(0)),
            HalfScoreReading(period: "End of 1st Quarter", home: 7, away: 0, date: at(34)),
            HalfScoreReading(period: "11:07 - 2nd Quarter", home: 14, away: 0, date: at(47)),
            HalfScoreReading(period: "0:25 - 2nd Quarter", home: 14, away: 3, date: at(81)),
            HalfScoreReading(period: "Halftime", home: 14, away: 3, date: at(87)),
            HalfScoreReading(period: "Halftime", home: 14, away: 3, date: at(98)),
            HalfScoreReading(period: "6:21 - 3rd Quarter", home: 21, away: 3, date: at(117)),
            HalfScoreReading(period: "End of 3rd Quarter", home: 21, away: 6, date: at(137)),
            HalfScoreReading(period: "8:57 - 4th Quarter", home: 28, away: 6, date: at(152)),
            HalfScoreReading(period: "Final", home: 28, away: 6, date: at(174)),
        ]
    }

    // MARK: - The specimen

    func testTheFinalGamesBothHalvesReadLARByElevenAndSeventeenPoints() {
        let pair = HalfScores.split(
            readings: mondayNightReadings(), currentHome: 28, currentAway: 6, isDone: true
        )

        XCTAssertEqual(pair.first, HalfScoreSplit(home: 14, away: 3))
        XCTAssertEqual(pair.first?.margin, 11)
        XCTAssertEqual(pair.first?.total, 17)

        XCTAssertEqual(pair.second, HalfScoreSplit(home: 14, away: 3))
        XCTAssertEqual(pair.second?.margin, 11)
        XCTAssertEqual(pair.second?.total, 17)

        // Both halves are over, so both cards say FINAL, not ACTUAL.
        XCTAssertTrue(pair.isComplete(.first))
        XCTAssertTrue(pair.isComplete(.second))
    }

    /// The margin the rail's own density peak disagrees with. Pinned so nobody
    /// "reconciles" the marker to the histogram instead of the other way round.
    func testTheStatedMarginIsTheScoreboardsNotTheLaddersBusiestBin() {
        let pair = HalfScores.split(
            readings: mondayNightReadings(), currentHome: 28, currentAway: 6, isDone: true
        )
        XCTAssertEqual(pair.score(.first)?.margin, 11)
        XCTAssertNotEqual(pair.score(.first)?.margin, 5, "the density peak is not the result")
    }

    // MARK: - The half has its own lifecycle (#7639's insight, on iOS)

    func testAFirstHalfIsFinalWhileTheGameIsStillBeingPlayed() {
        let live = Array(mondayNightReadings().prefix(7))  // through 6:21 - 3rd Quarter
        let pair = HalfScores.split(
            readings: live, currentHome: 21, currentAway: 3, isDone: false
        )

        XCTAssertEqual(pair.first?.margin, 11)
        XCTAssertTrue(pair.isComplete(.first), "the first half is over; the GAME is not")
    }

    func testASecondHalfInPlayIsActualNotFinal() {
        let live = Array(mondayNightReadings().prefix(7))
        let pair = HalfScores.split(
            readings: live, currentHome: 21, currentAway: 3, isDone: false
        )

        XCTAssertEqual(pair.second, HalfScoreSplit(home: 7, away: 0))
        XCTAssertFalse(pair.isComplete(.second), "still in play — the card must say ACTUAL")
    }

    // MARK: - Withheld rather than guessed

    /// 🔴 THE CONTROL THIS WHOLE RULE TURNS ON. Web's `computeHalfScores` tests
    /// `/end of 2nd/i`, which matches `"End of 2nd Half"` — FULL TIME in the
    /// two-half vocabulary. Under that test a finished soccer match hands its
    /// FINAL score back as the first-half score and the second half subtracts to
    /// 0–0. `PeriodLabel.isFirstHalfBoundary` refuses the half form by name.
    func testEndOfSecondHalfIsFullTimeAndIsNeverReadAsHalftime() {
        XCTAssertFalse(PeriodLabel.isFirstHalfBoundary("End of 2nd Half"))
        XCTAssertFalse(PeriodLabel.isFirstHalfBoundary("End of Second Half"))

        let soccer = [
            HalfScoreReading(period: "23'", home: 0, away: 0, date: at(0)),
            HalfScoreReading(period: "67'", home: 1, away: 1, date: at(60)),
            HalfScoreReading(period: "End of 2nd Half", home: 2, away: 1, date: at(95)),
        ]
        let pair = HalfScores.split(
            readings: soccer, currentHome: 2, currentAway: 1, isDone: true
        )

        XCTAssertNil(pair.first, "full time is not halftime")
        XCTAssertNil(pair.second)
        XCTAssertNotEqual(
            pair.second, HalfScoreSplit(home: 0, away: 0),
            "the loose rule's signature failure: a 0-0 second half on a 2-1 game"
        )
    }

    /// 🔴 THE CONTROL THAT MAKES "SPELLED IN FULL" LOAD-BEARING, and the reason
    /// the quarter clause may never be shortened to `"end of 2nd"`.
    ///
    /// A three-period sport has no halftime at all, so the end of its second
    /// period is not a boundary this rule may report. `"End of 2nd Period"`
    /// contains neither `"2nd half"` (so the refusal line above cannot save it)
    /// nor `"end of 2nd quarter"` — the ONLY thing keeping it out is that the
    /// quarter form is written out in full. Shorten it and this is the
    /// assertion that fails, which is exactly the point of having it.
    func testAThreePeriodSportsSecondPeriodIsNotHalftime() {
        XCTAssertFalse(PeriodLabel.isFirstHalfBoundary("End of 2nd Period"))
        XCTAssertFalse(PeriodLabel.isFirstHalfBoundary("End of Second Period"))

        // And it withholds rather than inventing a 3-period "half".
        let hockey = [
            HalfScoreReading(period: "End of 1st Period", home: 1, away: 0, date: at(0)),
            HalfScoreReading(period: "End of 2nd Period", home: 2, away: 1, date: at(40)),
            HalfScoreReading(period: "Final", home: 3, away: 1, date: at(80)),
        ]
        let pair = HalfScores.split(
            readings: hockey, currentHome: 3, currentAway: 1, isDone: true
        )
        XCTAssertNil(pair.first, "hockey has no halftime")
        XCTAssertNil(pair.second)
    }

    func testTheQuarterFormOfTheSameLabelIsAccepted() {
        XCTAssertTrue(PeriodLabel.isFirstHalfBoundary("End of 2nd Quarter"))
        XCTAssertTrue(PeriodLabel.isFirstHalfBoundary("Halftime"))
        XCTAssertTrue(PeriodLabel.isFirstHalfBoundary("HT"))
        XCTAssertTrue(PeriodLabel.isFirstHalfBoundary("Half Time"))
        XCTAssertTrue(PeriodLabel.isFirstHalfBoundary("End of 1st Half"))
    }

    func testAHalftimeThatWasNeverObservedDrawsNothing() {
        let gappy = [
            HalfScoreReading(period: "End of 1st Quarter", home: 7, away: 0, date: at(34)),
            HalfScoreReading(period: "6:21 - 3rd Quarter", home: 21, away: 3, date: at(117)),
            HalfScoreReading(period: "Final", home: 28, away: 6, date: at(174)),
        ]
        let pair = HalfScores.split(
            readings: gappy, currentHome: 28, currentAway: 6, isDone: true
        )

        XCTAssertNil(pair.first)
        XCTAssertNil(pair.second)
        XCTAssertFalse(pair.isComplete(.first))
    }

    /// `final − halftime` is "everything after halftime", which is only the
    /// second half when nothing was played after the second half.
    func testOvertimeWithholdsTheSecondHalfAndKeepsTheFirst() {
        var readings = mondayNightReadings()
        readings.append(HalfScoreReading(period: "7:12 - OT", home: 34, away: 34, date: at(190)))
        let pair = HalfScores.split(
            readings: readings, currentHome: 34, currentAway: 34, isDone: true
        )

        XCTAssertEqual(pair.first?.margin, 11, "the first half is untouched by overtime")
        XCTAssertNil(pair.second, "final − halftime would fold OT into the second half")
    }

    func testAfterRegulationIsAToken_NotASubstring() {
        XCTAssertTrue(PeriodLabel.isAfterRegulation("OT"))
        XCTAssertTrue(PeriodLabel.isAfterRegulation("7:12 - OT"))
        XCTAssertTrue(PeriodLabel.isAfterRegulation("End of 3OT"))
        XCTAssertTrue(PeriodLabel.isAfterRegulation("Overtime"))
        XCTAssertTrue(PeriodLabel.isAfterRegulation("Shootout"))
        // A bare `contains("ot")` passes every one of these.
        XCTAssertFalse(PeriodLabel.isAfterRegulation("Promotion Playoff"))
        XCTAssertFalse(PeriodLabel.isAfterRegulation("Not Started"))
        XCTAssertFalse(PeriodLabel.isAfterRegulation("Bottom 4th"))
    }

    func testAtHalftimeTheSecondHalfIsAbsentRatherThanNilNil() {
        let atHalftime = Array(mondayNightReadings().prefix(6))  // ends on Halftime
        let pair = HalfScores.split(
            readings: atHalftime, currentHome: 14, currentAway: 3, isDone: false
        )

        XCTAssertEqual(pair.first?.margin, 11)
        XCTAssertNil(pair.second, "a half nobody has played is not a 0-0 result")
    }

    func testAScoreboardBehindItsHistoryRefusesRatherThanPrintANegativeHalf() {
        let pair = HalfScores.split(
            readings: mondayNightReadings(), currentHome: 10, currentAway: 3, isDone: false
        )

        XCTAssertEqual(pair.first?.margin, 11)
        XCTAssertNil(pair.second, "10 − 14 is not a second half")
    }

    func testAnAbsentScoreboardWithholdsTheSecondHalfOnly() {
        let pair = HalfScores.split(
            readings: mondayNightReadings(), currentHome: nil, currentAway: nil, isDone: true
        )

        XCTAssertEqual(pair.first?.margin, 11)
        XCTAssertNil(pair.second)
    }

    // MARK: - Ordering

    /// The boundary is held for many polls and a late correction to the half's
    /// score has to win. Served order is not trusted; the readings are sorted.
    func testTheLastHalftimeReadingWinsAndOrderIsNotTrusted() {
        let shuffled = [
            HalfScoreReading(period: "Halftime", home: 14, away: 3, date: at(98)),
            HalfScoreReading(period: "15:00 - 1st Quarter", home: 0, away: 0, date: at(0)),
            HalfScoreReading(period: "Halftime", home: 13, away: 3, date: at(87)),
        ]
        let pair = HalfScores.split(
            readings: shuffled, currentHome: 14, currentAway: 3, isDone: false
        )

        XCTAssertEqual(
            pair.first, HalfScoreSplit(home: 14, away: 3),
            "the corrected 14-3 at :98, not the first sighting of 13-3 at :87"
        )
    }

    // MARK: - The default is the old behaviour

    func testThePairsNoneValueStatesNothing() {
        XCTAssertNil(HalfScores.Pair.none.score(.first))
        XCTAssertNil(HalfScores.Pair.none.score(.second))
        XCTAssertFalse(HalfScores.Pair.none.isComplete(.first))
        XCTAssertFalse(HalfScores.Pair.none.isComplete(.second))
    }

    func testAnEmptyHistoryIsNone() {
        XCTAssertEqual(
            HalfScores.split(readings: [], currentHome: 28, currentAway: 6, isDone: true),
            .none
        )
    }
}
