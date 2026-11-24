import Foundation
import SwiftUI
import XCTest
@testable import Bain_Luck

#if canImport(UIKit)
import UIKit
import Vision
#endif

/// #13182: `SeriesProbabilityView` requires an authoritative series standing
/// (`home_series_wins` / `away_series_wins` or `espn.series_home_wins` /
/// `espn.series_away_wins`) from `EventDetail`, withholds when absent instead of
/// assuming `0–0`, avoids double-counting a finished game when the served series
/// record already includes it, and renders Game 1 (`0–0`), mid-series (`2–1` live
/// and finished), and clinched series (`4–1` / `4–2`) cleanly.
@MainActor
final class SeriesProbabilityContract13182Tests: XCTestCase {

    private func decodeDetail(_ json: String) throws -> EventDetail {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return try decoder.decode(EventDetail.self, from: Data(json.utf8))
    }

    func testWithholdsSeriesCardWheneverAuthoritativeSeriesWinsAreAbsent() throws {
        // Playoff round tag present, but neither top-level nor espn series wins served -> nil!
        let missingBoth = try decodeDetail(#"""
        {
          "id": 9001,
          "sport": "basketball_nba",
          "away_team": "Boston Celtics",
          "home_team": "New York Knicks",
          "status": "live",
          "event_tags": ["sport:basketball", "conference_semis"],
          "current_odds": {"home_probability": 0.56, "away_probability": 0.44}
        }
        """#)
        XCTAssertNil(SeriesProbabilityView.resolvedMountInputs(for: missingBoth))

        // Finished Game 3 with `competitive_structure:best_of_7` but no series wins -> nil (never `0–1`!).
        let missingFinished = try decodeDetail(#"""
        {
          "id": 9002,
          "sport": "icehockey_nhl",
          "away_team": "Florida Panthers",
          "home_team": "Toronto Maple Leafs",
          "status": "completed",
          "away_score": 4,
          "home_score": 2,
          "hero_probability_source": "settled",
          "hero_settled_result": "away",
          "event_tags": ["sport:hockey", "competitive_structure:best_of_7", "round_2"],
          "prematch_odds": {"home_probability": 0.52, "away_probability": 0.48}
        }
        """#)
        XCTAssertNil(SeriesProbabilityView.resolvedMountInputs(for: missingFinished))
    }

    func testGame1ZeroZeroLiveAndMidSeriesTwoOneLiveAndFinishedWithoutDoubleCounting() throws {
        // 1. Game 1 (0–0) live with explicit `0–0` from server
        let game1Live = try decodeDetail(#"""
        {
          "id": 9010,
          "sport": "basketball_nba",
          "away_team": "Indiana Pacers",
          "home_team": "New York Knicks",
          "status": "live",
          "event_tags": ["nba_finals"],
          "home_series_wins": 0,
          "away_series_wins": 0,
          "best_of": 7,
          "current_odds": {"home_probability": 0.60, "away_probability": 0.40}
        }
        """#)
        let g1 = try XCTUnwrap(SeriesProbabilityView.resolvedMountInputs(for: game1Live))
        XCTAssertEqual(g1.homeSeriesWins, 0)
        XCTAssertEqual(g1.awaySeriesWins, 0)
        XCTAssertEqual(g1.gamesToWin, 4)
        XCTAssertEqual(g1.homeWinProb, 0.60, accuracy: 0.0001)
        let g1View = SeriesProbabilityView(
            homeWinProb: g1.homeWinProb,
            homeSeriesWins: g1.homeSeriesWins,
            awaySeriesWins: g1.awaySeriesWins,
            gamesToWin: g1.gamesToWin,
            homeTeam: game1Live.homeTeam,
            awayTeam: game1Live.awayTeam,
            homeTeamColor: .orange,
            awayTeamColor: .yellow
        )
        XCTAssertEqual(g1View.stateLabel, "Series tied 0–0")
        XCTAssertFalse(g1View.isSeriesOver)

        // 2. Mid-series Game 4 live at 2–1
        let midLive = try decodeDetail(#"""
        {
          "id": 9011,
          "sport": "basketball_nba",
          "away_team": "Boston Celtics",
          "home_team": "New York Knicks",
          "status": "live",
          "event_tags": ["conference_semis"],
          "home_series_wins": 2,
          "away_series_wins": 1,
          "best_of": 7,
          "current_odds": {"home_probability": 0.55, "away_probability": 0.45}
        }
        """#)
        let mLive = try XCTUnwrap(SeriesProbabilityView.resolvedMountInputs(for: midLive))
        XCTAssertEqual(mLive.homeSeriesWins, 2)
        XCTAssertEqual(mLive.awaySeriesWins, 1)
        XCTAssertEqual(mLive.gamesToWin, 4)
        XCTAssertEqual(mLive.homeWinProb, 0.55, accuracy: 0.0001)
        let mLiveView = SeriesProbabilityView(
            homeWinProb: mLive.homeWinProb,
            homeSeriesWins: mLive.homeSeriesWins,
            awaySeriesWins: mLive.awaySeriesWins,
            gamesToWin: mLive.gamesToWin,
            homeTeam: midLive.homeTeam,
            awayTeam: midLive.awayTeam,
            homeTeamColor: .orange,
            awayTeamColor: .green
        )
        XCTAssertEqual(mLiveView.stateLabel, "Knicks lead 2–1")

        // 3a. Finished Game 3 where server served PRIOR standing (1–1) + home won -> 2–1
        let midFinishedPrior = try decodeDetail(#"""
        {
          "id": 9012,
          "sport": "basketball_nba",
          "away_team": "Boston Celtics",
          "home_team": "New York Knicks",
          "status": "completed",
          "away_score": 101,
          "home_score": 108,
          "hero_probability_source": "settled",
          "hero_settled_result": "home",
          "event_tags": ["conference_semis"],
          "home_series_wins": 1,
          "away_series_wins": 1,
          "series_wins_include_current_game": false,
          "prematch_odds": {"home_probability": 0.54, "away_probability": 0.46}
        }
        """#)
        let mFinPrior = try XCTUnwrap(SeriesProbabilityView.resolvedMountInputs(for: midFinishedPrior))
        XCTAssertEqual(mFinPrior.homeSeriesWins, 2)
        XCTAssertEqual(mFinPrior.awaySeriesWins, 1)
        XCTAssertEqual(mFinPrior.homeWinProb, 0.54, accuracy: 0.0001)

        // 3b. Finished Game 3 where server ALREADY counted the game (`2–1`, `series_wins_include_current_game: true`) -> stays `2–1` (never `3–1`!)
        let midFinishedIncluded = try decodeDetail(#"""
        {
          "id": 9013,
          "sport": "basketball_nba",
          "away_team": "Boston Celtics",
          "home_team": "New York Knicks",
          "status": "completed",
          "away_score": 101,
          "home_score": 108,
          "hero_probability_source": "settled",
          "hero_settled_result": "home",
          "event_tags": ["conference_semis"],
          "home_series_wins": 2,
          "away_series_wins": 1,
          "series_wins_include_current_game": true,
          "prematch_odds": {"home_probability": 0.54, "away_probability": 0.46}
        }
        """#)
        let mFinIncluded = try XCTUnwrap(SeriesProbabilityView.resolvedMountInputs(for: midFinishedIncluded))
        XCTAssertEqual(mFinIncluded.homeSeriesWins, 2, "Must not double-count finished game when series_wins_include_current_game is true")
        XCTAssertEqual(mFinIncluded.awaySeriesWins, 1)
    }

    func testClinchedSeriesFourOneAndFourTwoAndBestOfFiveDivisionSeries() throws {
        // Clinched 4–1 (home clinches Game 5 from 3–1 prior)
        let clinched41 = try decodeDetail(#"""
        {
          "id": 9020,
          "sport": "basketball_nba",
          "away_team": "Dallas Mavericks",
          "home_team": "Boston Celtics",
          "status": "completed",
          "away_score": 88,
          "home_score": 106,
          "hero_probability_source": "settled",
          "hero_settled_result": "home",
          "event_tags": ["nba_finals"],
          "home_series_wins": 3,
          "away_series_wins": 1
        }
        """#)
        let c41 = try XCTUnwrap(SeriesProbabilityView.resolvedMountInputs(for: clinched41))
        XCTAssertEqual(c41.homeSeriesWins, 4)
        XCTAssertEqual(c41.awaySeriesWins, 1)
        XCTAssertEqual(c41.homeWinProb, 1.0, accuracy: 0.0001)
        let c41View = SeriesProbabilityView(
            homeWinProb: c41.homeWinProb,
            homeSeriesWins: c41.homeSeriesWins,
            awaySeriesWins: c41.awaySeriesWins,
            gamesToWin: c41.gamesToWin,
            homeTeam: clinched41.homeTeam,
            awayTeam: clinched41.awayTeam,
            homeTeamColor: Color(hex: "#007A33"),
            awayTeamColor: Color(hex: "#00538C")
        )
        XCTAssertTrue(c41View.isSeriesOver)
        XCTAssertEqual(c41View.stateLabel, "Celtics win series 4–1")
        XCTAssertEqual(c41View.homeSeriesProb, 1.0, accuracy: 0.0001)

        // Clinched 4–2 where server already updated standing to 2–4 (away clinched) -> never 2–5!
        let clinched42 = try decodeDetail(#"""
        {
          "id": 9021,
          "sport": "icehockey_nhl",
          "away_team": "Florida Panthers",
          "home_team": "Edmonton Oilers",
          "status": "completed",
          "away_score": 5,
          "home_score": 2,
          "hero_probability_source": "settled",
          "hero_settled_result": "away",
          "event_tags": ["stanley_cup"],
          "home_series_wins": 2,
          "away_series_wins": 4
        }
        """#)
        let c42 = try XCTUnwrap(SeriesProbabilityView.resolvedMountInputs(for: clinched42))
        XCTAssertEqual(c42.homeSeriesWins, 2)
        XCTAssertEqual(c42.awaySeriesWins, 4)
        XCTAssertEqual(c42.homeWinProb, 0.0, accuracy: 0.0001)
        let c42View = SeriesProbabilityView(
            homeWinProb: c42.homeWinProb,
            homeSeriesWins: c42.homeSeriesWins,
            awaySeriesWins: c42.awaySeriesWins,
            gamesToWin: c42.gamesToWin,
            homeTeam: clinched42.homeTeam,
            awayTeam: clinched42.awayTeam,
            homeTeamColor: Color(hex: "#041E42"),
            awayTeamColor: Color(hex: "#C8102E")
        )
        XCTAssertTrue(c42View.isSeriesOver)
        XCTAssertEqual(c42View.stateLabel, "Panthers win series 4–2")
        XCTAssertEqual(c42View.awaySeriesProb, 1.0, accuracy: 0.0001)

        // ALDS Best-of-5 (`best_of: 5` -> `gamesToWin == 3`)
        let alds = try decodeDetail(#"""
        {
          "id": 9022,
          "sport": "baseball_mlb",
          "away_team": "Detroit Tigers",
          "home_team": "Cleveland Guardians",
          "status": "live",
          "event_tags": ["alds"],
          "home_series_wins": 1,
          "away_series_wins": 1,
          "best_of": 5,
          "current_odds": {"home_probability": 0.57, "away_probability": 0.43}
        }
        """#)
        let aldsInputs = try XCTUnwrap(SeriesProbabilityView.resolvedMountInputs(for: alds))
        XCTAssertEqual(aldsInputs.gamesToWin, 3)
    }

    #if canImport(UIKit)
    func testRenderedMidSeriesAndClinchedCardsAt390LightAndDarkHaveZeroEllipsis() throws {
        for scheme in [ColorScheme.light, ColorScheme.dark] {
            let uiStyle: UIUserInterfaceStyle = scheme == .dark ? .dark : .light
            let surface = scheme == .dark ? Color.black : Color(.systemGroupedBackground)
            let stack = VStack(spacing: 14) {
                SeriesProbabilityView(
                    homeWinProb: 0.55,
                    homeSeriesWins: 2,
                    awaySeriesWins: 1,
                    gamesToWin: 4,
                    homeTeam: "New York Knicks",
                    awayTeam: "Boston Celtics",
                    homeTeamColor: Color(hex: "#F58426"),
                    awayTeamColor: Color(hex: "#007A33")
                )
                SeriesProbabilityView(
                    homeWinProb: 1.0,
                    homeSeriesWins: 4,
                    awaySeriesWins: 1,
                    gamesToWin: 4,
                    homeTeam: "Boston Celtics",
                    awayTeam: "Dallas Mavericks",
                    homeTeamColor: Color(hex: "#007A33"),
                    awayTeamColor: Color(hex: "#00538C")
                )
            }
            .padding(16)
            .frame(width: 390, alignment: .topLeading)
            .background(surface)
            .environment(\.colorScheme, scheme)

            let host = hostForMeasurement(stack, at: .large)
            host.overrideUserInterfaceStyle = uiStyle
            let fitting = host.sizeThatFits(in: CGSize(width: 390, height: 1000))
            host.view.frame = CGRect(origin: .zero, size: CGSize(width: 390, height: max(320, ceil(fitting.height) + 8)))
            host.view.setNeedsLayout()
            host.view.layoutIfNeeded()

            let fmt = UIGraphicsImageRendererFormat()
            fmt.scale = 3.0
            let img = UIGraphicsImageRenderer(bounds: host.view.bounds, format: fmt).image { ctx in
                if !host.view.drawHierarchy(in: host.view.bounds, afterScreenUpdates: true) {
                    host.view.layer.render(in: ctx.cgContext)
                }
            }

            let req = VNRecognizeTextRequest()
            req.recognitionLevel = .accurate
            try VNImageRequestHandler(cgImage: XCTUnwrap(img.cgImage), options: [:]).perform([req])
            let lines = (req.results ?? []).compactMap { $0.topCandidates(1).first?.string }
            let joined = lines.joined(separator: " | ")
            XCTAssertTrue(joined.contains("Knicks lead 2–1") || joined.contains("Knicks lead"), "Expected mid-series standing (\(scheme)); got: \(joined)")
            XCTAssertTrue(joined.contains("Celtics win series 4–1") || joined.contains("Series Result"), "Expected clinched series result (\(scheme)); got: \(joined)")
            XCTAssertFalse(lines.contains(where: { $0.contains("…") || $0.contains("...") }), "Zero ellipsis (\(scheme)); got: \(joined)")

            if let outDir = ProcessInfo.processInfo.environment["BUILDER_C_RENDER_DIR_13182"], !outDir.isEmpty {
                let dirURL = URL(fileURLWithPath: outDir, isDirectory: true)
                try FileManager.default.createDirectory(at: dirURL, withIntermediateDirectories: true)
                let suffix = scheme == .dark ? "dark" : "light"
                if let png = img.pngData() {
                    try png.write(to: dirURL.appendingPathComponent("13182-series-standing-and-clinched-\(suffix)-390.png"))
                }
            }
        }
    }
    #endif
}
