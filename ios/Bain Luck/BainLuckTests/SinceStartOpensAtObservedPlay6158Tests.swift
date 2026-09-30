import XCTest
@testable import Bain_Luck

/// #6158 — on a game that started late, "Since Start" opens at the first
/// OBSERVED opening period, not the scheduled hour. The phone half of ux's web
/// PR #9939 (`frontend/lib/observedPlayStart.ts`), same rule, same specimen.
///
/// SPECIMEN: White Sox @ Astros, `/events/15321836`, 2026-09-30. Scheduled
/// 21:00Z; the first Top 1st anyone saw is 21:13:06Z (the served `win_prob`
/// marker and `stat_model`'s game state, same instant; ESPN's first period row
/// is 21:14:06Z). The old window opened at 21:00Z: the first thirteen minutes of
/// a one-hour Since Start picture were a flat pre-game line drawn as play.
///
/// FIXTURE: `Fixtures/history-15321836-late-start.20260930T2213Z.json` is the
/// served `GET /api/events/15321836/history`, fetched 2026-09-30 ~23:17Z, cut
/// back to 22:13:00Z (every point after it dropped, status set to `live`) and
/// thinned 1-in-12 before 20:00Z. Everything Since Start draws is whole.
final class SinceStartOpensAtObservedPlay6158Tests: XCTestCase {

    // MARK: - Specimen

    private static var testsDir: URL { URL(fileURLWithPath: #filePath).deletingLastPathComponent() }
    private static let commence = "2026-09-30T21:00:00+00:00"
    private static let now = "2026-09-30T22:13:00Z".asDate!
    private static let firstTop1st = "2026-09-30T21:13:06.610471+00:00".asDate!

    private static func specimen() throws -> EventHistoryResponse {
        let url = testsDir.appendingPathComponent(
            "Fixtures/history-15321836-late-start.20260930T2213Z.json")
        return try decode(Data(contentsOf: url))
    }

    private static func decode(_ data: Data) throws -> EventHistoryResponse {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(EventHistoryResponse.self, from: data)
    }

    private static func window(_ range: OddsTimeRange,
                               history: EventHistoryResponse) throws -> ClosedRange<Date> {
        try XCTUnwrap(SharedChartWindow.domain(
            status: "live", commenceTime: commence, history: history,
            range: range, sportKey: "baseball_mlb", now: now))
    }

    func testSpecimenSinceStartOpensTwoMinutesBeforeTheFirstObservedTopOfTheFirst() throws {
        let window = try Self.window(.sinceStart, history: Self.specimen())
        XCTAssertEqual(window.lowerBound.timeIntervalSince1970,
                       Self.firstTop1st.addingTimeInterval(-120).timeIntervalSince1970,
                       accuracy: 0.001,
                       "Since Start must open at 21:11:06Z, not the scheduled 21:00Z")
        XCTAssertGreaterThan(window.lowerBound, Self.commence.asDate!)
    }

    /// The fullscreen chart has no shared window and cuts with the helper
    /// directly; it must open at the same instant as the page.
    func testSpecimenHelperCutEqualsThePageWindow() throws {
        let history = try Self.specimen()
        let cut = try XCTUnwrap(ObservedPlayStart.cut(
            scheduled: Self.commence.asDate, history: history, sportKey: "baseball_mlb"))
        XCTAssertEqual(cut, try Self.window(.sinceStart, history: history).lowerBound)
    }

    /// All is a superset of Since Start: the late start does not narrow it.
    func testSpecimenAllStillOpensAtOrBeforeTheScheduledStart() throws {
        let window = try Self.window(.all, history: Self.specimen())
        XCTAssertLessThanOrEqual(window.lowerBound, Self.commence.asDate!)
    }

    /// Without a sport the inning's half cannot be read — the helper declines
    /// and the window keeps the scheduled start, exactly as before.
    func testSpecimenWithoutASportKeepsTheScheduledStart() throws {
        let window = try XCTUnwrap(SharedChartWindow.domain(
            status: "live", commenceTime: Self.commence, history: Self.specimen(),
            range: .sinceStart, now: Self.now))
        XCTAssertLessThanOrEqual(window.lowerBound, Self.commence.asDate!)
    }

    // MARK: - The rule, clause by clause

    private static let scheduled = "2026-09-30T21:00:00Z".asDate!

    private static func sighting(_ minutesAfter: Double, opening: Bool = true, observed: Bool = true,
                                 notBeforeMinutes: Double? = nil) -> ObservedPlayStart.Sighting {
        ObservedPlayStart.Sighting(
            date: scheduled.addingTimeInterval(minutesAfter * 60),
            isOpening: opening, isObserved: observed,
            notBefore: notBeforeMinutes.map { scheduled.addingTimeInterval($0 * 60) })
    }

    func testLateOpeningObservationCutsTwoMinutesBeforeIt() {
        let cut = ObservedPlayStart.cut(scheduled: Self.scheduled,
                                        sightings: [Self.sighting(13), Self.sighting(40, opening: false)])
        XCTAssertEqual(cut, Self.scheduled.addingTimeInterval(11 * 60))
    }

    func testNotBeforeEarlierThanTheLeadInIsTheCut() {
        let cut = ObservedPlayStart.cut(scheduled: Self.scheduled,
                                        sightings: [Self.sighting(20, notBeforeMinutes: 9)])
        XCTAssertEqual(cut, Self.scheduled.addingTimeInterval(9 * 60))
    }

    func testNeverEarlierThanTheScheduledStart() {
        XCTAssertNil(ObservedPlayStart.cut(scheduled: Self.scheduled, sightings: [Self.sighting(1)]))
        XCTAssertNil(ObservedPlayStart.cut(scheduled: Self.scheduled, sightings: [Self.sighting(-5)]))
        XCTAssertNil(ObservedPlayStart.cut(scheduled: Self.scheduled,
                                           sightings: [Self.sighting(20, notBeforeMinutes: -3)]))
    }

    func testEarliestNotAnOpeningPeriodDeclines() {
        // We started watching mid-game; a later opening sighting does not rescue it.
        XCTAssertNil(ObservedPlayStart.cut(scheduled: Self.scheduled,
                                           sightings: [Self.sighting(15, opening: false), Self.sighting(20)]))
    }

    func testEarliestNotObservedDeclines() {
        XCTAssertNil(ObservedPlayStart.cut(scheduled: Self.scheduled,
                                           sightings: [Self.sighting(10, observed: false), Self.sighting(20)]))
    }

    func testMoreThanThreeHoursLateDeclines() {
        XCTAssertNil(ObservedPlayStart.cut(scheduled: Self.scheduled, sightings: [Self.sighting(181)]))
        XCTAssertNotNil(ObservedPlayStart.cut(scheduled: Self.scheduled, sightings: [Self.sighting(179)]))
    }

    func testNoSightingsOrNoScheduleDeclines() {
        XCTAssertNil(ObservedPlayStart.cut(scheduled: Self.scheduled, sightings: []))
        XCTAssertNil(ObservedPlayStart.cut(scheduled: nil, sightings: [Self.sighting(13)]))
    }

    // MARK: - What counts as the opening period

    func testOpeningPeriodVocabulary() {
        XCTAssertTrue(ObservedPlayStart.isOpeningPeriod("Top 1st", sportKey: "baseball_mlb"))
        XCTAssertFalse(ObservedPlayStart.isOpeningPeriod("Bottom 1st", sportKey: "baseball_mlb"))
        XCTAssertFalse(ObservedPlayStart.isOpeningPeriod("Middle 1st", sportKey: "baseball_mlb"))
        XCTAssertFalse(ObservedPlayStart.isOpeningPeriod("Top 3rd", sportKey: "baseball_mlb"))
        XCTAssertTrue(ObservedPlayStart.isOpeningPeriod("1st Quarter", sportKey: "americanfootball_nfl"))
        XCTAssertFalse(ObservedPlayStart.isOpeningPeriod("2nd Quarter", sportKey: "americanfootball_nfl"))
        XCTAssertTrue(ObservedPlayStart.isOpeningPeriod("1st Period", sportKey: "icehockey_nhl"))
        XCTAssertTrue(ObservedPlayStart.isOpeningPeriod("1st Half", sportKey: "soccer_epl"))
        XCTAssertFalse(ObservedPlayStart.isOpeningPeriod("Halftime", sportKey: "soccer_epl"))
    }

    // MARK: - Reading the payload

    private static func payload(espn: String = "[]", winProb: String = "{}",
                                markers: String = "[]") throws -> EventHistoryResponse {
        let json = """
        {"event_id":1,"home_team":"Houston Astros","away_team":"Chicago White Sox",
         "history":[],"espn_history":\(espn),
         "win_prob_history":\(winProb),"period_markers":\(markers)}
        """
        return try decode(Data(json.utf8))
    }

    func testBottomOfTheFirstSeenFirstKeepsTheScheduledStart() throws {
        let history = try Self.payload(espn: """
        [{"timestamp":"2026-09-30T21:25:00Z","period":"Bottom 1st"},
         {"timestamp":"2026-09-30T21:40:00Z","period":"Top 2nd"}]
        """)
        XCTAssertNil(ObservedPlayStart.cut(scheduled: Self.scheduled, history: history, sportKey: "baseball_mlb"))
    }

    func testAnEstimatedServedOpeningMarkerDeclines() throws {
        let history = try Self.payload(markers: """
        [{"timestamp":"2026-09-30T21:20:00Z","period":"Top 1st","source":"estimated"}]
        """)
        XCTAssertNil(ObservedPlayStart.cut(scheduled: Self.scheduled, history: history, sportKey: "baseball_mlb"))
    }

    func testAServedMarkerWithNoSourceDeclines() throws {
        let history = try Self.payload(markers: """
        [{"timestamp":"2026-09-30T21:20:00Z","period":"Top 1st"}]
        """)
        XCTAssertNil(ObservedPlayStart.cut(scheduled: Self.scheduled, history: history, sportKey: "baseball_mlb"))
    }

    func testAServedNotBeforeBoundsTheCut() throws {
        let history = try Self.payload(markers: """
        [{"timestamp":"2026-09-30T21:20:00Z","period":"Top 1st","source":"statpal",
          "not_before":"2026-09-30T21:10:00Z"}]
        """)
        XCTAssertEqual(ObservedPlayStart.cut(scheduled: Self.scheduled, history: history, sportKey: "baseball_mlb"),
                       "2026-09-30T21:10:00Z".asDate)
    }

    func testAnInningWithNoHalfSeenFirstDeclines() throws {
        let history = try Self.payload(winProb: """
        {"mlb":[{"timestamp":"2026-09-30T21:12:00Z","home_probability":0.5,"away_probability":0.5,
                 "game_state":{"inning":1}}],
         "stat_model":[{"timestamp":"2026-09-30T21:14:00Z","home_probability":0.5,"away_probability":0.5,
                 "game_state":{"period":"Top 1st"}}]}
        """)
        XCTAssertNil(ObservedPlayStart.cut(scheduled: Self.scheduled, history: history, sportKey: "baseball_mlb"))
    }

    func testTheSyntheticLiveEdgeIsNotAnObservation() throws {
        // The live edge re-serves a state at the request's "now"; were it read,
        // its earlier-stamped mid-game state would decline the real Top 1st.
        let history = try Self.payload(winProb: """
        {"stat_model":[
          {"timestamp":"2026-09-30T21:05:00Z","home_probability":0.5,"away_probability":0.5,
           "game_state":{"period":"Top 5th"},"live_edge":true},
          {"timestamp":"2026-09-30T21:14:00Z","home_probability":0.5,"away_probability":0.5,
           "game_state":{"period":"Top 1st"}}]}
        """)
        XCTAssertEqual(ObservedPlayStart.cut(scheduled: Self.scheduled, history: history, sportKey: "baseball_mlb"),
                       "2026-09-30T21:12:00Z".asDate)
    }
}
