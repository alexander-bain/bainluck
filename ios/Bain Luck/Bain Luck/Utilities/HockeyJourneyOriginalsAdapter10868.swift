import SwiftUI

/// #10868 — THE HOCKEY JOURNEY SCREEN'S PRODUCTION ADAPTER, PART FOUR: "ALL
/// PROPS", THE ORIGINAL CATALOGUE AND ITS DETAILS.
///
/// PILLARS: FORMATTING / TRUTH. SHIP: on `nhl-journey` "All props" lists every
/// original market outcome the page serves, once each, in the page's own
/// catalogue order, and each original's Details print its own pregame chance,
/// its own later reading and its own venue grade — or that slot's own words.
///
/// It decides nothing the app does not already decide:
///
///   - membership, order  `QuestionCatalog9483.build`, the one catalogue the page
///     and currentness    already draws (`AllMarketsCatalogView9483`), with the
///                        page's status. Every outcome it lists is one original,
///                        in its order; nothing it omits is added. Its
///                        `Absence` is said in `AllMarketsCatalogView9483.priceText`'s
///                        words ("Period finished", "No recent probability
///                        update", "Probability unavailable").
///   - source rows        `build` keeps no ids, so each listed outcome is mapped
///                        back to its served row by build's OWN keys: the group
///                        id (family, source, trimmed market text, period,
///                        venue market id — `QuestionCatalog9483.build`'s `key`,
///                        mirrored in `groupKey`), then the outcome's label and
///                        threshold. Rows sharing all of that are
///                        indistinguishable to the catalogue and are taken in
///                        served order. Never an array position across groups.
///   - identity           `(source, market, side)` from the row's served ids:
///                        the served `source`; `_market_id` (else
///                        `_market_ids` joined with "+"); the
///                        `contributor_outcome_ids` joined with "+". A row with
///                        no market id uses its market text, and one with no
///                        outcome ids uses the row id
///                        `market_name-outcome_name` (`GameMarketPlayerProp.id`'s
///                        shape, part three's). A missing source is
///                        `unattributed`. Ids never come from a ticker, a label
///                        or a position.
///   - pregame reading    part three's bases (`NFLMilestoneCard9483.cards`):
///                        before the start (`HockeyJourneyContributionAdapter10868.hasStarted`)
///                        the catalogue's own price for the outcome, admitted
///                        only while `NFLMilestoneCard9483.isRecent` finds its
///                        own `observed_at` recent; once started the served
///                        `pregame_mark` of an over-side player-prop row, and
///                        for every other row type "No pregame chance" — no
///                        other row type is decoded with a mark, and a current
///                        or settled price is never relabelled pregame.
///   - later reading      during play only. The catalogue's admitted price is
///                        `.comparison(.current)`. A price the catalogue calls
///                        stale, with its own date, is `.comparison(.recorded)`
///                        — the catalogue's own price rule read at the row's
///                        own observation instant. Otherwise
///                        `.comparison(.current)` with the catalogue's absence
///                        words. A row the venue already settled shows no
///                        chance ("No current chance"), whatever its price.
///   - grade              after the final only, `.result`. A player prop is
///                        graded by `HockeyJourneyContributionAdapter10868.contractResult`
///                        (settlement, refused when the served `hit`
///                        disagrees); every other row by the same settlement
///                        rule: `is_winner` with a venue's own
///                        `resolution_source` (`OutcomeVerdict.isAuthoritative`,
///                        never the retraction). Words are `OutcomeVerdict`'s
///                        ("Won" / "Lost"). Unknown is not loss: no settlement
///                        is "Not yet confirmed".
///   - about              the venue through `SourceLabels.label`; no rule text
///                        is served on `/game-markets`, so rules are
///                        "Rules unavailable"; the served market and outcome ids.
///   - labels             a player prop "Subject: N+" reads "Kirill Kaprizov 2+
///                        points" through part three's words (`PropSubject`,
///                        `PlayerPropsStatLabel`, `PlayerPropsFamily`); every
///                        other original its catalogue label.
///   - words              `formatProbability`; part one's `clockWords`.
///
/// The host passes the event, `/game-markets`, now, the reader's calendar, the
/// tint, and its held selection, which is passed through unchanged for the
/// leaf to resolve by exact scope and identity. Nothing here fetches.
enum HockeyJourneyOriginalsAdapter10868 {
    typealias Details = OriginalMarketDetails9483

    /// What the host already holds, passed in unchanged.
    struct Host {
        let now: Date
        let calendar: Calendar
        let locale: Locale

        init(now: Date = Date(), calendar: Calendar = .current, locale: Locale = .current) {
            self.now = now
            self.calendar = calendar
            self.locale = locale
        }

        /// Part one's host, for its clock words only.
        var page: HockeyJourneyPageAdapter10868.Host {
            HockeyJourneyPageAdapter10868.Host(probabilityObservedAt: nil, now: now,
                                               calendar: calendar, locale: locale)
        }
    }

    /// The fixed words, the screen author's own where the author wrote them.
    enum Words {
        static let heading = "All props"
        static let emptyWords = "No retained originals for this game"
        static let unavailableChoice = "Unnamed original"
        /// `PlayerMilestoneComparison9483`'s words once play starts with no served mark.
        static let noPregameChance = "No pregame chance"
        static let savedBeforeStart = "Saved before the start"
        static let recorded = "Recorded"
        static let noCurrentChance = "No current chance"
        static let notYetConfirmed = "Not yet confirmed"
        static let noSettlement = "No settlement served"
        static let disputed = "Served settlement and grade disagree"
        static let rulesUnavailable = "Rules unavailable"
        static let marketID = "Market ID"
        static let outcomeID = "Outcome ID"
        static let unattributed = "unattributed"

        static func context(_ count: Int) -> String {
            count == 1 ? "1 original" : "\(count) originals"
        }
    }

    // MARK: - The page's originals

    /// The originals group for the page at `host.now`. No served outcome is no
    /// catalogue, which draws `emptyWords`.
    static func originals(_ event: EventDetail, markets: GameMarketsResponse?, host: Host, tint: Color,
                          selection: Details.Selection? = nil) -> HockeyJourneyPageOriginals10868 {
        let pagePhase = HockeyJourneyPageAdapter10868.phase(event, now: host.now)
        let started = HockeyJourneyContributionAdapter10868.hasStarted(event, now: host.now)
        let found = markets.map { matched($0, status: event.status, now: host.now) } ?? []
        let built = found.map { original($0, event: event, phase: pagePhase, started: started, host: host) }
        var labels: [Details.Identity: String] = [:]
        for (match, made) in zip(found, built) {
            labels[made.identity] = label(match.source, event: event)
        }
        return HockeyJourneyPageOriginals10868(
            catalogue: built.isEmpty ? nil : Details.Catalogue(scope: scope(event, phase: pagePhase), originals: built),
            selection: selection,
            labels: labels,
            heading: Words.heading,
            context: built.isEmpty ? nil : Words.context(built.count),
            emptyWords: Words.emptyWords,
            unavailableChoice: Words.unavailableChoice,
            tint: tint)
    }

    /// One catalogue per event and phase, as the screen's own scope spells it.
    static func scope(_ event: EventDetail, phase: HockeyJourneyPagePhase10868) -> String {
        "nhl:\(event.id):\(phase):originals"
    }

    // MARK: - Served rows

    /// One served outcome row in the catalogue's own input order, with the ids
    /// and grade the catalogue does not keep.
    struct Source: Equatable {
        let family: QuestionCatalog9483.Family
        /// The catalogue's own reading of the row (`QuestionCatalog9483.row`).
        let row: QuestionCatalog9483.Row
        /// The label the catalogue gives the outcome.
        let label: String
        let marketName: String
        let outcomeName: String
        let marketID: Int?
        let marketIDs: [Int]?
        let outcomeIDs: [Int]?
        let isWinner: Bool?
        let resolutionSource: String?
        /// The served player-prop row, for its mark, grade and label.
        let prop: GameMarketPlayerProp?
    }

    /// Every served outcome row, in the order `QuestionCatalog9483.build` reads
    /// them: totals, spreads, team totals, periods, closed periods, player props,
    /// matchups, other.
    static func sources(_ data: GameMarketsResponse) -> [Source] {
        func outcome(_ family: QuestionCatalog9483.Family, _ o: GameMarketOutcome,
                     row: QuestionCatalog9483.Row) -> Source {
            Source(family: family, row: row, label: catalogueLabel(o.outcomeName, market: o.marketName),
                   marketName: o.marketName, outcomeName: o.outcomeName, marketID: o._marketId,
                   marketIDs: o._marketIds, outcomeIDs: o.contributorOutcomeIds, isWinner: o.isWinner,
                   resolutionSource: o.resolutionSource, prop: nil)
        }
        var out: [Source] = []
        for o in data.totals ?? [] { out.append(outcome(.gameLines, o, row: QuestionCatalog9483.row(o))) }
        for o in data.spreads ?? [] { out.append(outcome(.gameLines, o, row: QuestionCatalog9483.row(o))) }
        for o in data.teamTotals ?? [] { out.append(outcome(.teamScoring, o, row: QuestionCatalog9483.row(o))) }
        for o in data.periodMarkets ?? [] { out.append(outcome(.periods, o, row: QuestionCatalog9483.row(o))) }
        for closed in data.closedPeriodMarkets ?? [] {
            var row = QuestionCatalog9483.row(closed.row)
            row.windowClosed = closed.windowClosed == true
            out.append(outcome(.periods, closed.row, row: row))
        }
        for p in data.playerProps ?? [] {
            out.append(Source(family: .playerProps, row: QuestionCatalog9483.row(p),
                              label: catalogueLabel(p.outcomeName, market: p.marketName),
                              marketName: p.marketName, outcomeName: p.outcomeName, marketID: p._marketId,
                              marketIDs: p._marketIds, outcomeIDs: p.contributorOutcomeIds, isWinner: p.isWinner,
                              resolutionSource: p.resolutionSource, prop: p))
        }
        for matchup in data.matchups ?? [] {
            for o in matchup.outcomes {
                // `build`'s own matchup row: no period, no market id, the name unchanged.
                let row = QuestionCatalog9483.Row(marketName: matchup.marketName, outcomeName: o.name,
                                                  probability: o.probability, pricesOutcome: true,
                                                  source: matchup.source, observedAt: o.observedAt)
                out.append(Source(family: .matchups, row: row, label: o.name, marketName: matchup.marketName,
                                  outcomeName: o.name, marketID: matchup._marketId, marketIDs: matchup._marketIds,
                                  outcomeIDs: o.contributorOutcomeIds, isWinner: o.isWinner,
                                  resolutionSource: o.resolutionSource, prop: nil))
            }
        }
        for o in data.other ?? [] {
            out.append(Source(family: .other, row: QuestionCatalog9483.row(o),
                              label: catalogueLabel(o.outcomeName, market: o.marketName),
                              marketName: o.marketName, outcomeName: o.outcomeName, marketID: o._marketId,
                              marketIDs: o._marketIds, outcomeIDs: o.contributorOutcomeIds, isWinner: o.isWinner,
                              resolutionSource: o.resolutionSource, prop: nil))
        }
        return out
    }

    /// `build`'s `addRows` label: the trimmed outcome name, or the market text.
    static func catalogueLabel(_ outcomeName: String, market: String) -> String {
        let label = outcomeName.trimmingCharacters(in: .whitespacesAndNewlines)
        return label.isEmpty ? market : label
    }

    /// `QuestionCatalog9483.build`'s group key, spelled exactly as `add` spells it.
    static func groupKey(_ family: QuestionCatalog9483.Family, _ row: QuestionCatalog9483.Row) -> String {
        let question = row.marketName.trimmingCharacters(in: .whitespacesAndNewlines)
        return [family.rawValue, String(describing: row.source), question,
                String(describing: row.period), String(describing: row.marketId)]
            .joined(separator: "\u{1F}")
    }

    static func outcomeKey(group: String, label: String, threshold: Double?) -> String {
        [group, label, String(describing: threshold)].joined(separator: "\u{1E}")
    }

    /// One listed outcome and the served row it came from.
    struct Match: Equatable {
        let group: QuestionCatalog9483.Group
        let outcome: QuestionCatalog9483.Outcome
        let source: Source
    }

    /// Every outcome `build` lists, in its order, with its served row.
    static func matched(_ data: GameMarketsResponse, status: String?, now: Date) -> [Match] {
        var buckets: [String: [Source]] = [:]
        for source in sources(data) {
            let key = outcomeKey(group: groupKey(source.family, source.row), label: source.label,
                                 threshold: finite(source.row.threshold))
            buckets[key, default: []].append(source)
        }
        var out: [Match] = []
        for group in QuestionCatalog9483.build(data, status: status, now: now) {
            for outcome in group.outcomes {
                let key = outcomeKey(group: group.id, label: outcome.label, threshold: outcome.threshold)
                guard var bucket = buckets[key], !bucket.isEmpty else { continue }
                let source = bucket.removeFirst()
                buckets[key] = bucket
                out.append(Match(group: group, outcome: outcome, source: source))
            }
        }
        return out
    }

    // MARK: - One original

    static func original(_ match: Match, event: EventDetail, phase: HockeyJourneyPagePhase10868,
                         started: Bool, host: Host) -> Details.Original {
        let mode: Details.Mode
        let later: Details.Reading?
        let grade: Details.Grade?
        switch phase {
        case .before:
            mode = .pregame
            later = nil
            grade = nil
        case .live:
            let reading = laterReading(match, event: event, host: host)
            mode = reading.mode
            later = reading.later
            grade = nil
        case .final:
            mode = .result
            later = nil
            grade = contractGrade(match.source)
        }
        return Details.Original(
            identity: identity(of: match.source), title: match.group.question, outcome: match.outcome.label,
            mode: mode, pregame: pregameReading(match, started: started, event: event, host: host),
            later: later, grade: grade, about: aboutSection(match.source))
    }

    static func identity(of source: Source) -> Details.Identity {
        let venue = source.row.source.flatMap { $0.isEmpty ? nil : $0 } ?? Words.unattributed
        let market = source.marketID.map(String.init) ?? ids(source.marketIDs, separator: "+") ?? source.marketName
        let side = ids(source.outcomeIDs, separator: "+") ?? "\(source.marketName)-\(source.outcomeName)"
        return Details.Identity(source: venue, market: market, side: side)
    }

    /// Before the start: the catalogue's own price on its own recent clock.
    /// Once started: an over-side player prop's served mark, or no pregame chance.
    static func pregameReading(_ match: Match, started: Bool, event: EventDetail, host: Host) -> Details.Reading {
        let venue = SourceLabels.label(for: match.source.row.source)
        if started {
            guard let prop = match.source.prop,
                  QuestionCatalog9483.lineSide(match.source.row) == .over,
                  let mark = admissible(prop.pregameMark)
            else { return .missing(Words.noPregameChance) }
            return .value(formatProbability(mark), placement: mark,
                          provenance: joined([Words.savedBeforeStart, venue]))
        }
        guard let price = admissible(match.outcome.probability) else {
            return .missing(absenceWords(match.outcome, status: event.status))
        }
        guard NFLMilestoneCard9483.isRecent(match.outcome.observedAt, now: host.now),
              let at = match.outcome.observedAt?.asDate
        else { return .missing(AllMarketsCatalogView9483.noRecentPrice) }
        return .value(formatProbability(price), placement: price, provenance: joined([clock(at, host), venue]))
    }

    /// During play: the catalogue's current price, else a dated stale price as
    /// a recorded one, else the catalogue's words. A settled row shows no chance.
    static func laterReading(_ match: Match, event: EventDetail, host: Host)
        -> (mode: Details.Mode, later: Details.Reading) {
        let venue = SourceLabels.label(for: match.source.row.source)
        let settled = settlement(isWinner: match.source.isWinner, resolutionSource: match.source.resolutionSource) != nil
        if let price = admissible(match.outcome.probability) {
            if settled { return (.comparison(.current), .missing(Words.noCurrentChance)) }
            let when = match.outcome.observedAt?.asDate.map { "\(Words.recorded) \(clock($0, host))" }
                ?? Details.timeUnknown
            return (.comparison(.current),
                    .value(formatProbability(price), placement: price, provenance: joined([when, venue])))
        }
        if match.outcome.absence == .stale, let at = match.source.row.observedAt?.asDate,
           let price = admissible(QuestionCatalog9483.reading(match.source.row, status: event.status, now: at).probability) {
            if settled { return (.comparison(.current), .missing(Words.noCurrentChance)) }
            return (.comparison(.recorded),
                    .value(formatProbability(price), placement: price,
                           provenance: joined(["\(Words.recorded) \(clock(at, host))", venue])))
        }
        return (.comparison(.current), .missing(absenceWords(match.outcome, status: event.status)))
    }

    /// `AllMarketsCatalogView9483.priceText`'s words for an outcome with no price.
    static func absenceWords(_ outcome: QuestionCatalog9483.Outcome, status: String?) -> String {
        AllMarketsCatalogView9483.priceText(outcome, status: status) ?? AllMarketsCatalogView9483.unavailablePrice
    }

    /// The served settlement's verdict, or nil: a winner flag with a venue's own
    /// `resolution_source`, never the retraction. Part three's rule
    /// (`HockeyJourneyContributionAdapter10868.settlement`) on any row type.
    static func settlement(isWinner: Bool?, resolutionSource: String?) -> Bool? {
        guard let won = isWinner, let source = resolutionSource,
              source != OutcomeVerdict.retractedResolutionSource,
              OutcomeVerdict.isAuthoritative(source) else { return nil }
        return won
    }

    /// After the final. Unknown is not loss.
    static func contractGrade(_ source: Source) -> Details.Grade {
        let served = settlement(isWinner: source.isWinner, resolutionSource: source.resolutionSource)
        let won: Bool?
        if let prop = source.prop {
            switch HockeyJourneyContributionAdapter10868.contractResult(prop, count: nil, threshold: prop.threshold ?? 0) {
            case .reached: won = true
            case .missed: won = false
            case .unconfirmed: won = nil
            }
        } else {
            won = served
        }
        guard let won else {
            return Details.Grade(words: Words.notYetConfirmed, provenance: served == nil ? Words.noSettlement : Words.disputed)
        }
        let verdict: OutcomeVerdict = won ? .won : .lost
        let venue = SourceLabels.label(for: source.row.source)
        return Details.Grade(words: verdict.label, provenance: venue.map { "Settled by \($0)" } ?? "Venue settlement")
    }

    static func aboutSection(_ source: Source) -> Details.About {
        var rows: [Details.Row] = []
        if let market = source.marketID.map(String.init) ?? ids(source.marketIDs, separator: ", ") {
            rows.append(Details.Row(label: Words.marketID, value: market))
        }
        if let outcomes = ids(source.outcomeIDs, separator: ", ") {
            rows.append(Details.Row(label: Words.outcomeID, value: outcomes))
        }
        return Details.About(source: SourceLabels.label(for: source.row.source),
                             rules: .unavailable(Words.rulesUnavailable), provenance: rows, historicalQuote: nil)
    }

    /// "Kirill Kaprizov 2+ points" for a player prop whose outcome is exactly
    /// "Subject: N+"; otherwise the catalogue's label.
    static func label(_ source: Source, event: EventDetail) -> String {
        guard let prop = source.prop, let subject = HockeyJourneyContributionAdapter10868.subject(prop),
              let threshold = prop.threshold, threshold.isFinite else { return source.label }
        let target = PlayerPropsFamily.targetLabel(threshold)
        let parts = prop.outcomeName.split(separator: ":", maxSplits: 1)
        guard parts.count == 2, parts[1].trimmingCharacters(in: .whitespaces) == target else { return source.label }
        let stat = PlayerPropsFamily.name(statLabel: PlayerPropsStatLabel.display(
            marketName: prop.marketName, homeTeam: event.homeTeam, awayTeam: event.awayTeam, player: subject))
        return "\(subject) \(target) \(stat.lowercased())"
    }

    // MARK: - Words

    private static func clock(_ date: Date, _ host: Host) -> String {
        HockeyJourneyPageAdapter10868.clockWords(date, host: host.page)
    }

    private static func ids(_ values: [Int]?, separator: String) -> String? {
        guard let values, !values.isEmpty else { return nil }
        return values.map(String.init).joined(separator: separator)
    }

    private static func finite(_ value: Double?) -> Double? {
        guard let value, value.isFinite else { return nil }
        return value
    }

    /// A finite probability in 0...1, or nil. A real 0 stays.
    private static func admissible(_ value: Double?) -> Double? {
        guard let value, value.isFinite, (0...1).contains(value) else { return nil }
        return value
    }

    private static func joined(_ parts: [String?]) -> String? {
        let kept = parts.compactMap { $0 }.filter { !$0.isEmpty }
        return kept.isEmpty ? nil : kept.joined(separator: " · ")
    }
}
