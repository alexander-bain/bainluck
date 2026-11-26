import SwiftUI
import UIKit
import Vision
import XCTest
@testable import Bain_Luck

/// #13551 — Pile 4 (`contender_spotlight`): three cells side-by-side on Discover cards
/// (`MachineryDiscoverCardView`), using `387: A` initials fallback when any sibling carries
/// verified art and `388: A` no icon on all-text cards, stacking cleanly at `>= .xxxLarge`
/// with zero `"…"` truncation across `390 pt` Light/Dark, `320 pt`, and `.accessibility5`.
@MainActor
final class ContenderSpotlightDiscoverCard13551Tests: XCTestCase {

    private final class FixedTraitContainer: UIViewController {
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

    private let mixedArtSpotlightJSON = #"""
    {
      "slug": "machinery-2028-presidential",
      "form_id": "contender_spotlight",
      "stage": "public",
      "kicker": "POLITICS · 2028 RACE",
      "title": "Jon Ossoff leads the presidential race at 16%, with Democratic at 68%",
      "subtitle": "Top candidates to win the presidency.",
      "footer": "",
      "scale_ordered": false,
      "section_count": 4,
      "item_count": 1,
      "item_noun": "markets",
      "destination_href": "/collections/machinery-2028-presidential",
      "rows": [
        {
          "market_id": 112897,
          "outcome_id": 1625929,
          "name": "Jon Ossoff",
          "probability": 0.1605,
          "rendered_percent": 16,
          "art": {
            "url": "https://example.invalid/ossoff.png",
            "kind": "person",
            "detail": "U.S. Senator · GA",
            "accent_color": "#2563EB"
          }
        },
        {
          "market_id": 112897,
          "outcome_id": 1625920,
          "name": "JD Vance",
          "probability": 0.1305,
          "rendered_percent": 13,
          "art": {
            "url": "https://example.invalid/vance.png",
            "kind": "person",
            "detail": "Vice President",
            "accent_color": "#DC2626"
          }
        },
        {
          "market_id": 112897,
          "outcome_id": 1625923,
          "name": "Alexandria Ocasio-Cortez",
          "probability": 0.1065,
          "rendered_percent": 11,
          "art": {
            "url": null,
            "kind": "person",
            "detail": "U.S. Rep · NY",
            "accent_color": "#2563EB"
          }
        }
      ]
    }
    """#

    private let allTextSpotlightJSON = #"""
    {
      "slug": "machinery-rate-path-podium",
      "form_id": "contender_spotlight",
      "stage": "public",
      "kicker": "ECONOMICS · POLICY WATCH",
      "title": "Status quo holds at 54% ahead of the next FOMC decision",
      "subtitle": "Top three contenders for the headline rate outcome.",
      "footer": "",
      "scale_ordered": false,
      "section_count": 1,
      "item_count": 3,
      "item_noun": "outcomes",
      "destination_href": "/collections/machinery-rate-path-podium",
      "rows": [
        {
          "market_id": 57574217,
          "outcome_id": 1,
          "name": "No change",
          "probability": 0.54,
          "rendered_percent": 54,
          "art": null
        },
        {
          "market_id": 57574217,
          "outcome_id": 2,
          "name": "Quarter-point cut",
          "probability": 0.31,
          "rendered_percent": 31,
          "art": null
        },
        {
          "market_id": 57574217,
          "outcome_id": 3,
          "name": "Quarter-point hike",
          "probability": 0.15,
          "rendered_percent": 15,
          "art": null
        }
      ]
    }
    """#

    private let scaleOrderedFedJSON = #"""
    {
      "slug": "machinery-fed-and-macro",
      "form_id": "contender_spotlight",
      "stage": "public",
      "kicker": "ECONOMICS · FEDERAL RESERVE",
      "title": "A quarter-point increase leads the January Fed decision at 54%",
      "subtitle": "Scale-ordered decision outcomes keep horizontal comparison bars.",
      "footer": "",
      "scale_ordered": true,
      "section_count": 2,
      "item_count": 1,
      "item_noun": "markets",
      "destination_href": "/collections/machinery-fed-and-macro",
      "rows": [
        { "market_id": 57574217, "outcome_id": 213618739, "name": "Quarter-point increase", "probability": 0.539, "rendered_percent": 54, "art": null },
        { "market_id": 57574217, "outcome_id": 213618738, "name": "No change", "probability": 0.430, "rendered_percent": 43, "art": null },
        { "market_id": 57574217, "outcome_id": 213618737, "name": "Quarter-point cut", "probability": 0.015, "rendered_percent": 2, "art": null }
      ]
    }
    """#

    private static func makeSwatchImage(color: UIColor) -> UIImage {
        let renderer = UIGraphicsImageRenderer(size: CGSize(width: 88, height: 88))
        return renderer.image { ctx in
            color.setFill()
            ctx.fill(CGRect(x: 0, y: 0, width: 88, height: 88))
        }
    }

    func testContenderSpotlightThreeCellsAndAllTextRenderWithoutEllipsis() async throws {
        let dec = JSONDecoder()
        dec.keyDecodingStrategy = .convertFromSnakeCase
        let mixedCard = try dec.decode(MachineryCardContract.self, from: Data(mixedArtSpotlightJSON.utf8))
        let allTextCard = try dec.decode(MachineryCardContract.self, from: Data(allTextSpotlightJSON.utf8))
        let scaleCard = try dec.decode(MachineryCardContract.self, from: Data(scaleOrderedFedJSON.utf8))

        XCTAssertEqual(mixedCard.formId, .contenderSpotlight)
        XCTAssertFalse(mixedCard.scaleOrdered)
        XCTAssertEqual(allTextCard.formId, .contenderSpotlight)
        XCTAssertTrue(scaleCard.scaleOrdered)

        let preloaded: [String: PairedPlatformImage] = [
            "https://example.invalid/ossoff.png": Self.makeSwatchImage(color: .systemBlue),
            "https://example.invalid/vance.png": Self.makeSwatchImage(color: .systemRed),
        ]

        let outDir = ProcessInfo.processInfo.environment["TEST_RUNNER_BUILDER_C_RENDER_13551_CONTENDER_DIR"]
            ?? ProcessInfo.processInfo.environment["BUILDER_C_RENDER_13551_CONTENDER_DIR"]
        if let outDir, !outDir.isEmpty {
            try FileManager.default.createDirectory(atPath: outDir, withIntermediateDirectories: true)
        }

        let configs: [(tag: String, width: CGFloat, card: MachineryCardContract, scheme: ColorScheme, typeSize: DynamicTypeSize, height: CGFloat)] = [
            ("after-mixed-390-light", 390, mixedCard, .light, .large, 440),
            ("after-mixed-390-dark", 390, mixedCard, .dark, .large, 440),
            ("after-mixed-320-light", 320, mixedCard, .light, .large, 490),
            ("after-mixed-ax5-light", 390, mixedCard, .light, .accessibility5, 840),
            ("after-alltext-390-light", 390, allTextCard, .light, .large, 360),
            ("after-alltext-390-dark", 390, allTextCard, .dark, .large, 360),
            ("after-alltext-ax5-light", 390, allTextCard, .light, .accessibility5, 760),
            ("after-scale-390-light", 390, scaleCard, .light, .large, 420),
        ]

        for cfg in configs {
            let view = NavigationStack {
                MachineryDiscoverCardView(card: cfg.card)
                    .padding(16)
            }
            .environment(\.machineryPreloadedImages12288, preloaded)

            let img = await renderCard(view: view, width: cfg.width, scheme: cfg.scheme, typeSize: cfg.typeSize, height: cfg.height)
            let lines = try ocrLines(img)
            for line in lines {
                let trimmed = line.trimmingCharacters(in: .whitespaces)
                XCTAssertFalse(trimmed.hasPrefix("·"), "\(cfg.tag) wrapped detail line starts with '·': '\(line)'")
            }
            let ocr = lines.joined(separator: " ")
            let normalizedOcr = ocr.replacingOccurrences(of: "- ", with: "-")

            if cfg.card.slug == "machinery-2028-presidential" {
                for expected in ["#1", "#2", "#3", "Jon Ossoff", "16%", "JD Vance", "13%", "Ocasio-Cortez", "11%"] {
                    XCTAssertTrue(normalizedOcr.contains(expected), "\(cfg.tag) missing '\(expected)': \(ocr)")
                }
                // 387: A — sibling without art draws initials circle ("AO").
                XCTAssertTrue(ocr.contains("AO"), "\(cfg.tag) missing 387:A initials 'AO': \(ocr)")
            } else if cfg.card.slug == "machinery-rate-path-podium" {
                for expected in ["#1", "#2", "#3", "No change", "54%", "Quarter-point cut", "31%", "Quarter-point hike", "15%"] {
                    XCTAssertTrue(normalizedOcr.contains(expected), "\(cfg.tag) missing '\(expected)': \(ocr)")
                }
                // 388: A — all-text card never draws initials circles ("NC").
                XCTAssertFalse(ocr.contains("NC"), "\(cfg.tag) all-text card must not draw initials 'NC': \(ocr)")
            } else {
                XCTAssertFalse(ocr.contains("#1"), "\(cfg.tag) scale_ordered contender_spotlight must keep horizontal bars, not podium ranks: \(ocr)")
                XCTAssertTrue(ocr.contains("Quarter-point increase") && ocr.contains("54%"), "\(cfg.tag) missing scale row: \(ocr)")
            }

            XCTAssertFalse(ocr.contains("…"), "\(cfg.tag) truncated text with ellipsis: \(ocr)")

            if let outDir, !outDir.isEmpty, let png = img.pngData() {
                try png.write(to: URL(fileURLWithPath: outDir).appendingPathComponent("\(cfg.tag).png"))
            }
        }
    }

    private func renderCard<V: View>(
        view: V,
        width: CGFloat,
        scheme: ColorScheme,
        typeSize: DynamicTypeSize,
        height: CGFloat
    ) async -> UIImage {
        let frame = CGRect(x: 0, y: 0, width: width, height: height)
        let bg = scheme == .dark ? Color.black : Color(UIColor.systemGroupedBackground)
        let wrapped = view
            .frame(width: width, height: height, alignment: .topLeading)
            .background(bg)
            .environment(\.horizontalSizeClass, .compact)
            .environment(\.colorScheme, scheme)
            .environment(\.dynamicTypeSize, typeSize)
            .environmentObject(NavigationCoordinator())

        let host = hostForMeasurement(wrapped, at: typeSize)
        host.overrideUserInterfaceStyle = scheme == .dark ? .dark : .light
        let cat: UIContentSizeCategory = typeSize.isAccessibilitySize ? .accessibilityExtraExtraExtraLarge : .large
        let traits = UITraitCollection(traitsFrom: [
            UITraitCollection(horizontalSizeClass: .compact),
            UITraitCollection(userInterfaceStyle: scheme == .dark ? .dark : .light),
            UITraitCollection(preferredContentSizeCategory: cat),
        ])
        let container = FixedTraitContainer(child: host, traits: traits)
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

        for _ in 0..<5 {
            container.view.setNeedsLayout()
            container.view.layoutIfNeeded()
            try? await Task.sleep(for: .milliseconds(50))
        }

        let fmt = UIGraphicsImageRendererFormat()
        fmt.scale = 2.0
        fmt.opaque = true
        return UIGraphicsImageRenderer(size: frame.size, format: fmt).image { _ in
            _ = container.view.drawHierarchy(in: container.view.bounds, afterScreenUpdates: true)
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
