import XCTest
import SwiftUI
@testable import Bain_Luck

/// #11296 / #9483 — the live headline's retained pregame projected final
/// (`LivePregameComparison11296`, `EventDetailView.liveBaseline11296`).
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
    private func baseline(_ json: String = LivePregameComparison11296Tests.baselineNFL,
                          _ edits: [(key: String, value: String)]) throws -> PregameProjection {
        var object = try XCTUnwrap(JSONSerialization.jsonObject(with: Data(json.utf8)) as? [String: Any])
        for edit in edits {
            object[edit.key] = try JSONSerialization.jsonObject(with: Data(edit.value.utf8), options: .fragmentsAllowed)
        }
        let data = try JSONSerialization.data(withJSONObject: object)
        return try decoder().decode(PregameProjection.self, from: data)
    }

    private func baseline(_ json: String = LivePregameComparison11296Tests.baselineNFL,
                          _ key: String, _ value: String) throws -> PregameProjection {
        try baseline(json, [(key, value)])
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
        finalScorePeriod: String? = nil
    ) -> String {
        var odds = #"{"home_probability": 0.80, "away_probability": 0.20, "projected_home_score": 36.9, "projected_away_score": 10.7, "bookmaker_count": 3"#
        if let liveProjection { odds += #", "live_projection": "# + liveProjection }
        odds += "}"
        let score: (Int?) -> String = { $0.map(String.init) ?? "null" }
        let espn = period.map { #"{"period": "\#($0)"}"# } ?? "null"
        var extra = ""
        if let pregameProjection { extra += #", "pregame_projection": "# + pregameProjection }
        if let finalScorePeriod { extra += #", "final_score_period": "\#(finalScorePeriod)""# }
        return #"""
        {"id": 14870008, "sport": "\#(sport)", "home_team": "Georgia Bulldogs", "away_team": "Oklahoma Sooners", "commence_time": "\#(start)", "start_is_tbd": false, "start_is_from_schedule": true, "status": "\#(status)", "home_score": \#(score(home)), "away_score": \#(score(away)), "current_odds": \#(odds), "espn": \#(espn)\#(extra)}
        """#
    }

    private func detail(_ json: String, file: StaticString = #filePath, line: UInt = #line) throws -> EventDetail {
        do { return try decoder().decode(EventDetail.self, from: Data(json.utf8)) } catch {
            XCTFail("row did not decode: \(error)", file: file, line: line); throw error
        }
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
            EventDetailView.liveBaseline11296(e, ladderHome: ladder?.home, ladderAway: ladder?.away,
                                              hasScore: hasScore, now: Self.pageNow))
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
        let c = try XCTUnwrap(EventDetailView.liveBaseline11296(e, ladderHome: nil, ladderAway: nil,
                                                                hasScore: true, now: Self.pageNow))
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
        XCTAssertNil(EventDetailView.liveBaseline11296(final, ladderHome: nil, ladderAway: nil,
                                                       hasScore: true, now: Self.pageNow))
        // And a live row never reaches the final line.
        let live = try detail(rowJSON(liveProjection: Self.nflObject, pregameProjection: Self.baselineNFL))
        XCTAssertNil(EventDetailView.finalForecast11296(live))
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
        let mount = "LivePregameBaselineLine11296(comparison:liveBaseline,awayName:names.away,homeName:names.home)"
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
        XCTAssertTrue(page.contains("letliveBaseline=liveBaseline11296(event,hasScore:hasScore)"))
        XCTAssertEqual(occurrences("LivePregameComparison11296.resolve(", in: page), 1)
        XCTAssertEqual(occurrences("liveProjection", in: page), 0, "the page never reads the object's fields itself")
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
}
