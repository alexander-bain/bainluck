import SwiftUI
import UIKit
import Vision
import XCTest
@testable import Bain_Luck

/// Ruling 387: A — Where at least one sibling row in a set or section has verified art,
/// a row without a picture renders its deterministic initials inside the same circle;
/// all-text cards draw no icons, and player award rows without headshots render player
/// initials instead of a generic person silhouette.
@MainActor
final class RowInitialsFallback387ATests: XCTestCase {

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

    private static let samplePortraitURL = "https://image.tmdb.org/t/p/w185/sample_387a_portrait.jpg"
    private static let samplePortrait2URL = "https://image.tmdb.org/t/p/w185/sample_387a_portrait2.jpg"

    private static func makeSwatchImage(color: UIColor) -> UIImage {
        let fmt = UIGraphicsImageRendererFormat()
        fmt.scale = 2.0
        fmt.opaque = true
        return UIGraphicsImageRenderer(size: CGSize(width: 64, height: 64), format: fmt).image { ctx in
            color.setFill()
            ctx.fill(CGRect(x: 0, y: 0, width: 64, height: 64))
            UIColor.white.withAlphaComponent(0.35).setFill()
            ctx.fill(CGRect(x: 16, y: 14, width: 32, height: 32))
        }
    }

    private func decode<T: Decodable>(_ type: T.Type, json: String) throws -> T {
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        return try d.decode(T.self, from: Data(json.utf8))
    }

    func testMixedArtDiscoverCardAndContainerDrawInitialsInSameCircleAcrossSizesWhilePlainCardDrawsNone() async throws {
        let preloaded: [String: UIImage] = [
            Self.samplePortraitURL: Self.makeSwatchImage(color: UIColor(red: 0.14, green: 0.36, blue: 0.62, alpha: 1.0)),
            Self.samplePortrait2URL: Self.makeSwatchImage(color: UIColor(red: 0.54, green: 0.22, blue: 0.34, alpha: 1.0)),
        ]

        let mixedDiscoverCard = try decode(MachineryCardContract.self, json: """
        {
          "slug": "machinery-next-james-bond",
          "form_id": "sibling_fields_grid",
          "kicker": "ENTERTAINMENT · JAMES BOND",
          "title": "Margaret Qualley leads Bond girl at 33%, with Olivia Colman at 19%",
          "subtitle": "Missing-picture contender row falls back to initials in the same circle.",
          "footer": "",
          "scale_ordered": false,
          "section_count": 1,
          "item_count": 3,
          "item_noun": "contenders",
          "destination_href": "/collections/machinery-next-james-bond",
          "rows": [
            { "market_id": 1001, "outcome_id": 1, "name": "Bond girl · Margaret Qualley", "probability": 0.33, "rendered_percent": 33, "art": { "url": "\(Self.samplePortraitURL)", "kind": "person", "accent_color": "#2563EB" } },
            { "market_id": 1001, "outcome_id": 2, "name": "James Bond Theme · Raye", "probability": 0.31, "rendered_percent": 31, "art": { "url": "\(Self.samplePortrait2URL)", "kind": "person", "accent_color": "#DB2777" } },
            { "market_id": 1001, "outcome_id": 3, "name": "M · Olivia Colman", "probability": 0.19, "rendered_percent": 19, "art": null }
          ]
        }
        """)

        let mixedSectionBlock = try decode(MachineryVisualBlock.self, json: """
        {
          "form_id": "sibling_fields_grid",
          "initial_visible_limit": 3,
          "items": [
            {
              "market_id": 2001,
              "title": "Casting Decisions",
              "outcomes": [
                { "outcome_id": 11, "name": "Caleb McLaughlin", "probability": 0.48, "rendered_percent": 48, "art": { "url": "\(Self.samplePortraitURL)", "kind": "person", "accent_color": "#059669" } },
                { "outcome_id": 12, "name": "Hugh Jackman", "probability": 0.31, "rendered_percent": 31, "art": null },
                { "outcome_id": 13, "name": "Lana Del Rey", "probability": 0.14, "rendered_percent": 14, "art": { "url": null, "kind": "person", "accent_color": "#7C3AED" } }
              ]
            }
          ]
        }
        """)

        let serverInitialsArt = try decode(MachinerySubjectArt.self, json: """
        { "url": null, "kind": "person", "accent_color": "#2563EB", "initials": " QZ " }
        """)
        XCTAssertEqual(serverInitialsArt.initials, "QZ")
        XCTAssertEqual(KitInitials366B.initials(for: "Olivia Colman", subjectKind: "person"), "OC")
        XCTAssertEqual(KitInitials366B.initials(for: "Hugh Jackman", subjectKind: "person"), "HJ")
        XCTAssertEqual(KitInitials366B.initials(for: "Lana Del Rey", subjectKind: "person"), "LD")

        let allMissingCard = try decode(MachineryCardContract.self, json: """
        {
          "slug": "machinery-climate-water",
          "form_id": "benchmark_strip",
          "kicker": "ODD · CLIMATE",
          "title": "Napa rainfall clearing 10 inches leads at 87%",
          "subtitle": "All-text rows never invent initials circles.",
          "footer": "",
          "scale_ordered": false,
          "section_count": 1,
          "item_count": 2,
          "item_noun": "markets",
          "destination_href": "/collections/machinery-climate-water",
          "rows": [
            { "market_id": 3001, "outcome_id": 21, "name": "Napa Rainfall", "probability": 0.87, "rendered_percent": 87, "art": null },
            { "market_id": 3001, "outcome_id": 22, "name": "Lake Mead Level", "probability": 0.42, "rendered_percent": 42, "art": null }
          ]
        }
        """)

        let outDir = ProcessInfo.processInfo.environment["BUILDER_C_RENDER_387A_DIR"]
        if let outDir, !outDir.isEmpty {
            try FileManager.default.createDirectory(atPath: outDir, withIntermediateDirectories: true)
        }

        let matrix: [(tag: String, width: CGFloat, scheme: ColorScheme, size: DynamicTypeSize)] = [
            ("mixed-390-light", 390, .light, .large),
            ("mixed-390-dark", 390, .dark, .large),
            ("mixed-320-light", 320, .light, .large),
            ("mixed-390-ax5", 390, .light, .accessibility5),
        ]

        for m in matrix {
            let height: CGFloat = m.size.isAccessibilitySize ? 900 : 820
            let view = NavigationStack {
                VStack(alignment: .leading, spacing: 14) {
                    MachineryDiscoverCardView(card: mixedDiscoverCard)
                    MachinerySectionBlockView(visualBlock: mixedSectionBlock, members: [])
                    Spacer(minLength: 0)
                }
                .padding(14)
            }
            .environment(\.machineryPreloadedImages12288, preloaded)

            let img = await renderView(view, width: m.width, height: height, scheme: m.scheme, typeSize: m.size)
            let ocr = try ocrLines(img).joined(separator: " ")

            XCTAssertTrue(ocr.contains("OC"), "\(m.tag) missing Olivia Colman initials 'OC': \(ocr)")
            XCTAssertTrue(ocr.contains("HJ"), "\(m.tag) missing Hugh Jackman initials 'HJ': \(ocr)")
            XCTAssertTrue(ocr.contains("LD"), "\(m.tag) missing Lana Del Rey initials 'LD': \(ocr)")
            XCTAssertFalse(ocr.contains("…"), "\(m.tag) truncated text with ellipsis: \(ocr)")

            if let outDir, !outDir.isEmpty, let png = img.pngData() {
                try png.write(to: URL(fileURLWithPath: outDir).appendingPathComponent("\(m.tag).png"))
            }
        }

        // All-missing-art card must draw zero initials circles ("NR", "LM")
        let plainImg = await renderView(
            NavigationStack {
                VStack(alignment: .leading) {
                    MachineryDiscoverCardView(card: allMissingCard)
                    Spacer(minLength: 0)
                }
                .padding(14)
            },
            width: 390,
            height: 360,
            scheme: .light,
            typeSize: .large
        )
        let plainOCR = try ocrLines(plainImg).joined(separator: " ")
        XCTAssertFalse(plainOCR.contains("NR"), "All-text card must not draw initials 'NR': \(plainOCR)")
        XCTAssertFalse(plainOCR.contains("LM"), "All-text card must not draw initials 'LM': \(plainOCR)")
        if let outDir, !outDir.isEmpty, let png = plainImg.pngData() {
            try png.write(to: URL(fileURLWithPath: outDir).appendingPathComponent("plain-390-light.png"))
        }
    }

    func testRelatedFuturesPlayerAwardsDrawInitialsInCircleInsteadOfSilhouette() async throws {
        let json = """
        {
          "event_id": 15353823,
          "home_team": "Columbus Blue Jackets",
          "away_team": "New Jersey Devils",
          "away_team_futures": [
            {
              "market_id": 9001,
              "market_name": "Vezina Trophy",
              "outcome_id": 1,
              "outcome_name": "Connor Hellebuyck",
              "probability": 0.14,
              "market_tier": 3,
              "display_category": "awards",
              "matched_player": {
                "name": "Connor Hellebuyck",
                "headshot": null,
                "espn_id": null
              }
            },
            {
              "market_id": 9002,
              "market_name": "Hart Trophy",
              "outcome_id": 2,
              "outcome_name": "Jack Hughes",
              "probability": 0.08,
              "market_tier": 3,
              "display_category": "awards",
              "matched_player": {
                "name": "Jack Hughes",
                "headshot": null,
                "espn_id": null
              }
            }
          ],
          "home_team_futures": [
            {
              "market_id": 9003,
              "market_name": "Norris Trophy",
              "outcome_id": 3,
              "outcome_name": "Zach Werenski",
              "probability": 0.11,
              "market_tier": 3,
              "display_category": "awards",
              "matched_player": {
                "name": "Zach Werenski",
                "headshot": null,
                "espn_id": null
              }
            }
          ],
          "shared_futures": []
        }
        """
        let response = try decode(RelatedFuturesResponse.self, json: json)
        let outDir = ProcessInfo.processInfo.environment["BUILDER_C_RENDER_387A_DIR"]

        for (scheme, tag) in [(ColorScheme.light, "light"), (ColorScheme.dark, "dark")] {
            let colors = TeamTextContrast.surfaceColors(
                awayHex: "#CE1126",
                homeHex: "#002D62",
                colorScheme: scheme
            )
            let view = VStack(alignment: .leading) {
                RelatedFuturesView(
                    eventId: 15353823,
                    awayTeamColor: colors.away,
                    homeTeamColor: colors.home,
                    awayTeam: "New Jersey Devils",
                    homeTeam: "Columbus Blue Jackets",
                    sportKey: "icehockey_nhl",
                    preloadedData: response
                )
                Spacer(minLength: 0)
            }
            .padding(14)

            let img = await renderView(view, width: 390, height: 420, scheme: scheme, typeSize: .large)
            let ocr = try ocrLines(img).joined(separator: " ")
            XCTAssertTrue(ocr.contains("CH"), "Awards (\(tag)) missing 'CH' initials inside circle: \(ocr)")
            XCTAssertTrue(ocr.contains("JH"), "Awards (\(tag)) missing 'JH' initials inside circle: \(ocr)")
            XCTAssertTrue(ocr.contains("ZW"), "Awards (\(tag)) missing 'ZW' initials inside circle: \(ocr)")

            if let outDir, !outDir.isEmpty, let png = img.pngData() {
                try png.write(to: URL(fileURLWithPath: outDir).appendingPathComponent("awards-\(tag)-390.png"))
            }
        }
    }

    func testDiscoverPairedMetricCardDrawsInitialsInCircleWhenSiblingHasArtWhilePreservingSharedLeftEdge() async throws {
        let preloaded: [String: UIImage] = [
            Self.samplePortraitURL: Self.makeSwatchImage(color: UIColor(red: 0.14, green: 0.42, blue: 0.34, alpha: 1.0)),
        ]
        let pairedJSON = """
        {
          "set_id": "oscars-best-picture",
          "category": "entertainment",
          "kicker": "Awards · Oscars",
          "title": "Oscars Best Picture",
          "subtitle": "99th Academy Awards",
          "stage1_label": "Nominated",
          "stage2_label": "Winner",
          "stage1_settled": false,
          "primary_stage1_market_id": 501,
          "primary_stage2_market_id": 502,
          "entries": [
            {
              "subject_key": "odyssey",
              "subject": "The Odyssey",
              "detail": "Christopher Nolan",
              "stage1_market_id": 501,
              "stage2_market_id": 502,
              "stage1_probability": 0.88,
              "stage2_probability": 0.29,
              "art": {
                "kind": "tmdb_poster",
                "url": "\(Self.samplePortraitURL)",
                "adult": false,
                "kid_safe_vetted": true
              }
            },
            {
              "subject_key": "dune-messiah",
              "subject": "Dune Messiah",
              "detail": "Denis Villeneuve",
              "stage1_market_id": 501,
              "stage2_market_id": 502,
              "stage1_probability": 0.72,
              "stage2_probability": 0.18,
              "art": null
            }
          ]
        }
        """
        let set = try decode(PairedMetricSet.self, json: pairedJSON)
        let outDir = ProcessInfo.processInfo.environment["BUILDER_C_RENDER_387A_DIR"]

        for (scheme, tag) in [(ColorScheme.light, "light"), (ColorScheme.dark, "dark")] {
            let view = NavigationStack {
                VStack(alignment: .leading) {
                    DiscoverPairedMetricCardView(
                        set: set,
                        form: .pairedBarsTop5Expandable,
                        showsPlaceholderMonogram: false,
                        preloadedImages: preloaded
                    )
                    Spacer(minLength: 0)
                }
                .padding(14)
            }

            let img = await renderView(view, width: 390, height: 420, scheme: scheme, typeSize: .large)
            let boxes = try ocrBoxes(img)
            let joined = boxes.map(\.text).joined(separator: " ")
            XCTAssertTrue(joined.contains("DM"), "Paired (\(tag)) missing 'DM' initials circle for artless sibling: \(joined)")
            let odysseyX = try XCTUnwrap(boxes.first(where: { $0.text.contains("The Odyssey") })?.minXPx)
            let duneX = try XCTUnwrap(boxes.first(where: { $0.text.contains("Dune Messiah") })?.minXPx)
            XCTAssertLessThanOrEqual(
                abs(odysseyX - duneX),
                12.0,
                "Artless paired sibling 'Dune Messiah' (\(duneX) px) must share 'The Odyssey' left edge (\(odysseyX) px)"
            )

            if let outDir, !outDir.isEmpty, let png = img.pngData() {
                try png.write(to: URL(fileURLWithPath: outDir).appendingPathComponent("paired-\(tag)-390.png"))
            }
        }
    }

    private func renderView<V: View>(
        _ content: V,
        width: CGFloat,
        height: CGFloat,
        scheme: ColorScheme,
        typeSize: DynamicTypeSize
    ) async -> UIImage {
        let frame = CGRect(x: 0, y: 0, width: width, height: height)
        let bg = scheme == .dark ? Color.black : Color(UIColor.systemGroupedBackground)
        let wrapped = content
            .frame(width: width, height: height, alignment: .topLeading)
            .background(bg)
            .environment(\.horizontalSizeClass, .compact)
            .environment(\.colorScheme, scheme)
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
        fmt.scale = typeSize.isAccessibilitySize ? 2.0 : 3.0
        fmt.opaque = true
        return UIGraphicsImageRenderer(size: frame.size, format: fmt).image { _ in
            _ = container.view.drawHierarchy(in: container.view.bounds, afterScreenUpdates: true)
        }
    }

    private func ocrLines(_ image: UIImage) throws -> [String] {
        try ocrBoxes(image).map(\.text)
    }

    private func ocrBoxes(_ image: UIImage) throws -> [(text: String, minXPx: CGFloat)] {
        guard let cg = image.cgImage else { return [] }
        let width = CGFloat(cg.width)
        let req = VNRecognizeTextRequest()
        req.recognitionLevel = .accurate
        req.usesLanguageCorrection = false
        req.minimumTextHeight = 0.0
        try VNImageRequestHandler(cgImage: cg, options: [:]).perform([req])
        return (req.results ?? []).compactMap { obs in
            guard let text = obs.topCandidates(1).first?.string else { return nil }
            return (text: text, minXPx: obs.boundingBox.minX * width)
        }
    }
}
