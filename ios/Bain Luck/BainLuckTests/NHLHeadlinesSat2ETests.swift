import SwiftUI
import UIKit
import XCTest
@testable import Bain_Luck

@MainActor
final class NHLHeadlinesSat2ETests: XCTestCase {

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

    private func nhlBeforeFixture(commenceTime: String = "2026-11-15T00:00:00Z") throws -> EventDetail {
        try decodeEvent("""
        {
          "id": 9127251,
          "sport": "icehockey_nhl",
          "home_team": "Minnesota Wild",
          "away_team": "Boston Bruins",
          "commence_time": "\(commenceTime)",
          "status": "scheduled",
          "home_team_data": {
            "abbreviation": "MIN",
            "primary_color": "#154734",
            "record": "10-4-2"
          },
          "away_team_data": {
            "abbreviation": "BOS",
            "primary_color": "#FFB81C",
            "record": "8-7-2"
          },
          "current_odds": {
            "home_probability": 0.534,
            "away_probability": 0.466,
            "home_rendered_percent": 53,
            "away_rendered_percent": 47,
            "updated_at": "2026-11-14T14:48:00Z"
          },
          "opening_odds": {
            "home_probability": 0.51,
            "away_probability": 0.49,
            "home_rendered_percent": 51,
            "away_rendered_percent": 49
          },
          "hero_probability": 0.534,
          "hero_probability_away": 0.466,
          "hero_probability_source": "blend",
          "hero_probability_observed_at": "2026-11-14T14:48:00Z",
          "espn": {
            "broadcast": "ESPN+"
          },
          "win_probability_sources": {
            "betting": { "value": 0.535, "display_name": "Sportsbooks" },
            "kalshi": { "value": 0.53, "display_name": "Kalshi" },
            "polymarket": { "value": 0.535, "display_name": "Polymarket" }
          },
          "source_mark": {
            "state": "blend",
            "sources": [
              { "key": "kalshi", "name": "Kalshi", "probability": 0.53, "observed_at": "2026-11-14T14:48:00Z" },
              { "key": "polymarket", "name": "Polymarket", "probability": 0.535, "observed_at": "2026-11-14T14:47:50Z" },
              { "key": "betting", "name": "Sportsbooks", "probability": 0.535, "count": 5, "observed_at": "2026-11-14T14:47:30Z" }
            ]
          }
        }
        """)
    }

    private func nhlAfterFixture() throws -> EventDetail {
        try decodeEvent("""
        {
          "id": 9127252,
          "sport": "icehockey_nhl",
          "home_team": "Vegas Golden Knights",
          "away_team": "Nashville Predators",
          "commence_time": "2026-11-14T03:00:00Z",
          "completed_at": "2026-11-14T05:38:00Z",
          "status": "completed",
          "home_score": 4,
          "away_score": 2,
          "hero_settled_result": "home",
          "home_team_data": {
            "abbreviation": "VGK",
            "primary_color": "#B4975A",
            "record": "11-4-2"
          },
          "away_team_data": {
            "abbreviation": "NSH",
            "primary_color": "#FFB81C",
            "record": "9-7-1"
          },
          "prematch_odds": {
            "home_probability": 0.57,
            "away_probability": 0.43,
            "home_rendered_percent": 57,
            "away_rendered_percent": 43,
            "source": "blend"
          },
          "source_mark": {
            "state": "blend",
            "sources": [
              { "key": "kalshi", "name": "Kalshi", "probability": 0.57, "observed_at": "2026-11-14T02:58:00Z" },
              { "key": "polymarket", "name": "Polymarket", "probability": 0.57, "observed_at": "2026-11-14T02:57:50Z" },
              { "key": "betting", "name": "Sportsbooks", "probability": 0.57, "count": 5, "observed_at": "2026-11-14T02:57:00Z" }
            ]
          }
        }
        """)
    }

    private func makeHistory(
        event: EventDetail,
        startHome: Double,
        endHome: Double,
        projHome: Double? = nil,
        projAway: Double? = nil
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
            t1 = fmt.string(from: baseDate.addingTimeInterval(3_600))
            t2 = fmt.string(from: baseDate.addingTimeInterval(7_200))
        }
        let pmSpreadJSON: String = {
            guard let ph = projHome, let pa = projAway else { return "" }
            return """
              "pm_spread_data": {
                "projected_final": {
                  "home_score": \(ph),
                  "away_score": \(pa),
                  "spread_source": "kalshi"
                }
              },
            """
        }()
        return try decodeHistory("""
        {
          "event_id": \(event.id),
          "home_team": "\(event.homeTeam)",
          "away_team": "\(event.awayTeam)",
          \(pmSpreadJSON)
          "history": [
            { "timestamp": "\(t0)", "home_probability": \(startHome), "away_probability": \(startAway), "source": "aggregate" },
            { "timestamp": "\(t1)", "home_probability": \(midHome), "away_probability": \(midAway), "source": "aggregate" },
            { "timestamp": "\(t2)", "home_probability": \(endHome), "away_probability": \(endAway), "source": "aggregate" }
          ]
        }
        """)
    }

    func testNHLBeforeAndAfterAdoptCompactHeadlineRules() throws {
        let before = try nhlBeforeFixture()
        XCTAssertEqual(EventSportHeadlines12472.kind(for: before, now: fixedNow), .nhlBeforeGame)

        for streaming in [false, true] {
            let model = try XCTUnwrap(
                EventSportHeadlines12472.resolve(
                    event: before,
                    awayFullName: before.awayTeam,
                    homeFullName: before.homeTeam,
                    liveStatusText: nil,
                    hasScore: false,
                    numberStreams: streaming,
                    ladderHome: 3.5,
                    ladderAway: 2.7,
                    now: fixedNow
                )
            )
            XCTAssertEqual(model.leagueLabel, "NHL")
            XCTAssertNil(model.liveBadgeText)
            XCTAssertTrue(model.showsRowDivider)
            XCTAssertEqual(
                model.pregameColumnHeaders,
                EventSportHeadlines12472.PregameColumnHeaders(projected: "Proj.", chance: "Chance")
            )
            XCTAssertEqual(model.away.shortName, "Bruins")
            XCTAssertEqual(model.away.pregameProjectedNumberText, "2.7")
            XCTAssertEqual(model.away.winChanceText, "47%")
            XCTAssertEqual(model.home.shortName, "Wild")
            XCTAssertEqual(model.home.pregameProjectedNumberText, "3.5")
            XCTAssertEqual(model.home.winChanceText, "53%")
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

        let after = try nhlAfterFixture()
        XCTAssertEqual(EventSportHeadlines12472.kind(for: after, now: fixedNow), .nhlAfterGame)
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
        XCTAssertTrue(finalModel.plainMetaText?.hasPrefix("NHL · Final") == true)
        XCTAssertFalse(finalModel.plainMetaText?.localizedCaseInsensitiveContains("settled") == true)
        XCTAssertTrue(finalModel.showsRowDivider)
        XCTAssertFalse(finalModel.showsBottomBar)
        XCTAssertFalse(finalModel.showsEkg)
        XCTAssertEqual(
            finalModel.finalColumnHeaders,
            EventSportHeadlines12472.FinalColumnHeaders(pregame: "Pregame", finalLabel: "Final")
        )
        XCTAssertEqual(finalModel.away.shortName, "Predators")
        XCTAssertEqual(finalModel.away.won, false)
        XCTAssertEqual(finalModel.away.pregameChanceText, "43%")
        XCTAssertEqual(finalModel.away.finalResultText, "2")
        XCTAssertEqual(finalModel.away.secondarySublineText, "9-7-1")
        XCTAssertEqual(finalModel.home.shortName, "Golden Knights")
        XCTAssertEqual(finalModel.home.won, true)
        XCTAssertEqual(finalModel.home.pregameChanceText, "57%")
        XCTAssertEqual(finalModel.home.finalResultText, "4")
        XCTAssertEqual(finalModel.home.secondarySublineText, "11-4-2")
    }

    func testNHLBeforeAndAfterFitAt390AndAccessibility2AndExport390pxRenders() async throws {
        let before = try nhlBeforeFixture()
        let after = try nhlAfterFixture()

        func makeCard(
            _ event: EventDetail,
            hasScore: Bool,
            ladderHome: Double?,
            ladderAway: Double?
        ) throws -> EventSportHeadlineCard12472 {
            let model = try XCTUnwrap(
                EventSportHeadlines12472.resolve(
                    event: event,
                    awayFullName: event.awayTeam,
                    homeFullName: event.homeTeam,
                    liveStatusText: nil,
                    hasScore: hasScore,
                    numberStreams: false,
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

        let beforeCard = try makeCard(before, hasScore: false, ladderHome: 3.5, ladderAway: 2.7)
        let afterCard = try makeCard(after, hasScore: true, ladderHome: nil, ladderAway: nil)

        for card in [beforeCard, afterCard] {
            for dt in [DynamicTypeSize.large, .accessibility2] {
                let host = hostForMeasurement(card.frame(width: 358), at: dt)
                let fitted = host.sizeThatFits(in: CGSize(width: 358, height: 1000))
                XCTAssertLessThanOrEqual(fitted.width, 358.5)
                XCTAssertGreaterThan(fitted.height, 80)
            }
        }

        if let outDir = ProcessInfo.processInfo.environment["EXPORT_SAT2E_NHL_RENDERS_DIR"],
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
                projHome: Double? = nil,
                projAway: Double? = nil
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
                try await makeFullPage(before, startHome: 0.51, endHome: 0.534, projHome: 3.5, projAway: 2.7),
                size: CGSize(width: 390, height: 852),
                to: dirURL.appendingPathComponent("sat2e-nhl-before-390x852.png")
            )
            try await writeHostedPNG(
                try await makeFullPage(after, startHome: 0.57, endHome: 1.0),
                size: CGSize(width: 390, height: 852),
                to: dirURL.appendingPathComponent("sat2e-nhl-after-390x852.png")
            )

            let sheet = VStack(alignment: .leading, spacing: 14) {
                VStack(alignment: .leading, spacing: 5) {
                    Text("NHL Before · Proj. Goals & Chance Columns, Whole %, No Countdown Capsule")
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(.secondary)
                    beforeCard
                }
                VStack(alignment: .leading, spacing: 5) {
                    Text("NHL After · Aligned Pregame & Final, Winner ✓")
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
                to: dirURL.appendingPathComponent("sat2e-nhl-before-after-sheet-390.png")
            )
        }
    }
}
