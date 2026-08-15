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
    static func byCategory<T>(
        _ items: [T],
        sportsCategories: Set<String>,
        breakNonSportsRuns: Bool = false,
        category: (T) -> String
    ) -> [T] {
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
        var sportsSinceNonSport = 0
        let maxSportsRun = nonSports.count >= 4 ? 2 : 3

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
                if breakNonSportsRuns, category(nonSports[nonSportsIdx]) == lastCategory {
                    let windowEnd = min(nonSportsIdx + 5, nonSports.count)
                    if let swapIdx = (nonSportsIdx..<windowEnd)
                        .first(where: { category(nonSports[$0]) != lastCategory }) {
                        nonSports.swapAt(nonSportsIdx, swapIdx)
                    }
                }
                let item = nonSports[nonSportsIdx]
                nonSportsIdx += 1
                result.append(item)
                sportsSinceNonSport = 0
                lastCategory = category(item)
                continue
            }

            if sportsIdx < sports.count {
                // Avoid two adjacent cards of the same sports category by swapping
                // the front with the first differing card within the next 5 — an
                // O(1) swap on the backing array, indices unchanged otherwise.
                if category(sports[sportsIdx]) == lastCategory {
                    let windowEnd = min(sportsIdx + 5, sports.count)
                    if let swapIdx = (sportsIdx..<windowEnd)
                        .first(where: { category(sports[$0]) != lastCategory }) {
                        sports.swapAt(sportsIdx, swapIdx)
                    }
                }
                let item = sports[sportsIdx]
                sportsIdx += 1
                result.append(item)
                lastCategory = category(item)
                sportsSinceNonSport += 1
            } else if nonSportsIdx < nonSports.count {
                // Unreachable in practice (the leading `if` already claims this
                // case), kept to mirror the original control flow exactly.
                let item = nonSports[nonSportsIdx]
                nonSportsIdx += 1
                result.append(item)
                sportsSinceNonSport = 0
                lastCategory = category(item)
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
