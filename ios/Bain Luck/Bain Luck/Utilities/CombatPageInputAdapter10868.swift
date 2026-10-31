import Foundation

/// #10868 — THE COMBAT EVENT SCREEN'S PRODUCTION ADAPTER, PART FIVE: THE WHOLE
/// PAGE INPUT AND ITS MANUAL STORY STREAM.
///
/// PILLARS: FORMATTING / DISCOVER. SHIP: on an MMA or boxing event page the two
/// fighters, the anchor history, whichever fight stories an owner has proved
/// and the All props entry arrive as one screen, and a reader moves between
/// the stories with Previous and Next.
///
/// It composes; it decides nothing the parts do not already decide:
///   - phase, headline, reader heading, About   part one (`CombatBoutPageAdapter10868`)
///   - history                                  part two (`CombatHistoryAdapter10868`), passed in
///   - method, rounds, knockout, duration       part three (`CombatStoryAdapter10868`), passed in
///   - originals count                          part four's catalogue size, for the All props entry
///
/// THE STREAM IS MANUAL, as the hockey screen's (`HockeyJourneyPageInputAdapter10868`).
/// The only owner that ranks and auto-advances story cards is NBA's
/// (`NBAStoryStreamPolicy9483`); combat has none, so this file offers no
/// playback or dwell, elects no "latest" card and runs no timer: the host's held
/// card is shown, Previous/Next name the other offered cards, and nothing moves
/// unless the reader asks. The approved context-ranked, automatically advancing
/// stream (the reference's `combatMomentOrder`) remains the stream owner's to
/// add (#9483) and is NOT completed here. No offered story: no stream at all.
enum CombatPageInputAdapter10868 {

    /// The host's own stream state — what the reader is looking at.
    struct StreamState: Equatable {
        /// The card the host holds; nil or no longer offered shows the first offered card.
        var displayed: CombatEventPageCard10868?
        /// The host's full reader is open, so the stream suppresses its requests.
        var readerOpen: Bool = false
        /// The host chose the wide presentation.
        var wide: Bool = false

        init(displayed: CombatEventPageCard10868? = nil, readerOpen: Bool = false, wide: Bool = false) {
            self.displayed = displayed
            self.readerOpen = readerOpen
            self.wide = wide
        }
    }

    enum Words {
        static let streamHeading = "Fight stories"
        static let companionLabel = "Next"
        static let manualStatus = "Use Previous or Next to see each story"
        static let storiesLabel = "Fight stories"
        static let storyUnavailable = "This story isn’t available for this fight state. Every original is still in All props."
        static let methodsName = "Finish method"
        static let roundsName = "Fighter rounds"
        static let knockoutName = "Knockout chances"
        static let durationName = "Fight length"
        static let historyName = "Win probability"
    }

    static func input(
        _ event: EventDetail,
        history: FieldHistoryInput10868,
        methods: CombatMethodInput10868?,
        rounds: CombatRoundInput10868?,
        knockout: CombatMethodInput10868?,
        duration: CombatDurationInput10868?,
        originalsCount: Int?,
        stream state: StreamState,
        host: CombatBoutPageAdapter10868.Host
    ) -> CombatEventPageInput10868 {
        let phase = CombatBoutPageAdapter10868.phase(event, now: host.now)
        let offered = offeredCards(methods: methods, rounds: rounds, knockout: knockout, duration: duration)
        return CombatEventPageInput10868(
            phase: phase,
            eventID: String(event.id),
            reader: CombatBoutPageAdapter10868.readerHeader(event, host: host),
            headline: CombatBoutPageAdapter10868.headline(event, host: host),
            notice: CombatBoutPageAdapter10868.notice(host: host),
            history: history,
            methods: methods,
            rounds: rounds,
            knockout: knockout,
            duration: duration,
            stream: stream(scope: scope(event, phase: phase), offered: offered, state: state),
            stories: stories(offered),
            about: CombatBoutPageAdapter10868.about(event, host: host),
            copy: copy(originalsCount: originalsCount))
    }

    /// One owner scope per event and phase, as the stream requires.
    static func scope(_ event: EventDetail, phase: CombatEventPagePhase10868) -> String {
        "combat:\(event.id):\(phase.rawValue)"
    }

    /// The stories this phase has content for, in the reference's fixed order:
    /// Finish method, Fighter rounds, Knockout chances, Fight length.
    static func offeredCards(methods: CombatMethodInput10868?, rounds: CombatRoundInput10868?,
                             knockout: CombatMethodInput10868?,
                             duration: CombatDurationInput10868?) -> [CombatEventPageCard10868] {
        var cards: [CombatEventPageCard10868] = []
        if methods != nil { cards.append(.methods) }
        if rounds != nil { cards.append(.rounds) }
        if knockout != nil { cards.append(.knockout) }
        if duration != nil { cards.append(.duration) }
        return cards
    }

    /// The manual stream over the offered cards; nil when none is offered.
    static func stream(scope: String, offered: [CombatEventPageCard10868],
                       state: StreamState) -> StoryStreamPresentation10868? {
        guard !offered.isEmpty else { return nil }
        func ref(_ card: CombatEventPageCard10868) -> StoryStreamPresentation10868.CardRef {
            .init(scope: scope, id: card.rawValue)
        }
        let shown = state.displayed.flatMap { offered.contains($0) ? $0 : nil } ?? offered.first
        let index = shown.flatMap { offered.firstIndex(of: $0) }
        let neighbour: CombatEventPageCard10868? = {
            guard let index, offered.count > 1 else { return nil }
            return offered[(index + 1) % offered.count]
        }()
        let previous: CombatEventPageCard10868? = {
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

    /// Each offered card id links to its own leaf. No reason words: no owner
    /// ranks combat stories, so none is invented.
    static func stories(_ offered: [CombatEventPageCard10868]) -> [CombatEventPageStory10868] {
        offered.map { CombatEventPageStory10868(cardID: $0.rawValue, card: $0) }
    }

    static func copy(originalsCount: Int?) -> CombatEventPageCopy10868 {
        let label: String? = originalsCount.flatMap { count in
            guard count > 0 else { return nil }
            return count == 1 ? "1 original prop" : "All \(count) original props"
        }
        return CombatEventPageCopy10868(storiesLabel: Words.storiesLabel, storyUnavailable: Words.storyUnavailable,
                                        headlineUnavailable: CombatBoutPageAdapter10868.Words.headlineUnavailable,
                                        allPropsLabel: label)
    }

    static func name(_ card: CombatEventPageCard10868) -> String {
        switch card {
        case .history: Words.historyName
        case .methods: Words.methodsName
        case .rounds: Words.roundsName
        case .knockout: Words.knockoutName
        case .duration: Words.durationName
        }
    }
}
