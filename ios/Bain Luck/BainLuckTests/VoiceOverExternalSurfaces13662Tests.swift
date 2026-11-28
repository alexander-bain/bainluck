import SwiftUI
import XCTest
@testable import Bain_Luck

/// Item 5 (#13662) — VoiceOver spoken probability and control coverage across
/// Widgets, Lock Screen matchups, Live Activities, Apple Watch app, and Watch complications.
final class VoiceOverExternalSurfaces13662Tests: XCTestCase {
    private static func repoFile(_ relative: String) -> URL {
        URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent(relative)
    }

    func testSavedWidgetSpokenLabelsExpandShortAndLongshotPercents() throws {
        let now = ISO8601DateFormatter().date(from: "2026-11-28T10:00:00Z")!
        let json = """
        {
          "id": 9305,
          "name": "Who will win the primary?",
          "category": "Politics",
          "source": "kalshi",
          "status": "open",
          "updated_at": "2026-11-28T09:59:00Z",
          "outcomes": [
            {"id": 1, "name": "Underdog", "probability": 0.004, "observed_at": "2026-11-28T09:59:00Z"},
            {"id": 2, "name": "Favorite", "probability": 0.996, "observed_at": "2026-11-28T09:59:00Z"},
            {"id": 3, "name": "Contender", "probability": 0.53, "observed_at": "2026-11-28T09:59:00Z"}
          ]
        }
        """
        let market = try SavedWidgetDetailDecoding10875.decoder().decode(
            SavedWidgetMarketDetail10875.self,
            from: Data(json.utf8)
        )

        let low = SavedWidgetReadingRules10875.market(market, outcomeID: 1, now: now)
        XCTAssertTrue(low.spoken.contains("less than 1 percent"), "Got: \(low.spoken)")
        XCTAssertFalse(low.spoken.contains("<1%"), "Raw symbol leaked in spoken: \(low.spoken)")

        let high = SavedWidgetReadingRules10875.market(market, outcomeID: 2, now: now)
        XCTAssertTrue(high.spoken.contains("more than 99 percent"), "Got: \(high.spoken)")
        XCTAssertFalse(high.spoken.contains(">99%"), "Raw symbol leaked in spoken: \(high.spoken)")

        let mid = SavedWidgetReadingRules10875.market(market, outcomeID: 3, now: now)
        XCTAssertTrue(mid.spoken.contains("53 percent"), "Got: \(mid.spoken)")
        XCTAssertFalse(mid.spoken.contains("53%"), "Raw percent leaked in spoken: \(mid.spoken)")
    }

    func testLiveGamesWidgetVoiceOverSummariesSpeakHumanPercentsAndScores() {
        let gameSummary = liveGamesWidgetGameVoiceOverSummary(
            sport: "NFL",
            periodSpoken: PeriodLabel.spoken("Q3 4:12"),
            awayTeam: "Cincinnati Bengals",
            awayScore: 14,
            awayProb: 26,
            homeTeam: "Baltimore Ravens",
            homeScore: 21,
            homeProb: 74
        )
        XCTAssertTrue(gameSummary.contains("26 percent"), gameSummary)
        XCTAssertTrue(gameSummary.contains("74 percent"), gameSummary)
        XCTAssertFalse(gameSummary.contains("%"), gameSummary)

        let discoverSummary = liveGamesWidgetDiscoverVoiceOverSummary(
            category: "Politics",
            name: "2028 Nominee",
            leader: "Newsom",
            probability: 23,
            movement: 2
        )
        XCTAssertTrue(discoverSummary.contains("23 percent"), discoverSummary)
        XCTAssertTrue(discoverSummary.contains("up 2 points"), discoverSummary)
        XCTAssertFalse(discoverSummary.contains("%"), discoverSummary)

        XCTAssertEqual(spokenProbabilityText("<1%"), "less than 1 percent")
        XCTAssertEqual(spokenProbabilityText(">99%"), "more than 99 percent")
        XCTAssertEqual(spokenProbabilityText(absentProbabilityMarker), "No recent probability")
    }

    func testLiveActivityAndWatchComplicationSpokenCopyExpandPercentSymbols() throws {
        let now = ISO8601DateFormatter().date(from: "2026-11-28T10:00:00Z")!
        let snapshotJSON = """
        {
          "eventID": 1001,
          "homeTeam": "Kansas City Chiefs",
          "awayTeam": "Buffalo Bills",
          "homeScore": 24,
          "awayScore": 21,
          "lifecycle": "live",
          "homeRenderedPercent": 64,
          "awayRenderedPercent": 36,
          "scoreObservedAt": "2026-11-28T09:59:30Z",
          "probabilityObservedAt": "2026-11-28T09:59:30Z",
          "homeAbbreviation": "KC",
          "awayAbbreviation": "BUF",
          "periodLabel": "Q4 3:10"
        }
        """
        let activitySnapshot = try JSONDecoder.savedActivity13662Decoder.decode(
            GameActivitySnapshot.self,
            from: Data(snapshotJSON.utf8)
        )
        let reading = GameActivityReading(snapshot: activitySnapshot, eventID: 1001)
        XCTAssertTrue(reading.rowSpoken(.home).contains("64 percent"), reading.rowSpoken(.home))
        XCTAssertTrue(reading.rowSpoken(.away).contains("36 percent"), reading.rowSpoken(.away))
        XCTAssertFalse(reading.compactSpoken.contains("%"), reading.compactSpoken)

        let subOneRect = WatchRectangularReading(
            version: 1,
            eventID: 55,
            kind: .futureForecast,
            homeName: "Test Market",
            awayName: "Longshot",
            home: WatchCompactTeamIdentity(teamID: 1, abbreviation: "MKT"),
            away: WatchCompactTeamIdentity(teamID: 2, abbreviation: "LNG"),
            homePercent: 1,
            homeScore: nil,
            awayScore: nil,
            commenceTime: nil,
            stateLabel: "Longshot",
            observedAt: now.addingTimeInterval(-30),
            scoreObservedAt: nil,
            subOnePercent: true,
            aboveNinetyNinePercent: nil
        )
        let rectSpoken = subOneRect.accessibilityDescription(at: now)
        XCTAssertTrue(rectSpoken.contains("less than 1 percent"), rectSpoken)
        XCTAssertFalse(rectSpoken.contains("<1%"), rectSpoken)

        let above99Rect = WatchRectangularReading(
            version: 1,
            eventID: 56,
            kind: .futureForecast,
            homeName: "Test Market",
            awayName: "Favorite",
            home: WatchCompactTeamIdentity(teamID: 1, abbreviation: "MKT"),
            away: WatchCompactTeamIdentity(teamID: 2, abbreviation: "FAV"),
            homePercent: 99,
            homeScore: nil,
            awayScore: nil,
            commenceTime: nil,
            stateLabel: "Favorite",
            observedAt: now.addingTimeInterval(-30),
            scoreObservedAt: nil,
            subOnePercent: nil,
            aboveNinetyNinePercent: true
        )
        let aboveSpoken = above99Rect.accessibilityDescription(at: now)
        XCTAssertTrue(aboveSpoken.contains("more than 99 percent"), aboveSpoken)
        XCTAssertFalse(aboveSpoken.contains(">99%"), aboveSpoken)
    }

    func testExternalSurfaceSourceContractsHaveNoNoNumberAndExpandSpokenPercents() throws {
        let savedWidget = try String(contentsOf: Self.repoFile("BainLuckWidget/SavedItemWidget10875.swift"), encoding: .utf8)
        let savedLooks = try String(contentsOf: Self.repoFile("BainLuckWidget/SavedWidgetLooks12466.swift"), encoding: .utf8)
        XCTAssertFalse(savedWidget.contains(#".accessibilityLabel("No number")"#))
        XCTAssertFalse(savedLooks.contains(#".accessibilityLabel("No number")"#))
        XCTAssertTrue(savedWidget.contains(#".accessibilityLabel("No recent probability")"#))
        XCTAssertTrue(savedLooks.contains(#".accessibilityLabel("No recent probability")"#))

        let wristTile = try String(contentsOf: Self.repoFile("Bain Luck/Utilities/WatchWristTile12616.swift"), encoding: .utf8)
        XCTAssertTrue(wristTile.contains("spokenProbabilityText(model.heroFigureText)"))
        XCTAssertTrue(wristTile.contains("spokenTextExpandingProbabilitySymbols(model.supportingLine)"))

        let pinsHome = try String(contentsOf: Self.repoFile("BainLuckWatch Watch App/WatchPinnedHomeView12640.swift"), encoding: .utf8)
        XCTAssertTrue(pinsHome.contains("spokenProbabilityText(formatted.display)"))
        XCTAssertTrue(pinsHome.contains("spokenProbabilityText(probabilityText)"))
        XCTAssertTrue(pinsHome.contains("WatchRectangularReading.spokenAge"))

        for rel in [
            "BainLuckWatch Watch App/WatchMatchupGamePageHero297A.swift",
            "BainLuckWatch Watch App/WatchMatchupReading217.swift",
            "BainLuckWatch Watch App/WatchLiveView.swift",
            "BainLuckWatch Watch App/WatchHomeView.swift",
            "BainLuckWatch Watch App/WatchGlancesView.swift",
            "BainLuckWatch Watch App/WatchGuessView.swift",
        ] {
            let src = try String(contentsOf: Self.repoFile(rel), encoding: .utf8)
            XCTAssertTrue(
                src.contains("spokenProbabilityText") || src.contains("spokenTextExpandingProbabilitySymbols"),
                "\(rel) must expand spoken probabilities for VoiceOver"
            )
        }
    }
}

private extension JSONDecoder {
    static var savedActivity13662Decoder: JSONDecoder {
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601
        return decoder
    }
}
