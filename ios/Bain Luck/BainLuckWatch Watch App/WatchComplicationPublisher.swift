import Foundation
#if canImport(WidgetKit)
import WidgetKit
#endif

/// Project using the same rounded probability as the app; never export raw auth/API data.
nonisolated enum WatchComplicationProjection {
    static func snapshot(game: WatchSelectedGame, savedAt: Date) -> WatchComplicationSnapshot? {
        let title: String
        let detail: String
        let observed: Date?
        let kind: WatchCircularReading.Kind
        var rectangularKind: WatchRectangularReading.Kind?
        var rectHomeScore: Int?
        var rectAwayScore: Int?
        var rectScoreObserved: Date?
        var rectCommenceTime: Date?
        if game.isFinal {
            kind = .final
            rectangularKind = .finalResult
            guard let home = game.homeScore, let away = game.awayScore, home >= 0, away >= 0 else { return nil }
            if home > away { title = "\(game.homeTeam) won"; detail = "Final · \(home)–\(away)" }
            else if away > home { title = "\(game.awayTeam) won"; detail = "Final · \(away)–\(home)" }
            else { title = "\(game.awayTeam) at \(game.homeTeam)"; detail = "Final · tied \(home)–\(away)" }
            observed = game.scoreObservedAt
            rectHomeScore = home
            rectAwayScore = away
            rectScoreObserved = observed
        } else {
            let statusLower = game.status?.lowercased() ?? ""
            guard ["live", "scheduled", "upcoming", "in_progress", "pregame"].contains(statusLower),
                  game.showsForecast else { return nil }
            if let probability = game.homeProbabilityText,
               let clock = game.probabilityObservedAt, validObservation(clock, savedAt: savedAt) {
                kind = .forecast
                title = "\(game.homeTeam) win"
                detail = "\(probability) · \(game.stateLabel)"
                observed = clock
                if ["live", "in_progress"].contains(statusLower) {
                    rectangularKind = .liveForecast
                    if let hs = game.homeScore, let ascore = game.awayScore, hs >= 0, ascore >= 0,
                       let sClock = game.scoreObservedAt, validObservation(sClock, savedAt: savedAt),
                       abs(sClock.timeIntervalSince(clock)) <= WatchRectangularReading.liveAgeThresholdSeconds {
                        rectHomeScore = hs
                        rectAwayScore = ascore
                        rectScoreObserved = sClock
                    }
                } else {
                    rectangularKind = .scheduledForecast
                    if let start = game.commenceTime, start.timeIntervalSinceReferenceDate.isFinite {
                        rectCommenceTime = start
                    }
                }
            } else if ["live", "in_progress"].contains(statusLower), let home = game.homeScore, let away = game.awayScore,
                      home >= 0, away >= 0,
                      let clock = game.scoreObservedAt, validObservation(clock, savedAt: savedAt) {
                // Keep parent/circular score snapshot intact; rectangular face omits score-without-odds.
                kind = .score
                title = "\(game.awayTeam) at \(game.homeTeam)"
                detail = "Score \(away)–\(home) · Live"
                observed = clock
            } else {
                return nil
            }
        }
        guard let observed, validObservation(observed, savedAt: savedAt) else { return nil }
        let compact = WatchCircularReading(version: 1, eventID: game.id, kind: kind,
            homeName: game.homeTeam, awayName: game.awayTeam,
            home: game.homeCompactIdentity, away: game.awayCompactIdentity,
            percent: kind == .forecast ? game.homeRenderedPercent : nil,
            homeScore: kind == .forecast ? nil : game.homeScore,
            awayScore: kind == .forecast ? nil : game.awayScore,
            stateLabel: kind == .final ? "Final" : game.stateLabel, observedAt: observed)
        let validHome: WatchCompactTeamIdentity? = game.homeCompactIdentity.flatMap { $0.isValid ? $0 : nil }
        let validAway: WatchCompactTeamIdentity? = game.awayCompactIdentity.flatMap {
            guard $0.isValid else { return nil }
            if let vh = validHome, (vh.teamID == $0.teamID || vh.abbreviation == $0.abbreviation) { return nil }
            return $0
        }
        let rectangular: WatchRectangularReading? = rectangularKind.map { rKind in
            WatchRectangularReading(
                version: 1,
                eventID: game.id,
                kind: rKind,
                homeName: game.homeTeam,
                awayName: game.awayTeam,
                home: validHome,
                away: validAway,
                homePercent: (rKind == .liveForecast || rKind == .scheduledForecast) ? game.homeRenderedPercent : nil,
                homeScore: rectHomeScore,
                awayScore: rectAwayScore,
                commenceTime: rectCommenceTime,
                stateLabel: kind == .final ? "Final" : game.stateLabel,
                observedAt: observed,
                scoreObservedAt: rectScoreObserved
            )
        }
        let parent = WatchComplicationSnapshot(version: 1, eventID: game.id, title: title,
            detail: detail, observedAt: observed, savedAt: savedAt)
        return WatchComplicationSnapshot(version: 1, eventID: game.id, title: title,
            detail: detail, observedAt: observed, savedAt: savedAt,
            circularReading: compact.matches(parent) ? compact : nil,
            rectangularReading: rectangular.flatMap { $0.matches(parent) ? $0 : nil })
    }

    private static func validObservation(_ observed: Date, savedAt: Date) -> Bool {
        observed.timeIntervalSinceReferenceDate.isFinite
            && savedAt.timeIntervalSinceReferenceDate.isFinite
            && observed <= savedAt
    }
}

nonisolated enum WatchComplicationPublisher {
    /// Shared storage is unavailable until the app and extension are properly entitled.
    /// Never substitute separate standard defaults and pretend data was shared.
    static func publish(game: WatchSelectedGame?, savedAt: Date?) {
        let directory = FileManager.default.containerURL(forSecurityApplicationGroupIdentifier: "group.com.bainluck.watch")
        let snapshot = game.flatMap { game in savedAt.flatMap { WatchComplicationProjection.snapshot(game: game, savedAt: $0) } }
        guard write(snapshot, to: directory) else { return }
        #if canImport(WidgetKit)
        WidgetCenter.shared.reloadTimelines(ofKind: "BainLuckComplication")
        #endif
    }

    /// Returns true only when shared bytes changed; unchanged observations need no reload.
    @discardableResult
    static func write(_ snapshot: WatchComplicationSnapshot?, to directory: URL?, now: Date = Date()) -> Bool {
        guard let directory else { return false }
        let url = directory.appendingPathComponent("selected-game.json")
        do {
            let valid = snapshot.flatMap { $0.isValid(now: now) ? $0 : nil }
            if let valid, let existing = WatchComplicationSnapshot.read(from: directory, now: now),
               existing.version == valid.version, existing.eventID == valid.eventID,
               existing.title == valid.title, existing.detail == valid.detail,
               existing.observedAt == valid.observedAt,
               existing.circularReading == valid.circularReading,
               (valid.rectangularReading == nil || existing.rectangularReading == valid.rectangularReading) {
                return false // A newer fetch alone is not a newer reading.
            }
            // A tombstone replaces the previous reading atomically on selection change.
            let data = try valid.map { try JSONEncoder().encode($0) } ?? Data("{}".utf8)
            if valid == nil, let handle = try? FileHandle(forReadingFrom: url) {
                defer { try? handle.close() }
                if (try? handle.read(upToCount: 3)) == data { return false }
            }
            try data.write(to: url, options: .atomic)
            return true
        } catch { return false }
    }
}
