import Foundation
import SwiftUI
import UIKit
import Vision
import XCTest
@testable import Bain_Luck

@MainActor
final class SportsLeagueHeadings401BTests: XCTestCase {
    private nonisolated struct FakeSportsProvider401B: SportsFeedProviding, @unchecked Sendable {
        let main: FeedResponse
        let backfill: FeedResponse
        let grouped: GroupedFeedResponse

        nonisolated func fetchSportsFeed() async throws -> FeedResponse { main }
        nonisolated func fetchSportsEventBackfill(limit: Int) async throws -> FeedResponse { backfill }
        nonisolated func fetchSportsGroupedFeed(limit: Int) async throws -> GroupedFeedResponse { grouped }
    }

    private func decodeItem(_ json: String) throws -> FeedItem {
        let dec = JSONDecoder()
        dec.keyDecodingStrategy = .convertFromSnakeCase
        return try dec.decode(FeedItem.self, from: Data(json.utf8))
    }

    private func makeEventJSON(
        id: Int,
        sport: String,
        sportName: String?,
        status: String,
        away: String,
        home: String,
        commenceISO: String,
        endedISO: String? = nil,
        startIsTbd: Bool = false,
        awayScore: Int? = nil,
        homeScore: Int? = nil,
        awayProb: Double = 0.45,
        homeProb: Double = 0.55,
        awayAbbrev: String,
        homeAbbrev: String,
        awayHex: String,
        homeHex: String
    ) -> String {
        let sportNameJSON = sportName.map { "\"\($0)\"" } ?? "null"
        let endedJSON = endedISO.map { "\"\($0)\"" } ?? "null"
        let awayScoreJSON = awayScore.map(String.init) ?? "null"
        let homeScoreJSON = homeScore.map(String.init) ?? "null"
        let espnBlock = status == "live"
            ? #","espn": {"period": "Q2", "game_clock": "5:12"}"#
            : ""
        return """
        {
          "type": "event",
          "score": 80,
          "data": {
            "id": \(id),
            "sport": "\(sport)",
            "sport_name": \(sportNameJSON),
            "status": "\(status)",
            "away_team": "\(away)",
            "home_team": "\(home)",
            "commence_time": "\(commenceISO)",
            "ended_at": \(endedJSON),
            "start_is_tbd": \(startIsTbd ? "true" : "false"),
            "away_score": \(awayScoreJSON),
            "home_score": \(homeScoreJSON),
            "away_team_data": { "abbreviation": "\(awayAbbrev)", "primary_color": "\(awayHex)" },
            "home_team_data": { "abbreviation": "\(homeAbbrev)", "primary_color": "\(homeHex)" },
            "current_odds": {
              "away_probability": \(awayProb),
              "home_probability": \(homeProb)
            },
            "opening_odds": {
              "away_probability": 0.48,
              "home_probability": 0.52
            }\(espnBlock)
          }
        }
        """
    }

    private func makeEventItem(
        id: Int,
        sport: String,
        sportName: String?,
        status: String,
        away: String,
        home: String,
        commenceISO: String,
        endedISO: String? = nil,
        startIsTbd: Bool = false,
        awayScore: Int? = nil,
        homeScore: Int? = nil,
        awayProb: Double = 0.45,
        homeProb: Double = 0.55,
        awayAbbrev: String,
        homeAbbrev: String,
        awayHex: String,
        homeHex: String
    ) throws -> FeedItem {
        try decodeItem(makeEventJSON(
            id: id, sport: sport, sportName: sportName, status: status,
            away: away, home: home, commenceISO: commenceISO, endedISO: endedISO,
            startIsTbd: startIsTbd, awayScore: awayScore, homeScore: homeScore,
            awayProb: awayProb, homeProb: homeProb,
            awayAbbrev: awayAbbrev, homeAbbrev: homeAbbrev, awayHex: awayHex, homeHex: homeHex
        ))
    }

    func testBigLeaguesFirstAndTimeOrderWithinEachLeagueAcrossAllThreeBands() throws {
        // Minor/college leagues placed ahead of major leagues on input;
        // multiple games per league intentionally out of chronological order.
        let minorLive = try makeEventItem(
            id: 101, sport: "soccer_brazil_campeonato", sportName: "Brasileirão", status: "live",
            away: "Flamengo", home: "Palmeiras", commenceISO: "2026-11-25T00:15:00Z",
            awayScore: 1, homeScore: 1, awayAbbrev: "FLA", homeAbbrev: "PAL", awayHex: "#C8102E", homeHex: "#006437"
        )
        let ncaabLiveLate = try makeEventItem(
            id: 102, sport: "basketball_ncaab", sportName: "NCAAB", status: "live",
            away: "Saint Louis", home: "Grand Canyon", commenceISO: "2026-11-25T02:30:00Z",
            awayScore: 22, homeScore: 25, awayAbbrev: "SLU", homeAbbrev: "GCU", awayHex: "#003DA5", homeHex: "#522398"
        )
        let nhlLive = try makeEventItem(
            id: 103, sport: "icehockey_nhl", sportName: "NHL", status: "live",
            away: "Stars", home: "Oilers", commenceISO: "2026-11-25T01:00:00Z",
            awayScore: 2, homeScore: 1, awayAbbrev: "DAL", homeAbbrev: "EDM", awayHex: "#006847", homeHex: "#041E42"
        )
        let nbaLiveLater = try makeEventItem(
            id: 104, sport: "basketball_nba", sportName: "NBA", status: "live",
            away: "Clippers", home: "Lakers", commenceISO: "2026-11-25T02:00:00Z",
            awayScore: 48, homeScore: 51, awayAbbrev: "LAC", homeAbbrev: "LAL", awayHex: "#C8102E", homeHex: "#552583"
        )
        let nbaLiveEarlier = try makeEventItem(
            id: 105, sport: "basketball_nba", sportName: "NBA", status: "live",
            away: "Celtics", home: "Knicks", commenceISO: "2026-11-25T00:30:00Z",
            awayScore: 76, homeScore: 72, awayAbbrev: "BOS", homeAbbrev: "NYK", awayHex: "#007A33", homeHex: "#006BB6"
        )
        let euroLive = try makeEventItem(
            id: 106, sport: "basketball_euroleague", sportName: "Euroleague", status: "live",
            away: "Real Madrid", home: "Olympiacos", commenceISO: "2026-11-24T19:00:00Z",
            awayScore: 68, homeScore: 64, awayAbbrev: "RMA", homeAbbrev: "OLY", awayHex: "#00529F", homeHex: "#D50032"
        )

        let liveGroups = SportsLeagueBands401B.grouped(
            [euroLive, minorLive, ncaabLiveLate, nhlLive, nbaLiveLater, nbaLiveEarlier],
            band: .live
        )
        XCTAssertEqual(liveGroups.map(\.title), ["NBA", "NHL", "NCAAB", "Brasileirão", "Euroleague"])
        XCTAssertEqual(liveGroups[0].items.compactMap { $0.event?.id }, [105, 104], "NBA live sorted earliest start first")

        // Upcoming: earliest commenceTime first, TBD after confirmed time at same timestamp.
        let eplUp = try makeEventItem(
            id: 201, sport: "soccer_epl", sportName: "EPL", status: "scheduled",
            away: "Arsenal", home: "Chelsea", commenceISO: "2026-11-26T16:30:00Z",
            awayAbbrev: "ARS", homeAbbrev: "CHE", awayHex: "#EF0107", homeHex: "#034694"
        )
        let nflUpLater = try makeEventItem(
            id: 202, sport: "americanfootball_nfl", sportName: "NFL", status: "scheduled",
            away: "Bills", home: "Lions", commenceISO: "2026-11-26T21:25:00Z",
            awayAbbrev: "BUF", homeAbbrev: "DET", awayHex: "#00338D", homeHex: "#0076B6"
        )
        let nflUpEarlier = try makeEventItem(
            id: 203, sport: "americanfootball_nfl", sportName: "NFL", status: "scheduled",
            away: "Bears", home: "Vikings", commenceISO: "2026-11-26T17:30:00Z",
            awayAbbrev: "CHI", homeAbbrev: "MIN", awayHex: "#0B162A", homeHex: "#4F2683"
        )
        let nflUpSameTimeTBD = try makeEventItem(
            id: 204, sport: "americanfootball_nfl", sportName: "NFL", status: "scheduled",
            away: "Packers", home: "Chiefs", commenceISO: "2026-11-26T17:30:00Z",
            startIsTbd: true,
            awayAbbrev: "GB", homeAbbrev: "KC", awayHex: "#203731", homeHex: "#E31837"
        )
        let ncaafUp = try makeEventItem(
            id: 205, sport: "americanfootball_ncaaf", sportName: "NCAAF", status: "scheduled",
            away: "Ohio State", home: "Michigan", commenceISO: "2026-11-28T17:00:00Z",
            awayAbbrev: "OSU", homeAbbrev: "MICH", awayHex: "#BB0000", homeHex: "#00274C"
        )

        let upcomingGroups = SportsLeagueBands401B.grouped(
            [eplUp, nflUpSameTimeTBD, nflUpLater, ncaafUp, nflUpEarlier],
            band: .upcoming
        )
        XCTAssertEqual(upcomingGroups.map(\.title), ["NFL", "NCAAF", "EPL"])
        XCTAssertEqual(upcomingGroups[0].items.compactMap { $0.event?.id }, [203, 204, 202])

        // Just Happened: most recently ended first inside each league; big leagues first.
        let nhlFin = try makeEventItem(
            id: 301, sport: "icehockey_nhl", sportName: "NHL", status: "completed",
            away: "Bruins", home: "Rangers", commenceISO: "2026-11-24T22:00:00Z",
            endedISO: "2026-11-25T00:45:00Z",
            awayScore: 3, homeScore: 2, awayAbbrev: "BOS", homeAbbrev: "NYR", awayHex: "#FFB81C", homeHex: "#0038A8"
        )
        let nbaFinOlder = try makeEventItem(
            id: 302, sport: "basketball_nba", sportName: "NBA", status: "completed",
            away: "Heat", home: "Bucks", commenceISO: "2026-11-24T19:00:00Z",
            endedISO: "2026-11-24T21:30:00Z",
            awayScore: 102, homeScore: 111, awayAbbrev: "MIA", homeAbbrev: "MIL", awayHex: "#98002E", homeHex: "#00471B"
        )
        let nbaFinNewer = try makeEventItem(
            id: 303, sport: "basketball_nba", sportName: "NBA", status: "completed",
            away: "Warriors", home: "Suns", commenceISO: "2026-11-24T21:00:00Z",
            endedISO: "2026-11-24T23:40:00Z",
            awayScore: 118, homeScore: 114, awayAbbrev: "GSW", homeAbbrev: "PHX", awayHex: "#1D428A", homeHex: "#E56020"
        )

        let finishedGroups = SportsLeagueBands401B.grouped(
            [nhlFin, nbaFinOlder, nbaFinNewer],
            band: .justHappened
        )
        XCTAssertEqual(finishedGroups.map(\.title), ["NBA", "NHL"])
        XCTAssertEqual(finishedGroups[0].items.compactMap { $0.event?.id }, [303, 302], "Just Happened sorted most recent first")
    }

    func testFeedViewRenders390PtLightDarkRegularAndLargestTextWithLeagueHeadings() async throws {
        let now = Date()
        let iso = ISO8601DateFormatter()
        let liveEarlier = iso.string(from: now.addingTimeInterval(-3600))
        let liveLater = iso.string(from: now.addingTimeInterval(-1800))
        let up1 = iso.string(from: now.addingTimeInterval(2 * 3600))
        let up2 = iso.string(from: now.addingTimeInterval(4 * 3600))
        let finStart = iso.string(from: now.addingTimeInterval(-4 * 3600))
        let finEnd = iso.string(from: now.addingTimeInterval(-900))

        let itemJSONs: [String] = [
            // Deliberately out of league and time order so 401:B must group + reorder.
            makeEventJSON(
                id: 501, sport: "icehockey_nhl", sportName: "NHL", status: "live",
                away: "Stars", home: "Oilers", commenceISO: liveEarlier,
                awayScore: 2, homeScore: 2, awayAbbrev: "DAL", homeAbbrev: "EDM", awayHex: "#006847", homeHex: "#041E42"
            ),
            makeEventJSON(
                id: 502, sport: "basketball_nba", sportName: "NBA", status: "live",
                away: "Clippers", home: "Lakers", commenceISO: liveLater,
                awayScore: 54, homeScore: 58, awayAbbrev: "LAC", homeAbbrev: "LAL", awayHex: "#C8102E", homeHex: "#552583"
            ),
            makeEventJSON(
                id: 503, sport: "basketball_nba", sportName: "NBA", status: "live",
                away: "Celtics", home: "Knicks", commenceISO: liveEarlier,
                awayScore: 81, homeScore: 76, awayAbbrev: "BOS", homeAbbrev: "NYK", awayHex: "#007A33", homeHex: "#006BB6"
            ),
            makeEventJSON(
                id: 504, sport: "basketball_ncaab", sportName: "NCAAB", status: "scheduled",
                away: "Duke", home: "Kansas", commenceISO: up1,
                awayAbbrev: "DUKE", homeAbbrev: "KU", awayHex: "#003087", homeHex: "#0051BA"
            ),
            makeEventJSON(
                id: 505, sport: "americanfootball_nfl", sportName: "NFL", status: "scheduled",
                away: "Bills", home: "Lions", commenceISO: up2,
                awayAbbrev: "BUF", homeAbbrev: "DET", awayHex: "#00338D", homeHex: "#0076B6"
            ),
            makeEventJSON(
                id: 506, sport: "basketball_nba", sportName: "NBA", status: "completed",
                away: "Warriors", home: "Nuggets", commenceISO: finStart, endedISO: finEnd,
                awayScore: 112, homeScore: 109, awayAbbrev: "GSW", homeAbbrev: "DEN", awayHex: "#1D428A", homeHex: "#0E2240"
            ),
        ]

        let dec = JSONDecoder()
        dec.keyDecodingStrategy = .convertFromSnakeCase
        let emptyBackfill = try dec.decode(FeedResponse.self, from: Data(#"{"items":[],"total":0,"limit":200,"offset":0,"has_more":false}"#.utf8))
        let emptyGrouped = try dec.decode(GroupedFeedResponse.self, from: Data(#"{"feed":[],"total":0,"limit":20,"offset":0}"#.utf8))

        let outDir = ProcessInfo.processInfo.environment["BUILDER_C_RENDER_401B_DIR"]
        if let outDir, !outDir.isEmpty {
            try FileManager.default.createDirectory(atPath: outDir, withIntermediateDirectories: true)
        }

        let configs: [(tag: String, scheme: ColorScheme, typeSize: DynamicTypeSize, height: CGFloat, feedJSON: String, twoNBALive: Bool)] = [
            ("401b-reg-light", .light, .large, 2050, #"{"items":[\#(itemJSONs.joined(separator: ","))],"total":6,"limit":50,"offset":0,"has_more":false}"#, true),
            ("401b-reg-dark", .dark, .large, 2050, #"{"items":[\#(itemJSONs.joined(separator: ","))],"total":6,"limit":50,"offset":0,"has_more":false}"#, true),
            ("401b-ax5-light", .light, .accessibility5, 2650, #"{"items":[\#(itemJSONs[0]),\#(itemJSONs[2]),\#(itemJSONs[4]),\#(itemJSONs[5])],"total":4,"limit":50,"offset":0,"has_more":false}"#, false),
            ("401b-ax5-dark", .dark, .accessibility5, 2650, #"{"items":[\#(itemJSONs[0]),\#(itemJSONs[2]),\#(itemJSONs[4]),\#(itemJSONs[5])],"total":4,"limit":50,"offset":0,"has_more":false}"#, false),
        ]

        for cfg in configs {
            let feed = try dec.decode(FeedResponse.self, from: Data(cfg.feedJSON.utf8))
            let vm = FeedViewModel(
                client: FakeSportsProvider401B(main: feed, backfill: emptyBackfill, grouped: emptyGrouped),
                telemetry: nil,
                autoRefreshEnabled: false
            )
            await vm.startLoad()
            let view = FeedView(viewModel: vm)
                .environmentObject(NavigationCoordinator())
                .environmentObject(PinManager())
                .environment(\.horizontalSizeClass, .compact)
                .environment(\.colorScheme, cfg.scheme)

            let img = try captureView(view, scheme: cfg.scheme, typeSize: cfg.typeSize, height: cfg.height)
            let lines = try ocrLines(img)
            let joined = lines.joined(separator: "\n")

            XCTAssertFalse(joined.contains("Upcom-"), "\(cfg.tag) hyphenated Upcoming:\n\(joined)")
            XCTAssertFalse(joined.contains("Happen..."), "\(cfg.tag) truncated Just Happened:\n\(joined)")
            XCTAssertTrue(joined.contains("Live Now"), "\(cfg.tag) missing Live Now:\n\(joined)")
            XCTAssertTrue(joined.contains("Upcoming"), "\(cfg.tag) missing Upcoming:\n\(joined)")
            XCTAssertTrue(
                cfg.typeSize.isAccessibilitySize ? joined.contains("Happened") : joined.contains("Just Happened"),
                "\(cfg.tag) missing Just Happened:\n\(joined)"
            )

            let celticsIdx = try XCTUnwrap(lines.firstIndex { $0.contains("Celtics") }, "\(cfg.tag) missing Celtics:\n\(joined)")
            let starsIdx = try XCTUnwrap(lines.firstIndex { $0.contains("Stars") }, "\(cfg.tag) missing Stars:\n\(joined)")
            let billsIdx = try XCTUnwrap(lines.firstIndex { $0.contains("Bills") }, "\(cfg.tag) missing Bills:\n\(joined)")
            XCTAssertLessThan(celticsIdx, starsIdx, "\(cfg.tag) NBA before NHL failed")
            XCTAssertLessThan(starsIdx, billsIdx, "\(cfg.tag) Live before Upcoming failed")
            if cfg.twoNBALive {
                let clippersIdx = try XCTUnwrap(lines.firstIndex { $0.contains("Clippers") }, "\(cfg.tag) missing Clippers:\n\(joined)")
                let dukeIdx = try XCTUnwrap(lines.firstIndex { $0.contains("Duke") }, "\(cfg.tag) missing Duke:\n\(joined)")
                XCTAssertLessThan(celticsIdx, clippersIdx, "\(cfg.tag) NBA time order failed")
                XCTAssertLessThan(clippersIdx, starsIdx, "\(cfg.tag) NBA before NHL failed")
                XCTAssertLessThan(billsIdx, dukeIdx, "\(cfg.tag) Upcoming NFL before NCAAB failed")
            }

            if let outDir, !outDir.isEmpty, let png = img.pngData() {
                try png.write(to: URL(fileURLWithPath: "\(outDir)/\(cfg.tag).png"), options: .atomic)
            }
        }
    }

    private func captureView<V: View>(
        _ view: V,
        scheme: ColorScheme,
        typeSize: DynamicTypeSize,
        height: CGFloat
    ) throws -> UIImage {
        let host = hostForMeasurement(view, at: typeSize)
        host.overrideUserInterfaceStyle = scheme == .dark ? .dark : .light
        host.traitOverrides.horizontalSizeClass = .compact
        let bounds = CGRect(x: 0, y: 0, width: 390, height: height)
        let scene = UIApplication.shared.connectedScenes.compactMap { $0 as? UIWindowScene }.first
        let window: UIWindow = scene.map { UIWindow(windowScene: $0) } ?? UIWindow(frame: bounds)
        window.frame = bounds
        window.overrideUserInterfaceStyle = scheme == .dark ? .dark : .light
        window.rootViewController = host
        window.isHidden = false
        defer {
            window.isHidden = true
            window.rootViewController = nil
        }
        host.view.frame = bounds
        for _ in 0..<8 {
            host.view.setNeedsLayout()
            host.view.layoutIfNeeded()
            RunLoop.current.run(until: Date().addingTimeInterval(0.03))
        }
        let fmt = UIGraphicsImageRendererFormat()
        fmt.scale = 2.0
        fmt.opaque = true
        return UIGraphicsImageRenderer(size: bounds.size, format: fmt).image { _ in
            _ = host.view.drawHierarchy(in: host.view.bounds, afterScreenUpdates: true)
        }
    }

    private func ocrLines(_ image: UIImage) throws -> [String] {
        let cg = try XCTUnwrap(image.cgImage)
        // Tall 2x renders (>4000px) can cause VNRecognizeTextRequest to drop
        // individual mid-strip rows; scan overlapping 1400px horizontal bands
        // in top-to-bottom order while preserving exact line ordering.
        if cg.height <= 1800 {
            let req = VNRecognizeTextRequest()
            req.recognitionLevel = .accurate
            req.usesLanguageCorrection = false
            try VNImageRequestHandler(cgImage: cg).perform([req])
            return (req.results ?? []).compactMap { $0.topCandidates(1).first?.string }
        }
        let bandHeight = 1400
        let step = 1000
        var items: [(y: CGFloat, text: String)] = []
        var yStart = 0
        while yStart < cg.height {
            let h = min(bandHeight, cg.height - yStart)
            let rect = CGRect(x: 0, y: yStart, width: cg.width, height: h)
            guard let slice = cg.cropping(to: rect) else { break }
            let req = VNRecognizeTextRequest()
            req.recognitionLevel = .accurate
            req.usesLanguageCorrection = false
            try VNImageRequestHandler(cgImage: slice).perform([req])
            for obs in req.results ?? [] {
                guard let text = obs.topCandidates(1).first?.string else { continue }
                let globalY = CGFloat(yStart) + (1.0 - obs.boundingBox.midY) * CGFloat(h)
                items.append((globalY, text))
            }
            if yStart + h >= cg.height { break }
            yStart += step
        }
        items.sort { $0.y < $1.y }
        var deduped: [(y: CGFloat, text: String)] = []
        for item in items {
            let isDup = deduped.contains { abs($0.y - item.y) < 24 && $0.text == item.text }
            if !isDup { deduped.append(item) }
        }
        return deduped.map(\.text)
    }
}
