import SwiftUI
import UIKit
import XCTest
@testable import Bain_Luck

/// Ruling 197 (Alex, `#12538`) — Two teams in the same colour family across all
/// two-team app surfaces (cards, headlines, charts, bars, widgets).
///
/// When both teams' primary colours share a chromatic hue family (in addition to
/// near-identical collisions), the home team keeps its primary colour and the
/// away team switches to its own `secondary_color` when readable (`>= 3:1` on
/// white, distinguishable from home, and outside home's hue family), else slate
/// grey (`#64748B`).
@MainActor
final class Ruling197TwoTeamSurfacesTests: XCTestCase {

    private let fixedNow = ISO8601DateFormatter().date(from: "2026-11-15T20:00:00Z")!

    private struct TeamSpec {
        let name: String
        let abbr: String
        let primary: String
        let secondary: String?
        let record: String
    }

    private let duke = TeamSpec(name: "Duke", abbr: "DUKE", primary: "#00539B", secondary: "#FFFFFF", record: "4-0")
    private let kansas = TeamSpec(name: "Kansas", abbr: "KU", primary: "#0051BA", secondary: "#E8000D", record: "4-0")
    private let gonzaga = TeamSpec(name: "Gonzaga", abbr: "GONZ", primary: "#041E42", secondary: "#C8102E", record: "4-0")
    private let kentucky = TeamSpec(name: "Kentucky", abbr: "UK", primary: "#0033A0", secondary: "#FFFFFF", record: "3-1")
    private let unc = TeamSpec(name: "North Carolina", abbr: "UNC", primary: "#7BAFD4", secondary: "#13294B", record: "3-1")
    private let alabama = TeamSpec(name: "Alabama", abbr: "ALA", primary: "#9E1B32", secondary: "#FFFFFF", record: "4-0")

    private func makeFeedEvent(
        id: Int,
        away: TeamSpec,
        home: TeamSpec,
        awayScore: Int = 68,
        homeScore: Int = 71,
        awayPct: Int = 42,
        homePct: Int = 58
    ) throws -> FeedEventData {
        let awaySec = away.secondary.map { #""secondary_color": "\#($0)","# } ?? ""
        let homeSec = home.secondary.map { #""secondary_color": "\#($0)","# } ?? ""
        let json = """
        {
          "id": \(id),
          "sport": "basketball_ncaab",
          "sport_name": "NCAAB",
          "home_team": "\(home.name)",
          "away_team": "\(away.name)",
          "commence_time": "2026-11-15T19:00:00Z",
          "status": "live",
          "home_score": \(homeScore),
          "away_score": \(awayScore),
          "home_team_data": {
            "abbreviation": "\(home.abbr)",
            \(homeSec)
            "primary_color": "\(home.primary)",
            "record": "\(home.record)"
          },
          "away_team_data": {
            "abbreviation": "\(away.abbr)",
            \(awaySec)
            "primary_color": "\(away.primary)",
            "record": "\(away.record)"
          },
          "current_odds": {
            "home_probability": \(Double(homePct) / 100.0),
            "away_probability": \(Double(awayPct) / 100.0),
            "home_rendered_percent": \(homePct),
            "away_rendered_percent": \(awayPct),
            "projected_home_score": 78.0,
            "projected_away_score": 75.0,
            "updated_at": "2026-11-15T19:59:45Z"
          },
          "prematch_odds": {
            "home_probability": 0.55,
            "away_probability": 0.45,
            "home_rendered_percent": 55,
            "away_rendered_percent": 45
          },
          "espn": {
            "period": "2nd",
            "game_clock": "6:42",
            "broadcast": "ESPN"
          }
        }
        """
        let dec = JSONDecoder()
        dec.keyDecodingStrategy = .convertFromSnakeCase
        return try dec.decode(FeedEventData.self, from: Data(json.utf8))
    }

    private func makeEventDetail(
        id: Int,
        away: TeamSpec,
        home: TeamSpec,
        awayScore: Int = 68,
        homeScore: Int = 71,
        awayPct: Int = 42,
        homePct: Int = 58
    ) throws -> EventDetail {
        let awaySec = away.secondary.map { #""secondary_color": "\#($0)","# } ?? ""
        let homeSec = home.secondary.map { #""secondary_color": "\#($0)","# } ?? ""
        let json = """
        {
          "id": \(id),
          "sport": "basketball_ncaab",
          "sport_name": "NCAAB",
          "home_team": "\(home.name)",
          "away_team": "\(away.name)",
          "commence_time": "2026-11-15T19:00:00Z",
          "status": "live",
          "home_score": \(homeScore),
          "away_score": \(awayScore),
          "home_team_data": {
            "abbreviation": "\(home.abbr)",
            \(homeSec)
            "primary_color": "\(home.primary)",
            "record": "\(home.record)"
          },
          "away_team_data": {
            "abbreviation": "\(away.abbr)",
            \(awaySec)
            "primary_color": "\(away.primary)",
            "record": "\(away.record)"
          },
          "current_odds": {
            "home_probability": \(Double(homePct) / 100.0),
            "away_probability": \(Double(awayPct) / 100.0),
            "home_rendered_percent": \(homePct),
            "away_rendered_percent": \(awayPct),
            "projected_home_score": 78.0,
            "projected_away_score": 75.0,
            "updated_at": "2026-11-15T19:59:45Z"
          },
          "prematch_odds": {
            "home_probability": 0.55,
            "away_probability": 0.45,
            "home_rendered_percent": 55,
            "away_rendered_percent": 45,
            "projected_home_score": 77.5,
            "projected_away_score": 74.5
          },
          "hero_probability": \(Double(homePct) / 100.0),
          "hero_probability_away": \(Double(awayPct) / 100.0),
          "hero_probability_source": "blend",
          "hero_probability_observed_at": "2026-11-15T19:59:45Z",
          "espn": {
            "period": "2nd",
            "game_clock": "6:42",
            "broadcast": "ESPN"
          },
          "win_probability_sources": {
            "betting": { "value": 0.58, "display_name": "Sportsbooks" },
            "kalshi": { "value": 0.58, "display_name": "Kalshi" }
          }
        }
        """
        let dec = JSONDecoder()
        dec.keyDecodingStrategy = .convertFromSnakeCase
        return try dec.decode(EventDetail.self, from: Data(json.utf8))
    }

    private func makeWidgetArt(away: TeamSpec, home: TeamSpec) -> SavedWidgetArt12466 {
        SavedWidgetArt12466(
            away: .init(short: away.abbr, primaryHex: away.primary, secondaryHex: away.secondary, logoURL: nil),
            home: .init(short: home.abbr, primaryHex: home.primary, secondaryHex: home.secondary, logoURL: nil)
        )
    }

    // MARK: - Cross-Surface Contract Tests

    func testKansasAtDukeSwitchesAwayToCrimsonAcrossCardsHeadlinesAndWidgets() throws {
        let feedEvent = try makeFeedEvent(id: 19701, away: kansas, home: duke)
        let sportsRow = EventCardView(event: feedEvent, reason: nil).barColorHexes
        let discoverCard = NativeEventDiscoverCard(
            event: feedEvent,
            feedContext: nil,
            expandedContext: nil,
            navigationPath: .constant(NavigationPath())
        ).barColorHexes
        let widgetArt = makeWidgetArt(away: kansas, home: duke)
        let widgetLight = widgetArt.barHexes(surfaceLuminance: SavedWidgetArt12466.lightSurfaceLuminance)
        let widgetFills = widgetArt.fillHexes()

        for (surface, pair) in [
            ("EventCardView", sportsRow),
            ("NativeEventDiscoverCard", discoverCard),
            ("SavedWidgetArt12466.light", widgetLight),
            ("SavedWidgetArt12466.fills", widgetFills),
        ] {
            XCTAssertEqual(pair.away.uppercased(), "#E8000D", "\(surface): Kansas should switch to crimson #E8000D")
            XCTAssertEqual(pair.home.uppercased(), "#00539B", "\(surface): Duke should keep #00539B")
        }
    }

    func testGonzagaAtDukeSwitchesAwayToRedSecondaryOrSlateGreyWhenAbsent() throws {
        let feedEvent = try makeFeedEvent(id: 19702, away: gonzaga, home: duke)
        let sportsRow = EventCardView(event: feedEvent, reason: nil).barColorHexes
        let discoverCard = NativeEventDiscoverCard(
            event: feedEvent,
            feedContext: nil,
            expandedContext: nil,
            navigationPath: .constant(NavigationPath())
        ).barColorHexes
        let widgetLight = makeWidgetArt(away: gonzaga, home: duke)
            .barHexes(surfaceLuminance: SavedWidgetArt12466.lightSurfaceLuminance)

        for (surface, pair) in [
            ("EventCardView", sportsRow),
            ("NativeEventDiscoverCard", discoverCard),
            ("SavedWidgetArt12466.light", widgetLight),
        ] {
            XCTAssertEqual(pair.away.uppercased(), "#C8102E", "\(surface): Gonzaga navy vs Duke blue switches away to #C8102E")
            XCTAssertEqual(pair.home.uppercased(), "#00539B", "\(surface): Duke keeps #00539B")
        }

        // When away holds no usable secondary (#FFFFFF or nil), away switches to slate grey (#64748B).
        let gonzagaNoSec = TeamSpec(name: "Gonzaga", abbr: "GONZ", primary: "#041E42", secondary: nil, record: "4-0")
        let noSecFeed = try makeFeedEvent(id: 19703, away: gonzagaNoSec, home: duke)
        XCTAssertEqual(EventCardView(event: noSecFeed, reason: nil).barColorHexes.away, ProbabilityBarPalette.awayDefault)

        let ukFeed = try makeFeedEvent(id: 19704, away: kentucky, home: duke)
        let ukSports = EventCardView(event: ukFeed, reason: nil).barColorHexes
        let ukDiscover = NativeEventDiscoverCard(
            event: ukFeed,
            feedContext: nil,
            expandedContext: nil,
            navigationPath: .constant(NavigationPath())
        ).barColorHexes
        let ukWidget = makeWidgetArt(away: kentucky, home: duke)
            .barHexes(surfaceLuminance: SavedWidgetArt12466.lightSurfaceLuminance)
        for pair in [ukSports, ukDiscover, ukWidget] {
            XCTAssertEqual(pair.away, ProbabilityBarPalette.awayDefault)
            XCTAssertEqual(pair.home.uppercased(), "#00539B")
        }

        // Same-family secondary (UNC navy #13294B vs Duke #00539B) is also rejected -> slate grey (#64748B).
        let uncFeed = try makeFeedEvent(id: 19705, away: unc, home: duke)
        XCTAssertEqual(EventCardView(event: uncFeed, reason: nil).barColorHexes.away, ProbabilityBarPalette.awayDefault)
    }

    func testControlRedAgainstBlueDoesNotChangeEitherTeamsColour() throws {
        let feedEvent = try makeFeedEvent(id: 19706, away: alabama, home: duke)
        let sportsRow = EventCardView(event: feedEvent, reason: nil).barColorHexes
        let discoverCard = NativeEventDiscoverCard(
            event: feedEvent,
            feedContext: nil,
            expandedContext: nil,
            navigationPath: .constant(NavigationPath())
        ).barColorHexes
        let widgetLight = makeWidgetArt(away: alabama, home: duke)
            .barHexes(surfaceLuminance: SavedWidgetArt12466.lightSurfaceLuminance)

        for (surface, pair) in [
            ("EventCardView", sportsRow),
            ("NativeEventDiscoverCard", discoverCard),
            ("SavedWidgetArt12466.light", widgetLight),
        ] {
            XCTAssertEqual(pair.away.uppercased(), "#9E1B32", "\(surface): Alabama crimson must stay #9E1B32")
            XCTAssertEqual(pair.home.uppercased(), "#00539B", "\(surface): Duke royal blue must stay #00539B")
        }
    }

    // MARK: - 390 px Render Export

    func testRuling197TwoTeamSurfacesFitAt390AndExportContactSheet() throws {
        let cases: [(title: String, subtitle: String, id: Int, away: TeamSpec, home: TeamSpec)] = [
            (
                title: "1. Kansas at Duke — Two blues → Kansas secondary (#E8000D)",
                subtitle: "Away #0051BA + #E8000D · Home #00539B",
                id: 19711,
                away: kansas,
                home: duke
            ),
            (
                title: "2. Gonzaga at Duke — Navy vs royal blue → Gonzaga secondary (#C8102E)",
                subtitle: "Away #041E42 + #C8102E · Home #00539B",
                id: 19712,
                away: gonzaga,
                home: duke
            ),
            (
                title: "3. Kentucky at Duke — Unreadable #FFFFFF secondary → Slate grey (#64748B)",
                subtitle: "Away #0033A0 + #FFFFFF · Home #00539B",
                id: 19713,
                away: kentucky,
                home: duke
            ),
            (
                title: "4. Control: Alabama at Duke — Red vs blue → Unchanged (#9E1B32 / #00539B)",
                subtitle: "Away #9E1B32 · Home #00539B",
                id: 19714,
                away: alabama,
                home: duke
            ),
        ]

        struct MatchupSection: View {
            let title: String
            let subtitle: String
            let headlineCard: EventSportHeadlineCard12472
            let feedEvent: FeedEventData
            let awayColor: Color
            let homeColor: Color

            var body: some View {
                VStack(alignment: .leading, spacing: 8) {
                    VStack(alignment: .leading, spacing: 2) {
                        Text(title)
                            .font(.caption.weight(.bold))
                            .foregroundStyle(Color(hex: "#111827"))
                        Text(subtitle)
                            .font(.caption2.monospaced())
                            .foregroundStyle(Color(hex: "#6B7280"))
                    }

                    headlineCard

                    DiscoverCompactSingleGameCard190CView(
                        event: feedEvent,
                        prematch: PrematchReading.resolve(
                            prematch: feedEvent.prematchOdds,
                            opening: feedEvent.openingOdds
                        ),
                        awayColor: awayColor,
                        homeColor: homeColor,
                        usesPictureLayout191A: false,
                        projectionAndSuspendedLines: { EmptyView() },
                        footerRow: { EmptyView() }
                    )
                    .padding(14)
                    .background(Color.white, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
                    .overlay(
                        RoundedRectangle(cornerRadius: 14, style: .continuous)
                            .strokeBorder(Color.black.opacity(0.08), lineWidth: 1)
                    )
                }
            }
        }

        var sections: [MatchupSection] = []
        for item in cases {
            let detail = try makeEventDetail(id: item.id, away: item.away, home: item.home)
            let feed = try makeFeedEvent(id: item.id, away: item.away, home: item.home)
            let model = try XCTUnwrap(
                EventSportHeadlines12472.resolve(
                    event: detail,
                    awayFullName: detail.awayTeam,
                    homeFullName: detail.homeTeam,
                    liveStatusText: "2nd · 6:42",
                    hasScore: true,
                    numberStreams: false,
                    now: fixedNow
                )
            )
            let pairColors = TeamTextContrast.cardColors(
                awayHex: detail.awayTeamData?.primaryColor,
                homeHex: detail.homeTeamData?.primaryColor,
                awaySecondaryHex: detail.awayTeamData?.secondaryColor
            )
            let headline = EventSportHeadlineCard12472(
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
            let cardHexes = EventCardView(event: feed, reason: nil).barColorHexes
            sections.append(
                MatchupSection(
                    title: item.title,
                    subtitle: item.subtitle,
                    headlineCard: headline,
                    feedEvent: feed,
                    awayColor: Color(hex: cardHexes.away),
                    homeColor: Color(hex: cardHexes.home)
                )
            )
        }

        let sheet = VStack(alignment: .leading, spacing: 18) {
            VStack(alignment: .leading, spacing: 3) {
                Text("Ruling 197 — Same Colour Family Switch (390 px)")
                    .font(.subheadline.weight(.bold))
                    .foregroundStyle(Color(hex: "#111827"))
                Text("Game-page headline + Discover/Sports game card · Away switches to secondary else #64748B")
                    .font(.caption2)
                    .foregroundStyle(Color(hex: "#6B7280"))
            }
            ForEach(Array(sections.enumerated()), id: \.offset) { _, section in
                section
            }
        }
        .padding(14)
        .frame(width: 390)
        .background(Color(hex: "#F3F4F6"))
        .environment(\.colorScheme, .light)

        let renderer = ImageRenderer(content: sheet)
        renderer.scale = 3.0
        let image = try XCTUnwrap(renderer.uiImage)
        XCTAssertEqual(Int(image.size.width.rounded()), 390)
        XCTAssertGreaterThan(image.size.height, 600)

        if let exportDir = ProcessInfo.processInfo.environment["RULING197_EXPORT_DIR"],
           !exportDir.isEmpty {
            let dirURL = URL(fileURLWithPath: exportDir, isDirectory: true)
            try FileManager.default.createDirectory(at: dirURL, withIntermediateDirectories: true)
            let data = try XCTUnwrap(image.pngData())
            try data.write(to: dirURL.appendingPathComponent("ruling-197-two-team-surfaces-390.png"))
        }
    }
}
