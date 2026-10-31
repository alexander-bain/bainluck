import Foundation

/// #10868 — THE HOCKEY JOURNEY SCREEN'S PRODUCTION ADAPTER, PART THREE: THE
/// PLAYER POINTS AND ASSISTS STORIES.
///
/// PILLARS: FORMATTING / TRUTH. SHIP: on `nhl-journey` the points card (columns)
/// and the assists card (bars) print, for each player and milestone, exactly the
/// pregame chance, in-game reading, count and result the event page's own prop
/// readers already decide, or that slot's own absence words.
///
/// It decides nothing the app does not already decide. Each slot is the output
/// of the authority that owns it:
///
///   - phase            `HockeyJourneyPageAdapter10868.phase` (part one), said in
///                      the leaf's own words by `contributionPhase`.
///   - ladders          `PlayerPropsCardView.allPlayerCards`' grouping: the
///                      subject before the outcome's first colon, through
///                      `PropSubject.display`; team subjects dropped as
///                      `NFLMilestoneCard9483.cards` drops them
///                      (`PlayerPropsFamily.isTeamSubject`); the stat read
///                      through `PlayerPropsStatLabel.display` +
///                      `PlayerPropsFamily.name`; over-side rows only
///                      (`QuestionCatalog9483.lineSide`, gotcha #17). The
///                      player's side is the first row that knows
///                      (`PlayerPropsTeam.side`, #4919), never a default.
///   - pregame chance   `NFLMilestoneCard9483.cards`' two bases (#9483). Before
///                      the start the quote's own `over_probability`, admitted
///                      only while `NFLMilestoneCard9483.isRecent` finds its own
///                      `observed_at` recent (an undated quote is not recent).
///                      Once started (`live`, finished, or the clock past the
///                      listed start) the served `pregame_mark` (#4577) and
///                      nothing else: never `opening_over_probability`, never the
///                      current price, never a neighbouring milestone
///                      (`PlayerPropsScript`). `pregame_mark` carries no clock of
///                      its own, so none is printed. A flat ladder is no price
///                      (`PlayerPropsPricing.isPricedLadder`, #5137).
///   - in-game reading  during play only. `QuestionCatalog9483.reading`, the
///                      All markets live rule (`SourceAge.liveStaleAfter`), on
///                      the row's own `observed_at`, admitted only for an
///                      observation at or after the start. A settled row's price
///                      is never a chance. No movement is printed: the served
///                      `movement` is current minus OPENING, not since pregame,
///                      and this file subtracts nothing.
///   - reached so far   `PlayerPropsCardView.rungVerdict` on the box count only
///                      (the props card's live hit, #4907), as performance.
///   - counts           `PlayerPropsCardView.actualStatValue` (exact normalised
///                      name identity, fail closed) on the per-player box the
///                      page already holds (`/related-futures` `box_score`, read
///                      by `PlayerPropsCardView.boxScore`). Points are goals +
///                      assists, the server's own definition (`"kxnhlpts":
///                      ["goals", "assists"]`, backend
///                      `tasks/backfill_winners.py`): ESPN's NHL box has no
///                      points field. A box line is never read from a prop.
///   - result           after the final only, and only from the served
///                      settlement: `is_winner` with a venue's own
///                      `resolution_source` (`OutcomeVerdict.isAuthoritative`,
///                      never the retraction). Unknown is not loss: no
///                      settlement is "Result unconfirmed", never "Missed". A
///                      settlement the box count or the served `hit`
///                      contradicts is also unconfirmed — this file never picks
///                      one side of a disagreement.
///   - target, default  `PlayerPropsFamily.targetLabel`; the default milestone
///                      is `PlayerPropsFamily.defaultTarget` over the printed
///                      pregame chances (nearest even odds, ties low), as
///                      `NFLMilestoneCard9483.defaultRung` reads it.
///   - player order     `PlayerPropsOrder.cardPrecedes` over the printed pregame
///                      chances (the props card's #4857 key, read on pregame
///                      numbers so a settled 100%/0% never ranks anyone).
///   - words            every percent through `formatProbability`; every clock
///                      through `HockeyJourneyPageAdapter10868.clockWords`;
///                      venues through `SourceLabels.label`; teams through
///                      `TeamShortName.shortPair`; counts through
///                      `PlayerPropsCardView.formatStatValue`.
///
/// IDENTITY. A player is `player:` + `PlayerPropsCardView.normalizedPlayerName`
/// of the served subject: the served rows carry no provider player id (the
/// ESPN id inside `player_headshot` is a URL, absent on rescue rows, and is not
/// read). A milestone is its venue's source, `|`, then the row's own
/// `GameMarketPlayerProp.id` (`market_name-outcome_name`, the row id
/// `NFLMilestoneCard9483.Rung.rowID` keeps) — one source record, never an index.
///
/// The host passes what it already holds and this file never fetches: the event,
/// `/game-markets`, the per-player box, now, the reader's calendar, and the
/// reader's own player and milestone choices. A chosen id that is no longer
/// served gets no substitute.
///
/// WHOSE BODY (#10868 F1b): `/game-markets` is this game's only when its
/// `eventId` is exactly `event.id` (`ownMarkets`) — no name or time matching.
/// Another game's body reads as no body: no ladder, so no card. The host decides
/// this once; `ladders` checks it again itself.
enum HockeyJourneyContributionAdapter10868 {

    /// The two stories. Points keep columns; assists keep bars.
    enum Stat: Equatable {
        case points
        case assists

        var orientation: PlayerContributionOrientation10868 { self == .points ? .columns : .bars }
        /// The stat words a ladder must read as, after the matchup.
        var statWord: String { self == .points ? "Points" : "Assists" }
        var singular: String { self == .points ? "point" : "assist" }
        var plural: String { self == .points ? "points" : "assists" }
    }

    /// What the host already holds, passed in unchanged.
    struct Host {
        /// `vm.relatedFutures?.boxScore` — the per-player box the props card
        /// reads. `EventDetail.boxScoreData` decodes only the period scores.
        let boxScore: [String: [String: Double]]?
        let now: Date
        /// The reader's own calendar, time zone and locale; clock words are said in it.
        let calendar: Calendar
        let locale: Locale

        init(boxScore: [String: [String: Double]]?, now: Date = Date(),
             calendar: Calendar = .current, locale: Locale = .current) {
            self.boxScore = boxScore
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
        static let pointsEyebrow = "PLAYER POINTS"
        static let assistsEyebrow = "PLAYER ASSISTS"
        static let pointsTitle = "Points in context"
        static let assistsTitle = "Who creates the goals?"
        static let pointsDefinition = "One point for each goal or assist."
        static let assistsDefinition = "An assist credits a player who helped create a goal."
        static let chartTitle = "Pregame chances · at least this many"
        static let unavailable = "Unavailable"
        /// A ladder whose rungs fail the props card's own ordering check: both rungs are withheld. Same
        /// words as web `CONTRIBUTION_WORDS.notPriced`.
        static let notPriced = "Chance unavailable"
        /// `AllMarketsCatalogView9483.noRecentPrice`, the page's one spelling.
        static let noRecentUpdate = "No recent probability update"
        static let noInGameReading = "No in-game reading"
        static let reachedSoFar = "Reached so far"
        static let milestoneReachedSoFar = "Milestone reached so far"
        static let reached = "Reached"
        static let missed = "Missed"
        static let unconfirmed = "Result unconfirmed"
        static let countUnavailable = "Count unavailable"
        static let finalCountUnavailable = "Final count unavailable"
        static let savedBeforeStart = "saved before the start"
        /// The box carries no observation clock on either served channel.
        static let boxSoFar = "box score · update time not recorded"
        static let boxFinal = "box score after the final"
        static let timingSuffix = "probability timing"
    }

    /// Axis labels on the fixed 0...1 scale — scale words, not chances, so they
    /// do not go through `formatProbability` (which would print "<1%"/">99%").
    static let ticks = [
        PlayerContributionTick10868(value: 0, text: "0%"),
        PlayerContributionTick10868(value: 0.5, text: "50%"),
        PlayerContributionTick10868(value: 1, text: "100%"),
    ]

    // MARK: - Inputs

    /// The game markets, only when they are this game's by their served id —
    /// `eventId` exactly `event.id`, no name or time matching. A foreign or
    /// absent body is none. The hockey readers that open a body (`ladders`
    /// here, `HockeyJourneyOriginalsAdapter10868.originals`) check it themselves.
    static func ownMarkets(_ markets: GameMarketsResponse?, for event: EventDetail) -> GameMarketsResponse? {
        markets.flatMap { $0.eventId == event.id ? $0 : nil }
    }

    static func points(_ event: EventDetail, markets: GameMarketsResponse?, host: Host,
                       selectedPlayerID: String? = nil,
                       selectedMilestoneID: String? = nil) -> PlayerContributionInput10868? {
        input(.points, event: event, markets: markets, host: host,
              selectedPlayerID: selectedPlayerID, selectedMilestoneID: selectedMilestoneID)
    }

    static func assists(_ event: EventDetail, markets: GameMarketsResponse?, host: Host,
                        selectedPlayerID: String? = nil,
                        selectedMilestoneID: String? = nil) -> PlayerContributionInput10868? {
        input(.assists, event: event, markets: markets, host: host,
              selectedPlayerID: selectedPlayerID, selectedMilestoneID: selectedMilestoneID)
    }

    /// The card, or nil when no player has a ladder for this stat. With no
    /// choice the first player in order is shown at its default milestone; a
    /// chosen player no longer served is no player (the leaf's own words), and a
    /// chosen milestone is passed through exactly for the leaf to resolve.
    static func input(_ stat: Stat, event: EventDetail, markets: GameMarketsResponse?, host: Host,
                      selectedPlayerID: String? = nil,
                      selectedMilestoneID: String? = nil) -> PlayerContributionInput10868? {
        let pagePhase = HockeyJourneyPageAdapter10868.phase(event, now: host.now)
        let found = ladders(stat, event: event, markets: markets)
        guard !found.isEmpty else { return nil }
        let names = TeamShortName.shortPair(away: event.awayTeam, home: event.homeTeam, sportKey: event.sport)
        let built = found
            .map { card($0, stat: stat, event: event, phase: pagePhase, host: host, names: names) }
            .sorted { PlayerPropsOrder.cardPrecedes($0.order, $1.order) }

        let chosen: Card?
        if let selectedPlayerID {
            chosen = built.first { $0.player.id == selectedPlayerID }
        } else {
            chosen = built.first
        }
        let milestoneID = selectedMilestoneID ?? chosen?.defaultMilestoneID
        let timing: PlayerContributionTiming10868?
        if let chosen, let milestoneID {
            timing = chosen.timing.first { $0.milestoneID == milestoneID }
        } else {
            timing = nil
        }
        let chooser = built.count < 2 ? nil : PlayerContributionChooser10868(
            title: "Choose player · \(built.count)",
            choices: built.map { PlayerContributionChoice10868(id: $0.player.id, name: $0.player.name,
                                                               detail: $0.player.team) })
        return PlayerContributionInput10868(
            phase: pagePhase.contributionPhase,
            orientation: stat.orientation,
            eyebrow: stat == .points ? Words.pointsEyebrow : Words.assistsEyebrow,
            title: stat == .points ? Words.pointsTitle : Words.assistsTitle,
            definition: stat == .points ? Words.pointsDefinition : Words.assistsDefinition,
            player: chosen?.player,
            selectedMilestoneID: milestoneID,
            chartTitle: Words.chartTitle,
            ticks: ticks,
            chooser: chooser,
            timing: timing)
    }

    // MARK: - Ladders

    /// One player's one ladder for the stat: over-side rows with distinct finite
    /// thresholds, ascending.
    struct Ladder: Equatable {
        let playerID: String
        let name: String
        let side: PlayerPropsTeam.Side
        let rows: [GameMarketPlayerProp]
    }

    private struct Group {
        let playerID: String
        let name: String
        let market: String
        let source: String
        var rows: [GameMarketPlayerProp]
    }

    /// Every player's ladder for `stat`, one per player. Two venues or two
    /// market names are two ladders and are never blended; when a player has
    /// more than one, the longer wins, then the market name, then the source
    /// (`PlayerPropsOrder.statGroupPrecedes`' shape), so a relaunch deals the
    /// same card. Only from this game's own body (`ownMarkets`).
    static func ladders(_ stat: Stat, event: EventDetail, markets: GameMarketsResponse?) -> [Ladder] {
        var servedSide: [String: String] = [:]
        var order: [String] = []
        var groups: [String: Group] = [:]
        // A missing body and another game's body read the same: no ladder, so no card.
        for prop in ownMarkets(markets, for: event)?.playerProps ?? [] {
            guard let name = subject(prop),
                  !PlayerPropsFamily.isTeamSubject(name, teams: [event.homeTeam, event.awayTeam])
            else { continue }
            let id = playerID(name)
            // #4919 — the first row that KNOWS, across the player's props.
            if servedSide[id] == nil, let team = prop.playerTeam { servedSide[id] = team }
            guard isStat(stat, prop, subject: name, event: event),
                  let threshold = prop.threshold, threshold.isFinite,
                  QuestionCatalog9483.lineSide(QuestionCatalog9483.row(prop)) == .over
            else { continue }
            let market = prop.marketName.trimmingCharacters(in: .whitespaces)
            let source = venueKey(prop)
            let key = [id, market, source].joined(separator: "\u{1F}")
            if groups[key] == nil {
                order.append(key)
                groups[key] = Group(playerID: id, name: name, market: market, source: source, rows: [])
            }
            // A second row at one threshold is a duplicate, never a second chance.
            guard groups[key]?.rows.contains(where: { $0.threshold == threshold }) == false else { continue }
            groups[key]?.rows.append(prop)
        }

        var best: [String: Group] = [:]
        var players: [String] = []
        for key in order {
            guard let group = groups[key] else { continue }
            guard let held = best[group.playerID] else {
                best[group.playerID] = group
                players.append(group.playerID)
                continue
            }
            if (group.rows.count, held.market, held.source) > (held.rows.count, group.market, group.source) {
                best[group.playerID] = group
            }
        }
        return players.compactMap { id in
            best[id].map { group in
                Ladder(playerID: id, name: group.name,
                       side: PlayerPropsTeam.side(for: servedSide[id]),
                       rows: group.rows.sorted { ($0.threshold ?? 0) < ($1.threshold ?? 0) })
            }
        }
    }

    /// The served subject before the outcome's first colon, as the props card
    /// names it; nil for an outcome that names no subject.
    static func subject(_ prop: GameMarketPlayerProp) -> String? {
        let parts = prop.outcomeName.split(separator: ":", maxSplits: 1)
        guard parts.count == 2 else { return nil }
        let name = PropSubject.display(parts[0].trimmingCharacters(in: .whitespaces))
        return name.isEmpty ? nil : name
    }

    static func playerID(_ subject: String) -> String {
        "player:" + PlayerPropsCardView.normalizedPlayerName(subject)
    }

    static func milestoneID(_ prop: GameMarketPlayerProp) -> String {
        "\(venueKey(prop))|\(prop.id)"
    }

    /// The venue half of an identity key: the served source key, or empty.
    /// A key only — a venue is named to the reader through `SourceLabels`
    /// (#4135), never through this.
    static func venueKey(_ prop: GameMarketPlayerProp) -> String {
        guard let venue = prop.source else { return "" }
        return venue
    }

    private static func isStat(_ stat: Stat, _ prop: GameMarketPlayerProp, subject: String,
                               event: EventDetail) -> Bool {
        let label = PlayerPropsStatLabel.display(marketName: prop.marketName, homeTeam: event.homeTeam,
                                                 awayTeam: event.awayTeam, player: subject)
        return PlayerPropsFamily.name(statLabel: label).caseInsensitiveCompare(stat.statWord) == .orderedSame
    }

    // MARK: - One player's card

    struct Card {
        let player: PlayerContributionPlayer10868
        let order: PlayerPropsOrder.CardKey
        let defaultMilestoneID: String?
        let timing: [PlayerContributionTiming10868]
    }

    /// A milestone's pregame slot: the observation, its missing words, and the
    /// timing line's words.
    struct PregameReading: Equatable {
        let observation: PlayerContributionObservation10868?
        let missing: String
        var timingWords: String { observation?.accessibilityDetail ?? missing }
    }

    static func card(_ ladder: Ladder, stat: Stat, event: EventDetail, phase: HockeyJourneyPagePhase10868,
                     host: Host, names: (away: String, home: String)) -> Card {
        let started = hasStarted(event, now: host.now)
        var pregame = ladder.rows.map { pregameReading($0, started: started, host: host) }
        // #5137 — a ladder printing one repeated number is not a price.
        let printed = pregame.compactMap { $0.observation?.probability }
        if !PlayerPropsPricing.isPricedLadder(printed) {
            pregame = pregame.map { _ in PregameReading(observation: nil, missing: Words.notPriced) }
        }
        let count = Self.count(stat, name: ladder.name, box: host.boxScore)
        let actual = actualSlot(count, stat: stat, phase: phase)

        var milestones: [PlayerContributionMilestone10868] = []
        var timing: [PlayerContributionTiming10868] = []
        for (row, before) in zip(ladder.rows, pregame) {
            let threshold = row.threshold ?? 0
            let target = PlayerPropsFamily.targetLabel(threshold)
            let title = "\(target) \(stat.plural)"
            let id = milestoneID(row)
            let reached = count.map {
                PlayerPropsCardView.rungVerdict(servedActual: nil, servedHit: nil, threshold: threshold,
                                                boxActual: $0.total).hit == true
            } ?? false
            let current: PlayerContributionCurrent10868 = phase == .live
                ? inGameReading(row, reachedSoFar: reached, event: event, host: host)
                : .unavailable(Words.noInGameReading)
            let progress: PlayerContributionProgress10868? = phase == .live
                ? count.map { progressStatus($0.total, threshold: threshold, target: target, reached: reached) }
                : nil
            let result: PlayerContributionResult10868 = phase == .final
                ? contractResult(row, count: count?.total, threshold: threshold)
                : .unconfirmed(Words.unconfirmed)
            milestones.append(PlayerContributionMilestone10868(
                id: id, target: target, title: title, before: before.observation,
                beforeMissing: before.missing, current: current, progress: progress, result: result))
            timing.append(PlayerContributionTiming10868(
                milestoneID: id, title: "\(ladder.name) \(title) · \(Words.timingSuffix)",
                lines: timingLines(before: before, current: current, actual: actual, result: result,
                                   row: row, phase: phase)))
        }

        let team: String? = switch ladder.side {
        case .home: names.home
        case .away: names.away
        case .unknown: nil
        }
        let chances = milestones.map { $0.before?.probability }
        let printedChances = chances.compactMap { $0 }
        return Card(
            player: PlayerContributionPlayer10868(id: ladder.playerID, name: ladder.name, team: team,
                                                  milestones: milestones, actual: actual),
            order: PlayerPropsOrder.CardKey(rungs: printedChances.count,
                                            topProbability: printedChances.max() ?? 0, name: ladder.name),
            defaultMilestoneID: PlayerPropsFamily.defaultTarget(probabilities: chances).map { milestones[$0].id },
            timing: timing)
    }

    /// `NFLMilestoneCard9483.cards`' own "started": live, finished, or the clock
    /// past the listed start (a nil start counts as started).
    static func hasStarted(_ event: EventDetail, now: Date) -> Bool {
        event.status == "live" || EventState.isFinished(event.status)
            || EventState.hasStarted(commenceTime: event.commenceTime?.asDate, now: now)
    }

    // MARK: - Slots

    /// Before the start: the quote's own price while its own clock is recent.
    /// Once started: the served pregame mark, or "Unavailable".
    static func pregameReading(_ row: GameMarketPlayerProp, started: Bool, host: Host) -> PregameReading {
        let venue = SourceLabels.label(for: row.source)
        if started {
            guard let mark = admissible(row.pregameMark) else {
                return PregameReading(observation: nil, missing: Words.unavailable)
            }
            return PregameReading(observation: observation(mark, detail: joined([Words.savedBeforeStart, venue])),
                                  missing: Words.unavailable)
        }
        guard let price = admissible(row.overProbability) else {
            return PregameReading(observation: nil, missing: Words.unavailable)
        }
        guard NFLMilestoneCard9483.isRecent(row.observedAt, now: host.now), let at = row.observedAt?.asDate else {
            return PregameReading(observation: nil, missing: Words.noRecentUpdate)
        }
        let clock = "recorded \(HockeyJourneyPageAdapter10868.clockWords(at, host: host.page))"
        return PregameReading(observation: observation(price, detail: joined([clock, venue])),
                              missing: Words.unavailable)
    }

    /// During play: performance first, then a settled row (never a chance), then
    /// the row's own clock — undated, from before the start, or stale is no
    /// in-game reading.
    static func inGameReading(_ row: GameMarketPlayerProp, reachedSoFar: Bool, event: EventDetail,
                              host: Host) -> PlayerContributionCurrent10868 {
        if reachedSoFar { return .reached(Words.reachedSoFar) }
        if row.isWinner != nil && row.resolutionSource != nil { return .unavailable(Words.noInGameReading) }
        guard admissible(row.overProbability) != nil else { return .unavailable(Words.noInGameReading) }
        guard let at = row.observedAt?.asDate else { return .withheld(Words.noRecentUpdate) }
        if let start = event.commenceTime?.asDate, at < start { return .unavailable(Words.noInGameReading) }
        let reading = QuestionCatalog9483.reading(QuestionCatalog9483.row(row), status: event.status, now: host.now)
        if reading.absence == .stale || !NFLMilestoneCard9483.isRecent(row.observedAt, now: host.now) {
            return .withheld(Words.noRecentUpdate)
        }
        guard let price = admissible(reading.probability) else { return .unavailable(Words.noInGameReading) }
        let clock = "recorded \(HockeyJourneyPageAdapter10868.clockWords(at, host: host.page))"
        return .recorded(observation(price, detail: joined([clock, SourceLabels.label(for: row.source)])),
                         movement: nil)
    }

    /// The count toward the target, as performance; never a probability.
    static func progressStatus(_ count: Double, threshold: Double, target: String,
                               reached: Bool) -> PlayerContributionProgress10868 {
        if reached { return PlayerContributionProgress10868(status: Words.milestoneReachedSoFar, fraction: 1) }
        let more = max(1, Int((threshold - count).rounded(.up)))
        let fraction = threshold > 0 ? min(max(count / threshold, 0), 1) : nil
        return PlayerContributionProgress10868(status: "\(more) more for \(target)", fraction: fraction)
    }

    /// The served settlement's verdict, or nil when the row carries none: a
    /// winner flag with a venue's own `resolution_source`, never the retraction.
    static func settlement(_ row: GameMarketPlayerProp) -> Bool? {
        guard let won = row.isWinner, let source = row.resolutionSource,
              source != OutcomeVerdict.retractedResolutionSource,
              OutcomeVerdict.isAuthoritative(source) else { return nil }
        return won
    }

    /// Does anything served contradict the settlement? The box count (through
    /// the props card's own verdict) and the served `hit` are each checked;
    /// either disagreeing withholds the grade.
    static func contradicts(_ row: GameMarketPlayerProp, settlement won: Bool, count: Double?,
                            threshold: Double) -> Bool {
        if let count,
           let boxHit = PlayerPropsCardView.rungVerdict(servedActual: nil, servedHit: nil, threshold: threshold,
                                                        boxActual: count).hit,
           boxHit != won { return true }
        if let hit = row.hit, hit != won { return true }
        return false
    }

    /// After the final: the served settlement only. Unknown is not loss.
    static func contractResult(_ row: GameMarketPlayerProp, count: Double?,
                               threshold: Double) -> PlayerContributionResult10868 {
        guard let won = settlement(row),
              !contradicts(row, settlement: won, count: count, threshold: threshold)
        else { return .unconfirmed(Words.unconfirmed) }
        return won ? .reached(Words.reached) : .missed(Words.missed)
    }

    // MARK: - Counts

    /// One player's box line for the stat. Points need both goals and assists.
    struct Count: Equatable {
        let total: Double
        let goals: Double?
        let assists: Double
    }

    static func count(_ stat: Stat, name: String, box: [String: [String: Double]]?) -> Count? {
        guard let box,
              let assists = PlayerPropsCardView.actualStatValue(player: name, stat: "assists", box: box),
              assists.isFinite, assists >= 0 else { return nil }
        switch stat {
        case .assists:
            return Count(total: assists, goals: nil, assists: assists)
        case .points:
            guard let goals = PlayerPropsCardView.actualStatValue(player: name, stat: "goals", box: box),
                  goals.isFinite, goals >= 0 else { return nil }
            return Count(total: goals + assists, goals: goals, assists: assists)
        }
    }

    static func actualSlot(_ count: Count?, stat: Stat, phase: HockeyJourneyPagePhase10868)
        -> PlayerContributionActual10868 {
        switch phase {
        case .before:
            return .unavailable(Words.countUnavailable)
        case .live:
            guard let count else { return .unavailable(Words.countUnavailable) }
            return .count(PlayerContributionCount10868(
                count: number(count.total), unit: "\(unit(count.total, stat)) so far",
                breakdown: breakdown(count), accessibilityDetail: Words.boxSoFar))
        case .final:
            guard let count else { return .unavailable(Words.finalCountUnavailable) }
            return .count(PlayerContributionCount10868(
                count: number(count.total), unit: unit(count.total, stat),
                breakdown: breakdown(count), accessibilityDetail: Words.boxFinal))
        }
    }

    /// "1 goal + 1 assist" for points; nil for assists.
    static func breakdown(_ count: Count) -> String? {
        guard let goals = count.goals else { return nil }
        let g = goals == 1 ? "goal" : "goals"
        let a = count.assists == 1 ? "assist" : "assists"
        return "\(number(goals)) \(g) + \(number(count.assists)) \(a)"
    }

    private static func unit(_ value: Double, _ stat: Stat) -> String {
        value == 1 ? stat.singular : stat.plural
    }

    private static func number(_ value: Double) -> String {
        PlayerPropsCardView.formatStatValue(value)
    }

    // MARK: - Timing

    static func timingLines(before: PregameReading, current: PlayerContributionCurrent10868,
                            actual: PlayerContributionActual10868, result: PlayerContributionResult10868,
                            row: GameMarketPlayerProp, phase: HockeyJourneyPagePhase10868) -> [String] {
        typealias T = PlayerContributionInput10868
        var lines = ["\(T.pregameTitle): \(before.timingWords)"]
        if phase == .live {
            switch current {
            case .recorded(let observation, _): lines.append("\(T.recordedTitle): \(observation.accessibilityDetail)")
            case .unavailable(let words), .withheld(let words): lines.append("\(T.currentStatusTitle): \(words)")
            case .reached(let words): lines.append("\(T.actualSoFarTitle): \(words)")
            }
        }
        if phase != .before {
            let title = phase == .live ? T.countSoFarTitle : T.finalCountTitle
            switch actual {
            case .count(let count): lines.append("\(title): \(count.accessibilityDetail)")
            case .unavailable(let words): lines.append("\(title): \(words)")
            }
        }
        if phase == .final {
            let settledBy = result.isAdmitted
                ? SourceLabels.label(for: row.source).map { "settled by \($0)" } : nil
            lines.append(joined(["\(T.resultTitle): \(result.text)", settledBy]) ?? result.text)
        }
        return lines
    }

    // MARK: - Words

    /// A finite probability in 0...1, or nil. A real 0 stays.
    private static func admissible(_ value: Double?) -> Double? {
        guard let value, value.isFinite, (0...1).contains(value) else { return nil }
        return value
    }

    private static func observation(_ value: Double, detail: String?) -> PlayerContributionObservation10868 {
        PlayerContributionObservation10868(probability: value, text: formatProbability(value),
                                           accessibilityDetail: detail ?? "")
    }

    private static func joined(_ parts: [String?]) -> String? {
        let kept = parts.compactMap { $0 }.filter { !$0.isEmpty }
        return kept.isEmpty ? nil : kept.joined(separator: " · ")
    }
}
