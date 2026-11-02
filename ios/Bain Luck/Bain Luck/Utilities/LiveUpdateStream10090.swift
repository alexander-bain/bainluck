import Foundation

/// #10090 (Alex 2026-11-01) — THE EKG'S SCROLLING LIST OF VENUE UPDATES.
///
/// "Might be cooler to have it be a super-fluid scrolling stream of the
/// updates we're getting, with the source and the timestamp to the hundredth
/// of a second, even if they're duplicates." The stream's heartbeat carries
/// `updates` (`[[venue, ISO receipt]]`, every venue input since the last
/// heartbeat) and `update_p` beside it, each input's venue home-team
/// probability after it; the page keeps the newest `capacity` here. Not
/// trades, and never a price's age.
nonisolated struct LiveUpdateStream: Equatable {
    struct Update: Equatable, Hashable, Identifiable {
        var source: String
        var at: Date
        /// The venue's home-team probability after this input, nil when unknown.
        var p: Double? = nil
        /// Arrival order on this page: one book message can price several legs
        /// at the same millisecond, and each is its own row (duplicates shown).
        var seq: Int = 0
        var id: Int { seq }
    }

    static let capacity = 300

    /// Newest first.
    private(set) var updates: [Update] = []
    private var nextSeq = 0
    /// Newest receipt held per venue: a reconnect's first heartbeat can repeat
    /// what the last one sent, and those rows are not new.
    private var newest: [String: Date] = [:]

    /// Adds the heartbeat's updates (oldest first, as sent) that are newer than
    /// what is held for their venue, keeping same-time duplicates; newest
    /// first, bounded.
    mutating func add(_ incoming: [Update]) {
        let floor = newest
        var fresh: [Update] = []
        for update in incoming.sorted(by: { $0.at < $1.at }) {
            if let held = floor[update.source], update.at <= held { continue }
            var row = update
            row.seq = nextSeq
            nextSeq += 1
            fresh.append(row)
            newest[update.source] = max(newest[update.source] ?? update.at, update.at)
        }
        guard !fresh.isEmpty else { return }
        updates = Array((fresh.reversed() + updates).prefix(Self.capacity))
    }

    mutating func clear() { updates = []; newest = [:] }

    /// A venue's home-team probability as the row prints it: 81.0%, or a dash.
    static func probabilityText(_ p: Double?) -> String {
        guard let p else { return "—" }
        return String(format: "%.1f%%", (p * 1000).rounded() / 10)
    }

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

/// #10090 (Alex 2026-11-01: "it's also not a scrolling stream. it just arrives
/// in batches") — what the open list shows, revealed at the venues' own pace.
/// A heartbeat's rows are replayed from its arrival by their own receipt gaps,
/// capped at `spread` so a batch finishes before the next is due; a new batch
/// first shows what the last has not. Revealed rows join the screen's own list,
/// newest receipt first, so the stream's bound never takes a shown row away.
/// Mirrors the website's `advanceScreen`.
nonisolated struct LiveUpdateScreen: Equatable {
    struct Pending: Equatable { var seq: Int; var at: TimeInterval }

    static let spread: TimeInterval = 1.0
    static let capacity = 100

    private(set) var scheduled = -1
    private(set) var shown = -1
    private(set) var queue: [Pending] = []
    private(set) var rows: [LiveUpdateStream.Update] = []

    init() {}

    /// The screen when the list opens: what is already listed, at once.
    init(opening updates: [LiveUpdateStream.Update]) {
        let top = updates.map(\.seq).max() ?? -1
        scheduled = top
        shown = top
        rows = Array(updates.sorted(by: Self.newerReceipt).prefix(Self.capacity))
    }

    var waiting: Bool { !queue.isEmpty }

    /// Schedules what is new in `updates` and reveals what is due at `now`
    /// (a monotonic clock, seconds).
    mutating func advance(_ updates: [LiveUpdateStream.Update], now: TimeInterval) {
        let from = shown
        let fresh = updates.filter { $0.seq > scheduled }.sorted { $0.seq < $1.seq }
        if let first = fresh.first {
            if let last = queue.last { shown = max(shown, last.seq) }
            let base = fresh.map(\.at).min() ?? first.at
            var last = now
            queue = fresh.map { update in
                last = max(last, now + min(Self.spread, max(0, update.at.timeIntervalSince(base))))
                return Pending(seq: update.seq, at: last)
            }
            scheduled = fresh[fresh.count - 1].seq
        }
        while let next = queue.first, next.at <= now {
            shown = next.seq
            queue.removeFirst()
        }
        guard shown > from else { return }
        let added = updates.filter { $0.seq > from && $0.seq <= shown }
        rows = Array((added + rows).sorted(by: Self.newerReceipt).prefix(Self.capacity))
    }

    private static func newerReceipt(_ a: LiveUpdateStream.Update, _ b: LiveUpdateStream.Update) -> Bool {
        a.at != b.at ? a.at > b.at : a.seq > b.seq
    }
}
