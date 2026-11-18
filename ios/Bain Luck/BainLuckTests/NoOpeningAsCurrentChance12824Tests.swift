import SwiftUI
import UIKit
import XCTest
@testable import Bain_Luck

@MainActor
final class NoOpeningAsCurrentChance12824Tests: XCTestCase {

    private let fixedNow = ISO8601DateFormatter().date(from: "2026-11-18T02:30:00Z")!

    private func decodeEventDetail(_ json: String) throws -> EventDetail {
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        return try d.decode(EventDetail.self, from: Data(json.utf8))
    }

    private func decodeFeedEvent(_ json: String) throws -> FeedEventData {
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        return try d.decode(FeedEventData.self, from: Data(json.utf8))
    }

    private func decodeFeedItem(_ json: String) throws -> FeedItem {
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        return try d.decode(FeedItem.self, from: Data(json.utf8))
    }

    // MARK: - 1. EventSportHeadlines12472 (2-Row & 3-Way Soccer Before + During)

    private func makeSoccerEvent(status: String, source: String) throws -> EventDetail {
        try decodeEventDetail("""
        {
          "id": 15349001,
          "sport": "soccer_epl",
          "sport_name": "Premier League",
          "home_team": "Arsenal",
          "away_team": "Chelsea",
          "home_team_data": {"primary_color": "#EF0107", "abbreviation": "ARS", "record": "7-2-2"},
          "away_team_data": {"primary_color": "#034694", "abbreviation": "CHE", "record": "6-3-2"},
          "commence_time": "2026-11-18T01:45:00Z",
          "status": "\(status)",
          "home_score": \(status == "live" ? "1" : "null"),
          "away_score": \(status == "live" ? "1" : "null"),
          "hero_probability_source": "\(source)",
          "hero_probability": 0.44,
          "hero_probability_away": 0.28,
          "hero_probability_observed_at": \(source == "opening" ? "null" : "\"2026-11-18T02:28:00Z\""),
          "current_odds": {
            "home_probability": 0.44,
            "draw_probability": 0.28,
            "away_probability": 0.28,
            "home_rendered_percent": 44,
            "away_rendered_percent": 28,
            "live_projection": {
              "projected_home_score": 1.8,
              "projected_away_score": 1.6,
              "kind": "in_play",
              "captured_at": "2026-11-18T02:27:00Z",
              "scheduled_start": "2026-11-18T01:45:00Z",
              "source": "sportsbooks",
              "basis": "consensus_spread_total",
              "bookmaker_count": 3,
              "unit": "goals",
              "period": "regulation"
            }
          },
          "opening_odds": {
            "home_probability": 0.44,
            "away_probability": 0.28
          },
          "prematch_odds": {
            "home_probability": 0.48,
            "draw_probability": 0.27,
            "away_probability": 0.25,
            "home_rendered_percent": 48,
            "away_rendered_percent": 25,
            "source": "books"
          },
          "source_mark": {
            "headline": 0.44,
            "contributors": [{"key": "sportsbooks", "label": "Sportsbooks", "probability": 0.44, "weight": 1.0}]
          }
        }
        """)
    }

    private func makeLiveNFLEvent(source: String) throws -> EventDetail {
        try decodeEventDetail("""
        {
          "id": 15349002,
          "sport": "americanfootball_nfl",
          "sport_name": "NFL",
          "home_team": "Detroit Lions",
          "away_team": "New England Patriots",
          "home_team_data": {"primary_color": "#0076B6", "abbreviation": "DET"},
          "away_team_data": {"primary_color": "#002244", "secondary_color": "#C60C30", "abbreviation": "NE"},
          "commence_time": "2026-11-18T01:00:00Z",
          "status": "live",
          "home_score": 21,
          "away_score": 17,
          "hero_probability_source": "\(source)",
          "hero_probability": 0.58,
          "hero_probability_away": 0.42,
          "hero_probability_observed_at": \(source == "opening" ? "null" : "\"2026-11-18T02:28:00Z\""),
          "current_odds": {
            "home_probability": 0.58,
            "away_probability": 0.42,
            "home_rendered_percent": 58,
            "away_rendered_percent": 42
          },
          "opening_odds": {
            "home_probability": 0.58,
            "away_probability": 0.42
          },
          "prematch_odds": {
            "home_probability": 0.58,
            "away_probability": 0.42,
            "home_rendered_percent": 58,
            "away_rendered_percent": 42,
            "source": "books"
          },
          "source_mark": {
            "headline": 0.58,
            "contributors": [{"key": "sportsbooks", "label": "Sportsbooks", "probability": 0.58, "weight": 1.0}]
          }
        }
        """)
    }

    func testThreeWaySoccerAndTwoRowHeadlinesWithholdOpeningAsCurrentInBeforeAndDuring() throws {
        // 1. 3-way soccer BEFORE kickoff: opening withheld vs blend shown
        let pregameOpening = try makeSoccerEvent(status: "scheduled", source: "opening")
        let pregameBlend = try makeSoccerEvent(status: "scheduled", source: "blend")

        let preOpenModel = try XCTUnwrap(
            EventSportHeadlines12472.resolve(
                event: pregameOpening,
                awayFullName: pregameOpening.awayTeam,
                homeFullName: pregameOpening.homeTeam,
                liveStatusText: nil,
                hasScore: false,
                numberStreams: false,
                now: fixedNow.addingTimeInterval(-7200)
            )
        )
        XCTAssertEqual(preOpenModel.away.winChanceText, "")
        XCTAssertEqual(preOpenModel.home.winChanceText, "")
        XCTAssertNil(preOpenModel.bottomBar)
        XCTAssertNil(preOpenModel.sourceMark)

        let preBlendModel = try XCTUnwrap(
            EventSportHeadlines12472.resolve(
                event: pregameBlend,
                awayFullName: pregameBlend.awayTeam,
                homeFullName: pregameBlend.homeTeam,
                liveStatusText: nil,
                hasScore: false,
                numberStreams: false,
                now: fixedNow.addingTimeInterval(-7200)
            )
        )
        XCTAssertEqual(preBlendModel.home.winChanceText, "44%")
        XCTAssertEqual(preBlendModel.away.winChanceText, "28%")
        XCTAssertNotNil(preBlendModel.bottomBar)
        XCTAssertNotNil(preBlendModel.sourceMark)

        // 2. 3-way soccer DURING match: opening withheld (scores + Pregame line kept) vs blend shown
        let liveOpening = try makeSoccerEvent(status: "live", source: "opening")
        let liveBlend = try makeSoccerEvent(status: "live", source: "blend")

        let liveOpenModel = try XCTUnwrap(
            EventSportHeadlines12472.resolve(
                event: liveOpening,
                awayFullName: liveOpening.awayTeam,
                homeFullName: liveOpening.homeTeam,
                liveStatusText: "67'",
                hasScore: true,
                numberStreams: true,
                now: fixedNow
            )
        )
        XCTAssertEqual(liveOpenModel.away.liveScore, 1)
        XCTAssertEqual(liveOpenModel.home.liveScore, 1)
        XCTAssertEqual(liveOpenModel.away.winChanceText, "")
        XCTAssertEqual(liveOpenModel.home.winChanceText, "")
        XCTAssertNil(liveOpenModel.bottomBar)
        XCTAssertNil(liveOpenModel.sourceMark)
        XCTAssertNotNil(liveOpenModel.livePregameSummary)

        let liveBlendModel = try XCTUnwrap(
            EventSportHeadlines12472.resolve(
                event: liveBlend,
                awayFullName: liveBlend.awayTeam,
                homeFullName: liveBlend.homeTeam,
                liveStatusText: "67'",
                hasScore: true,
                numberStreams: true,
                now: fixedNow
            )
        )
        XCTAssertEqual(liveBlendModel.home.winChanceText, "44.0%")
        XCTAssertEqual(liveBlendModel.away.winChanceText, "28.0%")
        XCTAssertNotNil(liveBlendModel.bottomBar)
        XCTAssertNotNil(liveBlendModel.sourceMark)

        // 3. Direct `EventSportHeadlines12472.resolve` on 2-row live NFL with `opening`
        let nflOpen = try makeLiveNFLEvent(source: "opening")
        let nflOpenModel = try XCTUnwrap(
            EventSportHeadlines12472.resolve(
                event: nflOpen,
                awayFullName: nflOpen.awayTeam,
                homeFullName: nflOpen.homeTeam,
                liveStatusText: "Q3 · 8:14",
                hasScore: true,
                numberStreams: true,
                now: fixedNow
            )
        )
        XCTAssertEqual(nflOpenModel.away.liveScore, 17)
        XCTAssertEqual(nflOpenModel.home.liveScore, 21)
        XCTAssertEqual(nflOpenModel.away.winChanceText, "")
        XCTAssertEqual(nflOpenModel.home.winChanceText, "")
        XCTAssertNil(nflOpenModel.bottomBar)
        XCTAssertNil(nflOpenModel.sourceMark)
        XCTAssertEqual(nflOpenModel.livePregameSummary?.fullText, "Pregame  Lions 58%")
    }

    // MARK: - 2. Atlas Sheet, Overlaid Reading & Live Chart Edge

    func testAtlasSheetOverlaidReadingAndChartEdgeWithholdOpeningAsCurrent() throws {
        let liveOpening = try makeLiveNFLEvent(source: "opening")
        let liveBlend = try makeLiveNFLEvent(source: "blend")

        let openSheet = EventAtlasDetailsSheetModel11666.fromHeadline(
            event: liveOpening,
            phase: nil,
            observedAt: nil,
            liveStatus: .awaitingUpdate,
            now: fixedNow
        )
        XCTAssertEqual(openSheet.primaryReadingValue, "No recent probability")

        let blendSheet = EventAtlasDetailsSheetModel11666.fromHeadline(
            event: liveBlend,
            phase: .current,
            observedAt: fixedNow,
            liveStatus: .live,
            now: fixedNow
        )
        XCTAssertTrue(blendSheet.primaryReadingValue.contains("58.0%"))

        XCTAssertNil(
            EventAtlasLivePath11666.overlaidHeadlineReading(
                event: liveOpening,
                preview: nil,
                now: fixedNow.timeIntervalSince1970
            )
        )
        XCTAssertNotNil(
            EventAtlasLivePath11666.overlaidHeadlineReading(
                event: liveBlend,
                preview: nil,
                now: fixedNow.timeIntervalSince1970
            )
        )

        XCTAssertNil(LiveEdgeReading.current(in: liveOpening))
        XCTAssertNotNil(LiveEdgeReading.current(in: liveBlend))
    }

    // MARK: - 3. DiscoverSingleGameCard190C, RelatedByTagView, DailyChallenge & Siri

    func testDiscoverModelRelatedRowDailyChallengeAndSiriWithholdOpeningAsCurrent() throws {
        let openItem = try decodeFeedItem("""
        {
          "type": "event",
          "headline": "Rivalry matchup",
          "data": {
            "id": 15349003,
            "sport": "basketball_nba",
            "sport_name": "NBA",
            "home_team": "Boston Celtics",
            "away_team": "Toronto Raptors",
            "commence_time": "2026-11-18T01:00:00Z",
            "status": "live",
            "home_score": 68,
            "away_score": 72,
            "hero_probability_source": "opening",
            "current_odds": {
              "home_probability": 0.64,
              "away_probability": 0.36,
              "home_rendered_percent": 64,
              "away_rendered_percent": 36
            },
            "opening_odds": {
              "home_probability": 0.64,
              "away_probability": 0.36
            }
          }
        }
        """)
        let blendItem = try decodeFeedItem("""
        {
          "type": "event",
          "headline": "Rivalry matchup",
          "data": {
            "id": 15349004,
            "sport": "basketball_nba",
            "sport_name": "NBA",
            "home_team": "Boston Celtics",
            "away_team": "Toronto Raptors",
            "commence_time": "2026-11-18T01:00:00Z",
            "status": "live",
            "home_score": 68,
            "away_score": 72,
            "hero_probability_source": "blend",
            "current_odds": {
              "home_probability": 0.64,
              "away_probability": 0.36,
              "home_rendered_percent": 64,
              "away_rendered_percent": 36
            },
            "opening_odds": {
              "home_probability": 0.64,
              "away_probability": 0.36
            }
          }
        }
        """)

        let openFeedEvent = try XCTUnwrap(openItem.event)
        let blendFeedEvent = try XCTUnwrap(blendItem.event)
        let prematch = PrematchReading.resolve(prematch: openFeedEvent.prematchOdds, opening: openFeedEvent.openingOdds)

        // Direct DiscoverSingleGameCard190C.build & swingPoints
        XCTAssertNil(DiscoverSingleGameCard190C.swingPoints(event: openFeedEvent, prematch: prematch))
        let openDiscoverModel = DiscoverSingleGameCard190C.build(event: openFeedEvent, prematch: prematch)
        XCTAssertNil(openDiscoverModel.headers.primary)
        XCTAssertEqual(openDiscoverModel.rows.map { $0.primaryCell }, [.none, .none])
        XCTAssertEqual(openDiscoverModel.rows.map { $0.scoreText }, ["72", "68"])

        let blendDiscoverModel = DiscoverSingleGameCard190C.build(event: blendFeedEvent, prematch: prematch)
        XCTAssertEqual(blendDiscoverModel.headers.primary, "Now")
        XCTAssertEqual(blendDiscoverModel.rows.map { $0.primaryCell }, [.probability("36.0%"), .probability("64.0%")])

        // RelatedByTagView
        XCTAssertFalse(RelatedByTagView.admitsTrailingProbability(openFeedEvent))
        XCTAssertTrue(RelatedByTagView.admitsTrailingProbability(blendFeedEvent))

        // DailyChallengeViewModel
        XCTAssertNil(DailyChallengeViewModel.question(from: openItem, now: fixedNow))
        XCTAssertNotNil(DailyChallengeViewModel.question(from: blendItem, now: fixedNow))

        // ProbabilityAnswer10873 (Siri live opening-only -> unavailable; blend -> current)
        let liveOpenNFL = try makeLiveNFLEvent(source: "opening")
        let liveBlendNFL = try makeLiveNFLEvent(source: "blend")
        XCTAssertEqual(ProbabilityAnswer10873.game(liveOpenNFL, side: .home, now: fixedNow).kind, .unavailable)
        XCTAssertEqual(ProbabilityAnswer10873.gameBothSides(liveOpenNFL, now: fixedNow).kind, .unavailable)
        XCTAssertEqual(ProbabilityAnswer10873.game(liveBlendNFL, side: .home, now: fixedNow).kind, .current)
    }

    // MARK: - 4. Optional 390px Light & Dark Render Export

    func testExport12824AppViewsRenderSheetAt390px() async throws {
        guard let outDir = ProcessInfo.processInfo.environment["EXPORT_12824_APP_RENDERS_DIR"],
              !outDir.isEmpty else {
            return
        }
        let dirURL = URL(fileURLWithPath: outDir, isDirectory: true)
        try FileManager.default.createDirectory(at: dirURL, withIntermediateDirectories: true)

        let liveSoccerOpen = try makeSoccerEvent(status: "live", source: "opening")
        let liveSoccerBlend = try makeSoccerEvent(status: "live", source: "blend")
        let preSoccerOpen = try makeSoccerEvent(status: "scheduled", source: "opening")
        let preSoccerBlend = try makeSoccerEvent(status: "scheduled", source: "blend")

        func makeHeadlineCard(_ event: EventDetail, liveStatus: String?, now: Date) throws -> some View {
            let model = try XCTUnwrap(
                EventSportHeadlines12472.resolve(
                    event: event,
                    awayFullName: event.awayTeam,
                    homeFullName: event.homeTeam,
                    liveStatusText: liveStatus,
                    hasScore: event.status == "live",
                    numberStreams: event.status == "live",
                    now: now
                )
            )
            let colors = TeamTextContrast.cardColors(
                awayHex: event.awayTeamData?.primaryColor,
                homeHex: event.homeTeamData?.primaryColor,
                awaySecondaryHex: event.awayTeamData?.secondaryColor,
                checkHueFamily: true
            )
            return EventSportHeadlineCard12472(
                model: model,
                colors: colors,
                ekgTracker: .empty,
                liveUpdateStatus: .awaitingUpdate,
                displayAsOf: now,
                updateStream: LiveUpdateStream(),
                showUpdateStream: .constant(false),
                showProbabilityDetails: .constant(false),
                priceStreamingEligible: false,
                lastReceivedAt: now,
                confirmedAt: now,
                revealForecast: nil
            )
        }

        let relatedOpenItem = try decodeFeedItem("""
        {"type":"event","headline":null,"data":{"id":901,"sport":"basketball_nba","home_team":"Boston Celtics","away_team":"Toronto Raptors","status":"live","home_score":68,"away_score":72,"hero_probability_source":"opening","current_odds":{"home_probability":0.64,"away_probability":0.36,"home_rendered_percent":64,"away_rendered_percent":36}}}
        """)
        let relatedBlendItem = try decodeFeedItem("""
        {"type":"event","headline":null,"data":{"id":902,"sport":"basketball_nba","home_team":"New York Knicks","away_team":"Miami Heat","status":"live","home_score":81,"away_score":77,"hero_probability_source":"blend","current_odds":{"home_probability":0.64,"away_probability":0.36,"home_rendered_percent":64,"away_rendered_percent":36}}}
        """)

        let cardLiveOpen = try makeHeadlineCard(liveSoccerOpen, liveStatus: "67'", now: fixedNow)
        let cardLiveBlend = try makeHeadlineCard(liveSoccerBlend, liveStatus: "67'", now: fixedNow)
        let cardPreOpen = try makeHeadlineCard(preSoccerOpen, liveStatus: nil, now: fixedNow.addingTimeInterval(-7200))
        let cardPreBlend = try makeHeadlineCard(preSoccerBlend, liveStatus: nil, now: fixedNow.addingTimeInterval(-7200))

        let content = VStack(alignment: .leading, spacing: 14) {
            VStack(alignment: .leading, spacing: 5) {
                Text("1 · Live 3-Way Soccer Headline — Stored Opening Withheld (1–1 Score + Pregame Kept)")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.secondary)
                cardLiveOpen
            }
            VStack(alignment: .leading, spacing: 5) {
                Text("2 · Live 3-Way Soccer Headline — Observed Blend Control (Now 44.0% / 28.0% / 28.0%)")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.secondary)
                cardLiveBlend
            }
            VStack(alignment: .leading, spacing: 5) {
                Text("3 · Pregame 3-Way Soccer — Opening Withheld vs Blend")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.secondary)
                cardPreOpen
                cardPreBlend
            }
            VStack(alignment: .leading, spacing: 5) {
                Text("4 · Related Matchups — Opening Withheld (72 - 68 Only) vs Blend (36% / 64%)")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.secondary)
                NavigationStack {
                    RelatedByTagView(
                        preloadedItems: [relatedOpenItem, relatedBlendItem],
                        title: "More Like This"
                    )
                }
                .frame(height: 156)
            }
        }
        .padding(16)
        .frame(width: 390, alignment: .leading)

        for (scheme, suffix, style) in [(ColorScheme.light, "light", UIUserInterfaceStyle.light), (.dark, "dark", .dark)] {
            let bg = style == .dark ? UIColor.black : UIColor.systemGroupedBackground
            let wrapped = content
                .background(Color(uiColor: bg))
                .environment(\.colorScheme, scheme)
            let measureHost = hostForMeasurement(wrapped, at: .large)
            measureHost.overrideUserInterfaceStyle = style
            let fittedH = ceil(measureHost.sizeThatFits(in: CGSize(width: 390, height: 4000)).height)
            let size = CGSize(width: 390, height: max(fittedH, 400))

            let host = hostForMeasurement(wrapped, at: .large)
            host.overrideUserInterfaceStyle = style
            host.view.frame = CGRect(origin: .zero, size: size)
            let window: UIWindow
            if let scene = UIApplication.shared.connectedScenes.compactMap({ $0 as? UIWindowScene }).first {
                window = UIWindow(windowScene: scene)
            } else {
                window = UIWindow(frame: host.view.frame)
            }
            window.frame = host.view.frame
            window.overrideUserInterfaceStyle = style
            window.rootViewController = host
            window.isHidden = false
            defer {
                window.isHidden = true
                window.rootViewController = nil
            }
            host.view.setNeedsLayout()
            host.view.layoutIfNeeded()
            try await Task.sleep(nanoseconds: 250_000_000)
            host.view.layoutIfNeeded()

            let fmt = UIGraphicsImageRendererFormat()
            fmt.scale = 2.0
            let img = UIGraphicsImageRenderer(bounds: host.view.bounds, format: fmt).image { _ in
                _ = host.view.drawHierarchy(in: host.view.bounds, afterScreenUpdates: true)
            }
            try XCTUnwrap(img.pngData()).write(
                to: dirURL.appendingPathComponent("12824-app-views-\(suffix)-390.png")
            )
        }
    }
}
