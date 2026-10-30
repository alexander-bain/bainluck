import SwiftUI

// #10868 — the signed physical-stat split beside an existing combined-stat
// card: how each named component (Ground, Air) contributed to the combined
// actual, as compact aligned lanes on one explicit units axis, with every
// signed figure written out and the combined actual labelled on its own.
// D'Andre Swift 84 ground, 4 air, 88 combined; Saquon Barkley 82 ground,
// −2 air, 80 combined — the negative contribution keeps its sign and is drawn
// backward along the axis, never as positive yardage and never clamped to 0.
//
// Presentation only, extracted from the approved design
// (totals-final-forecast-binding-20261024 `CombinedYardsCard` parts strip and
// ADDITIVE-STAT-SPLIT-NEXT-SOURCE.md). The chances stay with the existing
// milestone card and its chart (`NFLMilestoneCard9483`,
// `PlayerMilestoneComparison9483`); this leaf shows no probability, derives
// none, and its lengths are units of the stat, not chances.
//
// Every figure, unit, provenance line, tick label, component name and endpoint
// arrives resolved by the owner and is shown verbatim. This layer never joins
// records, sums or checks components against the total, adds or removes a
// sign, formats or rounds a number, reads a clock, elects a default, grades a
// contract or decides whether a decomposition qualifies. It places only
// finite owner endpoints inside a valid owner domain: anything else keeps its
// name and its words and draws no bar. A missing component is never 0; a real
// 0 draws a visible zero mark.
//
// Phase gate: before play nothing physical is shown, whatever the owner
// carried. During play only an independently supplied actual-so-far is shown;
// after the final only a final actual. A reading of the other kind is not
// relabelled — the leaf says the actual for this phase is unavailable.
//
// Stateless: no selection, focus, scroll, animation, sheet or subscription.
// With no Details callback, or an absent or empty owner id, no button is
// offered and no tap is asked for; the leaf never synthesizes an id or
// navigates.
//
// Layout is decided by width at every text size: name, track and figure share
// one row per lane — every track on one units axis — only while each name and
// figure fits on one line beside a track with usable room. Otherwise, and
// always at accessibility sizes, each lane stacks its words above a
// full-width track. Words wrap; nothing is shrunk, capped or truncated.
//
// Host binding still owed — not available at this base (see
// ADDITIVE-STAT-SPLIT-NATIVE-BINDING-MAP.md). `GameMarketPlayerProp.actual` can
// hold a signed value but carries no combined-to-component association and no
// stat clock; `AfterPlayerProps` final counts are nonnegative integers and
// cannot carry −2. An owner must admit the subject, the combined stat and its
// component membership, the phase and finality, and supply each figure with
// its unit and provenance, the endpoints on the shared axis, and the domain.

/// Where the owner's page is in the game, decided by the owner.
nonisolated enum AdditiveStatSplitPhase10868: Equatable {
    case before, during, final
}

/// One owner-formatted figure. `text` carries its own sign ("−2", "4" or
/// "+4"); the leaf shows it as given.
nonisolated struct AdditiveStatSplitFigure10868: Equatable {
    let text: String
    /// The owner's unit words for this figure ("yards").
    let unit: String
    /// The owner's source words for this figure, or nil to show none.
    let provenance: String?
}

/// A component's owner-supplied endpoints on the shared units axis, in the
/// direction it contributed: Barkley's Air runs 82 → 80. Geometry only — the
/// leaf never checks it against the figure or against other components.
nonisolated struct AdditiveStatSplitSpan10868: Equatable {
    let start: Double
    let end: Double
}

/// Which of the host's two tints draws a component, chosen by the owner per
/// stat so the same stat keeps its identity wherever it appears.
nonisolated enum AdditiveStatSplitEmphasis10868: Equatable {
    case primary, secondary
}

nonisolated enum AdditiveStatSplitComponentReading10868: Equatable {
    /// A figure, and its endpoints when the owner can place it (nil draws no bar).
    case value(AdditiveStatSplitFigure10868, span: AdditiveStatSplitSpan10868?)
    /// The owner's own absence words for this component.
    case unavailable(String)
}

nonisolated struct AdditiveStatSplitComponent10868: Equatable, Identifiable {
    /// The owner's stable id for this component's stat.
    let id: String
    let name: String
    let emphasis: AdditiveStatSplitEmphasis10868
    let reading: AdditiveStatSplitComponentReading10868
}

nonisolated enum AdditiveStatSplitTotal10868: Equatable {
    case value(AdditiveStatSplitFigure10868)
    case unavailable(String)
}

/// The owner's decision on the split: qualified components in the owner's
/// order, or its words for why there is none.
nonisolated enum AdditiveStatSplitDecomposition10868: Equatable {
    case qualified([AdditiveStatSplitComponent10868])
    case unavailable(String)
}

nonisolated struct AdditiveStatSplitReading10868: Equatable {
    let total: AdditiveStatSplitTotal10868
    let split: AdditiveStatSplitDecomposition10868
}

/// What the owner has for this subject, and of which kind.
nonisolated enum AdditiveStatSplitActual10868: Equatable {
    case final(AdditiveStatSplitReading10868)
    case soFar(AdditiveStatSplitReading10868)
    /// The owner's words for having no actual at all.
    case absent(String)
}

nonisolated struct AdditiveStatSplitTick10868: Equatable {
    let value: Double
    let text: String
}

/// The shared units axis. Valid only with finite bounds, `lower < upper` and a
/// finite extent between them.
nonisolated struct AdditiveStatSplitAxis10868: Equatable {
    let lower: Double
    let upper: Double
    /// In the owner's order; ticks the domain cannot place are omitted.
    let ticks: [AdditiveStatSplitTick10868]
    /// The owner's unit words for the axis ("yards").
    let unit: String
}

nonisolated struct AdditiveStatSplitInput10868: Equatable {
    /// The owner's already-admitted subject, in its words ("Saquon Barkley").
    let subject: String
    /// The owner's label for the combined actual ("Combined").
    let totalName: String
    let phase: AdditiveStatSplitPhase10868
    let actual: AdditiveStatSplitActual10868
    let axis: AdditiveStatSplitAxis10868
    /// The exact original the owner opens from Details, opaque. Nil offers none.
    let detailsID: String?
}

/// Where a component is drawn, as fractions of the axis.
nonisolated enum AdditiveStatSplitMark10868: Equatable {
    /// From `from` to `to` in the owner's direction; `to < from` runs backward.
    case bar(from: Double, to: Double)
    /// Equal endpoints: a real zero, drawn as a visible mark.
    case zero(at: Double)
    /// Nothing the axis can place. No bar is invented.
    case none

    enum Direction: Equatable { case forward, backward }

    var direction: Direction? {
        guard case .bar(let from, let to) = self else { return nil }
        return to < from ? .backward : .forward
    }
}

nonisolated struct AdditiveStatSplitPlacedTick10868: Equatable {
    let fraction: Double
    let text: String
}

/// How the lanes are arranged at the reader's width and text size.
nonisolated enum AdditiveStatSplitLayout10868: Equatable {
    /// Name, track and figure on one row per lane; the tracks share one column.
    /// Only while every name and figure fits on one line beside a track of at
    /// least ``AdditiveStatSplitGeometry10868/minimumTrackWidth``.
    case aligned
    /// Name and figure wrap above a full-width track: whenever the aligned row
    /// would not fit, and always at accessibility sizes.
    case stacked
}

nonisolated enum AdditiveStatSplitGeometry10868 {
    /// Room at each end of a track so a mark at the domain edge, and its
    /// direction cue, are never clipped. Tracks and axis use the same inset.
    static let inset: CGFloat = 6
    static let zeroMarkWidth: CGFloat = 2
    static let minimumBarWidth: CGFloat = 2
    static let arrowLength: CGFloat = 5
    /// The least room between the insets an aligned track may have. The
    /// width fit counts it, so a crowded row stacks instead of collapsing its
    /// track to nothing.
    static let minimumUsableTrackWidth: CGFloat = 64
    static var minimumTrackWidth: CGFloat { minimumUsableTrackWidth + 2 * inset }

    /// Finite bounds alone are not enough: −1e308…1e308 has an infinite
    /// extent, which would put every value at 0.
    static func isValid(_ axis: AdditiveStatSplitAxis10868) -> Bool {
        let extent = axis.upper - axis.lower
        return axis.lower.isFinite && axis.upper.isFinite && axis.lower < axis.upper && extent.isFinite && extent > 0
    }

    /// A value's place on the axis. Nil for a non-finite value, a value outside
    /// the domain, an invalid domain or a non-finite result — omitted, never
    /// clamped.
    static func fraction(_ value: Double, on axis: AdditiveStatSplitAxis10868) -> Double? {
        guard isValid(axis), value.isFinite, value >= axis.lower, value <= axis.upper else { return nil }
        let result = (value - axis.lower) / (axis.upper - axis.lower)
        guard result.isFinite, result >= 0, result <= 1 else { return nil }
        return result
    }

    /// A zero mark only for the owner's equal endpoints. Unequal endpoints the
    /// arithmetic cannot tell apart are a span it cannot draw, so no mark —
    /// never a synthetic zero.
    static func mark(_ span: AdditiveStatSplitSpan10868?, on axis: AdditiveStatSplitAxis10868) -> AdditiveStatSplitMark10868 {
        guard let span, let from = fraction(span.start, on: axis), let to = fraction(span.end, on: axis) else { return .none }
        if span.start == span.end { return .zero(at: from) }
        return from == to ? .none : .bar(from: from, to: to)
    }

    static func ticks(_ axis: AdditiveStatSplitAxis10868) -> [AdditiveStatSplitPlacedTick10868] {
        axis.ticks.compactMap { tick in
            fraction(tick.value, on: axis).map { AdditiveStatSplitPlacedTick10868(fraction: $0, text: tick.text) }
        }
    }

    /// The x of a fraction along a track of this width, inside the insets.
    static func x(_ fraction: Double, width: CGFloat) -> CGFloat? {
        let usable = width - 2 * inset
        guard usable.isFinite, usable > 0, fraction.isFinite, fraction >= 0, fraction <= 1 else { return nil }
        return inset + usable * CGFloat(fraction)
    }

    /// The row each axis label goes on. Labels are centred on their tick and
    /// kept inside the axis; a label that would come within `gap` of one
    /// already on a row moves to the next row rather than shrinking or leaving
    /// its tick. Every label is placed; ties keep the owner's order.
    static func labelRows(centers: [CGFloat], widths: [CGFloat], extent: CGFloat, gap: CGFloat = 4) -> [Int] {
        guard centers.count == widths.count else { return [] }
        let extent = extent.isFinite ? max(0, extent) : 0
        let order = centers.indices.sorted { a, b in
            let ca = centers[a].isFinite ? centers[a] : 0
            let cb = centers[b].isFinite ? centers[b] : 0
            return ca == cb ? a < b : ca < cb
        }
        var rowEnds: [CGFloat] = []
        var rows = [Int](repeating: 0, count: centers.count)
        for i in order {
            let start = labelStart(center: centers[i], width: widths[i], extent: extent)
            let end = start + (widths[i].isFinite ? max(0, widths[i]) : 0)
            if let row = rowEnds.firstIndex(where: { start >= $0 + gap }) {
                rows[i] = row
                rowEnds[row] = end
            } else {
                rows[i] = rowEnds.count
                rowEnds.append(end)
            }
        }
        return rows
    }

    /// The width an axis label is measured at: the axis itself, so a label
    /// wider than the plot wraps inside it rather than running past the edge.
    /// Nil (the label's own width) when there is no usable axis width.
    static func labelWrapWidth(extent: CGFloat) -> CGFloat? {
        extent.isFinite && extent > 0 ? extent : nil
    }

    /// A label's leading edge: centred on its tick, kept inside the axis; a
    /// label as wide as the axis starts at 0.
    static func labelStart(center: CGFloat, width: CGFloat, extent: CGFloat) -> CGFloat {
        let width = width.isFinite ? max(0, width) : 0
        let center = center.isFinite ? center : 0
        guard width < extent else { return 0 }
        return min(max(0, center - width / 2), extent - width)
    }
}

/// The missing physical-stat portion of a combined-stat card.
struct AdditiveStatSplitPresentation10868: View {
    let input: AdditiveStatSplitInput10868
    /// The host's existing tints for the subject (team series colours).
    let primaryTint: Color
    let secondaryTint: Color
    var onDetails: ((String) -> Void)? = nil

    @Environment(\.dynamicTypeSize) private var typeSize
    @ScaledMetric(relativeTo: .title) private var figureSize: CGFloat = 28
    @ScaledMetric(relativeTo: .body) private var trackHeight: CGFloat = 12

    var body: some View {
        let readout = Self.readout(input)
        VStack(alignment: .leading, spacing: 10) {
            content(readout)
                .accessibilityElement(children: .ignore)
                .accessibilityLabel(readout.spoken)
                .accessibilityIdentifier("additive-stat-split")
            if let action = Self.detailsAction(id: input.detailsID, onDetails: onDetails) {
                Button(action: action) {
                    HStack(spacing: 4) {
                        Text(Readout.detailsText)
                        Image(systemName: "chevron.right")
                            .font(.caption.weight(.semibold))
                            .accessibilityHidden(true)
                    }
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(primaryTint)
                    .frame(minHeight: 44)
                }
                .buttonStyle(.plain)
                .accessibilityLabel(readout.detailsSpoken)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    @ViewBuilder private func content(_ readout: Readout) -> some View {
        switch readout.status {
        case .hidden:
            words(Readout.hiddenText)
        case .words(let text):
            words(text)
        case .shown:
            VStack(alignment: .leading, spacing: 10) {
                if let total = readout.total { totalBlock(total, caption: readout.caption ?? "") }
                if let splitWords = readout.splitWords { words(splitWords) }
                if !readout.lanes.isEmpty { lanes(readout) }
            }
        }
    }

    private func words(_ text: String) -> some View {
        Text(text)
            .font(.subheadline)
            .foregroundStyle(.secondary)
            .fixedSize(horizontal: false, vertical: true)
    }

    private func totalBlock(_ total: Readout.Total, caption: String) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text("\(total.name) · \(caption)")
                .font(.subheadline.weight(.semibold))
                .fixedSize(horizontal: false, vertical: true)
            Text(total.text)
                .font(total.isFigure ? .system(size: figureSize, weight: .bold).monospacedDigit() : .headline)
                .foregroundStyle(total.isFigure ? Color.primary : Color.secondary)
                .fixedSize(horizontal: false, vertical: true)
            if let provenance = total.provenance { provenanceText(provenance) }
        }
    }

    @ViewBuilder private func lanes(_ readout: Readout) -> some View {
        let candidates = Self.layoutCandidates(isAccessibilitySize: typeSize.isAccessibilitySize)
        if candidates.contains(.aligned) {
            // The first that fits the offered width: the aligned grid's ideal
            // width is every name and figure on one line plus a track of at
            // least `minimumTrackWidth`, so it never fits by collapsing its track.
            ViewThatFits(in: .horizontal) {
                alignedLanes(readout)
                stackedLanes(readout)
            }
        } else {
            stackedLanes(readout)
        }
        if let axisWords = readout.axisWords {
            Text(axisWords)
                .font(.caption)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
        }
    }

    /// One row per lane; every track in one column, so one shared axis. A
    /// provenance line wraps under its track and figure without widening them.
    private func alignedLanes(_ readout: Readout) -> some View {
        Grid(alignment: .leading, horizontalSpacing: 10, verticalSpacing: 6) {
            ForEach(readout.lanes) { lane in
                GridRow {
                    Text(lane.name)
                        .font(.subheadline.weight(.semibold))
                        .foregroundStyle(tint(lane.emphasis))
                        .fixedSize()
                    track(lane.mark, emphasis: lane.emphasis,
                          minimumWidth: AdditiveStatSplitGeometry10868.minimumTrackWidth)
                    figure(lane).fixedSize()
                }
                if let provenance = lane.provenance {
                    GridRow {
                        Color.clear.gridCellUnsizedAxes([.horizontal, .vertical])
                        provenanceText(provenance)
                            .gridCellColumns(2)
                            .gridCellUnsizedAxes(.horizontal)
                    }
                }
            }
            if let axis = readout.axis {
                GridRow {
                    Color.clear.gridCellUnsizedAxes([.horizontal, .vertical])
                    axisView(axis)
                    Color.clear.gridCellUnsizedAxes([.horizontal, .vertical])
                }
            }
        }
    }

    /// Words above full-width tracks, which still share one axis: same width,
    /// same insets.
    private func stackedLanes(_ readout: Readout) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            ForEach(readout.lanes) { lane in
                VStack(alignment: .leading, spacing: 4) {
                    Text(lane.name)
                        .font(.subheadline.weight(.semibold))
                        .foregroundStyle(tint(lane.emphasis))
                        .fixedSize(horizontal: false, vertical: true)
                    figure(lane).fixedSize(horizontal: false, vertical: true)
                    if let provenance = lane.provenance { provenanceText(provenance) }
                    track(lane.mark, emphasis: lane.emphasis, minimumWidth: 0)
                }
            }
            if let axis = readout.axis { axisView(axis) }
        }
    }

    private func figure(_ lane: Readout.Lane) -> some View {
        Text(lane.text)
            .font(lane.isFigure ? .headline.monospacedDigit() : .subheadline)
            .foregroundStyle(lane.isFigure ? Color.primary : Color.secondary)
    }

    private func provenanceText(_ text: String) -> some View {
        Text(text)
            .font(.caption)
            .foregroundStyle(.secondary)
            .fixedSize(horizontal: false, vertical: true)
    }

    private func tint(_ emphasis: AdditiveStatSplitEmphasis10868) -> Color {
        emphasis == .primary ? primaryTint : secondaryTint
    }

    /// One lane's track on the shared axis. A bar ends in a cue pointing the
    /// way the component ran; a backward bar is outlined, not filled, so a
    /// negative contribution never reads as positive yardage. `minimumWidth`
    /// is also the track's ideal width, which is what the width fit measures.
    private func track(_ mark: AdditiveStatSplitMark10868, emphasis: AdditiveStatSplitEmphasis10868,
                       minimumWidth: CGFloat) -> some View {
        let color = tint(emphasis)
        return GeometryReader { proxy in
            let width = proxy.size.width, height = proxy.size.height
            ZStack(alignment: .topLeading) {
                Capsule()
                    .fill(Color.secondary.opacity(0.08))
                switch mark {
                case .bar(let from, let to):
                    if let a = AdditiveStatSplitGeometry10868.x(from, width: width),
                       let b = AdditiveStatSplitGeometry10868.x(to, width: width) {
                        let lo = min(a, b), barWidth = max(AdditiveStatSplitGeometry10868.minimumBarWidth, abs(b - a))
                        let backward = mark.direction == .backward
                        Rectangle()
                            .fill(backward ? color.opacity(0.2) : color)
                            .overlay { if backward { Rectangle().strokeBorder(color, lineWidth: 1.5) } }
                            .frame(width: barWidth, height: height)
                            .offset(x: lo)
                        Path { path in
                            let reach = backward ? -AdditiveStatSplitGeometry10868.arrowLength : AdditiveStatSplitGeometry10868.arrowLength
                            path.move(to: CGPoint(x: b, y: 0))
                            path.addLine(to: CGPoint(x: b + reach, y: height / 2))
                            path.addLine(to: CGPoint(x: b, y: height))
                            path.closeSubpath()
                        }
                        .fill(color)
                    }
                case .zero(let at):
                    if let x = AdditiveStatSplitGeometry10868.x(at, width: width) {
                        Rectangle()
                            .fill(Color.primary)
                            .frame(width: AdditiveStatSplitGeometry10868.zeroMarkWidth, height: height + 4)
                            .offset(x: x - AdditiveStatSplitGeometry10868.zeroMarkWidth / 2, y: -2)
                    }
                case .none:
                    EmptyView()
                }
            }
        }
        .frame(height: trackHeight)
        .frame(minWidth: minimumWidth, idealWidth: minimumWidth, maxWidth: .infinity)
        .accessibilityHidden(true)
    }

    private func axisView(_ ticks: [AdditiveStatSplitPlacedTick10868]) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            GeometryReader { proxy in
                Path { path in
                    for tick in ticks {
                        guard let x = AdditiveStatSplitGeometry10868.x(tick.fraction, width: proxy.size.width) else { continue }
                        path.move(to: CGPoint(x: x, y: 0))
                        path.addLine(to: CGPoint(x: x, y: proxy.size.height))
                    }
                }
                .stroke(Color.secondary.opacity(0.4), lineWidth: 1)
            }
            .frame(height: 4)
            AdditiveStatSplitAxisLabels10868(fractions: ticks.map(\.fraction)) {
                ForEach(Array(ticks.enumerated()), id: \.offset) { _, tick in
                    Text(tick.text)
                        .font(.caption.monospacedDigit())
                        .foregroundStyle(.secondary)
                        .multilineTextAlignment(.center)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
        }
        .frame(maxWidth: .infinity)
        .accessibilityHidden(true)
    }

    /// The layouts tried, in order, against the offered width; the first that
    /// fits is drawn and the last always is. Accessibility sizes always stack.
    static func layoutCandidates(isAccessibilitySize: Bool) -> [AdditiveStatSplitLayout10868] {
        isAccessibilitySize ? [.stacked] : [.aligned, .stacked]
    }

    /// Details, only with both the owner's exact id and its callback. An empty
    /// id names no original and is treated exactly as an absent one; any
    /// nonempty id is passed through untouched.
    static func detailsAction(id: String?, onDetails: ((String) -> Void)?) -> (() -> Void)? {
        guard let id, !id.isEmpty, let onDetails else { return nil }
        return { onDetails(id) }
    }
}

/// Axis labels centred under their ticks, using the tracks' insets, on as many
/// rows as they need (``AdditiveStatSplitGeometry10868/labelRows``). Each label
/// is measured at the axis width, so one wider than the plot wraps inside it
/// and stays under its tick.
struct AdditiveStatSplitAxisLabels10868: Layout {
    var fractions: [Double]
    var rowSpacing: CGFloat = 2

    private func plan(width: CGFloat, subviews: Subviews) -> (starts: [CGFloat], rows: [Int], sizes: [CGSize]) {
        let count = min(fractions.count, subviews.count)
        let measure = AdditiveStatSplitGeometry10868.labelWrapWidth(extent: width)
            .map { ProposedViewSize(width: $0, height: nil) } ?? .unspecified
        let sizes = subviews.prefix(count).map { $0.sizeThatFits(measure) }
        let centers = fractions.prefix(count).map { AdditiveStatSplitGeometry10868.x($0, width: width) ?? 0 }
        let widths = sizes.map(\.width)
        let starts = zip(centers, widths).map { AdditiveStatSplitGeometry10868.labelStart(center: $0, width: $1, extent: width) }
        return (starts, AdditiveStatSplitGeometry10868.labelRows(centers: centers, widths: widths, extent: width), sizes)
    }

    private func rowHeight(_ sizes: [CGSize]) -> CGFloat { sizes.map(\.height).max() ?? 0 }

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let width = proposal.width ?? 0
        let plan = plan(width: width, subviews: subviews)
        guard let last = plan.rows.max() else { return CGSize(width: width, height: 0) }
        let rows = CGFloat(last + 1)
        return CGSize(width: width, height: rows * rowHeight(plan.sizes) + (rows - 1) * rowSpacing)
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        let plan = plan(width: bounds.width, subviews: subviews)
        let height = rowHeight(plan.sizes)
        for i in plan.rows.indices {
            subviews[i].place(at: CGPoint(x: bounds.minX + plan.starts[i],
                                          y: bounds.minY + CGFloat(plan.rows[i]) * (height + rowSpacing)),
                              proposal: ProposedViewSize(plan.sizes[i]))
        }
    }
}

// MARK: - What the split says

extension AdditiveStatSplitPresentation10868 {
    /// The split as words and marks, decided once from the owner's input and
    /// the phase gate.
    struct Readout: Equatable {
        enum Status: Equatable {
            /// Before play: nothing physical, whatever the owner carried.
            case hidden
            /// No actual of this phase's kind: the owner's words, or the
            /// leaf's when a reading of the other kind was carried.
            case words(String)
            case shown
        }

        struct Total: Equatable {
            let name: String
            let text: String
            let isFigure: Bool
            let provenance: String?
            let spoken: String
        }

        struct Lane: Equatable, Identifiable {
            let id: String
            let name: String
            let text: String
            let isFigure: Bool
            let provenance: String?
            let emphasis: AdditiveStatSplitEmphasis10868
            let mark: AdditiveStatSplitMark10868
            let spoken: String
        }

        let subject: String
        let status: Status
        /// "Final actual" or "Actual so far", when shown.
        let caption: String?
        let total: Total?
        /// In the owner's order.
        let lanes: [Lane]
        /// Why there are no lanes, when the split is not shown.
        let splitWords: String?
        /// The placeable ticks, only when the domain is valid and something is drawn.
        let axis: [AdditiveStatSplitPlacedTick10868]?
        let axisWords: String?
        let spoken: String

        static let hiddenText = "Actual split hidden before play"
        static let finalCaption = "Final actual"
        static let soFarCaption = "Actual so far"
        static let finalUnavailableText = "Final actual unavailable"
        static let soFarUnavailableText = "Actual so far unavailable"
        static let emptySplitText = "Split unavailable"
        static let detailsText = "Details"

        static func axisText(unit: String) -> String { "Lengths show \(unit), not chances" }

        var detailsSpoken: String { "\(Self.detailsText), \(subject)" }
    }

    static func readout(_ input: AdditiveStatSplitInput10868) -> Readout {
        func words(_ text: String) -> Readout {
            Readout(subject: input.subject, status: .words(text), caption: nil, total: nil, lanes: [],
                    splitWords: nil, axis: nil, axisWords: nil, spoken: "\(input.subject), \(text)")
        }
        switch (input.phase, input.actual) {
        case (.before, _):
            return Readout(subject: input.subject, status: .hidden, caption: nil, total: nil, lanes: [],
                           splitWords: nil, axis: nil, axisWords: nil,
                           spoken: "\(input.subject), \(Readout.hiddenText.lowercased())")
        case (.during, .soFar(let reading)):
            return shown(input, reading, caption: Readout.soFarCaption)
        case (.final, .final(let reading)):
            return shown(input, reading, caption: Readout.finalCaption)
        case (_, .absent(let text)):
            return words(text)
        case (.during, .final):
            return words(Readout.soFarUnavailableText)
        case (.final, .soFar):
            return words(Readout.finalUnavailableText)
        }
    }

    private static func shown(_ input: AdditiveStatSplitInput10868, _ reading: AdditiveStatSplitReading10868,
                              caption: String) -> Readout {
        let total: Readout.Total
        switch reading.total {
        case .value(let figure):
            let text = "\(figure.text) \(figure.unit)"
            total = Readout.Total(name: input.totalName, text: text, isFigure: true, provenance: figure.provenance,
                                  spoken: spoken(input.totalName, text, figure.provenance))
        case .unavailable(let text):
            total = Readout.Total(name: input.totalName, text: text, isFigure: false, provenance: nil,
                                  spoken: "\(input.totalName), \(text)")
        }

        var lanes: [Readout.Lane] = []
        var splitWords: String?
        switch reading.split {
        case .qualified(let components) where components.isEmpty:
            splitWords = Readout.emptySplitText
        case .qualified(let components):
            lanes = components.map { component in
                switch component.reading {
                case .value(let figure, let span):
                    let text = "\(figure.text) \(figure.unit)"
                    return Readout.Lane(id: component.id, name: component.name, text: text, isFigure: true,
                                        provenance: figure.provenance, emphasis: component.emphasis,
                                        mark: AdditiveStatSplitGeometry10868.mark(span, on: input.axis),
                                        spoken: spoken(component.name, text, figure.provenance))
                case .unavailable(let text):
                    return Readout.Lane(id: component.id, name: component.name, text: text, isFigure: false,
                                        provenance: nil, emphasis: component.emphasis, mark: .none,
                                        spoken: "\(component.name), \(text)")
                }
            }
        case .unavailable(let text):
            splitWords = text
        }

        let drawsSomething = lanes.contains { $0.mark != .none }
        let axis = drawsSomething ? AdditiveStatSplitGeometry10868.ticks(input.axis) : nil
        let axisWords = drawsSomething ? Readout.axisText(unit: input.axis.unit) : nil

        let parts = ["\(input.subject), \(caption.lowercased())", total.spoken]
            + (splitWords.map { [$0] } ?? [])
            + lanes.map(\.spoken)
            + (axisWords.map { [$0] } ?? [])
        return Readout(subject: input.subject, status: .shown, caption: caption, total: total, lanes: lanes,
                       splitWords: splitWords, axis: axis, axisWords: axisWords, spoken: parts.joined(separator: ". "))
    }

    private static func spoken(_ name: String, _ text: String, _ provenance: String?) -> String {
        provenance.map { "\(name), \(text), \($0)" } ?? "\(name), \(text)"
    }
}
