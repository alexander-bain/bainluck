import SwiftUI

// #10868 — the racing event screen (`racing-live`): one native presentation
// composed from the accepted leaves. Win chances lead. A fan sees, in this
// order: the race headline (the owner's eyebrow, title and About entry, each
// displayed driver's named chances for the phase, the race state with its own
// report clock and the reported progress), the drivers' win history front and
// centre, then the owner's story stream — win and podium chances; during the
// race how expectations shifted and the chase; at the final how pre-race
// expectations met the classification — and the "All props" entry. The history
// and each story open as full-size content made of the same Views, and "All
// props", the selected original's Details and each About are further content
// modes.
//
// Presentation only, composed from the approved `RacingLive.tsx` /
// `racingLive.css` / `racingHistoryReader.css` and `RacingPodiumPaths.tsx` /
// `racingPodiumPaths.css`, over `racingLifecycle.ts`, `racingLiveEvidence.ts`
// and `racingMomentStories.ts`, as mounted in `Atlas.tsx` (`racing-live`).
// The reference's fixture loaders, trade cleaning and five-minute replay
// eligibility, baseline election, `raceStoryOrder` ranking and its reasons,
// moment controls, story and reader session state, inspection pinning, "Aa
// Larger", sheets, dialogs and focus restoration are NOT ported. The leaves
// are the actual accepted Views:
//
//   • `FieldPhaseHeadlinePresentation10868` — the race headline, and the
//     owner's compact win chances under the chase and win/podium readers;
//   • `FieldProbabilityHistoryPresentation10868` — the anchor;
//   • `FieldWinPodiumPresentation10868` — win and podium chances;
//   • `FieldExpectationsPresentation10868` — how expectations shifted;
//   • `FieldChasePresentation10868` — the chase;
//   • `FieldFinishComparisonPresentation10868` — expectation and finish;
//   • `StoryStreamPresentationView10868` — the controlled story stream;
//   • `OriginalMarketCatalogueView9483` / `OriginalMarketDetailsView9483` —
//     "All props" and the selected original's Details.
//
// Nothing new is drawn here beyond arrangement, card surfaces, the owner's
// story words, the compact reader heading and the About text.
//
// The page's phase is the owner's explicit `FieldOutlookPhase10868`, never
// read from a lap, a clock or a result. A leaf is mounted only when its own
// phase is the page's, and the story cards only where the reference offers
// them: win and podium in every phase; expectations and the chase during the
// race; expectation and finish at the final. A leaf from another phase is not
// coerced into this one — it is not mounted, and a headline from another
// phase shows the owner's unavailable words. Every winner and podium contract
// is an independent original with its own clock: this layer never normalizes
// the drivers' chances, joins a win chance to a podium chance, treats a
// missing value as zero, turns a final classification into a 0/100 quote,
// reads a contract's Won/Lost from a position, or promotes a stale trade to a
// current headline. Each leaf keeps its own rules for that.
//
// The host supplies each leaf's own immutable input, already admitted for the
// same snapshot; this layer groups them and never re-elects, copies, filters
// or formats an observation, a report, a marker or a result. The history keeps
// every original's name, shape, own values and times, its independent runs,
// window, scale, inspection and source controls; its domain, range, segments
// and markers are the owner's.
//
// The story stream is the owner's: its cards, order, primary, companion,
// position, status, pending, playback, progress, previous/next, scope and
// reader-open flag, and its own "Open full card" entry. This layer wires each
// supplied card id to the one story the owner names for it, and shows the
// owner's unavailable words for an id that names no single story this phase
// mounts — never a neighbour. A card's own actions — choosing a driver pair,
// opening an original, opening a driver's history, opening the win/podium
// About — first call the stream's activation hook (so the owner can hold) and
// then the host's exact callback. None of these leaves takes a disclosure
// binding. Building a card asks for nothing. Full-size content reuses the same
// leaves with the host's exact callbacks and no activation, so opening a card
// never requests a hold by appearing, and closing one resumes nothing.
//
// The owner may also pass an interaction hook, so it can hold its stream
// before an action outside the stream lands (the reference holds the stream on
// a pointer-down or focus in its hero and originals panels). On the page — a
// headline driver's open and the headline's About, the anchor history's
// actions, inspection choices and plot taps, the All props entry — and in the
// catalogue and Details content — a category, Show more, an original's
// selection, a Details history control — the action calls that hook once and
// then the owner's exact callback with its exact value. Without a callback
// there is no action and no hook call; without a hook every callback is the
// owner's own, as before. Building or reading the view calls nothing, and
// there is no resume. Full-size content, including the race About in its
// compact heading, keeps the exact callbacks: its host already holds the
// stream while it is open. Stream cards keep the stream's own activation and
// never pass through the hook as well. A pointer-down on empty panel space,
// or focus moving into a panel, is not intercepted here; that stays with the
// host's containment.
//
// The full-size history is the same history input with its expanded layout
// and without its expand control; every series, guide, selection, readout,
// window, scale, inspection and other control is unchanged.
//
// Each About is the owner's text, reached only through the leaf's own About
// control (the headline's for the race, the win/podium card's for its
// comparison) and through the readers' compact heading. With no About text or
// no callback, the leaf draws no About control and keeps its own words.
//
// All props carries the owner's category controls (Winner, Podium, Matchups,
// Fastest lap) above the existing catalogue, and its count words and Show
// more below. The catalogue holds exactly the rows the owner admits for its
// current category and page, in its order. Nothing here filters, groups,
// slices or pages them, or clears or elects a held original when the category
// changes: each control hands back the owner's exact intent id. A control
// without readable words is not drawn; without a callback, or unavailable, it
// is static words, never a button. The categories wrap in an adaptive grid
// and stack one per row at accessibility sizes, each at least 44 pt tall.
//
// Phone stacks the headline above the history, then the stories. A regular
// or unspecified size class (a Mac window) places the headline beside the
// history while both keep their minimum widths, otherwise it stacks too;
// accessibility sizes always stack. The stories run full width below.
//
// The host owns the scroll, navigation, sheets, Back/Done, paging and swipe,
// focus, routing to and from the catalogue, an original's Details and each
// About, the catalogue's category and page, the selected driver and podium
// pair, the held/received frame, how a hook request holds the stream, live
// subscriptions and every genuine update. This view keeps no state, runs no
// timer or animation, holds no subscription and presents no sheet or
// navigation of its own. Every callback is the host's own closure handed to
// the leaf unchanged. With no callback, nothing pretends to act.
//
// Host binding still owed — not available at this base: an owner that admits,
// for one race snapshot, the phase, the headline, the history with its report
// guides at or before that snapshot, each story leaf's input, the reader
// heading and compact chances, the story stream and its card-to-story map, the
// About text, the originals group, and maps every callback to its existing
// controls — including from a win/podium original's exact
// `FieldChooserOriginalRef10868` to the Details selection it names.

/// One card the page can show full size. `history` is the anchor.
nonisolated enum RacingEventPageCard10868: String, Hashable, CaseIterable {
    case history
    case winPodium
    case expectations
    case chase
    case finish
}

/// Which owner About a control opens.
nonisolated enum RacingEventPageAboutTopic10868: String, Hashable, CaseIterable {
    /// The headline's About: how the race was recorded.
    case race
    /// The win/podium card's About: how to read the comparison.
    case winPodium
}

/// What the host's container is showing, chosen by the host.
nonisolated enum RacingEventPageMode10868: Equatable {
    /// The race screen body.
    case page
    /// One card's full-size content.
    case reader(RacingEventPageCard10868)
    /// Every retained original ("All props").
    case catalogue
    /// The held original's Details.
    case original
    /// One owner About.
    case about(RacingEventPageAboutTopic10868)
}

nonisolated enum RacingEventPageArrangement10868: Equatable {
    case stacked
    case sideBySide
}

// MARK: - Page input

/// The owner's one-line race words above full-size content.
nonisolated struct RacingEventPageReaderHeader10868: Equatable {
    /// "Singapore · Lap 52/62 report".
    let title: String
    /// "Verstappen leads · Leclerc +9.1s"; nil draws none.
    let state: String?
}

/// The owner's compact win chances under the chase and win/podium readers.
nonisolated struct RacingEventPageReaderChances10868: Equatable {
    /// "Race win chances", "Race results and pre-race chances".
    let heading: String
    /// The owner's headline input for this context — typically without its
    /// eyebrow, title and state. Mounted only at the page's own phase.
    let headline: FieldHeadlineInput10868
}

/// The owner's link from one stream card id to the story it shows.
nonisolated struct RacingEventPageStory10868: Equatable {
    /// Exactly as in `StoryStreamPresentation10868.cards`.
    let cardID: String
    let card: RacingEventPageCard10868
    /// The owner's words for why this story is here ("Leclerc closed 5.9
    /// seconds since the lap 46 report."); nil draws none.
    var reason: String? = nil
}

/// One owner About, verbatim.
nonisolated struct RacingEventPageAbout10868: Equatable {
    /// "Recorded race, separate clocks".
    let title: String
    let paragraphs: [String]
}

nonisolated struct RacingEventPageCopy10868: Equatable {
    /// Spoken name of the stories group ("Race stories").
    let storiesLabel: String
    /// Shown in a stream cell whose id names no single story this phase shows.
    let storyUnavailable: String
    /// Shown in place of a headline whose phase is not the page's.
    let headlineUnavailable: String
    /// "All 75 original outcomes"; nil draws no entry.
    let allPropsLabel: String?
}

nonisolated struct RacingEventPageInput10868: Equatable {
    let phase: FieldOutlookPhase10868
    let reader: RacingEventPageReaderHeader10868
    let headline: FieldHeadlineInput10868
    let history: FieldHistoryInput10868
    let winPodium: FieldPodiumInput10868?
    /// During the race only.
    let expectations: FieldExpectationsInput10868?
    /// During the race only.
    let chase: FieldChaseInput10868?
    /// At the final only.
    let finish: FieldFinishInput10868?
    let readerChances: RacingEventPageReaderChances10868?
    let stream: StoryStreamPresentation10868
    let stories: [RacingEventPageStory10868]
    /// Opened by the headline's About control; nil: no control.
    let raceAbout: RacingEventPageAbout10868?
    /// Opened by the win/podium card's About control; nil: no control.
    let winPodiumAbout: RacingEventPageAbout10868?
    let copy: RacingEventPageCopy10868
}

/// One owner category above "All props" ("Winner"): its exact intent id,
/// words and availability, and whether the owner has it selected.
nonisolated struct RacingEventPageCatalogueCategory10868: Equatable {
    let action: FieldHistoryAction10868
    let isSelected: Bool
}

/// The owner's controls around "All props". Which originals the catalogue
/// holds — the category's rows, their order and how many — is the owner's;
/// these controls only hand back its intents.
nonisolated struct RacingEventPageCatalogueControls10868: Equatable {
    /// Spoken name of the category group ("Race market category").
    let categoriesLabel: String
    let categories: [RacingEventPageCatalogueCategory10868]
    /// "Show more · 14 remaining"; nil draws none.
    var more: FieldHistoryAction10868? = nil
    /// "Showing 6 of 20 winner outcomes"; nil draws none.
    var context: String? = nil
}

nonisolated enum RacingEventPageControlArrangement10868: Equatable {
    /// An adaptive grid: as many equal columns as fit, wrapping onto new rows.
    case wrapping
    /// One full-width control per row.
    case stacked
}

/// The owner's retained originals behind "All props", for the catalogue and
/// Details modes. Every field reaches the existing leaves unchanged.
struct RacingEventPageOriginals10868 {
    /// The latest admitted originals for one scope; nil shows `emptyWords`.
    let catalogue: OriginalMarketDetails9483.Catalogue?
    /// The owner's held selection; nil holds none.
    let selection: OriginalMarketDetails9483.Selection?
    /// The selected original's recorded history; nil keeps its Details summary.
    var recorded: OriginalMarketDetails9483.RecordedHistory? = nil
    /// The owner's card label for an exact identity; otherwise its title.
    var labels: [OriginalMarketDetails9483.Identity: String] = [:]
    /// "All props".
    let heading: String
    /// "75 retained originals"; nil draws none.
    var context: String? = nil
    /// "No retained originals for this race".
    let emptyWords: String
    /// The label for an original with no readable title of its own.
    let unavailableChoice: String
    let tint: Color
    /// The category, count and Show more controls; nil draws none.
    var controls: RacingEventPageCatalogueControls10868? = nil
}

nonisolated enum RacingEventPageAccessibilityID10868 {
    static let page = "racingEventPage10868.page"
    static let hero = "racingEventPage10868.hero"
    static let headlineUnavailable = "racingEventPage10868.headline.unavailable"
    static let anchor = "racingEventPage10868.anchor"
    static let stories = "racingEventPage10868.stories"
    static let allProps = "racingEventPage10868.allProps"
    static let unavailable = "racingEventPage10868.story.unavailable"
    static let readerHeader = "racingEventPage10868.readerHeader"
    static let readerAbout = "racingEventPage10868.readerHeader.about"
    static let readerChances = "racingEventPage10868.readerChances"
    static let catalogue = "racingEventPage10868.catalogue"
    static let original = "racingEventPage10868.original"
    static let categories = "racingEventPage10868.catalogue.categories"
    static let catalogueContext = "racingEventPage10868.catalogue.context"
    static let more = "racingEventPage10868.catalogue.more"
    static func category(_ id: String) -> String { "racingEventPage10868.catalogue.category.\(id)" }
    static func card(_ card: RacingEventPageCard10868) -> String { "racingEventPage10868.card.\(card.rawValue)" }
    static func about(_ topic: RacingEventPageAboutTopic10868) -> String { "racingEventPage10868.about.\(topic.rawValue)" }
}

// MARK: - Page model

/// Which leaves the page mounts, resolved once per input.
nonisolated struct RacingEventPageModel10868: Equatable {
    let input: RacingEventPageInput10868

    init(_ input: RacingEventPageInput10868) {
        self.input = input
    }

    /// The headline at the page's own phase. Otherwise nothing.
    var headline: FieldHeadlineInput10868? {
        input.headline.phase == input.phase ? input.headline : nil
    }

    /// Win and podium chances at the page's own phase.
    var winPodium: FieldPodiumInput10868? {
        guard let winPodium = input.winPodium, winPodium.phase == input.phase else { return nil }
        return winPodium
    }

    /// How expectations shifted: during the race, at that phase.
    var expectations: FieldExpectationsInput10868? {
        guard input.phase == .during, let expectations = input.expectations, expectations.phase == .during else { return nil }
        return expectations
    }

    /// The chase: during the race, at that phase.
    var chase: FieldChaseInput10868? {
        guard input.phase == .during, let chase = input.chase, chase.phase == .during else { return nil }
        return chase
    }

    /// Expectation and finish: at the final, at that phase.
    var finish: FieldFinishInput10868? {
        guard input.phase == .final, let finish = input.finish, finish.phase == .final else { return nil }
        return finish
    }

    func isMounted(_ card: RacingEventPageCard10868) -> Bool {
        switch card {
        case .history: true
        case .winPodium: winPodium != nil
        case .expectations: expectations != nil
        case .chase: chase != nil
        case .finish: finish != nil
        }
    }

    /// The owner's link a stream card id names: exactly one link with that
    /// id, to a story this phase mounts. Otherwise nothing.
    func story(_ cardID: String) -> RacingEventPageStory10868? {
        let links = input.stories.filter { $0.cardID == cardID }
        guard links.count == 1, let link = links.first, link.card != .history, isMounted(link.card) else { return nil }
        return link
    }

    func storyCard(_ cardID: String) -> RacingEventPageCard10868? { story(cardID)?.card }

    /// Full-size content exists for the anchor and for a story this phase shows.
    func readerShows(_ card: RacingEventPageCard10868) -> Bool { isMounted(card) }

    /// The owner's compact chances under the chase and win/podium readers, at
    /// the page's own phase. Nothing under any other card.
    func readerChances(for card: RacingEventPageCard10868) -> RacingEventPageReaderChances10868? {
        guard card == .chase || card == .winPodium, readerShows(card),
              let chances = input.readerChances, chances.headline.phase == input.phase else { return nil }
        return chances
    }

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

    // MARK: About and entries

    /// The owner's About for a topic, when it carries readable words.
    func about(_ topic: RacingEventPageAboutTopic10868) -> RacingEventPageAbout10868? {
        let supplied = switch topic {
        case .race: input.raceAbout
        case .winPodium: input.winPodiumAbout
        }
        guard let about = supplied,
              Self.readable(about.title) != nil || about.paragraphs.contains(where: { Self.readable($0) != nil })
        else { return nil }
        return about
    }

    func aboutAvailable(_ topic: RacingEventPageAboutTopic10868, canOpen: Bool) -> Bool {
        canOpen && about(topic) != nil
    }

    /// Whether `mode`'s compact heading shows the race About entry: full-size
    /// content only — the page has the headline's own control.
    func aboutEntry(mode: RacingEventPageMode10868, canOpen: Bool) -> Bool {
        guard case .reader = mode, Self.readable(input.headline.copy.aboutLabel) != nil else { return false }
        return aboutAvailable(.race, canOpen: canOpen)
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
    static func arrangements(sizeClass: UserInterfaceSizeClass?, accessibilitySize: Bool) -> [RacingEventPageArrangement10868] {
        sizeClass != .compact && !accessibilitySize ? [.sideBySide, .stacked] : [.stacked]
    }

    // MARK: Catalogue controls

    /// Every catalogue control's action, in one id space.
    static func catalogueActions(_ controls: RacingEventPageCatalogueControls10868) -> [FieldHistoryAction10868] {
        controls.categories.map(\.action) + [controls.more].compactMap { $0 }
    }

    /// Not drawn without readable words. A button handing back this exact id
    /// only with a callback, when available, and when its id is nonempty and
    /// unique among the controls; otherwise static words.
    static func catalogueControlState(_ action: FieldHistoryAction10868?,
                                      in controls: RacingEventPageCatalogueControls10868,
                                      hasCallback: Bool) -> FieldHistoryControlState10868 {
        guard let action, readable(action.label) != nil else { return .hidden }
        guard hasCallback, action.isAvailable, !action.id.isEmpty,
              catalogueActions(controls).filter({ $0.id == action.id }).count == 1
        else { return .shownStatic }
        return .live(id: action.id)
    }

    /// The categories drawn, in the owner's order.
    static func shownCategories(_ controls: RacingEventPageCatalogueControls10868,
                                hasCallback: Bool) -> [RacingEventPageCatalogueCategory10868] {
        controls.categories.filter { catalogueControlState($0.action, in: controls, hasCallback: hasCallback) != .hidden }
    }

    /// Accessibility sizes stack the categories one per row; every other size
    /// wraps them, never a squeezed single row.
    static func categoryArrangement(accessibilitySize: Bool) -> RacingEventPageControlArrangement10868 {
        accessibilitySize ? .stacked : .wrapping
    }
}

// MARK: - About content

/// One owner About in its own words. Static text; it acts on nothing.
struct RacingEventPageAboutContent10868: View {
    let about: RacingEventPageAbout10868

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            if let title = RacingEventPageModel10868.readable(about.title) {
                Text(title)
                    .font(.headline)
                    .foregroundStyle(DS.textPrimary)
                    .accessibilityAddTraits(.isHeader)
            }
            ForEach(Array(about.paragraphs.enumerated()), id: \.offset) { _, paragraph in
                if let words = RacingEventPageModel10868.readable(paragraph) {
                    Text(words)
                        .font(.body)
                        .foregroundStyle(DS.textPrimary)
                }
            }
        }
        .fixedSize(horizontal: false, vertical: true)
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

// MARK: - Page view

struct RacingEventPagePresentation10868: View {
    typealias Stream = StoryStreamPresentation10868

    let input: RacingEventPageInput10868
    var mode: RacingEventPageMode10868 = .page
    /// The catalogue and Details modes' content; nil: neither has any.
    var originals: RacingEventPageOriginals10868? = nil
    /// Opens the host's container on the owner's About for the topic.
    var onAbout: ((RacingEventPageAboutTopic10868) -> Void)? = nil
    /// Opens the host's existing catalogue.
    var onAllProps: (() -> Void)? = nil
    /// A catalogue card's exact selection, for the host to hold and route.
    var onOriginalSelect: ((OriginalMarketDetails9483.Selection) -> Void)? = nil
    /// A Details history control's exact intent, for the host to route.
    var onOriginalHistory: ((OriginalMarketDetails9483.HistoryIntent) -> Void)? = nil
    var onStoryIntent: ((Stream.Intent) -> Void)? = nil
    /// A headline driver's exact open, for the host's history.
    var onHeadlineOpen: ((FieldMovementOpen10868) -> Void)? = nil
    var onHistoryAction: ((String) -> Void)? = nil
    var onHistoryInspectionChoice: ((String) -> Void)? = nil
    var onHistoryPlotPosition: ((Double) -> Void)? = nil
    /// The owner's exact pair id, for the host to select.
    var onWinPodiumChoosePair: ((String) -> Void)? = nil
    /// The exact win or podium original, for the host's Details.
    var onWinPodiumOpenOriginal: ((FieldChooserOriginalRef10868) -> Void)? = nil
    var onExpectationsOpen: ((FieldMovementOpen10868) -> Void)? = nil
    var onChaseOpenHistory: ((FieldChooserOriginalRef10868) -> Void)? = nil
    var onFinishOpenHistory: ((FieldChooserOriginalRef10868) -> Void)? = nil
    /// A category's exact intent id, for the host to choose its rows.
    var onCatalogueCategory: ((String) -> Void)? = nil
    /// Show more's exact intent id, for the host to admit its next rows.
    var onCatalogueMore: ((String) -> Void)? = nil
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
    @ScaledMetric(relativeTo: .body) private var categoryMinWidth: CGFloat = 120

    private var model: RacingEventPageModel10868 { RacingEventPageModel10868(input) }

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

    /// The same for an action without a value (the win/podium About).
    static func relayAction(_ action: (() -> Void)?,
                            through activation: StoryStreamCardActivation10868?) -> (() -> Void)? {
        guard let action else { return nil }
        guard let activation else { return action }
        return {
            activation.request()
            action()
        }
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
            case .about(let topic): aboutMode(topic)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    // MARK: Leaves — the actual Views, each with the host's own callbacks

    /// The host's opener for a topic's About; nil without readable About text
    /// or without a callback, so the leaf draws no About control.
    func aboutOpener(_ topic: RacingEventPageAboutTopic10868) -> (() -> Void)? {
        guard model.aboutAvailable(topic, canOpen: onAbout != nil), let onAbout else { return nil }
        return { onAbout(topic) }
    }

    /// The race headline, at the page's phase only. Its open and About pass
    /// the interaction hook first.
    func headlineContent() -> FieldPhaseHeadlinePresentation10868? {
        model.headline.map {
            FieldPhaseHeadlinePresentation10868(input: $0, onAbout: Self.heldAction(aboutOpener(.race), by: onInteraction),
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

    /// `activation` is the stream's hook for a card in the stream; nil in
    /// full-size content.
    func winPodiumContent(activation: StoryStreamCardActivation10868? = nil) -> FieldWinPodiumPresentation10868? {
        model.winPodium.map {
            FieldWinPodiumPresentation10868(
                input: $0,
                onChoosePair: Self.relay(onWinPodiumChoosePair, through: activation),
                onOpenOriginal: Self.relay(onWinPodiumOpenOriginal, through: activation),
                onAbout: Self.relayAction(aboutOpener(.winPodium), through: activation)
            )
        }
    }

    func expectationsContent(activation: StoryStreamCardActivation10868? = nil) -> FieldExpectationsPresentation10868? {
        model.expectations.map {
            FieldExpectationsPresentation10868(input: $0, onOpen: Self.relay(onExpectationsOpen, through: activation))
        }
    }

    func chaseContent(activation: StoryStreamCardActivation10868? = nil) -> FieldChasePresentation10868? {
        model.chase.map {
            FieldChasePresentation10868(input: $0, onOpenHistory: Self.relay(onChaseOpenHistory, through: activation))
        }
    }

    func finishContent(activation: StoryStreamCardActivation10868? = nil) -> FieldFinishComparisonPresentation10868? {
        model.finish.map {
            FieldFinishComparisonPresentation10868(input: $0, onOpenHistory: Self.relay(onFinishOpenHistory, through: activation))
        }
    }

    /// The owner's compact chances under a reader: static, no control.
    func readerChancesContent(_ card: RacingEventPageCard10868) -> FieldPhaseHeadlinePresentation10868? {
        model.readerChances(for: card).map { FieldPhaseHeadlinePresentation10868(input: $0.headline) }
    }

    /// The owner's About for a topic, as static content.
    func aboutContent(_ topic: RacingEventPageAboutTopic10868) -> RacingEventPageAboutContent10868? {
        model.about(topic).map { RacingEventPageAboutContent10868(about: $0) }
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

    /// The existing Details for the owner's held selection, with its recorded
    /// history and its history callback after the interaction hook.
    func originalDetailsContent() -> OriginalMarketDetailsView9483? {
        originals.map {
            OriginalMarketDetailsView9483(
                catalogue: $0.catalogue, selection: $0.selection, tint: $0.tint,
                recorded: $0.recorded, onHistory: Self.held(onOriginalHistory, by: onInteraction)
            )
        }
    }

    /// A catalogue control's exact owner intent after the interaction hook;
    /// nil when it is not a live control.
    private func catalogueAction(_ action: FieldHistoryAction10868?, _ callback: ((String) -> Void)?) -> (() -> Void)? {
        guard let controls = originals?.controls,
              case .live(let id) = RacingEventPageModel10868.catalogueControlState(action, in: controls, hasCallback: callback != nil),
              let send = Self.held(callback, by: onInteraction)
        else { return nil }
        return { send(id) }
    }

    func categoryAction(_ category: RacingEventPageCatalogueCategory10868) -> (() -> Void)? {
        catalogueAction(category.action, onCatalogueCategory)
    }

    func moreAction() -> (() -> Void)? {
        catalogueAction(originals?.controls?.more, onCatalogueMore)
    }

    /// Full-size content's race About: the exact callback, no hook.
    func openAbout(_ topic: RacingEventPageAboutTopic10868) {
        aboutOpener(topic)?()
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
        .accessibilityIdentifier(RacingEventPageAccessibilityID10868.page)
    }

    /// The headline and the history in one panel: side by side where both fit
    /// at their minimum widths, otherwise the headline above the history.
    private var hero: some View {
        VStack(alignment: .leading, spacing: 0) {
            let arrangements = RacingEventPageModel10868.arrangements(
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
        .modifier(RacingEventPageCardSurface10868())
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(RacingEventPageAccessibilityID10868.hero)
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

    /// The headline, or the owner's words when its phase is not the page's.
    @ViewBuilder private var headlineSection: some View {
        if let headline = headlineContent() {
            headline
        } else {
            Text(input.copy.headlineUnavailable)
                .font(.subheadline)
                .foregroundStyle(DS.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
                .frame(maxWidth: .infinity, alignment: .leading)
                .accessibilityIdentifier(RacingEventPageAccessibilityID10868.headlineUnavailable)
        }
    }

    private var anchor: some View {
        historyContent(reader: false)
            .frame(maxWidth: .infinity, alignment: .leading)
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier(RacingEventPageAccessibilityID10868.anchor)
    }

    private var stories: some View {
        VStack(alignment: .leading, spacing: 16) {
            StoryStreamPresentationView10868(input.stream, onIntent: onStoryIntent) { card, activation in
                storyCell(card, activation)
            }
            if model.allPropsAvailable(canOpen: onAllProps != nil), let label = input.copy.allPropsLabel {
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
                    .modifier(RacingEventPageCardSurface10868())
                    .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .accessibilityIdentifier(RacingEventPageAccessibilityID10868.allProps)
            }
        }
        .accessibilityElement(children: .contain)
        .accessibilityLabel(input.copy.storiesLabel)
        .accessibilityIdentifier(RacingEventPageAccessibilityID10868.stories)
    }

    /// The story the owner links to this stream card, with the stream's
    /// activation hook and the owner's reason words, or the owner's
    /// unavailable words.
    @ViewBuilder private func storyCell(_ card: Stream.Card, _ activation: StoryStreamCardActivation10868) -> some View {
        if let link = model.story(card.id) {
            VStack(alignment: .leading, spacing: 8) {
                if let reason = RacingEventPageModel10868.readable(link.reason) {
                    Text(reason)
                        .font(.subheadline)
                        .foregroundStyle(DS.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
                cardContent(link.card, activation: activation)
            }
            .padding(16)
            .frame(maxWidth: .infinity, alignment: .leading)
            .modifier(RacingEventPageCardSurface10868())
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier(RacingEventPageAccessibilityID10868.card(link.card))
        } else {
            Text(input.copy.storyUnavailable)
                .font(.subheadline)
                .foregroundStyle(DS.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
                .frame(maxWidth: .infinity, minHeight: 120, alignment: .leading)
                .padding(16)
                .modifier(RacingEventPageCardSurface10868())
                .accessibilityIdentifier(RacingEventPageAccessibilityID10868.unavailable)
        }
    }

    // MARK: Content shared by the page and the reader

    @ViewBuilder private func cardContent(_ card: RacingEventPageCard10868,
                                          activation: StoryStreamCardActivation10868?) -> some View {
        switch card {
        case .history: historyContent(reader: true)
        case .winPodium: winPodiumContent(activation: activation)
        case .expectations: expectationsContent(activation: activation)
        case .chase: chaseContent(activation: activation)
        case .finish: finishContent(activation: activation)
        }
    }

    /// The same leaf and input, full size, for the host's existing reader,
    /// under the compact race words. The chase and win/podium readers also
    /// carry the owner's compact chances. A card this phase does not show has
    /// no content.
    @ViewBuilder private func reader(_ card: RacingEventPageCard10868) -> some View {
        if model.readerShows(card) {
            VStack(alignment: .leading, spacing: 16) {
                compactHeader
                cardContent(card, activation: nil)
                if let chances = model.readerChances(for: card), let content = readerChancesContent(card) {
                    VStack(alignment: .leading, spacing: 8) {
                        Text(chances.heading)
                            .font(.headline)
                            .foregroundStyle(DS.textPrimary)
                            .fixedSize(horizontal: false, vertical: true)
                            .accessibilityAddTraits(.isHeader)
                        content
                    }
                    .padding(.top, 16)
                    .overlay(alignment: .top) { Rectangle().fill(DS.border).frame(height: 1) }
                    .accessibilityElement(children: .contain)
                    .accessibilityIdentifier(RacingEventPageAccessibilityID10868.readerChances)
                }
            }
        }
    }

    /// The owner's one-line race words and, in full-size content, the race
    /// About entry.
    private var compactHeader: some View {
        HStack(alignment: .top, spacing: 12) {
            VStack(alignment: .leading, spacing: 4) {
                Text(input.reader.title)
                    .font(.headline)
                    .foregroundStyle(DS.textPrimary)
                    .accessibilityAddTraits(.isHeader)
                if let state = RacingEventPageModel10868.readable(input.reader.state) {
                    Text(state)
                        .font(.subheadline)
                        .foregroundStyle(DS.textSecondary)
                }
            }
            .fixedSize(horizontal: false, vertical: true)
            .frame(maxWidth: .infinity, alignment: .leading)
            if model.aboutEntry(mode: mode, canOpen: onAbout != nil) {
                Button { openAbout(.race) } label: {
                    Image(systemName: "info.circle")
                        .font(.title3)
                        .foregroundStyle(DS.textPrimary)
                        .frame(minWidth: controlSize, minHeight: controlSize)
                        .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .accessibilityLabel(input.headline.copy.aboutLabel)
                .accessibilityHint(input.headline.copy.aboutHint ?? "")
                .accessibilityIdentifier(RacingEventPageAccessibilityID10868.readerAbout)
            }
        }
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(RacingEventPageAccessibilityID10868.readerHeader)
    }

    // MARK: All props, the selected original's Details and About

    /// The owner's admitted originals under the compact race words, with the
    /// owner's categories above and its count words and Show more below.
    @ViewBuilder private var catalogueMode: some View {
        if let catalogue = catalogueContent() {
            VStack(alignment: .leading, spacing: 12) {
                compactHeader
                if let controls = originals?.controls {
                    categoryControls(controls)
                }
                catalogue
                if let controls = originals?.controls {
                    pagingControls(controls)
                }
            }
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier(RacingEventPageAccessibilityID10868.catalogue)
        }
    }

    @ViewBuilder private func categoryControls(_ controls: RacingEventPageCatalogueControls10868) -> some View {
        let shown = RacingEventPageModel10868.shownCategories(controls, hasCallback: onCatalogueCategory != nil)
        if !shown.isEmpty {
            Group {
                switch RacingEventPageModel10868.categoryArrangement(accessibilitySize: typeSize.isAccessibilitySize) {
                case .wrapping:
                    LazyVGrid(columns: [GridItem(.adaptive(minimum: categoryMinWidth), spacing: 8, alignment: .topLeading)],
                              alignment: .leading, spacing: 8) {
                        ForEach(Array(shown.enumerated()), id: \.offset) { _, category in categoryControl(category) }
                    }
                case .stacked:
                    VStack(alignment: .leading, spacing: 8) {
                        ForEach(Array(shown.enumerated()), id: \.offset) { _, category in categoryControl(category) }
                    }
                }
            }
            .accessibilityElement(children: .contain)
            .accessibilityLabel(controls.categoriesLabel)
            .accessibilityIdentifier(RacingEventPageAccessibilityID10868.categories)
        }
    }

    @ViewBuilder private func categoryControl(_ category: RacingEventPageCatalogueCategory10868) -> some View {
        let spoken = category.action.spokenLabel ?? category.action.label
        if let action = categoryAction(category) {
            Button(action: action) { categoryFace(category) }
                .buttonStyle(.plain)
                .accessibilityLabel(spoken)
                .accessibilityAddTraits(category.isSelected ? .isSelected : [])
                .accessibilityIdentifier(RacingEventPageAccessibilityID10868.category(category.action.id))
        } else {
            categoryFace(category)
                .accessibilityElement(children: .ignore)
                .accessibilityLabel(spoken)
                .accessibilityAddTraits(category.isSelected ? .isSelected : [])
                .accessibilityIdentifier(RacingEventPageAccessibilityID10868.category(category.action.id))
        }
    }

    /// Selected: a checkmark and a heavier outline, not colour alone.
    /// Unavailable: secondary words and a dashed outline.
    private func categoryFace(_ category: RacingEventPageCatalogueCategory10868) -> some View {
        let shape = RoundedRectangle(cornerRadius: 12, style: .continuous)
        let tint = originals?.tint ?? DS.blue
        let available = category.action.isAvailable
        return HStack(spacing: 6) {
            if category.isSelected {
                Image(systemName: "checkmark")
                    .font(.body.weight(.semibold))
                    .accessibilityHidden(true)
            }
            Text(category.action.label)
                .font(.body.weight(category.isSelected ? .semibold : .regular))
                .multilineTextAlignment(.center)
                .fixedSize(horizontal: false, vertical: true)
        }
        .foregroundStyle(available ? (category.isSelected ? tint : DS.textPrimary) : DS.textSecondary)
        .padding(.horizontal, 12)
        .padding(.vertical, 8)
        .frame(maxWidth: .infinity, minHeight: controlSize)
        .background(shape.fill(category.isSelected ? tint.opacity(0.10) : DS.cardBg))
        .overlay(shape.strokeBorder(category.isSelected ? tint : DS.border,
                                    style: StrokeStyle(lineWidth: category.isSelected ? 2 : 1, dash: available ? [] : [4, 3])))
        .contentShape(shape)
    }

    /// The owner's count words, then Show more: a button only when live,
    /// otherwise its words.
    @ViewBuilder private func pagingControls(_ controls: RacingEventPageCatalogueControls10868) -> some View {
        let context = RacingEventPageModel10868.readable(controls.context)
        let more = controls.more
        let moreState = RacingEventPageModel10868.catalogueControlState(more, in: controls, hasCallback: onCatalogueMore != nil)
        if context != nil || moreState != .hidden {
            VStack(alignment: .leading, spacing: 8) {
                if let context {
                    Text(context)
                        .font(.subheadline)
                        .foregroundStyle(DS.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                        .accessibilityIdentifier(RacingEventPageAccessibilityID10868.catalogueContext)
                }
                if let more, moreState != .hidden {
                    if let action = moreAction() {
                        Button(action: action) {
                            Text(more.label)
                                .font(.body.weight(.semibold))
                                .foregroundStyle(DS.blue)
                                .multilineTextAlignment(.center)
                                .fixedSize(horizontal: false, vertical: true)
                                .padding(.horizontal, 16)
                                .padding(.vertical, 8)
                                .frame(maxWidth: .infinity, minHeight: controlSize)
                                .modifier(RacingEventPageCardSurface10868())
                                .contentShape(Rectangle())
                        }
                        .buttonStyle(.plain)
                        .accessibilityLabel(more.spokenLabel ?? more.label)
                        .accessibilityIdentifier(RacingEventPageAccessibilityID10868.more)
                    } else {
                        Text(more.label)
                            .font(.subheadline)
                            .foregroundStyle(DS.textSecondary)
                            .fixedSize(horizontal: false, vertical: true)
                            .accessibilityLabel(more.spokenLabel ?? more.label)
                            .accessibilityIdentifier(RacingEventPageAccessibilityID10868.more)
                    }
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    /// The held original's existing Details, for the host's container.
    @ViewBuilder private var originalMode: some View {
        if let details = originalDetailsContent() {
            details
                .accessibilityElement(children: .contain)
                .accessibilityIdentifier(RacingEventPageAccessibilityID10868.original)
        }
    }

    /// One owner About under the compact race words, for the host's container.
    @ViewBuilder private func aboutMode(_ topic: RacingEventPageAboutTopic10868) -> some View {
        if let content = aboutContent(topic) {
            VStack(alignment: .leading, spacing: 12) {
                compactHeader
                content
            }
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier(RacingEventPageAccessibilityID10868.about(topic))
        }
    }
}

/// The reference's white card on the page surface.
private struct RacingEventPageCardSurface10868: ViewModifier {
    func body(content: Content) -> some View {
        content
            .background(DS.cardBg, in: RoundedRectangle(cornerRadius: 20, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 20, style: .continuous).stroke(DS.border, lineWidth: 1))
    }
}
