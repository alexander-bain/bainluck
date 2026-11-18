import XCTest
@testable import Bain_Luck

/// Direction 217, wired: the Watch's big rectangular slot in the Matchup look,
/// built from the snapshot the Watch app publishes.
final class WatchMatchupReading217Tests: XCTestCase {
    private let utc = TimeZone(identifier: "UTC")!
    /// Tuesday, two days into the reference week (no wall-clock dates in fixtures).
    private let now = Date(timeIntervalSinceReferenceDate: 86_400)

    private let ne = WatchCompactTeamIdentity(teamID: 1, abbreviation: "NE")
    private let lac = WatchCompactTeamIdentity(teamID: 2, abbreviation: "LAC")
    private let bal = WatchCompactTeamIdentity(teamID: 3, abbreviation: "BAL")
    private let det = WatchCompactTeamIdentity(teamID: 4, abbreviation: "DET")

    private func percent(_ p: Int) -> String {
        (Double(p) / 100).formatted(.percent.precision(.fractionLength(0)))
    }

    private func scheduled(homePercent: Int, start: Date?, facts: WatchMatchupFacts217? = WatchMatchupFacts217()) -> WatchComplicationSnapshot {
        let observed = now.addingTimeInterval(-60)
        let reading = WatchRectangularReading(
            version: 1, eventID: 9, kind: .scheduledForecast,
            homeName: "Los Angeles Chargers", awayName: "New England Patriots", home: lac, away: ne,
            homePercent: homePercent, homeScore: nil, awayScore: nil, commenceTime: start,
            stateLabel: "Scheduled", observedAt: observed, scoreObservedAt: nil)
        return WatchComplicationSnapshot(eventID: 9, title: "Los Angeles Chargers win",
                                         detail: "\(percent(homePercent)) · Scheduled", observedAt: observed,
                                         savedAt: now, rectangularReading: reading, matchup: facts)
    }

    private func live(homePercent: Int, observed: Date, clock: String?) -> WatchComplicationSnapshot {
        let reading = WatchRectangularReading(
            version: 1, eventID: 10, kind: .liveForecast,
            homeName: "Baltimore Ravens", awayName: "Los Angeles Chargers", home: bal, away: lac,
            homePercent: homePercent, homeScore: 17, awayScore: 10, commenceTime: nil,
            stateLabel: "Live", observedAt: observed, scoreObservedAt: observed)
        return WatchComplicationSnapshot(eventID: 10, title: "Baltimore Ravens win",
                                         detail: "\(percent(homePercent)) · Live", observedAt: observed,
                                         savedAt: observed, rectangularReading: reading,
                                         matchup: WatchMatchupFacts217(homePrimary: "#241773", homeSecondary: "#9e7c0c",
                                                                       awayPrimary: "#0080c6", clock: clock))
    }

    private func final(home: Int, away: Int, pregameHome: Int?, pregameAway: Int?) -> WatchComplicationSnapshot {
        let observed = now.addingTimeInterval(-600)
        let reading = WatchRectangularReading(
            version: 1, eventID: 11, kind: .finalResult,
            homeName: "Detroit Lions", awayName: "New England Patriots", home: det, away: ne,
            homePercent: nil, homeScore: home, awayScore: away, commenceTime: nil,
            stateLabel: "Final", observedAt: observed, scoreObservedAt: observed)
        let title: String
        let detail: String
        if home > away { title = "Detroit Lions won"; detail = "Final · \(home)–\(away)" }
        else if away > home { title = "New England Patriots won"; detail = "Final · \(away)–\(home)" }
        else { title = "New England Patriots at Detroit Lions"; detail = "Final · tied \(home)–\(away)" }
        return WatchComplicationSnapshot(eventID: 11, title: title, detail: detail, observedAt: observed,
                                         savedAt: observed, rectangularReading: reading,
                                         matchup: WatchMatchupFacts217(pregameHomePercent: pregameHome,
                                                                       pregameAwayPercent: pregameAway))
    }

    func testBeforeKickoffTheSmallLineNamesTheFavouriteAndTheStart() throws {
        // Sunday 5:20 PM, five days on: "Sun 5:20 PM".
        let start = Date(timeIntervalSinceReferenceDate: 6 * 86_400 + 17 * 3600 + 20 * 60)
        let home = try XCTUnwrap(WatchMatchupReading217.make(snapshot: scheduled(homePercent: 56, start: start),
                                                             now: now, timeZone: utc, crest: { _ in nil }))
        XCTAssertEqual(home.stage, .before)
        XCTAssertEqual(home.bigText, "56%")
        XCTAssertTrue(home.bigIsHome)
        XCTAssertEqual(home.smallLine, "LAC · Sun 5:20 PM")
        XCTAssertNil(home.home.score)

        let away = try XCTUnwrap(WatchMatchupReading217.make(snapshot: scheduled(homePercent: 40, start: start),
                                                             now: now, timeZone: utc, crest: { _ in nil }))
        XCTAssertEqual(away.bigText, "60%")
        XCTAssertFalse(away.bigIsHome)
        XCTAssertEqual(away.smallLine, "NE · Sun 5:20 PM")
        XCTAssertTrue(away.accessibilityText.contains("New England Patriots 60% to win"))
    }

    func testAKickoffThatHasPassedWithoutANewReadingKeepsTodaysCard() {
        let start = now.addingTimeInterval(-60)
        XCTAssertNil(WatchMatchupReading217.make(snapshot: scheduled(homePercent: 56, start: start), now: now,
                                                 timeZone: utc, crest: { _ in nil }))
    }

    func testDuringTheGameTheSmallLineNamesTheLeaderAndTheClock() throws {
        let observed = now
        let reading = try XCTUnwrap(WatchMatchupReading217.make(snapshot: live(homePercent: 74, observed: observed, clock: "Q3 4:12"),
                                                                now: now, timeZone: utc, crest: { _ in nil }))
        XCTAssertEqual(reading.stage, .during)
        XCTAssertEqual(reading.bigText, "74%")
        XCTAssertEqual(reading.smallLine, "BAL · Q3 4:12")
        XCTAssertEqual(reading.home.score, 17)
        XCTAssertEqual(reading.away.score, 10)
        // Ruling 221: the Ravens' purple doesn't read on black, so their gold does.
        XCTAssertEqual(reading.bigInkHex, "#9e7c0c")

        let noClock = try XCTUnwrap(WatchMatchupReading217.make(snapshot: live(homePercent: 30, observed: observed, clock: nil),
                                                                now: now, timeZone: utc, crest: { _ in nil }))
        XCTAssertEqual(noClock.bigText, "70%")
        XCTAssertFalse(noClock.bigIsHome)
        XCTAssertEqual(noClock.smallLine, "LAC · Live")
    }

    func testAnOldLiveReadingSaysWhenItWasTaken() throws {
        let observed = now.addingTimeInterval(-600)
        let reading = try XCTUnwrap(WatchMatchupReading217.make(snapshot: live(homePercent: 74, observed: observed, clock: "Q3 4:12"),
                                                                now: now, timeZone: utc, crest: { _ in nil }))
        XCTAssertEqual(reading.smallLine, "BAL · As of 11:50 PM")
    }

    func testAfterAFinalTheWinnersPregameChanceAndTheTeamAreNamed() throws {
        let home = try XCTUnwrap(WatchMatchupReading217.make(snapshot: final(home: 35, away: 10, pregameHome: 58, pregameAway: 42),
                                                             now: now, timeZone: utc, crest: { _ in nil }))
        XCTAssertEqual(home.stage, .after)
        XCTAssertEqual(home.bigText, "58%")
        XCTAssertTrue(home.bigIsHome)
        XCTAssertEqual(home.smallLine, "DET pregame · Final")
        XCTAssertTrue(home.home.isWinner)
        XCTAssertFalse(home.away.isWinner)

        let away = try XCTUnwrap(WatchMatchupReading217.make(snapshot: final(home: 10, away: 24, pregameHome: 58, pregameAway: 42),
                                                             now: now, timeZone: utc, crest: { _ in nil }))
        XCTAssertEqual(away.bigText, "42%")
        XCTAssertEqual(away.smallLine, "NE pregame · Final")
        XCTAssertTrue(away.away.isWinner)
    }

    func testATieOrAFinalWithoutAPregameChanceKeepsTodaysCard() {
        XCTAssertNil(WatchMatchupReading217.make(snapshot: final(home: 20, away: 20, pregameHome: 58, pregameAway: 42),
                                                 now: now, timeZone: utc, crest: { _ in nil }))
        XCTAssertNil(WatchMatchupReading217.make(snapshot: final(home: 35, away: 10, pregameHome: nil, pregameAway: nil),
                                                 now: now, timeZone: utc, crest: { _ in nil }))
    }

    func testThreeHoursAfterTheFinalTheLauncherStandsIn() throws {
        let snapshot = final(home: 35, away: 10, pregameHome: 58, pregameAway: 42)
        let observed = try XCTUnwrap(snapshot.rectangularReading?.observedAt)
        XCTAssertEqual(WatchMatchupReading217.finalStepAside(for: snapshot, now: now), observed.addingTimeInterval(3 * 3600))
        XCTAssertFalse(WatchMatchupReading217.finalHasPassed(snapshot, now: observed.addingTimeInterval(3 * 3600 - 1)))
        let later = observed.addingTimeInterval(3 * 3600)
        XCTAssertTrue(WatchMatchupReading217.finalHasPassed(snapshot, now: later))
        XCTAssertNil(WatchMatchupReading217.make(snapshot: snapshot, now: later, timeZone: utc, crest: { _ in nil }))
    }

    func testAnOlderSnapshotWithoutFactsKeepsTodaysCardAndStillDecodes() throws {
        let start = Date(timeIntervalSinceReferenceDate: 6 * 86_400)
        let old = scheduled(homePercent: 56, start: start, facts: nil)
        XCTAssertNil(WatchMatchupReading217.make(snapshot: old, now: now, timeZone: utc, crest: { _ in nil }))
        XCTAssertFalse(WatchMatchupReading217.finalHasPassed(old, now: now.addingTimeInterval(86_400)))

        let encoded = try JSONEncoder().encode(old)
        XCTAssertFalse(String(decoding: encoded, as: UTF8.self).contains("matchup"))
        let decoded = try JSONDecoder().decode(WatchComplicationSnapshot.self, from: encoded)
        XCTAssertNil(decoded.matchup)
        XCTAssertNotNil(decoded.validatedRectangularReading(now: now))
    }

    func testTheFactsSurviveTheSharedFileAndStayUnderItsLimit() throws {
        let snapshot = live(homePercent: 74, observed: now, clock: "Q3 4:12")
        let data = try JSONEncoder().encode(snapshot)
        XCTAssertLessThan(data.count, WatchComplicationSnapshot.maximumBytes)
        let decoded = try JSONDecoder().decode(WatchComplicationSnapshot.self, from: data)
        XCTAssertEqual(decoded.matchup, snapshot.matchup)
    }

    func testTheCrestIsLookedUpByTeam() throws {
        let png = Data([0x89, 0x50, 0x4E, 0x47, 1, 2, 3])
        let reading = try XCTUnwrap(WatchMatchupReading217.make(snapshot: live(homePercent: 74, observed: now, clock: nil),
                                                                now: now, timeZone: utc,
                                                                crest: { $0 == 3 ? png : nil }))
        XCTAssertEqual(reading.home.crestPNG, png)
        XCTAssertNil(reading.away.crestPNG)
    }

    func testTheAppSavesOnlyRealHttpsCrests() async throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent("crests217-\(UUID().uuidString)")
        defer { try? FileManager.default.removeItem(at: directory) }
        let png = Data([0x89, 0x50, 0x4E, 0x47, 1, 2, 3])
        let html = Data("<html>".utf8)
        let saved = await WatchMatchupCrests217.fetchMissing(
            [(teamID: 3, logo: "https://example.com/bal.png"),
             (teamID: 2, logo: "http://example.com/lac.png"),
             (teamID: 1, logo: "https://example.com/error")],
            directory: directory, now: now,
            fetch: { $0.lastPathComponent == "error" ? html : png })
        XCTAssertTrue(saved)
        XCTAssertEqual(WatchMatchupCrests217.data(teamID: 3, directory: directory), png)
        XCTAssertNil(WatchMatchupCrests217.data(teamID: 2, directory: directory), "plain http is refused")
        XCTAssertNil(WatchMatchupCrests217.data(teamID: 1, directory: directory), "an error page is not a crest")
        let again = await WatchMatchupCrests217.fetchMissing([(teamID: 3, logo: "https://example.com/bal.png")],
                                                             directory: directory, now: now, fetch: { _ in png })
        XCTAssertFalse(again, "a saved crest is not fetched again")
    }

    func testTheSelectedGameCarriesServedCrestsAndPregameChances() throws {
        let json = """
        {"id": 5, "home_team": "Detroit Lions", "away_team": "New England Patriots",
         "sport": "americanfootball_nfl", "status": "final", "home_score": 35, "away_score": 10,
         "home_team_data": {"team_id": 4, "abbreviation": "DET", "primary_color": "#0076b6",
                            "logo_small": "https://cdn.example/det.png"},
         "away_team_data": {"team_id": 1, "abbreviation": "NE", "logo_small": "http://cdn.example/ne.png",
                            "logo_large": "https://cdn.example/ne-large.png"},
         "prematch_odds": {"home_probability": 0.58, "away_probability": 0.42}}
        """
        let game = try JSONDecoder().decode(WatchSelectedGame.self, from: Data(json.utf8))
        XCTAssertEqual(game.homeLogoURL, "https://cdn.example/det.png")
        XCTAssertEqual(game.awayLogoURL, "https://cdn.example/ne-large.png", "plain http falls through to the large https crest")
        XCTAssertEqual(game.pregameRenderedPercents.home, 58)
        XCTAssertEqual(game.pregameRenderedPercents.away, 42)
        // The saved copy keeps the crest.
        let again = try JSONDecoder().decode(WatchSelectedGame.self, from: JSONEncoder().encode(game))
        XCTAssertEqual(again.homeLogoURL, game.homeLogoURL)
        XCTAssertEqual(again.awayLogoURL, game.awayLogoURL)
    }
}
