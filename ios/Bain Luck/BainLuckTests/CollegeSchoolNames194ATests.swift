import SwiftUI
import UIKit
import XCTest
@testable import Bain_Luck

@MainActor
final class CollegeSchoolNames194ATests: XCTestCase {

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

    func testCollegeTeamsPrintSchoolNotMascotWhileProTeamsStayUnchanged() {
        let ncaaf = "americanfootball_ncaaf"
        let ncaab = "basketball_ncaab"
        let wncaab = "basketball_wncaab"

        // Ruling 194-A named specimens
        XCTAssertEqual(TeamShortName.short("Duke Blue Devils", sportKey: ncaab), "Duke")
        XCTAssertEqual(TeamShortName.short("Alabama Crimson Tide", sportKey: ncaaf), "Alabama")
        XCTAssertEqual(TeamShortName.short("Gonzaga Bulldogs", sportKey: ncaab), "Gonzaga")
        XCTAssertEqual(TeamShortName.short("Ole Miss Rebels", sportKey: ncaaf), "Ole Miss")

        // Additional multi-word schools & mascots + idempotence
        XCTAssertEqual(TeamShortName.short("Texas A&M Aggies", sportKey: ncaaf), "Texas A&M")
        XCTAssertEqual(TeamShortName.short("North Carolina Tar Heels", sportKey: ncaab), "North Carolina")
        XCTAssertEqual(TeamShortName.short("St. John's Red Storm", sportKey: ncaab), "St. John's")
        XCTAssertEqual(TeamShortName.short("Tennessee Lady Volunteers", sportKey: wncaab), "Tennessee")
        XCTAssertEqual(TeamShortName.short("Miami (FL) Hurricanes", sportKey: ncaaf), "Miami (FL)")
        XCTAssertEqual(TeamShortName.short("Ole Miss", sportKey: ncaaf), "Ole Miss")
        XCTAssertEqual(TeamShortName.short("Texas A&M", sportKey: ncaaf), "Texas A&M")

        // Pair resolution
        let secPair = TeamShortName.shortPair(
            away: "Ole Miss Rebels",
            home: "Alabama Crimson Tide",
            sportKey: ncaaf
        )
        XCTAssertEqual(secPair.away, "Ole Miss")
        XCTAssertEqual(secPair.home, "Alabama")

        // Professional teams unchanged
        XCTAssertEqual(TeamShortName.short("Boston Celtics", sportKey: "basketball_nba"), "Celtics")
        XCTAssertEqual(TeamShortName.short("Boston Red Sox", sportKey: "baseball_mlb"), "Red Sox")
        XCTAssertEqual(TeamShortName.short("Toronto Maple Leafs", sportKey: "icehockey_nhl"), "Maple Leafs")
        XCTAssertEqual(TeamShortName.short("Vegas Golden Knights", sportKey: "icehockey_nhl"), "Golden Knights")
        XCTAssertEqual(TeamShortName.short("Portland Trail Blazers", sportKey: "basketball_nba"), "Trail Blazers")
        XCTAssertEqual(TeamShortName.short("Kansas City Chiefs", sportKey: "americanfootball_nfl"), "Chiefs")
    }

    func testMissingLogoBadgeUsesServedAbbreviationAndNeverMascot() {
        let ncaab = "basketball_ncaab"
        let ncaaf = "americanfootball_ncaaf"

        XCTAssertEqual(
            TeamLogoView.badge(
                teamName: "Duke Blue Devils",
                opponentName: "North Carolina Tar Heels",
                sportKey: ncaab,
                servedAbbreviation: "DUKE",
                opponentAbbreviation: "UNC"
            ),
            "DUKE"
        )
        XCTAssertEqual(
            TeamLogoView.badge(
                teamName: "Alabama Crimson Tide",
                opponentName: "Ole Miss Rebels",
                sportKey: ncaaf,
                servedAbbreviation: "ALA",
                opponentAbbreviation: "MISS"
            ),
            "ALA"
        )
        // Solo missing-logo circle also uses served abbreviation
        XCTAssertEqual(
            TeamLogoView.badge(
                teamName: "Duke Blue Devils",
                opponentName: nil,
                sportKey: ncaab,
                servedAbbreviation: "DUKE"
            ),
            "DUKE"
        )
        // Unserved fallback derives from school, never mascot (`GON`, not `BUL`)
        XCTAssertEqual(
            TeamLogoView.badge(
                teamName: "Gonzaga Bulldogs",
                opponentName: "Purdue Boilermakers",
                sportKey: ncaab
            ),
            "GON"
        )
    }

    func testWidgetAndWatchPrintCollegeSchoolNamesEverywhere() throws {
        let widgetJSON = #"""
        {
          "id": 9194001,
          "sport": "basketball_ncaab",
          "home_team": "Duke Blue Devils",
          "away_team": "Gonzaga Bulldogs",
          "status": "scheduled",
          "commence_time": "2026-11-14T23:30:00Z",
          "hero_probability": 0.56,
          "hero_probability_away": 0.44,
          "hero_probability_source": "blend",
          "hero_probability_observed_at": "2026-11-14T17:55:00Z",
          "home_team_data": { "abbreviation": "DUKE", "primary_color": "#003087" },
          "away_team_data": { "abbreviation": "GONZ", "primary_color": "#041E42" }
        }
        """#
        let widgetEvent = try SavedWidgetDetailDecoding10875.decoder().decode(
            SavedWidgetEventDetail10875.self,
            from: Data(widgetJSON.utf8)
        )
        let reading = SavedWidgetReadingRules10875.game(widgetEvent, side: nil, now: fixedNow)
        XCTAssertEqual(reading.subject, "Gonzaga vs Duke")
        XCTAssertEqual(reading.shortSubject, "GONZ vs DUKE")
        XCTAssertEqual(reading.rows.map(\.label), ["Gonzaga", "Duke"])
        XCTAssertEqual(reading.rows.map(\.shortLabel), ["GONZ", "DUKE"])
        XCTAssertFalse(reading.spoken.contains("Blue Devils"))
        XCTAssertFalse(reading.spoken.contains("Bulldogs"))

        let watchJSON = #"""
        {
          "id": 9194002,
          "sport": "americanfootball_ncaaf",
          "home_team": "Alabama Crimson Tide",
          "away_team": "Ole Miss Rebels",
          "status": "live",
          "home_score": 24,
          "away_score": 21,
          "score_observed_at": "2026-11-14T17:59:30Z",
          "hero_probability": 0.63,
          "hero_probability_away": 0.37,
          "hero_probability_observed_at": "2026-11-14T17:59:40Z",
          "home_team_data": { "team_id": 333, "abbreviation": "ALA" },
          "away_team_data": { "team_id": 145, "abbreviation": "MISS" }
        }
        """#
        let watchGame = try JSONDecoder().decode(WatchSelectedGame.self, from: Data(watchJSON.utf8))
        XCTAssertEqual(watchGame.awayTeam, "Ole Miss")
        XCTAssertEqual(watchGame.homeTeam, "Alabama")

        let watchFeedJSON = #"""
        {
          "items": [
            {
              "type": "event",
              "score": 90,
              "data": {
                "id": 9194002,
                "sport": "americanfootball_ncaaf",
                "home_team": "Alabama Crimson Tide",
                "away_team": "Ole Miss Rebels",
                "status": "live",
                "home_team_data": { "abbreviation": "ALA" },
                "away_team_data": { "abbreviation": "MISS" }
              }
            }
          ]
        }
        """#
        let feedDecoder = JSONDecoder()
        feedDecoder.keyDecodingStrategy = .convertFromSnakeCase
        let watchFeed = try feedDecoder.decode(WatchFeedResponse.self, from: Data(watchFeedJSON.utf8))
        let feedEvent = try XCTUnwrap(watchFeed.items.first?.event)
        XCTAssertEqual(feedEvent.displayTeams().away, "Ole Miss")
        XCTAssertEqual(feedEvent.displayTeams().home, "Alabama")
        XCTAssertEqual(feedEvent.awayAbbrev(), "MISS")
        XCTAssertEqual(feedEvent.homeAbbrev(), "ALA")
    }

    func testCollegeFootballAndBasketballPagesBeforeDuringAfterRender390px() async throws {
        let ncaafBefore = try makeEvent(
            id: 9194101,
            sport: "americanfootball_ncaaf",
            awayTeam: "Ole Miss Rebels",
            awayAbbr: "MISS",
            awayColor: "#CE1126",
            awayRecord: "8-2",
            homeTeam: "Alabama Crimson Tide",
            homeAbbr: "ALA",
            homeColor: "#9E1B32",
            homeRecord: "8-2",
            status: "scheduled",
            commenceTime: "2026-11-15T00:30:00Z",
            awayScore: nil,
            homeScore: nil,
            projAway: 24.5,
            projHome: 28.5,
            openHome: 0.56,
            nowHome: 0.59,
            period: nil,
            clock: nil,
            broadcast: "ABC"
        )
        let ncaafDuring = try makeEvent(
            id: 9194102,
            sport: "americanfootball_ncaaf",
            awayTeam: "Alabama Crimson Tide",
            awayAbbr: "ALA",
            awayColor: "#9E1B32",
            awayRecord: "8-2",
            homeTeam: "LSU Tigers",
            homeAbbr: "LSU",
            homeColor: "#461D7C",
            homeRecord: "6-3",
            status: "live",
            commenceTime: "2026-11-14T16:30:00Z",
            awayScore: 24,
            homeScore: 17,
            projAway: 31.5,
            projHome: 24.5,
            openHome: 0.44,
            nowHome: 0.284,
            period: "3",
            clock: "6:18",
            broadcast: "CBS"
        )
        let ncaafAfter = try makeEvent(
            id: 9194103,
            sport: "americanfootball_ncaaf",
            awayTeam: "Ole Miss Rebels",
            awayAbbr: "MISS",
            awayColor: "#CE1126",
            awayRecord: "9-2",
            homeTeam: "Georgia Bulldogs",
            homeAbbr: "UGA",
            homeColor: "#111827",
            homeRecord: "8-2",
            status: "completed",
            commenceTime: "2026-11-09T20:30:00Z",
            awayScore: 28,
            homeScore: 10,
            projAway: 24.0,
            projHome: 27.0,
            openHome: 0.58,
            nowHome: 0.0,
            period: "4",
            clock: "0:00",
            broadcast: "ABC"
        )

        let ncaabBefore = try makeEvent(
            id: 9194201,
            sport: "basketball_ncaab",
            awayTeam: "Gonzaga Bulldogs",
            awayAbbr: "GONZ",
            awayColor: "#041E42",
            awayRecord: "3-0",
            homeTeam: "Duke Blue Devils",
            homeAbbr: "DUKE",
            homeColor: "#003087",
            homeRecord: "3-0",
            status: "scheduled",
            commenceTime: "2026-11-15T01:00:00Z",
            awayScore: nil,
            homeScore: nil,
            projAway: 76.5,
            projHome: 79.5,
            openHome: 0.54,
            nowHome: 0.58,
            period: nil,
            clock: nil,
            broadcast: "ESPN"
        )
        let ncaabDuring = try makeEvent(
            id: 9194202,
            sport: "basketball_ncaab",
            awayTeam: "Duke Blue Devils",
            awayAbbr: "DUKE",
            awayColor: "#003087",
            awayRecord: "3-0",
            homeTeam: "Louisville Cardinals",
            homeAbbr: "LOU",
            homeColor: "#AD0000",
            homeRecord: "2-1",
            status: "live",
            commenceTime: "2026-11-14T17:00:00Z",
            awayScore: 68,
            homeScore: 61,
            projAway: 82.5,
            projHome: 76.5,
            openHome: 0.36,
            nowHome: 0.242,
            period: "2",
            clock: "5:44",
            broadcast: "ESPN"
        )
        let ncaabAfter = try makeEvent(
            id: 9194203,
            sport: "basketball_ncaab",
            awayTeam: "Gonzaga Bulldogs",
            awayAbbr: "GONZ",
            awayColor: "#041E42",
            awayRecord: "4-0",
            homeTeam: "Baylor Bears",
            homeAbbr: "BAY",
            homeColor: "#154734",
            homeRecord: "2-1",
            status: "completed",
            commenceTime: "2026-11-11T03:00:00Z",
            awayScore: 89,
            homeScore: 76,
            projAway: 78.0,
            projHome: 75.0,
            openHome: 0.43,
            nowHome: 0.0,
            period: "2",
            clock: "0:00",
            broadcast: "ESPN2"
        )

        for event in [ncaafBefore, ncaafDuring, ncaafAfter, ncaabBefore, ncaabDuring, ncaabAfter] {
            let model = try XCTUnwrap(
                EventSportHeadlines12472.resolve(
                    event: event,
                    awayFullName: event.awayTeam,
                    homeFullName: event.homeTeam,
                    liveStatusText: PeriodLabel.liveStatusText(period: event.espn?.period, gameClock: event.espn?.gameClock),
                    hasScore: event.homeScore != nil && event.awayScore != nil,
                    numberStreams: event.status == "live",
                    now: fixedNow
                )
            )
            for forbidden in ["Blue Devils", "Crimson Tide", "Bulldogs", "Rebels", "Tigers", "Cardinals", "Bears"] {
                XCTAssertNotEqual(model.away.shortName, forbidden)
                XCTAssertNotEqual(model.home.shortName, forbidden)
            }
            XCTAssertNotNil(model.away.abbreviation)
            XCTAssertNotNil(model.home.abbreviation)
        }

        if let outDir = ProcessInfo.processInfo.environment["EXPORT_194A_RENDERS_DIR"],
           !outDir.isEmpty {
            let dirURL = URL(fileURLWithPath: outDir, isDirectory: true)
            try FileManager.default.createDirectory(at: dirURL, withIntermediateDirectories: true)

            let pages: [(String, EventDetail, Double, Double)] = [
                ("194a-ncaaf-before-390x852.png", ncaafBefore, 0.56, 0.59),
                ("194a-ncaaf-during-390x852.png", ncaafDuring, 0.44, 0.284),
                ("194a-ncaaf-after-390x852.png", ncaafAfter, 0.58, 0.0),
                ("194a-ncaab-before-390x852.png", ncaabBefore, 0.54, 0.58),
                ("194a-ncaab-during-390x852.png", ncaabDuring, 0.36, 0.242),
                ("194a-ncaab-after-390x852.png", ncaabAfter, 0.43, 0.0),
            ]
            for (filename, event, startH, endH) in pages {
                let page = try await makeFullPage(event, startHome: startH, endHome: endH)
                try await writeHostedPNG(
                    page,
                    size: CGSize(width: 390, height: 852),
                    to: dirURL.appendingPathComponent(filename)
                )
            }
        }
    }

    private func makeEvent(
        id: Int,
        sport: String,
        awayTeam: String,
        awayAbbr: String,
        awayColor: String,
        awayRecord: String,
        homeTeam: String,
        homeAbbr: String,
        homeColor: String,
        homeRecord: String,
        status: String,
        commenceTime: String,
        awayScore: Int?,
        homeScore: Int?,
        projAway: Double,
        projHome: Double,
        openHome: Double,
        nowHome: Double,
        period: String?,
        clock: String?,
        broadcast: String
    ) throws -> EventDetail {
        let openAway = 1.0 - openHome
        let nowAway = status == "completed" ? (nowHome == 1.0 ? 0.0 : 1.0) : (1.0 - nowHome)
        let homePct = Int((nowHome * 100).rounded())
        let awayPct = 100 - homePct
        let openHomePct = Int((openHome * 100).rounded())
        let openAwayPct = 100 - openHomePct
        let scoresJSON: String = {
            guard let awayScore, let homeScore else { return "" }
            return #""away_score": \#(awayScore), "home_score": \#(homeScore),"#
        }()
        let liveProjJSON: String = status == "live"
            ? #","live_projection": { "home_points": \#(projHome), "away_points": \#(projAway), "basis": "live_model" }"#
            : ""
        let espnPeriodJSON: String = {
            guard let period, let clock else { return #""broadcast": "\#(broadcast)""# }
            return #""period": "\#(period)", "game_clock": "\#(clock)", "broadcast": "\#(broadcast)""#
        }()
        let json = """
        {
          "id": \(id),
          "sport": "\(sport)",
          "home_team": "\(homeTeam)",
          "away_team": "\(awayTeam)",
          "commence_time": "\(commenceTime)",
          "status": "\(status)",
          \(scoresJSON)
          "home_team_data": {
            "abbreviation": "\(homeAbbr)",
            "primary_color": "\(homeColor)",
            "record": "\(homeRecord)"
          },
          "away_team_data": {
            "abbreviation": "\(awayAbbr)",
            "primary_color": "\(awayColor)",
            "record": "\(awayRecord)"
          },
          "current_odds": {
            "projected_home_score": \(projHome),
            "projected_away_score": \(projAway),
            "home_probability": \(nowHome),
            "away_probability": \(nowAway),
            "home_rendered_percent": \(homePct),
            "away_rendered_percent": \(awayPct),
            "updated_at": "2026-11-14T17:58:00Z"\(liveProjJSON)
          },
          "opening_odds": {
            "home_probability": \(openHome),
            "away_probability": \(openAway),
            "home_rendered_percent": \(openHomePct),
            "away_rendered_percent": \(openAwayPct)
          },
          "hero_probability": \(nowHome),
          "hero_probability_away": \(nowAway),
          "hero_probability_source": "blend",
          "hero_probability_observed_at": "2026-11-14T17:58:00Z",
          "espn": {
            \(espnPeriodJSON)
          },
          "win_probability_sources": {
            "betting": { "value": \(nowHome), "display_name": "Sportsbooks" },
            "kalshi": { "value": \(nowHome), "display_name": "Kalshi" },
            "polymarket": { "value": \(nowHome), "display_name": "Polymarket" }
          },
          "source_mark": {
            "state": "blend",
            "sources": [
              { "key": "kalshi", "name": "Kalshi", "probability": \(nowHome), "observed_at": "2026-11-14T17:58:00Z" },
              { "key": "polymarket", "name": "Polymarket", "probability": \(nowHome), "observed_at": "2026-11-14T17:57:50Z" },
              { "key": "betting", "name": "Sportsbooks", "probability": \(nowHome), "count": 5, "observed_at": "2026-11-14T17:57:30Z" }
            ]
          }
        }
        """
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(EventDetail.self, from: Data(json.utf8))
    }

    private func makeHistory(event: EventDetail, startHome: Double, endHome: Double) throws -> EventHistoryResponse {
        let iso = ISO8601DateFormatter()
        let base: Date
        let offsets: [TimeInterval]
        if event.status == "scheduled" {
            base = iso.date(from: "2026-11-14T15:00:00Z")!
            offsets = [0, 3600, 7200, 10680]
        } else {
            base = event.commenceTime?.asDate ?? iso.date(from: "2026-11-14T16:30:00Z")!
            offsets = [0, 1800, 3600, 5280]
        }
        let p0 = startHome
        let p1 = startHome + (endHome - startHome) * 0.35
        let p2 = startHome + (endHome - startHome) * 0.72
        let p3 = endHome
        let t0 = iso.string(from: base.addingTimeInterval(offsets[0]))
        let t1 = iso.string(from: base.addingTimeInterval(offsets[1]))
        let t2 = iso.string(from: base.addingTimeInterval(offsets[2]))
        let t3 = iso.string(from: base.addingTimeInterval(offsets[3]))
        let json = """
        {
          "event_id": \(event.id),
          "home_team": "\(event.homeTeam)",
          "away_team": "\(event.awayTeam)",
          "history": [
            { "timestamp": "\(t0)", "home_probability": \(p0), "away_probability": \(1.0 - p0), "source": "aggregate" },
            { "timestamp": "\(t1)", "home_probability": \(p1), "away_probability": \(1.0 - p1), "source": "aggregate" },
            { "timestamp": "\(t2)", "home_probability": \(p2), "away_probability": \(1.0 - p2), "source": "aggregate" },
            { "timestamp": "\(t3)", "home_probability": \(p3), "away_probability": \(1.0 - p3), "source": "aggregate" }
          ]
        }
        """
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(EventHistoryResponse.self, from: Data(json.utf8))
    }

    private func makeFullPage(_ event: EventDetail, startHome: Double, endHome: Double) async throws -> AnyView {
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

    private func writeHostedPNG<V: View>(
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
}
