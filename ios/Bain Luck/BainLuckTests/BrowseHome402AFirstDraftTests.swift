import SwiftUI
import UIKit
import Vision
import XCTest
@testable import Bain_Luck

@MainActor
final class BrowseHome402AFirstDraftTests: XCTestCase {

    private struct StaticDiscovery402A: ContainerDiscoveryLoading {
        let response: ContainerDiscoveryResponse
        func load(_ request: ContainerDiscoveryRequest) async throws -> ContainerDiscoveryResponse {
            if request.league == .nfl { return response }
            let dec = JSONDecoder()
            dec.keyDecodingStrategy = .convertFromSnakeCase
            return try dec.decode(ContainerDiscoveryResponse.self, from: Data(#"{"collections":[]}"#.utf8))
        }
    }

    private struct StaticPublicSets402A: BrowsePublicSetsLoading {
        let sets: [BrowsePublicSet402A]
        func loadPublicSets() async throws -> [BrowsePublicSet402A] { sets }
    }

    private final class Browse402ATraitContainer: UIViewController {
        let child: UIViewController
        let traits: UITraitCollection

        init(child: UIViewController, traits: UITraitCollection) {
            self.child = child
            self.traits = traits
            super.init(nibName: nil, bundle: nil)
        }

        required init?(coder: NSCoder) { fatalError("unused") }

        override func viewDidLoad() {
            super.viewDidLoad()
            addChild(child)
            child.view.frame = view.bounds
            child.view.autoresizingMask = [.flexibleWidth, .flexibleHeight]
            view.addSubview(child.view)
            child.didMove(toParent: self)
            setOverrideTraitCollection(traits, forChild: child)
        }
    }

    private static func makeSetArtImage(
        symbol: String,
        topColor: UIColor,
        bottomColor: UIColor
    ) -> UIImage {
        let size = CGSize(width: 104, height: 104)
        let renderer = UIGraphicsImageRenderer(size: size)
        return renderer.image { ctx in
            let cg = ctx.cgContext
            let colors = [topColor.cgColor, bottomColor.cgColor] as CFArray
            if let gradient = CGGradient(colorsSpace: CGColorSpaceCreateDeviceRGB(), colors: colors, locations: [0.0, 1.0]) {
                cg.drawLinearGradient(
                    gradient,
                    start: .zero,
                    end: CGPoint(x: size.width, y: size.height),
                    options: []
                )
            } else {
                topColor.setFill()
                ctx.fill(CGRect(origin: .zero, size: size))
            }
            let config = UIImage.SymbolConfiguration(pointSize: 40, weight: .semibold)
            if let icon = UIImage(systemName: symbol, withConfiguration: config)?
                .withTintColor(.white.withAlphaComponent(0.92), renderingMode: .alwaysOriginal) {
                let iconSize = icon.size
                let origin = CGPoint(
                    x: (size.width - iconSize.width) / 2,
                    y: (size.height - iconSize.height) / 2
                )
                icon.draw(at: origin)
            }
        }
    }

    func testCategoryOrderMatchesAcrossBrowseAndSearchAndPastWindowWeeksAreDropped() throws {
        XCTAssertEqual(
            BrowseCategoryLink402A.orderedAll.map(\.label),
            ["Entertainment", "Tech and business", "Economics", "Weather", "Politics"]
        )

        let dec = JSONDecoder()
        dec.keyDecodingStrategy = .convertFromSnakeCase
        let nflSeason = ContainerDiscoveryLeague.nfl.season(asOf: Date())
        let response = try dec.decode(ContainerDiscoveryResponse.self, from: Data("""
        {
          "collections": [
            {
              "type": "collection",
              "id": 9101,
              "slug": "nfl-\(nflSeason)-week-11",
              "name": "NFL Week 11",
              "text": "NFL \(nflSeason) · Week 11",
              "state": "published",
              "revision": 10,
              "edition": {"kind": "nfl_week", "league": "nfl", "season": \(nflSeason), "stage": "Regular Season", "week": 11},
              "status": "scheduled",
              "window_end": "2020-01-01T00:00:00Z",
              "game_count": 14,
              "question_count": 230,
              "matched_event_ids": [],
              "destination": {"kind": "container", "slug": "nfl-\(nflSeason)-week-11", "api": "/api/containers/nfl-\(nflSeason)-week-11"}
            },
            {
              "type": "collection",
              "id": 9103,
              "slug": "nfl-\(nflSeason)-week-13",
              "name": "NFL Week 13",
              "text": "NFL \(nflSeason) · Week 13 · Dec 3–7",
              "state": "published",
              "revision": 12,
              "edition": {"kind": "nfl_week", "league": "nfl", "season": \(nflSeason), "stage": "Regular Season", "week": 13},
              "status": "scheduled",
              "window_end": "2099-12-31T00:00:00Z",
              "game_count": 16,
              "question_count": 180,
              "matched_event_ids": [],
              "destination": {"kind": "container", "slug": "nfl-\(nflSeason)-week-13", "api": "/api/containers/nfl-\(nflSeason)-week-13"}
            }
          ]
        }
        """.utf8))
        let request = ContainerDiscoveryRequest(league: .nfl, season: nflSeason)
        let kept = request.entries(in: response, asOf: Date())
        XCTAssertEqual(kept.map(\.id), ["nfl-\(nflSeason)-week-13"])
    }

    func testExtractsLivePublicMachinerySetsAndConfiguresTechFeedMode() throws {
        XCTAssertNil(SportCategoryViewModel.feedMode(for: "tech"))
        XCTAssertEqual(SportCategoryViewModel.feedMode(for: "tennis_atp"), "sports")
        XCTAssertFalse(SportCategoryViewModel.loadsLeagueMarkets(for: "tech"))
        XCTAssertTrue(SportCategoryViewModel.loadsLeagueMarkets(for: "nba"))

        let feedJSON = #"""
        {
          "items": [
            {
              "type": "bundle",
              "data": {
                "id": "roundup:by-november-30",
                "title": "By November 30",
                "kind": "roundup",
                "collection_ref": {"slug": "by-november-30", "name": "By November 30", "revision": 1, "collection_count": 4},
                "roundup": {"kicker": "TIMEFRAME", "footer": "", "rows": []},
                "items": []
              }
            },
            {
              "type": "bundle",
              "data": {
                "id": "roundup:machinery-2026-summed-up",
                "title": "Bad Bunny leads 2026 Summed Up",
                "kind": "roundup",
                "image_url": "https://example.invalid/set-2026.jpg",
                "collection_ref": {"slug": "machinery-2026-summed-up", "name": "2026 Summed Up", "revision": 12, "collection_count": 9},
                "roundup": {"kicker": "CULTURE", "footer": "", "rows": []},
                "items": []
              }
            },
            {
              "type": "bundle",
              "data": {
                "id": "roundup:machinery-next-james-bond",
                "title": "Margaret Qualley leads Bond",
                "kind": "roundup",
                "image_url": "https://example.invalid/set-bond.jpg",
                "collection_ref": {"slug": "machinery-next-james-bond", "name": "The Next James Bond Film", "revision": 14, "collection_count": 7},
                "roundup": {"kicker": "ENTERTAINMENT", "footer": "", "rows": []},
                "items": []
              }
            },
            {
              "type": "bundle",
              "data": {
                "id": "roundup:machinery-2026-summed-up",
                "title": "Duplicate entry must dedup",
                "kind": "roundup",
                "collection_ref": {"slug": "machinery-2026-summed-up", "name": "2026 Summed Up", "revision": 12, "collection_count": 9},
                "roundup": {"kicker": "CULTURE", "footer": "", "rows": []},
                "items": []
              }
            },
            {
              "type": "bundle",
              "data": {
                "id": "roundup:machinery-ai-model-leaderboard-2026",
                "title": "A new Claude Opus leads",
                "kind": "roundup",
                "image_url": "https://example.invalid/set-ai.jpg",
                "collection_ref": {"slug": "machinery-ai-model-leaderboard-2026", "name": "AI Model Leaderboard", "revision": 21, "collection_count": 7},
                "roundup": {"kicker": "TECH · AI", "footer": "", "rows": []},
                "items": []
              }
            }
          ],
          "total": 5,
          "limit": 80,
          "offset": 0,
          "has_more": false
        }
        """#
        let dec = JSONDecoder()
        dec.keyDecodingStrategy = .convertFromSnakeCase
        let feed = try dec.decode(FeedResponse.self, from: Data(feedJSON.utf8))
        let sets = BrowsePublicSet402A.extractFromFeedItems(feed.items, limit: 8)
        XCTAssertEqual(sets.map(\.slug), [
            "machinery-2026-summed-up",
            "machinery-next-james-bond",
            "machinery-ai-model-leaderboard-2026",
        ])
        XCTAssertEqual(sets[0].title, "2026 Summed Up")
        XCTAssertEqual(sets[0].subtitle, "Culture · 9 markets")
        XCTAssertEqual(sets[0].imageURL?.absoluteString, "https://example.invalid/set-2026.jpg")
        XCTAssertEqual(sets[2].subtitle, "AI · 7 markets")
    }

    func testBrowseHome402ASelfContainedSetsCategoriesDestinationsAndSearchPills390LightDark() async throws {
        let dec = JSONDecoder()
        dec.keyDecodingStrategy = .convertFromSnakeCase
        let emptyDiscovery = try dec.decode(ContainerDiscoveryResponse.self, from: Data(#"{"collections":[]}"#.utf8))
        let svc = StaticDiscovery402A(response: emptyDiscovery)

        let setSpecs: [(slug: String, title: String, subtitle: String, symbol: String, top: UIColor, bottom: UIColor)] = [
            ("machinery-2026-summed-up", "2026 Summed Up", "Culture · 9 markets", "sparkles", .systemIndigo, .systemPurple),
            ("machinery-next-james-bond", "The Next James Bond Film", "Entertainment · 7 markets", "film.fill", UIColor(red: 0.16, green: 0.22, blue: 0.32, alpha: 1.0), .darkGray),
            ("machinery-chess-milestones-and-curiosities", "Chess Milestones & Curiosities", "Odds & Chess · 5 markets", "checkerboard.rectangle", .systemBrown, .systemOrange),
            ("machinery-oscars-best-picture", "Oscars Best Picture", "The Oscars · 8 markets", "trophy.fill", .systemRed, .systemOrange),
            ("machinery-ai-model-leaderboard-2026", "AI Model Leaderboard", "Tech & AI · 7 markets", "cpu.fill", .systemBlue, .systemTeal),
            ("machinery-space-race", "Race to the Moon & Mars", "Tech & Space · 8 markets", "moon.stars.fill", .systemBlue, .black),
            ("machinery-stage-and-cover", "Stage & Cover", "Entertainment · 6 markets", "music.mic", .systemPink, .systemPurple),
            ("machinery-long-shots", "Long Shots", "Long Shots · 14 markets", "scope", .systemTeal, .systemGreen),
        ]

        let publicSets = setSpecs.map {
            BrowsePublicSet402A(slug: $0.slug, title: $0.title, subtitle: $0.subtitle, imageURL: nil)
        }
        let setImages = Dictionary(
            uniqueKeysWithValues: setSpecs.map {
                ($0.slug, Image(uiImage: Self.makeSetArtImage(symbol: $0.symbol, topColor: $0.top, bottomColor: $0.bottom)))
            }
        )
        let setsSvc = StaticPublicSets402A(sets: publicSets)

        let entJSON = #"""
        {
          "total_markets": 100,
          "updated_at": "2026-11-26T12:41:00Z",
          "trending": [
            {
              "q": "Oscar Winner: Best Picture",
              "prob": 52.5,
              "src": "kalshi",
              "market_id": 6173044,
              "external_id": "KXOSCARPIC-27",
              "kind": "multi",
              "top_outcomes": [
                {"name": "The Odyssey", "prob": 52.5, "delta_24h": 0.0},
                {"name": "You Can See Everything", "prob": 23.5, "delta_24h": -1.0},
                {"name": "Dune: Part Three", "prob": 10.5, "delta_24h": 0.0}
              ],
              "outcome_count": 41,
              "volume_24h": 128866,
              "resolution_date": "2027-12-31T15:00:00Z",
              "image_url": null,
              "hook": null
            },
            {
              "q": "GTA VI Online released by...?",
              "prob": 50.5,
              "src": "polymarket",
              "market_id": 69851943,
              "external_id": "1353351",
              "kind": "multi",
              "top_outcomes": [
                {"name": "June 30, 2027", "prob": 50.5, "delta_24h": 0.0},
                {"name": "March 31, 2027", "prob": 18.5, "delta_24h": 0.0},
                {"name": "December 31, 2026", "prob": 4.5, "delta_24h": 0.0}
              ],
              "outcome_count": 3,
              "volume_24h": 13375,
              "resolution_date": "2027-07-01T03:59:00Z",
              "image_url": null,
              "hook": null
            },
            {
              "q": "\"Hexed\" 5-Day Opening Weekend Box Office",
              "prob": 38.0,
              "src": "kalshi",
              "market_id": 71029001,
              "external_id": "KXHEXED-26",
              "kind": "multi",
              "top_outcomes": [
                {"name": "32m–36m", "prob": 38.0, "delta_24h": 2.0},
                {"name": "36m–40m", "prob": 32.0, "delta_24h": 1.0},
                {"name": "40m–44m", "prob": 13.0, "delta_24h": -1.0}
              ],
              "outcome_count": 8,
              "volume_24h": 18200,
              "resolution_date": "2026-11-29T23:59:00Z",
              "image_url": null,
              "hook": null
            }
          ],
          "themes": {},
          "cultural_moments": [],
          "by_source": {"kalshi": 42, "polymarket": 58}
        }
        """#
        let entResponse = try dec.decode(EntertainmentResponse.self, from: Data(entJSON.utf8))

        let techFeedJSON = #"""
        {
          "items": [
            {
              "type": "futures",
              "score": 94,
              "data": {
                "id": 63522628,
                "name": "Which company has the best AI model on LiveBench (Coding) end of November?",
                "llm_sport_category": "tech",
                "source": "polymarket",
                "source_count": 1,
                "sources": ["polymarket"],
                "market_type": "field",
                "status": "open",
                "resolution_date": "2026-12-01T04:59:00+00:00",
                "top_outcomes": [
                  {"id": 239520644, "name": "OpenAI", "probability": 0.67, "rendered_percent": 67, "rank": 1},
                  {"id": 239504971, "name": "Google", "probability": 0.10, "rendered_percent": 10, "rank": 2},
                  {"id": 239579513, "name": "Meta", "probability": 0.08, "rendered_percent": 8, "rank": 3}
                ]
              }
            },
            {
              "type": "futures",
              "score": 89,
              "data": {
                "id": 63522629,
                "name": "Will OpenAI complete an IPO before 2027?",
                "llm_sport_category": "tech",
                "source": "kalshi",
                "source_count": 1,
                "sources": ["kalshi"],
                "market_type": "binary",
                "status": "open",
                "resolution_date": "2027-01-01T00:00:00+00:00",
                "top_outcomes": [
                  {"id": 3001, "name": "Yes", "probability": 0.42, "rendered_percent": 42, "rank": 1, "movement": 0.03}
                ]
              }
            },
            {
              "type": "futures",
              "score": 86,
              "data": {
                "id": 63522630,
                "name": "Next frontier coding model leader in 2026",
                "llm_sport_category": "tech",
                "source": "polymarket",
                "source_count": 1,
                "sources": ["polymarket"],
                "market_type": "field",
                "status": "open",
                "resolution_date": "2026-12-31T23:59:00+00:00",
                "top_outcomes": [
                  {"id": 4001, "name": "Anthropic", "probability": 0.56, "rendered_percent": 56, "rank": 1},
                  {"id": 4002, "name": "Google Gemini", "probability": 0.28, "rendered_percent": 28, "rank": 2}
                ]
              }
            }
          ],
          "total": 3,
          "limit": 50,
          "offset": 0,
          "has_more": false
        }
        """#
        let techFeed = try dec.decode(FeedResponse.self, from: Data(techFeedJSON.utf8))
        let techVM = SportCategoryViewModel(categoryKey: "tech")
        techVM.setItemsForTesting(techFeed.items, leagueMarkets: nil)
        XCTAssertFalse(techVM.drawsNoRows)
        XCTAssertEqual(techVM.topMarkets.count, 3)

        let outPath = ProcessInfo.processInfo.environment["TEST_RUNNER_BUILDER_C_RENDER_402A_DIR"]
            ?? ProcessInfo.processInfo.environment["BUILDER_C_RENDER_402A_DIR"]
        if let outPath, !outPath.isEmpty {
            try FileManager.default.createDirectory(atPath: outPath, withIntermediateDirectories: true)
        }

        for (scheme, sTag) in [(ColorScheme.light, "light"), (ColorScheme.dark, "dark")] {
            // 1. Browse using previewPublicSetsService (with previewSets == []) to prove async set loading + artwork
            let browseImg = await render390(
                view: LeaguesView(
                    previewDiscoveryService: svc,
                    previewSets: [],
                    preloadedSetImages: setImages,
                    previewPublicSetsService: setsSvc
                ),
                scheme: scheme,
                height: 1920
            )
            let browseOCR = try ocrLines(browseImg)
                .joined(separator: " ")
                .replacingOccurrences(of: "Al ", with: "AI ")
            XCTAssertFalse(browseOCR.localizedCaseInsensitiveContains("LIVE SETS"), "Browse (\(sTag)) still says LIVE SETS: \(browseOCR)")
            XCTAssertFalse(browseOCR.localizedCaseInsensitiveContains("NFL Week 12"), "Browse (\(sTag)) still shows finished NFL Week 12: \(browseOCR)")
            for token in [
                "Sets, categories, and leagues",
                "SETS",
                "2026 Summed Up",
                "The Next James Bond Film",
                "Chess Milestones & Curiosities",
                "Oscars Best Picture",
                "AI Model Leaderboard",
                "Race to the Moon & Mars",
                "Stage & Cover",
                "Long Shots",
                "CATEGORIES",
                "Entertainment",
                "Tech and business",
                "Economics",
                "Weather",
                "Politics",
                "NBA",
            ] {
                XCTAssertTrue(browseOCR.localizedCaseInsensitiveContains(token), "Browse (\(sTag)) missing '\(token)' in \(browseOCR)")
            }

            // 2. Search empty state using publicSetsService (with previewSets == [])
            let searchImg = await render390(
                view: NavigationStack {
                    SearchView(discoveryService: svc, previewSets: [], publicSetsService: setsSvc)
                },
                scheme: scheme,
                height: 1180
            )
            let searchOCR = try ocrLines(searchImg).joined(separator: " ")
            XCTAssertFalse(searchOCR.localizedCaseInsensitiveContains("LIVE SETS"), "Search (\(sTag)) still says LIVE SETS: \(searchOCR)")
            XCTAssertFalse(searchOCR.localizedCaseInsensitiveContains("NFL Week 12"), "Search (\(sTag)) still shows NFL Week 12: \(searchOCR)")
            XCTAssertFalse(searchOCR.localizedCaseInsensitiveContains("US Open"), "Search (\(sTag)) leaked finished US Open")
            for token in ["SETS", "2026 Summed Up", "Oscars Best Picture", "CATEGORIES", "Entertainment", "Tech and business", "Economics", "Weather", "Politics", "NBA"] {
                XCTAssertTrue(searchOCR.localizedCaseInsensitiveContains(token), "Search (\(sTag)) missing '\(token)' in \(searchOCR)")
            }

            // 3. Category destination: Entertainment
            let entImg = await render390(
                view: NavigationStack { EntertainmentView(preloadedData: entResponse) },
                scheme: scheme,
                height: 920
            )
            let entOCR = try ocrLines(entImg).joined(separator: " ")
            XCTAssertTrue(entOCR.localizedCaseInsensitiveContains("Entertainment"), "Entertainment destination (\(sTag)) missing header: \(entOCR)")
            XCTAssertTrue(entOCR.localizedCaseInsensitiveContains("The Odyssey"), "Entertainment destination (\(sTag)) missing market row: \(entOCR)")
            XCTAssertFalse(entOCR.contains("…"), "Entertainment destination (\(sTag)) clipped text: \(entOCR)")

            // 4. Category destination: Tech and business
            let techImg = await render390(
                view: NavigationStack {
                    SportCategoryView(
                        categoryKey: "tech",
                        categoryName: "Tech and business",
                        preloadedViewModel: techVM
                    )
                },
                scheme: scheme,
                height: 920
            )
            let techOCR = try ocrLines(techImg)
                .joined(separator: " ")
                .replacingOccurrences(of: "OpenAl", with: "OpenAI")
                .replacingOccurrences(of: "Al ", with: "AI ")
            XCTAssertFalse(techOCR.localizedCaseInsensitiveContains("No Tech and business Right Now"), "Tech destination (\(sTag)) rendered empty state: \(techOCR)")
            for token in ["Tech and business", "Markets", "OpenAI", "67%"] {
                XCTAssertTrue(techOCR.localizedCaseInsensitiveContains(token), "Tech destination (\(sTag)) missing '\(token)': \(techOCR)")
            }
            XCTAssertFalse(techOCR.contains("…"), "Tech destination (\(sTag)) clipped text: \(techOCR)")

            if let outPath, !outPath.isEmpty {
                let dir = URL(fileURLWithPath: outPath, isDirectory: true)
                if let p1 = browseImg.pngData() { try p1.write(to: dir.appendingPathComponent("browse-v3-\(sTag)-390.png")) }
                if let p2 = searchImg.pngData() { try p2.write(to: dir.appendingPathComponent("search-v3-\(sTag)-390.png")) }
                if let p3 = entImg.pngData() { try p3.write(to: dir.appendingPathComponent("entertainment-v3-\(sTag)-390.png")) }
                if let p4 = techImg.pngData() { try p4.write(to: dir.appendingPathComponent("tech-v3-\(sTag)-390.png")) }
            }
        }
    }

    private func render390<V: View>(
        view: V,
        scheme: ColorScheme,
        height: CGFloat
    ) async -> UIImage {
        let bg = scheme == .dark ? Color.black : Color(UIColor.systemGroupedBackground)
        let wrapped = view
            .frame(width: 390, height: height, alignment: .topLeading)
            .background(bg)
            .environment(\.horizontalSizeClass, .compact)
            .environment(\.colorScheme, scheme)
            .environment(\.dynamicTypeSize, .large)
            .environmentObject(NavigationCoordinator())
            .environmentObject(PinManager(defaults: .standard, allowLegacyGuestPins: false))
            .environmentObject(AuthManager(restoreOnInit: false))

        let host = hostForMeasurement(wrapped, at: .large)
        let traits = UITraitCollection(traitsFrom: [
            UITraitCollection(horizontalSizeClass: .compact),
            UITraitCollection(userInterfaceStyle: scheme == .dark ? .dark : .light),
            UITraitCollection(preferredContentSizeCategory: .large),
        ])
        let container = Browse402ATraitContainer(child: host, traits: traits)
        let frame = CGRect(x: 0, y: 0, width: 390, height: height)
        container.view.frame = frame

        let scene = UIApplication.shared.connectedScenes.compactMap { $0 as? UIWindowScene }.first
        let window: UIWindow = scene.map { UIWindow(windowScene: $0) } ?? UIWindow(frame: frame)
        window.frame = frame
        window.overrideUserInterfaceStyle = scheme == .dark ? .dark : .light
        window.rootViewController = container
        window.isHidden = false
        window.makeKeyAndVisible()
        defer {
            window.isHidden = true
            window.rootViewController = nil
        }

        for _ in 0..<8 {
            container.view.setNeedsLayout()
            container.view.layoutIfNeeded()
            try? await Task.sleep(for: .milliseconds(80))
        }

        let fmt = UIGraphicsImageRendererFormat()
        fmt.scale = 2.0
        fmt.opaque = true
        return UIGraphicsImageRenderer(size: frame.size, format: fmt).image { _ in
            container.view.drawHierarchy(in: container.view.bounds, afterScreenUpdates: true)
        }
    }

    private func ocrLines(_ image: UIImage) throws -> [String] {
        guard let cg = image.cgImage else { return [] }
        if cg.height <= 1800 {
            let req = VNRecognizeTextRequest()
            req.recognitionLevel = .accurate
            req.usesLanguageCorrection = false
            try VNImageRequestHandler(cgImage: cg, options: [:]).perform([req])
            return (req.results ?? []).compactMap { $0.topCandidates(1).first?.string }
        }
        var lines: [String] = []
        var yStart = 0
        while yStart < cg.height {
            let h = min(1400, cg.height - yStart)
            guard let slice = cg.cropping(to: CGRect(x: 0, y: yStart, width: cg.width, height: h)) else { break }
            let req = VNRecognizeTextRequest()
            req.recognitionLevel = .accurate
            req.usesLanguageCorrection = false
            try VNImageRequestHandler(cgImage: slice, options: [:]).perform([req])
            lines.append(contentsOf: (req.results ?? []).compactMap { $0.topCandidates(1).first?.string })
            if yStart + h >= cg.height { break }
            yStart += 1000
        }
        return lines
    }
}
