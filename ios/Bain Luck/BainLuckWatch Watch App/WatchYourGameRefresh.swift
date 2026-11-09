import Foundation

/// #12316 Smart Stack card freshness. The watch app refreshes only while it is open, so
/// during a game the card could be showing a reading saved long before. When the chosen game
/// has started by its schedule, is not final, its game-day window is open and the saved
/// reading is past the face's two-minute live threshold, the card fetches the public event
/// once, with a short bound, and shows a newer reading of the same game. Any failure shows
/// the saved reading with its age. It never writes the shared file: the app stays its only
/// writer, and the face slot keeps drawing what the app saved.
nonisolated enum WatchYourGameRefresh {
    static let timeoutSeconds: TimeInterval = 8

    static func wantsRefresh(_ saved: WatchComplicationSnapshot, now: Date) -> Bool {
        guard let window = saved.relevanceWindow, window.contains(now),
              let start = saved.commenceTime, now >= start,
              !["completed", "final"].contains(saved.status?.lowercased() ?? "") else { return false }
        let age = now.timeIntervalSince(saved.observedAt)
        return age.isFinite && age > WatchRectangularReading.liveStaleThresholdSeconds
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
