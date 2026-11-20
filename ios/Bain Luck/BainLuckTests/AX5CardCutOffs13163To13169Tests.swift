import SwiftUI
import UIKit
import Vision
import XCTest

@testable import Bain_Luck

@MainActor
final class AX5CardCutOffs13163To13169Tests: XCTestCase {

    private func makeDecoder() -> JSONDecoder {
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        return d
    }

    private func renderSnapshot<V: View>(
        _ view: V,
        width: CGFloat = 390,
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
            ? Color(red: 0.05, green: 0.07, blue: 0.11)
            : Color(red: 0.96, green: 0.97, blue: 0.98)
        let wrapped = view
            .fixedSize(horizontal: false, vertical: true)
            .padding(16)
            .frame(width: width)
            .background(bg)
            .environment(\.dynamicTypeSize, dynamicTypeSize)
            .environment(\.colorScheme, colorScheme)
            .environmentObject(PinManager())

        let window = UIWindow(frame: CGRect(x: 0, y: 0, width: width, height: 2600))
        window.overrideUserInterfaceStyle = colorScheme == .dark ? .dark : .light
        let host = hostForMeasurement(wrapped, at: dynamicTypeSize)
        host.overrideUserInterfaceStyle = colorScheme == .dark ? .dark : .light
        host.sizingOptions = [.intrinsicContentSize]
        window.rootViewController = host
        window.makeKeyAndVisible()
        host.view.overrideUserInterfaceStyle = colorScheme == .dark ? .dark : .light
        host.traitOverrides.preferredContentSizeCategory = contentSizeCategory
        host.view.layoutIfNeeded()
        RunLoop.main.run(until: Date().addingTimeInterval(0.08))
        host.view.layoutIfNeeded()

        let measured = host.sizeThatFits(in: CGSize(width: width, height: 10000))
        let height = max(ceil(measured.height), 120)
        window.frame = CGRect(x: 0, y: 0, width: width, height: height)
        host.view.frame = CGRect(x: 0, y: 0, width: width, height: height)
        host.view.layoutIfNeeded()
        RunLoop.main.run(until: Date().addingTimeInterval(0.05))

        let format = UIGraphicsImageRendererFormat()
        format.scale = 3.0
        let renderer = UIGraphicsImageRenderer(size: CGSize(width: width, height: height), format: format)
        return renderer.image { _ in
            host.view.drawHierarchy(in: host.view.bounds, afterScreenUpdates: true)
        }
    }

    private func sideBySide(_ left: UIImage, _ right: UIImage) -> UIImage {
        let gap: CGFloat = 12
        let width = left.size.width + gap + right.size.width
        let height = max(left.size.height, right.size.height)
        let format = UIGraphicsImageRendererFormat()
        format.scale = 3.0
        return UIGraphicsImageRenderer(size: CGSize(width: width, height: height), format: format).image { ctx in
            UIColor(white: 0.5, alpha: 0.15).setFill()
            ctx.fill(CGRect(x: 0, y: 0, width: width, height: height))
            left.draw(in: CGRect(x: 0, y: 0, width: left.size.width, height: left.size.height))
            right.draw(in: CGRect(x: left.size.width + gap, y: 0, width: right.size.width, height: right.size.height))
        }
    }

    private func ocrStrings(in image: UIImage) throws -> [String] {
        let cgImage = try XCTUnwrap(image.cgImage)
        let request = VNRecognizeTextRequest()
        request.recognitionLevel = .accurate
        request.usesLanguageCorrection = false
        let handler = VNImageRequestHandler(cgImage: cgImage, options: [:])
        try handler.perform([request])
        return (request.results ?? []).compactMap { $0.topCandidates(1).first?.string }
    }

    private func maybeExport(_ name: String, light: UIImage, dark: UIImage) throws {
        guard let dir = ProcessInfo.processInfo.environment["EXPORT_13163_13169_RENDERS_DIR"],
              !dir.isEmpty else { return }
        try FileManager.default.createDirectory(atPath: dir, withIntermediateDirectories: true)
        let pair = sideBySide(light, dark)
        try XCTUnwrap(pair.pngData()).write(to: URL(fileURLWithPath: "\(dir)/\(name).png"))
    }

    // MARK: - #13163: NativeFuturesDiscoverCard headline & leader name

    func test13163FuturesCardHeadlineAndLeaderNeverTruncateAtLargestText() throws {
        let json = #"""
        {
          "id": 913163,
          "name": "Katy Perry and Justin Trudeau engaged in 2026?",
          "llm_sport_category": "entertainment",
          "resolution_date": "2027-01-01T00:00:00Z",
          "top_outcomes": [
            {"id": 1, "name": "Katy Perry and Justin Trudeau engaged in 2026", "probability": 0.25, "rendered_percent": 25, "rank": 1, "movement": 0.02}
          ]
        }
        """#
        let data = try makeDecoder().decode(FeedFuturesData.self, from: Data(json.utf8))

        for (sizeLabel, typeSize) in [("default", DynamicTypeSize.large), ("largest", DynamicTypeSize.accessibility5)] {
            var rendered: [ColorScheme: UIImage] = [:]
            for scheme in [ColorScheme.light, ColorScheme.dark] {
                let img = renderSnapshot(
                    NativeFuturesDiscoverCard(
                        data: data,
                        feedContext: "Steady at 25%.",
                        expandedContext: nil,
                        navigationPath: .constant(NavigationPath())
                    ),
                    dynamicTypeSize: typeSize,
                    colorScheme: scheme
                )
                rendered[scheme] = img
                let lines = try ocrStrings(in: img)
                let joined = lines.joined(separator: " ")
                XCTAssertFalse(joined.contains("\u{2026}") || joined.contains("..."), "13163 (\(sizeLabel), \(scheme)) truncated with ellipsis: \(joined)")
                for token in ["Katy Perry", "Justin Trudeau", "engaged in 2026", "25%"] {
                    XCTAssertTrue(joined.localizedCaseInsensitiveContains(token), "13163 (\(sizeLabel), \(scheme)) missing '\(token)': \(joined)")
                }
            }
            try maybeExport("13163-futures-card-\(sizeLabel)-light-dark-390", light: rendered[.light]!, dark: rendered[.dark]!)
        }
    }

    // MARK: - #13164: NativeGroupCard compactRow outcomes

    func test13164GroupCardOutcomeRowsNeverTruncateAtLargestText() throws {
        let json = #"""
        [
          {
            "type": "futures",
            "score": 80,
            "data": {
              "id": 9131641,
              "name": "Fed Decision in December — No change",
              "llm_sport_category": "economics",
              "top_outcomes": [{"id": 11, "name": "No change", "probability": 0.91, "rendered_percent": 91, "rank": 1, "movement": 0.01}]
            }
          },
          {
            "type": "futures",
            "score": 79,
            "data": {
              "id": 9131642,
              "name": "Fed Decision in December — 25 bps decrease",
              "llm_sport_category": "economics",
              "top_outcomes": [{"id": 12, "name": "25 bps decrease", "probability": 0.08, "rendered_percent": 8, "rank": 2, "movement": -0.01}]
            }
          },
          {
            "type": "futures",
            "score": 78,
            "data": {
              "id": 9131643,
              "name": "Fed Decision in December — 50+ bps decrease",
              "llm_sport_category": "economics",
              "top_outcomes": [{"id": 13, "name": "50+ bps decrease", "probability": 0.01, "rendered_percent": 1, "rank": 3, "movement": 0.0}]
            }
          }
        ]
        """#
        let items = try makeDecoder().decode([FeedItem].self, from: Data(json.utf8))

        for (sizeLabel, typeSize) in [("default", DynamicTypeSize.large), ("largest", DynamicTypeSize.accessibility5)] {
            var rendered: [ColorScheme: UIImage] = [:]
            for scheme in [ColorScheme.light, ColorScheme.dark] {
                let img = renderSnapshot(
                    NativeGroupCard(
                        title: "Fed Decision in December",
                        items: items,
                        kind: "market_group",
                        navigationPath: .constant(NavigationPath())
                    ),
                    dynamicTypeSize: typeSize,
                    colorScheme: scheme
                )
                rendered[scheme] = img
                let lines = try ocrStrings(in: img)
                let joined = lines.joined(separator: " ")
                XCTAssertFalse(joined.contains("\u{2026}"), "13164 (\(sizeLabel), \(scheme)) truncated with ellipsis: \(joined)")
                for token in ["No change", "25 bps decrease", "50+ bps decrease", "91%", "8%", "1%"] {
                    XCTAssertTrue(joined.localizedCaseInsensitiveContains(token), "13164 (\(sizeLabel), \(scheme)) missing '\(token)': \(joined)")
                }
            }
            try maybeExport("13164-group-card-\(sizeLabel)-light-dark-390", light: rendered[.light]!, dark: rendered[.dark]!)
        }
    }

    // MARK: - #13165: HeatMapCardView threshold numbers

    func test13165HeatMapCellsNeverTruncateThresholdsAtLargestText() throws {
        let json = #"""
        {
          "id": 913165,
          "name": "Top AI Elo score by end of 2026",
          "llm_sport_category": "tech",
          "resolution_date": "2027-01-01T00:00:00Z",
          "top_outcomes": [{"id": 21, "name": "1450+", "probability": 0.64, "rendered_percent": 64, "rank": 1, "movement": 0.03}],
          "discover_card": {
            "suggested_format": "heatmap",
            "threshold_points": [
              {"label": "1430+", "value": 1430, "probability": 0.92},
              {"label": "1440+", "value": 1440, "probability": 0.81},
              {"label": "1450+", "value": 1450, "probability": 0.64},
              {"label": "1460+", "value": 1460, "probability": 0.38},
              {"label": "1470+", "value": 1470, "probability": 0.17}
            ]
          }
        }
        """#
        let data = try makeDecoder().decode(FeedFuturesData.self, from: Data(json.utf8))

        for (sizeLabel, typeSize) in [("default", DynamicTypeSize.large), ("largest", DynamicTypeSize.accessibility5)] {
            var rendered: [ColorScheme: UIImage] = [:]
            for scheme in [ColorScheme.light, ColorScheme.dark] {
                let img = renderSnapshot(
                    HeatMapCardView(data: data, navigationPath: .constant(NavigationPath())),
                    dynamicTypeSize: typeSize,
                    colorScheme: scheme
                )
                rendered[scheme] = img
                let lines = try ocrStrings(in: img)
                let joined = lines.joined(separator: " ")
                XCTAssertFalse(joined.contains("\u{2026}"), "13165 (\(sizeLabel), \(scheme)) truncated with ellipsis: \(joined)")
                for token in ["1430+", "1440+", "1450+", "1460+", "1470+", "92%", "64%", "17%"] {
                    XCTAssertTrue(joined.localizedCaseInsensitiveContains(token), "13165 (\(sizeLabel), \(scheme)) missing '\(token)': \(joined)")
                }
            }
            try maybeExport("13165-heatmap-card-\(sizeLabel)-light-dark-390", light: rendered[.light]!, dark: rendered[.dark]!)
        }
    }

    // MARK: - #13166: LivePregameSummaryRow214A1 projected score line

    func test13166LivePregameSummaryRowNeverTruncatesProjectedScoresAtLargestText() throws {
        let eventJSON = #"""
        {
          "id": 913166,
          "sport": "basketball_nba",
          "sport_name": "NBA",
          "home_team": "New Orleans Pelicans",
          "away_team": "Houston Rockets",
          "commence_time": "2026-11-20T01:00:00Z",
          "status": "live",
          "home_score": 82,
          "away_score": 89,
          "espn": {"period": "3Q", "display_clock": "4:12"},
          "current_odds": {"home_probability": 0.28, "away_probability": 0.72, "home_rendered_percent": 28, "away_rendered_percent": 72},
          "prematch_odds": {"home_probability": 0.44, "away_probability": 0.56, "home_rendered_percent": 44, "away_rendered_percent": 56},
          "pregame_projection": {
            "projected_home_score": 109.2,
            "projected_away_score": 114.3,
            "kind": "last_before_scheduled_start",
            "earliest_captured_at": "2026-11-19T22:00:00Z",
            "latest_captured_at": "2026-11-20T00:55:00Z",
            "boundary": "scheduled_start",
            "boundary_at": "2026-11-20T01:00:00Z",
            "source": "sportsbooks",
            "basis": "consensus_spread_total",
            "bookmaker_count": 5,
            "unit": "points",
            "period": "full_game"
          },
          "home_team_data": {"id": 20, "name": "New Orleans Pelicans", "abbreviation": "NOP", "primary_color": "#0C2340", "secondary_color": "#C8102E"},
          "away_team_data": {"id": 21, "name": "Houston Rockets", "abbreviation": "HOU", "primary_color": "#CE1141", "secondary_color": "#000000"}
        }
        """#
        let event = try makeDecoder().decode(FeedEventData.self, from: Data(eventJSON.utf8))

        for (sizeLabel, typeSize) in [("default", DynamicTypeSize.large), ("largest", DynamicTypeSize.accessibility5)] {
            var rendered: [ColorScheme: UIImage] = [:]
            for scheme in [ColorScheme.light, ColorScheme.dark] {
                let card = EventCardView(event: event, reason: nil)
                    .padding(14)
                    .background(Color(uiColor: .secondarySystemGroupedBackground), in: RoundedRectangle(cornerRadius: 14))

                let img = renderSnapshot(card, dynamicTypeSize: typeSize, colorScheme: scheme)
                rendered[scheme] = img
                let lines = try ocrStrings(in: img)
                let joined = lines.joined(separator: " ")
                XCTAssertFalse(joined.contains("\u{2026}"), "13166 (\(sizeLabel), \(scheme)) truncated with ellipsis: \(joined)")
                for token in ["Rockets", "Pelicans", "Pregame", "56%", "projected", "114", "109"] {
                    XCTAssertTrue(joined.localizedCaseInsensitiveContains(token), "13166 (\(sizeLabel), \(scheme)) missing '\(token)': \(joined)")
                }
            }
            try maybeExport("13166-live-pregame-summary-\(sizeLabel)-light-dark-390", light: rendered[.light]!, dark: rendered[.dark]!)
        }
    }

    // MARK: - #13167: NativeTournamentDiscoverCard title, leader, and movement

    func test13167TournamentCardNeverTruncatesTitleOrLeaderAtLargestText() throws {
        let json = #"""
        {
          "key": "lpga-cme-group-tour-championship-2026",
          "name": "CME Group Tour Championship",
          "tour": "lpga",
          "tour_label": "LPGA TOUR",
          "venue": "Tiburon Golf Club",
          "location": "Naples, FL",
          "schedule_status": "in_progress",
          "marquee_whathit": false,
          "golfers": [
            {"name": "Jeeno Thitikul", "probability": 0.43, "rendered_percent": 43, "rank": 1, "movement_24h": 0.127},
            {"name": "Nelly Korda", "probability": 0.22, "rendered_percent": 22, "rank": 2, "movement_24h": -0.031},
            {"name": "Lydia Ko", "probability": 0.11, "rendered_percent": 11, "rank": 3, "movement_24h": 0.015},
            {"name": "Ruoning Yin", "probability": 0.08, "rendered_percent": 8, "rank": 4, "movement_24h": 0.005}
          ]
        }
        """#
        let data = try makeDecoder().decode(FeedTournamentData.self, from: Data(json.utf8))

        for (sizeLabel, typeSize) in [("default", DynamicTypeSize.large), ("largest", DynamicTypeSize.accessibility5)] {
            var rendered: [ColorScheme: UIImage] = [:]
            for scheme in [ColorScheme.light, ColorScheme.dark] {
                let img = renderSnapshot(
                    NativeTournamentDiscoverCard(
                        data: data,
                        feedContext: "Round 3 underway in Naples.",
                        navigationPath: .constant(NavigationPath())
                    ),
                    dynamicTypeSize: typeSize,
                    colorScheme: scheme
                )
                rendered[scheme] = img
                let lines = try ocrStrings(in: img)
                let joined = lines.joined(separator: " ")
                let dehyphenated = joined.replacingOccurrences(of: "- ", with: "")
                XCTAssertFalse(joined.contains("\u{2026}") || joined.contains("..."), "13167 (\(sizeLabel), \(scheme)) truncated with ellipsis: \(joined)")
                for token in ["CME Group", "Tour", "Championship", "Jeeno Thitikul", "43%", "12.7 points today", "Naples"] {
                    XCTAssertTrue(dehyphenated.localizedCaseInsensitiveContains(token), "13167 (\(sizeLabel), \(scheme)) missing '\(token)': \(joined)")
                }
            }
            try maybeExport("13167-tournament-card-\(sizeLabel)-light-dark-390", light: rendered[.light]!, dark: rendered[.dark]!)
        }
    }

    // MARK: - #13169: MyTeamFuturesCard team rows and leader footer

    func test13169MyTeamFuturesCardNeverTruncatesTeamOrLeaderAtLargestText() throws {
        let futuresJSON = #"""
        {
          "id": 913169,
          "name": "NBA Finals Winner 2026-27",
          "llm_sport_category": "basketball",
          "top_outcomes": [
            {"id": 31, "name": "Oklahoma City Thunder", "probability": 0.27, "rendered_percent": 27, "rank": 1, "movement": 0.012},
            {"id": 32, "name": "Boston Celtics", "probability": 0.19, "rendered_percent": 19, "rank": 2, "movement": 0.008},
            {"id": 33, "name": "Golden State Warriors", "probability": 0.06, "rendered_percent": 6, "rank": 7, "movement": -0.005}
          ]
        }
        """#
        let matchedJSON = #"""
        [
          {"name": "Boston Celtics", "probability": 0.19, "rank": 2, "movement": 0.008},
          {"name": "Golden State Warriors", "probability": 0.06, "rank": 7, "movement": -0.005}
        ]
        """#
        let futures = try makeDecoder().decode(FeedFuturesData.self, from: Data(futuresJSON.utf8))
        let matched = try makeDecoder().decode([MatchedOutcome].self, from: Data(matchedJSON.utf8))

        for (sizeLabel, typeSize) in [("default", DynamicTypeSize.large), ("largest", DynamicTypeSize.accessibility5)] {
            var rendered: [ColorScheme: UIImage] = [:]
            for scheme in [ColorScheme.light, ColorScheme.dark] {
                let img = renderSnapshot(
                    MyTeamFuturesCard(futures: futures, matchedOutcomes: matched),
                    dynamicTypeSize: typeSize,
                    colorScheme: scheme
                )
                rendered[scheme] = img
                let lines = try ocrStrings(in: img)
                let joined = lines.joined(separator: " ")
                XCTAssertFalse(joined.contains("\u{2026}"), "13169 (\(sizeLabel), \(scheme)) truncated with ellipsis: \(joined)")
                for token in ["Boston Celtics", "19%", "Golden State Warriors", "6%", "Oklahoma City Thunder", "27%"] {
                    XCTAssertTrue(joined.localizedCaseInsensitiveContains(token), "13169 (\(sizeLabel), \(scheme)) missing '\(token)': \(joined)")
                }
            }
            try maybeExport("13169-my-team-futures-card-\(sizeLabel)-light-dark-390", light: rendered[.light]!, dark: rendered[.dark]!)
        }
    }
}
