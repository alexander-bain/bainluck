import Combine
import Foundation
import os

private let logger = Logger(subsystem: "com.bainluck", category: "mystuff")

/// Narrow fetch seam for the native **My Stuff** tab (L2-217 / C88) so the
/// view model's identity and progressive-publication contract can be driven by
/// deterministic fakes. `APIClient` conforms via the extension at the bottom of
/// this file; the default init arg keeps production wiring unchanged.
///
/// My Stuff issues exactly two requests and they are NOT equal:
/// - the team feed is **REQUIRED** — it produces the first team card;
/// - team futures ("Your Teams' Probabilities") is **OPTIONAL** — a supplemental
///   section that must never gate the card above it.
protocol MyStuffFeedProviding: Sendable {
    /// The required team-only feed (`my_teams_only=true`, events only).
    nonisolated func fetchMyTeamsFeed() async throws -> FeedResponse
    /// Optional team futures; non-fatal.
    nonisolated func fetchMyTeamFuturesSection(limit: Int) async throws -> TeamFuturesResponse
    /// The CURRENT opaque principal (`user:<id>` or `anon:<session>`), resolved at
    /// the moment of the call. Read immediately before publication so a response
    /// binds to the EXACT dispatch identity rather than a signed-in Boolean, which
    /// would let one authenticated account's data paint over another's.
    nonisolated func currentMyStuffPrincipal() async -> String
}

extension MyStuffFeedProviding {
    /// Default: the neutral empty principal, so `principalAtDispatch ==
    /// currentPrincipal` holds for principal-agnostic fakes and the gate stays
    /// publish-always — behaviorally identical for tests that only model requests.
    nonisolated func currentMyStuffPrincipal() async -> String { "" }
}

@MainActor
final class MyStuffViewModel: ObservableObject {
    @Published private(set) var items: [FeedItem] = []
    @Published private(set) var teamFutures: TeamFuturesResponse?
    @Published private(set) var loading = true
    @Published private(set) var error: String?

    /// Immutable snapshot of the required-feed generation that FIRST became
    /// renderable this load (L2-217 Item 2 / C88). Stamped once at data-ready and
    /// frozen, so the on-screen first-render event describes the generation that
    /// actually produced first paint — not whatever the live model reads after the
    /// optional futures merge. `@Published` so the view's generation-keyed
    /// `onChange` acknowledgement fires even when a same-id refresh retains rows
    /// (SwiftUI does not re-run `onAppear` for retained IDs). Nil for an empty
    /// required response, so an empty success emits no first-card time.
    @Published private(set) var firstRenderGeneration: MyStuffRenderGeneration?

    private var refreshTimer: Timer?

    private let client: MyStuffFeedProviding
    private let telemetry: (@Sendable (MyStuffLoadStage) -> Void)?
    private let clock: @Sendable () -> Date
    private let autoRefreshEnabled: Bool

    /// Wall-clock bound on the OPTIONAL futures request (L2-217 Item 2). The load
    /// never awaits it — it is merged whenever it lands — but a sibling that
    /// ignores cancellation must not linger forever, so it is abandoned at the
    /// deadline. Injectable so tests drive the hung path without real time.
    private let optionalDeadline: TimeInterval

    /// Retry budget for the REQUIRED feed. Preserved from #240 Item 3: a single
    /// transient blip on the cold load used to surface as an unrecoverable
    /// first-load failure while Discover already retried.
    private let requiredAttempts: Int
    private let retryBackoff: TimeInterval

    /// The single owned load task. Every entry point — the view's `.task`,
    /// pull-to-refresh, and the live auto-refresh timer — routes through
    /// `startLoad()`, which cancels AND joins the prior task before installing its
    /// replacement, so at most one owned load ever runs and a superseded load's
    /// work is actually terminated rather than merely discarded at publication.
    private var loadTask: Task<Void, Never>?
    /// The current load's in-flight optional task, held so a supersession or a
    /// view disappearance can cancel it (it is unstructured, so cancellation must
    /// be explicit).
    private var optionalTask: Task<Void, Never>?
    /// Set by `viewDidStop()` so a refresh-timer callback already queued at the
    /// moment the view disappeared cannot start a fresh load after teardown.
    private var isStopped = false

    /// Monotonic load identity. Each `load()` claims the next value; a load
    /// superseded by a newer one (navigation, refresh, auth change) discards its
    /// late responses instead of overwriting the current session's state.
    private var loadGeneration = 0

    init(
        client: MyStuffFeedProviding = APIClient.shared,
        telemetry: (@Sendable (MyStuffLoadStage) -> Void)? = { AnalyticsService.trackMyStuffStage($0) },
        clock: @escaping @Sendable () -> Date = { Date() },
        autoRefreshEnabled: Bool = true,
        optionalDeadline: TimeInterval = 10,
        requiredAttempts: Int = 3,
        retryBackoff: TimeInterval = 1.5
    ) {
        self.client = client
        self.telemetry = telemetry
        self.clock = clock
        self.autoRefreshEnabled = autoRefreshEnabled
        self.optionalDeadline = optionalDeadline
        self.requiredAttempts = requiredAttempts
        self.retryBackoff = retryBackoff
    }

    var liveNow: [FeedItem] {
        items.filter { $0.event?.status == "live" }
    }

    var justHappened: [FeedItem] {
        items.filter {
            let s = $0.event?.status
            return s == "completed" || s == "closed"
        }
    }

    var upcoming: [FeedItem] {
        items.filter {
            guard $0.type == "event" else { return false }
            let s = $0.event?.status
            return s == "scheduled" || s == nil
        }
    }

    var topMarkets: [FeedItem] {
        items.filter { $0.type == "futures" }
    }

    var hasLiveGames: Bool { !liveNow.isEmpty }

    /// True while a live-game auto-refresh timer is armed. Observable so a test can
    /// prove refresh is armed right after the required publish, even while the
    /// optional futures request is still hung.
    private(set) var refreshArmed = false

    // MARK: - Owned load rail

    /// The single owned-load entry point. Cancels the prior owned load and installs
    /// this one as the sole owner; the replacement JOINS the prior (awaits its
    /// termination) before running its body, so at most one load executes at a time.
    func startLoad() async {
        // A refresh-timer callback queued just as the view disappeared must not
        // resurrect a load after teardown.
        guard !isStopped else { return }
        let prior = loadTask
        prior?.cancel()
        // NOTE: no `await` between reading `loadTask` and reassigning it — the
        // synchronous region is atomic on the main actor, so rapid re-entry can
        // never strand a newer owner. The join happens INSIDE the new task.
        let task = Task { @MainActor [weak self] in
            await prior?.value
            guard let self, !Task.isCancelled else { return }
            await self.load()
        }
        loadTask = task
        await task.value
    }

    /// Called by the owning view on (re)appearance so a load can begin again after
    /// a prior `viewDidStop()` (navigation away, then back).
    func viewDidStart() {
        isStopped = false
    }

    /// Called when the owning view disappears. Terminates the owned load and its
    /// optional sibling — cancellation is real, not just a discard — stops the
    /// refresh timer, and invalidates the current generation as the publication
    /// backstop so a request that outraces cancellation can no longer mutate
    /// published state after the tab closes.
    func viewDidStop() {
        isStopped = true
        loadGeneration &+= 1
        loadTask?.cancel()
        loadTask = nil
        optionalTask?.cancel()
        optionalTask = nil
        stopRefresh()
    }

    /// Called by the owning view when the signed-in account changes. Invalidates the
    /// current generation and clears published state IMMEDIATELY, so the previous
    /// account's team cards never survive into the new account's session even for a
    /// frame — then the caller starts a fresh load under the new principal.
    func resetForIdentityChange() {
        loadGeneration &+= 1
        loadTask?.cancel()
        loadTask = nil
        optionalTask?.cancel()
        optionalTask = nil
        stopRefresh()
        items = []
        teamFutures = nil
        error = nil
        firstRenderGeneration = nil
        loading = true
    }

    // MARK: - Load

    func load() async {
        // Terminate any optional sibling still in flight from a prior load body.
        optionalTask?.cancel()
        optionalTask = nil

        loadGeneration &+= 1
        let generation = loadGeneration
        let isInitial = items.isEmpty
        if isInitial { loading = true }
        let loadStart = clock()
        let client = self.client

        // Resolve the dispatch principal BEFORE the request leaves, so publication
        // can bind the response to the exact identity that asked for it.
        let principalAtDispatch = await client.currentMyStuffPrincipal()
        guard generation == loadGeneration else { return }
        let authReadyMs = elapsedMs(since: loadStart)

        // === REQUIRED: the team feed. This alone gates the first card. ===
        let netStart = clock()
        var attempt = 0
        var published = false
        while attempt < max(1, requiredAttempts) {
            attempt += 1
            do {
                let feed = try await client.fetchMyTeamsFeed()
                guard generation == loadGeneration else { return }

                // Publication authority (L2-217 Item 2 / C88): an exact
                // dispatch-vs-current principal compare, so an A→B switch, a
                // logout, or a sign-in mid-flight discards this response instead
                // of painting one account's teams under another.
                let currentPrincipal = await client.currentMyStuffPrincipal()
                guard generation == loadGeneration else { return }
                guard MyStuffFirstRender.shouldPublish(
                    principalAtDispatch: principalAtDispatch,
                    currentPrincipal: currentPrincipal,
                    dispatchGeneration: generation,
                    currentGeneration: loadGeneration
                ) else {
                    emit(
                        .requiredDataReady, authReadyMs: authReadyMs, netStart: netStart,
                        loadStart: loadStart, count: 0,
                        outcome: MyStuffFirstRender.rejectionOutcome(
                            principalAtDispatch: principalAtDispatch,
                            currentPrincipal: currentPrincipal))
                    logger.debug("My Stuff response discarded — identity or generation changed")
                    return
                }

                items = feed.items
                error = nil
                // The first card is on screen the moment the REQUIRED data lands —
                // it is never held behind the optional futures request below.
                loading = false
                published = true

                // Freeze the render token before any optional merge can change the
                // live count. An empty required response leaves it nil, so an
                // empty-but-successful load emits no on-screen first-card event.
                if !items.isEmpty {
                    firstRenderGeneration = MyStuffRenderGeneration(
                        generation: generation,
                        startedAt: loadStart,
                        provenance: "network",
                        itemCount: items.count
                    )
                }

                emit(
                    .requiredDataReady, authReadyMs: authReadyMs, netStart: netStart,
                    loadStart: loadStart, count: items.count,
                    outcome: items.isEmpty
                        ? .emptySuccess
                        : (attempt > 1 ? .retrySuccess : .networkSuccess))

                // Arm auto-refresh immediately after the required publish: a live
                // game must have a refresh timer even while the optional futures
                // request is still in flight.
                configureAutoRefresh()
                logger.info("My Stuff required feed loaded: \(self.items.count) items")
                break
            } catch let error where DiscoverViewModel.isCancellation(error) {
                // Cancellation (view teardown, superseded load, auth change) is not
                // a failure: exit quietly — no error banner, no failure telemetry.
                // Resolve the skeleton first so a cancelled cold load never leaves
                // a spinner up.
                if isInitial { loading = false }
                emit(
                    .requiredDataReady, authReadyMs: authReadyMs, netStart: netStart,
                    loadStart: loadStart, count: items.count, outcome: .cancelled)
                logger.debug("My Stuff feed load cancelled")
                return
            } catch {
                guard generation == loadGeneration else { return }
                logger.error("My Stuff feed error (attempt \(attempt)/\(self.requiredAttempts)): \(error)")
                if attempt < max(1, requiredAttempts) {
                    try? await Task.sleep(for: .seconds(retryBackoff))
                    guard generation == loadGeneration else { return }
                    continue
                }
                loading = false
                // Cold load with nothing on screen → the honest error state. A
                // refresh failure keeps existing cards rather than blanking them.
                if isInitial { self.error = error.localizedDescription }
                emit(
                    .requiredDataReady, authReadyMs: authReadyMs, netStart: netStart,
                    loadStart: loadStart, count: items.count, outcome: .requiredFailure)
                return
            }
        }
        guard published, generation == loadGeneration else { return }

        // === OPTIONAL: team futures. Merged when it lands; never awaited. ===
        // The load body returns here, so a hung or failing futures request cannot
        // hold the first team card, the skeleton, or the owned-load rail. The task
        // is tracked so a supersession or a view disappearance cancels it, and it
        // is abandoned at a wall-clock deadline in case it ignores cancellation.
        let optionalStart = clock()
        let deadline = optionalDeadline
        // A merge channel + unstructured fetch, NOT a structured `withTaskGroup`: a
        // group awaits ALL children on scope exit, so one sibling that ignores
        // cancellation would keep this task — and the deadline itself — alive
        // forever, which is exactly the hang this item exists to prevent. The
        // channel lets the deadline close the wait while the runaway request is
        // simply abandoned (a late `deliver` after `close()` is dropped), with the
        // generation + principal guard as the second backstop. `SportsSiblingMerge`
        // is a plain generic mailbox; it is shared rather than duplicated here.
        let merge = SportsSiblingMerge<TeamFuturesResponse?>()
        let fetchTask = Task { [merge] in
            merge.deliver(try? await client.fetchMyTeamFuturesSection(limit: 100))
        }
        let deadlineTask = Task { [merge] in
            try? await Task.sleep(for: .seconds(max(0, deadline)))
            merge.close()
        }
        optionalTask = Task { @MainActor [weak self] in
            let response = await withTaskCancellationHandler {
                await merge.next() ?? nil
            } onCancel: {
                fetchTask.cancel()
                merge.close()
            }
            deadlineTask.cancel()
            guard let self, !Task.isCancelled else {
                fetchTask.cancel()
                return
            }
            await self.applyOptionalFutures(
                response, generation: generation, principalAtDispatch: principalAtDispatch,
                authReadyMs: authReadyMs, optionalStart: optionalStart, loadStart: loadStart)
        }
    }

    /// Merge the optional team futures, if this load still owns the screen and the
    /// identity has not changed. A miss is reported honestly (`partial_success`)
    /// and leaves the already-published team feed completely intact — the required
    /// first card is never retracted because a supplemental section failed.
    private func applyOptionalFutures(
        _ response: TeamFuturesResponse?,
        generation: Int,
        principalAtDispatch: String,
        authReadyMs: Double,
        optionalStart: Date,
        loadStart: Date
    ) async {
        guard generation == loadGeneration else { return }
        let currentPrincipal = await client.currentMyStuffPrincipal()
        guard generation == loadGeneration else { return }
        guard MyStuffFirstRender.shouldPublish(
            principalAtDispatch: principalAtDispatch,
            currentPrincipal: currentPrincipal,
            dispatchGeneration: generation,
            currentGeneration: loadGeneration
        ) else { return }

        if let response {
            teamFutures = response
            emit(
                .optionalMerge, authReadyMs: authReadyMs, netStart: optionalStart,
                loadStart: loadStart, count: response.items.count, outcome: .networkSuccess)
        } else {
            emit(
                .optionalMerge, authReadyMs: authReadyMs, netStart: optionalStart,
                loadStart: loadStart, count: teamFutures?.items.count ?? 0,
                outcome: .partialSuccess)
        }
    }

    private func elapsedMs(since start: Date) -> Double {
        max(0, clock().timeIntervalSince(start) * 1000)
    }

    private func emit(
        _ kind: MyStuffLoadStage.Kind,
        authReadyMs: Double,
        netStart: Date,
        loadStart: Date,
        count: Int,
        outcome: MyStuffOutcomeClass
    ) {
        guard let telemetry else { return }
        telemetry(
            MyStuffLoadStage(
                kind: kind,
                authReadyMs: authReadyMs,
                networkMs: elapsedMs(since: netStart),
                requiredDataReadyMs: elapsedMs(since: loadStart),
                itemCount: count,
                // The exact-principal in-memory response cache lives in APIClient and
                // is not visible from here; report it as unknown rather than guessing.
                cacheOutcome: "unknown",
                cacheAgeSeconds: -1,
                outcomeClass: outcome
            )
        )
    }

    private func configureAutoRefresh() {
        guard autoRefreshEnabled else { return }
        refreshTimer?.invalidate()
        guard hasLiveGames else { refreshArmed = false; return }
        refreshTimer = Timer.scheduledTimer(withTimeInterval: 15, repeats: true) { [weak self] _ in
            guard let self else { return }
            // Route the timer through the single owned rail: the refresh supersedes
            // (cancels + joins) any prior owned load rather than overlapping it.
            Task { @MainActor in
                await self.startLoad()
            }
        }
        refreshArmed = true
    }

    func stopRefresh() {
        refreshTimer?.invalidate()
        refreshTimer = nil
        refreshArmed = false
    }
}

// MARK: - Production fetch conformance

extension APIClient: MyStuffFeedProviding {
    /// The required team-only feed. Unchanged request shape — events only, with
    /// futures handled by the separate optional section.
    nonisolated func fetchMyTeamsFeed() async throws -> FeedResponse {
        try await fetchFeed(myTeamsOnly: true, includeFutures: false)
    }

    /// The optional team-futures section. Goes through the same principal-
    /// partitioned in-memory response cache as before (C78 Item 2) — this queue
    /// changes no cache policy or TTL.
    nonisolated func fetchMyTeamFuturesSection(limit: Int) async throws -> TeamFuturesResponse {
        try await fetchMyTeamFutures(limit: limit)
    }

    /// The current opaque principal, resolved on the actor. Reuses the same
    /// namespace the response cache and the Discover publication gate use, so all
    /// three agree on who the viewer is.
    nonisolated func currentMyStuffPrincipal() async -> String {
        await resolvedFeedIdentity()
    }
}
