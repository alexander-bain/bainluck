import CryptoKit
import SwiftUI
import UIKit
import Vision
import XCTest
@testable import Bain_Luck

/// Item 5 (`#12639`), Item 6 (`1.0.7` `.xxxLarge` iPhone `390 pt` & iPad `834 pt` walk +
/// card-face `Kalshi` / `Polymarket` removal), and Item 7 (`1.0.8` `#12642` Look Sheet 2).
@MainActor
final class ReleaseReadinessWalk107Tests: XCTestCase {

    private func decodeJSON<T: Decodable>(_ type: T.Type, _ json: String) throws -> T {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(type, from: Data(json.utf8))
    }

    private func decodeFile<T: Decodable>(_ type: T.Type, path: String) throws -> T {
        let data = try Data(contentsOf: URL(fileURLWithPath: path))
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(type, from: data)
    }

    /// Renders a single bounded view block (`<= 2000 pt` tall at `2x` = `<= 4000 px`, well below
    /// iOS Simulator `CARenderServer`'s `8192 px` backing-store limit) so `drawHierarchy` never fails.
    private func renderBlock<V: View>(
        _ content: V,
        width: CGFloat,
        maxHeight: CGFloat = 1950,
        dynamicType: DynamicTypeSize = .xxxLarge,
        sizeClass: UserInterfaceSizeClass = .compact,
        scheme: ColorScheme = .light
    ) -> UIImage {
        let uiStyle: UIUserInterfaceStyle = (scheme == .dark) ? .dark : .light
        let outerBg = (scheme == .dark) ? Color(hex: "#0F1115") : DS.surface
        let wrapped = content
            .frame(width: width, alignment: .topLeading)
            .background(outerBg)
            .environment(\.colorScheme, scheme)
            .environment(\.horizontalSizeClass, sizeClass)
            .environment(\.dynamicTypeSize, dynamicType)
            .environmentObject(PinManager())
            .environmentObject(NavigationCoordinator())

        let host = hostForMeasurement(wrapped, at: dynamicType)
        host.overrideUserInterfaceStyle = uiStyle
        let fitting = host.sizeThatFits(in: CGSize(width: width, height: maxHeight))
        let clampedHeight = min(maxHeight, max(80, ceil(fitting.height)))
        let size = CGSize(width: width, height: clampedHeight)
        host.view.frame = CGRect(origin: .zero, size: size)

        let window: UIWindow
        if let scene = UIApplication.shared.connectedScenes.compactMap({ $0 as? UIWindowScene }).first {
            window = UIWindow(windowScene: scene)
        } else {
            window = UIWindow(frame: host.view.frame)
        }
        window.frame = host.view.frame
        window.overrideUserInterfaceStyle = uiStyle
        window.rootViewController = host
        window.isHidden = false
        defer {
            window.isHidden = true
            window.rootViewController = nil
        }

        let until = Date().addingTimeInterval(0.22)
        repeat {
            host.view.setNeedsLayout()
            host.view.layoutIfNeeded()
            RunLoop.current.run(until: Date().addingTimeInterval(0.02))
        } while Date() < until

        let fmt = UIGraphicsImageRendererFormat()
        fmt.scale = 2.0
        fmt.opaque = true
        return UIGraphicsImageRenderer(bounds: host.view.bounds, format: fmt).image { ctx in
            let bg = (scheme == .dark)
                ? UIColor(red: 0.059, green: 0.067, blue: 0.082, alpha: 1.0)
                : UIColor.white
            bg.setFill()
            ctx.fill(host.view.bounds)
            if !host.view.drawHierarchy(in: host.view.bounds, afterScreenUpdates: true) {
                host.view.layer.render(in: ctx.cgContext)
            }
        }
    }

    private func stitchVertically(
        _ blocks: [UIImage],
        width: CGFloat,
        spacing: CGFloat = 12,
        scheme: ColorScheme = .light
    ) -> UIImage {
        let totalHeight = blocks.reduce(CGFloat(0)) { $0 + $1.size.height }
            + CGFloat(max(0, blocks.count - 1)) * spacing
        let fmt = UIGraphicsImageRendererFormat()
        fmt.scale = 2.0
        fmt.opaque = true
        return UIGraphicsImageRenderer(size: CGSize(width: width, height: max(1, totalHeight)), format: fmt).image { ctx in
            let bg = (scheme == .dark)
                ? UIColor(red: 0.059, green: 0.067, blue: 0.082, alpha: 1.0)
                : UIColor.white
            bg.setFill()
            ctx.fill(CGRect(x: 0, y: 0, width: width, height: max(1, totalHeight)))
            var y: CGFloat = 0
            for img in blocks {
                img.draw(in: CGRect(x: 0, y: y, width: img.size.width, height: img.size.height))
                y += img.size.height + spacing
            }
        }
    }

    private func ocrLines(_ image: UIImage) throws -> [String] {
        let req = VNRecognizeTextRequest()
        req.recognitionLevel = .accurate
        req.usesLanguageCorrection = false
        req.minimumTextHeight = 0.0
        try VNImageRequestHandler(cgImage: XCTUnwrap(image.cgImage)).perform([req])
        return (req.results ?? []).compactMap { $0.topCandidates(1).first?.string }
    }

    // MARK: - 1. Deterministic Card-Face Venue Guard at .xxxLarge (iPhone 390pt & iPad 834pt)

    func testCardFacesNeverPrintKalshiOrPolymarketAtXxxLarge() throws {
        let singleKalshiFutures = try decodeJSON(FeedFuturesData.self, """
        {
          "id": 910001,
          "name": "2028 U.S. Presidential Election Winner",
          "llm_sport_category": "politics",
          "source": "kalshi",
          "source_count": 1,
          "sources": ["kalshi"],
          "status": "open",
          "outcome_count": 6,
          "top_outcomes": [
            {"id": 1, "name": "JD Vance", "probability": 0.31, "rendered_percent": 31, "rank": 1},
            {"id": 2, "name": "Gavin Newsom", "probability": 0.22, "rendered_percent": 22, "rank": 2}
          ]
        }
        """)
        let multiSourceDist = try decodeJSON(FeedFuturesData.self, """
        {
          "id": 910002,
          "name": "Will the U.S. confirm extraterrestrial life?",
          "llm_sport_category": "science",
          "source": "polymarket",
          "source_count": 2,
          "sources": ["kalshi", "polymarket"],
          "status": "open",
          "outcome_count": 4,
          "top_outcomes": [
            {"id": 11, "name": "Before 2029", "probability": 0.23, "rendered_percent": 23, "rank": 1},
            {"id": 12, "name": "Before 2028", "probability": 0.16, "rendered_percent": 16, "rank": 2}
          ],
          "discover_card": {
            "suggested_format": "outcome_distribution",
            "bundle_candidate": false,
            "threshold_points": [],
            "distribution_outcomes": [
              {"label": "Before 2029", "probability": 0.23, "rendered_percent": 23},
              {"label": "Before 2028", "probability": 0.16, "rendered_percent": 16}
            ],
            "remaining_outcome_count": 2,
            "qa_signals": [],
            "public_source_disagreement": false,
            "reasons": []
          }
        }
        """)
        let polymarketHeatMap = try decodeJSON(FeedFuturesData.self, """
        {
          "id": 910003,
          "name": "Anthropic IPO Market Cap Thresholds",
          "llm_sport_category": "tech",
          "source": "polymarket",
          "source_count": 1,
          "sources": ["polymarket"],
          "status": "open",
          "outcome_count": 3,
          "top_outcomes": [
            {"id": 21, "name": "Above $80B", "probability": 0.64, "rendered_percent": 64, "rank": 1}
          ],
          "discover_card": {
            "suggested_format": "threshold_heatmap",
            "bundle_candidate": false,
            "threshold_points": [
              {"label": "Above $60B", "value": 60, "probability": 0.82},
              {"label": "Above $80B", "value": 80, "probability": 0.64},
              {"label": "Above $100B", "value": 100, "probability": 0.39}
            ],
            "distribution_outcomes": [],
            "remaining_outcome_count": 0,
            "qa_signals": [],
            "public_source_disagreement": false,
            "reasons": []
          }
        }
        """)
        let facetedPolymarket = try decodeJSON(FacetedFuturesMarket.self, """
        {
          "id": 910004,
          "name": "NBA Championship Winner",
          "llm_sport_category": "basketball_nba",
          "source": "polymarket",
          "outcome_count": 30,
          "top_outcomes": [
            {"id": 31, "name": "Boston Celtics", "probability": 0.24, "rendered_percent": 24},
            {"id": 32, "name": "Oklahoma City Thunder", "probability": 0.21, "rendered_percent": 21}
          ]
        }
        """)
        let matchedOutcomes = try decodeJSON([MatchedOutcome].self, """
        [
          {"name": "New England Patriots", "probability": 0.04, "rank": 18}
        ]
        """)

        let individualCards: [AnyView] = [
            AnyView(NativeFuturesDiscoverCard(
                data: singleKalshiFutures,
                feedContext: nil,
                expandedContext: nil,
                navigationPath: .constant(NavigationPath())
            ).padding(16)),
            AnyView(DistributionCardView(data: multiSourceDist, navigationPath: .constant(NavigationPath())).padding(16)),
            AnyView(HeatMapCardView(data: polymarketHeatMap, navigationPath: .constant(NavigationPath())).padding(16)),
            AnyView(FuturesBrowseMarketRow(market: facetedPolymarket).padding(16)),
            AnyView(MyTeamFuturesCard(futures: singleKalshiFutures, matchedOutcomes: matchedOutcomes).padding(16)),
            AnyView(DSMarketCard(question: "Fed cuts 25 bps in December?", probability: 68, source: "kalshi").padding(16)),
        ]

        for (width, sizeClass) in [(CGFloat(390), UserInterfaceSizeClass.compact), (CGFloat(834), UserInterfaceSizeClass.regular)] {
            var allLines: [String] = []
            for card in individualCards {
                let img = renderBlock(card, width: width, maxHeight: 1200, dynamicType: .xxxLarge, sizeClass: sizeClass)
                allLines.append(contentsOf: try ocrLines(img))
            }
            let joined = allLines.joined(separator: " ")
            XCTAssertFalse(allLines.isEmpty, "Rendered cards must produce readable OCR text")

            for banned in ["Kalshi", "Polymarket", "kalshi", "polymarket"] {
                XCTAssertFalse(
                    joined.localizedCaseInsensitiveContains(banned),
                    "Card faces at \(Int(width))pt .xxxLarge must never print '\(banned)'; got OCR lines: \(allLines)"
                )
            }
            XCTAssertTrue(
                joined.contains("2 sources"),
                "Multi-source card must still print '2 sources' at \(Int(width))pt .xxxLarge; got OCR lines: \(allLines)"
            )
            XCTAssertFalse(
                allLines.contains(where: { $0.contains("...") || $0.contains("…") }),
                "Card faces at \(Int(width))pt .xxxLarge must not truncate with ellipsis; got OCR lines: \(allLines)"
            )
        }

        // Verify AboutView at .xxxLarge never hyphenates 'Entertainment' on 390pt iPhone
        // and never truncates 'Prediction markets' to 'Prediction...' on 834pt iPad:
        for (width, sizeClass) in [(CGFloat(390), UserInterfaceSizeClass.compact), (CGFloat(834), UserInterfaceSizeClass.regular)] {
            let aboutImg = renderBlock(
                AboutView().frame(height: 920),
                width: width,
                maxHeight: 1100,
                dynamicType: .xxxLarge,
                sizeClass: sizeClass
            )
            let aboutLines = try ocrLines(aboutImg)
            XCTAssertFalse(
                aboutLines.contains(where: { $0.hasPrefix("Enter-") }),
                "AboutView domain pills must never hyphenate 'Entertainment' at \(Int(width))pt .xxxLarge; got: \(aboutLines)"
            )
            XCTAssertFalse(
                aboutLines.contains(where: { $0.contains("Prediction...") || $0.contains("Prediction…") }),
                "AboutView One number pill must never truncate 'Prediction markets' at \(Int(width))pt .xxxLarge; got: \(aboutLines)"
            )
        }
    }

    func testFinishedWinnerTickSitsAfterNameNotAfterScore() throws {
        let finishedJSON = """
        {
          "id": 900101, "sport": "americanfootball_nfl", "sport_name": "NFL", "status": "completed",
          "commence_time": "2026-11-16T01:15:00Z", "away_team": "Los Angeles Chargers", "home_team": "Baltimore Ravens",
          "away_score": 23, "home_score": 30,
          "away_team_data": { "abbreviation": "LAC", "primary_color": "#0080C6" },
          "home_team_data": { "abbreviation": "BAL", "primary_color": "#241773" },
          "prematch_odds": { "away_probability": 0.42, "home_probability": 0.58 }
        }
        """
        let feedEvent = try decodeJSON(FeedEventData.self, finishedJSON)
        let cols = TeamTextContrast.cardColors(
            awayHex: feedEvent.awayTeamData?.primaryColor,
            homeHex: feedEvent.homeTeamData?.primaryColor,
            awaySecondaryHex: nil,
            checkHueFamily: true
        )
        let img = renderBlock(
            VStack(spacing: 12) {
                EventCardView(event: feedEvent, reason: nil)
                DiscoverCompactSingleGameCard190CView(
                    event: feedEvent,
                    prematch: PrematchReading.resolve(prematch: feedEvent.prematchOdds, opening: feedEvent.openingOdds),
                    awayColor: cols.away,
                    homeColor: cols.home,
                    projectionAndSuspendedLines: { EmptyView() },
                    footerRow: { EmptyView() }
                )
            }.padding(16),
            width: 390,
            maxHeight: 600,
            dynamicType: .large,
            sizeClass: .compact
        )
        let lines = try ocrLines(img)
        XCTAssertFalse(
            lines.contains(where: { $0.contains("30 ✓") || $0.contains("30✔") || $0.contains("23 ✓") }),
            "Winner tick must never sit to the right of a score; got OCR lines: \(lines)"
        )
    }

    // MARK: - 2. Full Live-Payload Export: #12639 + 1.0.7 .xxxLarge Walk (iPhone & iPad) + #12642 Look Sheet 2

    func testExportLive12639ConnectedChartsAnd107WalkAtXxxLarge() throws {
        guard let exportDir = ProcessInfo.processInfo.environment["EXPORT_107_WALK_DIR"],
              !exportDir.isEmpty else {
            return
        }
        let outURL = URL(fileURLWithPath: exportDir, isDirectory: true)
        try FileManager.default.createDirectory(at: outURL, withIntermediateDirectories: true)

        let live12639Dir = ProcessInfo.processInfo.environment["LIVE_12639_DIR"]
            ?? "/Users/bain/.gemini/antigravity/brain/4c590449-f20c-4ff4-921d-f7e1343a4327/scratch/12639-live"
        let liveWalkDir = ProcessInfo.processInfo.environment["LIVE_WALK_DIR"]
            ?? "/Users/bain/.gemini/antigravity/brain/4c590449-f20c-4ff4-921d-f7e1343a4327/scratch/107-walk-live"

        // ── PART A: Item 5 (#12639) — Connected Win-Prob & Projected-Final Charts (Light & Dark 390 px) ──
        let celticsSixersEvent = try decodeFile(EventDetail.self, path: "\(live12639Dir)/15344730_event.json")
        let celticsSixersHist = try decodeFile(EventHistoryResponse.self, path: "\(live12639Dir)/15344730_history.json")
        let chargersRavensEvent = try decodeFile(EventDetail.self, path: "\(live12639Dir)/event-14780579.json")
        let chargersRavensHist = try decodeFile(EventHistoryResponse.self, path: "\(live12639Dir)/history-14780579.json")

        @ViewBuilder
        func chartPairBlock(
            event: EventDetail,
            history: EventHistoryResponse,
            label: String,
            scheme: ColorScheme
        ) -> some View {
            let pairCols = TeamTextContrast.surfaceColors(
                awayHex: event.awayTeamData?.primaryColor,
                homeHex: event.homeTeamData?.primaryColor,
                awaySecondaryHex: event.awayTeamData?.secondaryColor,
                homeSecondaryHex: event.homeTeamData?.secondaryColor,
                colorScheme: scheme,
                checkHueFamily: true
            )
            let projInput = ProjectedFinalPointsMount.input(
                sportKey: event.sport,
                eventStatus: event.status,
                history: history,
                finalHome: event.homeScore,
                finalAway: event.awayScore
            )
            VStack(alignment: .leading, spacing: 10) {
                Text(label)
                    .font(.caption.weight(.bold))
                    .foregroundStyle(scheme == .dark ? Color.white.opacity(0.75) : Color.secondary)
                    .fixedSize(horizontal: false, vertical: true)

                OddsChartView(
                    eventId: event.id,
                    teamColors: pairCols,
                    commenceTime: event.commenceTime,
                    status: event.status,
                    venueSettled: event.venueSettled == true,
                    homeTeamName: event.homeTeam,
                    awayTeamName: event.awayTeam,
                    homeTeamAbbrev: event.homeTeamData?.abbreviation,
                    awayTeamAbbrev: event.awayTeamData?.abbreviation,
                    sportKey: event.sport,
                    homeScore: event.homeScore,
                    awayScore: event.awayScore,
                    servedSettledResult: event.heroSettledResult,
                    servedHomeProbability: event.currentOdds?.homeProbability,
                    servedAwayProbability: event.currentOdds?.awayProbability,
                    selectedRange: .constant(.sinceStart),
                    preloadedHistory: history,
                    preloadedHistoryGeneration: 1
                )
                .background(Color.cardBackground)
                .clipShape(RoundedRectangle(cornerRadius: 12))

                if let projInput {
                    ProjectedFinalPointsChartView(
                        input: projInput,
                        homeTeam: event.homeTeam,
                        awayTeam: event.awayTeam,
                        homeColor: pairCols.home,
                        awayColor: pairCols.away,
                        periodMarkers: history.periodMarkers,
                        sportKey: event.sport
                    )
                    .padding(16)
                    .background(Color.cardBackground)
                    .clipShape(RoundedRectangle(cornerRadius: 12))
                }
            }
        }

        for (schemeName, scheme) in [("light", ColorScheme.light), ("dark", ColorScheme.dark)] {
            let b1 = renderBlock(
                VStack(alignment: .leading, spacing: 12) {
                    Text("#12639 · Connected Straight-Segment Charts (\(schemeName.capitalized), 390 px)")
                        .font(.subheadline.weight(.bold))
                        .foregroundStyle(scheme == .dark ? Color.white : Color.primary)
                        .fixedSize(horizontal: false, vertical: true)
                    chartPairBlock(
                        event: celticsSixersEvent,
                        history: celticsSixersHist,
                        label: "Event 15344730 · Celtics at 76ers (NBA Final — Web Parity Specimen)",
                        scheme: scheme
                    )
                }.padding(16),
                width: 390, maxHeight: 1600, dynamicType: .large, sizeClass: .compact, scheme: scheme
            )
            let b2 = renderBlock(
                chartPairBlock(
                    event: chargersRavensEvent,
                    history: chargersRavensHist,
                    label: "Event 14780579 · Chargers at Ravens (NFL Final)",
                    scheme: scheme
                ).padding(16),
                width: 390, maxHeight: 1600, dynamicType: .large, sizeClass: .compact, scheme: scheme
            )
            let stitched = stitchVertically([b1, b2], width: 390, spacing: 4, scheme: scheme)
            try XCTUnwrap(stitched.pngData()).write(to: outURL.appendingPathComponent("12639-connected-charts-\(schemeName)-390.png"))
        }

        // ── PART B: Item 6 — Full 1.0.7 Readiness Table Walk at .xxxLarge on iPhone (390 pt) & iPad (834 pt) ──
        let feed = try decodeFile(FeedResponse.self, path: "\(liveWalkDir)/feed.json")
        let searchResp = try decodeFile(SearchResponse.self, path: "\(liveWalkDir)/search_patriots.json")
        let patriotsPage = try decodeFile(TeamPageResponse.self, path: "\(liveWalkDir)/team_patriots.json")
        let leagueNFL = try decodeFile(LeagueMarketsResponse.self, path: "\(liveWalkDir)/league_nfl.json")
        let facetedResp = try decodeFile(FacetedFuturesResponse.self, path: "\(liveWalkDir)/futures_faceted.json")
        let calibrationData = try decodeFile(CalibrationData.self, path: "\(liveWalkDir)/calibration.json")

        let discoverFuturesSample = feed.items.compactMap(\.futures).first { $0.discoverCard?.suggestedFormat == "binary_probability" }
            ?? feed.items.compactMap(\.futures).first!
        let discoverDistSample = feed.items.compactMap(\.futures).first { $0.discoverCard?.suggestedFormat == "outcome_distribution" }
            ?? discoverFuturesSample
        let discoverHeatSample = feed.items.compactMap(\.futures).first { $0.discoverCard?.suggestedFormat == "threshold_heatmap" }
            ?? discoverFuturesSample
        let discoverEvents = feed.items.compactMap(\.event)
        let roundupBundle = feed.items.compactMap(\.bundle).first { $0.roundupContract != nil }
        let plainGroupBundle = feed.items.compactMap(\.bundle).first { $0.roundupContract == nil }
        let liveOscarsSet: PairedMetricSet? = feed.items.compactMap(\.bundle).compactMap(\.pairedMetricSet).first

        let searchPlace = MacReadingPlace<SearchViewModel>()
        _ = searchPlace.models {
            let vm = SearchViewModel()
            vm.query = "Patriots"
            vm.results = searchResp
            return vm
        }

        let sportVM = SportCategoryViewModel(categoryKey: "americanfootball_nfl")
        sportVM.setItemsForTesting(discoverEvents.prefix(2).map { _ in feed.items.first(where: { $0.event != nil })! }, leagueMarkets: leagueNFL)
        let calVM = CalibrationViewModel(preloaded: calibrationData)

        let fixedNow = ISO8601DateFormatter().date(from: "2026-11-16T19:15:00Z")!
        let pacific = TimeZone(identifier: "America/Los_Angeles")!
        let widgetJSON = """
        {
          "id": 701001, "sport": "americanfootball_nfl", "sport_name": "NFL", "status": "live",
          "commence_time": "2026-11-16T18:00:00Z", "away_team": "New England Patriots", "home_team": "Detroit Lions",
          "away_score": 17, "home_score": 24, "espn": { "period": "Q3", "game_clock": "08:14" },
          "away_team_data": { "abbreviation": "NE", "primary_color": "#C60C30" },
          "home_team_data": { "abbreviation": "DET", "primary_color": "#0076B6" },
          "prematch_odds": { "away_probability": 0.42, "home_probability": 0.58 },
          "pregame_projection": {
            "projected_away_score": 21.0, "projected_home_score": 27.0,
            "kind": "last_before_scheduled_start", "boundary": "scheduled_start",
            "boundary_at": "2026-11-16T18:00:00Z", "earliest_captured_at": "2026-11-16T17:30:00Z",
            "latest_captured_at": "2026-11-16T17:58:00Z", "source": "sportsbooks",
            "basis": "consensus_spread_total", "bookmaker_count": 5, "unit": "points", "period": "full_game"
          },
          "current_odds": {
            "away_probability": 0.338, "home_probability": 0.662,
            "away_rendered_percent": 34, "home_rendered_percent": 66,
            "live_projection": {
              "projected_away_score": 23.0, "projected_home_score": 30.0,
              "kind": "in_play", "boundary": "commence_time", "boundary_at": "2026-11-16T18:00:00Z",
              "earliest_confirmed_at": "2026-11-16T19:10:00Z", "latest_captured_at": "2026-11-16T19:14:00Z",
              "source": "sportsbooks", "basis": "consensus_spread_total", "bookmaker_count": 5, "unit": "points", "period": "full_game"
            }
          },
          "hero_probability_observed_at": "2026-11-16T19:14:00Z"
        }
        """
        let widgetDetail = try SavedWidgetDetailDecoding10875.decoder().decode(SavedWidgetEventDetail10875.self, from: Data(widgetJSON.utf8))
        let widgetArt = SavedWidgetArt12466.game(widgetDetail)
        let widgetReading = SavedWidgetReadingRules10875.game(widgetDetail, side: nil, now: fixedNow)
        let widgetModel = SavedGameHeadlineWidgetModel12616.build(
            reading: widgetReading, art: widgetArt, clockFooter: "As of 11:14 AM",
            isOffline: false, clearsRefreshTrailing: false, now: fixedNow, timeZone: pacific
        )
        let watchBefore = WatchWristTileModel12616.build(
            WatchWristTileInput12616(
                homeTeam: "Detroit Lions", awayTeam: "New England Patriots",
                homeServedAbbreviation: "DET", awayServedAbbreviation: "NE",
                sportKey: "americanfootball_nfl", homeProbability: 0.58, awayProbability: 0.42,
                projectedHomeScore: 27.0, projectedAwayScore: 21.0,
                homePrimaryColor: "#0076B6", homeSecondaryColor: "#38BDF8",
                awayPrimaryColor: "#C60C30", awaySecondaryColor: "#F87171",
                commenceTime: fixedNow.addingTimeInterval(3600)
            ),
            now: fixedNow, timeZone: pacific
        )

        let headlineModel = EventSportHeadlines12472.resolve(
            event: chargersRavensEvent,
            awayFullName: chargersRavensEvent.awayTeam,
            homeFullName: chargersRavensEvent.homeTeam,
            liveStatusText: "Final",
            hasScore: true,
            numberStreams: false,
            now: fixedNow
        )
        let chargersRavensColors = TeamTextContrast.cardColors(
            awayHex: chargersRavensEvent.awayTeamData?.primaryColor,
            homeHex: chargersRavensEvent.homeTeamData?.primaryColor,
            awaySecondaryHex: chargersRavensEvent.awayTeamData?.secondaryColor,
            checkHueFamily: true
        )

        var ocrReport: [String: [String: Any]] = [:]

        for (deviceTag, width, sizeClass) in [
            ("iphone-390", CGFloat(390), UserInterfaceSizeClass.compact),
            ("ipad-834", CGFloat(834), UserInterfaceSizeClass.regular),
        ] {
            let namedBlocks: [(key: String, isCalibration: Bool, view: AnyView)] = [
                ("row1a_discover_cards", false, AnyView(
                    VStack(alignment: .leading, spacing: 12) {
                        Text("1.0.7 Walk (.xxxLarge) · \(deviceTag.uppercased()) · Row 1 Discover")
                            .font(.subheadline.weight(.bold))
                        NativeFuturesDiscoverCard(
                            data: discoverFuturesSample,
                            feedContext: nil,
                            expandedContext: nil,
                            navigationPath: .constant(NavigationPath())
                        )
                        DistributionCardView(data: discoverDistSample, navigationPath: .constant(NavigationPath()))
                        HeatMapCardView(data: discoverHeatSample, navigationPath: .constant(NavigationPath()))
                    }.padding(16)
                )),
                ("row1b_discover_groups", false, AnyView(
                    VStack(alignment: .leading, spacing: 12) {
                        if let pb = plainGroupBundle {
                            NativeGroupCard(
                                title: pb.title, items: pb.items, kind: pb.kind,
                                theme: pb.comparisonTheme, sharedQuestion: pb.sharedQuestion,
                                collectionRef: pb.collectionRef, navigationPath: .constant(NavigationPath())
                            )
                        }
                        if let rb = roundupBundle,
                           let model = DiscoverRoundupCardModel.build(title: rb.title, contract: rb.roundupContract, now: fixedNow) {
                            DiscoverRoundupCardView(model: model, collectionRef: rb.collectionRef, now: fixedNow)
                        }
                    }.padding(16)
                )),
                ("row2_sports_feed", false, AnyView(
                    VStack(alignment: .leading, spacing: 12) {
                        Text("Row 2 · Sports Feed Event Cards (.xxxLarge)")
                            .font(.caption.weight(.bold)).foregroundStyle(.secondary)
                        ForEach(Array(discoverEvents.prefix(3)), id: \.id) { ev in
                            EventCardView(event: ev, reason: nil)
                        }
                    }.padding(16)
                )),
                ("row3_4_game_and_charts", false, AnyView(
                    VStack(alignment: .leading, spacing: 12) {
                        Text("Row 3 & 4 · Game Page Headline & Connected Charts (.xxxLarge)")
                            .font(.caption.weight(.bold)).foregroundStyle(.secondary)
                        EventSportHeadlineCard12472(
                            model: headlineModel,
                            colors: chargersRavensColors,
                            ekgTracker: EkgTracker(),
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
                        chartPairBlock(
                            event: chargersRavensEvent,
                            history: chargersRavensHist,
                            label: "Chargers @ Ravens · Win Probability + Projected Final",
                            scheme: .light
                        )
                    }.padding(16)
                )),
                ("row5_team_page", false, AnyView(
                    VStack(alignment: .leading, spacing: 8) {
                        Text("Row 5 · Team Page — New England Patriots (.xxxLarge)")
                            .font(.caption.weight(.bold)).foregroundStyle(.secondary)
                        TeamDetailView(
                            slug: "new-england-patriots",
                            loadedPageForTest: patriotsPage,
                            raceForTest: nil
                        )
                        .frame(height: 1100)
                        .clipped()
                    }.padding(16)
                )),
                ("row6_search_and_browse", false, AnyView(
                    VStack(alignment: .leading, spacing: 12) {
                        Text("Row 6 · Search ('Patriots') & Browse Markets (.xxxLarge)")
                            .font(.caption.weight(.bold)).foregroundStyle(.secondary)
                        SearchView(macPlace: searchPlace)
                            .frame(height: 680)
                            .clipped()
                        ForEach(Array(facetedResp.markets.prefix(2)), id: \.id) { m in
                            FuturesBrowseMarketRow(market: m)
                        }
                        SportCategoryView(
                            categoryKey: "americanfootball_nfl",
                            categoryName: "NFL",
                            preloadedViewModel: sportVM
                        )
                        .frame(height: 520)
                        .clipped()
                    }.padding(16)
                )),
                ("row7_mystuff_and_calibration", true, AnyView(
                    VStack(alignment: .leading, spacing: 12) {
                        Text("Row 7 · My Stuff Pinned Futures & Calibration (.xxxLarge)")
                            .font(.caption.weight(.bold)).foregroundStyle(.secondary)
                        MyTeamFuturesCard(
                            futures: discoverFuturesSample,
                            matchedOutcomes: [MatchedOutcome(name: "New England Patriots", probability: 0.14, rank: 8, movement: 0.02)]
                        )
                        CalibrationSurfaceView(viewModel: calVM, scrolls: false)
                            .frame(maxHeight: 680)
                            .clipped()
                    }.padding(16)
                )),
                ("row8_9_about_widgets_watch", false, AnyView(
                    VStack(alignment: .leading, spacing: 12) {
                        Text("Row 8 · About & Picture Credits (.xxxLarge)")
                            .font(.caption.weight(.bold)).foregroundStyle(.secondary)
                        AboutView()
                            .frame(height: 860)
                            .clipped()

                        Text("Row 9 · Widgets & Watch Tile (.xxxLarge)")
                            .font(.caption.weight(.bold)).foregroundStyle(.secondary)
                        SavedGameHeadlineWidgetView12616(
                            model: widgetModel, size: .medium, awayLogo: nil, homeLogo: nil, fullColor: true
                        ) { EmptyView() }
                        .padding(14)
                        .frame(width: 338, height: 158)
                        .background(Color.white, in: RoundedRectangle(cornerRadius: 22))
                        .overlay(RoundedRectangle(cornerRadius: 22).stroke(Color.gray.opacity(0.25), lineWidth: 1))

                        WatchWristTileView12616(model: watchBefore) { EmptyView() }
                            .frame(width: 188)
                    }.padding(16)
                )),
            ]

            var renderedImgs: [UIImage] = []
            var deviceRowsReport: [String: Any] = [:]

            for item in namedBlocks {
                let img = renderBlock(item.view, width: width, maxHeight: 1920, dynamicType: .xxxLarge, sizeClass: sizeClass)
                renderedImgs.append(img)
                try XCTUnwrap(img.pngData()).write(to: outURL.appendingPathComponent("walk-\(deviceTag)-\(item.key).png"))
                let lines = try ocrLines(img)
                let ellipses = lines.filter { $0.contains("…") || $0.contains("...") }
                let hyphens = lines.filter { $0.hasSuffix("-") }
                let venues = item.isCalibration ? [] : lines.filter {
                    $0.localizedCaseInsensitiveContains("kalshi") || $0.localizedCaseInsensitiveContains("polymarket")
                }
                deviceRowsReport[item.key] = [
                    "line_count": lines.count,
                    "ellipses": ellipses,
                    "hyphens": hyphens,
                    "venue_hits": venues,
                    "sample_lines": Array(lines.prefix(25)),
                ]
            }

            let part1Stitched = stitchVertically(Array(renderedImgs.prefix(4)), width: width, spacing: 8)
            let part2Stitched = stitchVertically(Array(renderedImgs.suffix(4)), width: width, spacing: 8)
            try XCTUnwrap(part1Stitched.pngData()).write(to: outURL.appendingPathComponent("walk-\(deviceTag)-xxxlarge-part1.png"))
            try XCTUnwrap(part2Stitched.pngData()).write(to: outURL.appendingPathComponent("walk-\(deviceTag)-xxxlarge-part2.png"))
            ocrReport[deviceTag] = deviceRowsReport
        }

        let reportData = try JSONSerialization.data(withJSONObject: ocrReport, options: [.prettyPrinted, .sortedKeys])
        try reportData.write(to: outURL.appendingPathComponent("walk-ocr-report.json"))

        // ── PART C: Item 7 (1.0.8 #12642) — Look Sheet 2 Contact Sheet (390 px Light & Dark) ──
        if let oscarsSet = liveOscarsSet {
            var preloadedArt: [String: UIImage] = [:]
            let artCacheDir = URL(fileURLWithPath: "/tmp/builderc-12642-art-cache", isDirectory: true)
            for entry in oscarsSet.entries {
                if let urlStr = entry.art?.url {
                    let digest = SHA256.hash(data: Data(urlStr.utf8)).map { String(format: "%02x", $0) }.joined()
                    let ext = urlStr.hasSuffix(".png") ? ".png" : ".jpg"
                    let fileURL = artCacheDir.appendingPathComponent(String(digest.prefix(16)) + ext)
                    if let d = try? Data(contentsOf: fileURL), let img = UIImage(data: d) {
                        preloadedArt[urlStr] = img
                    }
                }
            }

            let nhlBundle = feed.items.compactMap(\.bundle).first { $0.title.localizedCaseInsensitiveContains("NHL") }
            let nhlRows: [FeedRoundupRow] = nhlBundle?.roundupContract?.rows ?? []
            let nhlEntries: [PairedSubjectEntry] = nhlRows.enumerated().map { idx, r in
                PairedSubjectEntry(
                    subjectKey: "nhl-\(idx)",
                    subject: r.label,
                    detail: idx < 3 ? "2026-27 NHL Playoffs" : "",
                    stage1MarketId: r.marketId ?? 0,
                    stage1Outcome: r.label,
                    stage1Probability: r.probability,
                    stage1SettledState: nil,
                    stage2MarketId: r.marketId ?? 0,
                    stage2Outcome: r.label,
                    stage2Probability: r.probability,
                    missingStage1Reason: nil,
                    missingStage2Reason: nil,
                    art: nil
                )
            }
            let nhlPodiumSet = PairedMetricSet(
                setId: "nhl-playoffs-2027-preview",
                category: "sports",
                kicker: nhlBundle?.roundupContract?.kicker ?? "NHL PLAYOFF RACE",
                title: nhlBundle?.title ?? "Which team will make the 2026-27 NHL Playoffs?",
                subtitle: nhlBundle?.roundupContract?.countLine ?? "Top contenders ordered by playoff chance",
                stage1Label: "Make Playoffs",
                stage2Label: "Make Playoffs",
                stage1SettledYesLabel: "Clinched",
                stage1SettledNoLabel: "Eliminated",
                entries: nhlEntries
            )

            for (schemeName, scheme) in [("light", ColorScheme.light), ("dark", ColorScheme.dark)] {
                let headerCol = scheme == .dark ? Color.white : Color.primary
                let subCol = scheme == .dark ? Color.white.opacity(0.7) : Color.secondary

                let lookB1 = renderBlock(
                    VStack(alignment: .leading, spacing: 10) {
                        Text("1.0.8 · #12642 Winning Grouped-Card Looks (Look Sheet 2 · \(schemeName.capitalized) 390 px)")
                            .font(.subheadline.weight(.bold)).foregroundStyle(headerCol)
                        Text("Look 1 · Top 5 Dual Bars + 'Show all N' Expander (Live Oscars 2027 — Collapsed)")
                            .font(.caption2.weight(.semibold)).foregroundStyle(subCol)
                        DiscoverPairedMetricCardView(
                            set: oscarsSet, form: .pairedBarsTop5Expandable,
                            initialExpanded: false, preloadedImages: preloadedArt
                        )
                    }.padding(16),
                    width: 390, maxHeight: 1400, dynamicType: .large, sizeClass: .compact, scheme: scheme
                )
                let lookB2 = renderBlock(
                    VStack(alignment: .leading, spacing: 10) {
                        Text("Look 1 · Top 5 Dual Bars + 'Show all N' Expander (Live Oscars 2027 — Expanded)")
                            .font(.caption2.weight(.semibold)).foregroundStyle(subCol)
                        DiscoverPairedMetricCardView(
                            set: oscarsSet, form: .pairedBarsTop5Expandable,
                            initialExpanded: true, preloadedImages: preloadedArt
                        )
                    }.padding(16),
                    width: 390, maxHeight: 1600, dynamicType: .large, sizeClass: .compact, scheme: scheme
                )
                let lookB3 = renderBlock(
                    VStack(alignment: .leading, spacing: 10) {
                        Text("Look 2 · 3-Spot Podium + Ballot Tiers (Live Oscars 2027 Best Picture)")
                            .font(.caption2.weight(.semibold)).foregroundStyle(subCol)
                        DiscoverPairedMetricCardView(
                            set: oscarsSet, form: .podiumAndTiers, preloadedImages: preloadedArt
                        )
                    }.padding(16),
                    width: 390, maxHeight: 1400, dynamicType: .large, sizeClass: .compact, scheme: scheme
                )
                var blocks = [lookB1, lookB2, lookB3]
                if !nhlEntries.isEmpty {
                    let lookB4 = renderBlock(
                        VStack(alignment: .leading, spacing: 10) {
                            Text("Look 2 · 3-Spot Podium + Ballot Tiers (Live NHL Playoffs Grouped Bundle)")
                                .font(.caption2.weight(.semibold)).foregroundStyle(subCol)
                            DiscoverPairedMetricCardView(
                                set: nhlPodiumSet, form: .podiumAndTiers, preloadedImages: preloadedArt
                            )
                        }.padding(16),
                        width: 390, maxHeight: 1400, dynamicType: .large, sizeClass: .compact, scheme: scheme
                    )
                    blocks.append(lookB4)
                }

                let lookStitched = stitchVertically(blocks, width: 390, spacing: 4, scheme: scheme)
                try XCTUnwrap(lookStitched.pngData()).write(to: outURL.appendingPathComponent("12642-look-sheet-2-\(schemeName)-390.png"))
            }
        }

        // ── PART D: Finished-Game Winner Tick Alignment (Alex 9:54 AM PT) + #12873 SourceMarkSheet (390 px) ──
        let finishedFeedEvent = discoverEvents.first { $0.status == "completed" || $0.status == "closed" }
            ?? discoverEvents.first!
        let finishedColors = TeamTextContrast.cardColors(
            awayHex: finishedFeedEvent.awayTeamData?.primaryColor,
            homeHex: finishedFeedEvent.homeTeamData?.primaryColor,
            awaySecondaryHex: finishedFeedEvent.awayTeamData?.secondaryColor,
            checkHueFamily: true
        )
        let soccerDrawJSON = """
        {
          "id": 991201, "sport": "soccer_epl", "sport_name": "Premier League", "status": "completed",
          "commence_time": "2026-11-15T15:00:00Z", "away_team": "Arsenal", "home_team": "Chelsea",
          "away_score": 1, "home_score": 1, "final_score_period": "regulation",
          "away_team_data": { "abbreviation": "ARS", "primary_color": "#EF0107" },
          "home_team_data": { "abbreviation": "CHE", "primary_color": "#034694" },
          "prematch_odds": { "away_probability": 0.39, "home_probability": 0.34, "draw_probability": 0.27 }
        }
        """
        let soccerDrawDecoder = JSONDecoder()
        soccerDrawDecoder.keyDecodingStrategy = .convertFromSnakeCase
        let soccerDrawEvent = try soccerDrawDecoder.decode(FeedEventData.self, from: Data(soccerDrawJSON.utf8))

        let widgetFinishedJSON = """
        {
          "id": 701002, "sport": "americanfootball_nfl", "sport_name": "NFL", "status": "completed",
          "commence_time": "2026-11-16T01:15:00Z", "away_team": "Los Angeles Chargers", "home_team": "Baltimore Ravens",
          "away_score": 23, "home_score": 30,
          "away_team_data": { "abbreviation": "LAC", "primary_color": "#0080C6" },
          "home_team_data": { "abbreviation": "BAL", "primary_color": "#241773" },
          "prematch_odds": { "away_probability": 0.42, "home_probability": 0.58 }
        }
        """
        let widgetFinishedDetail = try SavedWidgetDetailDecoding10875.decoder().decode(
            SavedWidgetEventDetail10875.self, from: Data(widgetFinishedJSON.utf8)
        )
        let widgetFinishedArt = SavedWidgetArt12466.game(widgetFinishedDetail)
        let widgetFinishedReading = SavedWidgetReadingRules10875.game(widgetFinishedDetail, side: nil, now: fixedNow)
        let widgetFinishedModel = SavedGameHeadlineWidgetModel12616.build(
            reading: widgetFinishedReading, art: widgetFinishedArt, clockFooter: "",
            isOffline: false, clearsRefreshTrailing: false, now: fixedNow, timeZone: pacific
        )

        let scaledSingleMark = SourceMark(
            state: .single,
            sources: [.init(key: "betting", name: "Sportsbooks", probability: 0.16, observedAt: "2026-11-16T19:12:00Z", count: 6)],
            method: "Scaled across 32 outcomes so the field totals 100%"
        )
        let unscaledSportsbooksMark = SourceMark(
            state: .single,
            sources: [.init(key: "betting", name: "Sportsbooks", probability: 0.195, observedAt: nil, count: 5)],
            method: nil
        )

        let tickBlock1 = renderBlock(
            VStack(alignment: .leading, spacing: 12) {
                Text("#12874 · Finished-Game Winner Tick After Name (Scores Share Right Edge · 390 px)")
                    .font(.subheadline.weight(.bold))
                    .fixedSize(horizontal: false, vertical: true)
                Text("1 · Discover Finished Game Card")
                    .font(.caption2.weight(.semibold)).foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
                DiscoverCompactSingleGameCard190CView(
                    event: finishedFeedEvent,
                    prematch: PrematchReading.resolve(prematch: finishedFeedEvent.prematchOdds, opening: finishedFeedEvent.openingOdds),
                    awayColor: finishedColors.away,
                    homeColor: finishedColors.home,
                    projectionAndSuspendedLines: { EmptyView() },
                    footerRow: { EmptyView() }
                )
                .background(Color.cardBackground, in: RoundedRectangle(cornerRadius: 14))
                .overlay(RoundedRectangle(cornerRadius: 14).stroke(Color.gray.opacity(0.2), lineWidth: 1))

                Text("2 · Sports / Search / Team-Page Finished Cards (Winner + 3-Way Draw)")
                    .font(.caption2.weight(.semibold)).foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
                EventCardView(event: finishedFeedEvent, reason: nil)
                    .padding(12)
                    .background(Color.cardBackground, in: RoundedRectangle(cornerRadius: 14))
                    .overlay(RoundedRectangle(cornerRadius: 14).stroke(Color.gray.opacity(0.2), lineWidth: 1))
                EventCardView(event: soccerDrawEvent, reason: nil)
                    .padding(12)
                    .background(Color.cardBackground, in: RoundedRectangle(cornerRadius: 14))
                    .overlay(RoundedRectangle(cornerRadius: 14).stroke(Color.gray.opacity(0.2), lineWidth: 1))
            }.padding(16),
            width: 390, maxHeight: 1600, dynamicType: .large, sizeClass: .compact
        )

        let tickBlock2 = renderBlock(
            VStack(alignment: .leading, spacing: 12) {
                Text("3 · Game-Page Finished Headline")
                    .font(.caption2.weight(.semibold)).foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
                EventSportHeadlineCard12472(
                    model: headlineModel,
                    colors: chargersRavensColors,
                    ekgTracker: EkgTracker(),
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

                Text("4 · Finished Home-Screen Widgets (Small 158×158 & Medium 338×158)")
                    .font(.caption2.weight(.semibold)).foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
                HStack(alignment: .top, spacing: 12) {
                    SavedGameHeadlineWidgetView12616(
                        model: widgetFinishedModel, size: .small, awayLogo: nil, homeLogo: nil, fullColor: true
                    ) { EmptyView() }
                    .padding(12)
                    .frame(width: 158, height: 158)
                    .background(Color.white, in: RoundedRectangle(cornerRadius: 22))
                    .overlay(RoundedRectangle(cornerRadius: 22).stroke(Color.gray.opacity(0.25), lineWidth: 1))
                }
                SavedGameHeadlineWidgetView12616(
                    model: widgetFinishedModel, size: .medium, awayLogo: nil, homeLogo: nil, fullColor: true
                ) { EmptyView() }
                .padding(14)
                .frame(width: 338, height: 158)
                .background(Color.white, in: RoundedRectangle(cornerRadius: 22))
                .overlay(RoundedRectangle(cornerRadius: 22).stroke(Color.gray.opacity(0.25), lineWidth: 1))

                Text("5 · #12873 SourceMarkSheet — Single-Source Scaling Sentence & 'Sportsbooks\\' price'")
                    .font(.caption2.weight(.semibold)).foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
                SourceMarkSheet(mark: scaledSingleMark, number: 0.14)
                    .frame(height: 250)
                    .clipShape(RoundedRectangle(cornerRadius: 14))
                    .overlay(RoundedRectangle(cornerRadius: 14).stroke(Color.gray.opacity(0.2), lineWidth: 1))
                SourceMarkSheet(mark: unscaledSportsbooksMark, number: 0.20)
                    .frame(height: 245)
                    .clipShape(RoundedRectangle(cornerRadius: 14))
                    .overlay(RoundedRectangle(cornerRadius: 14).stroke(Color.gray.opacity(0.2), lineWidth: 1))
            }.padding(16),
            width: 390, maxHeight: 1850, dynamicType: .large, sizeClass: .compact
        )

        let tickSheet = stitchVertically([tickBlock1, tickBlock2], width: 390, spacing: 4)
        try XCTUnwrap(tickSheet.pngData()).write(to: outURL.appendingPathComponent("12874-finished-winner-tick-alignment-390.png"))
    }
}
