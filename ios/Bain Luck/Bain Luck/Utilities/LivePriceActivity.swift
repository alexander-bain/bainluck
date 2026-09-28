import Foundation

/// A local receipt for a newer price actually adopted by the held page.
/// `receivedAt` dates receipt here, never publication at an upstream source.
nonisolated struct LivePriceActivity: Equatable {
    let sequence: Int
    let receivedAt: Date
    let homeProbability: Double?
    let previousHomePercent: Int?
    let previousAwayPercent: Int?
    let homePercent: Int?
    let awayPercent: Int?
    let previousHomeLabel: String?
    let previousAwayLabel: String?
    let homeLabel: String?
    let awayLabel: String?

    var displayedValueChanged: Bool {
        previousHomeLabel != homeLabel || previousAwayLabel != awayLabel
    }
    var homeDelta: Int? {
        guard let previousHomePercent, let homePercent,
              previousHomeLabel == "\(previousHomePercent)%", homeLabel == "\(homePercent)%" else { return nil }
        return homePercent - previousHomePercent
    }
    var awayDelta: Int? {
        guard let previousAwayPercent, let awayPercent,
              previousAwayLabel == "\(previousAwayPercent)%", awayLabel == "\(awayPercent)%" else { return nil }
        return awayPercent - previousAwayPercent
    }

    /// Exactly the hero's printed pair, including withheld draw-sport away sides.
    static func displayedPercents(in event: EventDetail) -> (home: Int?, away: Int?) {
        guard let odds = event.currentOdds,
              let pair = DrawPricedWinner.printablePair(
                away: odds.awayProbability, home: odds.homeProbability, sport: event.sport
              ) else { return (nil, nil) }
        guard let away = pair.away else { return (Int((pair.home * 100).rounded()), nil) }
        let percents = complementDisplayPercents(away: away, home: pair.home,
                                   servedAway: odds.awayRenderedPercent,
                                   servedHome: odds.homeRenderedPercent)
        return (percents[1], percents[0])
    }

    static func displayedLabels(in event: EventDetail) -> (home: String?, away: String?) {
        guard let odds = event.currentOdds,
              let pair = DrawPricedWinner.printablePair(
                away: odds.awayProbability, home: odds.homeProbability, sport: event.sport
              ) else { return (nil, nil) }
        let percents = displayedPercents(in: event)
        return (formatProbability(pair.home, renderedPercent: percents.home),
                pair.away.map { formatProbability($0, renderedPercent: percents.away) })
    }

    /// Compare the adopted price, not response arrival or request-start state.
    static func isNewer(_ current: EventDetail, than previous: EventDetail) -> Bool {
        let held = LiveEventPriceReconciliation.pairedFoldRevision(in: previous)
        let adopted = LiveEventPriceReconciliation.pairedFoldRevision(in: current)
        if held != nil || adopted != nil {
            guard let held, let adopted else { return false }
            return FoldRevision.compare(adopted, held) == .newer
        }
        guard let before = LiveEventPriceReconciliation.newestSourceDate(in: previous),
              let after = LiveEventPriceReconciliation.newestSourceDate(in: current) else { return false }
        return after > before
    }
}
