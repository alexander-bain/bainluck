import SwiftUI
import UIKit
import XCTest
@testable import Bain_Luck

@MainActor
final class NCAABHeadlinesSat2CTests: XCTestCase {

    private let fixedNow = ISO8601DateFormatter().date(from: "2026-11-14T14:50:00Z")!

    private struct StubEventDetailProvider: EventDetailProviding {
        let detail: EventDetail
        let history: EventHistoryResponse

        func fetchEvent(id: Int) async throws -> EventDetail { detail }
        func fetchEventHistory(id: Int, hours: Int) async throws -> EventHistoryResponse { history }
        func fetchRelatedFutures(eventId: Int) async throws -> RelatedFuturesResponse {
            let decoder = JSONDecoder()
            decoder.keyDecodingStrategy = .convertFromSnakeCase
            return try decoder.decode(
                RelatedFuturesResponse.self,
                from: Data(#"{"event_id":\#(eventId),"home_team":"Home","away_team":"Away","markets":[]}"#.utf8)
            )
        }
        func fetchTeamProgression(eventId: Int) async throws -> TeamProgressionResponse {
            let decoder = JSONDecoder()
            decoder.keyDecodingStrategy = .convertFromSnakeCase
            return try decoder.decode(
                TeamProgressionResponse.self,
                from: Data(#"{"event_id":\#(eventId),"home":null,"away":null}"#.utf8)
            )
        }
        func fetchGameMarkets(eventId: Int) async throws -> GameMarketsResponse {
            let decoder = JSONDecoder()
            decoder.keyDecodingStrategy = .convertFromSnakeCase
            return try decoder.decode(
                GameMarketsResponse.self,
                from: Data(#"{"event_id":\#(eventId),"player_props":[],"period_markets":[],"other_markets":[]}"#.utf8)
            )
        }
        func fetchLineMovement(eventId: Int) async throws -> LineMovementResponse {
            LineMovementResponse(
                eventId: eventId,
                movements: [],
                explanation: nil,
                disagreementExplanation: nil,
                disagreementData: nil,
                context: nil,
                cached: nil,
                createdAt: nil
            )
        }
    }

    private func decodeEvent(_ json: String) throws -> EventDetail {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(EventDetail.self, from: Data(json.utf8))
    }

    private func decodeHistory(_ json: String) throws -> EventHistoryResponse {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(EventHistoryResponse.self, from: Data(json.utf8))
    }

    private func ncaabBeforeFixture(
        sport: String = "basketball_ncaab",
        commenceTime: String = "2026-11-14T23:30:00Z"
    ) throws -> EventDetail {
        try decodeEvent("""
        {
          "id": 9127221,
          "sport": "\(sport)",
          "home_team": "Duke Blue Devils",
          "away_team": "Kansas Jayhawks",
          "commence_time": "\(commenceTime)",
          "status": "scheduled",
          "home_team_data": {
            "abbreviation": "DUKE",
            "primary_color": "#003087",
            "record": "3-0"
          },
          "away_team_data": {
            "abbreviation": "KU",
            "primary_color": "#0051BA",
            "record": "3-0"
          },
          "current_odds": {
            "projected_home_score": 78.5,
            "projected_away_score": 75.5,
            "home_probability": 0.578,
            "away_probability": 0.422,
            "home_rendered_percent": 58,
            "away_rendered_percent": 42,
            "updated_at": "2026-11-14T14:48:00Z"
          },
          "opening_odds": {
            "home_probability": 0.55,
            "away_probability": 0.45,
            "home_rendered_percent": 55,
            "away_rendered_percent": 45
          },
          "hero_probability": 0.578,
          "hero_probability_away": 0.422,
          "hero_probability_source": "blend",
          "hero_probability_observed_at": "2026-11-14T14:48:00Z",
          "espn": {
            "broadcast": "ESPN"
          },
          "win_probability_sources": {
            "betting": { "value": 0.58, "display_name": "Sportsbooks" },
            "kalshi": { "value": 0.575, "display_name": "Kalshi" },
            "polymarket": { "value": 0.58, "display_name": "Polymarket" }
          },
          "source_mark": {
            "state": "blend",
            "sources": [
              { "key": "kalshi", "name": "Kalshi", "probability": 0.575, "observed_at": "2026-11-14T14:48:00Z" },
              { "key": "polymarket", "name": "Polymarket", "probability": 0.58, "observed_at": "2026-11-14T14:47:50Z" },
              { "key": "betting", "name": "Sportsbooks", "probability": 0.58, "count": 5, "observed_at": "2026-11-14T14:47:30Z" }
            ]
          }
        }
        """)
    }

    private func ncaabDuringFixture() throws -> EventDetail {
        try decodeEvent("""
        {
          "id": 9127222,
          "sport": "basketball_ncaab",
          "home_team": "Purdue Boilermakers",
          "away_team": "Gonzaga Bulldogs",
          "commence_time": "2026-11-14T13:15:00Z",
          "status": "live",
          "home_score": 61,
          "away_score": 66,
          "home_team_data": {
            "abbreviation": "PUR",
            "primary_color": "#CEB888",
            "record": "3-0"
          },
          "away_team_data": {
            "abbreviation": "GONZ",
            "primary_color": "#041E42",
            "record": "3-0"
          },
          "current_odds": {
            "live_projection": {
              "kind": "in_play",
              "boundary": "commence_time",
              "boundary_at": "2026-11-14T13:15:00Z",
              "source": "sportsbooks",
              "basis": "consensus_spread_total",
              "unit": "points",
              "period": "full_game",
              "bookmaker_count": 5,
              "projected_home_score": 77.5,
              "projected_away_score": 81.5,
              "earliest_confirmed_at": "2026-11-14T13:55:00Z",
              "latest_captured_at": "2026-11-14T14:49:00Z"
            },
            "home_probability": 0.342,
            "away_probability": 0.658,
            "home_rendered_percent": 34,
            "away_rendered_percent": 66,
            "updated_at": "2026-11-14T14:49:30Z"
          },
          "prematch_odds": {
            "home_probability": 0.52,
            "away_probability": 0.48,
            "home_rendered_percent": 52,
            "away_rendered_percent": 48,
            "source": "blend"
          },
          "opening_odds": {
            "home_probability": 0.52,
            "away_probability": 0.48,
            "home_rendered_percent": 52,
            "away_rendered_percent": 48
          },
          "hero_probability": 0.342,
          "hero_probability_away": 0.658,
          "hero_probability_source": "blend",
          "hero_probability_observed_at": "2026-11-14T14:49:30Z",
          "espn": {
            "period": "2nd Half",
            "game_clock": "7:42",
            "broadcast": "FOX"
          },
          "source_mark": {
            "state": "blend",
            "sources": [
              { "key": "kalshi", "name": "Kalshi", "probability": 0.34, "observed_at": "2026-11-14T14:49:30Z" },
              { "key": "polymarket", "name": "Polymarket", "probability": 0.345, "observed_at": "2026-11-14T14:49:20Z" },
              { "key": "betting", "name": "Sportsbooks", "probability": 0.34, "count": 5, "observed_at": "2026-11-14T14:49:10Z" }
            ]
          }
        }
        """)
    }

    private func ncaabAfterFixture(sport: String = "basketball_ncaab") throws -> EventDetail {
        try decodeEvent("""
        {
          "id": 9127223,
          "sport": "\(sport)",
          "home_team": "Houston Cougars",
          "away_team": "UConn Huskies",
          "commence_time": "2026-11-10T01:00:00Z",
          "completed_at": "2026-11-10T03:12:00Z",
          "status": "completed",
          "home_score": 71,
          "away_score": 76,
          "hero_settled_result": "away",
          "home_team_data": {
            "abbreviation": "HOU",
            "primary_color": "#C8102E",
            "record": "2-1"
          },
          "away_team_data": {
            "abbreviation": "CONN",
            "primary_color": "#000E2F",
            "record": "3-0"
          },
          "prematch_odds": {
            "home_probability": 0.54,
            "away_probability": 0.46,
            "home_rendered_percent": 54,
            "away_rendered_percent": 46,
            "source": "blend"
          },
          "pregame_projection": {
            "kind": "last_before_scheduled_start",
            "boundary": "scheduled_start",
            "boundary_at": "2026-11-10T01:00:00Z",
            "source": "sportsbooks",
            "basis": "consensus_spread_total",
            "unit": "points",
            "period": "full_game",
            "bookmaker_count": 5,
            "projected_home_score": 72.5,
            "projected_away_score": 70.5,
            "earliest_captured_at": "2026-11-09T20:00:00Z",
            "latest_captured_at": "2026-11-10T00:55:00Z"
          },
          "source_mark": {
            "state": "blend",
            "sources": [
              { "key": "kalshi", "name": "Kalshi", "probability": 0.54, "observed_at": "2026-11-10T00:58:00Z" },
              { "key": "polymarket", "name": "Polymarket", "probability": 0.54, "observed_at": "2026-11-10T00:57:50Z" },
              { "key": "betting", "name": "Sportsbooks", "probability": 0.54, "count": 5, "observed_at": "2026-11-10T00:57:00Z" }
            ]
          }
        }
        """)
    }

    private func makeHistory(event: EventDetail, startHome: Double, endHome: Double) throws -> EventHistoryResponse {
        let startAway = max(0.0, min(1.0, 1.0 - startHome))
        let midHome = (startHome + endHome) / 2.0
        let midAway = max(0.0, min(1.0, 1.0 - midHome))
        let endAway = max(0.0, min(1.0, 1.0 - endHome))
        let baseDate = event.commenceTime?.asDate ?? fixedNow
        let fmt = ISO8601DateFormatter()
        let t0: String
        let t1: String
        let t2: String
        if event.status == "scheduled" {
            t0 = fmt.string(from: baseDate.addingTimeInterval(-14_400))
            t1 = fmt.string(from: baseDate.addingTimeInterval(-7_200))
            t2 = fmt.string(from: baseDate.addingTimeInterval(-1_800))
        } else {
            t0 = fmt.string(from: baseDate.addingTimeInterval(120))
            t1 = fmt.string(from: baseDate.addingTimeInterval(2_100))
            t2 = fmt.string(from: baseDate.addingTimeInterval(4_200))
        }
        return try decodeHistory("""
        {
          "event_id": \(event.id),
          "home_team": "\(event.homeTeam)",
          "away_team": "\(event.awayTeam)",
          "history": [
            { "timestamp": "\(t0)", "home_probability": \(startHome), "away_probability": \(startAway), "source": "aggregate" },
            { "timestamp": "\(t1)", "home_probability": \(midHome), "away_probability": \(midAway), "source": "aggregate" },
            { "timestamp": "\(t2)", "home_probability": \(endHome), "away_probability": \(endAway), "source": "aggregate" }
          ]
        }
        """)
    }

    func testNCAABAndWNCAABBeforeDuringAndAfterAdoptCompactHeadlineRules() throws {
        let before = try ncaabBeforeFixture()
        XCTAssertEqual(EventSportHeadlines12472.kind(for: before, now: fixedNow), .ncaabBeforeGame)

        for streaming in [false, true] {
            let model = try XCTUnwrap(
                EventSportHeadlines12472.resolve(
                    event: before,
                    awayFullName: before.awayTeam,
                    homeFullName: before.homeTeam,
                    liveStatusText: nil,
                    hasScore: false,
                    numberStreams: streaming,
                    now: fixedNow
                )
            )
            XCTAssertEqual(model.leagueLabel, "NCAAB")
            XCTAssertNil(model.liveBadgeText)
            XCTAssertEqual(
                model.pregameColumnHeaders,
                EventSportHeadlines12472.PregameColumnHeaders(projected: "Proj.", chance: "Chance")
            )
            XCTAssertEqual(model.away.shortName, "Jayhawks")
            XCTAssertEqual(model.away.pregameProjectedNumberText, "75.5")
            XCTAssertEqual(model.away.winChanceText, "42%")
            XCTAssertEqual(model.home.shortName, "Blue Devils")
            XCTAssertEqual(model.home.pregameProjectedNumberText, "78.5")
            XCTAssertEqual(model.home.winChanceText, "58%")
        }

        let wncaabBefore = try ncaabBeforeFixture(sport: "basketball_wncaab")
        XCTAssertEqual(EventSportHeadlines12472.kind(for: wncaabBefore, now: fixedNow), .ncaabBeforeGame)
        let wncaabModel = try XCTUnwrap(
            EventSportHeadlines12472.resolve(
                event: wncaabBefore,
                awayFullName: wncaabBefore.awayTeam,
                homeFullName: wncaabBefore.homeTeam,
                liveStatusText: nil,
                hasScore: false,
                numberStreams: false,
                now: fixedNow
            )
        )
        XCTAssertEqual(wncaabModel.leagueLabel, "WNCAAB")

        let during = try ncaabDuringFixture()
        XCTAssertEqual(EventSportHeadlines12472.kind(for: during, now: fixedNow), .ncaabDuringGame)
        let liveModel = try XCTUnwrap(
            EventSportHeadlines12472.resolve(
                event: during,
                awayFullName: during.awayTeam,
                homeFullName: during.homeTeam,
                liveStatusText: PeriodLabel.liveStatusText(
                    period: during.espn?.period,
                    gameClock: during.espn?.gameClock
                ),
                hasScore: true,
                numberStreams: true,
                now: fixedNow
            )
        )
        XCTAssertEqual(liveModel.leagueLabel, "NCAAB")
        XCTAssertEqual(liveModel.liveBadgeText, "LIVE · 2H 7:42")
        XCTAssertEqual(
            liveModel.liveColumnHeaders,
            EventSportHeadlines12472.LiveColumnHeaders(score: "Score", pregame: "Pregame", now: "Now")
        )
        XCTAssertEqual(liveModel.away.shortName, "Bulldogs")
        XCTAssertEqual(liveModel.away.projectedText, "Proj. 81.5")
        XCTAssertEqual(liveModel.away.liveScore, 66)
        XCTAssertEqual(liveModel.away.pregameChanceText, "48%")
        XCTAssertEqual(liveModel.away.winChanceText, "65.8%")
        XCTAssertEqual(liveModel.home.shortName, "Boilermakers")
        XCTAssertEqual(liveModel.home.projectedText, "Proj. 77.5")
        XCTAssertEqual(liveModel.home.liveScore, 61)
        XCTAssertEqual(liveModel.home.pregameChanceText, "52%")
        XCTAssertEqual(liveModel.home.winChanceText, "34.2%")

        let after = try ncaabAfterFixture()
        XCTAssertEqual(EventSportHeadlines12472.kind(for: after, now: fixedNow), .ncaabAfterGame)
        let finalModel = try XCTUnwrap(
            EventSportHeadlines12472.resolve(
                event: after,
                awayFullName: after.awayTeam,
                homeFullName: after.homeTeam,
                liveStatusText: nil,
                hasScore: true,
                numberStreams: false,
                now: fixedNow
            )
        )
        XCTAssertTrue(finalModel.plainMetaText?.hasPrefix("NCAAB · Final") == true)
        XCTAssertEqual(
            finalModel.finalColumnHeaders,
            EventSportHeadlines12472.FinalColumnHeaders(pregame: "Pregame", finalLabel: "Final")
        )
        XCTAssertEqual(finalModel.away.shortName, "Huskies")
        XCTAssertEqual(finalModel.away.won, true)
        XCTAssertEqual(finalModel.away.pregameChanceText, "46%")
        XCTAssertEqual(finalModel.away.finalResultText, "76")
        XCTAssertEqual(finalModel.away.secondarySublineText, "3-0 · Proj. 71")
        XCTAssertEqual(finalModel.home.shortName, "Cougars")
        XCTAssertEqual(finalModel.home.won, false)
        XCTAssertEqual(finalModel.home.pregameChanceText, "54%")
        XCTAssertEqual(finalModel.home.finalResultText, "71")
        XCTAssertEqual(finalModel.home.secondarySublineText, "2-1 · Proj. 73")

        let wncaabAfter = try ncaabAfterFixture(sport: "basketball_wncaab")
        let wncaabFinalModel = try XCTUnwrap(
            EventSportHeadlines12472.resolve(
                event: wncaabAfter,
                awayFullName: wncaabAfter.awayTeam,
                homeFullName: wncaabAfter.homeTeam,
                liveStatusText: nil,
                hasScore: true,
                numberStreams: false,
                now: fixedNow
            )
        )
        XCTAssertTrue(wncaabFinalModel.plainMetaText?.hasPrefix("WNCAAB · Final") == true)
    }

    func testNCAABAllStatesFitAt390AndAccessibility2AndExport390pxRenders() async throws {
        let before = try ncaabBeforeFixture()
        let during = try ncaabDuringFixture()
        let after = try ncaabAfterFixture()

        func makeCard(
            _ event: EventDetail,
            liveStatus: String?,
            hasScore: Bool,
            streams: Bool
        ) throws -> EventSportHeadlineCard12472 {
            let model = try XCTUnwrap(
                EventSportHeadlines12472.resolve(
                    event: event,
                    awayFullName: event.awayTeam,
                    homeFullName: event.homeTeam,
                    liveStatusText: liveStatus,
                    hasScore: hasScore,
                    numberStreams: streams,
                    now: fixedNow
                )
            )
            let pairColors = TeamTextContrast.cardColors(
                awayHex: event.awayTeamData?.primaryColor,
                homeHex: event.homeTeamData?.primaryColor
            )
            return EventSportHeadlineCard12472(
                model: model,
                colors: pairColors,
                ekgTracker: .empty,
                liveUpdateStatus: event.status == "live" ? .live : .awaitingUpdate,
                displayAsOf: fixedNow,
                updateStream: LiveUpdateStream(),
                showUpdateStream: .constant(false),
                showProbabilityDetails: .constant(false),
                priceStreamingEligible: event.status == "live",
                lastReceivedAt: fixedNow,
                confirmedAt: fixedNow,
                revealForecast: nil
            )
        }

        let beforeCard = try makeCard(before, liveStatus: nil, hasScore: false, streams: false)
        let duringCard = try makeCard(
            during,
            liveStatus: PeriodLabel.liveStatusText(period: during.espn?.period, gameClock: during.espn?.gameClock),
            hasScore: true,
            streams: true
        )
        let afterCard = try makeCard(after, liveStatus: nil, hasScore: true, streams: false)

        for card in [beforeCard, duringCard, afterCard] {
            for dt in [DynamicTypeSize.large, .accessibility2] {
                let host = hostForMeasurement(card.frame(width: 358), at: dt)
                let fitted = host.sizeThatFits(in: CGSize(width: 358, height: 1000))
                XCTAssertLessThanOrEqual(fitted.width, 358.5)
                XCTAssertGreaterThan(fitted.height, 80)
            }
        }

        if let outDir = ProcessInfo.processInfo.environment["EXPORT_SAT2C_NCAAB_RENDERS_DIR"],
           !outDir.isEmpty {
            let dirURL = URL(fileURLWithPath: outDir, isDirectory: true)
            try FileManager.default.createDirectory(at: dirURL, withIntermediateDirectories: true)

            func writeHostedPNG<V: View>(
                _ view: V,
                size: CGSize,
                at dt: DynamicTypeSize = .large,
                to url: URL
            ) async throws {
                let host = hostForMeasurement(view.environment(\.colorScheme, .light), at: dt)
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
                host.view.setNeedsLayout()
                host.view.layoutIfNeeded()
                try await Task.sleep(nanoseconds: 250_000_000)
                let until = Date().addingTimeInterval(0.30)
                repeat {
                    host.view.setNeedsLayout()
                    host.view.layoutIfNeeded()
                    RunLoop.current.run(until: Date().addingTimeInterval(0.015))
                } while Date() < until
                let fmt = UIGraphicsImageRendererFormat()
                fmt.scale = 3.0
                let img = UIGraphicsImageRenderer(bounds: host.view.bounds, format: fmt).image { _ in
                    _ = host.view.drawHierarchy(in: host.view.bounds, afterScreenUpdates: true)
                }
                if let png = img.pngData() {
                    try png.write(to: url)
                }
            }

            func makeFullPage(_ event: EventDetail, startHome: Double, endHome: Double) async throws -> AnyView {
                let hist = try makeHistory(event: event, startHome: startHome, endHome: endHome)
                let vm = EventDetailViewModel(
                    eventId: event.id,
                    client: StubEventDetailProvider(detail: event, history: hist)
                )
                await vm.load()
                vm.stopRefresh()
                return AnyView(
                    NavigationStack {
                        EventDetailView(eventId: event.id)
                            .withLoadedEventForTest12278(event, viewModel: vm)
                    }
                    .environmentObject(PinManager())
                    .environmentObject(NavigationCoordinator())
                    .frame(width: 390, height: 852)
                    .background(Color(uiColor: .systemGroupedBackground))
                )
            }

            try await writeHostedPNG(
                try await makeFullPage(before, startHome: 0.55, endHome: 0.578),
                size: CGSize(width: 390, height: 852),
                to: dirURL.appendingPathComponent("sat2c-ncaab-before-390x852.png")
            )
            try await writeHostedPNG(
                try await makeFullPage(during, startHome: 0.52, endHome: 0.342),
                size: CGSize(width: 390, height: 852),
                to: dirURL.appendingPathComponent("sat2c-ncaab-during-390x852.png")
            )
            try await writeHostedPNG(
                try await makeFullPage(after, startHome: 0.54, endHome: 0.0),
                size: CGSize(width: 390, height: 852),
                to: dirURL.appendingPathComponent("sat2c-ncaab-after-390x852.png")
            )

            let sheet = VStack(alignment: .leading, spacing: 14) {
                VStack(alignment: .leading, spacing: 5) {
                    Text("NCAAB Before · Proj. & Chance Columns, Whole %, No Countdown Capsule")
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(.secondary)
                    beforeCard
                }
                VStack(alignment: .leading, spacing: 5) {
                    Text("NCAAB During · Live Score, Pregame & Now + Live Proj. Once")
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(.secondary)
                    duringCard
                }
                VStack(alignment: .leading, spacing: 5) {
                    Text("NCAAB After · Aligned Pregame & Final, Winner ✓")
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(.secondary)
                    afterCard
                }
            }
            .padding(16)
            .frame(width: 390)
            .background(Color(uiColor: .systemGroupedBackground))

            let sheetHost = hostForMeasurement(sheet.environment(\.colorScheme, .light), at: .large)
            let sheetHeight = ceil(sheetHost.sizeThatFits(in: CGSize(width: 390, height: 2000)).height)
            try await writeHostedPNG(
                sheet,
                size: CGSize(width: 390, height: sheetHeight),
                to: dirURL.appendingPathComponent("sat2c-ncaab-all-states-sheet-390.png")
            )
        }
    }
}
