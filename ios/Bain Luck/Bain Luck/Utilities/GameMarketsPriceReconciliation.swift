import Foundation

/// Orders the complete rendered projection, not each normalized percentage.
/// Row revision is an ordering clock only; it never earns a fresh/live badge.
nonisolated enum GameMarketsPriceReconciliation {
    struct Fence {
        var revisions: [String: Date] = [:]
        var withdrawn: [String: Set<String>] = [:]
        var winnerQuotes = FinalGameWinnerQuoteFence()
    }

    struct Row {
        let key: String
        let prices: [Double?]
        let source: String?
        let markets: Set<Int>
        let contributors: Set<String>
        let verdict: Bool?
        let winner: Bool?
        let actual: Double?
        var priced: Bool { prices.contains { $0 != nil } }
        var isWinnerQuote: Bool { key.hasPrefix("finalWinner:") }
    }

    static func rows(_ body: GameMarketsResponse) -> [Row] {
        func markets(_ one: Int?, _ many: [Int]?) -> Set<Int> {
            Set((many ?? []) + (one.map { [$0] } ?? []))
        }
        func ids(_ values: [Int]?) -> Set<String> { Set((values ?? []).map(String.init)) }
        var result = (body.playerProps ?? []).map {
            Row(key: "props:\($0.id)", prices: [$0.overProbability], source: $0.source,
                markets: markets($0._marketId, $0._marketIds), contributors: ids($0.contributorOutcomeIds),
                verdict: $0.hit, winner: $0.isWinner, actual: $0.actual)
        }
        for (section, entries) in [("spreads", body.spreads), ("totals", body.totals),
                                    ("teamTotals", body.teamTotals), ("period", body.periodMarkets)] {
            result += (entries ?? []).map {
                Row(key: "\(section):\($0.id)", prices: [$0.probability, $0.overProbability], source: $0.source,
                    markets: markets($0._marketId, $0._marketIds), contributors: ids($0.contributorOutcomeIds),
                    verdict: nil, winner: $0.isWinner, actual: nil)
            }
        }
        result += (body.other ?? []).map {
            Row(key: "other:\($0.id)", prices: [$0.probability], source: $0.source,
                markets: markets($0._marketId, $0._marketIds), contributors: ids($0.contributorOutcomeIds),
                verdict: nil, winner: $0.isWinner, actual: nil)
        }
        for matchup in body.matchups ?? [] {
            result += matchup.outcomes.map {
                Row(key: "matchups:\(matchup.id):\($0.name)", prices: [$0.probability], source: matchup.source,
                    markets: markets(matchup._marketId, matchup._marketIds),
                    contributors: ids($0.contributorOutcomeIds ?? matchup.contributorOutcomeIds),
                    verdict: nil, winner: $0.isWinner, actual: nil)
            }
        }
        if let quote = body.openWinnerQuote {
            result.append(Row(key: "finalWinner:\(quote.marketId)",
                prices: quote.outcomes.sorted { $0.outcomeId < $1.outcomeId }.map { $0.probability },
                source: quote.source, markets: [quote.marketId],
                contributors: quote.contributorOutcomeIds, verdict: nil, winner: nil, actual: nil))
        }
        return result
    }

    static func adopting(_ incoming: GameMarketsResponse, over held: GameMarketsResponse?,
                         fence: inout Fence) -> GameMarketsResponse {
        // A different event cannot add terminal evidence to this held page.
        if let held, incoming.eventId != held.eventId { return held }
        fence.winnerQuotes.recordClosed(incoming.closedWinnerMarketIds)
        func checkedQuote(_ body: GameMarketsResponse) -> GameMarketsResponse {
            var checked = body
            checked.closedWinnerMarketIds = fence.winnerQuotes.closedMarketIds.sorted()
            checked.openWinnerQuote = fence.winnerQuotes.visible(
                body.openWinnerQuote, eventId: body.eventId, eventStatus: body.status)
            if let quote = checked.openWinnerQuote,
               !(body.streamMarketIds ?? []).contains(quote.marketId)
                || !quote.contributorOutcomeIds.allSatisfy({ body.outcomeMarketIds?[$0] == quote.marketId }) {
                checked.openWinnerQuote = nil
            }
            return checked
        }
        // Terminal evidence clears the quote even when a regressed unrelated
        // score, grade, or row clock forces the rest of this response to be held.
        let checked = checkedQuote(incoming)
        let checkedHeld = held.map(checkedQuote)
        return adoptingProjection(checked, over: checkedHeld, fence: &fence)
    }

    private static func adoptingProjection(_ incoming: GameMarketsResponse, over held: GameMarketsResponse?,
                                          fence: inout Fence) -> GameMarketsResponse {
        let nextRows = rows(incoming)
        guard Set(nextRows.map(\.key)).count == nextRows.count else { return held ?? incoming }
        let next = Dictionary(uniqueKeysWithValues: nextRows.map { ($0.key, $0) })
        let clocks = (incoming.outcomeRevisionAt ?? [:]).compactMapValues {
            FuturesPriceReconciliation.observationDate($0)
        }
        guard let held else {
            fence.revisions = clocks
            for row in nextRows where !row.priced { fence.withdrawn[row.key] = row.contributors }
            return incoming
        }
        guard incoming.eventId == held.eventId else { return held }
        if EventState.isFinished(held.status) {
            guard EventState.isFinished(incoming.status),
                  held.homeScore == nil || incoming.homeScore == held.homeScore,
                  held.awayScore == nil || incoming.awayScore == held.awayScore else { return held }
        }
        let beforeRows = rows(held)
        let before = Dictionary(beforeRows.map { ($0.key, $0) }, uniquingKeysWith: { a, _ in a })
        var nextFence = fence
        let bindings = incoming.outcomeMarketIds ?? [:]
        let oldBindings = held.outcomeMarketIds ?? [:]
        var changedMarkets = Set<Int>()
        for (id, date) in clocks {
            if let prior = fence.revisions[id], date < prior { return held }
            if fence.revisions[id].map({ date > $0 }) ?? true,
               let market = bindings[id] { changedMarkets.insert(market) }
        }
        for (id, market) in bindings where oldBindings[id] != market { changedMarkets.insert(market) }
        // A genuine withdrawal changes the normalization denominator even if
        // no replacement observation clock exists. Never mix old/new vectors.
        for prior in beforeRows {
            let row = next[prior.key]
            if prior.verdict != nil && row?.verdict != prior.verdict
                || prior.winner != nil && row?.winner != prior.winner
                || prior.actual != nil && (prior.verdict != nil || prior.winner != nil)
                    && row?.actual != prior.actual { return held }
            if row?.priced != true {
                // Choosing a different whole winner book does not withdraw the
                // previous venue's still-valid price. A genuinely absent quote
                // does fence restoration of that book behind its own revision.
                if !prior.isWinnerQuote || incoming.openWinnerQuote == nil {
                    nextFence.withdrawn[prior.key] = prior.contributors
                }
                changedMarkets.formUnion(prior.markets)
            }
        }
        func newGrade(_ row: Row) -> Bool {
            let prior = before[row.key]
            return prior?.verdict == nil && row.verdict != nil
                || prior?.winner == nil && row.winner != nil
        }
        for row in nextRows where newGrade(row) { changedMarkets.formUnion(row.markets) }
        for row in nextRows {
            let prior = before[row.key]
            let terminal = newGrade(row)
            if !row.priced {
                nextFence.withdrawn[row.key] = row.contributors.union(prior?.contributors ?? [])
                continue
            }
            // A displayed quote must never hide a regressed/missing raw clock.
            for id in row.contributors {
                if let known = fence.revisions[id] {
                    if let date = clocks[id] {
                        guard date >= known else { return held }
                    } else if !terminal { return held }
                }
            }
            if terminal { nextFence.withdrawn.removeValue(forKey: row.key) }
            if !terminal, let removed = fence.withdrawn[row.key] {
                let contributors = removed.union(row.contributors)
                // An unrelated sibling revision cannot resurrect this row.
                guard !contributors.isEmpty,
                      contributors.allSatisfy({ clocks[$0] != nil }),
                      contributors.contains(where: { id in
                          guard let date = clocks[id] else { return false }
                          return fence.revisions[id].map { date > $0 } ?? true
                      }) else { return held }
                nextFence.withdrawn.removeValue(forKey: row.key)
            }
            if prior == nil, !terminal, !row.isWinnerQuote,
               !row.contributors.isEmpty,
               row.contributors.allSatisfy({ fence.revisions[$0] != nil }) {
                guard row.contributors.contains(where: { id in
                    guard let date = clocks[id], let old = fence.revisions[id] else { return false }
                    return date > old
                }) else { return held }
            }
            if let prior, prior.priced,
               prior.prices != row.prices || prior.source != row.source {
                guard terminal || !row.markets.isDisjoint(with: changedMarkets) else { return held }
            }
        }
        for (id, date) in clocks { nextFence.revisions[id] = max(date, nextFence.revisions[id] ?? date) }
        fence = nextFence
        return incoming
    }
}
