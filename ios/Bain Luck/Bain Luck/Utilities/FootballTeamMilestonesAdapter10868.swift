import Foundation

/// #10868 — THE FOOTBALL SCREEN'S PRODUCTION ADAPTER, PART THREE: TEAM SACKS AND
/// TEAM FIELD GOALS, PAIRED.
///
/// PILLARS: FORMATTING / TRUTH. SHIP: on `nfl-team-stats` (and the routes that
/// carry team milestones) both teams' own chances at the same sack or
/// field-goal milestone sit in one chart — each team's earlier chance from its
/// own contract, its own in-game reading during play, and its own contract
/// result after the final — and no exact count is ever inferred.
///
/// It feeds `PairedMilestonePresentation10868` (ab5c5d35) from `/game-markets`'
/// player props, and decides nothing the event page does not already decide:
///
///   - which rows      the venue's own stat words, read as the props card reads
///                     them (`PlayerPropsStatLabel.display` + `PlayerPropsFamily.name`):
///                     "Team Sacks" or "Team Field Goals"; a team subject
///                     (`PlayerPropsFamily.isTeamSubject`, the rule
///                     `NFLMilestoneCard9483.cards` drops team subjects by); an
///                     over-side line (`QuestionCatalog9483.lineSide`, gotcha #17)
///                     whose outcome reads exactly "Subject: N+" for its own
///                     threshold (`PlayerPropsFamily.targetLabel`).
///   - the pair        ONE served venue market — the same served market id and
///                     market words, as the approved `TeamMilestonesStory` reads
///                     one market — holding exactly two subjects. The fullest such
///                     market is used (then its words, then its venue: H3's ladder
///                     tie-break). Each side is named by the venue's own subject
///                     words, in served order; nothing joins a subject to the
///                     event's clubs, and a market with any other number of
///                     subjects draws no card.
///   - milestones      one group per served threshold, ascending; each side's
///                     slot is its OWN row at that threshold or the owner's
///                     missing words — never its sibling's, never a neighbour's.
///   - pregame chance  H3's `pregameReading` (`NFLMilestoneCard9483.cards`' two
///                     bases: the recent quote before the start, the served
///                     `pregame_mark` once started), and H3's flat-ladder
///                     refusal (#5137) per side.
///   - in-game         during play only, H3's `inGameReading` on the row's own
///                     clock. There is no team count channel, so "reached so far"
///                     is never claimed.
///   - result          after the final only, H3's `contractResult` (served
///                     settlement, refused when the served `hit` disagrees).
///                     Unknown is not loss.
///   - counts          none is served for a team stat: the count slots keep
///                     H3's absence words, never a count read off a grade.
///
/// The selection is the host's exact group id; with none, nothing is selected
/// (no default is elected here). Nothing fetches, subscribes or schedules.
enum FootballTeamMilestonesAdapter10868 {
    typealias H3 = HockeyJourneyContributionAdapter10868

    /// The two team-stat stories.
    enum Stat: Equatable, CaseIterable {
        case sacks
        case fieldGoals

        /// The venue's stat words after the matchup.
        var statWords: String { self == .sacks ? "Team Sacks" : "Team Field Goals" }
        var card: FootballEventPageCard10868 { self == .sacks ? .teamSacks : .teamFieldGoals }
        /// Sacks keep horizontal bars; field goals vertical columns.
        var orientation: PlayerContributionOrientation10868 { self == .sacks ? .bars : .columns }
        var unit: String { self == .sacks ? "sacks" : "field goals" }
        var eyebrow: String { self == .sacks ? "TEAM SACKS" : "TEAM FIELD GOALS" }
        /// The card names. Field goals keep the approved reference's words
        /// (`teamMilestoneDefinitions`); its sacks title names the passer by a
        /// word the period-label guard reads as a period noun
        /// (`periodLabelSingleSource`), so the sacks card says it plainly.
        var title: String { self == .sacks ? "Pressure on the passer" : "The kicking game" }
        var cardID: String { self == .sacks ? "teamSacks" : "teamFieldGoals" }
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

        /// H3's host: no per-player box applies to a team stat.
        var contribution: H3.Host {
            H3.Host(boxScore: nil, now: now, calendar: calendar, locale: locale)
        }
    }

    enum Words {
        static let definition = "Each team’s chance belongs to its own contract. These two chances do not add to 100%."
        static let chartTitle = "Pregame chances · at least this many"
        static let noOriginal = "No original for this milestone"
    }

    // MARK: - The card

    /// The card, or nil when no single served market pairs exactly two subjects.
    static func input(_ stat: Stat, event: EventDetail, markets: GameMarketsResponse?, host: Host,
                      selectedGroupID: String? = nil) -> PairedMilestoneInput10868? {
        guard let rows = market(stat, event: event, markets: markets) else { return nil }
        let subjects = subjectOrder(rows)
        guard subjects.count == 2 else { return nil }
        let phase = FootballEventPageAdapter10868.phase(event, now: host.now)
        let started = H3.hasStarted(event, now: host.now)
        let first = ladder(rows, subject: subjects[0])
        let second = ladder(rows, subject: subjects[1])
        let firstPregame = pregame(first, started: started, host: host)
        let secondPregame = pregame(second, started: started, host: host)

        let thresholds = Array(Set((first + second).compactMap(\.threshold))).sorted()
        let groups = thresholds.map { threshold -> PairedMilestoneGroup10868 in
            let target = PlayerPropsFamily.targetLabel(threshold)
            return PairedMilestoneGroup10868(
                id: groupID(stat, target: target), target: target, title: "\(target) \(stat.unit)",
                first: entry(first, firstPregame, subject: subjects[0], threshold: threshold, stat: stat,
                             phase: phase, event: event, host: host),
                second: entry(second, secondPregame, subject: subjects[1], threshold: threshold, stat: stat,
                              phase: phase, event: event, host: host))
        }
        return PairedMilestoneInput10868(
            phase: phase.contributionPhase,
            orientation: stat.orientation,
            cardID: stat.cardID,
            eyebrow: stat.eyebrow,
            title: stat.title,
            definition: Words.definition,
            first: subject(subjects[0], phase: phase),
            second: subject(subjects[1], phase: phase),
            groups: groups,
            selectedGroupID: selectedGroupID,
            chartTitle: Words.chartTitle,
            ticks: H3.ticks)
    }

    static func groupID(_ stat: Stat, target: String) -> String {
        "\(stat.cardID):\(target)"
    }

    // MARK: - The served market

    private struct Market {
        let name: String
        let source: String
        var rows: [GameMarketPlayerProp]
    }

    /// The rows of the one served market this card reads, in served order —
    /// from this event's own markets only (`FootballInputIdentityAdapter10868`):
    /// another game's markets, however plausible their clubs, draw no card.
    static func market(_ stat: Stat, event: EventDetail, markets: GameMarketsResponse?) -> [GameMarketPlayerProp]? {
        guard let markets = FootballInputIdentityAdapter10868.markets(markets, for: event) else { return nil }
        var order: [String] = []
        var groups: [String: Market] = [:]
        for prop in markets.playerProps ?? [] {
            guard let subject = H3.subject(prop),
                  PlayerPropsFamily.isTeamSubject(subject, teams: [event.homeTeam, event.awayTeam]),
                  isStat(stat, prop, subject: subject, event: event),
                  let threshold = prop.threshold, threshold.isFinite,
                  QuestionCatalog9483.lineSide(QuestionCatalog9483.row(prop)) == .over,
                  namesOwnTarget(prop, threshold: threshold)
            else { continue }
            let name = prop.marketName.trimmingCharacters(in: .whitespaces)
            let source = H3.venueKey(prop)
            let id = prop._marketId.map(String.init) ?? name
            let key = [source, id, name].joined(separator: "\u{1F}")
            if groups[key] == nil {
                order.append(key)
                groups[key] = Market(name: name, source: source, rows: [])
            }
            groups[key]?.rows.append(prop)
        }
        var best: Market?
        for key in order {
            guard let market = groups[key] else { continue }
            guard let held = best else {
                best = market
                continue
            }
            if (market.rows.count, held.name, held.source) > (held.rows.count, market.name, market.source) {
                best = market
            }
        }
        return best?.rows
    }

    static func isStat(_ stat: Stat, _ prop: GameMarketPlayerProp, subject: String, event: EventDetail) -> Bool {
        let label = PlayerPropsStatLabel.display(marketName: prop.marketName, homeTeam: event.homeTeam,
                                                 awayTeam: event.awayTeam, player: subject)
        return PlayerPropsFamily.name(statLabel: label).caseInsensitiveCompare(stat.statWords) == .orderedSame
    }

    /// The outcome after its colon is exactly the threshold's own target words.
    static func namesOwnTarget(_ prop: GameMarketPlayerProp, threshold: Double) -> Bool {
        let parts = prop.outcomeName.split(separator: ":", maxSplits: 1)
        guard parts.count == 2 else { return false }
        return parts[1].trimmingCharacters(in: .whitespaces) == PlayerPropsFamily.targetLabel(threshold)
    }

    /// Distinct subjects, in the order the venue served them.
    static func subjectOrder(_ rows: [GameMarketPlayerProp]) -> [String] {
        var seen: [String] = []
        for row in rows {
            guard let subject = H3.subject(row), !seen.contains(subject) else { continue }
            seen.append(subject)
        }
        return seen
    }

    /// One subject's rows, ascending; a second row at one threshold is a
    /// duplicate, never a second chance.
    static func ladder(_ rows: [GameMarketPlayerProp], subject: String) -> [GameMarketPlayerProp] {
        var kept: [GameMarketPlayerProp] = []
        for row in rows where H3.subject(row) == subject {
            guard !kept.contains(where: { $0.threshold == row.threshold }) else { continue }
            kept.append(row)
        }
        return kept.sorted { ($0.threshold ?? 0) < ($1.threshold ?? 0) }
    }

    // MARK: - Slots

    /// Each row's pregame reading, with H3's flat-ladder refusal (#5137).
    static func pregame(_ ladder: [GameMarketPlayerProp], started: Bool, host: Host) -> [H3.PregameReading] {
        let readings = ladder.map { H3.pregameReading($0, started: started, host: host.contribution) }
        let printed = readings.compactMap { $0.observation?.probability }
        guard PlayerPropsPricing.isPricedLadder(printed) else {
            return readings.map { _ in H3.PregameReading(observation: nil, missing: H3.Words.notPriced) }
        }
        return readings
    }

    static func entry(_ ladder: [GameMarketPlayerProp], _ pregame: [H3.PregameReading], subject: String,
                      threshold: Double, stat: Stat, phase: FootballEventPagePhase10868, event: EventDetail,
                      host: Host) -> PairedMilestoneEntry10868 {
        guard let index = ladder.firstIndex(where: { $0.threshold == threshold }) else {
            return .missing(Words.noOriginal)
        }
        let row = ladder[index]
        let before = pregame[index]
        let current: PlayerContributionCurrent10868 = phase == .live
            ? H3.inGameReading(row, reachedSoFar: false, event: event, host: host.contribution)
            : .unavailable(H3.Words.noInGameReading)
        let result: PlayerContributionResult10868 = phase == .final
            ? H3.contractResult(row, count: nil, threshold: threshold)
            : .unconfirmed(H3.Words.unconfirmed)
        return .original(PairedMilestoneOriginal10868(
            id: H3.milestoneID(row),
            title: "\(subject) \(PlayerPropsFamily.targetLabel(threshold)) \(stat.unit)",
            before: before.observation, beforeMissing: before.missing,
            current: current, result: result))
    }

    /// A side, named in the venue's own words; no team count is served.
    static func subject(_ name: String, phase: FootballEventPagePhase10868) -> PairedMilestoneSubject10868 {
        PairedMilestoneSubject10868(
            id: "subject:" + PlayerPropsCardView.normalizedPlayerName(name), name: name, detail: nil,
            countSoFar: nil, finalCount: nil,
            countMissing: phase == .final ? H3.Words.finalCountUnavailable : H3.Words.countUnavailable)
    }
}
