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

    private static let v2ScratchDir = "/Users/bain/.gemini/antigravity/brain/4c590449-f20c-4ff4-921d-f7e1343a4327/scratch/13750-v2"

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

    func testBrowseHome402ASecondDraftSetsCategoriesEntertainmentDestinationAndSearchPills() async throws {
        let dec = JSONDecoder()
        dec.keyDecodingStrategy = .convertFromSnakeCase
        let emptyDiscovery = try dec.decode(ContainerDiscoveryResponse.self, from: Data(#"{"collections":[]}"#.utf8))
        let svc = StaticDiscovery402A(response: emptyDiscovery)

        let publicSets: [BrowsePublicSet402A] = [
            BrowsePublicSet402A(slug: "machinery-2026-summed-up", title: "2026 Summed Up", subtitle: "Culture · 9 markets", imageURL: nil),
            BrowsePublicSet402A(slug: "machinery-next-james-bond", title: "The Next James Bond Film", subtitle: "Entertainment · 7 markets", imageURL: nil),
            BrowsePublicSet402A(slug: "machinery-chess-milestones-and-curiosities", title: "Chess Milestones & Curiosities", subtitle: "Odds & Chess · 5 markets", imageURL: nil),
            BrowsePublicSet402A(slug: "machinery-oscars-best-picture", title: "Oscars Best Picture", subtitle: "The Oscars · 8 markets", imageURL: nil),
            BrowsePublicSet402A(slug: "machinery-ai-model-leaderboard-2026", title: "AI Model Leaderboard", subtitle: "Tech & AI · 7 markets", imageURL: nil),
            BrowsePublicSet402A(slug: "machinery-space-race", title: "Race to the Moon & Mars", subtitle: "Tech & Space · 8 markets", imageURL: nil),
            BrowsePublicSet402A(slug: "machinery-stage-and-cover", title: "Stage & Cover", subtitle: "Entertainment · 6 markets", imageURL: nil),
            BrowsePublicSet402A(slug: "machinery-long-shots", title: "Long Shots", subtitle: "Long Shots · 14 markets", imageURL: nil),
        ]

        var setImages: [String: Image] = [:]
        for s in publicSets {
            let p = "\(Self.v2ScratchDir)/set-art/\(s.slug).jpg"
            if let ui = UIImage(contentsOfFile: p) {
                setImages[s.slug] = Image(uiImage: ui)
            }
        }
        XCTAssertEqual(setImages.count, 8, "Expected all 8 downloaded real set cover images in \(Self.v2ScratchDir)/set-art")

        let entDataPath = "\(Self.v2ScratchDir)/live_entertainment.json"
        let entData = try Data(contentsOf: URL(fileURLWithPath: entDataPath))
        let entResponse = try dec.decode(EntertainmentResponse.self, from: entData)

        let outPath = ProcessInfo.processInfo.environment["BUILDER_C_RENDER_402A_DIR"]
        if let outPath, !outPath.isEmpty {
            try FileManager.default.createDirectory(atPath: outPath, withIntermediateDirectories: true)
        }

        for (scheme, sTag) in [(ColorScheme.light, "light"), (ColorScheme.dark, "dark")] {
            let browseImg = await render390(
                view: LeaguesView(previewDiscoveryService: svc, previewSets: publicSets, preloadedSetImages: setImages),
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

            let searchImg = await render390(
                view: NavigationStack { SearchView(discoveryService: svc, previewSets: publicSets) },
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

            let entImg = await render390(
                view: NavigationStack { EntertainmentView(preloadedData: entResponse) },
                scheme: scheme,
                height: 1080
            )
            let entOCR = try ocrLines(entImg).joined(separator: " ")
            XCTAssertTrue(entOCR.localizedCaseInsensitiveContains("Entertainment"), "Entertainment destination (\(sTag)) missing header: \(entOCR)")
            XCTAssertFalse(entOCR.contains("…"), "Entertainment destination (\(sTag)) clipped text: \(entOCR)")

            if let outPath, !outPath.isEmpty {
                let dir = URL(fileURLWithPath: outPath, isDirectory: true)
                if let p1 = browseImg.pngData() { try p1.write(to: dir.appendingPathComponent("browse-v2-\(sTag)-390.png")) }
                if let p2 = searchImg.pngData() { try p2.write(to: dir.appendingPathComponent("search-v2-\(sTag)-390.png")) }
                if let p3 = entImg.pngData() { try p3.write(to: dir.appendingPathComponent("entertainment-v2-\(sTag)-390.png")) }
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
