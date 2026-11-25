import XCTest
import SwiftUI
import WidgetKit
#if canImport(UIKit)
import UIKit
#endif
@testable import Bain_Luck

final class WatchSmallAndLockScreenMatchup13430Tests: XCTestCase {
    private let utc = TimeZone(identifier: "UTC")!
    private let now = Date(timeIntervalSinceReferenceDate: 785_500_000)

    private func iso(_ date: Date) -> String {
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return f.string(from: date)
    }

    // MARK: - #13430 Small Slot (Corner & Circular) Contracts

    func testSmallSlotModelLiveAndUpcomingGames() throws {
        let observed = now.addingTimeInterval(-30)
        let ne = WatchCompactTeamIdentity(teamID: 1, abbreviation: "NE")
        let lac = WatchCompactTeamIdentity(teamID: 2, abbreviation: "LAC")
        let bal = WatchCompactTeamIdentity(teamID: 3, abbreviation: "BAL")

        let liveReading = WatchRectangularReading(
            version: 1, eventID: 10, kind: .liveForecast,
            homeName: "Baltimore Ravens", awayName: "Los Angeles Chargers",
            home: bal, away: lac,
            homePercent: 74, homeScore: 17, awayScore: 10, commenceTime: nil,
            stateLabel: "Live", observedAt: observed, scoreObservedAt: observed
        )
        let liveSnap = WatchComplicationSnapshot(
            eventID: 10, title: "Baltimore Ravens win", detail: "74% · Live",
            observedAt: observed, savedAt: now, rectangularReading: liveReading
        )
        let liveSmall = try XCTUnwrap(liveSnap.smallSlotModel(now: now))
        XCTAssertEqual(liveSmall.subjectLabel, "BAL")
        XCTAssertEqual(liveSmall.cornerLabel, "BAL")
        XCTAssertEqual(liveSmall.value, "74%")
        XCTAssertEqual(try XCTUnwrap(liveSmall.gaugeShare), 0.74, accuracy: 0.0001)
        XCTAssertTrue(liveSmall.isGame)

        // Away favorite before kickoff selects away abbreviation and 100 - homePercent.
        let start = now.addingTimeInterval(3600)
        let schedReading = WatchRectangularReading(
            version: 1, eventID: 11, kind: .scheduledForecast,
            homeName: "Los Angeles Chargers", awayName: "New England Patriots",
            home: lac, away: ne,
            homePercent: 40, homeScore: nil, awayScore: nil, commenceTime: start,
            stateLabel: "Scheduled", observedAt: observed, scoreObservedAt: nil
        )
        let schedSnap = WatchComplicationSnapshot(
            eventID: 11, title: "Los Angeles Chargers win", detail: "40% · Scheduled",
            observedAt: observed, savedAt: now, rectangularReading: schedReading
        )
        let schedSmall = try XCTUnwrap(schedSnap.smallSlotModel(now: now))
        XCTAssertEqual(schedSmall.subjectLabel, "NE")
        XCTAssertEqual(schedSmall.cornerLabel, "NE")
        XCTAssertEqual(schedSmall.value, "60%")
        XCTAssertEqual(try XCTUnwrap(schedSmall.gaugeShare), 0.60, accuracy: 0.0001)

        // Once scheduled kickoff passes without a live update, small slots step back to nil (bookmark fallback).
        XCTAssertNil(schedSnap.smallSlotModel(now: start))
    }

    func testSmallSlotModelFinalWithinThreeHoursAndStepAside() throws {
        let observed = now.addingTimeInterval(-600)
        let ne = WatchCompactTeamIdentity(teamID: 1, abbreviation: "NE")
        let det = WatchCompactTeamIdentity(teamID: 4, abbreviation: "DET")

        let winReading = WatchRectangularReading(
            version: 1, eventID: 12, kind: .finalResult,
            homeName: "Detroit Lions", awayName: "New England Patriots",
            home: det, away: ne,
            homePercent: nil, homeScore: 35, awayScore: 10, commenceTime: nil,
            stateLabel: "Final", observedAt: observed, scoreObservedAt: observed
        )
        let winSnap = WatchComplicationSnapshot(
            eventID: 12, title: "Detroit Lions won", detail: "Final · 35–10",
            observedAt: observed, savedAt: observed, rectangularReading: winReading,
            matchup: WatchMatchupFacts217(pregameHomePercent: 58, pregameAwayPercent: 42)
        )
        let winSmall = try XCTUnwrap(winSnap.smallSlotModel(now: now))
        XCTAssertEqual(winSmall.subjectLabel, "DET")
        XCTAssertEqual(winSmall.cornerLabel, "DET")
        XCTAssertEqual(winSmall.value, "Won")
        XCTAssertNil(winSmall.gaugeShare)

        // At 3 hours after final, step aside cleanly to bookmark fallback.
        XCTAssertNil(winSnap.smallSlotModel(now: observed.addingTimeInterval(3 * 3600)))

        // Tied final displays Draw cleanly within 3 hours.
        let tieReading = WatchRectangularReading(
            version: 1, eventID: 13, kind: .finalResult,
            homeName: "Detroit Lions", awayName: "New England Patriots",
            home: det, away: ne,
            homePercent: nil, homeScore: 1, awayScore: 1, commenceTime: nil,
            stateLabel: "Final", observedAt: observed, scoreObservedAt: observed
        )
        let tieSnap = WatchComplicationSnapshot(
            eventID: 13, title: "New England Patriots at Detroit Lions", detail: "Final · tied 1–1",
            observedAt: observed, savedAt: observed, rectangularReading: tieReading
        )
        let tieSmall = try XCTUnwrap(tieSnap.smallSlotModel(now: now))
        XCTAssertEqual(tieSmall.subjectLabel, "Draw")
        XCTAssertEqual(tieSmall.value, "Draw")
        XCTAssertNil(tieSmall.gaugeShare)
    }

    func testSmallSlotModelRefusesScoreWithoutOddsAndSupportsMarkets() throws {
        let obs = now.addingTimeInterval(-60)
        // Score-only game omits rectangularReading -> small slots also refuse (bookmark fallback).
        let sf = WatchCompactTeamIdentity(teamID: 1, abbreviation: "SF")
        let la = WatchCompactTeamIdentity(teamID: 2, abbreviation: "LA")
        let circularOnly = WatchCircularReading(
            version: 1, eventID: 14, kind: .score,
            homeName: "San Francisco Giants", awayName: "Los Angeles Dodgers",
            home: sf, away: la, percent: nil, homeScore: 4, awayScore: 2,
            stateLabel: "Live", observedAt: obs
        )
        let scoreOnlySnap = WatchComplicationSnapshot(
            eventID: 14, title: "Los Angeles Dodgers at San Francisco Giants", detail: "Score 2–4 · Live",
            observedAt: obs, savedAt: now, circularReading: circularOnly, rectangularReading: nil
        )
        XCTAssertNil(scoreOnlySnap.smallSlotModel(now: now))

        // Open market snapshots project into corner/circular gauges accurately, including <1% and >99%.
        func makeMarketSnapshot(id: Int, outcome: String, percent: Int, subOne: Bool = false, above99: Bool = false) -> WatchComplicationSnapshot {
            let reading = WatchRectangularReading(
                version: 1, eventID: id, kind: .futureForecast,
                homeName: "2028 Democratic Nominee", awayName: outcome,
                home: nil, away: nil,
                homePercent: percent, homeScore: nil, awayScore: nil, commenceTime: nil,
                stateLabel: "Market", observedAt: obs, scoreObservedAt: nil,
                subOnePercent: subOne ? true : nil,
                aboveNinetyNinePercent: above99 ? true : nil
            )
            let pctText = subOne ? "<1%" : (above99 ? ">99%" : "\(percent)%")
            return WatchComplicationSnapshot(
                eventID: id, title: "2028 Democratic Nominee", detail: "\(outcome) \(pctText)",
                observedAt: obs, savedAt: now, circularReading: nil, rectangularReading: reading
            )
        }

        let market = makeMarketSnapshot(id: 9303, outcome: "Newsom", percent: 23)
        let marketSmall = try XCTUnwrap(market.smallSlotModel(now: now))
        XCTAssertEqual(marketSmall.cornerLabel, "Newsom")
        XCTAssertEqual(marketSmall.value, "23%")
        XCTAssertEqual(try XCTUnwrap(marketSmall.gaugeShare), 0.23, accuracy: 0.0001)
        XCTAssertFalse(marketSmall.isGame)

        let subOne = makeMarketSnapshot(id: 9304, outcome: "Field", percent: 1, subOne: true)
        XCTAssertEqual(subOne.smallSlotModel(now: now)?.value, "<1%")

        let above99 = makeMarketSnapshot(id: 9305, outcome: "Favorite", percent: 99, above99: true)
        XCTAssertEqual(above99.smallSlotModel(now: now)?.value, ">99%")
    }

    func testWatchCircularMarketNeverHidesSubjectBehindBareGauge13430() throws {
        let obs = now.addingTimeInterval(-30)
        let reading = WatchRectangularReading(
            version: 1, eventID: 9303, kind: .futureForecast,
            homeName: "2028 Democratic Nominee", awayName: "Newsom",
            home: nil, away: nil,
            homePercent: 23, homeScore: nil, awayScore: nil, commenceTime: nil,
            stateLabel: "Market", observedAt: obs, scoreObservedAt: nil
        )
        let marketSnap = WatchComplicationSnapshot(
            eventID: 9303, title: "2028 Democratic Nominee", detail: "Newsom 23%",
            observedAt: obs, savedAt: now, circularReading: nil, rectangularReading: reading
        )
        let smallModel = try XCTUnwrap(marketSnap.smallSlotModel(now: now))
        XCTAssertEqual(smallModel.subjectLabel, "Newsom")
        XCTAssertEqual(smallModel.cornerLabel, "Newsom")
        XCTAssertEqual(smallModel.value, "23%")
        XCTAssertFalse(smallModel.isGame)

        let watchContentSource = try String(
            contentsOf: URL(fileURLWithPath: #filePath)
                .deletingLastPathComponent()
                .deletingLastPathComponent()
                .appendingPathComponent("BainLuckWatch Watch App/WatchSavedComplicationContent.swift"),
            encoding: .utf8
        )
        XCTAssertFalse(
            watchContentSource.contains(#"model.isGame ? model.subjectLabel : """#),
            "Circular slot must never render a bare Gauge percent without its subject"
        )
        XCTAssertFalse(watchContentSource.contains("Circular and corner families remain explicit launchers"))
        XCTAssertTrue(watchContentSource.contains("if let share = model.gaugeShare, model.isGame"))
    }

    func testSmallSlotModelAndLockScreenFitShareSingleRule() {
        XCTAssertEqual(SavedLockScreenFit10875.shortVerdicts, LockScreenSmallSlotFit13430.shortVerdicts)
        XCTAssertEqual(SavedLockScreenFit10875.ringLimit, LockScreenSmallSlotFit13430.ringLimit)
        XCTAssertEqual(
            LockScreenSmallSlotFit13430.ringValue(
                phase: .noResult, headlineExists: true, figure: nil, verdict: "Result unknown", rows: []
            ),
            "Unknown"
        )
        XCTAssertEqual(
            LockScreenSmallSlotFit13430.ringValue(
                phase: .noResult, headlineExists: false, figure: nil, verdict: nil, rows: []
            ),
            "Final"
        )
        XCTAssertEqual(
            LockScreenSmallSlotFit13430.ringValue(
                phase: .openingLine, headlineExists: true, figure: "60%", verdict: nil, rows: []
            ),
            "—"
        )
    }

    // MARK: - #13432 iPhone Double-Wide Lock Screen Matchup Contracts

    private func decodeEvent(_ json: String) throws -> SavedWidgetEventDetail10875 {
        try SavedWidgetDetailDecoding10875.decoder().decode(SavedWidgetEventDetail10875.self, from: Data(json.utf8))
    }

    private func resolveLockScreen(
        _ event: SavedWidgetEventDetail10875,
        side: SavedWidgetGameSide10875? = nil,
        isOffline: Bool = false,
        at date: Date? = nil
    ) -> SavedLockScreenRectangleState13432 {
        let evalDate = date ?? now
        let reading = SavedWidgetReadingRules10875.game(event, side: side, now: evalDate)
        let art = SavedWidgetArt12466.game(event)
        return SavedLockScreenMatchupAdapter13432.resolve(
            event: event,
            reading: reading,
            art: art,
            logos: .init(),
            side: side,
            isOffline: isOffline,
            now: evalDate,
            timeZone: utc
        )
    }

    func testLockScreenMatchupBeforeDuringAgedAsOfAndAfter() throws {
        // 1. Before kickoff (two-way NFL game): favorite shown + kickoff clock.
        let start = Date(timeIntervalSinceReferenceDate: 785_500_000 + 3 * 86_400)
        let beforeEvent = try decodeEvent("""
        {"id": 21701, "sport": "americanfootball_nfl",
         "home_team": "Los Angeles Chargers", "away_team": "New England Patriots",
         "status": "scheduled", "commence_time": "\(iso(start))",
         "home_team_data": {"abbreviation": "LAC", "primary_color": "#0080c6", "secondary_color": "#ffc20e"},
         "away_team_data": {"abbreviation": "NE", "primary_color": "#002a5c", "secondary_color": "#c60c30"},
         "current_odds": {"home_probability": 0.56, "away_probability": 0.44},
         "hero_probability_observed_at": "\(iso(now.addingTimeInterval(-30)))"}
        """)
        if case .matchup(let r) = resolveLockScreen(beforeEvent) {
            XCTAssertEqual(r.stage, .before)
            XCTAssertEqual(r.bigText, "56%")
            XCTAssertEqual(r.bigOwnerLabel, "LAC")
            XCTAssertFalse(r.smallLine.hasPrefix("LAC · "))
            XCTAssertNil(r.away.score)
            XCTAssertNil(r.threeWay)
        } else {
            XCTFail("Expected matchup before kickoff")
        }

        // Explicit away choice overrides favorite on the single big Lock Screen number.
        if case .matchup(let rAway) = resolveLockScreen(beforeEvent, side: .away) {
            XCTAssertEqual(rAway.bigText, "44%")
            XCTAssertEqual(rAway.bigOwnerLabel, "NE")
            XCTAssertFalse(rAway.bigIsHome)
            XCTAssertFalse(rAway.smallLine.hasPrefix("NE · "))
        } else {
            XCTFail("Expected explicit away choice matchup")
        }

        // 2. During live (fresh clock vs >120s aged "As of").
        let freshObs = now.addingTimeInterval(-45)
        let liveEvent = try decodeEvent("""
        {"id": 21702, "sport": "americanfootball_nfl",
         "home_team": "Baltimore Ravens", "away_team": "Los Angeles Chargers",
         "status": "live", "commence_time": "\(iso(now.addingTimeInterval(-3600)))",
         "home_score": 17, "away_score": 10,
         "espn": {"period": "Q3", "game_clock": "4:12"},
         "home_team_data": {"abbreviation": "BAL", "primary_color": "#241773", "secondary_color": "#9e7c0c"},
         "away_team_data": {"abbreviation": "LAC", "primary_color": "#0080c6", "secondary_color": "#ffc20e"},
         "current_odds": {"home_probability": 0.74, "away_probability": 0.26},
         "hero_probability_observed_at": "\(iso(freshObs))"}
        """)
        if case .matchup(let fresh) = resolveLockScreen(liveEvent) {
            XCTAssertEqual(fresh.stage, .during)
            XCTAssertEqual(fresh.bigText, "74%")
            XCTAssertEqual(fresh.bigOwnerLabel, "BAL")
            XCTAssertEqual(fresh.away.score, 10)
            XCTAssertEqual(fresh.home.score, 17)
            XCTAssertEqual(fresh.smallLine, "Q3 4:12")
        } else {
            XCTFail("Expected fresh live matchup")
        }

        // Past Watch's 120s threshold -> switches smallLine to "As of ..." with owner kept on primary line.
        let agedNow = freshObs.addingTimeInterval(WatchRectangularReading.liveAgeThresholdSeconds + 1)
        if case .matchup(let aged) = resolveLockScreen(liveEvent, at: agedNow) {
            XCTAssertEqual(aged.stage, .during)
            XCTAssertEqual(aged.bigOwnerLabel, "BAL")
            XCTAssertTrue(aged.smallLine.hasPrefix("As of "), "Unexpected aged smallLine: \(aged.smallLine)")
        } else {
            XCTFail("Expected aged live matchup")
        }

        // Offline forces "As of ..." even if recent.
        if case .matchup(let offlineM) = resolveLockScreen(liveEvent, isOffline: true) {
            XCTAssertEqual(offlineM.bigOwnerLabel, "BAL")
            XCTAssertTrue(offlineM.smallLine.hasPrefix("As of "))
        } else {
            XCTFail("Expected offline As of matchup")
        }

        // 3. After final (<3h -> ✓ winner + pregame %, >=3h -> postFinalEnded).
        let finalObs = now.addingTimeInterval(-600)
        let finalEvent = try decodeEvent("""
        {"id": 21705, "sport": "basketball_nba",
         "home_team": "Detroit Pistons", "away_team": "Toronto Raptors",
         "status": "completed", "commence_time": "\(iso(now.addingTimeInterval(-10_800)))",
         "home_score": 102, "away_score": 105,
         "hero_settled_result": "away",
         "score_observed_at": "\(iso(finalObs))",
         "home_team_data": {"abbreviation": "DET", "primary_color": "#c8102e", "secondary_color": "#1d42ba"},
         "away_team_data": {"abbreviation": "TOR", "primary_color": "#ce1141", "secondary_color": "#000000"},
         "prematch_odds": {"home_probability": 0.71, "away_probability": 0.29},
         "current_odds": {"home_probability": 0.0, "away_probability": 1.0}}
        """)
        if case .matchup(let after) = resolveLockScreen(finalEvent) {
            XCTAssertEqual(after.stage, .after)
            XCTAssertEqual(after.bigText, "29%")
            XCTAssertEqual(after.bigOwnerLabel, "TOR")
            XCTAssertFalse(after.bigIsHome)
            XCTAssertTrue(after.away.isWinner)
            XCTAssertFalse(after.home.isWinner)
            XCTAssertEqual(after.away.score, 105)
            XCTAssertEqual(after.home.score, 102)
            XCTAssertEqual(after.smallLine, "Pregame · Final")
        } else {
            XCTFail("Expected post-final matchup")
        }

        if case .postFinalEnded(let title) = resolveLockScreen(
            finalEvent,
            at: finalObs.addingTimeInterval(WatchMatchupReading217.finalHoldSeconds)
        ) {
            XCTAssertEqual(title, "TOR vs DET")
        } else {
            XCTFail("Expected postFinalEnded 3 hours after final")
        }
    }

    func testLockScreenMatchupThreeWaySoccerExplicitAndWithheldDraw5271() throws {
        // Explicit 3-way soccer shows all three outcomes: Home / Draw / Away.
        let soccerThreeWay = try decodeEvent("""
        {"id": 31001, "sport": "soccer_epl",
         "home_team": "Arsenal", "away_team": "Manchester City",
         "status": "live", "commence_time": "\(iso(now.addingTimeInterval(-3600)))",
         "home_score": 1, "away_score": 1,
         "espn": {"period": "64'", "game_clock": ""},
         "home_team_data": {"abbreviation": "ARS", "primary_color": "#ef0107", "secondary_color": "#063672"},
         "away_team_data": {"abbreviation": "MCI", "primary_color": "#6cabdd", "secondary_color": "#1c2c5b"},
         "current_odds": {"home_probability": 0.52, "draw_probability": 0.26, "away_probability": 0.22},
         "hero_probability_observed_at": "\(iso(now.addingTimeInterval(-30)))"}
        """)
        if case .matchup(let threeWayM) = resolveLockScreen(soccerThreeWay) {
            let tw = try XCTUnwrap(threeWayM.threeWay)
            XCTAssertEqual(tw.homeLabel, "ARS")
            XCTAssertEqual(tw.homeText, "52%")
            XCTAssertEqual(tw.drawText, "26%")
            XCTAssertEqual(tw.awayLabel, "MCI")
            XCTAssertEqual(tw.awayText, "22%")
            XCTAssertFalse(threeWayM.smallLine.isEmpty)
        } else {
            XCTFail("Expected 3-way soccer matchup")
        }

        // When draw is withheld (#5271): home stands alone cleanly, away selection falls back rather than inventing 1 - home.
        let soccerHomeOnly = try decodeEvent("""
        {"id": 31002, "sport": "soccer_epl",
         "home_team": "Arsenal", "away_team": "Manchester City",
         "status": "live", "commence_time": "\(iso(now.addingTimeInterval(-3600)))",
         "home_score": 1, "away_score": 1,
         "espn": {"period": "64'", "game_clock": ""},
         "home_team_data": {"abbreviation": "ARS", "primary_color": "#ef0107", "secondary_color": "#063672"},
         "away_team_data": {"abbreviation": "MCI", "primary_color": "#6cabdd", "secondary_color": "#1c2c5b"},
         "current_odds": {"home_probability": 0.52, "away_probability": 0.48},
         "hero_probability_observed_at": "\(iso(now.addingTimeInterval(-30)))"}
        """)
        if case .matchup(let homeOnlyM) = resolveLockScreen(soccerHomeOnly, side: nil) {
            XCTAssertNil(homeOnlyM.threeWay)
            XCTAssertEqual(homeOnlyM.bigText, "52%")
            XCTAssertEqual(homeOnlyM.bigOwnerLabel, "ARS")
            XCTAssertTrue(homeOnlyM.bigIsHome)
            XCTAssertFalse(homeOnlyM.smallLine.hasPrefix("ARS · "))
        } else {
            XCTFail("Expected home-only draw-priced matchup")
        }
        XCTAssertEqual(resolveLockScreen(soccerHomeOnly, side: .away), .fallbackText)

        // Tied soccer final with pregame draw probability keeps Matchup after final within 3h.
        let drawFinalObs = now.addingTimeInterval(-900)
        let soccerDrawFinal = try decodeEvent("""
        {"id": 31003, "sport": "soccer_epl",
         "home_team": "Arsenal", "away_team": "Manchester City",
         "status": "completed", "commence_time": "\(iso(now.addingTimeInterval(-10_800)))",
         "home_score": 1, "away_score": 1,
         "score_observed_at": "\(iso(drawFinalObs))",
         "home_team_data": {"abbreviation": "ARS", "primary_color": "#ef0107"},
         "away_team_data": {"abbreviation": "MCI", "primary_color": "#6cabdd"},
         "prematch_odds": {"home_probability": 0.46, "draw_probability": 0.28, "away_probability": 0.26}}
        """)
        if case .matchup(let drawAfter) = resolveLockScreen(soccerDrawFinal) {
            XCTAssertEqual(drawAfter.stage, .after)
            XCTAssertEqual(drawAfter.bigText, "28%")
            XCTAssertEqual(drawAfter.bigOwnerLabel, "Draw")
            XCTAssertEqual(drawAfter.smallLine, "Pregame · Final")
            XCTAssertFalse(drawAfter.home.isWinner)
            XCTAssertFalse(drawAfter.away.isWinner)
        } else {
            XCTFail("Expected soccer draw final with pregame draw %")
        }
    }

    func testLockScreenTimelineDatesIncludeAsOfAndPostFinalBoundaries() throws {
        let obs = now.addingTimeInterval(-45)
        let liveEvent = try decodeEvent("""
        {"id": 21702, "sport": "americanfootball_nfl",
         "home_team": "Baltimore Ravens", "away_team": "Los Angeles Chargers",
         "status": "live", "commence_time": "\(iso(now.addingTimeInterval(-3600)))",
         "home_team_data": {"abbreviation": "BAL"}, "away_team_data": {"abbreviation": "LAC"},
         "current_odds": {"home_probability": 0.74, "away_probability": 0.26},
         "hero_probability_observed_at": "\(iso(obs))"}
        """)
        let sel = SavedWidgetSelection10875(scope: "guest", subject: .init(kind: .game, id: 21702), side: nil, outcomeID: nil)
        let liveDates = SavedLockScreenMatchupAdapter13432.timelineDates(
            content: .detail(.game(liveEvent), offline: false), selection: sel, now: now, timeZone: utc
        )
        XCTAssertTrue(liveDates.contains(obs.addingTimeInterval(WatchRectangularReading.liveAgeThresholdSeconds + 1)))

        let finalObs = now.addingTimeInterval(-600)
        let finalEvent = try decodeEvent("""
        {"id": 21705, "sport": "basketball_nba",
         "home_team": "Detroit Pistons", "away_team": "Toronto Raptors",
         "status": "completed", "home_score": 102, "away_score": 105,
         "hero_settled_result": "away",
         "score_observed_at": "\(iso(finalObs))",
         "home_team_data": {"abbreviation": "DET"}, "away_team_data": {"abbreviation": "TOR"},
         "prematch_odds": {"home_probability": 0.71, "away_probability": 0.29}}
        """)
        let finalDates = SavedLockScreenMatchupAdapter13432.timelineDates(
            content: .detail(.game(finalEvent), offline: false), selection: sel, now: now, timeZone: utc
        )
        XCTAssertTrue(finalDates.contains(finalObs.addingTimeInterval(WatchMatchupReading217.finalHoldSeconds)))
        // Existing SavedWidgetTimeline10875 contract remains unchanged.
        XCTAssertEqual(
            SavedWidgetTimeline10875.entryDates(.detail(.game(finalEvent), offline: false), selection: sel, now: now),
            [now]
        )
    }

    @MainActor
    func testWordingAndRenderingAcrossPhoneSizesAndDynamicType() throws {
        let obs = now.addingTimeInterval(-45)
        let threeWay = WatchMatchupReading217(
            stage: .during,
            away: .init(abbreviation: "MCI", inkHex: "#6cabdd", crestPNG: nil, score: 1, isWinner: false),
            home: .init(abbreviation: "ARS", inkHex: "#ef0107", crestPNG: nil, score: 1, isWinner: false),
            bigText: "52%",
            bigIsHome: true,
            smallLine: "As of 1:12 PM",
            accessibilityText: "Manchester City at Arsenal. 1-1.",
            threeWay: .init(homeLabel: "ARS", homeText: "52%", drawText: "26%", awayLabel: "MCI", awayText: "22%")
        )
        let nbaFinal = WatchMatchupReading217(
            stage: .after,
            away: .init(abbreviation: "TOR", inkHex: "#ce1141", crestPNG: nil, score: 105, isWinner: true),
            home: .init(abbreviation: "DET", inkHex: "#c8102e", crestPNG: nil, score: 102, isWinner: false),
            bigText: "29%",
            bigOwnerLabel: "TOR",
            bigIsHome: false,
            smallLine: "Pregame · Final",
            accessibilityText: "Final. Raptors 105, Pistons 102."
        )
        for line in [threeWay.smallLine, nbaFinal.smallLine] {
            let lower = line.lowercased()
            XCTAssertFalse(lower.contains("pts"))
            XCTAssertFalse(lower.contains("stale"))
            XCTAssertFalse(lower.contains("checked"))
            XCTAssertFalse(lower.contains("saved"))
        }
        XCTAssertTrue(nbaFinal.smallLine.lowercased().contains("pregame"))

        // #13649 contracts: <=3% crest padding + explicit owner on primary line across Watch (41/45/49 mm) & Lock Screen.
        XCTAssertLessThanOrEqual(WatchMatchupComplication217.crestPaddingFraction, 0.03)
        let collegeReading = WatchMatchupReading217(
            stage: .during,
            away: .init(abbreviation: "M-OH", inkHex: "#c41230", crestPNG: nil, score: 49, isWinner: false),
            home: .init(abbreviation: "TA&M", inkHex: "#ffffff", crestPNG: nil, score: 62, isWinner: false),
            bigText: "78%",
            bigOwnerLabel: "TA&M",
            bigIsHome: true,
            smallLine: "2H 8:14",
            accessibilityText: "Miami OH at Texas A&M. 78%."
        )
        XCTAssertEqual(collegeReading.bigOwnerLabel, "TA&M")

        #if canImport(UIKit)
        for wSize in [CGSize(width: 171.5, height: 73), CGSize(width: 185, height: 79), CGSize(width: 199, height: 84.5)] {
            let cw = WatchMatchupComplication217(reading: collegeReading)
                .background(Color.black)
                .environment(\.widgetRenderingMode, .fullColor)
                .environment(\.colorScheme, .dark)
                .frame(width: wSize.width, height: wSize.height)
            let rw = rendererForMeasurement(cw, at: .large)
            rw.scale = 2
            XCTAssertNotNil(rw.uiImage)
        }
        for size in [CGSize(width: 157, height: 68), CGSize(width: 172, height: 76)] {
            for dt in [DynamicTypeSize.large, .accessibility5] {
                for scheme in [ColorScheme.dark, .light] {
                    let v1 = WatchMatchupComplication217(reading: threeWay)
                        .environment(\.widgetRenderingMode, .vibrant)
                        .environment(\.colorScheme, scheme)
                        .frame(width: size.width, height: size.height)
                    let r1 = rendererForMeasurement(v1, at: dt)
                    r1.scale = 3
                    XCTAssertNotNil(r1.uiImage)

                    let v2 = WatchMatchupComplication217(reading: nbaFinal)
                        .environment(\.widgetRenderingMode, .vibrant)
                        .environment(\.colorScheme, scheme)
                        .frame(width: size.width, height: size.height)
                    let r2 = rendererForMeasurement(v2, at: dt)
                    r2.scale = 3
                    XCTAssertNotNil(r2.uiImage)

                    let v3 = SavedLockPostFinalEndedView13432(title: "TOR vs DET")
                        .environment(\.widgetRenderingMode, .vibrant)
                        .environment(\.colorScheme, scheme)
                        .frame(width: size.width, height: size.height)
                    let r3 = rendererForMeasurement(v3, at: dt)
                    r3.scale = 3
                    XCTAssertNotNil(r3.uiImage)
                }
            }
        }
        let _ = obs
        #endif
    }

    // MARK: - #13432 On-Demand Contact Sheet Tile Exporter

    @MainActor
    func testExportSheet13432TilesWhenRequested() throws {
        guard ProcessInfo.processInfo.environment["BAINLUCK_RENDER_SHEET_13432"] == "1" else {
            throw XCTSkip("On-demand #13432 contact sheet tile exporter")
        }
        #if canImport(UIKit)
        let fm = FileManager.default
        let logoDir = "/tmp/sheet-13432-logos"
        let outDir = URL(fileURLWithPath: "/tmp/sheet-13432-tiles", isDirectory: true)
        try fm.createDirectory(at: outDir, withIntermediateDirectories: true)

        func logo(_ abbr: String) -> Data? {
            fm.contents(atPath: "\(logoDir)/\(abbr.lowercased()).png")
        }

        let start = Date(timeIntervalSinceReferenceDate: 785_500_000 + 3 * 86_400 + 17 * 3600 + 20 * 60)
        let obsFresh = now.addingTimeInterval(-35)
        let obsAged = now.addingTimeInterval(-600)
        let finalObs = now.addingTimeInterval(-900)

        let beforeE = try decodeEvent("""
        {"id": 21701, "sport": "americanfootball_nfl",
         "home_team": "Los Angeles Chargers", "away_team": "New England Patriots",
         "status": "scheduled", "commence_time": "\(iso(start))",
         "home_team_data": {"abbreviation": "LAC", "primary_color": "#0080c6"},
         "away_team_data": {"abbreviation": "NE", "primary_color": "#002a5c"},
         "current_odds": {"home_probability": 0.56, "away_probability": 0.44},
         "hero_probability_observed_at": "\(iso(obsFresh))"}
        """)
        let liveE = try decodeEvent("""
        {"id": 21702, "sport": "americanfootball_nfl",
         "home_team": "Baltimore Ravens", "away_team": "Los Angeles Chargers",
         "status": "live", "commence_time": "\(iso(now.addingTimeInterval(-3600)))",
         "home_score": 17, "away_score": 10,
         "espn": {"period": "Q3", "game_clock": "4:12"},
         "home_team_data": {"abbreviation": "BAL", "primary_color": "#241773", "secondary_color": "#9e7c0c"},
         "away_team_data": {"abbreviation": "LAC", "primary_color": "#0080c6"},
         "current_odds": {"home_probability": 0.74, "away_probability": 0.26},
         "hero_probability_observed_at": "\(iso(obsFresh))"}
        """)
        let agedE = try decodeEvent("""
        {"id": 21703, "sport": "americanfootball_nfl",
         "home_team": "Baltimore Ravens", "away_team": "Los Angeles Chargers",
         "status": "live", "commence_time": "\(iso(now.addingTimeInterval(-3600)))",
         "home_score": 17, "away_score": 10,
         "espn": {"period": "Q3", "game_clock": "4:12"},
         "home_team_data": {"abbreviation": "BAL", "primary_color": "#241773", "secondary_color": "#9e7c0c"},
         "away_team_data": {"abbreviation": "LAC", "primary_color": "#0080c6"},
         "current_odds": {"home_probability": 0.74, "away_probability": 0.26},
         "hero_probability_observed_at": "\(iso(obsAged))"}
        """)
        let soccerE = try decodeEvent("""
        {"id": 21704, "sport": "soccer_epl",
         "home_team": "Arsenal", "away_team": "Manchester City",
         "status": "live", "commence_time": "\(iso(now.addingTimeInterval(-3600)))",
         "home_score": 1, "away_score": 1,
         "espn": {"period": "64'", "game_clock": ""},
         "home_team_data": {"abbreviation": "ARS", "primary_color": "#ef0107"},
         "away_team_data": {"abbreviation": "MCI", "primary_color": "#6cabdd"},
         "current_odds": {"home_probability": 0.52, "draw_probability": 0.26, "away_probability": 0.22},
         "hero_probability_observed_at": "\(iso(obsFresh))"}
        """)
        let finalE = try decodeEvent("""
        {"id": 21705, "sport": "basketball_nba",
         "home_team": "Detroit Pistons", "away_team": "Toronto Raptors",
         "status": "completed", "home_score": 102, "away_score": 105,
         "hero_settled_result": "away",
         "score_observed_at": "\(iso(finalObs))",
         "home_team_data": {"abbreviation": "DET", "primary_color": "#c8102e"},
         "away_team_data": {"abbreviation": "TOR", "primary_color": "#ce1141"},
         "prematch_odds": {"home_probability": 0.71, "away_probability": 0.29}}
        """)

        func matchupTile(_ event: SavedWidgetEventDetail10875, away: String, home: String, at evalNow: Date = now) throws -> AnyView {
            let state = SavedLockScreenMatchupAdapter13432.resolve(
                event: event,
                reading: SavedWidgetReadingRules10875.game(event, side: nil, now: evalNow),
                art: SavedWidgetArt12466.game(event),
                logos: .init(away: logo(away), home: logo(home)),
                side: nil,
                isOffline: false,
                now: evalNow,
                timeZone: TimeZone(identifier: "America/Los_Angeles")!
            )
            switch state {
            case .matchup(let reading):
                return AnyView(WatchMatchupComplication217(reading: reading))
            case .postFinalEnded(let title):
                return AnyView(SavedLockPostFinalEndedView13432(title: title))
            case .fallbackText:
                return AnyView(Text("Fallback"))
            }
        }

        let marketJSON = """
        {"id": 9303, "name": "2028 Democratic Nominee", "status": "open", "lead_outcome_id": 1,
         "outcomes": [{"id": 1, "name": "Gavin Newsom", "probability": 0.23, "observed_at": "\(iso(obsAged))"}]}
        """
        let marketObj = try SavedWidgetDetailDecoding10875.decoder().decode(SavedWidgetMarketDetail10875.self, from: Data(marketJSON.utf8))
        let marketReading = SavedWidgetReadingRules10875.market(marketObj, outcomeID: 1, now: now)
        let marketView = AnyView(
            SavedLockMarketBody13432(
                shortSubject: marketReading.shortSubject,
                outcomeLabel: marketReading.headline?.label,
                valueText: marketReading.headline?.figure,
                footer: "As of 3:42 PM"
            )
        )
        let cannotShowView = AnyView(
            SavedLockMessageRectangleView13432(
                title: "Choose a saved game or market",
                detail: "Edit to choose"
            )
        )

        let cases: [(id: String, view: AnyView)] = [
            ("1-before", try matchupTile(beforeE, away: "ne", home: "lac")),
            ("2-during", try matchupTile(liveE, away: "lac", home: "bal")),
            ("3-aged", try matchupTile(agedE, away: "lac", home: "bal")),
            ("4-soccer-3way", try matchupTile(soccerE, away: "mci", home: "ars")),
            ("5-final", try matchupTile(finalE, away: "tor", home: "det_nba")),
            ("6-post-final-3h", try matchupTile(finalE, away: "tor", home: "det_nba", at: finalObs.addingTimeInterval(3 * 3600))),
            ("7-market", marketView),
            ("8-cannot-show", cannotShowView),
        ]

        let configs: [(tag: String, size: CGSize, scheme: ColorScheme, dt: DynamicTypeSize)] = [
            ("390-dark-def", CGSize(width: 157, height: 68), .dark, .large),
            ("390-light-def", CGSize(width: 157, height: 68), .light, .large),
            ("390-dark-a5", CGSize(width: 157, height: 68), .dark, .accessibility5),
            ("390-light-a5", CGSize(width: 157, height: 68), .light, .accessibility5),
            ("440-dark-def", CGSize(width: 172, height: 76), .dark, .large),
            ("440-light-def", CGSize(width: 172, height: 76), .light, .large),
            ("440-dark-a5", CGSize(width: 172, height: 76), .dark, .accessibility5),
            ("440-light-a5", CGSize(width: 172, height: 76), .light, .accessibility5),
        ]

        for c in cases {
            for cfg in configs {
                let bgColor = cfg.scheme == .dark ? Color(red: 0.14, green: 0.16, blue: 0.21) : Color(red: 0.87, green: 0.89, blue: 0.93)
                let tile = c.view
                    .padding(.horizontal, 6)
                    .padding(.vertical, 4)
                    .frame(width: cfg.size.width, height: cfg.size.height)
                    .background(
                        RoundedRectangle(cornerRadius: 14, style: .continuous)
                            .fill(bgColor)
                    )
                    .environment(\.widgetRenderingMode, .vibrant)
                    .environment(\.colorScheme, cfg.scheme)

                let renderer = rendererForMeasurement(tile, at: cfg.dt)
                renderer.scale = 3
                let image = try XCTUnwrap(renderer.uiImage)
                let data = try XCTUnwrap(image.pngData())
                try data.write(to: outDir.appendingPathComponent("\(c.id)__\(cfg.tag).png"))
            }
        }
        #endif
    }
}
