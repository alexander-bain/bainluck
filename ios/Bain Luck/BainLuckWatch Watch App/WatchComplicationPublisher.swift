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
        if game.isFinal {
            kind = .final
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
                kind = .forecast
                title = "\(game.homeTeam) win"
                detail = "\(probability) · \(game.stateLabel)"
                observed = clock
            } else if ["live", "in_progress"].contains(game.status?.lowercased() ?? ""), let home = game.homeScore, let away = game.awayScore,
                      home >= 0, away >= 0,
                      let clock = game.scoreObservedAt, validObservation(clock, savedAt: savedAt) {
                // A score is independently useful when no honest probability reading exists.
                // Keep away-home order aligned with the named matchup, and use only its clock.
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
        let parent = WatchComplicationSnapshot(version: 1, eventID: game.id, title: title,
            detail: detail, observedAt: observed, savedAt: savedAt)
        return WatchComplicationSnapshot(version: 1, eventID: game.id, title: title,
            detail: detail, observedAt: observed, savedAt: savedAt,
            circularReading: compact.matches(parent) ? compact : nil)
    }

    private static func validObservation(_ observed: Date, savedAt: Date) -> Bool {
        observed.timeIntervalSinceReferenceDate.isFinite
            && savedAt.timeIntervalSinceReferenceDate.isFinite
            && observed <= savedAt
    }
}

nonisolated enum WatchComplicationPublisher {
    #if canImport(WidgetKit)
    @MainActor private static let reloads = WatchComplicationReloads {
        WidgetCenter.shared.reloadTimelines(ofKind: "BainLuckComplication")
    }
    #endif
    /// Shared storage is unavailable until the app and extension are properly entitled.
    /// Never substitute separate standard defaults and pretend data was shared.
    static func publish(game: WatchSelectedGame?, savedAt: Date?) {
        let directory = FileManager.default.containerURL(forSecurityApplicationGroupIdentifier: "group.com.bainluck.watch")
        let snapshot = game.flatMap { game in savedAt.flatMap { WatchComplicationProjection.snapshot(game: game, savedAt: $0) } }
        let now = Date()
        let valid = snapshot.flatMap { $0.isValid(now: now) ? $0 : nil }
        guard write(valid, to: directory, now: now) else { return }
        #if canImport(WidgetKit)
        // The shared snapshot is already current. Foreground stream bursts
        // must not ask WidgetKit to rebuild on every accepted detail response.
        let key = valid.map { "\($0.eventID):\(String(describing: $0.circularReading?.kind))" }
        let live = valid != nil && game?.isLive == true
        DispatchQueue.main.async {
            reloads.changed(key: key, live: live)
        }
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
               existing.circularReading == valid.circularReading {
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


/// Bound WidgetKit reload requests independently of visible app updates.
/// Every snapshot is still written immediately by the publisher above.
@MainActor final class WatchComplicationReloads {
    private let now: () -> TimeInterval
    private let sleep: @MainActor (TimeInterval) async throws -> Void
    private let reload: @MainActor () -> Void
    private var lastKey: String?
    private var lastReload: TimeInterval?
    private var pending: Task<Void, Never>?
    private var generation = UUID()
    private static let liveInterval: TimeInterval = 30

    init(now: @escaping () -> TimeInterval = { ProcessInfo.processInfo.systemUptime },
         sleep: @escaping @MainActor (TimeInterval) async throws -> Void = { try await Task.sleep(for: .seconds($0)) },
         reload: @escaping @MainActor () -> Void) {
        self.now = now; self.sleep = sleep; self.reload = reload
    }

    func changed(key: String?, live: Bool) {
        // Clear, a different event/reading kind and non-live results are urgent.
        guard let key, key == lastKey, live, let lastReload else {
            reloadNow(key: key)
            return
        }
        let remaining = Self.liveInterval - (now() - lastReload)
        guard remaining > 0 else { reloadNow(key: key); return }
        guard pending == nil else { return } // Do not postpone the trailing edge.
        let token = generation
        pending = Task { @MainActor [weak self, sleep = self.sleep] in
            do { try await sleep(remaining) } catch { return }
            guard let self, !Task.isCancelled, self.generation == token else { return }
            self.reloadNow(key: key)
        }
    }

    private func reloadNow(key: String?) {
        generation = UUID()
        pending?.cancel(); pending = nil
        lastKey = key; lastReload = now()
        reload()
    }
}
