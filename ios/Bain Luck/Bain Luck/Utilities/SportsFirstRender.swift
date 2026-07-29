import Foundation

/// Immutable snapshot of the successful MAIN response generation that FIRST became
/// renderable for a native **Sports** tab load (L2-211 Item 2 / C73). Stamped once,
/// at data-ready (the model assignment of a non-empty main response), and never
/// mutated by a later same-load merge (backfill/grouped) or a superseding load — so
/// the on-screen first-render telemetry always describes the exact generation that
/// produced first paint rather than whatever the live view-model state happens to
/// read at the render callback.
///
/// Between data-ready and the `onAppear`/`onChange` that emits, the backfill can
/// append events (changing `vm.items.count`), a later load can supersede this one,
/// a same-card-ID row can be reused, or the feed can be filtered — none of which may
/// change what the emitted event reports, because it reads this frozen token, not
/// `vm.items.count`. Carries exactly the four canonical fields of the
/// `native-sports-lifecycle/v1` render token (`generation`, `started_at`,
/// `provenance`, `item_count`).
struct SportsRenderGeneration: Equatable, Sendable {
    /// The monotonic load identity that produced this renderable data.
    let generation: Int
    /// When the producing load began — the anchor the on-screen first-render
    /// elapsed time is measured from (frozen, so a later load's start can't skew it).
    let startedAt: Date
    /// Provenance frozen at data-ready. The Sports main feed is always a live
    /// network response (no cache seed), so this is `"network"`; the field exists to
    /// carry the canonical token shape and to stay honest if a cache seed is added.
    let provenance: String
    /// Bounded item count of the generation that first rendered (the count at
    /// data-ready, NOT a live read at emit time).
    let itemCount: Int
}

/// Pure decision core for the native Sports on-screen first-render milestone
/// (L2-211 Item 2 / C73). Kept free of SwiftUI so the once-per-generation and
/// immutable-token contract is unit-testable without a running view.
enum SportsFirstRender {
    /// The first-render decision for an IMMUTABLE render generation. Returns the
    /// elapsed ms (from the token's own `startedAt`) AND the generation to attribute
    /// IF an event should be emitted for it; otherwise nil.
    ///
    /// The once-only guard keys on the generation's IMMUTABLE `generation` id
    /// (`generation != lastEmittedGenerationId`), NOT a boolean an `onAppear` refire
    /// could leave desynced — so a same-card-ID refresh (SwiftUI retains the rows and
    /// does not re-fire `onAppear`) still emits its new generation when driven by an
    /// `onChange(of: firstRenderGeneration)`, and a stale re-appear never double-emits
    /// a generation already reported. The item count reported comes from the frozen
    /// token, never a live `vm.items.count`. Returns nil for an empty generation
    /// (`itemCount <= 0`) so an empty successful main emits no first-card event, and
    /// nil when there is no generation yet. The ms is clamped at 0 against clock skew.
    static func generationDecision(
        generation: SportsRenderGeneration?,
        lastEmittedGenerationId: Int?,
        now: Date
    ) -> (ms: Double, generation: SportsRenderGeneration)? {
        guard let generation, generation.itemCount > 0 else { return nil }
        guard generation.generation != lastEmittedGenerationId else { return nil }
        return (max(0, now.timeIntervalSince(generation.startedAt) * 1000), generation)
    }
}
