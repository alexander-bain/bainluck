import SwiftUI
import UIKit
import XCTest
@testable import Bain_Luck

@MainActor
final class NFLLiveHeadline199Tests: XCTestCase {

    private let fixedNow = ISO8601DateFormatter().date(from: "2026-11-15T19:15:00Z")!

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
                from: Data(#"{"event_id":\#(eventId),"home_team":"Detroit Lions","away_team":"New England Patriots","markets":[]}"#.utf8)
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

    private func patriotsLionsLiveFixture(
        includePrematch: Bool = true,
        awayWasFavourite: Bool = false,
        includePregameProjection: Bool = true,
        includeLiveProjection: Bool = true
    ) throws -> EventDetail {
        let prematchHome = awayWasFavourite ? 0.42 : 0.58
        let prematchAway = awayWasFavourite ? 0.58 : 0.42
        let prematchHomePct = awayWasFavourite ? 42 : 58
        let prematchAwayPct = awayWasFavourite ? 58 : 42

        let prematchMember = includePrematch ? """
          "prematch_odds": {
            "home_probability": \(prematchHome),
            "away_probability": \(prematchAway),
            "home_rendered_percent": \(prematchHomePct),
            "away_rendered_percent": \(prematchAwayPct),
            "source": "kalshi"
          },
        """ : ""

        let projHome = awayWasFavourite ? 23.8 : 27.2
        let projAway = awayWasFavourite ? 27.2 : 23.8
        let pregameProjMember = includePregameProjection ? """
          "pregame_projection": {
            "projected_home_score": \(projHome),
            "projected_away_score": \(projAway),
            "kind": "last_before_scheduled_start",
            "earliest_captured_at": "2026-11-15T17:30:00Z",
            "latest_captured_at": "2026-11-15T17:58:00Z",
            "boundary": "scheduled_start",
            "boundary_at": "2026-11-15T18:00:00Z",
            "source": "sportsbooks",
            "basis": "consensus_spread_total",
            "bookmaker_count": 5,
            "unit": "points",
            "period": "full_game"
          },
        """ : ""

        let liveProjMember = includeLiveProjection ? """
            "live_projection": {
              "projected_home_score": 28.0,
              "projected_away_score": 23.5,
              "kind": "in_play",
              "boundary": "commence_time",
              "boundary_at": "2026-11-15T18:00:00Z",
              "earliest_confirmed_at": "2026-11-15T19:13:00Z",
              "latest_captured_at": "2026-11-15T19:13:00Z",
              "source": "sportsbooks",
              "basis": "consensus_spread_total",
              "bookmaker_count": 4,
              "unit": "points",
              "period": "full_game"
            },
        """ : ""

        return try decodeEvent("""
        {
          "id": 9199001,
          "sport": "americanfootball_nfl",
          "home_team": "Detroit Lions",
          "away_team": "New England Patriots",
          "commence_time": "2026-11-15T18:00:00Z",
          "status": "live",
          "home_score": 21,
          "away_score": 17,
          "home_team_data": {
            "abbreviation": "DET",
            "primary_color": "#0076B6",
            "secondary_color": "#B0B7BC",
            "logo_large": "https://a.espncdn.com/i/teamlogos/nfl/500/det.png",
            "logo_small": "https://a.espncdn.com/i/teamlogos/nfl/500/scoreboard/det.png",
            "record": "8-1"
          },
          "away_team_data": {
            "abbreviation": "NE",
            "primary_color": "#002244",
            "secondary_color": "#C60C30",
            "logo_large": "https://a.espncdn.com/i/teamlogos/nfl/500/ne.png",
            "logo_small": "https://a.espncdn.com/i/teamlogos/nfl/500/scoreboard/ne.png",
            "record": "4-6"
          },
          "current_odds": {
            \(liveProjMember)
            "home_probability": 0.662,
            "away_probability": 0.338,
            "home_rendered_percent": 66,
            "away_rendered_percent": 34,
            "updated_at": "2026-11-15T19:14:00Z"
          },
          \(prematchMember)
          \(pregameProjMember)
          "opening_odds": {
            "home_probability": 0.54,
            "away_probability": 0.46,
            "home_rendered_percent": 54,
            "away_rendered_percent": 46
          },
          "hero_probability": 0.662,
          "hero_probability_away": 0.338,
          "hero_probability_source": "blend",
          "hero_probability_observed_at": "2026-11-15T19:14:00Z",
          "espn": {
            "period": "3rd",
            "game_clock": "8:14",
            "broadcast": "FOX"
          },
          "win_probability_sources": {
            "betting": { "value": 0.66, "display_name": "Sportsbooks" },
            "kalshi": { "value": 0.67, "display_name": "Kalshi" },
            "polymarket": { "value": 0.66, "display_name": "Polymarket" }
          },
          "source_mark": {
            "state": "blend",
            "label": "3 sources",
            "draws": true,
            "sources": [
              { "key": "betting", "name": "Sportsbooks", "probability": 0.66, "weight": 3.0 },
              { "key": "kalshi", "name": "Kalshi", "probability": 0.67, "weight": 0.8 },
              { "key": "polymarket", "name": "Polymarket", "probability": 0.66, "weight": 0.8 }
            ]
          }
        }
        """)
    }

    private func makeHistory(event: EventDetail) throws -> EventHistoryResponse {
        try decodeHistory("""
        {
          "event_id": \(event.id),
          "home_team": "\(event.homeTeam)",
          "away_team": "\(event.awayTeam)",
          "commence_time": "\(event.commenceTime ?? "2026-11-15T18:00:00Z")",
          "history": [
            { "timestamp": "2026-11-15T17:58:00Z", "home_probability": 0.580, "away_probability": 0.420, "source": "aggregate" },
            { "timestamp": "2026-11-15T18:05:00Z", "home_probability": 0.565, "away_probability": 0.435, "source": "aggregate" },
            { "timestamp": "2026-11-15T18:12:00Z", "home_probability": 0.530, "away_probability": 0.470, "source": "aggregate" },
            { "timestamp": "2026-11-15T18:18:00Z", "home_probability": 0.492, "away_probability": 0.508, "source": "aggregate" },
            { "timestamp": "2026-11-15T18:24:00Z", "home_probability": 0.515, "away_probability": 0.485, "source": "aggregate" },
            { "timestamp": "2026-11-15T18:30:00Z", "home_probability": 0.548, "away_probability": 0.452, "source": "aggregate" },
            { "timestamp": "2026-11-15T18:36:00Z", "home_probability": 0.575, "away_probability": 0.425, "source": "aggregate" },
            { "timestamp": "2026-11-15T18:42:00Z", "home_probability": 0.605, "away_probability": 0.395, "source": "aggregate" },
            { "timestamp": "2026-11-15T18:48:00Z", "home_probability": 0.590, "away_probability": 0.410, "source": "aggregate" },
            { "timestamp": "2026-11-15T18:54:00Z", "home_probability": 0.618, "away_probability": 0.382, "source": "aggregate" },
            { "timestamp": "2026-11-15T19:00:00Z", "home_probability": 0.635, "away_probability": 0.365, "source": "aggregate" },
            { "timestamp": "2026-11-15T19:05:00Z", "home_probability": 0.648, "away_probability": 0.352, "source": "aggregate" },
            { "timestamp": "2026-11-15T19:10:00Z", "home_probability": 0.654, "away_probability": 0.346, "source": "aggregate" },
            { "timestamp": "2026-11-15T19:14:00Z", "home_probability": 0.662, "away_probability": 0.338, "source": "aggregate" }
          ]
        }
        """)
    }

    private func hostForMeasurement<V: View>(_ view: V, at dt: DynamicTypeSize) -> UIHostingController<AnyView> {
        let wrapped = AnyView(view.environment(\.dynamicTypeSize, dt))
        let host = UIHostingController(rootView: wrapped)
        host.loadViewIfNeeded()
        return host
    }

    // MARK: - Ruling 200-B Live NFL Model & Pregame Line Tests

    func testNFLLiveHeadlineUsesRuling200BThreeColumnsAndSinglePregameLine() throws {
        let event = try patriotsLionsLiveFixture()
        XCTAssertEqual(EventSportHeadlines12472.kind(for: event, now: fixedNow), .nflDuringGame)
        XCTAssertTrue(EventSportHeadlines12472.applies(to: event, now: fixedNow))

        let model = try XCTUnwrap(
            EventSportHeadlines12472.resolve(
                event: event,
                awayFullName: event.awayTeam,
                homeFullName: event.homeTeam,
                liveStatusText: "Q3 · 8:14",
                hasScore: true,
                numberStreams: true,
                now: fixedNow
            )
        )

        XCTAssertEqual(
            model.liveColumnHeaders,
            EventSportHeadlines12472.LiveColumnHeaders(
                score: "Score",
                projected: "Proj.",
                pregame: nil,
                now: "Now"
            )
        )
        XCTAssertEqual(model.away.shortName, "Patriots")
        XCTAssertEqual(model.home.shortName, "Lions")
        XCTAssertEqual(model.away.liveScore, 17)
        XCTAssertEqual(model.home.liveScore, 21)
        XCTAssertEqual(model.away.liveProjectedNumberText, "23.5")
        XCTAssertEqual(model.home.liveProjectedNumberText, "28.0")
        XCTAssertNil(model.away.projectedText, "Proj. must live in its column, never stacked under the team name")
        XCTAssertNil(model.home.projectedText)
        XCTAssertNil(model.away.pregameChanceText, "No Pregame column during a game")
        XCTAssertNil(model.home.pregameChanceText)
        XCTAssertEqual(model.away.winChanceText, "33.8%")
        XCTAssertEqual(model.home.winChanceText, "66.2%")
        XCTAssertEqual(model.livePregameSummary?.fullText, "Pregame  Lions 58% · projected 27–24")

        // When away team was pregame favourite, away comes first in both halves
        let awayFavEvent = try patriotsLionsLiveFixture(awayWasFavourite: true)
        let awayFavModel = try XCTUnwrap(
            EventSportHeadlines12472.resolve(
                event: awayFavEvent,
                awayFullName: awayFavEvent.awayTeam,
                homeFullName: awayFavEvent.homeTeam,
                liveStatusText: "Q3 · 8:14",
                hasScore: true,
                numberStreams: true,
                now: fixedNow
            )
        )
        XCTAssertEqual(awayFavModel.livePregameSummary?.fullText, "Pregame  Patriots 58% · projected 27–24")
    }

    func testLivePregameSummaryMissingHalvesAndNeverPassesOpeningAsPregame() throws {
        // 1. Only pregame chance present -> projection half omitted
        let chanceOnly = try patriotsLionsLiveFixture(includePregameProjection: false)
        let chanceOnlyModel = try XCTUnwrap(
            EventSportHeadlines12472.resolve(
                event: chanceOnly,
                awayFullName: chanceOnly.awayTeam,
                homeFullName: chanceOnly.homeTeam,
                liveStatusText: "Q3 · 8:14",
                hasScore: true,
                numberStreams: false,
                now: fixedNow
            )
        )
        XCTAssertEqual(chanceOnlyModel.livePregameSummary?.fullText, "Pregame  Lions 58%")

        // 2. Only pregame projected score present (`prematch_odds` nil, `opening_odds` present)
        // -> opening_odds must NOT be passed off as Pregame!
        let projOnly = try patriotsLionsLiveFixture(includePrematch: false, includePregameProjection: true)
        let projOnlyModel = try XCTUnwrap(
            EventSportHeadlines12472.resolve(
                event: projOnly,
                awayFullName: projOnly.awayTeam,
                homeFullName: projOnly.homeTeam,
                liveStatusText: "Q3 · 8:14",
                hasScore: true,
                numberStreams: false,
                now: fixedNow
            )
        )
        XCTAssertEqual(projOnlyModel.livePregameSummary?.fullText, "Pregame  projected Lions 27–24")
        XCTAssertNil(projOnlyModel.pregameAwayMarker, "opening_odds must not draw a pregame marker")

        // 3. Both missing (`opening_odds` still present) -> line completely hidden, empty Proj. cell keeps 3 columns
        let bothMissing = try patriotsLionsLiveFixture(
            includePrematch: false,
            includePregameProjection: false,
            includeLiveProjection: false
        )
        let bothMissingModel = try XCTUnwrap(
            EventSportHeadlines12472.resolve(
                event: bothMissing,
                awayFullName: bothMissing.awayTeam,
                homeFullName: bothMissing.homeTeam,
                liveStatusText: "Q3 · 8:14",
                hasScore: true,
                numberStreams: false,
                now: fixedNow
            )
        )
        XCTAssertNil(bothMissingModel.livePregameSummary, "Grey pregame line must hide when both halves are missing")
        XCTAssertEqual(
            bothMissingModel.liveColumnHeaders,
            EventSportHeadlines12472.LiveColumnHeaders(score: "Score", projected: "Proj.", pregame: nil, now: "Now"),
            "Missing live projection leaves Proj. cell empty without changing column layout"
        )
        XCTAssertNil(bothMissingModel.away.liveProjectedNumberText)
        XCTAssertNil(bothMissingModel.home.liveProjectedNumberText)

        for m in [chanceOnlyModel, projOnlyModel, bothMissingModel] {
            let texts = [
                m.liveBadgeText,
                m.plainMetaText,
                m.livePregameSummary?.fullText,
                m.away.winChanceText,
                m.home.winChanceText,
            ].compactMap { $0 }
            for text in texts {
                XCTAssertFalse(text.localizedCaseInsensitiveContains("opening"), text)
                XCTAssertFalse(text.localizedCaseInsensitiveContains("opened"), text)
                XCTAssertFalse(text.localizedCaseInsensitiveContains("current win chance"), text)
                XCTAssertFalse(text.localizedCaseInsensitiveContains("projection before"), text)
            }
        }
    }

    // MARK: - Ruling 197 Same Hue-Family Disambiguation Tests

    func testRuling197SameHueFamilySwitchesAwayToSecondaryElseSlateGrey() {
        // Patriots (#002244 / #C60C30) at Lions (#0076B6 / #B0B7BC): both blue -> Patriots red
        let neDet = TeamTextContrast.cardColorHexes(
            awayHex: "#002244",
            homeHex: "#0076B6",
            awaySecondaryHex: "#C60C30"
        )
        XCTAssertEqual(neDet.away, "#C60C30")
        XCTAssertEqual(neDet.home, "#0076B6")

        // Kansas (#0051ba / #e8000d) at Duke (#00539b / #ffffff): both blue -> Kansas crimson
        let kuDuke = TeamTextContrast.cardColorHexes(
            awayHex: "#0051ba",
            homeHex: "#00539b",
            awaySecondaryHex: "#e8000d"
        )
        XCTAssertEqual(kuDuke.away, "#E8000D")
        XCTAssertEqual(kuDuke.home, "#00539B")

        // Gonzaga (#041e42 / #c8102e) at Duke (#00539b / #ffffff): navy + royal blue -> Gonzaga red
        let gonzDuke = TeamTextContrast.cardColorHexes(
            awayHex: "#041e42",
            homeHex: "#00539b",
            awaySecondaryHex: "#c8102e"
        )
        XCTAssertEqual(gonzDuke.away, "#C8102E")
        XCTAssertEqual(gonzDuke.home, "#00539B")

        // Kentucky (#0033a0 / #ffffff) at Duke (#00539b / #ffffff): secondary fails contrast -> slate grey
        let ukDuke = TeamTextContrast.cardColorHexes(
            awayHex: "#0033a0",
            homeHex: "#00539b",
            awaySecondaryHex: "#ffffff"
        )
        XCTAssertEqual(ukDuke.away, ProbabilityBarPalette.awayDefault)
        XCTAssertEqual(ukDuke.home, "#00539B")

        // Control: Alabama (#9e1b32 / #ffffff) at Duke (#00539b / #ffffff): red vs blue -> unchanged
        let bamaDuke = TeamTextContrast.cardColorHexes(
            awayHex: "#9e1b32",
            homeHex: "#00539b",
            awaySecondaryHex: "#ffffff"
        )
        XCTAssertEqual(bamaDuke.away, "#9E1B32")
        XCTAssertEqual(bamaDuke.home, "#00539B")
    }

    // MARK: - 390 px Layout Fit & Render Export

    func testNFLLiveCardFitsAt390AndAccessibility2AndExports390pxRenders() async throws {
        let fullLive = try patriotsLionsLiveFixture()
        let chanceOnlyLive = try patriotsLionsLiveFixture(includePregameProjection: false)
        let missingBothLive = try patriotsLionsLiveFixture(
            includePrematch: false,
            includePregameProjection: false,
            includeLiveProjection: false
        )

        func makeCard(_ event: EventDetail) throws -> EventSportHeadlineCard12472 {
            let model = try XCTUnwrap(
                EventSportHeadlines12472.resolve(
                    event: event,
                    awayFullName: event.awayTeam,
                    homeFullName: event.homeTeam,
                    liveStatusText: "Q3 · 8:14",
                    hasScore: true,
                    numberStreams: true,
                    now: fixedNow
                )
            )
            let pairColors = TeamTextContrast.cardColors(
                awayHex: event.awayTeamData?.primaryColor,
                homeHex: event.homeTeamData?.primaryColor,
                awaySecondaryHex: event.awayTeamData?.secondaryColor
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

        let cardFull = try makeCard(fullLive)
        let cardChanceOnly = try makeCard(chanceOnlyLive)
        let cardMissingBoth = try makeCard(missingBothLive)

        for card in [cardFull, cardChanceOnly, cardMissingBoth] {
            for dt in [DynamicTypeSize.large, .accessibility2] {
                let host = hostForMeasurement(card.frame(width: 358), at: dt)
                let fitted = host.sizeThatFits(in: CGSize(width: 358, height: 1000))
                XCTAssertLessThanOrEqual(fitted.width, 358.5)
                XCTAssertGreaterThan(fitted.height, 90)
            }
        }

        if let outDir = ProcessInfo.processInfo.environment["EXPORT_199_NFL_LIVE_RENDERS_DIR"],
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
                try await Task.sleep(nanoseconds: 350_000_000)
                let until = Date().addingTimeInterval(0.35)
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

            let hist = try makeHistory(event: fullLive)
            let vm = EventDetailViewModel(
                eventId: fullLive.id,
                client: StubEventDetailProvider(detail: fullLive, history: hist)
            )
            await vm.load()
            vm.stopRefresh()
            let fullPage = NavigationStack {
                EventDetailView(eventId: fullLive.id)
                    .withLoadedEventForTest12278(fullLive, viewModel: vm)
            }
            .environmentObject(PinManager())
            .environmentObject(NavigationCoordinator())
            .frame(width: 390, height: 852)
            .background(Color(uiColor: .systemGroupedBackground))

            try await writeHostedPNG(
                fullPage,
                size: CGSize(width: 390, height: 852),
                to: dirURL.appendingPathComponent("199-nfl-live-patriots-lions-page-390x852.png")
            )

            let statesSheet = VStack(alignment: .leading, spacing: 14) {
                VStack(alignment: .leading, spacing: 5) {
                    Text("NFL Live (Ruling 200-B + 197) · Score · Proj. · Now")
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(.secondary)
                    cardFull
                }
                VStack(alignment: .leading, spacing: 5) {
                    Text("Missing Pregame Projection · 'Pregame  Lions 58%'")
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(.secondary)
                    cardChanceOnly
                }
                VStack(alignment: .leading, spacing: 5) {
                    Text("Missing Pregame & Live Proj. · Empty Cell, Line Hidden")
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(.secondary)
                    cardMissingBoth
                }
            }
            .padding(16)
            .frame(width: 390)
            .background(Color(uiColor: .systemGroupedBackground))
            .ignoresSafeArea()

            let sheetHost = hostForMeasurement(statesSheet.environment(\.colorScheme, .light), at: .large)
            sheetHost.additionalSafeAreaInsets = .zero
            let sheetHeight = ceil(sheetHost.sizeThatFits(in: CGSize(width: 390, height: 1800)).height)
            try await writeHostedPNG(
                statesSheet,
                size: CGSize(width: 390, height: sheetHeight),
                to: dirURL.appendingPathComponent("199-nfl-live-headline-states-390.png")
            )
        }
    }
}
