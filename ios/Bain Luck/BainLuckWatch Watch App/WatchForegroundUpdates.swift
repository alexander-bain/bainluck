import Foundation

/// One outstanding invalidation plus one follow-up if a frame arrives during a
/// fetch. Identical/older frames do not earn another read. Values are never painted here.
@MainActor final class WatchForegroundInvalidation {
    private var sequence = 0
    private var consumed = 0
    private var lastFrame: LiveStreamFrame?
    private var nextAttempt: TimeInterval = 0
    var pending: Bool { sequence != consumed }
    var onPending: (@MainActor () -> Void)?

    func receive(_ frame: LiveStreamFrame, eventID: Int) {
        guard frame.eventId == eventID, frame != lastFrame else { return }
        if let held = lastFrame?.rev?.revision, let incoming = frame.rev?.revision {
            let order = FoldRevision.compare(incoming, held)
            if order == .older || (order == .same && frame.status == lastFrame?.status) { return }
        }
        lastFrame = frame
        invalidate()
    }
    func invalidate() {
        let alreadyPending = pending
        sequence += 1
        // A burst while already pending earns no extra scheduler wakeups.
        if !alreadyPending { onPending?() }
    }
    func delay(at now: TimeInterval) -> TimeInterval { max(0, nextAttempt - now) }
    func take(at now: TimeInterval) {
        consumed = sequence
        nextAttempt = now + 2 // Coalesce bursts without permitting a hot request loop.
    }
}

/// One cancellation-safe wait owned by the visible refresh loop. Stream signals
/// interrupt the deadline; a late canceled timer cannot resume a later wait.
@MainActor final class WatchForegroundWakeup {
    private var waitID: UUID?
    private var waiter: CheckedContinuation<Void, Error>?
    private var timer: Task<Void, Never>?

    func signal() {
        guard let id = waitID else { return }
        finish(id: id, result: .success(()))
    }

    func wait(seconds: TimeInterval,
              sleep: @escaping @MainActor (TimeInterval) async throws -> Void) async throws {
        try Task.checkCancellation()
        let id = UUID()
        try await withTaskCancellationHandler {
            try await withCheckedThrowingContinuation { (continuation: CheckedContinuation<Void, Error>) in
                precondition(waiter == nil, "Only the serial foreground owner may wait")
                guard !Task.isCancelled else {
                    continuation.resume(throwing: CancellationError())
                    return
                }
                waitID = id
                waiter = continuation
                timer = Task { @MainActor in
                    do {
                        try await sleep(seconds)
                        finish(id: id, result: .success(()))
                    } catch {
                        finish(id: id, result: .failure(error))
                    }
                }
            }
        } onCancel: {
            Task { @MainActor [weak self] in
                self?.finish(id: id, result: .failure(CancellationError()))
            }
        }
    }

    private func finish(id: UUID, result: Result<Void, Error>) {
        guard waitID == id, let continuation = waiter else { return }
        waitID = nil
        waiter = nil
        timer?.cancel()
        timer = nil
        continuation.resume(with: result)
    }
}

/// Shared by the mounted default opener and its URLSession boundary test.
/// Construction alone is inert: connect() is what starts the real byte pump.
@MainActor enum WatchForegroundStreamFactory {
    static func open(eventID: Int, session: URLSession? = nil) throws -> LiveStreamHandle {
        let transport = try LiveEventStreamTransport(eventId: eventID, session: session)
        transport.connect()
        return transport
    }
}

extension WatchSelectedGameStore {
    /// This method is owned by the visible view's structured task. There is one
    /// stream and one serial HTTP fetch. Background/navigation cancels both.
    @MainActor func runLiveForegroundRefresh(
        open: @escaping @MainActor (Int) throws -> LiveStreamHandle = { try WatchForegroundStreamFactory.open(eventID: $0) },
        clock: @escaping () -> TimeInterval = { ProcessInfo.processInfo.systemUptime },
        sleep: @escaping @MainActor (TimeInterval) async throws -> Void = { try await Task.sleep(for: .seconds($0)) }
    ) async {
        stopLiveForegroundUpdates()
        guard let eventID = selectedEventID else { return }
        let generation = foregroundStreamGeneration
        let invalidation = WatchForegroundInvalidation()
        let wakeup = WatchForegroundWakeup()
        invalidation.onPending = { wakeup.signal() }
        var stream: LiveStreamController?
        var attemptedStream = false
        var nextTick = clock()
        var fallbackNotBefore: TimeInterval = 0
        defer {
            stream?.stop()
            if foregroundStreamGeneration == generation { activeForegroundStream = nil }
        }
        while !Task.isCancelled, selectedEventID == eventID, foregroundStreamGeneration == generation {
            if game?.isLive != true {
                // Suspended/postponed and other non-live readings use their
                // ordinary poll. A later authoritative Live reading may reconnect.
                stream?.stop(); stream = nil
                activeForegroundStream = nil
                attemptedStream = false
                invalidation.take(at: clock())
            } else if !attemptedStream {
                attemptedStream = true
                let controller = LiveStreamController(open: {
                    let handle = try open(eventID)
                    // Control events can change deadlines without changing
                    // delivering (for example a rollover before the first open).
                    // Wake after the synchronous controller handlers run; these
                    // signals do not themselves authorize another detail read.
                    for event in ["reconnect", "closed", "error"] {
                        handle.on(event) { _ in wakeup.signal() }
                    }
                    return handle
                }, now: clock,
                    onFrame: { frame in invalidation.receive(frame, eventID: eventID) },
                    onDeliveringChange: { delivering in
                        // A dropped/closed stream earns one authoritative reread.
                        if !delivering { invalidation.invalidate() }
                    }, onResync: { invalidation.invalidate() })
                stream = controller
                activeForegroundStream = controller
                controller.start()
            }
            if clock() >= nextTick || stream?.state.reopenAt.map({ clock() >= $0 }) == true {
                stream?.tick()
                nextTick = clock() + LiveStreamTiming.tickInterval
            }
            let streamDue = invalidation.pending && foregroundInvalidationDelay <= 0
                && invalidation.delay(at: clock()) <= 0
            if (foregroundPollDelay <= 0 && clock() >= fallbackNotBefore) || streamDue {
                let triggeredByStream = invalidation.pending
                invalidation.take(at: clock())
                let prior = successfulRefreshSequence
                await refresh()
                // Transport cancellation without task cancellation sets no deadline.
                // Keep the original ordinary wait instead of spinning on that result.
                fallbackNotBefore = foregroundPollDelay <= 0 ? clock() + nextRefreshDelay : 0
                guard !Task.isCancelled, selectedEventID == eventID, foregroundStreamGeneration == generation else { return }
                if triggeredByStream, successfulRefreshSequence != prior {
                    stream?.acknowledgeAcceptedPrice()
                }
                // A newer invalidation is still pending. Never run a parallel HTTP read.
                continue
            }
            // Wait only for a real deadline. Accepted stream invalidations
            // wake this immediately; pending bursts share the same two-second
            // coalescing/backoff deadline instead of waking once per frame.
            let at = clock()
            var sleepDelay = max(foregroundPollDelay, max(0, fallbackNotBefore - at))
            if let stream, !stream.state.stopped {
                sleepDelay = min(sleepDelay, max(0, nextTick - at))
                if let reopenAt = stream.state.reopenAt {
                    sleepDelay = min(sleepDelay, max(0, reopenAt - at))
                }
            }
            if invalidation.pending {
                sleepDelay = min(sleepDelay, max(foregroundInvalidationDelay,
                                                invalidation.delay(at: at)))
            }
            do { try await wakeup.wait(seconds: max(0.01, sleepDelay), sleep: sleep) }
            catch { return }
        }
    }
}
