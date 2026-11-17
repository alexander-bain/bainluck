import SwiftUI
import UIKit
import Vision
import XCTest
@testable import Bain_Luck

/// #12823 (Fable 8:26 PM PT, Mon Nov 16 — 1.0.7 fast cut):
/// 1. Circular player headshots resolved from `team.roster` (including team-outcome
///    player markets like `"Christian Barmore Next Team"`), with team crest fallback.
/// 2. Redundant sport/fantasy/season prefixes (`"Pro Football: 2026-27"`,
///    `"Fantasy Football: 2026-27"`, `"NBA: 2026-27"`) stripped so rows stop cutting off.
/// 3. Zero `"Polymarket"` / `"Kalshi"` venue names on any row face.
@MainActor
final class TeamPageFuturesFastCut12823Tests: XCTestCase {

    private func decodePage(_ json: String) throws -> TeamPageResponse {
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        return try d.decode(TeamPageResponse.self, from: Data(json.utf8))
    }

    private func patriotsPageJSON() -> String {
        """
        {
          "team": {
            "id": 11,
            "slug": "new-england-patriots",
            "name": "New England Patriots",
            "abbreviation": "NE",
            "sport_key": "americanfootball_nfl",
            "sport_name": "NFL",
            "primary_color": "#002a5c",
            "secondary_color": "#c60c30",
            "logo_small": "https://a.espncdn.com/i/teamlogos/nfl/500/scoreboard/ne.png",
            "logo_large": "https://a.espncdn.com/i/teamlogos/nfl/500/scoreboard/ne.png",
            "record": "5-5",
            "roster": [
              {"name": "Drake Maye", "espn_id": "4431452", "headshot": "https://a.espncdn.com/i/headshots/nfl/players/full/4431452.png", "position": "QB"},
              {"name": "Christian Barmore", "espn_id": "4372030", "headshot": "https://a.espncdn.com/i/headshots/nfl/players/full/4372030.png", "position": "DT"},
              {"name": "Eli Raridon", "espn_id": "4870921", "headshot": "https://a.espncdn.com/i/headshots/nfl/players/full/4870921.png", "position": "TE"},
              {"name": "Rhamondre Stevenson", "espn_id": "4569173", "headshot": "https://a.espncdn.com/i/headshots/nfl/players/full/4569173.png", "position": "RB"},
              {"name": "Hunter Henry", "espn_id": "3046439", "headshot": "https://a.espncdn.com/i/headshots/nfl/players/full/3046439.png", "position": "TE"},
              {"name": "A.J. Brown", "espn_id": "4047646", "headshot": "https://a.espncdn.com/i/headshots/nfl/players/full/4047646.png", "position": "WR"}
            ]
          },
          "upcoming_events": [],
          "recent_events": [],
          "championship_path": [],
          "futures": [
            {
              "outcome_id": 239479198,
              "outcome_name": "Drake Maye",
              "market_id": 59385196,
              "market_name": "Fantasy Football: 2026-27 Top 12 Scoring QBs",
              "market_tier": 5,
              "category": "football",
              "source": "polymarket",
              "probability": 0.993,
              "rank": 1,
              "total_outcomes": 50,
              "is_winner": false,
              "matched_team": {"id": 11, "name": "New England Patriots", "logo_small": "https://a.espncdn.com/i/teamlogos/nfl/500/scoreboard/ne.png", "primary_color": "#002a5c"}
            },
            {
              "outcome_id": 262004984,
              "outcome_name": "New England",
              "market_id": 69832272,
              "market_name": "Christian Barmore Next Team",
              "market_tier": 5,
              "category": "football",
              "source": "kalshi",
              "probability": 0.985,
              "rank": 1,
              "total_outcomes": 33,
              "is_winner": false,
              "matched_team": {"id": 11, "name": "New England Patriots", "logo_small": "https://a.espncdn.com/i/teamlogos/nfl/500/scoreboard/ne.png", "primary_color": "#002a5c"}
            },
            {
              "outcome_id": 239956952,
              "outcome_name": "Drake Maye",
              "market_id": 59385197,
              "market_name": "Fantasy Football: 2026-27 Top 5 Scoring QBs",
              "market_tier": 5,
              "category": "football",
              "source": "polymarket",
              "probability": 0.495,
              "rank": 3,
              "total_outcomes": 50,
              "is_winner": false,
              "matched_team": {"id": 11, "name": "New England Patriots", "logo_small": "https://a.espncdn.com/i/teamlogos/nfl/500/scoreboard/ne.png", "primary_color": "#002a5c"}
            },
            {
              "outcome_id": 222298451,
              "outcome_name": "Eli Raridon",
              "market_id": 59693630,
              "market_name": "Top Fantasy Rookie TE",
              "market_tier": 3,
              "category": "football",
              "source": "kalshi",
              "probability": 0.375,
              "rank": 2,
              "total_outcomes": 10,
              "is_winner": false,
              "matched_team": {"id": 11, "name": "New England Patriots", "logo_small": "https://a.espncdn.com/i/teamlogos/nfl/500/scoreboard/ne.png", "primary_color": "#002a5c"}
            },
            {
              "outcome_id": 95102263,
              "outcome_name": "New England Patriots",
              "market_id": 16630438,
              "market_name": "Pro Football: Team to Make Postseason",
              "market_tier": 4,
              "category": "football",
              "source": "polymarket",
              "probability": 0.2275,
              "rank": 20,
              "total_outcomes": 32,
              "is_winner": false,
              "matched_team": {"id": 11, "name": "New England Patriots", "logo_small": "https://a.espncdn.com/i/teamlogos/nfl/500/scoreboard/ne.png", "primary_color": "#002a5c"}
            },
            {
              "outcome_id": 231028212,
              "outcome_name": "New England Patriots",
              "market_id": 59609683,
              "market_name": "Pro Football: 2026 Regular Season Win Totals",
              "market_tier": 5,
              "category": "football",
              "source": "polymarket",
              "probability": 0.15,
              "rank": 23,
              "total_outcomes": 32,
              "is_winner": false,
              "matched_team": {"id": 11, "name": "New England Patriots", "logo_small": "https://a.espncdn.com/i/teamlogos/nfl/500/scoreboard/ne.png", "primary_color": "#002a5c"}
            },
            {
              "outcome_id": 239519039,
              "outcome_name": "Drake Maye",
              "market_id": 59703244,
              "market_name": "Pro Football: 2026-27 400+ Passing Yards in a Game",
              "market_tier": 5,
              "category": "football",
              "source": "polymarket",
              "probability": 0.14,
              "rank": 19,
              "total_outcomes": 32,
              "is_winner": false,
              "matched_team": {"id": 11, "name": "New England Patriots", "logo_small": "https://a.espncdn.com/i/teamlogos/nfl/500/scoreboard/ne.png", "primary_color": "#002a5c"}
            },
            {
              "outcome_id": 239518925,
              "outcome_name": "Rhamondre Stevenson",
              "market_id": 59703242,
              "market_name": "Pro Football: 2026-27 1,000+ Rushing Yards",
              "market_tier": 5,
              "category": "football",
              "source": "polymarket",
              "probability": 0.1265,
              "rank": 19,
              "total_outcomes": 32,
              "is_winner": false,
              "matched_team": {"id": 11, "name": "New England Patriots", "logo_small": "https://a.espncdn.com/i/teamlogos/nfl/500/scoreboard/ne.png", "primary_color": "#002a5c"}
            }
          ]
        }
        """
    }

    func testPrefixStrippingAndHeadshotWithCrestFallback() throws {
        XCTAssertEqual(
            TeamFutureRowPresentation.cleanedMarketCaption("Fantasy Football: 2026-27 Top 12 Scoring QBs"),
            "Top 12 Scoring QBs"
        )
        XCTAssertEqual(
            TeamFutureRowPresentation.cleanedMarketCaption("Pro Football: 2026-27 400+ Passing Yards in a Game"),
            "400+ Passing Yards in a Game"
        )
        XCTAssertEqual(
            TeamFutureRowPresentation.cleanedMarketCaption("Pro Football: 2026 Regular Season Win Totals"),
            "Regular Season Win Totals"
        )
        XCTAssertEqual(
            TeamFutureRowPresentation.cleanedMarketCaption("Pro Football: Team to Make Postseason"),
            "Team to Make Postseason"
        )
        XCTAssertEqual(
            TeamFutureRowPresentation.cleanedMarketCaption("Pro Football Playoffs: AFC #7 Seed"),
            "Playoffs: AFC #7 Seed"
        )
        XCTAssertEqual(
            TeamFutureRowPresentation.cleanedMarketCaption("NBA: 2026-27 Sixth Man of the Year"),
            "Sixth Man of the Year"
        )
        XCTAssertEqual(
            TeamFutureRowPresentation.cleanedMarketCaption("Gold Glove: AL Center Field"),
            "Gold Glove: AL Center Field"
        )

        let page = try decodePage(patriotsPageJSON())
        let rows = page.futures.map { TeamFutureRowPresentation.fastCutRow12823($0, team: page.team) }

        // 1. Drake Maye -> player headshot + stripped caption
        XCTAssertEqual(rows[0].title, "Drake Maye")
        XCTAssertEqual(rows[0].caption, "Top 12 Scoring QBs")
        if case .playerHeadshot(let url, let pos, _, _, _) = rows[0].avatar {
            XCTAssertEqual(url.absoluteString, "https://a.espncdn.com/i/headshots/nfl/players/full/4431452.png")
            XCTAssertEqual(pos, "QB")
        } else {
            XCTFail("Expected playerHeadshot for Drake Maye")
        }

        // 2. Christian Barmore Next Team (outcome "New England") -> Christian Barmore headshot, nil position badge on team title!
        XCTAssertEqual(rows[1].title, "New England")
        XCTAssertEqual(rows[1].caption, "Christian Barmore Next Team")
        if case .playerHeadshot(let url, let pos, _, _, _) = rows[1].avatar {
            XCTAssertEqual(url.absoluteString, "https://a.espncdn.com/i/headshots/nfl/players/full/4372030.png")
            XCTAssertNil(pos)
        } else {
            XCTFail("Expected playerHeadshot for Christian Barmore Next Team")
        }

        // 3. Team-level row ("Team to Make Postseason") -> team crest fallback
        XCTAssertEqual(rows[4].title, "New England Patriots")
        XCTAssertEqual(rows[4].caption, "Team to Make Postseason")
        if case .teamCrest(let url, let abbr, _) = rows[4].avatar {
            XCTAssertEqual(url?.absoluteString, "https://a.espncdn.com/i/teamlogos/nfl/500/scoreboard/ne.png")
            XCTAssertEqual(abbr, "NE")
        } else {
            XCTFail("Expected teamCrest fallback for Team to Make Postseason")
        }

        // 3b. Rhamondre Stevenson -> player headshot + stripped "1,000+ Rushing Yards"
        XCTAssertEqual(rows[7].title, "Rhamondre Stevenson")
        XCTAssertEqual(rows[7].caption, "1,000+ Rushing Yards")
        if case .playerHeadshot(let url, let pos, _, _, _) = rows[7].avatar {
            XCTAssertEqual(url.absoluteString, "https://a.espncdn.com/i/headshots/nfl/players/full/4569173.png")
            XCTAssertEqual(pos, "RB")
        } else {
            XCTFail("Expected playerHeadshot for Rhamondre Stevenson")
        }

        // 4. Source guard: TeamDetailView never prints Polymarket / Kalshi / SourceLabels
        let teamDetailURL = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("Bain Luck/Views/TeamDetailView.swift")
        let src = try String(contentsOf: teamDetailURL, encoding: .utf8)
        XCTAssertFalse(src.contains("SourceLabels.label(for:"), "TeamDetailView must not render venue labels on rows")
    }

    func testMixedStringAndDictRosterAndNonArrayRosterNeverFailTeamPageDecode() throws {
        // 1. Mixed roster from roster_sync.py (ASCII string variant + rich dict + malformed/null entries)
        let mixedJSON = """
        {
          "team": {
            "id": 22,
            "slug": "dallas-mavericks",
            "name": "Dallas Mavericks",
            "abbreviation": "DAL",
            "location": "Dallas",
            "sport_key": "basketball_nba",
            "sport_name": "NBA",
            "primary_color": "#00538C",
            "logo_small": "https://a.espncdn.com/i/teamlogos/nba/500/scoreboard/dal.png",
            "roster": [
              "Luka Doncic",
              {"name": "Luka Dončić", "espn_id": "3945274", "headshot": "https://a.espncdn.com/i/headshots/nba/players/full/3945274.png", "position": "PG"},
              null,
              42,
              {"malformed": true},
              "Jayson Tatum"
            ]
          },
          "upcoming_events": [],
          "recent_events": [],
          "championship_path": [],
          "futures": [
            {
              "outcome_id": 1,
              "outcome_name": "Luka Doncic",
              "market_id": 100,
              "market_name": "NBA: 2026-27 Most Valuable Player",
              "market_tier": 1,
              "category": "basketball",
              "source": "kalshi",
              "probability": 0.28,
              "rank": 2,
              "total_outcomes": 30
            },
            {
              "outcome_id": 2,
              "outcome_name": "Kyrie Irving",
              "market_id": 101,
              "market_name": "NBA: 2026-27 All-Star Selection",
              "market_tier": 3,
              "category": "basketball",
              "source": "polymarket",
              "probability": 0.45,
              "rank": 8,
              "total_outcomes": 40
            },
            {
              "outcome_id": 3,
              "outcome_name": "England",
              "market_id": 102,
              "market_name": "Christian Barmore Next Team",
              "market_tier": 5,
              "category": "football",
              "source": "kalshi",
              "probability": 0.02
            }
          ]
        }
        """
        let mixedPage = try decodePage(mixedJSON)
        XCTAssertEqual(mixedPage.team.rosterMembers.count, 1)
        XCTAssertEqual(mixedPage.team.rosterMembers.first?.name, "Luka Dončić")

        // Diacritic-folded match resolves Luka Dončić's headshot even when outcome is ASCII "Luka Doncic"
        let lukaRow = TeamFutureRowPresentation.fastCutRow12823(mixedPage.futures[0], team: mixedPage.team)
        if case .playerHeadshot(let url, let pos, _, _, _) = lukaRow.avatar {
            XCTAssertEqual(url.absoluteString, "https://a.espncdn.com/i/headshots/nba/players/full/3945274.png")
            XCTAssertEqual(pos, "PG")
        } else {
            XCTFail("Expected playerHeadshot for Luka Doncic from mixed roster")
        }

        // Unmatched player falls back to team crest
        let kyrieRow = TeamFutureRowPresentation.fastCutRow12823(mixedPage.futures[1], team: mixedPage.team)
        if case .teamCrest(let url, let abbr, _) = kyrieRow.avatar {
            XCTAssertEqual(url?.absoluteString, "https://a.espncdn.com/i/teamlogos/nba/500/scoreboard/dal.png")
            XCTAssertEqual(abbr, "DAL")
        } else {
            XCTFail("Expected teamCrest fallback for unmatched player")
        }

        // Partial word ("England" on "New England Patriots") never falsely counts as naming the team
        let patriotsPage = try decodePage(patriotsPageJSON())
        let englandItem = mixedPage.futures[2]
        let englandOnPatriots = TeamFutureRowPresentation.fastCutRow12823(englandItem, team: patriotsPage.team)
        if case .teamCrest = englandOnPatriots.avatar {
            // Expected: "England" does not name "New England Patriots"
        } else {
            XCTFail("Partial word 'England' must not count as naming New England Patriots")
        }

        // 2. Legacy string-only roster AND non-array roster both decode cleanly and fall back to crest
        for rosterPayload in ["[\"Jayson Tatum\", \"Jaylen Brown\"]", "{\"legacy\": true}", "\"unstructured\""] {
            let nonDictJSON = """
            {
              "team": {
                "id": 5,
                "slug": "boston-celtics",
                "name": "Boston Celtics",
                "abbreviation": "BOS",
                "logo_small": "https://a.espncdn.com/i/teamlogos/nba/500/scoreboard/bos.png",
                "roster": \(rosterPayload)
              },
              "upcoming_events": [],
              "recent_events": [],
              "championship_path": [],
              "futures": [
                {
                  "outcome_id": 10,
                  "outcome_name": "Jayson Tatum",
                  "market_id": 200,
                  "market_name": "NBA: 2026-27 MVP",
                  "probability": 0.18
                }
              ]
            }
            """
            let decoded = try decodePage(nonDictJSON)
            XCTAssertTrue(decoded.team.rosterMembers.isEmpty)
            let row = TeamFutureRowPresentation.fastCutRow12823(decoded.futures[0], team: decoded.team)
            if case .teamCrest(_, let abbr, _) = row.avatar {
                XCTAssertEqual(abbr, "BOS")
            } else {
                XCTFail("Expected teamCrest fallback for roster payload \(rosterPayload)")
            }
        }
    }

    func testPatriotsTeamPageRendersWithZeroVenueNamesZeroTruncationAndExports390Sheet() async throws {
        let page = try decodePage(patriotsPageJSON())

        // Pre-fetch real ESPN headshots + Patriots crest when network is available in simulator,
        // falling back to deterministic crisp portraits/crest if offline.
        var preloaded: [URL: Image] = [:]
        let urls: [URL] = [
            URL(string: "https://a.espncdn.com/i/teamlogos/nfl/500/scoreboard/ne.png")!,
            URL(string: "https://a.espncdn.com/i/headshots/nfl/players/full/4431452.png")!,
            URL(string: "https://a.espncdn.com/i/headshots/nfl/players/full/4372030.png")!,
            URL(string: "https://a.espncdn.com/i/headshots/nfl/players/full/4870921.png")!,
            URL(string: "https://a.espncdn.com/i/headshots/nfl/players/full/4569173.png")!,
        ]
        for u in urls {
            if let (data, resp) = try? await URLSession.shared.data(from: u),
               (resp as? HTTPURLResponse)?.statusCode == 200,
               let uiImg = UIImage(data: data) {
                preloaded[u] = Image(uiImage: uiImg)
            }
        }

        let view = NavigationStack {
            TeamDetailView(
                slug: "new-england-patriots",
                loadedPageForTest: page,
                raceForTest: nil,
                preloadedAvatarImagesForTest: preloaded
            )
        }
        .frame(width: 390, height: 960)
        .environment(\.colorScheme, .light)

        let host = hostForMeasurement(view, at: .large)
        host.overrideUserInterfaceStyle = .light
        let targetFrame = CGRect(x: 0, y: 0, width: 390, height: 960)
        let scene = UIApplication.shared.connectedScenes.compactMap({ $0 as? UIWindowScene }).first
        let window: UIWindow = scene.map { UIWindow(windowScene: $0) } ?? UIWindow(frame: targetFrame)
        window.frame = targetFrame
        host.view.frame = targetFrame
        window.overrideUserInterfaceStyle = .light
        window.rootViewController = host
        window.isHidden = false
        defer {
            window.isHidden = true
            window.rootViewController = nil
        }

        let until = Date().addingTimeInterval(0.35)
        repeat {
            host.view.setNeedsLayout()
            host.view.layoutIfNeeded()
            RunLoop.current.run(until: Date().addingTimeInterval(0.03))
        } while Date() < until

        let fmt = UIGraphicsImageRendererFormat()
        fmt.scale = 3.0
        fmt.opaque = true
        let image = UIGraphicsImageRenderer(size: targetFrame.size, format: fmt).image { _ in
            _ = host.view.drawHierarchy(in: targetFrame, afterScreenUpdates: true)
        }

        // Vision OCR verification:
        // - Stripped captions ("Top 12 Scoring QBs", "400+ Passing Yards in a Game", "1,000+ Rushing Yards") read whole!
        // - Zero "Polymarket", "Kalshi", "Pro Football:", "Fantasy Football:", or "…"!
        let req = VNRecognizeTextRequest()
        req.recognitionLevel = .accurate
        req.usesLanguageCorrection = false
        req.minimumTextHeight = 0.0
        try VNImageRequestHandler(cgImage: XCTUnwrap(image.cgImage)).perform([req])
        let lines = (req.results ?? []).compactMap { $0.topCandidates(1).first?.string }
        let joined = lines.joined(separator: " ")

        for forbidden in ["Polymarket", "Kalshi", "Pro Football", "Fantasy Football", "New England DT", "…", "..."] {
            XCTAssertFalse(
                joined.localizedCaseInsensitiveContains(forbidden),
                "Patriots Season Futures must never show '\(forbidden)', got: \(lines)"
            )
        }
        for required in [
            "Drake Maye",
            "Top 12 Scoring QBs",
            "Christian Barmore Next Team",
            "400+ Passing Yards in a Game",
            "Rhamondre Stevenson",
            "1,000+ Rushing Yards",
            "Regular Season Win Totals"
        ] {
            XCTAssertTrue(
                joined.contains(required),
                "Patriots Season Futures must show '\(required)' whole, got: \(lines)"
            )
        }

        if let dir = ProcessInfo.processInfo.environment["EXPORT_TEAM_12823_DIR"], !dir.isEmpty {
            let outURL = URL(fileURLWithPath: dir, isDirectory: true)
            try FileManager.default.createDirectory(at: outURL, withIntermediateDirectories: true)
            try XCTUnwrap(image.pngData()).write(to: outURL.appendingPathComponent("12823-patriots-season-futures-390.png"))
        }
    }
}
