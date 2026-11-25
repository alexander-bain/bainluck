import SwiftUI
import UIKit
import Vision
import XCTest
@testable import Bain_Luck

@MainActor
final class LeaguePageTitle13662Tests: XCTestCase {

    private func decodeSnake<T: Decodable>(_ type: T.Type, _ json: String) throws -> T {
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        return try d.decode(T.self, from: Data(json.utf8))
    }

    private func captureWindow<V: View>(
        _ view: V,
        width: CGFloat = 390,
        height: CGFloat = 852,
        cropHeight: CGFloat = 420,
        scheme: ColorScheme = .light,
        size: DynamicTypeSize = .large
    ) -> UIImage {
        let style: UIUserInterfaceStyle = scheme == .dark ? .dark : .light
        let auth = AuthManager(restoreOnInit: false)
        let nav = NavigationCoordinator()
        let pins = PinManager(defaults: UserDefaults(suiteName: "LeagueTitle13662.\(UUID().uuidString)")!, allowLegacyGuestPins: true)
        let root = view
            .environment(\.colorScheme, scheme)
            .environment(\.horizontalSizeClass, .compact)
            .environmentObject(auth)
            .environmentObject(nav)
            .environmentObject(pins)

        let host = hostForMeasurement(root, at: size)
        host.overrideUserInterfaceStyle = style
        let rect = CGRect(x: 0, y: 0, width: width, height: height)
        host.view.frame = rect

        let scene = UIApplication.shared.connectedScenes.compactMap { $0 as? UIWindowScene }.first
        let window: UIWindow = scene.map { UIWindow(windowScene: $0) } ?? UIWindow(frame: rect)
        window.frame = rect
        window.overrideUserInterfaceStyle = style
        window.rootViewController = host
        window.makeKeyAndVisible()
        defer {
            window.isHidden = true
            window.rootViewController = nil
        }

        for _ in 0..<6 {
            host.view.setNeedsLayout()
            host.view.layoutIfNeeded()
            RunLoop.current.run(until: Date().addingTimeInterval(0.03))
        }

        let fmt = UIGraphicsImageRendererFormat()
        fmt.scale = 2.0
        fmt.opaque = true
        let full = UIGraphicsImageRenderer(size: rect.size, format: fmt).image { _ in
            _ = window.drawHierarchy(in: window.bounds, afterScreenUpdates: true)
        }
        return UIGraphicsImageRenderer(size: CGSize(width: width, height: cropHeight), format: fmt).image { _ in
            full.draw(at: .zero)
        }
    }

    private func ocrLines(_ image: UIImage) throws -> [String] {
        let req = VNRecognizeTextRequest()
        req.recognitionLevel = .accurate
        req.usesLanguageCorrection = false
        try VNImageRequestHandler(cgImage: XCTUnwrap(image.cgImage)).perform([req])
        return (req.results ?? []).compactMap { $0.topCandidates(1).first?.string }
    }

    func testCanonicalDisplayNamesNeverShowPlayoffsOrSeasonYear() throws {
        let gridJSON = """
        {
          "league": "nba",
          "name": "NBA Playoffs 2026-27",
          "season": "2026-27",
          "columns": [],
          "teams": [],
          "movers": [],
          "team_count": 30,
          "sources_available": ["kalshi"]
        }
        """
        let nbaGrid = try decodeSnake(ChampionshipGridResponse.self, gridJSON)
        let nbaVM = LeagueGridViewModel(slug: "nba", preloadedGrid: nbaGrid, preloadedMarkets: nil)
        XCTAssertEqual(nbaVM.displayName, "NBA")
        XCTAssertFalse(nbaVM.displayName.contains("Playoffs"))
        XCTAssertFalse(nbaVM.displayName.contains("2026"))

        let expected: [(String, String)] = [
            ("nba", "NBA"),
            ("nfl", "NFL"),
            ("mlb", "MLB"),
            ("nhl", "NHL"),
            ("wnba", "WNBA"),
            ("ncaa-basketball", "NCAAB"),
            ("ncaa-women-basketball", "WNCAAB"),
            ("ncaa-football", "NCAAF"),
            ("epl", "Premier League"),
            ("mls", "MLS"),
            ("la-liga", "La Liga"),
            ("champions-league", "Champions League"),
            ("bundesliga", "Bundesliga"),
            ("golf", "Golf"),
        ]
        for (slug, title) in expected {
            let otherGrid = try decodeSnake(ChampionshipGridResponse.self, """
            {
              "league": "\(slug)",
              "name": "\(title) Playoffs 2026-27",
              "season": "2026-27",
              "columns": [],
              "teams": [],
              "movers": [],
              "team_count": 0,
              "sources_available": []
            }
            """)
            let vm = LeagueGridViewModel(slug: slug, preloadedGrid: otherGrid)
            XCTAssertEqual(vm.displayName, title, "slug \(slug)")
            XCTAssertFalse(vm.displayName.localizedCaseInsensitiveContains("Playoffs"), slug)
            XCTAssertFalse(vm.displayName.localizedCaseInsensitiveContains("Tournament"), slug)
        }
    }

    func testLeagueGridNavigationTitlesDoNotTruncateAt390pt() throws {
        let marketsJSON = """
        {
          "sport_key": "basketball_nba",
          "total_markets": 0,
          "sections": {},
          "upcoming_games": [
            {
              "id": 15353569,
              "sport": "basketball_nba",
              "home_team": "Orlando Magic",
              "away_team": "Detroit Pistons",
              "commence_time": "2099-11-25T00:00:00Z",
              "status": "scheduled",
              "current_odds": { "home_probability": 0.54, "away_probability": 0.46 }
            }
          ],
          "recent_results": []
        }
        """
        let markets = try decodeSnake(LeagueMarketsResponse.self, marketsJSON)
        let grid = try decodeSnake(ChampionshipGridResponse.self, """
        {
          "league": "nba",
          "name": "NBA Playoffs 2026-27",
          "season": "2026-27",
          "columns": [],
          "teams": [],
          "movers": [],
          "team_count": 0,
          "sources_available": ["kalshi"]
        }
        """)

        let vm = LeagueGridViewModel(slug: "nba", preloadedGrid: grid, preloadedMarkets: markets)
        let view = NavigationStack {
            LeagueGridView(slug: "nba", preloadedViewModel: vm)
        }

        let lightLarge = captureWindow(view, scheme: .light, size: .large)
        let darkLarge = captureWindow(view, scheme: .dark, size: .large)
        let lightXXL = captureWindow(view, scheme: .light, size: .xxLarge)

        for (label, img) in [("light .large", lightLarge), ("dark .large", darkLarge), ("light .xxLarge", lightXXL)] {
            let lines = try ocrLines(img)
            let joined = lines.joined(separator: " ")
            XCTAssertTrue(joined.contains("NBA"), "\(label) missing NBA title: \(lines)")
            XCTAssertFalse(joined.contains("Playoffs"), "\(label) unexpectedly printed Playoffs: \(lines)")
            XCTAssertFalse(joined.contains("…") || joined.contains("..."), "\(label) truncated nav title: \(lines)")
        }

        // Check longer league titles at 390pt .large and .xxLarge to ensure no ellipsis
        for slug in ["champions-league", "epl"] {
            let lvm = LeagueGridViewModel(slug: slug, preloadedMarkets: markets)
            let lv = NavigationStack { LeagueGridView(slug: slug, preloadedViewModel: lvm) }
            for sz in [DynamicTypeSize.large, .xxLarge] {
                let cap = captureWindow(lv, cropHeight: 220, scheme: .light, size: sz)
                let lines = try ocrLines(cap)
                let topLines = lines.prefix(4).joined(separator: " ")
                XCTAssertFalse(topLines.contains("…") || topLines.contains("..."), "\(slug) @ \(sz) truncated: \(lines)")
            }
        }

        if let outDir = ProcessInfo.processInfo.environment["SHEET_13662_ITEM1_DIR"], !outDir.isEmpty {
            let dir = URL(fileURLWithPath: outDir, isDirectory: true)
            try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)

            // Also render Before ("NBA Playoffs 2026-27" at .xxLarge) over List at 390x852 for comparison
            let beforeScreen = NavigationStack {
                List {
                    Section("Upcoming") {
                        if let first = markets.upcomingGames.first {
                            EventCardView(event: first, reason: nil)
                        }
                    }
                }
                .listStyle(.insetGrouped)
                .navigationTitle("NBA Playoffs 2026-27")
                .navigationBarTitleDisplayMode(.large)
                .toolbar {
                    ToolbarItem(placement: .primaryAction) {
                        FollowButton295A(
                            subject: .league(slug: "nba", sportKey: "nba", name: "NBA Playoffs 2026-27"),
                            compact: true
                        )
                    }
                }
            }
            let beforeXXL = captureWindow(beforeScreen, scheme: .light, size: .xxLarge)
            let panels: [(String, UIImage)] = [
                ("Before (.xxLarge 390pt) · simulator results, not phone results", beforeXXL),
                ("After Light (.large 390pt) · simulator results, not phone results", lightLarge),
                ("After Dark (.large 390pt) · simulator results, not phone results", darkLarge),
                ("After Light (.xxLarge 390pt) · simulator results, not phone results", lightXXL),
            ]
            let padding: CGFloat = 16
            let gap: CGFloat = 16
            let headerH: CGFloat = 28
            let totalW = panels.map { $0.1.size.width }.reduce(0, +) + gap * CGFloat(panels.count - 1) + padding * 2
            let totalH = (panels.map { $0.1.size.height }.max() ?? 360) + headerH + padding * 2
            let fmt = UIGraphicsImageRendererFormat()
            fmt.scale = 2.0
            fmt.opaque = true
            let sheet = UIGraphicsImageRenderer(size: CGSize(width: totalW, height: totalH), format: fmt).image { ctx in
                UIColor.systemGray6.setFill()
                ctx.fill(CGRect(origin: .zero, size: CGSize(width: totalW, height: totalH)))
                var x = padding
                for (title, img) in panels {
                    let para = NSMutableParagraphStyle()
                    para.lineBreakMode = .byTruncatingTail
                    NSString(string: title).draw(
                        in: CGRect(x: x, y: padding, width: img.size.width, height: 22),
                        withAttributes: [.font: UIFont.systemFont(ofSize: 11, weight: .bold), .foregroundColor: UIColor.label, .paragraphStyle: para]
                    )
                    img.draw(at: CGPoint(x: x, y: padding + headerH))
                    x += img.size.width + gap
                }
            }
            let data = try XCTUnwrap(sheet.pngData())
            try data.write(to: dir.appendingPathComponent("sheet-13662-item1-league-title-390.png"))
        }
    }
}
