import Foundation
import SwiftUI
import UIKit
import Vision
import XCTest
@testable import Bain_Luck

/// #13753 — Season Futures AWARDS player rows never duplicate a player's name.
///
/// Reproduces the exact Devils @ Blue Jackets (`15353823`) `Connor Hellebuyck`
/// Vezina + Hart payload, verifies `awardPlayerGroups` groups both by canonical
/// `espn_id` / normalized name onto one row, and asserts an un-stitched 390 pt
/// render of `RelatedFuturesView` draws `"Connor Hellebuyck"` exactly once.
@MainActor
final class RelatedFuturesAwardDedup13753Tests: XCTestCase {

    private static func decoder() -> JSONDecoder {
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        return d
    }

    func testCanonicalGroupingMergesWhitespaceCaseAndMatchingEspnId() throws {
        let json = """
        [
          {
            "market_id": 60473132,
            "market_name": "NHL Vezina Trophy",
            "clean_label": "Vezina Trophy",
            "display_category": "award",
            "outcome_id": 225917740,
            "outcome_name": "Connor Hellebuyck",
            "probability": 0.135,
            "matched_player": {"name": "Connor Hellebuyck", "espn_id": "3020225"}
          },
          {
            "market_id": 52755679,
            "market_name": "NHL Hart Memorial Trophy",
            "clean_label": "Hart Trophy",
            "display_category": "award",
            "outcome_id": 206759014,
            "outcome_name": "Connor Hellebuyck ",
            "probability": 0.009,
            "matched_player": {"name": "Connor Hellebuyck", "espn_id": "3020225"}
          },
          {
            "market_id": 990001,
            "market_name": "Ted Lindsay Award",
            "clean_label": "Lindsay Award",
            "display_category": "award",
            "outcome_id": 990002,
            "outcome_name": "C. Hellebuyck",
            "probability": 0.004,
            "matched_player": {"name": "Connor Hellebuyck", "espn_id": "3020225"}
          },
          {
            "market_id": 880001,
            "market_name": "Art Ross Trophy",
            "clean_label": "Art Ross Trophy",
            "display_category": "award",
            "outcome_id": 880002,
            "outcome_name": "Jack Hughes",
            "probability": 0.02
          }
        ]
        """
        let away = try Self.decoder().decode([RelatedFuture].self, from: Data(json.utf8))
        let sides = relatedFutureSides(away: away, home: [])
        let groups = awardPlayerGroups(away, sides: sides)

        XCTAssertEqual(groups.away.count, 2)
        XCTAssertEqual(groups.away.map(\.name), ["Connor Hellebuyck", "Jack Hughes"])
        XCTAssertEqual(groups.away[0].awards.map(\.prob), [0.135, 0.009, 0.004])
    }

    func testUnstitchedRelatedFuturesViewPrintsHellebuyckOnceAt390pt() throws {
        let json = """
        {
          "event_id": 15353823,
          "home_team": "Columbus Blue Jackets",
          "away_team": "New Jersey Devils",
          "event_status": "scheduled",
          "away_team_futures": [
            {
              "market_id": 60473132,
              "market_name": "NHL Vezina Trophy",
              "clean_label": "Vezina Trophy",
              "display_category": "award",
              "market_tier": 3,
              "category": "championship",
              "source": "kalshi",
              "outcome_id": 225917740,
              "outcome_name": "Connor Hellebuyck",
              "probability": 0.135,
              "matched_player": {"name": "Connor Hellebuyck", "espn_id": "3020225"},
              "source_mark": {"state": "single", "sources": [{"key": "kalshi", "name": "Kalshi", "probability": 0.135}]}
            },
            {
              "market_id": 52755679,
              "market_name": "NHL Hart Memorial Trophy",
              "clean_label": "Hart Trophy",
              "display_category": "award",
              "market_tier": 3,
              "category": "championship",
              "source": "kalshi",
              "outcome_id": 206759014,
              "outcome_name": "Connor Hellebuyck",
              "probability": 0.009,
              "matched_player": {"name": "Connor Hellebuyck", "espn_id": "3020225"},
              "source_mark": {"state": "single", "sources": [{"key": "kalshi", "name": "Kalshi", "probability": 0.009}]}
            },
            {
              "market_id": 700001,
              "market_name": "Art Ross Trophy",
              "clean_label": "Art Ross Trophy",
              "display_category": "award",
              "market_tier": 3,
              "category": "championship",
              "source": "kalshi",
              "outcome_id": 700002,
              "outcome_name": "Jack Hughes",
              "probability": 0.02,
              "matched_player": {"name": "Jack Hughes", "espn_id": "4392731"},
              "source_mark": {"state": "single", "sources": [{"key": "kalshi", "name": "Kalshi", "probability": 0.02}]}
            },
            {
              "market_id": 700003,
              "market_name": "NHL Vezina Trophy",
              "clean_label": "Vezina Trophy",
              "display_category": "award",
              "market_tier": 3,
              "category": "championship",
              "source": "kalshi",
              "outcome_id": 700004,
              "outcome_name": "Jacob Markstrom",
              "probability": 0.01,
              "matched_player": {"name": "Jacob Markstrom", "espn_id": "5178"},
              "source_mark": {"state": "single", "sources": [{"key": "kalshi", "name": "Kalshi", "probability": 0.01}]}
            }
          ],
          "home_team_futures": [
            {
              "market_id": 700005,
              "market_name": "Norris Trophy",
              "clean_label": "Norris Trophy",
              "display_category": "award",
              "market_tier": 3,
              "category": "championship",
              "source": "kalshi",
              "outcome_id": 700006,
              "outcome_name": "Zach Werenski",
              "probability": 0.03,
              "matched_player": {"name": "Zach Werenski", "espn_id": "3899937"},
              "source_mark": {"state": "single", "sources": [{"key": "kalshi", "name": "Kalshi", "probability": 0.03}]}
            }
          ],
          "shared_futures": [],
          "total_count": 5
        }
        """
        let response = try Self.decoder().decode(RelatedFuturesResponse.self, from: Data(json.utf8))
        let colors = TeamTextContrast.cardColors(awayHex: "#CE1126", homeHex: "#002D62")

        let view = RelatedFuturesView(
            eventId: 15353823,
            awayTeamColor: colors.away,
            homeTeamColor: colors.home,
            awayTeam: "New Jersey Devils",
            homeTeam: "Columbus Blue Jackets",
            sportKey: "icehockey_nhl",
            preloadedData: response
        )
        .padding(12)
        .frame(width: 390, alignment: .topLeading)
        .background(Color(.systemGroupedBackground))

        let img = render390(view)
        let lines = try recognizeLines(in: img)
        let hellebuyckLines = lines.filter { $0.localizedCaseInsensitiveContains("Hellebuyck") }
        XCTAssertEqual(
            hellebuyckLines.count,
            1,
            "Un-stitched RelatedFuturesView must render Connor Hellebuyck once; got lines: \(lines)"
        )

        if let outDir = ProcessInfo.processInfo.environment["BUILDER_C_RENDER_13753_DIR"], !outDir.isEmpty {
            let dirURL = URL(fileURLWithPath: outDir, isDirectory: true)
            try FileManager.default.createDirectory(at: dirURL, withIntermediateDirectories: true)
            let pngData = try XCTUnwrap(img.pngData())
            try pngData.write(
                to: dirURL.appendingPathComponent("clean-awards-15353823-390.png"),
                options: .atomic
            )
        }
    }

    private func render390<V: View>(_ content: V) -> UIImage {
        let host = UIHostingController(
            rootView: content
                .environment(\.colorScheme, .light)
                .environment(\.dynamicTypeSize, .large)
                .environmentObject(NavigationCoordinator())
        )
        host.safeAreaRegions = []
        host.view.backgroundColor = UIColor.systemGroupedBackground
        let bounds = CGRect(x: 0, y: 0, width: 390, height: 640)
        let scene = UIApplication.shared.connectedScenes.compactMap { $0 as? UIWindowScene }.first
        let window: UIWindow = scene.map { UIWindow(windowScene: $0) } ?? UIWindow(frame: bounds)
        window.frame = bounds
        window.rootViewController = host
        window.isHidden = false
        for _ in 0..<4 {
            let fit = host.sizeThatFits(in: CGSize(width: 390, height: 2_000))
            let rect = CGRect(x: 0, y: 0, width: 390, height: max(400, ceil(fit.height)))
            host.view.frame = rect
            window.frame = rect
            host.view.setNeedsLayout()
            host.view.layoutIfNeeded()
            RunLoop.main.run(until: Date(timeIntervalSinceNow: 0.04))
        }
        let fmt = UIGraphicsImageRendererFormat()
        fmt.scale = 2.0
        let img = UIGraphicsImageRenderer(size: host.view.bounds.size, format: fmt).image { _ in
            host.view.drawHierarchy(in: host.view.bounds, afterScreenUpdates: true)
        }
        window.isHidden = true
        window.rootViewController = nil
        return img
    }

    private func recognizeLines(in image: UIImage) throws -> [String] {
        let cg = try XCTUnwrap(image.cgImage)
        let req = VNRecognizeTextRequest()
        req.recognitionLevel = .accurate
        req.usesLanguageCorrection = false
        try VNImageRequestHandler(cgImage: cg, options: [:]).perform([req])
        return (req.results ?? []).compactMap { $0.topCandidates(1).first?.string }
    }
}
