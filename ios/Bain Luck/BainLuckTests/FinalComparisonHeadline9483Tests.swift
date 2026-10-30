import XCTest
import SwiftUI
@testable import Bain_Luck

/// #9483 — the finished-game comparison headline (`FinalComparisonHeadline9483`):
/// which value lands in which side's cell, what stands where a value is absent,
/// which rows it draws at all, how the difference from the forecast is worded,
/// and when the forecast is a control.
///
/// FIXTURES, AND WHAT EACH IS:
///
///   - COMMANDERS @ 49ERS is the RETAINED REAL NFL FINAL from
///     `FinalForecastComparison11296Tests` (event 14780563, trimmed from
///     Authority's served `/api/feed?mode=sports` capture, 2026-10-20 07:10Z):
///     Washington Commanders 17 at San Francisco 49ers 23, served projection
///     away 22.2 / home 29.4, 21 sportsbooks. That suite's `projection(...)`
///     builder is private, so `retainedProjection` below restates its served
///     field values verbatim and qualifies them through the production
///     `FinalForecastComparison11296.qualified`. The capture carries no
///     pre-match reading, so this case has none: the earlier chance stays
///     unavailable.
///   - BEARS/EAGLES is the approved design reference CONTROL
///     (`football-comparison-headline-20261023/final-375.png`, event
///     14780549): pre-match 0.365 / 0.635, forecast 19.5 / 23, final 27 / 7.
///     It is not a new app capture. Its forecast halves are put on the retained
///     projection's provenance fields and qualified through the same helper;
///     shared native formatting is the authority for the printed chance, so it
///     is asserted against `formatProbability`, never the reference's decimals.
///   - NBA, malformed pairs, zero/tiny differences and rendered-percent
///     overrides are CONSTRUCTED and say so where they are built.
///
/// No wire payload was fabricated and nothing here reads live data. These are
/// model tests: not pixel, layout, interaction or VoiceOver evidence.
@MainActor
final class FinalComparisonHeadline9483Tests: XCTestCase {

    private typealias H = FinalComparisonHeadline9483<EmptyView>
    private typealias F = FinalForecastComparison11296

    private static let nfl = "americanfootball_nfl"
    private static let nba = "basketball_nba"

    // MARK: - Builders

    /// The retained 14780563 projection's served fields, verbatim from
    /// `FinalForecastComparison11296Tests.projection`; only the halves move,
    /// and a moved half is a CONSTRUCTED control.
    private func retainedProjection(home: Double = 29.4, away: Double = 22.2) -> PregameProjection {
        PregameProjection(
            projectedHomeScore: home, projectedAwayScore: away,
            kind: "last_before_scheduled_start",
            earliestCapturedAt: "2026-10-19T22:15:21.773164+00:00",
            latestCapturedAt: "2026-10-20T00:12:13.153004+00:00",
            boundary: "scheduled_start", boundaryAt: "2026-10-20T00:15:00+00:00",
            source: "sportsbooks", basis: "consensus_spread_total", bookmakerCount: 21,
            unit: "points", period: "full_game")
    }

    /// The production qualification, exactly as the host calls it.
    private func qualified(
        sport: String = FinalComparisonHeadline9483Tests.nfl,
        away: Int, home: Int, projection: PregameProjection
    ) throws -> F.Qualified {
        try XCTUnwrap(
            F.qualified(sport: sport, status: "completed", homeScore: home, awayScore: away,
                        actualPeriod: F.actualPeriod(sport: sport, servedFinalScorePeriod: nil),
                        projection: projection),
            "fixture: the production qualification must admit this projection")
    }

    private func reading(away: Double, home: Double, served: Bool,
                         percents: [Int?]? = nil) -> PrematchReading {
        PrematchReading(awayProbability: away, homeProbability: home,
                        percents: percents ?? renderedDuelPercents(away: away, home: home),
                        source: PrematchReading.booksSource, isServed: served,
                        awayIsComplement: false)
    }

    private func resolve(
        sport: String? = FinalComparisonHeadline9483Tests.nfl, status: String? = "completed",
        paired: NFLPairedHeadline9483?, baseline: PrematchReading?,
        score: NFLPairedHeadline9483.Center?, forecast: F.Qualified?,
        away: String = "Chicago Bears", home: String = "Philadelphia Eagles",
        context: String = "Final · Sep 28", canInspect: Bool = false
    ) -> H.Resolved? {
        H.resolve(sportKey: sport, status: status, paired: paired, baseline: baseline,
                  score: score, forecast: forecast, awayName: away, homeName: home,
                  finalContext: context, canInspect: canInspect)
    }

    /// The design reference control's pieces (Bears away, won).
    private func bearsPaired(pregame: PrematchReading? = nil) -> NFLPairedHeadline9483? {
        NFLPairedHeadline9483.final(homeWon: false, score: (away: 27, home: 7), pregame: pregame)
    }
    private var bearsBaseline: PrematchReading { reading(away: 0.365, home: 0.635, served: true) }
    private func bearsForecast(home: Double = 23, away: Double = 19.5) throws -> F.Qualified {
        try qualified(away: 27, home: 7, projection: retainedProjection(home: home, away: away))
    }
    private func bears(canInspect: Bool = false) throws -> H.Resolved {
        try XCTUnwrap(resolve(paired: bearsPaired(), baseline: bearsBaseline,
                              score: .score(away: 27, home: 7, final: true),
                              forecast: try bearsForecast(), canInspect: canInspect))
    }

    /// The retained real final (49ers home, won), with no pre-match reading.
    private func commanders(canInspect: Bool = false) throws -> (H.Resolved, F.Qualified) {
        let forecast = try qualified(away: 17, home: 23, projection: retainedProjection())
        let paired = try XCTUnwrap(NFLPairedHeadline9483.final(
            homeWon: true, score: (away: 17, home: 23), pregame: nil))
        let r = try XCTUnwrap(resolve(
            paired: paired, baseline: nil, score: .score(away: 17, home: 23, final: true),
            forecast: forecast, away: "Washington Commanders", home: "San Francisco 49ers",
            canInspect: canInspect))
        return (r, forecast)
    }

    // MARK: - Binding

    func testEachValueLandsOnItsOwnSideAndColumn() throws {
        let r = try bears()
        let percents = renderedDuelPercents(away: 0.365, home: 0.635)

        XCTAssertEqual(r.away.name, "Chicago Bears")
        XCTAssertEqual(r.away.result, "Won")
        XCTAssertEqual(r.away.earlier.text, formatProbability(0.365, renderedPercent: percents[0]))
        XCTAssertEqual(r.away.forecast.text, "19.5")
        XCTAssertEqual(r.away.final.text, "27")
        XCTAssertEqual(r.away.difference.text, "+7.5")
        XCTAssertEqual(r.away.difference.suffix, "pts")

        XCTAssertEqual(r.home.name, "Philadelphia Eagles")
        XCTAssertEqual(r.home.result, "Lost")
        XCTAssertEqual(r.home.earlier.text, formatProbability(0.635, renderedPercent: percents[1]))
        XCTAssertEqual(r.home.forecast.text, "23")
        XCTAssertEqual(r.home.final.text, "7")
        XCTAssertEqual(r.home.difference.text, "\u{2212}16.0")

        XCTAssertEqual(r.headers, ["Pre-match chance", "Before-start forecast", "Final score", "vs forecast"])
        XCTAssertEqual(r.rows.map(\.isHome), [false, true], "away first, then home")
    }

    func testTheRetainedRealFinalComparesWithItsQualifiedRawHalves() throws {
        let (r, forecast) = try commanders()
        XCTAssertEqual(forecast.comparison.away, 22, "the rounded card value exists…")
        XCTAssertEqual(forecast.comparison.home, 29)
        XCTAssertEqual(forecast.comparison.bookmakerCount, 21)

        XCTAssertEqual(r.away.forecast.text, "22.2", "…but the headline prints the raw half")
        XCTAssertEqual(r.home.forecast.text, "29.4")
        XCTAssertEqual(r.away.final.text, "17")
        XCTAssertEqual(r.home.final.text, "23")
        XCTAssertEqual(r.away.difference.text, "\u{2212}5.2", "17 − 22.2, not 17 − 22")
        XCTAssertEqual(r.home.difference.text, "\u{2212}6.4", "23 − 29.4, not 23 − 29")
        XCTAssertEqual(r.away.result, "Lost")
        XCTAssertEqual(r.home.result, "Won")
        // The capture carries no pre-match reading, so none is shown.
        XCTAssertFalse(r.away.earlier.isValue)
        XCTAssertFalse(r.home.earlier.isValue)
        XCTAssertEqual(r.headers.first, "Earlier chance")
    }

    func testNoRoundedComparisonIsTurnedBackIntoTheForecast() throws {
        let forecast = try bearsForecast()
        XCTAssertEqual(forecast.comparison.away, 20, "19.5 rounds half up on the card")
        let r = try bears()
        XCTAssertEqual(r.away.forecast.text, "19.5")
        XCTAssertEqual(r.away.difference.text, "+7.5", "not 27 − 20")
    }

    // MARK: - Earlier chance

    func testTheEarlierChanceKeepsTheReadingsOwnWordAndRenderedPercent() throws {
        let served = try XCTUnwrap(resolve(paired: bearsPaired(), baseline: bearsBaseline,
                                           score: nil, forecast: nil))
        XCTAssertEqual(served.away.earlier.label, "Pre-match chance")

        let opened = try XCTUnwrap(resolve(paired: bearsPaired(),
                                           baseline: reading(away: 0.365, home: 0.635, served: false),
                                           score: nil, forecast: nil))
        XCTAssertEqual(opened.away.earlier.label, "Opened chance", "an opening line is never called pre-match")
        XCTAssertEqual(opened.away.earlier.spoken, "Opened chance: \(opened.away.earlier.text)")

        // CONSTRUCTED: a served rendered pair that differs from local rounding.
        let override = try XCTUnwrap(resolve(
            paired: bearsPaired(), baseline: reading(away: 0.365, home: 0.635, served: true, percents: [40, 60]),
            score: nil, forecast: nil))
        XCTAssertEqual(override.away.earlier.text, formatProbability(0.365, renderedPercent: 40))
        XCTAssertEqual(override.home.earlier.text, formatProbability(0.635, renderedPercent: 60))
    }

    func testAMissingBaselineIsUnavailableNeverATerminalChanceOrTheSidesPregameWords() throws {
        // The paired arm carries its own pregame caption words; they are not parsed.
        let paired = bearsPaired(pregame: reading(away: 0.2, home: 0.8, served: true))
        XCTAssertNotNil(paired?.away.pregame)
        let r = try XCTUnwrap(resolve(paired: paired, baseline: nil,
                                      score: .score(away: 27, home: 7, final: true),
                                      forecast: try bearsForecast()))
        for row in r.rows {
            XCTAssertEqual(row.earlier.text, H.unavailableText)
            XCTAssertFalse(row.earlier.isValue)
            for terminal in ["100%", "0%", ">99%", "<1%", "20%", "80%"] {
                XCTAssertNotEqual(row.earlier.text, terminal)
            }
        }
        XCTAssertEqual(r.away.earlier.label, "Earlier chance")
        // A missing chance does not suppress the score comparison.
        XCTAssertEqual(r.away.final.text, "27")
        XCTAssertEqual(r.away.difference.text, "+7.5")
    }

    func testTheVerdictNeverEntersAProbabilityColumn() throws {
        for r in [try bears(), try commanders().0] {
            for row in r.rows {
                for cell in row.cells {
                    XCTAssertFalse(cell.text.contains("Won") || cell.text.contains("Lost"), cell.text)
                }
            }
        }
    }

    // MARK: - Final score

    func testAGenuineZeroScoreIsZeroAndAbsentOrNonfinalIsUnavailable() throws {
        // CONSTRUCTED: a shutout.
        let shutout = try XCTUnwrap(resolve(
            paired: NFLPairedHeadline9483.final(homeWon: true, score: (away: 0, home: 24), pregame: nil),
            baseline: nil, score: .score(away: 0, home: 24, final: true),
            forecast: try qualified(away: 0, home: 24, projection: retainedProjection(home: 23, away: 19.5))))
        XCTAssertEqual(shutout.away.final.text, "0")
        XCTAssertTrue(shutout.away.final.isValue)
        XCTAssertEqual(shutout.away.difference.text, "\u{2212}19.5")

        let absent: [NFLPairedHeadline9483.Center?] = [nil, .versus, .score(away: 27, home: 7, final: false)]
        for score in absent {
            let r = try XCTUnwrap(resolve(paired: bearsPaired(), baseline: bearsBaseline, score: score,
                                          forecast: try bearsForecast(), canInspect: true))
            for row in r.rows {
                XCTAssertEqual(row.final.text, H.unavailableText, "\(String(describing: score))")
                XCTAssertEqual(row.difference.text, H.unavailableText)
                XCTAssertFalse(row.inspects)
            }
            XCTAssertEqual(r.away.forecast.text, "19.5", "the forecast stands without a final")
        }
    }

    func testThePairsCentreNeverStandsInForTheScoreboard() throws {
        let paired = try XCTUnwrap(bearsPaired())
        XCTAssertEqual(paired.center, .score(away: 27, home: 7, final: true))
        let r = try XCTUnwrap(resolve(paired: paired, baseline: nil, score: nil, forecast: nil))
        XCTAssertEqual(r.away.final.text, H.unavailableText)
        XCTAssertEqual(r.home.final.text, H.unavailableText)
    }

    // MARK: - Forecast and difference

    func testAMissingForecastRemovesOnlyTheForecastAndTheDifference() throws {
        let r = try XCTUnwrap(resolve(paired: bearsPaired(), baseline: bearsBaseline,
                                      score: .score(away: 27, home: 7, final: true),
                                      forecast: nil, canInspect: true))
        for row in r.rows {
            XCTAssertEqual(row.forecast.text, H.unavailableText)
            XCTAssertEqual(row.difference.text, H.unavailableText)
            XCTAssertTrue(row.earlier.isValue)
            XCTAssertTrue(row.final.isValue)
            XCTAssertFalse(row.inspects)
        }
        XCTAssertEqual(r.away.forecast.spoken, "Before-start forecast: Unavailable")
        XCTAssertEqual(r.away.difference.spoken, "Difference from forecast: Unavailable")
    }

    func testTheDifferenceIsWordedByArithmeticOnly() throws {
        let r = try bears()
        XCTAssertEqual(r.away.difference.spoken, "Difference from forecast: 7.5 points above")
        XCTAssertEqual(r.home.difference.spoken, "Difference from forecast: 16.0 points below")

        // CONSTRUCTED: an exact forecast is "At forecast", never ±0.0.
        let exact = try XCTUnwrap(resolve(paired: bearsPaired(), baseline: nil,
                                          score: .score(away: 27, home: 7, final: true),
                                          forecast: try bearsForecast(home: 23, away: 27)))
        XCTAssertEqual(exact.away.forecast.text, "27")
        XCTAssertEqual(exact.away.difference.text, "0")
        XCTAssertEqual(exact.away.difference.spoken, "Difference from forecast: At forecast")

        // CONSTRUCTED: a real difference under the shared magnitude's precision.
        let tiny = try XCTUnwrap(resolve(paired: bearsPaired(), baseline: nil,
                                         score: .score(away: 27, home: 7, final: true),
                                         forecast: try bearsForecast(home: 7.04, away: 26.96)))
        XCTAssertEqual(tiny.away.difference.text, "<0.1")
        XCTAssertEqual(tiny.away.difference.suffix, "pts above")
        XCTAssertEqual(tiny.away.difference.spoken, "Difference from forecast: less than 0.1 points above")
        XCTAssertEqual(tiny.home.difference.text, "<0.1")
        XCTAssertEqual(tiny.home.difference.suffix, "pts below")
        for row in tiny.rows {
            XCTAssertFalse(row.difference.text.contains("0.0"), "never +0.0 or −0.0")
        }

        // The magnitude is the shared formatter's.
        XCTAssertEqual(H.differenceCell(actual: 27, forecast: 19.5, unit: "points").text,
                       "+\(deltaPointsNumber(7.5))")
    }

    // MARK: - Applicability

    func testOnlyAFinishedNFLOrNBARowWithADecidedPairApplies() throws {
        let paired = bearsPaired()
        for status in ["completed", "closed"] {
            XCTAssertNotNil(resolve(status: status, paired: paired, baseline: nil, score: nil, forecast: nil), status)
        }
        for status: String? in ["live", "scheduled", "suspended", nil] {
            XCTAssertNil(resolve(status: status, paired: paired, baseline: nil, score: nil, forecast: nil),
                         String(describing: status))
        }
        for sport: String? in ["baseball_mlb", "icehockey_nhl", "soccer_epl", "tennis_atp_us_open", nil] {
            XCTAssertNil(resolve(sport: sport, paired: paired, baseline: nil, score: nil, forecast: nil),
                         String(describing: sport))
        }

        // CONSTRUCTED NBA final.
        let nbaForecast = try qualified(sport: Self.nba, away: 104, home: 110,
                                        projection: retainedProjection(home: 112.5, away: 106))
        let nba = try XCTUnwrap(resolve(
            sport: Self.nba,
            paired: NFLPairedHeadline9483.final(homeWon: true, score: (away: 104, home: 110), pregame: nil),
            baseline: nil, score: .score(away: 104, home: 110, final: true), forecast: nbaForecast,
            away: "Indiana Pacers", home: "New Orleans Pelicans"))
        XCTAssertEqual(nba.home.forecast.text, "112.5")
        XCTAssertEqual(nba.home.difference.text, "\u{2212}2.5")
        XCTAssertEqual(nba.away.difference.text, "\u{2212}2.0")
    }

    func testNoWinnerIsInferredHere() throws {
        // No pair, a priced pair, and malformed (CONSTRUCTED) verdicts all decline.
        XCTAssertNil(resolve(paired: nil, baseline: nil, score: .score(away: 27, home: 7, final: true), forecast: nil))
        let priced = NFLPairedHeadline9483.priced(awayText: "60%", homeText: "40%", live: false,
                                                  score: nil, pregame: nil)
        XCTAssertNil(resolve(paired: priced, baseline: nil, score: .score(away: 27, home: 7, final: true), forecast: nil))
        let bothWon = NFLPairedHeadline9483(
            away: .init(figure: "Won", pregame: nil, won: true),
            home: .init(figure: "Won", pregame: nil, won: true),
            center: .versus)
        XCTAssertNil(resolve(paired: bothWon, baseline: nil, score: nil, forecast: nil))
        let oneMissing = NFLPairedHeadline9483(
            away: .init(figure: "Won", pregame: nil, won: true),
            home: .init(figure: "Lost", pregame: nil, won: nil),
            center: .versus)
        XCTAssertNil(resolve(paired: oneMissing, baseline: nil, score: nil, forecast: nil))

        // CONSTRUCTED: the supplied verdict is printed even where the scores
        // would say the other team won; the scores never decide it here.
        let r = try XCTUnwrap(resolve(
            paired: NFLPairedHeadline9483.final(homeWon: true, score: nil, pregame: nil),
            baseline: nil, score: .score(away: 27, home: 7, final: true), forecast: nil))
        XCTAssertEqual(r.away.result, "Lost")
        XCTAssertEqual(r.home.result, "Won")
    }

    // MARK: - Context

    func testTheFinalContextIsCarriedAsGiven() throws {
        XCTAssertEqual(try bears().finalContext, "Final · Sep 28")
        let r = try XCTUnwrap(resolve(paired: bearsPaired(), baseline: nil, score: nil, forecast: nil,
                                      context: "Final/OT · Oct 19"))
        XCTAssertEqual(r.finalContext, "Final/OT · Oct 19")
    }

    // MARK: - Inspection

    func testInspectionNeedsTheForecastTheFinalAndTheHostsCallback() throws {
        XCTAssertTrue(try bears(canInspect: true).rows.allSatisfy(\.inspects))
        XCTAssertFalse(try bears(canInspect: false).rows.contains(where: \.inspects))
        let noForecast = try XCTUnwrap(resolve(paired: bearsPaired(), baseline: bearsBaseline,
                                               score: .score(away: 27, home: 7, final: true),
                                               forecast: nil, canInspect: true))
        XCTAssertFalse(noForecast.rows.contains(where: \.inspects))
        let noFinal = try XCTUnwrap(resolve(paired: bearsPaired(), baseline: bearsBaseline, score: nil,
                                            forecast: try bearsForecast(), canInspect: true))
        XCTAssertFalse(noFinal.rows.contains(where: \.inspects))
        // A missing chance does not take the control away.
        let noBaseline = try XCTUnwrap(resolve(paired: bearsPaired(), baseline: nil,
                                               score: .score(away: 27, home: 7, final: true),
                                               forecast: try bearsForecast(), canInspect: true))
        XCTAssertTrue(noBaseline.rows.allSatisfy(\.inspects))

        let view = H(sportKey: Self.nfl, status: "completed", paired: bearsPaired(), baseline: nil,
                     score: nil, forecast: nil, awayName: "Chicago Bears", homeName: "Philadelphia Eagles",
                     awayColor: .blue, homeColor: .green, finalContext: "Final")
        XCTAssertNil(view.onForecastInspection, "no callback unless the host passes one")
    }

    func testInspectionCallsBackForItsExactSide() throws {
        var sides: [Bool] = []
        let inspect: (Bool) -> Void = { sides.append($0) }
        let r = try bears(canInspect: true)
        H.perform(r.home, inspect: inspect)
        H.perform(r.away, inspect: inspect)
        XCTAssertEqual(sides, [true, false])

        H.perform(try bears(canInspect: false).away, inspect: inspect)
        H.perform(r.away, inspect: nil)
        XCTAssertEqual(sides, [true, false], "a plain row and a missing callback call nothing")
    }

    // MARK: - Speech

    func testEachTeamIsSpokenWithItsResultAndTheFullForecastBasis() throws {
        let r = try bears(canInspect: true)
        XCTAssertEqual(r.away.spokenSummary,
                       "Chicago Bears, Won. Pre-match chance: \(r.away.earlier.text). "
                       + "Projection before scheduled start: 19.5 points. Final score: 27. "
                       + "Difference from forecast: 7.5 points above")
        XCTAssertEqual(r.away.actionLabel, "Compare final with forecast, Chicago Bears")
        XCTAssertEqual(r.home.actionLabel, "Compare final with forecast, Philadelphia Eagles")

        let (real, _) = try commanders()
        XCTAssertEqual(real.away.spokenSummary,
                       "Washington Commanders, Lost. Earlier chance: Unavailable. "
                       + "Projection before scheduled start: 22.2 points. Final score: 17. "
                       + "Difference from forecast: 5.2 points below")
        XCTAssertNil(real.away.actionLabel)

        // No grading, venue or question words in anything shown or spoken.
        let chrome = r.headers + r.rows.flatMap { [$0.spokenSummary, $0.actionLabel ?? ""] }
            + r.rows.flatMap { $0.cells.map { $0.text + ($0.suffix ?? "") } }
        for word in ["beat", "right", "wrong", "hit", "miss", "exceed", "reached", "settled",
                     "price", "odds", "market", "book", "?"] {
            XCTAssertFalse(chrome.contains { $0.lowercased().contains(word) }, word)
        }
    }

    // MARK: - Layout decision

    func testAccessibilitySizesTakeTheLabelledPairsAndOthersTryTheColumns() {
        for size in DynamicTypeSize.allCases {
            XCTAssertEqual(H.arrangement(typeSize: size),
                           size.isAccessibilitySize ? .labelledPairs : .columnsWhenTheyFit, "\(size)")
        }
    }
}
