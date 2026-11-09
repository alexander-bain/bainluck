import Foundation

/// #12316 Smart Stack card freshness. The watch app refreshes only while it is open, so
/// during a game the card could be showing a reading saved long before. When the chosen game
/// has started by its schedule, is not final, its game-day window is open and the saved
/// reading is past the face's two-minute live threshold, the card fetches the public event
/// once, with a short bound, and shows a newer reading of the same game. Any failure shows
/// the saved reading with its age. It never writes the shared file: the app stays its only
/// writer, and the face slot keeps drawing what the app saved. With the app closed, only a
/// Bain Luck complication on the active face asks the card again (`faceRecheck`).
nonisolated enum WatchYourGameRefresh {
    static let timeoutSeconds: TimeInterval = 8
    /// How soon the face asks again while the game is under way: when a saved reading stops
    /// being live, so the card is asked for a newer one about as soon as it could show one.
    static let faceRecheckSeconds: TimeInterval = WatchRectangularReading.liveStaleThresholdSeconds

    private static func isFinal(_ saved: WatchComplicationSnapshot) -> Bool {
        ["completed", "final"].contains(saved.status?.lowercased() ?? "")
    }

    /// Under way by its schedule: the game-day window is open, it has started, and it is not final.
    static func isUnderway(_ saved: WatchComplicationSnapshot, now: Date) -> Bool {
        guard let window = saved.relevanceWindow, window.contains(now),
              let start = saved.commenceTime, now >= start, !isFinal(saved) else { return false }
        return true
    }

    static func wantsRefresh(_ saved: WatchComplicationSnapshot, now: Date) -> Bool {
        guard isUnderway(saved, now: now) else { return false }
        let age = now.timeIntervalSince(saved.observedAt)
        return age.isFinite && age > WatchRectangularReading.liveStaleThresholdSeconds
    }

    /// When the face asks for its next timeline. The card has no timeline of its own, so with
    /// the app closed nothing else asks it for a new entry: a game not started yet is asked
    /// about at its start, one under way every `faceRecheckSeconds`, and an ask whose saved
    /// reading `wantsRefresh` asks the card, which fetches. nil: the face keeps its own end.
    static func faceRecheck(_ saved: WatchComplicationSnapshot?, now: Date) -> Date? {
        guard let saved, !isFinal(saved), let start = saved.commenceTime else { return nil }
        if start > now { return start }
        return isUnderway(saved, now: now) ? now.addingTimeInterval(faceRecheckSeconds) : nil
    }

    static func request(eventID: Int) -> URLRequest {
        var request = URLRequest(url: URL(string: "https://api.bainluck.com/api/events/\(eventID)")!)
        request.timeoutInterval = timeoutSeconds
        request.cachePolicy = .reloadIgnoringLocalCacheData
        return request
    }

    /// The one session behind the card's refresh: ephemeral, and bounded end to end.
    static let session: URLSession = {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.timeoutIntervalForRequest = timeoutSeconds
        configuration.timeoutIntervalForResource = timeoutSeconds
        configuration.waitsForConnectivity = false
        return URLSession(configuration: configuration)
    }()

    /// The reading the card shows: a newer projection of the same game, or the saved one.
    static func reading(saved: WatchComplicationSnapshot, now: Date, session: URLSession = session,
                        clock: () -> Date = { Date() }) async -> WatchComplicationSnapshot {
        guard wantsRefresh(saved, now: now),
              let fetched = try? await session.data(for: request(eventID: saved.eventID)),
              (fetched.1 as? HTTPURLResponse)?.statusCode == 200,
              let game = try? JSONDecoder().decode(WatchSelectedGame.self, from: fetched.0),
              game.id == saved.eventID else { return saved }
        let fetchedAt = max(now, clock())
        guard let fresh = WatchComplicationProjection.snapshot(game: game, savedAt: fetchedAt),
              fresh.eventID == saved.eventID, fresh.observedAt > saved.observedAt,
              fresh.validatedRectangularReading(now: fetchedAt) != nil else { return saved }
        return fresh
    }
}
