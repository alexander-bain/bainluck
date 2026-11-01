import Foundation

/// #10868 — THE BASEBALL GAME SCREEN'S PRODUCTION ADAPTER, PART SIX: THE WHOLE
/// PAGE INPUT AND ITS MANUAL STORY STREAM.
///
/// PILLARS: FORMATTING / DISCOVER. SHIP: on an MLB event page the matrix, the
/// history and every story the game has content for in its phase arrive as
/// one screen, and a reader moves between the stories with Previous and Next.
///
/// It composes; it decides nothing the parts do not already decide:
///   - headline            part one (`BaseballGamePageAdapter10868`)
///   - history             part two (`BaseballHistoryAdapter10868`), passed in
///   - totals              parts three and four, passed in
///   - home runs, strikeouts, series   part four, passed in
///   - extra innings       part seven (`BaseballExtraInningsAdapter10868`), passed in
///   - originals count     part five's catalogue size, for the All props entry
///
/// The stories are offered in the finished MLB page's own fixed slot order
/// (`MLBFinalDeck11284`: home runs, strikeouts, run totals, extra innings, the
/// series — the approved five families), each only where its phase mounts it.
/// Their names are the production cards' own titles (`MLBFinalCard11284.title`:
/// "Home runs", "<pitcher> · <stat>", "Run totals", "Extra innings", "The
/// series").
///
/// During play only, the home-run and strikeout slots are also offered for the
/// owner's live player input (`BaseballPlayerMilestonesAdapter10868`), passed
/// in. Their names are "Home runs" and the generic "Strikeouts" — no player or
/// pitching role is typed. Nil keeps every phase exactly as before.
///
/// THE STREAM IS MANUAL, exactly as hockey's and soccer's: the only owner that
/// ranks and auto-advances story cards is NBA's (`NBAStoryStreamPolicy9483`).
/// Baseball has no such owner — the reference's `baseballMomentOrder` ranking
/// is not ported — so this file offers no playback control and no dwell,
/// elects no "latest" card and runs no timer: the host's held card is shown,
/// Previous/Next name the other offered cards, and nothing moves unless the
/// reader asks. Context-ranked, automatic advancement stays the stream owner's
/// to add (#9483) — an explicit unpaid obligation, not this file's.
enum BaseballPageInputAdapter10868 {

    /// The host's own stream state — what the reader is looking at.
    struct StreamState: Equatable {
        /// The card the host holds; nil or no longer offered shows the first offered card.
        var displayed: BaseballEventPageCard10868?
        /// The host's full reader is open, so the stream suppresses its requests.
        var readerOpen: Bool
        /// The host chose the wide presentation.
        var wide: Bool

        init(displayed: BaseballEventPageCard10868? = nil, readerOpen: Bool = false, wide: Bool = false) {
            self.displayed = displayed
            self.readerOpen = readerOpen
            self.wide = wide
        }
    }

    enum Words {
        static let streamHeading = "Explore the game"
        static let companionLabel = "Next"
        static let manualStatus = "Use Previous or Next to see each story"
        static let storiesLabel = "Game stories"
        static let storyUnavailable = "This story isn’t available for this game state. Every original is still in All props."
        static let matrixUnavailable = "Comparison unavailable for this game state"
        static let homeRuns = "Home runs"
        static let strikeouts = "Strikeouts"
        static let runTotals = "Run totals"
        static let extraInnings = "Extra innings"
        static let series = "The series"
        static let history = "Win probability"
        static let allProps = "All props"
    }

    static func input(
        _ event: EventDetail,
        history: FieldHistoryInput10868,
        homeRuns: BaseballHomeRunsStory10868?,
        strikeouts: BaseballStrikeoutsStory10868?,
        totals: BaseballTotalsStory10868?,
        extraInnings: BaseballExtraInningsStory10868?,
        series: BaseballSeriesStory10868?,
        originalsCount: Int?,
        stream state: StreamState,
        host: BaseballGamePageAdapter10868.Host,
        livePlayerHomeRuns: PlayerContributionInput10868? = nil,
        livePlayerStrikeouts: PlayerContributionInput10868? = nil
    ) -> BaseballEventPageInput10868 {
        let phase = BaseballGamePageAdapter10868.phase(event, now: host.now)
        let offered = offeredCards(phase: phase, homeRuns: homeRuns, strikeouts: strikeouts,
                                   totals: totals, extraInnings: extraInnings, series: series,
                                   livePlayerHomeRuns: livePlayerHomeRuns,
                                   livePlayerStrikeouts: livePlayerStrikeouts)
        return BaseballEventPageInput10868(
            phase: phase,
            headline: BaseballGamePageAdapter10868.headline(event, host: host),
            history: history,
            homeRuns: homeRuns,
            strikeouts: strikeouts,
            totals: totals,
            extraInnings: extraInnings,
            series: series,
            stream: stream(scope: scope(event, phase: phase), offered: offered, strikeouts: strikeouts,
                           state: state),
            stories: stories(offered),
            copy: copy(originalsCount: originalsCount),
            livePlayerHomeRuns: livePlayerHomeRuns,
            livePlayerStrikeouts: livePlayerStrikeouts)
    }

    /// One owner scope per event and phase, as the stream requires.
    static func scope(_ event: EventDetail, phase: BaseballEventPagePhase10868) -> String {
        "mlb:\(event.id):\(phase)"
    }

    /// The stories this phase has content for, in the production deck's order.
    static func offeredCards(phase: BaseballEventPagePhase10868,
                             homeRuns: BaseballHomeRunsStory10868?,
                             strikeouts: BaseballStrikeoutsStory10868?,
                             totals: BaseballTotalsStory10868?,
                             extraInnings: BaseballExtraInningsStory10868? = nil,
                             series: BaseballSeriesStory10868?,
                             livePlayerHomeRuns: PlayerContributionInput10868? = nil,
                             livePlayerStrikeouts: PlayerContributionInput10868? = nil) -> [BaseballEventPageCard10868] {
        var cards: [BaseballEventPageCard10868] = []
        let liveHomeRuns = BaseballEventPageModel10868.live(livePlayerHomeRuns, phase: phase) != nil
        let liveStrikeouts = BaseballEventPageModel10868.live(livePlayerStrikeouts, phase: phase) != nil
        if (phase == .final && homeRuns != nil) || liveHomeRuns { cards.append(.homeRuns) }
        if (phase == .final && strikeouts != nil) || liveStrikeouts { cards.append(.strikeouts) }
        if let totals, totals.belongs(to: phase) { cards.append(.totals) }
        if extraInnings != nil { cards.append(.extraInnings) }
        if series != nil { cards.append(.series) }
        return cards
    }

    /// A card's stream name: the production card titles.
    static func name(_ card: BaseballEventPageCard10868, strikeouts: BaseballStrikeoutsStory10868?) -> String {
        switch card {
        case .history: Words.history
        case .homeRuns: Words.homeRuns
        case .strikeouts: strikeouts.map { "\($0.card.player) · \($0.card.stat)" } ?? Words.strikeouts
        case .totals: Words.runTotals
        case .extraInnings: Words.extraInnings
        case .series: Words.series
        }
    }

    static func stream(scope: String, offered: [BaseballEventPageCard10868],
                       strikeouts: BaseballStrikeoutsStory10868?,
                       state: StreamState) -> StoryStreamPresentation10868 {
        func ref(_ card: BaseballEventPageCard10868) -> StoryStreamPresentation10868.CardRef {
            .init(scope: scope, id: card.rawValue)
        }
        let shown = state.displayed.flatMap { offered.contains($0) ? $0 : nil } ?? offered.first
        let index = shown.flatMap { offered.firstIndex(of: $0) }
        let neighbour: BaseballEventPageCard10868? = {
            guard let index, offered.count > 1 else { return nil }
            return offered[(index + 1) % offered.count]
        }()
        let previous: BaseballEventPageCard10868? = {
            guard let index, offered.count > 1 else { return nil }
            return offered[(index + offered.count - 1) % offered.count]
        }()
        let cards = offered.map {
            StoryStreamPresentation10868.Card(id: $0.rawValue, name: Self.name($0, strikeouts: strikeouts))
        }
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

    /// One link per offered card id, to the one typed card it shows.
    static func stories(_ offered: [BaseballEventPageCard10868]) -> [BaseballEventPageStory10868] {
        offered.map { BaseballEventPageStory10868(cardID: $0.rawValue, card: $0) }
    }

    static func copy(originalsCount: Int?) -> BaseballEventPageCopy10868 {
        let label: String? = originalsCount.flatMap { count in
            count > 0 ? "\(Words.allProps) · \(count)" : nil
        }
        return BaseballEventPageCopy10868(storiesLabel: Words.storiesLabel, storyUnavailable: Words.storyUnavailable,
                                          matrixUnavailable: Words.matrixUnavailable, allPropsLabel: label)
    }
}
