import SwiftUI

// #10868 — the combat event screen (`mma`): one native presentation composed
// from the accepted leaves. The two fighters' win chances lead, at equal
// prominence. A fan sees, in this order: the fight headline (the owner's
// eyebrow, title and About entry, each named fighter's chance for the phase —
// before the fight the pre-fight chance; during it the pre-fight chance beside
// an admitted in-fight chance or its own unavailable words; after it the
// pre-fight chance beside the owner's reported official result — and the
// owner's fight state with its own clock) beside the fighters' win
// probability history; then the owner's story stream — finish method, fighter
// rounds, knockout chances and fight length — and the "All props" entry. The
// history and each story open as full-size content made of the same Views, and
// "All props", the held original's Details and the fight About are further
// content modes.
//
// Presentation only, composed from the approved `SpecializedHeadlines.tsx`
// (`CombatHeadline`, `CombatHeadlineFacts`), `CombatWinnerJourney.tsx` /
// `combatWinnerJourney.css` / `CombatChanceComparison.tsx`,
// `CombatOfficialResult.tsx`, `CombatStories.tsx` / `combatFocus.css`,
// `CombatOutcomeCards.tsx` and `CombatDurationCard.tsx`, over
// `combatWinnerHistory.ts`, `combatChartStart.ts`, `combatOfficialFinal.ts`,
// `combatPregame.ts`, `combatMomentStories.ts` and `combatCatalog.ts`, as
// mounted in `Atlas.tsx` (`mma`). The reference's fixture loaders, history
// qualification and five-minute segmentation, latest-before-start election,
// result-conflict rule, official-result qualification, title and rule
// matching, `combatMomentOrder` ranking and its reasons, catalogue family
// grouping, selection reducer, automatic cadence, story and reader session
// state, inspection state, "Aa Larger", sheets, dialogs and focus restoration
// are NOT ported. The leaves are the actual accepted Views:
//
//   • `FieldPhaseHeadlinePresentation10868` — the two named fighters;
//   • `FieldProbabilityHistoryPresentation10868` — the anchor;
//   • `CombatMethodPresentation10868` — "Finish method", and, separately
//     configured with its own input and words, "Knockout chances";
//   • `CombatRoundPresentation10868` — "Fighter rounds";
//   • `CombatDurationPresentation10868` — "Fight length";
//   • `StoryStreamPresentationView10868` — the controlled story stream;
//   • `OriginalMarketCatalogueView9483` / `OriginalMarketDetailsView9483` —
//     "All props" and the held original's Details.
//
// Nothing new is drawn here beyond arrangement, card surfaces, the owner's
// story and notice words, the compact reader heading and the About text with
// its source control.
//
// The page's phase is the owner's explicit `CombatEventPagePhase10868`, never
// read from a raw feed status, a clock, a round, a quote or the official
// result. The archived feed may still say "suspended" while the owner has
// admitted an official final; this layer does not reconcile them. A leaf is
// mounted only when its own phase is the page's and its own event is the
// page's. A leaf from another phase or event is not coerced into this one — it
// is not mounted, and a headline from another phase shows the owner's
// unavailable words. The headline's two fighters and the history's two traces
// are exactly what the owner supplies: independent originals, each with its
// own clock, or — for an admitted two-outcome Bain Luck blend — the owner's
// literal paired values and identities with their one shared clock, which the
// owner's own About, history and summary words name as the supplied aggregate
// and its complement. Every method, knockout, round and duration side is its
// own original. This layer never complements, normalizes or joins them, treats a
// missing value as zero, turns the official result into a 0/100 quote or a
// history point, reads a contract's grade from the official result, promotes a
// settlement-time or last quote to a current chance, adds an elapsed-in-round
// time to a listed start, or invents a round in progress, a projection or a
// finish marker. Each leaf keeps its own rules for that.
//
// The host supplies each leaf's own immutable input, already admitted for the
// same snapshot; this layer groups them and never re-elects, copies, filters
// or formats an observation, a result, a window, a marker or a word. The
// history keeps every series the owner admits — its name, shape, own values
// and times, its independent runs, window, inspection, scale and source
// controls; its domain, range, guides and breaks are the owner's. A series the
// owner admits only as absence words keeps them: no line is derived here for
// it from another series, and a headline side the owner admits no reading for
// keeps its own unavailable words.
//
// The story stream is the owner's: its cards, order, primary, companion,
// position, status, pending, playback, progress, previous/next, scope and
// reader-open flag, and its own "Open full card" entry. This layer wires each
// supplied card id to the one story the owner names for it, and shows the
// owner's unavailable words for an id that names no single story this phase
// mounts — never a neighbour. A card's own actions — selecting a side or
// opening its Details in any of the four cards — and a write to a card's
// timing disclosure first call the stream's activation hook (so the owner can
// hold) and then the host's exact callback or write. Reading a disclosure
// binding asks for nothing, and building a card asks for nothing. Full-size
// content reuses the same leaves with the host's exact callbacks and bindings
// and no activation, so opening a card never requests a hold by appearing,
// and closing one resumes nothing.
//
// The owner may also pass an interaction hook, so it can hold its stream
// before an action outside the stream lands (the reference holds the stream on
// a pointer-down or focus in its hero and originals panels). On the page — a
// headline fighter's open and the headline's About, the anchor history's
// actions, inspection choices and plot taps, the All props entry — and in the
// catalogue and Details content — a category, Show more, an original's
// selection and a Details history intent — the action calls that hook once and
// then the owner's exact callback with its exact value. Without a callback
// there is no action and no
// hook call; without a hook every callback is the owner's own. Building or
// reading the view calls nothing, and there is no resume. Full-size content,
// including the About and its source control, keeps the exact callbacks: its
// host already holds the stream while it is open. Stream cards keep the
// stream's own activation and never pass through the hook as well. A
// pointer-down on empty panel space, or focus moving into a panel, is not
// intercepted here; that stays with the host's containment.
//
// The full-size history is the same history input with its expanded layout
// and without its expand control; every series, run, guide, break, selection,
// readout, window, scale, range, inspection and other control is unchanged.
//
// The fight About is the owner's text — its pre-fight, official-result and
// history-and-source sections — reached through the headline's own About
// control and the readers' compact heading. A section's source control hands
// the owner its exact source; this layer opens nothing. With no About text or
// no callback there is no control.
//
// All props may carry the owner's category controls (All, Winner, Finish
// method, Fighter rounds, Knockout chances, Fight length) above the unchanged
// catalogue leaf, and its count words and Show more below. The catalogue holds
// exactly the rows the owner admits for its current category and page, in its
// order. Nothing here filters, classifies, groups, slices, fetches or pages
// them, or clears or elects a held original when the category or page
// changes: a category or Show more hands the owner its exact intent id. The
// count words are the owner's and describe the rows it supplied. A control
// without a callback, unavailable, or whose id is blank or shared with another
// category or Show more, is static words, never a button; blank words draw
// nothing. The categories wrap in an adaptive grid of equal-width, ≥ 44 pt
// controls, one full-width control per row at accessibility sizes; a selected
// one shows a checkmark and a heavier outline and is spoken as selected. With
// no controls the catalogue is exactly as before. The Details mode hands the
// actual Details leaf the owner's optional recorded history for the held
// original and its history intent callback, unchanged; without them it is the
// existing summary-only Details.
//
// Phone stacks the headline above the history, then the stories. A regular
// or unspecified size class (a Mac window) places the headline beside the
// history while both keep their minimum widths, otherwise it stacks too;
// accessibility sizes always stack. The stories run full width below.
//
// The host owns the scroll, navigation, sheets, Back/Done, paging and swipe,
// focus, routing to and from the catalogue, an original's Details and the
// About, the catalogue's category and page, each card's selected side and
// timing disclosure, the held/received frame, how a hook request holds the
// stream, live subscriptions and every
// genuine update. This view keeps no state, runs no timer or animation, holds
// no subscription and presents no sheet or navigation of its own. Every
// callback is the host's own closure handed to the leaf unchanged. With no
// callback, nothing pretends to act.
//
// Host binding still owed — not available at this base: an owner that admits,
// for one bout snapshot, the phase, the headline originals and fight state,
// the history with its guides at or before that snapshot, each story leaf's
// input, the reader heading, the story stream and its card-to-story map, the
// About text and its sources, the originals group with any admitted recorded
// history and its category and page controls, and maps every callback to its
// existing controls — including from a card's exact original reference to the
// Details selection it names, and from the blend's opaque display identities
// to the history it opens.

/// The owner's explicit phase for the whole screen.
nonisolated enum CombatEventPagePhase10868: String, Hashable, CaseIterable {
    case before
    case during
    case final
}

/// One card the page can show full size. `history` is the anchor.
nonisolated enum CombatEventPageCard10868: String, Hashable, CaseIterable {
    case history
    /// "Finish method".
    case methods
    /// "Fighter rounds".
    case rounds
    /// "Knockout chances": the method tiles with the owner's fighter rows.
    case knockout
    /// "Fight length".
    case duration
}

/// What the host's container is showing, chosen by the host.
nonisolated enum CombatEventPageMode10868: Equatable {
    /// The fight screen body.
    case page
    /// One card's full-size content.
    case reader(CombatEventPageCard10868)
    /// Every retained original ("All props").
    case catalogue
    /// The held original's Details.
    case original
    /// The owner's fight About.
    case about
}

nonisolated enum CombatEventPageArrangement10868: Equatable {
    case stacked
    case sideBySide
}

// MARK: - Page input

/// The owner's one-line fight words above full-size content.
nonisolated struct CombatEventPageReaderHeader10868: Equatable {
    /// "Kopylov won · TKO · R1, 3:12".
    let title: String
    /// "Last pre-match · Gautier 67.2% · Kopylov 32.8%"; nil draws none.
    let state: String?
}

/// The owner's link from one stream card id to the story it shows.
nonisolated struct CombatEventPageStory10868: Equatable {
    /// Exactly as in `StoryStreamPresentation10868.cards`.
    let cardID: String
    let card: CombatEventPageCard10868
    /// The owner's words for why this story is here ("Kopylov’s KO/TKO win
    /// had a 12.5% pre-fight chance."); nil draws none.
    var reason: String? = nil
}

/// One source the owner names in its About, handed back exactly on open.
nonisolated struct CombatEventPageSource10868: Equatable {
    /// The owner's stable id.
    let id: String
    /// "Official UFC result".
    let label: String
    let url: URL
}

/// One section of the owner's About, verbatim.
nonisolated struct CombatEventPageAboutSection10868: Equatable {
    /// "Official bout result".
    let title: String
    let paragraphs: [String]
    /// The section's source control; nil draws none.
    var source: CombatEventPageSource10868? = nil
}

/// The owner's fight About, verbatim.
nonisolated struct CombatEventPageAbout10868: Equatable {
    /// "About this fight".
    let title: String
    let sections: [CombatEventPageAboutSection10868]
}

nonisolated struct CombatEventPageCopy10868: Equatable {
    /// Spoken name of the stories group ("Fight stories").
    let storiesLabel: String
    /// Shown in a stream cell whose id names no single story this phase shows.
    let storyUnavailable: String
    /// Shown in place of a headline whose phase is not the page's.
    let headlineUnavailable: String
    /// "All 31 original props"; nil draws no entry.
    let allPropsLabel: String?
}

nonisolated struct CombatEventPageInput10868: Equatable {
    let phase: CombatEventPagePhase10868
    /// The bout every card must name.
    let eventID: String
    let reader: CombatEventPageReaderHeader10868
    let headline: FieldHeadlineInput10868
    /// The owner's status words under the headline ("Refreshing · recorded
    /// history retained"); nil draws none.
    var notice: String? = nil
    let history: FieldHistoryInput10868
    /// "Finish method".
    let methods: CombatMethodInput10868?
    /// "Fighter rounds".
    let rounds: CombatRoundInput10868?
    /// "Knockout chances": its own input and words, never the methods'.
    let knockout: CombatMethodInput10868?
    /// "Fight length".
    let duration: CombatDurationInput10868?
    /// The owner's story stream; nil draws no stories.
    let stream: StoryStreamPresentation10868?
    let stories: [CombatEventPageStory10868]
    /// Opened by the headline's About control; nil: no control.
    let about: CombatEventPageAbout10868?
    let copy: CombatEventPageCopy10868
}

/// One owner category above "All props" ("Finish method"): its exact intent
/// id, words and availability, and whether the owner has it selected.
nonisolated struct CombatEventPageCatalogueCategory10868: Equatable {
    let action: FieldHistoryAction10868
    let isSelected: Bool
}

/// The owner's controls around "All props". Which originals the catalogue
/// holds — the category's rows, their order and how many — is the owner's;
/// these controls only hand back its intents.
nonisolated struct CombatEventPageCatalogueControls10868: Equatable {
    /// Spoken name of the category group ("Fight market category").
    let categoriesLabel: String
    let categories: [CombatEventPageCatalogueCategory10868]
    /// "Show more · 25 remaining"; nil draws none.
    var more: FieldHistoryAction10868? = nil
    /// The owner's words for the rows it supplied ("Showing 6 of 31
    /// originals"); nil draws none.
    var context: String? = nil
}

nonisolated enum CombatEventPageControlArrangement10868: Equatable {
    /// An adaptive grid: as many equal columns as fit, wrapping onto new rows.
    case wrapping
    /// One full-width control per row.
    case stacked
}

/// The owner's retained originals behind "All props", for the catalogue and
/// Details modes. Every field reaches the existing leaves unchanged.
struct CombatEventPageOriginals10868 {
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
    /// "31 retained originals"; nil draws none.
    var context: String? = nil
    /// "No retained originals for this fight".
    let emptyWords: String
    /// The label for an original with no readable title of its own.
    let unavailableChoice: String
    let tint: Color
    /// The category, count and Show more controls; nil draws none.
    var controls: CombatEventPageCatalogueControls10868? = nil
}

nonisolated enum CombatEventPageAccessibilityID10868 {
    static let page = "combatEventPage10868.page"
    static let hero = "combatEventPage10868.hero"
    static let headlineUnavailable = "combatEventPage10868.headline.unavailable"
    static let notice = "combatEventPage10868.notice"
    static let anchor = "combatEventPage10868.anchor"
    static let stories = "combatEventPage10868.stories"
    static let allProps = "combatEventPage10868.allProps"
    static let unavailable = "combatEventPage10868.story.unavailable"
    static let readerHeader = "combatEventPage10868.readerHeader"
    static let readerAbout = "combatEventPage10868.readerHeader.about"
    static let catalogue = "combatEventPage10868.catalogue"
    static let original = "combatEventPage10868.original"
    static let about = "combatEventPage10868.about"
    static let categories = "combatEventPage10868.catalogue.categories"
    static let catalogueContext = "combatEventPage10868.catalogue.context"
    static let more = "combatEventPage10868.catalogue.more"
    static func category(_ id: String) -> String { "combatEventPage10868.catalogue.category.\(id)" }
    static func card(_ card: CombatEventPageCard10868) -> String { "combatEventPage10868.card.\(card.rawValue)" }
    static func source(_ id: String) -> String { "combatEventPage10868.about.source.\(id)" }
}

// MARK: - Page model

/// Which leaves the page mounts, resolved once per input.
nonisolated struct CombatEventPageModel10868: Equatable {
    let input: CombatEventPageInput10868

    init(_ input: CombatEventPageInput10868) {
        self.input = input
    }

    static func headlinePhase(_ phase: CombatEventPagePhase10868) -> FieldOutlookPhase10868 {
        switch phase {
        case .before: .before
        case .during: .during
        case .final: .final
        }
    }

    static func methodPhase(_ phase: CombatEventPagePhase10868) -> CombatMethodPhase10868 {
        switch phase {
        case .before: .before
        case .during: .during
        case .final: .final
        }
    }

    static func roundPhase(_ phase: CombatEventPagePhase10868) -> CombatRoundPhase10868 {
        switch phase {
        case .before: .before
        case .during: .during
        case .final: .final
        }
    }

    static func durationPhase(_ phase: CombatEventPagePhase10868) -> CombatDurationPhase10868 {
        switch phase {
        case .before: .before
        case .during: .during
        case .final: .final
        }
    }

    /// The headline at the page's own phase. Otherwise nothing.
    var headline: FieldHeadlineInput10868? {
        input.headline.phase == Self.headlinePhase(input.phase) ? input.headline : nil
    }

    /// Finish method at the page's own phase and bout.
    var methods: CombatMethodInput10868? {
        guard let methods = input.methods, methods.phase == Self.methodPhase(input.phase),
              methods.eventID == input.eventID else { return nil }
        return methods
    }

    /// Fighter rounds at the page's own phase and bout.
    var rounds: CombatRoundInput10868? {
        guard let rounds = input.rounds, rounds.phase == Self.roundPhase(input.phase),
              rounds.eventID == input.eventID else { return nil }
        return rounds
    }

    /// Knockout chances at the page's own phase and bout.
    var knockout: CombatMethodInput10868? {
        guard let knockout = input.knockout, knockout.phase == Self.methodPhase(input.phase),
              knockout.eventID == input.eventID else { return nil }
        return knockout
    }

    /// Fight length at the page's own phase and bout.
    var duration: CombatDurationInput10868? {
        guard let duration = input.duration, duration.phase == Self.durationPhase(input.phase),
              duration.eventID == input.eventID else { return nil }
        return duration
    }

    func isMounted(_ card: CombatEventPageCard10868) -> Bool {
        switch card {
        case .history: true
        case .methods: methods != nil
        case .rounds: rounds != nil
        case .knockout: knockout != nil
        case .duration: duration != nil
        }
    }

    /// The owner's link a stream card id names: exactly one link with that
    /// id, to a story this phase mounts. Otherwise nothing.
    func story(_ cardID: String) -> CombatEventPageStory10868? {
        let links = input.stories.filter { $0.cardID == cardID }
        guard links.count == 1, let link = links.first, link.card != .history, isMounted(link.card) else { return nil }
        return link
    }

    func storyCard(_ cardID: String) -> CombatEventPageCard10868? { story(cardID)?.card }

    /// Full-size content exists for the anchor and for a story this phase shows.
    func readerShows(_ card: CombatEventPageCard10868) -> Bool { isMounted(card) }

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
    var about: CombatEventPageAbout10868? {
        guard let about = input.about,
              Self.readable(about.title) != nil || about.sections.contains(where: Self.hasWords)
        else { return nil }
        return about
    }

    static func hasWords(_ section: CombatEventPageAboutSection10868) -> Bool {
        readable(section.title) != nil || section.paragraphs.contains { readable($0) != nil }
    }

    func aboutAvailable(canOpen: Bool) -> Bool {
        canOpen && about != nil
    }

    /// Whether `mode`'s compact heading shows the About entry: full-size
    /// content only — the page has the headline's own control.
    func aboutEntry(mode: CombatEventPageMode10868, canOpen: Bool) -> Bool {
        guard case .reader = mode, Self.readable(input.headline.copy.aboutLabel) != nil else { return false }
        return aboutAvailable(canOpen: canOpen)
    }

    /// A section's source control acts only with readable words and a callback.
    static func sourceIsLive(_ source: CombatEventPageSource10868?, canOpen: Bool) -> Bool {
        guard let source else { return false }
        return canOpen && readable(source.label) != nil
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
    static func arrangements(sizeClass: UserInterfaceSizeClass?, accessibilitySize: Bool) -> [CombatEventPageArrangement10868] {
        sizeClass != .compact && !accessibilitySize ? [.sideBySide, .stacked] : [.stacked]
    }

    // MARK: Catalogue controls

    /// Every catalogue control's action — categories and Show more — in one id space.
    static func catalogueActions(_ controls: CombatEventPageCatalogueControls10868) -> [FieldHistoryAction10868] {
        controls.categories.map(\.action) + [controls.more].compactMap { $0 }
    }

    /// Not drawn without readable words. A button handing back this exact id
    /// only with a callback, when available, and when its id is nonblank and
    /// unique among the controls; otherwise static words.
    static func catalogueControlState(_ action: FieldHistoryAction10868?,
                                      in controls: CombatEventPageCatalogueControls10868,
                                      hasCallback: Bool) -> FieldHistoryControlState10868 {
        guard let action, readable(action.label) != nil else { return .hidden }
        guard hasCallback, action.isAvailable, readable(action.id) != nil,
              catalogueActions(controls).filter({ $0.id == action.id }).count == 1
        else { return .shownStatic }
        return .live(id: action.id)
    }

    /// The categories drawn, in the owner's order.
    static func shownCategories(_ controls: CombatEventPageCatalogueControls10868,
                                hasCallback: Bool) -> [CombatEventPageCatalogueCategory10868] {
        controls.categories.filter { catalogueControlState($0.action, in: controls, hasCallback: hasCallback) != .hidden }
    }

    /// Accessibility sizes stack the categories one per row; every other size
    /// wraps them, never a squeezed single row.
    static func categoryArrangement(accessibilitySize: Bool) -> CombatEventPageControlArrangement10868 {
        accessibilitySize ? .stacked : .wrapping
    }
}

// MARK: - About content

/// The owner's fight About in its own words. Each section's source control
/// hands the owner its exact source; with no callback the source is words.
struct CombatEventPageAboutContent10868: View {
    let about: CombatEventPageAbout10868
    var onSource: ((CombatEventPageSource10868) -> Void)? = nil

    @ScaledMetric(relativeTo: .body) private var controlSize: CGFloat = 44

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            if let title = CombatEventPageModel10868.readable(about.title) {
                Text(title)
                    .font(.headline)
                    .foregroundStyle(DS.textPrimary)
                    .accessibilityAddTraits(.isHeader)
            }
            ForEach(Array(about.sections.enumerated()), id: \.offset) { _, section in
                if CombatEventPageModel10868.hasWords(section) {
                    VStack(alignment: .leading, spacing: 6) {
                        if let title = CombatEventPageModel10868.readable(section.title) {
                            Text(title)
                                .font(.body.weight(.semibold))
                                .foregroundStyle(DS.textPrimary)
                                .accessibilityAddTraits(.isHeader)
                        }
                        ForEach(Array(section.paragraphs.enumerated()), id: \.offset) { _, paragraph in
                            if let words = CombatEventPageModel10868.readable(paragraph) {
                                Text(words)
                                    .font(.body)
                                    .foregroundStyle(DS.textPrimary)
                            }
                        }
                        sourceControl(section.source)
                    }
                }
            }
        }
        .fixedSize(horizontal: false, vertical: true)
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    /// The section's exact source for the host to open, or its words.
    func sourceAction(_ source: CombatEventPageSource10868?) -> (() -> Void)? {
        guard let source, CombatEventPageModel10868.sourceIsLive(source, canOpen: onSource != nil),
              let onSource else { return nil }
        return { onSource(source) }
    }

    @ViewBuilder private func sourceControl(_ source: CombatEventPageSource10868?) -> some View {
        if let source, let label = CombatEventPageModel10868.readable(source.label) {
            if let action = sourceAction(source) {
                Button(action: action) {
                    HStack(spacing: 6) {
                        Text(label)
                            .font(.body.weight(.semibold))
                            .fixedSize(horizontal: false, vertical: true)
                        Image(systemName: "arrow.up.right")
                            .font(.body.weight(.semibold))
                            .accessibilityHidden(true)
                    }
                    .foregroundStyle(DS.blue)
                    .frame(minHeight: controlSize)
                    .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .accessibilityAddTraits(.isLink)
                .accessibilityIdentifier(CombatEventPageAccessibilityID10868.source(source.id))
            } else {
                Text(label)
                    .font(.subheadline)
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
                    .accessibilityIdentifier(CombatEventPageAccessibilityID10868.source(source.id))
            }
        }
    }
}

// MARK: - Page view

struct CombatEventPagePresentation10868: View {
    typealias Stream = StoryStreamPresentation10868

    let input: CombatEventPageInput10868
    var mode: CombatEventPageMode10868 = .page
    /// The catalogue and Details modes' content; nil: neither has any.
    var originals: CombatEventPageOriginals10868? = nil
    /// Opens the host's container on the owner's About.
    var onAbout: (() -> Void)? = nil
    /// An About section's exact source, for the host to open.
    var onAboutSource: ((CombatEventPageSource10868) -> Void)? = nil
    /// Opens the host's existing catalogue.
    var onAllProps: (() -> Void)? = nil
    /// A catalogue card's exact selection, for the host to hold and route.
    var onOriginalSelect: ((OriginalMarketDetails9483.Selection) -> Void)? = nil
    /// A Details history control's exact intent, for the host to route.
    var onOriginalHistory: ((OriginalMarketDetails9483.HistoryIntent) -> Void)? = nil
    /// A category's exact intent id, for the host to choose its rows.
    var onCatalogueCategory: ((String) -> Void)? = nil
    /// Show more's exact intent id, for the host to admit its next rows.
    var onCatalogueMore: ((String) -> Void)? = nil
    var onStoryIntent: ((Stream.Intent) -> Void)? = nil
    /// A headline fighter's exact open, for the host's history.
    var onHeadlineOpen: ((FieldMovementOpen10868) -> Void)? = nil
    var onHistoryAction: ((String) -> Void)? = nil
    var onHistoryInspectionChoice: ((String) -> Void)? = nil
    var onHistoryPlotPosition: ((Double) -> Void)? = nil
    var onMethodSelect: ((CombatMethodOriginalRef10868) -> Void)? = nil
    var onMethodDetails: ((CombatMethodOriginalRef10868) -> Void)? = nil
    /// Page-owned; nil shows the card's timing already expanded.
    var methodTimingExpanded: Binding<Bool>? = nil
    var onRoundSelect: ((CombatRoundOriginalRef10868) -> Void)? = nil
    var onRoundDetails: ((CombatRoundOriginalRef10868) -> Void)? = nil
    var roundTimingExpanded: Binding<Bool>? = nil
    var onKnockoutSelect: ((CombatMethodOriginalRef10868) -> Void)? = nil
    var onKnockoutDetails: ((CombatMethodOriginalRef10868) -> Void)? = nil
    var knockoutTimingExpanded: Binding<Bool>? = nil
    var onDurationSelect: ((CombatDurationOriginalRef10868) -> Void)? = nil
    var onDurationDetails: ((CombatDurationOriginalRef10868) -> Void)? = nil
    var durationTimingExpanded: Binding<Bool>? = nil
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
    @ScaledMetric(relativeTo: .body) private var categoryMinWidth: CGFloat = 140

    private var model: CombatEventPageModel10868 { CombatEventPageModel10868(input) }

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

    /// The fight headline, at the page's phase only. Its open and About pass
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
    func methodsContent(activation: StoryStreamCardActivation10868? = nil) -> CombatMethodPresentation10868? {
        model.methods.map {
            CombatMethodPresentation10868(
                input: $0,
                onSelect: Self.relay(onMethodSelect, through: activation),
                onDetails: Self.relay(onMethodDetails, through: activation),
                timingExpanded: Self.relayBinding(methodTimingExpanded, through: activation)
            )
        }
    }

    func roundsContent(activation: StoryStreamCardActivation10868? = nil) -> CombatRoundPresentation10868? {
        model.rounds.map {
            CombatRoundPresentation10868(
                input: $0,
                onSelect: Self.relay(onRoundSelect, through: activation),
                onDetails: Self.relay(onRoundDetails, through: activation),
                timingExpanded: Self.relayBinding(roundTimingExpanded, through: activation)
            )
        }
    }

    /// The same method tiles, with the knockout card's own input, words,
    /// callbacks and disclosure.
    func knockoutContent(activation: StoryStreamCardActivation10868? = nil) -> CombatMethodPresentation10868? {
        model.knockout.map {
            CombatMethodPresentation10868(
                input: $0,
                onSelect: Self.relay(onKnockoutSelect, through: activation),
                onDetails: Self.relay(onKnockoutDetails, through: activation),
                timingExpanded: Self.relayBinding(knockoutTimingExpanded, through: activation)
            )
        }
    }

    func durationContent(activation: StoryStreamCardActivation10868? = nil) -> CombatDurationPresentation10868? {
        model.duration.map {
            CombatDurationPresentation10868(
                input: $0,
                onSelect: Self.relay(onDurationSelect, through: activation),
                onDetails: Self.relay(onDurationDetails, through: activation),
                timingExpanded: Self.relayBinding(durationTimingExpanded, through: activation)
            )
        }
    }

    /// The owner's About with its exact source callback — content the host
    /// already holds, so no hook.
    func aboutContent() -> CombatEventPageAboutContent10868? {
        model.about.map { CombatEventPageAboutContent10868(about: $0, onSource: onAboutSource) }
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

    /// A catalogue control's exact owner intent after the interaction hook;
    /// nil when it is not a live control.
    private func catalogueAction(_ action: FieldHistoryAction10868?, _ callback: ((String) -> Void)?) -> (() -> Void)? {
        guard let controls = originals?.controls,
              case .live(let id) = CombatEventPageModel10868.catalogueControlState(action, in: controls, hasCallback: callback != nil),
              let send = Self.held(callback, by: onInteraction)
        else { return nil }
        return { send(id) }
    }

    func categoryAction(_ category: CombatEventPageCatalogueCategory10868) -> (() -> Void)? {
        catalogueAction(category.action, onCatalogueCategory)
    }

    func moreAction() -> (() -> Void)? {
        catalogueAction(originals?.controls?.more, onCatalogueMore)
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
        .accessibilityIdentifier(CombatEventPageAccessibilityID10868.page)
    }

    /// The headline and the history in one panel: side by side where both fit
    /// at their minimum widths, otherwise the headline above the history.
    private var hero: some View {
        VStack(alignment: .leading, spacing: 0) {
            let arrangements = CombatEventPageModel10868.arrangements(
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
        .modifier(CombatEventPageCardSurface10868())
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(CombatEventPageAccessibilityID10868.hero)
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
                    .accessibilityIdentifier(CombatEventPageAccessibilityID10868.headlineUnavailable)
            }
            if let notice = CombatEventPageModel10868.readable(input.notice) {
                Text(notice)
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .accessibilityIdentifier(CombatEventPageAccessibilityID10868.notice)
            }
        }
    }

    private var anchor: some View {
        historyContent(reader: false)
            .frame(maxWidth: .infinity, alignment: .leading)
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier(CombatEventPageAccessibilityID10868.anchor)
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
                    .accessibilityIdentifier(CombatEventPageAccessibilityID10868.stories)
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
                        .padding(.horizontal, 16)
                        .frame(minHeight: controlSize)
                        .modifier(CombatEventPageCardSurface10868())
                        .contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                    .accessibilityIdentifier(CombatEventPageAccessibilityID10868.allProps)
                }
            }
        }
    }

    /// The story the owner links to this stream card, with the stream's
    /// activation hook and the owner's reason words, or the owner's
    /// unavailable words.
    @ViewBuilder private func storyCell(_ card: Stream.Card, _ activation: StoryStreamCardActivation10868) -> some View {
        if let link = model.story(card.id) {
            VStack(alignment: .leading, spacing: 8) {
                if let reason = CombatEventPageModel10868.readable(link.reason) {
                    Text(reason)
                        .font(.subheadline)
                        .foregroundStyle(DS.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
                cardContent(link.card, activation: activation)
            }
            .padding(16)
            .frame(maxWidth: .infinity, alignment: .leading)
            .modifier(CombatEventPageCardSurface10868())
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier(CombatEventPageAccessibilityID10868.card(link.card))
        } else {
            Text(input.copy.storyUnavailable)
                .font(.subheadline)
                .foregroundStyle(DS.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
                .frame(maxWidth: .infinity, minHeight: 120, alignment: .leading)
                .padding(16)
                .modifier(CombatEventPageCardSurface10868())
                .accessibilityIdentifier(CombatEventPageAccessibilityID10868.unavailable)
        }
    }

    // MARK: Content shared by the page and the reader

    @ViewBuilder private func cardContent(_ card: CombatEventPageCard10868,
                                          activation: StoryStreamCardActivation10868?) -> some View {
        switch card {
        case .history: historyContent(reader: true)
        case .methods: methodsContent(activation: activation)
        case .rounds: roundsContent(activation: activation)
        case .knockout: knockoutContent(activation: activation)
        case .duration: durationContent(activation: activation)
        }
    }

    /// The same leaf and input, full size, for the host's existing reader,
    /// under the compact fight words. A card this phase does not show has no
    /// content.
    @ViewBuilder private func reader(_ card: CombatEventPageCard10868) -> some View {
        if model.readerShows(card) {
            VStack(alignment: .leading, spacing: 16) {
                compactHeader
                cardContent(card, activation: nil)
            }
        }
    }

    /// The owner's one-line fight words and, in full-size content, the About
    /// entry.
    private var compactHeader: some View {
        HStack(alignment: .top, spacing: 12) {
            VStack(alignment: .leading, spacing: 4) {
                Text(input.reader.title)
                    .font(.headline)
                    .foregroundStyle(DS.textPrimary)
                    .accessibilityAddTraits(.isHeader)
                if let state = CombatEventPageModel10868.readable(input.reader.state) {
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
                .accessibilityIdentifier(CombatEventPageAccessibilityID10868.readerAbout)
            }
        }
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(CombatEventPageAccessibilityID10868.readerHeader)
    }

    // MARK: All props, the held original's Details and About

    /// The owner's admitted originals under the compact fight words, with the
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
            .accessibilityIdentifier(CombatEventPageAccessibilityID10868.catalogue)
        }
    }

    @ViewBuilder private func categoryControls(_ controls: CombatEventPageCatalogueControls10868) -> some View {
        let shown = CombatEventPageModel10868.shownCategories(controls, hasCallback: onCatalogueCategory != nil)
        if !shown.isEmpty {
            Group {
                switch CombatEventPageModel10868.categoryArrangement(accessibilitySize: typeSize.isAccessibilitySize) {
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
            .accessibilityIdentifier(CombatEventPageAccessibilityID10868.categories)
        }
    }

    @ViewBuilder private func categoryControl(_ category: CombatEventPageCatalogueCategory10868) -> some View {
        let spoken = category.action.spokenLabel ?? category.action.label
        if let action = categoryAction(category) {
            Button(action: action) { categoryFace(category) }
                .buttonStyle(.plain)
                .accessibilityLabel(spoken)
                .accessibilityAddTraits(category.isSelected ? .isSelected : [])
                .accessibilityIdentifier(CombatEventPageAccessibilityID10868.category(category.action.id))
        } else {
            categoryFace(category)
                .accessibilityElement(children: .ignore)
                .accessibilityLabel(spoken)
                .accessibilityAddTraits(category.isSelected ? .isSelected : [])
                .accessibilityIdentifier(CombatEventPageAccessibilityID10868.category(category.action.id))
        }
    }

    /// Selected: a checkmark and a heavier outline, not colour alone.
    /// Unavailable: secondary words and a dashed outline.
    private func categoryFace(_ category: CombatEventPageCatalogueCategory10868) -> some View {
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
    @ViewBuilder private func pagingControls(_ controls: CombatEventPageCatalogueControls10868) -> some View {
        let context = CombatEventPageModel10868.readable(controls.context)
        let more = controls.more
        let moreState = CombatEventPageModel10868.catalogueControlState(more, in: controls, hasCallback: onCatalogueMore != nil)
        if context != nil || moreState != .hidden {
            VStack(alignment: .leading, spacing: 8) {
                if let context {
                    Text(context)
                        .font(.subheadline)
                        .foregroundStyle(DS.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                        .accessibilityIdentifier(CombatEventPageAccessibilityID10868.catalogueContext)
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
                                .modifier(CombatEventPageCardSurface10868())
                                .contentShape(Rectangle())
                        }
                        .buttonStyle(.plain)
                        .accessibilityLabel(more.spokenLabel ?? more.label)
                        .accessibilityIdentifier(CombatEventPageAccessibilityID10868.more)
                    } else {
                        Text(more.label)
                            .font(.subheadline)
                            .foregroundStyle(DS.textSecondary)
                            .fixedSize(horizontal: false, vertical: true)
                            .accessibilityLabel(more.spokenLabel ?? more.label)
                            .accessibilityIdentifier(CombatEventPageAccessibilityID10868.more)
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
                .accessibilityIdentifier(CombatEventPageAccessibilityID10868.original)
        }
    }

    /// The owner's About under the compact fight words, for the host's container.
    @ViewBuilder private var aboutMode: some View {
        if let content = aboutContent() {
            VStack(alignment: .leading, spacing: 12) {
                compactHeader
                content
            }
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier(CombatEventPageAccessibilityID10868.about)
        }
    }
}

/// The reference's white card on the page surface.
private struct CombatEventPageCardSurface10868: ViewModifier {
    func body(content: Content) -> some View {
        content
            .background(DS.cardBg, in: RoundedRectangle(cornerRadius: 20, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 20, style: .continuous).stroke(DS.border, lineWidth: 1))
    }
}
