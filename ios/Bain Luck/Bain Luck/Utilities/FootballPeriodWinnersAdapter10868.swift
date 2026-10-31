import SwiftUI

/// #10868 — THE FOOTBALL SCREEN'S PERIOD-WINNER STORY: the approved final
/// quarter-winner card on the completed `nfl-live` page, before the player
/// stories.
///
/// PILLARS: FORMATTING / TRUTH / DISCOVER. SHIP: after an NFL game a reader
/// sees, for each quarter, every side's own pregame chance of winning that
/// quarter beside the quarter's actual points and a separate check for the side
/// whose contract won — all twelve outcomes selectable, each with its own
/// Details — so a quarter that defied its pregame chances is visible at a
/// glance and a settled result is never read as a probability.
///
/// What is ADMITTED, and from where:
///   - the originals    each bound original must be exactly ONE served row of
///                      this event's own `/game-markets` (`period_markets`, or a
///                      closed period's row), matched by its exact venue key,
///                      market id, contributor outcome ids and typed market type —
///                      never by a market or outcome name. A bound original no
///                      longer served is shown as withdrawn; one served twice is
///                      ambiguous; neither borrows a chance or a result.
///   - the result       that row's own venue settlement, through the app's one
///                      rule (`HockeyJourneyOriginalsAdapter10868.settlement`:
///                      a winner flag with an authoritative `resolution_source`).
///                      Never a 0/1 quote, never the points. Unknown is
///                      "Result unconfirmed", never a loss.
///   - the pregame dot  the owner's bound historical trade for that original:
///                      finite, strictly between 0 and 1, positive volume, a
///                      minute- or hour-ending candle that ENDS BEFORE the
///                      verified kickoff. Shown as the venue traded it — three
///                      sides of a quarter are never normalized to 100%.
///   - the points       the event's own stored line score
///                      (`EventDetail.boxScoreData` through `StoredLineScore`, the
///                      app's line-score rule), a capture separate from the
///                      markets; the provenance is the score's own recorded time,
///                      never an invented quarter end.
///   - the labels       `PeriodLabel.lineScoreColumn` (spoken `PeriodLabel.spoken`)
///                      for the period; `TeamShortName` and the served team
///                      abbreviation for the sides.
///
/// PRODUCTION INPUT DEBT (named, not invented): no owner yet binds, through a
/// stable model, which side and which regulation period each quarter-winner
/// original is, the contract's own rules (whether it excludes overtime), or its
/// historical pregame trade and whether kickoff is verified. `Binding` is that
/// typed contract; without it this story is not offered. Nothing here parses a
/// market name, a title or a ticker, hardcodes a market id or infers a grade.
///
/// Every payload is this event's by exact id or it is not read: the binding's
/// `eventID` and the markets' served `eventId` must equal `EventDetail.id`.
enum FootballPeriodWinnersAdapter10868 {
    typealias Copy = FootballPeriodWinnersCopy10868
    typealias H4 = HockeyJourneyOriginalsAdapter10868
    typealias Details = OriginalMarketDetails9483

    nonisolated enum Side: String, CaseIterable, Equatable, Sendable {
        case home, away, tie
    }

    /// The owner's typed binding — production input debt; no owner supplies it yet.
    struct Binding: Equatable {
        /// The event this binding was made for; must equal `EventDetail.id`.
        let eventID: Int
        /// The verified kickoff. Nil: no pregame trade can be admitted.
        let verifiedStart: Date?
        let originals: [Original]

        struct Original: Equatable {
            /// The regulation period, 1-based.
            let period: Int
            let side: Side
            /// The served venue key ("kalshi").
            let source: String
            let marketID: Int
            let outcomeIDs: [Int]
            /// The served typed market type the row must carry.
            let marketType: String
            /// From the contract's own bound rules; nil: not bound, nothing said.
            let regulationOnly: Bool?
            /// The contract's own rule text, verbatim, for its Details.
            let rules: [String]
            let baseline: Baseline?
        }

        /// One historical trade candle for the original.
        struct Baseline: Equatable {
            nonisolated enum Interval: Equatable, Sendable { case minute, hour }
            let value: Double
            /// When the candle ENDS.
            let endingAt: Date
            let volume: Double
            let interval: Interval
        }
    }

    struct Host {
        let now: Date
        let calendar: Calendar
        let locale: Locale

        init(now: Date = Date(), calendar: Calendar = .current, locale: Locale = .current) {
            self.now = now
            self.calendar = calendar
            self.locale = locale
        }

        var words: HockeyJourneyPageAdapter10868.Host {
            HockeyJourneyPageAdapter10868.Host(probabilityObservedAt: nil, now: now, calendar: calendar, locale: locale)
        }
    }

    /// How a bound original stands against the served rows.
    nonisolated enum RowState: Equatable, Sendable {
        case served
        case withdrawn
        case ambiguous
    }

    /// One bound original, admitted.
    struct Admitted: Equatable {
        let original: Binding.Original
        /// The catalogue's identity for the same served row (H4's spelling).
        let identity: Details.Identity
        let state: RowState
        /// The pregame trade as admitted, or nil with `pregameMissing`.
        let pregame: PeriodOutcomeObservation10868?
        let pregameMissing: String
        /// The trade's own clock words ("Minute ending Oct 11, 5:34 AM"), when admitted.
        let clock: String?
        let result: PeriodOutcomeResult10868

        /// The card's opaque original id.
        var cellID: String { FootballPeriodWinnersAdapter10868.cellID(identity) }
    }

    // MARK: - Admission

    /// Every bound original for this event at the final, in binding order;
    /// empty when the binding is another event's, the game is not final, or
    /// no binding is supplied. Originals bound twice (same period and side, or
    /// the same original) are dropped: no identity is guessed.
    static func admitted(_ event: EventDetail, markets: GameMarketsResponse?, binding: Binding?,
                         host: Host) -> [Admitted] {
        guard let binding, binding.eventID == event.id,
              FootballEventPageAdapter10868.phase(event, now: host.now) == .final else { return [] }
        let own = FootballInputIdentityAdapter10868.markets(markets, for: event)
        let rows = (own?.periodMarkets ?? []) + (own?.closedPeriodMarkets ?? []).map(\.row)
        let usable = binding.originals.filter { original in
            !original.source.isEmpty && !original.outcomeIDs.isEmpty
                && Self.label(original.period, event: event) != nil
                && binding.originals.filter { $0.period == original.period && $0.side == original.side }.count == 1
                && binding.originals.filter { identity($0) == identity(original) }.count == 1
        }
        return usable.map { original -> Admitted in
            let matches = rows.filter { row in
                row.source == original.source && row._marketId == original.marketID
                    && row.contributorOutcomeIds == original.outcomeIDs && row.marketType == original.marketType
            }
            let state: RowState = matches.count == 1 ? .served : matches.isEmpty ? .withdrawn : .ambiguous
            let row = state == .served ? matches.first : nil
            let trade = row == nil ? nil : admittedTrade(original.baseline, verifiedStart: binding.verifiedStart,
                                                         now: host.now)
            let clock = trade.map { clockWords($0, host: host) }
            let venue = SourceLabels.label(for: original.source)
            let pregame = trade.map { candle in
                PeriodOutcomeObservation10868(
                    probability: candle.value, text: formatProbability(candle.value),
                    accessibilityDetail: SoccerMatchPageAdapter10868.joined([clockWords(candle, host: host), venue])
                        ?? clockWords(candle, host: host))
            }
            let missing: String = switch state {
            case .served: Copy.pregameUnavailable
            case .withdrawn: Copy.originalUnavailable
            case .ambiguous: Copy.originalAmbiguous
            }
            return Admitted(original: original, identity: identity(original), state: state, pregame: pregame,
                            pregameMissing: missing, clock: clock, result: result(row))
        }
    }

    /// The bound trade, only when it is a real pregame trade: finite, strictly
    /// inside 0…1, positive volume, ending before a verified kickoff that has
    /// itself passed. Anything else is no trade — never clamped or borrowed.
    static func admittedTrade(_ baseline: Binding.Baseline?, verifiedStart: Date?, now: Date) -> Binding.Baseline? {
        guard let baseline, let verifiedStart,
              baseline.value.isFinite, baseline.value > 0, baseline.value < 1,
              baseline.volume.isFinite, baseline.volume > 0,
              baseline.endingAt.timeIntervalSince1970.isFinite,
              baseline.endingAt < verifiedStart, verifiedStart <= now
        else { return nil }
        return baseline
    }

    /// The row's own venue settlement; no row, no grade.
    static func result(_ row: GameMarketOutcome?) -> PeriodOutcomeResult10868 {
        guard let row, let won = H4.settlement(isWinner: row.isWinner, resolutionSource: row.resolutionSource) else {
            return .unconfirmed(Copy.unconfirmed)
        }
        return won ? .won(Copy.won) : .lost(Copy.lost)
    }

    /// The catalogue's identity for the bound original — H4's spelling for a
    /// served row with a market id and contributor ids.
    static func identity(_ original: Binding.Original) -> Details.Identity {
        Details.Identity(source: original.source, market: String(original.marketID),
                         side: original.outcomeIDs.map(String.init).joined(separator: "+"))
    }

    static func cellID(_ identity: Details.Identity) -> String {
        [identity.source, identity.market, identity.side].joined(separator: "|")
    }

    /// The admitted original a card id names, exactly once, or none.
    static func admitted(cellID: String, in admitted: [Admitted]) -> Admitted? {
        let matches = admitted.filter { $0.cellID == cellID }
        return matches.count == 1 ? matches.first : nil
    }

    static func label(_ period: Int, event: EventDetail) -> String? {
        PeriodLabel.lineScoreColumn(period, sport: event.sport)
    }

    static func clockWords(_ candle: Binding.Baseline, host: Host) -> String {
        let clock = HockeyJourneyPageAdapter10868.clockWords(candle.endingAt, host: host.words)
        return candle.interval == .minute ? Copy.minuteEnding(clock) : Copy.hourEnding(clock)
    }

    // MARK: - The card

    /// The card's input at the final, or nil when nothing bound is served.
    /// `selectedID` is the host's held original, passed through unchanged;
    /// nil (nothing held yet) opens on `suggestedID`. Details availability
    /// is the host's to narrow (`detailsOriginalIDs`), against its catalogue.
    static func input(_ event: EventDetail, markets: GameMarketsResponse?, binding: Binding?,
                      selectedID: String?, host: Host) -> FootballPeriodWinnersInput10868? {
        let entries = Self.admitted(event, markets: markets, binding: binding, host: host)
        guard entries.contains(where: { $0.state == .served }) else { return nil }
        let teams = FootballEventPageAdapter10868.teams(event)
        let homeLabel = abbreviation(event.homeTeamData?.abbreviation) ?? teams.homeShort
        let awayLabel = abbreviation(event.awayTeamData?.abbreviation) ?? teams.awayShort
        let periods = Array(Set(entries.map(\.original.period))).sorted()
        let periodIDs = Dictionary(uniqueKeysWithValues: periods.map { ($0, periodID(event, $0)) })

        func series(_ side: Side) -> PeriodOutcomeSeries10868 {
            let name = side == .home ? homeLabel : side == .away ? awayLabel : Copy.tie
            let tint = side == .home ? teams.homeColor : side == .away ? teams.awayColor : DS.textSecondary
            let cells = entries.filter { $0.original.side == side }.compactMap { one -> PeriodOutcomeCell10868? in
                guard let periodID = periodIDs[one.original.period] else { return nil }
                return PeriodOutcomeCell10868(id: one.cellID, periodID: periodID, pregame: one.pregame,
                                              pregameMissing: one.pregameMissing,
                                              current: .unavailable(Copy.noCurrent), result: one.result)
            }
            return PeriodOutcomeSeries10868(id: seriesID(event, side), label: name, tint: tint, symbol: .circle,
                                            cells: cells)
        }

        let panels = periods.compactMap { period -> FootballPeriodWinnersPanel10868? in
            guard let label = Self.label(period, event: event), let id = periodIDs[period] else { return nil }
            let bound = entries.filter { $0.original.period == period }
            let excludes = !bound.isEmpty && bound.allSatisfy { $0.original.regulationOnly == true }
            return FootballPeriodWinnersPanel10868(period: PeriodOutcomePeriod10868(id: id, label: label),
                                                   spokenLabel: PeriodLabel.spoken(label),
                                                   note: excludes ? Copy.regulationOnly : nil)
        }
        let names: [Side: String] = [.home: teams.homeShort, .away: teams.awayShort, .tie: Copy.tie]
        let captions = entries.compactMap { one -> FootballPeriodWinnersCaption10868? in
            guard let label = Self.label(one.original.period, event: event) else { return nil }
            let outcome = one.original.side == .tie
                ? Copy.tiedPeriod : Copy.outscore(team: names[one.original.side] ?? "")
            return FootballPeriodWinnersCaption10868(cellID: one.cellID,
                                                     caption: Copy.caption(period: label, outcome: outcome))
        }
        let surprise = Self.upset(entries)
        let notes = [Copy.pointsNote] + panels.compactMap { $0.note == nil ? nil : Copy.regulationOnlyNote(period: $0.period.label) }
        let words = FootballPeriodWinnersWords10868(
            eyebrow: Copy.eyebrow,
            title: surprise == nil ? Copy.title : Copy.upsetTitle,
            summary: surprise.flatMap { one -> String? in
                guard let label = Self.label(one.original.period, event: event), let pregame = one.pregame else { return nil }
                return Copy.upsetSummary(team: names[one.original.side] ?? "", period: label, chance: pregame.text)
            },
            legendPregame: Copy.legendPregame, legendWon: Copy.legendWon, scoreCaption: Copy.scoreCaption,
            scaleTop: Copy.scaleTop, scaleBottom: Copy.scaleBottom, won: Copy.won,
            pregameTitle: Copy.pregameTitle, resultTitle: Copy.resultTitle, unavailable: Copy.unavailable,
            sidesLabel: Copy.sidesLabel, details: Copy.details, expand: Copy.expand,
            selectionMissing: Copy.selectionMissing, notes: notes, selectPanel: Copy.selectPanel)
        return FootballPeriodWinnersInput10868(
            panels: panels,
            series: [series(.home), series(.away), series(.tie)],
            homeSeriesID: seriesID(event, .home), awaySeriesID: seriesID(event, .away),
            homeScoreLabel: homeLabel, awayScoreLabel: awayLabel,
            actuals: periods.map { actual(event, period: $0, host: host) },
            captions: captions,
            // A held id passes through exactly: one this binding no longer
            // carries shows the card's "no original selected" readout and comes
            // back when that exact original does — never another in its place.
            // Only nothing held opens on the suggested original.
            selectedID: selectedID ?? suggestedID(entries),
            words: words)
    }

    static func periodID(_ event: EventDetail, _ period: Int) -> String { "nfl:\(event.id):period:\(period)" }
    static func seriesID(_ event: EventDetail, _ side: Side) -> String { "nfl:\(event.id):side:\(side.rawValue)" }

    private static func abbreviation(_ served: String?) -> String? {
        guard let text = served?.trimmingCharacters(in: .whitespaces), !text.isEmpty else { return nil }
        return text
    }

    /// The period's own points from the event's stored line score, or its
    /// unavailable words. The capture's time is the score's own record.
    static func actual(_ event: EventDetail, period: Int, host: Host) -> PeriodOutcomeActualContext10868 {
        let id = periodID(event, period)
        let columns = StoredLineScore.columns(
            homePeriods: event.boxScoreData?.homePeriodScores, awayPeriods: event.boxScoreData?.awayPeriodScores,
            sportKey: event.sport, homeTotal: event.homeScore, awayTotal: event.awayScore,
            isFinished: EventState.isFinished(event.status))
        let clock = event.scoreObservedAt?.asDate.map {
            HockeyJourneyPageAdapter10868.clockWords($0, host: host.words)
        }
        let state: PeriodOutcomeActualState10868
        if let columns, columns.indices.contains(period - 1),
           let home = columns[period - 1].home.points, let away = columns[period - 1].away.points {
            state = .reported(PeriodOutcomeActualReport10868(
                scores: [PeriodOutcomeActualScore10868(seriesID: seriesID(event, .home), text: String(home)),
                         PeriodOutcomeActualScore10868(seriesID: seriesID(event, .away), text: String(away))],
                unit: Copy.points, winner: .unreported(Copy.winnerByContract)))
        } else {
            state = .unavailable(Copy.scoreUnavailable)
        }
        return PeriodOutcomeActualContext10868(id: id + ":points", periodID: id, state: state,
                                               provenance: Copy.scoreProvenance(recorded: clock),
                                               noOriginal: Copy.pregameUnavailable)
    }

    /// A team that won its period by its own contract with a lower admitted
    /// pregame chance than the other team's in that period — the lowest such
    /// chance, earliest period first. From admitted evidence only; the tie
    /// outcome neither wins this claim nor blocks it. None, no claim.
    static func upset(_ admitted: [Admitted]) -> Admitted? {
        let candidates = admitted.filter { one in
            guard case .won = one.result, one.original.side != .tie, let mine = one.pregame?.probability else { return false }
            let others = admitted.filter {
                $0.original.period == one.original.period && $0.original.side != .tie && $0.cellID != one.cellID
            }.compactMap { $0.pregame?.probability }
            return !others.isEmpty && others.allSatisfy { mine < $0 }
        }
        return candidates.min { a, b in
            let (pa, pb) = (a.pregame?.probability ?? 1, b.pregame?.probability ?? 1)
            return pa != pb ? pa < pb : a.original.period < b.original.period
        }
    }

    /// The original the card opens on while nothing is held: the upset when
    /// there is one, else the first admitted original with a pregame chance,
    /// else the first served. Never a stand-in for a held original.
    static func suggestedID(_ admitted: [Admitted]) -> String? {
        if let surprise = Self.upset(admitted) { return surprise.cellID }
        if let priced = admitted.first(where: { $0.pregame != nil }) { return priced.cellID }
        return admitted.first(where: { $0.state == .served })?.cellID
    }

    // MARK: - Details through the same helper

    /// The Details' pregame reading for each admitted original with a trade —
    /// the same admitted value and clock the card draws.
    static func detailsReadings(_ admitted: [Admitted]) -> [Details.Identity: Details.Reading] {
        var readings: [Details.Identity: Details.Reading] = [:]
        for one in admitted {
            guard let pregame = one.pregame, let clock = one.clock else { continue }
            let provenance = SoccerMatchPageAdapter10868.joined(
                [Copy.baselineProvenance(clock), SourceLabels.label(for: one.original.source)])
            readings[one.identity] = .value(pregame.text, placement: pregame.probability, provenance: provenance)
        }
        return readings
    }

    /// The contract's own bound rule text for its Details, by identity.
    static func detailsRules(_ admitted: [Admitted]) -> [Details.Identity: [String]] {
        var rules: [Details.Identity: [String]] = [:]
        for one in admitted where !one.original.rules.isEmpty { rules[one.identity] = one.original.rules }
        return rules
    }
}
