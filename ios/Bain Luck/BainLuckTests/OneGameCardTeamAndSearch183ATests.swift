import SwiftUI
import UIKit
import XCTest
@testable import Bain_Luck

/// Ruling 183-A / #12616 — one unified `EventCardView` on Team pages (Size S,
/// `compactScheduleStyle: true`, no bottom bar) and in Search results (Size M,
/// with bottom bar), preserving all probability, draw-priced soccer, settled,
/// and authority-stoppage contracts.
@MainActor
final class OneGameCardTeamAndSearch183ATests: XCTestCase {

    private func decode<T: Decodable>(_ type: T.Type, _ json: String) throws -> T {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(T.self, from: Data(json.utf8))
    }

    // MARK: - 1. SearchEventCardAdapter183A.fromSearchResult (Size M)

    func testSearchResultAdapterMapsHeroProbabilityFallbackAndStoppage() throws {
        // #4967: search rows without `current_odds` still serve `hero_probability` /
        // `hero_probability_away`.
        let heroOnly = try decode(SearchEvent.self, """
        {
          "id": 9001,
          "sport": "basketball_nba",
          "home_team": "Boston Celtics",
          "away_team": "New York Knicks",
          "commence_time": "2026-12-01T00:30:00Z",
          "status": "scheduled",
          "hero_probability": 0.64,
          "hero_probability_away": 0.36
        }
        """)
        let adapted = SearchEventCardAdapter183A.fromSearchResult(heroOnly, sportDisplayName: "NBA")
        XCTAssertEqual(adapted.sportName, "NBA")
        XCTAssertEqual(adapted.currentOdds?.homeProbability ?? -1, 0.64, accuracy: 0.0001)
        XCTAssertEqual(adapted.currentOdds?.awayProbability ?? -1, 0.36, accuracy: 0.0001)

        // Finished row does NOT synthesize live `currentOdds` from `hero_probability`.
        let finished = try decode(SearchEvent.self, """
        {
          "id": 9002,
          "sport": "basketball_nba",
          "home_team": "Boston Celtics",
          "away_team": "Milwaukee Bucks",
          "commence_time": "2026-11-10T00:30:00Z",
          "status": "completed",
          "home_score": 114,
          "away_score": 107,
          "hero_probability": 1.0,
          "hero_probability_away": 0.0,
          "opening_odds": {"home_probability": 0.62, "away_probability": 0.38}
        }
        """)
        let adaptedFinished = SearchEventCardAdapter183A.fromSearchResult(finished, sportDisplayName: "NBA")
        XCTAssertNil(adaptedFinished.currentOdds)
        XCTAssertEqual(adaptedFinished.openingOdds?.homeProbability ?? -1, 0.62, accuracy: 0.0001)

        // #9208: `stoppage` surfaces through `espn.period` when `espn` is absent.
        let canceled = try decode(SearchEvent.self, """
        {
          "id": 9003,
          "sport": "baseball_mlb",
          "home_team": "Boston Red Sox",
          "away_team": "Tampa Bay Rays",
          "commence_time": "2026-09-20T23:10:00Z",
          "status": "suspended",
          "stoppage": "Canceled"
        }
        """)
        let adaptedCanceled = SearchEventCardAdapter183A.fromSearchResult(canceled, sportDisplayName: "MLB")
        XCTAssertEqual(adaptedCanceled.espn?.period, "Canceled")
    }

    // MARK: - 2. SearchEventCardAdapter183A.fromTeamScheduleBrief (Size S)

    func testTeamScheduleBriefAdapterOrientsHomeAndAwayAndRespectsSettledAndSoccerRules() throws {
        let celtics = try decode(TeamPageTeam.self, """
        {
          "id": 12,
          "slug": "boston-celtics-nba",
          "name": "Boston Celtics",
          "abbreviation": "BOS",
          "sport_key": "basketball_nba",
          "sport_name": "NBA",
          "primary_color": "#007A33",
          "secondary_color": "#BA9653",
          "record": "10-2"
        }
        """)

        // Away scheduled game: `win_probability: 0.68` is Celtics' (away) chance.
        let awayUpcoming = try decode(SearchEvent.self, """
        {
          "id": 9101,
          "sport_key": "basketball_nba",
          "home_team": "Cleveland Cavaliers",
          "away_team": "Boston Celtics",
          "commence_time": "2026-11-18T00:30:00Z",
          "status": "scheduled",
          "is_home": false,
          "opponent": "Cleveland Cavaliers",
          "win_probability": 0.68,
          "pregame_win_probability": 0.65
        }
        """)
        let adaptedAway = SearchEventCardAdapter183A.fromTeamScheduleBrief(awayUpcoming, team: celtics)
        XCTAssertFalse(adaptedAway.awayReadingIsServerVerified)
        XCTAssertEqual(adaptedAway.feedEvent.currentOdds?.awayProbability ?? -1, 0.68, accuracy: 0.0001)
        XCTAssertEqual(adaptedAway.feedEvent.currentOdds?.homeProbability ?? -1, 0.32, accuracy: 0.0001)
        XCTAssertEqual(adaptedAway.feedEvent.awayTeamData?.primaryColor, "#007A33")
        XCTAssertNil(adaptedAway.feedEvent.homeTeamData)

        // Settled recent game: stale mid-game `win_probability` is ignored (#6444),
        // while `pregame_win_probability` populates `prematchOdds` for PREGAME · FINAL.
        let homeFinished = try decode(SearchEvent.self, """
        {
          "id": 9102,
          "sport_key": "basketball_nba",
          "home_team": "Boston Celtics",
          "away_team": "Philadelphia 76ers",
          "commence_time": "2026-11-11T00:30:00Z",
          "status": "completed",
          "home_score": 118,
          "away_score": 106,
          "is_home": true,
          "opponent": "Philadelphia 76ers",
          "win_probability": 0.963,
          "pregame_win_probability": 0.71
        }
        """)
        let adaptedFinished = SearchEventCardAdapter183A.fromTeamScheduleBrief(homeFinished, team: celtics)
        XCTAssertNil(adaptedFinished.feedEvent.currentOdds, "settled team brief never promotes frozen live blend")
        XCTAssertEqual(adaptedFinished.feedEvent.prematchOdds?.homeProbability ?? -1, 0.71, accuracy: 0.0001)
        XCTAssertEqual(adaptedFinished.feedEvent.prematchOdds?.awayProbability ?? -1, 0.29, accuracy: 0.0001)

        // Draw-priced soccer away brief (#11541): preserves Arsenal's verified away
        // reading without inventing a 1 - p complement for Brighton.
        let arsenal = try decode(TeamPageTeam.self, """
        {
          "id": 44,
          "slug": "arsenal-epl",
          "name": "Arsenal",
          "abbreviation": "ARS",
          "sport_key": "soccer_epl",
          "sport_name": "Premier League",
          "primary_color": "#EF0107",
          "record": "7-3-1"
        }
        """)
        let arsenalAway = try decode(SearchEvent.self, """
        {
          "id": 9103,
          "sport_key": "soccer_epl",
          "home_team": "Brighton",
          "away_team": "Arsenal",
          "commence_time": "2026-11-21T15:00:00Z",
          "status": "scheduled",
          "is_home": false,
          "opponent": "Brighton",
          "win_probability": 0.58,
          "pregame_win_probability": 0.56
        }
        """)
        let adaptedSoccer = SearchEventCardAdapter183A.fromTeamScheduleBrief(arsenalAway, team: arsenal)
        XCTAssertTrue(adaptedSoccer.awayReadingIsServerVerified)
        XCTAssertEqual(adaptedSoccer.feedEvent.currentOdds?.awayProbability ?? -1, 0.58, accuracy: 0.0001)
        XCTAssertNil(adaptedSoccer.feedEvent.currentOdds?.homeProbability, "draw-priced sport never invents 1 - p")
    }

    // MARK: - 3. Hosted 390pt Team page & Search results renders + large text check

    func testTeamPageAndSearchResultsRenderUnifiedGameCardAt390Width() async throws {
        let suiteName = "OneGameCardTeamAndSearch183ATests.\(UUID().uuidString)"
        let defaults = try XCTUnwrap(UserDefaults(suiteName: suiteName))
        defer { defaults.removePersistentDomain(forName: suiteName) }
        let pins = PinManager(
            defaults: defaults,
            serverLoad: { PinsResponse(events: [], futures: []) },
            serverSync: { _, _, _ in }
        )

        let teamPage = try decode(TeamPageResponse.self, """
        {
          "team": {
            "id": 12,
            "slug": "boston-celtics-nba",
            "name": "Boston Celtics",
            "abbreviation": "BOS",
            "sport_key": "basketball_nba",
            "sport_name": "NBA",
            "primary_color": "#007A33",
            "secondary_color": "#BA9653",
            "logo_small": "https://a.espncdn.com/i/teamlogos/nba/500/bos.png",
            "logo_large": "https://a.espncdn.com/i/teamlogos/nba/500/bos.png",
            "record": "10-2"
          },
          "championship_path": [
            {"tier": 1, "label": "NBA Champion", "market_name": "NBA Championship Winner", "market_id": 501, "probability": 0.24, "rank": 1}
          ],
          "upcoming_events": [
            {
              "id": 9201,
              "sport_key": "basketball_nba",
              "sport_name": "NBA",
              "home_team": "Boston Celtics",
              "away_team": "Cleveland Cavaliers",
              "commence_time": "2026-11-19T00:00:00Z",
              "status": "scheduled",
              "is_home": true,
              "opponent": "Cleveland Cavaliers",
              "win_probability": 0.61,
              "pregame_win_probability": 0.61,
              "away_team_data": {"primary_color": "#860038", "abbreviation": "CLE", "record": "12-1", "logo_small": "https://a.espncdn.com/i/teamlogos/nba/500/cle.png"}
            },
            {
              "id": 9202,
              "sport_key": "basketball_nba",
              "sport_name": "NBA",
              "home_team": "Miami Heat",
              "away_team": "Boston Celtics",
              "commence_time": "2026-11-22T01:00:00Z",
              "status": "scheduled",
              "is_home": false,
              "opponent": "Miami Heat",
              "win_probability": 0.68,
              "pregame_win_probability": 0.68,
              "home_team_data": {"primary_color": "#98002E", "abbreviation": "MIA", "record": "6-5", "logo_small": "https://a.espncdn.com/i/teamlogos/nba/500/mia.png"}
            }
          ],
          "recent_events": [
            {
              "id": 9203,
              "sport_key": "basketball_nba",
              "sport_name": "NBA",
              "home_team": "Boston Celtics",
              "away_team": "Milwaukee Bucks",
              "commence_time": "2026-11-10T00:30:00Z",
              "status": "completed",
              "home_score": 113,
              "away_score": 107,
              "is_home": true,
              "opponent": "Milwaukee Bucks",
              "win_probability": 0.94,
              "pregame_win_probability": 0.64,
              "away_team_data": {"primary_color": "#00471B", "abbreviation": "MIL", "record": "4-8", "logo_small": "https://a.espncdn.com/i/teamlogos/nba/500/mil.png"}
            }
          ],
          "futures": []
        }
        """)

        let searchResponse = try decode(SearchResponse.self, """
        {
          "query": "Celtics",
          "teams": [
            {"id": 12, "name": "Boston Celtics", "slug": "boston-celtics-nba", "abbreviation": "BOS", "logo": "https://a.espncdn.com/i/teamlogos/nba/500/bos.png", "record": "10-2", "sport_key": "basketball_nba"}
          ],
          "results": [
            {
              "id": 9301,
              "sport": "basketball_nba",
              "sport_name": "NBA",
              "home_team": "Boston Celtics",
              "away_team": "New York Knicks",
              "commence_time": "2026-11-14T00:30:00Z",
              "status": "live",
              "home_score": 88,
              "away_score": 82,
              "espn": {"period": "Q3", "game_clock": "4:12"},
              "current_odds": {"home_probability": 0.714, "away_probability": 0.286},
              "prematch_odds": {"home_probability": 0.63, "away_probability": 0.37, "home_rendered_percent": 63, "away_rendered_percent": 37, "source": "books"},
              "home_team_data": {"primary_color": "#007A33", "abbreviation": "BOS", "record": "10-2", "logo_small": "https://a.espncdn.com/i/teamlogos/nba/500/bos.png"},
              "away_team_data": {"primary_color": "#006BB6", "abbreviation": "NYK", "record": "7-5", "logo_small": "https://a.espncdn.com/i/teamlogos/nba/500/nyk.png"}
            },
            {
              "id": 9302,
              "sport": "basketball_nba",
              "sport_name": "NBA",
              "home_team": "Boston Celtics",
              "away_team": "Cleveland Cavaliers",
              "commence_time": "2026-11-19T00:00:00Z",
              "status": "scheduled",
              "current_odds": {
                "home_probability": 0.61,
                "away_probability": 0.39,
                "projected_home_score": 116.4,
                "projected_away_score": 111.2
              },
              "home_team_data": {"primary_color": "#007A33", "abbreviation": "BOS", "record": "10-2", "logo_small": "https://a.espncdn.com/i/teamlogos/nba/500/bos.png"},
              "away_team_data": {"primary_color": "#860038", "abbreviation": "CLE", "record": "12-1", "logo_small": "https://a.espncdn.com/i/teamlogos/nba/500/cle.png"}
            },
            {
              "id": 9303,
              "sport": "basketball_nba",
              "sport_name": "NBA",
              "home_team": "Boston Celtics",
              "away_team": "Milwaukee Bucks",
              "commence_time": "2026-11-10T00:30:00Z",
              "status": "completed",
              "home_score": 113,
              "away_score": 107,
              "prematch_odds": {"home_probability": 0.64, "away_probability": 0.36, "home_rendered_percent": 64, "away_rendered_percent": 36, "source": "books"},
              "home_team_data": {"primary_color": "#007A33", "abbreviation": "BOS", "record": "10-2", "logo_small": "https://a.espncdn.com/i/teamlogos/nba/500/bos.png"},
              "away_team_data": {"primary_color": "#00471B", "abbreviation": "MIL", "record": "4-8", "logo_small": "https://a.espncdn.com/i/teamlogos/nba/500/mil.png"}
            }
          ],
          "futures": [],
          "sports": [{"key": "basketball_nba", "name": "NBA", "count": 3}]
        }
        """)

        let teamScreen = NavigationStack {
            TeamDetailView(slug: "boston-celtics-nba", loadedPageForTest: teamPage)
        }
        .environmentObject(pins)
        .environment(\.colorScheme, .light)

        let searchPlace = MacReadingPlace<SearchViewModel>()
        _ = searchPlace.models {
            let vm = SearchViewModel { _, _ in searchResponse }
            vm.query = "Celtics"
            vm.results = searchResponse
            return vm
        }
        let searchScreen = NavigationStack {
            SearchView(macPlace: searchPlace)
        }
        .environmentObject(NavigationCoordinator())
        .environmentObject(pins)
        .environment(\.colorScheme, .light)

        // Verify both full screens mount cleanly at 390x852 (.large and .accessibility2).
        for typeSize in [DynamicTypeSize.large, .accessibility2] {
            let bounds = CGRect(x: 0, y: 0, width: 390, height: 852)

            let hostedTeam = hostForMeasurement(teamScreen, at: typeSize)
            let teamWindow = UIWindow(frame: bounds)
            teamWindow.rootViewController = hostedTeam
            hostedTeam.view.frame = bounds
            teamWindow.isHidden = false
            hostedTeam.view.setNeedsLayout()
            hostedTeam.view.layoutIfNeeded()
            try await Task.sleep(nanoseconds: 80_000_000)
            hostedTeam.view.setNeedsLayout()
            hostedTeam.view.layoutIfNeeded()
            XCTAssertEqual(hostedTeam.view.bounds.width, 390, accuracy: 0.5)
            teamWindow.isHidden = true

            let hostedSearch = hostForMeasurement(searchScreen, at: typeSize)
            let searchWindow = UIWindow(frame: bounds)
            searchWindow.rootViewController = hostedSearch
            hostedSearch.view.frame = bounds
            searchWindow.isHidden = false
            hostedSearch.view.setNeedsLayout()
            hostedSearch.view.layoutIfNeeded()
            try await Task.sleep(nanoseconds: 80_000_000)
            hostedSearch.view.setNeedsLayout()
            hostedSearch.view.layoutIfNeeded()
            XCTAssertEqual(hostedSearch.view.bounds.width, 390, accuracy: 0.5)
            searchWindow.isHidden = true
        }

        // Export 390 px PNG proof artifacts when BAINLUCK_OVERNIGHT6_RENDER_DIR is set.
        if let dirPath = ProcessInfo.processInfo.environment["BAINLUCK_OVERNIGHT6_RENDER_DIR"],
           !dirPath.isEmpty {
            let outDir = URL(fileURLWithPath: dirPath, isDirectory: true)
            try FileManager.default.createDirectory(at: outDir, withIntermediateDirectories: true)

            func snapshotScreen<V: View>(_ view: V, height: CGFloat?, fileName: String) async throws {
                let hosted = hostForMeasurement(view, at: .large)
                let resolvedHeight: CGFloat
                if let height {
                    resolvedHeight = height
                } else {
                    let fitting = hosted.sizeThatFits(in: CGSize(width: 390, height: 3000))
                    resolvedHeight = ceil(fitting.height)
                }
                let bounds = CGRect(x: 0, y: 0, width: 390, height: resolvedHeight)
                let window = UIWindow(frame: bounds)
                window.rootViewController = hosted
                hosted.view.frame = bounds
                window.isHidden = false
                hosted.view.setNeedsLayout()
                hosted.view.layoutIfNeeded()
                try await Task.sleep(nanoseconds: 450_000_000)
                hosted.view.setNeedsLayout()
                hosted.view.layoutIfNeeded()
                let format = UIGraphicsImageRendererFormat()
                format.scale = 3.0
                format.opaque = true
                let image = UIGraphicsImageRenderer(bounds: bounds, format: format).image { _ in
                    hosted.view.drawHierarchy(in: bounds, afterScreenUpdates: true)
                }
                window.isHidden = true
                try XCTUnwrap(image.pngData()).write(to: outDir.appendingPathComponent(fileName))
            }

            try await snapshotScreen(
                teamScreen,
                height: 980,
                fileName: "overnight6-team-page-183a-390x852.png"
            )
            try await snapshotScreen(
                searchScreen,
                height: 920,
                fileName: "overnight6-search-results-183a-390x852.png"
            )

            // Direct Size S (Team schedule) vs Size M (Search results) card sheet at 390 px.
            let teamUpcomingAdapted = SearchEventCardAdapter183A.fromTeamScheduleBrief(
                teamPage.upcomingEvents[0], team: teamPage.team)
            let teamRecentAdapted = SearchEventCardAdapter183A.fromTeamScheduleBrief(
                teamPage.recentEvents[0], team: teamPage.team)
            let searchLiveAdapted = SearchEventCardAdapter183A.fromSearchResult(
                searchResponse.results[0], sportDisplayName: "NBA")
            let searchSchedAdapted = SearchEventCardAdapter183A.fromSearchResult(
                searchResponse.results[1], sportDisplayName: "NBA")

            let comparisonSheet = VStack(alignment: .leading, spacing: 14) {
                Text("183-A · Team Page (Size S, no bottom bar)")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.secondary)
                VStack(spacing: 10) {
                    EventCardView(
                        event: teamUpcomingAdapted.feedEvent,
                        reason: nil,
                        compactScheduleStyle: true,
                        awayReadingIsServerVerified: teamUpcomingAdapted.awayReadingIsServerVerified
                    )
                    .padding(14)
                    .background(Color.white)
                    .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))

                    EventCardView(
                        event: teamRecentAdapted.feedEvent,
                        reason: nil,
                        compactScheduleStyle: true,
                        awayReadingIsServerVerified: teamRecentAdapted.awayReadingIsServerVerified
                    )
                    .padding(14)
                    .background(Color.white)
                    .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
                }

                Text("183-A · Search Results (Size M, with bottom bar)")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.secondary)
                    .padding(.top, 4)
                VStack(spacing: 10) {
                    EventCardView(event: searchLiveAdapted, reason: nil)
                        .padding(14)
                        .background(Color.white)
                        .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))

                    EventCardView(event: searchSchedAdapted, reason: nil)
                        .padding(14)
                        .background(Color.white)
                        .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
                }
            }
            .padding(16)
            .frame(width: 390, alignment: .topLeading)
            .background(Color(white: 0.955))
            .environmentObject(pins)
            .environment(\.colorScheme, .light)

            try await snapshotScreen(
                comparisonSheet,
                height: nil,
                fileName: "overnight6-comparison-183a-390.png"
            )
        }
    }
}
