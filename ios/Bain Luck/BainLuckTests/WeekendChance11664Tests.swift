import XCTest
@testable import Bain_Luck

/// #11664 — which weekend, which game, and what Siri says. Every clock is a
/// fixed instant with its own UTC offset written out (gotcha #44).
private func at(_ iso: String) -> Date {
    ISO8601DateFormatter().date(from: iso)!
}

private let pacific = TimeZone(identifier: "America/Los_Angeles")!
private let eastern = TimeZone(identifier: "America/New_York")!
private let utc = TimeZone(identifier: "UTC")!

final class WeekendWindow11664Tests: XCTestCase {
    private func assertWindow(_ now: String, _ timeZone: TimeZone, _ start: String, _ end: String,
                              file: StaticString = #filePath, line: UInt = #line) {
        let window = WeekendWindow11664.window(at: at(now), timeZone: timeZone)
        XCTAssertEqual(window.start, at(start), "start for \(now) in \(timeZone.identifier)", file: file, line: line)
        XCTAssertEqual(window.end, at(end), "end for \(now) in \(timeZone.identifier)", file: file, line: line)
    }

    func testAWeekdayMeansTheComingWeekend() {
        assertWindow("2026-11-04T10:00:00-08:00", pacific, "2026-11-07T00:00:00-08:00", "2026-11-09T00:00:00-08:00")
        assertWindow("2026-11-06T23:59:59-08:00", pacific, "2026-11-07T00:00:00-08:00", "2026-11-09T00:00:00-08:00")
    }

    func testASaturdayOrSundayMeansThisWeekendToItsLastSecond() {
        assertWindow("2026-11-07T00:00:00-08:00", pacific, "2026-11-07T00:00:00-08:00", "2026-11-09T00:00:00-08:00")
        assertWindow("2026-11-08T23:59:59-08:00", pacific, "2026-11-07T00:00:00-08:00", "2026-11-09T00:00:00-08:00")
    }

    func testMondayMidnightBelongsToTheNextWeekend() {
        assertWindow("2026-11-09T00:00:00-08:00", pacific, "2026-11-14T00:00:00-08:00", "2026-11-16T00:00:00-08:00")
    }

    func testTheNovember1ClockChangeMakesA49HourWeekend() {
        for now in ["2026-10-31T12:00:00-07:00", "2026-11-01T01:30:00-07:00", "2026-11-01T01:30:00-08:00"] {
            assertWindow(now, pacific, "2026-10-31T00:00:00-07:00", "2026-11-02T00:00:00-08:00")
        }
        let window = WeekendWindow11664.window(at: at("2026-10-31T12:00:00-07:00"), timeZone: pacific)
        XCTAssertEqual(window.duration, 49 * 3_600)
    }

    func testTheMarchClockChangeMakesA47HourWeekend() {
        assertWindow("2026-03-07T12:00:00-05:00", eastern, "2026-03-07T00:00:00-05:00", "2026-03-09T00:00:00-04:00")
        XCTAssertEqual(WeekendWindow11664.window(at: at("2026-03-07T12:00:00-05:00"), timeZone: eastern).duration,
                       47 * 3_600)
    }

    func testThePhonesClockDecidesWhichWeekendAnInstantIsIn() {
        // Sunday 10 PM in New York is already Monday in UTC.
        assertWindow("2026-11-08T22:00:00-05:00", eastern, "2026-11-07T00:00:00-05:00", "2026-11-09T00:00:00-05:00")
        assertWindow("2026-11-09T03:00:00Z", utc, "2026-11-14T00:00:00Z", "2026-11-16T00:00:00Z")
        assertWindow("2026-11-14T00:00:00Z", utc, "2026-11-14T00:00:00Z", "2026-11-16T00:00:00Z")
    }
}

final class WeekendGamePick11664Tests: XCTestCase {
    private let patriots = "New England Patriots"
    private let wednesday = at("2026-11-04T10:00:00-08:00")
    private var window: DateInterval { WeekendWindow11664.window(at: wednesday, timeZone: pacific) }

    private func game(_ id: Int, home: String, away: String, _ start: String,
                      finished: Bool = false, stopped: Bool = false) -> WeekendGame11664 {
        WeekendGame11664(id: id, homeTeam: home, awayTeam: away, start: at(start), finished: finished, stopped: stopped)
    }

    private func pick(_ games: [WeekendGame11664], now: Date? = nil) -> WeekendGamePick11664 {
        WeekendGamePick11664.pick(team: patriots, games: games, window: window, now: now ?? wednesday)
    }

    func testOneGameThisWeekendAnswersWithTheTeamsSide() {
        let home = game(1, home: patriots, away: "Green Bay Packers", "2026-11-08T13:25:00-08:00")
        XCTAssertEqual(pick([home]), .one(home, side: .home))
        // A Sunday-night kickoff on the West Coast is Monday in UTC, still this weekend.
        let away = game(2, home: "Detroit Lions", away: patriots, "2026-11-08T17:20:00-08:00")
        XCTAssertEqual(pick([away]), .one(away, side: .away))
    }

    func testMondayNightIsTheNextGameNotThisWeekends() {
        let monday = game(3, home: patriots, away: "Buffalo Bills", "2026-11-09T17:15:00-08:00")
        XCTAssertEqual(pick([monday]), .noGame(next: monday))
    }

    func testNoGameNamesTheNextUnfinishedOne() {
        let lastWeek = game(4, home: "Miami Dolphins", away: patriots, "2026-11-01T10:00:00-08:00", finished: true)
        let next = game(5, home: "Detroit Lions", away: patriots, "2026-11-15T06:30:00-08:00")
        let later = game(6, home: patriots, away: "Buffalo Bills", "2026-11-22T10:00:00-08:00")
        XCTAssertEqual(pick([later, lastWeek, next]), .noGame(next: next))
        XCTAssertEqual(pick([lastWeek]), .noGame(next: nil))
        XCTAssertEqual(pick([]), .noGame(next: nil))
    }

    func testTwoGamesThisWeekendAskWhichOne() {
        let sunday = game(7, home: patriots, away: "Green Bay Packers", "2026-11-08T13:25:00-08:00")
        let saturday = game(8, home: "Detroit Lions", away: patriots, "2026-11-07T10:00:00-08:00")
        XCTAssertEqual(pick([sunday, saturday]), .several([saturday, sunday]))
    }

    func testAPostponedGameDropsOutAndTheNextOneIsNamed() {
        let postponed = game(9, home: patriots, away: "Green Bay Packers", "2026-11-08T13:25:00-08:00", stopped: true)
        let next = game(10, home: "Detroit Lions", away: patriots, "2026-11-15T06:30:00-08:00")
        XCTAssertEqual(pick([postponed, next]), .noGame(next: next))
    }

    func testAFinalOrLiveGameThisWeekendStillAnswers() {
        let final = game(11, home: patriots, away: "Green Bay Packers", "2026-11-08T10:00:00-08:00", finished: true)
        XCTAssertEqual(pick([final], now: at("2026-11-08T20:00:00-08:00")), .one(final, side: .home))
        let live = game(12, home: "Detroit Lions", away: patriots, "2026-11-08T10:00:00-08:00")
        XCTAssertEqual(pick([live], now: at("2026-11-08T11:30:00-08:00")), .one(live, side: .away))
    }

    func testAGameThatDoesNotNameTheTeamIsUnclearNotGuessed() {
        let renamed = game(13, home: "NE Patriots", away: "Green Bay Packers", "2026-11-08T13:25:00-08:00")
        XCTAssertEqual(pick([renamed]), .sideUnclear(renamed))
        let both = game(14, home: patriots, away: patriots, "2026-11-08T13:25:00-08:00")
        XCTAssertEqual(pick([both]), .sideUnclear(both))
    }

    func testTheSameGameInBothListsCountsOnce() {
        let live = game(15, home: patriots, away: "Green Bay Packers", "2026-11-08T13:25:00-08:00")
        XCTAssertEqual(pick([live, live]), .one(live, side: .home))
    }

    // MARK: - What Siri says

    private func event(_ json: String) throws -> EventDetail {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(EventDetail.self, from: Data(json.utf8))
    }

    @MainActor
    func testTheDayAndOpponentComeFirstThenTheGamePagesOwnAnswer() throws {
        let final = try event("""
        {"id":14780574,"home_team":"New England Patriots","away_team":"Green Bay Packers",
         "sport":"americanfootball_nfl","status":"completed","commence_time":"2026-11-08T21:25:00Z",
         "home_score":31,"away_score":10}
        """)
        let text = WeekendChanceAnswer11664.game(final, side: .home, now: at("2026-11-09T06:00:00Z"),
                                                 timeZone: pacific, locale: Locale(identifier: "en_US"))
        let page = ProbabilityAnswer10873.game(final, side: .home, now: at("2026-11-09T06:00:00Z")).text
        XCTAssertEqual(text, "This weekend: Sunday, Nov 8, at home against the Green Bay Packers. \(page)")
        XCTAssertTrue(page.contains("won"), page)
        XCTAssertEqual(WeekendChanceAnswer11664.lead(final, side: .away, timeZone: pacific, locale: Locale(identifier: "en_US")),
                       "This weekend: Sunday, Nov 8, at the New England Patriots.")
    }

    @MainActor
    func testAWithheldChanceStaysWithheld() throws {
        let drawPriced = try event("""
        {"id":7,"home_team":"Chelsea","away_team":"Arsenal","sport":"soccer_epl","status":"live",
         "commence_time":"2026-11-07T15:00:00Z","home_score":1,"away_score":1,
         "current_odds":{"home_probability":0.4,"away_probability":0.35,"draw_probability":0.25}}
        """)
        let text = WeekendChanceAnswer11664.game(drawPriced, side: .away, now: at("2026-11-07T15:30:00Z"),
                                                 timeZone: utc, locale: Locale(identifier: "en_US"))
        XCTAssertTrue(text.hasPrefix("This weekend: Saturday, Nov 7, "), text)
        XCTAssertTrue(text.contains("doesn't show a separate chance for Arsenal"), text)
        XCTAssertFalse(text.contains("%"), "a withheld away chance was printed: \(text)")
    }

    func testNoGameAndUnclearSayWhatTheyKnow() {
        let next = game(5, home: "Detroit Lions", away: patriots, "2026-11-15T06:30:00-08:00")
        XCTAssertEqual(WeekendChanceAnswer11664.noGame(team: patriots, next: next, timeZone: pacific, locale: Locale(identifier: "en_US")),
                       "The New England Patriots have no game this weekend. Their next game is Sunday, Nov 15, at the Detroit Lions.")
        let home = game(6, home: patriots, away: "Buffalo Bills", "2026-11-22T10:00:00-08:00")
        XCTAssertTrue(WeekendChanceAnswer11664.noGame(team: patriots, next: home, timeZone: pacific, locale: Locale(identifier: "en_US"))
            .hasSuffix("Sunday, Nov 22, against the Buffalo Bills."))
    }
}

final class SupportedTeam11664Tests: XCTestCase {
    func testThirtyTwoTeamsEachNamedAsTheServerNamesThem() {
        XCTAssertEqual(SupportedTeam11664.allCases.count, 32)
        XCTAssertEqual(Set(SupportedTeam11664.allCases.map(\.rawValue)).count, 32)
        for team in SupportedTeam11664.allCases {
            let title = SupportedTeam11664.caseDisplayRepresentations[team].map { String(localized: $0.title) }
            XCTAssertEqual(title, team.teamName, team.rawValue)
        }
        XCTAssertEqual(SupportedTeam11664.sanFrancisco49ers.teamName, "San Francisco 49ers")
    }

    func testSynonymsAreUniqueAndNeverASharedCity() {
        var owner: [String: SupportedTeam11664] = [:]
        let names = Set(SupportedTeam11664.allCases.map { $0.teamName.lowercased() })
        for team in SupportedTeam11664.allCases {
            let synonyms = SupportedTeam11664.caseDisplayRepresentations[team]?.synonyms ?? []
            XCTAssertFalse(synonyms.isEmpty, "\(team.rawValue) has no nickname")
            for synonym in synonyms.map({ String(localized: $0).lowercased() }) {
                XCTAssertNil(owner[synonym], "\"\(synonym)\" names both \(owner[synonym]!.rawValue) and \(team.rawValue)")
                XCTAssertFalse(names.contains(synonym), "\"\(synonym)\" is another team's full name")
                XCTAssertFalse(["new york", "los angeles", "ny", "la"].contains(synonym), "\"\(synonym)\" is a shared city")
                owner[synonym] = team
            }
        }
        XCTAssertEqual(owner["pats"], .newEnglandPatriots)
    }

    func testEveryPhraseNamesTheApp() throws {
        let file = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
            .appendingPathComponent("Bain Luck/Intents/BainLuckIntents10873.swift")
        let source = try String(contentsOf: file, encoding: .utf8)
        let provider = try XCTUnwrap(source.range(of: "struct BainLuckShortcuts10873"))
        let body = source[provider.upperBound...]
        var phrases: [String] = []
        var inPhrases = false
        for line in body.split(separator: "\n").map({ $0.trimmingCharacters(in: .whitespaces) }) {
            if line.hasPrefix("phrases: [") { inPhrases = true; continue }
            if inPhrases && line.hasPrefix("]") { inPhrases = false; continue }
            if inPhrases && line.hasPrefix("\"") { phrases.append(line) }
        }
        XCTAssertEqual(phrases.count, 11, "phrases found: \(phrases)")
        for phrase in phrases {
            XCTAssertTrue(phrase.contains("\\(.applicationName)"), "a phrase without the app's name: \(phrase)")
        }
        XCTAssertTrue(phrases.contains { $0.contains("\\(\\.$team)") && $0.contains("this weekend") })
    }
}
