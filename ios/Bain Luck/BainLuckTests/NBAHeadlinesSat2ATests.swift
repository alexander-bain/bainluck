import SwiftUI
import UIKit
import XCTest
@testable import Bain_Luck

@MainActor
final class NBAHeadlinesSat2ATests: XCTestCase {

    private let fixedNow = ISO8601DateFormatter().date(from: "2026-11-14T18:00:00Z")!

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

    private func nbaBeforeFixture(
        commenceTime: String = "2026-11-15T01:00:00Z",
        includeProjectedScores: Bool = true
    ) throws -> EventDetail {
        let projFields = includeProjectedScores ? """
            "projected_home_score": 112.5,
            "projected_away_score": 116.5,
        """ : ""
        return try decodeEvent("""
        {
          "id": 9127201,
          "sport": "basketball_nba",
          "home_team": "Milwaukee Bucks",
          "away_team": "Boston Celtics",
          "commence_time": "\(commenceTime)",
          "status": "scheduled",
          "home_team_data": {
            "abbreviation": "MIL",
            "primary_color": "#00471B",
            "record": "6-6"
          },
          "away_team_data": {
            "abbreviation": "BOS",
            "primary_color": "#007A33",
            "record": "9-3"
          },
          "current_odds": {
            \(projFields)
            "home_probability": 0.392,
            "away_probability": 0.608,
            "home_rendered_percent": 39,
            "away_rendered_percent": 61,
            "updated_at": "2026-11-14T17:58:00Z"
          },
          "opening_odds": {
            "home_probability": 0.42,
            "away_probability": 0.58,
            "home_rendered_percent": 42,
            "away_rendered_percent": 58
          },
          "hero_probability": 0.392,
          "hero_probability_away": 0.608,
          "hero_probability_source": "blend",
          "hero_probability_observed_at": "2026-11-14T17:58:00Z",
          "espn": {
            "broadcast": "ESPN"
          },
          "win_probability_sources": {
            "betting": { "value": 0.39, "display_name": "Sportsbooks" },
            "kalshi": { "value": 0.395, "display_name": "Kalshi" },
            "polymarket": { "value": 0.39, "display_name": "Polymarket" }
          },
          "source_mark": {
            "state": "blend",
            "sources": [
              { "key": "kalshi", "name": "Kalshi", "probability": 0.395, "observed_at": "2026-11-14T17:58:00Z" },
              { "key": "polymarket", "name": "Polymarket", "probability": 0.39, "observed_at": "2026-11-14T17:57:50Z" },
              { "key": "betting", "name": "Sportsbooks", "probability": 0.39, "count": 5, "observed_at": "2026-11-14T17:57:30Z" }
            ]
          }
        }
        """)
    }

    private func nbaAfterFixture() throws -> EventDetail {
        try decodeEvent("""
        {
          "id": 9127202,
          "sport": "basketball_nba",
          "home_team": "New York Knicks",
          "away_team": "Cleveland Cavaliers",
          "commence_time": "2026-11-13T00:30:00Z",
          "completed_at": "2026-11-13T03:02:00Z",
          "status": "completed",
          "home_score": 107,
          "away_score": 115,
          "hero_settled_result": "away",
          "home_team_data": {
            "abbreviation": "NYK",
            "primary_color": "#006BB6",
            "record": "7-5"
          },
          "away_team_data": {
            "abbreviation": "CLE",
            "primary_color": "#860038",
            "record": "11-1"
          },
          "prematch_odds": {
            "home_probability": 0.65,
            "away_probability": 0.35,
            "home_rendered_percent": 65,
            "away_rendered_percent": 35,
            "source": "blend"
          },
          "pregame_projection": {
            "kind": "last_before_scheduled_start",
            "boundary": "scheduled_start",
            "boundary_at": "2026-11-13T00:30:00Z",
            "source": "sportsbooks",
            "basis": "consensus_spread_total",
            "unit": "points",
            "period": "full_game",
            "bookmaker_count": 5,
            "projected_home_score": 113.5,
            "projected_away_score": 109.5,
            "earliest_captured_at": "2026-11-12T22:00:00Z",
            "latest_captured_at": "2026-11-13T00:25:00Z"
          },
          "source_mark": {
            "state": "blend",
            "sources": [
              { "key": "kalshi", "name": "Kalshi", "probability": 0.65, "observed_at": "2026-11-13T00:28:00Z" },
              { "key": "polymarket", "name": "Polymarket", "probability": 0.65, "observed_at": "2026-11-13T00:27:50Z" },
              { "key": "betting", "name": "Sportsbooks", "probability": 0.65, "count": 5, "observed_at": "2026-11-13T00:27:00Z" }
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
        return try decodeHistory("""
        {
          "event_id": \(event.id),
          "home_team": "\(event.homeTeam)",
          "away_team": "\(event.awayTeam)",
          "history": [
            { "timestamp": "2026-11-13T00:30:00Z", "home_probability": \(startHome), "away_probability": \(startAway), "source": "aggregate" },
            { "timestamp": "2026-11-13T01:45:00Z", "home_probability": \(midHome), "away_probability": \(midAway), "source": "aggregate" },
            { "timestamp": "2026-11-13T03:00:00Z", "home_probability": \(endHome), "away_probability": \(endAway), "source": "aggregate" }
          ]
        }
        """)
    }

    func testNBABeforeGameUsesWholePercentProjChanceColumnsAndPlainTimeWithoutCountdownCapsule() throws {
        let event = try nbaBeforeFixture()
        XCTAssertEqual(EventSportHeadlines12472.kind(for: event, now: fixedNow), .nbaBeforeGame)

        for streaming in [false, true] {
            let model = try XCTUnwrap(
                EventSportHeadlines12472.resolve(
                    event: event,
                    awayFullName: event.awayTeam,
                    homeFullName: event.homeTeam,
                    liveStatusText: nil,
                    hasScore: false,
                    numberStreams: streaming,
                    now: fixedNow
                )
            )
            XCTAssertEqual(model.kind, .nbaBeforeGame)
            XCTAssertEqual(model.leagueLabel, "NBA")
            XCTAssertNil(model.liveBadgeText, "before a game must never draw a countdown or live capsule")
            XCTAssertEqual(
                model.pregameColumnHeaders,
                EventSportHeadlines12472.PregameColumnHeaders(projected: "Proj.", chance: "Chance")
            )
            XCTAssertEqual(model.away.shortName, "Celtics")
            XCTAssertEqual(model.away.record, "9-3")
            XCTAssertEqual(model.away.pregameProjectedNumberText, "116.5")
            XCTAssertEqual(model.away.winChanceText, "61%", "NBA before a game must always use whole percent")

            XCTAssertEqual(model.home.shortName, "Bucks")
            XCTAssertEqual(model.home.record, "6-6")
            XCTAssertEqual(model.home.pregameProjectedNumberText, "112.5")
            XCTAssertEqual(model.home.winChanceText, "39%", "NBA before a game must always use whole percent")
            XCTAssertTrue(model.showsEkg)
            XCTAssertTrue(model.showsBottomBar)
            XCTAssertTrue(model.stacksRecordUnderName)
        }

        let underHour = try nbaBeforeFixture(commenceTime: "2026-11-14T18:42:00Z")
        let countdownModel = try XCTUnwrap(
            EventSportHeadlines12472.resolve(
                event: underHour,
                awayFullName: underHour.awayTeam,
                homeFullName: underHour.homeTeam,
                liveStatusText: nil,
                hasScore: false,
                numberStreams: false,
                now: fixedNow
            )
        )
        XCTAssertEqual(countdownModel.plainMetaText, "NBA · In 42m · ESPN")
        XCTAssertNil(countdownModel.liveBadgeText)

        let noProj = try nbaBeforeFixture(includeProjectedScores: false)
        let noProjModel = try XCTUnwrap(
            EventSportHeadlines12472.resolve(
                event: noProj,
                awayFullName: noProj.awayTeam,
                homeFullName: noProj.homeTeam,
                liveStatusText: nil,
                hasScore: false,
                numberStreams: true,
                now: fixedNow
            )
        )
        XCTAssertEqual(
            noProjModel.pregameColumnHeaders,
            EventSportHeadlines12472.PregameColumnHeaders(projected: nil, chance: "Chance")
        )
        XCTAssertNil(noProjModel.away.pregameProjectedNumberText)
        XCTAssertEqual(noProjModel.away.winChanceText, "61%")
    }

    func testNBAAfterGameUsesAlignedPregameFinalColumnsWinnerCheckAndQualifiedProjOnce() throws {
        let event = try nbaAfterFixture()
        XCTAssertEqual(EventSportHeadlines12472.kind(for: event, now: fixedNow), .nbaAfterGame)

        let model = try XCTUnwrap(
            EventSportHeadlines12472.resolve(
                event: event,
                awayFullName: event.awayTeam,
                homeFullName: event.homeTeam,
                liveStatusText: nil,
                hasScore: true,
                numberStreams: false,
                now: fixedNow
            )
        )
        XCTAssertEqual(model.kind, .nbaAfterGame)
        XCTAssertTrue(model.plainMetaText?.hasPrefix("NBA · Final") == true)
        XCTAssertFalse(model.plainMetaText?.localizedCaseInsensitiveContains("settled") ?? false)
        XCTAssertEqual(
            model.finalColumnHeaders,
            EventSportHeadlines12472.FinalColumnHeaders(pregame: "Pregame", finalLabel: "Final")
        )
        XCTAssertEqual(model.away.shortName, "Cavaliers")
        XCTAssertEqual(model.away.won, true)
        XCTAssertEqual(model.away.pregameChanceText, "35%")
        XCTAssertEqual(model.away.finalResultText, "115")
        XCTAssertEqual(model.away.secondarySublineText, "11-1 · Proj. 110")

        XCTAssertEqual(model.home.shortName, "Knicks")
        XCTAssertEqual(model.home.won, false)
        XCTAssertEqual(model.home.pregameChanceText, "65%")
        XCTAssertEqual(model.home.finalResultText, "107")
        XCTAssertEqual(model.home.secondarySublineText, "7-5 · Proj. 114")

        XCTAssertFalse(model.away.secondarySublineText?.localizedCaseInsensitiveContains("pregame") ?? false)
        XCTAssertFalse(model.home.secondarySublineText?.localizedCaseInsensitiveContains("pregame") ?? false)
        XCTAssertFalse(model.showsBottomBar)
        XCTAssertFalse(model.showsEkg)
    }

    func testNBABeforeAndAfterFitAt390AndAccessibility2AndExport390pxRenders() async throws {
        let nbaBefore = try nbaBeforeFixture()
        let nbaAfter = try nbaAfterFixture()

        func makeCard(_ event: EventDetail, hasScore: Bool) throws -> EventSportHeadlineCard12472 {
            let model = try XCTUnwrap(
                EventSportHeadlines12472.resolve(
                    event: event,
                    awayFullName: event.awayTeam,
                    homeFullName: event.homeTeam,
                    liveStatusText: nil,
                    hasScore: hasScore,
                    numberStreams: false,
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
                liveUpdateStatus: .awaitingUpdate,
                displayAsOf: fixedNow,
                updateStream: LiveUpdateStream(),
                showUpdateStream: .constant(false),
                showProbabilityDetails: .constant(false),
                priceStreamingEligible: false,
                lastReceivedAt: fixedNow,
                confirmedAt: fixedNow,
                revealForecast: nil
            )
        }

        let beforeCard = try makeCard(nbaBefore, hasScore: false)
        let afterCard = try makeCard(nbaAfter, hasScore: true)

        for card in [beforeCard, afterCard] {
            for dt in [DynamicTypeSize.large, .accessibility2] {
                let host = hostForMeasurement(card.frame(width: 358), at: dt)
                let fitted = host.sizeThatFits(in: CGSize(width: 358, height: 1000))
                XCTAssertLessThanOrEqual(fitted.width, 358.5)
                XCTAssertGreaterThan(fitted.height, 80)
            }
        }

        if let outDir = ProcessInfo.processInfo.environment["EXPORT_SAT2A_NBA_RENDERS_DIR"],
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
                try await makeFullPage(nbaBefore, startHome: 0.42, endHome: 0.392),
                size: CGSize(width: 390, height: 852),
                to: dirURL.appendingPathComponent("sat2a-nba-before-390x852.png")
            )
            try await writeHostedPNG(
                try await makeFullPage(nbaAfter, startHome: 0.65, endHome: 0.0),
                size: CGSize(width: 390, height: 852),
                to: dirURL.appendingPathComponent("sat2a-nba-after-390x852.png")
            )

            let sheet = VStack(alignment: .leading, spacing: 14) {
                VStack(alignment: .leading, spacing: 5) {
                    Text("NBA Before · Proj. & Chance Columns, Whole %, No Countdown Capsule")
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(.secondary)
                    beforeCard
                }
                VStack(alignment: .leading, spacing: 5) {
                    Text("NBA After · Two Rows, Pregame & Final Aligned, Winner ✓")
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(.secondary)
                    afterCard
                }
            }
            .padding(16)
            .frame(width: 390)
            .background(Color(uiColor: .systemGroupedBackground))

            let sheetHost = hostForMeasurement(sheet.environment(\.colorScheme, .light), at: .large)
            let sheetHeight = ceil(sheetHost.sizeThatFits(in: CGSize(width: 390, height: 1600)).height)
            try await writeHostedPNG(
                sheet,
                size: CGSize(width: 390, height: sheetHeight),
                to: dirURL.appendingPathComponent("sat2a-nba-before-after-sheet-390.png")
            )
        }
    }
}
