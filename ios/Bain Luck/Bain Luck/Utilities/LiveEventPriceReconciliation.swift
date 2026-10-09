import Foundation

/// #920: keep a newer pushed price over an older REST response while adopting
/// the REST score/status/metadata. Compare source write clocks, never response
/// arrival or sportsbook capture time. Unknown clocks leave REST authoritative.
nonisolated enum LiveEventPriceReconciliation {
    static func newestSourceDate(in event: EventDetail) -> Date? {
        // This one key is numeric metadata, not a probability source. Unknown
        // future source keys participate rather than silently proving freshness
        // from only the subset this client happens to recognize.
        let sources = (event.winProbabilitySources ?? [:]).filter { $0.key != "betting_book_count" }
        guard !sources.isEmpty else { return nil }
        let dates = sources.values.compactMap { $0.updatedAt?.asDate }
        guard dates.count == sources.count else { return nil }
        return dates.max()
    }

    /// Protect only a recognizable pre-game cache lease. Price clocks alone
    /// cannot overrule a reschedule, an unknown lifecycle, or a changed start.
    static func preservingLiveStatus(
        _ frame: LiveStreamFrame?, current: EventDetail?, polled: EventDetail,
        streamRecoverable: Bool, now: Date
    ) -> EventDetail {
        guard polled.status == "scheduled", current?.status == "live",
              current?.id == polled.id, frame?.status == "live",
              let oldStart = current?.commenceTime?.asDate,
              let newStart = polled.commenceTime?.asDate,
              oldStart == newStart, newStart <= now else { return polled }
        var candidate = polled
        candidate.status = "live"
        // Changing status does not waive any source, price or clock guard.
        return shouldPreserve(frame, over: candidate, streamRecoverable: streamRecoverable)
            ? candidate : polled
    }

    /// #9051 — the page is showing the server's live blend: a live event whose
    /// hero resolved to `"blend"` and whose printed number IS that hero. Only
    /// then does `blendFoldRevision` date what the reader sees.
    static func holdsLiveBlend(_ event: EventDetail) -> Bool {
        guard EventPriceStreaming.isEligible(event.status), event.heroProbabilitySource == "blend",
              let hero = event.heroProbability, hero.isFinite,
              let shown = event.currentOdds?.homeProbability else { return false }
        return shown == hero
    }

    /// #9051 — the fold revision of the number on screen, or `nil` (no claim):
    /// no live blend, or no well-formed vector. A revision is never read off a
    /// payload whose printed number is some other value (an opening line, a
    /// sportsbook consensus): it would date a number the page is not showing.
    static func pairedFoldRevision(in event: EventDetail) -> FoldRevision? {
        holdsLiveBlend(event) ? event.blendFoldRevision?.revision : nil
    }

    /// #9051 — a completed poll against the headline the page ALREADY accepted
    /// (web's `keepNewerHeldHeadline`).
    ///
    /// Frames move the held headline between polls, and `latestPriceFrame`
    /// holds only the latest one. So the poll is compared with the page itself:
    /// a response whose fold revision is strictly OLDER — or which carries none
    /// against a held one, since a value is never tagged with a revision
    /// borrowed from another value — keeps the held headline, its sources, clock
    /// and revision, and takes everything else (score, status, metadata) from
    /// the response. A newer, equal or incomparable response is the
    /// authoritative read and wins whole; that is how a changed fold is adopted.
    /// A response that ends the game or leaves the live blend wins whole, and a
    /// page holding no revision takes every response as before.
    static func keepingNewerHeldHeadline(_ polled: EventDetail, held: EventDetail?) -> EventDetail {
        guard let held, held.id == polled.id,
              let heldRevision = pairedFoldRevision(in: held),
              EventPriceStreaming.isEligible(polled.status), polled.heroProbabilitySource == "blend",
              let polledHero = polled.heroProbability, polledHero.isFinite else { return polled }
        if let polledRevision = pairedFoldRevision(in: polled),
           FoldRevision.compare(polledRevision, heldRevision) != .older { return polled }
        var kept = polled
        if var odds = kept.currentOdds, let heldOdds = held.currentOdds {
            odds.homeProbability = heldOdds.homeProbability
            // A withheld away side (#6238, draw-priced sports) stays withheld.
            odds.awayProbability = odds.awayProbability == nil ? nil : heldOdds.awayProbability
            odds.homeRenderedPercent = heldOdds.homeRenderedPercent
            odds.awayRenderedPercent = heldOdds.awayRenderedPercent
            kept.currentOdds = odds
        } else {
            kept.currentOdds = held.currentOdds
        }
        kept.heroProbability = held.heroProbability
        kept.heroProbabilityAway = held.heroProbabilityAway
        kept.heroProbabilityObservedAt = held.heroProbabilityObservedAt
        kept.winProbabilitySources = held.winProbabilitySources
        kept.blendFoldRevision = held.blendFoldRevision
        return kept
    }

    /// #10090 — what a held folded blend does with a frame that speaks for the
    /// server's FULL fold (or promises to). Web's `adoptFoldedQuote`.
    enum FoldedQuoteDecision: Equatable {
        /// A newer full vector: replace hero, pair, clock, vector and rail.
        case adopt(FoldedQuote)
        /// The same or an older fold than the page shows: nothing to do.
        case hold
        /// A raw frame on a multirow fold whose authoritative answer follows.
        /// No detail/history read — the result frame settles it.
        case awaitResult
        /// Not this path's to decide: the existing frame rules apply, including
        /// the detail/history read a folded hero asks for.
        case fallback
    }

    /// Only a page already showing a live server blend with a vector can be
    /// moved by a quote. An opening/consensus label, a phase change, a sport
    /// or event mismatch, a non-blend hero and different fold membership
    /// (`incomparable`) keep the authoritative paired read.
    static func foldedQuoteDecision(_ frame: LiveStreamFrame, held: EventDetail) -> FoldedQuoteDecision {
        guard frame.eventId == held.id, let heldRevision = pairedFoldRevision(in: held) else { return .fallback }
        guard frame.foldedResult else {
            // Only the raw PROMISE defers. An absent status is no claim (a
            // sibling's invalidation carries none); a different one is a phase
            // change and keeps its read.
            guard frame.foldedQuotePending == true, heldRevision.rows.count > 1,
                  frame.status == nil || frame.status == held.status else { return .fallback }
            return .awaitResult
        }
        // Explicit null or a refused quote: the existing fallback, never a
        // second deferral.
        guard let quote = frame.foldedQuote?.quote, quote.eventId == held.id,
              quote.heroProbabilitySource == "blend", quote.heroProbability != nil,
              quote.status == held.status, quote.sport == held.sport else { return .fallback }
        switch FoldRevision.compare(quote.blendFoldRevision, heldRevision) {
        case .newer: return .adopt(quote)
        case .same, .older: return .hold
        case .incomparable: return .fallback
        }
    }

    /// #10090 — the quote, exactly as served. The full vector dates the whole
    /// quote, so an older clock after a removal still lands, and the complete
    /// rail replaces the held one: a removed source never survives. The away
    /// side is the server's (`nil` on a draw-priced sport), never `1 - p`.
    /// Score, clock, status and everything else stay as held.
    static func adoptingFoldedQuote(_ quote: FoldedQuote, into event: inout EventDetail) {
        guard let hero = quote.heroProbability else { return }
        if var odds = event.currentOdds {
            odds.homeProbability = hero
            odds.awayProbability = quote.heroProbabilityAway
            // The served whole percents described the previous pair.
            odds.homeRenderedPercent = nil
            odds.awayRenderedPercent = nil
            event.currentOdds = odds
        }
        event.heroProbability = hero
        event.heroProbabilityAway = quote.heroProbabilityAway
        event.heroProbabilityObservedAt = quote.heroProbabilityObservedAt
        event.blendFoldRevision = ServedFoldRevision(quote.blendFoldRevision)
        event.winProbabilitySources = quote.winProbabilitySources
    }

    static func shouldPreserve(_ frame: LiveStreamFrame?, over polled: EventDetail, streamRecoverable: Bool) -> Bool {
        guard streamRecoverable, let frame, frame.eventId == polled.id,
              EventPriceStreaming.isEligible(polled.status),
              let p = frame.p, p.isFinite, (0...1).contains(p),
              let served = polled.currentOdds?.homeProbability, served.isFinite else { return false }
        // #9051: when the response's blend carries its fold revision, commit
        // order decides BEFORE any clock or source-presence rule. A frame from
        // before a source removal still folds the removed source into its `p`,
        // and the surviving quote that dates the fresh blend can be OLDER than
        // that frame — the clocks below kept a stale 60% over a fresh 40%.
        if let order = FoldRevision.frameOrder(
            held: pairedFoldRevision(in: polled), frame: frame.rev?.revision
        ) {
            return order == .newer
        }
        guard let source = frame.source,
              polled.winProbabilitySources?[source] != nil,
              let pushedAt = frame.updatedAt?.asDate,
              let newest = newestSourceDate(in: polled) else { return false }
        // Any equally/newer source may advance the aggregate, including a
        // different venue. Removed/refused sources and withheld prices above
        // must never be resurrected by a previously received frame.
        return newest < pushedAt
    }

    static func applying(_ frame: LiveStreamFrame?, to polled: EventDetail, streamRecoverable: Bool) -> EventDetail {
        guard shouldPreserve(frame, over: polled, streamRecoverable: streamRecoverable),
              let frame, let p = frame.p, var odds = polled.currentOdds else { return polled }
        odds.homeProbability = p
        odds.awayProbability = 1 - p
        odds.homeRenderedPercent = nil
        odds.awayRenderedPercent = nil
        var reconciled = polled
        reconciled.currentOdds = odds
        adoptFrameProvenance(frame, into: &reconciled)
        return reconciled
    }

    /// #9051 — the hero now prints this frame's `p`, so its clock and revision
    /// are the frame's too: the frame's own revision, or none. Never the held
    /// one — that dated the value this frame replaced.
    static func adoptFrameProvenance(_ frame: LiveStreamFrame, into event: inout EventDetail) {
        event.heroProbability = frame.p
        event.heroProbabilityObservedAt = frame.updatedAt
        if frame.rev?.revision != nil || event.blendFoldRevision?.revision != nil {
            event.blendFoldRevision = ServedFoldRevision(frame.rev?.revision)
        }
    }

    /// #9051 — web's `chartRevisionRefreshKey`. A removal can advance the fold
    /// while leaving only an OLDER surviving quote, so the chart's right edge can
    /// still end on the pre-removal blend after the headline has moved. When the
    /// held revision is newer than (or incomparable with) the one the history's
    /// pinned edge was computed from, and the line the chart draws does not end
    /// on the headline, the page asks for history again. Returns a stable key
    /// (the held vector) so it asks once per accepted fold; an unchanged cached
    /// response cannot loop, and the ordinary poll stays the retry.
    static func chartRevisionRefreshKey(
        event: EventDetail?, history: EventHistoryResponse?, liveBlend: [LiveBlendPoint]
    ) -> String? {
        guard let event, let history, history.blendEdgePinned == true,
              let heldRevision = pairedFoldRevision(in: event),
              let servedRevision = history.blendEdgeFoldRevision?.revision,
              let hero = event.currentOdds?.homeProbability, (0...1).contains(hero) else { return nil }
        let order = FoldRevision.compare(heldRevision, servedRevision)
        guard order == .newer || order == .incomparable else { return nil }
        let served = (history.aggregateLine ?? []).compactMap { point in
            point.timestamp.asDate.map { (date: $0, p: point.homeProbability) }
        }
        guard let publishedEdge = served.max(by: { $0.date < $1.date }) else { return nil }
        // The chart draws the served line carried forward by the pushed frames
        // past its edge (`OddsChartView.extendingBlendToLiveEdge`).
        let drawnEdge = liveBlend.filter { $0.date > publishedEdge.date }
            .max(by: { $0.date < $1.date })
            .map { (date: $0.date, p: $0.homeProbability) } ?? publishedEdge
        guard drawnEdge.p != hero else { return nil }
        return heldRevision.rows.sorted { $0.key < $1.key }
            .map { "\($0.key):\($0.value)" }.joined(separator: ",")
    }
}
