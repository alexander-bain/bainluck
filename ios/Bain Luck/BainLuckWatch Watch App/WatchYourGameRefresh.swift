import Foundation

/// #12316 Smart Stack card freshness. The watch app refreshes only while it is open, so
/// during a game the card could be showing a reading saved long before. When the chosen game
/// has started by its schedule, is not final, its game-day window is open and the newest
/// reading is past the face's two-minute live threshold, the card fetches the public event
/// once, with a short bound, and shows a newer reading of the same game. It keeps that reading
/// in its own store (never the app's saved file: the app stays that file's only writer) and
/// asks the face to draw it, so the face and the card show the same reading. Any failure shows
/// the newest reading with its age. With the app closed, only a Bain Luck complication on the
/// active face asks the card again (`faceRecheck`).
nonisolated enum WatchYourGameRefresh {
    static let timeoutSeconds: TimeInterval = 8
    /// How soon the face asks again while the game is under way and its newest reading is
    /// already past the live threshold.
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

    /// `saved` is the newest reading the face and the card draw, so a reading the card just
    /// kept wants nothing more until it, too, is past two minutes: no reload loop.
    static func wantsRefresh(_ saved: WatchComplicationSnapshot, now: Date) -> Bool {
        guard isUnderway(saved, now: now) else { return false }
        let age = now.timeIntervalSince(saved.observedAt)
        return age.isFinite && age > WatchRectangularReading.liveStaleThresholdSeconds
    }

    /// When the face asks for its next timeline. The card has no timeline of its own, so with
    /// the app closed nothing else asks it for a new entry: a game not started yet is asked
    /// about at its start; one under way the moment its newest reading stops being live (so
    /// the card checks before the face would say "Stale", which it then says only if nothing
    /// newer came back), and every `faceRecheckSeconds` once it is older. An ask whose newest
    /// reading `wantsRefresh` asks the card, which fetches. nil: the face keeps its own end.
    static func faceRecheck(_ saved: WatchComplicationSnapshot?, now: Date) -> Date? {
        guard let saved, !isFinal(saved), let start = saved.commenceTime else { return nil }
        if start > now { return start }
        guard isUnderway(saved, now: now) else { return nil }
        let stale = saved.observedAt.addingTimeInterval(WatchRectangularReading.liveStaleThresholdSeconds + 1)
        let regular = now.addingTimeInterval(faceRecheckSeconds)
        return stale > now ? min(stale, regular) : regular
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

    /// The reading the card shows: a newer projection of the same game, or `saved`. Only a
    /// strictly newer one is handed to `keep`, once.
    static func reading(saved: WatchComplicationSnapshot, now: Date, session: URLSession = session,
                        clock: () -> Date = { Date() },
                        keep: (WatchYourGameCardReading) -> Void = { _ in }) async -> WatchComplicationSnapshot {
        guard wantsRefresh(saved, now: now),
              let fetched = try? await session.data(for: request(eventID: saved.eventID)),
              (fetched.1 as? HTTPURLResponse)?.statusCode == 200,
              let game = try? JSONDecoder().decode(WatchSelectedGame.self, from: fetched.0),
              game.id == saved.eventID else { return saved }
        let kept = WatchYourGameCardReading(game: game, fetchedAt: max(now, clock()))
        guard let fresh = kept.snapshot, fresh.eventID == saved.eventID, fresh.observedAt > saved.observedAt,
              fresh.validatedRectangularReading(now: kept.fetchedAt) != nil else { return saved }
        keep(kept)
        return fresh
    }

    /// The card's own store, written here alone (this file is compiled into the widget
    /// extension only). True when the reading was written.
    @discardableResult
    static func keep(_ card: WatchYourGameCardReading, in directory: URL?) -> Bool {
        guard let directory, directory.isFileURL, let data = try? JSONEncoder().encode(card),
              data.count <= WatchYourGameCardReading.maximumBytes else { return false }
        do {
            try data.write(to: directory.appendingPathComponent(WatchYourGameCardReading.filename), options: .atomic)
            return true
        } catch {
            return false
        }
    }
}
