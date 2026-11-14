import SwiftUI
import UIKit
import XCTest
@testable import Bain_Luck

@MainActor
final class NCAAFHeadlinesSat2BTests: XCTestCase {

    private let fixedNow = ISO8601DateFormatter().date(from: "2026-11-14T16:00:00Z")!

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

    private func ncaafBeforeFixture(
        sport: String = "americanfootball_ncaaf",
        commenceTime: String = "2026-11-14T20:30:00Z"
    ) throws -> EventDetail {
        try decodeEvent("""
        {
          "id": 9127211,
          "sport": "\(sport)",
          "home_team": "Texas A&M Aggies",
          "away_team": "Tennessee Volunteers",
          "commence_time": "\(commenceTime)",
          "status": "scheduled",
          "home_team_data": {
            "abbreviation": "TAMU",
            "primary_color": "#500000",
            "record": "7-2"
          },
          "away_team_data": {
            "abbreviation": "TENN",
            "primary_color": "#FF8200",
            "record": "8-1"
          },
          "current_odds": {
            "projected_home_score": 24.5,
            "projected_away_score": 27.5,
            "home_probability": 0.448,
            "away_probability": 0.552,
            "home_rendered_percent": 45,
            "away_rendered_percent": 55,
            "updated_at": "2026-11-14T15:58:00Z"
          },
          "opening_odds": {
            "home_probability": 0.47,
            "away_probability": 0.53,
            "home_rendered_percent": 47,
            "away_rendered_percent": 53
          },
          "hero_probability": 0.448,
          "hero_probability_away": 0.552,
          "hero_probability_source": "blend",
          "hero_probability_observed_at": "2026-11-14T15:58:00Z",
          "espn": {
            "broadcast": "ABC"
          },
          "win_probability_sources": {
            "betting": { "value": 0.45, "display_name": "Sportsbooks" },
            "kalshi": { "value": 0.445, "display_name": "Kalshi" },
            "polymarket": { "value": 0.45, "display_name": "Polymarket" }
          },
          "source_mark": {
            "state": "blend",
            "sources": [
              { "key": "kalshi", "name": "Kalshi", "probability": 0.445, "observed_at": "2026-11-14T15:58:00Z" },
              { "key": "polymarket", "name": "Polymarket", "probability": 0.45, "observed_at": "2026-11-14T15:57:50Z" },
              { "key": "betting", "name": "Sportsbooks", "probability": 0.45, "count": 5, "observed_at": "2026-11-14T15:57:30Z" }
            ]
          }
        }
        """)
    }

    private func ncaafDuringFixture(
        sport: String = "americanfootball_ncaaf",
        includeLiveProjection: Bool = true
    ) throws -> EventDetail {
        let liveProjJSON = includeLiveProjection ? """
            "live_projection": {
              "kind": "in_play",
              "boundary": "commence_time",
              "boundary_at": "2026-11-14T14:30:00Z",
              "source": "sportsbooks",
              "basis": "consensus_spread_total",
              "unit": "points",
              "period": "full_game",
              "bookmaker_count": 5,
              "projected_home_score": 27.5,
              "projected_away_score": 30.5,
              "earliest_confirmed_at": "2026-11-14T15:10:00Z",
              "latest_captured_at": "2026-11-14T15:59:00Z"
            },
        """ : ""
        return try decodeEvent("""
        {
          "id": 9127212,
          "sport": "\(sport)",
          "home_team": "Georgia Bulldogs",
          "away_team": "Ole Miss Rebels",
          "commence_time": "2026-11-14T14:30:00Z",
          "status": "live",
          "home_score": 17,
          "away_score": 21,
          "home_team_data": {
            "abbreviation": "UGA",
            "primary_color": "#BA0C2F",
            "record": "8-1"
          },
          "away_team_data": {
            "abbreviation": "MISS",
            "primary_color": "#14213D",
            "record": "8-2"
          },
          "current_odds": {
            \(liveProjJSON)
            "home_probability": 0.384,
            "away_probability": 0.616,
            "home_rendered_percent": 38,
            "away_rendered_percent": 62,
            "updated_at": "2026-11-14T15:59:30Z"
          },
          "prematch_odds": {
            "home_probability": 0.56,
            "away_probability": 0.44,
            "home_rendered_percent": 56,
            "away_rendered_percent": 44,
            "source": "blend"
          },
          "opening_odds": {
            "home_probability": 0.56,
            "away_probability": 0.44,
            "home_rendered_percent": 56,
            "away_rendered_percent": 44
          },
          "hero_probability": 0.384,
          "hero_probability_away": 0.616,
          "hero_probability_source": "blend",
          "hero_probability_observed_at": "2026-11-14T15:59:30Z",
          "espn": {
            "period": "3rd Quarter",
            "game_clock": "6:42",
            "broadcast": "ABC"
          },
          "source_mark": {
            "state": "blend",
            "sources": [
              { "key": "kalshi", "name": "Kalshi", "probability": 0.385, "observed_at": "2026-11-14T15:59:30Z" },
              { "key": "polymarket", "name": "Polymarket", "probability": 0.38, "observed_at": "2026-11-14T15:59:20Z" },
              { "key": "betting", "name": "Sportsbooks", "probability": 0.385, "count": 5, "observed_at": "2026-11-14T15:59:10Z" }
            ]
          }
        }
        """)
    }

    private func ncaafAfterFixture() throws -> EventDetail {
        try decodeEvent("""
        {
          "id": 9127213,
          "sport": "americanfootball_ncaaf",
          "home_team": "LSU Tigers",
          "away_team": "Alabama Crimson Tide",
          "commence_time": "2026-11-08T00:30:00Z",
          "completed_at": "2026-11-08T04:05:00Z",
          "status": "completed",
          "home_score": 13,
          "away_score": 42,
          "hero_settled_result": "away",
          "home_team_data": {
            "abbreviation": "LSU",
            "primary_color": "#461D7C",
            "record": "6-3"
          },
          "away_team_data": {
            "abbreviation": "ALA",
            "primary_color": "#9E1B32",
            "record": "8-2"
          },
          "prematch_odds": {
            "home_probability": 0.44,
            "away_probability": 0.56,
            "home_rendered_percent": 44,
            "away_rendered_percent": 56,
            "source": "blend"
          },
          "pregame_projection": {
            "kind": "last_before_scheduled_start",
            "boundary": "scheduled_start",
            "boundary_at": "2026-11-08T00:30:00Z",
            "source": "sportsbooks",
            "basis": "consensus_spread_total",
            "unit": "points",
            "period": "full_game",
            "bookmaker_count": 5,
            "projected_home_score": 27.5,
            "projected_away_score": 30.5,
            "earliest_captured_at": "2026-11-07T20:00:00Z",
            "latest_captured_at": "2026-11-08T00:25:00Z"
          },
          "source_mark": {
            "state": "blend",
            "sources": [
              { "key": "kalshi", "name": "Kalshi", "probability": 0.44, "observed_at": "2026-11-08T00:28:00Z" },
              { "key": "polymarket", "name": "Polymarket", "probability": 0.44, "observed_at": "2026-11-08T00:27:50Z" },
              { "key": "betting", "name": "Sportsbooks", "probability": 0.44, "count": 5, "observed_at": "2026-11-08T00:27:00Z" }
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
            t1 = fmt.string(from: baseDate.addingTimeInterval(2_700))
            t2 = fmt.string(from: baseDate.addingTimeInterval(5_100))
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

    func testNCAAFBeforeDuringAndAfterAdoptCompactHeadlineRules() throws {
        let before = try ncaafBeforeFixture()
        XCTAssertEqual(EventSportHeadlines12472.kind(for: before, now: fixedNow), .ncaafBeforeGame)

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
            XCTAssertEqual(model.leagueLabel, "NCAAF")
            XCTAssertNil(model.liveBadgeText)
            XCTAssertEqual(
                model.pregameColumnHeaders,
                EventSportHeadlines12472.PregameColumnHeaders(projected: "Proj.", chance: "Chance")
            )
            XCTAssertEqual(model.away.shortName, "Volunteers")
            XCTAssertEqual(model.away.pregameProjectedNumberText, "27.5")
            XCTAssertEqual(model.away.winChanceText, "55%")
            XCTAssertEqual(model.home.shortName, "Aggies")
            XCTAssertEqual(model.home.pregameProjectedNumberText, "24.5")
            XCTAssertEqual(model.home.winChanceText, "45%")
        }

        let fcsBefore = try ncaafBeforeFixture(sport: "americanfootball_ncaaf_fcs")
        let fcsModel = try XCTUnwrap(
            EventSportHeadlines12472.resolve(
                event: fcsBefore,
                awayFullName: fcsBefore.awayTeam,
                homeFullName: fcsBefore.homeTeam,
                liveStatusText: nil,
                hasScore: false,
                numberStreams: false,
                now: fixedNow
            )
        )
        XCTAssertEqual(fcsModel.leagueLabel, "NCAAF FCS")

        let during = try ncaafDuringFixture()
        XCTAssertEqual(EventSportHeadlines12472.kind(for: during, now: fixedNow), .ncaafDuringGame)
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
        XCTAssertEqual(liveModel.leagueLabel, "NCAAF")
        XCTAssertEqual(
            liveModel.liveColumnHeaders,
            EventSportHeadlines12472.LiveColumnHeaders(score: "Score", pregame: "Pregame", now: "Now")
        )
        XCTAssertEqual(liveModel.away.shortName, "Rebels")
        XCTAssertEqual(liveModel.away.projectedText, "Proj. 30.5")
        XCTAssertEqual(liveModel.away.liveScore, 21)
        XCTAssertEqual(liveModel.away.pregameChanceText, "44%")
        XCTAssertEqual(liveModel.away.winChanceText, "61.6%")
        XCTAssertEqual(liveModel.home.shortName, "Bulldogs")
        XCTAssertEqual(liveModel.home.projectedText, "Proj. 27.5")
        XCTAssertEqual(liveModel.home.liveScore, 17)
        XCTAssertEqual(liveModel.home.pregameChanceText, "56%")
        XCTAssertEqual(liveModel.home.winChanceText, "38.4%")

        // When live projection is absent: NCAAF stacks team records under short names,
        // while NBA live preserves `record == nil` (`stacksRecordUnderName == false`).
        let duringNoProj = try ncaafDuringFixture(includeLiveProjection: false)
        let liveNoProjModel = try XCTUnwrap(
            EventSportHeadlines12472.resolve(
                event: duringNoProj,
                awayFullName: duringNoProj.awayTeam,
                homeFullName: duringNoProj.homeTeam,
                liveStatusText: "Q3 6:42",
                hasScore: true,
                numberStreams: true,
                now: fixedNow
            )
        )
        XCTAssertTrue(liveNoProjModel.stacksRecordUnderName)
        XCTAssertNil(liveNoProjModel.away.projectedText)
        XCTAssertEqual(liveNoProjModel.away.record, "8-2")
        XCTAssertEqual(liveNoProjModel.home.record, "8-1")

        let nbaLiveNoProj = try ncaafDuringFixture(sport: "basketball_nba", includeLiveProjection: false)
        let nbaLiveNoProjModel = try XCTUnwrap(
            EventSportHeadlines12472.resolve(
                event: nbaLiveNoProj,
                awayFullName: nbaLiveNoProj.awayTeam,
                homeFullName: nbaLiveNoProj.homeTeam,
                liveStatusText: "Q3 6:42",
                hasScore: true,
                numberStreams: true,
                now: fixedNow
            )
        )
        XCTAssertFalse(nbaLiveNoProjModel.stacksRecordUnderName)
        XCTAssertNil(nbaLiveNoProjModel.away.record)
        XCTAssertNil(nbaLiveNoProjModel.home.record)

        let after = try ncaafAfterFixture()
        XCTAssertEqual(EventSportHeadlines12472.kind(for: after, now: fixedNow), .ncaafAfterGame)
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
        XCTAssertTrue(finalModel.plainMetaText?.hasPrefix("NCAAF · Final") == true)
        XCTAssertEqual(
            finalModel.finalColumnHeaders,
            EventSportHeadlines12472.FinalColumnHeaders(pregame: "Pregame", finalLabel: "Final")
        )
        XCTAssertEqual(finalModel.away.shortName, "Crimson Tide")
        XCTAssertEqual(finalModel.away.won, true)
        XCTAssertEqual(finalModel.away.pregameChanceText, "56%")
        XCTAssertEqual(finalModel.away.finalResultText, "42")
        XCTAssertEqual(finalModel.away.secondarySublineText, "8-2 · Proj. 31")
        XCTAssertEqual(finalModel.home.shortName, "Tigers")
        XCTAssertEqual(finalModel.home.won, false)
        XCTAssertEqual(finalModel.home.pregameChanceText, "44%")
        XCTAssertEqual(finalModel.home.finalResultText, "13")
        XCTAssertEqual(finalModel.home.secondarySublineText, "6-3 · Proj. 28")
    }

    func testNCAAFAllStatesFitAt390AndAccessibility2AndExport390pxRenders() async throws {
        let before = try ncaafBeforeFixture()
        let during = try ncaafDuringFixture()
        let after = try ncaafAfterFixture()

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

        if let outDir = ProcessInfo.processInfo.environment["EXPORT_SAT2B_NCAAF_RENDERS_DIR"],
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
                try await makeFullPage(before, startHome: 0.47, endHome: 0.448),
                size: CGSize(width: 390, height: 852),
                to: dirURL.appendingPathComponent("sat2b-ncaaf-before-390x852.png")
            )
            try await writeHostedPNG(
                try await makeFullPage(during, startHome: 0.56, endHome: 0.384),
                size: CGSize(width: 390, height: 852),
                to: dirURL.appendingPathComponent("sat2b-ncaaf-during-390x852.png")
            )
            try await writeHostedPNG(
                try await makeFullPage(after, startHome: 0.44, endHome: 0.0),
                size: CGSize(width: 390, height: 852),
                to: dirURL.appendingPathComponent("sat2b-ncaaf-after-390x852.png")
            )

            let sheet = VStack(alignment: .leading, spacing: 14) {
                VStack(alignment: .leading, spacing: 5) {
                    Text("NCAAF Before · Proj. & Chance Columns, Whole %, No Countdown Capsule")
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(.secondary)
                    beforeCard
                }
                VStack(alignment: .leading, spacing: 5) {
                    Text("NCAAF During · Live Score, Pregame & Now + Live Proj. Once")
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(.secondary)
                    duringCard
                }
                VStack(alignment: .leading, spacing: 5) {
                    Text("NCAAF After · Aligned Pregame & Final, Winner ✓")
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
                to: dirURL.appendingPathComponent("sat2b-ncaaf-all-states-sheet-390.png")
            )
        }
    }
}
