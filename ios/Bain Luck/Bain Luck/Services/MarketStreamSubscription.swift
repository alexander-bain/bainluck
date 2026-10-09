import Foundation

/// A bounded set of market invalidations, never prices. Owners re-read their
/// authoritative representation and decide whether any newer data can land.
@MainActor
final class MarketStreamSubscription {
    typealias Factory = @MainActor ([Int]) throws -> LiveStreamHandle
    private let makeHandle: Factory
    private let onInvalidate: @MainActor ([Int]) -> Void
    private let onConnectionChange: @MainActor (Bool) -> Void
    private let now: () -> TimeInterval
    private let sleep: @Sendable (TimeInterval) async -> Void
    private var ids: [Int] = []
    private var handle: LiveStreamHandle?
    private var generation = 0
    private var lastWireAt: TimeInterval = 0
    private var retryAt: TimeInterval?
    private var tickTask: Task<Void, Never>?
    private var connected = false
    private var terminalIDs: Set<Int> = []
    /// Highest shared-hub recovery seen on the current handle; a new hub starts at 1.
    private var recoveredGeneration = 0

    init(makeHandle: Factory? = nil,
         onInvalidate: @escaping @MainActor ([Int]) -> Void,
         onConnectionChange: @escaping @MainActor (Bool) -> Void = { _ in },
         now: @escaping () -> TimeInterval = { Date().timeIntervalSince1970 },
         sleep: @escaping @Sendable (TimeInterval) async -> Void = {
             try? await Task.sleep(nanoseconds: UInt64($0 * 1_000_000_000))
         }) {
        self.makeHandle = makeHandle ?? { ids in
            var url = URLComponents(string: "https://api.bainluck.com/api/markets/stream")!
            url.queryItems = [URLQueryItem(name: "ids", value: ids.map(String.init).joined(separator: ","))]
            guard let address = url.url else { throw URLError(.badURL) }
            let transport = LiveEventStreamTransport(url: address)
            transport.connect()
            return transport
        }
        self.onInvalidate = onInvalidate
        self.onConnectionChange = onConnectionChange
        self.now = now
        self.sleep = sleep
    }

    /// Idempotent for a held visible set. Never silently drops overflow IDs.
    func start(ids requested: [Int]) {
        let selected = Array(Set(requested)).sorted()
        guard !selected.isEmpty, selected.count <= 50, selected.allSatisfy({ $0 > 0 }) else {
            stop()
            return
        }
        if ids != selected {
            stop()
            ids = selected
        }
        guard tickTask == nil else { return }
        connect()
        let pause = sleep
        tickTask = Task { @MainActor [weak self] in
            while !Task.isCancelled {
                await pause(5)
                guard !Task.isCancelled, let self else { return }
                self.tick()
            }
        }
    }

    func stop() {
        generation += 1
        tickTask?.cancel()
        tickTask = nil
        handle?.close()
        handle = nil
        ids = []
        terminalIDs = []
        retryAt = nil
        setConnected(false)
    }

    /// Driven clock makes quiet-wire recovery executable without wall sleeps.
    func tick() {
        guard !ids.isEmpty else { return }
        if let retryAt, now() >= retryAt {
            self.retryAt = nil
            connect()
        } else if handle != nil, now() - lastWireAt > 65 {
            recycle(after: 5)
        }
    }

    private func setConnected(_ value: Bool) {
        guard connected != value else { return }
        connected = value
        onConnectionChange(value)
    }

    private func recycle(after delay: TimeInterval) {
        generation += 1
        handle?.close()
        handle = nil
        setConnected(false)
        retryAt = now() + delay
    }

    private func connect() {
        let active = ids.filter { !terminalIDs.contains($0) }
        guard !active.isEmpty else { return }
        generation += 1
        let epoch = generation
        let next: LiveStreamHandle
        do { next = try makeHandle(active) }
        catch { recycle(after: 60); return }
        handle = next
        lastWireAt = now()
        recoveredGeneration = 0
        next.on("open") { [weak self] _ in
            guard let self, self.generation == epoch else { return }
            self.lastWireAt = self.now()
            self.setConnected(true)
            // Open includes unavailable IDs: the whole requested set needs an
            // authoritative read after the connection gap, including settlement.
            self.onInvalidate(active)
        }
        next.on("heartbeat") { [weak self] _ in
            guard let self, self.generation == epoch else { return }
            self.lastWireAt = self.now()
        }
        next.on("resync") { [weak self] raw in
            guard let self, self.generation == epoch,
                  let data = raw.data(using: .utf8),
                  let frame = try? JSONDecoder().decode(MarketRecovery.self, from: data),
                  (1...MarketRecovery.maxGeneration).contains(frame.generation),
                  frame.generation > self.recoveredGeneration else { return }
            self.recoveredGeneration = frame.generation
            self.lastWireAt = self.now()
            // Recovery owes a REST read, never quote freshness or terminal truth:
            // frames published while the hub was unsubscribed are gone.
            let remaining = active.filter { !self.terminalIDs.contains($0) }
            if !remaining.isEmpty { self.onInvalidate(remaining) }
        }
        next.on("market") { [weak self] raw in
            guard let self, self.generation == epoch,
                  let data = raw.data(using: .utf8),
                  let frame = try? JSONDecoder().decode(MarketInvalidation.self, from: data),
                  frame.invalidation, active.contains(frame.marketID) else { return }
            self.lastWireAt = self.now()
            self.onInvalidate([frame.marketID])
            if frame.terminal { self.terminalIDs.insert(frame.marketID) }
        }
        next.on("reconnect") { [weak self] _ in
            guard let self, self.generation == epoch else { return }
            self.onInvalidate(active)
            self.recycle(after: 5)
        }
        next.on("closed") { [weak self] raw in
            guard let self, self.generation == epoch else { return }
            let closed = raw.data(using: .utf8).flatMap { try? JSONDecoder().decode(MarketClosure.self, from: $0) }
            let ended = (closed?.marketIDs ?? active).filter { active.contains($0) }
            self.onInvalidate(ended)
            self.terminalIDs.formUnion(ended)
            self.recycle(after: 60)
        }
        next.on("error") { [weak self, weak next] _ in
            guard let self, let next, self.generation == epoch else { return }
            self.setConnected(false)
            // Network drops retry in the transport. HTTP refusals retire it;
            // bounded retry and the caller's poll handle eligibility recovery.
            if next.isClosed { self.recycle(after: 60) }
        }
    }
}

private struct MarketInvalidation: Decodable {
    let marketID: Int
    let invalidation: Bool
    let terminal: Bool
    enum CodingKeys: String, CodingKey { case marketID = "market_id", invalidation, terminal }
}
private struct MarketRecovery: Decodable {
    /// Same ceiling as the browser client's `Number.isSafeInteger`.
    static let maxGeneration = 9_007_199_254_740_991
    let generation: Int
}
private struct MarketClosure: Decodable {
    let marketIDs: [Int]
    enum CodingKeys: String, CodingKey { case marketIDs = "market_ids" }
}
