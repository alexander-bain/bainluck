import Foundation

/// Orders the complete rendered projection, not each normalized percentage.
/// Row revision is an ordering clock only; it never earns a fresh/live badge.
nonisolated enum GameMarketsPriceReconciliation {
    struct Fence {
        var revisions: [String: Date] = [:]
        var withdrawn: [String: Set<String>] = [:]
        var winnerQuotes = FinalGameWinnerQuoteFence()
    }

    struct Row: Equatable {
        var key: String
        let prices: [Double?]
        let source: String?
        let markets: Set<Int>
        let contributors: Set<String>
        let verdict: Bool?
        let winner: Bool?
        let actual: Double?
        /// The market-qualified key, before any contributor refinement.
        var base = ""
        var priced: Bool { prices.contains { $0 != nil } }
        var isWinnerQuote: Bool { key.hasPrefix("finalWinner:") }
        /// #9585 — no market and no contributor id: nothing can order this
        /// row's quote, so it may display as served but never fence or freeze.
        var isUnordered: Bool { markets.isEmpty && contributors.isEmpty && !isWinnerQuote }
    }

    /// #9585 — a display name is not an identity: Bears–Eagles served four
    /// `Both teams to score / Yes` rows from four markets. The key is the
    /// section, the name, the durable market ids and, whenever present, the
    /// row's own contributor ids — a function of the row alone, so a row keeps
    /// its identity (and its grade and withdrawal fences) whichever siblings
    /// come and go. Exact duplicates coalesce. Rows still conflicting are
    /// returned apart, so they never order or hold the rest of the page.
    /// Never position, price or clock.
    static func identity(_ row: Row) -> Row {
        var row = row
        let markets = row.markets.sorted().map(String.init)
        if !markets.isEmpty { row.key += "#m" + markets.joined(separator: ",") }
        row.base = row.key
        let contributors = row.contributors.sorted()
        if !contributors.isEmpty { row.key += "#c" + contributors.joined(separator: ",") }
        return row
    }

    static func identified(_ raw: [Row]) -> (rows: [Row], ambiguous: [Row]) {
        var order: [String] = []
        var groups: [String: [Row]] = [:]
        for row in raw.map(identity) {
            if groups[row.key] == nil { order.append(row.key) }
            groups[row.key, default: []].append(row)
        }
        var unique: [Row] = []
        var conflicted: [Row] = []
        for key in order {
            let group = groups[key] ?? []
            if group.allSatisfy({ $0 == group[0] }) { unique.append(group[0]) } else { conflicted += group }
        }
        return (unique, conflicted)
    }

    private static func markets(_ one: Int?, _ many: [Int]?) -> Set<Int> {
        Set((many ?? []) + (one.map { [$0] } ?? []))
    }
    private static func ids(_ values: [Int]?) -> Set<String> { Set((values ?? []).map(String.init)) }
    private static func row(_ prop: GameMarketPlayerProp) -> Row {
        Row(key: "props:\(prop.id)", prices: [prop.overProbability], source: prop.source,
            markets: markets(prop._marketId, prop._marketIds), contributors: ids(prop.contributorOutcomeIds),
            verdict: prop.hit, winner: prop.isWinner, actual: prop.actual)
    }
    private static func row(_ section: String, _ entry: GameMarketOutcome) -> Row {
        Row(key: "\(section):\(entry.id)", prices: [entry.probability, entry.overProbability], source: entry.source,
            markets: markets(entry._marketId, entry._marketIds), contributors: ids(entry.contributorOutcomeIds),
            verdict: nil, winner: entry.isWinner, actual: nil)
    }
    private static func row(_ entry: GameMarketOther) -> Row {
        Row(key: "other:\(entry.id)", prices: [entry.probability], source: entry.source,
            markets: markets(entry._marketId, entry._marketIds), contributors: ids(entry.contributorOutcomeIds),
            verdict: nil, winner: entry.isWinner, actual: nil)
    }
    private static func rows(_ matchup: GameMarketMatchup) -> [Row] {
        matchup.outcomes.map {
            Row(key: "matchups:\(matchup.id):\($0.name)", prices: [$0.probability], source: matchup.source,
                markets: markets(matchup._marketId, matchup._marketIds),
                contributors: ids($0.contributorOutcomeIds ?? matchup.contributorOutcomeIds),
                verdict: nil, winner: $0.isWinner, actual: nil)
        }
    }
    /// #10236 — its own section: one outcome can sit in both `player_props`
    /// and the During matrix, and the two are different published answers.
    /// The whole projection is the blend AND each contributor's own value, so
    /// a detail sheet can never show a contributor that moved without its clock.
    /// A row with no quoted chance publishes no price at all.
    private static func row(_ entry: DuringPropRow) -> Row {
        let quoted = entry.current.quotedProbability
        return Row(key: "duringProps:\(entry.questionKey)",
            prices: quoted == nil ? [nil] : [quoted] + entry.contributors.map(\.probability),
            source: entry.current.basis,
            markets: markets(entry._marketId, entry._marketIds), contributors: ids(entry.contributorOutcomeIds),
            verdict: entry.result?.hit, winner: entry.result?.isWinner, actual: entry.result?.actual)
    }
    private static let sections: [(String, KeyPath<GameMarketsResponse, [GameMarketOutcome]?>)] = [
        ("spreads", \.spreads), ("totals", \.totals), ("teamTotals", \.teamTotals), ("period", \.periodMarkets)]

    static func rows(_ body: GameMarketsResponse) -> [Row] {
        var result = (body.playerProps ?? []).map(row)
        for (section, path) in sections { result += (body[keyPath: path] ?? []).map { row(section, $0) } }
        result += (body.other ?? []).map(row)
        for matchup in body.matchups ?? [] { result += rows(matchup) }
        result += (body.duringPlayerProps?.rows ?? []).map(row)
        if let quote = body.openWinnerQuote {
            result.append(Row(key: "finalWinner:\(quote.marketId)",
                prices: quote.outcomes.sorted { $0.outcomeId < $1.outcomeId }.map { $0.probability },
                source: quote.source, markets: [quote.marketId],
                contributors: quote.contributorOutcomeIds, verdict: nil, winner: nil, actual: nil))
        }
        return result
    }

    /// #9585 — the body a reader is shown never carries a conflicting group:
    /// each one is replaced by the held page's own verified entry for that
    /// identity (its grade, actual and withdrawal state intact), or withheld
    /// when nothing verified exists. Every other entry is the incoming one.
    private static func quarantined(_ body: GameMarketsResponse, keys ambiguous: Set<String>,
                                    held: GameMarketsResponse?) -> GameMarketsResponse {
        guard !ambiguous.isEmpty else { return body }
        func keys(_ rows: [Row]) -> [String] { rows.map { identity($0).key } }
        func replaced<T>(_ incoming: [T]?, _ held: [T]?, group: (T) -> String, rows: (T) -> [Row]) -> [T]? {
            guard let incoming else { return nil }
            var verified: [String: T] = [:]
            for entry in held ?? [] where verified[group(entry)] == nil { verified[group(entry)] = entry }
            var placed = Set<String>()
            return incoming.compactMap { entry in
                guard keys(rows(entry)).contains(where: ambiguous.contains) else { return entry }
                guard placed.insert(group(entry)).inserted else { return nil }
                return verified[group(entry)]
            }
        }
        func flat<T>(_ incoming: [T]?, _ held: [T]?, _ row: (T) -> Row) -> [T]? {
            replaced(incoming, held, group: { identity(row($0)).key }, rows: { [row($0)] })
        }
        var body = body
        body.playerProps = flat(body.playerProps, held?.playerProps, row)
        body.spreads = flat(body.spreads, held?.spreads) { row("spreads", $0) }
        body.totals = flat(body.totals, held?.totals) { row("totals", $0) }
        body.teamTotals = flat(body.teamTotals, held?.teamTotals) { row("teamTotals", $0) }
        body.periodMarkets = flat(body.periodMarkets, held?.periodMarkets) { row("period", $0) }
        body.other = flat(body.other, held?.other, row)
        body.matchups = replaced(body.matchups, held?.matchups, group: { "matchups:\($0.id)" }, rows: rows)
        if var during = body.duringPlayerProps {
            during.rows = flat(during.rows, held?.duringPlayerProps?.rows, row) ?? []
            body.duringPlayerProps = during
        }
        return body
    }

    /// #9585 — every key `quarantined` keeps off the page: the conflicting
    /// rows, and every leg of a matchup one of them sits in (a matchup is held
    /// or withheld whole). None of these values is published, so none may
    /// lend, spend or be refused by an ordering clock.
    private static func unpublished(_ body: GameMarketsResponse, ambiguous: Set<String>) -> Set<String> {
        var keys = ambiguous
        for matchup in body.matchups ?? [] {
            let legs = rows(matchup).map { identity($0).key }
            if legs.contains(where: ambiguous.contains) { keys.formUnion(legs) }
        }
        return keys
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
        let identity = identified(rows(incoming))
        let ambiguous = Set(identity.ambiguous.map(\.key))
        let hidden = unpublished(incoming, ambiguous: ambiguous)
        let nextRows = identity.rows.filter { !hidden.contains($0.key) }
        let next = Dictionary(uniqueKeysWithValues: nextRows.map { ($0.key, $0) })
        // A contributor seen only on unpublished rows neither orders nor is
        // ordered: its clock waits until its row is shown again. One also on
        // a published row stays fully ordered.
        let unordered = Set((identity.ambiguous + identity.rows.filter { hidden.contains($0.key) })
            .flatMap(\.contributors))
            .subtracting(nextRows.flatMap(\.contributors))
        let clocks = (incoming.outcomeRevisionAt ?? [:]).compactMapValues {
            FuturesPriceReconciliation.observationDate($0)
        }
        let published = quarantined(incoming, keys: ambiguous, held: held)
        guard let held else {
            fence.revisions = clocks.filter { !unordered.contains($0.key) }
            for row in nextRows where !row.priced && !row.isUnordered { fence.withdrawn[row.key] = row.contributors }
            return published
        }
        guard incoming.eventId == held.eventId else { return held }
        if EventState.isFinished(held.status) {
            guard EventState.isFinished(incoming.status),
                  held.homeScore == nil || incoming.homeScore == held.homeScore,
                  held.awayScore == nil || incoming.awayScore == held.awayScore else { return held }
        }
        let beforeRows = identified(rows(held)).rows
        let before = Dictionary(uniqueKeysWithValues: beforeRows.map { ($0.key, $0) })
        var nextFence = fence
        let bindings = incoming.outcomeMarketIds ?? [:]
        let oldBindings = held.outcomeMarketIds ?? [:]
        var changedMarkets = Set<Int>()
        for (id, date) in clocks {
            guard !unordered.contains(id) else { continue }
            if let prior = fence.revisions[id], date < prior { return held }
            if fence.revisions[id].map({ date > $0 }) ?? true,
               let market = bindings[id] { changedMarkets.insert(market) }
        }
        for (id, market) in bindings where oldBindings[id] != market && !unordered.contains(id) {
            changedMarkets.insert(market)
        }
        // A genuine withdrawal changes the normalization denominator even if
        // no replacement observation clock exists. Never mix old/new vectors.
        for prior in beforeRows where !hidden.contains(prior.key) {
            let row = next[prior.key]
            if prior.verdict != nil && row?.verdict != prior.verdict
                || prior.winner != nil && row?.winner != prior.winner
                || prior.actual != nil && (prior.verdict != nil || prior.winner != nil)
                    && row?.actual != prior.actual { return held }
            if row?.priced != true {
                // Choosing a different whole winner book does not withdraw the
                // previous venue's still-valid price. A genuinely absent quote
                // does fence restoration of that book behind its own revision.
                if !prior.isUnordered, !prior.isWinnerQuote || incoming.openWinnerQuote == nil {
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
                if !row.isUnordered {
                    nextFence.withdrawn[row.key] = row.contributors.union(prior?.contributors ?? [])
                }
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
            if let prior, prior.priced, !row.isUnordered,
               prior.prices != row.prices || prior.source != row.source {
                guard terminal || !row.markets.isDisjoint(with: changedMarkets) else { return held }
            }
        }
        for (id, date) in clocks where !unordered.contains(id) {
            nextFence.revisions[id] = max(date, nextFence.revisions[id] ?? date)
        }
        fence = nextFence
        return published
    }
}
