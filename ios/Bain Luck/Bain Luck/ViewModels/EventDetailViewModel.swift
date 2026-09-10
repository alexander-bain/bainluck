import Combine
import os
import SwiftUI

private let logger = Logger(subsystem: "com.bainluck", category: "eventDetail")

/// The six fetches an event page makes, as a seam.
///
/// Same reason as `DiscoverFeedProviding`: the lifecycle this view model runs —
/// when a scheduled page starts polling, what a delivering stream does to that
/// poll, whether a status flip is ever noticed — is not reachable from a test
/// that has to make six real requests. Declared here and conformed at the foot
/// of this file so `APIClient.swift` (latency's) is not touched.
protocol EventDetailProviding: Sendable {
    func fetchEvent(id: Int) async throws -> EventDetail
    func fetchEventHistory(id: Int, hours: Int) async throws -> EventHistoryResponse
    func fetchRelatedFutures(eventId: Int) async throws -> RelatedFuturesResponse
    func fetchTeamProgression(eventId: Int) async throws -> TeamProgressionResponse
    func fetchGameMarkets(eventId: Int) async throws -> GameMarketsResponse
    func fetchLineMovement(eventId: Int) async throws -> LineMovementResponse
}

final class EventDetailViewModel: ObservableObject {
    @Published private(set) var event: EventDetail?
    @Published private(set) var loading = true
    @Published private(set) var error: String?
    @Published private(set) var history: EventHistoryResponse?
    @Published private(set) var relatedFutures: RelatedFuturesResponse?
    @Published private(set) var teamProgression: TeamProgressionResponse?
    @Published private(set) var gameMarkets: GameMarketsResponse?
    @Published private(set) var lineMovement: LineMovementResponse?
    /// When the last `load()` actually completed. Drives the refresh-countdown
    /// chrome from real request completion instead of a self-resetting timer that
    /// fakes a refresh cycle no request performs (C43 P2). `nil` until first load.
    @Published private(set) var lastLoadedAt: Date?

    private var refreshTask: Task<Void, Never>?
    /// The cadence the installed `refreshTask` is running at, so a `load()` that
    /// changes nothing does not cancel and re-create the loop it is running
    /// inside. `nil` whenever no task is installed.
    private var installedPlan: EventRefreshPlan?
    let eventId: Int

    // MARK: - Live push (#2687)

    /// True only while the SSE stream is DELIVERING — which is not the same as
    /// "a socket is open". The poll is gated on this, and every failure mode
    /// this can express ends with it false, so a dead push degrades to polling
    /// and never to a frozen number.
    @Published private(set) var streamDelivering = false

    private var stream: LiveStreamController?
    private var streamTickTask: Task<Void, Never>?
    /// Injected so tests can drive the lifecycle without a socket. `nil` means
    /// the real `URLSession` transport.
    private let makeStreamHandle: (@MainActor (Int) throws -> LiveStreamHandle)?
    private let now: () -> TimeInterval

    /// Whether a periodic auto-refresh request is currently installed, and at
    /// what cadence. A FINISHED page installs nothing; every other state polls,
    /// at a rate `EventRefreshPlan` chooses — see that file for why a scheduled
    /// page has to.
    ///
    /// This says nothing about chrome. `EventDetailView` gates its refresh ring
    /// on its own `isLive`, so a scheduled page polling quietly in the
    /// background does not start claiming a countdown at the reader.
    var isAutoRefreshing: Bool { refreshTask != nil }
    var currentRefreshPlan: EventRefreshPlan? { installedPlan }

    private let client: EventDetailProviding

    /// Injected so a test can run the poll loop without waiting for it. Returns
    /// the interval it was asked to wait, which is what makes the CADENCE — not
    /// merely the fact of a poll — assertable.
    private let sleep: @Sendable (TimeInterval) async -> Void

    init(
        eventId: Int,
        client: EventDetailProviding = APIClient.shared,
        makeStreamHandle: (@MainActor (Int) throws -> LiveStreamHandle)? = nil,
        now: @escaping () -> TimeInterval = { Date().timeIntervalSince1970 },
        sleep: (@Sendable (TimeInterval) async -> Void)? = nil
    ) {
        self.eventId = eventId
        self.client = client
        self.makeStreamHandle = makeStreamHandle
        self.now = now
        self.sleep = sleep ?? { seconds in
            try? await Task.sleep(nanoseconds: UInt64(seconds * 1_000_000_000))
        }
    }

    @MainActor
    func load() async {
        loading = event == nil

        // Start secondary fetches immediately (they only need eventId)
        let client = self.client
        let historyTask = Task { () -> EventHistoryResponse? in
            do { return try await client.fetchEventHistory(id: eventId, hours: 168) }
            catch { logger.error("History fetch failed for \(self.eventId): \(error)"); return nil }
        }
        let relatedFuturesTask = Task { () -> RelatedFuturesResponse? in
            do { return try await client.fetchRelatedFutures(eventId: eventId) }
            catch { logger.error("Related futures failed for \(self.eventId): \(error)"); return nil }
        }
        let progressionTask = Task { () -> TeamProgressionResponse? in
            do { return try await client.fetchTeamProgression(eventId: eventId) }
            catch { logger.error("Team progression failed for \(self.eventId): \(error)"); return nil }
        }
        let gameMarketsTask = Task { () -> GameMarketsResponse? in
            do { return try await client.fetchGameMarkets(eventId: eventId) }
            catch { logger.error("Game markets failed for \(self.eventId): \(error)"); return nil }
        }
        let lineMovementTask = Task { () -> LineMovementResponse? in
            do { return try await client.fetchLineMovement(eventId: eventId) }
            catch { logger.error("Line movement failed for \(self.eventId): \(error)"); return nil }
        }

        // Await primary fetch (controls loading state)
        do {
            event = try await client.fetchEvent(id: eventId)
            error = nil
        } catch {
            self.error = error.localizedDescription
            logger.error("Failed to load event \(self.eventId): \(error)")
        }

        // Unblock the page — render with whatever secondary data is already available
        loading = false
        configureAutoRefresh()

        // Await secondary fetches — only update if successful AND non-empty
        // (preserve existing data when a refresh returns nil or empty results)
        if let h = await historyTask.value {
            history = h
        }
        if let related = await relatedFuturesTask.value {
            if relatedFutures == nil || related.homeTeamFutures != nil || related.awayTeamFutures != nil || related.sharedFutures != nil || related.boxScore != nil {
                relatedFutures = related
            }
        }
        if let progression = await progressionTask.value {
            if teamProgression == nil || progression.homeTeam != nil || progression.awayTeam != nil {
                teamProgression = progression
            }
        }
        if let markets = await gameMarketsTask.value {
            let hasContent = (markets.playerProps != nil && !(markets.playerProps?.isEmpty ?? true))
                || (markets.spreads != nil && !(markets.spreads?.isEmpty ?? true))
                || (markets.totals != nil && !(markets.totals?.isEmpty ?? true))
                || (markets.other != nil && !(markets.other?.isEmpty ?? true))
            if gameMarkets == nil || hasContent {
                gameMarkets = markets
            }
        }
        if let movement = await lineMovementTask.value {
            lineMovement = movement
        }

        // Stamp the honest "last updated" moment — this load has completed. The
        // refresh countdown counts down from here to the next scheduled auto-refresh.
        lastLoadedAt = Date()
    }

    @MainActor
    private func configureAutoRefresh() {
        // The push stream stays a LIVE-only affair, exactly as the #2687 ruling
        // left it: a scheduled page now polls, but it does not open a socket to
        // wait for a match that has not started.
        if event?.status == "live" {
            startStreamIfNeeded()
        } else {
            stopStream()
        }

        // Decided AFTER the socket work, never before it: `stopStream()` clears
        // `streamDelivering`, and that is an input. Reading it first would let a
        // page that just lost its stream keep the slow push cadence.
        let plan = EventRefreshPlan.decide(
            status: event?.status,
            streamDelivering: streamDelivering,
            commenceTime: event?.commenceTime?.asDate,
            now: Date(timeIntervalSince1970: now())
        )

        guard case .poll(let interval) = plan else {
            refreshTask?.cancel()
            refreshTask = nil
            installedPlan = nil
            return
        }

        // IDEMPOTENT. `load()` calls this, and the poll loop calls `load()`, so
        // an unconditional cancel here would have every cycle cancel the very
        // task it is running inside and build a new one. Leaving an unchanged
        // plan alone also means the interval a running loop is sleeping on is
        // always the interval its plan names.
        if installedPlan == plan, refreshTask != nil { return }

        refreshTask?.cancel()
        // A `@MainActor` Task loop rather than a `Timer`, for the same reason as
        // the tick loop below: this method is main-actor isolated, and a
        // `Timer`'s `@Sendable` block cannot reach a non-Sendable view model
        // across that boundary without the compiler saying so.
        //
        // The gap is measured BETWEEN loads rather than on the wall clock, so a
        // six-endpoint refresh that takes longer than the interval on a slow
        // network never stacks a second one on top of itself.
        let wait = sleep
        refreshTask = Task { @MainActor [weak self] in
            while !Task.isCancelled {
                await wait(interval)
                guard !Task.isCancelled, let self else { return }
                await self.load()
            }
        }
        installedPlan = plan
    }

    @MainActor
    func stopRefresh() {
        refreshTask?.cancel()
        refreshTask = nil
        // Cleared with the task it describes. Leaving it set would have
        // `currentRefreshPlan` name a cadence nothing is running at, and the
        // idempotence check above read a stale plan on the way back in.
        installedPlan = nil
        stopStream()
    }

    // MARK: - Live push

    @MainActor
    private func startStreamIfNeeded() {
        guard stream == nil else { return }
        let id = eventId
        let make = makeStreamHandle
        let controller = LiveStreamController(
            open: {
                if let make { return try make(id) }
                let transport = try LiveEventStreamTransport(eventId: id)
                transport.connect()
                return transport
            },
            now: now,
            onFrame: { [weak self] frame in self?.apply(frame) },
            onDeliveringChange: { [weak self] delivering in
                guard let self else { return }
                self.streamDelivering = delivering
                // Re-decide the poll on every transition, in BOTH directions.
                // Only reacting to the good one would leave the page frozen the
                // first time a stream went quiet.
                self.configureAutoRefresh()
            }
        )
        stream = controller
        controller.start()
        // The controller's clock is driven, not ambient — see its own note. The
        // owner is what advances it.
        //
        // A `@MainActor` Task loop rather than a `Timer`: the controller is main-
        // actor isolated, so a `Timer`'s `@Sendable` block cannot reach it without
        // crossing an isolation boundary it has no business crossing (and the
        // compiler says so). This stays on one actor from end to end.
        streamTickTask = Task { @MainActor [weak self] in
            while !Task.isCancelled {
                try? await Task.sleep(
                    nanoseconds: UInt64(LiveStreamTiming.tickInterval * 1_000_000_000)
                )
                guard !Task.isCancelled, let self, let stream = self.stream else { return }
                stream.tick()
            }
        }
    }

    @MainActor
    private func stopStream() {
        streamTickTask?.cancel()
        streamTickTask = nil
        stream?.stop()
        stream = nil
        streamDelivering = false
    }

    /// Write a pushed price into the model the page already reads.
    ///
    /// The same choice web made: the stream writes the SAME place the poll
    /// writes, so the hero, the chart header and every other consumer stay
    /// consistent and nothing downstream needs to know push exists.
    @MainActor
    private func apply(_ frame: LiveStreamFrame) {
        guard var current = event, current.id == frame.eventId else { return }

        if let p = frame.p, var odds = current.currentOdds {
            odds.homeProbability = p
            // Derived, exactly as the feed derives it, which is what makes the
            // pair an exact complement — and therefore what the duel contract
            // is written for.
            odds.awayProbability = 1 - p
            // CLEARED TOGETHER. The served pair describes the `current_odds`
            // this payload arrived with; a pushed price is not that payload, so
            // keeping either would print a stale whole percent over a fresh
            // probability. Both nil means every reader falls back WHOLE to
            // `renderedDuelPercents`, which is the rule `duelPercents` states.
            odds.homeRenderedPercent = nil
            odds.awayRenderedPercent = nil
            current.currentOdds = odds
        }

        // A frame whose status has left the live set is the server telling us
        // the match ended; the controller closes on the `closed` event that
        // follows, and the status must not stay "live" underneath it.
        if let status = frame.status { current.status = status }

        event = current
        // NOT `lastLoadedAt`: that field means "a load completed" and drives the
        // refresh countdown chrome. A pushed frame is not a load, and claiming
        // one would make the countdown describe a request that never happened
        // — the exact fiction C43 P2 removed.
    }
}

// MARK: - Production event-fetch conformance

/// The real transport. Every method already exists on the actor with these
/// signatures, so this is a declaration of conformance and nothing else — there
/// is no adapter here to drift from what production does. Kept in this file
/// rather than in `APIClient.swift` so the seam does not edit latency's file.
extension APIClient: EventDetailProviding {}
