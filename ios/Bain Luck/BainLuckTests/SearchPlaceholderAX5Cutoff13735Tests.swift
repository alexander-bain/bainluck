import SwiftUI
import UIKit
import Vision
import XCTest
@testable import Bain_Luck

@MainActor
final class SearchPlaceholderAX5Cutoff13735Tests: XCTestCase {

    private final class SearchTraitContainer: UIViewController {
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

    func testSearchPlaceholderDoesNotClipAt390And320AX5() async throws {
        let outPath = "/Users/bain/.gemini/antigravity/brain/4c590449-f20c-4ff4-921d-f7e1343a4327/scratch/cutoff-13735"
        let shouldWrite = FileManager.default.fileExists(atPath: outPath)

        for width in [390, 320] {
            for (scheme, tag) in [(ColorScheme.light, "light"), (ColorScheme.dark, "dark")] {
                let view = NavigationStack { SearchView() }
                let (img, clipped) = await renderSearch(view: view, width: CGFloat(width), height: 1100, scheme: scheme)
                if shouldWrite {
                    let dir = URL(fileURLWithPath: outPath, isDirectory: true)
                    if let png = img.pngData() {
                        try png.write(to: dir.appendingPathComponent("after-\(width)-\(tag)-ax5.png"))
                    }
                }
                XCTAssertTrue(clipped.isEmpty, "Search placeholder / labels clipped at \(width) \(tag) AX5: \(clipped)")
                let lines = try ocrLines(img)
                let searchEllipses = lines.filter { $0.contains("...") || $0.contains("\u{2026}") }
                XCTAssertTrue(searchEllipses.isEmpty, "Search placeholder ellipsized at \(width) \(tag) AX5: \(searchEllipses) in \(lines)")
            }
        }
    }

    private func renderSearch<V: View>(
        view: V,
        width: CGFloat,
        height: CGFloat,
        scheme: ColorScheme
    ) async -> (image: UIImage, clipped: [String]) {
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
        let container = SearchTraitContainer(child: host, traits: traits)
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

        let clipped = clippedTextLabels(in: container.view)
        let renderer = UIGraphicsImageRenderer(size: frame.size)
        let img = renderer.image { _ in
            container.view.drawHierarchy(in: container.view.bounds, afterScreenUpdates: true)
        }
        return (img, clipped)
    }

    private func clippedTextLabels(in view: UIView) -> [String] {
        var hits: [String] = []
        if let tf = view as? UITextField, let placeholder = tf.attributedPlaceholder ?? tf.placeholder.map({ NSAttributedString(string: $0, attributes: [.font: tf.font ?? UIFont.preferredFont(forTextStyle: .body)]) }) {
            let needed = placeholder.boundingRect(with: CGSize(width: CGFloat.greatestFiniteMagnitude, height: tf.bounds.height), options: [], context: nil)
            if needed.width > tf.bounds.width + 2 {
                hits.append("UITextField placeholder '\(placeholder.string)' [\(Int(tf.bounds.width)) vs \(Int(ceil(needed.width)))]")
            }
        }
        for sub in view.subviews {
            hits.append(contentsOf: clippedTextLabels(in: sub))
        }
        return hits
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
