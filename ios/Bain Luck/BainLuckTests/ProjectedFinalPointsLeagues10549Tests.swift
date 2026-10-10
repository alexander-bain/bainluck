import XCTest
@testable import Bain_Luck

/// #10239 / #10549 follow-through (Alex, 2026-10-10: "shouldn't projected
/// final score be an easy fix to show everywhere?"). The projected final-points
/// chart is admitted by league NAME, on the page's own sport key, with that
/// league's first period and axis step. One fixture per league proves units
/// (points, on a points axis) and orientation (the served home pair stays the
/// home team).
///
/// What production serves today, and what this pins about it: the server's
/// observed period-start markers (`precision` + `not_before`) are football-only
/// (`period_markers.TRANSITION_SPORT_PREFIXES`). So a basketball page charts its
/// projection before tip-off, and a live or finished basketball page keeps its
/// Score Differential card until the server observes basketball period starts.
@MainActor
final class ProjectedFinalPointsLeagues10549Tests: XCTestCase {
    private static let day = "2026-10-10"

    private func at(_ time: String) -> Date { "\(Self.day)T\(time):00Z".asDate! }

    /// A served marker. `precision: nil` is the shape every non-football marker
    /// has today: a scoring-play or game-state tier with no observed start.
    private func marker(_ time: String, _ period: String, source: String = "espn_state",
                        precision: String? = "first_seen") -> String {
        var fields = [#""timestamp":"\#(Self.day)T\#(time):00+00:00""#, #""period":"\#(period)""#,
                      #""source":"\#(source)""#]
        if let precision {
            fields += [#""precision":"\#(precision)""#, #""not_before":"\#(Self.day)T\#(time):00+00:00""#]
        }
        return "{" + fields.joined(separator: ",") + "}"
    }

    private func rec(_ minute: String, _ home: Double, _ away: Double, probability: Double) -> String {
        #"{"timestamp":"\#(Self.day)T\#(minute):00+00:00","home_probability":\#(probability),"projected_home_score":\#(home),"projected_away_score":\#(away),"kind":"recorded","observed_at":"\#(Self.day)T\#(minute):30.123456+00:00"}"#
    }

    private func history(status: String, completedAt: String = "null", pairs: [String],
                         scores: [(String, Int, Int)] = [], markers: [String] = []) throws -> EventHistoryResponse {
        let scoreRows = scores.map { #"{"timestamp":"\#(Self.day)T\#($0.0):00+00:00","home_score":\#($0.1),"away_score":\#($0.2)}"# }
        let json = """
        {"event_id":15330001,"home_team":"Home","away_team":"Away","status":"\(status)",
         "completed_at":\(completedAt),"history":[],
         "bookmaker_history":{"draftkings":[\(pairs.joined(separator: ","))]},
         "score_history":[\(scoreRows.joined(separator: ","))],
         "period_markers":[\(markers.joined(separator: ","))]}
        """
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(EventHistoryResponse.self, from: Data(json.utf8))
    }

    private var completedAt: String { #""\#(Self.day)T03:30:00Z""# }

    // MARK: - Basketball: pregame forecasts, on a basketball axis

    private var nbaPairs: [String] {
        [rec("00:10", 114.5, 109.0, probability: 0.64), rec("00:40", 115.0, 108.5, probability: 0.66)]
    }

    func testBasketballChartsItsProjectionBeforeTipOffOnAPointsAxis() throws {
        for sport in ["basketball_nba", "basketball_wnba", "basketball_ncaab", "basketball_wncaab"] {
            let h = try history(status: "scheduled", pairs: nbaPairs)
            let input = try XCTUnwrap(ProjectedFinalPointsMount.input(
                sportKey: sport, eventStatus: "scheduled", history: h, finalHome: nil, finalAway: nil,
                asOf: at("00:50")), sport)
            XCTAssertEqual(input.sportKey, sport, "the page's own key reaches the series, never a substitute")
            XCTAssertTrue(ProjectedFinalPointsMount.replacesScoreDifferential(input), sport)
            let series = try XCTUnwrap(ProjectedFinalPointsSeries.build(input), sport)
            XCTAssertEqual(series.phase, .before)
            XCTAssertTrue(series.actualSteps.isEmpty, "nothing has been scored before tip-off")
            // Orientation: the served home pair is the home team's line.
            XCTAssertEqual(series.latest.home, 115.0)
            XCTAssertEqual(series.latest.away, 108.5)
            // Units: twenty-point gridlines, not eighteen touchdown steps to 119.
            XCTAssertEqual(series.yTicks, [0, 20, 40, 60, 80, 100, 120], sport)
        }
    }

    func testBasketballDuringAndAfterWaitForAnObservedFirstPeriod() throws {
        // Today's served shape: basketball markers carry no observed start.
        let unobserved = [marker("00:58", "1st Quarter", source: "espn_box", precision: nil),
                          marker("01:30", "2nd Quarter", source: "statpal", precision: nil)]
        let finished = try history(status: "completed", completedAt: completedAt, pairs: nbaPairs,
                                   scores: [("01:10", 20, 18)], markers: unobserved)
        XCTAssertNil(ProjectedFinalPointsMount.input(
            sportKey: "basketball_nba", eventStatus: "completed", history: finished, finalHome: 110, finalAway: 104),
                     "a scoring-play marker is not an observed tip-off; the differential stays")
        let live = try history(status: "live", pairs: nbaPairs, scores: [("01:10", 20, 18)], markers: unobserved)
        XCTAssertNil(ProjectedFinalPointsMount.input(
            sportKey: "basketball_nba", eventStatus: "live", history: live, finalHome: nil, finalAway: nil,
            asOf: at("01:40")))

        // When the server serves an observed first quarter, the same page mounts.
        let observed = try history(status: "completed", completedAt: completedAt, pairs: nbaPairs,
                                   scores: [("01:10", 20, 18)], markers: [marker("00:58", "1st Quarter")])
        let input = try XCTUnwrap(ProjectedFinalPointsMount.input(
            sportKey: "basketball_nba", eventStatus: "completed", history: observed, finalHome: 110, finalAway: 104))
        XCTAssertEqual(input.scoreObservationStartAt, at("00:58"))
        let series = try XCTUnwrap(ProjectedFinalPointsSeries.build(input))
        XCTAssertEqual(series.phase, .after)
        XCTAssertEqual(series.latestActual, .init(at: at("03:30"), home: 110, away: 104), "the page's own final")
    }

    func testMensCollegeBasketballOpensOnAHalfAndWomensOnAQuarter() throws {
        func mounts(_ sport: String, _ period: String) throws -> Date? {
            let h = try history(status: "completed", completedAt: completedAt, pairs: nbaPairs,
                                scores: [("01:10", 20, 18)], markers: [marker("00:58", period)])
            return ProjectedFinalPointsMount.input(
                sportKey: sport, eventStatus: "completed", history: h, finalHome: 80, finalAway: 72)?
                .scoreObservationStartAt
        }
        XCTAssertEqual(try mounts("basketball_ncaab", "1st Half"), at("00:58"))
        XCTAssertEqual(try mounts("basketball_ncaab", "1"), at("00:58"), "a bare 1 in men's college is the 1st half")
        XCTAssertNil(try mounts("basketball_ncaab", "1st Quarter"), "men's college never opens on a quarter")
        XCTAssertEqual(try mounts("basketball_wncaab", "1st Quarter"), at("00:58"))
        XCTAssertNil(try mounts("basketball_wncaab", "1st Half"), "women's college plays quarters")
        XCTAssertNil(try mounts("basketball_nba", "1st Half"))
    }

    func testAMoneylineContradictionIsStillRefusedInBasketball() throws {
        // The book's own moneyline makes home the favourite, its points say otherwise.
        let h = try history(status: "scheduled", pairs: [rec("00:10", 100.0, 105.0, probability: 0.8)])
        XCTAssertNil(ProjectedFinalPointsMount.input(
            sportKey: "basketball_nba", eventStatus: "scheduled", history: h, finalHome: nil, finalAway: nil,
            asOf: at("00:50")))
    }

    // MARK: - College football: the NFL's whole contract

    func testCollegeFootballMountsBeforeDuringAndAfterLikeTheNFL() throws {
        let pairs = [rec("00:10", 31.5, 24.0, probability: 0.68), rec("01:00", 34.0, 21.0, probability: 0.8),
                     rec("02:30", 38.0, 24.0, probability: 0.9)]
        let markers = [marker("00:20", "1st Quarter"), marker("01:05", "2nd Quarter", precision: "boundary_observed")]

        let scheduled = try history(status: "scheduled", pairs: pairs, markers: markers)
        let before = try XCTUnwrap(ProjectedFinalPointsMount.input(
            sportKey: "americanfootball_ncaaf", eventStatus: "scheduled", history: scheduled,
            finalHome: nil, finalAway: nil, asOf: at("00:15")))
        XCTAssertEqual(ProjectedFinalPointsSeries.build(before)?.phase, .before)

        let live = try history(status: "live", pairs: pairs, scores: [("00:50", 7, 0)], markers: markers)
        let during = try XCTUnwrap(ProjectedFinalPointsMount.input(
            sportKey: "americanfootball_ncaaf", eventStatus: "live", history: live,
            finalHome: nil, finalAway: nil, asOf: at("01:20")))
        XCTAssertEqual(during.scoreObservationStartAt, at("00:20"))
        XCTAssertEqual(ProjectedFinalPointsSeries.build(during)?.phase, .during)

        let finished = try history(status: "completed", completedAt: completedAt, pairs: pairs,
                                   scores: [("00:50", 7, 0)], markers: markers)
        let after = try XCTUnwrap(ProjectedFinalPointsMount.input(
            sportKey: "americanfootball_ncaaf", eventStatus: "completed", history: finished,
            finalHome: 41, finalAway: 27))
        XCTAssertEqual(after.sportKey, "americanfootball_ncaaf")
        XCTAssertTrue(ProjectedFinalPointsMount.replacesScoreDifferential(after))
        let series = try XCTUnwrap(ProjectedFinalPointsSeries.build(after))
        XCTAssertEqual(series.phase, .after)
        XCTAssertEqual(series.latest.home, 38.0, "home stays home")
        XCTAssertEqual(series.latest.away, 24.0)
        XCTAssertEqual(series.yTicks, [0, 7, 14, 21, 28, 35, 42, 49], "football keeps its touchdown step (final 41 + headroom)")
        XCTAssertEqual(ProjectedFinalPointsChartView.gameStateMarkers(
            finished.periodMarkers, sportKey: "americanfootball_ncaaf", series: series,
            floor: after.scoreObservationStartAt).map(\.label), ["Q1", "Q2"])
    }

    // MARK: - Everything else keeps its differential

    func testUnlistedSportsMountNothingEvenWithValidPairsAndAnObservedStart() throws {
        let h = try history(status: "completed", completedAt: completedAt, pairs: nbaPairs,
                            markers: [marker("00:58", "1st Period"), marker("00:58", "1st Quarter"),
                                      marker("00:58", "Top 1st")])
        for sport: String? in ["icehockey_nhl", "baseball_mlb", "tennis_atp_us_open", "basketball_euroleague",
                               "americanfootball_ncaaf_fcs", "basketball", nil] {
            XCTAssertNil(ProjectedFinalPointsMount.input(
                sportKey: sport, eventStatus: "completed", history: h, finalHome: 3, finalAway: 2), sport ?? "nil")
            XCTAssertNil(ProjectedFinalPointsMount.firstRecordedGameStateAt(h.periodMarkers, sportKey: sport))
        }
    }

    // MARK: - Halves read as halves

    func testHalvesAreExplainedDrawnAndSpokenAsHalves() throws {
        let markers = [marker("00:58", "1st Half"), marker("01:40", "Halftime", precision: "boundary_observed"),
                       marker("02:00", "2nd Half", precision: "boundary_observed")]
        let pairs = [rec("00:50", 78.5, 71.0, probability: 0.7), rec("01:30", 80.0, 70.0, probability: 0.78),
                     rec("02:20", 81.0, 70.5, probability: 0.8)]
        let h = try history(status: "completed", completedAt: completedAt, pairs: pairs,
                            scores: [("01:10", 20, 18)], markers: markers)
        let input = try XCTUnwrap(ProjectedFinalPointsMount.input(
            sportKey: "basketball_ncaab", eventStatus: "completed", history: h, finalHome: 82, finalAway: 70))
        let series = try XCTUnwrap(ProjectedFinalPointsSeries.build(input))
        let drawn = ProjectedFinalPointsChartView.gameStateMarkers(
            h.periodMarkers, sportKey: "basketball_ncaab", series: series, floor: input.scoreObservationStartAt)
        XCTAssertEqual(drawn.map(\.label), ["1H", "HT", "2H"])
        let spoken = ProjectedFinalPointsChartView.markersSpoken(drawn)
        XCTAssertTrue(spoken.contains("1st half first seen in progress"), spoken)
        XCTAssertTrue(spoken.contains("2nd half began"), spoken)

        let halves = ProjectedFinalPointsChartView.markerExplanation(sportKey: "basketball_ncaab")
        XCTAssertTrue(halves.contains("(1H, HT, 2H, OT)"), halves)
        XCTAssertFalse(halves.contains("Q1"), "a halves game is never explained in quarters")
        for sport in ["americanfootball_nfl", "americanfootball_ncaaf", "basketball_nba", "basketball_wncaab"] {
            XCTAssertTrue(ProjectedFinalPointsChartView.markerExplanation(sportKey: sport).contains("(Q1–Q4, HT, OT)"), sport)
        }
        XCTAssertEqual(PeriodLabel.spoken("1H"), "1st half")
        XCTAssertEqual(PeriodLabel.spoken("2H"), "2nd half")
        XCTAssertEqual(PeriodLabel.spoken("H"), "H", "no number, no half")
    }
}
