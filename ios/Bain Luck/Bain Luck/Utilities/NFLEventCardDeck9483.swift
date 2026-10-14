import Foundation

/// #9483 — the NFL page's visual cards (design ref #10868 v105/v107): the
/// forecast-versus-actual card and the player milestone cards that sit under
/// the paired chart, each openable full size.
///
/// Every number on a card is one the page already serves. The deck adds no
/// source and no ranking service; its order is fixed per page state, so a card
/// never moves while a reader is looking at it (v157/v158).
enum NFLEventCard9483: Equatable, Identifiable {
    case finish(NFLFinishCard9483)
    case milestone(NFLMilestoneCard9483)

    var id: String {
        switch self {
        case .finish: return "finish"
        case .milestone(let card): return "milestone:\(card.id)"
        }
    }

    var title: String {
        switch self {
        case .finish(let card): return card.kicker
        case .milestone(let card): return "\(card.player) · \(card.stat)"
        }
    }
}

enum NFLEventCardDeck9483 {
    /// At most this many player cards: the deck is a story, not the catalog —
    /// every ladder stays in the player props section below.
    static let maximumMilestoneCards = 2

    /// The deck for this page, or empty to draw none. NFL only.
    @MainActor
    static func cards(
        sportKey: String?, finish: NFLFinishCard9483?, milestones: [NFLMilestoneCard9483]
    ) -> [NFLEventCard9483] {
        guard NFLRecognizablePage9483.applies(sportKey: sportKey) else { return [] }
        return (finish.map { [.finish($0)] } ?? []) + milestones.map { .milestone($0) }
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
nonisolated struct NFLFinishCard9483: Equatable {
    nonisolated struct Pair: Equatable {
        let away: Double
        let home: Double
        let at: Date?

        /// nil when level.
        var homeLeads: Bool? { home == away ? nil : home > away }
    }

    nonisolated enum Phase: Equatable { case before, during, after }

    let phase: Phase
    let pregame: Pair
    /// The newest admitted projection while live.
    let projectedNow: Pair?
    /// The final score after the final.
    let final: Pair?

    var kicker: String { phase == .after ? "Final vs forecast" : "Projected finish" }

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
                guard let leads = pregame.homeLeads else { return "Projected level before kickoff" }
                return "\(name(leads)) projected ahead before kickoff"
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
    @MainActor
    static func build(_ input: ProjectedFinalPointsSeries.Input?) -> NFLFinishCard9483? {
        guard let input, NFLRecognizablePage9483.applies(sportKey: input.sportKey),
              let series = ProjectedFinalPointsSeries.build(input) else { return nil }
        let points = series.segments.flatMap { $0 }
        let floor = input.scoreObservationStartAt ?? input.kickoffAt
        let pregamePoint: ProjectedFinalPointsSeries.Point?
        switch series.phase {
        case .before: pregamePoint = series.latestIntervalUnavailable ? nil : series.latest
        case .during, .after: pregamePoint = floor.flatMap { f in points.last { $0.at < f } }
        }
        guard let pregamePoint else { return nil }
        let pregame = Pair(away: pregamePoint.away, home: pregamePoint.home, at: pregamePoint.at)
        switch series.phase {
        case .before:
            return NFLFinishCard9483(phase: .before, pregame: pregame, projectedNow: nil, final: nil)
        case .during:
            let latest = series.latest
            let now = !series.latestIntervalUnavailable && floor.map { latest.at >= $0 } == true
                ? Pair(away: latest.away, home: latest.home, at: latest.at) : nil
            return NFLFinishCard9483(phase: .during, pregame: pregame, projectedNow: now, final: nil)
        case .after:
            guard let actual = series.latestActual else { return nil }
            return NFLFinishCard9483(phase: .after, pregame: pregame, projectedNow: nil,
                                     final: Pair(away: actual.away, home: actual.home, at: actual.at))
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
        let chance: Double
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

    var caption: String {
        basis == .pregamePrice ? "Chance to reach each line" : "Pre-game chance to reach each line"
    }

    /// The rung a card opens on: the one nearest even odds, ties low
    /// (`PlayerPropsFamily.defaultTarget`).
    var defaultRung: Int? { PlayerPropsFamily.defaultTarget(probabilities: rungs.map(\.chance)) }

    /// The milestone profile this card draws, from its own rungs.
    @MainActor
    var profile: PlayerMilestoneProfile.Profile? {
        PlayerMilestoneProfile.profile(thresholds: rungs.map(\.threshold), probabilities: rungs.map(\.chance))
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
                guard let threshold = row.threshold, threshold.isFinite else { return nil }
                let chance = basis == .pregamePrice ? row.overProbability : row.pregameMark
                guard let chance, chance.isFinite, (0...1).contains(chance) else { return nil }
                return Rung(threshold: threshold, chance: chance, rowID: row.id, hit: finished ? row.hit : nil)
            }.sorted { $0.threshold < $1.threshold }
            let stat = PlayerPropsStatLabel.display(
                marketName: ladder.market, homeTeam: homeTeam, awayTeam: awayTeam, player: ladder.player)
            let card = NFLMilestoneCard9483(
                id: key, player: ladder.player, stat: stat,
                side: PlayerPropsTeam.side(for: ladder.rows.compactMap(\.playerTeam).first),
                basis: basis, rungs: rungs,
                actual: finished ? ladder.rows.compactMap(\.actual).first : nil)
            guard card.profile != nil else { return nil }
            return (card, PlayerPropsFamily.family(statLabel: stat, isPriced: true))
        }

        // The stat the game is most quoted on leads (the chooser's own order),
        // then the longer ladder, then the key — a relaunch deals the same deck.
        let order = PlayerPropsFamily.orderedFamilies(candidates.map(\.family))
        let rank = Dictionary(uniqueKeysWithValues: order.enumerated().map { ($1, $0) })
        let ranked = candidates.sorted { a, b in
            let (ra, rb) = (rank[a.family] ?? .max, rank[b.family] ?? .max)
            if ra != rb { return ra < rb }
            if a.card.rungs.count != b.card.rungs.count { return a.card.rungs.count > b.card.rungs.count }
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
