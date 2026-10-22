import Foundation

/// #9483 — the NFL page's visual cards (design ref #10868 v105/v107): the
/// forecast-versus-actual card and the player milestone cards that sit under
/// the paired chart, each openable full size.
///
/// Every number on a card is one the page already serves. The deck adds no
/// source and no ranking service; its order is fixed per page state, so a card
/// never moves while a reader is looking at it (v157/v158).
///
/// The NBA page (v328 NBA slice) uses the same deck and reader: its winning
/// margin and scoring ladders (`NBALadderCard9483`) sit before the projected
/// finish, and it has no player milestone cards.
///
/// The final MLB page (#11284) deals its own five story slots
/// (`MLBFinalCard11284`) through the same deck and reader. They are one
/// explicit case, built only by `MLBFinalDeck11284` on a finished MLB game,
/// so no NFL or NBA family reads them and they read no NFL or NBA family.
enum NFLEventCard9483: Equatable, Identifiable {
    case finish(NFLFinishCard9483)
    case milestone(NFLMilestoneCard9483)
    case ladder(NBALadderCard9483)
    case mlb(MLBFinalCard11284)

    var id: String {
        switch self {
        case .finish: return "finish"
        case .milestone(let card): return "milestone:\(card.id)"
        case .ladder(let card): return card.id
        case .mlb(let card): return card.id
        }
    }

    var title: String {
        switch self {
        case .finish(let card): return card.kicker
        case .milestone(let card): return "\(card.player) · \(card.stat)"
        case .ladder(let card): return card.title
        case .mlb(let card): return card.title
        }
    }

    /// The card as it may be shown at `now` (`NFLMilestoneCard9483.current(at:)`,
    /// `NBALadderCard9483.current(at:)`).
    func current(at now: Date) -> NFLEventCard9483 {
        switch self {
        case .finish: return self
        case .milestone(let card): return .milestone(card.current(at: now))
        case .ladder(let card): return .ladder(card.current(at: now))
        // A finished game's saved chances, finals and results are history:
        // nothing on these cards is a current quote that can expire.
        case .mlb: return self
        }
    }
}

enum NFLEventCardDeck9483 {
    /// At most this many player cards: the deck is a story, not the catalog —
    /// every ladder stays in the player props section below.
    static let maximumMilestoneCards = 2

    /// The deck for this page, or empty to draw none. NFL: the projected
    /// finish, then the player milestones. NBA: winning margin, scoring
    /// expectations, then the projected finish — a fixed order per page state,
    /// no ranking service. Each sport reads only its own families.
    @MainActor
    static func cards(
        sportKey: String?, finish: NFLFinishCard9483?, milestones: [NFLMilestoneCard9483],
        ladders: [NBALadderCard9483] = []
    ) -> [NFLEventCard9483] {
        let finishCard: [NFLEventCard9483] = finish.map { [.finish($0)] } ?? []
        if NBAEventCards9483.applies(sportKey: sportKey) {
            let order: [NBALadderCard9483.Family] = [.margin, .total]
            let ordered = order.compactMap { family in ladders.first { $0.family == family } }
            return ordered.map { .ladder($0) } + finishCard
        }
        guard NFLRecognizablePage9483.isNFL(sportKey: sportKey) else { return [] }
        return finishCard + milestones.map { .milestone($0) }
    }
}

// MARK: - Projected finish

/// The sportsbooks' projected final against what happened.
///
/// Three moments, never blended:
/// - **pregame**: the last projection recorded before the first observed game
///   state (the score floor `ProjectedFinalPointsMount` already admits on);
/// - **later**: while live, the newest projection — only when it is still a
///   current capture (`latestIntervalUnavailable` false);
/// - **final**: after the final, the final score, which is a result and never a
///   projection or a 100% quote.
///
/// #9483 R2 — after the final, the pregame side is the headline's qualified
/// "Projection before scheduled start" whenever the page has one, so the
/// headline, this card and the NBA ladders compare the final with ONE
/// expectation (Packers 14780562 printed DAL 28–GB 27 above a card that said
/// "Packers won as projected" from an earlier GB-favouring history point).
/// Without it the card keeps the history point and names that different basis.
nonisolated struct NFLFinishCard9483: Equatable {
    nonisolated struct Pair: Equatable {
        let away: Double
        let home: Double
        let at: Date?

        /// nil when level.
        var homeLeads: Bool? { home == away ? nil : home > away }
    }

    nonisolated enum Phase: Equatable { case before, during, after }

    /// Which expectation `pregame` is.
    nonisolated enum PregameBasis: Equatable {
        /// The last projection in the page's projected-points history before
        /// the first observed game state.
        case history
        /// The headline's qualified projection before the scheduled start
        /// (`FinalForecastComparison11296.Qualified`), served halves unrounded.
        /// It is a capture range, so `pregame.at` is nil: no single clock is claimed.
        case scheduledStart
    }

    let phase: Phase
    let pregame: Pair
    /// The newest admitted projection while live.
    let projectedNow: Pair?
    /// The final score after the final.
    let final: Pair?
    /// The league's points gridline step (`ProjectedFinalPointsSeries.League`):
    /// a touchdown in football, twenty in basketball.
    var tickStep: Double = 7
    /// What the sport calls the start: "kickoff", "tip-off".
    var startWord: String = "kickoff"
    var pregameBasis: PregameBasis = .history

    var kicker: String { phase == .after ? "Final vs forecast" : "Projected finish" }

    /// A finished card on the history point is a DIFFERENT expectation from
    /// the headline's, and says so instead of borrowing "pregame projection".
    var namesDistinctBasis: Bool { phase == .after && pregameBasis == .history }

    /// The label under each pregame number. #9483 (Design, eae3) — the history
    /// point is the last one before the instrument's first OBSERVED game state
    /// (`ProjectedFinalPointsMount`: the floor is not kickoff, and production
    /// passes `kickoffAt: nil`), so it can follow the start: "earlier
    /// forecast", never "pregame" or "before play".
    var pregameLabel: String { namesDistinctBasis ? Self.earlierForecast.lowercased() : "pregame projection" }

    /// The distinct history basis's name, in the caption, the legend and the
    /// spoken card alike.
    static let earlierForecast = "Earlier forecast"

    /// The pregame pair the NBA margin and total cards print as their
    /// "Pregame projection": the same pair this card compares with, and none
    /// after the final unless it is the headline's qualified one.
    var ladderPregame: (home: Double, away: Double)? {
        namesDistinctBasis ? nil : (home: pregame.home, away: pregame.away)
    }

    /// The same card with its live projection gone (v159: a projection past
    /// its validity leaves the held card).
    var withoutProjectedNow: NFLFinishCard9483 {
        NFLFinishCard9483(phase: phase, pregame: pregame, projectedNow: nil, final: final,
                          tickStep: tickStep, startWord: startWord, pregameBasis: pregameBasis)
    }

    /// The card's one sentence. It names a flip only when the projected leader
    /// actually changed, and never says one from a level pregame projection.
    func headline(awayName: String, homeName: String) -> String {
        func name(_ homeLeads: Bool) -> String { homeLeads ? homeName : awayName }
        switch phase {
        case .before:
            guard let leads = pregame.homeLeads else { return "Projected level" }
            return "\(name(leads)) projected ahead"
        case .during:
            guard let now = projectedNow else {
                guard let leads = pregame.homeLeads else { return "Projected level before \(startWord)" }
                return "\(name(leads)) projected ahead before \(startWord)"
            }
            guard let nowLeads = now.homeLeads else { return "The projected finish is level" }
            if let before = pregame.homeLeads, before != nowLeads { return "The projected finish has flipped" }
            return "\(name(nowLeads)) still projected ahead"
        case .after:
            guard let final, let winner = final.homeLeads else { return "Final vs forecast" }
            guard let before = pregame.homeLeads else { return "\(name(winner)) won" }
            return before == winner ? "\(name(winner)) won as projected" : "\(name(winner)) beat the forecast"
        }
    }

    /// From the page's own projected-points input. Nil wherever that series
    /// is refused, or holds no projection before the game began.
    ///
    /// `finalBaseline` is the headline's qualified forecast halves
    /// (`EventDetailView.qualifiedFinalForecast11296`), read only after the
    /// final; before and during the game the card is unchanged. The history
    /// series is never edited: its points, the final and the phase are its own.
    @MainActor
    static func build(_ input: ProjectedFinalPointsSeries.Input?,
                      finalBaseline: (away: Double, home: Double)? = nil) -> NFLFinishCard9483? {
        guard let input, NFLRecognizablePage9483.applies(sportKey: input.sportKey),
              let series = ProjectedFinalPointsSeries.build(input) else { return nil }
        let points = series.segments.flatMap { $0 }
        let floor = input.scoreObservationStartAt ?? input.kickoffAt
        let pregamePoint: ProjectedFinalPointsSeries.Point?
        switch series.phase {
        case .before: pregamePoint = series.latestIntervalUnavailable ? nil : series.latest
        case .during, .after: pregamePoint = floor.flatMap { f in points.last { $0.at < f } }
        }
        // The card exists exactly where it did; the baseline only changes
        // which pregame pair a finished one compares with.
        guard let pregamePoint else { return nil }
        let baseline = series.phase == .after ? finalBaseline.flatMap { b -> Pair? in
            guard b.away.isFinite, b.home.isFinite else { return nil }
            return Pair(away: b.away, home: b.home, at: nil)
        } : nil
        let pregame = baseline ?? Pair(away: pregamePoint.away, home: pregamePoint.home, at: pregamePoint.at)
        let basis: PregameBasis = baseline != nil ? .scheduledStart : .history
        let tickStep = ProjectedFinalPointsSeries.leagues[input.sportKey]?.tickStep ?? 7
        let startWord = NBAEventCards9483.applies(sportKey: input.sportKey) ? "tip-off" : "kickoff"
        switch series.phase {
        case .before:
            return NFLFinishCard9483(phase: .before, pregame: pregame, projectedNow: nil, final: nil,
                                     tickStep: tickStep, startWord: startWord)
        case .during:
            let latest = series.latest
            let now = !series.latestIntervalUnavailable && floor.map { latest.at >= $0 } == true
                ? Pair(away: latest.away, home: latest.home, at: latest.at) : nil
            return NFLFinishCard9483(phase: .during, pregame: pregame, projectedNow: now, final: nil,
                                     tickStep: tickStep, startWord: startWord)
        case .after:
            guard let actual = series.latestActual else { return nil }
            return NFLFinishCard9483(phase: .after, pregame: pregame, projectedNow: nil,
                                     final: Pair(away: actual.away, home: actual.home, at: actual.at),
                                     tickStep: tickStep, startWord: startWord, pregameBasis: basis)
        }
    }
}

// MARK: - Player milestones

/// One player's quoted ladder as a milestone profile, against the stat's
/// actual once the server has graded it.
struct NFLMilestoneCard9483: Equatable, Identifiable {
    nonisolated enum Basis: Equatable {
        /// Before kickoff: the venues' current price, which IS the pregame chance.
        case pregamePrice
        /// Once play starts: the server's pregame mark (`pregame_mark`, #4577).
        /// A live or settled price is never relabelled pregame.
        case pregameMark
    }

    nonisolated struct Rung: Equatable, Identifiable {
        let threshold: Double
        /// The chance this card may print for the line, or nil: before kickoff
        /// a quote with no recent observation, after it a line with no served
        /// pregame mark. A nil line stays on the card ("No recent price"),
        /// draws no dot, and never borrows another number.
        let chance: Double?
        /// The venue's observation clock for the quote behind `chance`
        /// (`pregamePrice` basis only), kept so the price can expire while a
        /// reader is looking (`current(at:)`).
        let observedAt: String?
        /// The original row (`GameMarketPlayerProp.id`), for exact details.
        let rowID: String
        /// The server's grade, after the final only.
        let hit: Bool?
        var id: String { rowID }
    }

    let id: String
    let player: String
    let stat: String
    let side: PlayerPropsTeam.Side
    let basis: Basis
    let rungs: [Rung]
    /// The stat's final value as the server graded it; nil until then.
    let actual: Double?
    /// #11285 — the served headshot of THIS ladder's own rows
    /// (`GameMarketPlayerProp.playerHeadshot`), never a name join; nil when
    /// none is served or the rows disagree (`headshot(of:)`).
    var headshot: URL? = nil

    /// The one https headshot a ladder's rows agree on, or nil.
    static func headshot(of rows: [GameMarketPlayerProp]) -> URL? {
        let served = Set(rows.compactMap(\.playerHeadshot)
            .map { $0.trimmingCharacters(in: .whitespaces) }.filter { !$0.isEmpty })
        guard served.count == 1, let url = served.first.flatMap({ URL(string: $0) }),
              url.scheme == "https" else { return nil }
        return url
    }

    /// Both bases are named for what they are: before kickoff the current
    /// price is the pregame chance; once play starts the number is the
    /// historical mark from before kickoff, never a live price.
    var caption: String {
        basis == .pregamePrice ? "Pregame chance to reach each line" : "Chance before kickoff to reach each line"
    }

    /// The rung a card opens on: the one nearest even odds, ties low
    /// (`PlayerPropsFamily.defaultTarget`).
    var defaultRung: Int? { PlayerPropsFamily.defaultTarget(probabilities: rungs.map(\.chance)) }

    /// The milestone profile this card draws, from its own priced rungs.
    @MainActor
    var profile: PlayerMilestoneProfile.Profile? {
        PlayerMilestoneProfile.profile(thresholds: rungs.map(\.threshold), probabilities: rungs.map(\.chance))
    }

    /// The card as it may be shown at `now`: a pregame price that has stopped
    /// being observed loses its number, the same rule `cards` admits on, so a
    /// card held open does not keep a price current because the reader was
    /// looking (v159's rule, applied to quotes). The mark basis is a
    /// historical number and does not age.
    func current(at now: Date) -> NFLMilestoneCard9483 {
        guard basis == .pregamePrice else { return self }
        let aged = rungs.map { rung -> Rung in
            guard rung.chance != nil, !Self.isRecent(rung.observedAt, now: now) else { return rung }
            return Rung(threshold: rung.threshold, chance: nil, observedAt: rung.observedAt,
                        rowID: rung.rowID, hit: rung.hit)
        }
        return NFLMilestoneCard9483(id: id, player: player, stat: stat, side: side, basis: basis,
                                    rungs: aged, actual: actual, headshot: headshot)
    }

    /// A quote is recent when its observation clock is readable and no older
    /// than `SourceAge.liveStaleAfter` — the bound every live price on the
    /// page uses. An undatable quote is NOT recent here: this card prints it
    /// as a current chance, so unknown counts toward "no recent price".
    nonisolated static func isRecent(_ observedAt: String?, now: Date) -> Bool {
        guard let age = SourceAge.ageSeconds(observedAt, now: now) else { return false }
        return age <= SourceAge.liveStaleAfter
    }

    /// The stat axis the chart draws: the profile's own domain, widened at
    /// either end so the actual always sits inside the plot with room to
    /// spare — a final 0 below a ladder starting at 0.5 included. The actual
    /// is a stat value on this axis, never a probability.
    nonisolated static func statDomain(_ domain: ClosedRange<Double>, actual: Double?) -> ClosedRange<Double> {
        guard let actual, actual.isFinite else { return domain }
        let pad = max((domain.upperBound - domain.lowerBound) * 0.06, 0.5)
        let lower = min(domain.lowerBound, actual - pad)
        let upper = max(domain.upperBound, actual + pad)
        return lower...upper
    }

    /// The player cards for this page, best first, at most
    /// `NFLEventCardDeck9483.maximumMilestoneCards`, one per player.
    ///
    /// Grouped exactly as the player props card groups them
    /// (`PlayerPropsCardView.allPlayerCards`): the subject before the colon,
    /// one ladder per full market name. A ladder is a candidate only when its
    /// chosen chance draws a milestone profile (three or more priced, distinct
    /// lines; #5137's flat-ladder refusal). Team subjects (D/ST, a club) are
    /// not players.
    @MainActor
    static func cards(
        props: [GameMarketPlayerProp], eventStatus: String?, commenceTime: Date?,
        homeTeam: String, awayTeam: String, now: Date = Date()
    ) -> [NFLMilestoneCard9483] {
        let started = eventStatus == "live" || EventState.isFinished(eventStatus)
            || EventState.hasStarted(commenceTime: commenceTime, now: now)
        let finished = EventState.isFinished(eventStatus)
        let basis: Basis = started ? .pregameMark : .pregamePrice

        var ladders: [String: (player: String, market: String, rows: [GameMarketPlayerProp])] = [:]
        for prop in props {
            let parts = prop.outcomeName.split(separator: ":", maxSplits: 1)
            guard parts.count == 2 else { continue }
            let player = PropSubject.display(parts[0].trimmingCharacters(in: .whitespaces))
            guard !PlayerPropsFamily.isTeamSubject(player, teams: [homeTeam, awayTeam]) else { continue }
            let market = prop.marketName.trimmingCharacters(in: .whitespaces)
            ladders["\(player)|\(market)", default: (player, market, [])].rows.append(prop)
        }

        let candidates: [(card: NFLMilestoneCard9483, family: String)] = ladders.compactMap { key, ladder in
            let rungs = ladder.rows.compactMap { row -> Rung? in
                guard let threshold = row.threshold, threshold.isFinite,
                      // The catalog's side rule: only a row naming the over
                      // side reads `over_probability` or its mark (gotcha #17).
                      QuestionCatalog9483.lineSide(QuestionCatalog9483.row(row)) == .over else { return nil }
                let observedAt = basis == .pregamePrice ? row.observedAt : nil
                var chance = basis == .pregamePrice ? row.overProbability : row.pregameMark
                if let c = chance, !(c.isFinite && (0...1).contains(c)) { chance = nil }
                if basis == .pregamePrice, !isRecent(observedAt, now: now) { chance = nil }
                return Rung(threshold: threshold, chance: chance, observedAt: observedAt,
                            rowID: row.id, hit: finished ? row.hit : nil)
            }.sorted { $0.threshold < $1.threshold }
            let stat = PlayerPropsStatLabel.display(
                marketName: ladder.market, homeTeam: homeTeam, awayTeam: awayTeam, player: ladder.player)
            let card = NFLMilestoneCard9483(
                id: key, player: ladder.player, stat: stat,
                side: PlayerPropsTeam.side(for: ladder.rows.compactMap(\.playerTeam).first),
                basis: basis, rungs: rungs,
                actual: finished ? ladder.rows.compactMap(\.actual).first : nil,
                headshot: headshot(of: ladder.rows))
            guard card.profile != nil else { return nil }
            return (card, PlayerPropsFamily.family(statLabel: stat, isPriced: true))
        }

        // The stat the game is most quoted on leads (the chooser's own order),
        // then the longer priced ladder, then the key — a relaunch deals the same deck.
        let order = PlayerPropsFamily.orderedFamilies(candidates.map(\.family))
        let rank = Dictionary(uniqueKeysWithValues: order.enumerated().map { ($1, $0) })
        let ranked = candidates.sorted { a, b in
            let (ra, rb) = (rank[a.family] ?? .max, rank[b.family] ?? .max)
            if ra != rb { return ra < rb }
            let (pa, pb) = (a.card.rungs.filter { $0.chance != nil }.count, b.card.rungs.filter { $0.chance != nil }.count)
            if pa != pb { return pa > pb }
            return a.card.id < b.card.id
        }
        var players = Set<String>()
        var chosen: [NFLMilestoneCard9483] = []
        for candidate in ranked where chosen.count < NFLEventCardDeck9483.maximumMilestoneCards {
            guard players.insert(candidate.card.player).inserted else { continue }
            chosen.append(candidate.card)
        }
        return chosen
    }
}
