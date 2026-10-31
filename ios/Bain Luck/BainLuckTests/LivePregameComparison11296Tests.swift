import XCTest
import SwiftUI
@testable import Bain_Luck

/// #11296 / #9483 — the live headline's retained pregame projected final
/// (`LivePregameComparison11296`, `EventDetailView.liveForecast11296`), in both
/// hosts: the adopted NFL/NBA row and the generic hero every other live page uses.
///
/// The first half decides the comparator's gates with constructed inputs; the
/// second decides the page's path through decoded rows, so the current pair
/// is whatever `LiveProjectedFinal2920.page` admits and the page prints.
///
/// FIXTURES: `nflObject` / `soccerObject` are the accepted in-play producer's
/// output (`a8df6e34cd`), carried verbatim from
/// `LiveProjectedFinalOnCardsAndPage2920Tests`. `baselineNFL` / `baselineSoccer`
/// have the shape of the retained producer's object (`a333d40931`,
/// `select_pregame_projection`) with CONSTRUCTED values for the same start;
/// the rows around them are CONSTRUCTED too. None of this is a real live
/// specimen, and none of it pays the composed-rendering check.
@MainActor
final class LivePregameComparison11296Tests: XCTestCase {

    private typealias C = LivePregameComparison11296
    private typealias A = LiveProjectedFinalAdmission2920

    // MARK: - Fixtures

    private static let start = "2026-10-19T20:25:00+00:00"
    private static let startDate = ISO8601DateFormatter().date(from: "2026-10-19T20:25:00Z")!
    /// 45 minutes past the start, after the in-play objects' capture.
    private static let pageNow = ISO8601DateFormatter().date(from: "2026-10-19T21:10:00Z")!

    private static let nflObject = #"""
    {"projected_home_score": 29.5, "projected_away_score": 19.0, "kind": "in_play", "boundary": "commence_time", "boundary_at": "2026-10-19T20:25:00+00:00", "earliest_confirmed_at": "2026-10-19T21:06:00+00:00", "latest_captured_at": "2026-10-19T21:06:00+00:00", "source": "sportsbooks", "basis": "consensus_spread_total", "bookmaker_count": 2, "unit": "points", "period": "full_game"}
    """#

    private static let soccerObject = #"""
    {"projected_home_score": 1.5, "projected_away_score": 1.0, "kind": "in_play", "boundary": "commence_time", "boundary_at": "2026-10-19T20:25:00+00:00", "earliest_confirmed_at": "2026-10-19T21:05:00+00:00", "latest_captured_at": "2026-10-19T21:05:00+00:00", "source": "sportsbooks", "basis": "consensus_spread_total", "bookmaker_count": 2, "unit": "goals", "period": "regulation"}
    """#

    /// Home favoured 23.5–20.5 before the start: prints 24 home, 21 away.
    private static let baselineNFL = #"""
    {"projected_home_score": 23.5, "projected_away_score": 20.5, "kind": "last_before_scheduled_start", "earliest_captured_at": "2026-10-19T18:02:00+00:00", "latest_captured_at": "2026-10-19T20:21:00+00:00", "boundary": "scheduled_start", "boundary_at": "2026-10-19T20:25:00+00:00", "source": "sportsbooks", "basis": "consensus_spread_total", "bookmaker_count": 4, "unit": "points", "period": "full_game"}
    """#

    private static let baselineSoccer = #"""
    {"projected_home_score": 1.6, "projected_away_score": 0.9, "kind": "last_before_scheduled_start", "earliest_captured_at": "2026-10-19T18:02:00+00:00", "latest_captured_at": "2026-10-19T20:21:00+00:00", "boundary": "scheduled_start", "boundary_at": "2026-10-19T20:25:00+00:00", "source": "sportsbooks", "basis": "consensus_spread_total", "bookmaker_count": 3, "unit": "goals", "period": "regulation"}
    """#

    // MARK: - Helpers

    private func decoder() -> JSONDecoder {
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        return d
    }

    private func projection(_ json: String, file: StaticString = #filePath, line: UInt = #line) throws -> PregameProjection {
        do { return try decoder().decode(PregameProjection.self, from: Data(json.utf8)) } catch {
            XCTFail("baseline did not decode: \(error)", file: file, line: line); throw error
        }
    }

    /// The baseline with each key's raw JSON value replaced.
    private func baseline(_ json: String,
                          _ edits: [(key: String, value: String)]) throws -> PregameProjection {
        var object = try XCTUnwrap(JSONSerialization.jsonObject(with: Data(json.utf8)) as? [String: Any])
        for edit in edits {
            object[edit.key] = try JSONSerialization.jsonObject(with: Data(edit.value.utf8), options: .fragmentsAllowed)
        }
        let data = try JSONSerialization.data(withJSONObject: object)
        return try decoder().decode(PregameProjection.self, from: data)
    }

    private func baseline(_ json: String, _ key: String, _ value: String) throws -> PregameProjection {
        try baseline(json, [(key, value)])
    }

    // A leading defaulted unlabeled parameter is never skipped, so the NFL
    // baseline's calls need their own overloads.
    private func baseline(_ edits: [(key: String, value: String)]) throws -> PregameProjection {
        try baseline(LivePregameComparison11296Tests.baselineNFL, edits)
    }

    private func baseline(_ key: String, _ value: String) throws -> PregameProjection {
        try baseline(LivePregameComparison11296Tests.baselineNFL, [(key, value)])
    }

    /// An admitted current pair, as `LiveProjectedFinal2920.page` hands it on.
    private func current(home: Double = 29.5, away: Double = 19.0,
                         unit: A.ScoreUnit = .points, period: A.ScorePeriod = .fullGame,
                         scheduledStart: Date = LivePregameComparison11296Tests.startDate,
                         label: String = "Projected final") -> A.Printed {
        A.Printed(
            label: label, home: Int(home.rounded()), away: Int(away.rounded()),
            admitted: A.AdmittedPair(
                home: home, away: away,
                provenance: A.Provenance(
                    bookmakerCount: 2, scheduledStart: scheduledStart,
                    earliestConfirmedAt: scheduledStart.addingTimeInterval(2460),
                    latestCapturedAt: scheduledStart.addingTimeInterval(2460),
                    unit: unit, period: period)))
    }

    private func resolve(status: String? = "live", sport: String? = "americanfootball_nfl",
                         commenceTime: String? = LivePregameComparison11296Tests.start,
                         current: A.Printed?, projection: PregameProjection?) -> C.Comparison? {
        C.resolve(status: status, sport: sport, commenceTime: commenceTime,
                  current: current, projection: projection)
    }

    /// A CONSTRUCTED detail row. `liveProjection` and `pregameProjection` are raw
    /// JSON spliced in under their served keys, or no key.
    private func rowJSON(
        sport: String = "americanfootball_nfl",
        status: String = "live",
        start: String = LivePregameComparison11296Tests.start,
        home: Int? = 14, away: Int? = 10,
        period: String? = "Q3",
        liveProjection: String?,
        pregameProjection: String?,
        finalScorePeriod: String? = nil,
        venueSettled: Bool? = nil
    ) -> String {
        var odds = #"{"home_probability": 0.80, "away_probability": 0.20, "projected_home_score": 36.9, "projected_away_score": 10.7, "bookmaker_count": 3"#
        if let liveProjection { odds += #", "live_projection": "# + liveProjection }
        odds += "}"
        let score: (Int?) -> String = { $0.map(String.init) ?? "null" }
        let espn = period.map { #"{"period": "\#($0)"}"# } ?? "null"
        var extra = ""
        if let pregameProjection { extra += #", "pregame_projection": "# + pregameProjection }
        if let finalScorePeriod { extra += #", "final_score_period": "\#(finalScorePeriod)""# }
        if let venueSettled { extra += #", "venue_settled": \#(venueSettled)"# }
        return #"""
        {"id": 14870008, "sport": "\#(sport)", "home_team": "Georgia Bulldogs", "away_team": "Oklahoma Sooners", "commence_time": "\#(start)", "start_is_tbd": false, "start_is_from_schedule": true, "status": "\#(status)", "home_score": \#(score(home)), "away_score": \#(score(away)), "current_odds": \#(odds), "espn": \#(espn)\#(extra)}
        """#
    }

    private func detail(_ json: String, file: StaticString = #filePath, line: UInt = #line) throws -> EventDetail {
        do { return try decoder().decode(EventDetail.self, from: Data(json.utf8)) } catch {
            XCTFail("row did not decode: \(error)", file: file, line: line); throw error
        }
    }

    /// The headline forecast for a row, with the page's own `hasScore`.
    private func forecast(_ e: EventDetail, ladder: (home: Double, away: Double)? = nil) -> C.Headline? {
        EventDetailView.liveForecast11296(
            e, ladderHome: ladder?.home, ladderAway: ladder?.away,
            hasScore: EventDetailView.showsScore(status: e.status, away: e.awayScore, home: e.homeScore),
            now: Self.pageNow)
    }

    /// What the page prints for a row: its current slot and the baseline under it.
    private func page(_ json: String, ladder: (home: Double, away: Double)? = nil,
                      file: StaticString = #filePath, line: UInt = #line)
        throws -> (current: String?, baseline: C.Comparison?) {
        let e = try detail(json, file: file, line: line)
        let hasScore = EventDetailView.showsScore(status: e.status, away: e.awayScore, home: e.homeScore)
        return (
            EventDetailView.projectionText(e, ladderHome: ladder?.home, ladderAway: ladder?.away,
                                           hasScore: hasScore, now: Self.pageNow),
            forecast(e, ladder: ladder)?.baseline)
    }

    // MARK: - Comparator: the compatible pair

    func testACompatiblePairPrintsTheBaselineKeyedAndRoundedLikeTheCards() throws {
        let c = try XCTUnwrap(resolve(current: current(), projection: projection(Self.baselineNFL)))
        XCTAssertEqual(c.label, "Projection before scheduled start", "the final line's own words")
        XCTAssertEqual(c.home, 24, "23.5 rounds half away from zero, as the cards round it")
        XCTAssertEqual(c.away, 21, "20.5 rounds half away from zero")
        XCTAssertEqual(c.bookmakerCount, 4)
        XCTAssertEqual(c.scheduledStart, Self.startDate)
        XCTAssertLessThan(c.latestCapturedAt, c.scheduledStart)
        // Keyed, never sorted: swap the served halves and the sides swap with them.
        let swapped = try baseline([("projected_home_score", "20.5"), ("projected_away_score", "23.5")])
        let s = try XCTUnwrap(resolve(current: current(), projection: swapped))
        XCTAssertEqual([s.home, s.away], [21, 24], "home and away stay in their own places")
    }

    func testAnEqualPairIsHonestAndPrints() throws {
        // A line quoted before the start and confirmed unchanged after it.
        let equal = try baseline([("projected_home_score", "29.5"), ("projected_away_score", "19.0")])
        let c = try XCTUnwrap(resolve(current: current(), projection: equal))
        XCTAssertEqual([c.home, c.away], [30, 19])
        XCTAssertEqual([c.home, c.away], [current().home, current().away], "no movement is required")
    }

    func testABaselineBelowTodaysActualScoreStillPrints() throws {
        // 31–14 to the home side now; the pregame 24–21 sits under both halves'
        // actual score (21 > 14 is fine; 24 < 31 is history, not a defect).
        let e = try detail(rowJSON(home: 31, away: 14,
                                   liveProjection: #"{"projected_home_score": 38.5, "projected_away_score": 17.0, "kind": "in_play", "boundary": "commence_time", "boundary_at": "2026-10-19T20:25:00+00:00", "earliest_confirmed_at": "2026-10-19T21:06:00+00:00", "latest_captured_at": "2026-10-19T21:06:00+00:00", "source": "sportsbooks", "basis": "consensus_spread_total", "bookmaker_count": 2, "unit": "points", "period": "full_game"}"#,
                                   pregameProjection: Self.baselineNFL))
        let c = try XCTUnwrap(forecast(e)?.baseline)
        XCTAssertLessThan(c.home, try XCTUnwrap(e.homeScore), "anti-vacuity: the baseline really is below the score")
        XCTAssertEqual([c.home, c.away], [24, 21])
    }

    // MARK: - Comparator: refusals

    func testWithNoCurrentPairOrNoBaselineNothingIsCompared() throws {
        XCTAssertNotNil(resolve(current: current(), projection: try projection(Self.baselineNFL)), "positive control")
        XCTAssertNil(resolve(current: nil, projection: try projection(Self.baselineNFL)), "no admitted current pair")
        XCTAssertNil(resolve(current: current(), projection: nil), "no baseline served")
        XCTAssertNil(resolve(current: current(), projection: try projection("{}")), "an empty object")
        XCTAssertNil(resolve(current: current(), projection: try projection(#"{"kind": 3}"#)), "a malformed object")
    }

    func testOnlyALiveRowCompares() throws {
        let p = try projection(Self.baselineNFL)
        XCTAssertNotNil(resolve(current: current(), projection: p), "positive control")
        for status in ["completed", "closed", "scheduled", "suspended", "postponed", "LIVE", ""] {
            XCTAssertNil(resolve(status: status, current: current(), projection: p), status)
        }
        XCTAssertNil(resolve(status: nil, current: current(), projection: p))
    }

    func testTheBaselinesLabelsMustBeTheOnesItsWordsDescribe() throws {
        XCTAssertNotNil(resolve(current: current(), projection: try projection(Self.baselineNFL)), "positive control")
        for (key, value) in [
            ("kind", #""latest_before_play""#), ("kind", #""opening""#), ("kind", #""in_play""#),
            ("boundary", #""commence_time""#), ("boundary", #""observed_start""#),
            ("source", #""kalshi""#), ("basis", #""moneyline""#),
        ] {
            XCTAssertNil(resolve(current: current(), projection: try baseline(key, value)), "\(key)=\(value)")
        }
    }

    func testAWrongUnitOrPeriodRefuses() throws {
        XCTAssertNil(resolve(current: current(), projection: try baseline("unit", #""goals""#)), "baseline unit")
        XCTAssertNil(resolve(current: current(), projection: try baseline("period", #""regulation""#)), "baseline period")
        // The current pair's own unit or period disagreeing with the baseline's.
        XCTAssertNil(resolve(current: current(unit: .goals), projection: try projection(Self.baselineNFL)), "current unit")
        XCTAssertNil(resolve(current: current(period: .regulation), projection: try projection(Self.baselineNFL)),
                     "current period")
        // Never inferred from the sport: a soccer baseline served as full game refuses.
        let soccerFullGame = try baseline(Self.baselineSoccer, "period", #""full_game""#)
        XCTAssertNil(resolve(sport: "soccer_epl",
                             current: current(home: 1.5, away: 1.0, unit: .goals, period: .regulation),
                             projection: soccerFullGame))
        // Unsupported sports stay unsupported.
        for sport in ["icehockey_nhl", "baseball_mlb", "tennis_atp_us_open", "mma_mixed_martial_arts", "", nil] as [String?] {
            XCTAssertNil(resolve(sport: sport, current: current(), projection: try projection(Self.baselineNFL)),
                         sport ?? "nil")
        }
    }

    func testTheBoundaryMustBeThisRowsStartAndTheCurrentPairs() throws {
        let p = try projection(Self.baselineNFL)
        XCTAssertNotNil(resolve(current: current(), projection: p), "positive control")
        // The same instant written another way still matches.
        XCTAssertNotNil(resolve(commenceTime: "2026-10-19T20:25:00Z", current: current(), projection: p))
        // The row's start moved later: the baseline was read before an old start.
        XCTAssertNil(resolve(commenceTime: "2026-10-19T20:40:00+00:00",
                             current: current(scheduledStart: Self.startDate.addingTimeInterval(900)),
                             projection: p), "row start moved")
        // The row and the baseline agree, but the current pair was measured from another start.
        XCTAssertNil(resolve(current: current(scheduledStart: Self.startDate.addingTimeInterval(60)), projection: p),
                     "current pair's start differs")
        // The baseline's boundary drifted by a minute either way.
        for drifted in ["2026-10-19T20:24:00+00:00", "2026-10-19T20:26:00+00:00"] {
            XCTAssertNil(resolve(current: current(), projection: try baseline("boundary_at", "\"\(drifted)\"")), drifted)
        }
        XCTAssertNil(resolve(commenceTime: nil, current: current(), projection: p), "no row start")
        XCTAssertNil(resolve(commenceTime: "soon", current: current(), projection: p), "unreadable row start")
    }

    func testTheBaselineMustBeCapturedStrictlyBeforeTheStart() throws {
        XCTAssertNil(resolve(current: current(), projection: try baseline("latest_captured_at", #""2026-10-19T20:25:00+00:00""#)),
                     "captured AT the start")
        XCTAssertNil(resolve(current: current(), projection: try baseline("latest_captured_at", #""2026-10-19T20:31:00+00:00""#)),
                     "captured after the start")
        XCTAssertNil(resolve(current: current(), projection: try baseline("earliest_captured_at", #""2026-10-19T20:22:00+00:00""#)),
                     "earliest after latest")
        XCTAssertNotNil(resolve(current: current(), projection: try baseline("earliest_captured_at", #""2026-10-19T20:21:00+00:00""#)),
                        "earliest equal to latest is one reading")
        for key in ["earliest_captured_at", "latest_captured_at", "boundary_at"] {
            XCTAssertNil(resolve(current: current(), projection: try baseline(key, #""yesterday""#)), "\(key) unreadable")
            XCTAssertNil(resolve(current: current(), projection: try baseline(key, "null")), "\(key) null")
        }
    }

    func testAMalformedCountOrPairRefusesWithoutTrapping() throws {
        for count in ["0", "-1", "2.5", "null", #""4""#, "1e19"] {
            XCTAssertNil(resolve(current: current(), projection: try baseline("bookmaker_count", count)), "count \(count)")
        }
        for (key, value) in [("projected_home_score", "0"), ("projected_away_score", "-3"),
                             ("projected_home_score", "null"), ("projected_away_score", #""21""#),
                             ("projected_home_score", "1e300")] {
            XCTAssertNil(resolve(current: current(), projection: try baseline(key, value)), "\(key)=\(value)")
        }
        var p = try projection(Self.baselineNFL)
        p = PregameProjection(projectedHomeScore: .infinity, projectedAwayScore: p.projectedAwayScore,
                              kind: p.kind, earliestCapturedAt: p.earliestCapturedAt,
                              latestCapturedAt: p.latestCapturedAt, boundary: p.boundary,
                              boundaryAt: p.boundaryAt, source: p.source, basis: p.basis,
                              bookmakerCount: p.bookmakerCount, unit: p.unit, period: p.period)
        XCTAssertNil(resolve(current: current(), projection: p), "an infinite half")
    }

    func testALevelPairPrintsOnlyWhereTheSportCanEndLevel() throws {
        let nflLevel = try baseline([("projected_home_score", "20.6"), ("projected_away_score", "20.6")])
        XCTAssertNotNil(resolve(current: current(), projection: nflLevel), "the NFL can end level, as the final line allows")
        let nba = try baseline([("projected_home_score", "110.6"), ("projected_away_score", "110.6")])
        XCTAssertNil(resolve(sport: "basketball_nba", current: current(home: 112.5, away: 101.0), projection: nba),
                     "basketball cannot end level")
    }

    // MARK: - The page path

    func testThePagePrintsTheBaselineOnlyBesideTheAdmittedPairItPrints() throws {
        let both = try page(rowJSON(liveProjection: Self.nflObject, pregameProjection: Self.baselineNFL))
        XCTAssertEqual(both.current, "Proj. 19-30", "the current pair the page prints")
        let c = try XCTUnwrap(both.baseline)
        XCTAssertEqual([c.away, c.home], [21, 24])
    }

    func testARefusedOrAbsentCurrentObjectAddsNoBaseline() throws {
        let ladder = (home: 27.2, away: 20.4)
        // Served and refused: the page prints nothing, so nothing sits under it.
        let refused = try page(rowJSON(liveProjection: "{}", pregameProjection: Self.baselineNFL), ladder: ladder)
        XCTAssertNil(refused.current, "anti-vacuity: the refused object prints nothing")
        XCTAssertNil(refused.baseline)
        // Not served: the page prints the ladders' untyped pair, which names no
        // unit or period, so the baseline does not attach to it.
        let untyped = try page(rowJSON(liveProjection: nil, pregameProjection: Self.baselineNFL), ladder: ladder)
        XCTAssertEqual(untyped.current, "Proj. 20-27", "anti-vacuity: the ladders' pair prints")
        XCTAssertNil(untyped.baseline, "an untyped current pair never acquires a comparison")
    }

    func testARefusedBaselineNeverRemovesTheCurrentForecast() throws {
        for bad in [nil, "{}", #"{"kind": "opening"}"#, Self.baselineSoccer] as [String?] {
            let shown = try page(rowJSON(liveProjection: Self.nflObject, pregameProjection: bad))
            XCTAssertEqual(shown.current, "Proj. 19-30", bad ?? "absent")
            XCTAssertNil(shown.baseline, bad ?? "absent")
        }
    }

    func testAPairThePageWithholdsCarriesNoBaseline() throws {
        // The current pair is below the printed score on the away side, so the
        // page withholds it — and the baseline goes with it.
        let shown = try page(rowJSON(home: 14, away: 24, liveProjection: Self.nflObject,
                                     pregameProjection: Self.baselineNFL))
        XCTAssertNil(shown.current, "anti-vacuity: the page withholds the current pair")
        XCTAssertNil(shown.baseline)
        // No score printed yet: #5697 withholds the projection, and the baseline too.
        let scoreless = try page(rowJSON(home: nil, away: nil, liveProjection: Self.nflObject,
                                         pregameProjection: Self.baselineNFL))
        XCTAssertNil(scoreless.current)
        XCTAssertNil(scoreless.baseline)
    }

    func testSoccerComparesOnlyWhileRegulationIsBeingPlayed() throws {
        let regulation = try page(rowJSON(sport: "soccer_epl", home: 1, away: 0, period: "67'",
                                          liveProjection: Self.soccerObject, pregameProjection: Self.baselineSoccer))
        XCTAssertEqual(regulation.current, "Proj. 1-2 (90 min)", "the current figure keeps its 90-minute basis")
        let c = try XCTUnwrap(regulation.baseline)
        XCTAssertEqual(c.label, "Projection (90 min) before scheduled start", "and so does the baseline's label")
        XCTAssertEqual([c.away, c.home], [1, 2])
        // Extra time, a shootout, or a phase nobody can read: no current pair, no comparison.
        for period in ["ET", "105'", "Pen.", "", "FT"] {
            let shown = try page(rowJSON(sport: "soccer_epl", home: 1, away: 1, period: period,
                                         liveProjection: Self.soccerObject, pregameProjection: Self.baselineSoccer))
            XCTAssertNil(shown.current, period)
            XCTAssertNil(shown.baseline, "\(period): the 90-minute baseline never sits beside it")
        }
    }

    func testTheFinishedPathIsUnchanged() throws {
        // A final carrying the same baseline: the final line answers, the live one does not.
        let final = try detail(rowJSON(status: "completed", home: 27, away: 20, period: "Final",
                                       liveProjection: Self.nflObject, pregameProjection: Self.baselineNFL))
        let line = try XCTUnwrap(EventDetailView.finalForecast11296(final))
        XCTAssertEqual(line, FinalForecastComparison11296.Comparison(
            label: "Projection before scheduled start", away: 21, home: 24, bookmakerCount: 4))
        XCTAssertNil(forecast(final))
        // And a live row never reaches the final line.
        let live = try detail(rowJSON(liveProjection: Self.nflObject, pregameProjection: Self.baselineNFL))
        XCTAssertNil(EventDetailView.finalForecast11296(live))
    }

    // MARK: - The generic host: pages the paired headline does not adopt

    func testALiveSoccerPageIsNotAdoptedAndItsHeadlineCarriesBothForecasts() throws {
        // The host: neither adoption rule takes a live soccer page, so the
        // generic hero is the headline that prints this.
        XCTAssertFalse(NFLRecognizablePage9483.applies(sportKey: "soccer_epl"))
        XCTAssertFalse(MLBFinalPage11284.adoptsPairedPage(sportKey: "soccer_epl", status: "live"))
        let e = try detail(rowJSON(sport: "soccer_epl", home: 1, away: 0, period: "67'",
                                   liveProjection: Self.soccerObject, pregameProjection: Self.baselineSoccer))
        let h = try XCTUnwrap(forecast(e))
        XCTAssertEqual(h.current.label, "Projected final (90 min)", "the current pair keeps its 90-minute basis")
        XCTAssertEqual([h.current.away, h.current.home], [1, 2])
        let b = try XCTUnwrap(h.baseline)
        XCTAssertEqual(b.label, "Projection (90 min) before scheduled start")
        XCTAssertEqual([b.away, b.home], [1, 2], "equal pairs are honest")
        XCTAssertEqual(C.spokenText(h, awayName: "Oklahoma Sooners", homeName: "Georgia Bulldogs"),
                       "Projected final (90 min): Oklahoma Sooners 1, Georgia Bulldogs 2. "
                       + "Projection (90 min) before scheduled start: Oklahoma Sooners 1, Georgia Bulldogs 2")
    }

    func testALiveCollegeFootballPageIsNotAdoptedAndItsHeadlineCarriesBothForecasts() throws {
        XCTAssertFalse(NFLRecognizablePage9483.applies(sportKey: "americanfootball_ncaaf"))
        XCTAssertFalse(MLBFinalPage11284.adoptsPairedPage(sportKey: "americanfootball_ncaaf", status: "live"))
        let e = try detail(rowJSON(sport: "americanfootball_ncaaf",
                                   liveProjection: Self.nflObject, pregameProjection: Self.baselineNFL))
        let h = try XCTUnwrap(forecast(e))
        XCTAssertEqual(h.current.label, "Projected final")
        XCTAssertEqual([h.current.away, h.current.home], [19, 30])
        XCTAssertEqual(h.baseline.map { [$0.away, $0.home] }, [21, 24])
    }

    func testTheCurrentForecastStaysInTheHeadlineWithoutABaseline() throws {
        for bad in [nil, "{}", Self.baselineSoccer] as [String?] {
            let e = try detail(rowJSON(sport: "americanfootball_ncaaf",
                                       liveProjection: Self.nflObject, pregameProjection: bad))
            let h = try XCTUnwrap(forecast(e), bad ?? "absent")
            XCTAssertEqual([h.current.away, h.current.home], [19, 30], bad ?? "absent")
            XCTAssertNil(h.baseline, bad ?? "absent")
            XCTAssertEqual(C.spokenText(h, awayName: "A", homeName: "H"), "Projected final: A 19, H 30")
        }
    }

    /// The one live hero arm that mounts no information control is the
    /// venue-settled verdict (the finished arm needs a finished status; the
    /// priced arm always mounts it, a live quote is never an opening line; the
    /// `vs` arm mounts it whenever the status is live). A forecast printed under
    /// that verdict would have details nobody can open — and it cannot print,
    /// because the two need opposite rows: the live forecast needs a score,
    /// twice over (admission withholds `.noActualScore`; `showsProjection`
    /// needs `hasScore` once underway, both scores present), and the
    /// producer serves `venue_settled` only on a row with NO score
    /// (`venue_settlement_is_askable`'s first test, pinned for a live row by
    /// `test_venue_settled_payload_6381.py::…scored_live_row…`). The client
    /// never adds a score to a served row that had none
    /// (`LiveEventScoreReconciliation` keeps a held score only over a polled one).
    func testAVenueSettledLiveRowCarriesNoForecastSoTheArmWithoutTheControlHidesNone() throws {
        let settled = try detail(rowJSON(sport: "americanfootball_ncaaf", home: nil, away: nil,
                                         liveProjection: Self.nflObject, pregameProjection: Self.baselineNFL,
                                         venueSettled: true))
        XCTAssertTrue(EventState.showsVenueSettledVerdict(
            settled.status, venueSettled: settled.venueSettled,
            commenceTime: settled.commenceTime?.asDate, now: Self.pageNow),
            "control: this row takes the verdict arm")
        XCTAssertEqual(LiveProjectedFinal2920.page(settled, now: Self.pageNow), .withheld,
                       "no actual score: the in-play object is withheld")
        XCTAssertNil(forecast(settled), "no score, no live forecast — the verdict arm prints none")

        // The score is the whole difference: the same row scored prints both forecasts.
        let scored = try detail(rowJSON(sport: "americanfootball_ncaaf",
                                        liveProjection: Self.nflObject, pregameProjection: Self.baselineNFL,
                                        venueSettled: true))
        guard case .admitted = LiveProjectedFinal2920.page(scored, now: Self.pageNow) else {
            return XCTFail("control: the same object is admitted once the row is scored")
        }
        let h = try XCTUnwrap(forecast(scored), "control: the fixture is admissible once scored")
        XCTAssertNotNil(h.baseline)

        // The hero's gate is the page's own score test, not a constant.
        let page = try source("Views/EventDetailView.swift")
        let hero = try XCTUnwrap(page.range(of: "privatefuncheroSection(_event:EventDetail)->someView{"))
        XCTAssertTrue(page[hero.upperBound...].hasPrefix(
            "letcolors=teamColors(event)lethasScore=EventDetailView.showsScore(status:event.status,away:event.awayScore,home:event.homeScore)"))
    }

    func testAnUntypedOrRefusedCurrentPairIsNotTakenIntoTheHeadline() throws {
        let ladder = (home: 27.2, away: 20.4)
        // The ladders' untyped pair keeps printing where it prints today (Game Info).
        let untyped = try detail(rowJSON(sport: "americanfootball_ncaaf", liveProjection: nil,
                                         pregameProjection: Self.baselineNFL))
        XCTAssertNotNil(EventDetailView.projectionText(untyped, ladderHome: ladder.home, ladderAway: ladder.away,
                                                       hasScore: true, now: Self.pageNow), "anti-vacuity")
        XCTAssertNil(forecast(untyped, ladder: ladder))
        let refused = try detail(rowJSON(sport: "americanfootball_ncaaf", liveProjection: "{}",
                                         pregameProjection: Self.baselineNFL))
        XCTAssertNil(forecast(refused, ladder: ladder))
        // Extra time: no current pair in any host.
        let et = try detail(rowJSON(sport: "soccer_epl", home: 1, away: 1, period: "ET",
                                    liveProjection: Self.soccerObject, pregameProjection: Self.baselineSoccer))
        XCTAssertNil(forecast(et))
    }

    // MARK: - Words

    func testTheGroupSpeaksBothPairsAndNamesBothTeams() throws {
        let c = try XCTUnwrap(resolve(current: current(), projection: try projection(Self.baselineNFL)))
        XCTAssertEqual(
            EventDetailView.projectionWithBaselineAccessibilityLabel11296(
                figure: "19-30", names: ("Oklahoma", "Georgia"), baseline: c),
            "Projected final, Oklahoma 19, Georgia 30. Projection before scheduled start: Oklahoma 21, Georgia 24")
        XCTAssertEqual(
            EventDetailView.projectionWithBaselineAccessibilityLabel11296(
                figure: "19-30", names: ("Oklahoma", "Georgia"), baseline: nil),
            EventDetailView.projectionAccessibilityLabel9483(figure: "19-30", names: ("Oklahoma", "Georgia")),
            "with no baseline the spoken label is exactly today's")
        XCTAssertEqual(C.pairText(c, awayName: "Oklahoma", homeName: "Georgia"),
                       "Oklahoma\u{00A0}21 · Georgia\u{00A0}24", "away first, as the current figure reads")
    }

    // MARK: - Where each forecast came from (the existing information popover)

    private typealias D = LiveForecastDetails11296

    /// A reader in Pacific time with US English, so the clocks are fixed.
    private static let pacific: Calendar = {
        var c = Calendar(identifier: .gregorian)
        c.timeZone = TimeZone(identifier: "America/Los_Angeles")!
        return c
    }()
    private static let usEnglish = Locale(identifier: "en_US")

    private func details(_ h: C.Headline, calendar: Calendar = LivePregameComparison11296Tests.pacific) -> [D.Section] {
        D.sections(h, calendar: calendar, locale: Self.usEnglish)
    }

    func testTheDetailsCarryEachForecastsOwnCountAndClocks() throws {
        // The current object's newest capture (19:40Z, 12:40 PM PT) precedes the
        // start: an unchanged quote reconfirmed after it. Admitted, never printed.
        let object = Self.nflObject.replacingOccurrences(
            of: #""latest_captured_at": "2026-10-19T21:06:00+00:00""#,
            with: #""latest_captured_at": "2026-10-19T19:40:00+00:00""#)
        XCTAssertNotEqual(object, Self.nflObject, "anti-vacuity: the capture moved")
        let e = try detail(rowJSON(liveProjection: object, pregameProjection: Self.baselineNFL))
        let h = try XCTUnwrap(forecast(e))
        let sections = details(h)
        XCTAssertEqual(sections.map(\.title), ["Projected final", "Projection before scheduled start"])

        let now = try XCTUnwrap(sections.first)
        guard now.lines.count == 2 else { return XCTFail("count and earliest confirmation only: \(now.lines)") }
        XCTAssertEqual(now.lines.first, "From 2 sportsbooks", "the current object's own count, not the baseline's")
        XCTAssertTrue(now.lines[1].hasPrefix("Oldest confirmation Oct 19"), now.lines[1])
        XCTAssertTrue(now.lines[1].contains("2:06"), "21:06Z, the oldest contributing confirmation: \(now.lines[1])")
        XCTAssertFalse(now.lines.joined().contains("12:40"), "the latest capture is not an update time")
        XCTAssertFalse(now.lines.joined().contains("1:25"), "the scheduled start is not a confirmation")

        let before = try XCTUnwrap(sections.last)
        guard sections.count == 2, before.lines.count == 3 else {
            return XCTFail("count, recorded range, scheduled start: \(before.lines)")
        }
        XCTAssertEqual(before.lines[0], "From 4 sportsbooks", "the baseline's own count reaches the details")
        XCTAssertTrue(before.lines[1].hasPrefix("Lines recorded Oct 19"), before.lines[1])
        XCTAssertTrue(before.lines[1].contains("11:02") && before.lines[1].contains("1:21")
                      && before.lines[1].contains(" – "), "18:02Z to 20:21Z, local: \(before.lines[1])")
        XCTAssertEqual(before.lines[1].components(separatedBy: "Oct").count - 1, 1, "one local day, its date once")
        XCTAssertTrue(before.lines[2].hasPrefix("Scheduled start Oct 19"), before.lines[2])
        XCTAssertTrue(before.lines[2].contains("1:25"), "20:25Z, the listed start: \(before.lines[2])")
    }

    func testWithNoBaselineTheDetailsReconstructNothing() throws {
        for bad in [nil, "{}", Self.baselineSoccer] as [String?] {
            let e = try detail(rowJSON(liveProjection: Self.nflObject, pregameProjection: bad))
            let h = try XCTUnwrap(forecast(e), bad ?? "absent")
            let sections = details(h)
            XCTAssertEqual(sections.map(\.title), ["Projected final"], bad ?? "absent")
            let lines = sections.flatMap(\.lines)
            XCTAssertFalse(lines.contains { $0.hasPrefix("Lines recorded") || $0.hasPrefix("Scheduled start") },
                           "no baseline, no baseline facts: \(lines)")
        }
        // No admitted pair, no forecast: the popover keeps only delivery and confidence.
        let refused = try detail(rowJSON(liveProjection: nil, pregameProjection: Self.baselineNFL))
        XCTAssertNil(forecast(refused))
    }

    func testSoccerDetailsKeepTheNinetyMinuteBasis() throws {
        let e = try detail(rowJSON(sport: "soccer_epl", home: 1, away: 0, period: "67'",
                                   liveProjection: Self.soccerObject, pregameProjection: Self.baselineSoccer))
        let h = try XCTUnwrap(forecast(e))
        XCTAssertEqual(details(h).map(\.title),
                       ["Projected final (90 min)", "Projection (90 min) before scheduled start"])
        XCTAssertEqual(details(h).last?.lines.first, "From 3 sportsbooks")
        XCTAssertEqual(h.current.admitted.provenance.period, .regulation)
        let basis = D.basis(h.current.admitted.provenance.period)
        XCTAssertTrue(basis.contains("spread and total") && basis.contains("90 minutes") && basis.contains("not extra time"), basis)
        let nfl = D.basis(.fullGame)
        XCTAssertTrue(nfl.contains("spread and total") && nfl.contains("full game") && nfl.contains("overtime included"), nfl)
    }

    func testTheRecordedRangeIsLocalAndDatesOnlyWhenTheDayChanges() throws {
        let iso = ISO8601DateFormatter()
        let lateNight = try XCTUnwrap(iso.date(from: "2026-10-19T06:30:00Z"))   // Oct 18, 11:30 PM PT
        let pastMidnight = try XCTUnwrap(iso.date(from: "2026-10-19T07:30:00Z")) // Oct 19, 12:30 AM PT
        let pacific = D.recordedRange(lateNight, pastMidnight, calendar: Self.pacific, locale: Self.usEnglish)
        XCTAssertTrue(pacific.contains("Oct 18") && pacific.contains("Oct 19"), pacific)
        var eastern = Calendar(identifier: .gregorian)
        eastern.timeZone = try XCTUnwrap(TimeZone(identifier: "America/New_York"))
        let sameDay = D.recordedRange(lateNight, pastMidnight, calendar: eastern, locale: Self.usEnglish)
        XCTAssertEqual(sameDay.components(separatedBy: "Oct").count - 1, 1, "one local day in New York: \(sameDay)")
        XCTAssertFalse(D.recordedRange(lateNight, lateNight, calendar: Self.pacific, locale: Self.usEnglish).contains("–"),
                       "one instant prints once")
        XCTAssertEqual(D.from(1), "From 1 sportsbook")
    }

    func testTheDetailsUseNoDeliveryWords() throws {
        let e = try detail(rowJSON(liveProjection: Self.nflObject, pregameProjection: Self.baselineNFL))
        let h = try XCTUnwrap(forecast(e))
        let text = details(h).flatMap { [$0.title] + $0.lines } + [D.basis(.fullGame), D.basis(.regulation)]
        for line in text {
            for word in ["eceived", "update", "published", "bookmaker", "books "] {
                XCTAssertFalse(line.contains(word), "'\(word)' in: \(line)")
            }
        }
    }

    // MARK: - Wiring (source guards)

    private func source(_ path: String) throws -> String {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()   // BainLuckTests
            .deletingLastPathComponent()   // Bain Luck (project dir)
            .appendingPathComponent("Bain Luck")
            .appendingPathComponent(path)
        let text = try String(contentsOf: url, encoding: .utf8)
        return text.split(separator: "\n", omittingEmptySubsequences: false)
            .map { line -> String in
                guard let slashes = line.range(of: "//") else { return String(line) }
                return String(line[line.startIndex..<slashes.lowerBound])
            }
            .joined(separator: "\n")
            .filter { !$0.isWhitespace }
    }

    private func occurrences(_ needle: String, in haystack: String) -> Int {
        haystack.components(separatedBy: needle).count - 1
    }

    func testTheBaselineSitsInsideTheCurrentProjectionGroupWithTheRightNames() throws {
        let page = try source("Views/EventDetailView.swift")
        let mount = "LivePregameBaselineLine11296(comparison:liveBaseline,awayName:names.away,homeName:names.home,font:.caption2)"
        XCTAssertEqual(occurrences("LivePregameBaselineLine11296(", in: page), 1, "drawn once")
        XCTAssertEqual(occurrences(mount, in: page), 1, "each name beside its own number")
        // Inside the scored arm's figure-over-caption group: after the figure and
        // its caption, before the group closes into one spoken element.
        let figure = try XCTUnwrap(page.range(of: "Text(figure).font(.system(size:eventHeadlineScoreSize9483"))
        let caption = try XCTUnwrap(page.range(of: ".dynamicTypeSize(...Self.nflPairedCaptionTypeCeiling)",
                                               range: figure.upperBound..<page.endIndex))
        let line = try XCTUnwrap(page.range(of: mount))
        let close = try XCTUnwrap(page.range(of: "}.accessibilityElement(children:.ignore).accessibilityLabel(Self.projectionWithBaselineAccessibilityLabel11296(figure:figure,names:names,baseline:liveBaseline))",
                                             range: caption.upperBound..<page.endIndex))
        XCTAssertTrue(caption.upperBound < line.lowerBound && line.upperBound < close.lowerBound,
                      "the baseline left the current projection's group")
        XCTAssertFalse(page[caption.upperBound..<line.lowerBound].contains("resultLayout"), "never a third column")
        XCTAssertTrue(page.contains("letliveBaseline=liveForecast11296(event,hasScore:hasScore)?.baseline"))
        XCTAssertEqual(occurrences("LivePregameComparison11296.resolve(", in: page), 1)
        XCTAssertEqual(occurrences("liveProjection", in: page), 0, "the page never reads the object's fields itself")
    }

    func testTheGenericHeroPrintsTheLiveForecastAndGameInfoStopsRepeatingIt() throws {
        let page = try source("Views/EventDetailView.swift")
        let mount = "ifletliveForecast=genericLiveForecast11296(event,hasScore:hasScore){LiveHeadlineForecast11296(forecast:liveForecast,awayName:event.awayTeam,homeName:event.homeTeam)}"
        XCTAssertEqual(occurrences("LiveHeadlineForecast11296(", in: page), 1, "drawn once")
        XCTAssertEqual(occurrences(mount, in: page), 1, "each name beside its own number")
        // In the hero, after its arms (the final line's slot), before its padding.
        let hero = try XCTUnwrap(page.range(of: "privatefuncheroSection(_event:EventDetail)->someView{"))
        let arms = try XCTUnwrap(page.range(of: "ifletpaired=nflPairedHeadline(event,hasScore:hasScore){", range: hero.upperBound..<page.endIndex))
        let final = try XCTUnwrap(page.range(of: "ifletfinalForecast=Self.finalForecast11296(event){"))
        let line = try XCTUnwrap(page.range(of: mount))
        let heroEnd = try XCTUnwrap(page.range(of: ".padding(approvedPair?.horizontal:.all)", range: hero.upperBound..<page.endIndex))
        XCTAssertTrue(arms.upperBound < final.lowerBound && final.upperBound < line.lowerBound && line.upperBound < heroEnd.lowerBound,
                      "the live forecast left the hero's shared slot under the arms")
        // Only where the paired headline does not print its own.
        let body = try XCTUnwrap(page.range(of: "privatefuncgenericLiveForecast11296(_event:EventDetail,hasScore:Bool)->LivePregameComparison11296.Headline?{"))
        XCTAssertTrue(page[body.upperBound...].hasPrefix(
            "guardnflPairedHeadline(event,hasScore:hasScore)==nilelse{returnnil}returnliveForecast11296(event,hasScore:hasScore)}"))
        // Game Info drops its copy exactly when the hero printed it, by the same call.
        XCTAssertTrue(page.contains("letheroLiveForecast=genericLiveForecast11296(event,hasScore:gameInfoHasScore)!=nil"))
        XCTAssertTrue(page.contains("nflHeadline||heroLiveForecast?nil:projectionText(event,hasScore:gameInfoHasScore).map{(\"chart.line.uptrend.xyaxis\",$0)}"))
    }

    func testTheGenericHeadlineLeadsWithTheCurrentLabelAndNamesEachTeam() throws {
        let helper = try source("Utilities/LivePregameComparison11296.swift")
        let start = try XCTUnwrap(helper.range(of: "structLiveHeadlineForecast11296:View{"))
        let view = String(helper[start.upperBound...])
        let label = try XCTUnwrap(view.range(of: "Text(forecast.current.label)"))
        let pair = try XCTUnwrap(view.range(of: "Text(LiveProjectedFinal2920.pairText(forecast.current,awayName:awayName,homeName:homeName))"))
        let baseline = try XCTUnwrap(view.range(of: "LivePregameBaselineLine11296(comparison:baseline,awayName:awayName,homeName:homeName)"))
        XCTAssertTrue(label.upperBound < pair.lowerBound && pair.upperBound < baseline.lowerBound,
                      "current label, current pair, then the retained pair beneath")
        XCTAssertFalse(view.contains("minimumScaleFactor"), "wraps, never shrinks")
        XCTAssertFalse(view.contains("lineLimit"), "wraps, never truncates")
        XCTAssertEqual(occurrences("awayName:homeName", in: helper), 0, "no name handed to the other side")
        XCTAssertEqual(occurrences("homeName:awayName", in: helper), 0, "no name handed to the other side")
    }

    func testTheComparatorReadsTheAdmittedPairAndNeverTheFinalResolver() throws {
        let helper = try source("Utilities/LivePregameComparison11296.swift")
        XCTAssertTrue(helper.contains("enumLivePregameComparison11296{"), "anti-vacuity")
        XCTAssertTrue(helper.contains("letnow=current.admitted.provenance"))
        XCTAssertFalse(helper.contains("FinalForecastComparison11296.resolve("), "the final resolver stays final-only")
        XCTAssertFalse(helper.contains("liveProjection"), "only the admitted pair, never the raw object")
        XCTAssertFalse(helper.contains("projectedHomeScore:"), "no score is manufactured")
        XCTAssertFalse(helper.contains("hasPrefix"), "no period read from the sport's name here")
        XCTAssertFalse(helper.contains("homeScore"), "the actual score does not bound a pregame forecast")
    }

    func testTheInformationPopoverDescribesTheForecastTheHeadlinePrints() throws {
        let page = try source("Views/EventDetailView.swift")
        // The page's one existing information surface gains the forecast; no new
        // control, no second popover.
        XCTAssertEqual(occurrences("FreshnessRevealView(", in: page), 1)
        XCTAssertTrue(page.contains(
            "FreshnessRevealView(status:vm.liveUpdateStatus,lastReceivedAt:vm.priceActivity?.receivedAt,confirmedAt:vm.event.flatMap{vm.displayedConfirmation($0)},confidenceTier:confidenceTier,forecast:revealForecast11296)"))
        XCTAssertEqual(occurrences("LiveForecastDetails11296(", in: page), 0, "only inside the popover")
        // #11703 adds two writes of the SAME state: it closes when its page is
        // covered (a link pushed another game) or changes game. #10090 (Alex 67)
        // adds one more: a tap on the EKG opens this same popover.
        XCTAssertEqual(occurrences("showProbabilityDetails", in: page), 6, "the one existing open/close state")
        // The same decision, on the same headline row, both hosts mount from.
        let reveal = try XCTUnwrap(page.range(of: "privatevarrevealForecast11296:LivePregameComparison11296.Headline?{"))
        XCTAssertTrue(page[reveal.upperBound...].hasPrefix(
            "guardletserved=vm.eventelse{returnnil}letevent=vm.headline(served)"
            + "returnliveForecast11296(event,hasScore:EventDetailView.showsScore(status:event.status,away:event.awayScore,home:event.homeScore))}"))
        XCTAssertTrue(page.contains("heroSection(vm.headline(event))"), "the hero reads the same headline row")
    }

    func testThePopoverSetsTheForecastApartFromDeliveryAndPrintsItsSections() throws {
        let feedback = try source("Components/LivePriceChangeFeedback.swift")
        let start = try XCTUnwrap(feedback.range(of: "structFreshnessRevealView:View{"))
        let reveal = String(feedback[start.upperBound...])
        XCTAssertTrue(reveal.contains("varforecast:LivePregameComparison11296.Headline?=nil"))
        let receipt = try XCTUnwrap(reveal.range(of: "Text(\"Receivedonthisdeviceat"))
        let tier = try XCTUnwrap(reveal.range(of: "Text(Confidence.heroBasis)"))
        let mount = try XCTUnwrap(reveal.range(of: "ifletforecast{Divider()LiveForecastDetails11296(forecast:forecast)}"))
        XCTAssertTrue(receipt.upperBound < mount.lowerBound && tier.upperBound < mount.lowerBound,
                      "below delivery and confidence, behind its own divider")
        XCTAssertEqual(occurrences("LiveForecastDetails11296(", in: feedback), 1)

        let helper = try source("Utilities/LivePregameComparison11296.swift")
        let viewStart = try XCTUnwrap(helper.range(of: "structLiveForecastDetails11296:View{"))
        let view = String(helper[viewStart.upperBound...])
        // The body prints exactly what `sections` and `basis` say, so the tests
        // above decide what the reader sees.
        XCTAssertTrue(view.contains("ForEach(Array(Self.sections(forecast).enumerated()),id:\\.offset)"))
        XCTAssertTrue(view.contains("Text(section.title)"))
        XCTAssertTrue(view.contains("Text(line)"))
        XCTAssertTrue(view.contains("Text(Self.basis(forecast.current.admitted.provenance.period))"))
        XCTAssertFalse(view.contains("lineLimit"), "wraps, never truncates")
        XCTAssertFalse(view.contains("minimumScaleFactor"), "wraps, never shrinks")
        // Each forecast's own clocks; never the receipt's, never the newest capture of the current pair.
        XCTAssertFalse(view.contains("receivedAt"), "a delivery clock never stands in for a source clock")
        XCTAssertFalse(view.contains("now.latestCapturedAt"), "the current pair's newest capture is not an update time")
        XCTAssertTrue(view.contains("now.earliestConfirmedAt"))
        XCTAssertTrue(view.contains("b.earliestCapturedAt,b.latestCapturedAt"))
        XCTAssertTrue(view.contains("b.scheduledStart"))
        XCTAssertFalse(view.contains("Button("), "no new control")
        XCTAssertFalse(view.contains("URLSession") || view.contains(".task"), "no fetch")
    }
}
