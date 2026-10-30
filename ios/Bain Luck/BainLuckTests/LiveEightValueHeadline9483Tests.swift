import XCTest
import SwiftUI
@testable import Bain_Luck

/// #9483 — the live eight-value headline (`LiveEightValueHeadline9483`): which
/// value lands in which side's cell, what stands where a value is absent, which
/// rows it draws at all, and when a projected final is a control.
///
/// FIXTURES. Every input is built the way the existing suites build it:
/// `PrematchReading` as `RecognizableNFLPage9483Tests` does, the paired pair
/// through `NFLPairedHeadline9483.priced` / `.final`, the admitted in-play pair
/// as `LivePregameComparison11296Tests.current` does, and the retained pair
/// through `LivePregameComparison11296.resolve` on a decoded object.
///
///   - PACERS/PELICANS is the REFERENCE CONTROL from the selected design image
///     (`eight-value-live-scoreboard-study-20261022/visual-refinement/
///     displayed-3-compact-momentum.png`): opening 56/44, now 21/79, score
///     91/99, projected 117/121, Q4 8:50. It is not a captured feed. The image
///     carries no retained pregame projection, so this control has none.
///   - BEARS/EAGLES is the football reference's CONTROL
///     (`football-comparison-headline-20261023`, event 14780549): pregame
///     0.365/0.635, Q3 0.8557/0.1443, score 20/7, projected 25.5/18. Shared
///     native formatting is the authority, so the printed text is asserted
///     against `formatProbability`, never against the reference's decimals.
///   - `baselineNFL` is `LivePregameComparison11296Tests`' CONSTRUCTED retained
///     object, verbatim, for the comparison-action cases.
///
/// None of this is a wire payload, an app blend or pixel/VoiceOver evidence.
@MainActor
final class LiveEightValueHeadline9483Tests: XCTestCase {

    private typealias H = LiveEightValueHeadline9483<EmptyView>
    private typealias A = LiveProjectedFinalAdmission2920

    private static let nfl = "americanfootball_nfl"
    private static let nba = "basketball_nba"
    private static let start = "2026-10-19T20:25:00+00:00"
    private static let startDate = ISO8601DateFormatter().date(from: "2026-10-19T20:25:00Z")!

    /// `LivePregameComparison11296Tests.baselineNFL`, verbatim (CONSTRUCTED).
    private static let baselineNFL = #"""
    {"projected_home_score": 23.5, "projected_away_score": 20.5, "kind": "last_before_scheduled_start", "earliest_captured_at": "2026-10-19T18:02:00+00:00", "latest_captured_at": "2026-10-19T20:21:00+00:00", "boundary": "scheduled_start", "boundary_at": "2026-10-19T20:25:00+00:00", "source": "sportsbooks", "basis": "consensus_spread_total", "bookmaker_count": 4, "unit": "points", "period": "full_game"}
    """#

    // MARK: - Builders

    private func reading(away: Double, home: Double, served: Bool) -> PrematchReading {
        PrematchReading(awayProbability: away, homeProbability: home,
                        percents: renderedDuelPercents(away: away, home: home),
                        source: PrematchReading.booksSource, isServed: served,
                        awayIsComplement: false)
    }

    /// An admitted current pair, as `LiveProjectedFinal2920.page` hands it on.
    private func printed(home: Double, away: Double) -> A.Printed {
        A.Printed(
            label: "Projected final", home: Int(home.rounded()), away: Int(away.rounded()),
            admitted: A.AdmittedPair(
                home: home, away: away,
                provenance: A.Provenance(
                    bookmakerCount: 2, scheduledStart: Self.startDate,
                    earliestConfirmedAt: Self.startDate.addingTimeInterval(2460),
                    latestCapturedAt: Self.startDate.addingTimeInterval(2460),
                    unit: .points, period: .fullGame)))
    }

    private func projection(_ json: String) throws -> PregameProjection {
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        return try d.decode(PregameProjection.self, from: Data(json.utf8))
    }

    /// A live NFL forecast whose retained pair the production comparator admits.
    private func comparedForecast(home: Double = 18, away: Double = 25.5) throws -> LivePregameComparison11296.Headline {
        let current = printed(home: home, away: away)
        let retained = try projection(Self.baselineNFL)
        let baseline = LivePregameComparison11296.resolve(
            status: "live", sport: Self.nfl, commenceTime: Self.start,
            current: current, projection: retained)
        XCTAssertNotNil(baseline, "fixture: the production comparator must admit the retained pair")
        return LivePregameComparison11296.Headline(current: current, baseline: baseline)
    }

    private func pacersPaired(live: Bool = true) -> NFLPairedHeadline9483 {
        NFLPairedHeadline9483.priced(awayText: "21%", homeText: "79%", live: live,
                                     score: (away: 91, home: 99), pregame: nil)
    }

    private func resolve(
        sport: String? = LiveEightValueHeadline9483Tests.nba, status: String? = "live",
        paired: NFLPairedHeadline9483?, phase: EventHeadlinePhase9483? = .current,
        baseline: PrematchReading?, score: NFLPairedHeadline9483.Center?,
        forecast: LivePregameComparison11296.Headline?,
        away: String = "Indiana Pacers", home: String = "New Orleans Pelicans",
        canCompare: Bool = false, earlierAway: Bool = false, earlierHome: Bool = false
    ) -> H.Resolved? {
        H.resolve(sportKey: sport, status: status, paired: paired, chancePhase: phase,
                  baseline: baseline, score: score, forecast: forecast,
                  awayName: away, homeName: home, gameState: "Q4 8:50",
                  canCompare: canCompare, earlierAway: earlierAway, earlierHome: earlierHome)
    }

    /// The reference control, whole.
    private func pacers() throws -> H.Resolved {
        try XCTUnwrap(resolve(
            paired: pacersPaired(),
            baseline: reading(away: 0.56, home: 0.44, served: false),
            score: .score(away: 91, home: 99, final: false),
            forecast: LivePregameComparison11296.Headline(current: printed(home: 121, away: 117), baseline: nil)))
    }

    // MARK: - Binding

    func testEightValuesLandOnTheirOwnSideAndColumn() throws {
        let r = try pacers()
        XCTAssertEqual(r.away.name, "Indiana Pacers")
        XCTAssertEqual(r.home.name, "New Orleans Pelicans")
        XCTAssertFalse(r.away.isHome)
        XCTAssertTrue(r.home.isHome)
        XCTAssertEqual(r.away.cells.map(\.text), ["56%", "21%", "91", "117"])
        XCTAssertEqual(r.home.cells.map(\.text), ["44%", "79%", "99", "121"])
        XCTAssertEqual(r.headers, ["Opened chance", "Current chance", "Score", "Projected final"])
        XCTAssertTrue((r.away.cells + r.home.cells).allSatisfy(\.isValue))
        XCTAssertEqual(r.gameState, "Q4 8:50")
    }

    func testTheEarlierChanceIsTheReadingsOwnPairUnderItsOwnWord() throws {
        let served = reading(away: 0.365, home: 0.635, served: true)
        let r = try XCTUnwrap(resolve(sport: Self.nfl, paired: pacersPaired(), baseline: served,
                                      score: nil, forecast: nil))
        XCTAssertEqual(r.away.earlier.label, "Pre-match chance")
        XCTAssertEqual(r.away.earlier.text, formatProbability(0.365, renderedPercent: served.percents[0]))
        XCTAssertEqual(r.home.earlier.text, formatProbability(0.635, renderedPercent: served.percents[1]))

        let opened = reading(away: 0.365, home: 0.635, served: false)
        let o = try XCTUnwrap(resolve(sport: Self.nfl, paired: pacersPaired(), baseline: opened,
                                      score: nil, forecast: nil))
        XCTAssertEqual(o.away.earlier.label, "Opened chance")
        XCTAssertFalse(o.headers.contains { $0.lowercased().contains("pregame") })

        // The reading's rendered integer wins over local rounding; the endpoint
        // guard still runs on the probability.
        let rendered = PrematchReading(awayProbability: 0.565, homeProbability: 0.435, percents: [56, 44],
                                       source: "kalshi", isServed: true, awayIsComplement: false)
        let e = try XCTUnwrap(resolve(paired: pacersPaired(), baseline: rendered, score: nil, forecast: nil))
        XCTAssertEqual(e.away.earlier.text, "56%")
        XCTAssertEqual(e.home.earlier.text, "44%")
        let edge = PrematchReading(awayProbability: 0.004, homeProbability: 0.996, percents: [0, 100],
                                   source: "kalshi", isServed: true, awayIsComplement: false)
        let g = try XCTUnwrap(resolve(paired: pacersPaired(), baseline: edge, score: nil, forecast: nil))
        XCTAssertEqual(g.away.earlier.text, "<1%")
        XCTAssertEqual(g.home.earlier.text, ">99%")
    }

    func testTheFootballControlPrintsWhatSharedFormattingPrints() throws {
        let pregame = reading(away: 0.365, home: 0.635, served: true)
        let paired = NFLPairedHeadline9483.priced(
            awayText: formatProbability(0.8557), homeText: formatProbability(0.1443), live: true,
            score: (away: 20, home: 7), pregame: pregame)
        let r = try XCTUnwrap(resolve(
            sport: Self.nfl, paired: paired, baseline: pregame,
            score: .score(away: 20, home: 7, final: false),
            forecast: try comparedForecast(home: 18, away: 25.5),
            away: "Chicago Bears", home: "Philadelphia Eagles"))
        XCTAssertEqual(r.away.current.text, paired.away.figure)
        XCTAssertEqual(r.home.current.text, paired.home.figure)
        XCTAssertEqual(r.away.score.text, "20")
        XCTAssertEqual(r.home.score.text, "7")
        // The printed integers the admission rounded, never the raw halves.
        XCTAssertEqual(r.away.projected.text, "\(Int((25.5).rounded()))")
        XCTAssertEqual(r.home.projected.text, "18")
        // The paired side's baseline string is never taken apart or reprinted.
        XCTAssertNotEqual(r.away.earlier.text, paired.away.pregame)
    }

    func testAMissingBaselineIsUnavailableNeverTheCurrentNumber() throws {
        let r = try XCTUnwrap(resolve(paired: pacersPaired(), baseline: nil,
                                      score: .score(away: 91, home: 99, final: false), forecast: nil))
        XCTAssertEqual(r.away.earlier, H.Cell(label: "Earlier chance", text: "Unavailable", isValue: false))
        XCTAssertEqual(r.home.earlier.text, "Unavailable")
        XCTAssertEqual(r.away.current.text, "21%")
    }

    func testADrawPricedSportsComplementIsWithheldAsTheSharedGuardWithholdsIt() {
        // This view declines every draw-priced sport before the guard is reached;
        // the guard itself is the existing helper's, unchanged.
        XCTAssertNil(resolve(sport: "soccer_epl", paired: pacersPaired(),
                             baseline: reading(away: 0.3, home: 0.4, served: true), score: nil, forecast: nil))
        XCTAssertNil(DrawPricedWinner.printablePair(away: 0.3, home: 0.4, sport: "soccer_epl")?.away)
    }

    // MARK: - Zero and missing

    func testAGenuineZeroScoreStaysZeroAndAMissingScoreIsUnavailable() throws {
        let zero = try XCTUnwrap(resolve(paired: pacersPaired(), baseline: nil,
                                         score: .score(away: 0, home: 0, final: false), forecast: nil))
        XCTAssertEqual(zero.away.score, H.Cell(label: "Score", text: "0", isValue: true))
        XCTAssertEqual(zero.home.score.text, "0")

        for missing: NFLPairedHeadline9483.Center? in [nil, .versus, .score(away: 91, home: 99, final: true)] {
            let r = try XCTUnwrap(resolve(paired: pacersPaired(), baseline: nil, score: missing, forecast: nil))
            XCTAssertEqual(r.away.score.text, "Unavailable", "\(String(describing: missing))")
            XCTAssertEqual(r.home.score.text, "Unavailable")
            XCTAssertFalse(r.away.score.isValue)
        }
    }

    func testThePairsCentreNeverStandsInForTheSuppliedScore() throws {
        // paired.center carries 91–99; the scoreboard admission supplied none.
        let r = try XCTUnwrap(resolve(paired: pacersPaired(), baseline: nil, score: nil, forecast: nil))
        XCTAssertEqual(r.away.score.text, "Unavailable")
        // And a supplied score prints with no pair at all.
        let s = try XCTUnwrap(resolve(paired: nil, baseline: nil,
                                      score: .score(away: 3, home: 10, final: false), forecast: nil))
        XCTAssertEqual(s.away.score.text, "3")
        XCTAssertEqual(s.home.score.text, "10")
        XCTAssertEqual(s.away.current.text, "Unavailable")
    }

    // MARK: - Current chance

    func testTheCurrentChanceFollowsTheHostsPhaseAndNothingElseMoves() throws {
        let baseline = reading(away: 0.56, home: 0.44, served: false)
        let score: NFLPairedHeadline9483.Center = .score(away: 91, home: 99, final: false)

        let current = try XCTUnwrap(resolve(paired: pacersPaired(), phase: .current,
                                            baseline: baseline, score: score, forecast: nil))
        XCTAssertEqual(current.away.current, H.Cell(label: "Current chance", text: "21%", isValue: true))

        let stale = try XCTUnwrap(resolve(paired: pacersPaired(), phase: .lastRecorded,
                                          baseline: baseline, score: score, forecast: nil))
        XCTAssertEqual(stale.away.current.text, "No recent probability")
        XCTAssertEqual(stale.home.current.text, "No recent probability")
        XCTAssertFalse(stale.away.current.isValue)
        XCTAssertFalse((stale.away.cells + stale.home.cells).contains { $0.text == "21%" || $0.text == "79%" })

        let none = try XCTUnwrap(resolve(paired: pacersPaired(), phase: nil,
                                         baseline: baseline, score: score, forecast: nil))
        XCTAssertEqual(none.away.current.text, "Unavailable")

        for r in [current, stale, none] {
            XCTAssertEqual(r.away.earlier.text, "56%")
            XCTAssertEqual(r.home.score.text, "99")
        }
    }

    func testOnlyAPricedSideSuppliesTheCurrentColumn() throws {
        let absent = try XCTUnwrap(resolve(paired: nil, baseline: nil, score: nil, forecast: nil))
        XCTAssertEqual(absent.away.current.text, "Unavailable")

        // A decided pair handed in at a live status draws no Won/Lost as a chance.
        let decided = try XCTUnwrap(NFLPairedHeadline9483.final(homeWon: true, score: (away: 91, home: 99), pregame: nil))
        let r = try XCTUnwrap(resolve(paired: decided, baseline: nil,
                                      score: .score(away: 91, home: 99, final: false), forecast: nil))
        XCTAssertEqual(r.away.current.text, "Unavailable")
        XCTAssertEqual(r.home.current.text, "Unavailable")
    }

    func testNoFinalOrVerdictWordsLeakIntoALiveHeadline() throws {
        let decided = try XCTUnwrap(NFLPairedHeadline9483.final(homeWon: false, score: (away: 99, home: 91), pregame: nil))
        let r = try XCTUnwrap(resolve(paired: decided, baseline: nil,
                                      score: .score(away: 99, home: 91, final: true), forecast: nil))
        let words = (r.away.cells + r.home.cells).flatMap { [$0.text, $0.label] } + r.headers
        for word in ["Won", "Lost", "Final", "final score"] {
            XCTAssertFalse(words.contains { $0.contains(word) && !$0.contains("Projected final") }, word)
        }
    }

    // MARK: - Applicability

    func testOnlyALiveNFLOrNBARowApplies() {
        XCTAssertTrue(H.applies(sportKey: Self.nfl, status: "live"))
        XCTAssertTrue(H.applies(sportKey: Self.nba, status: "live"))
        for status in ["scheduled", "final", "completed", "suspended", "postponed", nil] as [String?] {
            XCTAssertFalse(H.applies(sportKey: Self.nfl, status: status), "\(String(describing: status))")
            XCTAssertNil(resolve(sport: Self.nfl, status: status, paired: pacersPaired(), baseline: nil,
                                 score: nil, forecast: nil))
        }
        for sport in ["soccer_epl", "baseball_mlb", "americanfootball_ncaaf", "basketball_wnba", "tennis", nil] as [String?] {
            XCTAssertFalse(H.applies(sportKey: sport, status: "live"), "\(String(describing: sport))")
        }
    }

    // MARK: - Forecast

    func testAWithdrawnForecastLeavesEveryOtherValueStanding() throws {
        let whole = try pacers()
        let withdrawn = try XCTUnwrap(resolve(
            paired: pacersPaired(), baseline: reading(away: 0.56, home: 0.44, served: false),
            score: .score(away: 91, home: 99, final: false), forecast: nil))
        XCTAssertEqual(withdrawn.away.projected, H.Cell(label: "Projected final", text: "Unavailable", isValue: false))
        XCTAssertEqual(withdrawn.home.projected.text, "Unavailable")
        XCTAssertEqual(Array(withdrawn.away.cells.prefix(3)), Array(whole.away.cells.prefix(3)))
        XCTAssertEqual(Array(withdrawn.home.cells.prefix(3)), Array(whole.home.cells.prefix(3)))
        XCTAssertEqual(withdrawn.away.action, .plain)
    }

    func testTheProjectedFinalKeepsTheForecastsOwnLabel() throws {
        let current = A.Printed(label: "Projected final (90 min)", home: 2, away: 1,
                                admitted: printed(home: 2, away: 1).admitted)
        let r = try XCTUnwrap(resolve(paired: nil, baseline: nil, score: nil,
                                      forecast: LivePregameComparison11296.Headline(current: current, baseline: nil)))
        XCTAssertEqual(r.away.projected.label, "Projected final (90 min)")
        XCTAssertEqual(r.away.projected.spoken, "Projected final (90 min): 1")
    }

    // MARK: - Actions

    func testTheCompareControlNeedsTheAdmittedBaselineAndTheHostsCallback() throws {
        let compared = try comparedForecast()
        let both = try XCTUnwrap(resolve(sport: Self.nfl, paired: nil, baseline: nil, score: nil,
                                         forecast: compared, canCompare: true))
        XCTAssertEqual(both.away.action, .compare)
        XCTAssertEqual(both.home.action, .compare)

        let noCallback = try XCTUnwrap(resolve(sport: Self.nfl, paired: nil, baseline: nil, score: nil,
                                               forecast: compared, canCompare: false))
        XCTAssertEqual(noCallback.away.action, .plain)
        XCTAssertEqual(noCallback.away.projected.text, "26")

        let noBaseline = try XCTUnwrap(resolve(
            sport: Self.nfl, paired: nil, baseline: nil, score: nil,
            forecast: LivePregameComparison11296.Headline(current: compared.current, baseline: nil),
            canCompare: true))
        XCTAssertEqual(noBaseline.away.action, .plain)
        XCTAssertEqual(noBaseline.home.action, .plain)

        let noForecast = try XCTUnwrap(resolve(sport: Self.nfl, paired: nil, baseline: nil, score: nil,
                                               forecast: nil, canCompare: true))
        XCTAssertEqual(noForecast.away.action, .plain)
    }

    func testAnEarlierControlOnlyWhereTheCurrentForecastIsMissingAndTheHostGrantedIt() throws {
        // Granted for the away side only, no current forecast.
        let away = try XCTUnwrap(resolve(paired: nil, baseline: nil, score: nil, forecast: nil,
                                         canCompare: true, earlierAway: true, earlierHome: false))
        XCTAssertEqual(away.away.action, .earlier)
        XCTAssertEqual(away.home.action, .plain)
        // The missing cell is never filled from the earlier value.
        XCTAssertEqual(away.away.projected.text, "Unavailable")
        XCTAssertFalse(away.away.projected.isValue)

        // A current forecast never gets the earlier-only control.
        let present = try XCTUnwrap(resolve(
            paired: nil, baseline: nil, score: nil,
            forecast: LivePregameComparison11296.Headline(current: printed(home: 121, away: 117), baseline: nil),
            earlierAway: true, earlierHome: true))
        XCTAssertEqual(present.away.action, .plain)
        XCTAssertEqual(present.home.action, .plain)

        // Nothing granted, nothing drawn.
        let none = try XCTUnwrap(resolve(paired: nil, baseline: nil, score: nil, forecast: nil))
        XCTAssertEqual(none.away.action, .plain)
        XCTAssertEqual(none.home.action, .plain)
    }

    func testTheViewMakesNoEarlierCapabilityOfItsOwn() {
        let view = H(sportKey: Self.nfl, status: "live", paired: nil, chancePhase: .current,
                     baseline: nil, score: nil, forecast: nil,
                     awayName: "Chicago Bears", homeName: "Philadelphia Eagles",
                     awayColor: .blue, homeColor: .green, gameState: "Q3 5:47")
        XCTAssertNil(view.onEarlierAwayInspection)
        XCTAssertNil(view.onEarlierHomeInspection)
        XCTAssertNil(view.onProjectionInspection)
    }

    func testEveryControlCallsBackForItsExactSide() {
        var compared: [Bool] = []
        var earlier: [String] = []
        let compare: (Bool) -> Void = { compared.append($0) }
        let away: () -> Void = { earlier.append("away") }
        let home: () -> Void = { earlier.append("home") }

        H.perform(.compare, isHome: true, compare: compare, earlierAway: away, earlierHome: home)
        H.perform(.compare, isHome: false, compare: compare, earlierAway: away, earlierHome: home)
        XCTAssertEqual(compared, [true, false])
        XCTAssertEqual(earlier, [])

        H.perform(.earlier, isHome: true, compare: compare, earlierAway: away, earlierHome: home)
        H.perform(.earlier, isHome: false, compare: compare, earlierAway: away, earlierHome: home)
        XCTAssertEqual(earlier, ["home", "away"])
        XCTAssertEqual(compared, [true, false])

        H.perform(.plain, isHome: true, compare: compare, earlierAway: away, earlierHome: home)
        H.perform(.earlier, isHome: true, compare: compare, earlierAway: away, earlierHome: nil)
        XCTAssertEqual(earlier, ["home", "away"])
        XCTAssertEqual(compared, [true, false])
    }

    // MARK: - Speech

    func testEachTeamIsSpokenInReadingOrderAndEveryControlNamesItsTeam() throws {
        let r = try pacers()
        XCTAssertEqual(r.away.spokenSummary,
                       "Indiana Pacers. Opened chance: 56%. Current chance: 21%. Score: 91. Projected final: 117")
        let stale = try XCTUnwrap(resolve(paired: pacersPaired(), phase: .lastRecorded, baseline: nil,
                                          score: nil, forecast: nil))
        XCTAssertEqual(stale.home.spokenSummary,
                       "New Orleans Pelicans. Earlier chance: Unavailable. Current chance: No recent probability. Score: Unavailable. Projected final: Unavailable")

        let compared = try XCTUnwrap(resolve(sport: Self.nfl, paired: nil, baseline: nil, score: nil,
                                             forecast: try comparedForecast(), away: "Chicago Bears",
                                             home: "Philadelphia Eagles", canCompare: true))
        XCTAssertEqual(compared.away.actionLabel, "Compare projected finals, Chicago Bears")
        XCTAssertEqual(compared.home.actionLabel, "Compare projected finals, Philadelphia Eagles")

        let earlier = try XCTUnwrap(resolve(paired: nil, baseline: nil, score: nil, forecast: nil,
                                            earlierAway: true, earlierHome: true))
        XCTAssertEqual(earlier.away.actionLabel, "Earlier forecast, Indiana Pacers")
        XCTAssertEqual(earlier.home.actionLabel, "Earlier forecast, New Orleans Pelicans")
        XCTAssertNil(r.away.actionLabel)

        // No question or price words in the chrome.
        let chrome = r.headers + [r.away.spokenSummary, r.home.spokenSummary,
                                  compared.away.actionLabel ?? "", earlier.away.actionLabel ?? ""]
        for word in ["price", "Price", "?", "odds", "market"] {
            XCTAssertFalse(chrome.contains { $0.contains(word) }, word)
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
