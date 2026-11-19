import SwiftUI
import UIKit
import XCTest
@testable import Bain_Luck

/// #13013 (`246: A` + `264: A`) — Sports tab pills ordered into three groups
/// (`game today` → `in season with nothing today` → `out of season`), with one
/// fixed league order (`NFL, NBA, MLB, NHL, NCAAF, NCAAB, Soccer, Tennis, Golf`)
/// inside each group, no ordering by live-game count, and zero movement when a
/// game goes live or finishes.
@MainActor
final class SportsTabPillOrder13013Tests: XCTestCase {

    private func decodeItem(_ json: String) throws -> FeedItem {
        let dec = JSONDecoder()
        dec.keyDecodingStrategy = .convertFromSnakeCase
        return try dec.decode(FeedItem.self, from: Data(json.utf8))
    }

    private func eventItem(id: Int, sport: String, status: String, commenceISO: String) throws -> FeedItem {
        try decodeItem("""
        {
          "type": "event",
          "score": 90,
          "data": {
            "id": \(id),
            "sport": "\(sport)",
            "status": "\(status)",
            "home_team": "Home \(id)",
            "away_team": "Away \(id)",
            "commence_time": "\(commenceISO)"
          }
        }
        """)
    }

    private var easternCalendar: Calendar {
        var cal = Calendar(identifier: .gregorian)
        cal.timeZone = TimeZone(identifier: "America/New_York")!
        return cal
    }

    func testNovemberGameNightUsesFixedLeagueOrderInsideGroupsAndNeverOrdersByLiveCount() throws {
        let cal = easternCalendar
        // Thu Nov 19, 2026 at 7:30 PM ET (2026-11-20T00:30:00Z)
        let now = try XCTUnwrap(ISO8601DateFormatter().date(from: "2026-11-20T00:30:00Z"))

        let items: [FeedItem] = [
            // 4 NCAAB live games — must NOT jump ahead of NFL (scheduled today) or NBA/NHL
            try eventItem(id: 101, sport: "basketball_ncaab", status: "live", commenceISO: "2026-11-19T23:30:00Z"),
            try eventItem(id: 102, sport: "basketball_ncaab", status: "live", commenceISO: "2026-11-20T00:00:00Z"),
            try eventItem(id: 103, sport: "basketball_wncaab", status: "live", commenceISO: "2026-11-20T00:15:00Z"),
            try eventItem(id: 104, sport: "basketball_ncaab", status: "live", commenceISO: "2026-11-20T00:20:00Z"),
            // 2 NBA live games
            try eventItem(id: 201, sport: "basketball_nba", status: "live", commenceISO: "2026-11-20T00:00:00Z"),
            try eventItem(id: 202, sport: "basketball_nba", status: "live", commenceISO: "2026-11-20T00:10:00Z"),
            // 1 NHL live + 1 NHL scheduled tonight
            try eventItem(id: 301, sport: "icehockey_nhl", status: "live", commenceISO: "2026-11-20T00:00:00Z"),
            try eventItem(id: 302, sport: "icehockey_nhl", status: "scheduled", commenceISO: "2026-11-20T03:00:00Z"),
            // 1 Tennis match just finished earlier today
            try eventItem(id: 401, sport: "tennis_atp", status: "completed", commenceISO: "2026-11-19T18:00:00Z"),
            // 1 NFL Thursday Night Football scheduled today at 8:15 PM ET (2026-11-20T01:15:00Z)
            try eventItem(id: 501, sport: "americanfootball_nfl", status: "scheduled", commenceISO: "2026-11-20T01:15:00Z"),
            // MLB Championship futures card alone does NOT count as a game on today
            try decodeItem("""
            {
              "type": "futures",
              "score": 70,
              "data": { "id": 9901, "name": "2027 World Series Winner", "llm_sport_category": "baseball" }
            }
            """),
        ]

        // Group 0 (game today): NFL, NBA, NHL, NCAAB, Tennis
        // Group 1 (in season, nothing today): NCAAF, Soccer, Golf
        // Group 2 (out of season): MLB
        let ordered = SportFilterChips.orderedCategories(items: items, now: now, calendar: cal).map(\.name)
        XCTAssertEqual(
            ordered,
            ["All", "NFL", "NBA", "NHL", "NCAAB", "Tennis", "NCAAF", "Soccer", "Golf", "MLB"]
        )
    }

    func testSportPillDoesNotMoveWhenScheduledGameGoesLiveOrFinishes() throws {
        let cal = easternCalendar
        let now = try XCTUnwrap(ISO8601DateFormatter().date(from: "2026-11-20T01:20:00Z"))

        for nflStatus in ["scheduled", "live", "completed"] {
            let items: [FeedItem] = [
                try eventItem(id: 101, sport: "basketball_ncaab", status: "live", commenceISO: "2026-11-20T00:00:00Z"),
                try eventItem(id: 201, sport: "basketball_nba", status: "live", commenceISO: "2026-11-20T00:30:00Z"),
                try eventItem(id: 501, sport: "americanfootball_nfl", status: nflStatus, commenceISO: "2026-11-20T01:15:00Z"),
            ]
            let ordered = SportFilterChips.orderedCategories(items: items, now: now, calendar: cal).map(\.name)
            XCTAssertEqual(
                ordered,
                ["All", "NFL", "NBA", "NCAAB", "NHL", "NCAAF", "Soccer", "Tennis", "Golf", "MLB"],
                "Pill order must stay identical when NFL transitions across status=\(nflStatus)"
            )
        }
    }

    func testMidJulySummerSlatePutsMLBAheadAndWinterOffseasonSportsLastInFixedOrder() throws {
        let cal = easternCalendar
        // Wed Jul 22, 2026 at 7:30 PM ET (2026-07-22T23:30:00Z)
        let now = try XCTUnwrap(ISO8601DateFormatter().date(from: "2026-07-22T23:30:00Z"))

        let items: [FeedItem] = [
            try eventItem(id: 601, sport: "baseball_mlb", status: "live", commenceISO: "2026-07-22T23:05:00Z"),
            try eventItem(id: 602, sport: "baseball_mlb", status: "live", commenceISO: "2026-07-22T23:10:00Z"),
            try eventItem(id: 701, sport: "soccer_usa_mls", status: "scheduled", commenceISO: "2026-07-23T01:30:00Z"),
        ]

        // Group 0 (game today): MLB, Soccer
        // Group 1 (in season, nothing today): Tennis, Golf
        // Group 2 (out of season, fixed order): NFL, NBA, NHL, NCAAF, NCAAB
        let ordered = SportFilterChips.orderedCategories(items: items, now: now, calendar: cal).map(\.name)
        XCTAssertEqual(
            ordered,
            ["All", "MLB", "Soccer", "Tennis", "Golf", "NFL", "NBA", "NHL", "NCAAF", "NCAAB"]
        )
    }

    func testEmptyPreloadItemsInNovemberStillPlaceOffseasonMLBLastInFixedOrder() throws {
        let cal = easternCalendar
        let now = try XCTUnwrap(ISO8601DateFormatter().date(from: "2026-11-19T14:00:00Z"))

        let ordered = SportFilterChips.orderedCategories(items: [], now: now, calendar: cal).map(\.name)
        XCTAssertEqual(
            ordered,
            ["All", "NFL", "NBA", "NHL", "NCAAF", "NCAAB", "Soccer", "Tennis", "Golf", "MLB"]
        )
    }

    func testLiveGolfTournamentLiftsGolfIntoGameTodayGroupWithoutChangingCategoryMatches() throws {
        let cal = easternCalendar
        let now = try XCTUnwrap(ISO8601DateFormatter().date(from: "2026-11-19T19:00:00Z"))

        let tournamentItem = try decodeItem("""
        {
          "type": "tournament",
          "score": 88,
          "data": {
            "key": "pga_rsm_classic_2026",
            "name": "The RSM Classic",
            "schedule_status": "live",
            "commence_time": "2026-11-19T12:00:00Z",
            "golfers": []
          }
        }
        """)
        let golf = try XCTUnwrap(sportCategories.first { $0.id == "golf" })
        // SportCategory.matches stays unchanged so FeedViewModel.filteredItems(for: "golf") does not alter list membership.
        XCTAssertFalse(golf.matches(tournamentItem))

        let items: [FeedItem] = [
            tournamentItem,
            try eventItem(id: 801, sport: "basketball_nba", status: "scheduled", commenceISO: "2026-11-20T00:30:00Z"),
        ]
        let ordered = SportFilterChips.orderedCategories(items: items, now: now, calendar: cal).map(\.name)
        // Both NBA (scheduled today) and Golf (live tournament today) are in Group 0, ordered by fixed league order (NBA before Golf), ahead of idle in-season sports and offseason MLB.
        XCTAssertEqual(ordered.prefix(3), ["All", "NBA", "Golf"])
        XCTAssertEqual(ordered.last, "MLB")
    }

    func testRenders390PtLightAndDarkLooksWhenRequested() throws {
        guard let outDir = ProcessInfo.processInfo.environment["RENDER_13013_PILLS_DIR"],
              !outDir.isEmpty else { return }
        let dir = URL(fileURLWithPath: outDir, isDirectory: true)
        try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)

        let cal = easternCalendar
        let novNow = try XCTUnwrap(ISO8601DateFormatter().date(from: "2026-11-20T00:30:00Z"))
        let julNow = try XCTUnwrap(ISO8601DateFormatter().date(from: "2026-07-22T23:30:00Z"))

        let novItems: [FeedItem] = [
            try eventItem(id: 101, sport: "basketball_ncaab", status: "live", commenceISO: "2026-11-19T23:30:00Z"),
            try eventItem(id: 102, sport: "basketball_ncaab", status: "live", commenceISO: "2026-11-20T00:00:00Z"),
            try eventItem(id: 103, sport: "basketball_wncaab", status: "live", commenceISO: "2026-11-20T00:15:00Z"),
            try eventItem(id: 201, sport: "basketball_nba", status: "live", commenceISO: "2026-11-20T00:00:00Z"),
            try eventItem(id: 202, sport: "basketball_nba", status: "live", commenceISO: "2026-11-20T00:10:00Z"),
            try eventItem(id: 301, sport: "icehockey_nhl", status: "live", commenceISO: "2026-11-20T00:00:00Z"),
            try eventItem(id: 401, sport: "tennis_atp", status: "completed", commenceISO: "2026-11-19T18:00:00Z"),
            try eventItem(id: 501, sport: "americanfootball_nfl", status: "scheduled", commenceISO: "2026-11-20T01:15:00Z"),
        ]
        let julItems: [FeedItem] = [
            try eventItem(id: 601, sport: "baseball_mlb", status: "live", commenceISO: "2026-07-22T23:05:00Z"),
            try eventItem(id: 602, sport: "baseball_mlb", status: "live", commenceISO: "2026-07-22T23:10:00Z"),
            try eventItem(id: 701, sport: "soccer_usa_mls", status: "scheduled", commenceISO: "2026-07-23T01:30:00Z"),
        ]

        let novOrdered = SportFilterChips.orderedCategories(items: novItems, now: novNow, calendar: cal)
        let julOrdered = SportFilterChips.orderedCategories(items: julItems, now: julNow, calendar: cal)

        for (fileName, typeSize, height) in [
            ("13013-pill-order-default-390.png", DynamicTypeSize.large, CGFloat(540)),
            ("13013-pill-order-largest-text-390.png", DynamicTypeSize.xxxLarge, CGFloat(660)),
        ] {
            let light = renderSheet(novItems: novItems, novNow: novNow, novOrdered: novOrdered, julItems: julItems, julNow: julNow, julOrdered: julOrdered, cal: cal, scheme: .light, typeSize: typeSize, height: height)
            let dark = renderSheet(novItems: novItems, novNow: novNow, novOrdered: novOrdered, julItems: julItems, julNow: julNow, julOrdered: julOrdered, cal: cal, scheme: .dark, typeSize: typeSize, height: height)
            let combined = sideBySide(light, dark)
            try XCTUnwrap(combined.pngData()).write(to: dir.appendingPathComponent(fileName))
        }
    }

    @ViewBuilder
    private func wrappedChipsPreview(_ ordered: [SportCategory]) -> some View {
        let rows: [[SportCategory]] = [
            Array(ordered.prefix(4)),
            Array(ordered.dropFirst(4).prefix(3)),
            Array(ordered.dropFirst(7)),
        ]
        VStack(alignment: .leading, spacing: 6) {
            ForEach(0..<rows.count, id: \.self) { rowIdx in
                HStack(spacing: 6) {
                    ForEach(rows[rowIdx]) { cat in
                        let isAll = cat.id == "all"
                        HStack(spacing: 4) {
                            if !isAll {
                                Image(systemName: SportFilterChips.chipIcon(for: cat.id))
                                    .font(.system(size: 10))
                            }
                            Text(cat.name)
                                .font(.caption)
                                .fontWeight(isAll ? .semibold : .regular)
                        }
                        .padding(.horizontal, 12)
                        .padding(.vertical, 6)
                        .background(isAll ? Color.blue.opacity(0.15) : Color.secondary.opacity(0.08))
                        .foregroundStyle(isAll ? .blue : .primary)
                        .clipShape(Capsule())
                    }
                }
            }
        }
        .padding(.horizontal, 16)
    }

    private func renderSheet(
        novItems: [FeedItem],
        novNow: Date,
        novOrdered: [SportCategory],
        julItems: [FeedItem],
        julNow: Date,
        julOrdered: [SportCategory],
        cal: Calendar,
        scheme: ColorScheme,
        typeSize: DynamicTypeSize,
        height: CGFloat
    ) -> UIImage {
        let bg = scheme == .dark ? Color.black : Color(UIColor.systemGroupedBackground)
        let view = VStack(alignment: .leading, spacing: 14) {
            Text("Sports Tab Pills · November Game Night (264: A)")
                .font(.caption.weight(.semibold))
                .foregroundStyle(.secondary)
                .padding(.horizontal, 16)
                .padding(.top, 14)

            SportFilterChips(selectedCategory: .constant("all"), items: novItems, now: novNow, calendar: cal)
                .fixedSize(horizontal: false, vertical: true)

            Text("10-pill order (game today → in-season → out-of-season):")
                .font(.caption2)
                .foregroundStyle(.secondary)
                .padding(.horizontal, 16)
            wrappedChipsPreview(novOrdered)

            Divider().padding(.horizontal, 16).padding(.vertical, 4)

            Text("Sports Tab Pills · July Summer Night (264: A)")
                .font(.caption.weight(.semibold))
                .foregroundStyle(.secondary)
                .padding(.horizontal, 16)

            SportFilterChips(selectedCategory: .constant("all"), items: julItems, now: julNow, calendar: cal)
                .fixedSize(horizontal: false, vertical: true)

            Text("10-pill order (MLB/Soccer today → Tennis/Golf → winter offseason):")
                .font(.caption2)
                .foregroundStyle(.secondary)
                .padding(.horizontal, 16)
            wrappedChipsPreview(julOrdered)

            Spacer(minLength: 0)
        }
        .frame(width: 390, height: height, alignment: .topLeading)
        .background(bg)
        .environment(\.colorScheme, scheme)

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
        for _ in 0..<4 {
            host.view.setNeedsLayout()
            host.view.layoutIfNeeded()
            RunLoop.current.run(until: Date().addingTimeInterval(0.02))
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
