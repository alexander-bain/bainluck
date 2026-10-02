import XCTest

/// #1739 — the Apple Watch stops saying "Just now" over dead data.
///
/// Three defects, one cause: each watch list stamped its "Xs ago" line once,
/// on success, and kept whatever it last had when a refresh failed or came
/// back empty.
///
/// 1. The age line never counted up, and a failed refresh left "Just now".
/// 2. Trending re-polled only while it had an error or no rows, so a healthy
///    list was never refreshed.
/// 3. Live kept the last non-empty game list when a refresh had no live game:
///    finished games under a "Live" title, and "No live games" unreachable.
///
/// Both directions are pinned (gotcha #43): the dead games go AND a healthy
/// refresh still draws its games; a failure keeps the rows AND says so.
final class WatchFreshnessTellsTheTruth1739Tests: XCTestCase {

    private let t0 = Date(timeIntervalSince1970: 1_790_000_000)

    private func items(_ json: String) throws -> [WatchFeedItem] {
        let dec = JSONDecoder()
        dec.keyDecodingStrategy = .convertFromSnakeCase
        return try dec.decode(WatchFeedResponse.self, from: Data(json.utf8)).items
    }

    private func event(_ id: Int, status: String, home: Double = 0.6) -> String {
        """
        { "type": "event", "score": 50,
          "data": { "id": \(id), "home_team": "Boston Red Sox", "away_team": "New York Yankees",
                    "status": "\(status)", "home_score": 3, "away_score": 2, "sport_name": "MLB",
                    "current_odds": { "home_probability": \(home) },
                    "home_team_data": { "abbreviation": "BOS", "primary_color": "#BD3039" },
                    "away_team_data": { "abbreviation": "NYY", "primary_color": "#003087" },
                    "espn": { "period": "Top 7th", "game_clock": null } } }
        """
    }

    private func feed(_ cards: [String]) throws -> [WatchFeedItem] {
        try items(#"{ "items": [\#(cards.joined(separator: ","))] }"#)
    }

    // MARK: 1 — the age line

    func testAgeLineCountsUpFromTheFetchOfTheShownData() {
        var r = WatchRefreshState()
        XCTAssertNil(r.ageLine(now: t0), "nothing shown yet, nothing claimed")
        r.recordSuccess(fetchedAt: t0)
        XCTAssertEqual(r.ageLine(now: t0.addingTimeInterval(2)), "Just now")
        XCTAssertEqual(r.ageLine(now: t0.addingTimeInterval(42)), "42s ago")
        XCTAssertEqual(r.ageLine(now: t0.addingTimeInterval(185)), "3m ago")
        XCTAssertEqual(r.ageLine(now: t0.addingTimeInterval(2 * 3600 + 5)), "2h ago")
    }

    func testAFailedRefreshKeepsTheOldStampAndSaysItFailed() {
        var r = WatchRefreshState()
        r.recordSuccess(fetchedAt: t0)
        r.recordFailure()
        XCTAssertEqual(r.shownDataFetchedAt, t0, "a failure never re-stamps the data")
        XCTAssertEqual(r.ageLine(now: t0.addingTimeInterval(95)), "Couldn't refresh · 1m ago")
    }

    func testTheNextSuccessClearsTheFailure() {
        var r = WatchRefreshState()
        r.recordSuccess(fetchedAt: t0)
        r.recordFailure()
        r.recordSuccess(fetchedAt: t0.addingTimeInterval(60))
        XCTAssertFalse(r.lastRefreshFailed)
        XCTAssertEqual(r.ageLine(now: t0.addingTimeInterval(61)), "Just now")
    }

    func testAFailureBeforeAnyDataClaimsNoAge() {
        var r = WatchRefreshState()
        r.recordFailure()
        XCTAssertNil(r.ageLine(now: t0), "the error state speaks; no age over nothing")
    }

    // MARK: 3 — the Live list

    func testARefreshWithNoLiveGameEmptiesTheLiveList() throws {
        var list = WatchLiveList()
        list.apply(try feed([event(1, status: "live"), event(2, status: "live")]), fetchedAt: t0)
        XCTAssertEqual(list.games.map(\.id), [1, 2])

        // The slate ends: the same games come back completed.
        list.apply(try feed([event(1, status: "completed"), event(2, status: "completed")]),
                   fetchedAt: t0.addingTimeInterval(30))
        XCTAssertEqual(list.games, [], "finished games never stay under the Live title")
        XCTAssertEqual(list.refresh.ageLine(now: t0.addingTimeInterval(31)), "Just now")
    }

    func testAHealthyRefreshStillDrawsItsGames() throws {
        var list = WatchLiveList()
        list.apply(try feed([event(1, status: "live")]), fetchedAt: t0)
        list.apply(try feed([event(1, status: "completed"), event(3, status: "live", home: 0.25)]),
                   fetchedAt: t0.addingTimeInterval(30))
        XCTAssertEqual(list.games.map(\.id), [3])
        let g = try XCTUnwrap(list.games.first)
        XCTAssertEqual(g.homeProb, 25)
        XCTAssertEqual(g.awayProb, 75)
        XCTAssertEqual(g.homeAbbrev, "BOS")
        XCTAssertEqual(g.awayAbbrev, "NYY")
        XCTAssertEqual(g.sportLabel, "MLB")
    }

    func testAFailedLiveRefreshKeepsTheGamesAndSaysSo() throws {
        var list = WatchLiveList()
        list.apply(try feed([event(1, status: "live")]), fetchedAt: t0)
        list.applyFailure()
        XCTAssertEqual(list.games.map(\.id), [1], "a network blip does not blank the wrist")
        XCTAssertEqual(list.refresh.ageLine(now: t0.addingTimeInterval(40)), "Couldn't refresh · 40s ago")
    }

    // MARK: Views read the shared state (source checks, comments stripped)

    private func watchSource(_ name: String) throws -> String {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()   // BainLuckTests
            .deletingLastPathComponent()   // Bain Luck (project dir)
            .appendingPathComponent("BainLuckWatch Watch App")
            .appendingPathComponent(name)
        let text = try String(contentsOf: url, encoding: .utf8)
        // Strip `//` comments so prose about the old rule cannot satisfy or trip a scan.
        return text.split(separator: "\n", omittingEmptySubsequences: false)
            .map { line -> Substring in
                if let r = line.range(of: "//") { return line[..<r.lowerBound] }
                return line
            }
            .joined(separator: "\n")
    }

    func testNoWatchListBuildsAFrozenAgeString() throws {
        for name in ["WatchHomeView.swift", "WatchLiveView.swift", "WatchGlancesView.swift"] {
            let src = try watchSource(name)
            XCTAssertFalse(src.contains("s ago\""), "\(name) builds its own frozen \"Xs ago\" string")
            XCTAssertFalse(src.contains("lastUpdated"), "\(name) still keeps a once-computed age string")
            XCTAssertTrue(src.contains("ageLine(now:"), "\(name) must render the shared age line")
            XCTAssertTrue(src.contains("TimelineView"), "\(name)'s age line must re-tick while open")
            XCTAssertTrue(src.contains("recordFailure()") || src.contains("applyFailure()"),
                          "\(name) must record a failed refresh")
        }
    }

    func testLiveHasNoRetentionGuard() throws {
        let src = try watchSource("WatchLiveView.swift")
        XCTAssertFalse(src.contains("isEmpty ||"), "Live keeps a stale list behind an isEmpty guard")
        XCTAssertTrue(src.contains(".apply("), "Live must replace its list through WatchLiveList.apply")
    }

    func testTrendingRepollsWhileHealthy() throws {
        let src = try watchSource("WatchGlancesView.swift")
        let loop = try XCTUnwrap(src.range(of: "while !Task.isCancelled"), "Trending has a refresh loop")
        let body = src[loop.upperBound...].prefix(400)
        XCTAssertFalse(body.contains("if vm.error != nil || vm.markets.isEmpty"),
                       "Trending only re-polls on error/empty — a healthy list never refreshes")
        XCTAssertTrue(body.contains("await vm.load("), "Trending's loop must load every tick")
    }
}
