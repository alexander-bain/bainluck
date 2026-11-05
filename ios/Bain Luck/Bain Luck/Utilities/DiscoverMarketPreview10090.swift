import Foundation

/// #10090 — a held market's venue move at arrival on a Discover futures card
/// (`backend/app/utils/market_preview.py`). The iPhone twin of web's
/// `frontend/lib/discover/marketPreview.ts`; the rules are the same.
///
/// A `market_preview` frame is PROVISIONAL: it is overlaid on the cards the
/// screen draws, never written into the committed card store. A leg's preview
/// shows only while (a) its ttl has not run out, (b) its `observed_at` is newer
/// than the card's committed observation for that leg — so the committed
/// re-read with an equal or newer observation replaces it — and (c) the card
/// prints raw prices (`displayScale == 1`). Frames are fenced by the
/// publisher's per-market `seq`; a reconnect or an out-of-view card drops the
/// market's state.
nonisolated struct DiscoverMarketPreviewFrame: Sendable, Equatable {
    struct Outcome: Sendable, Equatable {
        let outcomeId: Int
        let p: Double
        let observedAt: String
    }
    let marketId: Int
    let source: String
    let outcomes: [Outcome]
    let seq: Int
    let ttlMs: Int
}

nonisolated struct DiscoverMarketPreviewLeg: Sendable, Equatable {
    let p: Double
    let observedAt: String
    /// On the owner's monotonic clock: after this the leg is not shown.
    let expiresAt: TimeInterval
}

nonisolated struct DiscoverMarketPreviewState: Sendable, Equatable {
    let source: String
    let seq: Int
    let legs: [String: DiscoverMarketPreviewLeg]
}

nonisolated enum DiscoverMarketPreview {
    /// The producer's ceiling (`MAX_PREVIEW_TTL_MS`); a longer lifetime is refused.
    static let maxTTLMs = 60_000

    /// A positive integer a JSON number carries exactly (web's `Number.isSafeInteger`).
    private static func positive(_ value: Any?) -> Int? {
        guard let number = value as? NSNumber, CFGetTypeID(number) != CFBooleanGetTypeID() else { return nil }
        let double = number.doubleValue
        guard double.isFinite, double.rounded() == double, double > 0,
              double <= Double(FoldRevision.maxSafeInteger) else { return nil }
        return number.int64Value <= Int64(FoldRevision.maxSafeInteger) ? Int(number.int64Value) : nil
    }

    /// A well-formed frame from the SSE event's data, else nil. Never throws.
    static func parse(_ raw: String) -> DiscoverMarketPreviewFrame? {
        guard let data = raw.data(using: .utf8),
              let frame = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any],
              frame["type"] as? String == "market_preview",
              let flag = frame["preview"] as? NSNumber, CFGetTypeID(flag) == CFBooleanGetTypeID(), flag.boolValue,
              let marketId = positive(frame["market_id"]), let seq = positive(frame["seq"]),
              let source = frame["source"] as? String,
              let ttl = positive(frame["ttl_ms"]), ttl <= maxTTLMs,
              let rows = frame["outcomes"] as? [Any], !rows.isEmpty else { return nil }
        var outcomes: [DiscoverMarketPreviewFrame.Outcome] = []
        for raw in rows {
            guard let row = raw as? [String: Any], let outcomeId = positive(row["outcome_id"]),
                  let number = row["p"] as? NSNumber, CFGetTypeID(number) != CFBooleanGetTypeID(),
                  number.doubleValue > 0, number.doubleValue < 1,
                  let observedAt = row["observed_at"] as? String,
                  DiscoverPriceRefresh.observation(observedAt) != nil else { return nil }
            outcomes.append(.init(outcomeId: outcomeId, p: number.doubleValue, observedAt: observedAt))
        }
        return DiscoverMarketPreviewFrame(marketId: marketId, source: source, outcomes: outcomes, seq: seq, ttlMs: ttl)
    }

    /// Admit a frame received at `receivedAt` (monotonic seconds). Returns
    /// `states` unchanged when refused: a lower or equal `seq` from the same source.
    static func apply(_ states: [Int: DiscoverMarketPreviewState], _ frame: DiscoverMarketPreviewFrame,
                      receivedAt: TimeInterval) -> [Int: DiscoverMarketPreviewState] {
        let prior = states[frame.marketId]
        if let prior, prior.source == frame.source, frame.seq <= prior.seq { return states }
        var legs: [String: DiscoverMarketPreviewLeg] = [:]
        if let prior, prior.source == frame.source {
            for (id, leg) in prior.legs where leg.expiresAt > receivedAt { legs[id] = leg }
        }
        let expiresAt = receivedAt + Double(frame.ttlMs) / 1000
        for row in frame.outcomes {
            legs[String(row.outcomeId)] = .init(p: row.p, observedAt: row.observedAt, expiresAt: expiresAt)
        }
        var next = states
        next[frame.marketId] = .init(source: frame.source, seq: frame.seq, legs: legs)
        return next
    }

    /// Drop these markets' previews (a reconnect, or the card left view).
    static func drop(_ states: [Int: DiscoverMarketPreviewState], _ ids: some Sequence<Int>) -> [Int: DiscoverMarketPreviewState] {
        var next = states
        for id in ids { next.removeValue(forKey: id) }
        return next
    }

    /// The soonest leg expiry after `now`, or nil.
    static func nextExpiry(_ states: [Int: DiscoverMarketPreviewState], after now: TimeInterval) -> TimeInterval? {
        states.values.flatMap { $0.legs.values.map(\.expiresAt) }.filter { $0 > now }.min()
    }

    /// `1 - p` on the venues' decimal grid (bare `1 - 0.445` is 0.5549999…).
    static func complement(_ p: Double) -> Double { (1000 - p * 1000) / 1000 }

    /// `market` with the admitted legs of `state` overlaid, or nil when no leg
    /// is admitted — so a card with no preview renders exactly as committed.
    static func overlay(_ market: FeedFuturesData, _ state: DiscoverMarketPreviewState,
                        now: TimeInterval) -> FeedFuturesData? {
        guard market.fullFieldRendered != true, market.displayScale == 1, market.source == state.source,
              !DiscoverPriceRefresh.marketIsResolved(market) else { return nil }
        // A raw scalar has no complete field or server allocation. Keep the
        // committed shared numbers until the existing API refresh supplies them.
        guard !(market.discoverCard?.distributionOutcomes ?? []).contains(where: {
            $0.renderedPercent != nil
        }) else { return nil }
        let rows = market.topOutcomes ?? []
        let admitted: [Double?] = rows.map { row in
            let key = String(row.id)
            // A withheld (nil) price stays withheld: the server refused it on purpose.
            guard let leg = state.legs[key], leg.expiresAt > now,
                  let committed = row.probability, committed != leg.p else { return nil }
            let clock = (market.outcomeObservedAt?[key] ?? nil) ?? row.priceObservedAt
            if let clock, !clock.isEmpty {
                // An undatable committed clock orders nothing, so it is not beaten.
                guard let held = DiscoverPriceRefresh.observation(clock),
                      let incoming = DiscoverPriceRefresh.observation(leg.observedAt),
                      incoming > held else { return nil }
            }
            return leg.p
        }
        guard admitted.contains(where: { $0 != nil }) else { return nil }

        func leg(_ row: FeedFuturesOutcome, _ p: Double) -> FeedFuturesOutcome {
            FeedFuturesOutcome(id: row.id, name: row.name, probability: p, rank: row.rank,
                               movement: row.movement, priceObservedAt: row.priceObservedAt)
        }
        var shown = market
        // A committed complement pair prints a total of 100 (#2060), and so must
        // its preview: a one-sided move carries its complement to the other leg,
        // and two previewed legs that are not a pair keep the committed pair. The
        // card's own `renderedCardPercents` then prints the new pair.
        if isComplementPair(rows.map(\.probability)) {
            let pair: (Double, Double)
            if let first = admitted[0], let second = admitted[1] {
                guard isComplementPair([first, second]) else { return nil }
                pair = (first, second)
            } else if let first = admitted[0] {
                pair = (first, complement(first))
            } else if let second = admitted[1] {
                pair = (complement(second), second)
            } else {
                return nil
            }
            shown.topOutcomes = [leg(rows[0], pair.0), leg(rows[1], pair.1)]
            return shown
        }
        // Any other card: each previewed leg on its own.
        shown.topOutcomes = zip(rows, admitted).map { row, p in p.map { leg(row, $0) } ?? row }
        return shown
    }
}
