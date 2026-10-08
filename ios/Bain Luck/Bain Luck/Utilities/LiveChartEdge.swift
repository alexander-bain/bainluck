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
///
/// `admission` (#10753) is the proof the frame was adopted on this game by
/// commit order while the game was still on. Nil for every caller that has no
/// such proof, and a nil point keeps exactly its live behaviour — it simply
/// earns no place on a finished chart.
nonisolated struct LiveBlendPoint: Sendable, Equatable {
    let date: Date
    let homeProbability: Double
    let source: String?
    let sourceProbability: Double?
    let admission: LiveBlendAdmission?

    init(date: Date, homeProbability: Double,
         source: String? = nil, sourceProbability: Double? = nil,
         admission: LiveBlendAdmission? = nil) {
        self.date = date
        self.homeProbability = homeProbability
        self.admission = admission
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

/// #10753 — why a pushed blend may outlive the finish on the chart that drew it.
///
/// A frame earns this only on the page's ordinary revised-price branch: the page
/// held a live blend folded from ONE row (`held`), and the frame wrote that same
/// row strictly later (`frame`). Nothing here is minted — both vectors are the
/// producer's own — and a frame whose status says the game is over earns none,
/// because a terminal frame is not a pre-finish observation.
nonisolated struct LiveBlendAdmission: Sendable, Equatable {
    let eventId: Int
    let held: FoldRevision
    let frame: FoldRevision

    init?(eventId: Int, held: FoldRevision?, frame: FoldRevision?, frameStatus: String?) {
        guard let held, let frame,
              FoldRevision.frameOrder(held: held, frame: frame) == .newer,
              frameStatus.map(EventPriceStreaming.isEligible) ?? true else { return nil }
        self.eventId = eventId
        self.held = held
        self.frame = frame
    }
}

/// #10753 — a finished game's detail fold vector, raw, with the game it belongs to.
///
/// The detail serves `blend_fold_revision` on a finished game too, as the
/// revision of the source rows it folded — NOT of the settled hero, the game end
/// or the final history (#10753, Root qualification 17055). So it is read raw,
/// never through `pairedFoldRevision` (which refuses a settled hero), and it is
/// used for one question only: has every retained frame's row been written no
/// later than what the finished detail read?
nonisolated struct FinishedSourceFold: Sendable, Equatable {
    let eventId: Int
    let revision: FoldRevision

    init?(eventId: Int, status: String?, revision: FoldRevision?) {
        guard EventState.isFinished(status), let revision else { return nil }
        self.eventId = eventId
        self.revision = revision
    }
}

/// #10753 — the pushed movement a reader already saw, kept across the finish.
///
/// A page left open through the end of a game draws pushed blends past the
/// served aggregate. The finished history that follows can land before the
/// server's blend includes them, and the finished payload is never extended
/// (settled means settled) — so the movement the reader watched vanished. These
/// rules keep exactly the part that was proved and drawn, and nothing else.
nonisolated enum DrawnBlendRetention {
    /// Record the admitted frames a PRE-FINISH chart just drew past its served
    /// blend edge. Only frames proved on this game count; ordered and bounded
    /// like the buffer they came from.
    static func recording(
        drawn liveFrames: [LiveBlendPoint], servedEdge: Date?, eventId: Int,
        into snapshot: [LiveBlendPoint]
    ) -> [LiveBlendPoint] {
        guard let servedEdge else { return snapshot }
        var next = snapshot
        for frame in liveFrames where frame.date > servedEdge && frame.admission?.eventId == eventId {
            next = LiveBlendBuffer.appending(frame, to: next)
        }
        return next
    }

    /// The recorded points a FINISHED chart may still draw.
    ///
    /// All or nothing on the proof: every point must be admitted on this game
    /// and the finished detail's vector must be the same one row, equal to or
    /// newer than each point's frame and its held context. Anything else —
    /// changed rows, mixed directions, an older or missing finished vector, a
    /// different game — retains nothing. Then each point must still be past the
    /// served blend (an exact served time or later coverage retires it) and no
    /// later than the game's end. No end, no served blend: nothing.
    static func retained(
        _ snapshot: [LiveBlendPoint], eventId: Int, finished: FinishedSourceFold?,
        servedEdge: Date?, gameEnd: Date?
    ) -> [LiveBlendPoint] {
        guard !snapshot.isEmpty, let finished, finished.eventId == eventId,
              let servedEdge, let gameEnd else { return [] }
        func covers(_ revision: FoldRevision) -> Bool {
            let order = FoldRevision.compare(finished.revision, revision)
            return order == .newer || order == .same
        }
        for point in snapshot {
            guard let admission = point.admission, admission.eventId == eventId,
                  covers(admission.frame), covers(admission.held) else { return [] }
        }
        return snapshot.filter { $0.date > servedEdge && $0.date <= gameEnd }
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
    /// `EventHistoryFreshness.lastReading(in:)` of the payload.
    let edge: Date?
    /// The latest win-probability reading across every source. Sources are
    /// walked in name order and a tie keeps the first, so a tie on the latest
    /// time resolves the same way on every open (#8509) — the same reading the
    /// page's `max(by:)` over the name-sorted series picked.
    let latestWinProb: WinProbHistoryPoint?

    init(_ history: EventHistoryResponse) {
        edge = EventHistoryFreshness.lastReading(in: history)
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
