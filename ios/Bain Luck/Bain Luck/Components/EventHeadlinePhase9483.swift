import SwiftUI

/// #9483 — which reading the hero's big pair is, said under it.
///
/// The headline disclosure moved "Win Probability" and the confidence bars
/// behind the circled-info button, so the pair needs its own subject. The
/// subject depends on the phase: a valid quote on a game that has not started
/// or is live is the CURRENT chance; a game that started and is neither live
/// nor final (suspended, delayed, a status that has not caught up) still
/// draws the pair, but nothing says it is current, so it is the LAST RECORDED
/// one. An opening-line hero (#9470) already says "Opening line" and gets no
/// second label. A finished hero is a verdict and does not use this.
///
/// Presentation only. It reads the same status, clock and opening-line flag the
/// hero already decided on, and never changes which pair is drawn.
nonisolated enum EventHeadlinePhase9483: Equatable, Sendable {
    case current
    case lastRecorded

    var label: String {
        switch self {
        case .current: return "Current win chance"
        case .lastRecorded: return "Last recorded win chance"
        }
    }

    static func resolve(
        status: String?, commenceTime: Date?, isOpeningLine: Bool, now: Date = Date()
    ) -> EventHeadlinePhase9483? {
        guard !isOpeningLine, !EventState.isFinished(status) else { return nil }
        if status == "live" { return .current }
        // `hasStarted` treats a missing clock as started, so an undated game
        // fails toward "last recorded", never toward "current".
        return EventState.hasStarted(commenceTime: commenceTime, now: now) ? .lastRecorded : .current
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
