import Foundation

/// Pure decision core for the Discover on-screen first-render milestone
/// (L2-206 / #1472, Item 3). Kept free of SwiftUI so the once-per-load and
/// ordering contract — a first-render time is emitted exactly once, only after a
/// load has started, and is a real elapsed measurement rather than a
/// model-assignment stamp — is unit-testable without a running view.
enum DiscoverFirstRender {
    /// The milliseconds from load start to `now` IF a first-render event should be
    /// emitted for this load; otherwise nil.
    ///
    /// Returns nil when it has already been emitted this load (`emitted == true`)
    /// or when no load-start is known (`loadStartedAt == nil`) — the latter guards
    /// against emitting a bogus "first render" that was never anchored to a load
    /// beginning (i.e. never conflating render with plain model assignment). The
    /// result is clamped at 0 so a clock skew can never report a negative latency.
    static func elapsedMsIfShouldEmit(emitted: Bool, loadStartedAt: Date?, now: Date) -> Double? {
        guard !emitted, let loadStartedAt else { return nil }
        return max(0, now.timeIntervalSince(loadStartedAt) * 1000)
    }

    /// The first-render decision for an IMMUTABLE render generation (L2-210 Item 2
    /// / C72; L2-212 Item 2 / C76). Returns the elapsed ms (measured from the
    /// token's OWN frozen `startedAt`) AND the generation to attribute IF an event
    /// should be emitted for it; otherwise nil.
    ///
    /// This supersedes the boolean `elapsedMsIfShouldEmit` guard on the Discover
    /// surface: the once-only guard is keyed on the generation's IMMUTABLE id
    /// (`generation.generation != lastEmittedGenerationId`), not a flag that a
    /// same-card-ID row reuse could leave desynced, and the provenance + bounded
    /// item count the caller reports come from the frozen token — never a live
    /// view-model read that a later generation, same-ID replacement, navigation, or
    /// model mutation could have changed between data-ready and the on-screen render
    /// callback. The elapsed time is likewise anchored to the token's frozen
    /// `startedAt` rather than a mutable view-level load-start timestamp that a
    /// newer load's `beginFirstRenderWindow` could have reset (the C76
    /// `mutable_render_start` counterexample). Returns nil for an empty generation
    /// (`itemCount <= 0`) so empty results emit no first-card event, and nil when
    /// there is no generation yet. The ms is clamped at 0 against clock skew.
    static func generationDecision(
        generation: DiscoverRenderGeneration?,
        lastEmittedGenerationId: Int?,
        now: Date
    ) -> (ms: Double, generation: DiscoverRenderGeneration)? {
        guard let generation, generation.itemCount > 0 else { return nil }
        guard generation.generation != lastEmittedGenerationId else { return nil }
        return (max(0, now.timeIntervalSince(generation.startedAt) * 1000), generation)
    }
}

/// Immutable snapshot of the data generation that FIRST became renderable for a
/// load (L2-210 Item 2 / C72). Captured once, at data-ready, and never mutated by
/// a later same-load replacement — so the on-screen first-render telemetry always
/// describes the exact generation that produced first paint rather than whatever
/// the live view-model state happens to read at the render callback. Between
/// data-ready and the `onAppear` that emits, a background revalidation can replace
/// the cache seed (changing item count and flipping the live provenance flag), a
/// later load can supersede this one, a same-card-ID row can be reused, or the
/// feed can be filtered/merged — none of which may change what the emitted event
/// reports, because it reads this frozen token, not `vm.items`/`vm.isShowingCachedContent`.
///
/// Carries exactly the four canonical fields of the `native-principal-render/v1`
/// render token (`generation`, `started_at`, `provenance`, `item_count`) — the same
/// shape as `SportsRenderGeneration` — so the on-screen first-render elapsed time is
/// measured from the token's own frozen `startedAt` and can never read a mutable
/// view-level load-start (L2-212 Item 2 / C76).
struct DiscoverRenderGeneration: Equatable, Sendable {
    /// The monotonic load identity that produced this renderable data.
    let generation: Int
    /// When the producing load began — the frozen anchor the on-screen first-render
    /// elapsed time is measured from, so a later load's start can never skew it (the
    /// C76 `mutable_render_start` counterexample).
    let startedAt: Date
    /// Provenance frozen at data-ready: `"cache"` when the last-good cache seed
    /// produced the first renderable cards for this load, `"network"` when the
    /// network did.
    let provenance: String
    /// Bounded item count of the generation that first rendered (the count at
    /// data-ready, not at emit time).
    let itemCount: Int

    /// Convenience predicate for the cache-vs-network provenance the on-screen
    /// telemetry reports; derived from the frozen `provenance` string.
    var fromCache: Bool { provenance == "cache" }
}
