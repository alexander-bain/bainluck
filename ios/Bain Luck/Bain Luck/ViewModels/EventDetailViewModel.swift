import Combine
import os
import SwiftUI

private let logger = Logger(subsystem: "com.bainluck", category: "eventDetail")

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

    /// live/034 S3 — the latest pushed frame, or nil when nothing is streaming.
    ///
    /// Published SEPARATELY rather than merged into `event`: `EventDetail` is an
    /// all-`let` `Decodable`, so patching it would mean reconstructing the whole
    /// model on every tick. The view prefers this for the hero number and falls
    /// back to `currentOdds` — see `liveHomeProbability`.
    @Published private(set) var livePush: LiveFrame?
    /// Whether the SSE stream is currently delivering. The UI may only claim
    /// "live" freshness while this is true.
    @Published private(set) var isStreaming = false

    private var refreshTimer: Timer?
    private var streamTask: Task<Void, Never>?
    let eventId: Int

    /// Whether a periodic auto-refresh request is currently installed. Only live
    /// events poll; scheduled/completed pages do not, so their UI must not imply it.
    /// While the stream is delivering there is no timer, and none should be implied.
    var isAutoRefreshing: Bool { refreshTimer != nil }

    /// The home win probability to render: the pushed value when one has arrived,
    /// otherwise whatever the last fetch carried.
    var liveHomeProbability: Double? {
        livePush?.probability ?? event?.currentOdds?.homeProbability
    }

    init(eventId: Int) {
        self.eventId = eventId
    }

    @MainActor
    func load() async {
        loading = event == nil

        // Start secondary fetches immediately (they only need eventId)
        let historyTask = Task { () -> EventHistoryResponse? in
            do { return try await APIClient.shared.fetchEventHistory(id: eventId, hours: 168) }
            catch { logger.error("History fetch failed for \(self.eventId): \(error)"); return nil }
        }
        let relatedFuturesTask = Task { () -> RelatedFuturesResponse? in
            do { return try await APIClient.shared.fetchRelatedFutures(eventId: eventId) }
            catch { logger.error("Related futures failed for \(self.eventId): \(error)"); return nil }
        }
        let progressionTask = Task { () -> TeamProgressionResponse? in
            do { return try await APIClient.shared.fetchTeamProgression(eventId: eventId) }
            catch { logger.error("Team progression failed for \(self.eventId): \(error)"); return nil }
        }
        let gameMarketsTask = Task { () -> GameMarketsResponse? in
            do { return try await APIClient.shared.fetchGameMarkets(eventId: eventId) }
            catch { logger.error("Game markets failed for \(self.eventId): \(error)"); return nil }
        }
        let lineMovementTask = Task { () -> LineMovementResponse? in
            do { return try await APIClient.shared.fetchLineMovement(eventId: eventId) }
            catch { logger.error("Line movement failed for \(self.eventId): \(error)"); return nil }
        }

        // Await primary fetch (controls loading state)
        do {
            event = try await APIClient.shared.fetchEvent(id: eventId)
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

    private func configureAutoRefresh() {
        refreshTimer?.invalidate()
        refreshTimer = nil
        guard event?.status == "live" else {
            // Not live: no timer, and no stream either — the ruling is explicit
            // that non-live keeps polling, and a scheduled page polls slowly by
            // being reloaded, not by holding a connection open.
            streamTask?.cancel()
            streamTask = nil
            isStreaming = false
            return
        }

        // live/034 S3 — try to be pushed. The timer is installed ONLY if the
        // stream is not delivering, and comes straight back the moment it stops.
        startStreamIfNeeded()
        guard !isStreaming else { return }
        installPollTimer()
    }

    private func installPollTimer() {
        refreshTimer?.invalidate()
        refreshTimer = Timer.scheduledTimer(withTimeInterval: 30, repeats: true) { [weak self] _ in
            guard let self else { return }
            Task { @MainActor in
                await self.load()
            }
        }
    }

    private func startStreamIfNeeded() {
        guard streamTask == nil else { return }
        isStreaming = true
        // Consumed on the MAIN actor, so `self` never crosses an isolation
        // boundary and every mutation below is already where it belongs.
        streamTask = Task { @MainActor [weak self] in
            guard let self else { return }
            for await frame in LiveEventStream.frames(eventId: self.eventId) {
                // A frame for another event can only mean crossed wires;
                // rendering it would put someone else's number on this page,
                // which is worse than showing a stale one.
                guard frame.eventId == self.eventId else { continue }
                self.livePush = frame
                self.isStreaming = true
                // The stream IS the refresh — stop paying for five requests
                // every 30 seconds while it is delivering.
                self.refreshTimer?.invalidate()
                self.refreshTimer = nil
                self.lastLoadedAt = Date()
            }

            // The loop falling through IS the single "it ended" signal, on every
            // exit path. Degrade to polling, never to a frozen number.
            self.isStreaming = false
            self.streamTask = nil
            guard !Task.isCancelled, self.event?.status == "live" else { return }
            self.installPollTimer()
            // Settle the page on a number from the database rather than the
            // last frame we happened to receive.
            await self.load()
        }
    }

    func stopRefresh() {
        refreshTimer?.invalidate()
        refreshTimer = nil
        isStreaming = false
        // Cancelling the consuming task terminates the AsyncStream, which tears
        // down the connection — there is no second teardown path to forget.
        streamTask?.cancel()
        streamTask = nil
    }
}
