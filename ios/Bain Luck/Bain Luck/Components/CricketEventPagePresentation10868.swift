import SwiftUI

// #10868 — the cricket Test-match screen (`cricket-live`): one native
// presentation composed from the accepted leaves. The three independent
// original chances lead. A fan sees, in this order: the owner's match title
// with its About entry; the headline (each original's pregame chance, its
// recorded or current chance during play, or the reported match outcome at
// the finish, with the owner's score, overs and target words under their own
// report clock) beside the three-outcome probability history; during play
// and at the finish the owner's story stream — during play how expectations
// changed, the chase and holding on; at the finish how pregame expectations
// met the result and the resolved chase — and the three original markets
// with the held original's Details. Before play the page is the title, the
// headline, the history and the three originals, with no story stream: the
// reference's before phase offers only the history as a reader card. The
// history and each story open as full-size content made of the same Views,
// and the full catalogue, the held original's Details (with the owner's
// recorded history when supplied), the headline's sources and timing and the
// match About are further content modes.
//
// Presentation only, composed from the approved `CricketLive.tsx` /
// `cricketLive.css` and `CricketLifecycle.tsx` / `cricketLifecycle.css`, over
// `cricketLiveEvidence.ts`, `cricketLifecycleEvidence.ts` and
// `cricketMomentStories.ts`, as mounted in `Atlas.tsx` (`cricket-live`). The
// reference's fixture loaders, positive-size candle cleaning and five-minute
// replay eligibility, baseline election, final adjudication, formatters,
// `cricketMomentOrder` ranking and its reasons, moment controls, story and
// reader session state, inspection state, "Aa Larger", sheets, dialogs and
// focus restoration are NOT ported. The shared
// `CricketPregameStoryPresentation10868` belongs to the separate
// `cricket-match` route and is not mounted here. The leaves are the actual
// accepted Views:
//
//   • `CricketHeadlinePresentation10868` — the three-outcome headline;
//   • `CricketProbabilityHistoryPresentation10868` — the anchor, with the
//     owner's score-report guides;
//   • `CricketOutlookPresentation10868` — "Changing expectations" during play
//     (comparison) and "Expectations and result" at the finish (completed);
//   • `CricketChasePresentation10868` — the chase during play and resolved at
//     the finish (never before play, and never the limited-over variant);
//   • `CricketSurvivalPresentation10868` — holding on, during play only;
//   • `StoryStreamPresentationView10868` — the controlled story stream;
//   • `OriginalMarketChooserView9483` — the three original markets and the
//     held original's Details, on the page;
//   • `OriginalMarketCatalogueView9483` / `OriginalMarketDetailsView9483` —
//     the full catalogue and the held original's Details as content modes.
//
// Nothing new is drawn here beyond arrangement, card surfaces, the owner's
// title, notice and story words, the compact reader heading, the About text
// and the headline's own sources-and-timing payload laid out verbatim.
//
// The page's phase is the owner's explicit `CricketHeadlinePhase10868`, never
// read from a score, an over count, a clock or a result. A leaf is mounted
// only when its own phase or mode is the page's, and the story cards only
// where the reference offers them. A leaf from another phase is not coerced
// into this one — it is not mounted, and a headline from another phase shows
// the owner's unavailable words. South Africa, Australia and Draw / tie are
// three independent originals with their own clocks: this layer never
// normalizes or complements them (48%, 47% and 9% stay 104%), treats a missing
// value as zero, turns the reported finish into a 0/100 quote, reads a
// contract's result from the match, carries a stale probability into a current
// slot, treats a scheduled start or a capture clock as a play boundary, or
// converts overs to a decimal or a rate. Each leaf keeps its own rules for
// that.
//
// The host supplies each leaf's own immutable input, already admitted for the
// same snapshot; this layer groups them and never re-elects, copies, filters
// or formats an observation, a report, a marker, a result or a word. The
// history keeps every original's name, shape, own values and times, its
// independent segments, window, inspection and step controls; its domain,
// ticks and markers are the owner's.
//
// The story stream is the owner's: its cards, order, primary, companion,
// position, status, pending, playback, progress, previous/next, scope and
// reader-open flag, and its own "Open full card" entry. This layer wires each
// supplied card id to the one story the owner names for it, and shows the
// owner's unavailable words for an id that names no single story this phase
// mounts — never a neighbour. A card's own actions — selecting or opening the
// Details of an original in either outlook card, the chase's Details, a
// survival checkpoint's selection or Details — first call the stream's
// activation hook (so the owner can hold) and then the host's exact callback.
// None of these leaves takes a disclosure binding, so there is no write to
// gate. Building a card asks for nothing. Full-size content reuses the same
// leaves with the host's exact callbacks and no activation, so opening a card
// never requests a hold by appearing, and closing one resumes nothing.
//
// The owner may also pass an interaction hook, so it can hold its stream
// before an action outside the stream lands (the reference holds the stream on
// a pointer-down or focus in its hero and originals panels). On the page — the
// title's About, the headline's sources and timing, the anchor history's
// previous, next, expand, window choices and plot taps, an original choice and
// the All props entry — and in the catalogue and Details content — an
// original's selection and a Details history intent — the action calls that
// hook once and then the owner's exact callback with its exact value.
// Without a callback there is no action and no hook call;
// without a hook every callback is the owner's own. Building or reading the
// view calls nothing, and there is no resume. Full-size content, including the
// About in its compact heading, keeps the exact callbacks: its host already
// holds the stream while it is open. Stream cards keep the stream's own
// activation and never pass through the hook as well. A pointer-down on empty
// panel space, or focus moving into a panel, is not intercepted here; that
// stays with the host's containment.
//
// The full-size history is the same history input and markers without its
// expand control, at the owner's reader plot height when supplied; every
// series, segment, tick, window, inspection and step control is unchanged.
//
// The headline's sources and timing is the headline's own payload, handed to
// the host unchanged, and shown here only as the host's `.sourceInfo` content
// with exactly that payload. Provenance leaves the headline only when the
// owner sets `secondaryProvenance` AND the host connects the disclosure; an
// unconnected headline keeps every provenance line inline. The match About is
// the owner's text, reached through the title's control and the readers'
// compact heading; with no readable About or no callback there is no control.
//
// The three originals stay reachable through the actual chooser and Details on
// the page, and through the actual catalogue and Details content. The
// reference supplies only these three result originals, so no category, page
// or Show more control is drawn. The Details content mode hands the actual
// Details leaf the owner's optional recorded history for the held original
// and its history intent callback, unchanged; without them it is the existing
// summary-only Details. This layer elects, fetches, formats or settles no
// history. The page's inline chooser is unchanged and draws no recorded plot.
//
// Phone stacks the headline above the history, then the stories and the
// originals. A regular or unspecified size class (a Mac window) places the
// headline beside the history (the reference's 1 : 1.7 grid) while both keep
// their minimum widths, otherwise it stacks too; accessibility sizes always
// stack. The stories and the originals run full width below.
//
// The host owns the scroll, navigation, sheets, Back/Done, paging and swipe,
// focus, routing to and from the catalogue, an original's Details, the
// sources and timing and the About, the selected original and checkpoint, the
// held/received frame, how a hook request holds the stream, live
// subscriptions and every genuine update. This view keeps no state, runs no
// timer or animation, holds no subscription and presents no sheet or
// navigation of its own. Every callback is the host's own closure handed to
// the leaf unchanged. With no callback, nothing pretends to act.
//
// Host binding still owed — not available at this base: an owner that admits,
// for one match snapshot, the phase, the headline rows and state words, the
// history with its segments and score-report guides at or before that
// snapshot, each story leaf's input, the reader heading, the story stream and
// its card-to-story map, the About text, the three originals' catalogue and
// held selection with any admitted recorded history, and maps every callback
// to its existing controls —
// including from an outlook, chase or survival reference to the Details
// selection it names.

/// One card the page can show full size. `history` is the anchor.
nonisolated enum CricketEventPageCard10868: String, Hashable, CaseIterable {
    case history
    /// "Changing expectations": the outlook card in comparison mode.
    case shifts
    case chase
    /// "Holding on".
    case survival
    /// "Expectations and result": the outlook card in completed mode.
    case expectations
}

/// What the host's container is showing, chosen by the host.
nonisolated enum CricketEventPageMode10868: Equatable {
    /// The match screen body.
    case page
    /// One card's full-size content.
    case reader(CricketEventPageCard10868)
    /// Every retained original ("All props").
    case catalogue
    /// The held original's Details.
    case original
    /// The owner's match About.
    case about
    /// The headline's sources and timing, exactly the payload it handed back.
    case sourceInfo(CricketHeadlineSourceInfo10868)
}

nonisolated enum CricketEventPageArrangement10868: Equatable {
    case stacked
    case sideBySide
}

// MARK: - Page input

/// The owner's match title over the hero.
nonisolated struct CricketEventPageTitle10868: Equatable {
    /// "Recorded · First Test · Durban"; nil draws none.
    let eyebrow: String?
    /// "South Africa · Australia".
    let title: String
}

/// The owner's one-line match words above full-size content.
nonisolated struct CricketEventPageReaderHeader10868: Equatable {
    /// "South Africa 154/4", "Australia won by 214 runs".
    let title: String
    /// "Score report · Day 5 · 64 overs · target 421"; nil draws none.
    let state: String?
}

/// The owner's link from one stream card id to the story it shows.
nonisolated struct CricketEventPageStory10868: Equatable {
    /// Exactly as in `StoryStreamPresentation10868.cards`.
    let cardID: String
    let card: CricketEventPageCard10868
    /// The owner's words for why this story is here ("6 wickets remain at
    /// the 64-over report."); nil draws none.
    var reason: String? = nil
}

/// The owner's match About, verbatim.
nonisolated struct CricketEventPageAbout10868: Equatable {
    /// "Recorded final-day play".
    let title: String
    let paragraphs: [String]
}

nonisolated struct CricketEventPageCopy10868: Equatable {
    /// Spoken name of the stories group ("Match stories").
    let storiesLabel: String
    /// Shown in a stream cell whose id names no single story this phase shows.
    let storyUnavailable: String
    /// Shown in place of a headline whose phase is not the page's.
    let headlineUnavailable: String
    /// Spoken name of the About control ("About this match").
    let aboutLabel: String
    /// "All 3 original markets"; nil draws no entry.
    var allPropsLabel: String? = nil
}

nonisolated struct CricketEventPageInput10868: Equatable {
    let phase: CricketHeadlinePhase10868
    let title: CricketEventPageTitle10868
    let reader: CricketEventPageReaderHeader10868
    let headline: CricketHeadlineInput10868
    /// The owner's explicit choice to move headline provenance into the
    /// connected sources-and-timing disclosure.
    var secondaryProvenance: Bool = false
    /// The owner's status words under the headline ("Refreshing · recorded
    /// history retained"); nil draws none.
    var notice: String? = nil
    let history: CricketHistoryInput10868
    /// The owner's score-report guides, mounted at the page's own phase.
    var historyMarkers: CricketHistoryMarkerContext10868? = nil
    /// The owner's plot height for the full-size history; nil keeps the
    /// page's.
    var readerPlotHeight: CGFloat? = nil
    /// During play only, comparison mode.
    var shifts: CricketOutlookInput10868? = nil
    /// During play, and resolved at the final.
    var chase: CricketChaseInput10868? = nil
    /// During play only.
    var survival: CricketSurvivalInput10868? = nil
    /// At the final only, completed mode.
    var expectations: CricketOutlookInput10868? = nil
    /// The batting side's series tint for the chase's runs.
    let runsTint: Color
    /// The tint of a remaining wicket, in the chase and survival cards.
    let wicketTint: Color
    /// The owner's story stream; nil draws no stories. Before play there is
    /// none: the reference's before page offers only the history.
    var stream: StoryStreamPresentation10868? = nil
    var stories: [CricketEventPageStory10868] = []
    /// Opened by the title's About control; nil: no control.
    var about: CricketEventPageAbout10868? = nil
    let copy: CricketEventPageCopy10868
}

/// The owner's three retained originals, for the page's chooser and the
/// catalogue and Details modes. Every field reaches the existing leaves
/// unchanged.
struct CricketEventPageOriginals10868 {
    /// The latest admitted originals for one scope; nil shows `emptyWords`.
    let catalogue: OriginalMarketDetails9483.Catalogue?
    /// The owner's held selection; nil holds none.
    let selection: OriginalMarketDetails9483.Selection?
    /// The held original's admitted recorded history, for the Details mode
    /// only; nil keeps its summary-only Details.
    var recorded: OriginalMarketDetails9483.RecordedHistory? = nil
    /// The owner's choice label for an exact identity; otherwise its title.
    var labels: [OriginalMarketDetails9483.Identity: String] = [:]
    /// "All 3 original markets".
    let heading: String
    /// The catalogue's count words ("3 retained originals"); nil draws none.
    var context: String? = nil
    /// "No retained originals for this match".
    let emptyWords: String
    /// The label for an original with no readable title of its own.
    let unavailableChoice: String
    let tint: Color
}

nonisolated enum CricketEventPageAccessibilityID10868 {
    static let page = "cricketEventPage10868.page"
    static let hero = "cricketEventPage10868.hero"
    static let title = "cricketEventPage10868.title"
    static let titleAbout = "cricketEventPage10868.title.about"
    static let headlineUnavailable = "cricketEventPage10868.headline.unavailable"
    static let notice = "cricketEventPage10868.notice"
    static let anchor = "cricketEventPage10868.anchor"
    static let stories = "cricketEventPage10868.stories"
    static let originals = "cricketEventPage10868.originals"
    static let allProps = "cricketEventPage10868.allProps"
    static let unavailable = "cricketEventPage10868.story.unavailable"
    static let readerHeader = "cricketEventPage10868.readerHeader"
    static let readerAbout = "cricketEventPage10868.readerHeader.about"
    static let catalogue = "cricketEventPage10868.catalogue"
    static let original = "cricketEventPage10868.original"
    static let about = "cricketEventPage10868.about"
    static let sourceInfo = "cricketEventPage10868.sourceInfo"
    static func card(_ card: CricketEventPageCard10868) -> String { "cricketEventPage10868.card.\(card.rawValue)" }
}

// MARK: - Page model

/// Which leaves the page mounts, resolved once per input.
nonisolated struct CricketEventPageModel10868: Equatable {
    let input: CricketEventPageInput10868

    init(_ input: CricketEventPageInput10868) {
        self.input = input
    }

    /// The chase leaf's phase for a page phase.
    static func chasePhase(_ phase: CricketHeadlinePhase10868) -> CricketChasePhase10868 {
        switch phase {
        case .before: .before
        case .during: .during
        case .completed: .final
        }
    }

    /// The history guides' phase for a page phase.
    static func markerPhase(_ phase: CricketHeadlinePhase10868) -> CricketHistoryMarkerPhase10868 {
        switch phase {
        case .before: .before
        case .during: .during
        case .completed: .completed
        }
    }

    /// The headline at the page's own phase. Otherwise nothing.
    var headline: CricketHeadlineInput10868? {
        input.headline.phase == input.phase ? input.headline : nil
    }

    /// The owner's guides at the page's own phase. Otherwise none.
    var historyMarkers: CricketHistoryMarkerContext10868? {
        guard let markers = input.historyMarkers, markers.phase == Self.markerPhase(input.phase) else { return nil }
        return markers
    }

    /// Changing expectations: during play, in comparison mode.
    var shifts: CricketOutlookInput10868? {
        guard input.phase == .during, let shifts = input.shifts, !shifts.isCompleted else { return nil }
        return shifts
    }

    /// The chase: during play, and resolved at the final — never before play.
    var chase: CricketChaseInput10868? {
        guard input.phase != .before, let chase = input.chase, chase.phase == Self.chasePhase(input.phase) else { return nil }
        return chase
    }

    /// Holding on: during play, at that phase.
    var survival: CricketSurvivalInput10868? {
        guard input.phase == .during, let survival = input.survival, survival.phase == .during else { return nil }
        return survival
    }

    /// Expectations and result: at the final, in completed mode.
    var expectations: CricketOutlookInput10868? {
        guard input.phase == .completed, let expectations = input.expectations, expectations.isCompleted else { return nil }
        return expectations
    }

    func isMounted(_ card: CricketEventPageCard10868) -> Bool {
        switch card {
        case .history: true
        case .shifts: shifts != nil
        case .chase: chase != nil
        case .survival: survival != nil
        case .expectations: expectations != nil
        }
    }

    /// The owner's link a stream card id names: exactly one link with that
    /// id, to a story this phase mounts. Otherwise nothing.
    func story(_ cardID: String) -> CricketEventPageStory10868? {
        let links = input.stories.filter { $0.cardID == cardID }
        guard links.count == 1, let link = links.first, link.card != .history, isMounted(link.card) else { return nil }
        return link
    }

    func storyCard(_ cardID: String) -> CricketEventPageCard10868? { story(cardID)?.card }

    /// Full-size content exists for the anchor and for a story this phase shows.
    func readerShows(_ card: CricketEventPageCard10868) -> Bool { isMounted(card) }

    /// The anchor's full-size content: the same history without an expand
    /// control inside the reader, at the owner's reader height when supplied.
    /// Every other field is the owner's, unchanged.
    var readerHistory: CricketHistoryInput10868 {
        let history = input.history
        return CricketHistoryInput10868(
            title: history.title, series: history.series, domain: history.domain,
            yTicks: history.yTicks, xTicks: history.xTicks, context: history.context,
            pregameKey: history.pregameKey, summary: history.summary,
            plotHeight: input.readerPlotHeight ?? history.plotHeight,
            window: history.window, inspection: history.inspection,
            previous: history.previous, next: history.next, expand: nil
        )
    }

    // MARK: About and entries

    /// The owner's About, when it carries readable words.
    var about: CricketEventPageAbout10868? {
        guard let about = input.about,
              Self.readable(about.title) != nil || about.paragraphs.contains(where: { Self.readable($0) != nil })
        else { return nil }
        return about
    }

    func aboutAvailable(canOpen: Bool) -> Bool {
        canOpen && about != nil && Self.readable(input.copy.aboutLabel) != nil
    }

    /// Whether `mode`'s compact heading shows the About entry: full-size
    /// content only — the page has the title's own control.
    func aboutEntry(mode: CricketEventPageMode10868, canOpen: Bool) -> Bool {
        guard case .reader = mode else { return false }
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
    static func arrangements(sizeClass: UserInterfaceSizeClass?, accessibilitySize: Bool) -> [CricketEventPageArrangement10868] {
        sizeClass != .compact && !accessibilitySize ? [.sideBySide, .stacked] : [.stacked]
    }
}

// MARK: - About and sources content

/// The owner's About in its own words. Static text; it acts on nothing.
struct CricketEventPageAboutContent10868: View {
    let about: CricketEventPageAbout10868

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            if let title = CricketEventPageModel10868.readable(about.title) {
                Text(title)
                    .font(.headline)
                    .foregroundStyle(DS.textPrimary)
                    .accessibilityAddTraits(.isHeader)
            }
            ForEach(Array(about.paragraphs.enumerated()), id: \.offset) { _, paragraph in
                if let words = CricketEventPageModel10868.readable(paragraph) {
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

/// The headline's own sources-and-timing payload, laid out verbatim: its
/// caption, each original's visible slots with their labels, figures or
/// words and full provenance, then the visible state. Static; it acts on
/// nothing and reads nothing the payload does not carry.
struct CricketEventPageSourceInfoContent10868: View {
    let info: CricketHeadlineSourceInfo10868

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text(CricketHeadlineInput10868.sourceInfoLabel)
                .font(.headline)
                .foregroundStyle(DS.textPrimary)
                .accessibilityAddTraits(.isHeader)
            if let caption = CricketEventPageModel10868.readable(info.caption) {
                Text(caption)
                    .font(.subheadline)
                    .foregroundStyle(DS.textSecondary)
            }
            ForEach(Array(info.subjects.enumerated()), id: \.offset) { _, subject in
                VStack(alignment: .leading, spacing: 8) {
                    Text(subject.subject)
                        .font(.body.weight(.semibold))
                        .foregroundStyle(DS.textPrimary)
                        .accessibilityAddTraits(.isHeader)
                    ForEach(Array(subject.entries.enumerated()), id: \.offset) { _, entry in
                        VStack(alignment: .leading, spacing: 2) {
                            Text(entry.label)
                                .font(.subheadline)
                                .foregroundStyle(DS.textSecondary)
                            Text(entry.text)
                                .font(.body.weight(.semibold))
                                .foregroundStyle(DS.textPrimary)
                            if let detail = entry.detail {
                                Text(detail)
                                    .font(.subheadline)
                                    .foregroundStyle(DS.textSecondary)
                            }
                        }
                        .accessibilityElement(children: .combine)
                    }
                }
            }
            stateSection
        }
        .fixedSize(horizontal: false, vertical: true)
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    @ViewBuilder private var stateSection: some View {
        switch info.state {
        case .reported(let frame)?:
            VStack(alignment: .leading, spacing: 4) {
                ForEach(Array(frame.entries.enumerated()), id: \.offset) { _, entry in
                    VStack(alignment: .leading, spacing: 2) {
                        if let label = entry.label {
                            Text(label)
                                .font(.subheadline)
                                .foregroundStyle(DS.textSecondary)
                        }
                        Text(entry.text)
                            .font(.body.weight(.semibold))
                            .foregroundStyle(DS.textPrimary)
                            .accessibilityLabel(entry.spoken)
                    }
                    .accessibilityElement(children: .combine)
                }
                if let detail = frame.detail {
                    Text(detail)
                        .font(.subheadline)
                        .foregroundStyle(DS.textSecondary)
                }
            }
        case .unavailable(let words)?:
            Text(words)
                .font(.subheadline)
                .foregroundStyle(DS.textSecondary)
        case nil:
            EmptyView()
        }
    }
}

// MARK: - Page view

struct CricketEventPagePresentation10868: View {
    typealias Stream = StoryStreamPresentation10868

    let input: CricketEventPageInput10868
    var mode: CricketEventPageMode10868 = .page
    /// The page's chooser and the catalogue and Details modes' content; nil:
    /// none of them has any.
    var originals: CricketEventPageOriginals10868? = nil
    /// Opens the host's container on the owner's About.
    var onAbout: (() -> Void)? = nil
    /// Opens the host's disclosure on the headline's exact payload.
    var onSourceInfo: ((CricketHeadlineSourceInfo10868) -> Void)? = nil
    /// Opens the host's existing catalogue.
    var onAllProps: (() -> Void)? = nil
    /// A chooser or catalogue original's exact selection, for the host to
    /// hold and route.
    var onOriginalSelect: ((OriginalMarketDetails9483.Selection) -> Void)? = nil
    /// A Details history control's exact intent, for the host to route.
    var onOriginalHistory: ((OriginalMarketDetails9483.HistoryIntent) -> Void)? = nil
    var onStoryIntent: ((Stream.Intent) -> Void)? = nil
    var onHistoryPrevious: (() -> Void)? = nil
    var onHistoryNext: (() -> Void)? = nil
    /// Opens the history's full-size content.
    var onHistoryExpand: (() -> Void)? = nil
    var onHistoryWindowChoice: ((String) -> Void)? = nil
    var onHistoryPlotPosition: ((Double) -> Void)? = nil
    var onShiftsSelect: ((CricketOutlookRef10868) -> Void)? = nil
    var onShiftsDetails: ((CricketOutlookRef10868) -> Void)? = nil
    var onChaseDetails: ((CricketChaseRef10868) -> Void)? = nil
    var onSurvivalSelect: ((CricketSurvivalTarget10868) -> Void)? = nil
    var onSurvivalDetails: ((CricketSurvivalTarget10868) -> Void)? = nil
    var onExpectationsSelect: ((CricketOutlookRef10868) -> Void)? = nil
    var onExpectationsDetails: ((CricketOutlookRef10868) -> Void)? = nil
    /// Called once just before a page, catalogue or Details action reaches
    /// its owner callback, so the owner can hold its stream. Never called by
    /// building the view, by full-size content or by a stream card.
    var onInteraction: (() -> Void)? = nil

    @Environment(\.horizontalSizeClass) private var sizeClass
    @Environment(\.dynamicTypeSize) private var typeSize
    @ScaledMetric(relativeTo: .body) private var headlineMinWidth: CGFloat = 260
    @ScaledMetric(relativeTo: .body) private var headlineMaxWidth: CGFloat = 400
    @ScaledMetric(relativeTo: .body) private var anchorMinWidth: CGFloat = 420
    @ScaledMetric(relativeTo: .body) private var controlSize: CGFloat = 44

    private var model: CricketEventPageModel10868 { CricketEventPageModel10868(input) }

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

    /// A page or catalogue action, after the owner's interaction hook. No host
    /// callback: no action and no hook call. No hook: the exact callback.
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
            case .sourceInfo(let info): sourceInfoMode(info)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    // MARK: Leaves — the actual Views, each with the host's own callbacks

    /// The headline, at the page's phase only. Its sources and timing passes
    /// the interaction hook first and then hands the host the headline's own
    /// payload.
    func headlineContent() -> CricketHeadlinePresentation10868? {
        model.headline.map {
            CricketHeadlinePresentation10868(input: $0, secondaryProvenance: input.secondaryProvenance,
                                             onSourceInfo: Self.held(onSourceInfo, by: onInteraction))
        }
    }

    /// The anchor passes the interaction hook first; the full-size history
    /// keeps the exact callbacks and has no expand control.
    func historyContent(reader: Bool) -> CricketProbabilityHistoryPresentation10868 {
        let interaction = reader ? nil : onInteraction
        return CricketProbabilityHistoryPresentation10868(
            input: reader ? model.readerHistory : input.history,
            markers: model.historyMarkers,
            onPrevious: Self.heldAction(onHistoryPrevious, by: interaction),
            onNext: Self.heldAction(onHistoryNext, by: interaction),
            onExpand: reader ? nil : Self.heldAction(onHistoryExpand, by: interaction),
            onWindowChoice: Self.held(onHistoryWindowChoice, by: interaction),
            onPlotPosition: Self.held(onHistoryPlotPosition, by: interaction)
        )
    }

    /// `activation` is the stream's hook for a card in the stream; nil in
    /// full-size content.
    func shiftsContent(activation: StoryStreamCardActivation10868? = nil) -> CricketOutlookPresentation10868? {
        model.shifts.map {
            CricketOutlookPresentation10868(input: $0,
                                            onSelect: Self.relay(onShiftsSelect, through: activation),
                                            onDetails: Self.relay(onShiftsDetails, through: activation))
        }
    }

    func chaseContent(activation: StoryStreamCardActivation10868? = nil) -> CricketChasePresentation10868? {
        model.chase.map {
            CricketChasePresentation10868(input: $0, runsTint: input.runsTint, wicketTint: input.wicketTint,
                                          onDetails: Self.relay(onChaseDetails, through: activation))
        }
    }

    func survivalContent(activation: StoryStreamCardActivation10868? = nil) -> CricketSurvivalPresentation10868? {
        model.survival.map {
            CricketSurvivalPresentation10868(input: $0, wicketTint: input.wicketTint,
                                             onSelect: Self.relay(onSurvivalSelect, through: activation),
                                             onDetails: Self.relay(onSurvivalDetails, through: activation))
        }
    }

    func expectationsContent(activation: StoryStreamCardActivation10868? = nil) -> CricketOutlookPresentation10868? {
        model.expectations.map {
            CricketOutlookPresentation10868(input: $0,
                                            onSelect: Self.relay(onExpectationsSelect, through: activation),
                                            onDetails: Self.relay(onExpectationsDetails, through: activation))
        }
    }

    /// The owner's About, as static content.
    func aboutContent() -> CricketEventPageAboutContent10868? {
        model.about.map { CricketEventPageAboutContent10868(about: $0) }
    }

    /// The headline's exact payload, as static content.
    func sourceInfoContent(_ info: CricketHeadlineSourceInfo10868) -> CricketEventPageSourceInfoContent10868 {
        CricketEventPageSourceInfoContent10868(info: info)
    }

    /// The existing chooser and held Details on the page, with the owner's
    /// originals exactly as admitted, its select callback after the hook.
    func chooserContent() -> OriginalMarketChooserView9483? {
        originals.map {
            OriginalMarketChooserView9483(
                catalogue: $0.catalogue, selection: $0.selection, heading: $0.heading,
                emptyWords: $0.emptyWords, unavailableChoice: $0.unavailableChoice, labels: $0.labels,
                tint: $0.tint, onSelect: Self.held(onOriginalSelect, by: onInteraction)
            )
        }
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

    /// The title's About, after the interaction hook.
    func openTitleAbout() {
        guard model.aboutAvailable(canOpen: onAbout != nil) else { return }
        Self.heldAction(onAbout, by: onInteraction)?()
    }

    /// Full-size content's About: the exact callback, no hook.
    func openReaderAbout() {
        guard model.aboutAvailable(canOpen: onAbout != nil) else { return }
        onAbout?()
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
            originalsPanel
        }
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(CricketEventPageAccessibilityID10868.page)
    }

    /// The title, then the headline and the history in one panel: side by
    /// side where both fit at their minimum widths, otherwise the headline
    /// above the history.
    private var hero: some View {
        VStack(alignment: .leading, spacing: 16) {
            titleRow
            let arrangements = CricketEventPageModel10868.arrangements(
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
        .modifier(CricketEventPageCardSurface10868())
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(CricketEventPageAccessibilityID10868.hero)
    }

    /// The owner's eyebrow and title, with the About control beside them.
    private var titleRow: some View {
        HStack(alignment: .center, spacing: 12) {
            VStack(alignment: .leading, spacing: 4) {
                if let eyebrow = CricketEventPageModel10868.readable(input.title.eyebrow) {
                    Text(eyebrow)
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(DS.textSecondary)
                }
                Text(input.title.title)
                    .font(.title2.bold())
                    .foregroundStyle(DS.textPrimary)
                    .accessibilityAddTraits(.isHeader)
            }
            .fixedSize(horizontal: false, vertical: true)
            .frame(maxWidth: .infinity, alignment: .leading)
            .accessibilityElement(children: .combine)
            .accessibilityIdentifier(CricketEventPageAccessibilityID10868.title)
            if model.aboutAvailable(canOpen: onAbout != nil) {
                aboutButton(action: openTitleAbout, id: CricketEventPageAccessibilityID10868.titleAbout)
            }
        }
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
                    .accessibilityIdentifier(CricketEventPageAccessibilityID10868.headlineUnavailable)
            }
            if let notice = CricketEventPageModel10868.readable(input.notice) {
                Text(notice)
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .accessibilityIdentifier(CricketEventPageAccessibilityID10868.notice)
            }
        }
    }

    private var anchor: some View {
        historyContent(reader: false)
            .frame(maxWidth: .infinity, alignment: .leading)
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier(CricketEventPageAccessibilityID10868.anchor)
    }

    /// The owner's stream, when it supplies one.
    @ViewBuilder private var stories: some View {
        if let stream = input.stream {
            StoryStreamPresentationView10868(stream, onIntent: onStoryIntent) { card, activation in
                storyCell(card, activation)
            }
            .accessibilityElement(children: .contain)
            .accessibilityLabel(input.copy.storiesLabel)
            .accessibilityIdentifier(CricketEventPageAccessibilityID10868.stories)
        }
    }

    /// The story the owner links to this stream card, with the stream's
    /// activation hook and the owner's reason words, or the owner's
    /// unavailable words.
    @ViewBuilder private func storyCell(_ card: Stream.Card, _ activation: StoryStreamCardActivation10868) -> some View {
        if let link = model.story(card.id) {
            VStack(alignment: .leading, spacing: 8) {
                if let reason = CricketEventPageModel10868.readable(link.reason) {
                    Text(reason)
                        .font(.subheadline)
                        .foregroundStyle(DS.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
                cardContent(link.card, activation: activation)
            }
            .padding(16)
            .frame(maxWidth: .infinity, alignment: .leading)
            .modifier(CricketEventPageCardSurface10868())
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier(CricketEventPageAccessibilityID10868.card(link.card))
        } else {
            Text(input.copy.storyUnavailable)
                .font(.subheadline)
                .foregroundStyle(DS.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
                .frame(maxWidth: .infinity, minHeight: 120, alignment: .leading)
                .padding(16)
                .modifier(CricketEventPageCardSurface10868())
                .accessibilityIdentifier(CricketEventPageAccessibilityID10868.unavailable)
        }
    }

    /// The three originals with the held original's Details, then the All
    /// props entry when the owner names one.
    @ViewBuilder private var originalsPanel: some View {
        let allProps = model.allPropsAvailable(canOpen: onAllProps != nil)
        if chooserContent() != nil || allProps {
            VStack(alignment: .leading, spacing: 16) {
                if let chooser = chooserContent() {
                    chooser
                }
                if allProps, let label = input.copy.allPropsLabel {
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
                        .frame(minHeight: controlSize)
                        .contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                    .accessibilityIdentifier(CricketEventPageAccessibilityID10868.allProps)
                }
            }
            .padding(16)
            .frame(maxWidth: .infinity, alignment: .leading)
            .modifier(CricketEventPageCardSurface10868())
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier(CricketEventPageAccessibilityID10868.originals)
        }
    }

    // MARK: Content shared by the page and the reader

    @ViewBuilder private func cardContent(_ card: CricketEventPageCard10868,
                                          activation: StoryStreamCardActivation10868?) -> some View {
        switch card {
        case .history: historyContent(reader: true)
        case .shifts: shiftsContent(activation: activation)
        case .chase: chaseContent(activation: activation)
        case .survival: survivalContent(activation: activation)
        case .expectations: expectationsContent(activation: activation)
        }
    }

    /// The same leaf and input, full size, for the host's existing reader,
    /// under the compact match words. A card this phase does not show has no
    /// content.
    @ViewBuilder private func reader(_ card: CricketEventPageCard10868) -> some View {
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
                if let state = CricketEventPageModel10868.readable(input.reader.state) {
                    Text(state)
                        .font(.subheadline)
                        .foregroundStyle(DS.textSecondary)
                }
            }
            .fixedSize(horizontal: false, vertical: true)
            .frame(maxWidth: .infinity, alignment: .leading)
            if model.aboutEntry(mode: mode, canOpen: onAbout != nil) {
                aboutButton(action: openReaderAbout, id: CricketEventPageAccessibilityID10868.readerAbout)
            }
        }
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(CricketEventPageAccessibilityID10868.readerHeader)
    }

    private func aboutButton(action: @escaping () -> Void, id: String) -> some View {
        Button(action: action) {
            Image(systemName: "info.circle")
                .font(.title3)
                .foregroundStyle(DS.textPrimary)
                .frame(minWidth: controlSize, minHeight: controlSize)
                .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityLabel(input.copy.aboutLabel)
        .accessibilityIdentifier(id)
    }

    // MARK: All props, the held original's Details, About and sources

    /// The owner's admitted originals under the compact match words.
    @ViewBuilder private var catalogueMode: some View {
        if let catalogue = catalogueContent() {
            VStack(alignment: .leading, spacing: 12) {
                compactHeader
                catalogue
            }
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier(CricketEventPageAccessibilityID10868.catalogue)
        }
    }

    /// The held original's existing Details, for the host's container.
    @ViewBuilder private var originalMode: some View {
        if let details = originalDetailsContent() {
            details
                .accessibilityElement(children: .contain)
                .accessibilityIdentifier(CricketEventPageAccessibilityID10868.original)
        }
    }

    /// The owner's About under the compact match words.
    @ViewBuilder private var aboutMode: some View {
        if let content = aboutContent() {
            VStack(alignment: .leading, spacing: 12) {
                compactHeader
                content
            }
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier(CricketEventPageAccessibilityID10868.about)
        }
    }

    /// The headline's exact payload under the compact match words.
    private func sourceInfoMode(_ info: CricketHeadlineSourceInfo10868) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            compactHeader
            sourceInfoContent(info)
        }
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(CricketEventPageAccessibilityID10868.sourceInfo)
    }
}

/// The reference's white card on the page surface.
private struct CricketEventPageCardSurface10868: ViewModifier {
    func body(content: Content) -> some View {
        content
            .background(DS.cardBg, in: RoundedRectangle(cornerRadius: 20, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 20, style: .continuous).stroke(DS.border, lineWidth: 1))
    }
}
