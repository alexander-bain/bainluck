import SwiftUI

// #10868 — the postponed match screen (`void`): one native presentation for a
// match the owner reports as postponed (or otherwise not played), composed
// from the accepted shared leaves. A fan sees, in this order: the owner's
// fixture words (league and the fixture's date) with a compact About entry,
// the named competitors, the owner's prominent match state and reason; the
// historical pregame probability chart with every supplied original's dated
// chance; the owner's status timeline — match postponement, market closure
// and sporting result kept as separate facts, and the owner's words for the
// reschedule; then the original markets with the held original's Details and
// the All props entry. The chart opens as full-size content made of the same
// View and the same history; All props, the held original's Details and the
// About are further content modes.
//
// PILLARS: FORMATTING / TRUTH. SHIP: a postponed match keeps its historical
// pregame chances and its original props without inventing a score, a match
// winner, a loss or 0%.
//
// Presentation only, extracted from the approved `PostponedHeader.tsx` /
// `postponed.css` (v183 / v289), over `postponedEvidence.ts` and its retained
// capture. The reference's capture loader, trade-hour qualification and
// cutoff, event and contract matching, timeline construction, hour election,
// clock formatting, story/session state, expand state and focus are NOT
// ported, and neither is its dashed-away line identity: originals are told
// apart by the shared chart's own shape and tint. The leaves are the actual
// accepted Views, unchanged:
//
//   • `FieldProbabilityHistoryPresentation10868` — the pregame chart, its key
//     and readouts, its inspection and its chart controls;
//   • `OriginalMarketChooserView9483` — the originals and the held original's
//     Details on the page;
//   • `OriginalMarketCatalogueView9483` / `OriginalMarketDetailsView9483` — All
//     props and the held original's Details (with the owner's recorded history
//     when admitted) as content modes.
//
// Nothing new is drawn here beyond arrangement, card surfaces, the owner's
// fixture, state, timeline, reader and About words, and the timeline's fact
// markers (a ring for the match, a closed square for a market, a bar for a
// sporting result — shape, never colour alone).
//
// TERMINAL ONLY. This route has one phase, the terminal status. There is no
// phase input and nothing here offers pregame or live applicability: no live
// status, clock, score, projection or result. The historical pregame
// observations still belong to the terminal view, and an original whose result
// is missing keeps its valid history.
//
// OWNER-RESOLVED, NEVER DERIVED HERE: the match state and reason (from the
// existing event identity and lifecycle authority — never read here from a raw
// status, a market, a quote or a settlement); the competitors and their order;
// the fixture's date words; every timeline fact, its kind, date words and
// detail, and the reschedule words; the history — its admitted independent
// series (blended where an owner publishes one, provider-named where not),
// runs, breaks, domain, ticks, readouts, inspection, selection, notes and
// controls; the originals, their identities, scope, modes, readings, grades
// and About rows; the held selection and its recorded history; the About and
// its sources. This layer never complements, normalizes or sums independent
// chances; never treats a missing value as zero; never selects a latest,
// nearest or later value for a selected hour (the chart binds an inspected
// figure only to its exact observation and keeps the owner's absence words);
// never adds a kickoff, settlement, announcement or closure marker to the
// chart; never turns a settlement amount or result into a probability, a mark
// or a 0%/100% end; never derives a match winner or a draw from market
// closure; and never rewrites mixed original states — open, fair-value
// closed, independently resolved, unconfirmed — into one blanket closure,
// void or loss. "All three closed" is the owner's words for its own proven
// specimen, never generated here.
//
// The full-size chart is the same history input — every series, run, break,
// tick, readout, selection, inspection and control — without its expand
// control (already open) and at the owner's reader plot height when that is
// taller. A selected hour stays exactly the owner's selection on both.
//
// The baselines in the compact heading of All props and Details are each
// supplied series' own earlier ("before") reading, displayed by the chart's
// own binding rule (`FieldHistoryGeometry10868.display`) under the owner's
// earlier-reading label — so the heading, the chart's key and the overview
// print one value with one provenance; the catalogue and Details print the
// owner's original readings, which the owner admits from the same
// observations.
//
// INTERACTION. The host owns the container, Back/Done, focus, scroll, every
// mode change, the held selection, the held hour and every genuine update;
// this view keeps no state, runs no timer or animation, holds no
// subscription, ranks nothing and presents no sheet or navigation. An absent
// callback means no enabled control. The owner may pass an interaction hook
// so it can hold incoming updates: on the page (the About control, the chart's
// actions, inspection choices and plot taps, an original choice, the All props
// entry) and in the catalogue and Details content (an original's selection, a
// Details history intent) the action calls that hook once and then the
// owner's exact callback with its exact value. Full-size content — the
// full-size chart and its compact heading's About entry, and the About with
// its source controls — keeps the exact callbacks: its host already holds.
// Building or reading the view calls nothing.
//
// LAYOUT. Phone stacks: fixture words and state, the chart, the timeline,
// then the originals. A regular or unspecified width (a Mac window) puts the
// fixture words, state and timeline in one column beside the chart while both
// keep their minimum widths, otherwise it stacks. Accessibility sizes always
// stack and grow. VoiceOver reads the same order in every arrangement: title,
// state, chart, timeline, originals.
//
// Host binding still owed — not available at this base: an owner that admits,
// for one postponed event snapshot, the lifecycle state and reason, the fixture
// and timeline facts with their kinds, the qualified independent pregame
// history with its inspection and controls, the originals with their own
// modes/readings/grades and any admitted recorded history, the About and its
// sources, and maps every callback to its existing controls.

// MARK: - Modes and arrangement

/// What the host's container is showing, chosen by the host.
nonisolated enum PostponedEventPageMode10868: Equatable {
    /// The match screen body.
    case page
    /// The pregame chart's full-size content.
    case history
    /// Every retained original ("All props").
    case catalogue
    /// The held original's Details.
    case original
    /// The owner's About.
    case about
}

nonisolated enum PostponedEventPageArrangement10868: Equatable {
    case stacked
    case sideBySide
}

/// One block of the page, for arrangement and reading order.
nonisolated enum PostponedEventPageBlock10868: String, Equatable, CaseIterable {
    /// The fixture words, the competitors and the About entry.
    case title
    /// The owner's match state and reason.
    case status
    /// The pregame chart.
    case anchor
    /// The owner's status facts and reschedule words.
    case timeline
    /// The originals and the All props entry.
    case originals
}

// MARK: - Page input

/// The owner's fixture title.
nonisolated struct PostponedEventPageTitle10868: Equatable {
    /// "La Liga · Sep 16, 2026": the league and the fixture's date words. Nil
    /// draws none.
    let eyebrow: String?
    /// The named competitors, in the owner's order ("Levante", "Bilbao").
    let competitors: [String]
    /// The owner's joining words ("vs").
    let joiner: String
    /// Fuller spoken title ("Levante versus Bilbao"); nil speaks the visible words.
    var spoken: String? = nil
}

/// The owner's prominent match state.
nonisolated struct PostponedEventPageStatus10868: Equatable {
    /// "Postponed".
    let state: String
    /// "Rain · match not played"; nil draws none.
    let reason: String?
}

/// Which kind of fact the owner states. Kept apart, never merged.
nonisolated enum PostponedEventPageFactKind10868: String, Equatable, CaseIterable {
    /// The match's own lifecycle ("Match postponed").
    case match
    /// An original market's closure or settlement state ("Original markets closed").
    case market
    /// A sporting result statement ("No sporting result").
    case result
}

/// One owner-supplied status fact.
nonisolated struct PostponedEventPageFact10868: Equatable {
    let id: String
    let kind: PostponedEventPageFactKind10868
    /// "Sep 16": the owner's calendar words. Context only, never a chart
    /// marker. Nil: undated.
    let date: String?
    /// "Match postponed".
    let title: String
    /// "Heavy rain · no sporting result"; nil draws none.
    let detail: String?
}

/// The owner's reschedule words.
nonisolated enum PostponedEventPageReschedule10868: Equatable {
    /// A captured new date, in the owner's words ("Rescheduled for Oct 2").
    case scheduled(String)
    /// The owner's absence words ("Rescheduled date not captured").
    case unknown(String)

    var words: String {
        switch self {
        case .scheduled(let words), .unknown(let words): words
        }
    }
}

/// The owner's status timeline.
nonisolated struct PostponedEventPageTimeline10868: Equatable {
    /// Spoken group name ("Match and market status").
    let label: String
    /// In the owner's order.
    let facts: [PostponedEventPageFact10868]
    let reschedule: PostponedEventPageReschedule10868?
}

/// The owner's one-line match words above full-size content and the modes.
nonisolated struct PostponedEventPageReaderHeader10868: Equatable {
    /// "Levante · Bilbao".
    let title: String
    /// "Postponed · no match result"; nil draws none.
    let state: String?
}

/// One source the owner names in its About, handed back exactly on open.
nonisolated struct PostponedEventPageSource10868: Equatable {
    let id: String
    /// "Levante’s official announcement".
    let label: String
    let url: URL
}

/// One section of the owner's About, verbatim.
nonisolated struct PostponedEventPageAboutSection10868: Equatable {
    /// "Match postponed · original markets closed".
    let title: String
    let paragraphs: [String]
    /// The section's source control; nil draws none.
    var source: PostponedEventPageSource10868? = nil
}

/// The owner's About, verbatim.
nonisolated struct PostponedEventPageAbout10868: Equatable {
    /// "About this match".
    let title: String
    let sections: [PostponedEventPageAboutSection10868]
}

nonisolated struct PostponedEventPageCopy10868: Equatable {
    /// Spoken name of the About control ("About this match").
    let aboutLabel: String
    /// "Opens the postponement, market and history sources"; nil: none.
    var aboutHint: String? = nil
    /// "All 3 original markets"; nil draws no entry.
    var allPropsLabel: String? = nil
}

nonisolated struct PostponedEventPageInput10868: Equatable {
    let title: PostponedEventPageTitle10868
    let status: PostponedEventPageStatus10868
    /// Nil draws no timeline.
    let timeline: PostponedEventPageTimeline10868?
    /// The owner's immutable pregame history with its held inspection,
    /// selection, readout and optional controls.
    let history: FieldHistoryInput10868
    /// The owner's plot height for the full-size chart; nil, or shorter than
    /// the page's, keeps the page's.
    var readerPlotHeight: CGFloat? = nil
    let reader: PostponedEventPageReaderHeader10868
    /// Opened by the title's About control; nil: no control.
    var about: PostponedEventPageAbout10868? = nil
    let copy: PostponedEventPageCopy10868
}

/// The owner's retained originals, for the page's chooser and the catalogue
/// and Details modes. Every field reaches the existing leaves unchanged.
struct PostponedEventPageOriginals10868 {
    /// The latest admitted originals for one scope; nil shows `emptyWords`.
    let catalogue: OriginalMarketDetails9483.Catalogue?
    /// The owner's held selection; nil holds none.
    let selection: OriginalMarketDetails9483.Selection?
    /// The held original's admitted recorded history, for the Details mode
    /// only; nil keeps its summary-only Details.
    var recorded: OriginalMarketDetails9483.RecordedHistory? = nil
    /// The owner's choice label for an exact identity; otherwise its title.
    var labels: [OriginalMarketDetails9483.Identity: String] = [:]
    /// "Original markets".
    let heading: String
    /// The catalogue's count words ("3 retained originals"); nil draws none.
    var context: String? = nil
    /// "No retained originals for this match".
    let emptyWords: String
    /// The label for an original with no readable title of its own.
    let unavailableChoice: String
    let tint: Color
}

nonisolated enum PostponedEventPageAccessibilityID10868 {
    static let page = "postponedEventPage10868.page"
    static let hero = "postponedEventPage10868.hero"
    static let title = "postponedEventPage10868.title"
    static let titleAbout = "postponedEventPage10868.title.about"
    static let status = "postponedEventPage10868.status"
    static let anchor = "postponedEventPage10868.anchor"
    static let timeline = "postponedEventPage10868.timeline"
    static let reschedule = "postponedEventPage10868.timeline.reschedule"
    static let originals = "postponedEventPage10868.originals"
    static let allProps = "postponedEventPage10868.allProps"
    static let readerHeader = "postponedEventPage10868.readerHeader"
    static let readerAbout = "postponedEventPage10868.readerHeader.about"
    static let baselines = "postponedEventPage10868.readerHeader.baselines"
    static let history = "postponedEventPage10868.history"
    static let catalogue = "postponedEventPage10868.catalogue"
    static let original = "postponedEventPage10868.original"
    static let about = "postponedEventPage10868.about"
    static func fact(_ id: String) -> String { "postponedEventPage10868.timeline.fact.\(id)" }
    static func source(_ id: String) -> String { "postponedEventPage10868.about.source.\(id)" }
}

// MARK: - Page model

/// One supplied series' earlier reading, as the chart's key shows it.
nonisolated struct PostponedEventPageBaseline10868: Equatable {
    let seriesID: String
    let name: String
    let display: FieldHistoryReadingDisplay10868
}

/// A timeline fact's marker: a shape per kind, never colour alone.
nonisolated enum PostponedEventPageFactMarker10868: Hashable {
    /// The match's lifecycle: an open ring.
    case ring
    /// A market's closure: a closed square.
    case closedSquare
    /// A sporting result statement: a bar.
    case bar
}

/// What the page arranges, resolved once per input. Pure; tested without
/// rendering.
nonisolated struct PostponedEventPageModel10868: Equatable {
    let input: PostponedEventPageInput10868

    init(_ input: PostponedEventPageInput10868) {
        self.input = input
    }

    static func readable(_ words: String?) -> String? {
        guard let words, !words.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return nil }
        return words
    }

    // MARK: Title and state

    /// The competitors with readable names, in the owner's order.
    var competitors: [String] {
        input.title.competitors.compactMap { Self.readable($0) }
    }

    /// The visible title words ("Levante vs Bilbao").
    var titleWords: String {
        let joiner = Self.readable(input.title.joiner).map { " \($0) " } ?? " "
        return competitors.joined(separator: joiner)
    }

    var spokenTitle: String {
        Self.readable(input.title.spoken) ?? titleWords
    }

    /// The owner's state, then its reason.
    var spokenStatus: String {
        [Self.readable(input.status.state), Self.readable(input.status.reason)]
            .compactMap { $0 }.joined(separator: ", ")
    }

    // MARK: Timeline

    /// The owner's facts with a readable title, in the owner's order.
    var facts: [PostponedEventPageFact10868] {
        (input.timeline?.facts ?? []).filter { Self.readable($0.title) != nil }
    }

    var reschedule: PostponedEventPageReschedule10868? {
        guard let reschedule = input.timeline?.reschedule, Self.readable(reschedule.words) != nil else { return nil }
        return reschedule
    }

    var showsTimeline: Bool { !facts.isEmpty || reschedule != nil }

    static func marker(_ kind: PostponedEventPageFactKind10868) -> PostponedEventPageFactMarker10868 {
        switch kind {
        case .match: .ring
        case .market: .closedSquare
        case .result: .bar
        }
    }

    /// Date, title, then detail, each in the owner's words.
    static func spokenFact(_ fact: PostponedEventPageFact10868) -> String {
        [readable(fact.date), readable(fact.title), readable(fact.detail)].compactMap { $0 }.joined(separator: ", ")
    }

    // MARK: History

    /// The full-size chart: the same history without its expand control, at
    /// the owner's reader height when that is taller. Every other field is the
    /// owner's, unchanged — the layout, readouts and held hour included.
    var readerHistory: FieldHistoryInput10868 {
        let history = input.history
        let height = max(history.plotHeight, input.readerPlotHeight ?? history.plotHeight)
        return FieldHistoryInput10868(
            title: history.title, caption: history.caption, series: history.series,
            selection: history.selection, domain: history.domain, ceiling: history.ceiling,
            yTicks: history.yTicks, xTicks: history.xTicks, guides: history.guides, breaks: history.breaks,
            readout: history.readout, markKey: history.markKey,
            comparisonExplanation: history.comparisonExplanation, notes: history.notes,
            summary: history.summary, plotHeight: height,
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

    /// The label of the owner's earlier reading in its readout intent.
    var baselineLabel: String {
        switch input.history.readout {
        case .singleBefore(let label): label
        case .beforeAndRecorded(let beforeLabel, _): beforeLabel
        case .beforeAndInspected(let beforeLabel, _): beforeLabel
        }
    }

    /// Each supplied series' own earlier reading, by the chart's own binding
    /// rule, in the owner's order. Never a neighbour's value, never summed.
    var baselines: [PostponedEventPageBaseline10868] {
        input.history.series.map {
            PostponedEventPageBaseline10868(seriesID: $0.id, name: $0.name,
                                            display: FieldHistoryGeometry10868.display($0.before, of: $0, in: input.history))
        }
    }

    /// The one provenance every baseline figure shares, shown once; nil when
    /// they differ or any is words — then each figure keeps its own.
    var sharedBaselineProvenance: String? {
        var shared: String?
        for baseline in baselines {
            guard case .figure(_, let provenance) = baseline.display else { return nil }
            if let shared, shared != provenance { return nil }
            shared = provenance
        }
        return shared
    }

    static func spokenBaseline(_ baseline: PostponedEventPageBaseline10868, sharedProvenance: String?) -> String {
        switch baseline.display {
        case .figure(let figure, let provenance):
            return sharedProvenance == nil ? "\(baseline.name) \(figure), \(provenance)" : "\(baseline.name) \(figure)"
        case .words(let words):
            return "\(baseline.name): \(words)"
        }
    }

    /// The compact heading carries the baselines in All props and Details only;
    /// the full-size chart already shows them in its own key.
    static func headerShowsBaselines(_ mode: PostponedEventPageMode10868) -> Bool {
        switch mode {
        case .catalogue, .original: true
        case .page, .history, .about: false
        }
    }

    // MARK: About and entries

    /// The owner's About, when it carries readable words.
    var about: PostponedEventPageAbout10868? {
        guard let about = input.about,
              Self.readable(about.title) != nil || about.sections.contains(where: Self.hasWords)
        else { return nil }
        return about
    }

    static func hasWords(_ section: PostponedEventPageAboutSection10868) -> Bool {
        readable(section.title) != nil || section.paragraphs.contains { readable($0) != nil }
    }

    func aboutAvailable(canOpen: Bool) -> Bool {
        canOpen && about != nil && Self.readable(input.copy.aboutLabel) != nil
    }

    /// The compact heading's About entry: the full-size chart only — the page
    /// has the title's own control, and the About mode is the About.
    func aboutEntry(mode: PostponedEventPageMode10868, canOpen: Bool) -> Bool {
        mode == .history && aboutAvailable(canOpen: canOpen)
    }

    /// A section's source control acts only with readable words and a callback.
    static func sourceIsLive(_ source: PostponedEventPageSource10868?, canOpen: Bool) -> Bool {
        guard let source else { return false }
        return canOpen && readable(source.label) != nil
    }

    func allPropsAvailable(canOpen: Bool) -> Bool {
        canOpen && Self.readable(input.copy.allPropsLabel) != nil
    }

    // MARK: Layout and reading order

    /// The arrangements to try, in order. Accessibility sizes and a compact
    /// width stack; a regular or unspecified width (a Mac window has no size
    /// class) tries the summary column beside the chart, then stacks — their
    /// minimum widths decide which fits.
    static func arrangements(sizeClass: UserInterfaceSizeClass?, accessibilitySize: Bool) -> [PostponedEventPageArrangement10868] {
        sizeClass != .compact && !accessibilitySize ? [.sideBySide, .stacked] : [.stacked]
    }

    /// The hero's columns in each arrangement; the originals always run full
    /// width below the hero.
    static func heroColumns(_ arrangement: PostponedEventPageArrangement10868) -> [[PostponedEventPageBlock10868]] {
        switch arrangement {
        case .stacked: [[.title, .status, .anchor, .timeline]]
        case .sideBySide: [[.title, .status, .timeline], [.anchor]]
        }
    }

    /// VoiceOver's order, the same in every arrangement.
    static let readingOrder: [PostponedEventPageBlock10868] = [.title, .status, .anchor, .timeline, .originals]

    /// Higher reads first inside the page container.
    static func sortPriority(_ block: PostponedEventPageBlock10868) -> Double {
        Double(readingOrder.count - (readingOrder.firstIndex(of: block) ?? readingOrder.count))
    }
}

// MARK: - Timeline content

/// The owner's status facts in its own words, each with its kind's marker,
/// then the reschedule words. Static; it acts on nothing.
struct PostponedEventPageTimelineView10868: View {
    let model: PostponedEventPageModel10868

    @ScaledMetric(relativeTo: .caption) private var markerSize: CGFloat = 12

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            ForEach(Array(model.facts.enumerated()), id: \.offset) { _, fact in
                HStack(alignment: .top, spacing: 12) {
                    marker(PostponedEventPageModel10868.marker(fact.kind))
                        .frame(width: markerSize, height: markerSize)
                        .padding(.top, 2)
                        .accessibilityHidden(true)
                    VStack(alignment: .leading, spacing: 4) {
                        if let date = PostponedEventPageModel10868.readable(fact.date) {
                            Text(date)
                                .font(.caption)
                                .foregroundStyle(DS.textSecondary)
                        }
                        Text(fact.title)
                            .font(.body.weight(.semibold))
                            .foregroundStyle(DS.textPrimary)
                        if let detail = PostponedEventPageModel10868.readable(fact.detail) {
                            Text(detail)
                                .font(.caption)
                                .foregroundStyle(DS.textSecondary)
                        }
                    }
                    .fixedSize(horizontal: false, vertical: true)
                    .frame(maxWidth: .infinity, alignment: .leading)
                }
                .accessibilityElement(children: .ignore)
                .accessibilityLabel(PostponedEventPageModel10868.spokenFact(fact))
                .accessibilityIdentifier(PostponedEventPageAccessibilityID10868.fact(fact.id))
            }
            if let reschedule = model.reschedule {
                Text(reschedule.words)
                    .font(.caption)
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .accessibilityIdentifier(PostponedEventPageAccessibilityID10868.reschedule)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .accessibilityElement(children: .contain)
        .accessibilityLabel(model.input.timeline?.label ?? "")
        .accessibilityIdentifier(PostponedEventPageAccessibilityID10868.timeline)
    }

    @ViewBuilder private func marker(_ marker: PostponedEventPageFactMarker10868) -> some View {
        switch marker {
        case .ring:
            Circle().strokeBorder(DS.textSecondary, lineWidth: 2)
        case .closedSquare:
            RoundedRectangle(cornerRadius: 3, style: .continuous)
                .fill(DS.border)
                .overlay(RoundedRectangle(cornerRadius: 3, style: .continuous).strokeBorder(DS.textSecondary, lineWidth: 2))
        case .bar:
            Capsule().fill(DS.textSecondary).frame(height: markerSize / 3)
        }
    }
}

// MARK: - About content

/// The owner's About in its own words. Each section's source control hands
/// the owner its exact source; with no callback the source is words.
struct PostponedEventPageAboutContent10868: View {
    let about: PostponedEventPageAbout10868
    var onSource: ((PostponedEventPageSource10868) -> Void)? = nil

    @ScaledMetric(relativeTo: .body) private var controlSize: CGFloat = 44

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            if let title = PostponedEventPageModel10868.readable(about.title) {
                Text(title)
                    .font(.headline)
                    .foregroundStyle(DS.textPrimary)
                    .accessibilityAddTraits(.isHeader)
            }
            ForEach(Array(about.sections.enumerated()), id: \.offset) { _, section in
                if PostponedEventPageModel10868.hasWords(section) {
                    VStack(alignment: .leading, spacing: 6) {
                        if let title = PostponedEventPageModel10868.readable(section.title) {
                            Text(title)
                                .font(.body.weight(.semibold))
                                .foregroundStyle(DS.textPrimary)
                                .accessibilityAddTraits(.isHeader)
                        }
                        ForEach(Array(section.paragraphs.enumerated()), id: \.offset) { _, paragraph in
                            if let words = PostponedEventPageModel10868.readable(paragraph) {
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

    /// The section's exact source for the host to open, or nothing.
    func sourceAction(_ source: PostponedEventPageSource10868?) -> (() -> Void)? {
        guard let source, PostponedEventPageModel10868.sourceIsLive(source, canOpen: onSource != nil),
              let onSource else { return nil }
        return { onSource(source) }
    }

    @ViewBuilder private func sourceControl(_ source: PostponedEventPageSource10868?) -> some View {
        if let source, let label = PostponedEventPageModel10868.readable(source.label) {
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
                .accessibilityIdentifier(PostponedEventPageAccessibilityID10868.source(source.id))
            } else {
                Text(label)
                    .font(.subheadline)
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
                    .accessibilityIdentifier(PostponedEventPageAccessibilityID10868.source(source.id))
            }
        }
    }
}

// MARK: - Page view

struct PostponedEventPagePresentation10868: View {
    typealias Model = PostponedEventPageModel10868

    let input: PostponedEventPageInput10868
    var mode: PostponedEventPageMode10868 = .page
    /// The page's chooser and the catalogue and Details modes' content; nil:
    /// none of them has any.
    var originals: PostponedEventPageOriginals10868? = nil
    /// Opens the host's container on the owner's About.
    var onAbout: (() -> Void)? = nil
    /// An About section's exact source, for the host to open.
    var onAboutSource: ((PostponedEventPageSource10868) -> Void)? = nil
    /// Opens the host's existing catalogue.
    var onAllProps: (() -> Void)? = nil
    /// A chooser or catalogue original's exact selection, for the host to
    /// hold and route.
    var onOriginalSelect: ((OriginalMarketDetails9483.Selection) -> Void)? = nil
    /// A Details history control's exact intent, for the host to route.
    var onOriginalHistory: ((OriginalMarketDetails9483.HistoryIntent) -> Void)? = nil
    /// The chart's exact action id (expand, inspect, previous, next, …).
    var onHistoryAction: ((String) -> Void)? = nil
    /// The chart's exact inspection choice id (the selected hour).
    var onHistoryInspectionChoice: ((String) -> Void)? = nil
    /// The domain position under a plot tap, for the host to resolve.
    var onHistoryPlotPosition: ((Double) -> Void)? = nil
    /// Called once just before a page, catalogue or Details action reaches
    /// its owner callback, so the owner can hold. Never called by building
    /// the view or by full-size content.
    var onInteraction: (() -> Void)? = nil

    @Environment(\.horizontalSizeClass) private var sizeClass
    @Environment(\.dynamicTypeSize) private var typeSize
    @ScaledMetric(relativeTo: .body) private var summaryMinWidth: CGFloat = 240
    @ScaledMetric(relativeTo: .body) private var summaryMaxWidth: CGFloat = 360
    @ScaledMetric(relativeTo: .body) private var anchorMinWidth: CGFloat = 420
    @ScaledMetric(relativeTo: .body) private var controlSize: CGFloat = 44

    var model: Model { Model(input) }

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
            case .history: historyMode
            case .catalogue: catalogueMode
            case .original: originalMode
            case .about: aboutMode
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    // MARK: Leaves — the actual Views, each with the host's own callbacks

    /// The page's chart passes the interaction hook first; the full-size chart
    /// keeps the exact callbacks and has no expand control.
    func historyContent(reader: Bool) -> FieldProbabilityHistoryPresentation10868 {
        let interaction = reader ? nil : onInteraction
        return FieldProbabilityHistoryPresentation10868(
            input: reader ? model.readerHistory : input.history,
            onAction: Self.held(onHistoryAction, by: interaction),
            onInspectionChoice: Self.held(onHistoryInspectionChoice, by: interaction),
            onPlotPosition: Self.held(onHistoryPlotPosition, by: interaction)
        )
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

    /// The owner's About with its exact source callback — content the host
    /// already holds, so no hook.
    func aboutContent() -> PostponedEventPageAboutContent10868? {
        model.about.map { PostponedEventPageAboutContent10868(about: $0, onSource: onAboutSource) }
    }

    func timelineContent() -> PostponedEventPageTimelineView10868? {
        model.showsTimeline ? PostponedEventPageTimelineView10868(model: model) : nil
    }

    /// The title's About, after the interaction hook.
    func openPageAbout() {
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
            originalsPanel
                .accessibilitySortPriority(Model.sortPriority(.originals))
        }
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(PostponedEventPageAccessibilityID10868.page)
    }

    /// The summary and the chart in one panel: side by side where both fit at
    /// their minimum widths, otherwise stacked.
    private var hero: some View {
        VStack(alignment: .leading, spacing: 0) {
            let arrangements = Model.arrangements(sizeClass: sizeClass, accessibilitySize: typeSize.isAccessibilitySize)
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
        .modifier(PostponedEventPageCardSurface10868())
        .accessibilityElement(children: .contain)
        .accessibilitySortPriority(Model.sortPriority(.title))
        .accessibilityIdentifier(PostponedEventPageAccessibilityID10868.hero)
    }

    private var heroStacked: some View {
        VStack(alignment: .leading, spacing: 20) {
            block(.title)
            block(.status)
            block(.anchor)
            block(.timeline)
        }
    }

    private var heroSideBySide: some View {
        HStack(alignment: .top, spacing: 32) {
            VStack(alignment: .leading, spacing: 20) {
                block(.title)
                block(.status)
                block(.timeline)
            }
            .frame(minWidth: summaryMinWidth, maxWidth: summaryMaxWidth, alignment: .topLeading)
            block(.anchor)
                .frame(minWidth: anchorMinWidth, maxWidth: .infinity, alignment: .topLeading)
                .layoutPriority(1)
        }
    }

    /// One hero block with its fixed reading priority.
    @ViewBuilder private func block(_ block: PostponedEventPageBlock10868) -> some View {
        Group {
            switch block {
            case .title: titleBlock
            case .status: statusBlock
            case .anchor: anchor
            case .timeline: timelineBlock
            case .originals: EmptyView()
            }
        }
        .accessibilitySortPriority(Model.sortPriority(block))
    }

    /// The owner's fixture words and competitors, with the About control beside them.
    private var titleBlock: some View {
        HStack(alignment: .top, spacing: 12) {
            VStack(alignment: .leading, spacing: 6) {
                if let eyebrow = Model.readable(input.title.eyebrow) {
                    Text(eyebrow)
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(DS.textSecondary)
                }
                titleText
                    .font(.title2.weight(.bold))
                    .foregroundStyle(DS.textPrimary)
                    .accessibilityAddTraits(.isHeader)
                    .accessibilityLabel(model.spokenTitle)
            }
            .fixedSize(horizontal: false, vertical: true)
            .frame(maxWidth: .infinity, alignment: .leading)
            .accessibilityElement(children: .combine)
            .accessibilityIdentifier(PostponedEventPageAccessibilityID10868.title)
            if model.aboutAvailable(canOpen: onAbout != nil) {
                aboutButton(action: openPageAbout, id: PostponedEventPageAccessibilityID10868.titleAbout)
            }
        }
    }

    /// The competitors, the owner's joining words quieter between them.
    private var titleText: Text {
        let joiner = Model.readable(input.title.joiner)
        var text = Text(verbatim: "")
        for (index, name) in model.competitors.enumerated() {
            if index > 0 {
                text = text + Text(verbatim: joiner.map { " \($0) " } ?? " ")
                    .font(.title3)
                    .foregroundStyle(DS.textSecondary)
            }
            text = text + Text(verbatim: name)
        }
        return text
    }

    /// The owner's prominent state, then its reason.
    private var statusBlock: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(input.status.state)
                .font(.title3.weight(.bold))
                .foregroundStyle(DS.textPrimary)
            if let reason = Model.readable(input.status.reason) {
                Text(reason)
                    .font(.subheadline)
                    .foregroundStyle(DS.textSecondary)
            }
        }
        .fixedSize(horizontal: false, vertical: true)
        .frame(maxWidth: .infinity, alignment: .leading)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(model.spokenStatus)
        .accessibilityIdentifier(PostponedEventPageAccessibilityID10868.status)
    }

    private var anchor: some View {
        historyContent(reader: false)
            .frame(maxWidth: .infinity, alignment: .leading)
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier(PostponedEventPageAccessibilityID10868.anchor)
    }

    @ViewBuilder private var timelineBlock: some View {
        if let timeline = timelineContent() {
            timeline
        }
    }

    /// The originals with the held original's Details, then the All props
    /// entry when the owner names one.
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
                    .accessibilityIdentifier(PostponedEventPageAccessibilityID10868.allProps)
                }
            }
            .padding(16)
            .frame(maxWidth: .infinity, alignment: .leading)
            .modifier(PostponedEventPageCardSurface10868())
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier(PostponedEventPageAccessibilityID10868.originals)
        }
    }

    // MARK: Content modes

    /// The same chart, full size, under the compact match words.
    private var historyMode: some View {
        VStack(alignment: .leading, spacing: 16) {
            compactHeader
            historyContent(reader: true)
        }
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(PostponedEventPageAccessibilityID10868.history)
    }

    /// The owner's admitted originals under the compact match words and the
    /// series' baselines.
    @ViewBuilder private var catalogueMode: some View {
        if let catalogue = catalogueContent() {
            VStack(alignment: .leading, spacing: 12) {
                compactHeader
                catalogue
            }
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier(PostponedEventPageAccessibilityID10868.catalogue)
        }
    }

    /// The held original's existing Details under the compact match words and
    /// the series' baselines.
    @ViewBuilder private var originalMode: some View {
        if let details = originalDetailsContent() {
            VStack(alignment: .leading, spacing: 12) {
                compactHeader
                details
            }
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier(PostponedEventPageAccessibilityID10868.original)
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
            .accessibilityIdentifier(PostponedEventPageAccessibilityID10868.about)
        }
    }

    /// The owner's one-line match words, the full-size chart's About entry,
    /// and in All props and Details each series' baseline.
    private var compactHeader: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(alignment: .top, spacing: 12) {
                VStack(alignment: .leading, spacing: 4) {
                    Text(input.reader.title)
                        .font(.headline)
                        .foregroundStyle(DS.textPrimary)
                        .accessibilityAddTraits(.isHeader)
                    if let state = Model.readable(input.reader.state) {
                        Text(state)
                            .font(.subheadline)
                            .foregroundStyle(DS.textSecondary)
                    }
                }
                .fixedSize(horizontal: false, vertical: true)
                .frame(maxWidth: .infinity, alignment: .leading)
                if model.aboutEntry(mode: mode, canOpen: onAbout != nil) {
                    aboutButton(action: openReaderAbout, id: PostponedEventPageAccessibilityID10868.readerAbout)
                }
            }
            if Model.headerShowsBaselines(mode) {
                baselines
            }
        }
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(PostponedEventPageAccessibilityID10868.readerHeader)
    }

    /// Each series' earlier reading as the chart's key shows it, with one
    /// shared provenance line or each figure's own.
    private var baselines: some View {
        let shared = model.sharedBaselineProvenance
        return VStack(alignment: .leading, spacing: 6) {
            Text(model.baselineLabel)
                .font(.subheadline)
                .foregroundStyle(DS.textSecondary)
            ForEach(Array(model.baselines.enumerated()), id: \.offset) { _, baseline in
                VStack(alignment: .leading, spacing: 2) {
                    switch baseline.display {
                    case .figure(let figure, let provenance):
                        Text("\(Text(verbatim: baseline.name).foregroundStyle(DS.textSecondary)) \(Text(verbatim: figure).fontWeight(.bold))")
                            .font(.subheadline)
                            .foregroundStyle(DS.textPrimary)
                        if shared == nil {
                            Text(provenance)
                                .font(.caption)
                                .foregroundStyle(DS.textSecondary)
                        }
                    case .words(let words):
                        Text("\(Text(verbatim: baseline.name).foregroundStyle(DS.textSecondary)) \(Text(verbatim: words))")
                            .font(.subheadline)
                            .foregroundStyle(DS.textPrimary)
                    }
                }
                .fixedSize(horizontal: false, vertical: true)
                .accessibilityElement(children: .ignore)
                .accessibilityLabel(Model.spokenBaseline(baseline, sharedProvenance: shared))
            }
            if let shared {
                Text(shared)
                    .font(.caption)
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .accessibilityElement(children: .contain)
        .accessibilityLabel(model.baselineLabel)
        .accessibilityIdentifier(PostponedEventPageAccessibilityID10868.baselines)
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
        .accessibilityHint(input.copy.aboutHint ?? "")
        .accessibilityIdentifier(id)
    }
}

/// The reference's white card on the page surface.
private struct PostponedEventPageCardSurface10868: ViewModifier {
    func body(content: Content) -> some View {
        content
            .background(DS.cardBg, in: RoundedRectangle(cornerRadius: 20, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 20, style: .continuous).stroke(DS.border, lineWidth: 1))
    }
}
