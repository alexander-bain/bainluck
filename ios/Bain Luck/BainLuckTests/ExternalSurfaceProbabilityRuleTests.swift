import XCTest
import SwiftUI
@testable import Bain_Luck

#if canImport(UIKit)
import UIKit
#endif

@MainActor
final class ExternalSurfaceProbabilityRuleTests: XCTestCase {
    private let fixedNow = Date(timeIntervalSinceReferenceDate: 816_700_000)

    func testSharedExternalFormatterNeverPrintsZeroOrOneHundredOnOpenMarkets() {
        for p in [0.0, 0.0004, 0.004, 0.005, 0.008, 0.0099] {
            XCTAssertEqual(ExternalSurfaceProbabilityFormat.openProbability(p), "<1%", "p=\(p)")
            XCTAssertEqual(ExternalSurfaceProbabilityFormat.openWholePercent(1, probability: p), "<1%", "p=\(p)")
        }
        for p in [0.9901, 0.992, 0.995, 0.996, 0.9999, 1.0] {
            XCTAssertEqual(ExternalSurfaceProbabilityFormat.openProbability(p), ">99%", "p=\(p)")
            XCTAssertEqual(ExternalSurfaceProbabilityFormat.openWholePercent(99, probability: p), ">99%", "p=\(p)")
        }
        XCTAssertEqual(ExternalSurfaceProbabilityFormat.openProbability(0.01), "1%")
        XCTAssertEqual(ExternalSurfaceProbabilityFormat.openProbability(0.50), "50%")
        XCTAssertEqual(ExternalSurfaceProbabilityFormat.openProbability(0.99), "99%")
        XCTAssertEqual(ExternalSurfaceProbabilityFormat.openWholePercent(0), "<1%")
        XCTAssertEqual(ExternalSurfaceProbabilityFormat.openWholePercent(100), ">99%")
        XCTAssertNil(ExternalSurfaceProbabilityFormat.openProbability(nil))
        XCTAssertEqual(ExternalSurfaceProbabilityFormat.missingProbabilityText, "No recent probability")
    }

    func testHomeScreenAndDiscoverWidgetModelsRespectSubOneAbove99AndNoZeroHundred() {
        let game = WidgetGame(
            id: 901,
            homeTeam: "Boston Celtics",
            awayTeam: "Washington Wizards",
            homeAbbrev: "BOS",
            awayAbbrev: "WAS",
            homeScore: 112,
            awayScore: 74,
            homeProb: 99,
            awayProb: 1,
            period: "Q4 2:10",
            sport: "NBA",
            homeColor: "#007A33",
            awayColor: "#002B5C",
            homeProbability: 0.996,
            awayProbability: 0.004
        )
        XCTAssertEqual(game.awayProbText, "<1%")
        XCTAssertEqual(game.homeProbText, ">99%")
        XCTAssertEqual(game.compactProbHeaderText, "<1%·>99%")

        let withheldThreeWay = WidgetGame(
            id: 902,
            homeTeam: "Arsenal",
            awayTeam: "Southampton",
            homeAbbrev: "ARS",
            awayAbbrev: "SOU",
            homeScore: 4,
            awayScore: 0,
            homeProb: 100,
            awayProb: nil,
            period: "88'",
            sport: "EPL",
            homeColor: "#EF0107",
            awayColor: "#D71920",
            homeProbability: 0.996,
            awayProbability: nil
        )
        XCTAssertEqual(withheldThreeWay.homeProbText, ">99%")
        XCTAssertEqual(withheldThreeWay.compactProbHeaderText, "ARS >99%")

        let longshot = WidgetDiscoverItem(
            id: 903,
            name: "NHL Champion",
            category: "NHL",
            leader: "Sharks",
            probability: 1,
            movement: 0,
            hookDescription: nil,
            headline: nil,
            rawProbability: 0.006
        )
        XCTAssertEqual(longshot.probabilityText, "<1%")
    }

    func testSavedLockScreenMatchup13432AndLiveActivityUseUnifiedRules() throws {
        let iso = ISO8601DateFormatter()
        let obsStr = iso.string(from: fixedNow.addingTimeInterval(-30))

        // 1. Live 2-way SavedLockScreenMatchup13432 (`0.004` / `0.996`)
        let twoWayJSON = """
        {
          "id": 801,
          "sport": "basketball_nba",
          "home_team": "Boston Celtics",
          "away_team": "Washington Wizards",
          "status": "live",
          "home_score": 112,
          "away_score": 74,
          "current_odds": {
            "home_probability": 0.996,
            "away_probability": 0.004,
            "home_rendered_percent": 100,
            "away_rendered_percent": 0
          },
          "hero_probability": 0.996,
          "hero_probability_away": 0.004,
          "hero_probability_observed_at": "\(obsStr)",
          "home_team_data": {"abbreviation": "BOS", "primary_color": "#007A33"},
          "away_team_data": {"abbreviation": "WAS", "primary_color": "#002B5C"}
        }
        """
        let twoWayEvent = try SavedWidgetDetailDecoding10875.decoder().decode(
            SavedWidgetEventDetail10875.self,
            from: Data(twoWayJSON.utf8)
        )
        let twoWayReading = SavedWidgetReadingRules10875.game(twoWayEvent, side: nil, now: fixedNow)
        let twoWayArt = SavedWidgetArt12466.game(twoWayEvent)
        if case .matchup(let m) = SavedLockScreenMatchupAdapter13432.resolve(
            event: twoWayEvent, reading: twoWayReading, art: twoWayArt,
            logos: .init(), side: nil, isOffline: false, now: fixedNow
        ) {
            XCTAssertEqual(m.bigText, ">99%")
        } else {
            XCTFail("Expected matchup state for live 2-way lock screen widget")
        }
        if case .matchup(let awaySide) = SavedLockScreenMatchupAdapter13432.resolve(
            event: twoWayEvent,
            reading: SavedWidgetReadingRules10875.game(twoWayEvent, side: .away, now: fixedNow),
            art: twoWayArt, logos: .init(), side: .away, isOffline: false, now: fixedNow
        ) {
            XCTAssertEqual(awaySide.bigText, "<1%")
        } else {
            XCTFail("Expected matchup state for live 2-way away lock screen widget")
        }

        // 2. Live 3-way SavedLockScreenMatchup13432 (`0.004` / `0.005` / `0.991`)
        let threeWayJSON = """
        {
          "id": 802,
          "sport": "soccer_epl",
          "home_team": "Arsenal",
          "away_team": "Southampton",
          "status": "live",
          "home_score": 0,
          "away_score": 5,
          "current_odds": {
            "home_probability": 0.004,
            "draw_probability": 0.005,
            "away_probability": 0.991
          },
          "hero_probability": 0.004,
          "hero_probability_observed_at": "\(obsStr)",
          "home_team_data": {"abbreviation": "ARS", "primary_color": "#EF0107"},
          "away_team_data": {"abbreviation": "SOU", "primary_color": "#D71920"}
        }
        """
        let threeWayEvent = try SavedWidgetDetailDecoding10875.decoder().decode(
            SavedWidgetEventDetail10875.self,
            from: Data(threeWayJSON.utf8)
        )
        let threeWayReading = SavedWidgetReadingRules10875.game(threeWayEvent, side: nil, now: fixedNow)
        let threeWayArt = SavedWidgetArt12466.game(threeWayEvent)
        if case .matchup(let three) = SavedLockScreenMatchupAdapter13432.resolve(
            event: threeWayEvent, reading: threeWayReading, art: threeWayArt,
            logos: .init(), side: nil, isOffline: false, now: fixedNow
        ) {
            XCTAssertEqual(three.threeWay?.homeText, "<1%")
            XCTAssertEqual(three.threeWay?.drawText, "<1%")
            XCTAssertEqual(three.threeWay?.awayText, ">99%")
            XCTAssertEqual(three.bigText, ">99%")
        } else {
            XCTFail("Expected matchup state for 3-way lock screen widget")
        }

        // 3. Final Lock Screen matchup + SavedGameHeadlineWidget12616 pregame <1% upset + missing odds
        let upsetJSON = """
        {
          "id": 803,
          "sport": "basketball_nba",
          "home_team": "Detroit Pistons",
          "away_team": "Boston Celtics",
          "status": "completed",
          "home_score": 105,
          "away_score": 104,
          "score_observed_at": "\(obsStr)",
          "hero_settled_result": "home",
          "prematch_odds": {
            "home_probability": 0.004,
            "away_probability": 0.996
          },
          "home_team_data": {"abbreviation": "DET", "primary_color": "#C8102E"},
          "away_team_data": {"abbreviation": "BOS", "primary_color": "#007A33"}
        }
        """
        let upsetEvent = try SavedWidgetDetailDecoding10875.decoder().decode(
            SavedWidgetEventDetail10875.self,
            from: Data(upsetJSON.utf8)
        )
        let upsetReading = SavedWidgetReadingRules10875.game(upsetEvent, side: nil, now: fixedNow)
        let upsetArt = SavedWidgetArt12466.game(upsetEvent)
        if case .matchup(let finalMatchup) = SavedLockScreenMatchupAdapter13432.resolve(
            event: upsetEvent, reading: upsetReading, art: upsetArt,
            logos: .init(), side: nil, isOffline: false, now: fixedNow
        ) {
            XCTAssertEqual(finalMatchup.bigText, "<1%")
        } else {
            XCTFail("Expected matchup state for final upset lock screen widget")
        }
        let headlineModel = SavedGameHeadlineWidgetModel12616.build(
            reading: upsetReading,
            art: upsetArt,
            clockFooter: nil,
            isOffline: false,
            clearsRefreshTrailing: true
        )
        XCTAssertTrue(headlineModel.mediumFooter.contains("<1% pregame chance"), headlineModel.mediumFooter)

        let unpricedWidgetJSON = """
        {
          "id": 804,
          "sport": "basketball_nba",
          "home_team": "Orlando Magic",
          "away_team": "Miami Heat",
          "status": "live",
          "home_score": 46,
          "away_score": 44
        }
        """
        let unpricedWidgetEvent = try SavedWidgetDetailDecoding10875.decoder().decode(
            SavedWidgetEventDetail10875.self,
            from: Data(unpricedWidgetJSON.utf8)
        )
        let unavailableWidgetReading = SavedWidgetReadingRules10875.game(unpricedWidgetEvent, side: nil, now: fixedNow)
        XCTAssertEqual(unavailableWidgetReading.phase, .unavailable)
        XCTAssertTrue(unavailableWidgetReading.spoken.contains("No recent probability"), unavailableWidgetReading.spoken)
        XCTAssertFalse(unavailableWidgetReading.spoken.localizedCaseInsensitiveContains("no chance to show"))

        // 4. Live Activities (`GameActivitySnapshot` + `GameLiveActivity`)
        let snapshot = try XCTUnwrap(GameActivitySnapshot(
            eventID: 904,
            homeTeam: "Boston Celtics",
            awayTeam: "Detroit Pistons",
            lifecycle: .live,
            homeScore: 108,
            awayScore: 72,
            homeProbability: 0.994,
            awayProbability: 0.006,
            sport: "basketball_nba",
            scoreObservedAt: fixedNow.addingTimeInterval(-15),
            probabilityObservedAt: fixedNow.addingTimeInterval(-15),
            homeAbbreviation: "BOS",
            awayAbbreviation: "DET",
            homeColorHex: "#007A33",
            awayColorHex: "#C8102E",
            periodLabel: "Q4 3:12"
        ))
        XCTAssertEqual(snapshot.probabilityText, ">99%")
        let liveReading = GameActivityReading(snapshot: snapshot, eventID: 904)
        XCTAssertEqual(liveReading.nowText(.home), ">99%")
        XCTAssertEqual(liveReading.nowText(.away), "<1%")
        XCTAssertEqual(liveReading.minimalNowText(.home), ">99%")
        XCTAssertFalse(liveReading.chanceSpoken.contains("100%"))
        XCTAssertFalse(liveReading.chanceSpoken.contains("0%"))
        XCTAssertTrue(liveReading.chanceSpoken.contains("<1%"))
        XCTAssertTrue(liveReading.chanceSpoken.contains(">99%"))

        let missingOdds = try XCTUnwrap(GameActivitySnapshot(
            eventID: 905,
            homeTeam: "Chicago Bulls",
            awayTeam: "Atlanta Hawks",
            lifecycle: .live,
            homeScore: 54,
            awayScore: 51,
            homeProbability: nil,
            awayProbability: nil,
            sport: "basketball_nba",
            scoreObservedAt: fixedNow.addingTimeInterval(-10),
            probabilityObservedAt: nil,
            homeAbbreviation: "CHI",
            awayAbbreviation: "ATL",
            periodLabel: "Q2 1:20"
        ))
        let missingReading = GameActivityReading(snapshot: missingOdds, eventID: 905)
        XCTAssertEqual(missingReading.chanceSpoken, "No recent probability")
    }

    func testLiveActivityDecodesServerPushedExtremesWithAndWithoutMarkKeys() throws {
        let obsSec = fixedNow.addingTimeInterval(-15).timeIntervalSinceReferenceDate

        // 1. Option (b) backward compatibility + Fable's server-shaped test:
        // No mark keys in content-state JSON, home side at 0.6% (`homeHeadlineTenths: 6`).
        let legacyPushJSON = """
        {
          "snapshot": {
            "eventID": 910,
            "homeTeam": "Washington Wizards",
            "awayTeam": "Boston Celtics",
            "lifecycle": "live",
            "homeScore": 74,
            "awayScore": 112,
            "homeRenderedPercent": 1,
            "awayRenderedPercent": 99,
            "homeHeadlineTenths": 6,
            "sport": "basketball_nba",
            "homeAbbreviation": "WAS",
            "awayAbbreviation": "BOS",
            "homeColorHex": "#002B5C",
            "awayColorHex": "#007A33",
            "periodLabel": "Q4",
            "scoreObservedAt": \(obsSec),
            "probabilityObservedAt": \(obsSec)
          }
        }
        """
        let legacyState = try JSONDecoder().decode(
            GameActivityAttributes.ContentState.self,
            from: Data(legacyPushJSON.utf8)
        )
        XCTAssertEqual(legacyState.snapshot.homeSubOne, true)
        XCTAssertNil(legacyState.snapshot.homeAboveNinetyNine)
        XCTAssertNil(legacyState.snapshot.awaySubOne)
        XCTAssertEqual(legacyState.snapshot.awayAboveNinetyNine, true)
        XCTAssertEqual(legacyState.snapshot.probabilityText, "<1%")
        let legacyReading = GameActivityReading(snapshot: legacyState.snapshot, eventID: 910)
        XCTAssertEqual(legacyReading.nowText(.home), "<1%")
        XCTAssertEqual(legacyReading.nowText(.away), ">99%")
        XCTAssertEqual(legacyReading.minimalNowText(.home), "<1%")

        // 2. Exact 1.0% / 99.0% boundary (`homeHeadlineTenths: 10`, no mark keys) stays `1%` / `99%`.
        let onePercentPushJSON = legacyPushJSON.replacingOccurrences(
            of: "\"homeHeadlineTenths\": 6",
            with: "\"homeHeadlineTenths\": 10"
        )
        let onePercentState = try JSONDecoder().decode(
            GameActivityAttributes.ContentState.self,
            from: Data(onePercentPushJSON.utf8)
        )
        XCTAssertNil(onePercentState.snapshot.homeSubOne)
        XCTAssertNil(onePercentState.snapshot.awayAboveNinetyNine)
        let onePercentReading = GameActivityReading(snapshot: onePercentState.snapshot, eventID: 910)
        XCTAssertEqual(onePercentReading.nowText(.home), "1%")
        XCTAssertEqual(onePercentReading.nowText(.away), "99%")

        // 3. Option (a) server mark keys cover both exact two-way (`homeSubOne` + `awayAboveNinetyNine`)
        // and 3-way soccer single-chance (`awayRenderedPercent` and `homeHeadlineTenths` absent).
        let soccerMarkJSON = """
        {
          "snapshot": {
            "eventID": 911,
            "homeTeam": "Southampton",
            "awayTeam": "Arsenal",
            "lifecycle": "live",
            "homeScore": 0,
            "awayScore": 4,
            "homeRenderedPercent": 1,
            "homeSubOne": true,
            "sport": "soccer_epl",
            "homeAbbreviation": "SOU",
            "awayAbbreviation": "ARS",
            "scoreObservedAt": \(obsSec),
            "probabilityObservedAt": \(obsSec)
          }
        }
        """
        let soccerState = try JSONDecoder().decode(
            GameActivityAttributes.ContentState.self,
            from: Data(soccerMarkJSON.utf8)
        )
        XCTAssertEqual(soccerState.snapshot.homeSubOne, true)
        XCTAssertEqual(soccerState.snapshot.probabilityText, "<1%")
        let soccerReading = GameActivityReading(snapshot: soccerState.snapshot, eventID: 911)
        XCTAssertNil(soccerReading.nowText(.away))

        let finalPregameJSON = """
        {
          "snapshot": {
            "eventID": 912,
            "homeTeam": "Detroit Pistons",
            "awayTeam": "Boston Celtics",
            "lifecycle": "final",
            "homeScore": 105,
            "awayScore": 104,
            "result": "home",
            "sport": "basketball_nba",
            "pregameHomePercent": 1,
            "pregameAwayPercent": 99,
            "pregameHomeSubOne": true,
            "pregameAwayAboveNinetyNine": true,
            "scoreObservedAt": \(obsSec)
          }
        }
        """
        let finalState = try JSONDecoder().decode(
            GameActivityAttributes.ContentState.self,
            from: Data(finalPregameJSON.utf8)
        )
        let finalReading = GameActivityReading(snapshot: finalState.snapshot, eventID: 912)
        XCTAssertEqual(finalReading.pregameText(.home), "<1%")
        XCTAssertEqual(finalReading.pregameText(.away), ">99%")
    }

    func testWatchAppAndComplicationsUnifyExtremesAndNoRecentProbability() throws {
        let extremeGameJSON = #"""
        {
          "id": 906,
          "away_team": "Charlotte Hornets",
          "home_team": "Cleveland Cavaliers",
          "away_team_data": {"team_id": 5312, "abbreviation": "CHA", "primary_color": "#1D1160", "secondary_color": "#00788C"},
          "home_team_data": {"team_id": 5313, "abbreviation": "CLE", "primary_color": "#860038", "secondary_color": "#FDBB30"},
          "status": "live",
          "sport": "basketball_nba",
          "away_score": 68,
          "home_score": 109,
          "score_observed_at": "2026-11-20T22:18:00Z",
          "espn": {"period": "4th Quarter", "game_clock": "01:12"},
          "hero_probability": 0.994,
          "hero_probability_away": 0.006,
          "hero_probability_observed_at": "2026-11-20T22:18:00Z"
        }
        """#
        let game = try JSONDecoder().decode(WatchSelectedGame.self, from: Data(extremeGameJSON.utf8))
        XCTAssertEqual(game.homeProbabilityText, ">99%")

        let hero = WatchMatchupGameHeroModel297A.build(
            from: game,
            now: game.probabilityObservedAt?.addingTimeInterval(20) ?? fixedNow,
            crestForTeamID: { _ in nil }
        )
        XCTAssertEqual(hero.away.currentPercentText, "<1%")
        XCTAssertEqual(hero.home.currentPercentText, ">99%")

        let published = try XCTUnwrap(WatchComplicationProjection.snapshot(
            game: game,
            savedAt: game.probabilityObservedAt?.addingTimeInterval(5) ?? fixedNow
        ))
        XCTAssertEqual(published.detail, ">99% · Live")
        XCTAssertEqual(published.circularReading?.value, ">99%")
        XCTAssertEqual(published.rectangularReading?.formattedHomePercent, ">99%")
        let small = try XCTUnwrap(published.smallSlotModel(now: game.probabilityObservedAt?.addingTimeInterval(5) ?? fixedNow))
        XCTAssertEqual(small.value, ">99%")
        let matchup = try XCTUnwrap(WatchMatchupReading217.make(
            snapshot: published,
            now: game.probabilityObservedAt?.addingTimeInterval(5) ?? fixedNow,
            crest: { _ in nil }
        ))
        XCTAssertEqual(matchup.bigText, ">99%")

        let subOnePin = try XCTUnwrap(WatchPinsPercent12640.format(0.007))
        XCTAssertEqual(subOnePin.display, "<1%")
        let above99Pin = try XCTUnwrap(WatchPinsPercent12640.format(0.993))
        XCTAssertEqual(above99Pin.display, ">99%")
        XCTAssertEqual(WatchFaceUnavailableReason13339.noLiveOdds.complicationHeadline, "No recent probability")

        let unpricedJSON = #"""
        {
          "id": 907,
          "away_team": "Miami Heat",
          "home_team": "Orlando Magic",
          "away_team_data": {"team_id": 5314, "abbreviation": "MIA"},
          "home_team_data": {"team_id": 5315, "abbreviation": "ORL"},
          "status": "live",
          "sport": "basketball_nba",
          "away_score": 44,
          "home_score": 46
        }
        """#
        let unpricedGame = try JSONDecoder().decode(WatchSelectedGame.self, from: Data(unpricedJSON.utf8))
        let unpricedHero = WatchMatchupGameHeroModel297A.build(from: unpricedGame, now: fixedNow, crestForTeamID: { _ in nil })
        XCTAssertEqual(unpricedHero.probabilityUnavailableText, "No recent probability")
    }

    func testPreStartMissingProbabilityUsesNoProbabilityYetAcrossAllExternalSurfaces() throws {
        XCTAssertEqual(ExternalSurfaceProbabilityFormat.noProbabilityYetText, "No probability yet")
        XCTAssertEqual(
            ExternalSurfaceProbabilityFormat.missingProbabilityText(hasStarted: false, hadPriorNumber: false),
            "No probability yet"
        )
        XCTAssertEqual(
            ExternalSurfaceProbabilityFormat.missingProbabilityText(hasStarted: true, hadPriorNumber: false),
            "No recent probability"
        )
        XCTAssertEqual(
            ExternalSurfaceProbabilityFormat.missingProbabilityText(hasStarted: false, hadPriorNumber: true),
            "No recent probability"
        )

        let iso = ISO8601DateFormatter()
        let futureKickoff = iso.string(from: fixedNow.addingTimeInterval(7200))
        let pastKickoff = iso.string(from: fixedNow.addingTimeInterval(-1800))
        let obsStr = iso.string(from: fixedNow.addingTimeInterval(-3600))

        // 1. Saved Home/Lock Widget readings (`SavedWidgetReadingRules10875` + source wiring in `BainLuckWidget`).
        func decodeSavedEvent(_ json: String) throws -> SavedWidgetEventDetail10875 {
            try SavedWidgetDetailDecoding10875.decoder().decode(SavedWidgetEventDetail10875.self, from: Data(json.utf8))
        }
        let preStartSavedEvent = try decodeSavedEvent("""
        {
          "id": 920,
          "sport": "basketball_nba",
          "home_team": "Miami Heat",
          "away_team": "Orlando Magic",
          "status": "scheduled",
          "commence_time": "\(futureKickoff)",
          "home_team_data": {"abbreviation": "MIA", "primary_color": "#98002E"},
          "away_team_data": {"abbreviation": "ORL", "primary_color": "#0077C0"}
        }
        """)
        let preStartSavedReading = SavedWidgetReadingRules10875.game(preStartSavedEvent, side: nil, now: fixedNow)
        XCTAssertEqual(preStartSavedReading.phase, .unavailable)
        XCTAssertTrue(preStartSavedReading.hasNotStartedWithoutNumber)
        XCTAssertEqual(preStartSavedReading.unavailableProbabilityText, "No probability yet")
        XCTAssertTrue(preStartSavedReading.spoken.contains("No probability yet"))

        let startedSavedEvent = try decodeSavedEvent("""
        {
          "id": 921,
          "sport": "basketball_nba",
          "home_team": "Miami Heat",
          "away_team": "Orlando Magic",
          "status": "scheduled",
          "commence_time": "\(pastKickoff)"
        }
        """)
        let startedSavedReading = SavedWidgetReadingRules10875.game(startedSavedEvent, side: nil, now: fixedNow)
        XCTAssertFalse(startedSavedReading.hasNotStartedWithoutNumber)
        XCTAssertEqual(startedSavedReading.unavailableProbabilityText, "No recent probability")
        XCTAssertTrue(startedSavedReading.spoken.contains("No recent probability"))

        let priorObsSavedEvent = try decodeSavedEvent("""
        {
          "id": 922,
          "sport": "basketball_nba",
          "home_team": "Miami Heat",
          "away_team": "Orlando Magic",
          "status": "scheduled",
          "commence_time": "\(futureKickoff)",
          "hero_probability_observed_at": "\(obsStr)"
        }
        """)
        XCTAssertEqual(
            SavedWidgetReadingRules10875.game(priorObsSavedEvent, side: nil, now: fixedNow).unavailableProbabilityText,
            "No recent probability"
        )

        let unknownStartSavedEvent = try decodeSavedEvent("""
        {
          "id": 923,
          "sport": "basketball_nba",
          "home_team": "Miami Heat",
          "away_team": "Orlando Magic",
          "status": "scheduled"
        }
        """)
        XCTAssertEqual(
            SavedWidgetReadingRules10875.game(unknownStartSavedEvent, side: nil, now: fixedNow).unavailableProbabilityText,
            "No recent probability"
        )

        let widgetRoot = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("BainLuckWidget")
        let savedWidgetSource = try String(contentsOf: widgetRoot.appendingPathComponent("SavedItemWidget10875.swift"), encoding: .utf8)
        let savedLooksSource = try String(contentsOf: widgetRoot.appendingPathComponent("SavedWidgetLooks12466.swift"), encoding: .utf8)
        XCTAssertTrue(savedWidgetSource.contains("reading.unavailableProbabilityText"))
        XCTAssertTrue(savedLooksSource.contains("model.reading.unavailableProbabilityText"))

        // 2. Lock Screen Matchup helper (`WatchMatchupReading217.resolveOutcomePresentation`).
        let preStartMatchup = WatchMatchupReading217.resolveOutcomePresentation(
            homePercent: -1,
            homeName: "Miami Heat",
            awayName: "Orlando Magic",
            homeAbbreviation: "MIA",
            awayAbbreviation: "ORL",
            isThreeWay: false,
            drawPercent: nil,
            awayPercent: nil,
            missingProbabilityText: ExternalSurfaceProbabilityFormat.missingProbabilityText(hasStarted: false)
        )
        XCTAssertEqual(preStartMatchup.bigText, "No probability yet")
        let startedMatchup = WatchMatchupReading217.resolveOutcomePresentation(
            homePercent: -1,
            homeName: "Miami Heat",
            awayName: "Orlando Magic",
            homeAbbreviation: "MIA",
            awayAbbreviation: "ORL",
            isThreeWay: false,
            drawPercent: nil,
            awayPercent: nil
        )
        XCTAssertEqual(startedMatchup.bigText, "No recent probability")

        // 3. Live Activities (`GameActivityReading`).
        let preStartActivitySnap = try XCTUnwrap(GameActivitySnapshot(
            eventID: 924,
            homeTeam: "Miami Heat",
            awayTeam: "Orlando Magic",
            lifecycle: .scheduled,
            homeScore: nil,
            awayScore: nil,
            homeProbability: nil,
            awayProbability: nil,
            sport: "basketball_nba",
            scoreObservedAt: nil,
            probabilityObservedAt: nil,
            homeAbbreviation: "MIA",
            awayAbbreviation: "ORL",
            homeColorHex: "#98002E",
            awayColorHex: "#0077C0",
            periodLabel: "7:00 PM"
        ))
        let preStartActivity = GameActivityReading(snapshot: preStartActivitySnap, eventID: 924)
        XCTAssertEqual(preStartActivity.missingProbabilityText, "No probability yet")
        XCTAssertEqual(preStartActivity.chanceSpoken, "No probability yet")
        XCTAssertEqual(preStartActivity.percentText(105), "No probability yet")

        let priorActivityJSON = """
        {
          "snapshot": {
            "eventID": 925,
            "homeTeam": "Miami Heat",
            "awayTeam": "Orlando Magic",
            "lifecycle": "scheduled",
            "sport": "basketball_nba",
            "pregameHomePercent": 54,
            "pregameAwayPercent": 46
          }
        }
        """
        let priorActivityState = try JSONDecoder().decode(
            GameActivityAttributes.ContentState.self,
            from: Data(priorActivityJSON.utf8)
        )
        let priorActivity = GameActivityReading(snapshot: priorActivityState.snapshot, eventID: 925)
        XCTAssertEqual(priorActivity.missingProbabilityText, "No recent probability")

        let liveMissingSnap = try XCTUnwrap(GameActivitySnapshot(
            eventID: 926,
            homeTeam: "Miami Heat",
            awayTeam: "Orlando Magic",
            lifecycle: .live,
            homeScore: 46,
            awayScore: 44,
            homeProbability: nil,
            awayProbability: nil,
            sport: "basketball_nba",
            scoreObservedAt: fixedNow,
            probabilityObservedAt: nil,
            homeAbbreviation: "MIA",
            awayAbbreviation: "ORL",
            homeColorHex: "#98002E",
            awayColorHex: "#0077C0",
            periodLabel: "Q2 5:12"
        ))
        XCTAssertEqual(GameActivityReading(snapshot: liveMissingSnap, eventID: 926).missingProbabilityText, "No recent probability")

        // 4. Apple Watch app & complications (`WatchSelectedGame`, `WatchMatchupGameHeroModel297A`, `WatchComplicationProjection`, `WatchRectangularReading`).
        let preStartWatchJSON = """
        {
          "id": 927,
          "away_team": "Orlando Magic",
          "home_team": "Miami Heat",
          "away_team_data": {"team_id": 5320, "abbreviation": "ORL"},
          "home_team_data": {"team_id": 5321, "abbreviation": "MIA"},
          "status": "scheduled",
          "commence_time": "\(futureKickoff)",
          "sport": "basketball_nba"
        }
        """
        let preStartWatchGame = try JSONDecoder().decode(WatchSelectedGame.self, from: Data(preStartWatchJSON.utf8))
        XCTAssertFalse(preStartWatchGame.hasStarted(at: fixedNow))
        XCTAssertFalse(preStartWatchGame.hadPriorProbability)
        XCTAssertEqual(preStartWatchGame.missingProbabilityText(at: fixedNow), "No probability yet")
        XCTAssertEqual(
            WatchMatchupGameHeroModel297A.build(from: preStartWatchGame, now: fixedNow, crestForTeamID: { _ in nil }).probabilityUnavailableText,
            "No probability yet"
        )
        if case .unavailable(let preFaceStatus, _) = WatchComplicationProjection.evaluateEventFaceState(
            game: preStartWatchGame,
            eventID: 927,
            isAdmitted: true,
            savedAt: fixedNow,
            clockSkewTolerance: 15,
            containerAvailable: true
        ) {
            XCTAssertEqual(preFaceStatus.reason, .noProbabilityYet)
            XCTAssertEqual(preFaceStatus.reason.complicationHeadline, "No probability yet")
        } else {
            XCTFail("Expected .noProbabilityYet unavailable status")
        }

        let startedWatchJSON = """
        {
          "id": 928,
          "away_team": "Orlando Magic",
          "home_team": "Miami Heat",
          "away_team_data": {"team_id": 5320, "abbreviation": "ORL"},
          "home_team_data": {"team_id": 5321, "abbreviation": "MIA"},
          "status": "scheduled",
          "commence_time": "\(pastKickoff)",
          "sport": "basketball_nba"
        }
        """
        let startedWatchGame = try JSONDecoder().decode(WatchSelectedGame.self, from: Data(startedWatchJSON.utf8))
        XCTAssertTrue(startedWatchGame.hasStarted(at: fixedNow))
        XCTAssertEqual(startedWatchGame.missingProbabilityText(at: fixedNow), "No recent probability")
        XCTAssertEqual(
            WatchMatchupGameHeroModel297A.build(from: startedWatchGame, now: fixedNow, crestForTeamID: { _ in nil }).probabilityUnavailableText,
            "No recent probability"
        )
        if case .unavailable(let startedFaceStatus, _) = WatchComplicationProjection.evaluateEventFaceState(
            game: startedWatchGame,
            eventID: 928,
            isAdmitted: true,
            savedAt: fixedNow,
            clockSkewTolerance: 15,
            containerAvailable: true
        ) {
            XCTAssertEqual(startedFaceStatus.reason, .noLiveOdds)
            XCTAssertEqual(startedFaceStatus.reason.complicationHeadline, "No recent probability")
        } else {
            XCTFail("Expected .noLiveOdds unavailable status")
        }

        let priorPrematchWatchJSON = """
        {
          "id": 929,
          "away_team": "Orlando Magic",
          "home_team": "Miami Heat",
          "away_team_data": {"team_id": 5320, "abbreviation": "ORL"},
          "home_team_data": {"team_id": 5321, "abbreviation": "MIA"},
          "status": "scheduled",
          "commence_time": "\(futureKickoff)",
          "prematch_odds": {"home_probability": 0.55, "away_probability": 0.45},
          "sport": "basketball_nba"
        }
        """
        let priorPrematchGame = try JSONDecoder().decode(WatchSelectedGame.self, from: Data(priorPrematchWatchJSON.utf8))
        XCTAssertTrue(priorPrematchGame.hadPriorProbability)
        XCTAssertEqual(priorPrematchGame.missingProbabilityText(at: fixedNow), "No recent probability")

        let mia = WatchCompactTeamIdentity(teamID: 14, abbreviation: "MIA")
        let orl = WatchCompactTeamIdentity(teamID: 19, abbreviation: "ORL")
        let preRect = WatchRectangularReading(
            version: 1, eventID: 927, kind: .scheduledForecast,
            homeName: "Miami Heat", awayName: "Orlando Magic",
            home: mia, away: orl, homePercent: nil, homeScore: nil, awayScore: nil,
            commenceTime: fixedNow.addingTimeInterval(7200), stateLabel: "Scheduled",
            observedAt: fixedNow, scoreObservedAt: nil
        )
        XCTAssertEqual(preRect.primaryLine(at: fixedNow), "No probability yet")
        let startedRect = WatchRectangularReading(
            version: 1, eventID: 928, kind: .scheduledForecast,
            homeName: "Miami Heat", awayName: "Orlando Magic",
            home: mia, away: orl, homePercent: nil, homeScore: nil, awayScore: nil,
            commenceTime: fixedNow.addingTimeInterval(-60), stateLabel: "Scheduled",
            observedAt: fixedNow, scoreObservedAt: nil
        )
        XCTAssertEqual(startedRect.primaryLine(at: fixedNow), "No recent probability")
        let marketRect = WatchRectangularReading(
            version: 1, eventID: 930, kind: .futureForecast,
            homeName: "NBA Champion", awayName: "Boston Celtics",
            home: nil, away: nil, homePercent: nil, homeScore: nil, awayScore: nil,
            commenceTime: fixedNow.addingTimeInterval(7200), stateLabel: "Open",
            observedAt: fixedNow, scoreObservedAt: nil
        )
        XCTAssertEqual(marketRect.primaryLine(at: fixedNow), "No recent probability")
    }

    #if canImport(UIKit)
    func testExportItem7ExternalSurfacesSheet() throws {
        guard ProcessInfo.processInfo.environment["BAINLUCK_EXPORT_ITEM7_SHEET"] == "1" else {
            throw XCTSkip("Set BAINLUCK_EXPORT_ITEM7_SHEET=1 to export simulator contact sheet PNG")
        }

        let obs = fixedNow.addingTimeInterval(-30)
        let extremeGame = WidgetGame(
            id: 1,
            homeTeam: "Boston Celtics",
            awayTeam: "Washington Wizards",
            homeAbbrev: "BOS",
            awayAbbrev: "WAS",
            homeScore: 112,
            awayScore: 74,
            homeProb: 99,
            awayProb: 1,
            period: "Q4 2:10",
            sport: "NBA",
            homeColor: "#007A33",
            awayColor: "#002B5C",
            homeProbability: 0.996,
            awayProbability: 0.004
        )
        let secondGame = WidgetGame(
            id: 2,
            homeTeam: "Edmonton Oilers",
            awayTeam: "San Jose Sharks",
            homeAbbrev: "EDM",
            awayAbbrev: "SJS",
            homeScore: 6,
            awayScore: 1,
            homeProb: 99,
            awayProb: 1,
            period: "3rd 4:15",
            sport: "NHL",
            homeColor: "#FF4C00",
            awayColor: "#006D75",
            homeProbability: 0.992,
            awayProbability: 0.008
        )
        let entry = BainLuckWidgetEntry(
            date: fixedNow,
            liveGames: [extremeGame, secondGame],
            discoverItems: [
                WidgetDiscoverItem(
                    id: 10,
                    name: "Eastern Conf Winner",
                    category: "NBA",
                    leader: "Celtics",
                    probability: 99,
                    movement: 2,
                    hookDescription: nil,
                    headline: nil,
                    rawProbability: 0.994
                ),
                WidgetDiscoverItem(
                    id: 11,
                    name: "Presidents Trophy",
                    category: "NHL",
                    leader: "Sharks",
                    probability: 1,
                    movement: 0,
                    hookDescription: nil,
                    headline: nil,
                    rawProbability: 0.006
                ),
            ]
        )

        let liveSnap = try XCTUnwrap(GameActivitySnapshot(
            eventID: 201,
            homeTeam: "Boston Celtics",
            awayTeam: "Washington Wizards",
            lifecycle: .live,
            homeScore: 112,
            awayScore: 74,
            homeProbability: 0.996,
            awayProbability: 0.004,
            sport: "basketball_nba",
            scoreObservedAt: obs,
            probabilityObservedAt: obs,
            homeAbbreviation: "BOS",
            awayAbbreviation: "WAS",
            homeColorHex: "#007A33",
            awayColorHex: "#002B5C",
            periodLabel: "Q4 2:10"
        ))
        let missingSnap = try XCTUnwrap(GameActivitySnapshot(
            eventID: 202,
            homeTeam: "Orlando Magic",
            awayTeam: "Miami Heat",
            lifecycle: .live,
            homeScore: 46,
            awayScore: 44,
            homeProbability: nil,
            awayProbability: nil,
            sport: "basketball_nba",
            scoreObservedAt: obs,
            probabilityObservedAt: nil,
            homeAbbreviation: "ORL",
            awayAbbreviation: "MIA",
            homeColorHex: "#0077C0",
            awayColorHex: "#98002E",
            periodLabel: "Q2 5:12"
        ))

        let det = WatchCompactTeamIdentity(teamID: 8, abbreviation: "DET")
        let bos = WatchCompactTeamIdentity(teamID: 2, abbreviation: "BOS")
        let subOneRectReading = WatchRectangularReading(
            version: 1, eventID: 301, kind: .liveForecast,
            homeName: "Boston Celtics", awayName: "Detroit Pistons",
            home: bos, away: det, homePercent: 1, homeScore: 72, awayScore: 108,
            commenceTime: nil, stateLabel: "Live", observedAt: obs, scoreObservedAt: obs,
            subOnePercent: true, aboveNinetyNinePercent: nil
        )
        let subOneWatchSnap = WatchComplicationSnapshot(
            eventID: 301, title: "Boston Celtics win", detail: "<1% · Live",
            observedAt: obs, savedAt: fixedNow,
            rectangularReading: subOneRectReading,
            matchup: WatchMatchupFacts217(
                homePrimary: "#007A33", awayPrimary: "#C8102E",
                clock: "Q4 3:12",
                awaySubOne: nil, awayAboveNinetyNine: true
            )
        )
        let matchupExtreme = WatchMatchupReading217(
            stage: .during,
            away: .init(abbreviation: "WAS", inkHex: "#5B92E5", crestPNG: nil, score: 74, isWinner: false),
            home: .init(abbreviation: "BOS", inkHex: "#10B981", crestPNG: nil, score: 112, isWinner: false),
            bigText: "<1%",
            bigOwnerLabel: "WAS",
            bigIsHome: false,
            smallLine: "Q4 2:10",
            accessibilityText: "",
            threeWay: .init(homeLabel: "BOS", homeText: ">99%", drawText: "<1%", awayLabel: "WAS", awayText: "<1%")
        )

        let watchHeroExtreme = WatchMatchupGameHeroModel297A(
            stage: .during,
            topBadgeText: "Q4 2:10",
            isLive: true,
            isThreeWaySoccer: false,
            isTiedFinal: false,
            away: .init(abbreviation: "WAS", shortName: "Wizards", teamID: 1, crestPNG: nil, fillHex: "#002B5C", inkHex: "#FFFFFF", barHex: "#5B92E5", currentPercentText: "<1%", currentShare: 0.005, score: 74, pregameText: nil, isWinner: false, isLoser: false),
            home: .init(abbreviation: "BOS", shortName: "Celtics", teamID: 2, crestPNG: nil, fillHex: "#007A33", inkHex: "#FFFFFF", barHex: "#10B981", currentPercentText: ">99%", currentShare: 0.995, score: 112, pregameText: nil, isWinner: false, isLoser: false),
            drawPercentText: nil, drawShare: nil, drawPregameText: nil,
            centerScoreText: "74–112", liveScoreExplanation: nil, finalScoreUnavailable: false,
            probabilityUnavailableText: nil, bottomSummaryText: nil,
            scoreAsOfText: "Score as of <1m", probabilityAsOfText: "Probability as of <1m"
        )
        let watchHeroMissing = WatchMatchupGameHeroModel297A(
            stage: .during,
            topBadgeText: "Q2 5:12",
            isLive: true,
            isThreeWaySoccer: false,
            isTiedFinal: false,
            away: .init(abbreviation: "MIA", shortName: "Heat", teamID: 3, crestPNG: nil, fillHex: "#98002E", inkHex: "#FFFFFF", barHex: "#98002E", currentPercentText: nil, currentShare: nil, score: 44, pregameText: nil, isWinner: false, isLoser: false),
            home: .init(abbreviation: "ORL", shortName: "Magic", teamID: 4, crestPNG: nil, fillHex: "#0077C0", inkHex: "#FFFFFF", barHex: "#0077C0", currentPercentText: nil, currentShare: nil, score: 46, pregameText: nil, isWinner: false, isLoser: false),
            drawPercentText: nil, drawShare: nil, drawPregameText: nil,
            centerScoreText: "44–46", liveScoreExplanation: nil, finalScoreUnavailable: false,
            probabilityUnavailableText: ExternalSurfaceProbabilityFormat.missingProbabilityText,
            bottomSummaryText: nil,
            scoreAsOfText: "Score as of 1m", probabilityAsOfText: nil
        )

        let missingPin = WatchFutureDetail12640(
            id: 401,
            name: "Stanley Cup Winner",
            status: "open",
            outcomes: [WatchFutureOutcome12640(id: 1, name: "Sabres", probability: 0.004)]
        )
        XCTAssertEqual(missingPin.resolvedOutcome(chosenOutcomeID: 1)?.formattedProbability?.display, "<1%")

        let sheet = VStack(alignment: .leading, spacing: 14) {
            VStack(alignment: .leading, spacing: 3) {
                Text("Item 7 · Unified Probability Formatting Across External Apple Surfaces")
                    .font(.system(size: 16, weight: .bold))
                Text("SIMULATOR RENDER SHEET — NOT PHYSICAL HARDWARE · Under 1% -> <1% · Above 99% -> >99% · Missing -> No recent probability")
                    .font(.system(size: 11, weight: .semibold))
                    .foregroundStyle(.secondary)
            }

            HStack(alignment: .top, spacing: 14) {
                tile("Home Small Widget (LiveGamesWidget)") {
                    SmallLiveGameView(entry: entry)
                        .frame(width: 158, height: 158)
                        .background(Color(uiColor: .systemBackground), in: RoundedRectangle(cornerRadius: 20))
                        .environment(\.colorScheme, .light)
                }
                tile("Home Medium Widget (<1%·>99% header & rows)") {
                    MediumLiveGamesView(entry: entry)
                        .frame(width: 338, height: 158)
                        .background(Color(uiColor: .systemBackground), in: RoundedRectangle(cornerRadius: 20))
                        .environment(\.colorScheme, .light)
                }
            }

            HStack(alignment: .top, spacing: 14) {
                tile("Live Activity Banner (<1% vs >99%)") {
                    GameActivityLockScreenView(reading: GameActivityReading(snapshot: liveSnap, eventID: 201))
                        .frame(width: 358)
                        .background(Color(uiColor: .systemBackground), in: RoundedRectangle(cornerRadius: 20))
                        .environment(\.colorScheme, .light)
                }
                tile("Live Activity Banner (Missing Prob)") {
                    GameActivityLockScreenView(reading: GameActivityReading(snapshot: missingSnap, eventID: 202))
                        .frame(width: 358)
                        .background(Color(uiColor: .systemBackground), in: RoundedRectangle(cornerRadius: 20))
                        .environment(\.colorScheme, .light)
                }
            }

            HStack(alignment: .top, spacing: 14) {
                tile("Lock Screen & Watch Matchup (<1% / >99% 3-Way)") {
                    WatchMatchupComplication217(reading: matchupExtreme)
                        .frame(width: 170, height: 68)
                        .padding(8)
                        .background(Color.black, in: RoundedRectangle(cornerRadius: 14))
                        .environment(\.colorScheme, .dark)
                        .environment(\.widgetRenderingMode, .fullColor)
                }
                tile("Watch Rectangular & Unpriced Complications (41mm & 45mm)") {
                    HStack(spacing: 10) {
                        WatchSavedComplicationContent(snapshot: subOneWatchSnap, now: fixedNow)
                            .frame(width: 162, height: 68)
                            .padding(8)
                            .background(Color.black, in: RoundedRectangle(cornerRadius: 14))
                            .environment(\.colorScheme, .dark)
                        WatchUnavailableComplicationContent13339(
                            status: WatchFaceStatusPayload13339(
                                targetID: 202,
                                title: "MIA at ORL",
                                reason: .noLiveOdds,
                                updatedAt: fixedNow
                            )
                        )
                        .frame(width: 156, height: 68)
                        .padding(8)
                        .background(Color.black, in: RoundedRectangle(cornerRadius: 14))
                        .environment(\.colorScheme, .dark)
                    }
                }
            }

            HStack(alignment: .top, spacing: 14) {
                tile("Watch Circular & Corner Complications") {
                    HStack(spacing: 12) {
                        WatchSavedCircularComplicationContent(snapshot: subOneWatchSnap, now: fixedNow)
                            .frame(width: 48, height: 48)
                            .padding(4)
                            .background(Color.black, in: Circle())
                            .environment(\.colorScheme, .dark)
                        WatchSavedCornerComplicationContent(snapshot: subOneWatchSnap, now: fixedNow)
                            .frame(width: 48, height: 48)
                            .padding(4)
                            .background(Color.black, in: Circle())
                            .environment(\.colorScheme, .dark)
                        GameActivitySmallView(reading: GameActivityReading(snapshot: liveSnap, eventID: 201))
                            .frame(width: 162, height: 74)
                            .background(Color.black, in: RoundedRectangle(cornerRadius: 16))
                            .environment(\.colorScheme, .dark)
                    }
                }
                tile("Watch Game Page Hero (<1% / >99% & No recent probability)") {
                    HStack(spacing: 10) {
                        WatchMatchupGamePageHeroView297A(model: watchHeroExtreme, caseWidth: 186)
                            .frame(width: 186)
                            .padding(6)
                            .background(Color.black, in: RoundedRectangle(cornerRadius: 16))
                            .environment(\.colorScheme, .dark)
                        WatchMatchupGamePageHeroView297A(model: watchHeroMissing, caseWidth: 186)
                            .frame(width: 186)
                            .padding(6)
                            .background(Color.black, in: RoundedRectangle(cornerRadius: 16))
                            .environment(\.colorScheme, .dark)
                    }
                }
            }
        }
        .padding(18)
        .background(Color(white: 0.94))

        let renderer = rendererForMeasurement(sheet)
        renderer.scale = 2.0
        let image = try XCTUnwrap(renderer.uiImage)
        let png = try XCTUnwrap(image.pngData())
        let outURL = URL(fileURLWithPath: "/tmp/item7-external-surfaces-sheet.png")
        try png.write(to: outURL)
        print("EXPORTED_ITEM7_SHEET=\(outURL.path) bytes=\(png.count)")
    }

    private func tile<Content: View>(_ label: String, @ViewBuilder content: () -> Content) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(label)
                .font(.system(size: 11, weight: .semibold))
                .foregroundStyle(.secondary)
            content()
        }
        .padding(10)
        .background(Color(white: 0.98), in: RoundedRectangle(cornerRadius: 12))
    }

    func testExportItem3MissingProbabilitySheet() throws {
        guard ProcessInfo.processInfo.environment["BAINLUCK_EXPORT_ITEM3_SHEET"] == "1" else {
            throw XCTSkip("Set BAINLUCK_EXPORT_ITEM3_SHEET=1 to export Item 3 Light/Dark contact sheet PNG")
        }

        let obs = fixedNow.addingTimeInterval(-30)
        let preStartActivitySnap = try XCTUnwrap(GameActivitySnapshot(
            eventID: 940,
            homeTeam: "Miami Heat",
            awayTeam: "Orlando Magic",
            lifecycle: .scheduled,
            homeScore: nil,
            awayScore: nil,
            homeProbability: nil,
            awayProbability: nil,
            sport: "basketball_nba",
            scoreObservedAt: nil,
            probabilityObservedAt: nil,
            homeAbbreviation: "MIA",
            awayAbbreviation: "ORL",
            homeColorHex: "#98002E",
            awayColorHex: "#0077C0",
            periodLabel: "7:00 PM"
        ))
        let startedActivitySnap = try XCTUnwrap(GameActivitySnapshot(
            eventID: 941,
            homeTeam: "Miami Heat",
            awayTeam: "Orlando Magic",
            lifecycle: .live,
            homeScore: 46,
            awayScore: 44,
            homeProbability: nil,
            awayProbability: nil,
            sport: "basketball_nba",
            scoreObservedAt: obs,
            probabilityObservedAt: nil,
            homeAbbreviation: "MIA",
            awayAbbreviation: "ORL",
            homeColorHex: "#98002E",
            awayColorHex: "#0077C0",
            periodLabel: "Q2 5:12"
        ))

        let iso = ISO8601DateFormatter()
        let futureKickoff = iso.string(from: fixedNow.addingTimeInterval(7200))
        let pastKickoff = iso.string(from: fixedNow.addingTimeInterval(-1800))

        let preStartSavedEvent = try SavedWidgetDetailDecoding10875.decoder().decode(
            SavedWidgetEventDetail10875.self,
            from: Data("""
            {"id": 940, "sport": "basketball_nba", "home_team": "Miami Heat", "away_team": "Orlando Magic",
             "status": "scheduled", "commence_time": "\(futureKickoff)"}
            """.utf8)
        )
        let startedSavedEvent = try SavedWidgetDetailDecoding10875.decoder().decode(
            SavedWidgetEventDetail10875.self,
            from: Data("""
            {"id": 941, "sport": "basketball_nba", "home_team": "Miami Heat", "away_team": "Orlando Magic",
             "status": "live", "commence_time": "\(pastKickoff)", "home_score": 46, "away_score": 44}
            """.utf8)
        )
        let preStartSavedReading = SavedWidgetReadingRules10875.game(preStartSavedEvent, side: nil, now: fixedNow)
        let startedSavedReading = SavedWidgetReadingRules10875.game(startedSavedEvent, side: nil, now: fixedNow)

        let preStartWatchGame = try JSONDecoder().decode(WatchSelectedGame.self, from: Data("""
        {"id": 940, "away_team": "Orlando Magic", "home_team": "Miami Heat",
         "away_team_data": {"team_id": 5320, "abbreviation": "ORL"},
         "home_team_data": {"team_id": 5321, "abbreviation": "MIA"},
         "status": "scheduled", "commence_time": "\(futureKickoff)", "sport": "basketball_nba"}
        """.utf8))
        let startedWatchGame = try JSONDecoder().decode(WatchSelectedGame.self, from: Data("""
        {"id": 941, "away_team": "Orlando Magic", "home_team": "Miami Heat",
         "away_team_data": {"team_id": 5320, "abbreviation": "ORL"},
         "home_team_data": {"team_id": 5321, "abbreviation": "MIA"},
         "status": "live", "commence_time": "\(pastKickoff)", "home_score": 46, "away_score": 44, "sport": "basketball_nba"}
        """.utf8))

        let preWatchHero = WatchMatchupGameHeroModel297A.build(from: preStartWatchGame, now: fixedNow, crestForTeamID: { _ in nil })
        let startedWatchHero = WatchMatchupGameHeroModel297A.build(from: startedWatchGame, now: fixedNow, crestForTeamID: { _ in nil })

        @ViewBuilder
        func widgetSummaryTile(reading: SavedWidgetReading10875, scheme: ColorScheme) -> some View {
            VStack(alignment: .leading, spacing: 6) {
                Text(reading.shortSubject)
                    .font(.caption.weight(.bold))
                Text(reading.status)
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                Spacer(minLength: 4)
                Text(reading.unavailableProbabilityText)
                    .font(.footnote.weight(.semibold))
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            .frame(width: 156, height: 92, alignment: .leading)
            .padding(12)
            .background(Color(uiColor: .systemBackground), in: RoundedRectangle(cornerRadius: 16))
            .environment(\.colorScheme, scheme)
        }

        let sheet = VStack(alignment: .leading, spacing: 14) {
            VStack(alignment: .leading, spacing: 3) {
                Text("Item 3 · Pre-Start vs Post-Start Missing Probability Copy (Light & Dark)")
                    .font(.system(size: 16, weight: .bold))
                Text("SIMULATOR RENDER SHEET — NOT PHYSICAL HARDWARE · Before Start (No Prior #): \"No probability yet\" · After Start / Prior #: \"No recent probability\"")
                    .font(.system(size: 11, weight: .semibold))
                    .foregroundStyle(.secondary)
            }

            HStack(alignment: .top, spacing: 14) {
                tile("Saved Widget & Lock Screen Model (Light)") {
                    HStack(spacing: 10) {
                        widgetSummaryTile(reading: preStartSavedReading, scheme: .light)
                        widgetSummaryTile(reading: startedSavedReading, scheme: .light)
                    }
                }
                tile("Saved Widget & Lock Screen Model (Dark)") {
                    HStack(spacing: 10) {
                        widgetSummaryTile(reading: preStartSavedReading, scheme: .dark)
                        widgetSummaryTile(reading: startedSavedReading, scheme: .dark)
                    }
                }
            }

            HStack(alignment: .top, spacing: 14) {
                tile("Live Activity · Pre-Start vs Started (Light)") {
                    VStack(spacing: 8) {
                        GameActivityLockScreenView(reading: GameActivityReading(snapshot: preStartActivitySnap, eventID: 940))
                            .frame(width: 348)
                            .background(Color(uiColor: .systemBackground), in: RoundedRectangle(cornerRadius: 18))
                            .environment(\.colorScheme, .light)
                        GameActivityLockScreenView(reading: GameActivityReading(snapshot: startedActivitySnap, eventID: 941))
                            .frame(width: 348)
                            .background(Color(uiColor: .systemBackground), in: RoundedRectangle(cornerRadius: 18))
                            .environment(\.colorScheme, .light)
                    }
                }
                tile("Live Activity · Pre-Start vs Started (Dark)") {
                    VStack(spacing: 8) {
                        GameActivityLockScreenView(reading: GameActivityReading(snapshot: preStartActivitySnap, eventID: 940))
                            .frame(width: 348)
                            .background(Color(uiColor: .systemBackground), in: RoundedRectangle(cornerRadius: 18))
                            .environment(\.colorScheme, .dark)
                        GameActivityLockScreenView(reading: GameActivityReading(snapshot: startedActivitySnap, eventID: 941))
                            .frame(width: 348)
                            .background(Color(uiColor: .systemBackground), in: RoundedRectangle(cornerRadius: 18))
                            .environment(\.colorScheme, .dark)
                    }
                }
            }

            HStack(alignment: .top, spacing: 14) {
                tile("Watch App Hero · Light & Dark") {
                    VStack(spacing: 8) {
                        HStack(spacing: 10) {
                            WatchMatchupGamePageHeroView297A(model: preWatchHero, caseWidth: 186)
                                .frame(width: 186)
                                .padding(6)
                                .background(Color.black, in: RoundedRectangle(cornerRadius: 16))
                                .environment(\.colorScheme, .dark)
                            WatchMatchupGamePageHeroView297A(model: startedWatchHero, caseWidth: 186)
                                .frame(width: 186)
                                .padding(6)
                                .background(Color.black, in: RoundedRectangle(cornerRadius: 16))
                                .environment(\.colorScheme, .dark)
                        }
                        HStack(spacing: 10) {
                            WatchMatchupGamePageHeroView297A(model: preWatchHero, caseWidth: 186)
                                .frame(width: 186)
                                .padding(6)
                                .background(Color(uiColor: .systemBackground), in: RoundedRectangle(cornerRadius: 16))
                                .environment(\.colorScheme, .light)
                            WatchMatchupGamePageHeroView297A(model: startedWatchHero, caseWidth: 186)
                                .frame(width: 186)
                                .padding(6)
                                .background(Color(uiColor: .systemBackground), in: RoundedRectangle(cornerRadius: 16))
                                .environment(\.colorScheme, .light)
                        }
                    }
                }
                tile("Watch Complications · Light & Dark") {
                    VStack(spacing: 8) {
                        HStack(spacing: 10) {
                            WatchUnavailableComplicationContent13339(
                                status: WatchFaceStatusPayload13339(
                                    targetID: 940,
                                    title: "ORL at MIA",
                                    reason: .noProbabilityYet,
                                    updatedAt: fixedNow
                                )
                            )
                            .frame(width: 158, height: 70)
                            .padding(8)
                            .background(Color.black, in: RoundedRectangle(cornerRadius: 14))
                            .environment(\.colorScheme, .dark)
                            WatchUnavailableComplicationContent13339(
                                status: WatchFaceStatusPayload13339(
                                    targetID: 941,
                                    title: "ORL at MIA",
                                    reason: .noLiveOdds,
                                    updatedAt: fixedNow
                                )
                            )
                            .frame(width: 158, height: 70)
                            .padding(8)
                            .background(Color.black, in: RoundedRectangle(cornerRadius: 14))
                            .environment(\.colorScheme, .dark)
                        }
                        HStack(spacing: 10) {
                            WatchUnavailableComplicationContent13339(
                                status: WatchFaceStatusPayload13339(
                                    targetID: 940,
                                    title: "ORL at MIA",
                                    reason: .noProbabilityYet,
                                    updatedAt: fixedNow
                                )
                            )
                            .frame(width: 158, height: 70)
                            .padding(8)
                            .background(Color(uiColor: .systemBackground), in: RoundedRectangle(cornerRadius: 14))
                            .environment(\.colorScheme, .light)
                            WatchUnavailableComplicationContent13339(
                                status: WatchFaceStatusPayload13339(
                                    targetID: 941,
                                    title: "ORL at MIA",
                                    reason: .noLiveOdds,
                                    updatedAt: fixedNow
                                )
                            )
                            .frame(width: 158, height: 70)
                            .padding(8)
                            .background(Color(uiColor: .systemBackground), in: RoundedRectangle(cornerRadius: 14))
                            .environment(\.colorScheme, .light)
                        }
                    }
                }
            }
        }
        .padding(18)
        .background(Color(white: 0.94))

        let renderer = rendererForMeasurement(sheet)
        renderer.scale = 2.0
        let image = try XCTUnwrap(renderer.uiImage)
        let png = try XCTUnwrap(image.pngData())
        let outURL = URL(fileURLWithPath: "/tmp/item3-no-prob-yet-sheet.png")
        try png.write(to: outURL)
        print("EXPORTED_ITEM3_SHEET=\(outURL.path) bytes=\(png.count)")
    }
    #endif
}
