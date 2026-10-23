import XCTest
@testable import Bain_Luck

/// #9483 / #11296 — THE OBSERVED-HISTORY FLOOR (Design, MISSING-SURFACE-DISPOSITION,
/// 2026-10-23). A live or finished projected-points input needs a score floor;
/// with no observed first-period start in `period_markers`, the same history's
/// first ESPN sighting of the first period may supply it — at the sighting's own
/// time, as a first-seen floor and never a kickoff.
///
/// Specimen 15195971 (Nuggets @ Thunder, retained capture 03:13:59Z): the
/// markers held the 2nd Quarter `boundary_observed` row, Halftime and the 3rd
/// Quarter; `espn_history` read `11:55 - 1st Quarter` first at
/// 01:50:48.082085Z, score 0–0 — its earliest row. The three markers and that
/// ESPN row keep their served period, precision and time; the other ESPN rows,
/// the score row and the pairs are CONSTRUCTED.
@MainActor
final class TheObservedHistoryFloor9483Tests: XCTestCase {

    private static let sighting = "2026-10-23T01:50:48.082085+00:00"
    private static var sightingDate: Date { sighting.asDate! }
    private static let asOf = "2026-10-23T03:14:01Z".asDate!

    private func espn(_ timestamp: String, _ period: String?, clock: String? = nil) -> String {
        let p = period.map { #""\#($0)""# } ?? "null"
        let c = clock.map { #""\#($0)""# } ?? "null"
        return #"{"timestamp":"\#(timestamp)","home_probability":0.6,"game_clock":\#(c),"period":\#(p),"home_score":0,"away_score":0}"#
    }

    private func marker(_ timestamp: String, _ period: String, precision: String = "first_seen") -> String {
        #"{"timestamp":"\#(timestamp)","period":"\#(period)","source":"espn_state","precision":"\#(precision)","not_before":"\#(timestamp)"}"#
    }

    private func rec(_ minute: String, _ home: Double, _ away: Double) -> String {
        #"{"timestamp":"2026-10-23T\#(minute):00+00:00","home_probability":0.6,"projected_home_score":\#(home),"projected_away_score":\#(away),"kind":"recorded","observed_at":"2026-10-23T\#(minute):30.123456+00:00"}"#
    }

    /// The specimen's served marker shape: no first-quarter start.
    private var specimenMarkers: [String] {
        [marker("2026-10-23T02:17:26.761979+00:00", "2nd Quarter", precision: "boundary_observed"),
         marker("2026-10-23T02:49:23.060930+00:00", "Halftime"),
         marker("2026-10-23T03:07:13.741042+00:00", "3rd Quarter")]
    }

    private var specimenESPN: [String] {
        [espn("2026-10-23T01:20:00+00:00", nil),
         espn(Self.sighting, "11:55 - 1st Quarter", clock: "11:55"),
         espn("2026-10-23T02:13:00+00:00", "11:40 - 2nd Quarter", clock: "11:40")]
    }

    private func history(status: String = "live", espn: [String], markers: [String],
                         pairs: [String] = []) throws -> EventHistoryResponse {
        let json = """
        {"event_id":15195971,"home_team":"Oklahoma City Thunder","away_team":"Denver Nuggets","status":"\(status)",
         "completed_at":null,"history":[],
         "espn_history":[\(espn.joined(separator: ","))],
         "bookmaker_history":{"draftkings":[\(pairs.joined(separator: ","))]},
         "score_history":[{"timestamp":"2026-10-23T02:00:00+00:00","home_score":20,"away_score":18}],
         "period_markers":[\(markers.joined(separator: ","))]}
        """
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(EventHistoryResponse.self, from: Data(json.utf8))
    }

    private func floor(_ h: EventHistoryResponse, sport: String = "basketball_nba") -> ProjectedFinalPointsMount.ObservedFloor? {
        ProjectedFinalPointsMount.observedHistoryFloor(h, sportKey: sport)
    }

    // MARK: - The specimen

    func testTheSpecimenHasNoObservedFirstPeriodMarker() throws {
        let h = try history(espn: specimenESPN, markers: specimenMarkers)
        XCTAssertNil(ProjectedFinalPointsMount.firstRecordedGameStateAt(h.periodMarkers, sportKey: "basketball_nba"),
                     "the 2nd Quarter boundary ends Q1; it is not the start of the game")
    }

    func testTheFirstQuarterSightingIsTheFloorAtItsOwnTime() throws {
        let h = try history(espn: specimenESPN, markers: specimenMarkers)
        let f = try XCTUnwrap(floor(h))
        XCTAssertEqual(f.basis, .espnFirstPeriodSighting)
        XCTAssertEqual(f.at, Self.sightingDate, "first seen — not moved back five seconds for 11:55")
        XCTAssertNotEqual(f.at, "2026-10-23T01:30:00Z".asDate, "never the scheduled start")
    }

    func testTheMountCarriesItAsAScoreFloorAndNeverAKickoff() throws {
        let h = try history(espn: specimenESPN, markers: specimenMarkers,
                            pairs: [rec("01:20", 114.2, 122.2), rec("02:40", 106.5, 104.0),
                                    rec("03:10", 106.0, 103.6)])
        let input = try XCTUnwrap(ProjectedFinalPointsMount.input(
            sportKey: "basketball_nba", eventStatus: "live", history: h,
            finalHome: nil, finalAway: nil, asOf: Self.asOf))
        XCTAssertEqual(input.scoreObservationStartAt, Self.sightingDate)
        XCTAssertNil(input.kickoffAt, "a first sighting says when we saw play, not when it began")
    }

    // MARK: - A marker still wins

    func testAnObservedFirstPeriodMarkerWinsOverTheSighting() throws {
        let h = try history(espn: specimenESPN,
                            markers: [marker("2026-10-23T01:52:00+00:00", "1st Quarter")] + specimenMarkers)
        XCTAssertEqual(floor(h), .init(at: "2026-10-23T01:52:00Z".asDate!, basis: .periodMarkerStart),
                       "the served marker decides exactly as before, even when the sighting is earlier")
    }

    // MARK: - Refusals

    func testAHistoryFirstSeenMidGameHasNoSighting() throws {
        // Watching started in the 2nd Quarter; a later 1st-Quarter row cannot outrank it.
        let h = try history(espn: [espn("2026-10-23T02:13:00+00:00", "11:40 - 2nd Quarter"),
                                   espn("2026-10-23T02:20:00+00:00", "1st Quarter")],
                            markers: specimenMarkers)
        XCTAssertNil(floor(h))
    }

    func testRowsWithoutAPeriodAreNotReadingsOfPlay() throws {
        let h = try history(espn: [espn("2026-10-23T01:20:00+00:00", nil),
                                   espn("2026-10-23T03:30:00+00:00", "Final")],
                            markers: specimenMarkers)
        XCTAssertNil(floor(h))
    }

    func testDisagreeingReadingsAtTheEarliestInstantRefuse() throws {
        let h = try history(espn: [espn(Self.sighting, "11:55 - 1st Quarter"),
                                   espn(Self.sighting, "11:40 - 2nd Quarter")],
                            markers: specimenMarkers)
        XCTAssertNil(floor(h))
    }

    func testTheLeaguesOwnFirstPeriodDecides() throws {
        let h = try history(espn: specimenESPN, markers: specimenMarkers)
        XCTAssertNil(floor(h, sport: "basketball_ncaab"), "men's college opens on a half, never a quarter")
        XCTAssertNil(floor(h, sport: "baseball_mlb"), "an unlisted league has no first period here")
        XCTAssertNotNil(floor(h, sport: "basketball_wncaab"))
    }

    func testAFloorAfterTheReadersClockStillMountsNothing() throws {
        let h = try history(espn: specimenESPN, markers: specimenMarkers,
                            pairs: [rec("01:20", 114.2, 122.2)])
        XCTAssertNil(ProjectedFinalPointsMount.input(
            sportKey: "basketball_nba", eventStatus: "live", history: h,
            finalHome: nil, finalAway: nil, asOf: "2026-10-23T01:45:00Z".asDate!))
    }

    func testBeforeTheGameNoFloorIsRead() throws {
        let h = try history(status: "scheduled", espn: specimenESPN, markers: specimenMarkers,
                            pairs: [rec("01:20", 114.2, 122.2)])
        let input = try XCTUnwrap(ProjectedFinalPointsMount.input(
            sportKey: "basketball_nba", eventStatus: "scheduled", history: h,
            finalHome: nil, finalAway: nil, asOf: "2026-10-23T01:25:00Z".asDate!))
        XCTAssertNil(input.scoreObservationStartAt)
    }
}
