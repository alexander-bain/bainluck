import SwiftUI
import UIKit
import XCTest
@testable import Bain_Luck

/// Saturday Night Continuation List — Item 7: iPad (`834×1194`) and Mac (`1280×840`) Pass.
///
/// Renders every reader-facing `1.0.7` screen at:
/// 1. **iPad (`834×1194`, `horizontalSizeClass = .regular`)**
/// 2. **Mac (`1280×840`, `220 pt` `MacMainWindow10878` sidebar + `1060 pt` detail pane)**
/// and asserts bounded readable column widths across single-column detail, tournament,
/// fight-card, and preferences surfaces.
@MainActor
final class IPadAndMacPassSat7Tests: XCTestCase {

    private let fixedNow = ISO8601DateFormatter().date(from: "2026-11-15T20:00:00Z")!

    private static var testsDir: URL {
        URL(fileURLWithPath: #filePath).deletingLastPathComponent()
    }

    private static var snakeDecoder: JSONDecoder {
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        return d
    }

    private func fixtureData(_ name: String) throws -> Data {
        try Data(contentsOf: Self.testsDir.appendingPathComponent("Fixtures").appendingPathComponent(name))
    }

    // MARK: - Deterministic Providers

    private nonisolated struct StubDiscoverProvider: DiscoverFeedProviding {
        let page: FeedResponse
        func fetchDiscoverFeed(
            limit: Int,
            offset: Int,
            eventPct: Double?,
            cacheTTL: TimeInterval?
        ) async throws -> FeedResponse {
            page
        }
    }

    private nonisolated struct StubSportsProvider: SportsFeedProviding {
        let main: FeedResponse
        let empty: FeedResponse
        let grouped: GroupedFeedResponse
        func fetchSportsFeed() async throws -> FeedResponse { main }
        func fetchSportsEventBackfill(limit: Int) async throws -> FeedResponse { empty }
        func fetchSportsGroupedFeed(limit: Int) async throws -> GroupedFeedResponse { grouped }
    }

    private nonisolated struct StubFuturesProvider: FuturesDetailProviding {
        let detail: FuturesMarketDetail
        func fetchFuturesDetail(id: Int) async throws -> FuturesMarketDetail { detail }
    }

    private nonisolated struct StubEventProvider: EventDetailProviding {
        struct StubUnavailable: Error {}
        let detail: EventDetail
        let history: EventHistoryResponse
        func fetchEvent(id: Int) async throws -> EventDetail { detail }
        func fetchEventHistory(id: Int, hours: Int) async throws -> EventHistoryResponse { history }
        func fetchRelatedFutures(eventId: Int) async throws -> RelatedFuturesResponse { throw StubUnavailable() }
        func fetchTeamProgression(eventId: Int) async throws -> TeamProgressionResponse { throw StubUnavailable() }
        func fetchGameMarkets(eventId: Int) async throws -> GameMarketsResponse { throw StubUnavailable() }
        func fetchLineMovement(eventId: Int) async throws -> LineMovementResponse { throw StubUnavailable() }
    }

    // MARK: - Mac Chrome Wrapper (mirrors `MacMainWindowView` on iOS Simulator host)

    private struct MacWindowChromePreview<Detail: View>: View {
        let activeTab: AppTab
        let detail: Detail

        var body: some View {
            HStack(spacing: 0) {
                VStack(alignment: .leading, spacing: 4) {
                    HStack(spacing: 6) {
                        Circle().fill(Color(hex: "#FF5F57")).frame(width: 11, height: 11)
                        Circle().fill(Color(hex: "#FEBC2E")).frame(width: 11, height: 11)
                        Circle().fill(Color(hex: "#28C840")).frame(width: 11, height: 11)
                    }
                    .padding(.horizontal, 14)
                    .padding(.top, 12)
                    .padding(.bottom, 10)

                    ForEach(MacMainWindow10878.destinations) { item in
                        sidebarItemRow(item, selected: item.tab == activeTab)
                    }

                    Text("Quick Links")
                        .font(.caption2.weight(.semibold))
                        .foregroundStyle(.secondary)
                        .padding(.horizontal, 14)
                        .padding(.top, 12)
                        .padding(.bottom, 2)

                    ForEach(MacMainWindow10878.quickLinks) { item in
                        sidebarItemRow(item, selected: item.tab == activeTab)
                    }

                    Spacer()
                }
                .frame(width: MacMainWindow10878.sidebarIdealWidth)
                .background(Color(uiColor: .secondarySystemBackground))

                Rectangle()
                    .fill(Color(uiColor: .separator).opacity(0.45))
                    .frame(width: 1)

                ZStack(alignment: .top) {
                    Color(uiColor: .systemGroupedBackground)
                    detail
                        .environment(\.horizontalSizeClass, MacMainWindow10878.detailSizeClass)
                        .frame(maxWidth: MacMainWindow10878.readableContentWidth)
                        .frame(maxWidth: .infinity, maxHeight: .infinity)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            }
            .environment(\.colorScheme, .light)
        }

        private func sidebarItemRow(_ item: MacMainWindow10878.SidebarItem, selected: Bool) -> some View {
            HStack(spacing: 8) {
                Image(systemName: item.systemImage)
                    .font(.system(size: 13, weight: .medium))
                    .frame(width: 18)
                Text(item.title)
                    .font(.system(size: 13, weight: selected ? .semibold : .regular))
                Spacer(minLength: 0)
            }
            .foregroundStyle(selected ? Color.accentColor : Color.primary)
            .padding(.horizontal, 10)
            .padding(.vertical, 6)
            .background(
                RoundedRectangle(cornerRadius: 7, style: .continuous)
                    .fill(selected ? Color.accentColor.opacity(0.12) : Color.clear)
            )
            .padding(.horizontal, 8)
        }
    }

    // MARK: - Build All 12 `1.0.7` Screens

    private struct ScreenSpecimen {
        let id: String
        let title: String
        let macTab: AppTab
        let makeView: () -> AnyView
    }

    private func buildTwelveScreens() async throws -> [ScreenSpecimen] {
        let dec = Self.snakeDecoder
        let auth = AuthManager()
        let pins = PinManager(
            defaults: UserDefaults(suiteName: "IPadAndMacPassSat7Tests")!,
            serverLoad: { PinsResponse(events: [], futures: []) },
            serverSync: { _, _, _ in }
        )

        // 1. Discover Feed (production 30-item feed + live NFL & scheduled NBA game cards at top)
        let prodFeedObj = try JSONSerialization.jsonObject(with: Data(DiscoverFeedProdFixture.json.utf8)) as! [String: Any]
        let prodRawItems = (prodFeedObj["items"] as? [[String: Any]]) ?? []
        let liveGameJSON = """
        {
          "type": "event",
          "headline": "Live NFL",
          "reason": "Down to the wire",
          "data": {
            "id": 9101,
            "sport": "americanfootball_nfl",
            "sport_name": "NFL",
            "home_team": "Detroit Lions",
            "away_team": "New England Patriots",
            "commence_time": "2026-11-15T18:00:00Z",
            "status": "live",
            "home_score": 24,
            "away_score": 17,
            "home_team_data": { "abbreviation": "DET", "primary_color": "#0076B6", "record": "7-2" },
            "away_team_data": { "abbreviation": "NE", "primary_color": "#002244", "secondary_color": "#C60C30", "record": "6-3" },
            "current_odds": {
              "home_probability": 0.684,
              "away_probability": 0.316,
              "home_rendered_percent": 68,
              "away_rendered_percent": 32,
              "projected_home_score": 28.0,
              "projected_away_score": 24.0
            },
            "prematch_odds": {
              "home_probability": 0.58,
              "away_probability": 0.42,
              "home_rendered_percent": 58,
              "away_rendered_percent": 42
            },
            "espn": { "period": "3", "game_clock": "6:12" }
          }
        }
        """
        let scheduledGameJSON = """
        {
          "type": "event",
          "headline": "Tonight",
          "data": {
            "id": 9102,
            "sport": "basketball_nba",
            "sport_name": "NBA",
            "home_team": "Boston Celtics",
            "away_team": "New York Knicks",
            "commence_time": "2026-11-16T00:30:00Z",
            "status": "scheduled",
            "home_team_data": { "abbreviation": "BOS", "primary_color": "#007A33", "record": "9-3" },
            "away_team_data": { "abbreviation": "NYK", "primary_color": "#006BB6", "secondary_color": "#F58426", "record": "7-5" },
            "current_odds": {
              "home_probability": 0.58,
              "away_probability": 0.42,
              "home_rendered_percent": 58,
              "away_rendered_percent": 42,
              "projected_home_score": 115.0,
              "projected_away_score": 109.0
            },
            "espn": { "broadcast": "ESPN" }
          }
        }
        """
        let liveObj = try JSONSerialization.jsonObject(with: Data(liveGameJSON.utf8)) as! [String: Any]
        let schedObj = try JSONSerialization.jsonObject(with: Data(scheduledGameJSON.utf8)) as! [String: Any]
        let combinedDiscoverDict: [String: Any] = [
            "items": [liveObj, schedObj] + Array(prodRawItems.prefix(10)),
            "total": 12,
            "limit": 50,
            "offset": 0,
            "has_more": false,
            "edition": "ed-ipad-mac",
        ]
        let discoverFeedResponse = try dec.decode(
            FeedResponse.self,
            from: try JSONSerialization.data(withJSONObject: combinedDiscoverDict)
        )
        let discoverPlace = MacReadingPlace<DiscoverViewModel>()
        let discoverVM = discoverPlace.models {
            DiscoverViewModel(client: StubDiscoverProvider(page: discoverFeedResponse), lastGood: nil)
        }
        _ = await discoverVM.load()

        // 2. Sports Feed (`FeedView`)
        let sportsFuturesObjs = prodRawItems.filter { ($0["type"] as? String) == "futures" }.prefix(4)
        let sportsFeedDict: [String: Any] = [
            "items": [liveObj, schedObj] + Array(sportsFuturesObjs),
            "total": 6,
            "limit": 20,
            "offset": 0,
            "has_more": false,
        ]
        let sportsFeedResponse = try dec.decode(
            FeedResponse.self,
            from: try JSONSerialization.data(withJSONObject: sportsFeedDict)
        )
        let emptyFeedResponse = try dec.decode(
            FeedResponse.self,
            from: Data(#"{"items":[],"total":0,"limit":50,"offset":0,"has_more":false}"#.utf8)
        )
        let emptyGroupedResponse = try dec.decode(
            GroupedFeedResponse.self,
            from: Data(#"{"feed":[],"total":0,"limit":20,"offset":0}"#.utf8)
        )
        let sportsVM = FeedViewModel(
            client: StubSportsProvider(main: sportsFeedResponse, empty: emptyFeedResponse, grouped: emptyGroupedResponse),
            telemetry: nil,
            autoRefreshEnabled: false
        )
        await sportsVM.startLoad()

        // 4. Search (`SearchView`)
        let searchResp = try dec.decode(SearchResponse.self, from: try fixtureData("search-lions-10298.20261003.stamped.json"))
        let searchPlace = MacReadingPlace<SearchViewModel>()
        _ = searchPlace.models {
            let vm = SearchViewModel { _, _ in searchResp }
            vm.query = "Lions"
            vm.results = searchResp
            return vm
        }

        // 6. Game Detail (`EventDetailView`)
        let liveEventDetail = try dec.decode(EventDetail.self, from: Data("""
        {
          "id": 9101,
          "sport": "americanfootball_nfl",
          "league": "NFL",
          "home_team": "Detroit Lions",
          "away_team": "New England Patriots",
          "commence_time": "2026-11-15T18:00:00Z",
          "status": "live",
          "home_score": 24,
          "away_score": 17,
          "home_team_data": { "abbreviation": "DET", "primary_color": "#0076B6", "record": "7-2" },
          "away_team_data": { "abbreviation": "NE", "primary_color": "#002244", "secondary_color": "#C60C30", "record": "6-3" },
          "current_odds": {
            "home_probability": 0.684,
            "away_probability": 0.316,
            "home_rendered_percent": 68,
            "away_rendered_percent": 32,
            "live_projection": {
              "projected_home_score": 28.0,
              "projected_away_score": 24.0,
              "kind": "in_play",
              "boundary": "commence_time",
              "boundary_at": "2026-11-15T18:00:00Z",
              "earliest_confirmed_at": "2026-11-15T19:50:00Z",
              "latest_captured_at": "2026-11-15T19:59:00Z",
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
            "away_rendered_percent": 42
          },
          "pregame_projection": {
            "kind": "last_before_scheduled_start",
            "boundary": "scheduled_start",
            "boundary_at": "2026-11-15T18:00:00Z",
            "earliest_captured_at": "2026-11-15T17:40:00Z",
            "latest_captured_at": "2026-11-15T17:58:00Z",
            "source": "sportsbooks",
            "basis": "consensus_spread_total",
            "bookmaker_count": 5,
            "unit": "points",
            "period": "full_game",
            "projected_home_score": 27.0,
            "projected_away_score": 24.0
          },
          "espn": { "period": "3rd Quarter", "game_clock": "6:12", "broadcast": "FOX" },
          "win_probability_sources": {
            "betting": { "value": 0.68, "display_name": "Sportsbooks" },
            "kalshi": { "value": 0.69, "display_name": "Kalshi" }
          }
        }
        """.utf8))
        let liveEventHistory = try dec.decode(EventHistoryResponse.self, from: Data("""
        {
          "event_id": 9101,
          "home_team": "Detroit Lions",
          "away_team": "New England Patriots",
          "status": "live",
          "history": [
            { "timestamp": "2026-11-15T18:00:00Z", "home_probability": 0.58, "away_probability": 0.42, "source": "aggregate" },
            { "timestamp": "2026-11-15T18:45:00Z", "home_probability": 0.51, "away_probability": 0.49, "source": "aggregate" },
            { "timestamp": "2026-11-15T19:20:00Z", "home_probability": 0.63, "away_probability": 0.37, "source": "aggregate" },
            { "timestamp": "2026-11-15T19:59:00Z", "home_probability": 0.684, "away_probability": 0.316, "source": "aggregate" }
          ]
        }
        """.utf8))
        let eventVM = EventDetailViewModel(
            eventId: 9101,
            client: StubEventProvider(detail: liveEventDetail, history: liveEventHistory)
        )
        await eventVM.load()
        eventVM.stopRefresh()

        // 7. Futures / Market Detail (`FuturesDetailView`)
        let futuresDetail = try dec.decode(
            FuturesMarketDetail.self,
            from: try fixtureData("futures-13795456-detail-8313.20261017T1545Z.json")
        )
        let futuresVM = FuturesDetailViewModel(
            marketId: futuresDetail.id,
            client: StubFuturesProvider(detail: futuresDetail)
        )
        await futuresVM.load()

        // 8. Golf Tournament (`GolfTournamentView`)
        let golfResp = try dec.decode(GolfTournamentDetailResponse.self, from: Data("""
        {
          "tournament": {
            "name": "Masters Tournament",
            "slug": "masters-tournament",
            "key": "masters",
            "is_major": true,
            "tour": "pga",
            "tour_label": "PGA Tour",
            "start_date": "2026-11-13",
            "end_date": "2026-11-16",
            "venue": "Augusta National Golf Club",
            "location": "Augusta, GA",
            "schedule_status": "in_progress",
            "commence_time": "2026-11-13T13:00:00Z"
          },
          "golfers": [
            { "name": "Scottie Scheffler", "probability": 0.242, "opening_probability": 0.18, "movement_24h": 0.042, "rank": 1 },
            { "name": "Rory McIlroy", "probability": 0.164, "opening_probability": 0.13, "movement_24h": 0.021, "rank": 2 },
            { "name": "Xander Schauffele", "probability": 0.118, "opening_probability": 0.10, "movement_24h": 0.015, "rank": 3 },
            { "name": "Jon Rahm", "probability": 0.089, "opening_probability": 0.09, "movement_24h": -0.005, "rank": 4 },
            { "name": "Collin Morikawa", "probability": 0.064, "opening_probability": 0.06, "movement_24h": 0.008, "rank": 5 }
          ],
          "evolution_market_id": 9401,
          "markets": []
        }
        """.utf8))
        let golfPresentation = GolfTournamentPresentation(response: golfResp)

        // 9. Fight Card / Concept (`ConceptCardView`)
        let ufcResp = try dec.decode(
            EventConceptResponse.self,
            from: try fixtureData("event-ufc-26sep19.20260917.json")
        )
        let ufcPresentation = ConceptCardPresentation(response: ufcResp)

        // 10. Team Page (`TeamDetailView`)
        let teamPage = try dec.decode(
            TeamPageResponse.self,
            from: try fixtureData("teams-boston-red-sox-mlb.20260916.json")
        )

        // 11. Preferences (`PreferencesView`)
        let prefsResp = try dec.decode(PreferencesResponse.self, from: Data("""
        {
          "home_location": "San Francisco, CA",
          "sport_affinities": { "nba": 1.0, "nfl": 0.75, "ncaab": 0.5, "soccer": 0.25 },
          "onboarding_completed": true,
          "favorites": [
            { "team_id": 14, "team_name": "Golden State Warriors", "relation_type": "follow", "sport_key": "basketball_nba" },
            { "team_id": 25, "team_name": "San Francisco 49ers", "relation_type": "local", "sport_key": "americanfootball_nfl" }
          ],
          "push_preferences": { "daily_challenge": true, "big_moves": true, "morning_digest": false }
        }
        """.utf8))

        // 12. Calibration (`CalibrationSurfaceView`)
        let calibrationVM = CalibrationViewModel(
            preloaded: try dec.decode(CalibrationData.self, from: Data(CalibrationProdFixture.json.utf8))
        )

        func navWrap<V: View>(_ inner: V) -> AnyView {
            AnyView(
                NavigationStack { inner }
                    .environmentObject(auth)
                    .environmentObject(NavigationCoordinator())
                    .environmentObject(pins)
            )
        }

        func bareWrap<V: View>(_ inner: V) -> AnyView {
            AnyView(
                inner
                    .environmentObject(auth)
                    .environmentObject(NavigationCoordinator())
                    .environmentObject(pins)
            )
        }

        return [
            ScreenSpecimen(id: "01-discover", title: "1. Discover", macTab: .discover) {
                bareWrap(DiscoverView(macPlace: discoverPlace))
            },
            ScreenSpecimen(id: "02-sports", title: "2. Sports Feed", macTab: .feed) {
                bareWrap(FeedView(viewModel: sportsVM))
            },
            ScreenSpecimen(id: "03-browse", title: "3. Browse", macTab: .leagues) {
                bareWrap(LeaguesView())
            },
            ScreenSpecimen(id: "04-search", title: "4. Search", macTab: .search) {
                bareWrap(SearchView(macPlace: searchPlace))
            },
            ScreenSpecimen(id: "05-mystuff", title: "5. My Stuff", macTab: .myStuff) {
                bareWrap(MyStuffView())
            },
            ScreenSpecimen(id: "06-game", title: "6. Game Page", macTab: .feed) {
                navWrap(EventDetailView(eventId: 9101).withLoadedEventForTest12278(liveEventDetail, viewModel: eventVM))
            },
            ScreenSpecimen(id: "07-futures", title: "7. Market Page", macTab: .discover) {
                navWrap(FuturesDetailView(marketId: futuresDetail.id, viewModelForTest: futuresVM))
            },
            ScreenSpecimen(id: "08-golf", title: "8. Golf Tournament", macTab: .feed) {
                navWrap(GolfTournamentView(slug: "masters-tournament", displayName: "Masters Tournament", loadedPresentationForTest: golfPresentation))
            },
            ScreenSpecimen(id: "09-concept", title: "9. Fight Card", macTab: .discover) {
                navWrap(ConceptCardView(key: "event:ufc:26sep19", displayName: "UFC Fight Night", loadedPresentationForTest: ufcPresentation))
            },
            ScreenSpecimen(id: "10-team", title: "10. Team Page", macTab: .feed) {
                navWrap(TeamDetailView(slug: "boston-red-sox-mlb", loadedPageForTest: teamPage))
            },
            ScreenSpecimen(id: "11-preferences", title: "11. Preferences", macTab: .preferences) {
                navWrap(PreferencesView(loadedPrefsForTest: prefsResp))
            },
            ScreenSpecimen(id: "12-calibration-about", title: "12. Calibration & About", macTab: .calibration) {
                navWrap(CalibrationSurfaceView(viewModel: calibrationVM))
            },
        ]
    }

    // MARK: - Capture & Contact-Sheet Stitcher

    private func captureViewport<V: View>(
        _ view: V,
        size: CGSize,
        scale: CGFloat = 2.0,
        window: UIWindow
    ) -> UIImage {
        let wrapped = view
            .environment(\.horizontalSizeClass, .regular)
            .environment(\.colorScheme, .light)
            .frame(width: size.width, height: size.height)
            .clipped()
        let host = hostForMeasurement(wrapped, at: .large)
        host.overrideUserInterfaceStyle = .light
        host.traitOverrides.horizontalSizeClass = .regular
        host.traitOverrides.preferredContentSizeCategory = .large
        window.rootViewController = host
        window.frame = CGRect(origin: .zero, size: size)
        host.view.frame = window.bounds
        host.view.setNeedsLayout()
        host.view.layoutIfNeeded()
        RunLoop.current.run(until: Date().addingTimeInterval(0.06))
        host.view.setNeedsLayout()
        host.view.layoutIfNeeded()
        RunLoop.current.run(until: Date().addingTimeInterval(0.03))
        let fmt = UIGraphicsImageRendererFormat()
        fmt.scale = scale
        return UIGraphicsImageRenderer(bounds: host.view.bounds, format: fmt).image { _ in
            _ = host.view.drawHierarchy(in: host.view.bounds, afterScreenUpdates: true)
        }
    }

    private func stitchGrid(
        title: String,
        tiles: [(label: String, image: UIImage)],
        columns: Int,
        tileDisplayWidth: CGFloat
    ) -> UIImage {
        guard let first = tiles.first else { return UIImage() }
        let aspect = first.image.size.height / max(first.image.size.width, 1)
        let tileH = round(tileDisplayWidth * aspect)
        let labelH: CGFloat = 24
        let pad: CGFloat = 16
        let headerH: CGFloat = 44
        let rows = Int(ceil(Double(tiles.count) / Double(columns)))
        let totalW = pad + CGFloat(columns) * tileDisplayWidth + CGFloat(columns - 1) * pad + pad
        let totalH = headerH + CGFloat(rows) * (labelH + tileH) + CGFloat(rows) * pad + pad

        let fmt = UIGraphicsImageRendererFormat()
        fmt.scale = 2.0
        return UIGraphicsImageRenderer(size: CGSize(width: totalW, height: totalH), format: fmt).image { ctx in
            UIColor(red: 0.94, green: 0.95, blue: 0.97, alpha: 1.0).setFill()
            ctx.fill(CGRect(x: 0, y: 0, width: totalW, height: totalH))

            let titleAttrs: [NSAttributedString.Key: Any] = [
                .font: UIFont.systemFont(ofSize: 18, weight: .bold),
                .foregroundColor: UIColor(red: 0.10, green: 0.12, blue: 0.16, alpha: 1.0),
            ]
            (title as NSString).draw(at: CGPoint(x: pad, y: 12), withAttributes: titleAttrs)

            let labelAttrs: [NSAttributedString.Key: Any] = [
                .font: UIFont.systemFont(ofSize: 13, weight: .semibold),
                .foregroundColor: UIColor(red: 0.25, green: 0.30, blue: 0.38, alpha: 1.0),
            ]

            for (idx, tile) in tiles.enumerated() {
                let r = idx / columns
                let c = idx % columns
                let x = pad + CGFloat(c) * (tileDisplayWidth + pad)
                let y = headerH + CGFloat(r) * (labelH + tileH + pad)
                (tile.label as NSString).draw(at: CGPoint(x: x + 2, y: y + 3), withAttributes: labelAttrs)

                let imgRect = CGRect(x: x, y: y + labelH, width: tileDisplayWidth, height: tileH)
                ctx.cgContext.saveGState()
                let clip = UIBezierPath(roundedRect: imgRect, cornerRadius: 10)
                clip.addClip()
                tile.image.draw(in: imgRect)
                ctx.cgContext.restoreGState()

                UIColor(white: 0.0, alpha: 0.12).setStroke()
                let border = UIBezierPath(roundedRect: imgRect, cornerRadius: 10)
                border.lineWidth = 1
                border.stroke()
            }
        }
    }

    func testIPadAndMacContactSheetsRenderAllTwelve107Screens() async throws {
        let screens = try await buildTwelveScreens()
        XCTAssertEqual(screens.count, 12)

        let window: UIWindow = {
            if let scene = UIApplication.shared.connectedScenes.compactMap({ $0 as? UIWindowScene }).first {
                return UIWindow(windowScene: scene)
            }
            return UIWindow(frame: CGRect(x: 0, y: 0, width: 1280, height: 1194))
        }()
        window.overrideUserInterfaceStyle = .light
        window.isHidden = false
        defer {
            window.isHidden = true
            window.rootViewController = nil
        }

        let iPadSize = CGSize(width: 834, height: 1194)
        let macSize = CGSize(width: 1280, height: 840)

        var iPadTiles: [(label: String, image: UIImage)] = []
        var macTiles: [(label: String, image: UIImage)] = []

        let outDir = ProcessInfo.processInfo.environment["EXPORT_IPAD_MAC_SHEET_DIR"]
        let dirURL = outDir.flatMap { $0.isEmpty ? nil : URL(fileURLWithPath: $0, isDirectory: true) }
        if let dirURL {
            try FileManager.default.createDirectory(at: dirURL, withIntermediateDirectories: true)
        }

        for spec in screens {
            let ipadImg = captureViewport(spec.makeView(), size: iPadSize, scale: 1.5, window: window)
            XCTAssertEqual(ipadImg.size.width, 834, accuracy: 1)
            iPadTiles.append((spec.title, ipadImg))
            if let dirURL {
                try ipadImg.pngData()?.write(to: dirURL.appendingPathComponent("ipad-\(spec.id).png"))
            }

            let macWrapped = MacWindowChromePreview(activeTab: spec.macTab, detail: spec.makeView())
            let macImg = captureViewport(macWrapped, size: macSize, scale: 1.5, window: window)
            XCTAssertEqual(macImg.size.width, 1280, accuracy: 1)
            macTiles.append((spec.title, macImg))
            if let dirURL {
                try macImg.pngData()?.write(to: dirURL.appendingPathComponent("mac-\(spec.id).png"))
            }
        }

        // Also capture standalone AboutView at iPad & Mac
        let aboutIPad = captureViewport(
            NavigationStack { AboutView() }
                .environmentObject(NavigationCoordinator()),
            size: iPadSize,
            scale: 1.5,
            window: window
        )
        let aboutMac = captureViewport(
            MacWindowChromePreview(
                activeTab: .preferences,
                detail: NavigationStack { AboutView() }
                    .environmentObject(NavigationCoordinator())
            ),
            size: macSize,
            scale: 1.5,
            window: window
        )
        if let dirURL {
            try aboutIPad.pngData()?.write(to: dirURL.appendingPathComponent("ipad-13-about.png"))
            try aboutMac.pngData()?.write(to: dirURL.appendingPathComponent("mac-13-about.png"))
        }

        let iPadSheet = stitchGrid(
            title: "Bain Luck 1.0.7 — iPad Pass (834×1194, Regular Width)",
            tiles: iPadTiles,
            columns: 3,
            tileDisplayWidth: 400
        )
        let macSheet = stitchGrid(
            title: "Bain Luck 1.0.7 — Mac Pass (1280×840, Sidebar + Detail)",
            tiles: macTiles,
            columns: 3,
            tileDisplayWidth: 460
        )

        if let dirURL {
            try iPadSheet.pngData()?.write(to: dirURL.appendingPathComponent("ipad-107-contact-sheet.png"))
            try macSheet.pngData()?.write(to: dirURL.appendingPathComponent("mac-107-contact-sheet.png"))
        }
    }

    func testWorstThreeIPadAndMacDefectsStayBoundedAndFrameless() throws {
        // Fix 1: Sports Feed regular-width masonry sections clear the outer List row
        // background so a 1-item section ("Live Now 1", "Upcoming 1") never draws a
        // half-empty white wrapper container around its left-column card.
        let appRoot = Self.testsDir.deletingLastPathComponent().appendingPathComponent("Bain Luck")
        let feedSource = try String(
            contentsOf: appRoot.appendingPathComponent("Views/FeedView.swift"),
            encoding: .utf8
        )
        let clearRowCount = feedSource.components(separatedBy: ".listRowBackground(Color.clear)").count - 1
        XCTAssertGreaterThanOrEqual(
            clearRowCount,
            4,
            "FeedView must clear the outer List row background on both regular-width masonry sections"
        )

        // Fix 2: Single-column detail, tournament, fight-card, and team schedule pages
        // cap at a centered 720 pt reading column across iPad (834 pt) and Mac (1060 pt detail).
        XCTAssertEqual(EventDetailView.readableDetailMaxWidth, 720)
        XCTAssertEqual(FuturesDetailView.readableDetailMaxWidth, 720)
        XCTAssertEqual(GolfTournamentView.readableDetailMaxWidth, 720)
        XCTAssertEqual(GolfCategoryView.readableDetailMaxWidth, 720)
        XCTAssertEqual(ConceptCardView.readableDetailMaxWidth, 720)
        XCTAssertEqual(TeamDetailView.readableDetailMaxWidth, 720)

        // Fix 3: Preferences caps at 720 pt centered, and My Stuff bounds both the
        // top "Manage pins" card row and the signed-out column cleanly.
        XCTAssertEqual(PreferencesView.readableDetailMaxWidth, 720)
        XCTAssertEqual(MyStuffView.signInMaxWidth, 560)
        XCTAssertEqual(MyStuffView.signedInManagePinsMaxWidth, 800)
    }
}
