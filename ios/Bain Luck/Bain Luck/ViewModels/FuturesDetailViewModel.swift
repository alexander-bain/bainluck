import Combine
import Foundation
import os

private let logger = Logger(subsystem: "com.bainluck", category: "futuresDetail")

protocol FuturesDetailProviding: Sendable {
    func fetchFuturesDetail(id: Int) async throws -> FuturesMarketDetail
}
extension APIClient: FuturesDetailProviding {}

final class FuturesDetailViewModel: ObservableObject {
    @Published private(set) var market: FuturesMarketDetail?
    @Published private(set) var loading = true
    @Published private(set) var error: String?
    @Published private(set) var chartRefreshToken = 0
    @Published private(set) var streamConnected = false

    let marketId: Int
    private let client: FuturesDetailProviding
    private let makeStreamHandle: MarketStreamSubscription.Factory?
    private let now: () -> TimeInterval
    private let refreshSleep: @Sendable (TimeInterval) async -> Void
    private let minimumRefreshInterval: TimeInterval
    private var lastRefreshAt: TimeInterval?
    private var retryAt: TimeInterval = 0
    private let sleep: @Sendable (TimeInterval) async -> Void
    private var subscription: MarketStreamSubscription?
    private var fallbackTask: Task<Void, Never>?
    private var refreshTask: Task<Void, Never>?
    private var refreshPending = false
    private var loadGeneration = 0
    private var visibilityGeneration = 0
    private var visible = false
    private var withdrawals: [Int: FuturesPriceReconciliation.Withdrawal] = [:]

    init(marketId: Int, client: FuturesDetailProviding = APIClient.shared,
         makeStreamHandle: MarketStreamSubscription.Factory? = nil,
         now: @escaping () -> TimeInterval = { Date().timeIntervalSince1970 },
         minimumRefreshInterval: TimeInterval = 2,
         refreshSleep: @escaping @Sendable (TimeInterval) async -> Void = {
             try? await Task.sleep(nanoseconds: UInt64($0 * 1_000_000_000))
         },
         sleep: @escaping @Sendable (TimeInterval) async -> Void = {
             try? await Task.sleep(nanoseconds: UInt64($0 * 1_000_000_000))
         }) {
        self.marketId = marketId
        self.client = client
        self.makeStreamHandle = makeStreamHandle
        self.sleep = sleep
        self.now = now
        self.minimumRefreshInterval = minimumRefreshInterval
        self.refreshSleep = refreshSleep
    }

    @MainActor
    func load() async {
        loadGeneration += 1
        let generation = loadGeneration
        let visibility = visibilityGeneration
        loading = market == nil
        do {
            let fetched = try await client.fetchFuturesDetail(id: marketId)
            guard !Task.isCancelled, generation == loadGeneration,
                  visibility == visibilityGeneration, fetched.id == marketId else { return }
            adopt(fetched)
            error = nil
        } catch {
            guard !Task.isCancelled, generation == loadGeneration,
                  visibility == visibilityGeneration else { return }
            if let seconds = FuturesPriceReadCooldown.seconds(for: error) {
                retryAt = max(retryAt, now() + seconds)
                // A refused final invalidation is still owed, even on a healthy wire.
                if refreshTask != nil { refreshPending = true }
            }
            self.error = error.localizedDescription
            logger.error("Failed to load futures \(self.marketId): \(error)")
        }
        loading = false
        configureStream()
    }

    @MainActor
    func setVisible(_ value: Bool) {
        guard value != visible else { return }
        visible = value
        visibilityGeneration += 1
        if !value {
            loadGeneration += 1
            subscription?.stop()
            fallbackTask?.cancel()
            fallbackTask = nil
            refreshTask?.cancel()
            refreshTask = nil
            refreshPending = false
        } else {
            configureStream()
        }
    }

    @MainActor
    private func adopt(_ fetched: FuturesMarketDetail) {
        let held = market
        let accepted = FuturesPriceReconciliation.adopting(fetched, over: held, withdrawals: &withdrawals)
        market = accepted
        if let held {
            // This token refreshes the chart, not a pushed-price receipt. An
            // accepted unclocked first quote still needs a matching chart.
            let changed = held.source != accepted.source
                || held.outcomes.map(\.id) != accepted.outcomes.map(\.id)
                || held.outcomes.map(\.probability) != accepted.outcomes.map(\.probability)
            if changed || FuturesPriceReconciliation.hasNewObservation(accepted, over: held) {
                chartRefreshToken += 1
            }
        }
    }

    @MainActor
    private func configureStream() {
        guard visible else { return }
        if let market, FuturesPriceReconciliation.isSettled(market) {
            subscription?.stop()
            fallbackTask?.cancel()
            fallbackTask = nil
            return
        }
        if subscription == nil {
            subscription = MarketStreamSubscription(makeHandle: makeStreamHandle,
                onInvalidate: { [weak self] ids in
                    guard let self, ids.contains(self.marketId) else { return }
                    self.requestRefresh()
                }, onConnectionChange: { [weak self] connected in self?.streamConnected = connected })
        }
        subscription?.start(ids: [marketId])
        guard fallbackTask == nil else { return }
        let pause = sleep
        fallbackTask = Task { @MainActor [weak self] in
            while !Task.isCancelled {
                await pause(60)
                guard !Task.isCancelled, let self, self.visible else { return }
                // A socket can remain healthy after the final invalidation's
                // authoritative read failed. Keep retrying that unpaid read.
                if !self.streamConnected || self.error != nil { self.requestRefresh() }
            }
        }
    }

    /// At most one fetch plus one trailing fetch for a burst, no faster than
    /// two seconds between automatic dispatches. The latest
    /// invalidation cannot be dropped while an older response is in flight.
    @MainActor
    private func requestRefresh() {
        guard visible else { return }
        if refreshTask != nil { refreshPending = true; return }
        let visibility = visibilityGeneration
        refreshTask = Task { @MainActor [weak self] in
            guard let self else { return }
            repeat {
                let nextEligible = max(self.retryAt,
                    self.lastRefreshAt.map { $0 + self.minimumRefreshInterval } ?? self.now())
                let delay = nextEligible - self.now()
                if delay > 0 { await self.refreshSleep(delay) }
                guard !Task.isCancelled, self.visible,
                      self.visibilityGeneration == visibility else { return }
                // Everything received during the wait is covered by this read.
                self.refreshPending = false
                self.lastRefreshAt = self.now()
                await self.load()
                guard !Task.isCancelled, self.visible,
                      self.visibilityGeneration == visibility else { return }
            } while self.refreshPending
            self.refreshTask = nil
        }
    }
}
