import SwiftUI
import UIKit
import XCTest
@testable import Bain_Luck

@MainActor
final class EventSportHeadlines12472Tests: XCTestCase {

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

    private func nflPregameFixture(
        commenceTime: String = "2026-11-15T18:00:00Z",
        homeProb: Double = 0.658,
        homeRendered: Int = 66,
        awayRendered: Int = 34,
        startIsTbd: Bool = false,
        heroSource: String = "blend"
    ) throws -> EventDetail {
        let awayProb = ((1.0 - homeProb) * 1_000_000).rounded() / 1_000_000
        return try decodeEvent("""
        {
          "id": 9124721,
          "sport": "americanfootball_nfl",
          "home_team": "Cincinnati Bengals",
          "away_team": "Pittsburgh Steelers",
          "commence_time": "\(commenceTime)",
          "start_is_tbd": \(startIsTbd),
          "status": "scheduled",
          "home_team_data": {
            "abbreviation": "CIN",
            "primary_color": "#FB4F14",
            "record": "5-4"
          },
          "away_team_data": {
            "abbreviation": "PIT",
            "primary_color": "#101820",
            "record": "6-2"
          },
          "current_odds": {
            "home_probability": \(homeProb),
            "away_probability": \(awayProb),
            "home_rendered_percent": \(homeRendered),
            "away_rendered_percent": \(awayRendered),
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
          "hero_probability": \(homeProb),
          "hero_probability_away": \(awayProb),
          "hero_probability_source": "\(heroSource)",
          "hero_probability_observed_at": "2026-11-13T17:58:00Z",
          "espn": {
            "broadcast": "CBS"
          },
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
    }

    private func nbaLiveFixture(
        homeProb: Double = 0.588,
        includeServedPrematch: Bool = true,
        includeLiveProjection: Bool = true
    ) throws -> EventDetail {
        let awayProb = ((1.0 - homeProb) * 1_000_000).rounded() / 1_000_000
        let prematchJSON = includeServedPrematch ? """
          "prematch_odds": {
            "home_probability": 0.51,
            "away_probability": 0.49,
            "home_rendered_percent": 51,
            "away_rendered_percent": 49,
            "source": "kalshi"
          },
        """ : ""
        let liveProjJSON = includeLiveProjection ? """
            "live_projection": {
              "kind": "in_play",
              "boundary": "commence_time",
              "boundary_at": "2026-11-13T13:30:00Z",
              "source": "sportsbooks",
              "basis": "consensus_spread_total",
              "unit": "points",
              "period": "full_game",
              "bookmaker_count": 5,
              "projected_home_score": 105.0,
              "projected_away_score": 103.5,
              "earliest_confirmed_at": "2026-11-13T14:40:00Z",
              "latest_captured_at": "2026-11-13T14:59:00Z"
            },
        """ : ""
        return try decodeEvent("""
        {
          "id": 9124722,
          "sport": "basketball_nba",
          "home_team": "Philadelphia 76ers",
          "away_team": "Boston Celtics",
          "commence_time": "2026-11-13T13:30:00Z",
          "status": "live",
          "home_score": 100,
          "away_score": 98,
          "home_team_data": {
            "abbreviation": "PHI",
            "primary_color": "#006BB6",
            "record": "7-3"
          },
          "away_team_data": {
            "abbreviation": "BOS",
            "primary_color": "#007A33",
            "record": "8-2"
          },
          "current_odds": {
            \(liveProjJSON)
            "home_probability": \(homeProb),
            "away_probability": \(awayProb),
            "home_rendered_percent": 59,
            "away_rendered_percent": 41,
            "updated_at": "2026-11-13T17:59:30Z"
          },
          \(prematchJSON)
          "opening_odds": {
            "home_probability": 0.51,
            "away_probability": 0.49,
            "home_rendered_percent": 51,
            "away_rendered_percent": 49
          },
          "hero_probability": \(homeProb),
          "hero_probability_away": \(awayProb),
          "hero_probability_source": "blend",
          "hero_probability_observed_at": "2026-11-13T17:59:30Z",
          "espn": {
            "period": "4th Quarter",
            "game_clock": "2:14",
            "broadcast": "ESPN"
          },
          "win_probability_sources": {
            "betting": { "value": 0.59, "display_name": "Sportsbooks" },
            "kalshi": { "value": 0.585, "display_name": "Kalshi" },
            "polymarket": { "value": 0.59, "display_name": "Polymarket" }
          },
          "source_mark": {
            "state": "blend",
            "sources": [
              { "key": "kalshi", "name": "Kalshi", "probability": 0.585, "observed_at": "2026-11-13T17:59:30Z" },
              { "key": "polymarket", "name": "Polymarket", "probability": 0.59, "observed_at": "2026-11-13T17:59:20Z" },
              { "key": "betting", "name": "Sportsbooks", "probability": 0.59, "count": 5, "observed_at": "2026-11-13T17:59:10Z" }
            ]
          }
        }
        """)
    }

    // MARK: - Scope & Eligibility

    func testScopeAdoptsOnlyNFLBeforeGameAndNBADuringGame() throws {
        let nflBefore = try nflPregameFixture()
        XCTAssertEqual(EventSportHeadlines12472.kind(for: nflBefore, now: fixedNow), .nflBeforeGame)
        XCTAssertTrue(EventSportHeadlines12472.applies(to: nflBefore, now: fixedNow))

        var nflLive = nflBefore
        nflLive.status = "live"
        XCTAssertNil(EventSportHeadlines12472.kind(for: nflLive, now: fixedNow), "live NFL is not part of this slice")

        var nflFinal = nflBefore
        nflFinal.status = "completed"
        XCTAssertNil(EventSportHeadlines12472.kind(for: nflFinal, now: fixedNow), "finished NFL stays on its existing final card")

        let nflOpeningOnly = try nflPregameFixture(heroSource: "opening")
        XCTAssertNil(EventSportHeadlines12472.kind(for: nflOpeningOnly, now: fixedNow), "opening-only weeks keep OpeningLineHero")

        let nbaLive = try nbaLiveFixture()
        XCTAssertEqual(EventSportHeadlines12472.kind(for: nbaLive, now: fixedNow), .nbaDuringGame)
        XCTAssertTrue(EventSportHeadlines12472.applies(to: nbaLive, now: fixedNow))

        var nbaBefore = nbaLive
        nbaBefore.status = "scheduled"
        XCTAssertNil(EventSportHeadlines12472.kind(for: nbaBefore, now: fixedNow), "scheduled NBA is not part of this slice")

        var nbaFinal = nbaLive
        nbaFinal.status = "completed"
        XCTAssertNil(EventSportHeadlines12472.kind(for: nbaFinal, now: fixedNow))
    }

    private func resolveHeadline(
        _ event: EventDetail,
        hasScore: Bool,
        numberStreams: Bool
    ) -> EventSportHeadlines12472.Model? {
        EventSportHeadlines12472.resolve(
            event: event,
            awayFullName: event.awayTeam,
            homeFullName: event.homeTeam,
            liveStatusText: PeriodLabel.liveStatusText(
                period: event.espn?.period,
                gameClock: event.espn?.gameClock
            ),
            hasScore: hasScore,
            numberStreams: numberStreams,
            now: fixedNow
        )
    }

    // MARK: - NFL Before a Game Rules

    func testNFLBeforeGameShowsWholePercentUnlessNumberStreams() throws {
        let event = try nflPregameFixture(homeProb: 0.658, homeRendered: 66, awayRendered: 34)

        let nonStreaming = try XCTUnwrap(
            resolveHeadline(event, hasScore: false, numberStreams: false)
        )
        XCTAssertEqual(nonStreaming.away.winChanceText, "34%")
        XCTAssertEqual(nonStreaming.home.winChanceText, "66%")
        XCTAssertEqual(nonStreaming.away.projectedText, "Proj. 20.0")
        XCTAssertEqual(nonStreaming.home.projectedText, "Proj. 24.5")
        XCTAssertEqual(nonStreaming.away.record, "6-2")
        XCTAssertEqual(nonStreaming.home.record, "5-4")
        XCTAssertNil(nonStreaming.away.pregameChanceText)
        XCTAssertNil(nonStreaming.home.pregameChanceText)
        XCTAssertNil(nonStreaming.liveColumnHeaders)
        XCTAssertEqual(nonStreaming.sourceMark?.draws, true)

        let streaming = try XCTUnwrap(
            resolveHeadline(event, hasScore: false, numberStreams: true)
        )
        XCTAssertEqual(streaming.away.winChanceText, "34.2%")
        XCTAssertEqual(streaming.home.winChanceText, "65.8%")
    }

    func testNFLBeforeGameMetaUsesPlainDateWhenDaysAwayAndCountdownInsideLastHour() throws {
        let daysAway = try nflPregameFixture(commenceTime: "2026-11-15T18:00:00Z")
        let daysModel = try XCTUnwrap(
            resolveHeadline(daysAway, hasScore: false, numberStreams: false)
        )
        let metaDays = try XCTUnwrap(daysModel.plainMetaText)
        XCTAssertTrue(metaDays.hasPrefix("NFL · "), metaDays)
        XCTAssertTrue(metaDays.hasSuffix(" · CBS"), metaDays)
        XCTAssertFalse(metaDays.localizedCaseInsensitiveContains("as of"))
        XCTAssertFalse(metaDays.localizedCaseInsensitiveContains("venue"))
        XCTAssertFalse(metaDays.localizedCaseInsensitiveContains("total"))
        XCTAssertFalse(metaDays.localizedCaseInsensitiveContains("opened"))

        let withinHour = try nflPregameFixture(commenceTime: "2026-11-13T18:42:00Z")
        let hourModel = try XCTUnwrap(
            resolveHeadline(withinHour, hasScore: false, numberStreams: false)
        )
        XCTAssertEqual(hourModel.plainMetaText, "NFL · In 42m · CBS")
    }

    // MARK: - NBA During a Game Rules

    func testNBADuringGameShowsProjectedOncePregameNeverOpenedAndNoRelativeAge() throws {
        // Even when prematch_odds is absent and PrematchReading falls back to opening_odds,
        // the headline uses a single "Pregame" column header ("Score · Pregame · Now")
        // with bare grey percentages ("49%", "51%"), NEVER repeating "pregame" twice and NEVER "opened".
        let fallbackToOpening = try nbaLiveFixture(includeServedPrematch: false)
        let model = try XCTUnwrap(
            resolveHeadline(fallbackToOpening, hasScore: true, numberStreams: true)
        )
        XCTAssertEqual(model.liveBadgeText, "LIVE · Q4 2:14")
        XCTAssertEqual(model.leagueLabel, "NBA")
        XCTAssertNil(model.plainMetaText)
        XCTAssertEqual(
            model.liveColumnHeaders,
            EventSportHeadlines12472.LiveColumnHeaders(score: "Score", pregame: "Pregame", now: "Now")
        )
        XCTAssertEqual(model.away.liveScore, 98)
        XCTAssertEqual(model.home.liveScore, 100)
        XCTAssertEqual(model.away.projectedText, "Proj. 103.5")
        XCTAssertEqual(model.home.projectedText, "Proj. 105.0")
        XCTAssertEqual(model.away.pregameChanceText, "49%")
        XCTAssertEqual(model.home.pregameChanceText, "51%")
        XCTAssertFalse(model.away.pregameChanceText?.localizedCaseInsensitiveContains("pregame") ?? false)
        XCTAssertFalse(model.home.pregameChanceText?.localizedCaseInsensitiveContains("pregame") ?? false)
        XCTAssertFalse(model.away.pregameChanceText?.localizedCaseInsensitiveContains("open") ?? false)
        XCTAssertFalse(model.home.pregameChanceText?.localizedCaseInsensitiveContains("open") ?? false)
        XCTAssertEqual(model.away.winChanceText, "41.2%")
        XCTAssertEqual(model.home.winChanceText, "58.8%")
        XCTAssertEqual(model.pregameAwayMarker ?? 0, 0.49, accuracy: 0.0001)
    }

    func testNBADuringGameClampsExtremeOpenProbabilitiesAndWithholdsUnscoredProjection() throws {
        let extreme = try nbaLiveFixture(homeProb: 0.999, includeLiveProjection: true)
        let modelNoScore = try XCTUnwrap(
            resolveHeadline(extreme, hasScore: false, numberStreams: true)
        )
        XCTAssertEqual(
            modelNoScore.liveColumnHeaders,
            EventSportHeadlines12472.LiveColumnHeaders(score: nil, pregame: "Pregame", now: "Now")
        )
        XCTAssertEqual(modelNoScore.away.winChanceText, "<1%")
        XCTAssertEqual(modelNoScore.home.winChanceText, ">99%")
        XCTAssertNil(modelNoScore.away.projectedText, "#5697: never print live projection without a live score")
        XCTAssertNil(modelNoScore.home.projectedText)
    }

    func testSourceMarkClearsWhenPreviewOverlaysPrice() throws {
        var event = try nbaLiveFixture()
        event.blendFoldRevision = try JSONDecoder().decode(
            ServedFoldRevision.self,
            from: Data(#"{"9124722":10}"#.utf8)
        )
        XCTAssertNotNil(event.sourceMark)
        let nowTs = fixedNow.timeIntervalSince1970
        let previewFrame = BlendPreviewFrame(
            eventId: 9124722,
            p: 0.612,
            status: "live",
            kind: .blend,
            epoch: 1,
            seq: 1,
            baseRev: 10,
            ttlMs: 60_000
        )
        let state = try XCTUnwrap(
            BlendPreview.previewAfter(nil, previewFrame, eventId: 9124722, now: nowTs)
        )
        let overlaid = BlendPreview.overlay(event, state, now: nowTs + 1)
        XCTAssertEqual(overlaid.heroProbability ?? 0, 0.612, accuracy: 0.0001)
        XCTAssertNil(overlaid.sourceMark, "previewed probability must never claim stale venue breakdown")
    }

    // MARK: - 390x852 First-Screen Fold & Accessibility Layout Proofs

    func testFirstScreenFitsHeadlineAndWinProbabilityChartAt390x852AndExportsRenders() async throws {
        let nflEvent = try nflPregameFixture()
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

        let nbaEvent = try nbaLiveFixture()
        let nbaHistory = try decodeHistory("""
        {
          "event_id": 9124722,
          "home_team": "Philadelphia 76ers",
          "away_team": "Boston Celtics",
          "history": [
            { "timestamp": "2026-11-13T13:30:00Z", "home_probability": 0.51, "away_probability": 0.49, "source": "aggregate" },
            { "timestamp": "2026-11-13T14:00:00Z", "home_probability": 0.57, "away_probability": 0.43, "source": "aggregate" },
            { "timestamp": "2026-11-13T14:20:00Z", "home_probability": 0.44, "away_probability": 0.56, "source": "aggregate" },
            { "timestamp": "2026-11-13T14:40:00Z", "home_probability": 0.53, "away_probability": 0.47, "source": "aggregate" },
            { "timestamp": "2026-11-13T14:59:30Z", "home_probability": 0.588, "away_probability": 0.412, "source": "aggregate" }
          ]
        }
        """)

        // Measure isolated headline card heights at 390pt (358pt content width inside 16pt horizontal margins)
        let nflModel = try XCTUnwrap(
            resolveHeadline(nflEvent, hasScore: false, numberStreams: false)
        )
        let nbaModel = try XCTUnwrap(
            resolveHeadline(nbaEvent, hasScore: true, numberStreams: true)
        )

        let beatingTracker = EkgTracker(
            eventId: 9124722,
            lastSignalAt: fixedNow.addingTimeInterval(-3),
            beatAt: fixedNow.addingTimeInterval(-3),
            beats: 1
        )

        let nflColors = TeamTextContrast.cardColors(
            awayHex: nflEvent.awayTeamData?.primaryColor,
            homeHex: nflEvent.homeTeamData?.primaryColor
        )
        let nbaColors = TeamTextContrast.cardColors(
            awayHex: nbaEvent.awayTeamData?.primaryColor,
            homeHex: nbaEvent.homeTeamData?.primaryColor
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

        let nbaCard = EventSportHeadlineCard12472(
            model: nbaModel,
            colors: nbaColors,
            ekgTracker: beatingTracker,
            liveUpdateStatus: .live,
            displayAsOf: fixedNow,
            updateStream: LiveUpdateStream(),
            showUpdateStream: .constant(false),
            showProbabilityDetails: .constant(false),
            priceStreamingEligible: true,
            lastReceivedAt: fixedNow,
            confirmedAt: fixedNow,
            revealForecast: nil
        )
        .frame(width: 358)

        let nflHost = hostForMeasurement(nflCard, at: .large)
        let nflSize = nflHost.sizeThatFits(in: CGSize(width: 358, height: 1000))
        XCTAssertLessThanOrEqual(nflSize.width, 358.5)
        XCTAssertLessThanOrEqual(nflSize.height, 180, "NFL pregame card height (\(nflSize.height)pt) keeps chart well above 852pt fold")

        let nbaHost = hostForMeasurement(nbaCard, at: .large)
        let nbaSize = nbaHost.sizeThatFits(in: CGSize(width: 358, height: 1000))
        XCTAssertLessThanOrEqual(nbaSize.width, 358.5)
        XCTAssertLessThanOrEqual(nbaSize.height, 185, "NBA live card height (\(nbaSize.height)pt) keeps chart well above 852pt fold")

        // Accessibility .accessibility2 width check (zero horizontal bleed)
        let nbaA11yHost = hostForMeasurement(nbaCard, at: .accessibility2)
        let nbaA11ySize = nbaA11yHost.sizeThatFits(in: CGSize(width: 358, height: 2000))
        XCTAssertLessThanOrEqual(nbaA11ySize.width, 358.5, "NBA live card must not bleed horizontally at accessibility2")

        // Full 390x852 EventDetailView page renders (headline + Win Probability chart in first screen)
        let nflVM = EventDetailViewModel(
            eventId: nflEvent.id,
            client: StubEventDetailProvider(detail: nflEvent, history: nflHistory)
        )
        await nflVM.load()
        nflVM.stopRefresh()

        let nbaVM = EventDetailViewModel(
            eventId: nbaEvent.id,
            client: StubEventDetailProvider(detail: nbaEvent, history: nbaHistory)
        )
        await nbaVM.load()
        nbaVM.stopRefresh()

        let nflStreamingModel = try XCTUnwrap(
            resolveHeadline(
                try nflPregameFixture(commenceTime: "2026-11-13T18:42:00Z"),
                hasScore: false,
                numberStreams: true
            )
        )

        if let exportDir = ProcessInfo.processInfo.environment["BL_EXPORT_12472_DIR"], !exportDir.isEmpty {
            let dirURL = URL(fileURLWithPath: exportDir, isDirectory: true)
            try FileManager.default.createDirectory(at: dirURL, withIntermediateDirectories: true)

            let nflPage = NavigationStack {
                EventDetailView(eventId: nflEvent.id)
                    .withLoadedEventForTest12278(nflEvent, viewModel: nflVM)
            }
            .environmentObject(PinManager())
            .environmentObject(NavigationCoordinator())
            .frame(width: 390, height: 852)
            .background(Color(uiColor: .systemGroupedBackground))

            let nbaPage = NavigationStack {
                EventDetailView(eventId: nbaEvent.id)
                    .withLoadedEventForTest12278(nbaEvent, viewModel: nbaVM)
            }
            .environmentObject(PinManager())
            .environmentObject(NavigationCoordinator())
            .frame(width: 390, height: 852)
            .background(Color(uiColor: .systemGroupedBackground))

            let cardsSheet = VStack(alignment: .leading, spacing: 18) {
                VStack(alignment: .leading, spacing: 6) {
                    Text("NFL Before a Game · Non-streaming (whole %)")
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(.secondary)
                    nflCard
                }
                VStack(alignment: .leading, spacing: 6) {
                    Text("NFL Before a Game · Streaming tenths + <1h countdown")
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(.secondary)
                    EventSportHeadlineCard12472(
                        model: nflStreamingModel,
                        colors: nflColors,
                        ekgTracker: beatingTracker,
                        liveUpdateStatus: .live,
                        displayAsOf: fixedNow,
                        updateStream: LiveUpdateStream(),
                        showUpdateStream: .constant(false),
                        showProbabilityDetails: .constant(false),
                        priceStreamingEligible: true,
                        lastReceivedAt: fixedNow,
                        confirmedAt: fixedNow,
                        revealForecast: nil
                    )
                    .frame(width: 358)
                }
                VStack(alignment: .leading, spacing: 6) {
                    Text("NBA During a Game · Score, Pregame, Now columns + Live Proj. once + EKG")
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(.secondary)
                    nbaCard
                }
            }
            .padding(16)
            .frame(width: 390)
            .background(Color(uiColor: .systemGroupedBackground))

            let a11ySheet = VStack(alignment: .leading, spacing: 14) {
                Text("NBA During a Game · Accessibility (.accessibility2, 390pt)")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.secondary)
                nbaCard
            }
            .padding(16)
            .frame(width: 390)
            .background(Color(uiColor: .systemGroupedBackground))

            func writeHostedPagePNG<V: View>(
                _ view: V,
                size: CGSize,
                at dt: DynamicTypeSize,
                to url: URL
            ) throws {
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
                let until = Date().addingTimeInterval(0.4)
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

            try writeHostedPagePNG(
                nflPage,
                size: CGSize(width: 390, height: 852),
                at: .large,
                to: dirURL.appendingPathComponent("12472-nfl-before-page-390x852.png")
            )
            try writeHostedPagePNG(
                nbaPage,
                size: CGSize(width: 390, height: 852),
                at: .large,
                to: dirURL.appendingPathComponent("12472-nba-during-page-390x852.png")
            )

            for (name, view, dt) in [
                ("12472-headline-cards-390.png", AnyView(cardsSheet.environment(\.colorScheme, .light)), DynamicTypeSize.large),
                ("12472-nba-during-a11y2-390.png", AnyView(a11ySheet.environment(\.colorScheme, .light)), DynamicTypeSize.accessibility2),
            ] {
                let renderer = rendererForMeasurement(view, at: dt)
                renderer.scale = 3.0
                if let png = renderer.uiImage?.pngData() {
                    try png.write(to: dirURL.appendingPathComponent(name))
                }
            }
        }
    }
}
