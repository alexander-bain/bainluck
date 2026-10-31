import SwiftUI

// #10868 — the tennis match screen (`tennis`, `tennis-live`, `tennis-final`):
// one native presentation composed from the accepted leaves. The two players'
// win chances lead, at equal prominence. A fan sees, in this order: the match
// headline (the owner's eyebrow, title and About entry, each named player's
// chance for the phase — before the match the pre-match chance; during it the
// pre-match chance beside an admitted in-match chance or its own unavailable
// words; after it the pre-match chance beside the owner's reported result —
// and the owner's match state: the set score in sets, never a games figure)
// beside the players' win probability history, with the held recorded reading
// under it once the owner holds one; then the owner's story stream — set
// winners (first-set expectations before and during play), total games, exact
// set finishes and set and game handicaps — and the "All props" entry. The
// history and each story open as full-size content made of the same Views, and
// "All props", the held original's Details and the match About are further
// content modes.
//
// Presentation only, composed from the approved `TennisFinal.tsx`
// (`TennisFinalHero`, `TennisFinalStories`, `tennisFinalFocus.ts`) for the
// final and `LiveTennis.tsx` (`lt-hero`, `LiveTennisHistory`,
// `LiveTennisStory`, `tennisFocus.ts`) for play, as mounted in `Atlas.tsx`
// (`tennis`, `tennis-final`) and `current-routes.json` (`tennis-live`). The
// reference's fixture loaders, replay and capture state, scrubber, moment
// ranking (`tennisMomentOrder`) and its reasons, catalogue search and
// category select, sheets, dialogs, "Aa Larger" and focus restoration are NOT
// ported. The leaves are the actual accepted Views:
//
//   • `FieldPhaseHeadlinePresentation10868` — the two named players;
//   • `FieldProbabilityHistoryPresentation10868` — the anchor;
//   • `TennisProbabilityComparisonPresentation9483` — the held recorded
//     reading under the anchor (shown only once the owner holds one, as the
//     production reading panel shows on the page);
//   • `TennisDatedChanceComparisonView9483` — the full-size history's dated
//     reading (the latest until one is held);
//   • `PeriodOutcomeFinalScorePresentation10868` — "Set winners" after the
//     match, and with the owner's opt-ins, "First-set expectations" during play
//     (completed sets) and before it (named sets, pre-match chances only);
//   • `TotalMilestoneLineComparison10868` — "Total games" after the match
//     (actual beside the opening market line);
//   • `TotalMilestoneThresholdLive10868` — "Total-game milestones" during play,
//     and before play with the owner's before-play copy;
//   • `ExactScoreFinishPresentation10868` — "Exact set finishes" after the
//     match (finish tiles);
//   • `ExactScoreFinishLanePresentation10868` — "Exact set finishes" during
//     play, and before play with the owner's before-play copy (finish lanes);
//   • `OriginalHandicapCardView9483` — "Set and game handicaps", final by
//     default, during or before play only with the owner's opt-in;
//   • `StoryStreamPresentationView10868` — the controlled story stream;
//   • `OriginalMarketCatalogueView9483` / `OriginalMarketDetailsView9483` —
//     "All props" and the held original's Details.
//
// Nothing new is drawn here beyond arrangement, card surfaces, the owner's
// story, reason and notice words, the compact reader heading and the About
// text.
//
// The page's phase is the owner's explicit `TennisEventPagePhase10868`, never
// read from a raw feed status, a set count, a clock, a quote or the result. A
// leaf is mounted only when its own phase is the page's AND its own shown rule
// says it shows something in that phase (a card that would draw nothing never
// takes a stream cell). The final totals and final exact-finish variants are
// mounted after the match only; the threshold and lane variants before and
// during play only. A leaf from another phase is not coerced into this one —
// it is not mounted, and a headline from another phase shows the owner's
// unavailable words.
//
// Tennis is two-outcome: the winner market prices no draw
// (`DrawPricedWinner.sportPricesADraw` — `SportVocab` declares
// `winnerMarketPricesADraw: false` for tennis). The headline's two players and
// the history's two traces are exactly what the owner supplies; this layer
// never complements, normalizes or joins them, treats a missing value as zero,
// turns the reported result into a 0/100 quote or a history point, reads a
// contract's grade from the reported result, promotes a settlement-time or
// last quote to a current chance, or invents a set in progress, a games score,
// a projection or a finish marker. Match, set and game units are the leaves'
// own and the owner's: a set count is never drawn on a games axis, and a set
// handicap and a game handicap stay separate panels. Each leaf keeps its own
// rules for that.
//
// The host supplies each leaf's own immutable input, already admitted for the
// same snapshot; this layer groups them and never re-elects, copies, filters
// or formats an observation, a result, a window, a marker or a word.
//
// The held recorded reading is the owner's resolution of the chart's own
// readout series (`TennisChartReading9483.Series.resolve`): the held reading,
// a break, a held reading that is gone, or — with nothing held — the latest.
// On the page it shows only once the owner holds something (the hero already
// prints the current chance, #9517); full size it always shows. "Show latest"
// is offered only when the owner offers it AND supplies the action.
//
// The story stream is the owner's: its cards, order, primary, companion,
// position, status, pending, playback, progress, previous/next, scope and
// reader-open flag. This layer wires each supplied card id to the one story the
// owner names for it, and shows the owner's unavailable words for an id that
// names no single story this phase mounts — never a neighbour. A card's own
// actions — selecting, opening Details, recovering a selection — and a write to
// a card's disclosure first call the stream's activation hook (so the owner can
// hold) and then the host's exact callback or write. Reading a disclosure
// binding asks for nothing, and building a card asks for nothing. Full-size
// content reuses the same leaves with the host's exact callbacks and bindings
// and no activation, so opening a card never requests a hold by appearing.
//
// The owner may also pass an interaction hook, so it can hold its stream
// before an action outside the stream lands. On the page — the headline's
// open and About, the anchor history's actions, inspection choices and plot
// taps, the held reading's "Show latest", the All props entry — and in the
// catalogue and Details content — an original's selection and a Details
// history intent — the action calls that hook once and then the owner's exact
// callback with its exact value. Without a callback there is no action and no
// hook call; without a hook every callback is the owner's own. Building or
// reading the view calls nothing. Full-size content keeps the exact callbacks:
// its host already holds the stream while it is open. Stream cards keep the
// stream's own activation and never pass through the hook as well.
//
// The full-size history is the same history input with its expanded layout
// and without its expand control; every series, run, guide, break, selection,
// readout, window, scale, range, inspection and other control is unchanged.
//
// Phone stacks the headline above the history, then the stories. A regular
// or unspecified size class (a Mac window) places the headline beside the
// history while both keep their minimum widths, otherwise it stacks too;
// accessibility sizes always stack. The stories run full width below.
//
// The host owns the scroll, navigation, sheets, Back/Done, paging, focus,
// routing to and from the catalogue, an original's Details and the About, each
// card's held selection and disclosure, the held reading, the held/received
// frame, how a hook request holds the stream, live subscriptions and every
// genuine update. This view keeps no state, runs no timer or animation, holds
// no subscription and presents no sheet or navigation of its own. Every
// callback is the host's own closure handed to the leaf unchanged. With no
// callback, nothing pretends to act.
//
// Host binding: `Utilities/Tennis*Adapter10868.swift` build this input from the
// event page's own bodies; what they still cannot admit is named there.

/// The owner's explicit phase for the whole screen.
nonisolated enum TennisEventPagePhase10868: String, Hashable, CaseIterable {
    case before
    case during
    case final
}

/// One card the page can show full size. `history` is the anchor.
nonisolated enum TennisEventPageCard10868: String, Hashable, CaseIterable {
    case history
    /// "Set winners" after the match; "First-set expectations" before and during.
    case sets
    /// "Total games" after the match; "Total-game milestones" before and during.
    case totals
    /// "Exact set finishes".
    case exact
    /// "Set and game handicaps".
    case handicaps
}

/// What the host's container is showing, chosen by the host.
nonisolated enum TennisEventPageMode10868: Equatable {
    /// The match screen body.
    case page
    /// One card's full-size content.
    case reader(TennisEventPageCard10868)
    /// Every retained original ("All props").
    case catalogue
    /// The held original's Details.
    case original
    /// The owner's match About.
    case about
}

nonisolated enum TennisEventPageArrangement10868: Equatable {
    case stacked
    case sideBySide
}

// MARK: - Page input

/// The owner's one-line match words above full-size content.
nonisolated struct TennisEventPageReaderHeader10868: Equatable {
    /// "Fokina won · 2–1 sets".
    let title: String
    /// "Pre-match · Fokina 46% · Tiafoe 55%"; nil draws none.
    let state: String?
}

/// The owner's link from one stream card id to the story it shows.
nonisolated struct TennisEventPageStory10868: Equatable {
    /// Exactly as in `StoryStreamPresentation10868.cards`.
    let cardID: String
    let card: TennisEventPageCard10868
    /// The owner's words for why this story is here; nil draws none.
    var reason: String? = nil
}

/// Total games: after the match, the actual total beside the opening market
/// line; before and during play, each original's literal threshold.
nonisolated enum TennisEventPageTotals10868: Equatable {
    case final(TotalMilestoneLineComparisonInput10868)
    case thresholds(TotalMilestoneThresholdLiveInput10868)
}

/// Exact set finishes: after the match, the finish tiles; before and during
/// play, the finish lanes.
nonisolated enum TennisEventPageExact10868: Equatable {
    case final(ExactScoreFinishInput10868)
    case lanes(ExactScoreFinishLaneInput10868)
}

/// Set and game handicaps: the shared handicap card's own input and tint.
struct TennisEventPageHandicaps10868: Equatable {
    let input: OriginalHandicapCard9483.Input
    let tint: Color
}

/// The owner's resolution of the chart's own readout series for the held
/// recorded reading, handed unchanged to the two accepted tennis comparisons.
struct TennisEventPageReading10868: Equatable {
    /// `TennisChartReading9483.Series.resolve(held)`.
    let shown: TennisChartReading9483.Shown
    /// `series.baseline`: the last observation before the scheduled start.
    let baseline: TennisChartReading9483.Reading?
    /// `series.scheduledStart`.
    let scheduledStart: Date?
    let homeName: String
    let awayName: String
    let homeTint: Color
    let awayTint: Color
    /// Whether the owner offers "Show latest" (the production panel's rule).
    let offersLatest: Bool
    /// Formatting only: today prints a time, another day its date too.
    let now: Date

    /// Something is held — a reading, a break or a reading that is gone. With
    /// nothing held the page shows no reading of its own.
    var isHeld: Bool {
        if case .reading(_, held: false) = shown { return false }
        return true
    }
}

/// One section of the owner's About, verbatim.
nonisolated struct TennisEventPageAboutSection10868: Equatable {
    /// "Chances".
    let title: String
    let paragraphs: [String]
}

/// The owner's match About, verbatim.
nonisolated struct TennisEventPageAbout10868: Equatable {
    /// "About this match".
    let title: String
    let sections: [TennisEventPageAboutSection10868]
}

nonisolated struct TennisEventPageCopy10868: Equatable {
    /// Spoken name of the stories group ("Match stories").
    let storiesLabel: String
    /// Shown in a stream cell whose id names no single story this phase shows.
    let storyUnavailable: String
    /// Shown in place of a headline whose phase is not the page's.
    let headlineUnavailable: String
    /// "All 18 original props"; nil draws no entry.
    let allPropsLabel: String?
}

struct TennisEventPageInput10868: Equatable {
    let phase: TennisEventPagePhase10868
    /// The match every card belongs to.
    let eventID: String
    let reader: TennisEventPageReaderHeader10868
    let headline: FieldHeadlineInput10868
    /// The owner's status words under the headline; nil draws none.
    var notice: String? = nil
    let history: FieldHistoryInput10868
    /// The held recorded reading; nil draws none.
    var reading: TennisEventPageReading10868? = nil
    /// `var` so the host can narrow which originals offer Details
    /// (`TennisCardsAdapter10868.offeringDetails`); nothing else is changed.
    var sets: PeriodOutcomeFinalScoreInput10868?
    let totals: TennisEventPageTotals10868?
    /// `var` for the same narrowing on the lanes.
    var exact: TennisEventPageExact10868?
    let handicaps: TennisEventPageHandicaps10868?
    /// The owner's story stream; nil draws no stories.
    let stream: StoryStreamPresentation10868?
    let stories: [TennisEventPageStory10868]
    /// Opened by the headline's About control; nil: no control.
    let about: TennisEventPageAbout10868?
    let copy: TennisEventPageCopy10868
}

/// The owner's originals behind "All props", for the catalogue and
/// Details modes. Every field reaches the existing leaves unchanged.
struct TennisEventPageOriginals10868 {
    /// The latest admitted originals for one scope; nil shows `emptyWords`.
    let catalogue: OriginalMarketDetails9483.Catalogue?
    /// The owner's held selection; nil holds none.
    let selection: OriginalMarketDetails9483.Selection?
    /// The held original's admitted recorded history, for the Details mode
    /// only; nil keeps its summary-only Details.
    var recorded: OriginalMarketDetails9483.RecordedHistory? = nil
    /// The owner's card label for an exact identity; otherwise its title.
    var labels: [OriginalMarketDetails9483.Identity: String] = [:]
    /// "All props".
    let heading: String
    /// "18 originals"; nil draws none.
    var context: String? = nil
    /// "Props unavailable".
    let emptyWords: String
    /// The label for an original with no readable title of its own.
    let unavailableChoice: String
    let tint: Color
}

nonisolated enum TennisEventPageAccessibilityID10868 {
    static let page = "tennisEventPage10868.page"
    static let hero = "tennisEventPage10868.hero"
    static let headlineUnavailable = "tennisEventPage10868.headline.unavailable"
    static let notice = "tennisEventPage10868.notice"
    static let anchor = "tennisEventPage10868.anchor"
    static let reading = "tennisEventPage10868.reading"
    static let stories = "tennisEventPage10868.stories"
    static let allProps = "tennisEventPage10868.allProps"
    static let unavailable = "tennisEventPage10868.story.unavailable"
    static let readerHeader = "tennisEventPage10868.readerHeader"
    static let readerAbout = "tennisEventPage10868.readerHeader.about"
    static let catalogue = "tennisEventPage10868.catalogue"
    static let original = "tennisEventPage10868.original"
    static let about = "tennisEventPage10868.about"
    static func card(_ card: TennisEventPageCard10868) -> String { "tennisEventPage10868.card.\(card.rawValue)" }
}

// MARK: - Page model

/// Which leaves the page mounts, resolved once per input.
struct TennisEventPageModel10868: Equatable {
    let input: TennisEventPageInput10868

    init(_ input: TennisEventPageInput10868) {
        self.input = input
    }

    // MARK: Each leaf's own name for the page's phase

    static func headlinePhase(_ phase: TennisEventPagePhase10868) -> FieldOutlookPhase10868 {
        switch phase {
        case .before: .before
        case .during: .during
        case .final: .final
        }
    }

    static func periodPhase(_ phase: TennisEventPagePhase10868) -> PeriodOutcomePhase10868 {
        switch phase {
        case .before: .before
        case .during: .during
        case .final: .final
        }
    }

    static func totalPhase(_ phase: TennisEventPagePhase10868) -> TotalMilestonePhase10868 {
        switch phase {
        case .before: .before
        case .during: .during
        case .final: .final
        }
    }

    static func exactPhase(_ phase: TennisEventPagePhase10868) -> ExactScoreMapPhase10868 {
        switch phase {
        case .before: .before
        case .during: .during
        case .final: .final
        }
    }

    static func handicapPhase(_ phase: TennisEventPagePhase10868) -> OriginalHandicapCard9483.Phase {
        switch phase {
        case .before: .before
        case .during: .during
        case .final: .final
        }
    }

    // MARK: Leaves — each only at its own phase, and only when it shows something

    /// The headline at the page's own phase. Otherwise nothing.
    var headline: FieldHeadlineInput10868? {
        input.headline.phase == Self.headlinePhase(input.phase) ? input.headline : nil
    }

    /// Set winners / first-set expectations at the page's own phase, when the
    /// leaf's own rule shows a set.
    var sets: PeriodOutcomeFinalScoreInput10868? {
        guard let sets = input.sets, sets.comparison.phase == Self.periodPhase(input.phase), sets.isShown else {
            return nil
        }
        return sets
    }

    /// The final's line comparison after the match; the threshold card before
    /// and during play. Never the other variant, never another phase.
    var totals: TennisEventPageTotals10868? {
        guard let totals = input.totals else { return nil }
        switch totals {
        case .final(let line):
            guard input.phase == .final, line.profile.phase == .final, line.isPresented else { return nil }
        case .thresholds(let live):
            guard input.phase != .final, live.profile.phase == Self.totalPhase(input.phase),
                  live.isPresented else { return nil }
        }
        return totals
    }

    /// The final's finish tiles after the match; the lanes before and during
    /// play. Never the other variant, never another phase.
    var exact: TennisEventPageExact10868? {
        guard let exact = input.exact else { return nil }
        switch exact {
        case .final(let tiles):
            guard input.phase == .final, tiles.map.phase == .final, tiles.isShown else { return nil }
        case .lanes(let lanes):
            guard input.phase != .final, lanes.map.phase == Self.exactPhase(input.phase), lanes.isShown else {
                return nil
            }
        }
        return exact
    }

    /// Set and game handicaps at the page's own phase, when the card's own
    /// rule shows it in that phase.
    var handicaps: TennisEventPageHandicaps10868? {
        guard let handicaps = input.handicaps, handicaps.input.phase == Self.handicapPhase(input.phase),
              OriginalHandicapCard9483.isShown(handicaps.input) else { return nil }
        return handicaps
    }

    func isMounted(_ card: TennisEventPageCard10868) -> Bool {
        switch card {
        case .history: true
        case .sets: sets != nil
        case .totals: totals != nil
        case .exact: exact != nil
        case .handicaps: handicaps != nil
        }
    }

    /// The owner's link a stream card id names: exactly one link with that
    /// id, to a story this phase mounts. Otherwise nothing.
    func story(_ cardID: String) -> TennisEventPageStory10868? {
        let links = input.stories.filter { $0.cardID == cardID }
        guard links.count == 1, let link = links.first, link.card != .history, isMounted(link.card) else { return nil }
        return link
    }

    func storyCard(_ cardID: String) -> TennisEventPageCard10868? { story(cardID)?.card }

    /// Full-size content exists for the anchor and for a story this phase shows.
    func readerShows(_ card: TennisEventPageCard10868) -> Bool { isMounted(card) }

    /// The anchor's full-size content: the same history in its expanded
    /// layout, without an expand control inside the reader. Every other field
    /// is the owner's, unchanged.
    var readerHistory: FieldHistoryInput10868 {
        let history = input.history
        return FieldHistoryInput10868(
            title: history.title, caption: history.caption, series: history.series,
            selection: history.selection, domain: history.domain, ceiling: history.ceiling,
            yTicks: history.yTicks, xTicks: history.xTicks, guides: history.guides, breaks: history.breaks,
            readout: history.readout, markKey: history.markKey,
            comparisonExplanation: history.comparisonExplanation, notes: history.notes,
            summary: history.summary, plotHeight: history.plotHeight,
            unboundReadingWords: history.unboundReadingWords, plotUnavailableWords: history.plotUnavailableWords,
            windows: history.windows, scale: history.scale, moreOriginals: history.moreOriginals,
            details: history.details, expand: nil, inspect: history.inspect,
            previous: history.previous, next: history.next, inspection: history.inspection,
            layout: .expanded,
            probabilityLowerBound: history.probabilityLowerBound,
            probabilityRangeExplanation: history.probabilityRangeExplanation,
            selectedReadout: history.selectedReadout, inspectionRingShape: history.inspectionRingShape,
            plotAbsence: history.plotAbsence, showsKey: history.showsKey
        )
    }

    // MARK: The held recorded reading

    /// The page shows the held reading only once the owner holds something.
    var pageReading: TennisEventPageReading10868? {
        guard let reading = input.reading, reading.isHeld else { return nil }
        return reading
    }

    /// Full size, the reading always shows (the latest until one is held).
    var readerReading: TennisEventPageReading10868? { input.reading }

    // MARK: About and entries

    /// The owner's About, when it carries readable words.
    var about: TennisEventPageAbout10868? {
        guard let about = input.about,
              Self.readable(about.title) != nil || about.sections.contains(where: Self.hasWords)
        else { return nil }
        return about
    }

    static func hasWords(_ section: TennisEventPageAboutSection10868) -> Bool {
        readable(section.title) != nil || section.paragraphs.contains { readable($0) != nil }
    }

    func aboutAvailable(canOpen: Bool) -> Bool {
        canOpen && about != nil
    }

    /// Whether `mode`'s compact heading shows the About entry: full-size
    /// content only — the page has the headline's own control.
    func aboutEntry(mode: TennisEventPageMode10868, canOpen: Bool) -> Bool {
        guard case .reader = mode, Self.readable(input.headline.copy.aboutLabel) != nil else { return false }
        return aboutAvailable(canOpen: canOpen)
    }

    func allPropsAvailable(canOpen: Bool) -> Bool {
        canOpen && Self.readable(input.copy.allPropsLabel) != nil
    }

    static func readable(_ words: String?) -> String? {
        guard let words, !words.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return nil }
        return words
    }

    /// The arrangements to try, in order. Accessibility sizes and a compact
    /// width stack; a regular or unspecified width (a Mac window has no size
    /// class) tries the headline beside the history, then stacks — their
    /// minimum widths decide which fits.
    static func arrangements(sizeClass: UserInterfaceSizeClass?, accessibilitySize: Bool) -> [TennisEventPageArrangement10868] {
        sizeClass != .compact && !accessibilitySize ? [.sideBySide, .stacked] : [.stacked]
    }
}

// MARK: - About content

/// The owner's match About in its own words. No source control: no production
/// field serves a source link for a tennis match.
struct TennisEventPageAboutContent10868: View {
    let about: TennisEventPageAbout10868

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            if let title = TennisEventPageModel10868.readable(about.title) {
                Text(title)
                    .font(.headline)
                    .foregroundStyle(DS.textPrimary)
                    .accessibilityAddTraits(.isHeader)
            }
            ForEach(Array(about.sections.enumerated()), id: \.offset) { _, section in
                if TennisEventPageModel10868.hasWords(section) {
                    VStack(alignment: .leading, spacing: 6) {
                        if let title = TennisEventPageModel10868.readable(section.title) {
                            Text(title)
                                .font(.body.weight(.semibold))
                                .foregroundStyle(DS.textPrimary)
                                .accessibilityAddTraits(.isHeader)
                        }
                        ForEach(Array(section.paragraphs.enumerated()), id: \.offset) { _, paragraph in
                            if let words = TennisEventPageModel10868.readable(paragraph) {
                                Text(words)
                                    .font(.body)
                                    .foregroundStyle(DS.textPrimary)
                            }
                        }
                    }
                }
            }
        }
        .fixedSize(horizontal: false, vertical: true)
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

// MARK: - Page view

struct TennisEventPagePresentation10868: View {
    typealias Stream = StoryStreamPresentation10868

    let input: TennisEventPageInput10868
    var mode: TennisEventPageMode10868 = .page
    /// The catalogue and Details modes' content; nil: neither has any.
    var originals: TennisEventPageOriginals10868? = nil
    /// Opens the host's container on the owner's About.
    var onAbout: (() -> Void)? = nil
    /// Opens the host's existing catalogue.
    var onAllProps: (() -> Void)? = nil
    /// A catalogue card's exact selection, for the host to hold and route.
    var onOriginalSelect: ((OriginalMarketDetails9483.Selection) -> Void)? = nil
    /// A Details history control's exact intent, for the host to route.
    var onOriginalHistory: ((OriginalMarketDetails9483.HistoryIntent) -> Void)? = nil
    var onStoryIntent: ((Stream.Intent) -> Void)? = nil
    /// A headline player's exact open, for the host's history.
    var onHeadlineOpen: ((FieldMovementOpen10868) -> Void)? = nil
    var onHistoryAction: ((String) -> Void)? = nil
    var onHistoryInspectionChoice: ((String) -> Void)? = nil
    var onHistoryPlotPosition: ((Double) -> Void)? = nil
    /// The host's explicit choice of the newest recorded reading.
    var onShowLatestReading: (() -> Void)? = nil
    /// A set original's exact identity, for its Details.
    var onSetDetails: ((String) -> Void)? = nil
    var onTotalSelect: ((String) -> Void)? = nil
    var onTotalDetails: ((String) -> Void)? = nil
    /// Page-owned; nil shows the card's timing already expanded.
    var totalTimingExpanded: Binding<Bool>? = nil
    /// (scope id, original id), exactly as supplied.
    var onExactSelect: ((String, String) -> Void)? = nil
    /// (scope id, original id), exactly as supplied.
    var onExactDetails: ((String, String) -> Void)? = nil
    var onExactRecover: (() -> Void)? = nil
    var onHandicapSelect: ((OriginalMarketDetails9483.Selection) -> Void)? = nil
    /// Page-owned; nil shows the explanation expanded.
    var handicapExplanationExpanded: Binding<Bool>? = nil
    /// Called once just before a page, catalogue or Details action reaches its
    /// owner callback, so the owner can hold its stream. Never called by
    /// building the view, by full-size content or by a stream card.
    var onInteraction: (() -> Void)? = nil

    @Environment(\.horizontalSizeClass) private var sizeClass
    @Environment(\.dynamicTypeSize) private var typeSize
    @ScaledMetric(relativeTo: .body) private var headlineMinWidth: CGFloat = 300
    @ScaledMetric(relativeTo: .body) private var headlineMaxWidth: CGFloat = 420
    @ScaledMetric(relativeTo: .body) private var anchorMinWidth: CGFloat = 420
    @ScaledMetric(relativeTo: .body) private var controlSize: CGFloat = 44

    private var model: TennisEventPageModel10868 { TennisEventPageModel10868(input) }

    // MARK: Relays

    /// A card's own action, after the stream's activation hook when the card
    /// sits in the stream. No host callback: no action at all.
    static func relay<Value>(_ action: ((Value) -> Void)?,
                             through activation: StoryStreamCardActivation10868?) -> ((Value) -> Void)? {
        guard let action else { return nil }
        guard let activation else { return action }
        return { value in
            activation.request()
            action(value)
        }
    }

    /// The same for a two-value action ((scope id, original id)).
    static func relayPair<First, Second>(_ action: ((First, Second) -> Void)?,
                                         through activation: StoryStreamCardActivation10868?) -> ((First, Second) -> Void)? {
        guard let action else { return nil }
        guard let activation else { return action }
        return { first, second in
            activation.request()
            action(first, second)
        }
    }

    /// The same for an action without a value.
    static func relayAction(_ action: (() -> Void)?,
                            through activation: StoryStreamCardActivation10868?) -> (() -> Void)? {
        guard let action else { return nil }
        guard let activation else { return action }
        return {
            activation.request()
            action()
        }
    }

    /// A card's disclosure binding: a write first calls the stream's
    /// activation hook when the card sits in the stream, then writes the
    /// owner's binding exactly; a read asks for nothing. No host binding: none.
    static func relayBinding(_ binding: Binding<Bool>?,
                             through activation: StoryStreamCardActivation10868?) -> Binding<Bool>? {
        guard let binding else { return nil }
        guard let activation else { return binding }
        return Binding(
            get: { binding.wrappedValue },
            set: { value in
                activation.request()
                binding.wrappedValue = value
            }
        )
    }

    /// A page, catalogue or Details action, after the owner's interaction
    /// hook. No host callback: no action and no hook call. No hook: the exact
    /// callback.
    static func held<Value>(_ action: ((Value) -> Void)?, by interaction: (() -> Void)?) -> ((Value) -> Void)? {
        guard let action else { return nil }
        guard let interaction else { return action }
        return { value in
            interaction()
            action(value)
        }
    }

    /// The same for an action without a value.
    static func heldAction(_ action: (() -> Void)?, by interaction: (() -> Void)?) -> (() -> Void)? {
        guard let action else { return nil }
        guard let interaction else { return action }
        return {
            interaction()
            action()
        }
    }

    var body: some View {
        Group {
            switch mode {
            case .page: page
            case .reader(let card): reader(card)
            case .catalogue: catalogueMode
            case .original: originalMode
            case .about: aboutMode
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    // MARK: Leaves — the actual Views, each with the host's own callbacks

    /// The host's About opener; nil without readable About text or without a
    /// callback, so the headline draws no About control.
    func aboutOpener() -> (() -> Void)? {
        guard model.aboutAvailable(canOpen: onAbout != nil), let onAbout else { return nil }
        return onAbout
    }

    /// The match headline, at the page's phase only. Its open and About pass
    /// the interaction hook first.
    func headlineContent() -> FieldPhaseHeadlinePresentation10868? {
        model.headline.map {
            FieldPhaseHeadlinePresentation10868(input: $0, onAbout: Self.heldAction(aboutOpener(), by: onInteraction),
                                                onOpen: Self.held(onHeadlineOpen, by: onInteraction))
        }
    }

    /// The anchor passes the interaction hook first; the full-size history
    /// keeps the exact callbacks.
    func historyContent(reader: Bool) -> FieldProbabilityHistoryPresentation10868 {
        let interaction = reader ? nil : onInteraction
        return FieldProbabilityHistoryPresentation10868(
            input: reader ? model.readerHistory : input.history,
            onAction: Self.held(onHistoryAction, by: interaction),
            onInspectionChoice: Self.held(onHistoryInspectionChoice, by: interaction),
            onPlotPosition: Self.held(onHistoryPlotPosition, by: interaction)
        )
    }

    /// "Show latest" for the page's reading (after the hook) or the reader's
    /// (exact). Nil without a callback: the leaf then offers no control.
    func showLatest(reader: Bool) -> (() -> Void)? {
        Self.heldAction(onShowLatestReading, by: reader ? nil : onInteraction)
    }

    /// The held recorded reading under the anchor, once the owner holds one.
    func pageReadingContent() -> TennisProbabilityComparisonPresentation9483? {
        guard let reading = model.pageReading else { return nil }
        let latest = showLatest(reader: false)
        return TennisProbabilityComparisonPresentation9483(
            shown: reading.shown, baseline: reading.baseline, scheduledStart: reading.scheduledStart,
            homeName: reading.homeName, awayName: reading.awayName,
            colors: (away: reading.awayTint, home: reading.homeTint), expanded: false,
            offersLatest: reading.offersLatest && latest != nil,
            onShowLatest: { latest?() })
    }

    /// The full-size history's dated reading: the latest until one is held.
    func readerReadingContent() -> TennisDatedChanceComparisonView9483? {
        guard let reading = model.readerReading else { return nil }
        return TennisDatedChanceComparisonView9483(
            shown: reading.shown, baseline: reading.baseline, scheduledStart: reading.scheduledStart,
            homeName: reading.homeName, awayName: reading.awayName,
            homeColor: reading.homeTint, awayColor: reading.awayTint,
            offersLatest: reading.offersLatest, onShowLatest: showLatest(reader: true), now: reading.now)
    }

    /// `activation` is the stream's hook for a card in the stream; nil in
    /// full-size content.
    func setsContent(activation: StoryStreamCardActivation10868? = nil) -> PeriodOutcomeFinalScorePresentation10868? {
        model.sets.map {
            PeriodOutcomeFinalScorePresentation10868(input: $0, onDetails: Self.relay(onSetDetails, through: activation))
        }
    }

    func finalTotalsContent(activation: StoryStreamCardActivation10868? = nil) -> TotalMilestoneLineComparison10868? {
        guard case .final(let line)? = model.totals else { return nil }
        return TotalMilestoneLineComparison10868(
            input: line,
            onSelect: Self.relay(onTotalSelect, through: activation),
            onDetails: Self.relay(onTotalDetails, through: activation),
            timingExpanded: Self.relayBinding(totalTimingExpanded, through: activation))
    }

    func thresholdTotalsContent(activation: StoryStreamCardActivation10868? = nil) -> TotalMilestoneThresholdLive10868? {
        guard case .thresholds(let live)? = model.totals else { return nil }
        return TotalMilestoneThresholdLive10868(
            input: live,
            onSelect: Self.relay(onTotalSelect, through: activation),
            onDetails: Self.relay(onTotalDetails, through: activation),
            timingExpanded: Self.relayBinding(totalTimingExpanded, through: activation))
    }

    func finalExactContent(activation: StoryStreamCardActivation10868? = nil) -> ExactScoreFinishPresentation10868? {
        guard case .final(let tiles)? = model.exact else { return nil }
        return ExactScoreFinishPresentation10868(
            input: tiles,
            onSelectOriginal: Self.relayPair(onExactSelect, through: activation),
            onDetails: Self.relayPair(onExactDetails, through: activation),
            onRecoverSelection: Self.relayAction(onExactRecover, through: activation))
    }

    func laneExactContent(activation: StoryStreamCardActivation10868? = nil) -> ExactScoreFinishLanePresentation10868? {
        guard case .lanes(let lanes)? = model.exact else { return nil }
        return ExactScoreFinishLanePresentation10868(
            input: lanes, onDetails: Self.relayPair(onExactDetails, through: activation))
    }

    func handicapsContent(activation: StoryStreamCardActivation10868? = nil) -> OriginalHandicapCardView9483? {
        model.handicaps.map {
            OriginalHandicapCardView9483(
                input: $0.input, tint: $0.tint,
                explanationExpanded: Self.relayBinding(handicapExplanationExpanded, through: activation),
                onSelect: Self.relay(onHandicapSelect, through: activation))
        }
    }

    /// The owner's About — content the host already holds, so no hook.
    func aboutContent() -> TennisEventPageAboutContent10868? {
        model.about.map { TennisEventPageAboutContent10868(about: $0) }
    }

    /// The existing catalogue with the owner's originals, exactly as admitted,
    /// and its select callback after the interaction hook.
    func catalogueContent() -> OriginalMarketCatalogueView9483? {
        originals.map {
            OriginalMarketCatalogueView9483(
                catalogue: $0.catalogue, selection: $0.selection, heading: $0.heading, context: $0.context,
                emptyWords: $0.emptyWords, unavailableChoice: $0.unavailableChoice, labels: $0.labels,
                tint: $0.tint, onSelect: Self.held(onOriginalSelect, by: onInteraction)
            )
        }
    }

    /// The existing Details for the owner's held selection, with its optional
    /// recorded history and its history callback after the interaction hook.
    func originalDetailsContent() -> OriginalMarketDetailsView9483? {
        originals.map {
            OriginalMarketDetailsView9483(
                catalogue: $0.catalogue, selection: $0.selection, tint: $0.tint,
                recorded: $0.recorded, onHistory: Self.held(onOriginalHistory, by: onInteraction)
            )
        }
    }

    /// Full-size content's About: the exact callback, no hook.
    func openReaderAbout() {
        aboutOpener()?()
    }

    /// The page's All props entry, after the interaction hook.
    func openAllProps() {
        guard model.allPropsAvailable(canOpen: onAllProps != nil) else { return }
        Self.heldAction(onAllProps, by: onInteraction)?()
    }

    // MARK: Page

    private var page: some View {
        VStack(alignment: .leading, spacing: 20) {
            hero
            stories
        }
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(TennisEventPageAccessibilityID10868.page)
    }

    /// The headline and the history in one panel: side by side where both fit
    /// at their minimum widths, otherwise the headline above the history.
    private var hero: some View {
        VStack(alignment: .leading, spacing: 0) {
            let arrangements = TennisEventPageModel10868.arrangements(
                sizeClass: sizeClass,
                accessibilitySize: typeSize.isAccessibilitySize
            )
            if arrangements == [.stacked] {
                heroStacked
            } else {
                ViewThatFits(in: .horizontal) {
                    heroSideBySide
                    heroStacked
                }
            }
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .modifier(TennisEventPageCardSurface10868())
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(TennisEventPageAccessibilityID10868.hero)
    }

    private var heroStacked: some View {
        VStack(alignment: .leading, spacing: 24) {
            headlineSection
            anchor
        }
    }

    private var heroSideBySide: some View {
        HStack(alignment: .top, spacing: 32) {
            headlineSection
                .frame(minWidth: headlineMinWidth, maxWidth: headlineMaxWidth, alignment: .topLeading)
            anchor
                .frame(minWidth: anchorMinWidth, maxWidth: .infinity, alignment: .topLeading)
                .layoutPriority(1)
        }
    }

    /// The headline, or the owner's words when its phase is not the page's,
    /// then the owner's status words.
    private var headlineSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            if let headline = headlineContent() {
                headline
            } else {
                Text(input.copy.headlineUnavailable)
                    .font(.subheadline)
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .accessibilityIdentifier(TennisEventPageAccessibilityID10868.headlineUnavailable)
            }
            if let notice = TennisEventPageModel10868.readable(input.notice) {
                Text(notice)
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .accessibilityIdentifier(TennisEventPageAccessibilityID10868.notice)
            }
        }
    }

    /// The history, then the held reading once the owner holds one.
    private var anchor: some View {
        VStack(alignment: .leading, spacing: 12) {
            historyContent(reader: false)
            if let reading = pageReadingContent() {
                reading
                    .accessibilityElement(children: .contain)
                    .accessibilityIdentifier(TennisEventPageAccessibilityID10868.reading)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(TennisEventPageAccessibilityID10868.anchor)
    }

    /// The owner's stream when it supplies one, then the All props entry.
    @ViewBuilder private var stories: some View {
        let allProps = model.allPropsAvailable(canOpen: onAllProps != nil)
        if input.stream != nil || allProps {
            VStack(alignment: .leading, spacing: 16) {
                if let stream = input.stream {
                    StoryStreamPresentationView10868(stream, onIntent: onStoryIntent) { card, activation in
                        storyCell(card, activation)
                    }
                    .accessibilityElement(children: .contain)
                    .accessibilityLabel(input.copy.storiesLabel)
                    .accessibilityIdentifier(TennisEventPageAccessibilityID10868.stories)
                }
                if allProps, let label = input.copy.allPropsLabel {
                    allPropsEntry(label)
                }
            }
        }
    }

    private func allPropsEntry(_ label: String) -> some View {
        Button(action: openAllProps) {
            HStack(spacing: 8) {
                Text(label)
                    .font(.body.weight(.semibold))
                    .fixedSize(horizontal: false, vertical: true)
                    .frame(maxWidth: .infinity, alignment: .leading)
                Image(systemName: "chevron.right")
                    .font(.body.weight(.semibold))
                    .accessibilityHidden(true)
            }
            .foregroundStyle(DS.blue)
            .padding(.horizontal, 16)
            .frame(minHeight: controlSize)
            .modifier(TennisEventPageCardSurface10868())
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityIdentifier(TennisEventPageAccessibilityID10868.allProps)
    }

    /// The story the owner links to this stream card, with the stream's
    /// activation hook and the owner's reason words, or the owner's
    /// unavailable words.
    @ViewBuilder private func storyCell(_ card: Stream.Card, _ activation: StoryStreamCardActivation10868) -> some View {
        if let link = model.story(card.id) {
            VStack(alignment: .leading, spacing: 8) {
                if let reason = TennisEventPageModel10868.readable(link.reason) {
                    Text(reason)
                        .font(.subheadline)
                        .foregroundStyle(DS.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
                cardContent(link.card, activation: activation)
            }
            .padding(16)
            .frame(maxWidth: .infinity, alignment: .leading)
            .modifier(TennisEventPageCardSurface10868())
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier(TennisEventPageAccessibilityID10868.card(link.card))
        } else {
            Text(input.copy.storyUnavailable)
                .font(.subheadline)
                .foregroundStyle(DS.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
                .frame(maxWidth: .infinity, minHeight: 120, alignment: .leading)
                .padding(16)
                .modifier(TennisEventPageCardSurface10868())
                .accessibilityIdentifier(TennisEventPageAccessibilityID10868.unavailable)
        }
    }

    // MARK: Content shared by the page and the reader

    @ViewBuilder private func cardContent(_ card: TennisEventPageCard10868,
                                          activation: StoryStreamCardActivation10868?) -> some View {
        switch card {
        case .history: historyReader
        case .sets: setsContent(activation: activation)
        case .totals: totalsContent(activation: activation)
        case .exact: exactContent(activation: activation)
        case .handicaps: handicapsContent(activation: activation)
        }
    }

    /// The full-size history, then its dated reading.
    private var historyReader: some View {
        VStack(alignment: .leading, spacing: 16) {
            historyContent(reader: true)
            if let reading = readerReadingContent() {
                reading
                    .accessibilityElement(children: .contain)
                    .accessibilityIdentifier(TennisEventPageAccessibilityID10868.reading)
            }
        }
    }

    @ViewBuilder private func totalsContent(activation: StoryStreamCardActivation10868?) -> some View {
        if let line = finalTotalsContent(activation: activation) {
            line
        } else if let thresholds = thresholdTotalsContent(activation: activation) {
            thresholds
        }
    }

    @ViewBuilder private func exactContent(activation: StoryStreamCardActivation10868?) -> some View {
        if let tiles = finalExactContent(activation: activation) {
            tiles
        } else if let lanes = laneExactContent(activation: activation) {
            lanes
        }
    }

    /// The same leaf and input, full size, for the host's existing reader,
    /// under the compact match words. A card this phase does not show has no
    /// content.
    @ViewBuilder private func reader(_ card: TennisEventPageCard10868) -> some View {
        if model.readerShows(card) {
            VStack(alignment: .leading, spacing: 16) {
                compactHeader
                cardContent(card, activation: nil)
            }
        }
    }

    /// The owner's one-line match words and, in full-size content, the About
    /// entry.
    private var compactHeader: some View {
        HStack(alignment: .top, spacing: 12) {
            VStack(alignment: .leading, spacing: 4) {
                Text(input.reader.title)
                    .font(.headline)
                    .foregroundStyle(DS.textPrimary)
                    .accessibilityAddTraits(.isHeader)
                if let state = TennisEventPageModel10868.readable(input.reader.state) {
                    Text(state)
                        .font(.subheadline)
                        .foregroundStyle(DS.textSecondary)
                }
            }
            .fixedSize(horizontal: false, vertical: true)
            .frame(maxWidth: .infinity, alignment: .leading)
            if model.aboutEntry(mode: mode, canOpen: onAbout != nil) {
                Button(action: openReaderAbout) {
                    Image(systemName: "info.circle")
                        .font(.title3)
                        .foregroundStyle(DS.textPrimary)
                        .frame(minWidth: controlSize, minHeight: controlSize)
                        .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .accessibilityLabel(input.headline.copy.aboutLabel)
                .accessibilityHint(input.headline.copy.aboutHint ?? "")
                .accessibilityIdentifier(TennisEventPageAccessibilityID10868.readerAbout)
            }
        }
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(TennisEventPageAccessibilityID10868.readerHeader)
    }

    // MARK: All props, the held original's Details and About

    /// The owner's admitted originals under the compact match words.
    @ViewBuilder private var catalogueMode: some View {
        if let catalogue = catalogueContent() {
            VStack(alignment: .leading, spacing: 12) {
                compactHeader
                catalogue
            }
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier(TennisEventPageAccessibilityID10868.catalogue)
        }
    }

    /// The held original's existing Details, for the host's container.
    @ViewBuilder private var originalMode: some View {
        if let details = originalDetailsContent() {
            details
                .accessibilityElement(children: .contain)
                .accessibilityIdentifier(TennisEventPageAccessibilityID10868.original)
        }
    }

    /// The owner's About under the compact match words, for the host's container.
    @ViewBuilder private var aboutMode: some View {
        if let content = aboutContent() {
            VStack(alignment: .leading, spacing: 12) {
                compactHeader
                content
            }
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier(TennisEventPageAccessibilityID10868.about)
        }
    }
}

/// The reference's white card on the page surface.
private struct TennisEventPageCardSurface10868: ViewModifier {
    func body(content: Content) -> some View {
        content
            .background(DS.cardBg, in: RoundedRectangle(cornerRadius: 20, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 20, style: .continuous).stroke(DS.border, lineWidth: 1))
    }
}
