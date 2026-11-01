import Foundation

/// #10090 (Alex 2026-11-01) — THE EKG'S SCROLLING LIST OF VENUE UPDATES.
///
/// "Might be cooler to have it be a super-fluid scrolling stream of the
/// updates we're getting, with the source and the timestamp to the hundredth
/// of a second, even if they're duplicates." The stream's heartbeat carries
/// `updates` (`[[venue, ISO receipt]]`, every venue input since the last
/// heartbeat); the page keeps the newest `capacity` here. Not trades, and
/// never a price's age: each row says only that a venue reported in.
nonisolated struct LiveUpdateStream: Equatable {
    struct Update: Equatable, Hashable, Identifiable {
        var source: String
        var at: Date
        var id: String { "\(source)@\(at.timeIntervalSince1970)" }
    }

    static let capacity = 100

    /// Newest first.
    private(set) var updates: [Update] = []

    /// Adds the heartbeat's updates, dropping any already held (a reconnect's
    /// first heartbeat can repeat the last one's), newest first, bounded.
    mutating func add(_ incoming: [Update]) {
        guard !incoming.isEmpty else { return }
        let held = Set(updates)
        let fresh = incoming.filter { !held.contains($0) }
        guard !fresh.isEmpty else { return }
        updates = Array((fresh + updates).sorted { ($0.at, $0.source) > ($1.at, $1.source) }
            .prefix(Self.capacity))
    }

    mutating func clear() { updates = [] }

    /// "Kalshi", "Polymarket", or the venue's own name.
    static func venueName(_ source: String) -> String {
        switch source {
        case "kalshi": return "Kalshi"
        case "polymarket": return "Polymarket"
        default: return source.capitalized
        }
    }

    /// The receipt time to the hundredth of a second, local time: 2:57:03.42 PM.
    static func timeText(_ date: Date, timeZone: TimeZone = .current) -> String {
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = timeZone
        let parts = calendar.dateComponents([.hour, .minute, .second, .nanosecond], from: date)
        let hour24 = parts.hour ?? 0
        let hour = hour24 % 12 == 0 ? 12 : hour24 % 12
        let hundredths = min(99, (parts.nanosecond ?? 0) / 10_000_000)
        return String(format: "%d:%02d:%02d.%02d %@", hour, parts.minute ?? 0, parts.second ?? 0,
                      hundredths, hour24 < 12 ? "AM" : "PM")
    }
}
