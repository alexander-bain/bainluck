import SwiftUI
import UIKit
import XCTest
@testable import Bain_Luck

/// Item 6 — One Type Table Everywhere (`HeadlineStyleTable199`):
/// Brings the Discover card (`DiscoverCompactSingleGameCard190C`), the feed card
/// (`EventCardView`), the Home Screen widgets (`SavedGameHeadlineWidget12616` &
/// `SavedWidgetLooks12466`), and the Apple Watch wrist tile (`WatchWristTile12616`)
/// onto `HeadlineStyleTable199` alongside `EventSportHeadlineCard12472`, so a team
/// name, a score, and a chance share one size and weight family across every surface.
@MainActor
final class OneTypeTableEverywhere199Tests: XCTestCase {

    private let pacific = TimeZone(identifier: "America/Los_Angeles")!
    private let fixedNow = ISO8601DateFormatter().date(from: "2026-11-16T19:15:00Z")!

    private func decodeJSON<T: Decodable>(_ type: T.Type, _ json: String) throws -> T {
        let dec = JSONDecoder()
        dec.keyDecodingStrategy = .convertFromSnakeCase
        return try dec.decode(T.self, from: Data(json.utf8))
    }

    private func decodeWidgetEvent(_ json: String) throws -> SavedWidgetEventDetail10875 {
        try SavedWidgetDetailDecoding10875.decoder().decode(
            SavedWidgetEventDetail10875.self,
            from: Data(json.utf8)
        )
    }

    // MARK: - 1. Metric Hierarchy & Source Wiring Guard Across Every Surface

    func testEverySurfaceRespectsHeadlineStyleTableHierarchyAndSourceWiring() throws {
        for surface in HeadlineStyleTable199.Surface.allCases {
            let nowSize = HeadlineStyleTable199.nowBaseSize(surface)
            let prominentSecond = HeadlineStyleTable199.secondNumberBaseSize(surface, prominent: true)
            let regularSecond = HeadlineStyleTable199.secondNumberBaseSize(surface, prominent: false)
            let pregameSecond = HeadlineStyleTable199.pregameNumberBaseSize(surface)
            let nameSize = HeadlineStyleTable199.nameBaseSize(surface)
            let quietSize = HeadlineStyleTable199.quietTextBaseSize(surface)
            let headerSize = HeadlineStyleTable199.headerBaseSize(surface)

            XCTAssertGreaterThanOrEqual(nowSize, prominentSecond, "\(surface) now >= prominent second")
            XCTAssertGreaterThan(prominentSecond, regularSecond, "\(surface) prominent second > regular second")
            XCTAssertGreaterThanOrEqual(regularSecond, pregameSecond, "\(surface) regular second >= pregame")
            XCTAssertGreaterThan(nameSize, quietSize, "\(surface) name > quiet")
            XCTAssertGreaterThan(pregameSecond, headerSize, "\(surface) pregame > header")
        }

        let iosRoot = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()

        let requiredUsages: [(path: String, tokens: [String])] = [
            (
                "Bain Luck/Components/EventSportHeadlineCard12472.swift",
                [
                    "HeadlineStyleTable199.now(.page",
                    "HeadlineStyleTable199.secondNumbers(.page",
                    "HeadlineStyleTable199.names(.page",
                    "HeadlineStyleTable199.headers(.page",
                    "HeadlineStyleTable199.quietText(.page",
                ]
            ),
            (
                "Bain Luck/Components/DiscoverCompactSingleGameCard190C.swift",
                [
                    "HeadlineStyleTable199.now(.card",
                    "HeadlineStyleTable199.secondNumbers(",
                    "HeadlineStyleTable199.names(.card",
                    "HeadlineStyleTable199.headers(.card",
                    "HeadlineStyleTable199.quietText(.card",
                ]
            ),
            (
                "Bain Luck/Components/EventCardView.swift",
                [
                    "HeadlineStyleTable199.now(.card",
                    "HeadlineStyleTable199.secondNumbers(",
                    "HeadlineStyleTable199.names(.card",
                    "HeadlineStyleTable199.headers(.card",
                ]
            ),
            (
                "Bain Luck/Widgets10875/SavedGameHeadlineWidget12616.swift",
                [
                    "HeadlineStyleTable199.now(.widget",
                    "HeadlineStyleTable199.secondNumbers(",
                    "HeadlineStyleTable199.names(",
                    "HeadlineStyleTable199.headers(.widget",
                    "HeadlineStyleTable199.quietText(.widget",
                ]
            ),
            (
                "BainLuckWidget/SavedWidgetLooks12466.swift",
                [
                    "HeadlineStyleTable199.now(.widget",
                    "HeadlineStyleTable199.secondNumbers(.widget",
                    "HeadlineStyleTable199.names(.widget",
                    "HeadlineStyleTable199.headers(.widget",
                ]
            ),
            (
                "Bain Luck/Utilities/WatchWristTile12616.swift",
                [
                    "HeadlineStyleTable199.now(.wristTile",
                    "HeadlineStyleTable199.secondNumbers(.wristTile",
                    "HeadlineStyleTable199.names(.wristTile",
                    "HeadlineStyleTable199.headers(.wristTile",
                    "HeadlineStyleTable199.quietText(.wristTile",
                ]
            ),
        ]

        for entry in requiredUsages {
            let text = try String(contentsOf: iosRoot.appendingPathComponent(entry.path), encoding: .utf8)
            for token in entry.tokens {
                XCTAssertTrue(text.contains(token), "\(entry.path) missing \(token)")
            }
        }
    }

    // MARK: - 2. 390 px Side-by-Side Contact Sheet Across Every Surface & Game State

    private func renderSectionImage(_ content: AnyView) async throws -> UIImage {
        let wrapped = content
            .environmentObject(PinManager(
                defaults: UserDefaults(suiteName: "OneTypeTableEverywhere199Tests")!,
                serverLoad: { PinsResponse(events: [], futures: []) },
                serverSync: { _, _, _ in }
            ))
            .environmentObject(NavigationCoordinator())
            .padding(.vertical, 12)
            .frame(width: 390)
            .background(Color(uiColor: .systemGroupedBackground))
            .ignoresSafeArea()

        let host = hostForMeasurement(wrapped.environment(\.colorScheme, .light), at: .large)
        host.additionalSafeAreaInsets = .zero
        host.overrideUserInterfaceStyle = .light
        let fittedH = max(120, min(ceil(host.sizeThatFits(in: CGSize(width: 390, height: 2300)).height), 2300))
        host.view.frame = CGRect(origin: .zero, size: CGSize(width: 390, height: fittedH))

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

        try await Task.sleep(nanoseconds: 160_000_000)
        let until = Date().addingTimeInterval(0.16)
        repeat {
            host.view.setNeedsLayout()
            host.view.layoutIfNeeded()
            RunLoop.current.run(until: Date().addingTimeInterval(0.015))
        } while Date() < until

        let fmt = UIGraphicsImageRendererFormat()
        fmt.scale = 3.0
        fmt.opaque = true
        return UIGraphicsImageRenderer(bounds: host.view.bounds, format: fmt).image { ctx in
            UIColor.systemGroupedBackground.setFill()
            ctx.fill(host.view.bounds)
            _ = host.view.drawHierarchy(in: host.view.bounds, afterScreenUpdates: true)
        }
    }

    private func writePNG(_ image: UIImage, filename: String, outDir: String?) throws {
        guard let outDir, !outDir.isEmpty else { return }
        let dirURL = URL(fileURLWithPath: outDir, isDirectory: true)
        try FileManager.default.createDirectory(at: dirURL, withIntermediateDirectories: true)
        if let png = image.pngData() {
            try png.write(to: dirURL.appendingPathComponent(filename))
        }
    }

    private func stitchImages(_ images: [UIImage]) -> UIImage {
        let totalHeight = images.reduce(CGFloat(0)) { $0 + $1.size.height }
        let fmt = UIGraphicsImageRendererFormat()
        fmt.scale = 3.0
        fmt.opaque = true
        return UIGraphicsImageRenderer(size: CGSize(width: 390, height: totalHeight), format: fmt).image { ctx in
            UIColor.systemGroupedBackground.setFill()
            ctx.fill(CGRect(x: 0, y: 0, width: 390, height: totalHeight))
            var y: CGFloat = 0
            for img in images {
                img.draw(in: CGRect(x: 0, y: y, width: 390, height: img.size.height))
                y += img.size.height
            }
        }
    }

    private func buildStateSection(
        phaseTitle: String,
        eventJSON: String,
        liveStatusText: String?,
        hasScore: Bool,
        watchInput: WatchWristTileInput12616
    ) throws -> AnyView {
        let feedEvent = try decodeJSON(FeedEventData.self, eventJSON)
        let pageDetail = try decodeJSON(EventDetail.self, eventJSON)
        let widgetDetail = try decodeWidgetEvent(eventJSON)

        let awayColor = Color(hex: "#C60C30")
        let homeColor = Color(hex: "#0076B6")

        // 1. Page Headline (.page)
        let headlineModel = EventSportHeadlines12472.resolve(
            event: pageDetail,
            awayFullName: pageDetail.awayTeam,
            homeFullName: pageDetail.homeTeam,
            liveStatusText: liveStatusText,
            hasScore: hasScore,
            numberStreams: false,
            now: fixedNow
        )
        let pageView = EventSportHeadlineCard12472(
            model: headlineModel,
            colors: (away: awayColor, home: homeColor),
            ekgTracker: EkgTracker(),
            liveUpdateStatus: .hidden,
            displayAsOf: fixedNow,
            updateStream: LiveUpdateStream(),
            showUpdateStream: .constant(false),
            showProbabilityDetails: .constant(false),
            priceStreamingEligible: false,
            lastReceivedAt: fixedNow,
            confirmedAt: fixedNow,
            revealForecast: nil
        )

        // 2. Discover Card (.card)
        let prematch = PrematchReading.resolve(prematch: feedEvent.prematchOdds, opening: feedEvent.openingOdds)
        let discoverCard = DiscoverCompactSingleGameCard190CView(
            event: feedEvent,
            prematch: prematch,
            awayColor: awayColor,
            homeColor: homeColor,
            usesPictureLayout191A: false,
            projectionAndSuspendedLines: { EmptyView() },
            footerRow: { EmptyView() }
        )
        .background(Color.cardBackground, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 16, style: .continuous)
                .stroke(HeadlineStyleTable199.cardBorderInk, lineWidth: 1)
        )

        // 3. Feed Card (.card)
        let feedCard = EventCardView(event: feedEvent, reason: nil)
            .padding(.horizontal, 14)
            .padding(.vertical, 6)
            .background(Color.cardBackground, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
            .overlay(
                RoundedRectangle(cornerRadius: 16, style: .continuous)
                    .stroke(HeadlineStyleTable199.cardBorderInk, lineWidth: 1)
            )

        // 4. Home Screen Widgets (.widget: Medium 338×158 & Small 158×158)
        let reading = SavedWidgetReadingRules10875.game(widgetDetail, side: nil, now: fixedNow)
        let art = SavedWidgetArt12466.game(widgetDetail)
        let widgetModel = SavedGameHeadlineWidgetModel12616.build(
            reading: reading,
            art: art,
            clockFooter: feedEvent.status == "completed" ? "Final" : "As of 11:14 AM",
            isOffline: false,
            clearsRefreshTrailing: false,
            now: fixedNow,
            timeZone: pacific
        )

        @ViewBuilder
        func widgetBar() -> some View {
            if reading.shares != nil {
                GeometryReader { geo in
                    let awayShare: CGFloat = art.isLive ? 0.338 : 0.42
                    let gap: CGFloat = 2
                    let usable = max(8, geo.size.width - gap)
                    HStack(spacing: gap) {
                        Capsule().fill(awayColor).frame(width: usable * awayShare)
                        Capsule().fill(homeColor).frame(width: usable * (1 - awayShare))
                    }
                    .frame(width: geo.size.width, height: 5)
                }
                .frame(height: 5)
            }
        }

        let mediumWidget = SavedGameHeadlineWidgetView12616(
            model: widgetModel,
            size: .medium,
            awayLogo: nil,
            homeLogo: nil,
            fullColor: true,
            bar: widgetBar
        )
        .padding(14)
        .frame(width: 338, height: 158)
        .background(Color.white, in: RoundedRectangle(cornerRadius: 22, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 22, style: .continuous)
                .stroke(HeadlineStyleTable199.cardBorderInk, lineWidth: 1)
        )

        let smallWidget = SavedGameHeadlineWidgetView12616(
            model: widgetModel,
            size: .small,
            awayLogo: nil,
            homeLogo: nil,
            fullColor: true,
            bar: widgetBar
        )
        .padding(14)
        .frame(width: 158, height: 158)
        .background(Color.white, in: RoundedRectangle(cornerRadius: 22, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 22, style: .continuous)
                .stroke(HeadlineStyleTable199.cardBorderInk, lineWidth: 1)
        )

        // 5. Watch Wrist Tile (.wristTile, 184 pt 41mm wrist width)
        let watchModel = WatchWristTileModel12616.build(watchInput, now: fixedNow, timeZone: pacific)
        let watchTile = WatchWristTileView12616(model: watchModel) {
            EmptyView()
        }
        .frame(width: 188)

        return AnyView(
            VStack(alignment: .leading, spacing: 12) {
                Text(phaseTitle)
                    .font(.subheadline.weight(.bold))
                    .foregroundStyle(.primary)
                    .padding(.horizontal, 16)

                VStack(alignment: .leading, spacing: 4) {
                    Text("1 · Game Page Headline (.page)")
                        .font(.caption2.weight(.semibold))
                        .foregroundStyle(.secondary)
                    pageView
                }
                .padding(.horizontal, 16)

                VStack(alignment: .leading, spacing: 4) {
                    Text("2 · Discover Card (.card)")
                        .font(.caption2.weight(.semibold))
                        .foregroundStyle(.secondary)
                    discoverCard
                }
                .padding(.horizontal, 16)

                VStack(alignment: .leading, spacing: 4) {
                    Text("3 · Sports / Feed Card (.card)")
                        .font(.caption2.weight(.semibold))
                        .foregroundStyle(.secondary)
                    feedCard
                }
                .padding(.horizontal, 16)

                VStack(alignment: .leading, spacing: 4) {
                    Text("4 · Medium Widget (.widget · 338×158)")
                        .font(.caption2.weight(.semibold))
                        .foregroundStyle(.secondary)
                    mediumWidget
                }
                .padding(.horizontal, 16)

                VStack(alignment: .leading, spacing: 4) {
                    Text("5 · Small Widget (.widget · 158×158) + Watch Tile (.wristTile) Side by Side")
                        .font(.caption2.weight(.semibold))
                        .foregroundStyle(.secondary)
                    HStack(alignment: .center, spacing: 12) {
                        smallWidget
                        watchTile
                    }
                }
                .padding(.horizontal, 16)
            }
        )
    }

    func testAllSurfacesRenderSideBySideOnOneTypeTable390() async throws {
        let freshStamp = "2026-11-16T19:14:00Z"
        let scheduledKickoff = ISO8601DateFormatter().date(from: "2026-11-17T01:15:00Z")!

        let beforeJSON = """
        {
          "id": 98001,
          "sport": "americanfootball_nfl",
          "sport_name": "NFL",
          "status": "scheduled",
          "commence_time": "2026-11-17T01:15:00Z",
          "away_team": "New England Patriots",
          "home_team": "Detroit Lions",
          "away_team_data": { "abbreviation": "NE", "primary_color": "#C60C30", "secondary_color": "#002244" },
          "home_team_data": { "abbreviation": "DET", "primary_color": "#0076B6", "secondary_color": "#B0B7BC" },
          "current_odds": {
            "away_probability": 0.42,
            "home_probability": 0.58,
            "away_rendered_percent": 42,
            "home_rendered_percent": 58,
            "projected_away_score": 21.0,
            "projected_home_score": 27.0
          },
          "pregame_projection": {
            "projected_away_score": 21.0,
            "projected_home_score": 27.0,
            "kind": "last_before_scheduled_start",
            "boundary": "scheduled_start",
            "boundary_at": "2026-11-17T01:15:00Z",
            "earliest_captured_at": "2026-11-16T18:30:00Z",
            "latest_captured_at": "\(freshStamp)",
            "source": "sportsbooks",
            "basis": "consensus_spread_total",
            "bookmaker_count": 5,
            "unit": "points",
            "period": "full_game"
          },
          "hero_probability_observed_at": "\(freshStamp)"
        }
        """

        let duringJSON = """
        {
          "id": 98002,
          "sport": "americanfootball_nfl",
          "sport_name": "NFL",
          "status": "live",
          "commence_time": "2026-11-16T18:00:00Z",
          "away_team": "New England Patriots",
          "home_team": "Detroit Lions",
          "away_score": 17,
          "home_score": 24,
          "espn": { "period": "Q3", "game_clock": "08:14" },
          "away_team_data": { "abbreviation": "NE", "primary_color": "#C60C30", "secondary_color": "#002244" },
          "home_team_data": { "abbreviation": "DET", "primary_color": "#0076B6", "secondary_color": "#B0B7BC" },
          "prematch_odds": { "away_probability": 0.42, "home_probability": 0.58 },
          "pregame_projection": {
            "projected_away_score": 21.0,
            "projected_home_score": 27.0,
            "kind": "last_before_scheduled_start",
            "boundary": "scheduled_start",
            "boundary_at": "2026-11-16T18:00:00Z",
            "earliest_captured_at": "2026-11-16T17:30:00Z",
            "latest_captured_at": "2026-11-16T17:58:00Z",
            "source": "sportsbooks",
            "basis": "consensus_spread_total",
            "bookmaker_count": 5,
            "unit": "points",
            "period": "full_game"
          },
          "current_odds": {
            "away_probability": 0.338,
            "home_probability": 0.662,
            "away_rendered_percent": 34,
            "home_rendered_percent": 66,
            "projected_away_score": 23.0,
            "projected_home_score": 30.0,
            "live_projection": {
              "projected_away_score": 23.0,
              "projected_home_score": 30.0,
              "kind": "in_play",
              "boundary": "commence_time",
              "boundary_at": "2026-11-16T18:00:00Z",
              "earliest_confirmed_at": "2026-11-16T19:10:00Z",
              "latest_captured_at": "\(freshStamp)",
              "source": "sportsbooks",
              "basis": "consensus_spread_total",
              "bookmaker_count": 5,
              "unit": "points",
              "period": "full_game"
            }
          },
          "hero_probability_observed_at": "\(freshStamp)"
        }
        """

        let afterJSON = """
        {
          "id": 98003,
          "sport": "americanfootball_nfl",
          "sport_name": "NFL",
          "status": "completed",
          "commence_time": "2026-11-16T13:00:00Z",
          "away_team": "New England Patriots",
          "home_team": "Detroit Lions",
          "away_score": 20,
          "home_score": 31,
          "hero_settled_result": "home",
          "away_team_data": { "abbreviation": "NE", "primary_color": "#C60C30", "secondary_color": "#002244" },
          "home_team_data": { "abbreviation": "DET", "primary_color": "#0076B6", "secondary_color": "#B0B7BC" },
          "prematch_odds": { "away_probability": 0.42, "home_probability": 0.58 },
          "current_odds": { "away_probability": 0.0, "home_probability": 1.0 }
        }
        """

        let beforeSection = try buildStateSection(
            phaseTitle: "BEFORE GAME · HeadlineStyleTable199 Across All 5 Surfaces (390 px)",
            eventJSON: beforeJSON,
            liveStatusText: nil,
            hasScore: false,
            watchInput: WatchWristTileInput12616(
                homeTeam: "Detroit Lions", awayTeam: "New England Patriots",
                homeServedAbbreviation: "DET", awayServedAbbreviation: "NE",
                sportKey: "americanfootball_nfl",
                homeProbability: 0.58, awayProbability: 0.42,
                projectedHomeScore: 27.0, projectedAwayScore: 21.0,
                homePrimaryColor: "#0076B6", awayPrimaryColor: "#C60C30",
                commenceTime: scheduledKickoff
            )
        )

        let duringSection = try buildStateSection(
            phaseTitle: "DURING GAME · HeadlineStyleTable199 Across All 5 Surfaces (390 px)",
            eventJSON: duringJSON,
            liveStatusText: "Q3 · 08:14",
            hasScore: true,
            watchInput: WatchWristTileInput12616(
                homeTeam: "Detroit Lions", awayTeam: "New England Patriots",
                homeServedAbbreviation: "DET", awayServedAbbreviation: "NE",
                sportKey: "americanfootball_nfl",
                isLive: true,
                homeScore: 24, awayScore: 17,
                homeProbability: 0.662, awayProbability: 0.338,
                prematchHomeProbability: 0.58, prematchAwayProbability: 0.42,
                homePrimaryColor: "#0076B6", awayPrimaryColor: "#C60C30",
                liveClockText: "Q3 8:14",
                probabilityObservedAt: fixedNow
            )
        )

        let afterSection = try buildStateSection(
            phaseTitle: "AFTER GAME · HeadlineStyleTable199 Across All 5 Surfaces (390 px)",
            eventJSON: afterJSON,
            liveStatusText: nil,
            hasScore: true,
            watchInput: WatchWristTileInput12616(
                homeTeam: "Detroit Lions", awayTeam: "New England Patriots",
                homeServedAbbreviation: "DET", awayServedAbbreviation: "NE",
                sportKey: "americanfootball_nfl",
                isFinal: true,
                homeScore: 31, awayScore: 20,
                prematchHomeProbability: 0.58, prematchAwayProbability: 0.42,
                homePrimaryColor: "#0076B6", awayPrimaryColor: "#C60C30"
            )
        )

        let beforeImg = try await renderSectionImage(beforeSection)
        let duringImg = try await renderSectionImage(duringSection)
        let afterImg = try await renderSectionImage(afterSection)
        let fullSheet = stitchImages([beforeImg, duringImg, afterImg])

        let outDir = ProcessInfo.processInfo.environment["EXPORT_TYPE_TABLE_199_DIR"]
        try writePNG(beforeImg, filename: "199-type-table-before-390.png", outDir: outDir)
        try writePNG(duringImg, filename: "199-type-table-during-390.png", outDir: outDir)
        try writePNG(afterImg, filename: "199-type-table-after-390.png", outDir: outDir)
        try writePNG(fullSheet, filename: "199-one-type-table-everywhere-390.png", outDir: outDir)
    }

    // MARK: - 3. One Layout Per State Across Every Surface (5 Unifications)

    func testOneLayoutPerStateAcrossEverySurface() throws {
        let freshStamp = "2026-11-16T19:14:00Z"

        // 1. Before: Discover card uses `Proj. · Chance` columns, never a `"Projected: ..."` sentence.
        let scheduledFeed = try decodeJSON(FeedEventData.self, """
        {
          "id": 99001,
          "sport": "americanfootball_nfl",
          "sport_name": "NFL",
          "status": "scheduled",
          "commence_time": "2026-11-17T01:15:00Z",
          "away_team": "New England Patriots",
          "home_team": "Detroit Lions",
          "away_team_data": { "abbreviation": "NE", "primary_color": "#002244", "secondary_color": "#C60C30" },
          "home_team_data": { "abbreviation": "DET", "primary_color": "#0076B6" },
          "current_odds": {
            "away_probability": 0.42,
            "home_probability": 0.58,
            "away_rendered_percent": 42,
            "home_rendered_percent": 58,
            "projected_away_score": 21.0,
            "projected_home_score": 27.0
          }
        }
        """)
        let beforeDiscover = DiscoverSingleGameCard190C.build(event: scheduledFeed, prematch: nil)
        XCTAssertEqual(beforeDiscover.headers, .init(score: nil, pregame: "Proj.", primary: "Chance"))
        XCTAssertEqual(beforeDiscover.rows[0].pregameText, "21")
        XCTAssertEqual(beforeDiscover.rows[1].pregameText, "27")
        XCTAssertNil(beforeDiscover.scheduledProjectedLine)

        // 2. After: Discover card uses `Pregame · Final` with tick after winner's score, no bar, no `Result` column;
        //    Feed card (`EventCardView`) also has no finished `ProbabilityBar` and places the tick after the winner's score.
        let finishedFeed = try decodeJSON(FeedEventData.self, """
        {
          "id": 99003,
          "sport": "americanfootball_nfl",
          "sport_name": "NFL",
          "status": "completed",
          "commence_time": "2026-11-16T13:00:00Z",
          "away_team": "New England Patriots",
          "home_team": "Detroit Lions",
          "away_score": 20,
          "home_score": 31,
          "prematch_odds": { "away_probability": 0.42, "home_probability": 0.58 }
        }
        """)
        let prematch = PrematchReading.resolve(prematch: finishedFeed.prematchOdds, opening: finishedFeed.openingOdds)
        let afterDiscover = DiscoverSingleGameCard190C.build(event: finishedFeed, prematch: prematch)
        XCTAssertEqual(afterDiscover.headers, .init(score: nil, pregame: "Pregame", primary: "Final"))
        XCTAssertNil(afterDiscover.bar)
        XCTAssertNil(afterDiscover.rows[0].scoreText)
        XCTAssertNil(afterDiscover.rows[1].scoreText)
        XCTAssertEqual(afterDiscover.rows[0].primaryCell, .finalScore(text: "20", won: false, isDrawOutcome: false))
        XCTAssertEqual(afterDiscover.rows[1].primaryCell, .finalScore(text: "31", won: true, isDrawOutcome: false))

        let iosRoot = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
        let eventCardSource = try String(contentsOf: iosRoot.appendingPathComponent("Bain Luck/Components/EventCardView.swift"), encoding: .utf8)
        XCTAssertTrue(eventCardSource.contains("if isFinished {\n            // One layout per state: finished cards print Pregame · Final with the\n            // tick after the winner's score and no probability bar.\n            EmptyView()"))

        // 3 & 4. Medium Widget: During uses `Score · Proj. · Now` (`204-C`) with pregame bar notch;
        //        Before prints both teams' chances in team colour (Patriots red `#C60C30`, not black `#111827`).
        let beforeWidgetDetail = try decodeWidgetEvent("""
        {
          "id": 99004,
          "sport": "americanfootball_nfl",
          "sport_name": "NFL",
          "status": "scheduled",
          "commence_time": "2026-11-17T01:15:00Z",
          "away_team": "New England Patriots",
          "home_team": "Detroit Lions",
          "away_team_data": { "abbreviation": "NE", "primary_color": "#002244", "secondary_color": "#C60C30" },
          "home_team_data": { "abbreviation": "DET", "primary_color": "#0076B6" },
          "current_odds": {
            "away_probability": 0.42,
            "home_probability": 0.58,
            "away_rendered_percent": 42,
            "home_rendered_percent": 58,
            "projected_away_score": 21.0,
            "projected_home_score": 27.0
          },
          "hero_probability_observed_at": "\(freshStamp)"
        }
        """)
        let beforeArt = SavedWidgetArt12466.game(beforeWidgetDetail)
        let beforeReading = SavedWidgetReadingRules10875.game(beforeWidgetDetail, side: nil, now: fixedNow)
        let beforeWidgetModel = SavedGameHeadlineWidgetModel12616.build(
            reading: beforeReading,
            art: beforeArt,
            clockFooter: "As of 11:14 AM",
            isOffline: false,
            clearsRefreshTrailing: false,
            now: fixedNow,
            timeZone: pacific
        )
        XCTAssertEqual(beforeWidgetModel.headers, .init(leading: "Proj.", pregame: nil, primary: "Chance"))
        XCTAssertEqual(beforeWidgetModel.away.teamInkHex.uppercased(), "#C60C30", "Patriots chance uses Patriots red")
        XCTAssertFalse(beforeWidgetModel.away.isEmphasized, "Patriots is the underdog")
        let widgetSource = try String(contentsOf: iosRoot.appendingPathComponent("Bain Luck/Widgets10875/SavedGameHeadlineWidget12616.swift"), encoding: .utf8)
        XCTAssertTrue(widgetSource.contains("case .before:\n            return row.figure == \"—\" ? inkSecondary : Color(hex: row.teamInkHex)"))

        // 3. During, medium widget: HELD on `Score · Pregame · Now` while Decision 204 is reopened with Alex.
        let duringWidgetDetail = try decodeWidgetEvent("""
        {
          "id": 99005,
          "sport": "americanfootball_nfl",
          "sport_name": "NFL",
          "status": "live",
          "commence_time": "2026-11-16T18:00:00Z",
          "away_team": "New England Patriots",
          "home_team": "Detroit Lions",
          "away_score": 17,
          "home_score": 24,
          "espn": { "period": "Q3", "game_clock": "08:14" },
          "away_team_data": { "abbreviation": "NE", "primary_color": "#002244", "secondary_color": "#C60C30" },
          "home_team_data": { "abbreviation": "DET", "primary_color": "#0076B6" },
          "prematch_odds": { "away_probability": 0.42, "home_probability": 0.58 },
          "current_odds": {
            "away_probability": 0.338,
            "home_probability": 0.662,
            "away_rendered_percent": 34,
            "home_rendered_percent": 66
          },
          "hero_probability_observed_at": "\(freshStamp)"
        }
        """)
        let duringArt = SavedWidgetArt12466.game(duringWidgetDetail)
        let duringReading = SavedWidgetReadingRules10875.game(duringWidgetDetail, side: nil, now: fixedNow)
        let duringWidgetModel = SavedGameHeadlineWidgetModel12616.build(
            reading: duringReading,
            art: duringArt,
            clockFooter: "As of 11:14 AM",
            isOffline: false,
            clearsRefreshTrailing: false,
            now: fixedNow,
            timeZone: pacific
        )
        XCTAssertEqual(duringWidgetModel.headers, .init(leading: "Score", pregame: "Pregame", primary: "Now"))
        XCTAssertEqual(duringWidgetModel.away.pregameText, "42%")
        XCTAssertEqual(duringWidgetModel.home.pregameText, "58%")

        // 5. Watch tile: `"Up 8 points from 58%"` (no `+`, `"points"` / `"point"`, no `"pregame"`).
        let watchUp = WatchWristTileModel12616.build(
            WatchWristTileInput12616(
                homeTeam: "Detroit Lions", awayTeam: "New England Patriots",
                homeServedAbbreviation: "DET", awayServedAbbreviation: "NE",
                sportKey: "americanfootball_nfl",
                isLive: true,
                homeScore: 24, awayScore: 17,
                homeProbability: 0.662, awayProbability: 0.338,
                prematchHomeProbability: 0.58, prematchAwayProbability: 0.42,
                homePrimaryColor: "#0076B6", awayPrimaryColor: "#C60C30",
                liveClockText: "Q3 8:14",
                probabilityObservedAt: fixedNow
            ),
            now: fixedNow,
            timeZone: pacific
        )
        XCTAssertEqual(watchUp.supportingLine, "Up 8 points from 58%")
    }
}
