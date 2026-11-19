import SwiftUI
import UIKit
import Vision
import XCTest
@testable import Bain_Luck

@MainActor
final class GameCardChanceFullSizeAsk2Tests: XCTestCase {

    private func decodeEvent(_ json: String) throws -> FeedEventData {
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        return try d.decode(FeedEventData.self, from: Data(json.utf8))
    }

    private func renderPNG<V: View>(_ view: V, width: CGFloat, typeSize: DynamicTypeSize = .large) -> UIImage {
        let wrapped = view
            .environment(\.colorScheme, .light)
            .background(Color.white)
        let measureHost = hostForMeasurement(wrapped, at: typeSize)
        measureHost.overrideUserInterfaceStyle = .light
        let fittedH = ceil(measureHost.sizeThatFits(in: CGSize(width: width, height: 1200)).height) + 28
        let size = CGSize(width: width, height: max(fittedH, 140))

        let host = hostForMeasurement(wrapped, at: typeSize)
        host.overrideUserInterfaceStyle = .light
        host.view.frame = CGRect(origin: .zero, size: size)
        let window = UIWindow(frame: host.view.frame)
        window.overrideUserInterfaceStyle = .light
        window.rootViewController = host
        window.isHidden = false
        defer {
            window.isHidden = true
            window.rootViewController = nil
        }
        host.view.setNeedsLayout()
        host.view.layoutIfNeeded()
        RunLoop.current.run(until: Date().addingTimeInterval(0.08))
        host.view.layoutIfNeeded()

        let fmt = UIGraphicsImageRendererFormat()
        fmt.scale = 3.0
        return UIGraphicsImageRenderer(bounds: host.view.bounds, format: fmt).image { _ in
            _ = host.view.drawHierarchy(in: host.view.bounds, afterScreenUpdates: true)
        }
    }

    private func ocrObservations(in image: UIImage) throws -> [(text: String, pixelHeight: CGFloat)] {
        let cgImage = try XCTUnwrap(image.cgImage)
        var results: [(String, CGFloat)] = []
        let request = VNRecognizeTextRequest { req, _ in
            guard let items = req.results as? [VNRecognizedTextObservation] else { return }
            for obs in items {
                if let top = obs.topCandidates(1).first {
                    results.append((top.string, obs.boundingBox.height * CGFloat(cgImage.height)))
                }
            }
        }
        request.recognitionLevel = .accurate
        request.usesLanguageCorrection = false
        try VNImageRequestHandler(cgImage: cgImage, options: [:]).perform([request])
        return results
    }

    func testSharedGameCardAndDiscoverCompactCardNeverShrinkChanceOrNowBelowScoreOrProj() throws {
        let suiteName = "GameCardChanceFullSizeAsk2.\(UUID().uuidString)"
        let defaults = try XCTUnwrap(UserDefaults(suiteName: suiteName))
        defer { defaults.removePersistentDomain(forName: suiteName) }
        let pins = PinManager(
            defaults: defaults,
            serverLoad: { PinsResponse(events: [], futures: []) },
            serverSync: { _, _, _ in }
        )

        let liveNBA = try decodeEvent("""
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
        """)

        let upcomingNBA = try decodeEvent("""
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
        """)

        // Narrow Search card width (306 pt inside chevron row) + standard Sports card width (358 pt)
        for cardWidth in [CGFloat(306), CGFloat(358)] {
            let liveImg = renderPNG(
                EventCardView(event: liveNBA, reason: nil)
                    .padding(.horizontal, 12)
                    .frame(width: cardWidth)
                    .environmentObject(pins),
                width: cardWidth
            )
            let liveObs = try ocrObservations(in: liveImg)
            let joinedLive = liveObs.map { $0.text }.joined(separator: " | ")
            XCTAssertFalse(joinedLive.contains("\u{2026}"), "Unexpected ellipsis at \(cardWidth): \(joinedLive)")

            let awayNowH = try XCTUnwrap(liveObs.first(where: { $0.text.contains("30.0%") })?.pixelHeight, "Missing 30.0% in \(joinedLive)")
            let homeNowH = try XCTUnwrap(liveObs.first(where: { $0.text.contains("70.0%") })?.pixelHeight, "Missing 70.0% in \(joinedLive)")

            // At 3x scale, unshrunken 20pt rounded heavy digits have OCR glyph height >= 40 px
            // (whereas the 0.45 minimumScaleFactor bug shrank them to ~22-28 px).
            XCTAssertGreaterThanOrEqual(awayNowH, 40.0, "Now (30.0%) shrank at width \(cardWidth): \(awayNowH) px")
            XCTAssertGreaterThanOrEqual(homeNowH, 40.0, "Now (70.0%) shrank at width \(cardWidth): \(homeNowH) px")

            let upImg = renderPNG(
                EventCardView(event: upcomingNBA, reason: nil)
                    .padding(.horizontal, 12)
                    .frame(width: cardWidth)
                    .environmentObject(pins),
                width: cardWidth
            )
            let upObs = try ocrObservations(in: upImg)
            let joinedUp = upObs.map { $0.text }.joined(separator: " | ")
            XCTAssertFalse(joinedUp.contains("\u{2026}"), "Unexpected ellipsis at \(cardWidth): \(joinedUp)")

            let awayChanceH = try XCTUnwrap(upObs.first(where: { $0.text.contains("47%") })?.pixelHeight, "Missing 47% in \(joinedUp)")
            let homeChanceH = try XCTUnwrap(upObs.first(where: { $0.text.contains("53%") })?.pixelHeight, "Missing 53% in \(joinedUp)")

            XCTAssertGreaterThanOrEqual(awayChanceH, 40.0, "Chance (47%) shrank at width \(cardWidth): \(awayChanceH) px")
            XCTAssertGreaterThanOrEqual(homeChanceH, 40.0, "Chance (53%) shrank at width \(cardWidth): \(homeChanceH) px")
        }

        // Discover compact upcoming game card (`NativeEventDiscoverCard` -> `DiscoverCompactSingleGameCard190CView`)
        let discImg = renderPNG(
            NativeEventDiscoverCard(
                event: upcomingNBA,
                feedContext: nil,
                expandedContext: nil,
                navigationPath: .constant(NavigationPath())
            )
            .frame(width: 358)
            .environmentObject(pins),
            width: 358
        )
        let discObs = try ocrObservations(in: discImg)
        let joinedDisc = discObs.map { $0.text }.joined(separator: " | ")
        let discAwayH = try XCTUnwrap(discObs.first(where: { $0.text.contains("47%") })?.pixelHeight, "Missing 47% in \(joinedDisc)")
        let discHomeH = try XCTUnwrap(discObs.first(where: { $0.text.contains("53%") })?.pixelHeight, "Missing 53% in \(joinedDisc)")
        XCTAssertGreaterThanOrEqual(discAwayH, 40.0, "Discover Chance (47%) shrank: \(discAwayH) px")
        XCTAssertGreaterThanOrEqual(discHomeH, 40.0, "Discover Chance (53%) shrank: \(discHomeH) px")
    }
}
