import SwiftUI
import UIKit
import XCTest
@testable import Bain_Luck

/// Regression coverage for `#13392`:
/// 1. Medium `LiveGamesWidget` 3-way fallback prints `"%"` (`"RMA 52%"`).
/// 2. Small `SavedGameHeadlineWidgetView12616` fits `"NCAAF · Final"` + `"Pregame 43%"` without `"…"`.
/// 3. Dynamic Island Minimal shows whole percents (`"57%"`) on one line while larger forms keep tenths.
/// 4. Widget gallery placeholder is date-free (`"NBA Champion"`).
final class WidgetAndLiveActivity13392Tests: XCTestCase {
    private static func repoFile(_ relative: String) -> URL {
        URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent(relative)
    }

    func testMediumLiveGamesThreeWayFallbackIncludesPercentSign() throws {
        let source = try String(contentsOf: Self.repoFile("BainLuckWidget/LiveGamesWidget.swift"), encoding: .utf8)
        XCTAssertTrue(source.contains(#"?? "\(game.homeAbbrev) \(game.homeProb)%""#))
        XCTAssertFalse(source.contains(#"?? "\(game.homeAbbrev) \(game.homeProb)""#))
    }

    @MainActor
    func testSmallSavedFinalHeaderPreservesModelAndRendersThreeTierViewThatFits() throws {
        let pacific = TimeZone(identifier: "America/Los_Angeles")!
        let fixedNow = ISO8601DateFormatter().date(from: "2026-11-21T22:00:00Z")!
        let json = """
        {
          "id": 15349422,
          "sport": "americanfootball_ncaaf",
          "sport_name": "NCAAF",
          "status": "completed",
          "commence_time": "2026-11-21T16:00:00Z",
          "away_team": "Rice Owls",
          "home_team": "Temple Owls",
          "away_score": 31,
          "home_score": 27,
          "hero_settled_result": "away",
          "away_team_data": {"abbreviation": "RICE", "primary_color": "#00205B", "secondary_color": "#C1C6C8"},
          "home_team_data": {"abbreviation": "TEM", "primary_color": "#9D2235", "secondary_color": "#FFFFFF"},
          "prematch_odds": {"away_probability": 0.43, "home_probability": 0.57},
          "current_odds": {"away_probability": 1.0, "home_probability": 0.0}
        }
        """
        let event = try SavedWidgetDetailDecoding10875.decoder().decode(
            SavedWidgetEventDetail10875.self,
            from: Data(json.utf8)
        )
        let reading = SavedWidgetReadingRules10875.game(event, side: nil, now: fixedNow)
        let art = SavedWidgetArt12466.game(event)
        let model = SavedGameHeadlineWidgetModel12616.build(
            reading: reading,
            art: art,
            clockFooter: "Final",
            isOffline: false,
            clearsRefreshTrailing: true,
            now: fixedNow,
            timeZone: pacific
        )

        XCTAssertEqual(model.smallTopMeta, "NCAAF · Final")
        XCTAssertEqual(model.smallTopTrailing, "Pregame 43%")

        let view = SavedGameHeadlineWidgetView12616(
            model: model,
            size: .small,
            awayLogo: nil,
            homeLogo: nil,
            fullColor: true
        ) {
            EmptyView()
        }
        .padding(14)
        .frame(width: 155, height: 155)
        .background(Color.white)

        let renderer = ImageRenderer(content: view)
        renderer.scale = 2
        let image = try XCTUnwrap(renderer.uiImage)
        XCTAssertGreaterThan(image.size.width, 100)

        let source = try String(
            contentsOf: Self.repoFile("Bain Luck/Widgets10875/SavedGameHeadlineWidget12616.swift"),
            encoding: .utf8
        )
        XCTAssertTrue(source.contains("ViewThatFits(in: .horizontal)"))
        XCTAssertTrue(source.contains("smallMetaWithTrailingRow("))
    }

    func testDynamicIslandMinimalUsesWholePercentWhileLargerFormsKeepTenths() throws {
        let now = Date()
        let snapshot = try XCTUnwrap(GameActivitySnapshot(
            eventID: 15342100,
            homeTeam: "West Virginia Mountaineers",
            awayTeam: "Houston Cougars",
            lifecycle: .live,
            homeScore: 31,
            awayScore: 31,
            homeProbability: 0.428,
            awayProbability: 0.572,
            sport: "americanfootball_ncaaf",
            scoreObservedAt: now,
            probabilityObservedAt: now,
            homeAbbreviation: "WVU",
            awayAbbreviation: "HOU",
            periodLabel: "Q4 2:15"
        ))
        XCTAssertEqual(snapshot.headlineNowText(home: false), "57.2%")
        XCTAssertEqual(snapshot.awayRenderedPercent, 57)

        let source = try String(
            contentsOf: Self.repoFile("BainLuckWidget/GameLiveActivity.swift"),
            encoding: .utf8
        )
        XCTAssertTrue(source.contains("func minimalNowText(_ side: Side) -> String?"))
        XCTAssertTrue(source.contains("else if let now = reading.minimalNowText(reading.lead)"))
        XCTAssertTrue(source.contains("Text(now)\n                    .lineLimit(1)"))
        XCTAssertTrue(source.contains("reading.nowText("), "Lock Screen, Compact, and Expanded must keep nowText tenths")
    }

    func testWidgetPlaceholderHasNoHardcodedYear() throws {
        let source = try String(contentsOf: Self.repoFile("BainLuckWidget/WidgetModels.swift"), encoding: .utf8)
        let start = try XCTUnwrap(source.range(of: "static var placeholder: BainLuckWidgetEntry {"))
        let end = try XCTUnwrap(source.range(of: "// MARK: - Widget Data Models", range: start.lowerBound..<source.endIndex))
        let placeholderBlock = String(source[start.lowerBound..<end.lowerBound])

        XCTAssertTrue(placeholderBlock.contains(#"name: "NBA Champion""#))
        XCTAssertFalse(placeholderBlock.contains("2026 NBA Champion"))
        let yearPattern = try NSRegularExpression(pattern: #"\b20\d{2}\b"#)
        let fullRange = NSRange(placeholderBlock.startIndex..., in: placeholderBlock)
        XCTAssertNil(yearPattern.firstMatch(in: placeholderBlock, options: [], range: fullRange))
    }
}
