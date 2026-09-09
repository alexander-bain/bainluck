import Foundation

/// When a fresh Discover response may reorder the list, and how it merges when
/// it may not (#4110).
///
/// 🔴 THE BUG THIS EXISTS FOR. `DiscoverViewModel` had three writers that each
/// assigned the WHOLE `items` array through `FeedInterleave.byCategory`: the boot
/// seed from the last-good cache, the fresh network fetch, and the pagination
/// merge. The interleave is deterministic for a given input, but the cached
/// response and the fresh response are DIFFERENT inputs, so they interleave to
/// different orders. The boot paint was therefore not a prefix of the fresh
/// paint, and a card the reader was mid-way through could move a long way or
/// leave the list at the moment the network answered. Alex watched it happen on
/// 2026-09-08. It needs no race: it is what the code did on a normal successful
/// load.
///
/// Pagination was the same defect wearing a different hat — `interleave(items +
/// fresh)` re-derives the order of every ALREADY-PAINTED card on every scroll.
///
/// ✅ THE CONTRACT. Not "paint once" — the boot cache exists so something is on
/// screen fast, and that is right. The rule is that once a card has a position,
/// nothing but the reader moves it.
///
/// The server's `edition` token (discover/001, live on production since
/// 2026-09-08) is what makes that decidable. It changes iff ordered MEMBERSHIP
/// changes — a card added, removed, replaced, or two swapped. Prices,
/// probabilities, scores and reason strings are explicitly not inputs, so the
/// 2-minute live-price poll rewrites numbers ~30x/hour without authorising a
/// reshuffle. It is reproducible across processes and stable across the `offset`
/// pages of one build. The only property we may rely on is
/// **same token ⇒ same cards in the same order**; we never recompute it, we only
/// compare two for equality.
enum DiscoverFeedReconcile {

    /// What a fresh response is allowed to do to the painted list.
    enum Decision: Equatable {
        /// Re-derive the whole order. Legal only when there is nothing to
        /// protect, or when the server says the ordering genuinely changed.
        case repaint
        /// Update in place, append what is new, remove what is gone — and never
        /// re-derive `FeedInterleave.byCategory` over the painted cards.
        case reconcile
    }

    /// The four branches of discover/001's contract, in one place.
    ///
    /// - `painted` empty: nothing is on screen to protect, so the fresh list IS
    ///   the first paint and takes the full interleave. Without this the common
    ///   cold no-cache load would append every card in raw server order and lose
    ///   the category interleave entirely — a regression dressed as a fix.
    /// - incoming edition ABSENT: the server states no ordering opinion, so we
    ///   keep ours and reconcile. This is a real branch and not a legacy shim —
    ///   it covers an older backend AND every empty refusal (`requires_auth`,
    ///   `leader_unavailable`, `input_age_ceiling`), for which discover returns no
    ///   token rather than a shared "empty edition" constant, precisely so three
    ///   different failures are not reconciled as one agreed ordering.
    /// - editions EQUAL: same cards in the same order; reconcile in place.
    /// - editions DIFFER: the server really did reorder, so a wholesale repaint
    ///   is legal. A nil painted edition counts as different — we painted a list
    ///   whose ordering we cannot vouch for, so we defer to the one we can.
    static func decision(
        paintedCount: Int, paintedEdition: String?, incomingEdition: String?
    ) -> Decision {
        if paintedCount == 0 { return .repaint }
        guard let incomingEdition else { return .reconcile }
        return paintedEdition == incomingEdition ? .reconcile : .repaint
    }

    /// Update in place, append new, remove gone — preserving the painted order
    /// exactly.
    ///
    /// The incoming copy of a card WINS on content (it carries the fresh prices
    /// and scores that the 2-minute poll moves) and LOSES on position: a card
    /// already on screen keeps the slot the reader last saw it in. Cards the
    /// server no longer sends are dropped; cards it has added arrive at the end,
    /// in the server's own order.
    ///
    /// Generic over the element and its key so the whole contract is testable
    /// without constructing a `FeedItem` graph.
    static func merge<Item>(
        painted: [Item], incoming: [Item], key: (Item) -> String
    ) -> [Item] {
        var incomingByKey: [String: Item] = [:]
        incomingByKey.reserveCapacity(incoming.count)
        for item in incoming { incomingByKey[key(item)] = item }

        // Kept cards, in PAINTED order, refreshed from the incoming payload.
        var merged: [Item] = []
        merged.reserveCapacity(max(painted.count, incoming.count))
        var kept = Set<String>()
        kept.reserveCapacity(painted.count)
        for item in painted {
            let k = key(item)
            guard let fresh = incomingByKey[k] else { continue }
            merged.append(fresh)
            kept.insert(k)
        }

        // Genuinely new cards, in the server's order, after everything painted.
        for item in incoming where !kept.contains(key(item)) {
            merged.append(item)
        }
        return merged
    }
}
