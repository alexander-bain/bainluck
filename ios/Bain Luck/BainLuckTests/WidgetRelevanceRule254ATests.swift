import Foundation
import XCTest
@testable import Bain_Luck

final class WidgetRelevanceRule254ATests: XCTestCase {
    private let base = Date(timeIntervalSince1970: 1_763_600_000) // fixed non-wall-clock epoch

    // MARK: - Core scoring & ranking hierarchy

    func testScoringHierarchyOrdersPinnedLiveAbovePregameAboveLiveGamesAboveFinalAboveIdle() {
        let live = WidgetRelevanceRule254A.spec(for: .live, at: base)
        let pregame = WidgetRelevanceRule254A.spec(
            for: .scheduled(commenceTime: base.addingTimeInterval(15 * 60), startIsTbd: false),
            at: base
        )
        let generalLive = WidgetRelevanceRule254A.liveGamesWidget(liveCount: 2, isPlaceholder: false)
        let recentFinal = WidgetRelevanceRule254A.spec(
            for: .finalResult(observedAt: base.addingTimeInterval(-10 * 60)),
            at: base
        )
        let idle = WidgetRelevanceRule254A.spec(for: .other, at: base)

        XCTAssertEqual(live.score, 100)
        XCTAssertEqual(pregame.score, 60)
        XCTAssertEqual(generalLive.score, 40)
        XCTAssertEqual(recentFinal.score, 25)
        XCTAssertEqual(idle.score, 0)

        XCTAssertGreaterThan(live.score, pregame.score)
        XCTAssertGreaterThan(pregame.score, generalLive.score)
        XCTAssertGreaterThan(generalLive.score, recentFinal.score)
        XCTAssertGreaterThan(recentFinal.score, idle.score)
    }

    func testScheduledGamePromotesBeforeKickoffAndAtKickoffThenExpires() {
        let kickoff = base.addingTimeInterval(2 * 3600)
        let state = GameRelevanceState254A.scheduled(commenceTime: kickoff, startIsTbd: false)

        // 2 hours before kickoff: idle
        XCTAssertEqual(WidgetRelevanceRule254A.spec(for: state, at: base), .zero)

        // 30 minutes before kickoff: pregame score with 30m duration
        let pregameStart = kickoff.addingTimeInterval(-30 * 60)
        let pregame = WidgetRelevanceRule254A.spec(for: state, at: pregameStart)
        XCTAssertEqual(pregame.score, 60)
        XCTAssertEqual(pregame.duration, 30 * 60, accuracy: 0.5)

        // At kickoff: live score with 3h fallback window
        let atKickoff = WidgetRelevanceRule254A.spec(for: state, at: kickoff)
        XCTAssertEqual(atKickoff.score, 100)
        XCTAssertEqual(atKickoff.duration, 3 * 3600, accuracy: 0.5)

        // 1 hour into game without refresh: live score with 2h remaining
        let midGame = WidgetRelevanceRule254A.spec(for: state, at: kickoff.addingTimeInterval(3600))
        XCTAssertEqual(midGame.score, 100)
        XCTAssertEqual(midGame.duration, 2 * 3600, accuracy: 0.5)

        // 3 hours after scheduled kickoff: drops back to 0 so unrefreshed widget never sticks
        let expired = WidgetRelevanceRule254A.spec(for: state, at: kickoff.addingTimeInterval(3 * 3600))
        XCTAssertEqual(expired, .zero)
    }

    func testScheduledTbdGameIsNeverPromoted() {
        let kickoff = base.addingTimeInterval(10 * 60)
        let state = GameRelevanceState254A.scheduled(commenceTime: kickoff, startIsTbd: true)
        XCTAssertEqual(WidgetRelevanceRule254A.spec(for: state, at: base), .zero)
        XCTAssertEqual(WidgetRelevanceRule254A.boundaryDates(for: state, now: base), [])
    }

    func testFinalResultCooldownAndBoundary() {
        let finalAt = base.addingTimeInterval(-15 * 60)
        let state = GameRelevanceState254A.finalResult(observedAt: finalAt)

        let recent = WidgetRelevanceRule254A.spec(for: state, at: base)
        XCTAssertEqual(recent.score, 25)
        XCTAssertEqual(recent.duration, 45 * 60, accuracy: 0.5)

        let boundaries = WidgetRelevanceRule254A.boundaryDates(for: state, now: base)
        XCTAssertEqual(boundaries, [finalAt.addingTimeInterval(60 * 60)])

        // After 1 hour: drops to 0
        let old = WidgetRelevanceRule254A.spec(for: state, at: finalAt.addingTimeInterval(60 * 60))
        XCTAssertEqual(old, .zero)
        XCTAssertEqual(WidgetRelevanceRule254A.boundaryDates(for: state, now: finalAt.addingTimeInterval(60 * 60)), [])
    }

    func testScheduledBoundaryDatesEmitLeadKickoffAndFallbackEnd() {
        let kickoff = base.addingTimeInterval(2 * 3600)
        let state = GameRelevanceState254A.scheduled(commenceTime: kickoff, startIsTbd: false)
        let boundaries = WidgetRelevanceRule254A.boundaryDates(for: state, now: base)
        XCTAssertEqual(boundaries, [
            kickoff.addingTimeInterval(-30 * 60),
            kickoff,
            kickoff.addingTimeInterval(3 * 3600),
        ])
    }

    func testGeneralLiveGamesWidgetIgnoresPlaceholderAndEmpty() {
        XCTAssertEqual(WidgetRelevanceRule254A.liveGamesWidget(liveCount: 3, isPlaceholder: true), .zero)
        XCTAssertEqual(WidgetRelevanceRule254A.liveGamesWidget(liveCount: 0, isPlaceholder: false), .zero)
        let active = WidgetRelevanceRule254A.liveGamesWidget(liveCount: 1, isPlaceholder: false)
        XCTAssertEqual(active.score, 40)
        XCTAssertGreaterThan(active.duration, 0)
    }

    // MARK: - iPhone SavedItemWidget adapter

    private func decodeEvent(status: String, commenceISO: String?, observedISO: String?,
                             homeScore: Int? = nil, awayScore: Int? = nil,
                             settledResult: String? = nil) throws -> SavedWidgetEventDetail10875 {
        var obj: [String: Any] = [
            "id": 9001,
            "sport": "basketball_nba",
            "home_team": "Boston Celtics",
            "away_team": "New York Knicks",
            "status": status,
            "hero_probability": 0.62,
            "hero_probability_away": 0.38,
        ]
        if let commenceISO { obj["commence_time"] = commenceISO }
        if let observedISO { obj["hero_probability_observed_at"] = observedISO }
        if let homeScore { obj["home_score"] = homeScore }
        if let awayScore { obj["away_score"] = awayScore }
        if let settledResult { obj["hero_settled_result"] = settledResult }
        let data = try JSONSerialization.data(withJSONObject: obj)
        return try SavedWidgetDetailDecoding10875.decoder().decode(SavedWidgetEventDetail10875.self, from: data)
    }

    func testSavedWidgetLivePregameAndFinalRelevance() throws {
        let iso = ISO8601DateFormatter()
        let selection = SavedWidgetSelection10875(
            scope: "guest",
            subject: SavedWidgetSubject10875(kind: .game, id: 9001),
            side: nil,
            outcomeID: nil
        )

        let liveEvent = try decodeEvent(
            status: "live",
            commenceISO: iso.string(from: base.addingTimeInterval(-3600)),
            observedISO: iso.string(from: base.addingTimeInterval(-30)),
            homeScore: 88, awayScore: 84
        )
        let liveSpec = SavedWidgetTimeline10875.relevance(.detail(.game(liveEvent), offline: false), selection: selection, at: base)
        XCTAssertEqual(liveSpec.score, 100)

        let soonEvent = try decodeEvent(
            status: "scheduled",
            commenceISO: iso.string(from: base.addingTimeInterval(20 * 60)),
            observedISO: iso.string(from: base.addingTimeInterval(-60))
        )
        let soonSpec = SavedWidgetTimeline10875.relevance(.detail(.game(soonEvent), offline: false), selection: selection, at: base)
        XCTAssertEqual(soonSpec.score, 60)
        let soonBoundaries = SavedWidgetTimeline10875.relevanceBoundaryDates(
            .detail(.game(soonEvent), offline: false), selection: selection, now: base
        )
        XCTAssertEqual(soonBoundaries.count, 2) // kickoff and kickoff+3h

        let farEvent = try decodeEvent(
            status: "scheduled",
            commenceISO: iso.string(from: base.addingTimeInterval(4 * 3600)),
            observedISO: iso.string(from: base.addingTimeInterval(-60))
        )
        XCTAssertEqual(
            SavedWidgetTimeline10875.relevance(.detail(.game(farEvent), offline: false), selection: selection, at: base),
            .zero
        )

        let recentFinalEvent = try decodeEvent(
            status: "completed",
            commenceISO: iso.string(from: base.addingTimeInterval(-4 * 3600)),
            observedISO: iso.string(from: base.addingTimeInterval(-20 * 60)),
            homeScore: 112, awayScore: 108, settledResult: "home"
        )
        XCTAssertEqual(
            SavedWidgetTimeline10875.relevance(.detail(.game(recentFinalEvent), offline: false), selection: selection, at: base).score,
            25
        )

        // Message/error states never promote
        XCTAssertEqual(SavedWidgetTimeline10875.relevance(.notConfigured, selection: nil, at: base), .zero)
        XCTAssertEqual(SavedWidgetTimeline10875.relevance(.unreachable, selection: selection, at: base), .zero)
    }

    // MARK: - Apple Watch Smart Stack adapter

    func testWatchComplicationSnapshotLiveScheduledAndFinalRelevance() {
        let home = WatchCompactTeamIdentity(teamID: 1, abbreviation: "BOS")
        let away = WatchCompactTeamIdentity(teamID: 2, abbreviation: "NYK")
        let observed = base.addingTimeInterval(-30)
        let saved = base.addingTimeInterval(-10)

        // 1. Live game on Watch -> 100
        let liveRect = WatchRectangularReading(
            version: 1, eventID: 501, kind: .liveForecast,
            homeName: "Celtics", awayName: "Knicks",
            home: home, away: away,
            homePercent: 64, homeScore: 88, awayScore: 84,
            commenceTime: nil, stateLabel: "Live",
            observedAt: observed, scoreObservedAt: observed
        )
        let liveSnap = WatchComplicationSnapshot(
            eventID: 501, title: "Celtics win", detail: "64% · Live",
            observedAt: observed, savedAt: saved, rectangularReading: liveRect
        )
        XCTAssertEqual(liveSnap.relevanceSpec254A(now: base).score, 100)

        // 2. Scheduled game starting in 15 min -> 60 + boundary dates at kickoff and kickoff+3h
        let kickoff = base.addingTimeInterval(15 * 60)
        let schedRect = WatchRectangularReading(
            version: 1, eventID: 502, kind: .scheduledForecast,
            homeName: "Celtics", awayName: "Knicks",
            home: home, away: away,
            homePercent: 58, homeScore: nil, awayScore: nil,
            commenceTime: kickoff, stateLabel: "Scheduled",
            observedAt: observed, scoreObservedAt: nil
        )
        let schedSnap = WatchComplicationSnapshot(
            eventID: 502, title: "Celtics win", detail: "58% · Scheduled",
            observedAt: observed, savedAt: saved, rectangularReading: schedRect
        )
        XCTAssertEqual(schedSnap.relevanceSpec254A(now: base).score, 60)
        XCTAssertEqual(schedSnap.relevanceBoundaryDates254A(now: base), [
            kickoff,
            kickoff.addingTimeInterval(3 * 3600),
        ])

        // 3. Final game 15 min ago -> 25; 2 hours ago -> 0
        let finalAt = base.addingTimeInterval(-15 * 60)
        let finalRect = WatchRectangularReading(
            version: 1, eventID: 503, kind: .finalResult,
            homeName: "Celtics", awayName: "Knicks",
            home: home, away: away,
            homePercent: nil, homeScore: 112, awayScore: 108,
            commenceTime: nil, stateLabel: "Final",
            observedAt: finalAt, scoreObservedAt: finalAt
        )
        let finalSnap = WatchComplicationSnapshot(
            eventID: 503, title: "Celtics won", detail: "Final · 112–108",
            observedAt: finalAt, savedAt: saved, rectangularReading: finalRect
        )
        XCTAssertEqual(finalSnap.relevanceSpec254A(now: base).score, 25)
        XCTAssertEqual(finalSnap.relevanceSpec254A(now: finalAt.addingTimeInterval(2 * 3600)), .zero)

        // 4. Futures market on Watch -> 0
        let marketRect = WatchRectangularReading(
            version: 1, eventID: 504, kind: .futureForecast,
            homeName: "NBA Champion", awayName: "Celtics",
            home: nil, away: nil,
            homePercent: 28, homeScore: nil, awayScore: nil,
            commenceTime: nil, stateLabel: "Market",
            observedAt: observed, scoreObservedAt: nil
        )
        let marketSnap = WatchComplicationSnapshot(
            eventID: 504, title: "NBA Champion", detail: "Celtics 28%",
            observedAt: observed, savedAt: saved, rectangularReading: marketRect
        )
        XCTAssertEqual(marketSnap.relevanceSpec254A(now: base), .zero)
    }
}
