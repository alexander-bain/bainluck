import SwiftUI

// #10868 — the daily-high page for the EXISTING weather-range route: one
// native presentation composed from the accepted shared leaves.
//
// PILLARS: FORMATTING / TRUTH / DISCOVER. SHIP: the native daily-high page keeps
// the selected range's before/recorded chance and history prominent, with both
// approved probability cards, independent original readers and truthful
// station/result context.
//
// A reader sees, in this order: the owner's daily-high heading (title, place,
// date and day-state words, the selected range's meaning, a compact Info entry)
// with — during and after the day only — the owner's captured station
// measurement and — after the day only — the owner's resolved-range words, each
// under its own label and apart from every chance; the probability-history
// anchor (the owner's focused composition: the selected range's own name,
// shape and readouts lead, then the plot of the owner's cohort with its
// day-boundary guide, the key below); on a phone, a compact probability
// context the host may pin (the same focused readout slots and "Chart" to the
// full history); the owner's story stream of the two approved cards — the
// before-day range outlook (every phase) and the noon shift (during and after
// the day only); then the entry to all original outcomes.
//
// Presentation only, from the approved `WeatherRanges.tsx`,
// `WeatherChanceReading.tsx`, `weatherReadingComparison.ts` and
// `weatherRanges.css`, the dated-comparison native reference
// (`weather-dated-comparison-20261025`) and the native v428 obligations. Their
// fixture loader, provider/event/token allowlist, baseline and last-point
// election, exact-minute lookup, 90-minute segmentation, cohort/rank/top-five
// election, event-zone cutoffs, station maximum, scalar parsing, temperature
// conversion, probability/date/change formatting and settlement rules are NOT
// ported. The leaves are the actual accepted Views:
//
//   • `FieldProbabilityHistoryPresentation10868` — the anchor, with its own
//     triangle identity, explicit breaks and focused selected readout;
//   • `FieldOutlookBarsPresentation10868` — "Before the day began";
//   • `FieldMovementPresentation10868` — "By noon, the outlook shifted";
//   • `StoryStreamPresentationView10868` — the controlled story stream;
//   • `OriginalMarketCatalogueView9483` / `OriginalMarketDetailsView9483` —
//     all original outcomes and the held original's Details.
//
// Nothing here decides a value, a comparison or a label. The phase is the
// owner's explicit input, never read from a clock, a quote, a station reading
// or a result. Whether the selected reading IS the before-day reference, a
// distinct earlier inspection or a recorded chance during the day is the
// owner's: it arrives as the history's own readout intent and focused selected
// readout, and the anchor and the compact context both show exactly the
// slots the history resolves (`FieldHistoryGeometry10868.selectedSummary`) —
// a missing inspected observation keeps the owner's words and never borrows a
// neighbour. Every figure, clock, label, provenance, movement, measurement and
// result word is the owner's string, shown verbatim. Independent ranges and
// Yes/No originals are never normalized, summed or complemented; a station
// measurement is never a probability point and never grades a range; a result
// is never a history endpoint. The owner's runs, gaps and breaks are drawn as
// supplied.
//
// Phase gates, from the owner's phase only: the outlook card mounts when its
// own phase is the page's; the noon card mounts during and after the day when
// its own phase is the page's (the leaf also hides itself before the day); the
// station measurement shows during and after the day; the resolved-range words
// show after the day only. The page shows the owner's Info, source, report and
// original text verbatim and decides nothing about when a fact became known:
// the owner supplies phase-appropriate text — before the day only admitted
// before facts, during the day no final maximum or result — and this layer
// never parses or filters prose.
//
// Holds. The owner may pass an interaction hook so it can hold before a page
// action lands: on the page — the Info entry, the anchor's actions, inspection
// choices and plot taps, the context's Chart, the all-originals entry and,
// outside the stream, each card's choose, open and full-card actions — and in
// the catalogue and Details content, the action calls the hook ONCE and then
// the owner's exact callback with its exact value. A card inside the stream
// calls the stream's own activation instead. Full-size content (the history
// and card readers, Info and source) keeps the exact callbacks: its host
// already holds while it is open. Building or reading the view calls nothing.
// Without a callback there is no control and no hook call.
//
// Layout. A compact width or an accessibility size stacks: heading, anchor,
// then a LazyVStack section whose header is the compact context (pinned when
// the host's scroll contains it) above the stream and the originals entry. A
// regular or unspecified width puts the anchor beside the owner's ranked cards
// while both keep their minimum widths, otherwise it stacks too. The host owns
// the scroll, pinning, navigation, sheets, Back/Done, focus, reader memory,
// selection, inspection, ranking, live updates and subscriptions; this view
// keeps no state, runs no timer and presents nothing of its own.
//
// Host binding still owed — not available at this base: an owner that admits,
// for one event snapshot, the phase and heading words; the cohort history with
// its runs, breaks, guide, readout intent, focused selected readout and held
// inspection; the outlook and noon inputs; the stream with its ranked eligible
// card ids and card links; the station measurement and resolved-range words;
// the Info and source text with links; all 22 originals with their held
// selection and recorded context — and maps every callback, including from a
// card's exact original reference to the Details selection it names.

// MARK: - Phase, cards, modes

/// The owner's explicit phase for the whole page.
nonisolated enum WeatherEventPagePhase10868: String, Hashable, CaseIterable {
    case before
    case during
    case final
}

/// One card the page can show full size. `history` is the anchor.
nonisolated enum WeatherEventPageCard10868: String, Hashable, CaseIterable {
    case history
    /// "Before the day began".
    case ranges
    /// "By noon, the outlook shifted".
    case movement
}

/// What the host's container is showing, chosen by the host.
nonisolated enum WeatherEventPageMode10868: Equatable {
    case page
    case reader(WeatherEventPageCard10868)
    /// All original outcomes.
    case catalogue
    /// The held original's Details.
    case original
    /// The owner's event Info.
    case about
    /// One owner source document, by its exact id.
    case source(String)
}

nonisolated enum WeatherEventPageArrangement10868: Equatable {
    case stacked
    case sideBySide
}

// MARK: - Input

/// The owner's daily-high heading words. No scoreboard: a range is not a competitor.
nonisolated struct WeatherEventPageHeader10868: Equatable {
    /// The owner's event title, e.g. "<city>’s daily high".
    let title: String
    /// The owner's place words, e.g. "<station name> · <station code>".
    let place: String
    /// The owner's date words, e.g. "<date> · the day runs midnight to midnight in <city>".
    let date: String
    /// The owner's status words, e.g. "Captured by noon in <city>"; nil draws none.
    let status: String?
    /// The selected range's meaning, e.g. "<range> Yes · the day’s high falls in this range"; nil draws none.
    let selectedMeaning: String?
    /// "About this temperature event".
    let infoLabel: String
    let infoHint: String?
}

/// The owner's one-line words above full-size content.
nonisolated struct WeatherEventPageReaderHeader10868: Equatable {
    /// e.g. "<city> · By noon".
    let title: String
    /// e.g. "<range> · Yes"; nil draws none.
    let state: String?
}

/// The owner's qualified station measurement. Never a probability, a point or a grade.
nonisolated struct WeatherEventPageStationFact10868: Equatable {
    /// "Captured high so far" / "Captured station high".
    let label: String
    /// The owner-formatted measurement, e.g. "<temperature>".
    let value: String
    /// "160 NWS observations through noon · first at 9:00 AM ET"; nil draws none.
    let detail: String?
    /// "Sub-hourly, Celsius precision · not the contract’s hourly table"; nil draws none.
    let note: String?
}

/// The owner's resolved-range words, from the existing settlement owner.
nonisolated struct WeatherEventPageResultFact10868: Equatable {
    /// "Resolved range".
    let label: String
    /// The owner-formatted resolved range, e.g. "<range>".
    let words: String
    /// "Exact CLOB winner flags · separate from the last recorded chance"; nil none.
    let detail: String?
}

/// The owner's link from one stream card id to the card it shows.
nonisolated struct WeatherEventPageStory10868: Equatable {
    /// Exactly as in `StoryStreamPresentation10868.cards`.
    let cardID: String
    let card: WeatherEventPageCard10868
    /// The owner's words for why this card is here; nil draws none.
    var reason: String? = nil
}

/// One external link the owner names, handed back exactly on open.
nonisolated struct WeatherEventPageLink10868: Equatable {
    let id: String
    /// "Original provider event".
    let label: String
    let url: URL
}

/// One section of the owner's Info or source text, verbatim.
nonisolated struct WeatherEventPageSection10868: Equatable {
    let title: String
    let paragraphs: [String]
    /// An external link; nil draws none.
    var link: WeatherEventPageLink10868? = nil
    /// The exact id of a source document this section opens; nil draws none.
    var sourceID: String? = nil
}

/// The owner's event Info.
nonisolated struct WeatherEventPageAbout10868: Equatable {
    let title: String
    let sections: [WeatherEventPageSection10868]
}

/// One owner source document ("Original source rules"), by exact id.
nonisolated struct WeatherEventPageSource10868: Equatable {
    let id: String
    let title: String
    let sections: [WeatherEventPageSection10868]
}

/// The owner's words for the compact probability context.
nonisolated struct WeatherEventPageContextCopy10868: Equatable {
    /// Spoken name ("Selected range probability").
    let label: String
    /// e.g. "<city> · By noon"; nil draws none.
    let heading: String?
    /// "Chart" — opens the full history through the history's own expand id.
    let chartLabel: String
    let chartSpokenLabel: String?
}

nonisolated struct WeatherEventPageCopy10868: Equatable {
    /// Spoken name of the stories group ("The day in probabilities").
    let storiesLabel: String
    /// Shown where a card id names no single card this phase mounts.
    let storyUnavailable: String
    /// "All 11 ranges · 22 original outcomes"; nil draws no entry.
    let catalogueLabel: String?
    /// "Open full card" — the full-card control outside the stream.
    let openCardLabel: String
    /// "Source details & rules" — the control of a section that opens a source.
    let sourceLabel: String
    /// Shown in source mode when the id names no single source.
    let sourceUnavailable: String
    let context: WeatherEventPageContextCopy10868
}

nonisolated struct WeatherEventPageInput10868: Equatable {
    let phase: WeatherEventPagePhase10868
    let header: WeatherEventPageHeader10868
    let reader: WeatherEventPageReaderHeader10868
    /// "Refreshing · recorded history retained"; nil draws none.
    var notice: String? = nil
    /// The anchor: the owner's cohort history and its held selection and inspection.
    let history: FieldHistoryInput10868
    /// "Before the day began"; mounted when its phase is the page's.
    let outlook: FieldOutlookInput10868?
    /// "By noon, the outlook shifted"; mounted during and after the day.
    let movement: FieldMovementInput10868?
    /// The owner's story stream; nil draws no stream.
    let stream: StoryStreamPresentation10868?
    let stories: [WeatherEventPageStory10868]
    /// The owner's ranked eligible card ids, in its order. Never sorted here.
    let ranked: [String]
    /// Shown during and after the day only.
    let station: WeatherEventPageStationFact10868?
    /// Shown after the day only.
    let result: WeatherEventPageResultFact10868?
    let about: WeatherEventPageAbout10868?
    let sources: [WeatherEventPageSource10868]
    let copy: WeatherEventPageCopy10868
}

/// The owner's original outcomes, for the catalogue and Details modes.
struct WeatherEventPageOriginals10868 {
    let catalogue: OriginalMarketDetails9483.Catalogue?
    let selection: OriginalMarketDetails9483.Selection?
    var recorded: OriginalMarketDetails9483.RecordedHistory? = nil
    var labels: [OriginalMarketDetails9483.Identity: String] = [:]
    /// "All original outcomes".
    let heading: String
    var context: String? = nil
    let emptyWords: String
    let unavailableChoice: String
    let tint: Color
}

nonisolated enum WeatherEventPageAccessibilityID10868 {
    static let page = "weatherEventPage10868.page"
    static let header = "weatherEventPage10868.header"
    static let info = "weatherEventPage10868.header.info"
    static let notice = "weatherEventPage10868.notice"
    static let station = "weatherEventPage10868.station"
    static let result = "weatherEventPage10868.result"
    static let anchor = "weatherEventPage10868.anchor"
    static let context = "weatherEventPage10868.context"
    static let contextChart = "weatherEventPage10868.context.chart"
    static let stories = "weatherEventPage10868.stories"
    static let cards = "weatherEventPage10868.cards"
    static let unavailable = "weatherEventPage10868.card.unavailable"
    static let catalogueEntry = "weatherEventPage10868.catalogue.entry"
    static let catalogue = "weatherEventPage10868.catalogue"
    static let original = "weatherEventPage10868.original"
    static let about = "weatherEventPage10868.about"
    static let source = "weatherEventPage10868.source"
    static let readerHeader = "weatherEventPage10868.readerHeader"
    static let readerInfo = "weatherEventPage10868.readerHeader.info"
    static func card(_ card: WeatherEventPageCard10868) -> String { "weatherEventPage10868.card.\(card.rawValue)" }
    static func openCard(_ card: WeatherEventPageCard10868) -> String { "weatherEventPage10868.card.\(card.rawValue).open" }
    static func link(_ id: String) -> String { "weatherEventPage10868.link.\(id)" }
    static func sourceEntry(_ id: String) -> String { "weatherEventPage10868.sourceEntry.\(id)" }
}

// MARK: - Model

/// One ranked card id, resolved: the owner's link, or its unavailable slot.
nonisolated enum WeatherEventPageRankedSlot10868: Equatable {
    case story(WeatherEventPageStory10868)
    case unavailable(String)
}

/// Which leaves the page mounts, resolved once per input.
nonisolated struct WeatherEventPageModel10868: Equatable {
    let input: WeatherEventPageInput10868

    init(_ input: WeatherEventPageInput10868) {
        self.input = input
    }

    static func leafPhase(_ phase: WeatherEventPagePhase10868) -> FieldOutlookPhase10868 {
        switch phase {
        case .before: .before
        case .during: .during
        case .final: .final
        }
    }

    static func readable(_ words: String?) -> String? { FieldMovementModel10868.readable(words) }

    // MARK: Phase gates

    /// The outlook at the page's own phase. Otherwise nothing.
    var outlook: FieldOutlookInput10868? {
        guard let outlook = input.outlook, outlook.phase == Self.leafPhase(input.phase) else { return nil }
        return outlook
    }

    /// The noon card during and after the day, at the page's own phase.
    var movement: FieldMovementInput10868? {
        guard input.phase != .before, let movement = input.movement,
              movement.phase == Self.leafPhase(input.phase) else { return nil }
        return movement
    }

    /// The station measurement, during and after the day only.
    var station: WeatherEventPageStationFact10868? {
        input.phase == .before ? nil : input.station
    }

    /// The resolved-range words, after the day only.
    var result: WeatherEventPageResultFact10868? {
        input.phase == .final ? input.result : nil
    }

    func isMounted(_ card: WeatherEventPageCard10868) -> Bool {
        switch card {
        case .history: true
        case .ranges: outlook != nil
        case .movement: movement != nil
        }
    }

    func readerShows(_ card: WeatherEventPageCard10868) -> Bool { isMounted(card) }

    // MARK: Stories

    /// The owner's link a card id names: exactly one link with that id, to a
    /// card this phase mounts. Otherwise nothing.
    func story(_ cardID: String) -> WeatherEventPageStory10868? {
        let links = input.stories.filter { $0.cardID == cardID }
        guard links.count == 1, let link = links.first, link.card != .history, isMounted(link.card) else { return nil }
        return link
    }

    /// The owner's ranked ids, in its order: a repeated or unresolved id is an
    /// unavailable slot, never a neighbour.
    var rankedSlots: [WeatherEventPageRankedSlot10868] {
        var counts: [String: Int] = [:]
        for id in input.ranked { counts[id, default: 0] += 1 }
        return input.ranked.map { id in
            guard counts[id] == 1, let link = story(id) else { return .unavailable(id) }
            return .story(link)
        }
    }

    // MARK: History

    /// The anchor full size: the same history — its focused composition, key,
    /// selection, inspection and readouts unchanged — without its own expand
    /// control inside the reader.
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
            layout: history.layout,
            probabilityLowerBound: history.probabilityLowerBound,
            probabilityRangeExplanation: history.probabilityRangeExplanation,
            selectedReadout: history.selectedReadout, inspectionRingShape: history.inspectionRingShape,
            plotAbsence: history.plotAbsence, showsKey: history.showsKey
        )
    }

    // MARK: Compact probability context

    /// Exactly the focused readout the anchor resolves: the selected range
    /// with its slots, or the owner's absence words.
    var selectedSummary: FieldHistorySelectedSummary10868 {
        FieldHistoryGeometry10868.selectedSummary(input.history)
    }

    /// The context in words: heading, then the selected range and its slots.
    var contextSummary: String {
        var parts = [input.copy.context.heading].compactMap(Self.readable)
        switch selectedSummary {
        case .none:
            break
        case .words(let words):
            parts.append(words)
        case .original(let series, let slots):
            parts.append(series.name)
            parts += slots.map(FieldHistoryGeometry10868.spokenSlot)
        }
        return parts.joined(separator: ". ")
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

    /// The context belongs to the stacked page; wide keeps the anchor in view.
    static func showsContext(_ arrangement: WeatherEventPageArrangement10868) -> Bool {
        arrangement == .stacked
    }

    // MARK: Info and sources

    static func hasWords(_ section: WeatherEventPageSection10868) -> Bool {
        readable(section.title) != nil || section.paragraphs.contains { readable($0) != nil }
    }

    var about: WeatherEventPageAbout10868? {
        guard let about = input.about,
              Self.readable(about.title) != nil || about.sections.contains(where: Self.hasWords)
        else { return nil }
        return about
    }

    func aboutAvailable(canOpen: Bool) -> Bool { canOpen && about != nil }

    /// The reader heading's Info entry: full-size history and card readers only.
    func aboutEntry(mode: WeatherEventPageMode10868, canOpen: Bool) -> Bool {
        guard case .reader = mode, Self.readable(input.header.infoLabel) != nil else { return false }
        return aboutAvailable(canOpen: canOpen)
    }

    /// The source document an id names: exactly one, with a nonblank id.
    func source(_ id: String) -> WeatherEventPageSource10868? {
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
    /// width tries the anchor beside the cards, then stacks.
    static func arrangements(sizeClass: UserInterfaceSizeClass?, accessibilitySize: Bool) -> [WeatherEventPageArrangement10868] {
        sizeClass != .compact && !accessibilitySize ? [.sideBySide, .stacked] : [.stacked]
    }
}

// MARK: - Small owner-labelled leaves

/// The owner's station measurement and resolved-range words, each under its
/// own label, apart from every chance.
struct WeatherEventPageFactsPresentation10868: View {
    let station: WeatherEventPageStationFact10868?
    let result: WeatherEventPageResultFact10868?

    @Environment(\.dynamicTypeSize) private var typeSize

    var body: some View {
        if station != nil || result != nil {
            Group {
                if typeSize.isAccessibilitySize {
                    VStack(alignment: .leading, spacing: 12) { facts }
                } else {
                    ViewThatFits(in: .horizontal) {
                        HStack(alignment: .top, spacing: 20) { facts }
                        VStack(alignment: .leading, spacing: 12) { facts }
                    }
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    @ViewBuilder private var facts: some View {
        if let result {
            fact(label: result.label, value: result.words, lines: [result.detail])
                .accessibilityIdentifier(WeatherEventPageAccessibilityID10868.result)
        }
        if let station {
            fact(label: station.label, value: station.value, lines: [station.detail, station.note])
                .accessibilityIdentifier(WeatherEventPageAccessibilityID10868.station)
        }
    }

    static func spoken(label: String, value: String, lines: [String?]) -> String {
        ([label, value] + lines.compactMap(WeatherEventPageModel10868.readable)).joined(separator: ". ")
    }

    private func fact(label: String, value: String, lines: [String?]) -> some View {
        VStack(alignment: .leading, spacing: 3) {
            Text(label)
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(DS.textSecondary)
            Text(value)
                .font(.title3.bold())
                .monospacedDigit()
                .foregroundStyle(DS.textPrimary)
            ForEach(Array(lines.compactMap(WeatherEventPageModel10868.readable).enumerated()), id: \.offset) { _, line in
                Text(line)
                    .font(.subheadline)
                    .foregroundStyle(DS.textPrimary)
            }
        }
        .fixedSize(horizontal: false, vertical: true)
        .frame(maxWidth: .infinity, alignment: .leading)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(Self.spoken(label: label, value: value, lines: lines))
    }
}

/// The selected range's focused readout, exactly as the anchor resolves it,
/// and Chart to the full history. The host mounts or pins it; it keeps no
/// selection of its own.
struct WeatherEventPageContextPresentation10868: View {
    let model: WeatherEventPageModel10868
    /// The history's own expand action, after the page hook. Nil: no Chart control.
    var onChart: (() -> Void)?

    @Environment(\.dynamicTypeSize) private var typeSize
    @ScaledMetric(relativeTo: .body) private var controlSize: CGFloat = 44

    private var copy: WeatherEventPageContextCopy10868 { model.input.copy.context }

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(alignment: .center, spacing: 8) {
                if let heading = WeatherEventPageModel10868.readable(copy.heading) {
                    Text(heading)
                        .font(.subheadline.weight(.semibold))
                        .foregroundStyle(DS.textPrimary)
                        .fixedSize(horizontal: false, vertical: true)
                        .frame(maxWidth: .infinity, alignment: .leading)
                } else {
                    Spacer(minLength: 0)
                }
                if let onChart {
                    Button(action: onChart) {
                        HStack(spacing: 4) {
                            Text(copy.chartLabel).font(.subheadline.weight(.semibold))
                            Image(systemName: "arrow.up.right").font(.caption.weight(.semibold)).accessibilityHidden(true)
                        }
                        .foregroundStyle(DS.blue)
                        .frame(minWidth: controlSize, minHeight: controlSize)
                        .contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                    .accessibilityLabel(copy.chartSpokenLabel ?? copy.chartLabel)
                    .accessibilityIdentifier(WeatherEventPageAccessibilityID10868.contextChart)
                }
            }
            summary
        }
        .padding(.vertical, 8)
        .frame(maxWidth: .infinity, alignment: .leading)
        .accessibilityElement(children: .contain)
        .accessibilityLabel(copy.label)
        .accessibilityIdentifier(WeatherEventPageAccessibilityID10868.context)
    }

    @ViewBuilder private var summary: some View {
        switch model.selectedSummary {
        case .none:
            EmptyView()
        case .words(let words):
            Text(words)
                .font(.subheadline)
                .foregroundStyle(DS.textPrimary)
                .fixedSize(horizontal: false, vertical: true)
        case .original(let series, let slots):
            VStack(alignment: .leading, spacing: 4) {
                Text(series.name)
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(series.tint)
                    .fixedSize(horizontal: false, vertical: true)
                LazyVGrid(columns: Array(repeating: GridItem(.flexible(), spacing: 14, alignment: .topLeading),
                                         count: typeSize.isAccessibilitySize ? 1 : max(1, slots.count)),
                          alignment: .leading, spacing: 8) {
                    ForEach(Array(slots.enumerated()), id: \.offset) { _, slot in
                        slotView(slot)
                    }
                }
            }
            .accessibilityElement(children: .ignore)
            .accessibilityLabel(([series.name] + slots.map(FieldHistoryGeometry10868.spokenSlot)).joined(separator: ". "))
        }
    }

    private func slotView(_ slot: FieldHistoryReadoutSlot10868) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(slot.label)
                .font(.caption)
                .foregroundStyle(DS.textSecondary)
            switch slot.display {
            case .figure(let figure, let provenance):
                Text(figure)
                    .font(.headline.monospacedDigit())
                    .foregroundStyle(DS.textPrimary)
                Text(provenance)
                    .font(.caption)
                    .foregroundStyle(DS.textPrimary)
            case .words(let words):
                Text(words)
                    .font(.subheadline.weight(.medium))
                    .foregroundStyle(DS.textPrimary)
            }
        }
        .fixedSize(horizontal: false, vertical: true)
    }
}

/// The owner's Info or source text in its own words. A section's link hands the
/// owner its exact link; a section's source control hands back its exact id,
/// only when that id names exactly one source. With no callback, words only.
struct WeatherEventPageSectionsContent10868: View {
    let title: String
    let sections: [WeatherEventPageSection10868]
    /// Ids that resolve to exactly one source document.
    let sourceIDs: Set<String>
    let sourceLabel: String
    var onLink: ((WeatherEventPageLink10868) -> Void)? = nil
    var onSource: ((String) -> Void)? = nil

    @ScaledMetric(relativeTo: .body) private var controlSize: CGFloat = 44

    /// The section's exact link for the host to open, or nothing.
    func linkAction(_ link: WeatherEventPageLink10868?) -> (() -> Void)? {
        guard let link, WeatherEventPageModel10868.readable(link.label) != nil, let onLink else { return nil }
        return { onLink(link) }
    }

    /// The section's exact source id, only when it resolves and with a callback.
    func sourceAction(_ id: String?) -> (() -> Void)? {
        guard let id, sourceIDs.contains(id), WeatherEventPageModel10868.readable(sourceLabel) != nil,
              let onSource else { return nil }
        return { onSource(id) }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            if let title = WeatherEventPageModel10868.readable(title) {
                Text(title)
                    .font(.headline)
                    .foregroundStyle(DS.textPrimary)
                    .accessibilityAddTraits(.isHeader)
            }
            ForEach(Array(sections.enumerated()), id: \.offset) { _, section in
                if WeatherEventPageModel10868.hasWords(section) {
                    VStack(alignment: .leading, spacing: 6) {
                        if let title = WeatherEventPageModel10868.readable(section.title) {
                            Text(title)
                                .font(.body.weight(.semibold))
                                .foregroundStyle(DS.textPrimary)
                                .accessibilityAddTraits(.isHeader)
                        }
                        ForEach(Array(section.paragraphs.enumerated()), id: \.offset) { _, paragraph in
                            if let words = WeatherEventPageModel10868.readable(paragraph) {
                                Text(words).font(.body).foregroundStyle(DS.textPrimary)
                            }
                        }
                        if let action = sourceAction(section.sourceID), let id = section.sourceID {
                            control(sourceLabel, symbol: "doc.text", action: action)
                                .accessibilityIdentifier(WeatherEventPageAccessibilityID10868.sourceEntry(id))
                        }
                        if let link = section.link, let action = linkAction(link) {
                            control(link.label, symbol: "arrow.up.right", action: action)
                                .accessibilityAddTraits(.isLink)
                                .accessibilityIdentifier(WeatherEventPageAccessibilityID10868.link(link.id))
                        } else if let link = section.link, let label = WeatherEventPageModel10868.readable(link.label) {
                            Text(label)
                                .font(.subheadline)
                                .foregroundStyle(DS.textSecondary)
                                .accessibilityIdentifier(WeatherEventPageAccessibilityID10868.link(link.id))
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

struct WeatherEventPagePresentation10868: View {
    typealias Stream = StoryStreamPresentation10868

    let input: WeatherEventPageInput10868
    var mode: WeatherEventPageMode10868 = .page
    /// The catalogue and Details modes; nil: neither has any.
    var originals: WeatherEventPageOriginals10868? = nil
    /// Opens the host's container on the owner's Info.
    var onAbout: (() -> Void)? = nil
    /// A source document's exact id, for the host to open.
    var onSource: ((String) -> Void)? = nil
    /// A section's exact external link, for the host to open.
    var onLink: ((WeatherEventPageLink10868) -> Void)? = nil
    /// Opens all original outcomes.
    var onCatalogue: (() -> Void)? = nil
    /// A catalogue card's exact selection.
    var onOriginalSelect: ((OriginalMarketDetails9483.Selection) -> Void)? = nil
    /// A Details history control's exact intent.
    var onOriginalHistory: ((OriginalMarketDetails9483.HistoryIntent) -> Void)? = nil
    /// The anchor's exact action ids — its expand, original and previous/next
    /// included; the context's Chart hands back the expand id too.
    var onHistoryAction: ((String) -> Void)? = nil
    var onHistoryInspectionChoice: ((String) -> Void)? = nil
    var onHistoryPlotPosition: ((Double) -> Void)? = nil
    /// The outlook's exact range choice (a bar or previous/next).
    var onRangeChoose: ((FieldChooserOriginalRef10868) -> Void)? = nil
    /// The outlook's exact original to open.
    var onRangeOpen: ((FieldChooserOriginalRef10868) -> Void)? = nil
    /// The noon card's exact original and observation key.
    var onMovementOpen: ((FieldMovementOpen10868) -> Void)? = nil
    var onStoryIntent: ((Stream.Intent) -> Void)? = nil
    /// Opens a card full size, outside the stream.
    var onReaderOpen: ((WeatherEventPageCard10868) -> Void)? = nil
    /// Called once just before a page, catalogue or Details action reaches its
    /// owner callback. Never by building the view, by full-size content or by
    /// a card inside the stream.
    var onInteraction: (() -> Void)? = nil

    @Environment(\.horizontalSizeClass) private var sizeClass
    @Environment(\.dynamicTypeSize) private var typeSize
    @ScaledMetric(relativeTo: .body) private var anchorMinWidth: CGFloat = 440
    @ScaledMetric(relativeTo: .body) private var cardsMinWidth: CGFloat = 340
    @ScaledMetric(relativeTo: .body) private var controlSize: CGFloat = 44

    var model: WeatherEventPageModel10868 { WeatherEventPageModel10868(input) }

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

    /// A card's own action inside the stream, after the stream's activation.
    static func relay<Value>(_ action: ((Value) -> Void)?,
                             through activation: StoryStreamCardActivation10868?) -> ((Value) -> Void)? {
        guard let action else { return nil }
        guard let activation else { return action }
        return { value in
            activation.request()
            action(value)
        }
    }

    /// Full size: the exact callback. In the stream: its activation first.
    /// Elsewhere on the page: the page hook first.
    private func route<Value>(_ action: ((Value) -> Void)?, activation: StoryStreamCardActivation10868?,
                              reader: Bool) -> ((Value) -> Void)? {
        if reader { return action }
        if let activation { return Self.relay(action, through: activation) }
        return Self.held(action, by: pageHook)
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

    /// The heading's Info entry, after the page hook.
    var infoAction: (() -> Void)? { Self.heldAction(aboutOpener(), by: pageHook) }

    /// The anchor passes the page hook first; full size keeps the exact callbacks.
    func historyContent(reader: Bool) -> FieldProbabilityHistoryPresentation10868 {
        let interaction = reader ? nil : pageHook
        return FieldProbabilityHistoryPresentation10868(
            input: reader ? model.readerHistory : input.history,
            onAction: Self.held(onHistoryAction, by: interaction),
            onInspectionChoice: Self.held(onHistoryInspectionChoice, by: interaction),
            onPlotPosition: Self.held(onHistoryPlotPosition, by: interaction)
        )
    }

    /// The before-day range outlook, at the page's phase.
    func outlookContent(activation: StoryStreamCardActivation10868? = nil,
                        reader: Bool = false) -> FieldOutlookBarsPresentation10868? {
        model.outlook.map {
            FieldOutlookBarsPresentation10868(
                input: $0,
                onChoose: route(onRangeChoose, activation: activation, reader: reader),
                onOpenOriginal: route(onRangeOpen, activation: activation, reader: reader))
        }
    }

    /// The noon shift, during and after the day.
    func movementContent(activation: StoryStreamCardActivation10868? = nil,
                         reader: Bool = false) -> FieldMovementPresentation10868? {
        model.movement.map {
            FieldMovementPresentation10868(input: $0, onOpen: route(onMovementOpen, activation: activation, reader: reader))
        }
    }

    /// The compact context. Its Chart hands back the history's own expand id
    /// after the page hook.
    func contextContent() -> WeatherEventPageContextPresentation10868 {
        var chart: (() -> Void)?
        if let id = model.contextChartID(canOpen: onHistoryAction != nil), let action = onHistoryAction {
            chart = { action(id) }
        }
        return WeatherEventPageContextPresentation10868(model: model, onChart: Self.heldAction(chart, by: pageHook))
    }

    /// The full-card control outside the stream, after the page hook.
    func openCardAction(_ card: WeatherEventPageCard10868) -> (() -> Void)? {
        guard model.isMounted(card), let open = onReaderOpen else { return nil }
        return Self.heldAction({ open(card) }, by: pageHook)
    }

    /// The all-originals entry, after the page hook.
    var catalogueAction: (() -> Void)? {
        guard model.catalogueAvailable(canOpen: onCatalogue != nil, hasOriginals: originals != nil) else { return nil }
        return Self.heldAction(onCatalogue, by: pageHook)
    }

    /// The existing catalogue with all original outcomes, its select after the hook.
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
    func aboutContent() -> WeatherEventPageSectionsContent10868? {
        model.about.map {
            WeatherEventPageSectionsContent10868(title: $0.title, sections: $0.sections, sourceIDs: model.sourceIDs,
                                                 sourceLabel: input.copy.sourceLabel, onLink: onLink, onSource: onSource)
        }
    }

    /// One source document by exact id — already held content. Nil when the id
    /// names no single source.
    func sourceContent(_ id: String) -> WeatherEventPageSectionsContent10868? {
        model.source(id).map {
            WeatherEventPageSectionsContent10868(title: $0.title, sections: $0.sections, sourceIDs: model.sourceIDs,
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
            let arrangements = WeatherEventPageModel10868.arrangements(
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
        .accessibilityIdentifier(WeatherEventPageAccessibilityID10868.page)
    }

    /// Heading, anchor, then the stories under the compact context — a
    /// section header the host's scroll pins.
    private var stackedPage: some View {
        LazyVStack(alignment: .leading, spacing: 16, pinnedViews: [.sectionHeaders]) {
            header
            anchor
            Section {
                stories
            } header: {
                contextContent()
                    .background(DS.surface)
            }
        }
    }

    /// The heading across; the anchor beside the owner's ranked cards.
    private var widePage: some View {
        VStack(alignment: .leading, spacing: 16) {
            header
            HStack(alignment: .top, spacing: 24) {
                anchor
                    .frame(minWidth: anchorMinWidth, maxWidth: .infinity, alignment: .topLeading)
                    .layoutPriority(1)
                rankedColumn
                    .frame(minWidth: cardsMinWidth, maxWidth: .infinity, alignment: .topLeading)
            }
        }
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(alignment: .top, spacing: 12) {
                VStack(alignment: .leading, spacing: 4) {
                    Text(input.header.title)
                        .font(.title2.bold())
                        .foregroundStyle(DS.textPrimary)
                        .accessibilityAddTraits(.isHeader)
                    Text(input.header.place)
                        .font(.subheadline.weight(.semibold))
                        .foregroundStyle(DS.textPrimary)
                    Text(input.header.date)
                        .font(.subheadline)
                        .foregroundStyle(DS.textPrimary)
                    if let status = WeatherEventPageModel10868.readable(input.header.status) {
                        Text(status)
                            .font(.subheadline.weight(.semibold))
                            .foregroundStyle(DS.textPrimary)
                    }
                }
                .fixedSize(horizontal: false, vertical: true)
                .frame(maxWidth: .infinity, alignment: .leading)
                if let infoAction {
                    Button(action: infoAction) {
                        Image(systemName: "info.circle")
                            .font(.title3)
                            .foregroundStyle(DS.textPrimary)
                            .frame(minWidth: controlSize, minHeight: controlSize)
                            .contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                    .accessibilityLabel(input.header.infoLabel)
                    .accessibilityHint(input.header.infoHint ?? "")
                    .accessibilityIdentifier(WeatherEventPageAccessibilityID10868.info)
                }
            }
            if let notice = WeatherEventPageModel10868.readable(input.notice) {
                Text(notice)
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
                    .accessibilityIdentifier(WeatherEventPageAccessibilityID10868.notice)
            }
            WeatherEventPageFactsPresentation10868(station: model.station, result: model.result)
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .modifier(WeatherEventPageCardSurface10868())
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(WeatherEventPageAccessibilityID10868.header)
    }

    /// The selected range's meaning, then the focused history.
    private var anchor: some View {
        VStack(alignment: .leading, spacing: 10) {
            if let meaning = WeatherEventPageModel10868.readable(input.header.selectedMeaning) {
                Text(meaning)
                    .font(.headline)
                    .foregroundStyle(DS.textPrimary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            historyContent(reader: false)
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .modifier(WeatherEventPageCardSurface10868())
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(WeatherEventPageAccessibilityID10868.anchor)
    }

    /// The owner's stream when it supplies one — otherwise its ranked cards —
    /// then the all-originals entry.
    private var stories: some View {
        VStack(alignment: .leading, spacing: 16) {
            if let stream = input.stream {
                StoryStreamPresentationView10868(stream, onIntent: onStoryIntent) { card, activation in
                    storyCell(card.id, activation: activation)
                }
                .accessibilityElement(children: .contain)
                .accessibilityLabel(input.copy.storiesLabel)
                .accessibilityIdentifier(WeatherEventPageAccessibilityID10868.stories)
            } else {
                rankedCards
            }
            catalogueEntry
        }
    }

    /// The owner's ranked cards beside the anchor, then the all-originals entry.
    private var rankedColumn: some View {
        VStack(alignment: .leading, spacing: 16) {
            rankedCards
            catalogueEntry
        }
    }

    private var rankedCards: some View {
        VStack(alignment: .leading, spacing: 16) {
            ForEach(Array(model.rankedSlots.enumerated()), id: \.offset) { _, slot in
                switch slot {
                case .story(let link):
                    VStack(alignment: .leading, spacing: 8) {
                        storyCell(link.cardID, activation: nil)
                        if let open = openCardAction(link.card) {
                            Button(action: open) {
                                Text(input.copy.openCardLabel)
                                    .font(.subheadline.weight(.semibold))
                                    .foregroundStyle(DS.blue)
                                    .frame(minHeight: controlSize, alignment: .leading)
                                    .contentShape(Rectangle())
                            }
                            .buttonStyle(.plain)
                            .accessibilityIdentifier(WeatherEventPageAccessibilityID10868.openCard(link.card))
                        }
                    }
                case .unavailable:
                    unavailableCell
                }
            }
        }
        .accessibilityElement(children: .contain)
        .accessibilityLabel(input.copy.storiesLabel)
        .accessibilityIdentifier(WeatherEventPageAccessibilityID10868.cards)
    }

    /// The card the owner links to this id, or the owner's unavailable words.
    @ViewBuilder private func storyCell(_ cardID: String, activation: StoryStreamCardActivation10868?) -> some View {
        if let link = model.story(cardID) {
            VStack(alignment: .leading, spacing: 8) {
                if let reason = WeatherEventPageModel10868.readable(link.reason) {
                    Text(reason)
                        .font(.subheadline)
                        .foregroundStyle(DS.textPrimary)
                        .fixedSize(horizontal: false, vertical: true)
                }
                cardContent(link.card, activation: activation, reader: false)
            }
            .padding(16)
            .frame(maxWidth: .infinity, alignment: .leading)
            .modifier(WeatherEventPageCardSurface10868())
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier(WeatherEventPageAccessibilityID10868.card(link.card))
        } else {
            unavailableCell
        }
    }

    private var unavailableCell: some View {
        Text(input.copy.storyUnavailable)
            .font(.subheadline)
            .foregroundStyle(DS.textSecondary)
            .fixedSize(horizontal: false, vertical: true)
            .frame(maxWidth: .infinity, minHeight: 120, alignment: .leading)
            .padding(16)
            .modifier(WeatherEventPageCardSurface10868())
            .accessibilityIdentifier(WeatherEventPageAccessibilityID10868.unavailable)
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
                .modifier(WeatherEventPageCardSurface10868())
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .accessibilityIdentifier(WeatherEventPageAccessibilityID10868.catalogueEntry)
        }
    }

    // MARK: Content shared by the page and the readers

    @ViewBuilder private func cardContent(_ card: WeatherEventPageCard10868,
                                          activation: StoryStreamCardActivation10868?, reader: Bool) -> some View {
        switch card {
        case .history: historyContent(reader: true)
        case .ranges: outlookContent(activation: activation, reader: reader)
        case .movement: movementContent(activation: activation, reader: reader)
        }
    }

    /// The same leaf and input, full size, under the compact words. A card this
    /// phase does not show has no content.
    @ViewBuilder private func reader(_ card: WeatherEventPageCard10868) -> some View {
        if model.readerShows(card) {
            VStack(alignment: .leading, spacing: 16) {
                compactHeader
                cardContent(card, activation: nil, reader: true)
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
                if let state = WeatherEventPageModel10868.readable(input.reader.state) {
                    Text(state)
                        .font(.subheadline)
                        .foregroundStyle(DS.textPrimary)
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
                .accessibilityLabel(input.header.infoLabel)
                .accessibilityHint(input.header.infoHint ?? "")
                .accessibilityIdentifier(WeatherEventPageAccessibilityID10868.readerInfo)
            }
        }
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(WeatherEventPageAccessibilityID10868.readerHeader)
    }

    @ViewBuilder private var catalogueMode: some View {
        if let catalogue = catalogueContent() {
            catalogue
                .accessibilityElement(children: .contain)
                .accessibilityIdentifier(WeatherEventPageAccessibilityID10868.catalogue)
        }
    }

    @ViewBuilder private var originalMode: some View {
        if let details = originalDetailsContent() {
            details
                .accessibilityElement(children: .contain)
                .accessibilityIdentifier(WeatherEventPageAccessibilityID10868.original)
        }
    }

    @ViewBuilder private var aboutMode: some View {
        if let content = aboutContent() {
            VStack(alignment: .leading, spacing: 12) {
                compactHeader
                content
            }
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier(WeatherEventPageAccessibilityID10868.about)
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
        .accessibilityIdentifier(WeatherEventPageAccessibilityID10868.source)
    }
}

/// The reference's white card on the page surface.
private struct WeatherEventPageCardSurface10868: ViewModifier {
    func body(content: Content) -> some View {
        content
            .background(DS.cardBg, in: RoundedRectangle(cornerRadius: 18, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 18, style: .continuous).stroke(DS.border, lineWidth: 1))
    }
}
