import SwiftUI

/// #10868 — THE CRICKET TEST-MATCH SCREEN'S PRODUCTION ADAPTER, PART FIVE: THE
/// WHOLE PAGE INPUT AND ITS MANUAL STORY STREAM.
///
/// PILLARS: FORMATTING / DISCOVER. SHIP: on `cricket-live` the title, the
/// three-original headline, the history, the stories production data can feed
/// and the original markets arrive as one screen from the bodies the event page
/// already holds; a reader moves between the stories with Previous and Next.
///
/// It composes; it decides nothing the parts do not already decide:
///   - phase, title, reader heading, headline, About  part one
///   - history                                        part two, passed in
///   - originals count                                part three's catalogue size
///   - Changing expectations, Expectations and result part four
///
/// THE STORY STREAM, BY PHASE (the reference's own offer):
///   - before play  no stream: the reference's before page is the title, the
///                  headline, the history and the originals only.
///   - during play  Changing expectations, when part four builds it. The chase
///                  and Holding on are never offered (part four's reasons).
///   - final        Expectations and result, when part four builds it. The
///                  resolved chase is never offered.
/// With no card to offer the stream is nil, so the page draws no stories group
/// rather than an empty one.
///
/// THE STREAM IS MANUAL. No owner ranks or auto-advances cricket stories; this
/// file offers no playback control and no dwell, elects no "latest" card and
/// runs no timer: the host's held card is shown, Previous/Next name the other
/// offered card, and nothing moves unless the reader asks. The approved ranked,
/// automatic stream stays the stream owner's obligation (#9483).
enum CricketPageInputAdapter10868 {
    typealias Page = CricketEventPageAdapter10868
    typealias Stories = CricketStoriesAdapter10868

    /// The host's own stream state — what the reader is looking at.
    struct StreamState: Equatable {
        /// The card the host holds; nil or no longer offered shows the first offered card.
        var displayed: CricketEventPageCard10868?
        /// The host's full reader is open, so the stream suppresses its requests.
        var readerOpen: Bool = false
        /// The host chose the wide presentation.
        var wide: Bool = false

        init(displayed: CricketEventPageCard10868? = nil, readerOpen: Bool = false, wide: Bool = false) {
            self.displayed = displayed
            self.readerOpen = readerOpen
            self.wide = wide
        }
    }

    enum Words {
        static let streamHeading = "Match stories"
        static let storiesLabel = "Match stories"
        static let companionLabel = "Next"
        static let manualStatus = "Use Previous or Next to see each story"
        static let storyUnavailable = "This story isn’t available for this match moment. Every original is still in All props."
        static let headlineUnavailable = "Match chances unavailable for this moment"
        static let shiftsName = "Changing expectations"
        static let expectationsName = "Expectations and result"
        static let chaseName = "The chase"
        static let survivalName = "Holding on"
        static let historyName = "Win probability"
        /// T20-format cards: named for exhaustiveness; this Test adapter
        /// never offers them.
        static let pregameName = "Pregame outlook"
        static let expectationShiftName = "Expectation shift"
    }

    static func input(_ event: EventDetail, history: CricketHistoryInput10868, originalsCount: Int?,
                      stream state: StreamState, host: Page.Host) -> CricketEventPageInput10868 {
        let phase = Page.phase(event, now: host.now)
        let headline = Page.headline(event, host: host)
        let shifts = Stories.shifts(headline)
        let expectations = Stories.expectations(headline)
        let offered = offeredCards(shifts: shifts, expectations: expectations)
        let tints = TeamTextContrast.cardColors(awayHex: event.awayTeamData?.primaryColor,
                                                homeHex: event.homeTeamData?.primaryColor)
        let stream: StoryStreamPresentation10868? = offered.isEmpty
            ? nil : Self.stream(scope: scope(event, phase: phase), offered: offered, state: state)
        return CricketEventPageInput10868(
            phase: phase,
            title: Page.title(event, host: host),
            reader: Page.readerHeader(event, host: host),
            headline: headline,
            secondaryProvenance: false,
            notice: nil,
            history: history,
            historyMarkers: nil,
            readerPlotHeight: nil,
            shifts: shifts,
            chase: nil,
            survival: nil,
            expectations: expectations,
            // Required by the screen; never drawn, because no chase or
            // Holding-on card is ever offered.
            runsTint: tints.home,
            wicketTint: DS.textSecondary,
            stream: stream,
            stories: stories(offered),
            about: Page.about(event, host: host),
            copy: copy(originalsCount: originalsCount))
    }

    /// One owner scope per event and phase, as the stream requires.
    static func scope(_ event: EventDetail, phase: CricketHeadlinePhase10868) -> String {
        "cricket:\(event.id):\(Page.phaseWord(phase))"
    }

    /// The stories this phase has content for, in the reference's order.
    static func offeredCards(shifts: CricketOutlookInput10868?,
                             expectations: CricketOutlookInput10868?) -> [CricketEventPageCard10868] {
        var cards: [CricketEventPageCard10868] = []
        if shifts != nil { cards.append(.shifts) }
        if expectations != nil { cards.append(.expectations) }
        return cards
    }

    static func stream(scope: String, offered: [CricketEventPageCard10868],
                       state: StreamState) -> StoryStreamPresentation10868 {
        func ref(_ card: CricketEventPageCard10868) -> StoryStreamPresentation10868.CardRef {
            .init(scope: scope, id: card.rawValue)
        }
        let shown = state.displayed.flatMap { offered.contains($0) ? $0 : nil } ?? offered.first
        let index = shown.flatMap { offered.firstIndex(of: $0) }
        var neighbour: CricketEventPageCard10868?
        var previous: CricketEventPageCard10868?
        if let index, offered.count > 1 {
            neighbour = offered[(index + 1) % offered.count]
            previous = offered[(index + offered.count - 1) % offered.count]
        }
        let cards = offered.map { StoryStreamPresentation10868.Card(id: $0.rawValue, name: name($0)) }
        return StoryStreamPresentation10868(
            scope: scope, eyebrow: nil, heading: Words.streamHeading,
            cards: cards,
            primary: shown.map(ref), companion: neighbour.map(ref),
            companionLabel: neighbour == nil ? nil : Words.companionLabel,
            wide: state.wide,
            position: index.map { "\($0 + 1) of \(offered.count)" },
            status: offered.count > 1 ? Words.manualStatus : nil,
            dwellFraction: nil, playback: nil,
            previous: previous.map(ref), next: neighbour.map(ref),
            readerOpen: state.readerOpen)
    }

    /// Each offered card id names exactly the story it shows.
    static func stories(_ offered: [CricketEventPageCard10868]) -> [CricketEventPageStory10868] {
        offered.map { CricketEventPageStory10868(cardID: $0.rawValue, card: $0) }
    }

    static func copy(originalsCount: Int?) -> CricketEventPageCopy10868 {
        let label: String? = originalsCount.flatMap { count in
            count > 0 ? CricketOriginalsAdapter10868.Words.heading(count) : nil
        }
        return CricketEventPageCopy10868(storiesLabel: Words.storiesLabel, storyUnavailable: Words.storyUnavailable,
                                         headlineUnavailable: Words.headlineUnavailable,
                                         aboutLabel: Page.Words.aboutLabel, allPropsLabel: label)
    }

    static func name(_ card: CricketEventPageCard10868) -> String {
        switch card {
        case .history: Words.historyName
        case .shifts: Words.shiftsName
        case .chase: Words.chaseName
        case .survival: Words.survivalName
        case .expectations: Words.expectationsName
        case .pregame: Words.pregameName
        case .expectationShift: Words.expectationShiftName
        }
    }
}
