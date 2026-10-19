import SwiftUI

/// #9483 — which reading the hero's big pair is, said under it.
///
/// The headline disclosure moved "Win Probability" and the confidence bars
/// behind the circled-info button, so the pair needs its own subject. The
/// subject depends on the phase: a valid quote on a game that has not started
/// or is live is the CURRENT chance; a game that started and is neither live
/// nor final (suspended, delayed, a status that has not caught up) still
/// draws the pair, but nothing says it is current, so it is the LAST RECORDED
/// one. Nor is a live pair CURRENT while its own status line says
/// "Update interrupted": the page stopped receiving prices, so the pair is the
/// last one it recorded. An opening-line hero (#9470) already says "Opening line" and gets no
/// second label. A finished hero is a verdict and does not use this.
///
/// Nor does a pair earn CURRENT by loading: the quote carries its own clock
/// (`hero_probability_observed_at`), and a quote older than
/// `SourceAge.liveStaleAfter` — before the off or during play — is the last
/// recorded one. Native's review of 5f542c7b96 mounted archived replays and
/// read "Current win chance" on quotes 11.5 h, 26 h and 36 h old. A pair with
/// no readable clock fails the same way an undated game does: toward "last
/// recorded", never toward "current". (`SourceAge.isStale` answers FALSE for
/// an undatable stamp because a mark must not draw on a guess; a claim of
/// "current" must not be made on one either, so the absent case is decided
/// here, not there.)
///
/// Presentation only. It reads the same status, clocks and opening-line flag
/// the hero already decided on, and never changes which pair is drawn.
nonisolated enum EventHeadlinePhase9483: Equatable, Sendable {
    case current
    case lastRecorded

    var label: String {
        switch self {
        case .current: return "Current win chance"
        case .lastRecorded: return "Last recorded win chance"
        }
    }

    /// Whether the pair gets a phase label at all. Time-free, so the page can
    /// mount the label's minute tick only where a label can be drawn.
    static func applies(status: String?, isOpeningLine: Bool) -> Bool {
        !isOpeningLine && !EventState.isFinished(status)
    }

    /// `observedAt` has no default on purpose: a caller that forgets the
    /// quote's clock must not compile into a page that calls every pair current.
    static func resolve(
        status: String?, commenceTime: Date?, isOpeningLine: Bool,
        observedAt: Date?,
        deliveryInterrupted: Bool = false, now: Date = Date()
    ) -> EventHeadlinePhase9483? {
        guard applies(status: status, isOpeningLine: isOpeningLine) else { return nil }
        if deliveryInterrupted { return .lastRecorded }
        guard let observedAt,
              now.timeIntervalSince(observedAt) <= SourceAge.liveStaleAfter
        else { return .lastRecorded }
        if status == "live" { return .current }
        // `hasStarted` treats a missing clock as started, so an undated game
        // fails toward "last recorded", never toward "current".
        return EventState.hasStarted(commenceTime: commenceTime, now: now) ? .lastRecorded : .current
    }

    /// Argon P1 — whether the chart may treat its newest price as live: the
    /// dot and number on the end of the line and the arrival ring. The same
    /// decision on the same clock as the phase label, so a pair the headline
    /// calls "last recorded" (stale, undated, interrupted, started but not
    /// live) never pulses as current on the line. The line itself is history
    /// and is drawn either way.
    static func isCurrent(
        status: String?, commenceTime: Date?, isOpeningLine: Bool,
        observedAt: Date?, deliveryInterrupted: Bool, now: Date
    ) -> Bool {
        resolve(status: status, commenceTime: commenceTime, isOpeningLine: isOpeningLine,
                observedAt: observedAt, deliveryInterrupted: deliveryInterrupted, now: now) == .current
    }

    /// The pre-game baseline a live hero carries under its current pair, in
    /// the finished hero's words ("Pre-match", or "Opened" on the
    /// `opening_odds` fallback). Same reading and pair rules as the finished
    /// caption: `PrematchReading` decides, `DrawPricedWinner` withholds the
    /// complement on a draw-priced sport and the lone side is then named.
    static func baselineText(
        prematch: PrematchOdds?, opening: OpeningOdds?, sport: String?,
        awayTeam: String, homeTeam: String
    ) -> String? {
        guard let pregame = PrematchReading.resolve(prematch: prematch, opening: opening),
              let pair = DrawPricedWinner.printablePair(
                away: pregame.awayProbability, home: pregame.homeProbability, sport: sport)
        else { return nil }
        if let away = pair.away {
            let percents = pregame.percents
            return "\(pregame.captionWord) \(formatProbability(away, renderedPercent: percents[0])) – \(formatProbability(pair.home, renderedPercent: percents[1]))"
        }
        let named = TeamShortName.shortPair(away: awayTeam, home: homeTeam, sportKey: sport)
        return "\(pregame.captionWord) \(named.home) \(formatProbability(pair.home))"
    }
}

/// The phase line and, on a live game, the pre-game baseline under it.
struct EventHeadlinePhaseLabel9483: View {
    let phase: EventHeadlinePhase9483
    let baseline: String?
    let maxWidth: CGFloat?

    var body: some View {
        VStack(spacing: 2) {
            Text(phase.label)
                .font(.caption2.weight(.semibold))
                .foregroundStyle(.secondary)
            if let baseline {
                Text(baseline)
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
        }
        .multilineTextAlignment(.center)
        .lineLimit(2)
        .frame(maxWidth: maxWidth)
        .fixedSize(horizontal: false, vertical: true)
        .accessibilityElement(children: .combine)
    }
}
