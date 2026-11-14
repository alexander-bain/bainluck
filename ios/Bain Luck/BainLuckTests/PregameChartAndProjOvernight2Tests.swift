import SwiftUI
import UIKit
import XCTest
@testable import Bain_Luck

@MainActor
final class PregameChartAndProjOvernight2Tests: XCTestCase {

    private let fixedNow = ISO8601DateFormatter().date(from: "2026-11-13T18:00:00Z")!

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
                from: Data(#"{"event_id":\#(eventId),"markets":[]}"#.utf8)
            )
        }
        func fetchTeamProgression(eventId: Int) async throws -> TeamProgressionResponse {
            try JSONDecoder().decode(TeamProgressionResponse.self, from: Data(#"{"home":null,"away":null}"#.utf8))
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

    // MARK: - 1. No "Since Start" before a game

    func testSinceStartNeverOfferedBeforeGameStarts() throws {
        let futureKickoff = fixedNow.addingTimeInterval(2 * 3600)
        let pastKickoff = fixedNow.addingTimeInterval(-1800)

        XCTAssertFalse(
            OddsChartView.gameHasStarted(status: "scheduled", commenceTime: futureKickoff, now: fixedNow),
            "scheduled pregame fixture has not started"
        )
        XCTAssertFalse(
            OddsChartView.gameHasStarted(status: "live", commenceTime: futureKickoff, history: nil, now: fixedNow),
            "premature live flag ahead of kickoff with no observed period has not started"
        )
        XCTAssertFalse(
            OddsChartView.offersSinceStart(isGameStarted: false, kickoff: futureKickoff, now: fixedNow)
        )
        XCTAssertFalse(
            OddsChartView.offersSinceStart(isGameStarted: true, kickoff: futureKickoff, now: fixedNow),
            "even if started flag is true, future kickoff cannot offer Since Start"
        )

        // Started / completed games with reached kickoff continue offering Since Start
        XCTAssertTrue(
            OddsChartView.gameHasStarted(status: "live", commenceTime: pastKickoff, now: fixedNow)
        )
        XCTAssertTrue(
            OddsChartView.offersSinceStart(isGameStarted: true, kickoff: pastKickoff, now: fixedNow)
        )
    }

    // MARK: - 2. Prominent Pregame Projected Final Columns

    func testNFLBeforeGamePromotesProjectedFinalIntoAlignedColumnBesideChance() throws {
        let nfl = try decodeEvent("""
        {
          "id": 9124721,
          "sport": "americanfootball_nfl",
          "home_team": "Cincinnati Bengals",
          "away_team": "Pittsburgh Steelers",
          "commence_time": "2026-11-15T18:00:00Z",
          "status": "scheduled",
          "home_team_data": { "abbreviation": "CIN", "primary_color": "#FB4F14", "record": "5-4" },
          "away_team_data": { "abbreviation": "PIT", "primary_color": "#101820", "record": "6-2" },
          "current_odds": {
            "home_probability": 0.658,
            "away_probability": 0.342,
            "home_rendered_percent": 66,
            "away_rendered_percent": 34,
            "projected_home_score": 24.5,
            "projected_away_score": 20.0,
            "updated_at": "2026-11-13T17:58:00Z"
          },
          "hero_probability": 0.658,
          "hero_probability_away": 0.342,
          "hero_probability_source": "blend",
          "espn": { "broadcast": "CBS" },
          "source_mark": {
            "state": "blend",
            "sources": [
              { "key": "kalshi", "name": "Kalshi", "probability": 0.65, "observed_at": "2026-11-13T17:58:00Z" },
              { "key": "betting", "name": "Sportsbooks", "probability": 0.66, "count": 6, "observed_at": "2026-11-13T17:56:00Z" }
            ]
          }
        }
        """)

        let model = try XCTUnwrap(
            EventSportHeadlines12472.resolve(
                event: nfl,
                awayFullName: nfl.awayTeam,
                homeFullName: nfl.homeTeam,
                liveStatusText: nil,
                hasScore: false,
                numberStreams: false,
                now: fixedNow
            )
        )
        XCTAssertEqual(
            model.pregameColumnHeaders,
            EventSportHeadlines12472.PregameColumnHeaders(projected: "Proj.", chance: "Chance")
        )
        XCTAssertEqual(model.away.pregameProjectedNumberText, "20.0")
        XCTAssertEqual(model.home.pregameProjectedNumberText, "24.5")
        XCTAssertEqual(model.away.winChanceText, "34%")
        XCTAssertEqual(model.home.winChanceText, "66%")
    }

    func testNFLBeforeGameWithoutAdmittedProjectionOmitsPregameProjectedColumn() throws {
        let nflNoProj = try decodeEvent("""
        {
          "id": 9124729,
          "sport": "americanfootball_nfl",
          "home_team": "Cincinnati Bengals",
          "away_team": "Pittsburgh Steelers",
          "commence_time": "2026-11-15T18:00:00Z",
          "status": "scheduled",
          "current_odds": {
            "home_probability": 0.66,
            "away_probability": 0.34,
            "home_rendered_percent": 66,
            "away_rendered_percent": 34,
            "updated_at": "2026-11-13T17:58:00Z"
          },
          "hero_probability": 0.66,
          "hero_probability_away": 0.34,
          "hero_probability_source": "blend"
        }
        """)

        let model = try XCTUnwrap(
            EventSportHeadlines12472.resolve(
                event: nflNoProj,
                awayFullName: nflNoProj.awayTeam,
                homeFullName: nflNoProj.homeTeam,
                liveStatusText: nil,
                hasScore: false,
                numberStreams: false,
                now: fixedNow
            )
        )
        XCTAssertNil(model.pregameColumnHeaders)
        XCTAssertNil(model.away.pregameProjectedNumberText)
        XCTAssertNil(model.home.pregameProjectedNumberText)
    }

    // MARK: - 3. Taller Game-Page Charts & 390px Renders

    func testGamePageChartsAreTallerAndExport390pxRenders() async throws {
        XCTAssertEqual(OddsChartView.phoneChartHeight, 340)
        XCTAssertEqual(ProjectedFinalPointsChartView.inlinePlotHeight, 300)

        let nflEvent = try decodeEvent("""
        {
          "id": 9124721,
          "sport": "americanfootball_nfl",
          "home_team": "Cincinnati Bengals",
          "away_team": "Pittsburgh Steelers",
          "commence_time": "2026-11-15T18:00:00Z",
          "status": "scheduled",
          "home_team_data": { "abbreviation": "CIN", "primary_color": "#FB4F14", "record": "5-4" },
          "away_team_data": { "abbreviation": "PIT", "primary_color": "#101820", "record": "6-2" },
          "current_odds": {
            "home_probability": 0.658,
            "away_probability": 0.342,
            "home_rendered_percent": 66,
            "away_rendered_percent": 34,
            "projected_home_score": 24.5,
            "projected_away_score": 20.0,
            "updated_at": "2026-11-13T17:58:00Z"
          },
          "opening_odds": {
            "home_probability": 0.62,
            "away_probability": 0.38,
            "home_rendered_percent": 62,
            "away_rendered_percent": 38
          },
          "hero_probability": 0.658,
          "hero_probability_away": 0.342,
          "hero_probability_source": "blend",
          "hero_probability_observed_at": "2026-11-13T17:58:00Z",
          "espn": { "broadcast": "CBS" },
          "win_probability_sources": {
            "betting": { "value": 0.66, "display_name": "Sportsbooks" },
            "kalshi": { "value": 0.65, "display_name": "Kalshi" },
            "polymarket": { "value": 0.66, "display_name": "Polymarket" }
          },
          "source_mark": {
            "state": "blend",
            "sources": [
              { "key": "kalshi", "name": "Kalshi", "probability": 0.65, "observed_at": "2026-11-13T17:58:00Z" },
              { "key": "polymarket", "name": "Polymarket", "probability": 0.66, "observed_at": "2026-11-13T17:57:00Z" },
              { "key": "betting", "name": "Sportsbooks", "probability": 0.66, "count": 6, "observed_at": "2026-11-13T17:56:00Z" }
            ]
          }
        }
        """)

        let nflHistory = try decodeHistory("""
        {
          "event_id": 9124721,
          "home_team": "Cincinnati Bengals",
          "away_team": "Pittsburgh Steelers",
          "history": [
            { "timestamp": "2026-11-10T12:00:00Z", "home_probability": 0.62, "away_probability": 0.38, "source": "aggregate" },
            { "timestamp": "2026-11-11T12:00:00Z", "home_probability": 0.64, "away_probability": 0.36, "source": "aggregate" },
            { "timestamp": "2026-11-12T12:00:00Z", "home_probability": 0.65, "away_probability": 0.35, "source": "aggregate" },
            { "timestamp": "2026-11-13T17:58:00Z", "home_probability": 0.658, "away_probability": 0.342, "source": "aggregate" }
          ]
        }
        """)

        let nflModel = try XCTUnwrap(
            EventSportHeadlines12472.resolve(
                event: nflEvent,
                awayFullName: nflEvent.awayTeam,
                homeFullName: nflEvent.homeTeam,
                liveStatusText: nil,
                hasScore: false,
                numberStreams: false,
                now: fixedNow
            )
        )
        let nflColors = TeamTextContrast.cardColors(
            awayHex: nflEvent.awayTeamData?.primaryColor,
            homeHex: nflEvent.homeTeamData?.primaryColor
        )

        let nflCard = EventSportHeadlineCard12472(
            model: nflModel,
            colors: nflColors,
            ekgTracker: .empty,
            liveUpdateStatus: .awaitingUpdate,
            displayAsOf: fixedNow,
            updateStream: LiveUpdateStream(),
            showUpdateStream: .constant(false),
            showProbabilityDetails: .constant(false),
            priceStreamingEligible: true,
            lastReceivedAt: nil,
            confirmedAt: nil,
            revealForecast: nil
        )
        .frame(width: 358)

        let a11yHost = hostForMeasurement(nflCard, at: .accessibility2)
        let a11ySize = a11yHost.sizeThatFits(in: CGSize(width: 358, height: 2000))
        XCTAssertLessThanOrEqual(a11ySize.width, 358.5, "NFL pregame card with Proj. column must not bleed at .accessibility2")

        guard let rawDir = ProcessInfo.processInfo.environment["BUILDER_C_RENDER_DIR"], !rawDir.isEmpty else {
            return
        }
        let dirURL = URL(fileURLWithPath: rawDir, isDirectory: true)
        try FileManager.default.createDirectory(at: dirURL, withIntermediateDirectories: true)

        let nflVM = EventDetailViewModel(
            eventId: nflEvent.id,
            client: StubEventDetailProvider(detail: nflEvent, history: nflHistory)
        )
        await nflVM.load()
        nflVM.stopRefresh()

        let nflPage = NavigationStack {
            EventDetailView(eventId: nflEvent.id)
                .withLoadedEventForTest12278(nflEvent, viewModel: nflVM)
        }
        .environmentObject(PinManager())
        .environmentObject(NavigationCoordinator())
        .frame(width: 390, height: 852)
        .background(Color(uiColor: .systemGroupedBackground))

        let host = hostForMeasurement(nflPage.environment(\.colorScheme, .light), at: .large)
        host.overrideUserInterfaceStyle = .light
        host.view.frame = CGRect(origin: .zero, size: CGSize(width: 390, height: 852))
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
        let until = Date().addingTimeInterval(0.45)
        repeat {
            host.view.setNeedsLayout()
            host.view.layoutIfNeeded()
            RunLoop.current.run(until: Date().addingTimeInterval(0.015))
        } while Date() < until
        let fmt = UIGraphicsImageRendererFormat()
        fmt.scale = 3.0
        let pageImg = UIGraphicsImageRenderer(bounds: host.view.bounds, format: fmt).image { _ in
            _ = host.view.drawHierarchy(in: host.view.bounds, afterScreenUpdates: true)
        }
        if let png = pageImg.pngData() {
            try png.write(to: dirURL.appendingPathComponent("overnight2-nfl-before-page-390x852.png"))
        }

        // Also render the NBA pregame paired headline + NCAAF pregame headline + NFL a11y2 at 390px
        let nbaPregame = try decodeEvent("""
        {
          "id": 9124730,
          "sport": "basketball_nba",
          "home_team": "Boston Celtics",
          "away_team": "New York Knicks",
          "commence_time": "2026-11-15T00:30:00Z",
          "status": "scheduled",
          "home_team_data": { "abbreviation": "BOS", "primary_color": "#007A33", "record": "9-2" },
          "away_team_data": { "abbreviation": "NYK", "primary_color": "#F58426", "record": "7-4" },
          "current_odds": {
            "home_probability": 0.61,
            "away_probability": 0.39,
            "home_rendered_percent": 61,
            "away_rendered_percent": 39,
            "projected_home_score": 114.5,
            "projected_away_score": 109.0,
            "updated_at": "2026-11-13T17:58:00Z"
          },
          "hero_probability": 0.61,
          "hero_probability_away": 0.39,
          "hero_probability_source": "blend",
          "espn": { "broadcast": "ESPN" }
        }
        """)

        let ncaafPregame = try decodeEvent("""
        {
          "id": 9124731,
          "sport": "americanfootball_ncaaf",
          "home_team": "Texas A&M Aggies",
          "away_team": "Tennessee Volunteers",
          "commence_time": "2026-11-15T17:00:00Z",
          "status": "scheduled",
          "home_team_data": { "abbreviation": "TAMU", "primary_color": "#500000", "record": "6-3" },
          "away_team_data": { "abbreviation": "TENN", "primary_color": "#FF8200", "record": "7-2" },
          "current_odds": {
            "home_probability": 0.45,
            "away_probability": 0.55,
            "home_rendered_percent": 45,
            "away_rendered_percent": 55,
            "projected_home_score": 24.5,
            "projected_away_score": 27.5,
            "updated_at": "2026-11-13T17:58:00Z"
          },
          "hero_probability": 0.45,
          "hero_probability_away": 0.55,
          "hero_probability_source": "blend",
          "espn": { "broadcast": "ABC" }
        }
        """)

        let cardsComparison = VStack(alignment: .leading, spacing: 18) {
            VStack(alignment: .leading, spacing: 6) {
                Text("NFL Before a Game · Prominent Proj. & Chance columns")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.secondary)
                nflCard
            }
            VStack(alignment: .leading, spacing: 6) {
                Text("NBA Before a Game · Prominent Projected Final row")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.secondary)
                EventDetailView(eventId: nbaPregame.id)
                    .withLoadedEventForTest12278(nbaPregame)
                    .heroSectionForTest12278(nbaPregame)
                    .padding(14)
                    .background(Color.cardBackground, in: RoundedRectangle(cornerRadius: 16))
                    .frame(width: 358)
            }
            VStack(alignment: .leading, spacing: 6) {
                Text("NCAAF Before a Game · Prominent Proj. capsule")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.secondary)
                EventDetailView(eventId: ncaafPregame.id)
                    .withLoadedEventForTest12278(ncaafPregame)
                    .heroSectionForTest12278(ncaafPregame)
                    .frame(width: 358)
            }
            VStack(alignment: .leading, spacing: 6) {
                Text("NFL Before a Game · Accessibility (.accessibility2, 390pt)")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.secondary)
                nflCard.environment(\.dynamicTypeSize, .accessibility2)
            }
        }
        .padding(16)
        .frame(width: 390)
        .background(Color(uiColor: .systemGroupedBackground))
        .environmentObject(PinManager())
        .environmentObject(NavigationCoordinator())

        let renderer = ImageRenderer(content: cardsComparison.environment(\.colorScheme, .light))
        renderer.scale = 3.0
        renderer.proposedSize = ProposedViewSize(width: 390, height: nil)
        if let png = renderer.uiImage?.pngData() {
            try png.write(to: dirURL.appendingPathComponent("overnight2-pregame-projected-final-390.png"))
        }
    }
}
