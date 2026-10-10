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
/// 3. (#8079 on web; #920 here) A NETWORK THAT WENT AWAY IS NOT A SERVER THAT
///    SAID NO. A release restarts the web dyno and cuts every open stream with
///    no `reconnect` frame. On web the browser's `EventSource` retries by itself
///    and push comes back; the native transport used to report that cut as
///    closed-for-good, `stop()` is terminal, and the page polled for the rest of
///    the match (native/319 caught it on production: release v5007, 3 min+ of
///    polling with no return to push). The transport now retries a dropped
///    connection the way `EventSource` does, and `tick()` reads `isConnecting`
///    so a silent-but-retrying transport is given `retryGiveUp` before it is
///    retired — the same split web's `readyState` check makes.
///
/// 4. (#10468 / #8320) A FRAME IS NOT A DELIVERY EITHER — until the page TAKES
///    it. A decoded frame can still be refused by its owner: the wrong event, a
///    revision the page already holds or one older than it, no usable price.
///    The handler used to rearm the delivery clock for every decoded frame, so
///    a stream of refused frames renewed the data-silence budget forever and
///    kept polling off behind a price that was not moving. The frame now
///    proves only the TRANSPORT, like a heartbeat; the owner calls
///    `acknowledgeAcceptedPrice()` once it has actually adopted a newer price
///    (or a successful authoritative re-read), and that is the only data-clock
///    rearm after `open`. Web's twin still rearms on the frame; this is the
///    native half of #8320 and is deliberately ahead of it.
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

private nonisolated struct LiveStreamRecovery: Decodable {
    let generation: Int
}

/// One pushed price. Matches `backend/app/routes/event_stream.py`'s
/// `probability` event, decoded with the app's `.convertFromSnakeCase` policy.
nonisolated struct LiveStreamFrame: Decodable, Sendable, Equatable {
    let eventId: Int
    let p: Double?
    let source: String?
    let sourceValue: Double?
    let updatedAt: String?
    let status: String?
    /// #9051 — the written row's revision, `{"<event_id>": rev}`. `p` is that
    /// ROW's aggregate, so it orders only against a held one-row vector; see
    /// `FoldRevision.frameOrder`. Absent from a producer before the contract.
    let rev: ServedFoldRevision?
    /// #10090 — on a FOLDED page's raw `probability` frame: the server promises
    /// one `folded_probability` frame next, carrying the authoritative quote or
    /// an explicit null. `false`/absent on that result and on every other frame.
    let foldedQuotePending: Bool?
    /// #10090 — the authoritative full-fold quote a `folded_probability` frame
    /// carries. `nil` for explicit null, for a malformed quote, and on every
    /// raw frame; `foldedResult` tells those apart.
    let foldedQuote: ServedFoldedQuote?
    /// #10090 — set by the controller, never decoded: this frame arrived as the
    /// named `folded_probability` event, the answer to a pending raw frame.
    var foldedResult = false

    init(eventId: Int, p: Double?, source: String?, sourceValue: Double?,
         updatedAt: String?, status: String?, rev: ServedFoldRevision? = nil,
         foldedQuotePending: Bool? = nil, foldedQuote: ServedFoldedQuote? = nil,
         foldedResult: Bool = false) {
        self.eventId = eventId
        self.p = p
        self.source = source
        self.sourceValue = sourceValue
        self.updatedAt = updatedAt
        self.status = status
        self.rev = rev
        self.foldedQuotePending = foldedQuotePending
        self.foldedQuote = foldedQuote
        self.foldedResult = foldedResult
    }

    private enum CodingKeys: String, CodingKey {
        case eventId, p, source, sourceValue, updatedAt, status, rev, foldedQuotePending, foldedQuote
    }
}

/// #10090 — the server's full fold for an event, pushed beside a raw row write
/// so a folded hero can move without re-reading detail and history. Built by
/// the same fold, hero resolver and source formatter as the detail route
/// (`backend/app/utils/folded_live_quote.py`).
nonisolated struct FoldedQuote: Decodable, Sendable, Equatable {
    let eventId: Int
    let heroProbability: Double?
    let heroProbabilityAway: Double?
    let heroProbabilitySource: String?
    let heroProbabilityObservedAt: String?
    let blendFoldRevision: FoldRevision
    let winProbabilitySources: [String: WinProbSource]
    let heroSportsbookCount: Int?
    let status: String?
    let sport: String?
    let heroSettledResult: String?

    private enum CodingKeys: String, CodingKey {
        case eventId, heroProbability, heroProbabilityAway, heroProbabilitySource,
             heroProbabilityObservedAt, blendFoldRevision, winProbabilitySources,
             heroSportsbookCount, status, sport, heroSettledResult
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        eventId = try c.decode(Int.self, forKey: .eventId)
        heroProbability = try c.decodeIfPresent(Double.self, forKey: .heroProbability)
        heroProbabilityAway = try c.decodeIfPresent(Double.self, forKey: .heroProbabilityAway)
        heroProbabilitySource = try c.decodeIfPresent(String.self, forKey: .heroProbabilitySource)
        heroProbabilityObservedAt = try c.decodeIfPresent(String.self, forKey: .heroProbabilityObservedAt)
        // A quote without a well-formed vector dates nothing, so it is no quote.
        guard let revision = try c.decode(ServedFoldRevision.self, forKey: .blendFoldRevision).revision else {
            throw DecodingError.dataCorruptedError(
                forKey: .blendFoldRevision, in: c, debugDescription: "malformed fold revision"
            )
        }
        blendFoldRevision = revision
        winProbabilitySources = try c.decode([String: WinProbSource].self, forKey: .winProbabilitySources)
        heroSportsbookCount = try c.decodeIfPresent(Int.self, forKey: .heroSportsbookCount)
        status = try c.decodeIfPresent(String.self, forKey: .status)
        sport = try c.decodeIfPresent(String.self, forKey: .sport)
        heroSettledResult = try c.decodeIfPresent(String.self, forKey: .heroSettledResult)
        // Same refusals as web's `readFoldedQuote`: a quote that cannot be
        // printed exactly as served is refused whole, never half-adopted.
        let probabilities = [heroProbability, heroProbabilityAway].compactMap { $0 }
        guard probabilities.allSatisfy({ $0.isFinite && (0...1).contains($0) }),
              heroProbabilityObservedAt.map({ $0.asDate != nil }) ?? true,
              heroSportsbookCount.map({ $0 >= 0 }) ?? true,
              winProbabilitySources.allSatisfy({ key, source in
                  guard let value = source.value?.doubleValue, value.isFinite else { return false }
                  // `betting_book_count` is a count wearing a source's shape.
                  return WinProbSourceCatalog.realSourceKeys.contains(key) ? (0...1).contains(value) : value >= 0
              }) else {
            throw DecodingError.dataCorrupted(.init(codingPath: decoder.codingPath,
                                                    debugDescription: "unprintable folded quote"))
        }
    }
}

/// The quote as it arrived. NEVER THROWS, like `ServedFoldRevision`: a bad quote
/// degrades to "no quote" — the existing detail/history fallback — and never
/// drops the frame around it.
nonisolated struct ServedFoldedQuote: Decodable, Sendable, Equatable {
    let quote: FoldedQuote?

    init(_ quote: FoldedQuote?) {
        self.quote = quote
    }

    init(from decoder: Decoder) throws {
        quote = try? decoder.singleValueContainer().decode(FoldedQuote.self)
    }
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
    /// True while the transport is (re)establishing a connection on its own —
    /// web's `readyState === CONNECTING`. `tick()` reads it to tell a network
    /// that went away (still retrying: wait) from a socket nothing is retrying.
    var isConnecting: Bool { get }
}

extension LiveStreamHandle {
    /// A transport that never retries is never connecting. That is the old,
    /// safe direction: silence retires it and the caller polls.
    var isConnecting: Bool { false }
}

// MARK: - Constants
//
// Identical to `frontend/lib/liveStreamController.ts`. Any change here is a
// change there; they are one contract with one server.

enum LiveStreamTiming {
    /// Transport silence: three missed 20s heartbeats. The stream is dead.
    static let silenceTimeout: TimeInterval = 60

    /// How long a silent transport that is STILL RETRYING is given before the
    /// controller retires it for good. Web's `RETRY_GIVEUP_MS`: long enough to
    /// outlast a release or a tunnel, short enough that a page left open
    /// against an unreachable server is not retrying all evening. Polling
    /// covers the whole window either way — this only decides whether push
    /// can come BACK.
    static let retryGiveUp: TimeInterval = 300

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
    private let onResync: @MainActor () -> Void
    /// #10090 — whether the owner reads `folded_probability`. Opt-in, so a
    /// surface that only needs "something moved" (Discover's cards) keeps its
    /// one refresh per raw frame instead of a second for the quote after it.
    private let deliversFoldedQuotes: Bool

    private var handle: LiveStreamHandle?
    private var delivering = false
    private var stopped = false
    private var connections = 0
    private var openedAt: TimeInterval = 0
    private var lastMessageAt: TimeInterval = 0
    private var lastDataAt: TimeInterval = 0
    private var lastResyncGeneration = 0
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
        onDeliveringChange: @escaping @MainActor (Bool) -> Void,
        onResync: @escaping @MainActor () -> Void = {},
        deliversFoldedQuotes: Bool = false
    ) {
        self.open = open
        self.now = now
        self.onFrame = onFrame
        self.onDeliveringChange = onDeliveringChange
        self.onResync = onResync
        self.deliversFoldedQuotes = deliversFoldedQuotes
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
        guard let current = handle else { return }

        // 1. TRANSPORT silent — no frames and no heartbeats for longer than we
        //    are willing to trust. Polling resumes either way; what the
        //    transport is DOING about the silence decides whether this is
        //    terminal.
        if at - lastMessageAt > LiveStreamTiming.silenceTimeout {
            setDelivering(false)
            // Still connecting: the transport is retrying by itself (a release
            // cut the socket, or the network went away) and may well succeed.
            // Retiring it here is what cost a reader push for the whole match.
            // Bounded, so an unreachable server is not retried forever.
            if current.isConnecting {
                if at - lastMessageAt > LiveStreamTiming.retryGiveUp { stop() }
                return
            }
            // Refused, or an open-but-silent socket nothing is retrying.
            // Neither will change on its own, so retire the stream as before.
            stop()
            return
        }
        // 2. PUBLISHER dead (or the market is quiet) — the socket is fine and
        //    heartbeats keep arriving, but no price has been ADOPTED for longer
        //    than we are willing to trust. Frames the owner refused count here
        //    exactly as heartbeats do: not at all (#10468). Report NOT DELIVERING so polling
        //    resumes, and keep the stream open.
        if at - lastDataAt > LiveStreamTiming.dataSilenceTimeout {
            setDelivering(false)
        }
    }

    /// #10468 — the owner ADOPTED a newer price from this stream (or a
    /// successful authoritative re-read it triggered). The only thing after
    /// `open` that rearms the delivery clock or turns delivery back on.
    ///
    /// Called by the owner AFTER it has committed the adopted state, so the
    /// `onDeliveringChange` this may fire — synchronously, from inside the
    /// owner's `onFrame` — reads that state, never the one before it. Refused
    /// once stopped, and between a rollover and its reopen: a stream that has
    /// no socket has delivered nothing, and the next one must push again.
    func acknowledgeAcceptedPrice() {
        guard !stopped, handle != nil else { return }
        lastDataAt = now()
        setDelivering(true)
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
        lastResyncGeneration = 0

        // The transport can reopen underneath this same handle after a drop.
        // A different server process may begin its recovery generation at 1.
        next.on("open") { [weak self, weak next] _ in
            guard let self, let next, !self.stopped, self.handle === next else { return }
            self.lastResyncGeneration = 0
            self.lastMessageAt = self.now()
            self.lastDataAt = self.now()
            self.setDelivering(true)
        }

        let onProbability = { (foldedResult: Bool) -> @MainActor (String) -> Void in
            { [weak self, weak next] raw in
                guard let self, let next, !self.stopped, self.handle === next else { return }
                self.lastMessageAt = self.now()
                guard let data = raw.data(using: .utf8) else { return }
                let decoder = JSONDecoder()
                decoder.keyDecodingStrategy = .convertFromSnakeCase
                // One bad frame is not a reason to abandon the stream. A decode
                // failure also GUARDS THE SHAPE: a malformed frame that dropped
                // `event_id` would otherwise be handed on and could blank a working
                // hero.
                guard var frame = try? decoder.decode(LiveStreamFrame.self, from: data) else { return }
                frame.foldedResult = foldedResult
                // TRANSPORT clock only (above), exactly like a heartbeat. Decoding a
                // frame is not delivering a price: the owner may refuse it (wrong
                // event, an old or equal revision, no usable value), and a stream of
                // refused frames used to renew the data-silence budget forever
                // (#10468). The owner calls `acknowledgeAcceptedPrice()` from inside
                // this callback once — and only if — it adopts the price.
                self.onFrame(frame)
            }
        }
        next.on("probability", onProbability(false))
        // #10090 — the same decoder, marked as the answer to a pending raw
        // frame. It shares that frame's raw revision, so it is handed on whole:
        // the quote inside is ordered by its own full vector, never deduped as
        // a repeat of the raw row.
        if deliversFoldedQuotes { next.on("folded_probability", onProbability(true)) }

        // #10090: a recovered shared subscription may have missed writes. Its
        // generation invalidates the held quote; it is not itself a price.
        // Dedup belongs to THIS connection, reset on every transport open.
        next.on("resync") { [weak self, weak next] raw in
            guard let self, let next, !self.stopped, self.handle === next else { return }
            self.lastMessageAt = self.now()
            guard let data = raw.data(using: .utf8),
                  let recovery = try? JSONDecoder().decode(LiveStreamRecovery.self, from: data),
                  recovery.generation > self.lastResyncGeneration else { return }
            self.lastResyncGeneration = recovery.generation
            self.onResync()
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
            // The transport retries a dropped connection by itself (#920);
            // only give up once it has actually closed (a refusal), so a
            // release or a blip costs polling until it is back, not push for
            // the rest of the match.
            if next.isClosed {
                self.stop()
            } else {
                self.setDelivering(false)
            }
        }
    }
}
