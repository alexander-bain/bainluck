import Combine
import Foundation
import os

private let logger = Logger(subsystem: "com.bainluck", category: "mystuff")

@MainActor
final class MyStuffViewModel: ObservableObject {
    @Published var items: [FeedItem] = []
    @Published var teamFutures: TeamFuturesResponse?
    @Published var loading = true
    @Published var error: String?

    private var refreshTimer: Timer?

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

    func load() async {
        let isInitial = items.isEmpty
        if isInitial { loading = true }
        do {
            async let feedTask = APIClient.shared.fetchFeed(myTeamsOnly: true, includeFutures: false)
            async let futuresTask = APIClient.shared.fetchMyTeamFutures(limit: 100)

            let feed = try await feedTask
            let futures = try? await futuresTask

            items = feed.items
            teamFutures = futures
            error = nil
            loading = false
            logger.info("My Stuff feed loaded: \(feed.items.count) items, \(futures?.items.count ?? 0) futures")
            configureAutoRefresh()
        } catch let apiError as APIError where apiError.isCancellation {
            if isInitial { loading = false }
            logger.debug("My Stuff feed load cancelled")
        } catch is CancellationError {
            if isInitial { loading = false }
            logger.debug("My Stuff feed load cancelled")
        } catch {
            if isInitial {
                self.error = error.localizedDescription
            }
            loading = false
            logger.error("My Stuff feed error: \(error)")
        }
    }

    private func configureAutoRefresh() {
        refreshTimer?.invalidate()
        guard hasLiveGames else { return }
        refreshTimer = Timer.scheduledTimer(withTimeInterval: 15, repeats: true) { [weak self] _ in
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
