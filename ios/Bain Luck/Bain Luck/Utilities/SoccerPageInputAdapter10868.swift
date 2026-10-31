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
///   - exact              part ten (`SoccerExactScoreAdapter10868`), passed in
///   - originals count    part eight's catalogue size, for the All props entry
///
/// THE STREAM IS MANUAL, exactly as hockey's (H5): the only owner that ranks and
/// auto-advances story cards is NBA's (`NBAStoryStreamPolicy9483`). Soccer has
/// no such owner, so this file offers no playback control and no dwell, elects
/// no "latest" card and runs no timer: the host's held card is shown,
/// Previous/Next name the other offered cards, and nothing moves unless the
/// reader asks. Context-ranked, automatic advancement stays the stream owner's
/// to add (#9483) — an explicit unpaid obligation, not this file's.
///
/// THE HALF-BY-HALF CARD FOLLOWS THE APPROVED ROUTE-PHASE MEMBERSHIP (Design,
/// wave-1 review 2026-10-31; route-tracker SOCCER-CARD-RECONCILIATION.json):
/// it is on the final, journey and replay routes and on neither the before nor
/// the live route. So by default (`HalvesAdmission.routeDefault`) it is offered
/// only after the final, whatever content the halves adapter has. The journey
/// and replay hosts — or any other owner-supplied context — admit it explicitly
/// (`.explicit`); nothing here ranks cards or infers a route.
///
/// EVERY CARD FOLLOWS THAT MEMBERSHIP BY DEFAULT (Design, SOCCER BEFORE
/// exact-map and goal-outlook reuse; `routeCards`):
///   - before kickoff   the total goal outlook and the full-match / first-half
///                      exact-score map — and nothing else. Both teams to score,
///                      first team to score and half by half are not automatic,
///                      whatever content their adapters have;
///   - during play      goal milestones, both teams to score, first team to score;
///   - after the final  those three and half by half.
/// The owner may admit any other card explicitly (`admittedCards`, or
/// `HalvesAdmission.explicit` for half by half) — owner-supplied context, never
/// a rank, a title or a time. A card that is offered still needs its own
/// content; a card that is not offered reaches neither the stream nor the page
/// input. Every original stays in All props either way. Filtering is not the
/// whole screen: the outlook and the map are composed by parts four and ten
/// from the event's own served rows and the owner's admission.
enum SoccerPageInputAdapter10868 {

    /// Where the half-by-half card may be offered.
    enum HalvesAdmission: Equatable {
        /// The approved route-phase membership: after the final only.
        case routeDefault
        /// The host explicitly admits it in this phase (the journey and replay
        /// routes, or other owner-supplied context).
        case explicit
    }

    /// Whether the half-by-half card is offered in `phase` under `admission`.
    static func offersHalves(phase: SoccerEventPagePhase10868, admission: HalvesAdmission) -> Bool {
        switch admission {
        case .routeDefault: phase == .final
        case .explicit: true
        }
    }

    /// The approved route-phase membership (route-tracker
    /// SOCCER-CARD-RECONCILIATION.json): the prop stories each phase offers
    /// without any owner admission.
    static func routeCards(_ phase: SoccerEventPagePhase10868) -> Set<SoccerEventPageCard10868> {
        switch phase {
        case .before: [.goals, .exact]
        case .live: [.goals, .both, .first]
        case .final: [.goals, .both, .first, .halves]
        }
    }

    /// Whether `card` is offered in `phase`: the route's own card, or one the
    /// owner admitted explicitly.
    static func offers(_ card: SoccerEventPageCard10868, phase: SoccerEventPagePhase10868,
                       admitted: Set<SoccerEventPageCard10868>) -> Bool {
        card != .history && (routeCards(phase).contains(card) || admitted.contains(card))
    }

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
        /// The goal card's name before kickoff, where it is the outlook.
        static let goalOutlook = "Total goal outlook"
        static let exact = "Exact final score"
        static let both = "Both teams to score"
        static let first = "First team to score"
        static let halves = "Half-by-half expectations"
        static let history = "Win probability"
        static let allProps = "All props"
    }

    /// `admittedCards` is the owner's explicit admission of cards beyond the
    /// route's own; `.explicit` half-by-half admission counts as one.
    static func input(
        _ event: EventDetail,
        history: FieldHistoryInput10868,
        goals suppliedGoals: TotalMilestoneInput10868?,
        both suppliedBoth: BothTeamsScoreInput10868?,
        first suppliedFirst: FirstScorerComparisonInput10868?,
        halves suppliedHalves: PeriodOutcomeComparisonInput10868?,
        exact suppliedExact: ExactScoreMapInput10868? = nil,
        halvesAdmission: HalvesAdmission = .routeDefault,
        admittedCards: Set<SoccerEventPageCard10868> = [],
        originalsCount: Int?,
        stream state: StreamState,
        host: SoccerMatchPageAdapter10868.Host
    ) -> SoccerEventPageInput10868 {
        let phase = SoccerMatchPageAdapter10868.phase(event, now: host.now)
        var admitted = admittedCards
        if halvesAdmission == .explicit { admitted.insert(.halves) }
        func offered<Input>(_ card: SoccerEventPageCard10868, _ input: Input?) -> Input? {
            offers(card, phase: phase, admitted: admitted) ? input : nil
        }
        let goals = offered(.goals, suppliedGoals)
        let exact = offered(.exact, suppliedExact)
        let both = offered(.both, suppliedBoth)
        let first = offered(.first, suppliedFirst)
        let halves = offered(.halves, suppliedHalves)
        let cards = offeredCards(goals: goals, exact: exact, both: both, first: first, halves: halves)
        return SoccerEventPageInput10868(
            phase: phase,
            header: SoccerMatchPageAdapter10868.header(event, host: host),
            headline: SoccerMatchPageAdapter10868.headline(event, host: host),
            history: history,
            goals: goals,
            both: both,
            first: first,
            halves: halves,
            exact: exact,
            stream: stream(scope: scope(event, phase: phase), offered: cards, state: state, phase: phase),
            stories: stories(cards),
            copy: copy(originalsCount: originalsCount))
    }

    /// One owner scope per event and phase, as the stream requires.
    static func scope(_ event: EventDetail, phase: SoccerEventPagePhase10868) -> String {
        "soccer:\(event.id):\(phase)"
    }

    /// The stories this phase has content for, in the screen's fixed order:
    /// goals, the exact-score map, both teams, first team, half by half.
    static func offeredCards(goals: TotalMilestoneInput10868?, exact: ExactScoreMapInput10868? = nil,
                             both: BothTeamsScoreInput10868?,
                             first: FirstScorerComparisonInput10868?,
                             halves: PeriodOutcomeComparisonInput10868?) -> [SoccerEventPageCard10868] {
        var cards: [SoccerEventPageCard10868] = []
        if goals != nil { cards.append(.goals) }
        if exact != nil { cards.append(.exact) }
        if both != nil { cards.append(.both) }
        if first != nil { cards.append(.first) }
        if halves != nil { cards.append(.halves) }
        return cards
    }

    static func stream(scope: String, offered: [SoccerEventPageCard10868],
                       state: StreamState, phase: SoccerEventPagePhase10868? = nil) -> StoryStreamPresentation10868 {
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
            cards: offered.map { StoryStreamPresentation10868.Card(id: $0.rawValue, name: name($0, phase: phase)) },
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
        case .exact: Words.exact
        case .history: Words.history
        }
    }

    /// The card's name in `phase`: before kickoff the goal card is the outlook.
    static func name(_ card: SoccerEventPageCard10868, phase: SoccerEventPagePhase10868?) -> String {
        card == .goals && phase == .before ? Words.goalOutlook : name(card)
    }
}
