import SwiftUI
import UIKit
import XCTest
@testable import Bain_Luck

/// 1.0.8 Item 2 — Adaptive Dark Mode:
/// Removes root `.preferredColorScheme(.light)` in `Bain_LuckApp.swift` and makes `DS`
/// color tokens adapt cleanly while preserving Light RGBs and keeping >= 4.5:1 contrast.
@MainActor
final class AdaptiveDarkMode108Tests: XCTestCase {

    private func srgbComponents(_ color: Color, style: UIUserInterfaceStyle) -> (r: Double, g: Double, b: Double) {
        let uiColor = UIColor(color).resolvedColor(
            with: UITraitCollection(userInterfaceStyle: style)
        )
        var r: CGFloat = 0
        var g: CGFloat = 0
        var b: CGFloat = 0
        var a: CGFloat = 0
        uiColor.getRed(&r, green: &g, blue: &b, alpha: &a)
        return (Double(r), Double(g), Double(b))
    }

    private func relativeLuminance(_ rgb: (r: Double, g: Double, b: Double)) -> Double {
        func linear(_ c: Double) -> Double {
            c <= 0.04045 ? c / 12.92 : pow((c + 0.055) / 1.055, 2.4)
        }
        return 0.2126 * linear(rgb.r) + 0.7152 * linear(rgb.g) + 0.0722 * linear(rgb.b)
    }

    private func contrastRatio(_ fg: Color, on bg: Color, style: UIUserInterfaceStyle) -> Double {
        let l1 = relativeLuminance(srgbComponents(fg, style: style))
        let l2 = relativeLuminance(srgbComponents(bg, style: style))
        let lighter = max(l1, l2)
        let darker = min(l1, l2)
        return (lighter + 0.05) / (darker + 0.05)
    }

    func testRootAppDoesNotForceLightColorSchemeAndPreservesLightRGBs() throws {
        let root = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
        let appSource = try String(
            contentsOf: root.appendingPathComponent("Bain Luck/Bain_LuckApp.swift"),
            encoding: .utf8
        )
        XCTAssertFalse(
            appSource.contains(".preferredColorScheme(.light)"),
            "root Bain_LuckApp scenes must respect system Dark/Light appearance"
        )

        let cardLight = srgbComponents(DS.cardBg, style: .light)
        XCTAssertEqual(cardLight.r, 1.0, accuracy: 0.01)
        XCTAssertEqual(cardLight.g, 1.0, accuracy: 0.01)
        XCTAssertEqual(cardLight.b, 1.0, accuracy: 0.01)

        let cardDark = srgbComponents(DS.cardBg, style: .dark)
        XCTAssertLessThan(cardDark.r, 0.25, "dark mode cardBg must be dark")
    }

    func testReadableDesignTokensMeetWCAGAAContrastInLightAndDark() {
        let readableTokens: [(String, Color)] = [
            ("textPrimary", DS.textPrimary),
            ("textSecondaryReadable", DS.textSecondaryReadable),
            ("blueReadable", DS.blueReadable),
            ("greenReadable", DS.greenReadable),
        ]
        for style: UIUserInterfaceStyle in [.light, .dark] {
            for (name, fg) in readableTokens {
                for (bgName, bg) in [("cardBg", DS.cardBg), ("surface", DS.surface)] {
                    let ratio = contrastRatio(fg, on: bg, style: style)
                    XCTAssertGreaterThanOrEqual(
                        ratio,
                        4.5,
                        "\(name) on \(bgName) in style \(style.rawValue) has contrast \(ratio) < 4.5"
                    )
                }
            }
        }
    }

    func testDarkAndLightCardsRenderCleanlyAt390Px() async throws {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let event = try decoder.decode(FeedEventData.self, from: Data("""
        {
          "id": 910802,
          "external_id": "dark_mode_sample",
          "sport": "basketball_nba",
          "sport_name": "NBA",
          "away_team": "Boston Celtics",
          "home_team": "New York Knicks",
          "commence_time": "2026-11-24T00:00:00Z",
          "status": "scheduled",
          "current_odds": { "away_probability": 0.57, "home_probability": 0.43 }
        }
        """.utf8))
        let futures = try decoder.decode(FeedFuturesData.self, from: Data("""
        {
          "id": 910803,
          "name": "Which movie has biggest opening weekend in 2026?",
          "llm_sport_category": "entertainment",
          "source": "polymarket",
          "source_count": 1,
          "sources": ["polymarket"],
          "market_tier": 2,
          "discover_card": {
            "card_type": "outcome_distribution",
            "distribution_outcomes": [
              { "label": "Avengers: Doomsday", "probability": 0.48, "rendered_percent": 48 },
              { "label": "Toy Story 5", "probability": 0.24, "rendered_percent": 24 },
              { "label": "Odyssey", "probability": 0.14, "rendered_percent": 14 }
            ]
          }
        }
        """.utf8))

        let suiteName = "AdaptiveDarkMode108Tests.\(UUID().uuidString)"
        let defaults = try XCTUnwrap(UserDefaults(suiteName: suiteName))
        defer { defaults.removePersistentDomain(forName: suiteName) }
        let pins = PinManager(defaults: defaults)

        for (name, scheme, uiStyle) in [
            ("108-adaptive-light-390.png", ColorScheme.light, UIUserInterfaceStyle.light),
            ("108-adaptive-dark-390.png", ColorScheme.dark, UIUserInterfaceStyle.dark),
        ] {
            let content = VStack(alignment: .leading, spacing: 14) {
                SectionCard {
                    SectionKicker(text: "Design System · \(uiStyle == .dark ? "Dark" : "Light")")
                    SectionTitle(title: "Tonight", count: 2, action: "See all")
                        .padding(.top, 4)
                    Text("Secondary readable subtitle")
                        .font(.caption)
                        .foregroundStyle(DS.textSecondaryReadable)
                        .padding(.top, 4)
                }
                EventCardView(event: event, reason: nil)
                    .padding(14)
                    .background(DS.cardBg, in: RoundedRectangle(cornerRadius: 16))
                DistributionCardView(data: futures, navigationPath: .constant(NavigationPath()))
                    .padding(14)
                    .background(DS.cardBg, in: RoundedRectangle(cornerRadius: 16))
            }
            .padding(16)
            .frame(width: 390)
            .background(DS.surface)
            .environmentObject(pins)
            .environment(\.colorScheme, scheme)

            let host = hostForMeasurement(content, at: .large)
            host.overrideUserInterfaceStyle = uiStyle
            let h = max(320, min(ceil(host.sizeThatFits(in: CGSize(width: 390, height: 1000)).height), 1000))
            host.view.frame = CGRect(origin: .zero, size: CGSize(width: 390, height: h))
            let window = UIWindow(frame: host.view.frame)
            window.overrideUserInterfaceStyle = uiStyle
            window.rootViewController = host
            window.isHidden = false
            defer {
                window.isHidden = true
                window.rootViewController = nil
            }
            try await Task.sleep(nanoseconds: 80_000_000)
            host.view.setNeedsLayout()
            host.view.layoutIfNeeded()
            RunLoop.current.run(until: Date().addingTimeInterval(0.05))

            let fmt = UIGraphicsImageRendererFormat()
            fmt.scale = 3.0
            fmt.opaque = true
            let img = UIGraphicsImageRenderer(bounds: host.view.bounds, format: fmt).image { _ in
                _ = host.view.drawHierarchy(in: host.view.bounds, afterScreenUpdates: true)
            }
            XCTAssertGreaterThan(img.size.height, 300)
            let att = XCTAttachment(image: img)
            att.name = name
            att.lifetime = .keepAlways
            add(att)
        }
    }
}
