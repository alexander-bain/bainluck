import SwiftUI
import UIKit
import Vision
import XCTest
@testable import Bain_Luck

/// Guard for the small-number bug on Sports and Search cards:
/// Fails if `Now` or `Chance` on a Sports card (`358 pt`) or Search card (`306 pt`,
/// adapted through `SearchEventCardAdapter183A.fromSearchResult`) draws smaller in
/// rendered glyph height than the score / projected score beside it at default (`.large`),
/// largest standard (`.xxxLarge`), and largest accessibility (`.accessibility5`) text sizes.
@MainActor
final class SmallNumberCardGuardTests: XCTestCase {

    private func decodeFeedEvent(_ json: String) throws -> FeedEventData {
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        return try d.decode(FeedEventData.self, from: Data(json.utf8))
    }

    private func decodeSearchEvent(_ json: String) throws -> SearchEvent {
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        return try d.decode(SearchEvent.self, from: Data(json.utf8))
    }

    private func renderCardPNG<V: View>(_ view: V, width: CGFloat, at typeSize: DynamicTypeSize) throws -> UIImage {
        let content = view
            .frame(width: width)
            .padding(.vertical, 8)
            .background(Color.white)
            .environment(\.colorScheme, .light)

        let renderer = rendererForMeasurement(content, at: typeSize)
        renderer.scale = 3.0
        if let image = renderer.uiImage {
            return image
        }

        let host = hostForMeasurement(content, at: typeSize)
        host.overrideUserInterfaceStyle = .light
        host.traitOverrides.preferredContentSizeCategory = UIContentSizeCategory(typeSize)
        let fittedH = ceil(host.sizeThatFits(in: CGSize(width: width, height: 1600)).height) + 24
        let bounds = CGRect(x: 0, y: 0, width: width, height: max(fittedH, 140))
        host.view.frame = bounds
        host.view.setNeedsLayout()
        host.view.layoutIfNeeded()
        let fmt = UIGraphicsImageRendererFormat()
        fmt.scale = 3.0
        return UIGraphicsImageRenderer(bounds: bounds, format: fmt).image { ctx in
            if !host.view.drawHierarchy(in: bounds, afterScreenUpdates: true) {
                host.view.layer.render(in: ctx.cgContext)
            }
        }
    }

    private struct OCRToken {
        let text: String
        let pixelHeight: CGFloat
    }

    private func recognizeTokens(in image: UIImage) throws -> [OCRToken] {
        let cgImage = try XCTUnwrap(image.cgImage)
        var tokens: [OCRToken] = []
        let request = VNRecognizeTextRequest { req, _ in
            guard let results = req.results as? [VNRecognizedTextObservation] else { return }
            for obs in results {
                if let top = obs.topCandidates(1).first {
                    let h = obs.boundingBox.height * CGFloat(cgImage.height)
                    tokens.append(OCRToken(text: top.string, pixelHeight: h))
                }
            }
        }
        request.recognitionLevel = .accurate
        request.usesLanguageCorrection = false
        try VNImageRequestHandler(cgImage: cgImage, options: [:]).perform([request])
        return tokens
    }

    private func tokenHeight(matching needle: String, in tokens: [OCRToken], context: String) throws -> CGFloat {
        // Prefer an exact token match first, then a short containing observation (excluding long sentence lines).
        if let exact = tokens.first(where: { $0.text.trimmingCharacters(in: .whitespaces) == needle }) {
            return exact.pixelHeight
        }
        if let shortMatch = tokens.first(where: { $0.text.contains(needle) && $0.text.count <= needle.count + 6 }) {
            return shortMatch.pixelHeight
        }
        let dump = tokens.map { "\($0.text)(\(Int($0.pixelHeight))px)" }.joined(separator: " | ")
        XCTFail("Missing '\(needle)' on \(context). OCR tokens: \(dump)")
        return 0
    }

    func testNowAndChanceNeverDrawSmallerThanScoreBesideThemOnSportsAndSearchCards() throws {
        let suiteName = "SmallNumberCardGuard.\(UUID().uuidString)"
        let defaults = try XCTUnwrap(UserDefaults(suiteName: suiteName))
        defer { defaults.removePersistentDomain(forName: suiteName) }
        let pins = PinManager(
            defaults: defaults,
            serverLoad: { PinsResponse(events: [], futures: []) },
            serverSync: { _, _, _ in }
        )

        let liveJSON = """
        {
          "id": 15350104,
          "sport": "basketball_nba",
          "sport_name": "NBA",
          "away_team": "Utah Jazz",
          "home_team": "Los Angeles Clippers",
          "away_team_data": {"primary_color": "#002B5C", "abbreviation": "UTA"},
          "home_team_data": {"primary_color": "#C8102E", "abbreviation": "LAC"},
          "commence_time": "2026-11-18T02:00:00Z",
          "status": "live",
          "away_score": 58,
          "home_score": 62,
          "espn": {"period": "Q2", "game_clock": "3:12"},
          "hero_probability_source": "blend",
          "current_odds": {
            "away_probability": 0.30,
            "home_probability": 0.70,
            "away_rendered_percent": 30,
            "home_rendered_percent": 70,
            "live_projection": {
              "projected_away_score": 116.0,
              "projected_home_score": 120.0,
              "kind": "in_play",
              "captured_at": "2026-11-18T03:10:00Z",
              "scheduled_start": "2026-11-18T02:00:00Z",
              "source": "sportsbooks",
              "basis": "consensus_spread_total",
              "bookmaker_count": 4,
              "unit": "points",
              "period": "full_game"
            }
          },
          "prematch_odds": {
            "away_probability": 0.33,
            "home_probability": 0.67,
            "away_rendered_percent": 33,
            "home_rendered_percent": 67,
            "source": "books"
          }
        }
        """

        let scheduledJSON = """
        {
          "id": 15350575,
          "sport": "basketball_nba",
          "sport_name": "NBA",
          "away_team": "Houston Rockets",
          "home_team": "Denver Nuggets",
          "away_team_data": {"primary_color": "#CE1141", "abbreviation": "HOU"},
          "home_team_data": {"primary_color": "#0E2240", "abbreviation": "DEN"},
          "commence_time": "2026-11-20T02:00:00Z",
          "status": "scheduled",
          "hero_probability_source": "blend",
          "current_odds": {
            "away_probability": 0.47,
            "home_probability": 0.53,
            "away_rendered_percent": 47,
            "home_rendered_percent": 53,
            "projected_away_score": 109.0,
            "projected_home_score": 112.0
          }
        }
        """

        let sportsLive = try decodeFeedEvent(liveJSON)
        let sportsScheduled = try decodeFeedEvent(scheduledJSON)
        let searchLive = SearchEventCardAdapter183A.fromSearchResult(
            try decodeSearchEvent(liveJSON),
            sportDisplayName: "NBA"
        )
        let searchScheduled = SearchEventCardAdapter183A.fromSearchResult(
            try decodeSearchEvent(scheduledJSON),
            sportDisplayName: "NBA"
        )

        let surfaces: [(name: String, width: CGFloat, live: FeedEventData, scheduled: FeedEventData)] = [
            ("Sports", 358, sportsLive, sportsScheduled),
            ("Search", 306, searchLive, searchScheduled)
        ]

        for surface in surfaces {
            for typeSize in [DynamicTypeSize.large, .xxxLarge, .accessibility5] {
                let liveCtx = "\(surface.name) live (\(Int(surface.width))pt, \(typeSize))"
                let liveImage = try renderCardPNG(
                    EventCardView(event: surface.live, reason: nil)
                        .padding(.horizontal, 12)
                        .environmentObject(pins),
                    width: surface.width,
                    at: typeSize
                )
                let liveTokens = try recognizeTokens(in: liveImage)
                let awayScoreH = try tokenHeight(matching: "58", in: liveTokens, context: liveCtx)
                let homeScoreH = try tokenHeight(matching: "62", in: liveTokens, context: liveCtx)
                let awayNowH = try tokenHeight(matching: "30.0%", in: liveTokens, context: liveCtx)
                let homeNowH = try tokenHeight(matching: "70.0%", in: liveTokens, context: liveCtx)

                XCTAssertGreaterThanOrEqual(
                    awayNowH,
                    awayScoreH,
                    "\(liveCtx): away Now (30.0% = \(awayNowH)px) drew smaller than away Score (58 = \(awayScoreH)px)"
                )
                XCTAssertGreaterThanOrEqual(
                    homeNowH,
                    homeScoreH,
                    "\(liveCtx): home Now (70.0% = \(homeNowH)px) drew smaller than home Score (62 = \(homeScoreH)px)"
                )

                let schedCtx = "\(surface.name) scheduled (\(Int(surface.width))pt, \(typeSize))"
                let schedImage = try renderCardPNG(
                    EventCardView(event: surface.scheduled, reason: nil)
                        .padding(.horizontal, 12)
                        .environmentObject(pins),
                    width: surface.width,
                    at: typeSize
                )
                let schedTokens = try recognizeTokens(in: schedImage)
                let awayChanceH = try tokenHeight(matching: "47%", in: schedTokens, context: schedCtx)
                let homeChanceH = try tokenHeight(matching: "53%", in: schedTokens, context: schedCtx)

                if !typeSize.isAccessibilitySize {
                    let awayProjH = try tokenHeight(matching: "109", in: schedTokens, context: schedCtx)
                    let homeProjH = try tokenHeight(matching: "112", in: schedTokens, context: schedCtx)
                    XCTAssertGreaterThanOrEqual(
                        awayChanceH,
                        awayProjH,
                        "\(schedCtx): away Chance (47% = \(awayChanceH)px) drew smaller than projected score (109 = \(awayProjH)px)"
                    )
                    XCTAssertGreaterThanOrEqual(
                        homeChanceH,
                        homeProjH,
                        "\(schedCtx): home Chance (53% = \(homeChanceH)px) drew smaller than projected score (112 = \(homeProjH)px)"
                    )
                } else {
                    // At AX5, scheduled projection moves to the bottom caption line; verify Chance stays >= the AX5 live Score height.
                    XCTAssertGreaterThanOrEqual(
                        awayChanceH,
                        awayScoreH,
                        "\(schedCtx): away Chance (47% = \(awayChanceH)px) drew smaller than AX5 card score (\(awayScoreH)px)"
                    )
                    XCTAssertGreaterThanOrEqual(
                        homeChanceH,
                        homeScoreH,
                        "\(schedCtx): home Chance (53% = \(homeChanceH)px) drew smaller than AX5 card score (\(homeScoreH)px)"
                    )
                }
            }
        }
    }
}
