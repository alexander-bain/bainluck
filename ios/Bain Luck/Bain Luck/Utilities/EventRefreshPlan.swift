import Foundation

/// How often an OPEN event page re-fetches itself — one decision, so the page
/// cannot disagree with itself about when it is allowed to go stale.
///
/// This exists because `EventDetailViewModel.configureAutoRefresh` asked one
/// question — `event?.status == "live"` — and installed a poll only when the
/// answer was yes. Two readers were frozen by that, and a third by the clause
/// underneath it:
///
///   1. **A SCHEDULED PAGE COULD NEVER WAKE UP.** Nothing but the poll calls
///      `load()` again, and a scheduled page installed no poll, so it never
///      re-asked the server for its own status. The page a reader opens twenty
///      minutes before kick-off — Alex's pre-game ritual, product priority 3 —
///      still said "scheduled" an hour into the game. Only leaving the page and
///      coming back fixed it. That is a deadlock, not a cadence choice: no poll
///      ⇒ no status ⇒ no poll.
///
///   2. **A SUSPENDED MATCH WAS FROZEN FOR GOOD.** `suspended` is explicitly
///      non-terminal (`EventState.isSuspended`) — a rain-delayed US Open match
///      goes back to `live`. It is not the string `"live"`, so it polled never,
///      and the return to play arrived only for readers who closed the page.
///
///   3. **A HEALTHY PUSH STREAM FROZE THE SCORE.** The poll stood down entirely
///      while the SSE stream delivered, on the reasoning that the stream "carries
///      the one number that was actually changing". It does not:
///      `LiveStreamFrame` carries `p`, `source`, `sourceValue`, `updatedAt` and
///      `status` — and no score. `EventDetail.homeScore`/`awayScore` are `let`,
///      reachable only by a full `load()`. So the better the push path worked,
///      the longer the score and the history chart stood still.
///
/// The shape of the answer is a cadence per state rather than a boolean, because
/// the saving that (3) was written to get is real — six endpoints every 30
/// seconds — and throwing it away to unfreeze the score would trade one defect
/// for a quota bill. A pushed page keeps a slow lane instead of no lane.
///
/// Pure and clock-injected on purpose: every branch below is reachable from a
/// test without a socket, a server or a wait.
nonisolated enum EventRefreshPlan: Equatable {
    /// Nothing changes on this page again. Settled means settled.
    case idle
    /// Re-`load()` this often, measured BETWEEN completions (not on the wall
    /// clock), so a slow six-endpoint refresh never stacks on itself.
    case poll(every: TimeInterval)

    // MARK: - Cadences

    /// In play, carrying itself: the price, the score and the chart all move and
    /// nothing else is delivering them.
    static let livePollInterval: TimeInterval = 30

    /// In play with the push stream delivering. The stream owns the price; this
    /// lane exists only for what the stream cannot carry — the score, the
    /// history chart, the markets. Four times cheaper than `livePollInterval`,
    /// which keeps most of #2687's saving, and finite, which is the fix.
    static let livePushPollInterval: TimeInterval = 120

    /// Kick-off is close (or overdue) and the status has not flipped yet. This
    /// is the window the reader is actually sitting in the page for.
    static let imminentPollInterval: TimeInterval = 60

    /// Scheduled and still far off. Slow enough to cost nothing on a page left
    /// open, frequent enough that the page cannot be indefinitely wrong.
    static let distantPollInterval: TimeInterval = 300

    /// How close to kick-off counts as imminent.
    static let imminentWindow: TimeInterval = 30 * 60

    // MARK: - The decision

    /// The cadence an event page should run at right now.
    ///
    /// - Parameters:
    ///   - status: the served `EventDetail.status`, which may be `nil` or a
    ///     value this build has never heard of.
    ///   - streamDelivering: whether the SSE stream is DELIVERING (not merely
    ///     connected — see `EventDetailViewModel.streamDelivering`).
    ///   - commenceTime: parsed kick-off, `nil` when the row carries no date.
    ///   - now: injected so the pre-game branches are testable.
    ///
    /// An unrecognised status falls to the pre-game branch rather than to
    /// `.idle`. That direction is deliberate and it is the lesson `EventState`
    /// was written for: the first unfamiliar state must not inherit the settled
    /// claim. The cost of guessing wrong here is one request every five minutes;
    /// the cost of guessing wrong the other way is a page frozen forever.
    static func decide(
        status: String?,
        streamDelivering: Bool,
        commenceTime: Date?,
        now: Date
    ) -> EventRefreshPlan {
        // Settled. Nothing below this line can change, so nothing asks again.
        if EventState.isFinished(status) { return .idle }

        // In play: the literal live status, or a suspended match that the clock
        // agrees has started. `isSuspendedAndStarted` rather than `isSuspended`
        // so #4021's future-dated suspended fixture is treated as the pre-game
        // row it actually is.
        let inPlay = status == "live"
            || EventState.isSuspendedAndStarted(status, commenceTime: commenceTime, now: now)
        if inPlay {
            return .poll(every: streamDelivering ? livePushPollInterval : livePollInterval)
        }

        // Pre-game. `hasStarted` returns true for a nil date by design, which
        // lands a dateless row on the attentive cadence — the cheap direction to
        // be wrong in.
        let started = EventState.hasStarted(commenceTime: commenceTime, now: now)
        let imminent = started
            || (commenceTime.map { $0.timeIntervalSince(now) <= imminentWindow } ?? false)
        return .poll(every: imminent ? imminentPollInterval : distantPollInterval)
    }
}
