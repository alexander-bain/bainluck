import SwiftUI
#if canImport(UIKit)
import UIKit
import Vision
import XCTest
@testable import Bain_Luck

/// Overnight Item 8 — Largest text size (`.accessibility5`), iPad two-column masonry
/// (`834 pt` -> `393 pt` columns & `744 pt` -> `348 pt` columns), and Mac/iPad landscape
/// three-column masonry (`1008 pt` -> `325 pt` / `300 pt` minimum columns) across every
/// new card shipped in build `5721`:
/// 1. `DiscoverCompactSingleGameCard190CView` + `DiscoverPictureChartPanel191AView` (`#12696`, `#12699`)
/// 2. `DiscoverPairedMetricCardView` Look 1 & Look 2 (`#12675`)
/// 3. `EventCardView` scheduled, live, 3-way soccer, and finished (`#12660`, `#12684`, `#12697`)
/// 4. `EventSportHeadlineCard12472` NFL before-game and NBA during-game (`#12668`)
@MainActor
final class LargestTextIPadAndMacCardsOvernight8Tests: XCTestCase {

    private let pins = PinManager(
        defaults: UserDefaults(suiteName: "LargestTextIPadAndMacCardsOvernight8Tests")!,
        serverLoad: { PinsResponse(events: [], futures: []) },
        serverSync: { _, _, _ in }
    )

    private func decodeFeedEvent(_ json: String) throws -> FeedEventData {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(FeedEventData.self, from: Data(json.utf8))
    }

    private func decodeEventDetail(_ json: String) throws -> EventDetail {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(EventDetail.self, from: Data(json.utf8))
    }

    private func decodeHistory(_ json: String) throws -> EventHistoryResponse {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(EventHistoryResponse.self, from: Data(json.utf8))
    }

    private func decodePairedSet(_ json: String) throws -> PairedMetricSet {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(PairedMetricSet.self, from: Data(json.utf8))
    }

    // MARK: - Fixtures

    private func makeLiveDiscoverGame() throws -> (FeedEventData, EventHistoryResponse) {
        let event = try decodeFeedEvent("""
        {
          "id": 15346901,
          "sport": "basketball_nba",
          "sport_name": "NBA",
          "away_team": "Boston Celtics",
          "home_team": "Minnesota Timberwolves",
          "commence_time": "2026-11-14T01:00:00Z",
          "status": "live",
          "away_score": 88,
          "home_score": 82,
          "espn": {
            "game_clock": "4:18",
            "period": "4Q",
            "broadcast": "ESPN"
          },
          "prematch_odds": {
            "away_probability": 0.54,
            "home_probability": 0.46,
            "away_rendered_percent": 54,
            "home_rendered_percent": 46,
            "source": "kalshi"
          },
          "current_odds": {
            "away_probability": 0.712,
            "home_probability": 0.288,
            "in_play_projected_away_score": 114.2,
            "in_play_projected_home_score": 107.8
          }
        }
        """)

        let history = try decodeHistory("""
        {
          "event_id": 15346901,
          "sport": "basketball_nba",
          "home_team": "Minnesota Timberwolves",
          "away_team": "Boston Celtics",
          "commence_time": "2026-11-14T01:00:00Z",
          "history": [
            {"timestamp": "2026-11-14T00:55:00Z", "home_probability": 0.46, "away_probability": 0.54},
            {"timestamp": "2026-11-14T01:25:00Z", "home_probability": 0.52, "away_probability": 0.48},
            {"timestamp": "2026-11-14T01:55:00Z", "home_probability": 0.39, "away_probability": 0.61},
            {"timestamp": "2026-11-14T02:20:00Z", "home_probability": 0.288, "away_probability": 0.712}
          ]
        }
        """)
        return (event, history)
    }

    private func makeFinishedDiscoverGame() throws -> (FeedEventData, EventHistoryResponse) {
        let event = try decodeFeedEvent("""
        {
          "id": 15346902,
          "sport": "americanfootball_nfl",
          "sport_name": "NFL",
          "away_team": "Washington Commanders",
          "home_team": "San Francisco 49ers",
          "commence_time": "2026-11-13T01:15:00Z",
          "status": "completed",
          "away_score": 17,
          "home_score": 23,
          "prematch_odds": {
            "away_probability": 0.24,
            "home_probability": 0.76,
            "away_rendered_percent": 24,
            "home_rendered_percent": 76,
            "source": "kalshi"
          },
          "pregame_projection": {
            "away_score": 22.0,
            "home_score": 29.0,
            "period": "full_game"
          }
        }
        """)

        let history = try decodeHistory("""
        {
          "event_id": 15346902,
          "sport": "americanfootball_nfl",
          "home_team": "San Francisco 49ers",
          "away_team": "Washington Commanders",
          "commence_time": "2026-11-13T01:15:00Z",
          "history": [
            {"timestamp": "2026-11-13T01:10:00Z", "home_probability": 0.76, "away_probability": 0.24},
            {"timestamp": "2026-11-13T02:10:00Z", "home_probability": 0.61, "away_probability": 0.39},
            {"timestamp": "2026-11-13T03:10:00Z", "home_probability": 0.84, "away_probability": 0.16},
            {"timestamp": "2026-11-13T04:05:00Z", "home_probability": 1.0, "away_probability": 0.0}
          ]
        }
        """)
        return (event, history)
    }

    private func makeScheduledNFLGame() throws -> FeedEventData {
        try decodeFeedEvent("""
        {
          "id": 15346903,
          "sport": "americanfootball_nfl",
          "sport_name": "NFL",
          "away_team": "Minnesota Vikings",
          "home_team": "Green Bay Packers",
          "commence_time": "2026-11-15T18:00:00Z",
          "status": "scheduled",
          "espn": {
            "broadcast": "FOX"
          },
          "prematch_odds": {
            "away_probability": 0.45,
            "home_probability": 0.55,
            "away_rendered_percent": 45,
            "home_rendered_percent": 55,
            "source": "kalshi"
          },
          "current_odds": {
            "away_probability": 0.41,
            "home_probability": 0.59,
            "away_rendered_percent": 41,
            "home_rendered_percent": 59,
            "projected_away_score": 20.0,
            "projected_home_score": 23.0
          }
        }
        """)
    }

    private func makeThreeWaySoccerGame() throws -> FeedEventData {
        try decodeFeedEvent("""
        {
          "id": 15346904,
          "sport": "soccer_uefa_champs_league",
          "sport_name": "Champions League",
          "away_team": "Manchester City",
          "home_team": "Real Madrid",
          "commence_time": "2026-11-15T20:00:00Z",
          "status": "scheduled",
          "prematch_odds": {
            "away_probability": 0.36,
            "home_probability": 0.39,
            "draw_probability": 0.25,
            "source": "kalshi"
          },
          "current_odds": {
            "away_probability": 0.36,
            "home_probability": 0.39,
            "draw_probability": 0.25
          }
        }
        """)
    }

    private func makeHeadlineModels() throws -> (nflBefore: EventSportHeadlines12472.Model, nbaDuring: EventSportHeadlines12472.Model) {
        let fixedNow = ISO8601DateFormatter().date(from: "2026-11-14T10:00:00Z")!
        let nflDetail = try decodeEventDetail("""
        {
          "id": 9124721,
          "sport": "americanfootball_nfl",
          "home_team": "San Francisco 49ers",
          "away_team": "Washington Commanders",
          "commence_time": "2026-11-15T21:25:00Z",
          "start_is_tbd": false,
          "status": "scheduled",
          "home_team_data": {"abbreviation": "SF", "primary_color": "#AA0000", "record": "6-3"},
          "away_team_data": {"abbreviation": "WAS", "primary_color": "#5A1414", "record": "7-3"},
          "current_odds": {
            "home_probability": 0.66,
            "away_probability": 0.34,
            "home_rendered_percent": 66,
            "away_rendered_percent": 34,
            "projected_home_score": 26.5,
            "projected_away_score": 21.0,
            "updated_at": "2026-11-14T09:58:00Z"
          },
          "hero_probability": 0.66,
          "hero_probability_away": 0.34,
          "hero_probability_source": "blend",
          "hero_probability_observed_at": "2026-11-14T09:58:00Z",
          "espn": {"broadcast": "CBS"}
        }
        """)

        let nbaDetail = try decodeEventDetail("""
        {
          "id": 9124722,
          "sport": "basketball_nba",
          "home_team": "Minnesota Timberwolves",
          "away_team": "Portland Trail Blazers",
          "commence_time": "2026-11-14T08:00:00Z",
          "start_is_tbd": false,
          "status": "live",
          "home_score": 94,
          "away_score": 87,
          "home_team_data": {"abbreviation": "MIN", "primary_color": "#0C2340", "record": "8-4"},
          "away_team_data": {"abbreviation": "POR", "primary_color": "#E03A3E", "record": "4-8"},
          "opening_odds": {
            "home_probability": 0.68,
            "away_probability": 0.32,
            "home_rendered_percent": 68,
            "away_rendered_percent": 32
          },
          "current_odds": {
            "home_probability": 0.814,
            "away_probability": 0.186,
            "in_play_projected_home_score": 116.0,
            "in_play_projected_away_score": 108.0,
            "updated_at": "2026-11-14T09:59:50Z"
          },
          "hero_probability": 0.814,
          "hero_probability_away": 0.186,
          "hero_probability_source": "blend",
          "hero_probability_observed_at": "2026-11-14T09:59:50Z",
          "espn": {"period": "4Q", "game_clock": "4:18"}
        }
        """)

        let nflModel = try XCTUnwrap(EventSportHeadlines12472.resolve(
            event: nflDetail,
            awayFullName: nflDetail.awayTeam,
            homeFullName: nflDetail.homeTeam,
            liveStatusText: nil,
            hasScore: false,
            numberStreams: false,
            ladderHome: 26.5,
            ladderAway: 21.0,
            now: fixedNow
        ))

        let nbaModel = try XCTUnwrap(EventSportHeadlines12472.resolve(
            event: nbaDetail,
            awayFullName: nbaDetail.awayTeam,
            homeFullName: nbaDetail.homeTeam,
            liveStatusText: "4Q · 4:18",
            hasScore: true,
            numberStreams: true,
            ladderHome: nil,
            ladderAway: nil,
            now: fixedNow
        ))

        return (nflModel, nbaModel)
    }

    private func makeGroupedPairedSet() throws -> PairedMetricSet {
        try decodePairedSet(#"""
        {
          "set_id": "nhl-playoffs-cup-2027",
          "category": "sports",
          "kicker": "NHL · STANLEY CUP RACE",
          "title": "Edmonton Oilers lead the Cup race, with 5 clubs above 85% to make the playoffs",
          "subtitle": "2026–27 NHL season · Playoff % paired beside Stanley Cup %",
          "stage_1_label": "Make Playoffs",
          "stage_2_label": "Win Cup",
          "entries": [
            {
              "subject_key": "nhl:edmonton-oilers",
              "subject": "Edmonton Oilers",
              "detail": "Pacific Division",
              "stage_1_market_id": 701,
              "stage_1_probability": 0.94,
              "stage_2_market_id": 801,
              "stage_2_probability": 0.19
            },
            {
              "subject_key": "nhl:dallas-stars",
              "subject": "Dallas Stars",
              "detail": "Central Division",
              "stage_1_market_id": 702,
              "stage_1_probability": 0.91,
              "stage_2_market_id": 802,
              "stage_2_probability": 0.15
            },
            {
              "subject_key": "nhl:carolina-hurricanes",
              "subject": "Carolina Hurricanes",
              "detail": "Metropolitan Division",
              "stage_1_market_id": 703,
              "stage_1_probability": 0.89,
              "stage_2_market_id": 803,
              "stage_2_probability": 0.13
            },
            {
              "subject_key": "nhl:colorado-avalanche",
              "subject": "Colorado Avalanche",
              "detail": "Central Division",
              "stage_1_market_id": 704,
              "stage_1_probability": 0.87,
              "stage_2_market_id": 804,
              "stage_2_probability": 0.11
            },
            {
              "subject_key": "nhl:minnesota-wild",
              "subject": "Minnesota Wild",
              "detail": "Central Division",
              "stage_1_market_id": 705,
              "stage_1_probability": 0.62,
              "stage_2_market_id": 805,
              "stage_2_probability": 0.05
            },
            {
              "subject_key": "nhl:vegas-golden-knights",
              "subject": "Vegas Golden Knights",
              "detail": "Pacific Division",
              "stage_1_market_id": 706,
              "stage_1_probability": 0.78,
              "stage_2_market_id": 806,
              "stage_2_probability": 0.08
            }
          ]
        }
        """#)
    }

    // MARK: - Measurement & OCR Helpers

    private func renderViewToImage<V: View>(
        _ content: V,
        width: CGFloat,
        typeSize: DynamicTypeSize
    ) -> UIImage {
        let wrapped = content
            .frame(width: width)
            .fixedSize(horizontal: false, vertical: true)
            .background(Color(red: 0.965, green: 0.965, blue: 0.973))
            .environmentObject(pins)
            .environment(\.colorScheme, .light)

        let renderer = rendererForMeasurement(wrapped, at: typeSize)
        renderer.scale = 2.0
        renderer.proposedSize = ProposedViewSize(width: width, height: nil)
        return renderer.uiImage ?? UIImage()
    }

    private func recognizeStrings(in image: UIImage) throws -> [String] {
        guard let cg = image.cgImage else { return [] }
        // Tile tall images into 900pt slices so Vision never downscales large vertical sheets.
        let slicePx = Int(900 * image.scale)
        let overlapPx = Int(120 * image.scale)
        var all: [String] = []
        var y = 0
        while y < cg.height {
            let h = min(slicePx, cg.height - y)
            if let cropped = cg.cropping(to: CGRect(x: 0, y: y, width: cg.width, height: h)) {
                let req = VNRecognizeTextRequest()
                req.recognitionLevel = .accurate
                req.usesLanguageCorrection = false
                try VNImageRequestHandler(cgImage: cropped, options: [:]).perform([req])
                let lines = (req.results ?? []).compactMap { $0.topCandidates(1).first?.string }
                all.append(contentsOf: lines)
            }
            if y + h >= cg.height { break }
            y += (slicePx - overlapPx)
        }
        return all
    }

    private func maybeSavePNG(_ image: UIImage, filename: String) throws {
        guard let dir = ProcessInfo.processInfo.environment["OVERNIGHT8_RENDER_DIR"],
              !dir.isEmpty else { return }
        let folderURL = URL(fileURLWithPath: dir)
        try FileManager.default.createDirectory(at: folderURL, withIntermediateDirectories: true)
        let data = try XCTUnwrap(image.pngData())
        try data.write(to: folderURL.appendingPathComponent(filename))
    }

    // MARK: - 1. Discover Single-Game Cards (190-C + 191-A) at AX5 & Narrow iPad/Mac Masonry

    func testDiscoverCardsAtAccessibility5AndNarrowMasonryDoNotRepeatPregameOrClip() async throws {
        let scheduled = try makeScheduledNFLGame()
        let soccer = try makeThreeWaySoccerGame()
        let (live, liveHistory) = try makeLiveDiscoverGame()
        let (finished, finishedHistory) = try makeFinishedDiscoverGame()

        // Finished Discover card at AX5: "PREGAME" appears ONCE in the column header, never per row.
        let finishedCardImage = renderViewToImage(
            NativeEventDiscoverCard(
                event: finished,
                feedContext: nil,
                expandedContext: nil,
                navigationPath: .constant(NavigationPath()),
                chartHistory: finishedHistory
            )
            .padding(16),
            width: 390,
            typeSize: .accessibility5
        )
        let finishedLines = try recognizeStrings(in: finishedCardImage)
        let joinedFinished = finishedLines.joined(separator: " ")
        XCTAssertTrue(joinedFinished.replacingOccurrences(of: " ", with: "").contains("WashingtonCommanders"),
                      "Complete away team name must read at AX5: \(finishedLines)")
        XCTAssertTrue(joinedFinished.replacingOccurrences(of: " ", with: "").contains("SanFrancisco49ers"),
                      "Complete home team name must read at AX5: \(finishedLines)")
        for line in finishedLines {
            XCTAssertFalse(line.contains("\u{2026}"), "No line may truncate with ellipsis at AX5: '\(line)'")
        }
        // Row cells must not repeat "Pregame 24%" / "Pregame 76%" on each team row.
        let perRowPregameMentions = finishedLines.filter {
            let low = $0.lowercased()
            return low.contains("pregame 24%") || low.contains("pregame 76%")
        }
        XCTAssertTrue(perRowPregameMentions.isEmpty,
                      "Finished Discover card rows must not repeat 'Pregame <pct>' per row: \(finishedLines)")

        // Narrow 300pt iPad/Mac 3-column masonry card with 191-A chart panel: right endpoint label never clips.
        let narrowLivePanel = renderViewToImage(
            NativeEventDiscoverCard(
                event: live,
                feedContext: "Celtics pulling away in the fourth quarter",
                expandedContext: nil,
                navigationPath: .constant(NavigationPath()),
                chartHistory: liveHistory
            ),
            width: 300,
            typeSize: .large
        )
        let narrowLines = try recognizeStrings(in: narrowLivePanel)
        for line in narrowLines {
            XCTAssertFalse(line.contains("\u{2026}"), "Narrow 300pt masonry card must not elide '\(line)'")
        }

        // 390px AX5 sheets of Discover single-game states (split cleanly for easy inspection)
        let discoverScheduledSoccer = VStack(spacing: 16) {
            NativeEventDiscoverCard(
                event: scheduled,
                feedContext: "NFC North lead on the line",
                expandedContext: nil,
                navigationPath: .constant(NavigationPath())
            )
            NativeEventDiscoverCard(
                event: soccer,
                feedContext: nil,
                expandedContext: nil,
                navigationPath: .constant(NavigationPath())
            )
        }
        .padding(16)

        let discoverLiveFinished = VStack(spacing: 16) {
            NativeEventDiscoverCard(
                event: live,
                feedContext: "Fourth-quarter run",
                expandedContext: nil,
                navigationPath: .constant(NavigationPath()),
                chartHistory: liveHistory
            )
            NativeEventDiscoverCard(
                event: finished,
                feedContext: nil,
                expandedContext: nil,
                navigationPath: .constant(NavigationPath()),
                chartHistory: finishedHistory
            )
        }
        .padding(16)

        try maybeSavePNG(
            renderViewToImage(discoverScheduledSoccer, width: 390, typeSize: .accessibility5),
            filename: "overnight8-discover-pregame-soccer-ax5-390.png"
        )
        try maybeSavePNG(
            renderViewToImage(discoverLiveFinished, width: 390, typeSize: .accessibility5),
            filename: "overnight8-discover-live-finished-ax5-390.png"
        )
    }

    // MARK: - 2. Sports Cards & Game-Page Headlines at AX5

    func testSportsCardsAndHeadlinesAtAccessibility5DoNotClipNamesOrBreakTopBar() throws {
        let scheduled = try makeScheduledNFLGame()
        let soccer = try makeThreeWaySoccerGame()
        let (live, _) = try makeLiveDiscoverGame()
        let (nflBefore, nbaDuring) = try makeHeadlineModels()
        let ekg = EkgTracker()

        let sportsSheet = VStack(spacing: 16) {
            EventCardView(event: scheduled, reason: "Divisional matchup")
                .padding(14)
                .background(Color.cardBackground)
                .clipShape(RoundedRectangle(cornerRadius: 14))

            EventCardView(event: live, reason: nil)
                .padding(14)
                .background(Color.cardBackground)
                .clipShape(RoundedRectangle(cornerRadius: 14))

            EventCardView(event: soccer, reason: nil)
                .padding(14)
                .background(Color.cardBackground)
                .clipShape(RoundedRectangle(cornerRadius: 14))
        }
        .padding(16)

        let headlinesSheet = VStack(spacing: 16) {
            EventSportHeadlineCard12472(
                model: nflBefore,
                colors: (away: Color(red: 0.35, green: 0.08, blue: 0.08), home: Color(red: 0.67, green: 0.0, blue: 0.0)),
                ekgTracker: ekg,
                liveUpdateStatus: .live,
                displayAsOf: ISO8601DateFormatter().date(from: "2026-11-14T09:58:00Z"),
                updateStream: LiveUpdateStream(),
                showUpdateStream: .constant(false),
                showProbabilityDetails: .constant(false),
                priceStreamingEligible: false,
                lastReceivedAt: nil,
                confirmedAt: nil,
                revealForecast: nil
            )

            EventSportHeadlineCard12472(
                model: nbaDuring,
                colors: (away: Color(red: 0.88, green: 0.23, blue: 0.24), home: Color(red: 0.05, green: 0.14, blue: 0.25)),
                ekgTracker: ekg,
                liveUpdateStatus: .live,
                displayAsOf: ISO8601DateFormatter().date(from: "2026-11-14T09:59:50Z"),
                updateStream: LiveUpdateStream(),
                showUpdateStream: .constant(false),
                showProbabilityDetails: .constant(false),
                priceStreamingEligible: true,
                lastReceivedAt: nil,
                confirmedAt: nil,
                revealForecast: nil
            )
        }
        .padding(16)

        let sportsImg = renderViewToImage(sportsSheet, width: 390, typeSize: .accessibility5)
        let headlinesImg = renderViewToImage(headlinesSheet, width: 390, typeSize: .accessibility5)
        let lines = try recognizeStrings(in: sportsImg) + recognizeStrings(in: headlinesImg)
        let compactJoined = lines.joined().replacingOccurrences(of: " ", with: "")
        XCTAssertTrue(compactJoined.contains("Timberwolves"),
                      "NBA during-game headline must show complete 'Timberwolves' at AX5: \(lines)")
        XCTAssertTrue(compactJoined.contains("Commanders"),
                      "NFL before-game headline must show complete 'Commanders' at AX5: \(lines)")
        XCTAssertTrue(compactJoined.contains("Packers"),
                      "Scheduled EventCardView must show complete 'Packers' at AX5: \(lines)")
        for line in lines {
            XCTAssertFalse(line.contains("\u{2026}"), "No headline or sports card line may truncate at AX5: '\(line)'")
        }
        try maybeSavePNG(sportsImg, filename: "overnight8-sports-cards-ax5-390.png")
        try maybeSavePNG(headlinesImg, filename: "overnight8-headlines-ax5-390.png")
    }

    // MARK: - 3. Grouped Cards (Look 1 & Look 2) at AX5 and Narrow iPad/Mac Masonry

    func testGroupedCardsScaleCleanlyAtAX5AndInNarrowMasonryColumns() throws {
        let pairedSet = try makeGroupedPairedSet()

        let look1AX5 = renderViewToImage(
            DiscoverPairedMetricCardView(set: pairedSet, form: .pairedBarsTop5Expandable).padding(16),
            width: 390,
            typeSize: .accessibility5
        )
        let look2AX5 = renderViewToImage(
            DiscoverPairedMetricCardView(set: pairedSet, form: .podiumAndTiers).padding(16),
            width: 390,
            typeSize: .accessibility5
        )
        let look1Large = renderViewToImage(
            DiscoverPairedMetricCardView(set: pairedSet, form: .pairedBarsTop5Expandable).padding(16),
            width: 390,
            typeSize: .large
        )
        XCTAssertGreaterThan(look1AX5.size.height, look1Large.size.height * 1.25,
                             "Grouped cards must scale up legibly at largest text size instead of staying fixed 11-14pt")

        let ax5Lines = try recognizeStrings(in: look1AX5) + recognizeStrings(in: look2AX5)
        for line in ax5Lines {
            XCTAssertFalse(line.contains("\u{2026}"), "Grouped card at AX5 must not clip text: '\(line)'")
        }
        try maybeSavePNG(look1AX5, filename: "overnight8-grouped-look1-ax5-390.png")
        try maybeSavePNG(look2AX5, filename: "overnight8-grouped-look2-ax5-390.png")

        // iPad two-column masonry (834pt iPad Pro 11 portrait -> two columns) at AX5,
        // plus 390px narrow-column sheet showing 300pt iPad/Mac 3-col masonry cards.
        let (live, liveHistory) = try makeLiveDiscoverGame()
        let scheduled = try makeScheduledNFLGame()

        let ipadTwoCol = HStack(alignment: .top, spacing: DiscoverMasonry.spacing) {
            VStack(spacing: DiscoverMasonry.spacing) {
                NativeEventDiscoverCard(
                    event: live,
                    feedContext: "Celtics pulling away in the fourth quarter",
                    expandedContext: nil,
                    navigationPath: .constant(NavigationPath()),
                    chartHistory: liveHistory
                )
                EventCardView(event: scheduled, reason: "Divisional matchup")
                    .padding(14)
                    .background(Color.cardBackground)
                    .clipShape(RoundedRectangle(cornerRadius: 14))
            }
            .frame(maxWidth: .infinity)

            VStack(spacing: DiscoverMasonry.spacing) {
                DiscoverPairedMetricCardView(set: pairedSet, form: .podiumAndTiers)
            }
            .frame(maxWidth: .infinity)
        }
        .padding(16)

        let ipadImg = renderViewToImage(ipadTwoCol, width: 834, typeSize: .accessibility5)
        try maybeSavePNG(ipadImg, filename: "overnight8-ipad-2col-ax5-834.png")

        let narrowMasonrySheet390 = VStack(spacing: 14) {
            Text("iPad / Mac 3-column masonry minimum width (300 pt)")
                .font(.caption.weight(.semibold))
                .foregroundStyle(.secondary)
            NativeEventDiscoverCard(
                event: live,
                feedContext: "Celtics pulling away in the fourth quarter",
                expandedContext: nil,
                navigationPath: .constant(NavigationPath()),
                chartHistory: liveHistory
            )
            .frame(width: 300)
            DiscoverPairedMetricCardView(set: pairedSet, form: .podiumAndTiers)
                .frame(width: 300)
            DiscoverPairedMetricCardView(set: pairedSet, form: .pairedBarsTop5Expandable)
                .frame(width: 300)
        }
        .padding(.vertical, 16)

        let narrow390Img = renderViewToImage(narrowMasonrySheet390, width: 390, typeSize: .large)
        let narrow390Lines = try recognizeStrings(in: narrow390Img)
        for line in narrow390Lines {
            XCTAssertFalse(line.contains("\u{2026}"), "300pt iPad/Mac masonry cards must not elide: '\(line)'")
        }
        try maybeSavePNG(narrow390Img, filename: "overnight8-ipad-mac-300pt-masonry-390.png")
    }
}
#endif
