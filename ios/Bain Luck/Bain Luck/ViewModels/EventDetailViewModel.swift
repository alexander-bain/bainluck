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

    private var refreshTimer: Timer?
    let eventId: Int

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
        if let rf = await relatedFuturesTask.value {
            // Only overwrite if new data has content, or we had nothing before
            if relatedFutures == nil || rf.homeTeamFutures != nil || rf.awayTeamFutures != nil || rf.sharedFutures != nil || rf.boxScore != nil {
                relatedFutures = rf
            }
        }
        if let tp = await progressionTask.value {
            if teamProgression == nil || tp.homeTeam != nil || tp.awayTeam != nil {
                teamProgression = tp
            }
        }
        if let gm = await gameMarketsTask.value {
            // Only overwrite if new data has meaningful content, or we had nothing before
            let hasContent = (gm.playerProps != nil && !(gm.playerProps?.isEmpty ?? true))
                || (gm.spreads != nil && !(gm.spreads?.isEmpty ?? true))
                || (gm.totals != nil && !(gm.totals?.isEmpty ?? true))
                || (gm.other != nil && !(gm.other?.isEmpty ?? true))
            if gameMarkets == nil || hasContent {
                gameMarkets = gm
            }
        }
        if let lm = await lineMovementTask.value {
            lineMovement = lm
        }
    }

    private func configureAutoRefresh() {
        refreshTimer?.invalidate()
        guard event?.status == "live" else { return }
        refreshTimer = Timer.scheduledTimer(withTimeInterval: 30, repeats: true) { [weak self] _ in
            guard let self else { return }
            Task { @MainActor in
                await self.load()
            }
        }
    }

    func stopRefresh() {
        refreshTimer?.invalidate()
        refreshTimer = nil
    }
}
