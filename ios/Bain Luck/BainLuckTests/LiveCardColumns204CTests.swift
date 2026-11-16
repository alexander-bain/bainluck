import SwiftUI
import UIKit
import XCTest
@testable import Bain_Luck

/// Ruling 204-C (Mon Nov 16) + Fable #12775 "GBP" note:
/// - During a game, the phone's cards (Discover, feed, search) print
///   `Score · Proj. · Now` with **no grey line**; the tick on the bar carries
///   the pregame chance (`prematch_odds`, never `opening_odds`).
/// - The game page headline (`EventSportHeadlineCard12472`) keeps its one grey
///   pregame line (`200-B`).
/// - Scheduled Discover / accessibility projected lines pass served
///   `awayTeamData.abbreviation` / `homeTeamData.abbreviation` (`MIN` / `GB`,
///   never derived `VIK` / `GBP`).
@MainActor
final class LiveCardColumns204CTests: XCTestCase {

    private let fixedNow = ISO8601DateFormatter().date(from: "2026-11-15T19:00:00Z")!

    private func decodeFeedEvent(_ json: String) throws -> FeedEventData {
        let dec = JSONDecoder()
        dec.keyDecodingStrategy = .convertFromSnakeCase
        return try dec.decode(FeedEventData.self, from: Data(json.utf8))
    }

    private func decodeSearchEvent(_ json: String) throws -> SearchEvent {
        let dec = JSONDecoder()
        dec.keyDecodingStrategy = .convertFromSnakeCase
        return try dec.decode(SearchEvent.self, from: Data(json.utf8))
    }

    private func decodeEventDetail(_ json: String) throws -> EventDetail {
        let dec = JSONDecoder()
        dec.keyDecodingStrategy = .convertFromSnakeCase
        return try dec.decode(EventDetail.self, from: Data(json.utf8))
    }

    private func decodeHistory(_ json: String) throws -> EventHistoryResponse {
        let dec = JSONDecoder()
        dec.keyDecodingStrategy = .convertFromSnakeCase
        return try dec.decode(EventHistoryResponse.self, from: Data(json.utf8))
    }

    private var liveNFLJSON: String {
        """
        {
          "id": 401548,
          "sport": "americanfootball_nfl",
          "sport_name": "NFL",
          "home_team": "Detroit Lions",
          "away_team": "New England Patriots",
          "commence_time": "2026-11-15T18:00:00Z",
          "status": "live",
          "home_score": 21,
          "away_score": 17,
          "home_team_data": {
            "abbreviation": "DET",
            "primary_color": "#0076B6",
            "record": "8-1"
          },
          "away_team_data": {
            "abbreviation": "NE",
            "primary_color": "#C60C30",
            "record": "3-7"
          },
          "current_odds": {
            "home_probability": 0.662,
            "away_probability": 0.338,
            "home_rendered_percent": 66,
            "away_rendered_percent": 34,
            "updated_at": "2026-11-15T18:55:00Z",
            "live_projection": {
              "projected_away_score": 23.6,
              "projected_home_score": 28.1,
              "kind": "in_play",
              "boundary": "commence_time",
              "boundary_at": "2026-11-15T18:00:00Z",
              "earliest_confirmed_at": "2026-11-15T18:50:00Z",
              "latest_captured_at": "2026-11-15T18:54:00Z",
              "source": "sportsbooks",
              "basis": "consensus_spread_total",
              "bookmaker_count": 5,
              "unit": "points",
              "period": "full_game"
            }
          },
          "prematch_odds": {
            "home_probability": 0.58,
            "away_probability": 0.42,
            "home_rendered_percent": 58,
            "away_rendered_percent": 42,
            "source": "kalshi"
          },
          "pregame_projection": {
            "kind": "last_before_scheduled_start",
            "boundary": "scheduled_start",
            "boundary_at": "2026-11-15T18:00:00Z",
            "source": "sportsbooks",
            "basis": "consensus_spread_total",
            "unit": "points",
            "period": "full_game",
            "projected_home_score": 27.1,
            "projected_away_score": 23.8,
            "bookmaker_count": 14,
            "earliest_captured_at": "2026-11-15T17:40:00Z",
            "latest_captured_at": "2026-11-15T17:58:00Z"
          },
          "highlight": {
            "label": "Detroit Lions leading after starting at 58%"
          },
          "espn": {
            "period": "Q3",
            "game_clock": "8:14",
            "broadcast": "CBS"
          }
        }
        """
    }

    private var liveNBASearchJSON: String {
        """
        {
          "id": 401549,
          "sport": "basketball_nba",
          "sport_name": "NBA",
          "home_team": "Philadelphia 76ers",
          "away_team": "Boston Celtics",
          "commence_time": "2026-11-15T18:00:00Z",
          "status": "live",
          "home_score": 79,
          "away_score": 88,
          "home_team_data": {
            "abbreviation": "PHI",
            "primary_color": "#006BB6"
          },
          "away_team_data": {
            "abbreviation": "BOS",
            "primary_color": "#007A33"
          },
          "current_odds": {
            "home_probability": 0.288,
            "away_probability": 0.712,
            "live_projection": {
              "projected_away_score": 118.2,
              "projected_home_score": 109.1,
              "kind": "in_play",
              "boundary": "commence_time",
              "boundary_at": "2026-11-15T18:00:00Z",
              "earliest_confirmed_at": "2026-11-15T18:45:00Z",
              "latest_captured_at": "2026-11-15T18:46:00Z",
              "source": "sportsbooks",
              "basis": "consensus_spread_total",
              "bookmaker_count": 4,
              "unit": "points",
              "period": "full_game"
            }
          },
          "prematch_odds": {
            "home_probability": 0.46,
            "away_probability": 0.54,
            "home_rendered_percent": 46,
            "away_rendered_percent": 54,
            "source": "kalshi"
          },
          "highlight": {
            "label": "Boston Celtics leading after starting at 54%"
          },
          "espn": {
            "period": "Q3",
            "game_clock": "4:12"
          }
        }
        """
    }

    private var liveSoccerJSON: String {
        """
        {
          "id": 401550,
          "sport": "soccer_epl",
          "sport_name": "Premier League",
          "home_team": "Chelsea",
          "away_team": "Arsenal",
          "commence_time": "2026-11-15T17:30:00Z",
          "status": "live",
          "home_score": 1,
          "away_score": 0,
          "home_team_data": {
            "abbreviation": "CHE",
            "primary_color": "#034694"
          },
          "away_team_data": {
            "abbreviation": "ARS",
            "primary_color": "#EF0107"
          },
          "current_odds": {
            "away_probability": 0.241,
            "draw_probability": 0.235,
            "home_probability": 0.524,
            "live_projection": {
              "projected_away_score": 1.0,
              "projected_home_score": 1.6,
              "kind": "in_play",
              "boundary": "commence_time",
              "boundary_at": "2026-11-15T17:30:00Z",
              "earliest_confirmed_at": "2026-11-15T18:35:00Z",
              "latest_captured_at": "2026-11-15T18:36:00Z",
              "source": "sportsbooks",
              "basis": "consensus_spread_total",
              "bookmaker_count": 3,
              "unit": "goals",
              "period": "regulation"
            }
          },
          "prematch_odds": {
            "away_probability": 0.41,
            "draw_probability": 0.25,
            "home_probability": 0.34,
            "source": "kalshi"
          },
          "espn": {
            "period": "67'"
          }
        }
        """
    }

    // MARK: - 1. Discover, Feed & Search Live Columns + Bar Tick + Zero Grey Line

    func testDiscoverFeedAndSearchLiveCardsPrintScoreProjNowWithBarTickAndNoGreyLine() throws {
        let liveNFL = try decodeFeedEvent(liveNFLJSON)
        let prematch = PrematchReading.resolve(prematch: liveNFL.prematchOdds, opening: liveNFL.openingOdds)

        // A. Discover live card model
        let discoverModel = DiscoverSingleGameCard190C.build(
            event: liveNFL,
            prematch: prematch,
            usesPictureLayout: true
        )
        XCTAssertEqual(discoverModel.headers, .init(score: "Score", pregame: "Proj.", primary: "Now"))
        XCTAssertNil(discoverModel.scheduledProjectedLine)
        XCTAssertEqual(discoverModel.rows.map(\.scoreText), ["17", "21"])
        XCTAssertEqual(discoverModel.rows.map(\.pregameText), ["24", "28"])
        XCTAssertEqual(discoverModel.rows.map(\.primaryCell), [.probability("33.8%"), .probability("66.2%")])
        XCTAssertEqual(discoverModel.bar?.pregameNotch ?? -1, 0.42, accuracy: 0.001)

        // B. Feed / Sports live card headers & footer gate
        let feedProj = CompactGameCard12616.liveProjectedColumnLabels(
            printed: EventCardView(event: liveNFL, reason: "Detroit Lions leading after starting at 58%").liveProjectedFinal2920,
            awayScore: liveNFL.awayScore,
            homeScore: liveNFL.homeScore
        )
        XCTAssertEqual(feedProj?.away, "24")
        XCTAssertEqual(feedProj?.home, "28")
        XCTAssertEqual(
            CompactGameCard12616.columnHeaders(
                isScheduled: false, isLive: true, isFinished: false, isSuspended: false,
                hasProjectedBefore: false, hasCurrentChance: true, hasPrematchChance: true,
                hasScore: true, hasProjectedLive: feedProj != nil
            ),
            .init(medium: "Score", pregame: "Proj.", large: "Now")
        )
        XCTAssertFalse(
            EventCardView.EventCardFooter.hasContent(
                reason: "Detroit Lions leading after starting at 58%",
                isLive: true,
                sport: liveNFL.sport
            ),
            "Ruling 204-C: live feed card draws no grey sentence under the bar"
        )

        // C. Search live card adapter -> EventCardView preserves live_projection & pregame tick
        let searchEvent = try decodeSearchEvent(liveNBASearchJSON)
        let adaptedSearch = SearchEventCardAdapter183A.fromSearchResult(searchEvent, sportDisplayName: "NBA")
        let searchCard = EventCardView(event: adaptedSearch, reason: adaptedSearch.highlight?.label)
        let searchProj = CompactGameCard12616.liveProjectedColumnLabels(
            printed: searchCard.liveProjectedFinal2920,
            awayScore: adaptedSearch.awayScore,
            homeScore: adaptedSearch.homeScore
        )
        XCTAssertEqual(searchProj?.away, "118")
        XCTAssertEqual(searchProj?.home, "109")
        let searchPrematch = PrematchReading.resolve(prematch: adaptedSearch.prematchOdds, opening: adaptedSearch.openingOdds)
        XCTAssertEqual(
            CompactGameCard12616.pregameBarNotch(
                prematch: searchPrematch, isLive: true, isFinished: false, isSuspended: false
            ) ?? -1,
            0.54,
            accuracy: 0.001
        )
        XCTAssertFalse(
            EventCardView.EventCardFooter.hasContent(
                reason: adaptedSearch.highlight?.label,
                isLive: true,
                sport: adaptedSearch.sport
            )
        )

        // D. Opening-only fallback never places a fake pregame tick during play
        let openingOnlyEvent = try decodeFeedEvent("""
        {
          "id": 999,
          "sport": "americanfootball_nfl",
          "home_team": "Detroit Lions",
          "away_team": "New England Patriots",
          "status": "live",
          "opening_odds": { "home_probability": 0.58, "away_probability": 0.42 }
        }
        """)
        let openingOnly = PrematchReading.resolve(
            prematch: openingOnlyEvent.prematchOdds,
            opening: openingOnlyEvent.openingOdds
        )
        XCTAssertEqual(openingOnly?.isServed, false)
        XCTAssertNil(
            CompactGameCard12616.pregameBarNotch(
                prematch: openingOnly, isLive: true, isFinished: false, isSuspended: false
            ),
            "opening_odds must never masquerade as a live pregame tick"
        )

        // E. Regulation 3-way soccer formats goals to one decimal and leaves Draw's Proj. cell empty
        let liveSoccer = try decodeFeedEvent(liveSoccerJSON)
        let soccerModel = DiscoverSingleGameCard190C.build(
            event: liveSoccer,
            prematch: PrematchReading.resolve(prematch: liveSoccer.prematchOdds, opening: nil),
            usesPictureLayout: true
        )
        XCTAssertEqual(soccerModel.headers, .init(score: "Score", pregame: "Proj.", primary: "Now"))
        XCTAssertEqual(soccerModel.rows.map(\.kind), [.away, .draw, .home])
        XCTAssertEqual(soccerModel.rows.map(\.pregameText), ["1.0", nil, "1.6"])
        XCTAssertEqual(soccerModel.bar?.pregameNotch ?? -1, 0.41, accuracy: 0.001)

        // F. Game-page headline keeps its one grey pregame line (Ruling 200-B)
        let pageDetail = try decodeEventDetail(liveNFLJSON)
        let pageHeadline = EventSportHeadlines12472.resolve(
            event: pageDetail,
            awayFullName: pageDetail.awayTeam,
            homeFullName: pageDetail.homeTeam,
            liveStatusText: "Q3 · 8:14",
            hasScore: true,
            numberStreams: true,
            now: fixedNow
        )
        XCTAssertEqual(pageHeadline.columns.map(\.header), ["Score", "Proj.", "Now"])
        XCTAssertEqual(pageHeadline.livePregameSummary?.fullText, "Pregame  Lions 58% · projected 27–24")
    }

    // MARK: - 2. Fable #12775 Note: Served `MIN` / `GB` Abbreviations (Never `GBP`)

    func testScheduledDiscoverProjectedLineUsesServedTeamAbbreviationsNotGBP() throws {
        let scheduledPackers = try decodeFeedEvent("""
        {
          "id": 401201,
          "sport": "americanfootball_nfl",
          "sport_name": "NFL",
          "home_team": "Green Bay Packers",
          "away_team": "Minnesota Vikings",
          "commence_time": "2026-11-15T21:25:00Z",
          "status": "scheduled",
          "home_team_data": { "abbreviation": "GB", "primary_color": "#203731" },
          "away_team_data": { "abbreviation": "MIN", "primary_color": "#4F2683" },
          "current_odds": {
            "home_probability": 0.59,
            "away_probability": 0.41,
            "home_rendered_percent": 59,
            "away_rendered_percent": 41,
            "projected_home_score": 24.0,
            "projected_away_score": 21.0
          }
        }
        """)
        let model = DiscoverSingleGameCard190C.build(event: scheduledPackers, prematch: nil)
        XCTAssertEqual(model.scheduledProjectedLine, "Projected: MIN 21 \u{2013} GB 24")
        XCTAssertFalse(model.scheduledProjectedLine?.contains("GBP") ?? true)
        XCTAssertFalse(model.scheduledProjectedLine?.contains("VIK") ?? true)
    }

    // MARK: - 3. 390 px Render Sheet (Discover, Feed, Search, 3-Way Soccer, GB Before, Game-Page Control)

    func testExportRuling204CPhoneCardsSheetAt390px() throws {
        let liveNFL = try decodeFeedEvent(liveNFLJSON)
        let liveNFLHistory = try decodeHistory("""
        {
          "event_id": 401548,
          "home_team": "Detroit Lions",
          "away_team": "New England Patriots",
          "status": "live",
          "history": [],
          "win_prob_history": {
            "kalshi": [
              {"timestamp": "2026-11-15T18:05:00Z", "home_probability": 0.54},
              {"timestamp": "2026-11-15T18:22:00Z", "home_probability": 0.48},
              {"timestamp": "2026-11-15T18:40:00Z", "home_probability": 0.61},
              {"timestamp": "2026-11-15T18:55:00Z", "home_probability": 0.662}
            ]
          },
          "aggregate_line": [
            {"timestamp": "2026-11-15T18:05:00Z", "home_probability": 0.54},
            {"timestamp": "2026-11-15T18:22:00Z", "home_probability": 0.48},
            {"timestamp": "2026-11-15T18:40:00Z", "home_probability": 0.61},
            {"timestamp": "2026-11-15T18:55:00Z", "home_probability": 0.662}
          ]
        }
        """)
        let searchAdapted = SearchEventCardAdapter183A.fromSearchResult(
            try decodeSearchEvent(liveNBASearchJSON),
            sportDisplayName: "NBA"
        )
        let liveSoccer = try decodeFeedEvent(liveSoccerJSON)
        let scheduledPackers = try decodeFeedEvent("""
        {
          "id": 401201,
          "sport": "americanfootball_nfl",
          "sport_name": "NFL",
          "home_team": "Green Bay Packers",
          "away_team": "Minnesota Vikings",
          "commence_time": "2026-11-15T21:25:00Z",
          "status": "scheduled",
          "home_team_data": { "abbreviation": "GB", "primary_color": "#203731" },
          "away_team_data": { "abbreviation": "MIN", "primary_color": "#4F2683" },
          "current_odds": {
            "home_probability": 0.59,
            "away_probability": 0.41,
            "home_rendered_percent": 59,
            "away_rendered_percent": 41,
            "projected_home_score": 24.0,
            "projected_away_score": 21.0
          }
        }
        """)

        let pageDetail = try decodeEventDetail(liveNFLJSON)
        let pageHeadlineModel = EventSportHeadlines12472.resolve(
            event: pageDetail,
            awayFullName: pageDetail.awayTeam,
            homeFullName: pageDetail.homeTeam,
            liveStatusText: "Q3 · 8:14",
            hasScore: true,
            numberStreams: true,
            now: fixedNow
        )
        let pageColors = TeamTextContrast.cardColors(
            awayHex: pageDetail.awayTeamData?.primaryColor,
            homeHex: pageDetail.homeTeamData?.primaryColor
        )

        let sheet = VStack(alignment: .leading, spacing: 14) {
            VStack(alignment: .leading, spacing: 2) {
                Text("Ruling 204-C — Phone Live Cards (390 px)")
                    .font(.subheadline.weight(.bold))
                    .foregroundStyle(Color(hex: "#111827"))
                Text("Score · Proj. · Now, pregame tick on bar, zero grey line; Game Page keeps 200-B grey line")
                    .font(.caption2)
                    .foregroundStyle(Color(hex: "#6B7280"))
            }

            sectionCard(title: "1. Discover Live Card (Score · Proj. · Now, bar tick at 42%, 191-A chart, no grey line)") {
                NativeEventDiscoverCard(
                    event: liveNFL,
                    feedContext: "Detroit Lions leading after starting at 58%",
                    expandedContext: nil,
                    navigationPath: .constant(NavigationPath()),
                    chartHistory: liveNFLHistory
                )
            }

            sectionCard(title: "2. Sports / Feed Live Card (Score · Proj. · Now, bar tick at 42%, no grey line)") {
                EventCardView(
                    event: liveNFL,
                    reason: "Detroit Lions leading after starting at 58%"
                )
                .padding(.horizontal, 14)
                .padding(.vertical, 8)
                .background(Color.white, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
            }

            sectionCard(title: "3. Search Live Card (NBA: Score · Proj. · Now, bar tick at 54%, no grey line)") {
                EventCardView(
                    event: searchAdapted,
                    reason: searchAdapted.highlight?.label
                )
                .padding(.horizontal, 14)
                .padding(.vertical, 8)
                .background(Color.white, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
            }

            sectionCard(title: "4. Feed Live 3-Way Soccer Card (Score · Proj. 1.0/1.6 · Now, Draw in middle, bar tick)") {
                EventCardView(
                    event: liveSoccer,
                    reason: "Chelsea leading after starting at 34%"
                )
                .padding(.horizontal, 14)
                .padding(.vertical, 8)
                .background(Color.white, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
            }

            sectionCard(title: "5. Discover Before Game (#12775 fix: served MIN / GB, never VIK / GBP)") {
                NativeEventDiscoverCard(
                    event: scheduledPackers,
                    feedContext: "Winner takes sole possession of first in the NFC North.",
                    expandedContext: nil,
                    navigationPath: .constant(NavigationPath())
                )
            }

            sectionCard(title: "6. Game-Page Headline Control (keeps its one 200-B grey pregame line)") {
                EventSportHeadlineCard12472(
                    model: pageHeadlineModel,
                    colors: pageColors,
                    ekgTracker: .empty,
                    liveUpdateStatus: .awaitingUpdate,
                    displayAsOf: fixedNow,
                    updateStream: LiveUpdateStream(),
                    showUpdateStream: .constant(false),
                    showProbabilityDetails: .constant(false),
                    priceStreamingEligible: true,
                    lastReceivedAt: fixedNow,
                    confirmedAt: fixedNow,
                    revealForecast: nil
                )
            }
        }
        .padding(16)
        .frame(width: 390)
        .background(Color(hex: "#F3F4F6"))
        .environmentObject(PinManager(
            defaults: UserDefaults(suiteName: "LiveCardColumns204CTests")!,
            serverLoad: { PinsResponse(events: [], futures: []) },
            serverSync: { _, _, _ in }
        ))
        .environmentObject(NavigationCoordinator())
        .environment(\.colorScheme, .light)

        let host = hostForMeasurement(sheet, at: .large)
        host.overrideUserInterfaceStyle = .light
        let fitting = host.sizeThatFits(in: CGSize(width: 390, height: 12_000))
        host.view.frame = CGRect(x: 0, y: 0, width: 390, height: max(fitting.height, 400))
        let scene = UIApplication.shared.connectedScenes.compactMap({ $0 as? UIWindowScene }).first
        let window: UIWindow = scene.map { UIWindow(windowScene: $0) } ?? UIWindow(frame: host.view.frame)
        window.frame = host.view.frame
        window.overrideUserInterfaceStyle = .light
        window.rootViewController = host
        window.isHidden = false
        defer {
            window.isHidden = true
            window.rootViewController = nil
        }
        let until = Date().addingTimeInterval(0.25)
        repeat {
            let nextH = max(host.sizeThatFits(in: CGSize(width: 390, height: 12_000)).height, 400)
            if abs(host.view.frame.height - nextH) > 0.5 {
                host.view.frame = CGRect(x: 0, y: 0, width: 390, height: nextH)
                window.frame = host.view.frame
            }
            host.view.setNeedsLayout()
            host.view.layoutIfNeeded()
            RunLoop.current.run(until: Date().addingTimeInterval(0.02))
        } while Date() < until

        let fmt = UIGraphicsImageRendererFormat()
        fmt.scale = 3.0
        let image = UIGraphicsImageRenderer(bounds: host.view.bounds, format: fmt).image { _ in
            _ = host.view.drawHierarchy(in: host.view.bounds, afterScreenUpdates: true)
        }
        XCTAssertEqual(Int(image.size.width.rounded()), 390)
        XCTAssertGreaterThan(image.size.height, 600)

        if let exportDir = ProcessInfo.processInfo.environment["RULING_204C_EXPORT_DIR"],
           !exportDir.isEmpty {
            let dirURL = URL(fileURLWithPath: exportDir, isDirectory: true)
            try FileManager.default.createDirectory(at: dirURL, withIntermediateDirectories: true)
            let data = try XCTUnwrap(image.pngData())
            try data.write(to: dirURL.appendingPathComponent("ruling-204c-phone-live-cards-390.png"))
        }
    }

    @ViewBuilder
    private func sectionCard<Content: View>(title: String, @ViewBuilder content: () -> Content) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(title)
                .font(.caption.weight(.semibold))
                .foregroundStyle(Color(hex: "#374151"))
            content()
        }
    }
}
