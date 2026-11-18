import SwiftUI
import UIKit
import XCTest
@testable import Bain_Luck

/// #12926 / #12581 (137-A) — Team schedule rows on `/api/teams/{slug}` carry
/// `source_mark` (current chance) and `pregame_source_mark` (historical pregame
/// reading) oriented to this page's team (`is_home`). `SearchEventCardAdapter183A`
/// maps each served mark onto its side without inferring or complementing an
/// opponent mark, and `EventCardView` draws the quiet `ⓘ` source mark for the
/// displayed probability (`source_mark` while gradable, `pregame_source_mark`
/// once settled).
@MainActor
final class TeamScheduleSourceMarks12926Tests: XCTestCase {

    private let celtics = TeamPageTeam(
        id: 501,
        slug: "boston-celtics",
        name: "Boston Celtics",
        abbreviation: "BOS",
        location: "Boston",
        sportKey: "basketball_nba",
        sportName: "NBA",
        primaryColor: "#007A33",
        secondaryColor: "#BA9653",
        logoSmall: nil,
        logoLarge: nil,
        record: "12-3",
        standings: nil
    )

    private func decodeBrief(_ json: String) throws -> SearchEvent {
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        return try d.decode(SearchEvent.self, from: Data(json.utf8))
    }

    func testUpcomingHomeAndAwayBriefsMapServedSourceMarkToPageTeamOnly() throws {
        let futureISO = Date().addingTimeInterval(3 * 3600).ISO8601Format()
        let obsISO = Date().addingTimeInterval(-120).ISO8601Format()

        let awayBrief = try decodeBrief("""
        {
          "id": 9901,
          "sport_key": "basketball_nba",
          "home_team": "Cleveland Cavaliers",
          "away_team": "Boston Celtics",
          "commence_time": "\(futureISO)",
          "status": "scheduled",
          "is_home": false,
          "opponent": "Cleveland Cavaliers",
          "win_probability": 0.382,
          "source_mark": {
            "state": "blend",
            "method": "Weighted middle across 3 sources",
            "sources": [
              {"key": "betting", "name": "Sportsbooks", "probability": 0.38, "observed_at": "\(obsISO)", "count": 6},
              {"key": "kalshi", "name": "Kalshi", "probability": 0.39, "observed_at": "\(obsISO)"},
              {"key": "polymarket", "name": "Polymarket", "probability": 0.375, "observed_at": null}
            ]
          },
          "pregame_win_probability": 0.382,
          "pregame_source_mark": {
            "state": "single",
            "sources": [{"key": "betting", "name": "Sportsbooks", "probability": 0.382, "observed_at": null}]
          }
        }
        """)

        let adaptedAway = SearchEventCardAdapter183A.fromTeamScheduleBrief(awayBrief, team: celtics)
        XCTAssertNil(adaptedAway.feedEvent.sourceMark, "137-A: never synthesize a home mark from an away brief")
        XCTAssertNotNil(adaptedAway.feedEvent.awaySourceMark)
        XCTAssertNil(adaptedAway.feedEvent.pregameSourceMark)
        XCTAssertNotNil(adaptedAway.feedEvent.awayPregameSourceMark)

        let resolvedAway = try XCTUnwrap(
            EventCardView.resolvedCardSourceMark(
                event: adaptedAway.feedEvent,
                canStillBeGraded: true,
                currentAwayIsWithheld: false,
                prematch: PrematchReading.resolve(prematch: adaptedAway.feedEvent.prematchOdds, opening: nil),
                prematchAwayIsWithheld: false
            )
        )
        XCTAssertEqual(resolvedAway.mark.state, .blend)
        XCTAssertEqual(resolvedAway.mark.sources.map(\.key), ["betting", "kalshi", "polymarket"])
        XCTAssertEqual(resolvedAway.subject, "Celtics")
        XCTAssertFalse(resolvedAway.isPregame)
        XCTAssertEqual(
            SourceMarkSheet.contextLine(subject: resolvedAway.subject, isPregame: resolvedAway.isPregame),
            "Celtics"
        )
        let awayProb = try XCTUnwrap(resolvedAway.number)
        XCTAssertEqual(awayProb, 0.382, accuracy: 0.0001)
        XCTAssertEqual(SourceMarkSheet.headline(resolvedAway.number), "38%")

        let homeBrief = try decodeBrief("""
        {
          "id": 9902,
          "sport_key": "basketball_nba",
          "home_team": "Boston Celtics",
          "away_team": "Toronto Raptors",
          "commence_time": "\(futureISO)",
          "status": "scheduled",
          "is_home": true,
          "opponent": "Toronto Raptors",
          "win_probability": 0.764,
          "source_mark": {
            "state": "blend",
            "sources": [
              {"key": "betting", "name": "Sportsbooks", "probability": 0.76, "observed_at": "\(obsISO)", "count": 5},
              {"key": "kalshi", "name": "Kalshi", "probability": 0.77, "observed_at": "\(obsISO)"}
            ]
          },
          "pregame_win_probability": 0.75,
          "pregame_source_mark": {
            "state": "single",
            "sources": [{"key": "betting", "name": "Sportsbooks", "probability": 0.75, "observed_at": null}]
          }
        }
        """)

        let adaptedHome = SearchEventCardAdapter183A.fromTeamScheduleBrief(homeBrief, team: celtics)
        XCTAssertNotNil(adaptedHome.feedEvent.sourceMark)
        XCTAssertNil(adaptedHome.feedEvent.awaySourceMark)
        let resolvedHome = try XCTUnwrap(
            EventCardView.resolvedCardSourceMark(
                event: adaptedHome.feedEvent,
                canStillBeGraded: true,
                currentAwayIsWithheld: false,
                prematch: PrematchReading.resolve(prematch: adaptedHome.feedEvent.prematchOdds, opening: nil),
                prematchAwayIsWithheld: false
            )
        )
        let homeProb = try XCTUnwrap(resolvedHome.number)
        XCTAssertEqual(homeProb, 0.764, accuracy: 0.0001)
        XCTAssertEqual(SourceMarkSheet.headline(resolvedHome.number), "76%")
    }

    func testSettledBriefUsesPregameSourceMarkAndNeverStaleLiveBlend() throws {
        let pastISO = Date().addingTimeInterval(-24 * 3600).ISO8601Format()

        let settledBrief = try decodeBrief("""
        {
          "id": 9903,
          "sport_key": "basketball_nba",
          "home_team": "Boston Celtics",
          "away_team": "New York Knicks",
          "commence_time": "\(pastISO)",
          "status": "completed",
          "home_score": 114,
          "away_score": 107,
          "is_home": true,
          "opponent": "New York Knicks",
          "win_probability": 0.994,
          "source_mark": {
            "state": "blend",
            "sources": [{"key": "kalshi", "name": "Kalshi", "probability": 0.994, "observed_at": null}]
          },
          "pregame_win_probability": 0.63,
          "pregame_source_mark": {
            "state": "single",
            "sources": [{"key": "betting", "name": "Sportsbooks", "probability": 0.634, "observed_at": null}]
          }
        }
        """)

        let adapted = SearchEventCardAdapter183A.fromTeamScheduleBrief(settledBrief, team: celtics)
        let prematch = PrematchReading.resolve(prematch: adapted.feedEvent.prematchOdds, opening: nil)
        let resolved = try XCTUnwrap(
            EventCardView.resolvedCardSourceMark(
                event: adapted.feedEvent,
                canStillBeGraded: false,
                currentAwayIsWithheld: false,
                prematch: prematch,
                prematchAwayIsWithheld: false
            )
        )
        XCTAssertEqual(resolved.mark.state, .single)
        XCTAssertEqual(resolved.mark.sources.map(\.key), ["betting"])
        XCTAssertEqual(resolved.subject, "Celtics")
        XCTAssertTrue(resolved.isPregame)
        XCTAssertEqual(
            SourceMarkSheet.contextLine(subject: resolved.subject, isPregame: resolved.isPregame),
            "Celtics · Pregame"
        )
        let preProb = try XCTUnwrap(resolved.number)
        XCTAssertEqual(preProb, 0.63, accuracy: 0.0001)
        XCTAssertEqual(SourceMarkSheet.headline(resolved.number), "63%")
        XCTAssertEqual(SourceMarkSheet.method(resolved.mark), "Sportsbooks' price")
        XCTAssertEqual(
            SourceMarkSheet.singleUnscaledAttribution(resolved.mark, headline: "63%"),
            "From Sportsbooks"
        )

        // Scaled single-source marks keep the full row + scaling sentence (`nil` singleUnscaledAttribution).
        let scaled = SourceMark(
            state: .single,
            sources: [.init(key: "betting", name: "Sportsbooks", probability: 0.16, observedAt: nil, count: 6)],
            method: "Scaled across 32 outcomes so the field totals 100%"
        )
        XCTAssertNil(SourceMarkSheet.singleUnscaledAttribution(scaled, headline: "14%"))
    }

    func testEventCardDarkModeResolvesThroughRuling221Floor() throws {
        let futureISO = Date().addingTimeInterval(3 * 3600).ISO8601Format()
        let json = """
        {
          "id": 9905,
          "sport": "basketball_nba",
          "home_team": "Indiana Pacers",
          "away_team": "Houston Rockets",
          "commence_time": "\(futureISO)",
          "status": "scheduled",
          "current_odds": {"home_probability": 0.26, "away_probability": 0.74},
          "away_team_data": {"primary_color": "#CE1141", "secondary_color": "#000000"},
          "home_team_data": {"primary_color": "#002D62", "secondary_color": "#FDBB30"}
        }
        """
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        let event = try d.decode(FeedEventData.self, from: Data(json.utf8))
        let card = EventCardView(event: event, reason: nil)
        let darkHexes = card.barColorHexes(for: .dark)
        XCTAssertTrue(
            TeamTextContrast.readableOnSurface(darkHexes.home, surfaceLuminance: TeamTextContrast.darkSurfaceLuminance),
            "Pacers #002D62 must resolve to readable secondary #FDBB30 (or lightened >= 3:1) in Dark mode, got \(darkHexes.home)"
        )
        XCTAssertEqual(darkHexes.home.uppercased(), "#FDBB30")
    }

    func testThreeWaySoccerAwayUnavailableDrawsNoMark() throws {
        let futureISO = Date().addingTimeInterval(6 * 3600).ISO8601Format()
        let arsenal = TeamPageTeam(
            id: 601,
            slug: "arsenal",
            name: "Arsenal",
            abbreviation: "ARS",
            location: "London",
            sportKey: "soccer_epl",
            sportName: "Premier League",
            primaryColor: "#EF0107",
            secondaryColor: "#FFFFFF",
            logoSmall: nil,
            logoLarge: nil,
            record: nil,
            standings: nil
        )

        let awaySoccerBrief = try decodeBrief("""
        {
          "id": 9904,
          "sport_key": "soccer_epl",
          "home_team": "Newcastle United",
          "away_team": "Arsenal",
          "commence_time": "\(futureISO)",
          "status": "scheduled",
          "is_home": false,
          "opponent": "Newcastle United",
          "win_probability": null,
          "source_mark": {"state": "none"},
          "pregame_win_probability": null,
          "pregame_source_mark": {"state": "none"}
        }
        """)

        let adapted = SearchEventCardAdapter183A.fromTeamScheduleBrief(awaySoccerBrief, team: arsenal)
        let resolved = EventCardView.resolvedCardSourceMark(
            event: adapted.feedEvent,
            canStillBeGraded: true,
            currentAwayIsWithheld: !adapted.awayReadingIsServerVerified,
            prematch: nil,
            prematchAwayIsWithheld: !adapted.awayReadingIsServerVerified
        )
        XCTAssertNil(resolved)
    }

    private func captureWindowSnapshot<V: View>(
        _ content: V,
        scheme: ColorScheme,
        width: CGFloat = 390,
        fixedHeight: CGFloat? = nil
    ) async throws -> UIImage {
        let host = hostForMeasurement(content, at: .large)
        let uiStyle: UIUserInterfaceStyle = scheme == .light ? .light : .dark
        host.overrideUserInterfaceStyle = uiStyle
        host.traitOverrides.preferredContentSizeCategory = .large

        let height: CGFloat = {
            if let fixedHeight { return fixedHeight }
            let fitted = ceil(host.sizeThatFits(in: CGSize(width: width, height: 1_600)).height)
            return max(fitted, 260)
        }()
        let bounds = CGRect(x: 0, y: 0, width: width, height: height)

        let scene = try XCTUnwrap(
            UIApplication.shared.connectedScenes.compactMap({ $0 as? UIWindowScene }).first
        )
        let existingWindows = scene.windows
        existingWindows.forEach { $0.isHidden = true }
        let window = UIWindow(windowScene: scene)
        window.frame = bounds
        window.overrideUserInterfaceStyle = uiStyle
        window.traitOverrides.preferredContentSizeCategory = .large
        window.rootViewController = host
        window.makeKeyAndVisible()
        defer {
            window.isHidden = true
            window.rootViewController = nil
            existingWindows.forEach { $0.isHidden = false }
        }

        host.view.frame = bounds
        host.view.setNeedsLayout()
        host.view.layoutIfNeeded()
        try await Task.sleep(nanoseconds: 900_000_000)
        host.view.setNeedsLayout()
        host.view.layoutIfNeeded()

        let fmt = UIGraphicsImageRendererFormat()
        fmt.scale = 3.0
        return UIGraphicsImageRenderer(bounds: bounds, format: fmt).image { ctx in
            if !window.drawHierarchy(in: bounds, afterScreenUpdates: true) {
                window.layer.render(in: ctx.cgContext)
            }
        }
    }

    func testRenderLiveTeamScheduleSourceMarks390() async throws {
        let env = ProcessInfo.processInfo.environment
        guard let outDir = env["RENDER_12926_DIR"], !outDir.isEmpty,
              let jsonPath = env["RENDER_12926_JSON"], !jsonPath.isEmpty else {
            return
        }

        let data = try Data(contentsOf: URL(fileURLWithPath: jsonPath))
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let page = try decoder.decode(TeamPageResponse.self, from: data)

        let upcomingWithMark = try XCTUnwrap(
            page.upcomingEvents.first(where: { $0.sourceMark?.draws == true }),
            "Live team payload must contain at least one upcoming row with a drawable source_mark"
        )
        let recentWithMark = try XCTUnwrap(
            page.recentEvents.first(where: { $0.pregameSourceMark?.draws == true }),
            "Live team payload must contain at least one recent row with a drawable pregame_source_mark"
        )

        let suiteName = "Render12926.\(UUID().uuidString)"
        let defaults = try XCTUnwrap(UserDefaults(suiteName: suiteName))
        defer { defaults.removePersistentDomain(forName: suiteName) }
        let pinManager = PinManager(defaults: defaults)

        let adaptedUpcoming = SearchEventCardAdapter183A.fromTeamScheduleBrief(upcomingWithMark, team: page.team)
        let adaptedRecent = SearchEventCardAdapter183A.fromTeamScheduleBrief(recentWithMark, team: page.team)

        let upcomingResolved = try XCTUnwrap(
            EventCardView.resolvedCardSourceMark(
                event: adaptedUpcoming.feedEvent,
                canStillBeGraded: true,
                currentAwayIsWithheld: DrawPricedWinner.sportPricesADraw(adaptedUpcoming.feedEvent.sport) && !adaptedUpcoming.awayReadingIsServerVerified,
                prematch: PrematchReading.resolve(prematch: adaptedUpcoming.feedEvent.prematchOdds, opening: nil),
                prematchAwayIsWithheld: false
            )
        )
        let recentResolved = try XCTUnwrap(
            EventCardView.resolvedCardSourceMark(
                event: adaptedRecent.feedEvent,
                canStillBeGraded: false,
                currentAwayIsWithheld: false,
                prematch: PrematchReading.resolve(prematch: adaptedRecent.feedEvent.prematchOdds, opening: nil),
                prematchAwayIsWithheld: DrawPricedWinner.sportPricesADraw(adaptedRecent.feedEvent.sport) && !adaptedRecent.awayReadingIsServerVerified
            )
        )

        try FileManager.default.createDirectory(atPath: outDir, withIntermediateDirectories: true)

        for scheme in [ColorScheme.light, ColorScheme.dark] {
            let tag = scheme == .light ? "light" : "dark"
            let pageBg = scheme == .light ? Color(hex: "#F2F2F7") : Color(hex: "#000000")
            let cardBg = scheme == .light ? Color.white : Color(hex: "#1C1C1E")

            let scheduleView = VStack(alignment: .leading, spacing: 14) {
                Text(page.team.name)
                    .font(.title3.bold())
                    .foregroundStyle(.primary)
                    .padding(.horizontal, 4)

                VStack(alignment: .leading, spacing: 6) {
                    Text("UPCOMING")
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(.secondary)
                        .padding(.horizontal, 4)
                    EventCardView(
                        event: adaptedUpcoming.feedEvent,
                        reason: nil,
                        compactScheduleStyle: true,
                        awayReadingIsServerVerified: adaptedUpcoming.awayReadingIsServerVerified
                    )
                    .padding(.horizontal, 14)
                    .padding(.vertical, 8)
                    .background(RoundedRectangle(cornerRadius: 12).fill(cardBg))
                }

                VStack(alignment: .leading, spacing: 6) {
                    Text("RECENT")
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(.secondary)
                        .padding(.horizontal, 4)
                    EventCardView(
                        event: adaptedRecent.feedEvent,
                        reason: nil,
                        compactScheduleStyle: true,
                        awayReadingIsServerVerified: adaptedRecent.awayReadingIsServerVerified
                    )
                    .padding(.horizontal, 14)
                    .padding(.vertical, 8)
                    .background(RoundedRectangle(cornerRadius: 12).fill(cardBg))
                }
            }
            .padding(16)
            .frame(width: 390)
            .background(pageBg)
            .environmentObject(pinManager)
            .environment(\.colorScheme, scheme)

            let scheduleImg = try await captureWindowSnapshot(scheduleView, scheme: scheme, width: 390)
            try XCTUnwrap(scheduleImg.pngData()).write(
                to: URL(fileURLWithPath: "\(outDir)/team-schedule-cards-\(tag)-390.png")
            )

            let upcomingSheet = SourceMarkSheet(
                mark: upcomingResolved.mark,
                number: upcomingResolved.number,
                subject: upcomingResolved.subject,
                isPregame: upcomingResolved.isPregame
            )
                .environment(\.colorScheme, scheme)
            let upSheetImg = try await captureWindowSnapshot(upcomingSheet, scheme: scheme, width: 390, fixedHeight: 430)
            try XCTUnwrap(upSheetImg.pngData()).write(
                to: URL(fileURLWithPath: "\(outDir)/team-schedule-upcoming-sheet-\(tag)-390.png")
            )

            let recentSheet = SourceMarkSheet(
                mark: recentResolved.mark,
                number: recentResolved.number,
                subject: recentResolved.subject,
                isPregame: recentResolved.isPregame
            )
                .environment(\.colorScheme, scheme)
            let recSheetImg = try await captureWindowSnapshot(recentSheet, scheme: scheme, width: 390, fixedHeight: 280)
            try XCTUnwrap(recSheetImg.pngData()).write(
                to: URL(fileURLWithPath: "\(outDir)/team-schedule-recent-sheet-\(tag)-390.png")
            )

            let futureISO = Date().addingTimeInterval(4 * 3600).ISO8601Format()
            let pacersEvent = try decoder.decode(FeedEventData.self, from: Data("""
            {
              "id": 9910,
              "sport": "basketball_nba",
              "sport_name": "NBA",
              "home_team": "Indiana Pacers",
              "away_team": "Houston Rockets",
              "commence_time": "\(futureISO)",
              "status": "scheduled",
              "current_odds": {"home_probability": 0.26, "away_probability": 0.74, "projected_home_score": 109, "projected_away_score": 117},
              "away_team_data": {"primary_color": "#CE1141", "secondary_color": "#000000", "logo_small": "https://a.espncdn.com/i/teamlogos/nba/500/scoreboard/hou.png"},
              "home_team_data": {"primary_color": "#002D62", "secondary_color": "#FDBB30", "logo_small": "https://a.espncdn.com/i/teamlogos/nba/500/scoreboard/ind.png"}
            }
            """.utf8))
            let bucksEvent = try decoder.decode(FeedEventData.self, from: Data("""
            {
              "id": 9911,
              "sport": "basketball_nba",
              "sport_name": "NBA",
              "home_team": "Miami Heat",
              "away_team": "Milwaukee Bucks",
              "commence_time": "\(futureISO)",
              "status": "scheduled",
              "current_odds": {"home_probability": 0.85, "away_probability": 0.15, "projected_home_score": 124, "projected_away_score": 112},
              "away_team_data": {"primary_color": "#00471B", "secondary_color": "#EEE1C6", "logo_small": "https://a.espncdn.com/i/teamlogos/nba/500/scoreboard/mil.png"},
              "home_team_data": {"primary_color": "#98002E", "secondary_color": "#F9A01B", "logo_small": "https://a.espncdn.com/i/teamlogos/nba/500/scoreboard/mia.png"}
            }
            """.utf8))
            let darkContrastStack = VStack(alignment: .leading, spacing: 12) {
                EventCardView(event: pacersEvent, reason: nil)
                    .padding(.horizontal, 14)
                    .padding(.vertical, 8)
                    .background(RoundedRectangle(cornerRadius: 12).fill(cardBg))
                EventCardView(event: bucksEvent, reason: nil)
                    .padding(.horizontal, 14)
                    .padding(.vertical, 8)
                    .background(RoundedRectangle(cornerRadius: 12).fill(cardBg))
            }
            .padding(16)
            .frame(width: 390)
            .background(pageBg)
            .environmentObject(pinManager)
            .environment(\.colorScheme, scheme)
            let contrastImg = try await captureWindowSnapshot(darkContrastStack, scheme: scheme, width: 390)
            try XCTUnwrap(contrastImg.pngData()).write(
                to: URL(fileURLWithPath: "\(outDir)/dark-contrast-cards-\(tag)-390.png")
            )
        }
    }
}
