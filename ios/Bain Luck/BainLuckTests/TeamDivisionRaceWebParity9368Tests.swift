import XCTest
@testable import Bain_Luck

/// #9368 — the iPhone team page's Division Race and Season Futures, against the
/// served payloads and against the web twin.
///
/// Specimens: `/api/playoffs/nfl` and `/api/teams/philadelphia-eagles` as served
/// on 2026-09-28 ~11:40Z. The grid is trimmed to the NFC East plus one NFC North
/// club, in the fields the race reads; the team list is all 30 served rows as
/// (tier, market name). Before this, the phone printed "NFC East Division Winner
/// 68%" over "Pro Football: NFC East Champion 65%" and the Super Bowl three times.
///
/// SCOPE: the parity half only READS web files (ux's, notice 41). A failure
/// there is a conversation, not an edit.
final class TeamDivisionRaceWebParity9368Tests: XCTestCase {

    // MARK: - Fixtures

    private static let gridJSON = #"""
{
 "league": "nfl",
 "name": "NFL Playoffs 2026-27",
 "season": "2026-27",
 "columns": [
  {
   "key": "make_playoffs",
   "label": "Make Playoffs",
   "order": 1
  },
  {
   "key": "division",
   "label": "Division",
   "order": 2
  },
  {
   "key": "conference",
   "label": "Conference",
   "order": 3
  },
  {
   "key": "championship",
   "label": "Super Bowl",
   "order": 4
  }
 ],
 "teams": [
  {
   "name": "Philadelphia Eagles",
   "short_name": "PHI",
   "team_id": 549,
   "logo_url": "https://a.espncdn.com/i/teamlogos/nfl/500/scoreboard/phi.png",
   "primary_color": "#06424d",
   "secondary_color": "#000000",
   "record": "2-0",
   "conference": "National Football Conference",
   "division": "NFC East",
   "region": null,
   "seed": null,
   "cells": {
    "make_playoffs": {
     "merged_probability": 0.765,
     "state": "live"
    },
    "division": {
     "merged_probability": 0.665,
     "state": "live"
    },
    "championship": {
     "merged_probability": 0.0533,
     "state": "live"
    }
   }
  },
  {
   "name": "Dallas Cowboys",
   "short_name": "DAL",
   "team_id": 552,
   "logo_url": "https://a.espncdn.com/i/teamlogos/nfl/500/scoreboard/dal.png",
   "primary_color": "#002a5c",
   "secondary_color": "#b0b7bc",
   "record": "1-2",
   "conference": "National Football Conference",
   "division": "NFC East",
   "region": null,
   "seed": null,
   "cells": {
    "make_playoffs": {
     "merged_probability": 0.4075,
     "state": "live"
    },
    "division": {
     "merged_probability": 0.2,
     "state": "live"
    },
    "championship": {
     "merged_probability": 0.025,
     "state": "live"
    }
   }
  },
  {
   "name": "Washington Commanders",
   "short_name": "WSH",
   "team_id": 542,
   "logo_url": "https://a.espncdn.com/i/teamlogos/nfl/500/scoreboard/wsh.png",
   "primary_color": "#5a1414",
   "secondary_color": "#ffb612",
   "record": "1-2",
   "conference": "National Football Conference",
   "division": "NFC East",
   "region": null,
   "seed": null,
   "cells": {
    "make_playoffs": {
     "merged_probability": 0.1525,
     "state": "live"
    },
    "division": {
     "merged_probability": 0.0465,
     "state": "live"
    },
    "championship": {
     "merged_probability": 0.0091,
     "state": "live"
    }
   }
  },
  {
   "name": "New York Giants",
   "short_name": "NYG",
   "team_id": 547,
   "logo_url": "https://a.espncdn.com/i/teamlogos/nfl/500/scoreboard/nyg.png",
   "primary_color": "#003c7f",
   "secondary_color": "#c9243f",
   "record": "2-1",
   "conference": "National Football Conference",
   "division": "NFC East",
   "region": null,
   "seed": null,
   "cells": {
    "make_playoffs": {
     "merged_probability": 0.2,
     "state": "live"
    },
    "division": {
     "merged_probability": 0.0875,
     "state": "live"
    },
    "championship": {
     "merged_probability": 0.0065,
     "state": "live"
    }
   }
  },
  {
   "name": "Detroit Lions",
   "short_name": "DET",
   "team_id": 567,
   "logo_url": "https://a.espncdn.com/i/teamlogos/nfl/500/scoreboard/det.png",
   "primary_color": "#0076b6",
   "secondary_color": "#bbbbbb",
   "record": "2-1",
   "conference": "National Football Conference",
   "division": "NFC North",
   "region": null,
   "seed": null,
   "cells": {
    "make_playoffs": {
     "merged_probability": 0.6625,
     "state": "live"
    },
    "division": {
     "merged_probability": 0.325,
     "state": "live"
    },
    "championship": {
     "merged_probability": 0.035,
     "state": "live"
    }
   }
  }
 ],
 "movers": [],
 "team_count": 5,
 "last_updated": null,
 "sources_available": [],
 "championship_market_id": null
}
"""#

    /// (market_tier, market_name) for the 30 futures rows served for the Eagles.
    private static let eaglesFutures: [(Int?, String)] = [
        (4, "Pro Football: Team to Make Postseason"),
        (4, "NFC East Division Winner"),
        (4, "Pro Football: NFC East Champion"),
        (5, "Pro Football: 2026 Regular Season Win Totals"),
        (2, "Pro Football: NFC Team to advance to Divisional Round"),
        (2, "Pro Football Playoffs: NFC #3 Seed"),
        (2, "Pro Football Playoffs: NFC #2 Seed"),
        (2, "Pro Football: Team to advance to NFC Championship Game"),
        (2, "Pro Football Playoffs: NFC #4 Seed"),
        (2, "Pro Football: 2027 NFC Champion "),
        (2, "NFC Championship Winner"),
        (5, "Pro Football Best Regular Season Record"),
        (5, "Fantasy Football: 2026-27 K Points Leader"),
        (5, "Fantasy Football 2026-27: Overall Points Leader"),
        (2, "Pro Football Playoffs: NFC #5 Seed"),
        (5, "Pro Football: 2026-27 Last Unbeaten Team"),
        (1, "Protector of the Year Winner?"),
        (5, "Fantasy Football: 2026-27 Season Top QB"),
        (5, "Fantasy Football: 2026-27 WR Points Leader"),
        (5, "Fantasy Football: 2026-27 RB Points Leader"),
        (5, "Pro Football Receiving Touchdowns Leader"),
        (2, "Pro Football: NFC #1 Seed"),
        (1, "2027 Pro Football Champion"),
        (3, "Pro Football: 2026-27 AP Defensive Player of the Year Winner"),
        (1, "NFL Super Bowl Winner"),
        (1, "Pro Football: 2027 Champion"),
        (5, "Top Fantasy QB"),
        (5, "Fantasy Football: 2026-27 FLEX Points Leader"),
        (5, "Fantasy Football: 2026-27 QB Points Leader"),
        (5, "Fantasy Football: 2026-27 TE Points Leader"),
    ]

    private let eaglesId = 549

    private func decoder() -> JSONDecoder {
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        return d
    }

    private func grid(_ json: String = gridJSON) throws -> ChampionshipGridResponse {
        try decoder().decode(ChampionshipGridResponse.self, from: Data(json.utf8))
    }

    private func futureItem(id: Int, tier: Int?, market: String) throws -> TeamFutureItem {
        let tierJSON = tier.map(String.init) ?? "null"
        let escaped = market.replacingOccurrences(of: "\"", with: "\\\"")
        return try decoder().decode(TeamFutureItem.self, from: Data("""
        {"outcome_id": \(id), "outcome_name": "Philadelphia Eagles", "market_id": \(id),
         "market_name": "\(escaped)", "market_tier": \(tierJSON), "category": "football",
         "source": "kalshi", "probability": 0.5, "probability_change_24h": null,
         "rank": 1, "total_outcomes": 4, "resolution_date": null, "is_winner": false,
         "matched_team": null, "canonical_market_key": null}
        """.utf8))
    }

    private func eaglesList() throws -> [TeamFutureItem] {
        try Self.eaglesFutures.enumerated().map { i, row in
            try futureItem(id: i + 1, tier: row.0, market: row.1)
        }
    }

    /// Edit one team of the served grid — for settled-state and scoping arms.
    private func gridEditing(
        _ name: String, _ edit: (inout [String: Any]) throws -> Void
    ) throws -> ChampionshipGridResponse {
        var obj = try XCTUnwrap(
            JSONSerialization.jsonObject(with: Data(Self.gridJSON.utf8)) as? [String: Any])
        var teams = try XCTUnwrap(obj["teams"] as? [[String: Any]])
        let idx = try XCTUnwrap(teams.firstIndex { ($0["name"] as? String) == name })
        try edit(&teams[idx])
        obj["teams"] = teams
        return try decoder().decode(
            ChampionshipGridResponse.self, from: JSONSerialization.data(withJSONObject: obj))
    }

    private func gridWith(_ name: String, cells: String) throws -> ChampionshipGridResponse {
        try gridEditing(name) { $0["cells"] = try JSONSerialization.jsonObject(with: Data(cells.utf8)) }
    }

    // MARK: - The race, on the served grid

    func testTheEaglesRaceIsTheFourNFCEastClubsInChampionshipOrder() throws {
        let race = try XCTUnwrap(
            TeamDivisionRace.build(grid: grid(), teamId: eaglesId, teamName: "Philadelphia Eagles"))
        XCTAssertEqual(race.divisionLabel, "NFC East")
        XCTAssertEqual(race.season, "2026-27")
        XCTAssertEqual(race.rows.map(\.name), [
            "Philadelphia Eagles", "Dallas Cowboys", "Washington Commanders", "New York Giants",
        ])
        XCTAssertEqual(race.rows.filter(\.isTeam).map(\.name), ["Philadelphia Eagles"])
        XCTAssertTrue(race.hasDivision && race.hasPlayoffs && race.hasChampionship)
    }

    /// One number per stage per club — the numbers the web race printed at 390px
    /// the same minute (67% · 77% · 5.3%).
    func testTheEaglesRowPrintsTheBlendedNumbersWebPrints() throws {
        let race = try XCTUnwrap(
            TeamDivisionRace.build(grid: grid(), teamId: eaglesId, teamName: "Philadelphia Eagles"))
        let me = try XCTUnwrap(race.rows.first(where: \.isTeam))
        XCTAssertEqual(me.division.text, "67%")
        XCTAssertEqual(me.playoffs.text, "77%")
        XCTAssertEqual(me.championship.text, "5.3%")
    }

    /// Labels repeat across conferences; a race that pooled by label alone would
    /// seat AFC clubs in the NFC race.
    func testPeersAreScopedToTheTeamsConference() throws {
        let other = try XCTUnwrap(try grid().teams.first { $0.division == "NFC North" }).name
        let g = try gridEditing(other) {
            $0["division"] = "NFC East"
            $0["conference"] = "American Football Conference"
        }
        XCTAssertEqual(g.teams.filter { $0.division == "NFC East" }.count, 5,
                       "the edit must seat a fifth, other-conference club under the label")
        let race = try XCTUnwrap(
            TeamDivisionRace.build(grid: g, teamId: eaglesId, teamName: "Philadelphia Eagles"))
        XCTAssertEqual(race.rows.count, 4)
        XCTAssertFalse(race.rows.contains { $0.name == other })
    }

    func testTheTeamIsFoundByIdBeforeName() throws {
        let byId = TeamDivisionRace.build(grid: try grid(), teamId: eaglesId, teamName: "somebody else")
        XCTAssertEqual(byId?.rows.first(where: \.isTeam)?.name, "Philadelphia Eagles")
        let byName = TeamDivisionRace.build(grid: try grid(), teamId: -1, teamName: "Philadelphia  Eagles!")
        XCTAssertEqual(byName?.rows.first(where: \.isTeam)?.name, "Philadelphia Eagles")
    }

    func testNoRaceWhenItCannotBeShownHonestly() throws {
        XCTAssertNil(TeamDivisionRace.build(grid: nil, teamId: eaglesId, teamName: "Philadelphia Eagles"))
        XCTAssertNil(TeamDivisionRace.build(grid: try grid(), teamId: -1, teamName: "Nobody FC"))
        // A one-club division is not a race.
        XCTAssertNil(TeamDivisionRace.build(grid: try grid(), teamId: -1, teamName: "Detroit Lions"))
    }

    // MARK: - Settled means settled

    /// A clinched cell has no number; it prints ✓ and sorts as certainty — never
    /// below a longshot still quoting 0.6% (#7522's bug, on the web race).
    func testAClinchedCellPrintsACheckAndSortsFirst() throws {
        let g = try gridWith("New York Giants", cells: #"""
        {"division": {"merged_probability": null, "state": "won"},
         "make_playoffs": {"merged_probability": null, "state": "won"},
         "championship": {"merged_probability": null, "state": "won"}}
        """#)
        let race = try XCTUnwrap(
            TeamDivisionRace.build(grid: g, teamId: eaglesId, teamName: "Philadelphia Eagles"))
        XCTAssertEqual(race.rows.first?.name, "New York Giants")
        XCTAssertEqual(race.rows.first?.championship.text, "✓")
        XCTAssertNil(race.rows.first?.championship.probability)
    }

    func testAnEliminatedCellPrintsACrossNotANumber() throws {
        let g = try gridWith("New York Giants", cells: #"""
        {"division": {"merged_probability": 0.0, "state": "eliminated"},
         "make_playoffs": {"merged_probability": 0.2, "state": "live"},
         "championship": {"merged_probability": 0.0065, "state": "live"}}
        """#)
        let race = try XCTUnwrap(
            TeamDivisionRace.build(grid: g, teamId: eaglesId, teamName: "Philadelphia Eagles"))
        let giants = try XCTUnwrap(race.rows.first { $0.name == "New York Giants" })
        XCTAssertEqual(giants.division.text, "✕")
        XCTAssertNil(giants.division.probability)
    }

    /// A column whose every cell is settled still has a header (#7522: testing
    /// the number alone deleted the column the moment it became certain).
    func testAColumnOfOnlyResultsStillCounts() {
        let won = TeamDivisionRace.Cell(probability: nil, state: .won)
        let gone = TeamDivisionRace.Cell(probability: nil, state: .eliminated)
        let none = TeamDivisionRace.Cell.absent
        XCTAssertTrue(won.hasContent)
        XCTAssertTrue(gone.hasContent)
        XCTAssertFalse(none.hasContent)
        XCTAssertEqual(none.text, "—")
    }

    // MARK: - Which grid

    func testGridSlugs() {
        XCTAssertEqual(TeamDivisionRace.gridSlug(sportKey: "americanfootball_nfl"), "nfl")
        XCTAssertEqual(TeamDivisionRace.gridSlug(sportKey: "soccer_uefa_champs_league"), "champions-league")
        XCTAssertEqual(TeamDivisionRace.gridSlug(sportKey: "baseball_mlb_preseason"), "mlb")
        XCTAssertEqual(TeamDivisionRace.gridSlug(sportKey: "baseball_kbo"), "kbo")
        XCTAssertNil(TeamDivisionRace.gridSlug(sportKey: nil))
        XCTAssertNil(TeamDivisionRace.gridSlug(sportKey: ""))
    }

    // MARK: - Season Futures (the #9368 specimen)

    /// The served 30 rows: with a Championship Path drawn, every per-source copy
    /// of a path or race question leaves the list, and every prop and award stays.
    func testTheEaglesListLosesItsPerSourceDuplicates() throws {
        let all = try eaglesList()
        let shown = TeamDivisionRace.seasonFutures(all, championshipPathDrawn: true)
        let names = Set(shown.map(\.marketName))
        for dup in ["NFC East Division Winner", "Pro Football: NFC East Champion",
                    "NFL Super Bowl Winner", "2027 Pro Football Champion", "Pro Football: 2027 Champion",
                    "Pro Football: 2027 NFC Champion ", "NFC Championship Winner"] {
            XCTAssertFalse(names.contains(dup), dup)
        }
        XCTAssertEqual(shown.count, 14)
        XCTAssertEqual(all.count - shown.count, 16)
        XCTAssertTrue(names.contains("Pro Football: 2026-27 AP Defensive Player of the Year Winner"))
        XCTAssertTrue(names.contains("Pro Football: 2026 Regular Season Win Totals"))
    }

    /// Without a path nothing else on the page answers those questions.
    func testWithoutAChampionshipPathTheListStaysWhole() throws {
        let all = try eaglesList()
        XCTAssertEqual(TeamDivisionRace.seasonFutures(all, championshipPathDrawn: false).count, 30)
    }

    /// Web's `f.market_tier ?? -1`: an untiered row is never a path question.
    func testAnUntieredRowStays() throws {
        let row = try futureItem(id: 1, tier: nil, market: "Something new")
        XCTAssertEqual(TeamDivisionRace.seasonFutures([row], championshipPathDrawn: true).count, 1)
    }

    // MARK: - The view draws what these rules decide

    private func source(_ relative: String) throws -> String {
        let root = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()   // BainLuckTests
            .deletingLastPathComponent()   // Bain Luck (project dir)
            .deletingLastPathComponent()   // ios
            .deletingLastPathComponent()   // repo root
        return try String(contentsOf: root.appendingPathComponent(relative), encoding: .utf8)
    }

    private var teamView: String {
        get throws { try source("ios/Bain Luck/Bain Luck/Views/TeamDetailView.swift") }
    }

    func testTheViewListsTheFilteredFuturesNotTheRawOnes() throws {
        let view = try teamView
        XCTAssertTrue(view.contains("TeamDivisionRace.seasonFutures("))
        XCTAssertTrue(view.contains("ForEach(futures)"))
        XCTAssertFalse(view.contains("ForEach(data.futures)"),
                       "the raw list is the per-source duplicates #9368 removed")
    }

    func testTheViewDrawsTheRace() throws {
        let view = try teamView
        XCTAssertTrue(view.contains("TeamDivisionRace.build(grid:"))
        XCTAssertTrue(view.contains("divisionRaceSection(race)"))
        XCTAssertTrue(view.contains("fetchChampionshipGrid(slug:"))
    }

    // MARK: - Web parity (reads ux's files, never edits them)

    func testWebSkipsTheSameTiers() throws {
        let page = try source("frontend/app/sport/[sport]/[league]/team/[team]/page.tsx")
        XCTAssertTrue(page.contains("championship_path.length > 0"))
        XCTAssertTrue(page.contains("![1, 2, 4].includes(f.market_tier ?? -1)"))
        XCTAssertEqual(TeamDivisionRace.pathTiers, [1, 2, 4])
    }

    func testWebReadsTheSameGridKeysAndPeerRule() throws {
        let web = try source("frontend/lib/teamDivisionRace.ts")
        for key in [TeamDivisionRace.divisionKey, TeamDivisionRace.playoffsKey,
                    TeamDivisionRace.championshipKey] {
            XCTAssertTrue(web.contains("cellOf(t, \"\(key)\")"), key)
        }
        XCTAssertTrue(web.contains("peers.length < 2"))
        XCTAssertTrue(web.contains("t.conference === me.conference"))
    }

    func testTheGridSlugTableMatchesWebEntryForEntry() throws {
        let web = try source("frontend/lib/gridSlug.ts")
        for (key, slug) in TeamDivisionRace.gridSlugMap {
            XCTAssertTrue(web.contains("\(key): \"\(slug)\","), key)
        }
        let body = try XCTUnwrap(web.range(of: "GRID_SLUG_MAP").map { web[$0.upperBound...] })
        let table = body[..<(body.range(of: "};")?.lowerBound ?? body.endIndex)]
        let webEntries = table.split(separator: "\n").filter { $0.contains(": \"") }.count
        XCTAssertEqual(webEntries, TeamDivisionRace.gridSlugMap.count)
        for suffix in TeamDivisionRace.seasonPhaseSuffixes {
            XCTAssertTrue(web.contains("\"\(suffix)\""), suffix)
        }
    }
}
