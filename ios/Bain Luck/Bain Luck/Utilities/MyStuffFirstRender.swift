import Foundation

/// Immutable snapshot of the REQUIRED team-feed generation that FIRST became
/// renderable for a My Stuff load (L2-217 Item 2 / C88).
///
/// Stamped once, at data-ready (the model assignment of a non-empty required
/// response), and never mutated by the OPTIONAL team-futures merge that follows
/// or by a superseding load. The on-screen first-render telemetry reads this
/// frozen token — its own `startedAt` and its own `itemCount` — rather than live
/// view-model state, so a futures merge, a later load, a same-row reuse, or a
/// filter between data-ready and the render callback can never change what the
/// emitted event describes.
///
/// Carries exactly the four canonical render-token fields shared with
/// `DiscoverRenderGeneration` and `SportsRenderGeneration` (`generation`,
/// `started_at`, `provenance`, `item_count`), so all three native surfaces
/// describe first paint identically.
struct MyStuffRenderGeneration: Equatable, Sendable {
    /// The monotonic load identity that produced this renderable data.
    let generation: Int
    /// When the producing load began — the frozen anchor the elapsed time is
    /// measured from, so a later load's start can never skew it.
    let startedAt: Date
    /// Provenance frozen at data-ready: `"network"` for a live response,
    /// `"cache"` when the exact-principal response cache served it.
    let provenance: String
    /// Bounded item count of the generation that first rendered (the count at
    /// data-ready, NOT a live read at emit time).
    let itemCount: Int

    var fromCache: Bool { provenance == "cache" }
}

/// The bounded outcome vocabulary from the `my-stuff-first-card/v1` authority
/// contract (`backend/scripts/evals/my_stuff_first_card.py`). Kept as a raw-value
/// enum so an emitted event can only ever carry one of these labels — never a
/// free-form string, an error message, or anything derived from user data.
enum MyStuffOutcomeClass: String, Sendable {
    case signInRequired = "sign_in_required"
    case networkSuccess = "network_success"
    case memoryCacheHit = "memory_cache_hit"
    case retrySuccess = "retry_success"
    case partialSuccess = "partial_success"
    case emptySuccess = "empty_success"
    case requiredFailure = "required_failure"
    case cancelled = "cancelled"
    case superseded = "superseded"
    case identitySuperseded = "identity_superseded"
    case cachePrincipalMismatch = "cache_principal_mismatch"
}

/// Pure decision core for the My Stuff publication + first-render contract
/// (L2-217 Items 2 & 3 / C88). Kept free of SwiftUI and of the view model so the
/// account-boundary and once-per-generation guarantees are unit-testable without
/// a running view or a network.
enum MyStuffFirstRender {
    /// Whether a response fetched under `principalAtDispatch` during
    /// `dispatchGeneration` may be PUBLISHED to the screen now.
    ///
    /// Two independent gates, both required:
    ///   • **Identity** — the opaque principal must be UNCHANGED since the
    ///     request left. This is an exact `user:<id>` / `anon:<session>` compare,
    ///     not a signed-in Boolean, so a switch between two AUTHENTICATED
    ///     accounts is caught (the `account_a_to_b_late_response` scenario), as
    ///     are logout (`logout_late_response`) and sign-in.
    ///   • **Generation** — a newer load (navigation, pull-to-refresh, the live
    ///     auto-refresh timer, an auth change) must not have superseded this one
    ///     (`superseded_generation`).
    ///
    /// Mirrors `DiscoverViewModel.shouldPublishFeed`'s dispatch-identity rule so
    /// all native surfaces admit content under the same terms.
    static func shouldPublish(
        principalAtDispatch: String,
        currentPrincipal: String,
        dispatchGeneration: Int,
        currentGeneration: Int
    ) -> Bool {
        guard principalAtDispatch == currentPrincipal else { return false }
        return dispatchGeneration == currentGeneration
    }

    /// The outcome class for a rejected publication, so a discarded response is
    /// still reported honestly — and distinguishably — rather than silently.
    /// An identity change outranks a bare generation bump: it is the stronger,
    /// more actionable statement about WHY nothing was published.
    static func rejectionOutcome(
        principalAtDispatch: String,
        currentPrincipal: String
    ) -> MyStuffOutcomeClass {
        principalAtDispatch == currentPrincipal ? .superseded : .identitySuperseded
    }

    /// The first-render decision for an IMMUTABLE render generation.
    ///
    /// Returns the elapsed ms — measured from the token's OWN frozen `startedAt`,
    /// never a mutable view-level load start — and the generation to attribute,
    /// IF an event should be emitted; otherwise nil.
    ///
    /// Returns nil when there is no generation (nothing renderable yet), when the
    /// generation is EMPTY (`itemCount <= 0`, so an empty-but-successful load
    /// emits no first-card time), and when this generation id was already
    /// emitted. Keying the once-only guard on the immutable generation id rather
    /// than a boolean is what lets a same-row-ID refresh emit its NEW generation
    /// (SwiftUI does not re-run `onAppear` for retained rows) while a stale
    /// re-appear cannot double-emit one already reported. The ms is clamped at 0
    /// against clock skew.
    static func generationDecision(
        generation: MyStuffRenderGeneration?,
        lastEmittedGenerationId: Int?,
        now: Date
    ) -> (ms: Double, generation: MyStuffRenderGeneration)? {
        guard let generation, generation.itemCount > 0 else { return nil }
        guard generation.generation != lastEmittedGenerationId else { return nil }
        return (max(0, now.timeIntervalSince(generation.startedAt) * 1000), generation)
    }
}

/// One bounded My Stuff load milestone (L2-217 Item 3 / C88).
///
/// Carries ONLY opaque durations, a count, a build tag, and a bounded outcome
/// label — never a uid, email, token, session id, item id, or market text. `-1`
/// marks a stage that did not run or is not separately measurable, matching the
/// convention already used by the Discover and Sports latency rails.
struct MyStuffLoadStage: Sendable {
    enum Kind: String, Sendable {
        /// The REQUIRED team feed was assigned to the model. NOT a first render.
        case requiredDataReady = "required_data_ready"
        /// The OPTIONAL team futures merged (or honestly failed) afterward.
        case optionalMerge = "optional_merge"
    }

    let kind: Kind
    /// Time from load start to the resolved principal being known.
    let authReadyMs: Double
    /// Round-trip for this stage's request.
    let networkMs: Double
    /// Time from load start to this stage's data being assigned.
    let requiredDataReadyMs: Double
    let itemCount: Int
    let cacheOutcome: String
    let cacheAgeSeconds: Double
    let outcomeClass: MyStuffOutcomeClass
}
