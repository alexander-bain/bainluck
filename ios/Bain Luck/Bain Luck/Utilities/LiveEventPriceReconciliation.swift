import Foundation

/// #920: keep a newer pushed price over an older REST response while adopting
/// the REST score/status/metadata. Compare source write clocks, never response
/// arrival or sportsbook capture time. Unknown clocks leave REST authoritative.
nonisolated enum LiveEventPriceReconciliation {
    static func newestSourceDate(in event: EventDetail) -> Date? {
        // This one key is numeric metadata, not a probability source. Unknown
        // future source keys participate rather than silently proving freshness
        // from only the subset this client happens to recognize.
        let sources = (event.winProbabilitySources ?? [:]).filter { $0.key != "betting_book_count" }
        guard !sources.isEmpty else { return nil }
        let dates = sources.values.compactMap { $0.updatedAt?.asDate }
        guard dates.count == sources.count else { return nil }
        return dates.max()
    }

    static func shouldPreserve(_ frame: LiveStreamFrame?, over polled: EventDetail, delivering: Bool) -> Bool {
        guard delivering, let frame, frame.eventId == polled.id,
              polled.status == "live",
              let p = frame.p, p.isFinite, (0...1).contains(p),
              let served = polled.currentOdds?.homeProbability, served.isFinite,
              let source = frame.source,
              polled.winProbabilitySources?[source] != nil,
              let pushedAt = frame.updatedAt?.asDate,
              let newest = newestSourceDate(in: polled) else { return false }
        // Any equally/newer source may advance the aggregate, including a
        // different venue. Removed/refused sources and withheld prices above
        // must never be resurrected by a previously received frame.
        return newest < pushedAt
    }

    static func applying(_ frame: LiveStreamFrame?, to polled: EventDetail, delivering: Bool) -> EventDetail {
        guard shouldPreserve(frame, over: polled, delivering: delivering),
              let p = frame?.p, var odds = polled.currentOdds else { return polled }
        odds.homeProbability = p
        odds.awayProbability = 1 - p
        odds.homeRenderedPercent = nil
        odds.awayRenderedPercent = nil
        var reconciled = polled
        reconciled.currentOdds = odds
        return reconciled
    }
}
