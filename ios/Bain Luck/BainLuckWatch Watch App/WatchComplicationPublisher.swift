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
        if game.isFinal {
            guard let home = game.homeScore, let away = game.awayScore, home >= 0, away >= 0 else { return nil }
            if home > away { title = "\(game.homeTeam) won"; detail = "Final · \(home)–\(away)" }
            else if away > home { title = "\(game.awayTeam) won"; detail = "Final · \(away)–\(home)" }
            else { title = "\(game.awayTeam) at \(game.homeTeam)"; detail = "Final · tied \(home)–\(away)" }
            observed = game.scoreObservedAt
        } else {
            guard ["live", "scheduled", "upcoming", "in_progress", "pregame"].contains(game.status?.lowercased() ?? ""),
                  game.showsForecast else { return nil }
            if let probability = game.homeProbabilityText,
               let clock = game.probabilityObservedAt, validObservation(clock, savedAt: savedAt) {
                title = "\(game.homeTeam) win"
                detail = "\(probability) · \(game.stateLabel)"
                observed = clock
            } else if ["live", "in_progress"].contains(game.status?.lowercased() ?? ""), let home = game.homeScore, let away = game.awayScore,
                      home >= 0, away >= 0,
                      let clock = game.scoreObservedAt, validObservation(clock, savedAt: savedAt) {
                // A score is independently useful when no honest probability reading exists.
                // Keep away-home order aligned with the named matchup, and use only its clock.
                title = "\(game.awayTeam) at \(game.homeTeam)"
                detail = "Score \(away)–\(home) · Live"
                observed = clock
            } else {
                return nil
            }
        }
        guard let observed, validObservation(observed, savedAt: savedAt) else { return nil }
        return WatchComplicationSnapshot(version: 1, eventID: game.id, title: title,
                                         detail: detail, observedAt: observed, savedAt: savedAt)
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
               existing.observedAt == valid.observedAt {
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
