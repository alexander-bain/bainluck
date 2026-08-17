import Foundation

/// Category-aware interleave used by the native Discover feed (L2-202 / C42 P2).
///
/// This is the single, linear-traversal core that `DiscoverViewModel.interleave`
/// (page-merge order) and `DiscoverView.interleave` / `.interleaveGrouped`
/// (presentation order) all delegate to. It replaces three copies of an
/// `Array.removeFirst()`-based drain — each front removal shifts every remaining
/// element (O(n)), making the whole drain O(n²) on the main actor over the full
/// payload. Here both partitions are consumed through advancing cursors and the
/// look-ahead reorder is an O(1) `swapAt`, so the drain is strictly linear in the
/// input size.
///
/// The output order is byte-for-byte identical to the prior `removeFirst`
/// algorithm: same category partition (stable by first appearance), same
/// `maxSportsRun` cap, same 5-wide look-ahead swap that avoids repeating a
/// category run, same terminal behavior. `DiscoverInterleaveTests` pins this
/// against a literal copy of the old algorithm across 0/1/2/3/50/200/500 mixed
/// fixtures. Callers keep their own early-return guards (e.g. the view's
/// `count > 2`) so each call site's exact behavior is preserved.
enum FeedInterleave {
    /// Interleave `items` so non-sports cards break up long sports runs, using a
    /// caller-supplied category classifier and sports-category set. Returns the
    /// input unchanged when there are no non-sports items to interleave with
    /// (matching every prior call site's `nonSports.isEmpty` guard).
    ///
    /// Linear: partition is one pass; the drain advances two cursors and performs
    /// at most one O(1) swap plus a bounded (≤5) look-ahead per emitted item.
    ///
    /// - Parameter breakNonSportsRuns: apply the same bounded look-ahead swap to
    ///   the **non-sports** drain (#1883). Defaults to `false`, which is the exact
    ///   pre-#1883 algorithm — that default is what keeps
    ///   `testByteForByteEquivalenceAcrossSizes` a live proof of the L2-202
    ///   equivalence rather than a test that had to be rewritten to stay green.
    ///
    ///   Why it is needed: the guard only ever broke runs in the *sports*
    ///   partition, and the sports partition runs dry partway down every Discover
    ///   page, so the tail of the page was an unguarded raw-order drain. Measured
    ///   on 83 production cards (2026-08-14), page `offset=30` came back with a
    ///   run of **six** politics cards — and today's guard made that page *worse*
    ///   than raw server order (5 → 6).
    ///
    ///   It is also the mandatory safety half of the #1883 concept fix. Mapping
    ///   `ufc → mma` moves concepts *out* of the non-sports partition, which
    ///   starves it of the variety it was using to break up runs: measured, the
    ///   domain map **alone** takes the worst case from 6 to **8**. Map plus this
    ///   guard returns it to 5. A fix that admits data ships its safety half in
    ///   the same commit.
    /// - Parameter family: a FINER token than `category` — the category narrowed
    ///   by the server's story key (#1885). Defaults to `category`, which makes
    ///   the second tier below provably inert and keeps every existing call
    ///   bit-for-bit unchanged.
    ///
    ///   Why a second tier rather than replacing `category`: swapping the run
    ///   test over to `family` wholesale would make the guard fire LESS often —
    ///   two politics cards from different stories would stop counting as a run
    ///   at all — and lengthen exactly the category runs the guard was built for.
    ///   So the preference is ordered. Break the category run if anything in the
    ///   window can; otherwise settle for breaking the STORY run, which is the
    ///   case the eleven county-magistrate cards presented: every candidate in
    ///   the window was `politics`, so tier one had nothing to offer and the page
    ///   shipped one story eleven times.
    static func byCategory<T>(
        _ items: [T],
        sportsCategories: Set<String>,
        breakNonSportsRuns: Bool = false,
        category: (T) -> String,
        family: ((T) -> String)? = nil
    ) -> [T] {
        // A nested func, not a stored `let`: binding a non-escaping parameter to
        // a local closure variable is a Swift escape error.
        func familyOf(_ item: T) -> String { family?(item) ?? category(item) }
        var sports: [T] = []
        var nonSports: [T] = []
        sports.reserveCapacity(items.count)
        nonSports.reserveCapacity(items.count)
        for item in items {
            if sportsCategories.contains(category(item)) {
                sports.append(item)
            } else {
                nonSports.append(item)
            }
        }
        // No non-sports to interleave — preserve the input exactly (the old code
        // returned `items` here, not the sports partition).
        guard !nonSports.isEmpty else { return items }

        var result: [T] = []
        result.reserveCapacity(items.count)

        // Cursors replace `removeFirst()`: advancing an index is O(1) and never
        // shifts the backing storage, so the whole drain is O(n) instead of O(n²).
        var sportsIdx = 0
        var nonSportsIdx = 0
        var lastCategory = ""
        var lastFamily = ""
        var sportsSinceNonSport = 0
        let maxSportsRun = nonSports.count >= 4 ? 2 : 3

        /// The bounded look-ahead swap, shared by both drains.
        ///
        /// Tier 1 is the original rule: find a card in the next 5 whose CATEGORY
        /// differs. Tier 2 (#1885) runs only when tier 1 found nothing, and
        /// settles for a card whose FAMILY differs.
        ///
        /// Tier 2 is SKIPPED OUTRIGHT when no `family` closure was supplied. Not
        /// an optimisation bolted on afterwards — it is what makes the inertness
        /// structural instead of incidental: with `family == nil` the two
        /// predicates are the same expression, so tier 2 could only re-find what
        /// tier 1 just rejected. Leaving it to run anyway cost a second window
        /// scan per emitted item and pushed the swap-heavy fixture in
        /// `DiscoverInterleaveTests` from ~5,000 classifications to 6,949 — the
        /// order was still correct, and the operation-count proof caught it
        /// anyway, which is the entire reason that test counts operations rather
        /// than timing them.
        func swapInADifferentCard(_ buffer: inout [T], from idx: Int) {
            let windowEnd = min(idx + 5, buffer.count)
            guard idx < windowEnd else { return }
            if let swapIdx = (idx..<windowEnd)
                .first(where: { category(buffer[$0]) != lastCategory }) {
                buffer.swapAt(idx, swapIdx)
                return
            }
            guard family != nil else { return }
            if let swapIdx = (idx..<windowEnd)
                .first(where: { familyOf(buffer[$0]) != lastFamily }) {
                buffer.swapAt(idx, swapIdx)
            }
        }

        while sportsIdx < sports.count || nonSportsIdx < nonSports.count {
            // Break a sports run (or drain the remaining non-sports once sports
            // are exhausted) — same predicate as the original leading `if`.
            if nonSportsIdx < nonSports.count
                && (sportsSinceNonSport >= maxSportsRun || sportsIdx >= sports.count) {
                // #1883: the same bounded look-ahead swap the sports branch has
                // always had. Opt-in, so the legacy order stays reachable and
                // pinned. Monotone by construction: when the next non-sports card
                // does not repeat `lastCategory` the swap never fires and the
                // output is bit-for-bit the pre-#1883 order.
                // #1885: the trigger widens from "same category" to "same family",
                // because a run of one STORY is the defect a reader actually
                // reports ("six in a row"), and eleven cards of one story all
                // read `politics` to the old test.
                // Short-circuit ordered so the family probe is never evaluated
                // when no `family` closure was supplied — op parity with the
                // pre-#1885 path, not just order parity.
                if breakNonSportsRuns,
                   category(nonSports[nonSportsIdx]) == lastCategory
                    || (family != nil && familyOf(nonSports[nonSportsIdx]) == lastFamily) {
                    swapInADifferentCard(&nonSports, from: nonSportsIdx)
                }
                let item = nonSports[nonSportsIdx]
                nonSportsIdx += 1
                result.append(item)
                sportsSinceNonSport = 0
                lastCategory = category(item)
                lastFamily = familyOf(item)
                continue
            }

            if sportsIdx < sports.count {
                // Avoid two adjacent cards of the same sports category by swapping
                // the front with the first differing card within the next 5 — an
                // O(1) swap on the backing array, indices unchanged otherwise.
                if category(sports[sportsIdx]) == lastCategory {
                    swapInADifferentCard(&sports, from: sportsIdx)
                }
                let item = sports[sportsIdx]
                sportsIdx += 1
                result.append(item)
                lastCategory = category(item)
                lastFamily = familyOf(item)
                sportsSinceNonSport += 1
            } else if nonSportsIdx < nonSports.count {
                // Unreachable in practice (the leading `if` already claims this
                // case), kept to mirror the original control flow exactly.
                let item = nonSports[nonSportsIdx]
                nonSportsIdx += 1
                result.append(item)
                sportsSinceNonSport = 0
                lastCategory = category(item)
                lastFamily = familyOf(item)
            }
        }

        return result
    }
}

/// A tiny, reference-type memo for a derived presentation value (L2-202 / C42 P2).
///
/// The native Discover feed rebuilds its interleaved+grouped presentation inside
/// a computed property that SwiftUI re-evaluates on *every* body pass — including
/// scroll-driven `visibleCount` bumps, impression-set mutations, and unrelated
/// `@State` changes that do not affect the feed content at all. That rebuild is
/// the full sanitize → stale-gate → dismiss → cooldown → interleave → group →
/// personalize → interleave pipeline over the whole payload, on the main actor.
///
/// Holding an instance in `@State` (a reference type) lets the view recompute the
/// presentation only when a cheap semantic *signature* changes — feed version,
/// dismiss store, interaction profile, or a coarse staleness bucket. Mutating the
/// cache's internals does **not** reassign the `@State` value, so the memo is
/// invisible to SwiftUI's invalidation and never schedules an extra render.
///
/// Not thread-safe by design: it is only ever touched during main-actor body
/// evaluation. `buildCount` is exposed as deterministic proof (tests) that
/// unrelated view-state changes reuse the cache and each semantic change rebuilds
/// exactly once.
final class MemoizedPresentation<Value> {
    private var signature: String?
    private var value: Value?

    /// Number of real rebuilds (cache misses). A stable signature across calls
    /// leaves this unchanged; each distinct consecutive signature increments it
    /// once. Used by tests to prove memoization, and available for telemetry.
    private(set) var buildCount = 0

    init() {}

    /// Return the memoized value for `signature`, invoking `build` only when the
    /// signature differs from the last resolved one.
    func resolve(signature newSignature: String, build: () -> Value) -> Value {
        if let current = signature, current == newSignature, let cached = value {
            return cached
        }
        let built = build()
        value = built
        signature = newSignature
        buildCount += 1
        return built
    }

    /// Force the next `resolve` to rebuild regardless of signature. Not needed by
    /// the current invalidation model (signatures cover every semantic change) but
    /// kept as an explicit escape hatch.
    func invalidate() {
        signature = nil
        value = nil
    }
}
