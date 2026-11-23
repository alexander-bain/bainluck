import SwiftUI
import UIKit
import Vision
import XCTest
@testable import Bain_Luck

/// #12962 / #12581: Finished tennis tournament results (`GET /api/tournaments/{slug}`)
/// draw each priced player's served `prematch_source_mark` beside their pre-match
/// probability, aligned to the duel-rounded percentage printed on the row, and open
/// `SourceMarkSheet` with the player's name and draw/round caption (`subtitle`).
@MainActor
final class TournamentResultSourceMarks12962Tests: XCTestCase {

    private func decodeHub(_ json: String) throws -> TournamentHubResponse {
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        return try d.decode(TournamentHubResponse.self, from: Data(json.utf8))
    }

    private func liveUSOpenSampleJSON() -> String {
        """
        {
          "slug": "us-open",
          "title": "US Open 2026",
          "subtitle": "Flushing Meadows",
          "sport": "tennis_atp",
          "status": "completed",
          "boards": [],
          "results": {
            "matches": [
              {
                "matchup_key": "mens-singles:arthur-rinderknech-vs-sho-shimabukuro:2026-08-30",
                "draw": "mens-singles",
                "draw_label": "Men's Singles",
                "round": "Round 1",
                "players": [
                  {
                    "entity_key": "arthur-rinderknech",
                    "display_name": "Arthur Rinderknech",
                    "is_winner": true,
                    "prematch_probability": 0.735,
                    "prematch_source": "kalshi",
                    "prematch_source_mark": {
                      "state": "single",
                      "sources": [{"key": "kalshi", "name": "Kalshi", "probability": 0.735, "observed_at": null, "reason": "observation_unknown"}]
                    }
                  },
                  {
                    "entity_key": "sho-shimabukuro",
                    "display_name": "Sho Shimabukuro",
                    "is_winner": false,
                    "prematch_probability": 0.265,
                    "prematch_source": "kalshi",
                    "prematch_source_mark": {
                      "state": "single",
                      "sources": [{"key": "kalshi", "name": "Kalshi", "probability": 0.265, "observed_at": null, "reason": "observation_unknown"}]
                    }
                  }
                ],
                "winner_entity_key": "arthur-rinderknech",
                "score": "6-7, 6-2, 7-6, 6-2",
                "completion": "final",
                "completed_at": "2026-08-30T15:05Z"
              },
              {
                "matchup_key": "womens-singles:storm-hunter-vs-yeon-woo-ku:2026-08-26",
                "draw": "womens-singles",
                "draw_label": "Women's Singles",
                "round": "Qualifying 2nd Round",
                "players": [
                  {
                    "entity_key": "storm-hunter",
                    "display_name": "Storm Hunter",
                    "is_winner": true,
                    "prematch_probability": 0.575,
                    "prematch_source": "polymarket",
                    "prematch_source_mark": {
                      "state": "single",
                      "sources": [{"key": "polymarket", "name": "Polymarket", "probability": 0.575, "observed_at": null, "reason": "observation_unknown"}]
                    }
                  },
                  {
                    "entity_key": "yeon-woo-ku",
                    "display_name": "Yeon-Woo Ku",
                    "is_winner": false,
                    "prematch_probability": 0.425,
                    "prematch_source": "polymarket",
                    "prematch_source_mark": {
                      "state": "single",
                      "sources": [{"key": "polymarket", "name": "Polymarket", "probability": 0.425, "observed_at": null, "reason": "observation_unknown"}]
                    }
                  }
                ],
                "winner_entity_key": "storm-hunter",
                "score": "4-6, 7-6, 6-0",
                "completion": "final",
                "completed_at": "2026-08-26T21:55Z"
              },
              {
                "matchup_key": "mens-singles:adam-walton-vs-wu-yibing:2026-08-30",
                "draw": "mens-singles",
                "draw_label": "Men's Singles",
                "round": "Round 1",
                "players": [
                  {
                    "entity_key": "adam-walton",
                    "display_name": "Adam Walton",
                    "is_winner": false,
                    "prematch_probability": 0.5417,
                    "prematch_source": "books",
                    "prematch_source_mark": {
                      "state": "single",
                      "sources": [{"key": "betting", "name": "Sportsbooks", "probability": 0.5417, "observed_at": null, "reason": "observation_unknown"}]
                    }
                  },
                  {
                    "entity_key": "wu-yibing",
                    "display_name": "Wu Yibing",
                    "is_winner": true,
                    "prematch_probability": 0.4582,
                    "prematch_source": "books",
                    "prematch_source_mark": {
                      "state": "single",
                      "sources": [{"key": "betting", "name": "Sportsbooks", "probability": 0.4582, "observed_at": null, "reason": "observation_unknown"}]
                    }
                  }
                ],
                "winner_entity_key": "wu-yibing",
                "score": "7-6, 6-2, 7-5",
                "completion": "final",
                "completed_at": "2026-08-30T15:05Z"
              },
              {
                "matchup_key": "espn:184626",
                "draw": "mens-singles",
                "draw_label": "Men's Singles",
                "round": "Qualifying 1st Round",
                "players": [
                  {"entity_key": "jurij-rodionov", "display_name": "Jurij Rodionov", "is_winner": true, "prematch_probability": null},
                  {"entity_key": "espn:athlete:2009", "display_name": "Kimmer Coppejans", "is_winner": false, "prematch_probability": null}
                ],
                "winner_entity_key": "jurij-rodionov",
                "score": "6-1, 6-4",
                "completion": "final",
                "completed_at": "2026-08-24T15:05Z"
              }
            ]
          }
        }
        """
    }

    func testPresentationDecodesPrematchSourceMarksAndAlignsDuelRoundedNumber() throws {
        let hub = try decodeHub(liveUSOpenSampleJSON())
        let p = TournamentHubPresentation(response: hub)
        XCTAssertEqual(p.results.count, 4)

        let rinderknech = try XCTUnwrap(p.results.first { $0.winnerName == "Arthur Rinderknech" })
        XCTAssertEqual(rinderknech.winnerPrematchText, "74%")
        XCTAssertEqual(rinderknech.loserPrematchText, "26%")
        XCTAssertEqual(try XCTUnwrap(rinderknech.winnerPrematchNumber), 0.74, accuracy: 0.0001)
        XCTAssertEqual(try XCTUnwrap(rinderknech.loserPrematchNumber), 0.26, accuracy: 0.0001)
        XCTAssertEqual(rinderknech.winnerPrematchSourceMark?.sources.first?.name, "Kalshi")
        XCTAssertEqual(rinderknech.loserPrematchSourceMark?.sources.first?.name, "Kalshi")

        let hunter = try XCTUnwrap(p.results.first { $0.winnerName == "Storm Hunter" })
        XCTAssertEqual(hunter.winnerPrematchText, "58%")
        XCTAssertEqual(hunter.loserPrematchText, "42%")
        // Raw 0.425 would round standalone to 43%; alignedPrematchNumber keeps sheet headline at 42%.
        XCTAssertEqual(try XCTUnwrap(hunter.loserPrematchNumber), 0.42, accuracy: 0.0001)
        XCTAssertEqual(hunter.loserPrematchSourceMark?.sources.first?.name, "Polymarket")

        let wu = try XCTUnwrap(p.results.first { $0.winnerName == "Wu Yibing" })
        XCTAssertEqual(wu.winnerPrematchText, "46%")
        XCTAssertEqual(wu.loserPrematchText, "54%")
        XCTAssertEqual(wu.winnerPrematchSourceMark?.sources.first?.name, "Sportsbooks")

        let unpriced = try XCTUnwrap(p.results.first { $0.winnerName == "Jurij Rodionov" })
        XCTAssertNil(unpriced.winnerPrematchText)
        XCTAssertNil(unpriced.winnerPrematchSourceMark)
        XCTAssertNil(unpriced.loserPrematchSourceMark)
    }

    private func captureSnapshot<V: View>(
        _ content: V,
        width: CGFloat = 390,
        height: CGFloat = 780
    ) async throws -> UIImage {
        let host = hostForMeasurement(content.environment(\.colorScheme, .light), at: .large)
        host.overrideUserInterfaceStyle = .light
        host.traitOverrides.preferredContentSizeCategory = .large

        let bounds = CGRect(x: 0, y: 0, width: width, height: height)
        let scene = try XCTUnwrap(
            UIApplication.shared.connectedScenes.compactMap({ $0 as? UIWindowScene }).first
        )
        let existingWindows = scene.windows
        existingWindows.forEach { $0.isHidden = true }
        let window = UIWindow(windowScene: scene)
        window.frame = bounds
        window.overrideUserInterfaceStyle = .light
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
        try await Task.sleep(nanoseconds: 450_000_000)
        for _ in 0..<5 {
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

    func testFinishedTennisResultsRenderSourceMarksAndAlignedPregameSheetAt390Px() async throws {
        let hub = try decodeHub(liveUSOpenSampleJSON())
        let p = TournamentHubPresentation(response: hub)

        let resultsList = ScrollView {
            VStack(alignment: .leading, spacing: 12) {
                Text("US Open · Recent Results")
                    .font(.title3.weight(.bold))
                    .foregroundStyle(DS.textPrimary)
                ForEach(p.results) { row in
                    TournamentHubResultCard(row: row)
                }
            }
            .padding(16)
        }
        .background(DS.surface)

        let hunter = try XCTUnwrap(p.results.first { $0.winnerName == "Storm Hunter" })
        let sheetView = SourceMarkSheet(
            mark: try XCTUnwrap(hunter.loserPrematchSourceMark),
            number: hunter.loserPrematchNumber,
            subject: hunter.loserName,
            subtitle: hunter.headline,
            isPregame: true
        )

        let rowsImg = try await captureSnapshot(resultsList, width: 390, height: 680)
        let sheetImg = try await captureSnapshot(sheetView, width: 390, height: 520)

        let cg = try XCTUnwrap(sheetImg.cgImage)
        let req = VNRecognizeTextRequest()
        req.recognitionLevel = .accurate
        req.usesLanguageCorrection = false
        try VNImageRequestHandler(cgImage: cg, options: [:]).perform([req])
        let ocr = (req.results ?? []).compactMap { $0.topCandidates(1).first?.string }.joined(separator: " | ")
        XCTAssertTrue(ocr.contains("Yeon-Woo Ku"), "Expected subject name in sheet: \(ocr)")
        XCTAssertTrue(ocr.contains("42%"), "Expected duel-aligned 42% headline in sheet: \(ocr)")
        XCTAssertTrue(ocr.contains("Polymarket"), "Expected Polymarket source in sheet: \(ocr)")

        if let outDir = ProcessInfo.processInfo.environment["RENDER_12962_DIR"], !outDir.isEmpty {
            try FileManager.default.createDirectory(atPath: outDir, withIntermediateDirectories: true)
            try XCTUnwrap(rowsImg.pngData()).write(to: URL(fileURLWithPath: "\(outDir)/12962-tennis-results-rows-390.png"))
            try XCTUnwrap(sheetImg.pngData()).write(to: URL(fileURLWithPath: "\(outDir)/12962-tennis-results-sheet-390.png"))
        }
    }
}
