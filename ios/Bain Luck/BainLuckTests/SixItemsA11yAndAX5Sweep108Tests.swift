import SwiftUI
import UIKit
import Vision
import XCTest
@testable import Bain_Luck

#if os(iOS)
private final class SweepTraitContainer108: UIViewController {
    private let child: UIViewController
    private let overrideTraits: UITraitCollection

    init(child: UIViewController, traits: UITraitCollection) {
        self.child = child
        self.overrideTraits = traits
        super.init(nibName: nil, bundle: nil)
    }

    @available(*, unavailable)
    required init?(coder: NSCoder) {
        fatalError("init(coder:) has not been implemented")
    }

    override func viewDidLoad() {
        super.viewDidLoad()
        addChild(child)
        child.view.frame = view.bounds
        child.view.autoresizingMask = [.flexibleWidth, .flexibleHeight]
        view.addSubview(child.view)
        setOverrideTraitCollection(overrideTraits, forChild: child)
        child.didMove(toParent: self)
    }
}

private struct MockContainerHubServiceSweep108: ContainerHubLoading {
    let response: ContainerHubResponse
    let pairedSets: [PairedMetricSet]
    nonisolated func load(slug: String) async throws -> ContainerHubResponse { response }
    nonisolated func loadPairedMetrics(slug: String) async -> [PairedMetricSet] { pairedSets }
}

private nonisolated struct MockDiscoverFeedClientSweep108: DiscoverFeedProviding {
    let response: FeedResponse
    func fetchDiscoverFeed(
        limit: Int, offset: Int, eventPct: Double?, cacheTTL: TimeInterval?
    ) async throws -> FeedResponse {
        response
    }
}

private nonisolated struct MockMyStuffClientSweep108: MyStuffFeedProviding {
    let feed: FeedResponse
    let futures: TeamFuturesResponse
    func fetchMyTeamsFeed() async throws -> FeedResponse { feed }
    func fetchMyTeamFuturesSection(limit: Int) async throws -> TeamFuturesResponse { futures }
    func currentMyStuffPrincipal() async -> String { "user:9001" }
}

private struct MasonryProbeCard108: Identifiable {
    let id: Int
    let label: String
    let height: CGFloat
}

@MainActor
final class SixItemsA11yAndAX5Sweep108Tests: XCTestCase {

    override class func setUp() {
        super.setUp()
        setAutomation(true)
    }

    override class func tearDown() {
        setAutomation(false)
        super.tearDown()
    }

    private static func setAutomation(_ enabled: Bool) {
        guard let lib = dlopen("/usr/lib/libAccessibility.dylib", RTLD_NOW),
              let symbol = dlsym(lib, "_AXSSetAutomationEnabled") else { return }
        typealias SetEnabled = @convention(c) (Int32) -> Void
        unsafeBitCast(symbol, to: SetEnabled.self)(enabled ? 1 : 0)
    }

    private func makeDecoder() -> JSONDecoder {
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        return d
    }

    private func outputURL(for name: String) -> URL? {
        guard let dir = ProcessInfo.processInfo.environment["SWEEP_OUTPUT_DIR"], !dir.isEmpty else {
            return nil
        }
        let dirURL = URL(fileURLWithPath: dir, isDirectory: true)
        try? FileManager.default.createDirectory(at: dirURL, withIntermediateDirectories: true)
        return dirURL.appendingPathComponent(name)
    }

    private func captureAndWalk<V: View>(
        view: V,
        name: String,
        width: CGFloat,
        height: CGFloat,
        horizontalSizeClass: UserInterfaceSizeClass,
        colorScheme: ColorScheme,
        dynamicTypeSize: DynamicTypeSize,
        settleNanoseconds: UInt64 = 50_000_000,
        settlePasses: Int = 12,
        targetLabels: [String] = []
    ) async throws -> (image: UIImage, matchedOrder: [String], allLabels: [String], truncatedOCR: [String]) {
        let uiSizeClass: UIUserInterfaceSizeClass = horizontalSizeClass == .compact ? .compact : .regular
        let uiStyle: UIUserInterfaceStyle = colorScheme == .dark ? .dark : .light
        let uiCategory: UIContentSizeCategory = dynamicTypeSize.isAccessibilitySize
            ? .accessibilityExtraExtraExtraLarge
            : .large

        let auth = AuthManager()
        auth.user = AuthUser(
            id: 9001,
            email: nil,
            displayName: "Sweep Reader",
            photoUrl: nil,
            onboardingCompleted: true,
            createdAt: nil
        )

        let root = NavigationStack { view }
            .frame(width: width, height: height, alignment: .topLeading)
            .environment(\.horizontalSizeClass, horizontalSizeClass)
            .environment(\.colorScheme, colorScheme)
            .environment(\.dynamicTypeSize, dynamicTypeSize)
            .environmentObject(NavigationCoordinator())
            .environmentObject(PinManager())
            .environmentObject(auth)

        let traits = UITraitCollection(traitsFrom: [
            UITraitCollection(horizontalSizeClass: uiSizeClass),
            UITraitCollection(userInterfaceStyle: uiStyle),
            UITraitCollection(preferredContentSizeCategory: uiCategory),
        ])
        let host = hostForMeasurement(root, at: dynamicTypeSize)
        let container = SweepTraitContainer108(child: host, traits: traits)
        container.view.backgroundColor = colorScheme == .dark ? .black : .systemGroupedBackground
        container.view.frame = CGRect(x: 0, y: 0, width: width, height: height)

        let scene = UIApplication.shared.connectedScenes.compactMap { $0 as? UIWindowScene }.first
        let window: UIWindow = scene.map { UIWindow(windowScene: $0) } ?? UIWindow(frame: container.view.frame)
        window.frame = container.view.frame
        window.rootViewController = container
        window.makeKeyAndVisible()
        defer {
            window.isHidden = true
            window.rootViewController = nil
        }

        for _ in 0..<settlePasses {
            container.view.setNeedsLayout()
            container.view.layoutIfNeeded()
            try? await Task.sleep(nanoseconds: settleNanoseconds)
        }

        var matchedOrder: [String] = []
        var allLabels: [String] = []
        var visited = Set<ObjectIdentifier>()

        func walk(_ node: NSObject) {
            let oid = ObjectIdentifier(node)
            guard !visited.contains(oid) else { return }
            visited.insert(oid)

            if let label = node.accessibilityLabel, !label.isEmpty {
                allLabels.append(label)
                for t in targetLabels where label.contains(t) && !matchedOrder.contains(t) {
                    matchedOrder.append(t)
                }
            }
            if let elements = node.accessibilityElements as? [NSObject], !elements.isEmpty {
                for el in elements { walk(el) }
                return
            }
            let count = node.accessibilityElementCount()
            if count != NSNotFound, count > 0 {
                for i in 0..<count {
                    if let el = node.accessibilityElement(at: i) as? NSObject {
                        walk(el)
                    }
                }
                return
            }
            if let v = node as? UIView {
                for sub in v.subviews { walk(sub) }
            }
        }
        walk(container.view)

        let fmt = UIGraphicsImageRendererFormat()
        fmt.scale = 2.0
        fmt.opaque = true
        let image = UIGraphicsImageRenderer(bounds: container.view.bounds, format: fmt).image { _ in
            _ = container.view.drawHierarchy(in: container.view.bounds, afterScreenUpdates: true)
        }

        if let outURL = outputURL(for: "\(name).png"), let png = image.pngData() {
            try png.write(to: outURL)
        }
        let att = XCTAttachment(image: image)
        att.name = "\(name).png"
        att.lifetime = .keepAlways
        add(att)

        var truncatedOCR: [String] = []
        if let cg = image.cgImage {
            let req = VNRecognizeTextRequest()
            req.recognitionLevel = .accurate
            req.usesLanguageCorrection = false
            try? VNImageRequestHandler(cgImage: cg, options: [:]).perform([req])
            let ocrLines = (req.results ?? []).compactMap { $0.topCandidates(1).first?.string }
            truncatedOCR = ocrLines.filter { $0.contains("…") || $0.contains("...") }
        }

        return (image, matchedOrder, allLabels, truncatedOCR)
    }

    private func sampleDiscoverFeed(prefix: String = "Card") throws -> FeedResponse {
        let json = """
        {
          "items": [
            {
              "type": "futures",
              "score": 99,
              "data": {
                "id": 9101,
                "name": "Who will win NBA Championship 2026?",
                "llm_sport_category": "basketball",
                "source": "polymarket",
                "source_count": 2,
                "sources": ["polymarket", "kalshi"],
                "market_tier": 2,
                "resolution_date": "2026-06-22T00:00:00Z",
                "discover_card": {
                  "card_type": "outcome_distribution",
                  "remaining_outcome_count": 24,
                  "distribution_outcomes": [
                    { "label": "Oklahoma City Thunder", "probability": 0.34, "rendered_percent": 34, "movement": 0.02 },
                    { "label": "Minnesota Timberwolves", "probability": 0.21, "rendered_percent": 21, "movement": -0.01 },
                    { "label": "San Francisco Warriors", "probability": 0.14, "rendered_percent": 14 },
                    { "label": "Charlotte Hornets", "probability": 0.004, "rendered_percent": 0 }
                  ]
                }
              }
            },
            {
              "type": "futures",
              "score": 98,
              "data": {
                "id": 9102,
                "name": "\(prefix) 2 Beta: Which movie leads 2026 domestic box office?",
                "llm_sport_category": "entertainment",
                "source": "kalshi",
                "source_count": 1,
                "sources": ["kalshi"],
                "top_outcomes": [
                  { "id": 91021, "name": "Avengers: Doomsday", "probability": 0.56, "rank": 1, "movement": 0.03 }
                ],
                "outcome_count": 8
              }
            },
            {
              "type": "event",
              "score": 97,
              "data": {
                "id": 9103,
                "sport": "soccer_uefa_europa_conference_league",
                "sport_name": "Conference League",
                "away_team": "FC Lausanne-Sport",
                "home_team": "Wolverhampton Wanderers",
                "commence_time": "2026-11-26T20:00:00Z",
                "status": "scheduled",
                "current_odds": {
                  "away_probability": 0.24,
                  "draw_probability": 0.27,
                  "home_probability": 0.49,
                  "away_rendered_percent": 24,
                  "home_rendered_percent": 49
                }
              }
            },
            {
              "type": "futures",
              "score": 96,
              "data": {
                "id": 9104,
                "name": "\(prefix) 4 Delta: Next James Bond announcement before Dec 31?",
                "llm_sport_category": "entertainment",
                "source": "kalshi",
                "top_outcomes": [{ "id": 91041, "name": "Yes", "probability": 0.41, "rank": 1 }],
                "outcome_count": 2
              }
            },
            {
              "type": "futures",
              "score": 95,
              "data": {
                "id": 9105,
                "name": "\(prefix) 5 Epsilon: Federal Reserve rate cut in December?",
                "llm_sport_category": "economics",
                "source": "kalshi",
                "top_outcomes": [{ "id": 91051, "name": "Yes", "probability": 0.62, "rank": 1 }],
                "outcome_count": 2
              }
            },
            {
              "type": "futures",
              "score": 94,
              "data": {
                "id": 9106,
                "name": "\(prefix) 6 Zeta: Oscars 2027 Best Picture frontrunner?",
                "llm_sport_category": "entertainment",
                "source": "polymarket",
                "top_outcomes": [{ "id": 91061, "name": "The Odyssey", "probability": 0.53, "rank": 1 }],
                "outcome_count": 10
              }
            }
          ],
          "total": 6,
          "limit": 20,
          "offset": 0,
          "has_more": false
        }
        """
        return try makeDecoder().decode(FeedResponse.self, from: Data(json.utf8))
    }

    private func sampleEventDetail() throws -> EventDetail {
        let json = """
        {
          "id": 15342680,
          "sport": "americanfootball_nfl",
          "league": "NFL",
          "home_team": "Washington Commanders",
          "away_team": "San Francisco 49ers",
          "commence_time": "2026-11-23T18:00:00Z",
          "status": "live",
          "home_score": 17,
          "away_score": 21,
          "current_odds": {
            "home_probability": 0.364,
            "away_probability": 0.636,
            "home_rendered_percent": 36,
            "away_rendered_percent": 64,
            "updated_at": "2026-11-23T17:30:00Z"
          },
          "opening_odds": {
            "home_probability": 0.44,
            "away_probability": 0.56,
            "home_rendered_percent": 44,
            "away_rendered_percent": 56
          },
          "prematch_odds": {
            "home_probability": 0.42,
            "away_probability": 0.58,
            "home_rendered_percent": 42,
            "away_rendered_percent": 58
          },
          "espn": {
            "period": "3",
            "game_clock": "6:12",
            "broadcast": "FOX"
          },
          "win_probability_sources": {
            "betting": { "value": 0.36, "display_name": "Sportsbooks" },
            "kalshi": { "value": 0.37, "display_name": "Kalshi" },
            "polymarket": { "value": 0.365, "display_name": "Polymarket" }
          }
        }
        """
        return try makeDecoder().decode(EventDetail.self, from: Data(json.utf8))
    }

    func testSweepAllFiveScreensAX5AndVoiceOverOrder() async throws {
        // 1. DISCOVER — AX5 390 Light & Dark + VO order (834 & 390)
        let discoverFeed = try sampleDiscoverFeed()
        for scheme in [ColorScheme.light, ColorScheme.dark] {
            let vm = DiscoverViewModel(client: MockDiscoverFeedClientSweep108(response: discoverFeed), lastGood: nil, telemetry: nil)
            let place = MacReadingPlace<DiscoverViewModel>()
            _ = place.models(orMake: { vm })
            let suffix = scheme == .dark ? "dark" : "light"
            let res = try await captureAndWalk(
                view: DiscoverView(macPlace: place),
                name: "01-discover-ax5-390-\(suffix)",
                width: 390,
                height: 2200,
                horizontalSizeClass: .compact,
                colorScheme: scheme,
                dynamicTypeSize: .accessibility5
            )
            print("SWEEP_DISCOVER_AX5_\(suffix.uppercased())_TRUNC:", res.truncatedOCR)
        }
        do {
            let vm = DiscoverViewModel(client: MockDiscoverFeedClientSweep108(response: discoverFeed), lastGood: nil, telemetry: nil)
            let place = MacReadingPlace<DiscoverViewModel>()
            _ = place.models(orMake: { vm })
            let targets = [
                "NBA Championship 2026",
                "Card 2 Beta",
                "FC Lausanne-Sport",
                "Card 4 Delta",
                "Card 5 Epsilon",
                "Card 6 Zeta",
            ]
            let vo834 = try await captureAndWalk(
                view: DiscoverView(macPlace: place),
                name: "01-discover-vo-834",
                width: 834,
                height: 1400,
                horizontalSizeClass: .regular,
                colorScheme: .light,
                dynamicTypeSize: .large,
                targetLabels: targets
            )
            print("SWEEP_DISCOVER_VO_834:", vo834.matchedOrder)
        }
        if let distCard = discoverFeed.items.first?.futures {
            for scheme in [ColorScheme.light, ColorScheme.dark] {
                let suffix = scheme == .dark ? "dark" : "light"
                let res = try await captureAndWalk(
                    view: DistributionCardView(data: distCard, navigationPath: .constant(NavigationPath()))
                        .padding(16),
                    name: "01b-distribution-card-ax5-390-\(suffix)",
                    width: 390,
                    height: 900,
                    horizontalSizeClass: .compact,
                    colorScheme: scheme,
                    dynamicTypeSize: .accessibility5
                )
                print("SWEEP_DIST_AX5_\(suffix.uppercased())_TRUNC:", res.truncatedOCR)
                XCTAssertEqual(res.truncatedOCR, [], "DistributionCardView truncated at AX5 \(suffix)")
            }
        }

        // 2. SET PAGE (ContainerHubView) — AX5 390 Light & Dark + VO order (834)
        let nflURL = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .appendingPathComponent("ContainerHubFixtures/live_nfl_week12_13417.json")
        let nflResp = try makeDecoder().decode(ContainerHubResponse.self, from: Data(contentsOf: nflURL))
        let hubService = MockContainerHubServiceSweep108(response: nflResp, pairedSets: [])
        for scheme in [ColorScheme.light, ColorScheme.dark] {
            let suffix = scheme == .dark ? "dark" : "light"
            let res = try await captureAndWalk(
                view: ContainerHubView(slug: "nfl-2026-week-12", displayName: "NFL Week 12", service: hubService),
                name: "02-set-page-ax5-390-\(suffix)",
                width: 390,
                height: 2000,
                horizontalSizeClass: .compact,
                colorScheme: scheme,
                dynamicTypeSize: .accessibility5
            )
            print("SWEEP_SET_AX5_\(suffix.uppercased())_TRUNC:", res.truncatedOCR)
        }
        do {
            let targets = ["Packers", "Bears", "Eagles", "Chiefs", "Broncos", "Giants", "Raiders", "Jets"]
            let vo834 = try await captureAndWalk(
                view: ContainerHubView(slug: "nfl-2026-week-12", displayName: "NFL Week 12", service: hubService),
                name: "02-set-page-vo-834",
                width: 834,
                height: 1210,
                horizontalSizeClass: .regular,
                colorScheme: .light,
                dynamicTypeSize: .large,
                targetLabels: targets
            )
            print("SWEEP_SET_VO_834:", vo834.matchedOrder)
        }

        // 3. GAME PAGE (EventDetailView) — AX5 390 Light & Dark + VO order (390)
        let eventDetail = try sampleEventDetail()
        for scheme in [ColorScheme.light, ColorScheme.dark] {
            let suffix = scheme == .dark ? "dark" : "light"
            let res = try await captureAndWalk(
                view: EventDetailView(eventId: eventDetail.id).withLoadedEventForTest12278(eventDetail),
                name: "03-game-page-ax5-390-\(suffix)",
                width: 390,
                height: 1500,
                horizontalSizeClass: .compact,
                colorScheme: scheme,
                dynamicTypeSize: .accessibility5
            )
            print("SWEEP_GAME_AX5_\(suffix.uppercased())_TRUNC:", res.truncatedOCR)
            print("SWEEP_GAME_VO_390_\(suffix.uppercased())_HEAD:", Array(res.allLabels.prefix(12)))
        }

        // 4. MY STUFF (MyStuffView + TwoColumnMasonryLayout108) — AX5 390 Light & Dark + VO order (834 & 390)
        let myFeedJSON = """
        {
          "items": [
            {"type":"event","score":99,"data":{"id":9401,"sport":"basketball_nba","sport_name":"NBA","away_team":"Minnesota Timberwolves","home_team":"Golden State Warriors","commence_time":"2026-11-24T01:00:00Z","status":"scheduled","current_odds":{"away_probability":0.54,"home_probability":0.46,"away_rendered_percent":54,"home_rendered_percent":46,"projected_away_score":114.0,"projected_home_score":110.0}}},
            {"type":"event","score":98,"data":{"id":9402,"sport":"icehockey_nhl","sport_name":"NHL","away_team":"Carolina Hurricanes","home_team":"Colorado Avalanche","commence_time":"2026-11-24T02:00:00Z","status":"scheduled","current_odds":{"away_probability":0.48,"home_probability":0.52,"away_rendered_percent":48,"home_rendered_percent":52}}},
            {"type":"event","score":97,"data":{"id":9403,"sport":"americanfootball_nfl","sport_name":"NFL","away_team":"San Francisco 49ers","home_team":"Washington Commanders","commence_time":"2026-11-24T03:00:00Z","status":"scheduled","current_odds":{"away_probability":0.61,"home_probability":0.39,"away_rendered_percent":61,"home_rendered_percent":39}}},
            {"type":"event","score":96,"data":{"id":9404,"sport":"soccer_epl","sport_name":"Premier League","away_team":"Wolverhampton Wanderers","home_team":"Nottingham Forest","commence_time":"2026-11-24T04:00:00Z","status":"scheduled","current_odds":{"away_probability":0.31,"draw_probability":0.26,"home_probability":0.43,"away_rendered_percent":31,"home_rendered_percent":43}}}
          ],
          "total": 4,
          "limit": 100,
          "offset": 0,
          "has_more": false
        }
        """
        let myFuturesJSON = """
        {
          "items": [
            {"outcome_id":1,"outcome_name":"Minnesota Timberwolves","market_id":501,"market_name":"Make the NBA Playoffs","probability":0.82,"matched_team":{"id":10,"name":"Minnesota Timberwolves","primary_color":"#0C2340"}},
            {"outcome_id":2,"outcome_name":"Minnesota Timberwolves","market_id":502,"market_name":"Win Northwest Division","probability":0.41,"matched_team":{"id":10,"name":"Minnesota Timberwolves","primary_color":"#0C2340"}},
            {"outcome_id":3,"outcome_name":"Minnesota Timberwolves","market_id":503,"market_name":"Win Western Conference Championship","probability":0.22,"matched_team":{"id":10,"name":"Minnesota Timberwolves","primary_color":"#0C2340"}},
            {"outcome_id":4,"outcome_name":"Minnesota Timberwolves","market_id":504,"market_name":"2027 NBA Finals Championship Winner","probability":0.11,"matched_team":{"id":10,"name":"Minnesota Timberwolves","primary_color":"#0C2340"}},
            {"outcome_id":5,"outcome_name":"San Francisco 49ers","market_id":505,"market_name":"Make the NFL Playoffs","probability":0.79,"matched_team":{"id":20,"name":"San Francisco 49ers","primary_color":"#AA0000"}},
            {"outcome_id":6,"outcome_name":"San Francisco 49ers","market_id":506,"market_name":"Win NFC Conference Championship","probability":0.29,"matched_team":{"id":20,"name":"San Francisco 49ers","primary_color":"#AA0000"}},
            {"outcome_id":7,"outcome_name":"Wolverhampton Wanderers","market_id":507,"market_name":"English Premier League Top 4 Finish 2026-27","probability":0.06,"matched_team":{"id":30,"name":"Wolverhampton Wanderers","primary_color":"#FDB913"}},
            {"outcome_id":8,"outcome_name":"Anthony Edwards","market_id":508,"market_name":"NBA Most Valuable Player 2026-27","probability":0.14,"matched_team":{"id":10,"name":"Minnesota Timberwolves","primary_color":"#0C2340"}}
          ],
          "team_ids": [10, 20, 30],
          "total_count": 8
        }
        """
        let myFeed = try makeDecoder().decode(FeedResponse.self, from: Data(myFeedJSON.utf8))
        let myFutures = try makeDecoder().decode(TeamFuturesResponse.self, from: Data(myFuturesJSON.utf8))
        let myClient = MockMyStuffClientSweep108(feed: myFeed, futures: myFutures)
        for scheme in [ColorScheme.light, ColorScheme.dark] {
            let myVM = MyStuffViewModel(client: myClient, telemetry: nil, autoRefreshEnabled: false)
            await myVM.startLoad()
            let suffix = scheme == .dark ? "dark" : "light"
            let res = try await captureAndWalk(
                view: MyStuffView(viewModelForTest: myVM),
                name: "04-mystuff-ax5-390-\(suffix)",
                width: 390,
                height: 2200,
                horizontalSizeClass: .compact,
                colorScheme: scheme,
                dynamicTypeSize: .accessibility5
            )
            print("SWEEP_MYSTUFF_AX5_\(suffix.uppercased())_TRUNC:", res.truncatedOCR)
            XCTAssertEqual(res.truncatedOCR, [], "MyStuffView truncated at AX5 \(suffix): \(res.truncatedOCR)")
        }
        XCTAssertGreaterThanOrEqual(
            TeamTextContrast.contrast(
                MyStuffTeamTextColour.probabilityHex("#0C2340", colorScheme: .dark),
                againstSurfaceLuminance: TeamTextContrast.darkSurfaceLuminance
            ) ?? 0,
            TeamTextContrast.minimumRatio,
            "MyStuff dark mode probability text for dark primaryColor must clear TeamTextContrast.minimumRatio"
        )
        // Focused AX5 capture showing TeamFuturesSection (PlayoffJourneyCard + Awards + Team Markets) completely on screen
        let oneGameFeedJSON = """
        {"items":[{"type":"event","score":99,"data":{"id":9401,"sport":"basketball_nba","sport_name":"NBA","away_team":"Minnesota Timberwolves","home_team":"Golden State Warriors","commence_time":"2026-11-24T01:00:00Z","status":"scheduled","current_odds":{"away_probability":0.54,"home_probability":0.46,"away_rendered_percent":54,"home_rendered_percent":46}}}],"total":1,"limit":100,"offset":0,"has_more":false}
        """
        let focusedFuturesJSON = """
        {
          "items": [
            {"outcome_id":1,"outcome_name":"Minnesota Timberwolves","market_id":501,"market_name":"Make the NBA Playoffs","probability":0.82,"matched_team":{"id":10,"name":"Minnesota Timberwolves","primary_color":"#0C2340"}},
            {"outcome_id":3,"outcome_name":"Minnesota Timberwolves","market_id":503,"market_name":"Win Western Conference Championship","probability":0.22,"matched_team":{"id":10,"name":"Minnesota Timberwolves","primary_color":"#0C2340"}},
            {"outcome_id":4,"outcome_name":"Minnesota Timberwolves","market_id":504,"market_name":"2027 NBA Finals Championship Winner","probability":0.11,"matched_team":{"id":10,"name":"Minnesota Timberwolves","primary_color":"#0C2340"}},
            {"outcome_id":2,"outcome_name":"Minnesota Timberwolves","market_id":502,"market_name":"Win Northwest Division","probability":0.41,"matched_team":{"id":10,"name":"Minnesota Timberwolves","primary_color":"#0C2340"}},
            {"outcome_id":7,"outcome_name":"Wolverhampton Wanderers","market_id":507,"market_name":"English Premier League Top 4 Finish 2026-27","probability":0.06,"matched_team":{"id":30,"name":"Wolverhampton Wanderers","primary_color":"#FDB913"}},
            {"outcome_id":8,"outcome_name":"Anthony Edwards","market_id":508,"market_name":"NBA Most Valuable Player 2026-27","probability":0.14,"matched_team":{"id":10,"name":"Minnesota Timberwolves","primary_color":"#0C2340"}}
          ],
          "team_ids": [10, 30],
          "total_count": 6
        }
        """
        let oneGameFeed = try makeDecoder().decode(FeedResponse.self, from: Data(oneGameFeedJSON.utf8))
        let focusedFutures = try makeDecoder().decode(TeamFuturesResponse.self, from: Data(focusedFuturesJSON.utf8))
        let oneGameClient = MockMyStuffClientSweep108(feed: oneGameFeed, futures: focusedFutures)
        for scheme in [ColorScheme.light, ColorScheme.dark] {
            let futVM = MyStuffViewModel(client: oneGameClient, telemetry: nil, autoRefreshEnabled: false)
            await futVM.startLoad()
            let suffix = scheme == .dark ? "dark" : "light"
            let res = try await captureAndWalk(
                view: MyStuffView(viewModelForTest: futVM),
                name: "04b-mystuff-futures-ax5-390-\(suffix)",
                width: 390,
                height: 2200,
                horizontalSizeClass: .compact,
                colorScheme: scheme,
                dynamicTypeSize: .accessibility5
            )
            print("SWEEP_MYSTUFF_FUTURES_AX5_\(suffix.uppercased())_TRUNC:", res.truncatedOCR)
            XCTAssertEqual(res.truncatedOCR, [], "TeamFuturesSection truncated at AX5 \(suffix): \(res.truncatedOCR)")
        }
        do {
            let myVM = MyStuffViewModel(client: myClient, telemetry: nil, autoRefreshEnabled: false)
            await myVM.startLoad()
            let targets = [
                "Timberwolves",
                "Hurricanes",
                "49ers",
                "Wolverhampton",
                "San Francisco 49ers",
                "Minnesota Timberwolves",
            ]
            let vo834 = try await captureAndWalk(
                view: MyStuffView(viewModelForTest: myVM),
                name: "04-mystuff-vo-834",
                width: 834,
                height: 2000,
                horizontalSizeClass: .regular,
                colorScheme: .light,
                dynamicTypeSize: .large,
                targetLabels: targets
            )
            print("SWEEP_MYSTUFF_VO_834_GAMES:", vo834.matchedOrder)
            XCTAssertEqual(vo834.matchedOrder, targets, "MyStuff 2-col regular width must traverse left-to-right then down")

            // Direct unequal-height probe of TwoColumnMasonryLayout108 (used by MyStuffView & LeagueGridView)
            let cards = (0..<6).map { idx in
                MasonryProbeCard108(id: idx, label: "Masonry Tile \(idx)", height: idx == 0 ? 280 : 64)
            }
            let masonryProbe = ScrollView {
                TwoColumnMasonryLayout108(spacing: 12) {
                    ForEach(cards) { card in
                        Button(card.label) {}
                            .frame(maxWidth: .infinity, minHeight: card.height, maxHeight: card.height)
                            .accessibilityLabel(card.label)
                            .accessibilitySortPriority(RegularWidthTwoColumnGrid108.sortPriority(index: card.id))
                    }
                }
                .padding(16)
            }
            let voMasonry = try await captureAndWalk(
                view: masonryProbe,
                name: "04-two-col-masonry-108-vo-834",
                width: 834,
                height: 1000,
                horizontalSizeClass: .regular,
                colorScheme: .light,
                dynamicTypeSize: .large,
                targetLabels: cards.map(\.label)
            )
            print("SWEEP_MASONRY108_VO_834:", voMasonry.matchedOrder)
            XCTAssertEqual(voMasonry.matchedOrder, cards.map(\.label))
        }

        // 5. PREFERENCES — AX5 390 Light & Dark + VO order (390)
        let prefsJSON = """
        {
          "home_location": "San Francisco, CA",
          "sport_affinities": {
            "nfl": 1.0,
            "ncaaf": 0.75,
            "nba": 0.5,
            "ncaab": 0.25,
            "entertainment": 0.25
          },
          "onboarding_completed": true,
          "favorites": [
            {"team_id": 1, "team_name": "San Francisco 49ers", "relation_type": "follow", "sport_key": "americanfootball_nfl", "logo_url": null, "source": "espn"},
            {"team_id": 2, "team_name": "Minnesota Timberwolves", "relation_type": "local", "sport_key": "basketball_nba", "logo_url": null, "source": "espn"},
            {"team_id": 3, "team_name": "Wolverhampton Wanderers", "relation_type": "rival", "sport_key": "soccer_epl", "logo_url": null, "source": "espn"},
            {"team_id": 4, "team_name": "Oklahoma City Thunder", "relation_type": "alma_mater", "sport_key": "basketball_nba", "logo_url": null, "source": "espn"}
          ],
          "push_preferences": {
            "daily_challenge": true,
            "big_moves": true,
            "morning_digest": false
          }
        }
        """
        let prefs = try makeDecoder().decode(PreferencesResponse.self, from: Data(prefsJSON.utf8))
        for scheme in [ColorScheme.light, ColorScheme.dark] {
            let suffix = scheme == .dark ? "dark" : "light"
            let res = try await captureAndWalk(
                view: PreferencesView(loadedPrefsForTest: prefs),
                name: "05-preferences-ax5-390-\(suffix)",
                width: 390,
                height: 2200,
                horizontalSizeClass: .compact,
                colorScheme: scheme,
                dynamicTypeSize: .accessibility5
            )
            print("SWEEP_PREFS_AX5_\(suffix.uppercased())_TRUNC:", res.truncatedOCR)
            print("SWEEP_PREFS_VO_390_\(suffix.uppercased())_HEAD:", Array(res.allLabels.prefix(15)))
        }
    }
}
#endif
