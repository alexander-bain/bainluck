import SwiftUI

// #10868 — the generic FIELD event screen: a championship or tournament field
// of named contenders (cricket, rugby, darts and chess fields today), composed
// from the accepted leaves. Win chances lead. A fan sees, in this order: the
// field headline (the owner's eyebrow, title and About entry, and each
// displayed contender's named chance for the phase), the contenders' win
// history front and centre, then the owner's story stream — the field's
// recorded win chances on one scale, and how each displayed contender's
// chance moved between the earliest and latest reading of the history — and
// the "All props" entry. The history and each story open as full-size content
// made of the same Views; "All props", the selected original's Details and the
// About are further content modes.
//
// Presentation only, in the structure of the accepted composed screens
// (`RacingEventPagePresentation10868`, `GolfEventPagePresentation10868`), for
// the field routes the approved reference mounts through `AtlasPage` /
// `FieldEventHeader` / `FieldStories` (`cricket-field`, `rugby-field`,
// `darts-field`) and `ChessHistoryHeader` (`chess-field`). The reference's
// fixture loaders, row-key bindings, quoted-row election and sort, catalog
// session, card focus, reader memory, "Aa Larger", sheets, dialogs and focus
// restoration are NOT ported. The leaves are the actual accepted Views:
//
//   • `FieldPhaseHeadlinePresentation10868` — the field headline;
//   • `FieldProbabilityHistoryPresentation10868` — the anchor;
//   • `FieldOutlookBarsPresentation10868` — the field's recorded win chances
//     on one zero-based scale;
//   • `PreEventProbabilityShiftPresentation10868` — each displayed contender's
//     earliest and latest recorded chance, two marks on one scale;
//   • `StoryStreamPresentationView10868` — the controlled story stream;
//   • `OriginalMarketCatalogueView9483` / `OriginalMarketDetailsView9483` —
//     "All props" and the selected original's Details.
//
// Nothing new is drawn here beyond arrangement, card surfaces, the owner's
// story words, the compact reader heading and the About text. Every word is
// the owner's: this layer names no sport and no kind of contender — "team",
// "player" or "contender" arrives in the owner's copy.
//
// The page's phase is the owner's explicit `FieldOutlookPhase10868`, never
// read from a price, a clock or a result. A leaf is mounted only when its own
// phase is the page's, and the stories only outside the during phase: this
// screen has no live state of its own, so a during page shows the headline,
// the history and All props, and no story. A leaf from another phase is not
// coerced into this one — it is not mounted, and a headline from another
// phase shows the owner's unavailable words. Every contender's winner
// contract is an independent original with its own clock: this layer never
// normalizes the contenders' chances, treats a missing value as zero, turns a
// result into a 0/100 quote, reads a contract's Won/Lost from a position, or
// promotes a stale reading to a current headline. Each leaf keeps its own
// rules for that.
//
// The host supplies each leaf's own immutable input, already admitted for the
// same snapshot; this layer groups them and never re-elects, copies, filters
// or formats an observation, a marker or a result. The history keeps every
// original's name, shape, own values and times, its independent runs, window,
// scale and controls; its domain, range, segments and markers are the owner's.
//
// The story stream is the owner's: its cards, order, primary, companion,
// position, status, previous/next and reader-open flag, and its own "Open full
// card" entry. This layer wires each supplied card id to the one story the
// owner names for it, and shows the owner's unavailable words for an id that
// names no single story this phase mounts — never a neighbour. A card's own
// actions — choosing a contender in the field card, opening its original,
// opening a contender's history from the movement card — first call the
// stream's activation hook (so the owner can hold) and then the host's exact
// callback. Full-size content reuses the same leaves with the host's exact
// callbacks and no activation, so opening a card never requests a hold by
// appearing, and closing one resumes nothing.
//
// The owner may also pass an interaction hook. On the page — a headline
// contender's open and the headline's About, the anchor history's actions,
// inspection choices and plot taps, the All props entry — and in the catalogue
// and Details content — an original's selection, a Details history control —
// the action calls that hook once and then the owner's exact callback with its
// exact value. Without a callback there is no action and no hook call; without
// a hook every callback is the owner's own. Building or reading the view calls
// nothing. Full-size content, including the About entry in its compact heading,
// keeps the exact callbacks. Stream cards keep the stream's own activation and
// never pass through the hook as well.
//
// The full-size history is the same history input with its expanded layout
// and without its expand control; every series, guide, selection, readout,
// window, scale and other control is unchanged — so the owner's Auto / Full
// scale choice holds across the page and the full-size chart.
//
// The About is the owner's text, reached only through the headline's own About
// control and the readers' compact heading. With no About text or no callback,
// the leaf draws no About control and keeps its own words.
//
// Phone stacks the headline above the history, then the stories. A regular or
// unspecified size class (a Mac window) places the headline beside the history
// while both keep their minimum widths, otherwise it stacks too; accessibility
// sizes always stack. The stories run full width below.
//
// The host owns the scroll, navigation, sheets, Back/Done, focus, routing to
// and from the catalogue, an original's Details and the About, the chosen
// contender, the chart's scale choice, live subscriptions and every genuine
// update. This view keeps no state, runs no timer or animation, holds no
// subscription and presents no sheet or navigation of its own. With no
// callback, nothing pretends to act.

/// One card the page can show full size. `history` is the anchor.
nonisolated enum FieldEventPageCard10868: String, Hashable, CaseIterable {
    case history
    /// The field's recorded win chances on one scale.
    case field
    /// Each displayed contender's earliest and latest recorded chance.
    case movement
}

/// What the host's container is showing, chosen by the host.
nonisolated enum FieldEventPageMode10868: Equatable {
    /// The field screen body.
    case page
    /// One card's full-size content.
    case reader(FieldEventPageCard10868)
    /// Every retained original ("All props").
    case catalogue
    /// The held original's Details.
    case original
    /// The owner's About.
    case about
}

nonisolated enum FieldEventPageArrangement10868: Equatable {
    case stacked
    case sideBySide
}

// MARK: - Page input

/// The owner's one-line words above full-size content.
nonisolated struct FieldEventPageReaderHeader10868: Equatable {
    /// "2027 IPL Champion".
    let title: String
    /// "Recorded win chances"; nil draws none.
    let state: String?
}

/// The owner's link from one stream card id to the story it shows.
nonisolated struct FieldEventPageStory10868: Equatable {
    /// Exactly as in `StoryStreamPresentation10868.cards`.
    let cardID: String
    let card: FieldEventPageCard10868
    /// The owner's words for why this story is here; nil draws none.
    var reason: String? = nil
}

/// The owner's About, verbatim.
nonisolated struct FieldEventPageAbout10868: Equatable {
    let title: String
    let paragraphs: [String]
}

nonisolated struct FieldEventPageCopy10868: Equatable {
    /// Spoken name of the stories group ("Championship stories").
    let storiesLabel: String
    /// Shown in a stream cell whose id names no single story this phase shows.
    let storyUnavailable: String
    /// Shown in place of a headline whose phase is not the page's.
    let headlineUnavailable: String
    /// "All 18 original outcomes"; nil draws no entry.
    let allPropsLabel: String?
}

nonisolated struct FieldEventPageInput10868: Equatable {
    let phase: FieldOutlookPhase10868
    let reader: FieldEventPageReaderHeader10868
    let headline: FieldHeadlineInput10868
    let history: FieldHistoryInput10868
    /// The field card; mounted at its own phase, never during.
    let field: FieldOutlookInput10868?
    /// The movement card; mounted at its own phase, never during.
    let movement: PreEventShiftInput10868?
    let stream: StoryStreamPresentation10868
    let stories: [FieldEventPageStory10868]
    /// Opened by the headline's About control; nil: no control.
    let about: FieldEventPageAbout10868?
    let copy: FieldEventPageCopy10868
}

/// The owner's retained originals behind "All props", for the catalogue and
/// Details modes. Every field reaches the existing leaves unchanged.
struct FieldEventPageOriginals10868 {
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
    /// "18 original outcomes"; nil draws none.
    var context: String? = nil
    /// "No original outcomes for this field".
    let emptyWords: String
    /// The label for an original with no readable title of its own.
    let unavailableChoice: String
    let tint: Color
}

nonisolated enum FieldEventPageAccessibilityID10868 {
    static let page = "fieldEventPage10868.page"
    static let hero = "fieldEventPage10868.hero"
    static let headlineUnavailable = "fieldEventPage10868.headline.unavailable"
    static let anchor = "fieldEventPage10868.anchor"
    static let stories = "fieldEventPage10868.stories"
    static let allProps = "fieldEventPage10868.allProps"
    static let unavailable = "fieldEventPage10868.story.unavailable"
    static let readerHeader = "fieldEventPage10868.readerHeader"
    static let readerAbout = "fieldEventPage10868.readerHeader.about"
    static let catalogue = "fieldEventPage10868.catalogue"
    static let original = "fieldEventPage10868.original"
    static let about = "fieldEventPage10868.about"
    static func card(_ card: FieldEventPageCard10868) -> String { "fieldEventPage10868.card.\(card.rawValue)" }
}

// MARK: - Page model

/// Which leaves the page mounts, resolved once per input.
nonisolated struct FieldEventPageModel10868: Equatable {
    let input: FieldEventPageInput10868

    init(_ input: FieldEventPageInput10868) {
        self.input = input
    }

    /// The headline at the page's own phase. Otherwise nothing.
    var headline: FieldHeadlineInput10868? {
        input.headline.phase == input.phase ? input.headline : nil
    }

    /// The field card at the page's own phase, never during: this screen has
    /// no live state for it.
    var field: FieldOutlookInput10868? {
        guard input.phase != .during, let field = input.field, field.phase == input.phase else { return nil }
        return field
    }

    /// The movement card at the page's own phase, never during.
    var movement: PreEventShiftInput10868? {
        guard input.phase != .during, let movement = input.movement, movement.phase == input.phase else { return nil }
        return movement
    }

    func isMounted(_ card: FieldEventPageCard10868) -> Bool {
        switch card {
        case .history: true
        case .field: field != nil
        case .movement: movement != nil
        }
    }

    /// The owner's link a stream card id names: exactly one link with that
    /// id, to a story this phase mounts. Otherwise nothing.
    func story(_ cardID: String) -> FieldEventPageStory10868? {
        let links = input.stories.filter { $0.cardID == cardID }
        guard links.count == 1, let link = links.first, link.card != .history, isMounted(link.card) else { return nil }
        return link
    }

    func storyCard(_ cardID: String) -> FieldEventPageCard10868? { story(cardID)?.card }

    /// Full-size content exists for the anchor and for a story this phase shows.
    func readerShows(_ card: FieldEventPageCard10868) -> Bool { isMounted(card) }

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

    /// The owner's About, when it carries readable words.
    var about: FieldEventPageAbout10868? {
        guard let about = input.about,
              Self.readable(about.title) != nil || about.paragraphs.contains(where: { Self.readable($0) != nil })
        else { return nil }
        return about
    }

    func aboutAvailable(canOpen: Bool) -> Bool {
        canOpen && about != nil
    }

    /// Whether `mode`'s compact heading shows the About entry: full-size
    /// content only — the page has the headline's own control.
    func aboutEntry(mode: FieldEventPageMode10868, canOpen: Bool) -> Bool {
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
    static func arrangements(sizeClass: UserInterfaceSizeClass?, accessibilitySize: Bool) -> [FieldEventPageArrangement10868] {
        sizeClass != .compact && !accessibilitySize ? [.sideBySide, .stacked] : [.stacked]
    }
}

// MARK: - About content

/// The owner's About in its own words. Static text; it acts on nothing.
struct FieldEventPageAboutContent10868: View {
    let about: FieldEventPageAbout10868

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            if let title = FieldEventPageModel10868.readable(about.title) {
                Text(title)
                    .font(.headline)
                    .foregroundStyle(DS.textPrimary)
                    .accessibilityAddTraits(.isHeader)
            }
            ForEach(Array(about.paragraphs.enumerated()), id: \.offset) { _, paragraph in
                if let words = FieldEventPageModel10868.readable(paragraph) {
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

struct FieldEventPagePresentation10868: View {
    typealias Stream = StoryStreamPresentation10868

    let input: FieldEventPageInput10868
    var mode: FieldEventPageMode10868 = .page
    /// The catalogue and Details modes' content; nil: neither has any.
    var originals: FieldEventPageOriginals10868? = nil
    /// Opens the host's container on the owner's About.
    var onAbout: (() -> Void)? = nil
    /// Opens the host's existing catalogue.
    var onAllProps: (() -> Void)? = nil
    /// A catalogue card's exact selection, for the host to hold and route.
    var onOriginalSelect: ((OriginalMarketDetails9483.Selection) -> Void)? = nil
    /// A Details history control's exact intent, for the host to route.
    var onOriginalHistory: ((OriginalMarketDetails9483.HistoryIntent) -> Void)? = nil
    var onStoryIntent: ((Stream.Intent) -> Void)? = nil
    /// A headline contender's exact open, for the host's history.
    var onHeadlineOpen: ((FieldMovementOpen10868) -> Void)? = nil
    var onHistoryAction: ((String) -> Void)? = nil
    var onHistoryInspectionChoice: ((String) -> Void)? = nil
    var onHistoryPlotPosition: ((Double) -> Void)? = nil
    /// The field card's exact chosen contender, for the host to hold.
    var onFieldChoose: ((FieldChooserOriginalRef10868) -> Void)? = nil
    /// The field card's exact original, for the host's Details.
    var onFieldOpenOriginal: ((FieldChooserOriginalRef10868) -> Void)? = nil
    /// The movement card's exact original and observation key, for the host's history.
    var onMovementOpen: ((FieldMovementOpen10868) -> Void)? = nil
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

    private var model: FieldEventPageModel10868 { FieldEventPageModel10868(input) }

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
    /// callback, so the leaf draws no About control.
    func aboutOpener() -> (() -> Void)? {
        guard model.aboutAvailable(canOpen: onAbout != nil), let onAbout else { return nil }
        return onAbout
    }

    /// The field headline, at the page's phase only. Its open and About pass
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

    /// `activation` is the stream's hook for a card in the stream; nil in
    /// full-size content.
    func fieldContent(activation: StoryStreamCardActivation10868? = nil) -> FieldOutlookBarsPresentation10868? {
        model.field.map {
            FieldOutlookBarsPresentation10868(
                input: $0,
                onChoose: Self.relay(onFieldChoose, through: activation),
                onOpenOriginal: Self.relay(onFieldOpenOriginal, through: activation)
            )
        }
    }

    func movementContent(activation: StoryStreamCardActivation10868? = nil) -> PreEventProbabilityShiftPresentation10868? {
        model.movement.map {
            PreEventProbabilityShiftPresentation10868(input: $0, onOpen: Self.relay(onMovementOpen, through: activation))
        }
    }

    /// The owner's About as static content.
    func aboutContent() -> FieldEventPageAboutContent10868? {
        model.about.map { FieldEventPageAboutContent10868(about: $0) }
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

    /// Full-size content's About: the exact callback, no hook.
    func openAbout() {
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
        .accessibilityIdentifier(FieldEventPageAccessibilityID10868.page)
    }

    /// The headline and the history in one panel: side by side where both fit
    /// at their minimum widths, otherwise the headline above the history.
    private var hero: some View {
        VStack(alignment: .leading, spacing: 0) {
            let arrangements = FieldEventPageModel10868.arrangements(
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
        .modifier(FieldEventPageCardSurface10868())
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(FieldEventPageAccessibilityID10868.hero)
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
                .accessibilityIdentifier(FieldEventPageAccessibilityID10868.headlineUnavailable)
        }
    }

    private var anchor: some View {
        historyContent(reader: false)
            .frame(maxWidth: .infinity, alignment: .leading)
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier(FieldEventPageAccessibilityID10868.anchor)
    }

    private var stories: some View {
        VStack(alignment: .leading, spacing: 16) {
            StoryStreamPresentationView10868(input.stream, onIntent: onStoryIntent) { card, activation in
                storyCell(card, activation)
            }
            if model.allPropsAvailable(canOpen: onAllProps != nil), let label = input.copy.allPropsLabel {
                allPropsEntry(label)
            }
        }
        .accessibilityElement(children: .contain)
        .accessibilityLabel(input.copy.storiesLabel)
        .accessibilityIdentifier(FieldEventPageAccessibilityID10868.stories)
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
            .modifier(FieldEventPageCardSurface10868())
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityIdentifier(FieldEventPageAccessibilityID10868.allProps)
    }

    /// The story the owner links to this stream card, with the stream's
    /// activation hook and the owner's reason words, or the owner's
    /// unavailable words.
    @ViewBuilder private func storyCell(_ card: Stream.Card, _ activation: StoryStreamCardActivation10868) -> some View {
        if let link = model.story(card.id) {
            VStack(alignment: .leading, spacing: 8) {
                if let reason = FieldEventPageModel10868.readable(link.reason) {
                    Text(reason)
                        .font(.subheadline)
                        .foregroundStyle(DS.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
                cardContent(link.card, activation: activation)
            }
            .padding(16)
            .frame(maxWidth: .infinity, alignment: .leading)
            .modifier(FieldEventPageCardSurface10868())
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier(FieldEventPageAccessibilityID10868.card(link.card))
        } else {
            Text(input.copy.storyUnavailable)
                .font(.subheadline)
                .foregroundStyle(DS.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
                .frame(maxWidth: .infinity, minHeight: 120, alignment: .leading)
                .padding(16)
                .modifier(FieldEventPageCardSurface10868())
                .accessibilityIdentifier(FieldEventPageAccessibilityID10868.unavailable)
        }
    }

    // MARK: Content shared by the page and the reader

    @ViewBuilder private func cardContent(_ card: FieldEventPageCard10868,
                                          activation: StoryStreamCardActivation10868?) -> some View {
        switch card {
        case .history: historyContent(reader: true)
        case .field: fieldContent(activation: activation)
        case .movement: movementContent(activation: activation)
        }
    }

    /// The same leaf and input, full size, for the host's existing reader,
    /// under the compact words. A card this phase does not show has no content.
    @ViewBuilder private func reader(_ card: FieldEventPageCard10868) -> some View {
        if model.readerShows(card) {
            VStack(alignment: .leading, spacing: 16) {
                compactHeader
                cardContent(card, activation: nil)
            }
        }
    }

    /// The owner's one-line words and, in full-size content, the About entry.
    private var compactHeader: some View {
        HStack(alignment: .top, spacing: 12) {
            VStack(alignment: .leading, spacing: 4) {
                Text(input.reader.title)
                    .font(.headline)
                    .foregroundStyle(DS.textPrimary)
                    .accessibilityAddTraits(.isHeader)
                if let state = FieldEventPageModel10868.readable(input.reader.state) {
                    Text(state)
                        .font(.subheadline)
                        .foregroundStyle(DS.textSecondary)
                }
            }
            .fixedSize(horizontal: false, vertical: true)
            .frame(maxWidth: .infinity, alignment: .leading)
            if model.aboutEntry(mode: mode, canOpen: onAbout != nil) {
                Button(action: openAbout) {
                    Image(systemName: "info.circle")
                        .font(.title3)
                        .foregroundStyle(DS.textPrimary)
                        .frame(minWidth: controlSize, minHeight: controlSize)
                        .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .accessibilityLabel(input.headline.copy.aboutLabel)
                .accessibilityHint(input.headline.copy.aboutHint ?? "")
                .accessibilityIdentifier(FieldEventPageAccessibilityID10868.readerAbout)
            }
        }
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(FieldEventPageAccessibilityID10868.readerHeader)
    }

    // MARK: All props, the selected original's Details and About

    /// The owner's admitted originals under the compact words.
    @ViewBuilder private var catalogueMode: some View {
        if let catalogue = catalogueContent() {
            VStack(alignment: .leading, spacing: 12) {
                compactHeader
                catalogue
            }
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier(FieldEventPageAccessibilityID10868.catalogue)
        }
    }

    /// The held original's existing Details, for the host's container.
    @ViewBuilder private var originalMode: some View {
        if let details = originalDetailsContent() {
            details
                .accessibilityElement(children: .contain)
                .accessibilityIdentifier(FieldEventPageAccessibilityID10868.original)
        }
    }

    /// The owner's About under the compact words, for the host's container.
    @ViewBuilder private var aboutMode: some View {
        if let content = aboutContent() {
            VStack(alignment: .leading, spacing: 12) {
                compactHeader
                content
            }
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier(FieldEventPageAccessibilityID10868.about)
        }
    }
}

/// The reference's white card on the page surface.
private struct FieldEventPageCardSurface10868: ViewModifier {
    func body(content: Content) -> some View {
        content
            .background(DS.cardBg, in: RoundedRectangle(cornerRadius: 20, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 20, style: .continuous).stroke(DS.border, lineWidth: 1))
    }
}
