import SwiftUI
import UIKit
import Vision
import XCTest
@testable import Bain_Luck

/// Ruling 240: A (#12992) — Native parity tests and 390 pt render harness:
///   1. Rule 1: A level rounded projected final prints in every sport (`111` and `111`),
///      removing `#8156`'s tie refusal across cards, event-page headlines, `EventDetailView`,
///      Widgets (`SavedWidgetArt12466`), and Apple Watch (`WatchWristTileModel12616`).
///   2. Rule 2: Never two winners on one card — when the rounded pair has one team ahead
///      and the surface's chance favours the other team, the projected pair is withheld so
///      the card/headline shows the chance only (collapsing the `Proj.` column header to empty).
@MainActor
final class ProjectedFinalPair240ATests: XCTestCase {

    private let fixedNow = ISO8601DateFormatter().date(from: "2026-11-19T01:20:00Z")!

    private func decodeSnake<T: Decodable>(_ type: T.Type, _ json: String) throws -> T {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(T.self, from: Data(json.utf8))
    }

    // MARK: - Tonight's served specimens (Nov 18, 2026)

    /// Alex's reported specimen (#12992): `15350555` Philadelphia 76ers @ Orlando Magic
    /// (`projected_away_score: 111.1`, `projected_home_score: 110.6` -> `111–111` beside `49% / 51%`).
    private static let sixersAtMagicJSON = """
    {
      "id": 15350555,
      "sport": "basketball_nba",
      "sport_name": "NBA",
      "home_team": "Orlando Magic",
      "away_team": "Philadelphia 76ers",
      "commence_time": "2026-11-20T00:00:00Z",
      "start_is_tbd": false,
      "status": "scheduled",
      "home_team_data": {
        "team_id": 19,
        "slug": "orlando-magic-nba",
        "primary_color": "#0077c0",
        "secondary_color": "#c4ced4",
        "record": "8-6",
        "abbreviation": "ORL"
      },
      "away_team_data": {
        "team_id": 20,
        "slug": "philadelphia-76ers-nba",
        "primary_color": "#006bb6",
        "secondary_color": "#ed174c",
        "record": "7-6",
        "abbreviation": "PHI"
      },
      "espn": { "broadcast": "NBA League Pass" },
      "current_odds": {
        "captured_at": "2026-11-18T22:01:00Z",
        "home_probability": 0.505,
        "away_probability": 0.495,
        "away_rendered_percent": 49,
        "home_rendered_percent": 51,
        "spread": 0.5,
        "over_under": 221.7,
        "projected_home_score": 110.6,
        "projected_away_score": 111.1,
        "bookmaker_count": 12
      },
      "hero_probability": 0.505,
      "hero_probability_away": 0.495,
      "hero_probability_source": "blend",
      "source_mark": {
        "state": "blend",
        "sources": [
          { "key": "kalshi", "name": "Kalshi", "probability": 0.505 },
          { "key": "polymarket", "name": "Polymarket", "probability": 0.505 },
          { "key": "betting", "name": "Sportsbooks", "probability": 0.4892, "count": 12 }
        ],
        "method": "Bain Luck blend · the weighted middle of these sources"
      }
    }
    """

    /// Tonight's live active scheduled toss-up (#12992 census): `15175997` LSU Tigers @ Tennessee Volunteers
    /// (`projected_away_score: 23.4`, `projected_home_score: 22.5` -> `23–23` beside `51% / 49%`).
    private static let lsuAtTennesseeJSON = """
    {
      "id": 15175997,
      "sport": "americanfootball_ncaaf",
      "sport_name": "NCAAF",
      "home_team": "Tennessee Volunteers",
      "away_team": "LSU Tigers",
      "commence_time": "2026-11-21T20:30:00Z",
      "start_is_tbd": false,
      "status": "scheduled",
      "home_team_data": {
        "team_id": 15937,
        "slug": "tennessee-volunteers-ncaaf",
        "primary_color": "#ff8200",
        "secondary_color": "#ffffff",
        "record": "8-2",
        "abbreviation": "TENN"
      },
      "away_team_data": {
        "team_id": 9,
        "slug": "lsu-tigers-ncaaf",
        "primary_color": "#461d76",
        "secondary_color": "#fdd023",
        "record": "6-4",
        "abbreviation": "LSU"
      },
      "espn": { "broadcast": "ABC" },
      "current_odds": {
        "captured_at": "2026-11-19T01:14:52Z",
        "home_probability": 0.4929,
        "away_probability": 0.5071,
        "away_rendered_percent": 51,
        "home_rendered_percent": 49,
        "spread": 0.9,
        "over_under": 45.9,
        "projected_home_score": 22.5,
        "projected_away_score": 23.4,
        "bookmaker_count": 10
      },
      "hero_probability": 0.4929,
      "hero_probability_away": 0.5071,
      "hero_probability_source": "blend",
      "away_source_mark": {
        "state": "blend",
        "sources": [
          { "key": "polymarket", "name": "Polymarket", "probability": 0.495 },
          { "key": "betting", "name": "Sportsbooks", "probability": 0.5071, "count": 10 }
        ],
        "method": "Bain Luck blend · the weighted middle of these sources"
      }
    }
    """

    /// Tonight's single active scheduled game hidden by Rule 2 (#12992 census, 1 of 150 drawable rows):
    /// `15349440` South Florida Bulls @ Florida Atlantic Owls (`projected_away_score: 32.5`,
    /// `projected_home_score: 31.9` -> South Florida `33–32`, while blended `Chance` favours
    /// Florida Atlantic `51%–49%`).
    private static let usfAtFauRule2JSON = """
    {
      "id": 15349440,
      "sport": "americanfootball_ncaaf",
      "sport_name": "NCAAF",
      "home_team": "Florida Atlantic Owls",
      "away_team": "South Florida Bulls",
      "commence_time": "2026-11-21T19:30:00Z",
      "start_is_tbd": false,
      "status": "scheduled",
      "home_team_data": {
        "team_id": 15300,
        "slug": "florida-atlantic-owls-ncaaf",
        "primary_color": "#003366",
        "secondary_color": "#cc0000",
        "record": "6-4",
        "abbreviation": "FAU"
      },
      "away_team_data": {
        "team_id": 15294,
        "slug": "south-florida-bulls-ncaaf",
        "primary_color": "#006747",
        "secondary_color": "#cfc493",
        "record": "6-4",
        "abbreviation": "USF"
      },
      "espn": { "broadcast": "ESPN+" },
      "current_odds": {
        "captured_at": "2026-11-19T01:14:51Z",
        "home_probability": 0.505,
        "away_probability": 0.495,
        "away_rendered_percent": 49,
        "home_rendered_percent": 51,
        "spread": 0.6,
        "over_under": 64.3,
        "projected_home_score": 31.9,
        "projected_away_score": 32.5,
        "bookmaker_count": 8
      },
      "hero_probability": 0.505,
      "hero_probability_away": 0.495,
      "hero_probability_source": "blend",
      "source_mark": {
        "state": "blend",
        "sources": [
          { "key": "kalshi", "name": "Kalshi", "probability": 0.505 },
          { "key": "polymarket", "name": "Polymarket", "probability": 0.505 },
          { "key": "betting", "name": "Sportsbooks", "probability": 0.4936, "count": 8 }
        ],
        "method": "Bain Luck blend · the weighted middle of these sources"
      }
    }
    """

    // MARK: - Pure Rule 1 & Rule 2 Guard Tests

    func testGuardNeverConflictsOnLevelPairsOrExactFiftyPercent() {
        // Level pair never conflicts even when chance strongly favours one side.
        XCTAssertFalse(
            ProjectedFinalChanceGuard240A.conflicts(
                projectedHome: 111,
                projectedAway: 111,
                homeChance: 0.505,
                awayChance: 0.495,
                sportKey: "basketball_nba"
            )
        )
        // Exact 50% chance never conflicts even when projected pair favours a side.
        XCTAssertFalse(
            ProjectedFinalChanceGuard240A.conflicts(
                projectedHome: 32,
                projectedAway: 33,
                homeChance: 0.5,
                awayChance: 0.5,
                sportKey: "americanfootball_ncaaf"
            )
        )
        XCTAssertFalse(
            ProjectedFinalChanceGuard240A.conflicts(
                projectedHome: 32,
                projectedAway: 33,
                homeChance: 0.5,
                awayChance: nil,
                sportKey: "americanfootball_ncaaf"
            )
        )
        // Opposite winners conflict.
        XCTAssertTrue(
            ProjectedFinalChanceGuard240A.conflicts(
                projectedHome: 32,
                projectedAway: 33,
                homeChance: 0.505,
                awayChance: 0.495,
                sportKey: "americanfootball_ncaaf"
            )
        )
        // Same winner agrees.
        XCTAssertFalse(
            ProjectedFinalChanceGuard240A.conflicts(
                projectedHome: 33,
                projectedAway: 32,
                homeChance: 0.505,
                awayChance: 0.495,
                sportKey: "americanfootball_ncaaf"
            )
        )
        // Three-way soccer: equal club win shares (e.g. 36% home, 28% draw, 36% away) do not conflict.
        XCTAssertFalse(
            ProjectedFinalChanceGuard240A.conflicts(
                projectedHome: 1.8,
                projectedAway: 1.2,
                homeChance: 0.36,
                awayChance: 0.36,
                sportKey: "soccer_epl"
            )
        )
        // Three-way soccer: away ahead in goals (1.8 vs 1.2) while home leads win share (45% vs 28%) conflicts.
        XCTAssertTrue(
            ProjectedFinalChanceGuard240A.conflicts(
                projectedHome: 1.2,
                projectedAway: 1.8,
                homeChance: 0.45,
                awayChance: 0.28,
                sportKey: "soccer_epl"
            )
        )
    }

    // MARK: - Cards, Headlines, Detail, Widget & Watch Parity

    func testTossUpPrintsLevelPairAcrossAllSurfaces() throws {
        let feedSixers: FeedEventData = try decodeSnake(FeedEventData.self, Self.sixersAtMagicJSON)
        let detailSixers: EventDetail = try decodeSnake(EventDetail.self, Self.sixersAtMagicJSON)
        let widgetSixers: SavedWidgetEventDetail10875 = try decodeSnake(SavedWidgetEventDetail10875.self, Self.sixersAtMagicJSON)

        // 1. Sports / Search / Hub compact card
        XCTAssertEqual(
            ScheduledCardProjectedFinal12616.card(feedSixers),
            .init(away: 111, home: 111),
            "76ers @ Magic toss-up must print 111 and 111 on scheduled cards"
        )

        // 2. Discover single-game card
        let discoverModel = DiscoverSingleGameCard190C.build(event: feedSixers, prematch: nil)
        XCTAssertEqual(discoverModel.headers.pregame, "Proj.")
        XCTAssertEqual(discoverModel.rows.first(where: { $0.kind == .away })?.pregameText, "111")
        XCTAssertEqual(discoverModel.rows.first(where: { $0.kind == .home })?.pregameText, "111")

        // 3. Event-page unified headline
        let headline = EventSportHeadlines12472.resolve(
            event: detailSixers,
            awayFullName: detailSixers.awayTeam,
            homeFullName: detailSixers.homeTeam,
            liveStatusText: nil,
            hasScore: false,
            numberStreams: false,
            now: fixedNow
        )
        XCTAssertEqual(headline.columns.map(\.header), ["Proj.", "Chance"])
        XCTAssertEqual(headline.away.pregameProjectedNumberText, "111")
        XCTAssertEqual(headline.home.pregameProjectedNumberText, "111")
        XCTAssertEqual(headline.away.winChanceText, "49%")
        XCTAssertEqual(headline.home.winChanceText, "51%")

        // 4. EventDetailView projectionText
        XCTAssertEqual(
            EventDetailView.projectionText(detailSixers, ladderHome: nil, ladderAway: nil, hasScore: false, now: fixedNow),
            "Proj. 111-111"
        )

        // 5. Saved-game Home Screen Widget
        let widgetArt = SavedWidgetArt12466.game(widgetSixers)
        XCTAssertEqual(widgetArt.projectedBefore, .init(away: 111, home: 111))

        // 6. Apple Watch wrist tile
        let watchModel = WatchWristTileModel12616.build(
            WatchWristTileInput12616(
                homeTeam: detailSixers.homeTeam,
                awayTeam: detailSixers.awayTeam,
                sportKey: detailSixers.sport,
                homeProbability: 0.505,
                awayProbability: 0.495,
                projectedHomeScore: 110.6,
                projectedAwayScore: 111.1,
                commenceTime: fixedNow.addingTimeInterval(7200)
            ),
            now: fixedNow
        )
        XCTAssertEqual(watchModel.supportingLine, "Favored · Proj. 111\u{2013}111")
    }

    func testRule2WithholdsConflictingPairAcrossAllSurfaces() throws {
        let feedUSF: FeedEventData = try decodeSnake(FeedEventData.self, Self.usfAtFauRule2JSON)
        let detailUSF: EventDetail = try decodeSnake(EventDetail.self, Self.usfAtFauRule2JSON)
        let widgetUSF: SavedWidgetEventDetail10875 = try decodeSnake(SavedWidgetEventDetail10875.self, Self.usfAtFauRule2JSON)

        // 1. Sports / Search / Hub compact card withholds 33–32 against 49%–51%
        XCTAssertNil(
            ScheduledCardProjectedFinal12616.card(feedUSF),
            "USF 33–32 must be withheld when FAU leads Chance 51%–49%"
        )

        // 2. Discover single-game card shows Chance only (no Proj. header)
        let discoverModel = DiscoverSingleGameCard190C.build(event: feedUSF, prematch: nil)
        XCTAssertNil(discoverModel.headers.pregame)
        XCTAssertEqual(discoverModel.headers.primary, "Chance")
        XCTAssertNil(discoverModel.rows.first(where: { $0.kind == .away })?.pregameText)
        XCTAssertNil(discoverModel.rows.first(where: { $0.kind == .home })?.pregameText)
        XCTAssertEqual(discoverModel.rows.first(where: { $0.kind == .away })?.primaryCell, .probability("49%"))
        XCTAssertEqual(discoverModel.rows.first(where: { $0.kind == .home })?.primaryCell, .probability("51%"))

        // 3. Event-page unified headline blanks Proj. header and collapses column width to 0
        let headline = EventSportHeadlines12472.resolve(
            event: detailUSF,
            awayFullName: detailUSF.awayTeam,
            homeFullName: detailUSF.homeTeam,
            liveStatusText: nil,
            hasScore: false,
            numberStreams: false,
            now: fixedNow
        )
        XCTAssertEqual(headline.columns.map(\.header), ["", "Chance"])
        XCTAssertNil(headline.away.pregameProjectedNumberText)
        XCTAssertNil(headline.home.pregameProjectedNumberText)
        let layout = HeadlineCellFit12822.resolve(
            model: headline,
            innerWidth: 330,
            crestSize: 28,
            isAccessibilitySize: false,
            nameFontSize: 18,
            nowFontSize: 20,
            secondProminentFontSize: 20,
            secondRegularFontSize: 16,
            headerFontSize: 12
        )
        XCTAssertEqual(layout.columnWidths.first, 0, "Withheld Proj. column must take 0 pt width")

        // 4. EventDetailView projectionText withholds
        XCTAssertNil(
            EventDetailView.projectionText(detailUSF, ladderHome: nil, ladderAway: nil, hasScore: false, now: fixedNow)
        )

        // 5. Saved-game Home Screen Widget withholds
        let widgetArt = SavedWidgetArt12466.game(widgetUSF)
        XCTAssertNil(widgetArt.projectedBefore)

        // 6. Apple Watch wrist tile shows Favored only without conflicting Proj.
        let watchModel = WatchWristTileModel12616.build(
            WatchWristTileInput12616(
                homeTeam: detailUSF.homeTeam,
                awayTeam: detailUSF.awayTeam,
                sportKey: detailUSF.sport,
                homeProbability: 0.505,
                awayProbability: 0.495,
                projectedHomeScore: 31.9,
                projectedAwayScore: 32.5,
                commenceTime: fixedNow.addingTimeInterval(7200)
            ),
            now: fixedNow
        )
        XCTAssertEqual(watchModel.supportingLine, "Favored")
    }

    func testLiveAdmissionWithholdsConflictingLivePairFurmanAtRadford() throws {
        // Tonight's live specimen `15350596` Furman @ Radford:
        // live_projection 80.4 away / 79.0 home -> 80–79 Furman while live Now favours Radford 51.1%–48.9%.
        let liveJSON = """
        {
          "projected_home_score": 79.0,
          "projected_away_score": 80.4,
          "kind": "in_play",
          "boundary": "commence_time",
          "boundary_at": "2026-11-19T00:00:00Z",
          "earliest_confirmed_at": "2026-11-19T01:15:00Z",
          "latest_captured_at": "2026-11-19T01:15:00Z",
          "source": "sportsbooks",
          "basis": "consensus_spread_total",
          "bookmaker_count": 7,
          "unit": "points",
          "period": "full_game"
        }
        """
        let lp: LiveProjection = try decodeSnake(LiveProjection.self, liveJSON)
        let outcome = LiveProjectedFinalAdmission2920.resolve(
            projection: lp,
            sport: "basketball_ncaab",
            status: "live",
            rowStart: .init(commenceTime: "2026-11-19T00:00:00Z"),
            homeScore: 68,
            awayScore: 65,
            phase: nil,
            now: fixedNow,
            homeChance: 0.51136,
            awayChance: 0.48864
        )
        XCTAssertEqual(outcome, .withheld(.conflictsWithChance))
    }

    // MARK: - 390 pt Default & Larger-Text Looks (Env-Gated)

    private func captureSheet<V: View>(
        _ view: V,
        width: CGFloat = 390,
        scheme: ColorScheme,
        at size: DynamicTypeSize
    ) -> UIImage {
        let bg = scheme == .dark ? Color.black : Color(UIColor.systemGroupedBackground)
        let root = view
            .frame(width: width, alignment: .topLeading)
            .padding(.vertical, 14)
            .background(bg)
            .environment(\.colorScheme, scheme)
            .environmentObject(NavigationCoordinator())
            .environmentObject(PinManager())

        let host = hostForMeasurement(root, at: size)
        host.overrideUserInterfaceStyle = scheme == .dark ? .dark : .light
        let fitting = host.sizeThatFits(in: CGSize(width: width, height: 2400))
        let height = max(ceil(fitting.height) + 22, 260)
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

    func testRender12992TossUpAndRule2HiddenLooks() throws {
        guard let outDir = ProcessInfo.processInfo.environment["RENDER_12992_DIR"],
              !outDir.isEmpty else {
            return
        }
        try FileManager.default.createDirectory(atPath: outDir, withIntermediateDirectories: true)

        let feedSixers: FeedEventData = try decodeSnake(FeedEventData.self, Self.sixersAtMagicJSON)
        let detailSixers: EventDetail = try decodeSnake(EventDetail.self, Self.sixersAtMagicJSON)
        let feedLSU: FeedEventData = try decodeSnake(FeedEventData.self, Self.lsuAtTennesseeJSON)
        let feedUSF: FeedEventData = try decodeSnake(FeedEventData.self, Self.usfAtFauRule2JSON)
        let detailUSF: EventDetail = try decodeSnake(EventDetail.self, Self.usfAtFauRule2JSON)

        let sixersHeadline = EventSportHeadlines12472.resolve(
            event: detailSixers,
            awayFullName: detailSixers.awayTeam,
            homeFullName: detailSixers.homeTeam,
            liveStatusText: nil,
            hasScore: false,
            numberStreams: false,
            now: fixedNow
        )
        let usfHeadline = EventSportHeadlines12472.resolve(
            event: detailUSF,
            awayFullName: detailUSF.awayTeam,
            homeFullName: detailUSF.homeTeam,
            liveStatusText: nil,
            hasScore: false,
            numberStreams: false,
            now: fixedNow
        )

        @ViewBuilder
        func tossUpView(scheme: ColorScheme) -> some View {
            VStack(alignment: .leading, spacing: 14) {
                Text("240: A · Toss-up level projected final (iPhone 390 pt)")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
                    .padding(.horizontal, 16)

                EventCardView(event: feedSixers, reason: nil)
                    .padding(.horizontal, 16)
                    .background(
                        RoundedRectangle(cornerRadius: 14, style: .continuous)
                            .fill(Color(UIColor.secondarySystemGroupedBackground))
                    )
                    .padding(.horizontal, 16)

                EventCardView(event: feedLSU, reason: nil)
                    .padding(.horizontal, 16)
                    .background(
                        RoundedRectangle(cornerRadius: 14, style: .continuous)
                            .fill(Color(UIColor.secondarySystemGroupedBackground))
                    )
                    .padding(.horizontal, 16)

                let sixersColors: (away: Color, home: Color) = {
                    let hexes = scheme == .dark
                        ? TeamTextContrast.darkSurfaceColorHexes(
                            awayHex: detailSixers.awayTeamData?.primaryColor,
                            homeHex: detailSixers.homeTeamData?.primaryColor,
                            awaySecondaryHex: detailSixers.awayTeamData?.secondaryColor,
                            homeSecondaryHex: detailSixers.homeTeamData?.secondaryColor
                          )
                        : TeamTextContrast.cardColorHexes(
                            awayHex: detailSixers.awayTeamData?.primaryColor,
                            homeHex: detailSixers.homeTeamData?.primaryColor,
                            awaySecondaryHex: detailSixers.awayTeamData?.secondaryColor
                          )
                    return (Color(hex: hexes.away), Color(hex: hexes.home))
                }()

                EventSportHeadlineCard12472(
                    model: sixersHeadline,
                    colors: sixersColors,
                    ekgTracker: EkgTracker(eventId: detailSixers.id),
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

        @ViewBuilder
        func rule2HiddenView(scheme: ColorScheme) -> some View {
            VStack(alignment: .leading, spacing: 14) {
                Text("240: A · Rule 2 hides conflicting pair (iPhone 390 pt)")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
                    .padding(.horizontal, 16)

                EventCardView(event: feedUSF, reason: nil)
                    .padding(.horizontal, 16)
                    .background(
                        RoundedRectangle(cornerRadius: 14, style: .continuous)
                            .fill(Color(UIColor.secondarySystemGroupedBackground))
                    )
                    .padding(.horizontal, 16)

                let usfColors: (away: Color, home: Color) = {
                    let hexes = scheme == .dark
                        ? TeamTextContrast.darkSurfaceColorHexes(
                            awayHex: detailUSF.awayTeamData?.primaryColor,
                            homeHex: detailUSF.homeTeamData?.primaryColor,
                            awaySecondaryHex: detailUSF.awayTeamData?.secondaryColor,
                            homeSecondaryHex: detailUSF.homeTeamData?.secondaryColor
                          )
                        : TeamTextContrast.cardColorHexes(
                            awayHex: detailUSF.awayTeamData?.primaryColor,
                            homeHex: detailUSF.homeTeamData?.primaryColor,
                            awaySecondaryHex: detailUSF.awayTeamData?.secondaryColor
                          )
                    return (Color(hex: hexes.away), Color(hex: hexes.home))
                }()

                EventSportHeadlineCard12472(
                    model: usfHeadline,
                    colors: usfColors,
                    ekgTracker: EkgTracker(eventId: detailUSF.id),
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

        for (tag, dt) in [("default", DynamicTypeSize.large), ("larger-text", DynamicTypeSize.xxxLarge)] {
            let tossLight = captureSheet(tossUpView(scheme: .light), scheme: .light, at: dt)
            let tossDark = captureSheet(tossUpView(scheme: .dark), scheme: .dark, at: dt)
            let tossSheet = sideBySide(tossLight, tossDark)
            let tossURL = URL(fileURLWithPath: outDir).appendingPathComponent("12992-iphone-tossup-\(tag)-390.png")
            try XCTUnwrap(tossSheet.pngData()).write(to: tossURL)

            let tossOCR = try ocrStrings(tossLight).joined(separator: " ")
            XCTAssertTrue(tossOCR.contains("111"), "Toss-up \(tag) render must draw 111: \(tossOCR)")

            let rule2Light = captureSheet(rule2HiddenView(scheme: .light), scheme: .light, at: dt)
            let rule2Dark = captureSheet(rule2HiddenView(scheme: .dark), scheme: .dark, at: dt)
            let rule2Sheet = sideBySide(rule2Light, rule2Dark)
            let rule2URL = URL(fileURLWithPath: outDir).appendingPathComponent("12992-iphone-rule2-hidden-\(tag)-390.png")
            try XCTUnwrap(rule2Sheet.pngData()).write(to: rule2URL)

            let rule2OCR = try ocrStrings(rule2Light).joined(separator: " ")
            XCTAssertFalse(rule2OCR.contains("Proj."), "Rule-2 \(tag) render must withhold Proj. header: \(rule2OCR)")
            XCTAssertTrue(rule2OCR.contains("49%") && rule2OCR.contains("51%"), "Rule-2 \(tag) render must show Chance 49%/51%: \(rule2OCR)")
        }
    }
}
