import SwiftUI
import UIKit
import Vision
import XCTest
@testable import Bain_Luck

/// #13551 — Pile 1 (percent pill on plain rows): `NativeGroupCard` `theme` and
/// `comparison` compact rows render probabilities inside `DiscoverPlainRowPercentPill13551`
/// across `390 pt` Light/Dark, `320 pt`, and `.accessibility5` with zero `"…"` truncation.
@MainActor
final class PercentPillPlainRows13551Tests: XCTestCase {

    private func makeDecoder() -> JSONDecoder {
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        return d
    }

    private func themeGroupItems() throws -> [FeedItem] {
        let json = #"""
        [
          {
            "type": "futures",
            "score": 88,
            "data": {
              "id": 91355101,
              "name": "Will OpenAI IPO before 2027?",
              "llm_sport_category": "tech",
              "top_outcomes": [
                {"id": 101, "name": "Yes", "probability": 0.42, "rendered_percent": 42, "rank": 1, "movement": 0.03}
              ]
            }
          },
          {
            "type": "futures",
            "score": 85,
            "data": {
              "id": 91355102,
              "name": "Will Anthropic reach a $100B valuation?",
              "llm_sport_category": "tech",
              "top_outcomes": [
                {"id": 102, "name": "Yes", "probability": 0.78, "rendered_percent": 78, "rank": 1, "movement": -0.02}
              ]
            }
          },
          {
            "type": "futures",
            "score": 82,
            "data": {
              "id": 91355103,
              "name": "Next major foundation model leader in 2026",
              "llm_sport_category": "tech",
              "top_outcomes": [
                {"id": 103, "name": "Google Gemini", "probability": 0.56, "rendered_percent": 56, "rank": 1, "movement": 0.0}
              ]
            }
          }
        ]
        """#
        return try makeDecoder().decode([FeedItem].self, from: Data(json.utf8))
    }

    private func comparisonGroupItems() throws -> [FeedItem] {
        let json = #"""
        [
          {
            "type": "futures",
            "score": 84,
            "data": {
              "id": 91355111,
              "name": "Who wins the 2026 House majority?",
              "llm_sport_category": "politics",
              "top_outcomes": [
                {"id": 201, "name": "Democratic Party", "probability": 0.61, "rendered_percent": 61, "rank": 1, "movement": 0.04}
              ]
            }
          },
          {
            "type": "futures",
            "score": 81,
            "data": {
              "id": 91355112,
              "name": "Who wins the 2026 Senate majority?",
              "llm_sport_category": "politics",
              "top_outcomes": [
                {"id": 202, "name": "Republican Party", "probability": 0.68, "rendered_percent": 68, "rank": 1, "movement": -0.01}
              ]
            }
          }
        ]
        """#
        return try makeDecoder().decode([FeedItem].self, from: Data(json.utf8))
    }

    private func renderSnapshot<V: View>(
        _ view: V,
        width: CGFloat,
        dynamicTypeSize: DynamicTypeSize,
        colorScheme: ColorScheme
    ) -> UIImage {
        let contentSizeCategory: UIContentSizeCategory = {
            switch dynamicTypeSize {
            case .accessibility5: return .accessibilityExtraExtraExtraLarge
            case .xxxLarge: return .extraExtraExtraLarge
            default: return .large
            }
        }()
        let bg = colorScheme == .dark
            ? Color.black
            : Color(UIColor.systemGroupedBackground)
        let wrapped = view
            .fixedSize(horizontal: false, vertical: true)
            .padding(16)
            .frame(width: width)
            .background(bg)
            .environment(\.horizontalSizeClass, .compact)
            .environment(\.dynamicTypeSize, dynamicTypeSize)
            .environment(\.colorScheme, colorScheme)
            .environmentObject(PinManager())
            .environmentObject(NavigationCoordinator())

        let frame = CGRect(x: 0, y: 0, width: width, height: 2600)
        let scene = UIApplication.shared.connectedScenes
            .compactMap { $0 as? UIWindowScene }
            .first { $0.activationState == .foregroundActive }
            ?? UIApplication.shared.connectedScenes.compactMap { $0 as? UIWindowScene }.first
        let window: UIWindow = scene.map { UIWindow(windowScene: $0) } ?? UIWindow(frame: frame)
        window.frame = frame
        window.overrideUserInterfaceStyle = colorScheme == .dark ? .dark : .light

        let host = hostForMeasurement(wrapped, at: dynamicTypeSize)
        host.overrideUserInterfaceStyle = colorScheme == .dark ? .dark : .light
        host.sizingOptions = [.intrinsicContentSize]
        window.rootViewController = host
        window.isHidden = false
        window.makeKeyAndVisible()
        defer {
            window.isHidden = true
            window.rootViewController = nil
        }

        host.view.overrideUserInterfaceStyle = colorScheme == .dark ? .dark : .light
        host.traitOverrides.preferredContentSizeCategory = contentSizeCategory
        host.traitOverrides.horizontalSizeClass = .compact
        host.view.layoutIfNeeded()
        RunLoop.main.run(until: Date().addingTimeInterval(0.08))
        host.view.layoutIfNeeded()

        let measured = host.sizeThatFits(in: CGSize(width: width, height: 10000))
        let height = max(ceil(measured.height), 120)
        window.frame = CGRect(x: 0, y: 0, width: width, height: height)
        host.view.frame = CGRect(x: 0, y: 0, width: width, height: height)
        host.view.layoutIfNeeded()
        RunLoop.main.run(until: Date().addingTimeInterval(0.05))

        let fmt = UIGraphicsImageRendererFormat()
        fmt.scale = 2.0
        fmt.opaque = true
        return UIGraphicsImageRenderer(size: CGSize(width: width, height: height), format: fmt).image { _ in
            _ = host.view.drawHierarchy(in: host.view.bounds, afterScreenUpdates: true)
        }
    }

    private func ocrStrings(in image: UIImage) throws -> [String] {
        let cgImage = try XCTUnwrap(image.cgImage)
        let req = VNRecognizeTextRequest()
        req.recognitionLevel = .accurate
        req.usesLanguageCorrection = false
        try VNImageRequestHandler(cgImage: cgImage, options: [:]).perform([req])
        return (req.results ?? []).compactMap { $0.topCandidates(1).first?.string }
    }

    func testPlainRowPercentPillRendersLightDarkCompactAndAX5WithoutTruncation() throws {
        let themeItems = try themeGroupItems()
        let comparisonItems = try comparisonGroupItems()

        let outDir = ProcessInfo.processInfo.environment["BUILDER_C_RENDER_13551_PILL_DIR"]
        if let outDir, !outDir.isEmpty {
            try FileManager.default.createDirectory(atPath: outDir, withIntermediateDirectories: true)
        }

        let configs: [(tag: String, kind: String, title: String, items: [FeedItem], width: CGFloat, scheme: ColorScheme, typeSize: DynamicTypeSize, tokens: [String])] = [
            (
                "theme-390-light", "theme", "AI & Tech Milestones", themeItems, 390, .light, .large,
                ["Milestones", "IPO before 2027?", "42%", "78%", "Google Gemini", "56%"]
            ),
            (
                "theme-390-dark", "theme", "AI & Tech Milestones", themeItems, 390, .dark, .large,
                ["Milestones", "IPO before 2027?", "42%", "78%", "Google Gemini", "56%"]
            ),
            (
                "theme-320-light", "theme", "AI & Tech Milestones", themeItems, 320, .light, .large,
                ["Milestones", "42%", "78%", "56%"]
            ),
            (
                "theme-390-ax5-light", "theme", "AI & Tech Milestones", themeItems, 390, .light, .accessibility5,
                ["IPO before 2027?", "42%", "78%", "56%"]
            ),
            (
                "theme-390-ax5-dark", "theme", "AI & Tech Milestones", themeItems, 390, .dark, .accessibility5,
                ["IPO before 2027?", "42%", "78%", "56%"]
            ),
            (
                "comparison-390-light", "comparison", "2026 Congress Balance", comparisonItems, 390, .light, .large,
                ["2026 Congress Balance", "Democratic Party", "61%", "Republican Party", "68%"]
            ),
            (
                "comparison-390-dark", "comparison", "2026 Congress Balance", comparisonItems, 390, .dark, .large,
                ["2026 Congress Balance", "Democratic Party", "61%", "Republican Party", "68%"]
            ),
        ]

        for cfg in configs {
            let card = NativeGroupCard(
                title: cfg.title,
                items: cfg.items,
                kind: cfg.kind,
                navigationPath: .constant(NavigationPath())
            )
            let img = renderSnapshot(card, width: cfg.width, dynamicTypeSize: cfg.typeSize, colorScheme: cfg.scheme)
            let joined = try ocrStrings(in: img).joined(separator: " ")

            XCTAssertFalse(joined.contains("\u{2026}") || joined.contains("..."), "\(cfg.tag) truncated with ellipsis: \(joined)")
            for token in cfg.tokens {
                XCTAssertTrue(joined.localizedCaseInsensitiveContains(token), "\(cfg.tag) missing '\(token)': \(joined)")
            }

            if let outDir, !outDir.isEmpty, let png = img.pngData() {
                try png.write(to: URL(fileURLWithPath: outDir).appendingPathComponent("\(cfg.tag).png"))
            }
        }
    }
}
