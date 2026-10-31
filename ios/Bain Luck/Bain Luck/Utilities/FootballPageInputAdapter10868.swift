import Foundation

/// #10868 — THE FOOTBALL SCREEN'S PRODUCTION ADAPTER, PART SEVEN: THE WHOLE PAGE
/// INPUT AND ITS MANUAL STORY STREAM.
///
/// PILLARS: FORMATTING / DISCOVER. SHIP: on every NFL route the comparison,
/// history and the route's own stories arrive as one screen, and a reader moves
/// between the stories with Previous and Next.
///
/// It composes; it decides nothing the parts do not already decide:
///   - phase, teams, header, headline   part one (`FootballEventPageAdapter10868`)
///   - history                          part five, passed in
///   - deck                             part two (the production deck), passed in
///   - team sacks / field goals         part three, passed in
///   - combined yards                   part four, passed in
///   - period winners                   `FootballPeriodWinnersAdapter10868`, passed in
///                                      (completed `nfl-live` only, by the route set)
///   - originals count                  part six's catalogue size, for All props
///   - which stories                    `FootballRouteCardSet10868` for the route,
///                                      and the screen's own mount rules
///                                      (`FootballEventPageModel10868.isMounted`),
///                                      so the stream never offers a card the page
///                                      would show as unavailable.
///
/// THE STREAM IS MANUAL. The only owner that ranks and auto-advances story cards
/// is NBA's (`NBAStoryStreamPolicy9483`); football has none, so this file offers
/// no playback control and no dwell, elects no "latest" card and runs no timer:
/// the host's held card is shown, Previous/Next name its neighbours in the
/// screen's fixed order (the projected finish, the final period winners, the
/// player milestones, team milestones, then combined yards — the deck's own
/// order with the period card directly before the players, as the approved
/// completed page mounts it), and nothing moves unless the reader asks.
/// Ranking stays the stream owner's (#9483).
enum FootballPageInputAdapter10868 {

    /// The host's own stream state — what the reader is looking at.
    struct StreamState: Equatable {
        /// The card the host holds; nil or no longer offered shows the first offered card.
        var displayed: FootballEventPageCard10868?
        var readerOpen: Bool = false
        var wide: Bool = false

        init(displayed: FootballEventPageCard10868? = nil, readerOpen: Bool = false, wide: Bool = false) {
            self.displayed = displayed
            self.readerOpen = readerOpen
            self.wide = wide
        }
    }

    enum Words {
        static let streamHeading = "Expectations and performance"
        static let companionLabel = "Next"
        static let manualStatus = "Use Previous or Next to see each story"
        static let storiesLabel = "Game stories"
        static let storyUnavailable = "This story isn’t available for this game state. Every original is still in All props."
    }

    static func input(
        _ event: EventDetail,
        route: FootballRoute10868,
        history: FieldHistoryInput10868,
        deck: [NFLEventCard9483],
        teamSacks: PairedMilestoneInput10868?,
        teamFieldGoals: PairedMilestoneInput10868?,
        combined: [FootballCombinedStory10868],
        periodWinners: FootballPeriodWinnersInput10868? = nil,
        originalsCount: Int?,
        stream state: StreamState,
        host: FootballEventPageAdapter10868.Host
    ) -> FootballEventPageInput10868 {
        let phase = FootballEventPageAdapter10868.phase(event, now: host.now)
        let scope = scope(event, phase: phase)
        // Every part but the stream; the screen's own model then says which
        // candidate stories it would mount.
        func page(stream: StoryStreamPresentation10868, stories: [FootballEventPageStory10868])
            -> FootballEventPageInput10868 {
            FootballEventPageInput10868(
                route: route, phase: phase,
                teams: FootballEventPageAdapter10868.teams(event),
                header: FootballEventPageAdapter10868.header(event, phase: phase, host: host),
                headline: FootballEventPageAdapter10868.headline(event, host: host),
                history: history, deck: deck, teamSacks: teamSacks, teamFieldGoals: teamFieldGoals,
                combined: combined, stream: stream, stories: stories,
                copy: copy(originalsCount: originalsCount), periodWinners: periodWinners)
        }
        let candidates = candidateCards(deck: deck, teamSacks: teamSacks, teamFieldGoals: teamFieldGoals,
                                        combined: combined, periodWinners: periodWinners)
        let draft = FootballEventPageModel10868(page(
            stream: StoryStreamPresentation10868(scope: scope, heading: Words.streamHeading, cards: []),
            stories: []))
        let offered = candidates.filter { draft.isMounted($0) }
        let names = Dictionary(offered.map { ($0, name($0, deck: deck, teamSacks: teamSacks,
                                                       teamFieldGoals: teamFieldGoals, combined: combined,
                                                       periodWinners: periodWinners)) },
                               uniquingKeysWith: { first, _ in first })
        return page(stream: stream(scope: scope, offered: offered, names: names, state: state),
                    stories: offered.map { FootballEventPageStory10868(cardID: $0.key, card: $0) })
    }

    /// One owner scope per event and phase, as the stream requires.
    static func scope(_ event: EventDetail, phase: FootballEventPagePhase10868) -> String {
        "nfl:\(event.id):\(phase)"
    }

    /// Every card the parts supplied, in the screen's fixed order.
    static func candidateCards(deck: [NFLEventCard9483], teamSacks: PairedMilestoneInput10868?,
                               teamFieldGoals: PairedMilestoneInput10868?,
                               combined: [FootballCombinedStory10868],
                               periodWinners: FootballPeriodWinnersInput10868? = nil) -> [FootballEventPageCard10868] {
        var cards: [FootballEventPageCard10868] = []
        if FootballDeckAdapter10868.finishCard(deck) != nil { cards.append(.finish) }
        if periodWinners != nil { cards.append(.periodWinners) }
        cards += FootballDeckAdapter10868.milestoneCards(deck).map { .milestone($0.id) }
        if teamSacks != nil { cards.append(.teamSacks) }
        if teamFieldGoals != nil { cards.append(.teamFieldGoals) }
        cards += combined.map { .combined($0.card.id) }
        return cards
    }

    static func stream(scope: String, offered: [FootballEventPageCard10868],
                       names: [FootballEventPageCard10868: String],
                       state: StreamState) -> StoryStreamPresentation10868 {
        func ref(_ card: FootballEventPageCard10868) -> StoryStreamPresentation10868.CardRef {
            .init(scope: scope, id: card.key)
        }
        let shown = state.displayed.flatMap { offered.contains($0) ? $0 : nil } ?? offered.first
        let index = shown.flatMap { offered.firstIndex(of: $0) }
        let neighbour: FootballEventPageCard10868? = {
            guard let index, offered.count > 1 else { return nil }
            return offered[(index + 1) % offered.count]
        }()
        let previous: FootballEventPageCard10868? = {
            guard let index, offered.count > 1 else { return nil }
            return offered[(index + offered.count - 1) % offered.count]
        }()
        return StoryStreamPresentation10868(
            scope: scope, eyebrow: nil, heading: Words.streamHeading,
            cards: offered.map { StoryStreamPresentation10868.Card(id: $0.key, name: names[$0] ?? $0.key) },
            primary: shown.map(ref), companion: neighbour.map(ref),
            companionLabel: neighbour == nil ? nil : Words.companionLabel,
            wide: state.wide,
            position: index.map { "\($0 + 1) of \(offered.count)" },
            status: offered.count > 1 ? Words.manualStatus : nil,
            dwellFraction: nil, playback: nil,
            previous: previous.map(ref), next: neighbour.map(ref),
            readerOpen: state.readerOpen)
    }

    /// Each card's full name, in its own owner's words.
    static func name(_ card: FootballEventPageCard10868, deck: [NFLEventCard9483],
                     teamSacks: PairedMilestoneInput10868?, teamFieldGoals: PairedMilestoneInput10868?,
                     combined: [FootballCombinedStory10868],
                     periodWinners: FootballPeriodWinnersInput10868? = nil) -> String {
        switch card {
        case .history:
            return HockeyJourneyHistoryAdapter10868.Words.title
        case .finish:
            return FootballDeckAdapter10868.finishCard(deck)?.kicker ?? card.key
        case .milestone(let id):
            let milestone = FootballDeckAdapter10868.milestoneCards(deck).first { $0.id == id }
            return milestone.map { NFLEventCard9483.milestone($0).title } ?? card.key
        case .teamSacks:
            return teamSacks?.title ?? card.key
        case .teamFieldGoals:
            return teamFieldGoals?.title ?? card.key
        case .combined(let id):
            let story = combined.first { $0.card.id == id }
            return story.map { NFLEventCard9483.milestone($0.card).title } ?? card.key
        case .periodWinners:
            return periodWinners?.words.title ?? card.key
        }
    }

    static func copy(originalsCount: Int?) -> FootballEventPageCopy10868 {
        let label: String? = originalsCount.flatMap { count in
            guard count > 0 else { return nil }
            return count == 1 ? "1 original outcome" : "All \(count) original outcomes"
        }
        return FootballEventPageCopy10868(
            storiesLabel: Words.storiesLabel, storyUnavailable: Words.storyUnavailable,
            headlineUnavailable: FootballEventPageAdapter10868.Words.headlineUnavailable,
            allPropsLabel: label)
    }
}
