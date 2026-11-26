import SwiftUI
import UIKit
import Vision
import XCTest
@testable import Bain_Luck

@MainActor
final class MyStuff320AX5Cutoff13733Tests: XCTestCase {

    private final class MyStuffTraitContainer: UIViewController {
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

    func testMyStuffStripAndGameCard320AX5NoTruncation() async throws {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let feed = try decoder.decode(FeedResponse.self, from: Data("""
        {
          "items": [
            {"type":"event","score":92,"data":{"id":9002,"sport":"americanfootball_nfl","sport_name":"NFL","away_team":"Washington Commanders","home_team":"Tampa Bay Buccaneers","status":"live","away_score":17,"home_score":21,"commence_time":"2026-11-24T22:00:00Z","espn":{"period":"Q4","clock":"4:15"},"current_odds":{"home_probability":0.64,"away_probability":0.36,"home_rendered_percent":64,"away_rendered_percent":36}}}
          ],
          "total": 1, "limit": 12, "offset": 0, "has_more": false
        }
        """.utf8))
        let events = feed.items.compactMap(\.event)

        let suite = "Cutoff13733.\(UUID().uuidString)"
        let defaults = UserDefaults(suiteName: suite)!
        defer { defaults.removePersistentDomain(forName: suite) }

        let checklistStore = FirstRunChecklistStore364A(defaults: defaults)
        checklistStore.state = FirstRunChecklistState364A(
            completedRows: [.lookUp, .follow],
            selectedSetSlugs: [],
            followedCount: 2,
            dismissedFromMyStuff: true
        )
        let followMgr = FollowManager295A(defaults: defaults, initialSubjects: [
            .team(slug: "boston-celtics", teamId: 100, name: "Boston Celtics", sportKey: "basketball_nba"),
            .team(slug: "washington-commanders", teamId: 28, name: "Washington Commanders", sportKey: "americanfootball_nfl")
        ])
        var snap = MyStuffLandingViewModel295A.PreloadedSnapshot()
        snap.liveEvents = events.map { ($0, false) }

        let outPath = "/Users/bain/.gemini/antigravity/brain/4c590449-f20c-4ff4-921d-f7e1343a4327/scratch/cutoff-13733"
        let shouldWrite = FileManager.default.fileExists(atPath: outPath)

        for width in [390, 320] {
            for (scheme, tag) in [(ColorScheme.light, "light"), (ColorScheme.dark, "dark")] {
                let view = MyStuffView(preloadedLandingForTest: snap)
                    .environment(\.firstRunChecklistStore364A, checklistStore)
                    .environment(\.followManager295A, followMgr)
                let img = await renderMyStuff(
                    view: view,
                    width: CGFloat(width),
                    height: width < 360 ? 1500 : 1250,
                    scheme: scheme
                )
                if shouldWrite {
                    let dir = URL(fileURLWithPath: outPath, isDirectory: true)
                    if let png = img.pngData() {
                        try png.write(to: dir.appendingPathComponent("after-\(width)-\(tag)-ax5.png"))
                    }
                }
                let lines = try ocrLines(img)
                let ellipses = lines.filter { $0.contains("...") || $0.contains("\u{2026}") }
                XCTAssertTrue(ellipses.isEmpty, "Unexpected ellipsis on My Stuff at \(width) \(tag) AX5: \(ellipses) in \(lines)")
                let joined = lines.joined(separator: " ").lowercased().replacingOccurrences(of: "- ", with: "")
                for expected in ["boston", "celtics", "commanders", "buccaneers"] {
                    XCTAssertTrue(joined.contains(expected), "Missing '\(expected)' at \(width) \(tag) AX5 in \(lines)")
                }
            }
        }
    }

    private func renderMyStuff<V: View>(
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
        let container = MyStuffTraitContainer(child: host, traits: traits)
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
