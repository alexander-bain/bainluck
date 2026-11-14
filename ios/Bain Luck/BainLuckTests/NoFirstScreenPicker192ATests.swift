import SwiftUI
import UIKit
import XCTest
@testable import Bain_Luck

/// Ruling 192-A (Overnight Item 3):
/// Golf, futures, and props pages have NO contender picker on the first screen:
/// - The chart shows the exact contenders the headline names (top 4).
/// - `"All N … ›"` opens the full field sheet.
/// - Time range moves into the full-screen chart (`"Full chart ↗"`).
/// - The `Sum / Top N` control is retired.
/// - First-screen charts are taller (`228 pt` on Golf up from `180 pt`; `296 pt` on Evolution up from `280 pt`).
@MainActor
final class NoFirstScreenPicker192ATests: XCTestCase {

    private let fixedNow = ISO8601DateFormatter().date(from: "2026-11-13T18:00:00Z")!

    private func makeDecoder() -> JSONDecoder {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return decoder
    }

    // MARK: - Fixtures

    private func makeGolfPresentation(fieldSize: Int = 120) throws -> (
        presentation: GolfTournamentPresentation,
        atlasData: EventAtlasGolfTournament11666.TournamentAtlasData
    ) {
        let topFour: [[String: Any]] = [
            ["name": "Scottie Scheffler", "probability": 0.29, "opening_probability": 0.21, "movement_24h": 0.045, "rank": 1],
            ["name": "Rory McIlroy", "probability": 0.21, "opening_probability": 0.16, "movement_24h": 0.030, "rank": 2],
            ["name": "Ludvig Åberg", "probability": 0.15, "opening_probability": 0.12, "movement_24h": 0.018, "rank": 3],
            ["name": "Collin Morikawa", "probability": 0.09, "opening_probability": 0.11, "movement_24h": -0.015, "rank": 4],
        ]
        var golfers = topFour
        for idx in 5...max(4, fieldSize) {
            golfers.append([
                "name": "Golfer \(idx) Player",
                "probability": max(0.002, 0.06 / Double(idx)),
                "opening_probability": 0.01,
                "movement_24h": 0.0,
                "rank": idx,
            ])
        }

        let dict: [String: Any] = [
            "tournament": [
                "name": "The Masters",
                "slug": "the-masters",
                "key": "the_masters",
                "is_major": true,
                "start_date": "2026-11-12",
                "end_date": "2026-11-15",
                "venue": "Augusta National",
                "location": "Augusta, GA",
                "schedule_status": "in_progress",
                "commence_time": "2026-11-12T12:00:00Z",
            ],
            "golfers": golfers,
            "evolution_market_id": 9001,
            "markets": [
                ["type": "winner", "label": "Tournament Winner", "market_ids": [9001], "market_names": ["The Masters Winner"]],
            ],
            "round_top_groups": [],
        ]
        let data = try JSONSerialization.data(withJSONObject: dict)
        let response = try makeDecoder().decode(GolfTournamentDetailResponse.self, from: data)
        let presentation = GolfTournamentPresentation(response: response)

        let marketDict: [String: Any] = [
            "id": 9001,
            "name": "The Masters Winner",
            "status": "open",
            "source": "datagolf",
            "commence_time": "2026-11-12T12:00:00Z",
            "updated_at": "2026-11-13T17:55:00Z",
            "outcomes": [
                ["id": 1, "name": "Scottie Scheffler", "probability": 0.29, "opening_probability": 0.21, "observed_at": "2026-11-13T17:55:00Z"],
                ["id": 2, "name": "Rory McIlroy", "probability": 0.21, "opening_probability": 0.16, "observed_at": "2026-11-13T17:55:00Z"],
                ["id": 3, "name": "Ludvig Åberg", "probability": 0.15, "opening_probability": 0.12, "observed_at": "2026-11-13T17:55:00Z"],
                ["id": 4, "name": "Collin Morikawa", "probability": 0.09, "opening_probability": 0.11, "observed_at": "2026-11-13T17:55:00Z"],
            ],
        ]
        let winMarket = try makeDecoder().decode(
            FuturesMarketDetail.self,
            from: try JSONSerialization.data(withJSONObject: marketDict)
        )

        let timelineDict: [String: Any] = [
            "market_id": 9001,
            "market_name": "The Masters Winner",
            "sport_category": "golf",
            "source": "datagolf",
            "hours": 168,
            "top": 50,
            "bucket_seconds": 3600,
            "representation": "source",
            "timeline": [
                ["timestamp": "2026-11-12T12:00:00Z", "outcomes": ["Scottie Scheffler": 0.21, "Rory McIlroy": 0.16, "Ludvig Åberg": 0.12, "Collin Morikawa": 0.11]],
                ["timestamp": "2026-11-12T20:00:00Z", "outcomes": ["Scottie Scheffler": 0.24, "Rory McIlroy": 0.18, "Ludvig Åberg": 0.11, "Collin Morikawa": 0.10]],
                ["timestamp": "2026-11-13T08:00:00Z", "outcomes": ["Scottie Scheffler": 0.26, "Rory McIlroy": 0.19, "Ludvig Åberg": 0.14, "Collin Morikawa": 0.095]],
                ["timestamp": "2026-11-13T14:00:00Z", "outcomes": ["Scottie Scheffler": 0.275, "Rory McIlroy": 0.205, "Ludvig Åberg": 0.145, "Collin Morikawa": 0.09]],
                ["timestamp": "2026-11-13T17:55:00Z", "outcomes": ["Scottie Scheffler": 0.29, "Rory McIlroy": 0.21, "Ludvig Åberg": 0.15, "Collin Morikawa": 0.09]],
            ],
            "outcomes": [
                ["id": 1, "name": "Scottie Scheffler", "current_probability": 0.29, "rank": 1, "opening_probability": 0.21],
                ["id": 2, "name": "Rory McIlroy", "current_probability": 0.21, "rank": 2, "opening_probability": 0.16],
                ["id": 3, "name": "Ludvig Åberg", "current_probability": 0.15, "rank": 3, "opening_probability": 0.12],
                ["id": 4, "name": "Collin Morikawa", "current_probability": 0.09, "rank": 4, "opening_probability": 0.11],
            ],
            "coverage_hours": 30.0,
            "observation_times": 5,
        ]
        let timeline = try makeDecoder().decode(
            ProbabilityTimelineResponse.self,
            from: try JSONSerialization.data(withJSONObject: timelineDict)
        )

        let closingRound = EventAtlasGolfTournament11666.ClosingRoundCard(
            tournamentName: "The Masters",
            rows: [
                .init(id: "1", golferName: "Scottie Scheffler", strokesToPar: -11, preTournamentWinChance: 0.21, finishLabel: "1", verdict: nil),
                .init(id: "2", golferName: "Rory McIlroy", strokesToPar: -9, preTournamentWinChance: 0.16, finishLabel: "2", verdict: nil),
                .init(id: "3", golferName: "Ludvig Åberg", strokesToPar: -8, preTournamentWinChance: 0.12, finishLabel: "T3", verdict: nil),
                .init(id: "4", golferName: "Collin Morikawa", strokesToPar: -7, preTournamentWinChance: 0.11, finishLabel: "T4", verdict: nil),
            ]
        )

        let atlas = EventAtlasGolfTournament11666.TournamentAtlasData(
            winnerMarket: winMarket,
            winnerTimeline: timeline,
            closingRound: closingRound
        )
        return (presentation, atlas)
    }

    private func makeChampionshipFutureFixture(teamCount: Int = 28) throws -> (
        market: FuturesMarketDetail,
        timeline: ProbabilityTimelineResponse
    ) {
        var outcomes: [[String: Any]] = [
            [
                "id": 101,
                "name": "Boston Celtics",
                "probability": 0.26,
                "opening_probability": 0.22,
                "probability_change_24h": 0.021,
                "primary_color": "#007A33",
                "observed_at": "2026-11-13T17:55:00Z",
                "last_updated": "2026-11-13T17:55:00Z",
            ],
            [
                "id": 102,
                "name": "Oklahoma City Thunder",
                "probability": 0.22,
                "opening_probability": 0.19,
                "probability_change_24h": 0.015,
                "primary_color": "#007AC1",
                "observed_at": "2026-11-13T17:55:00Z",
                "last_updated": "2026-11-13T17:55:00Z",
            ],
            [
                "id": 103,
                "name": "Cleveland Cavaliers",
                "probability": 0.14,
                "opening_probability": 0.09,
                "probability_change_24h": 0.032,
                "primary_color": "#860038",
                "observed_at": "2026-11-13T17:55:00Z",
                "last_updated": "2026-11-13T17:55:00Z",
            ],
            [
                "id": 104,
                "name": "Denver Nuggets",
                "probability": 0.10,
                "opening_probability": 0.12,
                "probability_change_24h": -0.011,
                "primary_color": "#0E2240",
                "observed_at": "2026-11-13T17:55:00Z",
                "last_updated": "2026-11-13T17:55:00Z",
            ],
        ]
        for idx in 5...max(4, teamCount) {
            outcomes.append([
                "id": 100 + idx,
                "name": "NBA Team \(idx)",
                "probability": max(0.005, 0.28 / Double(teamCount)),
                "observed_at": "2026-11-13T17:55:00Z",
                "last_updated": "2026-11-13T17:55:00Z",
            ])
        }

        let marketDict: [String: Any] = [
            "id": 181,
            "name": "2026-27 NBA Champion",
            "category": "basketball",
            "llm_sport_category": "basketball",
            "status": "open",
            "source": "blend",
            "mutually_exclusive": true,
            "bookmakers": ["kalshi", "polymarket", "draftkings"],
            "representation": "source",
            "outcomes": outcomes,
        ]
        let market = try makeDecoder().decode(
            FuturesMarketDetail.self,
            from: try JSONSerialization.data(withJSONObject: marketDict)
        )

        let timelineDict: [String: Any] = [
            "market_id": 181,
            "market_name": "2026-27 NBA Champion",
            "sport_category": "basketball",
            "source": "blend",
            "hours": 168,
            "top": 50,
            "bucket_seconds": 3600,
            "representation": "source",
            "timeline": [
                ["timestamp": "2026-11-07T18:00:00Z", "outcomes": ["Boston Celtics": 0.23, "Oklahoma City Thunder": 0.20, "Cleveland Cavaliers": 0.10, "Denver Nuggets": 0.12, "NBA Team 5": 0.06]],
                ["timestamp": "2026-11-09T18:00:00Z", "outcomes": ["Boston Celtics": 0.24, "Oklahoma City Thunder": 0.21, "Cleveland Cavaliers": 0.12, "Denver Nuggets": 0.11, "NBA Team 5": 0.05]],
                ["timestamp": "2026-11-11T18:00:00Z", "outcomes": ["Boston Celtics": 0.25, "Oklahoma City Thunder": 0.215, "Cleveland Cavaliers": 0.13, "Denver Nuggets": 0.105, "NBA Team 5": 0.05]],
                ["timestamp": "2026-11-13T17:55:00Z", "outcomes": ["Boston Celtics": 0.26, "Oklahoma City Thunder": 0.22, "Cleveland Cavaliers": 0.14, "Denver Nuggets": 0.10, "NBA Team 5": 0.05]],
            ],
            "outcomes": [
                ["id": 101, "name": "Boston Celtics", "current_probability": 0.26, "rank": 1, "primary_color": "#007A33"],
                ["id": 102, "name": "Oklahoma City Thunder", "current_probability": 0.22, "rank": 2, "primary_color": "#007AC1"],
                ["id": 103, "name": "Cleveland Cavaliers", "current_probability": 0.14, "rank": 3, "primary_color": "#860038"],
                ["id": 104, "name": "Denver Nuggets", "current_probability": 0.10, "rank": 4, "primary_color": "#0E2240"],
                ["id": 105, "name": "NBA Team 5", "current_probability": 0.05, "rank": 5],
            ],
            "coverage_hours": 144.0,
            "observation_times": 4,
        ]
        let timeline = try makeDecoder().decode(
            ProbabilityTimelineResponse.self,
            from: try JSONSerialization.data(withJSONObject: timelineDict)
        )
        return (market, timeline)
    }

    private func makePropsFixture(propCount: Int = 53) throws -> (
        market: FuturesMarketDetail,
        timeline: ProbabilityTimelineResponse
    ) {
        var outcomes: [[String: Any]] = [
            [
                "id": 501,
                "name": "Ja'Marr Chase · CIN",
                "probability": 0.52,
                "opening_probability": 0.47,
                "probability_change_24h": 0.05,
                "primary_color": "#FB4F14",
                "observed_at": "2026-11-13T17:55:00Z",
                "last_updated": "2026-11-13T17:55:00Z",
            ],
            [
                "id": 502,
                "name": "Najee Harris · PIT",
                "probability": 0.44,
                "opening_probability": 0.42,
                "probability_change_24h": 0.02,
                "primary_color": "#101820",
                "observed_at": "2026-11-13T17:55:00Z",
                "last_updated": "2026-11-13T17:55:00Z",
            ],
            [
                "id": 503,
                "name": "Tee Higgins · CIN",
                "probability": 0.36,
                "opening_probability": 0.38,
                "probability_change_24h": -0.02,
                "primary_color": "#B45309",
                "observed_at": "2026-11-13T17:55:00Z",
                "last_updated": "2026-11-13T17:55:00Z",
            ],
            [
                "id": 504,
                "name": "George Pickens · PIT",
                "probability": 0.31,
                "opening_probability": 0.29,
                "probability_change_24h": 0.02,
                "primary_color": "#1D4ED8",
                "observed_at": "2026-11-13T17:55:00Z",
                "last_updated": "2026-11-13T17:55:00Z",
            ],
        ]
        for idx in 5...max(4, propCount) {
            outcomes.append([
                "id": 500 + idx,
                "name": "Player \(idx) Anytime TD",
                "probability": max(0.04, 0.30 - Double(idx) * 0.004),
                "observed_at": "2026-11-13T17:55:00Z",
                "last_updated": "2026-11-13T17:55:00Z",
            ])
        }

        let marketDict: [String: Any] = [
            "id": 69954932,
            "event_id": 9124721,
            "name": "Anytime Touchdown Scorers",
            "category": "football",
            "llm_sport_category": "football",
            "status": "open",
            "source": "blend",
            "mutually_exclusive": false,
            "bookmakers": ["kalshi", "draftkings", "fanduel"],
            "representation": "source",
            "outcomes": outcomes,
        ]
        let market = try makeDecoder().decode(
            FuturesMarketDetail.self,
            from: try JSONSerialization.data(withJSONObject: marketDict)
        )

        let timelineDict: [String: Any] = [
            "market_id": 69954932,
            "market_name": "Anytime Touchdown Scorers",
            "sport_category": "football",
            "source": "blend",
            "hours": 168,
            "top": 50,
            "bucket_seconds": 3600,
            "representation": "source",
            "timeline": [
                ["timestamp": "2026-11-10T18:00:00Z", "outcomes": ["Ja'Marr Chase · CIN": 0.47, "Najee Harris · PIT": 0.42, "Tee Higgins · CIN": 0.38, "George Pickens · PIT": 0.29]],
                ["timestamp": "2026-11-11T18:00:00Z", "outcomes": ["Ja'Marr Chase · CIN": 0.49, "Najee Harris · PIT": 0.43, "Tee Higgins · CIN": 0.37, "George Pickens · PIT": 0.30]],
                ["timestamp": "2026-11-12T18:00:00Z", "outcomes": ["Ja'Marr Chase · CIN": 0.50, "Najee Harris · PIT": 0.435, "Tee Higgins · CIN": 0.365, "George Pickens · PIT": 0.305]],
                ["timestamp": "2026-11-13T17:55:00Z", "outcomes": ["Ja'Marr Chase · CIN": 0.52, "Najee Harris · PIT": 0.44, "Tee Higgins · CIN": 0.36, "George Pickens · PIT": 0.31]],
            ],
            "outcomes": [
                ["id": 501, "name": "Ja'Marr Chase · CIN", "current_probability": 0.52, "rank": 1, "primary_color": "#FB4F14"],
                ["id": 502, "name": "Najee Harris · PIT", "current_probability": 0.44, "rank": 2, "primary_color": "#101820"],
                ["id": 503, "name": "Tee Higgins · CIN", "current_probability": 0.36, "rank": 3, "primary_color": "#B45309"],
                ["id": 504, "name": "George Pickens · PIT", "current_probability": 0.31, "rank": 4, "primary_color": "#1D4ED8"],
            ],
            "coverage_hours": 72.0,
            "observation_times": 4,
        ]
        let timeline = try makeDecoder().decode(
            ProbabilityTimelineResponse.self,
            from: try JSONSerialization.data(withJSONObject: timelineDict)
        )
        return (market, timeline)
    }

    // MARK: - 1. Golf 192-A Contracts

    func testGolfFirstScreenNamesFourContendersTallerChartAndFullscreenTimeRanges() throws {
        XCTAssertEqual(EventAtlasGolfTournament11666.headlineContenderCount, 4)
        XCTAssertEqual(EventAtlasGolfTournament11666.firstScreenChartHeight, 228)
        XCTAssertGreaterThan(EventAtlasGolfTournament11666.firstScreenChartHeight, 180)

        let (presentation, atlasData) = try makeGolfPresentation(fieldSize: 120)
        let headlineContenders = EventAtlasGolfTournament11666.buildJourneyContenders(
            presentation: presentation,
            atlasData: atlasData,
            selectedGolferName: nil,
            now: fixedNow
        )
        XCTAssertEqual(
            headlineContenders.map(\.name),
            ["Scottie Scheffler", "Rory McIlroy", "Ludvig Åberg", "Collin Morikawa"]
        )
        XCTAssertEqual(
            EventAtlasGolfTournament11666.shortChartEndLabel(for: headlineContenders[0], phase: .recorded),
            "Scheffler 29%"
        )

        // De-collided right-edge Y labels never overlap even when four golfers sit at identical probability
        let clustered = EventAtlasGolfTournament11666.decollidedLabelYPositions(
            targets: [90, 91, 92, 93],
            minGap: 14,
            plotHeight: 200
        )
        XCTAssertEqual(clustered.count, 4)
        for idx in 1..<clustered.count {
            XCTAssertGreaterThanOrEqual(clustered[idx] - clustered[idx - 1], 13.9)
        }

        // Fullscreen time-range filter narrows 24h vs Season
        let dayFiltered = EventAtlasGolfTournament11666.filterContendersByTimeRange(
            headlineContenders,
            range: .day,
            commenceTime: presentation.commenceTime,
            now: fixedNow
        )
        let seasonFiltered = EventAtlasGolfTournament11666.filterContendersByTimeRange(
            headlineContenders,
            range: .season,
            commenceTime: presentation.commenceTime,
            now: fixedNow
        )
        XCTAssertLessThan(dayFiltered[0].points.count, seasonFiltered[0].points.count)
    }

    // MARK: - 2. Futures & Props 192-A Contracts

    func testFuturesAndPropsFirstScreenHeadlineMatchesChartAndAllNLinkOpensField() throws {
        XCTAssertEqual(EvolutionChartView.defaultFirstScreenHeight192A, 296)
        XCTAssertGreaterThan(EvolutionChartView.defaultFirstScreenHeight192A, 280)
        XCTAssertEqual(EvolutionChartView.fullscreenChartHeight192A, 340)

        let (champMarket, _) = try makeChampionshipFutureFixture(teamCount: 28)
        let champPage = FuturesAtlasPresentation11666.build(market: champMarket, now: fixedNow)
        let champHeadline = FuturesAtlasPresentation11666.firstScreenHeadlineRows192A(for: champPage.body)
        XCTAssertEqual(
            champHeadline.map(\.name),
            ["Boston Celtics", "Oklahoma City Thunder", "Cleveland Cavaliers", "Denver Nuggets"]
        )
        XCTAssertEqual(
            FuturesAtlasPresentation11666.allFieldLinkLabel192A(market: champMarket, body: champPage.body),
            "All 28 teams ›"
        )
        XCTAssertEqual(
            FuturesAtlasPresentation11666.chartCardTitle192A(market: champMarket, shape: champPage.body.shape),
            "Title Odds History"
        )

        let (propsMarket, _) = try makePropsFixture(propCount: 53)
        let propsPage = FuturesAtlasPresentation11666.build(market: propsMarket, now: fixedNow)
        let propsHeadline = FuturesAtlasPresentation11666.firstScreenHeadlineRows192A(for: propsPage.body)
        XCTAssertEqual(
            propsHeadline.map(\.name),
            ["Ja'Marr Chase · CIN", "Najee Harris · PIT", "Tee Higgins · CIN", "George Pickens · PIT"]
        )
        XCTAssertEqual(
            FuturesAtlasPresentation11666.allFieldLinkLabel192A(market: propsMarket, body: propsPage.body),
            "All 53 props ›"
        )
        XCTAssertEqual(
            FuturesAtlasPresentation11666.chartCardTitle192A(market: propsMarket, shape: propsPage.body.shape),
            "Touchdown Chance"
        )

        XCTAssertEqual(
            EvolutionChartView.shortEndLabel192A(name: "Ja'Marr Chase · CIN", percentValue: 52),
            "Chase 52%"
        )
        XCTAssertEqual(
            EvolutionChartView.shortEndLabel192A(name: "Boston Celtics", percentValue: 26),
            "Celtics 26%"
        )
    }

    // MARK: - 3. Accessibility Width Fit & 390px Simulator Renders

    private func renderWindowSnapshot<V: View>(
        _ view: V,
        size: CGSize,
        to url: URL
    ) throws {
        let host = hostForMeasurement(view.environment(\.colorScheme, .light), at: .large)
        host.overrideUserInterfaceStyle = .light
        host.view.frame = CGRect(origin: .zero, size: size)
        let window: UIWindow
        if let scene = UIApplication.shared.connectedScenes.compactMap({ $0 as? UIWindowScene }).first {
            window = UIWindow(windowScene: scene)
        } else {
            window = UIWindow(frame: host.view.frame)
        }
        window.frame = host.view.frame
        window.overrideUserInterfaceStyle = .light
        window.rootViewController = host
        window.isHidden = false
        defer {
            window.isHidden = true
            window.rootViewController = nil
        }
        let until = Date().addingTimeInterval(0.35)
        repeat {
            host.view.setNeedsLayout()
            host.view.layoutIfNeeded()
            RunLoop.current.run(until: Date().addingTimeInterval(0.015))
        } while Date() < until
        let fmt = UIGraphicsImageRendererFormat()
        fmt.scale = 3.0
        let image = UIGraphicsImageRenderer(bounds: host.view.bounds, format: fmt).image { _ in
            _ = host.view.drawHierarchy(in: host.view.bounds, afterScreenUpdates: true)
        }
        if let png = image.pngData() {
            try png.write(to: url)
        }
    }

    func testAccessibilityFitAndExport390pxRenders() throws {
        let (golfPres, golfAtlas) = try makeGolfPresentation(fieldSize: 120)
        let (champMarket, champTimeline) = try makeChampionshipFutureFixture(teamCount: 28)
        let (propsMarket, propsTimeline) = try makePropsFixture(propCount: 53)

        let golfA11yHost = hostForMeasurement(
            EventAtlasGolfTournamentSection11666(
                presentation: golfPres,
                atlasData: golfAtlas,
                now: fixedNow
            ).frame(width: 358),
            at: .accessibility2
        )
        let golfA11yWidth = golfA11yHost.sizeThatFits(in: CGSize(width: 358, height: 4000)).width
        XCTAssertLessThanOrEqual(golfA11yWidth, 358.5, "Golf 192-A section must fit 358pt at .accessibility2")

        let champA11yHost = hostForMeasurement(
            FuturesAtlasPageView11666(
                market: champMarket,
                marketId: champMarket.id,
                shareMessage: "",
                onShare: {},
                golfTournamentStart: nil,
                golfTournamentEnd: nil,
                chartRefreshToken: 0,
                representation: .source,
                preloadedTimeline: champTimeline,
                referenceNow: fixedNow
            ).frame(width: 390),
            at: .accessibility2
        )
        let champA11yWidth = champA11yHost.sizeThatFits(in: CGSize(width: 390, height: 4000)).width
        XCTAssertLessThanOrEqual(champA11yWidth, 390.5, "Futures 192-A page must fit 390pt at .accessibility2")

        guard let rawDir = ProcessInfo.processInfo.environment["BUILDER_C_RENDER_DIR"], !rawDir.isEmpty else {
            return
        }
        let dirURL = URL(fileURLWithPath: rawDir, isDirectory: true)
        try FileManager.default.createDirectory(at: dirURL, withIntermediateDirectories: true)

        // 1. Golf 192-A first screen (390x852)
        let golfPage = NavigationStack {
            ScrollView {
                EventAtlasGolfTournamentSection11666(
                    presentation: golfPres,
                    atlasData: golfAtlas,
                    now: fixedNow
                )
                .padding(.horizontal, 16)
                .padding(.top, 10)
            }
            .background(Color(uiColor: .systemGroupedBackground))
            .navigationTitle("Golf")
            .navigationBarTitleDisplayMode(.inline)
        }
        .frame(width: 390, height: 852)

        try renderWindowSnapshot(
            golfPage,
            size: CGSize(width: 390, height: 852),
            to: dirURL.appendingPathComponent("overnight3-golf-192a-390x852.png")
        )

        // 2. Championship Future 192-A first screen (390x852)
        let futuresPage = NavigationStack {
            ScrollView {
                FuturesAtlasPageView11666(
                    market: champMarket,
                    marketId: champMarket.id,
                    shareMessage: "",
                    onShare: {},
                    golfTournamentStart: nil,
                    golfTournamentEnd: nil,
                    chartRefreshToken: 0,
                    representation: .source,
                    preloadedTimeline: champTimeline,
                    referenceNow: fixedNow
                )
            }
            .background(Color(uiColor: .systemGroupedBackground))
            .navigationTitle("Market Details")
            .navigationBarTitleDisplayMode(.inline)
        }
        .frame(width: 390, height: 852)

        try renderWindowSnapshot(
            futuresPage,
            size: CGSize(width: 390, height: 852),
            to: dirURL.appendingPathComponent("overnight3-futures-192a-390x852.png")
        )

        // 3. Game Props 192-A first screen (390x852)
        let propsPage = NavigationStack {
            ScrollView {
                FuturesAtlasPageView11666(
                    market: propsMarket,
                    marketId: propsMarket.id,
                    shareMessage: "",
                    onShare: {},
                    golfTournamentStart: nil,
                    golfTournamentEnd: nil,
                    chartRefreshToken: 0,
                    representation: .source,
                    preloadedTimeline: propsTimeline,
                    referenceNow: fixedNow
                )
            }
            .background(Color(uiColor: .systemGroupedBackground))
            .navigationTitle("Props")
            .navigationBarTitleDisplayMode(.inline)
        }
        .frame(width: 390, height: 852)

        try renderWindowSnapshot(
            propsPage,
            size: CGSize(width: 390, height: 852),
            to: dirURL.appendingPathComponent("overnight3-props-192a-390x852.png")
        )

        // 4. Full-screen chart sheet showing time-range bar moved here & Sum/Top N retired (390x760)
        let fullscreenSheet = NavigationStack {
            ScrollView {
                EvolutionChartView(
                    marketId: champMarket.id,
                    hours: 168,
                    height: EvolutionChartView.fullscreenChartHeight192A,
                    representation: .source,
                    firstScreenCompact192A: true,
                    isPresentedFullscreen192A: true,
                    chartTitle192A: "Title Odds History",
                    headlineContenderNames: ["Boston Celtics", "Oklahoma City Thunder", "Cleveland Cavaliers", "Denver Nuggets"],
                    preloadedTimeline: champTimeline,
                    referenceNow: fixedNow
                )
                .padding(16)
            }
            .background(Color(uiColor: .systemGroupedBackground))
            .navigationTitle("2026-27 NBA Champion")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("Done") {}
                }
            }
        }
        .frame(width: 390, height: 760)

        try renderWindowSnapshot(
            fullscreenSheet,
            size: CGSize(width: 390, height: 760),
            to: dirURL.appendingPathComponent("overnight3-fullscreen-chart-390.png")
        )
    }
}
