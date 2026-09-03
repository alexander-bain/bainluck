import Foundation

/// The SSE lifecycle for a live event, ported from `frontend/lib/liveStreamController.ts`.
///
/// #2687: native has no stream at all. `EventDetailViewModel` re-fetches SIX
/// endpoints every 30 seconds while a match is live, so a price that is three
/// seconds old in Postgres can be thirty seconds old on the phone. Web closed
/// that gap in live/034 S2; this is the same lifecycle, in Swift.
///
/// WHY IT IS A PORT AND NOT A FRESH IMPLEMENTATION. The web version is the
/// second attempt: CERT-717 blocked the first on two lifecycle defects that
/// every gate passed straight over, and the constants and rules below are the
/// repair. Writing a native client from the endpoint's shape alone would
/// rediscover both. Kept deliberately line-for-line comparable with the
/// TypeScript so the two cannot drift silently.
///
/// THE TWO DEFECTS THIS ENCODES THE FIX FOR:
///
/// 1. `reconnect` is a ROLLOVER, not a death. The server closes every stream at
///    `SSE_MAX_CONNECTION_S` (900s) and says so in words. A client that treats
///    that as failure gives a fan push for fifteen minutes and then silently
///    falls back to polling for the rest of the match.
///
/// 2. A HEARTBEAT IS NOT A DELIVERY. The heartbeat is emitted by the web
///    process on its own timer, independent of the publisher. If `worker-ws`
///    dies while this process's Redis subscription stays healthy, heartbeats
///    continue forever — so treating one as evidence of delivery keeps polling
///    switched off behind a frozen number. Gotcha #53: a signal that arrives
///    regardless of the thing it is supposed to be evidence FOR is a response
///    shape, not a signal.
///
/// THE RULE THE WHOLE FILE SERVES: a push path that dies must degrade to
/// polling, never to a frozen number. Every failure mode — refused, errored,
/// closed, aged out, or silently dead — ends with `delivering == false`, and
/// the caller restores its poll on that.
///
/// TIME IS A PARAMETER, NOT AN AMBIENT FACT. Everything schedules against
/// `now()` and is driven by `tick()`, so a test advances a clock instead of
/// waiting on one. No branch in here reads the wall clock (gotcha #44).

// MARK: - Frame

/// One pushed price. Matches `backend/app/routes/event_stream.py`'s
/// `probability` event, decoded with the app's `.convertFromSnakeCase` policy.
nonisolated struct LiveStreamFrame: Decodable, Sendable, Equatable {
    let eventId: Int
    let p: Double?
    let source: String?
    let sourceValue: Double?
    let updatedAt: String?
    let status: String?
}

// MARK: - Transport

/// The slice of an SSE connection this controller uses.
///
/// A protocol rather than a concrete `URLSession` reader so the lifecycle can be
/// driven by a fake in tests. `LiveEventStreamTransport` is the real one.
@MainActor
protocol LiveStreamHandle: AnyObject {
    /// Register a handler for a named SSE event (`open`, `probability`,
    /// `heartbeat`, `reconnect`, `closed`, `error`). The payload is the raw
    /// `data:` text, empty for events that carry none.
    func on(_ event: String, _ handler: @escaping @MainActor (String) -> Void)
    func close()
    /// True once the transport has given up for good. The `error` handler is
    /// allowed to fire on a blip that the transport will itself retry.
    var isClosed: Bool { get }
}

// MARK: - Constants
//
// Identical to `frontend/lib/liveStreamController.ts`. Any change here is a
// change there; they are one contract with one server.

enum LiveStreamTiming {
    /// Transport silence: three missed 20s heartbeats. The stream is dead.
    static let silenceTimeout: TimeInterval = 60

    /// Delivery silence. Longer than the transport budget ON PURPOSE: a quiet
    /// market publishes nothing, and the right answer to "push has nothing to
    /// say" is to resume polling while KEEPING the stream open — not to tear it
    /// down. The instant a frame arrives, push takes back over.
    static let dataSilenceTimeout: TimeInterval = 90

    static let reconnectBaseDelay: TimeInterval = 1
    static let reconnectMaxDelay: TimeInterval = 30

    /// A stream that lasted this long was healthy; its rollover is not a failure.
    static let healthyStream: TimeInterval = 60

    /// How often the owner should call `tick()`.
    static let tickInterval: TimeInterval = 5
}

// MARK: - Controller

@MainActor
final class LiveStreamController {

    struct State: Equatable {
        var delivering = false
        var stopped = false
        var connections = 0
        var reopenAt: TimeInterval?
    }

    private let open: @MainActor () throws -> LiveStreamHandle
    private let now: () -> TimeInterval
    private let onFrame: @MainActor (LiveStreamFrame) -> Void
    private let onDeliveringChange: @MainActor (Bool) -> Void

    private var handle: LiveStreamHandle?
    private var delivering = false
    private var stopped = false
    private var connections = 0
    private var openedAt: TimeInterval = 0
    private var lastMessageAt: TimeInterval = 0
    private var lastDataAt: TimeInterval = 0
    private var reopenAt: TimeInterval?
    private var consecutiveFastRollovers = 0

    /// For assertions and debugging; not part of the render path.
    var state: State {
        State(
            delivering: delivering,
            stopped: stopped,
            connections: connections,
            reopenAt: reopenAt
        )
    }

    init(
        open: @escaping @MainActor () throws -> LiveStreamHandle,
        now: @escaping () -> TimeInterval,
        onFrame: @escaping @MainActor (LiveStreamFrame) -> Void,
        onDeliveringChange: @escaping @MainActor (Bool) -> Void
    ) {
        self.open = open
        self.now = now
        self.onFrame = onFrame
        self.onDeliveringChange = onDeliveringChange
    }

    // MARK: Public surface

    func start() { connect() }

    /// Drive the clock. Call every `LiveStreamTiming.tickInterval`.
    func tick() {
        guard !stopped else { return }
        let at = now()

        if let due = reopenAt, at >= due {
            connect()
            return
        }
        guard handle != nil else { return }

        // 1. TRANSPORT dead — no frames, no heartbeats, and no error callback
        //    either. Nothing will ever tell us; give up so the caller polls.
        if at - lastMessageAt > LiveStreamTiming.silenceTimeout {
            stop()
            return
        }
        // 2. PUBLISHER dead (or the market is quiet) — the socket is fine and
        //    heartbeats keep arriving, but no price has been pushed for longer
        //    than we are willing to trust. Report NOT DELIVERING so polling
        //    resumes, and keep the stream open.
        if at - lastDataAt > LiveStreamTiming.dataSilenceTimeout {
            setDelivering(false)
        }
    }

    /// Terminal. No reopen, ever.
    func stop() {
        stopped = true
        reopenAt = nil
        closeHandle()
        setDelivering(false)
    }

    // MARK: Internals

    private func setDelivering(_ next: Bool) {
        guard delivering != next else { return }
        delivering = next
        onDeliveringChange(next)
    }

    private func closeHandle() {
        guard let current = handle else { return }
        // Close explicitly. A transport that keeps retrying in the background
        // under a caller that has gone back to polling would double-fetch
        // forever.
        current.close()
        handle = nil
    }

    /// The server asked for a fresh socket. Close this one and schedule the next.
    ///
    /// NOTHING ELSE CALLS THIS. A refused connect (409 non-live, 503 at
    /// capacity, 404) or a stream gone silent must still degrade to polling
    /// rather than retry-loop against a server that has already said no. Only
    /// the explicit `reconnect` frame — the server asking, in words — reopens.
    private func rollOver() {
        guard !stopped else { return }
        let lived = now() - openedAt
        closeHandle()
        setDelivering(false)
        if lived >= LiveStreamTiming.healthyStream {
            consecutiveFastRollovers = 0
        } else {
            consecutiveFastRollovers += 1
        }
        let exponent = Double(max(0, consecutiveFastRollovers - 1))
        let delay = min(
            LiveStreamTiming.reconnectMaxDelay,
            LiveStreamTiming.reconnectBaseDelay * pow(2, exponent)
        )
        reopenAt = now() + delay
    }

    private func connect() {
        guard !stopped else { return }
        reopenAt = nil

        let next: LiveStreamHandle
        do {
            next = try open()
        } catch {
            // A transport that will not even construct is a refused connect.
            setDelivering(false)
            stopped = true
            return
        }

        handle = next
        connections += 1
        openedAt = now()
        // Seed BOTH clocks. A stream that has just opened has not failed to
        // deliver anything yet; demanding a frame before one could arrive would
        // flap the caller straight back to polling on every rollover.
        lastMessageAt = openedAt
        lastDataAt = openedAt

        next.on("open") { [weak self, weak next] _ in
            guard let self, let next, !self.stopped, self.handle === next else { return }
            self.lastMessageAt = self.now()
            self.lastDataAt = self.now()
            self.setDelivering(true)
        }

        next.on("probability") { [weak self, weak next] raw in
            guard let self, let next, !self.stopped, self.handle === next else { return }
            self.lastMessageAt = self.now()
            guard let data = raw.data(using: .utf8) else { return }
            let decoder = JSONDecoder()
            decoder.keyDecodingStrategy = .convertFromSnakeCase
            // One bad frame is not a reason to abandon the stream. A decode
            // failure also GUARDS THE SHAPE: a malformed frame that dropped
            // `event_id` would otherwise be handed on and could blank a working
            // hero.
            guard let frame = try? decoder.decode(LiveStreamFrame.self, from: data) else { return }
            // THE ONLY place the delivery clock is rearmed. A frame is the only
            // evidence that anything is still publishing.
            self.lastDataAt = self.now()
            self.onFrame(frame)
            self.setDelivering(true)
        }

        next.on("heartbeat") { [weak self, weak next] _ in
            guard let self, let next, !self.stopped, self.handle === next else { return }
            // TRANSPORT clock only. A heartbeat proves this server process is
            // alive and its socket is open. It proves nothing about the
            // publisher, because the web subscriber emits it regardless — which
            // is exactly how a dead `worker-ws` kept polling switched off behind
            // a frozen number.
            self.lastMessageAt = self.now()
        }

        // The match ended. Terminal: the caller refetches once and settles the
        // page on the final number.
        next.on("closed") { [weak self, weak next] _ in
            guard let self, let next, self.handle === next else { return }
            self.stop()
        }

        // The connection ceiling. NOT terminal — see `rollOver`.
        next.on("reconnect") { [weak self, weak next] _ in
            guard let self, let next, self.handle === next else { return }
            self.rollOver()
        }

        next.on("error") { [weak self, weak next] _ in
            guard let self, let next, !self.stopped, self.handle === next else { return }
            // The transport retries by itself while it is still trying; only
            // give up once it has actually closed, so a single blip does not
            // bounce us to polling.
            if next.isClosed {
                self.stop()
            } else {
                self.setDelivering(false)
            }
        }
    }
}
