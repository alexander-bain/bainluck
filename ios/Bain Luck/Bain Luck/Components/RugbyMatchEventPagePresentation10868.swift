import SwiftUI

// #10868 — the match page for the EXISTING rugby-match route: one native
// presentation composed from the accepted shared leaves.
//
// PILLARS: FORMATTING / TRUTH / DISCOVER. SHIP: the native rugby page keeps both
// team win chances and the draw readable, independently dated and explorable,
// then compares the winner's pre-match and lowest recorded chance with the
// separately reported final score in a full-size story.
//
// A reader sees, in this order: the owner's match headline (phase eyebrow,
// "<team> vs <team>", each outcome — each team and the draw — with its own
// pre-match chance; during the match the recorded chance beside it at the same
// size; after the match the separately reported final beside it; the owner's
// state line and a compact About control); every outcome's dated readouts as
// the history resolves them, each figure at one scaled figure size, above the
// tall, named, shape-keyed win probability history; on a phone,
// a compact probability context the host may pin (each outcome's own pre-match
// slot, as the history resolves it, and "Chart"); after the match only, the
// chance-to-result story; then every original market by its exact identity.
//
// Presentation only, from the approved `RugbyMatch.tsx`, `RugbyHistoryPlot.tsx`,
// `RetainedMatchHeadlineViews.tsx`, `MatchChanceComparison.tsx`,
// `MatchReadingContext.tsx`, `rugbyMatch.css` and the native readable/wide
// comparison records. Their evidence loader, validators, outcome and baseline
// election, lowest-close election, score reading, ticker parsing, archive
// clock, date and percentage formatting, normalization, segmentation and
// subscription/replay policy are NOT ported. The leaves are the actual
// accepted Views:
//
//   • `FieldPhaseHeadlinePresentation10868` — the primary outcome readings;
//   • `FieldProbabilityHistoryPresentation10868` — the history, its exact-minute
//     inspection and its owner runs; its readouts, resolved by
//     `FieldHistoryGeometry10868.readoutSlots`, are laid out by the small
//     comparison View below at the approved equal scaled figure size;
//   • `HistoricalChanceResultPresentation10868` — the final story;
//   • `OriginalMarketChooserView9483`, `OriginalMarketCatalogueView9483` and
//     `OriginalMarketDetailsView9483` — every original and the held one.
//
// Nothing here decides a value, a date, a comparison or a label. The phase is
// the owner's explicit input, never read from a clock, a trade, a score or a
// result. Every figure, clock, label, provenance, score and result word is
// the owner's string, shown verbatim. Independently timed outcome readings are
// never normalized, summed, complemented, synchronized or called a blend; a
// minute close is never an intraminute low, a current chance or a chance at a
// scoring moment; the reported final is never a point, a probability or a
// contract result. Lines join only what the owner's runs join — adjacent
// traded minutes — and nothing extends a line to a settled end. An inspected
// minute shows each original's own exact observation or the owner's words,
// never a neighbour or a value carried forward.
//
// Phase gates, from the owner's phase only: the headline mounts while its own
// phase is the page's; the story mounts after the match only, while its own
// phase is the final. The page shows the owner's Info, source and original text
// verbatim and decides nothing about when a fact became known: the owner
// supplies phase-appropriate text — before the match no later quote, score,
// lowest close or result; during the match no final report, score or result —
// and this layer never parses or filters prose.
//
// Exact hand-offs. Opening an original from the headline hands back the
// headline's own `FieldMovementOpen10868` (the exact original, with its recorded
// observation key during the match only). Inspecting a pre-match chance from
// the compact context, or the story's pre-match or lowest chance, hands back
// the exact original and that observation's own key, only while its figure is
// shown. History controls hand back the owner's exact action and choice ids
// and plot positions. Nothing is defaulted to another phase's observation.
//
// Holds. The owner may pass an interaction hook so it can hold before a page
// action lands: on the page — the headline's About and open, the history's
// actions, inspection choices and plot taps, the context's Chart and inspect,
// the story's endpoints, full-card entry and Details, and the original choices —
// and in the catalogue and Details content, the action calls the hook ONCE and
// then the owner's exact callback with its exact value. Full-size content (the
// history and story readers, Info and source) keeps the exact callbacks: its
// host already holds while it is open. Building or reading the view calls
// nothing. Without a callback there is no control and no hook call.
//
// Layout. A compact width or an accessibility size stacks: headline, the
// comparison over the history, then a LazyVStack section whose header is the
// compact context (pinned when the host's scroll contains it) above the story
// and the originals. A regular or unspecified width puts the comparison and
// history beside the story and originals while both keep their minimum widths,
// otherwise it stacks too. The history keeps the owner's plot height in every
// arrangement; full size uses the owner's full-size height, never shorter than
// the page's. The comparison puts the outcomes side by side while every whole
// name and figure fits an equal share of the width it is given, else one
// full-width row per outcome; accessibility sizes go straight to rows, and no
// figure shrinks. The same comparison View, with the same readouts, sits over
// the history inline and full size; while the history's key would show only
// those readouts, a presentation copy of the history hides that key, and the
// owner's history input is never changed. The host owns the scroll, pinning,
// navigation, sheets, Back/Done, focus, reader paging, reader memory,
// selection, inspection, live updates and subscriptions; this view keeps no
// state, runs no timer and presents nothing of its own.
//
// Host binding still owed — not available at this base: an owner that admits,
// for one match snapshot, the phase and the headline (outcome originals, names,
// shapes and tints, before and recorded observations with their keys, the
// reported final); the history with its runs, guide, windows, readout intent
// and held inspection; the context entries and their exact before
// observations; the final story; the Info and source text with links; every
// original with its held selection and recorded context — and maps every
// callback.

// MARK: - Phase, cards, modes

/// The owner's explicit phase for the whole page.
nonisolated enum RugbyMatchEventPagePhase10868: String, Hashable, CaseIterable {
    case before
    case during
    case final
}

/// One card the page can show full size.
nonisolated enum RugbyMatchEventPageCard10868: String, Hashable, CaseIterable {
    /// The win probability history.
    case history
    /// The final chance-to-result story.
    case story
}

/// What the host's container is showing, chosen by the host.
nonisolated enum RugbyMatchEventPageMode10868: Equatable {
    case page
    case reader(RugbyMatchEventPageCard10868)
    /// All original markets with their rules.
    case catalogue
    /// The held original's Details.
    case original
    /// The owner's match Info.
    case about
    /// One owner source document, by its exact id.
    case source(String)
}

nonisolated enum RugbyMatchEventPageArrangement10868: Equatable {
    case stacked
    case sideBySide
}

// MARK: - Input

/// The owner's one-line words above full-size content.
nonisolated struct RugbyMatchEventPageReaderHeader10868: Equatable {
    /// "<team> vs <team> · <phase words>".
    let title: String
    /// Nil draws none.
    let state: String?
}

/// One outcome in the compact context: the history series whose pre-match
/// slot it shows, and the exact original and pre-match observation key handed
/// back when that slot is inspected.
nonisolated struct RugbyMatchEventPageContextEntry10868: Equatable {
    /// Exactly one history series must carry this id.
    let seriesID: String
    /// Nil: the slot is words only.
    let inspect: FieldMovementOpen10868?
}

/// The owner's compact probability context for a phone.
nonisolated struct RugbyMatchEventPageContext10868: Equatable {
    /// Spoken name ("Match probability context").
    let label: String
    /// "<team> vs <team>" with the owner's phase words.
    let result: String
    /// "Before match · separate trades"; nil draws none.
    let caption: String?
    /// "Chart" — opens the full history through the history's own expand id.
    let chartLabel: String
    let chartSpokenLabel: String?
    let entries: [RugbyMatchEventPageContextEntry10868]
    /// An entry whose series does not resolve.
    let unavailableWords: String
    /// Spoken hint on an entry that inspects; nil none.
    let inspectHint: String?
}

/// One external link the owner names, handed back exactly on open.
nonisolated struct RugbyMatchEventPageLink10868: Equatable {
    let id: String
    let label: String
    let url: URL
}

/// One section of the owner's Info or source text, verbatim.
nonisolated struct RugbyMatchEventPageSection10868: Equatable {
    let title: String
    let paragraphs: [String]
    /// An external link; nil draws none.
    var link: RugbyMatchEventPageLink10868? = nil
    /// The exact id of a source document this section opens; nil draws none.
    var sourceID: String? = nil
}

/// The owner's match Info.
nonisolated struct RugbyMatchEventPageAbout10868: Equatable {
    let title: String
    let sections: [RugbyMatchEventPageSection10868]
}

/// One owner source document, by exact id.
nonisolated struct RugbyMatchEventPageSource10868: Equatable {
    let id: String
    let title: String
    let sections: [RugbyMatchEventPageSection10868]
}

nonisolated struct RugbyMatchEventPageCopy10868: Equatable {
    /// Shown where the headline cannot mount for this phase.
    let headlineUnavailable: String
    /// Shown in a full-size card this phase does not show.
    let readerUnavailable: String
    /// Shown in source mode when the id names no single source.
    let sourceUnavailable: String
    /// The control of a section that opens a source ("Original rules & identity").
    let sourceLabel: String
    /// "Original outcomes & rules" — opens all originals; nil draws no entry.
    let catalogueLabel: String?
    /// Spoken name of the readout comparison ("Recorded and pre-match chances").
    let comparisonLabel: String
}

nonisolated struct RugbyMatchEventPageInput10868: Equatable {
    let phase: RugbyMatchEventPagePhase10868
    /// "Constructed example · not a live feed"; nil draws none.
    var notice: String? = nil
    /// The primary outcome readings; mounted while its phase is the page's.
    let headline: FieldHeadlineInput10868
    let reader: RugbyMatchEventPageReaderHeader10868
    /// The owner's history, its runs, readouts and held inspection.
    let history: FieldHistoryInput10868
    /// The owner's full-size plot height; nil or unusable keeps the history's own,
    /// and full size is never shorter than the page's plot.
    var readerPlotHeight: CGFloat? = nil
    /// The compact phone context; nil draws none.
    let context: RugbyMatchEventPageContext10868?
    /// The final story; mounted after the match only.
    let story: HistoricalChanceInput10868?
    let about: RugbyMatchEventPageAbout10868?
    let sources: [RugbyMatchEventPageSource10868]
    let copy: RugbyMatchEventPageCopy10868
}

/// The owner's original markets, for the page's choices and the catalogue and Details modes.
struct RugbyMatchEventPageOriginals10868 {
    let catalogue: OriginalMarketDetails9483.Catalogue?
    let selection: OriginalMarketDetails9483.Selection?
    var recorded: OriginalMarketDetails9483.RecordedHistory? = nil
    /// The owner's display names by exact identity — for example the owner's
    /// name for a venue's own outcome name, which keeps its exact identity and rules.
    var labels: [OriginalMarketDetails9483.Identity: String] = [:]
    /// "All <count> original markets".
    let heading: String
    var context: String? = nil
    let emptyWords: String
    let unavailableChoice: String
    let tint: Color
}

nonisolated enum RugbyMatchEventPageAccessibilityID10868 {
    static let page = "rugbyMatchEventPage10868.page"
    static let headline = "rugbyMatchEventPage10868.headline"
    static let headlineUnavailable = "rugbyMatchEventPage10868.headline.unavailable"
    static let notice = "rugbyMatchEventPage10868.notice"
    static let anchor = "rugbyMatchEventPage10868.anchor"
    static let context = "rugbyMatchEventPage10868.context"
    static let contextChart = "rugbyMatchEventPage10868.context.chart"
    static let story = "rugbyMatchEventPage10868.story"
    static let originals = "rugbyMatchEventPage10868.originals"
    static let catalogueEntry = "rugbyMatchEventPage10868.catalogue.entry"
    static let catalogue = "rugbyMatchEventPage10868.catalogue"
    static let original = "rugbyMatchEventPage10868.original"
    static let about = "rugbyMatchEventPage10868.about"
    static let source = "rugbyMatchEventPage10868.source"
    static let readerHeader = "rugbyMatchEventPage10868.readerHeader"
    static let readerInfo = "rugbyMatchEventPage10868.readerHeader.info"
    static let readerUnavailable = "rugbyMatchEventPage10868.reader.unavailable"
    static let comparison = "rugbyMatchEventPage10868.comparison"
    static func contextEntry(_ seriesID: String) -> String { "rugbyMatchEventPage10868.context.\(seriesID)" }
    static func link(_ id: String) -> String { "rugbyMatchEventPage10868.link.\(id)" }
    static func sourceEntry(_ id: String) -> String { "rugbyMatchEventPage10868.sourceEntry.\(id)" }
}

// MARK: - Model

/// Which leaves the page mounts and what each hands back, resolved once per input.
nonisolated struct RugbyMatchEventPageModel10868: Equatable {
    let input: RugbyMatchEventPageInput10868

    init(_ input: RugbyMatchEventPageInput10868) {
        self.input = input
    }

    static func leafPhase(_ phase: RugbyMatchEventPagePhase10868) -> FieldOutlookPhase10868 {
        switch phase {
        case .before: .before
        case .during: .during
        case .final: .final
        }
    }

    static func readable(_ words: String?) -> String? { FieldMovementModel10868.readable(words) }

    // MARK: Phase gates

    /// The headline at the page's own phase. Otherwise nothing.
    var headline: FieldHeadlineInput10868? {
        input.headline.phase == Self.leafPhase(input.phase) ? input.headline : nil
    }

    /// The story after the match only, at its own final phase.
    var story: HistoricalChanceInput10868? {
        guard input.phase == .final, let story = input.story, story.phase == .final else { return nil }
        return story
    }

    func isMounted(_ card: RugbyMatchEventPageCard10868) -> Bool {
        switch card {
        case .history: true
        case .story: story != nil
        }
    }

    func readerShows(_ card: RugbyMatchEventPageCard10868) -> Bool { isMounted(card) }

    // MARK: History

    /// The approved size of every comparison figure before Dynamic Type scaling.
    static let comparisonFigureSize: CGFloat = 26

    /// The full-size plot height: the owner's full-size height while usable,
    /// never shorter than the page's own plot; else the page's. Presentation
    /// geometry only, never derived from the arrangement.
    static func readerPlotHeight(_ owner: CGFloat?, history: CGFloat) -> CGFloat {
        guard let owner, owner.isFinite, owner > 0 else { return history }
        return max(owner, history)
    }

    /// Whether the comparison stands in for the shared key: only while the key
    /// would show nothing but the readouts the comparison shows — no original's
    /// choose control and no owner key context. Otherwise the owner's key stays.
    var hidesSharedKey: Bool {
        input.history.series.allSatisfy { $0.choose == nil && FieldHistoryGeometry10868.keyContext($0) == nil }
    }

    /// A presentation copy of the owner's history: every series, run, readout,
    /// inspection, key word, action and plot field exactly as supplied, with only
    /// the given height, expand control and key visibility. The owner's input is
    /// never changed.
    static func presentationCopy(_ history: FieldHistoryInput10868, plotHeight: CGFloat,
                                 expand: FieldHistoryAction10868?, showsKey: Bool) -> FieldHistoryInput10868 {
        FieldHistoryInput10868(
            title: history.title, caption: history.caption, series: history.series,
            selection: history.selection, domain: history.domain, ceiling: history.ceiling,
            yTicks: history.yTicks, xTicks: history.xTicks, guides: history.guides, breaks: history.breaks,
            readout: history.readout, markKey: history.markKey,
            comparisonExplanation: history.comparisonExplanation, notes: history.notes,
            summary: history.summary, plotHeight: plotHeight,
            unboundReadingWords: history.unboundReadingWords, plotUnavailableWords: history.plotUnavailableWords,
            windows: history.windows, scale: history.scale, moreOriginals: history.moreOriginals,
            details: history.details, expand: expand, inspect: history.inspect,
            previous: history.previous, next: history.next, inspection: history.inspection,
            layout: history.layout,
            probabilityLowerBound: history.probabilityLowerBound,
            probabilityRangeExplanation: history.probabilityRangeExplanation,
            selectedReadout: history.selectedReadout, inspectionRingShape: history.inspectionRingShape,
            plotAbsence: history.plotAbsence, showsKey: showsKey
        )
    }

    /// The key's visibility in both presentation copies.
    private var presentedKey: Bool { hidesSharedKey ? false : input.history.showsKey }

    /// The history on the page: the owner's input with the duplicate key hidden.
    var presentedHistory: FieldHistoryInput10868 {
        let history = input.history
        return Self.presentationCopy(history, plotHeight: history.plotHeight, expand: history.expand, showsKey: presentedKey)
    }

    /// The history full size: the same input — its series, runs, readouts,
    /// windows, selection and inspection unchanged — at the owner's full-size
    /// height (never shorter than the page's), without its own expand control
    /// inside the reader, and with the same key visibility as the page.
    var readerHistory: FieldHistoryInput10868 {
        let history = input.history
        return Self.presentationCopy(
            history, plotHeight: Self.readerPlotHeight(input.readerPlotHeight, history: history.plotHeight),
            expand: nil, showsKey: presentedKey)
    }

    // MARK: Compact context

    /// The one history series an entry names; none for a blank, missing or shared id.
    func contextSeries(_ entry: RugbyMatchEventPageContextEntry10868) -> FieldHistorySeries10868? {
        guard Self.readable(entry.seriesID) != nil else { return nil }
        let matches = input.history.series.filter { $0.id == entry.seriesID }
        return matches.count == 1 ? matches[0] : nil
    }

    /// The entry's pre-match slot exactly as the history resolves it: the first
    /// readout slot of its series under the owner's readout intent.
    func contextSlot(_ entry: RugbyMatchEventPageContextEntry10868) -> FieldHistoryReadoutSlot10868? {
        contextSeries(entry).flatMap { FieldHistoryGeometry10868.readoutSlots($0, in: input.history).first }
    }

    /// The exact original and pre-match observation key to inspect: only with a
    /// callback, while the slot's figure is shown and the owner's hand-off names
    /// a complete original and a readable key. Otherwise no control.
    func contextInspect(_ entry: RugbyMatchEventPageContextEntry10868, canInspect: Bool) -> FieldMovementOpen10868? {
        guard canInspect, let slot = contextSlot(entry), case .figure = slot.display,
              let inspect = entry.inspect, inspect.ref.isComplete, Self.readable(inspect.observation) != nil
        else { return nil }
        return inspect
    }

    /// One entry in words: the series name and its slot, or the owner's words.
    func contextEntrySummary(_ entry: RugbyMatchEventPageContextEntry10868) -> String {
        guard let series = contextSeries(entry), let slot = contextSlot(entry) else {
            return input.context?.unavailableWords ?? ""
        }
        return [series.name, FieldHistoryGeometry10868.spokenSlot(slot)].joined(separator: ". ")
    }

    /// The history's own expand id for the context's Chart: live, available,
    /// with a callback and while the plot is shown. Otherwise no control.
    func contextChartID(canOpen: Bool) -> String? {
        guard let expand = input.history.expand, expand.isAvailable,
              case .live(let id) = FieldHistoryGeometry10868.chartControlState(
                  expand, informative: false, hasCallback: canOpen, in: input.history)
        else { return nil }
        return id
    }

    /// The context belongs to the stacked page; wide keeps the history in view.
    static func showsContext(_ arrangement: RugbyMatchEventPageArrangement10868) -> Bool {
        arrangement == .stacked
    }

    // MARK: Info and sources

    static func hasWords(_ section: RugbyMatchEventPageSection10868) -> Bool {
        readable(section.title) != nil || section.paragraphs.contains { readable($0) != nil }
    }

    var about: RugbyMatchEventPageAbout10868? {
        guard let about = input.about,
              Self.readable(about.title) != nil || about.sections.contains(where: Self.hasWords)
        else { return nil }
        return about
    }

    func aboutAvailable(canOpen: Bool) -> Bool { canOpen && about != nil }

    /// The reader heading's Info entry: full-size history and story readers only.
    func aboutEntry(mode: RugbyMatchEventPageMode10868, canOpen: Bool) -> Bool {
        guard case .reader = mode else { return false }
        return aboutAvailable(canOpen: canOpen)
    }

    /// The source document an id names: exactly one, with a nonblank id.
    func source(_ id: String) -> RugbyMatchEventPageSource10868? {
        guard Self.readable(id) != nil else { return nil }
        let matches = input.sources.filter { $0.id == id }
        return matches.count == 1 ? matches[0] : nil
    }

    /// Every source id that resolves to exactly one document.
    var sourceIDs: Set<String> {
        Set(input.sources.map(\.id).filter { source($0) != nil })
    }

    func catalogueAvailable(canOpen: Bool, hasOriginals: Bool) -> Bool {
        canOpen && hasOriginals && Self.readable(input.copy.catalogueLabel) != nil
    }

    // MARK: Layout

    /// Accessibility sizes and a compact width stack; a regular or unspecified
    /// width tries the history beside the secondary column, then stacks.
    static func arrangements(sizeClass: UserInterfaceSizeClass?, accessibilitySize: Bool) -> [RugbyMatchEventPageArrangement10868] {
        sizeClass != .compact && !accessibilitySize ? [.sideBySide, .stacked] : [.stacked]
    }
}

// MARK: - Small owner-labelled leaves

/// One outcome in the comparison: its series and the readouts the history
/// resolves for it, with the history's own note.
nonisolated struct RugbyMatchEventPageComparisonEntry10868: Equatable {
    let series: FieldHistorySeries10868
    let note: String?
    let slots: [FieldHistoryReadoutSlot10868]
    /// The history's own exact selection, marked as the key marks it.
    let isSelected: Bool
}

/// Every outcome's dated readouts exactly as the history resolves them
/// (`FieldHistoryGeometry10868.readoutSlots`, `keyNote`, `spokenSlot`): each
/// figure at one scaled figure size and weight under its own label with its own
/// date, beside the outcome's whole name and its history shape. An exact-minute
/// absence keeps the history's words in a smaller style, never a figure; equal
/// values at different times stay separate slots. Outcomes sit side by side
/// while every whole name and figure fits an equal share of the given width,
/// else one full-width row each; accessibility sizes go straight to rows, and a
/// row's slots stack where they do not fit whole. The history's exact selection
/// is marked as its key marks it. No action, state or formatting.
struct RugbyMatchEventPageComparisonPresentation10868: View {
    /// The history copy the page shows beside it: the same readouts inline and full size.
    let history: FieldHistoryInput10868
    /// Spoken name of the comparison.
    let label: String

    static let columnSpacing: CGFloat = 12
    static let rowSpacing: CGFloat = 14
    static let entryPadding: CGFloat = 8

    @Environment(\.dynamicTypeSize) private var typeSize
    @ScaledMetric(relativeTo: .title) private var figureSize: CGFloat = RugbyMatchEventPageModel10868.comparisonFigureSize
    @ScaledMetric(relativeTo: .caption) private var markRadius: CGFloat = 3.5

    /// Every series in the owner's order, with its resolved readouts.
    var entries: [RugbyMatchEventPageComparisonEntry10868] {
        history.series.map {
            RugbyMatchEventPageComparisonEntry10868(
                series: $0,
                note: FieldHistoryGeometry10868.keyNote($0, in: history),
                slots: FieldHistoryGeometry10868.readoutSlots($0, in: history),
                isSelected: FieldHistoryGeometry10868.isSelected($0, in: history))
        }
    }

    /// Every figure the entries draw, measured whole (with the entry's padding)
    /// by hidden copies so the layout picks columns only when each fits an
    /// equal share.
    static func figures(_ entries: [RugbyMatchEventPageComparisonEntry10868]) -> [String] {
        entries.flatMap(\.slots).compactMap {
            guard case .figure(let figure, _) = $0.display else { return nil }
            return figure
        }
    }

    /// One outcome in words: its whole name, its note, then each slot with its own date.
    static func spoken(_ entry: RugbyMatchEventPageComparisonEntry10868) -> String {
        ([entry.series.name] + [entry.note].compactMap(RugbyMatchEventPageModel10868.readable)
            + entry.slots.map(FieldHistoryGeometry10868.spokenSlot))
            .joined(separator: ". ")
    }

    /// A row's slots side by side where they fit whole, else stacked; stacked
    /// straight away at accessibility sizes.
    static func slotArrangements(accessibilitySize: Bool) -> [FieldChooserArrangement10868] {
        FieldChaseGeometry10868.stacksReadouts(accessibilitySize: accessibilitySize) ? [.stacked] : [.sideBySide, .stacked]
    }

    var body: some View {
        let entries = self.entries
        if !entries.isEmpty {
            FieldHeadlineCompetitorsLayout10868(count: entries.count, spacing: Self.columnSpacing, rowSpacing: Self.rowSpacing,
                                                accessibilitySize: typeSize.isAccessibilitySize) {
                ForEach(Array(entries.enumerated()), id: \.offset) { _, entry in
                    entryView(entry)
                }
                ForEach(Array(entries.enumerated()), id: \.offset) { _, entry in
                    nameRow(entry.series, whole: true).padding(Self.entryPadding).hidden().accessibilityHidden(true)
                }
                ForEach(Array(Self.figures(entries).enumerated()), id: \.offset) { _, figure in
                    figureText(figure).padding(Self.entryPadding).hidden().accessibilityHidden(true)
                }
            }
            .accessibilityElement(children: .contain)
            .accessibilityLabel(label)
            .accessibilityIdentifier(RugbyMatchEventPageAccessibilityID10868.comparison)
        }
    }

    private func entryView(_ entry: RugbyMatchEventPageComparisonEntry10868) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            nameRow(entry.series, whole: false)
            if let note = RugbyMatchEventPageModel10868.readable(entry.note) {
                Text(note)
                    .font(.footnote)
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            if Self.slotArrangements(accessibilitySize: typeSize.isAccessibilitySize).contains(.sideBySide) {
                ViewThatFits(in: .horizontal) {
                    HStack(alignment: .top, spacing: 14) { slots(entry) }
                    VStack(alignment: .leading, spacing: 10) { slots(entry) }
                }
            } else {
                VStack(alignment: .leading, spacing: 10) { slots(entry) }
            }
        }
        .padding(Self.entryPadding)
        .frame(maxWidth: .infinity, alignment: .topLeading)
        .background(RoundedRectangle(cornerRadius: 10).fill(entry.isSelected ? DS.surface : Color.clear))
        .overlay(RoundedRectangle(cornerRadius: 10).stroke(entry.isSelected ? DS.textSecondary : Color.clear, lineWidth: 1))
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(Self.spoken(entry))
        .accessibilityAddTraits(entry.isSelected ? .isSelected : [])
    }

    @ViewBuilder private func slots(_ entry: RugbyMatchEventPageComparisonEntry10868) -> some View {
        ForEach(Array(entry.slots.enumerated()), id: \.offset) { _, slot in
            VStack(alignment: .leading, spacing: 2) {
                Text(slot.label)
                    .font(.caption)
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
                switch slot.display {
                case .figure(let figure, let provenance):
                    figureText(figure)
                    Text(provenance)
                        .font(.caption)
                        .foregroundStyle(DS.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                case .words(let words):
                    Text(words)
                        .font(.callout.weight(.medium))
                        .foregroundStyle(DS.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
        }
    }

    /// The identity glyph and the whole name; `whole` measures it on one line.
    private func nameRow(_ series: FieldHistorySeries10868, whole: Bool) -> some View {
        HStack(alignment: .center, spacing: 6) {
            glyph(series)
            Text(series.name)
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(DS.textPrimary)
                .fixedSize(horizontal: whole, vertical: true)
        }
    }

    /// Every figure at the one scaled size and weight; never shrunk.
    private func figureText(_ figure: String) -> some View {
        Text(figure)
            .font(.system(size: figureSize, weight: .semibold))
            .monospacedDigit()
            .foregroundStyle(DS.textPrimary)
            .fixedSize()
    }

    /// The history's own identity: a short solid line through the outcome's mark shape.
    private func glyph(_ series: FieldHistorySeries10868) -> some View {
        let radius = markRadius
        let tint = series.tint
        let shape = series.shape
        return Canvas { context, size in
            let middle = CGPoint(x: size.width / 2, y: size.height / 2)
            var line = Path()
            line.move(to: CGPoint(x: 0, y: middle.y))
            line.addLine(to: CGPoint(x: size.width, y: middle.y))
            context.stroke(line, with: .color(tint), lineWidth: 2)
            context.fill(FieldHistoryGeometry10868.markPath(shape, at: middle, radius: radius * 1.3), with: .color(tint))
        }
        .frame(width: radius * 7, height: radius * 4.5)
        .accessibilityHidden(true)
    }
}

/// Each outcome's pre-match slot exactly as the history resolves it, each
/// inspecting its own exact observation, and Chart to the full history. The
/// host mounts or pins it; it keeps no selection of its own.
struct RugbyMatchEventPageContextPresentation10868: View {
    let model: RugbyMatchEventPageModel10868
    let context: RugbyMatchEventPageContext10868
    /// The history's own expand action, after the page hook. Nil: no Chart control.
    var onChart: (() -> Void)?
    /// An entry's exact original and observation, after the page hook. Nil: no entry acts.
    var onInspect: ((FieldMovementOpen10868) -> Void)?

    @Environment(\.dynamicTypeSize) private var typeSize
    @ScaledMetric(relativeTo: .body) private var controlSize: CGFloat = 44

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(alignment: .center, spacing: 8) {
                Text(context.result)
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(DS.textPrimary)
                    .fixedSize(horizontal: false, vertical: true)
                    .frame(maxWidth: .infinity, alignment: .leading)
                if let onChart {
                    Button(action: onChart) {
                        HStack(spacing: 4) {
                            Text(context.chartLabel).font(.subheadline.weight(.semibold))
                            Image(systemName: "arrow.up.right").font(.caption.weight(.semibold)).accessibilityHidden(true)
                        }
                        .foregroundStyle(DS.blue)
                        .frame(minWidth: controlSize, minHeight: controlSize)
                        .contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                    .accessibilityLabel(context.chartSpokenLabel ?? context.chartLabel)
                    .accessibilityIdentifier(RugbyMatchEventPageAccessibilityID10868.contextChart)
                }
            }
            if let caption = RugbyMatchEventPageModel10868.readable(context.caption) {
                Text(caption)
                    .font(.caption)
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            LazyVGrid(columns: Array(repeating: GridItem(.flexible(), spacing: 10, alignment: .topLeading),
                                     count: typeSize.isAccessibilitySize ? 1 : max(1, context.entries.count)),
                      alignment: .leading, spacing: 8) {
                ForEach(Array(context.entries.enumerated()), id: \.offset) { _, entry in
                    entryView(entry)
                }
            }
        }
        .padding(.vertical, 8)
        .frame(maxWidth: .infinity, alignment: .leading)
        .accessibilityElement(children: .contain)
        .accessibilityLabel(context.label)
        .accessibilityIdentifier(RugbyMatchEventPageAccessibilityID10868.context)
    }

    @ViewBuilder private func entryView(_ entry: RugbyMatchEventPageContextEntry10868) -> some View {
        let inspect = model.contextInspect(entry, canInspect: onInspect != nil)
        let content = entryContent(entry)
            .frame(maxWidth: .infinity, minHeight: controlSize, alignment: .topLeading)
            .contentShape(Rectangle())
        if let inspect, let onInspect {
            Button {
                onInspect(inspect)
            } label: {
                content
            }
            .buttonStyle(.plain)
            .accessibilityLabel(model.contextEntrySummary(entry))
            .accessibilityHint(context.inspectHint ?? "")
            .accessibilityIdentifier(RugbyMatchEventPageAccessibilityID10868.contextEntry(entry.seriesID))
        } else {
            content
                .accessibilityElement(children: .ignore)
                .accessibilityLabel(model.contextEntrySummary(entry))
                .accessibilityIdentifier(RugbyMatchEventPageAccessibilityID10868.contextEntry(entry.seriesID))
        }
    }

    @ViewBuilder private func entryContent(_ entry: RugbyMatchEventPageContextEntry10868) -> some View {
        if let series = model.contextSeries(entry), let slot = model.contextSlot(entry) {
            VStack(alignment: .leading, spacing: 2) {
                Text(series.name)
                    .font(.footnote.weight(.semibold))
                    .foregroundStyle(series.tint)
                    .fixedSize(horizontal: false, vertical: true)
                Text(slot.label)
                    .font(.caption2)
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
                switch slot.display {
                case .figure(let figure, let provenance):
                    Text(figure)
                        .font(.headline.monospacedDigit())
                        .foregroundStyle(DS.textPrimary)
                        .fixedSize(horizontal: false, vertical: true)
                    Text(provenance)
                        .font(.caption2)
                        .foregroundStyle(DS.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                case .words(let words):
                    Text(words)
                        .font(.footnote.weight(.medium))
                        .foregroundStyle(DS.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
        } else {
            Text(context.unavailableWords)
                .font(.footnote)
                .foregroundStyle(DS.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
        }
    }
}

/// The owner's Info or source text in its own words. A section's link hands the
/// owner its exact link; a section's source control hands back its exact id,
/// only when that id names exactly one source. With no callback, words only.
struct RugbyMatchEventPageSectionsContent10868: View {
    let title: String
    let sections: [RugbyMatchEventPageSection10868]
    /// Ids that resolve to exactly one source document.
    let sourceIDs: Set<String>
    let sourceLabel: String
    var onLink: ((RugbyMatchEventPageLink10868) -> Void)? = nil
    var onSource: ((String) -> Void)? = nil

    @ScaledMetric(relativeTo: .body) private var controlSize: CGFloat = 44

    /// The section's exact link for the host to open, or nothing.
    func linkAction(_ link: RugbyMatchEventPageLink10868?) -> (() -> Void)? {
        guard let link, RugbyMatchEventPageModel10868.readable(link.label) != nil, let onLink else { return nil }
        return { onLink(link) }
    }

    /// The section's exact source id, only when it resolves and with a callback.
    func sourceAction(_ id: String?) -> (() -> Void)? {
        guard let id, sourceIDs.contains(id), RugbyMatchEventPageModel10868.readable(sourceLabel) != nil,
              let onSource else { return nil }
        return { onSource(id) }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            if let title = RugbyMatchEventPageModel10868.readable(title) {
                Text(title)
                    .font(.headline)
                    .foregroundStyle(DS.textPrimary)
                    .accessibilityAddTraits(.isHeader)
            }
            ForEach(Array(sections.enumerated()), id: \.offset) { _, section in
                if RugbyMatchEventPageModel10868.hasWords(section) {
                    VStack(alignment: .leading, spacing: 6) {
                        if let title = RugbyMatchEventPageModel10868.readable(section.title) {
                            Text(title)
                                .font(.body.weight(.semibold))
                                .foregroundStyle(DS.textPrimary)
                                .accessibilityAddTraits(.isHeader)
                        }
                        ForEach(Array(section.paragraphs.enumerated()), id: \.offset) { _, paragraph in
                            if let words = RugbyMatchEventPageModel10868.readable(paragraph) {
                                Text(words).font(.body).foregroundStyle(DS.textPrimary)
                            }
                        }
                        if let action = sourceAction(section.sourceID), let id = section.sourceID {
                            control(sourceLabel, symbol: "doc.text", action: action)
                                .accessibilityIdentifier(RugbyMatchEventPageAccessibilityID10868.sourceEntry(id))
                        }
                        if let link = section.link, let action = linkAction(link) {
                            control(link.label, symbol: "arrow.up.right", action: action)
                                .accessibilityAddTraits(.isLink)
                                .accessibilityIdentifier(RugbyMatchEventPageAccessibilityID10868.link(link.id))
                        } else if let link = section.link, let label = RugbyMatchEventPageModel10868.readable(link.label) {
                            Text(label)
                                .font(.subheadline)
                                .foregroundStyle(DS.textSecondary)
                                .accessibilityIdentifier(RugbyMatchEventPageAccessibilityID10868.link(link.id))
                        }
                    }
                }
            }
        }
        .fixedSize(horizontal: false, vertical: true)
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private func control(_ label: String, symbol: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            HStack(spacing: 6) {
                Text(label).font(.body.weight(.semibold)).fixedSize(horizontal: false, vertical: true)
                Image(systemName: symbol).font(.body.weight(.semibold)).accessibilityHidden(true)
            }
            .foregroundStyle(DS.blue)
            .frame(minHeight: controlSize)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
    }
}

// MARK: - Page view

struct RugbyMatchEventPagePresentation10868: View {
    let input: RugbyMatchEventPageInput10868
    var mode: RugbyMatchEventPageMode10868 = .page
    /// The page's original choices and the catalogue and Details modes; nil: none.
    var originals: RugbyMatchEventPageOriginals10868? = nil
    /// Opens the host's container on the owner's Info.
    var onAbout: (() -> Void)? = nil
    /// A source document's exact id, for the host to open.
    var onSource: ((String) -> Void)? = nil
    /// A section's exact external link, for the host to open.
    var onLink: ((RugbyMatchEventPageLink10868) -> Void)? = nil
    /// Opens all original markets.
    var onCatalogue: (() -> Void)? = nil
    /// An original choice's exact selection.
    var onOriginalSelect: ((OriginalMarketDetails9483.Selection) -> Void)? = nil
    /// A Details history control's exact intent.
    var onOriginalHistory: ((OriginalMarketDetails9483.HistoryIntent) -> Void)? = nil
    /// The headline's exact original, with its recorded observation key during the match only.
    var onOriginalOpen: ((FieldMovementOpen10868) -> Void)? = nil
    /// An exact original and observation key to show in the history: the
    /// context's pre-match slots and the story's pre-match and lowest chances.
    var onInspect: ((FieldMovementOpen10868) -> Void)? = nil
    /// The history's exact action ids — its expand, windows, Details and
    /// previous/next included; the context's Chart hands back the expand id too.
    var onHistoryAction: ((String) -> Void)? = nil
    var onHistoryInspectionChoice: ((String) -> Void)? = nil
    var onHistoryPlotPosition: ((Double) -> Void)? = nil
    /// Opens a card full size.
    var onReaderOpen: ((RugbyMatchEventPageCard10868) -> Void)? = nil
    /// The story's "how to read" Details.
    var onStoryDetails: (() -> Void)? = nil
    /// Called once just before a page, catalogue or Details action reaches its
    /// owner callback. Never by building the view or by full-size content.
    var onInteraction: (() -> Void)? = nil

    @Environment(\.horizontalSizeClass) private var sizeClass
    @Environment(\.dynamicTypeSize) private var typeSize
    @ScaledMetric(relativeTo: .body) private var anchorMinWidth: CGFloat = 440
    @ScaledMetric(relativeTo: .body) private var secondaryMinWidth: CGFloat = 320
    @ScaledMetric(relativeTo: .body) private var controlSize: CGFloat = 44

    var model: RugbyMatchEventPageModel10868 { RugbyMatchEventPageModel10868(input) }

    private var isFullSize: Bool {
        switch mode {
        case .page, .catalogue, .original: false
        case .reader, .about, .source: true
        }
    }

    /// The page's hook; none in already-held full-size content.
    private var pageHook: (() -> Void)? { isFullSize ? nil : onInteraction }

    /// A page, catalogue or Details action, after the owner's interaction
    /// hook. No host callback: no action and no hook call.
    static func held<Value>(_ action: ((Value) -> Void)?, by interaction: (() -> Void)?) -> ((Value) -> Void)? {
        guard let action else { return nil }
        guard let interaction else { return action }
        return { value in
            interaction()
            action(value)
        }
    }

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
            case .source(let id): sourceMode(id)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    // MARK: Leaves — the actual Views, each with the host's own callbacks

    /// The host's Info opener; nil without readable Info text or a callback.
    func aboutOpener() -> (() -> Void)? {
        guard model.aboutAvailable(canOpen: onAbout != nil), let onAbout else { return nil }
        return onAbout
    }

    /// The headline at the page's phase: its About and open after the page hook.
    func headlineContent() -> FieldPhaseHeadlinePresentation10868? {
        model.headline.map {
            FieldPhaseHeadlinePresentation10868(
                input: $0,
                onAbout: Self.heldAction(aboutOpener(), by: pageHook),
                onOpen: Self.held(onOriginalOpen, by: pageHook))
        }
    }

    /// The readout comparison: the same View with the same readouts inline and
    /// full size, read from the history copy shown beside it.
    func comparisonContent(reader: Bool) -> RugbyMatchEventPageComparisonPresentation10868 {
        RugbyMatchEventPageComparisonPresentation10868(
            history: reader ? model.readerHistory : model.presentedHistory, label: input.copy.comparisonLabel)
    }

    /// The history: the page hook first; full size keeps the exact callbacks.
    func historyContent(reader: Bool) -> FieldProbabilityHistoryPresentation10868 {
        let interaction = reader ? nil : pageHook
        return FieldProbabilityHistoryPresentation10868(
            input: reader ? model.readerHistory : model.presentedHistory,
            onAction: Self.held(onHistoryAction, by: interaction),
            onInspectionChoice: Self.held(onHistoryInspectionChoice, by: interaction),
            onPlotPosition: Self.held(onHistoryPlotPosition, by: interaction)
        )
    }

    /// The compact context. Its Chart hands back the history's own expand id
    /// and its entries their exact observations, each after the page hook.
    func contextContent() -> RugbyMatchEventPageContextPresentation10868? {
        guard let context = input.context else { return nil }
        var chart: (() -> Void)?
        if let id = model.contextChartID(canOpen: onHistoryAction != nil), let action = onHistoryAction {
            chart = { action(id) }
        }
        return RugbyMatchEventPageContextPresentation10868(
            model: model, context: context,
            onChart: Self.heldAction(chart, by: pageHook),
            onInspect: Self.held(onInspect, by: pageHook))
    }

    /// The final story. On the page each action passes the page hook first and
    /// the full-card entry opens the story reader; full size keeps the exact
    /// callbacks and has no full-card entry.
    func storyContent(reader: Bool) -> HistoricalChanceResultPresentation10868? {
        guard let story = model.story else { return nil }
        if reader {
            return HistoricalChanceResultPresentation10868(input: story, onOpen: onInspect, onExpand: nil, onDetails: onStoryDetails)
        }
        var expand: (() -> Void)?
        if let open = onReaderOpen { expand = { open(.story) } }
        return HistoricalChanceResultPresentation10868(
            input: story,
            onOpen: Self.held(onInspect, by: pageHook),
            onExpand: Self.heldAction(expand, by: pageHook),
            onDetails: Self.heldAction(onStoryDetails, by: pageHook))
    }

    /// Every original by its exact identity on the page, its choice after the hook.
    func choicesContent() -> OriginalMarketChooserView9483? {
        originals.map {
            OriginalMarketChooserView9483(
                catalogue: $0.catalogue, selection: $0.selection, heading: $0.heading,
                emptyWords: $0.emptyWords, unavailableChoice: $0.unavailableChoice, labels: $0.labels,
                tint: $0.tint, onSelect: Self.held(onOriginalSelect, by: pageHook))
        }
    }

    /// The all-originals entry, after the page hook.
    var catalogueAction: (() -> Void)? {
        guard model.catalogueAvailable(canOpen: onCatalogue != nil, hasOriginals: originals != nil) else { return nil }
        return Self.heldAction(onCatalogue, by: pageHook)
    }

    /// The existing catalogue with every original and its rules, its select after the hook.
    func catalogueContent() -> OriginalMarketCatalogueView9483? {
        originals.map {
            OriginalMarketCatalogueView9483(
                catalogue: $0.catalogue, selection: $0.selection, heading: $0.heading, context: $0.context,
                emptyWords: $0.emptyWords, unavailableChoice: $0.unavailableChoice, labels: $0.labels,
                tint: $0.tint, onSelect: Self.held(onOriginalSelect, by: onInteraction)
            )
        }
    }

    /// The existing Details for the held selection, its history after the hook.
    func originalDetailsContent() -> OriginalMarketDetailsView9483? {
        originals.map {
            OriginalMarketDetailsView9483(
                catalogue: $0.catalogue, selection: $0.selection, tint: $0.tint,
                recorded: $0.recorded, onHistory: Self.held(onOriginalHistory, by: onInteraction)
            )
        }
    }

    /// The owner's Info with its exact link and source callbacks — already held content.
    func aboutContent() -> RugbyMatchEventPageSectionsContent10868? {
        model.about.map {
            RugbyMatchEventPageSectionsContent10868(title: $0.title, sections: $0.sections, sourceIDs: model.sourceIDs,
                                                    sourceLabel: input.copy.sourceLabel, onLink: onLink, onSource: onSource)
        }
    }

    /// One source document by exact id — already held content. Nil when the id
    /// names no single source.
    func sourceContent(_ id: String) -> RugbyMatchEventPageSectionsContent10868? {
        model.source(id).map {
            RugbyMatchEventPageSectionsContent10868(title: $0.title, sections: $0.sections, sourceIDs: model.sourceIDs,
                                                    sourceLabel: input.copy.sourceLabel, onLink: onLink, onSource: onSource)
        }
    }

    /// Full-size content's Info: the exact callback, no hook.
    func openReaderAbout() {
        aboutOpener()?()
    }

    // MARK: Page

    private var page: some View {
        Group {
            let arrangements = RugbyMatchEventPageModel10868.arrangements(
                sizeClass: sizeClass, accessibilitySize: typeSize.isAccessibilitySize)
            if arrangements == [.stacked] {
                stackedPage
            } else {
                ViewThatFits(in: .horizontal) {
                    widePage
                    stackedPage
                }
            }
        }
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(RugbyMatchEventPageAccessibilityID10868.page)
    }

    /// Headline, history, then the story and originals under the compact
    /// context — a section header the host's scroll pins.
    private var stackedPage: some View {
        LazyVStack(alignment: .leading, spacing: 16, pinnedViews: [.sectionHeaders]) {
            header
            anchor
            Section {
                secondary
            } header: {
                if let context = contextContent() {
                    context.background(DS.surface)
                }
            }
        }
    }

    /// The headline across; the history beside the story and originals.
    private var widePage: some View {
        VStack(alignment: .leading, spacing: 16) {
            header
            HStack(alignment: .top, spacing: 24) {
                anchor
                    .frame(minWidth: anchorMinWidth, maxWidth: .infinity, alignment: .topLeading)
                    .layoutPriority(1)
                secondary
                    .frame(minWidth: secondaryMinWidth, maxWidth: .infinity, alignment: .topLeading)
            }
        }
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: 10) {
            if let headline = headlineContent() {
                headline
            } else {
                Text(input.copy.headlineUnavailable)
                    .font(.subheadline)
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
                    .accessibilityIdentifier(RugbyMatchEventPageAccessibilityID10868.headlineUnavailable)
            }
            if let notice = RugbyMatchEventPageModel10868.readable(input.notice) {
                Text(notice)
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
                    .accessibilityIdentifier(RugbyMatchEventPageAccessibilityID10868.notice)
            }
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .modifier(RugbyMatchEventPageCardSurface10868())
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(RugbyMatchEventPageAccessibilityID10868.headline)
    }

    private var anchor: some View {
        VStack(alignment: .leading, spacing: 14) {
            comparisonContent(reader: false)
            historyContent(reader: false)
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .modifier(RugbyMatchEventPageCardSurface10868())
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(RugbyMatchEventPageAccessibilityID10868.anchor)
    }

    /// The story after the match, then every original and the catalogue entry.
    private var secondary: some View {
        VStack(alignment: .leading, spacing: 16) {
            if let story = storyContent(reader: false) {
                story
                    .padding(16)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .modifier(RugbyMatchEventPageCardSurface10868())
                    .accessibilityIdentifier(RugbyMatchEventPageAccessibilityID10868.story)
            }
            if let choices = choicesContent() {
                choices
                    .padding(16)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .modifier(RugbyMatchEventPageCardSurface10868())
                    .accessibilityIdentifier(RugbyMatchEventPageAccessibilityID10868.originals)
            }
            catalogueEntry
        }
    }

    @ViewBuilder private var catalogueEntry: some View {
        if let action = catalogueAction, let label = input.copy.catalogueLabel {
            Button(action: action) {
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
                .modifier(RugbyMatchEventPageCardSurface10868())
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .accessibilityIdentifier(RugbyMatchEventPageAccessibilityID10868.catalogueEntry)
        }
    }

    // MARK: Full size

    /// The same leaf and input, full size, under the compact words. A card this
    /// phase does not show keeps the owner's unavailable words — never another card.
    @ViewBuilder private func reader(_ card: RugbyMatchEventPageCard10868) -> some View {
        VStack(alignment: .leading, spacing: 16) {
            compactHeader
            if model.readerShows(card) {
                switch card {
                case .history:
                    comparisonContent(reader: true)
                    historyContent(reader: true)
                case .story: storyContent(reader: true)
                }
            } else {
                Text(input.copy.readerUnavailable)
                    .font(.subheadline)
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
                    .accessibilityIdentifier(RugbyMatchEventPageAccessibilityID10868.readerUnavailable)
            }
        }
    }

    /// The owner's one-line words and, in full-size readers, the Info entry.
    private var compactHeader: some View {
        HStack(alignment: .top, spacing: 12) {
            VStack(alignment: .leading, spacing: 4) {
                Text(input.reader.title)
                    .font(.headline)
                    .foregroundStyle(DS.textPrimary)
                    .accessibilityAddTraits(.isHeader)
                if let state = RugbyMatchEventPageModel10868.readable(input.reader.state) {
                    Text(state)
                        .font(.subheadline)
                        .foregroundStyle(DS.textPrimary)
                }
            }
            .fixedSize(horizontal: false, vertical: true)
            .frame(maxWidth: .infinity, alignment: .leading)
            if model.aboutEntry(mode: mode, canOpen: onAbout != nil), let label = model.headline?.copy.aboutLabel {
                Button(action: openReaderAbout) {
                    Image(systemName: "info.circle")
                        .font(.title3)
                        .foregroundStyle(DS.textPrimary)
                        .frame(minWidth: controlSize, minHeight: controlSize)
                        .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .accessibilityLabel(label)
                .accessibilityIdentifier(RugbyMatchEventPageAccessibilityID10868.readerInfo)
            }
        }
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(RugbyMatchEventPageAccessibilityID10868.readerHeader)
    }

    @ViewBuilder private var catalogueMode: some View {
        if let catalogue = catalogueContent() {
            catalogue
                .accessibilityElement(children: .contain)
                .accessibilityIdentifier(RugbyMatchEventPageAccessibilityID10868.catalogue)
        }
    }

    @ViewBuilder private var originalMode: some View {
        if let details = originalDetailsContent() {
            details
                .accessibilityElement(children: .contain)
                .accessibilityIdentifier(RugbyMatchEventPageAccessibilityID10868.original)
        }
    }

    @ViewBuilder private var aboutMode: some View {
        if let content = aboutContent() {
            VStack(alignment: .leading, spacing: 12) {
                compactHeader
                content
            }
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier(RugbyMatchEventPageAccessibilityID10868.about)
        }
    }

    @ViewBuilder private func sourceMode(_ id: String) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            compactHeader
            if let content = sourceContent(id) {
                content
            } else {
                Text(input.copy.sourceUnavailable)
                    .font(.subheadline)
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(RugbyMatchEventPageAccessibilityID10868.source)
    }
}

/// The reference's white card on the page surface.
private struct RugbyMatchEventPageCardSurface10868: ViewModifier {
    func body(content: Content) -> some View {
        content
            .background(DS.cardBg, in: RoundedRectangle(cornerRadius: 18, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 18, style: .continuous).stroke(DS.border, lineWidth: 1))
    }
}
