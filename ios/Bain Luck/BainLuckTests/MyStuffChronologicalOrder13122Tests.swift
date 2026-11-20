import SwiftUI
import UIKit
import Vision
import XCTest

@testable import Bain_Luck

@MainActor
final class MyStuffChronologicalOrder13122Tests: XCTestCase {

    private nonisolated final class StubMyStuffClient: MyStuffFeedProviding, @unchecked Sendable {
        let feed: FeedResponse
        let futures: TeamFuturesResponse

        init(feed: FeedResponse, futures: TeamFuturesResponse) {
            self.feed = feed
            self.futures = futures
        }

        nonisolated func fetchMyTeamsFeed() async throws -> FeedResponse { feed }
        nonisolated func fetchMyTeamFuturesSection(limit: Int) async throws -> TeamFuturesResponse { futures }
        nonisolated func currentMyStuffPrincipal() -> String? { "user:test-13122" }
    }

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
            default: return .large
            }
        }()
        let bg = colorScheme == .dark
            ? Color(red: 0.05, green: 0.07, blue: 0.11)
            : Color(red: 0.95, green: 0.96, blue: 0.98)
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

    func testUpcomingSortsSoonestFirstAndJustHappenedMostRecentFirst() async throws {
        let feedJSON = #"""
        {
          "items": [
            {
              "type": "event",
              "score": 91.0,
              "data": {
                "id": 23704,
                "sport": "basketball_nba",
                "sport_name": "NBA",
                "home_team": "Washington Wizards",
                "away_team": "Boston Celtics",
                "commence_time": "2026-11-25T00:00:00Z",
                "status": "scheduled",
                "current_odds": {"home_probability": 0.21, "away_probability": 0.79, "home_rendered_percent": 21, "away_rendered_percent": 79}
              }
            },
            {
              "type": "event",
              "score": 88.0,
              "data": {
                "id": 23703,
                "sport": "basketball_nba",
                "sport_name": "NBA",
                "home_team": "Golden State Warriors",
                "away_team": "Boston Celtics",
                "commence_time": "2026-11-23T01:30:00Z",
                "status": "scheduled",
                "current_odds": {"home_probability": 0.42, "away_probability": 0.58, "home_rendered_percent": 42, "away_rendered_percent": 58}
              }
            },
            {
              "type": "event",
              "score": 84.0,
              "data": {
                "id": 23701,
                "sport": "soccer_usa_mls",
                "sport_name": "MLS",
                "home_team": "New England Revolution",
                "away_team": "Philadelphia Union",
                "commence_time": "2026-11-21T20:30:00Z",
                "status": "scheduled",
                "current_odds": {
                  "home_probability": 0.31,
                  "draw_probability": 0.25,
                  "away_probability": 0.44,
                  "home_rendered_percent": 31,
                  "away_rendered_percent": 44,
                  "projected_home_score": 1.1,
                  "projected_away_score": 1.8
                }
              }
            },
            {
              "type": "event",
              "score": 82.0,
              "data": {
                "id": 23702,
                "sport": "icehockey_nhl",
                "sport_name": "NHL",
                "home_team": "Boston Bruins",
                "away_team": "Washington Capitals",
                "commence_time": "2026-11-22T00:00:00Z",
                "status": "scheduled",
                "current_odds": {"home_probability": 0.54, "away_probability": 0.46, "home_rendered_percent": 54, "away_rendered_percent": 46}
              }
            },
            {
              "type": "event",
              "score": 80.0,
              "data": {
                "id": 237025,
                "sport": "basketball_nba",
                "sport_name": "NBA",
                "home_team": "Sacramento Kings",
                "away_team": "Boston Celtics",
                "commence_time": "2026-11-22T03:00:00Z",
                "status": "scheduled",
                "current_odds": {
                  "home_probability": 0.36,
                  "away_probability": 0.64,
                  "home_rendered_percent": 36,
                  "away_rendered_percent": 64,
                  "projected_home_score": 112.1,
                  "projected_away_score": 117.8
                }
              }
            },
            {
              "type": "event",
              "score": 76.0,
              "data": {
                "id": 23705,
                "sport": "icehockey_nhl",
                "sport_name": "NHL",
                "home_team": "Boston Bruins",
                "away_team": "Winnipeg Jets",
                "commence_time": "2026-11-26T00:00:00Z",
                "status": "scheduled",
                "current_odds": {"home_probability": 0.48, "away_probability": 0.52, "home_rendered_percent": 48, "away_rendered_percent": 52}
              }
            },
            {
              "type": "event",
              "score": 70.0,
              "data": {
                "id": 23690,
                "sport": "basketball_nba",
                "sport_name": "NBA",
                "home_team": "Boston Celtics",
                "away_team": "Cleveland Cavaliers",
                "commence_time": "2026-11-18T00:00:00Z",
                "status": "completed",
                "home_score": 120,
                "away_score": 117,
                "hero_probability_source": "settled",
                "prematch_odds": {"home_probability": 0.55, "away_probability": 0.45, "home_rendered_percent": 55, "away_rendered_percent": 45}
              }
            },
            {
              "type": "event",
              "score": 65.0,
              "data": {
                "id": 23699,
                "sport": "icehockey_nhl",
                "sport_name": "NHL",
                "home_team": "Boston Bruins",
                "away_team": "St. Louis Blues",
                "commence_time": "2026-11-19T01:00:00Z",
                "status": "completed",
                "home_score": 3,
                "away_score": 2,
                "hero_probability_source": "settled",
                "prematch_odds": {"home_probability": 0.58, "away_probability": 0.42, "home_rendered_percent": 58, "away_rendered_percent": 42}
              }
            }
          ],
          "total": 8,
          "has_more": false
        }
        """#
        let futuresJSON = #"{"items":[],"team_ids":[1],"total_count":0}"#
        let decoder = makeDecoder()
        let feed = try decoder.decode(FeedResponse.self, from: Data(feedJSON.utf8))
        let futures = try decoder.decode(TeamFuturesResponse.self, from: Data(futuresJSON.utf8))

        let vm = MyStuffViewModel(
            client: StubMyStuffClient(feed: feed, futures: futures),
            telemetry: { _ in },
            autoRefreshEnabled: false,
            retryBackoff: 0.001
        )
        await vm.startLoad()

        XCTAssertEqual(
            vm.upcoming.compactMap { $0.event?.id },
            [23701, 23702, 237025, 23703, 23704, 23705],
            "Upcoming must sort soonest kickoff first (Sat Union @ Revs, Sat Capitals @ Bruins, Sat Celtics @ Kings, Sun Celtics @ Warriors, Tue Celtics @ Wizards, Wed Jets @ Bruins)"
        )
        XCTAssertEqual(
            vm.justHappened.compactMap { $0.event?.id },
            [23699, 23690],
            "Just Happened must sort most recent kickoff first"
        )

        let topUpcoming = Array(vm.upcoming.prefix(4))
        for (sizeLabel, typeSize) in [("default", DynamicTypeSize.large), ("largest", DynamicTypeSize.accessibility5)] {
            var rendered: [ColorScheme: UIImage] = [:]
            for scheme in [ColorScheme.light, ColorScheme.dark] {
                let sectionView = VStack(alignment: .leading, spacing: 10) {
                    HStack(spacing: 6) {
                        Label("Upcoming", systemImage: "calendar")
                            .foregroundStyle(.blue)
                            .font(.subheadline.weight(.semibold))
                        Text("\(vm.upcoming.count)")
                            .font(.caption2.weight(.medium))
                            .foregroundStyle(.secondary)
                            .padding(.horizontal, 6)
                            .padding(.vertical, 2)
                            .background(Color.secondary.opacity(0.12), in: Capsule())
                    }
                    ForEach(topUpcoming) { item in
                        if let event = item.event {
                            EventCardView(event: event, reason: nil)
                                .padding(12)
                                .background(Color(uiColor: .secondarySystemGroupedBackground), in: RoundedRectangle(cornerRadius: 12))
                        }
                    }
                }
                let img = renderSnapshot(sectionView, dynamicTypeSize: typeSize, colorScheme: scheme)
                rendered[scheme] = img
                let lines = try ocrStrings(in: img)
                let joined = lines.joined(separator: " ")
                XCTAssertFalse(joined.contains("\u{2026}") || joined.contains("..."), "13122 (\(sizeLabel), \(scheme)) truncated with ellipsis: \(joined)")
                for token in ["Upcoming", "Union", "Revolution", "Proj", "Bruins", "Celtics", "Kings", "118", "112"] {
                    XCTAssertTrue(joined.localizedCaseInsensitiveContains(token), "13122 (\(sizeLabel), \(scheme)) missing '\(token)': \(joined)")
                }
            }
            if let dir = ProcessInfo.processInfo.environment["EXPORT_13122_RENDERS_DIR"], !dir.isEmpty {
                try FileManager.default.createDirectory(atPath: dir, withIntermediateDirectories: true)
                let pair = sideBySide(rendered[.light]!, rendered[.dark]!)
                try XCTUnwrap(pair.pngData()).write(to: URL(fileURLWithPath: "\(dir)/13122-mystuff-upcoming-\(sizeLabel)-light-dark-390.png"))
            }
        }
    }

    func testUpcomingPreservesFeedOrderOnEqualTimestampsAndPlacesNilDatesLast() throws {
        let json = #"""
        [
          {"type": "event", "score": 90, "data": {"id": 1, "sport": "basketball_nba", "home_team": "Hawks", "away_team": "Heat", "status": "scheduled"}},
          {"type": "event", "score": 85, "data": {"id": 2, "sport": "basketball_nba", "home_team": "Knicks", "away_team": "Nets", "commence_time": "2026-11-22T00:00:00Z", "status": "scheduled"}},
          {"type": "event", "score": 80, "data": {"id": 3, "sport": "basketball_nba", "home_team": "Bulls", "away_team": "Bucks", "commence_time": "2026-11-22T00:00:00Z", "status": "scheduled"}},
          {"type": "event", "score": 75, "data": {"id": 4, "sport": "basketball_nba", "home_team": "Suns", "away_team": "Lakers", "commence_time": "2026-11-21T23:00:00Z", "status": "scheduled"}}
        ]
        """#
        let items = try makeDecoder().decode([FeedItem].self, from: Data(json.utf8))
        XCTAssertEqual(MyStuffViewModel.sortUpcoming(items).compactMap { $0.event?.id }, [4, 2, 3, 1])
    }
}
