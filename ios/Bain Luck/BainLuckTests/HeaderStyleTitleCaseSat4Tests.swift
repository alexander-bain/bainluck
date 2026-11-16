import SwiftUI
import UIKit
import XCTest
@testable import Bain_Luck

/// Sat Nov 14 Item 4 — One header style across cards, widgets and headlines:
/// `"Proj."` and `"Chance"` (plus `"Score"`, `"Pregame"`, `"Now"`, `"Final"` / `"Result"`)
/// in Title Case matching the headline — never `.uppercased()` (`"PROJ."` / `"CHANCE"`).
@MainActor
final class HeaderStyleTitleCaseSat4Tests: XCTestCase {

    private let fixedNow = ISO8601DateFormatter().date(from: "2026-11-15T17:00:00Z")!

    private func decodeFeedEvent(_ json: String) throws -> FeedEventData {
        let dec = JSONDecoder()
        dec.keyDecodingStrategy = .convertFromSnakeCase
        return try dec.decode(FeedEventData.self, from: Data(json.utf8))
    }

    private func decodeEventDetail(_ json: String) throws -> EventDetail {
        let dec = JSONDecoder()
        dec.keyDecodingStrategy = .convertFromSnakeCase
        return try dec.decode(EventDetail.self, from: Data(json.utf8))
    }

    private func scheduledFeedFixture() throws -> FeedEventData {
        try decodeFeedEvent("""
        {
          "id": 401201,
          "sport": "americanfootball_nfl",
          "sport_name": "NFL",
          "home_team": "Green Bay Packers",
          "away_team": "Minnesota Vikings",
          "commence_time": "2026-11-15T21:25:00Z",
          "status": "scheduled",
          "home_team_data": {
            "abbreviation": "GB",
            "primary_color": "#203731",
            "record": "7-3"
          },
          "away_team_data": {
            "abbreviation": "MIN",
            "primary_color": "#4F2683",
            "record": "8-2"
          },
          "current_odds": {
            "home_probability": 0.59,
            "away_probability": 0.41,
            "home_rendered_percent": 59,
            "away_rendered_percent": 41,
            "projected_home_score": 24.0,
            "projected_away_score": 21.0,
            "updated_at": "2026-11-15T16:59:00Z"
          },
          "prematch_odds": {
            "home_probability": 0.56,
            "away_probability": 0.44,
            "home_rendered_percent": 56,
            "away_rendered_percent": 44
          },
          "espn": {
            "broadcast": "FOX"
          }
        }
        """)
    }

    private func liveFeedFixture() throws -> FeedEventData {
        try decodeFeedEvent("""
        {
          "id": 401202,
          "sport": "americanfootball_nfl",
          "sport_name": "NFL",
          "home_team": "Detroit Lions",
          "away_team": "New England Patriots",
          "commence_time": "2026-11-15T18:00:00Z",
          "status": "live",
          "home_score": 21,
          "away_score": 17,
          "home_team_data": {
            "abbreviation": "DET",
            "primary_color": "#0076B6",
            "record": "8-1"
          },
          "away_team_data": {
            "abbreviation": "NE",
            "primary_color": "#C60C30",
            "record": "3-7"
          },
          "current_odds": {
            "home_probability": 0.684,
            "away_probability": 0.316,
            "home_rendered_percent": 68,
            "away_rendered_percent": 32,
            "updated_at": "2026-11-15T16:59:45Z"
          },
          "prematch_odds": {
            "home_probability": 0.58,
            "away_probability": 0.42,
            "home_rendered_percent": 58,
            "away_rendered_percent": 42
          },
          "espn": {
            "period": "3rd",
            "game_clock": "8:14",
            "broadcast": "CBS"
          }
        }
        """)
    }

    private func scheduledDetailFixture() throws -> EventDetail {
        try decodeEventDetail("""
        {
          "id": 401201,
          "sport": "americanfootball_nfl",
          "sport_name": "NFL",
          "home_team": "Green Bay Packers",
          "away_team": "Minnesota Vikings",
          "commence_time": "2026-11-15T21:25:00Z",
          "status": "scheduled",
          "home_team_data": {
            "abbreviation": "GB",
            "primary_color": "#203731",
            "record": "7-3"
          },
          "away_team_data": {
            "abbreviation": "MIN",
            "primary_color": "#4F2683",
            "record": "8-2"
          },
          "current_odds": {
            "home_probability": 0.59,
            "away_probability": 0.41,
            "home_rendered_percent": 59,
            "away_rendered_percent": 41,
            "projected_home_score": 24.0,
            "projected_away_score": 21.0,
            "updated_at": "2026-11-15T16:59:00Z"
          },
          "hero_probability": 0.59,
          "hero_probability_away": 0.41,
          "hero_probability_source": "blend",
          "hero_probability_observed_at": "2026-11-15T16:59:00Z",
          "espn": {
            "broadcast": "FOX"
          },
          "win_probability_sources": {
            "betting": { "value": 0.59, "display_name": "Sportsbooks" },
            "kalshi": { "value": 0.59, "display_name": "Kalshi" }
          }
        }
        """)
    }

    func testCardsAndHeadlinesShareTitleCaseProjAndChanceHeadersWithNoUppercased() throws {
        let scheduled = try scheduledFeedFixture()
        let detail = try scheduledDetailFixture()

        let compactHeaders = CompactGameCard12616.columnHeaders(
            isScheduled: true,
            isLive: false,
            isFinished: false,
            isSuspended: false,
            hasProjectedBefore: true,
            hasCurrentChance: true,
            hasPrematchChance: true,
            hasScore: false
        )
        XCTAssertEqual(compactHeaders.medium, "Proj.")
        XCTAssertEqual(compactHeaders.large, "Chance")

        let discoverModel = DiscoverSingleGameCard190C.build(
            event: scheduled,
            prematch: PrematchReading.resolve(prematch: scheduled.prematchOdds, opening: scheduled.openingOdds)
        )
        XCTAssertEqual(discoverModel.headers.primary, "Chance")

        let headlineModel = try XCTUnwrap(
            EventSportHeadlines12472.resolve(
                event: detail,
                awayFullName: detail.awayTeam,
                homeFullName: detail.homeTeam,
                liveStatusText: nil,
                hasScore: false,
                numberStreams: false,
                now: fixedNow
            )
        )
        XCTAssertEqual(headlineModel.pregameColumnHeaders?.projected, "Proj.")
        XCTAssertEqual(headlineModel.pregameColumnHeaders?.chance, "Chance")

        // Guard: neither EventCardView nor DiscoverCompactSingleGameCard190C uppercases column headers.
        let componentsDir = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("Bain Luck/Components")
        let eventCardSrc = try String(contentsOf: componentsDir.appendingPathComponent("EventCardView.swift"), encoding: .utf8)
        let discoverCardSrc = try String(contentsOf: componentsDir.appendingPathComponent("DiscoverCompactSingleGameCard190C.swift"), encoding: .utf8)

        XCTAssertFalse(eventCardSrc.contains("(headers.medium ?? \"\").uppercased()"))
        XCTAssertFalse(eventCardSrc.contains("(headers.pregame ?? \"\").uppercased()"))
        XCTAssertFalse(eventCardSrc.contains("(headers.large ?? \"\").uppercased()"))
        XCTAssertFalse(discoverCardSrc.contains("scoreHeader.uppercased()"))
        XCTAssertFalse(discoverCardSrc.contains("pregameHeader.uppercased()"))
        XCTAssertFalse(discoverCardSrc.contains("primaryHeader.uppercased()"))
    }

    func testTitleCaseHeaderSheetFitsAt390AndExportsRender() throws {
        let scheduledFeed = try scheduledFeedFixture()
        let liveFeed = try liveFeedFixture()
        let scheduledDetail = try scheduledDetailFixture()

        let headlineModel = try XCTUnwrap(
            EventSportHeadlines12472.resolve(
                event: scheduledDetail,
                awayFullName: scheduledDetail.awayTeam,
                homeFullName: scheduledDetail.homeTeam,
                liveStatusText: nil,
                hasScore: false,
                numberStreams: false,
                now: fixedNow
            )
        )
        let headlineColors = TeamTextContrast.cardColors(
            awayHex: scheduledDetail.awayTeamData?.primaryColor,
            homeHex: scheduledDetail.homeTeamData?.primaryColor
        )
        let headlineCard = EventSportHeadlineCard12472(
            model: headlineModel,
            colors: headlineColors,
            ekgTracker: .empty,
            liveUpdateStatus: .awaitingUpdate,
            displayAsOf: fixedNow,
            updateStream: LiveUpdateStream(),
            showUpdateStream: .constant(false),
            showProbabilityDetails: .constant(false),
            priceStreamingEligible: false,
            lastReceivedAt: nil,
            confirmedAt: nil,
            revealForecast: nil
        )

        let scheduledColors = TeamTextContrast.cardColors(
            awayHex: scheduledFeed.awayTeamData?.primaryColor,
            homeHex: scheduledFeed.homeTeamData?.primaryColor
        )
        let liveColors = TeamTextContrast.cardColors(
            awayHex: liveFeed.awayTeamData?.primaryColor,
            homeHex: liveFeed.homeTeamData?.primaryColor
        )

        let sheet = VStack(alignment: .leading, spacing: 16) {
            VStack(alignment: .leading, spacing: 2) {
                Text("One Header Style Across Headlines & Cards (390 px)")
                    .font(.subheadline.weight(.bold))
                    .foregroundStyle(Color(hex: "#111827"))
                Text("Title Case \"Proj.\" · \"Chance\" · \"Score\" · \"Pregame\" · \"Now\"")
                    .font(.caption2)
                    .foregroundStyle(Color(hex: "#6B7280"))
            }

            VStack(alignment: .leading, spacing: 6) {
                Text("1. Game-Page Headline (Before Game: Proj. · Chance)")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(Color(hex: "#374151"))
                headlineCard
            }

            VStack(alignment: .leading, spacing: 6) {
                Text("2. Sports / Feed Game Card (Before Game: Proj. · Chance)")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(Color(hex: "#374151"))
                EventCardView(event: scheduledFeed, reason: nil)
            }

            VStack(alignment: .leading, spacing: 6) {
                Text("3. Discover Single-Game Card (Before Game: Chance)")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(Color(hex: "#374151"))
                DiscoverCompactSingleGameCard190CView(
                    event: scheduledFeed,
                    prematch: PrematchReading.resolve(prematch: scheduledFeed.prematchOdds, opening: scheduledFeed.openingOdds),
                    awayColor: scheduledColors.away,
                    homeColor: scheduledColors.home,
                    usesPictureLayout191A: false,
                    projectionAndSuspendedLines: { EmptyView() },
                    footerRow: { EmptyView() }
                )
                .padding(14)
                .background(Color.white, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
                .overlay(
                    RoundedRectangle(cornerRadius: 14, style: .continuous)
                        .strokeBorder(Color.black.opacity(0.08), lineWidth: 1)
                )
            }

            VStack(alignment: .leading, spacing: 6) {
                Text("4. Discover Single-Game Card (During Game: Score · Pregame · Now)")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(Color(hex: "#374151"))
                DiscoverCompactSingleGameCard190CView(
                    event: liveFeed,
                    prematch: PrematchReading.resolve(prematch: liveFeed.prematchOdds, opening: liveFeed.openingOdds),
                    awayColor: liveColors.away,
                    homeColor: liveColors.home,
                    usesPictureLayout191A: false,
                    projectionAndSuspendedLines: { EmptyView() },
                    footerRow: { EmptyView() }
                )
                .padding(14)
                .background(Color.white, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
                .overlay(
                    RoundedRectangle(cornerRadius: 14, style: .continuous)
                        .strokeBorder(Color.black.opacity(0.08), lineWidth: 1)
                )
            }
        }
        .padding(16)
        .frame(width: 390)
        .background(Color(hex: "#F3F4F6"))
        .environmentObject(PinManager())
        .environmentObject(NavigationCoordinator())
        .environment(\.colorScheme, .light)

        let host = hostForMeasurement(sheet, at: .large)
        host.overrideUserInterfaceStyle = .light
        let fitting = host.sizeThatFits(in: CGSize(width: 390, height: 10_000))
        host.view.frame = CGRect(x: 0, y: 0, width: 390, height: max(fitting.height, 400))
        let scene = UIApplication.shared.connectedScenes.compactMap({ $0 as? UIWindowScene }).first
        let window: UIWindow = scene.map { UIWindow(windowScene: $0) } ?? UIWindow(frame: host.view.frame)
        window.frame = host.view.frame
        window.overrideUserInterfaceStyle = .light
        window.rootViewController = host
        window.isHidden = false
        defer {
            window.isHidden = true
            window.rootViewController = nil
        }
        let until = Date().addingTimeInterval(0.2)
        repeat {
            let nextH = max(host.sizeThatFits(in: CGSize(width: 390, height: 10_000)).height, 400)
            if abs(host.view.frame.height - nextH) > 0.5 {
                host.view.frame = CGRect(x: 0, y: 0, width: 390, height: nextH)
                window.frame = host.view.frame
            }
            host.view.setNeedsLayout()
            host.view.layoutIfNeeded()
            RunLoop.current.run(until: Date().addingTimeInterval(0.02))
        } while Date() < until

        let fmt = UIGraphicsImageRendererFormat()
        fmt.scale = 3.0
        let image = UIGraphicsImageRenderer(bounds: host.view.bounds, format: fmt).image { _ in
            _ = host.view.drawHierarchy(in: host.view.bounds, afterScreenUpdates: true)
        }
        XCTAssertEqual(Int(image.size.width.rounded()), 390)
        XCTAssertGreaterThan(image.size.height, 400)

        if let exportDir = ProcessInfo.processInfo.environment["SAT4_HEADERS_EXPORT_DIR"],
           !exportDir.isEmpty {
            let dirURL = URL(fileURLWithPath: exportDir, isDirectory: true)
            try FileManager.default.createDirectory(at: dirURL, withIntermediateDirectories: true)
            let data = try XCTUnwrap(image.pngData())
            try data.write(to: dirURL.appendingPathComponent("sat4-header-style-390.png"))
        }
    }
}
