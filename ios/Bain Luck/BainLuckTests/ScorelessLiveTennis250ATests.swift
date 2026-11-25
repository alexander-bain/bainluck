import XCTest
import SwiftUI
import UIKit
import Vision
@testable import Bain_Luck

/// #13000 (`250: A`) — A live match with no score source (`score_source_unavailable == true`)
/// shows its chance only (`LIVE` and `Now`, no `Score`/`Sets` column, no blank cell, no dash,
/// no `"0"`), and prints one plain line on the match page (`"No live score for this tournament."`).
/// Where a source does have the score (`score_source_unavailable == false` or `nil`), nothing changes.
@MainActor
final class ScorelessLiveTennis250ATests: XCTestCase {

    private let fixedNow: Date = {
        var c = DateComponents()
        c.year = 2026
        c.month = 11
        c.day = 19
        c.hour = 1
        c.minute = 15
        c.timeZone = TimeZone(secondsFromGMT: 0)
        return Calendar(identifier: .gregorian).date(from: c)!
    }()

    private func decodeSnake<T: Decodable>(_ type: T.Type, _ json: String) throws -> T {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(T.self, from: Data(json.utf8))
    }

    /// Event `15350873` from `#13000`: Tristan Boyer vs Genaro Alberto Olivieri
    /// (`ATP Challenger 75 Montevideo`, `tennis_atp`, `status: "live"`,
    /// `score_source_unavailable: true`, Kalshi + Polymarket blend).
    private static let boyerVsOlivieriJSON = """
    {
      "id": 15350873,
      "sport": "tennis_atp",
      "sport_name": "ATP",
      "home_team": "Tristan Boyer",
      "away_team": "Genaro Alberto Olivieri",
      "commence_time": "2026-11-18T23:30:00Z",
      "start_is_tbd": false,
      "status": "live",
      "home_score": null,
      "away_score": null,
      "score_source": null,
      "score_source_unavailable": true,
      "home_team_data": {
        "primary_color": "#1d4ed8",
        "secondary_color": "#60a5fa",
        "abbreviation": "BOY"
      },
      "away_team_data": {
        "primary_color": "#059669",
        "secondary_color": "#34d399",
        "abbreviation": "OLI"
      },
      "current_odds": {
        "captured_at": "2026-11-19T01:14:20Z",
        "home_probability": 0.624,
        "away_probability": 0.376,
        "away_rendered_percent": 38,
        "home_rendered_percent": 62
      },
      "prematch_odds": {
        "home_probability": 0.58,
        "away_probability": 0.42,
        "away_rendered_percent": 42,
        "home_rendered_percent": 58,
        "source": "blend"
      },
      "hero_probability": 0.624,
      "hero_probability_away": 0.376,
      "hero_probability_source": "blend",
      "source_mark": {
        "state": "blend",
        "sources": [
          { "key": "kalshi", "name": "Kalshi", "probability": 0.62 },
          { "key": "polymarket", "name": "Polymarket", "probability": 0.63 }
        ],
        "method": "Bain Luck blend · the weighted middle of these sources"
      }
    }
    """

    /// Covered live tennis match (`15350871` Samson vs Geerlings Martinez, WTA 125 LP Open,
    /// `score_source_unavailable: false`, ESPN set scores present) — proves nothing changes
    /// where a score source covers the match.
    private static let coveredTennisLiveJSON = """
    {
      "id": 15350871,
      "sport": "tennis_wta",
      "sport_name": "WTA",
      "home_team": "Laura Samson",
      "away_team": "Ariana Geerlings Martinez",
      "commence_time": "2026-11-18T22:00:00Z",
      "start_is_tbd": false,
      "status": "live",
      "home_score": 1,
      "away_score": 1,
      "score_source": "espn",
      "score_source_unavailable": false,
      "home_team_data": {
        "primary_color": "#7c3aed",
        "secondary_color": "#c4b5fd",
        "abbreviation": "SAM"
      },
      "away_team_data": {
        "primary_color": "#db2777",
        "secondary_color": "#f9a8d4",
        "abbreviation": "GEE"
      },
      "espn": {
        "period": "3rd Set"
      },
      "linescore": {
        "sets": [[6, 4], [3, 6], [4, 2]],
        "home_sets": 1,
        "away_sets": 1,
        "home_points": "30",
        "away_points": "15",
        "tiebreak": false,
        "source": "espn"
      },
      "current_odds": {
        "captured_at": "2026-11-19T01:14:20Z",
        "home_probability": 0.712,
        "away_probability": 0.288,
        "away_rendered_percent": 29,
        "home_rendered_percent": 71
      },
      "prematch_odds": {
        "home_probability": 0.64,
        "away_probability": 0.36,
        "away_rendered_percent": 36,
        "home_rendered_percent": 64,
        "source": "blend"
      },
      "hero_probability": 0.712,
      "hero_probability_away": 0.288,
      "hero_probability_source": "blend"
    }
    """

    func testDecodesScoreSourceUnavailableAcrossFeedDetailAndSearchModels() throws {
        let feed: FeedEventData = try decodeSnake(FeedEventData.self, Self.boyerVsOlivieriJSON)
        let detail: EventDetail = try decodeSnake(EventDetail.self, Self.boyerVsOlivieriJSON)
        let search: SearchEvent = try decodeSnake(SearchEvent.self, Self.boyerVsOlivieriJSON)

        XCTAssertEqual(feed.scoreSourceUnavailable, true)
        XCTAssertEqual(detail.scoreSourceUnavailable, true)
        XCTAssertEqual(search.scoreSourceUnavailable, true)

        let adaptedSearch = SearchEventCardAdapter183A.fromSearchResult(search, sportDisplayName: "ATP")
        XCTAssertEqual(adaptedSearch.scoreSourceUnavailable, true)

        let team: TeamPageTeam = try decodeSnake(
            TeamPageTeam.self,
            """
            {
              "id": 1,
              "name": "Tristan Boyer",
              "abbreviation": "BOY",
              "slug": "tristan-boyer",
              "sport_key": "tennis_atp",
              "sport_name": "ATP",
              "primary_color": "#1d4ed8",
              "secondary_color": "#60a5fa"
            }
            """
        )
        let adaptedBrief = SearchEventCardAdapter183A.fromTeamScheduleBrief(search, team: team).feedEvent
        XCTAssertEqual(adaptedBrief.scoreSourceUnavailable, true)

        let savedPin = FeedEventData(savedPinDetail: detail)
        XCTAssertEqual(savedPin.scoreSourceUnavailable, true)
    }

    func testLiveTennisCardOmitsScoreColumnBlankCellDashAndZeroWhenUnavailable() throws {
        var feed: FeedEventData = try decodeSnake(FeedEventData.self, Self.boyerVsOlivieriJSON)
        let cardView = EventCardView(event: feed, reason: nil)
        let headers = cardView.compactHeadersForTest250A
        XCTAssertNil(headers.medium, "EventCardView must omit the Score column header when score_source_unavailable == true")
        XCTAssertEqual(headers.large, "Now", "EventCardView must keep Now on a scoreless live match")

        let discoverModel = DiscoverSingleGameCard190C.build(
            event: feed,
            prematch: PrematchReading.resolve(prematch: feed.prematchOdds, opening: nil),
            showsInlinePregame: true,
            showsLiveTenths: true
        )
        XCTAssertTrue(discoverModel.isLive)
        XCTAssertNil(discoverModel.headers.score, "Discover card must omit Score header")
        XCTAssertEqual(discoverModel.headers.primary, "Now", "Discover card must keep Now header")
        XCTAssertNil(discoverModel.rows[0].scoreText)
        XCTAssertNil(discoverModel.rows[1].scoreText)
        XCTAssertEqual(discoverModel.rows[0].primaryCell, .probability("37.6%"))
        XCTAssertEqual(discoverModel.rows[1].primaryCell, .probability("62.4%"))

        // Even if a stale 0 ever arrived alongside `score_source_unavailable == true`,
        // neither card draws a "0" or a Score column.
        feed.awayScore = 0
        feed.homeScore = 0
        XCTAssertNil(EventCardView(event: feed, reason: nil).compactHeadersForTest250A.medium)
        let withZero = DiscoverSingleGameCard190C.build(
            event: feed,
            prematch: nil,
            showsInlinePregame: true
        )
        XCTAssertNil(withZero.headers.score)
        XCTAssertNil(withZero.rows[0].scoreText)
        XCTAssertNil(withZero.rows[1].scoreText)
    }

    func testLiveTennisMatchPageOmitsSetsAndScoreColumnsAndPrintsPlainTournamentLine() throws {
        let detail: EventDetail = try decodeSnake(EventDetail.self, Self.boyerVsOlivieriJSON)
        XCTAssertFalse(
            EventDetailView.showsScore(
                status: detail.status,
                away: 0,
                home: 0,
                scoreSourceUnavailable: detail.scoreSourceUnavailable
            )
        )

        let model = EventSportHeadlines12472.resolve(
            event: detail,
            awayFullName: detail.awayTeam,
            homeFullName: detail.homeTeam,
            liveStatusText: nil,
            hasScore: false,
            numberStreams: false,
            now: fixedNow
        )

        XCTAssertEqual(model.kind, .tennisDuringGame)
        XCTAssertEqual(model.liveBadgeText, "LIVE")
        XCTAssertEqual(model.leagueLabel, "ATP")
        XCTAssertEqual(
            model.columns,
            [.init(role: .now, header: "Now")],
            "Match page must leave Sets / Score out completely and keep Now only"
        )
        XCTAssertNil(model.liveColumnHeaders?.score)
        XCTAssertEqual(model.liveColumnHeaders?.now, "Now")
        XCTAssertNil(model.tennisScoreFirst)
        XCTAssertEqual(model.rows.count, 2)
        XCTAssertEqual(model.rows[0].cells, ["37.6%"])
        XCTAssertEqual(model.rows[1].cells, ["62.4%"])
        XCTAssertFalse(model.rows.flatMap(\.cells).contains(""))
        XCTAssertFalse(model.rows.flatMap(\.cells).contains("0"))
        XCTAssertFalse(model.rows.flatMap(\.cells).contains("—"))
        XCTAssertFalse(model.rows.flatMap(\.cells).contains("-"))
        XCTAssertEqual(model.scoreUnavailableNotice, "No live score for this tournament.")
    }

    func testCoveredMatchAndNoScoreYetMatchKeepExistingScoreBehavior() throws {
        // 1. Covered live tennis match with sets & points: nothing changes.
        let covered: EventDetail = try decodeSnake(EventDetail.self, Self.coveredTennisLiveJSON)
        let coveredModel = EventSportHeadlines12472.resolve(
            event: covered,
            awayFullName: covered.awayTeam,
            homeFullName: covered.homeTeam,
            liveStatusText: "3rd Set",
            hasScore: true,
            numberStreams: false,
            now: fixedNow
        )
        XCTAssertEqual(
            coveredModel.columns.map(\.header),
            ["S1", "S2", "S3", "Pts", "Now"]
        )
        XCTAssertNil(coveredModel.scoreUnavailableNotice)

        // 2. Covered live tennis match right after start ("no score yet": `score_source_unavailable == false`,
        // sets not yet populated, `0-0`): keeps `Sets` ("0"/"0") and prints no notice.
        var justStarted = covered
        justStarted.linescore = nil
        justStarted.awayScore = 0
        justStarted.homeScore = 0
        let justStartedModel = EventSportHeadlines12472.resolve(
            event: justStarted,
            awayFullName: justStarted.awayTeam,
            homeFullName: justStarted.homeTeam,
            liveStatusText: "1st Set",
            hasScore: true,
            numberStreams: false,
            now: fixedNow
        )
        XCTAssertEqual(justStartedModel.columns.map(\.header), ["Sets", "Now"])
        XCTAssertEqual(justStartedModel.rows[0].cells, ["0", "28.8%"])
        XCTAssertEqual(justStartedModel.rows[1].cells, ["0", "71.2%"])
        XCTAssertNil(justStartedModel.scoreUnavailableNotice)
    }

    // MARK: - 390 pt Light & Dark Render Harness (Default & Larger Text)

    private func captureSheet<V: View>(
        _ content: V,
        scheme: ColorScheme,
        at size: DynamicTypeSize,
        width: CGFloat = 390
    ) -> UIImage {
        let bg = scheme == .dark
            ? Color(red: 0.07, green: 0.08, blue: 0.10)
            : Color(red: 0.96, green: 0.96, blue: 0.97)
        let root = content
            .padding(.vertical, 16)
            .frame(width: width)
            .background(bg)
            .environment(\.colorScheme, scheme)
            .environment(\.dynamicTypeSize, size)
            .environmentObject(PinManager())

        let host = hostForMeasurement(root, at: size)
        host.overrideUserInterfaceStyle = scheme == .dark ? .dark : .light
        let fitting = host.sizeThatFits(in: CGSize(width: width, height: 2600))
        let height = max(ceil(fitting.height) + 24, 260)
        let scene = UIApplication.shared.connectedScenes.compactMap({ $0 as? UIWindowScene }).first
        let window: UIWindow = scene.map { UIWindow(windowScene: $0) }
            ?? UIWindow(frame: CGRect(x: 0, y: 0, width: width, height: height))
        window.frame = CGRect(x: 0, y: 0, width: width, height: height)
        host.view.frame = window.bounds
        window.overrideUserInterfaceStyle = scheme == .dark ? .dark : .light
        window.rootViewController = host
        window.isHidden = false
        defer {
            window.isHidden = true
            window.rootViewController = nil
        }

        for _ in 0..<5 {
            host.view.setNeedsLayout()
            host.view.layoutIfNeeded()
            RunLoop.current.run(until: Date().addingTimeInterval(0.04))
        }

        let fmt = UIGraphicsImageRendererFormat()
        fmt.scale = 3.0
        fmt.opaque = true
        return UIGraphicsImageRenderer(size: CGSize(width: width, height: height), format: fmt).image { _ in
            _ = host.view.drawHierarchy(in: host.view.bounds, afterScreenUpdates: true)
        }
    }

    private func sideBySide(_ light: UIImage, _ dark: UIImage) -> UIImage {
        let gap: CGFloat = 16
        let pad: CGFloat = 16
        let w = pad * 2 + light.size.width + gap + dark.size.width
        let h = pad * 2 + max(light.size.height, dark.size.height)
        let fmt = UIGraphicsImageRendererFormat()
        fmt.scale = 2.0
        fmt.opaque = true
        return UIGraphicsImageRenderer(size: CGSize(width: w, height: h), format: fmt).image { ctx in
            UIColor(white: 0.14, alpha: 1).setFill()
            ctx.fill(CGRect(x: 0, y: 0, width: w, height: h))
            light.draw(in: CGRect(x: pad, y: pad, width: light.size.width, height: light.size.height))
            dark.draw(in: CGRect(x: pad + light.size.width + gap, y: pad, width: dark.size.width, height: dark.size.height))
        }
    }

    private func ocrStrings(_ image: UIImage) throws -> [String] {
        guard let cg = image.cgImage else { return [] }
        let req = VNRecognizeTextRequest()
        req.recognitionLevel = .accurate
        req.usesLanguageCorrection = false
        try VNImageRequestHandler(cgImage: cg, options: [:]).perform([req])
        return (req.results ?? []).compactMap { $0.topCandidates(1).first?.string }
    }

    func testRender13000ScorelessLiveLooks() throws {
        guard let outDir = ProcessInfo.processInfo.environment["RENDER_13000_DIR"],
              !outDir.isEmpty else {
            return
        }
        try FileManager.default.createDirectory(atPath: outDir, withIntermediateDirectories: true)

        let feedBoyer: FeedEventData = try decodeSnake(FeedEventData.self, Self.boyerVsOlivieriJSON)
        let detailBoyer: EventDetail = try decodeSnake(EventDetail.self, Self.boyerVsOlivieriJSON)
        let detailCovered: EventDetail = try decodeSnake(EventDetail.self, Self.coveredTennisLiveJSON)

        let boyerHeadline = EventSportHeadlines12472.resolve(
            event: detailBoyer,
            awayFullName: detailBoyer.awayTeam,
            homeFullName: detailBoyer.homeTeam,
            liveStatusText: nil,
            hasScore: false,
            numberStreams: false,
            now: fixedNow
        )
        let coveredHeadline = EventSportHeadlines12472.resolve(
            event: detailCovered,
            awayFullName: detailCovered.awayTeam,
            homeFullName: detailCovered.homeTeam,
            liveStatusText: "3rd Set",
            hasScore: true,
            numberStreams: false,
            now: fixedNow
        )

        let detailTeamGame: EventDetail = try decodeSnake(EventDetail.self, """
        {
          "id": 99801,
          "sport": "basketball_ncaab",
          "sport_name": "NCAAB",
          "away_team": "Furman Paladins",
          "home_team": "Radford Highlanders",
          "commence_time": "2026-11-18T22:00:00Z",
          "status": "live",
          "score_source_unavailable": true,
          "current_odds": {
            "away_probability": 0.489,
            "home_probability": 0.511,
            "away_rendered_percent": 49,
            "home_rendered_percent": 51
          },
          "prematch_odds": {
            "away_probability": 0.46,
            "home_probability": 0.54
          }
        }
        """)
        let teamGameHeadline = EventSportHeadlines12472.resolve(
            event: detailTeamGame,
            awayFullName: detailTeamGame.awayTeam,
            homeFullName: detailTeamGame.homeTeam,
            liveStatusText: nil,
            hasScore: false,
            numberStreams: false,
            now: fixedNow
        )

        func resolvedColors(for detail: EventDetail, scheme: ColorScheme) -> (away: Color, home: Color) {
            let hexes = scheme == .dark
                ? TeamTextContrast.darkSurfaceColorHexes(
                    awayHex: detail.awayTeamData?.primaryColor,
                    homeHex: detail.homeTeamData?.primaryColor,
                    awaySecondaryHex: detail.awayTeamData?.secondaryColor,
                    homeSecondaryHex: detail.homeTeamData?.secondaryColor
                  )
                : TeamTextContrast.cardColorHexes(
                    awayHex: detail.awayTeamData?.primaryColor,
                    homeHex: detail.homeTeamData?.primaryColor,
                    awaySecondaryHex: detail.awayTeamData?.secondaryColor
                  )
            return (Color(hex: hexes.away), Color(hex: hexes.home))
        }

        let pinManager = PinManager()

        @ViewBuilder
        func scorelessSheetView(scheme: ColorScheme) -> some View {
            let boyerColors = resolvedColors(for: detailBoyer, scheme: scheme)
            let teamColors = resolvedColors(for: detailTeamGame, scheme: scheme)
            let coveredColors = resolvedColors(for: detailCovered, scheme: scheme)
            VStack(alignment: .leading, spacing: 14) {
                Text("250: A · Match card (no Score column, LIVE + Now only)")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
                    .padding(.horizontal, 16)

                EventCardView(event: feedBoyer, reason: nil)
                    .environmentObject(pinManager)
                    .padding(.horizontal, 14)
                    .padding(.vertical, 4)
                    .background(
                        RoundedRectangle(cornerRadius: 16, style: .continuous)
                            .fill(Color.cardBackground)
                    )
                    .overlay(
                        RoundedRectangle(cornerRadius: 16, style: .continuous)
                            .stroke(HeadlineStyleTable199.cardBorderInk, lineWidth: 1)
                    )
                    .padding(.horizontal, 16)

                Text("250: A · Match page (LIVE + Now + tournament line)")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
                    .padding(.horizontal, 16)
                    .padding(.top, 4)

                EventSportHeadlineCard12472(
                    model: boyerHeadline,
                    colors: boyerColors,
                    ekgTracker: EkgTracker(eventId: detailBoyer.id),
                    liveUpdateStatus: .hidden,
                    displayAsOf: fixedNow,
                    updateStream: LiveUpdateStream(),
                    showUpdateStream: .constant(false),
                    showProbabilityDetails: .constant(false),
                    priceStreamingEligible: false,
                    lastReceivedAt: nil,
                    confirmedAt: nil,
                    revealForecast: nil
                )
                .padding(.horizontal, 16)

                Text("250: A · Team-league page (LIVE + Now + game line)")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
                    .padding(.horizontal, 16)
                    .padding(.top, 4)

                EventSportHeadlineCard12472(
                    model: teamGameHeadline,
                    colors: teamColors,
                    ekgTracker: EkgTracker(eventId: detailTeamGame.id),
                    liveUpdateStatus: .hidden,
                    displayAsOf: fixedNow,
                    updateStream: LiveUpdateStream(),
                    showUpdateStream: .constant(false),
                    showProbabilityDetails: .constant(false),
                    priceStreamingEligible: false,
                    lastReceivedAt: nil,
                    confirmedAt: nil,
                    revealForecast: nil
                )
                .padding(.horizontal, 16)

                Text("Covered match unchanged (Samson vs Geerlings, ESPN sets + Pts)")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
                    .padding(.horizontal, 16)
                    .padding(.top, 4)

                EventSportHeadlineCard12472(
                    model: coveredHeadline,
                    colors: coveredColors,
                    ekgTracker: EkgTracker(eventId: detailCovered.id),
                    liveUpdateStatus: .hidden,
                    displayAsOf: fixedNow,
                    updateStream: LiveUpdateStream(),
                    showUpdateStream: .constant(false),
                    showProbabilityDetails: .constant(false),
                    priceStreamingEligible: false,
                    lastReceivedAt: nil,
                    confirmedAt: nil,
                    revealForecast: nil
                )
                .padding(.horizontal, 16)
            }
        }

        for (tag, dt) in [("default", DynamicTypeSize.large), ("largest-text", DynamicTypeSize.xxxLarge)] {
            let light = captureSheet(scorelessSheetView(scheme: .light), scheme: .light, at: dt)
            let dark = captureSheet(scorelessSheetView(scheme: .dark), scheme: .dark, at: dt)
            let combined = sideBySide(light, dark)
            let url = URL(fileURLWithPath: outDir).appendingPathComponent("13000-iphone-scoreless-live-\(tag)-390.png")
            try XCTUnwrap(combined.pngData()).write(to: url)

            let ocr = try ocrStrings(light).joined(separator: " ")
            XCTAssertTrue(ocr.contains("No live score for this tournament"), "Render \(tag) must print tournament line: \(ocr)")
            XCTAssertTrue(ocr.contains("No live score for this game"), "Render \(tag) must print game line: \(ocr)")
            XCTAssertTrue(ocr.contains("62.4%") && ocr.contains("37.6%"), "Render \(tag) must print live Now chances: \(ocr)")
            XCTAssertFalse(ocr.contains("Sets"), "Render \(tag) must omit Sets header on Boyer vs Olivieri: \(ocr)")
        }

        // Optional live Tennis pill verification render (#13021) when staged JSONs are present
        let atpPath = URL(fileURLWithPath: outDir).appendingPathComponent("live-tennis-atp.json")
        let wtaPath = URL(fileURLWithPath: outDir).appendingPathComponent("live-tennis-wta.json")
        if FileManager.default.fileExists(atPath: atpPath.path),
           FileManager.default.fileExists(atPath: wtaPath.path) {
            let decoder = JSONDecoder()
            decoder.keyDecodingStrategy = .convertFromSnakeCase
            let atp = try decoder.decode(LeagueMarketsResponse.self, from: Data(contentsOf: atpPath))
            let wta = try decoder.decode(LeagueMarketsResponse.self, from: Data(contentsOf: wtaPath))
            let merged = SportCategoryViewModel.mergeTourLeagueResponses([atp, wta])
            let upcoming = merged.upcomingGames.filter { $0.status != "live" }
            let tennisStack = VStack(alignment: .leading, spacing: 10) {
                Text("Tennis · Upcoming (\(upcoming.count))")
                    .font(.headline)
                    .padding(.horizontal, 16)
                ForEach(upcoming) { game in
                    EventCardView(event: game, reason: nil)
                        .environmentObject(pinManager)
                        .padding(.horizontal, 14)
                        .padding(.vertical, 4)
                        .background(
                            RoundedRectangle(cornerRadius: 16, style: .continuous)
                                .fill(Color.cardBackground)
                        )
                        .overlay(
                            RoundedRectangle(cornerRadius: 16, style: .continuous)
                                .stroke(HeadlineStyleTable199.cardBorderInk, lineWidth: 1)
                        )
                        .padding(.horizontal, 16)
                }
            }
            let tLight = captureSheet(tennisStack, scheme: .light, at: .large)
            let tDark = captureSheet(tennisStack, scheme: .dark, at: .large)
            let tCombined = sideBySide(tLight, tDark)
            let tURL = URL(fileURLWithPath: outDir).appendingPathComponent("13021-tennis-upcoming-light-dark-390.png")
            try XCTUnwrap(tCombined.pngData()).write(to: tURL)
        }
    }
}
