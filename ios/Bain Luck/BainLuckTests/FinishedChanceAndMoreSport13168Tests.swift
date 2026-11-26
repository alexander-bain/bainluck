import Foundation
import SwiftUI
import XCTest
@testable import Bain_Luck

#if canImport(UIKit)
import UIKit
import Vision
#endif

/// Pins Fable's 1.0.7 finished-game current-chance guards + #13168 (`RelatedByTagView`
/// `"More <Sport>"` cut-off at `.xxxLarge` & `.accessibility5`) using the real served
/// payload shape of `event 15350936` (`Philadelphia Flyers 6, Ottawa Senators 5` with
/// stale `current_odds` `47% / 53%` and `prematch_odds` `41% / 59%`).
@MainActor
final class FinishedChanceAndMoreSport13168Tests: XCTestCase {

    private let flyersAtSenators15350936JSON = """
    {
      "id": 15350936,
      "external_id": "2040a6c31c90ebbc7f929b41fd2df8fb",
      "sport": "icehockey_nhl",
      "sport_name": "NHL",
      "away_team": "Philadelphia Flyers",
      "home_team": "Ottawa Senators",
      "commence_time": "2026-11-20T00:00:00Z",
      "status": "completed",
      "away_score": 6,
      "home_score": 5,
      "hero_probability_source": "settled",
      "hero_settled_result": "away",
      "event_tags": ["sport:hockey", "competitive_structure:best_of_7"],
      "home_series_wins": 0,
      "away_series_wins": 0,
      "away_team_data": {
        "primary_color": "#F74902",
        "abbreviation": "PHI"
      },
      "home_team_data": {
        "primary_color": "#C52032",
        "abbreviation": "OTT"
      },
      "current_odds": {
        "away_probability": 0.47,
        "home_probability": 0.53,
        "away_rendered_percent": 47,
        "home_rendered_percent": 53
      },
      "prematch_odds": {
        "away_probability": 0.41,
        "home_probability": 0.59,
        "away_rendered_percent": 41,
        "home_rendered_percent": 59,
        "source": "kalshi"
      }
    }
    """

    private func decodeFeedEvent(_ json: String) throws -> FeedEventData {
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        return try d.decode(FeedEventData.self, from: Data(json.utf8))
    }

    private func decodeEventDetail(_ json: String) throws -> EventDetail {
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        return try d.decode(EventDetail.self, from: Data(json.utf8))
    }

    private func decodeItem(_ json: String) throws -> FeedItem {
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        return try d.decode(FeedItem.self, from: Data(json.utf8))
    }

    func testFinishedGame15350936WithholdsStaleCurrentOddsAcrossRelatedRowsSeriesCopyAndWatchMarquee() throws {
        let finishedFeed = try decodeFeedEvent(flyersAtSenators15350936JSON)
        let finishedDetail = try decodeEventDetail(flyersAtSenators15350936JSON)

        // 1. "More <Sport>" rows print Final and the score, never 47% / 53%
        XCTAssertFalse(RelatedByTagView.admitsTrailingProbability(finishedFeed))
        XCTAssertEqual(RelatedByTagView.trailingSummary(for: finishedFeed), "Final · 6–5")

        // 2. Series card uses the finished game's result (Flyers away win -> 0-1) + pregame baseline (0.59), never 0.53
        let seriesInputs = try XCTUnwrap(SeriesProbabilityView.resolvedMountInputs(for: finishedDetail))
        XCTAssertEqual(seriesInputs.homeSeriesWins, 0)
        XCTAssertEqual(seriesInputs.awaySeriesWins, 1)
        XCTAssertEqual(seriesInputs.homeWinProb, 0.59, accuracy: 0.0001)

        // 3. "Copy Probability" is not offered on a finished game
        XCTAssertNil(CardContextMenu.copyableHomeProbability(for: finishedFeed))
        XCTAssertNil(MyStuffView.eventCopyProbabilityText(finishedFeed))

        // 4. Unmounted legacy WatchMarquee skips finished events in Top Story and omits split in My Teams
        let watchFeedJSON = """
        { "items": [ { "type": "event", "score": 95, "data": \(flyersAtSenators15350936JSON) } ] }
        """
        let dec = JSONDecoder()
        dec.keyDecodingStrategy = .convertFromSnakeCase
        let watchFeed = try dec.decode(WatchFeedResponse.self, from: Data(watchFeedJSON.utf8))
        XCTAssertNil(WatchMarquee.marquee(from: watchFeed.items))
        let watchTeamGame = try XCTUnwrap(WatchMarquee.teamGames(from: watchFeed.items).first)
        XCTAssertNil(watchTeamGame.split)
        XCTAssertEqual(watchTeamGame.resultText, "FINAL · 6–5")
        XCTAssertNil(watchTeamGame.startText)
    }

    #if canImport(UIKit)
    private func renderImage<V: View>(
        _ content: V,
        scheme: ColorScheme,
        sizeCategory: UIContentSizeCategory,
        typeSize: DynamicTypeSize,
        width: CGFloat,
        height: CGFloat
    ) throws -> UIImage {
        let wrapped = content
            .environment(\.colorScheme, scheme)
            .environment(\.dynamicTypeSize, typeSize)
        let host = hostForMeasurement(wrapped, at: typeSize)
        let uiStyle: UIUserInterfaceStyle = scheme == .light ? .light : .dark
        host.overrideUserInterfaceStyle = uiStyle
        host.traitOverrides.preferredContentSizeCategory = sizeCategory

        let bounds = CGRect(x: 0, y: 0, width: width, height: height)
        let scene = try XCTUnwrap(
            UIApplication.shared.connectedScenes.compactMap({ $0 as? UIWindowScene }).first
        )
        let existingWindows = scene.windows
        existingWindows.forEach { $0.isHidden = true }
        let window = UIWindow(windowScene: scene)
        window.frame = bounds
        window.overrideUserInterfaceStyle = uiStyle
        window.traitOverrides.preferredContentSizeCategory = sizeCategory
        window.rootViewController = host
        window.makeKeyAndVisible()
        defer {
            window.isHidden = true
            window.rootViewController = nil
            existingWindows.forEach { $0.isHidden = false }
        }

        host.view.frame = bounds
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

    private func ocrStrings(in image: UIImage) throws -> [String] {
        let upscaledSize = CGSize(width: image.size.width * 3, height: image.size.height * 3)
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

    func testMoreSportAndSeriesCard13168NeverTruncateOrPrintFinishedCurrentOddsAtDefaultLargestAndAX5() throws {
        let item1 = try decodeItem("""
        {
          "type": "event",
          "data": {
            "id": 15351290,
            "sport": "icehockey_nhl",
            "sport_name": "NHL",
            "away_team": "Dallas Stars",
            "home_team": "Vegas Golden Knights",
            "status": "scheduled",
            "hero_probability_source": "blend",
            "current_odds": {
              "away_probability": 0.62,
              "home_probability": 0.38,
              "away_rendered_percent": 62,
              "home_rendered_percent": 38
            }
          }
        }
        """)
        let item2 = try decodeItem("""
        {
          "type": "event",
          "data": \(flyersAtSenators15350936JSON)
        }
        """)
        let item3 = try decodeItem("""
        {
          "type": "event",
          "data": {
            "id": 15351291,
            "sport": "icehockey_nhl",
            "sport_name": "NHL",
            "away_team": "Minnesota Wild",
            "home_team": "Columbus Blue Jackets",
            "status": "live",
            "away_score": 2,
            "home_score": 1,
            "hero_probability_source": "blend",
            "current_odds": {
              "away_probability": 0.68,
              "home_probability": 0.32,
              "away_rendered_percent": 68,
              "home_rendered_percent": 32
            }
          }
        }
        """)

        let finishedDetail = try decodeEventDetail(flyersAtSenators15350936JSON)
        let seriesInputs = try XCTUnwrap(SeriesProbabilityView.resolvedMountInputs(for: finishedDetail))

        let pageStack = NavigationStack {
            VStack(spacing: 14) {
                RelatedByTagView(
                    preloadedItems: [item1, item2, item3],
                    title: "More NHL",
                    limit: 4
                )

                SeriesProbabilityView(
                    homeWinProb: seriesInputs.homeWinProb,
                    homeSeriesWins: seriesInputs.homeSeriesWins,
                    awaySeriesWins: seriesInputs.awaySeriesWins,
                    gamesToWin: seriesInputs.gamesToWin,
                    homeTeam: finishedDetail.homeTeam,
                    awayTeam: finishedDetail.awayTeam,
                    homeTeamColor: Color(hex: "#C52032"),
                    awayTeamColor: Color(hex: "#F74902")
                )
                Spacer(minLength: 0)
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 16)
            .frame(width: 390, alignment: .top)
            .background(Color(.systemGroupedBackground))
        }

        let configs: [(UIContentSizeCategory, DynamicTypeSize, String, CGFloat)] = [
            (.large, .large, "default", 450),
            (.extraExtraExtraLarge, .xxxLarge, "xxxlarge", 560),
            (.accessibilityExtraExtraExtraLarge, .accessibility5, "ax5", 1420)
        ]

        for (cat, dt, label, height) in configs {
            for scheme in [ColorScheme.light, .dark] {
                let img = try renderImage(pageStack, scheme: scheme, sizeCategory: cat, typeSize: dt, width: 390, height: height)
                let joined = try ocrStrings(in: img).joined(separator: " | ")
                XCTAssertFalse(joined.contains("…"), "More NHL / Series (\(label), \(scheme)) truncated with '…': \(joined)")
                XCTAssertFalse(joined.contains("47%"), "Finished 15350936 printed stale 47%: \(joined)")
                XCTAssertFalse(joined.contains("53%"), "Finished 15350936 printed stale 53%: \(joined)")
                for token in ["Dallas", "Knights", "62%", "38%", "Flyers", "Senators", "Final", "Jackets", "Senators trail", "52%", "48%"] {
                    XCTAssertTrue(
                        joined.localizedCaseInsensitiveContains(token),
                        "Missing '\(token)' in More NHL / Series (\(label), \(scheme)): \(joined)"
                    )
                }
                if let dir = ProcessInfo.processInfo.environment["RENDER_13168_DIR"], !dir.isEmpty {
                    try FileManager.default.createDirectory(atPath: dir, withIntermediateDirectories: true)
                    let schemeTag = scheme == .light ? "light" : "dark"
                    try XCTUnwrap(img.pngData()).write(to: URL(fileURLWithPath: "\(dir)/13168-more-nhl-and-series-\(label)-\(schemeTag)-390.png"))
                }
            }
        }
    }

    func testFinishedShareCardPrintsFinalScoresAndPregameNeverStaleCurrentOdds() throws {
        let finishedDetail = try decodeEventDetail(flyersAtSenators15350936JSON)
        let pregame = try XCTUnwrap(PrematchReading.resolve(prematch: finishedDetail.prematchOdds, opening: finishedDetail.openingOdds))

        let shareImage = try XCTUnwrap(ShareCardRenderer.renderEventCard(
            homeTeam: finishedDetail.homeTeam,
            awayTeam: finishedDetail.awayTeam,
            homeProbability: pregame.homeProbability,
            awayProbability: pregame.awayProbability,
            awayRenderedPercent: pregame.percents.first ?? nil,
            homeRenderedPercent: pregame.percents.count > 1 ? pregame.percents[1] : nil,
            sportName: "NHL",
            homeColor: Color(hex: "#C52032"),
            awayColor: Color(hex: "#F74902"),
            status: "completed",
            homeScore: 5,
            awayScore: 6,
            commenceTime: Date().addingTimeInterval(-10800),
            pregameReading: pregame,
            sportKey: finishedDetail.sport,
            authorityPeriod: nil
        ))
        let joined = try ocrStrings(in: shareImage).joined(separator: " | ")
        XCTAssertFalse(joined.contains("47%"), "Finished share card printed stale 47%: \(joined)")
        XCTAssertFalse(joined.contains("53%"), "Finished share card printed stale 53%: \(joined)")
        for token in ["FINAL", "6", "5", "Pregame", "41%", "59%"] {
            XCTAssertTrue(
                joined.localizedCaseInsensitiveContains(token),
                "Finished share card missing '\(token)': \(joined)"
            )
        }
        if let dir = ProcessInfo.processInfo.environment["RENDER_13168_DIR"], !dir.isEmpty {
            try FileManager.default.createDirectory(atPath: dir, withIntermediateDirectories: true)
            let framed = UIGraphicsImageRenderer(size: CGSize(width: 390, height: 520)).image { ctx in
                UIColor.systemGroupedBackground.setFill()
                ctx.fill(CGRect(x: 0, y: 0, width: 390, height: 520))
                shareImage.draw(in: CGRect(x: 7.5, y: 10, width: 375, height: 500))
            }
            try XCTUnwrap(framed.pngData()).write(to: URL(fileURLWithPath: "\(dir)/13168-finished-share-card-390.png"))
        }
    }
    #endif
}
