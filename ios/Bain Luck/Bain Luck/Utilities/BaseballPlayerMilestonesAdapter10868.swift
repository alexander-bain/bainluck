import Foundation

/// #10868 — THE BASEBALL GAME SCREEN'S PRODUCTION ADAPTER: THE LIVE PLAYER
/// HOME-RUN AND STRIKEOUT MILESTONES.
///
/// PILLARS: FORMATTING / TRUTH. SHIP: during an MLB game, home-run and
/// strikeout cards compare each player's stored pregame chance with the
/// current chance, using the approved player-milestone visual
/// (`PlayerContributionPresentation10868`), and open the exact probability and
/// clock seen on the card.
///
/// PARTIAL, AND SAID SO. This is during play only. Before first pitch no typed
/// player channel is served (G1), so no card is built and none is faked from
/// display strings. No live count is typed (G2), so the count says its own
/// words and no milestone is ever "reached". No pitching role is typed (G3), so
/// strikeouts stay the producer's generic "strikeouts". No genuine live HR/K
/// body is retained (M1). After the final the accepted final comparisons
/// (`MLBHomeRunCard11284`, `MLBMilestoneCard11284`) stay the stories, unchanged.
///
/// It decides nothing the app does not already decide. Each slot is the
/// output of the authority that owns it:
///
///   - phase        `BaseballGamePageAdapter10868.phase` is `.live`. The served
///                  `during_player_props` is itself null unless the served game
///                  is live (`DuringPlayerProps`).
///   - rows         only the already decoded During rows (`10236.v1`) of THIS
///                  event's own body (`eventId == event.id`). A row is admitted
///                  only for this stat (`statKey`), `full_game`, a `player`
///                  subject and the typed at-least, over contract. A
///                  `questionKey` carried more than once is dropped: an
///                  ambiguous origin is never resolved by order. No name,
///                  market label or outcome is parsed. No role is inferred, and
///                  the name-keyed box score is never joined.
///   - players      exact `subject.key`, in first-seen producer order. The
///                  name is the served `subject.label`. No team is typed on a
///                  row, so none is printed.
///   - milestones   the player's admitted rows, by the typed count. Id is the
///                  producer's `questionKey`. Target is the served predicate
///                  label. Title is `EventPropsMatrixLayout.question`, the
///                  server's own unit words.
///   - pregame      the producer's stored pin, only where the server proved the
///                  comparison (`comparison.isComparable`), the baseline is a
///                  `pregame_pin` with a finite chance, and the pin's own clock
///                  is readable. It is dated by that clock alone.
///   - current      `DuringPropCurrent.currentProbability(now:)` ALONE admits
///                  the current quote, a qualified 0 or 1 included. A stamp it
///                  cannot read shows with "time unavailable" and no age claim.
///                  A dated stale quote is withheld (`isStale`), keeps its last
///                  quote and time in Details and shows no movement. Movement
///                  is the server's comparable delta, only while current
///                  (`EventPropsMatrixLayout.changeText`).
///   - count        always this stat's own unavailable words. Never read from
///                  a threshold, a quote, a grade or a box.
///   - default      `PlayerPropsFamily.defaultTarget` over the shown pregame
///                  chances, within the shown player only. A held player or
///                  milestone id is passed through. One no longer served gets
///                  the leaf's own unavailable words, never a substitute.
///   - words        every percent through `formatProbability`; every clock
///                  through `BaseballGamePageAdapter10868.clockWords` on the
///                  card and `MLBOriginal11284.stamp` in Details; venues
///                  through `SourceLabels.label`.
///
/// DETAILS (`players`, `details`). The card and its exact originals come from
/// ONE pass over the same body. An original is
/// `mlb-o:<event>:during:<questionKey>`. Its first section says what the card
/// shows for that milestone, in the card's own words, figures and clocks. Then
/// come the recorded pregame reference, each contributor's raw leg
/// (`MLBOriginal11284.recorded`, unchanged), and the market and outcome ids. A
/// tap opens Details only when its id names exactly one drawn milestone of the
/// shown player and exactly one original of the same result, event and live
/// phase.
enum BaseballPlayerMilestonesAdapter10868 {

    /// The two stories.
    enum Stat: Equatable {
        case homeRuns
        case strikeouts

        /// The producer's typed stat key (`event_props_matrix.STAT_TABLE`).
        var statKey: String { self == .homeRuns ? "home_runs" : "strikeouts" }
        /// Design decision 3.
        var countUnavailable: String {
            self == .homeRuns ? Words.homeRunCountUnavailable : Words.strikeoutCountUnavailable
        }
        var eyebrow: String { self == .homeRuns ? Words.homeRunsEyebrow : Words.strikeoutsEyebrow }
        var title: String { self == .homeRuns ? Words.homeRunsTitle : Words.strikeoutsTitle }
    }

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
        var page: BaseballGamePageAdapter10868.Host {
            BaseballGamePageAdapter10868.Host(probabilityObservedAt: nil, now: now, calendar: calendar, locale: locale)
        }
    }

    /// The host's held reading for one stat, passed through unchanged.
    struct Held: Equatable {
        /// A player's exact `subject.key`.
        var player: String? = nil
        /// A milestone's exact `questionKey`.
        var milestone: String? = nil
    }

    /// The exact original behind one drawn milestone, keyed by the producer's
    /// own identities, never by a name, a label or a threshold.
    struct Origin: Equatable {
        let playerKey: String
        let milestoneID: String
        let original: MLBOriginal11284
    }

    /// The card and the originals behind every player's milestones, from ONE
    /// pass.
    struct Players: Equatable {
        let eventID: Int
        let stat: Stat
        let input: PlayerContributionInput10868
        /// One per admitted milestone of every player, in player then milestone order.
        let origins: [Origin]
    }

    enum Words {
        static let homeRunsEyebrow = "PLAYER HOME RUNS"
        static let strikeoutsEyebrow = "PLAYER STRIKEOUTS"
        static let homeRunsTitle = "Pregame and current home-run chances"
        static let strikeoutsTitle = "Pregame and current strikeout chances"
        static let chartTitle = "Chances · at least this many"
        static let homeRunCountUnavailable = "Home run count unavailable"
        static let strikeoutCountUnavailable = "Strikeout count unavailable"
        /// The page's one spelling (`AllMarketsCatalogView9483.noRecentPrice`).
        static let noRecentUpdate = AllMarketsCatalogView9483.noRecentPrice
        static let pregameUnavailable = BaseballRunMilestonesAdapter10868.Words.pregameUnavailable
        static let inGameUnavailable = BaseballRunMilestonesAdapter10868.Words.inGameUnavailable
        static let resultUnavailable = BaseballRunMilestonesAdapter10868.Words.resultUnavailable
        static let recorded = BaseballRunMilestonesAdapter10868.Words.recorded
        static let savedBeforeStart = BaseballRunMilestonesAdapter10868.Words.savedBeforeStart
        static let timingSuffix = BaseballRunMilestonesAdapter10868.Words.timingSuffix
        /// `MLBOriginal11284.stamp`'s own words for a clock it cannot read.
        static let timeUnavailable = "time unavailable"
        /// The milestone Details' name for the producer's stored pin
        /// (`BaseballRunMilestonesAdapter10868.Words.pinLabel`).
        static let pinLabel = BaseballRunMilestonesAdapter10868.Words.pinLabel
        static let lastRecorded = "Last recorded in-game"
        static let unavailable = "Unavailable"
        static let sources = "Sources"

        static func chooser(_ count: Int) -> String { "Choose player · \(count)" }
    }

    /// The contract this file reads.
    static let contract = "10236.v1"
    static let periodKey = "full_game"

    /// Scale words on the fixed 0...1 axis, not chances, so not through
    /// `formatProbability` (which would print "<1%"/">99%").
    static let ticks = [
        PlayerContributionTick10868(value: 0, text: "0%"),
        PlayerContributionTick10868(value: 0.5, text: "50%"),
        PlayerContributionTick10868(value: 1, text: "100%"),
    ]

    // MARK: - One pass

    /// The card for `stat` and the exact original behind each milestone, or nil
    /// unless the page is live and this event's own body admits a player.
    static func players(_ event: EventDetail, markets: GameMarketsResponse?, stat: Stat, host: Host,
                        held: Held = Held()) -> Players? {
        guard BaseballGamePageAdapter10868.phase(event, now: host.now) == .live,
              let markets, markets.eventId == event.id,
              let during = markets.duringPlayerProps, during.contract == contract else { return nil }
        let admitted = rows(during, stat: stat)
        guard !admitted.isEmpty else { return nil }
        let unit = during.stats.first { $0.statKey == stat.statKey && $0.periodKey == periodKey }

        var order: [String] = []
        var grouped: [String: [DuringPropRow]] = [:]
        for row in admitted {
            if grouped[row.subject.key] == nil { order.append(row.subject.key) }
            grouped[row.subject.key, default: []].append(row)
        }

        var players: [PlayerContributionPlayer10868] = []
        var defaults: [String: String] = [:]
        var timings: [String: [PlayerContributionTiming10868]] = [:]
        var origins: [Origin] = []
        for key in order {
            let rows = (grouped[key] ?? []).sorted { $0.predicate.count < $1.predicate.count }
            guard let name = rows.first?.subject.label else { continue }
            var milestones: [PlayerContributionMilestone10868] = []
            var timing: [PlayerContributionTiming10868] = []
            for row in rows {
                let title = EventPropsMatrixLayout.question(row, stat: unit)
                let milestone = PlayerContributionMilestone10868(
                    id: row.questionKey, target: row.predicate.label, title: title,
                    before: pregame(row, host: host), beforeMissing: Words.pregameUnavailable,
                    current: current(row, host: host), progress: nil,
                    result: .unconfirmed(Words.resultUnavailable))
                milestones.append(milestone)
                timing.append(PlayerContributionTiming10868(
                    milestoneID: row.questionKey, title: "\(name) \(title) · \(Words.timingSuffix)",
                    lines: timingLines(milestone, stat: stat)))
                origins.append(Origin(playerKey: key, milestoneID: row.questionKey,
                                      original: original(row, milestone: milestone, name: name, stat: stat,
                                                         eventID: event.id, host: host)))
            }
            players.append(PlayerContributionPlayer10868(id: key, name: name, team: nil, milestones: milestones,
                                                         actual: .unavailable(stat.countUnavailable)))
            defaults[key] = PlayerPropsFamily.defaultTarget(probabilities: milestones.map { $0.before?.probability })
                .map { milestones[$0].id }
            timings[key] = timing
        }

        // A held player no longer served is no player — the leaf's own words.
        let shown: PlayerContributionPlayer10868? = held.player == nil
            ? players.first
            : players.first(where: { $0.id == held.player })
        let milestoneID = held.milestone ?? shown.flatMap { defaults[$0.id] }
        let timing = shown.flatMap { player in
            milestoneID.flatMap { id in timings[player.id]?.first(where: { $0.milestoneID == id }) }
        }
        let chooser = players.count < 2 ? nil : PlayerContributionChooser10868(
            title: Words.chooser(players.count),
            choices: players.map { PlayerContributionChoice10868(id: $0.id, name: $0.name, detail: nil) })
        let input = PlayerContributionInput10868(
            phase: .during, orientation: .columns,
            eyebrow: stat.eyebrow, title: stat.title, definition: nil,
            player: shown, selectedMilestoneID: milestoneID,
            chartTitle: Words.chartTitle, ticks: ticks, chooser: chooser, timing: timing)
        return Players(eventID: event.id, stat: stat, input: input, origins: origins)
    }

    /// The admitted rows for `stat`, in producer order. A `questionKey` carried
    /// more than once is dropped entirely.
    static func rows(_ during: DuringPlayerProps, stat: Stat) -> [DuringPropRow] {
        let typed = during.rows.filter {
            $0.statKey == stat.statKey && $0.periodKey == periodKey && $0.subject.kind == "player"
                && !$0.subject.key.isEmpty && !$0.questionKey.isEmpty
                && $0.predicate.isAtLeast && $0.predicate.side == "over"
        }
        var counts: [String: Int] = [:]
        for row in typed { counts[row.questionKey, default: 0] += 1 }
        return typed.filter { counts[$0.questionKey] == 1 }
    }

    // MARK: - Details

    /// The Details a tapped milestone opens, or nil. `drawn` and `phase` are
    /// the page input the card was drawn from; `players` is the result that
    /// card came from.
    ///
    /// The id must name exactly one milestone of the drawn player AND exactly
    /// one original of that player in the same result. The drawn card must be
    /// exactly that result's card, on the live page of the same event.
    /// Anything else (unknown, duplicated, removed, another event's, another
    /// phase's or a final namespace's id) is nil, never a neighbour.
    static func details(_ id: String, drawn: PlayerContributionInput10868?, phase: BaseballEventPagePhase10868,
                        players: Players?, eventID: Int) -> MLBOriginal11284? {
        guard phase == .live, let players, players.eventID == eventID,
              let drawn, drawn == players.input, drawn.phase == .during,
              let player = drawn.player else { return nil }
        let milestones = player.milestones.filter { $0.id == id }
        let origins = players.origins.filter { $0.milestoneID == id }
        guard milestones.count == 1, origins.count == 1, let origin = origins.first,
              origin.playerKey == player.id else { return nil }
        return origin.original
    }

    // MARK: - Slots

    /// The producer's stored pin, only where the server proved the comparison
    /// and the pin carries a finite chance and its own readable clock.
    static func pregame(_ row: DuringPropRow, host: Host) -> PlayerContributionObservation10868? {
        guard let comparison = row.comparison, comparison.isComparable,
              let baseline = comparison.baseline, baseline.basis == "pregame_pin",
              let probability = baseline.probability, probability.isFinite, (0...1).contains(probability),
              let at = baseline.observedAt?.asDate else { return nil }
        let clock = BaseballGamePageAdapter10868.clockWords(at, host: host.page)
        return PlayerContributionObservation10868(probability: probability, text: formatProbability(probability),
                                                  accessibilityDetail: "\(Words.savedBeforeStart) \(clock)")
    }

    /// `currentProbability(now:)` alone admits the current quote. Its own clock
    /// or "time unavailable"; a dated stale quote is withheld.
    static func current(_ row: DuringPropRow, host: Host) -> PlayerContributionCurrent10868 {
        if let probability = row.current.currentProbability(now: host.now) {
            return .recorded(currentObservation(row, probability: probability, host: host),
                             movement: EventPropsMatrixLayout.changeText(row, now: host.now))
        }
        if row.current.isStale(now: host.now) { return .withheld(Words.noRecentUpdate) }
        return .unavailable(Words.inGameUnavailable)
    }

    /// A quoted value with the quote's own clock (or its unavailable words)
    /// and the one venue its contributors name, if exactly one.
    static func currentObservation(_ row: DuringPropRow, probability: Double,
                                   host: Host) -> PlayerContributionObservation10868 {
        let clock = row.current.observedAt?.asDate.map {
            "\(Words.recorded) \(BaseballGamePageAdapter10868.clockWords($0, host: host.page))"
        }
        let words = clock.map { [$0] } ?? [Words.recorded, Words.timeUnavailable]
        return PlayerContributionObservation10868(
            probability: probability, text: formatProbability(probability),
            accessibilityDetail: joined(words + [venue(row)]) ?? Words.recorded)
    }

    static func venue(_ row: DuringPropRow) -> String? {
        let labels = row.contributors.compactMap { SourceLabels.label(for: $0.source) }
        guard let first = labels.first, labels.allSatisfy({ $0 == first }) else { return nil }
        return first
    }

    // MARK: - Timing

    static func timingLines(_ milestone: PlayerContributionMilestone10868, stat: Stat) -> [String] {
        typealias T = PlayerContributionInput10868
        var lines = ["\(T.pregameTitle): \(milestone.before?.accessibilityDetail ?? milestone.beforeMissing)"]
        switch milestone.current {
        case .recorded(let observation, _): lines.append("\(T.recordedTitle): \(observation.accessibilityDetail)")
        case .unavailable(let words), .withheld(let words), .reached(let words):
            lines.append("\(T.currentStatusTitle): \(words)")
        }
        lines.append("\(T.countSoFarTitle): \(stat.countUnavailable)")
        return lines
    }

    // MARK: - The original

    /// One milestone's exact original. First what the card shows, then the
    /// recorded pregame reference, the raw contributor legs and the ids.
    static func original(_ row: DuringPropRow, milestone: PlayerContributionMilestone10868, name: String,
                         stat: Stat, eventID: Int, host: Host) -> MLBOriginal11284 {
        typealias Field = MLBOriginal11284.Field
        typealias Section = MLBOriginal11284.Section
        var sections = [cardReading(row, milestone: milestone, stat: stat, host: host)]

        // The same admission as the card's pregame chance; its own stamp.
        var reference = Words.unavailable
        if pregame(row, host: host) != nil, let baseline = row.comparison?.baseline,
           let probability = baseline.probability {
            reference = "\(formatProbability(probability)) · \(MLBOriginal11284.stamp(baseline.observedAt))"
        }
        sections.append(Section(title: nil, fields: [Field(label: Words.pinLabel, value: reference)]))

        let legs = row.contributors.map { contributor in
            Field(label: "\(SourceLabels.label(for: contributor.source) ?? "Venue") · \(contributor.outcomeName ?? "outcome")",
                  value: MLBOriginal11284.recorded(contributor.probability, at: contributor.observedAt)
                      ?? Words.unavailable)
        }
        if !legs.isEmpty { sections.append(Section(title: Words.sources, fields: legs)) }

        var ids: [Field] = []
        if let markets = MLBOriginal11284.idList(row._marketIds ?? row._marketId.map { [$0] }) {
            ids.append(Field(label: "Market", value: markets))
        }
        if let outcomes = MLBOriginal11284.idList(row.contributorOutcomeIds) {
            ids.append(Field(label: "Outcome", value: outcomes))
        }
        if !ids.isEmpty { sections.append(Section(title: nil, fields: ids)) }

        return MLBOriginal11284(id: "mlb-o:\(eventID):during:\(row.questionKey)",
                                title: "\(name) · \(milestone.title)", sections: sections)
    }

    /// The card's own reading of one milestone, in the order and words of its
    /// selected comparison: the pregame chance or its words, the current chance
    /// with its own clock (and the server's movement) or its words, and the
    /// count's words. A withheld stale quote keeps its last value and time.
    /// Already formatted strings are joined; nothing is read back from one.
    static func cardReading(_ row: DuringPropRow, milestone: PlayerContributionMilestone10868, stat: Stat,
                            host: Host) -> MLBOriginal11284.Section {
        typealias T = PlayerContributionInput10868
        typealias Field = MLBOriginal11284.Field
        var fields = [Field(label: T.pregameTitle,
                            value: milestone.before.map { reading($0) } ?? milestone.beforeMissing)]
        switch milestone.current {
        case .recorded(let observation, let movement):
            fields.append(Field(label: T.recordedTitle, value: reading(observation)))
            if let movement { fields.append(Field(label: T.spokenMovement, value: movement)) }
        case .withheld(let words):
            fields.append(Field(label: T.currentStatusTitle, value: words))
            if let last = row.current.quotedProbability {
                fields.append(Field(label: Words.lastRecorded,
                                    value: reading(currentObservation(row, probability: last, host: host))))
            }
        case .unavailable(let words), .reached(let words):
            fields.append(Field(label: T.currentStatusTitle, value: words))
        }
        fields.append(Field(label: T.countSoFarTitle, value: stat.countUnavailable))
        return MLBOriginal11284.Section(title: milestone.title, fields: fields)
    }

    /// The card's figure beside its own full clock and source.
    static func reading(_ observation: PlayerContributionObservation10868) -> String {
        joined([observation.text, observation.accessibilityDetail]) ?? observation.text
    }

    static func joined(_ parts: [String?]) -> String? {
        BaseballGamePageAdapter10868.joined(parts)
    }
}
