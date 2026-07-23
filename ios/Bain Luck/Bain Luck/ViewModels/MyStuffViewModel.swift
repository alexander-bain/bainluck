import Combine
import Foundation
import os

private let logger = Logger(subsystem: "com.bainluck", category: "mystuff")

@MainActor
final class MyStuffViewModel: ObservableObject {
    @Published private(set) var items: [FeedItem] = []
    @Published private(set) var teamFutures: TeamFuturesResponse?
    @Published private(set) var loading = true
    @Published private(set) var error: String?

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

        // Team futures are best-effort and never fail the load (already `try?`).
        async let futuresTask = APIClient.shared.fetchMyTeamFutures(limit: 100)

        // #240 Item 3: the cold first-load had no safety net — a single transient
        // blip on the my-teams feed request surfaced "first-load failure" with no
        // recovery, while Discover already retries 3×. Retry the feed fetch with a
        // short backoff so a flaky cold load self-heals. Cancellation (view
        // re-appear / task replaced) is not an error and returns immediately.
        var loaded = false
        for attempt in 1...3 {
            do {
                let feed = try await APIClient.shared.fetchFeed(
                    myTeamsOnly: true, includeFutures: false
                )
                items = feed.items
                error = nil
                loaded = true
                break
            } catch let apiError as APIError where apiError.isCancellation {
                if isInitial { loading = false }
                logger.debug("My Stuff feed load cancelled")
                return
            } catch is CancellationError {
                if isInitial { loading = false }
                logger.debug("My Stuff feed load cancelled")
                return
            } catch {
                logger.error("My Stuff feed error (attempt \(attempt)/3): \(error)")
                if attempt < 3 {
                    try? await Task.sleep(for: .seconds(1.5))
                } else if isInitial {
                    self.error = error.localizedDescription
                }
            }
        }

        teamFutures = try? await futuresTask
        loading = false
        if loaded {
            logger.info(
                "My Stuff feed loaded: \(self.items.count) items, \(self.teamFutures?.items.count ?? 0) futures"
            )
            configureAutoRefresh()
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
