import SwiftUI
import UIKit
import Vision
import XCTest
@testable import Bain_Luck

/// #13551 — Pile 7 (`duel_bar`): one horizontal bar split between two sides on
/// Discover cards (`MachineryDiscoverCardView`), rendered at 390 pt Light, Dark,
/// and `.accessibility5` with zero fallback to Pile-2 stacked bars.
@MainActor
final class DuelBarDiscoverCard13551Tests: XCTestCase {

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

    private let liveTwoWayDuelJSON = #"""
    {
      "slug": "machinery-afc-west-duel",
      "form_id": "duel_bar",
      "stage": "public",
      "kicker": "SPORTS · NFL DIVISIONS",
      "title": "Denver leads Kansas City 57%–43% in the AFC West race",
      "subtitle": "Denver and Kansas City go head-to-head for the AFC West division crown.",
      "footer": "",
      "scale_ordered": false,
      "section_count": 2,
      "item_count": 1,
      "item_noun": "contenders",
      "destination_href": "/collections/machinery-afc-west-duel",
      "rows": [
        {
          "market_id": 53675,
          "outcome_id": 846594,
          "name": "Denver",
          "probability": 0.565,
          "rendered_percent": 57,
          "unfloored_percent": 57,
          "art": {
            "url": "https://a.espncdn.com/i/teamlogos/nfl/500/scoreboard/den.png",
            "kind": "team_logo",
            "detail": "DEN",
            "accent_color": "#0a2343"
          }
        },
        {
          "market_id": 53675,
          "outcome_id": 846593,
          "name": "Kansas City",
          "probability": 0.435,
          "rendered_percent": 43,
          "unfloored_percent": 43,
          "art": {
            "url": "https://a.espncdn.com/i/teamlogos/nfl/500/scoreboard/kc.png",
            "kind": "team_logo",
            "detail": "KC",
            "accent_color": "#e31837"
          }
        }
      ]
    }
    """#

    private let threeWayWithTieJSON = #"""
    {
      "slug": "machinery-epl-derby-duel",
      "form_id": "duel_bar",
      "kicker": "SOCCER · HEAD TO HEAD",
      "title": "Liverpool vs Arsenal match result",
      "subtitle": "Three-way match split including draw",
      "footer": "",
      "scale_ordered": false,
      "section_count": 1,
      "item_count": 1,
      "item_noun": "outcomes",
      "destination_href": "/collections/machinery-epl-derby-duel",
      "rows": [
        {
          "market_id": 70001,
          "outcome_id": 1,
          "name": "Liverpool",
          "probability": 0.46,
          "rendered_percent": 46,
          "art": { "kind": "none", "accent_color": "#C8102E" }
        },
        {
          "market_id": 70001,
          "outcome_id": 2,
          "name": "Draw",
          "probability": 0.24,
          "rendered_percent": 24,
          "art": { "kind": "none", "accent_color": "#64748B" }
        },
        {
          "market_id": 70001,
          "outcome_id": 3,
          "name": "Arsenal",
          "probability": 0.30,
          "rendered_percent": 30,
          "art": { "kind": "none", "accent_color": "#034694" }
        }
      ]
    }
    """#

    func testDuelBarContractAndThreeWayRenderOnDiscover390PtLightDarkAndAX5() async throws {
        let dec = JSONDecoder()
        dec.keyDecodingStrategy = .convertFromSnakeCase
        let twoWayCard = try dec.decode(MachineryCardContract.self, from: Data(liveTwoWayDuelJSON.utf8))
        let threeWayCard = try dec.decode(MachineryCardContract.self, from: Data(threeWayWithTieJSON.utf8))
        XCTAssertEqual(twoWayCard.formId, .duelBar)
        XCTAssertEqual(twoWayCard.outcomeRows.count, 2)
        XCTAssertEqual(threeWayCard.formId, .duelBar)
        XCTAssertEqual(threeWayCard.outcomeRows.count, 3)

        let outDir = ProcessInfo.processInfo.environment["BUILDER_C_RENDER_13551_DIR"]
        if let outDir, !outDir.isEmpty {
            try FileManager.default.createDirectory(atPath: outDir, withIntermediateDirectories: true)
        }

        let configs: [(tag: String, width: CGFloat, card: MachineryCardContract, scheme: ColorScheme, typeSize: DynamicTypeSize, height: CGFloat)] = [
            ("after-reg-light-390", 390, twoWayCard, .light, .large, 340),
            ("after-reg-dark-390", 390, twoWayCard, .dark, .large, 340),
            ("after-ax5-light-390", 390, twoWayCard, .light, .accessibility5, 580),
            ("after-ax5-dark-390", 390, twoWayCard, .dark, .accessibility5, 580),
            ("after-3way-light-390", 390, threeWayCard, .light, .large, 340),
            ("after-3way-dark-390", 390, threeWayCard, .dark, .large, 340),
            ("after-reg-light-320", 320, twoWayCard, .light, .large, 360),
            ("after-reg-dark-320", 320, twoWayCard, .dark, .large, 360),
            ("after-ax5-light-320", 320, twoWayCard, .light, .accessibility5, 660),
            ("after-3way-light-320", 320, threeWayCard, .light, .large, 360),
        ]

        for cfg in configs {
            let view = NavigationStack {
                MachineryDiscoverCardView(card: cfg.card)
                    .padding(16)
            }
            let img = await renderCard(view: view, width: cfg.width, scheme: cfg.scheme, typeSize: cfg.typeSize, height: cfg.height)
            let ocr = try ocrLines(img).joined(separator: " ")

            if cfg.card.slug == "machinery-afc-west-duel" {
                XCTAssertTrue(ocr.contains("Denver") && ocr.contains("57%"), "\(cfg.tag) missing Denver 57%: \(ocr)")
                XCTAssertTrue(ocr.contains("Kansas City") && ocr.contains("43%"), "\(cfg.tag) missing Kansas City 43%: \(ocr)")
            } else {
                XCTAssertTrue(ocr.contains("Liverpool") && ocr.contains("46%"), "\(cfg.tag) missing Liverpool 46%: \(ocr)")
                XCTAssertTrue(ocr.contains("Draw 24%"), "\(cfg.tag) missing middle Draw 24% label: \(ocr)")
                XCTAssertTrue(ocr.contains("Arsenal") && ocr.contains("30%"), "\(cfg.tag) missing Arsenal 30%: \(ocr)")
            }
            XCTAssertFalse(ocr.contains("…"), "\(cfg.tag) truncated text with ellipsis: \(ocr)")

            if let outDir, !outDir.isEmpty, let png = img.pngData() {
                try png.write(to: URL(fileURLWithPath: outDir).appendingPathComponent("\(cfg.tag).png"))
            }
        }
    }

    func testThreeNonDrawRowsUseFirstTwoSidesWithoutGreyMiddle() async throws {
        let json = #"""
        {
          "slug": "machinery-afc-west-three-contenders",
          "form_id": "duel_bar",
          "kicker": "SPORTS · NFL DIVISIONS",
          "title": "Denver vs Kansas City in the AFC West race",
          "subtitle": "Three contenders sent without a draw row",
          "footer": "",
          "scale_ordered": false,
          "section_count": 1,
          "item_count": 3,
          "item_noun": "contenders",
          "destination_href": "/collections/machinery-afc-west-three-contenders",
          "rows": [
            { "market_id": 53675, "outcome_id": 1, "name": "Denver", "probability": 0.56, "rendered_percent": 56, "art": { "kind": "none", "accent_color": "#0A2343" } },
            { "market_id": 53675, "outcome_id": 2, "name": "Kansas City", "probability": 0.42, "rendered_percent": 42, "art": { "kind": "none", "accent_color": "#E31837" } },
            { "market_id": 53675, "outcome_id": 3, "name": "Las Vegas", "probability": 0.02, "rendered_percent": 2, "art": { "kind": "none", "accent_color": "#000000" } }
          ]
        }
        """#
        let dec = JSONDecoder()
        dec.keyDecodingStrategy = .convertFromSnakeCase
        let card = try dec.decode(MachineryCardContract.self, from: Data(json.utf8))
        let sides = try XCTUnwrap(MachineryDiscoverCardView.resolveDuelBarSides(card.outcomeRows))
        XCTAssertEqual(sides.left.name, "Denver")
        XCTAssertEqual(sides.right.name, "Kansas City")
        XCTAssertNil(sides.middle, "Three non-draw contenders must never demote row 2 to a grey middle slice")

        let view = NavigationStack {
            MachineryDiscoverCardView(card: card)
                .padding(16)
        }
        let img = await renderCard(view: view, width: 390, scheme: .light, typeSize: .large, height: 340)
        let ocr = try ocrLines(img).joined(separator: " ")
        XCTAssertTrue(ocr.contains("Denver") && ocr.contains("56%"), "Missing left side Denver 56%: \(ocr)")
        XCTAssertTrue(ocr.contains("Kansas City") && ocr.contains("42%"), "Missing right side Kansas City 42%: \(ocr)")
        XCTAssertFalse(ocr.contains("Las Vegas"), "Row 3 must not replace row 2 or render in middle: \(ocr)")
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
