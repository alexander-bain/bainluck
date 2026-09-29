import Foundation

/// One event's embedded-market projection. Sports phase never controls market
/// eligibility: a completed game may still have open props awaiting settlement.
@MainActor
final class GameMarketsPriceDelivery {
    private let eventID: Int
    private let fetch: @Sendable (Int) async throws -> GameMarketsResponse
    private let publish: @MainActor (GameMarketsResponse) -> Void
    private let makeHandle: MarketStreamSubscription.Factory?
    private let now: () -> TimeInterval
    private let sleep: @Sendable (TimeInterval) async -> Void
    private let fallbackSleep: @Sendable (TimeInterval) async -> Void
    private var subscriptions: [String: MarketStreamSubscription] = [:]
    private var loadWaiters: [Int: CheckedContinuation<Void, Never>] = [:]
    private var nextWaiterID = 0
    private var task: Task<Void, Never>?
    private var fallback: Task<Void, Never>?
    private var pending = false
    private var generation = 0
    private var visible = false
    private var lastReadAt: TimeInterval?
    private var retryAt: TimeInterval = 0
    private var fence = GameMarketsPriceReconciliation.Fence()
    private(set) var value: GameMarketsResponse?

    init(eventID: Int,
         fetch: @escaping @Sendable (Int) async throws -> GameMarketsResponse,
         publish: @escaping @MainActor (GameMarketsResponse) -> Void,
         makeHandle: MarketStreamSubscription.Factory? = nil,
         now: @escaping () -> TimeInterval = { Date().timeIntervalSince1970 },
         sleep: @escaping @Sendable (TimeInterval) async -> Void = {
             try? await Task.sleep(nanoseconds: UInt64($0 * 1_000_000_000))
         },
         fallbackSleep: @escaping @Sendable (TimeInterval) async -> Void = {
             try? await Task.sleep(nanoseconds: UInt64($0 * 1_000_000_000))
         }) {
        self.eventID = eventID
        self.fetch = fetch
        self.publish = publish
        self.makeHandle = makeHandle
        self.now = now
        self.sleep = sleep
        self.fallbackSleep = fallbackSleep
    }

    func setVisible(_ active: Bool) {
        guard active != visible || !active else { return }
        visible = active
        if !active {
            generation += 1
            subscriptions.values.forEach { $0.stop() }
            subscriptions.removeAll()
            fallback?.cancel()
            fallback = nil
            task?.cancel()
            task = nil
            pending = false
            finishWaiters(Array(loadWaiters.keys))
        } else {
            configureSubscription()
            if value != nil { requestRefresh() }
        }
    }

    /// Initial/manual/periodic reads share the same serialization and budget as
    /// publications. A first load may run before the view becomes visible.
    func load() async {
        // During a failure cooldown the owed read happens at `retryAt`; a load
        // (the page's pull-to-refresh, its periodic reload) returns with the
        // held value instead of hanging on that retry for up to a minute.
        if retryAt > now() {
            requestRefresh(allowHidden: true)
            return
        }
        await withCheckedContinuation { continuation in
            nextWaiterID += 1
            loadWaiters[nextWaiterID] = continuation
            requestRefresh(allowHidden: true)
        }
    }

    func requestRefresh(allowHidden: Bool = false) {
        guard visible || allowHidden else { return }
        if task != nil { pending = true; return }
        let epoch = generation
        task = Task { @MainActor [weak self] in
            guard let self else { return }
            defer { if self.generation == epoch { self.task = nil } }
            repeat {
                let earliest = max(self.retryAt, self.lastReadAt.map { $0 + 2 } ?? self.now())
                let delay = earliest - self.now()
                if delay > 0 { await self.sleep(delay) }
                guard !Task.isCancelled, self.generation == epoch else { return }
                self.pending = false
                self.lastReadAt = self.now()
                await self.readAttempt(epoch: epoch)
                guard !Task.isCancelled, self.generation == epoch else { return }
            } while self.pending
        }
    }

    private func finishWaiters(_ ids: [Int]) {
        for id in ids { loadWaiters.removeValue(forKey: id)?.resume() }
    }

    private func readAttempt(epoch: Int) async {
        // A manual/initial load waits for its read attempt, not an unbounded
        // stream of trailing reads or a retry that may take minutes.
        let waiting = Array(loadWaiters.keys)
        defer { finishWaiters(waiting) }
        do {
            let body = try await fetch(eventID)
            guard !Task.isCancelled, generation == epoch else { return }
            if body.eventId == eventID {
                let accepted = GameMarketsPriceReconciliation.adopting(body, over: value, fence: &fence)
                value = accepted
                publish(accepted)
                configureSubscription()
            }
        } catch {
            guard !Task.isCancelled, generation == epoch else { return }
            if let seconds = FuturesPriceReadCooldown.seconds(for: error) {
                retryAt = max(retryAt, now() + seconds)
            } else {
                retryAt = max(retryAt, now() + 60)
            }
            // The final failed invalidation remains owed on a healthy wire.
            pending = visible
        }
    }

    private func configureSubscription() {
        guard visible else { return }
        let ids = Array(Set(value?.streamMarketIds ?? [])).filter { $0 > 0 }.sorted()
        var desired: [String: [Int]] = [:]
        for start in stride(from: 0, to: ids.count, by: 50) {
            let batch = Array(ids[start..<min(start + 50, ids.count)])
            desired[batch.map(String.init).joined(separator: ",")] = batch
        }
        for key in Array(subscriptions.keys) where desired[key] == nil {
            subscriptions.removeValue(forKey: key)?.stop()
        }
        for (key, batch) in desired where subscriptions[key] == nil {
            let subscription = MarketStreamSubscription(makeHandle: makeHandle,
                onInvalidate: { [weak self] _ in self?.requestRefresh() }, now: now)
            subscriptions[key] = subscription
            subscription.start(ids: batch)
        }
        guard fallback == nil else { return }
        let pause = fallbackSleep
        fallback = Task { @MainActor [weak self] in
            while !Task.isCancelled {
                await pause(60)
                guard !Task.isCancelled, let self, self.visible else { return }
                // Also discovers newly attached contracts that could not yet
                // invalidate the prior subscription set.
                self.requestRefresh()
            }
        }
    }
}
