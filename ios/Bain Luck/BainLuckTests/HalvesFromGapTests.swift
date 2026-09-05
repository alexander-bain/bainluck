import XCTest
@testable import Bain_Luck

/// Guards for #3317 (native/028): the MATCH chart stops printing another
/// sport's vocabulary.
///
/// A **Major League Baseball** win-probability chart drew `1H` and `2H` because
/// the halftime inference read a pause in the reading stream as evidence of a
/// SPORT. Photographed on the live Giants–Mets game 15296786, 2026-09-05:
/// `artifacts-native-028/n028-BEFORE-mets.png`.
///
/// **THE FIXTURE IS THE SAME IN BOTH DIRECTIONS, AND THAT IS THE POINT.** Every
/// negative case below reuses `firingShapeDates` — a date list measured off a
/// real MLB game — and each has a partner that feeds those identical dates in
/// under a soccer key and asserts the halves DO appear. Without that partner a
/// "no chips on baseball" test passes just as well against an inert fixture that
/// could never have fired, which would pin nothing at all. Because only the
/// sport argument differs, the difference is provably the gate.
final class HalvesFromGapTests: XCTestCase {

    private let anchor = Date(timeIntervalSince1970: 1_757_100_000)

    /// Readings whose shape is the one measured on 15296786: no period data,
    /// comfortably over the reading floor, and one pause well past eight
    /// minutes (the real game's largest was 872 seconds).
    ///
    /// Offsets first, no branch on the clock (gotcha #44) — the anchor is a
    /// literal instant, so this list is the same on every machine and in every
    /// timezone.
    private var firingShapeDates: [Date] {
        [0, 120, 240, 1_112, 1_232, 1_352].map { anchor.addingTimeInterval($0) }
    }

    // MARK: - The sport gate

    func testTheSportsThatDoNotPlayHalvesAreRefused() {
        // The four families that actually reach this code. `baseball_mlb` is the
        // photographed one; the others are the sports whose ESPN history exists
        // at all (measured 2026-09-05: baseball, americanfootball, basketball).
        for key in ["baseball_mlb", "baseball_ncaa", "americanfootball_nfl",
                    "americanfootball_ncaaf", "basketball_nba", "icehockey_nhl",
                    "tennis_wta_us_open", "golf_pga_championship_winner"] {
            XCTAssertFalse(HalvesFromGap.sportPlaysInHalves(key),
                           "\(key) does not play two halves")
        }
    }

    func testSoccerIsAccepted() {
        // All 60 soccer keys in the database are `soccer_`-prefixed (measured
        // 2026-09-05 over all 176 keys), including the catch-all `soccer_other`.
        for key in ["soccer_epl", "soccer_uefa_champs_league", "soccer_usa_mls",
                    "soccer_brazil_serie_b", "soccer_other", "SOCCER_EPL"] {
            XCTAssertTrue(HalvesFromGap.sportPlaysInHalves(key),
                          "\(key) is soccer")
        }
    }

    func testAnUnknownOrAbsentSportFailsClosed() {
        // A chart that cannot name its sport must infer nothing. Before #3317
        // this view had no sport at all, which is how it came to guess.
        XCTAssertFalse(HalvesFromGap.sportPlaysInHalves(nil))
        XCTAssertFalse(HalvesFromGap.sportPlaysInHalves(""))
        XCTAssertFalse(HalvesFromGap.sportPlaysInHalves("lacrosse_ncaa"))
        XCTAssertFalse(HalvesFromGap.sportPlaysInHalves("esports"))
    }

    // MARK: - The defect, and its control

    func testABaseballGameWithTheFiringShapeGetsNoHalves() {
        // #3317's first acceptance criterion, on the measured shape.
        XCTAssertEqual(
            HalvesFromGap.markers(sportKey: "baseball_mlb", espnDates: firingShapeDates).count,
            0)
    }

    func testTheSameDatesUnderSoccerDoProduceHalves() {
        // THE CONTROL. Identical dates, one argument changed. If this failed,
        // the test above would be passing because the fixture cannot fire —
        // and it would keep passing if the gate were deleted tomorrow.
        let markers = HalvesFromGap.markers(sportKey: "soccer_epl", espnDates: firingShapeDates)
        XCTAssertEqual(markers.map(\.label), ["1H", "HT", "2H"])
    }

    func testAnUnknownSportGetsNoHalvesOnTheSameDates() {
        XCTAssertEqual(HalvesFromGap.markers(sportKey: nil, espnDates: firingShapeDates).count, 0)
        XCTAssertEqual(HalvesFromGap.markers(sportKey: "rugby_union", espnDates: firingShapeDates).count, 0)
    }

    // MARK: - Where the halves land

    func testTheHalvesLandAtTheStartTheGapsMiddleAndTheResumption() {
        let markers = HalvesFromGap.markers(sportKey: "soccer_epl", espnDates: firingShapeDates)
        XCTAssertEqual(markers.count, 3)
        // 1H at the first reading; the gap runs 240s → 1112s, so HT is its
        // midpoint (676s) and 2H is the resumption.
        XCTAssertEqual(markers[0].date, anchor)
        XCTAssertEqual(markers[1].date, anchor.addingTimeInterval(676))
        XCTAssertEqual(markers[2].date, anchor.addingTimeInterval(1_112))
    }

    func testTheFirstQualifyingGapWins() {
        // Two pauses: the halves describe the earlier one. A second-half
        // stoppage must not relabel the match.
        let dates = [0, 120, 700, 1_400, 1_520, 2_400]
            .map { anchor.addingTimeInterval(Double($0)) }
        let markers = HalvesFromGap.markers(sportKey: "soccer_epl", espnDates: dates)
        XCTAssertEqual(markers.map(\.label), ["1H", "HT", "2H"])
        XCTAssertEqual(markers[2].date, anchor.addingTimeInterval(700))
    }

    // MARK: - The floors

    func testBelowTheReadingFloorNothingIsInferred() {
        // Four readings with a long pause is a sync hiccup, not a half-time.
        let dates = [0, 120, 1_112, 1_232].map { anchor.addingTimeInterval(Double($0)) }
        XCTAssertEqual(HalvesFromGap.markers(sportKey: "soccer_epl", espnDates: dates).count, 0)
    }

    func testTheGapBoundIsStrictlyGreater() {
        // Exactly eight minutes is not a gap "over" eight minutes. Pinned
        // because an off-by-one here silently changes which matches annotate.
        let onTheBound = [0, 60, 120, 180, 180 + HalvesFromGap.minimumGapSeconds,
                          240 + HalvesFromGap.minimumGapSeconds]
            .map { anchor.addingTimeInterval($0) }
        XCTAssertEqual(HalvesFromGap.markers(sportKey: "soccer_epl", espnDates: onTheBound).count, 0)

        let onePastIt = [0, 60, 120, 180, 181 + HalvesFromGap.minimumGapSeconds,
                         241 + HalvesFromGap.minimumGapSeconds]
            .map { anchor.addingTimeInterval($0) }
        XCTAssertEqual(
            HalvesFromGap.markers(sportKey: "soccer_epl", espnDates: onePastIt).map(\.label),
            ["1H", "HT", "2H"])
    }

    func testTheBoundsAreTheNumbersTheOldInlineRuleUsed() {
        // Extracting the rule must not have moved it. These two literals came
        // out of `extractPeriodMarkers` unchanged.
        XCTAssertEqual(HalvesFromGap.minimumGapSeconds, 480, accuracy: 1e-9)
        XCTAssertEqual(HalvesFromGap.minimumReadings, 5)
    }

    // MARK: - Totality

    func testUnsortedInputGivesTheSameAnswer() {
        // The caller maps over a served array; a pushed reading is appended, so
        // "already chronological" is not a safe assumption (the same trap
        // `LiveSparklineChart.windowed` sorts against).
        let shuffled = firingShapeDates.reversed().map { $0 }
        XCTAssertEqual(
            HalvesFromGap.markers(sportKey: "soccer_epl", espnDates: shuffled).map(\.label),
            ["1H", "HT", "2H"])
    }

    func testAnEmptyStreamInfersNothingRatherThanCrashing() {
        // The old inline code indexed `espnDates.first!` inside a loop it only
        // reached via a count check; a pure, total function has no such edge.
        XCTAssertEqual(HalvesFromGap.markers(sportKey: "soccer_epl", espnDates: []).count, 0)
        XCTAssertEqual(
            HalvesFromGap.markers(sportKey: "soccer_epl", espnDates: [anchor]).count, 0)
    }

    func testAContinuousStreamInfersNothing() {
        // A soccer match we watched without interruption gets no invented
        // halves — the inference needs a pause, not merely a sport.
        let dates = (0..<12).map { anchor.addingTimeInterval(Double($0) * 120) }
        XCTAssertEqual(HalvesFromGap.markers(sportKey: "soccer_epl", espnDates: dates).count, 0)
    }
}
