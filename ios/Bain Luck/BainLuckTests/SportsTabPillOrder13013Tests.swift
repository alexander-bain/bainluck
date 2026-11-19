import SwiftUI
import UIKit
import XCTest
@testable import Bain_Luck

/// #13013 (`246: A`) — Sports tab pills ordered by what is on today, with out-of-season sports last.
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

    func testNovemberGameNightOrdersLiveThenTodayThenQuietInSeasonWithOffseasonMLBLast() throws {
        var utc = Calendar(identifier: .gregorian)
        utc.timeZone = TimeZone(secondsFromGMT: 0)!
        let now = try XCTUnwrap(ISO8601DateFormatter().date(from: "2026-11-19T02:00:00Z"))

        let items: [FeedItem] = [
            // 3 NCAAB live
            try eventItem(id: 101, sport: "basketball_ncaab", status: "live", commenceISO: "2026-11-19T00:30:00Z"),
            try eventItem(id: 102, sport: "basketball_ncaab", status: "live", commenceISO: "2026-11-19T01:00:00Z"),
            try eventItem(id: 103, sport: "basketball_wncaab", status: "live", commenceISO: "2026-11-19T01:15:00Z"),
            // 2 NBA live (+ duplicate ID from backfill must not double count)
            try eventItem(id: 201, sport: "basketball_nba", status: "live", commenceISO: "2026-11-19T00:30:00Z"),
            try eventItem(id: 201, sport: "basketball_nba", status: "live", commenceISO: "2026-11-19T00:30:00Z"),
            try eventItem(id: 202, sport: "basketball_nba", status: "live", commenceISO: "2026-11-19T01:00:00Z"),
            // 1 NHL live + 1 NHL upcoming tonight
            try eventItem(id: 301, sport: "icehockey_nhl", status: "live", commenceISO: "2026-11-19T00:00:00Z"),
            try eventItem(id: 302, sport: "icehockey_nhl", status: "scheduled", commenceISO: "2026-11-19T03:00:00Z"),
            // 2 Tennis upcoming today (no live)
            try eventItem(id: 401, sport: "tennis_atp", status: "scheduled", commenceISO: "2026-11-19T14:00:00Z"),
            try eventItem(id: 402, sport: "tennis_wta", status: "scheduled", commenceISO: "2026-11-19T16:00:00Z"),
            // 1 NFL Thursday Night Football within 24h
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

        let ordered = SportFilterChips.orderedCategories(items: items, now: now, calendar: utc).map(\.name)
        XCTAssertEqual(
            ordered,
            ["All", "NCAAB", "NBA", "NHL", "Tennis", "NFL", "NCAAF", "Soccer", "Golf", "MLB"]
        )
    }

    func testMidJulySummerSlatePutsMLBAheadAndWinterOffseasonSportsLast() throws {
        var utc = Calendar(identifier: .gregorian)
        utc.timeZone = TimeZone(secondsFromGMT: 0)!
        let now = try XCTUnwrap(ISO8601DateFormatter().date(from: "2026-07-22T23:30:00Z"))

        let items: [FeedItem] = [
            try eventItem(id: 601, sport: "baseball_mlb", status: "live", commenceISO: "2026-07-22T23:05:00Z"),
            try eventItem(id: 602, sport: "baseball_mlb", status: "live", commenceISO: "2026-07-22T23:10:00Z"),
            try eventItem(id: 701, sport: "soccer_usa_mls", status: "scheduled", commenceISO: "2026-07-23T01:30:00Z"),
        ]

        let ordered = SportFilterChips.orderedCategories(items: items, now: now, calendar: utc).map(\.name)
        XCTAssertEqual(
            ordered,
            ["All", "MLB", "Soccer", "Tennis", "Golf", "NBA", "NFL", "NCAAF", "NCAAB", "NHL"]
        )
    }

    func testEmptyPreloadItemsInNovemberStillPlaceOffseasonMLBLast() throws {
        var utc = Calendar(identifier: .gregorian)
        utc.timeZone = TimeZone(secondsFromGMT: 0)!
        let now = try XCTUnwrap(ISO8601DateFormatter().date(from: "2026-11-19T14:00:00Z"))

        let ordered = SportFilterChips.orderedCategories(items: [], now: now, calendar: utc).map(\.name)
        XCTAssertEqual(ordered.first, "All")
        XCTAssertEqual(ordered.last, "MLB")
    }

    func testLiveGolfTournamentLiftsGolfPillWithoutChangingCategoryMatches() throws {
        var utc = Calendar(identifier: .gregorian)
        utc.timeZone = TimeZone(secondsFromGMT: 0)!
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
        let ordered = SportFilterChips.orderedCategories(items: items, now: now, calendar: utc).map(\.name)
        // Golf (1 live tournament -> tier 0) sits immediately after All, ahead of scheduled NBA (tier 1), with offseason MLB last.
        XCTAssertEqual(ordered.prefix(3), ["All", "Golf", "NBA"])
        XCTAssertEqual(ordered.last, "MLB")
    }

    func testRenders390PtLightAndDarkLooksWhenRequested() throws {
        guard let outDir = ProcessInfo.processInfo.environment["RENDER_13013_PILLS_DIR"],
              !outDir.isEmpty else { return }
        let dir = URL(fileURLWithPath: outDir, isDirectory: true)
        try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)

        var utc = Calendar(identifier: .gregorian)
        utc.timeZone = TimeZone(secondsFromGMT: 0)!
        let novNow = try XCTUnwrap(ISO8601DateFormatter().date(from: "2026-11-19T02:00:00Z"))
        let julNow = try XCTUnwrap(ISO8601DateFormatter().date(from: "2026-07-22T23:30:00Z"))

        let novItems: [FeedItem] = [
            try eventItem(id: 101, sport: "basketball_ncaab", status: "live", commenceISO: "2026-11-19T00:30:00Z"),
            try eventItem(id: 102, sport: "basketball_ncaab", status: "live", commenceISO: "2026-11-19T01:00:00Z"),
            try eventItem(id: 103, sport: "basketball_wncaab", status: "live", commenceISO: "2026-11-19T01:15:00Z"),
            try eventItem(id: 201, sport: "basketball_nba", status: "live", commenceISO: "2026-11-19T00:30:00Z"),
            try eventItem(id: 202, sport: "basketball_nba", status: "live", commenceISO: "2026-11-19T01:00:00Z"),
            try eventItem(id: 301, sport: "icehockey_nhl", status: "live", commenceISO: "2026-11-19T00:00:00Z"),
            try eventItem(id: 401, sport: "tennis_atp", status: "scheduled", commenceISO: "2026-11-19T14:00:00Z"),
            try eventItem(id: 501, sport: "americanfootball_nfl", status: "scheduled", commenceISO: "2026-11-20T01:15:00Z"),
        ]
        let julItems: [FeedItem] = [
            try eventItem(id: 601, sport: "baseball_mlb", status: "live", commenceISO: "2026-07-22T23:05:00Z"),
            try eventItem(id: 602, sport: "baseball_mlb", status: "live", commenceISO: "2026-07-22T23:10:00Z"),
            try eventItem(id: 701, sport: "soccer_usa_mls", status: "scheduled", commenceISO: "2026-07-23T01:30:00Z"),
        ]

        let novOrdered = SportFilterChips.orderedCategories(items: novItems, now: novNow, calendar: utc)
        let julOrdered = SportFilterChips.orderedCategories(items: julItems, now: julNow, calendar: utc)

        for (fileName, typeSize, height) in [
            ("13013-pill-order-default-390.png", DynamicTypeSize.large, CGFloat(540)),
            ("13013-pill-order-largest-text-390.png", DynamicTypeSize.xxxLarge, CGFloat(660)),
        ] {
            let light = renderSheet(novItems: novItems, novNow: novNow, novOrdered: novOrdered, julItems: julItems, julNow: julNow, julOrdered: julOrdered, scheme: .light, typeSize: typeSize, height: height)
            let dark = renderSheet(novItems: novItems, novNow: novNow, novOrdered: novOrdered, julItems: julItems, julNow: julNow, julOrdered: julOrdered, scheme: .dark, typeSize: typeSize, height: height)
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
        scheme: ColorScheme,
        typeSize: DynamicTypeSize,
        height: CGFloat
    ) -> UIImage {
        let bg = scheme == .dark ? Color.black : Color(UIColor.systemGroupedBackground)
        let view = VStack(alignment: .leading, spacing: 14) {
            Text("Sports Tab Pills · November Game Night")
                .font(.caption.weight(.semibold))
                .foregroundStyle(.secondary)
                .padding(.horizontal, 16)
                .padding(.top, 14)

            SportFilterChips(selectedCategory: .constant("all"), items: novItems, now: novNow)
                .fixedSize(horizontal: false, vertical: true)

            Text("Full 10-pill order (live → on today → in-season → MLB offseason last):")
                .font(.caption2)
                .foregroundStyle(.secondary)
                .padding(.horizontal, 16)
            wrappedChipsPreview(novOrdered)

            Divider().padding(.horizontal, 16).padding(.vertical, 4)

            Text("Sports Tab Pills · July Summer Night")
                .font(.caption.weight(.semibold))
                .foregroundStyle(.secondary)
                .padding(.horizontal, 16)

            SportFilterChips(selectedCategory: .constant("all"), items: julItems, now: julNow)
                .fixedSize(horizontal: false, vertical: true)

            Text("Full 10-pill order (MLB live + Soccer today → Tennis/Golf → winter offseason last):")
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
