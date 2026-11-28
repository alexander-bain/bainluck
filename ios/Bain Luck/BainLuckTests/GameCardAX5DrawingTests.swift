import Foundation
import SwiftUI
#if canImport(UIKit)
import UIKit
import Vision
#endif
import XCTest
@testable import Bain_Luck

/// Item 3 (Draft Drawing — NOT a merge):
/// Draws `EventCardView` on all four surfaces (`Sports`, `League`, `Team`, `My Stuff`)
/// at `.accessibility5` across `320 pt`, `390 pt`, and `834 pt` iPad (Light; plus `834 pt` Dark),
/// comparing **today** (capped at `17.5/13/20/24 pt`) beside a version where names, scores,
/// headers, and chances **grow** with the reader's setting (`eventCardAllowAX5GrowthDrawing = true`).
@MainActor
final class GameCardAX5DrawingTests: XCTestCase {

    #if os(iOS)

    private nonisolated final class SportsFeedStub: SportsFeedProviding, @unchecked Sendable {
        let feed: FeedResponse
        init(feed: FeedResponse) { self.feed = feed }
        nonisolated func fetchSportsFeed() async throws -> FeedResponse { feed }
        nonisolated func fetchSportsEventBackfill(limit: Int) async throws -> FeedResponse {
            let d = JSONDecoder()
            d.keyDecodingStrategy = .convertFromSnakeCase
            return try d.decode(
                FeedResponse.self,
                from: Data(#"{"items":[],"total":0,"limit":50,"offset":0,"has_more":false}"#.utf8)
            )
        }
        nonisolated func fetchSportsGroupedFeed(limit: Int) async throws -> GroupedFeedResponse {
            let d = JSONDecoder()
            d.keyDecodingStrategy = .convertFromSnakeCase
            return try d.decode(
                GroupedFeedResponse.self,
                from: Data(#"{"feed":[],"total":0,"limit":50,"offset":0}"#.utf8)
            )
        }
    }

    // MARK: - Fixtures (reader-facing sports cards only)

    private func decodeJSON<T: Decodable>(_ type: T.Type, json: String) throws -> T {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(type, from: Data(json.utf8))
    }

    private func isoString(_ date: Date) -> String {
        let fmt = ISO8601DateFormatter()
        fmt.formatOptions = [.withInternetDateTime]
        return fmt.string(from: date)
    }

    private func makeEventTimestamps(now: Date = Date()) -> (live1: String, live2: String, upcoming: String, recent: String) {
        (
            live1: isoString(now.addingTimeInterval(-3600)),
            live2: isoString(now.addingTimeInterval(-2400)),
            upcoming: isoString(now.addingTimeInterval(3 * 3600)),
            recent: isoString(now.addingTimeInterval(-18 * 3600))
        )
    }

    private func makeLiveNFLJSON(commence: String) -> String {
        """
        {
          "id": 9139001,
          "sport": "americanfootball_nfl",
          "sport_name": "NFL",
          "away_team": "Buffalo Bills",
          "home_team": "Kansas City Chiefs",
          "away_team_data": {"team_id": 32, "name": "Buffalo Bills", "short_name": "Bills", "abbreviation": "BUF", "primary_color": "#00338D"},
          "home_team_data": {"team_id": 12, "name": "Kansas City Chiefs", "short_name": "Chiefs", "abbreviation": "KC", "primary_color": "#E31837"},
          "commence_time": "\(commence)",
          "status": "live",
          "away_score": 17,
          "home_score": 21,
          "espn": {"period": "Q3", "game_clock": "4:18"},
          "prematch_odds": {"away_probability": 0.48, "home_probability": 0.52, "away_rendered_percent": 48, "home_rendered_percent": 52},
          "current_odds": {"away_probability": 0.42, "home_probability": 0.58, "away_rendered_percent": 42, "home_rendered_percent": 58}
        }
        """
    }

    private func makeLiveNBAProjectedJSON(commence: String) -> String {
        """
        {
          "id": 9139002,
          "sport": "basketball_nba",
          "sport_name": "NBA",
          "away_team": "Minnesota Timberwolves",
          "home_team": "Boston Celtics",
          "away_team_data": {"team_id": 16, "name": "Minnesota Timberwolves", "short_name": "Timberwolves", "abbreviation": "MIN", "primary_color": "#0C2340"},
          "home_team_data": {"team_id": 2, "name": "Boston Celtics", "short_name": "Celtics", "abbreviation": "BOS", "primary_color": "#007A33"},
          "commence_time": "\(commence)",
          "status": "live",
          "away_score": 78,
          "home_score": 84,
          "espn": {"period": "Q3", "game_clock": "5:12"},
          "prematch_odds": {"away_probability": 0.39, "home_probability": 0.61, "away_rendered_percent": 39, "home_rendered_percent": 61},
          "current_odds": {"away_probability": 0.36, "home_probability": 0.64, "projected_away_score": 109.0, "projected_home_score": 114.0}
        }
        """
    }

    private func makeUpcomingNFLJSON(commence: String) -> String {
        """
        {
          "id": 9139003,
          "sport": "americanfootball_nfl",
          "sport_name": "NFL",
          "away_team": "Baltimore Ravens",
          "home_team": "Cincinnati Bengals",
          "away_team_data": {"team_id": 33, "name": "Baltimore Ravens", "short_name": "Ravens", "abbreviation": "BAL", "primary_color": "#241773"},
          "home_team_data": {"team_id": 4, "name": "Cincinnati Bengals", "short_name": "Bengals", "abbreviation": "CIN", "primary_color": "#FB4F14"},
          "commence_time": "\(commence)",
          "status": "scheduled",
          "pregame_projection": {"away": 27, "home": 23},
          "current_odds": {"away_probability": 0.61, "home_probability": 0.39, "away_rendered_percent": 61, "home_rendered_percent": 39}
        }
        """
    }

    private func makeRecentNFLJSON(commence: String) -> String {
        """
        {
          "id": 9139004,
          "sport": "americanfootball_nfl",
          "sport_name": "NFL",
          "away_team": "Philadelphia Eagles",
          "home_team": "Dallas Cowboys",
          "away_team_data": {"team_id": 21, "name": "Philadelphia Eagles", "short_name": "Eagles", "abbreviation": "PHI", "primary_color": "#004C54"},
          "home_team_data": {"team_id": 6, "name": "Dallas Cowboys", "short_name": "Cowboys", "abbreviation": "DAL", "primary_color": "#041E42"},
          "commence_time": "\(commence)",
          "status": "completed",
          "away_score": 27,
          "home_score": 24,
          "prematch_odds": {"away_probability": 0.54, "home_probability": 0.46, "away_rendered_percent": 54, "home_rendered_percent": 46}
        }
        """
    }

    private func makeSportsFeed(times: (live1: String, live2: String, upcoming: String, recent: String)) throws -> FeedResponse {
        try decodeJSON(FeedResponse.self, json: """
        {
          "items": [
            {"type": "event", "score": 98, "data": \(makeLiveNFLJSON(commence: times.live1))},
            {"type": "event", "score": 95, "data": \(makeLiveNBAProjectedJSON(commence: times.live2))},
            {"type": "event", "score": 90, "data": \(makeUpcomingNFLJSON(commence: times.upcoming))}
          ],
          "total": 3,
          "limit": 50,
          "offset": 0,
          "has_more": false
        }
        """)
    }

    private func makeLeagueFixtures(now: Date, times: (live1: String, live2: String, upcoming: String, recent: String)) throws -> (ChampionshipGridResponse, LeagueMarketsResponse) {
        let grid = try decodeJSON(ChampionshipGridResponse.self, json: """
        {
          "league": "americanfootball_nfl",
          "name": "NFL",
          "season": "Season 2026-27",
          "columns": [],
          "teams": [],
          "movers": [],
          "team_count": 0,
          "sources_available": ["kalshi", "polymarket"]
        }
        """)
        let markets = try decodeJSON(LeagueMarketsResponse.self, json: """
        {
          "sport_key": "americanfootball_nfl",
          "sections": {},
          "total_markets": 0,
          "upcoming_games": [
            \(makeLiveNFLJSON(commence: times.live1)),
            \(makeUpcomingNFLJSON(commence: times.upcoming))
          ],
          "recent_results": [
            \(makeRecentNFLJSON(commence: times.recent))
          ]
        }
        """)
        _ = now
        return (grid, markets)
    }

    private func makeTeamPage(times: (live1: String, live2: String, upcoming: String, recent: String)) throws -> TeamPageResponse {
        try decodeJSON(TeamPageResponse.self, json: """
        {
          "team": {
            "id": 12,
            "slug": "kansas-city-chiefs",
            "name": "Kansas City Chiefs",
            "abbreviation": "KC",
            "location": "Kansas City",
            "sport_key": "americanfootball_nfl",
            "sport_name": "NFL",
            "primary_color": "#E31837",
            "secondary_color": "#FFB81C",
            "record": "9-2"
          },
          "championship_path": [],
          "upcoming_events": [
            {
              "id": 9139010,
              "sport": "americanfootball_nfl",
              "sport_name": "NFL",
              "away_team": "Buffalo Bills",
              "home_team": "Kansas City Chiefs",
              "commence_time": "\(times.upcoming)",
              "status": "scheduled",
              "is_home": true,
              "win_probability": 0.58
            },
            {
              "id": 9139011,
              "sport": "americanfootball_nfl",
              "sport_name": "NFL",
              "away_team": "Kansas City Chiefs",
              "home_team": "Baltimore Ravens",
              "commence_time": "\(times.upcoming)",
              "status": "scheduled",
              "is_home": false,
              "win_probability": 0.56
            }
          ],
          "recent_events": [
            {
              "id": 9139012,
              "sport": "americanfootball_nfl",
              "sport_name": "NFL",
              "away_team": "Kansas City Chiefs",
              "home_team": "Denver Broncos",
              "commence_time": "\(times.recent)",
              "status": "completed",
              "is_home": false,
              "away_score": 28,
              "home_score": 20,
              "pregame_win_probability": 0.63
            }
          ],
          "futures": []
        }
        """)
    }

    private func makeMyStuffSnapshot(times: (live1: String, live2: String, upcoming: String, recent: String)) throws -> MyStuffLandingViewModel295A.PreloadedSnapshot {
        let liveNFL = try decodeJSON(FeedEventData.self, json: makeLiveNFLJSON(commence: times.live1))
        let nextNFL = try decodeJSON(FeedEventData.self, json: makeUpcomingNFLJSON(commence: times.upcoming))
        let movedNBA = try decodeJSON(FeedEventData.self, json: makeLiveNBAProjectedJSON(commence: times.live2))
        return MyStuffLandingViewModel295A.PreloadedSnapshot(
            liveEvents: [(liveNFL, false)],
            nextEvents: [(nextNFL, false)],
            nextMarkets: [],
            movedEntries: [
                MyStuffMovedEntry295A(
                    id: "moved-9139002",
                    movementSummary: "Minnesota Timberwolves rose from 28% to 36%",
                    magnitudePoints: 8,
                    payload: .event(movedNBA, awayVerified: false)
                )
            ],
            discoverItems: []
        )
    }

    // MARK: - Simulator Rendering + Vision OCR

    private func renderFixedViewport<V: View>(
        _ view: V,
        width: CGFloat,
        height: CGFloat,
        colorScheme: ColorScheme,
        allowGrowth: Bool
    ) -> UIImage {
        let uiStyle: UIUserInterfaceStyle = colorScheme == .dark ? .dark : .light
        let wrapped = view
            .environment(\.colorScheme, colorScheme)
            .environment(\.dynamicTypeSize, .accessibility5)
            .environment(\.horizontalSizeClass, width >= 700 ? .regular : .compact)
            .environment(\.eventCardAllowAX5GrowthDrawing, allowGrowth)
            .frame(width: width, height: height)
            .clipped()

        let host = hostForMeasurement(wrapped, at: .accessibility5)
        host.safeAreaRegions = []
        host.overrideUserInterfaceStyle = uiStyle
        host.additionalSafeAreaInsets = .zero
        host.view.insetsLayoutMarginsFromSafeArea = false
        host.traitOverrides.horizontalSizeClass = width >= 700 ? .regular : .compact
        host.traitOverrides.preferredContentSizeCategory = .accessibilityExtraExtraExtraLarge
        host.view.traitOverrides.preferredContentSizeCategory = .accessibilityExtraExtraExtraLarge

        let bounds = CGRect(x: 0, y: 0, width: width, height: height)
        let scene = UIApplication.shared.connectedScenes.compactMap { $0 as? UIWindowScene }.first
        let window: UIWindow = scene.map { UIWindow(windowScene: $0) } ?? UIWindow(frame: bounds)
        window.frame = bounds
        window.overrideUserInterfaceStyle = uiStyle
        window.rootViewController = host
        window.isHidden = false
        defer {
            window.isHidden = true
            window.rootViewController = nil
        }

        host.view.frame = bounds
        host.view.backgroundColor = colorScheme == .dark ? .black : .systemGroupedBackground
        for _ in 0..<8 {
            host.view.setNeedsLayout()
            host.view.layoutIfNeeded()
            RunLoop.current.run(until: Date().addingTimeInterval(0.04))
        }

        let fmt = UIGraphicsImageRendererFormat()
        fmt.scale = 1.5
        fmt.opaque = true
        return UIGraphicsImageRenderer(size: bounds.size, format: fmt).image { _ in
            _ = window.drawHierarchy(in: bounds, afterScreenUpdates: true)
        }
    }

    private func ocrObservations(in image: UIImage) throws -> [(text: String, minX: CGFloat, maxX: CGFloat, minY: CGFloat, heightPt: CGFloat)] {
        let cg = try XCTUnwrap(image.cgImage)
        let req = VNRecognizeTextRequest()
        req.recognitionLevel = .accurate
        req.usesLanguageCorrection = false
        try VNImageRequestHandler(cgImage: cg, options: [:]).perform([req])
        return (req.results ?? []).compactMap { obs in
            guard let top = obs.topCandidates(1).first?.string else { return nil }
            let box = obs.boundingBox
            return (
                text: top,
                minX: box.minX * image.size.width,
                maxX: box.maxX * image.size.width,
                minY: box.minY * image.size.height,
                heightPt: box.height * image.size.height
            )
        }
    }

    private func maybeSave(_ image: UIImage, name: String) throws {
        guard let dir = ProcessInfo.processInfo.environment["GAMECARD_AX5_DRAWING_DIR"], !dir.isEmpty else { return }
        try FileManager.default.createDirectory(atPath: dir, withIntermediateDirectories: true)
        try XCTUnwrap(image.pngData()).write(
            to: URL(fileURLWithPath: dir).appendingPathComponent("\(name).png"),
            options: .atomic
        )
    }

    // MARK: - Capture + Breakage Diagnostic Test

    func testDrawTodayVsGrowingGameCardsAcrossFourSurfaces() async throws {
        let now = Date()
        let times = makeEventTimestamps(now: now)
        let sportsFeed = try makeSportsFeed(times: times)
        let (leagueGrid, leagueMarkets) = try makeLeagueFixtures(now: now, times: times)
        let teamPage = try makeTeamPage(times: times)
        let myStuffSnapshot = try makeMyStuffSnapshot(times: times)

        let suiteName = "gamecard-ax5-\(UUID().uuidString)"
        let defaults = UserDefaults(suiteName: suiteName)!
        defer { UserDefaults.standard.removePersistentDomain(forName: suiteName) }
        let pinManager = PinManager(defaults: defaults, allowLegacyGuestPins: false)
        let navCoordinator = NavigationCoordinator()
        let authManager = AuthManager(restoreOnInit: false)
        authManager.user = nil
        let followManager = FollowManager295A(defaults: defaults)
        let alertsPrompt = GameAlertsPromptController295A(defaults: defaults, requestPermissionHandler: {})

        let viewports: [(width: CGFloat, scheme: ColorScheme, tag: String)] = [
            (320, .light, "320_light"),
            (390, .light, "390_light"),
            (834, .light, "834_light"),
            (834, .dark, "834_dark"),
        ]

        let modes: [(allowGrowth: Bool, tag: String)] = [
            (false, "today"),
            (true, "growing"),
        ]

        // 1. Sports (FeedView)
        let sportsVM = FeedViewModel(client: SportsFeedStub(feed: sportsFeed), telemetry: nil, autoRefreshEnabled: false)
        await sportsVM.startLoad()
        for vp in viewports {
            let h: CGFloat = vp.width >= 700 ? 1550 : (vp.width <= 320 ? 1850 : 1700)
            for mode in modes {
                let img = renderFixedViewport(
                    FeedView(viewModel: sportsVM)
                        .environmentObject(pinManager)
                        .environmentObject(navCoordinator)
                        .environmentObject(authManager)
                        .environment(\.followManager295A, followManager)
                        .environment(\.gameAlertsPrompt295A, alertsPrompt),
                    width: vp.width,
                    height: h,
                    colorScheme: vp.scheme,
                    allowGrowth: mode.allowGrowth
                )
                try maybeSave(img, name: "sports_\(vp.tag)_\(mode.tag)")
                let obs = try ocrObservations(in: img)
                XCTAssertFalse(obs.isEmpty, "sports_\(vp.tag)_\(mode.tag): blank OCR")
                let flat = obs.map(\.text).joined(separator: " | ")
                let clipped = obs.filter { $0.text.contains("\u{2026}") || $0.text.contains("...") || $0.text.hasSuffix("-") }.map(\.text)
                print("GAMECARD_AX5_DIAG sports \(vp.tag) \(mode.tag) lines=\(obs.count) clipped=\(clipped) ocr=\(flat)")
            }
        }

        // 2. League (LeagueGridView)
        let leagueVM = LeagueGridViewModel(
            slug: "nfl",
            preloadedGrid: leagueGrid,
            preloadedMarkets: leagueMarkets,
            clock: { now }
        )
        for vp in viewports {
            let h: CGFloat = vp.width >= 700 ? 1550 : (vp.width <= 320 ? 1900 : 1750)
            for mode in modes {
                let img = renderFixedViewport(
                    NavigationStack {
                        LeagueGridView(slug: "nfl", preloadedViewModel: leagueVM)
                    }
                    .environmentObject(pinManager)
                    .environmentObject(navCoordinator)
                    .environmentObject(authManager)
                    .environment(\.followManager295A, followManager)
                    .environment(\.gameAlertsPrompt295A, alertsPrompt),
                    width: vp.width,
                    height: h,
                    colorScheme: vp.scheme,
                    allowGrowth: mode.allowGrowth
                )
                try maybeSave(img, name: "league_\(vp.tag)_\(mode.tag)")
                let obs = try ocrObservations(in: img)
                XCTAssertFalse(obs.isEmpty, "league_\(vp.tag)_\(mode.tag): blank OCR")
                let flat = obs.map(\.text).joined(separator: " | ")
                let clipped = obs.filter { $0.text.contains("\u{2026}") || $0.text.contains("...") || $0.text.hasSuffix("-") }.map(\.text)
                print("GAMECARD_AX5_DIAG league \(vp.tag) \(mode.tag) lines=\(obs.count) clipped=\(clipped) ocr=\(flat)")
            }
        }

        // 3. Team (TeamDetailView, Size S compactScheduleStyle: true)
        for vp in viewports {
            let h: CGFloat = vp.width >= 700 ? 1550 : (vp.width <= 320 ? 1900 : 1750)
            for mode in modes {
                let img = renderFixedViewport(
                    NavigationStack {
                        TeamDetailView(slug: "kansas-city-chiefs", loadedPageForTest: teamPage)
                            .navigationBarTitleDisplayMode(.inline)
                    }
                    .environmentObject(pinManager)
                    .environmentObject(navCoordinator)
                    .environmentObject(authManager)
                    .environment(\.followManager295A, followManager)
                    .environment(\.gameAlertsPrompt295A, alertsPrompt),
                    width: vp.width,
                    height: h,
                    colorScheme: vp.scheme,
                    allowGrowth: mode.allowGrowth
                )
                try maybeSave(img, name: "team_\(vp.tag)_\(mode.tag)")
                let obs = try ocrObservations(in: img)
                XCTAssertFalse(obs.isEmpty, "team_\(vp.tag)_\(mode.tag): blank OCR")
                let flat = obs.map(\.text).joined(separator: " | ")
                let clipped = obs.filter { $0.text.contains("\u{2026}") || $0.text.contains("...") || $0.text.hasSuffix("-") }.map(\.text)
                print("GAMECARD_AX5_DIAG team \(vp.tag) \(mode.tag) lines=\(obs.count) clipped=\(clipped) ocr=\(flat)")
            }
        }

        // 4. My Stuff (MyStuffLandingView295A)
        for vp in viewports {
            let h: CGFloat = vp.width >= 700 ? 1550 : (vp.width <= 320 ? 1900 : 1750)
            for mode in modes {
                let img = renderFixedViewport(
                    NavigationStack {
                        MyStuffLandingView295A(
                            landingVM: MyStuffLandingViewModel295A(preloaded: myStuffSnapshot),
                            path: .constant(NavigationPath()),
                            onOpenDiscover: {},
                            onManagePins: {},
                            onRefresh: {}
                        )
                        .navigationTitle("My Stuff")
                        .navigationBarTitleDisplayMode(.large)
                    }
                    .environmentObject(pinManager)
                    .environmentObject(navCoordinator)
                    .environmentObject(authManager)
                    .environment(\.followManager295A, followManager)
                    .environment(\.gameAlertsPrompt295A, alertsPrompt),
                    width: vp.width,
                    height: h,
                    colorScheme: vp.scheme,
                    allowGrowth: mode.allowGrowth
                )
                try maybeSave(img, name: "mystuff_\(vp.tag)_\(mode.tag)")
                let obs = try ocrObservations(in: img)
                XCTAssertFalse(obs.isEmpty, "mystuff_\(vp.tag)_\(mode.tag): blank OCR")
                let flat = obs.map(\.text).joined(separator: " | ")
                let clipped = obs.filter { $0.text.contains("\u{2026}") || $0.text.contains("...") || $0.text.hasSuffix("-") }.map(\.text)
                print("GAMECARD_AX5_DIAG mystuff \(vp.tag) \(mode.tag) lines=\(obs.count) clipped=\(clipped) ocr=\(flat)")
            }
        }
    }

    #endif
}
