import SwiftUI
#if canImport(UIKit)
import UIKit
import Vision
import XCTest
@testable import Bain_Luck

/// Overnight Item 9 — #11985 proof & enforcement:
/// 1. Scheduled Discover single-game cards print plain start times across every
///    window: `"In 22m"` (`< 1h`), `"Today 6:00 PM"`, `"Tomorrow 6:00 PM"`,
///    and `"Sun, Nov 15"` (`2+` days away, Ruling 182-A).
/// 2. Within each 20-card Discover page, at most one active/scheduled single-game
///    card per team keeps a seat unless BOTH games are live or within the hour
///    (`<= 3600s`); when a team has two non-imminent games on a page (such as
///    Magic @ Suns Tomorrow above Blazers @ Suns Today), the nearer game keeps
///    (or takes) the seat on that page and the later game yields to the next page,
///    without ever reordering frozen on-screen cards (#11984) or dropping items (#1091).
@MainActor
final class DiscoverStartTimeAndTeamSeat11985Tests: XCTestCase {

    private let pins = PinManager(
        defaults: UserDefaults(suiteName: "DiscoverStartTimeAndTeamSeat11985Tests")!,
        serverLoad: { PinsResponse(events: [], futures: []) },
        serverSync: { _, _, _ in }
    )

    private func decodeFeedItem(_ json: String) throws -> FeedItem {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(FeedItem.self, from: Data(json.utf8))
    }

    private func makeEventItem(
        id: Int,
        sport: String = "basketball_nba",
        sportName: String = "NBA",
        awayTeam: String,
        homeTeam: String,
        commenceTime: String,
        status: String = "scheduled",
        awayProb: Double = 0.44,
        homeProb: Double = 0.56,
        score: Double = 60
    ) throws -> FeedItem {
        try decodeFeedItem("""
        {
          "type": "event",
          "score": \(score),
          "reason": null,
          "headline": null,
          "data": {
            "id": \(id),
            "sport": "\(sport)",
            "sport_name": "\(sportName)",
            "away_team": "\(awayTeam)",
            "home_team": "\(homeTeam)",
            "commence_time": "\(commenceTime)",
            "status": "\(status)",
            "current_odds": {
              "away_probability": \(awayProb),
              "home_probability": \(homeProb),
              "away_rendered_percent": \(Int((awayProb * 100).rounded())),
              "home_rendered_percent": \(Int((homeProb * 100).rounded()))
            }
          }
        }
        """)
    }

    private func makeFuturesFiller(id: Int) throws -> FeedItem {
        try decodeFeedItem("""
        {
          "type": "futures",
          "score": 50,
          "reason": "Steady contender",
          "headline": null,
          "data": {
            "id": \(id),
            "name": "Market #\(id)",
            "sport": "politics",
            "category": "politics",
            "outcomes": [
              {"name": "Yes", "probability": 0.62},
              {"name": "No", "probability": 0.38}
            ]
          }
        }
        """)
    }

    // MARK: - 1. Start Time Proof Across Scheduled Windows (#11985 Half 1)

    func testScheduledDiscoverGameCardsPrintStartTimeAcrossCountdownTodayTomorrowAndFutureDate() throws {
        var cal = Calendar(identifier: .gregorian)
        cal.timeZone = TimeZone.current
        // Anchor at local 1:38 PM so +22m = "In 22m", 6:00 PM same day = "Today 6:00 PM",
        // 6:00 PM next day = "Tomorrow 6:00 PM", and +3 days = weekday + date.
        let nowComponents = DateComponents(year: 2026, month: 11, day: 14, hour: 13, minute: 38, second: 0)
        let fixedNow = try XCTUnwrap(cal.date(from: nowComponents))
        let iso = ISO8601DateFormatter()

        let in22m = iso.string(from: fixedNow.addingTimeInterval(22 * 60))
        let today6pm = iso.string(from: try XCTUnwrap(cal.date(bySettingHour: 18, minute: 0, second: 0, of: fixedNow)))
        let tomorrowBase = try XCTUnwrap(cal.date(byAdding: .day, value: 1, to: fixedNow))
        let tomorrow6pm = iso.string(from: try XCTUnwrap(cal.date(bySettingHour: 18, minute: 0, second: 0, of: tomorrowBase)))
        let threeDaysOut = iso.string(from: try XCTUnwrap(cal.date(byAdding: .day, value: 3, to: fixedNow)))

        XCTAssertEqual(
            StatusBadge.scheduledGameCardTimeText(commenceTime: in22m, startIsTbd: false, now: fixedNow),
            "In 22m"
        )
        let todayLabel = try XCTUnwrap(
            StatusBadge.scheduledGameCardTimeText(commenceTime: today6pm, startIsTbd: false, now: fixedNow)
        )
        XCTAssertTrue(todayLabel.hasPrefix("Today "), "Expected 'Today <clock>', got \(todayLabel)")
        XCTAssertTrue(todayLabel.contains("6:00"), "Expected 6:00 clock on Today card, got \(todayLabel)")

        let tomorrowLabel = try XCTUnwrap(
            StatusBadge.scheduledGameCardTimeText(commenceTime: tomorrow6pm, startIsTbd: false, now: fixedNow)
        )
        XCTAssertTrue(tomorrowLabel.hasPrefix("Tomorrow "), "Expected 'Tomorrow <clock>', got \(tomorrowLabel)")
        XCTAssertTrue(tomorrowLabel.contains("6:00"), "Expected 6:00 clock on Tomorrow card, got \(tomorrowLabel)")

        let futureLabel = try XCTUnwrap(
            StatusBadge.scheduledGameCardTimeText(commenceTime: threeDaysOut, startIsTbd: false, now: fixedNow)
        )
        XCTAssertTrue(futureLabel.contains("Nov 17"), "Expected future date per 182-A, got \(futureLabel)")
    }

    // MARK: - 2. One Game Per Team Per Page (#11985 Half 2)

    func testNearerGameTakesPageSeatWhenLaterGameRankedHigherOnPage() throws {
        let now = ISO8601DateFormatter().date(from: "2026-11-14T20:00:00Z")!

        // Alex's exact #11985 bug: Magic @ Suns (Tomorrow) ranked #3 above Suns vs Blazers (Today) ranked #9.
        let magicAtSunsTomorrow = try makeEventItem(
            id: 1001,
            awayTeam: "Orlando Magic",
            homeTeam: "Phoenix Suns",
            commenceTime: "2026-11-16T02:00:00Z",
            awayProb: 0.42,
            homeProb: 0.58,
            score: 88
        )
        let blazersAtSunsToday = try makeEventItem(
            id: 1002,
            awayTeam: "Portland Trail Blazers",
            homeTeam: "Phoenix Suns",
            commenceTime: "2026-11-15T02:00:00Z",
            awayProb: 0.29,
            homeProb: 0.71,
            score: 74
        )

        var rawPage: [DiscoverGroupedItem] = []
        for idx in 0..<24 {
            if idx == 2 {
                rawPage.append(.single(magicAtSunsTomorrow))
            } else if idx == 8 {
                rawPage.append(.single(blazersAtSunsToday))
            } else {
                rawPage.append(.single(try makeFuturesFiller(id: 2000 + idx)))
            }
        }

        let seated = DiscoverPageTeamSeat11985.seatItems(rawPage, now: now, pageSize: 20)
        XCTAssertEqual(seated.count, rawPage.count, "No card may ever be dropped (#1091)")

        let page1Ids = seated.prefix(20).map(\.id)
        let page2Ids = seated.dropFirst(20).map(\.id)

        XCTAssertTrue(page1Ids.contains("event-1002"), "Nearer Phoenix Suns game (Today) must hold the page-1 seat")
        XCTAssertFalse(page1Ids.contains("event-1001"), "Later Phoenix Suns game (Tomorrow) must yield its page-1 seat")
        XCTAssertTrue(page2Ids.contains("event-1001"), "Yielded Phoenix Suns game moves cleanly to page 2")
        XCTAssertEqual(page1Ids[2], "event-1002", "Nearer game takes the earlier Phoenix Suns seat on page 1")
    }

    func testBothGamesKeepPageSeatsWhenBothAreLiveOrWithinOneHour() throws {
        let now = ISO8601DateFormatter().date(from: "2026-11-14T20:00:00Z")!

        let liveGame = try makeEventItem(
            id: 1101,
            sport: "baseball_mlb",
            sportName: "MLB",
            awayTeam: "Chicago Cubs",
            homeTeam: "St. Louis Cardinals",
            commenceTime: "2026-11-14T18:10:00Z",
            status: "live",
            score: 90
        )
        let gameTwoIn40m = try makeEventItem(
            id: 1102,
            sport: "baseball_mlb",
            sportName: "MLB",
            awayTeam: "Chicago Cubs",
            homeTeam: "St. Louis Cardinals",
            commenceTime: "2026-11-14T20:40:00Z",
            status: "scheduled",
            score: 82
        )

        var rawPage: [DiscoverGroupedItem] = [.single(liveGame), .single(gameTwoIn40m)]
        for idx in 0..<22 {
            rawPage.append(.single(try makeFuturesFiller(id: 3000 + idx)))
        }

        let seated = DiscoverPageTeamSeat11985.seatItems(rawPage, now: now, pageSize: 20)
        let page1Ids = seated.prefix(20).map(\.id)
        XCTAssertTrue(page1Ids.contains("event-1101"))
        XCTAssertTrue(page1Ids.contains("event-1102"), "Both games are live/within the hour so both keep page-1 seats")
    }

    func testFrozenPrefixIsNeverReorderedUnderTheReader() throws {
        let now = ISO8601DateFormatter().date(from: "2026-11-14T20:00:00Z")!

        let frozenTomorrow = try makeEventItem(
            id: 1201,
            awayTeam: "Orlando Magic",
            homeTeam: "Phoenix Suns",
            commenceTime: "2026-11-16T02:00:00Z"
        )
        let newlyArrivedToday = try makeEventItem(
            id: 1202,
            awayTeam: "Portland Trail Blazers",
            homeTeam: "Phoenix Suns",
            commenceTime: "2026-11-15T02:00:00Z"
        )

        var items: [DiscoverGroupedItem] = [.single(frozenTomorrow)]
        for idx in 0..<5 {
            items.append(.single(try makeFuturesFiller(id: 4000 + idx)))
        }
        let frozenCount = items.count // 6 cards already painted on screen (#11984)
        items.append(.single(newlyArrivedToday))
        for idx in 0..<18 {
            items.append(.single(try makeFuturesFiller(id: 4100 + idx)))
        }

        let seated = DiscoverPageTeamSeat11985.seatItems(
            items,
            now: now,
            pageSize: 20,
            frozenPrefixCount: frozenCount
        )
        XCTAssertEqual(
            seated.prefix(frozenCount).map(\.id),
            items.prefix(frozenCount).map(\.id),
            "#11984: frozen on-screen prefix must never shift under the reader"
        )
        XCTAssertFalse(
            seated.prefix(20).dropFirst(frozenCount).map(\.id).contains("event-1202"),
            "Second Phoenix Suns game yields to page 2 when page 1 already holds a frozen Phoenix Suns card"
        )
        XCTAssertTrue(seated.dropFirst(20).map(\.id).contains("event-1202"))
    }

    // MARK: - 3. 390px Proof Render for #11985

    func testRender390pxDiscoverStartTimesAndSingleTeamSeatProof() throws {
        let realNow = Date()
        var cal = Calendar.current
        cal.timeZone = TimeZone.current
        let iso = ISO8601DateFormatter()

        let in25mISO = iso.string(from: realNow.addingTimeInterval(25 * 60))
        // Ensure Today clock is at least 75m in the future (or 11:30 PM tonight) so it prints "Today <time>"
        let todayTarget = max(
            realNow.addingTimeInterval(95 * 60),
            cal.date(bySettingHour: 18, minute: 0, second: 0, of: realNow) ?? realNow.addingTimeInterval(95 * 60)
        )
        let tomorrowBase = cal.date(byAdding: .day, value: 1, to: realNow) ?? realNow.addingTimeInterval(86_400)
        let tomorrowTarget = cal.date(bySettingHour: 18, minute: 0, second: 0, of: tomorrowBase) ?? tomorrowBase

        let celticsKnicksSoon = try makeEventItem(
            id: 1301,
            awayTeam: "New York Knicks",
            homeTeam: "Boston Celtics",
            commenceTime: in25mISO,
            awayProb: 0.39,
            homeProb: 0.61
        )
        let blazersSunsToday = try makeEventItem(
            id: 1302,
            awayTeam: "Portland Trail Blazers",
            homeTeam: "Phoenix Suns",
            commenceTime: iso.string(from: todayTarget),
            awayProb: 0.29,
            homeProb: 0.71
        )
        let magicSunsTomorrow = try makeEventItem(
            id: 1303,
            awayTeam: "Orlando Magic",
            homeTeam: "Phoenix Suns",
            commenceTime: iso.string(from: tomorrowTarget),
            awayProb: 0.42,
            homeProb: 0.58
        )

        var rawFeed: [DiscoverGroupedItem] = [
            .single(celticsKnicksSoon),
            .single(magicSunsTomorrow),
            .single(blazersSunsToday),
        ]
        for idx in 0..<20 {
            rawFeed.append(.single(try makeFuturesFiller(id: 5000 + idx)))
        }
        let seated = DiscoverPageTeamSeat11985.seatItems(rawFeed, now: realNow, pageSize: 20)
        let page1Events = seated.prefix(20).compactMap { item -> FeedEventData? in
            if case .single(let f) = item { return f.event }
            return nil
        }
        XCTAssertEqual(page1Events.map(\.id), [1301, 1302], "Page 1 seats Knicks@Celtics (within hour) + Blazers@Suns (Today); Magic@Suns (Tomorrow) yields to Page 2")

        let sheet = VStack(alignment: .leading, spacing: 14) {
            Text("Discover Page 1 — Start Times & One Game Per Team (#11985)")
                .font(.caption.weight(.semibold))
                .foregroundStyle(.secondary)

            ForEach(page1Events, id: \.id) { ev in
                NativeEventDiscoverCard(
                    event: ev,
                    feedContext: ev.id == 1302 ? "Nearer Phoenix Suns game keeps the Page 1 seat" : "Tip-off inside the hour",
                    expandedContext: nil,
                    navigationPath: .constant(NavigationPath())
                )
            }

            Divider().padding(.vertical, 4)

            Text("Page 2 — Yielded Later Game for Same Team")
                .font(.caption.weight(.semibold))
                .foregroundStyle(.secondary)

            if let magicEv = magicSunsTomorrow.event {
                NativeEventDiscoverCard(
                    event: magicEv,
                    feedContext: "Tomorrow's Phoenix Suns game yielded Page 1 to Today's game",
                    expandedContext: nil,
                    navigationPath: .constant(NavigationPath())
                )
            }
        }
        .padding(16)
        .frame(width: 390, alignment: .topLeading)
        .background(Color(red: 0.965, green: 0.965, blue: 0.973))
        .environmentObject(pins)
        .environment(\.colorScheme, .light)

        let renderer = rendererForMeasurement(sheet, at: .large)
        renderer.scale = 2.0
        renderer.proposedSize = ProposedViewSize(width: 390, height: nil)
        let image = try XCTUnwrap(renderer.uiImage)

        let req = VNRecognizeTextRequest()
        req.recognitionLevel = .accurate
        req.usesLanguageCorrection = false
        try VNImageRequestHandler(cgImage: try XCTUnwrap(image.cgImage), options: [:]).perform([req])
        let lines = (req.results ?? []).compactMap { $0.topCandidates(1).first?.string }
        let joined = lines.joined(separator: " ")
        XCTAssertTrue(joined.contains("In 2") || joined.contains("In 1"), "Countdown must appear on <1h card: \(lines)")
        XCTAssertTrue(joined.contains("Tomorrow"), "Tomorrow start time must appear on yielded card: \(lines)")

        if let dir = ProcessInfo.processInfo.environment["OVERNIGHT9_RENDER_DIR"], !dir.isEmpty {
            let folder = URL(fileURLWithPath: dir, isDirectory: true)
            try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
            try XCTUnwrap(image.pngData()).write(to: folder.appendingPathComponent("overnight9-discover-start-time-and-team-seat-390.png"))
        }
    }
}
#endif
