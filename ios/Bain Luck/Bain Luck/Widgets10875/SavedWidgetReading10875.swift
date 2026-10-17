import Foundation

/// #10875 — what the saved-item widget says about one game or market, decided
/// by the rules the detail page one tap away draws with.
///
/// A game walks the event hero's branches in the hero's order: finished →
/// venue-settled → closed with no winner → the price pair. The pair is the
/// hero's pair (`OpeningLineHero`'s rule), the away side is withheld on a
/// draw-priced sport (`DrawPricedWinner`), the integers are decided as one pair
/// (`EventDetailView.heroPairPercents`), and whether the price is CURRENT or
/// LAST RECORDED is read off the quote's own clock (`EventHeadlinePhase9483`).
/// A market reads the market page's row value (`FuturesDetailRowValue`: Won /
/// Lost / price), its integers (`futuresDetailRenderedPercents`) and its hero
/// leg (`futuresDetailHeroOutcome`). On a resolved market the server's
/// `settlement_display` decides first (#698, `settledResult`): a row whose
/// stored data does not support a result says "Result unknown", never Lost.
///
/// The rules that need app models are restated here against the widget's own
/// decode, and `SavedItemWidget10875Tests` holds each restatement to its source
/// on the same inputs. The rules that do not (`EventState`, `EventOutcome`,
/// `OutcomeVerdict`, `DrawPricedWinner`, the percent helpers) are the app's own
/// files, compiled into the widget.
///
/// What this never does: print a number with no source, call an undated price
/// current, name a winner the event has not got, replace a result with a price,
/// derive the away side as `1 − home` where the sport prices a draw, or call a
/// settled row Lost when its result is unknown.
nonisolated struct SavedWidgetReading10875: Equatable, Sendable {
    enum Phase: String, Equatable, Sendable {
        /// A dated price that is still current.
        case current
        /// A price that has stopped being current: old, undated, a started game
        /// that is not live, or a closed market.
        case lastRecorded
        /// Nobody has quoted the game since its opening line.
        case openingLine
        /// Settled: this is the result.
        case result
        /// Over or stopped, with no result to name.
        case noResult
        /// No number to show for what was chosen.
        case unavailable
    }

    /// One side or outcome as a row: its name, its figure or verdict.
    struct Row: Equatable, Sendable {
        let label: String
        /// Short form for the tightest layouts ("TOR").
        let shortLabel: String
        /// "62%", "<1%", a score, or nil when there is nothing to print.
        let figure: String?
        /// "Won" / "Lost" / "Draw" where settled.
        let verdict: String?
        let emphasized: Bool
    }

    let phase: Phase
    /// "Toronto Maple Leafs vs Colorado Avalanche", or the market's name.
    let subject: String
    /// "TOR vs COL", or the market's name.
    let shortSubject: String
    /// The state in words: "Live", "Final", "Starts Oct 17, 7:05 PM", "Closed".
    let status: String
    /// The rows a medium widget lists. Away first, as every card does.
    let rows: [Row]
    /// The one thing a small or circular widget shows.
    let headline: Row?
    /// What the price is, in the hero's words, when there is a price.
    let priceCaption: String?
    /// The price's own observation clock. Never the fetch time.
    let observedAt: Date?
    /// When a CURRENT price stops being current on its own clock, so the
    /// timeline can change its words without a new fetch.
    let becomesLastRecordedAt: Date?
    /// The whole reading as one sentence, for VoiceOver.
    let spoken: String
    /// #698: a settled row whose result is unknown keeps its last price
    /// ("50%"), printed only as "Last recorded", never as a value or a result.
    var lastRecordedFigure: String? = nil
}

/// Which side of a game the reader chose to follow, if any.
nonisolated enum SavedWidgetGameSide10875: String, CaseIterable, Sendable {
    case away
    case home
}

/// The two staleness bounds, restated from `SourceAge` (which needs the app's
/// date parsing). Pinned to it by `SavedItemWidget10875Tests`.
nonisolated enum SavedWidgetStaleness10875 {
    static let liveStaleAfter: TimeInterval = 30 * 60
    static let futuresStaleAfter: TimeInterval = 6 * 60 * 60
}

enum SavedWidgetReadingRules10875 {

    // MARK: - Games

    static func game(_ event: SavedWidgetEventDetail10875, side: SavedWidgetGameSide10875?,
                     now: Date = Date()) -> SavedWidgetReading10875 {
        let subject = "\(event.awayTeam) vs \(event.homeTeam)"
        let short = TeamShortName.abbreviationPair(
            away: event.awayTeam, home: event.homeTeam,
            awayServed: event.awayTeamData?.abbreviation, homeServed: event.homeTeamData?.abbreviation)
        let shortSubject = "\(short.away) vs \(short.home)"
        let commence = SavedWidgetDetailDecoding10875.date(event.commenceTime)

        func row(_ isHome: Bool, figure: String?, verdict: String? = nil, emphasized: Bool = false) -> SavedWidgetReading10875.Row {
            .init(label: isHome ? event.homeTeam : event.awayTeam,
                  shortLabel: isHome ? short.home : short.away,
                  figure: figure, verdict: verdict, emphasized: emphasized)
        }
        func reading(_ phase: SavedWidgetReading10875.Phase, status: String, rows: [SavedWidgetReading10875.Row],
                     headline: SavedWidgetReading10875.Row?, caption: String? = nil, observedAt: Date? = nil,
                     flipsAt: Date? = nil, spoken: String) -> SavedWidgetReading10875 {
            .init(phase: phase, subject: subject, shortSubject: shortSubject, status: status, rows: rows,
                  headline: headline, priceCaption: caption, observedAt: observedAt,
                  becomesLastRecordedAt: flipsAt, spoken: spoken)
        }
        // A score is printed only when both sides are held (`EventState`'s
        // partial-line rule): half a score is not a score.
        let scores: (away: String, home: String)? = {
            guard let away = event.awayScore, let home = event.homeScore else { return nil }
            return (String(away), String(home))
        }()
        let scoreSentence = scores.map { " \(event.awayTeam) \($0.away), \(event.homeTeam) \($0.home)." } ?? ""

        // 1. Finished: the verdict, never a price.
        if EventState.isFinished(event.status) {
            let final = scores.map { "Final · \($0.away)–\($0.home)" } ?? "Final"
            let outcome = EventOutcome.resolve(status: event.status, homeScore: event.homeScore,
                                               awayScore: event.awayScore, servedResult: event.heroSettledResult)
            switch outcome {
            case .undecided:
                return reading(.noResult, status: final,
                               rows: [row(false, figure: scores?.away), row(true, figure: scores?.home)],
                               headline: nil,
                               spoken: "\(subject) is final. No result has been recorded.\(scoreSentence)")
            case .draw:
                return reading(.result, status: final,
                               rows: [row(false, figure: scores?.away, verdict: "Draw"),
                                      row(true, figure: scores?.home, verdict: "Draw")],
                               headline: .init(label: "Draw", shortLabel: "Draw", figure: nil, verdict: "Draw", emphasized: false),
                               spoken: "\(subject) ended in a draw.\(scoreSentence)")
            case .home, .away:
                let homeWon = outcome == .home
                let rows = [row(false, figure: scores?.away, verdict: homeWon ? "Lost" : "Won", emphasized: !homeWon),
                            row(true, figure: scores?.home, verdict: homeWon ? "Won" : "Lost", emphasized: homeWon)]
                let winner = homeWon ? event.homeTeam : event.awayTeam
                let headline: SavedWidgetReading10875.Row
                if let side {
                    headline = side == .home ? rows[1] : rows[0]
                } else {
                    headline = homeWon ? rows[1] : rows[0]
                }
                return reading(.result, status: final, rows: rows, headline: headline,
                               spoken: "\(subject) is final. \(winner) won.\(scoreSentence)")
            }
        }

        // 2. Settled at the venue before our own status caught up: the venue's
        //    verdict, verbatim.
        if EventState.showsVenueSettledVerdict(event.status, venueSettled: event.venueSettled,
                                               commenceTime: commence, now: now) {
            let verdict = event.venueSettledResult?.trimmingCharacters(in: .whitespacesAndNewlines)
            let said = (verdict?.isEmpty == false) ? verdict! : "No final score has been recorded"
            return reading(.result, status: "Settled",
                           rows: [row(false, figure: nil), row(true, figure: nil)],
                           headline: .init(label: said, shortLabel: "Settled", figure: nil, verdict: said, emphasized: true),
                           spoken: "\(subject) is settled: \(said).")
        }

        // 3. Closed at the venue with no winner.
        if EventState.showsVenueClosedNoWinner(event.status, venueSettled: event.venueSettled,
                                               venueClosedNoWinner: event.venueClosedNoWinner,
                                               commenceTime: commence, now: now) {
            return reading(.noResult, status: EventState.venueClosedNoWinnerLabel,
                           rows: [row(false, figure: nil), row(true, figure: nil)], headline: nil,
                           spoken: "\(subject) ended with no winner.")
        }

        let stopped = EventState.isSuspendedAndStarted(event.status, commenceTime: commence, now: now)
        let status: String = {
            if stopped { return EventState.suspendedLabel(authorityPeriod: nil) }
            if event.status == "live" {
                return scores.map { "Live · \($0.away)–\($0.home)" } ?? "Live"
            }
            return startText(commenceTime: commence, startIsTbd: event.startIsTbd == true) ?? "Scheduled"
        }()

        // 4. The price pair, as the hero resolves it.
        let shown = heroPair(event)
        guard let shown,
              let pair = DrawPricedWinner.printablePair(away: shown.away, home: shown.home, sport: event.sport)
        else {
            return reading(.unavailable, status: status,
                           rows: [row(false, figure: nil), row(true, figure: nil)], headline: nil,
                           spoken: "\(subject). Bain Luck has no chance to show right now. \(status).")
        }

        var awayFigure: String?
        let homeFigure: String
        if let away = pair.away {
            let percents = heroPairPercents(shown, away: away, home: pair.home)
            awayFigure = formatProbability(away, renderedPercent: percents.away)
            homeFigure = formatProbability(pair.home, renderedPercent: percents.home)
        } else {
            // Draw-priced: the lone home number, rounded alone (#5271).
            homeFigure = formatProbability(pair.home)
        }

        let phase: SavedWidgetReading10875.Phase
        let caption: String
        var flipsAt: Date?
        let observedAt = SavedWidgetDetailDecoding10875.date(event.heroProbabilityObservedAt)
        if shown.isOpeningLine {
            phase = .openingLine
            caption = "Opening line"
        } else if isCurrentGamePrice(status: event.status, commence: commence, observedAt: observedAt, now: now) {
            phase = .current
            caption = "Current win chance"
            // The hero's own two clocks: the quote ageing past the live bound,
            // and a not-live game reaching its start.
            var flips: [Date] = []
            if let observedAt { flips.append(observedAt.addingTimeInterval(SavedWidgetStaleness10875.liveStaleAfter)) }
            if event.status != "live", let commence { flips.append(commence) }
            flipsAt = flips.min()
        } else {
            phase = .lastRecorded
            caption = "Last recorded win chance"
        }

        let awayLeads = awayFigure != nil && (pair.away ?? 0) > pair.home
        let homeLeads = awayFigure != nil && pair.home > (pair.away ?? 1)
        let rows = [row(false, figure: awayFigure, emphasized: awayLeads),
                    row(true, figure: homeFigure, emphasized: homeLeads)]
        let headline: SavedWidgetReading10875.Row?
        switch side {
        case .home?: headline = rows[1]
        case .away?: headline = rows[0] // its figure is nil where the sport prices a draw
        case nil:
            // `DrawPricedWinner.headlineSide`: the favourite, or HOME on a
            // draw-priced sport, favourite or not.
            if let pick = DrawPricedWinner.headlineSide(away: shown.away, home: shown.home, sport: event.sport) {
                headline = pick.isHome ? rows[1] : rows[0]
            } else {
                headline = nil
            }
        }

        let said: String = {
            if side == .away, awayFigure == nil {
                return "Bain Luck doesn't show a separate chance for \(event.awayTeam). \(event.homeTeam) \(homeFigure)"
            }
            if let awayFigure { return "\(event.awayTeam) \(awayFigure), \(event.homeTeam) \(homeFigure)" }
            return "\(event.homeTeam) \(homeFigure)"
        }()
        let when = observedAt == nil && phase == .lastRecorded ? " No time was recorded for it." : ""
        return reading(phase, status: status, rows: rows, headline: headline, caption: caption,
                       observedAt: shown.isOpeningLine ? nil : observedAt, flipsAt: flipsAt,
                       spoken: "\(subject). \(caption): \(said).\(when) \(status).")
    }

    /// The pair the hero prints — `OpeningLineHero.resolve`'s rule on this
    /// decode. `nil` when the event carries no `current_odds` at all, which is
    /// the hero's unavailable branch.
    struct HeroPair: Equatable {
        let away: Double?
        let home: Double?
        let awayRenderedPercent: Int?
        let homeRenderedPercent: Int?
        let isOpeningLine: Bool
    }

    static func heroPair(_ event: SavedWidgetEventDetail10875) -> HeroPair? {
        guard let odds = event.currentOdds else { return nil }
        if event.heroProbabilitySource == "opening",
           event.status != "live", !EventState.isFinished(event.status),
           let home = event.heroProbability, home.isFinite, home > 0, home < 1 {
            return HeroPair(away: event.heroProbabilityAway.flatMap { $0.isFinite ? $0 : nil }, home: home,
                            awayRenderedPercent: nil, homeRenderedPercent: nil, isOpeningLine: true)
        }
        return HeroPair(away: odds.awayProbability, home: odds.homeProbability,
                        awayRenderedPercent: odds.awayRenderedPercent, homeRenderedPercent: odds.homeRenderedPercent,
                        isOpeningLine: false)
    }

    /// `EventDetailView.heroPairPercents`: the served integers BOTH OR NEITHER.
    static func heroPairPercents(_ shown: HeroPair, away: Double, home: Double) -> (away: Int?, home: Int?) {
        let fallback = complementDisplayPercents(away: away, home: home)
        let bothServed = shown.awayRenderedPercent != nil && shown.homeRenderedPercent != nil
        return (away: bothServed ? shown.awayRenderedPercent : fallback[0],
                home: bothServed ? shown.homeRenderedPercent : fallback[1])
    }

    /// `EventHeadlinePhase9483.resolve` for a non-opening, unfinished pair: an
    /// undated or old quote is never current; a game that has started is
    /// current only while live.
    static func isCurrentGamePrice(status: String?, commence: Date?, observedAt: Date?, now: Date) -> Bool {
        guard let observedAt, now.timeIntervalSince(observedAt) <= SavedWidgetStaleness10875.liveStaleAfter
        else { return false }
        if status == "live" { return true }
        return !EventState.hasStarted(commenceTime: commence, now: now)
    }

    /// The start, absolute: a relative "Tomorrow" goes stale on a Home Screen.
    static func startText(commenceTime: Date?, startIsTbd: Bool) -> String? {
        guard let commenceTime else { return nil }
        if startIsTbd {
            return "Starts " + commenceTime.formatted(.dateTime.month(.abbreviated).day()) + " · time TBD"
        }
        return "Starts " + commenceTime.formatted(.dateTime.month(.abbreviated).day().hour().minute())
    }

    // MARK: - Markets

    static func market(_ market: SavedWidgetMarketDetail10875, outcomeID: Int?,
                       now: Date = Date()) -> SavedWidgetReading10875 {
        let resolved = market.status == "resolved"
        // Only `open` is open. Anything else (`withdrawn`, `suspended`,
        // `closed`) is named in the market page's own word for it, and its
        // price is never the current one.
        let isOpen = market.status == "open"
        let standing = marketStatusText(market.status)
        func reading(_ phase: SavedWidgetReading10875.Phase, status: String, rows: [SavedWidgetReading10875.Row],
                     headline: SavedWidgetReading10875.Row?, caption: String? = nil, observedAt: Date? = nil,
                     flipsAt: Date? = nil, spoken: String, lastRecorded: String? = nil) -> SavedWidgetReading10875 {
            .init(phase: phase, subject: market.name, shortSubject: market.name, status: status, rows: rows,
                  headline: headline, priceCaption: caption, observedAt: observedAt,
                  becomesLastRecordedAt: flipsAt, spoken: spoken, lastRecordedFigure: lastRecorded)
        }

        let chosen: SavedWidgetMarketOutcome10875?
        if let outcomeID {
            chosen = market.outcomes.first { $0.id == outcomeID }
            if chosen == nil {
                // Said on screen, not only to VoiceOver: the reader has to
                // edit the widget. Nothing is substituted for the choice.
                let row = SavedWidgetReading10875.Row(label: "Chosen outcome", shortLabel: "Not listed", figure: nil,
                                                      verdict: "No longer listed", emphasized: false)
                return reading(.unavailable, status: standing, rows: [row], headline: row,
                               spoken: "That outcome is no longer listed in \(market.name). Edit the widget to choose another.")
            }
        } else {
            chosen = heroOutcome(market)
        }
        guard let outcome = chosen else {
            return reading(.unavailable, status: standing, rows: [], headline: nil,
                           spoken: "\(market.name): Bain Luck has no outcome to show right now.")
        }

        let verdict: OutcomeVerdict?
        switch settledResult(outcome, marketSource: market.source, marketStatus: market.status) {
        case .won?: verdict = .won
        case .lost?: verdict = .lost
        case .unknown?:
            // Settled, result not supported by the row: said as unknown, with
            // the last price named as last recorded. Never Lost, never a value.
            let last = outcome.probability.flatMap { $0.isFinite ? $0 : nil }.map {
                formatProbability($0, renderedPercent: renderedPercents(market.outcomes)[outcome.id])
            }
            let row = SavedWidgetReading10875.Row(label: outcome.name, shortLabel: outcome.name, figure: nil,
                                                  verdict: "Result unknown", emphasized: false)
            let observedAt = last == nil ? nil : SavedWidgetDetailDecoding10875.date(outcome.observedAt ?? outcome.lastUpdated)
            let lastSaid = last.map { " Its last recorded chance was \($0)." } ?? ""
            return reading(.noResult, status: "Settled", rows: [row], headline: row, observedAt: observedAt,
                           spoken: "\(market.name) has settled. The result for \(outcome.name) is unknown.\(lastSaid)",
                           lastRecorded: last)
        case nil:
            verdict = OutcomeVerdict.verdict(isWinner: outcome.isWinner, resolutionSource: outcome.resolutionSource,
                                             marketResolved: resolved)
        }
        if let verdict {
            let row = SavedWidgetReading10875.Row(label: outcome.name, shortLabel: outcome.name, figure: nil,
                                                  verdict: verdict.label, emphasized: verdict == .won)
            return reading(.result, status: resolved ? "Settled" : standing, rows: [row], headline: row,
                           spoken: "\(market.name): \(outcome.name) \(verdict == .won ? "won" : "lost").")
        }
        guard let probability = outcome.probability, probability.isFinite else {
            let row = SavedWidgetReading10875.Row(label: outcome.name, shortLabel: outcome.name, figure: nil,
                                                  verdict: nil, emphasized: false)
            return reading(.unavailable, status: standing, rows: [row], headline: row,
                           spoken: "\(market.name): Bain Luck has no price for \(outcome.name) right now.")
        }

        let figure = formatProbability(probability, renderedPercent: renderedPercents(market.outcomes)[outcome.id])
        let row = SavedWidgetReading10875.Row(label: outcome.name, shortLabel: outcome.name, figure: figure,
                                              verdict: nil, emphasized: false)
        // The outcome's own clock: a verified answer's oldest included
        // observation, otherwise the row's price stamp.
        let observedAt = SavedWidgetDetailDecoding10875.date(outcome.observedAt ?? outcome.lastUpdated)
        if isOpen, let observedAt,
           now.timeIntervalSince(observedAt) <= SavedWidgetStaleness10875.futuresStaleAfter {
            // Within the bound the page draws no age mark, and it makes no
            // "current" claim either: the widget prints the price's own clock
            // ("As of 3:42 PM") and no word for it.
            return reading(.current, status: standing, rows: [row], headline: row, caption: nil,
                           observedAt: observedAt,
                           flipsAt: observedAt.addingTimeInterval(SavedWidgetStaleness10875.futuresStaleAfter),
                           spoken: "\(market.name): \(outcome.name) \(figure).")
        }
        let when = observedAt == nil ? " No time was recorded for it." : ""
        let closedSaid = resolved ? " has closed"
            : (isOpen || market.status == nil ? "" : " is \(standing.lowercased())")
        return reading(.lastRecorded, status: standing, rows: [row], headline: row,
                       caption: "Last recorded chance", observedAt: observedAt,
                       spoken: "\(market.name)\(closedSaid): \(outcome.name) \(figure), last recorded chance.\(when)")
    }

    /// #698 — what a resolved market's row may say about its own result, the
    /// restatement of `backend/app/utils/settlement_display.py` as served, and
    /// of web's `settledResultDisplay.ts`, on the widget's decode.
    ///
    /// A served `settlement_display` is the answer: `won` / `lost` are
    /// results, any other verdict (or none) is unknown, so a new server word can
    /// only make the row say less. Absent on a resolved Polymarket market, the
    /// server predates the field and the same rule runs on the served values,
    /// conservatively: only an exact 1 + `true` / 0 + `false` with a tier-3
    /// source is a result. `nil` means "not this rule's market": the
    /// `OutcomeVerdict` rule applies unchanged (open boards, other venues).
    nonisolated enum SettledResult: Equatable, Sendable {
        case won
        case lost
        case unknown
    }

    /// The venues whose resolved detail rows the server targets.
    static let settlementDisplaySources: Set<String> = ["polymarket"]

    static func settledResult(_ outcome: SavedWidgetMarketOutcome10875, marketSource: String?,
                              marketStatus: String?) -> SettledResult? {
        guard marketStatus == "resolved" else { return nil }
        if let served = outcome.settlementDisplay {
            switch served.verdict {
            case "won": return .won
            case "lost": return .lost
            default: return .unknown
            }
        }
        guard let marketSource, settlementDisplaySources.contains(marketSource) else { return nil }
        guard outcome.resolutionSource != OutcomeVerdict.retractedResolutionSource,
              OutcomeVerdict.isAuthoritative(outcome.resolutionSource),
              let probability = outcome.probability, probability.isFinite else { return .unknown }
        if probability == 1, outcome.isWinner == true { return .won }
        if probability == 0, outcome.isWinner == false { return .lost }
        return .unknown
    }

    /// The market's standing in words. `open` reads Open and `resolved`
    /// Closed; any other status is the market page's own word for it
    /// (`status.capitalized`), never Open.
    static func marketStatusText(_ status: String?) -> String {
        switch status {
        case "open": return "Open"
        case "resolved": return "Closed"
        case let other?:
            let word = other.trimmingCharacters(in: .whitespacesAndNewlines)
            return word.isEmpty ? "Status unknown" : word.capitalized
        case nil: return "Status unknown"
        }
    }

    /// `futuresDetailHeroOutcome`: the served lead leg while it is priced and
    /// the market is open, otherwise the highest-priced leg.
    static func heroOutcome(_ market: SavedWidgetMarketDetail10875) -> SavedWidgetMarketOutcome10875? {
        if let leadId = market.leadOutcomeId, market.status != "resolved",
           let lead = market.outcomes.first(where: { $0.id == leadId }), lead.probability != nil {
            return lead
        }
        return market.outcomes.max(by: { ($0.probability ?? 0) < ($1.probability ?? 0) })
    }

    /// `futuresDetailRenderedPercents`: decided over probability-descending
    /// order, ties by id, looked up by identity.
    static func renderedPercents(_ outcomes: [SavedWidgetMarketOutcome10875]) -> [Int: Int] {
        let order = outcomes.sorted { a, b in
            let lhs = a.probability ?? -1
            let rhs = b.probability ?? -1
            if lhs != rhs { return lhs > rhs }
            return a.id < b.id
        }
        let printed = renderedCardPercents(order.map(\.probability))
        var byID: [Int: Int] = [:]
        for (index, outcome) in order.enumerated() {
            guard printed.indices.contains(index), let percent = printed[index] else { continue }
            byID[outcome.id] = percent
        }
        return byID
    }
}

/// #10875 R1 — how the two Lock Screen families fit the headline's verdict.
/// Only Won / Lost / Draw fit beside a name; anything longer ("Result
/// unknown", the venue's own words, a team name) gets a word that fits the
/// ring and a line of its own in the rectangle, never one truncated line
/// ("Result unk…"). Keyed on the string, not the phase, so a verdict added
/// later is covered too. The spoken label keeps the full sentence.
nonisolated enum SavedLockScreenFit10875 {
    /// The verdicts that share a line with the outcome name.
    static let shortVerdicts: Set<String> = ["Won", "Lost", "Draw"]
    /// The longest word the circular widget's value line holds whole ("Unknown").
    static let ringLimit = 7

    /// The circular widget's value: a figure, a verdict that fits, or a word
    /// standing for one that does not.
    static func ringValue(_ reading: SavedWidgetReading10875) -> String {
        guard let headline = reading.headline else { return reading.phase == .noResult ? "Final" : "—" }
        // Nothing to show for the choice (its label says why, e.g. "Not
        // listed"): a dash, never a sentence squeezed into the circle.
        if reading.phase == .unavailable { return "—" }
        guard let verdict = headline.verdict else { return headline.figure ?? "—" }
        if shortVerdicts.contains(verdict) || verdict.count <= ringLimit { return verdict }
        // #698: settled, and the result is unknown.
        if reading.phase == .noResult { return "Unknown" }
        // The venue's words naming a side: that side's short name ("SEA").
        // The server writes "{participant} wins" (venue_settlement
        // WINNER_SENTENCE); the bare name is kept too.
        if let side = reading.rows.first(where: { $0.label == verdict || $0.label + " wins" == verdict }),
           side.shortLabel.count <= ringLimit {
            return side.shortLabel
        }
        return "—"
    }

    /// The rectangular widget's verdict when it needs its own line; nil when
    /// it fits beside the outcome name (Won / Lost / Draw) or there is none.
    static func rectangleOwnLineVerdict(_ reading: SavedWidgetReading10875) -> String? {
        guard reading.phase != .unavailable,
              let verdict = reading.headline?.verdict, !shortVerdicts.contains(verdict) else { return nil }
        return verdict
    }

    /// The rectangle's last line under an own-line verdict: the outcome name
    /// it belongs to, then the caption. The name is said once, never
    /// "Settled · Settled".
    static func rectangleFooter(_ reading: SavedWidgetReading10875, caption: String) -> String {
        guard let name = reading.headline?.shortLabel, !name.isEmpty,
              name != caption, name != reading.status else { return caption }
        return "\(name) · \(caption)"
    }
}
