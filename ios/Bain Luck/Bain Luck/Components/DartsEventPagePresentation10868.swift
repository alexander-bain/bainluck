import SwiftUI

// #10868 — the darts match screen (`darts-match`): one native presentation
// composed from the accepted shared leaves plus one small dated-endpoint card.
//
// PILLARS: FORMATTING / DISCOVER / TRUTH. SHIP: a darts match page leads with
// both players' named, dated win chances and — after the final — the actual
// reported legs, then a readable earlier/later probability comparison on one
// absolute 0–100% track, with full-size history and movement readers and every
// original contract reachable.
//
// A fan sees, in this order: the match headline (the owner's eyebrow, title and
// About entry; each named player's chance for the phase — before the match the
// pre-match chance or its explicit absence, during it that reminder beside an
// admitted recorded chance, after it that reminder beside the independently
// reported final legs — and the owner's game state with its own clock); the
// final legs as tally marks out of the owner's legs played (final only); the
// two-player win probability history; on a phone, a compact probability
// context the host can pin (both players' selected or last-recorded chances
// with their own clock words, the owner's pre-match absence and, at the
// final, the legs summary, and "Chart" to the full history); the dated
// earlier/later comparison card; then the original contracts.
//
// Presentation only, from the approved `DartsMatch.tsx`, `DartsMovementCard.tsx`
// (+ `dartsMovement.ts`, `dartsMovement.css`), `DartsPinnedContext.tsx`
// (+ `dartsPinnedContext.css`) and `dartsMatch.css`, and the native visual
// references (darts-movement-card-v359, darts-reader-comparison-20261025,
// darts-probability-anchor-v379, native-darts-history-v147,
// native-darts-final-v199, darts-chart-first-v270). Their fixture loaders,
// ticker and identity checks, candle admission, shared-minute and
// first/last-minute election, `ChanceText`, `ArchiveMatchClock` and every
// clock formatter, `dartsMovementChange`, the score validator, the reader and
// story session state, "Aa Larger", sheets and dialogs are NOT ported. The
// leaves are the actual accepted Views:
//
//   • `FieldPhaseHeadlinePresentation10868` — the two named players, with the
//     owner's neutral recorded keys where no qualified start exists;
//   • `FieldProbabilityHistoryPresentation10868` — the anchor;
//   • `OriginalMarketCatalogueView9483` / `OriginalMarketDetailsView9483` —
//     the original contracts and the held original's Details;
//
// and, because no existing leaf draws an ABSOLUTE earlier/later endpoint
// comparison without changing its policy (`FieldMovementPresentation10868` is a
// signed-change bar chart), `DartsDatedEndpointsPresentation10868` below: an
// immutable dated-endpoint card on the existing semantic tokens, the history's
// own mark shapes (`FieldHistoryGeometry10868.markPath`) and the chooser's own
// resolver (`FieldChooserModel10868`).
//
// Nothing here decides a value. The phase is the owner's explicit input, never
// read from a feed status, a clock, a score or a quote. Every figure, clock,
// label, provenance, change, legs and state word is the owner's string, shown
// verbatim; every raw probability is geometry only and is placed only when it
// is finite and inside 0...1 — an unknown value is never 0 and an invalid one is
// never clamped or printed as a chance. Nothing selects a baseline, a latest,
// lowest or shared timestamp, infers an opponent, complements or normalizes two
// independently traded chances (27% and 87% stay 114%), parses a clock or a
// score, grades a contract from the match, ranks or subscribes. A selected
// minute where one player has no trade keeps that player's own absence words
// and the other player's own figure. The final legs are the owner's
// independently reported counts, drawn as tally marks only out of the owner's
// explicit legs played (never a literal, never inferred from a grade), and they
// never move with the probability selection. An original's own contract
// result stays in its Details, apart from the legs and the chances.
//
// Phases. Before: the headline's pre-match chance or its explicit absence,
// the history and the originals; no legs, no movement card and no later or
// final reading. During: the headline's own readings and game state, and the
// movement card when the owner admits its endpoints; no legs. Final: the
// pre-match reminder or absence beside the reported legs, the plot and the
// dated endpoint card with their qualifying observations, the originals.
//
// Holds. The owner may pass an interaction hook so it can hold before a page
// action lands: on the page — the headline's open and About, the history's
// actions, inspection choices and plot taps, the context's Chart, the movement
// card's open-earlier/open-later, sources and expand — and in the originals and
// Details content, the action calls the hook ONCE and then the owner's exact
// callback with its exact value. Full-size content (the readers) keeps the exact
// callbacks: its host already holds while it is open. Building or reading the
// view calls nothing. Without a callback there is no control and no hook call.
//
// Layout. A compact width or an accessibility size stacks: headline, history,
// then a LazyVStack section whose header is the compact probability context
// (pinned when the host's scroll contains it) above the movement card and the
// originals. A regular or unspecified width (a Mac window) puts the history
// beside the story column while both keep their minimum widths, otherwise it
// stacks too. The host owns the scroll, navigation, sheets, Back/Done, focus,
// the held selection and inspection, updates and subscriptions; this view
// keeps no state, runs no timer and presents nothing of its own.
//
// Host binding still owed — not available at this base: an owner that admits,
// for one match snapshot, the phase, the headline originals, pairs, finishes
// and state, the history with its runs, readout and inspection, the dated
// endpoint rows with their actions, the reported legs with their legs played
// and provenance, the reader heading, the About text and sources and the
// originals catalogue with its selection and recorded history — and maps every
// callback to its existing controls.

/// The owner's explicit phase for the whole screen.
nonisolated enum DartsEventPagePhase10868: String, Hashable, CaseIterable {
    case before
    case during
    case final
}

/// One card the page can show full size. `history` is the anchor.
nonisolated enum DartsEventPageCard10868: String, Hashable, CaseIterable {
    case history
    /// The dated earlier/later comparison.
    case movement
}

/// What the host's container is showing, chosen by the host.
nonisolated enum DartsEventPageMode10868: Equatable {
    case page
    case reader(DartsEventPageCard10868)
    /// The held original's Details.
    case original
    /// The owner's match About.
    case about
}

nonisolated enum DartsEventPageArrangement10868: Equatable {
    case stacked
    case sideBySide
}

// MARK: - Dated endpoints

/// One dated endpoint of one original, exactly as the owner formatted it from
/// one observation.
nonisolated struct DartsDatedEndpoint10868: Equatable {
    /// The owner's opaque key for this observation. Never read; identity only.
    let key: String
    /// The owner's direct label ("Earlier", "Later"). Never derived here, and
    /// never turned into a pre-match label.
    let label: String
    /// 0...1, the raw value behind `figure` — geometry only, never parsed from it.
    let probability: Double
    /// The owner's formatted figure ("27%", "0%").
    let figure: String
    /// The observation's own clock words ("Oct 12, 8:47 AM EDT").
    let clock: String
    /// "Kalshi trade · minute ending"; nil draws none.
    let provenance: String?
}

/// One side of one row: an endpoint, or the owner's words for its absence.
nonisolated enum DartsEndpointSlot10868: Equatable {
    case endpoint(DartsDatedEndpoint10868)
    /// "Not traded at 8:48 AM". Never a zero and never a neighbour's figure.
    case absent(label: String, words: String)
}

/// One original's earlier/later endpoints.
nonisolated struct DartsEndpointRow10868: Equatable {
    let ref: FieldChooserOriginalRef10868
    /// The owner's whole name, kept beside the unavailable words when the row
    /// does not resolve.
    let name: String
    let earlier: DartsEndpointSlot10868
    let later: DartsEndpointSlot10868
    /// The owner's difference words ("−26 pts"); shown only while both
    /// endpoints are drawn. Never computed here.
    let change: String?
    /// The same shape this original carries on the history.
    let shape: FieldHistoryShape10868
    let tint: Color
}

nonisolated struct DartsEndpointsCopy10868: Equatable {
    /// "Recorded win chances"; nil draws none.
    let eyebrow: String?
    /// "What changed?"
    let title: String
    /// The owner's pre-match words ("Pre-match chance unavailable"); nil
    /// draws none. Never derived from the earlier endpoint.
    let baseline: String?
    /// The track's ends and middle ("0%", "Win chance", "100%").
    let scaleLower: String
    let scaleLabel: String
    let scaleUpper: String
    /// Spoken name of the rows.
    let graphicLabel: String
    /// "Hollow: earlier trade. Filled: later trade. These dated endpoints
    /// don’t describe every moment between them."; nil draws none.
    let markKey: String?
    /// In place of a figure whose raw value cannot be placed ("Unavailable").
    let endpointUnavailable: String
    /// A row that does not resolve ("Original unavailable in this update").
    let unavailableWords: String
    /// When no row draws both endpoints ("No comparison is available at this
    /// selected minute.").
    let noComparison: String
    /// The owner's selected-minute words shown with `noComparison`; nil none.
    let selectedWords: String?
    /// "Comparison & sources" — opens the owner's About; nil draws none.
    let sourcesLabel: String?
    /// "Expand darts probability movement" — the full-size control's spoken name.
    let expandLabel: String
}

/// The owner's admitted endpoint comparison for one snapshot.
nonisolated struct DartsEndpointsInput10868: Equatable {
    /// The exact scope every reference must share.
    let scope: String
    /// The canonical catalogue, in the owner's order.
    let catalogue: [FieldChooserOriginal10868]
    /// In the owner's order. Never sorted, filtered or deduplicated here.
    let rows: [DartsEndpointRow10868]
    /// "Earlier in chart" / "Later in chart": the owner's exact intent ids.
    let openEarlier: FieldHistoryAction10868?
    let openLater: FieldHistoryAction10868?
    let copy: DartsEndpointsCopy10868
}

/// What one endpoint shows.
nonisolated enum DartsEndpointDisplay10868: Equatable {
    /// A placeable endpoint: the owner's figure, clock and provenance at its fraction.
    case figure(DartsDatedEndpoint10868, fraction: Double)
    /// The owner's absence words, or the copy's words for an unplaceable value.
    case words(label: String, words: String)

    var fraction: Double? {
        if case .figure(_, let fraction) = self { return fraction }
        return nil
    }

    var label: String {
        switch self {
        case .figure(let endpoint, _): endpoint.label
        case .words(let label, _): label
        }
    }
}

/// One row, resolved.
nonisolated struct DartsEndpointRowPlan10868: Equatable {
    let row: DartsEndpointRow10868
    let resolution: FieldChooserResolution10868
    /// Nil when the row does not resolve.
    let earlier: DartsEndpointDisplay10868?
    let later: DartsEndpointDisplay10868?

    /// The canonical whole name, or the owner's row name when unresolved.
    var name: String { resolution.original?.name ?? row.name }

    /// Both endpoints are placeable.
    var isComparison: Bool { earlier?.fraction != nil && later?.fraction != nil }
}

/// One drawn marker: hollow earlier, filled later.
nonisolated struct DartsEndpointMark10868: Equatable {
    let fraction: Double
    let hollow: Bool
}

nonisolated enum DartsEndpointGeometry10868 {
    /// A probability's place on the absolute track: itself when finite and
    /// inside 0...1. Otherwise nothing — never clamped, never 0.
    static func fraction(_ probability: Double) -> Double? {
        probability.isFinite && probability >= 0 && probability <= 1 ? probability : nil
    }

    /// The x of a fraction on a track inset at both ends so an edge marker
    /// stays whole; nil when the track cannot be drawn.
    static func x(_ fraction: Double, width: CGFloat, inset: CGFloat) -> CGFloat? {
        guard let placed = self.fraction(fraction), width.isFinite, inset.isFinite, inset >= 0,
              width > 2 * inset else { return nil }
        return inset + (width - 2 * inset) * CGFloat(placed)
    }

    /// The markers a row draws, earlier then later — placeable endpoints only.
    /// Nothing between them is drawn.
    static func marks(_ plan: DartsEndpointRowPlan10868) -> [DartsEndpointMark10868] {
        var marks: [DartsEndpointMark10868] = []
        if let earlier = plan.earlier?.fraction { marks.append(DartsEndpointMark10868(fraction: earlier, hollow: true)) }
        if let later = plan.later?.fraction { marks.append(DartsEndpointMark10868(fraction: later, hollow: false)) }
        return marks
    }

    /// The distance between both endpoints on the probability track (not a
    /// path in time), only while both are placeable.
    static func span(_ plan: DartsEndpointRowPlan10868) -> ClosedRange<Double>? {
        guard let earlier = plan.earlier?.fraction, let later = plan.later?.fraction else { return nil }
        return min(earlier, later)...max(earlier, later)
    }
}

/// The card's rules, resolved once per input.
nonisolated struct DartsEndpointsModel10868: Equatable {
    let input: DartsEndpointsInput10868
    /// The chooser's resolver: exactly one complete record in the same scope.
    let field: FieldChooserModel10868
    /// Row identities listed more than once.
    private let repeated: Set<FieldChooserOriginalRef10868>

    init(_ input: DartsEndpointsInput10868) {
        self.input = input
        // Only what the chooser's resolver reads; nothing is drawn or selected.
        field = FieldChooserModel10868(FieldChooserInput10868(
            scope: input.scope,
            intro: nil,
            featured: FieldChooserFeatured10868(title: input.copy.title, badge: nil, refs: input.rows.map(\.ref),
                                                emptyWords: input.copy.unavailableWords),
            context: nil,
            more: nil,
            browse: nil,
            catalogue: input.catalogue,
            frame: nil,
            selected: nil,
            unavailableWords: input.copy.unavailableWords,
            chooseHint: nil
        ))
        var counts: [FieldChooserOriginalRef10868: Int] = [:]
        for row in input.rows { counts[row.ref, default: 0] += 1 }
        repeated = Set(counts.filter { $0.value > 1 }.keys)
    }

    static func readable(_ words: String?) -> String? { FieldMovementModel10868.readable(words) }

    /// A placeable endpoint with a readable figure; the owner's absence words;
    /// otherwise the copy's unavailable words under the endpoint's own label.
    func display(_ slot: DartsEndpointSlot10868) -> DartsEndpointDisplay10868 {
        switch slot {
        case .endpoint(let endpoint):
            guard let fraction = DartsEndpointGeometry10868.fraction(endpoint.probability),
                  Self.readable(endpoint.figure) != nil else {
                return .words(label: endpoint.label, words: input.copy.endpointUnavailable)
            }
            return .figure(endpoint, fraction: fraction)
        case .absent(let label, let words):
            return .words(label: label, words: Self.readable(words) ?? input.copy.endpointUnavailable)
        }
    }

    /// Every row in the owner's order. A repeated or unresolved row keeps its
    /// owner name beside the unavailable words and borrows nothing; each side
    /// of a resolved row is decided on its own.
    var rows: [DartsEndpointRowPlan10868] {
        input.rows.map { row in
            let resolution: FieldChooserResolution10868 = repeated.contains(row.ref) ? .unavailable : field.resolve(row.ref)
            guard resolution.original != nil else {
                return DartsEndpointRowPlan10868(row: row, resolution: resolution, earlier: nil, later: nil)
            }
            return DartsEndpointRowPlan10868(row: row, resolution: resolution,
                                             earlier: display(row.earlier), later: display(row.later))
        }
    }

    var hasComparison: Bool { rows.contains(where: \.isComparison) }

    /// The owner's difference words, only beside two drawn endpoints.
    func change(_ plan: DartsEndpointRowPlan10868) -> String? {
        plan.isComparison ? Self.readable(plan.row.change) : nil
    }

    /// An open action hands back its exact id only while a comparison is
    /// drawn, with a callback, when available and when its id is nonblank and
    /// unique between the two; otherwise its words, or nothing.
    func openState(_ action: FieldHistoryAction10868?, hasCallback: Bool) -> FieldHistoryControlState10868 {
        guard hasComparison, let action, Self.readable(action.label) != nil else { return .hidden }
        let ids = [input.openEarlier, input.openLater].compactMap { $0?.id }
        guard hasCallback, action.isAvailable, Self.readable(action.id) != nil,
              ids.filter({ $0 == action.id }).count == 1 else { return .shownStatic }
        return .live(id: action.id)
    }

    static func spoken(_ display: DartsEndpointDisplay10868) -> String {
        switch display {
        case .figure(let endpoint, _):
            let parts: [String?] = ["\(endpoint.label) \(endpoint.figure)", endpoint.clock, endpoint.provenance]
            return parts.compactMap(readable).joined(separator: ", ")
        case .words(let label, let words):
            return "\(label): \(words)"
        }
    }

    /// A row's whole reading in the owner's words, so its track may stay decorative.
    func rowSummary(_ plan: DartsEndpointRowPlan10868) -> String {
        guard plan.resolution.original != nil, let earlier = plan.earlier, let later = plan.later else {
            let parts: [String?] = [plan.row.name, input.copy.unavailableWords]
            return parts.compactMap(Self.readable).joined(separator: ". ")
        }
        var parts = [plan.name, Self.spoken(earlier), Self.spoken(later)]
        if let change = change(plan) { parts.append(change) }
        return parts.joined(separator: ". ")
    }
}

/// The dated earlier/later comparison on one absolute 0–100% track: each
/// original's two endpoints as equally readable figures with their own
/// clocks, a hollow earlier and a filled later marker, and the owner's
/// open-earlier/open-later actions. Immutable; it keeps no state.
struct DartsDatedEndpointsPresentation10868: View {
    let input: DartsEndpointsInput10868
    /// The exact open-earlier / open-later id. Nil: no open control.
    var onOpen: ((String) -> Void)?
    /// The owner's About ("Comparison & sources"). Nil: no control.
    var onSources: (() -> Void)?
    /// Full size. Nil: no expand control (the full-size card passes none).
    var onExpand: (() -> Void)?
    let model: DartsEndpointsModel10868

    init(input: DartsEndpointsInput10868, onOpen: ((String) -> Void)? = nil, onSources: (() -> Void)? = nil,
         onExpand: (() -> Void)? = nil) {
        self.input = input
        self.onOpen = onOpen
        self.onSources = onSources
        self.onExpand = onExpand
        self.model = DartsEndpointsModel10868(input)
    }

    @Environment(\.dynamicTypeSize) private var typeSize
    @ScaledMetric(relativeTo: .body) private var controlSize: CGFloat = 44
    @ScaledMetric(relativeTo: .title2) private var figureSize: CGFloat = 22
    @ScaledMetric(relativeTo: .caption) private var markRadius: CGFloat = 5
    @ScaledMetric(relativeTo: .body) private var trackHeight: CGFloat = 40

    private var copy: DartsEndpointsCopy10868 { input.copy }

    /// The exact open action, or nil when the control is not live.
    func openAction(_ action: FieldHistoryAction10868?) -> (() -> Void)? {
        guard case .live(let id) = model.openState(action, hasCallback: onOpen != nil), let onOpen else { return nil }
        return { onOpen(id) }
    }

    /// The owner's About, only with readable words and a callback.
    var sourcesAction: (() -> Void)? {
        guard DartsEndpointsModel10868.readable(copy.sourcesLabel) != nil else { return nil }
        return onSources
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            header
            if let baseline = DartsEndpointsModel10868.readable(copy.baseline) {
                Text(baseline)
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            if !model.hasComparison {
                VStack(alignment: .leading, spacing: 4) {
                    if let selected = DartsEndpointsModel10868.readable(copy.selectedWords) {
                        Text(selected).font(.subheadline.weight(.semibold)).foregroundStyle(DS.textPrimary)
                    }
                    Text(copy.noComparison).font(.subheadline).foregroundStyle(DS.textPrimary)
                }
                .fixedSize(horizontal: false, vertical: true)
            }
            scale
            VStack(alignment: .leading, spacing: 0) {
                ForEach(Array(model.rows.enumerated()), id: \.offset) { _, plan in
                    rowView(plan)
                }
            }
            .accessibilityElement(children: .contain)
            .accessibilityLabel(copy.graphicLabel)
            actions
            if let key = DartsEndpointsModel10868.readable(copy.markKey) {
                Text(key)
                    .font(.footnote)
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            if let sourcesAction, let label = copy.sourcesLabel {
                Button(action: sourcesAction) {
                    Text(label)
                        .font(.subheadline.weight(.semibold))
                        .foregroundStyle(DS.blue)
                        .fixedSize(horizontal: false, vertical: true)
                        .frame(minHeight: controlSize, alignment: .leading)
                        .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .accessibilityIdentifier(DartsEventPageAccessibilityID10868.movementSources)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(DartsEventPageAccessibilityID10868.movement)
    }

    private var header: some View {
        HStack(alignment: .top, spacing: 12) {
            VStack(alignment: .leading, spacing: 4) {
                if let eyebrow = DartsEndpointsModel10868.readable(copy.eyebrow) {
                    Text(eyebrow).font(.caption).foregroundStyle(DS.textSecondary)
                }
                Text(copy.title)
                    .font(.title3.bold())
                    .foregroundStyle(DS.textPrimary)
                    .accessibilityAddTraits(.isHeader)
            }
            .fixedSize(horizontal: false, vertical: true)
            .frame(maxWidth: .infinity, alignment: .leading)
            if let onExpand {
                Button(action: onExpand) {
                    Image(systemName: "arrow.up.left.and.arrow.down.right")
                        .font(.body.weight(.semibold))
                        .foregroundStyle(DS.blue)
                        .frame(minWidth: controlSize, minHeight: controlSize)
                        .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .accessibilityLabel(copy.expandLabel)
                .accessibilityIdentifier(DartsEventPageAccessibilityID10868.movementExpand)
            }
        }
    }

    private var scale: some View {
        HStack {
            Text(copy.scaleLower)
            Spacer(minLength: 4)
            Text(copy.scaleLabel)
            Spacer(minLength: 4)
            Text(copy.scaleUpper)
        }
        .font(.caption)
        .foregroundStyle(DS.textSecondary)
        .accessibilityHidden(true)
    }

    private func rowView(_ plan: DartsEndpointRowPlan10868) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Divider()
            HStack(alignment: .firstTextBaseline, spacing: 8) {
                Text(plan.name)
                    .font(.headline)
                    .foregroundStyle(DS.textPrimary)
                    .fixedSize(horizontal: false, vertical: true)
                    .frame(maxWidth: .infinity, alignment: .leading)
                if let change = model.change(plan) {
                    Text(change)
                        .font(.subheadline.bold())
                        .foregroundStyle(plan.row.tint)
                        .fixedSize()
                }
            }
            if plan.resolution.original == nil {
                Text(copy.unavailableWords)
                    .font(.subheadline)
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            } else {
                track(plan)
                figures(plan)
            }
        }
        .padding(.vertical, 6)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(model.rowSummary(plan))
        .accessibilityIdentifier(DartsEventPageAccessibilityID10868.movementRow(plan.row.ref))
    }

    private func track(_ plan: DartsEndpointRowPlan10868) -> some View {
        let radius = markRadius
        let tint = plan.row.tint
        let shape = plan.row.shape
        return Canvas { context, size in
            let inset = radius * 1.3 + 1
            let y = size.height / 2
            guard let left = DartsEndpointGeometry10868.x(0, width: size.width, inset: inset),
                  let right = DartsEndpointGeometry10868.x(1, width: size.width, inset: inset) else { return }
            var line = Path()
            line.move(to: CGPoint(x: left, y: y))
            line.addLine(to: CGPoint(x: right, y: y))
            context.stroke(line, with: .color(DS.border), lineWidth: 1)
            for value in [0.0, 0.5, 1.0] {
                guard let x = DartsEndpointGeometry10868.x(value, width: size.width, inset: inset) else { continue }
                var tick = Path()
                tick.move(to: CGPoint(x: x, y: y - 6))
                tick.addLine(to: CGPoint(x: x, y: y + 6))
                context.stroke(tick, with: .color(DS.border), lineWidth: 1)
            }
            if let span = DartsEndpointGeometry10868.span(plan),
               let from = DartsEndpointGeometry10868.x(span.lowerBound, width: size.width, inset: inset),
               let to = DartsEndpointGeometry10868.x(span.upperBound, width: size.width, inset: inset) {
                var distance = Path()
                distance.move(to: CGPoint(x: from, y: y))
                distance.addLine(to: CGPoint(x: to, y: y))
                context.stroke(distance, with: .color(tint), lineWidth: 3)
            }
            for mark in DartsEndpointGeometry10868.marks(plan) {
                guard let x = DartsEndpointGeometry10868.x(mark.fraction, width: size.width, inset: inset) else { continue }
                let path = FieldHistoryGeometry10868.markPath(shape, at: CGPoint(x: x, y: y), radius: radius)
                if mark.hollow {
                    context.fill(path, with: .color(DS.cardBg))
                    context.stroke(path, with: .color(tint), lineWidth: 2)
                } else {
                    context.fill(path, with: .color(tint))
                }
            }
        }
        .frame(height: trackHeight)
        .accessibilityHidden(true)
    }

    @ViewBuilder private func figures(_ plan: DartsEndpointRowPlan10868) -> some View {
        if let earlier = plan.earlier, let later = plan.later {
            if typeSize.isAccessibilitySize {
                VStack(alignment: .leading, spacing: 10) {
                    endpointFigure(earlier)
                    endpointFigure(later)
                }
            } else {
                HStack(alignment: .top, spacing: 16) {
                    endpointFigure(earlier)
                    endpointFigure(later)
                }
            }
        }
    }

    private func endpointFigure(_ display: DartsEndpointDisplay10868) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(display.label)
                .font(.caption)
                .foregroundStyle(DS.textSecondary)
            switch display {
            case .figure(let endpoint, _):
                Text(endpoint.figure)
                    .font(.system(size: figureSize, weight: .bold))
                    .monospacedDigit()
                    .foregroundStyle(DS.textPrimary)
                    .fixedSize()
                    .accessibilityIdentifier(DartsEventPageAccessibilityID10868.endpoint(endpoint.key))
                Text(endpoint.clock)
                    .font(.caption)
                    .foregroundStyle(DS.textPrimary)
                    .fixedSize(horizontal: false, vertical: true)
                if let provenance = DartsEndpointsModel10868.readable(endpoint.provenance) {
                    Text(provenance)
                        .font(.caption2)
                        .foregroundStyle(DS.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
            case .words(_, let words):
                Text(words)
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    @ViewBuilder private var actions: some View {
        let earlier = model.openState(input.openEarlier, hasCallback: onOpen != nil)
        let later = model.openState(input.openLater, hasCallback: onOpen != nil)
        if earlier != .hidden || later != .hidden {
            Group {
                if typeSize.isAccessibilitySize {
                    VStack(alignment: .leading, spacing: 8) {
                        actionControl(input.openEarlier, state: earlier)
                        actionControl(input.openLater, state: later)
                    }
                } else {
                    HStack(spacing: 8) {
                        actionControl(input.openEarlier, state: earlier)
                        actionControl(input.openLater, state: later)
                    }
                }
            }
        }
    }

    @ViewBuilder private func actionControl(_ action: FieldHistoryAction10868?, state: FieldHistoryControlState10868) -> some View {
        if let action, state != .hidden {
            let face = Text(action.label)
                .font(.subheadline.weight(.semibold))
                .multilineTextAlignment(.center)
                .fixedSize(horizontal: false, vertical: true)
                .padding(.horizontal, 10)
                .frame(maxWidth: .infinity, minHeight: controlSize)
                .background(DS.cardBg, in: RoundedRectangle(cornerRadius: 10, style: .continuous))
                .overlay(RoundedRectangle(cornerRadius: 10, style: .continuous).stroke(DS.border, lineWidth: 1))
            if let perform = openAction(action) {
                Button(action: perform) { face.foregroundStyle(DS.blue) }
                    .buttonStyle(.plain)
                    .accessibilityLabel(action.spokenLabel ?? action.label)
                    .accessibilityIdentifier(DartsEventPageAccessibilityID10868.movementOpen(action.id))
            } else {
                face.foregroundStyle(DS.textSecondary)
                    .accessibilityLabel(action.spokenLabel ?? action.label)
                    .accessibilityIdentifier(DartsEventPageAccessibilityID10868.movementOpen(action.id))
            }
        }
    }
}

// MARK: - Final legs

/// One player's reported legs.
nonisolated struct DartsLegScore10868: Equatable {
    let ref: FieldChooserOriginalRef10868
    /// The owner's whole name, kept beside the unavailable words when the
    /// score does not resolve.
    let name: String
    /// Legs won, as reported. Never read off a grade or a probability.
    let won: Int
    /// The owner's figure ("4").
    let figure: String
    /// "Sander van Ockenburg: 4 legs won, of 4 played".
    let spoken: String
}

/// The owner's independently reported final legs.
nonisolated struct DartsLegsInput10868: Equatable {
    /// "Final legs".
    let label: String
    /// Legs played, as the owner reports it — the tally's denominator. Nil
    /// draws no marks; never a literal and never inferred from a grade.
    let played: Int?
    /// In the owner's order.
    let scores: [DartsLegScore10868]
    /// "Final · McEwan 0–4 van Ockenburg", for the compact context and readers.
    let summary: String
    /// "Reported by Darts World · Oct 12".
    let provenance: String
    /// "Filled marks: legs won, out of legs played"; nil draws none.
    let markKey: String?
}

/// One player's legs, resolved.
nonisolated struct DartsLegRow10868: Equatable {
    let score: DartsLegScore10868
    /// The canonical whole name, or the owner's score name when unresolved.
    let name: String
    let resolved: Bool
    /// The canonical accent, when resolved.
    let tint: Color?
    /// One per leg played, true for a leg won; nil draws no marks.
    let marks: [Bool]?
}

nonisolated enum DartsLegsModel10868 {
    /// One mark per leg played, filled for each leg won — only while both are
    /// the owner's consistent counts (played > 0, 0 ≤ won ≤ played).
    static func marks(won: Int, played: Int?) -> [Bool]? {
        guard let played, played > 0, won >= 0, won <= played else { return nil }
        return (0..<played).map { $0 < won }
    }

    /// Every score in the owner's order, resolved through `resolve`: an
    /// unresolved score keeps its owner name and borrows no figure or marks.
    static func rows(_ legs: DartsLegsInput10868,
                     resolve: (FieldChooserOriginalRef10868) -> FieldChooserResolution10868) -> [DartsLegRow10868] {
        var counts: [FieldChooserOriginalRef10868: Int] = [:]
        for score in legs.scores { counts[score.ref, default: 0] += 1 }
        return legs.scores.map { score in
            let resolution: FieldChooserResolution10868 = (counts[score.ref] ?? 0) > 1 ? .unavailable : resolve(score.ref)
            guard let original = resolution.original else {
                return DartsLegRow10868(score: score, name: score.name, resolved: false, tint: nil, marks: nil)
            }
            return DartsLegRow10868(score: score, name: original.name, resolved: true, tint: original.accent,
                                    marks: marks(won: score.won, played: legs.played))
        }
    }

    /// Columns: one per player, one at accessibility sizes.
    static func columns(count: Int, accessibilitySize: Bool) -> Int {
        accessibilitySize ? 1 : max(1, count)
    }
}

/// The final legs: each player's reported figure and tally marks.
struct DartsLegsPresentation10868: View {
    let legs: DartsLegsInput10868
    let rows: [DartsLegRow10868]
    /// A score that does not resolve ("Player unavailable in this update").
    let unavailableWords: String

    @Environment(\.dynamicTypeSize) private var typeSize
    @ScaledMetric(relativeTo: .title2) private var figureSize: CGFloat = 25
    @ScaledMetric(relativeTo: .caption) private var markWidth: CGFloat = 18
    @ScaledMetric(relativeTo: .caption) private var markHeight: CGFloat = 6

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            let columns = DartsLegsModel10868.columns(count: rows.count, accessibilitySize: typeSize.isAccessibilitySize)
            LazyVGrid(columns: Array(repeating: GridItem(.flexible(), spacing: 16, alignment: .topLeading), count: columns),
                      alignment: .leading, spacing: 12) {
                ForEach(Array(rows.enumerated()), id: \.offset) { _, row in
                    rowView(row)
                }
            }
            Text(legs.provenance)
                .font(.caption)
                .foregroundStyle(DS.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
            if let key = DartsEndpointsModel10868.readable(legs.markKey) {
                Text(key)
                    .font(.caption)
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(DartsEventPageAccessibilityID10868.legs)
    }

    private func rowView(_ row: DartsLegRow10868) -> some View {
        let tint = row.tint ?? DS.textPrimary
        return VStack(alignment: .leading, spacing: 6) {
            Rectangle().fill(tint).frame(height: 3).accessibilityHidden(true)
            Text(row.name)
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(DS.textPrimary)
                .fixedSize(horizontal: false, vertical: true)
            if row.resolved {
                HStack(alignment: .firstTextBaseline, spacing: 8) {
                    Text(row.score.figure)
                        .font(.system(size: figureSize, weight: .bold))
                        .monospacedDigit()
                        .foregroundStyle(DS.textPrimary)
                    Text(legs.label)
                        .font(.caption)
                        .foregroundStyle(DS.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
                if let marks = row.marks {
                    LazyVGrid(columns: [GridItem(.adaptive(minimum: markWidth), spacing: 5)], alignment: .leading, spacing: 5) {
                        ForEach(Array(marks.enumerated()), id: \.offset) { _, won in
                            RoundedRectangle(cornerRadius: markHeight / 2, style: .continuous)
                                .fill(won ? tint : DS.cardBg)
                                .overlay(RoundedRectangle(cornerRadius: markHeight / 2, style: .continuous)
                                    .stroke(won ? tint : DS.border, lineWidth: 1))
                                .frame(width: markWidth, height: markHeight)
                        }
                    }
                    .accessibilityHidden(true)
                }
            } else {
                Text(unavailableWords)
                    .font(.subheadline)
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(row.resolved ? row.score.spoken : "\(row.name). \(unavailableWords)")
        .accessibilityIdentifier(DartsEventPageAccessibilityID10868.legScore(row.score.ref))
    }
}

// MARK: - Page input

/// The owner's one-line match words above full-size content.
nonisolated struct DartsEventPageReaderHeader10868: Equatable {
    /// "McEwan vs van Ockenburg".
    let title: String
    /// "Final · McEwan 0–4 van Ockenburg · Pre-match unavailable"; nil draws none.
    let state: String?
}

/// One source the owner names in its About, handed back exactly on open.
nonisolated struct DartsEventPageSource10868: Equatable {
    let id: String
    /// "Darts World report".
    let label: String
    let url: URL
}

nonisolated struct DartsEventPageAboutSection10868: Equatable {
    let title: String
    let paragraphs: [String]
    var source: DartsEventPageSource10868? = nil
}

/// The owner's match About, verbatim.
nonisolated struct DartsEventPageAbout10868: Equatable {
    let title: String
    let sections: [DartsEventPageAboutSection10868]
}

/// The owner's words for the compact probability context.
nonisolated struct DartsContextCopy10868: Equatable {
    /// Spoken name ("Darts probability context").
    let label: String
    /// "Chart" — opens the full history through the history's own expand id.
    let chartLabel: String
    /// "Open darts win probability"; nil speaks `chartLabel`.
    let chartSpokenLabel: String?
    /// "Pre-match chance unavailable"; nil draws none.
    let baseline: String?
}

nonisolated struct DartsEventPageCopy10868: Equatable {
    /// Spoken name of the story column ("Darts match stories").
    let storiesLabel: String
    /// Shown in place of a headline whose phase is not the page's.
    let headlineUnavailable: String
    /// At the final with no reported legs ("Final legs not reported").
    let legsUnavailable: String
    /// A legs score that does not resolve ("Player unavailable in this update").
    let unavailableWords: String
    let context: DartsContextCopy10868
}

nonisolated struct DartsEventPageInput10868: Equatable {
    let phase: DartsEventPagePhase10868
    let reader: DartsEventPageReaderHeader10868
    let headline: FieldHeadlineInput10868
    /// "Refreshing · recorded history retained"; nil draws none.
    var notice: String? = nil
    let history: FieldHistoryInput10868
    /// The admitted endpoint comparison; nil draws no card.
    let movement: DartsEndpointsInput10868?
    /// The reported final legs; read at the final only.
    let legs: DartsLegsInput10868?
    let about: DartsEventPageAbout10868?
    let copy: DartsEventPageCopy10868
}

/// The owner's original contracts, for the originals section and Details mode.
struct DartsEventPageOriginals10868 {
    let catalogue: OriginalMarketDetails9483.Catalogue?
    let selection: OriginalMarketDetails9483.Selection?
    var recorded: OriginalMarketDetails9483.RecordedHistory? = nil
    var labels: [OriginalMarketDetails9483.Identity: String] = [:]
    /// "Original contracts".
    let heading: String
    /// "Both captured winner contracts"; nil draws none.
    var context: String? = nil
    let emptyWords: String
    let unavailableChoice: String
    let tint: Color
}

nonisolated enum DartsEventPageAccessibilityID10868 {
    static let page = "dartsEventPage10868.page"
    static let header = "dartsEventPage10868.header"
    static let headlineUnavailable = "dartsEventPage10868.headline.unavailable"
    static let notice = "dartsEventPage10868.notice"
    static let legs = "dartsEventPage10868.legs"
    static let legsUnavailable = "dartsEventPage10868.legs.unavailable"
    static let anchor = "dartsEventPage10868.anchor"
    static let context = "dartsEventPage10868.context"
    static let contextChart = "dartsEventPage10868.context.chart"
    static let stories = "dartsEventPage10868.stories"
    static let movement = "dartsEventPage10868.movement"
    static let movementExpand = "dartsEventPage10868.movement.expand"
    static let movementSources = "dartsEventPage10868.movement.sources"
    static let originals = "dartsEventPage10868.originals"
    static let readerHeader = "dartsEventPage10868.readerHeader"
    static let readerAbout = "dartsEventPage10868.readerHeader.about"
    static let original = "dartsEventPage10868.original"
    static let about = "dartsEventPage10868.about"
    /// Market and outcome together: separate contracts may share an outcome token.
    static func movementRow(_ ref: FieldChooserOriginalRef10868) -> String {
        "dartsEventPage10868.movement.row.\(ref.marketID).\(ref.outcomeID)"
    }
    static func movementOpen(_ id: String) -> String { "dartsEventPage10868.movement.open.\(id)" }
    static func endpoint(_ key: String) -> String { "dartsEventPage10868.movement.endpoint.\(key)" }
    static func legScore(_ ref: FieldChooserOriginalRef10868) -> String {
        "dartsEventPage10868.legs.\(ref.marketID).\(ref.outcomeID)"
    }
    static func contextReading(_ id: String) -> String { "dartsEventPage10868.context.reading.\(id)" }
    static func source(_ id: String) -> String { "dartsEventPage10868.about.source.\(id)" }
}

// MARK: - Page model

/// One player's reading in the compact context: the same slot the chart's key
/// shows for that original.
nonisolated struct DartsContextReading10868: Equatable {
    let seriesID: String
    let name: String
    let shape: FieldHistoryShape10868
    let tint: Color
    /// The history's own last readout slot for this original; nil with none.
    let slot: FieldHistoryReadoutSlot10868?
}

/// Which leaves the page mounts, resolved once per input.
nonisolated struct DartsEventPageModel10868: Equatable {
    let input: DartsEventPageInput10868

    init(_ input: DartsEventPageInput10868) {
        self.input = input
    }

    static func headlinePhase(_ phase: DartsEventPagePhase10868) -> FieldOutlookPhase10868 {
        switch phase {
        case .before: .before
        case .during: .during
        case .final: .final
        }
    }

    static func readable(_ words: String?) -> String? { FieldMovementModel10868.readable(words) }

    /// The headline at the page's own phase. Otherwise nothing.
    var headline: FieldHeadlineInput10868? {
        input.headline.phase == Self.headlinePhase(input.phase) ? input.headline : nil
    }

    /// The dated endpoint card: during and at the final, when the owner admits
    /// it. Before the match there is no later endpoint, so no card.
    var movement: DartsEndpointsInput10868? {
        input.phase == .before ? nil : input.movement
    }

    /// The reported legs, at the final only. Never before or during.
    var legs: DartsLegsInput10868? {
        input.phase == .final ? input.legs : nil
    }

    /// The owner's words at the final when no legs are reported.
    var legsUnavailable: String? {
        input.phase == .final && input.legs == nil ? Self.readable(input.copy.legsUnavailable) : nil
    }

    /// The legs, each resolved through the headline's own catalogue resolver.
    var legRows: [DartsLegRow10868] {
        guard let legs else { return [] }
        let field = FieldHeadlineModel10868(input.headline).field
        return DartsLegsModel10868.rows(legs) { field.resolve($0) }
    }

    func isMounted(_ card: DartsEventPageCard10868) -> Bool {
        switch card {
        case .history: true
        case .movement: movement != nil
        }
    }

    func readerShows(_ card: DartsEventPageCard10868) -> Bool { isMounted(card) }

    /// The anchor's full-size content: the same history in its expanded
    /// layout, without an expand control inside the reader. Every other field
    /// — selection, inspection, readout and provenance — is the owner's, unchanged.
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

    // MARK: Compact probability context

    /// The context's clock words: the inspection's own caption while the owner
    /// holds one, otherwise the history's own caption. Never computed.
    var contextCaption: String? {
        Self.readable(input.history.inspection?.caption) ?? Self.readable(input.history.caption)
    }

    /// Each original's reading — exactly the last slot the chart's key shows
    /// for it (`FieldHistoryGeometry10868.readoutSlots`), so a selected minute
    /// without a trade keeps that original's own words and its neighbour keeps
    /// its own figure.
    var contextReadings: [DartsContextReading10868] {
        input.history.series.map { series in
            DartsContextReading10868(
                seriesID: series.id, name: series.name, shape: series.shape, tint: series.tint,
                slot: FieldHistoryGeometry10868.readoutSlots(series, in: input.history).last)
        }
    }

    /// The owner's pre-match words, then the reported legs summary at the final.
    var contextFooter: [String] {
        [input.copy.context.baseline, legs?.summary].compactMap(Self.readable)
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

    /// The whole context in words: caption, each original's slot, footer.
    var contextSummary: String {
        var parts: [String] = []
        if let caption = contextCaption { parts.append(caption) }
        for reading in contextReadings {
            if let slot = reading.slot {
                parts.append("\(reading.name): \(FieldHistoryGeometry10868.spokenSlot(slot))")
            } else {
                parts.append(reading.name)
            }
        }
        parts += contextFooter
        return parts.joined(separator: ". ")
    }

    /// The context belongs to the stacked page; wide keeps the history beside
    /// the stories, so its own readouts stay in view.
    static func showsContext(_ arrangement: DartsEventPageArrangement10868) -> Bool {
        arrangement == .stacked
    }

    // MARK: About

    var about: DartsEventPageAbout10868? {
        guard let about = input.about,
              Self.readable(about.title) != nil || about.sections.contains(where: Self.hasWords)
        else { return nil }
        return about
    }

    static func hasWords(_ section: DartsEventPageAboutSection10868) -> Bool {
        readable(section.title) != nil || section.paragraphs.contains { readable($0) != nil }
    }

    func aboutAvailable(canOpen: Bool) -> Bool {
        canOpen && about != nil
    }

    /// The compact heading's About entry: full-size content only.
    func aboutEntry(mode: DartsEventPageMode10868, canOpen: Bool) -> Bool {
        guard case .reader = mode, Self.readable(input.headline.copy.aboutLabel) != nil else { return false }
        return aboutAvailable(canOpen: canOpen)
    }

    // MARK: Layout

    /// Accessibility sizes and a compact width stack; a regular or unspecified
    /// width tries the history beside the stories, then stacks.
    static func arrangements(sizeClass: UserInterfaceSizeClass?, accessibilitySize: Bool) -> [DartsEventPageArrangement10868] {
        sizeClass != .compact && !accessibilitySize ? [.sideBySide, .stacked] : [.stacked]
    }
}

// MARK: - Compact probability context

/// Both players' selected or last-recorded chances, with their own clock
/// words, the owner's pre-match words and — at the final — the legs summary,
/// and Chart to the full history. The host mounts or pins it; it reads the
/// same history input as the chart and keeps no selection of its own.
struct DartsProbabilityContextPresentation10868: View {
    let model: DartsEventPageModel10868
    /// The history's own expand action, after the page hook. Nil: no Chart control.
    var onChart: (() -> Void)?

    @Environment(\.dynamicTypeSize) private var typeSize
    @ScaledMetric(relativeTo: .body) private var controlSize: CGFloat = 44
    @ScaledMetric(relativeTo: .caption) private var markRadius: CGFloat = 4

    private var copy: DartsContextCopy10868 { model.input.copy.context }

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(alignment: .center, spacing: 8) {
                if let caption = model.contextCaption {
                    Text(caption)
                        .font(.caption)
                        .foregroundStyle(DS.textSecondary)
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
                    .accessibilityIdentifier(DartsEventPageAccessibilityID10868.contextChart)
                }
            }
            LazyVGrid(columns: Array(repeating: GridItem(.flexible(), spacing: 14, alignment: .topLeading),
                                     count: typeSize.isAccessibilitySize ? 1 : max(1, model.contextReadings.count)),
                      alignment: .leading, spacing: 8) {
                ForEach(Array(model.contextReadings.enumerated()), id: \.offset) { _, reading in
                    readingView(reading)
                }
            }
            if !model.contextFooter.isEmpty {
                Text(model.contextFooter.joined(separator: " · "))
                    .font(.caption)
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .padding(.vertical, 8)
        .frame(maxWidth: .infinity, alignment: .leading)
        .accessibilityElement(children: .contain)
        .accessibilityLabel(copy.label)
        .accessibilityIdentifier(DartsEventPageAccessibilityID10868.context)
    }

    private func readingView(_ reading: DartsContextReading10868) -> some View {
        let radius = markRadius
        return VStack(alignment: .leading, spacing: 3) {
            Rectangle().fill(reading.tint).frame(height: 2).accessibilityHidden(true)
            HStack(spacing: 6) {
                Canvas { context, size in
                    let path = FieldHistoryGeometry10868.markPath(reading.shape, at: CGPoint(x: size.width / 2, y: size.height / 2),
                                                                  radius: radius)
                    context.fill(path, with: .color(reading.tint))
                }
                .frame(width: radius * 3, height: radius * 3)
                .accessibilityHidden(true)
                Text(reading.name)
                    .font(.caption)
                    .foregroundStyle(DS.textPrimary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            switch reading.slot?.display {
            case .figure(let figure, let provenance)?:
                Text(figure)
                    .font(.headline.monospacedDigit())
                    .foregroundStyle(DS.textPrimary)
                Text(provenance)
                    .font(.caption)
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            case .words(let words)?:
                Text(words)
                    .font(.subheadline.weight(.medium))
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            case nil:
                EmptyView()
            }
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(reading.slot.map { "\(reading.name): \(FieldHistoryGeometry10868.spokenSlot($0))" } ?? reading.name)
        .accessibilityIdentifier(DartsEventPageAccessibilityID10868.contextReading(reading.seriesID))
    }
}

// MARK: - About content

/// The owner's match About in its own words. Each section's source control
/// hands the owner its exact source; with no callback the source is words.
struct DartsEventPageAboutContent10868: View {
    let about: DartsEventPageAbout10868
    var onSource: ((DartsEventPageSource10868) -> Void)? = nil

    @ScaledMetric(relativeTo: .body) private var controlSize: CGFloat = 44

    /// The section's exact source for the host to open, or nothing.
    func sourceAction(_ source: DartsEventPageSource10868?) -> (() -> Void)? {
        guard let source, DartsEventPageModel10868.readable(source.label) != nil, let onSource else { return nil }
        return { onSource(source) }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            if let title = DartsEventPageModel10868.readable(about.title) {
                Text(title)
                    .font(.headline)
                    .foregroundStyle(DS.textPrimary)
                    .accessibilityAddTraits(.isHeader)
            }
            ForEach(Array(about.sections.enumerated()), id: \.offset) { _, section in
                if DartsEventPageModel10868.hasWords(section) {
                    VStack(alignment: .leading, spacing: 6) {
                        if let title = DartsEventPageModel10868.readable(section.title) {
                            Text(title)
                                .font(.body.weight(.semibold))
                                .foregroundStyle(DS.textPrimary)
                                .accessibilityAddTraits(.isHeader)
                        }
                        ForEach(Array(section.paragraphs.enumerated()), id: \.offset) { _, paragraph in
                            if let words = DartsEventPageModel10868.readable(paragraph) {
                                Text(words).font(.body).foregroundStyle(DS.textPrimary)
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

    @ViewBuilder private func sourceControl(_ source: DartsEventPageSource10868?) -> some View {
        if let source, let label = DartsEventPageModel10868.readable(source.label) {
            if let action = sourceAction(source) {
                Button(action: action) {
                    HStack(spacing: 6) {
                        Text(label).font(.body.weight(.semibold)).fixedSize(horizontal: false, vertical: true)
                        Image(systemName: "arrow.up.right").font(.body.weight(.semibold)).accessibilityHidden(true)
                    }
                    .foregroundStyle(DS.blue)
                    .frame(minHeight: controlSize)
                    .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .accessibilityAddTraits(.isLink)
                .accessibilityIdentifier(DartsEventPageAccessibilityID10868.source(source.id))
            } else {
                Text(label)
                    .font(.subheadline)
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
                    .accessibilityIdentifier(DartsEventPageAccessibilityID10868.source(source.id))
            }
        }
    }
}

// MARK: - Page view

struct DartsEventPagePresentation10868: View {
    let input: DartsEventPageInput10868
    var mode: DartsEventPageMode10868 = .page
    /// The originals section and the Details mode; nil: neither has any.
    var originals: DartsEventPageOriginals10868? = nil
    /// Opens the host's container on the owner's About.
    var onAbout: (() -> Void)? = nil
    /// An About section's exact source, for the host to open.
    var onAboutSource: ((DartsEventPageSource10868) -> Void)? = nil
    /// A catalogue card's exact selection, for the host to hold and route.
    var onOriginalSelect: ((OriginalMarketDetails9483.Selection) -> Void)? = nil
    /// A Details history control's exact intent, for the host to route.
    var onOriginalHistory: ((OriginalMarketDetails9483.HistoryIntent) -> Void)? = nil
    /// A headline player's exact open, for the host's history.
    var onHeadlineOpen: ((FieldMovementOpen10868) -> Void)? = nil
    /// The history's exact action ids — its expand included, which the
    /// context's Chart hands back too.
    var onHistoryAction: ((String) -> Void)? = nil
    var onHistoryInspectionChoice: ((String) -> Void)? = nil
    var onHistoryPlotPosition: ((Double) -> Void)? = nil
    /// The movement card's exact open-earlier / open-later id.
    var onMovementOpen: ((String) -> Void)? = nil
    /// Opens a card full size (the movement card's expand).
    var onReaderOpen: ((DartsEventPageCard10868) -> Void)? = nil
    /// Called once just before a page, originals or Details action reaches its
    /// owner callback. Never called by building the view or by full-size content.
    var onInteraction: (() -> Void)? = nil

    @Environment(\.horizontalSizeClass) private var sizeClass
    @Environment(\.dynamicTypeSize) private var typeSize
    @ScaledMetric(relativeTo: .body) private var anchorMinWidth: CGFloat = 420
    @ScaledMetric(relativeTo: .body) private var storiesMinWidth: CGFloat = 340
    @ScaledMetric(relativeTo: .body) private var controlSize: CGFloat = 44

    var model: DartsEventPageModel10868 { DartsEventPageModel10868(input) }

    private var isReader: Bool {
        if case .reader = mode { return true }
        return false
    }

    /// A page action, after the owner's interaction hook. No host callback: no
    /// action and no hook call. No hook: the exact callback.
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

    /// The page's hook; none in full-size content, which is already held.
    private var pageHook: (() -> Void)? { isReader ? nil : onInteraction }

    var body: some View {
        Group {
            switch mode {
            case .page: page
            case .reader(let card): reader(card)
            case .original: originalMode
            case .about: aboutMode
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    // MARK: Leaves — the actual Views, each with the host's own callbacks

    /// The host's About opener; nil without readable About text or a callback.
    func aboutOpener() -> (() -> Void)? {
        guard model.aboutAvailable(canOpen: onAbout != nil), let onAbout else { return nil }
        return onAbout
    }

    /// The headline at the page's phase only; its open and About pass the page hook first.
    func headlineContent() -> FieldPhaseHeadlinePresentation10868? {
        model.headline.map {
            FieldPhaseHeadlinePresentation10868(input: $0, onAbout: Self.heldAction(aboutOpener(), by: pageHook),
                                                onOpen: Self.held(onHeadlineOpen, by: pageHook))
        }
    }

    /// The anchor passes the page hook first; the full-size history keeps the
    /// exact callbacks.
    func historyContent(reader: Bool) -> FieldProbabilityHistoryPresentation10868 {
        let interaction = reader ? nil : pageHook
        return FieldProbabilityHistoryPresentation10868(
            input: reader ? model.readerHistory : input.history,
            onAction: Self.held(onHistoryAction, by: interaction),
            onInspectionChoice: Self.held(onHistoryInspectionChoice, by: interaction),
            onPlotPosition: Self.held(onHistoryPlotPosition, by: interaction)
        )
    }

    /// The dated endpoint card. On the page its open, sources and expand pass
    /// the page hook first; full size keeps the exact callbacks and offers no
    /// expand of its own.
    func movementContent(reader: Bool) -> DartsDatedEndpointsPresentation10868? {
        let interaction = reader ? nil : pageHook
        var expand: (() -> Void)?
        if !reader, let open = onReaderOpen {
            expand = { open(.movement) }
        }
        return model.movement.map {
            DartsDatedEndpointsPresentation10868(
                input: $0,
                onOpen: Self.held(onMovementOpen, by: interaction),
                onSources: Self.heldAction(aboutOpener(), by: interaction),
                onExpand: Self.heldAction(expand, by: interaction))
        }
    }

    /// The reported final legs, at the final only.
    func legsContent() -> DartsLegsPresentation10868? {
        model.legs.map {
            DartsLegsPresentation10868(legs: $0, rows: model.legRows, unavailableWords: input.copy.unavailableWords)
        }
    }

    /// The compact probability context. Its Chart hands back the history's own
    /// expand id after the page hook.
    func contextContent() -> DartsProbabilityContextPresentation10868 {
        var chart: (() -> Void)?
        if let id = model.contextChartID(canOpen: onHistoryAction != nil), let action = onHistoryAction {
            chart = { action(id) }
        }
        return DartsProbabilityContextPresentation10868(model: model, onChart: Self.heldAction(chart, by: pageHook))
    }

    /// The existing catalogue with the owner's originals, its select after the hook.
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

    /// The owner's About with its exact source callback — already held content.
    func aboutContent() -> DartsEventPageAboutContent10868? {
        model.about.map { DartsEventPageAboutContent10868(about: $0, onSource: onAboutSource) }
    }

    /// Full-size content's About: the exact callback, no hook.
    func openReaderAbout() {
        aboutOpener()?()
    }

    // MARK: Page

    private var page: some View {
        Group {
            let arrangements = DartsEventPageModel10868.arrangements(
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
        .accessibilityIdentifier(DartsEventPageAccessibilityID10868.page)
    }

    /// Headline, history, then the stories under the compact context — a
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

    /// The headline across; the history beside the stories.
    private var widePage: some View {
        VStack(alignment: .leading, spacing: 16) {
            header
            HStack(alignment: .top, spacing: 24) {
                anchor
                    .frame(minWidth: anchorMinWidth, maxWidth: .infinity, alignment: .topLeading)
                    .layoutPriority(1)
                stories
                    .frame(minWidth: storiesMinWidth, maxWidth: .infinity, alignment: .topLeading)
            }
        }
    }

    /// The headline (or the owner's words), the notice, then the final legs.
    private var header: some View {
        VStack(alignment: .leading, spacing: 16) {
            if let headline = headlineContent() {
                headline
            } else {
                Text(input.copy.headlineUnavailable)
                    .font(.subheadline)
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .accessibilityIdentifier(DartsEventPageAccessibilityID10868.headlineUnavailable)
            }
            if let notice = DartsEventPageModel10868.readable(input.notice) {
                Text(notice)
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
                    .accessibilityIdentifier(DartsEventPageAccessibilityID10868.notice)
            }
            if let legs = legsContent() {
                legs
            } else if let words = model.legsUnavailable {
                Text(words)
                    .font(.subheadline)
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
                    .accessibilityIdentifier(DartsEventPageAccessibilityID10868.legsUnavailable)
            }
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .modifier(DartsEventPageCardSurface10868())
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(DartsEventPageAccessibilityID10868.header)
    }

    private var anchor: some View {
        historyContent(reader: false)
            .padding(16)
            .frame(maxWidth: .infinity, alignment: .leading)
            .modifier(DartsEventPageCardSurface10868())
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier(DartsEventPageAccessibilityID10868.anchor)
    }

    /// The movement card, then the original contracts.
    private var stories: some View {
        VStack(alignment: .leading, spacing: 16) {
            if let movement = movementContent(reader: false) {
                movement
                    .padding(16)
                    .modifier(DartsEventPageCardSurface10868())
            }
            if let catalogue = catalogueContent() {
                catalogue
                    .padding(16)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .modifier(DartsEventPageCardSurface10868())
                    .accessibilityElement(children: .contain)
                    .accessibilityIdentifier(DartsEventPageAccessibilityID10868.originals)
            }
        }
        .accessibilityElement(children: .contain)
        .accessibilityLabel(input.copy.storiesLabel)
        .accessibilityIdentifier(DartsEventPageAccessibilityID10868.stories)
    }

    // MARK: Full size

    /// The same leaf and input, full size, under the compact match words. A
    /// card this phase does not show has no content.
    @ViewBuilder private func reader(_ card: DartsEventPageCard10868) -> some View {
        if model.readerShows(card) {
            VStack(alignment: .leading, spacing: 16) {
                compactHeader
                switch card {
                case .history: historyContent(reader: true)
                case .movement: movementContent(reader: true)
                }
            }
        }
    }

    /// The owner's one-line match words with its result context and, in
    /// full-size content, the About entry.
    private var compactHeader: some View {
        HStack(alignment: .top, spacing: 12) {
            VStack(alignment: .leading, spacing: 4) {
                Text(input.reader.title)
                    .font(.headline)
                    .foregroundStyle(DS.textPrimary)
                    .accessibilityAddTraits(.isHeader)
                if let state = DartsEventPageModel10868.readable(input.reader.state) {
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
                .accessibilityIdentifier(DartsEventPageAccessibilityID10868.readerAbout)
            }
        }
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(DartsEventPageAccessibilityID10868.readerHeader)
    }

    @ViewBuilder private var originalMode: some View {
        if let details = originalDetailsContent() {
            details
                .accessibilityElement(children: .contain)
                .accessibilityIdentifier(DartsEventPageAccessibilityID10868.original)
        }
    }

    @ViewBuilder private var aboutMode: some View {
        if let content = aboutContent() {
            VStack(alignment: .leading, spacing: 12) {
                compactHeader
                content
            }
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier(DartsEventPageAccessibilityID10868.about)
        }
    }
}

/// The reference's white card on the page surface.
private struct DartsEventPageCardSurface10868: ViewModifier {
    func body(content: Content) -> some View {
        content
            .background(DS.cardBg, in: RoundedRectangle(cornerRadius: 18, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 18, style: .continuous).stroke(DS.border, lineWidth: 1))
    }
}
