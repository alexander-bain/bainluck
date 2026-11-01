import Foundation

/// #10090 (Alex 67, "can you add the ekg to the app too") — THE EVENT PAGE'S
/// "EKG": A HEARTBEAT UNDER THE BIG PERCENTAGE THAT BEATS ONLY WHEN THE MARKETS
/// REPORT IN.
///
/// When the headline holds still, a reader cannot tell "nobody is trading"
/// from "trades keep arriving at the same price". The web answered it first
/// (`frontend/lib/event/ekgHeartbeat.ts`); this is the same rule, ported, so
/// the two surfaces beat on the same evidence.
///
/// ═══ A BEAT IS EVIDENCE, NEVER A TIMER ═══
///
/// Exactly two things earn a beat:
///
///   * decision J's `confirmed_at` ADVANCING, as the page already gates it
///     (`EventDetailViewModel.confirmedAtCoveringShown`: nil while a newer
///     price is owed, a commit floor is uncovered or a preview prints another
///     number). A nil adds nothing and erases nothing;
///   * the clock of the number the hero PRINTS advancing
///     (`displayedProbabilityObservedAt`, preview included) — the web's
///     "accepted price clock". Without it the line would go flat exactly while
///     new prices land, because J is withheld whenever a newer one is owed.
///
/// Nothing else: a keep-alive carries the same `confirmed_at`, a re-read that
/// returns the held value carries the same clock, and a reconnect moves
/// neither. While the stream is not delivering, advances are recorded
/// silently, so the catch-up after a reconnect never beats on its own; and an
/// advance to a clock already older than the flat threshold is recorded
/// silently too — newer than what we had, but not a report made now.
///
/// ═══ FLAT ═══
///
/// `flatAfter` = 15 s, the web's `EKG_FLAT_AFTER_MS`: J's confirming beats
/// arrive about every 6 s while the markets keep agreeing, so 15 s survives two
/// missed confirmations, and it is under the stream's 20 s keep-alive.
///
/// TIME IS A PARAMETER (gotcha #44): every function takes `now`.
nonisolated struct EkgTracker: Equatable {
    /// No evidenced report for this long ⇒ the line is flat.
    static let flatAfter: TimeInterval = 15
    /// Bursts coalesce: at most one drawn beat per this long.
    static let minBeatGap: TimeInterval = 1.5

    static let empty = EkgTracker()

    var eventId: Int?
    /// Newest `confirmed_at` seen for this event.
    var confirmedAt: Date?
    /// Newest printed-number clock seen for this event.
    var priceAt: Date?
    /// When the markets last reported in (a drawn beat or a coalesced one).
    var lastSignalAt: Date?
    /// When the last beat was DRAWN.
    var beatAt: Date?
    /// Drawn beats on this page — keys the animation so each beat plays once.
    var beats = 0

    /// One render's inputs. Equatable, so the page steps the tracker only when
    /// one of them moves; `stepped` is idempotent for a repeat anyway.
    struct Observation: Equatable {
        var eventId: Int
        /// The stream is open and delivering (`EkgHeartbeat.transportOpen`).
        var transportOpen: Bool
        var confirmedAt: Date?
        var priceObservedAt: Date?
    }

    private static func newer(_ next: Date?, than prev: Date?) -> Bool {
        guard let next else { return false }
        return prev.map { next > $0 } ?? true
    }

    func stepped(_ obs: Observation, now: Date) -> EkgTracker {
        // Another event starts from its baseline: the clocks it opens with are
        // what it already had, never a report it heard.
        guard eventId == obs.eventId else {
            return EkgTracker(eventId: obs.eventId, confirmedAt: obs.confirmedAt,
                              priceAt: obs.priceObservedAt)
        }
        let confirmedAdvanced = Self.newer(obs.confirmedAt, than: confirmedAt)
        let priceAdvanced = Self.newer(obs.priceObservedAt, than: priceAt)
        var next = self
        if confirmedAdvanced { next.confirmedAt = obs.confirmedAt }
        if priceAdvanced { next.priceAt = obs.priceObservedAt }

        // An advance is a report only if the report is recent: the first
        // confirmation after a connect "advances" from nothing, and on a
        // market that went quiet minutes ago it is minutes old.
        let advancedTo = [confirmedAdvanced ? obs.confirmedAt : nil,
                          priceAdvanced ? obs.priceObservedAt : nil].compactMap { $0 }.max()
        guard let advancedTo, now.timeIntervalSince(advancedTo) < Self.flatAfter,
              obs.transportOpen else { return next }

        next.lastSignalAt = now
        if beatAt.map({ now.timeIntervalSince($0) >= Self.minBeatGap }) ?? true {
            next.beatAt = now
            next.beats = beats + 1
        }
        return next
    }
}

nonisolated enum EkgHeartbeat {
    enum Mode: Equatable { case beating, flat, interrupted }

    struct Presentation: Equatable {
        var mode: Mode
        /// Keys the drawn beat; 0 = none drawn yet on this page.
        var beats: Int
        /// Whole seconds since the markets last reported in; nil = never.
        var secondsSinceSignal: Int?
        /// For VoiceOver.
        var label: String
    }

    /// What the view draws: the moving trace, or — under Reduce Motion — a
    /// still mark and the age in words.
    enum Drawing: Equatable {
        case trace(Mode, beats: Int)
        case still(Mode, text: String?)
    }

    /// Only a delivering stream can be hearing the markets.
    static func transportOpen(_ status: LiveUpdateStatus) -> Bool {
        status == .live || status == .awaitingUpdate
    }

    /// The gate (Alex 67: on by default, live games only). Hidden before the
    /// off, after the finish, under a venue's settled verdict, on an opening
    /// line (no stream to report). Interruption stays visible: that is the
    /// line's own warning state.
    static func isVisible(eventStatus: String?, finished: Bool, venueSettledVerdict: Bool,
                          isOpeningLine: Bool) -> Bool {
        eventStatus == "live" && !finished && !venueSettledVerdict && !isOpeningLine
    }

    static func present(_ tracker: EkgTracker, status: LiveUpdateStatus, now: Date) -> Presentation {
        let since = tracker.lastSignalAt.map { max(0, now.timeIntervalSince($0)) }
        let seconds = since.map { Int($0.rounded(.down)) }
        let ago = seconds.map { "last update \($0) second\($0 == 1 ? "" : "s") ago" } ?? "no update yet"
        if status == .interrupted {
            return Presentation(mode: .interrupted, beats: tracker.beats, secondsSinceSignal: seconds,
                                label: "Markets reporting: updates interrupted")
        }
        let alive = transportOpen(status) && since.map { $0 < EkgTracker.flatAfter } == true
        return Presentation(mode: alive ? .beating : .flat, beats: tracker.beats,
                            secondsSinceSignal: seconds, label: "Markets reporting: \(ago)")
    }

    static func drawing(_ presentation: Presentation, reduceMotion: Bool) -> Drawing {
        guard reduceMotion else { return .trace(presentation.mode, beats: presentation.beats) }
        return .still(presentation.mode, text: presentation.secondsSinceSignal.map { "Updated \($0)s ago" })
    }
}
