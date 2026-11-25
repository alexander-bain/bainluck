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

    func testBrowseHome402AFirstDraftRendersLiveSetsCategoriesLeaguesAndAlignedSearchPills() async throws {
        let dec = JSONDecoder()
        dec.keyDecodingStrategy = .convertFromSnakeCase
        let nflSeason = ContainerDiscoveryLeague.nfl.season(asOf: Date())
        let sampleDiscovery = try dec.decode(ContainerDiscoveryResponse.self, from: Data("""
        {
          "collections": [
            {
              "type": "collection",
              "id": 9101,
              "slug": "nfl-\(nflSeason)-week-12",
              "name": "NFL Week 12",
              "text": "NFL \(nflSeason) · Week 12 · Nov 25–30",
              "state": "published",
              "revision": 10,
              "edition": {"kind": "nfl_week", "league": "nfl", "season": \(nflSeason), "stage": "Regular Season", "week": 12},
              "status": "active",
              "game_count": 14,
              "question_count": 230,
              "matched_event_ids": [],
              "destination": {"kind": "container", "slug": "nfl-\(nflSeason)-week-12", "api": "/api/containers/nfl-\(nflSeason)-week-12"}
            },
            {
              "type": "collection",
              "id": 9102,
              "slug": "nfl-\(nflSeason)-week-13",
              "name": "NFL Week 13",
              "text": "NFL \(nflSeason) · Week 13 · Dec 2–7",
              "state": "published",
              "revision": 12,
              "edition": {"kind": "nfl_week", "league": "nfl", "season": \(nflSeason), "stage": "Regular Season", "week": 13},
              "status": "active",
              "game_count": 16,
              "question_count": 180,
              "matched_event_ids": [],
              "destination": {"kind": "container", "slug": "nfl-\(nflSeason)-week-13", "api": "/api/containers/nfl-\(nflSeason)-week-13"}
            }
          ]
        }
        """.utf8))
        let svc = StaticDiscovery402A(response: sampleDiscovery)

        let outPath = ProcessInfo.processInfo.environment["BUILDER_C_RENDER_402A_DIR"]
        if let outPath, !outPath.isEmpty {
            try FileManager.default.createDirectory(atPath: outPath, withIntermediateDirectories: true)
        }

        for (scheme, sTag) in [(ColorScheme.light, "light"), (ColorScheme.dark, "dark")] {
            let browseImg = await render390(
                view: LeaguesView(previewDiscoveryService: svc),
                scheme: scheme,
                height: 1220
            )
            let browseOCR = try ocrLines(browseImg).joined(separator: " ")
            for token in ["Sets, categories, and leagues", "LIVE SETS", "NFL Week 12", "NFL Week 13", "CATEGORIES", "Politics", "Entertainment", "Economics", "Weather", "NBA"] {
                XCTAssertTrue(browseOCR.localizedCaseInsensitiveContains(token), "Browse (\(sTag)) missing '\(token)' in \(browseOCR)")
            }

            let searchImg = await render390(
                view: NavigationStack { SearchView(discoveryService: svc) },
                scheme: scheme,
                height: 920
            )
            let searchOCR = try ocrLines(searchImg).joined(separator: " ")
            for token in ["LIVE SETS", "NFL Week 12", "NFL Week 13", "CATEGORIES", "Politics", "Entertainment", "Economics", "Weather", "NBA"] {
                XCTAssertTrue(searchOCR.localizedCaseInsensitiveContains(token), "Search (\(sTag)) missing '\(token)' in \(searchOCR)")
            }
            XCTAssertFalse(searchOCR.localizedCaseInsensitiveContains("US Open"), "Search (\(sTag)) leaked finished US Open")

            if let outPath, !outPath.isEmpty {
                let dir = URL(fileURLWithPath: outPath, isDirectory: true)
                if let p1 = browseImg.pngData() { try p1.write(to: dir.appendingPathComponent("browse-\(sTag)-390.png")) }
                if let p2 = searchImg.pngData() { try p2.write(to: dir.appendingPathComponent("search-\(sTag)-390.png")) }
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
            UITraitCollection(preferredContentSizeCategory: .large)
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

        for _ in 0..<8 {
            container.view.setNeedsLayout()
            container.view.layoutIfNeeded()
            try? await Task.sleep(for: .milliseconds(80))
        }

        let renderer = UIGraphicsImageRenderer(size: frame.size)
        return renderer.image { _ in
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
