import SwiftUI
import UIKit
import Vision
import XCTest
@testable import Bain_Luck

/// #13869 — iPad Sports tab (`FeedView`) must use the full available width at
/// `834 pt` and `1194 pt` in both light and dark appearances instead of leaving
/// the right column(s) empty when leagues have only 1–2 games.
@MainActor
final class SportsTabIPadWidth13869Tests: XCTestCase {
    private nonisolated final class Client13869: SportsFeedProviding, @unchecked Sendable {
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

    private func makeMultiLeagueFeed() throws -> FeedResponse {
        let now = Date()
        let iso = ISO8601DateFormatter()
        let live1 = iso.string(from: now.addingTimeInterval(-3600))
        let live2 = iso.string(from: now.addingTimeInterval(-2400))
        let live3 = iso.string(from: now.addingTimeInterval(-1800))
        let soon1 = iso.string(from: now.addingTimeInterval(3600))
        let soon2 = iso.string(from: now.addingTimeInterval(5400))
        let soon3 = iso.string(from: now.addingTimeInterval(7200))
        let soon4 = iso.string(from: now.addingTimeInterval(10800))

        let json = """
        {
          "items": [
            {
              "type": "event",
              "score": 98,
              "data": {
                "id": 9138691,
                "sport": "americanfootball_nfl",
                "sport_name": "NFL",
                "home_team": "Kansas City Chiefs",
                "away_team": "Buffalo Bills",
                "home_team_data": {"team_id": 12, "name": "Kansas City Chiefs", "short_name": "Chiefs", "abbreviation": "KC", "primary_color": "#E31837"},
                "away_team_data": {"team_id": 2, "name": "Buffalo Bills", "short_name": "Bills", "abbreviation": "BUF", "primary_color": "#00338D"},
                "commence_time": "\(live1)",
                "status": "live",
                "home_score": 21,
                "away_score": 17,
                "espn": {"period": "Q3", "clock": "4:18"},
                "current_odds": {"home_probability": 0.58, "away_probability": 0.42}
              }
            },
            {
              "type": "event",
              "score": 95,
              "data": {
                "id": 9138692,
                "sport": "americanfootball_ncaaf",
                "sport_name": "NCAAF",
                "home_team": "Ohio State Buckeyes",
                "away_team": "Michigan Wolverines",
                "home_team_data": {"team_id": 194, "name": "Ohio State Buckeyes", "short_name": "Ohio State", "abbreviation": "OSU", "primary_color": "#BB0000"},
                "away_team_data": {"team_id": 130, "name": "Michigan Wolverines", "short_name": "Michigan", "abbreviation": "MICH", "primary_color": "#00274C"},
                "commence_time": "\(live2)",
                "status": "live",
                "home_score": 14,
                "away_score": 10,
                "espn": {"period": "Q2", "clock": "2:05"},
                "current_odds": {"home_probability": 0.64, "away_probability": 0.36}
              }
            },
            {
              "type": "event",
              "score": 93,
              "data": {
                "id": 9138693,
                "sport": "basketball_ncaab",
                "sport_name": "NCAAB",
                "home_team": "Duke Blue Devils",
                "away_team": "North Carolina Tar Heels",
                "home_team_data": {"team_id": 150, "name": "Duke Blue Devils", "short_name": "Duke", "abbreviation": "DUKE", "primary_color": "#003087"},
                "away_team_data": {"team_id": 153, "name": "North Carolina Tar Heels", "short_name": "North Carolina", "abbreviation": "UNC", "primary_color": "#7BAFD4"},
                "commence_time": "\(live3)",
                "status": "live",
                "home_score": 48,
                "away_score": 46,
                "espn": {"period": "2H", "clock": "11:42"},
                "current_odds": {"home_probability": 0.55, "away_probability": 0.45}
              }
            },
            {
              "type": "event",
              "score": 91,
              "data": {
                "id": 9138694,
                "sport": "basketball_nba",
                "sport_name": "NBA",
                "home_team": "Boston Celtics",
                "away_team": "New York Knicks",
                "home_team_data": {"team_id": 2, "name": "Boston Celtics", "short_name": "Celtics", "abbreviation": "BOS", "primary_color": "#007A33"},
                "away_team_data": {"team_id": 18, "name": "New York Knicks", "short_name": "Knicks", "abbreviation": "NYK", "primary_color": "#006BB6"},
                "commence_time": "\(soon1)",
                "status": "scheduled",
                "current_odds": {"home_probability": 0.62, "away_probability": 0.38}
              }
            },
            {
              "type": "event",
              "score": 89,
              "data": {
                "id": 9138695,
                "sport": "basketball_nba",
                "sport_name": "NBA",
                "home_team": "Los Angeles Lakers",
                "away_team": "Golden State Warriors",
                "home_team_data": {"team_id": 13, "name": "Los Angeles Lakers", "short_name": "Lakers", "abbreviation": "LAL", "primary_color": "#552583"},
                "away_team_data": {"team_id": 9, "name": "Golden State Warriors", "short_name": "Warriors", "abbreviation": "GSW", "primary_color": "#1D428A"},
                "commence_time": "\(soon2)",
                "status": "scheduled",
                "current_odds": {"home_probability": 0.51, "away_probability": 0.49}
              }
            },
            {
              "type": "event",
              "score": 87,
              "data": {
                "id": 9138696,
                "sport": "icehockey_nhl",
                "sport_name": "NHL",
                "home_team": "Dallas Stars",
                "away_team": "Edmonton Oilers",
                "home_team_data": {"team_id": 25, "name": "Dallas Stars", "short_name": "Stars", "abbreviation": "DAL", "primary_color": "#006847"},
                "away_team_data": {"team_id": 22, "name": "Edmonton Oilers", "short_name": "Oilers", "abbreviation": "EDM", "primary_color": "#041E42"},
                "commence_time": "\(soon3)",
                "status": "scheduled",
                "current_odds": {"home_probability": 0.54, "away_probability": 0.46}
              }
            },
            {
              "type": "event",
              "score": 85,
              "data": {
                "id": 9138697,
                "sport": "soccer_epl",
                "sport_name": "Premier League",
                "home_team": "Arsenal",
                "away_team": "Liverpool",
                "home_team_data": {"team_id": 359, "name": "Arsenal", "short_name": "Arsenal", "abbreviation": "ARS", "primary_color": "#EF0107"},
                "away_team_data": {"team_id": 364, "name": "Liverpool", "short_name": "Liverpool", "abbreviation": "LIV", "primary_color": "#C8102E"},
                "commence_time": "\(soon4)",
                "status": "scheduled",
                "current_odds": {"home_probability": 0.43, "away_probability": 0.31, "draw_probability": 0.26}
              }
            }
          ],
          "total": 7,
          "limit": 50,
          "offset": 0,
          "has_more": false
        }
        """
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        return try d.decode(FeedResponse.self, from: Data(json.utf8))
    }

    func testRenderSportsTabIPadWidths13869() async throws {
        let env = ProcessInfo.processInfo.environment
        let outDir = env["IPAD_SPORTS_13869_DIR"] ?? ""
        let prefix = (env["IPAD_SPORTS_13869_PREFIX"] ?? "after").trimmingCharacters(in: .whitespacesAndNewlines)
        if !outDir.isEmpty {
            try FileManager.default.createDirectory(atPath: outDir, withIntermediateDirectories: true)
        }

        let feed = try makeMultiLeagueFeed()
        let vm = FeedViewModel(client: Client13869(feed: feed), telemetry: nil, autoRefreshEnabled: false)
        await vm.startLoad()
        XCTAssertEqual(vm.items.count, 7)

        let suiteName = "test-13869-\(UUID().uuidString)"
        let defaults = UserDefaults(suiteName: suiteName)!
        defer { UserDefaults.standard.removePersistentDomain(forName: suiteName) }
        let pinManager = PinManager(defaults: defaults, allowLegacyGuestPins: false)
        let navCoordinator = NavigationCoordinator()

        let specs: [(name: String, width: CGFloat, height: CGFloat, scheme: ColorScheme)] = [
            ("\(prefix)-834-light.png", 834, 1100, .light),
            ("\(prefix)-834-dark.png", 834, 1100, .dark),
            ("\(prefix)-1194-light.png", 1194, 1000, .light),
            ("\(prefix)-1194-dark.png", 1194, 1000, .dark),
        ]

        let scene = UIApplication.shared.connectedScenes.compactMap { $0 as? UIWindowScene }.first
        let window: UIWindow = scene.map { UIWindow(windowScene: $0) } ?? UIWindow(frame: CGRect(x: 0, y: 0, width: 1194, height: 1100))
        window.isHidden = false
        defer {
            window.isHidden = true
            window.rootViewController = nil
        }

        for spec in specs {
            let uiStyle: UIUserInterfaceStyle = spec.scheme == .dark ? .dark : .light
            let view = FeedView(viewModel: vm)
                .environmentObject(pinManager)
                .environmentObject(navCoordinator)
                .environment(\.horizontalSizeClass, .regular)
                .environment(\.colorScheme, spec.scheme)
                .frame(width: spec.width, height: spec.height)
                .clipped()

            let host = hostForMeasurement(view, at: .large)
            host.safeAreaRegions = []
            host.overrideUserInterfaceStyle = uiStyle
            host.traitOverrides.horizontalSizeClass = .regular
            let bounds = CGRect(x: 0, y: 0, width: spec.width, height: spec.height)
            window.frame = bounds
            window.overrideUserInterfaceStyle = uiStyle
            window.rootViewController = host
            host.view.frame = bounds

            for _ in 0..<10 {
                host.view.setNeedsLayout()
                host.view.layoutIfNeeded()
                RunLoop.current.run(until: Date().addingTimeInterval(0.04))
            }

            let fmt = UIGraphicsImageRendererFormat()
            fmt.scale = 2.0
            fmt.opaque = true
            let image = UIGraphicsImageRenderer(size: bounds.size, format: fmt).image { _ in
                _ = host.view.drawHierarchy(in: host.view.bounds, afterScreenUpdates: true)
            }

            if !outDir.isEmpty {
                let data = try XCTUnwrap(image.pngData())
                try data.write(to: URL(fileURLWithPath: outDir).appendingPathComponent(spec.name), options: .atomic)
            }

            if prefix != "before" {
                let boxes = try ocrBoxes(image)
                let allText = boxes.map(\.text).joined(separator: " ")
                XCTAssertTrue(allText.contains("Chiefs") || allText.contains("Bills"), "Expected NFL fixture in \(spec.name)")
                XCTAssertTrue(
                    boxes.contains { $0.midX > 0.55 },
                    "Expected right half of \(spec.name) at width \(spec.width) pt to contain rendered card text"
                )
                if spec.width >= 1194 {
                    XCTAssertTrue(
                        boxes.contains { $0.midX > 0.72 },
                        "Expected third column at 1194 pt in \(spec.name) to be populated"
                    )
                }
            }
        }
    }

    func testBlocksPackConsecutiveSingleGameLeaguesWhileKeepingOrder() async throws {
        let feed = try makeMultiLeagueFeed()
        let vm = FeedViewModel(client: Client13869(feed: feed), telemetry: nil, autoRefreshEnabled: false)
        await vm.startLoad()

        let liveGroups = SportsLeagueBands401B.grouped(vm.liveNow, band: .live)
        let liveBlocks = SportsRegularGridLayout13869.blocks(from: liveGroups)
        XCTAssertEqual(liveBlocks.count, 1)
        guard case .singletons(_, let packedLive) = liveBlocks[0] else {
            return XCTFail("Expected all 3 live single-game leagues to pack into one block")
        }
        XCTAssertEqual(packedLive.map(\.title), ["NFL", "NCAAF", "NCAAB"])

        let upcomingGroups = SportsLeagueBands401B.grouped(vm.upcoming, band: .upcoming)
        let upcomingBlocks = SportsRegularGridLayout13869.blocks(from: upcomingGroups)
        XCTAssertEqual(upcomingBlocks.count, 2)
        guard case .league(let nbaGroup) = upcomingBlocks[0],
              case .singletons(_, let packedUpcoming) = upcomingBlocks[1] else {
            return XCTFail("Expected NBA(2) as league block followed by packed NHL(1)+EPL(1) singletons")
        }
        XCTAssertEqual(nbaGroup.title, "NBA")
        XCTAssertEqual(nbaGroup.items.count, 2)
        XCTAssertEqual(packedUpcoming.map(\.title), ["NHL", "EPL"])

        // Standalone 1-game league separated by a 2-game league stays its own league block.
        let loneSingletonGroups = [packedUpcoming[0], nbaGroup, packedUpcoming[1]]
        let loneBlocks = SportsRegularGridLayout13869.blocks(from: loneSingletonGroups)
        XCTAssertEqual(loneBlocks.count, 3)
        for block in loneBlocks {
            guard case .league = block else {
                return XCTFail("Expected non-adjacent single-game leagues to stay individual league blocks")
            }
        }
    }

    func testEffectiveColumnCountNeverLeavesEmptyRightColumns() {
        XCTAssertEqual(SportsRegularGridLayout13869.effectiveColumnCount(baseColumns: 3, itemCount: 1), 1)
        XCTAssertEqual(SportsRegularGridLayout13869.effectiveColumnCount(baseColumns: 3, itemCount: 2), 2)
        XCTAssertEqual(SportsRegularGridLayout13869.effectiveColumnCount(baseColumns: 3, itemCount: 3), 3)
        XCTAssertEqual(SportsRegularGridLayout13869.effectiveColumnCount(baseColumns: 3, itemCount: 4), 3)
        XCTAssertEqual(SportsRegularGridLayout13869.effectiveColumnCount(baseColumns: 2, itemCount: 1), 1)
        XCTAssertEqual(SportsRegularGridLayout13869.effectiveColumnCount(baseColumns: 2, itemCount: 2), 2)
        XCTAssertEqual(SportsRegularGridLayout13869.effectiveColumnCount(baseColumns: 2, itemCount: 3), 2)
        XCTAssertEqual(SportsRegularGridLayout13869.effectiveColumnCount(baseColumns: 1, itemCount: 3), 1)
    }

    private func ocrBoxes(_ image: UIImage) throws -> [(text: String, midX: CGFloat)] {
        let req = VNRecognizeTextRequest()
        req.recognitionLevel = .accurate
        req.usesLanguageCorrection = false
        try VNImageRequestHandler(cgImage: XCTUnwrap(image.cgImage)).perform([req])
        return (req.results ?? []).compactMap { obs in
            guard let s = obs.topCandidates(1).first?.string else { return nil }
            return (s, obs.boundingBox.midX)
        }
    }
}
