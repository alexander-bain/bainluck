import Foundation

/// The live right-hand edge of the match chart: the pushed frames the page has
/// actually been given, and the rule for when a freshly-polled payload replaces
/// the one already drawn.
///
/// #920 on the phone. The hero ticks on the push stream while the chart stands
/// still, so one screen prints two different numbers for one question — the
/// thing "the blend is the product" exists to forbid. Two separate causes, both
/// of them here:
///
///   1. **The chart never adopted a fresher payload.** `OddsChartView` holds its
///      history in a `@StateObject`, whose `wrappedValue` autoclosure SwiftUI
///      evaluates ONCE per view identity. `EventDetailViewModel` re-polls every
///      120 s and hands the result down as `preloadedHistory:`, and every one of
///      those was discarded; `OddsChartViewModel.load()` then guards on
///      `history == nil`, so it never re-fetched either. The chart a reader saw
///      was pinned to the moment the page opened, for as long as it stayed open.
///
///   2. **Pushed frames reached the hero and stopped there.**
///      `EventDetailViewModel.apply` writes a frame into `event.currentOdds` and
///      nothing else, and `OddsChartView` does not read `currentOdds` at all.
///
/// Everything in this file is pure and clock-free on purpose: the freeze is a
/// lifecycle bug, and a lifecycle bug proved only through a lifecycle is proved
/// slowly and flakily. The decisions are here; the wiring is two call sites.
// MARK: - A pushed blend

/// One published live blend, held at the moment the server says it was true.
///
/// `LiveStreamFrame.p` is the AGGREGATE home probability, not the single source
/// that happened to move — `build_frame`'s docstring in `app/utils/live_push.py`
/// is explicit that publishing the moved source's own price "would put a second,
/// disagreeing number on screen". That is the whole reason a frame may be
/// appended to the backend's `aggregate_line`: it is a later reading of the same
/// line, not a different one.
///
/// The date is the STAMPED `updated_at`, never the arrival time. A frame that
/// spent two seconds in a queue belongs where the data was true, not where the
/// packet landed — otherwise the segment joining it to the backend points either
/// side of it bends under network jitter.
nonisolated struct LiveBlendPoint: Sendable, Equatable {
    let date: Date
    let homeProbability: Double

    init(date: Date, homeProbability: Double) {
        self.date = date
        self.homeProbability = homeProbability
    }
}

// MARK: - The buffer

/// Accumulates pushed blends for as long as the page is open.
nonisolated enum LiveBlendBuffer {
    /// Bounded, because the page this feeds is one a reader leaves open for a
    /// whole match. At the publisher's cadence this is several hours of frames;
    /// the cap exists so "several" can never become "unbounded" on a page nobody
    /// closed, not because any real match is expected to reach it.
    static let capacity = 720

    /// Append a frame, keeping the buffer time-ordered and bounded.
    ///
    /// A frame that is not STRICTLY newer than the last one held is dropped. The
    /// stream replays its most recent frame on reconnect, and a duplicate stamp
    /// admitted here would draw a second point on top of the first — visible as
    /// a kink in a line that should be straight, and counted twice by anything
    /// that measures the buffer.
    static func appending(_ point: LiveBlendPoint, to buffer: [LiveBlendPoint]) -> [LiveBlendPoint] {
        if let last = buffer.last, point.date <= last.date { return buffer }
        var next = buffer
        next.append(point)
        if next.count > capacity { next.removeFirst(next.count - capacity) }
        return next
    }
}

// MARK: - Which payload is fresher

nonisolated enum EventHistoryFreshness {
    /// The most recent moment this payload holds a probability reading for —
    /// its live edge, across every series the match chart can draw.
    ///
    /// All four are folded in rather than just the blend, because any one of
    /// them advancing moves a line the reader is looking at. A payload whose
    /// edge has not moved but whose middle has been backfilled reads as
    /// unchanged here; that is deliberate and it is the cheap direction to be
    /// wrong in, since the backfilled points are already behind the edge and the
    /// next poll that does advance the edge brings them along.
    static func lastReading(in history: EventHistoryResponse) -> Date? {
        var latest: Date?
        func offer(_ stamp: String) {
            guard let date = stamp.asDate else { return }
            if let current = latest, current >= date { return }
            latest = date
        }

        for point in history.aggregateLine ?? [] { offer(point.timestamp) }
        for point in history.history { offer(point.timestamp) }
        for point in history.espnHistory ?? [] { offer(point.timestamp) }
        for series in (history.winProbHistory ?? [:]).values {
            for point in series { offer(point.timestamp) }
        }
        return latest
    }

    /// Whether `fresh` may replace `current` on screen.
    ///
    /// Monotonic at the edge: a payload whose live edge is BEHIND the one drawn
    /// never replaces it. Two fetches are in flight against this chart — the
    /// page's 120 s poll and the chart's own one-shot `load()` — and the slower
    /// one can land second while carrying older data. Without this, the chart
    /// would visibly step backwards, which is worse than the freeze it replaces.
    ///
    /// A payload with no readings at all never wins, so an empty or errored
    /// refresh cannot blank a chart that is drawing.
    static func shouldAdopt(_ fresh: EventHistoryResponse, over current: EventHistoryResponse?) -> Bool {
        guard let current else { return true }
        guard let freshEdge = lastReading(in: fresh) else { return false }
        guard let currentEdge = lastReading(in: current) else { return true }
        return freshEdge >= currentEdge
    }
}
