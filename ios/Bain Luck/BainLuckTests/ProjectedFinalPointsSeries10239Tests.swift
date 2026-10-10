import XCTest
@testable import Bain_Luck

@MainActor
final class ProjectedFinalPointsSeries10239Tests: XCTestCase {
    private typealias Series = ProjectedFinalPointsSeries
    private let epoch = Date(timeIntervalSince1970: 1_790_000_000)
    private func t(_ seconds: Double) -> Date { epoch.addingTimeInterval(seconds) }
    private func pair(_ seconds: Double, _ home: Double? = 27, _ away: Double? = 7.5,
                      probability: Double? = 0.8, kind: Series.Kind = .recorded) -> Series.Pair {
        .init(at: t(seconds), home: home, away: away, homeProbability: probability, kind: kind)
    }
    private func score(_ seconds: Double, _ home: Double, _ away: Double) -> Series.Actual {
        .init(at: t(seconds), home: home, away: away)
    }
    private func input(_ pairs: [Series.Pair], actuals: [Series.Actual] = [],
                       sport: String = "americanfootball_nfl", source: String = "draftkings",
                       floor: Double? = 0, final: Double? = nil, now: Double = 1800,
                       cutoff: Double? = nil, start: Double? = nil) -> Series.Input {
        .init(sportKey: sport, sourceKey: source, basis: .sameBookSameCaptureFullGameSpreadAndTotal,
              pairs: pairs, actuals: actuals, kickoffAt: nil, scoreObservationStartAt: floor.map(t),
              finalAt: final.map(t), asOf: t(now), windowStartAt: start.map(t), requestCutoffAt: cutoff.map(t))
    }

    func testNamedLeaguesOnlyAndNamedSportsbook() {
        for sport in ["baseball_mlb", "icehockey_nhl", "soccer_epl", "tennis_atp", "golf_pga",
                      "americanfootball_ncaaf_fcs", "basketball_euroleague", "americanfootball", ""] {
            XCTAssertNil(Series.build(input([pair(0)], sport: sport)), sport)
        }
        for sport in ["americanfootball_nfl", "americanfootball_ncaaf", "basketball_nba",
                      "basketball_wnba", "basketball_ncaab", "basketball_wncaab"] {
            XCTAssertNotNil(Series.build(input([pair(0)], sport: sport)), sport)
        }
        XCTAssertNil(Series.build(input([pair(0)], source: "unknown")))
        XCTAssertNil(Series.build(input([pair(0)], source: "kalshi")))
        XCTAssertEqual(Series.build(input([pair(0)]))?.sourceName, "DraftKings")
    }

    func testBeforeHasNoFabricatedActuals() throws {
        let result = try XCTUnwrap(Series.build(input([pair(0)], actuals: [score(0, 0, 0)], floor: nil)))
        XCTAssertEqual(result.phase, .before)
        XCTAssertTrue(result.actualSteps.isEmpty)
        XCTAssertNil(result.latestActual)
    }

    func testQuietPregameRetainsOlderForecastButMarksRecentIntervalUnavailable() throws {
        let result = try XCTUnwrap(Series.build(input(
            [pair(-17 * 3600, 24.2, 20.8), pair(-16 * 3600, nil, nil)],
            floor: nil, now: 0)))
        XCTAssertEqual(result.phase, .before)
        XCTAssertEqual(result.start, t(-17 * 3600))
        XCTAssertEqual(result.latest.at, t(-17 * 3600))
        XCTAssertEqual(result.latest.holdEnd, result.latest.at)
        XCTAssertTrue(result.latestIntervalUnavailable)
        XCTAssertTrue(result.actualSteps.isEmpty)
    }

    func testOlderPregameForecastDoesNotOverrideAnExplicitWindowOrProvenance() {
        XCTAssertNil(Series.build(input([pair(-17 * 3600)], floor: nil, now: 0, start: -6 * 3600)))
        XCTAssertNil(Series.build(input([pair(-17 * 3600, kind: .synthetic)], floor: nil, now: 0)))
        XCTAssertNil(Series.build(input([pair(-17 * 3600, 20, 24)], floor: nil, now: 0)))
        XCTAssertNil(Series.build(input([pair(-17 * 3600)], floor: nil, now: 0, cutoff: -16 * 3600)))
    }

    func testObservedFloorRejectsPregameScores() throws {
        let result = try XCTUnwrap(Series.build(input([pair(60)], actuals: [score(-1, 0, 0), score(30, 7, 0)])))
        XCTAssertEqual(result.phase, .during)
        XCTAssertEqual(result.actualSteps, [score(30, 7, 0)])
    }

    func testRestampedCutoffRowsAreRefusedEvenIfCallerSaysRecorded() throws {
        let result = try XCTUnwrap(Series.build(input([pair(0, 40, 10), pair(120, 35, 10), pair(121)], cutoff: 0)))
        XCTAssertEqual(result.segments.flatMap { $0 }.map(\.at), [t(121)])
        XCTAssertNil(Series.build(input([pair(120)], cutoff: 0)))
    }

    func testExplicitSyntheticNeverBecomesAnObservation() throws {
        let result = try XCTUnwrap(Series.build(input([pair(0), pair(60, 35, 10, kind: .synthetic)])))
        XCTAssertEqual(result.latest.at, t(0))
        XCTAssertEqual(result.segments[0][0].holdEnd, t(0))
    }

    func testBrokenPairSplitsLineAndSingletonsSurvive() throws {
        let result = try XCTUnwrap(Series.build(input([pair(0), pair(60, nil, 7), pair(120)])))
        XCTAssertEqual(result.segments.map(\.count), [1, 1])
        XCTAssertEqual(result.withheld.map(\.reason), [.incomplete])
        XCTAssertEqual(result.segments[0][0].holdEnd, t(0))
    }

    func testInvalidValuesAndMoneylineContradictionAreWithheld() throws {
        let result = try XCTUnwrap(Series.build(input([
            pair(0), pair(60, .nan, 7), pair(120, 27, .infinity), pair(180, -1, 7),
            pair(240, 7, 27, probability: 0.8)
        ])))
        XCTAssertEqual(result.withheld.map(\.reason), [.invalidPoints, .invalidPoints, .invalidPoints, .contradictsMoneyline])
        XCTAssertTrue(result.latestIntervalUnavailable)
        XCTAssertEqual(result.latest.at, t(0))
    }

    func testPairBelowRecordedScoreIsNotDrawn() throws {
        let result = try XCTUnwrap(Series.build(input([pair(0), pair(120, 13, 7)], actuals: [score(60, 14, 0)])))
        XCTAssertEqual(result.withheld.map(\.reason), [.belowActual])
        XCTAssertEqual(result.latestActual, score(60, 14, 0))
    }

    func testForecastDoesNotBorrowLaterActualScore() throws {
        let result = try XCTUnwrap(Series.build(input([pair(0, 13, 7)], actuals: [score(60, 14, 0)])))
        XCTAssertTrue(result.withheld.isEmpty)
        XCTAssertEqual(result.latest.home, 13)
    }

    func testLongCaptureGapBreaksRatherThanHoldingThroughSilence() throws {
        let result = try XCTUnwrap(Series.build(input([pair(0), pair(3601)], now: 3700)))
        XCTAssertEqual(result.segments.map(\.count), [1, 1])
        XCTAssertEqual(result.segments[0][0].holdEnd, t(0))
        XCTAssertFalse(result.latestIntervalUnavailable)
        XCTAssertTrue(try XCTUnwrap(Series.build(input([pair(0)], now: 3601))).latestIntervalUnavailable)
    }

    func testValidAdjacentCapturesHoldOnlyUntilNextCapture() throws {
        let result = try XCTUnwrap(Series.build(input([pair(0), pair(60, 28, 7.5)], now: 120)))
        XCTAssertEqual(result.segments.map(\.count), [2])
        XCTAssertEqual(result.segments[0].map(\.holdEnd), [t(60), t(60)])
    }

    func testFinalActualNeverAppendedToForecast() throws {
        let result = try XCTUnwrap(Series.build(input([pair(0), pair(60, 27, 7), pair(120, 28, 7)],
            actuals: [score(60, 27, 7), score(120, 28, 7)], final: 60)))
        XCTAssertEqual(result.phase, .after)
        XCTAssertEqual(result.end, t(60))
        XCTAssertEqual(result.latest.away, 7.5)
        XCTAssertEqual(result.latest.at, t(0))
        XCTAssertEqual(result.latestActual, score(60, 27, 7))
    }

    func testInspectionClipsBothQuantitiesAndKeepsFullWindow() throws {
        let source = input([pair(-60), pair(60, 28, 7.5), pair(120, 30, 10)],
                           actuals: [score(0, 0, 0), score(120, 7, 0)])
        let full = try XCTUnwrap(Series.build(source))
        let result = try XCTUnwrap(Series.at(t(90), input: source))
        XCTAssertEqual(result.start, full.start)
        XCTAssertEqual(result.latest.at, t(60))
        XCTAssertEqual(result.latestActual, score(0, 0, 0))
        XCTAssertEqual(result.end, t(90))
        XCTAssertEqual(Series.at(t(9999), input: source)?.end, full.end)
    }

    func testPregameContextDoesNotDrawEmptyHourAndZeroIsValid() throws {
        let result = try XCTUnwrap(Series.build(input([pair(-5000), pair(-50, 0, 0, probability: 0.5)])))
        XCTAssertEqual(result.start, t(-50))
        XCTAssertEqual(result.latest.home, 0)
        XCTAssertEqual(result.yTicks, [0, 7])
    }

    func testNoValidPairsAndFutureOnlyAreUnavailable() {
        XCTAssertNil(Series.build(input([pair(0, nil, nil)])))
        XCTAssertNil(Series.build(input([pair(1801)])))
        XCTAssertNil(Series.build(input([pair(0)], start: 1900)))
    }
}
