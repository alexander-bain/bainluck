import SwiftUI
import UIKit
import XCTest
@testable import Bain_Luck

@MainActor
final class MLBHeadlinesSat2DTests: XCTestCase {

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

    private func mlbBeforeFixture(commenceTime: String = "2026-11-15T02:40:00Z") throws -> EventDetail {
        try decodeEvent("""
        {
          "id": 9127241,
          "sport": "baseball_mlb",
          "home_team": "Los Angeles Dodgers",
          "away_team": "San Diego Padres",
          "commence_time": "\(commenceTime)",
          "status": "scheduled",
          "home_team_data": {
            "abbreviation": "LAD",
            "primary_color": "#005A9C",
            "record": "98-64"
          },
          "away_team_data": {
            "abbreviation": "SD",
            "primary_color": "#2F241D",
            "record": "93-69"
          },
          "current_odds": {
            "home_probability": 0.582,
            "away_probability": 0.418,
            "home_rendered_percent": 58,
            "away_rendered_percent": 42,
            "updated_at": "2026-11-14T14:48:00Z"
          },
          "opening_odds": {
            "home_probability": 0.56,
            "away_probability": 0.44,
            "home_rendered_percent": 56,
            "away_rendered_percent": 44
          },
          "hero_probability": 0.582,
          "hero_probability_away": 0.418,
          "hero_probability_source": "blend",
          "hero_probability_observed_at": "2026-11-14T14:48:00Z",
          "espn": {
            "broadcast": "FOX"
          },
          "win_probability_sources": {
            "betting": { "value": 0.58, "display_name": "Sportsbooks" },
            "kalshi": { "value": 0.585, "display_name": "Kalshi" },
            "polymarket": { "value": 0.58, "display_name": "Polymarket" }
          },
          "source_mark": {
            "state": "blend",
            "sources": [
              { "key": "kalshi", "name": "Kalshi", "probability": 0.585, "observed_at": "2026-11-14T14:48:00Z" },
              { "key": "polymarket", "name": "Polymarket", "probability": 0.58, "observed_at": "2026-11-14T14:47:50Z" },
              { "key": "betting", "name": "Sportsbooks", "probability": 0.58, "count": 5, "observed_at": "2026-11-14T14:47:30Z" }
            ]
          }
        }
        """)
    }

    private func mlbDuringFixture() throws -> EventDetail {
        try decodeEvent("""
        {
          "id": 9127242,
          "sport": "baseball_mlb",
          "home_team": "Los Angeles Dodgers",
          "away_team": "San Diego Padres",
          "commence_time": "2026-11-14T13:15:00Z",
          "status": "live",
          "home_score": 4,
          "away_score": 3,
          "home_team_data": {
            "abbreviation": "LAD",
            "primary_color": "#005A9C",
            "record": "98-64"
          },
          "away_team_data": {
            "abbreviation": "SD",
            "primary_color": "#2F241D",
            "record": "93-69"
          },
          "current_odds": {
            "home_probability": 0.718,
            "away_probability": 0.282,
            "home_rendered_percent": 72,
            "away_rendered_percent": 28,
            "updated_at": "2026-11-14T14:49:30Z"
          },
          "prematch_odds": {
            "home_probability": 0.58,
            "away_probability": 0.42,
            "home_rendered_percent": 58,
            "away_rendered_percent": 42,
            "source": "blend"
          },
          "opening_odds": {
            "home_probability": 0.58,
            "away_probability": 0.42,
            "home_rendered_percent": 58,
            "away_rendered_percent": 42
          },
          "hero_probability": 0.718,
          "hero_probability_away": 0.282,
          "hero_probability_source": "blend",
          "hero_probability_observed_at": "2026-11-14T14:49:30Z",
          "espn": {
            "period": "Top 7th",
            "broadcast": "FOX"
          },
          "source_mark": {
            "state": "blend",
            "sources": [
              { "key": "kalshi", "name": "Kalshi", "probability": 0.72, "observed_at": "2026-11-14T14:49:30Z" },
              { "key": "polymarket", "name": "Polymarket", "probability": 0.715, "observed_at": "2026-11-14T14:49:20Z" },
              { "key": "betting", "name": "Sportsbooks", "probability": 0.72, "count": 5, "observed_at": "2026-11-14T14:49:10Z" }
            ]
          }
        }
        """)
    }

    private func makeHistory(
        event: EventDetail,
        startHome: Double,
        endHome: Double,
        projHome: Double,
        projAway: Double
    ) throws -> EventHistoryResponse {
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
          "pm_spread_data": {
            "projected_final": {
              "home_score": \(projHome),
              "away_score": \(projAway),
              "spread_source": "kalshi"
            }
          },
          "history": [
            { "timestamp": "\(t0)", "home_probability": \(startHome), "away_probability": \(startAway), "source": "aggregate" },
            { "timestamp": "\(t1)", "home_probability": \(midHome), "away_probability": \(midAway), "source": "aggregate" },
            { "timestamp": "\(t2)", "home_probability": \(endHome), "away_probability": \(endAway), "source": "aggregate" }
          ]
        }
        """)
    }

    func testMLBBeforeAndDuringAdoptCompactHeadlineRules() throws {
        let before = try mlbBeforeFixture()
        XCTAssertEqual(EventSportHeadlines12472.kind(for: before, now: fixedNow), .mlbBeforeGame)

        for streaming in [false, true] {
            let model = try XCTUnwrap(
                EventSportHeadlines12472.resolve(
                    event: before,
                    awayFullName: before.awayTeam,
                    homeFullName: before.homeTeam,
                    liveStatusText: nil,
                    hasScore: false,
                    numberStreams: streaming,
                    ladderHome: 4.6,
                    ladderAway: 3.9,
                    now: fixedNow
                )
            )
            XCTAssertEqual(model.leagueLabel, "MLB")
            XCTAssertNil(model.liveBadgeText)
            XCTAssertTrue(model.showsRowDivider)
            XCTAssertEqual(
                model.pregameColumnHeaders,
                EventSportHeadlines12472.PregameColumnHeaders(projected: "Proj.", chance: "Chance")
            )
            XCTAssertEqual(model.away.shortName, "Padres")
            XCTAssertEqual(model.away.pregameProjectedNumberText, "3.9")
            XCTAssertEqual(model.away.winChanceText, "42%")
            XCTAssertEqual(model.home.shortName, "Dodgers")
            XCTAssertEqual(model.home.pregameProjectedNumberText, "4.6")
            XCTAssertEqual(model.home.winChanceText, "58%")
        }

        let beforeNoProj = try XCTUnwrap(
            EventSportHeadlines12472.resolve(
                event: before,
                awayFullName: before.awayTeam,
                homeFullName: before.homeTeam,
                liveStatusText: nil,
                hasScore: false,
                numberStreams: false,
                now: fixedNow
            )
        )
        XCTAssertEqual(
            beforeNoProj.pregameColumnHeaders,
            EventSportHeadlines12472.PregameColumnHeaders(projected: nil, chance: "Chance")
        )

        let during = try mlbDuringFixture()
        XCTAssertEqual(EventSportHeadlines12472.kind(for: during, now: fixedNow), .mlbDuringGame)
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
                ladderHome: 5.2,
                ladderAway: 3.8,
                now: fixedNow
            )
        )
        XCTAssertEqual(liveModel.leagueLabel, "MLB")
        XCTAssertEqual(liveModel.liveBadgeText, "LIVE · Top 7th")
        XCTAssertTrue(liveModel.showsRowDivider)
        XCTAssertEqual(
            liveModel.liveColumnHeaders,
            EventSportHeadlines12472.LiveColumnHeaders(score: "Score", pregame: "Pregame", now: "Now")
        )
        XCTAssertEqual(liveModel.away.shortName, "Padres")
        XCTAssertEqual(liveModel.away.projectedText, "Proj. 3.8")
        XCTAssertEqual(liveModel.away.liveScore, 3)
        XCTAssertEqual(liveModel.away.pregameChanceText, "42%")
        XCTAssertEqual(liveModel.away.winChanceText, "28.2%")
        XCTAssertEqual(liveModel.home.shortName, "Dodgers")
        XCTAssertEqual(liveModel.home.projectedText, "Proj. 5.2")
        XCTAssertEqual(liveModel.home.liveScore, 4)
        XCTAssertEqual(liveModel.home.pregameChanceText, "58%")
        XCTAssertEqual(liveModel.home.winChanceText, "71.8%")

        let liveNoProj = try XCTUnwrap(
            EventSportHeadlines12472.resolve(
                event: during,
                awayFullName: during.awayTeam,
                homeFullName: during.homeTeam,
                liveStatusText: "Top 7th",
                hasScore: true,
                numberStreams: true,
                now: fixedNow
            )
        )
        XCTAssertTrue(liveNoProj.stacksRecordUnderName)
        XCTAssertEqual(liveNoProj.away.record, "93-69")
        XCTAssertEqual(liveNoProj.home.record, "98-64")
    }

    func testMLBBeforeAndDuringFitAt390AndAccessibility2AndExport390pxRenders() async throws {
        let before = try mlbBeforeFixture()
        let during = try mlbDuringFixture()

        func makeCard(
            _ event: EventDetail,
            liveStatus: String?,
            hasScore: Bool,
            streams: Bool,
            ladderHome: Double?,
            ladderAway: Double?
        ) throws -> EventSportHeadlineCard12472 {
            let model = try XCTUnwrap(
                EventSportHeadlines12472.resolve(
                    event: event,
                    awayFullName: event.awayTeam,
                    homeFullName: event.homeTeam,
                    liveStatusText: liveStatus,
                    hasScore: hasScore,
                    numberStreams: streams,
                    ladderHome: ladderHome,
                    ladderAway: ladderAway,
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

        let beforeCard = try makeCard(
            before,
            liveStatus: nil,
            hasScore: false,
            streams: false,
            ladderHome: 4.6,
            ladderAway: 3.9
        )
        let duringCard = try makeCard(
            during,
            liveStatus: PeriodLabel.liveStatusText(period: during.espn?.period, gameClock: during.espn?.gameClock),
            hasScore: true,
            streams: true,
            ladderHome: 5.2,
            ladderAway: 3.8
        )

        for card in [beforeCard, duringCard] {
            for dt in [DynamicTypeSize.large, .accessibility2] {
                let host = hostForMeasurement(card.frame(width: 358), at: dt)
                let fitted = host.sizeThatFits(in: CGSize(width: 358, height: 1000))
                XCTAssertLessThanOrEqual(fitted.width, 358.5)
                XCTAssertGreaterThan(fitted.height, 80)
            }
        }

        if let outDir = ProcessInfo.processInfo.environment["EXPORT_SAT2D_MLB_RENDERS_DIR"],
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

            func makeFullPage(
                _ event: EventDetail,
                startHome: Double,
                endHome: Double,
                projHome: Double,
                projAway: Double
            ) async throws -> AnyView {
                let hist = try makeHistory(
                    event: event,
                    startHome: startHome,
                    endHome: endHome,
                    projHome: projHome,
                    projAway: projAway
                )
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
                try await makeFullPage(before, startHome: 0.56, endHome: 0.582, projHome: 4.6, projAway: 3.9),
                size: CGSize(width: 390, height: 852),
                to: dirURL.appendingPathComponent("sat2d-mlb-before-390x852.png")
            )
            try await writeHostedPNG(
                try await makeFullPage(during, startHome: 0.58, endHome: 0.718, projHome: 5.2, projAway: 3.8),
                size: CGSize(width: 390, height: 852),
                to: dirURL.appendingPathComponent("sat2d-mlb-during-390x852.png")
            )

            let sheet = VStack(alignment: .leading, spacing: 14) {
                VStack(alignment: .leading, spacing: 5) {
                    Text("MLB Before · Proj. Runs & Chance Columns, Whole %, No Countdown Capsule")
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(.secondary)
                    beforeCard
                }
                VStack(alignment: .leading, spacing: 5) {
                    Text("MLB During · Live Inning, Score, Pregame & Now + Live Proj. Runs Once")
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(.secondary)
                    duringCard
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
                to: dirURL.appendingPathComponent("sat2d-mlb-before-during-sheet-390.png")
            )
        }
    }
}
