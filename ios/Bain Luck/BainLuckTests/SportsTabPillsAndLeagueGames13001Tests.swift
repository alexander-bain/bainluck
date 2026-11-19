import SwiftUI
import UIKit
import Vision
import XCTest
@testable import Bain_Luck

/// #13001 + #12932 — Pins the Sports tab pills and league/tennis game-first ordering:
///   1. Sports tab pills are sports-only (`NCAAF` and `NCAAB` present; `Politics`, `Entmt`, `Econ`, `Weather` absent).
///   2. `LeagueMarketsResponse` decodes `upcoming_games` and `recent_results` (carrying `#12932` `source_mark` / `away_source_mark`),
///      and `LeagueGridView` draws **Live Now -> Upcoming -> Just Happened** above Championship Probabilities.
///   3. `SportCategoryViewModel.mergeTourLeagueResponses` combines `tennis_atp` + `tennis_wta` matches and markets
///      so `SportCategoryView(key: "tennis")` renders matches first.
@MainActor
final class SportsTabPillsAndLeagueGames13001Tests: XCTestCase {

    private func decodeSnake<T: Decodable>(_ type: T.Type, _ json: String) throws -> T {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(T.self, from: Data(json.utf8))
    }

    private func captureView<V: View>(
        _ view: V,
        width: CGFloat = 390,
        fixedHeight: CGFloat = 760,
        wrapNavigation: Bool = true,
        scheme: ColorScheme = .light,
        at size: DynamicTypeSize = .large
    ) -> UIImage {
        let bg = scheme == .dark ? Color.black : Color(UIColor.systemGroupedBackground)
        let inner: AnyView = {
            if wrapNavigation {
                return AnyView(
                    NavigationStack {
                        view
                            .toolbar(.hidden, for: .navigationBar)
                    }
                )
            }
            return AnyView(view)
        }()
        let root = inner
            .frame(width: width, height: fixedHeight, alignment: .topLeading)
            .background(bg)
            .environment(\.colorScheme, scheme)
            .environmentObject(PinManager())

        let host = hostForMeasurement(root, at: size)
        host.overrideUserInterfaceStyle = scheme == .dark ? .dark : .light
        let scene = UIApplication.shared.connectedScenes.compactMap({ $0 as? UIWindowScene }).first
        let window: UIWindow = scene.map { UIWindow(windowScene: $0) } ?? UIWindow(frame: CGRect(x: 0, y: 0, width: width, height: fixedHeight))
        window.frame = CGRect(x: 0, y: 0, width: width, height: fixedHeight)
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
            RunLoop.current.run(until: Date().addingTimeInterval(0.03))
        }

        let fmt = UIGraphicsImageRendererFormat()
        fmt.scale = 3.0
        fmt.opaque = true
        return UIGraphicsImageRenderer(size: CGSize(width: width, height: fixedHeight), format: fmt).image { _ in
            _ = host.view.drawHierarchy(in: host.view.bounds, afterScreenUpdates: true)
        }
    }

    private func ocrLines(_ image: UIImage) throws -> [String] {
        let req = VNRecognizeTextRequest()
        req.recognitionLevel = .accurate
        req.usesLanguageCorrection = false
        try VNImageRequestHandler(cgImage: XCTUnwrap(image.cgImage)).perform([req])
        return (req.results ?? []).compactMap { $0.topCandidates(1).first?.string }
    }

    private func writeRenderIfEnabled(_ image: UIImage, name: String) throws {
        let dir = URL(fileURLWithPath: "/tmp/renders-13001-12932", isDirectory: true)
        guard FileManager.default.fileExists(atPath: dir.path) else { return }
        let data = try XCTUnwrap(image.pngData())
        try data.write(to: dir.appendingPathComponent("\(name).png"))
    }

    func testSportsTabPillsAreSportsOnlyWithCollegeFootballAndBasketball() throws {
        let names = sportCategories.map(\.name)
        XCTAssertTrue(names.contains("NCAAF"))
        XCTAssertTrue(names.contains("NCAAB"))
        for forbidden in ["Politics", "Entmt", "Econ", "Weather"] {
            XCTAssertFalse(names.contains(forbidden), "\(forbidden) must not appear on the Sports tab")
        }

        let ncaaf = try XCTUnwrap(sportCategories.first(where: { $0.id == "ncaaf" }))
        XCTAssertEqual(ncaaf.route, .leagueGrid(slug: "ncaa-football"))
        let ncaab = try XCTUnwrap(sportCategories.first(where: { $0.id == "ncaab" }))
        XCTAssertEqual(ncaab.route, .leagueGrid(slug: "ncaa-basketball"))
    }

    func testLeagueGridDecodesGamesWithSourceMarksAndDrawsGamesAboveChampionships() throws {
        let recentISO = ISO8601DateFormatter().string(from: Date().addingTimeInterval(-3600))
        let leagueJSON = """
        {
          "sport_key": "americanfootball_nfl",
          "total_markets": 1,
          "sections": {
            "championship": [
              {
                "id": 8801,
                "name": "Super Bowl LX Winner",
                "source": "kalshi",
                "outcome_count": 32,
                "top_outcomes": [
                  { "name": "Detroit Lions", "prob": 22.0 },
                  { "name": "Kansas City Chiefs", "prob": 16.0 }
                ]
              }
            ]
          },
          "upcoming_games": [
            {
              "id": 14780580,
              "sport": "americanfootball_nfl",
              "home_team": "Houston Texans",
              "away_team": "Indianapolis Colts",
              "commence_time": "2099-11-20T01:15:00Z",
              "status": "scheduled",
              "current_odds": {
                "home_probability": 0.845,
                "away_probability": 0.155,
                "projected_home_score": 28.1,
                "projected_away_score": 15.6
              },
              "source_mark": {
                "state": "blend",
                "sources": [
                  { "key": "sportsbooks", "name": "Sportsbooks", "count": 12, "probability": 0.85, "observed_at": "2026-11-18T23:10:00Z" },
                  { "key": "kalshi", "name": "Kalshi", "probability": 0.84, "observed_at": "2026-11-18T23:09:00Z" }
                ],
                "method": "Bain Luck blend · weighted average before rounding"
              }
            }
          ],
          "recent_results": [
            {
              "id": 14780579,
              "sport": "americanfootball_nfl",
              "home_team": "Baltimore Ravens",
              "away_team": "Los Angeles Chargers",
              "commence_time": "\(recentISO)",
              "completed_at": "\(recentISO)",
              "status": "completed",
              "home_score": 20,
              "away_score": 23,
              "opening_odds": {
                "home_probability": 0.62,
                "away_probability": 0.38
              }
            }
          ]
        }
        """

        let gridJSON = """
        {
          "league": "nfl",
          "name": "NFL",
          "season": "2026–27",
          "columns": [
            { "key": "champion", "label": "Super Bowl", "order": 1 }
          ],
          "teams": [
            {
              "name": "Detroit Lions",
              "short_name": "Lions",
              "conference": "NFC",
              "primary_color": "#0076B6",
              "cells": {
                "champion": { "merged_probability": 0.22, "state": "open" }
              }
            }
          ],
          "movers": [],
          "team_count": 1,
          "sources_available": ["kalshi", "polymarket"]
        }
        """

        let markets = try decodeSnake(LeagueMarketsResponse.self, leagueJSON)
        let grid = try decodeSnake(ChampionshipGridResponse.self, gridJSON)
        XCTAssertEqual(markets.upcomingGames.count, 1)
        XCTAssertEqual(markets.recentResults.count, 1)
        XCTAssertEqual(markets.upcomingGames.first?.sourceMark?.state, .blend)

        let vm = LeagueGridViewModel(slug: "nfl", preloadedGrid: grid, preloadedMarkets: markets)
        XCTAssertEqual(vm.upcomingGames.map(\.id), [14780580])
        XCTAssertEqual(vm.recentGames.map(\.id), [14780579])

        let view = LeagueGridView(slug: "nfl", preloadedViewModel: vm)
        let light = captureView(view, fixedHeight: 760, scheme: .light)
        let dark = captureView(view, fixedHeight: 760, scheme: .dark)
        let lines = try ocrLines(light)
        let joined = lines.joined(separator: " ")
        XCTAssertTrue(joined.localizedCaseInsensitiveContains("Upcoming"), "NFL league screen must show Upcoming games at top: \(lines)")
        XCTAssertTrue(joined.localizedCaseInsensitiveContains("Colts") && joined.localizedCaseInsensitiveContains("Texans"), "NFL league screen must show Colts at Texans: \(lines)")

        try writeRenderIfEnabled(light, name: "13001-nfl-games-first-light-390")
        try writeRenderIfEnabled(dark, name: "13001-nfl-games-first-dark-390")
    }

    func testTennisMergesBothToursAndDrawsMatchesFirst() throws {
        let recentISO = ISO8601DateFormatter().string(from: Date().addingTimeInterval(-3600))
        let atpJSON = """
        {
          "sport_key": "tennis_atp",
          "total_markets": 1,
          "sections": {
            "championship": [
              { "id": 9101, "name": "ATP Finals Winner", "source": "kalshi", "outcome_count": 8, "top_outcomes": [{ "name": "Jannik Sinner", "prob": 48.0 }] }
            ]
          },
          "upcoming_games": [
            {
              "id": 15349294,
              "sport": "tennis_atp",
              "home_team": "Heliovaara / Patten",
              "away_team": "Arribage / Olivetti",
              "commence_time": "2099-11-19T13:30:00Z",
              "status": "scheduled",
              "current_odds": { "home_probability": 0.58, "away_probability": 0.42 }
            }
          ],
          "recent_results": [
            {
              "id": 15349300,
              "sport": "tennis_atp",
              "home_team": "Flavio Cobolli",
              "away_team": "Frances Tiafoe",
              "commence_time": "\(recentISO)",
              "status": "completed",
              "home_score": 0,
              "away_score": 2,
              "opening_odds": { "home_probability": 0.44, "away_probability": 0.56 }
            }
          ]
        }
        """
        let wtaJSON = """
        {
          "sport_key": "tennis_wta",
          "total_markets": 1,
          "sections": {
            "championship": [
              { "id": 9102, "name": "Australian Open Women's Winner", "source": "kalshi", "outcome_count": 32, "top_outcomes": [{ "name": "Aryna Sabalenka", "prob": 31.0 }] }
            ]
          },
          "upcoming_games": [
            {
              "id": 15349901,
              "sport": "tennis_wta",
              "home_team": "Coco Gauff",
              "away_team": "Iga Swiatek",
              "commence_time": "2099-11-19T15:00:00Z",
              "status": "scheduled",
              "current_odds": { "home_probability": 0.47, "away_probability": 0.53 }
            }
          ],
          "recent_results": []
        }
        """

        let atp = try decodeSnake(LeagueMarketsResponse.self, atpJSON)
        let wta = try decodeSnake(LeagueMarketsResponse.self, wtaJSON)
        let merged = SportCategoryViewModel.mergeTourLeagueResponses([atp, wta])
        XCTAssertEqual(merged.upcomingGames.count, 2)
        XCTAssertEqual(merged.recentResults.count, 1)
        XCTAssertEqual(merged.totalMarkets, 2)

        let vm = SportCategoryViewModel(categoryKey: "tennis")
        vm.setItemsForTesting([], leagueMarkets: merged)
        XCTAssertFalse(vm.drawsNoRows)
        XCTAssertEqual(vm.leagueUpcomingGames.count, 2)
        XCTAssertEqual(vm.leagueRecentGames.count, 1)

        let view = SportCategoryView(categoryKey: "tennis", categoryName: "Tennis", preloadedViewModel: vm)
        let light = captureView(view, fixedHeight: 760, scheme: .light)
        let dark = captureView(view, fixedHeight: 760, scheme: .dark)
        let lines = try ocrLines(light)
        let joined = lines.joined(separator: " ")
        XCTAssertTrue(joined.contains("Upcoming"), "Tennis category screen must draw Upcoming matches: \(lines)")

        try writeRenderIfEnabled(light, name: "fixture-13001-tennis-matches-light-390")
        try writeRenderIfEnabled(dark, name: "fixture-13001-tennis-matches-dark-390")
    }

    func testRenderLivePayloadsWhenStaged() throws {
        let dir = URL(fileURLWithPath: "/tmp/renders-13001-12932", isDirectory: true)
        guard FileManager.default.fileExists(atPath: dir.path) else { return }

        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase

        // 1. Sports tab pills: real horizontal chip bar + full 10-pill inventory wrapped across 3 rows
        let slices: [[SportCategory]] = [
            Array(sportCategories[0..<4]),
            Array(sportCategories[4..<7]),
            Array(sportCategories[7..<sportCategories.count]),
        ]
        let chipsCard = VStack(alignment: .leading, spacing: 14) {
            SportFilterChips(selectedCategory: .constant("all"))
                .fixedSize(horizontal: false, vertical: true)
            Divider().padding(.horizontal, 16)
            VStack(alignment: .leading, spacing: 8) {
                ForEach(Array(slices.enumerated()), id: \.offset) { _, row in
                    HStack(spacing: 8) {
                        ForEach(row) { cat in
                            HStack(spacing: 4) {
                                if cat.id != "all" {
                                    Image(systemName: SportFilterChips.chipIcon(for: cat.id)).font(.system(size: 10))
                                }
                                Text(cat.name).font(.caption).fixedSize()
                            }
                            .padding(.horizontal, 14)
                            .padding(.vertical, 7)
                            .background(cat.id == "all" ? Color.blue.opacity(0.15) : Color.secondary.opacity(0.08))
                            .foregroundStyle(cat.id == "all" ? .blue : .primary)
                            .clipShape(Capsule())
                        }
                    }
                }
            }
            .padding(.horizontal, 16)
        }
        .padding(.top, 8)
        .padding(.bottom, 16)
        try writeRenderIfEnabled(captureView(chipsCard, fixedHeight: 285, wrapNavigation: false, scheme: .light), name: "13001-sports-pills-light-390")
        try writeRenderIfEnabled(captureView(chipsCard, fixedHeight: 285, wrapNavigation: false, scheme: .dark), name: "13001-sports-pills-dark-390")

        // 2. Live NFL LeagueGridView + #12932 league game SourceMarkSheet
        let nflGridPath = dir.appendingPathComponent("live-nfl-grid.json")
        let nflLeaguePath = dir.appendingPathComponent("live-nfl-league.json")
        if FileManager.default.fileExists(atPath: nflGridPath.path),
           FileManager.default.fileExists(atPath: nflLeaguePath.path) {
            let grid = try decoder.decode(ChampionshipGridResponse.self, from: Data(contentsOf: nflGridPath))
            let markets = try decoder.decode(LeagueMarketsResponse.self, from: Data(contentsOf: nflLeaguePath))
            let vm = LeagueGridViewModel(slug: "nfl", preloadedGrid: grid, preloadedMarkets: markets)
            let view = LeagueGridView(slug: "nfl", preloadedViewModel: vm)
            try writeRenderIfEnabled(captureView(view, fixedHeight: 840, scheme: .light), name: "13001-12932-nfl-live-light-390")
            try writeRenderIfEnabled(captureView(view, fixedHeight: 840, scheme: .dark), name: "13001-12932-nfl-live-dark-390")

            if let firstGame = vm.upcomingGames.first,
               let resolved = EventCardView.resolvedCardSourceMark(
                   event: firstGame,
                   canStillBeGraded: true,
                   currentAwayIsWithheld: false,
                   prematch: nil,
                   prematchAwayIsWithheld: false
               ) {
                let fixedNow = ISO8601DateFormatter().date(from: "2026-11-19T00:05:00Z")!
                let sheet = SourceMarkSheet(
                    mark: resolved.mark,
                    number: resolved.number,
                    subject: resolved.subject,
                    isPregame: resolved.isPregame,
                    now: fixedNow
                )
                try writeRenderIfEnabled(captureView(sheet, fixedHeight: 420, wrapNavigation: false, scheme: .light), name: "12932-nfl-league-game-sheet-light-390")
                try writeRenderIfEnabled(captureView(sheet, fixedHeight: 420, wrapNavigation: false, scheme: .dark), name: "12932-nfl-league-game-sheet-dark-390")
            }
        }

        // 3. Live Tennis merged ATP + WTA matches-first screen
        let atpPath = dir.appendingPathComponent("live-tennis-atp.json")
        let wtaPath = dir.appendingPathComponent("live-tennis-wta.json")
        if FileManager.default.fileExists(atPath: atpPath.path),
           FileManager.default.fileExists(atPath: wtaPath.path) {
            let atp = try decoder.decode(LeagueMarketsResponse.self, from: Data(contentsOf: atpPath))
            let wta = try decoder.decode(LeagueMarketsResponse.self, from: Data(contentsOf: wtaPath))
            let merged = SportCategoryViewModel.mergeTourLeagueResponses([atp, wta])
            let vm = SportCategoryViewModel(categoryKey: "tennis")
            vm.setItemsForTesting([], leagueMarkets: merged)
            let view = SportCategoryView(categoryKey: "tennis", categoryName: "Tennis", preloadedViewModel: vm)
            try writeRenderIfEnabled(captureView(view, fixedHeight: 840, scheme: .light), name: "13001-tennis-live-light-390")
            try writeRenderIfEnabled(captureView(view, fixedHeight: 840, scheme: .dark), name: "13001-tennis-live-dark-390")
        }
    }
}
