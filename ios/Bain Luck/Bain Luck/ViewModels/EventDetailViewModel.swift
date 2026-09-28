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
    func fetchFreshEvent(id: Int) async throws -> EventDetail
    func fetchFreshEventHistory(id: Int, hours: Int) async throws -> EventHistoryResponse
    func fetchRelatedFutures(eventId: Int) async throws -> RelatedFuturesResponse
    func fetchTeamProgression(eventId: Int) async throws -> TeamProgressionResponse
    func fetchGameMarkets(eventId: Int) async throws -> GameMarketsResponse
    func fetchLineMovement(eventId: Int) async throws -> LineMovementResponse
}

// Existing in-memory providers have no response cache. APIClient implements
// these explicitly so the production revision path cannot reuse warm TTL data.
extension EventDetailProviding {
    func fetchFreshEvent(id: Int) async throws -> EventDetail { try await fetchEvent(id: id) }
    func fetchFreshEventHistory(id: Int, hours: Int) async throws -> EventHistoryResponse {
        try await fetchEventHistory(id: id, hours: hours)
    }
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
    /// Accepted price receipt; socket state and load completion never manufacture one.
    @Published private(set) var priceActivity: LivePriceActivity?

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

    /// #8320 — whether a live frame or its authoritative folded-price reread
    /// has put a PRICE on this page since the stream last started delivering.
    ///
    /// `streamDelivering` turns true on the stream's `open` event, before any
    /// price has arrived — rightly for the poll, which it stands down, because
    /// a stream that has just opened has not failed to deliver yet. It is not
    /// evidence for a reader: native/319 photographed the green dot for up to
    /// 90 seconds on an opened stream with no prices. So the dot reads this as
    /// well. It is set only where an accepted live update reaches the hero, and
    /// cleared on every fall back to polling, so a rollover or a quiet market
    /// has to push again before the page says it is being pushed to.
    @Published private(set) var streamHasPushedPrice = false

    /// #8320: a successful stream-triggered authoritative fold read also
    /// delivers a price. Socket open / cached unchanged reads do not.
    private var deliveryGeneration = 0
    private var streamRefetchGeneration: Int?

    /// A failed authoritative pair is a delivery failure even if SSE stays open.
    /// Separate from the full-load error: a successful game-state read cannot
    /// certify that both price payloads recovered.
    @Published private(set) var pricePairRefreshFailed = false

    var liveUpdateStatus: LiveUpdateStatus {
        if pricePairRefreshFailed && event?.status == "live" { return .interrupted }
        return LiveUpdateStatus.decide(status: event?.status, delivering: streamDelivering,
                                acceptedUpdate: streamHasPushedPrice,
                                refreshFailed: error != nil)
    }

    /// Every pushed blend this page has been given, at its stamped time (#920).
    ///
    /// The chart's right edge is drawn from this. Without it the stream reaches
    /// the hero and stops: `apply` writes `currentOdds`, and the match chart
    /// reads history, so the better the push path worked the further the two
    /// numbers on one screen drifted apart.
    ///
    /// Published rather than handed straight to the chart so it survives the
    /// view being re-created, which is the half of this bug that bit hardest.
    @Published private(set) var liveBlend: [LiveBlendPoint] = []

    /// #8541 — the stream has said the match is over and the server has not yet
    /// served a finished payload.
    ///
    /// A pushed frame carries a status but no score. Before this, the frame that
    /// ended the match set the status, `closed` stopped the stream, and a finished
    /// status plans `.idle` — so the page never asked again and printed FINAL over
    /// whatever score its last refresh (up to two minutes earlier) had. A walk-off
    /// is exactly the run that lands in that window. While this is set the page
    /// keeps the live cadence until a load comes back finished.
    private var awaitingServedFinal = false

    /// #9056 — the home probability the last completed load left in the hero,
    /// and the moment a pushed price moved `EventRefreshPlan.scoreCatchUpMove`
    /// away from it. The push carries no score, so a big move is the page's only
    /// sign that the score it is showing has probably just gone out of date.
    private var probabilityAtLastLoad: Double?
    private var scoreCatchUpUntil: TimeInterval?

    private var latestPriceFrame: LiveStreamFrame?
    private var latestSourceFrames: [String: LiveStreamFrame] = [:]
    private var latestAcceptedSourceDates: [String: Date] = [:]
    private var latestAcceptedPriceDate: Date?

    /// #9051 — the "this held blend cannot be ordered, read it again" requests.
    /// A folded hero refuses every raw-row frame, and each refusal says the
    /// blend moved, so the page re-reads detail and history — at most once per
    /// `revisionRefetchWindow`, and never dropping the LAST request of a burst:
    /// one arriving inside the window or during a read schedules exactly one
    /// more (web's `createFoldedRefetchScheduler`, FOLDED_FRAME_REFETCH_MS).
    static let revisionRefetchWindow: TimeInterval = 5
    private var revisionRefetchTask: Task<Void, Never>?
    private var revisionRefetchPending = false
    private var lastRevisionRefetchAt: TimeInterval?
    /// The held revision the chart last asked history to catch up to, so one
    /// accepted fold asks once (`chartRevisionRefreshKey`).
    private var requestedChartRevisionKey: String?

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
            adopt(try await client.fetchEvent(id: eventId))
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
            requestChartRevisionRefreshIfNeeded()
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

    /// One detail response into the page: every price, source and status rule a
    /// load applies, shared by `load()` and the #9051 re-read so the two can
    /// never disagree about what a response may overwrite.
    @MainActor
    private func adopt(_ response: EventDetail, recordsPriceActivity: Bool = true) {
        let prior = event
        var fetched = response
        if awaitingServedFinal {
            if EventState.isFinished(fetched.status) {
                awaitingServedFinal = false
            } else {
                // The detail payload is cached for up to 30s while live, so the
                // first load after a pushed final can still say `live`. The push
                // is the newer fact: keep it, take everything else, ask again.
                fetched.status = event?.status
            }
        }
        // #9051: a response older than the headline the page already holds
        // (by fold revision) keeps that headline and takes everything else.
        fetched = LiveEventPriceReconciliation.keepingNewerHeldHeadline(fetched, held: event)
        // Delivery can pause while a socket recovers. Keep its last
        // proven observation, but terminal refusal makes REST authoritative.
        // Check controller state here: error -> refusal need not emit a
        // second false delivery callback.
        let streamRecoverable = stream?.state.stopped == false
        fetched = LiveEventPriceReconciliation.preservingLiveStatus(
            latestPriceFrame, current: event, polled: fetched,
            streamRecoverable: streamRecoverable, now: Date(timeIntervalSince1970: now())
        )
        if LiveEventPriceReconciliation.shouldPreserve(
            latestPriceFrame, over: fetched, streamRecoverable: streamRecoverable
        ) {
            fetched = LiveEventPriceReconciliation.applying(
                latestPriceFrame, to: fetched, streamRecoverable: streamRecoverable
            )
        } else {
            // A newer REST reading, a refusal, or an unrankable response
            // retires the override. A later cache hit must not resurrect a
            // pushed price that REST has already superseded.
            latestPriceFrame = nil
            // Unknown or older REST may remain authoritative, but neither
            // erases a clock already proved by a served/pushed reading.
            // Otherwise its next stale replay could move the hero while
            // the chart correctly rejects that older point.
            if let servedAt = LiveEventPriceReconciliation.newestSourceDate(in: fetched),
               latestAcceptedPriceDate.map({ servedAt > $0 }) ?? true {
                latestAcceptedPriceDate = servedAt
            }
        }
        // Retiring an override must not erase an observation already known:
        // a later cache hit cannot make a replayed older source frame new.
        for (key, date) in LiveEventSourceReconciliation.observationDates(in: fetched) {
            if latestAcceptedSourceDates[key].map({ date > $0 }) ?? true {
                latestAcceptedSourceDates[key] = date
            }
        }
        fetched = LiveEventSourceReconciliation.reconciling(
            &latestSourceFrames, over: fetched, streamRecoverable: streamRecoverable
        )
        event = fetched
        if recordsPriceActivity, let prior, LivePriceActivity.isNewer(fetched, than: prior) {
            recordPriceActivity(from: prior, to: fetched)
        }
        probabilityAtLastLoad = fetched.currentOdds?.homeProbability
    }

    @MainActor
    private func recordPriceActivity(from prior: EventDetail, to current: EventDetail) {
        guard prior.id == current.id, prior.status == "live", current.status == "live" else { return }
        let before = LivePriceActivity.displayedPercents(in: prior)
        let after = LivePriceActivity.displayedPercents(in: current)
        guard after.home != nil || after.away != nil else { return }
        let beforeLabels = LivePriceActivity.displayedLabels(in: prior)
        let afterLabels = LivePriceActivity.displayedLabels(in: current)
        priceActivity = LivePriceActivity(
            sequence: (priceActivity?.sequence ?? 0) + 1,
            receivedAt: Date(timeIntervalSince1970: now()),
            homeProbability: current.currentOdds?.homeProbability,
            previousHomePercent: before.home, previousAwayPercent: before.away,
            homePercent: after.home, awayPercent: after.away,
            previousHomeLabel: beforeLabels.home, previousAwayLabel: beforeLabels.away,
            homeLabel: afterLabels.home, awayLabel: afterLabels.away
        )
    }

    // MARK: - #9051 fold-revision re-read

    /// Ask for detail + history again because the held blend could not be
    /// ordered against what just arrived. See `revisionRefetchWindow`.
    @MainActor
    private func requestRevisionRefetch() {
        if revisionRefetchTask != nil {
            revisionRefetchPending = true
            return
        }
        let wait = lastRevisionRefetchAt.map { max(0, $0 + Self.revisionRefetchWindow - now()) } ?? 0
        let pause = sleep
        revisionRefetchTask = Task { @MainActor [weak self] in
            if wait > 0 { await pause(wait) }
            guard !Task.isCancelled, let self else { return }
            self.revisionRefetchPending = false
            self.lastRevisionRefetchAt = self.now()
            await self.rereadPricePair()
            guard !Task.isCancelled else { return }
            self.revisionRefetchTask = nil
            if self.revisionRefetchPending {
                self.revisionRefetchPending = false
                self.requestRevisionRefetch()
            }
        }
    }

    /// #9268 — the detail alone, between the slow lane's full loads: the score,
    /// clock, period and status the stream does not carry.
    ///
    /// Through `adopt`, exactly as `load()` takes the same response, so a newer
    /// pushed price or a pushed final is kept over whatever the (cached) detail
    /// says and only the game state moves. Not a load: it does not stamp
    /// `lastLoadedAt`, which drives the refresh countdown, and it leaves the
    /// chart and markets to the full load that owns them.
    @MainActor
    private func rereadGameState() async {
        do {
            adopt(try await client.fetchEvent(id: eventId))
            error = nil
        } catch {
            self.error = error.localizedDescription
            logger.error("Game-state read failed for \(self.eventId): \(error)")
        }
        // A read that brings the final (or a suspension) has to re-plan the page
        // just as a load would; unchanged, this leaves the running loop alone.
        configureAutoRefresh()
    }

    /// Detail and history only — the two payloads that carry the blend and its
    /// revision. Not a `load()`: that is six requests and owns `lastLoadedAt`.
    @MainActor
    private func rereadPricePair() async {
        let client = self.client
        let id = eventId
        let requestedGeneration = streamRefetchGeneration
        async let detailRead = client.fetchFreshEvent(id: id)
        async let historyRead = client.fetchFreshEventHistory(id: id, hours: 168)
        do {
            // A failed half cannot publish its sibling alone or earn a receipt.
            // Keep the held pair until both reads finish, then use the existing
            // revision/removal reconciliation against the baseline at adoption.
            let (fetched, h) = try await (detailRead, historyRead)
            guard !Task.isCancelled else { return }
            let priorRevision = event.flatMap { LiveEventPriceReconciliation.pairedFoldRevision(in: $0) }
            let recordsActivity = requestedGeneration == nil || (
                requestedGeneration == deliveryGeneration && streamRefetchGeneration == requestedGeneration
            )
            adopt(fetched, recordsPriceActivity: recordsActivity)
            history = h
            if recordsActivity { pricePairRefreshFailed = false }
            if requestedGeneration == deliveryGeneration,
               streamRefetchGeneration == requestedGeneration,
               let priorRevision, let current = event,
               let revision = LiveEventPriceReconciliation.pairedFoldRevision(in: current),
               FoldRevision.compare(revision, priorRevision) == .newer {
                streamHasPushedPrice = true
                streamRefetchGeneration = nil
            }
            configureAutoRefresh()
        } catch {
            guard !Task.isCancelled else { return }
            // A retired connection's failure cannot darken its successor.
            if requestedGeneration == nil || requestedGeneration == deliveryGeneration {
                pricePairRefreshFailed = true
                streamHasPushedPrice = false
                configureAutoRefresh()
            }
            logger.error("Price-pair read failed for \(self.eventId): \(error)")
        }
        requestChartRevisionRefreshIfNeeded()
    }

    @MainActor
    private func requestChartRevisionRefreshIfNeeded() {
        guard let key = LiveEventPriceReconciliation.chartRevisionRefreshKey(
            event: event, history: history, liveBlend: liveBlend
        ), key != requestedChartRevisionKey else { return }
        requestedChartRevisionKey = key
        requestRevisionRefetch()
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
        if let until = scoreCatchUpUntil, now() >= until { scoreCatchUpUntil = nil }
        let plan: EventRefreshPlan = awaitingServedFinal
            ? .poll(every: EventRefreshPlan.livePollInterval)
            : EventRefreshPlan.decide(
                status: event?.status,
                streamDelivering: streamDelivering && !pricePairRefreshFailed,
                commenceTime: event?.commenceTime?.asDate,
                now: Date(timeIntervalSince1970: now()),
                catchingUp: scoreCatchUpUntil != nil
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
        //
        // #9268 — ONE loop, cut into slots, rather than a second loop for the
        // detail: two loops would each sleep, each re-plan, and could each run
        // a read on top of the other's. On the pushed slow lane every slot but
        // the last re-reads the game state alone; every other plan is one slot.
        let wait = sleep
        let slots = EventRefreshPlan.slots(for: plan)
        let gap = interval / Double(slots)
        refreshTask = Task { @MainActor [weak self] in
            var slot = 0
            while !Task.isCancelled {
                await wait(gap)
                guard !Task.isCancelled, let self else { return }
                slot += 1
                if self.pricePairRefreshFailed {
                    // Keep the game clock moving while the existing reader
                    // retries the incomplete authoritative price pair.
                    await self.rereadGameState()
                    self.requestRevisionRefetch()
                } else if slot < slots {
                    await self.rereadGameState()
                } else {
                    slot = 0
                    await self.load()
                }
            }
        }
        installedPlan = plan
    }

    @MainActor
    func stopRefresh() {
        refreshTask?.cancel()
        refreshTask = nil
        revisionRefetchTask?.cancel()
        revisionRefetchTask = nil
        revisionRefetchPending = false
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
                // Cleared on the way DOWN only. The way up follows the first
                // frame of a resumed stream (`apply` runs before the controller
                // reports delivering), so clearing there would erase the price
                // that just earned it.
                if !delivering {
                    self.streamHasPushedPrice = false
                    self.deliveryGeneration += 1
                    self.streamRefetchGeneration = nil
                    // The dot and fast polling reflect the outage immediately.
                    // A recoverable outage does not invalidate a price already
                    // observed; load() checks terminal refusal before using it.
                }
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
        deliveryGeneration += 1
        streamRefetchGeneration = nil
        streamHasPushedPrice = false
        streamTickTask?.cancel()
        streamTickTask = nil
        stream?.stop()
        stream = nil
        streamDelivering = false
        latestPriceFrame = nil
        latestSourceFrames.removeAll()
    }

    /// Write a pushed price into the model the page already reads.
    ///
    /// The same choice web made: the stream writes the SAME place the poll
    /// writes, so the hero, the chart header and every other consumer stay
    /// consistent and nothing downstream needs to know push exists.
    @MainActor
    private func apply(_ frame: LiveStreamFrame) {
        guard var current = event, current.id == frame.eventId else { return }
        let prior = current
        var acceptedNewPrice = false
        var armScoreCatchUp = false

        // Source ordering is independent of the blend: a delayed Kalshi quote
        // can still advance its own bar after a newer Polymarket blend frame.
        if let key = frame.source,
           let updated = LiveEventSourceReconciliation.applying(
               frame, to: current, newerThan: latestAcceptedSourceDates[key]
           ) {
            current = updated
            latestSourceFrames[key] = frame
            latestAcceptedSourceDates[key] = frame.updatedAt?.asDate
        }

        let stamped = frame.updatedAt?.asDate
        // #9051: when the held blend carries its fold revision, commit order
        // decides, not a clock. A frame from before a source removal still folds
        // the removed source into its `p`, and a frame on a FOLDED hero is a
        // raw-row value that hero never was. Only a strictly newer write to the
        // one row the hero reads lands — even one whose clock is older. An
        // unorderable frame still says the blend moved: read it again.
        let foldOrder = FoldRevision.frameOrder(
            held: LiveEventPriceReconciliation.pairedFoldRevision(in: current),
            frame: frame.rev?.revision
        )
        let priceIsNotNewer: Bool
        if let foldOrder {
            priceIsNotNewer = foldOrder != .newer
            if foldOrder == .incomparable {
                streamRefetchGeneration = deliveryGeneration
                requestRevisionRefetch()
            }
        } else {
            priceIsNotNewer = stamped.map { stamp in
                latestAcceptedPriceDate.map { stamp <= $0 } ?? false
            } ?? false
        }
        if !priceIsNotNewer, let p = frame.p, p.isFinite, (0...1).contains(p), var odds = current.currentOdds {
            // A clockless unversioned frame remains handled as before, but
            // cannot prove a newer receipt for freshness or motion.
            acceptedNewPrice = foldOrder == .newer || (foldOrder == nil && stamped != nil)
            latestPriceFrame = frame
            if let stamped, latestAcceptedPriceDate.map({ stamped > $0 }) ?? true {
                latestAcceptedPriceDate = stamped
            }
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
            LiveEventPriceReconciliation.adoptFrameProvenance(frame, into: &current)
            // The hero now shows a pushed price — the only thing the page's
            // stream dot may claim (#8320).
            streamHasPushedPrice = true
            if acceptedNewPrice { pricePairRefreshFailed = false }
            // #9056 — measured against the last LOAD, not the last frame, so a
            // play priced in over several small frames still counts as one move.
            if let base = probabilityAtLastLoad, abs(p - base) >= EventRefreshPlan.scoreCatchUpMove {
                armScoreCatchUp = scoreCatchUpUntil == nil
                scoreCatchUpUntil = now() + EventRefreshPlan.scoreCatchUpWindow
            }
        }

        // The same number, kept for the chart (#920). The hero renders the most
        // recent frame; the chart needs all of them, because a line is the
        // history of the number and not its latest value.
        //
        // Stamped time only. A frame with no `updated_at` — or one this build
        // cannot parse — still moves the hero, which needs no x-coordinate, but
        // it gets no point: placing it at "now" would draw an invented time next
        // to backend points that all carry real ones.
        //
        // The venue reading rides along (#836/#837/#920): on a single-source page
        // the backend blends nothing, and that venue's own line is the one the
        // chart draws — so it is the one that has to keep up with the hero.
        if !priceIsNotNewer, let p = frame.p, let stamped {
            liveBlend = LiveBlendBuffer.appending(
                LiveBlendPoint(date: stamped, homeProbability: p,
                               source: frame.source, sourceProbability: frame.sourceValue),
                to: liveBlend
            )
        }

        // A frame whose status has left the live set is the server telling us
        // the match ended; the controller closes on the `closed` event that
        // follows, and the status must not stay "live" underneath it.
        if let status = frame.status {
            if !EventState.isFinished(current.status), EventState.isFinished(status) {
                awaitingServedFinal = true
            }
            current.status = status
        }

        event = current
        if acceptedNewPrice { recordPriceActivity(from: prior, to: current) }
        // Re-planned only when the window OPENS: a move inside an open window
        // extends it and the loop is already on the fast cadence. Only a live
        // page, because `configureAutoRefresh` stops the stream on anything else
        // and this runs inside the stream's own callback.
        if armScoreCatchUp, current.status == "live" { configureAutoRefresh() }
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
