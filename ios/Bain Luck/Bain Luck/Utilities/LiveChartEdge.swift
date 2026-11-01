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
///
/// `source`/`sourceProbability` are the OTHER number a frame carries — the venue
/// reading behind the blend, the same value the backend persists into
/// `win_prob_history[<source>][].home_probability`. They never reach the blend
/// line. They exist for one place only: a single-source page, where the backend
/// published no blend and that venue's own series is the line the reader reads
/// (`OddsChartView.extendingServedSourceSeries`, #836/#837/#920). Held on the
/// same validity bar as the blend — a named source and a finite probability —
/// or not at all; a frame without one is still a perfectly good blend reading.
nonisolated struct LiveBlendPoint: Sendable, Equatable {
    let date: Date
    let homeProbability: Double
    let source: String?
    let sourceProbability: Double?
    /// Disposable projection authority; never placed in the committed buffer.
    let previewAuthority: BlendPreviewChartAuthority?
    /// #10090 — the committed headline's authority to re-value an OLDER pinned
    /// edge (`BlendPreview.olderPinUnderHeadline`). A render marker, never drawn
    /// as a point and never placed in the committed buffer.
    let headlineOverPin: BlendPreviewChartAuthority?

    init(date: Date, homeProbability: Double,
         source: String? = nil, sourceProbability: Double? = nil,
         previewAuthority: BlendPreviewChartAuthority? = nil,
         headlineOverPin: BlendPreviewChartAuthority? = nil) {
        self.date = date
        self.homeProbability = homeProbability
        self.previewAuthority = previewAuthority
        self.headlineOverPin = headlineOverPin
        if let source, !source.isEmpty,
           let value = sourceProbability, value.isFinite, (0...1).contains(value) {
            self.source = source
            self.sourceProbability = value
        } else {
            self.source = nil
            self.sourceProbability = nil
        }
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
    ///
    /// A value that is not a probability is dropped too, which the hero path has
    /// never needed to care about and a chart must. `web`'s twin
    /// (`frontend/lib/liveChartHistory.ts`) makes the same check for the same
    /// reason: a `NaN` reaching a plot does not print a wrong number, it takes
    /// the axis with it and blanks the frame — a bad frame must cost its own
    /// point and nothing else.
    static func appending(_ point: LiveBlendPoint, to buffer: [LiveBlendPoint]) -> [LiveBlendPoint] {
        guard point.homeProbability.isFinite, (0...1).contains(point.homeProbability) else {
            return buffer
        }
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
        EventHistoryEdges(history).latest
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
    ///
    /// One exception, `adoptsSourceRemoval`: a complete fresh build that drops
    /// a series the drawn payload holds.
    static func shouldAdopt(_ fresh: EventHistoryResponse, over current: EventHistoryResponse?) -> Bool {
        shouldAdopt(EventHistoryEdges(fresh), over: current.map(EventHistoryEdges.init))
    }

    /// The same rule over edges already read (`EventHistoryDigest.edges`).
    /// `nil` is "nothing held".
    static func shouldAdopt(_ fresh: EventHistoryEdges, over current: EventHistoryEdges?) -> Bool {
        guard let current else { return true }
        return shouldAdopt(freshEdge: fresh.latest, over: .some(current.latest))
            || adoptsSourceRemoval(fresh, over: current)
    }

    /// #10090 §3 — a withdrawn source whose series held the drawn payload's
    /// latest reading kept every later payload behind that edge, so the chart
    /// went on drawing the withdrawn line until another series passed its
    /// last stamp (on a sparse pre-match chart, possibly never), and the
    /// reconcile floor stayed owed against a payload it could not show.
    ///
    /// A payload missing a held series is taken here only when it is provably
    /// not older:
    ///   - It is a COMPLETE fresh build: it carries `history_fold_revision`,
    ///     which the producer serves only on a complete fresh build. A
    ///     cacheable, partial or doubtful build makes no membership claim, so a
    ///     series absent from it proves nothing.
    ///   - It is unpinned. A pinned edge is a claim about now and is never
    ///     rescued here.
    ///   - It is the same event.
    ///   - No series both payloads hold is behind the drawn one. Every
    ///     retained endpoint stays where it is or moves forward.
    ///   - If the drawn payload also carries a complete-build revision, the
    ///     fresh one read later on the rows both carry: at or past it on every
    ///     row and past it on at least one.
    /// It never makes a point, a stamp or a clock. The withdrawn series is
    /// simply the one the later complete build does not have.
    static func adoptsSourceRemoval(_ fresh: EventHistoryEdges, over held: EventHistoryEdges) -> Bool {
        guard fresh.eventId == held.eventId, !fresh.pinned,
              let freshRead = fresh.completeRead else { return false }
        let retained = held.series.keys.filter { fresh.series[$0] != nil }
        guard !retained.isEmpty, retained.count < held.series.count,
              retained.allSatisfy({ fresh.series[$0]! >= held.series[$0]! }) else { return false }
        guard let heldRead = held.completeRead else { return true }
        let rows = heldRead.rows.keys.filter { freshRead.rows[$0] != nil }
        return !rows.isEmpty
            && rows.allSatisfy { freshRead.rows[$0]! >= heldRead.rows[$0]! }
            && rows.contains { freshRead.rows[$0]! > heldRead.rows[$0]! }
    }

    /// The same rule over edges already read (`EventHistoryDigest.edge`). The
    /// outer `nil` of `current` is "nothing held"; an inner `nil` is a held
    /// payload with no readings.
    static func shouldAdopt(freshEdge: Date?, over current: Date??) -> Bool {
        guard let current else { return true }
        guard let freshEdge else { return false }
        guard let currentEdge = current else { return true }
        return freshEdge >= currentEdge
    }
}

/// What the adoption rule reads off one payload: the latest reading of each
/// series the match chart can draw, and the two producer claims
/// `adoptsSourceRemoval` needs.
nonisolated struct EventHistoryEdges: Sendable, Equatable {
    let eventId: Int
    /// The latest parseable stamp per series: `aggregate`, `odds`, `espn` and
    /// `wp:<source>`. A series with no parseable stamp is absent.
    let series: [String: Date]
    /// `history_fold_revision`: the producer's complete-build read order.
    /// `nil` is no claim.
    let completeRead: FoldRevision?
    let pinned: Bool

    /// `EventHistoryFreshness.lastReading(in:)`.
    var latest: Date? { series.values.max() }

    init(_ history: EventHistoryResponse) {
        var series: [String: Date] = [:]
        func offer(_ key: String, _ stamps: some Sequence<String>) {
            var latest: Date?
            for stamp in stamps {
                guard let date = stamp.asDate else { continue }
                if let current = latest, current >= date { continue }
                latest = date
            }
            if let latest { series[key] = latest }
        }
        offer("aggregate", (history.aggregateLine ?? []).lazy.map(\.timestamp))
        offer("odds", history.history.lazy.map(\.timestamp))
        offer("espn", (history.espnHistory ?? []).lazy.map(\.timestamp))
        for (source, points) in history.winProbHistory ?? [:] {
            offer("wp:" + source, points.lazy.map(\.timestamp))
        }
        self.eventId = history.eventId
        self.series = series
        self.completeRead = history.historyFoldRevision?.revision
        self.pinned = history.blendEdgePinned == true
    }
}

// MARK: - Read once per payload, not once per page

/// #8651 — what the event page reads off a history payload, read ONCE when the
/// payload arrives instead of on every page rebuild.
///
/// Build 34 on Alex's phone (Steelers–Browns 14780550, Oct 1): a game page left
/// open "got very, very choppy to the point where the app became unusable".
/// Measured on build 34's own source in a Release simulator build: every update
/// the page takes in — a game-markets reread (as often as every 2 s, the
/// delivery's budget, when a game's markets keep moving), a pushed price, a
/// re-polled history — rebuilt the page, and the page body
/// re-parsed every timestamp in the history twice: `lastReading(in:)` for the
/// chart's live edge (~9,500 stamps on that game) and the latest
/// win-probability reading for the chart's readout, whose `max(by:)` parsed both
/// sides of every comparison (~4,400 readings). ~600 ms of a ~860 ms main-thread
/// freeze per update, measured in a simulator on a Mac. Both scans grow with
/// the game's history. Neither depends on anything but the payload, so the page holds them here.
nonisolated struct EventHistoryDigest {
    /// The adoption rule's read of the payload (`EventHistoryFreshness`).
    let edges: EventHistoryEdges
    /// `EventHistoryFreshness.lastReading(in:)` of the payload.
    var edge: Date? { edges.latest }
    /// The latest win-probability reading across every source. Sources are
    /// walked in name order and a tie keeps the first, so a tie on the latest
    /// time resolves the same way on every open (#8509) — the same reading the
    /// page's `max(by:)` over the name-sorted series picked.
    let latestWinProb: WinProbHistoryPoint?

    init(_ history: EventHistoryResponse) {
        edges = EventHistoryEdges(history)
        latestWinProb = Self.latestWinProb(in: history)
    }

    /// Each stamp is parsed once. An unparseable stamp sorts as the distant
    /// past, as it did in the comparator this replaces.
    static func latestWinProb(in history: EventHistoryResponse) -> WinProbHistoryPoint? {
        guard let series = history.winProbHistory else { return nil }
        var latest: (point: WinProbHistoryPoint, at: Date)?
        for (_, points) in series.sorted(by: { $0.key < $1.key }) {
            for point in points {
                let at = point.timestamp.asDate ?? .distantPast
                if let current = latest, current.at >= at { continue }
                latest = (point, at)
            }
        }
        return latest?.point
    }
}
