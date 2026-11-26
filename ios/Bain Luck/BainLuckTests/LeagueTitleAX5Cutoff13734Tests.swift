import SwiftUI
import UIKit
import Vision
import XCTest
@testable import Bain_Luck

@MainActor
final class LeagueTitleAX5Cutoff13734Tests: XCTestCase {

    private final class LeagueTraitContainer: UIViewController {
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

    func testChampionsLeagueTitleWrapsWithoutTruncationAt390And320AX5() async throws {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let markets = try decoder.decode(LeagueMarketsResponse.self, from: Data("""
        {
          "sport_key": "soccer_uefa_champs_league",
          "total_markets": 1,
          "sections": {},
          "upcoming_games": [
            {
              "id": 9153501,
              "sport": "soccer_uefa_champs_league",
              "home_team": "Wolverhampton Wanderers",
              "away_team": "Borussia Monchengladbach",
              "commence_time": "2099-11-26T20:00:00Z",
              "status": "scheduled",
              "current_odds": {"home_probability": 0.44, "away_probability": 0.29, "draw_probability": 0.27}
            }
          ]
        }
        """.utf8))
        let grid = try decoder.decode(ChampionshipGridResponse.self, from: Data("""
        {
          "league": "soccer_uefa_champs_league",
          "name": "Champions League",
          "season": "Season 2026-27",
          "columns": [],
          "teams": [],
          "movers": [],
          "team_count": 0,
          "sources_available": ["kalshi", "polymarket"]
        }
        """.utf8))

        let outPath = "/Users/bain/.gemini/antigravity/brain/4c590449-f20c-4ff4-921d-f7e1343a4327/scratch/cutoff-13734"
        let shouldWrite = FileManager.default.fileExists(atPath: outPath)

        for width in [390, 320] {
            for (scheme, tag) in [(ColorScheme.light, "light"), (ColorScheme.dark, "dark")] {
                let vm = LeagueGridViewModel(
                    slug: "champions-league",
                    preloadedGrid: grid,
                    preloadedMarkets: markets
                )
                let view = NavigationStack {
                    LeagueGridView(slug: "champions-league", preloadedViewModel: vm)
                }
                let img = await renderLeague(view: view, width: CGFloat(width), height: 1320, scheme: scheme)
                if shouldWrite {
                    let dir = URL(fileURLWithPath: outPath, isDirectory: true)
                    if let png = img.pngData() {
                        try png.write(to: dir.appendingPathComponent("after-\(width)-\(tag)-ax5.png"))
                    }
                }
                let lines = try ocrLines(img)
                let headerEllipses = lines.filter { $0.contains("Champ") && ($0.contains("...") || $0.contains("\u{2026}")) }
                XCTAssertTrue(headerEllipses.isEmpty, "League title truncated at \(width) \(tag) AX5: \(lines)")
                let compact = lines.joined().lowercased().replacingOccurrences(of: "-", with: "").replacingOccurrences(of: " ", with: "")
                XCTAssertTrue(compact.contains("championsleague"), "Missing full 'Champions League' at \(width) \(tag) AX5 in \(lines)")
            }
        }
    }

    private func renderLeague<V: View>(
        view: V,
        width: CGFloat,
        height: CGFloat,
        scheme: ColorScheme
    ) async -> UIImage {
        let bg = scheme == .dark ? Color.black : Color(UIColor.systemGroupedBackground)
        let wrapped = view
            .frame(width: width, height: height, alignment: .topLeading)
            .background(bg)
            .environment(\.horizontalSizeClass, .compact)
            .environment(\.colorScheme, scheme)
            .environment(\.dynamicTypeSize, .accessibility5)
            .environmentObject(NavigationCoordinator())
            .environmentObject(PinManager(defaults: .standard, allowLegacyGuestPins: false))
            .environmentObject(AuthManager(restoreOnInit: false))

        let host = hostForMeasurement(wrapped, at: .accessibility5)
        let traits = UITraitCollection(traitsFrom: [
            UITraitCollection(horizontalSizeClass: .compact),
            UITraitCollection(userInterfaceStyle: scheme == .dark ? .dark : .light),
            UITraitCollection(preferredContentSizeCategory: .accessibilityExtraExtraExtraLarge)
        ])
        let container = LeagueTraitContainer(child: host, traits: traits)
        let frame = CGRect(x: 0, y: 0, width: width, height: height)
        container.view.frame = frame

        let scene = UIApplication.shared.connectedScenes.compactMap { $0 as? UIWindowScene }.first
        let window: UIWindow = scene.map { UIWindow(windowScene: $0) } ?? UIWindow(frame: frame)
        window.frame = frame
        window.overrideUserInterfaceStyle = scheme == .dark ? .dark : .light
        window.rootViewController = container
        window.isHidden = false
        window.makeKeyAndVisible()

        for _ in 0..<5 {
            container.view.setNeedsLayout()
            container.view.layoutIfNeeded()
            try? await Task.sleep(for: .milliseconds(50))
        }

        let renderer = UIGraphicsImageRenderer(size: frame.size)
        return renderer.image { _ in
            container.view.drawHierarchy(in: container.view.bounds, afterScreenUpdates: true)
        }
    }

    private func ocrLines(_ image: UIImage) throws -> [String] {
        guard let cg = image.cgImage else { return [] }
        let req = VNRecognizeTextRequest()
        req.recognitionLevel = .accurate
        req.usesLanguageCorrection = false
        try VNImageRequestHandler(cgImage: cg, options: [:]).perform([req])
        return (req.results ?? []).compactMap { $0.topCandidates(1).first?.string }
    }
}
