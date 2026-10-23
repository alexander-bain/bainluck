import Foundation

/// #9483 / #10868 — every market a game page serves, reachable from one
/// catalog. The phone's copy of the web's `lib/questionCatalog.ts` (#10809,
/// Atlas v6 slice 1), and it makes the same decisions.
///
/// The maps and cards above draw the markets they can draw. Some served rows
/// reach no card at all (a map refuses a line in the wrong unit, the special
/// card needs three rows). The catalog is the route to the rest: every row of
/// `/game-markets` lands in exactly one group, findable by family or search.
///
/// GROUPING. A group is one venue's one original market: family, source, the
/// market text exactly as served, period, and the venue market id where the
/// row carries one. Two venues asking the same thing stay two groups.
///
/// QUOTES. No new price rule:
///   - a row type that carries a per-outcome `probability` prints it;
///   - otherwise `over_probability`, only on an outcome that names the over
///     side — never on the Under leg and never complemented (gotcha #17);
///   - during play, a price last seen more than `SourceAge.liveStaleAfter`
///     ago prints nothing;
///   - after the final, nothing: the graded cards above own results;
///   - a closed period row is never priced (#10850).
///
/// ABSENCE (#10877). An outcome that prints no number keeps WHY, from the
/// input that knew it: the final, a period the server says closed
/// (`window_closed: true`), a stale live observation, or no known reason. A
/// missing number alone never reads as a closed period or a result.
///
/// One divergence from web: web tests whether a row HAS the `probability`
/// key; Swift cannot tell an absent key from a null one, so spread/total/period
/// rows use `probability` when it is a number and otherwise the over-side rule.
/// Only a row serving `probability: null` beside an `over_probability` on an
/// over-named outcome can differ, and then it prints that line's own Over
/// chance — the number web's flat line list prints for the same row.
///
/// PURE: no I/O, no SwiftUI. `now` is a parameter.
nonisolated enum QuestionCatalog9483 {

    /// The family chips, in the order a reader meets them on the page.
    enum Family: String, CaseIterable, Sendable {
        case gameLines = "Game lines"
        case teamScoring = "Team scoring"
        case periods = "Periods"
        case playerProps = "Player props"
        case matchups = "Matchups"
        case other = "Other"
    }

    /// #10877 — why an outcome prints no number.
    nonisolated enum Absence: Equatable, Sendable {
        /// After the final: the graded cards above own results.
        case settled
        /// Served in `closed_period_markets` with `window_closed: true`. Not a
        /// grade and not a winner — only that the period's window is over.
        case periodFinished
        /// During play, last observed longer ago than `SourceAge.liveStaleAfter`.
        case stale
        /// No usable number and no known reason.
        case unavailable
    }

    struct Outcome: Equatable, Sendable {
        let label: String
        let threshold: Double?
        /// The number to print, or nil when this row may not print one.
        let probability: Double?
        let observedAt: String?
        /// Why `probability` is nil; nil exactly when it prints.
        let absence: Absence?

        nonisolated init(label: String, threshold: Double?, probability: Double?, observedAt: String?,
                         absence: Absence = .unavailable) {
            self.label = label
            self.threshold = threshold
            self.probability = probability
            self.observedAt = observedAt
            self.absence = probability == nil ? absence : nil
        }
    }

    struct Group: Identifiable, Equatable, Sendable {
        let id: String
        let family: Family
        let question: String
        /// Reader-facing venue name (`SourceLabels`), or nil when we cannot
        /// name the venue.
        let venue: String?
        let period: String?
        var outcomes: [Outcome]
    }

    /// One served row, as much of it as the catalog reads.
    struct Row: Equatable, Sendable {
        var marketName: String
        var outcomeName: String
        var threshold: Double? = nil
        var probability: Double? = nil
        /// Whether this row type prices its outcome directly (`other`,
        /// matchups) rather than through an over line (props).
        var pricesOutcome: Bool
        var overProbability: Double? = nil
        var source: String? = nil
        var period: String? = nil
        var observedAt: String? = nil
        var inverted: Bool = false
        var marketId: Int? = nil
        /// A `closed_period_markets` row that says `window_closed: true`.
        var windowClosed: Bool = false
    }

    enum Side: Equatable { case over, under, unreadable }

    /// web `propOutcomeSide`: "Over"/"Yes" and an "N+" rung are the over side.
    static func propOutcomeSide(_ outcomeName: String?) -> Side {
        let o = (outcomeName ?? "").trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        if o.isEmpty { return .unreadable }
        if o == "over" || o == "yes" { return .over }
        if o == "under" || o == "no" { return .under }
        if o.range(of: #"\d+\s*\+"#, options: .regularExpression) != nil { return .over }
        return .unreadable
    }

    /// Which side of the line an outcome names; unreadable prints no over price.
    static func lineSide(_ row: Row) -> Side {
        if row.inverted { return .under }
        let side = propOutcomeSide(row.outcomeName)
        if side != .unreadable { return side }
        if row.outcomeName.range(of: #"\bunder\b"#, options: [.regularExpression, .caseInsensitive]) != nil {
            return .under
        }
        if row.outcomeName.range(of: #"\bover\b"#, options: [.regularExpression, .caseInsensitive]) != nil {
            return .over
        }
        return .unreadable
    }

    private static func finite(_ value: Double?) -> Double? {
        guard let value, value.isFinite else { return nil }
        return value
    }

    static func quote(_ row: Row, status: String?, now: Date, closed: Bool = false) -> Double? {
        reading(row, status: status, now: now, closed: closed).probability
    }

    /// The number to print, or why there is none (#10877). `closed` withholds
    /// the number; only a row that also says `windowClosed` is a finished period.
    static func reading(
        _ row: Row, status: String?, now: Date, closed: Bool = false
    ) -> (probability: Double?, absence: Absence?) {
        if SettledQuote.isSettled(status) { return (nil, .settled) }
        if closed { return (nil, row.windowClosed ? .periodFinished : .unavailable) }
        let live = !SettledQuote.isPregame(status)
        if live && SourceAge.isStale(row.observedAt, now: now, after: SourceAge.liveStaleAfter) {
            return (nil, .stale)
        }
        let price: Double?
        if row.pricesOutcome {
            price = finite(row.probability)
        } else if let direct = finite(row.probability) {
            price = direct
        } else {
            price = lineSide(row) == .over ? finite(row.overProbability) : nil
        }
        if let price { return (price, nil) }
        return (nil, .unavailable)
    }

    static func row(_ o: GameMarketOutcome) -> Row {
        Row(marketName: o.marketName, outcomeName: o.outcomeName, threshold: o.threshold,
            probability: o.probability, pricesOutcome: false, overProbability: o.overProbability,
            source: o.source, period: o.period, observedAt: o.observedAt,
            inverted: o._inverted == true, marketId: o._marketId)
    }

    static func row(_ p: GameMarketPlayerProp) -> Row {
        Row(marketName: p.marketName, outcomeName: p.outcomeName, threshold: p.threshold,
            pricesOutcome: false, overProbability: p.overProbability, source: p.source,
            observedAt: p.observedAt, inverted: p._inverted == true, marketId: p._marketId)
    }

    static func row(_ o: GameMarketOther) -> Row {
        Row(marketName: o.marketName, outcomeName: o.outcomeName, probability: o.probability,
            pricesOutcome: true, source: o.source, observedAt: o.observedAt, marketId: o._marketId)
    }

    static func build(_ data: GameMarketsResponse, status: String?, now: Date = Date()) -> [Group] {
        var order: [String] = []
        var groups: [String: Group] = [:]

        func add(_ family: Family, _ row: Row,
                 _ reading: (probability: Double?, absence: Absence?), _ label: String) {
            let question = row.marketName.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !question.isEmpty else { return }
            // `String(describing:)` keeps nil distinct from every served value.
            let key = [family.rawValue, String(describing: row.source), question,
                       String(describing: row.period), String(describing: row.marketId)]
                .joined(separator: "\u{1F}")
            if groups[key] == nil {
                order.append(key)
                groups[key] = Group(id: key, family: family, question: question,
                                    venue: SourceLabels.label(for: row.source),
                                    period: row.period, outcomes: [])
            }
            groups[key]?.outcomes.append(Outcome(
                label: label, threshold: finite(row.threshold),
                probability: reading.probability, observedAt: row.observedAt,
                absence: reading.absence ?? .unavailable))
        }

        func addRows(_ family: Family, _ rows: [Row], closed: Bool = false) {
            // An Under row carries its Over twin's price, so beside that twin it
            // adds a blank outcome and nothing else. An Under with no Over twin
            // stays listed: the market must remain reachable.
            func lineKey(_ r: Row) -> String {
                [String(describing: r.source), r.marketName, String(describing: r.period),
                 String(describing: r.threshold)].joined(separator: "\u{1F}")
            }
            let overLines = Set(rows.filter { lineSide($0) == .over }.map(lineKey))
            for r in rows {
                if !r.pricesOutcome, lineSide(r) == .under, overLines.contains(lineKey(r)) { continue }
                let label = r.outcomeName.trimmingCharacters(in: .whitespacesAndNewlines)
                add(family, r, reading(r, status: status, now: now, closed: closed),
                    label.isEmpty ? r.marketName : label)
            }
        }

        addRows(.gameLines, (data.totals ?? []).map(row))
        addRows(.gameLines, (data.spreads ?? []).map(row))
        addRows(.teamScoring, (data.teamTotals ?? []).map(row))
        addRows(.periods, (data.periodMarkets ?? []).map(row))
        addRows(.periods, (data.closedPeriodMarkets ?? []).map { closedRow in
            var r = row(closedRow.row)
            r.windowClosed = closedRow.windowClosed == true
            return r
        }, closed: true)
        addRows(.playerProps, (data.playerProps ?? []).map(row))
        for matchup in data.matchups ?? [] {
            for outcome in matchup.outcomes {
                let r = Row(marketName: matchup.marketName, outcomeName: outcome.name,
                            probability: outcome.probability, pricesOutcome: true,
                            source: matchup.source, observedAt: outcome.observedAt)
                add(.matchups, r, reading(r, status: status, now: now), outcome.name)
            }
        }
        addRows(.other, (data.other ?? []).map(row))

        let families = Family.allCases
        return order.compactMap { groups[$0] }.enumerated().sorted {
            let a = families.firstIndex(of: $0.element.family) ?? 0
            let b = families.firstIndex(of: $1.element.family) ?? 0
            return a != b ? a < b : $0.offset < $1.offset
        }.map(\.element)
    }

    /// Every source outcome the payload carries, for the accounting guard: the
    /// catalog drops only an Under leg whose Over twin it already lists.
    static func sourceOutcomeCount(_ data: GameMarketsResponse) -> Int {
        (data.totals?.count ?? 0) + (data.spreads?.count ?? 0) + (data.teamTotals?.count ?? 0)
            + (data.periodMarkets?.count ?? 0) + (data.closedPeriodMarkets?.count ?? 0)
            + (data.playerProps?.count ?? 0) + (data.other?.count ?? 0)
            + (data.matchups ?? []).reduce(0) { $0 + $1.outcomes.count }
    }
}
