import Foundation

/// #12307 — what an App Clip invocation asks for, and the one public read that
/// answers it.
///
/// Only bainluck.com's own game and market pages qualify, the same two routes
/// the full app's universal links open (`NavigationCoordinator.handleURL`):
/// `https://bainluck.com/events/<id>` and `https://bainluck.com/futures/<id>`,
/// on either host. Anything else is not something the clip can show, and it
/// says so rather than guessing a page.
///
/// The read is the saved widget's (`SavedItemWidgetFetch10875`): the same URL,
/// the same 404/410-is-gone rule, and the widget's decode and reading rules, so
/// the clip prints what the widget and the page one tap away print.
/// `AppClip12307Tests` holds the URLs to the widget's.
nonisolated enum ClipInvocation12307 {
    static let hosts: Set<String> = ["bainluck.com", "www.bainluck.com"]
    static let apiBase = "https://api.bainluck.com"

    /// The game or market an invocation URL names, or nil.
    static func subject(from url: URL?) -> SavedWidgetSubject10875? {
        guard let url, url.scheme?.lowercased() == "https",
              let host = url.host?.lowercased(), hosts.contains(host) else { return nil }
        let parts = url.pathComponents.filter { $0 != "/" }
        guard parts.count == 2, let id = Int(parts[1]), id > 0 else { return nil }
        switch parts[0] {
        case "events": return SavedWidgetSubject10875(kind: .game, id: id)
        case "futures": return SavedWidgetSubject10875(kind: .market, id: id)
        default: return nil
        }
    }

    /// The public detail for a subject: the widget's two GETs.
    static func detailURL(for subject: SavedWidgetSubject10875) -> URL? {
        switch subject.kind {
        case .game: return URL(string: "\(apiBase)/api/events/\(subject.id)")
        case .market: return URL(string: "\(apiBase)/api/futures/\(subject.id)?representation=verified_title")
        }
    }

    /// The page on bainluck.com a reader can open instead, for the same subject.
    static func webURL(for subject: SavedWidgetSubject10875) -> URL? {
        URL(string: "https://www.bainluck.com/\(subject.kind == .game ? "events" : "futures")/\(subject.id)")
    }
}

/// What the clip has for its subject, before a date is applied.
nonisolated enum ClipLoad12307: Equatable, Sendable {
    /// Waiting for the first answer.
    case loading
    /// The detail, read again at each moment it is shown, so a current price
    /// ages into "last recorded" on its own clock while the clip stays open.
    case detail(SavedWidgetDetailPayload10875)
    /// The link names a page the clip doesn't show.
    case unsupported
    /// The detail answered "not found" or "gone".
    case gone
    /// No answer, and nothing to show.
    case unreachable
}

/// Main-actor, like `SavedWidgetReadingRules10875`, whose readings it returns.
enum ClipLoader12307 {
    /// One read. `fetch` returns the response body and status, or throws on a
    /// network failure; the status rule is the widget's.
    static func load(_ subject: SavedWidgetSubject10875?,
                     fetch: (URL) async throws -> (Data, Int)) async -> ClipLoad12307 {
        guard let subject, let url = ClipInvocation12307.detailURL(for: subject) else { return .unsupported }
        let data: Data
        let status: Int
        do {
            (data, status) = try await fetch(url)
        } catch {
            return .unreachable
        }
        if status == 404 || status == 410 { return .gone }
        guard (200...299).contains(status),
              let payload = try? SavedWidgetDetailPayload10875.decode(data, as: subject.kind) else { return .unreachable }
        // A market page refuses an answer for another id, so the clip does too;
        // a game is drawn as served (a proven duplicate comes back as its
        // canonical row), as the event page and the widget draw it.
        if subject.kind == .market, payload.id != subject.id { return .unreachable }
        return .detail(payload)
    }

    /// The reading at `date`: the favourite leads a game, the market page's
    /// hero leg leads a market, as on the pages themselves.
    static func reading(_ payload: SavedWidgetDetailPayload10875, at date: Date) -> SavedWidgetReading10875 {
        switch payload {
        case .game(let event): return SavedWidgetReadingRules10875.game(event, side: nil, now: date)
        case .market(let market): return SavedWidgetReadingRules10875.market(market, outcomeID: nil, now: date)
        }
    }

    /// The line under the rows, in the saved widget's words (`SavedClock10875`):
    /// a current price says when it was observed, an old one says it's the last
    /// recorded, and a result or a missing number says nothing here.
    static func caption(_ reading: SavedWidgetReading10875, now: Date) -> String? {
        switch reading.phase {
        case .current:
            return clock(reading.observedAt, relativeTo: now).map { "As of \($0)" }
        case .lastRecorded:
            return "Last recorded " + (clock(reading.observedAt, relativeTo: now) ?? "· time unknown")
        case .openingLine:
            return "Opening line"
        case .noResult:
            return reading.lastRecordedFigure.map { figure in
                "Last recorded \(figure)" + (clock(reading.observedAt, relativeTo: now).map { " · \($0)" } ?? "")
            }
        case .result, .unavailable:
            return nil
        }
    }

    /// The observation clock, absolute: "3:42 PM" today, "Oct 15, 3:42 PM" otherwise.
    static func clock(_ date: Date?, relativeTo now: Date) -> String? {
        guard let date else { return nil }
        if Calendar.current.isDate(date, inSameDayAs: now) {
            return date.formatted(date: .omitted, time: .shortened)
        }
        return date.formatted(.dateTime.month(.abbreviated).day().hour().minute())
    }

    static let session: URLSession = {
        let config = URLSessionConfiguration.ephemeral
        config.timeoutIntervalForRequest = 15
        config.timeoutIntervalForResource = 30
        config.requestCachePolicy = .reloadIgnoringLocalCacheData
        return URLSession(configuration: config)
    }()

    static func productionFetch(_ url: URL) async throws -> (Data, Int) {
        let (data, response) = try await session.data(from: url)
        return (data, (response as? HTTPURLResponse)?.statusCode ?? 0)
    }
}
