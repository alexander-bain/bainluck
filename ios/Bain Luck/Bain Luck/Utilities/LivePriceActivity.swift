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
    /// #10090 — the hero's own printed strings (`displayedLabels`, tenths)
    /// before and after, for the one thing that must follow what is printed:
    /// which way the changed text slides. Nil when not recorded.
    var previousHomePrinted: String? = nil
    var previousAwayPrinted: String? = nil
    var homePrinted: String? = nil
    var awayPrinted: String? = nil

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

    /// Which way the printed value moved, for the slide of a changed hero or
    /// tip. The whole-point delta when it moved; when it did not, the printed
    /// tenths (62.1% → 62.4% is a rise the whole delta of 0 calls a fall).
    /// Nil when banded, unrecorded or unchanged. The flash, arrow and caption
    /// keep reading the whole deltas.
    var homeRising: Bool? { Self.rising(whole: homeDelta, from: previousHomePrinted, to: homePrinted) }
    var awayRising: Bool? { Self.rising(whole: awayDelta, from: previousAwayPrinted, to: awayPrinted) }

    private static func rising(whole: Int?, from: String?, to: String?) -> Bool? {
        guard let whole else { return nil }
        if whole != 0 { return whole > 0 }
        guard let before = from.flatMap(printedTenths), let after = to.flatMap(printedTenths),
              before != after else { return nil }
        return after > before
    }

    /// "62.4%" → 624; a band ("<1%", ">99%") or anything else → nil.
    private static func printedTenths(_ text: String) -> Int? {
        guard text.hasSuffix("%") else { return nil }
        let parts = text.dropLast().split(separator: ".", omittingEmptySubsequences: false)
        guard parts.count == 2, parts[1].count == 1, let whole = Int(parts[0]), let tenth = Int(parts[1]),
              whole >= 0, tenth >= 0 else { return nil }
        return whole * 10 + tenth
    }

    /// The hero's pair in whole percents, including withheld draw-sport away
    /// sides: the receipt's arithmetic (#10090 prints the hero in tenths).
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

    /// Exactly the hero's printed strings — in tenths since #10090 (ALEX item
    /// 39, `EventHeadlineTenths10090`) — for what must read the hero's own
    /// number: its whole-string change and the chart's live-edge label.
    static func displayedLabels(in event: EventDetail) -> (home: String?, away: String?) {
        guard let odds = event.currentOdds,
              let pair = DrawPricedWinner.printablePair(
                away: odds.awayProbability, home: odds.homeProbability, sport: event.sport
              ) else { return (nil, nil) }
        let printed = EventHeadlineTenths10090.pair(home: pair.home, away: pair.away)
        return (printed.home, printed.away)
    }

    /// The pair in whole percents, as the hero printed it before #10090. The
    /// receipt's labels keep this: the flash, the arrow and the "↑2 pts"
    /// caption speak whole points, and `homeDelta`/`awayDelta` are only
    /// defined over an unbanded whole label.
    static func wholeLabels(in event: EventDetail) -> (home: String?, away: String?) {
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
