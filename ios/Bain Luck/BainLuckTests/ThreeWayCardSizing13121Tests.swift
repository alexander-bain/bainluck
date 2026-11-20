import SwiftUI
import UIKit
import Vision
import XCTest
@testable import Bain_Luck

/// #13121 (`1.0.7`): On a three-way soccer card (`EventCardView` in `My Stuff`, `Sports`, `Search`),
/// nothing shrinks below a two-way card's type size, and no line ends in `"…"`.
/// Multi-word club names wrap cleanly; when a single word exceeds the inline width beside
/// trailing columns, the row grows vertically rather than shrinking the font.
@MainActor
final class ThreeWayCardSizing13121Tests: XCTestCase {

    private func makeDecoder() -> JSONDecoder {
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        return d
    }

    private func decodeEvent(_ json: String) throws -> FeedEventData {
        try makeDecoder().decode(FeedEventData.self, from: Data(json.utf8))
    }

    private func wolvesAtForestScheduled() throws -> FeedEventData {
        try decodeEvent("""
        {
          "id": 91312101,
          "external_id": "epl_wolves_forest",
          "sport": "soccer_epl",
          "sport_name": "Premier League",
          "away_team": "Wolverhampton Wanderers",
          "home_team": "Nottingham Forest",
          "commence_time": "2026-11-21T15:00:00Z",
          "status": "scheduled",
          "current_odds": {
            "away_probability": 0.28,
            "home_probability": 0.46,
            "draw_probability": 0.26,
            "away_rendered_percent": 28,
            "home_rendered_percent": 46
          }
        }
        """)
    }

    private func wolvesAtForestLive() throws -> FeedEventData {
        try decodeEvent("""
        {
          "id": 91312102,
          "external_id": "epl_wolves_forest_live",
          "sport": "soccer_epl",
          "sport_name": "Premier League",
          "away_team": "Wolverhampton Wanderers",
          "home_team": "Nottingham Forest",
          "commence_time": "2026-11-19T20:00:00Z",
          "status": "live",
          "away_score": 1,
          "home_score": 1,
          "espn": {"game_clock": "68'", "period": "2nd Half"},
          "current_odds": {
            "away_probability": 0.29,
            "home_probability": 0.37,
            "draw_probability": 0.34,
            "away_rendered_percent": 29,
            "home_rendered_percent": 37
          },
          "prematch_odds": {
            "away_probability": 0.28,
            "home_probability": 0.46,
            "draw_probability": 0.26
          }
        }
        """)
    }

    private func celticsAtLakersScheduled() throws -> FeedEventData {
        try decodeEvent("""
        {
          "id": 91312103,
          "external_id": "nba_bos_lal",
          "sport": "basketball_nba",
          "sport_name": "NBA",
          "away_team": "Boston Celtics",
          "home_team": "Los Angeles Lakers",
          "commence_time": "2026-11-21T03:00:00Z",
          "status": "scheduled",
          "current_odds": {
            "away_probability": 0.58,
            "home_probability": 0.42,
            "away_rendered_percent": 58,
            "home_rendered_percent": 42,
            "projected_away_score": 116.2,
            "projected_home_score": 111.4
          }
        }
        """)
    }

    func testThreeWaySoccerCardUsesExactSameTeamNameFontSizeAsTwoWayBasketballCard() throws {
        let scheduledSoccer = EventCardView(event: try wolvesAtForestScheduled(), reason: "Starting Saturday — tight match")
        let liveSoccer = EventCardView(event: try wolvesAtForestLive(), reason: nil)
        let basketball = EventCardView(event: try celticsAtLakersScheduled(), reason: "Rivalry matchup")

        XCTAssertTrue(scheduledSoccer.isThreeWayCard13121)
        XCTAssertTrue(liveSoccer.isThreeWayCard13121)
        XCTAssertFalse(basketball.isThreeWayCard13121)

        XCTAssertEqual(
            scheduledSoccer.resolvedCompactTeamNameFontSizeForTest13121,
            basketball.resolvedCompactTeamNameFontSizeForTest13121,
            accuracy: 0.01,
            "Scheduled three-way soccer card must never shrink below a two-way basketball card's name size"
        )
        XCTAssertEqual(
            liveSoccer.resolvedCompactTeamNameFontSizeForTest13121,
            basketball.resolvedCompactTeamNameFontSizeForTest13121,
            accuracy: 0.01,
            "Live three-way soccer card must never shrink below a two-way basketball card's name size"
        )
    }

    private func captureSnapshot<V: View>(
        _ content: V,
        scheme: ColorScheme,
        width: CGFloat = 390,
        height: CGFloat = 760
    ) async throws -> UIImage {
        let host = hostForMeasurement(content.environment(\.colorScheme, scheme), at: .large)
        let uiStyle: UIUserInterfaceStyle = scheme == .light ? .light : .dark
        host.overrideUserInterfaceStyle = uiStyle
        host.traitOverrides.preferredContentSizeCategory = .large

        let bounds = CGRect(x: 0, y: 0, width: width, height: height)
        let scene = try XCTUnwrap(
            UIApplication.shared.connectedScenes.compactMap({ $0 as? UIWindowScene }).first
        )
        let existingWindows = scene.windows
        existingWindows.forEach { $0.isHidden = true }
        let window = UIWindow(windowScene: scene)
        window.frame = bounds
        window.overrideUserInterfaceStyle = uiStyle
        window.traitOverrides.preferredContentSizeCategory = .large
        window.rootViewController = host
        window.makeKeyAndVisible()
        defer {
            window.isHidden = true
            window.rootViewController = nil
            existingWindows.forEach { $0.isHidden = false }
        }

        host.view.frame = bounds
        host.view.setNeedsLayout()
        host.view.layoutIfNeeded()
        try await Task.sleep(nanoseconds: 550_000_000)
        for _ in 0..<6 {
            host.view.setNeedsLayout()
            host.view.layoutIfNeeded()
            RunLoop.current.run(until: Date().addingTimeInterval(0.02))
        }

        let fmt = UIGraphicsImageRendererFormat()
        fmt.scale = 1.0
        fmt.opaque = true
        return UIGraphicsImageRenderer(bounds: bounds, format: fmt).image { ctx in
            if !window.drawHierarchy(in: bounds, afterScreenUpdates: true) {
                window.layer.render(in: ctx.cgContext)
            }
        }
    }

    private func recognizeLines(in image: UIImage) throws -> [String] {
        // Upscale 2x for crisp Vision OCR on 1x 390px snapshots
        let upscaledSize = CGSize(width: image.size.width * 2, height: image.size.height * 2)
        let fmt = UIGraphicsImageRendererFormat()
        fmt.scale = 1.0
        let hiRes = UIGraphicsImageRenderer(size: upscaledSize, format: fmt).image { _ in
            image.draw(in: CGRect(origin: .zero, size: upscaledSize))
        }
        let cgImage = try XCTUnwrap(hiRes.cgImage)
        let req = VNRecognizeTextRequest()
        req.recognitionLevel = .accurate
        req.usesLanguageCorrection = false
        try VNImageRequestHandler(cgImage: cgImage, options: [:]).perform([req])
        return (req.results ?? []).compactMap { $0.topCandidates(1).first?.string }
    }

    func testMyStuffSoccerCardBesideBasketballCardHasZeroEllipsisAndExports390Renders() async throws {
        let scheduledSoccer = try wolvesAtForestScheduled()
        let liveSoccer = try wolvesAtForestLive()
        let basketball = try celticsAtLakersScheduled()

        let suiteName = "Test13121.\(UUID().uuidString)"
        let defaults = try XCTUnwrap(UserDefaults(suiteName: suiteName))
        defer { defaults.removePersistentDomain(forName: suiteName) }
        let pinManager = PinManager(defaults: defaults)

        let myStuffList = List {
            Section {
                EventCardView(event: scheduledSoccer, reason: "Close match on Saturday")
                    .listRowInsets(EdgeInsets(top: 8, leading: 12, bottom: 8, trailing: 12))
                EventCardView(event: basketball, reason: "Rivalry matchup")
                    .listRowInsets(EdgeInsets(top: 8, leading: 12, bottom: 8, trailing: 12))
                EventCardView(event: liveSoccer, reason: nil)
                    .listRowInsets(EdgeInsets(top: 8, leading: 12, bottom: 8, trailing: 12))
            } header: {
                Label("Upcoming & Live (My Stuff)", systemImage: "bookmark.fill")
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(.orange)
                    .textCase(nil)
            }
        }
        .listStyle(.insetGrouped)
        .environmentObject(pinManager)

        let lightImg = try await captureSnapshot(myStuffList, scheme: .light, width: 390, height: 840)
        let darkImg = try await captureSnapshot(myStuffList, scheme: .dark, width: 390, height: 840)

        let joined = try recognizeLines(in: lightImg).joined(separator: " | ")
        for expected in ["Wolverhampton", "Wanderers", "Draw", "Nottingham", "Forest", "Celtics", "Lakers"] {
            XCTAssertTrue(
                joined.localizedCaseInsensitiveContains(expected),
                "Expected full word '\(expected)' in rendered My Stuff list; OCR read: \(joined)"
            )
        }
        XCTAssertFalse(joined.contains("…"), "No line on the My Stuff soccer card may end in '…': \(joined)")
        XCTAssertFalse(joined.contains("..."), "No line on the My Stuff soccer card may end in '...': \(joined)")

        if let outDir = ProcessInfo.processInfo.environment["RENDER_13121_DIR"], !outDir.isEmpty {
            try FileManager.default.createDirectory(atPath: outDir, withIntermediateDirectories: true)
            try XCTUnwrap(lightImg.pngData()).write(to: URL(fileURLWithPath: "\(outDir)/13121-mystuff-soccer-beside-nba-light-390.png"))
            try XCTUnwrap(darkImg.pngData()).write(to: URL(fileURLWithPath: "\(outDir)/13121-mystuff-soccer-beside-nba-dark-390.png"))
        }
    }
}
