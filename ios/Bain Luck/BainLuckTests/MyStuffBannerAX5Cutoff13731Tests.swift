import SwiftUI
import UIKit
import Vision
import XCTest
@testable import Bain_Luck

@MainActor
final class MyStuffBannerAX5Cutoff13731Tests: XCTestCase {

    private final class BannerTraitContainer: UIViewController {
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

    func testMyStuffChecklistBannerAX5NoTruncationAt390And320() async throws {
        let checklistState = FirstRunChecklistState364A(
            completedRows: [.lookUp, .follow],
            selectedSetSlugs: [],
            followedCount: 2,
            dismissedFromMyStuff: false
        )
        XCTAssertTrue(checklistState.showsInMyStuff)

        let outPath = "/Users/bain/.gemini/antigravity/brain/4c590449-f20c-4ff4-921d-f7e1343a4327/scratch/cutoff-13731"
        let shouldWrite = FileManager.default.fileExists(atPath: outPath)

        for width in [390, 320] {
            let panelHeight: CGFloat = width < 360 ? 1550 : 1200
            for (scheme, tag) in [(ColorScheme.light, "light"), (ColorScheme.dark, "dark")] {
                let image = await renderBanner(
                    state: checklistState,
                    width: CGFloat(width),
                    height: panelHeight,
                    scheme: scheme
                )
                if shouldWrite {
                    let dir = URL(fileURLWithPath: outPath, isDirectory: true)
                    if let png = image.pngData() {
                        try png.write(to: dir.appendingPathComponent("after-\(width)-\(tag)-ax5.png"))
                    }
                }

                let lines = try ocrLines(image)
                let ellipses = lines.filter { $0.contains("...") || $0.contains("\u{2026}") }
                XCTAssertTrue(
                    ellipses.isEmpty,
                    "Unexpected ellipsis at \(width) \(tag) AX5: \(ellipses) (all lines: \(lines))"
                )
                let joined = lines
                    .joined(separator: " ")
                    .lowercased()
                    .replacingOccurrences(of: "- ", with: "")
                for token in ["getting", "started", "look", "anything", "follow", "world", "devices", "headsup"] {
                    let normalizedJoined = joined.replacingOccurrences(of: "heads-up", with: "headsup")
                    XCTAssertTrue(
                        normalizedJoined.contains(token),
                        "Missing wrapped token '\(token)' at \(width) \(tag) AX5 in \(lines)"
                    )
                }
            }
        }
    }

    private func renderBanner(
        state: FirstRunChecklistState364A,
        width: CGFloat,
        height: CGFloat,
        scheme: ColorScheme
    ) async -> UIImage {
        let bg = scheme == .dark ? Color.black : Color(UIColor.systemGroupedBackground)
        let view = VStack(alignment: .leading, spacing: 12) {
            MyStuffChecklistBanner364A(state: .constant(state))
        }
        .padding(16)
        .frame(width: width, height: height, alignment: .topLeading)
        .background(bg)
        .environment(\.horizontalSizeClass, .compact)
        .environment(\.colorScheme, scheme)
        .environment(\.dynamicTypeSize, .accessibility5)

        let host = hostForMeasurement(view, at: .accessibility5)
        let traits = UITraitCollection(traitsFrom: [
            UITraitCollection(horizontalSizeClass: .compact),
            UITraitCollection(userInterfaceStyle: scheme == .dark ? .dark : .light),
            UITraitCollection(preferredContentSizeCategory: .accessibilityExtraExtraExtraLarge)
        ])
        let container = BannerTraitContainer(child: host, traits: traits)
        let frame = CGRect(x: 0, y: 0, width: width, height: height)
        container.view.frame = frame

        let scene = UIApplication.shared.connectedScenes.compactMap { $0 as? UIWindowScene }.first
        let window: UIWindow = scene.map { UIWindow(windowScene: $0) } ?? UIWindow(frame: frame)
        window.frame = frame
        window.overrideUserInterfaceStyle = scheme == .dark ? .dark : .light
        window.rootViewController = container
        window.isHidden = false
        window.makeKeyAndVisible()

        for _ in 0..<4 {
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
