import SwiftUI
import UIKit
import XCTest
@testable import Bain_Luck

/// #13013 (`246: A` + `256: B`) — Verifies the Sports tab's four-block `"All"` order
/// (`Live Now` -> `Upcoming` with <=6h first -> `Just Happened` -> one horizontal `Futures` shelf)
/// and quiet-day shelf promotion.
@MainActor
final class SportsFuturesShelf13013Tests: XCTestCase {

    private func decodeItem(_ json: String) throws -> FeedItem {
        let dec = JSONDecoder()
        dec.keyDecodingStrategy = .convertFromSnakeCase
        return try dec.decode(FeedItem.self, from: Data(json.utf8))
    }

    private func decodeGrouped(_ json: String) throws -> GroupedFeedItem {
        let dec = JSONDecoder()
        dec.keyDecodingStrategy = .convertFromSnakeCase
        return try dec.decode(GroupedFeedItem.self, from: Data(json.utf8))
    }

    func testGameNightOrdersUpcomingWithinSixHoursFirstAndKeepsSingleFuturesShelfLast() throws {
        let now = try XCTUnwrap(ISO8601DateFormatter().date(from: "2026-11-19T01:00:00Z"))

        let laterTomorrow = try decodeItem("""
        {
          "type": "event",
          "score": 85,
          "data": {
            "id": 701,
            "sport": "americanfootball_nfl",
            "sport_name": "NFL",
            "status": "scheduled",
            "away_team": "Buffalo Bills",
            "home_team": "Houston Texans",
            "commence_time": "2026-11-19T10:15:00Z"
          }
        }
        """)
        let tonightNBA = try decodeItem("""
        {
          "type": "event",
          "score": 82,
          "data": {
            "id": 702,
            "sport": "basketball_nba",
            "sport_name": "NBA",
            "status": "scheduled",
            "away_team": "Boston Celtics",
            "home_team": "Denver Nuggets",
            "commence_time": "2026-11-19T03:00:00Z"
          }
        }
        """)
        let superBowlFuture = try decodeItem("""
        {
          "type": "futures",
          "score": 95,
          "data": {
            "id": 8801,
            "name": "Super Bowl LX Winner",
            "llm_sport_category": "football",
            "outcome_count": 32,
            "top_outcomes": [
              { "id": 1, "name": "Detroit Lions", "probability": 0.22, "rank": 1 },
              { "id": 2, "name": "Kansas City Chiefs", "probability": 0.16, "rank": 2 },
              { "id": 3, "name": "Buffalo Bills", "probability": 0.14, "rank": 3 }
            ]
          }
        }
        """)
        let rsmTournament = try decodeItem("""
        {
          "type": "tournament",
          "score": 88,
          "data": {
            "key": "pga_rsm_2026",
            "name": "The RSM Classic",
            "slug": "the-rsm-classic",
            "tour_label": "PGA Tour",
            "schedule_status": "live",
            "source_count": 2,
            "golfers": [
              { "name": "Ludvig Åberg", "probability": 0.18, "rank": 1 },
              { "name": "Maverick McNealy", "probability": 0.11, "rank": 2 },
              { "name": "Denny McCarthy", "probability": 0.08, "rank": 3 }
            ]
          }
        }
        """)
        let statProp = try decodeGrouped("""
        {
          "group_key": "prop:1",
          "type": "stat_prop",
          "player_name": "Nikola Jokic",
          "stat_category": "Points",
          "lines": [{ "id": 1, "name": "25+ Points", "probability": 0.54, "threshold_value": 25, "threshold_direction": "over" }]
        }
        """)
        let playoffLadder = try decodeGrouped("""
        {
          "group_key": "celtics",
          "type": "playoff_progression",
          "sport_key": "basketball_nba",
          "entity_name": "Boston Celtics",
          "stages": [
            { "id": 11, "label": "Make Playoffs", "probability": 0.96 },
            { "id": 12, "label": "Win East", "probability": 0.34 },
            { "id": 13, "label": "Win Finals", "probability": 0.19 }
          ]
        }
        """)

        // Upcoming puts <=6h game (702) ahead of 9.25h game (701).
        let orderedUp = SportsFuturesShelf13013.orderedUpcoming([laterTomorrow, tonightNBA], now: now)
        XCTAssertEqual(orderedUp.compactMap { $0.event?.id }, [702, 701])

        // Because a game starts within 6 hours, futures NEVER lead "All".
        XCTAssertFalse(SportsFuturesShelf13013.shelfLeads(live: [], upcoming: orderedUp, now: now))

        // Quiet day (only 9.25h game and no live games): futures shelf DOES lead "All".
        XCTAssertTrue(SportsFuturesShelf13013.shelfLeads(live: [], upcoming: [laterTomorrow], now: now))

        // Shelf combines futures + golf tournament + playoff ladder, dropping individual stat_prop cards.
        let shelf = SportsFuturesShelf13013.shelfCards(
            from: [superBowlFuture, rsmTournament],
            groupedItems: [statProp, playoffLadder],
            for: "all"
        )
        XCTAssertEqual(shelf.map(\.id), ["futures:8801", "tournament:pga_rsm_2026", "ladder:celtics"])
    }

    func testRendersShelfAnd256BProposalLooksWhenRequested() throws {
        if let shelfDir = ProcessInfo.processInfo.environment["RENDER_13013_SHELF_DIR"], !shelfDir.isEmpty {
            let dir = URL(fileURLWithPath: shelfDir, isDirectory: true)
            try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
            for (name, typeSize, h) in [
                ("13013-futures-shelf-default-390.png", DynamicTypeSize.large, CGFloat(820)),
                ("13013-futures-shelf-largest-text-390.png", DynamicTypeSize.xxxLarge, CGFloat(980)),
            ] {
                let light = try renderShelfPreview(scheme: .light, typeSize: typeSize, height: h)
                let dark = try renderShelfPreview(scheme: .dark, typeSize: typeSize, height: h)
                try XCTUnwrap(sideBySide(light, dark).pngData()).write(to: dir.appendingPathComponent(name))
            }
        }

        if let moreDir = ProcessInfo.processInfo.environment["RENDER_256B_PROPOSAL_DIR"], !moreDir.isEmpty {
            let dir = URL(fileURLWithPath: moreDir, isDirectory: true)
            try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
            for (name, typeSize, h) in [
                ("256b-iphone-minor-leagues-control-default-390.png", DynamicTypeSize.large, CGFloat(840)),
                ("256b-iphone-minor-leagues-control-largest-text-390.png", DynamicTypeSize.xxxLarge, CGFloat(1040)),
            ] {
                let light = try render256BProposalPreview(scheme: .light, typeSize: typeSize, height: h)
                let dark = try render256BProposalPreview(scheme: .dark, typeSize: typeSize, height: h)
                try XCTUnwrap(sideBySide(light, dark).pngData()).write(to: dir.appendingPathComponent(name))
            }
        }
    }

    private func renderShelfPreview(scheme: ColorScheme, typeSize: DynamicTypeSize, height: CGFloat) throws -> UIImage {
        let bg = scheme == .dark ? Color.black : Color(UIColor.systemGroupedBackground)
        let cardBg = scheme == .dark ? Color(UIColor.secondarySystemGroupedBackground) : Color.white

        let liveGame = try decodeItem("""
        {
          "type": "event",
          "score": 98,
          "data": {
            "id": 991,
            "sport": "basketball_nba",
            "sport_name": "NBA",
            "status": "live",
            "away_team": "Washington Wizards",
            "home_team": "Toronto Raptors",
            "away_score": 71,
            "home_score": 69,
            "commence_time": "2026-11-19T00:30:00Z",
            "espn": { "period": "Q3", "game_clock": "4:18" },
            "away_team_data": { "abbreviation": "WAS", "primary_color": "#002B5C" },
            "home_team_data": { "abbreviation": "TOR", "primary_color": "#CE1141" },
            "current_odds": { "away_probability": 0.491, "home_probability": 0.509 }
          }
        }
        """)
        let upcomingGame = try decodeItem("""
        {
          "type": "event",
          "score": 90,
          "data": {
            "id": 992,
            "sport": "icehockey_nhl",
            "sport_name": "NHL",
            "status": "scheduled",
            "away_team": "Colorado Avalanche",
            "home_team": "Utah Mammoth",
            "commence_time": "2026-11-19T03:00:00Z",
            "away_team_data": { "abbreviation": "COL", "primary_color": "#6F263D" },
            "home_team_data": { "abbreviation": "UTA", "primary_color": "#69B3E7" },
            "current_odds": { "away_probability": 0.58, "home_probability": 0.42, "away_rendered_percent": 58, "home_rendered_percent": 42 }
          }
        }
        """)
        let finishedGame = try decodeItem("""
        {
          "type": "event",
          "score": 84,
          "data": {
            "id": 993,
            "sport": "americanfootball_nfl",
            "sport_name": "NFL",
            "status": "completed",
            "away_team": "Buffalo Bills",
            "home_team": "Kansas City Chiefs",
            "away_score": 30,
            "home_score": 21,
            "commence_time": "2026-11-18T21:25:00Z",
            "away_team_data": { "abbreviation": "BUF", "primary_color": "#00338D" },
            "home_team_data": { "abbreviation": "KC", "primary_color": "#E31837" },
            "prematch_odds": { "away_probability": 0.52, "home_probability": 0.48, "away_rendered_percent": 52, "home_rendered_percent": 48 }
          }
        }
        """)
        let sbFuture = try decodeItem("""
        {
          "type": "futures",
          "score": 95,
          "data": {
            "id": 8801,
            "name": "Super Bowl LX Winner",
            "llm_sport_category": "football",
            "source": "both",
            "source_count": 2,
            "outcome_count": 32,
            "top_outcomes": [
              { "id": 1, "name": "Detroit Lions", "probability": 0.22, "rank": 1 },
              { "id": 2, "name": "Buffalo Bills", "probability": 0.16, "rank": 2 },
              { "id": 3, "name": "Kansas City Chiefs", "probability": 0.14, "rank": 3 }
            ]
          }
        }
        """)
        let rsm = try decodeItem("""
        {
          "type": "tournament",
          "score": 88,
          "data": {
            "key": "pga_rsm_2026",
            "name": "The RSM Classic",
            "slug": "the-rsm-classic",
            "tour_label": "PGA Tour",
            "schedule_status": "live",
            "source_count": 2,
            "golfers": [
              { "name": "Ludvig Åberg", "probability": 0.18, "rank": 1 },
              { "name": "Maverick McNealy", "probability": 0.11, "rank": 2 },
              { "name": "Denny McCarthy", "probability": 0.08, "rank": 3 }
            ]
          }
        }
        """)

        let liveEv = try XCTUnwrap(liveGame.event)
        let upcomingEv = try XCTUnwrap(upcomingGame.event)
        let finishedEv = try XCTUnwrap(finishedGame.event)
        let sbData = try XCTUnwrap(sbFuture.futures)
        let rsmData = try XCTUnwrap(rsm.tournament)

        let root = VStack(alignment: .leading, spacing: 10) {
            sectionHeader("Live Now", icon: "circle.fill", color: .red, count: 1)
                .padding(.top, 10)
            EventCardView(event: liveEv, reason: nil)
                .padding(.horizontal, 16).padding(.vertical, 4)
                .background(cardBg).clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))

            sectionHeader("Upcoming", icon: "calendar", color: .blue, count: 1)
            EventCardView(event: upcomingEv, reason: nil)
                .padding(.horizontal, 16).padding(.vertical, 4)
                .background(cardBg).clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))

            sectionHeader("Just Happened", icon: "clock.arrow.circlepath", color: .secondary, count: 1)
            EventCardView(event: finishedEv, reason: nil)
                .padding(.horizontal, 16).padding(.vertical, 4)
                .background(cardBg).clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))

            sectionHeader("Futures", icon: "chart.bar.fill", color: .purple, count: 2)
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(alignment: .top, spacing: 12) {
                    FuturesCardView(futures: sbData)
                        .padding(12).frame(width: 276, alignment: .topLeading)
                        .background(cardBg).clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
                        .overlay(RoundedRectangle(cornerRadius: 12, style: .continuous).stroke(Color.primary.opacity(0.07), lineWidth: 1))
                    SportsShelfTournamentCardView13013(tournament: rsmData)
                        .padding(12).frame(width: 276, alignment: .topLeading)
                        .background(cardBg).clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
                        .overlay(RoundedRectangle(cornerRadius: 12, style: .continuous).stroke(Color.primary.opacity(0.07), lineWidth: 1))
                }
            }
            .fixedSize(horizontal: false, vertical: true)
            Spacer(minLength: 0)
        }
        .padding(.horizontal, 20)
        .frame(width: 390, height: height, alignment: .topLeading)
        .background(bg)
        .environment(\.colorScheme, scheme)
        .environmentObject(PinManager())

        return snapshot(root, scheme: scheme, typeSize: typeSize, height: height)
    }

    private func render256BProposalPreview(scheme: ColorScheme, typeSize: DynamicTypeSize, height: CGFloat) throws -> UIImage {
        let bg = scheme == .dark ? Color.black : Color(UIColor.systemGroupedBackground)
        let cardBg = scheme == .dark ? Color(UIColor.secondarySystemGroupedBackground) : Color.white

        let majorLive = try decodeItem("""
        {
          "type": "event",
          "score": 98,
          "data": {
            "id": 991,
            "sport": "basketball_nba",
            "sport_name": "NBA",
            "status": "live",
            "away_team": "Memphis Grizzlies",
            "home_team": "Cleveland Cavaliers",
            "away_score": 113,
            "home_score": 112,
            "commence_time": "2026-11-19T00:00:00Z",
            "espn": { "period": "Q4", "game_clock": "1:12" },
            "away_team_data": { "abbreviation": "MEM", "primary_color": "#5D76A9" },
            "home_team_data": { "abbreviation": "CLE", "primary_color": "#860038" },
            "current_odds": { "away_probability": 0.518, "home_probability": 0.482 }
          }
        }
        """)
        let challengerTennis = try decodeItem("""
        {
          "type": "event",
          "score": 76,
          "data": {
            "id": 15350873,
            "sport": "tennis_atp",
            "sport_name": "ATP",
            "status": "live",
            "away_team": "Tristan Boyer",
            "home_team": "Genaro Alberto Olivieri",
            "commence_time": "2026-11-18T22:00:00Z",
            "current_odds": { "away_probability": 0.624, "home_probability": 0.376 }
          }
        }
        """)
        let brasileiraoLive = try decodeItem("""
        {
          "type": "event",
          "score": 74,
          "data": {
            "id": 995,
            "sport": "soccer_brazil_campeonato",
            "sport_name": "Brasileirão",
            "status": "live",
            "away_team": "Palmeiras",
            "home_team": "Botafogo",
            "away_score": 1,
            "home_score": 1,
            "commence_time": "2026-11-19T00:30:00Z",
            "espn": { "game_clock": "68'" },
            "current_odds": {
              "away_probability": 0.31,
              "draw_probability": 0.36,
              "home_probability": 0.33
            }
          }
        }
        """)

        let majorLiveEv = try XCTUnwrap(majorLive.event)
        let challengerEv = try XCTUnwrap(challengerTennis.event)
        let brasileiraoEv = try XCTUnwrap(brasileiraoLive.event)

        let root = VStack(alignment: .leading, spacing: 12) {
            Text("256: B · Collapsed (bottom of Live Now)")
                .font(.caption.weight(.semibold))
                .foregroundStyle(.secondary)
                .padding(.top, 12)

            VStack(spacing: 0) {
                EventCardView(event: majorLiveEv, reason: nil)
                    .padding(.horizontal, 16).padding(.vertical, 4)
                Divider().padding(.leading, 16)
                HStack(alignment: .center, spacing: 8) {
                    VStack(alignment: .leading, spacing: 2) {
                        Text("6 more live games")
                            .font(.subheadline.weight(.semibold))
                            .foregroundStyle(.primary)
                        Text("Challenger tennis, Brasileirão, AHL")
                            .font(.caption)
                            .foregroundStyle(DS.textSecondaryReadable)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                    Spacer(minLength: 8)
                    Image(systemName: "chevron.down")
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(DS.textSecondaryReadable)
                }
                .padding(.horizontal, 16)
                .padding(.vertical, 11)
            }
            .background(cardBg)
            .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))

            Text("256: B · Opened inline (tapped)")
                .font(.caption.weight(.semibold))
                .foregroundStyle(.secondary)
                .padding(.top, 4)

            VStack(spacing: 0) {
                HStack(spacing: 8) {
                    Text("6 more live games · Challenger tennis, Brasileirão, AHL")
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(DS.textSecondaryReadable)
                        .fixedSize(horizontal: false, vertical: true)
                    Spacer(minLength: 8)
                    HStack(spacing: 4) {
                        Text("Hide")
                        Image(systemName: "chevron.up")
                    }
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.blue)
                    .fixedSize()
                }
                .padding(.horizontal, 16)
                .padding(.vertical, 10)
                Divider().padding(.leading, 16)
                EventCardView(event: challengerEv, reason: nil)
                    .padding(.horizontal, 16).padding(.vertical, 4)
                Divider().padding(.leading, 16)
                EventCardView(event: brasileiraoEv, reason: nil)
                    .padding(.horizontal, 16).padding(.vertical, 4)
            }
            .background(cardBg)
            .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))

            Spacer(minLength: 0)
        }
        .padding(.horizontal, 20)
        .frame(width: 390, height: height, alignment: .topLeading)
        .background(bg)
        .environment(\.colorScheme, scheme)
        .environmentObject(PinManager())

        return snapshot(root, scheme: scheme, typeSize: typeSize, height: height)
    }

    private func sectionHeader(_ title: String, icon: String, color: Color, count: Int) -> some View {
        HStack(spacing: 6) {
            Label(title, systemImage: icon)
                .foregroundStyle(color)
                .font(.subheadline.weight(.semibold))
            Text("\(count)")
                .font(.caption2.weight(.medium))
                .foregroundStyle(DS.textSecondaryReadable)
                .padding(.horizontal, 5)
                .padding(.vertical, 1)
                .background(Color.secondary.opacity(0.12))
                .clipShape(Capsule())
        }
    }

    private func snapshot<V: View>(_ view: V, scheme: ColorScheme, typeSize: DynamicTypeSize, height: CGFloat) -> UIImage {
        let host = hostForMeasurement(view, at: typeSize)
        host.overrideUserInterfaceStyle = scheme == .dark ? .dark : .light
        let scene = UIApplication.shared.connectedScenes.compactMap({ $0 as? UIWindowScene }).first
        let window: UIWindow = scene.map { UIWindow(windowScene: $0) } ?? UIWindow(frame: CGRect(x: 0, y: 0, width: 390, height: height))
        window.frame = CGRect(x: 0, y: 0, width: 390, height: height)
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
            RunLoop.current.run(until: Date().addingTimeInterval(0.03))
        }
        let fmt = UIGraphicsImageRendererFormat()
        fmt.scale = 2.0
        fmt.opaque = true
        return UIGraphicsImageRenderer(size: CGSize(width: 390, height: height), format: fmt).image { _ in
            _ = host.view.drawHierarchy(in: host.view.bounds, afterScreenUpdates: true)
        }
    }

    private func sideBySide(_ left: UIImage, _ right: UIImage) -> UIImage {
        let gap: CGFloat = 16
        let size = CGSize(width: left.size.width + right.size.width + gap, height: max(left.size.height, right.size.height))
        let fmt = UIGraphicsImageRendererFormat()
        fmt.scale = 2.0
        fmt.opaque = true
        return UIGraphicsImageRenderer(size: size, format: fmt).image { ctx in
            UIColor(white: 0.12, alpha: 1.0).setFill()
            ctx.fill(CGRect(origin: .zero, size: size))
            left.draw(at: .zero)
            right.draw(at: CGPoint(x: left.size.width + gap, y: 0))
        }
    }
}
