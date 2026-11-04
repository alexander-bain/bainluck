import Foundation

/// #10090 — one Discover game card's v3 preview reader, driven by the same
/// readers, in the same order, as the event page (`EventDetailViewModel`):
/// `readerAfterMembership` from the card's adopted revision, `readerOpenedV3`,
/// `readerAfterV3`, `readerAfterCommitFloor` and `heldAcrossCommitFloor`,
/// `readerReset`. The web twin is `useDiscoverPriceStream`.
///
/// Nothing here is ever written into the committed card store: the shown
/// preview is laid over a copy of the card when it is drawn
/// (`DiscoverCardPreviews.overlay`), behind the event page's own display gate
/// (`BlendPreview.displayed`), so a committed read with a newer revision wins.
nonisolated struct DiscoverEventPreview: Sendable, Equatable {
    var reader = BlendPreviewReader.empty
    /// The folded preview a commit floor withdrew that the card keeps until
    /// the commit's own read lands (`BlendPreview.heldAcrossCommitFloor`).
    var handover: BlendPreviewState?

    var shown: BlendPreviewState? { reader.held ?? handover }

    /// The card's adopted revision is the reader's sole membership authority.
    /// `reopens` asks the owner to close and reopen the stream, whose v3 open
    /// is bound to the membership it was opened with (`membershipReopens`).
    mutating func adoptMembership(of card: FeedEventData?) -> Bool {
        guard let card, let revision = BlendPreviewCommitted(card).revision else { return false }
        let members = Set(revision.rows.keys)
        let reopens = BlendPreview.membershipReopens(reader, members: members)
        reader = BlendPreview.readerAfterMembership(reader, members: members)
        if reopens { handover = nil }
        return reopens
    }

    /// A `preview_open_v3`.
    mutating func open(_ raw: String, eventId: Int) {
        guard let open = PreviewEnvelopeV3.decode(raw, kind: .open, eventId: eventId) else { return }
        let next = BlendPreview.readerOpenedV3(reader, open)
        guard next != reader else { return }
        if next.held == nil { handover = nil }
        reader = next
    }

    /// A `preview_v3`, dated at its receipt (`now` already less the wait).
    mutating func preview(_ raw: String, eventId: Int, now: TimeInterval) {
        guard let envelope = PreviewEnvelopeV3.decode(raw, kind: .preview, eventId: eventId) else { return }
        let next = BlendPreview.readerAfterV3(reader, envelope, eventId: eventId, now: now)
        // During a hand-over any frame of this card decides afresh.
        guard next != reader || handover != nil else { return }
        reader = next
        handover = nil
    }

    /// A commit floor: a `fold_preview_floor` control, or a raw frame's own
    /// revision. A folded card keeps the preview the floor withdrew only when
    /// `handsOver` (the control, or a raw frame that promises its folded
    /// result), never past its lifetime or `BlendPreview.commitFloorHandover`.
    mutating func commitFloor(_ floor: FoldRevision?, handsOver: Bool, card: FeedEventData?, now: TimeInterval) {
        let next = BlendPreview.readerAfterCommitFloor(reader, floor)
        let kept = handsOver
            ? BlendPreview.heldAcrossCommitFloor(shown, floor: floor, after: next,
                                                 committed: card.map(BlendPreviewCommitted.init), now: now)
            : nil
        reader = next
        handover = kept
    }

    /// A `fold_preview_floor` control's raw data; another event's is ignored.
    mutating func floorControl(_ raw: String, eventId: Int, card: FeedEventData?, now: TimeInterval) {
        guard case .floor(let value) = BlendPreview.commitFloorControl(raw: raw, eventId: eventId) else { return }
        commitFloor(value, handsOver: true, card: card, now: now)
    }

    /// A committed `probability` frame for this card (web's `onFrame`).
    mutating func frame(_ frame: LiveStreamFrame, eventId: Int, card: FeedEventData?, now: TimeInterval) {
        guard frame.eventId == eventId else { return }
        let promise = frame.foldedQuotePending == true && frame.foldedQuote == nil
        if let revision = frame.rev?.revision {
            commitFloor(revision, handsOver: promise && (frame.status == nil || frame.status == shown?.status),
                  card: card, now: now)
        } else if !promise {
            handover = nil
        }
    }

    /// A `reconcile` control: its removal revision is a commit floor.
    mutating func reconcile(_ control: LiveStreamReconcile, eventId: Int) {
        guard control.eventId == eventId else { return }
        reader = BlendPreview.readerAfterCommitFloor(reader, control.removalRev)
        handover = nil
    }

    /// A `resync`: the held preview is withdrawn, the session kept.
    mutating func invalidate() {
        reader.held = nil
        handover = nil
    }

    /// A connection boundary (open, reconnect, error, stop): the display goes
    /// and the v3 session ends; domain, epochs, fences and floors stay.
    mutating func reset() {
        reader = BlendPreview.readerReset(reader)
        handover = nil
    }
}

/// #10090 — the previews a Discover screen draws: each streamed game card's
/// shown blend preview and each held market's admitted legs, and the monotonic
/// time they are judged at. Published by `DiscoverViewModel`; laid over the
/// cards at draw time, never into `items`.
nonisolated struct DiscoverCardPreviews: Sendable, Equatable {
    var events: [Int: BlendPreviewState] = [:]
    var markets: [Int: DiscoverMarketPreviewState] = [:]
    var now: TimeInterval = 0

    var isEmpty: Bool { events.isEmpty && markets.isEmpty }

    /// The soonest moment a shown preview's lifetime ends after `now`, or nil.
    var nextExpiry: TimeInterval? {
        let event = events.values.map(\.expiresAt).filter { $0 > now }.min()
        let market = DiscoverMarketPreview.nextExpiry(markets, after: now)
        return [event, market].compactMap { $0 }.min()
    }

    /// `event` printing its admitted preview, or nil when none applies (the
    /// event page's gate: blend hero, same status, no newer committed revision,
    /// unexpired). The card's own pair rules print it (`DrawPricedWinner`,
    /// `duelPercents`): the served whole percents describe the committed pair.
    static func overlay(_ event: FeedEventData, _ state: BlendPreviewState?, now: TimeInterval) -> FeedEventData? {
        guard let odds = event.currentOdds,
              let p = BlendPreview.displayed(state, committed: BlendPreviewCommitted(event), now: now) else { return nil }
        var shown = event
        shown.currentOdds = BlendPreview.overlaid(odds, p: p, state: state)
        return shown
    }

    /// `item` with its admitted preview overlaid — bundles leaf by leaf — or
    /// `item` itself when none applies, so a card with no preview is drawn
    /// exactly as committed.
    func overlay(_ item: FeedItem) -> FeedItem {
        isEmpty ? item : overlaid(item) ?? item
    }

    /// nil when nothing in `item` is overlaid.
    private func overlaid(_ item: FeedItem) -> FeedItem? {
        if let bundle = item.bundle {
            let leaves = bundle.items.map { overlaid($0) }
            guard leaves.contains(where: { $0 != nil }) else { return nil }
            return item.withBundle(bundle.withItems(zip(bundle.items, leaves).map { $1 ?? $0 }))
        }
        if let event = item.event, let shown = Self.overlay(event, events[event.id], now: now) {
            return Self.replacing(item, event: shown, futures: item.futures)
        }
        if let market = item.futures, let state = markets[market.id],
           let shown = DiscoverMarketPreview.overlay(market, state, now: now) {
            return Self.replacing(item, event: item.event, futures: shown)
        }
        return nil
    }

    func overlay(_ items: [FeedItem]) -> [FeedItem] {
        isEmpty ? items : items.map { overlay($0) }
    }

    private static func replacing(_ item: FeedItem, event: FeedEventData?, futures: FeedFuturesData?) -> FeedItem {
        FeedItem(type: item.type, score: item.score, reason: item.reason, headline: item.headline,
                 contextSummary: item.contextSummary, event: event, futures: futures,
                 tournament: item.tournament, concept: item.concept, bundle: item.bundle,
                 personalized: item.personalized, baseScore: item.baseScore, multiplier: item.multiplier,
                 personalizationReasons: item.personalizationReasons, collection: item.collection)
    }
}
