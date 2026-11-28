import Foundation
import SwiftUI
#if canImport(UIKit)
import UIKit
import Vision
#endif
import XCTest
@testable import Bain_Luck

/// 466: A (PILLAR: FORMATTING):
/// Verifies that at `.accessibility5`, game card names, scores, and probabilities grow
/// on `Sports`, `League`, `Team`, and `My Stuff` (including `NavigationLink` chevron rows)
/// without left/right clipping or truncation, using stacked rows (`name` above `score` + `chance`)
/// wherever a row is too narrow side-by-side, while leaving ordinary sizes (`.large`) unchanged.
@MainActor
final class GameCardAX5Layout466ATests: XCTestCase {

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
          "id": 9466001,
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

    private func makeLiveNBAJSON(commence: String) -> String {
        """
        {
          "id": 9466002,
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
          "id": 9466003,
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
          "id": 9466004,
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
            {"type": "event", "score": 95, "data": \(makeLiveNBAJSON(commence: times.live2))},
            {"type": "event", "score": 90, "data": \(makeUpcomingNFLJSON(commence: times.upcoming))}
          ],
          "total": 3,
          "limit": 50,
          "offset": 0,
          "has_more": false
        }
        """)
    }

    private func makeLeagueFixtures(times: (live1: String, live2: String, upcoming: String, recent: String)) throws -> (ChampionshipGridResponse, LeagueMarketsResponse) {
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
              "id": 9466010,
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
              "id": 9466011,
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
              "id": 9466012,
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
        let movedNBA = try decodeJSON(FeedEventData.self, json: makeLiveNBAJSON(commence: times.live2))
        return MyStuffLandingViewModel295A.PreloadedSnapshot(
            liveEvents: [(liveNFL, false)],
            nextEvents: [(nextNFL, false)],
            nextMarkets: [],
            movedEntries: [
                MyStuffMovedEntry295A(
                    id: "moved-9466002",
                    movementSummary: "Minnesota Timberwolves rose from 28% to 36%",
                    magnitudePoints: 8,
                    payload: .event(movedNBA, awayVerified: false)
                )
            ],
            discoverItems: []
        )
    }

    private func render<V: View>(
        _ view: V,
        into window: UIWindow,
        width: CGFloat,
        height: CGFloat,
        colorScheme: ColorScheme,
        typeSize: DynamicTypeSize = .accessibility5
    ) -> UIImage {
        let uiStyle: UIUserInterfaceStyle = colorScheme == .dark ? .dark : .light
        let wrapped = view
            .environment(\.colorScheme, colorScheme)
            .environment(\.dynamicTypeSize, typeSize)
            .environment(\.horizontalSizeClass, width >= 700 ? .regular : .compact)
            .frame(width: width, height: height)
            .clipped()

        let host = hostForMeasurement(wrapped, at: typeSize)
        host.safeAreaRegions = []
        host.overrideUserInterfaceStyle = uiStyle
        host.additionalSafeAreaInsets = .zero
        host.view.insetsLayoutMarginsFromSafeArea = false
        host.traitOverrides.horizontalSizeClass = width >= 700 ? .regular : .compact
        let uiCategory: UIContentSizeCategory = typeSize == .accessibility5 ? .accessibilityExtraExtraExtraLarge : .large
        host.traitOverrides.preferredContentSizeCategory = uiCategory
        host.view.traitOverrides.preferredContentSizeCategory = uiCategory

        let bounds = CGRect(x: 0, y: 0, width: width, height: height)
        window.frame = bounds
        window.overrideUserInterfaceStyle = uiStyle
        window.rootViewController = host
        window.isHidden = false

        host.view.frame = bounds
        host.view.backgroundColor = colorScheme == .dark ? .black : .systemGroupedBackground
        for _ in 0..<5 {
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
        guard let dir = ProcessInfo.processInfo.environment["GAMECARD_466A_CAPTURE_DIR"], !dir.isEmpty else { return }
        try FileManager.default.createDirectory(atPath: dir, withIntermediateDirectories: true)
        try XCTUnwrap(image.pngData()).write(
            to: URL(fileURLWithPath: dir).appendingPathComponent("\(name).png"),
            options: .atomic
        )
    }

    private func assertNoClippedCardTokens(_ ocr: [String], surface: String) {
        let joined = ocr.joined(separator: " | ")
        let forbiddenExactTokens: Set<String> = ["FL", "BA", "IFL", "core", "egame", "regame", "hiefs", "ills", "Timberwolve", "Bengal"]
        for line in ocr {
            for word in line.split(whereSeparator: \.isWhitespace).map(String.init) {
                XCTAssertFalse(
                    forbiddenExactTokens.contains(word),
                    "\(surface): clipped card token `\(word)` in OCR: \(joined)"
                )
            }
            XCTAssertFalse(line.contains("\u{2026}") || line.contains("..."), "\(surface): ellipsis truncation `\(line)` in OCR: \(joined)")
        }
    }

    func testGameCardAXLayout466AWidthsAndStackingAcrossDevices() {
        let widths: [CGFloat] = [232, 256, 304, 334, 530, 730]
        for width in widths {
            // 2-col Live (Score + Now)
            let twoCol = GameCardAXLayout466A.resolve(
                cardWidth: width,
                awayName: "Bills",
                homeName: "Chiefs",
                scaledNameSize: 53,
                scaledScoreSize: 53,
                scaledNowSize: 58,
                scaledHeaderSize: 38,
                scaledPregameSize: 49,
                hasMedium: true,
                hasLiveProjected: false,
                hasLarge: true,
                isFinished: false,
                hasDrawRow: false,
                mediumHeaderText: "Score",
                projectedHeaderText: "",
                largeHeaderText: "Now",
                mediumSamples: ["17", "21"],
                projectedSamples: [],
                largeSamples: ["42%", "58%"]
            )
            XCTAssertLessThanOrEqual(twoCol.totalClusterWidth, width, "2-col overflowed \(width)")
            XCTAssertGreaterThan(twoCol.nowFontSize, 24, "nowFontSize must grow above 24 at \(width)")
            XCTAssertGreaterThan(twoCol.scoreFontSize, 20, "scoreFontSize must grow above 20 at \(width)")
            XCTAssertGreaterThan(twoCol.nameFontSize, 17.5, "nameFontSize must grow above 17.5 at \(width)")
            XCTAssertGreaterThan(twoCol.headerFontSize, 13, "headerFontSize must grow above 13 at \(width)")
            if width <= 334 {
                XCTAssertTrue(twoCol.usesStackedRow, "2-col live should stack on narrow width \(width)")
            } else if width >= 700 {
                XCTAssertFalse(twoCol.usesStackedRow, "2-col live should fit side-by-side on iPad \(width)")
            }

            // 3-col Live (Score + Proj. + Now) with long word Timberwolves
            let threeCol = GameCardAXLayout466A.resolve(
                cardWidth: width,
                awayName: "Timberwolves",
                homeName: "Celtics",
                scaledNameSize: 53,
                scaledScoreSize: 53,
                scaledNowSize: 58,
                scaledHeaderSize: 38,
                scaledPregameSize: 49,
                hasMedium: true,
                hasLiveProjected: true,
                hasLarge: true,
                isFinished: false,
                hasDrawRow: false,
                mediumHeaderText: "Score",
                projectedHeaderText: "Proj.",
                largeHeaderText: "Now",
                mediumSamples: ["78", "84"],
                projectedSamples: ["109", "114"],
                largeSamples: ["36%", "64%"]
            )
            XCTAssertLessThanOrEqual(threeCol.totalClusterWidth, width, "3-col overflowed \(width)")
            XCTAssertGreaterThan(threeCol.nowFontSize, 24, "3-col nowFontSize must grow above 24 at \(width)")
            XCTAssertGreaterThan(threeCol.scoreFontSize, 20, "3-col scoreFontSize must grow above 20 at \(width)")
            XCTAssertGreaterThan(threeCol.nameFontSize, 17.5, "Timberwolves nameFontSize must grow above 17.5 at \(width)")
            if width <= 530 {
                XCTAssertTrue(threeCol.usesStackedRow, "Timberwolves 3-col should stack cleanly at \(width)")
            }

            // 2-col Live with long single word Timberwolves (fits side-by-side at 730 pt iPad)
            let twoColLong = GameCardAXLayout466A.resolve(
                cardWidth: width,
                awayName: "Timberwolves",
                homeName: "Celtics",
                scaledNameSize: 53,
                scaledScoreSize: 53,
                scaledNowSize: 58,
                scaledHeaderSize: 38,
                scaledPregameSize: 49,
                hasMedium: true,
                hasLiveProjected: false,
                hasLarge: true,
                isFinished: false,
                hasDrawRow: false,
                mediumHeaderText: "Score",
                projectedHeaderText: "",
                largeHeaderText: "Now",
                mediumSamples: ["78", "84"],
                projectedSamples: [],
                largeSamples: ["36%", "64%"]
            )
            XCTAssertLessThanOrEqual(twoColLong.totalClusterWidth, width, "2-col Timberwolves overflowed \(width)")
            if width <= 530 {
                XCTAssertTrue(twoColLong.usesStackedRow, "Timberwolves 2-col should stack cleanly at \(width)")
            } else {
                XCTAssertFalse(twoColLong.usesStackedRow, "Timberwolves 2-col should fit side-by-side at iPad \(width)")
            }

            // 3-way soccer (with Draw row)
            let soccer = GameCardAXLayout466A.resolve(
                cardWidth: width,
                awayName: "Arsenal",
                homeName: "Chelsea",
                scaledNameSize: 53,
                scaledScoreSize: 53,
                scaledNowSize: 58,
                scaledHeaderSize: 38,
                scaledPregameSize: 49,
                hasMedium: true,
                hasLiveProjected: false,
                hasLarge: true,
                isFinished: false,
                hasDrawRow: true,
                mediumHeaderText: "Score",
                projectedHeaderText: "",
                largeHeaderText: "Now",
                mediumSamples: ["1", "2"],
                projectedSamples: [],
                largeSamples: ["41%", "29%", "30%"]
            )
            XCTAssertLessThanOrEqual(soccer.totalClusterWidth, width, "soccer overflowed \(width)")
        }
    }

    func testOrdinarySizeRemainsUntouchedAtLargeDynamicType() async throws {
        let times = makeEventTimestamps(now: Date())
        let liveNFL = try decodeJSON(FeedEventData.self, json: makeLiveNFLJSON(commence: times.live1))
        let suiteName = "gamecard-466a-ordinary-\(UUID().uuidString)"
        let defaults = UserDefaults(suiteName: suiteName)!
        defer { UserDefaults.standard.removePersistentDomain(forName: suiteName) }
        let pinManager = PinManager(defaults: defaults, allowLegacyGuestPins: false)
        let navCoordinator = NavigationCoordinator()
        let authManager = AuthManager(restoreOnInit: false)
        let scene = UIApplication.shared.connectedScenes.compactMap { $0 as? UIWindowScene }.first
        let window = scene.map { UIWindow(windowScene: $0) } ?? UIWindow(frame: CGRect(x: 0, y: 0, width: 390, height: 320))
        defer {
            window.isHidden = true
            window.rootViewController = nil
        }

        let cardView = EventCardView(event: liveNFL, reason: nil)
            .padding(14)
            .background(Color.cardBackgroundDark)
            .environmentObject(pinManager)
            .environmentObject(navCoordinator)
            .environmentObject(authManager)

        let img = render(cardView, into: window, width: 390, height: 300, colorScheme: .light, typeSize: .large)
        let ocr = try ocrTexts(in: img)
        let joined = ocr.joined(separator: " | ")
        XCTAssertTrue(ocr.contains { $0.contains("Bills") && $0.contains("42%") } || (joined.contains("Bills") && joined.contains("42%")), "Ordinary .large card broken: \(joined)")
        XCTAssertFalse(DynamicTypeSize.large.isAccessibilitySize)
        XCTAssertFalse(DynamicTypeSize.xxxLarge.isAccessibilitySize)
    }

    func testCaptureFourSurfacesAtAX5TodayOrAfter() async throws {
        let skipAfterAsserts = ProcessInfo.processInfo.environment["GAMECARD_466A_SKIP_AFTER_ASSERTS"] == "1"
        let now = Date()
        let times = makeEventTimestamps(now: now)
        let sportsFeed = try makeSportsFeed(times: times)
        let (leagueGrid, leagueMarkets) = try makeLeagueFixtures(times: times)
        let teamPage = try makeTeamPage(times: times)
        let myStuffSnapshot = try makeMyStuffSnapshot(times: times)
        let liveNFLEvent = try decodeJSON(FeedEventData.self, json: makeLiveNFLJSON(commence: times.live1))

        let suiteName = "gamecard-466a-\(UUID().uuidString)"
        let defaults = UserDefaults(suiteName: suiteName)!
        defer { UserDefaults.standard.removePersistentDomain(forName: suiteName) }
        let pinManager = PinManager(defaults: defaults, allowLegacyGuestPins: false)
        let navCoordinator = NavigationCoordinator()
        let authManager = AuthManager(restoreOnInit: false)
        authManager.user = nil
        let followManager = FollowManager295A(defaults: defaults)
        let alertsPrompt = GameAlertsPromptController295A(defaults: defaults, requestPermissionHandler: {})

        let screenWidth = UIScreen.main.bounds.width
        let allViewports: [(width: CGFloat, scheme: ColorScheme, tag: String)] = [
            (320, .light, "320_light"),
            (390, .light, "390_light"),
            (320, .dark, "320_dark"),
            (390, .dark, "390_dark"),
            (834, .light, "834_light"),
            (834, .dark, "834_dark"),
        ]
        let viewports = allViewports.filter { $0.width <= screenWidth + 1 }
        XCTAssertFalse(viewports.isEmpty)

        let scene = UIApplication.shared.connectedScenes.compactMap { $0 as? UIWindowScene }.first
        let window = scene.map { UIWindow(windowScene: $0) } ?? UIWindow(frame: CGRect(x: 0, y: 0, width: 390, height: 1500))
        defer {
            window.isHidden = true
            window.rootViewController = nil
        }

        // 1. Sports (FeedView)
        let sportsVM = FeedViewModel(client: SportsFeedStub(feed: sportsFeed), telemetry: nil, autoRefreshEnabled: false)
        await sportsVM.startLoad()
        for vp in viewports {
            let h: CGFloat = vp.width >= 700 ? 1550 : (vp.width <= 320 ? 1850 : 1700)
            let img = render(
                FeedView(viewModel: sportsVM)
                    .environmentObject(pinManager)
                    .environmentObject(navCoordinator)
                    .environmentObject(authManager)
                    .environment(\.followManager295A, followManager)
                    .environment(\.gameAlertsPrompt295A, alertsPrompt),
                into: window,
                width: vp.width,
                height: h,
                colorScheme: vp.scheme
            )
            try maybeSave(img, name: "sports_\(vp.tag)")
            let ocr = try ocrTexts(in: img)
            print("GAMECARD_466A_OCR sports_\(vp.tag) = \(ocr.joined(separator: " | "))")
            if !skipAfterAsserts {
                assertNoClippedCardTokens(ocr, surface: "sports_\(vp.tag)")
                let joined = ocr.joined(separator: " | ")
                XCTAssertTrue(ocr.contains { $0.contains("NFL") }, "sports_\(vp.tag) missing NFL: \(joined)")
                XCTAssertTrue(ocr.contains { $0.contains("Bills") }, "sports_\(vp.tag) missing Bills: \(joined)")
                XCTAssertTrue(ocr.contains { $0.contains("Chiefs") }, "sports_\(vp.tag) missing Chiefs: \(joined)")
                XCTAssertTrue(ocr.contains { $0.contains("42%") }, "sports_\(vp.tag) missing 42%: \(joined)")
                XCTAssertTrue(ocr.contains { $0.contains("58%") }, "sports_\(vp.tag) missing 58%: \(joined)")
                XCTAssertTrue(ocr.contains { $0.contains("Timberwolves") }, "sports_\(vp.tag) missing Timberwolves: \(joined)")
                XCTAssertTrue(ocr.contains { $0.contains("36%") }, "sports_\(vp.tag) missing 36%: \(joined)")
                XCTAssertTrue(ocr.contains { $0.contains("64%") }, "sports_\(vp.tag) missing 64%: \(joined)")
            }
        }

        // 2. League (LeagueGridView — NavigationLink chevron)
        let leagueVM = LeagueGridViewModel(
            slug: "nfl",
            preloadedGrid: leagueGrid,
            preloadedMarkets: leagueMarkets,
            clock: { now }
        )
        for vp in viewports {
            let h: CGFloat = vp.width >= 700 ? 1550 : (vp.width <= 320 ? 2080 : 1960)
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
                width: vp.width,
                height: h,
                colorScheme: vp.scheme
            )
            try maybeSave(img, name: "league_\(vp.tag)")
            let ocr = try ocrTexts(in: img)
            print("GAMECARD_466A_OCR league_\(vp.tag) = \(ocr.joined(separator: " | "))")
            if !skipAfterAsserts {
                assertNoClippedCardTokens(ocr, surface: "league_\(vp.tag)")
                let joined = ocr.joined(separator: " | ")
                XCTAssertTrue(ocr.contains { $0.contains("Bills") }, "league_\(vp.tag) missing Bills: \(joined)")
                XCTAssertTrue(ocr.contains { $0.contains("Chiefs") }, "league_\(vp.tag) missing Chiefs: \(joined)")
                XCTAssertTrue(ocr.contains { $0.contains("42%") }, "league_\(vp.tag) missing 42%: \(joined)")
                XCTAssertTrue(ocr.contains { $0.contains("58%") }, "league_\(vp.tag) missing 58%: \(joined)")
                XCTAssertTrue(ocr.contains { $0.contains("Ravens") }, "league_\(vp.tag) missing Ravens: \(joined)")
                XCTAssertTrue(ocr.contains { $0.contains("61%") }, "league_\(vp.tag) missing 61%: \(joined)")
                XCTAssertTrue(ocr.contains { $0.contains("Bengals") }, "league_\(vp.tag) missing Bengals: \(joined)")
                XCTAssertTrue(ocr.contains { $0.contains("39%") }, "league_\(vp.tag) missing 39%: \(joined)")
            }
        }

        // 3. Team (TeamDetailView — NavigationLink chevron)
        for vp in viewports {
            let h: CGFloat = vp.width >= 700 ? 1550 : (vp.width <= 320 ? 1850 : 1700)
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
                width: vp.width,
                height: h,
                colorScheme: vp.scheme
            )
            try maybeSave(img, name: "team_\(vp.tag)")
            let ocr = try ocrTexts(in: img)
            print("GAMECARD_466A_OCR team_\(vp.tag) = \(ocr.joined(separator: " | "))")
            if !skipAfterAsserts {
                assertNoClippedCardTokens(ocr, surface: "team_\(vp.tag)")
                let joined = ocr.joined(separator: " | ")
                XCTAssertTrue(ocr.contains { $0.contains("Bills") }, "team_\(vp.tag) missing Bills: \(joined)")
                XCTAssertTrue(ocr.contains { $0.contains("Chiefs") }, "team_\(vp.tag) missing Chiefs: \(joined)")
                XCTAssertTrue(ocr.contains { $0.contains("42%") }, "team_\(vp.tag) missing 42%: \(joined)")
                XCTAssertTrue(ocr.contains { $0.contains("58%") }, "team_\(vp.tag) missing 58%: \(joined)")
            }
        }

        // 4. My Stuff (MyStuffLandingView295A)
        for vp in viewports {
            let h: CGFloat = vp.width >= 700 ? 1550 : (vp.width <= 320 ? 1850 : 1700)
            let img = render(
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
                into: window,
                width: vp.width,
                height: h,
                colorScheme: vp.scheme
            )
            try maybeSave(img, name: "mystuff_\(vp.tag)")
            let ocr = try ocrTexts(in: img)
            print("GAMECARD_466A_OCR mystuff_\(vp.tag) = \(ocr.joined(separator: " | "))")
            if !skipAfterAsserts {
                assertNoClippedCardTokens(ocr, surface: "mystuff_\(vp.tag)")
                let joined = ocr.joined(separator: " | ")
                XCTAssertTrue(ocr.contains { $0.contains("Bills") }, "mystuff_\(vp.tag) missing Bills: \(joined)")
                XCTAssertTrue(ocr.contains { $0.contains("Chiefs") }, "mystuff_\(vp.tag) missing Chiefs: \(joined)")
                XCTAssertTrue(ocr.contains { $0.contains("42%") }, "mystuff_\(vp.tag) missing 42%: \(joined)")
                XCTAssertTrue(ocr.contains { $0.contains("58%") }, "mystuff_\(vp.tag) missing 58%: \(joined)")
            }
        }

        // 5. Explicit live game card inside List chevron row at 320 & 390 pt (Team compactScheduleStyle)
        if !skipAfterAsserts {
            for vp in viewports where vp.width < 700 {
                let img = render(
                    NavigationStack {
                        List {
                            NavigationLink(value: 1) {
                                EventCardView(event: liveNFLEvent, reason: nil, compactScheduleStyle: true)
                            }
                        }
                        .listStyle(.insetGrouped)
                    }
                    .environmentObject(pinManager)
                    .environmentObject(navCoordinator)
                    .environmentObject(authManager),
                    into: window,
                    width: vp.width,
                    height: 680,
                    colorScheme: vp.scheme
                )
                try maybeSave(img, name: "chevron_live_\(vp.tag)")
                let ocr = try ocrTexts(in: img)
                assertNoClippedCardTokens(ocr, surface: "chevron_live_\(vp.tag)")
                let joined = ocr.joined(separator: " | ")
                XCTAssertTrue(ocr.contains { $0.contains("Bills") }, "chevron_live_\(vp.tag) missing Bills: \(joined)")
                XCTAssertTrue(ocr.contains { $0.contains("Chiefs") }, "chevron_live_\(vp.tag) missing Chiefs: \(joined)")
                XCTAssertTrue(ocr.contains { $0.contains("42%") }, "chevron_live_\(vp.tag) missing 42%: \(joined)")
                XCTAssertTrue(ocr.contains { $0.contains("58%") }, "chevron_live_\(vp.tag) missing 58%: \(joined)")
            }
        }
    }

    #endif
}
