import XCTest
@testable import Bain_Luck

/// #10234 — the iPhone team page's Championship Path printed "Division 37% #1"
/// above a Division Race showing the Vikings at 38%.
///
/// Specimens: `/api/playoffs/nfl` (NFC North, the fields the race reads) and
/// `/api/teams/detroit-lions` `championship_path` as served on 2026-10-02 ~21:30Z.
/// The served division step is `{probability: 0.365, rank: 1}`. The number is the
/// average of Kalshi 0.385 and Polymarket 0.345, and the rank is Kalshi's alone.
final class TeamPathDivisionRankAgreesWithTheRace10234Tests: XCTestCase {

    private static let gridJSON = #"""
    {"league": "nfl", "name": "NFL Playoffs 2026-27", "season": "2026-27", "columns": [],
     "movers": [], "team_count": 4, "last_updated": null, "sources_available": ["kalshi", "polymarket"],
     "championship_market_id": null,
     "teams": [
      {"name": "Detroit Lions", "team_id": 567, "conference": "National Football Conference",
       "division": "NFC North", "cells": {
        "make_playoffs": {"merged_probability": 0.6775, "state": "live"},
        "division": {"merged_probability": 0.365, "state": "live"},
        "championship": {"merged_probability": 0.0393, "state": "live"}}},
      {"name": "Chicago Bears", "team_id": 561, "conference": "National Football Conference",
       "division": "NFC North", "cells": {
        "make_playoffs": {"merged_probability": 0.525, "state": "live"},
        "division": {"merged_probability": 0.21, "state": "live"},
        "championship": {"merged_probability": 0.035, "state": "live"}}},
      {"name": "Minnesota Vikings", "team_id": 555, "conference": "National Football Conference",
       "division": "NFC North", "cells": {
        "make_playoffs": {"merged_probability": 0.7125, "state": "live"},
        "division": {"merged_probability": 0.38, "state": "live"},
        "championship": {"merged_probability": 0.0343, "state": "live"}}},
      {"name": "Green Bay Packers", "team_id": 559, "conference": "National Football Conference",
       "division": "NFC North", "cells": {
        "make_playoffs": {"merged_probability": 0.29, "state": "live"},
        "division": {"merged_probability": 0.07, "state": "live"},
        "championship": {"merged_probability": 0.0143, "state": "live"}}}
     ]}
    """#

    private static let pathJSON = #"""
    [{"tier": 1, "label": "Championship", "market_name": "Pro Football: 2027 Champion",
      "market_id": 129037, "probability": 0.0379, "rank": 10, "movement": null, "season": "2026"},
     {"tier": 2, "label": "Conference", "market_name": "NFC Championship Winner",
      "market_id": 31615, "probability": 0.071, "rank": 5, "movement": null, "season": "2026"},
     {"tier": 4, "label": "Division", "market_name": "NFC North Division Winner",
      "market_id": 53673, "probability": 0.365, "rank": 1, "movement": null, "season": "2026"}]
    """#

    private let lionsId = 567

    private func decoder() -> JSONDecoder {
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        return d
    }

    private func path() throws -> [ChampionshipPathEntry] {
        try decoder().decode([ChampionshipPathEntry].self, from: Data(Self.pathJSON.utf8))
    }

    private func entry(tier: Int) throws -> ChampionshipPathEntry {
        try XCTUnwrap(path().first { $0.tier == tier })
    }

    /// The served grid with one club's division cell replaced.
    private func race(editing name: String? = nil, division: [String: Any]? = nil,
                      dropDivision: Bool = false) throws -> TeamDivisionRace.Race {
        var obj = try XCTUnwrap(
            JSONSerialization.jsonObject(with: Data(Self.gridJSON.utf8)) as? [String: Any])
        var teams = try XCTUnwrap(obj["teams"] as? [[String: Any]])
        for i in teams.indices {
            var cells = try XCTUnwrap(teams[i]["cells"] as? [String: Any])
            if dropDivision { cells["division"] = nil }
            if let name, let division, (teams[i]["name"] as? String) == name {
                cells["division"] = division
            }
            teams[i]["cells"] = cells
        }
        obj["teams"] = teams
        let grid = try decoder().decode(
            ChampionshipGridResponse.self, from: JSONSerialization.data(withJSONObject: obj))
        return try XCTUnwrap(TeamDivisionRace.build(grid: grid, teamId: lionsId, teamName: "Detroit Lions"))
    }

    // MARK: - The specimen

    func testTheSpecimenIsTheContradiction() throws {
        let division = try entry(tier: 4)
        XCTAssertEqual(division.rank, 1, "the served rank is Kalshi's own #1")
        let race = try race()
        let lions = try XCTUnwrap(race.rows.first(where: \.isTeam))
        let vikings = try XCTUnwrap(race.rows.first { $0.name == "Minnesota Vikings" })
        XCTAssertGreaterThan(
            try XCTUnwrap(vikings.division.probability), try XCTUnwrap(lions.division.probability))
    }

    func testTheLionsDivisionRankReadsTheRaceNotTheServedRank() throws {
        XCTAssertEqual(
            TeamDivisionRace.pathRank(try entry(tier: 4), race: try race(), raceSettled: true), 2)
    }

    func testLeagueWideRanksStayAsServed() throws {
        let race = try race()
        XCTAssertEqual(TeamDivisionRace.pathRank(try entry(tier: 1), race: race, raceSettled: true), 10)
        XCTAssertEqual(TeamDivisionRace.pathRank(try entry(tier: 2), race: race, raceSettled: true), 5)
    }

    // MARK: - Before the race exists

    func testNoDivisionRankWhileTheRaceIsStillLoading() throws {
        XCTAssertNil(TeamDivisionRace.pathRank(try entry(tier: 4), race: nil, raceSettled: false))
        // Only the division step waits; the others never consult the race.
        XCTAssertEqual(TeamDivisionRace.pathRank(try entry(tier: 1), race: nil, raceSettled: false), 10)
    }

    func testWithNoRaceTheServedRankStands() throws {
        XCTAssertEqual(TeamDivisionRace.pathRank(try entry(tier: 4), race: nil, raceSettled: true), 1)
    }

    func testARaceWithoutADivisionColumnLeavesTheServedRank() throws {
        let race = try race(dropDivision: true)
        XCTAssertFalse(race.hasDivision)
        XCTAssertEqual(TeamDivisionRace.pathRank(try entry(tier: 4), race: race, raceSettled: true), 1)
    }

    // MARK: - Settled and tied cells

    func testAClinchedDivisionIsFirst() throws {
        let race = try race(editing: "Detroit Lions",
                            division: ["merged_probability": NSNull(), "state": "won"])
        XCTAssertEqual(TeamDivisionRace.pathRank(try entry(tier: 4), race: race, raceSettled: true), 1)
    }

    func testAnEliminatedTeamGetsNoPlace() throws {
        let race = try race(editing: "Detroit Lions",
                            division: ["merged_probability": 0.0, "state": "eliminated"])
        XCTAssertNil(TeamDivisionRace.pathRank(try entry(tier: 4), race: race, raceSettled: true))
    }

    func testATieSharesThePlace() throws {
        let race = try race(editing: "Minnesota Vikings",
                            division: ["merged_probability": 0.365, "state": "live"])
        XCTAssertEqual(TeamDivisionRace.pathRank(try entry(tier: 4), race: race, raceSettled: true), 1)
    }

    func testARivalBehindDoesNotPushTheTeamDown() throws {
        let race = try race(editing: "Minnesota Vikings",
                            division: ["merged_probability": 0.30, "state": "live"])
        XCTAssertEqual(TeamDivisionRace.pathRank(try entry(tier: 4), race: race, raceSettled: true), 1)
    }

    // MARK: - The page uses it

    func testTheTeamPagePrintsThePathRankThroughTheHelper() throws {
        let root = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()   // BainLuckTests
            .deletingLastPathComponent()   // Bain Luck (project dir)
            .deletingLastPathComponent()   // ios
            .deletingLastPathComponent()   // repo root
        let view = try String(
            contentsOf: root.appendingPathComponent("ios/Bain Luck/Bain Luck/Views/TeamDetailView.swift"),
            encoding: .utf8)
        XCTAssertEqual(view.components(separatedBy: "TeamDivisionRace.pathRank(").count - 1, 1)
        XCTAssertFalse(view.contains("let rank = entry.rank"),
                       "the path row must not print the served rank directly")
        XCTAssertEqual(view.components(separatedBy: "raceSettled = true").count - 1, 1,
                       "the page must mark the race fetch settled exactly once")
    }
}
