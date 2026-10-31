import Foundation

/// #10868 — THE FIELD SCREEN'S PRODUCTION ADAPTER, PART FIVE: THE WHOLE PAGE
/// INPUT AND ITS MANUAL STORY STREAM.
///
/// PILLARS: FORMATTING / DISCOVER. SHIP: on a championship field page the
/// named-chance headline, the contenders' win history, the field and movement
/// stories and "All props" arrive as one screen from the market the page
/// already holds, and a story the app cannot feed truthfully is absent — never
/// a card filled with invented tournament data.
///
/// It composes; it decides nothing the parts do not already decide:
///   - phase, headline, reader heading, About   part one (`FieldEventPageAdapter10868`)
///   - history                                  part two, passed in
///   - field and movement stories               part three, passed in
///   - originals count                          part four's catalogue size
///
/// THE STREAM IS MANUAL. No owner ranks or auto-advances field stories; nothing
/// here elects, times or plays one (the approved ranked, auto-advancing stream
/// remains the stream owner's obligation, #9483). The host's held card is shown
/// (else the first offered), Previous / Next name the other offered card, and
/// nothing moves unless the reader asks. A story with no input is not offered:
/// with neither, the stream shows its own empty words and every original stays
/// one tap away in All props.
enum FieldEventPageInputAdapter10868 {
    typealias Page = FieldEventPageAdapter10868

    /// The host's own stream state.
    struct StreamState: Equatable {
        /// The card the host holds; nil or no longer offered shows the first offered card.
        var displayed: FieldEventPageCard10868?
        /// The host's full reader is open, so the stream suppresses its requests.
        var readerOpen: Bool = false
        /// The host chose the wide presentation.
        var wide: Bool = false

        init(displayed: FieldEventPageCard10868? = nil, readerOpen: Bool = false, wide: Bool = false) {
            self.displayed = displayed
            self.readerOpen = readerOpen
            self.wide = wide
        }
    }

    enum Words {
        static let companionLabel = "Next"
        static let manualStatus = "Use Previous or Next to see each story"
        static let fieldName = "The field"
        static let movementName = "How chances moved"
        static let historyName = "Win probability"
        static let storyUnavailable = "This story isn’t available right now. Every original is still in All props."
        static let headlineUnavailable = "Headline unavailable right now"
        static let streamHeading = "Field stories"
        static let storiesLabel = "Field stories"
    }

    static func input(_ market: FuturesMarketDetail, history: FieldHistoryInput10868,
                      field: FieldOutlookInput10868?, movement: PreEventShiftInput10868?,
                      originalsCount: Int?, stream state: StreamState,
                      host: Page.Host) -> FieldEventPageInput10868 {
        let phase = Page.phase(market)
        let offered = offeredCards(field: field, movement: movement)
        return FieldEventPageInput10868(
            phase: phase,
            reader: Page.readerHeader(market),
            headline: Page.headline(market, host: host),
            history: history,
            field: field,
            movement: movement,
            stream: stream(scope: streamScope(market, phase: phase), offered: offered, state: state),
            stories: stories(offered),
            about: Page.about(market),
            copy: copy(originalsCount: originalsCount))
    }

    /// One owner scope per market and phase, as the stream requires.
    static func streamScope(_ market: FuturesMarketDetail, phase: FieldOutlookPhase10868) -> String {
        "field:\(market.id):\(Page.phaseWord(phase)):stories"
    }

    /// The stories this snapshot has content for, in the screen's fixed order.
    static func offeredCards(field: FieldOutlookInput10868?,
                             movement: PreEventShiftInput10868?) -> [FieldEventPageCard10868] {
        var cards: [FieldEventPageCard10868] = []
        if field != nil { cards.append(.field) }
        if movement != nil { cards.append(.movement) }
        return cards
    }

    static func stream(scope: String, offered: [FieldEventPageCard10868],
                       state: StreamState) -> StoryStreamPresentation10868 {
        func ref(_ card: FieldEventPageCard10868) -> StoryStreamPresentation10868.CardRef {
            .init(scope: scope, id: card.rawValue)
        }
        let shown = state.displayed.flatMap { offered.contains($0) ? $0 : nil } ?? offered.first
        let index = shown.flatMap { offered.firstIndex(of: $0) }
        let neighbour: FieldEventPageCard10868? = {
            guard let index, offered.count > 1 else { return nil }
            return offered[(index + 1) % offered.count]
        }()
        let previous: FieldEventPageCard10868? = {
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

    static func stories(_ offered: [FieldEventPageCard10868]) -> [FieldEventPageStory10868] {
        offered.map { FieldEventPageStory10868(cardID: $0.rawValue, card: $0) }
    }

    static func copy(originalsCount: Int?) -> FieldEventPageCopy10868 {
        let label: String? = originalsCount.flatMap { count in
            guard count > 0 else { return nil }
            return count == 1 ? "1 original outcome" : "All \(count) original outcomes"
        }
        return FieldEventPageCopy10868(storiesLabel: Words.storiesLabel,
                                       storyUnavailable: Words.storyUnavailable,
                                       headlineUnavailable: Words.headlineUnavailable,
                                       allPropsLabel: label)
    }

    /// The stream's name for a card.
    static func name(_ card: FieldEventPageCard10868) -> String {
        switch card {
        case .history: Words.historyName
        case .field: Words.fieldName
        case .movement: Words.movementName
        }
    }

    /// The card a stream ref names in this scope, or nil.
    static func card(_ ref: StoryStreamPresentation10868.CardRef, scope: String) -> FieldEventPageCard10868? {
        guard ref.scope == scope, let card = FieldEventPageCard10868(rawValue: ref.id), card != .history else { return nil }
        return card
    }
}
