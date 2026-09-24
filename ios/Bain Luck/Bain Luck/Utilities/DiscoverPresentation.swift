import Foundation

/// The spacing pass the native Discover feed runs over the served ranking
/// (#8415, the phone half of web #8413).
///
/// `DiscoverViewModel.interleave` (page-merge order) and `DiscoverView.interleave`
/// / `.interleaveGrouped` (presentation order) all delegate here.
///
/// 🔴 WHAT THIS REPLACED. The old pass split the list into a sports queue and a
/// non-sports queue and took a sports card whenever the run cap allowed —
/// exactly one non-sports card after every two sports cards, whatever the
/// ranking — and its "don't repeat the last category" swap reached four cards
/// ahead for ANY other card. On the 2026-09-24 production payload
/// (`/api/feed?limit=50&event_pct=0.15`, the phone's own request) that turned a
/// served 4-sports / 6-non-sports top ten into 7/3: NASCAR (#18), an Azerbaijan
/// Grand Prix market (#19) and ATP Hangzhou (#20) reached page one while the
/// served #2 fell off it. The web had the same algorithm and the same defect.
///
/// ✅ SPACING DEFERS, IT NEVER PROMOTES. Each slot takes the highest-ranked
/// remaining card the rules allow. A card moves forward only past cards the
/// rules are holding back, never because of its category. The rules, in the
/// order they give way when nothing satisfies all of them:
///
///   1. the sports run cap and no two same-sport cards side by side — the web's
///      two rules, byte-for-byte (`frontend/lib/discover/spacedOrder.ts`);
///   2. no two same-CATEGORY cards side by side for non-sports too (#1883: a run
///      of six politics cards at `offset=30`);
///   3. no two same-STORY cards side by side (#1885: eleven county-magistrate
///      cards, all `politics`, so rule 2 alone could not see them).
///
/// Rules 2 and 3 are the phone's, kept from the old pass, and give way first.
/// So on any page where no two adjacent non-sports cards share a category, the
/// phone's order is the web's order. When no remaining card satisfies the
/// sports rules (only sports left and the cap reached), the highest-ranked card
/// that is not a same-sport repeat is taken, then simply the highest-ranked.
///
/// Idempotent: every rule depends only on what has already been placed, so a
/// second pass over its own output places the same card at every slot. That
/// matters because the view spaces twice (before grouping and after
/// personalization) on top of the page-merge pass.
///
/// Linear in practice, not quadratic: every rule reads only a card's category
/// and story family, and both are constant within one family. So "the first
/// remaining card in rank order that the rule allows" is always the HEAD of some
/// family queue, and each slot costs one scan of the family heads rather than a
/// scan of the remaining cards. The category and family closures run exactly
/// once per card (`DiscoverSpacingTests` counts them).
enum FeedInterleave {
    /// One family's cards, as input indices in rank order; `head` is the next
    /// unplaced one.
    private struct Queue {
        let category: String
        let family: String
        var members: [Int]
        var head = 0
    }

    static func spaced<T>(
        _ items: [T],
        sportsCategories: Set<String>,
        category: (T) -> String,
        family: ((T) -> String)? = nil
    ) -> [T] {
        guard items.count > 2 else { return items }

        let categories = items.map(category)
        let families = family.map { items.map($0) } ?? categories

        // One queue per family, in rank order. Family keys are namespaced by
        // their category so two categories can never share a queue even when a
        // caller's family closure does not refine its category.
        var queues: [Queue] = []
        var queueIndex: [String: Int] = [:]
        for i in items.indices {
            let key = categories[i] + "\u{1F}" + families[i]
            if let q = queueIndex[key] {
                queues[q].members.append(i)
            } else {
                queueIndex[key] = queues.count
                queues.append(Queue(category: categories[i], family: families[i], members: [i]))
            }
        }

        let nonSportsCount = categories.filter { !sportsCategories.contains($0) }.count
        let maxSportsRun = nonSportsCount >= 4 ? 2 : 3

        var result: [T] = []
        result.reserveCapacity(items.count)
        var lastCategory = ""
        var lastFamily = ""
        var sportsSinceNonSport = 0

        while result.count < items.count {
            func allowedBySportsRules(_ q: Queue) -> Bool {
                !sportsCategories.contains(q.category)
                    || (sportsSinceNonSport < maxSportsRun && q.category != lastCategory)
            }
            // The ladder, strictest first. Each rung's answer is the lowest
            // rank among the queue heads it allows.
            let rungs: [(Queue) -> Bool] = [
                { allowedBySportsRules($0) && $0.category != lastCategory && $0.family != lastFamily },
                { allowedBySportsRules($0) && $0.category != lastCategory },
                { allowedBySportsRules($0) && $0.family != lastFamily },
                { allowedBySportsRules($0) },
                { $0.category != lastCategory },
            ]
            var best = [Int?](repeating: nil, count: rungs.count + 1)
            for q in queues.indices where queues[q].head < queues[q].members.count {
                let rank = queues[q].members[queues[q].head]
                for (r, allows) in rungs.enumerated() where allows(queues[q]) {
                    if best[r].map({ queues[$0].members[queues[$0].head] > rank }) ?? true { best[r] = q }
                }
                if best[rungs.count].map({ queues[$0].members[queues[$0].head] > rank }) ?? true {
                    best[rungs.count] = q
                }
            }
            guard let q = best.lazy.compactMap({ $0 }).first else { break }

            let picked = queues[q].members[queues[q].head]
            queues[q].head += 1
            result.append(items[picked])
            lastCategory = categories[picked]
            lastFamily = families[picked]
            sportsSinceNonSport = sportsCategories.contains(lastCategory) ? sportsSinceNonSport + 1 : 0
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

    /// Explicit, and load-bearing: it is what makes the app archivable.
    ///
    /// Swift 6.3.3's `EarlyPerfInliner` crashes while inlining into this class's
    /// *synthesized* deallocating destructor, so `-O` builds of the app die with
    /// "While running pass SILFunctionTransform \"EarlyPerfInliner\" on
    /// SILFunction @$s9Bain_Luck20MemoizedPresentationCfD". Debug builds optimize
    /// nothing and are unaffected, which is why every simulator build, every
    /// `xcodebuild test` run and all of CI stayed green while `xcodebuild
    /// archive` could not produce a binary at all. Writing the destructor out by
    /// hand gives the pass a real body and it no longer crashes.
    ///
    /// Releasing the storage here is also what the synthesized destructor did, so
    /// this is a codegen workaround with no behaviour change. Guarded by
    /// `ReleaseBuildArchivabilityTests` and by `tools/native-release-check.sh`.
    deinit {
        value = nil
        signature = nil
    }

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
