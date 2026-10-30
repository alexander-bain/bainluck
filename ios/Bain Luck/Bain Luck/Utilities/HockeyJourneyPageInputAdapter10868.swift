import Foundation

/// #10868 — THE HOCKEY JOURNEY SCREEN'S PRODUCTION ADAPTER, PART FIVE: THE
/// WHOLE PAGE INPUT AND ITS MANUAL STORY STREAM.
///
/// PILLARS: FORMATTING / DISCOVER. SHIP: on `nhl-journey` the matrix, history
/// and the points and assists stories arrive as one screen, and a reader moves
/// between the stories with Previous and Next.
///
/// It composes; it decides nothing the parts do not already decide:
///   - headline, header  part one (`HockeyJourneyPageAdapter10868`)
///   - history           part two (`HockeyJourneyHistoryAdapter10868`), passed in
///   - points, assists   part three (`HockeyJourneyContributionAdapter10868`), passed in
///   - originals count   part four's catalogue size, for the All props entry
///
/// THE STREAM IS MANUAL. The only owner that ranks and auto-advances story
/// cards is NBA's (`NBAStoryStreamPolicy9483`, ranked on NBA ladders, with its
/// own dwell in `NBAStoryStreamView9483`). Hockey has no such owner, so this
/// file offers no playback control and no dwell, elects no "latest" card and
/// runs no timer: the host's held card is shown, Previous/Next name the other
/// offered card, and nothing moves unless the reader asks. Automatic ranking
/// for hockey is the stream owner's to add (#9483), not this file's.
enum HockeyJourneyPageInputAdapter10868 {

    /// The host's own stream state — what the reader is looking at.
    struct StreamState: Equatable {
        /// The card the host holds; nil or no longer offered shows the first offered card.
        var displayed: HockeyJourneyPageCard10868?
        /// The host's full reader is open, so the stream suppresses its requests.
        var readerOpen: Bool = false
        /// The host chose the wide presentation.
        var wide: Bool = false

        init(displayed: HockeyJourneyPageCard10868? = nil, readerOpen: Bool = false, wide: Bool = false) {
            self.displayed = displayed
            self.readerOpen = readerOpen
            self.wide = wide
        }
    }

    enum Words {
        static let streamHeading = "Expectations and performance"
        static let companionLabel = "Next"
        static let manualStatus = "Use Previous or Next to see each story"
        static let pointsName = "Points in context"
        static let assistsName = "Who creates the goals?"
        static let explorePoints = "Explore points"
        static let exploreAssists = "Explore assists"
        static let storiesLabel = "Game stories"
        static let storyUnavailable = "This story isn’t available for this game state. Every original is still in All props."
        static let matrixUnavailable = "Comparison unavailable for this game state"
    }

    static func input(
        _ event: EventDetail,
        history: FieldHistoryInput10868,
        points: PlayerContributionInput10868?,
        assists: PlayerContributionInput10868?,
        originalsCount: Int?,
        stream state: StreamState,
        host: HockeyJourneyPageAdapter10868.Host
    ) -> HockeyJourneyPageInput10868 {
        let phase = HockeyJourneyPageAdapter10868.phase(event, now: host.now)
        let offered = offeredCards(points: points, assists: assists)
        return HockeyJourneyPageInput10868(
            phase: phase,
            header: HockeyJourneyPageAdapter10868.header(event, phase: phase),
            headline: HockeyJourneyPageAdapter10868.headline(event, host: host),
            history: history,
            points: points,
            assists: assists,
            stream: stream(scope: scope(event, phase: phase), offered: offered, state: state),
            stories: stories(offered),
            copy: copy(originalsCount: originalsCount))
    }

    /// One owner scope per event and phase, as the stream requires.
    static func scope(_ event: EventDetail, phase: HockeyJourneyPagePhase10868) -> String {
        "nhl:\(event.id):\(phase)"
    }

    /// The stories this phase has content for, in the screen's fixed order.
    static func offeredCards(points: PlayerContributionInput10868?,
                             assists: PlayerContributionInput10868?) -> [HockeyJourneyPageCard10868] {
        var cards: [HockeyJourneyPageCard10868] = []
        if points != nil { cards.append(.points) }
        if assists != nil { cards.append(.assists) }
        return cards
    }

    static func stream(scope: String, offered: [HockeyJourneyPageCard10868],
                       state: StreamState) -> StoryStreamPresentation10868 {
        func ref(_ card: HockeyJourneyPageCard10868) -> StoryStreamPresentation10868.CardRef {
            .init(scope: scope, id: card.rawValue)
        }
        let shown = state.displayed.flatMap { offered.contains($0) ? $0 : nil } ?? offered.first
        let index = shown.flatMap { offered.firstIndex(of: $0) }
        let neighbour: HockeyJourneyPageCard10868? = {
            guard let index, offered.count > 1 else { return nil }
            return offered[(index + 1) % offered.count]
        }()
        let previous: HockeyJourneyPageCard10868? = {
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

    static func stories(_ offered: [HockeyJourneyPageCard10868]) -> [HockeyJourneyPageStory10868] {
        offered.map { card in
            HockeyJourneyPageStory10868(cardID: card.rawValue, card: card,
                                        exploreLabel: card == .points ? Words.explorePoints : Words.exploreAssists)
        }
    }

    static func copy(originalsCount: Int?) -> HockeyJourneyPageCopy10868 {
        let label: String? = originalsCount.flatMap { count in
            guard count > 0 else { return nil }
            return count == 1 ? "1 original outcome" : "All \(count) original outcomes"
        }
        return HockeyJourneyPageCopy10868(storiesLabel: Words.storiesLabel, storyUnavailable: Words.storyUnavailable,
                                          matrixUnavailable: Words.matrixUnavailable, allPropsLabel: label)
    }

    private static func name(_ card: HockeyJourneyPageCard10868) -> String {
        switch card {
        case .points: Words.pointsName
        case .assists: Words.assistsName
        case .history: "Win probability"
        }
    }
}
