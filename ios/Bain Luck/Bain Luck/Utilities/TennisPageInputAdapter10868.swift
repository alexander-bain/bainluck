import Foundation

/// #10868 — THE TENNIS MATCH SCREEN'S PRODUCTION ADAPTER, PART FIVE: THE WHOLE
/// PAGE INPUT AND ITS MANUAL STORY STREAM.
///
/// PILLARS: FORMATTING / DISCOVER. SHIP: on a tennis event page the two
/// players with the set score, the anchor history and its dated reading,
/// whichever match stories an owner has proved and the All props entry arrive
/// as one screen, and a reader moves between the stories with Previous and Next.
///
/// It composes; it decides nothing the parts do not already decide:
///   - phase, headline, reader heading, notice, About   part one (`TennisMatchPageAdapter10868`)
///   - history                                          part two (`TennisHistoryAdapter10868`), passed in
///   - dated reading                                    part three (`TennisReadingAdapter10868`), passed in
///   - originals count                                  part four's catalogue size, for All props
///   - sets, totals, exact, handicaps                   passed in, and NIL FROM PRODUCTION TODAY
///
/// THE FOUR STORY CARDS HAVE NO PRODUCTION OWNER YET. Each accepted leaf needs
/// words and membership no served field proves for tennis: the served matrix
/// (`game_question_matrix`, contract 10238.v1) types no tennis question —
/// `subject` and `predicate` null, the set-winner questions carry no `period`,
/// the total-games questions are `untyped_unit` — so which original is a set
/// winner, a games total, an exact set finish or a handicap, and the panel
/// predicate ("to win at least one set"), cannot be decided without parsing a
/// title, which this screen never does. During play the first-set card also
/// needs completed-set state and games within sets, and `EventDetail` does not
/// decode the served `linescore`. Owners: backend matrix typing
/// (`app/utils/event_question_matrix.py`) and Native's model (`EventDetail`
/// `linescore`). Until then the host passes nil, no story is offered, the stream
/// is absent, and every original stays reachable in All props.
///
/// THE STREAM IS MANUAL, as the hockey and combat screens'. The only owner that
/// ranks and auto-advances story cards is NBA's (`NBAStoryStreamPolicy9483`);
/// tennis has none, so this file offers no playback or dwell, elects no
/// "latest" card and runs no timer: the host's held card is shown,
/// Previous/Next name the other offered cards, and nothing moves unless the
/// reader asks. The approved ranked, automatically advancing stream remains the
/// stream owner's to add (#9483) and is NOT completed here.
enum TennisPageInputAdapter10868 {

    /// The host's own stream state — what the reader is looking at.
    struct StreamState: Equatable {
        /// The card the host holds; nil or no longer offered shows the first offered card.
        var displayed: TennisEventPageCard10868?
        /// The host's full reader is open, so the stream suppresses its requests.
        var readerOpen: Bool = false
        /// The host chose the wide presentation.
        var wide: Bool = false

        init(displayed: TennisEventPageCard10868? = nil, readerOpen: Bool = false, wide: Bool = false) {
            self.displayed = displayed
            self.readerOpen = readerOpen
            self.wide = wide
        }
    }

    enum Words {
        static let streamHeading = "Match stories"
        static let companionLabel = "Next"
        static let manualStatus = "Use Previous or Next to see each story"
        static let storiesLabel = "Match stories"
        static let storyUnavailable = "This story isn’t available for this match state. Every original is still in All props."
        static let historyName = "Win probability"
        static let setsFinalName = "Set winners"
        static let setsName = "First-set expectations"
        static let totalsFinalName = "Total games"
        static let totalsName = "Total-game milestones"
        static let exactName = "Exact set finishes"
        static let handicapsName = "Set and game handicaps"
    }

    static func input(
        _ event: EventDetail,
        history: FieldHistoryInput10868,
        reading: TennisEventPageReading10868?,
        sets: PeriodOutcomeFinalScoreInput10868? = nil,
        totals: TennisEventPageTotals10868? = nil,
        exact: TennisEventPageExact10868? = nil,
        handicaps: TennisEventPageHandicaps10868? = nil,
        originalsCount: Int?,
        stream state: StreamState,
        host: TennisMatchPageAdapter10868.Host
    ) -> TennisEventPageInput10868 {
        let phase = TennisMatchPageAdapter10868.phase(event, now: host.now)
        let offered = offeredCards(sets: sets, totals: totals, exact: exact, handicaps: handicaps)
        return TennisEventPageInput10868(
            phase: phase,
            eventID: String(event.id),
            reader: TennisMatchPageAdapter10868.readerHeader(event, host: host),
            headline: TennisMatchPageAdapter10868.headline(event, host: host),
            notice: TennisMatchPageAdapter10868.notice(host: host),
            history: history,
            reading: reading,
            sets: sets,
            totals: totals,
            exact: exact,
            handicaps: handicaps,
            stream: stream(scope: scope(event, phase: phase), offered: offered, phase: phase, state: state),
            stories: stories(offered),
            about: TennisMatchPageAdapter10868.about(event, host: host),
            copy: copy(originalsCount: originalsCount))
    }

    /// One owner scope per event and phase, as the stream requires.
    static func scope(_ event: EventDetail, phase: TennisEventPagePhase10868) -> String {
        "tennis:\(event.id):\(phase.rawValue)"
    }

    /// The stories this phase has content for, in the approved order: sets,
    /// totals, exact set finishes, handicaps.
    static func offeredCards(sets: PeriodOutcomeFinalScoreInput10868?, totals: TennisEventPageTotals10868?,
                             exact: TennisEventPageExact10868?,
                             handicaps: TennisEventPageHandicaps10868?) -> [TennisEventPageCard10868] {
        var cards: [TennisEventPageCard10868] = []
        if sets != nil { cards.append(.sets) }
        if totals != nil { cards.append(.totals) }
        if exact != nil { cards.append(.exact) }
        if handicaps != nil { cards.append(.handicaps) }
        return cards
    }

    /// The manual stream over the offered cards; nil when none is offered.
    static func stream(scope: String, offered: [TennisEventPageCard10868], phase: TennisEventPagePhase10868,
                       state: StreamState) -> StoryStreamPresentation10868? {
        guard !offered.isEmpty else { return nil }
        func ref(_ card: TennisEventPageCard10868) -> StoryStreamPresentation10868.CardRef {
            .init(scope: scope, id: card.rawValue)
        }
        let shown = state.displayed.flatMap { offered.contains($0) ? $0 : nil } ?? offered.first
        let index = shown.flatMap { offered.firstIndex(of: $0) }
        let neighbour: TennisEventPageCard10868? = {
            guard let index, offered.count > 1 else { return nil }
            return offered[(index + 1) % offered.count]
        }()
        let previous: TennisEventPageCard10868? = {
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

    /// Each offered card id links to its own leaf. No reason words: no owner
    /// ranks tennis stories, so none is invented.
    static func stories(_ offered: [TennisEventPageCard10868]) -> [TennisEventPageStory10868] {
        offered.map { TennisEventPageStory10868(cardID: $0.rawValue, card: $0) }
    }

    static func copy(originalsCount: Int?) -> TennisEventPageCopy10868 {
        let label: String? = originalsCount.flatMap { count in
            guard count > 0 else { return nil }
            return count == 1 ? "1 original prop" : "All \(count) original props"
        }
        return TennisEventPageCopy10868(storiesLabel: Words.storiesLabel, storyUnavailable: Words.storyUnavailable,
                                        headlineUnavailable: TennisMatchPageAdapter10868.Words.headlineUnavailable,
                                        allPropsLabel: label)
    }

    static func name(_ card: TennisEventPageCard10868, phase: TennisEventPagePhase10868) -> String {
        switch card {
        case .history: Words.historyName
        case .sets: phase == .final ? Words.setsFinalName : Words.setsName
        case .totals: phase == .final ? Words.totalsFinalName : Words.totalsName
        case .exact: Words.exactName
        case .handicaps: Words.handicapsName
        }
    }
}
