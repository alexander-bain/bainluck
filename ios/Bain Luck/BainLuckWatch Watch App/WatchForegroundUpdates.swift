import Foundation

/// One outstanding invalidation plus one follow-up if a frame arrives during a
/// fetch. Identical/older frames do not earn another read. Values are never painted here.
@MainActor final class WatchForegroundInvalidation {
    private var sequence = 0
    private var consumed = 0
    private var lastFrame: LiveStreamFrame?
    private var nextAttempt: TimeInterval = 0
    var pending: Bool { sequence != consumed }

    func receive(_ frame: LiveStreamFrame, eventID: Int) {
        guard frame.eventId == eventID, frame != lastFrame else { return }
        if let held = lastFrame?.rev?.revision, let incoming = frame.rev?.revision {
            let order = FoldRevision.compare(incoming, held)
            if order == .older || (order == .same && frame.status == lastFrame?.status) { return }
        }
        lastFrame = frame
        invalidate()
    }
    func invalidate() { sequence += 1 }
    func delay(at now: TimeInterval) -> TimeInterval { max(0, nextAttempt - now) }
    func take(at now: TimeInterval) {
        consumed = sequence
        nextAttempt = now + 2 // Coalesce bursts without permitting a hot request loop.
    }
}

extension WatchSelectedGameStore {
    /// This method is owned by the visible view's structured task. There is one
    /// stream and one serial HTTP fetch. Background/navigation cancels both.
    @MainActor func runLiveForegroundRefresh(
        open: @escaping @MainActor (Int) throws -> LiveStreamHandle = { try LiveEventStreamTransport(eventId: $0) },
        clock: @escaping () -> TimeInterval = { ProcessInfo.processInfo.systemUptime },
        sleep: (TimeInterval) async throws -> Void = { try await Task.sleep(for: .seconds($0)) }
    ) async {
        stopLiveForegroundUpdates()
        guard let eventID = selectedEventID else { return }
        let generation = foregroundStreamGeneration
        let invalidation = WatchForegroundInvalidation()
        var stream: LiveStreamController?
        var attemptedStream = false
        var nextTick = clock()
        var fallbackNotBefore: TimeInterval = 0
        defer {
            stream?.stop()
            if foregroundStreamGeneration == generation { activeForegroundStream = nil }
        }
        while !Task.isCancelled, selectedEventID == eventID, foregroundStreamGeneration == generation {
            if game?.isFinal == true || game?.isClosed == true {
                stream?.stop(); stream = nil
                invalidation.take(at: clock())
            } else if game?.isLive == true, !attemptedStream {
                attemptedStream = true
                let controller = LiveStreamController(open: { try open(eventID) }, now: clock,
                    onFrame: { frame in invalidation.receive(frame, eventID: eventID) },
                    onDeliveringChange: { delivering in
                        // A dropped/closed stream earns one authoritative reread.
                        if !delivering { invalidation.invalidate() }
                    }, onResync: { invalidation.invalidate() })
                stream = controller
                activeForegroundStream = controller
                controller.start()
            }
            if clock() >= nextTick {
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
            do { try await sleep(1) } catch { return }
        }
    }
}
