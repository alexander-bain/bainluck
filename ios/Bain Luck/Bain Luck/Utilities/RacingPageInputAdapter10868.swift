import Foundation

/// #10868 — THE RACING SCREEN'S PRODUCTION ADAPTER, PART FOUR: THE WHOLE PAGE
/// INPUT.
///
/// PILLARS: FORMATTING / DISCOVER. SHIP: on `racing-live` the named-chance
/// headline, the drivers' win history and "All props" arrive as one screen from
/// the race market the page already holds, and every story the app cannot yet
/// feed truthfully is absent — never a card filled with invented race data.
///
/// It composes; it decides nothing the parts do not already decide:
///   - phase, headline, reader heading, About   part one (`RacingFieldPageAdapter10868`)
///   - history                                  part two, passed in
///   - originals count                          part three's catalogue size
///
/// THE STORIES ARE ABSENT, EACH FOR A NAMED REASON. The composed screen mounts a
/// story only where its leaf's own input can be built from production data:
///   - win and podium  needs each driver's winner outcome joined to that driver's
///                     podium outcome by a served participant identity. The two
///                     are separate markets with separate ids; the only common
///                     key is the outcome NAME, and no name is an identity
///                     (RACING-WIN-PODIUM-NATIVE-BINDING-MAP: pairing "by genuine
///                     identity" is Native's). Not built.
///   - expectations,   during the race only, and `.during` is never produced: no
///     the chase       race start, live status, lap report or gap reaches the app.
///   - expectation     at the final, needs each driver's physical finish
///     and finish      (classification) and a pre-race chance elected at a
///                     start clock; neither reaches the app.
/// So `stories` is empty and the stream offers no card: the stream's own empty
/// words show ("No stories in this order. Every original prop is still in All
/// props."), and every original stays one tap away. No reader chances are built
/// (they ride only under the chase and win/podium readers).
///
/// THE STREAM IS MANUAL AND EMPTY. No owner ranks or auto-advances racing
/// stories; nothing here elects, times or plays one (the approved ranked,
/// auto-advancing stream remains the stream owner's obligation, #9483).
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
    }

    static func input(_ market: FuturesMarketDetail, history: FieldHistoryInput10868, originalsCount: Int?,
                      stream state: StreamState, host: Page.Host) -> RacingEventPageInput10868 {
        let phase = Page.phase(market)
        return RacingEventPageInput10868(
            phase: phase,
            reader: Page.readerHeader(market),
            headline: Page.headline(market, host: host),
            history: history,
            winPodium: nil,
            expectations: nil,
            chase: nil,
            finish: nil,
            readerChances: nil,
            stream: stream(scope: streamScope(market, phase: phase), state: state),
            stories: [],
            raceAbout: Page.raceAbout(market),
            winPodiumAbout: nil,
            copy: copy(originalsCount: originalsCount))
    }

    /// One owner scope per market and phase, as the stream requires.
    static func streamScope(_ market: FuturesMarketDetail, phase: FieldOutlookPhase10868) -> String {
        "racing:\(market.id):\(Page.phaseWord(phase)):stories"
    }

    /// The owner's stream with no card offered: no primary, no neighbour, no
    /// playback, no dwell.
    static func stream(scope: String, state: StreamState) -> StoryStreamPresentation10868 {
        StoryStreamPresentation10868(
            scope: scope, eyebrow: nil, heading: Words.streamHeading,
            cards: [], primary: nil, companion: nil, companionLabel: nil,
            wide: state.wide,
            position: nil, status: nil,
            dwellFraction: nil, playback: nil,
            previous: nil, next: nil,
            readerOpen: state.readerOpen)
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
