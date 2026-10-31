import Foundation

/// #10868 — THE RACING SCREEN'S PRODUCTION ADAPTER, PART FOUR: THE WHOLE PAGE
/// INPUT.
///
/// PILLARS: FORMATTING / DISCOVER. SHIP: on `racing-live` the named-chance
/// headline, the drivers' win history, the win and podium comparison (when the
/// host holds its two markets and the owner's join) and "All props" arrive as one
/// screen, and every story the app cannot yet feed truthfully is absent — never a
/// card filled with invented race data.
///
/// It composes; it decides nothing the parts do not already decide:
///   - phase, headline, reader heading, About   part one (`RacingFieldPageAdapter10868`)
///   - history                                  part two, passed in
///   - originals count                          part three's catalogue size
///   - win and podium card and its About        part five, passed in
///
/// A STORY IS MOUNTED ONLY WHERE ITS LEAF'S OWN INPUT CAN BE BUILT:
///   - win and podium  part five (`RacingWinPodiumAdapter10868`), passed in: built
///                     only from the race's podium market body AND the adopting
///                     owner's join between the two markets' outcomes. The two
///                     are separate markets with separate ids; the only common
///                     key is the outcome NAME, and no name is an identity, so
///                     nothing here pairs them. No production owner fetches the
///                     podium body or serves the join today, so in production
///                     this card is absent (owner binding debt in the return).
///   - expectations,   during the race only, and `.during` is never produced: no
///     the chase       race start, live status, lap report or gap reaches the app.
///   - expectation     at the final, needs each driver's physical finish
///     and finish      (classification) and a pre-race chance elected at a
///                     start clock; neither reaches the app.
/// Without the win/podium card, `stories` is empty and the stream offers no card:
/// the stream's own empty words show ("No stories in this order. Every original
/// prop is still in All props."), and every original stays one tap away. No
/// reader chances are built (they ride only under the chase and win/podium
/// readers).
///
/// THE STREAM IS MANUAL. No owner ranks or auto-advances racing stories; nothing
/// here elects, times or plays one (the approved ranked, auto-advancing stream
/// remains the stream owner's obligation, #9483). With the win/podium card it
/// offers that one card as the shown card, with no Previous / Next, playback or
/// dwell; its "Open full card" opens the card's full-size reader.
enum RacingPageInputAdapter10868 {
    typealias Page = RacingFieldPageAdapter10868

    /// The host's own stream state.
    struct StreamState: Equatable {
        /// The host's full reader is open, so the stream suppresses its requests.
        var readerOpen: Bool = false
        /// The host chose the wide presentation.
        var wide: Bool = false

        init(readerOpen: Bool = false, wide: Bool = false) {
            self.readerOpen = readerOpen
            self.wide = wide
        }
    }

    /// The Design-approved racing page copy.
    enum Words {
        static let streamHeading = "Race stories"
        static let storiesLabel = "Race stories"
        static let storyUnavailable = "This story isn’t available for this race moment. Every original is still in All props."
        static let headlineUnavailable = "Race headline unavailable for this moment"
        static let winPodiumName = RacingWinPodiumAdapter10868.Words.cardName
    }

    /// `winPodium` is part five's card, or nil (no podium body or join held).
    static func input(_ market: FuturesMarketDetail, history: FieldHistoryInput10868, originalsCount: Int?,
                      stream state: StreamState, winPodium: RacingWinPodiumAdapter10868.Card? = nil,
                      host: Page.Host) -> RacingEventPageInput10868 {
        let phase = Page.phase(market)
        // A card from another phase is not this page's story.
        let card = winPodium.flatMap { $0.input.phase == phase ? $0 : nil }
        return RacingEventPageInput10868(
            phase: phase,
            reader: Page.readerHeader(market),
            headline: Page.headline(market, host: host),
            history: history,
            winPodium: card?.input,
            expectations: nil,
            chase: nil,
            finish: nil,
            readerChances: nil,
            stream: stream(scope: streamScope(market, phase: phase), offersWinPodium: card != nil, state: state),
            stories: card == nil ? [] : [RacingEventPageStory10868(cardID: RacingEventPageCard10868.winPodium.rawValue,
                                                                   card: .winPodium)],
            raceAbout: Page.raceAbout(market),
            winPodiumAbout: card?.about,
            copy: copy(originalsCount: originalsCount))
    }

    /// One owner scope per market and phase, as the stream requires.
    static func streamScope(_ market: FuturesMarketDetail, phase: FieldOutlookPhase10868) -> String {
        "racing:\(market.id):\(Page.phaseWord(phase)):stories"
    }

    /// The owner's manual stream: the win/podium card when offered, shown, with
    /// no neighbour, no playback and no dwell. Nothing offered: no primary.
    static func stream(scope: String, offersWinPodium: Bool = false,
                       state: StreamState) -> StoryStreamPresentation10868 {
        let id = RacingEventPageCard10868.winPodium.rawValue
        return StoryStreamPresentation10868(
            scope: scope, eyebrow: nil, heading: Words.streamHeading,
            cards: offersWinPodium ? [StoryStreamPresentation10868.Card(id: id, name: Words.winPodiumName)] : [],
            primary: offersWinPodium ? StoryStreamPresentation10868.CardRef(scope: scope, id: id) : nil,
            companion: nil, companionLabel: nil,
            wide: state.wide,
            position: nil, status: nil,
            dwellFraction: nil, playback: nil,
            previous: nil, next: nil,
            readerOpen: state.readerOpen)
    }

    /// The story card a stream ref names in this scope, or nil.
    static func card(_ ref: StoryStreamPresentation10868.CardRef, scope: String) -> RacingEventPageCard10868? {
        guard ref.scope == scope, let card = RacingEventPageCard10868(rawValue: ref.id), card != .history else { return nil }
        return card
    }

    static func copy(originalsCount: Int?) -> RacingEventPageCopy10868 {
        let label: String? = originalsCount.flatMap { count in
            guard count > 0 else { return nil }
            return count == 1 ? "1 original outcome" : "All \(count) original outcomes"
        }
        return RacingEventPageCopy10868(storiesLabel: Words.storiesLabel, storyUnavailable: Words.storyUnavailable,
                                        headlineUnavailable: Words.headlineUnavailable, allPropsLabel: label)
    }
}
