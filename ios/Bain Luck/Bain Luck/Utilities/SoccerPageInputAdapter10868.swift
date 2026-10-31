import Foundation

/// #10868 — THE SOCCER MATCH SCREEN'S PRODUCTION ADAPTER, PART NINE: THE WHOLE
/// PAGE INPUT AND ITS MANUAL STORY STREAM.
///
/// PILLARS: FORMATTING / DISCOVER. SHIP: on the soccer match screen the three
/// named outcomes, the history and every story the match has content for
/// arrive as one screen, and a reader moves between the stories with Previous
/// and Next.
///
/// It composes; it decides nothing the parts do not already decide:
///   - header, headline   part one (`SoccerMatchPageAdapter10868`)
///   - history            part two (`SoccerHistoryAdapter10868`), passed in
///   - goals, both, first, halves   parts four to seven, passed in
///   - originals count    part eight's catalogue size, for the All props entry
///
/// THE STREAM IS MANUAL, exactly as hockey's (H5): the only owner that ranks and
/// auto-advances story cards is NBA's (`NBAStoryStreamPolicy9483`). Soccer has
/// no such owner, so this file offers no playback control and no dwell, elects
/// no "latest" card and runs no timer: the host's held card is shown,
/// Previous/Next name the other offered cards, and nothing moves unless the
/// reader asks. Context-ranked, automatic advancement stays the stream owner's
/// to add (#9483) — an explicit unpaid obligation, not this file's.
enum SoccerPageInputAdapter10868 {

    /// The host's own stream state — what the reader is looking at.
    struct StreamState: Equatable {
        /// The card the host holds; nil or no longer offered shows the first offered card.
        var displayed: SoccerEventPageCard10868?
        /// The host's full reader is open, so the stream suppresses its requests.
        var readerOpen: Bool
        /// The host chose the wide presentation.
        var wide: Bool

        init(displayed: SoccerEventPageCard10868? = nil, readerOpen: Bool = false, wide: Bool = false) {
            self.displayed = displayed
            self.readerOpen = readerOpen
            self.wide = wide
        }
    }

    enum Words {
        static let streamHeading = "Explore the match"
        static let companionLabel = "Next"
        static let manualStatus = "Use Previous or Next to see each story"
        static let storiesLabel = "Match stories"
        static let storyUnavailable = "This story isn’t available for this match state. Every original is still in All props."
        static let goals = "Goal milestones"
        static let both = "Both teams to score"
        static let first = "First team to score"
        static let halves = "Half-by-half expectations"
        static let history = "Win probability"
        static let allProps = "All props"
    }

    static func input(
        _ event: EventDetail,
        history: FieldHistoryInput10868,
        goals: TotalMilestoneInput10868?,
        both: BothTeamsScoreInput10868?,
        first: FirstScorerComparisonInput10868?,
        halves: PeriodOutcomeComparisonInput10868?,
        originalsCount: Int?,
        stream state: StreamState,
        host: SoccerMatchPageAdapter10868.Host
    ) -> SoccerEventPageInput10868 {
        let phase = SoccerMatchPageAdapter10868.phase(event, now: host.now)
        let offered = offeredCards(goals: goals, both: both, first: first, halves: halves)
        return SoccerEventPageInput10868(
            phase: phase,
            header: SoccerMatchPageAdapter10868.header(event, host: host),
            headline: SoccerMatchPageAdapter10868.headline(event, host: host),
            history: history,
            goals: goals,
            both: both,
            first: first,
            halves: halves,
            stream: stream(scope: scope(event, phase: phase), offered: offered, state: state),
            stories: stories(offered),
            copy: copy(originalsCount: originalsCount))
    }

    /// One owner scope per event and phase, as the stream requires.
    static func scope(_ event: EventDetail, phase: SoccerEventPagePhase10868) -> String {
        "soccer:\(event.id):\(phase)"
    }

    /// The stories this phase has content for, in the screen's fixed order.
    static func offeredCards(goals: TotalMilestoneInput10868?, both: BothTeamsScoreInput10868?,
                             first: FirstScorerComparisonInput10868?,
                             halves: PeriodOutcomeComparisonInput10868?) -> [SoccerEventPageCard10868] {
        var cards: [SoccerEventPageCard10868] = []
        if goals != nil { cards.append(.goals) }
        if both != nil { cards.append(.both) }
        if first != nil { cards.append(.first) }
        if halves != nil { cards.append(.halves) }
        return cards
    }

    static func stream(scope: String, offered: [SoccerEventPageCard10868],
                       state: StreamState) -> StoryStreamPresentation10868 {
        func ref(_ card: SoccerEventPageCard10868) -> StoryStreamPresentation10868.CardRef {
            .init(scope: scope, id: card.rawValue)
        }
        let shown = state.displayed.flatMap { offered.contains($0) ? $0 : nil } ?? offered.first
        let index = shown.flatMap { offered.firstIndex(of: $0) }
        let neighbour: SoccerEventPageCard10868? = {
            guard let index, offered.count > 1 else { return nil }
            return offered[(index + 1) % offered.count]
        }()
        let previous: SoccerEventPageCard10868? = {
            guard let index, offered.count > 1 else { return nil }
            return offered[(index + offered.count - 1) % offered.count]
        }()
        return StoryStreamPresentation10868(
            scope: scope, eyebrow: nil, heading: Words.streamHeading,
            cards: offered.map { StoryStreamPresentation10868.Card(id: $0.rawValue, name: name($0)) },
            primary: shown.map(ref), companion: neighbour.map(ref),
            companionLabel: neighbour == nil ? nil : Words.companionLabel,
            wide: state.wide,
            position: index.map { "\($0 + 1) of \(offered.count)" },
            status: offered.count > 1 ? Words.manualStatus : nil,
            dwellFraction: nil, playback: nil,
            previous: previous.map(ref), next: neighbour.map(ref),
            readerOpen: state.readerOpen)
    }

    /// One link per offered card id, to the one typed card it shows.
    static func stories(_ offered: [SoccerEventPageCard10868]) -> [SoccerEventPageStory10868] {
        offered.map { SoccerEventPageStory10868(cardID: $0.rawValue, card: $0) }
    }

    static func copy(originalsCount: Int?) -> SoccerEventPageCopy10868 {
        let label: String? = originalsCount.flatMap { count in
            count > 0 ? "\(Words.allProps) · \(count)" : nil
        }
        return SoccerEventPageCopy10868(storiesLabel: Words.storiesLabel, storyUnavailable: Words.storyUnavailable,
                                        allPropsLabel: label)
    }

    static func name(_ card: SoccerEventPageCard10868) -> String {
        switch card {
        case .goals: Words.goals
        case .both: Words.both
        case .first: Words.first
        case .halves: Words.halves
        case .history: Words.history
        }
    }
}
