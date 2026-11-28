import Foundation
import SwiftUI
#if canImport(UIKit)
import UIKit
import Vision
#endif
import XCTest
@testable import Bain_Luck

/// Item 2 (PILLAR: FORMATTING):
/// Verifies at `.accessibility5` across `320 pt` and `390 pt` (Light & Dark) that the
/// `"Upcoming"` (and sibling band) section headers never break mid-word or hyphenate
/// (`Up-com-ing`, `Upcom-ing`, `Happen-ed`, etc.) on:
/// 1. League (`LeagueGridView`)
/// 2. Sports (`FeedView`)
/// 3. Team (`TeamDetailView`)
/// 4. My Stuff (`MyStuffView` team feed + `MyStuffLandingView295A`)
@MainActor
final class SectionHeaderAX5NoWordBreakTests: XCTestCase {

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

    private nonisolated final class MyStuffFeedStub: MyStuffFeedProviding, @unchecked Sendable {
        let feed: FeedResponse
        init(feed: FeedResponse) { self.feed = feed }
        nonisolated func fetchMyTeamsFeed() async throws -> FeedResponse { feed }
        nonisolated func fetchMyTeamFuturesSection(limit: Int) async throws -> TeamFuturesResponse {
            let d = JSONDecoder()
            d.keyDecodingStrategy = .convertFromSnakeCase
            return try d.decode(
                TeamFuturesResponse.self,
                from: Data(#"{"items":[],"team_ids":[],"total_count":0}"#.utf8)
            )
        }
    }

    private func decodeJSON<T: Decodable>(_ type: T.Type, json: String) throws -> T {
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        return try d.decode(type, from: Data(json.utf8))
    }

    private func isoString(_ date: Date) -> String {
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime]
        return f.string(from: date)
    }

    private func makeUpcomingNFLJSON(commence: String) -> String {
        """
        {
          "id": 9239001,
          "sport": "americanfootball_nfl",
          "sport_name": "NFL",
          "away_team": "Baltimore Ravens",
          "home_team": "Cincinnati Bengals",
          "away_team_data": {"team_id": 33, "name": "Baltimore Ravens", "short_name": "Ravens", "abbreviation": "BAL", "primary_color": "#241773"},
          "home_team_data": {"team_id": 4, "name": "Cincinnati Bengals", "short_name": "Bengals", "abbreviation": "CIN", "primary_color": "#FB4F14"},
          "commence_time": "\(commence)",
          "status": "scheduled",
          "current_odds": {"away_probability": 0.61, "home_probability": 0.39, "away_rendered_percent": 61, "home_rendered_percent": 39}
        }
        """
    }

    private func makeRecentNFLJSON(commence: String) -> String {
        """
        {
          "id": 9239002,
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

    private func render<V: View>(
        _ view: V,
        into window: UIWindow,
        width: CGFloat,
        height: CGFloat,
        colorScheme: ColorScheme
    ) -> UIImage {
        let uiStyle: UIUserInterfaceStyle = colorScheme == .dark ? .dark : .light
        let wrapped = view
            .environment(\.colorScheme, colorScheme)
            .environment(\.dynamicTypeSize, .accessibility5)
            .environment(\.horizontalSizeClass, .compact)
            .frame(width: width, height: height)
            .clipped()

        let host = hostForMeasurement(wrapped, at: .accessibility5)
        host.safeAreaRegions = []
        host.overrideUserInterfaceStyle = uiStyle
        host.additionalSafeAreaInsets = .zero
        host.view.insetsLayoutMarginsFromSafeArea = false
        host.traitOverrides.horizontalSizeClass = .compact
        host.traitOverrides.preferredContentSizeCategory = .accessibilityExtraExtraExtraLarge
        host.view.traitOverrides.preferredContentSizeCategory = .accessibilityExtraExtraExtraLarge

        let bounds = CGRect(x: 0, y: 0, width: width, height: height)
        window.frame = bounds
        window.overrideUserInterfaceStyle = uiStyle
        window.rootViewController = host
        window.isHidden = false

        host.view.frame = bounds
        host.view.backgroundColor = colorScheme == .dark ? .black : .systemGroupedBackground
        for _ in 0..<4 {
            host.view.setNeedsLayout()
            host.view.layoutIfNeeded()
            RunLoop.current.run(until: Date().addingTimeInterval(0.03))
        }

        let fmt = UIGraphicsImageRendererFormat()
        fmt.scale = 1.5
        fmt.opaque = true
        return UIGraphicsImageRenderer(size: bounds.size, format: fmt).image { _ in
            _ = window.drawHierarchy(in: bounds, afterScreenUpdates: true)
        }
    }

    private func ocrTexts(in image: UIImage) throws -> [String] {
        let cg = try XCTUnwrap(image.cgImage)
        let req = VNRecognizeTextRequest()
        req.recognitionLevel = .accurate
        req.usesLanguageCorrection = false
        try VNImageRequestHandler(cgImage: cg, options: [:]).perform([req])
        return (req.results ?? []).compactMap { $0.topCandidates(1).first?.string }
    }

    private func maybeSave(_ image: UIImage, name: String) throws {
        guard let dir = ProcessInfo.processInfo.environment["SECTION_HEADER_AX5_CAPTURE_DIR"], !dir.isEmpty else { return }
        try FileManager.default.createDirectory(atPath: dir, withIntermediateDirectories: true)
        try XCTUnwrap(image.pngData()).write(
            to: URL(fileURLWithPath: dir).appendingPathComponent("\(name).png"),
            options: .atomic
        )
    }

    private func assertIntactUpcomingHeader(
        ocr: [String],
        surface: String,
        allowBeforeFail: Bool,
        expectedToken: String = "Upcoming",
        checkJustHappened: Bool = false
    ) {
        let joined = ocr.joined(separator: " | ")
        print("SECTION_HEADER_AX5_OCR \(surface) lines=\(ocr.count) text=\(joined)")
        guard !allowBeforeFail else { return }
        let brokenMarkers = ["Up-", "Upcom-", "com-", "Happen-", "Hap-", "Upco…", "Upc…", "\u{2026}"]
        for marker in brokenMarkers {
            XCTAssertFalse(
                ocr.contains { $0.contains(marker) },
                "\(surface): header broke mid-word or truncated (`\(marker)`) in OCR: \(joined)"
            )
        }
        XCTAssertTrue(
            ocr.contains { $0.localizedCaseInsensitiveContains(expectedToken) },
            "\(surface): expected intact '\(expectedToken)' header in OCR: \(joined)"
        )
        if checkJustHappened {
            XCTAssertTrue(
                ocr.contains { $0.localizedCaseInsensitiveContains("Happened") },
                "\(surface): expected intact 'Happened' in Just Happened header OCR: \(joined)"
            )
        }
    }

    func testUpcomingHeaderNoMidWordBreakAt320And390AX5AcrossSurfaces() async throws {
        let allowBeforeFail = ProcessInfo.processInfo.environment["SECTION_HEADER_AX5_ALLOW_BEFORE_FAIL"] == "1"
        let now = Date()
        let upcomingTime = isoString(now.addingTimeInterval(3 * 3600))
        let recentTime = isoString(now.addingTimeInterval(-18 * 3600))

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
        let leagueMarkets = try decodeJSON(LeagueMarketsResponse.self, json: """
        {
          "sport_key": "americanfootball_nfl",
          "sections": {},
          "total_markets": 0,
          "upcoming_games": [\(makeUpcomingNFLJSON(commence: upcomingTime))],
          "recent_results": [\(makeRecentNFLJSON(commence: recentTime))]
        }
        """)
        let feed = try decodeJSON(FeedResponse.self, json: """
        {
          "items": [
            {"type": "event", "score": 95, "data": \(makeUpcomingNFLJSON(commence: upcomingTime))},
            {"type": "event", "score": 90, "data": \(makeRecentNFLJSON(commence: recentTime))}
          ],
          "total": 2,
          "limit": 50,
          "offset": 0,
          "has_more": false
        }
        """)
        let teamPage = try decodeJSON(TeamPageResponse.self, json: """
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
              "id": 9239010,
              "sport": "americanfootball_nfl",
              "sport_name": "NFL",
              "away_team": "Baltimore Ravens",
              "home_team": "Kansas City Chiefs",
              "commence_time": "\(upcomingTime)",
              "status": "scheduled",
              "is_home": true,
              "win_probability": 0.58
            }
          ],
          "recent_events": [
            {
              "id": 9239011,
              "sport": "americanfootball_nfl",
              "sport_name": "NFL",
              "away_team": "Kansas City Chiefs",
              "home_team": "Denver Broncos",
              "commence_time": "\(recentTime)",
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

        let suiteName = "section-header-ax5-\(UUID().uuidString)"
        let defaults = UserDefaults(suiteName: suiteName)!
        defer { UserDefaults.standard.removePersistentDomain(forName: suiteName) }
        let pinManager = PinManager(defaults: defaults, allowLegacyGuestPins: false)
        let navCoordinator = NavigationCoordinator()
        let authManager = AuthManager(restoreOnInit: false)
        authManager.user = AuthUser(
            id: 42,
            email: "reader@example.com",
            displayName: "Reader",
            photoUrl: nil,
            onboardingCompleted: true,
            createdAt: nil
        )
        let followManager = FollowManager295A(defaults: defaults)
        let alertsPrompt = GameAlertsPromptController295A(defaults: defaults, requestPermissionHandler: {})
        let checklistStore = FirstRunChecklistStore364A(defaults: defaults)
        checklistStore.dismissFromMyStuff()

        let myStuffFeed = try decodeJSON(FeedResponse.self, json: """
        {
          "items": [
            {"type": "event", "score": 95, "data": \(makeUpcomingNFLJSON(commence: upcomingTime))}
          ],
          "total": 1,
          "limit": 50,
          "offset": 0,
          "has_more": false
        }
        """)
        let sportsVM = FeedViewModel(client: SportsFeedStub(feed: feed), telemetry: nil, autoRefreshEnabled: false)
        await sportsVM.startLoad()
        let myStuffVM = MyStuffViewModel(client: MyStuffFeedStub(feed: myStuffFeed), telemetry: nil, autoRefreshEnabled: false)
        await myStuffVM.startLoad()

        let leagueVM = LeagueGridViewModel(
            slug: "nfl",
            preloadedGrid: grid,
            preloadedMarkets: leagueMarkets,
            clock: { now }
        )

        let scene = UIApplication.shared.connectedScenes.compactMap { $0 as? UIWindowScene }.first
        let window = scene.map { UIWindow(windowScene: $0) } ?? UIWindow(frame: CGRect(x: 0, y: 0, width: 390, height: 1100))
        defer {
            window.isHidden = true
            window.rootViewController = nil
        }

        let configs: [(width: CGFloat, scheme: ColorScheme, tag: String)] = [
            (320, .light, "320_light"),
            (390, .light, "390_light"),
            (320, .dark, "320_dark"),
            (390, .dark, "390_dark"),
        ]

        // 1. League (LeagueGridView)
        for cfg in configs {
            let img = render(
                NavigationStack {
                    LeagueGridView(slug: "nfl", preloadedViewModel: leagueVM)
                }
                .environmentObject(pinManager)
                .environmentObject(navCoordinator)
                .environmentObject(authManager)
                .environment(\.followManager295A, followManager)
                .environment(\.gameAlertsPrompt295A, alertsPrompt),
                into: window,
                width: cfg.width,
                height: 1450,
                colorScheme: cfg.scheme
            )
            try maybeSave(img, name: "league_\(cfg.tag)")
            assertIntactUpcomingHeader(
                ocr: try ocrTexts(in: img),
                surface: "league_\(cfg.tag)",
                allowBeforeFail: allowBeforeFail,
                checkJustHappened: true
            )
        }

        // 2. Sports (FeedView)
        for cfg in configs {
            let img = render(
                FeedView(viewModel: sportsVM)
                    .environmentObject(pinManager)
                    .environmentObject(navCoordinator)
                    .environmentObject(authManager)
                    .environment(\.followManager295A, followManager)
                    .environment(\.gameAlertsPrompt295A, alertsPrompt),
                into: window,
                width: cfg.width,
                height: 1150,
                colorScheme: cfg.scheme
            )
            try maybeSave(img, name: "sports_\(cfg.tag)")
            assertIntactUpcomingHeader(ocr: try ocrTexts(in: img), surface: "sports_\(cfg.tag)", allowBeforeFail: allowBeforeFail)
        }

        // 3. Team (TeamDetailView)
        for cfg in configs {
            let img = render(
                NavigationStack {
                    TeamDetailView(slug: "kansas-city-chiefs", loadedPageForTest: teamPage)
                        .navigationBarTitleDisplayMode(.inline)
                }
                .environmentObject(pinManager)
                .environmentObject(navCoordinator)
                .environmentObject(authManager)
                .environment(\.followManager295A, followManager)
                .environment(\.gameAlertsPrompt295A, alertsPrompt),
                into: window,
                width: cfg.width,
                height: 1150,
                colorScheme: cfg.scheme
            )
            try maybeSave(img, name: "team_\(cfg.tag)")
            assertIntactUpcomingHeader(ocr: try ocrTexts(in: img), surface: "team_\(cfg.tag)", allowBeforeFail: allowBeforeFail)
        }

        // 4. My Stuff (MyStuffView team-feed list showing "Upcoming")
        for cfg in configs {
            let img = render(
                MyStuffView(viewModelForTest: myStuffVM)
                    .environmentObject(authManager)
                    .environmentObject(navCoordinator)
                    .environmentObject(pinManager)
                    .environment(\.followManager295A, followManager)
                    .environment(\.firstRunChecklistStore364A, checklistStore)
                    .environment(\.gameAlertsPrompt295A, alertsPrompt),
                into: window,
                width: cfg.width,
                height: 1350,
                colorScheme: cfg.scheme
            )
            try maybeSave(img, name: "mystuff_\(cfg.tag)")
            assertIntactUpcomingHeader(ocr: try ocrTexts(in: img), surface: "mystuff_\(cfg.tag)", allowBeforeFail: allowBeforeFail)
        }
    }

    func testSectionBandHeaderViewHelperContractsAndOrdinarySize() throws {
        XCTAssertTrue(SectionBandHeaderView.isSingleWord("Upcoming"))
        XCTAssertTrue(SectionBandHeaderView.isSingleWord("Pinned"))
        XCTAssertFalse(SectionBandHeaderView.isSingleWord("Live Now"))
        XCTAssertEqual(SectionBandHeaderView.splitTwoWordLines(for: "Just Happened"), ["Just", "Happened"])
        XCTAssertEqual(SectionBandHeaderView.splitTwoWordLines(for: "Live Now"), ["Live", "Now"])
        XCTAssertNil(SectionBandHeaderView.splitTwoWordLines(for: "Upcoming"))
        XCTAssertNil(SectionBandHeaderView.splitTwoWordLines(for: "Live \u{00B7} Suspended"))

        let wrapped = List {
            Section {
                Text("Row")
            } header: {
                SectionBandHeaderView(title: "Upcoming", systemImage: "calendar", imageColor: .blue, count: 5)
            }
        }
        .listStyle(.insetGrouped)
        .environment(\.dynamicTypeSize, .large)
        .frame(width: 390, height: 220)

        let host = hostForMeasurement(wrapped, at: .large)
        let bounds = CGRect(x: 0, y: 0, width: 390, height: 220)
        let scene = UIApplication.shared.connectedScenes.compactMap { $0 as? UIWindowScene }.first
        let window = scene.map { UIWindow(windowScene: $0) } ?? UIWindow(frame: bounds)
        window.frame = bounds
        window.rootViewController = host
        window.isHidden = false
        defer {
            window.isHidden = true
            window.rootViewController = nil
        }
        host.view.frame = bounds
        for _ in 0..<3 {
            host.view.setNeedsLayout()
            host.view.layoutIfNeeded()
            RunLoop.current.run(until: Date().addingTimeInterval(0.02))
        }
        let img = UIGraphicsImageRenderer(size: bounds.size).image { _ in
            _ = window.drawHierarchy(in: bounds, afterScreenUpdates: true)
        }
        let ocr = try ocrTexts(in: img)
        let joined = ocr.joined(separator: " | ")
        XCTAssertTrue(ocr.contains { $0.contains("Upcoming") }, "Ordinary size should render intact Upcoming: \(joined)")
        XCTAssertFalse(ocr.contains { $0.contains("Up-") || $0.contains("com-") }, "Ordinary size broken: \(joined)")
    }

    #endif
}
