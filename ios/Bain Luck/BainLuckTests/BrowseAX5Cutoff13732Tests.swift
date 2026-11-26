import SwiftUI
import UIKit
import Vision
import XCTest
@testable import Bain_Luck

@MainActor
final class BrowseAX5Cutoff13732Tests: XCTestCase {

    private final class BrowseTraitContainer: UIViewController {
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

    func testBrowseFeatureCardsAndLeagueTilesAX5NoTruncationAt390And320() async throws {
        let outPath = "/Users/bain/.gemini/antigravity/brain/4c590449-f20c-4ff4-921d-f7e1343a4327/scratch/cutoff-13732"
        let shouldWrite = FileManager.default.fileExists(atPath: outPath)

        let browseView = LeaguesView()
        let leagueListView = LeaguesView.leagueTilesSampleForTest()

        for width in [390, 320] {
            let topHeight: CGFloat = width < 360 ? 2100 : 1650
            for (scheme, tag) in [(ColorScheme.light, "light"), (ColorScheme.dark, "dark")] {
                let topImage = await renderPanel(view: browseView, width: CGFloat(width), height: topHeight, scheme: scheme)
                let tileImage = await renderPanel(view: leagueListView, width: CGFloat(width), height: 1550, scheme: scheme)

                if shouldWrite {
                    let dir = URL(fileURLWithPath: outPath, isDirectory: true)
                    if let png = topImage.pngData() {
                        try png.write(to: dir.appendingPathComponent("after-top-\(width)-\(tag)-ax5.png"))
                    }
                    if let png = tileImage.pngData() {
                        try png.write(to: dir.appendingPathComponent("after-tiles-\(width)-\(tag)-ax5.png"))
                    }
                }

                let topLines = try ocrLines(topImage)
                let topEllipses = topLines.filter { $0.contains("...") || $0.contains("\u{2026}") }
                XCTAssertTrue(topEllipses.isEmpty, "Browse feature cards ellipsized at \(width) \(tag): \(topEllipses) in \(topLines)")
                let topCompact = topLines.joined().lowercased().replacingOccurrences(of: "-", with: "").replacingOccurrences(of: " ", with: "")
                for token in ["prediction", "markets", "track", "record", "methodology"] {
                    XCTAssertTrue(topCompact.contains(token), "Missing Browse feature copy '\(token)' at \(width) \(tag): \(topLines)")
                }

                let tileLines = try ocrLines(tileImage)
                let tileEllipses = tileLines.filter { $0.contains("...") || $0.contains("\u{2026}") }
                XCTAssertTrue(tileEllipses.isEmpty, "Browse league tiles ellipsized at \(width) \(tag): \(tileEllipses) in \(tileLines)")
                let tileCompact = tileLines.joined().lowercased().replacingOccurrences(of: "-", with: "").replacingOccurrences(of: " ", with: "")
                for token in ["nba", "mlb", "nhl", "women", "basketball", "ucl", "europe"] {
                    XCTAssertTrue(tileCompact.contains(token), "Missing league tile copy '\(token)' at \(width) \(tag): \(tileLines)")
                }
            }
        }
    }

    private func renderPanel<V: View>(
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
        let container = BrowseTraitContainer(child: host, traits: traits)
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
