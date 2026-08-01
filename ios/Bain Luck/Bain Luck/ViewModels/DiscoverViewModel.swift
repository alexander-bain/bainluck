import Combine
import Foundation

/// Narrow feed-fetch seam so `DiscoverViewModel` pagination can be exercised by
/// a deterministic fake client in tests (L2-192 Item 2). `APIClient` (an actor)
/// conforms via the extension at the bottom of this file; the default init arg
/// keeps production wiring unchanged.
protocol DiscoverFeedProviding: Sendable {
    nonisolated func fetchDiscoverFeed(
        limit: Int,
        offset: Int,
        eventPct: Double?,
        cacheTTL: TimeInterval?
    ) async throws -> FeedResponse

    /// Initial-load fetch that ALSO resolves the request/namespace principal so the
    /// view model can gate publication on the resolved principal (L2-210 Item 1 /
    /// C72). Returns the decoded page plus whether THIS request carried a signed-in
    /// credential and whether the CURRENT expected feed namespace is signed-in.
    /// Defaulted below to a publish-always result for fakes that do not model a
    /// principal, so existing pagination/SWR fakes behave exactly as before.
    nonisolated func fetchDiscoverFeedResolvingPrincipal(
        limit: Int,
        offset: Int,
        eventPct: Double?,
        cacheTTL: TimeInterval?
    ) async throws -> DiscoverFeedFetchResult

    /// The CURRENT opaque feed principal (signed-in user namespace, else anonymous
    /// session namespace), resolved at the moment of the call (L2-212 Item 1 / C76).
    /// The view model reads this immediately before in-memory publication so a
    /// response can be bound to the EXACT dispatch identity that produced it — not a
    /// signed-in Boolean parity that would let one authenticated account's feed paint
    /// over another's (the `boolean_only_a_to_b_publish` counterexample).
    nonisolated func currentFeedPrincipal() async -> String

    /// Whether the optimistic last-good cache seed may be admitted for the CURRENT
    /// persisted identity before auth restore resolves (L2-212 Item 1 / C76). Reports
    /// whether the current namespace is signed-in and whether a credential is
    /// eligible for restore, so the divergent no-token cleanup can be serialized
    /// before cache admission while a valid returning user still paints immediately.
    nonisolated func optimisticSeedContext() async -> DiscoverOptimisticSeedContext
}

/// The result of a principal-resolving initial feed fetch (L2-210 Item 1 / C72;
/// L2-212 Item 1 / C76): the decoded page plus the signals `DiscoverViewModel`'s
/// publication gate needs to keep a response from painting under the wrong principal.
struct DiscoverFeedFetchResult: Sendable {
    let response: FeedResponse
    /// The OPAQUE feed principal that dispatched this request (a `user:<id>` or
    /// `anon:<session>` namespace). Publication compares this against the CURRENT
    /// identity so a mid-flight login/logout/account switch — even between two
    /// authenticated accounts — can never paint one identity's feed under another
    /// (the C76 `cross_identity_publish`/`cross_identity_store` counterexamples).
    let identityAtFetch: String
    /// Whether the request that produced `response` actually carried a signed-in
    /// credential (the token provider was installed when it left the client).
    let wasAuthenticated: Bool
    /// Whether the expected feed namespace at dispatch was signed-in (a `user:<id>`
    /// namespace, optimistic or resolved), as opposed to anonymous.
    let expectedSignedIn: Bool
}

/// The two signals that decide whether the optimistic last-good cache seed may be
/// admitted before auth restore resolves (L2-212 Item 1 / C76).
struct DiscoverOptimisticSeedContext: Sendable {
    /// Whether the current persisted feed namespace is signed-in (`user:<id>`).
    let signedInNamespace: Bool
    /// Whether a credential is eligible for restore for that namespace (a stored
    /// session credential exists). A valid returning user is `true`; the divergent
    /// no-token state (signed-in namespace, no restorable credential) is `false`.
    let credentialEligibleForRestore: Bool
}

extension DiscoverFeedProviding {
    /// Default: no principal modeled, so report `expected == authenticated` (both
    /// `false`), an empty dispatch identity, and the publication gate always
    /// publishes — behaviorally identical to pre-L2-210 for fakes that only
    /// implement `fetchDiscoverFeed`.
    nonisolated func fetchDiscoverFeedResolvingPrincipal(
        limit: Int,
        offset: Int,
        eventPct: Double?,
        cacheTTL: TimeInterval?
    ) async throws -> DiscoverFeedFetchResult {
        let response = try await fetchDiscoverFeed(
            limit: limit, offset: offset, eventPct: eventPct, cacheTTL: cacheTTL)
        return DiscoverFeedFetchResult(
            response: response, identityAtFetch: "",
            wasAuthenticated: false, expectedSignedIn: false)
    }

    /// Default: the neutral empty identity, so `identityAtFetch == currentIdentity`
    /// holds for principal-agnostic fakes and the publish/persist gate stays
    /// publish-always (same behavior as before this seam existed).
    nonisolated func currentFeedPrincipal() async -> String { "" }

    /// Default: anonymous namespace, seed admissible — an unmodeled fake seeds its
    /// last-good exactly as before.
    nonisolated func optimisticSeedContext() async -> DiscoverOptimisticSeedContext {
        DiscoverOptimisticSeedContext(signedInNamespace: false, credentialEligibleForRestore: true)
    }
}

final class DiscoverViewModel: ObservableObject {
    @Published private(set) var items: [FeedItem] = [] {
        didSet { itemsVersion &+= 1 }
    }

    /// Monotonic version bumped on every `items` reassignment (L2-202 / C42 P2).
    /// The feed only ever replaces `items` wholesale — cold load, cache seed,
    /// pull-to-refresh, account switch, pagination merge — so a counter is a
    /// cheaper, more reliable "did the feed change" signal than diffing the array.
    /// `DiscoverView` folds this into its presentation memo signature so the
    /// interleave+group pipeline rebuilds when the feed actually changes, not on
    /// every SwiftUI body pass. Not `@Published`: it always changes in lockstep
    /// with `items`, whose publish already re-runs any dependent view body.
    private(set) var itemsVersion = 0

    /// Provenance of the data that FIRST became renderable for the current load
    /// (L2-208 Item 2 / C67 P2): `true` when the last-good cache seed produced the
    /// first renderable cards, `false` when the network did. Captured ONCE per load
    /// — the moment `items` first goes non-empty — and never flipped by a later
    /// same-load network replacement, so the view's on-screen first-render event
    /// reports the source that actually produced first paint rather than whatever
    /// `isShowingCachedContent` happens to read at `onAppear` time (a fast network
    /// hit can flip that flag to false before SwiftUI emits the render callback).
    /// Nil until the first renderable data lands; reset at each `load()` start. Not
    /// `@Published`: it is read only in the render callback, never drives layout.
    private(set) var firstDataFromCache: Bool?

    /// Immutable snapshot of the generation that FIRST became renderable for the
    /// current load (L2-210 Item 2 / C72). Stamped ONCE — the moment `items` first
    /// goes non-empty, from the cache seed or the network — and never mutated by a
    /// later same-load replacement. The view's on-screen first-render telemetry
    /// reads this frozen token (its own provenance + bounded item count) instead of
    /// live `items`/`isShowingCachedContent`, so a later generation, a same-card-ID
    /// row reuse, navigation, or a model mutation between data-ready and the render
    /// callback can never make the emitted event describe another generation. Nil
    /// until first renderable data lands; reset at each `load()` start.
    ///
    /// `@Published` (L2-212 Item 2 / C76): the view acknowledges the rendered
    /// generation through `.onChange(of: firstRenderGeneration)`, so a retained
    /// same-card-ID refresh still emits its new generation without assuming the first
    /// card's `onAppear` re-fires (SwiftUI does not re-run `onAppear` for retained
    /// row IDs). Mirrors `FeedViewModel.firstRenderGeneration` (Sports).
    @Published private(set) var firstRenderGeneration: DiscoverRenderGeneration?

    @Published private(set) var loading = true
    @Published private(set) var error: String?
    @Published private(set) var loadingMore = false
    /// Exposed so the feed can show an honest end-of-feed card once pagination
    /// is exhausted (#902 item 9). Stays true until loadMoreIfNeeded confirms
    /// the API has no more pages.
    @Published private(set) var hasMore = true

    /// True while the currently rendered `items` came from the last-good disk
    /// cache and have not yet been replaced by a fresh server response (#1465).
    /// Lets the view stay honest that content is being revalidated.
    @Published private(set) var isShowingCachedContent = false

    /// True when a revalidation failed while last-good content is still on screen
    /// (#1465). The view surfaces a small, honest "showing recent — couldn't
    /// refresh" banner instead of silently presenting stale data as current.
    @Published private(set) var refreshFailedShowingCache = false

    /// When the currently shown last-good payload was stored, for honest staleness
    /// framing. Nil once fresh content replaces the cache.
    @Published private(set) var lastGoodStoredAt: Date?

    private var nextOffset = 0
    private let client: DiscoverFeedProviding
    /// Read seam for the last-good disk cache (#1465). Nil in tests that only
    /// exercise pagination so those stay hermetic and network-only.
    private let lastGood: DiscoverLastGoodReading?
    /// Sink for stale-while-revalidate telemetry (#1465). Defaults to Firebase;
    /// injectable so tests can assert emitted events deterministically.
    private let telemetry: (@Sendable (DiscoverFeedTelemetry) -> Void)?

    /// Total wall-clock budget for transient retries of the initial load
    /// (L2-201 / #1472). One budget across ALL retries — NOT a fresh timeout per
    /// attempt — so a slow/timing-out request that consumes the budget yields a
    /// single attempt rather than multiplying one load into many long requests
    /// (C42 P3). Injectable so tests drive it deterministically.
    private let retryBudget: TimeInterval
    /// Backoff between transient retries, clamped to the remaining budget.
    private let retryBackoff: TimeInterval

    /// Monotonic load identity (L2-201 / #1472). Each `load()` claims the next
    /// value; a load whose generation is superseded by a newer `load()` (pull to
    /// refresh, account switch, rapid re-entry) discards its late response instead
    /// of overwriting the current session's feed. Prevents a stale in-flight
    /// response from one identity clobbering another's.
    private var loadGeneration = 0

    /// Bounded first page (L2-201 / #1472). The initial load requests only enough
    /// cards for the first viewport so first paint no longer waits on the full
    /// former window to transfer/decode/interleave (C42 P1). The remaining pages
    /// load in the background through the existing scroll-driven
    /// `loadMoreIfNeeded` pagination/merge contract (DiscoverView prefetches ~3
    /// cards before the rendered window's end). The backend ranks the full
    /// candidate universe before slicing, so a 50-card first page returns the
    /// first 50 of the former 200 in the same order.
    static let firstPageLimit = 50

    /// Upper bound on how many consecutive duplicate-only / ineligible server
    /// pages a single loadMore pass will scan before surfacing a retryable
    /// error instead of spinning forever (L2-192 Item 2). Each page is up to
    /// `limit` rows, so this is a wide-but-finite forward window.
    private static let maxPageScans = 6

    init(
        client: DiscoverFeedProviding = APIClient.shared,
        lastGood: DiscoverLastGoodReading? = APIClient.shared,
        telemetry: (@Sendable (DiscoverFeedTelemetry) -> Void)? = { AnalyticsService.trackDiscoverFeedCache($0) },
        retryBudget: TimeInterval = 6,
        retryBackoff: TimeInterval = 1
    ) {
        self.client = client
        self.lastGood = lastGood
        self.telemetry = telemetry
        self.retryBudget = retryBudget
        self.retryBackoff = retryBackoff
    }

    private static let sportsCategories: Set<String> = [
        "basketball", "football", "baseball", "hockey", "soccer",
        "golf", "mma", "boxing", "tennis", "cricket", "motorsports",
        "americanfootball", "icehockey", "olympics",
    ]

    @MainActor
    func load() async {
        // Claim a load identity so a superseded (older) load discards its late
        // response instead of overwriting a newer session's feed (L2-201 / #1472).
        loadGeneration &+= 1
        let generation = loadGeneration
        let loadStart = Date()
        // Re-arm first-render provenance for this load (L2-208 Item 2): the next
        // data to become renderable — cache seed or network — stamps it once.
        firstDataFromCache = nil
        // Re-arm the immutable render-generation token (L2-210 Item 2): the next
        // data to become renderable stamps it once, frozen for this load.
        firstRenderGeneration = nil

        // Serialize the no-token divergent cleanup before cache admission (L2-212
        // Item 1 / C76). At cold launch the optimistic namespace is seeded from the
        // last-known signed-in id BEFORE auth restore resolves. When that id has no
        // restorable credential (the credential store and last-known-id store
        // diverged — id present, token gone), painting the `user:<id>` last-good
        // would surface a signed-in user's personalized cache to someone who is
        // effectively anonymous, in the window before AuthManager's cleanup flips the
        // namespace to anonymous. Gate the seed on that resolution: a signed-in
        // namespace admits its personalized last-good ONLY when a credential is
        // eligible for restore — the valid returning user still paints immediately,
        // with no added delay — while the divergent no-token state skips the seed and
        // lets the cleanup resolve the namespace to anonymous first.
        let seedContext = await client.optimisticSeedContext()
        guard generation == loadGeneration else { return }
        let seedAdmissible = Self.shouldSeedOptimisticCache(
            signedInNamespace: seedContext.signedInNamespace,
            credentialEligibleForRestore: seedContext.credentialEligibleForRestore)

        // Stale-while-revalidate (#1465): on a cold view model, seed the last
        // successful payload from disk so a first card renders immediately instead
        // of blocking on the 9–13s cold `/api/feed` miss (#1459). The view re-runs
        // its `now`-relative eligibility gate on this content, so nothing here
        // extends how long a settled/aged card may survive.
        if items.isEmpty, seedAdmissible, let lastGood {
            let t0 = Date()
            let cached = await lastGood.loadLastGoodFeed()
            // A newer load() started while we read the disk cache — its identity
            // owns the feed now; do not seed stale content over it.
            guard generation == loadGeneration else { return }
            if let cached {
                let renderable = Self.renderable(cached.response.items)
                if renderable.isEmpty {
                    telemetry?(DiscoverFeedTelemetry(
                        outcome: .cacheMiss, cacheDecodeMs: Self.elapsedMs(since: t0),
                        itemCount: 0))
                } else {
                    let mergeStart = Date()
                    items = Self.interleave(renderable)
                    // First paint provenance: the cache seed produced first paint.
                    if firstDataFromCache == nil { firstDataFromCache = true }
                    // Freeze the render-generation token from the cache seed
                    // (L2-210 Item 2; L2-212 Item 2 / C76): the canonical token
                    // {generation, started_at, provenance, item_count}, provenance
                    // cache, count = the seeded cards, started_at anchored to this
                    // load's frozen start.
                    if firstRenderGeneration == nil {
                        firstRenderGeneration = DiscoverRenderGeneration(
                            generation: generation, startedAt: loadStart,
                            provenance: "cache", itemCount: items.count)
                    }
                    let mergeMs = Self.elapsedMs(since: mergeStart)
                    hasMore = cached.response.hasMore
                    nextOffset = Self.pageBoundary(cached.response, from: 0)
                    loading = false
                    error = nil
                    isShowingCachedContent = true
                    refreshFailedShowingCache = false
                    lastGoodStoredAt = cached.storedAt
                    telemetry?(DiscoverFeedTelemetry(
                        outcome: .cacheHitServed, cacheDecodeMs: Self.elapsedMs(since: t0),
                        itemCount: renderable.count,
                        cacheAgeSeconds: cached.age(now: Date()),
                        mergeMs: mergeMs,
                        dataReadyMs: Self.elapsedMs(since: loadStart)))
                }
            } else {
                telemetry?(DiscoverFeedTelemetry(
                    outcome: .cacheMiss, cacheDecodeMs: Self.elapsedMs(since: t0),
                    itemCount: 0))
            }
        }

        // Only show the blocking loading state when there is nothing to render.
        // When last-good seeded content, revalidation happens silently behind it.
        if items.isEmpty {
            loading = true
            error = nil
        }
        // Whether a first card is already on screen from the cache seed. When
        // false, the network success below is what makes the data ready, so its
        // `dataReadyMs` is the cold time-to-data-ready (the on-screen first render
        // is tracked separately by the view — L2-206 Item 3).
        let seededFromCache = !items.isEmpty

        // One bounded first-page fetch with deadline-aware, classified retries
        // (L2-201 / #1472). The prior code re-issued a normalized-identical
        // `event_pct: nil` fallback (a no-op the backend collapses to the same
        // Discover page) and retried EVERY error — decode/4xx included — up to a
        // six-request ceiling. This makes a single attempt, retries only transient
        // transport / 5xx / 429 failures, and only while one shared budget remains.
        let netStart = Date()
        let deadline = Date().addingTimeInterval(retryBudget)
        // Whether the ONE guaranteed initial attempt has been admitted yet
        // (L2-208 Item 2 / C67 P1). The first attempt always runs (bounded by the
        // budget); once admitted, any later loop that finds the budget exhausted
        // throws `DeadlineExceededError` from `fetchWithinDeadline` instead of
        // starting a new unbounded request.
        var admittedFirstAttempt = false
        while true {
            do {
                // One REAL cancellable deadline for the whole initial load (L2-206
                // Item 2). The bare `fetchDiscoverFeed` is only bounded by
                // URLSession's 30/60s timeouts, so a suspended request would hang
                // far past the nominal budget. Racing it against the remaining
                // budget cancels a stuck request AT the budget — and because each
                // attempt is bounded by the time LEFT (not a fresh per-attempt
                // timeout), a slow request that burns the budget yields no retry.
                let fetch = try await fetchWithinDeadline(
                    deadline: deadline, isFirstAttempt: !admittedFirstAttempt)
                admittedFirstAttempt = true
                // A newer load() superseded this one mid-flight (refresh / account
                // switch) — drop this response rather than overwrite (C42, races).
                guard generation == loadGeneration else { return }

                // Principal publication gate (L2-210 Item 1 / C72): never publish an
                // anonymous network response over a signed-in user's optimistic
                // cache. The returning-user race fires a tokenless revalidation
                // before auth restore installs the provider; its anonymous response
                // must not paint over the personalized cache seed. When the expected
                // namespace is signed-in but this response came back anonymous,
                // discard it and retry within the SAME bounded budget — by the next
                // attempt the provider is installed (authenticated → publishes) or
                // restore has resolved to anonymous (expected namespace anon →
                // publishes). Mirrors `shouldPersistFeed` so the screen and disk
                // admit under identical principal rules.
                // Resolve the CURRENT opaque principal immediately before publication
                // (L2-212 Item 1 / C76) so the gate binds to the EXACT dispatch
                // identity, not a signed-in Boolean parity that would let one
                // authenticated account's response paint over another's.
                let currentIdentity = await client.currentFeedPrincipal()
                guard generation == loadGeneration else { return }
                if !Self.shouldPublishFeed(
                    identityAtFetch: fetch.identityAtFetch,
                    expectedSignedIn: fetch.expectedSignedIn,
                    wasAuthenticated: fetch.wasAuthenticated,
                    currentIdentity: currentIdentity
                ) {
                    telemetry?(DiscoverFeedTelemetry(
                        outcome: .principalDiscarded,
                        networkMs: Self.elapsedMs(since: netStart),
                        itemCount: fetch.response.items.count))
                    let remaining = deadline.timeIntervalSinceNow
                    // Budget spent — settle to the optimistic cache (or honest
                    // error) rather than start a new unbounded request.
                    guard remaining > 0 else { break }
                    try? await Task.sleep(for: .seconds(min(retryBackoff, remaining)))
                    guard generation == loadGeneration else { return }
                    continue
                }

                let response = fetch.response
                let renderable = Self.renderable(response.items)
                // L2-215 Item 1 (#1486): count the empty predictive envelopes this
                // page dropped, identity-free, on the network path only.
                reportSuppressedEnvelopes(response.items)
                let mergeStart = Date()
                items = Self.interleave(renderable)
                // First paint provenance: only stamp network when the cache seed
                // did NOT already produce first paint this load — a background
                // revalidation behind a served cache must not relabel the render
                // that already happened from cache (C67 P2).
                if firstDataFromCache == nil { firstDataFromCache = false }
                // Freeze the render-generation token from the network (L2-210 Item
                // 2; L2-212 Item 2 / C76), but only if the cache seed did not already
                // freeze it — the generation that FIRST rendered owns the token. The
                // canonical token {generation, started_at, provenance, item_count}
                // anchors started_at to this load's frozen start.
                if firstRenderGeneration == nil {
                    firstRenderGeneration = DiscoverRenderGeneration(
                        generation: generation, startedAt: loadStart,
                        provenance: "network", itemCount: items.count)
                }
                let mergeMs = Self.elapsedMs(since: mergeStart)
                hasMore = response.hasMore
                // Advance by the SERVER page boundary (offset + limit), not the
                // decoded item count — the tolerant decoder drops malformed rows,
                // so initial and incremental loads must share one contract (C29).
                nextOffset = Self.pageBoundary(response, from: 0)

                // Fresh server content replaces last-good without blanking or a
                // local reorder — the server order is preserved as decoded (#1465).
                error = nil
                loading = false
                isShowingCachedContent = false
                refreshFailedShowingCache = false
                lastGoodStoredAt = nil
                telemetry?(DiscoverFeedTelemetry(
                    outcome: .revalidateSuccess,
                    networkMs: Self.elapsedMs(since: netStart), itemCount: items.count,
                    mergeMs: mergeMs,
                    dataReadyMs: seededFromCache ? nil : Self.elapsedMs(since: loadStart)))
                return
            } catch let cancel where Self.isCancellation(cancel) {
                // Raw OR wrapped cancellation (task teardown, superseded generation,
                // or the deadline race cancelling the loser): abandon quietly — keep
                // prior content, no error banner, no failure telemetry (L2-214 Item 2).
                loading = false
                return
            } catch {
                // The attempt ran (and failed) — it counts as admitted, so any
                // further loop is a retry that must respect the exhausted-budget
                // throw rather than start a new unbounded request (L2-208 Item 2).
                admittedFirstAttempt = true
                // A newer load() owns the feed — stop silently, let it drive state.
                guard generation == loadGeneration else { return }
                print("DiscoverView load error: \(error)")
                // Only transient transport / 5xx / 429 self-heal; decode and
                // non-retryable 4xx cannot, so never spend a retry on them. And a
                // retry happens only while the ONE shared budget still has time —
                // a request that itself burned the budget yields no further attempt.
                let remaining = deadline.timeIntervalSinceNow
                guard Self.isRetryable(error), remaining > 0 else { break }
                try? await Task.sleep(for: .seconds(min(retryBackoff, remaining)))
                guard generation == loadGeneration else { return }
            }
        }

        // All network attempts failed. Never blank last-good content — keep it and
        // tell the truth that the refresh failed (#1465). With nothing cached, fall
        // to the honest error state exactly as before.
        guard generation == loadGeneration else { return }
        loading = false
        if !items.isEmpty {
            refreshFailedShowingCache = true
            error = "Showing recent markets — couldn't refresh"
            telemetry?(DiscoverFeedTelemetry(
                outcome: .revalidateFailedKeptCache,
                networkMs: Self.elapsedMs(since: netStart), itemCount: items.count,
                cacheAgeSeconds: lastGoodStoredAt.map { Date().timeIntervalSince($0) }))
        } else {
            error = "Couldn't load feed"
            telemetry?(DiscoverFeedTelemetry(
                outcome: .revalidateFailedNoCache,
                networkMs: Self.elapsedMs(since: netStart), itemCount: 0))
        }
    }

    /// Whether a fetched network response may be PUBLISHED to the on-screen feed
    /// (L2-210 Item 1 / C72; L2-212 Item 1 / C76). Mirrors `APIClient.shouldPersistFeed`
    /// EXACTLY so the screen and the disk admit under identical terms — publication and
    /// persistence bind to the same opaque dispatch identity, not a signed-in Boolean:
    ///   • the dispatch identity must be UNCHANGED since the request left
    ///     (`identityAtFetch == currentIdentity`), so a mid-flight login/logout/account
    ///     switch — including a switch between two AUTHENTICATED accounts (the
    ///     `boolean_only_a_to_b_publish` counterexample) — never paints one identity's
    ///     feed under another;
    ///   • a signed-in namespace admits only an authenticated response, an anonymous
    ///     namespace only an unauthenticated one (`expectedSignedIn == wasAuthenticated`).
    /// The returning-user race — an anonymous response arriving while the expected
    /// namespace is still `user:<id>` — therefore resolves to "do not publish", so the
    /// anonymous feed never paints over the personalized cache seed.
    static func shouldPublishFeed(
        identityAtFetch: String,
        expectedSignedIn: Bool,
        wasAuthenticated: Bool,
        currentIdentity: String
    ) -> Bool {
        guard identityAtFetch == currentIdentity else { return false }
        return expectedSignedIn == wasAuthenticated
    }

    /// Whether the optimistic last-good cache seed may be admitted for the current
    /// persisted identity before auth restore resolves (L2-212 Item 1 / C76). An
    /// anonymous namespace always admits its own last-good; a signed-in namespace
    /// admits its personalized last-good ONLY when a credential is eligible for
    /// restore — the valid returning user paints immediately with no added delay,
    /// while the divergent no-token state (signed-in namespace, no restorable
    /// credential) does not seed, so the cleanup that resolves the namespace to
    /// anonymous is serialized before any signed-in cache is painted.
    static func shouldSeedOptimisticCache(
        signedInNamespace: Bool,
        credentialEligibleForRestore: Bool
    ) -> Bool {
        signedInNamespace ? credentialEligibleForRestore : true
    }

    /// Whether a pagination response fetched under `capturedGeneration` may still
    /// mutate feed state, given the CURRENT load generation (C78 Item 1). The load
    /// generation is captured before pagination's first await and re-checked after
    /// every await: a logout, login, account switch, pull-refresh, or superseding
    /// load bumps `loadGeneration` (see `load()`/`rebindForIdentityChange()`), so a
    /// response that returns after such a transition belongs to a DEAD generation
    /// and must be dropped before it appends items, advances the offset, flips
    /// `hasMore`/`error`, or emits analytics — otherwise a prior identity's page
    /// would paint into, and advance the paging cursor of, the new identity (the
    /// `reject_stale_append_and_offset` counterexample). A same-generation response
    /// (`captured == current`) applies normally.
    static func shouldApplyPaginationResult(
        capturedGeneration: Int,
        currentGeneration: Int
    ) -> Bool {
        capturedGeneration == currentGeneration
    }

    /// Whether a failed fetch should be retried (L2-201 / #1472). Only transient
    /// transport failures, 5xx, and 429 can self-heal; decoding/schema failures,
    /// non-retryable 4xx, invalid URLs, and cancellation cannot, so retrying them
    /// only multiplies work (C42 P3). Handles both `APIError` (production) and the
    /// raw `URLError`/`CancellationError` deterministic fakes throw in tests.
    /// True for every cancellation form — a raw `CancellationError`, a
    /// `URLError.cancelled`, or a cancellation WRAPPED as `APIError.networkError`
    /// (feed requests wrap URLSession errors, so a torn-down `.task`/`.refreshable`
    /// or a superseded deadline race surfaces cancellation wrapped, bypassing the
    /// raw checks). Cancellation is not a failure: callers route it to a quiet exit
    /// — no error banner, no failure telemetry — never the error path (L2-214 Item 2).
    static func isCancellation(_ error: Error) -> Bool {
        if error is CancellationError { return true }
        if let url = error as? URLError { return url.code == .cancelled }
        if let api = error as? APIError { return api.isCancellation }
        return false
    }

    static func isRetryable(_ error: Error) -> Bool {
        if error is CancellationError { return false }
        if let api = error as? APIError {
            switch api {
            case .networkError:
                return !api.isCancellation
            case .httpError(let code, _):
                return code == 429 || (500...599).contains(code)
            case .decodingError, .invalidURL:
                return false
            }
        }
        if let url = error as? URLError {
            return url.code != .cancelled
        }
        if error is DeadlineExceededError { return false }
        return false
    }

    /// Thrown when the total initial-load budget elapses before a response
    /// arrives (L2-206 Item 2). Non-retryable: the deadline is the whole-load
    /// budget, so once it fires there is no time left to retry.
    struct DeadlineExceededError: Error {}

    /// Run one bounded fetch of the offset-0 first page, cancelled at `deadline`
    /// (L2-206 Item 2). The bare fetch is only bounded by URLSession's 30/60s
    /// timeouts; racing it against the remaining budget makes the six-second
    /// deadline REAL — a suspended request is cancelled at the budget instead of
    /// hanging, and because the sleep uses the time LEFT (not a fresh per-attempt
    /// timeout) the total load can never exceed the budget across retries.
    private func fetchWithinDeadline(deadline: Date, isFirstAttempt: Bool) async throws -> DiscoverFeedFetchResult {
        let remaining = deadline.timeIntervalSinceNow
        let client = self.client
        guard remaining > 0 else {
            // Budget already spent. A RETRY reaching here must NEVER start a new
            // request — a bare `fetchDiscoverFeed` is bounded only by URLSession's
            // 30/60s timeouts, so admitting one after the deadline recreates exactly
            // the unbounded hang the total budget exists to prevent (C67 P1 /
            // L2-208 Item 2). Throw the non-retryable deadline error instead and let
            // the loop settle to last-good/error.
            //
            // Only the very FIRST attempt is admitted with a non-positive budget,
            // and solely for a degenerate/zero CONFIGURED budget that production
            // never uses (prod budget is 6s) — so the feed still makes one attempt
            // rather than refusing to load at all. It cannot multiply into many
            // requests because the loop only re-enters here on a retry, which now
            // throws.
            guard isFirstAttempt else { throw DeadlineExceededError() }
            return try await client.fetchDiscoverFeedResolvingPrincipal(
                limit: Self.firstPageLimit, offset: 0, eventPct: 0.15, cacheTTL: nil)
        }
        return try await withThrowingTaskGroup(of: DiscoverFeedFetchResult.self) { group in
            group.addTask {
                try await client.fetchDiscoverFeedResolvingPrincipal(
                    limit: Self.firstPageLimit, offset: 0, eventPct: 0.15, cacheTTL: nil)
            }
            group.addTask {
                try await Task.sleep(for: .seconds(remaining))
                throw DeadlineExceededError()
            }
            // Cancel the loser on exit: when the deadline wins, cancelAll() cancels
            // the stuck fetch (its URLSession task is cancelled); when the fetch
            // wins, it cancels the pending sleep.
            defer { group.cancelAll() }
            guard let first = try await group.next() else { throw DeadlineExceededError() }
            return first
        }
    }

    /// Rebind the feed to a NEW auth identity (login, logout, account switch, or a
    /// failed restore that drops back to anonymous) — L2-206 Item 1. The caller
    /// (DiscoverView) has already rebound `APIClient`'s cache namespace; this
    /// clears the prior identity's in-memory cards and resets load state BEFORE
    /// reloading, so another account's items are never presented under the new
    /// identity. `load()` then claims a fresh generation (superseding any in-flight
    /// load — its late response is discarded, never overwriting the new identity)
    /// and seeds the new identity's own last-good cache.
    @MainActor
    func rebindForIdentityChange() async {
        items = []
        nextOffset = 0
        hasMore = true
        isShowingCachedContent = false
        refreshFailedShowingCache = false
        lastGoodStoredAt = nil
        error = nil
        loading = true
        await load()
    }

    /// Cards the feed can actually render, admitted through ONE shared
    /// predicate (L2-201 / #1472 — C42 P1). Previously this dropped `bundle`
    /// cards even though `DiscoverView` has a full comparison-bundle render path,
    /// so feed-driven bundles were silently discarded from the initial page AND
    /// dragged the renderable count below the old fallback threshold. A bundle is
    /// admitted only when it carries at least one renderable child; an empty /
    /// all-ineligible bundle contributes no card (matching DiscoverView's bundle
    /// sanitization) and must not seed a first card or inflate the page.
    private static func renderable(_ items: [FeedItem]) -> [FeedItem] {
        items.filter(isRenderable)
    }

    static func isRenderable(_ item: FeedItem) -> Bool {
        suppressionReason(item) == nil
    }

    /// L2-215 Item 1 (#1486) — fail-closed empty-envelope classifier. Returns an
    /// identity-free machine reason when a card is an empty predictive envelope
    /// (a bare colored tile + title + Like/Share, nothing to predict), or `nil`
    /// when it carries a renderable outcome/probability OR an authoritative result.
    /// Mirrors the web `feedItemSuppressionReason` rules so both surfaces admit the
    /// same cards:
    ///  - `event`: always renderable — a real matchup + status/score, never a bare tile.
    ///  - `futures`: needs ≥1 outcome row OR a settled status; else `empty_futures`.
    ///  - `tournament`: needs ≥1 golfer OR a settled marquee result (`marquee_whathit`);
    ///    else `empty_tournament`.
    ///  - `concept`: a probability-free hub card, renderable ONLY with an authoritative
    ///    result (WHAT-HIT + a winner/summary); else `empty_concept` (the TdF / Belgian
    ///    GP class). Previously a live/upcoming concept was admitted (L2-166) — #1486
    ///    fails it closed until it can render a real outcome.
    ///  - `bundle`: needs ≥1 renderable member; else `empty_bundle`.
    ///  - unknown shape → `unknown_type`.
    static func suppressionReason(_ item: FeedItem, depth: Int = 0) -> String? {
        if item.event != nil { return nil }
        if let futures = item.futures {
            if let outcomes = futures.topOutcomes, !outcomes.isEmpty { return nil }
            if futuresIsSettled(futures) { return nil }
            return "empty_futures"
        }
        if let tournament = item.tournament {
            // Renderable on its golfer field OR — L2-224 — on an authoritative
            // settled result. The previous comment here asserted "the native
            // tournament payload carries no whathit/result field"; it does (the
            // backend sends `marquee_whathit` on every tournament card), the MODEL
            // just dropped it. Now that it decodes, this matches web exactly
            // (`feedItemSuppressionReason`, discover/utils.ts): golfers OR whathit.
            if let golfers = tournament.golfers, !golfers.isEmpty { return nil }
            if tournament.marqueeWhathit == true { return nil }
            return "empty_tournament"
        }
        if let concept = item.concept {
            // Renderable only in the post-settlement WHAT-HIT window (a "FINAL / see
            // the recap" result framing; a graded winner when present, #1219). A
            // live/upcoming concept has nothing to predict → the #1486 empty tile.
            return concept.marqueeWhathit == true ? nil : "empty_concept"
        }
        if let bundle = item.bundle {
            // Recursion backstop — bundles are not expected to nest.
            if depth > 3 { return "empty_bundle" }
            let anyRenderable = bundle.items.contains { suppressionReason($0, depth: depth + 1) == nil }
            return anyRenderable ? nil : "empty_bundle"
        }
        return "unknown_type"
    }

    /// L2-225: this used to check terminal STATUS only — one of the four authorities
    /// web's `_futuresIsSettled` consults (`discover/utils.ts`). A futures card that
    /// was settled by `resolved` / `winner` / a past `resolution_date` but still
    /// carried `status='open'` (gotcha #33, the normal Kalshi shape) was therefore
    /// classified `empty_futures` here and dropped, while web admitted it as a
    /// result-carrying card. Both surfaces now read the same shared predicate.
    private static func futuresIsSettled(_ d: FeedFuturesData) -> Bool {
        FeedLifecycle.futuresIsSettled(d)
    }

    /// Emit identity-free suppression telemetry (card type + machine reason + count,
    /// surface `discover`) for the empty predictive envelopes dropped from a fetched
    /// page. Fired only on the network publish path so a served cache seed does not
    /// double-count. Carries no ids, names, sessions, or market text (L2-215 Item 1).
    private func reportSuppressedEnvelopes(_ items: [FeedItem]) {
        var counts: [String: Int] = [:]
        for item in items {
            if let reason = Self.suppressionReason(item) {
                counts["\(item.type):\(reason)", default: 0] += 1
            }
        }
        for (key, count) in counts {
            let parts = key.split(separator: ":", maxSplits: 1).map(String.init)
            guard parts.count == 2 else { continue }
            AnalyticsService.trackFeedEnvelopeSuppressed(
                type: parts[0], reason: parts[1], count: count, surface: "discover")
        }
    }

    private static func elapsedMs(since start: Date) -> Double {
        Date().timeIntervalSince(start) * 1000
    }

    /// Advance pagination toward fresh content, always terminating in one of
    /// three honest states: new cards appended, honest exhaustion (`hasMore =
    /// false`), or a retryable `error`. Never spins on a duplicate-only or
    /// decoded-empty page (C26 P2): the offset advances by the server's page
    /// boundary even when a page yields no new IDs, so the loop can never refetch
    /// the same page forever, and a bounded scan surfaces a retry rather than an
    /// indefinite "Finding fresh markets…" spinner.
    @MainActor
    func loadMoreIfNeeded() async {
        guard hasMore, !loading, !loadingMore else { return }
        loadingMore = true
        defer { loadingMore = false }

        // Capture the active load generation BEFORE the first await (C78 Item 1).
        // Re-checked after every await below so a response that returns after an
        // identity change / refresh / superseding load never mutates the new
        // generation's paging state.
        let generation = loadGeneration

        var scans = 0
        while hasMore, scans < Self.maxPageScans {
            scans += 1

            let response: FeedResponse
            do {
                response = try await client.fetchDiscoverFeed(
                    limit: 200,
                    offset: nextOffset,
                    eventPct: 0.15,
                    cacheTTL: nil
                )
            } catch let cancel where Self.isCancellation(cancel) {
                // Raw OR wrapped cancellation — pagination was abandoned; keep
                // content, no "couldn't load more" banner, no failure event (L2-214).
                return
            } catch {
                // A response (or failure) from a superseded generation must not
                // paint an error over the new identity (C78 Item 1) — drop it
                // silently, exactly as a successful stale page is dropped below.
                guard Self.shouldApplyPaginationResult(
                    capturedGeneration: generation, currentGeneration: loadGeneration
                ) else { return }
                // Surface a retryable error instead of swallowing it into a
                // permanent progress state (C26 P2). The view offers a retry
                // control that calls back into loadMoreIfNeeded.
                print("DiscoverView loadMore error: \(error)")
                self.error = "Couldn't load more markets"
                return
            }

            // Drop a response that belongs to a superseded load generation (C78
            // Item 1): an identity change (rebindForIdentityChange → load),
            // pull-refresh, or any superseding load bumped loadGeneration while
            // this page was in flight. Appending, advancing nextOffset, flipping
            // hasMore/error, or emitting analytics here would corrupt the new
            // generation's feed — so return before ANY state mutation.
            guard Self.shouldApplyPaginationResult(
                capturedGeneration: generation, currentGeneration: loadGeneration
            ) else { return }

            // Advance by the SERVER page boundary FIRST, not the decoded item
            // count. The tolerant FeedResponse decoder silently drops malformed
            // rows (FeedModels), so `items.count` is NOT the number of server
            // slots consumed (C29 P1) — the backend paginates
            // `feed_items[offset : offset + limit]` with
            // `has_more = (offset + limit) < total`, so the next page always
            // begins at `offset + limit`. Advancing by decoded count would
            // overlap the prior server page on a partially-malformed page
            // (burning the scan budget on duplicates) or, on a
            // fully-malformed/decoded-empty page, fail to advance and falsely
            // declare exhaustion while later pages still exist.
            let pageEnd = Self.pageBoundary(response, from: nextOffset)
            let advanced = pageEnd > nextOffset
            nextOffset = pageEnd

            let loadedIds = Set(items.map(Self.itemKey))
            let fresh = response.items.filter { !loadedIds.contains(Self.itemKey($0)) }

            if !fresh.isEmpty {
                // Real new content (may be lifecycle-stale — the view's stale
                // gate filters it and, if the whole page was rot, re-triggers
                // this method because items.count changed). Either way this is a
                // terminating, honest step forward.
                items = Self.interleave(items + fresh)
                hasMore = response.hasMore
                error = nil
                return
            }

            // No new IDs this page (duplicate-only, decoded-empty, or fully
            // malformed). Only the SERVER's own signal ends the feed.
            if !response.hasMore {
                hasMore = false
                error = nil
                return
            }

            // Defensive: the server claims more but the offset could not advance
            // (a misbehaving `limit <= 0` AND a decoded-empty page). Stop rather
            // than refetch the same page forever; treat as caught-up.
            if !advanced {
                hasMore = false
                error = nil
                return
            }

            // The server claims more and the offset advanced past this page —
            // even a fully-malformed/decoded-empty page. Keep scanning FORWARD
            // (bounded by maxPageScans) toward the next server page instead of
            // falsely ending the feed on decode loss (C29 P1).
            hasMore = response.hasMore
        }

        // Exhausted the scan budget while the server still claims more but keeps
        // returning nothing new: surface a retry instead of spinning forever.
        // Still gated on the captured generation (C78 Item 1) so a supersession on
        // the final scan's await never writes a retry error over the new identity.
        if hasMore, Self.shouldApplyPaginationResult(
            capturedGeneration: generation, currentGeneration: loadGeneration
        ) {
            self.error = "Couldn't find fresh markets"
        }
    }

    /// The offset the NEXT server page begins at, given a decoded response and
    /// the current monotonic offset floor (C29 P1). The server page boundary is
    /// `response.offset + response.limit` — the contract the backend paginates on
    /// (`feed_items[offset : offset + limit]`). Decoded item count is used only
    /// as a floor so a misbehaving server that under-reports `limit` still can't
    /// stall behind a nonempty decoded page, and the result never regresses below
    /// the current offset (monotonic guarantee).
    private static func pageBoundary(_ response: FeedResponse, from currentOffset: Int) -> Int {
        let serverPageEnd = response.offset + response.limit
        let decodedPageEnd = response.offset + response.items.count
        return max(currentOffset, serverPageEnd, decodedPageEnd)
    }

    /// Page-merge interleave (L2-202): delegates to the shared linear-traversal
    /// core so the O(n²) `removeFirst()` drain is gone here and in the view's two
    /// interleave paths, with byte-for-byte identical order. This call site keeps
    /// its historical lack of a small-input guard — the core handles 0/1/2 items
    /// the same way the old inline loop did.
    private static func interleave(_ items: [FeedItem]) -> [FeedItem] {
        FeedInterleave.byCategory(items, sportsCategories: sportsCategories, category: category(for:))
    }

    private static func category(for item: FeedItem) -> String {
        if let f = item.futures { return f.llmSportCategory?.lowercased() ?? "other" }
        if let e = item.event { return e.sport?.split(separator: "_").first.map(String.init) ?? "other" }
        if let c = item.concept { return c.domain?.lowercased() ?? "other" }
        return "other"
    }

    private static func itemKey(_ item: FeedItem) -> String {
        if let event = item.event { return "event-\(event.id)" }
        if let futures = item.futures { return "futures-\(futures.id)" }
        // Bundles dedup on their stable bundle id so a comparison card cannot
        // duplicate across pages (matches DiscoverView's key) — L2-201 / #1472.
        if let bundle = item.bundle { return "bundle-\(bundle.id)" }
        // tournament/concept fall through to FeedItem.id ("tournament-<key>" /
        // "concept-<key>"), which is already stable and unique.
        return item.id
    }
}

// MARK: - Production feed-fetch conformance

extension APIClient: DiscoverFeedProviding {
    /// Thin adapter mapping the narrow Discover pagination seam onto the full
    /// feed surface (L2-192). The offset-0 page routes through
    /// `fetchFeedPersistingLastGood` so its raw body is cached as last-good for
    /// the next launch (#1465); pagination pages stay transient. Production
    /// behavior is otherwise identical, and tests inject a deterministic fake.
    nonisolated func fetchDiscoverFeed(
        limit: Int,
        offset: Int,
        eventPct: Double?,
        cacheTTL: TimeInterval?
    ) async throws -> FeedResponse {
        try await fetchFeedPersistingLastGood(
            limit: limit, offset: offset, eventPct: eventPct, cacheTTL: cacheTTL).response
    }

    /// Principal-resolving initial fetch (L2-210 Item 1 / C72): returns the decoded
    /// page plus the real request/namespace principal signals so the view model can
    /// gate publication. The offset-0 persist path already computes both; pagination
    /// offsets report the neutral publish-always pair.
    nonisolated func fetchDiscoverFeedResolvingPrincipal(
        limit: Int,
        offset: Int,
        eventPct: Double?,
        cacheTTL: TimeInterval?
    ) async throws -> DiscoverFeedFetchResult {
        try await fetchFeedPersistingLastGood(
            limit: limit, offset: offset, eventPct: eventPct, cacheTTL: cacheTTL)
    }

    /// The current opaque feed principal (L2-212 Item 1 / C76): resolved on the
    /// actor so a mid-flight identity change is reflected at publication time.
    nonisolated func currentFeedPrincipal() async -> String {
        await resolvedFeedIdentity()
    }

    /// The optimistic-seed admission context for the current identity (L2-212 Item 1
    /// / C76): signed-in-ness of the current namespace plus whether a stored session
    /// credential is eligible for restore.
    nonisolated func optimisticSeedContext() async -> DiscoverOptimisticSeedContext {
        await resolvedOptimisticSeedContext()
    }
}

// MARK: - Last-good read conformance (#1465)

extension APIClient: DiscoverLastGoodReading {}
